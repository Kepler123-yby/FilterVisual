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

## 使用流程

1. 在运动配置修改两组半径、A 组高度、B−A 高度差、参考板、XY 速度及正弦项。正弦频率单位为 rad/s；角度和角速度模式有不同物理含义。
2. 观测配置决定模拟传感器的频率、噪声、丢帧和异常值。滤波器内 Q/R 决定模型的信任程度，分别编辑，避免把真实噪声当作自动标定结果。
3. 为 EKF、UKF、IMM 设置独立更新频率、初始状态和 P₀。复制实例后可比较不同参数；IMM 转移矩阵输入每秒转移率，周期概率为 `expm(Λ Δt)`。
4. 开启“更新后纯预测”，填写每次校正后的预测提前量，例如 `[0.1,0.3,0.5]` 秒。每个结果以 `origin_time+lead_s` 为目标时刻，与该时刻真值比较；它不改变主滤波流程。
5. 开始运行后观察进度。运动、拟合、误差三图始终保留；可叠加或并排对比，用共享时间游标检查同一时刻。
6. 评估区看实际 NIS、NEES、自由度、参考区间、有效计数及 IMM 概率。纯预测没有新观测，NIS 留空；超出场景尾部的预测没有未来真值，误差留空。
7. 报告按共同有效时刻比较误差，参数建议包含证据与多个可能原因。Q/R 倍率扫描复用同一观测源；复制候选到新草稿后重新运行，历史基线不变。
8. Monte Carlo 使用不同种子在同一时刻聚合 ANIS/ANEES。为控制计算量，它评估主滤波结果，关闭附带预测；报告明确标出这一点。
9. 导出完整 JSON/NPZ/CSV/ZIP，或保存草稿配置。导入 JSON 后可复现实验；同一版本、配置和种子产生相同数值序列。

更新频率是最大观测校正频率：每次正常周期最多消费一个最新的可用帧，多余旧帧会跳过并计数。帧仍以实际观测时间更新；校正后预测至周期终点。没有新帧时只预测，不伪造校正或 NIS。仿真积分步长、观测频率、各实例频率、评估网格和播放帧率是不同概念。

首版已知板 ID，不包含相机检测、PnP 和板 ID 数据关联。NIS/NEES 的时间样本相关，单条时间曲线只作描述性一致性诊断。非线性 EKF/UKF 与 IMM 的卡方界是近似参考；IMM 尤其不能把参考区间当作严格的通过率认证。只在同一物理量、相同有效时间集合上比较误差。

自定义状态、观测、Q/R 和 f/F、h/H 的详细修改步骤及四维 / 六维示例见 [自定义模型说明](model-authoring.md)。本地数据默认写入项目 `data/` 并被 Git 忽略；新运行使用独立 UUID，取消或超时会保留具体状态。

普通仿真限时默认 120 秒；扫描和 Monte Carlo 按实际候选/种子数量扩大总预算（扫描含基线），界面仍可取消并查看进度。默认 IMM 扫描 5 个候选可能需数分钟；批量试验不会在 120 秒时误终止整个比较。
