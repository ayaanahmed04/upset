"""Check matchup identity, outcome isolation, and safe publication."""

import json
from dataclasses import replace

import pytest

from upset.data.export_matchups import export_matchups
from upset.data.identify_historical import IdentifiedFight
from upset.data.matchups import AMBIGUOUS_OUTCOME, INPUT_FIELDS, build_matchup_rows
from upset.data.models import Fight
from upset.data.prefight_features import PreFightFeatures

SOURCE = "kaggle_ufc_1994_2026"
ALICE = "00000000-0000-4000-8000-000000000001"
BOB = "00000000-0000-4000-8000-000000000002"


def _fight(bout_id="bout-1", *, winner="Alice", date="2020-01-02"):
    return IdentifiedFight(
        Fight(
            source=SOURCE,
            source_bout_id=bout_id,
            fighter_1_name="Alice",
            fighter_2_name="Bob",
            source_fighter_1_id="profile-a",
            source_fighter_2_id="profile-b",
            event_date=date,
            winner_name=winner if winner != "Draw/NC" else None,
            source_winner_label=winner,
        ),
        ALICE,
        BOB,
    )


def _feature(bout_id, fighter_id, **changes):
    base = PreFightFeatures(
        source_bout_id=bout_id,
        event_date="2020-01-02",
        upset_fighter_id=fighter_id,
        prior_fights=2,
        prior_fight_seconds=900,
        sig_strikes_landed_per_minute=3.0,
        sig_strikes_accuracy=0.5,
        takedowns_landed_per_15_minutes=1.0,
        takedown_accuracy=0.5,
        knockdowns_per_15_minutes=0.0,
        submission_attempts_per_15_minutes=1.0,
        control_observed_fraction=0.5,
    )
    return replace(base, **changes)


def _inputs(bout_id="bout-1"):
    a = _feature(bout_id, ALICE)
    b = _feature(
        bout_id,
        BOB,
        prior_fights=1,
        prior_fight_seconds=300,
        sig_strikes_landed_per_minute=2.0,
        sig_strikes_accuracy=None,
        takedowns_landed_per_15_minutes=0.0,
    )
    return _fight(bout_id), [a, b]


def test_stable_id_orientation_and_missing_rates():
    fight, features = _inputs()
    row = build_matchup_rows([fight], list(reversed(features)))[0]

    assert (row.fighter_a_id, row.fighter_b_id) == (ALICE, BOB)
    assert row.target_a_win == 1
    assert row.training_exclusion_reason is None
    assert row.feature_differences["prior_fights_diff"] == 1
    assert row.feature_differences["sig_strikes_landed_per_minute_diff"] == 1.0
    assert row.feature_differences["sig_strikes_accuracy_diff"] is None
    assert set(row.feature_differences) == {f"{name}_diff" for name in INPUT_FIELDS}
    assert "winner" not in row.feature_differences


def test_swapping_source_sides_or_winner_cannot_change_inputs():
    fight, features = _inputs()
    original = build_matchup_rows([fight], features)[0]
    reversed_fight = replace(
        fight,
        fight=replace(
            fight.fight,
            fighter_1_name="Bob",
            fighter_2_name="Alice",
            source_fighter_1_id="profile-b",
            source_fighter_2_id="profile-a",
        ),
        upset_fighter_1_id=BOB,
        upset_fighter_2_id=ALICE,
    )
    swapped = build_matchup_rows([reversed_fight], features)[0]
    assert swapped.fighter_a_id == original.fighter_a_id
    assert swapped.feature_differences == original.feature_differences
    assert swapped.target_a_win == 1

    opposite_result = replace(
        fight,
        fight=replace(fight.fight, winner_name="Bob", source_winner_label="Bob"),
    )
    opposite = build_matchup_rows([opposite_result], features)[0]
    assert opposite.feature_differences == original.feature_differences
    assert opposite.target_a_win == 0


def test_draw_nc_is_preserved_and_debut_rates_stay_missing():
    fight, features = _inputs()
    debut = replace(
        features[1],
        prior_fights=0,
        prior_fight_seconds=0,
        sig_strikes_landed_per_minute=None,
        sig_strikes_accuracy=None,
        takedowns_landed_per_15_minutes=None,
        takedown_accuracy=None,
        knockdowns_per_15_minutes=None,
        submission_attempts_per_15_minutes=None,
        control_observed_fraction=None,
    )
    ambiguous = replace(
        fight,
        fight=replace(fight.fight, winner_name=None, source_winner_label="Draw/NC"),
    )
    row = build_matchup_rows([ambiguous], [features[0], debut])[0]
    assert row.target_a_win is None
    assert row.training_exclusion_reason == AMBIGUOUS_OUTCOME
    assert row.source_winner_label == "Draw/NC"
    assert row.feature_differences["prior_fights_diff"] == 2
    assert row.feature_differences["sig_strikes_landed_per_minute_diff"] is None


@pytest.mark.parametrize("problem", ["duplicate", "missing", "extra", "wrong_date"])
def test_incomplete_or_conflicting_feature_pairs_are_rejected(problem):
    fight, features = _inputs()
    if problem == "duplicate":
        features.append(features[0])
        message = "Duplicate pre-fight feature"
    elif problem == "missing":
        features.pop()
        message = "Missing participant feature"
    elif problem == "extra":
        features.append(_feature("unknown-bout", ALICE))
        message = "Unmatched fighter features"
    else:
        features[0] = replace(features[0], event_date="2020-01-03")
        message = "feature dates differ"
    with pytest.raises(ValueError, match=message):
        build_matchup_rows([fight], features)


def test_ambiguous_names_and_contradictory_results_are_rejected():
    fight, features = _inputs()
    same_name = replace(
        fight,
        fight=replace(fight.fight, fighter_2_name="Alice"),
    )
    with pytest.raises(ValueError, match="Unresolved fight winner"):
        build_matchup_rows([same_name], features)
    bad_draw = replace(fight, fight=replace(fight.fight, source_winner_label="Draw/NC"))
    with pytest.raises(ValueError, match="Contradictory Draw/NC"):
        build_matchup_rows([bad_draw], features)
    absent = replace(fight, fight=replace(fight.fight, winner_name=None))
    with pytest.raises(ValueError, match="Unresolved fight winner"):
        build_matchup_rows([absent], features)


def test_duplicate_bouts_and_invalid_numeric_features_are_rejected():
    fight, features = _inputs()
    with pytest.raises(ValueError, match="Duplicate historical bout"):
        build_matchup_rows([fight, fight], features)
    broken = replace(features[0], sig_strikes_accuracy=float("nan"))
    with pytest.raises(ValueError, match="Invalid sig_strikes_accuracy"):
        build_matchup_rows([fight], [broken, features[1]])
    broken = replace(features[0], prior_fights=0)
    with pytest.raises(ValueError, match="First-fight rates"):
        build_matchup_rows([fight], [broken, features[1]])


def test_export_preserves_inputs_and_previous_output_on_error(tmp_path):
    decisive, features = _inputs()
    ambiguous, other_features = _inputs("bout-2")
    ambiguous = replace(
        ambiguous,
        fight=replace(ambiguous.fight, winner_name=None, source_winner_label="Draw/NC"),
    )
    fights_path = tmp_path / "fights_identified.jsonl"
    features_path = tmp_path / "fighter_features.jsonl"
    fights_path.write_text(
        "".join(json.dumps(row.as_record()) + "\n" for row in [decisive, ambiguous]),
        encoding="utf-8",
    )
    features_path.write_text(
        "".join(
            json.dumps(row.as_record()) + "\n" for row in [*features, *other_features]
        ),
        encoding="utf-8",
    )
    output_path = tmp_path / "out" / "matchups.jsonl"
    originals = (fights_path.read_bytes(), features_path.read_bytes())
    assert export_matchups(fights_path, features_path, output_path) == (2, 1, 1)
    saved = output_path.read_bytes()
    rows = [json.loads(line) for line in saved.splitlines()]
    assert [row["source_bout_id"] for row in rows] == ["bout-1", "bout-2"]
    assert rows[0]["target_a_win"] == 1
    assert rows[1]["target_a_win"] is None
    assert export_matchups(fights_path, features_path, output_path) == (2, 1, 1)
    assert output_path.read_bytes() == saved
    assert (fights_path.read_bytes(), features_path.read_bytes()) == originals

    features_path.write_text(
        "".join(json.dumps(row.as_record()) + "\n" for row in features),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Missing participant feature"):
        export_matchups(fights_path, features_path, output_path)
    assert output_path.read_bytes() == saved


def test_export_rejects_collisions_and_unexpected_fields(tmp_path):
    fight, features = _inputs()
    fights_path = tmp_path / "fights_identified.jsonl"
    features_path = tmp_path / "fighter_features.jsonl"
    fights_path.write_text(json.dumps(fight.as_record()) + "\n", encoding="utf-8")
    features_path.write_text(
        "".join(json.dumps(row.as_record()) + "\n" for row in features),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="must not overwrite"):
        export_matchups(fights_path, features_path, features_path)
    features_path.write_text(json.dumps({**features[0].as_record(), "winner": True}))
    with pytest.raises(ValueError, match="fields do not match"):
        export_matchups(fights_path, features_path, tmp_path / "matchups.jsonl")
