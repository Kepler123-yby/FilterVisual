import json

import numpy as np
import pytest

from filtervisual.config.schema import ExperimentConfig, FilterConfig, RotationConfig, SceneConfig, SineTerm, TranslationConfig
from filtervisual.core.types import Estimate, ForecastRecord, InstanceRun, PhysicalEstimate, RunResult, SimulationData, TruthMapping, UpdateDiagnostics
from filtervisual.evaluation.monte_carlo import aggregate_trials
from filtervisual.evaluation.report import canonical_truth_state, evaluate_run
from filtervisual.models.rm_cv import RoboMasterCVModel
from filtervisual.scene.motion import build_truth


def fake_result(kind="ekf", count=5, duration=1):
    config = ExperimentConfig(
        scene=SceneConfig(duration_s=duration, simulation_dt=.025,
                          translation=TranslationConfig(mode="constant", velocity_xy=[1, 0]),
                          rotation=RotationConfig(mode="angular_velocity", terms=[SineTerm(amplitude=0, offset=2)])),
        instances=[FilterConfig(id="test", name="真实对照", kind=kind)],
    )
    model = RoboMasterCVModel(config.scene.geometry)
    truth = build_truth(config.scene, config.seed)
    data = SimulationData(truth, [], scene_hash="scene-hash", observation_hash="observation-hash")
    times = np.linspace(0, duration, count)
    samples = []
    for time in times:
        state = canonical_truth_state(truth.sample(time))
        state[0] += .1
        state[6] += .02
        samples.append(Estimate(time, state, np.eye(11)))
    diagnostics = [UpdateDiagnostics(time, np.array([1., 0, 0, 0]), np.eye(4), 4, sample)
                   for time, sample in zip(times, samples)]
    run = InstanceRun(config.instances[0], model, samples=samples, updates=diagnostics,
                      consumed_observation_ids=[str(i) for i in range(count)], elapsed_s=.2)
    return RunResult(config, data, [run], times)


def test_runtime_truth_mapping_error_keeps_healthy_instance_report():
    import copy
    result=fake_result(count=3,duration=.1)
    bad=copy.deepcopy(result.instances[0])
    bad.config.id="bad-mapping";bad.config.name="坏映射"
    bad.model.truth_mapping=lambda physical: TruthMapping((0,0),[0.,0.])
    result.instances.append(bad)
    payload=evaluate_run(result).payload
    assert payload["instances"][0]["status"]=="completed"
    assert payload["instances"][1]["status"]=="failed"
    assert payload["instances"][1]["samples"][0]["nees"]["reason"]=="invalid_truth_mapping"
    assert any("部分实例失败" in line for line in payload["report"]["summary"])


def test_bad_physical_projection_does_not_break_report():
    result=fake_result(count=3,duration=.1)
    result.instances[0].model.project=lambda x,P: PhysicalEstimate(center_xy=np.array(["bad","bad"]))
    payload=evaluate_run(result).payload
    assert not payload["instances"][0]["samples"][0]["physical"]["valid"]
    assert payload["instances"][0]["samples"][0]["physical_error"]["center_xy"] is None


def add_forecast(result, origin, lead, error=.2, failed=False):
    target = origin + lead
    if target <= result.config.scene.duration_s:
        state = canonical_truth_state(result.data.truth.sample(target))
    else:
        state = canonical_truth_state(result.data.truth.sample(result.config.scene.duration_s))
    state[0] += error
    covariance = np.eye(11)
    projection = result.instances[0].model.project(state, covariance)
    if failed:
        state = np.full(11, np.nan)
        covariance = np.full((11, 11), np.nan)
        projection = PhysicalEstimate(valid=False, error="bad model")
    forecast = ForecastRecord("test", origin, lead, target, state, covariance, projection)
    if failed:
        forecast.error = "bad model"
    result.instances[0].forecasts.append(forecast)


def test_report_scores_actual_data_and_is_strict_json():
    result = fake_result()
    evaluated = evaluate_run(result)
    instance = evaluated.payload["instances"][0]
    report = evaluated.payload["report"]["instances"][0]
    assert instance["samples"][0]["nees"]["value"] == pytest.approx(.1**2 + .02**2)
    assert instance["updates"][0]["nis"]["value"] == 1
    assert report["position_rmse"] == pytest.approx(.1)
    assert report["angle_rmse"] == pytest.approx(.02)
    assert report["actual_update_hz"] == 4
    assert report["elapsed_s"] == .2
    assert evaluated.payload["truth"][1]["state"][0] == pytest.approx(.25)
    assert "RMSE" in evaluated.payload["report"]["summary"][0]
    json.dumps(evaluated.payload, allow_nan=False)


def test_forecast_errors_use_target_time_and_unavailable_tail_is_null():
    result = fake_result()
    add_forecast(result, .2, .3)
    add_forecast(result, .9, .3)
    forecasts = evaluate_run(result).payload["instances"][0]["forecasts"]
    assert forecasts[0]["target_time"] == .5
    assert forecasts[0]["error"][0] == pytest.approx(.2)
    assert forecasts[0]["physical_error"]["center_xy"] == pytest.approx([.2, 0])
    assert forecasts[0]["nis"]["value"] is None
    assert forecasts[0]["nis"]["reason"] == "no_new_observation"
    assert forecasts[1]["error"] == [None] * 11
    assert forecasts[1]["nees"]["reason"] == "truth_unavailable"
    assert forecasts[1]["truth_physical"] is None
    forecast_report = evaluate_run(result).payload["report"]["instances"][0]["forecast"][0]
    assert forecast_report["count"] == 1
    assert forecast_report["position_rmse"] == pytest.approx(.2)
    assert forecast_report["truth_unavailable"] == 1


def test_prediction_failure_is_not_a_zero_error_or_main_failure():
    result = fake_result()
    add_forecast(result, .2, .3, failed=True)
    evaluated = evaluate_run(result)
    instance = evaluated.payload["instances"][0]
    assert instance["status"] == "completed"
    assert instance["forecasts"][0]["prediction_error"] == "bad model"
    assert instance["forecasts"][0]["physical_error"] is None
    assert instance["forecasts"][0]["nees"]["reason"] == "prediction_failed"
    assert evaluated.payload["report"]["instances"][0]["forecast"][0]["count"] == 0
    json.dumps(evaluated.payload, allow_nan=False)


def test_partial_state_truth_mapping_does_not_score_unmapped_state():
    class PartialModel:
        state_names = ("unmapped", "cx")
        units = ("1", "m")
        angular_indices = ()

        def truth_mapping(self, physical):
            return TruthMapping((1,), np.array([physical.center_xy[0]]))

        def project(self, state, covariance):
            return PhysicalEstimate(center_xy=np.array([state[1], 0]))

    result = fake_result()
    result.instances[0].model = PartialModel()
    result.instances[0].samples = [Estimate(0, np.array([999, .1]), np.eye(2))]
    evaluated = evaluate_run(result)
    sample = evaluated.payload["instances"][0]["samples"][0]
    assert sample["truth"] == [None, 0]
    assert sample["error"] == [None, .1]
    assert sample["nees"]["dof"] == 1
    assert sample["nees"]["state_names"] == ["cx"]
    assert sample["nees"]["value"] == pytest.approx(.01)
    assert evaluated.payload["report"]["instances"][0]["rmse"] == [None, .1]


def test_angular_error_wraps_and_imm_is_approximate():
    result = fake_result(kind="imm")
    result.instances[0].samples[0].x[6] += 2 * np.pi
    evaluated = evaluate_run(result)
    sample = evaluated.payload["instances"][0]["samples"][0]
    assert sample["error"][6] == pytest.approx(.02)
    assert sample["nees"]["assumption"] == "gaussian_mixture_approximation"
    assert "近似" in sample["nees"]["label"]


def test_imm_report_summarizes_real_mode_probabilities():
    result = fake_result(kind="imm", count=3)
    for sample, probabilities in zip(result.instances[0].samples, [[.8, .2], [.4, .6], [.2, .8]]):
        sample.mode_probabilities = np.array(probabilities)
    report = evaluate_run(result).payload["report"]
    modes = report["instances"][0]["mode_probability_summary"]
    assert modes["last"] == [.2, .8]
    assert modes["dominant_mode_changes"] == 1
    assert any("80.0%" in text for text in report["summary"])


def test_report_marks_partial_failure_without_claiming_complete_comparison():
    result = fake_result()
    result.instances[0].error = "numerical failure"
    report = evaluate_run(result).payload["report"]
    assert report["instances"][0]["status"] == "failed"
    assert any("部分实例失败" in text for text in report["summary"])
    assert all("最小值" not in text for text in report["summary"])


def test_model_loading_failure_does_not_remove_good_instance():
    result = fake_result()
    bad_config = result.config.instances[0].model_copy(update={"id": "bad", "name": "坏模型"})
    result.instances.append(InstanceRun(bad_config, None, error="missing build_model"))
    result.config.instances.append(bad_config)
    evaluated = evaluate_run(result)
    assert evaluated.payload["instances"][0]["status"] == "completed"
    assert evaluated.payload["instances"][1]["status"] == "failed"
    assert evaluated.payload["instances"][1]["samples"] == []
    assert any("坏模型" in text for text in evaluated.payload["report"]["summary"])


def test_comparison_uses_common_valid_times_instead_of_each_instances_own_window():
    result = fake_result(count=3)
    first = result.instances[0]
    for index, sample in enumerate(first.samples):
        sample.x[0] = result.data.truth.sample(sample.t).center_xy[0] + (1 if index == 2 else 0)
    other_config = first.config.model_copy(update={"id": "other", "name": "共同窗口胜者"})
    other_x = canonical_truth_state(result.data.truth.sample(1))
    other_x[0] += .7
    other = InstanceRun(other_config, first.model, samples=[Estimate(1, other_x, np.eye(11))])
    result.instances.append(other)
    result.config.instances.append(other_config)
    evaluated = evaluate_run(result)
    comparison = next(row for row in evaluated.payload["report"]["comparisons"] if row["quantity"] == "center_xy")
    assert comparison["common_count"] == 1
    assert comparison["best_instance_id"] == "other"
    assert comparison["best_rmse"] == pytest.approx(.7)
    assert comparison["evidence_interval"] == [1, 1]


def test_monte_carlo_uses_independent_trials_at_same_time_and_actual_count():
    first, second = evaluate_run(fake_result(count=3)).payload, evaluate_run(fake_result(count=3)).payload
    second["instances"][0]["samples"][0]["nees"]["value"] = .3
    second["instances"][0]["updates"][0]["nis"]["value"] = None
    groups = aggregate_trials([first, second])
    nees = next(row for row in groups if row["statistic"] == "anees" and row["t"] == 0)
    nis = next(row for row in groups if row["statistic"] == "anis" and row["t"] == 0)
    assert nees["count"] == 2
    assert nees["mean"] == pytest.approx((.0104 + .3) / 2)
    from scipy.stats import chi2
    assert nees["bounds"] == pytest.approx([chi2.ppf(.025, 22) / 2, chi2.ppf(.975, 22) / 2])
    assert nis["count"] == 1
    assert nis["bounds"] == pytest.approx([chi2.ppf(.025, 4), chi2.ppf(.975, 4)])
    assert "same_time" in nees["interpretation"]


def test_real_monte_carlo_preserves_config_and_aggregates_seed_trials():
    from filtervisual.evaluation.monte_carlo import run_monte_carlo
    result = fake_result(count=3, duration=.2)
    before = result.config.model_dump()
    assert result.config.forecast.enabled is True
    out = run_monte_carlo(result.config, [42, 43])
    assert out["trials"] == 2
    assert out["groups"]
    assert all(row["count"] == 2 for row in out["groups"])
    assert all(row["statistic"] in ("anis", "anees") for row in out["groups"])
    assert result.config.model_dump() == before
    assert "不运行附带纯预测" in out["notes"][0]


def test_invalid_projection_finite_values_are_not_scored_or_ranked():
    result = fake_result(count=3)
    result.instances[0].model.project = lambda x, P: PhysicalEstimate(
        valid=False, error="projection outside domain", center_xy=np.array([0., 0.]),
        reference_yaw=0.,
    )
    add_forecast(result, .2, .3)
    payload = evaluate_run(result).payload
    instance = payload["instances"][0]
    assert instance["samples"][0]["physical"]["valid"] is False
    assert instance["samples"][0]["physical_error"]["center_xy"] is None
    assert instance["forecasts"][0]["physical_error"]["center_xy"] is None
    report = payload["report"]
    assert report["instances"][0]["position_rmse"] is None
    assert report["instances"][0]["angle_rmse"] is None
    assert report["instances"][0]["position_count"] == 0
    assert report["instances"][0]["angle_count"] == 0
    assert report["instances"][0]["forecast"][0]["count"] == 0
    assert report["comparisons"] == []
