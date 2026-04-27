"""The PM Copilot agent.

LangGraph's prebuilt ReAct agent gives us the loop (model → tools → model
→ ... → final answer) without us having to hand-roll it. The interesting
work is in:

  - SYSTEM_PROMPT: the role, guardrails, citation rules, and output norms
  - the tool list: what capabilities we expose
  - the wrapper run() function: where input/output guardrails fire and
    where human approval is requested for high-impact actions

For learning: read this file last. The tools and guardrails make more
sense once you've seen the pieces.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langgraph.prebuilt import create_react_agent

from app.audit import log_event, new_trace_id
from app.config import settings
from app.guardrails.approval import (
    ApprovalRequest,
    cli_approval_prompt,
    needs_approval,
)
from app.guardrails.input_filter import screen_input
from app.guardrails.output_filter import screen_output
from app.memory.preferences import get_pm_name, get_preferences
from app.tools import firm_db
from app.tools.firm_db import FIRM_DB_TOOLS
from app.tools.forecasting import FORECAST_TOOLS
from app.tools.market_data import MARKET_TOOLS
from app.tools.news import NEWS_TOOLS
from app.tools.rag import RAG_TOOLS

ALL_TOOLS = FIRM_DB_TOOLS + RAG_TOOLS + MARKET_TOOLS + NEWS_TOOLS + FORECAST_TOOLS


SYSTEM_PROMPT = """You are PM Copilot, an AI assistant for portfolio managers \
at Acme Wealth, a registered investment advisor.

# Who you serve
You assist {pm_name} (PM ID: {pm_id}) in researching client accounts, \
synthesizing internal and external information, and DRAFTING (never executing) \
portfolio actions for human review.

# Their standing preferences
{preferences_block}

# How to work
1. Plan briefly before acting. State which tools you intend to use and why.
2. Prefer the firm DB tools for client/portfolio facts. Never invent client \
data — if you don't have it, fetch it.
3. For firm policy, internal views, or compliance questions, use \
search_firm_knowledge and CITE THE SOURCE FILE in your final answer (e.g. \
"per IPS-2024-v3"). Citations are mandatory.
4. For market context, use the market data and news tools. Note when data \
is from the synthetic fallback.
5. When proposing any portfolio action (rebalance, trade idea), label it \
clearly as a PROPOSAL FOR PM REVIEW. Include the rationale, expected impact, \
relevant policy thresholds, and risks. Never write "you should buy/sell" — \
use language like "consider", "candidate for", "would bring allocation to".
6. For client-facing drafts, append the standard AI-disclosure disclaimer.
7. If the user asks for something outside your tools or that requires \
firm action, say so plainly.

# Hard limits
- Do not recommend specific securities to retail clients directly.
- Do not transmit client PII (names, account numbers) to external tools — \
internal client_ids like C001 are fine.
- Do not claim certainty about future returns.

Be concise. Use tools, don't speculate.
"""


@dataclass
class AgentResult:
    trace_id: str
    final_text: str
    tool_calls: list[dict] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    blocked: bool = False
    block_reason: str | None = None


def _build_agent():
    api_key = settings.anthropic_api_key_value()
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is missing or empty. "
            "Set a non-empty value in Railway Variables."
        )
    llm = ChatAnthropic(
        model=settings.anthropic_model,
        api_key=api_key,
        temperature=0.2,
        max_tokens=2048,
    )
    return create_react_agent(llm, ALL_TOOLS)


def _format_preferences(prefs: list[str]) -> str:
    if not prefs:
        return "(no recorded preferences)"
    return "\n".join(f"- {p}" for p in prefs)


def _detect_proposal(text: str) -> bool:
    """Very cheap classifier for whether the agent is producing a high-impact
    proposal. Keywords-based on purpose — explicit > clever."""
    keywords = (
        "proposal for pm review",
        "rebalancing proposal",
        "trade proposal",
        "candidate for sale",
        "candidate for purchase",
    )
    lower = text.lower()
    return any(k in lower for k in keywords)


def run(
    user_message: str,
    *,
    pm_id: str = "PM01",
    history: list | None = None,
    on_approval=None,
) -> AgentResult:
    """Execute one user turn through the full agent + guardrail stack.

    Args:
        user_message: The PM's question or instruction.
        pm_id: Which PM is asking (selects preferences).
        history: Prior LangChain messages for multi-turn context.
        on_approval: Callable(ApprovalRequest, trace_id) -> bool for human
                     approval. Defaults to a CLI prompt.
    """
    trace_id = new_trace_id()
    firm_db.set_trace_id(trace_id)
    log_event("turn_start", trace_id=trace_id, payload={
        "pm_id": pm_id, "user_message": user_message,
    })

    # 1. Input screening
    check = screen_input(user_message, trace_id=trace_id)
    if not check.allowed:
        msg = (
            "I can't process that — it appears to contain a prompt-injection "
            "pattern. Please rephrase."
        )
        return AgentResult(
            trace_id=trace_id, final_text=msg, flags=check.reasons,
            blocked=True, block_reason="input_blocked",
        )
    safe_input = check.redacted_input

    # 2. Build prompt with PM context
    sys_prompt = SYSTEM_PROMPT.format(
        pm_name=get_pm_name(pm_id),
        pm_id=pm_id,
        preferences_block=_format_preferences(get_preferences(pm_id)),
    )

    messages = [SystemMessage(content=sys_prompt)]
    if history:
        messages.extend(history)
    messages.append(HumanMessage(content=safe_input))

    # 3. Invoke the ReAct agent
    agent = _build_agent()
    state = agent.invoke({"messages": messages})
    out_messages = state["messages"]

    # 4. Extract final text + tool call trace
    final_text = ""
    tool_calls: list[dict] = []
    for m in out_messages:
        if isinstance(m, AIMessage):
            if isinstance(m.content, str):
                final_text = m.content
            for tc in (m.tool_calls or []):
                tool_calls.append({"name": tc["name"], "args": tc.get("args", {})})
        elif isinstance(m, ToolMessage):
            tool_calls.append({"tool_result_for": m.name, "preview": str(m.content)[:200]})

    # 5. Output screening
    is_proposal = _detect_proposal(final_text)
    is_client_draft = "client" in user_message.lower() and (
        "draft" in user_message.lower() or "email" in user_message.lower()
    )
    out_check = screen_output(
        final_text, trace_id=trace_id, is_client_facing_draft=is_client_draft,
    )
    final_text = out_check.revised_output

    # 6. Human approval gate for high-impact items
    if is_proposal and needs_approval("rebalancing_proposal"):
        approver = on_approval or cli_approval_prompt
        approved = approver(
            ApprovalRequest(
                action_type="rebalancing_proposal",
                summary="The agent has produced a portfolio action proposal.",
                details={"preview": final_text[:500] + "..."},
            ),
            trace_id=trace_id,
        )
        if not approved:
            final_text = (
                "[Approval declined by PM. Proposal not finalized.]\n\n"
                "Draft for your review only:\n\n" + final_text
            )

    log_event("turn_end", trace_id=trace_id, payload={
        "tool_call_count": len([t for t in tool_calls if "name" in t]),
        "flags": out_check.flags,
    })

    return AgentResult(
        trace_id=trace_id,
        final_text=final_text,
        tool_calls=tool_calls,
        flags=out_check.flags,
    )
