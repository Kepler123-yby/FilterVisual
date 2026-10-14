"""Post-correction lookahead never mutates the main filter or consumes truth."""
from __future__ import annotations

import numpy as np

from filtervisual.core.types import ForecastRecord, PhysicalEstimate, RunCancelled


def advance_to(filter, target_time: float, max_step_s: float = .005, cancel=lambda: False):
    remaining = float(target_time - filter.t)
    if remaining < -1e-10:
        raise ValueError("cannot predict backward in time")
    if remaining <= 1e-12:
        return
    if getattr(filter, "can_predict_exact", lambda dt: False)(remaining):
        filter.predict(remaining)
        return
    steps = int(np.ceil(remaining/max_step_s))
    start = filter.t
    for i in range(steps):
        if i % 32 == 0 and cancel():
            raise RunCancelled()
        end = min(target_time, start+(i+1)*max_step_s)
        filter.predict(max(0., end-filter.t))


def forecast_after_update(filter, instance_id, config, cancel=lambda: False):
    if not config.enabled:
        return []
    start = filter.snapshot()
    forecasts = [None] * len(config.leads_s)

    def record(lead, branch):
        return ForecastRecord(
            instance_id=instance_id, origin_time=start.t, lead_s=lead,
            target_time=start.t + lead, state=branch.x.copy(), P=branch.P.copy(),
            physical_projection=branch.model.project(branch.x, branch.P),
            mode_probabilities=getattr(branch, "probabilities", getattr(branch, "mu", None)),
        )

    def failed(lead, error):
        return ForecastRecord(
            instance_id=instance_id, origin_time=start.t, lead_s=lead,
            target_time=start.t + lead, state=np.full_like(start.x, np.nan),
            P=np.full_like(start.P, np.nan),
            physical_projection=PhysicalEstimate(valid=False, error=str(error)), error=str(error),
        )

    pending = []
    for index, lead in enumerate(config.leads_s):
        if cancel():
            raise RunCancelled()
        try:
            branch = filter.clone()
            target = start.t + lead
            remaining = target - start.t
            if remaining <= 1e-12 or getattr(branch, "can_predict_exact", lambda dt: False)(remaining):
                advance_to(branch, target, config.max_step_s, cancel)
                forecasts[index] = record(lead, branch)
            else:
                # Independent branches run an identical prefix on the grid
                # anchored at this posterior. Share only those complete steps;
                # each endpoint keeps its own final step and model copy.
                steps = int(np.ceil(remaining / config.max_step_s))
                pending.append((steps - 1, index, lead, branch))
        except RunCancelled:
            raise
        except Exception as e:
            forecasts[index] = failed(lead, e)
    if pending:
        pending.sort(key=lambda item: item[0])
        prefix = pending[0][3]
        completed_steps, prefix_error = 0, None
        for prefix_steps, index, lead, _ in pending:
            if cancel():
                raise RunCancelled()
            try:
                if prefix_error is not None:
                    raise prefix_error
                try:
                    while completed_steps < prefix_steps:
                        if completed_steps % 32 == 0 and cancel():
                            raise RunCancelled()
                        completed_steps += 1
                        end = start.t + completed_steps * config.max_step_s
                        prefix.predict(max(0., end - prefix.t))
                except RunCancelled:
                    raise
                except Exception as error:
                    prefix_error = error
                    raise
                branch = prefix.clone()
                branch.predict(max(0., start.t + lead - branch.t))
                forecasts[index] = record(lead, branch)
            except RunCancelled:
                raise
            except Exception as error:
                forecasts[index] = failed(lead, error)
    return forecasts
