"""Division labels follow accepted, dated bouts rather than majority votes."""

import json
import sqlite3

import pytest

from test_research_app import A, C, add_same_date_historical_bout, build, fixture
from upset.research_app import connect, distributions, fighter_report, latest_classified_division, route, search


def set_divisions(database):
    with sqlite3.connect(database) as db:
        for bid, payload in db.execute("SELECT id,payload FROM fights").fetchall():
            value = json.loads(payload)
            value["weight_class"] = "Heavyweight" if bid == "cito:new" else "UFC Light Heavyweight Title Bout"
            db.execute("UPDATE fights SET payload=? WHERE id=?", (json.dumps(value), bid))


def test_latest_division_overrides_majority_and_respects_exclusive_cutoff(tmp_path):
    paths = add_same_date_historical_bout(fixture(tmp_path))
    output = tmp_path / "research"
    build(paths, output)
    database = output / "upset.sqlite"
    set_divisions(database)
    with connect(database) as db:
        old = fighter_report(db, A, "2026-09-20", 0)
        assert old["summary"]["division"] == "Light Heavyweight"
        for window in (0, 3, 5, 10):
            new = fighter_report(db, A, "2026-09-21", window)
            assert new["summary"]["division"] == "Heavyweight"
            assert new["summary"]["division_date"] == "2026-09-20"
            assert new["summary"]["division_basis"] == "latest_classified_bout"
        assert new["profile"]["weight_lbs"] == old["profile"]["weight_lbs"]
        assert fighter_report(db, C, "2026-09-21", 0)["summary"]["division"] is None
    # Peer assignments use the identical rule; old light-heavyweight bouts stay
    # in the Career metric totals, as the displayed window definition promises.
    pools = distributions(database, "2026-09-21", 0)
    assert "Heavyweight" in pools and "Light Heavyweight" not in pools
    assert pools["Heavyweight"]["fighters"] == 2


def test_search_and_reports_share_cutoff_division_and_counts(tmp_path):
    output = tmp_path / "research"
    build(fixture(tmp_path), output)
    database = output / "upset.sqlite"
    set_divisions(database)
    with connect(database) as db:
        for cutoff, division, bouts in (("2026-03-07", None, 0),
                                        ("2026-09-20", "Light Heavyweight", 1),
                                        ("2026-09-21", "Heavyweight", 2)):
            hit = next(r for r in search(db, "Alex", cutoff) if r["id"] == A)
            report = fighter_report(db, A, cutoff, 0)
            assert hit["division"] == report["summary"]["division"] == division
            assert hit["recorded_bouts"] == bouts
            assert hit["last_bout"] == report["summary"]["last_bout"]
        assert next(r for r in search(db, "Alex") if r["id"] == A)["division"] == "Heavyweight"
    result = route(database, "/api/fighters?q=Alex&before=2026-09-20")
    assert next(r for r in result if r["id"] == A)["division"] == "Light Heavyweight"
    with pytest.raises(ValueError):
        route(database, "/api/fighters?q=Alex&before=not-a-date")


def test_unclassified_bout_does_not_erase_last_known_division():
    history = [{"date": "2026-10-03", "division": None},
               {"date": "2026-09-20", "division": "Heavyweight"},
               {"date": "2025-01-01", "division": "Light Heavyweight"}]
    assert latest_classified_division(history) == ("Heavyweight", "2026-09-20", "latest_classified_bout")
    assert latest_classified_division(history[:1]) == (None, None, "no_classified_bout")


def test_conflicting_same_day_divisions_do_not_invent_an_order():
    history = [{"date": "2026-10-03", "division": "Heavyweight"},
               {"date": "2026-10-03", "division": "Light Heavyweight"},
               {"date": "2025-01-01", "division": "Light Heavyweight"}]
    assert latest_classified_division(history) == (None, "2026-10-03", "ambiguous_same_day_divisions")
