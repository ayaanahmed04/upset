"""Package verified v1 and v2 rating evidence for independent review."""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from contextlib import closing
from pathlib import Path

from audit_rating_v1_review import (
    DATABASE,
    FIGHT,
    GAETHJE,
    ROOT,
    TOPURIA,
    audit,
)
from audit_rating_v1_review import (
    OUTPUT as V1_AUDIT,
)
from audit_rating_v1_review import (
    SNAPSHOT as V1,
)

from upset.research_app import connect

NAME = "UPSET-Rating-Review-v2-2026-11-05"
RATING_FIELDS = (
    "fighter_id",
    "event_date",
    "bouts",
    "last_outcomes",
    "raw_combined",
    "curve_percentile",
    "curve_score",
    "small_history_adjustment",
    "change_adjustment",
    "score",
    "change",
    "peak",
)


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path):
    return json.loads(path.read_text())


def rows(path):
    with path.open() as stream:
        yield from map(json.loads, stream)


def save(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def save_rows(path, values):
    with path.open("w") as stream:
        for row in values:
            stream.write(json.dumps(row, separators=(",", ":"), allow_nan=False) + "\n")


def provenance(folder, version):
    manifest = read(folder / "manifest.json")
    if manifest["version"] != f"upset_rating_experimental_{version}":
        raise ValueError(f"Unexpected rating version in {folder.name}.")
    for name, expected in manifest["output_sha256"].items():
        if sha(folder / name) != expected:
            raise ValueError(f"{version} output differs from its manifest: {name}")
    sources = {}
    for name, expected in manifest["input_sha256"].items():
        source = Path(name)
        if sha(source) != expected:
            raise ValueError(
                f"{version} input differs from its manifest: {source.name}"
            )
        label = (
            str(source.relative_to(ROOT))
            if source.is_relative_to(ROOT)
            else source.name
        )
        if label in sources:
            raise ValueError(f"Duplicate source fingerprint label: {label}")
        sources[label] = expected
    fields = (
        "version",
        "experimental",
        "validated",
        "public_release",
        "database_sha256",
        "before_exclusive",
        "latest_event",
        "display_curve",
        "output_sha256",
    )
    return {
        **{key: manifest[key] for key in fields},
        "input_sha256": sources,
        "original_manifest_sha256": sha(folder / "manifest.json"),
    }


def compact_ratings(records, names, version):
    fields = (
        RATING_FIELDS
        if version == "v1"
        else RATING_FIELDS
        + (
            "curve_unrounded",
            "unheld_score",
            "outcome_hold",
        )
    )
    for row in records:
        yield {
            **{key: row[key] for key in fields},
            "fighter_name": names[row["fighter_id"]],
        }


def case_states(records):
    result = {}
    for uid, name in ((GAETHJE, "Justin Gaethje"), (TOPURIA, "Ilia Topuria")):
        history = [row for row in records if row["fighter_id"] == uid]
        i = next(i for i, row in enumerate(history) if FIGHT in row["fight_ids"])
        result[name] = {"before": history[i - 1], "after": history[i]}
    return result


def matched_evidence(old, new):
    identity = ("fight_id", "event_date", "fighter_ids", "winner_id")
    for v1, v2 in zip(old, new, strict=True):
        if any(v1[key] != v2[key] for key in identity):
            raise ValueError("Development records differ in matched bout identity.")
        yield {
            **{
                key: v2[key]
                for key in (
                    *identity,
                    "fighter_names",
                    "prior_bouts",
                    "prior_snapshot_dates",
                )
            },
            "v1": {
                "parts": v1["parts"],
                "nll": v1["candidate_nll"],
                "probability_a": v1["candidate_probability_a"],
            },
            "v2": {
                "parts": v2["parts"],
                "nll": v2["v2_nll"],
                "probability_a": v2["v2_probability_a"],
            },
        }


def _fraction(measure):
    n = measure["denominator"]
    return f"{measure['count']:,} / {n:,} ({measure['share']:.1%})" if n else "—"


def _volatility(measure, count, share):
    n = measure["denominator"]
    return f"{measure[count]:,} / {n:,} ({measure[share]:.1%})" if n else "—"


def addendum(v1_audit, v2_audit, evaluation, case):
    v1, earlier = (v1_audit[key] for key in ("full_history", "prior_review_sample"))
    old, new = (case[key]["Justin Gaethje"] for key in ("v1", "v2"))
    comparison = evaluation["comparison_to_v1"]
    common = comparison["common_display"]
    status = (
        "The archived run met the local experimental preview gates."
        if evaluation["serving_eligible"]
        else "The archived run missed at least one local experimental preview gate."
    )
    lines = [
        f"""# What changed in Experimental v2

{status} These are development results on previously inspected recorded fights.

## Justin Gaethje and Ilia Topuria

UPSET records Gaethje winning a June 14, 2026 title bout by KO/TKO at 5:00 of round
four. The stored record leaves the circumstances of the stoppage unspecified.
Topuria landed 97 of 162 significant strikes and scored the only recorded
knockdown. Gaethje landed 91 of 192 and went 0 for 5 on takedowns.

| Calculation | Experimental v1 | Experimental v2 |
| --- | ---: | ---: |
| Striking | {old["before"]["parts"][0]["score"]:.3f} → {old["after"]["parts"][0]["score"]:.3f} | {new["before"]["parts"][0]["score"]:.3f} → {new["after"]["parts"][0]["score"]:.3f} |
| Wrestling | {old["before"]["parts"][1]["score"]:.3f} → {old["after"]["parts"][1]["score"]:.3f} | {new["before"]["parts"][1]["score"]:.3f} → {new["after"]["parts"][1]["score"]:.3f} |
| Grappling | {old["before"]["parts"][2]["score"]:.3f} → {old["after"]["parts"][2]["score"]:.3f} | {new["before"]["parts"][2]["score"]:.3f} → {new["after"]["parts"][2]["score"]:.3f} |
| Résumé | {old["before"]["parts"][3]["score"]:.3f} → {old["after"]["parts"][3]["score"]:.3f} | {new["before"]["parts"][3]["score"]:.3f} → {new["after"]["parts"][3]["score"]:.3f} |
| Combined before grading | {old["before"]["raw_combined"]:.3f} → {old["after"]["raw_combined"]:.3f} | {new["before"]["raw_combined"]:.3f} → {new["after"]["raw_combined"]:.3f} |
| Displayed badge | {old["before"]["score"]} → {old["after"]["score"]} | {new["before"]["score"]} → {new["after"]["score"]} |

In v1, Résumé contributed +0.273 combined points, Striking contributed −0.291,
and Wrestling plus Grappling contributed −0.320. The two lower skills traded
places in the ranked blend, so the audit groups them. The combined decrease of
0.338 crossed a rounding boundary. V1 counted KO/TKO losses in Striking and used
an opponent's KO/TKO wins as a defense comparison. V2 adds direct credit for the
fighter's own KO/TKO wins alongside the existing KO/TKO loss feature.

V2 gives Résumé half the combined weight. The skills blend stays at 50% strongest,
30% second and 20% third. The fixed curve uses pre-2019 fighter-date states.
The outcome hold comes after grading and caps. Gaethje's v2 post-fight badge
before that last rule was **{new["after"]["unheld_score"]}**. The saved hold reason
for this update is **{(new["after"]["outcome_hold"] or "none").replace("_", " ")}**.

## How often badges moved against the result

The earlier ZIP sample compares two consecutive decisive appearances within its
2019 to October 25, 2026 comparison window. It requires a rated state from each
appearance and checks that the later pre-fight grade dates to the earlier bout.
The full history follows each fighter's consecutive states through October 31,
including the final update when there is no later bout. The three columns below
use those scopes. The 90+ condition uses the pre-update badge.

| Measure | v1 earlier sample | v1 full history | v2 full history |
| --- | ---: | ---: | ---: |"""
    ]
    for label, key in (
        ("Wins that lowered the badge", "wins_lowered"),
        ("Wins at 90+ that lowered the badge", "elite_wins_lowered"),
        ("Losses that raised the badge", "losses_raised"),
    ):
        cells = " | ".join(_fraction(audit[key]) for audit in (earlier, v1, v2_audit))
        lines.append(f"| {label} | {cells} |")
    for label, group, count, share in (
        ("Displayed move of exactly five", "all", "boundary_hits", "boundary_share"),
        ("Five-point limit applied", "all", "cap_applied", "cap_share"),
        (
            "Exactly five with 10+ prior bouts",
            "ten_plus_prior_bouts",
            "boundary_hits",
            "boundary_share",
        ),
        (
            "Limit applied with 10+ prior bouts",
            "ten_plus_prior_bouts",
            "cap_applied",
            "cap_share",
        ),
    ):
        cells = " | ".join(
            _volatility(audit["volatility"][group], count, share)
            for audit in (earlier, v1, v2_audit)
        )
        lines.append(f"| {label} | {cells} |")
    lines.append(f"""
The limit applied when the pre-hold movement would have exceeded five points.
An exact five-point change can occur on its own. V2 held {v2_audit["holds"]["after_win"]:,}
winner updates and {v2_audit["holds"]["after_loss"]:,} loser updates through October 31.
The fixed curve is steepest between 89 and 94. Those five grade points span
the 95th through 97th percentiles. V2 keeps that section and the movement limit.

## The top grade

V1 half-up rounding made an unrounded 98.5 display as 99. That threshold begins
at the top 0.255% of the fixed historical reference curve. V2 requires a curve
grade of 99 at or above the 99.99th reference percentile. A win hold can retain
a previous 99. The reference compares fighter-date states, including multiple
states for the same fighter.

| Version | Fighters who displayed 99 | 99 states earned / held |
| --- | --- | ---: |""")
    for label, record in (("v1", v1), ("v2", v2_audit)):
        states = record["at_99"]
        names = ", ".join(row["name"] for row in states["fighters"]) or "None in scope"
        lines.append(
            f"| {label} | {names} | {states['earned_states']} / {states['held_states']} |"
        )
    lines.append(f"""
## Matched historical comparison

Across {comparison["matched_bouts"]:,} identical fights, log loss was
**{comparison["v1_nll"]:.5f}** for v1 and **{evaluation["candidate"]["nll"]:.5f}**
for v2. Lower is better. The archived 95% paired date-bootstrap interval for
the change was {comparison["paired_date_nll"]["interval_95"][0]:+.5f} to
{comparison["paired_date_nll"]["interval_95"][1]:+.5f}. On the {common["bouts"]:,}
fights where both versions gave the fighters unequal grades, the higher grade
was on the winner **{common["v1"]["wins"]:,} times in v1** and
**{common["v2"]["wins"]:,} times in v2**. An individual badge is a 60–99 index.

The verifier recomputes the matched arithmetic, grade comparisons and display
rules from the saved evidence. A full replay of the opponent features requires
the original reviewed bout database. The archived date-block bootstrap and
prefix checks are described in the [v2 protocol](methods/v2.md).
""")
    return "\n".join(lines)


README = """# UPSET rating review

Start with [What changed in Experimental v2](REVIEW_ADDENDUM.md). It walks
through the Gaethje case, shows how often the display moved against a result,
and compares the two versions on the same historical fights.

| File | Contents |
| --- | --- |
| `case/gaethje-topuria.json` | Recorded fight totals and exact rating inputs before and after the fight |
| `evidence/validation-v2.json` | The declared gates, measured comparison, saved prefix check and subgroups |
| `evidence/v1-audit.json`, `evidence/v2-audit.json` | Cohorts, outcome counts, movement limits and named 99 states |
| `evidence/development.jsonl` | Named matched fights, stored pre-fight component inputs and per-fight loss for both models |
| `evidence/displayed-comparisons.jsonl` | Named decisive fights and the strictly earlier grades used in each comparison |
| `evidence/rating-updates-v*.jsonl` | Named fighter-date states used to verify the display history |
| `evidence/model-v*.json` | Skill and résumé blend, evaluation slope and fixed grading curve |
| `evidence/snapshot-provenance.json` | Hashes for the frozen inputs, outputs and original manifests |
| `methods/`, `source/` | Declared protocols and model source reference copies |

Extract the whole archive and run `python3 verify_review.py` from this folder.
It uses Python 3.10 or newer and its standard library. The source reference
copies need the rest of UPSET and the original reviewed database for full
feature replay. The bundle covers previously inspected historical development
fights. Performance on new fights requires separate evaluation.
"""


def create_review(snapshot, output):
    if output.exists():
        raise FileExistsError(f"Preserve the existing review archive: {output.name}")
    sources = {"v1": V1, "v2": snapshot}
    fingerprints = {
        version: provenance(path, version) for version, path in sources.items()
    }
    if any(item["database_sha256"] != sha(DATABASE) for item in fingerprints.values()):
        raise ValueError("Both ratings must bind the same reviewed database.")
    with closing(connect(DATABASE)) as db:
        names = dict(db.execute("SELECT id, name FROM fighters"))
    old_audit = read(V1_AUDIT)
    if (
        old_audit["source_sha256"]["ratings.jsonl"]
        != fingerprints["v1"]["output_sha256"]["ratings.jsonl"]
    ):
        raise ValueError("V1 audit is from a different snapshot.")
    evaluation = read(snapshot / "evaluation.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        dir=output.parent, prefix=".rating-review-v2-"
    ) as tmp:
        bundle = Path(tmp) / NAME
        evidence = bundle / "evidence"
        for name in ("case", "evidence", "methods", "source"):
            (bundle / name).mkdir(parents=True)
        case = {"recorded_bout": old_audit["gaethje_topuria"]["recorded_bout"]}
        for version, folder in sources.items():
            records = list(rows(folder / "ratings.jsonl"))
            case[version] = case_states(records)
            save_rows(
                evidence / f"rating-updates-{version}.jsonl",
                compact_ratings(records, names, version),
            )
            if version == "v2":
                new_audit = audit(records, names)
            shutil.copyfile(folder / "model.json", evidence / f"model-{version}.json")
            shutil.copyfile(
                folder / "protocol.md", bundle / "methods" / f"{version}.md"
            )
            del records
        save(bundle / "case/gaethje-topuria.json", case)
        save(evidence / "v1-audit.json", old_audit)
        save(evidence / "v2-audit.json", new_audit)
        save(evidence / "snapshot-provenance.json", fingerprints)
        shutil.copyfile(snapshot / "evaluation.json", evidence / "validation-v2.json")
        shutil.copyfile(
            snapshot / "displayed_comparisons.jsonl",
            evidence / "displayed-comparisons.jsonl",
        )
        save_rows(
            evidence / "development.jsonl",
            matched_evidence(
                rows(V1 / "development.jsonl"),
                rows(snapshot / "development.jsonl"),
            ),
        )
        for name in (
            "build.py",
            "build_v2.py",
            "data.py",
            "engine.py",
            "engine_v2.py",
            "serving.py",
            "serving_v2.py",
        ):
            shutil.copyfile(ROOT / "src/upset/ratings" / name, bundle / "source" / name)
        shutil.copyfile(
            ROOT / "scripts/verify_rating_review_v2.py", bundle / "verify_review.py"
        )
        (bundle / "START_HERE.md").write_text(README)
        (bundle / "REVIEW_ADDENDUM.md").write_text(
            addendum(old_audit, new_audit, evaluation, case)
        )
        paths = [p for p in sorted(bundle.rglob("*")) if p.is_file()]
        save(
            bundle / "SHA256.json", {str(p.relative_to(bundle)): sha(p) for p in paths}
        )
        subprocess.run([sys.executable, str(bundle / "verify_review.py")], check=True)
        staged = Path(tmp) / output.name
        with zipfile.ZipFile(
            staged, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9
        ) as zipped:
            for path in (*paths, bundle / "SHA256.json"):
                zipped.write(path, arcname=str(path.relative_to(bundle.parent)))
        with zipfile.ZipFile(staged) as zipped:
            if zipped.testzip() is not None:
                raise ValueError("Review archive failed its integrity check.")
        staged.replace(output)
    print(f"{output} ({output.stat().st_size:,} bytes)")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "docs/share" / f"{NAME}.zip"
    )
    args = parser.parse_args()
    create_review(args.snapshot.resolve(), args.output.resolve())


if __name__ == "__main__":
    main()
