"""Do style matchups (wrestler vs striker and so on) predict UFC results beyond the UPSET forecast?

Walk-forward research on top of forecast revision 5.2 (age + debut starting point). For every fight,
each fighter's style profile is built only from their UFC fights before that date:

* takedown pressure: takedown attempts per 15 minutes
* takedown defense: share of opponents' takedown attempts they stopped
* control: share of fight time spent in control (where recorded)
* striking at range: share of landed significant strikes thrown at distance
* volume and power: significant strikes landed per minute, knockdowns per 15 minutes

Small samples are pulled toward the league average (empirical-Bayes style), so two fights don't
define a style. Style labels use cut-offs set on 2010-2018 fighters:

* grappler: takedown pressure in the top 30%
* striker: takedown pressure in the bottom 40% and striking at range above the median
* mixed: everyone else

Candidates added to the forecast (fit 2010-2018, scored once on 2019 onward):

* takedown matchup: A's takedown pressure x B's takedown-defense gaps, minus the same for B
* grappler vs striker: +1 when A is a grappler facing a striker, -1 the other way round
* power vs chin: A's knockdowns per 15 x B's knockdowns absorbed per 15, minus the same for B
"""

import argparse
import json
import math
import random
import sqlite3
from collections import defaultdict
from contextlib import closing
from itertools import groupby
from pathlib import Path

from upset.ratings import v5_adjustments_research as R

TRAIN = ("2010-01-01", "2018-12-31")
TEST_FROM = "2019-01-01"
PRIOR_MINUTES = 30.0     # weight of the league average, in fight minutes
PRIOR_TD_ATTEMPTS = 8.0  # weight of the league takedown-defense average, in attempts


def load(database):
    with closing(sqlite3.connect(database)) as db:
        fights = {}
        for fid, day, payload in db.execute("SELECT id,event_date,payload FROM fights"):
            p = json.loads(payload)
            fights[fid] = {"day": day, "ids": [p.get("upset_fighter_1_id"), p.get("upset_fighter_2_id")]}
        stats = defaultdict(dict)
        for fid, uid, payload in db.execute("SELECT fight_id,fighter_id,payload FROM stats"):
            stats[fid][uid] = json.loads(payload)
    return fights, stats


class Profile:
    __slots__ = ("minutes", "td_att", "sub_att", "ctrl", "ctrl_minutes", "sig", "dist", "kd",
                 "opp_td_att", "opp_td_landed", "kd_absorbed", "fights")

    def __init__(self):
        for name in self.__slots__:
            setattr(self, name, 0.0)


def add(profile, own, opp):
    minutes = (own.get("fight_duration_seconds") or 0) / 60
    if minutes <= 0:
        return
    profile.fights += 1
    profile.minutes += minutes
    profile.td_att += own.get("takedowns_attempted") or 0
    profile.sub_att += own.get("submission_attempts") or 0
    if own.get("control_seconds") is not None:
        profile.ctrl += own["control_seconds"] / 60
        profile.ctrl_minutes += minutes
    profile.sig += own.get("sig_strikes_landed") or 0
    profile.dist += own.get("distance_landed") or 0
    profile.kd += own.get("knockdowns") or 0
    profile.opp_td_att += opp.get("takedowns_attempted") or 0
    profile.opp_td_landed += opp.get("takedowns_landed") or 0
    profile.kd_absorbed += opp.get("knockdowns") or 0


def describe(profile, league):
    """Shrunk rates for one fighter at one cutoff."""
    m = profile.minutes
    shrink = lambda total, rate: (total + rate * PRIOR_MINUTES) / (m + PRIOR_MINUTES)
    td15 = 15 * shrink(profile.td_att, league["td_per_min"])
    tdd = 1 - (profile.opp_td_landed + league["td_success"] * PRIOR_TD_ATTEMPTS) / (profile.opp_td_att + PRIOR_TD_ATTEMPTS)
    ctrl = (profile.ctrl + league["ctrl_share"] * PRIOR_MINUTES) / (profile.ctrl_minutes + PRIOR_MINUTES)
    dist = (profile.dist + league["dist_share"] * 40) / (profile.sig + 40)
    kd15 = 15 * shrink(profile.kd, league["kd_per_min"])
    kda15 = 15 * shrink(profile.kd_absorbed, league["kd_per_min"])
    slpm = shrink(profile.sig, league["sig_per_min"])
    return {"td15": td15, "tdd": tdd, "ctrl": ctrl, "dist": dist, "kd15": kd15, "kda15": kda15,
            "slpm": slpm, "fights": int(profile.fights)}


def league_averages(fights, stats):
    totals = defaultdict(float)
    for fid, fight in fights.items():
        if not (TRAIN[0] <= fight["day"] <= TRAIN[1]):
            continue
        for uid in fight["ids"]:
            row = stats.get(fid, {}).get(uid)
            if not row or not row.get("fight_duration_seconds"):
                continue
            minutes = row["fight_duration_seconds"] / 60
            totals["minutes"] += minutes
            totals["td_att"] += row.get("takedowns_attempted") or 0
            totals["td_landed"] += row.get("takedowns_landed") or 0
            totals["kd"] += row.get("knockdowns") or 0
            totals["sig"] += row.get("sig_strikes_landed") or 0
            totals["dist"] += row.get("distance_landed") or 0
            if row.get("control_seconds") is not None:
                totals["ctrl"] += row["control_seconds"] / 60
                totals["ctrl_minutes"] += minutes
    return {"td_per_min": totals["td_att"] / totals["minutes"], "td_success": totals["td_landed"] / totals["td_att"],
            "ctrl_share": totals["ctrl"] / totals["ctrl_minutes"], "dist_share": totals["dist"] / totals["sig"],
            "kd_per_min": totals["kd"] / totals["minutes"], "sig_per_min": totals["sig"] / totals["minutes"]}


def percentile(values, q):
    values = sorted(values)
    return values[min(len(values) - 1, int(q * len(values)))]


def build_records(fights, stats, adjusted, forecasts, league):
    profiles = defaultdict(Profile)
    records = []
    ordered = sorted(fights.items(), key=lambda kv: (kv[1]["day"], kv[0]))
    for day, batch in groupby(ordered, key=lambda kv: kv[1]["day"]):
        batch = list(batch)
        for fid, fight in batch:
            item = forecasts.get(fid)
            if item is None or fid not in adjusted or day < TRAIN[0]:
                continue
            ids = item["fighter_ids"]
            sides = [describe(profiles[uid], league) for uid in ids]
            records.append({"fight_id": fid, "day": day, "y": item["y"], "p": adjusted[fid],
                            "eligible": min(item["prior_decisive_bouts"]) >= 1, "sides": sides, "ids": ids})
        for fid, fight in batch:
            rows = stats.get(fid, {})
            a, b = fight["ids"]
            if a in rows and b in rows:
                add(profiles[a], rows[a], rows[b])
                add(profiles[b], rows[b], rows[a])
    return records


def label(side, cut):
    if side["fights"] == 0:
        return "debut"
    if side["td15"] >= cut["grappler"]:
        return "grappler"
    if side["td15"] <= cut["striker_td"] and side["dist"] >= cut["striker_dist"]:
        return "striker"
    return "mixed"


def features(rec, spec, cut):
    a, b = rec["sides"]
    x = [R.logit(rec["p"])]
    if "takedown" in spec:
        x.append(a["td15"] * (1 - b["tdd"]) - b["td15"] * (1 - a["tdd"]))
    if "grappler_vs_striker" in spec:
        la, lb = label(a, cut), label(b, cut)
        x.append(float(la == "grappler" and lb == "striker") - float(lb == "grappler" and la == "striker"))
    if "power" in spec:
        x.append(a["kd15"] * b["kda15"] - b["kd15"] * a["kda15"])
    return x


def evaluate(records, spec, cut):
    train = [(features(r, spec, cut), r["y"]) for r in records
             if TRAIN[0] <= r["day"] <= TRAIN[1] and r["eligible"] and r["y"] is not None]
    w = R.fit(R.symmetric(train))
    test = [r for r in records if r["day"] >= TEST_FROM and r["eligible"] and r["y"] is not None]
    probs = [R.sigmoid(sum(a * b for a, b in zip(w, features(r, spec, cut)))) for r in test]
    return w, test, probs


def summary(test, probs):
    n = len(test)
    return {"bouts": n, "log_loss": round(sum(R.loss(p if r["y"] else 1 - p) for r, p in zip(test, probs)) / n, 5),
            "accuracy": round(sum((p > .5) == bool(r["y"]) for r, p in zip(test, probs)) / n, 4)}


def bootstrap(test, base, cand, draws=400, seed=11):
    by_day = defaultdict(list)
    for r, p0, p1 in zip(test, base, cand):
        by_day[r["day"]].append(R.loss(p1 if r["y"] else 1 - p1) - R.loss(p0 if r["y"] else 1 - p0))
    days, rng, means = list(by_day), random.Random(seed), []
    for _ in range(draws):
        picked = [d for day in (rng.choice(days) for _ in days) for d in by_day[day]]
        means.append(sum(picked) / len(picked))
    means.sort()
    return [round(means[int(.025 * draws)], 4), round(means[int(.975 * draws)], 4)]


def matchup_history(records, cut):
    """How each style pairing went against what the forecast expected, 2010 onward."""
    table = defaultdict(lambda: {"bouts": 0, "won": 0.0, "expected": 0.0})
    for r in records:
        if r["y"] is None or not r["eligible"]:
            continue
        labels = [label(s, cut) for s in r["sides"]]
        if "debut" in labels or labels[0] == labels[1]:
            continue
        order = ("grappler", "mixed", "striker")
        i = 0 if order.index(labels[0]) < order.index(labels[1]) else 1
        key = labels[i] + " vs " + labels[1 - i]
        p = r["p"] if i == 0 else 1 - r["p"]
        y = r["y"] if i == 0 else 1 - r["y"]
        cell = table[key]
        cell["bouts"] += 1
        cell["won"] += y
        cell["expected"] += p
    out = {}
    for key, cell in table.items():
        n = cell["bouts"]
        won, expected = cell["won"] / n, cell["expected"] / n
        se = math.sqrt(max(expected * (1 - expected), 1e-9) / n)
        out[key] = {"bouts": n, "first_style_won": round(won, 4), "forecast_expected": round(expected, 4),
                    "difference": round(won - expected, 4), "difference_95pct": [round(won - expected - 1.96 * se, 4),
                                                                               round(won - expected + 1.96 * se, 4)]}
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--rating-snapshot", type=Path, required=True)
    parser.add_argument("--forecast-adjustment", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit(f"{args.output} exists; write a new version instead.")
    fights, stats = load(args.database)
    forecasts = {}
    for line in open(args.rating_snapshot / "forecasts.jsonl"):
        item = json.loads(line)
        forecasts[item["fight_id"]] = item
    adjusted = {}
    for line in open(args.forecast_adjustment / "forecasts.jsonl"):
        row = json.loads(line)
        adjusted[row["fight_id"]] = row["forecast"]
    league = league_averages(fights, stats)
    records = build_records(fights, stats, adjusted, forecasts, league)
    train_sides = [s for r in records if TRAIN[0] <= r["day"] <= TRAIN[1] for s in r["sides"] if s["fights"] >= 1]
    cut = {"grappler": percentile([s["td15"] for s in train_sides], .70),
           "striker_td": percentile([s["td15"] for s in train_sides], .40),
           "striker_dist": percentile([s["dist"] for s in train_sides], .50)}

    specs = {"forecast 5.2 (recalibrated)": {}, "+ takedown matchup": {"takedown": 1},
             "+ grappler vs striker": {"grappler_vs_striker": 1}, "+ power vs chin": {"power": 1},
             "+ all three": {"takedown": 1, "grappler_vs_striker": 1, "power": 1}}
    report = {"train": TRAIN, "test_from": TEST_FROM, "league": {k: round(v, 5) for k, v in league.items()},
              "style_cutoffs": {k: round(v, 4) for k, v in cut.items()}, "models": {}}
    base = None
    for name, spec in specs.items():
        w, test, probs = evaluate(records, spec, cut)
        entry = {"weights": [round(v, 4) for v in w], **summary(test, probs)}
        if base is None:
            base = probs
        else:
            entry["change_vs_forecast_95pct"] = bootstrap(test, base, probs)
        report["models"][name] = entry
    report["matchup_history_since_2010"] = matchup_history(records, cut)
    counts = defaultdict(int)
    for r in records:
        if r["day"] >= TEST_FROM:
            for s in r["sides"]:
                counts[label(s, cut)] += 1
    report["style_counts_since_2019"] = dict(counts)
    args.output.mkdir(parents=True)
    (args.output / "report.json").write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
