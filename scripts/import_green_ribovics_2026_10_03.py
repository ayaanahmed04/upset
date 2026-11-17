"""Admit the reviewed Green–Ribovics bout from the saved UFC 332 card."""

import json
from pathlib import Path
from shutil import copyfile
from tempfile import TemporaryDirectory

from import_recent_card import verify_preservation

from upset.data.build_research_db import build_database, rows
from upset.data.collect_cito_archive import _digest
from upset.data.export_cito_card import _bout_signature, _read_card
from upset.data.export_cito_current_archive import _manifest, normalize_completed_bout
from upset.data.identity import FighterProviderLink, FighterRegistry, load_fighter_registry, save_fighter_registry
from upset.data.reconcile_cito_archive import _write_verified
from upset.data.stage_current import stage_completed_fights

PROCESSED = Path("data/processed")
PRIOR = PROCESSED / "cito_current_2026_11_08_reviewed_v1"
PRIOR_DATABASE = PROCESSED / "research_2026_11_08_reviewed_v1/upset.sqlite"
CARD = Path("data/raw/cito_refresh_2026_10_05_v1/cards/ufc-332")
HISTORY = PROCESSED / "kaggle_ufc_1994_2026/identified"
ARCHIVE = PROCESSED / "cito_current_2026_11_10_reviewed_v1"
DATABASE = PROCESSED / "research_2026_11_10_reviewed_v1"
BOUT_ID = "13123"
GREEN_PROVIDER_ID = "81485dd0-6b98-44a5-9f6e-d4d8cad1c272"
GREEN_ID = "2f1e8b72-5466-4eee-acf2-34d5f32a460a"
RIBOVICS_PROVIDER_ID = "dfce6b48-e1d8-4811-aef3-d156448c983e"
RIBOVICS_ID = "4efe6b66-52e6-427f-93bf-f4b26ed74a80"
EVIDENCE = {
    "cito_fighter_id": GREEN_PROVIDER_ID,
    "upset_fighter_id": GREEN_ID,
    "name": "King Green",
    "reviewed_at": "2026-11-10",
    "source_bout_id": BOUT_ID,
    "basis": "Both official UFC athlete histories identify the dated UFC 332 matchup and result.",
    "public_sources": [
        "https://www.ufc.com/athlete/king-green",
        "https://www.ufc.com/athlete/esteban-ribovics",
        "https://www.ufc.com/index.php/video/160794",
    ],
}


def reviewed_fight():
    payloads, hashes, manifest_hash = _read_card(CARD)
    event, statistics = payloads["event"], payloads["stats"]
    listing = payloads["bouts"]
    if isinstance(listing, dict):
        listing = listing["bouts"]
    raw = next(row for row in listing if str(row["id"]) == BOUT_ID)
    for embedded in (event, statistics):
        matches = [row for row in embedded["bouts"] if str(row["id"]) == BOUT_ID]
        if len(matches) != 1 or _bout_signature(matches[0]) != _bout_signature(raw):
            raise ValueError("Saved UFC 332 endpoints disagree on the reviewed bout.")
    totals, rounds = ([row for row in statistics[key] if str(row["boutId"]) == BOUT_ID]
                      for key in ("boutStats", "roundStats"))
    fight, paired, reconciled = normalize_completed_bout(raw, event, totals, rounds)
    if (fight["event_date"], fight["source_fighter_1_id"], fight["source_fighter_2_id"],
            fight["fighter_2_name"], fight["winner_name"], fight["result_method"],
            fight["result_round"], fight["result_time"]) != (
                "2026-10-03", RIBOVICS_PROVIDER_ID, GREEN_PROVIDER_ID, "King Green",
                "Esteban Ribovics", "KO/TKO", 1, "4:08"):
        raise ValueError("Saved bout differs from the dated UFC evidence.")
    if len(paired) != 2 or len(reconciled) != 2:
        raise ValueError("Expected both fighters' totals and first-round statistics.")
    inputs = {str(CARD / f"{kind}.json"): digest for kind, digest in hashes.items()}
    inputs[str(CARD / "manifest.json")] = manifest_hash
    return fight, paired, inputs


def main():
    if ARCHIVE.exists() or DATABASE.exists():
        raise ValueError("Use fresh release directories.")
    inputs = {str(Path(__file__)): _digest(Path(__file__)), str(PRIOR_DATABASE): _digest(PRIOR_DATABASE)}
    prior = _manifest(PRIOR, inputs)
    fight, paired, raw_inputs = reviewed_fight()
    inputs.update(raw_inputs)
    if (fight != next(row for row in rows(PRIOR / "fights.jsonl") if row["source_bout_id"] == BOUT_ID)
            or paired != [row for row in rows(PRIOR / "fight_stats.jsonl") if row["source_bout_id"] == BOUT_ID]):
        raise ValueError("Reviewed raw fight or totals differ from the saved archive.")

    registry = load_fighter_registry(PRIOR / "fighter_registry.json")
    linked = {link.provider_fighter_id: link.upset_fighter_id for link in registry.provider_links if link.provider == "cito"}
    if (GREEN_PROVIDER_ID in linked or linked.get(RIBOVICS_PROVIDER_ID) != RIBOVICS_ID
            or not any(row.upset_fighter_id == GREEN_ID and row.display_name == "King Green"
                       for row in registry.identities)):
        raise ValueError("Reviewed identity links differ from the prior release.")
    registry = FighterRegistry(registry.identities, (*registry.provider_links,
        FighterProviderLink("cito", GREEN_PROVIDER_ID, GREEN_ID, json.dumps(EVIDENCE, sort_keys=True))))
    review = json.loads((PRIOR / "review.json").read_text())
    review["withheld_prior_bout_ids"].remove(BOUT_ID)
    review["unresolved_fighter_identities"] = [
        row for row in review["unresolved_fighter_identities"] if row["cito_fighter_id"] != GREEN_PROVIDER_ID
    ]
    review["green_ribovics_review"] = EVIDENCE

    with TemporaryDirectory(dir=PROCESSED, prefix=".upset-green-ribovics-") as temporary:
        folder = Path(temporary) / "current"
        folder.mkdir()
        for name in ("fights.jsonl", "fight_stats.jsonl", "fighters_identified.jsonl", "bout_provenance.jsonl"):
            copyfile(PRIOR / name, folder / name)
        rounds = rows(PRIOR / "rounds_staged.jsonl")
        for row in rounds:
            if row["source_bout_id"] == BOUT_ID and row["source_fighter_id"] == GREEN_PROVIDER_ID:
                row["upset_fighter_id"] = GREEN_ID
        for name, batch in (
            ("rounds_staged.jsonl", rounds),
            ("identity_link_evidence.jsonl", rows(PRIOR / "identity_link_evidence.jsonl") + [EVIDENCE]),
            ("accepted_fights.jsonl", rows(PRIOR / "accepted_fights.jsonl") + [fight]),
            ("accepted_fight_stats.jsonl", rows(PRIOR / "accepted_fight_stats.jsonl") + paired),
        ):
            _write_verified(folder / name, batch)
        save_fighter_registry(registry, folder / "fighter_registry.json")
        (folder / "review.json").write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n")
        staged = stage_completed_fights(folder / "accepted_fights.jsonl", folder / "accepted_fight_stats.jsonl",
            folder / "fighter_registry.json", HISTORY / "fights_identified.jsonl", folder / "identified")
        staged["input_paths"] = {"registry": str(ARCHIVE / "fighter_registry.json"),
                                 "historical": str(HISTORY / "fights_identified.jsonl")}
        (folder / "identified/manifest.json").write_text(json.dumps(staged, indent=2) + "\n")
        manifest = {
            **prior, "status": "Reviewed October 3 Green–Ribovics backfill",
            "identified_current_bouts": prior["identified_current_bouts"] + 1,
            "backfilled_bouts": 1, "new_bouts": 0, "new_identities": 0, "identity_links_added": 1,
            "bouts_awaiting_identity_review": len(review["withheld_prior_bout_ids"]),
            "unresolved_provider_fighters": len(review["unresolved_fighter_identities"]),
            "identified_subset_manifest": staged, "input_sha256": inputs,
            "output_sha256": {str(path.relative_to(folder)): _digest(path)
                              for path in folder.rglob("*") if path.is_file()},
        }
        if any(_digest(Path(path)) != digest for path, digest in inputs.items()):
            raise ValueError("Reviewed input files changed during import.")
        (folder / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        folder.rename(ARCHIVE)

    build_database(HISTORY, ARCHIVE, ARCHIVE / "fighter_registry.json",
                   PROCESSED / "cito_historical_rounds_v1", DATABASE)
    result = verify_preservation(PRIOR_DATABASE, DATABASE / "upset.sqlite")
    if [result[table]["added"] for table in ("fighters", "fights", "stats")] != [0, 1, 2]:
        raise ValueError("The reviewed import must add only the fight and its paired statistics.")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
