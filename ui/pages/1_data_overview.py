"""Streamlit data overview page.

This page is a read-only inspector for all local data sources used by PM Copilot.
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from collections import Counter, deque
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

# Make the app package importable when running via Streamlit pages.
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.config import settings  # noqa: E402
from app.memory.preferences import get_pm_name, get_preferences  # noqa: E402


st.set_page_config(page_title="Data Overview", page_icon="🗂️", layout="wide")
st.title("🗂️ PM Copilot Data Overview")
st.caption("Read-only view of SQLite tables, markdown corpora, vector index, preferences, and audit logs.")


def _extract_first_paragraphs(markdown_text: str, limit: int = 2) -> list[str]:
    blocks = re.split(r"\n\s*\n", markdown_text.strip())
    paragraphs: list[str] = []
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        if not re.search(r"[A-Za-z0-9]", block):
            continue
        lines = [ln.rstrip() for ln in block.splitlines() if ln.strip()]
        if not lines:
            continue
        # Skip heading-only blocks; we want paragraph snapshots.
        if all(ln.lstrip().startswith("#") for ln in lines):
            continue
        paragraphs.append("\n".join(lines))
        if len(paragraphs) >= limit:
            break
    return paragraphs


@st.cache_data(show_spinner=False)
def _load_sqlite_overview(sqlite_path: str) -> tuple[list[str], dict[str, int], dict[str, pd.DataFrame]]:
    path = Path(sqlite_path)
    if not path.exists():
        return [], {}, {}

    with sqlite3.connect(path) as conn:
        tables = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
        ]
        counts: dict[str, int] = {}
        previews: dict[str, pd.DataFrame] = {}
        for table in tables:
            counts[table] = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            previews[table] = pd.read_sql_query(
                f"SELECT * FROM {table} LIMIT 200",
                conn,
            )
    return tables, counts, previews


@st.cache_data(show_spinner=False)
def _load_markdown_snapshots(directory: str) -> list[dict[str, Any]]:
    path = Path(directory)
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    for md_path in sorted(path.glob("*.md")):
        text = md_path.read_text(encoding="utf-8")
        paragraphs = _extract_first_paragraphs(text, limit=2)
        out.append(
            {
                "name": md_path.name,
                "path": str(md_path),
                "size_bytes": md_path.stat().st_size,
                "snapshot": paragraphs,
            }
        )
    return out


@st.cache_data(show_spinner=False)
def _load_chroma_overview(chroma_path: str) -> dict[str, Any]:
    path = Path(chroma_path)
    if not path.exists():
        return {"exists": False, "message": "Chroma directory not found."}

    try:
        import chromadb
    except Exception as exc:  # pragma: no cover - import depends on runtime image
        return {"exists": True, "error": f"Unable to import chromadb: {exc}"}

    try:
        client = chromadb.PersistentClient(path=str(path))
        collection = client.get_or_create_collection(name="firm_docs")
        count = collection.count()
        data = collection.get(include=["metadatas"])
        metas = data.get("metadatas") or []
        source_counts = Counter((m or {}).get("source", "unknown") for m in metas)
        return {
            "exists": True,
            "count": count,
            "source_counts": dict(sorted(source_counts.items())),
            "path": str(path),
        }
    except Exception as exc:  # pragma: no cover - runtime datastore edge-cases
        return {"exists": True, "error": f"Failed to read Chroma collection: {exc}"}


@st.cache_data(show_spinner=False)
def _load_preferences_summary(data_dir: str) -> tuple[pd.DataFrame, bool]:
    pref_path = Path(data_dir) / "pm_preferences.json"
    if pref_path.exists():
        payload = json.loads(pref_path.read_text(encoding="utf-8"))
        rows = []
        for pm_id, item in payload.items():
            rows.append(
                {
                    "pm_id": pm_id,
                    "name": item.get("name", pm_id),
                    "preference_count": len(item.get("preferences", [])),
                }
            )
        return pd.DataFrame(rows).sort_values("pm_id"), True

    # Fallback to in-code defaults.
    rows = [
        {
            "pm_id": "PM01",
            "name": get_pm_name("PM01"),
            "preference_count": len(get_preferences("PM01")),
        }
    ]
    return pd.DataFrame(rows), False


@st.cache_data(show_spinner=False)
def _load_audit_tail(audit_path: str, tail_size: int = 50) -> tuple[int, pd.DataFrame]:
    path = Path(audit_path)
    if not path.exists():
        return 0, pd.DataFrame()

    tail: deque[str] = deque(maxlen=tail_size)
    total = 0
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            total += 1
            if line.strip():
                tail.append(line)

    rows: list[dict[str, Any]] = []
    for line in tail:
        try:
            parsed = json.loads(line)
            rows.append(
                {
                    "ts": parsed.get("ts"),
                    "trace_id": parsed.get("trace_id"),
                    "event_type": parsed.get("event_type"),
                    "payload": json.dumps(parsed.get("payload", {}), default=str)[:240],
                }
            )
        except json.JSONDecodeError:
            rows.append({"ts": "", "trace_id": "", "event_type": "parse_error", "payload": line[:240]})
    return total, pd.DataFrame(rows)


st.subheader("Runtime Configuration")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Model", settings.anthropic_model)
c2.metric("Approval Gate", str(settings.require_approval_for_proposals))
c3.metric("API Key Present", "Yes" if settings.has_anthropic_api_key() else "No")
c4.metric("Data Dir", str(settings.data_dir))


st.subheader("SQLite Data (Firm DB)")
tables, row_counts, previews = _load_sqlite_overview(str(settings.sqlite_path))
if not tables:
    st.warning(f"SQLite DB not found at `{settings.sqlite_path}`. Run `python -m app.data.seed_db`.")
else:
    summary_rows = [{"table": t, "rows": row_counts.get(t, 0)} for t in tables]
    st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)
    for table in tables:
        with st.expander(f"{table} — preview ({row_counts.get(table, 0)} rows total)", expanded=False):
            st.dataframe(previews[table], use_container_width=True, hide_index=True)


st.subheader("Knowledge Docs Snapshots (first 2 paragraphs)")
doc_snapshots = _load_markdown_snapshots(str(settings.docs_dir))
if not doc_snapshots:
    st.warning(f"No markdown files found in `{settings.docs_dir}`.")
else:
    for item in doc_snapshots:
        with st.expander(f"{item['name']} ({item['size_bytes']} bytes)", expanded=False):
            if not item["snapshot"]:
                st.info("No paragraph-like content found.")
            else:
                for idx, para in enumerate(item["snapshot"], start=1):
                    st.markdown(f"**Paragraph {idx}**")
                    st.markdown(para)


st.subheader("Project Docs Snapshots (`docs/*.md`)")
project_doc_snapshots = _load_markdown_snapshots(str(ROOT / "docs"))
if not project_doc_snapshots:
    st.info("No project markdown docs found in `docs/`.")
else:
    for item in project_doc_snapshots:
        with st.expander(f"{item['name']} ({item['size_bytes']} bytes)", expanded=False):
            if not item["snapshot"]:
                st.info("No paragraph-like content found.")
            else:
                for idx, para in enumerate(item["snapshot"], start=1):
                    st.markdown(f"**Paragraph {idx}**")
                    st.markdown(para)


st.subheader("Vector Store (Chroma)")
chroma = _load_chroma_overview(str(settings.chroma_path))
if not chroma.get("exists"):
    st.warning(chroma.get("message", "Chroma index not available."))
elif chroma.get("error"):
    st.error(chroma["error"])
else:
    m1, m2 = st.columns(2)
    m1.metric("Indexed Chunks", chroma.get("count", 0))
    m2.metric("Chroma Path", chroma.get("path", ""))
    source_counts = chroma.get("source_counts", {})
    if source_counts:
        st.dataframe(
            pd.DataFrame(
                [{"source": source, "chunks": count} for source, count in source_counts.items()]
            ),
            use_container_width=True,
            hide_index=True,
        )


st.subheader("PM Preferences")
pref_df, from_file = _load_preferences_summary(str(settings.data_dir))
if from_file:
    st.caption("Loaded from persisted `app/data/pm_preferences.json`.")
else:
    st.caption("Using in-code defaults from `app/memory/preferences.py` (no persisted file yet).")
st.dataframe(pref_df, use_container_width=True, hide_index=True)
with st.expander("PM01 preference details", expanded=False):
    prefs = get_preferences("PM01")
    if not prefs:
        st.info("No preferences found for PM01.")
    else:
        for i, pref in enumerate(prefs, start=1):
            st.markdown(f"{i}. {pref}")


st.subheader("Audit Log")
audit_total, audit_tail_df = _load_audit_tail(str(settings.audit_log_path))
if audit_total == 0:
    st.info(f"No audit log found at `{settings.audit_log_path}`.")
else:
    st.caption(f"Total events: {audit_total}. Showing the latest {len(audit_tail_df)}.")
    st.dataframe(audit_tail_df, use_container_width=True, hide_index=True)
