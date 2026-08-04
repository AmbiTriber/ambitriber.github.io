#!/usr/bin/env python3
"""Generate weekly market updates via Cloudflare Workers AI (free tier).
Uses Polygon.io for market news context + Cloudflare Workers AI for summarization."""

import requests
import json
import os
from datetime import datetime

# ── Config ──
CF_ACCOUNT_ID = os.environ["CF_ACCOUNT_ID"]
CF_API_TOKEN = os.environ["CF_API_TOKEN"]
CF_MODEL = "@cf/meta/llama-3.1-8b-instruct"  # free tier, 10K req/day
POLYGON_API_KEY = os.environ.get("POLYGON_API_KEY", "")

CF_AI_URL = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/run/{CF_MODEL}"

# ── Market indices / ETFs to pull news for context ──
MARKET_TICKERS = ["SPY", "QQQ", "IWM", "DIA", "GLD", "USO"]


def get_ticker_news(ticker: str, limit: int = 3):
    """Get recent news snippets for a ticker from Polygon free tier via REST API."""
    if not POLYGON_API_KEY:
        return []
    try:
        url = f"https://api.polygon.io/v2/reference/news"
        params = {"ticker": ticker, "limit": limit, "apiKey": POLYGON_API_KEY}
        resp = requests.get(url, params=params, timeout=15)
        if resp.status_code == 429:
            print(f"  ⏳ Polygon rate limited for {ticker}, skipping.")
            return []
        resp.raise_for_status()
        data = resp.json()
        items = []
        for r in data.get("results", []):
            parts = [p for p in [r.get("title"), r.get("description")] if p]
            if parts:
                items.append(" | ".join(parts))
        return items[:limit]
    except Exception as e:
        print(f"  ⚠️  Polygon news fetch failed for {ticker}: {e}")
        return []


def gather_market_context():
    """Pull recent news for major market ETFs to ground the summary."""
    all_snippets = []
    import time
    for i, t in enumerate(MARKET_TICKERS):
        if i > 0:
            time.sleep(15)  # Respect Polygon free tier: 5 calls/min
        snippets = get_ticker_news(t, limit=2)
        for s in snippets:
            all_snippets.append(f"[{t}] {s}")
    return "\n".join(all_snippets) if all_snippets else "(No news context available — generate from general knowledge)"


def call_cloudflare_ai(prompt: str, max_tokens: int = 600) -> str:
    """Call Cloudflare Workers AI (free tier)."""
    headers = {"Authorization": f"Bearer {CF_API_TOKEN}"}
    payload = {
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
    }
    resp = requests.post(CF_AI_URL, headers=headers, json=payload, timeout=90)
    resp.raise_for_status()
    data = resp.json()
    return data["result"]["choices"][0]["message"]["content"].strip()


def backup_existing_file():
    if os.path.exists("market-updates.json"):
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        backup_filename = f"backups/market-updates-{timestamp}.json"
        os.makedirs("backups", exist_ok=True)
        os.rename("market-updates.json", backup_filename)
        print(f"📦 Backed up previous update to {backup_filename}")


def main():
    today = datetime.today().strftime("%B %d, %Y")

    print("📡 Gathering market news context from Polygon...")
    market_context = gather_market_context()

    prompt = f"""You are a financial markets analyst writing a weekly update for a retail investor blog.

Today is {today}. Here is recent market news for context:

{market_context}

Write a structured weekly market update in exactly 5 sections. Return ONLY valid JSON — no markdown, no code fences, no extra text:

{{"updates": [
  {{"title": "Market Update", "content": "1-2 sentences on overall market performance this week."}},
  {{"title": "Current Developments", "content": "1-2 sentences on key macro events, earnings, or policy changes."}},
  {{"title": "Market Reactions", "content": "1-2 sentences on how markets reacted — sector moves, sentiment shifts."}},
  {{"title": "Portfolio Strategy", "content": "1-2 sentences on what a diversified long-term investor should consider."}},
  {{"title": "Looking Ahead", "content": "1-2 sentences on what to watch next week."}}
]}}

IMPORTANT: Return ONLY the JSON object. No markdown, no explanation."""

    print("🤖 Calling Cloudflare Workers AI...")
    try:
        raw = call_cloudflare_ai(prompt, max_tokens=600)
        # Strip any markdown code fences if the model wraps it
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()

        # Clean invalid escape sequences (e.g. \&, \s) that some models produce
        # Replace invalid backslash sequences with the character itself
        import re
        raw_clean = re.sub(r'\\([^"\\/bfnrtu])', r'\1', raw)

        parsed = json.loads(raw_clean)

        backup_existing_file()

        with open("market-updates.json", "w") as f:
            json.dump(parsed, f, indent=2)
        print("✅ Market updates saved to market-updates.json")
    except Exception as e:
        print(f"❌ Error: {e}")
        print(f"   Raw response: {raw if 'raw' in dir() else 'N/A'}")
        raise


if __name__ == "__main__":
    main()
