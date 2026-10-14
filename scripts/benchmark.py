#!/usr/bin/env python3
"""Measure a real experiment and hash numerical arrays, excluding wall-clock data."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import resource
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"backend"/"src"))
import numpy as np
from filtervisual.config.schema import ExperimentConfig
from filtervisual.simulation.runner import run_experiment
from filtervisual.evaluation.report import evaluate_run


def numerical_hash(result):
    digest=hashlib.sha256()
    for frame in result.data.observations:
        digest.update(np.asarray([frame.t],dtype="<f8").tobytes())
        digest.update(np.asarray(frame.values,dtype="<f8").tobytes())
    for instance in result.instances:
        digest.update(instance.config.id.encode())
        for sample in instance.samples:
            for array in ([sample.t],sample.x,sample.P):
                digest.update(np.asarray(array,dtype="<f8").tobytes())
        for record in instance.forecasts:
            for array in ([record.origin_time,record.target_time],record.state,record.P):
                digest.update(np.asarray(array,dtype="<f8").tobytes())
    return digest.hexdigest()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--config",default="examples/baseline.json")
    parser.add_argument("--repeat",type=int,default=1)
    args=parser.parse_args()
    config=ExperimentConfig.model_validate_json(Path(args.config).read_text())
    hashes=[]
    for repeat in range(args.repeat):
        started=time.perf_counter()
        result=run_experiment(config)
        payload=evaluate_run(result).payload
        digest=numerical_hash(result);hashes.append(digest)
        print(json.dumps(dict(config=args.config,repeat=repeat+1,duration_s=config.scene.duration_s,
            instances=len(result.instances),updates=sum(len(x.updates) for x in result.instances),
            forecasts=sum(len(x.forecasts) for x in result.instances),
            elapsed_s=round(time.perf_counter()-started,3),peak_memory_mb=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,1),
            numerical_sha256=digest,errors={x.config.id:x.error for x in result.instances if x.error},
            summary=payload["report"]["summary"]),ensure_ascii=False))
    if len(set(hashes))>1:
        raise SystemExit("同配置数值 hash 不一致")


if __name__=="__main__":
    main()
