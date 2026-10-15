"""Keep the documented custom-model examples executable and mathematically consistent."""

from pathlib import Path

import numpy as np
import pytest

from filtervisual.config.schema import ExperimentConfig, GeometryConfig
from filtervisual.config.validation import validate_experiment
from filtervisual.core.types import ObservationContext, ObservationFrame
from filtervisual.evaluation.report import evaluate_run
from filtervisual.models.custom import check_contract, load_model
from filtervisual.models.protocol import numerical_jacobian
from filtervisual.scene.motion import build_truth
from filtervisual.simulation.runner import run_experiment


ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("filename,n", [("reduced_xy.py", 4), ("custom_xy_bias.py", 6)])
@pytest.mark.parametrize("dt", [0., .02, .17])
def test_documented_jacobians_match_numerical_derivatives(filename, n, dt):
    geometry = GeometryConfig(reference_id=2)
    model = load_model((ROOT / "examples/models" / filename).read_text(), {}, geometry)
    x = np.array([.3, -.2, .7, -.4, .02, -.03][:n])
    before = x.copy()
    F_numeric = numerical_jacobian(lambda value: model.f(value, dt, .4), x,
                                   model.state_residual)
    np.testing.assert_allclose(model.jacobian_f(x, dt, .4), F_numeric, atol=1e-7)
    for ids in ((2,), (3, 1), (0, 1, 2, 3)):
        context = ObservationContext(.4, ids, tuple(4*i+3 for i in range(len(ids))))
        H_numeric = numerical_jacobian(
            lambda value: model.h(value, context), x,
            lambda a, b: model.observation_residual(a, b, context))
        np.testing.assert_allclose(model.jacobian_h(x, context), H_numeric, atol=1e-7)
        per_plate = [model.h(x, ObservationContext(.4, (plate,), (3,))) for plate in ids]
        np.testing.assert_allclose(model.h(x, context), np.concatenate(per_plate))
    np.testing.assert_array_equal(x, before)


def test_bias_example_covariances_observation_and_projection():
    geometry = GeometryConfig()
    model = load_model((ROOT / "examples/models/custom_xy_bias.py").read_text(),
                       {"xy_correlation": .6}, geometry)
    x = np.array([.3, -.2, .7, -.4, .02, -.03])
    check_contract(model, geometry, x, np.eye(6))
    dt = .1
    expected = .2 * np.array([[dt**3/3, dt**2/2], [dt**2/2, dt]])
    Q = model.Q(dt)
    np.testing.assert_allclose(Q[np.ix_([0, 2], [0, 2])], expected)
    np.testing.assert_allclose(Q[np.ix_([1, 3], [1, 3])], expected)
    np.testing.assert_allclose(np.diag(Q)[4:], [1e-7, 1e-7])
    np.testing.assert_array_equal(model.Q(0), np.zeros((6, 6)))
    assert np.linalg.eigvalsh(Q).min() >= 0
    context = ObservationContext(0., (3, 1), (3, 7))
    R = model.R(ObservationFrame(0., context, model.h(x, context)))
    assert R.shape == (8, 8)
    assert np.linalg.eigvalsh(R).min() > 0
    np.testing.assert_allclose(R[0, 1], .00006)
    np.testing.assert_allclose(R[:4, 4:], np.zeros((4, 4)))
    # Opposite center/bias shifts are observationally indistinguishable.
    shifted = x + np.array([.1, -.1, 0, 0, -.1, .1])
    np.testing.assert_allclose(model.h(x, context), model.h(shifted, context))
    np.testing.assert_allclose(model.project(x, np.eye(6)).center_xy, x[:2])
    truth = build_truth(ExperimentConfig().scene, 42).sample(0.)
    assert model.truth_mapping(truth).indices == (0, 1, 2, 3)


@pytest.mark.parametrize("params", [{"q_bias": -1}, {"q_accel": -1},
                                    {"position_std": 0}, {"yaw_std": 0},
                                    {"xy_correlation": 1}, {"reference_yaw": float("nan")}])
def test_bias_example_rejects_invalid_noise_parameters(params):
    with pytest.raises(ValueError):
        load_model((ROOT / "examples/models/custom_xy_bias.py").read_text(),
                   params, GeometryConfig())


@pytest.mark.parametrize("filename,n", [("custom-xy.json", 4), ("custom-xy-bias.json", 6)])
def test_importable_examples_run_ekf_ukf_with_four_state_nees(filename, n):
    config = ExperimentConfig.model_validate_json((ROOT / "examples" / filename).read_text())
    if n == 6:
        assert config.models[0].source == (ROOT / "examples/models/custom_xy_bias.py").read_text()
    assert not validate_experiment(config)
    model_ids = {model.id for model in config.models}
    assert all(mode.model_id in model_ids for instance in config.instances for mode in instance.imm.models)
    config.scene.duration_s = .12
    config.forecast.leads_s = [.02]
    payload = evaluate_run(run_experiment(config)).payload
    assert {item["kind"] for item in payload["instances"]} == {"ekf", "ukf"}
    for instance in payload["instances"]:
        assert instance["status"] == "completed"
        assert len(instance["state_names"]) == n
        assert instance["samples"][-1]["nees"]["dof"] == 4
        assert instance["samples"][-1]["physical"]["armor_positions"] is None
        assert np.isfinite(instance["samples"][-1]["x"]).all()
