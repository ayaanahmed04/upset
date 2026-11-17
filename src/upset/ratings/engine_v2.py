"""Dated v2 rating features, including opponent-adjusted KO/TKO wins.

The replay follows v1's chronology and shares its invariant helpers. Its
feature-aware stages are kept here to preserve the frozen v1 engine.
"""

from collections import Counter, defaultdict
from copy import deepcopy
from dataclasses import replace
from datetime import date
from itertools import groupby
from math import fsum, isfinite, sqrt

from upset.ratings.engine import (
    FEATURES as V1_FEATURES,
    MIN_CONTEXT_PEERS,
    PARTS,
    Feature,
    History,
    _add,
    _observations,
    _pooled_baseline,
    _rate,
    elo_expectation,
    normal_score,
)

VERSION = "experimental_rating_features_v2"
FEATURES = {
    key: replace(spec, weight=spec.weight * .90) if spec.part == "striking" else spec
    for key, spec in V1_FEATURES.items()
}
FEATURES["ko_win"] = Feature("striking", "ko_win", 1, "ko_loss", 1, 0, 5, .10, .10)


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
        "ko_wins_per_bout": _rate(raw, "ko_win"),
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
