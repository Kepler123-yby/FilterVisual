# 本地使用

安装命令见 README。开发模式执行 `bash scripts/dev.sh`，打开 `http://127.0.0.1:5173`。生产模式先 `npm --prefix web run build`，再启动后端，直接访问 `http://127.0.0.1:8000`。

## 安装依赖失败的修复步骤

当前项目需要 Python 3.10–3.13，推荐 3.13。锁定的 NumPy 2.2.6 和 SciPy 1.15.3 不支持 Python 3.14；在 3.14 下，pip 可能尝试从源码构建并出现 `metadata-generation-failed`。末尾的 pip 升级提示不是该问题的原因。版本及安装文件见 [NumPy](https://pypi.org/project/numpy/2.2.6/) 和 [SciPy](https://pypi.org/project/scipy/1.15.3/)。

以下命令均在项目根目录执行。先检查失败环境实际使用的版本：

```bash
.venv/bin/python --version
```

如果已激活旧虚拟环境，先执行 `deactivate`。重建前备份旧 `.venv`（重复修复时也会保留之前的备份）：

```bash
if [ -d .venv ]; then
  mkdir -p .venv-backup
  mv .venv ".venv-backup/$(date +%Y%m%d-%H%M%S)"
fi
```

备份仅供保留文件；虚拟环境移动后不应直接运行或复制其中的包。随后选择下面一种方式创建新环境。

### macOS（Homebrew）

安装指定版本，使用 Homebrew 的实际路径创建环境，兼容 Apple Silicon 和 Intel Mac：

```bash
brew install python@3.13
"$(brew --prefix python@3.13)/bin/python3.13" -m venv .venv
```

参考 [Homebrew Python 3.13](https://formulae.brew.sh/formula/python@3.13)。创建后继续执行下方“安装并验证依赖”。

### Linux（Ubuntu 22.04 / 24.04）

这两个 Ubuntu 版本的默认 Python 分别为 3.10 / 3.12，均在项目支持范围内。安装对应的虚拟环境组件并确认实际命令使用的版本：

```bash
sudo apt update
sudo apt install python3 python3-venv
python3 -c 'import sys; assert (3, 10) <= sys.version_info[:2] < (3, 14), sys.version; print(sys.version)'
python3 -m venv .venv
```

如果版本检查失败，请使用下一节的 Python 3.13 方案，然后继续“安装并验证依赖”。Ubuntu 的虚拟环境说明见 [官方 Python 文档](https://documentation.ubuntu.com/ubuntu-for-developers/tutorials/python-use/)。

### Linux（其他发行版或默认 Python 为 3.14+）

使用 uv 下载独立的 Python 3.13 并创建带 pip 的环境，无需替换系统 Python。需要系统已有 `curl`；若已安装 uv，可跳过前两行：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
uv python install 3.13
uv venv --python 3.13 --seed .venv
```

参考 [uv 安装说明](https://docs.astral.sh/uv/getting-started/installation/) 和 [Python 版本管理](https://docs.astral.sh/uv/guides/install-python/)。

### 安装并验证依赖（macOS / Linux 共用）

```bash
.venv/bin/python --version
.venv/bin/python -m pip install --only-binary=:all: -r backend/requirements.lock
.venv/bin/python -m pip install --no-deps -e backend
.venv/bin/python -m pip check
.venv/bin/python -c 'import numpy, scipy; print("NumPy", numpy.__version__, "SciPy", scipy.__version__)'
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=backend/src .venv/bin/python -m pytest backend/tests -q
```

`--only-binary=:all:` 要求使用预编译包，避免意外进入本地源码编译。如果仍出现 `No matching distribution found`，请检查 Python 版本、CPU 架构以及当前软件源是否提供对应的 wheel；该报错与网络连接失败需要分别处理。

确认依赖正常后，准备 Node.js 22 LTS（至少 22.12）并启动：

```bash
npm --prefix web ci
bash scripts/dev.sh
```

## npm 安装提示和依赖审计

`added ... packages` 表示安装完成。`funding` 和 npm 新版本通知无需额外处理；修复项目依赖不需要升级全局 npm。

前端锁定文件已更新 Vite、Vitest、Playwright 和 jsdom，修复已报告的 6 项漏洞，并移除 jsdom 间接依赖的 `whatwg-encoding` 弃用提示。更新代码后，在项目根目录按锁定文件重新安装、审计并验证：

```bash
npm --prefix web ci
npm --prefix web audit
npm --prefix web test -- --run
npm --prefix web run build
```

审计结果随漏洞数据库更新而变化，出现新问题时应检查依赖链并升级到兼容的修复版本；不要直接用 `npm audit fix --force` 覆盖项目的精确版本约束。

`allow-scripts` 提示来自 npm 的安装脚本策略。项目在 `web/package.json` 中允许已检查的 `esbuild@0.28.2` 安装脚本，用于准备平台对应的构建程序；禁止可选的 `fsevents` 安装脚本，macOS 使用包内预编译文件，Linux 不需要该包。无需批准全部脚本，也无需手动编译 `fsevents`。使用支持该命令的 npm 时，可查看是否仍有待审查项：

```bash
npm --prefix web approve-scripts --allow-scripts-pending
```

脚本策略见 [npm 官方说明](https://docs.npmjs.com/cli/v11/commands/npm-approve-scripts/)。构建时若提示部分文件大于 500 kB，这是 Monaco / Plotly 体积提示；以构建退出状态判断是否成功。

## 启动脚本的 macOS / Linux 兼容性

`bash scripts/dev.sh` 兼容 macOS 自带的 Bash 3.2 和 Linux。脚本使用 `.venv` 中的 Python 标准库管理两个服务，不依赖外部 `setsid` 命令或 Bash 的 `wait -n`。

如果旧版本报 `wait: -n: invalid option` 或 `setsid: command not found`，执行 `git pull` 更新项目后重新运行 `bash scripts/dev.sh`，无需额外安装 Bash 或系统工具。Ctrl+C 会停止本次启动的两个服务及其子进程；任一服务退出时也会清理另一服务，并保留退出状态。

## 启动和端口

Python 虚拟环境提供后端运行时，前端仍由 Node.js / npm 启动。`scripts/dev.sh` 同时启动两者，不安装或注册 systemd 服务，也不设置开机自启。

默认后端端口为 8000，前端端口为 5173。端口占用时脚本会退出，不会自动换端口或停止已有服务。若原应用仍在运行，可直接打开原地址；需要另一套开发实例时，给两个服务都选择空闲端口：

```bash
FILTERVISUAL_API_PORT=8001 FILTERVISUAL_WEB_PORT=5174 bash scripts/dev.sh
```

此时访问 `http://127.0.0.1:5174`，前端会代理到 8001。避免两套后端同时使用同一数据目录；另一实例可额外指定独立的 `FILTERVISUAL_DATA_DIR`。环境变量仅对本次命令生效。

## 使用流程

平移与自旋支持负值。匀速模式下，`vx < 0` / `vy < 0` 分别向世界 −X / −Y 移动；范围内平滑变速及速度节点使用有向速度，负值表示沿当前方向角反向运动，速度区间可以为 `[-2,-0.5]` 或 `[-2,2]`，但上限不能小于下限。随机模式的方向由随机种子生成，跨过零时可以连续反向。

自旋的 A、Ω、a、C 以及初始角均可为负。角速度模式下，ω 为正表示逆时针、为负表示顺时针（从 +Z 向下看）；Ω 为负表示正弦相位反向推进，不等于整个角速度始终为负。输入单独的 `-`、小数前缀或科学计数法前缀时不会被强制改成 0，填写完整数字后才写入草稿；红色的不完整输入会阻止运行，按 Esc 可恢复最后有效值。半径、噪声、时间间隔等物理量仍保留原有范围限制。

两种自旋模式的定义不同，多个正弦项的 C 也会相加：

- **角度模式**：`theta(t) = initial_yaw + Σ[A sin(Ωt+a)+C]`。A、C 的单位为 rad，Ω 为 rad/s，a 为 rad。这里 `initial_yaw` 是附加角偏置；实际 `theta(0)` 还包括 `Σ[A sin(a)+C]`。
- **角速度模式**：`omega(t) = Σ[A sin(Ωt+a)+C]`，`theta(t) = initial_yaw + ∫₀ᵗ omega(s) ds`。A、C 的单位为 rad/s，Ω 为 rad/s，a 为 rad；此时 `initial_yaw` 就是实际 `theta(0)`。Ω=0 时也按该定义取常量极限。

1. 在运动配置修改两组半径、A 组高度、B−A 高度差、参考板、XY 速度及正弦项。正弦频率单位为 rad/s；角度和角速度模式有不同物理含义。
2. 观测配置决定模拟传感器的频率、噪声、丢帧和异常值。滤波器内 Q/R 决定模型的信任程度，分别编辑，避免把真实噪声当作自动标定结果。
3. 为 EKF、UKF、IMM 设置独立更新频率、初始状态和 P₀。复制实例后可比较不同参数；IMM 转移矩阵输入每秒转移率，周期概率为 `expm(Λ Δt)`。
4. 开启“更新后纯预测”，填写每次校正后的预测提前量，例如 `[0.1,0.3,0.5]` 秒。每个结果以 `origin_time+lead_s` 为目标时刻，与该时刻真值比较；它不改变主滤波流程。
5. 开始运行后观察进度。运动、拟合、误差三图始终保留；可叠加或并排对比，用共享时间游标检查同一时刻。
6. 评估区看实际 NIS、NEES、自由度、参考区间、有效计数及 IMM 概率。纯预测没有新观测，NIS 留空；超出场景尾部的预测没有未来真值，误差留空。
7. 报告按共同有效时刻比较误差，参数建议包含证据与多个可能原因。Q/R 倍率扫描复用同一观测源，并在基线与候选共同有效时刻的交集上比较；没有共同样本时不提供排名。复制候选到新草稿后重新运行，历史基线不变。
8. Monte Carlo 使用不同种子，在同一时刻、相同自由度与状态语义内聚合 ANIS/ANEES，区间按该分组实际有效试验数计算。为控制计算量，它评估主滤波结果，关闭附带预测；报告明确标出这一点。
9. 按用途导出 JSON/NPZ/CSV/ZIP，或保存草稿配置。配置 JSON 和运行结果 JSON 都可通过“导入配置”恢复为新草稿；不会把导出结果重新写入历史。相同代码、依赖、配置和种子可复现数值结果，不承诺不同平台下的逐位一致。

更新频率是最大观测校正频率：每次正常周期最多消费一个最新的可用帧，多余旧帧会跳过并计数。帧仍以实际观测时间更新；校正后预测至周期终点。没有新帧时只预测，不伪造校正或 NIS。仿真积分步长、观测频率、各实例频率、评估网格和播放帧率是不同概念。

首版已知板 ID，不包含相机检测、PnP 和板 ID 数据关联。NIS/NEES 的时间样本相关，单条时间曲线只作描述性一致性诊断。非线性 EKF/UKF 与 IMM 的卡方界是近似参考；IMM 尤其不能把参考区间当作严格的通过率认证。只在同一物理量、相同有效时间集合上比较误差。

自定义状态、观测、Q/R 和 f/F、h/H 的详细修改步骤及四维 / 六维示例见 [自定义模型说明](model-authoring.md)。

无需阅读代码的模型修改入口为“预测模型与方程” → “表单配置模型（无需 Python）”。从 [表单操作说明](model-form.md) 开始，无需找到或修改 `build_model`。

普通仿真限时默认 120 秒；扫描和 Monte Carlo 按实际候选/种子数量扩大总预算（扫描含基线），界面仍可取消并查看进度。默认 IMM 扫描 5 个候选可能需数分钟；批量试验不会在 120 秒时误终止整个比较。

## 观测噪声和统计指标

每板真实观测为 `[x,y,z,yaw]`，在真值上叠加零均值高斯噪声，yaw 随后归一化到 `[-pi,pi)`。默认位置标准差 0.01 m、yaw 标准差 0.02 rad，即单板真实协方差 `diag(0.0001,0.0001,0.0001,0.0004)`。真实协方差支持 4×4 单板块或按 A0…A3 排列的 16×16 矩阵；显式矩阵覆盖标准差设置。4×4 块在多板时独立重复，16×16 可表达跨板相关。

异常值按整帧抽样，以设定概率将噪声向量乘 `outlier_scale`，所以条件协方差乘该倍率的平方；它不移动真实目标。丢帧则直接缺失。不同时间独立抽取噪声，滤波器共用同一份已生成的观测。滤波器的 R 独立配置，不会自动跟随上述真实噪声或异常值率调整。

NIS 为新息 `νᵀS⁻¹ν`，自由度是该次实际观测维数；NEES 为映射状态误差 `eᵀP_subset⁻¹e`，自由度是有真值的映射子集维数。角度误差取最短角差。默认置信度 95% 的参考区间是相应自由度的双侧卡方分位数；独立种子平均值使用实际有效试验数 N，对应 `χ²(N·dof)/N`。没有新观测、没有可用真值或协方差非法时显示缺失及原因，不计作零误差。高置信度或落在区间内都不等于滤波器已正确建模；非线性、异常值、初始偏差及 IMM 混合分布都会影响卡方近似。

## 保存、取消和导出

在项目根目录按上述命令启动时，本地数据写入 `data/runs/<UUID>/`，默认被 Git 忽略。`FILTERVISUAL_DATA_DIR` 指定的是数据根目录，应用会在其下创建 `runs/`；相对路径按后端工作目录解释，建议自定义时使用绝对路径。

服务按单 worker 队列运行，排队时间不占运行限时。取消或超时会终止该作业并保留配置与具体状态；不提供未完成作业的部分结果导出。应用重启后会检查已封存文件，完整结果可恢复为完成状态，其余中断作业标为失败，需要从配置发起新运行。

“保存配置”下载当前草稿，不包含计算结果。已完成运行的导出用途如下：

| 格式 | 包含内容 |
|---|---|
| JSON | 运行清单、提交时配置及模型源码、完整结构化结果 |
| CSV | 普通仿真的状态 / 预测逐分量数值；扫描或 Monte Carlo 的对应汇总，不包含完整 P 矩阵 |
| NPZ | `results.npz` 数值数组，普通仿真包含完整状态 / P 及预测 / 新息；单独下载不含观测文件和模型源码 |
| ZIP | 完整运行目录，含配置、源码、清单、JSON、`results.npz` 和 `observations.npz` |
| Markdown | 带配置哈希的文字报告和结构化报告数据 |

JSON 缺失值使用 `null`；NPZ 使用 NaN 并提供有效掩码。分析作业保存候选 / 试验汇总，其 NPZ 内容不同于普通仿真；Monte Carlo 不保存各次完整轨迹。需要完整归档时优先使用 ZIP。
