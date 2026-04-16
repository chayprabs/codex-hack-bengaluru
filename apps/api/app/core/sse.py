from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time
from itertools import count
from threading import Lock
from typing import Any, AsyncIterator, Iterable, Literal, Mapping

from fastapi import Request
from pydantic import BaseModel
from starlette.responses import StreamingResponse

from ..models import AuditStreamEventName


@dataclass(frozen=True, slots=True)
class SSEMessage:
    event: AuditStreamEventName
    data: Any
    event_id: str
    retry: int | None = None


@dataclass(slots=True)
class _Subscriber:
    queue: asyncio.Queue[SSEMessage]
    loop: asyncio.AbstractEventLoop


def _normalize_payload(payload: Any) -> Any:
    if isinstance(payload, BaseModel):
        return payload.model_dump(mode="json")
    if isinstance(payload, (datetime, date, time)):
        return payload.isoformat()
    if isinstance(payload, Mapping):
        return {str(key): _normalize_payload(value) for key, value in payload.items()}
    if isinstance(payload, (list, tuple, set)):
        return [_normalize_payload(item) for item in payload]
    return payload


def _with_audit_context(audit_id: str, payload: Any) -> dict[str, Any]:
    normalized = _normalize_payload(payload)
    if isinstance(normalized, dict):
        return {"audit_id": audit_id, **normalized} if "audit_id" not in normalized else normalized
    return {"audit_id": audit_id, "payload": normalized}


def serialize_sse_message(message: SSEMessage) -> str:
    lines = [f"event: {message.event}", f"id: {message.event_id}"]
    if message.retry is not None:
        lines.append(f"retry: {message.retry}")

    payload = json.dumps(message.data, default=str, separators=(",", ":"), ensure_ascii=False)
    for line in payload.splitlines() or [""]:
        lines.append(f"data: {line}")

    lines.append("")
    return "\n".join(lines) + "\n"


def serialize_sse_comment(comment: str) -> str:
    return f": {comment}\n\n"


class AuditEventBroker:
    """In-process SSE pub/sub for one-process hackathon deployments."""

    def __init__(
        self,
        *,
        heartbeat_interval: float = 15.0,
        retry_ms: int = 3000,
        subscriber_queue_size: int = 100,
    ) -> None:
        self.heartbeat_interval = heartbeat_interval
        self.retry_ms = retry_ms
        self.subscriber_queue_size = subscriber_queue_size
        self._subscriber_ids = count(1)
        self._event_ids = count(1)
        self._subscribers: dict[str, dict[int, _Subscriber]] = defaultdict(dict)
        self._lock = Lock()

    def build_message(
        self,
        audit_id: str,
        event: AuditStreamEventName,
        payload: Any,
        *,
        event_id: str | None = None,
        retry: int | None = None,
    ) -> SSEMessage:
        return SSEMessage(
            event=event,
            data=_with_audit_context(audit_id, payload),
            event_id=event_id or f"{audit_id}:{next(self._event_ids)}",
            retry=self.retry_ms if retry is None else retry,
        )

    def subscribe(self, audit_id: str) -> tuple[int, asyncio.Queue[SSEMessage]]:
        subscriber = _Subscriber(
            queue=asyncio.Queue(maxsize=self.subscriber_queue_size),
            loop=asyncio.get_running_loop(),
        )
        subscriber_id = next(self._subscriber_ids)
        with self._lock:
            self._subscribers[audit_id][subscriber_id] = subscriber
        return subscriber_id, subscriber.queue

    def unsubscribe(self, audit_id: str, subscriber_id: int) -> None:
        with self._lock:
            subscribers = self._subscribers.get(audit_id)
            if subscribers is None:
                return
            subscribers.pop(subscriber_id, None)
            if not subscribers:
                self._subscribers.pop(audit_id, None)

    def publish(
        self,
        audit_id: str,
        event: AuditStreamEventName,
        payload: Any,
        *,
        event_id: str | None = None,
        retry: int | None = None,
    ) -> str:
        message = self.build_message(
            audit_id,
            event,
            payload,
            event_id=event_id,
            retry=retry,
        )
        self.publish_message(audit_id, message)
        return message.event_id

    def publish_message(self, audit_id: str, message: SSEMessage) -> None:
        stale_subscribers: list[int] = []
        with self._lock:
            subscribers = list(self._subscribers.get(audit_id, {}).items())

        for subscriber_id, subscriber in subscribers:
            try:
                subscriber.loop.call_soon_threadsafe(self._enqueue_message, subscriber.queue, message)
            except RuntimeError:
                stale_subscribers.append(subscriber_id)

        for subscriber_id in stale_subscribers:
            self.unsubscribe(audit_id, subscriber_id)

    @staticmethod
    def _enqueue_message(queue: asyncio.Queue[SSEMessage], message: SSEMessage) -> None:
        if queue.full():
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                pass

        try:
            queue.put_nowait(message)
        except asyncio.QueueFull:
            pass

    async def stream(
        self,
        audit_id: str,
        request: Request,
        *,
        initial_events: Iterable[SSEMessage] | None = None,
    ) -> AsyncIterator[str]:
        subscriber_id, queue = self.subscribe(audit_id)
        try:
            for message in initial_events or ():
                yield serialize_sse_message(message)

            while True:
                if await request.is_disconnected():
                    break

                try:
                    message = await asyncio.wait_for(queue.get(), timeout=self.heartbeat_interval)
                except asyncio.TimeoutError:
                    yield serialize_sse_comment("keep-alive")
                    continue

                yield serialize_sse_message(message)
        finally:
            self.unsubscribe(audit_id, subscriber_id)

    def stream_response(
        self,
        audit_id: str,
        request: Request,
        *,
        initial_events: Iterable[SSEMessage] | None = None,
    ) -> StreamingResponse:
        return StreamingResponse(
            self.stream(audit_id, request, initial_events=initial_events),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )


audit_event_broker = AuditEventBroker()


def build_audit_event(
    audit_id: str,
    event: AuditStreamEventName,
    payload: Any,
    *,
    event_id: str | None = None,
    retry: int | None = None,
) -> SSEMessage:
    return audit_event_broker.build_message(
        audit_id,
        event,
        payload,
        event_id=event_id,
        retry=retry,
    )


def build_agent_status_event(
    audit_id: str,
    payload: Any,
    *,
    event_id: str | None = None,
    retry: int | None = None,
) -> SSEMessage:
    return build_audit_event(
        audit_id,
        "agent_status",
        payload,
        event_id=event_id,
        retry=retry,
    )


def build_finding_event(
    audit_id: str,
    payload: Any,
    *,
    event_id: str | None = None,
    retry: int | None = None,
) -> SSEMessage:
    return build_audit_event(
        audit_id,
        "finding",
        payload,
        event_id=event_id,
        retry=retry,
    )


def build_score_update_event(
    audit_id: str,
    payload: Any,
    *,
    event_id: str | None = None,
    retry: int | None = None,
) -> SSEMessage:
    return build_audit_event(
        audit_id,
        "score_update",
        payload,
        event_id=event_id,
        retry=retry,
    )


def build_audit_complete_event(
    audit_id: str,
    payload: Any,
    *,
    event_id: str | None = None,
    retry: int | None = None,
) -> SSEMessage:
    return build_audit_event(
        audit_id,
        "audit_complete",
        payload,
        event_id=event_id,
        retry=retry,
    )


def publish_audit_event(
    audit_id: str,
    event: AuditStreamEventName,
    payload: Any,
    *,
    event_id: str | None = None,
    retry: int | None = None,
) -> str:
    return audit_event_broker.publish(
        audit_id,
        event,
        payload,
        event_id=event_id,
        retry=retry,
    )


def publish_agent_status(
    audit_id: str,
    payload: Any,
    *,
    event_id: str | None = None,
    retry: int | None = None,
) -> str:
    return publish_audit_event(
        audit_id,
        "agent_status",
        payload,
        event_id=event_id,
        retry=retry,
    )


def publish_finding(
    audit_id: str,
    payload: Any,
    *,
    event_id: str | None = None,
    retry: int | None = None,
) -> str:
    return publish_audit_event(
        audit_id,
        "finding",
        payload,
        event_id=event_id,
        retry=retry,
    )


def publish_score_update(
    audit_id: str,
    payload: Any,
    *,
    event_id: str | None = None,
    retry: int | None = None,
) -> str:
    return publish_audit_event(
        audit_id,
        "score_update",
        payload,
        event_id=event_id,
        retry=retry,
    )


def publish_audit_complete(
    audit_id: str,
    payload: Any,
    *,
    event_id: str | None = None,
    retry: int | None = None,
) -> str:
    return publish_audit_event(
        audit_id,
        "audit_complete",
        payload,
        event_id=event_id,
        retry=retry,
    )


def build_audit_stream_response(
    audit_id: str,
    request: Request,
    *,
    initial_events: Iterable[SSEMessage] | None = None,
) -> StreamingResponse:
    return audit_event_broker.stream_response(
        audit_id,
        request,
        initial_events=initial_events,
    )
