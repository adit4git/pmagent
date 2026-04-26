"""External market data tool.

Wraps yfinance for real quotes when reachable. Falls back to deterministic
synthetic data so the agent always has something to reason about even when
offline or rate-limited (this happens often with free APIs — a good lesson
in resilience).
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta

from langchain_core.tools import tool

from app.audit import log_event
from app.tools.firm_db import _current_trace_id

try:
    import yfinance as yf
    YF_AVAILABLE = True
except ImportError:
    YF_AVAILABLE = False


def _synthetic_price(ticker: str) -> float:
    """Deterministic pseudo-price so the same ticker gets a stable number."""
    h = int(hashlib.md5(ticker.encode()).hexdigest(), 16)
    base = 50 + (h % 400)
    return round(base + (h % 100) / 10.0, 2)


def _synthetic_change(ticker: str) -> float:
    h = int(hashlib.md5((ticker + "chg").encode()).hexdigest(), 16)
    return round(((h % 600) - 300) / 100.0, 2)  # -3.00 to +3.00 percent


@tool
def get_quote(ticker: str) -> str:
    """Get a current market quote for a ticker symbol. Returns price,
    daily change %, and 52-week range when available.

    Args:
        ticker: Stock or ETF ticker, e.g. 'AAPL', 'VTI', 'NVDA'.
    """
    ticker = ticker.upper().strip()
    payload: dict = {"ticker": ticker}

    if YF_AVAILABLE:
        try:
            info = yf.Ticker(ticker).fast_info
            price = getattr(info, "last_price", None)
            if price:
                prev = getattr(info, "previous_close", None) or price
                change_pct = round(100 * (price - prev) / prev, 2) if prev else 0.0
                payload.update({
                    "price_usd": round(float(price), 2),
                    "daily_change_pct": change_pct,
                    "52w_high": float(getattr(info, "year_high", None) or 0),
                    "52w_low": float(getattr(info, "year_low", None) or 0),
                    "source": "yfinance",
                })
                log_event("tool_call", trace_id=_current_trace_id, payload={
                    "tool": "get_quote", "args": {"ticker": ticker},
                    "result_summary": f"{ticker}=${payload['price_usd']}",
                })
                return json.dumps(payload)
        except Exception as e:
            payload["yfinance_error"] = str(e)

    # Fallback
    payload.update({
        "price_usd": _synthetic_price(ticker),
        "daily_change_pct": _synthetic_change(ticker),
        "52w_high": round(_synthetic_price(ticker) * 1.25, 2),
        "52w_low": round(_synthetic_price(ticker) * 0.75, 2),
        "source": "synthetic_fallback",
        "note": "Real data unavailable; using deterministic synthetic price for development.",
    })
    log_event("tool_call", trace_id=_current_trace_id, payload={
        "tool": "get_quote", "args": {"ticker": ticker},
        "result_summary": f"{ticker} (synthetic) ${payload['price_usd']}",
    })
    return json.dumps(payload)


@tool
def get_sector_snapshot(sector: str) -> str:
    """Get a brief market snapshot for a sector. Uses a small basket of
    representative ETFs.

    Args:
        sector: One of: tech, financials, healthcare, energy, consumer,
                broad_market, bonds.
    """
    baskets = {
        "tech": ["XLK", "QQQ"],
        "financials": ["XLF"],
        "healthcare": ["XLV"],
        "energy": ["XLE"],
        "consumer": ["XLY", "XLP"],
        "broad_market": ["SPY", "VTI"],
        "bonds": ["BND", "AGG"],
    }
    sector = sector.lower().strip()
    tickers = baskets.get(sector, [])
    if not tickers:
        return json.dumps({
            "error": f"unknown sector '{sector}'",
            "valid_sectors": list(baskets.keys()),
        })
    quotes = [json.loads(get_quote.invoke({"ticker": t})) for t in tickers]
    avg_change = round(sum(q["daily_change_pct"] for q in quotes) / len(quotes), 2)
    out = {
        "sector": sector,
        "representative_etfs": tickers,
        "quotes": quotes,
        "avg_daily_change_pct": avg_change,
    }
    log_event("tool_call", trace_id=_current_trace_id, payload={
        "tool": "get_sector_snapshot", "args": {"sector": sector},
        "result_summary": f"{sector} avg={avg_change}%",
    })
    return json.dumps(out)


MARKET_TOOLS = [get_quote, get_sector_snapshot]
