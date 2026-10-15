# 自定义状态、观测与滤波方程

本文说明如何修改状态向量、实际观测、Q/R、状态转移 f/F 和观测映射 h/H。先用 [四维中心 CV 配置](../examples/custom-xy.json) 跑通，再参考 [六维偏置模型](../examples/models/custom_xy_bias.py) 增加状态。

保留全部四板状态时，可从 [11 维自定义模板](../examples/models/custom_cv.py) 开始；它继承的完整 f/F/h/H/Q/R 实现在 [rm_cv.py](../backend/src/filtervisual/models/rm_cv.py)。

时间用秒、位置用米、内部角度用弧度。入口是 `build_model(params, geometry)`；`params` 来自“模型参数（JSON）”，`geometry` 来自场景。源码在本机可信 Python 子进程中执行，不是权限沙箱；验证限时 5 秒，普通实验默认限时 120 秒。

## 1. 修改入口与操作顺序

| 要修改的内容 | 界面入口 / Python 方法 | 导出配置中的字段 |
|---|---|---|
| 状态名称、顺序、维数、单位 | “预测模型与 Python 方程” → “自定义 Python 模型”；`state_names`、`units`、`angular_indices` | `models[].source` |
| 初始状态、初始不确定性 | “初始状态 x₀ / P₀” | `instances[].x0`、`instances[].p0` |
| 状态如何随时间变化 | `f(x, dt, t0)`、`jacobian_f(x, dt, t0)` | `models[].source` |
| 状态如何预测观测 | `h(x, context)`、`jacobian_h(x, context)` | `models[].source` |
| 自定义模型的过程、观测噪声 | `Q(dt)`、`R(frame)`；参数填“模型参数（JSON）” | `models[].params` |
| 自定义模型的噪声整体倍率 | “噪声假设 Q / R”中的 Q 倍率、R 倍率 | `instances[].q_scale`、`instances[].r_scale` |
| 内置模型的噪声 | 平移 / 自旋 / 几何 Q 强度、滤波器 R | `models[].params` 中的 `q_translation`、`q_rotation`、`q_geometry`、`observation_covariance` 等 |
| 真实观测噪声、板选择、频率 | 场景的观测设置 | `observation.*` |
| 图表物理量和可评估真值 | `project(x, P)`、`truth_mapping(physical)` | `models[].source` |

导出配置使用小写 `p0`，不要把界面内部的 `P0` 写进导出 JSON。实例通过 `model_id` 引用 `models[].id`；`models[].source` 存放完整源码文本，不是文件路径。

建议按以下顺序操作：

1. 复制一个 EKF 实例，展开“预测模型与 Python 方程”，切换为“自定义 Python 模型”。自动模板是 11 维模型。
2. 把完整示例 Python 文件粘贴到编辑器，填写对应“模型参数（JSON）”。修改仓库 `.py` 文件不会自动更新已保存草稿的源码。
3. 按源码顺序填写 x₀，把 P₀ 改成相同维数的完整矩阵。修改 x₀ 长度后，仍需检查 P₀ 每一行的长度和数值。
4. Q / R 倍率先设为 1，确认场景满足模型假设，再点击“验证方程与维数”。
5. 开始新运行，检查实例完成状态、轨迹、状态名称和 NEES 自由度；需要比较 UKF 时再复制实例并切换算法。

“验证通过”表示示例输入下的接口、形状和协方差检查通过，**不代表 Jacobian 数值、物理假设或可观测性已证明正确**。运行时也会再次验证源码。

## 2. x、z、f/F、h/H、Q/R 的关系

设状态维数为 n，当前帧包含 k 块装甲板，观测维数为 m=4k：

```text
x⁻ = f(x⁺, Δt, t0)                 预测下一时刻状态
F  = ∂f/∂x                         离散状态转移 Jacobian
P⁻ = F P⁺ Fᵀ + q_scale · Q(Δt)     EKF 预测协方差

ẑ = h(x⁻, context)                 预测传感器会测到什么
H  = ∂h/∂x                         观测 Jacobian
ν  = observation_residual(z, ẑ)    新息，yaw 使用最短角差
S  = H P⁻ Hᵀ + r_scale · R(frame)  EKF 新息协方差
```

小写 f/h 返回向量，大写 F/H 返回导数矩阵。线性模型可写 `f(x)=F@x`；四板几何包含 sin/cos，通常应写非线性 h，不能用 `H@x` 代替它。t0 是本步开始时刻，dt 是本步真实间隔，可能为零。

| 对象 / 方法 | 返回形状 | 约定 |
|---|---|---|
| `state_names`、`units` | 长度 n | 名称唯一，单位允许重复；1…32 维 |
| `x0`、`f(...)` | `(n,)` | 有限一维向量，不是 `(n,1)` 列矩阵 |
| `p0`、`Q(dt)`、`jacobian_f(...)` | `(n,n)` | P₀ 正定，Q 半正定，F 不要求对称 |
| `frame.values`、`h(...)` | `(m,)` | 按当前板顺序拼接 `[x,y,z,yaw]` |
| `R(frame)` | `(m,m)` | 对称正定协方差 |
| `jacobian_h(...)` | `(m,n)` | 行对应观测顺序，列对应状态顺序 |

EKF 优先调用 `jacobian_f`、`jacobian_h`；没有可调用方法时使用中心有限差分。UKF 用 f/h 传播 sigma 点，不使用 F/H。IMM 每个子模式按其 EKF / UKF 引擎执行。

## 3. 修改状态向量时的联动项

内置 11 维顺序如下，索引从 0 开始：

| 索引 | 状态 | 单位 | 含义 |
|---|---|---|---|
| 0、1 | `cx,cy` | m | 中心 XY |
| 2 | `zA` | m | A0/A2 板高 |
| 3、4、5 | `vx,vy,vz` | m/s | 中心 XY 速度、板高变化速度 |
| 6 | `theta` | rad | 中心指向参考板的角度 |
| 7 | `omega` | rad/s | 角速度 |
| 8、9 | `rA,rB` | m | A0/A2、A1/A3 两组半径 |
| 10 | `dh` | m | B 组板高减 A 组板高 |

参考角从世界 +X 逆时针为正；修改参考板不会改变 A0/A2 属于 A 组、A1/A3 属于 B 组的约定。

内置匀速 / 恒定角速度的 f 只推进位置和参考角：

```python
y = x.copy()
y[:3] += x[3:6] * dt
y[6] += x[7] * dt
# F 必须对上面的离散 f 求导，不是连续时间系统的 A 矩阵。
F = np.eye(11)
F[0, 3] = F[1, 4] = F[2, 5] = F[6, 7] = dt
```

例如改为新的速度方程，就要重新计算其对应 F 行；仅在 F 中改变某个数，不会改变 f 返回的预测状态。

例如改为 `[cx,cy,vx,vy]`，需要一起修改：

1. 元数据改为四个状态，单位为 `("m","m","m/s","m/s")`，`angular_indices=()`。只改名称不会自动改变数组索引。
2. f 返回四维，F/Q 改为 4×4；h 仍每板输出四项，因此单板 H 为 4×4，全板 H 为 16×4。
3. x₀ 改为四个数，P₀ 改为 4×4，不能继续使用原来的 11×11 矩阵。
4. h 原来从状态读取的高度、半径和角度改为已知参数，明确不再支持哪些运动。
5. `project` 按新索引提取物理量，未知字段留 `None`；`truth_mapping` 同步修改索引。

新增角度状态时，把它的**状态索引**加入 `angular_indices`，使用 Python 整数。角速度不是周期变量，不应加入。继承 `AngularModel` 可获得周期残差和适用于 UKF 负权重的局部角度均值。

P₀ 对角线填方差。例如中心标准差 0.2 m、速度标准差 1 m/s，对应 `diag(0.04,0.04,1,1)`；非对角项表示先验相关性，整个矩阵仍须对称正定。x₀ 不读取隐藏真值。

IMM 外层实例和各模式的状态名称、顺序、单位和角度索引必须相同。不能直接混合四维与六维模型；不同动力学的模式也应统一状态语义。

## 4. 实际观测 z 与预测观测 h

实际观测 z 是 `ObservationFrame.values`；h 生成预测值 ẑ。修改 h 不会改变模拟器已生成的 z，也不会自动向实际观测增加偏置。

当前应用固定使用已知板 ID 的世界坐标观测：

```text
plate_ids = (2,)
z = [A2.x,A2.y,A2.z,A2.yaw]                            # 4 维

plate_ids = (0,1,2,3)
z = [A0.x,A0.y,A0.z,A0.yaw,...,A3.x,A3.y,A3.z,A3.yaw]  # 16 维
```

h 必须按 `context.plate_ids` 的顺序拼接，不能固定返回 A0 或自行排序。板 ID 是物理身份，不是数组里的序号；`(2,)` 只返回四项。固定板、最近可见板模式生成单板帧，全板模式生成四板帧；丢失或不可见帧直接缺失，不使用零向量代替。

界面可修改板选择、频率、真实噪声、丢帧率和异常值率。模型校验会探测 `(0,)`、`(1,)`、`(0,1,2,3)`，因此即便实验只选单板，也要支持这些上下文。

若要改成像素 `[u,v]`、距离 / 方位角、直接中心位置等观测，需同步扩展 [观测生成器](../backend/src/filtervisual/scene/observations.py) 或输入适配器、[观测类型](../backend/src/filtervisual/core/types.py) 的角度索引、[模型校验](../backend/src/filtervisual/models/custom.py)、h/H/R 和相关配置 / 显示。**当前版本不能只改编辑器里的 h/R 就切换到任意维数的观测。**

### 内置四板 h/H 的具体关系

对 11 维状态，当前板编号 j，`b=j%2`，参考板编号 ref：

```text
φ = theta + (j-ref)·π/2
r = rA（偶数板）或 rB（奇数板）
h_j(x) = [cx+r·cosφ, cy+r·sinφ, zA+b·dh, φ]
```

单板 H 是 4×11，所有非零项如下，其余填零：

| 行（观测分量） | 列（状态）及导数 |
|---|---|
| 0：板 x | `cx:1`，`theta:-r·sinφ`，对应半径 `rA/rB:cosφ` |
| 1：板 y | `cy:1`，`theta:r·cosφ`，对应半径 `rA/rB:sinφ` |
| 2：板 z | `zA:1`，`dh:b` |
| 3：板 yaw | `theta:1` |

多板 H 按板顺序在行方向堆叠。改变几何、角度定义或状态顺序后要重新推导这些列。这里 yaw 是板的径向方向，不能未经转换就换成相机坐标系角度。

## 5. Q：按实际时间间隔构造过程协方差

Q 描述模型未解释的状态演化不确定性，不会自动改变真实目标运动。`Q(dt)` 返回**该时间间隔的离散协方差**；dt 随观测时间、更新频率和预测子步变化，不能写死为 `1/50`。

对一维 `[位置,速度]`，连续白加速度谱密度为 q 时：

```text
Q_pair(dt) = q · [[dt³/3, dt²/2],
                  [dt²/2, dt]]
```

q 的单位为 m²/s³，不是单次位置标准差，也不需要再次平方。`q=0.2, dt=0.1 s` 时该块为：

```text
[[0.0000666667, 0.001],
 [0.001,        0.02 ]]
```

四维顺序 `[cx,cy,vx,vy]` 的 X 轴块填入 `[0,2]`，Y 轴块填入 `[1,3]`。直接把两个块放在对角线上，对应的是另一个状态顺序 `[cx,vx,cy,vy]`。

这个公式与“每步内加速度恒定、各步独立，方差为 σa²”的模型不同；后者使用 `σa²·[[dt⁴/4,dt³/2],[dt³/2,dt²]]`。应根据噪声假设选择公式及参数单位。

内置模型还有 `[theta,omega]` 的白角加速度块，以及几何随机游走 `q_geometry·dt`。自定义 Q 必须有限、对称、半正定，处理 dt=0；常见连续时间模型在零时间间隔返回零矩阵。

## 6. R：与真实观测噪声分开设置

| 设置 | 含义 | 是否改变新运行的观测 |
|---|---|---|
| `observation.std_xyz/std_yaw/covariance` | 模拟传感器实际加入的噪声 | 是 |
| `R(frame)` / 模型参数 | 滤波器假设的观测不确定性 | 否 |
| `r_scale` | R 整体乘以该系数 | 否 |
| `Q(dt)` / `q_scale` | 预测过程不确定性 | 否 |
| `p0` | 初始状态的先验不确定性 | 否 |

单板各轴独立，位置标准差 0.01 m、yaw 标准差 0.02 rad：

```python
R_one = np.diag([0.01**2, 0.01**2, 0.01**2, 0.02**2])
# 对角线为 [0.0001, 0.0001, 0.0001, 0.0004]
```

R 根据当前帧返回 m×m；不同板独立时用 `np.kron(np.eye(k), R_one)`。全板应返回 16×16，不能一直返回 4×4。

若 x/y 噪声相关系数 ρ=0.6，两个轴标准差均为 0.01 m，则：

```python
R_one = np.array([
    [0.0001, 0.00006, 0,      0],
    [0.00006,0.0001,  0,      0],
    [0,      0,       0.0001, 0],
    [0,      0,       0,      0.0004],
])
```

非对角元素是 `ρ·σx·σy`，不能直接填 0.6；要成对填写并保持正定。若希望真实观测也有相同相关性，还需在观测设置中填写该协方差。显式 `observation.covariance` 会覆盖由标准差构造的默认噪声矩阵。真实噪声协方差可半正定，滤波器 R 必须正定。

内置 `observation_covariance` 参数支持 4×4 单板块或 16×16 全板矩阵。后者按 A0、A1、A2、A3 的 `[x,y,z,yaw]` 固定排列，单板时按 ID 提取子矩阵。自定义 R 需要自己实现此逻辑。

倍率作用于**协方差**：`r_scale=4` 表示标准差乘 2，而非乘 4；Q 同理。IMM 有效倍率是“实例倍率 × 模式倍率”。要求 `q_scale≥0`、`r_scale>0`，不建议在源码和界面无意重复放大。

## 7. 示例一：从 11 维缩减为四维中心 CV

完整源码：[reduced_xy.py](../examples/models/reduced_xy.py)。直接在界面导入 [custom-xy.json](../examples/custom-xy.json)，其中已包含源码、四维初值、P₀ 和无自旋场景。

假设板高、半径和参考角已知，目标只做 XY 平移。模型不会估计高度、自旋或半径，不适合直接用于有旋转的场景。

```text
x = [cx, cy, vx, vy]
f(x,dt) = [cx+vx·dt, cy+vy·dt, vx, vy]

F = [[1,0,dt,0],
     [0,1,0,dt],
     [0,0,1,0],
     [0,0,0,1]]
```

下面是类中可替换的同名方法，完整可运行文件见上面的源码链接：

```python
def f(self, x, dt, t0):
    y = x.copy()
    y[:2] += x[2:4] * dt
    return y

def jacobian_f(self, x, dt, t0):
    F = np.eye(4)
    F[0, 2] = F[1, 3] = dt
    return F

def Q(self, dt):
    Q = np.zeros((4, 4))
    block = self.q * np.array([[dt**3 / 3, dt**2 / 2],
                              [dt**2 / 2, dt]])
    Q[np.ix_([0, 2], [0, 2])] = block
    Q[np.ix_([1, 3], [1, 3])] = block
    return Q
```

h 为中心加上已知板偏移。由于角度和几何不在状态中，单板 H 为：

```text
H_one = [[1,0,0,0],    # 板 x 对 cx 求导为 1
         [0,1,0,0],    # 板 y 对 cy 求导为 1
         [0,0,0,0],    # 固定板高，不随状态改变
         [0,0,0,0]]    # 固定 yaw，不随状态改变
```

零行表示该观测不直接校正这些状态，但仍参与新息和 NIS，不能从 h/R 删除。速度可通过多时刻位置和互协方差间接校正。固定 yaw / 高度假设不符时可能持续产生大新息。

“模型参数（JSON）”可填写：

```json
{"q": 0.2, "position_std": 0.01, "yaw_std": 0.02, "reference_yaw": 0.0}
```

参数由 `build_model` 原样传给示例构造函数。这个四维模型使用 `q`，不是内置模型的 `q_translation`。匹配的初值 / P₀：

```json
{
  "x0": [0, 0, 0.5, 0],
  "p0": [[0.04,0,0,0],[0,0.04,0,0],[0,0,1,0],[0,0,0,1]],
  "q_scale": 1,
  "r_scale": 1
}
```

这是导出配置的实例字段片段。界面中将 x0 数组、p0 矩阵分别填入对应输入框。

尝试将 q 从 0.2 改为 2.0，只改变运动不确定性；将 `position_std` 从 0.01 改为 0.03，会把 R 的 XYZ 方差增至 9 倍，yaw 方差不变。每次只改一项并新建运行，比较误差、NIS/NEES 和纯预测；增大噪声不保证误差降低。

该示例只提供中心和速度投影，装甲板投影留空；NEES 使用四维 `[cx,cy,vx,vy]`，四板误差不评估。

## 8. 示例二：增加测量偏置状态，联动修改 h/H/Q

完整源码：[custom_xy_bias.py](../examples/models/custom_xy_bias.py)。可直接导入的完整配置：[custom-xy-bias.json](../examples/custom-xy-bias.json)。

在四维状态后增加 `bx,by`，表示各板 x/y 测量通道共用的加性偏置，单位 m；它们不是目标中心真实位移：

```text
x = [cx, cy, vx, vy, bx, by]
f(x,dt) = [cx+vx·dt, cy+vy·dt, vx, vy, bx, by]

F = [[1,0,dt,0,0,0],
     [0,1,0,dt,0,0],
     [0,0,1,0,0,0],
     [0,0,0,1,0,0],
     [0,0,0,0,1,0],
     [0,0,0,0,0,1]]

h_j(x) = [cx+r·cosφ+bx, cy+r·sinφ+by, 已知板高, 已知φ]

H_one = [[1,0,0,0,1,0],
         [0,1,0,0,0,1],
         [0,0,0,0,0,0],
         [0,0,0,0,0,0]]
```

| 修改项 | 四维示例 | 六维偏置示例 |
|---|---|---|
| 元数据 / x₀ | 长度 4 | 长度 6，末尾增加 `bx,by` |
| F / Q / P₀ | 4×4 | 6×6 |
| 单板 h / R | 4 维 / 4×4 | 仍为 4 维 / 4×4 |
| 单板 H | 4×4 | 4×6，增加偏置列 |
| Q | 两个位置 / 速度块 | 保留它们，增加 `Q[4,4]=Q[5,5]=q_bias·dt` |
| 物理投影 | `center_xy=x[:2]` | 仍为 `x[:2]`，不要把偏置加到中心 |
| 真值映射 | 四维 | 仅映射前四维，不伪造偏置真值 |

可直接粘贴的模型参数：

```json
{
  "q_accel": 0.2,
  "q_bias": 0.000001,
  "position_std": 0.01,
  "yaw_std": 0.02,
  "xy_correlation": 0.6,
  "reference_yaw": 0.0
}
```

`q_bias` 是偏置随机游走强度，单位 m²/s；`xy_correlation` 是 R 的单板 x/y 相关系数，满足 `-1<ρ<1`。不同板的白噪声在 R 中独立，共同偏置的不确定性由 P 表达。

配套 x₀ 和 P₀：

```json
{
  "x0": [0, 0, 0.5, 0, 0, 0],
  "p0": [
    [0.04,0,0,0,0,0],
    [0,0.04,0,0,0,0],
    [0,0,1,0,0,0],
    [0,0,0,1,0,0],
    [0,0,0,0,0.0001,0],
    [0,0,0,0,0,0.0001]
  ]
}
```

这演示了增维接口，但不证明偏置能够独立辨识。观测只约束 `cx+bx` 和 `cy+by`；cx 增加 0.1、bx 减少 0.1，预测观测不变。先验可以约束估计分配，识别真实偏置仍需要独立中心约束、额外传感器或标定数据。

配套场景没有固定传感器偏置，偏置初值为零、先验方差较小；它把真实 x/y 高斯噪声设置成与 R 一致的相关噪声。不要把修改 bx 初值误认为给模拟器注入偏置。NEES 仍只有 4 个自由度。

### 在文件中改代码后，怎样重新导入网页

如果习惯在本地编辑 `.py`，修改 `examples/models/custom_xy_bias.py` 后，可用下面的命令把最新源码放进一份新配置；同时演示把 `q_accel` 改为 0.4。输出文件再通过网页“导入配置”打开，无需手动编辑 JSON 中转义后的源码字符串：

```bash
.venv/bin/python - <<'PY'
import json
from pathlib import Path

config = json.loads(Path("examples/custom-xy-bias.json").read_text())
config["models"][0]["source"] = Path("examples/models/custom_xy_bias.py").read_text()
config["models"][0]["params"]["q_accel"] = 0.4
config["name"] = "六维模型修改试验"
Path("examples/custom-xy-bias-edited.json").write_text(
    json.dumps(config, ensure_ascii=False, indent=2) + "\n")
PY
```

此命令假定仍使用同一套六维状态及参数接口。若改变了维数或顺序，还要按前文同步修改配置中的每个实例 x₀ / P₀；若改了参数名，也要更新 `models[].params`。

## 9. 验证源码、Jacobian 和完整运行

在项目根目录检查两个示例的契约、数值导数和短实验：

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest backend/tests/test_custom_xy.py backend/tests/test_model_examples.py -q
```

也可以在项目 `.venv` 中运行下面的完整检查片段（后端需已按 README 安装）：

```python
from pathlib import Path
import numpy as np
from filtervisual.config.schema import GeometryConfig
from filtervisual.core.types import ObservationContext
from filtervisual.models.custom import load_model, check_contract
from filtervisual.models.protocol import numerical_jacobian

geometry = GeometryConfig()
source = Path("examples/models/custom_xy_bias.py").read_text()
model = load_model(source, {"xy_correlation": 0.6}, geometry)
x = np.array([0., 0., 0.5, 0., 0., 0.])
P0 = np.diag([0.04, 0.04, 1., 1., 0.0001, 0.0001])
print(check_contract(model, geometry, x, P0))

ctx = ObservationContext(time_s=0., plate_ids=(1,), angular_indices=(3,))
dt, t0 = 0.02, 0.
F_numeric = numerical_jacobian(
    lambda state: model.f(state, dt, t0), x, model.state_residual)
H_numeric = numerical_jacobian(
    lambda state: model.h(state, ctx), x,
    lambda a, b: model.observation_residual(a, b, ctx))
np.testing.assert_allclose(model.jacobian_f(x, dt, t0), F_numeric, atol=1e-7)
np.testing.assert_allclose(model.jacobian_h(x, ctx), H_numeric, atol=1e-7)
```

验证自己的模型时，替换源码、参数、x₀、角度索引和 P₀，覆盖多个状态、dt 和板 ID；单点数值检查不能证明任意非线性方程的导数都正确。

继承内置模型后修改 f/h，加载器会禁用更深层继承的对应 batch / Jacobian，避免沿用旧方程。自己在同一子类编写的导数和 `f_batch` 不会自动修正，仍要与新方程一致。调试时可先省略解析导数，让 EKF 使用有限差分。

注意：`RoboMasterCVModel.project()` 自身会调用 `jacobian_h` 计算板位置协方差。因此继承它并修改 h 时，应同时实现正确的 `jacobian_h`，或自行重写 project；仅依靠 EKF 的有限差分回退并不能修复继承的投影函数。更改状态布局时，也不能继续沿用按 11 维固定索引实现的 project / truth_mapping。

## 10. 其余必需接口与复现约定

| 接口 | 约定 |
|---|---|
| `state_residual(a,b)` | 状态差，角度使用最短角差 |
| `observation_residual(a,b,context)` | 观测差，每板 yaw 周期为 2π |
| `state_mean(points,weights)` | 状态均值，正确处理角度和 UKF 负权重 |
| `observation_mean(points,weights,context)` | 观测域均值 |
| `project(x,P)` | 返回 `PhysicalEstimate`；未知字段留 `None`，无效几何设 `valid=False` |
| `truth_mapping(physical)` | 返回 `TruthMapping(indices,values,angular_indices)` 或 `None` |

`AngularModel` 提供默认残差和均值。`f_batch(points,dt,t0)`、`state_residual_batch(points,mean)` 是可选优化，结果应与逐点调用一致。自定义模型按纯预测子步推进，不沿用内置快速传播声明。

`truth_mapping.indices` 索引原始状态，`truth_mapping.angular_indices` 索引**映射后的子集**。例如只评估原状态索引 `(6,7)` 的 `[theta,omega]`，应返回 `indices=(6,7)`、`angular_indices=(0,)`，不是 `(6,)`。NEES 使用该子集的协方差，显示对应自由度；没有真值的状态应排除。

真值映射只用于实验完成后评估，f/h/Q/R 不接收隐藏真值。project 决定哪些物理误差可计算；未提供装甲板投影时，四板误差标为未评估，不填零。

函数输出应由传入状态、dt、t0、上下文和参数决定。不要原地修改输入数组、只读观测帧，或用隐式时钟 / 缓存计数改变方程。模型必须可被 `deepcopy` 复制；实例、候选和纯预测分支各自拥有模型。纯预测从校正后的副本开始，不再消费未来观测。

修改源码或参数后应新建运行，历史结果保持只读。每次运行保存配置、源码、种子、依赖版本、观测和原始状态；JSON 可检查 `models[].source/params`、`instances[].x0/p0`，NPZ 可检查数值序列。

## 11. 常见修改错误

| 现象 / 错误 | 优先检查 |
|---|---|
| x₀ / P₀ 维数不匹配 | 元数据、x₀、P₀ 是否同步修改 |
| 单板可运行，全板失败 | h/R/H 是否随当前板数扩展；是否按板 ID 排列 |
| EKF 异常、UKF 正常 | F/H 是否是旧状态顺序或旧方程；与数值导数比较 |
| 协方差不对称 / 非正定 | 对角线是否填方差，相关项是否成对且合理 |
| 频率变化后预测异常 | Q 是否按实际 dt 离散化 |
| 改真实噪声后滤波器假设没变 | 真实观测和 R 独立，需要分别配置 |
| 只改 h 后持续大残差 | 实际观测与新 h 的定义、坐标系和单位是否一致 |
| NEES 自由度少于状态维数 | truth_mapping 是否只映射有真值的状态 |
| 修改 `.py` 文件但草稿没变 | 草稿保存源码文本，需要重新粘贴或重新导入配置 |
