#!/usr/bin/env python3
"""Generate the top 10 portfolio holdings from eToro portfolio data.
Reads portfolio-holdings.json (produced by etoro_portfolio.py) and outputs top10.json."""

import json
import os
import sys
from datetime import date

# Paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PORTFOLIO_PATH = os.path.join(SCRIPT_DIR, "portfolio-holdings.json")
OUTPUT_PATH = os.path.join(SCRIPT_DIR, "top10.json")


def main():
    if not os.path.exists(PORTFOLIO_PATH):
        print(f"Error: Portfolio file not found at {PORTFOLIO_PATH}", file=sys.stderr)
        print("Run: python etoro_portfolio.py -o portfolio-holdings.json", file=sys.stderr)
        sys.exit(1)

    with open(PORTFOLIO_PATH, "r") as f:
        data = json.load(f)

    # New format: positions are at top-level "positions" key
    positions = data.get("positions", [])
    if not positions:
        print("Error: No positions found in portfolio data", file=sys.stderr)
        sys.exit(1)

    # Aggregate positions by ticker (same stock may appear in multiple positions)
    by_ticker = {}
    for p in positions:
        ticker = p.get("tickerSymbol", "")
        if not ticker:
            continue  # skip positions with no resolved ticker
        name = p.get("companyName", ticker)
        leverage = p.get("leverage", 1)
        amount = p.get("amount", 0)

        if ticker not in by_ticker:
            by_ticker[ticker] = {
                "company": name,
                "ticker": ticker,
                "amount": 0.0,
                "leverage": leverage,
            }
        by_ticker[ticker]["amount"] += amount
        # Use max leverage if there are multiple positions with different leverage
        if leverage > by_ticker[ticker]["leverage"]:
            by_ticker[ticker]["leverage"] = leverage

    total_value = sum(v["amount"] for v in by_ticker.values())

    # Sort by amount descending, take top 10
    sorted_items = sorted(by_ticker.values(), key=lambda x: x["amount"], reverse=True)[:10]

    # Build output
    output = []
    for i, item in enumerate(sorted_items, 1):
        pct = round(item["amount"] / total_value * 100, 2)
        entry = {
            "rank": i,
            "company": item["company"],
            "ticker": item["ticker"],
            "percentage": pct,
        }
        # Only include leverage if > 1x
        if item["leverage"] > 1:
            entry["leverage"] = item["leverage"]

        output.append(entry)

    result = {
        "generated_at": str(date.today()),
        "top10": output,
    }

    with open(OUTPUT_PATH, "w") as f:
        json.dump(result, f, indent=2)

    print(f"Top 10 holdings written to {OUTPUT_PATH}")
    for entry in output:
        lev = f" (leverage: {entry['leverage']}x)" if "leverage" in entry else ""
        print(f"   {entry['rank']}. {entry['company']} ({entry['ticker']}) - {entry['percentage']}%{lev}")


if __name__ == "__main__":
    main()