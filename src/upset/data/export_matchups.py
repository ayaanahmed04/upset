"""Publish historical matchups with prior features and explicit binary targets."""

import json
from dataclasses import fields
from pathlib import Path
from tempfile import TemporaryDirectory

from upset.data.export_prefight import read_identified
from upset.data.identify_historical import IdentifiedFight
from upset.data.matchups import MatchupRow, build_matchup_rows
from upset.data.models import Fight
from upset.data.prefight_features import PreFightFeatures


def _read_features(path: Path) -> list[PreFightFeatures]:
    expected = {field.name for field in fields(PreFightFeatures)}
    rows = []
    with path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            try:
                record = json.loads(line)
                if not isinstance(record, dict) or set(record) != expected:
                    raise ValueError("fields do not match the fighter feature model")
                rows.append(PreFightFeatures(**record))
            except (TypeError, ValueError) as error:
                raise ValueError(
                    f"Invalid {path.name} at line {line_number}: {error}"
                ) from error
    return rows


def export_matchups(
    fights_path: Path, features_path: Path, output_path: Path
) -> tuple[int, int, int]:
    """Validate all joins and labels before replacing the verified JSONL file."""
    if output_path.resolve() in (fights_path.resolve(), features_path.resolve()):
        raise ValueError("Output must not overwrite an input file.")

    fights: list[IdentifiedFight] = read_identified(
        fights_path,
        Fight,
        IdentifiedFight,
        ("upset_fighter_1_id", "upset_fighter_2_id"),
    )
    features = _read_features(features_path)
    matchups: tuple[MatchupRow, ...] = build_matchup_rows(fights, features)
    records = [row.as_record() for row in matchups]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(
        dir=output_path.parent, prefix=".upset-matchups-"
    ) as directory:
        temporary = Path(directory) / output_path.name
        with temporary.open("w", encoding="utf-8", newline="\n") as saved:
            for record in records:
                saved.write(
                    json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n"
                )
        with temporary.open(encoding="utf-8") as saved:
            restored = [json.loads(line) for line in saved]
        if restored != records:
            raise ValueError("Matchup read-back verification failed.")
        temporary.replace(output_path)

    labeled = sum(row.target_a_win is not None for row in matchups)
    return len(matchups), labeled, len(matchups) - labeled


def main() -> None:
    processed = Path("data/processed/kaggle_ufc_1994_2026")
    output = processed / "prefight" / "matchups.jsonl"
    total, labeled, ambiguous = export_matchups(
        processed / "identified" / "fights_identified.jsonl",
        processed / "prefight" / "fighter_features.jsonl",
        output,
    )
    print(f"Historical matchups: {total}")
    print(f"Decisive binary targets: {labeled}")
    print(f"Ambiguous Draw/NC targets: {ambiguous}")
    print("Read-back verification: passed")
    print(f"Saved to: {output}")


if __name__ == "__main__":
    main()
