"""Per-language instructions (§44).

Each instruction is written *in* the target language so the model is anchored
in it, and explicitly forbids drifting back to English. Technical terminology
is preserved rather than force-translated (§14).
"""

from __future__ import annotations

from app.voice.dialects import DEFAULT_ARABIC_DIALECT
from app.voice.state import LANGUAGE_NAMES, SUPPORTED_LANGUAGES

LANGUAGE_INSTRUCTIONS: dict[str, str] = {
    "en": (
        "Speak English only. Use clear, natural spoken English for a university student. "
        "Keep technical terms in their standard English form. Do not switch to another "
        "language unless the student explicitly asks you to."
    ),
    "ar": (
        "تحدّث بالعربية فقط، وبالفصحى المعاصرة الواضحة وبأسلوب محاضرة جامعية مبسّطة: جمل "
        "قصيرة، ومفردات دقيقة، بلا عامية وبلا تعقيد بلاغي. احتفظ بالمصطلحات التقنية بصيغتها "
        "الإنجليزية المتعارف عليها (مثل binary search و array) ولا تترجمها ترجمة حرفية. "
        "لا تنتقل إلى لغة أخرى ولا إلى العامية إلا إذا طلب الطالب ذلك صراحةً."
    ),
    "fr": (
        "Parle uniquement en français. Utilise un français oral naturel et clair, adapté à un "
        "étudiant universitaire. Conserve les termes techniques dans leur forme standard "
        "(binary search, array, pointeur). Ne change pas de langue sauf demande explicite de l'étudiant."
    ),
    "sw": (
        "Ongea kwa Kiswahili pekee. Tumia Kiswahili sanifu na cha mazungumzo kinachofaa kwa "
        "mwanafunzi wa chuo kikuu. Hifadhi istilahi za kiufundi katika umbo lake la Kiingereza "
        "(binary search, array). Usibadilishe lugha isipokuwa mwanafunzi akiomba waziwazi."
    ),
    "am": (
        "በአማርኛ ብቻ ተናገር። ለዩኒቨርሲቲ ተማሪ የሚመጥን ግልጽና ተፈጥሯዊ የንግግር አማርኛ ተጠቀም። "
        "ቴክኒካዊ ቃላትን በእንግሊዝኛ መልካቸው አቆይ (binary search, array)። "
        "ተማሪው በግልጽ ካልጠየቀ በስተቀር ወደ ሌላ ቋንቋ አትሂድ።"
    ),
    "ha": (
        "Yi magana da Hausa kawai. Yi amfani da Hausa mai sauƙi da ta dace da ɗalibin jami'a. "
        "Ka bar kalmomin fasaha a sigar Turanci (binary search, array). "
        "Kada ka sauya harshe sai idan ɗalibin ya nemi hakan a fili."
    ),
    "so": (
        "Kaliya Af-Soomaali ku hadal. Isticmaal Af-Soomaali cad oo dabiici ah oo ku habboon "
        "arday jaamacadeed. Ereyada farsamada ku hayso qaabkooda Ingiriisiga ah "
        "(binary search, array). Luqadda ha beddelin ilaa ardaygu si cad u codsado."
    ),
    "yo": (
        "Sọ èdè Yorùbá nìkan. Lo Yorùbá tí ó ṣe kedere tí ó sì bá akẹ́kọ̀ọ́ yunifásítì mu. "
        "Fi àwọn ọ̀rọ̀ ìmọ̀-ẹ̀rọ sílẹ̀ ní èdè Gẹ̀ẹ́sì (binary search, array). "
        "Má ṣe yí èdè padà àfi tí akẹ́kọ̀ọ́ bá béèrè ní gbangba."
    ),
    "ig": (
        "Kwuo naanị n'asụsụ Igbo. Jiri Igbo doro anya nke dabara nwa akwụkwọ mahadum. "
        "Hapụ okwu teknụzụ n'ụdị Bekee ha (binary search, array). "
        "Agbanwela asụsụ ma ọ bụrụ na nwa akwụkwọ arịọ ya n'ụzọ doro anya."
    ),
    "zu": (
        "Khuluma isiZulu kuphela. Sebenzisa isiZulu esicacile nesemvelo esifanele umfundi "
        "wasenyuvesi. Gcina amagama obuchwepheshe esimweni sawo sesiNgisi (binary search, array). "
        "Ungashintshi ulimi ngaphandle uma umfundi ecela ngokusobala."
    ),
}

# Short, natural "go ahead and ask" line used when the student interrupts (§72).
INTERRUPT_ACK: dict[str, str] = {
    "en": "Of course — go ahead, what's your question?",
    "ar": "طبعًا، اتفضل اسأل سؤالك.",
    "fr": "Bien sûr — vas-y, quelle est ta question ?",
    "sw": "Bila shaka — endelea, swali lako ni lipi?",
    "am": "በእርግጥ — ጠይቅ፣ ጥያቄህ ምንድን ነው?",
    "ha": "Tabbas — ci gaba, menene tambayarka?",
    "so": "Dabcan — sii wad, su'aashaadu waa maxay?",
    "yo": "Dájúdájú — béèrè, kí ni ìbéèrè rẹ?",
    "ig": "N'ezie — jụọ, gịnị bụ ajụjụ gị?",
    "zu": "Impela — qhubeka, umbuzo wakho uthini?",
}

RESUME_TRANSITION: dict[str, str] = {
    "en": "Let's continue from where we stopped.",
    "ar": "تمام، نكمل من حيث وقفنا.",
    "fr": "Reprenons là où nous nous étions arrêtés.",
    "sw": "Tuendelee kutoka pale tulipoishia.",
    "am": "ካቆምንበት እንቀጥል።",
    "ha": "Mu ci gaba daga inda muka tsaya.",
    "so": "Aan ka sii wadno meeshii aan joojinay.",
    "yo": "Jẹ́ kí a tẹ̀síwájú láti ibi tí a ti dúró.",
    "ig": "Ka anyị gaa n'ihu site ebe anyị kwụsịrị.",
    "zu": "Masiqhubeke lapho besigcine khona.",
}


def language_instruction(language: str) -> str:
    return LANGUAGE_INSTRUCTIONS.get(language, LANGUAGE_INSTRUCTIONS["en"])


def language_name(language: str) -> str:
    return LANGUAGE_NAMES.get(language, "English")


def interrupt_ack(language: str) -> str:
    return INTERRUPT_ACK.get(language, INTERRUPT_ACK["en"])


def resume_transition(language: str) -> str:
    return RESUME_TRANSITION.get(language, RESUME_TRANSITION["en"])


def validate_language(language: str | None) -> str:
    lang = (language or "en").strip().lower()
    if lang not in SUPPORTED_LANGUAGES:
        return "en"
    return lang


#: Arabic is taught in fusHa. The language instruction above already says "speak
#: Arabic"; this says *which* Arabic, in the language itself, so a live model does
#: not drift into a dialect halfway through a lesson.
ARABIC_DIALECT_INSTRUCTIONS: dict[str, str] = {
    "ar-MSA": (
        "تحدّث بالعربية الفصحى المعاصرة كما يكتبها مدرّس عربي أصيل: صياغة طبيعية سلسة "
        "سليمة النحو والإملاء تماماً، وليست ترجمة حرفية من الإنجليزية. عبّر عن كل فكرة "
        "بما يعادلها الطبيعي المألوف في العربية، بجمل قصيرة واضحة ومفردات دقيقة، بلا عامية "
        "وبلا تعقيد بلاغي. أبقِ المصطلحات التقنية بالإنجليزية كما هي."
    ),
    "ar-EG": (
        "تحدّث باللهجة المصرية الأكاديمية المهذّبة كما يشرح مدرّس مصري مثقّف: صياغة طبيعية "
        "سلسة سليمة، وليست ترجمة حرفية من الإنجليزية، وبدون عامية سوقية وبدون أخطاء إملائية. "
        "عبّر عن كل فكرة بما يقوله مدرس مصري بالعامية المثقفة، بجمل قصيرة واضحة. "
        "أبقِ المصطلحات التقنية بالإنجليزية كما هي."
    ),
}


def arabic_dialect_instruction(dialect: str | None) -> str:
    """The register sentence for an Arabic session (empty for other languages)."""
    if not dialect:
        return ""
    return ARABIC_DIALECT_INSTRUCTIONS.get(dialect, ARABIC_DIALECT_INSTRUCTIONS[DEFAULT_ARABIC_DIALECT])
