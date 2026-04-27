# PM Copilot — Agentic AI Starter Project

A learning-focused, production-pattern agentic AI system for portfolio managers. Hits every critical layer of enterprise agentic AI: tool use, RAG, multi-source orchestration, memory, guardrails, evaluation, and human-in-the-loop.

## What You'll Learn

- **Agent orchestration** with LangGraph (ReAct pattern)
- **Tool calling** across internal DB, RAG, and external APIs
- **RAG** with hybrid search (BM25 + embeddings) and citations
- **Memory** (short-term conversation + long-term preferences)
- **Guardrails** (PII filtering, compliance blocks, human approval)
- **Audit logging** (every tool call traced)
- **Evaluation** (LLM-as-judge + tool-call accuracy)

## Prerequisites (Mac)

1. **Python 3.11+** — check with `python3 --version`. If missing: `brew install python@3.11`
2. **VS Code** — download from https://code.visualstudio.com/
3. **VS Code extensions** (install from the Extensions panel):
   - Python (Microsoft)
   - Pylance
   - Jupyter (optional, for notebook exploration)
4. **An Anthropic API key** — get one at https://console.anthropic.com/

## Setup (5 minutes)

```bash
# 1. Open the project in VS Code
cd pm-copilot
code .

# 2. Open VS Code's integrated terminal (Cmd+`) and run:
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 3. Configure your API key
export ANTHROPIC_API_KEY="sk-ant-your-key-here"
# Optional: set ANTHROPIC_MODEL, LOG_LEVEL, REQUIRE_APPROVAL_FOR_PROPOSALS

# 4. Seed the mock firm database and load documents into the vector store
python -m app.data.seed_db
python -m app.data.seed_rag

# 5. Run the agent in CLI mode (great for learning what's happening)
python -m app.main

# 6. OR launch the Streamlit UI
streamlit run ui/app.py
```

In VS Code, select the `.venv` interpreter: `Cmd+Shift+P` → "Python: Select Interpreter" → choose `.venv/bin/python`.

## Try These Queries

Each query exercises a different combination of tools. Watch the trace output to see the agent plan, call tools, and synthesize.

1. *"Summarize the Johnson family account and flag any drift from their target allocation."*
   → Firm DB + internal policy RAG

2. *"What's our firm's view on tech sector exposure right now, and how does it compare to recent market moves?"*
   → Internal research RAG + market data

3. *"Are there any recent news items for the top holdings in the Chen portfolio I should know about before our meeting?"*
   → Firm DB + news + multi-step planning

4. *"Draft a rebalancing proposal for the Patel account considering their risk profile and current market conditions."*
   → Everything + human-approval guardrail

## Project Layout

```
pm-copilot/
├── app/
│   ├── main.py                  # CLI entrypoint
│   ├── config.py                # Settings & env loading
│   ├── agents/
│   │   └── pm_agent.py          # LangGraph ReAct agent
│   ├── tools/
│   │   ├── firm_db.py           # Mock firm SQLite DB tools
│   │   ├── rag.py               # Internal RAG over docs
│   │   ├── market_data.py       # External market quotes
│   │   ├── news.py              # Financial news
│   │   └── forecasting.py       # Simple forecast tool
│   ├── guardrails/
│   │   ├── input_filter.py      # PII + prompt injection screen
│   │   ├── output_filter.py     # Compliance language check
│   │   └── approval.py          # Human-in-the-loop gate
│   ├── memory/
│   │   └── preferences.py       # Per-PM long-term memory
│   ├── data/
│   │   ├── seed_db.py           # Build the firm SQLite DB
│   │   ├── seed_rag.py          # Index docs into Chroma
│   │   └── documents/           # Sample firm PDFs/markdown
│   └── evals/
│       ├── eval_set.py          # Test cases
│       └── run_evals.py         # Eval harness
├── ui/
│   └── app.py                   # Streamlit chat UI
├── requirements.txt
├── .env.example
└── README.md
```

## How to Read the Code (Suggested Order)

1. `app/tools/firm_db.py` — start here. Simplest tool, shows the schema pattern.
2. `app/tools/rag.py` — RAG with hybrid search and citations.
3. `app/agents/pm_agent.py` — the orchestration brain.
4. `app/guardrails/` — what makes this enterprise-grade.
5. `app/evals/run_evals.py` — how you keep it honest.

## Extending the Project

Once you have it running, try:
- Add a new tool (e.g., SEC EDGAR filings via their free API)
- Replace SQLite with Postgres
- Add a second agent for compliance review
- Plug in OpenTelemetry for proper tracing
- Swap Claude for a local model via Ollama

## Troubleshooting

- **`ModuleNotFoundError`** — make sure `.venv` is activated (`source .venv/bin/activate`).
- **`AuthenticationError` / auth `TypeError`** — ensure `ANTHROPIC_API_KEY` is present and non-empty (no whitespace-only value).
- **Chroma errors on first run** — delete `app/data/db/chroma` and re-run `seed_rag`.
- **`yfinance` rate-limited** — the market data tool falls back to cached synthetic prices; safe to ignore for learning.

## Environment Variables

The app reads configuration directly from process environment variables.

```bash
export ANTHROPIC_API_KEY="sk-ant-your-key-here"
export ANTHROPIC_MODEL="claude-sonnet-4-6"   # optional
export LOG_LEVEL="INFO"                       # optional
export REQUIRE_APPROVAL_FOR_PROPOSALS="true" # optional
```

If you prefer storing variables in a local `.env`, source it into your shell before running:

```bash
set -a
source .env
set +a
```

On Railway, set these in your service `Variables` and redeploy.
