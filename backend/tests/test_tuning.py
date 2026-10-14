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
