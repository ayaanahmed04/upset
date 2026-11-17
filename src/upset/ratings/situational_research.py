"""Can situational, analyst-style factors improve the UPSET forecast (revision 5.2)?

Inspired by how fight analysts break down matchups. Each candidate is built only from fights before
the bout, added to the 5.2 forecast, fit on 2010-2018 and scored once on the 3,177-fight record set
since 2019 (95% intervals by resampling event dates). Because the 2019+ set has been used before, a
candidate must also improve both halves of it (2019-2022 and 2023+) to count.

1. Style splits (the "his averages describe a fight B won't give him" idea): how this fighter has
   done against opponents of the upcoming opponent's style (grappler, striker, mixed), measured as
   results above or below what the forecast expected, pulled toward zero when there are few such fights.
2. Staying down: how long a fighter stays controlled once taken down, against the opponent's
   takedown pressure ("the get-up game").
3. Mileage: prior KO/TKO losses, knockdowns absorbed and total UFC minutes, beyond age.
4. Stance: southpaw against orthodox.
5. Reach difference.
6. Small cage: grappler-vs-striker at the UFC Apex (smaller octagon) against bigger arenas.
"""

import argparse
import json
import random
import sqlite3
from collections import defaultdict
from contextlib import closing
from itertools import groupby
from pathlib import Path

from upset.ratings import v5_adjustments_research as R
from upset.ratings.style_matchup_research import Profile, add, describe, label, league_averages, percentile

TRAIN = ("2010-01-01", "2018-12-31")
TEST_FROM = "2019-01-01"
HALVES = (("2019-2022", "2019-01-01", "2022-12-31"), ("2023 on", "2023-01-01", "2099-12-31"))


def load(database, events_path):
    with closing(sqlite3.connect(database)) as db:
        profiles = {uid: json.loads(p or "{}") or {} for uid, p in db.execute("SELECT id,profile FROM fighters")}
        fights, stats = {}, defaultdict(dict)
        for fid, day, payload in db.execute("SELECT id,event_date,payload FROM fights"):
            p = json.loads(payload)
            result = p.get("reviewed_result") or p
            names = [p["fighter_1_name"], p["fighter_2_name"]]
            winner = result.get("winner_name")
            method = result.get("result_method") or ""
            fights[fid] = {"day": day, "ids": [p.get("upset_fighter_1_id"), p.get("upset_fighter_2_id")],
                           "loser": None if winner is None else (1 if winner == names[0] else 0 if winner == names[1] else None),
                           "ko": method.startswith(("KO", "TKO"))}
        for fid, uid, payload in db.execute("SELECT fight_id,fighter_id,payload FROM stats"):
            stats[fid][uid] = json.loads(payload)
    events = json.loads(Path(events_path).read_text()) if events_path else {}
    return profiles, fights, stats, events


def small_cage(info, day):
    """UFC Apex: named in the location, or a Las Vegas Fight Night from mid-2020 on (pay-per-views use the big arena)."""
    where, title = (info.get("location") or "").lower(), (info.get("title") or "").lower()
    if "apex" in where:
        return True
    return "las vegas" in where and "fight night" in title and day >= "2020-06-01"


def build(profiles, fights, stats, events, forecasts, adjusted, fixed_cut=None):
    league = {**league_averages(fights, stats)}
    prof = defaultdict(Profile)
    split = defaultdict(lambda: defaultdict(lambda: [0.0, 0]))   # uid -> opponent style -> [residual sum, n]
    career = defaultdict(lambda: {"ko_losses": 0, "kd_absorbed": 0.0, "minutes": 0.0, "td_absorbed": 0.0, "ctrl_absorbed": 0.0})
    # Cut-offs for style labels, set on 2010-2018 fighters as in the style research.
    records, train_sides = [], []
    ordered = sorted(fights.items(), key=lambda kv: (kv[1]["day"], kv[0]))
    pending_cut = fixed_cut
    for day, batch in groupby(ordered, key=lambda kv: kv[1]["day"]):
        batch = list(batch)
        snaps = {}
        for fid, fight in batch:
            a, b = fight["ids"]
            if not a or not b:
                continue
            snaps[fid] = [describe(prof[u], league) for u in (a, b)]
            if TRAIN[0] <= day <= TRAIN[1]:
                train_sides.extend(s for s in snaps[fid] if s["fights"] >= 1)
            item = forecasts.get(fid)
            if item is None or fid not in adjusted or item["y"] is None or day < TRAIN[0]:
                continue
            flip = item["fighter_ids"][0] != a
            ids = item["fighter_ids"]
            sides = snaps[fid][::-1] if flip else snaps[fid]
            records.append({"fid": fid, "day": day, "y": item["y"], "p": adjusted[fid], "ids": ids, "sides": sides,
                            "eligible": min(item["prior_decisive_bouts"]) >= 1,
                            "split": [{k: tuple(v) for k, v in split[u].items()} for u in ids],
                            "career": [dict(career[u]) for u in ids],
                            "stance": [profiles.get(u, {}).get("stance") for u in ids],
                            "reach": [profiles.get(u, {}).get("reach_inches") for u in ids],
                            "small_cage": small_cage(events.get(fid, {}), day)})
        # After the date: update every running total with this date's fights.
        for fid, fight in batch:
            a, b = fight["ids"]
            if not a or not b:
                continue
            rows = stats.get(fid, {})
            item = forecasts.get(fid)
            if item is not None and fid in adjusted and item["y"] is not None and pending_cut is not None:
                p_first = adjusted[fid]
                for k, uid in enumerate(item["fighter_ids"]):
                    won = item["y"] if k == 0 else 1 - item["y"]
                    expected = p_first if k == 0 else 1 - p_first
                    opp_side = snaps[fid][1] if uid == a else snaps[fid][0]
                    cell = split[uid][label(opp_side, pending_cut)]
                    cell[0] += won - expected
                    cell[1] += 1
            for k, uid in enumerate((a, b)):
                c = career[uid]
                if fight["loser"] == k and fight["ko"]:
                    c["ko_losses"] += 1
                own, opp = rows.get(uid), rows.get(b if uid == a else a)
                if own and opp:
                    c["minutes"] += (own.get("fight_duration_seconds") or 0) / 60
                    c["kd_absorbed"] += opp.get("knockdowns") or 0
                    c["td_absorbed"] += opp.get("takedowns_landed") or 0
                    if opp.get("control_seconds") is not None:
                        c["ctrl_absorbed"] += opp["control_seconds"] / 60
            if a in rows and b in rows:
                add(prof[a], rows[a], rows[b])
                add(prof[b], rows[b], rows[a])
    cut = {"grappler": percentile([s["td15"] for s in train_sides], .70),
           "striker_td": percentile([s["td15"] for s in train_sides], .40),
           "striker_dist": percentile([s["dist"] for s in train_sides], .50)}
    return records, cut, league


def stay_down(c, league_minutes_per_td):
    return (c["ctrl_absorbed"] + league_minutes_per_td * 4) / (c["td_absorbed"] + 4)


def features(r, spec, cut, k_split, league_mpt):
    a, b = r["sides"]
    x = [R.logit(r["p"])]
    if "split" in spec:
        def edge(i):
            opp_style = label(r["sides"][1 - i], cut)
            total, n = r["split"][i].get(opp_style, (0.0, 0))
            return total / (n + k_split)
        x.append(edge(0) - edge(1))
    if "staydown" in spec:
        ca, cb = r["career"]
        x.append(b["td15"] * stay_down(ca, league_mpt) - a["td15"] * stay_down(cb, league_mpt))
        x[-1] = -x[-1]                       # positive = good for A
    if "ko_losses" in spec:
        x.append(r["career"][0]["ko_losses"] - r["career"][1]["ko_losses"])
    if "kd_absorbed" in spec:
        x.append(r["career"][0]["kd_absorbed"] - r["career"][1]["kd_absorbed"])
    if "minutes" in spec:
        x.append((r["career"][0]["minutes"] - r["career"][1]["minutes"]) / 60)
    if "stance" in spec:
        sa, sb = r["stance"]
        x.append(float(sa == "Southpaw" and sb == "Orthodox") - float(sb == "Southpaw" and sa == "Orthodox"))
    if "reach" in spec:
        ra, rb = r["reach"]
        x.append((ra - rb) if ra is not None and rb is not None else 0.0)
    if "small_cage" in spec:
        la, lb = label(a, cut), label(b, cut)
        g = float(la == "grappler" and lb == "striker") - float(lb == "grappler" and la == "striker")
        x.append(g * (1.0 if r["small_cage"] else 0.0))
        x.append(g * (0.0 if r["small_cage"] else 1.0))
    return x


def score(rows, probs):
    n = len(rows)
    return {"bouts": n, "log_loss": round(sum(R.loss(p if r["y"] else 1 - p) for r, p in zip(rows, probs)) / n, 5),
            "accuracy": round(sum((p > .5) == bool(r["y"]) for r, p in zip(rows, probs)) / n, 4)}


def bootstrap(rows, base, cand, draws=500, seed=13):
    by_day = defaultdict(list)
    for r, p0, p1 in zip(rows, base, cand):
        by_day[r["day"]].append(R.loss(p1 if r["y"] else 1 - p1) - R.loss(p0 if r["y"] else 1 - p0))
    days, rng, means = list(by_day), random.Random(seed), []
    for _ in range(draws):
        picked = [d for day in (rng.choice(days) for _ in days) for d in by_day[day]]
        means.append(sum(picked) / len(picked))
    means.sort()
    return [round(means[int(.025 * draws)], 4), round(means[int(.975 * draws)], 4)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--rating-snapshot", type=Path, required=True)
    parser.add_argument("--forecast-adjustment", type=Path, required=True)
    parser.add_argument("--event-names", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit(f"{args.output} exists; write a new version instead.")
    profiles, fights, stats, events = load(args.database, args.event_names / "event_names.json" if args.event_names else None)
    forecasts = {json.loads(l)["fight_id"]: json.loads(l) for l in open(args.rating_snapshot / "forecasts.jsonl")}
    adjusted = {json.loads(l)["fight_id"]: json.loads(l)["forecast"] for l in open(args.forecast_adjustment / "forecasts.jsonl")}
    _, cut, _ = build(profiles, fights, stats, events, forecasts, adjusted)          # pass 1: style cut-offs from 2010-2018
    records, cut2, league = build(profiles, fights, stats, events, forecasts, adjusted, cut)   # pass 2: label with them throughout
    assert cut2 == cut
    totals = defaultdict(float)
    for r in records:
        if r["day"] <= TRAIN[1]:
            for c in r["career"]:
                totals["ctrl"] += c["ctrl_absorbed"]; totals["td"] += c["td_absorbed"]
    league_mpt = totals["ctrl"] / max(totals["td"], 1)
    train = [r for r in records if TRAIN[0] <= r["day"] <= TRAIN[1] and r["eligible"]]
    test = [r for r in records if r["day"] >= TEST_FROM and r["eligible"]]

    # Shrinkage for the style splits, chosen on the training years only.
    def fit_and_predict(spec, rows, k):
        w = R.fit(R.symmetric([(features(r, spec, cut, k, league_mpt), r["y"]) for r in train]))
        return w, [R.sigmoid(sum(a * b for a, b in zip(w, features(r, spec, cut, k, league_mpt)))) for r in rows]
    k_split = min((2, 4, 8, 16), key=lambda k: score(train, fit_and_predict({"split": 1}, train, k)[1])["log_loss"])

    specs = {"forecast 5.2": {}, "1. style splits": {"split": 1}, "2. staying down": {"staydown": 1},
             "3a. KO/TKO losses": {"ko_losses": 1}, "3b. knockdowns absorbed": {"kd_absorbed": 1},
             "3c. UFC minutes (mileage)": {"minutes": 1}, "4. stance": {"stance": 1}, "5. reach": {"reach": 1},
             "6. small cage x grappler": {"small_cage": 1}}
    report = {"train": TRAIN, "test_from": TEST_FROM, "split_shrinkage": k_split,
              "small_cage_fights_since_2019": sum(r["small_cage"] for r in test), "models": {}}
    _, base = fit_and_predict({}, test, k_split)
    halves = {name: [i for i, r in enumerate(test) if lo <= r["day"] <= hi] for name, lo, hi in HALVES}
    for name, spec in specs.items():
        w, probs = fit_and_predict(spec, test, k_split)
        entry = {"weights": [round(v, 4) for v in w], **score(test, probs)}
        if spec:
            entry["change_95pct"] = bootstrap(test, base, probs)
            entry["change_by_half"] = {h: round(score([test[i] for i in idx], [probs[i] for i in idx])["log_loss"]
                                                - score([test[i] for i in idx], [base[i] for i in idx])["log_loss"], 4)
                                       for h, idx in halves.items()}
            entry["passes"] = entry["change_95pct"][1] < 0 and all(v < 0 for v in entry["change_by_half"].values())
        report["models"][name] = entry
    args.output.mkdir(parents=True)
    (args.output / "report.json").write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
