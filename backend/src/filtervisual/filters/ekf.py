"""Angle-aware extended Kalman filter with Joseph covariance updates."""
from __future__ import annotations

import numpy as np

from filtervisual.core.linalg import solve_positive, validate_covariance
from filtervisual.core.types import UpdateDiagnostics
from filtervisual.filters.protocol import GaussianFilter
from filtervisual.models.protocol import numerical_jacobian


class ExtendedKalmanFilter(GaussianFilter):
    kind = "ekf"

    def can_predict_exact(self, dt):
        """Permit forecast coalescing only for an explicitly exact model."""
        return bool(getattr(self.model, "exact_linear_prediction", False))

    def predict(self, dt):
        dt = self._validate_dt(dt)
        jacobian = getattr(self.model, "jacobian_f", None)
        F = (jacobian(self.x, dt, self.t) if callable(jacobian) else
             numerical_jacobian(lambda x: self.model.f(x, dt, self.t), self.x,
                                self.model.state_residual))
        Q = validate_covariance(self.model.Q(dt), name="Q", dimension=len(self.x)) * self.q_scale
        F = np.asarray(F, dtype=float)
        if F.shape != self.P.shape or not np.isfinite(F).all():
            raise ValueError("jacobian_f has invalid shape or values")
        return self._finish(self.model.f(self.x.copy(), dt, self.t), F @ self.P @ F.T + Q,
                            t=self.t + dt)

    def update(self, frame):
        values = self._validate_frame(frame)
        jacobian = getattr(self.model, "jacobian_h", None)
        H = (jacobian(self.x, frame.context) if callable(jacobian) else
             numerical_jacobian(lambda x: self.model.h(x, frame.context), self.x,
                                lambda a, b: self.model.observation_residual(a, b, frame.context)))
        H = np.asarray(H, dtype=float)
        if H.shape != (len(values), len(self.x)) or not np.isfinite(H).all():
            raise ValueError("jacobian_h has invalid shape or values")
        expected = np.asarray(self.model.h(self.x, frame.context), dtype=float)
        if expected.shape != values.shape or not np.isfinite(expected).all():
            raise ValueError("h has invalid observation shape or values")
        innovation = self.model.observation_residual(values, expected, frame.context)
        R = validate_covariance(self.model.R(frame), name="R", positive_definite=True,
                                dimension=len(values)) * self.r_scale
        prior = self.P
        S = H @ prior @ H.T + R
        solution, S, jitter = solve_positive(S, H @ prior, name="innovation S")
        K = solution.T
        identity = np.eye(len(self.x)) - K @ H
        covariance = identity @ prior @ identity.T + K @ R @ K.T
        posterior = self._finish(self.x + K @ innovation, covariance, jitter=jitter)
        return UpdateDiagnostics(t=self.t, innovation=np.asarray(innovation), S=S,
                                 dof=len(values), posterior=posterior,
                                 observation_id=frame.id, jitter=self.jitter)
