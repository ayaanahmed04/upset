"""Compare v4, results-only Elo and archived pre-event odds on matched bouts."""

import argparse
import csv
import hashlib
import json
import math
from bisect import bisect_left
from collections import Counter, defaultdict
from contextlib import closing
from datetime import UTC, date, datetime, timedelta
from io import TextIOWrapper
from itertools import groupby
from pathlib import Path
from urllib.parse import urlsplit
from zipfile import ZipFile

import numpy as np
from scipy.optimize import minimize_scalar
from scipy.special import expit, logit

from upset.data.audit_cito_archive import _name
from upset.data.identity import load_fighter_registry
from upset.data.reviewed_bout_metadata import reviewed_title_evidence
from upset.ratings import build, serving_v4
from upset.ratings.data import load_bouts
from upset.ratings.engine import elo_expectation
from upset.research_app import connect
from upset.skill.striking_adapter import digest, encoded, verify_hashes, write_artifact

FIT_START = "2012-01-01"
EVAL_START = "2019-01-01"
RECENT = "2025-01-01"
MODELS = {"v4_rolling": (0., 50.), "elo32": (0., 5.), "elo64_decay": (0., 5.)}
CASE_PAIRS = {frozenset(pair) for pair in (
    ("Petr Yan", "Merab Dvalishvili"), ("Justin Gaethje", "Ilia Topuria"),
    ("Sean Strickland", "Khamzat Chimaev"), ("Justin Gaethje", "Paddy Pimblett"),
    ("Alex Pereira", "Magomed Ankalaev"), ("Ilia Topuria", "Charles Oliveira"),
    ("Michael Morales", "Sean Brady"), ("Manuel Torres", "Grant Dawson"),
)}


def elo_at(state, uid, day, half_life):
    value, previous = state.get(uid, (1500., day))
    if half_life:
        elapsed = (date.fromisoformat(day) - date.fromisoformat(previous)).days
        value = 1500 + (value - 1500) * 2 ** (-elapsed / half_life)
    return value


def replay_elo(bouts, factor, half_life=None):
    """Score every pairing from the start of the date, then apply its updates."""
    states, ratings, histories = {}, {}, {}
    for day, batch in groupby(bouts, key=lambda bout: bout["event_date"]):
        changes = defaultdict(list)
        for bout in batch:
            a, b = bout["fighter_ids"]
            values = tuple(elo_at(states, uid, day, half_life) for uid in (a, b))
            ratings[bout["fight_id"]] = values
            if bout["winner_id"] is not None:
                delta = factor * ((bout["winner_id"] == a) - elo_expectation(*values))
                changes[a].append(delta)
                changes[b].append(-delta)
        for uid, updates in changes.items():
            value = elo_at(states, uid, day, half_life) + math.fsum(updates)
            states[uid] = value, day
            histories[day, uid] = value
    return ratings, histories, states


def load_histories(snapshot):
    histories = defaultdict(list)
    with (snapshot / "ratings.jsonl").open() as stream:
        for line in stream:
            row = json.loads(line)
            histories[row["fighter_id"]].append(
                (row["event_date"], row["score"], row["raw_combined"], row["elo"]))
    return {uid: (tuple(row[0] for row in history), history) for uid, history in histories.items()}


def prior_state(histories, uid, cutoff):
    days, rows = histories.get(uid, ((), ()))
    index = bisect_left(days, cutoff)
    return rows[index - 1] if index else None


def source_metadata(database):
    with closing(connect(database)) as db:
        return {row["id"]: json.loads(row["payload"]) for row in db.execute("SELECT id,payload FROM fights")}


def ufcstats_key(url, kind):
    parts = urlsplit(url)
    prefix = f"/{kind}-details/"
    if parts.hostname in {"ufcstats.com", "www.ufcstats.com"} and parts.path.startswith(prefix):
        return parts.path.removeprefix(prefix)
    return None


def market_probabilities(archive, bouts, source, registry):
    by_url, by_names = {}, defaultdict(set)
    by_id = {bout["fight_id"]: bout for bout in bouts}
    stats_ids = {link.provider_fighter_id: link.upset_fighter_id
                 for link in registry.provider_links if link.provider == "ufcstats"}
    for bout in bouts:
        key, day = bout["fight_id"], bout["event_date"]
        raw = source[key]
        url_id = ufcstats_key(raw.get("source_url") or "", "fight")
        if url_id:
            by_url[url_id] = key
        for names in (bout["names"], [raw["fighter_1_name"], raw["fighter_2_name"]]):
            by_names[day, tuple(sorted(map(_name, names)))].add(key)

    latest = {}
    with ZipFile(archive) as zipped, zipped.open("UFC_betting_odds.csv") as stream:
        rows = csv.DictReader(TextIOWrapper(stream, encoding="utf-8-sig"))
        for row in rows:
            day = row["event_date"]
            if day < EVAL_START or (row["source"], row["region"]) != ("BetOnline.ag", "us"):
                continue
            timestamp = datetime.fromisoformat(row["adding_date"])
            if timestamp.utcoffset() is None:
                continue
            timestamp = timestamp.astimezone(UTC)
            lead_days = (date.fromisoformat(day) - timestamp.date()).days
            if not 1 <= lead_days <= 7:
                continue
            names = [_name(row[f"fighter_{i}"]) for i in (1, 2)]
            url_id = ufcstats_key(row["fight_url"], "fight")
            if url_id:
                key = by_url.get(url_id)
            else:
                matched = by_names[day, tuple(sorted(names))]
                key = next(iter(matched)) if len(matched) == 1 else None
            if key is None:
                continue
            bout, raw = by_id[key], source[key]
            if bout["event_date"] != day:
                continue
            observed_ids = [stats_ids.get(ufcstats_key(row[f"fighter_{i}_url"], "fighter"))
                            for i in (1, 2)]
            ids = bout["fighter_ids"]
            if url_id:
                if set(observed_ids) != set(ids):
                    continue
                reverse = observed_ids[0] != ids[0]
            else:
                candidates = [list(map(_name, pair)) for pair in
                              (bout["names"], [raw["fighter_1_name"], raw["fighter_2_name"]])]
                reverse = names not in candidates
                if any(uid and uid != expected for uid, expected in
                       zip(observed_ids, ids[::-1] if reverse else ids, strict=True)):
                    continue
            if not row["odds_1"] or not row["odds_2"]:
                continue
            prices = tuple(float(row[f"odds_{i}"]) for i in (1, 2))
            if any(not math.isfinite(price) or price <= 1 for price in prices):
                continue
            a, b = prices[::-1] if reverse else prices
            candidate = {"probability_a": b / (a + b), "observed_at": timestamp.isoformat(),
                         "decimal_odds": [a, b], "match": "ufcstats_ids" if url_id else "dated_pair"}
            previous = latest.get(key)
            if previous is None or timestamp > previous[0]:
                latest[key] = timestamp, candidate
            elif timestamp == previous[0] and candidate != previous[1]:
                latest[key] = timestamp, None
    return {key: entry for key, (_, entry) in latest.items() if entry is not None}


def fit_slope(rows, model):
    x = np.array([row["differences"][model] for row in rows])
    y = np.array([row["winner_a"] for row in rows])
    if not len(x) or not np.any(x):
        raise ValueError(f"Insufficient earlier calibration evidence for {model}.")

    def loss(slope):
        z = slope * x
        return float(np.mean(np.logaddexp(0, z) - y * z))

    bounds = MODELS[model]
    result = minimize_scalar(loss, bounds=bounds, method="bounded")
    if not result.success:
        raise ValueError(f"Calibration failed for {model}.")
    return min((*bounds, float(result.x)), key=loss)


def evaluate(rows, fixed_slope):
    folds, predictions = [], []
    for year in sorted({row["event_date"][:4] for row in rows if row["event_date"] >= EVAL_START}):
        start = year + "-01-01"
        training = [row for row in rows if FIT_START <= row["event_date"] < start]
        slopes = {model: fit_slope(training, model) for model in MODELS}
        for row in rows:
            if row["event_date"][:4] != year:
                continue
            probabilities = {model: float(expit(slope * row["differences"][model]))
                             for model, slope in slopes.items()}
            probabilities["v4_fixed"] = float(expit(fixed_slope * 10 * row["differences"]["v4_rolling"]))
            predictions.append({**row, "probabilities": probabilities})
        folds.append({"year": year, "training_bouts": len(training), "slopes": slopes})
    return predictions, folds


def summarize(rows, market=False):
    if not rows:
        return {"bouts": 0}
    model_names = ("coin_flip", "v4_fixed", *MODELS, *(("market",) if market else ()))
    y = np.array([row["winner_a"] for row in rows])
    result, losses = {}, {}
    for model in model_names:
        if model == "market":
            p = np.array([row["market"]["probability_a"] for row in rows])
        elif model == "coin_flip":
            p = np.full(len(rows), .5)
        else:
            p = np.array([row["probabilities"][model] for row in rows])
        safe = np.clip(p, 1e-15, 1 - 1e-15)
        losses[model] = np.logaddexp(0, logit(safe)) - y * logit(safe)
        ties = p == .5
        result[model] = {"log_loss": float(np.mean(losses[model])),
                         "brier": float(np.mean((p - y) ** 2)), "ties": int(ties.sum()),
                         "ordering": float(np.mean(np.where(ties, .5, (p > .5) == y)))}
    badge_diff = np.array([row["badges"][0] - row["badges"][1] for row in rows])
    alternatives = ("elo32", "elo64_decay", "market") if market else ("elo32", "elo64_decay")
    paired = {model: build.cluster_comparison(rows, losses[model] - losses["v4_rolling"], "event_date")
              for model in alternatives}
    return {"bouts": len(rows), "models": result, "paired_log_loss_vs_v4_rolling": paired,
            "v4_badge_ordering": float(np.mean(np.where(badge_diff == 0, .5, (badge_diff > 0) == y))),
            "v4_badge_ties": int(np.count_nonzero(badge_diff == 0))}


def title_orderings(cases):
    title_bouts = [row for row in cases if row["title"]]
    orderings = {}
    for model in ("v4", "elo32", "elo64_decay"):
        for stage in ("before", "after", "latest"):
            key = f"{model}_{stage}"
            counts = Counter()
            for row in title_bouts:
                a, b = row[key]
                if a is None or b is None:
                    counts["missing"] += 1
                elif a == b:
                    counts["tied"] += 1
                else:
                    counts["winner_ahead" if (a > b) == row["winner_a"] else "winner_behind"] += 1
            orderings[key] = dict(counts)
    return {"bouts": len(title_bouts), "orderings": orderings}


def comparison(database, snapshot, registry_path, odds, protocol, output):
    if output.exists() or output.resolve().is_relative_to(database.parent.resolve()):
        raise ValueError("Use a new analysis directory outside the serving database folder.")
    inputs = {str(path.resolve()): digest(path) for path in
              (database, registry_path, odds, protocol, Path(__file__),
               snapshot / "manifest.json", snapshot / "ratings.jsonl")}
    reference = serving_v4.load_snapshot(snapshot, database)
    cutoff = reference.metadata["before_exclusive"]
    bouts, _ = load_bouts(database, cutoff)
    source = source_metadata(database)
    histories = load_histories(snapshot)
    standard = replay_elo(bouts, 32)
    responsive = replay_elo(bouts, 64, 730)
    quotes = market_probabilities(odds, bouts, source, load_fighter_registry(registry_path))
    matched, cases, excluded = [], [], Counter()
    for bout in bouts:
        key, day, ids = (bout[name] for name in ("fight_id", "event_date", "fighter_ids"))
        raw = source[key]
        title = "Title" in (raw.get("weight_class") or "") or reviewed_title_evidence(raw) is not None
        prior = [prior_state(histories, uid, day) for uid in ids]
        post_cutoff = (date.fromisoformat(day) + timedelta(days=1)).isoformat()
        post = [prior_state(histories, uid, post_cutoff) for uid in ids]
        if any(row and not math.isclose(row[3], standard[0][key][index], abs_tol=1e-9)
               for index, row in enumerate(prior)):
            raise ValueError(f"Results-only baseline does not reproduce the saved résumé Elo for {key}.")
        if bout["winner_id"] is None:
            if day >= EVAL_START:
                excluded["nondecisive"] += 1
            continue
        winner_a = bout["winner_id"] == ids[0]
        if day >= RECENT and (title or frozenset(bout["names"]) in CASE_PAIRS):
            cases.append({"fight_id": key, "event_date": day, "title": title,
                          "fighters": bout["names"], "winner_a": winner_a,
                          "v4_before": [row[1] if row else None for row in prior],
                          "v4_after": [row[1] if row else None for row in post],
                          "v4_latest": [prior_state(histories, uid, cutoff)[1] for uid in ids],
                          "elo32_before": standard[0][key],
                          "elo32_after": [standard[1][day, uid] for uid in ids],
                          "elo32_latest": [elo_at(standard[2], uid, cutoff, None) for uid in ids],
                          "elo64_decay_before": responsive[0][key],
                          "elo64_decay_after": [responsive[1][day, uid] for uid in ids],
                          "elo64_decay_latest": [elo_at(responsive[2], uid, cutoff, 730) for uid in ids]})
        if any(row is None for row in prior):
            if day >= EVAL_START:
                excluded["no_prior_v4_for_one_or_both"] += 1
            continue
        a, b = prior
        matched.append({"fight_id": key, "event_date": day, "fighter_ids": ids,
                        "fighter_names": bout["names"], "winner_a": winner_a, "title": title,
                        "badges": [a[1], b[1]], "v4_state_dates": [a[0], b[0]],
                        "differences": {"v4_rolling": (a[2] - b[2]) / 10,
                                        "elo32": (standard[0][key][0] - standard[0][key][1]) / 100,
                                        "elo64_decay": (responsive[0][key][0] - responsive[0][key][1]) / 100},
                        "market": quotes.get(key)})
    predictions, folds = evaluate(matched, reference.metadata["model"]["probability_fit"]["slope"])
    recent = [row for row in predictions if row["event_date"] >= RECENT]
    market = [row for row in predictions if row["market"] is not None]
    summary = {"before_exclusive": cutoff, "excluded": dict(excluded), "folds": folds,
               "all": summarize(predictions), "recent": summarize(recent),
               "recent_title": summarize([row for row in recent if row["title"]]),
               "title_orderings": title_orderings(cases),
               "market": summarize(market, market=True),
               "market_years": dict(Counter(row["event_date"][:4] for row in market)),
               "annual": {fold["year"]: summarize([row for row in predictions
                                                  if row["event_date"][:4] == fold["year"]])
                          for fold in folds}}
    files = {"summary.json": encoded(summary), "cases.json": encoded(cases),
             "predictions.jsonl": "".join(json.dumps(row, sort_keys=True, allow_nan=False) + "\n" for row in predictions),
             "protocol.md": protocol.read_text()}
    verify_hashes(inputs)
    files["manifest.json"] = encoded({"retrospective": True, "input_sha256": inputs,
                                     "market_source": "https://www.kaggle.com/datasets/jerzyszocik/ufc-betting-odds-daily-dataset",
                                     "output_sha256": {name: hashlib.sha256(body.encode()).hexdigest()
                                                       for name, body in files.items()}})
    write_artifact(output, files)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("database", "snapshot", "registry", "odds", "protocol", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    report = comparison(args.database, args.snapshot, args.registry, args.odds, args.protocol, args.output)
    print(encoded({key: report[key] for key in ("all", "recent", "recent_title", "market", "market_years")}))


if __name__ == "__main__":
    main()
