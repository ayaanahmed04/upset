"""Replay the frozen model on cached completed bouts, never as live forecasts."""

import argparse
import json
import subprocess
from collections import defaultdict
from datetime import UTC, datetime
from math import log
from pathlib import Path
from tempfile import TemporaryDirectory

from upset.data.asof_features import ScheduledMatchup, build_asof_features
from upset.data.build_research_db import rows
from upset.data.collect_cito_archive import _digest
from upset.data.export_asof_features import _historical, _stage_rows, audit_asof_history
from upset.data.export_cito_current_archive import _manifest
from upset.data.identity import load_fighter_registry
from upset.data.reconcile_cito_archive import _write_verified
from upset.modeling.frozen_replay import parse_artifact, probability
from upset.modeling.prospective_archive import _validate_model

EXPECTED_MODEL_SHA256 = "55bf4a6f363c9c45bd3db008b74faab5927318b6614836e440024f52d9c8894c"


def history_gaps(canonical, linked, registry):
    """Report omitted prior bouts without treating missing links as new fighters.

    Direct history is only one dependency: omitted stats also change the global
    recent-rate prior; Elo effects can propagate through subsequent opponents.
    Consequently a lack of direct gaps does not certify feature completeness.
    """
    links = {(r.provider, r.provider_fighter_id): r.upset_fighter_id
             for r in registry.provider_links}
    by_key = {(r["source"], r["source_bout_id"]): r for r in canonical}
    if len(by_key) != len(canonical):
        raise ValueError("Duplicate canonical current bout.")
    accepted = {}
    for item in linked:
        fight = item.fight
        key = (fight.source, fight.source_bout_id)
        if key in accepted or key not in by_key:
            raise ValueError("Identified bout is duplicate or absent from canonical cohort.")
        raw = by_key[key]
        if raw != fight.__dict__ or any(
            links.get((fight.source, raw[f"source_fighter_{side}_id"])) != uid
            for side, uid in ((1, item.upset_fighter_1_id), (2, item.upset_fighter_2_id))
        ):
            raise ValueError("Identified bout or registry differs from canonical cohort.")
        accepted[key] = item
    omitted = [r for k, r in by_key.items() if k not in accepted]
    if any(all((r["source"], r[f"source_fighter_{s}_id"]) in links for s in (1, 2))
           for r in omitted):
        raise ValueError("Canonical linked bout is missing from the identified stage.")
    queue = defaultdict(lambda: {"names": set(), "blocked_bouts": set(),
                                 "directly_affected_replay_bouts": set()})
    diagnostics = {}
    for raw in omitted:
        for side in (1, 2):
            pid = raw[f"source_fighter_{side}_id"]
            if (raw["source"], pid) not in links:
                entry = queue[(raw["source"], pid)]
                entry["names"].add(raw[f"fighter_{side}_name"])
                entry["blocked_bouts"].add(raw["source_bout_id"])
    for key, item in accepted.items():
        fight = item.fight
        ids = sorted((item.upset_fighter_1_id, item.upset_fighter_2_id))
        direct = {uid: [] for uid in ids}
        earlier = [r for r in omitted if r["event_date"] < fight.event_date]
        for raw in earlier:
            known = {links.get((raw["source"], raw[f"source_fighter_{s}_id"])) for s in (1, 2)}
            for uid in ids:
                if uid in known:
                    direct[uid].append(raw["source_bout_id"])
            if set(ids) & known:
                for side in (1, 2):
                    entry = queue.get((raw["source"], raw[f"source_fighter_{side}_id"]))
                    if entry is not None:
                        entry["directly_affected_replay_bouts"].add(fight.source_bout_id)
        diagnostics[key] = {
            "direct_missing_prior_bouts": {uid: sorted(bids) for uid, bids in direct.items()},
            "has_direct_history_gap": any(direct.values()),
            "omitted_cohort_bouts_before_date": len(earlier),
            "population_prior_has_omitted_bouts": bool(earlier),
            "coverage_verified": False,
        }
    priority = [{"provider": provider, "provider_fighter_id": pid,
                 "source_names": sorted(entry["names"]),
                 "blocked_bouts": sorted(entry["blocked_bouts"]),
                 "directly_affected_replay_bouts": sorted(entry["directly_affected_replay_bouts"])}
                for (provider, pid), entry in queue.items()]
    priority.sort(key=lambda r: (-len(r["directly_affected_replay_bouts"]),
                                -len(r["blocked_bouts"]), r["provider_fighter_id"]))
    return diagnostics, priority, omitted


def replay_rows(historical_fights, historical_stats, current_fights, current_stats,
                canonical, registry, artifact):
    gaps, priority, omitted = history_gaps(canonical, current_fights, registry)
    requests = [ScheduledMatchup(r.fight.source_bout_id, r.fight.event_date,
                                 *sorted((r.upset_fighter_1_id, r.upset_fighter_2_id)))
                for r in current_fights]
    features = build_asof_features(historical_fights + current_fights,
                                  historical_stats + current_stats, requests)
    predictions, snapshots = [], []
    for item in sorted(current_fights, key=lambda r: (r.fight.event_date, r.fight.source_bout_id)):
        fight = item.fight
        ids = sorted((item.upset_fighter_1_id, item.upset_fighter_2_id))
        names = {item.upset_fighter_1_id: fight.fighter_1_name,
                 item.upset_fighter_2_id: fight.fighter_2_name}
        values = features[fight.source_bout_id]
        p = probability(artifact, values)
        swapped = {c: v if v is None or c.endswith("_sum") else -v
                   for c, v in values.items()}
        if abs(p + probability(artifact, swapped) - 1) > 1e-12:
            raise ValueError("Current probability symmetry check failed.")
        target = None if fight.winner_name is None else int(fight.winner_name == names[ids[0]])
        common = {"source": fight.source, "source_bout_id": fight.source_bout_id,
                  "event_date": fight.event_date, "fighter_a_id": ids[0], "fighter_b_id": ids[1]}
        snapshots.append({**common, "feature_differences": values})
        predictions.append({**common, "fighter_a_name": names[ids[0]], "fighter_b_name": names[ids[1]],
                            "probability_a_win": p, "target_a_win": target,
                            "history_diagnostics": gaps[(fight.source, fight.source_bout_id)]})
    decisive = [r for r in predictions if r["target_a_win"] is not None]
    metrics = None
    if decisive:
        n = len(decisive)
        correct = sum(int(r["probability_a_win"] >= 0.5) == r["target_a_win"] for r in decisive)
        metrics = {"decisive_bouts": n, "correct_picks": correct, "accuracy": correct / n,
                   "brier": sum((r["probability_a_win"] - r["target_a_win"]) ** 2 for r in decisive) / n,
                   "log_loss": -sum(log(max(1e-15, min(1 - 1e-15,
                       r["probability_a_win"] if r["target_a_win"] else 1 - r["probability_a_win"])))
                       for r in decisive) / n}
    summary = {"replayed_bouts": len(predictions), "excluded_current_bouts": len(omitted),
               "unresolved_provider_fighters": len(priority),
               "replayed_bouts_with_direct_history_gaps": sum(r["history_diagnostics"]["has_direct_history_gap"] for r in predictions),
               "replayed_bouts_after_omitted_history": sum(r["history_diagnostics"]["population_prior_has_omitted_bouts"] for r in predictions),
               "retrospective_diagnostic_metrics": metrics}
    return snapshots, predictions, priority, summary


def export_replay(inputs, reference, current, registry_path, frozen, output, code_commit,
                  *, expected_model_sha256=EXPECTED_MODEL_SHA256, code_worktree_dirty=False):
    if any(output.resolve() == p.resolve() or output.resolve().is_relative_to(p.resolve())
           for p in [*inputs.values(), reference, current, registry_path, frozen]):
        raise ValueError("Replay output overlaps inputs.")
    hashes = {str(p): _digest(p) for p in inputs.values()}
    # Allow ongoing interface edits while binding the Python implementation.
    code_root = Path(__file__).resolve().parents[1]
    hashes.update({str(p): _digest(p) for p in code_root.rglob("*.py")})
    hashes[str(reference / "manifest.json")] = _digest(reference / "manifest.json")
    cm = _manifest(current, hashes)
    for name in ("fights.jsonl", "fight_stats.jsonl", "identified/manifest.json",
                 "identified/fights_identified.jsonl", "identified/fight_stats_identified.jsonl"):
        if name not in cm["output_sha256"]:
            raise ValueError(f"Current replay export is missing a verified output: {name}")
    hashes[str(registry_path)] = _digest(registry_path)
    for name in ("model.bin", "model_spec.json"):
        hashes[str(frozen / name)] = _digest(frozen / name)
    if hashes[str(frozen / "model.bin")] != expected_model_sha256:
        raise ValueError("Frozen artifact differs from the accepted Mac model.")
    spec = _validate_model(frozen / "model_spec.json", frozen / "model.bin")
    artifact = parse_artifact((frozen / "model.bin").read_bytes(), spec)
    if any(_digest(path) != artifact["input_hashes"][name] for name, path in inputs.items()):
        raise ValueError("Replay historical inputs differ from frozen model sources.")
    if output.exists():
        saved = _manifest(output, {})
        if saved["input_sha256"] != hashes or saved["code_commit"] != code_commit:
            raise ValueError("Existing replay differs; use a new output directory.")
        return saved
    audit = audit_asof_history(inputs, reference)
    historical_fights, historical_stats, _, _ = _historical(inputs, reference)
    current_fights, current_stats, stage_sha = _stage_rows(current / "identified", inputs, _digest(registry_path))
    if len(current_fights) != cm["identified_current_bouts"]:
        raise ValueError("Current manifest and identified cohort counts differ.")
    canonical = rows(current / "fights.jsonl")
    if len(canonical) != cm["canonical_current_bouts"]:
        raise ValueError("Canonical current cohort count differs.")
    # Bind each staged stat to the canonical normalized source, including nulls.
    canonical_stats = rows(current / "fight_stats.jsonl")
    source_stats = {(r["source"], r["source_bout_id"], r["source_fighter_id"]): r for r in canonical_stats}
    if len(source_stats) != len(canonical_stats):
        raise ValueError("Duplicate canonical current statistics.")
    for item in current_stats:
        r = item.stats
        if source_stats.get((r.source, r.source_bout_id, r.source_fighter_id)) != r.__dict__:
            raise ValueError("Staged statistics differ from canonical current data.")
    snapshots, predictions, priority, summary = replay_rows(
        historical_fights, historical_stats, current_fights, current_stats,
        canonical, load_fighter_registry(registry_path), artifact)
    if any(_digest(Path(p)) != h for p, h in hashes.items()):
        raise ValueError("Replay input changed during calculation.")
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent, prefix=".upset-current-replay-") as temporary:
        folder = Path(temporary) / "export"
        folder.mkdir()
        for name, batch in (("features.jsonl", snapshots), ("predictions.jsonl", predictions),
                            ("identity_priorities.jsonl", priority)):
            _write_verified(folder / name, batch)
        report = {"schema_version": 1, "status": "retrospective pipeline diagnostic; not prospective evidence",
                  "processed_at_utc": datetime.now(UTC).isoformat(), "code_commit": code_commit,
                  "code_worktree_dirty": code_worktree_dirty,
                  **summary, "historical_audit": audit, "stage_manifest_sha256": stage_sha,
                  "api_calls": 0, "coverage_verified": False, "prospective_evidence": False,
                  "model_retrained": False, "source_availability_reconstructed": False,
                  "limitations": ["Already observed period; selected identity-linked subset, not a fresh holdout.",
                      "Excluded bouts affect direct history, population smoothing and potentially opponent Elo.",
                      "Calendar completeness and historical acquisition times are not established.",
                      "Frozen historical result labels remain unchanged; reviewed amendments are not backdated."],
                  "input_sha256": hashes,
                  "output_sha256": {p.name: _digest(p) for p in folder.iterdir()}}
        (folder / "manifest.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        folder.rename(output)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    base = Path("data/processed/kaggle_ufc_1994_2026")
    parser.add_argument("--current", type=Path, default=Path("data/processed/cito_current_identity_v2"))
    parser.add_argument("--registry", type=Path, default=Path("data/processed/cito_current_identity_v2/fighter_registry.json"))
    parser.add_argument("--frozen", type=Path, default=base / "models/symmetric_recent_elo_v1")
    parser.add_argument("--output", type=Path, default=Path("data/processed/current_replay_v1"))
    args = parser.parse_args()
    inputs = {"matchups": base / "prefight/matchups.jsonl",
              "defensive_history": base / "prefight/defensive_history_v2.jsonl",
              "rating_history": base / "prefight/rating_history_v1.jsonl",
              "recent_history": base / "prefight/recent_history_v1.jsonl",
              "identified_fights": base / "identified/fights_identified.jsonl",
              "identified_stats": base / "identified/fight_stats_identified.jsonl",
              "registry": Path("data/mappings/fighter_registry.json")}
    try:
        dirty = bool(subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"],
                                    capture_output=True, text=True, check=True).stdout.strip())
        commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                                text=True, check=True).stdout.strip()
        report = export_replay(inputs, base / "experiments/recent_form_v1", args.current,
                               args.registry, args.frozen, args.output, commit,
                               code_worktree_dirty=dirty)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(str(error))
    print(json.dumps({k: v for k, v in report.items() if k not in {"input_sha256", "output_sha256", "limitations"}}, indent=2))
    print(f"Saved to: {args.output}")


if __name__ == "__main__":
    main()
