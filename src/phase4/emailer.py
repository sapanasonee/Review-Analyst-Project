"""
Phase 4 — Email Delivery (Draft Email).

Creates a Gmail draft containing the Weekly Pulse HTML so the user can review and send.
Uses OAuth 2.0 with scope gmail.compose only (draft, no send).
"""

import base64
import os
import re
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"
OUTPUT_DIR = ROOT / "output"
DATA_DIR = ROOT / "data"

GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.compose"


def _get_credentials():
    """OAuth 2.0 credentials using credentials.json and cached token.json."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds_path = CONFIG_DIR / "credentials.json"
    token_path = CONFIG_DIR / "token.json"

    if not creds_path.exists():
        raise FileNotFoundError(
            f"Gmail OAuth credentials not found at {creds_path}. "
            "Download from Google Cloud Console (OAuth 2.0 Client ID, Desktop app) and save as config/credentials.json"
        )

    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), [GMAIL_SCOPE])

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), [GMAIL_SCOPE])
            creds = flow.run_local_server(port=0)
        with open(token_path, "w") as f:
            f.write(creds.to_json())

    return creds


def create_draft(subject: str, html_body: str, to: str) -> str:
    """
    Create a Gmail draft with the given subject, HTML body, and To address.
    Returns the draft ID (for linking to Gmail).
    """
    from googleapiclient.discovery import build

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["To"] = to

    # Plain text fallback (first 500 chars of stripped HTML)
    plain = re.sub(r"<[^>]+>", "", html_body).strip()[:500]
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii").rstrip("=")

    creds = _get_credentials()
    service = build("gmail", "v1", credentials=creds)
    draft = (
        service.users()
        .drafts()
        .create(userId="me", body={"message": {"raw": raw}})
        .execute()
    )
    return draft["id"]


def send_email(subject: str, html_body: str, to: str) -> str:
    """
    Send an email (not a draft) with the given subject, HTML body, and To address.
    Returns the message ID. Uses the same gmail.compose scope.
    """
    from googleapiclient.discovery import build

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["To"] = to

    plain = re.sub(r"<[^>]+>", "", html_body).strip()[:500]
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii").rstrip("=")

    creds = _get_credentials()
    service = build("gmail", "v1", credentials=creds)
    result = (
        service.users()
        .messages()
        .send(userId="me", body={"raw": raw})
        .execute()
    )
    return result["id"]


def _load_week_label_from_html(html_path: Path) -> str:
    """Extract 'Week of X – Y' from the saved HTML report."""
    text = html_path.read_text(encoding="utf-8")
    m = re.search(r"Week of ([^<]+)", text)
    if m:
        return m.group(1).strip()
    return ""


def run() -> str:
    """
    Load weekly_pulse.html, create a Gmail draft, and return the draft ID.
    Subject and To come from env (GMAIL_RECIPIENT) and week label from the report.
    """
    html_path = OUTPUT_DIR / "weekly_pulse.html"
    if not html_path.exists():
        raise FileNotFoundError(
            f"Run Phase 3 first: {html_path} not found. Generate the report with report.run()."
        )

    html_body = html_path.read_text(encoding="utf-8")
    week_label = _load_week_label_from_html(html_path)
    if not week_label:
        meta_path = DATA_DIR / "scrape_metadata.json"
        if meta_path.exists():
            import json
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            weeks = meta.get("weeks", 12)
            from datetime import datetime, timedelta
            end = datetime.utcnow()
            start = end - timedelta(weeks=weeks)
            week_label = f"{start.strftime('%b %d')} – {end.strftime('%b %d, %Y')}"
        else:
            week_label = "this week"

    to = os.getenv("GMAIL_RECIPIENT", "").strip()
    if not to:
        raise ValueError("GMAIL_RECIPIENT not set in .env. Set it to the email address for the draft.")

    subject = f"Groww Weekly Pulse — Week of {week_label}"
    print("Phase 4 — Email Delivery (Draft)")
    print(f"  Creating draft: To={to}, Subject={subject[:50]}...")
    draft_id = create_draft(subject, html_body, to)
    url = f"https://mail.google.com/mail/u/0/#drafts/{draft_id}"
    print(f"  Draft created: {url}")
    return draft_id
