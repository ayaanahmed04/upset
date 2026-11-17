"""Verified, dated experimental overall ratings; request-time lookup only."""

import hashlib
import json
from bisect import bisect_left
from collections import defaultdict
from copy import deepcopy
from datetime import date
from math import isclose, isfinite
from pathlib import Path

from upset.data.identity import validate_upset_fighter_id

VERSION = "upset_rating_experimental_v1"
PARTS = {"striking", "wrestling", "grappling", "resume"}


def _digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _day(value):
    try:
        valid = isinstance(value, str) and date.fromisoformat(value).isoformat() == value
    except ValueError:
        valid = False
    if not valid:
        raise ValueError("Use a canonical ISO date.")
    return value


def _number(value, low=None, high=None):
    return (type(value) in (int, float) and isfinite(value)
            and (low is None or value >= low) and (high is None or value <= high))


def _finite_tree(value):
    if isinstance(value, dict):
        return all(isinstance(key, str) and _finite_tree(item) for key, item in value.items())
    if isinstance(value, list):
        return all(_finite_tree(item) for item in value)
    if type(value) in (int, float):
        return isfinite(value)
    return value is None or isinstance(value, (str, bool))


def _verify_hashes(values):
    if not isinstance(values, dict) or not values:
        raise ValueError("Rating snapshot requires input hashes.")
    for path, expected in values.items():
        if (not isinstance(path, str) or not Path(path).is_absolute()
                or not isinstance(expected, str) or _digest(path) != expected):
            raise ValueError("Rating snapshot input hash differs: " + str(path))


def _validate_evaluation(evaluation):
    if not isinstance(evaluation, dict):
        raise TypeError("Rating evaluation must be an object.")
    if (evaluation.get("version") != VERSION
            or evaluation.get("engineering_checks_passed") is not True
            or evaluation.get("serving_eligible") is not True):
        raise ValueError("Experimental rating snapshot has not passed its serving checks.")
    if not isinstance(evaluation.get("evaluation_label"), str) or not evaluation["evaluation_label"].strip():
        raise ValueError("Rating evaluation needs an explicit evidence label.")
    record = evaluation.get("track_record")
    if not isinstance(record, dict):
        raise TypeError("Rating evaluation needs a measured track record.")
    wins, total, accuracy = (record.get(key) for key in ("wins", "total", "accuracy"))
    if type(total) is not int or type(wins) is not int or not 0 <= wins <= total:
        raise ValueError("Invalid rating track-record counts.")
    if (total == 0 and accuracy is not None or total > 0
            and (not _number(accuracy, 0, 1) or not isclose(accuracy, wins/total, abs_tol=1e-8))):
        raise ValueError("Rating track-record accuracy differs from its counts.")
    _day(record.get("from_date"))
    if not _finite_tree(evaluation):
        raise ValueError("Non-finite rating evaluation value.")


def _validate_row(row, metadata, previous):
    if not isinstance(row, dict):
        raise TypeError("Rating observation must be an object.")
    validate_upset_fighter_id(row["fighter_id"])
    day = _day(row["event_date"])
    if day >= metadata["before_exclusive"] or day > metadata["latest_event"]:
        raise ValueError("Rating row exceeds its snapshot cutoff.")
    score, peak, change, bouts = (row.get(key) for key in ("score", "peak", "change", "bouts"))
    if (type(score) is not int or not 60 <= score <= 99 or type(peak) is not int
            or not score <= peak <= 99 or type(bouts) is not int or bouts <= 0):
        raise ValueError("Invalid rating score, peak or bout count.")
    if bouts < 5 and score > 88:
        raise ValueError("Limited-history rating exceeds its declared cap.")
    if type(row.get("provisional")) is not bool or row["provisional"] != (bouts < 4):
        raise ValueError("Rating provisional flag differs from recorded history.")
    if previous is None:
        if change is not None or peak != score:
            raise ValueError("First rating needs null change and its own peak.")
    elif (day <= previous["event_date"] or bouts <= previous["bouts"]
          or type(change) is not int or change != score-previous["score"] or abs(change) > 5
          or peak != max(score, previous["peak"])):
        raise ValueError("Rating chronology, change or peak is inconsistent.")
    if (not _number(row.get("elo")) or not _number(row.get("raw_combined"), 0, 100)
            or not _number(row.get("skills_combined"), 0, 100)):
        raise ValueError("Invalid raw rating calculation.")
    parts = row.get("parts")
    if (not isinstance(parts, list) or len(parts) != 4
            or {part.get("key") for part in parts if isinstance(part, dict)} != PARTS):
        raise ValueError("Rating row requires its four distinct parts.")
    for part in parts:
        if (not isinstance(part.get("label"), str) or not part["label"].strip()
                or not _number(part.get("score"), 60, 99)
                or not _number(part.get("raw_score"), 0, 100)
                or not isinstance(part.get("metrics"), dict)):
            raise ValueError("Invalid rating component.")
    if not _finite_tree(row):
        raise ValueError("Non-finite rating snapshot value.")


class RatingSnapshot:
    """Read-only indexed history. Returned reports are detached copies."""

    def __init__(self, metadata, rows, evaluation):
        self.metadata = deepcopy(metadata)
        self.evaluation = deepcopy(evaluation)
        self.database = Path(metadata["input_database"]).resolve()
        histories = defaultdict(list)
        for row in rows:
            histories[row["fighter_id"]].append(deepcopy(row))
        self._rows = {uid: tuple(history) for uid, history in histories.items()}
        self._dates = {uid: tuple(row["event_date"] for row in history)
                       for uid, history in self._rows.items()}

    def estimate(self, database, report):
        if Path(database).resolve() != self.database:
            raise ValueError("Experimental rating belongs to a different database.")
        before = _day(report["before"])
        base = {"version": VERSION, "experimental": True, "validated": False,
                "before": before, "data_through": self.metadata["latest_event"],
                "scope": "career; updated only after recorded fights",
                "evaluation_label": self.evaluation["evaluation_label"],
                "track_record": deepcopy(self.evaluation["track_record"]),
                "model": deepcopy(self.metadata["model"]),
                "display_curve": deepcopy(self.metadata["display_curve"])}
        if before > self.metadata["before_exclusive"]:
            return {**base, "status": "unsupported_cutoff", "score": None,
                    "message": "No experimental overall-rating snapshot is available for this date."}
        uid = report["id"]
        position = bisect_left(self._dates.get(uid, ()), before)
        if not position:
            return {**base, "status": "no_history", "score": None,
                    "message": "Rated after first recorded UFC fight.", "history": []}
        selected = deepcopy(self._rows[uid][position-1])
        selected.pop("history", None)
        history = [{"date": row["event_date"], "score": row["score"], "change": row["change"],
                    **({"fight_id": row["fight_id"]} if "fight_id" in row else {})}
                   for row in self._rows[uid][:position]]
        return {**selected, **base, "status": "available", "history": history}


def load_snapshot(folder, database):
    """Verify the complete artifact once before exposing any numerical rating."""
    folder, database = Path(folder), Path(database)
    metadata = json.loads((folder/"manifest.json").read_text())
    if not isinstance(metadata, dict):
        raise TypeError("Rating manifest must be an object.")
    if (metadata.get("version") != VERSION or metadata.get("experimental") is not True
            or metadata.get("validated") is not False
            or Path(metadata["input_database"]).resolve() != database.resolve()
            or _digest(database) != metadata.get("database_sha256")):
        raise ValueError("Experimental rating snapshot version/database differs.")
    before, latest = _day(metadata["before_exclusive"]), _day(metadata["latest_event"])
    reference = _day(metadata["display_curve"]["reference_before"])
    if latest >= before or reference > before:
        raise ValueError("Rating snapshot date contract differs.")
    model = metadata["model"]
    if not isinstance(model, dict):
        raise TypeError("Rating model metadata must be an object.")
    if (not _number(model.get("resume_weight"), 0, 1)
            or model.get("skill_weights") != [.5, .3, .2] or not _finite_tree(metadata)):
        raise ValueError("Invalid experimental rating model metadata.")
    _verify_hashes(metadata["input_sha256"])
    outputs = metadata.get("output_sha256")
    if not isinstance(outputs, dict) or not {"ratings.jsonl", "evaluation.json"} <= outputs.keys():
        raise ValueError("Rating snapshot is missing bound outputs.")
    for name, expected in outputs.items():
        path = folder/name
        if not path.resolve().is_relative_to(folder.resolve()) or _digest(path) != expected:
            raise ValueError("Rating snapshot output hash differs: " + name)
    evaluation = json.loads((folder/"evaluation.json").read_text())
    _validate_evaluation(evaluation)
    rows, previous = [], {}
    for line in (folder/"ratings.jsonl").read_text().splitlines():
        row = json.loads(line)
        if not isinstance(row, dict):
            raise TypeError("Rating observation must be an object.")
        _validate_row(row, metadata, previous.get(row["fighter_id"]))
        previous[row["fighter_id"]] = row
        rows.append(row)
    if not rows:
        raise ValueError("Experimental rating snapshot contains no ratings.")
    return RatingSnapshot(metadata, rows, evaluation)
