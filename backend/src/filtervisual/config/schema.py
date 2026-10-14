"""Versioned, explicit configuration. Runtime changes create new experiments."""
from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Configuration(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class GeometryConfig(Configuration):
    radius_a: float = .25
    radius_b: float = .35
    height_a: float = .20
    height_diff: float = .08
    reference_id: int = 0


class SineTerm(Configuration):
    amplitude: float = 1.
    frequency_rad_s: float = 1.2
    phase_rad: float = 0.
    offset: float = 0.


class Waypoint(Configuration):
    time_s: float
    speed: float
    heading_rad: float


class TranslationConfig(Configuration):
    mode: Literal["constant", "waypoints", "random_smooth"] = "random_smooth"
    initial_xy: list[float] = Field(default_factory=lambda: [0., 0.])
    velocity_xy: list[float] = Field(default_factory=lambda: [.5, 0.])
    speed_min: float = .5
    speed_max: float = 2.
    node_interval_s: float = 1.
    waypoints: list[Waypoint] = Field(default_factory=list)


class RotationConfig(Configuration):
    mode: Literal["angle", "angular_velocity"] = "angular_velocity"
    initial_yaw: float = 0.
    terms: list[SineTerm] = Field(default_factory=lambda: [
        SineTerm(amplitude=1., frequency_rad_s=1.2, offset=2.),
        SineTerm(amplitude=.3, frequency_rad_s=3., phase_rad=.5),
    ])


class SceneConfig(Configuration):
    duration_s: float = 12.
    simulation_dt: float = .002
    geometry: GeometryConfig = Field(default_factory=GeometryConfig)
    translation: TranslationConfig = Field(default_factory=TranslationConfig)
    rotation: RotationConfig = Field(default_factory=RotationConfig)


class ObservationConfig(Configuration):
    frequency_hz: float = 100.
    mode: Literal["fixed", "nearest_visible", "all"] = "nearest_visible"
    plate_id: int = 0
    viewpoint_xyz: list[float] = Field(default_factory=lambda: [-3., 0., .2])
    std_xyz: float = .01
    std_yaw: float = .02
    covariance: list[list[float]] | None = None
    dropout_probability: float = 0.
    outlier_probability: float = 0.
    outlier_scale: float = 10.


class ModelDefinition(Configuration):
    id: str = "rm-cv"
    kind: Literal["builtin", "python"] = "builtin"
    builtin_name: str | None = "rm_cv"
    source: str | None = None
    params: dict = Field(default_factory=dict)


class UKFParameters(Configuration):
    alpha: float = .5
    beta: float = 2.
    kappa: float = 0.


class IMMModeConfig(Configuration):
    model_id: str = "rm-cv"
    kind: Literal["ekf", "ukf"] = "ekf"
    q_scale: float = 1.
    r_scale: float = 1.


class IMMConfig(Configuration):
    models: list[IMMModeConfig] = Field(default_factory=lambda: [
        IMMModeConfig(q_scale=.2), IMMModeConfig(q_scale=4.),
    ])
    probabilities: list[float] = Field(default_factory=lambda: [.5, .5])
    generator: list[list[float]] = Field(default_factory=lambda: [[-1., 1.], [1., -1.]])


def default_x0() -> list[float]:
    return [0., 0., .2, 0., 0., 0., 0., 0., .2, .2, 0.]


def default_p0() -> list[list[float]]:
    std = [.2, .2, .1, 1., 1., .2, .5, 2., .1, .1, .05]
    return [[s*s if i == j else 0. for j in range(11)] for i, s in enumerate(std)]


class FilterConfig(Configuration):
    id: str
    name: str
    kind: Literal["ekf", "ukf", "imm"] = "ekf"
    enabled: bool = True
    model_id: str = "rm-cv"
    frequency_hz: float = 50.
    x0: list[float] = Field(default_factory=default_x0)
    p0: list[list[float]] = Field(default_factory=default_p0)
    q_scale: float = 1.
    r_scale: float = 1.
    ukf: UKFParameters = Field(default_factory=UKFParameters)
    imm: IMMConfig = Field(default_factory=IMMConfig)


class ForecastConfig(Configuration):
    enabled: bool = True
    leads_s: list[float] = Field(default_factory=lambda: [.1, .3, .5])
    max_step_s: float = .005


class EvaluationConfig(Configuration):
    frequency_hz: float = 50.
    confidence: float = .95
    monte_carlo_trials: int = 20


class ExperimentConfig(Configuration):
    schema_version: Literal[1] = 1
    name: str = "四装甲板平移与自旋"
    seed: int = 42
    scene: SceneConfig = Field(default_factory=SceneConfig)
    observation: ObservationConfig = Field(default_factory=ObservationConfig)
    models: list[ModelDefinition] = Field(default_factory=lambda: [ModelDefinition()])
    instances: list[FilterConfig] = Field(default_factory=lambda: [
        FilterConfig(id="ekf-01", name="EKF 01", kind="ekf"),
        FilterConfig(id="ukf-01", name="UKF 01", kind="ukf"),
        FilterConfig(id="imm-01", name="IMM 01", kind="imm"),
    ])
    forecast: ForecastConfig = Field(default_factory=ForecastConfig)
    evaluation: EvaluationConfig = Field(default_factory=EvaluationConfig)


def default_experiment() -> ExperimentConfig:
    return ExperimentConfig()
