from copy import deepcopy
from math import log

import pytest

from upset.ratings.settle_forecasts import ORIENTATION, settle

A = "00000000-0000-4000-8000-000000000001"
B = "00000000-0000-4000-8000-000000000002"
C = "00000000-0000-4000-8000-000000000003"
SOURCE = "https://api.citoapi.com/api/v1/ufc/events/ufc-334/bouts"


@pytest.fixture
def ledger():
    return {"event": "UFC 334", "event_date": "2026-11-14",
            "scheduled_start_utc": "2026-11-14T22:00:00+00:00",
            "frozen_at_utc": "2026-11-11T00:00:00+00:00", "data_through": "2026-11-07",
            "probability_orientation": ORIENTATION, "source_urls": ["https://www.ufc.com/event/ufc-334"],
            "matchups": [{"fighters": ["First", "Second"], "fighter_ids": [A, B],
                          "status": "matched", "probabilities_a": {"v4": .75}, "market_probability_a": .6}]}


def bout(pair=(B, A), winner=A, url=SOURCE):
    return {"event_date": "2026-11-14", "source_url": url, "fighter_ids": list(pair),
            "winner_id": winner, "fight_id": "cito:match", "outcome": "decisive" if winner else "nc",
            "result_method": "KO/TKO" if winner else "No Contest"}


def test_reversed_result_corners_use_forecast_orientation(ledger):
    original = deepcopy(ledger)
    result = settle(ledger, [bout()])
    assert ledger == original
    assert result["statuses"] == {"scored": 1}
    assert result["matchups"][0]["winner_is_first"] is True
    assert result["models"]["v4"]["log_loss"] == pytest.approx(-log(.75))
    assert result["models"]["v4"]["brier"] == pytest.approx(.0625)
    assert result["market_matched"]["market"]["log_loss"] == pytest.approx(-log(.6))


@pytest.mark.parametrize("bouts,status", [
    ([bout(url=SOURCE.replace("334", "335"))], "awaiting_reviewed_results"),
    ([bout((A, C))], "no_reviewed_match"),
    ([bout(winner=None)], "nondecisive"),
])
def test_unsettled_or_nondecisive_results_have_no_score(ledger, bouts, status):
    report = settle(ledger, bouts)
    assert report["statuses"] == {status: 1}
    assert report["models"] == {}
    assert report["market_matched"]["market"]["bouts"] == 0


def test_rejects_conflicting_replayed_event_rows(ledger):
    with pytest.raises(ValueError, match="Ambiguous"):
        settle(ledger, [bout(), bout()])
