#!/usr/bin/env python3
"""Generate weekly market updates via Cloudflare Workers AI (free tier).
Uses Polygon.io for market news context + Cloudflare Workers AI for summarization."""

import requests
import json
import os
from datetime import datetime

# -- Config --
CF_ACCOUNT_ID = os.environ["CF_ACCOUNT_ID"]
CF_API_TOKEN = os.environ["CF_API_TOKEN"]
CF_MODEL = "@cf/meta/llama-3.1-8b-instruct"  # free tier, 10K req/day
POLYGON_API_KEY = os.environ.get("POLYGON_API_KEY", "")

CF_AI_URL = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/run/{CF_MODEL}"

# -- Market indices / ETFs to pull news for context --
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
            print(f"  Polygon rate limited for {ticker}, skipping.")
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
        print(f"  WARNING: Polygon news fetch failed for {ticker}: {e}")
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
    return "\n".join(all_snippets) if all_snippets else "(No news context available -- generate from general knowledge)"


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


def repair_truncated_json(raw: str) -> str:
    """Attempt to repair truncated JSON by closing unclosed brackets/arrays."""
    raw = raw.strip()
    # Count opening vs closing braces/brackets
    open_braces = raw.count("{")
    close_braces = raw.count("}")
    open_brackets = raw.count("[")
    close_brackets = raw.count("]")

    # If the last complete value is a string, close it
    # Find the last quote and check if it's closed
    last_dquote = raw.rfind('"')
    if last_dquote > 0:
        # Count quotes after the last newline before last_dquote to check if string is closed
        after_last_quote = raw[last_dquote + 1:]
        # If there's content after the last quote that isn't a structural char, the string is truncated
        if after_last_quote and not after_last_quote.startswith(("}", "]", ",", " ", "\n")):
            raw = raw[:last_dquote + 1]  # truncate incomplete string

    # Close unclosed strings (find unterminated quotes)
    # Add missing closing brackets/braces
    raw += "}" * (open_braces - close_braces)
    raw += "]" * (open_brackets - close_brackets)
    return raw


def extract_json(text: str) -> dict:
    """Try to parse JSON from model output, with repair fallbacks."""
    text = text.strip()
    # Strip markdown code fences
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        for suffix in ["```json", "```"]:
            if text.endswith(suffix):
                text = text[:-len(suffix)]
        text = text.strip()

    # Clean invalid escape sequences
    import re
    text = re.sub(r'\\([^"\\/bfnrtu])', r'\1', text)

    # Attempt 1: direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Attempt 2: repair truncated JSON
    repaired = repair_truncated_json(text)
    try:
        return json.loads(repaired)
    except json.JSONDecodeError:
        pass

    # Attempt 3: try to find a complete JSON object via regex
    match = re.search(r'\{.*"updates"\s*:\s*\[.*\]\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    # Attempt 4: try to find any complete JSON object
    brace_depth = 0
    start = -1
    for i, ch in enumerate(text):
        if ch == '{':
            if start == -1:
                start = i
            brace_depth += 1
        elif ch == '}':
            brace_depth -= 1
            if brace_depth == 0 and start != -1:
                candidate = text[start:i + 1]
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    start = -1  # reset and keep looking

    raise json.JSONDecodeError("Could not extract valid JSON from model output", text, 0)


def backup_existing_file():
    if os.path.exists("market-updates.json"):
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        backup_filename = f"backups/market-updates-{timestamp}.json"
        os.makedirs("backups", exist_ok=True)
        os.rename("market-updates.json", backup_filename)
        print(f"Backed up previous update to {backup_filename}")


def main():
    today = datetime.today().strftime("%B %d, %Y")

    print("Gathering market news context from Polygon...")
    market_context = gather_market_context()

    prompt = f"""You are a financial markets analyst writing a weekly update for a retail investor blog.

Today is {today}. Here is recent market news for context:

{market_context}

Write a structured weekly market update in exactly 5 sections. Return ONLY valid JSON -- no markdown, no code fences, no extra text:

{{"updates": [
  {{"title": "Market Update", "content": "1-2 sentences on overall market performance this week."}},
  {{"title": "Current Developments", "content": "1-2 sentences on key macro events, earnings, or policy changes."}},
  {{"title": "Market Reactions", "content": "1-2 sentences on how markets reacted -- sector moves, sentiment shifts."}},
  {{"title": "Portfolio Strategy", "content": "1-2 sentences on what a diversified long-term investor should consider."}},
  {{"title": "Looking Ahead", "content": "1-2 sentences on what to watch next week."}}
]}}

IMPORTANT: Return ONLY the JSON object. No markdown, no explanation."""

    print("Calling Cloudflare Workers AI...")
    try:
        raw = call_cloudflare_ai(prompt, max_tokens=800)
        parsed = extract_json(raw)

        backup_existing_file()

        with open("market-updates.json", "w") as f:
            json.dump(parsed, f, indent=2)
        print("Market updates saved to market-updates.json")
    except Exception as e:
        print(f"ERROR: {e}")
        print(f"   Raw response: {raw if 'raw' in dir() else 'N/A'}")
        raise


if __name__ == "__main__":
    main()