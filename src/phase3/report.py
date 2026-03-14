"""
Phase 3 — Report Generation (Weekly Pulse).

Uses Gemini to synthesize themes + reviews into 3 themes, 3 quotes, 3 actions,
then formats the result into a scannable ≤250-word report (Markdown + HTML).
"""

import json
import os
import re
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from jinja2 import Environment, FileSystemLoader

load_dotenv()

# Paths
ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"
TEMPLATES_DIR = ROOT / "templates"

GEMINI_MODEL = "gemini-2.5-flash"
MAX_WORDS = 250

# Sample size of reviews to send to Gemini (to stay under context limits)
REVIEW_SAMPLE_SIZE = 150


def _load_themes() -> list[dict]:
    path = DATA_DIR / "themes.json"
    if not path.exists():
        raise FileNotFoundError(f"Run Phase 2A first: {path} not found")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("themes", [])


def _load_reviews() -> list[dict]:
    path = DATA_DIR / "raw_reviews.json"
    if not path.exists():
        raise FileNotFoundError(f"Run Phase 1 first: {path} not found")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_week_label() -> str:
    meta_path = DATA_DIR / "scrape_metadata.json"
    if meta_path.exists():
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        weeks = meta.get("weeks", 12)
        from datetime import timedelta
        end = datetime.utcnow()
        start = end - timedelta(weeks=weeks)
        return f"{start.strftime('%b %d')} – {end.strftime('%b %d, %Y')}"
    return datetime.utcnow().strftime("%b %d – %b %d, %Y")


def _synthesize_with_gemini(themes: list[dict], reviews: list[dict]) -> dict:
    """Use Gemini to produce top 3 themes (with mention_count), 3 quotes, 3 actions."""
    try:
        import google.generativeai as genai
    except ImportError:
        raise RuntimeError("Install google-generativeai: pip install google-generativeai")

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY or GOOGLE_API_KEY not set in .env")

    genai.configure(api_key=api_key)

    # Limit review text sent to stay within context
    sample = reviews[:REVIEW_SAMPLE_SIZE]
    reviews_text = "\n".join(
        f"- ({r.get('score', '?')} stars) {r.get('content', '')[:200]}"
        for r in sample
    )
    themes_text = json.dumps(themes, indent=2)

    prompt = f"""You are a product analyst for the fintech app Groww.
Do NOT include any personally identifiable information (names, usernames, emails, IDs) in your output.

Given these THEMES (from Phase 2) and a sample of PLAY STORE REVIEWS, produce a JSON object with:

1. "themes" — exactly the TOP 3 themes from the list below, each with:
   - "name": same as given
   - "sentiment": positive | negative | mixed (from the list)
   - "mention_count": approximate number of reviews in the sample that match this theme (integer)

2. "quotes" — exactly 3 real user quotes. Each quote must be an EXACT substring from one of the reviews below. Each object:
   - "text": exact quote from a review (no names)
   - "stars": star rating (1-5)

3. "actions" — exactly 3 concrete, actionable ideas for the product team, each one short sentence.

Total word count of themes + quotes + actions must be ≤ 250 words.
Respond ONLY with valid JSON, no markdown fences.

THEMES:
{themes_text}

REVIEWS (sample):
{reviews_text}
"""

    model = genai.GenerativeModel(GEMINI_MODEL)
    generation_config = genai.GenerationConfig(
        response_mime_type="application/json",
        temperature=0.3,
    )
    response = model.generate_content(
        prompt,
        generation_config=generation_config,
    )
    raw = response.text.strip()
    # Remove markdown code block if present
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)


def _synthesize_fallback(themes: list[dict], reviews: list[dict]) -> dict:
    """Build analysis without LLM: top 3 themes, 3 heuristic quotes, 3 generic actions."""
    top_themes = themes[:3]
    for t in top_themes:
        t["mention_count"] = t.get("mention_count", 0) or 10  # placeholder

    # Pick 3 diverse quotes: one low, one mid, one high rating; prefer longer content
    by_stars: dict[int, list[dict]] = {}
    for r in reviews:
        s = r.get("score", 3)
        if s not in by_stars:
            by_stars[s] = []
        by_stars[s].append(r)
    quotes = []
    for stars in [1, 3, 5]:
        if stars in by_stars and by_stars[stars]:
            r = max(by_stars[stars], key=lambda x: len(x.get("content", "")))
            content = (r.get("content") or "").strip()
            if len(content) > 15:
                quotes.append({"text": content[:200], "stars": stars})
    while len(quotes) < 3 and reviews:
        r = reviews[len(quotes) % len(reviews)]
        content = (r.get("content") or "").strip()
        if len(content) > 10:
            quotes.append({"text": content[:200], "stars": r.get("score", 3)})
        if len(quotes) >= 3:
            break
    quotes = quotes[:3]

    actions = [
        "Prioritise stability fixes and crash reports from the affected devices.",
        "Improve visibility of support channels and set response-time expectations.",
        "Consider a short in-app survey to capture feedback on recent changes.",
    ]
    return {
        "themes": top_themes,
        "quotes": quotes,
        "actions": actions[:3],
    }


def _word_count(text: str) -> int:
    return len(re.findall(r"\S+", text))


def _stars_display(n: int) -> str:
    return "★" * n + "☆" * (5 - n)


def generate_pulse(analysis: dict, week_label: str) -> str:
    """Produce markdown report (top 3 themes, 3 quotes, 3 actions)."""
    themes = analysis.get("themes", [])[:3]
    quotes = analysis.get("quotes", [])[:3]
    actions = analysis.get("actions", [])[:3]

    lines = [
        "# GROWW — Weekly Review Pulse",
        f"**Week of {week_label}**",
        "Reviews analysed: 8–12 weeks window",
        "",
        "## Top themes",
        "",
    ]
    for i, t in enumerate(themes, 1):
        name = t.get("name", "")
        sentiment = t.get("sentiment", "mixed")
        count = t.get("mention_count", 0)
        lines.append(f"{i}. **{name}** ({sentiment}) — ~{count} mentions")
    lines.extend(["", "## User quotes", ""])
    for q in quotes:
        text = q.get("text", "")
        stars = q.get("stars", 3)
        lines.append(f'- "{text}"')
        lines.append(f"  ({_stars_display(stars)})")
        lines.append("")
    lines.extend(["## Action ideas", ""])
    for i, a in enumerate(actions, 1):
        lines.append(f"{i}. {a}")
    lines.append("")

    md = "\n".join(lines)
    n = _word_count(md)
    if n > MAX_WORDS:
        import warnings
        warnings.warn(f"Report has {n} words (max {MAX_WORDS}). Consider shortening.")
    return md


def generate_pulse_html(analysis: dict, week_label: str) -> str:
    """Produce HTML report using Jinja2 template."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)

    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))
    template_path = TEMPLATES_DIR / "pulse_email.html"
    if not template_path.exists():
        return _html_fallback(analysis, week_label)

    template = env.get_template("pulse_email.html")
    themes = analysis.get("themes", [])[:3]
    quotes = analysis.get("quotes", [])[:3]
    actions = analysis.get("actions", [])[:3]

    for q in quotes:
        q["stars_display"] = _stars_display(q.get("stars", 3))

    return template.render(
        week_label=week_label,
        themes=themes,
        quotes=quotes,
        actions=actions,
        stars_display=_stars_display,
    )


def _html_fallback(analysis: dict, week_label: str) -> str:
    """Email-safe inline-styled HTML fallback (used when Jinja2 template is missing)."""
    themes = analysis.get("themes", [])[:3]
    quotes = analysis.get("quotes", [])[:3]
    actions = analysis.get("actions", [])[:3]

    theme_rows = ""
    for t in themes:
        name = t.get("name", "")
        sentiment = t.get("sentiment", "mixed")
        count = t.get("mention_count", 0)
        theme_rows += (
            f'<tr><td style="padding:10px 12px;background-color:#0f172a;border-bottom:1px solid #1a2332;">'
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>'
            f'<td valign="top"><p style="margin:0;font-size:15px;font-weight:600;color:#f9fafb;">{name}</p>'
            f'<p style="margin:3px 0 0;font-size:12px;color:#6b7280;">~{count} mentions</p></td>'
            f'<td align="right" valign="middle" width="90">'
            f'<span style="display:inline-block;padding:4px 10px;border-radius:999px;border:1px solid #374151;'
            f'background-color:#1e293b;font-size:11px;color:#fbbf24;text-transform:capitalize;font-weight:600;">{sentiment}</span>'
            f'</td></tr></table></td></tr>'
        )

    quote_rows = ""
    for q in quotes:
        text = q.get("text", "")
        stars = _stars_display(q.get("stars", 3))
        quote_rows += (
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:10px;">'
            f'<tr><td style="padding:12px 14px;border-radius:10px;border:1px solid #374151;background-color:#0f172a;">'
            f'<p style="margin:0 0 6px;font-size:14px;color:#e5e7eb;font-style:italic;line-height:1.5;">&ldquo;{text}&rdquo;</p>'
            f'<p style="margin:0;font-size:13px;color:#fbbf24;letter-spacing:2px;">{stars}</p>'
            f'</td></tr></table>'
        )

    action_rows = ""
    for i, a in enumerate(actions, 1):
        action_rows += (
            f'<tr><td width="24" valign="top" style="font-size:13px;color:#4ade80;padding:5px 0;font-weight:700;">{i}.</td>'
            f'<td style="font-size:14px;color:#e5e7eb;padding:5px 0;line-height:1.5;">{a}</td></tr>'
        )

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>Groww Weekly Pulse</title></head>
<body style="margin:0;padding:0;background-color:#0b1020;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#0b1020;">
<tr><td align="center" style="padding:28px 12px;">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0" style="max-width:600px;width:100%;background-color:#111828;border:1px solid #1f2937;border-radius:16px;overflow:hidden;">

<tr><td bgcolor="#020617" style="background-color:#020617;padding:18px 24px;border-bottom:2px solid #1a3a2a;">
<table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>
<td width="44" valign="middle" style="padding-right:14px;">
<table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>
<td width="36" height="36" align="center" valign="middle" bgcolor="#166534" style="background-color:#166534;border-radius:10px;border:2px solid #22c55e;font-size:16px;font-weight:700;color:#e5e7eb;text-align:center;line-height:36px;">G</td>
</tr></table></td>
<td valign="middle">
<p style="margin:0 0 2px;font-size:16px;font-weight:700;color:#e5e7eb;">Groww Customer Signal</p>
<p style="margin:0;font-size:12px;color:#9ca3af;">Weekly pulse from Play Store reviews</p>
</td></tr></table></td></tr>

<tr><td style="padding:20px 24px 24px;color:#f9fafb;">
<h1 style="margin:0 0 8px;font-size:22px;letter-spacing:0.04em;text-transform:uppercase;color:#f9fafb;font-weight:700;">Customer Signal — Weekly Note</h1>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:16px;">
<tr><td style="font-size:15px;color:#f9fafb;font-weight:700;">Week of {week_label}</td>
<td align="right" style="font-size:12px;color:#6b7280;">8–12 weeks window</td></tr></table>

<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
<tr><td style="padding-top:4px;border-top:1px solid #1f2937;">
<p style="margin:12px 0 10px;font-size:13px;text-transform:uppercase;letter-spacing:0.1em;color:#4ade80;font-weight:700;">&#9650; Top themes</p>
</td></tr></table>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">{theme_rows}</table>

<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top:20px;">
<tr><td style="padding-top:4px;border-top:1px solid #1f2937;">
<p style="margin:12px 0 10px;font-size:13px;text-transform:uppercase;letter-spacing:0.1em;color:#4ade80;font-weight:700;">&#9662; User quotes</p>
</td></tr></table>
{quote_rows}

<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top:20px;">
<tr><td style="padding-top:4px;border-top:1px solid #1f2937;">
<p style="margin:12px 0 10px;font-size:13px;text-transform:uppercase;letter-spacing:0.1em;color:#4ade80;font-weight:700;">&#9654; Action ideas</p>
</td></tr></table>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
<tr><td style="padding:14px 16px;border-radius:12px;border:2px solid #166534;background-color:#052e16;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">{action_rows}</table>
</td></tr></table>

<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top:22px;">
<tr><td align="center" style="padding-top:12px;border-top:1px solid #1f2937;">
<p style="margin:0;font-size:11px;color:#4b5563;">Auto-generated by Groww Review Analyst &middot; No PII included</p>
</td></tr></table>
</td></tr></table>
</td></tr></table>
</body></html>"""


def save_report(md: str, html: str) -> tuple[str, str]:
    """Write weekly_pulse.md and weekly_pulse.html to output/."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    md_path = OUTPUT_DIR / "weekly_pulse.md"
    html_path = OUTPUT_DIR / "weekly_pulse.html"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    return str(md_path), str(html_path)


def run() -> dict:
    """Run Phase 3: load themes + reviews, synthesize with Gemini (or fallback), generate report."""
    print("Phase 3 — Report Generation (Weekly Pulse)")
    themes = _load_themes()
    reviews = _load_reviews()
    week_label = _load_week_label()
    print(f"  Loaded {len(themes)} themes, {len(reviews)} reviews")
    print(f"  Week label: {week_label}")

    use_mock = os.getenv("USE_MOCK_LLM", "").strip().lower() in ("1", "true", "yes")
    try:
        if use_mock:
            print("  Using fallback synthesis (USE_MOCK_LLM is set).")
            analysis = _synthesize_fallback(themes, reviews)
        else:
            print("  Synthesizing with Gemini...")
            analysis = _synthesize_with_gemini(themes, reviews)
    except Exception as e:
        err = str(e).lower()
        if "api key" in err or "api_key" in err or "403" in err or "429" in err:
            print(f"  Gemini unavailable ({e}). Using fallback synthesis.")
            analysis = _synthesize_fallback(themes, reviews)
        else:
            raise

    # Enforce structure
    analysis["themes"] = analysis.get("themes", [])[:3]
    analysis["quotes"] = analysis.get("quotes", [])[:3]
    analysis["actions"] = analysis.get("actions", [])[:3]
    for t in analysis["themes"]:
        t.setdefault("mention_count", 0)
    for q in analysis["quotes"]:
        q.setdefault("stars", 3)

    md = generate_pulse(analysis, week_label)
    html = generate_pulse_html(analysis, week_label)
    n = _word_count(md)
    print(f"  Report word count: {n} (max {MAX_WORDS})")
    if n > MAX_WORDS:
        print(f"  Warning: report exceeds {MAX_WORDS} words.")

    md_path, html_path = save_report(md, html)
    print(f"  Saved: {md_path}")
    print(f"  Saved: {html_path}")
    return analysis
