"""A normal cycle consumes at most one new frame, at its actual timestamp."""
from __future__ import annotations

from time import perf_counter
import copy
import numpy as np

from filtervisual.core.types import Estimate, InstanceRun, RunCancelled
from filtervisual.models.registry import make_filter
from filtervisual.simulation.forecast import forecast_after_update


def time_grid(duration: float, frequency: float):
    count = int(np.floor(duration*frequency+1e-10))
    grid = np.arange(count+1,dtype=float)/frequency
    if grid[-1] < duration-1e-10:
        grid = np.r_[grid,duration]
    return grid


def estimate_at(past_snapshot,target_time,model,filter_template=None):
    if target_time < past_snapshot.t-1e-10:
        raise ValueError("evaluation cannot use a future posterior")
    if abs(target_time-past_snapshot.t) <= 1e-10:
        return Estimate(target_time,past_snapshot.x.copy(),past_snapshot.P.copy(),
                        None if past_snapshot.mode_probabilities is None else past_snapshot.mode_probabilities.copy())
    if filter_template is None:
        raise ValueError("a configured filter template is required for causal interpolation")
    branch=filter_template.clone()
    branch.restore(past_snapshot)
    branch.predict(target_time-branch.t)
    snapshot=branch.snapshot()
    return Estimate(target_time,snapshot.x.copy(),snapshot.P.copy(),snapshot.mode_probabilities)


def run_instance(config,model,data,forecast,evaluation_times,models=None,cancel=lambda:False,emit=lambda p:None):
    result=InstanceRun(config=config,model=model)
    history=[]
    began=perf_counter()
    filter=None
    try:
        # A custom model failing to clone is one failed instance, not a failed job.
        model=copy.deepcopy(model)
        result.model=model
        if getattr(model,"_filtervisual_custom",False):
            from filtervisual.models.custom import check_contract
            check_contract(model,model._filtervisual_geometry,config.x0,config.p0)
        filter=make_filter(config,model,models=models)
        frames=data.observations
        cursor=0
        ticks=time_grid(data.truth.duration_s,config.frequency_hz)
        for i,tick in enumerate(ticks):
            if cancel():
                raise RunCancelled()
            pending=[]
            while cursor<len(frames) and frames[cursor].t<=tick+1e-10:
                pending.append(frames[cursor]);cursor+=1
            fresh=[frame for frame in pending if frame.t>=filter.t-1e-10]
            if fresh:
                frame=fresh[-1]
                result.skipped_observation_ids.extend(x.id for x in pending if x is not frame)
                filter.predict(max(0.,frame.t-filter.t))
                update=filter.update(frame)
                result.updates.append(update)
                result.consumed_observation_ids.append(frame.id)
                history.append(filter.snapshot())
                result.forecasts.extend(forecast_after_update(filter,config.id,forecast,cancel))
            else:
                result.skipped_observation_ids.extend(frame.id for frame in pending)
            if tick-filter.t>1e-12:
                filter.predict(tick-filter.t)
            history.append(filter.snapshot())
            if i%16==0 or i==len(ticks)-1:
                emit((i+1)/len(ticks))
    except RunCancelled:
        raise
    except Exception as e:
        result.error=f"{type(e).__name__}: {e}"
    if filter is not None and history:
        times=np.array([x.t for x in history])
        for time in evaluation_times:
            if result.error and time>times[-1]+1e-10:
                break
            index=int(np.searchsorted(times,time+1e-10,side="right")-1)
            if index<0:
                continue
            try:
                result.samples.append(estimate_at(history[index],time,model,filter))
            except Exception as e:
                result.error=f"evaluation: {type(e).__name__}: {e}";break
    result.elapsed_s=perf_counter()-began
    return result
