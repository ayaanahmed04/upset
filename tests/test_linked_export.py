import json
from dataclasses import asdict
from pathlib import Path

import pytest

from upset.data.export_linked import export_linked_fights
from upset.data.models import Fight, Fighter


@pytest.fixture
def input_files(tmp_path):
    source = "kaggle_ufc_1994_2026"

    fight = Fight(
        source=source,
        source_bout_id="fight-1",
        fighter_1_name="Alex",
        fighter_2_name="Sam",
        event_date="2020-01-01",
        source_winner_label="Draw/NC",
    )

    profiles = [
        Fighter(source, "profile-a", None, "Alex"),
        Fighter(source, "profile-b", None, "Sam"),
        Fighter(source, "profile-c", None, "Alex"),
    ]

    mapping = {
        "schema_version": 1,
        "source": source,
        "overrides": [
            {
                "source": source,
                "source_bout_id": "fight-1",
                "fighter_side": 1,
                "fighter_name": "Alex",
                "source_fighter_id": "profile-c",
                "event_date": "2020-01-01",
                "opponent_name": "Sam",
            }
        ],
    }

    fights_path = tmp_path / "fights.jsonl"
    profiles_path = tmp_path / "fighters.jsonl"
    mappings_path = tmp_path / "overrides.json"

    fights_path.write_text(
        json.dumps(asdict(fight)) + "\n",
        encoding="utf-8",
    )
    profiles_path.write_text(
        "".join(json.dumps(asdict(profile)) + "\n" for profile in profiles),
        encoding="utf-8",
    )
    mappings_path.write_text(json.dumps(mapping), encoding="utf-8")

    return fights_path, profiles_path, mappings_path


def test_exports_linked_fights_without_changing_inputs(tmp_path, input_files):
    original_bytes = [path.read_bytes() for path in input_files]
    output_path = tmp_path / "processed" / "fights_linked.jsonl"

    count = export_linked_fights(*input_files, output_path)

    records = [
        json.loads(line)
        for line in output_path.read_text(encoding="utf-8").splitlines()
    ]

    assert count == len(records) == 1
    assert records[0]["source_fighter_1_id"] == "profile-c"
    assert records[0]["source_fighter_2_id"] == "profile-b"
    assert records[0]["winner_name"] is None
    assert records[0]["source_winner_label"] == "Draw/NC"
    assert [path.read_bytes() for path in input_files] == original_bytes


@pytest.mark.parametrize(
    ("problem", "message"),
    [
        ("unresolved", "Unresolved participant"),
        ("bad_schema", "Unsupported mapping version"),
        ("malformed_json", "Expecting"),
    ],
)
def test_failed_export_preserves_existing_file(
    tmp_path, input_files, problem, message
):
    fights_path, _, mappings_path = input_files
    output_path = tmp_path / "fights_linked.jsonl"
    previous_export = '{"previous": "successful export"}\n'
    output_path.write_text(previous_export, encoding="utf-8")

    if problem == "malformed_json":
        fights_path.write_text("{broken json\n", encoding="utf-8")
    else:
        mapping = json.loads(mappings_path.read_text(encoding="utf-8"))

        if problem == "unresolved":
            mapping["overrides"] = []
        else:
            mapping["schema_version"] = 2

        mappings_path.write_text(json.dumps(mapping), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        export_linked_fights(*input_files, output_path)

    assert output_path.read_text(encoding="utf-8") == previous_export


@pytest.mark.parametrize("input_index", [0, 1, 2])
def test_cannot_overwrite_any_input(input_files, input_index):
    output_path: Path = input_files[input_index]
    original_bytes = [path.read_bytes() for path in input_files]

    with pytest.raises(ValueError, match="must not overwrite"):
        export_linked_fights(*input_files, output_path)

    assert [path.read_bytes() for path in input_files] == original_bytes