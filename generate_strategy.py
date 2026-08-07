#!/usr/bin/env python3
"""Generate strategy.json from portfolio-holdings.json using yfinance for
sector, country, and dividend yield data. Only analyzes individual stocks
(not ETFs), as ETFs don't provide meaningful sector/geography breakdowns."""

import json
import os
import sys
import time
from collections import defaultdict
from datetime import date

import yfinance as yf

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PORTFOLIO_PATH = os.path.join(SCRIPT_DIR, "portfolio-holdings.json")
OUTPUT_PATH = os.path.join(SCRIPT_DIR, "strategy.json")

# ETF ticker patterns to exclude from stock-level analysis
ETF_PATTERNS = (".DE", ".L", ".MI", ".PA", ".AS", ".SW", ".MC", ".BR", ".HK", ".T", ".TO")


def is_etf(ticker: str) -> bool:
    """Heuristic: tickers ending with exchange suffixes are likely ETFs."""
    return ticker.endswith(ETF_PATTERNS) or ticker.startswith(("IUS", "QDVI", "EUNA", "UDVD", "XDEW", "IQQ", "G2X", "IS3", "IUSC"))


def load_portfolio() -> list[dict]:
    if not os.path.exists(PORTFOLIO_PATH):
        print(f"ERROR: {PORTFOLIO_PATH} not found. Run etoro_portfolio.py first.", file=sys.stderr)
        sys.exit(1)
    with open(PORTFOLIO_PATH, "r") as f:
        data = json.load(f)
    return data.get("positions", [])


def aggregate_by_ticker(positions: list[dict]) -> dict[str, dict]:
    """Group positions by ticker, summing amounts."""
    by_ticker: dict[str, dict] = {}
    for p in positions:
        ticker = p.get("tickerSymbol", "")
        if not ticker:
            continue
        amount = p.get("amount", 0)
        if ticker not in by_ticker:
            by_ticker[ticker] = {
                "ticker": ticker,
                "company": p.get("companyName", ticker),
                "amount": 0.0,
            }
        by_ticker[ticker]["amount"] += amount
    return by_ticker


def _clean_ticker(t: str) -> str:
    """Strip exchange suffixes that yfinance doesn't recognize (e.g., .US, .ST, .CO)."""
    for suffix in (".US", ".ST", ".CO", ".L", ".DE"):
        if t.endswith(suffix):
            return t[: -len(suffix)]
    return t


def fetch_stock_info(tickers: list[str]) -> dict[str, dict]:
    """Fetch sector, country, and dividend yield from yfinance for a list of tickers.
    yfinance returns dividendYield as a percentage (e.g., 6.56 = 6.56%), so we use it directly."""
    result: dict[str, dict] = {}
    batch_size = 20

    for i in range(0, len(tickers), batch_size):
        batch = tickers[i : i + batch_size]
        # Map cleaned tickers for yfinance lookup
        cleaned_batch = [_clean_ticker(t) for t in batch]
        print(f"  Fetching data for {len(batch)} tickers: {', '.join(batch)}")
        try:
            tickers_obj = yf.Tickers(" ".join(cleaned_batch))
            for t, ct in zip(batch, cleaned_batch):
                try:
                    info = tickers_obj.tickers[ct].info
                    div_yield_raw = info.get("dividendYield")
                    # yfinance returns dividendYield as a percentage already
                    # (e.g., 6.56 = 6.56%, 0.94 = 0.94%). Cap at 50% to filter bad data.
                    if div_yield_raw is not None and isinstance(div_yield_raw, (int, float)) and 0 < div_yield_raw <= 50:
                        div_yield = round(div_yield_raw, 2)
                    else:
                        div_yield = 0
                    result[t] = {
                        "sector": info.get("sector", "Unknown"),
                        "country": info.get("country", "Unknown"),
                        "dividendYield": div_yield,
                        "company": info.get("longName") or info.get("shortName", t),
                    }
                except Exception:
                    result[t] = {"sector": "Unknown", "country": "Unknown", "dividendYield": 0, "company": t}
        except Exception as e:
            print(f"  WARNING: Batch fetch failed: {e}. Trying individually...")
            for t, ct in zip(batch, cleaned_batch):
                try:
                    tk = yf.Ticker(ct)
                    info = tk.info
                    div_yield_raw = info.get("dividendYield")
                    if div_yield_raw is not None and isinstance(div_yield_raw, (int, float)) and 0 < div_yield_raw <= 50:
                        div_yield = round(div_yield_raw, 2)
                    else:
                        div_yield = 0
                    result[t] = {
                        "sector": info.get("sector", "Unknown"),
                        "country": info.get("country", "Unknown"),
                        "dividendYield": round(div_yield, 2),
                        "company": info.get("longName") or info.get("shortName", t),
                    }
                except Exception:
                    result[t] = {"sector": "Unknown", "country": "Unknown", "dividendYield": 0, "company": t}
        time.sleep(0.5)  # Rate limiting

    return result


def main():
    print("Loading portfolio data...")
    positions = load_portfolio()
    by_ticker = aggregate_by_ticker(positions)

    # Separate stocks from ETFs
    stocks = {t: v for t, v in by_ticker.items() if not is_etf(t)}
    etfs = {t: v for t, v in by_ticker.items() if is_etf(t)}

    total_stock_value = sum(v["amount"] for v in stocks.values())
    total_portfolio_value = sum(v["amount"] for v in by_ticker.values())

    print(f"Found {len(stocks)} individual stocks ({total_stock_value:.0f} USD, {total_stock_value/total_portfolio_value*100:.1f}% of portfolio)")
    print(f"Found {len(etfs)} ETFs (excluded from stock-level analysis)")

    if not stocks:
        print("No individual stocks found. Writing empty strategy.json.")
        output = {
            "generated_at": str(date.today()),
            "positions_analyzed": 0,
            "coverage_pct": 0,
            "sectors": [],
            "geography": [],
            "dividends": {"weighted_yield": 0, "payer_count": 0, "total_analyzed": 0, "top_yielders": []},
        }
        with open(OUTPUT_PATH, "w") as f:
            json.dump(output, f, indent=2)
        print(f"Strategy written to {OUTPUT_PATH}")
        return

    # Fetch stock info
    stock_tickers = list(stocks.keys())
    print(f"Fetching sector/geography/dividend data for {len(stock_tickers)} stocks...")
    info_map = fetch_stock_info(stock_tickers)

    # Aggregate sectors
    sector_amounts: dict[str, float] = defaultdict(float)
    country_amounts: dict[str, float] = defaultdict(float)
    dividend_data: list[dict] = []

    for ticker, pos in stocks.items():
        info = info_map.get(ticker, {})
        amount = pos["amount"]
        sector = info.get("sector", "Unknown")
        country = info.get("country", "Unknown")
        div_yield = info.get("dividendYield", 0)
        company = info.get("company", pos["company"])

        sector_amounts[sector] += amount
        country_amounts[country] += amount

        if div_yield and div_yield > 0:
            dividend_data.append({
                "ticker": ticker,
                "company": company,
                "yield": div_yield,  # Already in percentage form from fetch_stock_info
                "amount": amount,
            })

    # Build sector list (sorted by percentage)
    sectors = [
        {"sector": s, "percentage": round(amt / total_stock_value * 100, 2)}
        for s, amt in sorted(sector_amounts.items(), key=lambda x: -x[1])
    ]

    # Build geography list
    geography = [
        {"country": c, "percentage": round(amt / total_stock_value * 100, 2)}
        for c, amt in sorted(country_amounts.items(), key=lambda x: -x[1])
    ]

    # Compute weighted dividend yield
    weighted_yield = 0.0
    if dividend_data:
        total_div_amount = sum(d["amount"] for d in dividend_data)
        weighted_yield = round(
            sum(d["yield"] * d["amount"] for d in dividend_data) / total_div_amount, 2
        )

    # Top yielders (top 5)
    top_yielders = sorted(dividend_data, key=lambda x: -x["yield"])[:5]
    top_yielders_clean = [{"ticker": d["ticker"], "company": d["company"], "yield": d["yield"]} for d in top_yielders]

    output = {
        "generated_at": str(date.today()),
        "positions_analyzed": len(stocks),
        "coverage_pct": round(total_stock_value / total_portfolio_value * 100, 1),
        "sectors": sectors,
        "geography": geography,
        "dividends": {
            "weighted_yield": weighted_yield,
            "payer_count": len(dividend_data),
            "total_analyzed": len(stocks),
            "top_yielders": top_yielders_clean,
        },
    }

    with open(OUTPUT_PATH, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nStrategy written to {OUTPUT_PATH}")
    print(f"  Sectors: {len(sectors)}")
    print(f"  Countries: {len(geography)}")
    print(f"  Dividend payers: {len(dividend_data)}/{len(stocks)}")
    print(f"  Weighted yield: {weighted_yield}%")


if __name__ == "__main__":
    main()