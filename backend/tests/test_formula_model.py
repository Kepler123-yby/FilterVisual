import copy

import numpy as np
import pytest

from filtervisual.config.schema import GeometryConfig
from filtervisual.core.types import ObservationContext, ObservationFrame
from filtervisual.filters.ekf import ExtendedKalmanFilter
from filtervisual.filters.ukf import UnscentedKalmanFilter
from filtervisual.models.custom import check_contract, load_model
from filtervisual.models.formula import FormulaModel
from filtervisual.models.protocol import numerical_jacobian
from filtervisual.models.rm_cv import RoboMasterCVModel
from filtervisual.scene.motion import build_truth
from filtervisual.config.schema import SceneConfig


SOURCE = """from filtervisual.models.formula import FormulaModel
def build_model(params, geometry):
    return FormulaModel(params, geometry)
"""


def diagonal(expressions):
    return [[value if i == j else "0" for j in range(len(expressions))]
            for i, value in enumerate(expressions)]


def xy_spec():
    return {
        "version": 1,
        "states": [
            dict(name=name, unit=unit, angular=False, initial=0., variance=1., transition=transition, truth=role)
            for name, unit, transition, role in (
                ("px", "m", "px + ux * dt", "cx"), ("py", "m", "py + uy * dt", "cy"),
                ("ux", "m/s", "ux", "vx"), ("uy", "m/s", "uy", "vy"),
            )
        ],
        "observation": ["px + plate_radius * cos(plate_offset)",
                        "py + plate_radius * sin(plate_offset)", "plate_height", "plate_offset"],
        "q": diagonal(["0.1 * dt", "0.1 * dt", "0.2 * dt", "0.2 * dt"]),
        "r": diagonal(["0.01**2", "0.01**2", "0.01**2", "0.02**2"]),
    }


def canonical_spec():
    model = RoboMasterCVModel(GeometryConfig())
    initial = [0., 0., .2, .5, .1, 0., .3, 1., .25, .35, .08]
    transitions = ["cx + vx*dt", "cy + vy*dt", "zA + vz*dt", "vx", "vy", "vz",
                   "theta + omega*dt", "omega", "rA", "rB", "dh"]
    q = diagonal(["0"] * 11)
    for position, velocity, strength in ((0, 3, ".5"), (1, 4, ".5"), (2, 5, ".5"), (6, 7, ".8")):
        q[position][position] = f"{strength}*dt**3/3"
        q[position][velocity] = q[velocity][position] = f"{strength}*dt**2/2"
        q[velocity][velocity] = f"{strength}*dt"
    for index in (8, 9, 10):
        q[index][index] = "1e-6*dt"
    return dict(version=1, states=[dict(name=name, unit=unit, angular=index == 6,
        initial=initial[index], variance=.1, transition=transitions[index], truth=name)
        for index, (name, unit) in enumerate(zip(model.state_names, model.units))],
        observation=["cx+((1-plate_odd)*rA+plate_odd*rB)*cos(theta+plate_offset)",
                     "cy+((1-plate_odd)*rA+plate_odd*rB)*sin(theta+plate_offset)",
                     "zA+plate_odd*dh", "theta+plate_offset"], q=q,
        r=diagonal([".01**2", ".01**2", ".01**2", ".02**2"]))


def context(ids=(0, 1, 2, 3)):
    return ObservationContext(time_s=.1, plate_ids=ids,
                              angular_indices=tuple(4*i+3 for i in range(len(ids))))


def test_form_model_uses_existing_custom_contract_and_preserves_input():
    spec = xy_spec()
    params, geometry = {"form_model": spec}, GeometryConfig(reference_id=2)
    original = copy.deepcopy(params)
    model = load_model(SOURCE, params, geometry)
    metadata = check_contract(model, geometry, [0., 0., .5, 0.], np.eye(4))
    assert metadata["dimension"] == 4
    assert params == original
    geometry.radius_a = 9.
    spec["states"][0]["name"] = "changed"
    np.testing.assert_allclose(model.f([1., 2., 3., 4.], .1), [1.3, 2.4, 3., 4.])
    expected = [1.-.25, 2., .2, -np.pi, 1., 2.-.35, .28, -np.pi/2.]
    np.testing.assert_allclose(model.h([1., 2., 3., 4.], context((0, 1))), expected, atol=1e-14)
    assert model.angular_indices == ()


def test_all_transition_rows_read_old_state_and_expose_time_only_in_f():
    spec = xy_spec()
    spec["states"][0]["transition"] = "py + sin(t0) + max(dt, 0)"
    spec["states"][1]["transition"] = "px"
    model = FormulaModel({"form_model": spec}, GeometryConfig())
    np.testing.assert_allclose(model.f([1., 2., 3., 4.], .2, np.pi/2.)[:2], [3.2, 1.])


def test_full_form_model_matches_builtin_equations_projection_and_numeric_jacobians():
    spec = canonical_spec()
    geometry = GeometryConfig(reference_id=3)
    model = FormulaModel({"form_model": spec}, geometry)
    builtin = RoboMasterCVModel(geometry)
    x = np.array([row["initial"] for row in spec["states"]])
    P = np.diag(np.linspace(.001, .01, 11))
    frame = ObservationFrame(.1, context((3, 1)), np.zeros(8))
    np.testing.assert_allclose(model.f(x, .17), builtin.f(x, .17))
    np.testing.assert_allclose(model.h(x, frame.context), builtin.h(x, frame.context))
    np.testing.assert_allclose(model.Q(.17), builtin.Q(.17))
    np.testing.assert_allclose(model.R(frame), builtin.R(frame))
    np.testing.assert_allclose(numerical_jacobian(lambda state: model.f(state, .17), x),
                               builtin.jacobian_f(x, .17), atol=1e-9)
    np.testing.assert_allclose(numerical_jacobian(lambda state: model.h(state, frame.context), x),
                               builtin.jacobian_h(x, frame.context), atol=1e-9)
    actual, expected = model.project(x, P), builtin.project(x, P)
    np.testing.assert_allclose(actual.armor_positions, expected.armor_positions)
    for field in expected.covariance:
        np.testing.assert_allclose(actual.covariance[field], expected.covariance[field], atol=1e-14)
    assert check_contract(model, geometry, x, P)["angular_indices"] == [6]
    x[8] = -1.
    assert not model.project(x, P).valid


def test_reordered_subset_truth_mapping_uses_subset_angular_indices_and_no_invented_armor():
    spec = xy_spec()
    spec["states"].insert(0, dict(name="bias", unit="m", angular=False,
        initial=0., variance=1., transition="bias", truth=""))
    spec["states"][2].update(name="heading", unit="rad", angular=True, transition="heading", truth="theta")
    spec["states"][0]["transition"] = "bias"
    spec["q"] = diagonal(["dt"] * 5)
    spec["observation"] = ["px", "0", "height_a", "heading"]
    model = FormulaModel({"form_model": spec}, GeometryConfig())
    physical = build_truth(SceneConfig(), 42).sample(.1)
    mapping = model.truth_mapping(physical)
    assert mapping.indices == (1, 2, 3, 4)
    assert mapping.angular_indices == (1,)
    np.testing.assert_allclose(mapping.values,
        [physical.center_xy[0], physical.reference_yaw, *physical.velocity_xyz[:2]])
    estimate = model.project(np.zeros(5), np.eye(5))
    assert estimate.center_xy is None and estimate.armor_positions is None
    np.testing.assert_allclose(estimate.velocity_xyz, [0., 0., 0.])


@pytest.mark.parametrize("engine", [ExtendedKalmanFilter, UnscentedKalmanFilter])
def test_formula_model_predict_update_works_without_manual_f_or_h(engine):
    model = FormulaModel({"form_model": xy_spec()}, GeometryConfig())
    filter_ = engine(model, [0., 0., .5, .1], np.eye(4)*.1)
    filter_.predict(.1)
    ctx = context((2,))
    frame = ObservationFrame(.1, ctx, model.h([.05, .01, .5, .1], ctx))
    result = filter_.update(frame)
    assert np.isfinite(result.posterior.x).all()
    assert np.linalg.eigvalsh(result.posterior.P).min() > 0.
    np.testing.assert_allclose(result.innovation, 0., atol=1e-12)


@pytest.mark.parametrize("expression", [
    "__import__('os').getcwd()", "px.real", "[px][0]", "sum(px for px in [1])",
    "lambda: px", "px if px else 0", "True", "np.sin(px)", "sin(x=px)", "min(px)",
    "2**1000000", "1e999", "sqrt(-1)", "1/0",
])
def test_unsafe_or_nonfinite_expressions_are_rejected_with_row_location(expression):
    spec = xy_spec()
    spec["states"][0]["transition"] = expression
    with pytest.raises(ValueError, match="f 状态第 1 行"):
        model = FormulaModel({"form_model": spec}, GeometryConfig())
        model.f(np.zeros(4), .1)


@pytest.mark.parametrize("field,expression,location", [
    ("observation", "dt", "h 观测第 1 行"),
    ("observation", "t0", "h 观测第 1 行"),
    ("q", "px", "Q 第 1 行第 1 列"),
    ("q", "t0", "Q 第 1 行第 1 列"),
    ("r", "dt", "R 第 1 行第 1 列"),
    ("r", "plate_id", "R 第 1 行第 1 列"),
])
def test_expression_context_does_not_expose_unsupported_variables(field, expression, location):
    spec = xy_spec()
    if field == "observation":
        spec[field][0] = expression
    else:
        spec[field][0][0] = expression
    with pytest.raises(ValueError, match=location):
        FormulaModel({"form_model": spec}, GeometryConfig())


@pytest.mark.parametrize("change,message", [
    (lambda s: s["states"][0].update(name="dt"), "状态第 1 行 名称"),
    (lambda s: s["states"][0].update(name="py"), "状态第 2 行 名称"),
    (lambda s: s["states"][0].update(variance=0.), "状态第 1 行 初始方差"),
    (lambda s: s["states"][0].update(initial=float("inf")), "状态第 1 行 初值"),
    (lambda s: s["states"][1].update(truth="cx"), "状态第 2 行 真值对应"),
    (lambda s: s["states"][0].update(unit="cm"), "状态第 1 行 真值对应 cx 的单位须为 m"),
    (lambda s: s["states"][0].update(truth="theta", unit="rad"), "状态第 1 行 真值对应 theta 须勾选角度标记"),
    (lambda s: s["states"][0].update(angular=True), "状态第 1 行 真值对应 cx 不能勾选角度标记"),
    (lambda s: s.update(q=[["0"]]), "Q 须为 4×4"),
    (lambda s: s["q"][0].__setitem__(1, "dt"), "Q 须为有限的对称半正定"),
    (lambda s: s["q"][0].__setitem__(0, "-dt"), "Q 须为有限的对称半正定"),
    (lambda s: s["r"][0].__setitem__(0, "0"), "R 须为有限的对称正定"),
])
def test_bad_state_metadata_or_covariance_reports_form_field(change, message):
    spec = xy_spec()
    change(spec)
    with pytest.raises(ValueError, match=message):
        FormulaModel({"form_model": spec}, GeometryConfig())


def test_invalid_plate_ids_are_rejected_and_noise_is_fresh():
    model = FormulaModel({"form_model": xy_spec()}, GeometryConfig())
    for ids in ((), (0, 0), (4,), (True,), (0.,)):
        with pytest.raises(ValueError, match="装甲板编号"):
            model.h(np.zeros(4), context(ids))
    frame = ObservationFrame(0., context((0, 2)), np.zeros(8))
    r = model.R(frame)
    r[0, 0] = 999.
    assert model.R(frame)[0, 0] == pytest.approx(.0001)
    assert not model.Q(0.).any()
    with pytest.raises(ValueError, match="dt"):
        model.Q(-1.)
