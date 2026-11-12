"""Build UPSET Rating v5: one calibrated fighter-strength number, dated after every fight.

Walk-forward only. Each fight is predicted from ratings strictly before its date, and every
fight on one date is scored before any rating from that date changes. The model settings and
skill weights come from the v5 research run, which chose them on 2010-2018 fights only.
Nothing here refits the model; the display constants below never change a prediction.

Scale: 80 is the median active UFC fighter. Every 5 points doubles the odds between two
established fighters (85 vs 80 is about 2-to-1, 90 vs 80 about 4-to-1, 95 vs 80 about 8-to-1).

Rules the number must obey, checked here and again when the site loads the snapshot:
  * A winner never shows a lower number than before the fight; a loser never a higher one.
  * Right after a fight, the winner's number is at least the loser's ("pass rule").
  * Optional head-to-head lock (--h2h-lock, off in the served release): for two years after A
    beats B, B cannot rise above A while A stays unbeaten. Tested and rejected for v5 because
    it made the rating predict worse (2010-2018 log loss 0.6667 -> 0.6724); the site shows the
    head-to-head record beside the numbers instead.
  * The probability shown for a matchup comes from the same strengths as the number.
"""

import argparse
import hashlib
import json
import math
import pickle
import sqlite3
import time
from collections import Counter, defaultdict
from contextlib import closing
from datetime import date, timedelta
from itertools import groupby
from pathlib import Path
from statistics import median

from upset.ratings import v5_research as R
from upset.ratings.data import load_bouts

VERSION = "upset_rating_v5"
ROOT = Path(__file__).resolve().parents[3]
ACTIVE_DAYS = 730
LOCK_DAYS = 730
FLOOR, CAP, CENTER_SCORE, POINTS_PER_DOUBLING = 60, 99, 80, 5
# (stars, share of active fighters at or above this level, label)
STAR_LEVELS = ((5.0, .015, "Champion level"), (4.5, .06, "Title contender"), (4.0, .18, "Ranked caliber"),
               (3.5, .40, "Fringe contender"), (3.0, .65, "Solid UFC level"), (2.5, .85, "Below UFC average"))
BOTTOM = (2.0, "Lower tier")
GAP_BINS = ((0, 2), (3, 5), (6, 9), (10, 14), (15, 99))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def relative(path):
    return Path(path).resolve().relative_to(ROOT).as_posix()


def next_day(day):
    return (date.fromisoformat(day) + timedelta(days=1)).isoformat()


def load_v4_with_bouts(path):
    """v4 dated profiles as (date, raw_combined, z by part, score, bouts with stats so far)."""
    from statistics import NormalDist
    normal = NormalDist()
    rows = defaultdict(list)
    with open(path) as stream:
        for line in stream:
            row = json.loads(line)
            z = {}
            for part in row["parts"]:
                if part["key"] in ("striking", "wrestling", "grappling") and part.get("raw_score") is not None:
                    z[part["key"]] = normal.inv_cdf(min(.9999, max(.0001, part["raw_score"] / 100)))
            rows[row["fighter_id"]].append((row["event_date"], row["raw_combined"], z, row["score"], row["bouts"]))
    out = {}
    for uid, items in rows.items():
        items.sort(key=lambda r: r[0])
        out[uid] = ([r[0] for r in items], items)
    return out


def replay(prepared, v4, cfg, weights, lock=False):
    """The research replay with every dated state kept for serving.

    With a pass rule this is v5_diagnose.run (the displayed rating). Without one it is the
    unconstrained research model (the matchup forecast): no pass rule and no holds.
    """
    constrained = cfg["pass_rule"] is not None
    v0, tau2, beta = cfg["v0"], cfg["tau2"], cfg["beta"]
    weight = {"finish": cfg["w_finish"], "decision": 1., "close": cfg["w_close"], "other": .5}
    r, v, last, shown, post_skill = {}, {}, {}, {}, {}
    states, preds = defaultdict(list), []
    decisive = defaultdict(int)
    last_meeting, last_loss = {}, {}

    shrink_k = cfg.get("k", 0.)
    skill_var = cfg.get("vs", 0.)

    def skill_variance(prior):
        """Uncertainty of the skill term: vs / n for n prior bouts in the profile (vs for no profile)."""
        if not skill_var:
            return 0.
        return skill_var if prior is None or len(prior) < 5 else skill_var / max(1, prior[4])

    def skill(prior):
        """Skill term, shrunk toward the average for short UFC records: n / (n + k) with n prior bouts."""
        vec = R.skill_vector(prior)
        if vec is None:
            return 0.
        factor = 1.
        if len(prior) >= 5 and shrink_k:
            factor = prior[4] / (prior[4] + shrink_k)
        if len(prior) >= 5 and cfg.get("ramp"):
            factor = min(1., prior[4] / cfg["ramp"])
        return factor * beta * sum(a * b for a, b in zip(weights, vec))

    for day, batch in groupby(prepared, key=lambda b: b["event_date"]):
        updates = defaultdict(list)
        for bout in batch:
            ids = bout["fighter_ids"]
            pre = []
            for side, uid in enumerate(ids):
                if uid not in r:
                    r[uid], v[uid] = 0., v0
                var = v[uid] if uid not in last else min(v0, v[uid] + tau2 * max(0., R.years(last[uid], day)))
                pre.append((r[uid], var, skill(bout["v4"][side])))
            (ra, va, sa), (rb, vb, sb) = pre
            extra = skill_variance(bout["v4"][0]) + skill_variance(bout["v4"][1])
            g = 1 / math.sqrt(1 + 3 * (va + vb + extra) / math.pi ** 2)
            logit = g * ((ra + sa) - (rb + sb))
            preds.append({"fight_id": bout["fight_id"], "event_date": day, "p": R.sigmoid(logit), "g": g,
                          "fighter_ids": ids, "prior_bouts": [decisive[ids[0]], decisive[ids[1]]],
                          "pre_strength": [ra + sa, rb + sb],
                          "y": None if bout["winner_id"] is None else int(bout["winner_id"] == ids[0]),
                          "v4": [None if x is None else x[1] for x in bout["v4"]]})
            if bout["winner_id"] is None:
                continue
            w = weight[bout["kind"]]
            for side, uid in enumerate(ids):
                y = int(bout["winner_id"] == uid)
                (ri, vi, si), (rj, vj, sj) = pre[side], pre[1 - side]
                q = R.sigmoid(g * ((ri + si) - (rj + sj)))
                post_v = 1 / (1 / vi + w * g * g * q * (1 - q))
                updates[uid].append({"delta": post_v * w * g * (y - q), "post_v": post_v, "opponent_id": ids[1 - side],
                                     "outcome": "win" if y else "loss", "fight_id": bout["fight_id"],
                                     "method_kind": bout["kind"]})
        for uid, changes in updates.items():
            r[uid] += sum(c["delta"] for c in changes)
            v[uid] = min(c["post_v"] for c in changes)
            last[uid] = day
            decisive[uid] += len(changes)
            after = R.v4_prior(v4, uid, next_day(day))
            post_skill[uid] = skill(after)
            if cfg.get("display_ramp") and after is not None and len(after) >= 5:
                # Earned display: stats count in full only from the Nth UFC fight. Predictions keep the full term.
                post_skill[uid] *= min(1., after[4] / cfg["display_ramp"])

        def display(uid):
            return r[uid] + post_skill.get(uid, 0.)

        passed = defaultdict(list)
        for uid, changes in updates.items() if constrained else ():
            for change in changes:
                opp = change["opponent_id"]
                if change["outcome"] == "win" and display(opp) > display(uid):
                    gap = display(opp) - display(uid)
                    r[uid] += gap / 2 + 1e-6
                    r[opp] -= gap / 2 + 1e-6
                    passed[uid].append(opp)
        holds = {}
        for uid, changes in updates.items() if constrained else ():
            outcomes = {c["outcome"] for c in changes}
            if uid in shown and len(outcomes) == 1:
                before, after = shown[uid], display(uid)
                if outcomes == {"win"} and after < before:
                    r[uid] += before - after
                    holds[uid] = "held_after_win"
                elif outcomes == {"loss"} and after > before:
                    r[uid] -= after - before
                    holds[uid] = "held_after_loss"
        locked = {}
        if constrained and lock:
            for uid, changes in updates.items():
                if any(c["outcome"] == "loss" for c in changes):
                    last_loss[uid] = day
            horizon = (date.fromisoformat(day) - timedelta(days=LOCK_DAYS)).isoformat()
            for uid, changes in updates.items():
                holders = []
                for opp_key, (met, winner) in last_meeting.get(uid, {}).items():
                    if winner == opp_key and met >= horizon and last_loss.get(opp_key, "") <= met:
                        holders.append(opp_key)
                if not holders:
                    continue
                cap = min(display(a) for a in holders)
                beaten_today = [display(c["opponent_id"]) for c in changes if c["outcome"] == "win"]
                if beaten_today:
                    cap = max(cap, max(beaten_today))
                if all(c["outcome"] == "win" for c in changes) and uid in shown:
                    cap = max(cap, shown[uid])
                if display(uid) > cap:
                    r[uid] -= display(uid) - cap
                    locked[uid] = sorted(a for a in holders if display(a) <= cap + 1e-9)
            for uid, changes in updates.items():
                for c in changes:
                    winner = uid if c["outcome"] == "win" else c["opponent_id"]
                    last_meeting.setdefault(uid, {})[c["opponent_id"]] = (day, winner)
        for uid, changes in updates.items():
            states[uid].append({"event_date": day, "strength": display(uid), "results": r[uid],
                                "skill": post_skill.get(uid, 0.), "variance": v[uid],
                                "fights": [{key: c[key] for key in ("fight_id", "opponent_id", "outcome", "method_kind")}
                                           for c in changes],
                                "passed": passed[uid], "outcome_hold": holds.get(uid),
                                "locked_by": locked.get(uid, [])})
            shown[uid] = display(uid)
    return preds, states


def fit_slope(rows):
    c = 1.
    for _ in range(60):
        grad = hess = 0.
        for x, y in rows:
            p = R.sigmoid(c * x)
            grad += (y - p) * x
            hess += p * (1 - p) * x * x
        c += grad / hess
    return c


def odds_label(p):
    p = max(p, 1 - p)
    ratio = p / (1 - p)
    return "even" if ratio < 1.15 else f"{ratio:.1f}-to-1"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--v4", type=Path, required=True)
    parser.add_argument("--research", type=Path, required=True)
    parser.add_argument("--market", type=Path, help="Results benchmark predictions.jsonl with archived odds.")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--h2h-lock", action="store_true", help="Research option; not used for the release.")
    parser.add_argument("--display-ramp", type=int, default=0,
                        help="Earned display: stats count n/N of their weight until the Nth UFC fight (0 = v5.0).")
    parser.add_argument("--cache", type=Path, help="Scratch folder for resumable steps (outside the release).")
    args = parser.parse_args()
    started = time.time()
    database = args.database.resolve()
    database_key = digest(database)[:12]

    def cached(name, compute):
        """Resume long steps across short sessions; caches are keyed by the database hash."""
        if args.cache is None:
            return compute()
        path = args.cache / f"{name}.{database_key}.pickle"
        if path.exists():
            return pickle.loads(path.read_bytes())
        value = compute()
        args.cache.mkdir(parents=True, exist_ok=True)
        path.write_bytes(pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL))
        print(f"cached {name} after {time.time() - started:.0f}s", flush=True)
        return value

    if args.output.exists() and any(args.output.iterdir()):
        raise SystemExit("Output folder already has files; use a new folder.")
    database = args.database.resolve()
    v4_manifest = json.loads((args.v4 / "manifest.json").read_text())
    before = v4_manifest["before_exclusive"]
    summary = json.loads((args.research / "summary.json").read_text())
    cfg = {**summary["selected_pass_rule"], **({"display_ramp": args.display_ramp} if args.display_ramp else {})}
    provisional_below = max(4, args.display_ramp)
    weights = summary["skill_weights_striking_wrestling_grappling"]
    if summary["before_exclusive"] != before or summary["database_sha256"] != digest(database):
        raise SystemExit("Research run, v4 snapshot and database are not the same release.")

    bouts, meta = cached("bouts", lambda: load_bouts(database, before))
    v4 = cached("v4_with_bouts", lambda: load_v4_with_bouts(args.v4 / "ratings.jsonl"))

    def load_v4_parts():
        out = {}
        with (args.v4 / "ratings.jsonl").open() as stream:
            for line in stream:
                row = json.loads(line)
                out[(row["fighter_id"], row["event_date"])] = {"parts": row["parts"]}
        return out
    v4_rows = cached("v4_parts", load_v4_parts)
    v4_dates = defaultdict(list)
    for uid, day in sorted(v4_rows):
        v4_dates[uid].append(day)
    prepared = R.prepare(bouts, v4)
    preds, states = cached(f"rating_replay_ramp{args.display_ramp}" + ("_lock" if args.h2h_lock else ""),
                           lambda: replay(prepared, v4, cfg, weights, lock=args.h2h_lock))
    forecast_cfg = summary["selected"]
    if forecast_cfg["pass_rule"] is not None:
        raise SystemExit("The forecast model must be the unconstrained research selection.")
    forecast_preds, forecast_states = cached("forecast_replay_b", lambda: replay(prepared, v4, forecast_cfg, weights))
    forecast_at = {(uid, s["event_date"]): s for uid, rows_ in forecast_states.items() for s in rows_}
    latest = max(b["event_date"] for b in bouts)

    # --- Calibration (reported, not applied: the fitted slope stays at 1 unless it is far off).
    split = {name: R.eligible(preds, *window) for name, window in
             (("train", R.TRAIN), ("test", R.TEST), ("recent", ("2025-01-01", "2099-01-01")))}
    slopes = {name: round(fit_slope([(math.log(p["p"] / (1 - p["p"])), p["y"]) for p in rows]), 4)
              for name, rows in split.items()}
    if not .85 <= slopes["train"] <= 1.15:
        raise SystemExit("Training calibration slope is outside 0.85-1.15; the scale would mislead.")

    # --- Frozen display constants from the active roster at the latest event.
    active_since = (date.fromisoformat(latest) - timedelta(days=ACTIVE_DAYS)).isoformat()
    current = {uid: rows[-1] for uid, rows in states.items() if rows[-1]["event_date"] >= active_since}
    center = median(s["strength"] for s in current.values())
    skill_center = median(s["skill"] for s in current.values())
    g_typical = median(p["g"] for p in split["test"])
    per_unit = POINTS_PER_DOUBLING * g_typical / math.log(2)

    def score_of(strength):
        return int(min(CAP, max(FLOOR, math.floor(CENTER_SCORE + per_unit * (strength - center) + .5))))

    active_scores = sorted((score_of(s["strength"]) for s in current.values()), reverse=True)
    thresholds = []
    for stars, share, label in STAR_LEVELS:
        cut = active_scores[max(0, math.ceil(share * len(active_scores)) - 1)]
        if thresholds and cut >= thresholds[-1]["min_score"]:
            cut = thresholds[-1]["min_score"] - 1
        thresholds.append({"stars": stars, "min_score": cut, "label": label, "top_share": share})

    def stars_of(score):
        for level in thresholds:
            if score >= level["min_score"]:
                return level["stars"], level["label"]
        return BOTTOM

    # --- Bout counts (every UFC bout, including draws and no contests) for provisional status.
    bout_days = defaultdict(list)
    division_on = {}
    for bout in bouts:
        for uid in bout["fighter_ids"]:
            bout_days[uid].append(bout["event_date"])
            division_on[(uid, bout["event_date"])] = bout["division"]

    def bouts_through(uid, day):
        return sum(1 for d in bout_days[uid] if d <= day)

    def v4_row(uid, day):
        days = [d for d in v4_dates.get(uid, ()) if d <= day]
        return v4_rows[(uid, days[-1])] if days else None

    # --- Rows.
    rows, score_at = [], {}
    for uid in sorted(states):
        previous, peak = None, None
        for state in states[uid]:
            day = state["event_date"]
            score = score_of(state["strength"])
            peak = score if peak is None else max(peak, score)
            stars, tier = stars_of(score)
            n = bouts_through(uid, day)
            sd_points = per_unit * math.sqrt(state["variance"])
            skills_points = per_unit * (state["skill"] - skill_center)
            results_points = per_unit * (state["results"] - (center - skill_center))
            base = v4_row(uid, day)
            parts = []
            for part in (base or {}).get("parts", []):
                if part["key"] in ("striking", "wrestling", "grappling"):
                    parts.append({"key": part["key"], "label": part["label"],
                                  "score": int(math.floor(part["score"] + .5)), "raw_score": part["raw_score"],
                                  "metrics": part["metrics"]})
            parts.append({"key": "results", "label": "Results",
                          "score": int(min(CAP, max(FLOOR, math.floor(CENTER_SCORE + results_points + .5)))),
                          "raw_score": round(state["results"], 6),
                          "metrics": {"results_points": round(results_points, 3),
                                      "decisive_ufc_bouts": sum(len(s["fights"]) for s in states[uid] if s["event_date"] <= day)}})
            row = {"fighter_id": uid, "event_date": day, "fight_ids": [f["fight_id"] for f in state["fights"]],
                   "bouts": n, "provisional": n < provisional_below,
                   "confidence": "low" if n < provisional_below else "medium" if n < 8 else "high",
                   "score": score, "change": None if previous is None else score - previous,
                   "previous_score": previous, "peak": peak, "stars": stars, "tier": tier,
                   "strength": round(state["strength"], 6), "variance": round(state["variance"], 6),
                   "uncertainty_points": round(sd_points, 2),
                   "range": [max(FLOOR, score - round(sd_points)), min(CAP, score + round(sd_points))],
                   "contributions": {"skills": round(skills_points, 2), "results": round(results_points, 2)},
                   "skills_term": round(state["skill"], 6), "results_term": round(state["results"], 6),
                   "fights": state["fights"], "last_outcomes": [f["outcome"] for f in state["fights"]],
                   "passed": state["passed"], "outcome_hold": state["outcome_hold"], "locked_by": state["locked_by"],
                   "division": division_on.get((uid, day)), "parts": parts,
                   "forecast": {"strength": round(forecast_at[(uid, day)]["strength"], 6),
                                "variance": round(forecast_at[(uid, day)]["variance"], 6)}}
            if len(state["fights"]) == 1:
                row["fight_id"] = state["fights"][0]["fight_id"]
            rows.append(row)
            score_at[(uid, day)] = score
            previous = score

    # --- Integrity checks on the served integers.
    wrong_direction, pass_violations, multi_bout_days = 0, [], 0
    by_fighter = defaultdict(list)
    for row in rows:
        by_fighter[row["fighter_id"]].append(row)
    for history in by_fighter.values():
        for a, b in zip(history, history[1:]):
            outcomes = set(b["last_outcomes"])
            if (outcomes == {"win"} and b["score"] < a["score"]) or (outcomes == {"loss"} and b["score"] > a["score"]):
                wrong_direction += 1
    for row in rows:
        if len(row["fights"]) > 1:
            multi_bout_days += 1
            continue
        fight = row["fights"][0]
        if fight["outcome"] == "win":
            loser = score_at.get((fight["opponent_id"], row["event_date"]))
            if loser is not None and row["score"] < loser and len([f for f in by_fighter[fight["opponent_id"]]
                                                                    if f["event_date"] == row["event_date"]][0]["fights"]) == 1:
                pass_violations.append(fight["fight_id"])

    # --- Title fights: winner at or above loser right after the fight, and now.
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro&immutable=1", uri=True)) as db:
        names = dict(db.execute("SELECT id,name FROM fighters"))
        titles = {row[0] for row in db.execute(
            "SELECT id FROM fights WHERE instr(json_extract(payload,'$.weight_class'),'Title')>0")}
    latest_score = {uid: history[-1]["score"] for uid, history in by_fighter.items()}
    title_checks = []
    for bout in bouts:
        if bout["fight_id"] not in titles or bout["winner_id"] is None or bout["event_date"] < "2019-01-01":
            continue
        winner = bout["winner_id"]
        loser = [u for u in bout["fighter_ids"] if u != winner][0]
        after = score_at[(winner, bout["event_date"])] - score_at[(loser, bout["event_date"])]
        title_checks.append({"date": bout["event_date"], "winner": names[winner], "loser": names[loser],
                             "gap_after": after, "gap_now": latest_score[winner] - latest_score[loser]})

    # --- Head-to-head locks still broken at the latest event (should be none or explained).
    meetings = {}
    for uid, history in by_fighter.items():
        for row in history:
            for fight in row["fights"]:
                if fight["outcome"] == "win":
                    key = frozenset((uid, fight["opponent_id"]))
                    if key not in meetings or meetings[key][0] <= row["event_date"]:
                        meetings[key] = (row["event_date"], uid, fight["opponent_id"])
    lock_horizon = (date.fromisoformat(latest) - timedelta(days=LOCK_DAYS)).isoformat()
    h2h_now = []
    for met, winner, loser in meetings.values():
        if met < lock_horizon or any(f["outcome"] == "loss" for row in by_fighter[winner] if row["event_date"] > met
                                     for f in row["fights"]):
            continue
        if latest_score[loser] > latest_score[winner]:
            h2h_now.append({"date": met, "winner": names.get(winner), "loser": names.get(loser),
                            "winner_score": latest_score[winner], "loser_score": latest_score[loser]})

    # --- Track record and scale check with pre-fight integers (test window, both fighters rated).
    def pre_score(uid, day):
        history = [h for h in by_fighter.get(uid, ()) if h["event_date"] < day]
        return history[-1]["score"] if history else None

    wins = ties = unavailable = total = 0
    gap_rows = defaultdict(list)
    for p in preds:
        if p["event_date"] < R.TEST[0] or p["y"] is None:
            continue
        a, b = (pre_score(uid, p["event_date"]) for uid in p["fighter_ids"])
        if a is None or b is None:
            unavailable += 1
            continue
        if a == b:
            ties += 1
            continue
        total += 1
        favorite_won = (a > b) == bool(p["y"])
        wins += favorite_won
        gap = abs(a - b)
        for lo, hi in GAP_BINS:
            if lo <= gap <= hi:
                gap_rows[(lo, hi)].append((max(p["p"], 1 - p["p"]) if (p["p"] > .5) == (a > b) else min(p["p"], 1 - p["p"]),
                                           favorite_won))
    scale_check = []
    for (lo, hi), items in sorted(gap_rows.items()):
        scale_check.append({"gap": f"{lo}-{hi}", "bouts": len(items),
                            "model_favorite_probability": round(sum(x for x, _ in items) / len(items), 3),
                            "higher_rated_won": round(sum(y for _, y in items) / len(items), 3),
                            "rule_of_thumb": round(1 / (1 + 2 ** (-((lo + min(hi, 20)) / 2) / POINTS_PER_DOUBLING)), 3)})
    calibration = []
    for lo, hi in ((.5, .55), (.55, .6), (.6, .65), (.65, .7), (.7, .75), (.75, .8), (.8, 1.)):
        items = [(max(p["p"], 1 - p["p"]), int((p["p"] > .5) == bool(p["y"]))) for p in split["test"]
                 if lo <= max(p["p"], 1 - p["p"]) < hi and p["p"] != .5]
        if items:
            calibration.append({"bin": [lo, hi], "bouts": len(items),
                                "predicted": round(sum(x for x, _ in items) / len(items), 3),
                                "actual": round(sum(y for _, y in items) / len(items), 3)})

    # --- Archived market odds on the same bouts (optional).
    market = None
    if args.market:
        by_fight = {p["fight_id"]: p for p in preds}
        by_forecast = {p["fight_id"]: p for p in forecast_preds}
        matched = []
        with args.market.open() as stream:
            for line in stream:
                row = json.loads(line)
                quote = row.get("market")
                mine = by_fight.get(row["fight_id"])
                if not quote or not mine or mine["y"] is None:
                    continue
                p = mine["p"] if mine["fighter_ids"] == row["fighter_ids"] else 1 - mine["p"]
                f = by_forecast[row["fight_id"]]["p"]
                f = f if mine["fighter_ids"] == row["fighter_ids"] else 1 - f
                y = int(row["winner_a"])
                matched.append({"event_date": row["event_date"], "y": y, "v5": p, "forecast": f,
                                "v4": row["probabilities"]["v4_fixed"], "market": quote["probability_a"]})

        def score(key):
            ll = -sum(math.log(m[key] if m["y"] else 1 - m[key]) for m in matched) / len(matched)
            acc = sum((m[key] > .5) == bool(m["y"]) for m in matched) / len(matched)
            return {"log_loss": round(ll, 4), "accuracy": round(acc, 4)}
        market = {"bouts": len(matched), "source": "Archived BetOnline.ag prices, 1-7 days before each event (no-vig)",
                  "v5_rating": score("v5"), "v5_forecast": score("forecast"), "v4_declared": score("v4"),
                  "market": score("market")}

    v5_metrics = {name: R.metrics(rows_) for name, rows_ in split.items()}
    forecast_metrics = {name: R.metrics(R.eligible(forecast_preds, *window)) for name, window in
                        (("train", R.TRAIN), ("test", R.TEST), ("recent", ("2025-01-01", "2099-01-01")))}
    comparison = summary["comparison"]
    evaluation = {
        "version": VERSION,
        "evaluation_label": ("Walk-forward replay: every fight predicted only from earlier fights, settings chosen on "
                             "2010-2018 and 2019 onward scored once. Historical, not a live forecast record."),
        "track_record": {"from_date": R.TEST[0], "before_exclusive": before, "wins": wins, "total": total,
                         "accuracy": wins / total, "ties_excluded": ties, "unavailable_excluded": unavailable,
                         "label": "Higher-rated fighter's record in every UFC fight since 2019, using ratings from before each fight."},
        "metrics": {"v5": v5_metrics, "v5_forecast": forecast_metrics,
                    "v4": comparison["v4_declared_slope"], "elo32": comparison["elo32"],
                    "elo64_decay": comparison["elo64_decay"], "results_only": comparison["results_only"],
                    "v5_unconstrained": comparison["v5"]},
        "calibration_slope": slopes, "calibration_test": calibration, "scale_check": scale_check,
        "market": market,
        "integrity": {"wrong_direction_updates": wrong_direction, "pass_rule_violations": len(pass_violations),
                      "multi_bout_days_skipped": multi_bout_days,
                      "pass_adjustments": sum(len(r["passed"]) for r in rows),
                      "outcome_holds": sum(r["outcome_hold"] is not None for r in rows),
                      "title_fights_since_2019": len(title_checks),
                      "title_winner_below_after_fight": sum(t["gap_after"] < 0 for t in title_checks),
                      "title_winner_below_now": [t for t in title_checks if t["gap_now"] < 0],
                      "head_to_head_locks_applied": sum(bool(r["locked_by"]) for r in rows),
                      "head_to_head_inversions_now": h2h_now},
        "distribution": {"active_since": active_since, "active_fighters": len(current),
                         "score_percentiles": {str(q): active_scores[int((1 - q) * (len(active_scores) - 1))]
                                               for q in (.01, .1, .25, .5, .75, .9, .95, .99)},
                         "at_cap": sum(s == CAP for s in active_scores),
                         "stars": dict(Counter(stars_of(s)[0] for s in active_scores))},
        "top_active": [{"name": names.get(uid), "score": by_fighter[uid][-1]["score"],
                        "stars": by_fighter[uid][-1]["stars"], "bouts": by_fighter[uid][-1]["bouts"],
                        "last_fight": by_fighter[uid][-1]["event_date"]}
                       for uid in sorted(current, key=lambda u: -current[u]["strength"])[:40]],
    }
    # The displayed number as a predictor: pre-fight display strengths (differs from the internal
    # strength only when the earned-display ramp is on).
    from bisect import bisect_left as _bl
    shown = {uid: ([s["event_date"] for s in st], st) for uid, st in states.items()}

    def shown_before(uid, day):
        days, st = shown.get(uid, ([], []))
        i = _bl(days, day)
        return st[i - 1]["strength"] if i else None
    display_metrics = {}
    for label, window in (("train", R.TRAIN), ("test", R.TEST), ("recent", ("2025-01-01", "2099-01-01"))):
        rows_ = []
        for p in R.eligible(preds, *window):
            a, b = (shown_before(uid, p["event_date"]) for uid in p["fighter_ids"])
            if a is not None and b is not None:
                rows_.append({**p, "p": R.sigmoid(p["g"] * (a - b))})
        display_metrics[label] = R.metrics(rows_)
    evaluation["metrics"]["v5_display"] = display_metrics
    diag_ll = json.loads((args.research / "diag" / "diagnostics.json").read_text())["test"]["log_loss"]
    evaluation["research_replay_test_log_loss"] = diag_ll
    evaluation["engineering_checks_passed"] = bool(
        wrong_direction == 0 and not pass_violations and evaluation["integrity"]["title_winner_below_after_fight"] == 0
        and abs(v5_metrics["test"]["log_loss"] - diag_ll) <= .002
        and forecast_metrics["test"]["log_loss"] == comparison["v5"]["test"]["log_loss"]
        and forecast_metrics["test"]["log_loss"] <= comparison["v4_declared_slope"]["test"]["log_loss"] - .004
        and v5_metrics["test"]["log_loss"] <= comparison["v4_declared_slope"]["test"]["log_loss"] + .002
        and display_metrics["test"]["log_loss"] < comparison["elo64_decay"]["test"]["log_loss"]
        and evaluation["distribution"]["at_cap"] <= 5)

    args.output.mkdir(parents=True, exist_ok=True)
    with (args.output / "ratings.jsonl").open("w") as stream:
        for row in rows:
            stream.write(json.dumps(row, sort_keys=True) + "\n")
    (args.output / "evaluation.json").write_text(json.dumps(evaluation, indent=1))
    with (args.output / "forecasts.jsonl").open("w") as stream:
        for p, f in zip(preds, forecast_preds):
            assert p["fight_id"] == f["fight_id"]
            stream.write(json.dumps({"fight_id": p["fight_id"], "event_date": p["event_date"],
                                     "fighter_ids": p["fighter_ids"], "forecast": round(f["p"], 6),
                                     "rating_probability": round(p["p"], 6), "y": p["y"],
                                     "prior_decisive_bouts": f["prior_bouts"]}, sort_keys=True) + "\n")
    inputs = [database, database.parent / "manifest.json", args.v4 / "ratings.jsonl", args.v4 / "manifest.json",
              args.research / "summary.json", args.research / "diag" / "diagnostics.json",
              Path(__file__), Path(R.__file__), ROOT / "src/upset/ratings/data.py"]
    if args.market:
        inputs.append(args.market)
    manifest = {
        "version": VERSION, "revision": "5.1" if args.display_ramp else "5.0", "experimental": True, "validated": False,
        "input_database": relative(database), "database_sha256": digest(database),
        "before_exclusive": before, "latest_event": latest,
        "model": {**cfg, "head_to_head_lock": args.h2h_lock, "skill_weights_striking_wrestling_grappling": weights,
                  "probability": "P(A beats B) = 1 / (1 + exp(-g * (strength_A - strength_B))), g = 1/sqrt(1 + 3(var_A+var_B)/pi^2)",
                  "settings_chosen_on": list(R.TRAIN), "scored_once_on": list(R.TEST)},
        "display_curve": {"reference_before": R.TEST[0]},
        "scale": {"center_score": CENTER_SCORE, "center_strength": center, "skill_center": skill_center,
                  "points_per_unit": per_unit, "points_per_doubling": POINTS_PER_DOUBLING,
                  "typical_g": g_typical, "floor": FLOOR, "cap": CAP, "active_days": ACTIVE_DAYS,
                  "variance_prior": cfg["v0"], "variance_growth_per_year": cfg["tau2"],
                  "rule": "80 is the median active UFC fighter; every 5 points doubles the odds.",
                  "provisional_below": provisional_below, "display_ramp": args.display_ramp},
        "stars": {"levels": thresholds, "bottom": {"stars": BOTTOM[0], "label": BOTTOM[1]},
                  "basis": f"Share of {len(current)} UFC fighters active since {active_since}"},
        "input_sha256": {relative(path): digest(path) for path in inputs},
    }
    manifest["forecast_model"] = {**forecast_cfg, "basis": "Unconstrained research selection; same skill weights."}
    manifest["output_sha256"] = {name: digest(args.output / name)
                                 for name in ("ratings.jsonl", "evaluation.json", "forecasts.jsonl")}
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=1))
    print(json.dumps({key: evaluation[key] for key in ("track_record", "metrics", "calibration_slope", "scale_check",
                                                       "market", "integrity", "distribution", "engineering_checks_passed")},
                     indent=1)[:6000])
    print(json.dumps(manifest["scale"], indent=1), json.dumps(thresholds))
    for row in evaluation["top_active"][:30]:
        print(row)


if __name__ == "__main__":
    main()
