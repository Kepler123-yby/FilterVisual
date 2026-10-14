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
    forecasts = []
    for lead in config.leads_s:
        if cancel():
            raise RunCancelled()
        target = start.t+lead
        try:
            branch = filter.clone()
            advance_to(branch,target,config.max_step_s,cancel)
            forecasts.append(ForecastRecord(
                instance_id=instance_id,origin_time=start.t,lead_s=lead,target_time=target,
                state=branch.x.copy(),P=branch.P.copy(),
                physical_projection=branch.model.project(branch.x,branch.P),
                mode_probabilities=getattr(branch,"probabilities",getattr(branch,"mu",None)),
            ))
        except RunCancelled:
            raise
        except Exception as e:
            # A failed lookahead is missing data, never a mutation of the posterior.
            forecasts.append(ForecastRecord(
                instance_id=instance_id,origin_time=start.t,lead_s=lead,target_time=target,
                state=np.full_like(start.x,np.nan),P=np.full_like(start.P,np.nan),
                physical_projection=PhysicalEstimate(valid=False,error=str(e)),error=str(e),
            ))
    return forecasts
