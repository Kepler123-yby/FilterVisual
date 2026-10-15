"""Exercise launcher signals and descendant cleanup in real process groups."""

import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time

import pytest


LAUNCHER = Path(__file__).resolve().parents[2] / "scripts" / "dev.py"
LISTENER = """
import json, signal, socket, sys, time
from pathlib import Path
signal.signal(signal.SIGTERM, signal.SIG_IGN)
with socket.socket() as server:
    server.bind(('127.0.0.1', 0))
    server.listen()
    Path(sys.argv[1]).write_text(json.dumps(server.getsockname()[1]))
    while True:
        time.sleep(0.1)
"""


def launch(tmp_path, exit_first=None):
    ready = tmp_path / "ready.json"
    # The parent exits on TERM but its child deliberately ignores TERM.
    server = [sys.executable, "-c",
              "import subprocess, sys, time; "
              "subprocess.Popen(sys.argv[1:]); time.sleep(60)",
              sys.executable, "-c", LISTENER, str(ready)]
    commands = [server]
    if exit_first is not None:
        failure = [sys.executable, "-c",
                   "import pathlib, sys, time; p = pathlib.Path(sys.argv[1]); "
                   "\nwhile not p.exists(): time.sleep(0.01)\nsys.exit(7)", str(ready)]
        commands = [failure, server] if exit_first else [server, failure]
    runner = (
        "import json, pathlib, runpy, sys; "
        "launcher = runpy.run_path(sys.argv[1]); "
        "sys.exit(launcher['supervise'](json.loads(sys.argv[2]), pathlib.Path.cwd()))"
    )
    process = subprocess.Popen([sys.executable, "-c", runner, str(LAUNCHER),
                                json.dumps(commands)])
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if ready.exists() and ready.read_text():
            return process, json.loads(ready.read_text())
        if process.poll() is not None:
            pytest.fail(f"Launcher exited before child was ready: {process.returncode}")
        time.sleep(0.02)
    process.terminate()
    process.wait(timeout=10)
    pytest.fail("Child did not become ready")


def assert_port_closed(port):
    with socket.socket() as client:
        client.settimeout(1)
        assert client.connect_ex(("127.0.0.1", port)) != 0


@pytest.mark.parametrize("signum", [signal.SIGINT, signal.SIGTERM])
def test_launcher_signal_stops_descendants(tmp_path, signum):
    process, port = launch(tmp_path)
    try:
        os.kill(process.pid, signum)
        assert process.wait(timeout=10) == 128 + signum
        assert_port_closed(port)
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=10)


@pytest.mark.parametrize("exit_first", [True, False])
def test_either_server_failure_stops_peer_descendants(tmp_path, exit_first):
    process, port = launch(tmp_path, exit_first)
    try:
        assert process.wait(timeout=10) == 7
        assert_port_closed(port)
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=10)
