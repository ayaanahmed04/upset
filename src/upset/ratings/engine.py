"""Dated experimental rating features, with frozen same-date opponent contexts.

This is a deterministic feature replay, not a fitted skill or winner model.
Own feature observations are compared with an opponent's earlier pooled rate.
Adjusted numerators are exposure weighted, decay by .85 per earlier bout, and
shrink toward zero. Population rate fallbacks and peer scaling use earlier dates
only. Post-date snapshots are latched until that fighter next appears.
"""

from collections import Counter, defaultdict
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date
from itertools import groupby
from math import erf, fsum, isfinite, sqrt

VERSION = "experimental_rating_features_v1"
PARTS = ("striking", "wrestling", "grappling", "resume")


@dataclass(frozen=True)
class Feature:
    part: str
    raw: str
    own_sign: float
    opposing: str
    opposing_sign: float
    offset: float
    prior: float
    floor: float
    weight: float


# Numerators for per-15-minute rates already contain the factor fifteen.
# The priors below are in raw opportunity units, not in number of strikes won.
FEATURES = {
    "sig_diff": Feature("striking", "sig_diff", 1, "sig_diff", -1, 0, 45, 1., .30),
    "sig_accuracy": Feature("striking", "sig_accuracy", 1, "sig_conceded_accuracy", 1, 0, 500, .10, .15),
    "sig_defense": Feature("striking", "sig_conceded_accuracy", -1, "sig_accuracy", -1, 0, 500, .10, .20),
    "kd_scored": Feature("striking", "kd_scored", 1, "kd_received", 1, 0, 45, .5, .20),
    "kd_avoided": Feature("striking", "kd_received", -1, "kd_scored", -1, 0, 45, .5, .10),
    "ko_avoided": Feature("striking", "ko_loss", -1, "ko_win", -1, 0, 5, .10, .05),
    "td_rate": Feature("wrestling", "td_rate", 1, "td_received", 1, 0, 45, 1., .25),
    "td_accuracy": Feature("wrestling", "td_accuracy", 1, "td_conceded_accuracy", 1, 0, 50, .10, .20),
    "td_defense": Feature("wrestling", "td_conceded_accuracy", -1, "td_accuracy", -1, 0, 50, .10, .35),
    "control_share": Feature("wrestling", "control_share", 1, "control_share", -1, 1, 45, .15, .20),
    "sub_rate": Feature("grappling", "sub_rate", 1, "sub_received", 1, 0, 45, .5, .30),
    "sub_win": Feature("grappling", "sub_win", 1, "sub_loss", 1, 0, 5, .10, .25),
    "sub_avoided": Feature("grappling", "sub_loss_eff", -1, "sub_win_eff", -1, 0, 20, .10, .20),
    "ground_diff": Feature("grappling", "ground_diff", 1, "ground_diff", -1, 0, 45, .5, .25),
}

RAW_PRIORS = {
    "sig_diff": 45, "sig_landed": 45, "sig_absorbed": 45,
    "sig_accuracy": 500, "sig_conceded_accuracy": 500,
    "kd_scored": 45, "kd_received": 45, "ko_win": 5, "ko_loss": 5,
    "td_rate": 45, "td_received": 45, "td_accuracy": 50,
    "td_conceded_accuracy": 50, "control_share": 45,
    "sub_rate": 45, "sub_received": 45, "sub_win": 5, "sub_loss": 5,
    "sub_win_eff": 20, "sub_loss_eff": 20, "ground_diff": 45,
}
NEUTRAL = {key: .5 if "accuracy" in key or key == "control_share" else 0.
           for key in RAW_PRIORS}
MIN_CONTEXT_PEERS = 20


@dataclass
class History:
    raw: dict = field(default_factory=dict)
    adjusted: dict = field(default_factory=dict)
    baseline_context: Counter = field(default_factory=Counter)
    bouts: int = 0
    division: str | None = None
    elo: float = 1500.
    snapshot: dict | None = None


def normal_score(value):
    return 50 * (1 + erf(value / sqrt(2)))


def elo_expectation(a, b):
    small = 10 ** (-abs(a-b)/400)
    return 1/(1+small) if a >= b else small/(1+small)


def _add(counts, key, numerator, denominator):
    if denominator <= 0:
        return
    values = counts.setdefault(key, [0., 0.])
    values[0] += numerator
    values[1] += denominator


def _observations(bout, side):
    own, opposing = bout["stats"][side], bout["stats"][1-side]
    uid = bout["fighter_ids"][side]
    minutes = bout["duration_seconds"]/60
    win = bout["winner_id"] == uid
    loss = bout["winner_id"] is not None and not win
    ko = bout["method_group"] == "ko"
    sub = bout["method_group"] == "sub"
    values = {}
    def put(key, numerator, denominator):
        if numerator is not None and denominator is not None and denominator > 0:
            values[key] = (float(numerator), float(denominator))
    put("sig_diff", own["sig_strikes_landed"]-opposing["sig_strikes_landed"], minutes)
    put("sig_landed", own["sig_strikes_landed"], minutes)
    put("sig_absorbed", opposing["sig_strikes_landed"], minutes)
    put("sig_accuracy", own["sig_strikes_landed"], own["sig_strikes_attempted"])
    put("sig_conceded_accuracy", opposing["sig_strikes_landed"], opposing["sig_strikes_attempted"])
    put("kd_scored", 15*own["knockdowns"], minutes)
    put("kd_received", 15*opposing["knockdowns"], minutes)
    put("ko_win", int(win and ko), 1)
    put("ko_loss", int(loss and ko), 1)
    put("td_rate", 15*own["takedowns_landed"], minutes)
    put("td_received", 15*opposing["takedowns_landed"], minutes)
    put("td_accuracy", own["takedowns_landed"], own["takedowns_attempted"])
    put("td_conceded_accuracy", opposing["takedowns_landed"], opposing["takedowns_attempted"])
    if own["control_seconds"] is not None and opposing["control_seconds"] is not None:
        put("control_share", own["control_seconds"]/60,
            (own["control_seconds"]+opposing["control_seconds"])/60)
    put("sub_rate", 15*own["submission_attempts"], minutes)
    put("sub_received", 15*opposing["submission_attempts"], minutes)
    put("sub_win", int(win and sub), 1)
    put("sub_loss", int(loss and sub), 1)
    if int(win and sub) <= own["submission_attempts"]:
        put("sub_win_eff", int(win and sub), own["submission_attempts"])
    if int(loss and sub) <= opposing["submission_attempts"]:
        put("sub_loss_eff", int(loss and sub), opposing["submission_attempts"])
    put("ground_diff", own["ground_landed"]-opposing["ground_landed"], minutes)
    return values


def _rate(counts, key):
    values = counts.get(key)
    return values[0]/values[1] if values and values[1] > 0 else None


def _pooled_baseline(history, key, division, pools, minutes_prior):
    # With no earlier observations at all, use explicit neutral startup values.
    population = pools.get(division, {}).get(key) if division is not None else None
    if population and population[1] > 0:
        baseline, basis = population[0]/population[1], "division"
    else:
        population = pools.get(None, {}).get(key)
        if population and population[1] > 0:
            baseline, basis = population[0]/population[1], "global"
        else:
            baseline, basis = NEUTRAL[key], "neutral_start"
    own = history.raw.get(key, (0., 0.))
    prior = minutes_prior if RAW_PRIORS[key] == 45 else RAW_PRIORS[key]
    return (own[0]+prior*baseline)/(own[1]+prior), basis


def _adjusted_rate(history, key, minutes_prior):
    values = history.adjusted.get(key)
    if not values or values[1] <= 0:
        return None
    spec = FEATURES[key]
    prior = minutes_prior if spec.prior == 45 else spec.prior
    return values[0]/(values[1]+prior)


def _peer_context(histories, minutes_prior):
    by_division = defaultdict(lambda: defaultdict(list))
    for state in histories.values():
        for key in FEATURES:
            value = _adjusted_rate(state, key, minutes_prior)
            if value is not None:
                by_division[None][key].append(value)
                if state.division is not None:
                    by_division[state.division][key].append(value)
    result = {}
    for division in by_division.keys() | {None}:
        result[division] = {}
        for key, spec in FEATURES.items():
            peers = by_division[division][key]
            if division is not None and len(peers) >= MIN_CONTEXT_PEERS:
                basis = "division"
            else:
                peers = by_division[None][key]
                basis = "global" if peers else "floor_only"
            mean = fsum(peers)/len(peers) if peers else 0.
            variance = fsum((p-mean)**2 for p in peers)/len(peers) if peers else 0.
            result[division][key] = {"basis": basis, "peers": len(peers),
                                     "mean": mean, "std": max(spec.floor, sqrt(variance))}
    return result


def _snapshot(uid, state, day, context, minutes_prior):
    parts, available, feature_z, contexts = {}, {}, {}, {}
    for part in PARTS[:-1]:
        numerators, weights, names = [], [], []
        for key, spec in FEATURES.items():
            if spec.part != part:
                continue
            value = _adjusted_rate(state, key, minutes_prior)
            if value is None:
                continue
            scale = context.get(state.division, context[None])[key]
            z = max(-3., min(3., (value-scale["mean"])/scale["std"]))
            numerators.append(spec.weight*z)
            weights.append(spec.weight)
            names.append(key)
            feature_z[key] = z
            contexts[key] = dict(scale)
        parts[part] = normal_score(fsum(numerators)/fsum(weights)) if weights else None
        available[part] = names
    parts["resume"] = normal_score((state.elo-1500)/200)
    raw = state.raw
    metrics = {
        "sig_landed_per_minute": _rate(raw, "sig_landed"),
        "sig_absorbed_per_minute": _rate(raw, "sig_absorbed"),
        "sig_differential_per_minute": _rate(raw, "sig_diff"),
        "striking_accuracy": _rate(raw, "sig_accuracy"),
        "striking_defense": None if _rate(raw, "sig_conceded_accuracy") is None else 1-_rate(raw, "sig_conceded_accuracy"),
        "knockdowns_per_15_minutes": _rate(raw, "kd_scored"),
        "knockdowns_received_per_15_minutes": _rate(raw, "kd_received"),
        "ko_losses_per_bout": _rate(raw, "ko_loss"),
        "takedowns_per_15_minutes": _rate(raw, "td_rate"),
        "takedown_accuracy": _rate(raw, "td_accuracy"),
        "takedown_defense": None if _rate(raw, "td_conceded_accuracy") is None else 1-_rate(raw, "td_conceded_accuracy"),
        "control_share": _rate(raw, "control_share"),
        "submission_attempts_per_15_minutes": _rate(raw, "sub_rate"),
        "submission_wins_per_bout": _rate(raw, "sub_win"),
        "submission_losses_per_opponent_attempt": _rate(raw, "sub_loss_eff"),
        "ground_strike_differential_per_minute": _rate(raw, "ground_diff"),
    }
    return {"fighter_id": uid, "event_date": day, "bouts": state.bouts,
            "division": state.division, "elo": state.elo, "raw_parts": parts,
            "metrics": metrics, "coverage": {"available_features": available,
                "context_by_feature": contexts, "feature_z": feature_z,
                "feature_exposures": {key: pair[1] for key, pair in state.adjusted.items()},
                "opponent_baseline_context": dict(state.baseline_context),
                "weighted_minutes": raw.get("sig_landed", (0., 0.))[1]}}


def replay(bouts, minutes_prior=45, recency=.85):
    """Return post-date snapshots and strictly earlier, latched pre-fight parts.

    Within one date every opponent baseline and Elo expectation is frozen.
    Existing own counts decay by recency**number_of_same_date_bouts; all new
    same-date observations have equal weight one. Context pools are cumulative
    earlier observed opportunities, not recency-weighted across the roster.
    """
    if not isfinite(minutes_prior) or minutes_prior <= 0 or not 0 < recency <= 1:
        raise ValueError("Use positive prior minutes and recency in (0,1].")
    histories, pools, snapshots, prefights = {}, defaultdict(dict), [], []
    ordered = sorted(bouts, key=lambda b: (b["event_date"], b["fight_id"]))
    seen = set()
    for bout in ordered:
        if (date.fromisoformat(bout["event_date"]).isoformat() != bout["event_date"]
                or bout["fight_id"] in seen or len(set(bout["fighter_ids"])) != 2):
            raise ValueError("Invalid date, duplicate bout or participants.")
        seen.add(bout["fight_id"])
    for day, dated in groupby(ordered, key=lambda b: b["event_date"]):
        batch = list(dated)
        context = _peer_context(histories, minutes_prior)
        observations = defaultdict(list)
        elo_changes, bout_counts, divisions = defaultdict(list), Counter(), defaultdict(set)
        for bout in batch:
            ids = bout["fighter_ids"]
            states = [histories.get(uid, History()) for uid in ids]
            expectation = elo_expectation(states[0].elo, states[1].elo)
            cold = {part: 50. for part in PARTS}
            prefights.append({"fight_id": bout["fight_id"], "event_date": day,
                "fighter_ids": list(ids), "winner_id": bout["winner_id"], "outcome": bout["outcome"],
                "parts": [deepcopy(s.snapshot["raw_parts"]) if s.snapshot else dict(cold) for s in states],
                "prior_bouts": [s.bouts for s in states],
                "prior_snapshot_dates": [s.snapshot["event_date"] if s.snapshot else None for s in states]})
            if bout["winner_id"] is not None:
                if bout["winner_id"] not in ids:
                    raise ValueError("Winner is not a participant.")
                change = 32 * (int(bout["winner_id"] == ids[0])-expectation)
                elo_changes[ids[0]].append(change)
                elo_changes[ids[1]].append(-change)
            for side, uid in enumerate(ids):
                raw = _observations(bout, side)
                adjusted, basis_counts = {}, Counter()
                for key, spec in FEATURES.items():
                    if spec.raw not in raw:
                        continue
                    numerator, denominator = raw[spec.raw]
                    opposing, basis = _pooled_baseline(states[1-side], spec.opposing,
                                                       bout["division"], pools, minutes_prior)
                    expected = spec.offset+spec.opposing_sign*opposing
                    adjusted[key] = (spec.own_sign*numerator-expected*denominator, denominator)
                    basis_counts[basis] += 1
                observations[uid].append((raw, adjusted, basis_counts, bout["division"]))
                bout_counts[uid] += 1
                divisions[uid].add(bout["division"])
        # No participant update or population-pool mutation occurs above here.
        for uid in sorted(observations):
            state = histories.setdefault(uid, History())
            factor = recency**bout_counts[uid]
            for counts in (state.raw, state.adjusted):
                for pair in counts.values():
                    pair[0] *= factor
                    pair[1] *= factor
            for raw, adjusted, basis_counts, division in observations[uid]:
                for key, (num, den) in raw.items():
                    _add(state.raw, key, num, den)
                    _add(pools[None], key, num, den)
                    if division is not None:
                        _add(pools[division], key, num, den)
                for key, (num, den) in adjusted.items():
                    _add(state.adjusted, key, num, den)
                state.baseline_context.update(basis_counts)
            state.elo += fsum(elo_changes[uid])
            state.bouts += bout_counts[uid]
            classified = divisions[uid] - {None}
            if len(classified) == 1:
                state.division = next(iter(classified))
            elif len(classified) > 1:
                state.division = None
            state.snapshot = _snapshot(uid, state, day, context, minutes_prior)
            snapshots.append(deepcopy(state.snapshot))
    return snapshots, prefights
