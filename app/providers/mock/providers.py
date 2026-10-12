"""Deterministic mock providers (§52) — TESTS ONLY.

They are registered only when VOICE_ENABLE_MOCK_PROVIDERS=true or by the test
fixtures. Production code paths never select them.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
from typing import Any, AsyncIterator

from app.curriculum import LOCALISED_GREETINGS
from app.learner.canonical_concepts import catalogue_concepts

logger = logging.getLogger(__name__)
from app.prompts.interaction import is_language_switch_prompt, speakable

from app.providers.mock.dialogue import TutorDialogue
from app.providers.base import (
    AudioChunk,
    LLMProvider,
    ProviderAuthError,
    ProviderError,
    ProviderEvent,
    ProviderEventType,
    ProviderInternalError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    RealtimeVoiceProvider,
    SessionConfig,
    SpeechToTextProvider,
    TextToSpeechProvider,
    ToolHandler,
)

FAILURES: dict[str, type[ProviderError]] = {
    "timeout": ProviderTimeoutError,
    "rate_limit": ProviderRateLimitError,
    "auth": ProviderAuthError,
    "internal": ProviderInternalError,
}


class FailureInjector:
    """Shared switchboard used by failover tests to break a vendor on demand."""

    def __init__(self) -> None:
        self._rules: dict[str, tuple[str, int]] = {}

    def fail(self, provider: str, kind: str = "internal", times: int = 10_000) -> None:
        self._rules[provider] = (kind, times)

    def heal(self, provider: str | None = None) -> None:
        if provider:
            self._rules.pop(provider, None)
        else:
            self._rules.clear()

    def check(self, provider: str) -> None:
        rule = self._rules.get(provider)
        if not rule:
            return
        kind, remaining = rule
        if remaining <= 0:
            self._rules.pop(provider, None)
            return
        self._rules[provider] = (kind, remaining - 1)
        raise FAILURES.get(kind, ProviderInternalError)(
            f"injected {kind} failure for {provider}", provider=provider
        )


INJECTOR = FailureInjector()


SAMPLE_RATE = 24000

#: What the mock tutor says. It is deliberately tutor-shaped — the demo voices
#: this transcript, so it should read like a lesson rather than a placeholder.
#: `reply_for_turn` also appends the turn number, which keeps the text unique
#: per turn (useful when reading the event stream).
TUTOR_LINES = (
    "Welcome back. Last time we covered searching a sorted range. "
    "Today let us see what happens when the range is empty.",
    "Good question. Binary search compares the target with the middle element, "
    "then discards the half that cannot contain it. So the range halves each step.",
    "Careful: the array must be sorted first. If it is not sorted, discard "
    "the half is not a safe move and the search can miss the target.",
    "Let us trace it. With sixteen elements, after one step we have eight, "
    "then four, then two, then one. That is why the cost grows like log of n.",
    "One common mistake is computing the midpoint with a plain sum. "
    "Adding two large indices overflows; the safe form adds half the difference.",
)
#: ~45 ms of audio per character of text, so a mock reply lasts roughly as long
#: as the sentence it stands in for (clamped — this is a demo, not a codec).
MS_PER_CHAR = 45
MIN_UTTERANCE_MS = 700
MAX_UTTERANCE_MS = 3200
#: Chunk size the mocks stream in (~120 ms @ 24 kHz). Streaming in chunks — not
#: one big blob — is what exercises the client's incremental playback path.
_CHUNK_MS = 120


def utterance_ms(text: str) -> int:
    """How long the mock voice should 'speak' a given line for."""
    return max(MIN_UTTERANCE_MS, min(MAX_UTTERANCE_MS, len(text) * MS_PER_CHAR))


def _voice_pcm(
    duration_ms: int,
    *,
    sample_rate: int = SAMPLE_RATE,
    seed: int = 7,
    amplitude: float = 0.28,
) -> bytes:
    """Synthesise an audible, speech-like utterance as PCM16 LE.

    A single sine would sound like a test tone, so this builds a stream of
    syllable-like bursts: each syllable gets a pitch drawn from a small
    pseudo-random walk (deterministic for a given seed), a couple of harmonics
    for timbre, and an attack/decay envelope. The result is clearly audible and
    recognisably "someone talking" without pretending to be real speech.

    Deterministic: same (duration_ms, sample_rate, seed) always yields the same
    bytes, so tests stay reproducible.
    """
    import math

    n = int(sample_rate * duration_ms / 1000)
    if n <= 0:
        return b""
    frames = bytearray()
    rng = seed or 1
    idx = 0
    while idx < n:
        # ---- new syllable -------------------------------------------------
        rng = (1103515245 * rng + 12345) % (2**31)
        pitch = 105.0 + (rng / 2**31) * 90.0            # 105–195 Hz
        rng = (1103515245 * rng + 12345) % (2**31)
        syl_ms = 90.0 + (rng / 2**31) * 120.0           # 90–210 ms syllables
        syl_len = max(1, int(sample_rate * syl_ms / 1000))
        # occasional short pause between "words"
        rng = (1103515245 * rng + 12345) % (2**31)
        gap_len = int(sample_rate * 35 / 1000) if rng % 5 == 0 else 0
        fade = max(1, int(sample_rate * 12 / 1000))      # 12 ms attack/decay

        for i in range(syl_len):
            t = i / sample_rate
            env = 1.0
            if i < fade:
                env = i / fade
            elif i > syl_len - fade:
                env = max(0.0, (syl_len - i) / fade)
            # pitch glides slightly across the syllable — sounds more human
            f = pitch * (1.0 + 0.06 * (i / syl_len))
            v = (
                math.sin(2 * math.pi * f * t)
                + 0.35 * math.sin(2 * math.pi * 2 * f * t)
                + 0.18 * math.sin(2 * math.pi * 3 * f * t)
            )
            sample = int(max(-1.0, min(1.0, v / 1.53 * env * amplitude)) * 32767)
            frames += sample.to_bytes(2, "little", signed=True)

        frames += b"\x00\x00" * gap_len
        idx += syl_len + gap_len
    return bytes(frames[: n * 2])


#: Service-generated prompts that are instructions, not the student speaking.
_SERVICE_PROMPTS = (
    "Greet the student",           # OPENING_PROMPT
    "Resume the lesson",           # RESUME_PROMPT
    "The student is returning",    # RECAP_PROMPT
    "Continue answering",          # mid-failover nudge
    "Language changed",            # (legacy) switch notice
    "The student switched",        # language switch prompt
)


def _student_words(prompt: str) -> str:
    """The student's own words, out of whatever the service sent to the provider.

    The service wraps a question as `The student asked (in English): "…"` and sends
    bare text for typed turns. A real vendor attends to the whole prompt; the demo
    needs just the student's sentence to decide whether they said "yes", "no" or
    asked something — so it unwraps the question form and otherwise treats the text
    as the student speaking, unless it is a service instruction.
    """
    text = (prompt or "").strip()
    if not text or any(text.startswith(m) for m in _SERVICE_PROMPTS):
        return ""
    match = re.search(r'asked \(in [^)]*\):\s*"(.*?)"', text, re.S)
    if match:
        return match.group(1).strip()
    return text


def planned_line(metadata: dict[str, Any] | None, language: str, index: int,
                 topic_fallback: str = "this topic") -> str | None:
    """The tutor's line for step `index` of a catalogued lesson plan.

    Shared by the realtime mock and the LLM mock so a composed pipeline (Igbo,
    Yoruba) teaches the same plan as a native realtime session. Returns None when
    the session has no plan, which keeps the generic mock lines in play.
    """
    sections = (metadata or {}).get("sections") or []
    if not sections:
        return None
    topic = (metadata or {}).get("topic_title") or topic_fallback
    if index == 0:
        greeting = LOCALISED_GREETINGS.get(language, LOCALISED_GREETINGS["en"])
        first = sections[0]
        return (
            f"{greeting} Today we are covering {topic}. "
            f"Step 1, {first['title']}: {first.get('goal', '')}."
        )
    if index < len(sections):
        step = sections[index]
        return f"Step {index + 1}, {step['title']}: {step.get('goal', '')}."
    return (
        f"That completes the plan for {topic}. "
        "Ask me about any step and we will go deeper into it."
    )


def _chunks(pcm: bytes, sample_rate: int = SAMPLE_RATE):
    """Split a buffer into AudioChunks the way a streaming vendor would."""
    step = int(sample_rate * _CHUNK_MS / 1000) * 2
    for start in range(0, len(pcm), step):
        blob = pcm[start : start + step]
        if blob:
            yield AudioChunk(data=blob, sample_rate=sample_rate)


def _tone(nbytes: int = 1600) -> bytes:
    """Short audible beep (kept for callers that just want *some* audio)."""
    return _voice_pcm(max(1, int(nbytes / 2 / SAMPLE_RATE * 1000)) or 1)


class MockRealtimeProvider(RealtimeVoiceProvider):
    provider_name = "mock"
    supports_native_interruption = True
    supports_turn_detection = True

    def __init__(
        self,
        vendor: str = "mock",
        *,
        reply: str = "This is the mock tutor speaking.",
        transcript: str = "What is the midpoint of the current range?",
    ):
        self.provider_name = vendor
        #: Tests that assert on a specific line pass `reply`; the demo page gets
        #: the rotating tutor lines below.
        self.reply = reply
        self._custom_reply = reply != "This is the mock tutor speaking."
        self.transcript = transcript
        self._queue: asyncio.Queue[ProviderEvent | None] = asyncio.Queue()
        self._open = False
        self._tool_handler: ToolHandler | None = None
        self.sent_text: list[str] = []
        self.audio_bytes_in = 0
        self.interrupts = 0
        self.config: SessionConfig | None = None
        #: Stand-in VAD: an utterance ends after this much inbound audio
        #: (12800 B = 0.4 s of 16 kHz PCM16) followed by a pause.
        self.vad_min_bytes = 12800
        self.vad_silence_s = 0.6
        self._since_turn = 0
        self._partial_sent = False
        self._heard_text = ""
        self._turn_timer: asyncio.Task | None = None
        self._turns = 0
        self._language_switch = False
        self._greeted = False
        self._reported_section = ""
        self.dialogue = TutorDialogue()
        #: Optional *real* voice for the demo (app/voice/demo_voice.py). When set,
        #: the tutor's sentences are spoken by a vendor instead of the built-in
        #: synthetic tone, while the conversation itself stays offline.
        self.tts = None
        self.tts_vendor: str | None = None
        #: Arabic register of this session (`ar-MSA` today), if any.
        self.dialect: str | None = None
        self.tts_voice: str | None = None
        self.tts_bytes = 0
        self.tts_fallbacks = 0

    async def start_session(self, config: SessionConfig) -> None:
        INJECTOR.check(self.provider_name)
        self.config = config
        self.dialogue = TutorDialogue.from_metadata(config.metadata, config.language)
        # A reconnect (failover / language switch) hands back `step_index` > 0: the
        # student already heard the opening and the earlier parts, so do NOT greet and
        # re-explain from the top — continue from where the lesson stopped (§10, and the
        # round-23 "it starts explaining again with the same text" complaint).
        _si = (config.metadata or {}).get("step_index") or 0
        try:
            _si = int(_si)
        except (TypeError, ValueError):
            _si = 0
        self._greeted = bool((config.metadata or {}).get("resumed")) or _si > 0
        self.tts_voice = (config.metadata or {}).get("tts_voice_id") or None
        self.language = config.language
        self.dialect = (config.metadata or {}).get("dialect") or None
        # A vendor voice that has more than one voice per language (Arabic is
        # taught in fusHa: `ar-SA-ZariyahNeural`) is told which one to use.
        _context = getattr(self.tts, "set_language_context", None)
        if _context is not None:
            _context(config.language, self.dialect)
        self._open = True
        await self._queue.put(ProviderEvent(type=ProviderEventType.CONNECTED))

    async def send_audio(self, audio: AudioChunk) -> None:
        if not self._open:
            raise ProviderInternalError("session not open", provider=self.provider_name)
        INJECTOR.check(self.provider_name)
        self.audio_bytes_in += len(audio.data)
        if not self.vad_min_bytes:
            return
        # Stand in for the vendor's own turn detection so the demo can be driven
        # by a real microphone: audio in, and when the student stops talking the
        # mock "hears" an utterance and answers. A pause is what ends the turn —
        # not a byte count — so continuous speech yields exactly one reply.
        self._since_turn += len(audio.data)
        if not self._partial_sent and self._since_turn >= self.vad_min_bytes // 2:
            self._partial_sent = True
            await self._queue.put(
                ProviderEvent(
                    type=ProviderEventType.INPUT_TRANSCRIPT,
                    text=self.transcript[: max(1, len(self.transcript) // 2)],
                    partial=True,
                )
            )
        self._arm_turn_timer()

    def _arm_turn_timer(self) -> None:
        if self._turn_timer and not self._turn_timer.done():
            self._turn_timer.cancel()
        if self._since_turn >= 1:
            self._turn_timer = asyncio.get_running_loop().create_task(self._end_turn_after_silence())

    async def _end_turn_after_silence(self) -> None:
        try:
            await asyncio.sleep(self.vad_silence_s)
        except asyncio.CancelledError:
            return  # student is still talking
        if not self._open or self._since_turn < self.vad_min_bytes:
            return
        self._since_turn = 0
        self._partial_sent = False
        self._heard_text = self.transcript
        await self._queue.put(
            ProviderEvent(type=ProviderEventType.INPUT_TRANSCRIPT, text=self.transcript, partial=False)
        )
        await self._speak(self.reply_for_turn(self._heard_text))

    async def send_text(self, text: str, *, role: str = "user", trigger_response: bool = True) -> None:
        if not self._open:
            raise ProviderInternalError("session not open", provider=self.provider_name)
        INJECTOR.check(self.provider_name)
        self.sent_text.append(text)
        if not trigger_response:
            return
        if is_language_switch_prompt(text):
            self._language_switch = True
            await self._speak(self.reply_for_turn())
            return
        await self._speak(self.reply_for_turn(_student_words(text)))

    def reply_for_turn(self, student_text: str = "") -> str:
        """The tutor's next spoken line.

        With a catalogue lesson plan this runs the demo dialogue policy
        (`app/providers/mock/dialogue.py`): teach one step, check understanding,
        and react to what the student said. Without a plan it falls back to the
        rotating generic lines.
        """
        self._turns += 1
        if self._custom_reply:
            return self.reply
        dialogue = self.dialogue
        if self._language_switch:
            self._language_switch = False
            self._greeted = True          # the switch line is this session's greeting
            return dialogue.language_switch()
        if not self._greeted:
            # Session start: greet (in the session language), teach step one, check in.
            self._greeted = True
            return dialogue.opening()
        if dialogue.planned:
            return dialogue.respond(student_text)
        line = TUTOR_LINES[(self._turns - 1) % len(TUTOR_LINES)]
        return line

    async def _report_position(self) -> None:
        """Tell the session which plan step we are teaching (`update_lesson_position`).

        With the position in session state, a reconnect (failover or a language
        change) hands the new provider `step_index`, so the lesson continues
        instead of starting over.
        """
        section = self.dialogue.current_section()
        if not self._tool_handler or not section:
            return
        # Report the plan's own naming (English catalogue) so the service's state,
        # checkpoints and step lookup stay language-independent; the student hears
        # the localised wording.
        title = section.get("original_title") or section.get("title", "")
        if not title or title == self._reported_section:
            return
        self._reported_section = title

        # Moving past a step means the student has met its concept: record it under
        # the catalogue's English name, so the profile is readable whatever language
        # the lesson was taught in.
        args: dict[str, Any] = {
            "topic": self.dialogue.plan_topic or self.dialogue.topic,
            "section": title,
        }
        concepts = catalogue_concepts(self.dialogue.topic_id)
        finished = self.dialogue.step - 1
        if 0 <= finished < len(concepts):
            args["last_concept"] = concepts[finished]
        with contextlib.suppress(Exception):
            await self._tool_handler("update_lesson_position", args)

    def attach_tts(self, tts, vendor: str) -> None:
        """Voice this offline session with a real TTS vendor (see demo_voice.py)."""
        self.tts = tts
        self.tts_vendor = vendor

    async def _speak(self, reply: str) -> None:
        """Emit a full assistant turn: transcript delta(s) then streamed audio."""
        await self._report_position()
        await self._queue.put(ProviderEvent(type=ProviderEventType.TURN_STARTED))
        await self._queue.put(ProviderEvent(type=ProviderEventType.OUTPUT_TRANSCRIPT, text=reply))
        if not await self._speak_with_vendor(reply):
            pcm = _voice_pcm(utterance_ms(reply), seed=len(reply) + self._since_turn)
            for chunk in _chunks(pcm):
                # ProviderEvent.audio carries raw PCM bytes (the session manager
                # base64-encodes it for the client itself).
                await self._queue.put(ProviderEvent(type=ProviderEventType.AUDIO, audio=chunk.data))
        await self._queue.put(ProviderEvent(type=ProviderEventType.TURN_COMPLETE, text=reply))

    async def _speak_with_vendor(self, reply: str) -> bool:
        """Speak `reply` through the attached vendor TTS. False → synthetic fallback.

        A vendor that is slow, out of quota or unreachable must never end the
        lesson: the student hears the synthetic voice and keeps going, and the
        failure is visible in `tts_fallbacks`.
        """
        if self.tts is None:
            return False
        spoken = speakable(reply)
        try:
            async for chunk in self.tts.synthesize_stream(
                spoken, self.language, voice=self.tts_voice or None
            ):
                self.tts_bytes += len(chunk.data)
                await self._queue.put(ProviderEvent(type=ProviderEventType.AUDIO, audio=chunk.data))
        except Exception as exc:  # noqa: BLE001 - any vendor problem falls back
            self.tts_fallbacks += 1
            logger.warning(
                "demo voice %s failed (%s); using the synthetic voice for this turn",
                self.tts_vendor,
                exc,
            )
            self.tts_bytes = 0
            return False
        if self.tts_bytes == 0:
            self.tts_fallbacks += 1
            return False
        return True

    async def receive_events(self) -> AsyncIterator[ProviderEvent]:
        while True:
            event = await self._queue.get()
            if event is None:
                return
            yield event

    async def interrupt(self) -> None:
        self.interrupts += 1
        await self._queue.put(ProviderEvent(type=ProviderEventType.INTERRUPTED))

    async def close_session(self) -> None:
        self._open = False
        if self._turn_timer and not self._turn_timer.done():
            self._turn_timer.cancel()
        await self._queue.put(None)

    def set_tool_handler(self, handler: ToolHandler | None) -> None:
        self._tool_handler = handler


class MockSTTProvider(SpeechToTextProvider):
    def __init__(self, vendor: str = "mock", transcript: str = "mock transcript"):
        self.provider_name = vendor
        self.transcript = transcript
        self._queue: asyncio.Queue[ProviderEvent | None] = asyncio.Queue()
        self.audio_bytes_in = 0
        self.started = False

    async def start_stream(self, language: str, sample_rate: int = 16000) -> None:
        INJECTOR.check(self.provider_name)
        self.started = True
        self.language = language

    async def send_audio(self, chunk: AudioChunk) -> None:
        INJECTOR.check(self.provider_name)
        self.audio_bytes_in += len(chunk.data)

    async def receive_events(self) -> AsyncIterator[ProviderEvent]:
        while True:
            event = await self._queue.get()
            if event is None:
                return
            yield event

    async def finalize(self) -> None:
        INJECTOR.check(self.provider_name)
        await self._queue.put(
            ProviderEvent(type=ProviderEventType.INPUT_TRANSCRIPT, text=self.transcript, partial=False)
        )

    async def push_transcript(self, text: str, partial: bool = False) -> None:
        await self._queue.put(ProviderEvent(type=ProviderEventType.INPUT_TRANSCRIPT, text=text, partial=partial))

    async def stop_stream(self) -> None:
        self.started = False
        await self._queue.put(None)


class MockTTSProvider(TextToSpeechProvider):
    def __init__(self, vendor: str = "mock"):
        self.provider_name = vendor
        self.spoken: list[str] = []
        self.cancelled = 0

    async def synthesize_stream(
        self, text: str, language: str, *, voice: str | None = None
    ) -> AsyncIterator[AudioChunk]:
        INJECTOR.check(self.provider_name)
        self.spoken.append(text)
        pcm = _voice_pcm(utterance_ms(text), seed=len(text) + 31, amplitude=0.26)
        for chunk in _chunks(pcm):
            yield chunk
            await asyncio.sleep(0)

    async def cancel(self) -> None:
        self.cancelled += 1


class MockLLMProvider(LLMProvider):
    """The text half of a composed pipeline.

    When the session carries a catalogue lesson plan it answers with the next
    planned step (see `planned_line`), which is what makes a composed language
    like Igbo demo the same lesson as a native realtime session. Tests that pass
    an explicit `reply` keep getting that exact text.
    """

    def __init__(self, vendor: str = "mock", reply: str = "Mock answer."):
        self.provider_name = vendor
        self.reply = reply
        self.calls: list[list[dict[str, str]]] = []
        self.tool_script: list[tuple[str, dict[str, Any]]] = []
        self._turns = 0
        self._greeted = False
        self._reported_section = ""
        self.dialogue = TutorDialogue()

    async def stream_reply(
        self,
        messages: list[dict[str, str]],
        *,
        system_instruction: str,
        language: str,
        tools: list[dict[str, Any]] | None = None,
        tool_handler: ToolHandler | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AsyncIterator[ProviderEvent]:
        INJECTOR.check(self.provider_name)
        self.calls.append(list(messages))
        if self._turns == 0 or self.dialogue.language != language:
            self.dialogue = TutorDialogue.from_metadata(metadata, language)
            _si = (metadata or {}).get("step_index") or 0
            try:
                _si = int(_si)
            except (TypeError, ValueError):
                _si = 0
            self._greeted = bool((metadata or {}).get("resumed")) or _si > 0
        self._turns += 1
        last = messages[-1].get("content", "") if messages else ""
        if not self.dialogue.planned:
            text = self.reply                       # explicit/generic reply: no plan to walk
        elif is_language_switch_prompt(last):
            text = self.dialogue.language_switch()
        elif not self._greeted:
            self._greeted = True
            text = self.dialogue.opening()
        else:
            text = self.dialogue.respond(_student_words(last))
        section = self.dialogue.current_section()
        if tool_handler and section and section.get("title") and section["title"] != self._reported_section:
            # Same `update_lesson_position` contract the realtime mock uses, so a
            # composed pipeline keeps the lesson position too — reported under the
            # catalogue's naming, exactly like the realtime path.
            self._reported_section = section["title"]
            with contextlib.suppress(Exception):
                await tool_handler(
                    "update_lesson_position",
                    {
                        "topic": self.dialogue.plan_topic or self.dialogue.topic,
                        "section": section.get("original_title") or section["title"],
                    },
                )
        for name, args in self.tool_script:
            if tool_handler:
                await tool_handler(name, args)
            yield ProviderEvent(type=ProviderEventType.TOOL_CALL, tool_name=name, tool_args=args)
        self.tool_script = []
        for piece in text.split(" "):
            yield ProviderEvent(type=ProviderEventType.OUTPUT_TRANSCRIPT, text=piece + " ", partial=True)
        yield ProviderEvent(type=ProviderEventType.TURN_COMPLETE, text=text)


class MockRAGProvider:
    """Stand-in for LERNA RAG in unit tests."""

    def __init__(self, evidence: list[dict[str, Any]] | None = None):
        self.evidence = evidence or [
            {
                "chunk_id": "mock-1",
                "text": "Binary search halves the search interval by comparing the target to the midpoint.",
                "source": "Lecture 4 - Searching",
                "score": 0.91,
                "trust_score": 0.95,
                "source_type": "student_upload",
            }
        ]
        self.queries: list[str] = []

    async def retrieve(self, query: str, **kwargs: Any):
        from app.rag.adapter import RetrievalResult, _normalise_evidence

        self.queries.append(query)
        return RetrievalResult(query=query, evidence=_normalise_evidence(self.evidence), available=True)


MockGeminiProvider = MockRealtimeProvider
MockElevenLabsProvider = MockRealtimeProvider
MockDeepgramProvider = MockRealtimeProvider
