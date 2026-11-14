"""Skill profiles for the site: where a fighter sits among active UFC fighters on eight skills,
with an uncertainty band, plus the fighters whose skill profile is most similar.

Source: the multi-skill model (src/upset/ratings/multiskill_research.py). Every skill is
opponent-adjusted and built only from recorded UFC fights. Descriptive, not a prediction.
"""

import json
import math
from bisect import bisect_left
from pathlib import Path

# Each skill blends related measurements from the model (side, key, weight), so one narrow stat does not
# decide it: power counts knockdowns and KO/TKO wins, submissions count attempts and submission wins.
SKILLS = [([("offense", "str", 1)], "Striking volume", "Strikes landed at range, adjusted for opponents' defense"),
          ([("defense", "str", 1)], "Striking defense", "How few strikes opponents land at range"),
          ([("offense", "kd", .5), ("offense", "ko", .5)], "Knockout power", "Knockdowns scored and KO/TKO wins, adjusted for opponents' durability"),
          ([("defense", "ko", .5), ("defense", "kd", .5)], "Durability", "How hard this fighter is to drop or stop"),
          ([("offense", "td", 1)], "Takedowns", "Takedowns landed, adjusted for opponents' takedown defense"),
          ([("defense", "td", 1)], "Takedown defense", "How few takedowns opponents complete"),
          ([("offense", "ctrl", 1)], "Control", "Time spent in control on the ground or against the fence"),
          ([("offense", "sub", .5), ("offense", "subwin", .5)], "Submission threat", "Submission attempts and submission wins, adjusted for opponents")]
# "Fights most like" compares what fighters do more than how good they are: offense counts most.
STYLE = [(1.0, [("offense", "str", 1)]), (.7, [("offense", "clinch", 1)]), (1.0, [("offense", "gnd", 1)]),
         (1.0, [("offense", "kd", .5), ("offense", "ko", .5)]), (1.2, [("offense", "td", 1)]), (1.2, [("offense", "ctrl", 1)]),
         (1.0, [("offense", "sub", .5), ("offense", "subwin", .5)]), (.6, [("defense", "str", 1)]), (.6, [("defense", "td", 1)]),
         (.5, [("defense", "ko", .5), ("defense", "kd", .5)])]
DIVISION_STEP = 0.6         # distance added per weight class apart; two or more classes apart come last
MIN_FIGHTS = 3
SIMILAR_MIN_FIGHTS = 5      # only suggest fighters whose own profile is well measured
DIVISIONS = ["strawweight", "flyweight", "bantamweight", "featherweight", "lightweight", "welterweight",
             "middleweight", "light heavyweight", "heavyweight"]


def division_index(label):
    text = (label or "").lower()
    if "light heavyweight" in text:
        return DIVISIONS.index("light heavyweight")
    return next((i for i, name in enumerate(DIVISIONS) if name in text), None)


class SkillProfiles:
    def __init__(self, path, women=frozenset(), divisions=None):
        self.women = women
        self.divisions = divisions or {}
        data = json.loads(Path(path).read_text())
        self.fighters = {uid: f for uid, f in data.items() if f["fights"] >= MIN_FIGHTS}
        self.scale = {}
        for side in ("offense", "defense"):
            for key in next(iter(self.fighters.values()))[side]:
                values = [f[side][key][0] for f in self.fighters.values()]
                mean = sum(values) / len(values)
                self.scale[(side, key)] = (mean, math.sqrt(sum((v - mean) ** 2 for v in values) / len(values)) or 1.0)
        self.sorted = [sorted(self._blend(f, parts) for f in self.fighters.values()) for parts, _, _ in SKILLS]
        self.shape = {uid: self._vector(f) for uid, f in self.fighters.items()}
        self.style = {uid: [w * self._blend(f, parts) for w, parts in STYLE] for uid, f in self.fighters.items()}

    def _z(self, f, side, key, shift=0.0):
        mean, spread = self.scale[(side, key)]
        return (f[side][key][0] + shift * f[side][key][1] - mean) / spread

    def _blend(self, f, parts, shift=0.0):
        """Weighted mix of standardized measurements (each in league standard deviations)."""
        return sum(weight * self._z(f, side, key, shift) for side, key, weight in parts)

    def _pct(self, index, value):
        values = self.sorted[index]
        return round(100 * bisect_left(values, value) / len(values))

    def _vector(self, f):
        """Percentile on each skill, so no single noisy skill dominates the comparison."""
        return [self._pct(i, self._blend(f, parts)) for i, (parts, _, _) in enumerate(SKILLS)]

    def _similar(self, uid, f):
        mine_div = division_index(self.divisions.get(uid))
        scored = []
        for other, g in self.fighters.items():
            if other == uid or g["fights"] < SIMILAR_MIN_FIGHTS or (other in self.women) != (uid in self.women):
                continue
            their_div = division_index(self.divisions.get(other))
            apart = abs(mine_div - their_div) if mine_div is not None and their_div is not None else 9
            shape = math.dist(self.shape[uid], self.shape[other]) / 2.83          # 0 = same skill scores, 100 = opposite
            style = math.dist(self.style[uid], self.style[other])                # in league standard deviations
            scored.append((apart > 1, style + shape / 12 + DIVISION_STEP * min(apart, 1), shape, other))
        scored.sort()
        scored = sorted(scored[:3], key=lambda row: row[2])      # show the closest skill match first
        return [{"id": other, "name": self.fighters[other]["name"],
                 "division": (self.divisions.get(other) or "").replace("Women's ", "") or None,
                 "match": max(0, round(100 - shape))}
                for _, _, shape, other in scored[:3]]

    def profile(self, uid):
        f = self.fighters.get(uid)
        if f is None:
            return {"status": "unavailable",
                    "message": f"Skill profiles cover fighters with {MIN_FIGHTS}+ UFC fights who fought in the last two years."}
        skills = []
        for i, (parts, label, about) in enumerate(SKILLS):
            skills.append({"label": label, "about": about, "percentile": self._pct(i, self._blend(f, parts)),
                           "low": self._pct(i, self._blend(f, parts, -1)), "high": self._pct(i, self._blend(f, parts, 1))})
        return {"status": "available", "fights": f["fights"], "compared_with": len(self.fighters), "skills": skills,
                "similar": self._similar(uid, f),
                "label": "Opponent-adjusted skills from recorded UFC fights, ranked among active fighters. "
                         "The band shows how sure the estimate is. A description, not a prediction."}
