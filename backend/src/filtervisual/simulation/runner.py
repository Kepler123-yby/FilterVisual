"""Reproducible experiment orchestration without UI or storage dependencies."""
from __future__ import annotations

from hashlib import sha256
import json
import numpy as np

from filtervisual.config.validation import validate_experiment
from filtervisual.core.types import InstanceRun, RunProgress, RunResult, SimulationData, RunCancelled
from filtervisual.models.registry import make_model
from filtervisual.scene.motion import build_truth
from filtervisual.scene.observations import generate_observations
from filtervisual.simulation.scheduler import run_instance,time_grid


def config_hash(value):
    if hasattr(value,"model_dump"):
        value=value.model_dump()
    return sha256(json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()


def build_data(config):
    truth=build_truth(config.scene,config.seed)
    observations=generate_observations(truth,config.observation,config.seed)
    scene_hash=config_hash({"scene":config.scene.model_dump(),"seed":config.seed})
    digest=sha256()
    for frame in observations:
        digest.update(str((frame.t,frame.context.plate_ids,frame.id)).encode())
        digest.update(frame.values.tobytes())
    return SimulationData(truth,observations,scene_hash,digest.hexdigest(),
                          config_hash({"observation":config.observation.model_dump(),"seed":config.seed}))


def run_experiment(config,cancel=lambda:False,emit=lambda p:None):
    config=config.model_copy(deep=True)
    issues=validate_experiment(config)
    if issues:
        raise ValueError("; ".join(x.path+": "+x.message for x in issues))
    emit(RunProgress("truth"))
    data=build_data(config)
    times=time_grid(config.scene.duration_s,config.evaluation.frequency_hz)
    models={};model_errors={}
    for definition in config.models:
        try:
            models[definition.id]=make_model(definition,config.scene.geometry)
        except Exception as e:
            model_errors[definition.id]=str(e)
    instances=[]
    enabled=[x for x in config.instances if x.enabled]
    for i,instance in enumerate(enabled):
        if cancel():
            raise RunCancelled()
        if instance.model_id not in models:
            result=InstanceRun(config=instance,model=None,error=model_errors.get(instance.model_id,"model not found"))
        else:
            def progress(fraction):
                emit(RunProgress("filtering",i,len(enabled),int((i+fraction)*1000),len(enabled)*1000))
            result=run_instance(instance,models[instance.model_id],data,config.forecast,times,
                                models=models,cancel=cancel,emit=progress)
        instances.append(result)
        emit(RunProgress("filtering",i+1,len(enabled),(i+1)*1000,len(enabled)*1000))
    return RunResult(config,data,instances,times)
