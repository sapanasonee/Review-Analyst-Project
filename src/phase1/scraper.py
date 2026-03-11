import json
import os
import re
from datetime import datetime, timedelta, timezone

from google_play_scraper import Sort, reviews
from langdetect import detect, LangDetectException


DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")

KEEP_FIELDS = ["score", "content", "thumbsUpCount", "at"]

EMOJI_PATTERN = re.compile(
    "["
    "\U0001F600-\U0001F64F"
    "\U0001F300-\U0001F5FF"
    "\U0001F680-\U0001F6FF"
    "\U0001F1E0-\U0001F1FF"
    "\U00002700-\U000027BF"
    "\U0001F900-\U0001F9FF"
    "\U0001FA00-\U0001FA6F"
    "\U0001FA70-\U0001FAFF"
    "\U00002600-\U000026FF"
    "\U0000FE00-\U0000FE0F"
    "\U0000200D"
    "\U00002B50"
    "\U0000231A-\U0000231B"
    "\U00002934-\U00002935"
    "\U000025AA-\U000025AB"
    "\U000025FB-\U000025FE"
    "\U00003030\U0000303D"
    "\U0000200B"
    "]"
)

MIN_WORD_COUNT = 5


DEVANAGARI_PATTERN = re.compile(r"[\u0900-\u097F]")

HINGLISH_WORDS = {
    "hai", "nahi", "nahin", "nhin", "karo", "karna", "krna", "krte",
    "kaise", "bahut", "bohot", "bhut", "accha", "acha",
    "chahiye", "bhi", "kuch", "zyada", "jyada", "jayada",
    "kerta", "kerte", "mein", "raha", "rahi", "rhe",
    "wala", "wale", "wali", "sabse", "thik", "aur",
    "lekin", "abhi", "hota", "hoti", "phle", "pehle",
    "baad", "isliye", "kyuki", "kyunki", "kyoki",
    "koi", "sab", "sirf", "bilkul",
    "dena", "lena", "milta", "milti", "bolte", "dekho", "dikhe",
    "paisa", "paise", "pese", "lagao", "lagta", "lgta",
    "jaata", "jaati", "rehte", "rehta", "chalta", "chalte",
    "sakta", "sakti", "krege", "kriye", "kijiye",
    "madhe", "frod", "sath", "tha", "gaya", "gayi", "gaye",
    "dekh", "mera", "meri", "mere", "apna", "apni",
    "nhi", "diya", "diye", "liye", "kiya", "kiye",
    "toh", "isko", "usko", "iski", "uski", "yeh", "yehi",
}

HINGLISH_THRESHOLD = 2


def _is_english(text: str) -> bool:
    if DEVANAGARI_PATTERN.search(text):
        return False
    words = set(text.lower().split())
    if len(words & HINGLISH_WORDS) >= HINGLISH_THRESHOLD:
        return False
    try:
        return detect(text) == "en"
    except LangDetectException:
        return False


def _is_valid_review(text: str) -> bool:
    if EMOJI_PATTERN.search(text):
        return False
    if len(text.split()) <= MIN_WORD_COUNT:
        return False
    if not _is_english(text):
        return False
    return True


def fetch_reviews(app_id: str, weeks: int = 12, count: int = 500) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(weeks=weeks)

    all_reviews: list[dict] = []
    token = None
    batch_size = min(count, 200)

    while len(all_reviews) < count:
        result, token = reviews(
            app_id,
            lang="en",
            country="in",
            sort=Sort.NEWEST,
            count=batch_size,
            continuation_token=token,
        )

        if not result:
            break

        for r in result:
            review_dt = r["at"]
            if hasattr(review_dt, "tzinfo") and review_dt.tzinfo is None:
                review_dt = review_dt.replace(tzinfo=timezone.utc)

            if review_dt < cutoff:
                token = None
                break

            content = r.get("content", "")
            if not _is_valid_review(content):
                continue

            cleaned = {k: r[k] for k in KEEP_FIELDS if k in r}
            cleaned["at"] = cleaned["at"].isoformat()

            title = r.get("title")
            if title:
                cleaned["title"] = title

            all_reviews.append(cleaned)

        if token is None:
            break

    return all_reviews


def save_reviews(reviews_list: list[dict], app_id: str, weeks: int,
                 directory: str = DATA_DIR) -> str:
    os.makedirs(directory, exist_ok=True)

    filepath = os.path.join(directory, "raw_reviews.json")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(reviews_list, f, ensure_ascii=False, indent=2)

    meta = {
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "review_count": len(reviews_list),
        "app_id": app_id,
        "weeks": weeks,
    }
    meta_path = os.path.join(directory, "scrape_metadata.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    return filepath


def run(app_id: str = "com.nextbillion.groww", weeks: int = 12, count: int = 500):
    print(f"Fetching up to {count} reviews from the last {weeks} weeks for {app_id}...")
    print(f"Filters: English only, no emojis, more than {MIN_WORD_COUNT} words")
    reviews_list = fetch_reviews(app_id, weeks=weeks, count=count)
    print(f"Collected {len(reviews_list)} reviews (after filtering).")

    path = save_reviews(reviews_list, app_id, weeks)
    print(f"Saved to {path}")
    return reviews_list
