import json
from dataclasses import replace

import pytest

from upset.data.export_prefight import export_prefight_stats
from upset.data.identify_historical import IdentifiedFight, IdentifiedFightStats
from upset.data.models import Fight, FightStats
from upset.data.prefight import build_prefight_snapshots

SOURCE = "kaggle_ufc_1994_2026"
IDS = {
    name: f"00000000-0000-4000-8000-{index:012d}"
    for index, name in enumerate("ABCD", 1)
}


def _fight(bout: str, day: str, fighter: str, opponent: str) -> IdentifiedFight:
    return IdentifiedFight(
        Fight(
            source=SOURCE,
            source_bout_id=bout,
            fighter_1_name=fighter,
            fighter_2_name=opponent,
            source_fighter_1_id=fighter,
            source_fighter_2_id=opponent,
            event_date=day,
        ),
        IDS[fighter],
        IDS[opponent],
    )


def _stats(
    bout: str, fighter: str, landed: int, control: int | None
) -> IdentifiedFightStats:
    return IdentifiedFightStats(
        FightStats(
            source=SOURCE,
            source_bout_id=bout,
            source_fighter_id=fighter,
            fight_duration_seconds=300,
            source_time_format="3 Rnd (5-5-5)",
            knockdowns=0,
            sig_strikes_landed=landed,
            sig_strikes_attempted=landed + 10,
            takedowns_landed=1,
            takedowns_attempted=2,
            submission_attempts=0,
            control_seconds=control,
            head_landed=landed,
            body_landed=0,
            leg_landed=0,
            distance_landed=landed,
            clinch_landed=0,
            ground_landed=0,
        ),
        IDS[fighter],
    )


def _history():
    # A appears twice on the same day. Neither fight can see the other's result.
    fights = [
        _fight("later", "2020-01-03", "A", "D"),
        _fight("day-two", "2020-01-02", "A", "C"),
        _fight("day-one", "2020-01-02", "A", "B"),
    ]
    stats = [
        _stats("later", "A", 30, 0),
        _stats("later", "D", 4, 5),
        _stats("day-two", "A", 20, 12),
        _stats("day-two", "C", 3, None),
        _stats("day-one", "A", 10, None),
        _stats("day-one", "B", 2, None),
    ]
    return fights, stats


def test_same_day_results_are_excluded_and_earlier_results_are_summed():
    fights, stats = _history()
    snapshots = build_prefight_snapshots(fights, stats)
    same_day = [s for s in snapshots if s.event_date == "2020-01-02"]
    assert len(same_day) == 4
    assert all(s.prior_fights == 0 for s in same_day)
    assert all(s.prior_control_seconds is None for s in same_day)

    later_a = next(
        s
        for s in snapshots
        if s.source_bout_id == "later" and s.upset_fighter_id == IDS["A"]
    )
    assert later_a.prior_fights == 2
    assert later_a.prior_fight_seconds == 600
    assert later_a.prior_sig_strikes_landed == 30
    assert later_a.prior_sig_strikes_attempted == 50
    assert later_a.prior_takedowns_landed == 2
    assert later_a.prior_control_observed_fights == 1
    assert later_a.prior_control_seconds == 12
    assert all(s.prior_fights == 0 for s in snapshots if s.upset_fighter_id == IDS["D"])
    assert snapshots == build_prefight_snapshots(
        list(reversed(fights)), list(reversed(stats))
    )


def test_zero_control_is_observed_but_missing_control_is_not():
    fights, stats = _history()
    third = _fight("third", "2020-01-04", "A", "B")
    snapshots = build_prefight_snapshots(
        [*fights, third],
        [*stats, _stats("third", "A", 1, None), _stats("third", "B", 1, 0)],
    )
    later_a = next(
        s
        for s in snapshots
        if s.source_bout_id == "third" and s.upset_fighter_id == IDS["A"]
    )
    assert later_a.prior_control_observed_fights == 2
    assert later_a.prior_control_seconds == 12
    prior_b = next(
        s
        for s in snapshots
        if s.source_bout_id == "third" and s.upset_fighter_id == IDS["B"]
    )
    assert prior_b.prior_fights == 1
    assert prior_b.prior_control_seconds is None


@pytest.mark.parametrize("bad_day", [None, "2020-02-30", "2020-1-2"])
def test_invalid_event_dates_are_rejected(bad_day):
    fights, stats = _history()
    fights[0] = replace(fights[0], fight=replace(fights[0].fight, event_date=bad_day))
    with pytest.raises(ValueError, match="Invalid event date"):
        build_prefight_snapshots(fights, stats)


def test_missing_duplicate_or_mismatched_statistics_are_rejected():
    fights, stats = _history()
    with pytest.raises(ValueError, match="Missing fight statistics"):
        build_prefight_snapshots(fights, stats[:-1])
    with pytest.raises(ValueError, match="Duplicate or unexpected"):
        build_prefight_snapshots(fights, [*stats, stats[0]])
    wrong = replace(stats[0], upset_fighter_id=IDS["B"])
    with pytest.raises(ValueError, match="identities differ"):
        build_prefight_snapshots(fights, [wrong, *stats[1:]])
    with pytest.raises(ValueError, match="Invalid sig_strikes_landed"):
        build_prefight_snapshots(
            fights,
            [
                replace(stats[0], stats=replace(stats[0].stats, sig_strikes_landed=-1)),
                *stats[1:],
            ],
        )


def test_export_is_repeatable_and_preserves_previous_file_after_invalid_input(tmp_path):
    fights, stats = _history()
    fights_path = tmp_path / "fights_identified.jsonl"
    stats_path = tmp_path / "fight_stats_identified.jsonl"
    for path, rows in ((fights_path, fights), (stats_path, stats)):
        path.write_text(
            "".join(json.dumps(row.as_record()) + "\n" for row in rows),
            encoding="utf-8",
        )
    output = tmp_path / "prefight" / "prefight_stats.jsonl"

    assert export_prefight_stats(fights_path, stats_path, output) == 6
    first = output.read_bytes()
    records = [json.loads(line) for line in output.read_text().splitlines()]
    assert len(records) == 6
    assert records[-2]["prior_fights"] == 2
    assert export_prefight_stats(fights_path, stats_path, output) == 6
    assert output.read_bytes() == first
    stats_path.write_text(
        "".join(json.dumps(row.as_record()) + "\n" for row in stats[:-1]),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Missing fight statistics"):
        export_prefight_stats(fights_path, stats_path, output)
    assert output.read_bytes() == first


def test_export_rejects_output_collisions_and_unknown_fields(tmp_path):
    fights, stats = _history()
    fights_path = tmp_path / "fights_identified.jsonl"
    stats_path = tmp_path / "fight_stats_identified.jsonl"
    fights_path.write_text(
        "".join(json.dumps(row.as_record()) + "\n" for row in fights)
    )
    stats_path.write_text("".join(json.dumps(row.as_record()) + "\n" for row in stats))
    with pytest.raises(ValueError, match="must not overwrite"):
        export_prefight_stats(fights_path, stats_path, stats_path)
    invalid = {**fights[0].as_record(), "unexpected": True}
    fights_path.write_text(json.dumps(invalid) + "\n")
    with pytest.raises(ValueError, match="fields do not match"):
        export_prefight_stats(fights_path, stats_path, tmp_path / "output.jsonl")
