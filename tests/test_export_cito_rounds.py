"""Exercise offline round normalization with real Cito field names."""

import json
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from upset.data.export_cito_rounds import export_cito_rounds


def raw_round(fighter: str, number: int) -> dict:
    return {
        "id": f"round-{fighter}-{number}",
        "boutId": "bout-1",
        "fighterSlug": fighter,
        "fighterName": fighter.capitalize(),
        "round": number,
        "knockdowns": 1,
        "significantStrikes": "7 of 27",
        "totalStrikes": "9 of 30",
        "takedowns": "1 of 3",
        "submissionAttempts": 0,
        "reversals": 0,
        "controlTime": "1:13",
        "head": "1 of 20",
        "body": "2 of 2",
        "leg": "4 of 5",
        "distance": "6 of 26",
        "clinch": "0 of 0",
        "ground": "1 of 1",
        "lastSyncedAt": "2026-09-22T01:00:00Z",
    }


def write_bout(folder: Path, rows: list[dict]) -> None:
    (folder / "bout-1.json").write_text(json.dumps({
        "source": "cito", "source_bout_id": "bout-1",
        "response": {"success": True, "data": rows},
    }), encoding="utf-8")


def full_bout() -> list[dict]:
    return [raw_round(fighter, number)
            for fighter in ("alpha", "beta") for number in (1, 2)]


def test_round_export_normalizes_and_is_deterministic():
    with TemporaryDirectory() as folder:
        input_dir = Path(folder) / "raw"
        input_dir.mkdir()
        write_bout(input_dir, list(reversed(full_bout())))
        output = Path(folder) / "processed" / "rounds.jsonl"
        assert export_cito_rounds(input_dir, output) == (1, 4)
        first = output.read_bytes()
        assert export_cito_rounds(input_dir, output) == (1, 4)
        assert output.read_bytes() == first
        rows = [json.loads(line) for line in output.read_text().splitlines()]
        assert [(row["source_fighter_slug"], row["round_number"])
                for row in rows] == [
                    ("alpha", 1), ("beta", 1), ("alpha", 2), ("beta", 2)
                ]
        assert all(row["source"] == "cito" for row in rows)
        assert rows[0]["control_seconds"] == 73
        assert rows[0]["head_landed"] == 1


@pytest.mark.parametrize("change,reason", [
    (lambda rows: rows.append(deepcopy(rows[0])), "Duplicate round"),
    (lambda rows: rows.pop(), "Incomplete"),
    (lambda rows: rows[0].update({"boutId": "other"}), "different bout ID"),
    (lambda rows: rows[0].update({"head": "2 of 20"}), "Invalid row 1"),
    (lambda rows: rows[0].update({"round": 0}), "Invalid row 1"),
    (lambda rows: rows[0].update({"controlTime": "oops"}), "Invalid row 1"),
])
def test_round_export_rejects_bad_bouts_without_replacing_output(change, reason):
    with TemporaryDirectory() as folder:
        input_dir = Path(folder) / "raw"
        input_dir.mkdir()
        output = Path(folder) / "rounds.jsonl"
        output.write_text("existing result\n", encoding="utf-8")
        rows = full_bout()
        change(rows)
        write_bout(input_dir, rows)
        with pytest.raises(ValueError, match=reason):
            export_cito_rounds(input_dir, output)
        assert output.read_text(encoding="utf-8") == "existing result\n"


def test_round_export_rejects_missing_input():
    with TemporaryDirectory() as folder:
        with pytest.raises(ValueError, match="No cached"):
            export_cito_rounds(Path(folder), Path(folder) / "rounds.jsonl")
