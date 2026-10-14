"""Local trusted Python models; API validation runs in a bounded child process."""
from __future__ import annotations

import multiprocessing as mp
import copy
import traceback
import numpy as np

from filtervisual.config.schema import GeometryConfig, ModelDefinition
from filtervisual.core.linalg import validate_covariance
from filtervisual.core.types import ObservationContext, ObservationFrame

TEMPLATE = '''import numpy as np
from filtervisual.models.rm_cv import RoboMasterCVModel

class CustomCV(RoboMasterCVModel):
    # Metadata, angular residuals, projection and truth mapping are inherited.
    # Override f/h/Q/R and their Jacobians together when equations change.
    def f(self, x, dt, t0):
        y = np.asarray(x, dtype=float).copy()
        y[:3] += y[3:6] * dt
        y[6] += y[7] * dt
        return y

    def f_batch(self, points, dt, t0):
        return np.array([self.f(x, dt, t0) for x in points])

def build_model(params, geometry):
    return CustomCV(geometry, **params)
'''


def load_model(source: str, params: dict, geometry: GeometryConfig):
    namespace = {"__name__": "filtervisual_user_model"}
    exec(compile(source, "<user-model>", "exec"), namespace)
    factory = namespace.get("build_model")
    if not callable(factory):
        raise ValueError("源码须提供 build_model(params, geometry)")
    model = factory(copy.deepcopy(params), geometry.model_copy(deep=True))
    names=tuple(getattr(model,"state_names",()))
    units=tuple(getattr(model,"units",()))
    angular=tuple(getattr(model,"angular_indices",()))
    if (not 1<=len(names)<=32 or len(set(names))!=len(names) or len(units)!=len(names)
            or any(not isinstance(i,(int,np.integer)) or not 0<=i<len(names) for i in angular)):
        raise ValueError("模型元数据 state_names/units/angular_indices 不匹配")
    # A subclass changing an equation must not silently retain the built-in
    # optimized implementation of that equation or its old Jacobian.
    def owner(name):
        if name in getattr(model,"__dict__",{}):
            return type(model)
        return next((cls for cls in type(model).__mro__ if name in cls.__dict__),None)
    for equation, helpers in (("f",("f_batch","jacobian_f")),
                              ("h",("jacobian_h",)),
                              ("state_residual",("state_residual_batch",))):
        implementation = owner(equation)
        for helper in helpers:
            inherited = owner(helper)
            if (equation in getattr(model,"__dict__",{}) and helper not in getattr(model,"__dict__",{})) or (implementation and inherited and type(model).__mro__.index(implementation) < type(model).__mro__.index(inherited)):
                setattr(model,helper,None)
    # Custom models always use requested prediction substeps; inherited claims
    # about the built-in semigroup cannot authorize a different equation.
    model.exact_linear_prediction = False
    model._filtervisual_custom=True
    model._filtervisual_geometry=geometry.model_copy(deep=True)
    return model


def load_custom_model(definition: ModelDefinition, geometry: GeometryConfig):
    return load_model(definition.source or "", definition.params, geometry)


def check_contract(model, geometry, x0=None, p0=None):
    names = tuple(model.state_names)
    units = tuple(model.units)
    angular = tuple(model.angular_indices)
    n = len(names)
    if not 1 <= n <= 32 or len(units) != n or len(set(names)) != n:
        raise ValueError("state_names 须为 1…32 个唯一名称，units 须等长")
    if any(not isinstance(i, int) or not 0 <= i < n for i in angular):
        raise ValueError("angular_indices 须是有效的状态索引")
    x = np.zeros(n) if x0 is None else np.asarray(x0, float)
    if n == 11 and x0 is None:
        x[[2,8,9,10]] = [geometry.height_a,geometry.radius_a,geometry.radius_b,geometry.height_diff]
    P = np.eye(n) if p0 is None else np.asarray(p0, float)
    if x.shape != (n,) or not np.isfinite(x).all():
        raise ValueError(f"x0 须为 {n} 维有限向量")
    validate_covariance(P, name="P0", positive_definite=True)
    if P.shape != (n,n):
        raise ValueError("P0 形状与状态不一致")
    required = ("f","h","Q","R","state_residual","observation_residual",
                "state_mean","observation_mean","project","truth_mapping")
    for name in required:
        if not callable(getattr(model,name,None)):
            raise ValueError(f"缺少模型接口 {name}")
    def shaped(value, shape, equation):
        a = np.asarray(value,float)
        if a.shape != shape or not np.isfinite(a).all():
            raise ValueError(f"{equation} 应返回有限数组 {shape}，实际为 {a.shape}")
        return a
    shaped(model.f(x.copy(),.01,0.),(n,),"f(x,dt,t0)")
    if callable(getattr(model,"f_batch",None)):
        probes=np.array([x,x+.001])
        actual=shaped(model.f_batch(probes,.01,0.),probes.shape,"f_batch")
        expected=np.array([model.f(p.copy(),.01,0.) for p in probes])
        if not np.allclose(actual,expected,atol=1e-10,rtol=1e-8):
            raise ValueError("f_batch 与 f 不一致")
    shaped(model.state_residual(x,x),(n,),"state_residual")
    shaped(model.state_mean(np.array([x,x]),np.array([.5,.5])),(n,),"state_mean")
    for dt in (0.,.01,.2):
        q = shaped(model.Q(dt),(n,n),"Q(dt)")
        validate_covariance(q,name="Q",positive_definite=False)
    for ids in ((0,),(1,),(0,1,2,3)):
        ctx=ObservationContext(time_s=0.,plate_ids=ids,angular_indices=tuple(4*i+3 for i in range(len(ids))))
        h=np.asarray(model.h(x.copy(),ctx),float)
        if h.ndim != 1 or len(h) != 4*len(ids) or not np.isfinite(h).all():
            raise ValueError("h 须按 plate_ids 返回每板 [x,y,z,yaw] 四维观测")
        frame=ObservationFrame(0.,ctx,h)
        shaped(model.observation_residual(h,h,ctx),h.shape,"observation_residual")
        shaped(model.observation_mean(np.array([h,h]),np.array([.5,.5]),ctx),h.shape,"observation_mean")
        r=shaped(model.R(frame),(len(h),len(h)),"R(frame)")
        validate_covariance(r,name="R",positive_definite=True)
        if callable(getattr(model,"jacobian_h",None)):
            shaped(model.jacobian_h(x,ctx),(len(h),n),"jacobian_h")
    if callable(getattr(model,"jacobian_f",None)):
        shaped(model.jacobian_f(x,.01,0.),(n,n),"jacobian_f")
    from filtervisual.models.protocol import validate_projection
    validate_projection(model.project(x,P))
    from filtervisual.scene.motion import build_truth
    from filtervisual.config.schema import SceneConfig
    physical=build_truth(SceneConfig(duration_s=.01,geometry=geometry),0).sample(0.)
    mapping=model.truth_mapping(physical)
    if mapping is not None:
        indices=tuple(mapping.indices)
        if (len(indices)!=len(mapping.values) or len(set(indices))!=len(indices)
                or any(not isinstance(i,(int,np.integer)) or isinstance(i,bool) or i<0 or i>=n for i in indices)
                or not np.isfinite(mapping.values).all()):
            raise ValueError("truth_mapping 的 indices/values 不匹配")
        if any(not isinstance(i,(int,np.integer)) or i<0 or i>=len(indices) for i in mapping.angular_indices):
            raise ValueError("truth_mapping.angular_indices 须索引映射子集")
    return {"state_names":list(names),"units":list(units),"angular_indices":list(angular),"dimension":n}


def _validate_child(queue, definition, geometry, x0, p0):
    try:
        from filtervisual.models.registry import make_model
        model=make_model(ModelDefinition.model_validate(definition),GeometryConfig.model_validate(geometry))
        metadata=check_contract(model,GeometryConfig.model_validate(geometry),x0,p0)
        queue.put({"valid":True,"issues":[],"metadata":metadata})
    except Exception as error:
        line = error.lineno if isinstance(error,SyntaxError) else next(
            (f.lineno for f in reversed(traceback.extract_tb(error.__traceback__)) if f.filename=="<user-model>"),None)
        queue.put({"valid":False,"issues":[{"message":str(error),"line":line,"field":"source"}],"metadata":None})


def validate_model(definition, geometry, x0=None, p0=None, timeout_s=5.):
    ctx=mp.get_context("spawn")
    queue=ctx.Queue()
    process=ctx.Process(target=_validate_child,args=(queue,definition.model_dump(),geometry.model_dump(),x0,p0))
    process.start()
    try:
        # Receive before join: larger metadata must not deadlock the feeder.
        result=queue.get(timeout=timeout_s)
        process.join(timeout=1.)
        return result
    except Exception:
        return {"valid":False,"issues":[{"message":"模型验证超时或进程退出（限时 5 秒）","line":None,"field":"source"}],"metadata":None}
    finally:
        if process.is_alive():
            process.terminate();process.join(timeout=1.)
        queue.close()
