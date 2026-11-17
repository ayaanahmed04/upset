"""Accept reviewed Steveson/Parnasse identities from existing saved evidence."""

import argparse
import json
from pathlib import Path

from upset.data.build_research_db import rows
from upset.data.collect_cito_archive import _digest
from upset.data.integrate_cito_rahiki_identities import integrate

REVIEWED = (
    {
        "name": "Gable Steveson",
        "cito_fighter_id": "0627d23e-7e8b-4eac-af5d-9b459b712e66",
        "new_upset_fighter_id": "c8833bb7-7f48-45e4-99a7-12c3a52b66a2",
        "bout_id": "118c25bda9392140",
        "event_date": "2026-07-11",
        "opponent_name": "Elisha Ellison",
        "opponent_cito_id": "d26bbb5b-b9ea-414e-9efd-29c90828e652",
        "opponent_ufcstats_id": "87e4a3a5080ee7ce",
        "public_profile_url": "https://www.ufc.com/athlete/gable-steveson",
        "public_bout_url": "https://www.ufc.com/video/158290",
        "history_sha256": "c444837a4b4e103ec0bbe8bc0c02133185b7de2aec4f42786477d08b16a54f05",
        "public_identity_sources": [
            "https://www.ufc.com/video/158290",
            "https://jp.ufc.com/news/cryptocom-ufc-331-van-vs-pantoja-2-official-scorecards",
        ],
        "public_clock_note": "UFC debut video lists 2:31; prelim/scorecard text lists 2:32. Saved source clock 2:31 is preserved. Identity evidence does not resolve every source clock conflict.",
        "expected_history": [
            {"bout_id": "118c25bda9392140", "date": "2026-07-11", "opponent": "Elisha Ellison", "outcome": "win", "method": "KO/TKO", "round": 1, "time": "2:31"},
            {"bout_id": "cryptocom-ufc-331-jsonapi-11", "date": "2026-09-19", "opponent": "Sean Sharaf", "outcome": "loss", "method": "KO/TKO", "round": 1, "time": "0:12"},
        ],
    },
    {
        "name": "Salahdine Parnasse",
        "cito_fighter_id": "1e39b040-9955-400e-a1c8-8ccb6bf29fcd",
        "new_upset_fighter_id": "f9ea8a84-55f1-4c5f-be9e-407e9aa4c351",
        "bout_id": "bba8c0ab999b9e6f",
        "event_date": "2026-09-05",
        "opponent_name": "Dan Hooker",
        "opponent_cito_id": "8a873ec7-e6bc-4a08-8977-124e8c6291c2",
        "opponent_ufcstats_id": "193b9d1858bc4df3",
        "public_profile_url": "https://www.ufc.com/athlete/salahdine-parnasse",
        "public_bout_url": "https://jp.ufc.com/news/ufc-paris-official-scorecards-hooker-vs-parnasse",
        "history_sha256": "cd99feb4b9d24afc7129f4e356ed382869f31ac4a4c5c563917392f1033b6ac9",
        "public_identity_sources": [
            "https://www.ufc.com/athlete/salahdine-parnasse",
            "https://jp.ufc.com/news/ufc-paris-official-scorecards-hooker-vs-parnasse",
        ],
        "public_clock_note": "UFC scorecard and saved source list 2:35; UFC main-card recap lists 2:25. Saved source clock is preserved.",
        "expected_history": [
            {"bout_id": "bba8c0ab999b9e6f", "date": "2026-09-05", "opponent": "Dan Hooker", "outcome": "win", "method": "KO/TKO", "round": 1, "time": "2:35"},
        ],
    },
)


def verify_complete_history(rule, canonical, history):
    """Both Steveson fights must agree across saved histories and canonical rows."""
    expected = {r["bout_id"]: r for r in rule["expected_history"]}
    own = rule["cito_fighter_id"]
    fights = [r for r in canonical if own in (r["source_fighter_1_id"], r["source_fighter_2_id"])]
    if (len(fights) != len(expected) or len(history) != len(expected)
            or {r["source_bout_id"] for r in fights} != set(expected)
            or {str(r["bout"]["id"]) for r in history} != set(expected)):
        raise ValueError("Reviewed complete fighter history differs.")
    for fight in fights:
        wanted = expected[fight["source_bout_id"]]
        saved = next(r for r in history if str(r["bout"]["id"]) == wanted["bout_id"])
        side = 1 if fight["source_fighter_1_id"] == own else 2
        other = 3 - side
        winner = rule["name"] if wanted["outcome"] == "win" else wanted["opponent"]
        if (fight[f"fighter_{side}_name"] != rule["name"]
                or fight[f"fighter_{other}_name"] != wanted["opponent"]
                or fight["event_date"] != wanted["date"]
                or fight["winner_name"] != winner
                or fight["source_winner_label"] != winner
                or saved["fighterName"] != rule["name"]
                or saved["opponent"]["name"] != wanted["opponent"]
                or saved["event"]["eventDate"] != wanted["date"]
                or saved["outcome"] != wanted["outcome"]
                or saved["isCompleted"] is not True
                or saved["bout"].get("status") != "completed"
                or saved["bout"].get("isCancelled") is True):
            raise ValueError("Reviewed participant, date or outcome differs.")
        for canonical_field, saved_field, wanted_field in (
            ("result_method", "method", "method"),
            ("result_round", "resultRound", "round"),
            ("result_time", "resultTime", "time"),
        ):
            if fight[canonical_field] != wanted[wanted_field] or saved["bout"][saved_field] != wanted[wanted_field]:
                raise ValueError("Reviewed result or clock differs.")


def integrate_newcomers(current, bundles, historical, output):
    canonical = rows(current / "fights.jsonl")
    for rule in REVIEWED:
        path = bundles / "fighters" / rule["cito_fighter_id"] / "fights.json"
        if _digest(path) != rule["history_sha256"]:
            raise ValueError("Reviewed newcomer history hash differs.")
        wrapper = json.loads(path.read_text())
        verify_complete_history(rule, canonical, wrapper["response"]["data"])
    return integrate(current, bundles, historical, output, rules=REVIEWED)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current", type=Path, default=Path("data/processed/cito_current_rahiki_v1"))
    parser.add_argument("--bundles", type=Path, default=Path("data/raw/cito_fighter_bundles_v1"))
    parser.add_argument("--historical", type=Path, default=Path("data/processed/kaggle_ufc_1994_2026/identified/fights_identified.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/cito_current_newcomers_v1"))
    args = parser.parse_args()
    result = integrate_newcomers(args.current, args.bundles, args.historical, args.output)
    print(json.dumps({k: result[k] for k in ("identity_links_added", "newly_identified_bouts", "identified_current_bouts", "bouts_awaiting_identity_review", "unresolved_provider_fighters", "api_calls")}, indent=2))


if __name__ == "__main__":
    main()
