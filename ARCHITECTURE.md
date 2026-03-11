# Groww Play Store Review Analyst — Weekly Pulse Generator

## Overview

A pipeline that imports **8–12 weeks** of public Play Store reviews for the **Groww** app, analyses them (theme generation with Grok or keyword fallback; **synthesis with Gemini**), and produces a scannable **Weekly Pulse (≤ 250 words)** containing top 3 themes, 3 user quotes, and 3 action ideas — with **zero PII** in any artifact. A **Streamlit dashboard** serves as the control surface — view the pulse, explore reviews, and trigger the draft email with one click.

---

## Project Constraints

| Constraint | Rule |
|---|---|
| **No PII** | No usernames, emails, or IDs in any artifact — scrape, analysis, report, or email |
| **Public data only** | Use public Play Store review exports only — no scraping behind logins |
| **Themes** | 3–5 themes max |
| **Note length** | Weekly pulse must be scannable, **≤ 250 words** |
| **Note contents** | Top 3 themes, 3 user quotes, 3 action ideas |
| **Time window** | Import reviews from the last **8–12 weeks** |

**PII enforcement:** `userName`, `reviewId`, and any other identifiers are stripped at the scrape boundary (Phase 1) and never forwarded to the LLM, the report, the dashboard, or the email. Quotes carry only the star rating — no attribution.

---

## High-Level Flow

```
┌─────────────┐     ┌──────────────────┐     ┌──────────────────┐     ┌──────────────┐
│  Play Store  │────▶│  Review Storage   │────▶│  Grok Analysis   │────▶│ Weekly Pulse │
│  Scraper     │     │  (Local JSON/CSV) │     │  (xAI API)       │     │  Report      │
└─────────────┘     └──────────────────┘     └──────────────────┘     └──────┬───────┘
                                                                              │
                                                                              ▼
                                                                   ┌──────────────────┐
                                                                   │  Streamlit        │
                                                                   │  Dashboard        │
                                                                   │  ┌──────────────┐ │
                                                                   │  │ View Pulse   │ │
                                                                   │  │ Browse Revs  │ │
                                                                   │  │ [Send Email] │ │
                                                                   │  └──────────────┘ │
                                                                   └────────┬─────────┘
                                                                            │ click
                                                                            ▼
                                                                   ┌──────────────┐
                                                                   │  Draft Email  │
                                                                   │  (Gmail API)  │
                                                                   └──────────────┘
```

---

## Phases

### Phase 1 — Data Collection (Play Store Scraper)

**Goal:** Import reviews from the last **8–12 weeks** for the Groww app from the public Google Play Store (no login required).

| Aspect | Detail |
|---|---|
| **Library** | `google-play-scraper` (Python) — public API, no authentication |
| **Language filter** | `langdetect` — only English reviews are kept |
| **App ID** | `com.nextbillion.groww` |
| **Time window** | Last 8–12 weeks (configurable, default 12 weeks) |
| **Fields captured** | `score` (rating), `title`, `content` (review text), `thumbsUpCount`, `at` (date) |
| **Fields dropped** | `userName`, `reviewId`, and all other identifiers — stripped before storage |
| **Filters** | English only, no emojis, more than 5 words |
| **Output** | `data/raw_reviews.json` |

**Module:** `src/phase1/scraper.py`

```
def fetch_reviews(app_id, weeks=12, count=500) -> list[dict]
    # 1. Use google_play_scraper.reviews() with continuation token for pagination
    # 2. Filter reviews where `at` >= (today - weeks*7 days)
    # 3. Drop non-English reviews (langdetect)
    # 4. Drop reviews with emojis or <= 5 words
    # 5. Strip PII fields (userName, reviewId) before collecting
    # 6. Return list of review dicts
    # 7. Persist to data/raw_reviews.json
```

**Key decisions:**
- **Public data only:** `google-play-scraper` hits the publicly available Play Store — no login, no API key, no terms-of-service issues.
- **English only:** `langdetect` filters out Hindi, Hinglish, and other non-English reviews so the LLM gets clean, consistent input.
- **Strip PII at source:** `userName`, `reviewId`, and any other identifiers are excluded before writing to `raw_reviews.json`. No downstream phase ever sees personal data.
- **8–12 week window** gives enough volume for meaningful theme detection across a quarter.
- **Title field included:** Many reviewers summarize their sentiment in the title, providing a strong signal for theme extraction.
- Store raw JSON so every downstream phase can re-process without re-scraping.
- Add a `scrape_metadata.json` with run timestamp, review count, and week range for traceability.

---

### Phase 2 — Review Analysis with Grok

**Goal:** Use Grok to **generate themes first**, then **group reviews** into those themes and extract quotes + actions.

| Aspect | Detail |
|---|---|
| **LLM Provider** | xAI — Grok model |
| **SDK / Client** | `openai` Python SDK (xAI exposes an OpenAI-compatible API at `https://api.x.ai/v1`) |
| **Model** | `grok-3-mini-fast` (cost-efficient; swap to `grok-3` for richer output) |
| **Auth** | `XAI_API_KEY` environment variable |
| **Theme limit** | 3–5 themes max |
| **Quote limit** | 3 most representative quotes |

**Module:** `src/phase2/analyzer.py`

```
def analyze_reviews(reviews: list[dict]) -> dict
    # Returns:
    # {
    #   "themes":  [{"name": str, "sentiment": str, "mention_count": int, "review_indices": [int]}, ...],
    #   "quotes":  [{"text": str, "stars": int}, ...],   # exactly 3
    #   "actions": [str, str, str]
    # }
```

**Prompt strategy (two-step — generate themes, then group):**

| Step | Purpose | Input | Output |
|---|---|---|---|
| **Step A — Theme generation** | Read all reviews and identify 3–5 recurring themes | Batched review texts (chunked if needed) | JSON with `themes[]` (name + sentiment) |
| **Step B — Grouping & synthesis** | Assign each review to a theme, pick 3 best quotes, generate 3 action ideas | Reviews + themes from Step A | Final structured JSON with grouped reviews, quotes, actions |

This two-step approach ensures themes are **discovered from the data** rather than fitting reviews into predetermined categories.

**Prompt template (Step A — Theme generation):**

```
You are a product analyst for a fintech app called Groww.
Do NOT include any personally identifiable information (names,
usernames, emails, IDs, etc.) in your output.

Read the following Play Store reviews from the last 8–12 weeks.
Identify between 3 and 5 recurring themes (no more than 5).

For each theme provide:
  - "name": a short label (2-4 words)
  - "sentiment": positive | negative | mixed

Respond ONLY with valid JSON: { "themes": [...] }
```

**Prompt template (Step B — Grouping & synthesis):**

```
You are a product analyst for a fintech app called Groww.
Do NOT include any personally identifiable information in your output.

Given these themes and the original reviews, produce a JSON object:

1. "themes" — the same 3–5 themes, now enriched with:
   - "mention_count": approximate number of reviews matching this theme

2. "quotes" — exactly 3 most representative real user quotes, each with:
   - "text": exact quote from a review (no names, no IDs)
   - "stars": star rating

3. "actions" — exactly 3 concrete, actionable ideas the product team
   should consider, each as a single sentence.

Total word count of all themes + quotes + actions must be ≤ 250 words.
Respond ONLY with valid JSON.
```

**Key decisions:**
- **Generate-then-group:** Step A (Phase 2A) discovers themes; **Step B (synthesis)** is performed in **Phase 3** using **Gemini**: themes + reviews → 3 quotes, 3 actions, mention counts. This keeps report-generation logic and the report LLM in one place (Phase 3).
- Use the OpenAI-compatible SDK for Grok (Phase 2A); use `google-generativeai` for Gemini (Phase 3).
- Two-step prompting keeps each call focused and token-efficient.
- Enforce JSON-only output (`response_format: { type: "json_object" }`) for reliable parsing.
- Hard cap of **5 themes** enforced both in the prompt and with post-processing validation (truncate if LLM returns more).
- If review volume exceeds context window, chunk into batches of ~50 reviews, run Step A per-batch, then merge themes before a single Step B pass.

---

### Phase 3 — Report Generation (Weekly Pulse)

**Goal:** Use **Gemini** to synthesize themes + reviews into a final analysis (top 3 themes with mention counts, 3 quotes, 3 actions), then format the result into a scannable, one-page weekly pulse — **≤ 250 words**.

| Aspect | Detail |
|---|---|
| **LLM for synthesis** | Google — Gemini (e.g. `gemini-2.5-flash`) |
| **SDK** | `google-generativeai` |
| **Auth** | `GEMINI_API_KEY` or `GOOGLE_API_KEY` in `.env` |
| **Fallback** | When API key missing or rate-limited: heuristic quotes + generic actions |

**Module:** `src/phase3/report.py`

```
def run() -> dict
    # 1. Load themes (data/themes.json) and reviews (data/raw_reviews.json)
    # 2. Call Gemini to produce: top 3 themes (mention_count), 3 quotes, 3 actions (≤250 words)
    # 3. generate_pulse(analysis, week_label) -> Markdown
    # 4. generate_pulse_html(analysis, week_label) -> HTML via Jinja2
    # 5. Save to output/weekly_pulse.md and output/weekly_pulse.html
```

**Report structure (top 3 themes, 3 quotes, 3 actions):**

```
╔══════════════════════════════════════════════════╗
║          GROWW — WEEKLY REVIEW PULSE             ║
║          Week of Mar 2 – Mar 8, 2026             ║
║          Reviews analysed: 8–12 weeks window     ║
╠══════════════════════════════════════════════════╣
║                                                  ║
║  TOP THEMES                                      ║
║  ─────────                                       ║
║  1. App Crashes (negative) — ~38 mentions        ║
║  2. Easy KYC (positive) — ~27 mentions           ║
║  3. Withdrawal Delays (negative) — ~21 mentions  ║
║                                                  ║
║  USER QUOTES                                     ║
║  ───────────                                     ║
║  "App keeps crashing when I try to place an      ║
║   order during market hours"  (★★☆☆☆)           ║
║                                                  ║
║  "KYC was done in 2 minutes, very smooth"        ║
║   (★★★★★)                                       ║
║                                                  ║
║  "Withdrawal took 5 days, no status updates"     ║
║   (★☆☆☆☆)                                       ║
║                                                  ║
║  ACTION IDEAS                                    ║
║  ────────────                                    ║
║  1. Investigate crash reports on Android 14...   ║
║  2. Highlight the fast KYC flow in onboard...    ║
║  3. Add estimated withdrawal timelines in...     ║
║                                                  ║
╚══════════════════════════════════════════════════╝
```

**Output formats:**
| Format | File | Purpose |
|---|---|---|
| Markdown | `output/weekly_pulse.md` | Human-readable, version-controllable |
| HTML | `output/weekly_pulse.html` | Email body rendering |

**Key decisions:**
- **250-word hard cap.** `generate_pulse()` counts words and raises a warning if the output exceeds the limit; the LLM prompt already enforces this, but a server-side check acts as a safety net.
- Report shows the **top 3 themes** (out of the 3–5 generated), **3 quotes**, and **3 action ideas** — nothing more, keeping it scannable.
- No attribution on quotes — just the star rating in parentheses. No usernames, no IDs.
- Generate both Markdown (for archival / Git) and HTML (for email body).
- Use a Jinja2 template (`templates/pulse_email.html`) for the HTML version so styling is decoupled from logic.
- Week label is auto-computed from the scrape date range.

---

### Phase 4 — Email Delivery (Draft Email)

**Goal:** Create a Gmail draft containing the Weekly Pulse so the user can review and send.

| Aspect | Detail |
|---|---|
| **Service** | Gmail API (via `google-api-python-client`) |
| **Auth** | OAuth 2.0 — `credentials.json` + token refresh |
| **Scope** | `https://www.googleapis.com/auth/gmail.compose` (drafts only) |
| **Action** | Create draft (NOT auto-send) |

**Module:** `src/phase4/emailer.py`

```
def create_draft(subject: str, html_body: str, to: str) -> str
    # 1. Build MIME message with HTML body
    # 2. Authenticate with Gmail API
    # 3. Call drafts.create()
    # 4. Return draft ID + Gmail link
```

**Key decisions:**
- Draft-only scope keeps permissions minimal and safe.
- Subject line auto-generated: `"Groww Weekly Pulse — Week of {date_range}"`.
- Credentials stored in `config/credentials.json` (gitignored).
- First run triggers browser-based OAuth consent; subsequent runs use cached token.

---

### Phase 5 — Dashboard (Streamlit)

**Goal:** Provide a single-page web dashboard as the control surface for the entire pipeline — view the pulse, browse raw reviews, and trigger email delivery with one click.

| Aspect | Detail |
|---|---|
| **Framework** | Streamlit |
| **Entry point** | `app.py` (run via `streamlit run app.py`) |
| **State management** | `st.session_state` for pipeline progress and cached results |

**Module:** `src/phase5/dashboard.py` (entry point: `app.py`)

```
# Streamlit app — single file, calls into src/ modules

# Sidebar
#   - "Fetch Reviews" button  → runs Phase 1
#   - "Analyze with Grok" button → runs Phase 2
#   - "Send Email Draft" button → runs Phase 4
#   - Status indicators for each phase (idle / running / done / error)

# Main area — three tabs
#   Tab 1: Weekly Pulse   → rendered report (themes, quotes, actions)
#   Tab 2: Raw Reviews    → searchable/filterable table of scraped reviews
#   Tab 3: Pipeline Log   → timestamped log of what ran and any errors
```

**Dashboard layout:**

```
┌─────────────────────────────────────────────────────────────────┐
│  GROWW REVIEW ANALYST                                           │
├──────────┬──────────────────────────────────────────────────────┤
│          │                                                      │
│ CONTROLS │  ┌─── Weekly Pulse ─── Raw Reviews ─── Log ───┐     │
│          │  │                                             │     │
│ [Fetch   │  │  GROWW — WEEKLY REVIEW PULSE                │     │
│  Reviews]│  │  Week of Mar 2 – Mar 8, 2026                │     │
│  ✅ Done │  │  Reviews: 8–12 week window | ≤250 words     │     │
│          │  │                                             │     │
│ [Analyze │  │  TOP 3 THEMES                               │     │
│  w/ Grok]│  │  1. App Crashes (negative) — ~38 mentions   │     │
│  ✅ Done │  │  2. Easy KYC (positive) — ~27 mentions      │     │
│          │  │  3. Withdrawal Delays (neg.) — ~21 mentions │     │
│ ───────  │  │                                             │     │
│ Recipient│  │  USER QUOTES (3)                            │     │
│ [email]  │  │  "App keeps crashing when..." (★★☆☆☆)      │     │
│          │  │  "KYC was done in 2 minutes..." (★★★★★)     │     │
│ [Send    │  │  "Withdrawal took 5 days..." (★☆☆☆☆)       │     │
│  Email   │  │                                             │     │
│  Draft]  │  │  ACTION IDEAS (3)                           │     │
│  ⏳ Idle │  │  1. Investigate crash reports on...         │     │
│          │  │  2. Highlight the fast KYC flow in...       │     │
│          │  │  3. Add estimated withdrawal timelines...   │     │
│          │  │                                             │     │
│          │  └─────────────────────────────────────────────┘     │
└──────────┴──────────────────────────────────────────────────────┘
```

**Tab details:**

| Tab | Content | Interactive elements |
|---|---|---|
| **Weekly Pulse** | Rendered ≤250-word report — top 3 themes with sentiment badges, 3 user quotes (no attribution), 3 action items | None (read-only display) |
| **Raw Reviews** | `st.dataframe` of all scraped reviews with columns: date, stars, review text, thumbs-up count (no user names) | Star-rating filter (slider), text search, sort by date/rating |
| **Pipeline Log** | Timestamped entries showing each phase's start/end, review count, token usage, errors | Clear log button |

**Sidebar controls — step-by-step flow:**

| # | Button | What it does | State after success |
|---|---|---|---|
| 1 | **Fetch Reviews** | Runs `scraper.fetch_reviews()`, stores result in `st.session_state.reviews` | Shows review count badge |
| 2 | **Analyze with Grok** | Runs `analyzer.analyze_reviews()` on fetched reviews, stores analysis in session state | Populates Weekly Pulse tab |
| 3 | **Send Email Draft** | Takes recipient from text input, runs `emailer.create_draft()` with the generated HTML pulse | Shows success toast with Gmail draft link |

Buttons are enabled sequentially — "Analyze" is disabled until reviews are fetched, "Send Email" is disabled until analysis is complete. This prevents out-of-order execution.

**Key decisions:**
- Streamlit keeps the dashboard as a single Python file with no frontend build step.
- Pipeline phases are triggered manually via buttons rather than auto-running, giving the user full control over when to call the Grok API (cost) and when to create the email draft.
- `st.session_state` holds intermediate results so phases don't need to re-run unless the user explicitly clicks again.
- A `st.spinner` wraps each long-running operation (scraping, LLM call) for clear progress feedback.
- The "Raw Reviews" tab lets the user sanity-check scraped data before spending Grok tokens on analysis.

---

## Project Structure

```
groww-review-analyst/
│
├── config/
│   ├── .env.example          # Template for environment variables
│   └── credentials.json      # Gmail OAuth credentials (gitignored)
│
├── data/
│   ├── raw_reviews.json      # Scraped reviews (auto-generated)
│   ├── themes.json           # Phase 2A output (3–5 themes)
│   └── scrape_metadata.json  # Scrape run info
│
├── output/
│   ├── weekly_pulse.md       # Generated report (Markdown)
│   └── weekly_pulse.html     # Generated report (HTML for email)
│
├── templates/
│   └── pulse_email.html      # Jinja2 HTML email template
│
├── src/
│   ├── __init__.py
│   ├── phase1/
│   │   ├── __init__.py
│   │   └── scraper.py        # Phase 1 — Play Store data collection
│   ├── phase2/
│   │   ├── __init__.py
│   │   └── analyzer.py       # Phase 2 — Grok-powered analysis
│   ├── phase3/
│   │   ├── __init__.py
│   │   └── report.py         # Phase 3 — Report generation
│   ├── phase4/
│   │   ├── __init__.py
│   │   └── emailer.py        # Phase 4 — Gmail draft creation
│   └── phase5/
│       ├── __init__.py
│       └── dashboard.py      # Phase 5 — Streamlit dashboard
│
├── app.py                    # Streamlit entry point (imports phase5)
├── main.py                   # CLI orchestrator — runs all phases in sequence
├── requirements.txt          # Python dependencies
├── .env                      # API keys (gitignored)
├── .gitignore
└── ARCHITECTURE.md           # This file
```

---

## Tech Stack

| Component | Technology | Why |
|---|---|---|
| Language | Python 3.11+ | Rich ecosystem for scraping, API clients, templating |
| Play Store Scraping | `google-play-scraper` | Lightweight, no auth required, well-maintained |
| Language Detection | `langdetect` | Filters non-English reviews before LLM processing |
| LLM (Phase 2A themes) | Grok via xAI API | Theme generation; OpenAI-compatible endpoint |
| LLM Client (Grok) | `openai` Python SDK | Works with xAI's compatible API |
| LLM (Phase 3 synthesis) | Google Gemini (`google-generativeai`) | Produces quotes + actions from themes + reviews; free tier available |
| Dashboard | `streamlit` | Single-file Python dashboard, no frontend build step, built-in widgets |
| Templating | `jinja2` | Clean separation of report logic and presentation |
| Email | `google-api-python-client` | Official Gmail API client for draft creation |
| Env Management | `python-dotenv` | Secure config loading from `.env` |

---

## Environment Variables

```env
# .env
XAI_API_KEY=xai-xxxxxxxxxxxxxxxxxxxx     # Grok (Phase 2A theme generation)
GEMINI_API_KEY=xxxxxxxxxxxxxxxxxxxx      # Gemini (Phase 3 synthesis); or GOOGLE_API_KEY
USE_MOCK_LLM=false                       # true = use keyword/heuristic fallbacks only
GMAIL_SENDER=you@gmail.com               # Your Gmail address
GMAIL_RECIPIENT=you@gmail.com            # Draft recipient (yourself)
```

---

## Orchestration

The project supports **two entry points** — a CLI for headless/scripted runs and the Streamlit dashboard for interactive use.

### CLI (`main.py`)

```python
# Pseudocode — runs all phases end-to-end
def main():
    # Phase 1
    reviews = scraper.fetch_reviews("com.nextbillion.groww", weeks=12)

    # Phase 2
    analysis = analyzer.analyze_reviews(reviews)

    # Phase 3
    md_report = report.generate_pulse(analysis, week_label)
    html_report = report.generate_pulse_html(analysis, week_label)

    # Phase 4
    draft_id = emailer.create_draft(
        subject=f"Groww Weekly Pulse — {week_label}",
        html_body=html_report,
        to=GMAIL_RECIPIENT
    )

    print(f"Draft created: https://mail.google.com/mail/#drafts/{draft_id}")
```

### Dashboard (`app.py`)

```bash
streamlit run app.py
```

The dashboard calls the same `src/` modules but lets the user trigger each phase individually via sidebar buttons, inspect intermediate results, and decide when to send the email draft.

---

## Error Handling & Edge Cases

| Scenario | Handling |
|---|---|
| Zero reviews in 8–12 week window | Log warning, generate report with "No reviews found" message |
| Grok API rate limit / timeout | Retry with exponential backoff (max 3 retries) |
| Grok returns malformed JSON | Validate with `json.loads()`; re-prompt once with stricter instructions |
| Gmail OAuth token expired | Auto-refresh via stored refresh token; if invalid, re-trigger consent |
| Grok returns > 5 themes | Post-processing truncates to top 5 by mention count; log a warning |
| Generated pulse exceeds 250 words | Log warning; trim action items to single clauses and re-check |
| Reviews exceed Grok context window | Chunk reviews into batches of ~50; run Step A per-batch then merge themes before Step B |
| Dashboard button clicked out of order | Buttons are sequentially enabled; disabled state prevents skipping phases |
| Long-running phase blocks dashboard | Each phase wrapped in `st.spinner`; Streamlit's built-in async keeps UI responsive |

---

## Phase Execution Summary

| Phase | Input | Output | Dependencies |
|---|---|---|---|
| **1 — Scrape** | App ID, 8–12 week window | `raw_reviews.json` | `google-play-scraper` |
| **2 — Analyze** | Raw reviews | `themes.json` (3–5 themes) | `openai` SDK (Grok) or keyword fallback |
| **Phase 3 — Report** | Themes + reviews | Gemini synthesizes → top 3 themes, 3 quotes, 3 actions; then Markdown + HTML report | `google-generativeai`, `jinja2` |
| **4 — Email** | HTML report | Gmail draft | `google-api-python-client`, OAuth creds |
| **5 — Dashboard** | All of the above | Interactive web UI | `streamlit` |
| **Scheduler** | CLI pipeline (`main.main(weeks=8, count=1000)`) | Weekly Gmail draft to `spnsn9@gmail.com` (8 weeks, 1000 reviews) | `schedule` Python library |

---

## Scheduler

**Goal:** Automatically generate and email the Weekly Pulse every week at **5:35 PM IST** to a **fixed recipient** (`spnsn9@gmail.com`), using the existing CLI pipeline with **8 weeks** of reviews and a **1000-review** cap.

| Aspect | Detail |
|---|---|
| **Entry point** | `scheduler.py` |
| **Trigger time** | Weekly, Monday at 17:35 local time (set OS timezone to IST to align with 5:35 PM IST) |
| **Recipient** | Fixed: `spnsn9@gmail.com` (set inside `scheduler.py`) |
| **Data limits** | Last **8 weeks** only; up to **1000 reviews** (no 5000+ run) |
| **What it runs** | Calls `main.main(weeks=8, count=1000)` which executes Phases 1–4 in sequence |
| **Library** | `schedule` (Python) |

**Module:** `scheduler.py`

```python
SCHEDULED_WEEKS = 8
SCHEDULED_COUNT = 1000

def run_weekly_pulse():
    os.environ["GMAIL_RECIPIENT"] = "spnsn9@gmail.com"
    main(weeks=SCHEDULED_WEEKS, count=SCHEDULED_COUNT)  # from main.py — phases 1–4

def main():
    schedule.every().monday.at("17:35").do(run_weekly_pulse)
    while True:
        schedule.run_pending()
        time.sleep(30)
```

**How to use:**

- Ensure `.env` is configured with the required API keys (Grok / Gemini) and Gmail OAuth is set up (`config/credentials.json`).
- Start the scheduler in a long-running environment:

```bash
python scheduler.py
```

The process must remain running (e.g. on a small VM or always-on machine). The scheduler uses **local system time**; set the OS timezone to **Asia/Kolkata** to align 17:35 local with **5:35 PM IST**.

### GitHub Actions integration

In addition to the long-running Python scheduler, a GitHub Actions workflow (`.github/workflows/weekly_pulse.yml`) runs the same pipeline on a **weekly cron**:

| Aspect | Detail |
|---|---|
| **Trigger** | `cron: \"5 12 * * MON\"` (12:05 UTC ≈ 17:35 IST on Mondays) |
| **Runner** | `ubuntu-latest` |
| **What it runs** | Installs deps, writes `.env` from repository secrets, and calls `scheduler.run_weekly_pulse()` (8 weeks, 1000 reviews, recipient `spnsn9@gmail.com`) |
| **Artifacts** | Uploads `output/weekly_pulse.md` and `output/weekly_pulse.html` as a build artifact |

This provides a **cloud scheduler** that mirrors the local behaviour. For Gmail delivery from Actions, you must ensure suitable credentials are available to the workflow (for most real setups, that means using a service account or SMTP-based mailer instead of interactive OAuth).

## Future Enhancements (Out of Scope)

- **Historical tracking:** Store weekly analyses in a database to show trends over time.
- **Multi-app support:** Parameterize app ID to compare Groww vs competitors.
- **Slack/Teams delivery:** Post the pulse to a team channel instead of (or in addition to) email.
- **Trend charts:** Add week-over-week sentiment charts to the dashboard once historical data is stored.
