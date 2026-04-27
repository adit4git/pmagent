"""Run evals.

    python -m app.evals.run_evals

Three checks per case:
  1. Required tools were called.
  2. Some expected keyword shows up in the answer.
  3. No forbidden phrase shows up in the answer.

Tool-call accuracy and forbidden-phrase checks are deterministic — that's
on purpose. LLM-as-judge for rubric evaluation is a great next step
(mirror this structure with a judge prompt).
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass

from rich.console import Console
from rich.table import Table

from app.agents.pm_agent import run
from app.config import settings
from app.evals.eval_set import CASES, EvalCase

console = Console()


@dataclass
class CaseResult:
    name: str
    passed: bool
    tool_check: bool
    keyword_check: bool
    forbidden_check: bool
    notes: str
    trace_id: str


def _evaluate(case: EvalCase) -> CaseResult:
    # Disable approval gate for evals so they run unattended
    os.environ["REQUIRE_APPROVAL_FOR_PROPOSALS"] = "false"
    result = run(case.query)
    text_lower = result.final_text.lower()
    tool_names = {tc["name"] for tc in result.tool_calls if "name" in tc}

    tool_check = all(t in tool_names for t in case.required_tools)

    if case.expected_keywords_any:
        keyword_check = any(k.lower() in text_lower for k in case.expected_keywords_any)
    else:
        keyword_check = True

    forbidden_check = not any(p.lower() in text_lower for p in case.forbidden_phrases)

    passed = tool_check and keyword_check and forbidden_check
    notes = []
    if not tool_check:
        missing = [t for t in case.required_tools if t not in tool_names]
        notes.append(f"missing tools: {missing}")
    if not keyword_check:
        notes.append("no expected keyword found")
    if not forbidden_check:
        notes.append("forbidden phrase present")

    return CaseResult(
        name=case.name, passed=passed, tool_check=tool_check,
        keyword_check=keyword_check, forbidden_check=forbidden_check,
        notes="; ".join(notes) or "ok",
        trace_id=result.trace_id,
    )


def main() -> int:
    if not settings.has_anthropic_api_key():
        console.print("[red]ANTHROPIC_API_KEY not set.[/red]")
        return 1

    table = Table(title="PM Copilot Evals", show_header=True, header_style="bold cyan")
    table.add_column("Case")
    table.add_column("Tools", justify="center")
    table.add_column("Keywords", justify="center")
    table.add_column("Forbidden", justify="center")
    table.add_column("Pass", justify="center")
    table.add_column("Notes")

    passed = 0
    for case in CASES:
        console.print(f"[dim]running {case.name}…[/dim]")
        r = _evaluate(case)
        if r.passed:
            passed += 1
        table.add_row(
            r.name,
            "✓" if r.tool_check else "✗",
            "✓" if r.keyword_check else "✗",
            "✓" if r.forbidden_check else "✗",
            "[green]✓[/green]" if r.passed else "[red]✗[/red]",
            r.notes,
        )

    console.print(table)
    console.print(f"\n[bold]{passed}/{len(CASES)} passed[/bold]")
    return 0 if passed == len(CASES) else 1


if __name__ == "__main__":
    sys.exit(main())
