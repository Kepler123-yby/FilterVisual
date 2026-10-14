from pathlib import Path
from filtervisual.config.schema import ModelDefinition
from filtervisual.models.custom import check_contract,load_model
from filtervisual.simulation.runner import run_experiment
from filtervisual.evaluation.report import evaluate_run


def test_reduced_xy_model_runs_and_nees_is_only_four_states(baseline_config):
    source=(Path(__file__).resolve().parents[2]/"examples/models/reduced_xy.py").read_text()
    c=baseline_config
    c.scene.duration_s=.1;c.scene.rotation.terms=[]
    c.scene.translation.mode="constant"
    c.models=[ModelDefinition(id="xy",kind="python",source=source)]
    c.instances=c.instances[:2]
    for instance in c.instances:
        instance.model_id="xy";instance.x0=[0,0,0,0]
        instance.p0=[[1 if i==j else 0 for j in range(4)] for i in range(4)]
    model=load_model(source,{},c.scene.geometry)
    assert check_contract(model,c.scene.geometry)["dimension"]==4
    payload=evaluate_run(run_experiment(c)).payload
    for instance in payload["instances"]:
        assert instance["status"]=="completed"
        assert instance["samples"][-1]["nees"]["dof"]==4
        assert instance["samples"][-1]["physical"]["armor_positions"] is None
