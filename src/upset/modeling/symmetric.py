"""Mirrored training and complementary matchup probabilities."""

from dataclasses import dataclass

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier

from upset.modeling.elo_comparison import BOOSTED_SETTINGS, _logistic

SYMMETRIC_BOOSTED_SETTINGS = {**BOOSTED_SETTINGS, "min_samples_leaf": 60}


@dataclass(frozen=True)
class _ObservedBoosted:
    """Use the training fold's observed columns for every later prediction."""

    estimator: HistGradientBoostingClassifier
    observed_columns: np.ndarray

    def predict_proba(self, matrix):
        values = np.asarray(matrix, dtype=float)
        if values.ndim != 2 or values.shape[1] != len(self.observed_columns):
            raise ValueError("Boosted prediction columns differ from training.")
        return self.estimator.predict_proba(values[:, self.observed_columns])


def swap_features(matrix, signs, *, swap_indices=None) -> np.ndarray:
    """Reverse differences, retain shared context, and exchange paired values.

    A permutation lets A's individual value become B's, including missingness.
    Requiring an involution means that swapping twice restores the input.
    Omitting it preserves the original difference-only transformation exactly.
    """
    values = np.asarray(matrix, dtype=float)
    signs = np.asarray(signs, dtype=float)
    if values.ndim != 2 or signs.shape != (values.shape[1],):
        raise ValueError("Feature matrix and swap signs differ.")
    if not np.isin(signs, (-1, 1)).all() or np.isinf(values).any():
        raise ValueError("Invalid swap signs or infinite feature.")
    if swap_indices is None:
        return values * signs
    indices = np.asarray(swap_indices)
    expected = np.arange(values.shape[1])
    if (
        indices.shape != expected.shape
        or not np.issubdtype(indices.dtype, np.integer)
        or not np.array_equal(np.sort(indices), expected)
        or not np.array_equal(indices[indices], expected)
        or not np.all(signs * signs[indices] == 1)
    ):
        raise ValueError("Swap indices and signs must define an involution.")
    return values[:, indices] * signs


def fit_symmetric(matrix, targets, signs, *, boosted=False, swap_indices=None):
    values = np.asarray(matrix, dtype=float)
    reverse = swap_features(values, signs, swap_indices=swap_indices)
    targets = np.asarray(targets)
    if (
        targets.shape != (len(values),)
        or not len(targets)
        or not np.isin(targets, (0, 1)).all()
    ):
        raise ValueError("Mirrored training requires binary targets.")
    # Keep both orientations inside the already selected chronological fold.
    augmented = np.stack((values, reverse), axis=1).reshape(-1, values.shape[1])
    labels = np.column_stack((targets, 1 - targets)).ravel()
    weights = np.full(len(labels), 0.5)
    if boosted:
        # scikit-learn 1.9.1's histogram binning fails on an all-NaN column.
        # Fix the column selection using training data only. Partially missing
        # columns still reach the estimator with NaNs and use native routing.
        observed = np.isfinite(augmented).any(axis=0)
        if not observed.any():
            raise ValueError("Boosting needs an observed training feature.")
        estimator = HistGradientBoostingClassifier(**SYMMETRIC_BOOSTED_SETTINGS)
        estimator.fit(augmented[:, observed], labels, sample_weight=weights)
        model = _ObservedBoosted(estimator, observed)
    else:
        model = _logistic()
        model.fit(augmented, labels, classifier__sample_weight=weights)
    return model


def symmetric_probabilities(model, matrix, signs, *, swap_indices=None):
    """Return coherent probabilities plus both raw directional estimates.

    This guarantee holds even when fitted tree splits or missing-data handling
    are not symmetric. Call this again on swapped inputs to verify the result.
    """
    reverse = swap_features(matrix, signs, swap_indices=swap_indices)
    forward = model.predict_proba(matrix)[:, 1]
    backward = model.predict_proba(reverse)[:, 1]
    probability = 0.5 + 0.5 * (forward - backward)
    if (
        not np.isfinite(probability).all()
        or not ((probability >= 0) & (probability <= 1)).all()
    ):
        raise ValueError("Invalid symmetric probability.")
    return probability, forward, backward
