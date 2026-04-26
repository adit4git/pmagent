"""Seed the mock firm SQLite database with synthetic clients, portfolios,
holdings, target allocations, and recent trades. Run once before starting
the agent:

    python -m app.data.seed_db
"""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from app.config import settings

SCHEMA = """
DROP TABLE IF EXISTS trades;
DROP TABLE IF EXISTS holdings;
DROP TABLE IF EXISTS target_allocations;
DROP TABLE IF EXISTS portfolios;
DROP TABLE IF EXISTS clients;

CREATE TABLE clients (
    client_id        TEXT PRIMARY KEY,
    name             TEXT NOT NULL,
    risk_profile     TEXT NOT NULL,           -- conservative | moderate | aggressive
    investment_horizon_years INTEGER NOT NULL,
    aum_usd          REAL NOT NULL,
    notes            TEXT,
    pm_id            TEXT NOT NULL
);

CREATE TABLE portfolios (
    portfolio_id     TEXT PRIMARY KEY,
    client_id        TEXT NOT NULL REFERENCES clients(client_id),
    name             TEXT NOT NULL,
    inception_date   TEXT NOT NULL
);

CREATE TABLE target_allocations (
    portfolio_id     TEXT NOT NULL REFERENCES portfolios(portfolio_id),
    asset_class      TEXT NOT NULL,           -- equities | fixed_income | cash | alternatives
    target_pct       REAL NOT NULL,
    PRIMARY KEY (portfolio_id, asset_class)
);

CREATE TABLE holdings (
    portfolio_id     TEXT NOT NULL REFERENCES portfolios(portfolio_id),
    ticker           TEXT NOT NULL,
    asset_class      TEXT NOT NULL,
    shares           REAL NOT NULL,
    cost_basis_usd   REAL NOT NULL,
    PRIMARY KEY (portfolio_id, ticker)
);

CREATE TABLE trades (
    trade_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    portfolio_id     TEXT NOT NULL REFERENCES portfolios(portfolio_id),
    trade_date       TEXT NOT NULL,
    ticker           TEXT NOT NULL,
    side             TEXT NOT NULL,           -- BUY | SELL
    shares           REAL NOT NULL,
    price_usd        REAL NOT NULL
);
"""

CLIENTS = [
    # client_id, name, risk_profile, horizon, aum, notes, pm_id
    ("C001", "Johnson Family Trust", "moderate", 15, 4_250_000,
     "Multi-generational trust. ESG screen requested. Quarterly reviews.", "PM01"),
    ("C002", "Chen Household", "aggressive", 25, 1_850_000,
     "Tech-heavy bias acceptable. Tax-loss harvesting on. Owner is 38.", "PM01"),
    ("C003", "Patel Retirement Account", "conservative", 8, 2_100_000,
     "Retiring in ~8 years. Capital preservation is priority. No leverage.", "PM01"),
    ("C004", "Garcia Foundation", "moderate", 30, 12_400_000,
     "Endowment. 4.5% annual draw. Mission-aligned investing required.", "PM01"),
]

PORTFOLIOS = [
    ("P001", "C001", "Johnson Core Portfolio", "2014-03-01"),
    ("P002", "C002", "Chen Growth Portfolio", "2018-08-15"),
    ("P003", "C003", "Patel Income & Preservation", "2019-01-10"),
    ("P004", "C004", "Garcia Endowment Pool", "2010-06-30"),
]

TARGETS = [
    # portfolio_id, asset_class, target_pct
    ("P001", "equities", 60), ("P001", "fixed_income", 30),
    ("P001", "cash", 5), ("P001", "alternatives", 5),

    ("P002", "equities", 85), ("P002", "fixed_income", 10),
    ("P002", "cash", 2), ("P002", "alternatives", 3),

    ("P003", "equities", 35), ("P003", "fixed_income", 55),
    ("P003", "cash", 10), ("P003", "alternatives", 0),

    ("P004", "equities", 55), ("P004", "fixed_income", 25),
    ("P004", "cash", 5), ("P004", "alternatives", 15),
]

HOLDINGS = [
    # portfolio_id, ticker, asset_class, shares, cost_basis
    # Johnson — slightly equity-overweight (drift to flag)
    ("P001", "VTI",  "equities",     8000, 180.00),
    ("P001", "VXUS", "equities",     6000,  55.00),
    ("P001", "BND",  "fixed_income", 9000,  78.00),
    ("P001", "VNQ",  "alternatives", 1500,  85.00),
    ("P001", "CASH", "cash",         150000, 1.0),

    # Chen — heavy tech, aggressive
    ("P002", "AAPL", "equities", 2000, 145.00),
    ("P002", "MSFT", "equities", 1200, 280.00),
    ("P002", "NVDA", "equities",  600, 220.00),
    ("P002", "GOOGL","equities",  900, 130.00),
    ("P002", "VTI",  "equities", 1500, 200.00),
    ("P002", "BND",  "fixed_income", 1800, 78.00),
    ("P002", "CASH", "cash",        30000, 1.0),

    # Patel — conservative, bond-heavy
    ("P003", "BND",  "fixed_income", 14000, 80.00),
    ("P003", "VTIP", "fixed_income",  5000, 50.00),
    ("P003", "VTI",  "equities",      3500, 190.00),
    ("P003", "VYM",  "equities",      2000, 105.00),
    ("P003", "CASH", "cash",         210000, 1.0),

    # Garcia
    ("P004", "VTI",  "equities",     20000, 195.00),
    ("P004", "VXUS", "equities",     14000,  56.00),
    ("P004", "BND",  "fixed_income", 22000,  80.00),
    ("P004", "VNQ",  "alternatives",  6000,  90.00),
    ("P004", "GLD",  "alternatives",  2500, 165.00),
    ("P004", "CASH", "cash",         620000, 1.0),
]


def _recent_trades() -> list[tuple]:
    today = date.today()
    rows = []
    samples = [
        ("P002", "NVDA",  "BUY",   100, 850.00, 12),
        ("P002", "AAPL",  "SELL",  150, 195.00, 30),
        ("P001", "VTI",   "BUY",   500, 245.00,  6),
        ("P003", "BND",   "BUY",  1000,  74.50, 18),
        ("P004", "VXUS",  "BUY",  2000,  62.00,  9),
    ]
    for portfolio_id, ticker, side, shares, price, days_ago in samples:
        rows.append((
            portfolio_id,
            (today - timedelta(days=days_ago)).isoformat(),
            ticker, side, shares, price,
        ))
    return rows


def main() -> None:
    settings.ensure_dirs()
    if settings.sqlite_path.exists():
        settings.sqlite_path.unlink()

    conn = sqlite3.connect(settings.sqlite_path)
    try:
        conn.executescript(SCHEMA)
        conn.executemany(
            "INSERT INTO clients VALUES (?, ?, ?, ?, ?, ?, ?)", CLIENTS
        )
        conn.executemany(
            "INSERT INTO portfolios VALUES (?, ?, ?, ?)", PORTFOLIOS
        )
        conn.executemany(
            "INSERT INTO target_allocations VALUES (?, ?, ?)", TARGETS
        )
        conn.executemany(
            "INSERT INTO holdings VALUES (?, ?, ?, ?, ?)", HOLDINGS
        )
        conn.executemany(
            "INSERT INTO trades(portfolio_id, trade_date, ticker, side, shares, price_usd) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            _recent_trades(),
        )
        conn.commit()
    finally:
        conn.close()

    print(f"✓ Seeded firm DB at {settings.sqlite_path}")
    print(f"  {len(CLIENTS)} clients, {len(PORTFOLIOS)} portfolios, "
          f"{len(HOLDINGS)} holdings")


if __name__ == "__main__":
    main()
