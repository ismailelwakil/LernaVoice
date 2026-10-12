"""Round 20: the offline tutor teaches in passes, not one line at a time.

Run once from the service root:  python3 tools/patch_teacher_dialogue.py
"""
import io


def sub(path, pairs):
    s = io.open(path, encoding="utf-8").read()
    for old, new in pairs:
        assert old in s, (path, old[:70])
        s = s.replace(old, new, 1)
    io.open(path, "w", encoding="utf-8").write(s)


sub("app/providers/mock/dialogue.py", [
    (
        "from app.prompts.interaction import (\n"
        "    phrase,\n"
        "    phrase_variants,\n"
        "    move_on,\n"
        "    react,\n"
        "    speakable,\n"
        "    step_lead,\n"
        ")",
        "from app.learning.lesson_script import LessonScript, Pass, build_script\n"
        "from app.prompts.interaction import (\n"
        "    phrase,\n"
        "    phrase_variants,\n"
        "    move_on,\n"
        "    react,\n"
        "    speakable,\n"
        "    step_lead,\n"
        "    teach_frame,\n"
        ")",
    ),
    (
        """    #: True once the whole plan has been taught: further turns must not re-close it.
    done: bool = False""",
        """    #: True once the whole plan has been taught: further turns must not re-close it.
    done: bool = False
    #: The lesson as teaching passes (round 20). Present whenever the session was
    #: given a grounded brief; this is what makes a turn an explanation rather
    #: than a single line. `None` -> the older plan-reading behaviour.
    script: LessonScript | None = None
    #: Which pass of the script the tutor is teaching (and speaking) right now.
    pass_index: int = 0
    #: Rotates the grounded facts used to answer a question.
    _answered: int = 0""",
    ),
    (
        """        return cls(
            language=language,
            line_language=line_language(language, md.get("dialect")),""",
        """        dialogue = cls(
            language=language,
            line_language=line_language(language, md.get("dialect")),""",
    ),
    (
        """            level=str(md.get("student_level") or "intermediate"),
            step=step,
        )""",
        """            level=str(md.get("student_level") or "intermediate"),
            step=step,
        )
        dialogue.script = dialogue._build_script(sections)
        return dialogue

    # ------------------------------------------------------- teaching passes
    def _build_script(self, sections: list[dict[str, str]]) -> LessonScript | None:
        \"\"\"The grounded brief as passes — the shape of a real explanation.\"\"\"
        moves = (self.explanation or {}).get("moves") or []
        if not moves:
            return None
        style = (self.explanation or {}).get("style") or {}
        script = build_script(
            topic=self.topic,
            language=self.line_language,
            level=self.level,
            moves=moves,
            sections=sections,
            max_clause_words=int(style.get("clauses") or 24),
        )
        return script if len(script) else None

    @property
    def teaching(self) -> bool:
        \"\"\"True when this tutor has a grounded lesson to teach, pass by pass.\"\"\"
        return bool(self.script and len(self.script))

    def _pass_at(self, index: int) -> Pass | None:
        return self.script.at(index) if self.script else None

    def _speak_pass(self, index: int) -> str:
        \"\"\"Speak one whole pass, and remember where the lesson now stands.

        `step` follows the pass's own plan section, so checkpoints and resume keep
        naming real lesson steps even though a turn now covers more ground.
        \"\"\"
        current = self._pass_at(index)
        if current is None:
            return ""
        self.pass_index = index
        self.step = current.section_index
        return self._name(current.script())

    def _facts(self, count: int = 2) -> str:
        \"\"\"Grounded sentences to answer with — the pack's own words, rotating.\"\"\"
        moves = [
            m
            for m in (self.explanation or {}).get("moves") or []
            if m.get("kind") in ("idea", "fact", "why", "example") and m.get("text")
        ]
        if not moves:
            return ""
        picked = [moves[(self._answered + i) % len(moves)] for i in range(min(count, len(moves)))]
        self._answered += count
        return " ".join(str(m["text"]).strip() for m in picked)

    def _reteach(self, current: Pass) -> str:
        \"\"\"Say the same part again by another route, never the same sentence twice.\"\"\"
        self._explain_style += 1
        route = self._explain_style % 3
        shorter = [_first_clause(s) for s in current.sentences if len(s.split()) > 8]
        if route == 1 and shorter:
            return self._name(
                f"{self._v('rephrase')} {teach_frame(self.line_language, 'plainer')} "
                f"{' '.join(shorter[:3])} {self._v('encourage')}"
            )
        if route == 2:
            example = [s for s in current.sentences if teach_frame(self.line_language, "example") in s]
            if example:
                return self._name(f"{self._v('rephrase')} {example[0]} {self._v('encourage')}")
            return self._name(
                f"{self._v('rephrase')} {self._p('example')} "
                f"{self._t('which_part', title=self._title_lower({'title': current.section}))}"
            )
        return self._name(
            f"{self._v('rephrase')} {self._p('which_part')} "
            f"({current.section}) {self._v('encourage')}"
        )

    def _teach_turn(self, intent: Intent, student_text: str) -> str:
        \"\"\"One teaching turn: re-explain, answer-and-continue, or teach the next pass.\"\"\"
        current = self._pass_at(self.pass_index)
        if current is None:
            return self._name(self._generic(intent))

        if intent is Intent.CONFUSED:
            return self._reteach(current)

        if intent is Intent.QUESTION:
            answer = self._facts(2)
            tail = ""
            following = self.pass_index + 1
            if following < len(self.script):
                tail = f"{teach_frame(self.line_language, 'back')} {self._speak_pass(following)}"
            return self._name(f"{self._p('answer_ack')} {answer} {tail}".strip())

        following = self.pass_index + 1
        if following >= len(self.script):
            self.done = True
            praise = self._v("praise") if intent is Intent.AFFIRM else react(self.line_language, self._variety)
            return self._name(f"{praise} {self._v('close')}")
        # An answer, a grunt, or a stray remark: acknowledge in a couple of words and
        # keep teaching. That is what a teacher does with the floor still theirs.
        if intent is Intent.AFFIRM:
            ack = self._v("praise")
        else:
            ack = react(self.line_language, self._variety)
        return self._name(f"{ack} {self._speak_pass(following)}")""",
    ),
    (
        """        first = self.sections[0]
        # A person sets the scene before the first idea, then hands the turn over.
        return (
            f"{greeting}{who} {self._topic_line()} "
            f"{move_on(self.line_language, 0)} {self._lead_or_explain(first, 0)} "
            f"{self._p('invite_stop')}"
        )""",
        """        if self.teaching:
            # The first turn is already the first taught part, developed properly.
            return f"{greeting}{who} {self._topic_line()} {self._speak_pass(0)}"
        first = self.sections[0]
        # A person sets the scene before the first idea, then hands the turn over.
        return (
            f"{greeting}{who} {self._topic_line()} "
            f"{move_on(self.line_language, 0)} {self._lead_or_explain(first, 0)} "
            f"{self._p('invite_stop')}"
        )""",
    ),
    (
        """        if not self.planned:
            return self._name(self._generic(intent))

        current = self.sections[min(self.step, len(self.sections) - 1)]""",
        """        if not self.planned:
            return self._name(self._generic(intent))

        if self.teaching:
            return self._teach_turn(intent, student_text)

        current = self.sections[min(self.step, len(self.sections) - 1)]""",
    ),
    (
        """        step = self.sections[min(self.step, len(self.sections) - 1)]
        tail = self.check_line() or (self._p("check") if self._asking() else self._p("invite_stop"))
        return self._name(
            f"{self._p('switch')} {self._lead_or_explain(step, self.step, offset=1)} {tail}"
        )""",
        """        if self.teaching:
            return self._name(f"{self._p('switch')} {self._speak_pass(self.pass_index)}")
        step = self.sections[min(self.step, len(self.sections) - 1)]
        tail = self.check_line() or (self._p("check") if self._asking() else self._p("invite_stop"))
        return self._name(
            f"{self._p('switch')} {self._lead_or_explain(step, self.step, offset=1)} {tail}"
        )""",
    ),
    (
        """    def _title_lower(self, section: dict[str, str]) -> str:""",
        """    def _title_lower(self, section: dict[str, str]) -> str:""",
    ),
])

# `_first_clause` — the helper the re-teaching route uses
sub("app/providers/mock/dialogue.py", [
    (
        """def _contains(padded_text: str, needle: str) -> bool:""",
        """def _first_clause(sentence: str) -> str:
    \"\"\"The opening clause of a sentence, ending like one — for a plainer re-run.\"\"\"
    for mark in (": ", "؛ ", "; ", "، ", ", "):
        head, sep, _tail = sentence.partition(mark)
        if sep and len(head.split()) >= 4:
            head = head.strip().rstrip("،,;:")
            return head if head.endswith((".", "!", "?")) else head + "."
    return sentence


def _contains(padded_text: str, needle: str) -> bool:""",
    ),
])
print("dialogue teaches in passes")
