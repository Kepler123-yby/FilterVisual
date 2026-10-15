import numpy as np

from filtervisual.evaluation.report import evaluate_run
from filtervisual.tuning.rules import suggest
from test_report import fake_result


def test_consistency_rule_requires_50_samples_and_cites_multiple_causes():
    small = fake_result(count=49)
    for diagnostic in small.instances[0].updates:
        diagnostic.innovation[0] = 10
    evaluated = evaluate_run(small)
    assert not any("outside_fraction" in row["evidence"]["metric"] for row in suggest(evaluated))
    enough = fake_result(count=50)
    for diagnostic in enough.instances[0].updates:
        diagnostic.innovation[0] = 10
    evaluated = evaluate_run(enough)
    rows = [row for row in suggest(evaluated) if row["evidence"]["metric"].startswith("nis_outside")]
    assert len(rows) == 1
    assert rows[0]["evidence"]["count"] == 50
    assert rows[0]["evidence"]["interval"] == [0, 1]
    assert len(rows[0]["causes"]) >= 2
    assert rows[0]["hypothesis"] is True
    assert rows[0]["trial_patch"]["q_scale"] == 3


def test_suggestion_does_not_mutate_original_parameters():
    result = fake_result(count=50)
    before = result.config.model_dump()
    for diagnostic in result.instances[0].updates:
        diagnostic.innovation[0] = 10
    evaluate_run(result)
    assert result.config.model_dump() == before


def test_frequency_suggestion_uses_actual_update_rate():
    evaluated = evaluate_run(fake_result(count=5))
    frequency = [row for row in suggest(evaluated) if row["evidence"]["metric"] == "actual_update_hz"]
    assert frequency[0]["evidence"]["value"] == 4
    assert frequency[0]["trial_patch"] == {}


def test_scanning_reuses_observations_and_preserves_config(monkeypatch):
    from filtervisual.tuning.scan import scan_noise
    from filtervisual.simulation.runner import build_data, run_instance

    result = fake_result(count=3, duration=.2)
    result.config.forecast.enabled = False
    result.data = build_data(result.config)
    before = result.config.model_dump()
    seen_data = []

    def tracked_run(*args, **kwargs):
        seen_data.append(args[2])
        return run_instance(*args, **kwargs)

    monkeypatch.setattr("filtervisual.simulation.runner.run_instance", tracked_run)
    out = scan_noise(result.config, "test", "q_scale", [.3, 1, 3], result.data)
    assert len(seen_data) == 4
    assert all(data is result.data for data in seen_data)
    assert out["observation_hash"] == result.data.observation_hash
    assert out["baseline"]["value"] == 1
    assert [candidate["value"] for candidate in out["candidates"]] == [.3, 1, 3]
    assert all(candidate["payload"]["observations"] == out["baseline"]["payload"]["observations"]
               for candidate in out["candidates"])
    assert result.config.model_dump() == before


def test_scan_rejects_scene_changes_before_reusing_data():
    import pytest
    from filtervisual.simulation.runner import build_data
    from filtervisual.tuning.scan import scan_noise
    result = fake_result(count=3, duration=.2)
    data = build_data(result.config)
    result.config.scene.geometry.radius_a += .1
    with pytest.raises(ValueError, match="scene_hash"):
        scan_noise(result.config, "test", "q_scale", [1], data)


def test_scan_rejects_observation_changes_before_reusing_data():
    import pytest
    from filtervisual.simulation.runner import build_data
    from filtervisual.tuning.scan import scan_noise
    result=fake_result(count=3,duration=.2)
    data=build_data(result.config)
    result.config.observation.std_xyz*=2
    with pytest.raises(ValueError,match="observation_config_hash"):
        scan_noise(result.config,"test","q_scale",[1],data)


def test_scan_imm_resolves_distinct_mode_model_ids():
    from filtervisual.config.schema import IMMModeConfig, ModelDefinition
    from filtervisual.simulation.runner import build_data
    from filtervisual.tuning.scan import scan_noise
    result = fake_result(kind="imm", count=3, duration=.2)
    result.config.forecast.enabled = False
    result.config.models.extend([
        ModelDefinition(id="calm", params={"q_translation": .1}),
        ModelDefinition(id="maneuver", params={"q_translation": 2}),
    ])
    result.config.instances[0].imm.models = [
        IMMModeConfig(model_id="calm"), IMMModeConfig(model_id="maneuver"),
    ]
    data = build_data(result.config)
    out = scan_noise(result.config, "test", "q_scale", [1], data)
    assert out["baseline"]["report"]["instances"][0]["status"] == "completed"
    assert out["candidates"][0]["payload"]["instances"][0]["samples"][0]["mode_probabilities"] is not None


def test_scan_progress_and_cancellation():
    import pytest
    from filtervisual.core.types import RunCancelled
    from filtervisual.simulation.runner import build_data
    from filtervisual.tuning.scan import scan_noise
    result=fake_result(count=3,duration=.04)
    result.config.forecast.enabled=False
    events=[]
    scan_noise(result.config,"test","q_scale",[1],build_data(result.config),emit=events.append)
    assert events[-1].completed_events==events[-1].total_events==2000
    with pytest.raises(RunCancelled):
        scan_noise(result.config,"test","q_scale",[1],build_data(result.config),cancel=lambda:True)


def test_scan_uses_exactly_the_normal_evaluation_grid():
    from filtervisual.simulation.runner import run_experiment
    from filtervisual.tuning.scan import scan_noise

    config = fake_result(count=3, duration=.10000000005).config
    config.forecast.enabled = False
    config.evaluation.frequency_hz = 10.
    normal = run_experiment(config)
    expected = [row.t for row in normal.instances[0].samples]
    scanned = scan_noise(config, "test", "q_scale", [1], normal.data)
    assert [row["t"] for row in scanned["baseline"]["payload"]["instances"][0]["samples"]] == expected
    assert scanned["baseline"]["report"]["instances"][0]["position_rmse"] == (
        evaluate_run(normal).payload["report"]["instances"][0]["position_rmse"]
    )


def test_scan_ranking_uses_common_times_and_stable_candidate_indices(monkeypatch):
    import copy
    import pytest
    from filtervisual.simulation.runner import build_data
    from filtervisual.tuning.scan import scan_noise

    result = fake_result(count=3)
    result.config.forecast.enabled = False
    baseline = copy.deepcopy(result.instances[0])
    first = copy.deepcopy(baseline)
    second = copy.deepcopy(baseline)
    for sample in baseline.samples:
        sample.x[0] = result.data.truth.sample(sample.t).center_xy[0] + .5
    for index, sample in enumerate(first.samples):
        sample.x[0] = result.data.truth.sample(sample.t).center_xy[0] + (1 if index == 2 else 0)
    second.samples = second.samples[-1:]
    second.samples[0].x[0] = result.data.truth.sample(1.).center_xy[0] + .7
    trials = iter([baseline, first, second])
    monkeypatch.setattr("filtervisual.simulation.runner.run_instance", lambda *args, **kwargs: next(trials))
    # Duplicate multipliers still refer to distinct actual trials.
    out = scan_noise(result.config, "test", "q_scale", [1, 1], build_data(result.config))
    comparison = out["common_comparison"]
    assert comparison["common_count"] == 1
    assert comparison["evidence_interval"] == [1., 1.]
    assert comparison["best_candidate_index"] == 1
    assert [row["candidate_index"] for row in comparison["scores"]] == [None, 0, 1]
    assert [row["rmse"] for row in comparison["scores"]] == pytest.approx([.5, 1., .7])
    assert out["candidates"][0]["report"]["instances"][0]["position_rmse"] < .7
    assert out["report"]["common_comparison"] == comparison
    assert "1 个共同有效时刻" in out["summary"][1]


def test_scan_does_not_rank_disjoint_valid_windows(monkeypatch):
    import copy
    from filtervisual.simulation.runner import build_data
    from filtervisual.tuning.scan import scan_noise

    result = fake_result(count=3)
    result.config.forecast.enabled = False
    trials = []
    for index in range(3):
        run = copy.deepcopy(result.instances[0])
        run.samples = run.samples[index:index + 1]
        trials.append(run)
    trial_iter = iter(trials)
    monkeypatch.setattr("filtervisual.simulation.runner.run_instance", lambda *args, **kwargs: next(trial_iter))
    out = scan_noise(result.config, "test", "q_scale", [.3, 3], build_data(result.config))
    comparison = out["common_comparison"]
    assert comparison["common_count"] == 0
    assert comparison["evidence_interval"] is None
    assert comparison["best_candidate_index"] is None
    assert all(row["rmse"] is None and row["reason"] == "no_common_times" for row in comparison["scores"])
    assert not any("最小" in line for line in out["summary"])
