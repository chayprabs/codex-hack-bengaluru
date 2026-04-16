#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any


@dataclass
class StreamSummary:
    event_counts: dict[str, int] = field(default_factory=dict)
    findings_seen: int = 0
    status_updates_seen: int = 0
    score_updates_seen: int = 0
    completion_seen: bool = False

    def note_event(self, event_name: str, payload: dict[str, Any]) -> None:
        self.event_counts[event_name] = self.event_counts.get(event_name, 0) + 1
        if event_name == "finding":
            self.findings_seen += 1
        elif event_name == "agent_status":
            self.status_updates_seen += 1
        elif event_name == "score_update":
            self.score_updates_seen += 1
        elif event_name == "audit_complete":
            self.completion_seen = True


class SmokeCheckError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Quick smoke test for the TrustLayer API stack.",
    )
    parser.add_argument(
        "--api-base-url",
        default="http://127.0.0.1:8000/api",
        help="API base URL including the /api prefix.",
    )
    parser.add_argument(
        "--stream-seconds",
        type=float,
        default=6.0,
        help="How long to consume the audit SSE stream before falling back to polling.",
    )
    parser.add_argument(
        "--poll-seconds",
        type=float,
        default=12.0,
        help="How long to poll the audit endpoint for progress or completion.",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=0.5,
        help="Seconds between audit status polls.",
    )
    parser.add_argument(
        "--request-timeout",
        type=float,
        default=5.0,
        help="Socket timeout in seconds for non-stream HTTP calls.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    api_base_url = args.api_base_url.rstrip("/")

    try:
        health = request_json("GET", build_url(api_base_url, "/health"), timeout=args.request_timeout)
        require(health.get("status") == "ok", "Health endpoint did not report status=ok.")
        print(f"[smoke] health ok: service={health.get('service')} driver={health['database']['driver']}")

        created_audit = request_json(
            "POST",
            build_url(api_base_url, "/demo-audit"),
            timeout=args.request_timeout,
        )
        audit_id = created_audit["id"]
        initial_status = created_audit["status"]
        print(f"[smoke] demo audit created: id={audit_id} status={initial_status}")

        stream_summary = consume_stream(
            build_url(api_base_url, f"/audits/{audit_id}/stream"),
            duration_seconds=args.stream_seconds,
            timeout=min(args.request_timeout, 1.0),
        )
        print(
            "[smoke] stream summary: "
            f"events={stream_summary.event_counts} "
            f"status_updates={stream_summary.status_updates_seen} "
            f"findings={stream_summary.findings_seen} "
            f"score_updates={stream_summary.score_updates_seen} "
            f"completion={stream_summary.completion_seen}"
        )

        final_audit, audit_history = poll_audit(
            build_url(api_base_url, f"/audits/{audit_id}"),
            starting_status=initial_status,
            timeout_seconds=args.poll_seconds,
            interval_seconds=args.poll_interval,
            request_timeout=args.request_timeout,
        )

        history_text = " -> ".join(audit_history)
        print(
            "[smoke] audit progress: "
            f"statuses={history_text} findings={len(final_audit.get('findings', []))} score={final_audit.get('score')}"
        )

        require(
            stream_summary.status_updates_seen > 0
            or stream_summary.findings_seen > 0
            or final_audit["status"] != initial_status,
            "Did not observe agent status updates, findings, or audit state advancement.",
        )
        require(
            stream_summary.findings_seen > 0 or len(final_audit.get("findings", [])) > 0,
            "Did not observe any findings in the stream or final audit payload.",
        )
        require(
            final_audit["status"] == "completed" or final_audit["status"] != initial_status,
            "Audit did not complete or advance beyond its initial state.",
        )
        require(
            0 <= int(final_audit["score"]) <= 100,
            "Final audit score was outside the expected 0-100 range.",
        )

        print("[smoke] PASS")
        return 0
    except KeyboardInterrupt:
        print("\n[smoke] interrupted")
        return 130
    except SmokeCheckError as exc:
        print(f"[smoke] FAIL: {exc}", file=sys.stderr)
        return 1
    except urllib.error.URLError as exc:
        reason = exc.reason if hasattr(exc, "reason") else exc
        print(
            "[smoke] FAIL: could not reach the API. "
            f"Base URL: {api_base_url}. Error: {reason}",
            file=sys.stderr,
        )
        return 1


def build_url(api_base_url: str, path: str) -> str:
    return urllib.parse.urljoin(f"{api_base_url}/", path.lstrip("/"))


def request_json(
    method: str,
    url: str,
    *,
    timeout: float,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body: bytes | None = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(url, data=body, method=method, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw_body = response.read().decode("utf-8")
    return json.loads(raw_body)


def consume_stream(url: str, *, duration_seconds: float, timeout: float) -> StreamSummary:
    deadline = time.monotonic() + duration_seconds
    summary = StreamSummary()
    request = urllib.request.Request(url, headers={"Accept": "text/event-stream"})

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            content_type = response.headers.get("Content-Type", "")
            require(
                content_type.startswith("text/event-stream"),
                f"Stream endpoint returned unexpected content type: {content_type!r}",
            )

            event_name: str | None = None
            data_lines: list[str] = []

            while time.monotonic() < deadline:
                try:
                    raw_line = response.readline()
                except socket.timeout:
                    continue

                if not raw_line:
                    break

                line = raw_line.decode("utf-8").rstrip("\r\n")
                if not line:
                    if event_name and data_lines:
                        payload = json.loads("\n".join(data_lines))
                        if isinstance(payload, dict):
                            summary.note_event(event_name, payload)
                        if summary.completion_seen:
                            break
                    event_name = None
                    data_lines = []
                    continue

                if line.startswith(":"):
                    continue
                if line.startswith("event:"):
                    event_name = line.split(":", 1)[1].strip()
                    continue
                if line.startswith("data:"):
                    data_lines.append(line.split(":", 1)[1].lstrip())
    except TimeoutError:
        pass

    return summary


def poll_audit(
    url: str,
    *,
    starting_status: str,
    timeout_seconds: float,
    interval_seconds: float,
    request_timeout: float,
) -> tuple[dict[str, Any], list[str]]:
    deadline = time.monotonic() + timeout_seconds
    history = [starting_status]
    latest_audit = request_json("GET", url, timeout=request_timeout)
    if latest_audit["status"] != history[-1]:
        history.append(latest_audit["status"])

    while time.monotonic() < deadline:
        if latest_audit["status"] == "completed":
            return latest_audit, history
        if latest_audit["status"] != starting_status and latest_audit.get("findings"):
            return latest_audit, history

        time.sleep(interval_seconds)
        latest_audit = request_json("GET", url, timeout=request_timeout)
        if latest_audit["status"] != history[-1]:
            history.append(latest_audit["status"])

    return latest_audit, history


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeCheckError(message)


if __name__ == "__main__":
    raise SystemExit(main())
