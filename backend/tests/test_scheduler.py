import numpy as np
import pytest
from filtervisual.config.schema import default_experiment
from filtervisual.simulation.runner import run_experiment


def config(duration=.1):
    c=default_experiment()
    c.scene.duration_s=duration
    c.scene.translation.mode="constant"
    c.observation.mode="fixed"
    c.observation.frequency_hz=40.
    c.instances=c.instances[:1]
    c.forecast.enabled=False
    return c


def test_low_frequency_uses_latest_new_observation_once():
    c=config();c.instances[0].frequency_hz=20.
    a=run_experiment(c).instances[0]
    assert a.error is None
    assert [x.t for x in a.updates]==pytest.approx([0,.05,.1])
    c.instances[0].frequency_hz=10.
    b=run_experiment(c).instances[0]
    assert [x.t for x in b.updates]==pytest.approx([0,.1])


def test_noncommensurate_frequency_and_missing_frames():
    c=config(.2);c.instances[0].frequency_hz=37.;c.observation.frequency_hz=100.
    a=run_experiment(c).instances[0]
    assert a.error is None
    assert len(a.consumed_observation_ids)==len(set(a.consumed_observation_ids))
    assert all(abs(row.t*100-round(row.t*100))<1e-10 for row in a.updates)
    c.observation.dropout_probability=1.;c.forecast.enabled=True
    b=run_experiment(c).instances[0]
    assert b.updates==[] and b.forecasts==[]


@pytest.mark.parametrize("kind",["ekf","ukf","imm"])
def test_enabling_forecast_does_not_change_main_sequence(kind):
    c=config(.1);c.instances[0].kind=kind
    off=run_experiment(c).instances[0]
    c.forecast.enabled=True;c.forecast.leads_s=[.013,.025]
    on=run_experiment(c).instances[0]
    assert off.error is None and on.error is None
    for a,b in zip(off.samples,on.samples):
        np.testing.assert_array_equal(a.x,b.x)
        np.testing.assert_array_equal(a.P,b.P)
    assert len(on.forecasts)==2*len(on.updates)


def test_high_frequency_does_not_repeat_measurements():
    c=config();c.instances[0].frequency_hz=200.;c.observation.frequency_hz=50.
    a=run_experiment(c).instances[0]
    assert a.error is None
    assert len(a.updates)==6
    assert len(set(a.consumed_observation_ids))==6


def test_instances_and_scan_candidates_own_independent_models():
    from filtervisual.config.schema import ModelDefinition
    from filtervisual.models.custom import TEMPLATE
    from filtervisual.tuning.scan import scan_noise
    c=config(.04)
    source=TEMPLATE.replace("# Metadata,", "calls=0\n    def R(self,frame):\n        self.calls+=1\n        return super().R(frame)*(1+self.calls)\n\n    # Metadata,")
    c.models=[ModelDefinition(id="counter",kind="python",source=source)]
    a=c.instances[0];a.model_id="counter"
    b=a.model_copy(deep=True);b.id="second";c.instances.append(b)
    result=run_experiment(c)
    for first,second in zip(result.instances[0].samples,result.instances[1].samples):
        np.testing.assert_array_equal(first.x,second.x)
        np.testing.assert_array_equal(first.P,second.P)
    scan=scan_noise(c,a.id,"q_scale",[1,1],result.data)
    baseline=scan["baseline"]["payload"]["instances"][0]["samples"]
    for candidate in scan["candidates"]:
        assert candidate["payload"]["instances"][0]["samples"]==baseline


def test_observation_values_are_read_only():
    from filtervisual.core.types import ObservationFrame
    frame=ObservationFrame.scalar(0.,1.)
    with pytest.raises(ValueError):
        frame.values[0]=2.
