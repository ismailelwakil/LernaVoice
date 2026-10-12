#!/usr/bin/env python3
"""Does the demo voice actually work? Run this the moment a key is in `.env`.

    python3 tools/verify_elevenlabs_voice.py                 # English sample
    python3 tools/verify_elevenlabs_voice.py ar              # Egyptian Arabic
    python3 tools/verify_elevenlabs_voice.py --all           # every covered language
    python3 tools/verify_elevenlabs_voice.py --list          # voices on the account

It prints what will be spoken, the account/voice/model, connect and first-audio
latency, the PCM byte count, and writes a playable `.wav` next to the script so
the audio can be listened to outside the browser (`out/voice-sample-<lang>.wav`).

Exit codes: 0 ok · 2 nothing configured / vendor refused.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import struct
import sys
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from app.config import get_settings  # noqa: E402
from app.prompts.interaction import speakable  # noqa: E402
from app.providers.base import ProviderError  # noqa: E402
from app.providers.capabilities import PROVIDER_CAPABILITIES, Capability  # noqa: E402

SAMPLE = {
    "en": "Hello, let's begin. Today we are working on Binary Search. First off. "
          "The idea of halving. Compare with the middle and discard the half that "
          "cannot hold the target. Jump in whenever you want.",
    "ar": "\u0623\u0647\u0644\u0627\u064b\u060c \u0646\u0628\u062f\u0623. \u0627\u0644\u0646\u0647\u0627\u0631\u062f\u0629 \u0647\u0646\u0634\u062a\u063a\u0644 \u0639\u0644\u0649 \u0627\u0644\u0628\u062d\u062b \u0627\u0644\u062b\u0646\u0627\u0626\u064a. "
          "\u0623\u0648\u0644 \u062d\u0627\u062c\u0629: \u0641\u0643\u0631\u0629 \u0627\u0644\u0646\u0635\u0641. \u0642\u0627\u0631\u0646 \u0628\u0627\u0644\u0646\u0635 \u0648\u0627\u0631\u0645\u064a \u0627\u0644\u0646\u0635 \u0627\u0644\u0644\u064a \u0645\u0634 \u0645\u0645\u0643\u0646 \u064a\u0643\u0648\u0646 \u0641\u064a\u0647 \u0627\u0644\u0647\u062f\u0641. "
          "\u0627\u062a\u0643\u0644\u0645 \u0648\u0642\u062a \u0645\u0627 \u062a\u062d\u0628.",
    "fr": "Bonjour, commen\u00e7ons. Aujourd'hui nous travaillons sur la recherche binaire.",
    "sw": "Habari, tuanze. Leo tunafanya kazi kwenye utafutaji wa nusu.",
    "am": "\u1230\u120b\u121d\u1362 \u12a5\u1295\u12f0\u1275 \u12a5\u1295\u1300\u1228\u1305\u1362",
    "ha": "Sannu, bari mu fara. Yau muna aiki kan bincike na rabi.",
    "so": "Salaan, aan bilaabno. Maanta waxaan ka shaqaynaynaa raadinta badh.",
    "yo": "B\u00e1\u00e1 ni, \u1eb9 j\u1eb9 k\u00e1 b\u1eb9r\u1eb9\u0300. L\u00f3n\u00ec\u00ed a \u1e63i\u1e63\u1eb9\u0301 l\u00f3r\u00ed \u00ecw\u00e1d\u00ec\u00ed.",
    "ig": "Ndeewo, ka any\u1ecb bido. Taa any\u1ecb na-ar\u1ee5 \u1ecdr\u1ee5 na nch\u1ecdp\u1ee5ta \u1ecdk\u1ecdr\u1ecd.",
    "zu": "Sawubona, ake siqale. Namuhla sisebenza ekusesheni okuhambisana nengxenye.",
}


async def list_voices(settings) -> int:
    from app.providers.elevenlabs.voices import list_voices as fetch

    try:
        voices = await fetch(settings)
    except Exception as exc:  # noqa: BLE001
        print(f"  ! could not list voices: {exc}")
        return 2
    print(f"  {len(voices)} voices on this account (server-side key, id + name):")
    for voice in voices[:25]:
        print(f"    - {voice['voice_id']}  {voice['name']}  [{voice.get('category')}]")
    print("\n  Pick one with ELEVENLABS_VOICE_ID=<id> in .env")
    return 0


async def sample(language: str) -> int:
    settings = get_settings()
    if not settings.elevenlabs_configured:
        print("  ! ELEVENLABS_API_KEY is not set \u2014 put the key in .env (free plan is fine).")
        return 2
    if not PROVIDER_CAPABILITIES["elevenlabs"].supports(Capability.TTS, language):
        print(f"  ! ElevenLabs TTS does not cover '{language}' (no Igbo, no Yoruba). "
              f"That language keeps Gemini/browser voice.")
        return 2

    text = speakable(SAMPLE.get(language, SAMPLE["en"]))
    print(f"\n== {language} ==")
    print(f"  voice   : {settings.elevenlabs_voice_id} \u00b7 model {settings.elevenlabs_tts_model}")
    if language == "en":
        from app.providers.elevenlabs.voice_check import format_preflight, preflight

        ok, results = await preflight(settings.elevenlabs_api_key, settings.elevenlabs_tts_model,
                                      settings.elevenlabs_voice_id)
        print(format_preflight(ok, results))
        if not ok:
            return 2
    print(f"  says    : {text[:140]}{'\u2026' if len(text) > 140 else ''}")

    from app.providers.elevenlabs.tts import ElevenLabsTTSProvider

    provider = ElevenLabsTTSProvider(settings)
    started = time.perf_counter()
    first_audio_ms: float | None = None
    pcm = bytearray()
    try:
        async for chunk in provider.synthesize_stream(text, language):
            if first_audio_ms is None:
                first_audio_ms = (time.perf_counter() - started) * 1000
            pcm.extend(chunk.data)
    except ProviderError as exc:
        print(f"  ! vendor refused: {type(exc).__name__}: {exc}")
        return 2
    total_ms = (time.perf_counter() - started) * 1000
    seconds = len(pcm) / (settings.output_sample_rate * 2)

    out = ROOT / "out"
    out.mkdir(exist_ok=True)
    wav_path = out / f"voice-sample-{language}.wav"
    with wave.open(str(wav_path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(settings.output_sample_rate)
        handle.writeframes(bytes(pcm))

    peak = max((abs(v) for (v,) in struct.iter_unpack("<h", bytes(pcm[: 2 * 24000]))), default=0)
    print(f"  transport           : {provider.last_transport} "
          f"(ws = streamed, rest = one call per line)")
    print(f"  connect+first audio : {first_audio_ms:.0f} ms" if first_audio_ms else "  no audio")
    print(f"  total               : {total_ms:.0f} ms \u00b7 {len(pcm)} bytes \u00b7 {seconds:.1f}s of {settings.output_sample_rate // 1000} kHz PCM")
    print(f"  peak sample         : {peak} (0 would mean silence)")
    print(f"  listen              : {wav_path}")
    return 0 if len(pcm) > settings.output_sample_rate else 2


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("language", nargs="?", default="en")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--list", action="store_true", dest="list_")
    args = parser.parse_args()

    settings = get_settings()
    print(f"ELEVENLABS_API_KEY : {'set' if settings.elevenlabs_configured else 'NOT set'}")
    print(f"demo voice         : {settings.voice_demo_voice} \u00b7 model {settings.elevenlabs_tts_model}")
    if not settings.elevenlabs_configured:
        print("\nNothing wired yet. Free plan key: https://elevenlabs.io \u2192 Profile \u2192 API Keys.")
        return 2

    if args.list_:
        return await list_voices(settings)

    languages = ["en", "ar", "fr", "sw", "am", "ha", "so", "zu"] if args.all else [args.language]
    worst = 0
    for language in languages:
        worst = max(worst, await sample(language))
    return worst


if __name__ == "__main__":
    os.environ.setdefault("VOICE_ENABLE_MOCK_PROVIDERS", "true")
    raise SystemExit(asyncio.run(main()))
