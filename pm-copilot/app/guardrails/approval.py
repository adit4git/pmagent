"""Human-in-the-loop approval gate.

The agent flags certain actions (rebalancing proposals, large hypothetical
trades) as "high impact." These bubble up through this gate. In CLI mode
we prompt on stdin; in the Streamlit UI, the surrounding app handles it.

Per firm compliance FAQ, anything that could be construed as a personalized
trade recommendation requires PM sign-off before execution.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.audit import log_event
from app.config import settings


@dataclass
class ApprovalRequest:
    action_type: str        # e.g. "rebalancing_proposal"
    summary: str
    details: dict


def needs_approval(action_type: str) -> bool:
    if not settings.require_approval_for_proposals:
        return False
    high_impact = {
        "rebalancing_proposal",
        "trade_proposal",
        "client_communication_send",
    }
    return action_type in high_impact


def cli_approval_prompt(req: ApprovalRequest, *, trace_id: str) -> bool:
    """Block on stdin for an approval. Returns True if approved."""
    print("\n" + "=" * 60)
    print(f"[HUMAN APPROVAL REQUIRED — {req.action_type}]")
    print("=" * 60)
    print(req.summary)
    print("-" * 60)
    if req.details:
        for k, v in req.details.items():
            print(f"  {k}: {v}")
    print("=" * 60)
    answer = input("Approve? [y/N]: ").strip().lower()
    approved = answer in {"y", "yes"}
    log_event("approval_decision", trace_id=trace_id, payload={
        "action_type": req.action_type,
        "approved": approved,
    })
    return approved
