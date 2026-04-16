#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shlex
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "apps" / "web"
API_DIR = ROOT_DIR / "apps" / "api"

API_HOST = "127.0.0.1"
API_PORT = "8000"


def format_command(command: list[str]) -> str:
    if os.name == "nt":
        return subprocess.list2cmdline(command)
    return shlex.join(command)


def find_npm() -> str:
    candidates = ["npm.cmd", "npm"] if os.name == "nt" else ["npm"]
    for candidate in candidates:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    raise SystemExit("Could not find npm. Install Node.js and npm first.")


def find_api_python() -> str:
    candidates = [
        API_DIR / ".venv" / "Scripts" / "python.exe",
        API_DIR / ".venv" / "bin" / "python",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return sys.executable


def build_web_command() -> list[str]:
    return [find_npm(), "run", "dev"]


def build_api_command() -> list[str]:
    return [
        find_api_python(),
        "-m",
        "uvicorn",
        "app.main:app",
        "--reload",
        "--host",
        API_HOST,
        "--port",
        API_PORT,
    ]


def print_launch(label: str, command: list[str], cwd: Path) -> None:
    print(f"[trustlayer] {label}: {format_command(command)}")
    print(f"[trustlayer] cwd: {cwd}")


def run_single(label: str, command: list[str], cwd: Path) -> int:
    print_launch(label, command, cwd)
    return subprocess.call(command, cwd=cwd)


def spawn_process(command: list[str], cwd: Path) -> subprocess.Popen[str]:
    kwargs: dict[str, object] = {"cwd": cwd}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(command, **kwargs)


def stop_process(label: str, process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return

    try:
        if os.name == "nt":
            process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            os.killpg(process.pid, signal.SIGTERM)
    except Exception:
        process.terminate()

    try:
        process.wait(timeout=5)
        return
    except subprocess.TimeoutExpired:
        pass

    if os.name == "nt":
        process.kill()
    else:
        os.killpg(process.pid, signal.SIGKILL)
    process.wait(timeout=5)
    print(f"[trustlayer] stopped {label}")


def run_both() -> int:
    commands = [
        ("api", build_api_command(), API_DIR),
        ("web", build_web_command(), WEB_DIR),
    ]

    processes: list[tuple[str, subprocess.Popen[str]]] = []
    try:
        for label, command, cwd in commands:
            print_launch(label, command, cwd)
            processes.append((label, spawn_process(command, cwd)))

        while True:
            for label, process in processes:
                exit_code = process.poll()
                if exit_code is None:
                    continue

                print(f"[trustlayer] {label} exited with code {exit_code}")
                for other_label, other_process in processes:
                    if other_process is not process:
                        stop_process(other_label, other_process)
                return exit_code

            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n[trustlayer] stopping web and api...")
        for label, process in processes:
            stop_process(label, process)
        return 130


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run TrustLayer local development servers.",
    )
    parser.add_argument(
        "target",
        nargs="?",
        default="both",
        choices=("web", "api", "both"),
        help="Choose which app to run.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.target == "web":
        return run_single("web", build_web_command(), WEB_DIR)

    if args.target == "api":
        return run_single("api", build_api_command(), API_DIR)

    return run_both()


if __name__ == "__main__":
    raise SystemExit(main())
