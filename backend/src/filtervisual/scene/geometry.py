"""Fixed plate identities and the four-armor target's world projection."""

from __future__ import annotations

import numpy as np

from filtervisual.config.schema import GeometryConfig


def armor_yaws(geometry: GeometryConfig, reference_yaw: float) -> np.ndarray:
    """Return continuous outward yaw angles, ordered by fixed plate ID."""
    if not np.isfinite(reference_yaw):
        raise ValueError("reference_yaw must be finite")
    if geometry.reference_id not in range(4):
        raise ValueError("reference_id must be in 0..3")
    return float(reference_yaw) + (np.arange(4) - geometry.reference_id) * np.pi / 2


def armor_positions(
    center_xy: np.ndarray, geometry: GeometryConfig, reference_yaw: float,
) -> np.ndarray:
    """Project plate centers in meters; even and odd IDs retain their group."""
    center = np.asarray(center_xy, dtype=float)
    if center.shape != (2,) or not np.all(np.isfinite(center)):
        raise ValueError("center_xy must contain two finite coordinates")
    dimensions = np.asarray([
        geometry.radius_a, geometry.radius_b,
        geometry.height_a, geometry.height_diff,
    ], dtype=float)
    if not np.all(np.isfinite(dimensions)) or np.any(dimensions[:2] <= 0):
        raise ValueError("geometry must have finite dimensions and positive radii")
    yaws = armor_yaws(geometry, reference_yaw)
    parity = np.arange(4) % 2
    radii = np.where(parity == 0, geometry.radius_a, geometry.radius_b)
    return np.column_stack((
        center[0] + radii * np.cos(yaws),
        center[1] + radii * np.sin(yaws),
        geometry.height_a + parity * geometry.height_diff,
    ))
