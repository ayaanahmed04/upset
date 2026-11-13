"""Do round-by-round numbers improve the UPSET forecast (revision 5.2)?

Cito's archive stores every bout's stats round by round. This checks those rows against the fight
totals already in the database, then tests factors that only round data can measure. Each one is
built only from rounds fought before the bout, added to the 5.2 forecast, fit on 2010-2018 and
scored once on the 3,177-fight record set since 2019, with the same pass rule as the situational
test (95% interval below zero and better in both 2019-2022 and 2023+).

1. Rounds won: a judges-style score for each completed round (significant strikes landed,
   knockdowns, takedowns, control time). Fight results hide close rounds; this does not.
2. Late-round edge: how a fighter's strike margin per minute after round 1 compares with round 1
   (gets better as the fight goes on, or fades).
3. Output fade (cardio): significant strikes thrown per minute after round 1 against round 1,
   compared with the league's usual drop.
4. Wrestling against a striker (the analyst's Fighter A / Fighter B idea): how much a fighter's
   striking output falls in rounds where the opponent lands a takedown or holds a minute of control,
   multiplied by how often the upcoming opponent produces rounds like that.
"""

import argparse
import json
import math
import sqlite3
import unicodedata
from collections import Counter, defaultdict
from contextlib import closing
from itertools import groupby
from pathlib import Path

from upset.ratings import v5_adjustments_research as R
from upset.ratings.situational_research import HALVES, TEST_FROM, TRAIN, bootstrap, score

KAGGLE = "kaggle_ufc_1994_2026:"
CHECKED = ("sig_strikes_landed", "sig_strikes_attempted", "takedowns_landed", "knockdowns")
ROUND_RULES_FROM = "2001-01-01"   # five-minute rounds under the unified rules
PSEUDO_MINUTES = 15.0             # each rate is pulled toward the league with 15 minutes of league data
PSEUDO_ROUNDS = 6.0


def seconds(text):
    try:
        minutes, secs = str(text).split(":")
        return int(minutes) * 60 + int(secs)
    except (TypeError, ValueError):
        return None


def norm(name):
    return "".join(ch for ch in unicodedata.normalize("NFKD", name or "").lower() if ch.isalnum())


def load_fights(database):
    fights, stats = {}, defaultdict(dict)
    with closing(sqlite3.connect(database)) as db:
        for fid, day, payload in db.execute("SELECT id,event_date,payload FROM fights"):
            p = json.loads(payload)
            result = p.get("reviewed_result") or {}
            fights[fid] = {"day": day, "ids": [p.get("upset_fighter_1_id"), p.get("upset_fighter_2_id")],
                           "names": [p.get("fighter_1_name"), p.get("fighter_2_name")],
                           "round": result.get("result_round") or p.get("result_round"),
                           "time": result.get("result_time") or p.get("result_time")}
        for fid, uid, payload in db.execute("SELECT fight_id,fighter_id,payload FROM stats"):
            stats[fid][uid] = json.loads(payload)
    return fights, stats


def load_rounds(bridge, current, fights):
    """fight id -> fighter id -> round number -> row, plus counts of what was left out and why."""
    status = {json.loads(l)["cito_bout_id"]: json.loads(l)["status"] for l in open(bridge / "bout_matches.jsonl")}
    rounds = defaultdict(lambda: defaultdict(dict))
    dropped, conflicts = Counter(), set()

    def put(fid, uid, row):
        slot = rounds[fid][uid]
        n = row["round_number"]
        if n in slot and any(slot[n].get(k) != row.get(k) for k in CHECKED):
            conflicts.add(fid)
        slot[n] = row

    for line in open(bridge / "round_stats_staged.jsonl"):
        r = json.loads(line)
        if status.get(r["source_bout_id"]) != "totals_verified_proposal":
            dropped["bout totals not verified"] += 1
            continue
        fid = KAGGLE + (r.get("candidate_historical_bout_id") or "")
        fight = fights.get(fid)
        if fight is None:
            dropped["fight not in database"] += 1
            continue
        uid = r.get("reviewed_upset_fighter_id") or r.get("proposed_upset_fighter_id")
        if uid not in fight["ids"]:
            hits = [i for i, name in zip(fight["ids"], fight["names"]) if norm(name) == norm(r.get("fighter_name"))]
            uid = hits[0] if len(hits) == 1 else None
        if uid is None:
            dropped["fighter not matched"] += 1
            continue
        put(fid, uid, r)
    for line in open(current / "rounds_staged.jsonl"):
        r = json.loads(line)
        fid = "cito:" + r["source_bout_id"]
        fight = fights.get(fid)
        if fight is None or r.get("upset_fighter_id") not in fight["ids"]:
            dropped["recent row not matched"] += 1
            continue
        put(fid, r["upset_fighter_id"], r)
    return rounds, dropped, conflicts


def audit(rounds, stats, fights, conflicts):
    """Keep a fight only if both corners' rounds add up to the database totals and the rounds run 1..N."""
    good, why = {}, Counter()
    for fid, by in rounds.items():
        fight = fights[fid]
        if fid in conflicts:
            why["duplicate rows disagree"] += 1
            continue
        if set(by) != set(fight["ids"]) or len(by) != 2:
            why["missing a corner"] += 1
            continue
        numbers = [sorted(by[u]) for u in fight["ids"]]
        if numbers[0] != numbers[1] or numbers[0] != list(range(1, len(numbers[0]) + 1)):
            why["round numbers do not line up"] += 1
            continue
        if fight["round"] and len(numbers[0]) != int(fight["round"]):
            why["round count differs from result"] += 1
            continue
        mismatch = False
        for uid in fight["ids"]:
            total = stats.get(fid, {}).get(uid)
            if total is None:
                mismatch = True
                break
            for key in CHECKED:
                if total.get(key) is not None and sum(row.get(key) or 0 for row in by[uid].values()) != total[key]:
                    mismatch = True
        if mismatch:
            why["rounds do not add up to fight totals"] += 1
            continue
        good[fid] = by
        why["kept"] += 1
    return good, why


def round_lines(fight, by):
    """Per round: minutes and both corners' numbers, ordered as fight['ids']."""
    last, clock = fight["round"], seconds(fight["time"])
    if not last or clock is None:
        return []
    out = []
    for n in range(1, int(last) + 1):
        minutes = (300 if n < int(last) else clock) / 60
        rows = [by[u][n] for u in fight["ids"]]
        out.append({"n": n, "minutes": minutes, "full": n < int(last) or clock >= 300, "rows": rows})
    return out


def judge(own, opp):
    """Judges-style round score (positive = this corner won the round)."""
    g = lambda r, k: r.get(k) or 0
    return (g(own, "sig_strikes_landed") - g(opp, "sig_strikes_landed")
            + 4 * (g(own, "knockdowns") - g(opp, "knockdowns"))
            + 2 * (g(own, "takedowns_landed") - g(opp, "takedowns_landed"))
            + (g(own, "control_seconds") - g(opp, "control_seconds")) / 30)


def wrestled(opp):
    return (opp.get("takedowns_landed") or 0) >= 1 or (opp.get("control_seconds") or 0) >= 60


def new_history():
    return Counter()


def update(h, line, side):
    own, opp = line["rows"][side], line["rows"][1 - side]
    m = line["minutes"]
    if line["full"]:
        s = judge(own, opp)
        h["rounds"] += 1
        h["won"] += 1.0 if s > 0 else 0.5 if s == 0 else 0.0
    part = "r1" if line["n"] == 1 else "late"
    h[part + "_min"] += m
    h[part + "_diff"] += (own.get("sig_strikes_landed") or 0) - (opp.get("sig_strikes_landed") or 0)
    h[part + "_att"] += own.get("sig_strikes_attempted") or 0
    state = "wr" if wrestled(opp) else "clean"
    h[state + "_min"] += m
    h[state + "_att"] += own.get("sig_strikes_attempted") or 0
    h["all_rounds"] += 1
    h["wrestling_rounds"] += 1.0 if wrestled(own) else 0.0


def league(lines):
    """League rates from 2010-2018 rounds, used as the pull-toward values."""
    h = Counter()
    for line in lines:
        for side in (0, 1):
            update(h, line, side)
    return {"r1_pace": h["r1_att"] / h["r1_min"], "late_pace": h["late_att"] / h["late_min"],
            "wr_pace": h["wr_att"] / h["wr_min"], "clean_pace": h["clean_att"] / h["clean_min"],
            "wrestling_rate": h["wrestling_rounds"] / h["all_rounds"],
            "rounds": h["all_rounds"] // 2}


def describe(h, L, k_rounds):
    M = PSEUDO_MINUTES
    pace = lambda part, prior: (h[part + "_att"] + prior * M) / (h[part + "_min"] + M)
    return {"rounds_won": (h["won"] + 0.5 * k_rounds) / (h["rounds"] + k_rounds) - 0.5,
            "late_edge": h["late_diff"] / (h["late_min"] + M) - h["r1_diff"] / (h["r1_min"] + M),
            "fade": math.log(pace("late", L["late_pace"]) / pace("r1", L["r1_pace"])) - math.log(L["late_pace"] / L["r1_pace"]),
            "suppressed": math.log(pace("wr", L["wr_pace"]) / pace("clean", L["clean_pace"])) - math.log(L["wr_pace"] / L["clean_pace"]),
            "wrestles": (h["wrestling_rounds"] + L["wrestling_rate"] * PSEUDO_ROUNDS) / (h["all_rounds"] + PSEUDO_ROUNDS),
            "rounds_seen": h["all_rounds"]}


def build(fights, good, forecasts, adjusted):
    lines = {fid: round_lines(fights[fid], by) for fid, by in good.items() if fights[fid]["day"] >= ROUND_RULES_FROM}
    lines = {fid: v for fid, v in lines.items() if v}
    L = league([ln for fid, v in lines.items() if TRAIN[0] <= fights[fid]["day"] <= TRAIN[1] for ln in v])
    history = defaultdict(new_history)
    records = []
    ordered = sorted(fights.items(), key=lambda kv: (kv[1]["day"], kv[0]))
    for day, batch in groupby(ordered, key=lambda kv: kv[1]["day"]):
        batch = list(batch)
        for fid, fight in batch:
            item = forecasts.get(fid)
            if item is None or fid not in adjusted or item["y"] is None or day < TRAIN[0]:
                continue
            ids = item["fighter_ids"]
            records.append({"fid": fid, "day": day, "y": item["y"], "p": adjusted[fid], "ids": ids,
                            "eligible": min(item["prior_decisive_bouts"]) >= 1,
                            "h": [Counter(history[u]) for u in ids]})
        for fid, fight in batch:
            for line in lines.get(fid, []):
                for side, uid in enumerate(fight["ids"]):
                    update(history[uid], line, side)
    return records, L, lines


def features(r, spec, L, k_rounds):
    a, b = (describe(h, L, k_rounds) for h in r["h"])
    x = [R.logit(r["p"])]
    if "rounds_won" in spec:
        x.append(a["rounds_won"] - b["rounds_won"])
    if "late_edge" in spec:
        x.append(a["late_edge"] - b["late_edge"])
    if "fade" in spec:
        x.append(a["fade"] - b["fade"])
    if "wrestling" in spec:
        x.append(b["wrestles"] * a["suppressed"] - a["wrestles"] * b["suppressed"])
    return x


def decision_check(fights, lines, winners):
    """How often the round score agrees with the official decision winner (a sanity check on the scoring)."""
    agree = total = 0
    for fid, v in lines.items():
        w = winners.get(fid)
        if w is None or len(v) < 3 or not all(ln["full"] for ln in v):
            continue
        tally = sum((judge(ln["rows"][0], ln["rows"][1]) > 0) - (judge(ln["rows"][1], ln["rows"][0]) > 0) for ln in v)
        if tally == 0:
            continue
        total += 1
        agree += (tally > 0) == (w == 0)
    return {"decisions": total, "round_score_agrees": round(agree / max(total, 1), 4)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--bridge", type=Path, required=True)
    parser.add_argument("--current", type=Path, required=True)
    parser.add_argument("--rating-snapshot", type=Path, required=True)
    parser.add_argument("--forecast-adjustment", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit(f"{args.output} exists; write a new version instead.")
    fights, stats = load_fights(args.database)
    rounds, dropped, conflicts = load_rounds(args.bridge, args.current, fights)
    good, why = audit(rounds, stats, fights, conflicts)
    forecasts = {json.loads(l)["fight_id"]: json.loads(l) for l in open(args.rating_snapshot / "forecasts.jsonl")}
    adjusted = {json.loads(l)["fight_id"]: json.loads(l)["forecast"] for l in open(args.forecast_adjustment / "forecasts.jsonl")}
    records, L, lines = build(fights, good, forecasts, adjusted)

    winners = {}
    with closing(sqlite3.connect(args.database)) as db:
        for fid, payload in db.execute("SELECT id,payload FROM fights"):
            p = json.loads(payload)
            res = p.get("reviewed_result") or p
            if (res.get("result_method") or "").startswith("Decision"):
                names = [p["fighter_1_name"], p["fighter_2_name"]]
                if res.get("winner_name") in names:
                    winners[fid] = names.index(res["winner_name"])

    train = [r for r in records if TRAIN[0] <= r["day"] <= TRAIN[1] and r["eligible"]]
    test = [r for r in records if r["day"] >= TEST_FROM and r["eligible"]]

    def fit_and_predict(spec, rows, k):
        w = R.fit(R.symmetric([(features(r, spec, L, k), r["y"]) for r in train]))
        return w, [R.sigmoid(sum(a * b for a, b in zip(w, features(r, spec, L, k)))) for r in rows]
    k_rounds = min((3, 6, 12, 24), key=lambda k: score(train, fit_and_predict({"rounds_won": 1}, train, k)[1])["log_loss"])

    with_history = sum(1 for r in test if min(h["all_rounds"] for h in r["h"]) >= 3)
    report = {"train": TRAIN, "test_from": TEST_FROM,
              "rounds": {"bouts_with_round_rows": len(rounds), "rows_left_out": dict(dropped), "audit": dict(why),
                         "bouts_used_from_2001": len(lines), "league_2010_2018": {k: round(v, 3) for k, v in L.items()},
                         "judging_check": decision_check(fights, lines, winners)},
              "test_fights_both_with_3plus_prior_rounds": with_history, "rounds_won_shrinkage": k_rounds, "models": {}}
    specs = {"forecast 5.2": {}, "1. rounds won": {"rounds_won": 1}, "2. late-round edge": {"late_edge": 1},
             "3. output fade (cardio)": {"fade": 1}, "4. wrestling vs striker (A/B)": {"wrestling": 1},
             "all four": {"rounds_won": 1, "late_edge": 1, "fade": 1, "wrestling": 1}}
    _, base = fit_and_predict({}, test, k_rounds)
    halves = {name: [i for i, r in enumerate(test) if lo <= r["day"] <= hi] for name, lo, hi in HALVES}
    for name, spec in specs.items():
        w, probs = fit_and_predict(spec, test, k_rounds)
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
