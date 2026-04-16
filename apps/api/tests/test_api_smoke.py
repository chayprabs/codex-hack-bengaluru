from __future__ import annotations

import asyncio
import unittest
from contextlib import ExitStack, asynccontextmanager
from typing import Any
from unittest.mock import patch

from support import ensure_api_path

ensure_api_path()

from fastapi import FastAPI, status
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.db import DatabaseRuntime
from app.main import create_app
from app.models import AgentStatus
from app.routes.audits import stream_audit
from app.services.audit_service import AuditService


class StubAuditRunner:
    def __init__(self) -> None:
        self.started_audit_ids: list[str] = []

    def build_initial_agents(self) -> list[AgentStatus]:
        return [
            AgentStatus(name="planner"),
            AgentStatus(name="scanner"),
            AgentStatus(name="verifier"),
        ]

    def start(self, audit_id: str) -> None:
        self.started_audit_ids.append(audit_id)


@asynccontextmanager
async def no_lifespan(_: FastAPI):
    yield


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

        self.stack.enter_context(patch("app.main.lifespan", no_lifespan))
        self.stack.enter_context(patch("app.api.routes.health.database_runtime", self.runtime))
        self.stack.enter_context(patch("app.routes.audits.audit_service", self.audit_service))
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
                "database": {
                    "driver": "memory",
                    "path": ":memory:",
                    "ready": True,
                },
            },
        )

    def test_create_audit_returns_created_audit(self) -> None:
        repo_url = "https://github.com/acme/platform"

        response = self.client.post("/api/audits", json={"repo_url": repo_url})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        payload = response.json()
        self.assertEqual(payload["repo_url"], repo_url)
        self.assertEqual(payload["status"], "queued")
        self.assertEqual(
            [agent["name"] for agent in payload["agents"]],
            ["planner", "scanner", "verifier"],
        )
        self.assertIn(payload["id"], self.runner.started_audit_ids)

    def test_create_demo_audit_uses_configured_demo_repo(self) -> None:
        response = self.client.post("/api/demo-audit")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        payload = response.json()
        self.assertEqual(payload["repo_url"], "https://github.com/example/demo-repo")
        self.assertEqual(payload["status"], "queued")
        self.assertIn(payload["id"], self.runner.started_audit_ids)

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
