"""Serve the UPSET forecast adjustment (revision 5.2) on top of a v5.1 rating snapshot.

* Past fights: the adjusted walk-forward forecast from the build replaces the v5.1 value, so every
  "forecast going in", Upset Tracker chance and replay uses the same model.
* Upcoming or any-date matchups: the v5.1 matchup is adjusted on the fly from both fighters' ages and
  debut starting points at the cutoff, using only fights before it.

The rating (60-99) is untouched. Everything is checked against the build's hashes before use.
"""

import hashlib
import json
import math
import sqlite3
from bisect import bisect_left
from contextlib import closing
from copy import deepcopy
from datetime import date
from pathlib import Path

VERSION = "forecast_adjustment_v1"
WEIGHT_ORDER = ("Strawweight", "Flyweight", "Bantamweight", "Featherweight", "Lightweight", "Welterweight",
                "Middleweight", "Light Heavyweight", "Heavyweight")


def completed_years(born, day):
    return day.year - born.year - ((day.month, day.day) < (born.month, born.day))


def weight_class_check(forecast, names, divisions):
    """The forecast was only tested on real fights, which happen within one weight class, and has no size
    term. Two or more classes apart, or men against women, it gives no win chance; one class apart it notes it."""
    if not forecast or forecast.get("status") != "available" or not all(divisions):
        return forecast
    women = [d.startswith("Women's ") for d in divisions]
    base = [d.removeprefix("Women's ") for d in divisions]
    if any(b not in WEIGHT_ORDER for b in base):
        return forecast
    gap = abs(WEIGHT_ORDER.index(base[0]) - WEIGHT_ORDER.index(base[1]))
    if women[0] != women[1] or gap >= 2:
        apart = "men's and women's divisions" if women[0] != women[1] else f"{gap} weight classes apart"
        return {"version": forecast.get("version"), "status": "unavailable", "reason": "weight_classes",
                "divisions": list(divisions),
                "message": f"No win chance for this matchup: {names[0]} last fought at {divisions[0]} and {names[1]} at "
                           f"{divisions[1]}, {apart}. UPSET's forecast is tested only on real fights within a weight "
                           "class and doesn't account for size."}
    if gap == 1:
        return {**forecast, "division_note": f"{names[0]} last fought at {divisions[0]} and {names[1]} at {divisions[1]}. "
                                             "The forecast doesn't account for size."}
    return forecast


def _logit(p):
    p = min(max(p, 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


def _sigmoid(x):
    return 1 / (1 + math.exp(-max(min(x, 40), -40)))


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class ForecastAdjustment:
    def __init__(self, folder, database, rating_snapshot):
        folder = Path(folder)
        self.manifest = json.loads((folder / "manifest.json").read_text())
        inputs = self.manifest["inputs"]
        db_manifest = json.loads((Path(database).parent / "manifest.json").read_text())
        if (self.manifest.get("version") != VERSION or inputs["database_sha256"] != db_manifest["database_sha256"]
                or inputs["rating_manifest_sha256"] != _sha(Path(rating_snapshot) / "manifest.json")):
            raise ValueError("Forecast adjustment does not match this database and rating snapshot.")
        for name, expected in self.manifest["output_sha256"].items():
            if _sha(folder / name) != expected:
                raise ValueError(f"Forecast adjustment file {name} fails its hash check.")
        model = self.manifest["model"]
        self.w = model["weights"]
        self.pivot, self.decay = model["age_pivot"], model["decay"]
        self.revision = self.manifest["revision"]
        self.adjusted = {}
        with open(folder / "forecasts.jsonl") as stream:
            for line in stream:
                row = json.loads(line)
                self.adjusted[row["fight_id"]] = row["forecast"]
        self.edges = json.loads((folder / "debut_edges.json").read_text())
        self.births, self.dates, self.classes = {}, {}, {}
        with closing(sqlite3.connect(database)) as db:
            for uid, profile in db.execute("SELECT id,profile FROM fighters"):
                dob = (json.loads(profile or "{}") or {}).get("date_of_birth")
                try:
                    self.births[uid] = date.fromisoformat(dob) if dob else None
                except ValueError:
                    self.births[uid] = None
            for day, payload in db.execute("SELECT event_date,payload FROM fights ORDER BY event_date"):
                p = json.loads(payload)
                for key in ("upset_fighter_1_id", "upset_fighter_2_id"):
                    uid = p.get(key)
                    if uid:
                        self.dates.setdefault(uid, []).append(day)
                        self.classes.setdefault(uid, []).append((day, (p.get("weight_class") or "").lower()))

    # ------------------------------------------------------------------ features
    def age(self, uid, day):
        born = self.births.get(uid)
        return (date.fromisoformat(day) - born).days / 365.25 if born else None

    def age_years(self, uid, day):
        born = self.births.get(uid)
        return completed_years(born, date.fromisoformat(day)) if born else None

    def start(self, uid, day):
        edge = self.edges.get(uid)
        if not edge or edge["date"] >= day:
            return 0.0
        prior = bisect_left(self.dates.get(uid, []), day)
        return edge["edge"] * self.decay ** (prior - 1) if prior >= 1 else 0.0

    def heavy(self, a, b, day, division=None):
        if division:
            return "heavyweight" in division.lower()
        last = []
        for uid in (a, b):
            rows = [c for d, c in self.classes.get(uid, []) if d < day and c]
            last.append(rows[-1] if rows else "")
        return all("heavyweight" in c for c in last)

    def explain(self, p, a, b, day, division=None):
        ages = [self.age(a, day), self.age(b, day)]
        term = lambda x: max((x if x is not None else self.pivot) - self.pivot, 0)
        heavy = self.heavy(a, b, day, division)
        base = self.w["forecast"] * _logit(p)
        age_part = (self.w["age_heavy"] if heavy else self.w["age_light"]) * (term(ages[0]) - term(ages[1]))
        start_part = self.w["start"] * (self.start(a, day) - self.start(b, day))
        p_base, p_age, p_full = _sigmoid(base), _sigmoid(base + age_part), _sigmoid(base + age_part + start_part)
        return p_full, {"v5_1": round(p, 4), "ages": [self.age_years(a, day), self.age_years(b, day)],
                        "heavy_division": heavy, "age_effect": round(p_age - p_base, 4),
                        "start_effect": round(p_full - p_age, 4)}

    # ------------------------------------------------------------------ apply
    def apply(self, snapshot):
        """Swap in adjusted past forecasts and wrap the live matchup."""
        for fid, item in snapshot.forecasts.items():
            if fid in self.adjusted:
                item.setdefault("forecast_v5_1", item["forecast"])
                item["forecast"] = self.adjusted[fid]
        metrics = self.manifest["metrics"]
        evaluation = snapshot.evaluation["metrics"]
        evaluation.setdefault("v5_1_forecast", deepcopy(evaluation["v5_forecast"]))
        for name in ("train", "test", "recent"):
            evaluation["v5_forecast"][name] = {**evaluation["v5_forecast"].get(name, {}), **metrics[name]["adjusted"]}
        original = snapshot.matchup

        def matchup(a, b, division=None):
            out = original(a, b)
            ids = a.get("fighter_id"), b.get("fighter_id")
            if out.get("status") != "available" or not all(ids):
                return out
            day = a.get("before")
            p, factors = self.explain(out["probabilities"][0], ids[0], ids[1], day, division)
            ratio = max(p, 1 - p) / max(1e-9, min(p, 1 - p))
            out.update(probabilities=[p, 1 - p], favorite=None if abs(p - .5) < .01 else (0 if p > .5 else 1),
                       odds="even" if ratio < 1.05 else f"{ratio:.1f}-to-1", factors=factors, revision=self.revision,
                       record={"since_2019": metrics["test"]["adjusted"], "since_2025": metrics["recent"]["adjusted"]},
                       label="UPSET forecast · includes age and a starting point from debut odds · walk-forward tested, not betting advice")
            return out

        snapshot.matchup = matchup
        snapshot.forecast_adjustment = self
        return snapshot
