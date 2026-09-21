import csv
import json

import pytest

from upset.data.export_profiles import export_historical_profiles


@pytest.fixture
def profile_row():
    return {
        "Fighter_Name": "Example Fighter",
        "Fighter_URL": (
            "http://ufcstats.com/fighter-details/0000000000000001"
        ),
        "Height": "5' 11\"",
        "Weight": "155 lbs.",
        "Reach": "",
        "Stance": "Orthodox",
        "DOB": "1990-02-28",
    }


def write_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as source_file:
        writer = csv.DictWriter(source_file, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


def test_exports_same_name_profiles_with_distinct_ids(tmp_path, profile_row):
    input_path = tmp_path / "raw.csv"
    output_path = tmp_path / "processed" / "fighters.jsonl"

    second_row = {
        **profile_row,
        "Fighter_URL": (
            "http://ufcstats.com/fighter-details/0000000000000002"
        ),
    }
    write_csv(input_path, [profile_row, second_row])
    original_bytes = input_path.read_bytes()

    count = export_historical_profiles(input_path, output_path)

    records = [
        json.loads(line)
        for line in output_path.read_text(encoding="utf-8").splitlines()
    ]

    assert count == len(records) == 2
    assert records[0]["name"] == records[1]["name"]
    assert [record["source_fighter_id"] for record in records] == [
        "0000000000000001",
        "0000000000000002",
    ]
    assert records[0]["height_inches"] == 71.0
    assert records[0]["reach_inches"] is None
    assert records[0]["source_fighter_slug"] is None
    assert records[0]["date_of_birth"] == "1990-02-28"
    assert records[0]["source"] == "kaggle_ufc_1994_2026"
    assert records[0]["source_url"] == profile_row["Fighter_URL"]
    assert input_path.read_bytes() == original_bytes


@pytest.mark.parametrize("problem", ["invalid_date", "duplicate_id"])
def test_bad_input_preserves_existing_export(tmp_path, profile_row, problem):
    input_path = tmp_path / "raw.csv"
    output_path = tmp_path / "fighters.jsonl"

    second_row = profile_row.copy()
    if problem == "invalid_date":
        second_row["DOB"] = "1990-02-30"

    write_csv(input_path, [profile_row, second_row])

    previous_export = '{"previous": "successful export"}\n'
    output_path.write_text(previous_export, encoding="utf-8")

    with pytest.raises(ValueError, match="Profile validation failed"):
        export_historical_profiles(input_path, output_path)

    assert output_path.read_text(encoding="utf-8") == previous_export


def test_empty_input_creates_no_export(tmp_path):
    input_path = tmp_path / "raw.csv"
    output_path = tmp_path / "fighters.jsonl"
    input_path.write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="no profile records"):
        export_historical_profiles(input_path, output_path)

    assert not output_path.exists()


def test_cannot_overwrite_input(tmp_path, profile_row):
    input_path = tmp_path / "raw.csv"
    write_csv(input_path, [profile_row])
    original_bytes = input_path.read_bytes()

    with pytest.raises(ValueError, match="must not overwrite"):
        export_historical_profiles(input_path, input_path)

    assert input_path.read_bytes() == original_bytes