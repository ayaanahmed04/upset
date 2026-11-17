"""Verify the extracted UPSET v2 review using only Python's standard library."""

import hashlib
import json
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from itertools import pairwise
from math import exp, floor, fsum, isclose, log, log1p
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EVIDENCE = ROOT / "evidence"
VERSIONS = ("v1", "v2", "v2_no_holds")
START, END = "2019-01-01", "2026-10-26"
SKILLS = ("striking", "wrestling", "grappling")


def read(path):
    return json.loads(path.read_text())


def rows(path):
    with path.open() as stream:
        yield from map(json.loads, stream)


def check(condition, message):
    if not condition:
        raise ValueError(message)


def near(actual, expected, message):
    check(isclose(actual, expected, rel_tol=0, abs_tol=1e-10), message)


def verify_hashes():
    expected = read(ROOT / "SHA256.json")
    for name, digest in expected.items():
        path = (ROOT / name).resolve()
        check(
            ROOT in path.parents
            and hashlib.sha256(path.read_bytes()).hexdigest() == digest,
            f"Bundle file differs: {name}",
        )
    snapshots = read(EVIDENCE / "snapshot-provenance.json")
    check(
        snapshots["v1"]["database_sha256"] == snapshots["v2"]["database_sha256"],
        "The source database fingerprints differ.",
    )
    for version in VERSIONS[:2]:
        for name, file in (
            ("model.json", f"evidence/model-{version}.json"),
            ("protocol.md", f"methods/{version}.md"),
        ):
            check(
                snapshots[version]["output_sha256"][name] == expected[file],
                f"{version} published {name} differs from the original output.",
            )
    for name, file in (
        ("evaluation.json", "evidence/validation-v2.json"),
        ("displayed_comparisons.jsonl", "evidence/displayed-comparisons.jsonl"),
    ):
        check(
            snapshots["v2"]["output_sha256"][name] == expected[file],
            f"v2 published {name} differs from the original output.",
        )
    for path in (ROOT / "source").glob("*.py"):
        file = path.relative_to(ROOT).as_posix()
        source = "src/upset/ratings/" + path.name
        check(
            snapshots["v2"]["input_sha256"][source] == expected[file],
            f"Published source differs: {path.name}",
        )


def blend(parts, model):
    values = sorted((parts[k] for k in SKILLS), reverse=True)
    skill = fsum(
        value * weight
        for value, weight in zip(values, model["skill_weights"], strict=True)
    )
    resume = model["resume_weight"]
    return skill, resume * parts["resume"] + (1 - resume) * skill


def grading(combined, model, version):
    reference = model["reference_values"]
    p = (bisect_left(reference, combined) + bisect_right(reference, combined)) / (
        2 * len(reference)
    )
    for (a, x), (b, y) in zip(model["anchors"], model["anchors"][1:]):
        if p <= b:
            unrounded = x + (p - a) * ((y - x) / (b - a))
            grade = floor(unrounded + 0.5)
            if version == "v2" and (p < 0.9999 or unrounded < 99):
                grade = min(98, grade)
            return p, unrounded, grade
    raise ValueError("Reference percentile is out of bounds.")


def result(row):
    outcomes = set(row["last_outcomes"])
    return next(iter(outcomes)) if outcomes in ({"win"}, {"loss"}) else None


def badge(row, prior, hold):
    curve = row["curve_score"]
    protected = min(curve, 88) if row["bouts"] < 5 else curve
    old = prior["score"] if prior else None
    unheld = protected if old is None else min(old + 5, max(old - 5, protected))
    reason = None
    if hold and old is not None:
        outcome = result(row)
        if outcome == "win" and unheld < old:
            reason = "held_after_win"
        elif outcome == "loss" and unheld > old:
            reason = "held_after_loss"
    shown = old if reason else unheld
    return {
        "score": shown,
        "change": shown - old if old is not None else None,
        "peak": max(shown, prior["peak"]) if prior else shown,
        "small_history_adjustment": protected - curve,
        "change_adjustment": unheld - protected,
        "unheld_score": unheld,
        "outcome_hold": reason,
    }


def verify_ratings(models):
    histories = {key: defaultdict(list) for key in VERSIONS}
    for version in VERSIONS[:2]:
        last = None
        for row in rows(EVIDENCE / f"rating-updates-{version}.jsonl"):
            uid, day = row["fighter_id"], row["event_date"]
            history = histories[version][uid]
            prior = history[-1] if history else None
            check(last is None or day >= last, "Rating rows are out of date order.")
            check(
                prior is None or day > prior["event_date"],
                "Duplicate fighter-date state.",
            )
            check(
                prior is None or row["fighter_name"] == prior["fighter_name"],
                "Inconsistent fighter name.",
            )
            last = day
            p, unrounded, curve = grading(row["raw_combined"], models[version], version)
            near(p, row["curve_percentile"], "Curve percentile differs.")
            check(curve == row["curve_score"], "Curve score differs.")
            expected = badge(row, prior, hold=version == "v2")
            check(
                all(row[key] == value for key, value in expected.items() if key in row),
                "Display adjustment, score or peak differs.",
            )
            history.append(row)
            if version == "v2":
                near(
                    unrounded, row["curve_unrounded"], "Unrounded curve grade differs."
                )
                unheld = histories["v2_no_holds"][uid]
                unheld.append(
                    {**row, **badge(row, unheld[-1] if unheld else None, hold=False)}
                )
    return histories


def policy(pairs):
    counts = Counter()
    for before, after in pairs:
        outcome = result(after)
        if outcome is None:
            continue
        delta = after["score"] - before["score"]
        wrong = delta < 0 if outcome == "win" else delta > 0
        counts[outcome + "_updates"] += 1
        counts[outcome + "_wrong_direction"] += wrong
        counts["wrong_direction_updates"] += wrong
        counts["decisive_updates"] += 1
        counts["full_five_moves"] += abs(delta) == 5
        counts["actual_limit_applications"] += bool(after["change_adjustment"])
        counts["win_holds"] += after.get("outcome_hold") == "held_after_win"
        counts["loss_holds"] += after.get("outcome_hold") == "held_after_loss"
        if outcome == "win" and before["score"] >= 90:
            counts["elite_updates"] += 1
            counts["elite_wrong_direction"] += wrong
        if before["bouts"] >= 10:
            counts["ten_plus_updates"] += 1
            counts["ten_plus_full_five_moves"] += abs(delta) == 5
            counts["ten_plus_actual_limit_applications"] += bool(
                after["change_adjustment"]
            )
    return counts


def verify_audit_counts(saved, counts):
    for key, outcome in (
        ("wins_lowered", "win"),
        ("elite_wins_lowered", "elite"),
        ("losses_raised", "loss"),
    ):
        record = saved[key]
        check(
            record["count"] == counts[f"{outcome}_wrong_direction"]
            and record["denominator"] == counts[f"{outcome}_updates"],
            f"{key} differs.",
        )
    for group, prefix in (("all", ""), ("ten_plus_prior_bouts", "ten_plus_")):
        record = saved["volatility"][group]
        check(
            record["denominator"] == counts[f"{prefix or 'decisive_'}updates"]
            and record["boundary_hits"] == counts[f"{prefix}full_five_moves"]
            and record["cap_applied"] == counts[f"{prefix}actual_limit_applications"],
            f"Volatility audit differs for {group}.",
        )


def verify_policies(histories, saved, audits):
    for version, by_fighter in histories.items():
        pairs = (
            (before, after)
            for history in by_fighter.values()
            for before, after in pairwise(history)
            if after["event_date"] >= START
        )
        counts = policy(pairs)
        named = []
        for uid, history in by_fighter.items():
            top = [r for r in history if r["event_date"] >= START and r["score"] == 99]
            if top:
                counts["display_99_states"] += len(top)
                counts["held_99_states"] += sum(
                    bool(r.get("outcome_hold")) for r in top
                )
                named.append(
                    {
                        "fighter_id": uid,
                        "name": top[0]["fighter_name"],
                        "first_99_in_window": top[0]["event_date"],
                    }
                )
        expected = saved[version]
        check(
            all(
                value == counts[key]
                for key, value in expected.items()
                if key != "named_99_fighters"
            ),
            f"{version} display policy counts differ.",
        )
        check(
            sorted(named, key=lambda r: (r["first_99_in_window"], r["name"]))
            == expected["named_99_fighters"],
            f"{version} named 99 fighters differ.",
        )
        if version in audits:
            verify_audit_counts(audits[version], counts)
    print("Rating chronology, outcome holds, five-point limits and named 99s verified.")


def verify_development(models, evaluation):
    comparison = evaluation["comparison_to_v1"]
    losses = {k: [] for k in VERSIONS[:2]}
    errors = {k: [] for k in VERSIONS[:2]}
    dates = set()
    for row in rows(EVIDENCE / "development.jsonl"):
        day = row["event_date"]
        dates.add(day)
        check(
            START <= day < END
            and all(d and d < day for d in row["prior_snapshot_dates"])
            and min(row["prior_bouts"]) > 0,
            "Ineligible development fight or snapshot date.",
        )
        y = int(row["winner_id"] == row["fighter_ids"][0])
        for version, model in models.items():
            current = row[version]
            a, b = [
                blend({k: 60 + 0.39 * v for k, v in part.items()}, model)[1]
                for part in current["parts"]
            ]
            z = model["probability_fit"]["slope"] * (a - b)
            p = 1 / (1 + exp(-z))
            loss = max(z, 0) + log1p(exp(-abs(z))) - y * z
            near(p, current["probability_a"], "Per-fight probability differs.")
            near(loss, current["nll"], "Per-fight log loss differs.")
            losses[version].append(loss)
            errors[version].append((p - y) ** 2)
    n = len(losses["v2"])
    candidate = evaluation["candidate"]
    check(
        n == candidate["bouts"] == comparison["matched_bouts"],
        "Matched fight count differs.",
    )
    check(
        len(dates) == comparison["paired_date_nll"]["clusters"],
        "Bootstrap date count differs.",
    )
    for version, expected_nll, expected_brier in (
        ("v1", comparison["v1_nll"], comparison["v1_brier"]),
        ("v2", candidate["nll"], candidate["brier"]),
    ):
        near(fsum(losses[version]) / n, expected_nll, "Mean log loss differs.")
        near(fsum(errors[version]) / n, expected_brier, "Mean Brier score differs.")
    diff = (
        fsum(new - old for old, new in zip(losses["v1"], losses["v2"], strict=True)) / n
    )
    near(diff, comparison["nll_difference"], "Paired log-loss difference differs.")
    print(f"{n:,} matched fights verified. Log-loss change {diff:+.6f}.")


def verify_display(histories, evaluation, old_sample):
    records = evaluation["display_records"]
    common = evaluation["comparison_to_v1"]["common_display"]
    counts = {key: Counter() for key in VERSIONS}
    both = Counter()
    old_paired = []
    prior_comparisons = {}
    for fight in rows(EVIDENCE / "displayed-comparisons.jsonl"):
        day = fight["event_date"]
        check(
            START <= day < END and fight["winner_id"] in fight["fighter_ids"],
            "Displayed comparison outside the decisive development cohort.",
        )
        winners = {}
        for version in VERSIONS:
            selected = []
            for name, uid in zip(
                fight["fighter_names"], fight["fighter_ids"], strict=True
            ):
                history = histories[version][uid]
                i = bisect_left(history, day, key=lambda row: row["event_date"]) - 1
                state = history[i] if i >= 0 else None
                selected.append(state)
                check(
                    state is None or state["fighter_name"] == name,
                    "Comparison fighter name differs.",
                )
                if version == "v1":
                    prior_day, before = prior_comparisons.get(uid, (None, None))
                    prior_comparisons[uid] = day, state
                    if before and state and state["event_date"] == prior_day:
                        old_paired.append((before, state))
            grades = [r["score"] if r else None for r in selected]
            dates = [r["event_date"] if r else None for r in selected]
            check(
                {"state_dates": dates, "grades": grades} == fight[version],
                "A comparison does not use the immediately earlier state.",
            )
            a, b = grades
            if None in grades:
                counts[version]["unavailable_excluded"] += 1
            elif a == b:
                counts[version]["ties_excluded"] += 1
            else:
                winners[version] = (
                    fight["fighter_ids"][int(b > a)] == fight["winner_id"]
                )
                counts[version]["wins"] += winners[version]
                counts[version]["total"] += 1
        if "v1" in winners and "v2" in winners:
            both["bouts"] += 1
            both["v1"] += winners["v1"]
            both["v2"] += winners["v2"]
    verify_audit_counts(old_sample, policy(old_paired))
    for version, saved in records.items():
        check(
            all(
                counts[version][k] == saved[k]
                for k in ("wins", "total", "ties_excluded", "unavailable_excluded")
            ),
            f"{version} displayed comparison counts differ.",
        )
        near(
            counts[version]["wins"] / counts[version]["total"],
            saved["accuracy"],
            f"{version} displayed accuracy differs.",
        )
    check(
        both["bouts"] == common["bouts"]
        and all(both[v] == common[v]["wins"] for v in VERSIONS[:2]),
        "Common displayed comparison differs.",
    )
    near(
        (both["v2"] - both["v1"]) / both["bouts"],
        common["accuracy_difference"],
        "Common display accuracy difference differs.",
    )
    print(
        f"Common non-tied grades verified. {both['v1']:,} → {both['v2']:,} winners in {both['bouts']:,} fights."
    )


def verify_case(case, models, histories):
    for version, model in models.items():
        for name, states in case[version].items():
            for row in states.values():
                parts = {p["key"]: p["score"] for p in row["parts"]}
                skill, combined = blend(parts, model)
                near(skill, row["skills_combined"], "Case skills blend differs.")
                near(combined, row["raw_combined"], "Case combined score differs.")
                history = histories[version][row["fighter_id"]]
                i = bisect_left(
                    history, row["event_date"], key=lambda r: r["event_date"]
                )
                state = history[i]
                check(
                    state["fighter_name"] == name
                    and all(state[k] == row[k] for k in row.keys() & state.keys()),
                    "Case does not match archived history.",
                )
        gaethje = case[version]["Justin Gaethje"]
        topuria = case[version]["Ilia Topuria"]
        before, after = gaethje["before"], gaethje["after"]
        expected = 1 / (1 + 10 ** ((topuria["before"]["elo"] - before["elo"]) / 400))
        near(
            before["elo"] + 32 * (1 - expected),
            after["elo"],
            "Case Elo update differs.",
        )
        print(
            f"{version} Gaethje badge verified. {before['score']} → {after['score']}."
        )


def main():
    verify_hashes()
    models = {key: read(EVIDENCE / f"model-{key}.json") for key in VERSIONS[:2]}
    v1_audit, v2_audit = (read(EVIDENCE / f"{key}-audit.json") for key in VERSIONS[:2])
    evaluation = read(EVIDENCE / "validation-v2.json")
    histories = verify_ratings(models)
    verify_policies(
        histories,
        evaluation["policies"],
        {"v1": v1_audit["full_history"], "v2": v2_audit},
    )
    verify_development(models, evaluation)
    verify_display(histories, evaluation, v1_audit["prior_review_sample"])
    verify_case(read(ROOT / "case/gaethje-topuria.json"), models, histories)
    comparison = evaluation["comparison_to_v1"]
    common = comparison["common_display"]
    engineering = (
        evaluation["chronology"]["passed"]
        and evaluation["policy"]["wrong_direction_updates"] == 0
    )
    eligible = (
        engineering
        and comparison["matched_bouts"] >= 500
        and evaluation["candidate"]["nll"] < log(2)
        and comparison["nll_difference"] <= 0.010
        and common["bouts"] >= 500
        and common["accuracy_difference"] >= -0.02
    )
    check(
        engineering == evaluation["engineering_checks_passed"]
        and eligible == evaluation["serving_eligible"],
        "Declared local preview gate differs.",
    )
    print(
        "Bundle hashes and saved arithmetic verified. Full feature replay requires the original inputs."
    )


if __name__ == "__main__":
    main()
