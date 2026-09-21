import csv
import json
from dataclasses import asdict, replace

import pytest

from upset.data.export_fight_stats import (
    export_historical_fight_stats,
    load_linked_fights,
)
from upset.data.normalization import normalize_kaggle_fight


def _raw_fight() -> dict:
    """Return one complete historical fight row."""

    return {
        "Fight_URL": (
            "http://ufcstats.com/fight-details/4acab67848e78327"
        ),
        "Fighter_1": "Scott Morris",
        "Fighter_2": "Sean Daugherty",
        "Winner": "Scott Morris",
        "Weight_Class": "Open Weight Bout",
        "Method": "Submission",
        "End_Round": 1,
        "End_Time": "0:20",
        "Total_Fight_Time_Sec": 20,
        "Time_Format": "No Time Limit",
        "Event_Date": "1999-05-07",
        "F1_KD": 0,
        "F2_KD": 0,
        "F1_Sig_Landed": 1,
        "F1_Sig_Att": 2,
        "F2_Sig_Landed": 0,
        "F2_Sig_Att": 1,
        "F1_TD_Landed": 0,
        "F2_TD_Landed": 0,
        "F1_TD_Att": 1,
        "F2_TD_Att": 0,
        "F1_Sub_Att": 1,
        "F2_Sub_Att": 0,
        "F1_Ctrl_Sec": 0,
        "F2_Ctrl_Sec": 0,
        "F1_Head": 1,
        "F2_Head": 0,
        "F1_Body": 0,
        "F2_Body": 0,
        "F1_Leg": 0,
        "F2_Leg": 0,
        "F1_Distance": 0,
        "F2_Distance": 0,
        "F1_Clinch": 1,
        "F2_Clinch": 0,
        "F1_Ground": 0,
        "F2_Ground": 0,
    }


def _linked_fight(raw_fight: dict):
    """Return the normalized fight with participant IDs attached."""

    return replace(
        normalize_kaggle_fight(raw_fight),
        source_fighter_1_id="fighter-1",
        source_fighter_2_id="fighter-2",
    )


def _write_raw_fights(path, fights: list[dict]) -> None:
    """Write raw test fights using the source CSV format."""

    with path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as output_file:
        writer = csv.DictWriter(
            output_file,
            fieldnames=list(fights[0]),
        )
        writer.writeheader()
        writer.writerows(fights)


def _write_linked_fights(path, fights) -> None:
    """Write typed linked fights as JSON Lines."""

    with path.open(
        "w",
        encoding="utf-8",
        newline="\n",
    ) as output_file:
        for fight in fights:
            output_file.write(
                json.dumps(asdict(fight))
                + "\n"
            )


def test_export_writes_verified_fighter_fight_records(tmp_path):
    raw_fight = _raw_fight()

    raw_path = tmp_path / "raw.csv"
    linked_path = tmp_path / "linked.jsonl"
    output_path = tmp_path / "fight_stats.jsonl"

    _write_raw_fights(raw_path, [raw_fight])
    _write_linked_fights(
        linked_path,
        [_linked_fight(raw_fight)],
    )

    count = export_historical_fight_stats(
        raw_path,
        linked_path,
        output_path,
    )

    records = [
        json.loads(line)
        for line in output_path.read_text(
            encoding="utf-8"
        ).splitlines()
    ]

    assert count == 2
    assert len(records) == 2

    assert records[0]["source_bout_id"] == "4acab67848e78327"
    assert records[0]["source_fighter_id"] == "fighter-1"
    assert records[1]["source_fighter_id"] == "fighter-2"

    # Missing Python values must survive JSON as null.
    assert records[0]["control_seconds"] is None
    assert records[1]["control_seconds"] is None


def test_invalid_raw_data_does_not_replace_existing_output(tmp_path):
    raw_fight = _raw_fight()
    raw_fight["F1_Sig_Att"] = 0

    raw_path = tmp_path / "raw.csv"
    linked_path = tmp_path / "linked.jsonl"
    output_path = tmp_path / "fight_stats.jsonl"

    _write_raw_fights(raw_path, [raw_fight])
    _write_linked_fights(
        linked_path,
        [_linked_fight(raw_fight)],
    )

    existing_contents = '{"existing": true}\n'
    output_path.write_text(
        existing_contents,
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="fight-stat validation failed",
    ):
        export_historical_fight_stats(
            raw_path,
            linked_path,
            output_path,
        )

    assert output_path.read_text(
        encoding="utf-8"
    ) == existing_contents


def test_rejects_missing_linked_fight(tmp_path):
    raw_fight = _raw_fight()
    unrelated_fight = replace(
        _linked_fight(raw_fight),
        source_bout_id="unrelated-fight",
    )

    raw_path = tmp_path / "raw.csv"
    linked_path = tmp_path / "linked.jsonl"
    output_path = tmp_path / "fight_stats.jsonl"

    _write_raw_fights(raw_path, [raw_fight])
    _write_linked_fights(
        linked_path,
        [unrelated_fight],
    )

    with pytest.raises(
        ValueError,
        match="No linked fight found",
    ):
        export_historical_fight_stats(
            raw_path,
            linked_path,
            output_path,
        )

    assert not output_path.exists()


def test_rejects_unused_linked_fight(tmp_path):
    raw_fight = _raw_fight()
    linked_fight = _linked_fight(raw_fight)
    extra_fight = replace(
        linked_fight,
        source_bout_id="unused-fight",
    )

    raw_path = tmp_path / "raw.csv"
    linked_path = tmp_path / "linked.jsonl"
    output_path = tmp_path / "fight_stats.jsonl"

    _write_raw_fights(raw_path, [raw_fight])
    _write_linked_fights(
        linked_path,
        [linked_fight, extra_fight],
    )

    with pytest.raises(
        ValueError,
        match="not present in the raw dataset",
    ):
        export_historical_fight_stats(
            raw_path,
            linked_path,
            output_path,
        )


def test_rejects_duplicate_linked_fight_ids(tmp_path):
    raw_fight = _raw_fight()
    linked_fight = _linked_fight(raw_fight)
    linked_path = tmp_path / "linked.jsonl"

    _write_linked_fights(
        linked_path,
        [linked_fight, linked_fight],
    )

    with pytest.raises(
        ValueError,
        match="Duplicate linked fight ID",
    ):
        load_linked_fights(linked_path)


def test_rejects_linked_fight_from_unexpected_source(tmp_path):
    raw_fight = _raw_fight()
    linked_fight = replace(
        _linked_fight(raw_fight),
        source="cito",
    )
    linked_path = tmp_path / "linked.jsonl"

    _write_linked_fights(
        linked_path,
        [linked_fight],
    )

    with pytest.raises(
        ValueError,
        match="unexpected source",
    ):
        load_linked_fights(linked_path)


def test_refuses_to_overwrite_an_input_file(tmp_path):
    raw_fight = _raw_fight()

    raw_path = tmp_path / "raw.csv"
    linked_path = tmp_path / "linked.jsonl"

    _write_raw_fights(raw_path, [raw_fight])
    _write_linked_fights(
        linked_path,
        [_linked_fight(raw_fight)],
    )

    with pytest.raises(
        ValueError,
        match="must not overwrite",
    ):
        export_historical_fight_stats(
            raw_path,
            linked_path,
            raw_path,
        )


def test_requires_jsonl_output(tmp_path):
    raw_fight = _raw_fight()

    raw_path = tmp_path / "raw.csv"
    linked_path = tmp_path / "linked.jsonl"
    output_path = tmp_path / "fight_stats.csv"

    _write_raw_fights(raw_path, [raw_fight])
    _write_linked_fights(
        linked_path,
        [_linked_fight(raw_fight)],
    )

    with pytest.raises(
        ValueError,
        match="must use the .jsonl extension",
    ):
        export_historical_fight_stats(
            raw_path,
            linked_path,
            output_path,
        )