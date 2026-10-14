"""Periodic residuals and local means, including negative UKF weights."""
from __future__ import annotations

from collections.abc import Sequence
import numpy as np


def wrap_angle(value):
    """Map radians to [-pi, pi), preserving NumPy broadcasting."""
    return (np.asarray(value) + np.pi) % (2. * np.pi) - np.pi


def angular_residual(a: np.ndarray, b: np.ndarray,
                     angular_indices: Sequence[int] = ()) -> np.ndarray:
    residual = np.asarray(a, dtype=float) - np.asarray(b, dtype=float)
    residual = residual.copy()
    for index in angular_indices:
        residual[..., index] = wrap_angle(residual[..., index])
    return residual


def weighted_mean(points: np.ndarray, weights: np.ndarray,
                  angular_indices: Sequence[int] = ()) -> np.ndarray:
    """Unwrap each angle near the first point before taking a weighted mean.

    A sine/cosine mean can select the antipodal angle when sigma-point weights
    are negative. Local unwrapping matches the tangent-space UKF residual.
    """
    points = np.asarray(points, dtype=float)
    weights = np.asarray(weights, dtype=float)
    if points.ndim != 2 or weights.shape != (len(points),) or not len(points):
        raise ValueError("points and weights dimensions must agree")
    if not np.isfinite(points).all() or not np.isfinite(weights).all():
        raise ValueError("points and weights must be finite")
    if not np.isclose(weights.sum(), 1., atol=1e-10):
        raise ValueError("mean weights must sum to one")
    local = points.copy()
    for index in angular_indices:
        local[:, index] = points[0, index] + wrap_angle(points[:, index] - points[0, index])
    # Keep the angle near its reference instead of wrapping the state history.
    return weights @ local
