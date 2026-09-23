"""Compare separately cached Cito round and fight-total responses."""

import json
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from upset.data.audit_cito_round_totals import audit_bout


def sample_round(fighter: str, number: int) -> dict:
    return {
        "id": f"round-{fighter}-{number}", "boutId": "bout-1",
        "fighterSlug": fighter, "fighterName": fighter.capitalize(),
        "round": number, "knockdowns": 1, "significantStrikes": "7 of 27",
        "totalStrikes": "9 of 30", "takedowns": "1 of 3",
        "submissionAttempts": 0, "reversals": 0, "controlTime": "1:13",
        "head": "1 of 20", "body": "2 of 2", "leg": "4 of 5",
        "distance": "6 of 26", "clinch": "0 of 0", "ground": "1 of 1",
    }


def sample_total(fighter: str) -> dict:
    return {
        "id": f"total-{fighter}", "boutId": "bout-1",
        "fighterSlug": fighter, "fighterName": fighter.capitalize(),
        "knockdowns": 2, "significantStrikes": "14 of 54",
        "totalStrikes": "18 of 60", "takedowns": "2 of 6",
        "submissionAttempts": 0, "reversals": 0, "controlTime": "2:26",
        "head": "2 of 40", "body": "4 of 4", "leg": "8 of 10",
        "distance": "12 of 52", "clinch": "0 of 0", "ground": "2 of 2",
    }


def write_inputs(folder: Path) -> tuple[Path, Path]:
    rounds_dir = folder / "rounds"
    totals_dir = folder / "totals"
    rounds_dir.mkdir()
    totals_dir.mkdir()
    rounds = [sample_round(fighter, number)
              for fighter in ("alpha", "beta") for number in (1, 2)]
    totals = [sample_total(fighter) for fighter in ("beta", "alpha")]
    (rounds_dir / "bout-1.json").write_text(json.dumps({
        "source": "cito", "source_bout_id": "bout-1",
        "response": {"success": True, "data": rounds},
    }), encoding="utf-8")
    (totals_dir / "bout-1.json").write_text(json.dumps({
        "source": "cito", "source_bout_id": "bout-1",
        "response": {"success": True, "data": {
            "availability": {}, "boutStats": totals,
            "roundStats": list(reversed(deepcopy(rounds))),
        }},
    }), encoding="utf-8")
    return rounds_dir, totals_dir


def alter_totals(path: Path, change) -> None:
    saved = json.loads(path.read_text(encoding="utf-8"))
    change(saved["response"]["data"])
    path.write_text(json.dumps(saved), encoding="utf-8")


def test_rounds_and_fight_totals_match_by_fighter_and_round():
    with TemporaryDirectory() as folder:
        rounds, totals = write_inputs(Path(folder))
        report = audit_bout("bout-1", rounds, totals)
        assert report["comparison"] == "matched"
        assert report["fighters"] == ["alpha", "beta"]
        assert report["round_rows"] == 4
        assert report["fight_total_rows"] == 2
        assert report["fields_per_fighter_compared"] > 10


def test_fight_total_count_mismatch_reports_fighter_and_field():
    with TemporaryDirectory() as folder:
        rounds, totals = write_inputs(Path(folder))
        alter_totals(
            totals / "bout-1.json",
            lambda data: data["boutStats"][0].update({"knockdowns": 3}),
        )
        with pytest.raises(ValueError, match="beta knockdowns: round sum 2"):
            audit_bout("bout-1", rounds, totals)


def test_embedded_round_drift_is_reported_even_if_fight_total_matches():
    with TemporaryDirectory() as folder:
        rounds, totals = write_inputs(Path(folder))
        alter_totals(
            totals / "bout-1.json",
            lambda data: data["roundStats"][0].update({"knockdowns": 0}),
        )
        with pytest.raises(ValueError, match="round endpoint 1, totals endpoint 0"):
            audit_bout("bout-1", rounds, totals)


def test_total_for_different_bout_is_rejected():
    with TemporaryDirectory() as folder:
        rounds, totals = write_inputs(Path(folder))
        alter_totals(
            totals / "bout-1.json",
            lambda data: data["boutStats"][0].update({"boutId": "other"}),
        )
        with pytest.raises(ValueError, match="Invalid cached totals"):
            audit_bout("bout-1", rounds, totals)


def test_missing_round_is_rejected_before_comparison():
    with TemporaryDirectory() as folder:
        rounds, totals = write_inputs(Path(folder))
        alter_totals(
            totals / "bout-1.json", lambda data: data["roundStats"].pop()
        )
        with pytest.raises(ValueError, match="complete round rows"):
            audit_bout("bout-1", rounds, totals)
