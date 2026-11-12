import json
import random
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from upset.ratings.forecast_adjust import ForecastAdjustment

S = "2026_11_10_reviewed_v3"
DATABASE = Path(f"data/processed/research_{S}/upset.sqlite")
SNAPSHOT = Path(f"data/processed/overall_rating_v5_1_{S}")
FOLDER = Path("data/processed/forecast_adjustment_2026_11_12_v1")
pytestmark = pytest.mark.skipif(not FOLDER.exists(), reason="forecast adjustment build not present")


@pytest.fixture(scope="module")
def adjustment():
    return ForecastAdjustment(FOLDER, DATABASE, SNAPSHOT)


def test_live_adjustment_reproduces_the_walk_forward_build(adjustment):
    """The on-the-fly calculation used for upcoming fights must give the stored value for past fights."""
    rows = [json.loads(line) for line in open(SNAPSHOT / "forecasts.jsonl")]
    with closing(sqlite3.connect(DATABASE)) as db:
        classes = {fid: json.loads(p).get("weight_class") for fid, p in db.execute("SELECT id,payload FROM fights")}
    recent = [r for r in rows if r["event_date"] >= "2019-01-01" and min(r["prior_decisive_bouts"]) >= 1]
    for item in random.Random(3).sample(recent, 200):
        a, b = item["fighter_ids"]
        p, _ = adjustment.explain(item["forecast"], a, b, item["event_date"], classes[item["fight_id"]] or "")
        assert abs(p - adjustment.adjusted[item["fight_id"]]) < 1e-5, item["fight_id"]


def test_adjustment_is_antisymmetric(adjustment):
    rows = [json.loads(line) for line in open(SNAPSHOT / "forecasts.jsonl")][-300:]
    for item in rows:
        a, b = item["fighter_ids"]
        p_ab, _ = adjustment.explain(item["forecast"], a, b, item["event_date"])
        p_ba, _ = adjustment.explain(1 - item["forecast"], b, a, item["event_date"])
        assert abs(p_ab + p_ba - 1) < 1e-9


def test_metrics_improve_on_the_published_record_set():
    m = json.loads((FOLDER / "manifest.json").read_text())["metrics"]
    for window in ("test", "recent"):
        assert m[window]["adjusted"]["bouts"] == m[window]["v5_1"]["bouts"]
        assert m[window]["adjusted"]["log_loss"] < m[window]["v5_1"]["log_loss"]
    assert m["test"]["v5_1"]["bouts"] == 3177


def test_mismatched_inputs_are_refused(tmp_path):
    copy = tmp_path / "adj"
    shutil.copytree(FOLDER, copy)
    manifest = json.loads((copy / "manifest.json").read_text())
    manifest["inputs"]["rating_manifest_sha256"] = "0" * 64
    (copy / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        ForecastAdjustment(copy, DATABASE, SNAPSHOT)
