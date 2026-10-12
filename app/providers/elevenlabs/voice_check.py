"""Voice preflight for the verify tool: which voices does this plan allow?

Free plans cannot use every voice in the library through the API ("Free users
cannot use library voices via the API", HTTP 402). The default voice shipped in
`.env.example` is one of those, so the tool probes the configured voice and, when
it is refused, tests a handful of well-suited alternatives and says which ones
work \u2014 instead of leaving a silent fallback to the synthetic voice.
"""

from __future__ import annotations

import asyncio

import httpx

API = "https://api.elevenlabs.io/v1"
PROBE_TEXT = "Hello."
#: Warm/clear voices that suit a tutor; probed in order when the configured one fails.
CANDIDATES = [
    ("Xb7hH8MSUJpSbSDYk0k2", "Alice \u2014 Clear, Engaging Educator"),
    ("EXAVITQu4vr4xnSDxMaL", "Sarah \u2014 Mature, Reassuring"),
    ("JBFqnCBsd6RMkjVDRZzb", "George \u2014 Warm Storyteller"),
    ("pNInz6obpgDQGcFmaJgB", "Adam \u2014 Dominant, Firm"),
    ("onwK4e9ZLuTAKqWW03F9", "Daniel \u2014 Steady Broadcaster"),
    ("cgSgspJ2msm6clMCkdW9", "Jessica \u2014 Playful, Bright"),
    ("bIHbv24MWmeRgasZH58o", "Will \u2014 Relaxed Optimist"),
]


async def voice_status(client: httpx.AsyncClient, key: str, voice_id: str, model: str) -> str:
    """'ok' · 'paid_plan_required' · 'missing_permissions' · status code as text."""
    response = await client.post(
        f"{API}/text-to-speech/{voice_id}",
        headers={"xi-api-key": key},
        params={"output_format": "pcm_24000"},
        json={"text": PROBE_TEXT, "model_id": model},
    )
    if response.status_code == 200:
        return "ok"
    try:
        detail = response.json().get("detail") or {}
        code = detail.get("code") if isinstance(detail, dict) else None
    except Exception:  # noqa: BLE001
        code = None
    return str(code or response.status_code)


async def preflight(key: str, model: str, configured: str) -> tuple[bool, list[tuple[str, str, str]]]:
    """(configured voice works?, [(voice_id, label, status), ...])."""
    async with httpx.AsyncClient(timeout=30) as client:
        status = await voice_status(client, key, configured, model)
        if status == "ok":
            return True, [(configured, "configured", "ok")]
        results: list[tuple[str, str, str]] = [(configured, "configured (ELEVENLABS_VOICE_ID)", status)]
        for voice_id, label in CANDIDATES:
            if voice_id == configured:
                continue
            results.append((voice_id, label, await voice_status(client, key, voice_id, model)))
            if results[-1][2] == "ok" and sum(1 for _, _, s in results if s == "ok") >= 3:
                break  # three working choices are enough to pick from
    return False, results


def format_preflight(configured_ok: bool, results: list[tuple[str, str, str]]) -> str:
    lines = []
    if configured_ok:
        lines.append("  voice check: configured voice works \u2713")
        return "\n".join(lines)
    lines.append("  voice check: the configured voice is NOT usable on this plan:")
    for voice_id, label, status in results:
        mark = "\u2713" if status == "ok" else "\u2717"
        lines.append(f"    {mark} {voice_id}  {label}  [{status}]")
    working = [v for v, _, s in results if s == "ok"]
    if working:
        lines.append(f"  \u2192 put a working id in .env:  ELEVENLABS_VOICE_ID={working[0]}")
    else:
        lines.append(
            "  \u2192 none of the probed voices work; the plan may need $5 of credits "
            "(library voices are paid-only through the API)."
        )
    return "\n".join(lines)


if __name__ == "__main__":  # pragma: no cover - manual helper
    import os
    import sys

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from dotenv import load_dotenv

    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
    from app.config import get_settings

    settings = get_settings()
    ok, res = asyncio.run(
        preflight(settings.elevenlabs_api_key, settings.elevenlabs_tts_model, settings.elevenlabs_voice_id)
    )
    print(format_preflight(ok, res))
