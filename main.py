import json
import os
import re
from pathlib import Path

from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, EmailStr

from src.phase1 import scraper
from src.phase2 import analyzer
from src.phase3 import report
from src.phase4 import emailer

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"

app = FastAPI(
    title="Groww Review Analyst API",
    description="Weekly pulse from Play Store reviews — scrape, analyse, report, email.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

pipeline_status: dict = {"running": False, "last_result": None}


# ── Helpers ──────────────────────────────────────────────────────

def _load_json(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _run_pipeline(weeks: int = 12, count: int = 500):
    """Run phases 1-3 sequentially (background-safe)."""
    pipeline_status["running"] = True
    pipeline_status["last_result"] = None
    try:
        reviews = scraper.run(weeks=weeks, count=count)
        themes = analyzer.run_step_a()
        analysis = report.run()
        pipeline_status["last_result"] = {
            "reviews": len(reviews),
            "themes": len(themes),
            "top_themes": len(analysis.get("themes", [])),
            "quotes": len(analysis.get("quotes", [])),
            "actions": len(analysis.get("actions", [])),
            "status": "success",
        }
    except Exception as e:
        pipeline_status["last_result"] = {"status": "error", "detail": str(e)}
    finally:
        pipeline_status["running"] = False


# ── Pydantic models ─────────────────────────────────────────────

class SendRequest(BaseModel):
    to: EmailStr
    mode: str = "send"  # "send" or "draft"


class PipelineRequest(BaseModel):
    weeks: int = 12
    count: int = 500


# ── Routes ───────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
def root():
    from fastapi.responses import RedirectResponse
    return RedirectResponse("/docs")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/status")
def get_status():
    """Current pipeline status and data availability."""
    return {
        "pipeline": pipeline_status,
        "data": {
            "reviews": (DATA_DIR / "raw_reviews.json").exists(),
            "themes": (DATA_DIR / "themes.json").exists(),
            "pulse": (OUTPUT_DIR / "weekly_pulse.html").exists(),
        },
    }


@app.post("/api/pipeline")
def run_full_pipeline(req: PipelineRequest, bg: BackgroundTasks):
    """Kick off phases 1-3 in the background."""
    if pipeline_status["running"]:
        raise HTTPException(409, "Pipeline is already running.")
    bg.add_task(_run_pipeline, req.weeks, req.count)
    return {"message": "Pipeline started", "weeks": req.weeks, "count": req.count}


@app.get("/api/themes")
def get_themes():
    """Return all identified themes (up to 5)."""
    data = _load_json(DATA_DIR / "themes.json")
    if not data:
        raise HTTPException(404, "No themes found. Run the pipeline first.")
    return data


@app.get("/api/reviews")
def get_reviews():
    """Return scraped reviews."""
    data = _load_json(DATA_DIR / "raw_reviews.json")
    if data is None:
        raise HTTPException(404, "No reviews found. Run Phase 1 first.")
    return {"count": len(data), "reviews": data}


@app.get("/api/pulse/md")
def get_pulse_md():
    """Return the weekly pulse as markdown."""
    path = OUTPUT_DIR / "weekly_pulse.md"
    if not path.exists():
        raise HTTPException(404, "No pulse found. Run Phase 3 first.")
    return {"markdown": path.read_text(encoding="utf-8")}


@app.get("/api/pulse/html", response_class=HTMLResponse)
def get_pulse_html():
    """Return the weekly pulse as rendered HTML."""
    path = OUTPUT_DIR / "weekly_pulse.html"
    if not path.exists():
        raise HTTPException(404, "No pulse found. Run Phase 3 first.")
    return path.read_text(encoding="utf-8")


@app.get("/api/pulse/meta")
def get_pulse_meta():
    """Return week label and scrape metadata."""
    meta = _load_json(DATA_DIR / "scrape_metadata.json") or {}
    html_path = OUTPUT_DIR / "weekly_pulse.html"
    week_label = ""
    if html_path.exists():
        m = re.search(r"Week of ([^<]+)", html_path.read_text(encoding="utf-8"))
        if m:
            week_label = m.group(1).strip()
    return {"week_label": week_label, "weeks": meta.get("weeks"), "review_count": meta.get("review_count")}


@app.post("/api/send")
def send_pulse(req: SendRequest):
    """Send or draft the weekly pulse email to any address."""
    html_path = OUTPUT_DIR / "weekly_pulse.html"
    if not html_path.exists():
        raise HTTPException(404, "No pulse found. Run the pipeline first.")

    html_body = html_path.read_text(encoding="utf-8")
    m = re.search(r"Week of ([^<]+)", html_body)
    week_label = m.group(1).strip() if m else "this week"
    subject = f"Groww Weekly Pulse — Week of {week_label}"

    if req.mode == "draft":
        draft_id = emailer.create_draft(subject, html_body, req.to)
        return {
            "mode": "draft",
            "draft_id": draft_id,
            "url": f"https://mail.google.com/mail/u/0/#drafts/{draft_id}",
        }
    else:
        msg_id = emailer.send_email(subject, html_body, req.to)
        return {"mode": "sent", "message_id": msg_id}


# ── CLI entry point (preserved) ─────────────────────────────────

def main(weeks: int = 12, count: int = 500):
    reviews = scraper.run(weeks=weeks, count=count)
    print(f"\nPhase 1 complete — {len(reviews)} reviews ready for analysis.\n")

    themes = analyzer.run_step_a()
    print(f"\nPhase 2A complete — {len(themes)} themes identified.\n")

    report.run()
    print("\nPhase 3 complete — Weekly pulse saved to output/.\n")

    emailer.run()
    print("\nPhase 4 complete — Gmail draft created.\n")


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 10000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
