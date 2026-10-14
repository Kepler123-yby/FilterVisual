# 自定义 Python 模型

模型编辑器运行本机可信 Python 源码，入口为 `build_model(params, geometry)`。验证与实验在独立子进程执行，验证限时 5 秒，实验默认限时 120 秒。源码不是权限沙箱，请只运行自己信任的代码；服务默认绑定 `127.0.0.1`。

`examples/models/custom_cv.py` 是完整 11 维四装甲板模型。`examples/models/reduced_xy.py` 使用四维 `[cx,cy,vx,vy]`，只输出中心投影和四维 NEES；它假定几何已知、自旋为零，适合 `examples/custom-xy.json`。

## 必需接口

| 接口 | 返回值/约定 |
|---|---|
| `state_names`, `units` | 等长唯一名称和单位；1…32 维 |
| `angular_indices` | 需要最短角差的状态索引 |
| `f(x,dt,t0)` | `t0` 至 `t0+dt` 的状态，形状 `(n,)` |
| `h(x,context)` | 按 `context.plate_ids` 顺序，每板 `[x,y,z,yaw]`，形状 `(4k,)` |
| `Q(dt)` | `(n,n)` 半正定离散过程协方差，随真实时间间隔变化 |
| `R(frame)` | `(4k,4k)` 正定观测协方差；与真实观测噪声分别配置 |
| `state_residual(a,b)` | 状态差，角度使用最短角差 |
| `observation_residual(a,b,context)` | 观测差，每板 yaw 周期为 `2π` |
| `state_mean(points,weights)` | 状态均值，正确处理角度和 UKF 的负权重 |
| `observation_mean(points,weights,context)` | 同上，观测域 |
| `project(x,P)` | `PhysicalEstimate`；未知物理量留 `None`，无效几何设 `valid=False` |
| `truth_mapping(physical)` | `TruthMapping(indices,values,angular_indices)` 或 `None` |

`AngularModel` 提供默认周期残差和局部角度均值。`jacobian_f(x,dt,t0)`、`jacobian_h(x,context)` 可选；未提供时 EKF 使用中心有限差分。`f_batch(points,dt,t0)`、`state_residual_batch(points,mean)` 是可选优化，其结果必须与逐点调用一致。

继承内置模型并更改 `f` 或 `h` 时，加载器会禁用更深层继承的相应 batch/Jacobian，防止 UKF 或 EKF 意外沿用旧方程。自己实现的 Jacobian 仍需随方程一起修改。自定义模型按纯预测子步推进，不继承内置模型的快速传播声明。

## 坐标与状态

所有时间为秒，位置为米，内部角度为弧度；参考角是中心指向所选参考板的方向，从世界 `+X` 逆时针为正。A0/A2 始终属于 A 组，A1/A3 始终属于 B 组，即使改变参考板也不改变板 ID。

内置状态为 `[cx,cy,zA,vx,vy,vz,theta,omega,rA,rB,dh]`。`P0` 必须与状态维数相符。IMM 的所有模式和外层实例必须使用相同状态名称、单位及周期索引；可使用不同动力学、Q/R 或 EKF/UKF 引擎。

真值映射仅供实验完成后评估，滤波和预测函数不接收真值。NEES 只评估映射的状态子集并显示对应自由度；中心投影不完整时，四板误差为未评估，不填零。纯预测从校正后的副本开始，所有观测只用于主滤波流程。

## 复现

接口应由传入的 `x`、`dt`、`t0`、观测上下文和参数确定输出；不要使用隐式可变时钟或让缓存计数影响方程。观测帧和数值数组只读；模型必须可被 `deepcopy` 复制。每实例、每候选及每纯预测分支分别拥有模型，预测函数不会改变主实例的缓存。API 创建实验时会在 worker 内再次校验自定义模型，包括 IMM 子模式，点击编辑器的“验证”不是运行前的必要条件。

每次运行保存配置、源码、种子、依赖版本、观测、原始状态和报告。修改源码或参数后必须新建运行，历史结果保持只读。用 JSON 导出检查具体 `config.models[].source`，用 NPZ 检查矩阵和数值序列；不要用报告文字代替原始数据。
