#!/usr/bin/env python3
"""
eToro Portfolio Fetcher

Fetches the current portfolio positions from the eToro API and enriches each
position with the ticker symbol (symbolFull) and company name
(instrumentDisplayName) by resolving the instrumentID.

Authentication:
  Set the following environment variables before running:
    ETORO_API_KEY   - Your eToro Public API Key
    ETORO_USER_KEY  - Your eToro User Key

  Keys are generated from: Settings > Trading > API Key Management

Usage:
  python etoro_portfolio.py              # Real account
  python etoro_portfolio.py --demo       # Demo account
  python etoro_portfolio.py -o output.json
  python etoro_portfolio.py --demo -o demo_portfolio.json

Output:
  JSON with enriched positions containing:
    - All original position fields
    - tickerSymbol: The instrument's ticker (e.g., "AAPL")
    - companyName: The instrument's display name (e.g., "Apple Inc.")
"""

import argparse
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode


BASE_URL = "https://public-api.etoro.com"

# ---------------------------------------------------------------------------
# Auto-load environment variables from .env.web (if present)
# ---------------------------------------------------------------------------
ENV_FILE = Path(__file__).resolve().parent / ".env.web"


def _load_dotenv(env_path: Path) -> None:
    """Parse a .env file and set os.environ, skipping comments and blank lines."""
    if not env_path.exists():
        return
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


_load_dotenv(ENV_FILE)
PORTFOLIO_PATH_REAL = "/api/v1/trading/info/portfolio"
PORTFOLIO_PATH_DEMO = "/api/v1/trading/info/demo/portfolio"
INSTRUMENTS_PATH = "/api/v1/market-data/instruments"
INSTRUMENT_BATCH_SIZE = 100  # Fetch instruments in batches to avoid huge URLs


def get_headers() -> dict[str, str]:
    """Build required request headers with API key, user key, and a unique request ID."""
    api_key = os.environ.get("ETORO_API_KEY")
    user_key = os.environ.get("ETORO_USER_KEY")

    if not api_key:
        print("ERROR: ETORO_API_KEY environment variable is not set.", file=sys.stderr)
        print("Get your keys from: Settings > Trading > API Key Management on eToro", file=sys.stderr)
        sys.exit(1)

    if not user_key:
        print("ERROR: ETORO_USER_KEY environment variable is not set.", file=sys.stderr)
        print("Get your keys from: Settings > Trading > API Key Management on eToro", file=sys.stderr)
        sys.exit(1)

    return {
        "x-request-id": str(uuid.uuid4()),
        "x-api-key": api_key,
        "x-user-key": user_key,
        "Accept": "application/json",
        "User-Agent": "eToroPortfolioScript/1.0",
    }


def api_get(path: str, params: dict[str, str] | None = None) -> Any:
    """Perform an authenticated GET request to the eToro API and return parsed JSON."""
    url = f"{BASE_URL}{path}"
    if params:
        url = f"{url}?{urlencode(params)}"

    req = Request(url, headers=get_headers())

    try:
        with urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8")
        except Exception:
            pass
        print(f"ERROR: HTTP {e.code} from {url}", file=sys.stderr)
        if body:
            print(f"  Response: {body[:500]}", file=sys.stderr)
        if e.code == 401:
            print("  Check that your ETORO_API_KEY and ETORO_USER_KEY are correct.", file=sys.stderr)
        elif e.code == 429:
            print("  Rate limit exceeded. Wait and try again.", file=sys.stderr)
        sys.exit(1)
    except URLError as e:
        print(f"ERROR: Network error calling {url}: {e.reason}", file=sys.stderr)
        sys.exit(1)


def fetch_portfolio(demo: bool) -> dict:
    """Fetch the full portfolio (positions + mirrors + orders) from eToro."""
    path = PORTFOLIO_PATH_DEMO if demo else PORTFOLIO_PATH_REAL
    env_label = "demo" if demo else "real"
    print(f"Fetching {env_label} portfolio...", file=sys.stderr)
    return api_get(path)


def fetch_instruments_batch(instrument_ids: list[int]) -> dict[int, dict]:
    """
    Fetch instrument display data for a list of instrument IDs.
    Returns a dict mapping instrumentID -> instrument data.
    """
    result: dict[int, dict] = {}

    for i in range(0, len(instrument_ids), INSTRUMENT_BATCH_SIZE):
        batch = instrument_ids[i : i + INSTRUMENT_BATCH_SIZE]
        ids_param = ",".join(str(iid) for iid in batch)

        print(f"  Resolving instruments: {ids_param}", file=sys.stderr)
        data = api_get(INSTRUMENTS_PATH, {"instrumentIds": ids_param})

        for item in data.get("instrumentDisplayDatas", []):
            iid = item.get("instrumentID")
            if iid is not None:
                result[iid] = item

    return result


def enrich_positions(positions: list[dict], instrument_map: dict[int, dict]) -> list[dict]:
    """Add tickerSymbol and companyName to each position based on instrumentID."""
    missing_ids: set[int] = set()
    enriched: list[dict] = []

    for pos in positions:
        instrument_id = pos.get("instrumentID")
        inst_info = instrument_map.get(instrument_id) if instrument_id is not None else None

        enriched_pos = dict(pos)  # Copy all original fields
        if inst_info:
            enriched_pos["tickerSymbol"] = inst_info.get("symbolFull", "")
            enriched_pos["companyName"] = inst_info.get("instrumentDisplayName", "")
        else:
            enriched_pos["tickerSymbol"] = ""
            enriched_pos["companyName"] = ""
            if instrument_id is not None:
                missing_ids.add(instrument_id)

        enriched.append(enriched_pos)

    if missing_ids:
        print(f"  WARNING: Could not resolve instrument IDs: {sorted(missing_ids)}", file=sys.stderr)

    return enriched


def collect_unique_instrument_ids(portfolio: dict) -> set[int]:
    """Extract all unique instrumentID values from positions in the portfolio."""
    ids: set[int] = set()

    # Standalone positions
    for pos in portfolio.get("clientPortfolio", {}).get("positions", []):
        iid = pos.get("instrumentID")
        if iid is not None:
            ids.add(iid)

    # Positions inside mirrors
    for mirror in portfolio.get("clientPortfolio", {}).get("mirrors", []):
        for pos in mirror.get("positions", []):
            iid = pos.get("instrumentID")
            if iid is not None:
                ids.add(iid)

    return ids


def main():
    parser = argparse.ArgumentParser(
        description="Fetch eToro portfolio positions with resolved ticker symbols and company names."
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Fetch the demo (virtual) portfolio instead of the real portfolio.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default=None,
        help="Write output JSON to the specified file (default: stdout).",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        default=True,
        help="Pretty-print the JSON output (default: true).",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Output compact JSON (single line).",
    )
    args = parser.parse_args()

    # 1. Fetch portfolio
    portfolio = fetch_portfolio(demo=args.demo)

    # 2. Collect all unique instrument IDs
    instrument_ids = collect_unique_instrument_ids(portfolio)
    sorted_ids = sorted(instrument_ids)
    print(f"Found {len(sorted_ids)} unique instrument IDs in portfolio.", file=sys.stderr)

    # 3. Fetch instrument details
    instrument_map: dict[int, dict] = {}
    if sorted_ids:
        instrument_map = fetch_instruments_batch(sorted_ids)
    else:
        print("  No positions found with instrument IDs.", file=sys.stderr)

    # 4. Enrich positions with ticker symbols and company names
    client_portfolio = portfolio.get("clientPortfolio", {})
    standalone = client_portfolio.get("positions", [])
    mirrors = client_portfolio.get("mirrors", [])

    # Enrich standalone positions
    enriched_standalone = enrich_positions(standalone, instrument_map)

    # Enrich mirror positions
    enriched_mirrors: list[dict] = []
    for mirror in mirrors:
        enriched_mirror = dict(mirror)
        mirror_positions = mirror.get("positions", [])
        enriched_mirror["positions"] = enrich_positions(mirror_positions, instrument_map)
        enriched_mirrors.append(enriched_mirror)

    # 5. Build output
    output = {
        "summary": {
            "environment": "demo" if args.demo else "real",
            "totalPositions": len(enriched_standalone),
            "totalMirrors": len(enriched_mirrors),
            "credit": client_portfolio.get("credit", 0),
            "resolvedInstruments": len(instrument_map),
            "unresolvedInstruments": len(sorted_ids) - len(instrument_map),
        },
        "positions": enriched_standalone,
        "mirrors": enriched_mirrors,
    }

    # Also include unresolved instrument IDs for reference
    resolved_ids = set(instrument_map.keys())
    unresolved = set(sorted_ids) - resolved_ids
    if unresolved:
        output["summary"]["unresolvedInstrumentIds"] = sorted(unresolved)

    # 6. Output
    indent = None if args.compact else 2
    json_output = json.dumps(output, indent=indent, ensure_ascii=False, default=str)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(json_output)
            f.write("\n")
        print(f"Output written to {args.output}", file=sys.stderr)
    else:
        print(json_output)


if __name__ == "__main__":
    main()