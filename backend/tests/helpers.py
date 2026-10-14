"""Small independent linear models for numerical acceptance tests."""
from __future__ import annotations

import numpy as np

from filtervisual.core.types import TruthMapping
from filtervisual.filters.ekf import ExtendedKalmanFilter
from filtervisual.filters.ukf import UnscentedKalmanFilter
from filtervisual.models.protocol import AngularModel


class LinearModel(AngularModel):
    def __init__(self, n=2, cv=False, q=0., angular=False):
        self.state_names = ("angle",) if angular else ("position", "velocity")[:n]
        self.units = ("rad",) if angular else ("m", "m/s")[:n]
        self.angular_indices = (0,) if angular else ()
        self.n, self.cv, self.q = n, cv, q

    def f(self, x, dt, t0=0.):
        return self.jacobian_f(x, dt, t0) @ x

    def jacobian_f(self, x, dt, t0=0.):
        matrix = np.eye(self.n)
        if self.cv:
            matrix[0, 1] = dt
        return matrix

    def h(self, x, context):
        return np.asarray(x[:1]).copy()

    def jacobian_h(self, x, context):
        matrix = np.zeros((1, self.n))
        matrix[0, 0] = 1.
        return matrix

    def Q(self, dt):
        if self.cv:
            return self.q * np.array([[dt ** 3 / 3., dt ** 2 / 2.], [dt ** 2 / 2., dt]])
        return np.eye(self.n) * self.q * dt

    def R(self, frame):
        return np.eye(1)

    def observation_residual(self, a, b, context):
        from filtervisual.core.angles import angular_residual
        return angular_residual(a, b, (0,) if self.angular_indices else ())

    def observation_mean(self, points, weights, context):
        from filtervisual.core.angles import weighted_mean
        return weighted_mean(points, weights, (0,) if self.angular_indices else ())

    def project(self, x, P):
        return None

    def truth_mapping(self, physical):
        return TruthMapping(indices=(0,), values=np.asarray(physical.center_xy[:1]), angular_indices=())


def scalar_model(angular=False):
    return LinearModel(n=1, angular=angular)


def _factory(kind):
    if kind == "ekf":
        return ExtendedKalmanFilter
    if kind == "ukf":
        return UnscentedKalmanFilter
    if kind == "imm":
        from filtervisual.filters.imm import InteractingMultipleModel
        return lambda model, x0, P0: InteractingMultipleModel(
            [ExtendedKalmanFilter(model, x0, P0), UnscentedKalmanFilter(model, x0, P0)],
            np.array([.5, .5]), np.array([[-1., 1.], [1., -1.]]))
    raise ValueError(kind)


def make_linear_filter(kind):
    return _factory(kind)(LinearModel(), np.zeros(2), np.diag([4., 1.]))


def make_cv_filter(kind, position=1., velocity=2., q=0.):
    return _factory(kind)(LinearModel(cv=True, q=q), np.array([position, velocity]), np.eye(2))


def assert_snapshot_equal(actual, expected):
    assert actual.t == expected.t
    np.testing.assert_array_equal(actual.x, expected.x)
    np.testing.assert_array_equal(actual.P, expected.P)
    if actual.mode_probabilities is not None or expected.mode_probabilities is not None:
        np.testing.assert_array_equal(actual.mode_probabilities, expected.mode_probabilities)
    assert len(actual.mode_snapshots) == len(expected.mode_snapshots)
    for a, b in zip(actual.mode_snapshots, expected.mode_snapshots):
        assert_snapshot_equal(a, b)
