import json
from dataclasses import replace

import pytest

from upset.data.export_prefight_features import export_prefight_features
from upset.data.prefight import PreFightSnapshot
from upset.data.prefight_features import build_prefight_features

FIGHTER_ID = "00000000-0000-4000-8000-000000000001"
OPPONENT_ID = "00000000-0000-4000-8000-000000000002"


def _snapshot(**changes) -> PreFightSnapshot:
    return replace(
        PreFightSnapshot(
            source_bout_id="fight-2",
            event_date="2020-01-02",
            upset_fighter_id=FIGHTER_ID,
            prior_fights=2,
            prior_fight_seconds=900,
            prior_sig_strikes_landed=45,
            prior_sig_strikes_attempted=90,
            prior_takedowns_landed=3,
            prior_takedowns_attempted=6,
            prior_knockdowns=1,
            prior_submission_attempts=2,
            prior_control_observed_fights=1,
            prior_control_seconds=30,
        ),
        **changes,
    )


def test_pre_fight_rates_use_only_snapshot_history():
    feature = build_prefight_features([_snapshot()])[0]
    assert feature.prior_fights == 2
    assert feature.prior_fight_seconds == 900
    assert feature.sig_strikes_landed_per_minute == 3.0
    assert feature.sig_strikes_accuracy == 0.5
    assert feature.takedowns_landed_per_15_minutes == 3.0
    assert feature.takedown_accuracy == 0.5
    assert feature.knockdowns_per_15_minutes == 1.0
    assert feature.submission_attempts_per_15_minutes == 2.0
    assert feature.control_observed_fraction == 0.5
    assert "winner" not in feature.as_record()
    assert "control_seconds_per_minute" not in feature.as_record()


def test_zero_prior_fights_have_missing_rates_not_artificial_zeros():
    new_fighter = _snapshot(
        prior_fights=0,
        prior_fight_seconds=0,
        prior_sig_strikes_landed=0,
        prior_sig_strikes_attempted=0,
        prior_takedowns_landed=0,
        prior_takedowns_attempted=0,
        prior_knockdowns=0,
        prior_submission_attempts=0,
        prior_control_observed_fights=0,
        prior_control_seconds=None,
    )
    feature = build_prefight_features([new_fighter])[0]
    assert feature.prior_fights == 0
    assert feature.sig_strikes_landed_per_minute is None
    assert feature.sig_strikes_accuracy is None
    assert feature.takedown_accuracy is None
    assert feature.control_observed_fraction is None


def test_zero_attempts_and_zero_elapsed_time_have_separate_missingness():
    no_attempts = _snapshot(
        prior_sig_strikes_landed=0,
        prior_sig_strikes_attempted=0,
        prior_takedowns_landed=0,
        prior_takedowns_attempted=0,
    )
    feature = build_prefight_features([no_attempts])[0]
    assert feature.sig_strikes_landed_per_minute == 0.0
    assert feature.sig_strikes_accuracy is None
    assert feature.takedowns_landed_per_15_minutes == 0.0
    assert feature.takedown_accuracy is None

    zero_seconds = _snapshot(prior_fight_seconds=0)
    feature = build_prefight_features([zero_seconds])[0]
    assert feature.sig_strikes_landed_per_minute is None
    assert feature.sig_strikes_accuracy == 0.5


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"prior_fights": -1}, "Invalid prior_fights"),
        ({"prior_fights": True}, "Invalid prior_fights"),
        ({"prior_sig_strikes_attempted": 44}, "exceed attempts"),
        ({"prior_takedowns_attempted": 2}, "exceed attempts"),
        ({"prior_control_observed_fights": 3}, "exceed prior fights"),
        ({"prior_control_observed_fights": 0}, "require observed"),
        ({"prior_control_seconds": None}, "must be nonnegative"),
        ({"event_date": "2020-02-30"}, "Invalid snapshot date"),
        (
            {
                "prior_fights": 0,
                "prior_control_observed_fights": 0,
                "prior_control_seconds": None,
            },
            "first fight cannot",
        ),
    ],
)
def test_invalid_snapshot_is_rejected(changes, reason):
    with pytest.raises(ValueError, match=reason):
        build_prefight_features([_snapshot(**changes)])


def test_duplicate_keys_and_empty_history_are_rejected():
    with pytest.raises(ValueError, match="nonempty"):
        build_prefight_features([])
    with pytest.raises(ValueError, match="Duplicate pre-fight snapshot"):
        build_prefight_features([_snapshot(), _snapshot()])


def test_export_is_repeatable_and_bad_input_preserves_existing_output(tmp_path):
    snapshot_path = tmp_path / "prefight_stats.jsonl"
    output_path = tmp_path / "features" / "fighter_features.jsonl"
    pair = [_snapshot(), _snapshot(upset_fighter_id=OPPONENT_ID)]
    snapshot_path.write_text(
        "".join(json.dumps(item.as_record()) + "\n" for item in pair)
    )

    assert export_prefight_features(snapshot_path, output_path) == 2
    original = output_path.read_bytes()
    assert all(
        json.loads(line)["sig_strikes_landed_per_minute"] == 3.0
        for line in original.splitlines()
    )
    assert export_prefight_features(snapshot_path, output_path) == 2
    assert output_path.read_bytes() == original

    snapshot_path.write_text(
        "".join(
            json.dumps(item.as_record()) + "\n"
            for item in [_snapshot(prior_fights=-1), pair[1]]
        )
    )
    with pytest.raises(ValueError, match="Invalid prior_fights"):
        export_prefight_features(snapshot_path, output_path)
    assert output_path.read_bytes() == original

    snapshot_path.write_text(json.dumps(pair[0].as_record()) + "\n")
    with pytest.raises(ValueError, match="Expected two snapshots"):
        export_prefight_features(snapshot_path, output_path)
    assert output_path.read_bytes() == original


def test_export_rejects_conflicting_dates_for_one_bout(tmp_path):
    snapshot_path = tmp_path / "prefight_stats.jsonl"
    snapshot_path.write_text(
        "".join(
            json.dumps(item.as_record()) + "\n"
            for item in [
                _snapshot(),
                _snapshot(upset_fighter_id=OPPONENT_ID, event_date="2020-01-03"),
            ]
        )
    )
    with pytest.raises(ValueError, match="two snapshots on one date"):
        export_prefight_features(snapshot_path, tmp_path / "features.jsonl")


def test_export_rejects_extra_fields_and_input_output_collision(tmp_path):
    snapshot_path = tmp_path / "prefight_stats.jsonl"
    snapshot_path.write_text(json.dumps(_snapshot().as_record()) + "\n")
    with pytest.raises(ValueError, match="must not overwrite"):
        export_prefight_features(snapshot_path, snapshot_path)
    snapshot_path.write_text(
        json.dumps({**_snapshot().as_record(), "future_win": True})
    )
    with pytest.raises(ValueError, match="fields do not match"):
        export_prefight_features(snapshot_path, tmp_path / "features.jsonl")
