"""Face-validity diagnostics for a fixed v5 configuration (no fitting happens here)."""

import argparse
import json
import math
import sqlite3
from collections import defaultdict
from contextlib import closing
from datetime import date, timedelta
from itertools import groupby
from pathlib import Path

from upset.ratings.data import load_bouts
from upset.ratings import v5_research as R


def next_day(day):
    return (date.fromisoformat(day) + timedelta(days=1)).isoformat()


def run(prepared, v4, cfg, weights):
    """Replay with display strength = r + beta * post-fight skill, pass rule and holds on display."""
    v0, tau2, beta = cfg["v0"], cfg["tau2"], cfg["beta"]
    weight = {"finish": cfg["w_finish"], "decision": 1., "close": cfg["w_close"], "other": .5}
    r, v, last, n, shown = {}, {}, {}, defaultdict(int), {}
    post_skill = {}
    history = defaultdict(list)
    preds, wrong, holds, passes = [], 0, 0, 0

    def skill(prior):
        vec = R.skill_vector(prior)
        return 0. if vec is None else beta * sum(a * b for a, b in zip(weights, vec))

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
            g = 1 / math.sqrt(1 + 3 * (va + vb) / math.pi ** 2)
            p = R.sigmoid(g * ((ra + sa) - (rb + sb)))
            preds.append({"fight_id": bout["fight_id"], "event_date": day, "p": p, "prior_bouts": [n[ids[0]], n[ids[1]]],
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
                updates[uid].append((post_v * w * g * (y - q), post_v, ids[1 - side], y, bout))
        for uid, changes in updates.items():
            r[uid] += sum(c[0] for c in changes)
            v[uid] = min(c[1] for c in changes)
            last[uid] = day
            n[uid] += len(changes)
            post_skill[uid] = skill(R.v4_prior(v4, uid, next_day(day)))
        display = lambda uid: r[uid] + post_skill.get(uid, 0.)
        # Pass rule on the displayed strength.
        for uid, changes in updates.items():
            for _, _, opp, y, _ in changes:
                if y == 1 and display(opp) > display(uid):
                    gap = display(opp) - display(uid)
                    r[uid] += gap / 2 + 1e-6
                    r[opp] -= gap / 2 + 1e-6
                    passes += 1
        # Direction holds: a decisive winner never shows a lower number, a loser never a higher one.
        for uid, changes in updates.items():
            outcomes = {c[3] for c in changes}
            if uid in shown and len(outcomes) == 1:
                before, after = shown[uid], display(uid)
                if outcomes == {1} and after < before:
                    r[uid] += before - after; holds += 1
                elif outcomes == {0} and after > before:
                    r[uid] -= after - before; holds += 1
        for uid in updates:
            shown[uid] = display(uid)
            history[uid].append((day, shown[uid], v[uid], n[uid]))
    return preds, history, {"pass_adjustments": passes, "direction_holds": holds}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--database", type=Path, required=True)
    p.add_argument("--v4", type=Path, required=True)
    p.add_argument("--research", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    summary = json.loads((args.research / "summary.json").read_text())
    cfg, weights = summary["selected_pass_rule"], summary["skill_weights_striking_wrestling_grappling"]
    bouts, meta = load_bouts(args.database, "2026-11-08")
    v4 = R.load_v4(args.v4 / "ratings.jsonl")
    prepared = R.prepare(bouts, v4)
    preds, history, counts = run(prepared, v4, cfg, weights)
    test = R.metrics(R.eligible(preds, *R.TEST))
    train = R.metrics(R.eligible(preds, *R.TRAIN))
    recent = R.metrics(R.eligible(preds, "2025-01-01", "2099-01-01"))
    names, divisions = {}, {}
    with closing(sqlite3.connect(Path(args.database).as_uri() + "?mode=ro&immutable=1", uri=True)) as db:
        for uid, name in db.execute("SELECT id,name FROM fighters"):
            names[uid] = name
        titles = {row[0] for row in db.execute(
            "SELECT id FROM fights WHERE instr(json_extract(payload,'$.weight_class'),'Title')>0")}
    def at(uid, day):
        rows = [h for h in history.get(uid, []) if h[0] <= day]
        return rows[-1][1] if rows else None
    latest = {uid: rows[-1] for uid, rows in history.items()}
    active = {uid: row for uid, row in latest.items() if row[0] >= "2025-01-01"}
    strengths = sorted(row[1] for row in active.values())
    pct = lambda q: strengths[int(q * (len(strengths) - 1))]
    inversions = []
    for bout in bouts:
        if bout["event_date"] < "2025-01-01" or bout["winner_id"] is None or bout["fight_id"] not in titles:
            continue
        w = bout["winner_id"]; l = [u for u in bout["fighter_ids"] if u != w][0]
        inversions.append({"date": bout["event_date"], "winner": names[w], "loser": names[l],
                           "after": round(at(w, bout["event_date"]) - at(l, bout["event_date"]), 3),
                           "now": round(latest[w][1] - latest[l][1], 3)})
    top = sorted(active.items(), key=lambda kv: -kv[1][1])[:40]
    report = {"config": cfg, "counts": counts, "train": train, "test": test, "test_2025_26": recent,
              "active_fighters": len(active),
              "active_strength_percentiles": {q: round(pct(q), 3) for q in (.01, .1, .25, .5, .75, .9, .95, .99)},
              "active_max": round(strengths[-1], 3),
              "title_fights_since_2025": len(inversions),
              "title_winner_below_after_fight": sum(x["after"] < 0 for x in inversions),
              "title_winner_below_now": sum(x["now"] < 0 for x in inversions),
              "title_now_inversions": [x for x in inversions if x["now"] < 0],
              "top40": [(names[uid], round(row[1], 3), row[3]) for uid, row in top]}
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "diagnostics.json").write_text(json.dumps(report, indent=1))
    print(json.dumps({k: report[k] for k in report if k != "top40"}, indent=1)[:3500])
    for row in report["top40"]:
        print(row)


if __name__ == "__main__":
    main()
