"""Shared filter lifecycle: exact times, independent clones and full snapshots."""
from __future__ import annotations

import copy
from typing import Protocol, runtime_checkable
import numpy as np

from filtervisual.core.linalg import cholesky_with_jitter, validate_covariance
from filtervisual.core.types import Estimate, FilterSnapshot


@runtime_checkable
class Filter(Protocol):
    model: object

    def predict(self, dt: float) -> Estimate: ...
    def update(self, frame): ...
    def snapshot(self) -> FilterSnapshot: ...
    def restore(self, snapshot: FilterSnapshot) -> None: ...
    def clone(self) -> "Filter": ...


class GaussianFilter:
    kind = "gaussian"
    def __init__(self, model, x0, P0, t0=0., q_scale=1., r_scale=1.):
        self.model = model
        self.x = np.asarray(x0, dtype=float).copy()
        n = len(model.state_names)
        if self.x.shape != (n,) or not np.isfinite(self.x).all():
            raise ValueError(f"x0 must contain {n} finite state values")
        self.P = validate_covariance(P0, name="P0", positive_definite=True, dimension=n)
        self.t = float(t0)
        if not np.isfinite([self.t, q_scale, r_scale]).all() or q_scale < 0 or r_scale <= 0:
            raise ValueError("time and noise scales must be finite; q_scale>=0 and r_scale>0")
        self.q_scale, self.r_scale = float(q_scale), float(r_scale)
        self.jitter = 0.

    def _validate_dt(self, dt):
        dt = float(dt)
        if not np.isfinite(dt) or dt < 0:
            raise ValueError("prediction dt must be finite and nonnegative")
        return dt

    def _validate_frame(self, frame):
        if not np.isclose(self.t, frame.t, rtol=0., atol=1e-10):
            raise ValueError(f"observation time {frame.t} differs from filter time {self.t}")
        if not np.isclose(frame.context.time_s, frame.t, rtol=0., atol=1e-10):
            raise ValueError("observation frame time and context time differ")
        values = np.asarray(frame.values, dtype=float)
        if values.ndim != 1 or not len(values) or not np.isfinite(values).all():
            raise ValueError("observation values must be a nonempty finite vector")
        return values

    def _finish(self, x, P, *, t=None, jitter=0.):
        x = np.asarray(x, dtype=float)
        if x.shape != self.x.shape or not np.isfinite(x).all():
            raise ValueError("model produced an invalid state vector")
        _, repaired, repair_jitter = cholesky_with_jitter((P + P.T) * .5, name="posterior P")
        self.x, self.P = x.copy(), repaired
        self.jitter = max(float(jitter), repair_jitter)
        if t is not None:
            self.t = float(t)
        return Estimate(t=self.t, x=self.x.copy(), P=self.P.copy())

    def snapshot(self):
        return FilterSnapshot(t=self.t, x=self.x.copy(), P=self.P.copy(),
                              kind=self.kind, jitter=self.jitter)

    def restore(self, snapshot):
        if np.asarray(snapshot.x).shape != self.x.shape:
            raise ValueError("snapshot state dimension differs from filter")
        self.x = np.asarray(snapshot.x, dtype=float).copy()
        self.P = validate_covariance(snapshot.P, name="snapshot P", positive_definite=True,
                                     dimension=len(self.x))
        self.t = float(snapshot.t)
        self.jitter = float(getattr(snapshot, "jitter", 0.))

    def clone(self):
        clone = copy.deepcopy(self)
        clone.restore(self.snapshot())
        return clone


def make_filter(config, model, models=None):
    """Build standard engines; IMM modes reference registered model definitions."""
    from filtervisual.filters.ekf import ExtendedKalmanFilter
    from filtervisual.filters.ukf import UnscentedKalmanFilter
    arguments = dict(model=model, x0=np.asarray(config.x0), P0=np.asarray(config.p0),
                     q_scale=config.q_scale, r_scale=config.r_scale)
    if config.kind == "ekf":
        return ExtendedKalmanFilter(**arguments)
    if config.kind == "ukf":
        return UnscentedKalmanFilter(**arguments, parameters=config.ukf)
    if config.kind == "imm":
        from filtervisual.filters.imm import InteractingMultipleModel
        # Same state semantics; q multipliers represent calm / maneuver modes.
        settings = config.imm
        filters = []
        signature = (tuple(model.state_names), tuple(model.units), tuple(model.angular_indices))
        for mode in settings.models:
            if models is None and mode.model_id != config.model_id:
                raise ValueError(f"IMM mode model {mode.model_id} requires the model registry")
            mode_model = models[mode.model_id] if models is not None else model
            mode_signature = (tuple(mode_model.state_names), tuple(mode_model.units),
                              tuple(mode_model.angular_indices))
            if mode_signature != signature:
                raise ValueError(f"IMM mode model {mode.model_id} differs from the instance model's state dimensions and semantics")
            owned_model=copy.deepcopy(mode_model)
            if getattr(owned_model,"_filtervisual_custom",False):
                from filtervisual.models.custom import check_contract
                check_contract(owned_model,owned_model._filtervisual_geometry,config.x0,config.p0)
            mode_arguments = dict(arguments, model=owned_model,
                                  q_scale=config.q_scale * mode.q_scale,
                                  r_scale=config.r_scale * mode.r_scale)
            filters.append(UnscentedKalmanFilter(**mode_arguments, parameters=config.ukf)
                           if mode.kind == "ukf" else ExtendedKalmanFilter(**mode_arguments))
        return InteractingMultipleModel(filters, np.asarray(settings.probabilities),
                                        np.asarray(settings.generator))
    raise ValueError(f"unsupported filter kind: {config.kind}")
