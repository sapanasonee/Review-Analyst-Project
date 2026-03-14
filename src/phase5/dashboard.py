"""
Phase 5 — Streamlit Dashboard.

Web UI to run the pipeline, preview the weekly pulse, copy/share it,
and send it via email to any address.
Run with:  streamlit run app.py
"""

from pathlib import Path
import json
import re
import streamlit as st
import streamlit.components.v1 as components

from src.phase1 import scraper
from src.phase2 import analyzer
from src.phase3 import report
from src.phase4 import emailer

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"

ACCENT = "#4ade80"
MUTED = "#6b7280"


def _inject_global_css():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    .block-container { max-width: 960px; padding-top: 2rem; }

    /* sidebar */
    section[data-testid="stSidebar"] { background-color: #0f172a; }
    section[data-testid="stSidebar"] .stMarkdown p,
    section[data-testid="stSidebar"] .stMarkdown li { color: #cbd5e1; }

    /* phase step cards */
    .phase-step {
        display: flex; align-items: center; gap: 10px;
        padding: 10px 14px; margin-bottom: 6px;
        border-radius: 10px; border: 1px solid #1e293b;
        background: #111828; font-size: 14px; color: #e2e8f0;
    }
    .phase-step .num {
        width: 26px; height: 26px; border-radius: 50%;
        display: inline-flex; align-items: center; justify-content: center;
        font-weight: 700; font-size: 12px;
    }
    .phase-done .num { background: #166534; color: #4ade80; }
    .phase-pending .num { background: #1e293b; color: #475569; }
    .phase-done { border-color: #166534; }

    /* hero header */
    .hero {
        background: linear-gradient(135deg, #020617 0%, #0f172a 50%, #020617 100%);
        border: 1px solid #1e293b; border-radius: 16px;
        padding: 28px 32px; margin-bottom: 20px; text-align: center;
    }
    .hero h1 { margin: 0 0 6px; font-size: 28px; color: #f8fafc; font-weight: 700; letter-spacing: .02em; }
    .hero p { margin: 0; font-size: 14px; color: #64748b; }

    /* share card */
    .share-card {
        background: #111828; border: 1px solid #1e293b; border-radius: 14px;
        padding: 22px 24px; margin-bottom: 16px;
    }
    .share-card h3 {
        margin: 0 0 4px; font-size: 16px; color: #e2e8f0; font-weight: 600;
    }
    .share-card p { margin: 0; font-size: 13px; color: #64748b; }

    /* email sent banner */
    .email-success {
        background: #052e16; border: 1px solid #166534; border-radius: 10px;
        padding: 14px 18px; color: #4ade80; font-size: 14px; font-weight: 500;
        margin-top: 10px;
    }
    .email-error {
        background: #450a0a; border: 1px solid #991b1b; border-radius: 10px;
        padding: 14px 18px; color: #f87171; font-size: 14px; font-weight: 500;
        margin-top: 10px;
    }

    /* stat pills */
    .stat-row { display: flex; gap: 10px; margin: 12px 0 0; justify-content: center; }
    .stat-pill {
        padding: 5px 14px; border-radius: 999px;
        background: #1e293b; border: 1px solid #334155;
        font-size: 12px; color: #94a3b8; font-weight: 500;
    }

    /* theme grid */
    .theme-grid { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 20px; }
    .theme-tile {
        flex: 1 1 calc(33.3% - 10px); min-width: 170px;
        background: #111828; border: 1px solid #1e293b; border-radius: 12px;
        padding: 16px 18px; position: relative; overflow: hidden;
    }
    .theme-tile.featured { border-color: #166534; }
    .theme-tile.featured::before {
        content: 'IN PULSE'; position: absolute; top: 8px; right: -22px;
        transform: rotate(45deg); background: #166534; color: #4ade80;
        font-size: 9px; font-weight: 700; letter-spacing: .06em;
        padding: 2px 28px;
    }
    .theme-tile .t-name { font-size: 15px; font-weight: 600; color: #f1f5f9; margin: 0 0 6px; }
    .theme-tile .t-badge {
        display: inline-block; padding: 3px 9px; border-radius: 999px;
        font-size: 11px; font-weight: 600; text-transform: capitalize;
    }
    .badge-positive { background: #052e16; border: 1px solid #166534; color: #4ade80; }
    .badge-negative { background: #450a0a; border: 1px solid #991b1b; color: #f87171; }
    .badge-mixed    { background: #1e293b; border: 1px solid #374151; color: #fbbf24; }

    div[data-testid="stTabs"] button[data-baseweb="tab"] {
        font-weight: 600; font-size: 14px;
    }
    </style>
    """, unsafe_allow_html=True)


def _init_state():
    defaults = {
        "phase1_done": (DATA_DIR / "raw_reviews.json").exists(),
        "phase2_done": (DATA_DIR / "themes.json").exists(),
        "phase3_done": (OUTPUT_DIR / "weekly_pulse.html").exists(),
        "phase4_done": False,
        "log_lines": [],
        "email_status": None,
    }
    for k, v in defaults.items():
        st.session_state.setdefault(k, v)


def _log(message: str):
    st.session_state.log_lines.append(message)


def _load_reviews():
    path = DATA_DIR / "raw_reviews.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def _load_themes():
    path = DATA_DIR / "themes.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8")).get("themes", [])


def _load_scrape_meta() -> dict:
    path = DATA_DIR / "scrape_metadata.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _load_pulse_md():
    path = OUTPUT_DIR / "weekly_pulse.md"
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _load_pulse_html():
    path = OUTPUT_DIR / "weekly_pulse.html"
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _get_week_label():
    html = _load_pulse_html()
    if html:
        m = re.search(r"Week of ([^<]+)", html)
        if m:
            return m.group(1).strip()
    return "this week"


def _get_pulse_theme_names() -> set[str]:
    """Extract theme names that were featured in the generated pulse HTML."""
    html = _load_pulse_html()
    if not html:
        return set()
    return {m.strip() for m in re.findall(r'font-weight:600[^>]*>([^<]+)</p>', html)}


# ── Sidebar ─────────────────────────────────────────────────────

def _render_sidebar():
    with st.sidebar:
        st.markdown("### Pipeline Controls")
        st.caption("Run each phase sequentially to generate the weekly pulse.")
        st.markdown("---")

        if st.button("1  Fetch Reviews", use_container_width=True):
            with st.spinner("Scraping Play Store..."):
                reviews = scraper.run()
            st.session_state.phase1_done = True
            _log(f"Phase 1: fetched {len(reviews)} reviews.")
            st.rerun()

        if st.button("2  Analyze Themes", use_container_width=True,
                      disabled=not st.session_state.phase1_done):
            with st.spinner("Identifying themes..."):
                themes = analyzer.run_step_a()
            st.session_state.phase2_done = True
            _log(f"Phase 2A: identified {len(themes)} themes.")
            st.rerun()

        if st.button("3  Generate Pulse", use_container_width=True,
                      disabled=not st.session_state.phase2_done):
            with st.spinner("Generating weekly pulse..."):
                analysis = report.run()
            st.session_state.phase3_done = True
            _log(
                f"Phase 3: report with {len(analysis.get('themes', []))} themes, "
                f"{len(analysis.get('quotes', []))} quotes, "
                f"{len(analysis.get('actions', []))} actions."
            )
            st.rerun()

        st.markdown("---")
        st.markdown("### Status")
        phases = [
            ("Fetch Reviews", st.session_state.phase1_done),
            ("Analyze Themes", st.session_state.phase2_done),
            ("Generate Pulse", st.session_state.phase3_done),
        ]
        for label, done in phases:
            icon = "✅" if done else "⏳"
            st.markdown(f"{icon}&ensp;{label}")


# ── Tabs ────────────────────────────────────────────────────────

def _tab_pulse():
    """Weekly Pulse preview + share/send."""
    html = _load_pulse_html()
    md = _load_pulse_md()

    if not html:
        st.info("Run the pipeline (sidebar) to generate the weekly pulse first.")
        return

    week_label = _get_week_label()

    # ── Hero header
    reviews = _load_reviews()
    themes = _load_themes()
    meta = _load_scrape_meta()
    weeks = meta.get("weeks", "–")
    st.markdown(f"""
    <div class="hero">
        <h1>Groww Weekly Pulse</h1>
        <p>Week of {week_label} &nbsp;·&nbsp; {weeks} weeks analysed</p>
        <div class="stat-row">
            <span class="stat-pill">{len(reviews)} reviews</span>
            <span class="stat-pill">{len(themes)} themes</span>
            <span class="stat-pill">{weeks} weeks</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── All 5 themes
    if themes:
        pulse_names = _get_pulse_theme_names()
        st.markdown("#### Identified Themes")
        st.caption("All themes extracted from reviews. The ones marked **IN PULSE** were selected as the top 3 for this week's report.")
        tiles_html = '<div class="theme-grid">'
        for t in themes:
            name = t.get("name", "")
            sentiment = t.get("sentiment", "mixed")
            featured = "featured" if name in pulse_names else ""
            badge_cls = f"badge-{sentiment}" if sentiment in ("positive", "negative", "mixed") else "badge-mixed"
            tiles_html += (
                f'<div class="theme-tile {featured}">'
                f'<p class="t-name">{name}</p>'
                f'<span class="t-badge {badge_cls}">{sentiment}</span>'
                f'</div>'
            )
        tiles_html += '</div>'
        st.markdown(tiles_html, unsafe_allow_html=True)

    # ── HTML Preview
    st.markdown("#### Pulse Preview")
    components.html(html, height=680, scrolling=True)

    st.markdown("---")

    # ── Share & Send section
    col_copy, col_send = st.columns(2, gap="large")

    with col_copy:
        st.markdown("""
        <div class="share-card">
            <h3>📋 Copy & Share</h3>
            <p>Copy the pulse content for Slack, email clients, or any channel.</p>
        </div>
        """, unsafe_allow_html=True)

        copy_format = st.radio(
            "Format",
            ["Markdown (Slack, Notion)", "HTML (Email clients)"],
            horizontal=True,
            label_visibility="collapsed",
        )

        if copy_format.startswith("Markdown"):
            st.code(md, language="markdown")
            st.caption("Click the copy icon ↗ on the code block above to copy.")
        else:
            st.code(html, language="html")
            st.caption("Click the copy icon ↗ on the code block above to copy.")

        st.download_button(
            "Download HTML file",
            data=html,
            file_name="weekly_pulse.html",
            mime="text/html",
            use_container_width=True,
        )

    with col_send:
        st.markdown("""
        <div class="share-card">
            <h3>📧 Send via Email</h3>
            <p>Send the weekly pulse directly to any email address.</p>
        </div>
        """, unsafe_allow_html=True)

        recipient = st.text_input(
            "Recipient email",
            placeholder="team-lead@company.com",
            label_visibility="collapsed",
        )

        send_mode = st.radio(
            "Mode",
            ["Send now", "Create draft"],
            horizontal=True,
            help="'Send now' delivers immediately. 'Create draft' saves it in your Gmail drafts.",
        )

        send_clicked = st.button(
            "Send Email" if send_mode == "Send now" else "Create Draft",
            use_container_width=True,
            type="primary",
            disabled=not recipient,
        )

        if send_clicked and recipient:
            subject = f"Groww Weekly Pulse — Week of {week_label}"
            try:
                with st.spinner("Sending..." if send_mode == "Send now" else "Creating draft..."):
                    if send_mode == "Send now":
                        msg_id = emailer.send_email(subject, html, recipient)
                        st.session_state.email_status = ("success", f"Email sent to {recipient} (id: {msg_id})")
                    else:
                        draft_id = emailer.create_draft(subject, html, recipient)
                        url = f"https://mail.google.com/mail/u/0/#drafts/{draft_id}"
                        st.session_state.email_status = ("success", f"Draft created for {recipient} — [Open in Gmail]({url})")
                _log(f"Phase 4: {'Sent' if send_mode == 'Send now' else 'Draft'} to {recipient}")
                st.rerun()
            except Exception as e:
                st.session_state.email_status = ("error", str(e))
                st.rerun()

        if st.session_state.get("email_status"):
            status_type, status_msg = st.session_state.email_status
            if status_type == "success":
                st.markdown(f'<div class="email-success">✓ {status_msg}</div>', unsafe_allow_html=True)
            else:
                st.markdown(f'<div class="email-error">✗ {status_msg}</div>', unsafe_allow_html=True)


def _tab_reviews():
    """Raw reviews explorer."""
    reviews = _load_reviews()
    if not reviews:
        st.info("No reviews found. Run Phase 1 from the sidebar first.")
        return

    st.caption(f"{len(reviews)} reviews loaded (filtered, English-only)")

    col_filter, col_sort = st.columns(2)
    with col_filter:
        star_filter = st.multiselect("Filter by stars", [1, 2, 3, 4, 5], default=[1, 2, 3, 4, 5])
    with col_sort:
        sort_by = st.selectbox("Sort by", ["Most recent", "Lowest rating", "Highest rating"])

    filtered = [r for r in reviews if r.get("score", 3) in star_filter]
    if sort_by == "Lowest rating":
        filtered.sort(key=lambda r: r.get("score", 3))
    elif sort_by == "Highest rating":
        filtered.sort(key=lambda r: r.get("score", 3), reverse=True)

    st.caption(f"Showing {len(filtered)} of {len(reviews)}")
    st.dataframe(
        filtered,
        use_container_width=True,
        column_config={
            "score": st.column_config.NumberColumn("Stars", format="%d ⭐"),
            "content": st.column_config.TextColumn("Review", width="large"),
        },
    )


def _tab_log():
    """Pipeline execution log."""
    if not st.session_state.log_lines:
        st.info("No pipeline runs yet. Use the sidebar to run each phase.")
        return

    for line in reversed(st.session_state.log_lines):
        st.markdown(f"- {line}")


# ── Main ────────────────────────────────────────────────────────

def main():
    st.set_page_config(
        page_title="Groww Review Analyst",
        page_icon="📊",
        layout="wide",
    )
    _inject_global_css()
    _init_state()
    _render_sidebar()

    tab_pulse, tab_reviews, tab_log = st.tabs(
        ["Weekly Pulse", "Raw Reviews", "Pipeline Log"]
    )

    with tab_pulse:
        _tab_pulse()
    with tab_reviews:
        _tab_reviews()
    with tab_log:
        _tab_log()


if __name__ == "__main__":
    main()
