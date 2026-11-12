"""Skill profiles for the site: where a fighter sits among active UFC fighters on eight skills,
with an uncertainty band, plus the fighters whose skill profile is most similar.

Source: the multi-skill model (src/upset/ratings/multiskill_research.py). Every skill is
opponent-adjusted and built only from recorded UFC fights. Descriptive, not a prediction.
"""

import json
import math
from bisect import bisect_left
from pathlib import Path

SKILLS = [("offense", "str", "Striking volume", "Strikes landed at range, adjusted for opponents' defense"),
          ("defense", "str", "Striking defense", "How few strikes opponents land at range"),
          ("offense", "kd", "Knockdown power", "Knockdowns scored, adjusted for opponents' chins"),
          ("defense", "ko", "Durability", "How hard this fighter is to stop"),
          ("offense", "td", "Takedowns", "Takedowns landed, adjusted for opponents' takedown defense"),
          ("defense", "td", "Takedown defense", "How few takedowns opponents complete"),
          ("offense", "ctrl", "Control", "Time spent in control on the ground or against the fence"),
          ("offense", "sub", "Submission threat", "Submission attempts, adjusted for opponents")]
MIN_FIGHTS = 3


class SkillProfiles:
    def __init__(self, path, women=frozenset()):
        self.women = women
        data = json.loads(Path(path).read_text())
        self.fighters = {uid: f for uid, f in data.items() if f["fights"] >= MIN_FIGHTS}
        self.sorted = {(side, key): sorted(f[side][key][0] for f in self.fighters.values()) for side, key, _, _ in SKILLS}
        self.spread = {k: (math.sqrt(sum(v * v for v in vals) / len(vals)) or 1.0) for k, vals in self.sorted.items()}

    def _pct(self, side, key, value):
        values = self.sorted[(side, key)]
        return round(100 * bisect_left(values, value) / len(values))

    def _vector(self, f):
        return [f[side][key][0] / self.spread[(side, key)] for side, key, _, _ in SKILLS]

    def profile(self, uid):
        f = self.fighters.get(uid)
        if f is None:
            return {"status": "unavailable",
                    "message": f"Skill profiles cover fighters with {MIN_FIGHTS}+ UFC fights who fought in the last two years."}
        skills = []
        for side, key, label, about in SKILLS:
            mean, sd = f[side][key]
            skills.append({"label": label, "about": about, "percentile": self._pct(side, key, mean),
                           "low": self._pct(side, key, mean - sd), "high": self._pct(side, key, mean + sd)})
        mine = self._vector(f)
        nearest = sorted(((math.dist(mine, self._vector(g)), other) for other, g in self.fighters.items()
                          if other != uid and (other in self.women) == (uid in self.women)))[:3]
        return {"status": "available", "fights": f["fights"], "compared_with": len(self.fighters), "skills": skills,
                "similar": [{"id": other, "name": self.fighters[other]["name"]} for _, other in nearest],
                "label": "Opponent-adjusted skills from recorded UFC fights, ranked among active fighters. "
                         "The band shows how sure the estimate is. A description, not a prediction."}
