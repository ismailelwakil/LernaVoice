"""Voice session orchestration: the heart of the service.

Owns one live conversation: provider connection, retry + failover with full
session continuity (§21), the event stream, tool dispatch into LERNA, and
persistence.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from typing import Any, AsyncIterator

from app.config import Settings, get_settings
from app.learner.orchestrator_adapter import OrchestratorAdapter
from app.learner.progress_adapter import ProgressProfileAdapter
from app.logging_setup import get_logger, session_id_var
from app.persistence.models import InteractionDoc, ProviderEventDoc, QuestionDoc
from app.persistence.repository import VoiceRepository, get_repository
from app.prompts.languages import interrupt_ack, validate_language
from app.prompts.resume import build_recap_prompt, build_resume_prompt
from app import curriculum
from app.prompts.interaction import build_language_switch_prompt
from app.prompts.languages import language_name
from app.prompts.system import OPENING_PROMPT, build_system_instruction
from app.providers.base import (
    AudioChunk,
    MalformedAudioError,
    ProviderError,
    ProviderEvent,
    ProviderEventType,
    ProviderUnsupportedError,
    RealtimeVoiceProvider,
    SessionConfig,
)
from app.providers.factory import ProviderFactory, get_factory
from app.rag.adapter import RAGAdapter
from app.voice.checkpoint_manager import CheckpointManager
from app.voice.events import ErrorCode, EventType, VoiceEvent, error_event, make_event
from app.voice.latency import (
    SPAN_INTERRUPT_TO_STOP,
    SPAN_PROVIDER_CONNECT,
    SPAN_RAG,
    SPAN_RESUME_TO_AUDIO,
    SPAN_SPEECH_TO_FIRST_AUDIO,
    LatencyTracker,
)
from app.voice.provider_router import PipelinePlan, UnsupportedLanguageError, VoiceProviderRouter
from app.learner.canonical_concepts import canonical_topic, canonicalise_concept
from app.learner.profiles import LearnerProfile, LearnerProfileStore, resolve_profile
from app.learning.explainer import ExplanationBrief, build_brief
from app.learning.levels import normalise_level
from app.voice.dialects import normalise_dialect
from app.voice.state import (
    InteractionRecord,
    LearningSignal,
    SessionState,
    StudentQuestionRecord,
    VisualPayload,
    VoiceSessionState,
)
from app.voice.tools import declarations_for

log = get_logger(__name__)

MAX_PCM_CHUNK = 1 << 20  # 1 MiB guard against malformed frames


class VoiceSession:
    """One live tutoring conversation."""

    def __init__(
        self,
        state: VoiceSessionState,
        *,
        repository: VoiceRepository,
        router: VoiceProviderRouter,
        factory: ProviderFactory,
        rag: RAGAdapter,
        progress: ProgressProfileAdapter,
        orchestrator: OrchestratorAdapter,
        settings: Settings,
        profiles: LearnerProfileStore | None = None,
    ):
        self.state = state
        #: The learner-profile store for this deployment (level lives here until
        #: LERNA's Progress Profile is wired in — see app/learner/profiles.py).
        self.profile_store = profiles
        self.repository = repository
        self.router = router
        self.factory = factory
        self.rag = rag
        self.progress = progress
        self.orchestrator = orchestrator
        self.settings = settings

        self.checkpoints = CheckpointManager(repository)
        self.latency = LatencyTracker()

        self.provider: RealtimeVoiceProvider | None = None
        self.plan: PipelinePlan | None = None
        self._pump: asyncio.Task | None = None
        self._subscribers: set[asyncio.Queue[VoiceEvent]] = set()
        self._seq = 0
        self._lock = asyncio.Lock()

        self._response_buffer: list[str] = []
        self._spoken_transcript: list[str] = []
        self._input_buffer: list[str] = []
        self._awaiting_first_audio = False
        self._in_question_mode = False
        self._failed_signatures: set[str] = set()
        self.retry_count = 0
        self.fallback_reason: str | None = None

        # The grounded, level-adapted explanation is decided when the session is
        # created, so /state can show what will be taught before the lesson starts.
        self._brief()
        self.learner_context: dict[str, Any] = {}
        self.last_evidence: list[dict[str, Any]] = []
        #: The level-adapted explanation brief this session teaches from.
        self.explanation: ExplanationBrief | None = None

    # ------------------------------------------------------------ event bus

    def subscribe(self) -> asyncio.Queue[VoiceEvent]:
        queue: asyncio.Queue[VoiceEvent] = asyncio.Queue(maxsize=1000)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[VoiceEvent]) -> None:
        self._subscribers.discard(queue)

    async def emit(self, event: VoiceEvent) -> None:
        self._seq += 1
        event.seq = self._seq
        event.session_id = self.state.session_id
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                log.warning("subscriber queue full; dropping event", extra={"event": event.event.value})

    async def _set_state(self, new_state: SessionState, **extra: Any) -> None:
        if self.state.state is new_state:
            return
        previous = self.state.state
        self.state.state = new_state
        self.state.touch()
        await self.emit(
            make_event(
                EventType.SESSION_STATE_CHANGED,
                from_state=previous.value,
                to_state=new_state.value,
                **extra,
            )
        )

    # ------------------------------------------------------------- lifecycle

    async def start(self, *, recap: bool | None = None) -> None:
        """Begin the session. `recap` defaults to True for a returning student."""
        if recap is None:
            recap = self.state.is_returning
        session_id_var.set(self.state.session_id)
        learner = await self.progress.get_context(self.state.student_id)
        self.learner_context = learner.as_prompt_context()
        self.learner_context["student_level"] = self.state.student_level
        self.learner_context["teaching_level"] = self._brief().style.instruction
        await self.orchestrator.register_modality(
            self.state.student_id, self.state.session_id, self.state.lesson_id
        )

        await self._connect(reason="initial_selection")
        await self.emit(
            make_event(
                EventType.SESSION_STARTED,
                student_id=self.state.student_id,
                language=self.state.language,
                course_id=self.state.course_id,
                lesson_id=self.state.lesson_id,
                state=self.state.state.value,
                pipeline=self.state.active_pipeline.model_dump(),
            )
        )

        if recap and self.state.resume_checkpoint:
            await self.emit(
                make_event(
                    EventType.SESSION_RECAP,
                    previous_session_id=self.state.previous_session_id,
                    topic=self.state.current_topic,
                    section=self.state.current_section,
                    concepts_covered=list(self.state.concepts_covered),
                    unresolved_questions=list(self.state.unresolved_questions),
                    checkpoint=self.state.resume_checkpoint.model_dump(),
                )
            )
            prompt = build_recap_prompt(
                language=self.state.language,
                summary=self.state.session_summary,
                checkpoint=self.state.resume_checkpoint.model_dump(),
                unresolved=self.state.unresolved_questions,
            )
        else:
            prompt = OPENING_PROMPT
            if self.state.current_topic:
                prompt = f"{OPENING_PROMPT}\nTopic to teach: {self.state.current_topic}."
        await self.emit_explanation_planned()
        await self._set_state(SessionState.THINKING)
        await self._send_text_to_provider(prompt)
        await self._persist()

    def _brief(self) -> ExplanationBrief:
        """The grounded, level-adapted explanation for this session's topic."""
        evidence = None
        if getattr(self.state, "document_ids", None):
            from app.rag import local_corpus
            query = self.state.current_topic or self.state.topic_id or ""
            chunks = local_corpus.retrieve(query, document_ids=self.state.document_ids, top_k=6)
            if chunks:
                evidence = list(chunks)
        brief = build_brief(
            topic_id=self.state.topic_id,
            topic_title=self.state.current_topic or None,
            language=self.state.language,
            level=self.state.student_level,
            plan=list(self.state.lesson_plan),
            evidence=evidence,
        )
        self.explanation = brief
        self.state.explanation = brief.as_dict()
        return brief

    async def emit_explanation_planned(self) -> None:
        """Publish what the tutor is teaching from: the level, moves and sources."""
        brief = self._brief()
        await self.emit(
            make_event(
                EventType.EXPLANATION_PLANNED,
                topic_id=brief.topic_id,
                topic=brief.topic,
                level=brief.level,
                language=brief.language,
                grounding=brief.grounding,
                teaching_order=[
                    "picture" if m.kind == "hook" else m.kind for m in brief.moves
                ],
                move_count=len(brief.moves),
                sources=[s.as_dict() for s in brief.sources],
                sources_used=[s.publisher for s in brief.sources],
            )
        )

    async def change_level(self, level: str) -> dict[str, Any]:
        """Explain the same lesson for a different level; learning state untouched."""
        previous = self.state.student_level
        new_level = normalise_level(level, previous)
        self.state.student_level = new_level
        if self.profile_store is not None:
            self.profile_store.upsert(self.state.student_id, level=new_level)
        if self.learner_context:
            self.learner_context["student_level"] = new_level
        self.state.touch()
        await self.emit_explanation_planned()
        await self._persist()
        return {
            "session_id": self.state.session_id,
            "student_level": new_level,
            "previous_level": previous,
            "changed": new_level != previous,
            "topic_id": self.state.topic_id,
            "concepts_covered": list(self.state.concepts_covered),
        }

    async def _build_session_config(self) -> SessionConfig:
        checkpoint = self.state.resume_checkpoint.model_dump() if self.state.resume_checkpoint else None
        lesson_context = {
            "course_id": self.state.course_id,
            "lesson_id": self.state.lesson_id,
            "topic": self.state.current_topic,
            "section": self.state.current_section,
            "lesson_plan": [
                f"{i + 1}. {step['title']} — {step.get('goal', '')}"
                for i, step in enumerate(self.state.lesson_plan)
            ]
            or None,
            "concepts_already_covered": self.state.concepts_covered,
        }
        if self.state.lesson_plan:
            lesson_context["teaching_instruction"] = (
                "Teach the plan in order, one step at a time, checking understanding "
                "between steps. Do not restart a step the student already understood. "
                f"Express every step in {language_name(self.state.language)} — the step "
                "titles and goals above are a sketch of the content, not a script to read "
                "out, and they are written in English only as the plan's own wording. "
                "Never read this plan aloud."
            )
        brief = self._brief()
        if self.learner_context:
            self.learner_context["student_level"] = self.state.student_level
        instruction = build_system_instruction(
            language=self.state.language,
            dialect=self.state.dialect,
            lesson_context=lesson_context,
            learner_context=self.learner_context,
            checkpoint=checkpoint,
            extra=brief.prompt_block() if brief.moves else None,
        )
        initial_context = self._conversation_context()
        return SessionConfig(
            session_id=self.state.session_id,
            language=self.state.language,
            system_instruction=instruction,
            voice_name=self.settings.gemini_voice_name,
            input_sample_rate=self.settings.input_sample_rate,
            output_sample_rate=self.settings.output_sample_rate,
            tools=declarations_for(self.state.language),
            initial_context=initial_context,
            metadata={
                "student_id": self.state.student_id,
                "dialect": self.state.dialect,
                "topic_id": self.state.topic_id,
                "topic_title": self.state.current_topic,
                "student_level": self.state.student_level,
                "step_index": self._plan_position(),
                # True on the 2nd+ provider connect of this session (a failover or
                # reconnect). The provider uses it to *continue* the lesson instead of
                # greeting and re-explaining from the top (round 23 repeat fix).
                "resumed": self._next_connect_is_resume(),
                "sections": list(self.state.lesson_plan),
                # The offline mock teaches the same grounded brief, level and all.
                "explanation": brief.as_dict(),
            },
        )

    def _next_connect_is_resume(self) -> bool:
        """First connect of a session is fresh; every later one is a reconnect."""
        already = getattr(self, "_provider_connects", 0)
        self._provider_connects = already + 1
        return already > 0

    def _plan_position(self) -> int:
        """Which plan step we are on, so a reconnect resumes instead of restarting."""
        title = self.state.current_section or ""
        for index, step in enumerate(self.state.lesson_plan):
            if step.get("title") == title:
                return index
        return 0

    def _conversation_context(self) -> list[dict[str, str]]:
        """Replayed into a new provider so a failover keeps the thread (§21)."""
        context: list[dict[str, str]] = []
        for record in self.state.interactions[-12:]:
            if record.role == "system":
                continue
            context.append(
                {"role": "user" if record.role == "student" else "assistant", "content": record.text}
            )
        return context

    # -------------------------------------------------------- provider mgmt

    def preview_planned_pipeline(self) -> None:
        """Publish the pipeline this language *will* route to, before connect.

        Without this a fresh session reports the ActivePipeline defaults, which
        for a composed language like Igbo claims `realtime:gemini` until the
        handshake completes — the dev panel would contradict /voice/languages.
        """
        try:
            plan = self.router.select_pipeline(self.state.language, exclude=self._failed_signatures)
        except Exception:
            return
        self.state.active_pipeline = plan.pipeline

    async def _connect(self, *, reason: str) -> None:
        """Select a pipeline and connect, retrying then failing over (§18-§20)."""
        language = self.state.language
        attempts = 0
        last_error: Exception | None = None

        while True:
            try:
                plan = self.router.select_pipeline(language, exclude=self._failed_signatures)
            except UnsupportedLanguageError as exc:
                if self._failed_signatures:
                    # The language IS supported — we simply ran out of pipelines because
                    # every available one failed to connect (outage / quota / auth). Fall
                    # through to the honest "no provider could be reached" error below
                    # instead of telling the student their language is unsupported.
                    break
                await self.emit(
                    error_event(
                        ErrorCode.VOICE_LANGUAGE_UNSUPPORTED,
                        str(exc),
                        recoverable=False,
                        session_id=self.state.session_id,
                    )
                )
                await self._set_state(SessionState.ERROR)
                raise

            await self.emit(make_event(EventType.PROVIDER_SELECTED, **{**plan.as_dict(), "reason": reason}))
            await self._record_provider_event("selected", plan=plan, reason=reason)

            for attempt in range(self.settings.voice_max_retries + 1):
                attempts += 1
                try:
                    self.latency.start(SPAN_PROVIDER_CONNECT)
                    provider = self.factory.build_pipeline(plan.pipeline)
                    provider.set_tool_handler(self._handle_tool)
                    config = await self._build_session_config()
                    await asyncio.wait_for(
                        provider.start_session(config), timeout=self.settings.voice_provider_timeout
                    )
                    connect_ms = self.latency.stop(SPAN_PROVIDER_CONNECT)

                    await self._teardown_provider()
                    self.provider = provider
                    self.plan = plan
                    transition = self.state.switch_pipeline(plan.pipeline, reason)
                    self.router.record_success(plan)
                    self.retry_count = attempt
                    self._pump = asyncio.create_task(self._pump_events())

                    await self.emit(
                        make_event(
                            EventType.PROVIDER_CONNECTED,
                            **{**plan.as_dict(), "connect_ms": connect_ms, "retry_count": attempt},
                        )
                    )
                    if transition.from_pipeline and transition.from_pipeline != transition.to_pipeline:
                        await self.emit(
                            make_event(
                                EventType.PROVIDER_SWITCHED,
                                **{"from": transition.from_pipeline},
                                to=transition.to_pipeline,
                                reason=reason,
                            )
                        )
                        await self._record_provider_event("switched", plan=plan, reason=reason)
                    await self._record_provider_event("connected", plan=plan, reason=reason)
                    await self._persist()
                    return

                except Exception as exc:
                    self.latency.stop_if_open(SPAN_PROVIDER_CONNECT)
                    last_error = exc
                    error = exc if isinstance(exc, ProviderError) else None
                    vendor = (error.provider if error else plan.providers[0]) or "unknown"
                    self.router.record_failure(vendor, exc)
                    await self.emit(
                        make_event(
                            EventType.PROVIDER_FAILED,
                            provider=vendor,
                            pipeline=plan.signature,
                            error_class=getattr(error, "error_class", None)
                            and error.error_class.value,
                            message=str(exc)[:300],
                            attempt=attempt,
                        )
                    )
                    await self._record_provider_event(
                        "failed", plan=plan, reason=str(exc)[:200], retry_count=attempt
                    )
                    retryable = error.retryable if error else True
                    if retryable and attempt < self.settings.voice_max_retries:
                        delay = self.settings.voice_retry_backoff * (2**attempt)
                        await self.emit(
                            make_event(
                                EventType.PROVIDER_RETRYING,
                                provider=vendor,
                                attempt=attempt + 1,
                                delay_s=round(delay, 2),
                            )
                        )
                        await asyncio.sleep(delay)
                        continue
                    break

            # pipeline exhausted -> failover
            self._failed_signatures.add(plan.signature)
            self.fallback_reason = _reason_for(last_error)
            if not self.settings.voice_fallback_enabled:
                break
            remaining = self.router.plan_pipelines(language, exclude=self._failed_signatures)
            if not remaining:
                break
            await self.emit(
                make_event(
                    EventType.PROVIDER_FALLBACK_STARTED,
                    failed_pipeline=plan.signature,
                    reason=self.fallback_reason,
                    next_pipeline=remaining[0].signature,
                )
            )
            await self._record_provider_event("fallback_started", plan=plan, reason=self.fallback_reason)
            reason = f"fallback:{self.fallback_reason}"

        await self._set_state(SessionState.ERROR)
        code = _error_code_for(last_error)
        hint = _hint_for(last_error)
        message = "No voice provider could be reached."
        if hint:
            message = f"{message} {hint}"
        await self.emit(
            error_event(
                code,
                message,
                recoverable=code is not ErrorCode.VOICE_PROVIDER_AUTH_FAILED,
                session_id=self.state.session_id,
                attempts=attempts,
                hint=hint,
                detail=str(last_error)[:300] if last_error else None,
            )
        )
        raise last_error or RuntimeError("no voice provider available")

    async def _teardown_provider(self) -> None:
        if self._pump:
            self._pump.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._pump
            self._pump = None
        if self.provider is not None:
            with contextlib.suppress(Exception):
                await self.provider.close_session()
            self.provider = None

    async def _failover(self, error: Exception) -> bool:
        """Mid-session provider death: move to the next pipeline, keep context."""
        if not self.settings.voice_fallback_enabled:
            return False
        if self.plan:
            self._failed_signatures.add(self.plan.signature)
        self.fallback_reason = _reason_for(error)
        try:
            await self._connect(reason=f"mid_session_failover:{self.fallback_reason}")
            # Nudge the new provider to carry on seamlessly.
            if self._in_question_mode and self.state.open_questions():
                pending = self.state.open_questions()[-1]
                await self._send_text_to_provider(
                    f"Continue answering the student's question: \"{pending.text}\". "
                    "Do not restart the lesson and do not mention any technical issue."
                )
            return True
        except Exception:
            return False

    # ------------------------------------------------------------ event pump

    async def _pump_events(self) -> None:
        assert self.provider is not None
        provider = self.provider
        try:
            async for event in provider.receive_events():
                await self._handle_provider_event(event)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await self._on_provider_error(exc)

    async def _handle_provider_event(self, event: ProviderEvent) -> None:
        etype = event.type

        if etype is ProviderEventType.CONNECTED:
            return

        if etype is ProviderEventType.INPUT_TRANSCRIPT and event.text:
            await self.emit(
                make_event(EventType.INPUT_TRANSCRIPT, text=event.text, partial=event.partial)
            )
            if not event.partial:
                self._input_buffer.append(event.text)
                await self._record_student_turn(event.text)
            return

        if etype is ProviderEventType.OUTPUT_TRANSCRIPT and event.text:
            if not self._response_buffer:
                await self.emit(make_event(EventType.ASSISTANT_RESPONSE_STARTED))
            self._response_buffer.append(event.text)
            await self.emit(make_event(EventType.ASSISTANT_TEXT_DELTA, text=event.text))
            return

        if etype is ProviderEventType.AUDIO and event.audio:
            if self._awaiting_first_audio:
                ms = self.latency.stop_if_open(SPAN_SPEECH_TO_FIRST_AUDIO)
                self.latency.stop_if_open(SPAN_RESUME_TO_AUDIO)
                self._awaiting_first_audio = False
                if ms is not None:
                    await self.emit(make_event(EventType.LATENCY, span=SPAN_SPEECH_TO_FIRST_AUDIO, ms=ms))
            await self._set_state(SessionState.ANSWERING if self._in_question_mode else SessionState.SPEAKING)
            import base64

            await self.emit(
                make_event(
                    EventType.ASSISTANT_AUDIO_CHUNK,
                    audio=base64.b64encode(event.audio).decode("ascii"),
                    encoding="pcm_s16le",
                    sample_rate=self.settings.output_sample_rate,
                )
            )
            return

        if etype is ProviderEventType.INTERRUPTED:
            await self.emit(make_event(EventType.ASSISTANT_INTERRUPTED, source="provider"))
            return

        if etype is ProviderEventType.TURN_COMPLETE:
            await self._finish_turn(event.text)
            return

        if etype is ProviderEventType.ERROR and event.error is not None:
            await self._on_provider_error(event.error)
            return

        if etype is ProviderEventType.CLOSED:
            if self.state.state not in (SessionState.ENDED, SessionState.PAUSED):
                await self._on_provider_error(
                    ProviderError("provider connection closed unexpectedly", provider=self.provider_name)
                )
            return

    async def _finish_turn(self, final_text: str | None) -> None:
        text = (final_text or "".join(self._response_buffer)).strip()
        self._response_buffer = []
        if text:
            self._spoken_transcript.append(text)
            await self._record_tutor_turn(text)
        await self.emit(
            make_event(
                EventType.ASSISTANT_RESPONSE_COMPLETED,
                text=text,
                pipeline=self.state.active_pipeline.signature(),
            )
        )
        if self._in_question_mode:
            pending = self.state.open_questions()
            if pending:
                question = pending[-1]
                question.answered = True
                question.answer = text
                question.answered_at = time.time()
                self.state.unresolved_questions = [
                    q for q in self.state.unresolved_questions if q != question.text
                ]
                await self._persist_question(question)
                await self.emit(
                    make_event(
                        EventType.QUESTION_COMPLETED,
                        question_id=question.question_id,
                        question=question.text,
                    )
                )
            await self._set_state(SessionState.LISTENING)
        else:
            await self._set_state(SessionState.LISTENING)
        await self._persist()

    async def _on_provider_error(self, exc: Exception) -> None:
        error = exc if isinstance(exc, ProviderError) else ProviderError(str(exc), provider=self.provider_name)
        self.router.record_failure(error.provider or self.provider_name, error)
        await self.emit(
            make_event(
                EventType.PROVIDER_FAILED,
                provider=error.provider,
                pipeline=self.state.active_pipeline.signature(),
                error_class=error.error_class.value,
                message=str(error)[:300],
            )
        )
        await self._record_provider_event("failed", reason=str(error)[:200])
        if await self._failover(error):
            return
        await self._set_state(SessionState.ERROR)
        hint = _hint_for(error)
        message = "Voice service is temporarily unavailable."
        if hint:
            # A configuration problem, not a transient one: say what to do about it.
            message = f"{message} {hint}"
        await self.emit(
            error_event(
                _error_code_for(error),
                message,
                recoverable=True,
                session_id=self.state.session_id,
                hint=hint,
                detail=str(error)[:300],
            )
        )

    @property
    def provider_name(self) -> str:
        return self.state.active_pipeline.signature()

    # ----------------------------------------------------------- student I/O

    async def send_audio(self, data: bytes) -> None:
        if not data:
            return
        if len(data) > MAX_PCM_CHUNK or len(data) % 2 != 0:
            raise MalformedAudioError("audio frame is not 16-bit PCM or is too large", provider="client")
        if self.provider is None:
            raise RuntimeError("session has no active provider")
        if self.state.state in (SessionState.PAUSED, SessionState.ENDED):
            return
        if self.state.state in (SessionState.LISTENING, SessionState.IDLE, SessionState.INTERRUPTED):
            if not self.latency.is_open(SPAN_SPEECH_TO_FIRST_AUDIO):
                self.latency.start(SPAN_SPEECH_TO_FIRST_AUDIO)
                self._awaiting_first_audio = True
        try:
            await self.provider.send_audio(
                AudioChunk(data=data, sample_rate=self.settings.input_sample_rate)
            )
        except Exception as exc:
            await self._on_provider_error(exc)

    async def _send_text_to_provider(self, text: str) -> None:
        if self.provider is None:
            raise RuntimeError("session has no active provider")
        self.latency.start(SPAN_SPEECH_TO_FIRST_AUDIO)
        self._awaiting_first_audio = True
        try:
            await self.provider.send_text(text)
        except Exception as exc:
            await self._on_provider_error(exc)

    async def send_text(self, text: str) -> None:
        """Typed student turn (used by the Streamlit client and by tests)."""
        await self._record_student_turn(text)
        await self._set_state(SessionState.THINKING)
        await self._send_text_to_provider(text)

    # ------------------------------------------------------- interrupt flow

    async def interrupt(self, *, source: str = "student") -> dict[str, Any]:
        """§23: stop now, checkpoint, switch to question mode."""
        async with self._lock:
            self.latency.start(SPAN_INTERRUPT_TO_STOP)
            # 1+2. Tell the client to stop playback immediately, then cancel the
            #      provider. The client never waits for the provider.
            await self.emit(make_event(EventType.ASSISTANT_INTERRUPTED, source=source, stop_playback=True))
            stop_ms = self.latency.stop(SPAN_INTERRUPT_TO_STOP)
            await self.emit(make_event(EventType.LATENCY, span=SPAN_INTERRUPT_TO_STOP, ms=stop_ms))

            if self.provider is not None:
                with contextlib.suppress(Exception):
                    await self.provider.interrupt()

            # 3+4. Capture logical lesson state.
            partial = "".join(self._response_buffer).strip()
            if partial:
                self._spoken_transcript.append(partial)
                self._response_buffer = []
            checkpoint = await self.checkpoints.create(
                self.state, spoken_transcript="\n".join(self._spoken_transcript), reason=f"interrupt:{source}"
            )
            self.state.interrupt_count += 1
            await self.emit(
                make_event(
                    EventType.CHECKPOINT_CREATED,
                    checkpoint=checkpoint.model_dump(),
                    interrupt_count=self.state.interrupt_count,
                )
            )

            # 5+6. Interrupted / listening, and invite the question.
            self._in_question_mode = True
            await self._set_state(SessionState.INTERRUPTED)
            ack = interrupt_ack(self.state.language)
            await self.emit(make_event(EventType.QUESTION_STARTED, prompt=ack, language=self.state.language))
            self.state.record_interaction(
                InteractionRecord(role="tutor", text=ack, language=self.state.language, kind="system")
            )
            await self._persist()
            return {"checkpoint": checkpoint.model_dump(), "acknowledgement": ack, "stop_ms": stop_ms}

    async def ask_question(self, text: str, *, is_followup: bool | None = None) -> StudentQuestionRecord:
        """§23.7/§25: answer with lesson context + RAG, support follow-ups."""
        prior = [q.text for q in self.state.student_questions if q.answered]
        if is_followup is None:
            is_followup = self._in_question_mode and bool(self.state.student_questions)

        record = StudentQuestionRecord(
            text=text,
            language=self.state.language,
            is_followup=bool(is_followup),
            parent_question_id=self.state.student_questions[-1].question_id
            if is_followup and self.state.student_questions
            else None,
        )
        self.state.student_questions.append(record)
        self.state.unresolved_questions.append(text)
        self._in_question_mode = True
        await self._persist_question(record)
        await self._record_student_turn(text, kind="question")
        await self.emit(
            make_event(
                EventType.QUESTION_STARTED,
                question_id=record.question_id,
                question=text,
                is_followup=record.is_followup,
            )
        )
        await self._set_state(SessionState.THINKING)

        evidence_block = await self._retrieve_for_question(text)
        from app.prompts.interruption import build_question_prompt

        prompt = build_question_prompt(
            question=text,
            language=self.state.language,
            checkpoint=self.state.resume_checkpoint.model_dump() if self.state.resume_checkpoint else None,
            prior_questions=prior,
            is_followup=record.is_followup,
        )
        if evidence_block:
            prompt = f"{prompt}\n\n{evidence_block}"
        await self._send_text_to_provider(prompt)
        return record

    async def _retrieve_for_question(self, question: str) -> str:
        self.latency.start(SPAN_RAG)
        result = await self.rag.retrieve(
            question,
            student_id=self.state.student_id,
            course_id=self.state.course_id,
            lesson_id=self.state.lesson_id,
            topic=self.state.current_topic,
            topic_id=self.state.topic_id,
            document_ids=self.state.document_ids,
        )
        ms = self.latency.stop(SPAN_RAG)
        self.last_evidence = [e.as_dict() for e in result.evidence]
        await self.emit(
            make_event(
                EventType.RAG_RETRIEVED,
                query=question,
                available=result.available,
                count=len(result.evidence),
                evidence=self.last_evidence[:4],
                ms=ms,
            )
        )
        if not result.available and not result.evidence:
            await self.emit(
                error_event(
                    ErrorCode.VOICE_RAG_UNAVAILABLE,
                    "Course materials could not be searched; answering from the lesson's "
                    "vetted sources only.",
                    recoverable=True,
                    session_id=self.state.session_id,
                )
            )
        return result.as_prompt_block()

    # ---------------------------------------------------------- resume flow

    async def resume(self, *, language_switch: bool = False) -> dict[str, Any]:
        """§26: continue from the checkpoint, never restart.

        `language_switch=True` (set by `change_language`) makes the prompt carry the
        switch instruction as well, so the very next thing the student hears is the
        new language.
        """
        async with self._lock:
            checkpoint = self.state.resume_checkpoint
            self.latency.start(SPAN_RESUME_TO_AUDIO)
            await self.emit(
                make_event(
                    EventType.RESUME_STARTED,
                    checkpoint=checkpoint.model_dump() if checkpoint else None,
                )
            )
            await self._set_state(SessionState.RESUMING)
            self._in_question_mode = False
            self.state.resume_count += 1

            answered = [q.text for q in self.state.student_questions if q.answered]
            prompt = build_resume_prompt(
                language=self.state.language,
                checkpoint=checkpoint.model_dump() if checkpoint else None,
                answered_questions=answered,
                language_switch=language_switch,
            )
            await self._send_text_to_provider(prompt)
            await self.emit(make_event(EventType.RESUME_COMPLETED, resume_count=self.state.resume_count))
            await self._persist()
            return {"resumed_from": checkpoint.model_dump() if checkpoint else None}

    # ------------------------------------------------------ language change

    async def change_language(
        self, language: str, dialect: str | None = None
    ) -> dict[str, Any]:
        """§45: new language, new pipeline if needed, same lesson state.

        `language` may also name an Arabic register — `ar-MSA`, or an older
        Egyptian spelling such as `ar-EG` / `egyptian`. Every spelling resolves to
        the formal register, so an older client is answered in fusHa rather than
        failing, and the session stays `ar` for routing and learning state.
        """
        raw = (language or "").strip()
        register = raw.split("-", 1)[1] if ("-" in raw and raw.lower().startswith("ar")) else None
        base = raw.split("-", 1)[0] if register else raw
        new_language = validate_language(base)
        new_dialect = normalise_dialect(new_language, dialect or register)
        if new_language == self.state.language and (new_dialect or None) == (self.state.dialect or None):
            return {"language": new_language, "dialect": self.state.dialect, "changed": False}
        previous = self.state.language
        previous_dialect = self.state.dialect
        self.state.language = new_language
        self.state.dialect = new_dialect
        self._failed_signatures.clear()
        self.state.record_interaction(
            InteractionRecord(
                role="system",
                text=(
                    f"language changed {previous} -> {new_language}"
                    + (f" ({previous_dialect} -> {new_dialect})" if new_dialect != previous_dialect else "")
                ),
                language=new_language,
                kind="system",
            )
        )
        await self._connect(reason=f"language_change:{previous}->{new_language}")
        await self.emit(
            make_event(
                EventType.LANGUAGE_CHANGED,
                **{"from": previous},
                to=new_language,
                dialect=new_dialect,
                previous_dialect=previous_dialect,
                pipeline=self.state.active_pipeline.model_dump(),
                checkpoint_preserved=self.state.resume_checkpoint is not None,
            )
        )
        # Speak in the new language immediately. Reconnecting alone produces no audio
        # until the student speaks again, so they keep hearing the old language and the
        # switch looks broken. With a checkpoint we resume (in the new language, tagged
        # as a switch); without one we ask for a one-line acknowledgement.
        if self.state.resume_checkpoint:
            await self.resume(language_switch=True)
        else:
            await self._send_text_to_provider(
                build_language_switch_prompt(
                    new_language,
                    section=self.state.current_section or "",
                    topic=self.state.current_topic or "",
                )
            )
        await self._persist()
        return {"language": new_language, "dialect": new_dialect, "changed": True}

    # ----------------------------------------------------------- pause / end

    async def pause(self) -> None:
        await self._set_state(SessionState.PAUSED)
        if self.provider is not None:
            with contextlib.suppress(Exception):
                await self.provider.interrupt()
        await self.emit(make_event(EventType.SESSION_PAUSED))
        await self._persist()

    async def unpause(self) -> None:
        if self.state.state is not SessionState.PAUSED:
            return
        await self._set_state(SessionState.LISTENING)
        await self.emit(make_event(EventType.SESSION_RESUMED))

    async def end(self, reason: str = "client_request") -> None:
        if self.state.state is SessionState.ENDED:
            return
        partial = "".join(self._response_buffer).strip()
        if partial:
            self._spoken_transcript.append(partial)
        if self._spoken_transcript:
            await self.checkpoints.create(
                self.state, spoken_transcript="\n".join(self._spoken_transcript), reason="session_end"
            )
        self.state.session_summary = self._build_summary()
        self.state.next_action = (
            self.state.resume_checkpoint.next_concept or self.state.resume_checkpoint.resume_instruction
            if self.state.resume_checkpoint
            else ""
        )
        self.state.ended_at = time.time()
        await self._set_state(SessionState.ENDED)
        await self._teardown_provider()
        await self.emit(make_event(EventType.SESSION_ENDED, reason=reason, summary=self.state.session_summary))
        await self._persist()

    def _build_summary(self) -> str:
        parts = []
        if self.state.current_topic:
            parts.append(f"Topic: {self.state.current_topic}.")
        if self.state.concepts_covered:
            parts.append("Covered: " + ", ".join(self.state.concepts_covered[:10]) + ".")
        answered = [q.text for q in self.state.student_questions if q.answered]
        if answered:
            parts.append(f"Answered {len(answered)} question(s), latest: {answered[-1]}")
        if self.state.unresolved_questions:
            parts.append("Still open: " + "; ".join(self.state.unresolved_questions[:3]) + ".")
        if self.state.resume_checkpoint and self.state.resume_checkpoint.next_concept:
            parts.append(f"Next: {self.state.resume_checkpoint.next_concept}.")
        return " ".join(parts) or self.state.session_summary

    # ------------------------------------------------------------- tool call

    def _canonical_concept(self, text: str):
        """English storage for something said in any language (app/learner/canonical_concepts.py)."""
        return canonicalise_concept(text, language=self.state.language, topic_id=self.state.topic_id)

    async def _handle_tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        try:
            if name == "search_course_materials":
                query = str(args.get("query", "")).strip()
                block = await self._retrieve_for_question(query)
                return {"evidence": self.last_evidence[:6], "guidance": block}

            if name == "show_visual":
                visual = VisualPayload(
                    type=args.get("type", "text"),
                    content=str(args.get("content", "")),
                    language=args.get("language"),
                    caption=args.get("caption"),
                )
                await self.emit(make_event(EventType.VISUAL_UPDATED, visual=visual.model_dump()))
                return {"status": "displayed"}

            if name == "record_learning_signal":
                # The tutor teaches in the session language; the profile is English.
                concept = self._canonical_concept(str(args.get("concept", "")))
                signal = LearningSignal(
                    kind=args.get("kind", "concept_discussed"),
                    concept=concept.canonical or str(args.get("concept", "")),
                    detail=args.get("detail"),
                    confidence=float(args.get("confidence", 0.5) or 0.5),
                    spoken_as=concept.spoken if concept.spoken != concept.canonical else None,
                    language=self.state.language,
                    canonical=concept.resolved,
                    catalogue_ref=concept.catalogue_ref,
                )
                self.state.learning_signals.append(signal)
                if signal.kind in ("concept_discussed", "concept_completed", "concept_understood"):
                    self.state.add_concept(signal.concept)
                if signal.kind == "misconception_detected" and signal.concept not in self.state.misconceptions:
                    self.state.misconceptions.append(signal.concept)
                written = await self.progress.record_signal(
                    self.state.student_id, signal, session_id=self.state.session_id
                )
                await self.emit(
                    make_event(
                        EventType.LEARNING_SIGNAL, **signal.model_dump(), persisted_to_profile=written
                    )
                )
                return {"status": "recorded", "progress_profile_updated": written}

            if name == "update_lesson_position":
                self.state.current_topic = canonical_topic(
                    self.state.topic_id, str(args.get("topic") or self.state.current_topic)
                )
                self.state.current_section = args.get("section") or self.state.current_section
                if args.get("last_concept"):
                    self.state.add_concept(self._canonical_concept(str(args["last_concept"])).canonical)
                if self.state.resume_checkpoint and args.get("next_concept"):
                    self.state.resume_checkpoint.next_concept = self._canonical_concept(
                        str(args["next_concept"])
                    ).canonical
                self.state.touch()
                return {"status": "updated"}

            return {"error": f"unknown tool '{name}'"}
        except Exception as exc:
            log.warning("tool call failed", extra={"tool": name, "error_type": type(exc).__name__})
            return {"error": f"{type(exc).__name__}"}

    # ----------------------------------------------------------- persistence

    async def _record_student_turn(self, text: str, kind: str = "lesson") -> None:
        record = InteractionRecord(
            role="student",
            text=text,
            language=self.state.language,
            pipeline=self.state.active_pipeline.signature(),
            kind=kind,
        )
        self.state.record_interaction(record)
        await self._persist_interaction(record)

    async def _record_tutor_turn(self, text: str) -> None:
        record = InteractionRecord(
            role="tutor",
            text=text,
            language=self.state.language,
            pipeline=self.state.active_pipeline.signature(),
            kind="answer" if self._in_question_mode else "lesson",
        )
        self.state.record_interaction(record)
        await self._persist_interaction(record)

    async def _persist_interaction(self, record: InteractionRecord) -> None:
        if not self.settings.voice_store_transcripts:
            return
        with contextlib.suppress(Exception):
            await self.repository.append_interaction(
                InteractionDoc(
                    session_id=self.state.session_id,
                    student_id=self.state.student_id,
                    interaction_id=record.interaction_id,
                    role=record.role,
                    kind=record.kind,
                    text=record.text,
                    language=record.language,
                    pipeline=record.pipeline,
                    timestamp=record.ts,
                )
            )

    async def _persist_question(self, record: StudentQuestionRecord) -> None:
        with contextlib.suppress(Exception):
            await self.repository.upsert_question(
                QuestionDoc(
                    session_id=self.state.session_id,
                    student_id=self.state.student_id,
                    question_id=record.question_id,
                    text=record.text,
                    language=record.language,
                    answered=record.answered,
                    answer=record.answer,
                    is_followup=record.is_followup,
                    parent_question_id=record.parent_question_id,
                    evidence_ids=record.evidence_ids,
                    asked_at=record.asked_at,
                    answered_at=record.answered_at,
                )
            )

    async def _record_provider_event(
        self,
        kind: str,
        *,
        plan: PipelinePlan | None = None,
        reason: str | None = None,
        retry_count: int = 0,
    ) -> None:
        with contextlib.suppress(Exception):
            await self.repository.append_provider_event(
                ProviderEventDoc(
                    session_id=self.state.session_id,
                    student_id=self.state.student_id,
                    kind=kind,
                    from_pipeline=self.state.active_pipeline.signature(),
                    to_pipeline=plan.signature if plan else None,
                    provider=plan.providers[0] if plan else None,
                    reason=reason,
                    retry_count=retry_count,
                )
            )

    async def _persist(self) -> None:
        with contextlib.suppress(Exception):
            await self.repository.save_session(self.state)

    # --------------------------------------------------------- introspection

    def diagnostics(self) -> dict[str, Any]:
        return {
            "session_id": self.state.session_id,
            "state": self.state.state.value,
            "language": self.state.language,
            "pipeline": self.state.active_pipeline.model_dump(),
            "active_provider": self.state.active_pipeline.signature(),
            "retry_count": self.retry_count,
            "fallback_reason": self.fallback_reason,
            "failed_pipelines": sorted(self._failed_signatures),
            "interrupt_count": self.state.interrupt_count,
            "resume_count": self.state.resume_count,
            "checkpoint": self.state.resume_checkpoint.model_dump() if self.state.resume_checkpoint else None,
            "latency": self.latency.snapshot(),
            "provider_health": self.router.health.snapshot(),
            "questions": len(self.state.student_questions),
            "unresolved": list(self.state.unresolved_questions),
        }


def _hint_for(error: Exception | None) -> str | None:
    """A configuration hint for the client, when the failure is 'you set this up wrong'."""
    if error is None:
        return None
    from app.config import get_settings
    from app.providers.hints import setup_hint

    return setup_hint(str(error), project=get_settings().google_cloud_project)


def _reason_for(error: Exception | None) -> str:
    if error is None:
        return "UNKNOWN"
    if isinstance(error, ProviderError):
        return error.error_class.value.upper()
    return type(error).__name__.upper()


def _error_code_for(error: Exception | None) -> ErrorCode:
    from app.providers.base import (
        ErrorClass,
        ProviderAuthError,
        ProviderQuotaError,
        ProviderRateLimitError,
        ProviderTimeoutError,
    )

    if isinstance(error, ProviderAuthError):
        return ErrorCode.VOICE_PROVIDER_AUTH_FAILED
    if isinstance(error, ProviderRateLimitError):
        return ErrorCode.VOICE_PROVIDER_RATE_LIMITED
    if isinstance(error, ProviderQuotaError):
        return ErrorCode.VOICE_PROVIDER_QUOTA_EXHAUSTED
    if isinstance(error, ProviderTimeoutError):
        return ErrorCode.VOICE_PROVIDER_TIMEOUT
    if isinstance(error, ProviderUnsupportedError):
        return ErrorCode.VOICE_CAPABILITY_UNSUPPORTED
    if isinstance(error, ProviderError) and error.error_class is ErrorClass.UNSUPPORTED:
        return ErrorCode.VOICE_CAPABILITY_UNSUPPORTED
    return ErrorCode.VOICE_PROVIDER_UNAVAILABLE


# --------------------------------------------------------------------------- #
# manager
# --------------------------------------------------------------------------- #


class VoiceSessionManager:
    """Creates, caches, restores and disposes voice sessions."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        repository: VoiceRepository | None = None,
        router: VoiceProviderRouter | None = None,
        factory: ProviderFactory | None = None,
        rag: RAGAdapter | None = None,
        progress: ProgressProfileAdapter | None = None,
        orchestrator: OrchestratorAdapter | None = None,
        profiles: LearnerProfileStore | None = None,
    ):
        self.settings = settings or get_settings()
        self.repository = repository or get_repository(self.settings)
        self.router = router or VoiceProviderRouter(settings=self.settings)
        self.factory = factory or get_factory(self.settings)
        self.rag = rag or RAGAdapter(settings=self.settings)
        self.progress = progress or ProgressProfileAdapter()
        self.orchestrator = orchestrator or OrchestratorAdapter()
        #: Where the student's level lives until LERNA's profile is wired in. The
        #: default is memory-only (tests stay hermetic); the running service hands
        #: in the file-backed store from app.main.
        self.profiles = profiles if profiles is not None else LearnerProfileStore(None)
        self._sessions: dict[str, VoiceSession] = {}

    async def resolve_profile(
        self, student_id: str, requested_level: str | None = None
    ) -> LearnerProfile:
        """Request > LERNA Progress Profile > local store > default."""
        stored = self.profiles.get(student_id) if self.profiles else None
        lerna: dict[str, Any] | None = None
        try:
            context = await self.progress.get_context(student_id)
            lerna = {
                "level": context.level,
                "name": context.name,
                "preferred_language": context.preferred_language,
                "available": context.available,
                "note": context.note,
            }
        except Exception as exc:  # a profile read must never block a lesson
            log.warning("profile lookup failed", extra={"error_type": type(exc).__name__})
        return resolve_profile(
            student_id, stored=stored, lerna=lerna, requested_level=requested_level
        )

    def _wrap(self, state: VoiceSessionState) -> VoiceSession:
        session = VoiceSession(
            state,
            repository=self.repository,
            router=self.router,
            factory=self.factory,
            rag=self.rag,
            progress=self.progress,
            orchestrator=self.orchestrator,
            settings=self.settings,
            profiles=self.profiles,
        )
        self._sessions[state.session_id] = session
        return session

    async def create(
        self,
        *,
        student_id: str,
        language: str = "en",
        course_id: str | None = None,
        lesson_id: str | None = None,
        topic: str | None = None,
        topic_id: str | None = None,
        document_ids: list[str] | None = None,
        dialect: str | None = None,
        level: str | None = None,
        resume_latest: bool = False,
    ) -> VoiceSession:
        language = validate_language(language)
        # How this student is taught: their profile (LERNA, or the local mirror
        # until that integration is live), unless the caller overrides it here.
        profile = await self.resolve_profile(student_id, level)
        # Arabic only: which register the tutor speaks — fusHa (`ar-MSA`).
        dialect = normalise_dialect(language, dialect)
        # A catalogued topic is authoritative: it names the lesson, its course and
        # the section-by-section plan the tutor should follow (§43 lesson context).
        catalogued = curriculum.resolve(topic_id, topic)
        if catalogued is not None:
            course_id = course_id or catalogued.course_id
            lesson_id = lesson_id or catalogued.id
            topic = catalogued.title
        if resume_latest:
            previous = await self.repository.latest_session_for_student(
                student_id, course_id=course_id, lesson_id=lesson_id
            )
            if previous is not None:
                # A returning student gets a NEW session that inherits the
                # learning state of the old one (§28) - the finished session
                # record stays intact for history and analytics.
                state = VoiceSessionState(
                    student_id=student_id,
                    course_id=course_id or previous.course_id,
                    lesson_id=lesson_id or previous.lesson_id,
                    language=language,
                    dialect=dialect or previous.dialect,
                    student_level=profile.level,
                    current_topic=topic or previous.current_topic,
                    current_section=previous.current_section,
                    topic_id=(catalogued.id if catalogued else previous.topic_id),
                    lesson_plan=(
                        catalogued.lesson_plan() if catalogued else list(previous.lesson_plan)
                    ),
                    resume_checkpoint=previous.resume_checkpoint,
                    concepts_covered=list(previous.concepts_covered),
                    misconceptions=list(previous.misconceptions),
                    unresolved_questions=list(previous.unresolved_questions),
                    session_summary=previous.session_summary,
                    next_action=previous.next_action,
                    document_ids=document_ids or previous.document_ids,
                    is_returning=True,
                    previous_session_id=previous.session_id,
                )
                session = self._wrap(state)
                await self.repository.save_session(state)
                return session

        state = VoiceSessionState(
            student_id=student_id,
            course_id=course_id,
            lesson_id=lesson_id,
            language=language,
            dialect=dialect,
            student_level=profile.level,
            current_topic=topic or "",
            topic_id=catalogued.id if catalogued else None,
            lesson_plan=catalogued.lesson_plan() if catalogued else [],
            document_ids=document_ids,
        )
        session = self._wrap(state)
        session.preview_planned_pipeline()
        await self.repository.save_session(state)
        return session

    async def get(self, session_id: str) -> VoiceSession | None:
        session = self._sessions.get(session_id)
        if session is not None:
            return session
        state = await self.repository.get_session(session_id)
        if state is None:
            return None
        return self._wrap(state)

    async def require(self, session_id: str) -> VoiceSession:
        session = await self.get(session_id)
        if session is None:
            raise KeyError(session_id)
        return session

    async def latest_for_student(self, student_id: str) -> VoiceSessionState | None:
        return await self.repository.latest_session_for_student(student_id)

    async def dispose(self, session_id: str) -> None:
        session = self._sessions.pop(session_id, None)
        if session is not None:
            await session._teardown_provider()

    async def shutdown(self) -> None:
        for session_id in list(self._sessions):
            await self.dispose(session_id)

    def active_count(self) -> int:
        return len(self._sessions)


_manager: VoiceSessionManager | None = None


def get_manager() -> VoiceSessionManager:
    global _manager
    if _manager is None:
        _manager = VoiceSessionManager()
    return _manager


def set_manager(manager: VoiceSessionManager | None) -> None:
    global _manager
    _manager = manager
