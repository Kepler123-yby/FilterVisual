"""Numerical diagnostics with explicit missing-data and statistical semantics."""
from __future__ import annotations

from typing import Any, Sequence

import numpy as np
from scipy.stats import chi2


def quadratic_score(error: np.ndarray, covariance: np.ndarray) -> float:
    """Return e' P^-1 e through a solve; an invalid covariance is never repaired."""
    error = np.asarray(error, dtype=float)
    covariance = np.asarray(covariance, dtype=float)
    if error.ndim != 1 or not error.size or covariance.shape != (error.size, error.size):
        raise ValueError("error and covariance dimensions must agree and be nonempty")
    if not np.isfinite(error).all() or not np.isfinite(covariance).all():
        raise ValueError("error and covariance must be finite")
    if not np.allclose(covariance, covariance.T, atol=1e-12, rtol=1e-10):
        raise ValueError("covariance must be symmetric")
    try:
        factor = np.linalg.cholesky(covariance)
        whitened = np.linalg.solve(factor, error)
    except np.linalg.LinAlgError as exc:
        raise ValueError("covariance must be positive definite") from exc
    value = float(whitened @ whitened)
    if not np.isfinite(value):
        raise ValueError("quadratic score is not finite")
    return value


def chi_square_bounds(dof: int, confidence: float = .95, trials: int = 1) -> tuple[float, float]:
    """Two-sided bounds, with trials reserved for independent trial averages."""
    if isinstance(dof, bool) or int(dof) != dof or dof < 1:
        raise ValueError("dof must be a positive integer")
    if isinstance(trials, bool) or int(trials) != trials or trials < 1:
        raise ValueError("trials must be a positive integer")
    if not np.isfinite(confidence) or not 0. < confidence < 1.:
        raise ValueError("confidence must be between zero and one")
    tail = (1. - confidence) / 2.
    return (float(chi2.ppf(tail, dof * trials) / trials),
            float(chi2.ppf(1. - tail, dof * trials) / trials))


def _score_record(statistic: str, value: float | None, dof: int | None, *,
                  reason: str | None = None, filter_kind: str = "ekf",
                  confidence: float = .95, state_names: Sequence[str] = ()) -> dict[str, Any]:
    assumption = ("gaussian_mixture_approximation" if filter_kind == "imm"
                  else "nonlinear_gaussian_approximation" if filter_kind in ("ekf", "ukf")
                  else "linear_gaussian_reference")
    label = "高斯混合近似参考" if filter_kind == "imm" else "卡方参考区间"
    bounds = chi_square_bounds(dof, confidence) if value is not None and dof is not None else None
    return dict(statistic=statistic, value=value, dof=dof, reason=reason,
                confidence=confidence, bounds=list(bounds) if bounds else None,
                assumption=assumption, label=label, state_names=list(state_names))


def nis_score(innovation: np.ndarray | None, covariance: np.ndarray | None, *,
              filter_kind: str = "ekf", confidence: float = .95,
              reason: str = "no_new_observation") -> dict[str, Any]:
    if innovation is None or covariance is None:
        return _score_record("nis", None, None, reason=reason, filter_kind=filter_kind,
                             confidence=confidence)
    innovation = np.asarray(innovation, dtype=float)
    try:
        value = quadratic_score(innovation, covariance)
    except ValueError as exc:
        out = _score_record("nis", None, len(innovation), reason="invalid_covariance",
                            filter_kind=filter_kind, confidence=confidence)
        out["detail"] = str(exc)
        return out
    return _score_record("nis", value, len(innovation), filter_kind=filter_kind, confidence=confidence)


def nees_score(state: np.ndarray, covariance: np.ndarray, *, indices: Sequence[int],
               truth_values: Sequence[float] | None, angular_indices: Sequence[int] = (),
               state_names: Sequence[str] = (), filter_kind: str = "ekf",
               confidence: float = .95, truth_available: bool = True) -> dict[str, Any]:
    """Score only mapped states; angular indices address the mapped subset."""
    common = dict(filter_kind=filter_kind, confidence=confidence, state_names=state_names)
    if not truth_available:
        return _score_record("nees", None, None, reason="truth_unavailable", **common)
    if truth_values is None or len(indices) == 0:
        return _score_record("nees", None, None, reason="no_truth_mapping", **common)
    state = np.asarray(state, dtype=float)
    covariance = np.asarray(covariance, dtype=float)
    subset = np.asarray(indices, dtype=int)
    values = np.asarray(truth_values, dtype=float)
    if state.ndim != 1 or covariance.shape != (state.size, state.size):
        raise ValueError("state and covariance dimensions must agree")
    if values.shape != (len(subset),) or len(set(subset)) != len(subset):
        raise ValueError("truth mapping values must match unique state indices")
    if (subset < 0).any() or (subset >= state.size).any():
        raise ValueError("truth mapping state index out of range")
    error = state[subset] - values
    for index in angular_indices:
        if not 0 <= index < len(subset):
            raise ValueError("truth mapping angular index out of range")
        error[index] = (error[index] + np.pi) % (2 * np.pi) - np.pi
    try:
        value = quadratic_score(error, covariance[np.ix_(subset, subset)])
    except ValueError as exc:
        out = _score_record("nees", None, len(subset), reason="invalid_covariance", **common)
        out["detail"] = str(exc)
        return out
    return _score_record("nees", value, len(subset), **common)


def error_summary(times: Sequence[float], errors: Sequence[Sequence[float]]) -> dict[str, Any]:
    """Component and vector scores; missing endpoints never count as zero errors."""
    times = np.asarray(times, dtype=float)
    errors = np.asarray(errors, dtype=float)
    if errors.ndim == 1:
        errors = errors[:, None]
    if errors.ndim != 2 or len(times) != len(errors) or times.ndim != 1:
        raise ValueError("one error vector is required per time")
    if not np.isfinite(times).all() or (np.diff(times) < 0).any():
        raise ValueError("times must be finite and nondecreasing")
    valid = np.isfinite(errors).all(axis=1)
    count = int(valid.sum())
    if not count:
        return dict(count=0, rmse=None, vector_rmse=None, bias=None, max_error=None,
                    time_weighted_rmse=None, evidence_interval=None, reason="no_valid_samples")
    selected = errors[valid]
    weighted = None
    # Integrate only adjacent valid samples, preserving gaps and unavailable tails.
    segments = valid[:-1] & valid[1:]
    durations = np.diff(times)
    duration = float(durations[segments].sum())
    if duration > 0:
        integral = ((errors[:-1][segments] ** 2 + errors[1:][segments] ** 2) *
                    durations[segments, None] / 2.).sum(axis=0)
        weighted = np.sqrt(integral / duration).tolist()
    return dict(count=count, rmse=np.sqrt(np.mean(selected ** 2, axis=0)).tolist(),
                vector_rmse=float(np.sqrt(np.mean(np.sum(selected ** 2, axis=1)))),
                bias=np.mean(selected, axis=0).tolist(),
                max_error=float(np.max(np.linalg.norm(selected, axis=1))),
                time_weighted_rmse=weighted,
                evidence_interval=[float(times[valid][0]), float(times[valid][-1])], reason=None)


def consistency_summary(records: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group time diagnostics by statistic, mapped state semantics, and dof."""
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for row in records:
        if row.get("value") is None:
            continue
        key = (row["statistic"], row["dof"], tuple(row.get("state_names", [])), row["assumption"])
        groups.setdefault(key, []).append(row)
    output = []
    for (statistic, dof, names, assumption), rows in groups.items():
        values = np.asarray([row["value"] for row in rows], dtype=float)
        outside = [not row["bounds"][0] <= row["value"] <= row["bounds"][1] for row in rows]
        times = [float(row["t"]) for row in rows if row.get("t") is not None]
        output.append(dict(statistic=statistic, dof=dof, state_names=list(names),
                           assumption=assumption, count=len(rows), mean=float(values.mean()),
                           outside_fraction=float(np.mean(outside)),
                           lower_fraction=float(np.mean([row["value"] < row["bounds"][0] for row in rows])),
                           upper_fraction=float(np.mean([row["value"] > row["bounds"][1] for row in rows])),
                           evidence_interval=[min(times), max(times)] if times else None,
                           interpretation="correlated_time_samples_descriptive"))
    return output
