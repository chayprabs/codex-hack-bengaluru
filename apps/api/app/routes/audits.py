"""Compatibility shim for older imports.

The authoritative audit route implementation now lives in ``app.api.routes.audits``
so the API router, docs, and tests all point at the same module path.
"""

from ..api.routes.audits import (
    create_audit,
    create_demo_audit,
    get_audit,
    get_demo_setup,
    router,
    stream_audit,
)

__all__ = [
    "router",
    "create_audit",
    "get_demo_setup",
    "create_demo_audit",
    "get_audit",
    "stream_audit",
]
