# PM Copilot — Architecture Overview

## What It Is

PM Copilot is an AI assistant for portfolio managers. A PM asks a natural-language question ("Summarize the Johnson account and flag any drift"), and the system orchestrates several tools — a firm database, a document knowledge base, live market data, news, and a return forecaster — to produce a grounded, compliance-safe answer.

---

## Top-Level Structure

```
pm-copilot/
├── app/
│   ├── agents/       # Orchestration — the request/response lifecycle
│   ├── tools/        # Five independent tool modules
│   ├── guardrails/   # Input screening, output screening, approval gate
│   ├── memory/       # Per-PM preferences (injected into every prompt)
│   ├── data/         # DB seeding, RAG indexing, documents, SQLite, Chroma
│   ├── evals/        # Evaluation test cases and harness
│   ├── main.py       # CLI entry point
│   ├── config.py     # Environment-based configuration (Pydantic)
│   └── audit.py      # Append-only JSONL audit logger
├── ui/
│   └── app.py        # Streamlit chat UI (wraps the same agent)
├── docs/             # Architecture diagrams and this file
├── requirements.txt
└── audit_log.jsonl   # Runtime audit trail
```

---

## The Request Lifecycle

Every query — whether from the CLI (`app/main.py`) or the Streamlit UI (`ui/app.py`) — passes through the same pipeline inside `app/agents/pm_agent.py`:

```
User Query
    │
    ▼
1. Input Screening          ← guardrails/input_filter.py
   Detect PII (redact) and prompt injection (block)
    │
    ▼
2. Build System Prompt      ← memory/preferences.py
   Inject PM name, role instructions, per-PM preferences,
   citation rules, and guardrail instructions
    │
    ▼
3. LangGraph ReAct Agent    ← Claude API via langchain-anthropic
   Claude loops: plan → call tool → observe result → refine
   until it can answer without more tools
    │
    ├── firm_db.py       (SQLite — client portfolios, holdings, drift)
    ├── rag.py           (Chroma + BM25 — firm documents)
    ├── market_data.py   (yfinance — live quotes, sector snapshots)
    ├── news.py          (Yahoo RSS — recent headlines)
    └── forecasting.py   (naive drift model — return estimates)
    │
    ▼
4. Output Screening         ← guardrails/output_filter.py
   Rewrite unhedged language; append AI disclaimer if client-facing
    │
    ▼
5. Human Approval Gate      ← guardrails/approval.py
   For high-impact proposals (rebalancing, trade, client communication):
   CLI prompts stdin; Streamlit uses UI buttons
    │
    ▼
6. Audit Log                ← audit.py
   Every event (tool call, guardrail decision, approval) written to
   audit_log.jsonl with a shared trace_id for the full turn
    │
    ▼
AgentResult → Entry Point → Rendered to PM
```

---

## Components

### `app/agents/pm_agent.py` — The Brain

The central orchestrator. Its `run()` function executes the full pipeline above and returns an `AgentResult` containing:

- `final_text` — the answer to render
- `tool_calls` — the full execution trace (tool names, args, results)
- `flags` — any guardrail flags raised
- `trace_id` — UUID correlating all audit events for this turn
- `blocked` / `block_reason` — set if the input was rejected

Uses LangGraph's prebuilt `create_react_agent` under the hood.

---

### `app/tools/` — Five Independent Tools

Each tool is decorated with LangChain's `@tool` and returns JSON.

| Module | Purpose | Backend |
|---|---|---|
| `firm_db.py` | Client profiles, portfolios, holdings, drift, trades | SQLite (`app/data/db/firm.sqlite`) |
| `rag.py` | Search firm documents (policy, research, compliance) | Chroma + BM25 hybrid search |
| `market_data.py` | Live quotes, sector snapshots | yfinance (synthetic fallback) |
| `news.py` | Recent headlines for a ticker | Yahoo Finance RSS |
| `forecasting.py` | Return estimates with confidence intervals | Naive drift + volatility model |

**Hybrid RAG** (`rag.py`) combines:
- **Dense retrieval**: Chroma vector store + `sentence-transformers/all-MiniLM-L6-v2` embeddings
- **Sparse retrieval**: BM25Okapi keyword search
- **Fusion**: Reciprocal Rank Fusion (k=60) to merge the two ranked lists

**Resilience pattern**: `market_data.py` and `news.py` both have deterministic synthetic fallbacks so the agent works even when external APIs are unavailable.

---

### `app/guardrails/` — Three-Layer Safety

Run in sequence on every turn.

**1. `input_filter.py`** — Runs before the agent.
- PII detection (SSN, credit card, email, phone via regex) → redacts and continues
- Prompt injection detection ("ignore previous instructions", etc.) → blocks the request entirely

**2. `output_filter.py`** — Runs after the agent produces its answer.
- Rewrites unhedged language ("you should buy/sell") with review-needed flags
- Auto-appends an AI disclosure if the response is a client-facing draft

**3. `approval.py`** — Runs if the output looks like a proposal.
- Keyword detection classifies as `rebalancing_proposal`, `trade_proposal`, or `client_communication_send`
- CLI: prompts on stdin with a formatted preview
- Streamlit: delegates to UI approval buttons
- Every decision is audited

---

### `app/memory/preferences.py` — PM Preferences

Loads per-PM preferences from `app/data/pm_preferences.json` and injects them into the system prompt at every turn. Example preferences for PM01:

- "Always apply ESG screening notes when discussing the Garcia Foundation."
- "Prefer concise bullet summaries for quick reads."
- "Flag any tax-loss harvesting opportunities proactively."

The backend is a simple JSON file — easy to swap for Redis or a database.

---

### `app/data/` — Data Layer

| Path | Purpose | How to populate |
|---|---|---|
| `db/firm.sqlite` | Firm database (clients, portfolios, holdings, trades) | `python -m app.data.seed_db` |
| `db/chroma/` | Vector store for firm documents | `python -m app.data.seed_rag` |
| `documents/*.md` | Four firm knowledge documents (policy, research, compliance, playbook) | Included in repo |
| `pm_preferences.json` | Per-PM preference store | Included in repo |

**Test clients in the database:**
- Johnson (moderate risk)
- Chen (aggressive)
- Patel (conservative)
- Garcia Foundation (endowment)

---

### `app/audit.py` — Audit Trail

Append-only JSONL file at `audit_log.jsonl`. Every event records:

```json
{"ts": "...", "trace_id": "uuid", "event_type": "tool_call", "payload": {...}}
```

Event types: `turn_start`, `input_screen`, `tool_call`, `output_screen`, `approval_decision`, `turn_end`.

All events within one user turn share the same `trace_id`, making it easy to replay or debug a specific interaction.

---

### `app/evals/` — Evaluation Framework

`eval_set.py` defines 5 test cases covering:
1. Client summary retrieval
2. Firm knowledge search
3. Multi-tool orchestration
4. Prompt injection blocking
5. Proposal detection

`run_evals.py` runs them headlessly (approval gate disabled) and checks: correct tools used, expected keywords present, forbidden phrases absent. A foundation for adding LLM-as-judge scoring later.

---

### Entry Points

| File | Use Case |
|---|---|
| `app/main.py` | CLI — interactive REPL with Rich-formatted output and tool trace table |
| `ui/app.py` | Streamlit — chat UI with session state, approval buttons, tool trace expander |

Both call the same `pm_agent.run()` function. The only difference is how the `on_approval` callback is wired: CLI uses stdin, Streamlit uses `st.session_state`.

---

## Configuration

All configuration is read from process environment variables by `app/config.py`:

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | required | Anthropic API key |
| `ANTHROPIC_MODEL` | `claude-sonnet-4-6` | Model to use |
| `LOG_LEVEL` | `INFO` | Logging verbosity |
| `REQUIRE_APPROVAL_FOR_PROPOSALS` | `true` | Enable human approval gate |

Data paths (SQLite, Chroma, documents) are derived from the project root and created automatically on startup.

---

## Key Design Patterns

**ReAct loop** — Claude reasons, picks a tool, observes the result, and iterates. All tool calls are logged and shown to the PM, making reasoning transparent.

**Modular tools** — Each tool module is independent. Adding a new data source means writing one `@tool` function and adding it to the agent's tool list in `pm_agent.py`.

**Layered guardrails** — Input, output, and approval checks are separate modules. Each can be tuned or replaced without touching the agent logic.

**Append-only audit log** — JSONL is immutable by convention. Trace IDs make it straightforward to audit any individual turn for compliance or debugging.

**System prompt rebuilt per turn** — PM preferences are re-fetched and injected fresh on every call, so preference changes take effect immediately without restarting anything.
