"""Freeze the retained baseline and prohibit early prospective score peeking."""

import argparse
import hashlib
import json
import platform
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import scipy

from upset.skill.defense_opponent import audit
from upset.skill.defense_opponent_pilot import (
    attempt_group,
    fighter_weights,
    weighted_interval,
)
from upset.skill.defense_validation import augment, cluster_interval
from upset.skill.defense_variability import diagnostic
from upset.skill.takedown_defense import digest

CONFIG = {"version": "td_defense_prospective_v1", "seed_before_exclusive": "2026-10-26",
          "start_inclusive": "2026-10-27", "end_exclusive": "2027-10-27",
          "strength": 25, "concentration": 5, "clip": 1e-6,
          "primary_minimum": 500, "subgroup_minimum": 100, "minimum_dates": 20,
          "public_release": False, "opponent_adjusted": False}
MODELS = ("candidate", "raw_career", "raw_last5", "binomial")
REFERENCES = ("raw_career", "raw_last5")


def utcnow():
    return datetime.now(UTC)


def versions():
    return {"python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__}


def atomic_output(output, files):
    if output.exists():
        raise ValueError("Use a new immutable output directory.")
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent, prefix=".upset-prospective-") as temporary:
        folder = Path(temporary) / "artifact"
        folder.mkdir()
        for name, contents in files.items():
            body = contents if isinstance(contents, bytes) else contents.encode()
            (folder / name).write_bytes(body)
            if (folder / name).read_bytes() != body:
                raise ValueError("Artifact read-back verification failed.")
        folder.rename(output)


def encoded(value):
    return json.dumps(value, indent=2, sort_keys=True)+"\n"


def load_adapter(adapter):
    manifest_path, sides = adapter / "manifest.json", adapter / "sides.jsonl"
    manifest_bytes, sides_bytes = manifest_path.read_bytes(), sides.read_bytes()
    manifest = json.loads(manifest_bytes)
    database = Path(manifest["input_database"])
    database_hash = digest(database)
    if (hashlib.sha256(sides_bytes).hexdigest() != manifest["output_sha256"]["sides.jsonl"]
            or database_hash != manifest["input_sha256"]["database_sha256"]):
        raise ValueError("Adapter/database hash mismatch.")
    rows = [json.loads(line) for line in sides_bytes.splitlines()]
    before = manifest["before_exclusive"]
    date.fromisoformat(before)
    if len(rows) != manifest["side_rows"] or any(
            r["event_date"] >= before or r["database_sha256"] != manifest["input_sha256"]["database_sha256"]
            for r in rows):
        raise ValueError("Adapter cutoff/count/provenance mismatch.")
    audit(rows, before)
    hashes = {str(manifest_path.resolve()): hashlib.sha256(manifest_bytes).hexdigest(),
              str(sides.resolve()): hashlib.sha256(sides_bytes).hexdigest(),
              str(database.resolve()): database_hash}
    if any(digest(Path(p)) != expected for p, expected in hashes.items()):
        raise ValueError("Adapter changed while reading.")
    return rows, manifest, hashes


def freeze(adapter, protocol, output):
    if output.exists():
        raise ValueError("Use a new immutable output directory.")
    if utcnow().date().isoformat() >= CONFIG["start_inclusive"]:
        raise ValueError("A protected freeze must precede the future block.")
    rows, metadata, hashes = load_adapter(adapter)
    if metadata["before_exclusive"] != CONFIG["seed_before_exclusive"]:
        raise ValueError("Unexpected seed cutoff.")
    source = Path(__file__).resolve()
    dependencies = list(source.parent.glob("*.py"))
    dependencies.append(source.parents[1] / "data" / "identity.py")
    frozen = {str(p.resolve()): digest(p) for p in (*dependencies, protocol)}
    body = (adapter / "sides.jsonl").read_bytes()
    if (hashlib.sha256(body).hexdigest() != metadata["output_sha256"]["sides.jsonl"]
            or any(digest(Path(p)) != expected for p, expected in hashes.items())):
        raise ValueError("Seed changed while freezing.")
    manifest = {"config": CONFIG, "created_at_utc": utcnow().isoformat(), "versions": versions(),
                "input_sha256": hashes, "frozen_dependencies_sha256": frozen,
                "seed_sha256": digest(adapter / "sides.jsonl"), "seed_sides": len(rows),
                "seed_latest_event": max(r["event_date"] for r in rows), "public_release": False}
    atomic_output(output, {"manifest.json": encoded(manifest), "seed.jsonl": body,
                           "protocol.md": protocol.read_bytes(), "config.json": encoded(CONFIG)})
    # Bind local copies too; no later mutation is needed.
    return manifest


def load_freeze(folder):
    manifest = json.loads((folder / "manifest.json").read_text())
    if (manifest["config"] != CONFIG or json.loads((folder / "config.json").read_text()) != CONFIG
            or manifest["versions"] != versions() or digest(folder / "seed.jsonl") != manifest["seed_sha256"]):
        raise ValueError("Frozen config, environment or seed changed.")
    if datetime.fromisoformat(manifest["created_at_utc"]).date().isoformat() >= CONFIG["start_inclusive"]:
        raise ValueError("Freeze was created too late.")
    for path, expected in manifest["frozen_dependencies_sha256"].items():
        if digest(Path(path)) != expected:
            raise ValueError(f"Frozen source/protocol changed: {path}")
    protocol_hashes = [value for path, value in manifest["frozen_dependencies_sha256"].items() if path.endswith('.md')]
    if len(protocol_hashes) != 1 or digest(folder / "protocol.md") != protocol_hashes[0]:
        raise ValueError("Frozen protocol copy changed.")
    seed = [json.loads(line) for line in (folder / "seed.jsonl").read_text().splitlines()]
    if len(seed) != manifest["seed_sides"]:
        raise ValueError("Frozen seed count changed.")
    return seed, manifest


def compatible(seed, latest):
    def key(row):
        return row["fight_id"], row["fighter_id"]

    previous = {key(r): r for r in seed}
    current = {key(r): r for r in latest}
    if len(previous) != len(seed) or len(current) != len(latest) or not previous.keys() <= current.keys():
        raise ValueError("Duplicate or deleted historical side.")
    for identity, old in previous.items():
        new = current[identity]
        if ({k: v for k, v in old.items() if k != "database_sha256"}
                != {k: v for k, v in new.items() if k != "database_sha256"}):
            raise ValueError("Historical measurements/identity/provenance changed.")
    additions = [r for k, r in current.items() if k not in previous]
    if any(r["event_date"] < CONFIG["start_inclusive"] for r in additions):
        raise ValueError("New historical/gap-day observations invalidate this freeze.")
    return additions


def status(folder, adapter):
    seed, frozen = load_freeze(folder)
    latest, metadata, hashes = load_adapter(adapter)
    additions = compatible(seed, latest)
    future = [r for r in additions if r["event_date"] < CONFIG["end_exclusive"]]
    now = utcnow().date().isoformat()
    return {"status": "pending_future_block" if now < CONFIG["end_exclusive"] else "awaiting_finalization_review",
            "checked_at_utc": utcnow().isoformat(), "block": CONFIG,
            "seed_sides": frozen["seed_sides"], "new_block_sides": len(future),
            "new_block_dates": len({r["event_date"] for r in future}),
            "adapter_before_exclusive": metadata["before_exclusive"], "adapter_sha256": hashes,
            "history_compatible": True, "scores_computed": False, "public_release": False}


def predict(rows):
    """Reuse tested date batching; exclude post-block outcomes before prediction."""
    included = [r for r in rows if r["event_date"] < CONFIG["end_exclusive"]]
    paired = {(r["fight_id"], r["fighter_id"]): r for r in included}
    output = []
    for r in augment(included):
        if r["event_date"] < CONFIG["start_inclusive"]:
            continue
        raw, last = r["raw_career"], r["raw_last5"]
        candidate = r["global25"]
        output.append({**paired[r["fight_id"], r["fighter_id"]], **r,
                       "primary": r["status"] == "observed" and raw is not None and last is not None and candidate is not None,
                       "candidate": candidate, "binomial": candidate,
                       "clipped": {model: value is not None and not CONFIG["clip"] <= value <= 1-CONFIG["clip"]
                                   for model, value in (("candidate", candidate), ("raw_career", raw), ("raw_last5", last))}})
    return output


def summarize(rows, models, minimum):
    if not rows:
        return {"side_bouts": 0, "status": "inconclusive_empty", "models": {}, "comparisons": {}}
    enough = len(rows) >= minimum and len({r["event_date"] for r in rows}) >= 20
    reports, losses = {}, {}
    for model in models:
        data = [{**r, "global25": float(np.clip(r[model], 1e-6, 1-1e-6))} for r in rows]
        family = "global_binomial" if model == "binomial" else "global_bout_variability"
        reports[model], losses[model] = diagnostic(data, family, 5, minimum)
    dates = [r["event_date"] for r in rows]
    weights = fighter_weights(rows)
    comparisons, flags = {}, []
    for reference in REFERENCES:
        if reference not in models:
            continue
        differences = {key: losses["candidate"][key]-losses[reference][key] for key in ("nll", "normalized_rps")}
        differences.update({f"interval_score_{level}": losses["candidate"]["interval_scores"][level]-losses[reference]["interval_scores"][level]
                            for level in ("0.5", "0.9")})
        comparisons[reference] = {key: {"date_bootstrap": cluster_interval(value, dates),
                                      "fighter_sensitivity": weighted_interval(value, weights)}
                                  for key, value in differences.items()}
        difference = comparisons[reference]["nll"]["date_bootstrap"]
        if enough and difference["mean"] > .05 and difference["interval_95"][0] > 0:
            flags.append(reference)
    return {"side_bouts": len(rows), "date_clusters": len(set(dates)), "models": reports,
            "comparisons": comparisons, "material_regression_flags": flags,
            "status": "sized_for_diagnostic" if enough else "inconclusive_thin_group"}


def evaluation(rows):
    primary = [r for r in rows if r["primary"]]
    report = {"primary": summarize(primary, MODELS, 500), "subgroups": {}}
    for field, label in (("division", lambda r: r["division"] or "unknown"),
                         ("year", lambda r: r["event_date"][:4]),
                         ("prior_attempts", lambda r: "0" if r["prior_attempts"] == 0 else "1-9" if r["prior_attempts"] < 10 else "10-24" if r["prior_attempts"] < 25 else "25+"),
                         ("attempts", lambda r: attempt_group(r["attempts"]))):
        report["subgroups"][field] = {name: summarize([r for r in primary if label(r) == name], MODELS, 100)
                                        for name in sorted({label(r) for r in primary})}
    positive = [r for r in rows if r["status"] == "observed" and r["candidate"] is not None]
    report["broader_positive"] = summarize(positive, ("candidate", "binomial"), 500)
    report["zero_prior_attempts"] = summarize([r for r in positive if r["prior_attempts"] == 0], ("candidate", "binomial"), 500)
    failures = []
    main = report["primary"]
    if main["status"] != "sized_for_diagnostic":
        failures.append("primary_inconclusive")
    for reference, values in main["comparisons"].items():
        if (values["nll"]["date_bootstrap"]["mean"] >= 0
                or any(values["nll"][method]["interval_95"][1] >= 0 for method in ("date_bootstrap", "fighter_sensitivity"))):
            failures.append(f"nll_evidence:{reference}")
        if values["normalized_rps"]["date_bootstrap"]["mean"] > 0:
            failures.append(f"rps_nonworsening:{reference}")
    for name, group in (("overall", main), ("attempts10+", report["subgroups"]["attempts"].get("10+", {}))):
        if group.get("status") != "sized_for_diagnostic":
            failures.append(f"calibration_inconclusive:{name}")
        elif any(v["status"] != "within_band" for v in group["models"]["candidate"]["levels"].values()):
            failures.append(f"calibration:{name}")
    for field, groups in report["subgroups"].items():
        failures.extend(f"subgroup_regression:{field}:{name}" for name, value in groups.items() if value.get("material_regression_flags"))
    report["decision"] = {"baseline_predictive_checks_pass": not failures, "failed_or_inconclusive_checks": failures,
                           "public_release": False, "remaining_release_gates": ["skill_intervals", "reliability_threshold", "window_estimator", "opponent_adjustment"]}
    return report


def finalize(folder, adapter, attestation, output):
    # This guard deliberately precedes reading either the frozen seed or future outcomes.
    if utcnow().date().isoformat() < CONFIG["end_exclusive"]:
        raise ValueError("Future block is still open; early scoring is prohibited.")
    if output.exists():
        raise ValueError("Use a new immutable output directory.")
    seed, frozen = load_freeze(folder)
    metadata = json.loads((adapter / "manifest.json").read_text())
    if metadata["before_exclusive"] < CONFIG["end_exclusive"]:
        raise ValueError("Adapter does not reach the full future block.")
    reviewed = json.loads(attestation.read_text())
    if (reviewed.get("adapter_sides_sha256") != digest(adapter / "sides.jsonl")
            or reviewed.get("start_inclusive") != CONFIG["start_inclusive"]
            or reviewed.get("end_exclusive") != CONFIG["end_exclusive"]
            or type(reviewed.get("unresolved_eligible_bouts")) is not int
            or reviewed["unresolved_eligible_bouts"] != 0
            or not str(reviewed.get("reviewed_by") or "").strip()
            or not str(reviewed.get("evidence") or "").strip()):
        raise ValueError("A matching completeness review is required.")
    rows, metadata, hashes = load_adapter(adapter)
    compatible(seed, rows)
    predictions = predict(rows)
    if not any(r["status"] == "observed" for r in predictions):
        raise ValueError("No positive future observations; cannot finalize an empty block.")
    report = {"config": CONFIG, "created_at_utc": utcnow().isoformat(), "input_sha256": hashes,
              "freeze_manifest_sha256": digest(folder / "manifest.json"), "seed_sha256": frozen["seed_sha256"],
              "completeness_attestation_sha256": digest(attestation), "completeness_review": reviewed,
              "measurement_statuses": dict(Counter(r["status"] for r in predictions)),
              "clipping": {model: sum(r["clipped"][model] for r in predictions) for model in ("candidate", *REFERENCES)},
              "evaluation": evaluation(predictions), "public_release": False}
    if any(digest(Path(p)) != value for p, value in hashes.items()):
        raise ValueError("Inputs changed during evaluation.")
    atomic_output(output, {"report.json": encoded(report),
                           "predictions.jsonl": "".join(json.dumps(r, sort_keys=True)+"\n" for r in predictions)})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("freeze")
    create.add_argument("--adapter", type=Path, required=True)
    create.add_argument("--protocol", type=Path, required=True)
    create.add_argument("--output", type=Path, required=True)
    check = sub.add_parser("status")
    finish = sub.add_parser("finalize")
    for p in (check, finish):
        p.add_argument("--freeze", type=Path, required=True)
        p.add_argument("--adapter", type=Path, required=True)
    finish.add_argument("--attestation", type=Path, required=True)
    finish.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "freeze":
        result = freeze(args.adapter, args.protocol, args.output)
    elif args.command == "status":
        result = status(args.freeze, args.adapter)
    else:
        result = finalize(args.freeze, args.adapter, args.attestation, args.output)
    print(encoded(result))


if __name__ == "__main__":
    main()
