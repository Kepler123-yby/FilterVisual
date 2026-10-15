from filtervisual.models.custom import TEMPLATE,validate_model,load_model,check_contract
from filtervisual.config.schema import GeometryConfig,ModelDefinition


def test_custom_template_contract_and_isolated_validation():
    definition=ModelDefinition(kind="python",source=TEMPLATE)
    result=validate_model(definition,GeometryConfig())
    assert result["valid"],result
    assert result["metadata"]["dimension"]==11


def test_custom_syntax_errors_have_source_line():
    result=validate_model(ModelDefinition(kind="python",source="def broken(:\n pass"),GeometryConfig())
    assert not result["valid"]
    assert result["issues"][0]["line"]==1


def test_bad_equation_reports_shape():
    source=TEMPLATE.replace("y = np.asarray(x, dtype=float).copy()","return np.zeros(2)\n        y = np.asarray(x, dtype=float).copy()")
    result=validate_model(ModelDefinition(kind="python",source=source),GeometryConfig())
    assert not result["valid"] and "f(x,dt,t0)" in result["issues"][0]["message"]


def test_infinite_model_is_terminated():
    result=validate_model(ModelDefinition(kind="python",source="while True: pass"),GeometryConfig(),timeout_s=.3)
    assert not result["valid"] and "超时" in result["issues"][0]["message"]


def test_overriding_f_disables_inherited_batch_and_jacobian():
    import numpy as np
    from filtervisual.filters.ukf import UnscentedKalmanFilter
    source='''from filtervisual.models.rm_cv import RoboMasterCVModel
class Accelerated(RoboMasterCVModel):
    def f(self,x,dt,t0):
        y=super().f(x,dt,t0)
        y[0]+=3*dt
        return y
def build_model(params,geometry): return Accelerated(geometry)
'''
    model=load_model(source,{},GeometryConfig())
    assert model.f_batch is None and model.jacobian_f is None
    assert not model.exact_linear_prediction
    x=np.zeros(11);x[8:10]=.2
    engine=UnscentedKalmanFilter(model,x,np.eye(11)*.01)
    assert np.isclose(engine.predict(.1).x[0],.3)


def test_contract_rejects_duplicate_truth_mapping():
    source=TEMPLATE.replace("# Metadata,", "def truth_mapping(self, physical):\n        from filtervisual.core.types import TruthMapping\n        return TruthMapping((0,0),[0.,0.])\n\n    # Metadata,")
    result=validate_model(ModelDefinition(kind="python",source=source),GeometryConfig())
    assert not result["valid"] and "truth_mapping" in result["issues"][0]["message"]


def test_instance_equation_override_disables_inherited_helpers():
    import numpy as np
    source='''from filtervisual.models.rm_cv import RoboMasterCVModel
def build_model(params,geometry):
    model=RoboMasterCVModel(geometry)
    original=model.f
    def changed(x,dt,t0):
        y=original(x,dt,t0);y[0]+=2*dt;return y
    model.f=changed
    return model
'''
    model=load_model(source,{},GeometryConfig())
    assert model.f_batch is None and model.jacobian_f is None
    x=np.zeros(11);x[8:10]=.2
    from filtervisual.filters.ukf import UnscentedKalmanFilter
    assert np.isclose(UnscentedKalmanFilter(model,x,np.eye(11)*.01).predict(.1).x[0],.2)


def test_contract_rejects_inconsistent_batch_state_residual():
    import numpy as np
    import pytest
    model = load_model(TEMPLATE, {}, GeometryConfig())
    model.state_residual_batch = lambda points, mean: np.zeros_like(points)
    with pytest.raises(ValueError, match="state_residual_batch.*state_residual"):
        check_contract(model, GeometryConfig())


def test_contract_rejects_malformed_batch_state_residual():
    import numpy as np
    import pytest
    model = load_model(TEMPLATE, {}, GeometryConfig())
    model.state_residual_batch = lambda points, mean: np.zeros(len(points))
    with pytest.raises(ValueError, match="state_residual_batch"):
        check_contract(model, GeometryConfig())
