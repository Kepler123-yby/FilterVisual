"""The model contract and reusable angular operations for local models."""
from __future__ import annotations

from typing import Protocol, runtime_checkable
import numpy as np

from filtervisual.core.angles import angular_residual, weighted_mean


@runtime_checkable
class Model(Protocol):
    state_names: tuple[str, ...]
    units: tuple[str, ...]
    angular_indices: tuple[int, ...]

    def f(self, x: np.ndarray, dt: float, t0: float) -> np.ndarray: ...
    def h(self, x: np.ndarray, context) -> np.ndarray: ...
    def Q(self, dt: float) -> np.ndarray: ...
    def R(self, frame) -> np.ndarray: ...
    def state_residual(self, a, b) -> np.ndarray: ...
    def observation_residual(self, a, b, context) -> np.ndarray: ...
    def state_mean(self, points, weights) -> np.ndarray: ...
    def observation_mean(self, points, weights, context) -> np.ndarray: ...
    def project(self, x, P): ...
    def truth_mapping(self, physical): ...


class AngularModel:
    """Optional mixin; user models can implement these methods directly."""
    angular_indices: tuple[int, ...] = ()

    def state_residual(self, a, b):
        return angular_residual(a, b, self.angular_indices)

    def observation_residual(self, a, b, context):
        return angular_residual(a, b, context.angular_indices)

    def state_mean(self, points, weights):
        return weighted_mean(points, weights, self.angular_indices)

    def observation_mean(self, points, weights, context):
        return weighted_mean(points, weights, context.angular_indices)


def validate_projection(projection):
    """Normalize physical outputs; malformed user projections stay local."""
    from filtervisual.core.types import PhysicalEstimate
    if not isinstance(projection,PhysicalEstimate):
        raise ValueError("project must return PhysicalEstimate")
    for name,shape in (("center_xy",(2,)),("velocity_xyz",(3,)),("armor_positions",(4,3)),
                       ("reference_yaw",()),("angular_velocity",()),("height_a",()),
                       ("radius_a",()),("radius_b",()),("height_diff",())):
        value=getattr(projection,name)
        if value is None:
            continue
        numeric=np.asarray(value,dtype=float)
        if numeric.shape!=shape:
            raise ValueError(f"project.{name} must have shape {shape}")
        if projection.valid and not np.isfinite(numeric).all():
            raise ValueError(f"project.{name} must be finite when valid=True")
        setattr(projection,name,float(numeric) if shape==() else numeric.copy())
    return projection


def numerical_jacobian(function, x: np.ndarray, residual=None) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    columns = []
    for index, value in enumerate(x):
        step = 1e-6 * max(1., abs(value))
        plus, minus = x.copy(), x.copy()
        plus[index] += step
        minus[index] -= step
        a, b = np.asarray(function(plus)), np.asarray(function(minus))
        difference = residual(a, b) if residual else a - b
        columns.append(difference / (2. * step))
    return np.column_stack(columns)
