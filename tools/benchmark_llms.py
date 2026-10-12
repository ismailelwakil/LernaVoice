"""Round-25 live benchmark: Gemini vs OpenRouter as the lesson "brain", Azure as the voice.

Runs BOTH providers on (a) a lesson explanation and (b) a student question, in polite
Egyptian Arabic, measures time-to-first-token and total time, then lets Azure TTS speak
the winner. Purely observational — it does not change routing; the verdict is printed
and `llm_priority` is set by hand/config afterwards.

Usage: python3 tools/benchmark_llms.py
"""

from __future__ import annotations

import asyncio
import time

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


async def run(name, provider, user: str) -> dict:
    t0 = time.time()
    ttft = None
    out: list[str] = []
    try:
        async for ev in provider.stream_reply(
            [{"role": "user", "content": user}],
            system_instruction=SYSTEM,
            language="ar",
        ):
            if ev.type is ProviderEventType.OUTPUT_TRANSCRIPT:
                if ttft is None:
                    ttft = time.time() - t0
                out.append(ev.text or "")
        ok, err = True, ""
    except Exception as exc:  # noqa: BLE001
        ok, err = False, f"{type(exc).__name__}: {str(exc)[:120]}"
    total = time.time() - t0
    text = "".join(out).strip()
    return {
        "provider": name, "ok": ok, "err": err,
        "ttft": round(ttft, 2) if ttft is not None else None,
        "total": round(total, 2), "chars": len(text), "text": text,
    }


async def main() -> None:
    s = get_settings()
    print("model(openrouter):", s.openrouter_model, "| gemini text:", s.gemini_text_model)
    gem = GeminiLLMProvider(s)
    ort = OpenRouterLLMProvider(s)

    results = {}
    for label, user in (("lesson", LESSON), ("question", QUESTION)):
        g = await run("gemini", gem, user)
        o = await run("openrouter", ort, user)
        results[label] = (g, o)
        print(f"\n===== {label.upper()} =====")
        for r in (g, o):
            line = f"[{r['provider']}] ok={r['ok']} ttft={r['ttft']}s total={r['total']}s chars={r['chars']}"
            print(line)
            if not r["ok"]:
                print("   err:", r["err"])
            else:
                print("   text:", r["text"][:220])

    # verdict: prefer success, then lower TTFT, then more content
    def score(r):
        return (0 if r["ok"] else 1, r["ttft"] if r["ttft"] is not None else 99, -r["chars"])

    g_score = score(results["lesson"][0]) + score(results["question"][0])
    o_score = score(results["lesson"][1]) + score(results["question"][1])
    winner = "gemini" if g_score <= o_score else "openrouter"
    loser = "openrouter" if winner == "gemini" else "gemini"
    print(f"\nVERDICT: primary={winner} secondary={loser}  (gemini {g_score} vs openrouter {o_score})")

    # let Azure speak the winner's lesson answer
    win_r = results["lesson"][0] if winner == "gemini" else results["lesson"][1]
    if win_r["ok"] and win_r["text"]:
        try:
            from app.providers.azure.tts import AzureTTSProvider
            tts = AzureTTSProvider(s)
            t0 = time.time()
            chunks = 0
            async for c in tts.synthesize_stream(win_r["text"][:400], "ar", voice="ar-EG-SalmaNeural"):
                chunks += 1
            print(f"\nAZURE spoke winner text: {chunks} chunks in {round(time.time()-t0,2)}s (ar-EG-SalmaNeural)")
        except Exception as exc:  # noqa: BLE001
            print("\nAZURE TTS failed:", type(exc).__name__, str(exc)[:150])


asyncio.run(main())
