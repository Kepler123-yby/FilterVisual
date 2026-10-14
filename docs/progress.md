# 分阶段交付记录

## M1：仿真与数值核心

四装甲板固定 ID 和两组半径/高度；XY 连续平移和多正弦角度/角速度；独立随机观测源；EKF、UKF、IMM；各实例独立更新频率；每次实际校正后按提前量复制分支纯预测；真值在滤波结束后对齐评估。

独立审阅修复了 IMM 角度创新的模式顺序依赖、极小似然概率的永久下溢，以及 IMM 与外层实例的状态语义不一致。配置错误附具体字段路径。

核心验证命令：

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=backend/src .venv/bin/python -m pytest backend/tests/test_config.py backend/tests/test_geometry.py backend/tests/test_motion.py backend/tests/test_observations.py backend/tests/test_filters.py backend/tests/test_imm.py backend/tests/test_metrics.py backend/tests/test_scheduler.py backend/tests/test_forecast.py backend/tests/test_reproducibility.py -q
```

后续阶段：本地作业与可复现存储、真实数据界面、模型编辑、评估调参、端到端验收。

## M2：本地作业、评估和参数试验

本地 FastAPI 单 worker 队列，含取消/超时/重启恢复；配置和结果不可变 JSON+NPZ，文件/源码/观测哈希校验及数值有效掩码；JSON/CSV/Markdown/NPZ/ZIP 导出。NIS/NEES、共同有效时间比较、带证据的调参候选、同源观测 Q/R 扫描、独立种子 Monte Carlo 已接通真实计算。

自定义模型在子进程编译、验证和运行，包含完整四板及四维中心示例。独立审阅修复了模型方程修改后误继承旧 batch/Jacobian、不同实例/扫描候选共享可变模型、错误真值映射及投影击穿其他报告等问题。

后端全套 146 项测试通过；真实 HTTP 创建实验、读回结果和 ZIP 导出通过。默认 12 秒/三实例/1695 次校正/5085 次附带预测连续两次完成，优化后耗时 49.446/49.240 秒；数值 SHA256 与优化前一致。

下一阶段交付全部界面、浏览器验收和本地启动说明。

## M3：完整界面与端到端验收

真实数据实验台、自定义 Python / IMM 子模型编辑、完整矩阵、预测/一致性报告、扫描/Monte Carlo、导入导出、不可变历史与可复制候选全部完成。图表串行刷新，播放和共享游标不触发数值计算；自定义状态的真值来自显式映射，同轴只绘相同单位。

最终后端 **149 tests**、前端 **21 tests**、真实 Chromium **4 E2E tests** 全通过，生产构建和实际安装通过。使用说明与真实基准见 `docs/acceptance.md`；启动命令见 README。
