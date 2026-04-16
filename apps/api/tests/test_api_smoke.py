from __future__ import annotations

import asyncio
import unittest
from contextlib import ExitStack
from typing import Any
from unittest.mock import patch

from support import ensure_api_path

ensure_api_path()

from fastapi import status
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.db import DatabaseRuntime
from app.main import create_app
from app.api.routes.audits import stream_audit
from app.models import AgentStatus, Audit, Finding
from app.services.audit_service import AuditService


class StubAuditRunner:
    def __init__(self) -> None:
        self.started_audits: list[tuple[str, str]] = []

    def build_initial_agents(self) -> list[AgentStatus]:
        return [
            AgentStatus(name="planner"),
            AgentStatus(name="scanner"),
            AgentStatus(name="verifier"),
        ]

    def start(self, audit_id: str, *, mode: str = "live") -> None:
        self.started_audits.append((audit_id, mode))


class ApiSmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.stack = ExitStack()
        self.runtime = DatabaseRuntime("memory://")
        self.runner = StubAuditRunner()
        self.audit_service = AuditService(
            repository=self.runtime.audit_repository,
            runner=self.runner,
            demo_repo_url="https://github.com/example/demo-repo",
        )

        self.stack.enter_context(patch("app.api.routes.audits.audit_service", self.audit_service))
        self.stack.enter_context(patch("app.api.routes.wall.audit_service", self.audit_service))

        self.client = self.stack.enter_context(TestClient(create_app()))

    def tearDown(self) -> None:
        self.stack.close()

    def test_health_endpoint_reports_service_status(self) -> None:
        response = self.client.get("/api/health")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.json(),
            {
                "status": "ok",
                "service": "trustlayer-api",
            },
        )

    def test_root_endpoint_reports_service_metadata(self) -> None:
        response = self.client.get("/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.json(),
            {
                "name": "TrustLayer API",
                "docs": "/docs",
            },
        )

    def test_create_audit_returns_created_audit(self) -> None:
        repo_url = "https://github.com/acme/platform"

        response = self.client.post("/api/audits", json={"repo_url": repo_url})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        payload = response.json()
        self.assertEqual(payload["repo_url"], repo_url)
        self.assertEqual(payload["audit_mode"], "fast")
        self.assertEqual(payload["status"], "queued")
        self.assertEqual(
            [agent["name"] for agent in payload["agents"]],
            ["planner", "scanner", "verifier"],
        )
        self.assertIn((payload["id"], "live"), self.runner.started_audits)

    def test_create_audit_accepts_deep_mode(self) -> None:
        response = self.client.post(
            "/api/audits",
            json={"repo_url": "https://github.com/acme/platform", "audit_mode": "deep"},
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.json()["audit_mode"], "deep")

    def test_create_audit_normalizes_supported_github_repo_urls(self) -> None:
        response = self.client.post(
            "/api/audits",
            json={"repo_url": "https://www.github.com/acme/platform.git"},
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.json()["repo_url"], "https://github.com/acme/platform")

    def test_create_audit_rejects_non_github_repo_urls(self) -> None:
        response = self.client.post(
            "/api/audits",
            json={"repo_url": "https://example.com/acme/platform"},
        )

        self.assertEqual(response.status_code, status.HTTP_422_UNPROCESSABLE_CONTENT)
        payload = response.json()
        self.assertIn("detail", payload)
        self.assertIn("github.com", payload["detail"][0]["msg"].lower())

    def test_create_demo_audit_uses_configured_demo_repo(self) -> None:
        response = self.client.post("/api/demo-audit")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        payload = response.json()
        self.assertEqual(payload["repo_url"], "https://github.com/example/demo-repo")
        self.assertEqual(payload["audit_mode"], "deep")
        self.assertEqual(payload["status"], "queued")
        self.assertIn((payload["id"], "demo"), self.runner.started_audits)

    def test_create_demo_audit_accepts_profile_key(self) -> None:
        response = self.client.post("/api/demo-audit?profile_key=tenant-portal")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        payload = response.json()
        self.assertEqual(payload["repo_url"], "https://github.com/trustlayer-demo/workspace-portal")
        self.assertEqual(payload["audit_mode"], "deep")
        self.assertIn((payload["id"], "demo"), self.runner.started_audits)

    def test_demo_setup_exposes_flagship_path_and_backup_profiles(self) -> None:
        response = self.client.get("/api/demo-setup")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertEqual(payload["primary_demo_repo_url"], "https://github.com/example/demo-repo")
        self.assertIn("replay sync", payload["stream_backup_summary"].lower())
        self.assertGreaterEqual(len(payload["profiles"]), 5)

        flagship = next(profile for profile in payload["profiles"] if profile["is_flagship"])
        self.assertEqual(flagship["repo_url"], "https://github.com/example/demo-repo")
        self.assertEqual(flagship["label"], "Acme subscriptions platform")
        self.assertEqual(flagship["score_journey"][0], 100)
        self.assertEqual(flagship["final_score"], 57)
        self.assertEqual(flagship["final_coverage"], 92)
        self.assertGreaterEqual(flagship["finding_count"], 5)

    def test_get_audit_returns_created_audit(self) -> None:
        created_audit = self._create_audit()

        response = self.client.get(f"/api/audits/{created_audit['id']}")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json(), created_audit)

    def test_stream_endpoint_exposes_sse_content_type(self) -> None:
        created_audit = self._create_audit()
        request = Request(
            {
                "type": "http",
                "asgi": {"version": "3.0"},
                "http_version": "1.1",
                "method": "GET",
                "scheme": "http",
                "path": f"/api/audits/{created_audit['id']}/stream",
                "raw_path": f"/api/audits/{created_audit['id']}/stream".encode("utf-8"),
                "query_string": b"",
                "headers": [],
                "client": ("testclient", 50000),
                "server": ("testserver", 80),
            },
            self._receive,
        )

        # TestClient waits on the open-ended SSE body, so inspect the route response directly.
        response = asyncio.run(stream_audit(created_audit["id"], request))
        first_chunk = asyncio.run(self._read_first_chunk(response))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.headers["content-type"].startswith("text/event-stream"))
        self.assertEqual(response.headers["cache-control"], "no-cache")
        self.assertEqual(response.headers["x-accel-buffering"], "no")
        self.assertIn(f'"audit_id":"{created_audit["id"]}"', first_chunk)
        self.assertIn("event: agent_status", first_chunk)

    def test_wall_endpoint_returns_flattened_finding_entries(self) -> None:
        audit = Audit(
            id="wall-audit",
            repo_url="https://github.com/acme/example",
            status="completed",
            score=82,
            agents=self.runner.build_initial_agents(),
            findings=[
                Finding(
                    severity="high",
                    title="Unsigned webhook path",
                    agent_name="webhook",
                    check_name="missing_signature_verification",
                    files=["app/routes/webhooks.py"],
                    line_hints=["24"],
                    impact_summary="Webhook processing starts before trust is established.",
                    evidence_snippet="Signature verification does not happen before the payload is processed.",
                    confidence="high",
                    proof_type="deterministic_pattern",
                    suggested_patch="Validate provider signatures before parsing or mutating webhook state.",
                    verification_state="verified",
                )
            ],
        )
        self.runtime.audit_repository.create_audit(audit)

        response = self.client.get("/api/wall")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertEqual(len(payload), 1)
        self.assertEqual(
            payload[0],
            {
                "audit_id": "wall-audit",
                "finding_id": audit.findings[0].id,
                "repo_url": "https://github.com/acme/example",
                "title": "Unsigned webhook path",
                "severity": "high",
                "agent_name": "webhook",
                "check_name": "missing_signature_verification",
                "impact_summary": "Webhook processing starts before trust is established.",
                "confidence": "high",
                "proof_type": "deterministic_pattern",
                "verification_state": "verified",
                "created_at": audit.findings[0].created_at.isoformat().replace("+00:00", "Z"),
            },
        )

    def _create_audit(self) -> dict[str, Any]:
        response = self.client.post(
            "/api/audits",
            json={"repo_url": "https://github.com/acme/example"},
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        return response.json()

    @staticmethod
    async def _read_first_chunk(response) -> str:
        chunk = await response.body_iterator.__anext__()
        close = getattr(response.body_iterator, "aclose", None)
        if close is not None:
            await close()
        return chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk

    @staticmethod
    async def _receive() -> dict[str, object]:
        return {"type": "http.request", "body": b"", "more_body": False}


if __name__ == "__main__":
    unittest.main()
