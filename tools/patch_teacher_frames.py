"""Round 20: teaching frames + a stronger "teach like a teacher" instruction.

Run once from the service root:  python3 tools/patch_teacher_frames.py
"""
import io


def sub(path, pairs):
    s = io.open(path, encoding="utf-8").read()
    for old, new in pairs:
        assert old in s, (path, old[:70])
        s = s.replace(old, new, 1)
    io.open(path, "w", encoding="utf-8").write(s)


TEACH = '''
#: Teaching frames — the connective sentences that turn a list of grounded moves
#: into the explanation a teacher would actually give, in one turn. Used by
#: `app/learning/lesson_script.py`: the topic sentence of the part being taught,
#: the picture, the worked example, the trap, the promise of what comes next.
TEACH: dict[str, dict[str, str]] = {
    "en": {
        "picture": "Picture it like this.",
        "example": "Let's walk a small example together.",
        "watch": "This is where people slip.",
        "use": "And this is where you meet it in real work.",
        "why": "Now, why does that hold?",
        "next": "Once that is solid, we go on to",
        "back": "Back to where we were.",
        "plainer": "Let me say the same thing in smaller words.",
        "turn": "Your turn:",
    },
    "ar": {
        "picture": "تخيّل معي الصورة هذه.",
        "example": "لنمشِ معًا على مثال صغير.",
        "watch": "هنا يقع أكثر الناس في الخطأ.",
        "use": "وهنا ستقابلها في العمل الحقيقي.",
        "why": "والآن، لماذا يصح هذا؟",
        "next": "وبعد أن يثبت هذا، ننتقل إلى",
        "back": "نعود إلى ما كنا نشرحه.",
        "plainer": "دعني أقولها بكلمات أبسط.",
        "turn": "دورك الآن:",
    },
    "fr": {
        "picture": "Imagine-le comme ceci.",
        "example": "Prenons ensemble un petit exemple.",
        "watch": "C'est là que tout le monde se trompe.",
        "use": "Et c'est là que tu la rencontres en pratique.",
        "why": "Maintenant, pourquoi cela tient-il ?",
        "next": "Une fois cela acquis, nous passons à",
        "back": "Revenons à ce que nous disions.",
        "plainer": "Je le dis avec des mots plus simples.",
        "turn": "À toi :",
    },
    "sw": {
        "picture": "Fikiria hivi.",
        "example": "Hebu tupitie mfano mdogo pamoja.",
        "watch": "Hapa ndipo wengi wanakosea.",
        "use": "Na hapa ndipo unapokutana nayo kazini.",
        "why": "Sasa, kwa nini hii inashikilia?",
        "next": "Hili likishakaa, tunaenda kwa",
        "back": "Turudi tulipokuwa.",
        "plainer": "Niseme kwa maneno rahisi.",
        "turn": "Zamu yako:",
    },
    "am": {
        "picture": "እንዲህ አድርገህ አስብ።",
        "example": "በትንሽ ምሳሌ አብረን እንሂድ።",
        "watch": "ብዙዎች የሚሳሳቱት እዚህ ነው።",
        "use": "በእውነተኛ ሥራ የምትገናኘውም እዚህ ነው።",
        "why": "አሁን፣ ይህ ለምን ይሠራል?",
        "next": "ይህ ከጸና በኋላ ወደሚከተለው እንሄዳለን",
        "back": "ወደነበርንበት እንመለስ።",
        "plainer": "በቀላል ቃላት ልናገረው።",
        "turn": "የአንተ ተራ፦",
    },
    "ha": {
        "picture": "Ka yi tunanin haka.",
        "example": "Mu bi ɗan ƙaramin misali tare.",
        "watch": "Anan ne yawancin mutane suke kuskure.",
        "use": "Kuma anan za ka same ta a aikin gaske.",
        "why": "Yanzu, me ya sa wannan yake aiki?",
        "next": "Idan wannan ya tabbata, za mu je ga",
        "back": "Mu koma inda muka tsaya.",
        "plainer": "Bari in faɗe shi da kalmomi masu sauƙi.",
        "turn": "Naka ne yanzu:",
    },
    "so": {
        "picture": "U malee sidan.",
        "example": "Aan wada tillaabo yar oo tusaale ah.",
        "watch": "Halkan ayaa dadka badankood ku qaldamaan.",
        "use": "Halkan ayaad kala kulmi doontaa shaqada dhabta ah.",
        "why": "Hadda, maxay tani u shaqaysaa?",
        "next": "Markii tan adkaato, waxaan u gudubnaa",
        "back": "Aan ku noqono wixii aan ka hadlaynay.",
        "plainer": "Aan ku dhaho erayo fudud.",
        "turn": "Adigaa hadda:",
    },
    "yo": {
        "picture": "Fojú inú wò ó báyìí.",
        "example": "Ẹ jẹ́ ká gbé àpẹẹrẹ kékeré kan pọ̀.",
        "watch": "Ibí yìí ni ọ̀pọ̀ ènìyàn ti ń ṣe àṣìṣe.",
        "use": "Ibí yìí náà ni wàá ti pàdé rẹ̀ ní iṣẹ́ gidi.",
        "why": "Nísinsìnyí, kí ló fà á tí èyí fi ń ṣiṣẹ́?",
        "next": "Bí èyí bá ti fẹsẹ̀ múlẹ̀, a máa lọ sí",
        "back": "Ẹ jẹ́ ká padà sí ibi tí a ti wà.",
        "plainer": "Ẹ jẹ́ kí n sọ ọ́ ní ọ̀rọ̀ tó rọrùn.",
        "turn": "Ìgbà tìẹ ni:",
    },
    "ig": {
        "picture": "Chee ya otú a.",
        "example": "Ka anyị jiri obere ihe atụ gaa.",
        "watch": "Ọ bụ ebe a ka ọtụtụ na-emehie.",
        "use": "Ọ bụkwa ebe a ka ị ga-ahụ ya n'ọrụ n'ezie.",
        "why": "Ugbu a, gịnị mere nke a ji arụ ọrụ?",
        "next": "Ozugbo nke a kwụsịrị, anyị ga-aga na",
        "back": "Ka anyị laghachi ebe anyị nọ.",
        "plainer": "Ka m kwuo ya n'okwu dị mfe.",
        "turn": "Oge gị:",
    },
    "zu": {
        "picture": "Cabanga ngalokhu.",
        "example": "Ake sihambe ngesibonelo esincane ndawonye.",
        "watch": "Yilapho iningi liziphambanisa khona.",
        "use": "Futhi yilapho uzohlangana nayo emsebenzini wangempela.",
        "why": "Manje, kungani lokhu kusebenza?",
        "next": "Uma lokhu sekuginile, siqhubekela ku",
        "back": "Ake sibuyele lapho sasikhona.",
        "plainer": "Ake ngikusho ngamazwi alula.",
        "turn": "Eyaku:",
    },
}


def teach_frame(language: str | None, key: str) -> str:
    """A connective sentence in the lesson language (English if uncurated)."""
    table = TEACH.get((language or "en")[:2]) or TEACH["en"]
    return table.get(key) or TEACH["en"][key]


'''

sub("app/prompts/interaction.py", [
    (
        "STEP_LEAD: dict[str, tuple[str, ...]] = {",
        TEACH.lstrip("\n") + "STEP_LEAD: dict[str, tuple[str, ...]] = {",
    ),
    (
        """- Teach and keep teaching. You do NOT have to ask a question at the end of every step —
  usually you just move on and let the student interrupt you. Ask something only when it
  earns its place: a tricky idea, a likely misconception, or the student has gone quiet.""",
        """- Teach and keep teaching. You do NOT have to ask a question at the end of every step —
  usually you just move on and let the student interrupt you. Ask something only when it
  earns its place: a tricky idea, a likely misconception, or the student has gone quiet.
- Explain like a teacher, not like a caption. A turn is a *pass of teaching*: say what this
  part is about, develop each idea with its reason, ground it with one concrete example or
  number, warn about the mistake, then stop and give the student the floor. Five to nine
  sentences is normal; a single sentence followed by "any questions?" is not teaching.
- Never end every turn with a question, and never with "do you have any questions?". The
  student knows they can interrupt; you just keep teaching until they do.""",
    ),
])
print("teaching frames added")
