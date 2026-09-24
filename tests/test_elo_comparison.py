"""Exercise complete synthetic source histories through the new experiment."""

import json
from dataclasses import replace

import pytest
from test_prefight_defense import _bout, _pair

from upset.data.matchups import build_matchup_rows
from upset.data.prefight import build_prefight_snapshots
from upset.data.prefight_defense import build_defensive_history
from upset.data.prefight_features import build_prefight_features
from upset.data.prefight_ratings import build_rating_history
from upset.modeling.defense_ablation import compare_defense, export_defense_ablation
from upset.modeling.elo_comparison import (
    BOOSTED_SETTINGS,
    VARIANTS,
    _audit_matchup_sources,
    _preserve_references,
    compare_elo,
    export_elo_comparison,
    join_ratings,
)


@pytest.fixture(scope="module")
def history():
    fights, stats = [], []
    # New participants enter each year. Build true histories from these bouts
    # rather than manually fabricating feature counts that cannot reconcile.
    for year in range(2017, 2025):
        for month in range(1, 9):
            for index in range(3):
                bout = f"{year}-{month}-{index}"
                first = index * 2 + (year - 2017 if month == 1 else 0)
                second = first + 1
                ids = [f"00000000-0000-4000-8000-{i + 1:012d}" for i in (first, second)]
                names = [f"Fighter {i}" for i in (first, second)]
                ambiguous = year == 2022 and month == 2 and index == 0
                winner = None if ambiguous else names[(year + month + index) % 2]
                template = _bout(bout, f"{year}-{month:02d}-01")
                fight = replace(
                    template,
                    upset_fighter_1_id=ids[0],
                    upset_fighter_2_id=ids[1],
                    fight=replace(
                        template.fight,
                        fighter_1_name=names[0],
                        fighter_2_name=names[1],
                        source_fighter_1_id=str(first),
                        source_fighter_2_id=str(second),
                        winner_name=winner,
                        source_winner_label=winner or "Draw/NC",
                        weight_class="Lightweight" if index % 2 else "Welterweight",
                    ),
                )
                fights.append(fight)
                pair = _pair(
                    bout,
                    a_sig=month + index,
                    b_sig=month,
                    a_kd=index % 2,
                    b_kd=month % 2,
                )
                for side, row in enumerate(pair):
                    stats.append(
                        replace(
                            row,
                            upset_fighter_id=ids[side],
                            stats=replace(
                                row.stats, source_fighter_id=str((first, second)[side])
                            ),
                        )
                    )
    snapshots = build_prefight_snapshots(fights, stats)
    features = build_prefight_features(list(snapshots))
    matchups = build_matchup_rows(fights, list(features))
    defense = {
        (r.source_bout_id, r.upset_fighter_id): r
        for r in build_defensive_history(fights, stats)
    }
    ratings = {
        (r.source_bout_id, r.upset_fighter_id): r for r in build_rating_history(fights)
    }
    return matchups, defense, ratings, fights


@pytest.fixture(scope="module")
def comparison(history):
    rows, defense, ratings, _ = history
    return compare_elo(rows, defense, ratings)


def test_exact_references_identical_cohort_and_complete_diagnostics(
    history, comparison
):
    rows, defense, _, _ = history
    references, _ = compare_defense(rows, defense)
    predictions, report = comparison
    assert [r["source_bout_id"] for r in predictions] == [
        r["source_bout_id"] for r in references
    ]
    assert report["decisive_bouts"] == 95
    assert report["draw_nc_exclusions"] == 1
    for row, original in zip(predictions, references, strict=True):
        p = row["probabilities_a_win"]
        assert set(p) == set(VARIANTS)
        assert p["baseline"] == original["baseline_probability_a_win"]
        assert p["all_defense"] == original["defense_probability_a_win"]
        assert all(value is None for value in p.values()) == (
            row["target_a_win"] is None
        )
        assert row["event_date"] <= "2023-08-19"
    for scores in report["pooled"].values():
        assert scores["decisive_bouts"] == 95
    for bins in report["reliability_deciles"].values():
        assert sum(b["count"] for b in bins) == 95
    for group in report["subgroups"].values():
        assert sum(v["coverage"] for v in group.values()) == pytest.approx(1)
    assert report["symmetry"]["elo_only"]["maximum_absolute_error"] < 1e-12
    assert len(report["paired_comparisons"]) == 5
    assert BOOSTED_SETTINGS["early_stopping"] is False
    assert BOOSTED_SETTINGS["max_iter"] == 150


def test_later_results_and_extreme_future_features_cannot_change_development(
    history, comparison
):
    rows, defense, _, fights = history
    altered = []
    for row in rows:
        if row.event_date > "2023-08-19":
            values = dict(row.feature_differences)
            values["sig_strikes_landed_per_minute_diff"] = 1e9
            row = replace(
                row, feature_differences=values, target_a_win=1 - row.target_a_win
            )
        altered.append(row)
    changed_fights = [
        replace(
            f,
            fight=replace(
                f.fight,
                winner_name=f.fight.fighter_2_name,
                source_winner_label=f.fight.fighter_2_name,
            ),
        )
        if f.fight.event_date > "2023-08-19"
        else f
        for f in fights
    ]
    new_ratings = {
        (r.source_bout_id, r.upset_fighter_id): r
        for r in build_rating_history(changed_fights)
    }
    assert compare_elo(tuple(altered), defense, new_ratings) == comparison


def test_join_requires_complete_ids_opponents_dates_and_counts(history):
    rows, defense, ratings, _ = history
    key = rows[0].source_bout_id, rows[0].fighter_a_id
    bad = dict(ratings)
    bad.pop(key)
    with pytest.raises(ValueError, match="join keys"):
        join_ratings(rows, bad)
    bad = dict(ratings)
    bad[key] = replace(bad[key], event_date="2016-01-01")
    with pytest.raises(ValueError, match="dates differ"):
        join_ratings(rows, bad)
    bad[key] = replace(ratings[key], opponent_id=rows[0].fighter_a_id)
    with pytest.raises(ValueError, match="opponent mismatch"):
        join_ratings(rows, bad)
    bad[key] = replace(ratings[key], prior_fights=10)
    with pytest.raises(ValueError, match="appearance counts"):
        compare_elo(rows, defense, bad)


def test_matchup_targets_are_checked_against_source_fights(history):
    rows, _, _, fights = history
    altered = (replace(rows[0], target_a_win=1 - rows[0].target_a_win), *rows[1:])
    with pytest.raises(ValueError, match="identity/date/target"):
        _audit_matchup_sources(altered, fights)


def test_preserved_reference_cannot_silently_drift(history):
    rows, defense, _, _ = history
    saved, _ = compare_defense(rows, defense)
    assert _preserve_references(saved, list(reversed(saved))) == saved
    changed = [dict(r) for r in saved]
    changed[0]["baseline_probability_a_win"] += 0.01
    with pytest.raises(ValueError, match="Saved reference differs"):
        _preserve_references(saved, changed)
    with pytest.raises(ValueError, match="cohort differs"):
        _preserve_references(saved, saved[:-1])


def test_export_audits_preserves_inputs_and_never_overwrites_experiments(
    tmp_path, history
):
    rows, defense, ratings, fights = history
    matchups, defenses = tmp_path / "matchups.jsonl", tmp_path / "defenses.jsonl"
    rating_path, sources = tmp_path / "ratings.jsonl", tmp_path / "fights.jsonl"
    registry = tmp_path / "registry.json"
    reference, output = tmp_path / "reference", tmp_path / "new"
    for path, items in (
        (matchups, rows),
        (defenses, defense.values()),
        (rating_path, ratings.values()),
        (sources, fights),
    ):
        path.write_text("".join(json.dumps(r.as_record()) + "\n" for r in items))
    registry.write_text('{"synthetic_fixture": true}\n')
    export_defense_ablation(
        matchups, defenses, registry, reference, "reference-fixture"
    )
    originals = {
        p: p.read_bytes()
        for p in (
            matchups,
            defenses,
            rating_path,
            sources,
            registry,
            reference / "predictions.jsonl",
            reference / "manifest.json",
        )
    }
    manifest = export_elo_comparison(
        matchups,
        defenses,
        rating_path,
        sources,
        registry,
        reference,
        output,
        "new-fixture",
    )
    assert manifest == json.loads((output / "manifest.json").read_text())
    assert manifest["rating_audit"]["all_rating_rows_checked"] == len(ratings)
    assert manifest["rating_audit"]["all_numeric_fields_recomputed"]
    assert len(manifest["predictions_sha256"]) == 64
    assert len(manifest["weight_class_scores"]) == 2
    assert manifest["reference_code_commit"] == "reference-fixture"
    predictions = [
        json.loads(line)
        for line in (output / "predictions.jsonl").read_text().splitlines()
    ]
    saved = [
        json.loads(line)
        for line in (reference / "predictions.jsonl").read_text().splitlines()
    ]
    for row, old in zip(predictions, saved, strict=True):
        assert (
            row["probabilities_a_win"]["baseline"] == old["baseline_probability_a_win"]
        )
        assert (
            row["probabilities_a_win"]["all_defense"]
            == old["defense_probability_a_win"]
        )
    assert all(p.read_bytes() == data for p, data in originals.items())
    with pytest.raises(ValueError, match="already exists"):
        export_elo_comparison(
            matchups,
            defenses,
            rating_path,
            sources,
            registry,
            reference,
            output,
            "rerun-fixture",
        )
    reference_manifest = json.loads((reference / "manifest.json").read_text())
    reference_manifest["matchups_sha256"] = "wrong"
    (reference / "manifest.json").write_text(json.dumps(reference_manifest))
    rejected = tmp_path / "rejected"
    with pytest.raises(ValueError, match="input hash differs"):
        export_elo_comparison(
            matchups,
            defenses,
            rating_path,
            sources,
            registry,
            reference,
            rejected,
            "new-fixture",
        )
    assert not rejected.exists()
