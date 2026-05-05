"""Streamlit page to browse full markdown documents by URL parameter.

Examples:
    ?doc=knowledge/01_investment_policy.md
    ?doc=project/REBUILD_SPEC.md
"""
from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import quote

import streamlit as st

# Make the app package importable when running via Streamlit pages.
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.config import settings  # noqa: E402


st.set_page_config(page_title="Doc Endpoint", page_icon="📄", layout="wide")
st.title("📄 Document Endpoint")
st.caption("Browse full markdown file content from deployed docs.")


def _catalog_docs() -> dict[str, Path]:
    catalog: dict[str, Path] = {}
    sources = {
        "knowledge": settings.docs_dir,
        "project": ROOT / "docs",
    }
    for source, base_dir in sources.items():
        if not base_dir.exists():
            continue
        for path in sorted(base_dir.glob("*.md")):
            catalog[f"{source}/{path.name}"] = path
    return catalog


def _resolve_doc_key(query_value: str | None, catalog: dict[str, Path]) -> tuple[str | None, str | None]:
    """Resolve query string to a catalog key, allowing short filename form."""
    if not query_value:
        return None, None

    if query_value in catalog:
        return query_value, None

    if "/" not in query_value:
        matches = [key for key in catalog if key.endswith(f"/{query_value}")]
        if len(matches) == 1:
            return matches[0], None
        if len(matches) > 1:
            return None, (
                f"`{query_value}` matches multiple docs. "
                "Use `source/filename.md` (for example `knowledge/01_investment_policy.md`)."
            )

    return None, f"Document not found for `doc={query_value}`."


docs = _catalog_docs()
if not docs:
    st.error("No markdown files found in `app/data/documents` or `docs`.")
    st.stop()

requested_doc = st.query_params.get("doc")
resolved_key, resolve_error = _resolve_doc_key(requested_doc, docs)

if resolve_error:
    st.warning(resolve_error)

doc_keys = list(docs.keys())
default_index = 0
if resolved_key in docs:
    default_index = doc_keys.index(resolved_key)

selected_key = st.selectbox("Document", doc_keys, index=default_index)
if selected_key != requested_doc:
    st.query_params["doc"] = selected_key

selected_path = docs[selected_key]
content = selected_path.read_text(encoding="utf-8")

st.caption(f"Path: `{selected_path}`")
st.caption(f"Shareable URL query: `?doc={quote(selected_key, safe='')}`")
st.divider()
st.markdown(content)

with st.expander("Raw markdown"):
    st.code(content, language="markdown")
