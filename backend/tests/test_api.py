"""Run the actual spawned worker, query immutable results, and stop bad jobs."""
from hashlib import sha256
import json
from pathlib import Path
import time

from fastapi.testclient import TestClient
import pytest

from filtervisual.config.schema import ModelDefinition, default_experiment
from filtervisual.service.app import create_app


def small_config():
    config = default_experiment()
    config.scene.duration_s = .08
    config.scene.simulation_dt = .01
    config.instances = config.instances[:1]
    config.forecast.leads_s = [.02]
    return config


def poll(client, run_id, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        row = client.get(f"/api/runs/{run_id}").json()
        if row["status"] not in ("queued", "running"):
            return row
        time.sleep(.04)
    raise AssertionError(f"job did not complete: {row}")


def submit(client, config):
    response = client.post("/api/runs", json=config.model_dump())
    assert response.status_code == 202, response.text
    return response.json()["id"]


def test_invalid_run_has_actionable_field_path(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        config = small_config()
        config.instances[0].frequency_hz = 0
        response = client.post("/api/runs", json=config.model_dump())
        assert response.status_code == 422
        assert "frequency_hz" in response.text
        assert client.get("/api/runs").json() == []
        assert client.get("/api/runs/not-a-uuid").status_code == 404
        assert client.get("/api/health").json()["worker_count"] == 1
        assert client.get("/api/default-config").json()["scene"]["duration_s"] == 12


def test_real_worker_result_series_exports_and_restart(tmp_path):
    app = create_app(tmp_path)
    with TestClient(app) as client:
        config = small_config()
        run_id = submit(client, config)
        assert client.get(f"/api/runs/{run_id}/result").status_code == 409
        status = poll(client, run_id)
        assert status["status"] == "completed", status
        assert status["progress"] == 1
        result = client.get(f"/api/runs/{run_id}/result").json()
        assert result["instances"][0]["samples"]
        assert client.get(f"/api/runs/{run_id}/report").json() == result["report"]
        name = result["instances"][0]["state_names"][0]
        response = client.get(f"/api/runs/{run_id}/series", params={"instance": config.instances[0].id, "state": name, "limit": 2})
        assert response.status_code == 200
        rows = response.json()
        assert len(rows["items"]) == 2 and rows["next_offset"] == 2
        assert rows["items"][0]["value"] == result["instances"][0]["samples"][0]["x"][0]
        forecasts = client.get(f"/api/runs/{run_id}/series", params={"kind": "forecasts", "lead": .02}).json()
        assert forecasts["total"] > 0
        manifest = Path(tmp_path) / "runs" / run_id / "manifest.json"
        original = sha256(manifest.read_bytes()).hexdigest()
        for format in ("json", "csv", "markdown", "npz", "zip"):
            response = client.get(f"/api/runs/{run_id}/export", params={"format": format})
            assert response.status_code == 200 and response.content
        assert sha256(manifest.read_bytes()).hexdigest() == original
        config.seed += 1
        assert client.get(f"/api/runs/{run_id}/config").json()["seed"] != config.seed
    # Simulate exiting after the worker seals files but before the parent
    # acknowledges its completion message. The valid finished result survives.
    stale = app.state.jobs.status(run_id).model_dump()
    stale["status"] = "running"
    app.state.store.update_status(run_id, stale)
    with TestClient(create_app(tmp_path)) as client:
        assert client.get(f"/api/runs/{run_id}").json()["status"] == "completed"
        assert client.get(f"/api/runs/{run_id}/result").json() == result


def test_custom_source_error_preserves_healthy_instance(tmp_path):
    config = small_config()
    config.models.append(ModelDefinition(id="bad", kind="python", source="def build_model(params, geometry):\n    raise ValueError('bad equation')"))
    bad = config.instances[0].model_copy(deep=True)
    bad.id = "bad-instance"
    bad.model_id = "bad"
    config.instances.append(bad)
    with TestClient(create_app(tmp_path)) as client:
        run_id = submit(client, config)
        assert poll(client, run_id)["status"] == "completed"
        instances = client.get(f"/api/runs/{run_id}/result").json()["instances"]
        assert instances[0]["status"] == "completed"
        assert instances[1]["status"] == "failed"
        assert "bad equation" in instances[1]["error"]
        source = client.get("/api/models/template").json()["source"]
        response = client.post("/api/models/validate", json={"definition": {"id": "custom", "kind": "python", "source": source}})
        assert response.status_code == 200 and response.json()["valid"], response.text
        response = client.post("/api/models/validate", json={"definition": {"id": "custom", "kind": "python", "source": "x = ("}})
        assert not response.json()["valid"] and response.json()["issues"][0]["line"] == 1


def test_scan_and_monte_carlo_are_children_and_preserve_baseline(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        config = small_config()
        run_id = submit(client, config)
        assert poll(client, run_id)["status"] == "completed"
        original = client.get(f"/api/runs/{run_id}/result").content
        response = client.post(f"/api/runs/{run_id}/scan", json={"instance_id": config.instances[0].id, "parameter": "q_scale", "multipliers": [.5, 2.]})
        assert response.status_code == 202
        child = response.json()
        assert child["parent_id"] == run_id and child["kind"] == "noise_scan"
        assert poll(client, child["id"])["status"] == "completed"
        result = client.get(f"/api/runs/{child['id']}/result").json()
        assert len(result["candidates"]) == 2 and result["observation_hash"]
        csv = client.get(f"/api/runs/{child['id']}/export", params={"format": "csv"}).content.decode("utf-8-sig")
        assert "position_rmse,m," in csv and len(csv.splitlines()) > 3
        response = client.post(f"/api/runs/{run_id}/monte-carlo", json={"trials": 2, "seeds": [42, 43]})
        assert response.status_code == 202
        child = response.json()
        assert poll(client, child["id"])["status"] == "completed"
        result = client.get(f"/api/runs/{child['id']}/result").json()
        assert result["trials"] == 2 and result["groups"]
        csv = client.get(f"/api/runs/{child['id']}/export", params={"format": "csv"}).content.decode("utf-8-sig")
        assert "dimensionless" in csv and "valid_trials" in csv and len(csv.splitlines()) > 2
        assert original == client.get(f"/api/runs/{run_id}/result").content
        assert client.post(f"/api/runs/{run_id}/scan", json={"instance_id": "unknown", "parameter": "q_scale", "multipliers": [1]}).status_code == 422
        assert client.post(f"/api/runs/{run_id}/monte-carlo", json={"trials": 2, "seeds": [1, 1]}).status_code == 422


def test_running_and_queued_cancellation(tmp_path):
    config = small_config()
    config.models.append(ModelDefinition(id="loop", kind="python", source="while True:\n    pass"))
    with TestClient(create_app(tmp_path, timeout_s=10)) as client:
        first = submit(client, config)
        deadline = time.monotonic() + 3
        while client.get(f"/api/runs/{first}").json()["status"] != "running" and time.monotonic() < deadline:
            time.sleep(.02)
        second = submit(client, small_config())
        assert client.get(f"/api/runs/{second}").json()["status"] == "queued"
        assert client.post(f"/api/runs/{second}/cancel").json()["status"] == "cancelled"
        client.post(f"/api/runs/{first}/cancel")
        assert poll(client, first)["status"] == "cancelled"
        assert client.get(f"/api/runs/{first}/result").status_code == 409
    with TestClient(create_app(tmp_path)) as client:
        assert client.get(f"/api/runs/{first}").json()["status"] == "cancelled"
        assert client.get(f"/api/runs/{second}").json()["status"] == "cancelled"


def test_worker_timeout_is_persisted_and_next_run_can_start(tmp_path):
    config = small_config()
    config.models.append(ModelDefinition(id="loop", kind="python", source="while True:\n    pass"))
    with TestClient(create_app(tmp_path, timeout_s=.2)) as client:
        run_id = submit(client, config)
        status = poll(client, run_id)
        assert status["status"] == "timed_out" and "0.2" in status["error"]
        assert client.get(f"/api/runs/{run_id}/result").status_code == 409
    with TestClient(create_app(tmp_path, timeout_s=10)) as client:
        assert client.get(f"/api/runs/{run_id}").json()["status"] == "timed_out"
        assert poll(client, submit(client, small_config()))["status"] == "completed"


def test_spa_is_optional_and_does_not_hide_unknown_api(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>FilterVisual</html>")
    with TestClient(create_app(tmp_path / "data", web_dir=dist)) as client:
        assert "FilterVisual" in client.get("/").text
        assert "FilterVisual" in client.get("/experiment/example").text
        assert client.get("/api/missing").status_code == 404
        assert client.get("/api/health").status_code == 200
