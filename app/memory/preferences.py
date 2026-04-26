"""Long-term per-PM preferences.

Tiny JSON-on-disk store. The point isn't the storage backend — swap for
Redis or pgvector later. The point is showing where preferences plug in:
they get injected into the system prompt at the start of every turn.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.config import settings

_STORE_PATH = settings.data_dir / "pm_preferences.json"


def _load() -> dict:
    if not _STORE_PATH.exists():
        return {
            "PM01": {
                "name": "Sarah",
                "preferences": [
                    "Always apply ESG screening notes when discussing the Garcia Foundation.",
                    "Prefer concise bullet summaries for quick reads.",
                    "Flag any tax-loss harvesting opportunities proactively.",
                ],
            }
        }
    return json.loads(_STORE_PATH.read_text())


def _save(data: dict) -> None:
    _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _STORE_PATH.write_text(json.dumps(data, indent=2))


def get_preferences(pm_id: str) -> list[str]:
    data = _load()
    return data.get(pm_id, {}).get("preferences", [])


def add_preference(pm_id: str, pref: str) -> None:
    data = _load()
    bucket = data.setdefault(pm_id, {"name": pm_id, "preferences": []})
    if pref not in bucket["preferences"]:
        bucket["preferences"].append(pref)
    _save(data)


def get_pm_name(pm_id: str) -> str:
    return _load().get(pm_id, {}).get("name", pm_id)
