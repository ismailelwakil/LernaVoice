"""Round 16, part 2: thread the Arabic register through the session.

Run once from the service root:  python3 tools/patch_arabic_dialects2.py
"""
import io


def read(p):
    return io.open(p, encoding="utf-8").read()


def write(p, s):
    io.open(p, "w", encoding="utf-8").write(s)


def sub(path, pairs, all_=False):
    s = read(path)
    for old, new in pairs:
        assert old in s, (path, old[:70])
        s = s.replace(old, new) if all_ else s.replace(old, new, 1)
    write(path, s)


# --------------------------------------------------------------------------- #
# 1. the session records which register it is taught in
# --------------------------------------------------------------------------- #

sub("app/voice/state.py", [(
    '''    language: str = "en"
    state: SessionState = SessionState.IDLE''',
    '''    language: str = "en"
    #: Arabic only: `ar-EG` (Egyptian, the default) or `ar-MSA` (fusHa). The
    #: language code stays `ar` for routing and learning state; this only changes
    #: the voice, the phrase set and the sentence the instruction adds.
    dialect: str | None = None
    state: SessionState = SessionState.IDLE''',
)])

sub("app/api/schemas.py", [
    (
        '''from app.voice.state import SUPPORTED_LANGUAGES''',
        '''from app.voice.dialects import arabic_dialect_options, normalise_dialect
from app.voice.state import SUPPORTED_LANGUAGES''',
    ),
    (
        '''    document_ids: list[str] | None = None
    resume_latest: bool = False

    @field_validator("language")''',
        '''    document_ids: list[str] | None = None
    #: Arabic register: "ar-EG" (Egyptian, default) or "ar-MSA" (fusHa). Ignored
    #: for the other nine languages; aliases ("egyptian", "msa", "fusha") work.
    dialect: str | None = None
    resume_latest: bool = False

    @field_validator("language")''',
    ),
    (
        '''        if v not in SUPPORTED_LANGUAGES:
            raise ValueError(f"language must be one of {', '.join(SUPPORTED_LANGUAGES)}")
        return v


class SessionSummary''',
        '''        if v not in SUPPORTED_LANGUAGES:
            raise ValueError(f"language must be one of {', '.join(SUPPORTED_LANGUAGES)}")
        return v

    @field_validator("dialect")
    @classmethod
    def _check_dialect(cls, v: str | None, info) -> str | None:
        return normalise_dialect(info.data.get("language"), v)


class SessionSummary''',
    ),
    (
        '''    language: str
    state: str
    current_topic: str = ""''',
        '''    language: str
    dialect: str | None = None
    state: str
    current_topic: str = ""''',
    ),
    (
        '''class SessionStateResponse(BaseModel):
    session_id: str
    state: str
    language: str''',
        '''class SessionStateResponse(BaseModel):
    session_id: str
    state: str
    language: str
    dialect: str | None = None''',
    ),
])

sub("app/api/routes.py", [
    (
        '''        document_ids=payload.document_ids,
        resume_latest=payload.resume_latest,
    )''',
        '''        document_ids=payload.document_ids,
        dialect=payload.dialect,
        resume_latest=payload.resume_latest,
    )''',
    ),
    (
        '''        language=state.language,
        state=state.state.value,
        current_topic=state.current_topic,
        current_section=state.current_section,
        interrupt_count=state.interrupt_count,
        resume_count=state.resume_count,
        active_pipeline=state.active_pipeline.model_dump(),''',
        '''        language=state.language,
        dialect=state.dialect,
        state=state.state.value,
        current_topic=state.current_topic,
        current_section=state.current_section,
        interrupt_count=state.interrupt_count,
        resume_count=state.resume_count,
        active_pipeline=state.active_pipeline.model_dump(),''',
    ),
    (
        '''        state=state.state.value,
        language=state.language,
        current_topic=state.current_topic,''',
        '''        state=state.state.value,
        language=state.language,
        dialect=state.dialect,
        current_topic=state.current_topic,''',
    ),
    (
        '''        out.append(
            {
                "code": code,
                "name": LANGUAGE_NAMES[code],
                "primary_pipeline": plans[0].as_dict() if plans else None,''',
        '''        entry = {
            "code": code,
            "name": LANGUAGE_NAMES[code],
            "primary_pipeline": plans[0].as_dict() if plans else None,
            "fallback_pipelines": [p.as_dict() for p in plans[1:4]],
            "realtime_native": bool(plans and plans[0].pipeline.mode == "realtime"),
        }
        if code == "ar":
            # Arabic is one language but two registers: the student picks which
            # one the tutor *sounds* like (see app/voice/dialects.py).
            entry["dialects"] = arabic_dialect_options()
        out.append(entry)
        continue
        out.append(  # pragma: no cover - unreachable, kept for shape reference
            {
                "code": code,
                "name": LANGUAGE_NAMES[code],
                "primary_pipeline": plans[0].as_dict() if plans else None,''',
    ),
    (
        '''from app.voice.state import LANGUAGE_NAMES, SUPPORTED_LANGUAGES''',
        '''from app.voice.dialects import arabic_dialect_options
from app.voice.state import LANGUAGE_NAMES, SUPPORTED_LANGUAGES''',
    ),
])

# --------------------------------------------------------------------------- #
# 2. the manager: normalise once, carry it everywhere
# --------------------------------------------------------------------------- #

sub("app/voice/session_manager.py", [
    (
        '''        document_ids: list[str] | None = None,
        resume_latest: bool = False,
    ) -> VoiceSession:
        language = validate_language(language)''',
        '''        document_ids: list[str] | None = None,
        dialect: str | None = None,
        resume_latest: bool = False,
    ) -> VoiceSession:
        language = validate_language(language)
        # Arabic only: which register the tutor speaks (`ar-EG` default / `ar-MSA`).
        dialect = normalise_dialect(language, dialect)''',
    ),
    (
        '''                state = VoiceSessionState(
                    student_id=student_id,
                    course_id=course_id or previous.course_id,
                    lesson_id=lesson_id or previous.lesson_id,
                    language=language,''',
        '''                state = VoiceSessionState(
                    student_id=student_id,
                    course_id=course_id or previous.course_id,
                    lesson_id=lesson_id or previous.lesson_id,
                    language=language,
                    dialect=dialect or previous.dialect,''',
    ),
    (
        '''        state = VoiceSessionState(
            student_id=student_id,
            course_id=course_id,
            lesson_id=lesson_id,
            language=language,''',
        '''        state = VoiceSessionState(
            student_id=student_id,
            course_id=course_id,
            lesson_id=lesson_id,
            language=language,
            dialect=dialect,''',
    ),
    (
        '''        instruction = build_system_instruction(
            language=self.state.language,
            lesson_context=lesson_context,
            learner_context=self.learner_context,
            checkpoint=checkpoint,
        )''',
        '''        instruction = build_system_instruction(
            language=self.state.language,
            dialect=self.state.dialect,
            lesson_context=lesson_context,
            learner_context=self.learner_context,
            checkpoint=checkpoint,
        )''',
    ),
    (
        '''            metadata={
                "student_id": self.state.student_id,
                "topic_id": self.state.topic_id,''',
        '''            metadata={
                "student_id": self.state.student_id,
                "dialect": self.state.dialect,
                "topic_id": self.state.topic_id,''',
    ),
    (
        '''from app.voice.state import (''',
        '''from app.voice.dialects import normalise_dialect
from app.voice.state import (''',
    ),
])

# --------------------------------------------------------------------------- #
# 3. prompts: the register sentence, and the fusHa lines themselves
# --------------------------------------------------------------------------- #

sub("app/prompts/system.py", [
    (
        '''def build_system_instruction(
    *,
    language: str,''',
        '''def build_system_instruction(
    *,
    language: str,
    dialect: str | None = None,''',
    ),
    (
        '''        language_instruction(language),''',
        '''        language_instruction(language),
        arabic_dialect_instruction(dialect),''',
    ),
])

sub("app/prompts/languages.py", [
    (
        '''from app.voice.state import LANGUAGE_NAMES, SUPPORTED_LANGUAGES''',
        '''from app.voice.dialects import DEFAULT_ARABIC_DIALECT
from app.voice.state import LANGUAGE_NAMES, SUPPORTED_LANGUAGES''',
    ),
])

s = read("app/prompts/system.py")
assert "arabic_dialect_instruction" in s
sub("app/prompts/system.py", [(
    '''from app.prompts.languages import language_instruction, language_name''',
    '''from app.prompts.languages import (
    arabic_dialect_instruction,
    language_instruction,
    language_name,
)''',
)])

# the two registers, as instructions the model can actually follow
s = read("app/prompts/languages.py")
assert 'return LANGUAGE_NAMES.get(language, "English")' in s
s += '''

#: Arabic is taught in two registers. The language instruction above already says
#: "speak Arabic"; this says *which* Arabic, in the language itself, so a live
#: model does not drift into a third register halfway through a lesson.
ARABIC_DIALECT_INSTRUCTIONS: dict[str, str] = {
    "ar-EG": (
        "تحدّث باللهجة المصرية الطبيعية كما يتحدث بها الناس في مصر: مفردات دارجة، "
        "إيقاع كلام عادي، وبساطة في الجمل. تجنّب الفصحى الرسمية في الشرح، "
        "وابقَ على المصطلحات التقنية بالإنجليزية كما هي."
    ),
    "ar-MSA": (
        "تحدّث بالعربية الفصحى المعاصرة الواضحة، بلغة محاضرة جامعية مبسّطة: جمل قصيرة، "
        "مفردات دقيقة، بلا عامية وبلا تعقيد بلاغي. أبقِ المصطلحات التقنية بالإنجليزية كما هي."
    ),
}


def arabic_dialect_instruction(dialect: str | None) -> str:
    """The register sentence for an Arabic session (empty for other languages)."""
    if not dialect:
        return ""
    return ARABIC_DIALECT_INSTRUCTIONS.get(dialect, ARABIC_DIALECT_INSTRUCTIONS[DEFAULT_ARABIC_DIALECT])
'''
write("app/prompts/languages.py", s)

# fusHa lines: the same teaching moves, in the register a lecture is delivered in
s = read("app/prompts/interaction.py")
assert "LANGUAGE_SWITCH_MARKER" in s
s = s.replace(
    'LANGUAGE_SWITCH_MARKER = "The student switched the lesson language"',
    '''LANGUAGE_SWITCH_MARKER = "The student switched the lesson language"


# --------------------------------------------------------------------------- #
# Arabic in fusHa ("ar-msa")
# --------------------------------------------------------------------------- #
# The same lines as `ar`, in the register a university lecture is delivered in.
# Selected by the session's dialect (app/voice/dialects.py); everything that asks
# "which language?" still sees `ar`, so routing and learning state are untouched.

INTERACTION_PHRASES["ar-msa"] = {
    "put_simply": "ببساطة: {goal}",
    "holding": "خُذ وقتك، أنا في انتظارك.",
    "which_part": "أي جزء غير واضح — {title}، أم الذي يليه؟",
    "step_plain": "{title} — {goal}.",
    "topic_line": "نتناول اليوم {topic}.",
    "step_one": "الخطوة الأولى: {title} — {goal}.",
    "next_step": "الخطوة التالية: {title} — {goal}.",
    "on_step": "نحن الآن في {title}: {goal}.",
    "on_current": "فيما يخص {title}: {goal}.",
    "think_of": "تصوّر {title} على النحو التالي: {goal}",
    "smaller": "لنوضّحها بخطوة أصغر: {goal}",
    "nothing_more": "لا أكثر من ذلك.",
    "check": "هل الأمر واضح حتى هنا؟",
    "praise": "بالضبط، أحسنت.",
    "rephrase": "لا مشكلة، دعني أشرحها بطريقة أخرى.",
    "simpler": "دعني أبسّطها قليلًا.",
    "encourage": "خُذ وقتك.",
    "next": "حسنًا، نُكمل.",
    "example": "هل تحب أن أعطيك مثالًا واضحًا؟",
    "invite": "ما الذي تريد أن أوضّحه بالتحديد؟",
    "close": "هذه هي الخطة كاملة. ماذا تحب أن نفعل بعد ذلك؟",
    "switch": "سنُكمل بالعربية من هنا.",
    "answer_ack": "سؤال جيد.",
}

PHRASE_VARIANTS["ar-msa"] = {
    "check": ("أُكمل؟", "هل تحب مثالًا قبل أن نُكمل؟", "واضحة هكذا أم أعيدها بطريقة أخرى؟"),
    "praise": ("أحسنت.", "ممتاز، لقد فهمتها."),
    "rephrase": ("دعني أقترب منها من زاوية أخرى.", "حسنًا، بطريقة أخرى."),
    "encourage": ("لا عجلة.",),
    "close": ("وهذا كل ما كان يجب أن نغطيه.",),
    "going_on": ("حسنًا — وهذا يوصلنا إلى ما يلي:",),
    "invite_stop": ("قاطعني في أي وقت.",),
}

STEP_LEAD["ar-msa"] = (
    "{title}. {goal}.",
    "حسنًا، {title}. {goal}.",
    "الآن، {title}: {goal}.",
    "{title}، والفكرة هنا أنّ {goal}.",
)

MOVE_ON["ar-msa"] = ("أولًا.", "حسنًا.", "الآن.", "جيد.", "انظر.")

REACT["ar-msa"] = ("نعم.", "حسنًا.", "طيب.", "جيد.")''',
    1,
)
write("app/prompts/interaction.py", s)

# a fusHa greeting for the opening line
sub("app/curriculum.py", [(
    '''LOCALISED_GREETINGS: dict[str, str] = {
    "en": "Hello, let's begin.",''',
    '''LOCALISED_GREETINGS: dict[str, str] = {
    "en": "Hello, let's begin.",
    #: Arabic in fusHa, used when the session is set to the `ar-MSA` register.
    "ar-msa": "مرحبًا بك، لنبدأ الدرس.",''',
)])
print("1-3 ok")
