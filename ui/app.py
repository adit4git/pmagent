"""Streamlit chat UI for PM Copilot.

Run:  streamlit run ui/app.py

Shows the agent's tool trace alongside the answer so PMs (and learners)
can see exactly what was consulted.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make the app package importable when running via streamlit
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

from app.agents.pm_agent import run  # noqa: E402
from app.config import settings  # noqa: E402
from app.guardrails.approval import ApprovalRequest  # noqa: E402

st.set_page_config(page_title="PM Copilot", page_icon="📊", layout="wide")

st.title("📊 PM Copilot")
st.caption(f"model: `{settings.anthropic_model}` · approval gate: "
           f"`{settings.require_approval_for_proposals}`")

with st.sidebar:
    st.header("About")
    st.markdown(
        "Agentic AI starter for portfolio managers. The agent has access "
        "to firm DB tools, internal RAG over policy + research, market data, "
        "news, and a toy forecast tool."
    )
    st.divider()
    st.subheader("Sample queries")
    samples = [
        "Summarize the Johnson family account and flag any drift from target.",
        "What's our firm's view on tech sector exposure?",
        "Recent news on the top Chen holdings before tomorrow's meeting?",
        "Draft a rebalancing proposal for the Patel account.",
    ]
    for s in samples:
        if st.button(s, use_container_width=True):
            st.session_state["queued_input"] = s

    st.divider()
    if st.button("Clear conversation"):
        st.session_state.pop("messages", None)
        st.rerun()

if "messages" not in st.session_state:
    st.session_state["messages"] = []
if "pending_approval" not in st.session_state:
    st.session_state["pending_approval"] = None

# Render history
for msg in st.session_state["messages"]:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("trace"):
            with st.expander("🔍 Agent trace"):
                for step in msg["trace"]:
                    if "name" in step:
                        st.markdown(f"**call** `{step['name']}` — `{step.get('args', {})}`")
                    else:
                        st.markdown(
                            f"**result** ← `{step.get('tool_result_for', '?')}`  \n"
                            f"```\n{step.get('preview', '')}\n```"
                        )
        if msg.get("flags"):
            st.warning("Flags: " + ", ".join(msg["flags"]))

# Approval gate via Streamlit (replaces the CLI prompt)
def streamlit_approver(req: ApprovalRequest, *, trace_id: str) -> bool:
    # Stash the request and stop; user clicks button to resume.
    st.session_state["pending_approval"] = {
        "req": req, "trace_id": trace_id,
    }
    return False  # always returns False on first pass; UI handles re-run


if st.session_state["pending_approval"]:
    pa = st.session_state["pending_approval"]
    st.warning(f"Approval required: {pa['req'].action_type}")
    with st.expander("Proposal preview", expanded=True):
        st.markdown(pa["req"].details.get("preview", ""))
    c1, c2 = st.columns(2)
    if c1.button("✅ Approve"):
        st.session_state["messages"].append({
            "role": "assistant",
            "content": "Proposal approved. (In a real system this would route to the trading desk.)",
        })
        st.session_state["pending_approval"] = None
        st.rerun()
    if c2.button("❌ Decline"):
        st.session_state["messages"].append({
            "role": "assistant",
            "content": "Proposal declined. Draft retained for your reference.",
        })
        st.session_state["pending_approval"] = None
        st.rerun()

# Input
prompt = st.session_state.pop("queued_input", None) or st.chat_input("Ask about a client…")

if prompt:
    st.session_state["messages"].append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("thinking…"):
            result = run(prompt, on_approval=streamlit_approver)
        st.markdown(result.final_text)
        with st.expander("🔍 Agent trace"):
            if result.tool_calls:
                for step in result.tool_calls:
                    if "name" in step:
                        st.markdown(f"**call** `{step['name']}` — `{step.get('args', {})}`")
                    else:
                        st.markdown(
                            f"**result** ← `{step.get('tool_result_for', '?')}`  \n"
                            f"```\n{step.get('preview', '')}\n```"
                        )
            else:
                st.markdown("_(no tool calls)_")
        if result.flags:
            st.warning("Flags: " + ", ".join(result.flags))
        st.caption(f"trace_id: `{result.trace_id}`")

    st.session_state["messages"].append({
        "role": "assistant",
        "content": result.final_text,
        "trace": result.tool_calls,
        "flags": result.flags,
    })
