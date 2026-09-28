"""Convert one verified raw Cito card to canonical bouts and a link-review queue."""

import argparse
import hashlib
import json
import re
from collections import defaultdict
from dataclasses import asdict, replace
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from upset.data.audit_cito_round_totals import STAT_FIELDS, _normalize_stats
from upset.data.collect_cito_card import COMPONENTS, _read_saved
from upset.data.identity import load_fighter_registry
from upset.data.models import FightStats
from upset.data.normalization import normalize_cito_event, normalize_cito_fight

METHODS = {
    "KO/TKO": "KO/TKO", "SUB": "Submission",
    "U-DEC": "Decision - Unanimous", "S-DEC": "Decision - Split",
}
_CLOCK = re.compile(r"([0-5]):([0-5][0-9])\Z")


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_card(directory: Path):
    manifest_path = directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("status") != (
        "raw card captured; stats and bout coverage unverified"
    ) or manifest.get("coverage_verified") is not False:
        raise ValueError("Unrecognized raw card manifest.")
    slug = manifest["event_slug"]
    payloads = {}
    for kind in COMPONENTS:
        path = directory / f"{kind}.json"
        if _hash(path) != manifest["sha256"].get(kind):
            raise ValueError(f"Raw card hash differs: {kind}")
        saved, count = _read_saved(path, kind, slug)
        if saved["observed_at_utc"] != manifest["observed_at_utc"].get(kind):
            raise ValueError(f"Raw card acquisition timestamp differs: {kind}")
        if kind == "bouts" and count != manifest["listed_bouts"]:
            raise ValueError("Raw card bout count differs from manifest.")
        payloads[kind] = saved["response"]["data"]
    return payloads, {name: _hash(directory / f"{name}.json")
                      for name in COMPONENTS}, _hash(manifest_path)


def _index(rows, label):
    if not isinstance(rows, list):
        raise TypeError(f"Expected a list of {label}.")
    result = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str) or (
            not row["id"] or row["id"] in result
        ):
            raise ValueError(f"Duplicate or invalid {label} ID.")
        result[row["id"]] = row
    return result


def _bout_signature(row):
    fighters = row.get("fighters")
    if not isinstance(fighters, list) or len(fighters) != 2:
        raise ValueError("Card bout lacks exactly two fighters.")
    return (
        row["id"], row.get("eventSlug"), row.get("status"),
        row.get("isCancelled"), row.get("hasStats"),
        row.get("winnerFighterSlug"), row.get("method"),
        row.get("resultRound"), row.get("resultTime"),
        tuple((f.get("fighterId"), f.get("fighterSlug"),
               f.get("fighterName"), f.get("outcome")) for f in fighters),
    )


def _duration(bout) -> int:
    number = bout.get("resultRound")
    clock = bout.get("resultTime")
    match = _CLOCK.fullmatch(clock) if isinstance(clock, str) else None
    if type(number) is not int or not 1 <= number <= 5 or not match:
        raise ValueError(f"Invalid completed-bout round or time: {bout['id']}")
    minutes, seconds = (int(x) for x in match.groups())
    if minutes == 5 and seconds != 0:
        raise ValueError(f"Invalid fight clock: {bout['id']}")
    total = 300 * (number - 1) + 60 * minutes + seconds
    if total == 0:
        raise ValueError(f"Zero observed duration: {bout['id']}")
    return total


def _normalize_card(payloads):
    event_raw, bouts_raw, stats_raw = (
        payloads["event"], payloads["bouts"], payloads["stats"]
    )
    if not isinstance(event_raw, dict) or not isinstance(stats_raw, dict):
        raise TypeError("Event and stats responses need object data.")
    event = normalize_cito_event(event_raw)
    day = date.fromisoformat(event.event_date)
    if (day.isoformat() != event.event_date or event_raw.get("status") != "completed"
            or event_raw.get("hasStats") is not True or day <= date(2026, 3, 7)):
        raise ValueError("Event is not a completed post-snapshot UFC card with stats.")
    other_event = stats_raw.get("event")
    if not isinstance(other_event, dict) or any(
        other_event.get(key) != event_raw.get(key)
        for key in ("id", "slug", "eventDate", "status", "hasStats")
    ):
        raise ValueError("Stats event does not match event detail.")
    listed = _index(bouts_raw, "listed bout")
    embedded_bouts = {}
    for label, embedded in (
        ("event", event_raw.get("bouts")),
        ("stats", stats_raw.get("bouts")),
    ):
        indexed = _index(embedded, label + " bout")
        embedded_bouts[label] = indexed
        if set(indexed) != set(listed) or any(
            _bout_signature(indexed[key]) != _bout_signature(row)
            for key, row in listed.items()
        ):
            raise ValueError(f"{label} bout list differs from provider listing.")

    raw_totals = stats_raw.get("boutStats")
    raw_rounds = stats_raw.get("roundStats")
    if not isinstance(raw_totals, list) or not isinstance(raw_rounds, list):
        raise TypeError("Card lacks fighter totals or round rows.")
    totals = defaultdict(list)
    rounds = defaultdict(list)
    for row in raw_totals:
        if not isinstance(row, dict):
            raise TypeError("Invalid fighter-total row.")
        bid = str(row.get("boutId"))
        totals[bid].append(_normalize_stats(row, bid, total=True))
    for row in raw_rounds:
        if not isinstance(row, dict):
            raise TypeError("Invalid round-stat row.")
        bid = str(row.get("boutId"))
        rounds[(bid, row.get("fighterSlug"))].append(
            _normalize_stats(row, bid, total=False)
        )
    if set(totals) != set(listed) or len(raw_totals) != 2 * len(listed):
        raise ValueError("Card totals do not cover exactly two fighters per bout.")
    fights, stats, participants, slug_differences = [], [], {}, []
    for bid, raw in listed.items():
        if (raw.get("status") != "completed" or raw.get("isCancelled") is not False
                or raw.get("hasStats") is not True):
            raise ValueError(f"Card includes an incomplete/cancelled bout: {bid}")
        if raw.get("method") not in METHODS:
            raise ValueError(f"Unreviewed result method: {bid}/{raw.get('method')}")
        raw_fighters = raw["fighters"]
        slugs = [f.get("fighterSlug") for f in raw_fighters]
        ids = [f.get("fighterId") for f in raw_fighters]
        names = [f.get("fighterName") for f in raw_fighters]
        if (any(not isinstance(v, str) or not v for v in slugs + ids + names)
                or len(set(slugs)) != 2 or len(set(ids)) != 2
                or len(set(names)) != 2):
            raise ValueError(f"Unresolved bout participant: {bid}")
        winner = raw.get("winnerFighterSlug")
        if winner not in slugs or any(f.get("outcome") != (
            "win" if f["fighterSlug"] == winner else "loss"
        ) for f in raw_fighters):
            raise ValueError(f"Winner disagrees with participant outcomes: {bid}")
        fight = normalize_cito_fight(raw, event=event)
        fight = replace(
            fight, result_method=METHODS[raw["method"]],
            event_date=event.event_date,
            source_url=f"https://api.citoapi.com/api/v1/ufc/events/{event.source_event_slug}/bouts",
            source_winner_label=fight.winner_name,
        )
        duration = _duration(raw)
        # The observed provider sample has two bout-slug aliases. A fighter's
        # name is safe for *pairing two rows within this one bout* only; the
        # lasting identity still comes from its separate reviewed profile ID.
        indexed_totals = {row.fighter_name: row for row in totals[bid]}
        if len(indexed_totals) != 2 or set(indexed_totals) != set(names) or (
            len({row.source_fighter_slug for row in totals[bid]}) != 2
        ):
            raise ValueError(f"Bout totals have wrong fighters: {bid}")
        reference = {(str(row.get("boutId")), row.get("fighterSlug")): row
                     for row in raw_totals if row.get("boutId") == bid}
        for label, source_row in (
            ("event", embedded_bouts["event"][bid]),
            ("listing", raw),
            ("stats", embedded_bouts["stats"][bid]),
        ):
            embedded = source_row.get("boutStats")
            if not isinstance(embedded, list) or len(embedded) != 2 or {
                (str(row.get("boutId")), row.get("fighterSlug")): row
                for row in embedded if isinstance(row, dict)
            } != reference:
                raise ValueError(
                    f"{label} fighter totals disagree with card totals: {bid}"
                )
        for fighter in raw_fighters:
            slug = fighter["fighterSlug"]
            value = indexed_totals[fighter["fighterName"]]
            stats_slug = value.source_fighter_slug
            if slug != stats_slug:
                slug_differences.append({
                    "source_bout_id": bid, "cito_fighter_id": fighter["fighterId"],
                    "bout_fighter_slug": slug, "stats_fighter_slug": stats_slug,
                })
            seen_rounds = rounds.get((bid, stats_slug), [])
            if sorted(row.round_number for row in seen_rounds) != list(range(
                1, raw["resultRound"] + 1
            )) or any(row.fighter_name != value.fighter_name for row in seen_rounds):
                raise ValueError(f"Incomplete or wrong round history: {bid}/{stats_slug}")
            if any(getattr(value, field) != sum(getattr(r, field)
                                                for r in seen_rounds)
                   for field in STAT_FIELDS):
                raise ValueError(f"Round totals differ from fight totals: {bid}/{stats_slug}")
            if value.control_seconds > duration:
                raise ValueError(f"Control exceeds bout duration: {bid}/{slug}")
            stats.append(FightStats(
                source="cito", source_bout_id=bid,
                source_fighter_id=fighter["fighterId"],
                fight_duration_seconds=duration,
                source_time_format="5 min rounds",
                knockdowns=value.knockdowns,
                sig_strikes_landed=value.sig_strikes_landed,
                sig_strikes_attempted=value.sig_strikes_attempted,
                takedowns_landed=value.takedowns_landed,
                takedowns_attempted=value.takedowns_attempted,
                submission_attempts=value.submission_attempts,
                control_seconds=value.control_seconds,
                head_landed=value.head_landed, body_landed=value.body_landed,
                leg_landed=value.leg_landed, distance_landed=value.distance_landed,
                clinch_landed=value.clinch_landed, ground_landed=value.ground_landed,
            ))
            provider_id = fighter["fighterId"]
            previous = participants.setdefault(provider_id, (
                fighter["fighterName"], slug,
            ))
            if previous != (fighter["fighterName"], slug):
                raise ValueError(f"Provider fighter identity changed on card: {provider_id}")
        fights.append(fight)
    if set(rounds) != {(bid, row.source_fighter_slug)
                      for bid, rows in totals.items() for row in rows}:
        raise ValueError("Unexpected round rows for a different bout or fighter.")
    return fights, stats, participants, len(raw_rounds), slug_differences


def _identity_review(participants, registry):
    by_name = defaultdict(list)
    ufcstats_ids = defaultdict(list)
    linked = {}
    for identity in registry.identities:
        by_name[identity.display_name.casefold()].append(identity.upset_fighter_id)
    for link in registry.provider_links:
        if link.provider == "ufcstats":
            ufcstats_ids[link.upset_fighter_id].append(link.provider_fighter_id)
        elif link.provider == "cito":
            linked[link.provider_fighter_id] = link.upset_fighter_id
    review = []
    for provider_id, (name, slug) in sorted(participants.items()):
        candidates = sorted(by_name[name.casefold()])
        review.append({
            "cito_fighter_id": provider_id, "fighter_name": name,
            "fighter_slug": slug, "reviewed_upset_fighter_id": linked.get(provider_id),
            "suggested_candidates_by_name_only": [
                {"upset_fighter_id": uid, "ufcstats_fighter_ids": sorted(ufcstats_ids[uid])}
                for uid in candidates
            ],
        })
    return review


def export_cito_card(card: Path, registry_path: Path, output: Path) -> dict:
    """Export only after full read-back checks; names never become identity links."""
    if output.exists() or output.resolve() == card.resolve():
        raise ValueError("Output exists or overlaps raw input.")
    payloads, input_hashes, card_hash = _read_card(card)
    fights, stats, participants, round_rows, slug_differences = _normalize_card(
        payloads
    )
    registry = load_fighter_registry(registry_path)
    review = _identity_review(participants, registry)
    outstanding = sum(row["reviewed_upset_fighter_id"] is None for row in review)
    if any(_hash(card / f"{name}.json") != digest
           for name, digest in input_hashes.items()) or _hash(
               card / "manifest.json"
           ) != card_hash:
        raise ValueError("Raw card changed during conversion.")
    registry_hash = _hash(registry_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent, prefix=".upset-cito-export-") as temp:
        folder = Path(temp) / "export"
        folder.mkdir()
        contents = {
            "fights.jsonl": [asdict(row) for row in fights],
            "fight_stats.jsonl": [asdict(row) for row in stats],
            "fighter_link_review.json": review,
        }
        for name, rows in contents.items():
            path = folder / name
            with path.open("w", encoding="utf-8") as file:
                if name.endswith(".jsonl"):
                    for row in rows:
                        file.write(json.dumps(row, allow_nan=False, sort_keys=True) + "\n")
                else:
                    file.write(json.dumps(rows, allow_nan=False, sort_keys=True,
                                          indent=2) + "\n")
            reread = ([json.loads(line) for line in path.read_text().splitlines()]
                      if name.endswith(".jsonl") else json.loads(path.read_text()))
            if reread != rows:
                raise ValueError(f"Cito export read-back differs: {name}")
        if _hash(registry_path) != registry_hash:
            raise ValueError("Fighter registry changed during conversion.")
        report = {
            "status": "canonical conversion verified; fighter links require review",
            "event_slug": payloads["event"]["slug"],
            "event_date": payloads["event"]["eventDate"],
            "fights": len(fights), "fighter_stats": len(stats),
            "round_rows_reconciled": round_rows,
            "provider_slug_differences": slug_differences,
            "provider_fighters": len(review), "unlinked_provider_fighters": outstanding,
            "input_sha256": {**input_hashes, "card_manifest": card_hash,
                             "fighter_registry": registry_hash},
            "output_sha256": {name: _hash(folder / name) for name in contents},
            "current_coverage_verified": False,
        }
        (folder / "manifest.json").write_text(
            json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )
        folder.rename(output)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--card", type=Path, required=True)
    parser.add_argument("--registry", type=Path,
                        default=Path("data/mappings/fighter_registry.json"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = export_cito_card(args.card, args.registry, args.output)
    except (ValueError, KeyError, OSError, TypeError) as error:
        parser.error(str(error))
    print(json.dumps(report, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
