from upset.data.normalization import (
    normalize_cito_round,
    parse_control_time,
    parse_landed_attempted,
)


def test_parse_landed_attempted():
    assert parse_landed_attempted("7 of 27") == (7, 27)
    assert parse_landed_attempted("0 of 0") == (0, 0)
    assert parse_landed_attempted("12 of 36") == (12, 36)


def test_parse_control_time():
    assert parse_control_time("1:13") == 73
    assert parse_control_time("0:00") == 0
    assert parse_control_time("2:05") == 125

def test_normalize_cito_round():



    
    raw_round = {
        "id": "round-123",
        "boutId": "bout-456",
        "fighterSlug": "curtis-blaydes",
        "fighterName": "Curtis Blaydes",
        "round": 1,
        "knockdowns": 0,
        "significantStrikes": "7 of 27",
        "totalStrikes": "7 of 27",
        "takedowns": "1 of 3",
        "submissionAttempts": 0,
        "reversals": 0,
        "controlTime": "1:13",
        "head": "1 of 20",
        "body": "2 of 2",
        "leg": "4 of 5",
        "distance": "6 of 26",
        "clinch": "0 of 0",
        "ground": "1 of 1",
        "lastSyncedAt": "2026-09-12T22:57:42.270Z",
    }

    normalized = normalize_cito_round(raw_round)

    assert normalized["source"] == "cito"
    assert normalized["fighter_name"] == "Curtis Blaydes"
    assert normalized["round_number"] == 1

    assert normalized["sig_strikes_landed"] == 7
    assert normalized["sig_strikes_attempted"] == 27

    assert normalized["takedowns_landed"] == 1
    assert normalized["takedowns_attempted"] == 3

    assert normalized["control_seconds"] == 73

    assert normalized["head_landed"] == 1
    assert normalized["body_landed"] == 2
    assert normalized["leg_landed"] == 4

    