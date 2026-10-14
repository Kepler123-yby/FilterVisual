# FilterVisual Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 交付可编辑 RoboMaster 四装甲板运动、比较 EKF/UKF/IMM、评估更新后未来状态预测并给出可验证调参建议的本地 app。

**Architecture:** Python 负责确定性真值、共同观测流、滤波、时序、纯预测和诊断；React 负责参数编辑与同步可视化。每次实验生成不可变配置与数值结果，界面只回放或筛选结果，不通过动画时间驱动滤波。数学核心先独立验收，再接 API 和 UI。

**Tech Stack:** React 19 / TypeScript / Vite / Plotly.js / Monaco；Python / FastAPI / Pydantic 2 / NumPy 2.2.6 / SciPy 1.15.3；pytest / Vitest / Playwright。

**Spec:** `docs/superpowers/specs/2026-10-15-filtervisual-design.md`。先阅读该文档；其中“建议默认值”可在审阅后改动，不能当作已由用户逐项确认的约束。

## 执行完成记录（2026-10-15）

Task 1–11 的产品代码、示例、文档和最终验收已完成。实际按三个阶段统一提交并上传 GitHub；先失败测试与逐任务提交的原始流程文字保留为设计记录，不表示还有功能待开发。验收结果见 [acceptance.md](../../acceptance.md)，阶段记录见 [progress.md](../../progress.md)。

- [x] Task 1–5：配置、几何/真值、EKF/UKF/IMM、指标、调度和更新后纯预测。
- [x] Task 6–7：一致性评估/报告/参数扫描/MC、本地作业、存储、模型验证和导出。
- [x] Task 8–10：可编辑比较界面、独立 IMM/自定义模型、预测/报告和参数试验界面。
- [x] Task 11：149 个后端测试、21 个前端测试、4 个真实 E2E、构建、安装、启停、基准及文档。

## Global Constraints

- Python >=3.10；兼容当前环境的 Python 3.10.12。
- Node.js >=22.12；兼容当前环境的 Node.js 22.23.2。
- 前端采用 React 19、TypeScript、Vite、Plotly.js、Monaco；界面文案使用中文。
- 后端采用 FastAPI、Pydantic 2、NumPy 2.2.6、SciPy 1.15.3；测试采用 pytest、Vitest、Playwright。
- 首次实现时生成并提交精确依赖锁文件；本次文档阶段不安装依赖。
- 所有计算统一使用米、秒、弧度；UI 可显示角度制，但序列化保留单位元数据。
- 数值计算与绘图刷新独立；改变回放速度或动画帧率不得改变仿真和滤波结果。
- 每次运行绑定不可变配置、模型源码、种子和版本；编辑配置只生成草稿，不修改旧结果。
- 默认服务仅监听 127.0.0.1；自定义 Python 仅用于本地用户认可的模型，工作进程提供异常和超时隔离。
- 生产代码不复用讨论草图中的示意曲线或假指标。

## Review Focus

1. 角度经过 ±π、可见板切换或参考板不同：角度残差正确，板身份和参考角不混淆；Task 2、3。
2. 非整除频率、过高频率及缺测：观测只校正一次，按真实时间戳处理，报告实际校正频率；Task 5。
3. 错误矩阵、模型源码异常和维数变化：给出具体字段/实例错误，不让成功实例或旧结果消失；Task 1、7、9。
4. 预测目标越过场景末尾、重复提前量及纯预测开关：缺真值明确为空，主滤波结果不变；Task 5、10。
5. 未映射状态、不同自由度、IMM 混合与多种子统计：不输出伪 NEES、伪 NIS 或严格“检验通过”；Task 6、10。

---

## 文件结构与任务边界

以下是拟创建路径，本次仅保存文档。各文件按职责拆分，不建立重复数值实现。

```text
backend/
  pyproject.toml, requirements.lock
  src/filtervisual/
    __init__.py
    core/types.py, core/angles.py, core/linalg.py
    config/schema.py, config/validation.py
    scene/geometry.py, scene/motion.py, scene/observations.py
    models/protocol.py, models/registry.py, models/rm_cv.py, models/custom.py
    filters/protocol.py, filters/ekf.py, filters/ukf.py, filters/imm.py
    simulation/scheduler.py, simulation/forecast.py, simulation/runner.py
    evaluation/metrics.py, evaluation/monte_carlo.py, evaluation/report.py
    tuning/rules.py, tuning/scan.py
    service/jobs.py, service/store.py, service/app.py
  tests/{conftest,helpers}.py
  tests/test_{config,geometry,motion,observations,filters,imm,scheduler,
              forecast,metrics,report,tuning,api,custom,store}.py
web/
  package.json, package-lock.json, tsconfig.json, vite.config.ts
  src/app/{App,Workbench}.tsx, src/app/styles.css
  src/api/{client,types}.ts, src/api/generated.d.ts, src/api/openapi.json
  src/experiments/{store,validation}.ts
  src/experiments/{SceneEditor,ObservationEditor,RunHistory}.tsx
  src/filters/{InstanceList,ParameterEditor,MatrixEditor,ModelEditor}.tsx
  src/plots/{TargetScene,StatePlot,ErrorPlot,ComparisonLayout,TimeCursor}.tsx
  src/forecast/{ForecastEditor,ForecastPlot}.tsx
  src/evaluation/{ConsistencyPlot,MetricsTable,ReportPanel,TuningPanel}.tsx
  tests/{configuration,comparison,model-editor,forecast-report}.test.tsx
  e2e/experiment.spec.ts
examples/{baseline,all-plates,spin-and-translation}.json
examples/models/custom_cv.py
docs/{model-authoring,getting-started,acceptance}.md
scripts/{dev.sh,benchmark.py}
.gitignore
```

任务依赖：1 → 2 → 3 → 4 → 5 → 6 → 7；8 从 7 接真实数据；9 在 3/7/8 上加入自定义编辑；10 连接 5/6/8/9；11 完成全链路验收。内部可并行：Task 2 的场景代码和 Task 3 的滤波公式；Task 6 的评估与 Task 8 的 UI 工作需等公共契约稳定。

## Task 1：配置、类型与可运行的验证入口

**Files:** Create `backend/pyproject.toml`, `backend/requirements.lock`, `backend/src/filtervisual/__init__.py`, `backend/src/filtervisual/core/types.py`, `backend/src/filtervisual/config/schema.py`, `backend/src/filtervisual/config/validation.py`, `backend/tests/conftest.py`, `backend/tests/test_config.py`, `examples/baseline.json`, `.gitignore`。

**Interfaces:**
- Produces Pydantic `ExperimentConfig(schema_version=1,seed,scene,observation,models,instances,forecast,evaluation)`；子类型为 `SceneConfig,GeometryConfig,SineTerm,ObservationConfig,FilterConfig,ForecastConfig,EvaluationConfig,ModelDefinition,UKFParameters`。
- `ModelDefinition(id,kind,builtin_name,source,params)`；kind 为 builtin/python，两个入口互斥，实例 model_id 必须引用 models 中的 ID。自定义状态元数据由源码入口返回的 Model 提供，验证后展示并保存到运行 manifest。
- `GeometryConfig` 字段为 `radius_a,radius_b,height_a,height_diff,reference_id`；`FilterConfig` 字段为 `id,name,kind,model_id,frequency_hz,x0,p0,q_scale,r_scale,ukf,imm`；`ForecastConfig(enabled,leads_s,max_step_s=0.005)`。N 始终由 `len(leads_s)` 得到，禁止存两个可互相矛盾的计数。
- Produces NumPy 数据类型 `PhysicalState(t,center_xy,height_a,velocity_xyz,reference_yaw,angular_velocity,radius_a,radius_b,height_diff,armor_positions)`、`ObservationContext(time_s,plate_ids,angular_indices)`、`ObservationFrame(t,context,values)`、`Estimate(t,x,P,mode_probabilities=None)`、`UpdateDiagnostics(t,innovation,S,dof,posterior,observation_id)`、`FilterSnapshot`、`ForecastRecord`、`InstanceRun`、`RunResult`。frame.t 和 context.time_s 必须一致。
- `validate_experiment(config: ExperimentConfig) -> list[ValidationIssue]`；`ValidationIssue(path,code,message)` 不修改输入。
- Fixtures `baseline_config` 从 baseline JSON 加载。`.gitignore` 排除 `.superpowers/, .venv/, __pycache__/, node_modules/, data/, web/dist/`，保留 examples 和文档。

- [ ] **Step 1:** 创建 Python 包的最小测试配置和验证用例，先写：

```python
def test_reject_invalid_covariance_and_horizon(baseline_config):
    c = baseline_config.model_copy(deep=True)
    c.instances[0].p0[0][0] = -1
    c.forecast.leads_s = [0.1, -0.2]
    paths = {x.path for x in validate_experiment(c)}
    assert "instances[0].p0" in paths
    assert "forecast.leads_s[1]" in paths
```

另写有限值、矩阵维数、非正频率、参考板不在 0…3、IMM 行和/负转移率、重复实例 ID 的拒绝测试，以及合法配置 JSON 往返保持值。
- [ ] **Step 2:** 在 `.venv` 中安装固定的 NumPy/SciPy 和兼容 Python 3.10 的其余依赖，锁定精确版本；运行 `python -m pytest backend/tests/test_config.py -q`，确认因缺少类型或函数失败。
- [ ] **Step 3:** 实现类型与校验；从设计第 3、5 节填写 baseline JSON，三个实例共享场景但各有独立参数。
- [ ] **Step 4:** 重跑同一测试，期望全部通过；执行配置 JSON schema 导出，检查数组和单位字段可被前端消费。
- [ ] **Step 5:** 只提交该任务文件，提交信息 `feat: define experiment schema and validation`。

## Task 2：四板几何、运动真值与共同观测源

**Files:** Create `backend/src/filtervisual/scene/geometry.py`, `backend/src/filtervisual/scene/motion.py`, `backend/src/filtervisual/scene/observations.py`, `backend/tests/test_geometry.py`, `backend/tests/test_motion.py`, `backend/tests/test_observations.py`, `examples/all-plates.json`。

**Interfaces:**
- Consumes Task 1 类型。
- `armor_positions(center_xy: ndarray, geometry: GeometryConfig, reference_yaw: float) -> ndarray[4,3]`。
- `build_truth(scene: SceneConfig, seed: int) -> TruthTrajectory`，`TruthTrajectory.sample(t: float) -> PhysicalState` 仅接受 `0<=t<=duration`。
- `generate_observations(truth: TruthTrajectory, config: ObservationConfig, seed: int) -> list[ObservationFrame]`。
- `SimulationData(truth,observations,scene_hash,observation_hash)`；过滤引擎不会接收 truth 作为模型输入。

- [ ] **Step 1:** 编写解析几何与自旋用例：

```python
def test_four_plate_geometry():
    g = GeometryConfig(radius_a=.4, radius_b=.2,
        height_a=.1, height_diff=.15, reference_id=0)
    actual = armor_positions(np.array([1., 2.]), g, 0.)
    np.testing.assert_allclose(actual,
        [[1.4,2,.1],[1,2.2,.25],[.6,2,.1],[1,1.8,.25]], atol=1e-12)
```

覆盖 reference_id=1 的同一物理姿态映射、Ω=0、角速度常数 2 rad/s 在 0.3 s 后角度 0.6、速度范围始终满足、相同种子观测逐项一致、不同板切换仍保留 ID/正确 yaw、同帧多板排序。
- [ ] **Step 2:** 运行 `python -m pytest backend/tests/test_geometry.py backend/tests/test_motion.py backend/tests/test_observations.py -q`，期望新函数缺失导致失败。
- [ ] **Step 3:** 按设计第 3、4 节实现几何、解析自旋及连续真值求解；观察噪声和运动随机流用独立 `SeedSequence` 子流。
- [ ] **Step 4:** 同命令全部通过；同一 truth 在 50 Hz/37 Hz 的公共时刻 sample 一致，避免以观测采样替代真值时钟。
- [ ] **Step 5:** 提交 `feat: simulate four-armor target and observations`。

## Task 3：模型契约、角度处理与 EKF/UKF

**Files:** Create `backend/src/filtervisual/core/angles.py`, `backend/src/filtervisual/core/linalg.py`, `backend/src/filtervisual/models/protocol.py`, `backend/src/filtervisual/models/registry.py`, `backend/src/filtervisual/models/rm_cv.py`, `backend/src/filtervisual/filters/protocol.py`, `backend/src/filtervisual/filters/ekf.py`, `backend/src/filtervisual/filters/ukf.py`, `backend/tests/helpers.py`, `backend/tests/test_filters.py`。

**Interfaces:**
- `Model` 声明 `state_names,units,angular_indices` 和 `f(x,dt,t0),h(x,context),Q(dt),R(frame),jacobian_f(x,dt,t0),jacobian_h(x,context),state_residual(a,b),observation_residual(a,b,context),state_mean(points,weights),observation_mean(points,weights,context),project(x,P),truth_mapping(physical)`。t0 由 Filter 当前时间传入，模型不维护共享可变时钟。
- `truth_mapping` 返回 `TruthMapping(indices,values,angular_indices)` 或 None；`project` 返回物理状态及可用协方差投影 `PhysicalEstimate`。
- `Filter` 协议：`predict(dt: float)->Estimate`, `update(frame: ObservationFrame)->UpdateDiagnostics`, `snapshot()->FilterSnapshot`, `restore(snapshot)->None`, `clone()->Filter`；update 强制当前状态时间等于 frame.t。
- `ExtendedKalmanFilter(model,x0,P0,t0=0.,q_scale=1.,r_scale=1.)`、`UnscentedKalmanFilter(...,parameters:UKFParameters)`。
- `make_filter(config: FilterConfig, model: Model) -> Filter` 注册工厂；`make_model(definition: ModelDefinition, geometry: GeometryConfig) -> Model` 暂只支持内置模型。
- Test helpers：`make_linear_filter(kind)`（二维恒等 f/Q=0、观测第一维/R=1、x₀=[0,0]/P₀=diag(4,1)）；`make_cv_filter(kind,position=1.,velocity=2.,q=0.)`（二维匀速、初始 P=I）。

- [ ] **Step 1:** 为 EKF、UKF 参数化写解析测试：

```python
@pytest.mark.parametrize("kind", ["ekf", "ukf"])
def test_linear_update_matches_analytic_solution(kind):
    f = make_linear_filter(kind)
    f.predict(0.)
    d = f.update(ObservationFrame.scalar(t=0., value=3.))
    np.testing.assert_allclose(d.posterior.x, [2.4,0], atol=1e-8)
    np.testing.assert_allclose(d.posterior.P, np.diag([.8,1]), atol=1e-8)
    assert d.innovation[0] == pytest.approx(3.)
    assert d.S[0,0] == pytest.approx(5.)
```

在 Task 1 类型中补 `ObservationFrame.scalar` 测试构造器；再测预测 179°/观测 -179° 的创新为 +2°、Q(0.1) 中 `q*dt³/3` 项、Jacobian 对照差分、协方差对称/正定与不可修复错误。
- [ ] **Step 2:** 运行 `python -m pytest backend/tests/test_filters.py -q`，期望解析测试失败。
- [ ] **Step 3:** 实现设计第 5 节模型与两个算法；补 `TruthMapping/PhysicalEstimate` 核心类型；使用 Cholesky 求解，记录 jitter，快照数组复制并只读，clone 不共享可变状态。
- [ ] **Step 4:** 同命令全部通过；矩阵容差 1e-8，纯几何与角度容差 1e-12；分别使用内置模型运行指定板和四板观测冒烟检查。
- [ ] **Step 5:** 提交 `feat: implement angle-aware EKF and UKF`。

## Task 4：IMM 的混合、时间转移和模式概率

**Files:** Create `backend/src/filtervisual/filters/imm.py`, `backend/tests/test_imm.py`；Modify `backend/src/filtervisual/models/registry.py`, `backend/src/filtervisual/config/validation.py`, `backend/tests/helpers.py`。

**Interfaces:**
- `transition_matrix(generator: ndarray, dt: float) -> ndarray`，约定行 current/列 next。
- `fuse_gaussians(means: list[ndarray], covariances: list[ndarray], weights: ndarray, model: Model) -> tuple[ndarray,ndarray]`。
- `InteractingMultipleModel(filters:list[Filter],probabilities:ndarray,generator:ndarray)` 实现同一 Filter 协议，snapshot 包括每个子滤波器完整快照。

- [ ] **Step 1:** 编写数值测试：

```python
def test_imm_fusion_and_transition():
    mean, P = fuse_gaussians([np.array([0.]),np.array([2.])],
        [np.array([[1.]]),np.array([[1.]])], np.array([.25,.75]), scalar_model())
    assert mean[0] == pytest.approx(1.5)
    assert P[0,0] == pytest.approx(1.75)
    Pi = transition_matrix(np.array([[-1.,1.],[1.,-1.]]), .1)
    assert Pi[0,0] == pytest.approx(.9093653765)
    np.testing.assert_allclose(Pi @ Pi, transition_matrix(
        np.array([[-1.,1.],[1.,-1.]]), .2), atol=1e-10)
```

`scalar_model()` 在 helpers 中提供一维无角度模型。覆盖不等维/不同状态语义拒绝、极小似然不产生 NaN、角度跨界混合、概率和为 1、clone 模式状态隔离。
- [ ] **Step 2:** 运行 `python -m pytest backend/tests/test_imm.py -q`，期望新功能缺失而失败。
- [ ] **Step 3:** 实现 interaction → 各模式 predict → 各模式 update → log 似然归一化 → 融合；预测过程按 Λdt 推进模式概率；注册默认平稳/机动两套 Q 强度。
- [ ] **Step 4:** 同命令通过；对所有公共 Filter 测试加入 IMM 参数化，验证快照与时间行为一致。
- [ ] **Step 5:** 提交 `feat: add time-consistent IMM filtering`。

## Task 5：正常周期、未来预测和共同时间网格

**Files:** Create `backend/src/filtervisual/simulation/scheduler.py`, `backend/src/filtervisual/simulation/forecast.py`, `backend/src/filtervisual/simulation/runner.py`, `backend/tests/test_scheduler.py`, `backend/tests/test_forecast.py`；Modify `backend/src/filtervisual/core/types.py` 增加 RunProgress 与运行序列字段。

**Interfaces:**
- `run_instance(config:FilterConfig,model:Model,data:SimulationData,forecast:ForecastConfig,evaluation_times:ndarray)->InstanceRun`。
- `forecast_after_update(filter:Filter,instance_id:str,config:ForecastConfig)->list[ForecastRecord]`；函数没有 truth 或 observation 参数。
- `estimate_at(past_snapshot:FilterSnapshot,target_time:float,model:Model)->Estimate` 只允许向前传播。
- `run_experiment(config:ExperimentConfig,cancel:Callable[[],bool],emit:Callable[[RunProgress],None])->RunResult`；RunProgress 包含完成实例数、事件数、总事件数及阶段。
- InstanceRun 保存正常循环样本、校正诊断、lookahead、共同网格样本、消费/跳过观测 ID、失败原因；RunResult 保存配置快照和 SimulationData，不在数值核心写盘。

- [ ] **Step 1:** 写分支隔离测试：

```python
def test_lookahead_keeps_main_filter_unchanged():
    f = make_cv_filter("ekf", position=1., velocity=2.)
    before = f.snapshot()
    out = forecast_after_update(f, "baseline", ForecastConfig(
        enabled=True, leads_s=[.1,.2,.3], max_step_s=.005))
    np.testing.assert_allclose([x.state[0] for x in out], [1.2,1.4,1.6], atol=1e-10)
    assert_snapshot_equal(f.snapshot(), before)
    assert f.predict(.01).x[0] == pytest.approx(1.02)
```

helper `assert_snapshot_equal` 比较 t/x/P/模式快照。调度用例含：40 Hz 观测/20 Hz 周期到 0.1 s 消费 .05/.1 的帧，10 Hz 只消费 .1；37 Hz 对 100 Hz 观测必须 `update_time=observation_time`；200 Hz 循环/50 Hz 观测每帧最多校正一次；缺测不触发附带预测。测试不计 t=0 初始化帧。

另测启停及 N 变化主序列一致、IMM 的子状态与概率一致、未来真值/观测变化预测不变、重复提前量保留请求顺序、不整除提前量精确 target_time、超过场景末尾标记未评估、共同网格不引用未来后验。
- [ ] **Step 2:** 运行 `python -m pytest backend/tests/test_scheduler.py backend/tests/test_forecast.py -q`，期望失败。
- [ ] **Step 3:** 按设计第 6 节实现按时间排序的调度和独立 clone 预测；每个提前量独立从后验开始，最大子步 0.005 s。正常流程最多一次校正，然后补传播到周期边界。
- [ ] **Step 4:** 同命令通过；实例失败隔离、取消检查点与进度单调增加均可验证；同一实验不同实例直接复用已生成的观测流。
- [ ] **Step 5:** 提交 `feat: schedule filtering and post-update lookahead`。

## Task 6：指标、Monte Carlo、结果总结与候选试验

**Files:** Create `backend/src/filtervisual/evaluation/metrics.py`, `backend/src/filtervisual/evaluation/monte_carlo.py`, `backend/src/filtervisual/evaluation/report.py`, `backend/src/filtervisual/tuning/rules.py`, `backend/src/filtervisual/tuning/scan.py`, `backend/tests/test_metrics.py`, `backend/tests/test_report.py`, `backend/tests/test_tuning.py`；Modify `backend/src/filtervisual/core/types.py` 增加 EvaluatedRun、ComparisonReport、Recommendation、TuningResult、MonteCarloResult。

**Interfaces:**
- `quadratic_score(error:ndarray,covariance:ndarray)->float`, `chi_square_bounds(dof:int,confidence:float,trials:int=1)->tuple[float,float]`。
- `evaluate_run(result:RunResult)->EvaluatedRun`，含 `metrics,forecast_metrics,consistency,report`；不可用值保存为 null 并附 reason。
- `run_monte_carlo(config:ExperimentConfig,seeds:Sequence[int],cancel,emit)->MonteCarloResult`，调用同一 run_experiment。
- `build_report(evaluated:EvaluatedRun)->ComparisonReport`；`suggest(evaluated)->list[Recommendation]`。Recommendation 含 `instance_id,evidence,causes,parameter_paths,trial_patch,hypothesis=True`。
- `scan_noise(config:ExperimentConfig,instance_id:str,parameter:Literal["q_scale","r_scale"],multipliers:Sequence[float],data:SimulationData)->TuningResult`；结果保留基线和候选，不修改 config。

- [ ] **Step 1:** 写已知分数和区间测试：

```python
def test_consistency_scores_and_bounds():
    assert quadratic_score(np.array([3.]), np.array([[5.]])) == pytest.approx(1.8)
    assert quadratic_score(np.array([.4,-1.]), np.diag([.8,1.])) == pytest.approx(1.2)
    low, high = chi_square_bounds(dof=2, confidence=.95)
    assert low == pytest.approx(.05063562, rel=1e-6)
    assert high == pytest.approx(7.37775891, rel=1e-6)
```

覆盖只有部分真值映射的 NEES、角度最短差、无观测的 NIS=None、超尾预测有效计数、不同维度不排名、20 次独立试验界用 20×dof、不对时间点均值标理论检验、IMM 标签为近似参考。规则测试要求异常 ≥50 样本才提示，至少列出模型/噪声候选原因，所有建议带证据；修改未来真值只影响评分。扫描保持观测哈希且不改基线参数。
- [ ] **Step 2:** 运行 `python -m pytest backend/tests/test_metrics.py backend/tests/test_report.py backend/tests/test_tuning.py -q`，期望失败。
- [ ] **Step 3:** 实现设计第 7 节。共同状态/提前量/板 ID/有效区间分组；图表抽稀不参与指标。自动总结使用实际数值和证据索引，缺测不以零补齐。
- [ ] **Step 4:** 同命令通过；以 `[0.1,0.3,1,3,10]` 扫描合成问题，验证候选各有完整结果和参数差异，不要求某倍率在所有状态上获胜。
- [ ] **Step 5:** 提交 `feat: evaluate consistency and generate tuning evidence`。

## Task 7：本地作业 API、自定义模型工作进程与保存

**Files:** Create `backend/src/filtervisual/models/custom.py`, `backend/src/filtervisual/service/jobs.py`, `backend/src/filtervisual/service/store.py`, `backend/src/filtervisual/service/app.py`, `backend/tests/test_api.py`, `backend/tests/test_custom.py`, `backend/tests/test_store.py`；Modify `backend/src/filtervisual/models/registry.py`, `backend/pyproject.toml`。

**Interfaces:**
- `load_custom_model(definition:ModelDefinition,geometry:GeometryConfig)->Model`，编译与验证均在子进程；调用源码的 `build_model(params,geometry)`，核对返回的 Model 元数据与函数形状，不接收 truth 引用。
- `JobManager.submit(config)->run_id`, `status(run_id)->RunStatus`, `cancel(run_id)->None`；worker 调用 run_experiment + evaluate_run。
- `RunStore.save(run_id,config,result,evaluated)->None`, `load(run_id)->StoredRun`, `export(run_id,format)->bytes`；新 run UUID 独立目录，JSON+NPZ。
- `create_app(data_dir:Path)->FastAPI` 提供设计第 8 节所有端点；另 `POST /api/runs/{id}/scan` 和 `POST /api/runs/{id}/monte-carlo` 创建关联子作业，保持基线。模块导出 ASGI `app`，并提供 `python -m filtervisual.service.app --write-openapi web/src/api/openapi.json`。
- 默认 worker 同时运行一个作业，单作业超时 120 s 可配置；排队/取消/超时返回具体状态。模型验证超时 5 s。

- [ ] **Step 1:** 写 API 验证与往返用例：

```python
def test_invalid_run_is_rejected_with_field_path(client, baseline_config):
    payload = baseline_config.model_dump()
    payload["instances"][0]["frequency_hz"] = 0
    response = client.post("/api/runs", json=payload)
    assert response.status_code == 422
    assert "frequency_hz" in response.text
```

client fixture 使用 create_app(tmp_path)。再测 run 创建→完成→数值序列→报告→导出→读取一致；配置 hash 变更产生新 run；坏模型返回方程/形状错误，不阻断其他实例；取消/超时后仍保留状态；NPZ/JSON 可加载且无 pickle；NaN 序列化被拒绝。
- [ ] **Step 2:** 运行 `python -m pytest backend/tests/test_api.py backend/tests/test_custom.py backend/tests/test_store.py -q`，期望失败。
- [ ] **Step 3:** 实现单 worker 队列、取消令牌和不可变存储；失败实例写入结果；查询 series 支持 instance/kind/state/lead/time_range/offset/limit，默认 limit=2000。导出注明缺测、单位、配置和源码版本。模型源仅在 child 中加载；scan 只允许滤波参数改变，场景/观测配置 hash 不匹配时拒绝复用数据。
- [ ] **Step 4:** 同命令通过；使用 TestClient 验证健康状态与进度，启动绑定 127.0.0.1 的后端进行一次实际 HTTP 冒烟检查。
- [ ] **Step 5:** 提交 `feat: expose local run jobs and reproducible storage`。

## Task 8：接真实数据的可编辑运动与比较实验台

**Files:** Create `web/package.json`, `web/package-lock.json`, `web/tsconfig.json`, `web/vite.config.ts`, `web/src/app/{App,Workbench}.tsx`, `web/src/app/styles.css`, `web/src/api/{client,types}.ts`, `web/src/experiments/{store,validation}.ts`, `web/src/experiments/{SceneEditor,ObservationEditor,RunHistory}.tsx`, `web/src/filters/InstanceList.tsx`, `web/src/plots/{TargetScene,StatePlot,ErrorPlot,ComparisonLayout,TimeCursor}.tsx`, `web/tests/configuration.test.tsx`, `web/tests/comparison.test.tsx`。

**Interfaces:**
- Task 7 的 OpenAPI 导出后，`npm --prefix web run generate:api` 使用 openapi-typescript 从 `web/src/api/openapi.json` 生成 `web/src/api/generated.d.ts` 并提交；`types.ts` 只作类型别名和视图适配，不另维护不同字段名。package.json 配置 test、build、generate:api 和 test:e2e 脚本。
- `ExperimentStore` 暴露 `draft,selectedRunId,cursorTime,selectedState,selectedPlate,enabledInstanceIds,comparisonMode,updateDraft(path,value),submit(),selectRun(id)`；旧 run 只读。
- `api.createRun(config):Promise<RunStatus>`、`api.getStatus(id)`、`api.getSeries(query)`、`api.getReport(id)`；轮询只读进度，完成后取数值结果。
- `TargetScene` 消费实际物理投影，提供 XY/板编号/参考角/高度示意；`StatePlot/ErrorPlot` 消费 RunSeries，cursor 统一由 store 控制。

- [ ] **Step 1:** 建立最小前端测试脚本并写测试：

```typescript
it('keeps movement, fit and error visible while editing geometry', async () => {
  render(<Workbench />);
  await user.clear(screen.getByLabelText('A 组半径（m）'));
  await user.type(screen.getByLabelText('A 组半径（m）'), '0.30');
  expect(screen.getByTestId('target-scene')).toBeVisible();
  expect(screen.getByTestId('state-plot')).toBeVisible();
  expect(screen.getByTestId('error-plot')).toBeVisible();
});
```

另测复制实例生成新 ID、改参数只变草稿、旧结果显示待更新标签、选择并排保留统一游标、degree→radian 只转换边界输入不改数据。测试使用 Task 7 结果格式的固定解析样本。
- [ ] **Step 2:** 安装前端依赖并生成 package-lock；运行 `npm --prefix web test -- --run`，确认组件不存在或行为未实现而失败。
- [ ] **Step 3:** 实现中文实验台、几何/正弦/速度/观测编辑、实例频率、运行历史与真实结果绘图。绘图更新不调用数值模拟；窄屏折行，核心三图保留。支持叠加/并排、板/状态/实例选择。
- [ ] **Step 4:** 同命令通过；`npm --prefix web run build` 通过。与后端连通，在浏览器检查三图和几何高度显示，不用示意曲线代替未加载数据。
- [ ] **Step 5:** 提交 `feat: build editable simulation and comparison workbench`。

## Task 9：滤波参数、矩阵与 Python 模型编辑器

**Files:** Create `web/src/filters/{ParameterEditor,MatrixEditor,ModelEditor}.tsx`, `web/tests/model-editor.test.tsx`, `examples/models/custom_cv.py`, `docs/model-authoring.md`；Modify `web/src/filters/InstanceList.tsx`。

**Interfaces:**
- 编辑器通过 ExperimentStore.updateDraft 更新 FilterConfig/ModelDefinition，后台 `/api/models/validate` 返回 ValidationIssue。
- MatrixEditor 支持完整 P₀/Q/R、对角快捷输入及形状展示；Q 可切换模型强度参数或自定义 Q(dt)，不得混淆真实噪声。
- IMM 编辑子实例、μ₀、Λ；展示用户所选参考时间的 Π，不将每周期概率偷偷当作每秒转移率。
- ModelEditor 提供状态名称/单位/周期、源码、参数、真值映射和物理投影；通过 Monaco 报具体行/方程错误。

- [ ] **Step 1:** 写 UI 与后端联合样例测试：非法 P₀ 显示字段错误且不提交；UKF 参数改动保存在新 run 配置；IMM 不同状态语义拒绝；自定义二维 CV 可预测与校正，其缺失几何状态 NEES 明确只评估映射子集。
- [ ] **Step 2:** 运行 `npm --prefix web test -- --run model-editor` 和 `python -m pytest backend/tests/test_custom.py -q`，新增用例先失败。
- [ ] **Step 3:** 实现编辑器和一个可运行的 Model 样例，文档列出 Task 3 的每个接口、角度约定及映射方式；编译错误保留草稿，用户可修正后再验证。
- [ ] **Step 4:** 两条命令均通过；从界面编辑 f/h、运行后确认输出来自新模型 hash。样例使用真实数据契约，不只测试编辑框存字符串。
- [ ] **Step 5:** 提交 `feat: edit filter parameters and custom models`。

## Task 10：纯预测、NIS/NEES、总结、候选试验与导出界面

**Files:** Create `web/src/forecast/{ForecastEditor,ForecastPlot}.tsx`, `web/src/evaluation/{ConsistencyPlot,MetricsTable,ReportPanel,TuningPanel}.tsx`, `web/tests/forecast-report.test.tsx`；Modify `web/src/api/client.ts`, `web/src/app/Workbench.tsx`。

**Interfaces:**
- ForecastEditor 操作 ForecastConfig.leads_s：N 改动扩展/缩短列表，等间隔生成是一种填表方式；字段名“预测提前量（秒）”。
- ForecastPlot 选择单次 origin_time 的未来拟合，或固定 lead_s 随 origin_time 的差距；同时支持板位置、中心与参考角。
- ConsistencyPlot/ReportPanel 接收实际 EvaluatedRun；曲线 click evidence_range 更新同一 cursorTime。
- TuningPanel 调用子作业 scan/monte-carlo；候选参数差异可复制到新草稿，原 run 永不更新。

- [ ] **Step 1:** 写界面行为测试：

```typescript
it('labels a forecast by its future target time', () => {
  render(<ForecastPlot record={fixtureForecast({ origin_time: 4.8, lead_s: 0.3 })} />);
  expect(screen.getByText(/目标时刻.*5.10/)).toBeVisible();
});
```

另测无未来真值标“未评估”且不绘造零误差、纯预测 NIS 显示“无新观测”、IMM 标签“高斯近似参考”、未映射状态不显示全状态 NEES、报告缺失败实例而非宣布完整比较、扫描候选不会覆盖基线、打开评估仍保留核心三图。
- [ ] **Step 2:** 运行 `npm --prefix web test -- --run forecast-report`，期望失败。
- [ ] **Step 3:** 接入真实 forecast/evaluation/report 数据；提供置信水平、自由度、有效计数、模型概率、参数差异和原始导出入口。NIS/NEES 数据不足使用 reason 标签；不生成装饰性评分。
- [ ] **Step 4:** 同命令和构建通过；浏览器检验长时间轴、末尾预测、并排比较和规则证据跳转；至少核对一个下载的 CSV/JSON 与后端原始值一致。
- [ ] **Step 5:** 提交 `feat: visualize lookahead diagnostics and tuning reports`。

## Task 11：端到端验收、启动说明与基准

**Files:** Create `web/e2e/experiment.spec.ts`, `scripts/dev.sh`, `scripts/benchmark.py`, `examples/spin-and-translation.json`, `docs/getting-started.md`, `docs/acceptance.md`；Modify `README.md`。

**Interfaces:**
- `scripts/dev.sh` 使用项目 `.venv` 与 npm 同时启动本地后端/前端，退出时清理自己的进程；后端端口 8000、前端 5173 可通过任务专用配置覆盖。
- `python scripts/benchmark.py --config examples/baseline.json` 输出时长、实例数、校正/预测次数、数值结果 hash、耗时和峰值内存。
- 文档提供安装、启动、模型编写、实验复现和指标限制；不会声称未经测量的实时性能。

- [ ] **Step 1:** 编写一个完整 E2E：修改几何/自旋 → 创建 EKF、UKF、IMM → 改单实例频率 → 运行 → 查看三图 → 启用每次更新后 `[.1,.3,.5]` 预测 → 查看对应差距 → NIS/NEES/模型概率 → Q 候选扫描 → 复制候选 → 导出与重新打开。明确断言来源是真实 completed run，旧 run hash 不变。
- [ ] **Step 2:** 运行 `npm --prefix web run test:e2e`，确认缺少启动/全链路集成时用例失败；失败须能定位到具体环节。
- [ ] **Step 3:** 完成启动与导出复现流程，填写 acceptance 检查记录和实际基准。UI 用真实实验截图核验桌面宽屏和窄屏、长矩阵、长实例名、参数错误和部分失败。
- [ ] **Step 4:** 一次运行最终检查：`python -m pytest backend/tests -q`、`npm --prefix web test -- --run`、`npm --prefix web run build`、`npm --prefix web run test:e2e`；期望全通过。重复同配置的数值 hash 一致；纯预测开关/显示帧率变化主结果一致。
- [ ] **Step 5:** 提交 `test: verify end-to-end experiments and document local usage`。

## 交付与审阅

M1：Task 1–5，数学核心与调度/纯预测全部能独立运行。

M2：Task 6–8，真实数据可视化、指标及可复现作业可用。

M3：Task 9–11，自定义模型、参数试验、导出和全链路完成。

建议后续采用分任务实施与独立审阅：滤波、IMM 和时间调度各有解析验收，先把数值契约检查清楚再扩展界面。若用户选择由当前会话直接实施，保留相同任务与检查，最后做独立整体审阅。

文档阶段不包含产品实现。下一步审阅重点是建议默认值：本地 Web/Python 技术栈、已知板 ID 的合成观测、自旋默认角速度模式、自定义 Python 模型入口及逐项提前量配置。
