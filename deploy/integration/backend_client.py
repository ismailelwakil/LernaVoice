"""Minimal LERNA-backend client for the Voice AI service.

Copy this into your backend. It does the only two server-side calls you need:
create a session, then mint a short-lived token for the browser. The service key
never leaves your server.

Env:
    VOICE_SERVICE_URL        e.g. https://voice.your-domain   (no trailing slash)
    VOICE_SERVICE_API_KEY    the shared secret (X-Voice-Service-Key)
"""

from __future__ import annotations

import os

import httpx

BASE = os.environ["VOICE_SERVICE_URL"].rstrip("/")
KEY = os.environ["VOICE_SERVICE_API_KEY"]
HEADERS = {"X-Voice-Service-Key": KEY}


def start_lesson(
    student_id: str,
    *,
    language: str = "ar",
    topic_id: str | None = None,      # preferred: a catalogue id from GET /curriculum/courses
    topic: str | None = None,         # or free text the service will resolve
    level: str | None = None,         # beginner | intermediate | advanced (optional)
    document_ids: list[str] | None = None,  # ids from POST /voice/material
    resume_latest: bool = False,      # recap instead of restart
) -> dict:
    """Create a session + token and return what the browser needs to connect."""
    body = {
        "student_id": student_id,
        "language": language,
        "topic_id": topic_id,
        "topic": topic,
        "level": level,
        "document_ids": document_ids,
        "resume_latest": resume_latest,
    }
    body = {k: v for k, v in body.items() if v is not None}

    with httpx.Client(timeout=30) as client:
        created = client.post(f"{BASE}/voice/session", headers=HEADERS, json=body)
        created.raise_for_status()
        session = created.json()                       # 201
        session_id = session["session_id"]

        tok = client.post(f"{BASE}/voice/session/{session_id}/token", headers=HEADERS)
        tok.raise_for_status()
        token = tok.json()["token"]                    # "vst_...", 15-min TTL

    return {
        "session_id": session_id,
        # The browser opens this directly (binary PCM16 16 kHz up, JSON events down).
        "ws_url": f"{session['websocket_url']}?token={token}",
        "language": session.get("language"),
        "current_topic": session.get("current_topic"),
    }


def latest_session(student_id: str) -> dict | None:
    """For continuation: the student's most recent session, if any."""
    with httpx.Client(timeout=15) as client:
        r = client.get(f"{BASE}/voice/students/{student_id}/latest", headers=HEADERS)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()


if __name__ == "__main__":
    import json

    print(json.dumps(start_lesson("student-123", language="ar", topic="البحث الثنائي"),
                     ensure_ascii=False, indent=2))
