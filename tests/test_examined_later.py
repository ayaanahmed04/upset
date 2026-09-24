"""Historical stress test with frozen inputs and forecasts before scoring."""

import json
from dataclasses import replace

import pytest
import test_recent_form as shared_fixtures

from upset.data.matchups import AMBIGUOUS_OUTCOME
from upset.modeling.defense_ablation import export_defense_ablation
from upset.modeling.elo_comparison import export_elo_comparison
from upset.modeling.evaluation import DEVELOPMENT_LAST_DATE, _sha256
from upset.modeling.examined_later import (
    COMPARATOR,
    MODEL,
    _forecast_rows,
    export_forecasts,
    score_forecasts,
)
from upset.modeling.recent_form import export_recent_form

history = shared_fixtures.history
recent = shared_fixtures.recent
stats = shared_fixtures.stats


@pytest.fixture(scope="module")
def snapshot(tmp_path_factory, request):
    folder = tmp_path_factory.mktemp("examined-later")
    rows, defense, ratings, fights = request.getfixturevalue("history")
    recent_rows = request.getfixturevalue("recent")
    stat_rows = request.getfixturevalue("stats")
    # The final date contains one Draw/NC; forecasts must still cover it.
    final = next(r for r in rows if r.event_date == "2024-08-01")
    rows = tuple(
        replace(
            r, target_a_win=None, source_winner_label="Draw/NC",
            training_exclusion_reason=AMBIGUOUS_OUTCOME,
        ) if r.source_bout_id == final.source_bout_id else r
        for r in rows
    )
    fights = [
        replace(
            f,
            fight=replace(
                f.fight, winner_name=None, source_winner_label="Draw/NC"
            ),
        ) if f.fight.source_bout_id == final.source_bout_id else f
        for f in fights
    ]
    inputs = {
        name: folder / f"{name}.jsonl"
        for name in (
            "matchups", "defensive_history", "rating_history", "recent_history",
            "identified_fights", "identified_stats",
        )
    }
    inputs["registry"] = folder / "registry.json"
    for name, records in (
        ("matchups", rows),
        ("defensive_history", defense.values()),
        ("rating_history", ratings.values()),
        ("recent_history", recent_rows.values()),
        ("identified_fights", fights),
        ("identified_stats", stat_rows),
    ):
        inputs[name].write_text(
            "".join(json.dumps(record.as_record()) + "\n" for record in records)
        )
    inputs["registry"].write_text('{"fixture": true}\n')
    base, elo, reference = (folder / name for name in ("base", "elo", "recent"))
    export_defense_ablation(
        inputs["matchups"], inputs["defensive_history"], inputs["registry"],
        base, "synthetic-base",
    )
    export_elo_comparison(
        inputs["matchups"], inputs["defensive_history"],
        inputs["rating_history"], inputs["identified_fights"],
        inputs["registry"], base, elo, "synthetic-elo",
    )
    export_recent_form(
        inputs["matchups"], inputs["defensive_history"],
        inputs["rating_history"], inputs["recent_history"],
        inputs["identified_fights"], inputs["identified_stats"],
        inputs["registry"], elo, reference, "synthetic-recent",
    )
    return inputs, reference, rows, defense, ratings, recent_rows, fights, final


def test_forecast_is_outcome_free_includes_draw_and_is_time_separated(
    tmp_path, snapshot,
):
    inputs, reference, rows, _, _, _, _, final = snapshot
    output = tmp_path / "forecasts"
    expected = _sha256(reference / "manifest.json")
    report = export_forecasts(
        inputs, reference, output, "committed-fixture",
        expected_reference_sha256=expected,
    )
    forecasts = [json.loads(line) for line in (output / "forecasts.jsonl").open()]
    assert report == json.loads((output / "manifest.json").read_text())
    assert report["training_decisive_bouts"] == sum(
        r.target_a_win is not None and r.event_date <= DEVELOPMENT_LAST_DATE
        for r in rows
    )
    assert report["forecast_bouts"] == 24
    assert report["forecasts_sha256"] == _sha256(output / "forecasts.jsonl")
    assert {r["source_bout_id"] for r in forecasts} == {
        r.source_bout_id for r in rows if r.event_date > DEVELOPMENT_LAST_DATE
    }
    assert all(r["event_date"] > DEVELOPMENT_LAST_DATE for r in forecasts)
    assert all(
        "target_a_win" not in r and "exclusion_reason" not in r
        and set(r["probabilities_a_win"]) == {MODEL, COMPARATOR}
        for r in forecasts
    )
    assert next(
        r for r in forecasts if r["source_bout_id"] == final.source_bout_id
    )["probabilities_a_win"][MODEL] is not None
    assert all(
        abs(r["probabilities_a_win"][name]
            + r["swapped_probabilities_b_win"][name] - 1) < 1e-12
        for r in forecasts for name in (MODEL, COMPARATOR)
    )
    with pytest.raises(ValueError, match="Output exists"):
        export_forecasts(
            inputs, reference, output, "again", expected_reference_sha256=expected
        )


def test_later_labels_cannot_change_forecasts(snapshot):
    _, _, rows, defense, ratings, recent_rows, fights, _ = snapshot
    unchanged, count = _forecast_rows(rows, defense, ratings, recent_rows, fights)
    flipped = tuple(
        replace(r, target_a_win=1-r.target_a_win)
        if r.event_date > DEVELOPMENT_LAST_DATE and r.target_a_win is not None
        else r for r in rows
    )
    changed, changed_count = _forecast_rows(
        flipped, defense, ratings, recent_rows, fights
    )
    assert count == changed_count
    assert unchanged == changed


def test_frozen_source_mismatch_is_rejected_before_publication(tmp_path, snapshot):
    inputs, reference, *_ = snapshot
    output = tmp_path / "rejected"
    with pytest.raises(ValueError, match="Reference manifest hash"):
        export_forecasts(inputs, reference, output, "fixture")
    assert not output.exists()
    registry = inputs["registry"]
    altered = tmp_path / "registry.json"
    altered.write_bytes(registry.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="Frozen source hash differs: registry"):
        export_forecasts(
            {**inputs, "registry": altered}, reference, output, "fixture",
            expected_reference_sha256=_sha256(reference / "manifest.json"),
        )
    assert not output.exists()


def test_score_uses_saved_forecasts_and_rejects_changes(tmp_path, snapshot):
    inputs, reference, *_ = snapshot
    output = tmp_path / "forecasts"
    expected = _sha256(reference / "manifest.json")
    export_forecasts(
        inputs, reference, output, "fixture",
        expected_reference_sha256=expected,
    )
    forecast = output / "forecasts.jsonl"
    unchanged = forecast.read_bytes()
    forecast.write_bytes(unchanged + b"\n")
    with pytest.raises(ValueError, match="Forecast or frozen-source evidence"):
        score_forecasts(
            output, inputs["matchups"], inputs["identified_fights"], reference,
            expected_reference_sha256=expected,
        )
    assert not (output / "scored").exists()
    forecast.write_bytes(unchanged)
    report = score_forecasts(
        output, inputs["matchups"], inputs["identified_fights"], reference,
        expected_reference_sha256=expected,
    )
    scored = [
        json.loads(line) for line in (output / "scored/scored_predictions.jsonl").open()
    ]
    assert report == json.loads((output / "scored/manifest.json").read_text())
    assert report["validation_bouts"] == 24
    assert report["draw_nc_exclusions"] == 1
    assert report["decisive_bouts"] == 23
    assert report["forecasts_sha256"] == _sha256(forecast)
    assert report["scored_predictions_sha256"] == _sha256(
        output / "scored/scored_predictions.jsonl"
    )
    assert sum(r["target_a_win"] is None for r in scored) == 1
    assert sum(r["probabilities_a_win"][MODEL] is not None for r in scored) == 24
    assert set(report["pooled"]) == {MODEL, COMPARATOR}
    assert sum(v["count"] for v in report["reliability_deciles"][MODEL]) == 23
    assert set(report["year_scores"]) == {"2024"}
    assert all(
        0 <= v["ten_bin_expected_calibration_error"] <= 1
        for v in report["calibration"].values()
    )
    with pytest.raises(ValueError, match="already exists"):
        score_forecasts(
            output, inputs["matchups"], inputs["identified_fights"], reference,
            expected_reference_sha256=expected,
        )
