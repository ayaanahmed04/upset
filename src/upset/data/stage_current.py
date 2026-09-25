"""Stage reviewed, normalized completed fights without rewriting historical data."""

import argparse
import hashlib
import json
from dataclasses import fields
from datetime import UTC, date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from upset.data.export_prefight import read_identified
from upset.data.identify_historical import IdentifiedFight, IdentifiedFightStats
from upset.data.identity import load_fighter_registry
from upset.data.models import Fight, FightStats

LAST_HISTORICAL_DATE = "2026-03-07"
ACCEPTED_HISTORICAL_FIGHTS_SHA256 = (
    "a5b3076e08b540bef41529300d3e092dc2477f458bba88c1118ebe94a721c53e"
)


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read(path: Path, record_type: type) -> list:
    expected = {field.name for field in fields(record_type)}
    result = []
    with path.open(encoding="utf-8") as source:
        for number, line in enumerate(source, 1):
            try:
                value = json.loads(line)
                if not isinstance(value, dict) or set(value) != expected:
                    raise ValueError("Unexpected canonical fields")
                result.append(record_type(**value))
            except (TypeError, ValueError) as error:
                raise ValueError(f"Invalid {path.name} row {number}: {error}") from error
    if not result:
        raise ValueError(f"Empty current input: {path.name}")
    return result


def stage_completed_fights(
    fights_path: Path, stats_path: Path, registry_path: Path,
    historical_path: Path, output: Path, *, observed_at: datetime | None = None,
    expected_historical_sha256: str = ACCEPTED_HISTORICAL_FIGHTS_SHA256,
) -> dict:
    """Require paired stats, reviewed provider links and unique dated matchups.

    Input fights and stats use the existing canonical Fight/FightStats JSONL
    schema; provider acquisition/normalization and manual identity review
    happen upstream. This stage does not update model history or train a model.
    """
    moment = datetime.now(UTC) if observed_at is None else observed_at
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("Acquisition timestamp must have a UTC timezone.")
    moment = moment.astimezone(UTC).replace(microsecond=0)
    paths = (fights_path, stats_path, registry_path, historical_path)
    if (output.exists() or len({p.resolve() for p in paths}) != len(paths)
            or output.resolve() in {p.resolve() for p in paths}):
        raise ValueError("Output exists or current inputs overlap.")
    source_hashes = {name: _hash(path) for name, path in zip(
        ("fights", "stats", "registry", "historical"), paths, strict=True
    )}
    if source_hashes["historical"] != expected_historical_sha256:
        raise ValueError("Historical fights differ from the accepted snapshot.")
    registry = load_fighter_registry(registry_path)
    known = {item.upset_fighter_id for item in registry.identities}
    links = {(link.provider, link.provider_fighter_id): link.upset_fighter_id
             for link in registry.provider_links}
    historical = read_identified(
        historical_path, Fight, IdentifiedFight,
        ("upset_fighter_1_id", "upset_fighter_2_id"),
    )
    if max(row.fight.event_date for row in historical) != LAST_HISTORICAL_DATE:
        raise ValueError("Historical cutoff differs from the accepted snapshot.")
    occupied = {(r.fight.event_date, *sorted((r.upset_fighter_1_id,
                                             r.upset_fighter_2_id)))
                for r in historical}
    fights = _read(fights_path, Fight)
    stats = _read(stats_path, FightStats)
    provider = fights[0].source
    if not isinstance(provider, str) or not provider or provider != provider.lower():
        raise ValueError("Current provider must be a nonempty lowercase key.")
    bout_keys = {}
    expected = set()
    linked_fights = []
    for fight in fights:
        bout = fight.source_bout_id
        try:
            day = date.fromisoformat(fight.event_date)
            if day.isoformat() != fight.event_date:
                raise ValueError("Noncanonical date")
        except (TypeError, ValueError) as error:
            raise ValueError(f"Invalid completed-fight date: {bout}") from error
        if (fight.source != provider or not isinstance(bout, str) or not bout
                or bout in bout_keys or not LAST_HISTORICAL_DATE < fight.event_date
                or day > moment.date()):
            raise ValueError(f"Duplicate, future or pre-cutoff current fight: {bout}")
        if not isinstance(fight.source_url, str) or not fight.source_url.startswith(
            "https://"
        ):
            raise ValueError(f"Current fight requires an HTTPS source URL: {bout}")
        source_ids = (fight.source_fighter_1_id, fight.source_fighter_2_id)
        if any(not isinstance(i, str) or not i for i in source_ids):
            raise ValueError(f"Missing provider fighter ID: {bout}")
        participants = tuple(links.get((provider, i)) for i in source_ids)
        if any(i not in known for i in participants) or participants[0] == (
            participants[1]
        ):
            raise ValueError(f"Unreviewed or conflicting fighter link: {bout}")
        names = (fight.fighter_1_name, fight.fighter_2_name)
        if fight.source_winner_label == "Draw/NC":
            if fight.winner_name is not None:
                raise ValueError(f"Ambiguous bout has a winner: {bout}")
        elif (fight.winner_name != fight.source_winner_label
              or names.count(fight.winner_name) != 1):
            raise ValueError(f"Unresolved completed-fight winner: {bout}")
        pair = (fight.event_date, *sorted(participants))
        if pair in occupied:
            raise ValueError(f"Duplicated historical or current matchup: {bout}")
        occupied.add(pair)
        bout_keys[bout] = (source_ids, participants)
        expected.update((bout, sid) for sid in source_ids)
        linked_fights.append(IdentifiedFight(fight, *participants).as_record())
    seen = set()
    linked_stats = []
    for row in stats:
        key = row.source_bout_id, row.source_fighter_id
        if row.source != provider or key not in expected or key in seen:
            raise ValueError(f"Duplicate or unmatched current statistics: {key}")
        seen.add(key)
        for landed, attempted in (
            (row.sig_strikes_landed, row.sig_strikes_attempted),
            (row.takedowns_landed, row.takedowns_attempted),
        ):
            if type(landed) is not int or type(attempted) is not int or (
                not 0 <= landed <= attempted
            ):
                raise ValueError(f"Invalid landed/attempted statistics: {key}")
        counts = ("fight_duration_seconds", "knockdowns", "submission_attempts",
                  "head_landed", "body_landed", "leg_landed", "distance_landed",
                  "clinch_landed", "ground_landed")
        if any(type(getattr(row, k)) is not int or getattr(row, k) < 0
               for k in counts) or (row.control_seconds is not None and (
                   type(row.control_seconds) is not int or row.control_seconds < 0
               )) or sum(getattr(row, k) for k in (
                   "head_landed", "body_landed", "leg_landed"
               )) != row.sig_strikes_landed or sum(getattr(row, k) for k in (
                   "distance_landed", "clinch_landed", "ground_landed"
               )) != row.sig_strikes_landed:
            raise ValueError(f"Invalid current fight totals: {key}")
        if (not row.fight_duration_seconds or row.control_seconds is not None
                and row.control_seconds > row.fight_duration_seconds):
            raise ValueError(f"Invalid fight duration/control time: {key}")
        source_ids, participants = bout_keys[row.source_bout_id]
        fighter_id = participants[source_ids.index(row.source_fighter_id)]
        linked_stats.append(IdentifiedFightStats(row, fighter_id).as_record())
    if seen != expected:
        raise ValueError(f"Missing statistics for participants: {sorted(expected - seen)[:3]}")
    for bout in bout_keys:
        pair = [row for row in stats if row.source_bout_id == bout]
        if (len(pair) != 2 or pair[0].source_fighter_id == pair[1].source_fighter_id
                or pair[0].fight_duration_seconds != pair[1].fight_duration_seconds):
            raise ValueError(f"Opponents have mismatched fight durations: {bout}")
    if any(_hash(path) != source_hashes[name] for name, path in zip(
        ("fights", "stats", "registry", "historical"), paths, strict=True
    )):
        raise ValueError("Current inputs changed during validation.")
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent, prefix=".upset-current-") as temp:
        staged = Path(temp) / "stage"
        staged.mkdir()
        for filename, rows in (
            ("fights_identified.jsonl", linked_fights),
            ("fight_stats_identified.jsonl", linked_stats),
        ):
            path = staged / filename
            with path.open("w", encoding="utf-8") as file:
                for record in rows:
                    file.write(json.dumps(record, allow_nan=False, sort_keys=True) + "\n")
            if [json.loads(line) for line in path.read_text().splitlines()] != rows:
                raise ValueError("Current identified export read-back differs.")
        report = {
            "status": "partial reviewed completed-fight stage; not model input",
            "observed_at_utc": moment.isoformat().replace("+00:00", "Z"),
            "provider": provider, "historical_cutoff": LAST_HISTORICAL_DATE,
            "fights": len(linked_fights), "fighter_stats": len(linked_stats),
            "input_sha256": source_hashes,
            "output_sha256": {name: _hash(staged / name) for name in (
                "fights_identified.jsonl", "fight_stats_identified.jsonl"
            )},
        }
        (staged / "manifest.json").write_text(json.dumps(report, indent=2,
                                                        sort_keys=True) + "\n")
        staged.rename(output)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fights", type=Path, required=True)
    parser.add_argument("--stats", type=Path, required=True)
    parser.add_argument("--registry", type=Path,
                        default=Path("data/mappings/fighter_registry.json"))
    parser.add_argument("--historical", type=Path, default=Path(
        "data/processed/kaggle_ufc_1994_2026/identified/fights_identified.jsonl"
    ))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = stage_completed_fights(
            args.fights, args.stats, args.registry, args.historical, args.output
        )
    except (ValueError, OSError) as error:
        parser.error(str(error))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
