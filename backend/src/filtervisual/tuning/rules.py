"""Local hypotheses grounded in real errors and consistency diagnostics."""

from __future__ import annotations

import numpy as np

from filtervisual.core.types import EvaluatedRun


def suggest(evaluated: EvaluatedRun) -> list[dict]:
    payload = evaluated.payload
    report = payload.get("report", {})
    recommendations = []
    configurations = payload["config"]["instances"]
    by_id = {row["id"]: (index, row) for index, row in enumerate(configurations)}
    for result in report.get("instances", []):
        if result["status"] != "completed" or result["instance_id"] not in by_id:
            continue
        index, configuration = by_id[result["instance_id"]]
        prefix = f"instances[{index}]"
        for group in result["consistency"]:
            if group["count"] < 50 or group["outside_fraction"] <= .1:
                continue
            high = group["upper_fraction"] >= group["lower_fraction"]
            title = ("协方差可能偏自信，建议比较更大的过程噪声" if high
                     else "协方差可能偏保守，建议比较更小的过程噪声")
            multiplier = 3 if high else .3
            recommendations.append(dict(
                instance_id=result["instance_id"], title=title,
                evidence=dict(interval=group["evidence_interval"],
                              metric=f"{group['statistic']}_outside_fraction_dof_{group['dof']}",
                              value=group["outside_fraction"], count=group["count"]),
                causes=["运动或观测模型与目标不匹配", "过程噪声 Q 或观测噪声 R 的尺度不匹配",
                        "初始化误差、异常观测或非高斯噪声"],
                parameter_paths=[f"{prefix}.q_scale", f"{prefix}.r_scale"],
                trial_patch=dict(q_scale=configuration["q_scale"] * multiplier), hypothesis=True,
                note="超过 10% 的出界比例是启发式提示；连续时间样本相关，不能判定 Q/R 的唯一原因。",
            ))
        instance = next(row for row in payload["instances"] if row["id"] == result["instance_id"])
        samples = instance["samples"]
        center_rows = []
        for sample in samples:
            error = (sample.get("physical_error") or {}).get("center_xy")
            if error is not None and np.all(np.isfinite(np.asarray(error, dtype=float))):
                center_rows.append((sample["t"], np.linalg.norm(error)))
        if len(center_rows) >= 10:
            times, magnitude = np.asarray(center_rows).T
            cut = max(3, len(center_rows) // 5)
            initial, later = float(np.mean(magnitude[:cut])), float(np.mean(magnitude[-cut:]))
            if initial > max(.02, 3 * later):
                recommendations.append(dict(
                    instance_id=result["instance_id"], title="初始阶段误差较大，检查初始状态与 P₀",
                    evidence=dict(interval=[float(times[0]), float(times[cut - 1])],
                                  metric="initial_position_error_mean", value=initial, count=cut),
                    causes=["初始中心、速度或参考角与先验不匹配", "P₀ 过小限制了观测校正",
                            "初始运动段存在模型未描述的机动"],
                    parameter_paths=[f"{prefix}.x0", f"{prefix}.p0"], trial_patch={}, hypothesis=True,
                    note="调整初始化后在同一观测数据上复跑，检查收敛与后期误差。",
                ))
        bias = result.get("position_bias")
        rmse = result.get("position_rmse")
        if bias is not None and rmse is not None and result["sample_count"] >= 50:
            norm_bias = float(np.linalg.norm(bias))
            if norm_bias > .01 and norm_bias > .5 * rmse:
                recommendations.append(dict(
                    instance_id=result["instance_id"], title="中心误差存在持续偏置，检查几何与观测方程",
                    evidence=dict(interval=result["evidence_interval"], metric="position_bias_norm",
                                  value=norm_bias, count=result["sample_count"]),
                    causes=["参考板、板编号、yaw 零点或几何参数约定不一致", "观测噪声包含系统性偏差",
                            "模型缺少运动项或尚未收敛"],
                    parameter_paths=[f"{prefix}.model_id", "scene.geometry"], trial_patch={}, hypothesis=True,
                    note="单纯扩大 Q/R 通常不能证明或消除结构性偏置；先核对方程与坐标约定。",
                ))
        nominal = configuration["frequency_hz"]
        actual = result["actual_update_hz"]
        if nominal > 0 and actual < .7 * nominal:
            recommendations.append(dict(
                instance_id=result["instance_id"], title="实际校正频率低于设置频率，检查观测与缺测",
                evidence=dict(interval=[0, payload["config"]["scene"]["duration_s"]],
                              metric="actual_update_hz", value=actual),
                causes=["观测频率低于滤波周期频率", "可见板缺失、随机缺测或观测帧被跳过"],
                parameter_paths=[f"{prefix}.frequency_hz", "observation.frequency_hz",
                                 "observation.dropout_probability"], trial_patch={}, hypothesis=True,
                note="增加滤波周期频率不会产生新的观测；比较预测误差与实际校正数量后再修改。",
            ))
    return recommendations
