from upset.data.viewer_events import ROUND_FIELDS, paired_rounds


def test_rounds_are_aligned_to_fighter_identity_and_totals():
    fight = {"source_fighter_1_id": "provider-a", "source_fighter_2_id": "provider-b",
             "upset_fighter_1_id": "a", "upset_fighter_2_id": "b", "result_round": 1}
    first = dict.fromkeys(ROUND_FIELDS, 0) | {"sig_strikes_landed": 7, "sig_strikes_attempted": 10}
    second = dict.fromkeys(ROUND_FIELDS, 0) | {"sig_strikes_landed": 9, "sig_strikes_attempted": 11}
    a = {**first, "round_number": 1, "source_fighter_id": "provider-a", "upset_fighter_id": "a"}
    b = {**second, "round_number": 1, "source_fighter_id": "provider-b", "upset_fighter_id": "b"}
    assert paired_rounds(fight, [b, a], [first, second]) == [{"round": 1, "stats": [first, second]}]
    assert paired_rounds(fight, [a], [first, second]) == []
    assert paired_rounds(fight, [a, {**b, "upset_fighter_id": "a"}], [first, second]) == []
    assert paired_rounds(fight, [a, b], [{**first, "sig_strikes_landed": 6}, second]) == []
