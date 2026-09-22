import json
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from upset.data.export_identified import export_identified_historical
from upset.data.identify_historical import identify_historical_data
from upset.data.identity import (
    FighterIdentity,
    FighterProviderLink,
    FighterRegistry,
    load_fighter_registry,
    save_fighter_registry,
)
from upset.data.models import Fight, Fighter, FightStats

SOURCE = "kaggle_ufc_1994_2026"
FIRST_ID = "00000000-0000-4000-8000-000000000001"
SECOND_ID = "00000000-0000-4000-8000-000000000002"


def _stats(source_id: str) -> FightStats:
    return FightStats(
        source=SOURCE,
        source_bout_id="fight-1",
        source_fighter_id=source_id,
        fight_duration_seconds=300,
        source_time_format="3 Rnd (5-5-5)",
        knockdowns=0,
        sig_strikes_landed=1,
        sig_strikes_attempted=2,
        takedowns_landed=0,
        takedowns_attempted=1,
        submission_attempts=0,
        control_seconds=None,
        head_landed=1,
        body_landed=0,
        leg_landed=0,
        distance_landed=1,
        clinch_landed=0,
        ground_landed=0,
    )


def _data():
    # The two same-name fighters must remain distinct people.
    profiles = [
        Fighter(SOURCE, "fighter-a", None, "Alex"),
        Fighter(SOURCE, "fighter-b", None, "Alex"),
    ]
    fights = [
        Fight(
            SOURCE,
            "fight-1",
            "Alex",
            "Alex",
            source_fighter_1_id="fighter-a",
            source_fighter_2_id="fighter-b",
            source_winner_label="Draw/NC",
        )
    ]
    stats = [_stats("fighter-a"), _stats("fighter-b")]
    registry = FighterRegistry(
        identities=(
            FighterIdentity(FIRST_ID, "Alex New Name"),
            FighterIdentity(SECOND_ID, "Alex"),
        ),
        provider_links=(
            FighterProviderLink("ufcstats", "fighter-a", FIRST_ID, "Profile URL"),
            FighterProviderLink("ufcstats", "fighter-b", SECOND_ID, "Profile URL"),
        ),
    )
    return profiles, fights, stats, registry


def test_identifies_duplicate_names_and_preserves_source_records():
    profiles, fights, stats, registry = _data()
    identified = identify_historical_data(profiles, fights, stats, registry)

    assert [record.upset_fighter_id for record in identified.profiles] == [
        FIRST_ID,
        SECOND_ID,
    ]
    assert identified.fights[0].upset_fighter_1_id == FIRST_ID
    assert identified.fights[0].upset_fighter_2_id == SECOND_ID
    assert [record.upset_fighter_id for record in identified.fight_stats] == [
        FIRST_ID,
        SECOND_ID,
    ]
    assert identified.fights[0].as_record()["source_winner_label"] == "Draw/NC"
    assert identified.fight_stats[0].as_record()["control_seconds"] is None
    assert "upset_fighter_id" not in asdict(profiles[0])


def test_wrong_provider_does_not_match_even_when_source_id_matches():
    profiles, fights, stats, registry = _data()
    links = tuple(
        FighterProviderLink(
            "cito", link.provider_fighter_id, link.upset_fighter_id, "Cito"
        )
        for link in registry.provider_links
    )
    wrong_registry = FighterRegistry(registry.identities, links)

    with pytest.raises(ValueError, match="Missing ufcstats registry link"):
        identify_historical_data(profiles, fights, stats, wrong_registry)


def test_missing_profile_and_statistics_are_rejected():
    profiles, fights, stats, registry = _data()
    with pytest.raises(ValueError, match="no matching profile"):
        identify_historical_data(profiles[:1], fights, stats, registry)
    with pytest.raises(ValueError, match="Missing fighter-fight statistics"):
        identify_historical_data(profiles, fights, stats[:1], registry)


def test_duplicate_stats_and_self_fight_are_rejected():
    profiles, fights, stats, registry = _data()
    with pytest.raises(ValueError, match="Duplicate historical fight statistics"):
        identify_historical_data(profiles, fights, [*stats, stats[0]], registry)
    same_identity = FighterRegistry(
        registry.identities,
        (
            registry.provider_links[0],
            FighterProviderLink("ufcstats", "fighter-b", FIRST_ID, "Reviewed link"),
        ),
    )
    with pytest.raises(ValueError, match="same identity on both sides"):
        identify_historical_data(profiles, fights, stats, same_identity)


def _write_inputs(tmp_path):
    profiles, fights, stats, registry = _data()
    paths = [
        tmp_path / name
        for name in ("fighters.jsonl", "fights_linked.jsonl", "fight_stats.jsonl")
    ]
    for path, records in zip(paths, (profiles, fights, stats), strict=True):
        path.write_text(
            "".join(json.dumps(asdict(record)) + "\n" for record in records),
            encoding="utf-8",
        )
    registry_path = tmp_path / "fighter_registry.json"
    save_fighter_registry(registry, registry_path)
    return (*paths, registry_path)


def test_export_writes_three_identified_files_and_preserves_inputs(tmp_path):
    inputs = _write_inputs(tmp_path)
    originals = [path.read_bytes() for path in inputs]
    output_dir = tmp_path / "identified"

    assert export_identified_historical(*inputs, output_dir) == (2, 1, 2)

    outputs = [
        [json.loads(line) for line in (output_dir / name).read_text().splitlines()]
        for name in (
            "fighters_identified.jsonl",
            "fights_identified.jsonl",
            "fight_stats_identified.jsonl",
        )
    ]
    assert outputs[0][0]["source_fighter_id"] == "fighter-a"
    assert outputs[0][0]["upset_fighter_id"] == FIRST_ID
    assert outputs[1][0]["upset_fighter_2_id"] == SECOND_ID
    assert outputs[2][1]["upset_fighter_id"] == SECOND_ID
    assert [path.read_bytes() for path in inputs] == originals


def test_invalid_input_keeps_previous_outputs(tmp_path):
    inputs = _write_inputs(tmp_path)
    output_dir = tmp_path / "identified"
    export_identified_historical(*inputs, output_dir)
    previous = {path.name: path.read_bytes() for path in output_dir.iterdir()}
    # Remove one fighter's statistics; reject the entire batch before writing.
    stats_path = inputs[2]
    stats_path.write_text(stats_path.read_text().splitlines()[0] + "\n")

    with pytest.raises(ValueError, match="Missing fighter-fight statistics"):
        export_identified_historical(*inputs, output_dir)
    assert {path.name: path.read_bytes() for path in output_dir.iterdir()} == previous


def test_output_cannot_overwrite_an_input(tmp_path):
    inputs = _write_inputs(tmp_path)
    # The output directory can be any directory; verify a colliding filename.
    profiles_path = tmp_path / "fighters_identified.jsonl"
    profiles_path.write_bytes(inputs[0].read_bytes())
    with pytest.raises(ValueError, match="must not overwrite"):
        export_identified_historical(profiles_path, *inputs[1:], tmp_path)


def test_committed_registry_resolves_real_ufcstats_ids():
    registry_path = (
        Path(__file__).resolve().parents[1] / "data/mappings/fighter_registry.json"
    )
    registry = load_fighter_registry(registry_path)
    links = [link for link in registry.provider_links if link.provider == "ufcstats"]
    first, second = links[:2]
    profiles, fights, stats, _ = _data()
    profiles = [
        replace(profiles[0], source_fighter_id=first.provider_fighter_id),
        replace(profiles[1], source_fighter_id=second.provider_fighter_id),
    ]
    fights = [
        replace(
            fights[0],
            source_fighter_1_id=first.provider_fighter_id,
            source_fighter_2_id=second.provider_fighter_id,
        )
    ]
    stats = [
        replace(stats[0], source_fighter_id=first.provider_fighter_id),
        replace(stats[1], source_fighter_id=second.provider_fighter_id),
    ]

    identified = identify_historical_data(profiles, fights, stats, registry)

    assert [item.upset_fighter_id for item in identified.profiles] == [
        first.upset_fighter_id,
        second.upset_fighter_id,
    ]
    assert [item.upset_fighter_id for item in identified.fight_stats] == [
        first.upset_fighter_id,
        second.upset_fighter_id,
    ]
