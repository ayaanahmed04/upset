"""Learn how judges score a round from the stats, instead of hand-picked weights.

What we know about judging:
  * the official winner of every decision (who won more rounds on most cards), and
  * for recent cards, each judge's total (29-28 means that judge gave two rounds to one fighter).
Neither says which rounds, so the round winners are treated as hidden: the model is a logistic
score on the difference in round stats, fitted by EM (work out how likely each round was won given
the label, refit, repeat). 10-8 cards and point deductions are left out because the total no longer
gives a round count.

Checks are out of sample, by fight (5 folds): how often the model's rounds-won count equals a real
judge's count, and how often its round count picks the official decision winner. The hand-picked
score in round_research.judge is the baseline, and two real judges at the same fight are the ceiling.

    python -m upset.ratings.round_scoring --database ... --bridge ... --current ... --archive data/raw/cito_archive/cards --output DIR
"""

import argparse
import glob
import hashlib
import json
import math
import random
import sqlite3
from collections import Counter
from contextlib import closing
from itertools import combinations, product
from pathlib import Path

import numpy as np

from upset.ratings import round_research as RR

VERSION = "round_scoring_v1"
FEATURES = ["head", "body", "leg", "other_strikes", "knockdowns", "takedowns", "control_minutes",
            "submission_attempts", "reversals", "missed", "strike_ratio",
            "ground_strikes", "head_sqrt", "control_sqrt", "any_knockdown", "any_takedown"]
RIDGE = 1.0
FOLDS = 5


def vector(row):
    g = lambda k: row.get(k) or 0
    return [g("head_landed"), g("body_landed"), g("leg_landed"),
            max(0, g("total_strikes_landed") - g("sig_strikes_landed")), g("knockdowns"), g("takedowns_landed"),
            g("control_seconds") / 60, g("submission_attempts"), g("reversals"),
            max(0, g("sig_strikes_attempted") - g("sig_strikes_landed")), 0.0]


def difference(own, opp):
    g = lambda r, k: r.get(k) or 0
    x = list(np.array(vector(own)) - np.array(vector(opp)))
    x[-1] = math.log((g(own, "sig_strikes_landed") + 3) / (g(opp, "sig_strikes_landed") + 3))
    # Judges react to "more" less and less as the numbers grow, and to whether something happened at all.
    x += [g(own, "ground_landed") - g(opp, "ground_landed"),
          math.sqrt(g(own, "head_landed")) - math.sqrt(g(opp, "head_landed")),
          (math.sqrt(g(own, "control_seconds")) - math.sqrt(g(opp, "control_seconds"))) / 8,
          float(g(own, "knockdowns") > 0) - float(g(opp, "knockdowns") > 0),
          float(g(own, "takedowns_landed") > 0) - float(g(opp, "takedowns_landed") > 0)]
    return np.array(x)


def probability(own, opp, weights):
    """Chance a judge gives this round to `own`."""
    return 1 / (1 + math.exp(-float(np.dot(weights, difference(own, opp)))))


def posterior(p, label):
    """P(each round won by A | label). label = ('count', k): A won exactly k rounds; ('win', s): A (s=1) or B (s=0) won more."""
    n = len(p)
    total, won = 0.0, np.zeros(n)
    for pattern in product((0, 1), repeat=n):
        k = sum(pattern)
        if label[0] == "count":
            ok = k == label[1]
        else:
            ok = (2 * k > n) if label[1] else (2 * k < n)
        if not ok:
            continue
        pr = math.prod(q if bit else 1 - q for q, bit in zip(p, pattern))
        total += pr
        won += pr * np.array(pattern)
    return (won / total if total > 0 else np.array(p)), total


def fit(examples, ridge=RIDGE, rounds=25):
    """examples: list of (X [rounds x features], label). Returns weights."""
    w = np.zeros(len(FEATURES))
    w[0] = w[1] = w[2] = 0.1
    for _ in range(rounds):
        xs, ys = [], []
        for X, label in examples:
            p = 1 / (1 + np.exp(-X @ w))
            q, _ = posterior(p, label)
            xs.append(X)
            ys.append(q)
        X, y = np.vstack(xs), np.concatenate(ys)
        for _ in range(8):                                   # weighted logistic regression on soft labels (Newton steps)
            p = 1 / (1 + np.exp(-X @ w))
            grad = X.T @ (p - y) + ridge * w
            hess = (X * (p * (1 - p))[:, None]).T @ X + ridge * np.eye(len(w))
            w = w - np.linalg.solve(hess, grad)
    return w


def gather(database, bridge, current, archive):
    fights, stats = RR.load_fights(database)
    rounds, _, conflicts = RR.load_rounds(bridge, current, fights)
    good, _ = RR.audit(rounds, stats, fights, conflicts)
    winners = {}
    with closing(sqlite3.connect(database)) as db:
        for fid, payload in db.execute("SELECT id,payload FROM fights"):
            p = json.loads(payload)
            res = p.get("reviewed_result") or p
            names = [p["fighter_1_name"], p["fighter_2_name"]]
            if (res.get("result_method") or "").startswith("Decision") and res.get("winner_name") in names:
                winners[fid] = names.index(res["winner_name"])
    # Cito bout id -> (fight id, slug -> fighter id), for reading the judges' totals.
    link = {}
    for line in open(bridge / "round_stats_staged.jsonl"):
        r = json.loads(line)
        fid = RR.KAGGLE + (r.get("candidate_historical_bout_id") or "")
        if fid not in good:
            continue
        uid = r.get("reviewed_upset_fighter_id") or r.get("proposed_upset_fighter_id")
        if uid not in fights[fid]["ids"]:
            hits = [i for i, n in zip(fights[fid]["ids"], fights[fid]["names"]) if RR.norm(n) == RR.norm(r.get("fighter_name"))]
            uid = hits[0] if len(hits) == 1 else None
        if uid:
            link.setdefault(r["source_bout_id"], (fid, {}))[1][r["source_fighter_slug"]] = uid
    cards = {}
    for path in glob.glob(str(Path(archive) / "*" / "bouts.json")):
        for bout in json.load(open(path))["response"]["data"]:
            if not bout.get("scorecards") or bout["id"] not in link:
                continue
            fid, slugs = link[bout["id"]]
            for card in bout["scorecards"]:
                score = {slugs.get(x["fighterSlug"]): x["score"] for x in card["scores"]}
                if set(score) == set(fights[fid]["ids"]):
                    cards.setdefault(fid, []).append([score[u] for u in fights[fid]["ids"]])
    data = []
    for fid, by in good.items():
        fight = fights[fid]
        if fight["day"] < RR.ROUND_RULES_FROM or fid not in winners:
            continue
        lines = RR.round_lines(fight, by)
        if len(lines) < 3 or not all(line["full"] for line in lines):
            continue
        n = len(lines)
        counts = [a - 9 * n for a, b in cards.get(fid, []) if a + b == 19 * n and 0 <= a - 9 * n <= n]
        data.append({"fid": fid, "day": fight["day"], "X": np.array([difference(l["rows"][0], l["rows"][1]) for l in lines]),
                     "hand": [RR.judge(l["rows"][0], l["rows"][1]) for l in lines], "winner": winners[fid],
                     "counts": counts, "cards_dropped": len(cards.get(fid, [])) - len(counts)})
    return data


def examples_for(items):
    out = []
    for d in items:
        if d["counts"]:
            out.extend((d["X"], ("count", k)) for k in d["counts"])
        else:
            out.append((d["X"], ("win", 1 if d["winner"] == 0 else 0)))
    return out


def measure(items, predict):
    """predict(d) -> per-round probabilities for corner A."""
    cards = exact = within_one = fights = right = 0
    for d in items:
        p = predict(d)
        mine = sum(q > .5 for q in p)
        fights += 1
        right += (2 * mine > len(p)) == (d["winner"] == 0) if 2 * mine != len(p) else 0
        for k in d["counts"]:
            cards += 1
            exact += mine == k
            within_one += abs(mine - k) <= 1
    return {"decisions": fights, "picks_official_winner": round(right / max(fights, 1), 4), "judge_cards": cards,
            "same_round_count_as_judge": round(exact / max(cards, 1), 4), "within_one_round": round(within_one / max(cards, 1), 4)}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--bridge", type=Path, required=True)
    parser.add_argument("--current", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit(f"{args.output} exists; write a new version instead.")
    data = gather(args.database, args.bridge, args.current, args.archive)
    order = sorted(data, key=lambda d: d["fid"])
    random.Random(11).shuffle(order)
    hand = lambda d: [1.0 if s > 0 else 0.0 if s < 0 else .5 for s in d["hand"]]
    held = {}
    for fold in range(FOLDS):
        w = fit(examples_for([d for i, d in enumerate(order) if i % FOLDS != fold]))
        for i, d in enumerate(order):
            if i % FOLDS == fold:
                held[d["fid"]] = list(1 / (1 + np.exp(-d["X"] @ w)))
    carded = [d for d in order if d["counts"]]
    pairs = same = 0
    for d in carded:
        for a, b in combinations(d["counts"], 2):
            pairs += 1
            same += a == b
    weights = fit(examples_for(order))
    report = {"version": VERSION, "features": FEATURES, "weights": [round(float(v), 5) for v in weights],
              "trained_on": {"decisions": len(order), "with_judge_totals": len(carded),
                             "judge_cards": sum(len(d["counts"]) for d in order),
                             "cards_left_out_10_8_or_deduction": sum(d["cards_dropped"] for d in order)},
              "out_of_sample": {"hand_picked_score": {"all": measure(order, hand), "fights_with_judge_totals": measure(carded, hand)},
                                "learned_score": {"all": measure(order, lambda d: held[d["fid"]]),
                                                  "fights_with_judge_totals": measure(carded, lambda d: held[d["fid"]])}},
              "two_real_judges_same_count": round(same / max(pairs, 1), 4), "judge_pairs": pairs}
    # How good are the confident calls? On cards where a judge gave every round to one fighter, each round's
    # winner is known, so held-out calls can be checked round by round.
    sure = sure_right = close = close_right = 0
    for d in carded:
        n = len(d["hand"])
        for k in d["counts"]:
            if k not in (0, n):
                continue
            for q in held[d["fid"]]:
                right = (q > .5) == (k == n)
                if abs(q - .5) >= .15:
                    sure += 1
                    sure_right += right
                else:
                    close += 1
                    close_right += right
    report["known_rounds_check"] = {"clear_calls": sure, "clear_calls_right": round(sure_right / max(sure, 1), 4),
                                    "close_calls": close, "close_calls_right": round(close_right / max(close, 1), 4),
                                    "note": "Rounds from cards a judge scored entirely for one fighter; clear = 65%+ either way."}
    args.output.mkdir(parents=True)
    body = json.dumps(report, indent=1) + "\n"
    (args.output / "model.json").write_text(body)
    (args.output / "manifest.json").write_text(json.dumps(
        {"version": VERSION, "output_sha256": {"model.json": hashlib.sha256(body.encode()).hexdigest()},
         "database_sha256": hashlib.sha256(args.database.read_bytes()).hexdigest(), "tool": "src/upset/ratings/round_scoring.py"}, indent=1) + "\n")
    print(body)


def load(folder):
    folder = Path(folder)
    manifest = json.loads((folder / "manifest.json").read_text())
    body = (folder / "model.json").read_bytes()
    if manifest.get("version") != VERSION or hashlib.sha256(body).hexdigest() != manifest["output_sha256"]["model.json"]:
        raise ValueError(f"{folder} does not match its fingerprint.")
    model = json.loads(body)
    return np.array(model["weights"]), model


if __name__ == "__main__":
    main()
