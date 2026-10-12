"""LERNA Voice AI — Streamlit TESTING / DEMO client (§41).

This is NOT the production frontend. It is a developer harness that drives the
same public REST + WebSocket API a real client would use.

The main surface is a voice-mode screen (dark, animated orb, bottom control
bar). The sidebar carries session config; the **⌄ dev** chip inside the screen
opens the §41 diagnostics drawer (active pipeline, fallback reason, retry
count, latency, checkpoint, raw event stream).

Audio path:
    in  — optional microphone, captured in the browser, resampled to PCM16
          @ 16 kHz and streamed as binary WebSocket frames
    out — assistant PCM16 @ 24 kHz streamed from `assistant.audio.chunk`
          events is decoded and scheduled back-to-back, so it starts playing
          while it is still arriving (no wait-for-turn-complete buffering)

Run:
    VOICE_ENABLE_MOCK_PROVIDERS=true uvicorn app.main:app --port 3000
    streamlit run streamlit_app/app.py

Env:
    VOICE_SERVICE_URL      default http://localhost:3000
    VOICE_SERVICE_PORT     sibling-port host for sandbox previews (default 3000)
    VOICE_SERVICE_API_KEY  only if the service requires auth
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

ROOT = Path(__file__).resolve().parents[1]

SERVICE_URL = os.getenv("VOICE_SERVICE_URL", "http://localhost:3000").rstrip("/")
API_KEY = os.getenv("VOICE_SERVICE_API_KEY", "")
# When previewed on a sandbox host (8501-xxx.e2b.app) the service lives on a
# sibling port host (3000-xxx.e2b.app); the page derives that automatically.
SERVICE_PORT = os.getenv("VOICE_SERVICE_PORT", "3000")

LANGUAGES = {
    "en": "English",
    "ar": "العربية · Arabic",
    "fr": "Français",
    "sw": "Kiswahili",
    "am": "አማርኛ · Amharic",
    "ha": "Hausa",
    "so": "Soomaali",
    "yo": "Yorùbá",
    "ig": "Igbo",
    "zu": "isiZulu",
}

st.set_page_config(page_title="LERNA Voice", layout="wide", initial_sidebar_state="collapsed")

st.markdown(
    """
    <style>
      .stApp{background:#000}
      header[data-testid="stHeader"]{background:transparent}
      #MainMenu,footer{visibility:hidden}
      .block-container{padding:0 !important;max-width:100% !important}
      section[data-testid="stSidebar"]{background:#0b0d12;border-right:1px solid #1d2230}
      section[data-testid="stSidebar"] *{color:#d9e1ec}
      iframe{border:0}
    </style>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown("### Session")
    student_id = st.text_input("Student ID", "demo-student-001")
    course_id = st.text_input("Course ID", "algorithms-101")
    lesson_id = st.text_input("Lesson ID", "lesson-binary-search")
    topic = st.text_input("Topic", "Binary Search")
    language = st.selectbox(
        "Language", list(LANGUAGES), index=1, format_func=lambda c: f"{LANGUAGES[c]} ({c})"
    )
    returning = st.checkbox("Returning student (recap)", value=False)
    st.caption(
        "Settings apply the next time you tap **Connect**. Diagnostics live "
        "inside the screen — tap the **⌄ dev** chip at the top right."
    )
    st.markdown("---")
    st.caption("**Audio** — press the blue **●** to connect (that also unlocks sound), then")
    st.caption("• **🎤** start talking · speak, pause, the tutor answers")
    st.caption("• **🎙** interrupt it mid-sentence (barge-in)")
    st.caption("• **+** send 0.5 s of synthetic audio if you have no mic")
    st.caption("• type a question and press Enter")
    st.caption("• **🔊** chip plays a test tone if you hear nothing")
    st.markdown("---")
    st.caption(f"Service: `{SERVICE_URL}` (auto-detected on sandbox hosts)")
    st.caption("Demo harness only — the production frontend is out of scope.")

config = {
    "serviceUrl": SERVICE_URL,
    "servicePort": SERVICE_PORT,
    "apiKey": API_KEY,
    "student_id": student_id,
    "course_id": course_id,
    "lesson_id": lesson_id,
    "topic": topic,
    "language": language,
    "resume_latest": returning,
    "languages": LANGUAGES,
}

# The screen itself lives in app/static/voice_mode.html so the service can serve
# the identical page on its own port. We only inject the config here; when this
# harness runs on a sandbox host the page derives the sibling-port service host.
TEMPLATE = (ROOT / "app" / "static" / "voice_mode.html").read_text(encoding="utf-8")
CONFIG = {
    "serviceUrl": SERVICE_URL,
    "servicePort": SERVICE_PORT,
    "apiKey": API_KEY,
    "student_id": student_id,
    "course_id": course_id,
    "lesson_id": lesson_id,
    "topic": topic,
    "language": language,
    "resume_latest": returning,
    "languages": LANGUAGES,
}
PAGE = re.sub(
    r'(<script id="cfg" type="application/json">).*?(</script>)',
    lambda m: m.group(1) + json.dumps(CONFIG, ensure_ascii=False) + m.group(2),
    TEMPLATE,
    count=1,
    flags=re.S,
)

# st.components.v1.html is deprecated in favour of st.iframe (Streamlit 1.65+);
# both embed the page via srcdoc, so keep the fallback for older installs.
if hasattr(st, "iframe"):
    st.iframe(PAGE, height=760)
else:
    components.html(PAGE, height=760, scrolling=False)
