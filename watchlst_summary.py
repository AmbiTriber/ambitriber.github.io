# pip install polygon-api-client requests
import os
from polygon import RESTClient
import requests

POLYGON_API_KEY = os.environ["POLYGON_API_KEY"]
CF_ACCOUNT_ID = os.environ["CF_ACCOUNT_ID"]
CF_API_TOKEN = os.environ["CF_API_TOKEN"]
CF_MODEL = "@cf/meta/llama-3.1-8b-instruct"  # free tier, 10K req/day

polygon_client = RESTClient(api_key=POLYGON_API_KEY)

def get_ticker_news(ticker: str, limit: int = 5):
    """Get recent news for a ticker from Polygon."""
    # Polygon returns a list of news items with title, description, url, published_utc, etc.
    news = polygon_client.list_ticker_news(ticker=ticker, limit=limit)
    items = []
    for n in news:
        text_parts = []
        if n.title:
            text_parts.append(n.title)
        if n.description:
            text_parts.append(n.description)
        if text_parts:
            items.append(" - " + " | ".join(text_parts))
    return items[:limit]

def summarize_ticker(ticker: str, snippets: list[str]) -> str:
    if not snippets:
        return f"No recent news found for {ticker}."

    context = "\n".join(snippets)
    prompt = f"""You are a financial news summarizer.
Based on the following news snippets about {ticker}, write a 2–4 sentence summary in English.
Focus on: price drivers, earnings/guidance, major partnerships, regulatory news, and overall sentiment.
Do not give investment advice.

NEWS:
{context}

Summary:"""

    url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/run/{CF_MODEL}"
    headers = {"Authorization": f"Bearer {CF_API_TOKEN}"}
    payload = {
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 150,
    }

    resp = requests.post(url, headers=headers, json=payload)
    resp.raise_for_status()
    data = resp.json()
    return data["result"]["choices"][0]["message"]["content"].strip()

def generate_watchlist_summary(tickers: list[str]) -> str:
    sections = []
    for t in tickers:
        snippets = get_ticker_news(t, limit=5)
        summary = summarize_ticker(t, snippets)
        sections.append(f"## {t}\n{summary}")
    return "\n\n".join(sections)

if __name__ == "__main__":
    tickers = ["AAPL", "NVDA", "TSLA"]  # or read from a file
    summary = generate_watchlist_summary(tickers)
    print(summary)
    # Optionally write to a file:
    # with open("watchlist_summary.md", "w", encoding="utf-8") as f:
    #     f.write(summary)