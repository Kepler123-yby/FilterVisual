"""Scaled unscented filtering with angular means and regenerated sigma points."""
from __future__ import annotations

import numpy as np

from filtervisual.config.schema import UKFParameters
from filtervisual.core.linalg import cholesky_with_jitter, solve_positive, validate_covariance
from filtervisual.core.types import UpdateDiagnostics
from filtervisual.filters.protocol import GaussianFilter


class UnscentedKalmanFilter(GaussianFilter):
    kind = "ukf"

    def __init__(self, model, x0, P0, t0=0., q_scale=1., r_scale=1., parameters=None):
        super().__init__(model, x0, P0, t0, q_scale, r_scale)
        self.parameters = parameters or UKFParameters()
        n = len(self.x)
        alpha, beta, kappa = self.parameters.alpha, self.parameters.beta, self.parameters.kappa
        if not np.isfinite([alpha, beta, kappa]).all() or alpha <= 0 or beta < 0 or n + kappa <= 0:
            raise ValueError("UKF alpha must be positive, beta nonnegative and n+kappa positive")
        self.lambda_ = alpha * alpha * (n + kappa) - n
        self.scale = n + self.lambda_
        self.mean_weights = np.full(2 * n + 1, 1. / (2. * self.scale))
        self.covariance_weights = self.mean_weights.copy()
        self.mean_weights[0] = self.lambda_ / self.scale
        self.covariance_weights[0] = self.mean_weights[0] + (1. - alpha * alpha + beta)

    def _sigma_points(self):
        factor, _, jitter = cholesky_with_jitter(self.P, name="sigma P")
        offset = np.sqrt(self.scale) * factor.T
        points = np.concatenate([self.x[None, :], self.x + offset, self.x - offset])
        return points, jitter

    def can_predict_exact(self, dt):
        """Angle sigma points must stay in one local chart when coalescing."""
        if not getattr(self.model, "exact_linear_prediction", False):
            return False
        indices = tuple(self.model.angular_indices)
        if not indices:
            return True
        F = np.asarray(self.model.jacobian_f(self.x, dt, self.t))
        predicted = F @ self.P @ F.T + self.q_scale * self.model.Q(dt)
        width_squared = self.scale * np.maximum(np.diag(self.P), np.diag(predicted))
        return bool(np.all(width_squared[list(indices)] < np.pi ** 2 * (1. - 1e-12)))

    def predict(self, dt):
        dt = self._validate_dt(dt)
        points, jitter = self._sigma_points()
        batch_f = getattr(self.model, "f_batch", None)
        propagated = np.asarray(batch_f(points, dt, self.t) if callable(batch_f) else
                                [self.model.f(point.copy(), dt, self.t) for point in points])
        if propagated.shape != points.shape or not np.isfinite(propagated).all():
            raise ValueError("f has invalid sigma-point shape or values")
        mean = self.model.state_mean(propagated, self.mean_weights)
        batch_residual = getattr(self.model, "state_residual_batch", None)
        residuals = np.asarray(batch_residual(propagated, mean) if callable(batch_residual) else
                               [self.model.state_residual(point, mean) for point in propagated])
        Q = validate_covariance(self.model.Q(dt), name="Q", dimension=len(self.x)) * self.q_scale
        P = (residuals.T * self.covariance_weights) @ residuals + Q
        return self._finish(mean, P, t=self.t + dt, jitter=jitter)

    def update(self, frame):
        values = self._validate_frame(frame)
        points, sigma_jitter = self._sigma_points()
        transformed = np.asarray([self.model.h(point, frame.context) for point in points])
        if transformed.shape != (len(points), len(values)) or not np.isfinite(transformed).all():
            raise ValueError("h has invalid sigma-point observation shape or values")
        mean = self.model.observation_mean(transformed, self.mean_weights, frame.context)
        dz = np.asarray([self.model.observation_residual(point, mean, frame.context)
                         for point in transformed])
        dx = np.asarray([self.model.state_residual(point, self.x) for point in points])
        R = validate_covariance(self.model.R(frame), name="R", positive_definite=True,
                                dimension=len(values)) * self.r_scale
        S = (dz.T * self.covariance_weights) @ dz + R
        cross = (dx.T * self.covariance_weights) @ dz
        solution, S, jitter = solve_positive(S, cross.T, name="innovation S")
        K = solution.T
        innovation = self.model.observation_residual(values, mean, frame.context)
        posterior = self._finish(self.x + K @ innovation, self.P - K @ S @ K.T,
                                 jitter=max(sigma_jitter, jitter))
        return UpdateDiagnostics(t=self.t, innovation=np.asarray(innovation), S=S,
                                 dof=len(values), posterior=posterior,
                                 observation_id=frame.id, jitter=self.jitter)
