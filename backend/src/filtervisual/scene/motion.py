"""Deterministic continuous truth, independent of observations and rendering."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
from scipy.integrate import solve_ivp

from filtervisual.config.schema import SceneConfig
from filtervisual.core.types import PhysicalState
from filtervisual.scene.geometry import armor_positions


def random_stream(seed: int, stream: int) -> np.random.Generator:
    """Rebuild a dedicated random stream without consuming another stream."""
    return np.random.default_rng(np.random.SeedSequence(seed, spawn_key=(stream,)))


def _short_angle(angle: float) -> float:
    return float((angle + np.pi) % (2 * np.pi) - np.pi)


@dataclass(frozen=True)
class VelocityProfile:
    """Scalar speed and heading nodes joined by half-cosine transitions."""

    times: np.ndarray
    speeds: np.ndarray
    headings: np.ndarray

    def __call__(self, t: float) -> np.ndarray:
        if len(self.times) == 1 or t <= self.times[0]:
            speed, heading = self.speeds[0], self.headings[0]
        elif t >= self.times[-1]:
            speed, heading = self.speeds[-1], self.headings[-1]
        else:
            i = int(np.searchsorted(self.times, t, side="right") - 1)
            u = (t - self.times[i]) / (self.times[i + 1] - self.times[i])
            weight = (1 - np.cos(np.pi * u)) / 2
            speed = (1 - weight) * self.speeds[i] + weight * self.speeds[i + 1]
            heading = self.headings[i] + weight * _short_angle(
                self.headings[i + 1] - self.headings[i]
            )
        return float(speed) * np.array([np.cos(heading), np.sin(heading)])


def rotation_at(rotation, t: float) -> tuple[float, float]:
    """Evaluate the unwrapped reference angle and angular velocity analytically.

    In angle mode ``initial_yaw`` is an additive angular offset. In velocity
    mode it is exactly theta(0). Sinc gives the constant-frequency limit without
    division by zero, and avoids catastrophic cancellation for tiny frequency.
    """
    theta = float(rotation.initial_yaw)
    omega = 0.0
    if rotation.mode == "angle":
        for term in rotation.terms:
            w, phase = term.frequency_rad_s, term.phase_rad
            theta += term.amplitude * np.sin(w * t + phase) + term.offset
            omega += term.amplitude * w * np.cos(w * t + phase)
    else:
        for term in rotation.terms:
            w, phase = term.frequency_rad_s, term.phase_rad
            omega += term.amplitude * np.sin(w * t + phase) + term.offset
            theta += term.amplitude * t * np.sinc(w * t / (2 * np.pi)) * np.sin(
                phase + w * t / 2
            ) + term.offset * t
    return float(theta), float(omega)


@dataclass(frozen=True)
class TruthTrajectory:
    scene: SceneConfig
    position: Callable[[float], np.ndarray]
    velocity: Callable[[float], np.ndarray]

    @property
    def duration_s(self) -> float:
        return float(self.scene.duration_s)

    @property
    def times(self) -> np.ndarray:
        count = int(np.floor(self.duration_s / self.scene.simulation_dt))
        times = np.arange(count + 1) * self.scene.simulation_dt
        if times[-1] < self.duration_s - 1e-12:
            times = np.r_[times, self.duration_s]
        return times

    def sample(self, t: float) -> PhysicalState:
        if not np.isfinite(t) or t < -1e-12 or t > self.duration_s + 1e-12:
            raise ValueError(f"truth time {t!r} is outside [0, {self.duration_s}]")
        time = float(np.clip(t, 0, self.duration_s))
        center = np.asarray(self.position(time), dtype=float).reshape(2)
        velocity = np.r_[self.velocity(time), 0.0]
        theta, omega = rotation_at(self.scene.rotation, time)
        geometry = self.scene.geometry
        return PhysicalState(
            t=time, center_xy=center, height_a=geometry.height_a,
            velocity_xyz=velocity, reference_yaw=theta, angular_velocity=omega,
            radius_a=geometry.radius_a, radius_b=geometry.radius_b,
            height_diff=geometry.height_diff,
            armor_positions=armor_positions(center, geometry, theta),
        )


def _velocity_profile(scene: SceneConfig, seed: int) -> Callable[[float], np.ndarray]:
    translation = scene.translation
    if translation.mode == "constant":
        value = np.asarray(translation.velocity_xy, dtype=float)
        return lambda _: value.copy()
    if translation.mode == "waypoints":
        points = translation.waypoints
        if not points:
            raise ValueError("waypoint translation requires at least one waypoint")
        times = np.asarray([point.time_s for point in points], dtype=float)
        speeds = np.asarray([point.speed for point in points], dtype=float)
        headings = np.asarray([point.heading_rad for point in points], dtype=float)
        if np.any(np.diff(times) <= 0) or np.any(speeds < 0):
            raise ValueError("waypoints require increasing times and nonnegative speed")
        return VelocityProfile(times, speeds, headings)
    if translation.mode != "random_smooth":
        raise ValueError(f"unknown translation mode: {translation.mode}")
    rng = random_stream(seed, 0)
    interval = float(translation.node_interval_s)
    times = np.arange(int(np.ceil(scene.duration_s / interval)) + 1) * interval
    speeds = rng.uniform(translation.speed_min, translation.speed_max, len(times))
    headings = rng.uniform(-np.pi, np.pi, len(times))
    return VelocityProfile(times, speeds, headings)


def build_truth(scene: SceneConfig, seed: int) -> TruthTrajectory:
    """Solve a continuous scene once; sample it at arbitrary exact event times."""
    scene = scene.model_copy(deep=True)
    velocity = _velocity_profile(scene, seed)
    initial = np.asarray(scene.translation.initial_xy, dtype=float)
    solution = solve_ivp(
        lambda t, _: velocity(t), (0.0, scene.duration_s), initial,
        dense_output=True, max_step=scene.simulation_dt, rtol=1e-8, atol=1e-10,
    )
    if not solution.success or solution.sol is None:
        raise RuntimeError(f"truth integration failed: {solution.message}")
    return TruthTrajectory(scene=scene, position=solution.sol, velocity=velocity)
