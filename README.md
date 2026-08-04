# Ambitriber Finance — Personal Finfluencer Site

My personal financial blog hosted on **GitHub Pages** at [ambitribe.com](https://ambitribe.com).  
Shares my eToro portfolio strategy, top holdings, weekly market updates, and AI-generated posts — automatically refreshed every week.

---

## 📁 Project Structure

```
├── index.html                  # Main landing page (all sections)
├── tribercss.css               # Stylesheet (eToro-inspired green theme)
├── CNAME                       # Custom domain (ambitribe.com)
│
├── generate_top10.py           # Reads portfolio data → produces top10.json
├── generate_market_updates.py  # Polygon news + Cloudflare AI → market-updates.json
├── generate_weekly_post.py     # Cloudflare AI → weekly-post.json + archives
├── watchlst_summary.py         # Per-ticker news summarizer (Polygon + Cloudflare AI)
├── run_weekly_pipeline.sh      # Master script: runs all 3 generators + git push
│
├── top10.json                  # Top 10 holdings (auto-generated)
├── market-updates.json         # 5-section market summary (auto-generated)
├── weekly-post.json            # Latest ~200 word post (auto-generated)
├── posts-archive.json          # All historical posts, newest first
```

## 🚀 How It Works

### 1. Data Sources
- **Top Holdings** — scraped from your eToro portfolio (`~/etoro-workspace/portfolio-holdings.json`)
- **Market News** — pulled from [Polygon.io](https://polygon.io) (free tier: 5 API calls/min)
- **AI Summarization** — [Cloudflare Workers AI](https://developers.cloudflare.com/workers-ai/) (free tier: 10K requests/day, Llama 3.1 8B)
- **Market Updates** — Polygon news for SPY/QQQ/IWM/DIA/GLD/USO → summarized by Cloudflare AI
- **Weekly Post** — Cloudflare AI writes a ~200 word post using your top 10 holdings as context

### 2. Automation (n8n)
An **n8n workflow** named *"Ambitriber Weekly Pipeline"* runs every **Sunday at 9:00 AM**:

```
Schedule Trigger → SSH (runs run_weekly_pipeline.sh on your server)
```

The pipeline:
1. `generate_top10.py` — reads eToro data, writes `top10.json`
2. `generate_market_updates.py` — pulls Polygon news + Cloudflare AI summary, writes `market-updates.json`
3. `generate_weekly_post.py` — Cloudflare AI generates post from holdings, writes `weekly-post.json` and appends to `posts-archive.json`
4. `git add` + `git commit` + `git push` — pushes everything to GitHub → site goes live

## ⚙️ Setup Instructions

### Prerequisites
- **Python 3.8+** with dependencies:
  ```bash
  pip install requests polygon-api-client
  ```
- **Cloudflare account** — [sign up free](https://dash.cloudflare.com/sign-up)
  - Get your **Account ID** from the Workers & Pages dashboard
  - Create an **API Token** with Workers AI permissions
- **Polygon.io account** — [free tier](https://polygon.io) (optional but recommended for news-grounded updates)
- **n8n** instance running (local or cloud)
- **SSH access** from n8n to the machine hosting this repo
- **eToro portfolio data** at `~/etoro-workspace/portfolio-holdings.json`

### Step 1: Set Environment Variables
```bash
# Fill in your keys
nano .env.web
# Source before running the pipeline
source .env.web
```
Or add the exports to your `~/.bashrc` / `~/.profile` if you want them always available.

### Step 2: Test Locally
```bash
cd /home/ioannis/Projects/ambitriber.github.io
./run_weekly_pipeline.sh
```
All 3 JSON files should update and git should push them.

### Step 3: Configure the n8n Workflow
1. Open your n8n instance, find the workflow **"Ambitriber Weekly Pipeline"**
2. Click the **SSH node** → add credentials for your server (host, port, user, password or key)
3. Click **"Activate"** to enable the Sunday 9 AM schedule
4. Optionally, run it once manually to verify everything works end-to-end

### Step 4: (Optional) Change the Schedule
Edit the Schedule Trigger node in n8n:
- **Interval mode** — pick days, hours, minutes via dropdowns
- **Cron mode** — use an expression like `0 9 * * 1` for Monday 9 AM

## 📝 Sections on the Site

| Section | Description | Data Source |
|---|---|---|
| **About Me** | Who I am as an investor | Static HTML |
| **📊 Top Holdings** | My top 10 positions with value, weight, and leverage | `top10.json` |
| **Investment Strategy** | Sector/geographic breakdown, dividend strategy | Static HTML |
| **📝 Weekly Post** | ~200 word AI-generated commentary on my holdings | `weekly-post.json` |
| **Market Updates** | 5-section summary (markets, developments, reactions, strategy, outlook) | `market-updates.json` |
| **📚 Posts Archive** | Running log of all past weekly posts | `posts-archive.json` |
| **Contact** | Links to my BullAware and eToro profiles | Static HTML |

## 🔧 Manual Runs
To regenerate content without waiting for the schedule:
```bash
# Just holdings
python3 generate_top10.py

# Just market updates
python3 generate_market_updates.py

# Just the weekly post
python3 generate_weekly_post.py

# Everything + push
./run_weekly_pipeline.sh
```

## 🛡️ Error Handling
- Each Python script exits with a non-zero code on failure, so n8n can alert you
- `posts-archive.json` deduplicates by date — running the pipeline twice won't create duplicate posts
- Old `market-updates.json` is automatically backed up to `backups/` before being overwritten
- The bash pipeline uses `set -euo pipefail` — stops on any error
