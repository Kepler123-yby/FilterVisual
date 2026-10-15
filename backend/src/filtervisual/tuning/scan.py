"""Clone Q/R candidates, keeping the baseline and the observation source intact."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from filtervisual.config.schema import ExperimentConfig
from filtervisual.core.types import RunResult, SimulationData, RunProgress, RunCancelled
from filtervisual.evaluation.report import compare_physical_errors, evaluate_run, json_safe


def _compare_candidates(baseline, candidates):
    """Rank common center-error samples; candidate indices survive duplicate scales."""
    scores, participants = [], []
    for index, row in enumerate([baseline] + candidates):
        instance = row["payload"]["instances"][0]
        own_score = row["report"]["instances"][0]
        reason = ("failed" if instance["status"] != "completed" else
                  "no_valid_samples" if own_score["position_rmse"] is None else None)
        scores.append(dict(
            role="baseline" if index == 0 else "candidate",
            candidate_index=None if index == 0 else index - 1,
            multiplier=row["multiplier"], rmse=None, reason=reason,
        ))
        if reason is None:
            # Every trial uses the original instance id; temporary distinct ids
            # prevent one multiplier from overwriting another in the comparison.
            participants.append(dict(instance, id=str(index)))
    comparison = compare_physical_errors(participants, "center_xy", 2)
    if comparison:
        for score in comparison["scores"]:
            scores[int(score["instance_id"])]["rmse"] = score["rmse"]
    else:
        for score in scores:
            if score["reason"] is None:
                score["reason"] = "no_common_times"
    eligible = [score for score in scores if score["role"] == "candidate" and score["rmse"] is not None]
    best = min(eligible, key=lambda score: score["rmse"]) if eligible else None
    return dict(
        quantity="center_xy", common_count=comparison["common_count"] if comparison else 0,
        evidence_interval=comparison["evidence_interval"] if comparison else None,
        scores=scores, best_candidate_index=best["candidate_index"] if best else None,
    )


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
    from filtervisual.simulation.scheduler import time_grid
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
    times = time_grid(config.scene.duration_s, config.evaluation.frequency_hz)
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
    comparison = _compare_candidates(baseline, candidates)
    best_index = comparison["best_candidate_index"]
    if best_index is not None:
        best = next(score for score in comparison["scores"] if score["candidate_index"] == best_index)
        summary.append(
            f"在可评估结果的 {comparison['common_count']} 个共同有效时刻内，"
            f"候选中中心位置 RMSE 最小的倍率为 {best['multiplier']:g}，误差 {best['rmse']:.6g} m；"
            "其他状态和预测需分别核对。"
        )
    else:
        summary.append("没有共同有效的中心位置评估时刻，无法给出候选排序；各自窗口的指标仅用于独立诊断。")
    excluded = sum(score["reason"] in ("failed", "no_valid_samples") for score in comparison["scores"])
    if excluded:
        summary.append(f"有 {excluded} 个基线或候选因失败或无有效中心位置样本未参与共同窗口比较。")
    return json_safe(dict(
        type="noise_scan", instance_id=instance_id, parameter=parameter,
        multipliers=list(multipliers), observation_hash=data.observation_hash,
        baseline=baseline, candidates=candidates, summary=summary, common_comparison=comparison,
        report=dict(summary=summary, baseline=baseline["report"], common_comparison=comparison,
                    candidates=[dict(multiplier=row["multiplier"], report=row["report"]) for row in candidates]),
    ))
