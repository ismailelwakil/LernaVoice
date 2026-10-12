"""§55 — the complete end-to-end scenario, start to finish, on mock providers.

Arabic lesson -> 2 interruptions with follow-ups -> mid-lesson Gemini outage ->
failover with full continuity -> resume -> session end -> student returns later
and gets a recap that continues instead of restarting.
"""

from __future__ import annotations

from app.providers.mock.providers import INJECTOR
from app.voice.events import EventType
from app.voice.interruption_manager import InterruptionManager
from app.voice.resume_manager import ResumeManager
from app.voice.state import SessionState


async def test_full_arabic_lesson_with_outage_and_return(manager, recorder, repository, progress):
    # --- 1. a student starts an Arabic lesson ------------------------------
    session = await manager.create(
        student_id="student-arabic-001",
        language="ar",
        course_id="algorithms-101",
        lesson_id="lesson-binary-search",
        topic="Binary Search",
    )
    rec = recorder(session)
    await session.start()
    await rec.drain()

    assert session.state.language == "ar"
    assert session.state.active_pipeline.signature() == "realtime:gemini"
    assert rec.has(EventType.SESSION_STARTED)

    # --- 2. the tutor teaches; the student speaks --------------------------
    await session.send_audio(b"\x12\x34" * 480)
    session.state.current_section = "تعريف البحث الثنائي"
    session.state.concepts_covered += ["مصفوفة مرتبة", "المؤشر الأول"]
    await session._finish_turn("البحث الثنائي يقسم المصفوفة إلى نصفين.")

    # --- 3. first interruption + follow-up ---------------------------------
    interruptions = InterruptionManager(session)
    first = await interruptions.interrupt()
    await rec.drain()
    assert first["acknowledgement"] == "طبعًا، اتفضل اسأل سؤالك."
    assert rec.of(EventType.ASSISTANT_INTERRUPTED)[0].data["stop_playback"] is True

    q1 = await interruptions.ask("ليه بنقسم المصفوفة على اتنين؟")
    assert q1["is_followup"] is False
    await session._finish_turn("لأن كل قسمة بتشيل نص الاحتمالات.")

    q2 = await interruptions.ask("وإيه اللي يحصل لو المصفوفة مش مرتبة؟")
    assert q2["is_followup"] is True
    await session._finish_turn("ساعتها البحث الثنائي مش هيشتغل صح.")

    await ResumeManager(session).resume()
    await rec.drain()
    assert rec.has(EventType.RESUME_COMPLETED)
    assert session.state.resume_count == 1

    # --- 4. lesson continues, then the primary provider dies mid-lesson ----
    session.state.current_section = "حساب نقطة المنتصف"
    session.state.concepts_covered.append("نقطة المنتصف")
    await interruptions.interrupt()
    checkpoint_before = session.state.resume_checkpoint
    questions_before = len(session.state.student_questions)

    INJECTOR.fail("gemini", "internal")
    await session._on_provider_error(RuntimeError("gemini live socket closed"))
    await rec.drain()

    assert rec.has(EventType.PROVIDER_FALLBACK_STARTED)
    assert rec.has(EventType.PROVIDER_SWITCHED)
    pipeline = session.state.active_pipeline
    assert pipeline.mode == "cascade"
    assert "gemini" not in (pipeline.stt, pipeline.llm, pipeline.tts)

    # continuity (§21): nothing about the lesson was lost
    assert session.state.language == "ar"
    assert session.state.current_topic == "Binary Search"
    assert session.state.current_section == "حساب نقطة المنتصف"
    assert session.state.resume_checkpoint.checkpoint_id == checkpoint_before.checkpoint_id
    assert len(session.state.student_questions) == questions_before
    assert "نقطة المنتصف" in session.state.concepts_covered

    # --- 5. the student keeps going on the backup pipeline -----------------
    q3 = await interruptions.ask("يعني المنتصف هو المتوسط؟")
    assert q3["is_followup"] is True
    await session._finish_turn("ظبط، المتوسط بين أول وآخر مؤشر.")
    await ResumeManager(session).resume()
    assert session.state.resume_count == 2
    assert session.state.interrupt_count == 2
    assert len(session.state.student_questions) == 3
    assert not session.state.unresolved_questions

    # --- 6. end the session ------------------------------------------------
    await session.end()
    await rec.drain()
    assert session.state.state is SessionState.ENDED
    assert rec.has(EventType.SESSION_ENDED)

    stored = await repository.get_session(session.state.session_id)
    assert stored.language == "ar"
    assert len(stored.student_questions) == 3
    assert stored.resume_checkpoint is not None
    assert len(stored.provider_history) >= 2

    # --- 7. the student returns later: recap, not restart ------------------
    returning = await manager.create(
        student_id="student-arabic-001",
        language="ar",
        course_id="algorithms-101",
        lesson_id="lesson-binary-search",
        resume_latest=True,
    )
    rec2 = recorder(returning)
    await returning.start()
    await rec2.drain()

    assert returning.state.session_id != session.state.session_id
    assert returning.state.is_returning is True
    assert returning.state.current_topic == "Binary Search"
    assert "نقطة المنتصف" in returning.state.concepts_covered
    assert returning.state.resume_checkpoint is not None

    recap = rec2.of(EventType.SESSION_RECAP)
    assert recap, "a returning student must receive a recap event"
    assert recap[0].data["previous_session_id"] == session.state.session_id

    prompt = returning.provider.sent_text[-1]
    assert "نقطة المنتصف" in prompt or "Binary Search" in prompt
    assert "start over" not in prompt.lower()


async def test_event_stream_order_is_coherent(manager, recorder):
    session = await manager.create(student_id="s", language="en", topic="Binary Search")
    rec = recorder(session)
    await session.start()
    await session.interrupt()
    await session.ask_question("Why?")
    await session._finish_turn("Because.")
    await session.resume()
    await session.end()
    await rec.drain()

    names = rec.types()
    assert names.index("session.started") < names.index("assistant.interrupted")
    assert names.index("assistant.interrupted") < names.index("checkpoint.created")
    assert names.index("checkpoint.created") < names.index("question.started")
    assert names.index("question.started") < names.index("resume.started")
    assert names[-1] == "session.ended"
    seqs = [e.seq for e in rec.events]
    assert seqs == sorted(seqs)
