import csv
import json

import pytest

from upset.data.export_historical import export_historical_fights


@pytest.fixture
def historical_row():
    """One valid fight, with an ID whose leading zeros must survive."""
    return {
        "Fight_URL": "http://ufcstats.com/fight-details/0000000000000001",
        "Fighter_1": "Fighter One",
        "Fighter_2": "Fighter Two",
        "Winner": "Draw/NC",
        "Weight_Class": "Lightweight",
        "Method": "Other",
        "End_Round": "3",
        "End_Time": "5:00",
        "Event_Date": "2020-01-01",
    }


def write_csv(path, rows):
    """Create a small source CSV for a test."""
    with path.open("w", encoding="utf-8", newline="") as source_file:
        writer = csv.DictWriter(source_file, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


def test_export_preserves_values(tmp_path, historical_row):
    input_path = tmp_path / "raw.csv"
    output_path = tmp_path / "processed" / "fights.jsonl"
    write_csv(input_path, [historical_row])
    original_bytes = input_path.read_bytes()

    count = export_historical_fights(input_path, output_path)

    lines = output_path.read_text(encoding="utf-8").splitlines()
    assert count == len(lines) == 1

    record = json.loads(lines[0])
    assert record["source_bout_id"] == "0000000000000001"
    assert record["winner_name"] is None
    assert record["source_winner_label"] == "Draw/NC"
    assert record["source_fighter_1_id"] is None
    assert record["result_round"] == 3
    assert record["source"] == "kaggle_ufc_1994_2026"
    assert record["source_url"] == historical_row["Fight_URL"]

    # Exporting must never change the source CSV.
    assert input_path.read_bytes() == original_bytes


@pytest.mark.parametrize("problem", ["invalid_winner", "duplicate_id"])
def test_bad_input_preserves_existing_export(
    tmp_path, historical_row, problem
):
    input_path = tmp_path / "raw.csv"
    output_path = tmp_path / "fights.jsonl"

    second_row = historical_row.copy()
    if problem == "invalid_winner":
        second_row["Winner"] = "Unknown Fighter"
        expected_error = "Winner must match"
    else:
        expected_error = "Duplicate fight ID"

    write_csv(input_path, [historical_row, second_row])

    # Represent a file left behind by an earlier successful export.
    previous_export = '{"previous": "successful export"}\n'
    output_path.write_text(previous_export, encoding="utf-8")

    with pytest.raises(ValueError, match=expected_error):
        export_historical_fights(input_path, output_path)

    assert output_path.read_text(encoding="utf-8") == previous_export


def test_empty_input_creates_no_export(tmp_path):
    input_path = tmp_path / "raw.csv"
    output_path = tmp_path / "fights.jsonl"
    input_path.write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="no fight records"):
        export_historical_fights(input_path, output_path)

    assert not output_path.exists()


def test_cannot_overwrite_input(tmp_path, historical_row):
    input_path = tmp_path / "raw.csv"
    write_csv(input_path, [historical_row])
    original_bytes = input_path.read_bytes()

    with pytest.raises(ValueError, match="must not overwrite"):
        export_historical_fights(input_path, input_path)

    assert input_path.read_bytes() == original_bytes