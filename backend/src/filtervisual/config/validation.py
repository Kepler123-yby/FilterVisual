"""Cross-field physical and matrix validation with actionable field paths."""
from __future__ import annotations
from dataclasses import dataclass
import math
import numpy as np
from .schema import ExperimentConfig


@dataclass
class ValidationIssue:
    path: str
    code: str
    message: str


def validate_experiment(config: ExperimentConfig) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    def add(path, text, code="invalid"):
        issues.append(ValidationIssue(path, code, text))

    def positive(path, value, maximum=None):
        if not math.isfinite(value) or value <= 0 or maximum is not None and value > maximum:
            add(path, f"请输入大于 0{f' 且不超过 {maximum}' if maximum else ''}的有限值")

    def matrix(path, value, n=None, definite=True):
        try:
            m = np.asarray(value, float)
            if m.ndim != 2 or m.shape[0] != m.shape[1] or n is not None and m.shape != (n,n):
                raise ValueError("矩阵维数必须与状态或观测维数一致")
            if not np.isfinite(m).all() or not np.allclose(m, m.T, rtol=1e-10, atol=1e-12):
                raise ValueError("矩阵必须有限且对称")
            eig = np.linalg.eigvalsh(m)
            if definite and eig.min() <= 0 or not definite and eig.min() < -1e-12:
                raise ValueError("矩阵必须正定" if definite else "矩阵必须半正定")
        except (ValueError, TypeError, np.linalg.LinAlgError) as e:
            add(path, str(e), "invalid_covariance")

    positive("scene.duration_s", config.scene.duration_s, 120.)
    if config.seed < 0:
        add("seed", "随机种子须为非负整数")
    positive("scene.simulation_dt", config.scene.simulation_dt, 1.)
    g = config.scene.geometry
    positive("scene.geometry.radius_a", g.radius_a, 3.)
    positive("scene.geometry.radius_b", g.radius_b, 3.)
    if g.height_a < 0 or g.height_a+g.height_diff < 0:
        add("scene.geometry.height_diff", "两组板高均需不小于 0")
    if g.reference_id not in range(4):
        add("scene.geometry.reference_id", "参考板编号须为 0、1、2、3")
    tr = config.scene.translation
    if len(tr.initial_xy) != 2 or len(tr.velocity_xy) != 2:
        add("scene.translation", "XY 位置与速度均须为两个分量")
    if not math.isfinite(tr.speed_min):
        add("scene.translation.speed_min", "有向速度下限须为有限值")
    if not math.isfinite(tr.speed_max) or tr.speed_max < tr.speed_min:
        add("scene.translation.speed_max", "有向速度上限须为有限值且不小于下限")
    positive("scene.translation.node_interval_s", tr.node_interval_s)
    if tr.mode == "waypoints" and (not tr.waypoints or any(
            b.time_s <= a.time_s for a,b in zip(tr.waypoints, tr.waypoints[1:]))):
        add("scene.translation.waypoints", "速度节点须非空且按时间严格递增")
    for i, waypoint in enumerate(tr.waypoints):
        if not math.isfinite(waypoint.speed):
            add(f"scene.translation.waypoints[{i}].speed", "节点有向速度须为有限值")
        if not math.isfinite(waypoint.heading_rad):
            add(f"scene.translation.waypoints[{i}].heading_rad", "节点方向须为有限值")
        if not math.isfinite(waypoint.time_s) or waypoint.time_s < 0 or waypoint.time_s > config.scene.duration_s:
            add(f"scene.translation.waypoints[{i}].time_s", "节点时间须在仿真范围内")
    if len(config.scene.rotation.terms) > 32:
        add("scene.rotation.terms", "正弦项最多 32 个")
    obs = config.observation
    positive("observation.frequency_hz", obs.frequency_hz, 1000.)
    if len(obs.viewpoint_xyz) != 3 or obs.plate_id not in range(4):
        add("observation", "视点需要 XYZ 三个分量，板编号为 0…3")
    if obs.std_xyz < 0 or obs.std_yaw < 0:
        add("observation.std_xyz", "真实噪声标准差须非负")
    for key in ("dropout_probability", "outlier_probability"):
        if not 0 <= getattr(obs,key) <= 1:
            add("observation."+key, "概率须在 0…1")
    positive("observation.outlier_scale", obs.outlier_scale)
    if obs.covariance is not None:
        matrix("observation.covariance", obs.covariance, definite=False)
        if len(obs.covariance) not in (4,16):
            add("observation.covariance", "真实观测协方差需要 4×4 或 16×16")
    model_ids = [m.id for m in config.models]
    if len(model_ids) != len(set(model_ids)):
        add("models", "模型 ID 不能重复")
    definitions = {m.id:m for m in config.models}
    for i,m in enumerate(config.models):
        if m.kind == "python" and not m.source:
            add(f"models[{i}].source", "请填写 Python 模型源码")
        if m.kind == "builtin":
            if m.builtin_name not in ("rm_cv", "robomaster_cv"):
                add(f"models[{i}].builtin_name", "请选择 rm_cv 内置模型")
            else:
                try:
                    from filtervisual.models.registry import make_model
                    make_model(m, config.scene.geometry)
                except (ValueError, TypeError) as error:
                    add(f"models[{i}].params", str(error))
    ids = [f.id for f in config.instances]
    if len(ids) != len(set(ids)):
        add("instances", "实例 ID 不能重复")
    if not config.instances or len(config.instances) > 12:
        add("instances", "需要 1…12 个滤波器实例")
    for i,f in enumerate(config.instances):
        p=f"instances[{i}]"
        positive(p+".frequency_hz", f.frequency_hz, 1000.)
        if f.model_id not in definitions:
            add(p+".model_id", "引用的模型不存在")
        if not f.x0 or not np.isfinite(f.x0).all():
            add(p+".x0", "初始状态须非空且有限")
        if len(f.x0) > 32:
            add(p+".x0", "首版最多支持 32 维状态")
        matrix(p+".p0",f.p0,len(f.x0))
        if f.q_scale < 0 or f.r_scale <= 0:
            add(p+".r_scale", "Q 倍率须非负，R 倍率须为正")
        if f.ukf.alpha <= 0 or f.ukf.beta < 0 or len(f.x0)+f.ukf.kappa <= 0:
            add(p+".ukf", "UKF 参数需满足 α>0、β≥0、n+κ>0")
        if f.kind == "imm":
            imm=f.imm; n=len(imm.models)
            if n<2 or n>8 or len(imm.probabilities)!=n:
                add(p+".imm.probabilities", "IMM 需要 2…8 个模式及等长概率")
            elif any(v<0 for v in imm.probabilities) or not np.isclose(sum(imm.probabilities),1.):
                add(p+".imm.probabilities", "初始模式概率须非负且和为 1")
            try:
                rate=np.asarray(imm.generator,float)
                off=rate.copy();np.fill_diagonal(off,0)
                if rate.shape!=(n,n) or not np.isfinite(rate).all() or (off<0).any() or not np.allclose(rate.sum(axis=1),0,atol=1e-10):
                    raise ValueError("转移率矩阵须方阵、非对角非负且每行和为 0")
            except (ValueError,TypeError) as e:
                add(p+".imm.generator",str(e))
            for j,mode in enumerate(imm.models):
                if mode.model_id not in definitions:
                    add(p+".imm.models", "IMM 子模式引用的模型不存在")
                if mode.q_scale < 0 or mode.r_scale <= 0:
                    add(p+f".imm.models[{j}].r_scale", "Q 倍率须非负，R 倍率须为正")
    for i,tau in enumerate(config.forecast.leads_s):
        positive(f"forecast.leads_s[{i}]",tau,30.)
    if not config.forecast.leads_s or len(config.forecast.leads_s)>16:
        add("forecast.leads_s", "需要 1…16 个预测提前量")
    positive("forecast.max_step_s",config.forecast.max_step_s,1.)
    positive("evaluation.frequency_hz",config.evaluation.frequency_hz,500.)
    if not 0 < config.evaluation.confidence < 1:
        add("evaluation.confidence", "置信水平须在 0…1")
    if not 1 <= config.evaluation.monte_carlo_trials <= 200:
        add("evaluation.monte_carlo_trials", "独立试验次数须在 1…200")
    return issues
