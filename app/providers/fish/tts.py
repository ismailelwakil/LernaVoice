"""Fish Audio TTS — the backup voice (round 27).

Fish Audio (``api.fish.audio``) is a text-to-speech / voice-cloning service, *not*
a text model. The ``s2.1-pro-free`` model is free under Fair Use and auto-detects
the language of the input text (83 languages, Arabic included), so a single
endpoint speaks every language we teach with no per-language voice name.

It returns a WAV/PCM binary. We parse the header, downmix to mono and resample to
the pipeline's PCM16 rate so the bytes are interchangeable with the Azure, Gemini
Live and ElevenLabs paths — Fish slots in as a drop-in backup speaker.

Language set below is deliberately conservative: only languages Fish documents
(``en ar fr sw``). Hausa/Yoruba/Igbo/Somali/Amharic are *not* claimed until
verified, so the router never routes a mandatory language to an unproven voice.
"""

from __future__ import annotations

import array
import struct
from typing import AsyncIterator

from app.config import Settings, get_settings
from app.providers.base import (
    AudioChunk,
    ProviderAuthError,
    ProviderUnsupportedError,
    TextToSpeechProvider,
)
from app.providers.capabilities import PROVIDER_CAPABILITIES, Capability
from app.providers.ws_utils import classify_exception

#: Documented Fish languages among LERNA's ten (others unverified — see module doc).
FISH_TTS_LANGUAGES = {"en", "ar", "fr", "sw"}


class FishAudioTTSProvider(TextToSpeechProvider):
    provider_name = "fish"

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._cancelled = False
        self.last_transport = "rest"
        #: Per-session context, mirroring the Azure provider's interface.
        self.language: str | None = None
        self.dialect: str | None = None

    def set_language_context(self, language: str, dialect: str | None = None) -> None:
        self.language = language
        self.dialect = dialect

    async def cancel(self) -> None:
        self._cancelled = True

    async def synthesize_stream(
        self, text: str, language: str, *, voice: str | None = None
    ) -> AsyncIterator[AudioChunk]:
        capability = PROVIDER_CAPABILITIES.get("fish")
        if capability is None or not capability.supports(Capability.TTS, language):
            raise ProviderUnsupportedError(
                f"Fish TTS does not cover '{language}'", provider="fish"
            )
        key = getattr(self.settings, "fish_audio_api_key", None)
        if not key:
            raise ProviderAuthError("FISH_AUDIO_API_KEY is not configured", provider="fish")

        model = getattr(self.settings, "fish_audio_model", "s2.1-pro-free") or "s2.1-pro-free"
        body: dict[str, object] = {"text": text, "format": "wav"}
        if voice:
            body["reference_id"] = voice
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "model": model,
        }

        import httpx

        try:
            async with httpx.AsyncClient(timeout=self.settings.voice_provider_timeout * 3) as client:
                response = await client.post(
                    "https://api.fish.audio/v1/tts", headers=headers, json=body
                )
        except Exception as exc:  # noqa: BLE001
            raise classify_exception(exc, "fish") from exc

        if response.status_code >= 400:
            detail = response.text[:200]
            if response.status_code in (401, 403):
                raise ProviderAuthError(
                    f"Fish refused the key ({response.status_code}): {detail}", provider="fish"
                )
            raise classify_exception(
                RuntimeError(f"HTTP {response.status_code}: {detail}"), "fish"
            )

        pcm, src_rate = _wav_to_pcm(response.content)
        if self._cancelled or not pcm:
            return
        target = self.settings.output_sample_rate
        if src_rate and src_rate != target:
            pcm = _resample(pcm, src_rate, target)
        step = target // 5 * 2  # ~200 ms, like the other paths
        for offset in range(0, len(pcm), step):
            if self._cancelled:
                return
            yield AudioChunk(data=pcm[offset : offset + step], sample_rate=target)


def _wav_to_pcm(data: bytes) -> tuple[bytes, int]:
    """Return (mono 16-bit PCM, source sample rate) from a WAV/PCM payload."""
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        return data, 44100  # raw PCM: Fish's native rate is 44.1 kHz
    src_rate, channels, bits, pcm = 44100, 1, 16, b""
    i = 12
    while i + 8 <= len(data):
        cid = data[i : i + 4]
        size = struct.unpack("<I", data[i + 4 : i + 8])[0]
        chunk = data[i + 8 : i + 8 + size]
        if cid == b"fmt " and len(chunk) >= 16:
            channels = struct.unpack("<H", chunk[2:4])[0]
            src_rate = struct.unpack("<I", chunk[4:8])[0]
            bits = struct.unpack("<H", chunk[14:16])[0]
        elif cid == b"data":
            pcm = chunk
            break
        i += 8 + size + (size & 1)
    if bits == 16 and channels == 2 and pcm:
        stereo = array.array("h")
        stereo.frombytes(pcm[: len(pcm) // 2 * 2])
        mono = array.array("h", [(stereo[j] + stereo[j + 1]) // 2 for j in range(0, len(stereo) - 1, 2)])
        pcm = mono.tobytes()
    return pcm, src_rate


def _resample(pcm: bytes, src: int, dst: int) -> bytes:
    """Linear-interpolation resample of 16-bit mono PCM (src → dst Hz)."""
    if src == dst or not pcm:
        return pcm
    samples = array.array("h")
    samples.frombytes(pcm[: len(pcm) // 2 * 2])
    n = len(samples)
    if n == 0:
        return pcm
    out_len = max(1, int(n * dst / src))
    out = array.array("h", bytes(2 * out_len))
    ratio = src / dst
    for k in range(out_len):
        pos = k * ratio
        i0 = int(pos)
        frac = pos - i0
        if i0 + 1 < n:
            val = samples[i0] * (1.0 - frac) + samples[i0 + 1] * frac
        else:
            val = samples[min(i0, n - 1)]
        out[k] = int(max(-32768, min(32767, val)))
    return out.tobytes()
