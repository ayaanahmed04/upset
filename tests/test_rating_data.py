"""Paired rating data preserves chronology, reviewed results and count meaning."""

import json
import sqlite3

import pytest
from test_research_app import A, B, add_same_date_historical_bout, build, fixture

from upset.ratings.data import digest, load_bouts


def database(tmp_path, *, same_day=False):
    paths = fixture(tmp_path)
    if same_day:
        paths = add_same_date_historical_bout(paths)
    out = tmp_path / "research"
    build(paths, out)
    return out / "upset.sqlite"


def edit_unbound(original, tmp_path, table, identity, changes):
    folder = tmp_path / "unbound"
    folder.mkdir()
    target = folder / "upset.sqlite"
    target.write_bytes(original.read_bytes())
    with sqlite3.connect(target) as db:
        key = "id" if table == "fights" else "fighter_id"
        raw = json.loads(db.execute(f"SELECT payload FROM {table} WHERE {key}=? LIMIT 1", (identity,)).fetchone()[0])
        raw.update(changes)
        db.execute(f"UPDATE {table} SET payload=? WHERE {key}=?", (json.dumps(raw), identity))
    return target


def test_adapter_preserves_source_bytes_cutoff_missing_control_and_reviewed_results(tmp_path):
    path = database(tmp_path)
    inputs = {p: digest(p) for p in path.parent.iterdir() if p.is_file()}
    empty, empty_meta = load_bouts(path, "2026-03-07")
    assert empty == [] and empty_meta["latest_event"] is None
    rows, metadata = load_bouts(path, "2026-09-20")
    assert len(rows) == 1 and rows[0]["fighter_ids"] == [A, B]
    assert rows[0]["winner_id"] is None and rows[0]["outcome"] == "nc"
    assert rows[0]["reviewed_outcome"] and rows[0]["method_group"] == "other"
    assert all(stat["control_seconds"] is None for stat in rows[0]["stats"])
    assert rows[0]["stats"][0]["sig_strikes_landed"] == 60
    assert metadata["missing_control_sides"] == 2
    assert metadata["database_sha256"] == inputs[path]
    assert metadata["fighter_labels"][A] == "Alex Silva"
    assert "currently reviewed" in metadata["interpretation"]
    assert all(digest(p) == value for p, value in inputs.items())
    with (sqlite3.connect(path.resolve().as_uri() + "?mode=ro&immutable=1", uri=True) as db,
          pytest.raises(sqlite3.OperationalError, match="readonly")):
        db.execute("DELETE FROM fighters")


def test_same_date_bouts_remain_one_date_batch_in_stable_order(tmp_path):
    path = database(tmp_path, same_day=True)
    rows, metadata = load_bouts(path, "2026-03-08")
    assert [r["fight_id"] for r in rows] == ["kaggle:old", "kaggle:rematch"]
    assert {r["event_date"] for r in rows} == {"2026-03-07"}
    assert metadata["fighter_stat_rows"] == 4


def test_current_winner_uses_permanent_id_and_division_preserves_sex(tmp_path):
    path = database(tmp_path)
    changed = edit_unbound(path, tmp_path, "fights", "cito:new",
                           {"weight_class": "UFC Women's Flyweight Title Bout"})
    rows, _ = load_bouts(changed, "2026-09-21")
    row = rows[-1]
    assert row["winner_id"] == A and row["outcome"] == "decisive"
    assert row["division"] == "Women's Flyweight" and row["method_group"] == "decision"
    assert rows[0]["division"] is None


@pytest.mark.parametrize("changes,match", [
    ({"sig_strikes_attempted": 1}, "exceeds attempts"),
    ({"takedowns_landed": -1}, "Invalid count"),
    ({"knockdowns": True}, "Invalid count"),
    ({"ground_landed": 999}, "breakdown differs"),
    ({"control_seconds": 601}, "control duration"),
    ({"control_seconds": False}, "control duration"),
    ({"fight_duration_seconds": -1}, "fight duration"),
    ({"upset_fighter_id": B}, "participant identity"),
])
def test_invalid_or_mismatched_counts_never_silently_coerce(tmp_path, changes, match):
    path = database(tmp_path)
    changed = edit_unbound(path, tmp_path, "stats", A, changes)
    with pytest.raises(ValueError, match=match):
        load_bouts(changed, "2026-03-08")


def test_hash_mismatch_and_unresolved_winner_fail_closed(tmp_path):
    path = database(tmp_path)
    manifest = path.parent / "manifest.json"
    metadata = json.loads(manifest.read_text())
    metadata["database_sha256"] = "wrong"
    manifest.write_text(json.dumps(metadata))
    with pytest.raises(ValueError, match="hash differs"):
        load_bouts(path, "2026-11-04")
    changed = edit_unbound(path, tmp_path, "fights", "cito:new", {"winner_name": "Unknown person"})
    with pytest.raises(ValueError, match="uniquely identify"):
        load_bouts(changed, "2026-11-04")


@pytest.mark.parametrize("before", ["2026-3-07", "2026-02-30", None])
def test_noncanonical_dates_rejected(tmp_path, before):
    path = database(tmp_path)
    with pytest.raises((ValueError, TypeError)):
        load_bouts(path, before)


def test_missing_pair_rejected_and_unknown_outcome_is_not_a_draw(tmp_path):
    path = database(tmp_path)
    changed = edit_unbound(path, tmp_path, "fights", "cito:new",
                           {"winner_name": None, "result_method": "Could Not Continue"})
    rows, _ = load_bouts(changed, "2026-11-04")
    assert rows[-1]["outcome"] == "other" and rows[-1]["winner_id"] is None
    with sqlite3.connect(changed) as db:
        db.execute("DELETE FROM stats WHERE fight_id='cito:new' AND fighter_id=?", (B,))
    with pytest.raises(ValueError, match="exactly two"):
        load_bouts(changed, "2026-11-04")
