"""Append-only JSONL audit log. Every tool call, guardrail decision, and
agent action lands here with a timestamp and correlation id. In production
you'd ship these to a SIEM or data warehouse — here we keep it dead simple.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import settings


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_trace_id() -> str:
    return str(uuid.uuid4())


def log_event(
    event_type: str,
    *,
    trace_id: str,
    payload: dict[str, Any] | None = None,
) -> None:
    """Write one event to the audit log."""
    record = {
        "ts": _now(),
        "trace_id": trace_id,
        "event_type": event_type,
        "payload": payload or {},
    }
    path: Path = settings.audit_log_path
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")
