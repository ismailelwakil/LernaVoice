"""Round-27 live benchmark: the three providers on the axis each actually competes on.

Fish Audio is a TEXT-TO-SPEECH service, so it cannot be a lesson "brain" — it competes
with Azure on the VOICE axis. OpenRouter and Gemini are text models, so they compete on
the BRAIN axis. This runs both axes live and prints a winner for each role:

  BRAIN  : OpenRouter vs Gemini  — generate a polite-Egyptian lesson + answer a question.
  VOICE  : Fish Audio vs Azure   — speak the same Arabic line; measure latency + audio.

Purely observational — it does not change routing. Usage:
    PYTHONPATH=. python3 tools/benchmark_tts.py
"""

from __future__ import annotations

import asyncio
import os
import time
import wave

from app.config import get_settings
from app.providers.base import ProviderEventType
from app.providers.gemini.llm import GeminiLLMProvider
from app.providers.openrouter.llm import OpenRouterLLMProvider

SYSTEM = (
    "You are a warm, respectful tutor. Answer in polite Egyptian Arabic (عامية مهذبة: "
    "يا فندم/حضرتك), short spoken sentences, one concrete example. Never use English "
    "phrases. 4-7 sentences."
)
LESSON = "اشرح لطالب ثانوي فكرة تركيب الخلية ووظيفة الغشاء الخلوي."
QUESTION = "ليه الغشاء الخلوي مهم للخلية؟"
VOICE_LINE = "أهلًا يا فندم. النهارده هنتكلم عن الخلية والغشاء اللي بيحميها."
OUT_DIR = "demo-audio"


async def run_llm(name, provider, user: str) -> dict:
    t0 = time.time()
    ttft = None
    out: list[str] = []
    try:
        async for ev in provider.stream_reply(
            [{"role": "user", "content": user}], system_instruction=SYSTEM, language="ar"
        ):
            if ev.type is ProviderEventType.OUTPUT_TRANSCRIPT:
                if ttft is None:
                    ttft = time.time() - t0
                out.append(ev.text or "")
        ok, err = True, ""
    except Exception as exc:  # noqa: BLE001
        ok, err = False, f"{type(exc).__name__}: {str(exc)[:140]}"
    text = "".join(out).strip()
    return {"provider": name, "ok": ok, "err": err,
            "ttft": round(ttft, 2) if ttft is not None else None,
            "total": round(time.time() - t0, 2), "chars": len(text), "text": text}


async def run_tts(name, provider, text: str, language: str, voice: str | None, tag: str) -> dict:
    t0 = time.time()
    ttft = None
    chunks = 0
    audio = bytearray()
    rate = 24000
    try:
        async for c in provider.synthesize_stream(text, language, voice=voice):
            if ttft is None:
                ttft = time.time() - t0
            chunks += 1
            audio += c.data
            rate = c.sample_rate or rate
        ok, err = True, ""
    except Exception as exc:  # noqa: BLE001
        ok, err = False, f"{type(exc).__name__}: {str(exc)[:140]}"
    total = time.time() - t0
    seconds = round(len(audio) / (2 * rate), 2) if audio else 0.0
    if ok and audio:
        os.makedirs(OUT_DIR, exist_ok=True)
        path = os.path.join(OUT_DIR, f"round27_{tag}.wav")
        with wave.open(path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(rate)
            wf.writeframes(bytes(audio))
    else:
        path = ""
    return {"provider": name, "ok": ok, "err": err,
            "ttft": round(ttft, 2) if ttft is not None else None,
            "total": round(total, 2), "chunks": chunks, "audio_s": seconds, "file": path}


async def main() -> None:
    s = get_settings()
    print("openrouter model:", s.openrouter_model, "| gemini text:", s.gemini_text_model,
          "| fish model:", s.fish_audio_model)
    print("configured:", sorted(s.configured_providers()))

    # ---------------- BRAIN axis: OpenRouter vs Gemini ----------------
    print("\n########## BRAIN (text reasoning) ##########")
    gem, ort = GeminiLLMProvider(s), OpenRouterLLMProvider(s)
    brain: dict[str, tuple] = {}
    for label, user in (("lesson", LESSON), ("question", QUESTION)):
        g = await run_llm("gemini", gem, user)
        o = await run_llm("openrouter", ort, user)
        brain[label] = (g, o)
        print(f"\n===== {label.upper()} =====")
        for r in (g, o):
            print(f"[{r['provider']}] ok={r['ok']} ttft={r['ttft']}s total={r['total']}s chars={r['chars']}")
            if not r["ok"]:
                print("   err:", r["err"])
            else:
                print("   text:", r["text"][:200])

    def brain_score(r):
        return (0 if r["ok"] else 1, r["ttft"] if r["ttft"] is not None else 99, -r["chars"])

    g_s = brain_score(brain["lesson"][0]) + brain_score(brain["question"][0])
    o_s = brain_score(brain["lesson"][1]) + brain_score(brain["question"][1])
    brain_winner = "gemini" if g_s <= o_s else "openrouter"
    print(f"\nBRAIN VERDICT: winner={brain_winner}  (gemini {g_s} vs openrouter {o_s})")

    # ---------------- VOICE axis: Fish Audio vs Azure ----------------
    print("\n########## VOICE (text-to-speech) ##########")
    win_text = (brain["lesson"][0] if brain_winner == "gemini" else brain["lesson"][1])["text"]
    say = (win_text[:300] if win_text else VOICE_LINE)
    print("speaking:", say[:120], "...")

    from app.providers.azure.tts import AzureTTSProvider
    from app.providers.fish.tts import FishAudioTTSProvider

    azure = await run_tts("azure", AzureTTSProvider(s), say, "ar", "ar-EG-SalmaNeural", "azure_ar")
    fish = await run_tts("fish", FishAudioTTSProvider(s), say, "ar", None, "fish_ar")
    for r in (azure, fish):
        print(f"[{r['provider']}] ok={r['ok']} ttft={r['ttft']}s total={r['total']}s "
              f"chunks={r['chunks']} audio={r['audio_s']}s file={r['file']}")
        if not r["ok"]:
            print("   err:", r["err"])

    def voice_score(r):
        return (0 if r["ok"] else 1, r["ttft"] if r["ttft"] is not None else 99, -r["audio_s"])

    voice_winner = "azure" if voice_score(azure) <= voice_score(fish) else "fish"
    print(f"\nVOICE VERDICT: winner={voice_winner} "
          f"(azure {voice_score(azure)} vs fish {voice_score(fish)})")

    print(f"\n===== SUMMARY =====\n  BRAIN winner : {brain_winner} (the other is the fallback brain)")
    print(f"  VOICE winner : {voice_winner} (the other is the fallback voice)")
    print("  Fish Audio is a voice, not a brain — it backs up Azure, not OpenRouter/Gemini.")


asyncio.run(main())
