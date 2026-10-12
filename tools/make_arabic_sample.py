"""Round 18: the Arabic sample, fusHa only - plain voice vs humanised voice.

    python3 tools/make_arabic_sample.py

Writes demo-audio/arabic-humanised.wav (24 kHz mono PCM16): first the plain
Azure voice, a beat of silence, then the same sentence with the humanising SSML
(expressive style, pitch lift, breaths, emphasis on English technical terms).
"""
import asyncio
import os
import sys
import wave

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import Settings  # noqa: E402
from app.providers.azure.tts import AzureTTSProvider  # noqa: E402

SENTENCE = (
    "مرحبًا بك، لنبدأ الدرس. "
    "نتناول اليوم binary search، ونقسم المدى نصفين في كل خطوة."
)
OUT = os.path.join("demo-audio", "arabic-humanised.wav")
RATE = 24000


async def speak(settings: Settings) -> bytes:
    provider = AzureTTSProvider(settings)
    chunks = [c async for c in provider.synthesize_stream(SENTENCE, "ar")]
    return b"".join(c.data for c in chunks)


async def main() -> None:
    base = Settings(_env_file=".env")
    plain = base.model_copy(
        update={"azure_tts_style": "", "azure_tts_pitch": 0.0, "azure_tts_pauses": False}
    )
    raw = await speak(plain)
    human = await speak(base)
    gap = b"\x00\x00" * int(RATE * 0.6)          # 600 ms so the two are audibly apart
    pcm = raw + gap + human

    os.makedirs("demo-audio", exist_ok=True)
    with wave.open(OUT, "wb") as fh:
        fh.setnchannels(1)
        fh.setsampwidth(2)
        fh.setframerate(RATE)
        fh.writeframes(pcm)
    seconds = len(pcm) / 2 / RATE
    print(f"{OUT}: {len(pcm)} bytes of PCM, {seconds:.1f}s")
    print(f"  plain    {len(raw):7d} bytes = {len(raw) / 2 / RATE:5.1f}s")
    print(f"  humanised{len(human):7d} bytes = {len(human) / 2 / RATE:5.1f}s")


asyncio.run(main())
