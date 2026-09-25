"""Audit all historical pre-fight columns before exporting future features."""

import argparse
import json
import subprocess
from datetime import UTC, datetime
from math import isclose, isnan
from pathlib import Path
from tempfile import TemporaryDirectory

from upset.data.asof_features import ScheduledMatchup, build_asof_features
from upset.data.export_prefight import read_identified
from upset.data.identify_historical import IdentifiedFight, IdentifiedFightStats
from upset.data.identity import load_fighter_registry
from upset.data.models import Fight, FightStats
from upset.data.prefight_ratings import read_rating_history
from upset.data.prefight_recent import read_recent_history
from upset.data.stage_current import ACCEPTED_HISTORICAL_FIGHTS_SHA256
from upset.modeling.baseline import read_matchups
from upset.modeling.defense_ablation import join_defense, read_defensive_history
from upset.modeling.elo_comparison import join_ratings
from upset.modeling.evaluation import _sha256
from upset.modeling.examined_later import EXPECTED_REFERENCE_SHA256, _snapshot
from upset.modeling.frozen_replay import COLUMNS, TRAINING_LAST_DATE
from upset.modeling.prospective_archive import SCHEDULE_FIELDS, _read_jsonl, _utc
from upset.modeling.recent_form import feature_matrix, join_recent


def _historical(inputs: dict[str, Path], reference: Path):
    previous = _snapshot(inputs, reference, EXPECTED_REFERENCE_SHA256)
    if previous["identified_fights_sha256"] != ACCEPTED_HISTORICAL_FIGHTS_SHA256:
        raise ValueError("Historical fight hash differs from the accepted cohort.")
    fights = read_identified(
        inputs["identified_fights"], Fight, IdentifiedFight,
        ("upset_fighter_1_id", "upset_fighter_2_id"),
    )
    stats = read_identified(
        inputs["identified_stats"], FightStats, IdentifiedFightStats,
        ("upset_fighter_id",),
    )
    rows = read_matchups(inputs["matchups"])
    if len(rows) != previous["total_source_bouts"] or (
        max(row.event_date for row in rows) != TRAINING_LAST_DATE
    ):
        raise ValueError("Historical matchup cohort differs from frozen source.")
    return fights, stats, rows, previous


def audit_asof_history(inputs: dict[str, Path], reference: Path) -> dict:
    """Match each of 36 newly reconstructed columns against old saved inputs."""
    fights, stats, rows, previous = _historical(inputs, reference)
    requests = [ScheduledMatchup(row.source_bout_id, row.event_date,
                                 row.fighter_a_id, row.fighter_b_id) for row in rows]
    rebuilt = build_asof_features(fights, stats, requests)
    by_defense = read_defensive_history(inputs["defensive_history"])
    ratings = join_ratings(rows, read_rating_history(inputs["rating_history"]))
    defense = join_defense(rows, by_defense)
    recent = join_recent(
        rows, read_recent_history(inputs["recent_history"]), ratings, by_defense
    )
    old = feature_matrix(rows, defense, ratings, recent, COLUMNS)
    maximum_error = 0.0
    for matchup, values in zip(rows, old, strict=True):
        record = rebuilt[matchup.source_bout_id]
        for name, expected in zip(COLUMNS, values, strict=True):
            actual = record[name]
            if isnan(expected):
                if actual is not None:
                    raise ValueError(f"Historical missingness differs: {matchup.source_bout_id}/{name}")
            elif actual is None or not isclose(
                actual, expected, rel_tol=1e-12, abs_tol=1e-9
            ):
                raise ValueError(f"Historical as-of value differs: {matchup.source_bout_id}/{name}")
            else:
                maximum_error = max(maximum_error, abs(actual - expected))
    if any(_sha256(path) != previous[name + "_sha256"]
           for name, path in inputs.items()):
        raise ValueError("Historical source changed during as-of audit.")
    return {"bouts": len(rows), "fighter_rows": 2 * len(rows),
            "columns": len(COLUMNS), "comparison": "matched",
            "maximum_absolute_error": maximum_error,
            "reference_manifest_sha256": EXPECTED_REFERENCE_SHA256}


def _stage_rows(directory: Path, inputs: dict[str, Path], registry_sha: str):
    manifest_path = directory / "manifest.json"
    report = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (report.get("status") != "partial reviewed completed-fight stage; not model input"
            or report.get("historical_cutoff") != TRAINING_LAST_DATE
            or report.get("input_sha256", {}).get("historical") != _sha256(
                inputs["identified_fights"]
            ) or report.get("input_sha256", {}).get("registry") != registry_sha):
        raise ValueError(f"Current stage source or registry differs: {directory}")
    paths = (directory / "fights_identified.jsonl",
             directory / "fight_stats_identified.jsonl")
    if any(_sha256(path) != report.get("output_sha256", {}).get(key)
           for path, key in zip(paths,
                                ("fights_identified.jsonl", "fight_stats_identified.jsonl"),
                                strict=True)):
        raise ValueError(f"Current stage content changed: {directory}")
    fights = read_identified(paths[0], Fight, IdentifiedFight,
                             ("upset_fighter_1_id", "upset_fighter_2_id"))
    stats = read_identified(paths[1], FightStats, IdentifiedFightStats,
                            ("upset_fighter_id",))
    if (len(fights) != report.get("fights") or len(stats) != report.get("fighter_stats")
            or any(f.fight.event_date <= TRAINING_LAST_DATE for f in fights)
            or any(f.fight.source != report.get("provider") for f in fights)
            or len(stats) != 2 * len(fights)):
        raise ValueError(f"Current stage row count/date/provider differs: {directory}")
    return fights, stats, _sha256(manifest_path)


def export_asof_features(
    inputs: dict[str, Path], reference: Path, registry_path: Path,
    schedule_path: Path, stages: list[Path], output: Path, code_commit: str,
    *, now: datetime | None = None,
) -> dict:
    """Publish outcome-free snapshots; source coverage still needs review."""
    if output.exists() or not stages or len(set(map(Path.resolve, stages))) != len(stages):
        raise ValueError("Output exists or current stages are missing/duplicated.")
    moment = datetime.now(UTC) if now is None else now
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("Feature-export clock needs a timezone.")
    moment = moment.astimezone(UTC)
    audit = audit_asof_history(inputs, reference)
    historical_fights, historical_stats, _, _ = _historical(inputs, reference)
    registry = load_fighter_registry(registry_path)
    links = {(link.provider, link.provider_fighter_id): link.upset_fighter_id
             for link in registry.provider_links}
    registry_sha = _sha256(registry_path)
    schedule = _read_jsonl(schedule_path, SCHEDULE_FIELDS)
    requests = []
    for item in schedule:
        start = _utc(item["scheduled_start_utc"])
        observed = _utc(item["source_observed_at_utc"])
        if (start <= moment or observed > moment or start.date().isoformat()
                <= TRAINING_LAST_DATE or item["fighter_a_id"] >= item["fighter_b_id"]
                or any(links.get((item["provider"], item[f"source_fighter_{side}_id"]))
                       != item[f"fighter_{side}_id"] for side in ("a", "b"))):
            raise ValueError("Future schedule has an invalid date or unreviewed link.")
        requests.append(ScheduledMatchup(
            item["source_bout_id"], start.date().isoformat(),
            item["fighter_a_id"], item["fighter_b_id"],
        ))
    stage_hashes = []
    fights, stats = list(historical_fights), list(historical_stats)
    for directory in stages:
        extra_fights, extra_stats, digest = _stage_rows(directory, inputs, registry_sha)
        saved = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        if _utc(saved["observed_at_utc"]) > moment:
            raise ValueError("Current fight batch was acquired after feature export.")
        fights.extend(extra_fights)
        stats.extend(extra_stats)
        stage_hashes.append(digest)
    built = build_asof_features(fights, stats, requests)
    records = [{"source_bout_id": item["source_bout_id"],
                "fighter_a_id": item["fighter_a_id"],
                "fighter_b_id": item["fighter_b_id"],
                "feature_differences": built[item["source_bout_id"]]}
               for item in schedule]
    if any(_sha256(path) != json.loads((reference / "manifest.json").read_text())[
        name + "_sha256"] for name, path in inputs.items()):
        raise ValueError("Historical files changed during feature export.")
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent, prefix=".upset-asof-") as temp:
        staged = Path(temp) / "features"
        staged.mkdir()
        feature_path = staged / "features.jsonl"
        with feature_path.open("w", encoding="utf-8") as stream:
            for row in records:
                stream.write(json.dumps(row, allow_nan=False, sort_keys=True) + "\n")
        if [json.loads(line) for line in feature_path.read_text().splitlines()] != records:
            raise ValueError("Feature export read-back differs.")
        report = {"status": "exploratory feature snapshot; current source coverage unverified",
                  "code_commit": code_commit, "historical_audit": audit,
                  "registry_sha256": registry_sha,
                  "schedule_sha256": _sha256(schedule_path),
                  "stage_manifest_sha256": stage_hashes,
                  "features_sha256": _sha256(feature_path),
                  "scheduled_bouts": len(records)}
        (staged / "manifest.json").write_text(json.dumps(report, indent=2,
                                                        sort_keys=True) + "\n")
        staged.rename(output)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("audit", "generate"))
    base = Path("data/processed/kaggle_ufc_1994_2026")
    for name, path in {
        "matchups": base / "prefight/matchups.jsonl",
        "defense": base / "prefight/defensive_history_v2.jsonl",
        "ratings": base / "prefight/rating_history_v1.jsonl",
        "recent": base / "prefight/recent_history_v1.jsonl",
        "fights": base / "identified/fights_identified.jsonl",
        "stats": base / "identified/fight_stats_identified.jsonl",
        "historical_registry": Path("data/mappings/fighter_registry.json"),
        "reference": base / "experiments/recent_form_v1",
    }.items():
        parser.add_argument("--" + name.replace("_", "-"), type=Path, default=path)
    parser.add_argument("--registry", type=Path,
                        default=Path("data/mappings/fighter_registry.json"))
    parser.add_argument("--schedule", type=Path)
    parser.add_argument("--stage", action="append", type=Path, default=[])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    inputs = {"matchups": args.matchups, "defensive_history": args.defense,
              "rating_history": args.ratings, "recent_history": args.recent,
              "identified_fights": args.fights, "identified_stats": args.stats,
              "registry": args.historical_registry}
    try:
        if args.action == "audit":
            print(json.dumps(audit_asof_history(inputs, args.reference), indent=2))
        else:
            if args.schedule is None or args.output is None:
                parser.error("generate requires --schedule and --output.")
            commit = subprocess.run(["git", "rev-parse", "HEAD"], check=True,
                                    capture_output=True, text=True).stdout.strip()
            if subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"],
                              check=True, capture_output=True, text=True).stdout.strip():
                parser.error("Commit project code before exporting pre-fight features.")
            print(json.dumps(export_asof_features(
                inputs, args.reference, args.registry, args.schedule, args.stage,
                args.output, commit,
            ), indent=2))
    except (ValueError, OSError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
