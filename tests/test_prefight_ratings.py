"""Known Elo arithmetic, same-day isolation, independent replay, and safe export."""

import json
from dataclasses import replace

import pytest
from test_prefight_defense import ALICE, BOB, _bout

from upset.data.audit_prefight_ratings import audit_prefight_ratings
from upset.data.export_prefight_ratings import export_prefight_ratings
from upset.data.prefight_ratings import (
    build_rating_history,
    read_rating_history,
)

CHARLIE = "00000000-0000-4000-8000-000000000003"


def _index(fights):
    return {
        (r.source_bout_id, r.upset_fighter_id): r for r in build_rating_history(fights)
    }


def test_known_updates_skip_draw_nc_but_count_appearances():
    fights = [
        _bout("first", "2020-01-01"),
        _bout("draw", "2020-02-01", winner=None),
        _bout("second_win", "2020-03-01"),
        _bout("third", "2020-04-01", winner="Bob"),
    ]
    rows = _index(fights)
    assert rows["first", ALICE].rating == 1500
    assert rows["first", BOB].elo_probability == 0.5
    assert rows["draw", ALICE].rating == 1516
    assert rows["draw", BOB].rating == 1484
    assert rows["second_win", ALICE].rating == 1516
    assert rows["second_win", ALICE].prior_fights == 2
    assert rows["second_win", ALICE].prior_decisive_fights == 1
    assert rows["second_win", ALICE].elo_probability == pytest.approx(0.5459219228)
    assert rows["third", ALICE].rating == pytest.approx(1530.53049847)
    assert rows["third", ALICE].rating + rows["third", BOB].rating == 3000
    assert audit_prefight_ratings(fights, rows)["all_rating_rows_checked"] == 8


def test_same_day_tournament_is_order_independent_and_uses_predate_opponents():
    first = _bout("first", "2020-01-01")
    second = replace(_bout("second", "2020-01-01"), upset_fighter_2_id=CHARLIE)
    second = replace(
        second,
        fight=replace(second.fight, fighter_2_name="Charlie", source_fighter_2_id="c"),
    )
    next_day = _bout("next", "2020-01-02")
    rows = _index([first, second, next_day])
    assert _index([next_day, second, first]) == rows
    assert rows["second", ALICE].rating == 1500
    assert rows["second", ALICE].prior_fights == 0
    assert rows["next", ALICE].rating == 1532
    assert rows["next", BOB].rating == 1484
    assert rows["next", ALICE].opponent_rating == 1484
    renamed = replace(first, fight=replace(first.fight, source_bout_id="zzz"))
    assert _index([renamed, second, next_day])["next", ALICE] == rows["next", ALICE]
    audit_prefight_ratings([first, second, next_day], rows)


def test_current_and_future_result_changes_cannot_change_earlier_snapshots():
    fights = [
        _bout("early", "2020-01-01"),
        _bout("current", "2021-01-01"),
        _bout("future", "2022-01-01"),
    ]
    before = _index(fights)
    altered = [
        fights[0],
        _bout("current", "2021-01-01", winner="Bob"),
        _bout("future", "2022-01-01", winner="Bob"),
    ]
    after = _index(altered)
    for key, row in before.items():
        if row.event_date <= "2021-01-01":
            assert row == after[key]
    assert before["future", ALICE].rating != after["future", ALICE].rating


@pytest.mark.parametrize(
    "field,value",
    [
        ("rating", 1500.0),
        ("opponent_rating", 1500.0),
        ("elo_probability", 0.5),
        ("prior_fights", 0),
        ("prior_decisive_fights", 0),
        ("event_date", "2020-03-01"),
        ("opponent_id", CHARLIE),
        ("source_bout_id", "other"),
    ],
)
def test_independent_audit_detects_every_corrupted_field(field, value):
    fights = [_bout("first", "2020-01-01"), _bout("later", "2020-02-01")]
    rows = _index(fights)
    rows["later", ALICE] = replace(rows["later", ALICE], **{field: value})
    with pytest.raises(ValueError, match=field):
        audit_prefight_ratings(fights, rows)


def test_deterministic_export_readback_and_existing_file_preservation(tmp_path):
    source, output = tmp_path / "fights.jsonl", tmp_path / "ratings.jsonl"
    fights = [_bout("first", "2020-01-01"), _bout("later", "2020-02-01")]
    source.write_text("".join(json.dumps(f.as_record()) + "\n" for f in fights))
    assert export_prefight_ratings(source, output) == 4
    first = output.read_bytes()
    export_prefight_ratings(source, output)
    assert output.read_bytes() == first
    assert read_rating_history(output) == _index(fights)
    output.write_text("preserve this existing evidence\n")
    with pytest.raises(ValueError, match="Existing rating history differs"):
        export_prefight_ratings(source, output)
    assert output.read_text() == "preserve this existing evidence\n"
    with pytest.raises(ValueError, match="replace the identified"):
        export_prefight_ratings(source, source)


@pytest.mark.parametrize(
    "change",
    [
        {"rating": float("nan")},
        {"elo_probability": True},
        {"prior_fights": True},
        {"prior_decisive_fights": -1},
        {"extra": 1},
        {"event_date": "20200101"},
        {"opponent_id": ALICE},
        {"rating": 1501.0},
        {"elo_probability": 0.8},
    ],
)
def test_reader_rejects_malformed_records(tmp_path, change):
    row = build_rating_history([_bout("first", "2020-01-01")])[0].as_record()
    row.update(change)
    path = tmp_path / "ratings.jsonl"
    path.write_text(json.dumps(row) + "\n")
    with pytest.raises(ValueError, match="Invalid rating history"):
        read_rating_history(path)


def test_rejects_duplicates_unresolved_labels_and_incomplete_audit(tmp_path):
    fight = _bout("first", "2020-01-01")
    with pytest.raises(ValueError, match="duplicate fight"):
        build_rating_history([fight, fight])
    with pytest.raises(ValueError, match="Unresolved decisive"):
        build_rating_history(
            [replace(fight, fight=replace(fight.fight, source_winner_label="Bob"))]
        )
    with pytest.raises(ValueError, match="Draw/NC has a named winner"):
        build_rating_history(
            [replace(fight, fight=replace(fight.fight, source_winner_label="Draw/NC"))]
        )
    rows = _index([fight])
    rows.pop(("first", BOB))
    with pytest.raises(ValueError, match="Missing rating row"):
        audit_prefight_ratings([fight], rows)
    path = tmp_path / "ratings.jsonl"
    line = json.dumps(next(iter(rows.values())).as_record()) + "\n"
    path.write_text(line * 2)
    with pytest.raises(ValueError, match="Duplicate rating row"):
        read_rating_history(path)
