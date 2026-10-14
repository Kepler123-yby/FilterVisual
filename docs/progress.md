# 分阶段交付记录

## M1：仿真与数值核心

四装甲板固定 ID 和两组半径/高度；XY 连续平移和多正弦角度/角速度；独立随机观测源；EKF、UKF、IMM；各实例独立更新频率；每次实际校正后按提前量复制分支纯预测；真值在滤波结束后对齐评估。

独立审阅修复了 IMM 角度创新的模式顺序依赖、极小似然概率的永久下溢，以及 IMM 与外层实例的状态语义不一致。配置错误附具体字段路径。

核心验证命令：

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=backend/src .venv/bin/python -m pytest backend/tests/test_config.py backend/tests/test_geometry.py backend/tests/test_motion.py backend/tests/test_observations.py backend/tests/test_filters.py backend/tests/test_imm.py backend/tests/test_metrics.py backend/tests/test_scheduler.py backend/tests/test_forecast.py backend/tests/test_reproducibility.py -q
```

后续阶段：本地作业与可复现存储、真实数据界面、模型编辑、评估调参、端到端验收。
