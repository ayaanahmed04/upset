import random

import numpy as np

from upset.ratings import round_scoring as S


def row(**values):
    return {"sig_strikes_landed": 0, "head_landed": 0, **values}


def test_posterior_uses_the_label():
    p = [0.5, 0.5, 0.5]
    q, total = S.posterior(p, ("count", 3))
    assert list(q) == [1, 1, 1] and abs(total - 0.125) < 1e-12
    q, _ = S.posterior(p, ("count", 0))
    assert list(q) == [0, 0, 0]
    q, total = S.posterior([0.9, 0.5, 0.1], ("win", 1))        # A won more rounds: two or three of them
    assert q[0] > q[1] > q[2] and abs(total - (0.9 * 0.5 * 0.9 + 0.9 * 0.5 * 0.1 + 0.1 * 0.5 * 0.1 + 0.9 * 0.5 * 0.1)) < 1e-12


def test_probability_is_mirrored_between_corners():
    w = np.array([0.1] * len(S.FEATURES))
    a = row(sig_strikes_landed=20, head_landed=15, knockdowns=1, control_seconds=60)
    b = row(sig_strikes_landed=10, head_landed=6, takedowns_landed=1)
    assert abs(S.probability(a, b, w) + S.probability(b, a, w) - 1) < 1e-12
    assert S.probability(a, a, w) == 0.5


def test_fit_recovers_who_wins_rounds_from_totals_only():
    rng = random.Random(3)
    examples = []
    for _ in range(300):
        X = np.zeros((3, len(S.FEATURES)))
        X[:, 0] = [rng.gauss(0, 8) for _ in range(3)]            # head strikes decide every round
        won = int(sum(x > 0 for x in X[:, 0]))
        examples.append((X, ("count", won)))
    w = S.fit(examples, rounds=10)
    assert w[0] > 0.2 and all(abs(v) < 1e-6 for v in w[1:])
