#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────
# Weekly Pipeline: update holdings, generate content, push to GitHub
# Run this weekly via n8n or cron.
# ──────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# ── Load API keys from .env.web if present ──
if [ -f ".env.web" ]; then
  set -a; source .env.web; set +a
fi

# ── Use conda Python (has polygon & requests installed) ──
PYTHON="/home/ioannis/miniconda3/bin/python3"
echo " Using Python: $PYTHON"

echo "============================================"
echo "  Ambitriber Weekly Pipeline"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "============================================"

# ── Step 1: Generate top 10 holdings ──
echo ""
echo "[1/5] Generating top 10 holdings..."
$PYTHON generate_top10.py

# ── Step 2: Generate market updates ──
echo ""
echo "[2/5] Generating market updates..."
$PYTHON generate_market_updates.py

# ── Step 3: Generate weekly post ──
echo ""
echo "[3/5] Generating weekly post..."
$PYTHON generate_weekly_post.py

# ── Step 4: Git add, commit, push ──
echo ""
echo "[4/5] Committing and pushing to GitHub..."
git config user.email "yiannis_90@hotmail.com" 2>/dev/null
git config user.name "Ambitriber" 2>/dev/null
git add top10.json market-updates.json weekly-post.json posts-archive.json index.html tribercss.css
git commit -m "Weekly update: $(date '+%Y-%m-%d')" || echo "Nothing to commit"

# Use GITHUB_TOKEN from .env.web if set; otherwise fall back to credential helper
if [ -n "${GITHUB_TOKEN:-}" ]; then
  git push "https://AmbiTriber:${GITHUB_TOKEN}@github.com/AmbiTriber/ambitriber.github.io.git" main
else
  git push origin main
fi

echo ""
echo "[5/5] ✅ Pipeline complete!"
echo "============================================"