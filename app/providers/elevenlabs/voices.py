"""ElevenLabs voice discovery — server-side only.

The demo screen asks *this service* which voices exist; it never holds the API
key (`xi-api-key` stays on the server, like every other vendor credential).
"""

from __future__ import annotations

import httpx

from app.config import Settings
from app.providers.base import ProviderAuthError

API = "https://api.elevenlabs.io/v1/voices"


async def list_voices(settings: Settings) -> list[dict[str, object]]:
    """Voice id + name + language labels, best-for-multilingual first."""
    if not settings.elevenlabs_api_key:
        raise ProviderAuthError("ELEVENLABS_API_KEY is not configured", provider="elevenlabs")
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(API, headers={"xi-api-key": settings.elevenlabs_api_key})
        response.raise_for_status()
        payload = response.json()

    voices: list[dict[str, object]] = []
    for item in payload.get("voices", []):
        labels = item.get("labels") or {}
        voices.append(
            {
                "voice_id": item.get("voice_id"),
                "name": item.get("name"),
                "gender": labels.get("gender"),
                "accent": labels.get("accent"),
                "description": item.get("description") or labels.get("description"),
                "category": item.get("category"),
            }
        )
    voices.sort(key=lambda v: (str(v.get("category") or "") != "premade", str(v.get("name") or "")))
    return voices
