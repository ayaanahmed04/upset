import json
from pathlib import Path

import pytest

from upset.data import build_market_odds as M

ODDS = Path("data/processed/market_odds_2026_11_10_v3")


def test_no_vig_and_american_lines():
    assert abs(M.fair(1.53, 2.65) - 0.634) < 0.001
    assert M.fair(1.01, 30) is None and M.fair(1.02, 1.69) is None
    assert M.american(11.0) == "+1000" and M.american(1.04) == "-2500"


def test_names_and_corners():
    assert M.orientation({"fighter_1": "Holly Holm", "fighter_2": "Ronda Rousey"}, ["Ronda Rousey", "Holly Holm"]) == -1
    assert M.orientation({"fighter_1": "Heili Alateng", "fighter_2": "Juan Diaz"}, ["Alatengheili", "Juan Diaz"]) == 1
    row = {"fighter_1": "Zachary Reese", "fighter_2": "Cody Brundage"}
    assert M.orientation(row, ["Zach Reese", "Cody Brundage"]) == 0
    assert M.loose_orientation(row, ["Zach Reese", "Cody Brundage"]) == 1


@pytest.mark.skipif(not ODDS.exists(), reason="market odds build not present")
def test_known_upsets_are_priced_as_underdog_wins():
    odds = json.loads((ODDS / "odds.json").read_text())
    def chance(winner, date):
        hit = [e for e in odds.values() if e["date"] == date and winner in e["names"]]
        assert len(hit) == 1, (winner, date)
        e = hit[0]
        return e["probability_a"] if e["names"][0] == winner else 1 - e["probability_a"]
    assert chance("Sean Sharaf", "2026-09-19") < .12
    assert chance("Holly Holm", "2015-11-14") < .2
    assert chance("Julianna Pena", "2021-12-11") < .15
    assert chance("Shana Dobson", "2020-08-22") < .15
    assert all(0 < e["probability_a"] < 1 for e in odds.values())
    report = json.loads((ODDS / "report.json").read_text())
    # The mix is reported, never assumed: it must be scored on fights after the fit window.
    assert report["mix"]["fit_on"].endswith("2018-12-31") and report["mix"]["test"]["all"]["market"]["bouts"] > 3000
