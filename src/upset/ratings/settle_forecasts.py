"""Score a saved pre-event forecast against a reviewed results database."""

import argparse
import hashlib
import json
import math
import re
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from upset.data.identity import validate_upset_fighter_id
from upset.ratings.data import load_bouts
from upset.skill.striking_adapter import digest, encoded, verify_hashes, write_artifact

ORIENTATION = "Listed first fighter conditional on a decisive result"
EVENT_URL = re.compile(r"https://www\.ufc\.com/event/([a-z0-9-]+)")


def event_identity(forecast):
    event = EVENT_URL.fullmatch(forecast["source_urls"][0])
    start = datetime.fromisoformat(forecast["scheduled_start_utc"])
    frozen = datetime.fromisoformat(forecast["frozen_at_utc"])
    day = date.fromisoformat(forecast["event_date"])
    if (event is None or start.utcoffset() is None or frozen.utcoffset() is None
            or not frozen < start or not date.fromisoformat(forecast["data_through"]) < day
            or forecast["probability_orientation"] != ORIENTATION):
        raise ValueError("Forecast event, time or probability orientation is invalid.")
    return event[1], day


def validate_predictions(matchups):
    seen = set()
    models = None
    for row in matchups:
        names, ids = row["fighters"], row["fighter_ids"]
        if len(names) != 2 or len(ids) != 2 or not all(isinstance(name, str) and name for name in names):
            raise ValueError("A scheduled matchup needs two fighters.")
        for uid in ids:
            if uid is not None:
                validate_upset_fighter_id(uid)
        known = frozenset(uid for uid in ids if uid is not None)
        if len(known) != sum(uid is not None for uid in ids) or seen & known:
            raise ValueError("A fighter appears more than once on the frozen card.")
        seen.update(known)
        probabilities = row["probabilities_a"]
        if row["status"] == "matched":
            if len(known) != 2 or not probabilities or any(not valid_probability(p) for p in probabilities.values()):
                raise ValueError("Eligible forecasts require two linked identities and valid probabilities.")
            if models is None:
                models = set(probabilities)
            elif set(probabilities) != models:
                raise ValueError("Eligible forecasts must share a model cohort.")
        elif row["status"] != "insufficient_linked_ufc_history" or probabilities is not None:
            raise ValueError("Unmatched forecasts must preserve their original coverage status.")
        market = row["market_probability_a"]
        if market is not None and not valid_probability(market):
            raise ValueError("Invalid archived market probability.")


def valid_probability(value):
    return type(value) in (int, float) and 0 < value < 1


def score_rows(rows, model):
    predictions = [(row["market_probability_a"] if model == "market" else row["probabilities_a"][model],
                    row["winner_is_first"]) for row in rows]
    if not predictions:
        return {"bouts": 0}
    correct = sum((p > .5) == won for p, won in predictions if p != .5)
    ties = sum(p == .5 for p, _ in predictions)
    return {"bouts": len(predictions), "correct": correct, "ties": ties,
            "ordering_accuracy": (correct + .5 * ties) / len(predictions),
            "log_loss": -math.fsum(math.log(p) if won else math.log1p(-p)
                                   for p, won in predictions) / len(predictions),
            "brier": math.fsum((p - won) ** 2 for p, won in predictions) / len(predictions)}


def settle(forecast, bouts):
    slug, day = event_identity(forecast)
    validate_predictions(forecast["matchups"])
    source = f"https://api.citoapi.com/api/v1/ufc/events/{slug}/bouts"
    card = [bout for bout in bouts if bout["event_date"] == day.isoformat() and bout["source_url"] == source]
    by_pair = {}
    for bout in card:
        pair = frozenset(bout["fighter_ids"])
        if pair in by_pair:
            raise ValueError("Ambiguous reviewed pair on the event date.")
        by_pair[pair] = bout

    results, scored = [], []
    for row in forecast["matchups"]:
        result = {**row, "forecast_status": row["status"], "fight_id": None, "winner_id": None,
                  "winner_is_first": None}
        bout = by_pair.get(frozenset(row["fighter_ids"]))
        if row["probabilities_a"] is None:
            result["status"] = "no_frozen_forecast"
        elif bout is None:
            result["status"] = "no_reviewed_match" if card else "awaiting_reviewed_results"
        elif bout["winner_id"] is None:
            result["status"] = "nondecisive"
        else:
            result["status"] = "scored"
            result["winner_is_first"] = bout["winner_id"] == row["fighter_ids"][0]
            scored.append(result)
        if bout:
            result.update(fight_id=bout["fight_id"], winner_id=bout["winner_id"],
                          recorded_outcome=bout["outcome"], result_method=bout["result_method"])
        results.append(result)

    market = [row for row in scored if row["market_probability_a"] is not None]
    models = sorted(scored[0]["probabilities_a"]) if scored else []
    return {"event": forecast["event"], "event_date": day.isoformat(),
            "frozen_at_utc": forecast["frozen_at_utc"], "reviewed_event_bouts": len(card),
            "statuses": dict(Counter(row["status"] for row in results)),
            "models": {model: score_rows(scored, model) for model in models},
            "market_matched": {model: score_rows(market, model) for model in (*models, "market")},
            "matchups": results}


def run(ledger, database, output):
    if output.exists() or any(output.resolve().is_relative_to(folder.resolve())
                              for folder in (ledger, database.parent)):
        raise ValueError("Use a fresh output directory separate from the forecast and results.")
    paths = (ledger / "manifest.json", ledger / "forecast.json", database, Path(__file__))
    inputs = {str(path.resolve()): digest(path) for path in paths}
    manifest = json.loads(paths[0].read_text())
    if manifest["output_sha256"]["forecast.json"] != inputs[str(paths[1].resolve())]:
        raise ValueError("Frozen forecast differs from its manifest.")
    forecast = json.loads(paths[1].read_text())
    _, day = event_identity(forecast)
    bouts, _ = load_bouts(database, (day + timedelta(days=1)).isoformat())
    report = settle(forecast, bouts)
    verify_hashes(inputs)
    body = encoded(report)
    write_artifact(output, {"settlement.json": body, "manifest.json": encoded({
        "created_at_utc": datetime.now(UTC).isoformat(), "input_sha256": inputs,
        "output_sha256": {"settlement.json": hashlib.sha256(body.encode()).hexdigest()},
    })})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ("ledger", "database", "output"):
        parser.add_argument("--" + field, type=Path, required=True)
    args = parser.parse_args()
    report = run(args.ledger, args.database, args.output)
    print(encoded({key: value for key, value in report.items() if key != "matchups"}))


if __name__ == "__main__":
    main()
