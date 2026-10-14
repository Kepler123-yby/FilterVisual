"""Clone Q/R candidates, keeping the baseline and the observation source intact."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from filtervisual.config.schema import ExperimentConfig
from filtervisual.core.types import RunResult, SimulationData, RunProgress, RunCancelled
from filtervisual.evaluation.report import evaluate_run, json_safe


def scan_noise(
    config: ExperimentConfig, instance_id: str, parameter: str,
    multipliers: Sequence[float], data: SimulationData,
    *, cancel=lambda: False, emit=lambda progress: None,
) -> dict:
    if parameter not in ("q_scale", "r_scale"):
        raise ValueError("noise scan parameter must be q_scale or r_scale")
    multipliers = list(multipliers)
    if not multipliers or any(not np.isfinite(value) or value <= 0 for value in multipliers):
        raise ValueError("noise scan requires finite positive multipliers")
    matches = [instance for instance in config.instances if instance.id == instance_id]
    if not matches:
        raise ValueError(f"unknown instance {instance_id}")
    original = matches[0]
    baseline_value = getattr(original, parameter)
    from filtervisual.models.registry import make_model
    from filtervisual.simulation.runner import config_hash, run_instance
    expected_hash = config_hash(dict(scene=config.scene.model_dump(), seed=config.seed))
    if data.scene_hash != expected_hash:
        raise ValueError("scan scene_hash differs from the baseline scene and seed; cannot reuse observations")
    if data.observation_config_hash != config_hash(dict(observation=config.observation.model_dump(),seed=config.seed)):
        raise ValueError("scan observation_config_hash differs from the baseline noise and observation configuration")
    required_ids = {original.model_id}
    if original.kind == "imm":
        required_ids.update(mode.model_id for mode in original.imm.models)
    models = {definition.id: make_model(definition, config.scene.geometry)
              for definition in config.models if definition.id in required_ids}
    if set(models) != required_ids:
        raise ValueError("scan requires all primary and IMM mode models in the model registry")
    duration = config.scene.duration_s
    frequency = config.evaluation.frequency_hz
    times = np.arange(int(np.floor(duration * frequency + 1e-10)) + 1) / frequency
    if times[-1] < duration - 1e-12:
        times = np.r_[times, duration]
    results = []
    # Always include a real baseline, even if the requested list omits multiplier 1.
    total=1+len(multipliers)
    for index,multiplier in enumerate([1.] + list(multipliers)):
        if cancel():
            raise RunCancelled()
        candidate = config.model_copy(deep=True)
        candidate.instances = [original.model_copy(deep=True)]
        candidate.instances[0].enabled = True
        setattr(candidate.instances[0], parameter, baseline_value * float(multiplier))
        model = models[original.model_id]
        run = run_instance(candidate.instances[0], model, data, candidate.forecast, times, models=models,
                           cancel=cancel,emit=lambda fraction: emit(RunProgress(
                               "noise_scan",index,total,int((index+fraction)*1000),total*1000)))
        evaluated = evaluate_run(RunResult(candidate, data, [run], times))
        results.append(dict(
            multiplier=float(multiplier), value=baseline_value * float(multiplier),
            parameter_diff={parameter: dict(before=baseline_value, after=baseline_value * float(multiplier))},
            config=json_safe(candidate), payload=evaluated.payload, report=evaluated.payload["report"],
        ))
        emit(RunProgress("noise_scan",index+1,total,(index+1)*1000,total*1000))
    baseline, candidates = results[0], results[1:]
    summary = [
        f"为 {original.name} 比较 {parameter} 的 {len(candidates)} 个倍率，"
        "所有候选复用基线的相同观测帧，原配置保持不变。"
    ]
    eligible = [row for row in candidates if row["report"]["instances"][0]["status"] == "completed"
                and row["report"]["instances"][0]["position_rmse"] is not None]
    if eligible:
        best = min(eligible, key=lambda row: row["report"]["instances"][0]["position_rmse"])
        value = best["report"]["instances"][0]["position_rmse"]
        summary.append(f"候选中中心位置 RMSE 最小的倍率为 {best['multiplier']:g}，误差 {value:.6g} m；其他状态和预测需分别核对。")
    return json_safe(dict(
        type="noise_scan", instance_id=instance_id, parameter=parameter,
        multipliers=list(multipliers), observation_hash=data.observation_hash,
        baseline=baseline, candidates=candidates, summary=summary,
        report=dict(summary=summary, baseline=baseline["report"],
                    candidates=[dict(multiplier=row["multiplier"], report=row["report"]) for row in candidates]),
    ))
