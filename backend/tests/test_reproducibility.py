import numpy as np
from filtervisual.simulation.runner import run_experiment


def short_config(baseline_config):
    baseline_config.scene.duration_s=.3
    baseline_config.scene.simulation_dt=.005
    baseline_config.instances=baseline_config.instances[:2]
    baseline_config.observation.mode="all"
    return baseline_config


def test_forecast_branches_do_not_change_main_results(baseline_config):
    c=short_config(baseline_config)
    enabled=run_experiment(c)
    c.forecast.enabled=False
    disabled=run_experiment(c)
    for a,b in zip(enabled.instances,disabled.instances):
        assert a.consumed_observation_ids==b.consumed_observation_ids
        for x,y in zip(a.samples,b.samples):
            np.testing.assert_array_equal(x.x,y.x)
            np.testing.assert_array_equal(x.P,y.P)


def test_identical_config_reuses_exact_truth_and_observations(baseline_config):
    c=short_config(baseline_config)
    a,b=run_experiment(c),run_experiment(c)
    assert a.data.observation_hash==b.data.observation_hash
    for x,y in zip(a.instances,b.instances):
        for u,v in zip(x.samples,y.samples):
            np.testing.assert_array_equal(u.x,v.x)
            np.testing.assert_array_equal(u.P,v.P)
