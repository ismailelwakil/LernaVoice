

# Round 26 — comprehension & conduct policy + lessons from uploaded material.
def test_unclear_escalates_repeat_then_write_then_giveup():
    from app.providers.mock.dialogue import TutorDialogue
    from app.learning.explainer import build_brief
    plan = [{"title": "The idea", "goal": "halve the range"}, {"title": "Trace", "goal": "walk the indexes"}]
    brief = build_brief(topic_id="binary-search", language="ar", level="beginner", plan=plan)
    md = {"topic_id": "binary-search", "topic_title": "البحث الثنائي", "sections": plan,
          "explanation": brief.as_dict(), "student_level": "beginner"}
    dlg = TutorDialogue.from_metadata(md, "ar"); dlg.opening()
    r1, r2, r3 = (dlg.respond(x) for x in ("!!!", "###", "@@@"))
    for r in (r1, r2, r3):                     # first three: "say it again"
        assert "كتاب" not in r and "قصدك" not in r
    assert len({r1, r2, r3}) >= 2              # and the wording varies, not a loop
    r4 = dlg.respond("%%%")
    assert "كتاب" in r4                        # 4th time → ask them to write it
    r5 = dlg.respond("^^^")
    assert "قصدك" in r5                        # still not → "I didn't get your point"


def test_clear_turn_resets_unclear_counter():
    from app.providers.mock.dialogue import TutorDialogue
    from app.learning.explainer import build_brief
    plan = [{"title": "The idea", "goal": "halve the range"}, {"title": "Trace", "goal": "walk"}]
    brief = build_brief(topic_id="binary-search", language="ar", level="beginner", plan=plan)
    md = {"topic_id": "binary-search", "topic_title": "البحث الثنائي", "sections": plan,
          "explanation": brief.as_dict(), "student_level": "beginner"}
    dlg = TutorDialogue.from_metadata(md, "ar"); dlg.opening()
    dlg.respond("!!!"); dlg.respond("###")
    dlg.respond("نعم")                          # a clear turn resets the streak
    again = dlg.respond("!!!")                 # next unclear is "repeat" again, not "write it"
    assert "كتب" not in again and "قصدك" not in again


def test_impolite_warns_once_then_ends_lesson():
    from app.providers.mock.dialogue import TutorDialogue
    from app.learning.explainer import build_brief
    plan = [{"title": "The idea", "goal": "halve"}, {"title": "Trace", "goal": "walk"}]
    brief = build_brief(topic_id="binary-search", language="ar", level="beginner", plan=plan)
    md = {"topic_id": "binary-search", "topic_title": "البحث الثنائي", "sections": plan,
          "explanation": brief.as_dict(), "student_level": "beginner"}
    dlg = TutorDialogue.from_metadata(md, "ar"); dlg.opening()
    warn = dlg.respond("يا غبي")
    assert "احترام" in warn or "أدب" in warn
    end = dlg.respond("انت غبي جدا")
    assert "انتهى" in end and dlg.done
    closed = dlg.respond("نعم")
    assert "مغلق" in closed or "جلسة جديدة" in closed


def test_upload_material_yields_a_teachable_lesson():
    from app.rag import local_corpus
    from app.learning.explainer import build_brief
    local_corpus.reset()
    # A topic that is NOT in the curated catalogue — the only source is the upload.
    text = ("Quantum tunnelling lets a particle cross a barrier it classically could not pass. "
            "The wave function does not stop at the barrier, it decays through it. "
            "A thicker or taller barrier makes tunnelling much less likely. "
            "Tunnel diodes and nuclear fusion both rely on this effect.")
    doc_id = local_corpus.add_document("Quantum Tunnelling", text, language="en")
    chunks = local_corpus.retrieve("quantum tunnelling barrier wave function", document_ids=[doc_id])
    assert chunks, "retrieval found nothing in the uploaded material"
    brief = build_brief(topic_id=None, topic_title="Quantum Tunnelling",
                        language="en", level="beginner",
                        plan=[{"title": "How it works", "goal": "cross the barrier"}],
                        evidence=chunks)
    assert brief.moves and brief.grounding == "uploaded"
    joined = " ".join(m.text for m in brief.moves)
    assert "barrier" in joined and "wave function" in joined
    local_corpus.reset()
