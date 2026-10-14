"""Loopback FastAPI service and optional built frontend, on a single URL."""
from __future__ import annotations

import argparse
from contextlib import asynccontextmanager
from dataclasses import asdict
import json
import os
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from filtervisual.config.schema import ExperimentConfig, GeometryConfig, ModelDefinition, default_experiment
from filtervisual.config.validation import validate_experiment
from filtervisual.service.jobs import JobManager, RunStatus
from filtervisual.storage.store import RunStore


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class ModelValidationRequest(RequestModel):
    definition: ModelDefinition
    geometry: GeometryConfig = Field(default_factory=GeometryConfig)
    x0: list[float] | None = None
    p0: list[list[float]] | None = None


class ModelValidationIssue(BaseModel):
    message: str
    line: int | None = None
    field: str | None = None


class ModelValidationResponse(BaseModel):
    valid: bool
    issues: list[ModelValidationIssue]
    metadata: dict[str, Any] | None = None


class ModelTemplateResponse(BaseModel):
    source: str


class ScanRequest(RequestModel):
    instance_id: str
    parameter: Literal["q_scale", "r_scale"]
    multipliers: list[float] = Field(default_factory=lambda: [.1, .3, 1., 3., 10.], min_length=1, max_length=20)


class MonteCarloRequest(RequestModel):
    trials: int = Field(default=20, ge=1, le=200)
    seeds: list[int] | None = Field(default=None, min_length=1, max_length=200)


def create_app(data_dir: Path | str, *, timeout_s: float = 120., web_dir: Path | str | None = None) -> FastAPI:
    store = RunStore(data_dir)
    manager = JobManager(store, timeout_s=timeout_s)

    @asynccontextmanager
    async def lifespan(app):
        manager.recover_interrupted()
        yield
        manager.close()

    app = FastAPI(title="FilterVisual local experiment API", version="0.1.0", lifespan=lifespan)
    app.state.store = store
    app.state.jobs = manager
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173",
                        "http://localhost:8000", "http://127.0.0.1:8000"], allow_methods=["GET", "POST"],
                       allow_headers=["Content-Type"])

    def status_or_404(run_id: str):
        try:
            return manager.status(run_id)
        except KeyError:
            raise HTTPException(404, "未找到实验")

    def completed(run_id: str):
        status = status_or_404(run_id)
        if status.status != "completed":
            raise HTTPException(409, {"message": "实验结果尚不可用", "status": status.status, "error": status.error})
        try:
            return store.load(run_id)
        except (OSError, ValueError) as error:
            raise HTTPException(500, f"结果文件无法读取：{error}")

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok", "version": "0.1.0", "worker_count": 1, "timeout_s": manager.timeout_s,
                "timeout_policy": "single_simulation_budget; batch_total_scales_with_trial_count"}

    @app.get("/api/default-config", response_model=ExperimentConfig)
    def default_config():
        return default_experiment()

    @app.get("/api/runs", response_model=list[RunStatus])
    def history():
        return manager.statuses()

    @app.post("/api/runs", response_model=RunStatus, status_code=202)
    def create_run(config: ExperimentConfig):
        issues = validate_experiment(config)
        if issues:
            raise HTTPException(422, [asdict(issue) for issue in issues])
        return manager.status(manager.submit(config))

    @app.get("/api/runs/{run_id}", response_model=RunStatus)
    def run_status(run_id: str):
        return status_or_404(run_id)

    @app.post("/api/runs/{run_id}/cancel", response_model=RunStatus)
    def cancel_run(run_id: str):
        status_or_404(run_id)
        manager.cancel(run_id)
        return manager.status(run_id)

    @app.get("/api/runs/{run_id}/result")
    def result(run_id: str) -> dict:
        return completed(run_id).payload

    @app.get("/api/runs/{run_id}/report")
    def report(run_id: str) -> dict:
        return completed(run_id).report

    @app.get("/api/runs/{run_id}/config", response_model=ExperimentConfig)
    def run_config(run_id: str):
        status_or_404(run_id)
        return store.config(run_id)

    @app.get("/api/runs/{run_id}/series")
    def series(run_id: str, instance: str | None = None, kind: Literal["samples", "updates", "forecasts", "truth", "observations"] = "samples",
               state: str | None = None, lead: float | None = None, start: float | None = None,
               end: float | None = None, offset: int = Query(0, ge=0), limit: int = Query(2000, ge=1, le=10000)) -> dict:
        payload = completed(run_id).payload
        if start is not None and end is not None and start > end:
            raise HTTPException(422, "start 须不大于 end")
        if kind in ("truth", "observations"):
            rows = payload.get(kind, [])
            if state is not None:
                raise HTTPException(422, "状态分量筛选适用于实例状态或预测序列")
        else:
            matches = [row for row in payload.get("instances", []) if instance is None or row["id"] == instance]
            if instance is not None and not matches:
                raise HTTPException(404, "未找到滤波器实例")
            rows = []
            for item in matches:
                index = None
                if state is not None:
                    try:
                        index = item["state_names"].index(state)
                    except ValueError:
                        raise HTTPException(422, f"实例 {item['id']} 不包含状态 {state}")
                    if kind == "updates":
                        raise HTTPException(422, "新息的分量由观测维度定义，不能按状态名筛选")
                for row in item.get(kind, []):
                    copy = dict(row, instance_id=item["id"])
                    if index is not None:
                        copy.update(state=state, unit=item["units"][index], value=row["x"][index],
                                    truth_value=row.get("truth", [None] * len(item["state_names"]))[index],
                                    error_value=row.get("error", [None] * len(item["state_names"]))[index],
                                    variance=row["P_diag"][index])
                    rows.append(copy)
        def timestamp(row):
            return row.get("t", row.get("origin_time", 0.))
        rows = [row for row in rows if (start is None or timestamp(row) >= start) and
                (end is None or timestamp(row) <= end) and
                (lead is None or kind != "forecasts" or abs(row["lead_s"] - lead) < 1e-12)]
        rows.sort(key=timestamp)
        return {"items": rows[offset:offset + limit], "total": len(rows), "offset": offset, "limit": limit,
                "next_offset": offset + limit if offset + limit < len(rows) else None}

    @app.get("/api/runs/{run_id}/export")
    def export(run_id: str, format: Literal["json", "csv", "markdown", "npz", "zip"] = "json"):
        completed(run_id)
        media = {"json": "application/json", "csv": "text/csv; charset=utf-8", "markdown": "text/markdown; charset=utf-8",
                 "npz": "application/octet-stream", "zip": "application/zip"}
        extension = "md" if format == "markdown" else format
        return Response(store.export(run_id, format), media_type=media[format],
                        headers={"Content-Disposition": f'attachment; filename="filtervisual-{run_id}.{extension}"'})

    @app.post("/api/runs/{run_id}/scan", response_model=RunStatus, status_code=202)
    def scan(run_id: str, request: ScanRequest):
        stored = completed(run_id)
        if status_or_404(run_id).kind != "simulation":
            raise HTTPException(422, "候选扫描须基于原始仿真实验")
        if request.instance_id not in [row.id for row in stored.config.instances if row.enabled]:
            raise HTTPException(422, "请指定基线中已启用的实例")
        if any(value <= 0 for value in request.multipliers):
            raise HTTPException(422, "倍率须为有限正数")
        args = request.model_dump()
        args["observation_hash"] = stored.manifest["observation_hash"]
        child = manager.submit(stored.config, "noise_scan", run_id, args)
        return manager.status(child)

    @app.post("/api/runs/{run_id}/monte-carlo", response_model=RunStatus, status_code=202)
    def monte_carlo(run_id: str, request: MonteCarloRequest):
        stored = completed(run_id)
        if status_or_404(run_id).kind != "simulation":
            raise HTTPException(422, "Monte Carlo 须基于原始仿真实验")
        seeds = request.seeds if request.seeds is not None else [stored.config.seed + index for index in range(request.trials)]
        if len(seeds) != request.trials or len(set(seeds)) != len(seeds) or any(seed < 0 for seed in seeds):
            raise HTTPException(422, "seeds 须为与 trials 等长且互不重复的非负种子")
        child = manager.submit(stored.config, "monte_carlo", run_id, {"seeds": seeds})
        return manager.status(child)

    @app.get("/api/models/template", response_model=ModelTemplateResponse)
    def model_template():
        from filtervisual.models.custom import TEMPLATE
        return {"source": TEMPLATE}

    @app.post("/api/models/validate", response_model=ModelValidationResponse)
    def model_validate(request: ModelValidationRequest):
        from filtervisual.models.custom import validate_model
        return validate_model(request.definition, request.geometry, request.x0, request.p0)

    # Mount assets only when built. SPA fallback is restricted to non-API paths.
    dist = Path(web_dir) if web_dir is not None else Path(__file__).resolve().parents[4] / "web" / "dist"
    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")
    if (dist / "index.html").is_file():
        @app.get("/{path:path}", include_in_schema=False)
        def frontend(path: str):
            if path.startswith("api/"):
                raise HTTPException(404, "未知 API 路径")
            file = (dist / path).resolve()
            if file.is_relative_to(dist.resolve()) and file.is_file():
                return FileResponse(file)
            return FileResponse(dist / "index.html")
    return app


app = create_app(Path(os.environ.get("FILTERVISUAL_DATA_DIR", "data")),
                 timeout_s=float(os.environ.get("FILTERVISUAL_JOB_TIMEOUT", "120")))


def main():
    parser = argparse.ArgumentParser(description="FilterVisual local service")
    parser.add_argument("--write-openapi", type=Path)
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if args.write_openapi:
        args.write_openapi.parent.mkdir(parents=True, exist_ok=True)
        args.write_openapi.write_text(json.dumps(app.openapi(), ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        import uvicorn
        uvicorn.run(app, host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
