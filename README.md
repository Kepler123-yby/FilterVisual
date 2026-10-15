# FilterVisual

用于 RoboMaster 四装甲板目标的本地滤波实验台。配置 XY 平移、多正弦自旋、两组半径和高度，比较 EKF、UKF、IMM 的拟合、更新后纯预测、NIS/NEES 及参数候选。

## 安装和启动

需要 Python 3.10–3.13（推荐 3.13）和 Node.js 22.12+（推荐 22 LTS）。当前锁定的 NumPy / SciPy 不支持 Python 3.14。所有数值计算在本机执行。

```bash
python3.13 -m venv .venv
.venv/bin/python -m pip install --only-binary=:all: -r backend/requirements.lock
.venv/bin/python -m pip install --no-deps -e backend
npm --prefix web ci
bash scripts/dev.sh
```

首次安装 Python 或遇到 SciPy `metadata-generation-failed` 时，请按 [macOS / Linux 安装修复步骤](docs/getting-started.md#安装依赖失败的修复步骤) 选择对应系统的命令，备份旧环境后重新创建 `.venv`。升级 pip 不会解决 Python 与锁定依赖的版本兼容问题。

打开 `http://127.0.0.1:5173`。启动脚本兼容 macOS 自带 Bash 和 Linux，使用项目 Python 管理服务，无需安装 `setsid` 或升级 Bash。按 Ctrl+C 或任一服务退出时，会清理本次启动的后端和前端进程。端口可设置 `FILTERVISUAL_API_PORT` / `FILTERVISUAL_WEB_PORT`。

只启动构建好的应用：

```bash
npm --prefix web run build
PYTHONPATH=backend/src .venv/bin/python -m uvicorn filtervisual.service.app:app --host 127.0.0.1 --port 8000
```

打开 `http://127.0.0.1:8000`。实验默认保存到 `data/runs/`，可用 `FILTERVISUAL_DATA_DIR` 改变目录；单作业默认限时 120 秒，可用 `FILTERVISUAL_JOB_TIMEOUT` 调整。

## 功能

- 四板固定身份 A0…A3，A0/A2 与 A1/A3 分别设置半径和高度，任选参考板。
- 连续 XY 运动和多个 `A sin(Ωt+a)+C` 项，支持角度或角速度定义。
- 独立观测频率、真实噪声、丢帧/异常值，与每个滤波器的更新频率和 Q/R 分开。
- EKF、UKF、IMM 多实例叠加或并排；完整 P₀、Q/R 和自定义 Python 模型。
- 每次实际校正后复制分支，按任意提前量纯预测，与目标时刻真值对齐比较。
- 拟合/误差/预测差距、NIS/NEES、模式概率、证据报告、Q/R 扫描和独立种子 Monte Carlo。
- 不可变历史结果、配置导入、JSON/CSV/NPZ/ZIP/Markdown 导出，包含源码及依赖哈希。

## 验证

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=backend/src .venv/bin/python -m pytest backend/tests -q
npm --prefix web test -- --run
npm --prefix web run build
# 先运行 scripts/dev.sh；首次使用 Playwright 需安装浏览器：
npm --prefix web exec -- playwright install chromium
npm --prefix web run test:e2e
.venv/bin/python scripts/benchmark.py --config examples/baseline.json --repeat 2
```

`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` 避免 ROS 系统 Python 插件影响项目测试。

详见 [使用说明](docs/getting-started.md)、[模型接口](docs/model-authoring.md)、[验收记录](docs/acceptance.md)、[设计](docs/superpowers/specs/2026-10-15-filtervisual-design.md) 和 [实施计划](docs/superpowers/plans/2026-10-15-filtervisual-implementation.md)。

首版使用已知板 ID 的合成 XYZ/yaw 观测，不包含相机检测/PnP/ROS。自定义 Python 源码在限时子进程中运行，但不是权限沙箱。NIS/NEES 的卡方界是统计参考，IMM 标为高斯混合近似；时间序列的相关样本不作为独立试验通过率。
