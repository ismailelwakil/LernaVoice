#!/usr/bin/env python3
"""Verify the *real* voice path end to end.

Run this once the vendor keys are in `.env` (and `VOICE_ENABLE_MOCK_PROVIDERS` is not
set). It does not touch the mocks: it opens a genuine Gemini Live session, asks the
tutor to speak, and reports what came back — model, auth path, first audio latency,
bytes of PCM, and the transcript.

    python3 tools/verify_live_voice.py               # English, default topic
    python3 tools/verify_live_voice.py ar            # any of the 10 languages
    python3 tools/verify_live_voice.py --all         # every language, sequentially

Nothing here writes to the repository and no credential is printed.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def use_service_account() -> dict:
    """Validate GOOGLE_APPLICATION_CREDENTIALS and fill GOOGLE_CLOUD_PROJECT from it.

    Reports only non-secret facts (project id, client-email domain, key presence) so a
    credential can be diagnosed in a shared terminal without leaking it.
    """
    import json

    info: dict = {"path": os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", ""), "status": "not set"}
    if not info["path"]:
        return info
    path = Path(info["path"])
    if not path.exists():
        info["status"] = f"missing file: {path}"
        return info
    try:
        data = json.loads(path.read_text())
    except Exception as exc:  # noqa: BLE001 - diagnosis only
        info["status"] = f"not valid JSON: {type(exc).__name__}"
        return info

    kind = data.get("type")
    info["type"] = kind
    info["project_id"] = data.get("project_id")
    email = data.get("client_email") or ""
    info["client_email_domain"] = email.split("@")[-1] if "@" in email else ""
    info["has_private_key"] = bool(data.get("private_key"))
    if kind != "service_account" or not info["has_private_key"]:
        info["status"] = "not a service-account key (expected type=service_account with private_key)"
        return info
    info["status"] = "ok"
    # Convenience: a blank GOOGLE_CLOUD_PROJECT is filled from the key itself.
    if not os.environ.get("GOOGLE_CLOUD_PROJECT") and info.get("project_id"):
        os.environ["GOOGLE_CLOUD_PROJECT"] = str(info["project_id"])
        info["project_filled_from_key"] = True
    return info


def load_dotenv() -> None:
    """Minimal .env reader (no dependency on python-dotenv for a dev script)."""
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.split("  #")[0].strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), value)


async def probe(language: str, seconds: float = 12.0) -> dict:
    from app.config import Settings
    from app.curriculum import get_topic
    from app.providers.base import AudioChunk, SessionConfig
    from app.providers.gemini.live import GeminiLiveProvider
    from app.prompts.system import build_system_instruction
    from app.prompts.languages import language_name

    settings = Settings()
    topic = get_topic("binary-search") or get_topic("recursion")
    plan = topic.lesson_plan() if topic else []
    instruction = build_system_instruction(
        language=language,
        lesson_context={
            "topic": topic.title if topic else "the session topic",
            "lesson_plan": [f"{i + 1}. {s['title']} — {s.get('goal', '')}" for i, s in enumerate(plan)],
            "teaching_instruction": f"Teach in {language_name(language)}. Never read the plan aloud.",
        },
    )
    provider = GeminiLiveProvider(settings)
    config = SessionConfig(
        session_id="verify",
        language=language,
        system_instruction=instruction,
        voice_name=settings.gemini_voice_name,
        metadata={"topic_title": topic.title if topic else "", "sections": plan},
    )

    result: dict = {
        "language": language,
        "model": settings.active_gemini_live_model,
        "auth": settings.gemini_auth_mode,
        "voice": settings.gemini_voice_name,
        "affective_dialog": settings.gemini_affective_dialog,
        "audio_bytes": 0,
        "audio_ms": 0.0,
        "first_audio_ms": None,
        "transcript": "",
        "errors": [],
    }

    started = time.perf_counter()
    await provider.start_session(config)
    result["connect_ms"] = round((time.perf_counter() - started) * 1000)
    await provider.send_text(
        "Greet the student in one short sentence, name the topic, and teach the first step. "
        "Keep it brief."
    )

    deadline = time.perf_counter() + seconds
    stream = provider.receive_events()
    while time.perf_counter() < deadline:
        try:
            event = await asyncio.wait_for(
                stream.__anext__(), timeout=max(0.1, deadline - time.perf_counter())
            )
        except (asyncio.TimeoutError, StopAsyncIteration):
            break
        kind = str(getattr(event, "type", "")).lower()
        if getattr(event, "audio", None):
            if result["first_audio_ms"] is None:
                result["first_audio_ms"] = round((time.perf_counter() - started) * 1000)
            result["audio_bytes"] += len(event.audio)
        if getattr(event, "text", None) and "transcript" in kind:
            result["transcript"] += event.text
        if "error" in kind:
            result["errors"].append(str(getattr(event, "text", kind))[:200])

    result["audio_ms"] = round(result["audio_bytes"] / (settings.output_sample_rate * 2) * 1000, 1)
    await provider.close_session()
    return result


async def main() -> int:
    load_dotenv()
    cred = use_service_account()
    parser = argparse.ArgumentParser(description="Verify the live Gemini voice end to end")
    parser.add_argument("language", nargs="?", default="en")
    parser.add_argument("--all", action="store_true", help="probe every mandatory language")
    parser.add_argument("--seconds", type=float, default=12.0)
    args = parser.parse_args()

    languages = ["en", "ar", "fr", "sw", "am", "ha", "so", "yo", "ig", "zu"] if args.all else [args.language]

    from app.config import Settings

    settings = Settings()
    if cred["status"] != "not set":
        print(f"credential    : {cred['status']}"
              + (f" · type={cred.get('type')}" if cred.get("type") else "")
              + (f" · project={cred.get('project_id')}" if cred.get("project_id") else "")
              + (f" · domain=@{cred['client_email_domain']}" if cred.get("client_email_domain") else "")
              + ("  (GOOGLE_CLOUD_PROJECT filled from the key)" if cred.get("project_filled_from_key") else ""))
    print(f"provider mode : {settings.voice_provider_mode}   mock: {settings.voice_enable_mock_providers}")
    print(f"gemini auth   : {settings.gemini_auth_mode}   model: {settings.active_gemini_live_model}")
    if settings.voice_enable_mock_providers:
        print("\n! VOICE_ENABLE_MOCK_PROVIDERS is on — unset it to exercise the real vendor.")
    if settings.gemini_auth_mode == "none":
        if cred["status"] not in ("not set", "ok"):
            print(f"\nThe credential file is not usable: {cred['status']}")
            print(f"  path: {cred['path']}")
            print("  Fix the file (Vertex service-account JSON) or the path, then re-run.")
            return 2
        print("\nNo Gemini credential found. Put one of these in .env and re-run:")
        print("  Vertex:   GOOGLE_GENAI_USE_VERTEXAI=true, GOOGLE_CLOUD_PROJECT=…,")
        print("            GOOGLE_CLOUD_LOCATION=…, GOOGLE_APPLICATION_CREDENTIALS=/path/to/sa.json")
        print("  Dev API:  GOOGLE_GENAI_USE_VERTEXAI=false, GEMINI_API_KEY=AIza…")
        return 2

    failures = 0
    for language in languages:
        try:
            out = await probe(language, args.seconds)
        except Exception as exc:  # noqa: BLE001 — this script reports, it does not raise
            print(f"\n{language}: FAILED — {type(exc).__name__}: {str(exc)[:200]}")
            failures += 1
            continue
        status = "ok" if out["audio_bytes"] else "NO AUDIO"
        print(f"\n{language}: {status}")
        print(f"  connect {out['connect_ms']} ms · first audio {out['first_audio_ms']} ms · "
              f"{out['audio_ms']} ms of PCM ({out['audio_bytes']} bytes)")
        if out["transcript"]:
            print(f"  transcript: {out['transcript'][:200]}")
        if out["errors"]:
            print(f"  errors: {out['errors']}")
        if not out["audio_bytes"]:
            failures += 1

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
