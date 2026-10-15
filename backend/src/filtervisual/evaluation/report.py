"""Evaluate actual time-aligned estimates and make evidence-bearing summaries."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from typing import Any

import numpy as np

from filtervisual.core.types import EvaluatedRun, PhysicalEstimate, RunResult
from filtervisual.evaluation.metrics import consistency_summary, error_summary, nees_score, nis_score


def json_safe(value: Any) -> Any:
    """Numeric missing values are explicit nulls, including unavailable geometry."""
    if isinstance(value, np.ndarray):
        return json_safe(value.tolist())
    if isinstance(value, np.generic):
        return json_safe(value.item())
    if isinstance(value, float):
        return value if np.isfinite(value) else None
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [json_safe(item) for item in value]
    if hasattr(value, "model_dump"):
        return json_safe(value.model_dump())
    if is_dataclass(value):
        return {field.name: json_safe(getattr(value, field.name)) for field in fields(value)}
    return value


def physical_dict(physical: Any) -> dict[str, Any]:
    return json_safe(physical)


def _checked_projection(projection):
    from filtervisual.models.protocol import validate_projection
    return validate_projection(projection)


def _safe_project(model, state, covariance):
    try:
        return _checked_projection(model.project(state,covariance))
    except Exception as error:
        return PhysicalEstimate(valid=False, error=f"physical projection failed: {error}")


def physical_error(estimate: PhysicalEstimate, truth: Any | None) -> dict[str, Any] | None:
    if truth is None:
        return None
    output: dict[str, Any] = {}
    for name in (
        "center_xy", "height_a", "velocity_xyz", "reference_yaw", "angular_velocity",
        "radius_a", "radius_b", "height_diff", "armor_positions",
    ):
        # A custom projection can retain finite placeholder values outside its
        # domain. Its validity flag applies to every projected quantity.
        estimated = getattr(estimate, name, None) if estimate.valid else None
        actual = getattr(truth, name, None)
        if estimated is None or actual is None:
            output[name] = None
            continue
        error = np.asarray(estimated, dtype=float) - np.asarray(actual, dtype=float)
        if name == "reference_yaw":
            error = (error + np.pi) % (2 * np.pi) - np.pi
        output[name] = json_safe(error)
    return output


def _mapping_arrays(model, state: np.ndarray, truth) -> tuple[np.ndarray, np.ndarray, Any]:
    actual = np.full(len(state), np.nan)
    errors = np.full(len(state), np.nan)
    mapping = model.truth_mapping(truth) if truth is not None else None
    if mapping is not None:
        if any(not isinstance(i,(int,np.integer)) or isinstance(i,bool) for i in mapping.indices):
            raise ValueError("truth mapping indices must be integers")
        indices = np.asarray(mapping.indices, dtype=int)
        values = np.asarray(mapping.values, dtype=float)
        if values.shape != (len(indices),) or not np.isfinite(values).all() or len(set(indices)) != len(indices):
            raise ValueError("truth mapping requires one value per unique state index")
        if np.any(indices < 0) or np.any(indices >= len(state)):
            raise ValueError("truth mapping index outside model state")
        actual[indices] = values
        difference = np.asarray(state)[indices] - values
        for index in mapping.angular_indices:
            if not 0 <= index < len(indices):
                raise ValueError("truth mapping angular index outside mapped subset")
            difference[index] = (difference[index] + np.pi) % (2 * np.pi) - np.pi
        errors[indices] = difference
    return actual, errors, mapping


def _nees(model, state, covariance, truth, kind, confidence):
    try:
        actual, errors, mapping = _mapping_arrays(model, state, truth)
    except Exception as error:
        actual=np.full(len(state),np.nan)
        score=nees_score(state,covariance,indices=(),truth_values=None,filter_kind=kind,confidence=confidence)
        score.update(reason="invalid_truth_mapping",detail=str(error))
        return actual,actual.copy(),score
    indices = mapping.indices if mapping is not None else ()
    names = [model.state_names[i] for i in indices]
    score = nees_score(
        state, covariance, indices=indices,
        truth_values=mapping.values if mapping is not None else None,
        angular_indices=mapping.angular_indices if mapping is not None else (),
        state_names=names, filter_kind=kind, confidence=confidence,
        truth_available=truth is not None,
    )
    return actual, errors, score


def canonical_truth_state(physical) -> np.ndarray:
    return np.r_[
        physical.center_xy, physical.height_a, physical.velocity_xyz,
        physical.reference_yaw, physical.angular_velocity,
        physical.radius_a, physical.radius_b, physical.height_diff,
    ]


def evaluate_run(result: RunResult) -> EvaluatedRun:
    """Future truth is first read here, after filtering and branching completed."""
    truth = result.data.truth
    confidence = result.config.evaluation.confidence
    truth_rows = []
    for t in result.evaluation_times:
        physical = truth.sample(float(t))
        truth_rows.append(dict(physical_dict(physical), state=json_safe(canonical_truth_state(physical))))
    payload = dict(
        config=json_safe(result.config), truth=truth_rows,
        observations=[dict(id=frame.id, t=frame.t, plate_ids=list(frame.context.plate_ids),
                           values=json_safe(frame.values)) for frame in result.data.observations],
        instances=[],
    )
    for run in result.instances:
        model, kind = run.model, run.config.kind
        if model is None:
            payload["instances"].append(dict(
                id=run.config.id, name=run.config.name, kind=kind, status="failed",
                error=run.error or "model unavailable", state_names=[], units=[], angular_indices=[],
                samples=[], updates=[], forecasts=[], elapsed_s=run.elapsed_s,
                consumed_observations=len(run.consumed_observation_ids),
                skipped_observations=len(run.skipped_observation_ids),
                parameter_snapshot=json_safe(run.config),
            ))
            continue
        samples, updates, forecasts = [], [], []
        for estimate in run.samples:
            physical = _safe_project(model, estimate.x, estimate.P)
            actual_physical = truth.sample(estimate.t)
            actual, errors, nees = _nees(model, estimate.x, estimate.P, actual_physical, kind, confidence)
            samples.append(dict(
                t=estimate.t, x=json_safe(estimate.x), truth=json_safe(actual), error=json_safe(errors),
                P_diag=json_safe(np.diag(estimate.P)), physical=physical_dict(physical), nees=nees,
                physical_error=physical_error(physical, actual_physical),
                mode_probabilities=json_safe(estimate.mode_probabilities),
            ))
        for diagnostic in run.updates:
            updates.append(dict(
                t=diagnostic.t, innovation=json_safe(diagnostic.innovation), S=json_safe(diagnostic.S),
                nis=nis_score(diagnostic.innovation, diagnostic.S, filter_kind=kind, confidence=confidence),
                observation_id=diagnostic.observation_id,
            ))
        for forecast in run.forecasts:
            try:
                projection=_checked_projection(forecast.physical_projection)
            except Exception as error:
                projection=PhysicalEstimate(valid=False,error=str(error))
            available = 0 <= forecast.target_time <= truth.duration_s + 1e-12
            actual_physical = truth.sample(forecast.target_time) if available else None
            prediction_error = getattr(forecast, "error", None)
            if prediction_error:
                actual = np.full(len(forecast.state), np.nan)
                errors = actual.copy()
                nees = nees_score(forecast.state, forecast.P, indices=(), truth_values=None,
                                  filter_kind=kind, confidence=confidence)
                nees.update(reason="prediction_failed", detail=prediction_error)
            else:
                actual, errors, nees = _nees(model, forecast.state, forecast.P, actual_physical, kind, confidence)
            forecasts.append(dict(
                origin_time=forecast.origin_time, lead_s=forecast.lead_s, target_time=forecast.target_time,
                x=json_safe(forecast.state), P_diag=json_safe(np.diag(forecast.P)),
                truth=json_safe(actual), error=json_safe(errors),
                physical=physical_dict(projection),
                truth_physical=physical_dict(actual_physical) if available else None,
                physical_error=physical_error(projection, actual_physical)
                               if not prediction_error else None,
                nees=nees, nis=nis_score(None, None, filter_kind=kind, confidence=confidence),
                truth_available=available, mode_probabilities=json_safe(forecast.mode_probabilities),
                prediction_error=prediction_error,
            ))
        mapping_errors=[row["nees"].get("detail") for row in samples+forecasts
                        if row["nees"].get("reason")=="invalid_truth_mapping"]
        evaluation_error="truth_mapping: "+mapping_errors[0] if mapping_errors else None
        payload["instances"].append(dict(
            id=run.config.id, name=run.config.name, kind=kind,
            status="failed" if run.error or evaluation_error else "completed", error=run.error or evaluation_error,
            state_names=list(model.state_names), units=list(model.units),
            angular_indices=list(model.angular_indices), samples=samples, updates=updates, forecasts=forecasts,
            elapsed_s=run.elapsed_s, consumed_observations=len(run.consumed_observation_ids),
            skipped_observations=len(run.skipped_observation_ids),
            parameter_snapshot=json_safe(run.config),
        ))
    evaluated = EvaluatedRun(payload=json_safe(payload))
    evaluated.payload["report"] = build_report(evaluated)
    return evaluated


def _summary(times, values, width):
    if width == 0:
        return error_summary(times, np.full((len(times), 1), np.nan))
    rows = [np.full(width, np.nan) if value is None else np.asarray(value, dtype=float).reshape(width)
            for value in values]
    errors = np.asarray(rows, dtype=float).reshape(-1, width)
    return error_summary(times, errors)


def _physical_summary(rows, time_key, key, width):
    return _summary(
        [row[time_key] for row in rows],
        [(row.get("physical_error") or {}).get(key) for row in rows], width,
    )


def compare_physical_errors(instances, key, width, lead=None):
    """Compare the intersection of real valid times, never future interpolation."""
    values = {}
    for instance in instances:
        rows = instance["samples"] if lead is None else [
            row for row in instance["forecasts"] if row["lead_s"] == lead
        ]
        time_key = "t" if lead is None else "origin_time"
        at_time = {}
        for row in rows:
            value = (row.get("physical_error") or {}).get(key)
            if value is None:
                continue
            vector = np.asarray(value, dtype=float).reshape(width)
            if np.all(np.isfinite(vector)):
                at_time[round(row[time_key], 12)] = vector
        if at_time:
            values[instance["id"]] = (instance, at_time)
    if not values:
        return None
    common = sorted(set.intersection(*(set(at_time) for _, at_time in values.values())))
    if not common:
        return None
    scores = []
    for instance, at_time in values.values():
        score = error_summary(common, [at_time[t] for t in common])
        scores.append(dict(instance_id=instance["id"], name=instance["name"],
                           rmse=score["vector_rmse"]))
    best = min(scores, key=lambda row: row["rmse"])
    return dict(quantity=key, lead_s=lead, common_count=len(common),
                evidence_interval=[common[0], common[-1]], scores=scores,
                best_instance_id=best["instance_id"], best_name=best["name"], best_rmse=best["rmse"])


def _mode_statistics(samples):
    rows = [(sample["t"], sample["mode_probabilities"]) for sample in samples
            if sample.get("mode_probabilities") is not None]
    if not rows:
        return None
    probabilities = np.asarray([row[1] for row in rows], dtype=float)
    dominant = np.argmax(probabilities, axis=1)
    return dict(count=len(rows), mean=probabilities.mean(axis=0).tolist(),
                last=probabilities[-1].tolist(), min=probabilities.min(axis=0).tolist(),
                max=probabilities.max(axis=0).tolist(),
                dominant_mode_changes=int(np.count_nonzero(np.diff(dominant))),
                evidence_interval=[rows[0][0], rows[-1][0]])


def build_report(evaluated: EvaluatedRun) -> dict[str, Any]:
    """Compare physical quantities on the shared grid without ranking NEES/dof."""
    payload = evaluated.payload
    report: dict[str, Any] = dict(instances=[], recommendations=[], summary=[], comparisons=[])
    for instance in payload["instances"]:
        samples = instance["samples"]
        dimensions = len(instance["state_names"])
        times = [sample["t"] for sample in samples]
        errors = [sample["error"] for sample in samples]
        state_scores = _summary(times, errors, dimensions)
        # Per-component state scores retain mapped dimensions when other dimensions
        # have no truth; the vector score intentionally needs all selected values.
        rmse = []
        for index in range(dimensions):
            component = _summary(times, [[row[index]] for row in errors], 1)
            rmse.append(component["rmse"][0] if component["rmse"] is not None else None)
        center = _physical_summary(samples, "t", "center_xy", 2)
        angle = _physical_summary(samples, "t", "reference_yaw", 1)
        consistency = consistency_summary(
            [dict(sample["nees"], t=sample["t"]) for sample in samples] +
            [dict(update["nis"], t=update["t"]) for update in instance["updates"]]
        )
        forecast_metrics = []
        for lead in sorted(set(row["lead_s"] for row in instance["forecasts"])):
            records = [row for row in instance["forecasts"] if row["lead_s"] == lead]
            future_center = _physical_summary(records, "origin_time", "center_xy", 2)
            future_angle = _physical_summary(records, "origin_time", "reference_yaw", 1)
            armor_scores = []
            for plate in range(4):
                values = []
                for record in records:
                    armor = (record.get("physical_error") or {}).get("armor_positions")
                    values.append(armor[plate] if armor is not None else None)
                armor_scores.append(_summary([r["origin_time"] for r in records], values, 3))
            forecast_metrics.append(dict(
                lead_s=lead, position_rmse=future_center["vector_rmse"],
                angle_rmse=future_angle["vector_rmse"],
                armor_rmse=[score["vector_rmse"] for score in armor_scores],
                count=future_center["count"], max_error=future_center["max_error"],
                evidence_interval=future_center["evidence_interval"],
                time_weighted_rmse=future_center["time_weighted_rmse"],
                armor_max_error=[score["max_error"] for score in armor_scores],
                truth_unavailable=sum(not row["truth_available"] for row in records),
            ))
        config = instance["parameter_snapshot"]
        duration = payload["config"]["scene"]["duration_s"]
        # t=0 is an initialization update and does not increase the rate over time.
        actual_update_hz = sum(row["t"] > 1e-12 for row in instance["updates"]) / duration
        report["instances"].append(dict(
            instance_id=instance["id"], name=instance["name"], kind=instance["kind"],
            status=instance["status"], error=instance.get("error"), sample_count=len(samples),
            rmse=rmse, position_rmse=center["vector_rmse"], angle_rmse=angle["vector_rmse"],
            position_count=center["count"], angle_count=angle["count"],
            position_bias=center["bias"], max_error=center["max_error"],
            time_weighted_rmse=center["time_weighted_rmse"], evidence_interval=center["evidence_interval"],
            forecast=forecast_metrics, consistency=consistency, elapsed_s=instance["elapsed_s"],
            actual_update_hz=actual_update_hz, frequency_hz=config["frequency_hz"],
            skipped_observations=instance["skipped_observations"],
            parameter_snapshot=config, mapped_state_count=sum(value is not None for value in rmse),
            state_vector_scores=state_scores, mode_probability_summary=_mode_statistics(samples),
        ))
    completed = [row for row in report["instances"] if row["status"] == "completed"]
    failed = [row for row in report["instances"] if row["status"] == "failed"]
    if failed:
        report["summary"].append("部分实例失败：" + "、".join(row["name"] for row in failed) + "；比较仅包含已完成实例。")
    if not completed:
        report["summary"].append("没有已完成实例，无法给出完整比较。")
    completed_payload = [row for row in payload["instances"] if row["status"] == "completed"]
    for key, title, unit, width in (("center_xy", "中心位置", "m", 2),
                                   ("reference_yaw", "参考角", "rad", 1)):
        comparison = compare_physical_errors(completed_payload, key, width)
        if comparison:
            report["comparisons"].append(comparison)
            report["summary"].append(
                f"在 {comparison['common_count']} 个共同有效评估时刻内，{comparison['best_name']} 的{title} "
                f"RMSE 为 {comparison['best_rmse']:.6g} {unit}，是 {len(comparison['scores'])} 个可评估实例中的最小值。"
            )
    leads = sorted({row["lead_s"] for item in completed for row in item["forecast"]})
    for lead in leads:
        comparison = compare_physical_errors(completed_payload, "center_xy", 2, lead)
        if comparison:
            report["comparisons"].append(comparison)
            report["summary"].append(
                f"提前 {lead:g} s 的中心预测中，在 {comparison['common_count']} 个共同有效预测起点上，"
                f"{comparison['best_name']} RMSE 为 {comparison['best_rmse']:.6g} m；超出场景尾部的预测不参与评分。"
            )
        else:
            report["summary"].append(f"提前 {lead:g} s 没有共同有效预测起点，仅展示各实例自身指标，不给出跨实例排序。")
    if completed:
        fastest = min(completed, key=lambda item: item["elapsed_s"])
        report["summary"].append(
            f"本次运行中 {fastest['name']} 的滤波、评估网格传播及附带预测耗时为 {fastest['elapsed_s']:.6g} s，"
            "是已完成实例中最短的；不同频率和预测次数会改变计算量。"
        )
    for instance in completed:
        modes = instance["mode_probability_summary"]
        if modes:
            last = "、".join(f"模式 {i}: {value:.1%}" for i, value in enumerate(modes["last"]))
            report["summary"].append(
                f"{instance['name']} 最终模式概率为 {last}，主导模式在评估网格上切换 "
                f"{modes['dominant_mode_changes']} 次；各模式概率曲线用于定位机动响应。"
            )
    report["summary"].append("NIS/NEES 时间序列为相关样本的描述诊断；IMM 使用高斯混合近似参考，不据此跨状态集合排名。")
    from filtervisual.tuning.rules import suggest
    payload["report"] = report
    report["recommendations"] = suggest(evaluated)
    return json_safe(report)
