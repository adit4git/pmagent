"""Output filter: catches problematic language before it reaches the user.

Watches for two patterns:
  1. Unhedged client-facing trade recommendations ("you should buy X").
  2. Missing AI-disclosure when the response looks client-facing.

Real systems would also redact PII in outputs and run a moderation model.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.audit import log_event

_RECOMMENDATION_PATTERNS = [
    re.compile(r"\byou should (buy|sell|short)\b", re.I),
    re.compile(r"\bI recommend (buying|selling)\b", re.I),
    re.compile(r"\bguaranteed (return|profit|gain)\b", re.I),
]

_DISCLAIMER_FRAGMENT = "not a personalized investment recommendation"


@dataclass
class OutputCheck:
    allowed: bool
    revised_output: str
    flags: list[str]


def screen_output(
    text: str, *, trace_id: str, is_client_facing_draft: bool = False
) -> OutputCheck:
    flags: list[str] = []
    revised = text

    for pat in _RECOMMENDATION_PATTERNS:
        if pat.search(text):
            flags.append("unhedged_recommendation_language")
            revised = pat.sub("[review needed: hedged language required]", revised)

    if is_client_facing_draft and _DISCLAIMER_FRAGMENT not in text.lower():
        flags.append("missing_ai_disclaimer")
        revised += (
            "\n\n---\n*Analysis prepared with assistance from internal AI tools "
            "and reviewed by your portfolio manager. Past performance does not "
            "guarantee future results. This is not a personalized investment "
            "recommendation.*"
        )

    log_event("output_screen", trace_id=trace_id, payload={
        "flags": flags,
        "is_client_facing_draft": is_client_facing_draft,
    })
    return OutputCheck(allowed=True, revised_output=revised, flags=flags)
