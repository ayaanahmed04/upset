"""Record the UFC 334 research forecasts before the card begins."""

import hashlib
import json
from collections import defaultdict
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from scipy.special import expit

from upset.data.audit_cito_archive import _name
from upset.ratings.data import load_bouts
from upset.ratings.results_benchmark import elo_at, load_histories, prior_state, replay_elo
from upset.ratings.serving_v4 import load_snapshot
from upset.research_app import connect
from upset.skill.striking_adapter import digest, encoded, verify_hashes, write_artifact

DATA = Path("data/processed")
DATABASE = DATA / "research_2026_11_10_reviewed_v1/upset.sqlite"
SNAPSHOT = DATA / "overall_rating_v4_2026_11_10_reviewed_v1"
BENCHMARK = DATA / "rating_results_benchmark_2026_11_10_v2"
OUTPUT = DATA / "rating_prospective_ufc334_2026_11_10_v1"
EVENT_DATE = "2026-11-14"
START = datetime(2026, 11, 14, 22, tzinfo=UTC)
EVENT_URL = "https://www.ufc.com/event/ufc-334"
UPDATE_URL = "https://www.ufc.com/news/updates-polymarket-ufc-334-gane-vs-hokit"
# The November 10 official card and the two-sided prices displayed with it.
CARD = (
    ("Ciryl Gane", "Josh Hokit", (-205, 170)),
    ("Kayla Harrison", "Amanda Nunes", (-190, 160)),
    ("Caio Borralho", "Yousri Belgaroui", (-155, 130)),
    ("Uroš Medić", "Kevin Holland", (-155, 130)),
    ("Bilal Hasan", "Luis Gurule", (-1100, 700)),
    ("Stephen Thompson", "Charles Radtke", (-145, 120)),
    ("Drew Dober", "Chris Duncan", (-145, 120)),
    ("Jim Miller", "Terrance McKinney", (170, -205)),
    ("Donte Johnson", "Cesar Almeida", (-175, 145)),
    ("Jared Gordon", "Melquizael Costa", (290, -370)),
    ("Macy Chiasson", "Bia Mesquita", (210, -260)),
    ("Alatengheili", "Juan Diaz", None),
    ("Evan Elder", "Samuel Sanches", (100, -120)),
)


def market_probability(prices):
    a, b = [abs(odds) / (abs(odds) + 100) if odds < 0 else 100 / (odds + 100) for odds in prices]
    return a / (a + b)


def main():
    started = datetime.now(UTC)
    if started >= START:
        raise ValueError("The scheduled card start has passed.")
    report = BENCHMARK / "summary.json"
    manifest = json.loads((BENCHMARK / "manifest.json").read_text())
    inputs = {str(path.resolve()): digest(path) for path in
              (Path(__file__), DATABASE, SNAPSHOT / "manifest.json", report, BENCHMARK / "manifest.json")}
    if (inputs[str(report.resolve())] != manifest["output_sha256"]["summary.json"]
            or any(inputs[str(path.resolve())] != manifest["input_sha256"][str(path.resolve())]
                   for path in (DATABASE, SNAPSHOT / "manifest.json"))):
        raise ValueError("Forecast calibration and data differ from the verified benchmark.")
    verify_hashes(manifest["input_sha256"])

    reference = load_snapshot(SNAPSHOT, DATABASE)
    cutoff = reference.metadata["before_exclusive"]
    if reference.metadata["latest_event"] >= EVENT_DATE or cutoff > EVENT_DATE:
        raise ValueError("The forecast cannot use any part of this event's results.")
    fold = next(fold for fold in json.loads(report.read_text())["folds"] if fold["year"] == "2026")
    histories = load_histories(SNAPSHOT)
    bouts, _ = load_bouts(DATABASE, cutoff)
    standard = replay_elo(bouts, 32)[2]
    responsive = replay_elo(bouts, 64, 730)[2]
    fighter_ids = defaultdict(list)
    with closing(connect(DATABASE)) as db:
        for row in db.execute("SELECT id,name FROM fighters"):
            fighter_ids[_name(row["name"])].append(row["id"])

    rows = []
    for a, b, prices in CARD:
        matched = [fighter_ids[_name(name)] for name in (a, b)]
        if any(len(matches) > 1 for matches in matched):
            raise ValueError(f"Ambiguous scheduled fighter in {a} vs {b}.")
        ids = [matches[0] if matches else None for matches in matched]
        prior = [prior_state(histories, uid, cutoff) for uid in ids]
        row = {"fighters": [a, b], "fighter_ids": ids,
               "v4_badges": [state[1] if state else None for state in prior],
               "v4_state_dates": [state[0] if state else None for state in prior],
               "market_prices_american": prices, "market_source_url": EVENT_URL if prices else None,
               "market_probability_a": market_probability(prices) if prices else None,
               "status": "matched" if all(prior) else "insufficient_linked_ufc_history",
               "probabilities_a": None}
        if all(prior):
            differences = {"v4_rolling": (prior[0][2] - prior[1][2]) / 10}
            for key, state, decay in (("elo32", standard, None), ("elo64_decay", responsive, 730)):
                first, second = [elo_at(state, uid, EVENT_DATE, decay) for uid in ids]
                differences[key] = (first - second) / 100
            row["probabilities_a"] = {model: float(expit(fold["slopes"][model] * delta))
                                      for model, delta in differences.items()}
            row["probabilities_a"]["v4_fixed"] = float(expit(
                reference.metadata["model"]["probability_fit"]["slope"] * 10 * differences["v4_rolling"]))
        rows.append(row)
    verify_hashes(inputs)
    frozen_at = datetime.now(UTC)
    if frozen_at >= START:
        raise ValueError("The event began before the forecast could be saved.")
    ledger = {"event": "UFC 334", "event_date": EVENT_DATE, "scheduled_start_utc": START.isoformat(),
              "frozen_at_utc": frozen_at.isoformat(), "source_urls": [EVENT_URL, UPDATE_URL],
              "data_through": reference.metadata["latest_event"], "calibration_before": "2026-01-01",
              "probability_orientation": "Listed first fighter conditional on a decisive result",
              "market_timing": "Prices shown on the UFC card when reviewed November 10, before the event",
              "matchups": rows}
    body = encoded(ledger)
    write_artifact(OUTPUT, {"forecast.json": body, "manifest.json": encoded({
        "input_sha256": inputs, "output_sha256": {"forecast.json": hashlib.sha256(body.encode()).hexdigest()},
    })})
    print(f"Saved {sum(row['status'] == 'matched' for row in rows)} of {len(rows)} forecasts to {OUTPUT}.")


if __name__ == "__main__":
    main()
