"""Round 18: the formal-Arabic sweep - words, comments and the last Egyptian lines.

Run once from the service root:  python3 tools/patch_arabic_formal_only5.py
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
# the last Egyptian sentences the mock actually speaks
# --------------------------------------------------------------------------- #

sub("app/prompts/interaction.py", [
    (
        '''        "encourage": ["لا عجلة."],''',
        '''        "encourage": ["لا داعي للعجلة، خذ وقتك."],''',
    ),
    (
        '''        "invite_stop": ["قاطعني في أي وقت."],
    },    "fr": {''',
        '''        "invite_stop": ["يمكنك أن تقاطعني في أي وقت."],
    },
    "fr": {''',
    ),
    (
        '''    "ar": ("نعم.", "حسنًا.", "طيب.", "جيد."),    "fr": ("Mmm.", "D'accord.", "Oui.", "Je vois."),''',
        '''    "ar": ("نعم.", "حسنًا.", "فهمت.", "جيد."),
    "fr": ("Mmm.", "D'accord.", "Oui.", "Je vois."),''',
    ),
])

# --------------------------------------------------------------------------- #
# the curated Arabic lesson plan: fusHa, not Egyptian
# --------------------------------------------------------------------------- #

sub("app/curriculum_localisation.py", [
    (
        '''The course catalogue is written in English (`app/curriculum.py`); the tutoring
around it is localised. With a real voice this gap becomes audible: an Egyptian
voice reading *"The idea of halving. Compare with the middle…"* in the middle of
an Arabic sentence sounds like a machine switching languages mid-breath.''',
        '''The course catalogue is written in English (`app/curriculum.py`); the tutoring
around it is localised. With a real voice this gap becomes audible: an Arabic
voice reading *"The idea of halving. Compare with the middle…"* in the middle of
an Arabic sentence sounds like a machine switching languages mid-breath.''',
    ),
    (
        '''            "The idea of halving": (
                "فكرة التنصيف",
                "نقارن بالعنصر اللي في النص، ونرمي النص اللي مستحيل يكون فيه الهدف",
            ),
            "Trace it on a small array": (
                "نمشي على مثال صغير",
                "16 عنصر، بعدها 8، بعدها 4، بعدها 2، لحد ما نوصل للعنصر",
            ),
            "Why the cost is logarithmic": (
                "ليه التكلفة لوغاريتمي",
                "المجال بيبقى نص كل خطوة، فعدد الخطوات لوغاريتم العدد",
            ),
            "Common mistakes": (
                "الأخطاء الشائعة",
                "مصفوفة غير مرتبة، وحساب النص بطريقة بتعمل overflow",
            ),''',
        '''            "The idea of halving": (
                "فكرة التنصيف",
                "نقارن بالعنصر الأوسط، ونُهمل النصف الذي يستحيل أن يحتوي على الهدف",
            ),
            "Trace it on a small array": (
                "نتتبّع الخطوات على مصفوفة صغيرة",
                "16 عنصرًا، ثم 8، ثم 4، ثم 2، حتى نصل إلى العنصر",
            ),
            "Why the cost is logarithmic": (
                "لماذا التكلفة لوغاريتمية",
                "يتنصّف المجال في كل خطوة، فيكون عدد الخطوات لوغاريتم عدد العناصر",
            ),
            "Common mistakes": (
                "الأخطاء الشائعة",
                "مصفوفة غير مرتبة، وحساب نقطة المنتصف بطريقة تسبب overflow",
            ),''',
    ),
    (
        '''            "The base case": (
                "الحالة الأساسية",
                "لازم يكون فيه شرط بيوقف الاستدعاء، من غيره البرنامج بيلف على الفاضي",
            ),
            "The recursive case": (
                "الحالة التكرارية",
                "نحل جزء صغير من المسألة، ونسيب الباقي لنفس الدالة",
            ),
            "The stack unwinds": (
                "رجوع الاستدعاءات",
                "لما نوصل للحالة الأساسية، كل استدعاء بيرجع بالترتيب العكسي",
            ),
            "When recursion is the wrong tool": (
                "إمتى ما نستخدمش الاستدعاء الذاتي",
                "أحيانًا الحلقة العادية أوضح وأوفر في الذاكرة",
            ),''',
        '''            "The base case": (
                "الحالة الأساسية",
                "لا بد من شرط يوقف الاستدعاء، وإلا استمر البرنامج بلا نهاية",
            ),
            "The recursive case": (
                "الحالة التكرارية",
                "نحل جزءًا صغيرًا من المسألة، ونترك الباقي للدالة نفسها",
            ),
            "The stack unwinds": (
                "عودة الاستدعاءات",
                "عند الوصول إلى الحالة الأساسية تعود الاستدعاءات بالترتيب العكسي",
            ),
            "When recursion is the wrong tool": (
                "متى لا نستخدم الاستدعاء الذاتي",
                "أحيانًا تكون الحلقة العادية أوضح وأقل استهلاكًا للذاكرة",
            ),''',
    ),
    (
        '''            "Divide": (
                "التقسيم",
                "نقسّم المصفوفة نصين وندي كل نص لنفس الدالة",
            ),
            "Conquer": (
                "الترتيب",
                "لما يوصل النص لعنصر واحد يبقى مترتب خلاص",
            ),
            "The merge step": (
                "خطوة الدمج",
                "نقارن أول عنصر من كل نص وناخد الأصغر، لحد ما القايمتين يخلصوا",
            ),
            "Cost and stability": (
                "التكلفة والاستقرار",
                "التكلفة n لوغاريتم n، والترتيب مستقر بس محتاج ذاكرة إضافية",
            ),''',
        '''            "Divide": (
                "التقسيم",
                "نقسم المصفوفة إلى نصفين، ونسلّم كل نصف إلى الدالة نفسها",
            ),
            "Conquer": (
                "الترتيب",
                "عندما يصل النصف إلى عنصر واحد يكون مرتبًا",
            ),
            "The merge step": (
                "خطوة الدمج",
                "نقارن أول عنصر من كل نصف فنأخذ الأصغر، حتى تنتهي القائمتان",
            ),
            "Cost and stability": (
                "التكلفة والاستقرار",
                "التكلفة n لوغاريتم n، والترتيب مستقر لكنه يحتاج ذاكرة إضافية",
            ),''',
    ),
])

# --------------------------------------------------------------------------- #
# comments that still describe the cancelled register
# --------------------------------------------------------------------------- #

sub(".env.example", [
    ("#: Per-language voice overrides, e.g. ar:ar-EG-ShakirNeural,en:en-US-JennyNeural",
     "#: Per-language voice overrides, e.g. ar:ar-SA-HamedNeural,en:en-US-JennyNeural"),
])

sub("app/config.py", [
    ('#: Per-language voice overrides, e.g. "ar:ar-EG-ShakirNeural,en:en-US-JennyNeural".',
     '#: Per-language voice overrides, e.g. "ar:ar-SA-HamedNeural,en:en-US-JennyNeural".'),
])

sub("app/api/schemas.py", [
    (
        '''    #: Arabic register: "ar-EG" (Egyptian, default) or "ar-MSA" (fusHa). Ignored
    #: for the other nine languages; aliases ("egyptian", "msa", "fusha") work.''',
        '''    #: Arabic register. Arabic is taught in "ar-MSA" (fusHa) and every value
    #: resolves to it - older clients that still send "ar-EG" or "egyptian" are
    #: accepted and answered in fusHa. Ignored for the other nine languages.''',
    ),
    (
        '''    #: Language code, or an Arabic register (`ar-MSA` / `ar-EG`).''',
        '''    #: Language code, or an Arabic register spelling (`ar-MSA`, `ar-EG`, `fusha`…).''',
    ),
])

sub("app/providers/mock/providers.py", [
    (
        '''        #: Arabic register of this session (`ar-EG` / `ar-MSA`), if any.''',
        '''        #: Arabic register of this session (`ar-MSA` today), if any.''',
    ),
    (
        '''        # A vendor voice that has more than one voice for a language (Arabic in
        # fusHa vs Egyptian) needs to know which one this session speaks in.''',
        '''        # A vendor voice that has more than one voice per language (Arabic is
        # taught in fusHa: `ar-SA-ZariyahNeural`) is told which one to use.''',
    ),
])

sub("app/voice/demo_voice.py", [
    (
        '''        Only the vendor needs `dialect` (Arabic: Egyptian vs fusHa voice); the
        synthetic fallback ignores it, which is why this is a soft protocol.''',
        '''        Only the vendor needs `dialect` (Arabic speaks with its fusHa voice); the
        synthetic fallback ignores it, which is why this is a soft protocol.''',
    ),
])

sub("app/voice/session_manager.py", [
    (
        '''        `language` may also name an Arabic register — `ar-MSA`, `ar-EG`, or an
        alias such as `fusha` / `egyptian` — which switches the voice and the
        phrase set while the session stays `ar` for routing and learning state.''',
        '''        `language` may also name an Arabic register — `ar-MSA`, or an older
        Egyptian spelling such as `ar-EG` / `egyptian`. Every spelling resolves to
        the formal register, so an older client is answered in fusHa rather than
        failing, and the session stays `ar` for routing and learning state.''',
    ),
    (
        '''        # Arabic only: which register the tutor speaks (`ar-EG` default / `ar-MSA`).''',
        '''        # Arabic only: which register the tutor speaks — fusHa (`ar-MSA`).''',
    ),
])

sub("app/voice/state.py", [
    (
        '''    #: Arabic only: `ar-EG` (Egyptian, the default) or `ar-MSA` (fusHa). The
    #: language code stays `ar` for routing and learning state; this only changes
    #: the voice, the phrase set and the sentence the instruction adds.''',
        '''    #: Arabic only: the register the tutor speaks — `ar-MSA` (fusHa) today. An
    #: older client may still send `ar-EG`; it normalises to `ar-MSA`. The language
    #: code stays `ar` for routing and learning state; this only decides the voice,
    #: the phrase set and the sentence the instruction adds.''',
    ),
])

# --------------------------------------------------------------------------- #
# the browser voice: prefer the fusHa voice, not the Egyptian one
# --------------------------------------------------------------------------- #

sub("app/static/voice_mode.html", [
    (
        '''/* A UI language code may carry a dialect (`ar-EG` / `ar-MSA`). The service wants''',
        '''/* A UI language code may carry a register (`ar-MSA`, or an older `ar-EG`). The service wants''',
    ),
    (
        """    if(want === 'ar' && /(^|-)eg($|-)|egypt|amira|salma|hoda|shakir/.test(l + ' ' + n)) sc += 6; // we teach Egyptian""",
        """    if(want === 'ar'){                                            // we teach fusHa
      if(l === 'ar' || l === 'ar-sa') sc += 6;                    // …so the standard voice wins
      else if(/^ar-eg/.test(l)) sc -= 2;                          // the dialect voice comes last
      if(/maged|tarik|naayf|zariyah/.test(n)) sc += 2;            // …and its speakers first
    }""",
    ),
])

# --------------------------------------------------------------------------- #
# tests
# --------------------------------------------------------------------------- #

sub("tests/unit/test_azure_tts.py", [
    ('async def _speak(provider, text="أهلاً بيك", language="ar"):',
     'async def _speak(provider, text="أهلاً بك", language="ar"):'),
    ("async def test_requests_the_egyptian_voice_as_raw_pcm(monkeypatch):",
     "async def test_requests_the_arabic_voice_as_raw_pcm(monkeypatch):"),
    ('assert "ar-EG-SalmaNeural" in body and "أهلاً بيك" in body',
     'assert "ar-SA-ZariyahNeural" in body and "أهلاً بك" in body'),
    ('''    settings = _settings(azure_voice_overrides="ar:ar-EG-ShakirNeural, zu:zu-ZA-ThembaNeural")
    assert voice_for("ar", settings) == "ar-EG-ShakirNeural"''',
     '''    settings = _settings(azure_voice_overrides="ar:ar-SA-HamedNeural, zu:zu-ZA-ThembaNeural")
    assert voice_for("ar", settings) == "ar-SA-HamedNeural"'''),
    ('assert voice_for("ar", _settings()) == "ar-EG-SalmaNeural"',
     'assert voice_for("ar", _settings()) == "ar-SA-ZariyahNeural"'),
])

sub("tests/provider/test_mock_audio.py", [
    ('assert spoken.startswith("مرحبا"), f"expected an Arabic greeting, got: {spoken}"',
     'assert spoken.startswith("مرحبًا بك"), f"expected an Arabic greeting, got: {spoken}"'),
    ("# no English plan text leaks into an Egyptian-Arabic turn.",
     "# no English plan text leaks into an Arabic turn."),
    ('assert "هنكمل بالعربي" in spoken',
     'assert "سنُكمل بالعربية" in spoken'),
])

sub("tests/browser/test_client_audio.py", [
    ("""    { name:'Amira', lang:'ar-EG', localService:true, voiceURI:'amira' },
  ]; },""",
     """    { name:'Amira', lang:'ar-EG', localService:true, voiceURI:'amira' },
    { name:'Maged', lang:'ar-SA', localService:true, voiceURI:'maged' },
  ]; },"""),
    ("""handle({ event:'language.changed', to:'ar' });
check('voice_follows_language_switch', /amira/i.test(client.chosenVoiceName || ''),
      { chosen: client.chosenVoiceName, avail: client.voiceAvailability() });""",
     """handle({ event:'language.changed', to:'ar' });
check('voice_follows_language_switch', /maged/i.test(client.chosenVoiceName || ''),
      { chosen: client.chosenVoiceName, avail: client.voiceAvailability() });
check('fusHa_is_preferred_over_the_dialect_voice', !/amira/i.test(client.chosenVoiceName || ''),
      client.chosenVoiceName);"""),
    ('''    assert checks["voice_follows_language_switch"], values
    assert checks["arabic_uses_an_available_voice"], values''',
     '''    assert checks["voice_follows_language_switch"], values
    assert checks["fusHa_is_preferred_over_the_dialect_voice"], values
    assert checks["arabic_uses_an_available_voice"], values'''),
])
print("formal sweep: words, comments, browser voice and tests")
