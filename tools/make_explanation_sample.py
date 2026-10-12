"""Round 19: the same topic explained at two levels, spoken in fusHa.

    python3 tools/make_explanation_sample.py

Writes demo-audio/explanation-levels-ar.wav (24 kHz mono PCM16): first the turn
an Arabic **beginner** hears for binary search, a beat of silence, then the turn
an **advanced** student hears for the same topic. Both turn texts are captured
from a real WebSocket session against the running service
(`tools/ws_levels_probe.py`), so what is heard here is exactly what the demo
teaches — grounded in the vetted sources, ordered by the level, and voiced by
the live Azure voice.
"""
import asyncio
import json
import os
import sys
import wave

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import Settings  # noqa: E402
from app.providers.azure.tts import AzureTTSProvider, voice_for  # noqa: E402

TEXTS = "/tmp/levels_text.json"
OUT = os.path.join("demo-audio", "explanation-levels-ar.wav")
RATE = 24000

#: What the service actually said, per level (captured over the socket). Kept in
#: the repo so the sample can be rebuilt without a live session.
FALLBACK = {
    "beginner": (
        "مرحبًا بك، لنبدأ الدرس. نتناول اليوم البحث الثنائي. أولًا. "
        "دعني أرسم لك صورة أولًا. تخيّل أنك تبحث عن كلمة في المعجم: افتح المنتصف، "
        "ثم اختر النصف الذي يجب أن تكون فيه الكلمة، وأعد الخطوة. "
        "يمكنك أن تقاطعني في أي وقت."
    ),
    "advanced": (
        "مرحبًا بك، لنبدأ الدرس. نتناول اليوم البحث الثنائي. أولًا. "
        "الفكرة ببساطة: البحث الثنائي ينظر إلى العنصر الأوسط في قائمة مرتبة، "
        "ثم يستبعد النصف الذي يستحيل أن يحتوي على الهدف. "
        "يمكنك أن تقاطعني في أي وقت."
    ),
}


def turns() -> dict[str, str]:
    if os.path.exists(TEXTS):
        with open(TEXTS, encoding="utf-8") as fh:
            captured = json.load(fh)
        if set(captured) >= set(FALLBACK) and all(captured.values()):
            return captured
    return FALLBACK


async def speak(provider: AzureTTSProvider, text: str) -> bytes:
    chunks = [c async for c in provider.synthesize_stream(text, "ar")]
    return b"".join(c.data for c in chunks)


async def main() -> None:
    settings = Settings(_env_file=".env")
    provider = AzureTTSProvider(settings)
    spoken = turns()

    parts = {}
    for level in ("beginner", "advanced"):
        parts[level] = await speak(provider, spoken[level])

    gap = b"\x00\x00" * int(RATE * 0.7)          # 700 ms between the two levels
    pcm = parts["beginner"] + gap + parts["advanced"]

    os.makedirs("demo-audio", exist_ok=True)
    with wave.open(OUT, "wb") as fh:
        fh.setnchannels(1)
        fh.setsampwidth(2)
        fh.setframerate(RATE)
        fh.writeframes(pcm)
    print(f"{OUT}: {len(pcm)} bytes of PCM, {len(pcm) / 2 / RATE:.1f}s")
    for level, data in parts.items():
        print(f"  {level:10s} {len(data):7d} bytes = {len(data) / 2 / RATE:5.1f}s")
    print("  voice      ", voice_for("ar", "ar-MSA", settings))


asyncio.run(main())
