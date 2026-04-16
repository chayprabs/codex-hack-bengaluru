import json
from typing import Any


def format_sse_event(
    data: Any,
    *,
    event: str | None = None,
    event_id: str | None = None,
    retry: int | None = None,
) -> str:
    """Serialize a payload using the Server-Sent Events wire format."""

    message_lines: list[str] = []
    if event:
        message_lines.append(f"event: {event}")
    if event_id:
        message_lines.append(f"id: {event_id}")
    if retry is not None:
        message_lines.append(f"retry: {retry}")

    payload = json.dumps(data, default=str)
    for line in payload.splitlines() or [""]:
        message_lines.append(f"data: {line}")

    message_lines.append("")
    return "\n".join(message_lines)


def format_sse_comment(comment: str) -> str:
    return f": {comment}\n\n"
