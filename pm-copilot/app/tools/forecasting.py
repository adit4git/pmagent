"""Simple forecasting tool.

Deliberately minimal — a tiny mean-reversion + drift model. The point is
that the agent learns when to invoke a forecast and how to *interpret* its
output, including caveats. Not the model itself.

For a more advanced exercise, swap this for ARIMA, Prophet, or a
pre-trained Hugging Face time-series model.
"""
from __future__ import annotations

import json
import math

from langchain_core.tools import tool

from app.audit import log_event
from app.tools.firm_db import _current_trace_id
from app.tools.market_data import _synthetic_price


@tool
def forecast_return(ticker: str, horizon_days: int = 30) -> str:
    """Generate a naive return forecast for a ticker over a given horizon.

    IMPORTANT: This is a simple statistical model intended for illustrative
    purposes. It returns an expected return and confidence interval — but you
    must always communicate the model's limitations to the user and never
    present the output as a personalized recommendation.

    Args:
        ticker: Ticker symbol, e.g. 'VTI'.
        horizon_days: Forecast horizon in calendar days (1-365).
    """
    ticker = ticker.upper().strip()
    horizon_days = max(1, min(int(horizon_days), 365))

    # Toy model: assume 7% annualized expected return, 16% annualized vol.
    # Scale by horizon. Add small ticker-specific tilt for variety.
    base_annual_ret = 0.07
    base_annual_vol = 0.16
    # Light tilt
    tilt = (sum(ord(c) for c in ticker) % 7 - 3) / 100  # ±0.03
    expected = base_annual_ret + tilt
    horizon_years = horizon_days / 365
    expected_return = expected * horizon_years
    expected_vol = base_annual_vol * math.sqrt(horizon_years)

    payload = {
        "ticker": ticker,
        "horizon_days": horizon_days,
        "expected_return_pct": round(100 * expected_return, 2),
        "vol_pct": round(100 * expected_vol, 2),
        "ci_95_low_pct": round(100 * (expected_return - 1.96 * expected_vol), 2),
        "ci_95_high_pct": round(100 * (expected_return + 1.96 * expected_vol), 2),
        "model": "naive_drift_v0",
        "caveats": [
            "Toy model for illustration only.",
            "Assumes constant vol and normality — both wrong in practice.",
            "Does not incorporate firm research views or current market regime.",
        ],
    }
    log_event("tool_call", trace_id=_current_trace_id, payload={
        "tool": "forecast_return",
        "args": {"ticker": ticker, "horizon_days": horizon_days},
        "result_summary": f"E[r]={payload['expected_return_pct']}%",
    })
    return json.dumps(payload)


FORECAST_TOOLS = [forecast_return]
