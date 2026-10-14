import numpy as np
import pytest
from filtervisual.config.schema import ForecastConfig
from filtervisual.simulation.forecast import advance_to, forecast_after_update
from helpers import assert_snapshot_equal, make_cv_filter


@pytest.mark.parametrize("kind",["ekf","ukf"])
def test_lookahead_keeps_main_filter_unchanged(kind):
    f=make_cv_filter(kind,position=1.,velocity=2.)
    before=f.snapshot()
    out=forecast_after_update(f,"baseline",ForecastConfig(enabled=True,leads_s=[.1,.2,.3]))
    np.testing.assert_allclose([x.state[0] for x in out],[1.2,1.4,1.6],atol=1e-10)
    np.testing.assert_array_equal(f.snapshot().x,before.x)
    np.testing.assert_array_equal(f.snapshot().P,before.P)
    assert f.predict(.01).x[0]==pytest.approx(1.02)
    assert [x.target_time for x in out]==pytest.approx([.1,.2,.3])


def test_duplicate_horizons_and_exact_endpoint():
    out=forecast_after_update(make_cv_filter("ekf"),"a",ForecastConfig(leads_s=[.013,.013,.3]))
    assert len(out)==3
    assert out[0].target_time==pytest.approx(.013)
    np.testing.assert_allclose(out[0].state,out[1].state)


def test_failed_branch_does_not_change_posterior():
    f=make_cv_filter("ekf")
    # Raising in a copy's predict simulates a model valid for its local operating region.
    def fail(dt):
        raise ValueError("prediction domain")
    f.predict=fail
    out=forecast_after_update(f,"a",ForecastConfig(leads_s=[.1]))
    assert out[0].error=="prediction domain"
    assert f.x[0]==1.
    assert f.t==0.


def assert_independent_forecasts(filter, leads, step=.005):
    before = filter.snapshot()
    expected = []
    for lead in leads:
        branch = filter.clone()
        advance_to(branch, before.t + lead, step)
        expected.append(branch.snapshot())
    actual = forecast_after_update(filter, "comparison", ForecastConfig(leads_s=leads, max_step_s=step))
    assert_snapshot_equal(filter.snapshot(), before)
    assert [row.lead_s for row in actual] == leads
    for row, snapshot in zip(actual, expected):
        assert row.error is None
        assert row.target_time == before.t + row.lead_s
        np.testing.assert_allclose(row.state, snapshot.x, atol=1e-12, rtol=1e-12)
        np.testing.assert_allclose(row.P, snapshot.P, atol=1e-12, rtol=1e-12)
        if snapshot.mode_probabilities is not None:
            np.testing.assert_allclose(row.mode_probabilities, snapshot.mode_probabilities,
                                       atol=1e-12, rtol=1e-12)
    return actual


@pytest.mark.parametrize("kind", ["ekf", "ukf", "imm"])
def test_shared_prefix_matches_independent_noninteger_unordered_and_duplicate_leads(kind):
    filter = make_cv_filter(kind, position=1.3, velocity=2.1, q=.2)
    filter.predict(.173)
    assert_independent_forecasts(filter, [.137, .013, .1, .137, .2017, .005, .00501])


@pytest.mark.parametrize("kind", ["ekf", "ukf", "imm"])
def test_shared_prefix_custom_time_dependent_nonlinear_model(kind):
    from filtervisual.config.schema import FilterConfig, GeometryConfig
    from filtervisual.models.custom import load_model
    from filtervisual.models.registry import make_filter

    source = '''import numpy as np
from filtervisual.models.rm_cv import RoboMasterCVModel
class NonlinearCV(RoboMasterCVModel):
    def f(self, x, dt, t0):
        y = super().f(x, dt, t0)
        y[0] += dt * (.02 * x[0] ** 2 + np.sin(t0))
        return y
def build_model(params, geometry): return NonlinearCV(geometry)
'''
    model = load_model(source, {}, GeometryConfig())
    config = FilterConfig(id="custom", name="custom", kind=kind)
    config.x0[0], config.x0[6], config.x0[7] = 1.3, np.pi - .03, 2.1
    config.p0 = (np.eye(11) * .02).tolist()
    filter = make_filter(config, model)
    filter.predict(.173)
    assert_independent_forecasts(filter, [.087, .013, .087, .1551])


def test_prefix_reuse_reduces_imm_steps_without_coalescing_them(monkeypatch):
    from filtervisual.filters.imm import InteractingMultipleModel

    calls = []
    original = InteractingMultipleModel.predict
    def tracked(self, dt):
        calls.append(dt)
        return original(self, dt)
    monkeypatch.setattr(InteractingMultipleModel, "predict", tracked)
    forecasts = forecast_after_update(make_cv_filter("imm"), "imm",
                                     ForecastConfig(leads_s=[.1, .3, .5]))
    assert all(row.error is None for row in forecasts)
    assert len(calls) == 102  # 99 shared steps, three independently finished endpoints.
    assert max(calls) <= .005 + 1e-12


def test_shared_prefix_retains_ukf_angle_chart_shortcut_guard():
    from filtervisual.config.schema import FilterConfig, GeometryConfig
    from filtervisual.models.registry import make_filter
    from filtervisual.models.rm_cv import RoboMasterCVModel

    config = FilterConfig(id="ukf", name="ukf", kind="ukf")
    covariance = np.eye(11) * .02
    covariance[7, 7] = 4.
    config.p0 = covariance.tolist()
    filter = make_filter(config, RoboMasterCVModel(GeometryConfig()))
    assert filter.can_predict_exact(.1)
    assert not filter.can_predict_exact(1.1)
    assert_independent_forecasts(filter, [1.1, .1, .1317, 1.1])


def test_partial_endpoint_failure_does_not_damage_longer_shared_prefix():
    filter = make_cv_filter("ekf")
    original = filter.model.f
    def fail_only_partial(x, dt, t0):
        if .0029 < dt < .0031:
            raise ValueError("partial endpoint domain")
        return original(x, dt, t0)
    filter.model.f = fail_only_partial
    before = filter.snapshot()
    forecasts = forecast_after_update(filter, "partial", ForecastConfig(leads_s=[.013, .02]))
    assert forecasts[0].error == "partial endpoint domain"
    assert forecasts[1].error is None
    assert forecasts[1].state[0] == pytest.approx(1.04)
    assert_snapshot_equal(filter.snapshot(), before)
