"""Independent seeded trial averages at each exact diagnostic time and dimension."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from filtervisual.config.schema import ExperimentConfig
from filtervisual.core.types import RunCancelled, RunProgress
from filtervisual.evaluation.metrics import chi_square_bounds
from filtervisual.evaluation.report import evaluate_run, json_safe


def aggregate_trials(trials: Sequence[dict], confidence: float = .95) -> list[dict]:
    groups = {}
    for trial_index, payload in enumerate(trials):
        for instance in payload["instances"]:
            for statistic, rows, field in (("nees", instance["samples"], "nees"),
                                           ("nis", instance["updates"], "nis")):
                for row in rows:
                    score = row[field]
                    if score["value"] is None:
                        continue
                    names = tuple(score.get("state_names", []))
                    key = (instance["id"], round(row["t"], 12), statistic, score["dof"], names, score["assumption"])
                    groups.setdefault(key, {})[trial_index] = score["value"]
    output = []
    for (instance_id, t, statistic, dof, names, assumption), trials_at_time in sorted(groups.items()):
        count = len(trials_at_time)
        values = list(trials_at_time.values())
        bounds = chi_square_bounds(dof, confidence, count)
        output.append(dict(
            instance_id=instance_id, t=t, statistic="a" + statistic, dof=dof,
            count=count, trials=len(trials), mean=float(np.mean(values)), bounds=list(bounds),
            state_names=list(names), assumption=assumption,
            interpretation="independent_seed_trials_at_same_time_and_state_dimension",
            label="独立试验均值的近似参考" if assumption != "linear_gaussian_reference"
                  else "独立试验均值卡方参考",
        ))
    return output


def run_monte_carlo(
    config: ExperimentConfig, seeds: Sequence[int], cancel=lambda: False, emit=lambda _: None,
) -> dict:
    seeds = list(seeds)
    if not seeds or len(set(seeds)) != len(seeds) or any(seed < 0 for seed in seeds):
        raise ValueError("Monte Carlo requires distinct nonnegative seeds for independent trials")
    from filtervisual.simulation.runner import run_experiment
    trials, failures = [], []
    for index, seed in enumerate(seeds):
        if cancel():
            raise RunCancelled("Monte Carlo cancelled")
        trial = config.model_copy(deep=True)
        trial.seed = seed
        # Side forecasts do not affect the main filter. Main consistency trials
        # omit those branches rather than paying N lookahead costs per update.
        trial.forecast.enabled = False
        result = run_experiment(trial, cancel=cancel, emit=lambda _: None)
        evaluated = evaluate_run(result)
        trials.append(evaluated.payload)
        for instance in evaluated.payload["instances"]:
            if instance["status"] == "failed":
                failures.append(dict(seed=seed, instance_id=instance["id"], error=instance["error"]))
        emit(RunProgress(phase="monte_carlo", completed_instances=index + 1,
                         total_instances=len(seeds), completed_events=index + 1, total_events=len(seeds)))
    groups = aggregate_trials(trials, config.evaluation.confidence)
    summary = [
        f"完成 {len(seeds)} 个独立随机种子试验，在同一时刻、同一状态集合和自由度内计算 ANIS/ANEES。",
        "参考区间使用每个分组实际有效试验数；不把连续时刻当作独立样本。",
    ]
    if failures:
        summary.append(f"有 {len(failures)} 个实例试验失败，均值只使用对应分组的有效试验。")
    if any(group["assumption"] == "gaussian_mixture_approximation" for group in groups):
        summary.append("IMM 结果使用高斯混合近似参考，不能宣称通过严格普通卡方检验。")
    return json_safe(dict(
        type="monte_carlo", config=config, seeds=seeds, trials=len(seeds), groups=groups,
        failures=failures, summary=summary, report=dict(summary=summary, groups=groups, failures=failures),
        notes=["主滤波一致性试验不运行附带纯预测；原配置保持不变。"],
    ))
