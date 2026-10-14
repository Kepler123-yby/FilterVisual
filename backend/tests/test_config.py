import numpy as np
from filtervisual.config.schema import ExperimentConfig, default_experiment
from filtervisual.config.validation import validate_experiment


def test_default_config_is_valid_and_roundtrips():
    c=default_experiment()
    assert validate_experiment(c)==[]
    assert ExperimentConfig.model_validate_json(c.model_dump_json())==c


def test_reject_invalid_covariance_and_horizon(baseline_config):
    c=baseline_config.model_copy(deep=True)
    c.instances[0].p0[0][0]=-1
    c.forecast.leads_s=[.1,-.2]
    paths={x.path for x in validate_experiment(c)}
    assert "instances[0].p0" in paths
    assert "forecast.leads_s[1]" in paths


def test_cross_field_errors_are_specific(baseline_config):
    c=baseline_config.model_copy(deep=True)
    c.instances[1].id=c.instances[0].id
    c.instances[0].frequency_hz=0
    c.scene.geometry.reference_id=4
    c.instances[2].imm.generator=[[.2,-.2],[1,-1]]
    paths={x.path for x in validate_experiment(c)}
    assert {"instances","instances[0].frequency_hz","scene.geometry.reference_id","instances[2].imm.generator"}<=paths


def test_invalid_seeds_waypoints_and_mode_noise_are_rejected(baseline_config):
    from filtervisual.config.schema import Waypoint
    c=baseline_config
    c.seed=-1
    c.scene.translation.mode="waypoints"
    c.scene.translation.waypoints=[Waypoint(time_s=0,speed=-1,heading_rad=0)]
    c.instances[2].imm.models[0].r_scale=-1
    paths={x.path for x in validate_experiment(c)}
    assert {"seed", "scene.translation.waypoints[0].speed", "instances[2].imm.models[0].r_scale"}<=paths


def test_invalid_builtin_parameters_rejected(baseline_config):
    baseline_config.models[0].params={"q_translation": -1}
    assert "models[0].params" in {x.path for x in validate_experiment(baseline_config)}
