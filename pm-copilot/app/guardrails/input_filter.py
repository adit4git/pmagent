"""Input filtering: detect PII and obvious prompt-injection patterns
before they reach the LLM.

This is intentionally simple — pattern-based — so it's transparent.
Production systems use ML classifiers (e.g., Microsoft Presidio for PII)
plus dedicated prompt-injection models. The hooks here are the same.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.audit import log_event

# US SSN, credit card-ish, email, phone
_PII_PATTERNS = {
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "credit_card": re.compile(r"\b(?:\d[ -]*?){13,16}\b"),
    "email": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
    "phone": re.compile(r"\b\(?\d{3}\)?[ .-]?\d{3}[ .-]?\d{4}\b"),
}

_INJECTION_PATTERNS = [
    re.compile(r"ignore (previous|all|prior) instructions", re.I),
    re.compile(r"disregard (the|your) (system|prior)", re.I),
    re.compile(r"you are now (a|an) [a-z]+", re.I),
    re.compile(r"reveal (your|the) (system )?prompt", re.I),
]


@dataclass
class InputCheck:
    allowed: bool
    reasons: list[str]
    redacted_input: str


def screen_input(text: str, *, trace_id: str) -> InputCheck:
    reasons: list[str] = []
    redacted = text

    for label, pat in _PII_PATTERNS.items():
        if pat.search(text):
            reasons.append(f"pii_detected:{label}")
            redacted = pat.sub(f"[REDACTED_{label.upper()}]", redacted)

    for pat in _INJECTION_PATTERNS:
        if pat.search(text):
            reasons.append("prompt_injection_pattern")
            break

    allowed = "prompt_injection_pattern" not in reasons
    log_event("input_screen", trace_id=trace_id, payload={
        "reasons": reasons,
        "allowed": allowed,
    })
    return InputCheck(allowed=allowed, reasons=reasons, redacted_input=redacted)
