"""Verify and serve UPSET Rating v5: the number, its stars, attributes and matchup forecasts.

Request-time lookup only. The snapshot is verified once at startup: database, inputs and
outputs are hash-bound, the evaluation must pass its gate, and every dated row is checked
against the declared scale and the rating's rules before any number is shown.
"""

import json
import math
from bisect import bisect_left
from collections import defaultdict
from copy import deepcopy
from datetime import date
from pathlib import Path

from upset.ratings import serving

VERSION = "upset_rating_v5"
ROOT = Path(__file__).resolve().parents[3]
PART_KEYS = ("striking", "wrestling", "grappling", "results")
STALE_DAYS = 730


def _path(value):
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def _sigmoid(x):
    return 1 / (1 + math.exp(-x)) if x >= 0 else math.exp(x) / (1 + math.exp(x))


def passes_gate(evaluation):
    integrity, metrics = evaluation["integrity"], evaluation["metrics"]
    return (evaluation.get("version") == VERSION
            and evaluation["engineering_checks_passed"] is True
            and integrity["wrong_direction_updates"] == 0
            and integrity["pass_rule_violations"] == 0
            and integrity["title_winner_below_after_fight"] == 0
            and metrics["v5"]["test"]["bouts"] >= 2000
            and metrics["v5"]["test"]["log_loss"] <= metrics["v4"]["test"]["log_loss"] + .002
            and metrics["v5_forecast"]["test"]["log_loss"] <= metrics["v4"]["test"]["log_loss"] - .004
            and .85 <= evaluation["calibration_slope"]["train"] <= 1.15
            and evaluation["distribution"]["at_cap"] <= 5
            and ("v5_display" not in metrics
                 or metrics["v5_display"]["test"]["log_loss"] < metrics["elo64_decay"]["test"]["log_loss"]))


def stars_for(score, stars):
    for level in stars["levels"]:
        if score >= level["min_score"]:
            return level["stars"], level["label"]
    return stars["bottom"]["stars"], stars["bottom"]["label"]


def validate_row(row, previous, metadata):
    scale, stars = metadata["scale"], metadata["stars"]
    serving._day(row["event_date"])
    score = row["score"]
    exact = scale["center_score"] + scale["points_per_unit"] * (row["strength"] - scale["center_strength"])
    expected_stars = stars_for(score, stars)
    if (type(score) is not int or not scale["floor"] <= score <= scale["cap"]
            or not (abs(score - exact) <= .5001 or (score == scale["cap"] and exact > score)
                    or (score == scale["floor"] and exact < score))
            or (row["stars"], row["tier"]) != expected_stars
            or not serving._number(row["variance"], 0, scale["variance_prior"] + 1e-9)
            or type(row["bouts"]) is not int or row["bouts"] < 1
            or row["provisional"] is not (row["bouts"] < scale.get("provisional_below", 4))
            or [part["key"] for part in row["parts"]][-1] != "results"
            or not set(part["key"] for part in row["parts"]) <= set(PART_KEYS)
            or not all(type(part["score"]) is int and scale["floor"] <= part["score"] <= scale["cap"]
                       for part in row["parts"])
            or not serving._number(row["forecast"]["strength"])
            or not serving._number(row["forecast"]["variance"], 0)
            or not serving._finite_tree(row)):
        raise ValueError("Invalid v5 rating row.")
    if previous is None:
        if row["change"] is not None or row["peak"] != score:
            raise ValueError("Invalid first v5 rating row.")
        return
    outcomes = set(row["last_outcomes"])
    if (row["event_date"] <= previous["event_date"] or row["change"] != score - previous["score"]
            or row["previous_score"] != previous["score"] or row["peak"] != max(previous["peak"], score)
            or row["bouts"] < previous["bouts"]
            or (outcomes == {"win"} and score < previous["score"])
            or (outcomes == {"loss"} and score > previous["score"])):
        raise ValueError("V5 rating history breaks its rules.")


class RatingSnapshot:
    """Read-only indexed history. Returned reports are detached copies."""

    def __init__(self, metadata, rows, evaluation, forecasts):
        self.metadata = deepcopy(metadata)
        self.evaluation = deepcopy(evaluation)
        self.database = _path(metadata["input_database"]).resolve()
        histories = defaultdict(list)
        for row in rows:
            histories[row["fighter_id"]].append(deepcopy(row))
        self._rows = {uid: tuple(history) for uid, history in histories.items()}
        self._dates = {uid: tuple(row["event_date"] for row in history) for uid, history in self._rows.items()}
        self.forecasts = forecasts

    def _base(self, before):
        scale = self.metadata["scale"]
        evaluation = self.evaluation
        return {"version": VERSION, "experimental": True, "validated": False,
                "before": before, "data_through": self.metadata["latest_event"],
                "scope": "UFC career; changes only after a recorded fight",
                "evaluation_label": evaluation["evaluation_label"],
                "track_record": deepcopy(evaluation["track_record"]),
                "model": {key: self.metadata["model"][key] for key in ("v0", "tau2", "beta", "pass_rule")},
                "display_curve": deepcopy(self.metadata["display_curve"]),
                "scale": {**{key: scale[key] for key in ("center_score", "points_per_doubling", "floor", "cap", "rule")},
                          "provisional_below": scale.get("provisional_below", 4), "display_ramp": scale.get("display_ramp", 0)},
                "revision": self.metadata.get("revision", "5.0"),
                "star_levels": deepcopy(self.metadata["stars"]),
                "forecast_record": {name: deepcopy(evaluation["metrics"]["v5_forecast"][name]) for name in ("test", "recent")},
                "market_check": deepcopy(evaluation.get("market"))}

    def estimate(self, database, report):
        if Path(database).resolve() != self.database:
            raise ValueError("UPSET rating belongs to a different database.")
        before = serving._day(report["before"])
        base = self._base(before)
        if before > self.metadata["before_exclusive"]:
            return {**base, "status": "unsupported_cutoff", "score": None,
                    "message": "No UPSET rating snapshot is available for this date."}
        uid = report["id"]
        position = bisect_left(self._dates.get(uid, ()), before)
        if not position:
            return {**base, "status": "no_history", "score": None,
                    "message": "Rated after first decisive UFC fight.", "history": []}
        selected = deepcopy(self._rows[uid][position - 1])
        history = [{"date": row["event_date"], "score": row["score"], "change": row["change"], "stars": row["stars"],
                    "last_outcomes": list(row["last_outcomes"]),
                    **({"fight_id": row["fight_id"]} if "fight_id" in row else {}),
                    **({"outcome_hold": row["outcome_hold"]} if row["outcome_hold"] else {}),
                    **({"locked_by": list(row["locked_by"])} if row["locked_by"] else {})}
                   for row in self._rows[uid][:position]]
        age = (date.fromisoformat(before) - date.fromisoformat(selected["event_date"])).days
        return {**selected, **base, "status": "available", "history": history,
                "days_since_rated_fight": age, "rating_is_stale": age > STALE_DAYS}

    def matchup(self, a, b):
        """Forecast for two available estimates at the same cutoff, from the unconstrained model."""
        if a.get("status") != "available" or b.get("status") != "available":
            return {"version": VERSION, "status": "unavailable",
                    "message": "A forecast needs a rated UFC fight for both fighters."}
        fa, fb = a["forecast"], b["forecast"]
        g = 1 / math.sqrt(1 + 3 * (fa["variance"] + fb["variance"]) / math.pi ** 2)
        p = _sigmoid(g * (fa["strength"] - fb["strength"]))
        ratio = max(p, 1 - p) / max(1e-9, min(p, 1 - p))
        record = self.evaluation["metrics"]["v5_forecast"]
        return {"version": VERSION, "status": "available", "probabilities": [p, 1 - p],
                "favorite": None if abs(p - .5) < .01 else (0 if p > .5 else 1),
                "odds": "even" if ratio < 1.05 else f"{ratio:.1f}-to-1",
                "rating_gap": a["score"] - b["score"],
                "provisional": bool(a["provisional"] or b["provisional"]),
                "stale": bool(a["rating_is_stale"] or b["rating_is_stale"]),
                "record": {"since_2019": record["test"], "since_2025": record["recent"]},
                "market_check": deepcopy(self.evaluation.get("market")),
                "label": "UPSET forecast · walk-forward tested, not betting advice"}


def load_snapshot(folder, database):
    folder, database = Path(folder), Path(database)
    metadata = json.loads((folder / "manifest.json").read_text())
    if (not isinstance(metadata, dict) or metadata.get("version") != VERSION
            or metadata.get("experimental") is not True or metadata.get("validated") is not False
            or not serving._finite_tree(metadata)
            or _path(metadata["input_database"]).resolve() != database.resolve()
            or serving._digest(database) != metadata["database_sha256"]):
        raise ValueError("UPSET rating v5 snapshot version/database differs.")
    serving._day(metadata["latest_event"])
    if not metadata["latest_event"] < serving._day(metadata["before_exclusive"]):
        raise ValueError("V5 snapshot date contract differs.")
    for name, expected in metadata["input_sha256"].items():
        if serving._digest(_path(name)) != expected:
            raise ValueError("V5 snapshot input hash differs: " + name)
    outputs = metadata["output_sha256"]
    if set(outputs) != {"ratings.jsonl", "evaluation.json", "forecasts.jsonl"}:
        raise ValueError("Missing required v5 outputs.")
    for name, expected in outputs.items():
        if serving._digest(folder / name) != expected:
            raise ValueError("V5 snapshot output hash differs: " + name)
    evaluation = json.loads((folder / "evaluation.json").read_text())
    if not passes_gate(evaluation):
        raise ValueError("V5 snapshot failed its serving gate.")
    levels = metadata["stars"]["levels"]
    if any(a["min_score"] <= b["min_score"] or a["stars"] <= b["stars"] for a, b in zip(levels, levels[1:])):
        raise ValueError("V5 star levels must strictly descend.")
    rows, previous = [], {}
    with (folder / "ratings.jsonl").open() as stream:
        for line in stream:
            row = json.loads(line)
            uid = row["fighter_id"]
            validate_row(row, previous.get(uid), metadata)
            rows.append(row)
            previous[uid] = row
    if not rows:
        raise ValueError("V5 snapshot contains no ratings.")
    scores = {(row["fighter_id"], row["event_date"]): row for row in rows}
    for row in rows:
        if len(row["fights"]) != 1 or row["fights"][0]["outcome"] != "win":
            continue
        loser = scores.get((row["fights"][0]["opponent_id"], row["event_date"]))
        if loser is not None and len(loser["fights"]) == 1 and loser["score"] > row["score"]:
            raise ValueError("V5 snapshot breaks the pass rule: " + row["fights"][0]["fight_id"])
    forecasts = {}
    with (folder / "forecasts.jsonl").open() as stream:
        for line in stream:
            item = json.loads(line)
            if not serving._number(item["forecast"], 0, 1):
                raise ValueError("Invalid v5 forecast.")
            forecasts[item["fight_id"]] = item
    return RatingSnapshot(metadata, rows, evaluation, forecasts)
