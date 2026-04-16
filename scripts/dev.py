#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "apps" / "web"
API_DIR = ROOT_DIR / "apps" / "api"
DEV_STATE_PATH = ROOT_DIR / ".trustlayer-dev.json"

API_HOST = "127.0.0.1"
DEFAULT_API_PORT = 8000
MAX_API_PORT_SEARCH = 20


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


def find_node() -> str:
    candidates = ["node.exe", "node"] if os.name == "nt" else ["node"]
    for candidate in candidates:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    raise SystemExit("Could not find node. Install Node.js first.")


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
    next_cli = WEB_DIR / "node_modules" / "next" / "dist" / "bin" / "next"
    if next_cli.exists():
        return [find_node(), str(next_cli), "dev"]
    return [find_npm(), "run", "dev"]


def _is_port_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def _can_connect(host: str, port: int, timeout: float = 0.25) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        try:
            sock.connect((host, port))
        except OSError:
            return False
    return True


def build_api_base_url(api_port: int) -> str:
    return f"http://{API_HOST}:{api_port}/api"


def _dev_state_payload(*, token: str, api_port: int) -> dict[str, object]:
    return {
        "token": token,
        "api_port": api_port,
        "api_base_url": build_api_base_url(api_port),
        "updated_at": int(time.time()),
    }


def write_dev_state(*, token: str, api_port: int) -> None:
    DEV_STATE_PATH.write_text(
        json.dumps(_dev_state_payload(token=token, api_port=api_port), indent=2),
        encoding="utf-8",
    )


def read_dev_state() -> dict[str, object] | None:
    if not DEV_STATE_PATH.exists():
        return None

    try:
        raw_payload = json.loads(DEV_STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    if not isinstance(raw_payload, dict):
        return None

    return raw_payload


def clear_dev_state(*, token: str) -> None:
    payload = read_dev_state()
    if not payload or payload.get("token") != token:
        return

    try:
        DEV_STATE_PATH.unlink()
    except FileNotFoundError:
        return


def resolve_web_api_base_url() -> str | None:
    explicit_base_url = os.getenv("NEXT_PUBLIC_API_BASE_URL", "").strip()
    if explicit_base_url:
        return explicit_base_url.rstrip("/")

    configured_port = os.getenv("TRUSTLAYER_API_PORT", "").strip()
    if configured_port:
        try:
            return build_api_base_url(int(configured_port))
        except ValueError:
            raise SystemExit(
                f"TRUSTLAYER_API_PORT must be a valid integer, received: {configured_port!r}"
            )

    state = read_dev_state()
    if not state:
        return None

    api_port = state.get("api_port")
    if not isinstance(api_port, int):
        return None

    updated_at = state.get("updated_at")
    is_fresh_state = isinstance(updated_at, int) and (int(time.time()) - updated_at) <= 120
    if not is_fresh_state and not _can_connect(API_HOST, api_port):
        return None

    api_base_url = state.get("api_base_url")
    if isinstance(api_base_url, str) and api_base_url.strip():
        return api_base_url.rstrip("/")

    return build_api_base_url(api_port)


def wait_for_port(
    host: str,
    port: int,
    *,
    timeout_seconds: float = 20.0,
    process: subprocess.Popen[str] | None = None,
) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if _can_connect(host, port):
            return True

        if process is not None and process.poll() is not None:
            return False

        time.sleep(0.2)

    return _can_connect(host, port)


def resolve_api_port() -> int:
    configured_port = os.getenv("TRUSTLAYER_API_PORT")
    if configured_port:
        try:
            return int(configured_port)
        except ValueError as exc:
            raise SystemExit(
                f"TRUSTLAYER_API_PORT must be a valid integer, received: {configured_port!r}"
            ) from exc

    for port in range(DEFAULT_API_PORT, DEFAULT_API_PORT + MAX_API_PORT_SEARCH):
        if _is_port_available(API_HOST, port):
            return port

    raise SystemExit(
        f"Could not find an available API port between {DEFAULT_API_PORT} and "
        f"{DEFAULT_API_PORT + MAX_API_PORT_SEARCH - 1}."
    )


def build_api_command(api_port: int, *, reload: bool = True) -> list[str]:
    command = [
        find_api_python(),
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        API_HOST,
        "--port",
        str(api_port),
    ]
    if reload:
        command.insert(4, "--reload")
    return command


def print_launch(label: str, command: list[str], cwd: Path) -> None:
    print(f"[trustlayer] {label}: {format_command(command)}", flush=True)
    print(f"[trustlayer] cwd: {cwd}", flush=True)


def run_single(
    label: str,
    command: list[str],
    cwd: Path,
    *,
    env: dict[str, str] | None = None,
) -> int:
    print_launch(label, command, cwd)
    return subprocess.call(command, cwd=cwd, env=env)


def spawn_process(
    command: list[str],
    cwd: Path,
    *,
    env: dict[str, str] | None = None,
) -> subprocess.Popen[str]:
    kwargs: dict[str, object] = {"cwd": cwd, "env": env}
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
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
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
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        os.killpg(process.pid, signal.SIGKILL)
    process.wait(timeout=5)
    print(f"[trustlayer] stopped {label}", flush=True)


def run_both() -> int:
    api_port = resolve_api_port()
    if api_port != DEFAULT_API_PORT:
        print(
            f"[trustlayer] api port {DEFAULT_API_PORT} is unavailable; using {api_port} instead.",
            flush=True,
        )

    web_env = os.environ.copy()
    web_env["NEXT_PUBLIC_API_BASE_URL"] = build_api_base_url(api_port)
    state_token = str(uuid.uuid4())
    write_dev_state(token=state_token, api_port=api_port)

    print(
        "[trustlayer] web will use NEXT_PUBLIC_API_BASE_URL="
        f"{web_env['NEXT_PUBLIC_API_BASE_URL']}",
        flush=True,
    )

    processes: list[tuple[str, subprocess.Popen[str]]] = []
    try:
        api_command = build_api_command(api_port, reload=False)
        print_launch("api", api_command, API_DIR)
        api_process = spawn_process(api_command, API_DIR)
        processes.append(("api", api_process))

        print(
            f"[trustlayer] waiting for api on http://{API_HOST}:{api_port}/api ...",
            flush=True,
        )
        if not wait_for_port(API_HOST, api_port, process=api_process):
            print(
                f"[trustlayer] api did not become ready on port {api_port}.",
                flush=True,
            )
            return api_process.poll() or 1

        web_command = build_web_command()
        print_launch("web", web_command, WEB_DIR)
        processes.append(("web", spawn_process(web_command, WEB_DIR, env=web_env)))

        while True:
            for label, process in processes:
                exit_code = process.poll()
                if exit_code is None:
                    continue

                print(f"[trustlayer] {label} exited with code {exit_code}", flush=True)
                for other_label, other_process in processes:
                    if other_process is not process:
                        stop_process(other_label, other_process)
                return exit_code

            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n[trustlayer] stopping web and api...", flush=True)
        for label, process in processes:
            stop_process(label, process)
        return 130
    finally:
        clear_dev_state(token=state_token)


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
        web_env = os.environ.copy()
        resolved_base_url = resolve_web_api_base_url()
        if resolved_base_url:
            web_env["NEXT_PUBLIC_API_BASE_URL"] = resolved_base_url
            print(
                "[trustlayer] web will use NEXT_PUBLIC_API_BASE_URL="
                f"{resolved_base_url}",
                flush=True,
            )
        return run_single("web", build_web_command(), WEB_DIR, env=web_env)

    if args.target == "api":
        api_port = resolve_api_port()
        if api_port != DEFAULT_API_PORT:
            print(
                f"[trustlayer] api port {DEFAULT_API_PORT} is unavailable; using {api_port} instead.",
                flush=True,
            )
        state_token = str(uuid.uuid4())
        write_dev_state(token=state_token, api_port=api_port)
        try:
            return run_single("api", build_api_command(api_port), API_DIR)
        finally:
            clear_dev_state(token=state_token)

    return run_both()


if __name__ == "__main__":
    raise SystemExit(main())
