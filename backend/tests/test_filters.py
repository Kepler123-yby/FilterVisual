import math

import numpy as np
import pytest

from filtervisual.core.angles import angular_residual, weighted_mean
from filtervisual.core.linalg import CovarianceError, cholesky_with_jitter, validate_covariance
from filtervisual.core.types import ObservationFrame
from filtervisual.models.rm_cv import RoboMasterCVModel
from filtervisual.config.schema import GeometryConfig
from helpers import make_linear_filter, make_cv_filter, scalar_model


@pytest.mark.parametrize("kind", ["ekf", "ukf", "imm"])
def test_linear_update_matches_analytic_solution(kind):
    f = make_linear_filter(kind)
    f.predict(0.)
    d = f.update(ObservationFrame.scalar(t=0., value=3.))
    np.testing.assert_allclose(d.posterior.x, [2.4, 0], atol=1e-8)
    np.testing.assert_allclose(d.posterior.P, np.diag([.8, 1]), atol=1e-8)
    np.testing.assert_allclose(d.innovation, [3.], atol=1e-12)
    np.testing.assert_allclose(d.S, [[5.]], atol=1e-8)


@pytest.mark.parametrize("kind", ["ekf", "ukf"])
def test_angle_innovation_uses_shortest_difference(kind):
    from filtervisual.filters.ekf import ExtendedKalmanFilter
    from filtervisual.filters.ukf import UnscentedKalmanFilter
    model = scalar_model(angular=True)
    factory = ExtendedKalmanFilter if kind == "ekf" else UnscentedKalmanFilter
    f = factory(model, np.array([math.radians(179)]), np.array([[.01]]))
    d = f.update(ObservationFrame.scalar(t=0., value=math.radians(-179)))
    assert d.innovation[0] == pytest.approx(math.radians(2), abs=1e-12)


def test_angle_mean_uses_local_unwrapping_with_negative_weights():
    points = np.deg2rad([[179.], [-179.], [177.]])
    actual = weighted_mean(points, np.array([-3., 2., 2.]), (0,))
    assert actual[0] == pytest.approx(math.radians(179), abs=1e-12)
    assert angular_residual(np.deg2rad([-179.]), np.deg2rad([179.]), (0,))[0] == pytest.approx(math.radians(2))


def test_robo_master_noise_scales_with_actual_dt():
    model = RoboMasterCVModel(GeometryConfig(), q_translation=2., q_rotation=3., q_geometry=.04)
    q = model.Q(.1)
    np.testing.assert_allclose(q[np.ix_([0, 3], [0, 3])], 2 * np.array([[.1**3/3, .1**2/2], [.1**2/2, .1]]))
    assert q[6, 7] == pytest.approx(3 * .1**2/2)
    assert q[8, 8] == pytest.approx(.004)
    np.testing.assert_array_equal(model.Q(0.), np.zeros((11, 11)))


@pytest.mark.parametrize("kind", ["ekf", "ukf", "imm"])
def test_time_context_clone_and_readonly_snapshot(kind):
    f = make_cv_filter(kind)
    snapshot = f.snapshot()
    with pytest.raises(ValueError):
        snapshot.x[0] = 9.
    clone = f.clone()
    clone.predict(.3)
    assert clone.snapshot().x[0] == pytest.approx(1.6)
    assert f.snapshot().x[0] == pytest.approx(1.)
    assert f.snapshot().t == pytest.approx(0.)
    f.restore(clone.snapshot())
    assert f.predict(.1).x[0] == pytest.approx(1.8)
    with pytest.raises(ValueError, match="time"):
        f.update(ObservationFrame.scalar(t=.1, value=2.))


def test_invalid_covariance_is_not_silently_fixed():
    with pytest.raises(CovarianceError):
        validate_covariance(np.diag([1., -.01]), name="P0", positive_definite=True)
    with pytest.raises(CovarianceError):
        cholesky_with_jitter(np.diag([1., -.01]))
    factor, repaired, jitter = cholesky_with_jitter(np.diag([1., -1e-13]))
    assert 0 < jitter <= 1e-8
    np.testing.assert_allclose(factor @ factor.T, repaired, atol=1e-14)


def test_builtin_observation_jacobian_matches_angular_finite_difference():
    from filtervisual.core.types import ObservationContext
    from filtervisual.models.protocol import numerical_jacobian
    model = RoboMasterCVModel(GeometryConfig(reference_id=1))
    x = np.array([1., 2., .2, 0., 0., 0., 3.13, 2., .25, .35, .08])
    context = ObservationContext(time_s=.2, plate_ids=(0, 1, 2, 3), angular_indices=(3, 7, 11, 15))
    numeric = numerical_jacobian(lambda state: model.h(state, context), x,
                                  lambda a, b: model.observation_residual(a, b, context))
    np.testing.assert_allclose(model.jacobian_h(x, context), numeric, atol=1e-8)


@pytest.mark.parametrize("kind", ["ekf", "ukf"])
@pytest.mark.parametrize("ids", [(1,), (0, 1, 2, 3)])
def test_builtin_filter_symmetric_positive_covariance_smoke(kind, ids):
    from filtervisual.core.types import ObservationContext
    from filtervisual.filters.ekf import ExtendedKalmanFilter
    from filtervisual.filters.ukf import UnscentedKalmanFilter
    model = RoboMasterCVModel(GeometryConfig())
    x = np.array([0., 0., .2, .2, .1, 0., 3.13, 2., .25, .35, .08])
    filter_ = (ExtendedKalmanFilter if kind == "ekf" else UnscentedKalmanFilter)(
        model, x, np.eye(11) * .001)
    for index in range(1, 6):
        dt = .02
        x = model.f(x, dt, (index-1)*dt)
        filter_.predict(dt)
        context = ObservationContext(time_s=index*dt, plate_ids=ids,
                                     angular_indices=tuple(4*i+3 for i in range(len(ids))))
        frame = ObservationFrame(t=index*dt, context=context, values=model.h(x, context))
        posterior = filter_.update(frame).posterior
        np.testing.assert_allclose(posterior.P, posterior.P.T, atol=1e-12)
        assert np.linalg.eigvalsh(posterior.P).min() > 0.
    assert model.project(posterior.x, posterior.P).valid


def test_full_measurement_covariance_preserves_fixed_plate_identity():
    from filtervisual.core.types import ObservationContext
    covariance = np.diag(np.arange(1., 17.))
    covariance[0, 8] = covariance[8, 0] = .5
    model = RoboMasterCVModel(GeometryConfig(), observation_covariance=covariance)
    frame = ObservationFrame(t=0., context=ObservationContext(plate_ids=(2, 0)), values=np.zeros(8))
    indices = [8, 9, 10, 11, 0, 1, 2, 3]
    np.testing.assert_array_equal(model.R(frame), covariance[np.ix_(indices, indices)])


@pytest.mark.parametrize("kind", ["ekf", "ukf"])
def test_explicit_time_model_and_finite_difference_fallback(kind):
    from helpers import LinearModel
    from filtervisual.filters.ekf import ExtendedKalmanFilter
    from filtervisual.filters.ukf import UnscentedKalmanFilter
    class TimeModel(LinearModel):
        jacobian_f = None
        jacobian_h = None
        def f(self, x, dt, t0):
            return x + (t0 * dt + .5 * dt ** 2)
    factory = ExtendedKalmanFilter if kind == "ekf" else UnscentedKalmanFilter
    filter_ = factory(TimeModel(n=1), np.array([0.]), np.eye(1), t0=2.)
    estimate = filter_.predict(.1)
    assert estimate.x[0] == pytest.approx(.205, abs=1e-10)
    diagnostic = filter_.update(ObservationFrame.scalar(t=2.1, value=.205))
    assert diagnostic.innovation[0] == pytest.approx(0., abs=1e-9)


def test_nonpositive_estimated_radius_is_explicit_invalid_projection():
    model = RoboMasterCVModel(GeometryConfig())
    x = np.array([0., 0., .2, 0., 0., 0., 0., 0., -.1, .35, .08])
    projection = model.project(x, np.eye(11))
    assert not projection.valid
    assert projection.radius_a == -.1
    assert "radii" in projection.error


@pytest.mark.parametrize("kind", ["ekf", "ukf"])
def test_builtin_linear_prediction_semigroup_matches_substeps(kind):
    from filtervisual.filters.ekf import ExtendedKalmanFilter
    from filtervisual.filters.ukf import UnscentedKalmanFilter
    model = RoboMasterCVModel(GeometryConfig())
    x = np.array([0., 0., .2, .5, .3, 0., .7, 2., .25, .35, .08])
    engine = ExtendedKalmanFilter if kind == "ekf" else UnscentedKalmanFilter
    single = engine(model, x, np.eye(11) * .01)
    stepped = single.clone()
    single.predict(.5)
    for i in range(100):
        stepped.predict(.005)
    np.testing.assert_allclose(single.x, stepped.x, atol=1e-11)
    np.testing.assert_allclose(single.P, stepped.P, atol=1e-11)


def test_ukf_large_angle_sigma_spread_prevents_prediction_coalescing():
    from filtervisual.config.schema import FilterConfig
    from filtervisual.models.registry import make_filter
    model = RoboMasterCVModel(GeometryConfig())
    filter_ = make_filter(FilterConfig(id="ukf", name="UKF", kind="ukf"), model)
    assert filter_.can_predict_exact(.1)
    assert not filter_.can_predict_exact(3.)


@pytest.mark.parametrize("alpha,kappa", [(1e-9, 0.), (1e200, 0.), (1e-200, 0.)])
def test_ukf_rejects_numerically_degenerate_sigma_weights(alpha, kappa):
    from filtervisual.config.schema import UKFParameters
    from filtervisual.filters.ukf import UnscentedKalmanFilter
    with pytest.raises(ValueError, match="UKF.*(scale|weights)"):
        UnscentedKalmanFilter(scalar_model(), [0.], [[1.]],
            parameters=UKFParameters(alpha=alpha, kappa=kappa))


def test_ukf_sigma_scale_does_not_subtract_nearly_equal_numbers():
    from filtervisual.config.schema import UKFParameters
    from filtervisual.filters.ukf import UnscentedKalmanFilter
    parameters = UKFParameters(alpha=.001, kappa=.2)
    filter_ = UnscentedKalmanFilter(scalar_model(), [0.], [[1.]], parameters=parameters)
    assert filter_.scale == parameters.alpha ** 2 * (1 + parameters.kappa)
    np.testing.assert_allclose(filter_.predict(.1).P, [[1.]], atol=1e-12)


def test_ukf_small_alpha_does_not_move_a_stationary_center_far_from_origin():
    from filtervisual.config.schema import UKFParameters
    from filtervisual.filters.ukf import UnscentedKalmanFilter
    x = np.array([1000., -1000., .2, 0., 0., 0., .3, 0., .25, .35, .08])
    filter_ = UnscentedKalmanFilter(RoboMasterCVModel(GeometryConfig()), x,
        np.eye(11) * .01, parameters=UKFParameters(alpha=.0001))
    result = filter_.predict(0.)
    np.testing.assert_allclose(result.x[:2], x[:2], rtol=0., atol=1e-10)
    np.testing.assert_allclose(result.P[:2, :2], np.eye(2) * .01, atol=1e-10)
