import json
import os
import math
from collections import defaultdict

from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")

XAI_BASE_URL = "https://api.x.ai/v1"
XAI_MODEL = "grok-3-mini-fast"
MAX_THEMES = 5
CHUNK_SIZE = 50

# Keyword-based fallback themes (Groww fintech app)
THEME_KEYWORDS: dict[str, list[str]] = {
    "App Crashes & Bugs": [
        "crash", "crashes", "crashing", "hang", "freeze", "freezing",
        "bug", "bugs", "glitch", "not working", "doesn't work", "not opening",
        "slow", "lag", "stuck", "error", "broken", "paused", "refresh",
    ],
    "Customer Support": [
        "support", "customer care", "customer service", "help", "response",
        "complaint", "executive", "call", "chat", "contact", "resolve",
    ],
    "KYC & Onboarding": [
        "kyc", "verification", "onboard", "signup", "sign up", "account",
        "document", "pan", "aadhaar", "smooth", "easy", "quick",
    ],
    "Withdrawals & Payouts": [
        "withdraw", "withdrawal", "payout", "transfer", "money", "amount",
        "delay", "delayed", "days", "pending", "credited", "bank",
    ],
    "Funds & Portfolio": [
        "fund", "funds", "mutual fund", "mf", "portfolio", "folio",
        "external", "internal", "track", "tracking", "update", "nav",
        "sip", "invest", "investment", "stocks", "trading", "order",
    ],
    "UI & Experience": [
        "interface", "ui", "ux", "design", "layout", "feature", "features",
        "chart", "dashboard", "easy to use", "user friendly", "simple",
    ],
}

STEP_A_SYSTEM = (
    "You are a product analyst for a fintech app called Groww. "
    "Do NOT include any personally identifiable information "
    "(names, usernames, emails, IDs, etc.) in your output."
)

STEP_A_PROMPT = """\
Read the following Play Store reviews from the last 8–12 weeks.
Identify between 3 and 5 recurring themes (no more than 5).

For each theme provide:
  - "name": a short label (2-4 words)
  - "sentiment": positive | negative | mixed

Respond ONLY with valid JSON: {{ "themes": [...] }}

Reviews:
{reviews_text}
"""


def _get_client() -> OpenAI:
    api_key = os.getenv("XAI_API_KEY")
    if not api_key:
        raise RuntimeError("XAI_API_KEY not set in environment / .env file")
    return OpenAI(base_url=XAI_BASE_URL, api_key=api_key)


def _format_reviews_for_prompt(reviews: list[dict]) -> str:
    lines = []
    for i, r in enumerate(reviews, 1):
        stars = r.get("score", "?")
        title = r.get("title", "")
        content = r.get("content", "")
        text = f"[Title: {title}] {content}" if title else content
        lines.append(f"{i}. ({stars} stars) {text}")
    return "\n".join(lines)


def _chunk_reviews(reviews: list[dict], chunk_size: int = CHUNK_SIZE) -> list[list[dict]]:
    num_chunks = math.ceil(len(reviews) / chunk_size)
    return [reviews[i * chunk_size:(i + 1) * chunk_size] for i in range(num_chunks)]


def _call_grok(client: OpenAI, system: str, user_prompt: str) -> dict:
    response = client.chat.completions.create(
        model=XAI_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.3,
    )
    raw = response.choices[0].message.content
    return json.loads(raw)


def _merge_chunk_themes(all_chunk_themes: list[list[dict]]) -> list[dict]:
    """Merge themes from multiple chunks by grouping similar names."""
    theme_map: dict[str, dict] = {}
    for chunk_themes in all_chunk_themes:
        for t in chunk_themes:
            name_lower = t["name"].lower().strip()
            if name_lower in theme_map:
                existing = theme_map[name_lower]
                if t.get("sentiment") != existing["sentiment"]:
                    existing["sentiment"] = "mixed"
                existing["_chunk_count"] += 1
            else:
                theme_map[name_lower] = {
                    "name": t["name"],
                    "sentiment": t.get("sentiment", "mixed"),
                    "_chunk_count": 1,
                }
    sorted_themes = sorted(theme_map.values(), key=lambda x: x["_chunk_count"], reverse=True)
    return [{"name": t["name"], "sentiment": t["sentiment"]} for t in sorted_themes[:MAX_THEMES]]


def _generate_themes_fallback(reviews: list[dict]) -> list[dict]:
    """Generate 3-5 themes using keyword matching (no API). Same output shape as Grok."""
    theme_counts: dict[str, list[int]] = defaultdict(list)

    for i, r in enumerate(reviews):
        text = (r.get("title") or "") + " " + (r.get("content") or "")
        text_lower = text.lower()
        stars = r.get("score", 3)

        for theme_name, keywords in THEME_KEYWORDS.items():
            if any(kw in text_lower for kw in keywords):
                theme_counts[theme_name].append(stars)

    results = []
    for theme_name, star_list in sorted(theme_counts.items(), key=lambda x: -len(x[1]))[:MAX_THEMES]:
        if not star_list:
            continue
        avg = sum(star_list) / len(star_list)
        if avg >= 4:
            sentiment = "positive"
        elif avg <= 2:
            sentiment = "negative"
        else:
            sentiment = "mixed"
        results.append({"name": theme_name, "sentiment": sentiment})

    if not results:
        results = [
            {"name": "General Feedback", "sentiment": "mixed"},
            {"name": "App Experience", "sentiment": "mixed"},
            {"name": "Feature Requests", "sentiment": "mixed"},
        ]
    return results[:MAX_THEMES]


def generate_themes(reviews: list[dict]) -> list[dict]:
    """Phase 2A: Generate 3-5 themes from the review corpus using Grok."""
    client = _get_client()
    chunks = _chunk_reviews(reviews)

    print(f"  Step A: Generating themes from {len(reviews)} reviews ({len(chunks)} chunk(s))...")

    if len(chunks) == 1:
        reviews_text = _format_reviews_for_prompt(reviews)
        prompt = STEP_A_PROMPT.format(reviews_text=reviews_text)
        result = _call_grok(client, STEP_A_SYSTEM, prompt)
        themes = result.get("themes", [])[:MAX_THEMES]
    else:
        all_chunk_themes = []
        for i, chunk in enumerate(chunks, 1):
            print(f"    Processing chunk {i}/{len(chunks)} ({len(chunk)} reviews)...")
            reviews_text = _format_reviews_for_prompt(chunk)
            prompt = STEP_A_PROMPT.format(reviews_text=reviews_text)
            result = _call_grok(client, STEP_A_SYSTEM, prompt)
            chunk_themes = result.get("themes", [])
            all_chunk_themes.append(chunk_themes)

        print(f"  Merging themes from {len(chunks)} chunks...")
        themes = _merge_chunk_themes(all_chunk_themes)

    for t in themes:
        if t["sentiment"] not in ("positive", "negative", "mixed"):
            t["sentiment"] = "mixed"

    print(f"  Identified {len(themes)} themes (Grok).")
    return themes


def save_themes(themes: list[dict], directory: str = DATA_DIR) -> str:
    os.makedirs(directory, exist_ok=True)
    filepath = os.path.join(directory, "themes.json")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump({"themes": themes}, f, ensure_ascii=False, indent=2)
    return filepath


def load_reviews(directory: str = DATA_DIR) -> list[dict]:
    filepath = os.path.join(directory, "raw_reviews.json")
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def run_step_a() -> list[dict]:
    """Run Phase 2A: load reviews, generate themes, save to data/themes.json."""
    print("Phase 2A — Theme Generation")
    reviews = load_reviews()
    print(f"  Loaded {len(reviews)} reviews from data/raw_reviews.json")

    use_mock = os.getenv("USE_MOCK_LLM", "").strip().lower() in ("1", "true", "yes")
    if use_mock:
        print("  Using keyword-based fallback (USE_MOCK_LLM is set).")
        themes = _generate_themes_fallback(reviews)
        print(f"  Identified {len(themes)} themes:")
    else:
        try:
            themes = generate_themes(reviews)
        except Exception as e:
            err_msg = str(e).lower()
            if "permission" in err_msg or "403" in err_msg or "credits" in err_msg or "api key" in err_msg or "incorrect" in err_msg:
                print(f"  Grok API unavailable ({e}). Using keyword-based fallback.")
                themes = _generate_themes_fallback(reviews)
                print(f"  Identified {len(themes)} themes:")
            else:
                raise

    for t in themes:
        print(f"    - {t['name']} ({t['sentiment']})")

    path = save_themes(themes)
    print(f"  Themes saved to {path}")
    return themes
