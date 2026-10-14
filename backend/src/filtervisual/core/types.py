"""Shared contracts; snapshots copy their arrays and never share mutable state."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass
class PhysicalState:
    t: float
    center_xy: np.ndarray
    height_a: float
    velocity_xyz: np.ndarray
    reference_yaw: float
    angular_velocity: float
    radius_a: float
    radius_b: float
    height_diff: float
    armor_positions: np.ndarray


@dataclass
class PhysicalEstimate:
    center_xy: np.ndarray | None = None
    height_a: float | None = None
    velocity_xyz: np.ndarray | None = None
    reference_yaw: float | None = None
    angular_velocity: float | None = None
    radius_a: float | None = None
    radius_b: float | None = None
    height_diff: float | None = None
    armor_positions: np.ndarray | None = None
    covariance: dict[str, np.ndarray] | None = None
    valid: bool = True
    error: str | None = None


@dataclass(frozen=True)
class ObservationContext:
    time_s: float = 0.
    plate_ids: tuple[int, ...] = ()
    angular_indices: tuple[int, ...] = ()


@dataclass
class ObservationFrame:
    t: float
    context: ObservationContext
    values: np.ndarray
    id: str = ""

    @classmethod
    def scalar(cls, t: float, value: float) -> ObservationFrame:
        return cls(t, ObservationContext(time_s=t), np.array([value]), id=f"scalar-{t}")


@dataclass
class Estimate:
    t: float
    x: np.ndarray
    P: np.ndarray
    mode_probabilities: np.ndarray | None = None


@dataclass(frozen=True)
class FilterSnapshot:
    t: float
    x: np.ndarray
    P: np.ndarray
    mode_probabilities: np.ndarray | None = None
    mode_snapshots: tuple[FilterSnapshot, ...] = ()
    kind: str = "ekf"
    jitter: float = 0.
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        for key in ("x", "P", "mode_probabilities"):
            value = getattr(self, key)
            if value is not None:
                frozen = np.array(value, dtype=float, copy=True)
                frozen.flags.writeable = False
                object.__setattr__(self, key, frozen)


@dataclass
class UpdateDiagnostics:
    t: float
    innovation: np.ndarray
    S: np.ndarray
    dof: int
    posterior: Estimate
    observation_id: str = ""
    mode_diagnostics: tuple[UpdateDiagnostics, ...] = ()
    jitter: float = 0.


@dataclass
class TruthMapping:
    indices: tuple[int, ...]
    values: np.ndarray
    angular_indices: tuple[int, ...] = ()


@dataclass
class SimulationData:
    truth: Any
    observations: list[ObservationFrame]
    scene_hash: str = ""
    observation_hash: str = ""


@dataclass
class ForecastRecord:
    instance_id: str
    origin_time: float
    lead_s: float
    target_time: float
    state: np.ndarray
    P: np.ndarray
    physical_projection: PhysicalEstimate
    mode_probabilities: np.ndarray | None = None
    error: str | None = None


@dataclass
class InstanceRun:
    config: Any
    model: Any
    samples: list[Estimate] = field(default_factory=list)
    updates: list[UpdateDiagnostics] = field(default_factory=list)
    forecasts: list[ForecastRecord] = field(default_factory=list)
    consumed_observation_ids: list[str] = field(default_factory=list)
    skipped_observation_ids: list[str] = field(default_factory=list)
    error: str | None = None
    elapsed_s: float = 0.


@dataclass
class RunProgress:
    phase: str
    completed_instances: int = 0
    total_instances: int = 0
    completed_events: int = 0
    total_events: int = 0


@dataclass
class RunResult:
    config: Any
    data: SimulationData
    instances: list[InstanceRun]
    evaluation_times: np.ndarray


@dataclass
class EvaluatedRun:
    payload: dict[str, Any]


class RunCancelled(Exception):
    """A user cancelled an experiment."""
