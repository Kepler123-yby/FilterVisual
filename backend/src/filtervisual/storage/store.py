"""Immutable result snapshots plus separately mutable lifecycle status."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from hashlib import sha256
from importlib.metadata import PackageNotFoundError, version
from io import BytesIO, StringIO
import json
from pathlib import Path
import platform
import re
from uuid import UUID
from zipfile import ZIP_DEFLATED, ZipFile

import numpy as np

from filtervisual import __version__
from filtervisual.config.schema import ExperimentConfig
from filtervisual.simulation.runner import config_hash


def _json_bytes(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2).encode("utf-8")


def _write(path: Path, value) -> None:
    raw = _json_bytes(value)  # Validate before touching any persistent file.
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(raw)
    temporary.replace(path)


def _versions() -> dict:
    values = {"python": platform.python_version(), "filtervisual": __version__}
    for name in ("numpy", "scipy", "pydantic", "fastapi"):
        try:
            values[name] = version(name)
        except PackageNotFoundError:
            values[name] = "unavailable"
    return values


def _source_fingerprint() -> dict:
    source_root = Path(__file__).resolve().parents[1]
    files = {str(path.relative_to(source_root)): sha256(path.read_bytes()).hexdigest()
             for path in sorted(source_root.rglob("*.py"))}
    return {"sha256": sha256(_json_bytes(files)).hexdigest(), "files": files}


@dataclass(frozen=True)
class StoredRun:
    config: ExperimentConfig
    payload: dict
    report: dict
    manifest: dict


class RunStore:
    def __init__(self, data_dir: Path | str):
        self.root = Path(data_dir) / "runs"
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, run_id: str) -> Path:
        # UUID-only identities prevent API clients from escaping the store.
        try:
            if str(UUID(run_id)) != run_id:
                raise ValueError
        except (ValueError, TypeError, AttributeError) as error:
            raise KeyError("unknown run") from error
        return self.root / run_id

    def create(self, run_id: str, config: ExperimentConfig, status: dict,
               kind: str = "simulation", parent_id: str | None = None,
               request: dict | None = None) -> None:
        path = self.path(run_id)
        payload = config.model_dump(mode="json")
        _json_bytes(payload)
        path.mkdir(exist_ok=False)
        _write(path / "experiment.json", payload)
        _write(path / "status.json", status)
        models = path / "models"
        models.mkdir()
        for index, model in enumerate(config.models):
            if model.kind == "python":
                safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", model.id)[:80]
                (models / f"{index:02d}-{safe_name}.py").write_text(model.source or "", encoding="utf-8")
        _write(path / "manifest.json", {
            "schema_version": 1, "id": run_id, "kind": kind, "parent_id": parent_id,
            "created_at": status["created_at"], "config_hash": config_hash(config),
            "observation_config_hash": config_hash(config.observation),
            "seed": config.seed, "versions": _versions(), "request": request or {},
            "backend_source": _source_fingerprint(),
            "missing_values": "JSON null; NPZ NaN with a boolean validity mask",
            "units": "model state units; physical position m, angles rad, time s",
            "sealed": False,
        })

    def update_status(self, run_id: str, status: dict) -> None:
        path = self.path(run_id)
        if not path.is_dir():
            raise KeyError("unknown run")
        _write(path / "status.json", status)

    def statuses(self) -> list[dict]:
        output = []
        for path in self.root.glob("*/status.json"):
            try:
                row = json.loads(path.read_text(encoding="utf-8"))
                self.path(row["id"])
                output.append(row)
            except (KeyError, OSError, ValueError):
                continue
        return sorted(output, key=lambda row: row["created_at"], reverse=True)

    def config(self, run_id: str) -> ExperimentConfig:
        path = self.path(run_id) / "experiment.json"
        if not path.exists():
            raise KeyError("unknown run")
        return ExperimentConfig.model_validate_json(path.read_text(encoding="utf-8"))

    def save(self, run_id: str, config: ExperimentConfig, result=None, evaluated=None,
             *, payload: dict | None = None, data=None) -> None:
        path = self.path(run_id)
        if not path.is_dir():
            raise KeyError("unknown run")
        manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
        if manifest["sealed"] or (path / "payload.json").exists():
            raise FileExistsError("completed run results are immutable")
        if manifest["config_hash"] != config_hash(config):
            raise ValueError("result configuration differs from the submitted immutable snapshot")
        payload = payload if payload is not None else evaluated.payload
        _json_bytes(payload)  # Reject NaN and Inf rather than silently changing results.
        report = payload.get("report", {})
        _write(path / "payload.json", payload)
        _write(path / "report.json", report)
        observation_arrays = {}
        result_arrays = {}
        data = result.data if result is not None else data
        if data is not None:
            frames = data.observations
            observation_arrays["t"] = np.array([frame.t for frame in frames])
            observation_arrays["id"] = np.array([frame.id for frame in frames], dtype="U")
            width = max((len(frame.values) for frame in frames), default=0)
            values = np.full((len(frames), width), np.nan)
            ids = np.full((len(frames), 4), -1, dtype=int)
            for index, frame in enumerate(frames):
                values[index, :len(frame.values)] = frame.values
                ids[index, :len(frame.context.plate_ids)] = frame.context.plate_ids
            observation_arrays.update(values=values, valid=np.isfinite(values), plate_ids=ids)
            manifest.update(scene_hash=data.scene_hash, observation_hash=data.observation_hash)
        if result is not None:
            result_arrays["truth_t"] = np.array([row["t"] for row in payload["truth"]])
            result_arrays["truth_state"] = np.array([row["state"] for row in payload["truth"]], dtype=float)
            result_arrays["truth_armor_positions"] = np.array([row["armor_positions"] for row in payload["truth"]], dtype=float)
            for index, instance in enumerate(result.instances):
                prefix = f"instance_{index}"
                n = len(instance.config.x0)
                wire = payload["instances"][index]
                result_arrays[f"{prefix}_id"] = np.array(instance.config.id)
                result_arrays[f"{prefix}_t"] = np.array([sample.t for sample in instance.samples])
                result_arrays[f"{prefix}_x"] = np.array([sample.x for sample in instance.samples]).reshape(-1, n)
                result_arrays[f"{prefix}_P"] = np.array([sample.P for sample in instance.samples]).reshape(-1, n, n)
                result_arrays[f"{prefix}_forecast_origin"] = np.array([row.origin_time for row in instance.forecasts])
                result_arrays[f"{prefix}_forecast_target"] = np.array([row.target_time for row in instance.forecasts])
                result_arrays[f"{prefix}_forecast_x"] = np.array([row.state for row in instance.forecasts]).reshape(-1, n)
                result_arrays[f"{prefix}_forecast_P"] = np.array([row.P for row in instance.forecasts]).reshape(-1, n, n)
                for kind, raw_rows, wire_rows in (("sample", instance.samples, wire["samples"]),
                                                 ("forecast", instance.forecasts, wire["forecasts"])):
                    for key in ("truth", "error"):
                        result_arrays[f"{prefix}_{kind}_{key}"] = np.array([row[key] for row in wire_rows], dtype=float).reshape(-1, n)
                    result_arrays[f"{prefix}_{kind}_nees"] = np.array([row["nees"]["value"] for row in wire_rows], dtype=float)
                    result_arrays[f"{prefix}_{kind}_nees_dof"] = np.array([row["nees"]["dof"] or 0 for row in wire_rows], dtype=int)
                    mode_width = max((len(row.mode_probabilities) for row in raw_rows if row.mode_probabilities is not None), default=0)
                    result_arrays[f"{prefix}_{kind}_mode_probabilities"] = np.array([
                        row.mode_probabilities if row.mode_probabilities is not None else np.full(mode_width, np.nan)
                        for row in raw_rows], dtype=float).reshape(len(raw_rows), mode_width)
                updates = instance.updates
                update_width = max((len(row.innovation) for row in updates), default=0)
                innovations = np.full((len(updates), update_width), np.nan)
                innovation_covariance = np.full((len(updates), update_width, update_width), np.nan)
                for row_index, row in enumerate(updates):
                    width = len(row.innovation)
                    innovations[row_index, :width] = row.innovation
                    innovation_covariance[row_index, :width, :width] = row.S
                result_arrays.update({
                    f"{prefix}_update_t": np.array([row.t for row in updates]),
                    f"{prefix}_update_dof": np.array([row.dof for row in updates], dtype=int),
                    f"{prefix}_update_observation_id": np.array([row.observation_id for row in updates], dtype="U"),
                    f"{prefix}_innovation": innovations, f"{prefix}_innovation_S": innovation_covariance,
                    f"{prefix}_nis": np.array([row["nis"]["value"] for row in wire["updates"]], dtype=float),
                })
        else:
            # Child experiments have their full structured series in JSON. Keep
            # relevant numeric trial/scan summaries in a non-pickle NPZ too.
            if payload.get("type") == "monte_carlo":
                seeds = payload.get("seeds", [])
                dtype = np.int64 if all(seed <= np.iinfo(np.int64).max for seed in seeds) else "U"
                result_arrays["seeds"] = np.asarray(seeds, dtype=dtype)
                groups = payload.get("groups", [])
                for key in ("t", "mean", "dof", "count"):
                    result_arrays[key] = np.array([row[key] for row in groups])
                result_arrays["bounds"] = np.array([row["bounds"] for row in groups]).reshape(-1, 2)
            elif payload.get("type") == "noise_scan":
                result_arrays["multipliers"] = np.array(payload.get("multipliers", []), dtype=float)
                manifest["observation_hash"] = payload.get("observation_hash")
        # Missing diagnostics and padded observation dimensions remain explicit
        # in NPZ; every numerical array receives its own validity mask.
        for arrays in (observation_arrays, result_arrays):
            for key, value in list(arrays.items()):
                if np.issubdtype(value.dtype, np.number) and not key.endswith("_valid"):
                    arrays[f"{key}_valid"] = np.isfinite(value)
        np.savez_compressed(path / "observations.npz", **observation_arrays)
        np.savez_compressed(path / "results.npz", **result_arrays)
        manifest["sealed"] = True
        manifest["files"] = {
            str(file.relative_to(path)): sha256(file.read_bytes()).hexdigest()
            for file in sorted(path.rglob("*"))
            if file.is_file() and file.name not in ("manifest.json", "status.json")
        }
        _write(path / "manifest.json", manifest)

    def load(self, run_id: str) -> StoredRun:
        path = self.path(run_id)
        config = self.config(run_id)
        if not (path / "payload.json").exists():
            raise FileNotFoundError("run result is not ready")
        manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
        if not manifest.get("sealed"):
            raise ValueError("run result is incomplete: manifest is not sealed")
        for name, expected in manifest.get("files", {}).items():
            file = (path / name).resolve()
            if not file.is_relative_to(path.resolve()) or not file.is_file():
                raise ValueError(f"artifact missing or invalid: {name}")
            if sha256(file.read_bytes()).hexdigest() != expected:
                raise ValueError(f"artifact checksum mismatch: {name}")
        if manifest.get("config_hash") != config_hash(config):
            raise ValueError("experiment configuration checksum mismatch")
        return StoredRun(config, json.loads((path / "payload.json").read_text(encoding="utf-8")),
                         json.loads((path / "report.json").read_text(encoding="utf-8")),
                         manifest)

    def export(self, run_id: str, format: str = "json") -> bytes:
        stored = self.load(run_id)
        path = self.path(run_id)
        if format == "json":
            return _json_bytes({"manifest": stored.manifest, "config": stored.config.model_dump(mode="json"),
                                "result": stored.payload})
        if format == "npz":
            return (path / "results.npz").read_bytes()
        if format == "zip":
            buffer = BytesIO()
            with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
                for file in sorted(path.rglob("*")):
                    if file.is_file() and not file.name.endswith(".tmp"):
                        archive.write(file, str(file.relative_to(path)))
            return buffer.getvalue()
        if format == "markdown":
            text = f"# {stored.config.name}\n\n配置哈希：`{stored.manifest['config_hash']}`\n\n"
            text += "\n\n".join(stored.report.get("summary", []))
            text += "\n\n```json\n" + _json_bytes(stored.report).decode() + "\n```\n"
            return text.encode("utf-8")
        if format == "csv":
            buffer = StringIO(newline="")
            writer = csv.writer(buffer)
            if stored.payload.get("type") == "monte_carlo":
                writer.writerow(["config_hash", "instance_id", "t_s", "statistic", "unit", "mean", "lower", "upper",
                                 "dof", "valid_trials", "requested_trials", "state_names", "assumption"])
                for row in stored.payload["groups"]:
                    writer.writerow([stored.manifest["config_hash"], row["instance_id"], row["t"], row["statistic"],
                                     "dimensionless", row["mean"], *row["bounds"], row["dof"], row["count"], row["trials"],
                                     "|".join(row["state_names"]), row["assumption"]])
                return ("\ufeff" + buffer.getvalue()).encode("utf-8")
            if stored.payload.get("type") == "noise_scan":
                writer.writerow(["config_hash", "instance_id", "candidate", "parameter", "multiplier", "value",
                                 "metric", "unit", "metric_value", "valid_samples"])
                # Keep the same common-window evidence used by UI and ranking.
                comparison = stored.payload.get("common_comparison", {})
                for score in comparison.get("scores", []):
                    candidate_index = score["candidate_index"]
                    label = "baseline" if candidate_index is None else f"candidate_{candidate_index}"
                    candidate = (stored.payload["baseline"] if candidate_index is None else
                                 stored.payload["candidates"][candidate_index])
                    writer.writerow([stored.manifest["config_hash"], stored.payload["instance_id"], label,
                                     stored.payload["parameter"], candidate["multiplier"], candidate["value"],
                                     "common_position_rmse", "m", score["rmse"],
                                     comparison["common_count"] if score["rmse"] is not None else 0])
                for label, candidate in [("baseline", stored.payload["baseline"])] + [
                    (f"candidate_{index}", row) for index, row in enumerate(stored.payload["candidates"])]:
                    for row in candidate["report"]["instances"]:
                        for metric, unit in (("position_rmse", "m"), ("angle_rmse", "rad")):
                            writer.writerow([stored.manifest["config_hash"], row["instance_id"], label,
                                             stored.payload["parameter"], candidate["multiplier"], candidate["value"],
                                             metric, unit, row.get(metric), row.get(metric.replace("_rmse", "_count"))])
                        for forecast in row.get("forecast", []):
                            writer.writerow([stored.manifest["config_hash"], row["instance_id"], label,
                                             stored.payload["parameter"], candidate["multiplier"], candidate["value"],
                                             f"forecast_position_rmse_lead_{forecast['lead_s']:g}s", "m",
                                             forecast.get("position_rmse"), forecast.get("count")])
                return ("\ufeff" + buffer.getvalue()).encode("utf-8")
            writer.writerow(["config_hash", "instance_id", "kind", "t_s", "origin_time_s", "lead_s",
                             "state", "unit", "estimate", "truth", "error", "valid", "prediction_error"])
            for instance in stored.payload.get("instances", []):
                names, units = instance["state_names"], instance["units"]
                for kind in ("samples", "forecasts"):
                    for row in instance[kind]:
                        for i, name in enumerate(names):
                            estimate = row["x"][i]
                            truth = row.get("truth", [None] * len(names))[i]
                            error = row.get("error", [None] * len(names))[i]
                            writer.writerow([stored.manifest["config_hash"], instance["id"], kind,
                                             row.get("t", row.get("target_time")), row.get("origin_time", ""),
                                             row.get("lead_s", ""), name, units[i],
                                             "" if estimate is None else estimate,
                                             "" if truth is None else truth, "" if error is None else error,
                                             error is not None, row.get("prediction_error", "")])
            # UTF-8 BOM makes Chinese model names readable in spreadsheet tools.
            return ("\ufeff" + buffer.getvalue()).encode("utf-8")
        raise ValueError("export format must be json, csv, markdown, npz or zip")
