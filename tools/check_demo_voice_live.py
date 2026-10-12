#!/usr/bin/env python3
"""Listen to what the *running service* actually sends the browser.

    python3 tools/check_demo_voice_live.py [lang] [--port 3000]

Different question from `verify_elevenlabs_voice.py` (which tests the vendor
directly): this one opens a real session over the WebSocket, collects the
assistant PCM the demo client would play, and decides whether it is vendor
**speech** or the synthetic demo tone \u2014 a tone has only a few dozen distinct
sample values, human speech thousands.

Writes `out/session-<lang>.wav` so the result can be played outside the browser.
Exit codes: 0 speech · 2 synthetic/mock (i.e. the human voice is not wired).
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import struct
import sys
import urllib.request
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import websockets  # noqa: E402


def _get(base: str, path: str) -> dict:
    return json.loads(urllib.request.urlopen(base + path, timeout=20).read())


def _post(base: str, path: str, body: dict) -> dict:
    request = urllib.request.Request(
        base + path, data=json.dumps(body).encode(), headers={"content-type": "application/json"}
    )
    return json.loads(urllib.request.urlopen(request, timeout=20).read())


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("language", nargs="?", default="ar")
    parser.add_argument("--port", type=int, default=3000)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--seconds", type=float, default=20)
    args = parser.parse_args()
    base = f"http://{args.host}:{args.port}"

    health = _get(base, "/health")
    print(f"service    : {health['service']} \u00b7 mock_providers={health['mock_providers']}")
    print(f"demo voice : {health.get('demo_voice') or 'none (synthetic tone)'}")
    try:
        voices = _get(base, "/voice/voices")
        print(f"voices     : {len(voices['voices'])} available \u00b7 default {voices['default_voice_id']}")
    except Exception as exc:  # noqa: BLE001
        print(f"voices     : not available ({exc})")

    session = _post(
        base,
        "/voice/session",
        {"student_id": "voice-check", "language": args.language, "topic_id": "binary-search"},
    )
    pcm = bytearray()
    transcript = []
    async with websockets.connect(
        f"ws://{args.host}:{args.port}/voice/session/{session['session_id']}/audio",
        max_size=None,
    ) as ws:
        await ws.send(json.dumps({"type": "start"}))
        deadline = asyncio.get_event_loop().time() + args.seconds
        while asyncio.get_event_loop().time() < deadline:
            try:
                raw = await asyncio.wait_for(
                    ws.recv(), timeout=deadline - asyncio.get_event_loop().time()
                )
            except asyncio.TimeoutError:
                break
            if isinstance(raw, (bytes, bytearray)):
                continue
            event = json.loads(raw)
            data = event.get("data") if isinstance(event.get("data"), dict) else event
            if event.get("event") == "assistant.audio.chunk" and data.get("audio"):
                pcm.extend(base64.b64decode(data["audio"]))
            elif event.get("event") == "assistant.text.delta" and data.get("text"):
                transcript.append(data["text"])
            elif event.get("event") == "assistant.response.completed":
                break

    samples = [value for (value,) in struct.iter_unpack("<h", bytes(pcm[: 24000 * 2]))]
    distinct = len(set(samples))
    speech = distinct > 1000
    print(f"heard      : {len(pcm)} bytes \u00b7 {len(pcm) / 48000:.1f}s of PCM \u00b7 {distinct} distinct samples/s")
    if transcript:
        print(f"said       : {''.join(transcript)[:150]}")
    out = ROOT / "out"
    out.mkdir(exist_ok=True)
    path = out / f"session-{args.language}.wav"
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(24000)
        handle.writeframes(bytes(pcm))
    print(f"verdict    : {'VENDOR SPEECH' if speech else 'synthetic tone \u2014 no human voice wired'}")
    print(f"listen     : {path}")
    return 0 if speech else 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
