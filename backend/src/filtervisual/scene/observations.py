"""One reproducible observation source with explicit fixed armor identities."""

from __future__ import annotations

import numpy as np

from filtervisual.config.schema import ObservationConfig
from filtervisual.core.types import ObservationContext, ObservationFrame
from filtervisual.scene.geometry import armor_yaws
from filtervisual.scene.motion import TruthTrajectory, random_stream


def _wrap(angles: np.ndarray) -> np.ndarray:
    return (angles + np.pi) % (2 * np.pi) - np.pi


def select_plate_ids(
    positions: np.ndarray, yaws: np.ndarray, config: ObservationConfig,
) -> tuple[int, ...]:
    """Select visible front-facing armor, retaining physical IDs when it switches."""
    if config.mode == "all":
        return (0, 1, 2, 3)
    if config.mode in ("fixed", "specified"):
        return (config.plate_id,)
    if config.mode != "nearest_visible":
        raise ValueError(f"unknown observation mode: {config.mode}")
    view = np.asarray(config.viewpoint_xyz, dtype=float)
    directions = view[None, :] - positions
    normals = np.column_stack((np.cos(yaws), np.sin(yaws), np.zeros(4)))
    # At numerical tangency, zero is treated as invisible, as in the model.
    visible = np.flatnonzero(np.sum(normals * directions, axis=1) > 1e-12)
    if not len(visible):
        return ()
    distances = np.linalg.norm(directions[visible], axis=1)
    closest = np.flatnonzero(np.isclose(distances, distances.min(), rtol=0, atol=1e-12))[0]
    return (int(visible[closest]),)


def observation_covariance(config: ObservationConfig, plate_ids: tuple[int, ...]) -> np.ndarray:
    """Use a per-plate 4x4 covariance or a correlated whole-target 16x16 one."""
    if config.covariance is None:
        sigma = np.r_[np.full(3, config.std_xyz, dtype=float), config.std_yaw]
        base = np.diag(sigma**2)
    else:
        base = np.asarray(config.covariance, dtype=float)
    if base.shape == (4, 4):
        return np.kron(np.eye(len(plate_ids)), base)
    if base.shape == (16, 16):
        indices = np.asarray([4 * plate + i for plate in plate_ids for i in range(4)])
        return base[np.ix_(indices, indices)]
    raise ValueError("observation covariance must be 4x4 or 16x16")


def _noise_factor(covariance: np.ndarray) -> np.ndarray:
    if not np.all(np.isfinite(covariance)) or not np.allclose(
        covariance, covariance.T, rtol=1e-10, atol=1e-12,
    ):
        raise ValueError("true observation covariance must be finite and symmetric")
    eigenvalues, vectors = np.linalg.eigh(covariance)
    tolerance = 1e-12 * max(1.0, float(np.max(np.abs(eigenvalues))))
    if np.min(eigenvalues) < -tolerance:
        raise ValueError("true observation covariance must be positive semidefinite")
    return vectors * np.sqrt(np.maximum(eigenvalues, 0.0))


def generate_observations(
    truth: TruthTrajectory, config: ObservationConfig, seed: int,
) -> list[ObservationFrame]:
    """Sample one shared noisy stream, unaffected by forecast requests.

    Dropout, outlier selection and Gaussian noise have separate fixed streams;
    changing a dropout probability does not redraw surviving observations.
    A missed or non-visible frame is absent, rather than a made-up zero vector.
    """
    noise_rng = random_stream(seed, 1)
    dropout_rng = random_stream(seed, 2)
    outlier_rng = random_stream(seed, 3)
    frames = []
    factors: dict[tuple[int, ...], np.ndarray] = {}
    count = int(np.floor(truth.duration_s * config.frequency_hz + 1e-10)) + 1
    for index in range(count):
        t = index / config.frequency_hz
        state = truth.sample(t)
        yaws = armor_yaws(truth.scene.geometry, state.reference_yaw)
        plate_ids = select_plate_ids(state.armor_positions, yaws, config)
        dropped = dropout_rng.random() < config.dropout_probability
        outlier = outlier_rng.random() < config.outlier_probability
        # Draw all 16 standard normals at each time even for missing frames.
        # Fixed indexing preserves plate-specific draws as visibility switches.
        noise_standard = noise_rng.standard_normal(16)
        if not plate_ids:
            continue
        if plate_ids not in factors:
            factors[plate_ids] = _noise_factor(observation_covariance(config, plate_ids))
        indices = np.asarray([4 * plate + j for plate in plate_ids for j in range(4)])
        noise = factors[plate_ids] @ noise_standard[indices]
        if outlier:
            noise *= config.outlier_scale
        if dropped:
            continue
        values = np.concatenate([
            np.r_[state.armor_positions[plate], yaws[plate]] for plate in plate_ids
        ]) + noise
        angular_indices = tuple(range(3, len(values), 4))
        values[list(angular_indices)] = _wrap(values[list(angular_indices)])
        context = ObservationContext(time_s=t, plate_ids=plate_ids, angular_indices=angular_indices)
        frames.append(ObservationFrame(t=t, context=context, values=values, id=str(index)))
    return frames
