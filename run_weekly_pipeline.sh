#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────
# Weekly Pipeline: fetch eToro portfolio, update holdings,
# generate content, push to GitHub.
# Run this weekly via n8n or cron.
# ──────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# ── Load API keys from .env.web if present ──
if [ -f ".env.web" ]; then
  set -a; source .env.web; set +a
fi

# ── Find Python (prefer conda, fall back to system python3) ──
if command -v python3 &>/dev/null; then
  PYTHON="python3"
elif command -v python &>/dev/null; then
  PYTHON="python"
else
  echo "ERROR: Python not found"
  exit 1
fi
echo "Using Python: $PYTHON"

echo "============================================"
echo "  Ambitriber Weekly Pipeline"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "============================================"

# ── Step 0: Fetch eToro portfolio ──
echo ""
echo "[0/6] Fetching eToro portfolio..."
$PYTHON etoro_portfolio.py -o portfolio-holdings.json

# ── Step 1: Generate top 10 holdings ──
echo ""
echo "[1/6] Generating top 10 holdings..."
$PYTHON generate_top10.py

# ── Step 2: Generate market updates ──
echo ""
echo "[2/6] Generating market updates..."
$PYTHON generate_market_updates.py || echo "WARNING: Market updates failed (non-critical)"

# ── Step 3: Generate weekly post ──
echo ""
echo "[3/6] Generating weekly post..."
$PYTHON generate_weekly_post.py || echo "WARNING: Weekly post failed (non-critical)"

# ── Step 4: Backup existing files ──
echo ""
echo "[4/6] Backing up existing data..."
mkdir -p backups
if [ -f "market-updates.json" ]; then
  cp market-updates.json "backups/market-updates-$(date '+%Y-%m-%d_%H-%M-%S').json"
fi

# ── Step 5: Git add, commit, push ──
echo ""
echo "[5/6] Committing and pushing to GitHub..."
git config user.email "yiannis_90@hotmail.com" 2>/dev/null || true
git config user.name "Ambitriber" 2>/dev/null || true

# Use GITHUB_TOKEN for authenticated push if available
if [ -n "${GITHUB_TOKEN:-}" ]; then
  REPO_URL="https://github.com/AmbiTriber/ambitriber.github.io.git"
  # Update remote to use token (suppress token in output)
  git remote set-url origin "https://${GITHUB_TOKEN}@github.com/AmbiTriber/ambitriber.github.io.git" 2>/dev/null || true
  echo "  Using GITHUB_TOKEN for authentication"
fi

git add portfolio-holdings.json top10.json market-updates.json weekly-post.json posts-archive.json index.html tribercss.css
git commit -m "Weekly update: $(date '+%Y-%m-%d')" || echo "Nothing to commit"

# Push (token is in remote URL if GITHUB_TOKEN was set)
git push origin main

# Restore remote URL without token for safety
if [ -n "${GITHUB_TOKEN:-}" ]; then
  git remote set-url origin "https://github.com/AmbiTriber/ambitriber.github.io.git" || true
fi

echo ""
echo "[6/6] Pipeline complete!"
echo "============================================"