"""
Phase 5 — Streamlit Dashboard.

Web UI to run phases 1–4 and inspect results (themes, pulse, raw reviews, log).
Run with:  streamlit run app.py
"""

from pathlib import Path
import json

import streamlit as st

from src.phase1 import scraper
from src.phase2 import analyzer
from src.phase3 import report
from src.phase4 import emailer

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"


def _init_state():
    st.session_state.setdefault("phase1_done", False)
    st.session_state.setdefault("phase2_done", False)
    st.session_state.setdefault("phase3_done", False)
    st.session_state.setdefault("phase4_done", False)
    st.session_state.setdefault("log_lines", [])


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


def _load_pulse_md():
    path = OUTPUT_DIR / "weekly_pulse.md"
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def run_phase1():
    with st.spinner("Fetching reviews (Phase 1)..."):
        reviews = scraper.run()
    st.session_state.phase1_done = True
    _log(f"Phase 1: fetched {len(reviews)} reviews.")


def run_phase2():
    with st.spinner("Analyzing themes (Phase 2A)..."):
        themes = analyzer.run_step_a()
    st.session_state.phase2_done = True
    _log(f"Phase 2A: identified {len(themes)} themes.")


def run_phase3():
    with st.spinner("Generating weekly pulse (Phase 3)..."):
        analysis = report.run()
    st.session_state.phase3_done = True
    _log(
        f"Phase 3: report generated with {len(analysis.get('themes', []))} themes, "
        f"{len(analysis.get('quotes', []))} quotes, {len(analysis.get('actions', []))} actions."
    )


def run_phase4():
    with st.spinner("Creating Gmail draft (Phase 4)..."):
        draft_id = emailer.run()
    st.session_state.phase4_done = True
    _log(f"Phase 4: Gmail draft created (id={draft_id}).")


def main():
    st.set_page_config(
        page_title="Groww Review Analyst",
        page_icon="📊",
        layout="wide",
    )
    _init_state()

    st.sidebar.title("Pipeline controls")
    if st.sidebar.button("1. Fetch reviews (Phase 1)"):
        run_phase1()
    if st.sidebar.button("2. Analyze themes (Phase 2A)", disabled=not st.session_state.phase1_done):
        run_phase2()
    if st.sidebar.button("3. Generate weekly pulse (Phase 3)", disabled=not st.session_state.phase2_done):
        run_phase3()
    if st.sidebar.button("4. Create email draft (Phase 4)", disabled=not st.session_state.phase3_done):
        run_phase4()

    st.sidebar.markdown("---")
    st.sidebar.markdown("**Status**")
    st.sidebar.write(
        f"Phase 1: {'✅' if st.session_state.phase1_done else '⏳'}  \n"
        f"Phase 2A: {'✅' if st.session_state.phase2_done else '⏳'}  \n"
        f"Phase 3: {'✅' if st.session_state.phase3_done else '⏳'}  \n"
        f"Phase 4: {'✅' if st.session_state.phase4_done else '⏳'}"
    )

    st.title("Groww Review Analyst — Weekly Pulse")

    tab_pulse, tab_reviews, tab_log = st.tabs(["Weekly Pulse", "Raw Reviews", "Pipeline Log"])

    with tab_pulse:
        md = _load_pulse_md()
        if not md:
            st.info("Run Phase 3 to generate the weekly pulse.")
        else:
            st.markdown(md)

    with tab_reviews:
        reviews = _load_reviews()
        if not reviews:
            st.info("No reviews found. Run Phase 1 first.")
        else:
            st.caption(f"{len(reviews)} reviews loaded (filtered, English-only).")
            st.dataframe(reviews, use_container_width=True)

    with tab_log:
        if not st.session_state.log_lines:
            st.info("No pipeline runs yet.")
        else:
            st.code("\n".join(st.session_state.log_lines))


if __name__ == "__main__":
    main()
