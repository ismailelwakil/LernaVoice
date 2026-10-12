"""Round 19, part C: the API surface for levels.

Run once from the service root:  python3 tools/patch_explanation_engine_c.py
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


# --------------------------------------------------------------------------- #
# settings: where the level mirror lives
# --------------------------------------------------------------------------- #

sub("app/config.py", [
    (
        '    azure_voice_overrides: str = ""',
        '    azure_voice_overrides: str = ""\n'
        "    #: Where the learner-profile mirror lives (each student's level) until\n"
        "    #: LERNA's Progress Profile is wired in. Empty keeps it in memory, which\n"
        "    #: is what the test suite uses.\n"
        '    learner_profile_path: str = ""',
    ),
])

# --------------------------------------------------------------------------- #
# schemas: level on create, on the summary, on the state, and its own request
# --------------------------------------------------------------------------- #

sub("app/api/schemas.py", [
    (
        "from app.voice.dialects import normalise_dialect, split_language",
        "from app.learning.levels import is_known_level\n"
        "from app.voice.dialects import normalise_dialect, split_language",
    ),
    (
        """    #: Arabic register. Arabic is taught in "ar-MSA" (fusHa) and every value""",
        """    #: How to pitch the explanation: beginner | intermediate | advanced (also
        #: accepts a1/a2/b1/b2/c1/c2 and "first year"). Left out -> the level in the
        #: student's LERNA profile is used, and failing that the service default.
    level: str | None = None
    #: Arabic register. Arabic is taught in "ar-MSA" (fusHa) and every value""",
    ),
    (
        """        self.dialect = normalise_dialect(language, self.dialect or register)
        return self""",
        """        self.dialect = normalise_dialect(language, self.dialect or register)
        return self

    @model_validator(mode="after")
    def _check_level(self) -> "CreateSessionRequest":
        \"\"\"An unknown level is a client bug, so say so instead of guessing.\"\"\"
        if self.level is not None and not is_known_level(self.level):
            raise ValueError("level must be one of beginner, intermediate, advanced")
        return self""",
    ),
    (
        """    language: str
    dialect: str | None = None
    state: str
    current_topic: str = ""
    current_section: str = ""
    topic_id: str | None = None""",
        """    language: str
    dialect: str | None = None
    #: beginner | intermediate | advanced — the pitch of the explanation.
    student_level: str = "intermediate"
    state: str
    current_topic: str = ""
    current_section: str = ""
    topic_id: str | None = None""",
    ),
    (
        """    language: str
    dialect: str | None = None
    current_topic: str = ""
    current_section: str = ""
    topic_id: str | None = None
    lesson_plan: list[dict[str, str]] = []""",
        """    language: str
    dialect: str | None = None
    student_level: str = "intermediate"
    current_topic: str = ""
    current_section: str = ""
    topic_id: str | None = None
    lesson_plan: list[dict[str, str]] = []""",
    ),
    (
        """    active_pipeline: dict[str, Any]
    provider_history: list[dict[str, Any]] = Field(default_factory=list)
    diagnostics: dict[str, Any] | None = None""",
        """    active_pipeline: dict[str, Any]
    provider_history: list[dict[str, Any]] = Field(default_factory=list)
    diagnostics: dict[str, Any] | None = None
    #: What the tutor is teaching from: the vetted sources, the level's teaching
    #: moves and the closing question (see app/learning/explainer.py).
    explanation: dict[str, Any] | None = None""",
    ),
    (
        """class SimpleResponse(BaseModel):""",
        """class LevelChangeRequest(BaseModel):
    \"\"\"A new pitch for the lesson being taught: beginner | intermediate | advanced.\"\"\"

    level: str

    @model_validator(mode="after")
    def _check_level(self) -> "LevelChangeRequest":
        if not is_known_level(self.level):
            raise ValueError("level must be one of beginner, intermediate, advanced")
        return self


class SimpleResponse(BaseModel):""",
    ),
])

# --------------------------------------------------------------------------- #
# routes: honour the level, expose it, and let the client change it
# --------------------------------------------------------------------------- #

sub("app/api/routes.py", [
    (
        """    LanguageChangeRequest,
    QuestionRequest,""",
        """    LanguageChangeRequest,
    LevelChangeRequest,
    QuestionRequest,""",
    ),
    (
        """        document_ids=payload.document_ids,
        dialect=payload.dialect,
        resume_latest=payload.resume_latest,
    )""",
        """        document_ids=payload.document_ids,
        dialect=payload.dialect,
        level=payload.level,
        resume_latest=payload.resume_latest,
    )""",
    ),
    (
        """        language=state.language,
        dialect=state.dialect,
        state=state.state.value,
        current_topic=state.current_topic,
        current_section=state.current_section,
        interrupt_count=state.interrupt_count,""",
        """        language=state.language,
        dialect=state.dialect,
        student_level=state.student_level,
        state=state.state.value,
        current_topic=state.current_topic,
        current_section=state.current_section,
        interrupt_count=state.interrupt_count,""",
    ),
    (
        """        session_id=state.session_id,
        state=state.state.value,
        language=state.language,
        dialect=state.dialect,
        current_topic=state.current_topic,""",
        """        session_id=state.session_id,
        state=state.state.value,
        language=state.language,
        dialect=state.dialect,
        student_level=state.student_level,
        current_topic=state.current_topic,""",
    ),
    (
        """@router.post("/voice/session/{session_id}/pause", response_model=SimpleResponse)""",
        """@router.post("/voice/session/{session_id}/level", response_model=SimpleResponse)
async def change_level(
    session_id: str, payload: LevelChangeRequest, principal: Principal = Depends(require_service_auth)
) -> SimpleResponse:
    \"\"\"Re-pitch the same lesson for another level; nothing learned is lost.\"\"\"
    session = await _session_or_404(session_id)
    result = await session.change_level(payload.level)
    return SimpleResponse(
        session_id=session_id,
        state=session.state.state.value,
        detail=f"level={result['student_level']}",
    )


@router.post("/voice/session/{session_id}/pause", response_model=SimpleResponse)""",
    ),
])

# --------------------------------------------------------------------------- #
# main: the running service uses the file-backed level mirror
# --------------------------------------------------------------------------- #

sub("app/main.py", [
    (
        "from app.persistence.repository import get_repository",
        "from app.learner.profiles import LearnerProfileStore\n"
        "from app.persistence.repository import get_repository",
    ),
    (
        """    repo = get_repository(settings)
    manager = get_manager()
    bridge = get_bridge(settings)""",
        """    repo = get_repository(settings)
    manager = get_manager()
    if settings.learner_profile_path and not getattr(manager.profiles, "path", None):
        # Remember each student's level across restarts; tests keep it in memory.
        manager.profiles = LearnerProfileStore(settings.learner_profile_path)
    bridge = get_bridge(settings)""",
    ),
])
print("part C: level on create, on the summary/state, /level endpoint, file-backed store")
