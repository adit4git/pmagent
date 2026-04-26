"""Index firm documents into Chroma for RAG.

Run once after seed_db:

    python -m app.data.seed_rag

Re-running rebuilds the index from scratch.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions

from app.config import settings


def _chunk_text(text: str, chunk_size: int = 700, overlap: int = 100) -> list[str]:
    """Simple character-based chunker. Real systems use semantic chunking,
    but this is enough to learn the patterns."""
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunk = text[start:end]
        # try to break at a paragraph or sentence boundary
        if end < len(text):
            last_break = max(chunk.rfind("\n\n"), chunk.rfind(". "))
            if last_break > chunk_size // 2:
                end = start + last_break + 1
                chunk = text[start:end]
        chunks.append(chunk.strip())
        start = end - overlap if end < len(text) else end
    return [c for c in chunks if c]


def main() -> None:
    settings.ensure_dirs()

    if settings.chroma_path.exists():
        shutil.rmtree(settings.chroma_path)
    settings.chroma_path.mkdir(parents=True, exist_ok=True)

    docs_dir: Path = settings.docs_dir
    files = sorted(docs_dir.glob("*.md"))
    if not files:
        print(f"⚠ No documents found in {docs_dir}")
        return

    embedder = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="all-MiniLM-L6-v2"
    )
    client = chromadb.PersistentClient(path=str(settings.chroma_path))
    collection = client.get_or_create_collection(
        name="firm_docs", embedding_function=embedder
    )

    ids, docs, metas = [], [], []
    for path in files:
        text = path.read_text(encoding="utf-8")
        chunks = _chunk_text(text)
        for i, chunk in enumerate(chunks):
            ids.append(f"{path.stem}__c{i}")
            docs.append(chunk)
            metas.append({
                "source": path.name,
                "doc_id": path.stem,
                "chunk_index": i,
            })

    collection.add(ids=ids, documents=docs, metadatas=metas)

    print(f"✓ Indexed {len(files)} files → {len(ids)} chunks "
          f"into Chroma at {settings.chroma_path}")


if __name__ == "__main__":
    main()
