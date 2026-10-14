import numpy as np
import pytest

from filtervisual.core.types import ObservationFrame
from filtervisual.filters.ekf import ExtendedKalmanFilter
from filtervisual.filters.imm import InteractingMultipleModel, fuse_gaussians, transition_matrix
from helpers import assert_snapshot_equal, make_cv_filter, scalar_model


def test_imm_fusion_and_transition():
    mean, P = fuse_gaussians([np.array([0.]), np.array([2.])],
                            [np.array([[1.]]), np.array([[1.]])],
                            np.array([.25, .75]), scalar_model())
    assert mean[0] == pytest.approx(1.5)
    assert P[0, 0] == pytest.approx(1.75)
    generator = np.array([[-1., 1.], [1., -1.]])
    Pi = transition_matrix(generator, .1)
    assert Pi[0, 0] == pytest.approx(.9093653765)
    np.testing.assert_allclose(Pi @ Pi, transition_matrix(generator, .2), atol=1e-10)


def test_imm_angular_mix_crosses_boundary_locally():
    mean, P = fuse_gaussians(np.deg2rad([[179.], [-179.]]),
                            [np.array([[.01]]), np.array([[.01]])], np.array([.5, .5]),
                            scalar_model(angular=True))
    assert mean[0] == pytest.approx(np.pi)
    assert P[0, 0] == pytest.approx(.01 + np.deg2rad(1.) ** 2)


def test_imm_angular_innovation_and_nis_do_not_depend_on_mode_order():
    diagnostics = []
    for angles in ((-179., 160.), (160., -179.)):
        model = scalar_model(angular=True)
        modes = [ExtendedKalmanFilter(model, np.deg2rad([angle]), np.array([[.01]]))
                 for angle in angles]
        imm = InteractingMultipleModel(modes, np.array([.5, .5]), np.zeros((2, 2)))
        diagnostics.append(imm.update(ObservationFrame.scalar(t=0., value=0.)))
    first, second = diagnostics
    np.testing.assert_allclose(first.innovation, np.deg2rad([-170.5]), atol=1e-12)
    np.testing.assert_allclose(first.innovation, second.innovation, atol=1e-12)
    np.testing.assert_allclose(first.S, second.S, atol=1e-12)
    first_nis = first.innovation @ np.linalg.solve(first.S, first.innovation)
    second_nis = second.innovation @ np.linalg.solve(second.S, second.innovation)
    assert first_nis == pytest.approx(second_nis, abs=1e-12)


def test_zero_prior_mode_and_very_small_likelihood_are_finite():
    model = scalar_model()
    filters = [ExtendedKalmanFilter(model, np.array([value]), np.eye(1)) for value in (0., 1.)]
    imm = InteractingMultipleModel(filters, np.array([1., 0.]), np.array([[-1., 1.], [1., -1.]]))
    imm.predict(.1)
    diagnostic = imm.update(ObservationFrame.scalar(t=.1, value=1e4))
    assert np.isfinite(diagnostic.posterior.x).all()
    assert np.isfinite(imm.probabilities).all()
    assert imm.probabilities.sum() == pytest.approx(1.)


def test_underflowed_mode_recovers_from_equal_cumulative_likelihood_after_restore():
    model = scalar_model()
    modes = [ExtendedKalmanFilter(model, np.array([mean]), np.array([[.01]]))
             for mean in (0., 1000.)]
    imm = InteractingMultipleModel(modes, np.array([.5, .5]), np.zeros((2, 2)))
    imm.update(ObservationFrame.scalar(t=0., value=1000.))
    assert imm.probabilities[0] == 0.
    snapshot = imm.snapshot()
    clone = imm.clone()
    imm.probabilities = np.array([.5, .5])
    imm.restore(snapshot)
    for filter_ in (imm, clone):
        filter_.predict(.01)
        filter_.update(ObservationFrame.scalar(t=.01, value=0.))
        # The joint Gaussian likelihood of [1000, 0] is identical under
        # initial means 0 and 1000, so equal prior probabilities are recovered.
        np.testing.assert_allclose(filter_.probabilities, [.5, .5], atol=1e-10)
    assert_snapshot_equal(imm.snapshot(), clone.snapshot())


def test_imm_clone_restores_all_modes_and_keeps_original_unchanged():
    imm = make_cv_filter("imm")
    before = imm.snapshot()
    clone = imm.clone()
    clone.predict(.2)
    clone.update(ObservationFrame.scalar(t=.2, value=1.4))
    assert_snapshot_equal(imm.snapshot(), before)
    assert clone.snapshot().t == pytest.approx(.2)
    imm.restore(clone.snapshot())
    assert_snapshot_equal(imm.snapshot(), clone.snapshot())
    with pytest.raises(ValueError):
        imm.snapshot().mode_probabilities[0] = .8


def test_imm_rejects_different_state_semantics():
    first = make_cv_filter("ekf")
    second = make_cv_filter("ukf")
    second.model.state_names = ("radius", "velocity")
    with pytest.raises(ValueError, match="semantics"):
        InteractingMultipleModel([first, second], np.array([.5, .5]), np.zeros((2, 2)))


@pytest.mark.parametrize("attribute,value", [
    ("state_names", ("radius",)), ("units", ("s",)), ("angular_indices", (0,)),
])
def test_imm_factory_rejects_modes_with_different_instance_state_metadata(attribute, value):
    from filtervisual.config.schema import FilterConfig, IMMConfig, IMMModeConfig
    from filtervisual.filters.protocol import make_filter
    outer, mode = scalar_model(), scalar_model()
    setattr(outer, attribute, value)
    config = FilterConfig(
        id="imm", name="IMM", kind="imm", model_id="outer", x0=[0.], p0=[[1.]],
        imm=IMMConfig(models=[IMMModeConfig(model_id="mode"), IMMModeConfig(model_id="mode")]),
    )
    with pytest.raises(ValueError, match="instance model"):
        make_filter(config, outer, models={"outer": outer, "mode": mode})


@pytest.mark.parametrize("generator", [np.array([[-1., -1.], [1., -1.]]),
                                       np.array([[-1., 2.], [1., -1.]])])
def test_imm_rejects_invalid_generator(generator):
    with pytest.raises(ValueError):
        transition_matrix(generator, .1)


def test_asymmetric_transition_uses_row_current_column_next():
    imm = make_cv_filter("imm")
    imm.generator = np.array([[-2., 2.], [.2, -.2]])
    imm.probabilities = np.array([1., 0.])
    expected = imm.probabilities @ transition_matrix(imm.generator, .3)
    imm.predict(.3)
    np.testing.assert_allclose(imm.probabilities, expected, atol=1e-12)


def test_cached_transition_does_not_share_mutable_result():
    generator = np.array([[-1., 1.], [1., -1.]])
    first = transition_matrix(generator, .1)
    first[0, 0] = 99.
    assert transition_matrix(generator, .1)[0, 0] == pytest.approx(.9093653765)


@pytest.mark.parametrize("kind", ["ekf", "ukf", "imm"])
def test_prediction_can_use_actual_irregular_elapsed_time(kind):
    filter_ = make_cv_filter(kind)
    result = filter_.predict(.037)
    assert result.t == pytest.approx(.037)
    assert result.x[0] == pytest.approx(1.074)
