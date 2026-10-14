"""A single-worker queue; custom model code never executes in the API process."""
from __future__ import annotations

from collections import deque
from copy import deepcopy
from datetime import datetime, timezone
import multiprocessing as mp
import math
from pathlib import Path
import queue
import threading
import time
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel

from filtervisual.config.schema import ExperimentConfig
from filtervisual.core.types import RunCancelled
from filtervisual.storage.store import RunStore


JobState = Literal["queued", "running", "completed", "failed", "cancelled", "timed_out"]


class RunStatus(BaseModel):
    id: str
    name: str = ""
    status: JobState
    progress: float = 0.
    stage: str = "queued"
    error: str | None = None
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    kind: Literal["simulation", "noise_scan", "monte_carlo"] = "simulation"
    parent_id: str | None = None
    timeout_s: float = 120.


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _worker(data_dir: str, run_id: str, config_dict: dict, kind: str, request: dict, events, cancel):
    """Spawn target: only JSON-like messages cross the control channel."""
    try:
        config = ExperimentConfig.model_validate(config_dict)
        store = RunStore(data_dir)
        def emit(progress):
            denominator = progress.total_events or progress.total_instances or 1
            numerator = progress.completed_events if progress.total_events else progress.completed_instances
            events.put(("progress", max(0., min(.95, .95 * numerator / denominator)), progress.phase))
        if kind == "simulation":
            from filtervisual.simulation.runner import run_experiment
            from filtervisual.evaluation.report import evaluate_run
            result = run_experiment(config, cancel=cancel.is_set, emit=emit)
            if cancel.is_set():
                raise RunCancelled()
            events.put(("progress", .96, "evaluating"))
            evaluated = evaluate_run(result)
            if cancel.is_set():
                raise RunCancelled()
            events.put(("progress", .98, "saving"))
            store.save(run_id, config, result, evaluated)
        elif kind == "monte_carlo":
            from filtervisual.evaluation.monte_carlo import run_monte_carlo
            payload = run_monte_carlo(config, request["seeds"], cancel=cancel.is_set, emit=emit)
            if cancel.is_set():
                raise RunCancelled()
            events.put(("progress", .98, "saving"))
            store.save(run_id, config, payload=payload)
        elif kind == "noise_scan":
            from filtervisual.simulation.runner import build_data
            from filtervisual.tuning.scan import scan_noise
            events.put(("progress", .05, "rebuilding_baseline_observations"))
            data = build_data(config)
            if data.observation_hash != request["observation_hash"]:
                raise ValueError("baseline observation hash differs; candidates cannot reuse different observations")
            payload = scan_noise(config, request["instance_id"], request["parameter"], request["multipliers"], data,
                                 cancel=cancel.is_set, emit=emit)
            if cancel.is_set():
                raise RunCancelled()
            events.put(("progress", .98, "saving"))
            store.save(run_id, config, payload=payload, data=data)
        else:
            raise ValueError("unknown job type")
        events.put(("completed",))
    except RunCancelled:
        events.put(("cancelled",))
    except BaseException as error:
        # Syntax/shape/numerical errors remain visible as concrete job failures.
        events.put(("failed", f"{type(error).__name__}: {error}"))


class JobManager:
    def __init__(self, store: RunStore, timeout_s: float = 120.):
        if not math.isfinite(timeout_s) or timeout_s <= 0:
            raise ValueError("job timeout must be finite and positive")
        self.store = store
        self.timeout_s = timeout_s
        self._condition = threading.Condition(threading.RLock())
        self._pending = deque()
        self._records = {}
        self._requests = {}
        self._cancelled = set()
        self._thread = None
        self._closing = False
        self._active = None
        for raw in store.statuses():
            status = RunStatus.model_validate(raw)
            if not status.name:
                status.name = store.config(status.id).name
            self._records[status.id] = status

    def recover_interrupted(self):
        # Called by ASGI lifespan, not module import: spawn reimports its main
        # module and must not change the parent's currently running statuses.
        with self._condition:
            for status in list(self._records.values()):
                if status.status in ("queued", "running"):
                    try:
                        # A parent can exit after the child seals all artifacts
                        # but before its completion event is acknowledged.
                        self.store.load(status.id)
                    except (OSError, ValueError, KeyError):
                        self._change(status.id, status="failed", stage="interrupted",
                                     error="应用重启，先前作业已中断；可从原配置创建新实验", finished_at=_now())
                    else:
                        self._change(status.id, status="completed", stage="completed", progress=1.,
                                     error=None, finished_at=status.finished_at or _now())

    def budget_for(self, kind: str = "simulation", request: dict | None = None) -> float:
        """A batch receives the sum of its individual simulation budgets."""
        request = request or {}
        if kind == "simulation":
            count = 1
        elif kind == "noise_scan":
            count = 1 + len(request.get("multipliers", []))  # Baseline is a real trial.
        elif kind == "monte_carlo":
            count = len(request.get("seeds", []))
        else:
            raise ValueError("unknown job type")
        budget = self.timeout_s * count
        if not math.isfinite(budget) or budget <= 0:
            raise ValueError("job requires a finite positive total timeout budget")
        return budget

    def submit(self, config: ExperimentConfig, kind: str = "simulation", parent_id: str | None = None,
               request: dict | None = None) -> str:
        # Freeze before taking queue ownership; subsequent draft edits cannot
        # alter a submitted run, including mutable nested model parameters.
        snapshot = ExperimentConfig.model_validate(config.model_dump(mode="json"))
        request = deepcopy(request or {})
        run_id = str(uuid4())
        suffix = {"simulation": "", "noise_scan": " · 噪声候选比较", "monte_carlo": " · Monte Carlo"}[kind]
        status = RunStatus(id=run_id, name=snapshot.name + suffix, status="queued", stage="queued", created_at=_now(),
                           kind=kind, parent_id=parent_id, timeout_s=self.budget_for(kind, request))
        with self._condition:
            if self._closing:
                raise RuntimeError("job manager is shutting down")
            self.store.create(run_id, snapshot, status.model_dump(), kind, parent_id, request)
            self._records[run_id] = status
            self._requests[run_id] = (snapshot.model_dump(mode="json"), kind, request)
            self._pending.append(run_id)
            if self._thread is None:
                self._thread = threading.Thread(target=self._loop, name="filtervisual-jobs", daemon=True)
                self._thread.start()
            self._condition.notify_all()
        return run_id

    def status(self, run_id: str) -> RunStatus:
        with self._condition:
            if run_id not in self._records:
                raise KeyError("unknown run")
            return self._records[run_id].model_copy(deep=True)

    def statuses(self) -> list[RunStatus]:
        with self._condition:
            return [row.model_copy(deep=True) for row in sorted(self._records.values(),
                    key=lambda status: status.created_at, reverse=True)]

    def _change(self, run_id: str, **fields):
        with self._condition:
            status = self._records[run_id]
            for key, value in fields.items():
                if key == "progress":
                    value = max(status.progress, value)
                setattr(status, key, value)
            self.store.update_status(run_id, status.model_dump())

    def cancel(self, run_id: str) -> None:
        with self._condition:
            status = self.status(run_id)
            if status.status not in ("queued", "running"):
                return
            self._cancelled.add(run_id)
            if status.status == "queued":
                self._change(run_id, status="cancelled", stage="cancelled", finished_at=_now())
            if self._active is not None and self._active[0] == run_id:
                self._active[2].set()
            self._condition.notify_all()

    def _loop(self):
        context = mp.get_context("spawn")
        while True:
            with self._condition:
                self._condition.wait_for(lambda: self._pending or self._closing)
                if self._closing:
                    return
                run_id = self._pending.popleft()
                if run_id in self._cancelled:
                    self._requests.pop(run_id, None)
                    continue
                config, kind, request = self._requests.pop(run_id)
                events, cancel = context.Queue(), context.Event()
                process = context.Process(target=_worker, args=(str(self.store.root.parent), run_id,
                                          config, kind, request, events, cancel), daemon=True)
                self._active = (run_id, process, cancel)
                self._change(run_id, status="running", stage="starting", started_at=_now())
                budget = self._records[run_id].timeout_s
                start = time.monotonic()
            terminal = None
            error = None
            try:
                process.start()
                while terminal is None:
                    with self._condition:
                        stop = self._closing or run_id in self._cancelled
                    if stop:
                        cancel.set()
                        terminal = "cancelled"
                        break
                    if time.monotonic() - start > budget:
                        terminal = "timed_out"
                        error = (f"作业超过总限时 {budget:g} 秒（单次仿真基础预算 {self.timeout_s:g} 秒），已终止；"
                                 "请缩短场景、减少预测分支或提高基础超时限制")
                        break
                    try:
                        message = events.get(timeout=.05)
                    except queue.Empty:
                        if not process.is_alive():
                            # The queue may flush just after is_alive changes.
                            try:
                                message = events.get(timeout=.1)
                            except queue.Empty:
                                terminal = "failed"
                                error = f"工作进程退出（exit code {process.exitcode}）"
                                break
                        else:
                            continue
                    if message[0] == "progress":
                        self._change(run_id, progress=message[1], stage=message[2])
                    else:
                        terminal = message[0]
                        error = message[1] if len(message) > 1 else None
            except Exception as exception:
                terminal, error = "failed", str(exception)
            finally:
                if process.pid is not None:
                    process.join(timeout=.1)
                    if process.is_alive():
                        process.terminate()
                        process.join(timeout=1.)
                    if process.is_alive():
                        process.kill()
                        process.join(timeout=1.)
                events.close()
                with self._condition:
                    self._active = None
                self._change(run_id, status=terminal or "failed", stage=terminal or "failed",
                             progress=1. if terminal == "completed" else self.status(run_id).progress,
                             error=error, finished_at=_now())

    def close(self):
        with self._condition:
            self._closing = True
            for run_id in list(self._pending):
                self._cancelled.add(run_id)
                self._change(run_id, status="cancelled", stage="shutdown", finished_at=_now())
            if self._active is not None:
                self._active[2].set()
            self._condition.notify_all()
        if self._thread is not None:
            self._thread.join(timeout=4.)
