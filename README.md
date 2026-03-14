# Groww Play Store Review Analyst

A pipeline that scrapes **8–12 weeks** of public Play Store reviews for the **Groww** fintech app, groups them into **5 themes** (via Grok or keyword fallback), synthesises a **Weekly Pulse** report with **Gemini**, and delivers it as a styled email — all with **zero PII**.

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Copy and fill in your API keys
cp .env.example .env

# 3. Run the full pipeline (scrape → themes → pulse → email draft)
python main.py

# 4. Launch the Streamlit dashboard
python -m streamlit run app.py

# 5. Start the FastAPI server
python -m uvicorn main:app --host 0.0.0.0 --port 10000
```

## Tech Stack

| Layer | Technology |
|---|---|
| Scraping | `google-play-scraper` + `langdetect` |
| Theme analysis | Grok (xAI) with keyword fallback |
| Report synthesis | Gemini 2.5 Flash |
| Email | Gmail API (OAuth 2.0) |
| Dashboard | Streamlit |
| API | FastAPI + Uvicorn |
| Scheduler | `schedule` (local) + GitHub Actions (cloud) |
| Containerisation | Docker |
| Hosting | Render (backend) · Vercel (frontend) |

## DevOps & Maintenance

### The Pulse Trick (Uptime Monitoring)

Render's **Starter (free) tier** spins down a web service after ~15 minutes of inactivity. A cold start takes ~30 seconds, which is too slow for a live demo or a reviewer clicking through the dashboard.

To work around this, the project uses **UptimeRobot** (free plan) to send an HTTP GET to the `/health` endpoint every **14 minutes**. This keeps the Render instance awake during the day so that demo viewers always get an instant response.

| Item | Detail |
|---|---|
| **Monitor target** | `https://<your-render-app>.onrender.com/health` |
| **Ping interval** | Every 14 minutes |
| **Why 14 min?** | Render sleeps after 15 min of inactivity; pinging at 14 min keeps us just inside the window. |
| **Free-tier budget** | Render gives **750 free hours/month** (~31 days). A single always-awake service uses ~720 h/month, comfortably within budget. |
| **Off-hours** | You can pause the UptimeRobot monitor at night/weekends to save hours if needed. |

**Setup:**

1. Sign up at [UptimeRobot](https://uptimerobot.com) (free).
2. Add a new **HTTP(s)** monitor.
3. Set the URL to your Render service's `/health` endpoint.
4. Set the monitoring interval to **14 minutes** (the minimum on the free plan is 5 min).
5. Save — the backend will now stay warm automatically.

### GitHub Actions (Weekly Cron)

A separate GitHub Actions workflow (`.github/workflows/weekly_pulse.yml`) runs the full pipeline every **Monday at 17:35 IST** and uploads the pulse as a build artifact. See `ARCHITECTURE.md` for setup details.

## Project Structure

```
├── main.py                  # FastAPI app + CLI entry point
├── app.py                   # Streamlit launcher
├── scheduler.py             # Local weekly scheduler
├── Dockerfile               # Production container for Render
├── requirements.txt
├── .env.example             # Template for API keys
├── src/
│   ├── phase1/scraper.py    # Play Store scraper
│   ├── phase2/analyzer.py   # Theme generation (Grok / fallback)
│   ├── phase3/report.py     # Pulse synthesis (Gemini) + HTML
│   ├── phase4/emailer.py    # Gmail draft / send
│   └── phase5/dashboard.py  # Streamlit dashboard
├── templates/
│   └── pulse_email.html     # Jinja2 email template (inline CSS)
├── data/                    # Scraped reviews + themes (gitignored)
├── output/                  # Generated pulse files (gitignored)
└── config/                  # Gmail OAuth credentials (gitignored)
```

## Documentation

See **`ARCHITECTURE.md`** for the full system design, phase-by-phase breakdown, deployment guide, and future enhancements.
