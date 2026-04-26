"""Internal RAG tool over firm documents.

Implements hybrid retrieval: dense (Chroma + sentence-transformers) plus
sparse (BM25) with a simple reciprocal-rank-fusion blend. Returns chunks
with source metadata so the agent can cite them — citations are non-
negotiable in regulated domains.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions
from langchain_core.tools import tool
from rank_bm25 import BM25Okapi

from app.audit import log_event
from app.config import settings
from app.tools.firm_db import _current_trace_id  # reuse trace slot

K_DENSE = 6
K_SPARSE = 6
K_FINAL = 4


@lru_cache(maxsize=1)
def _retrievers():
    """Lazy-build both retrievers once per process."""
    embedder = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="all-MiniLM-L6-v2"
    )
    client = chromadb.PersistentClient(path=str(settings.chroma_path))
    collection = client.get_or_create_collection(
        name="firm_docs", embedding_function=embedder
    )

    # Build BM25 over the same corpus
    all_data = collection.get(include=["documents", "metadatas"])
    corpus = all_data["documents"] or []
    metas = all_data["metadatas"] or []
    ids = all_data["ids"] or []
    tokenized = [doc.lower().split() for doc in corpus]
    bm25 = BM25Okapi(tokenized) if tokenized else None
    return collection, bm25, corpus, metas, ids


def _reciprocal_rank_fusion(rank_lists: list[list[str]], k: int = 60) -> dict[str, float]:
    """Standard RRF: combine multiple ranked lists into one score."""
    scores: dict[str, float] = {}
    for ranked in rank_lists:
        for rank, doc_id in enumerate(ranked):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
    return scores


@tool
def search_firm_knowledge(query: str) -> str:
    """Search internal firm knowledge: investment policy, research notes,
    compliance FAQs, and operational playbooks. Use this for any question
    about firm policy, internal views, or how the firm operates.

    Returns a JSON list of {text, source, doc_id, chunk_index} so you
    can cite sources in your response. ALWAYS cite sources you used.

    Args:
        query: A natural-language search query.
    """
    collection, bm25, corpus, metas, ids = _retrievers()
    if not corpus:
        return json.dumps({"error": "no documents indexed; run seed_rag"})

    # Dense
    dense_res = collection.query(query_texts=[query], n_results=K_DENSE)
    dense_ids = dense_res["ids"][0] if dense_res["ids"] else []

    # Sparse
    sparse_ids = []
    if bm25 is not None:
        scores = bm25.get_scores(query.lower().split())
        top = sorted(range(len(scores)), key=lambda i: -scores[i])[:K_SPARSE]
        sparse_ids = [ids[i] for i in top]

    # Fuse
    fused = _reciprocal_rank_fusion([dense_ids, sparse_ids])
    final = sorted(fused.items(), key=lambda x: -x[1])[:K_FINAL]

    # Look up texts and metadata
    id_to_idx = {doc_id: i for i, doc_id in enumerate(ids)}
    results = []
    for doc_id, _ in final:
        idx = id_to_idx.get(doc_id)
        if idx is None:
            continue
        results.append({
            "text": corpus[idx],
            "source": metas[idx].get("source", "unknown"),
            "doc_id": metas[idx].get("doc_id", "unknown"),
            "chunk_index": metas[idx].get("chunk_index", -1),
        })

    log_event(
        "tool_call",
        trace_id=_current_trace_id,
        payload={
            "tool": "search_firm_knowledge",
            "args": {"query": query},
            "result_summary": f"{len(results)} chunks: "
                              + ", ".join(r["source"] for r in results),
        },
    )

    return json.dumps(results)


RAG_TOOLS = [search_firm_knowledge]
