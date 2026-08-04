#!/usr/bin/env python3
"""Generate a weekly ~200 word post about my holdings using Cloudflare Workers AI (free tier).
Reads top10.json for context, calls Cloudflare Workers AI, writes weekly-post.json and
appends the new post to posts-archive.json."""

import json
import os
import sys
import requests
from datetime import datetime

# ── Config ──
CF_ACCOUNT_ID = os.environ["CF_ACCOUNT_ID"]
CF_API_TOKEN = os.environ["CF_API_TOKEN"]
CF_MODEL = "@cf/meta/llama-3.1-8b-instruct"  # free tier, 10K req/day

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TOP10_PATH = os.path.join(SCRIPT_DIR, "top10.json")
WEEKLY_POST_PATH = os.path.join(SCRIPT_DIR, "weekly-post.json")
ARCHIVE_PATH = os.path.join(SCRIPT_DIR, "posts-archive.json")

CF_AI_URL = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/run/{CF_MODEL}"


def load_top10():
    with open(TOP10_PATH, "r") as f:
        return json.load(f)


def build_prompt(top10_data):
    """Build a prompt that includes portfolio context."""
    holdings_desc = "\n".join(
        f"{h['rank']}. {h['company']} ({h['ticker']}) — {h['percentage']}% of portfolio"
        + (f", {h['leverage']}x leverage" if h.get("leverage") else "")
        for h in top10_data["top10"]
    )

    today = datetime.now().strftime("%B %d, %Y")

    return f"""You are Ambitriber, a multi-strategy retail investor on eToro sharing your weekly thoughts.

Today is {today}. Here are your current top 10 holdings:
{holdings_desc}
Total portfolio value: ${top10_data['total_portfolio_value']:,.2f}

Write a ~200 word first-person weekly post from Ambitriber's perspective. The post should:
- Be conversational and friendly, as if talking to your copiers and followers
- Comment on 2-3 of your top holdings and why you're holding them
- Briefly mention any strategic moves you're considering or why you're staying the course
- End with a forward-looking note and encouragement
- Do NOT use markdown — plain text only, with natural paragraph breaks

Return ONLY the post content as plain text, no JSON wrapper, no title."""


def call_cloudflare_ai(prompt: str, max_tokens: int = 500) -> str:
    """Call Cloudflare Workers AI (free tier)."""
    headers = {"Authorization": f"Bearer {CF_API_TOKEN}"}
    payload = {
        "messages": [
            {"role": "system", "content": "You are a friendly retail investor writing a weekly portfolio update. Keep it natural and authentic."},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": max_tokens,
    }
    resp = requests.post(CF_AI_URL, headers=headers, json=payload, timeout=90)
    resp.raise_for_status()
    data = resp.json()
    return data["result"]["choices"][0]["message"]["content"].strip()


def generate_title():
    """Simple date-based title."""
    today = datetime.now().strftime("%B %d, %Y")
    return f"Weekly Portfolio Check-In — {today}"


def save_weekly_post(title, content):
    today = datetime.now().strftime("%B %d, %Y")
    post = {
        "title": title,
        "date": today,
        "content": content,
    }
    with open(WEEKLY_POST_PATH, "w") as f:
        json.dump(post, f, indent=2)
    print(f"✅ Weekly post saved to {WEEKLY_POST_PATH}")
    return post


def append_to_archive(post):
    """Append the post to posts-archive.json (newest first)."""
    if os.path.exists(ARCHIVE_PATH):
        with open(ARCHIVE_PATH, "r") as f:
            archive = json.load(f)
    else:
        archive = {"posts": []}

    # Check if this post (by date) is already in the archive
    existing_dates = {p["date"] for p in archive.get("posts", [])}
    if post["date"] in existing_dates:
        print(f"⚠️  Post for {post['date']} already in archive, skipping append.")
        return

    archive["posts"].insert(0, post)  # newest first
    with open(ARCHIVE_PATH, "w") as f:
        json.dump(archive, f, indent=2)
    print(f"✅ Post appended to archive ({len(archive['posts'])} total)")


def main():
    if not os.path.exists(TOP10_PATH):
        print(f"❌ top10.json not found at {TOP10_PATH}. Run generate_top10.py first.", file=sys.stderr)
        sys.exit(1)

    print("📊 Loading portfolio data...")
    top10_data = load_top10()

    print("🤖 Calling Cloudflare Workers AI to generate post...")
    prompt = build_prompt(top10_data)
    try:
        content = call_cloudflare_ai(prompt, max_tokens=500)
    except requests.exceptions.RequestException as e:
        print(f"❌ Cloudflare AI call failed: {e}", file=sys.stderr)
        sys.exit(1)

    title = generate_title()
    post = save_weekly_post(title, content)
    append_to_archive(post)

    print(f"\n{'='*60}")
    print(f"📝 {title}")
    print(f"{'='*60}")
    print(content)
    print(f"{'='*60}")
    print("Done!")


if __name__ == "__main__":
    main()
