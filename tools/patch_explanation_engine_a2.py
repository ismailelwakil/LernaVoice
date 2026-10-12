"""Round 19, part A2: event, session state, progress level, session teaching.

Run once from the service root:  python3 tools/patch_explanation_engine_a2.py
"""
import io


def read(p):
    return io.open(p, encoding="utf-8").read()


def write(p, s):
    io.open(p, "w", encoding="utf-8").write(s)


def sub(path, pairs):
    s = read(path)
    for old, new in pairs:
        assert old in s, (path, old[:70])
        s = s.replace(old, new, 1)
    write(path, s)


sub("app/voice/events.py", [
    (
        '    LANGUAGE_CHANGED = "language.changed"',
        '    LANGUAGE_CHANGED = "language.changed"\n'
        '    #: The grounded, level-adapted explanation the tutor teaches from.\n'
        '    EXPLANATION_PLANNED = "explanation.planned"',
    ),
])

sub("app/voice/state.py", [
    (
        """    dialect: str | None = None
    state: SessionState = SessionState.IDLE""",
        """    dialect: str | None = None
    #: How this student is taught: beginner | intermediate | advanced. Read from the
    #: LERNA Progress Profile (a local mirror until that integration is live, see
    #: app/learner/profiles.py); it decides the moves of the explanation.
    student_level: str = "intermediate"
    state: SessionState = SessionState.IDLE""",
    ),
    (
        """    lesson_plan: list[dict[str, str]] = Field(default_factory=list)""",
        """    lesson_plan: list[dict[str, str]] = Field(default_factory=list)
    #: The grounding the tutor was given for this topic: the vetted sources and the
    #: level-adapted moves (see app/learning/explainer.py). Persisted, so a resumed
    #: session keeps explaining the same way.
    explanation: dict | None = None""",
    ),
])

sub("app/learner/progress_adapter.py", [
    (
        """    preferred_language: str | None = None
    learning_preference: str | None = None""",
        """    preferred_language: str | None = None
    learning_preference: str | None = None
    #: beginner | intermediate | advanced — how the tutor should pitch it.
    level: str | None = None""",
    ),
    (
        """            "student_name": self.name,
            "course": self.course,""",
        """            "student_name": self.name,
            "student_level": self.level,
            "course": self.course,""",
    ),
    (
        """        preferred_language=sget("preferred_language", None),
        learning_preference=sget("learning_preference", None),""",
        """        preferred_language=sget("preferred_language", None),
        learning_preference=sget("learning_preference", None),
        level=(
            sget("level", None)
            or sget("education_level", None)
            or get("level", None)
            or get("student_level", None)
            or get("proficiency", None)
        ),""",
    ),
])

sub("app/voice/session_manager.py", [
    (
        "from app.learner.canonical_concepts import canonical_topic, canonicalise_concept",
        "from app.learner.canonical_concepts import canonical_topic, canonicalise_concept\n"
        "from app.learner.profiles import LearnerProfile, LearnerProfileStore, resolve_profile\n"
        "from app.learning.explainer import ExplanationBrief, build_brief\n"
        "from app.learning.levels import normalise_level",
    ),
    (
        """        orchestrator: OrchestratorAdapter,
        settings: Settings,
        profiles: LearnerProfileStore | None = None,
    ):
        self.state = state
        self.profile_store = profiles""",
        """        orchestrator: OrchestratorAdapter,
        settings: Settings,
        profiles: LearnerProfileStore | None = None,
    ):
        self.state = state
        self.profile_store = profiles""",
    ),
    (
        """        self.learner_context: dict[str, Any] = {}
        self.last_evidence: list[dict[str, Any]] = []""",
        """        self.learner_context: dict[str, Any] = {}
        self.last_evidence: list[dict[str, Any]] = []
        #: The level-adapted explanation brief this session teaches from.
        self.explanation: ExplanationBrief | None = None""",
    ),
    (
        """        learner = await self.progress.get_context(self.state.student_id)
        self.learner_context = learner.as_prompt_context()""",
        """        learner = await self.progress.get_context(self.state.student_id)
        self.learner_context = learner.as_prompt_context()
        self.learner_context["student_level"] = self.state.student_level
        self.learner_context["teaching_level"] = self._brief().style.instruction""",
    ),
    (
        """        await self._set_state(SessionState.THINKING)
        await self._send_text_to_provider(prompt)
        await self._persist()""",
        """        await self.emit_explanation_planned()
        await self._set_state(SessionState.THINKING)
        await self._send_text_to_provider(prompt)
        await self._persist()""",
    ),
    (
        """    async def _build_session_config(self) -> SessionConfig:
        checkpoint = self.state.resume_checkpoint.model_dump() if self.state.resume_checkpoint else None""",
        """    def _brief(self) -> ExplanationBrief:
        \"\"\"The grounded, level-adapted explanation for this session's topic.\"\"\"
        brief = build_brief(
            topic_id=self.state.topic_id,
            topic_title=self.state.current_topic or None,
            language=self.state.language,
            level=self.state.student_level,
            plan=list(self.state.lesson_plan),
        )
        self.explanation = brief
        self.state.explanation = brief.as_dict()
        return brief

    async def emit_explanation_planned(self) -> None:
        \"\"\"Publish what the tutor is teaching from: the level, moves and sources.\"\"\"
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
        \"\"\"Explain the same lesson for a different level; learning state untouched.\"\"\"
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
        checkpoint = self.state.resume_checkpoint.model_dump() if self.state.resume_checkpoint else None""",
    ),
    (
        """        instruction = build_system_instruction(
            language=self.state.language,
            dialect=self.state.dialect,
            lesson_context=lesson_context,
            learner_context=self.learner_context,
            checkpoint=checkpoint,
        )""",
        """        brief = self._brief()
        if self.learner_context:
            self.learner_context["student_level"] = self.state.student_level
        instruction = build_system_instruction(
            language=self.state.language,
            dialect=self.state.dialect,
            lesson_context=lesson_context,
            learner_context=self.learner_context,
            checkpoint=checkpoint,
            extra=brief.prompt_block() if brief.moves else None,
        )""",
    ),
    (
        """            metadata={
                "student_id": self.state.student_id,
                "dialect": self.state.dialect,
                "topic_id": self.state.topic_id,
                "topic_title": self.state.current_topic,
                "step_index": self._plan_position(),
                "sections": list(self.state.lesson_plan),
            },""",
        """            metadata={
                "student_id": self.state.student_id,
                "dialect": self.state.dialect,
                "topic_id": self.state.topic_id,
                "topic_title": self.state.current_topic,
                "student_level": self.state.student_level,
                "step_index": self._plan_position(),
                "sections": list(self.state.lesson_plan),
                # The offline mock teaches the same grounded brief, level and all.
                "explanation_moves": [m.as_dict() for m in brief.for_step(0)],
                "explanation": brief.as_dict(),
            },""",
    ),
])
print("part A2: event, state, progress level and the session teaching wired")
