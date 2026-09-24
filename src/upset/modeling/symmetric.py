"""Mirrored training and complementary matchup probabilities."""

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier

from upset.modeling.elo_comparison import BOOSTED_SETTINGS, _logistic

SYMMETRIC_BOOSTED_SETTINGS = {**BOOSTED_SETTINGS, "min_samples_leaf": 60}


def swap_features(matrix: np.ndarray, signs: np.ndarray) -> np.ndarray:
    """Reverse signed differences while leaving shared matchup context fixed."""
    values = np.asarray(matrix, dtype=float)
    signs = np.asarray(signs, dtype=float)
    if values.ndim != 2 or signs.shape != (values.shape[1],):
        raise ValueError("Feature matrix and swap signs differ.")
    if not np.isin(signs, (-1, 1)).all() or np.isinf(values).any():
        raise ValueError("Invalid swap signs or infinite feature.")
    return values * signs


def fit_symmetric(matrix, targets, signs, *, boosted=False):
    values = np.asarray(matrix, dtype=float)
    reverse = swap_features(values, signs)
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
        model = HistGradientBoostingClassifier(**SYMMETRIC_BOOSTED_SETTINGS)
        model.fit(augmented, labels, sample_weight=weights)
    else:
        model = _logistic()
        model.fit(augmented, labels, classifier__sample_weight=weights)
    return model


def symmetric_probabilities(model, matrix, signs):
    """Return coherent probabilities plus both raw directional estimates.

    This guarantee holds even when fitted tree splits or missing-data handling
    are not symmetric. Call this again on swapped inputs to verify the result.
    """
    reverse = swap_features(matrix, signs)
    forward = model.predict_proba(matrix)[:, 1]
    backward = model.predict_proba(reverse)[:, 1]
    probability = 0.5 + 0.5 * (forward - backward)
    if (
        not np.isfinite(probability).all()
        or not ((probability >= 0) & (probability <= 1)).all()
    ):
        raise ValueError("Invalid symmetric probability.")
    return probability, forward, backward
