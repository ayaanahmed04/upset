import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

import pytest

from upset.predictions import published_picks as P

DATABASE = Path("data/processed/research_2026_11_10_reviewed_v3/upset.sqlite")
NOW = datetime(2026, 11, 11, 19, 0, tzinfo=timezone.utc)


def fake_api(event):
    def fetch(url):
        return {"latest_bout": "2026-11-07"} if url.endswith("/api/meta") else event
    return fetch


def card(status="scheduled", starts="2026-11-14T22:00:00+00:00"):
    forecast = {"status": "available", "probabilities": [0.57, 0.43], "rating_gap": 5, "provisional": True,
                "stale": False, "label": "UPSET forecast", "record": {"since_2019": {"bouts": 1}}}
    return {"slug": "ufc-999", "name": "UFC 999", "date": "2026-11-14", "starts_at": starts, "status": status,
            "bouts": [{"fighters": [{"id": "a", "name": "Ciryl Gane"}, {"id": "b", "name": "Josh Hokit"}],
                       "division": "Heavyweight", "title": True, "rounds": 5, "forecast": forecast},
                      {"fighters": [{"id": "c", "name": "New Guy"}, {"id": "d", "name": "Other Guy"}],
                       "forecast": {"status": "unavailable"}}]}


def test_names_match_across_spellings():
    assert P.same_person("Uros Medic", "Uroš Medić")
    assert P.same_person("Heili Alateng", "Alatengheili")
    assert not P.same_person("Jim Miller", "Dan Miller")


def test_no_vig_removes_margin():
    fair = P.no_vig(1.5, 2.75)
    assert abs(sum(fair) - 1) < 1e-12 and fair[0] > fair[1]
    assert P.no_vig(1.02, 1.69) is None  # broken quote, overround far above a real book


def test_freeze_writes_fingerprinted_file_once(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "fetch_json", fake_api(card()))
    folder, payload, manifest = P.freeze("http://x", "ufc-999", tmp_path, now=NOW)
    assert manifest["picks_sha256"] == P.digest((folder / "picks.json").read_bytes())
    assert [p["pick_name"] for p in payload["picks"]] == ["Ciryl Gane"]
    assert payload["not_picked"][0]["reason"].startswith("Not enough")
    with pytest.raises(SystemExit):
        P.freeze("http://x", "ufc-999", tmp_path, now=NOW)


def test_freeze_refuses_started_or_finished_cards(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "fetch_json", fake_api(card(starts="2026-11-11T18:00:00+00:00")))
    with pytest.raises(SystemExit):
        P.freeze("http://x", "ufc-999", tmp_path, now=NOW)
    monkeypatch.setattr(P, "fetch_json", fake_api(card(status="archived")))
    with pytest.raises(SystemExit):
        P.freeze("http://x", "ufc-998", tmp_path, now=NOW)


def test_tampered_picks_fail_the_fingerprint(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "fetch_json", fake_api(card()))
    folder, _, _ = P.freeze("http://x", "ufc-999", tmp_path, now=NOW)
    text = (folder / "picks.json").read_text().replace("0.57", "0.75")
    (folder / "picks.json").write_text(text)
    with pytest.raises(ValueError):
        P.load_frozen(folder)
    assert "error" in P.load_record(tmp_path)["events"][0]


@pytest.mark.skipif(not DATABASE.exists(), reason="reviewed database not present")
def test_grade_against_a_finished_card(tmp_path):
    from upset.data.viewer_events import reviewed_bout
    with closing(sqlite3.connect(DATABASE)) as db:
        db.row_factory = sqlite3.Row
        rows = db.execute("SELECT id,payload FROM fights WHERE event_date='2026-11-07' ORDER BY id").fetchall()
    bouts = [b for b in (reviewed_bout(json.loads(r["payload"]), r["id"]) for r in rows) if b["outcome"] == "decisive"][:2]
    assert len(bouts) == 2
    picks = []
    for order, bout in enumerate(bouts):
        fighters = [{"id": f["id"], "name": f["name"]} for f in bout["fighters"]]
        p = [0.6, 0.4] if order == 0 else [0.3, 0.7]
        picks.append({"order": order, "fighters": fighters, "probabilities": p,
                      "pick": fighters[0 if p[0] > p[1] else 1]["id"], "pick_name": "",
                      "market": {"probabilities": [0.5, 0.5]}})
    picks.append({"order": 9, "fighters": [{"id": "x", "name": "X"}, {"id": "y", "name": "Y"}],
                  "probabilities": [0.5, 0.5], "pick": "x", "pick_name": "X"})
    body = P.dump({"version": P.VERSION, "frozen_at": "2026-11-06T00:00:00Z",
                   "event": {"slug": "test", "date": "2026-11-07"}, "model": {}, "rules": P.RULES,
                   "picks": picks, "not_picked": [], "market_source": None})
    folder = tmp_path / "test"
    folder.mkdir()
    (folder / "picks.json").write_bytes(body)
    (folder / "manifest.json").write_bytes(P.dump({"version": P.VERSION, "picks_sha256": P.digest(body)}))
    graded = P.grade(folder, DATABASE)
    results = {r["order"]: r for r in graded["results"]}
    for order, bout in enumerate(bouts):
        assert results[order]["status"] == "graded"
        assert results[order]["correct"] == (picks[order]["pick"] == bout["winner_id"])
    assert results[9]["status"] == "not_held"
    record = P.load_record(tmp_path)
    assert record["summary"]["graded"] == 2 and record["summary"]["void"] == 1
    assert (folder / "picks.json").read_bytes() == body
    with pytest.raises(SystemExit):
        P.grade(folder, DATABASE)
