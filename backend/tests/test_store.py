"""Persistence is a frozen reproducibility snapshot, never executable pickle."""
from hashlib import sha256
from io import BytesIO
import json
import csv
from io import StringIO
from uuid import uuid4
from zipfile import ZipFile

import numpy as np
import pytest

from filtervisual.config.schema import default_experiment
from filtervisual import __version__
from filtervisual.evaluation.report import evaluate_run
from filtervisual.simulation.runner import config_hash, run_experiment
from filtervisual.storage.store import RunStore


def small_config():
    config = default_experiment()
    config.scene.duration_s = .08
    config.scene.simulation_dt = .01
    config.instances = config.instances[:1]
    config.forecast.leads_s = [.02]
    return config


def saved(tmp_path):
    store = RunStore(tmp_path)
    config = small_config()
    run_id = str(uuid4())
    store.create(run_id, config, {"id": run_id, "status": "running", "created_at": "2026-10-15T00:00:00Z"})
    result = run_experiment(config)
    evaluated = evaluate_run(result)
    store.save(run_id, config, result, evaluated)
    return store, run_id, config, evaluated.payload


def test_round_trip_sealed_hashes_and_non_pickle_npz(tmp_path):
    store, run_id, config, payload = saved(tmp_path)
    loaded = store.load(run_id)
    assert loaded.payload == payload
    assert loaded.config == config
    assert loaded.manifest["config_hash"] == config_hash(config)
    assert loaded.manifest["observation_config_hash"] == config_hash(config.observation)
    assert len(loaded.manifest["backend_source"]["sha256"]) == 64
    assert "storage/store.py" in loaded.manifest["backend_source"]["files"]
    assert loaded.manifest["sealed"]
    assert loaded.manifest["versions"]["filtervisual"] == __version__
    for name, digest in loaded.manifest["files"].items():
        assert sha256((store.path(run_id) / name).read_bytes()).hexdigest() == digest
    with np.load(BytesIO(store.export(run_id, "npz")), allow_pickle=False) as arrays:
        assert arrays["instance_0_x"].shape[1] == 11
        assert arrays["instance_0_P"].shape[1:] == (11, 11)
        assert arrays["instance_0_id"].item() == config.instances[0].id
        assert arrays["truth_state"].shape[1] == 11
        assert arrays["instance_0_innovation_S"].shape[0] > 0
        assert arrays["instance_0_nis"].shape[0] > 0
        assert arrays["instance_0_sample_nees"].shape[0] == arrays["instance_0_t"].shape[0]
        for key in arrays.files:
            if np.issubdtype(arrays[key].dtype, np.number) and not key.endswith("_valid"):
                assert key + "_valid" in arrays.files
                np.testing.assert_array_equal(arrays[key + "_valid"], np.isfinite(arrays[key]))
    with np.load(store.path(run_id) / "observations.npz", allow_pickle=False) as arrays:
        assert arrays["values"].shape[0] > 0
        assert arrays["valid"].dtype == bool
    original = (store.path(run_id) / "manifest.json").read_bytes()
    for format in ("json", "csv", "markdown", "npz", "zip"):
        assert store.export(run_id, format)
    assert (store.path(run_id) / "manifest.json").read_bytes() == original
    exported = json.loads(store.export(run_id))
    assert exported["result"] == payload
    with ZipFile(BytesIO(store.export(run_id, "zip"))) as archive:
        assert {"experiment.json", "report.json", "manifest.json", "results.npz", "observations.npz"} <= set(archive.namelist())
    assert "config_hash" in store.export(run_id, "csv").decode("utf-8-sig")


def test_saved_run_cannot_be_overwritten_or_rebound_to_draft(tmp_path):
    store, run_id, config, payload = saved(tmp_path)
    config.seed += 1
    assert store.load(run_id).config.seed != config.seed
    with pytest.raises(FileExistsError, match="immutable"):
        store.save(run_id, config, payload=payload)
    other = str(uuid4())
    store.create(other, config, {"id": other, "created_at": "2026-10-15T00:00:00Z"})
    config.seed += 1
    with pytest.raises(ValueError, match="configuration"):
        store.save(other, config, payload={"report": {}})


def test_rejects_nan_before_result_persistence_and_path_traversal(tmp_path):
    store = RunStore(tmp_path)
    config = small_config()
    run_id = str(uuid4())
    store.create(run_id, config, {"id": run_id, "created_at": "2026-10-15T00:00:00Z"})
    with pytest.raises(ValueError):
        store.save(run_id, config, payload={"value": float("nan")})
    assert not (store.path(run_id) / "payload.json").exists()
    with pytest.raises(KeyError):
        store.path("../../etc/passwd")


def test_tampered_and_unsealed_results_are_rejected(tmp_path):
    store, run_id, _, _ = saved(tmp_path)
    path = store.path(run_id)
    original = (path / "manifest.json").read_text()
    manifest = json.loads(original)
    manifest["sealed"] = False
    (path / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="not sealed"):
        store.load(run_id)
    (path / "manifest.json").write_text(original)
    payload = json.loads((path / "payload.json").read_text())
    payload["config"]["name"] = "modified"
    (path / "payload.json").write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="checksum mismatch"):
        store.load(run_id)


def test_scan_csv_preserves_common_window_evidence(tmp_path):
    from filtervisual.simulation.runner import build_data
    from filtervisual.tuning.scan import scan_noise
    config = small_config()
    data = build_data(config)
    payload = scan_noise(config, config.instances[0].id, "q_scale", [2.], data)
    store, run_id = RunStore(tmp_path), str(uuid4())
    store.create(run_id, config, {"id": run_id, "created_at": "2026-10-15T00:00:00Z"}, kind="noise_scan")
    store.save(run_id, config, payload=payload, data=data)
    rows = list(csv.DictReader(StringIO(store.export(run_id, "csv").decode("utf-8-sig"))))
    common = [row for row in rows if row["metric"] == "common_position_rmse"]
    assert len(common) == 2
    assert [row["candidate"] for row in common] == ["baseline", "candidate_0"]
    for row, score in zip(common, payload["common_comparison"]["scores"]):
        assert float(row["metric_value"]) == score["rmse"]
        assert int(row["valid_samples"]) == payload["common_comparison"]["common_count"]


def test_scan_csv_uses_metric_valid_counts_instead_of_total_grid_samples(tmp_path):
    config = small_config()
    store, run_id = RunStore(tmp_path), str(uuid4())
    payload = dict(type="noise_scan", instance_id="ekf-01", parameter="q_scale", multipliers=[],
                   report={}, candidates=[], baseline=dict(multiplier=1., value=1., report=dict(instances=[dict(
                       instance_id="ekf-01", sample_count=100, position_rmse=None, position_count=0,
                       angle_rmse=.1, angle_count=2,
                   )])))
    store.create(run_id, config, {"id": run_id, "created_at": "2026-10-15T00:00:00Z"}, kind="noise_scan")
    store.save(run_id, config, payload=payload)
    rows = list(csv.DictReader(StringIO(store.export(run_id, "csv").decode("utf-8-sig"))))
    assert {row["metric"]: row["valid_samples"] for row in rows} == {"position_rmse": "0", "angle_rmse": "2"}
