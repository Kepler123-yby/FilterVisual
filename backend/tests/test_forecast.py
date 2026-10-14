import numpy as np
import pytest
from filtervisual.config.schema import ForecastConfig
from filtervisual.simulation.forecast import forecast_after_update
from helpers import make_cv_filter


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
