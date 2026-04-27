"""CLI runner for PM Copilot.

Run with:  python -m app.main

Best place to learn from — you see the trace, tool calls, and final output
inline, which is hard to do in a chat UI.
"""
from __future__ import annotations

import sys

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from app.agents.pm_agent import run
from app.config import settings

console = Console()


SAMPLE_QUERIES = [
    "Summarize the Johnson family account and flag any drift from their target allocation.",
    "What's our firm's view on tech sector exposure right now, and how does it compare to recent market moves?",
    "Are there any recent news items for the top holdings in the Chen portfolio I should know about before our meeting?",
    "Draft a rebalancing proposal for the Patel account considering their risk profile and current market conditions.",
]


def _print_header() -> None:
    console.print(Panel.fit(
        "[bold cyan]PM Copilot[/bold cyan] — agentic AI starter\n"
        f"[dim]model: {settings.anthropic_model}  |  approval gate: "
        f"{settings.require_approval_for_proposals}[/dim]",
        border_style="cyan",
    ))
    console.print("\n[bold]Try one of these (paste a number or your own question):[/bold]")
    for i, q in enumerate(SAMPLE_QUERIES, 1):
        console.print(f"  [cyan]{i}[/cyan]. {q}")
    console.print("  [cyan]q[/cyan]. quit\n")


def _print_result(result) -> None:
    console.rule("[dim]agent trace[/dim]")
    if result.tool_calls:
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("#", width=3)
        table.add_column("Step")
        table.add_column("Detail", overflow="fold")
        for i, tc in enumerate(result.tool_calls, 1):
            if "name" in tc:
                table.add_row(str(i), f"call: {tc['name']}", str(tc.get("args", "")))
            else:
                table.add_row(str(i), f"result ← {tc.get('tool_result_for', '?')}",
                              tc.get("preview", "")[:200])
        console.print(table)
    else:
        console.print("[dim](no tool calls — answered from prompt alone)[/dim]")

    if result.flags:
        console.print(f"[yellow]flags: {', '.join(result.flags)}[/yellow]")

    console.rule("[bold green]answer[/bold green]")
    console.print(result.final_text)
    console.print(f"\n[dim]trace_id: {result.trace_id}[/dim]\n")


def main() -> int:
    if not settings.has_anthropic_api_key():
        console.print("[red]ANTHROPIC_API_KEY not set. Copy .env.example to .env and add your key.[/red]")
        return 1

    _print_header()
    history: list = []

    while True:
        try:
            raw = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]bye[/dim]")
            return 0
        if not raw:
            continue
        if raw.lower() in {"q", "quit", "exit"}:
            return 0
        if raw.isdigit() and 1 <= int(raw) <= len(SAMPLE_QUERIES):
            raw = SAMPLE_QUERIES[int(raw) - 1]
            console.print(f"[dim]» {raw}[/dim]")

        with console.status("[cyan]thinking…[/cyan]"):
            result = run(raw, history=history)
        _print_result(result)


if __name__ == "__main__":
    sys.exit(main())
