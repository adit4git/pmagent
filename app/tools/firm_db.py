"""Firm database tools.

These wrap structured queries against the mock SQLite firm DB. In production
each of these would map to a service team's API; the schema-first pattern is
the same.

The agent calls these via LangChain's @tool decorator. Each function:
- has a clear docstring (the LLM reads this!)
- returns JSON-friendly dicts
- logs every call to the audit log
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from typing import Any

from langchain_core.tools import tool

from app.audit import log_event
from app.config import settings


@contextmanager
def _conn():
    con = sqlite3.connect(settings.sqlite_path)
    con.row_factory = sqlite3.Row
    try:
        yield con
    finally:
        con.close()


def _rows_to_dicts(rows) -> list[dict[str, Any]]:
    return [dict(r) for r in rows]


# Trace id is set per-turn by the agent runner via this module-level slot.
# Crude but keeps tool signatures clean for the LLM.
_current_trace_id: str = "no-trace"


def set_trace_id(trace_id: str) -> None:
    global _current_trace_id
    _current_trace_id = trace_id


def _audit(tool_name: str, args: dict, result_summary: str) -> None:
    log_event(
        "tool_call",
        trace_id=_current_trace_id,
        payload={"tool": tool_name, "args": args, "result_summary": result_summary},
    )


@tool
def list_clients() -> str:
    """List all clients managed by the current portfolio manager.
    Returns a JSON array of {client_id, name, risk_profile, aum_usd}.
    Use this when the user mentions a client by name and you need their client_id."""
    with _conn() as con:
        rows = con.execute(
            "SELECT client_id, name, risk_profile, aum_usd FROM clients"
        ).fetchall()
    out = _rows_to_dicts(rows)
    _audit("list_clients", {}, f"{len(out)} clients")
    return json.dumps(out)


@tool
def get_client_summary(client_id: str) -> str:
    """Return a full summary for a client: profile, risk, notes, portfolios,
    target allocations, current allocation drift, and recent trades.

    Args:
        client_id: Internal client id like 'C001'. Use list_clients first
                   if you only have a name.
    """
    with _conn() as con:
        client = con.execute(
            "SELECT * FROM clients WHERE client_id = ?", (client_id,)
        ).fetchone()
        if not client:
            _audit("get_client_summary", {"client_id": client_id}, "not found")
            return json.dumps({"error": f"client {client_id} not found"})

        portfolios = con.execute(
            "SELECT * FROM portfolios WHERE client_id = ?", (client_id,)
        ).fetchall()

        result = {"client": dict(client), "portfolios": []}
        for p in portfolios:
            pid = p["portfolio_id"]
            targets = con.execute(
                "SELECT asset_class, target_pct FROM target_allocations "
                "WHERE portfolio_id = ?", (pid,)
            ).fetchall()
            holdings = con.execute(
                "SELECT ticker, asset_class, shares, cost_basis_usd "
                "FROM holdings WHERE portfolio_id = ?", (pid,)
            ).fetchall()
            trades = con.execute(
                "SELECT trade_date, ticker, side, shares, price_usd "
                "FROM trades WHERE portfolio_id = ? "
                "ORDER BY trade_date DESC LIMIT 10", (pid,)
            ).fetchall()

            # Compute current allocation using cost basis as a stand-in for MV.
            # In a real system you'd hit a pricing service.
            holdings_d = _rows_to_dicts(holdings)
            total = sum(h["shares"] * h["cost_basis_usd"] for h in holdings_d)
            current = {}
            for h in holdings_d:
                ac = h["asset_class"]
                current[ac] = current.get(ac, 0) + h["shares"] * h["cost_basis_usd"]
            current_pct = {
                ac: round(100 * v / total, 2) for ac, v in current.items()
            } if total else {}

            targets_d = {t["asset_class"]: t["target_pct"] for t in targets}
            drift = {
                ac: round(current_pct.get(ac, 0) - targets_d.get(ac, 0), 2)
                for ac in set(list(current_pct.keys()) + list(targets_d.keys()))
            }

            result["portfolios"].append({
                "portfolio": dict(p),
                "target_allocation_pct": targets_d,
                "current_allocation_pct": current_pct,
                "drift_pct": drift,
                "holdings": holdings_d,
                "recent_trades": _rows_to_dicts(trades),
                "total_value_usd_estimated": round(total, 2),
            })

    _audit(
        "get_client_summary",
        {"client_id": client_id},
        f"{len(result['portfolios'])} portfolios",
    )
    return json.dumps(result)


@tool
def get_top_holdings(client_id: str, n: int = 5) -> str:
    """Get the top N holdings (by cost-basis dollar value) across all
    portfolios for a client.

    Args:
        client_id: Internal client id like 'C002'.
        n: How many holdings to return. Defaults to 5.
    """
    with _conn() as con:
        rows = con.execute(
            """
            SELECT h.ticker, h.asset_class,
                   SUM(h.shares * h.cost_basis_usd) AS value_usd
            FROM holdings h
            JOIN portfolios p ON h.portfolio_id = p.portfolio_id
            WHERE p.client_id = ? AND h.ticker != 'CASH'
            GROUP BY h.ticker
            ORDER BY value_usd DESC
            LIMIT ?
            """,
            (client_id, n),
        ).fetchall()
    out = _rows_to_dicts(rows)
    _audit("get_top_holdings", {"client_id": client_id, "n": n}, f"{len(out)} rows")
    return json.dumps(out)


FIRM_DB_TOOLS = [list_clients, get_client_summary, get_top_holdings]
