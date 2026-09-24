"""Model behavior under swapped participants, missing values and tied inputs."""

import numpy as np
import pytest
from threadpoolctl import threadpool_limits

from upset.modeling.symmetric import (
    SYMMETRIC_BOOSTED_SETTINGS,
    fit_symmetric,
    swap_features,
    symmetric_probabilities,
)


@pytest.mark.parametrize("boosted", [False, True])
def test_complementary_predictions_with_missingness_shared_context_and_ties(boosted):
    rng = np.random.default_rng(7)
    matrix = rng.normal(size=(120, 4))
    matrix[:, 2] = np.abs(matrix[:, 2])  # shared exposure, unchanged on a swap
    matrix[:, 3] = np.nan  # an entirely missing training column remains supported
    matrix[::4, 1] = np.nan
    labels = (matrix[:, 0] > 0).astype(int)
    signs = np.array([-1, -1, 1, -1])
    with threadpool_limits(limits=1):
        model = fit_symmetric(matrix, labels, signs, boosted=boosted)
        p, raw_p, raw_q = symmetric_probabilities(model, matrix, signs)
        q, _, _ = symmetric_probabilities(model, swap_features(matrix, signs), signs)
        assert np.allclose(p + q, 1, atol=1e-12, rtol=0)
        assert np.all((p >= 0) & (p <= 1))
        assert np.allclose(p, 0.5 + 0.5 * (raw_p - raw_q))
        assert np.mean(p[labels == 1]) > np.mean(p[labels == 0])
        tie = np.array([[0, 0, 2, np.nan]])
        assert symmetric_probabilities(model, tie, signs)[0][0] == 0.5
        if boosted:
            assert model.observed_columns.tolist() == [True, True, True, False]
            # A value that first appears in validation cannot make a column
            # selected from the training period re-enter the fitted tree.
            probe = np.array([[1.0, np.nan, 3.0, np.nan]])
            with_future_value = np.array([[1.0, np.nan, 3.0, 12345.0]])
            assert np.array_equal(
                symmetric_probabilities(model, probe, signs)[0],
                symmetric_probabilities(model, with_future_value, signs)[0],
            )
    reversed_twice = swap_features(swap_features(matrix, signs), signs)
    assert np.array_equal(reversed_twice, matrix, equal_nan=True)
    assert SYMMETRIC_BOOSTED_SETTINGS["early_stopping"] is False


def test_mirrored_samples_keep_total_bout_weight_and_complement_targets(monkeypatch):
    observed = {}

    class Recorder:
        def fit(self, x, y, **kwargs):
            observed.update(x=x, y=y, weights=kwargs["classifier__sample_weight"])

    monkeypatch.setattr("upset.modeling.symmetric._logistic", Recorder)
    x = np.array([[3, 8], [-4, 9]])
    fit_symmetric(x, [1, 0], [-1, 1])
    assert observed["x"].tolist() == [[3, 8], [-3, 8], [-4, 9], [4, 9]]
    assert observed["y"].tolist() == [1, 0, 0, 1]
    assert observed["weights"].sum() == 2
    assert observed["weights"].tolist() == [0.5] * 4


def test_invalid_swap_and_targets_are_rejected():
    with pytest.raises(ValueError, match="swap signs"):
        swap_features(np.zeros((2, 2)), [1])
    with pytest.raises(ValueError, match="Invalid swap"):
        swap_features(np.zeros((2, 2)), [1, 0])
    with pytest.raises(ValueError, match="binary"):
        fit_symmetric(np.zeros((2, 2)), [0, None], [-1, 1])
    with pytest.raises(ValueError, match="observed training feature"):
        fit_symmetric(np.full((2, 2), np.nan), [0, 1], [-1, 1], boosted=True)
