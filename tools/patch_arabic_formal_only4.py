"""Round 17, take 2: instruction, greeting, default voice, comment.

Run once from the service root:  python3 tools/patch_arabic_formal_only4.py
"""
import io


def read(p):
    return io.open(p, encoding="utf-8").read()


def write(p, s):
    io.open(p, "w", encoding="utf-8").write(s)


def sub(path, pairs):
    s = read(path)
    for old, new in pairs:
        assert old in s, (path, old[:60])
        s = s.replace(old, new, 1)
    write(path, s)


sub("app/prompts/languages.py", [
    (
        '''    "ar": (
        "تحدّث بالعربية فقط. استخدم عربية طبيعية وواضحة ومناسبة لطالب جامعي، وإذا كان الطالب "
        "يستخدم اللهجة المصرية فتحدّث بالمصرية بشكل طبيعي. احتفظ بالمصطلحات التقنية بصيغتها "
        "الإنجليزية المتعارف عليها (مثل binary search و array) ولا تترجمها ترجمة حرفية. "
        "لا تنتقل إلى لغة أخرى إلا إذا طلب الطالب ذلك صراحةً."
    ),''',
        '''    "ar": (
        "تحدّث بالعربية فقط، وبالفصحى المعاصرة الواضحة وبأسلوب محاضرة جامعية مبسّطة: جمل "
        "قصيرة، ومفردات دقيقة، بلا عامية وبلا تعقيد بلاغي. احتفظ بالمصطلحات التقنية بصيغتها "
        "الإنجليزية المتعارف عليها (مثل binary search و array) ولا تترجمها ترجمة حرفية. "
        "لا تنتقل إلى لغة أخرى ولا إلى العامية إلا إذا طلب الطالب ذلك صراحةً."
    ),''',
    ),
    (
        '''#: Arabic is taught in two registers. The language instruction above already says
#: "speak Arabic"; this says *which* Arabic, in the language itself, so a live
#: model does not drift into a third register halfway through a lesson.
ARABIC_DIALECT_INSTRUCTIONS: dict[str, str] = {
    "ar-EG": (
        "تحدّث باللهجة المصرية الطبيعية كما يتحدث بها الناس في مصر: مفردات دارجة، "
        "إيقاع كلام عادي، وبساطة في الجمل. تجنّب الفصحى الرسمية في الشرح، "
        "وابقَ على المصطلحات التقنية بالإنجليزية كما هي."
    ),
    "ar-MSA": (''',
        '''#: Arabic is taught in fusHa. The language instruction above already says "speak
#: Arabic"; this says *which* Arabic, in the language itself, so a live model does
#: not drift into a dialect halfway through a lesson.
ARABIC_DIALECT_INSTRUCTIONS: dict[str, str] = {
    "ar-MSA": (''',
    ),
])

sub("app/curriculum.py", [
    (
        '''    "ar": "مرحبا، لنبدأ الدرس.",''',
        '''    "ar": "مرحبًا بك، لنبدأ الدرس.",''',
    ),
    (
        '''    #: Arabic in fusHa, used when the session is set to the `ar-MSA` register.
    "ar-msa": "مرحبًا بك، لنبدأ الدرس.",
''',
        "",
    ),
])

sub("app/providers/azure/tts.py", [
    (
        '''    "ar": "ar-EG-SalmaNeural",''',
        '''    #: Arabic is taught in fusHa: `ar-SA-ZariyahNeural` (see app/voice/dialects.py).
    "ar": "ar-SA-ZariyahNeural",''',
    ),
    (
        '''Arabic has two registers here and they are different voices, not different
settings: `ar-EG-SalmaNeural` (Egyptian) and `ar-SA-ZariyahNeural` (fusHa). The''',
        '''Arabic is spoken in fusHa (`ar-SA-ZariyahNeural`); an Egyptian voice
(`ar-EG-SalmaNeural`) is still one `AZURE_VOICE_OVERRIDES` entry away. The''',
    ),
])

sub("app/providers/mock/dialogue.py", [
    (
        '''    #: Which phrase table answers: Arabic in fusHa has its own (`ar-msa`), while
    #: `language` stays `ar` for localisation, separators and canonical concepts.''',
        '''    #: Which phrase table answers - today always the language itself. Arabic's
    #: table is the formal one; the hook stays so a second register can be added
    #: again without touching the dialogue.''',
    ),
])
print("instruction + greeting + voice + comments ok")
