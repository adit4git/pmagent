#!/bin/bash
set -e

if [ -z "${ANTHROPIC_API_KEY//[[:space:]]/}" ]; then
    echo "ERROR: ANTHROPIC_API_KEY is missing or empty. Add a non-empty value in Railway → Variables."
    exit 1
fi

if [ ! -f "app/data/db/firm.sqlite" ]; then
    echo "Seeding firm database..."
    python -m app.data.seed_db
fi

if [ ! -d "app/data/db/chroma" ] || [ -z "$(ls -A app/data/db/chroma 2>/dev/null)" ]; then
    echo "Indexing documents into ChromaDB..."
    python -m app.data.seed_rag
fi

exec streamlit run ui/app.py \
    --server.port "${PORT:-8501}" \
    --server.address 0.0.0.0 \
    --server.headless true \
    --server.fileWatcherType none
