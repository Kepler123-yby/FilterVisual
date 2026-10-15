"""Run both development servers on macOS and Linux using the Python stdlib."""

import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def signal_group(process: subprocess.Popen, signum: int) -> bool:
    try:
        os.killpg(process.pid, signum)
        return True
    except ProcessLookupError:
        return False


def cleanup(processes: list[subprocess.Popen]) -> None:
    for process in processes:
        signal_group(process, signal.SIGTERM)
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        for process in processes:
            process.poll()  # Reap exited leaders before checking their groups.
        if not any(signal_group(process, 0) for process in processes):
            break
        time.sleep(0.05)
    for process in processes:
        # npm may exit before its Vite child; clean the group even then.
        signal_group(process, signal.SIGKILL)
        process.wait()


def supervise(commands: list[list[str]], cwd: Path, message: str = "") -> int:
    processes: list[subprocess.Popen] = []
    stop_signal = 0

    def request_stop(signum, _frame):
        nonlocal stop_signal
        stop_signal = signum

    previous = {
        signum: signal.signal(signum, request_stop)
        for signum in (signal.SIGINT, signal.SIGTERM)
    }
    try:
        for command in commands:
            if stop_signal:
                return 128 + stop_signal
            # POSIX sessions provide process groups without a setsid executable.
            processes.append(subprocess.Popen(command, cwd=cwd, start_new_session=True))
        if message:
            print(message, flush=True)
        while not stop_signal:
            for process in processes:
                status = process.poll()
                if status is not None:
                    return status if status >= 0 else 128 - status
            time.sleep(0.1)
        return 128 + stop_signal
    except OSError as error:
        print(f"FilterVisual 启动失败：{error}", file=sys.stderr)
        return 127
    finally:
        cleanup(processes)
        for signum, handler in previous.items():
            signal.signal(signum, handler)


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    api_port = os.environ.get("FILTERVISUAL_API_PORT", "8000")
    web_port = os.environ.get("FILTERVISUAL_WEB_PORT", "5173")
    os.environ["FILTERVISUAL_API_PORT"] = api_port
    os.environ["PYTHONPATH"] = str(root / "backend" / "src")
    return supervise(
        [
            [sys.executable, "-m", "uvicorn", "filtervisual.service.app:app",
             "--host", "127.0.0.1", "--port", api_port],
            ["npm", "--prefix", "web", "run", "dev", "--", "--port", web_port,
             "--strictPort"],
        ],
        root,
        f"FilterVisual: http://127.0.0.1:{web_port}",
    )


if __name__ == "__main__":
    sys.exit(main())
