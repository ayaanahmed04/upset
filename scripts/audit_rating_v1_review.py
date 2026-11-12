"""Reproduce the v1 rating review from frozen states and recorded bout data."""

import hashlib
import json
from bisect import bisect_left
from collections import Counter, defaultdict
from contextlib import closing
from math import isclose
from pathlib import Path

from upset.research_app import connect, fighter_report

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data/processed"
SNAPSHOT = PROCESSED / "overall_rating_2026_11_05_v1"
DATABASE = PROCESSED / "research_2026_11_03_v1/upset.sqlite"
OUTPUT = PROCESSED / "overall_rating_v1_review_audit_2026_11_05.json"
GAETHJE = "678d50b2-742c-44e4-b833-d560794ba84c"
TOPURIA = "7a1b1eb6-1471-4f85-987c-d77c340947eb"
FIGHT = "cito:7208e40818401e88"


def _digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _lines(path):
    with path.open() as stream:
        for line in stream:
            yield json.loads(line)


def _share(count, total):
    return count / total if total else None


def _summarize(pairs, change_cap):
    counts = Counter()
    volatility = [Counter(), Counter()]
    for before, after in pairs:
        delta = after["score"] - before["score"]
        if delta != after["change"]:
            raise ValueError("Displayed change does not match consecutive states.")
        outcomes = set(after["last_outcomes"])
        if outcomes == {"win"}:
            counts["wins"] += 1
            counts["wins_lowered"] += delta < 0
            if before["score"] >= 90:
                counts["elite_wins"] += 1
                counts["elite_wins_lowered"] += delta < 0
        elif outcomes == {"loss"}:
            counts["losses"] += 1
            counts["losses_raised"] += delta > 0
        else:
            counts["nondecisive_or_mixed"] += 1
            continue
        if reason := after.get("outcome_hold"):
            counts[reason] += 1
        groups = volatility if before["bouts"] >= 10 else volatility[:1]
        for group in groups:
            group["denominator"] += 1
            group["boundary_hits"] += abs(delta) == change_cap
            group["cap_applied"] += bool(after["change_adjustment"])

    summary = {}
    for measure, cohort in (
        ("wins_lowered", "wins"),
        ("elite_wins_lowered", "elite_wins"),
        ("losses_raised", "losses"),
    ):
        count, total = counts[measure], counts[cohort]
        summary[measure] = {
            "count": count,
            "denominator": total,
            "share": _share(count, total),
        }
    summary["volatility"] = {
        key: {
            "denominator": c["denominator"],
            "boundary_hits": c["boundary_hits"],
            "boundary_share": _share(c["boundary_hits"], c["denominator"]),
            "cap_applied": c["cap_applied"],
            "cap_share": _share(c["cap_applied"], c["denominator"]),
        }
        for key, c in zip(("all", "ten_plus_prior_bouts"), volatility, strict=True)
    }
    summary["holds"] = {
        "after_win": counts["held_after_win"],
        "after_loss": counts["held_after_loss"],
    }
    summary["nondecisive_or_mixed_excluded"] = counts["nondecisive_or_mixed"]
    return summary


def audit(rows, names, start="2019-01-01", *, change_cap=5):
    """Audit chronological post-date rating rows using the preceding fighter state."""
    previous = {}
    pairs = []
    at_99 = {}
    latest = None
    first_ratings = 0
    for row in rows:
        uid, day = row["fighter_id"], row["event_date"]
        if latest is not None and day < latest:
            raise ValueError("Rating rows must be in date order.")
        latest = day
        before = previous.get(uid)
        if before and before["event_date"] >= day:
            raise ValueError("A fighter can only have one state per date.")
        previous[uid] = row
        if day < start:
            continue
        if before is None:
            first_ratings += 1
        else:
            pairs.append((before, row))
        if row["score"] == 99:
            fighter = at_99.setdefault(
                uid,
                {
                    "fighter_id": uid,
                    "name": names[uid],
                    "first_date_in_scope": day,
                    "earned_states": 0,
                    "held_states": 0,
                },
            )
            field = "held_states" if row.get("outcome_hold") else "earned_states"
            fighter[field] += 1
    return {
        "scope": {
            "from_inclusive": start,
            "through_inclusive": latest,
            "consecutive_updates": len(pairs),
            "first_ratings_excluded": first_ratings,
            "change_cap": change_cap,
            "unit": "Fighter-date update from the fighter's immediately prior rating",
            "decisive_rule": "All recorded outcomes on the date are wins or all are losses",
            "elite_rule": "Previous displayed grade of at least 90",
            "experience_rule": "At least 10 linked bouts as of the preceding state",
            "cap_rule": "Nonzero change adjustment before any result hold",
        },
        **_summarize(pairs, change_cap),
        "at_99": {
            "distinct_fighters": len(at_99),
            "fighters": sorted(at_99.values(), key=lambda fighter: fighter["name"]),
            "earned_states": sum(r["earned_states"] for r in at_99.values()),
            "held_states": sum(r["held_states"] for r in at_99.values()),
        },
    }


def _review_sample(rows, prefights, start, end, change_cap):
    # Reconstruct the earlier ZIP's displayed_comparisons evidence from frozen inputs.
    histories = defaultdict(list)
    for row in rows:
        histories[row["fighter_id"]].append(row)
    last_comparison = {}
    pairs = []
    appearances = 0
    for fight in prefights:
        day = fight["event_date"]
        if not start <= day < end or fight["winner_id"] is None:
            continue
        appearances += 2
        for uid in fight["fighter_ids"]:
            history = histories[uid]
            index = bisect_left(history, day, key=lambda row: row["event_date"])
            state = history[index - 1] if index else None
            earlier_day, earlier_state = last_comparison.get(uid, (None, None))
            last_comparison[uid] = day, state
            if earlier_state and state and earlier_day == state["event_date"]:
                pairs.append((earlier_state, state))
    return {
        "scope": {
            "from_inclusive": start,
            "before_exclusive": end,
            "decisive_appearances": appearances,
            "paired_updates": len(pairs),
            "unit": "Two consecutive decisive appearances in displayed comparisons, both "
            "rated, with the later pre-fight state dated to the earlier fight",
            "limitations": "Requires another decisive appearance within the comparison "
            "window, and skips intervening rating states",
        },
        **_summarize(pairs, change_cap),
    }


def _rounding(model):
    anchors = {grade: percentile for percentile, grade in reversed(model["anchors"])}
    threshold = anchors[98] + 0.5 * (anchors[99] - anchors[98])
    return {
        "half_up_unrounded_grade_threshold": 98.5,
        "half_up_reference_percentile_threshold": threshold,
        "half_up_reference_upper_tail_share": 1 - threshold,
        "exact_99_reference_percentile_threshold": anchors[99],
        "exact_99_reference_upper_tail_share": 1 - anchors[99],
        "reference_states": len(model["reference_values"]),
        "scope": "Interpolation before display caps, on the fixed pre-2019 "
        "fighter-date reference curve",
    }


def _case(db, rows, model, cutoff):
    report = fighter_report(db, GAETHJE, cutoff, 0)
    bout = next(fight for fight in report["history"] if fight["fight_id"] == FIGHT)
    snapshots = {}
    for uid, name in ((GAETHJE, "Justin Gaethje"), (TOPURIA, "Ilia Topuria")):
        history = [row for row in rows if row["fighter_id"] == uid]
        position = next(i for i, row in enumerate(history) if FIGHT in row["fight_ids"])
        snapshots[name] = history[position - 1 : position + 1]
    before, after = snapshots["Justin Gaethje"]
    old_parts, new_parts = (
        {p["key"]: p["score"] for p in row["parts"]} for row in (before, after)
    )
    skill_weights = model["skill_weights"]
    resume_weight = model["resume_weight"]
    old_rank, new_rank = (
        sorted((key for key in parts if key != "resume"), key=parts.get, reverse=True)
        for parts in (old_parts, new_parts)
    )
    old_weights = dict(zip(old_rank, skill_weights, strict=True))
    new_weights = dict(zip(new_rank, skill_weights, strict=True))
    contributions = {
        key: (1 - resume_weight)
        * (new_weights[key] * new_parts[key] - old_weights[key] * old_parts[key])
        for key in old_rank
    }
    combined_changes = {
        "striking": contributions["striking"],
        "wrestling_and_grappling": sum(
            contributions[key] for key in ("wrestling", "grappling")
        ),
        "resume": resume_weight * (new_parts["resume"] - old_parts["resume"]),
    }
    combined_delta = after["raw_combined"] - before["raw_combined"]
    if not isclose(sum(combined_changes.values()), combined_delta, abs_tol=1e-12):
        raise ValueError("Combined attribution does not reproduce Gaethje's change.")
    stats = (
        "sig_strikes_landed",
        "sig_strikes_attempted",
        "knockdowns",
        "takedowns_landed",
        "takedowns_attempted",
        "control_seconds",
        "ground_landed",
        "submission_attempts",
        "fight_duration_seconds",
    )
    bout_keys = (
        "fight_id",
        "date",
        "outcome",
        "method",
        "result_round",
        "result_time",
        "title_bout",
        "source",
        "weight_class",
    )
    return {
        "recorded_bout": {
            **{key: bout[key] for key in bout_keys},
            "Justin Gaethje": {key: bout["own"][key] for key in stats},
            "Ilia Topuria": {key: bout["opponent_stats"][key] for key in stats},
        },
        "record_scope": "UPSET's stored result and totals. The method and time leave "
        "the circumstances of the stoppage unspecified.",
        "displayed_grades": {
            name: [row["score"] for row in states] for name, states in snapshots.items()
        },
        "gaethje_components": {
            key: [old_parts[key], new_parts[key]] for key in old_parts
        },
        "gaethje_ranked_skill_weights": {"before": old_weights, "after": new_weights},
        "gaethje_raw_combined": [before["raw_combined"], after["raw_combined"]],
        "gaethje_curve_grades": [before["curve_score"], after["curve_score"]],
        "gaethje_curve_percentiles": [
            before["curve_percentile"],
            after["curve_percentile"],
        ],
        "gaethje_post_bout_adjustments": {
            key: after[key] for key in ("small_history_adjustment", "change_adjustment")
        },
        "gaethje_combined_point_attribution": combined_changes,
        "gaethje_combined_change": combined_delta,
        "attribution_rule": "Difference in weighted points, grouping Wrestling and Grappling "
        "because their rank weights switch. This is before the curve.",
    }


def main():
    manifest = json.loads((SNAPSHOT / "manifest.json").read_text())
    input_hashes = {
        name: _digest(SNAPSHOT / name)
        for name in ("ratings.jsonl", "prefights.jsonl", "model.json", "config.json")
    }
    if any(
        sha != manifest["output_sha256"][name] for name, sha in input_hashes.items()
    ):
        raise ValueError("Frozen v1 inputs do not match the manifest.")
    if _digest(DATABASE) != manifest["database_sha256"]:
        raise ValueError("Reviewed database does not match the v1 manifest.")
    rows = list(_lines(SNAPSHOT / "ratings.jsonl"))
    model = json.loads((SNAPSHOT / "model.json").read_text())
    config = json.loads((SNAPSHOT / "config.json").read_text())
    start, end, cap = (
        config[key] for key in ("freeze_before", "evaluation_before", "change_cap")
    )
    with closing(connect(DATABASE)) as db:
        names = dict(db.execute("SELECT id, name FROM fighters"))
        result = {
            "version": manifest["version"],
            "source_sha256": {
                **input_hashes,
                "upset.sqlite": manifest["database_sha256"],
            },
            "full_history": audit(rows, names, start, change_cap=cap),
            "prior_review_sample": _review_sample(
                rows, _lines(SNAPSHOT / "prefights.jsonl"), start, end, cap
            ),
            "rounding_at_99": _rounding(model),
            "gaethje_topuria": _case(db, rows, model, manifest["before_exclusive"]),
        }
    OUTPUT.write_text(
        json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n"
    )
    print(OUTPUT)


if __name__ == "__main__":
    main()
