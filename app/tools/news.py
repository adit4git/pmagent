"""Financial news tool.

Uses Yahoo Finance RSS (free, no auth) for ticker-specific news. Falls back
to a small canned list when offline. Returns headlines + summaries the agent
can synthesize.
"""
from __future__ import annotations

import json
from datetime import datetime
from urllib.error import URLError

from langchain_core.tools import tool

from app.audit import log_event
from app.tools.firm_db import _current_trace_id

try:
    import feedparser
    FP_AVAILABLE = True
except ImportError:
    FP_AVAILABLE = False


_FALLBACK_NEWS = {
    "AAPL": [
        {"title": "Apple expands services revenue ahead of expectations",
         "summary": "Services segment continues to grow double digits, offsetting iPhone unit weakness.",
         "published": "2025-01-15"},
    ],
    "NVDA": [
        {"title": "NVIDIA guides next quarter above consensus on AI demand",
         "summary": "Hyperscaler capex remains robust despite digestion narrative.",
         "published": "2025-01-12"},
    ],
    "MSFT": [
        {"title": "Microsoft's AI infrastructure spend faces investor scrutiny",
         "summary": "Capex trajectory questioned as AI revenue ramp moderates.",
         "published": "2025-01-10"},
    ],
}


@tool
def get_recent_news(ticker: str, max_items: int = 5) -> str:
    """Get recent news headlines for a ticker. Returns title, summary, and
    publication date for each item. Use this to surface material developments
    on a holding.

    Args:
        ticker: The ticker symbol, e.g. 'NVDA'.
        max_items: Maximum number of news items. Defaults to 5.
    """
    ticker = ticker.upper().strip()
    items: list[dict] = []

    if FP_AVAILABLE:
        url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US"
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:max_items]:
                items.append({
                    "title": entry.get("title", ""),
                    "summary": entry.get("summary", "")[:400],
                    "published": entry.get("published", ""),
                    "link": entry.get("link", ""),
                })
        except (URLError, Exception):
            pass

    if not items:
        items = _FALLBACK_NEWS.get(ticker, [{
            "title": f"No recent news available for {ticker}",
            "summary": "News feed unavailable; check primary sources.",
            "published": datetime.now().date().isoformat(),
        }])
        source_note = "fallback"
    else:
        source_note = "yahoo_rss"

    log_event("tool_call", trace_id=_current_trace_id, payload={
        "tool": "get_recent_news",
        "args": {"ticker": ticker, "max_items": max_items},
        "result_summary": f"{len(items)} items from {source_note}",
    })
    return json.dumps({"ticker": ticker, "source": source_note, "items": items})


NEWS_TOOLS = [get_recent_news]
