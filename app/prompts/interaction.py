"""The conversational layer: how the tutor behaves *as a teacher* (§43, §44).

Two things live here:

1. `INTERACTION_SUFFIX` — appended to every system instruction. It is what makes
   the tutor check understanding, react to the student's actual words, rephrase
   instead of repeating, and use the student's name. Real vendors follow it
   (Gemini Live, ElevenLabs, Deepgram all take a system instruction).
2. `INTERACTION_PHRASES` — the same behaviour as short, speakable lines in all
   ten mandatory languages, so the offline demo sounds like it too.

Templates ({title}, {goal}, {topic}) sit alongside the fixed lines, so the
mock's sentence *scaffolding* is in the lesson language too — not just its
interjections. The lesson content itself (the plan's step titles and goals) is the
course material's own English wording; a real vendor translates it naturally, the
mock does not.

On the translations: these are brief, hand-written teaching phrases (matching the
style of `INTERRUPT_ACK` and `RESUME_TRANSITION` in `languages.py`), written to be
short and unambiguous rather than literary. They exist so the demo can be heard in
each language without a vendor key; with real credentials the model produces its
own, natively fluent phrasing and these are only used for the mock. Arabic is
**Modern Standard Arabic (fusHa)** throughout: the Egyptian register was removed
on request, and `ar` is the only Arabic phrase table.

Technical terminology stays in English by design (§14) — a tutor saying "binary
search" inside an Arabic sentence is correct, not a bug.
"""

from __future__ import annotations

from app.prompts.languages import language_name

# --------------------------------------------------------------------------- #
# behaviour, in words the model can follow
# --------------------------------------------------------------------------- #

INTERACTION_SUFFIX = """INTERACTION — you are a person tutoring, not a script being read
- Talk like a real teacher: contractions, short spoken sentences, natural reactions
  ("right", "careful here", "ah, good question"). Vary how you open every single turn.
  Never reuse a sentence, phrase or question you have already used in this session.
- Teach and keep teaching. You do NOT have to ask a question at the end of every step —
  usually you just move on and let the student interrupt you. Ask something only when it
  earns its place: a tricky idea, a likely misconception, or the student has gone quiet.
- Explain like a teacher, not like a caption. A turn is a *pass of teaching*: say what this
  part is about, develop each idea with its reason, ground it with one concrete example or
  number, warn about the mistake, then flow on to the next part. Five to nine
  sentences is normal; a single sentence followed by "any questions?" is not teaching.
- Never end every turn with a question, and never with "do you have any questions?". The
  student knows they can interrupt; you just keep teaching until they do.
- Never use "is that clear?" style check-ins, and never twice in a session. If you do ask,
  ask about the content ("what happens if only two elements are left?"), not about comfort.
- When the student speaks, react to what they actually said:
  · correct → name what was right, in a few words, then continue;
  · partly right or wrong → name the specific gap; do not re-explain everything;
  · "I don't understand" → same idea by another route: plainer words, an example, or a
    smaller step. Never repeat the sentence you just said, and do not lecture them for it;
  · a question → answer it, then pick the thread back up where you were.
- If the student is quiet, keep teaching — move on to the next part of the lesson.
  Silence means "continue", never "shall we pause?" or "any questions?". Only stop
  explaining when the whole plan is covered or the student interrupts with a question.
- Use the student's name once in a while, not every turn.
- Speak the lesson's ideas in the target language. Technical terms stay as they are normally
  said (binary search, array) — that is correct, not a lapse.
- Never read the plan aloud, never say "step 2 of 4", never announce what you are about to do
  or list your steps. Just teach.
- Teach the lesson straight through to its end; do not loop back and re-explain a part you
  have already taught, and never restart from the beginning. If you resume after an
  interruption, continue from the part where you stopped.
- When you reach the very end of the lesson: if the student never asked anything the whole
  way, ask once, in their language, whether they have any questions. If they did ask during
  the lesson, just wrap up warmly — they already know the floor is open.
- If the student is confused, simplify: plainer words, a smaller step, a concrete example —
  a different route each time, never the same sentence twice.
- If you cannot understand what the student said: ask them to repeat, in their language, and
  vary the wording. If after three tries you still cannot understand, ask them to type it.
  If you still cannot get it, say plainly "I didn't get your point" and move on gracefully.
- Conduct: if the student is rude or abusive, warn them once, calmly, to speak politely and
  you'll continue. If they do it a second time, state that the lesson is ended, and end it —
  do not keep teaching after that."""


def interaction_suffix() -> str:
    return INTERACTION_SUFFIX


# --------------------------------------------------------------------------- #
# the same behaviour, speakable, in all ten languages
# --------------------------------------------------------------------------- #

INTERACTION_PHRASES: dict[str, dict[str, str]] = {
    "en": {
        "put_simply": "Put simply: {goal}",
        "holding": "Take your time — I'll wait.",
        "which_part": "Which part is fuzzy — the {title}, or what comes after it?",
        "step_plain": "{title} — {goal}.",
        "topic_line": "Today we are working on {topic}.",
        "step_one": "Step one: {title} — {goal}.",
        "next_step": "Next: {title} — {goal}.",
        "on_step": "Right — we're on {title}: {goal}.",
        "on_current": "On {title}: {goal}.",
        "think_of": "Think of {title} as: {goal}",
        "smaller": "Let's take it in a smaller step: {goal}",
        "nothing_more": "nothing more than that.",
        "check": "Does that make sense so far?",
        "praise": "Exactly — well done.",
        "rephrase": "No problem, let me put it another way.",
        "simpler": "Let me make it simpler.",
        "encourage": "Take your time.",
        "next": "Good, let's move on.",
        "example": "Would you like a concrete example?",
        "invite": "What would you like me to clarify?",
        "close": "That's the whole plan. What else would you like to explore?",
        "switch": "We'll continue in this language now.",
        "answer_ack": "Good question.",
        "repeat_please": "Sorry, I didn't catch that — could you say it again?",
        "type_it": "I'm still not catching it by voice — could you type it for me?",
        "not_got": "I'm sorry, I didn't get your point.",
        "polite_warn": "Please let's keep it respectful — speak politely and we'll continue.",
        "polite_end": "That's the second time. This lesson is ended — goodbye.",
        "lesson_closed": "The lesson is closed. Start a new session when you're ready.",
    },
    "ar": {
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
        "repeat_please": "عذرًا، لم ألتقط ما قلت — هل يمكنك إعادته؟",
        "type_it": "ما زلت لا أفهمه صوتًا — هل يمكنك كتابته لي؟",
        "not_got": "عذرًا، لم أفهم قصدك.",
        "polite_warn": "من فضلك لنتحدث باحترام — تكلم بأدب وسنكمل.",
        "polite_end": "هذه المرة الثانية. انتهى الدرس الآن — إلى اللقاء.",
        "lesson_closed": "الدرس مُغلق. ابدأ جلسة جديدة عندما تكون جاهزًا.",
    },
    # Round 24 — polite Egyptian Arabic (respectful, not slang). fusHa stays the default
    # register; `ar-EG` sessions answer with these lines and fall back to fusHa for any
    # key not curated here (see the `startswith("ar")` fallback in phrase_variants).
    "ar-eg": {
        "put_simply": "ببساطة يا فندم: {goal}",
        "holding": "خد وقتك، أنا مستنيك.",
        "which_part": "أنهي جزء مش واضح لحضرتك — {title} ولا اللي بعده؟",
        "step_plain": "{title} — {goal}.",
        "topic_line": "النهارده هنتكلم عن {topic}.",
        "step_one": "أول خطوة: {title} — {goal}.",
        "next_step": "الخطوة الجاية: {title} — {goal}.",
        "on_step": "إحنا دلوقتي في {title}: {goal}.",
        "on_current": "بالنسبة لـ{title}: {goal}.",
        "think_of": "تخيّل {title} بالشكل ده: {goal}",
        "smaller": "خليني أوضحها بخطوة أصغر: {goal}",
        "nothing_more": "مش أكتر من كده.",
        "check": "واضح لحد هنا يا فندم؟",
        "praise": "بالظبط كده، أحسنت.",
        "rephrase": "مفيش مشكلة، خليني أشرحها بطريقة تانية.",
        "simpler": "خليني أبسّطها شوية.",
        "encourage": "خد وقتك.",
        "next": "تمام، نكمّل.",
        "example": "تحب أضربلك مثال واضح؟",
        "invite": "عندك أي سؤال تحب أسألهولي؟",
        "close": "دي الخطة كلها يا فندم. تحب نعمل إيه بعد كده؟",
        "switch": "هنكمّل بالمصري من هنا.",
        "answer_ack": "سؤال حلو أوي.",
        "repeat_please": "معذرة يا فندم، مأخدتش بالي — تقدر تعيدها؟",
        "type_it": "لسه مش واضحلي بالصوت — تقدر تكتبهالي؟",
        "not_got": "معذرة يا فندم، مافهمتش قصدك.",
        "polite_warn": "لو سمحت خلي كلامنا بأدب — ونتفضل نكمّل.",
        "polite_end": "دي تاني مرة. الدرس انتهى كده — مع السلامة.",
        "lesson_closed": "الدرس اتقفل. ابدأ جلسة جديدة لما تحب.",
    },
    "fr": {
        "put_simply": "Autrement dit : {goal}",
        "holding": "Prends ton temps, je t'attends.",
        "which_part": "Quelle partie est floue : {title}, ou ce qui vient après ?",
        "step_plain": "{title} — {goal}.",
        "topic_line": "Aujourd'hui, nous travaillons sur {topic}.",
        "step_one": "Première étape : {title} — {goal}.",
        "next_step": "Étape suivante : {title} — {goal}.",
        "on_step": "Nous en sommes à {title} : {goal}.",
        "on_current": "À propos de {title} : {goal}.",
        "think_of": "Pense à {title} comme : {goal}",
        "smaller": "Prenons une étape plus simple : {goal}",
        "nothing_more": "rien de plus que ça.",
        "check": "Est-ce que c'est clair jusqu'ici ?",
        "praise": "Exactement, bravo.",
        "rephrase": "Pas de problème, disons-le autrement.",
        "simpler": "Je simplifie.",
        "encourage": "Prends ton temps.",
        "next": "Bien, continuons.",
        "example": "Tu veux un exemple concret ?",
        "invite": "Qu'est-ce que je peux clarifier ?",
        "close": "Voilà tout le plan. On explore quoi ensuite ?",
        "switch": "On continue dans cette langue maintenant.",
        "answer_ack": "Bonne question.",
    },
    "sw": {
        "put_simply": "Kwa urahisi: {goal}",
        "holding": "Chukua muda wako, nakusubiri.",
        "which_part": "Sehemu ipi haiko wazi: {title}, au kinachofuata?",
        "step_plain": "{title} — {goal}.",
        "topic_line": "Leo tunajifunza {topic}.",
        "step_one": "Hatua ya kwanza: {title} — {goal}.",
        "next_step": "Hatua inayofuata: {title} — {goal}.",
        "on_step": "Tuko kwenye {title}: {goal}.",
        "on_current": "Kuhusu {title}: {goal}.",
        "think_of": "Fikiria {title} kama: {goal}",
        "smaller": "Tuchukue hatua ndogo zaidi: {goal}",
        "nothing_more": "hakuna zaidi ya hiyo.",
        "check": "Je, hadi inaeleweka hadi hapa?",
        "praise": "Sawa kabisa, umefanya vizuri.",
        "rephrase": "Hakuna shida, niseme kwa njia nyingine.",
        "simpler": "Nirahisishe.",
        "encourage": "Chukua muda wako.",
        "next": "Vizuri, tuendelee.",
        "example": "Unataka mfano wa wazi?",
        "invite": "Unataka nifafanue nini?",
        "close": "Huo ndio mpango wote. Tufanye nini kingine?",
        "switch": "Tutaendelea kwa lugha hii sasa.",
        "answer_ack": "Swali zuri.",
    },
    "am": {
        "put_simply": "በቀላሉ፦ {goal}",
        "holding": "ጊዜህን ውሰድ፣ እጠብቅሃለሁ።",
        "which_part": "የትኛው ክፍል ነው የማይገባህ — {title}፣ ወይስ ቀጣዩ?",
        "step_plain": "{title} — {goal}።",
        "topic_line": "ዛሬ በ{topic} ላይ እየሰራን ነው።",
        "step_one": "የመጀመሪያው እርምጃ፦ {title} — {goal}።",
        "next_step": "የሚቀጥለው እርምጃ፦ {title} — {goal}።",
        "on_step": "አሁን በ{title} ላይ ነን፦ {goal}።",
        "on_current": "ስለ {title}፦ {goal}።",
        "think_of": "{title}ን እንደ {goal} አስበው",
        "smaller": "በትንሽ እርምጃ እንውሰደው፦ {goal}",
        "nothing_more": "ከዚህ በላይ አይደለም።",
        "check": "እስካሁን ግልጽ ነው?",
        "praise": "በትክክል፣ ጥሩ ሰርተሃል።",
        "rephrase": "ችግር የለም፣ በሌላ መንገድ ልናገረው።",
        "simpler": "ቀላል ላድርገው።",
        "encourage": "ቀስ ብለህ ውሰድ።",
        "next": "ጥሩ፣ እንቀጥል።",
        "example": "ግልጽ ምሳሌ ትፈልጋለህ?",
        "invite": "ምን እንዳብራራልህ ትፈልጋለህ?",
        "close": "ይህ መርሃግብሩ ሙሉ ነው። ሌላ ምን እናድርግ?",
        "switch": "ከአሁን በዚህ ቋንቋ እንቀጥላለን።",
        "answer_ack": "ጥሩ ጥያቄ።",
    },
    "ha": {
        "put_simply": "A sauƙaƙe: {goal}",
        "holding": "Ɗauki lokacinka, ina jira.",
        "which_part": "Wane bangare ba shi da kyau: {title}, ko abin da ke biyo baya?",
        "step_plain": "{title} — {goal}.",
        "topic_line": "Yau muna aiki kan {topic}.",
        "step_one": "Mataki na farko: {title} — {goal}.",
        "next_step": "Mataki na gaba: {title} — {goal}.",
        "on_step": "Muna kan {title}: {goal}.",
        "on_current": "Game da {title}: {goal}.",
        "think_of": "Ka yi tunanin {title} kamar: {goal}",
        "smaller": "Mu ɗauki mataki mafi sauƙi: {goal}",
        "nothing_more": "ba abin da ya wuce haka.",
        "check": "Ko hakan ya bayyana har yanzu?",
        "praise": "Haka ne, ka yi kyau.",
        "rephrase": "Babu matsala, bari in faɗe shi wata hanya.",
        "simpler": "Bari in sauƙaƙe shi.",
        "encourage": "Dauki lokacinka.",
        "next": "To, mu ci gaba.",
        "example": "Kana son misali bayyananne?",
        "invite": "Me kake son in bayyana?",
        "close": "Wannan shi ne dukan shirin. Me kuma za mu yi?",
        "switch": "Za mu ci gaba da wannan harshe yanzu.",
        "answer_ack": "Tambaya mai kyau.",
    },
    "so": {
        "put_simply": "Si fudud: {goal}",
        "holding": "Waqtigaaga qaado, waan ku sugayaa.",
        "which_part": "Qaybtee aan caddayn: {title}, mise tan xigta?",
        "step_plain": "{title} — {goal}.",
        "topic_line": "Maanta waxaan ka shaqeynaynaa {topic}.",
        "step_one": "Tallaabada koowaad: {title} — {goal}.",
        "next_step": "Tallaabada xigta: {title} — {goal}.",
        "on_step": "Waxaan joognaa {title}: {goal}.",
        "on_current": "Ku saabsan {title}: {goal}.",
        "think_of": "U malee {title} sida: {goal}",
        "smaller": "Aan qaadanno tallaabo yar: {goal}",
        "nothing_more": "wax ka badan taas ma jiro.",
        "check": "Ma tan caddaynayaa ilaa hadda?",
        "praise": "Si sax ah, waad wanaagsan tahay.",
        "rephrase": "Dhib ma leh, aan si kale u dhigo.",
        "simpler": "Aan ka dhigo mid fudud.",
        "encourage": "Waqtigaaga qaado.",
        "next": "Wanaagsan, aan sii wadno.",
        "example": "Ma rabtaa tusaale cad?",
        "invite": "Maxaad rabtaa inaan caddeeyo?",
        "close": "Taasi waa qorshaha oo dhan. Maxaan kale sameynaa?",
        "switch": "Hadda waxaan ku sii wadi doonaa luqaddan.",
        "answer_ack": "Su'aal wanaagsan.",
    },
    "yo": {
        "put_simply": "Ní ọ̀nà tó rọrùn: {goal}",
        "holding": "Ẹ jẹ́ kí o rọ̀, mò ń dúró.",
        "which_part": "Apá wo ni kò yé ọ: {title}, tàbí èyí tó ń bọ̀?",
        "step_plain": "{title} — {goal}.",
        "topic_line": "Lónìí a ń ṣiṣẹ́ lórí {topic}.",
        "step_one": "Ìgbésẹ̀ kìíní: {title} — {goal}.",
        "next_step": "Ìgbésẹ̀ tó ń bọ̀: {title} — {goal}.",
        "on_step": "A wà lórí {title}: {goal}.",
        "on_current": "Nípa {title}: {goal}.",
        "think_of": "Ro {title} bíi: {goal}",
        "smaller": "Ẹ jẹ́ ká mú ìgbésẹ̀ tó rọrùn: {goal}",
        "nothing_more": "kò ju bẹ́ẹ̀ lọ.",
        "check": "Ṣé ó yé ọ títí di báyìí?",
        "praise": "Gan-an, o ṣe dáadáa.",
        "rephrase": "Kò sí wàhálà, jẹ́ kí n sọ ọ́ ní ọ̀nà mìíràn.",
        "simpler": "Jẹ́ kí n rọ̀ ọ́ jẹ́.",
        "encourage": "Ẹ gbà á lọ́wọ́.",
        "next": "Ó dára, ẹ jẹ́ ká tẹ̀síwájú.",
        "example": "Ṣé o fẹ́ àpẹẹrẹ tí ó ṣe kedere?",
        "invite": "Kí ni o fẹ́ kí n ṣàlàyé?",
        "close": "Ìyẹn ni gbogbo ètò náà. Kí ni ká ṣe nísinsìnyí?",
        "switch": "A máa tẹ̀síwájú ní èdè yìí báyìí.",
        "answer_ack": "Ìbéèrè tí ó dára.",
    },
    "ig": {
        "put_simply": "N'ụzọ dị mfe: {goal}",
        "holding": "Were oge gị, m na-eche.",
        "which_part": "Akụkụ ole na-edoghị anya: {title}, ka nke na-esote?",
        "step_plain": "{title} — {goal}.",
        "topic_line": "Taa anyị na-arụ ọrụ na {topic}.",
        "step_one": "Nzọụkwụ mbụ: {title} — {goal}.",
        "next_step": "Nzọụkwụ na-esote: {title} — {goal}.",
        "on_step": "Anyị nọ na {title}: {goal}.",
        "on_current": "Banyere {title}: {goal}.",
        "think_of": "Chee {title} dịka: {goal}",
        "smaller": "Ka anyị were nzọụkwụ nta: {goal}",
        "nothing_more": "ọ dịghị ihe karịrị nke ahụ.",
        "check": "Ọ doro anya ruo ugbu a?",
        "praise": "Ọ bụ otu ahụ, ị mere nke ọma.",
        "rephrase": "Nsogbu adịghị, ka m kwuo ya n'ụzọ ọzọ.",
        "simpler": "Ka m mee ya ka ọ dị mfe.",
        "encourage": "Were oge gị.",
        "next": "Ọ dị mma, ka anyị gaa n'ihu.",
        "example": "Ị chọrọ ihe atụ doro anya?",
        "invite": "Gịnị ka ị chọrọ ka m kọwaa?",
        "close": "Nke ahụ bụ atụmatụ ahụ dum. Gịnị ọzọ ka anyị ga-eme?",
        "switch": "Anyị ga-eji asụsụ a gaa n'ihu ugbu a.",
        "answer_ack": "Ajụjụ dị mma.",
    },
    "zu": {
        "put_simply": "Ngamafuphi: {goal}",
        "holding": "Thatha isikhathi sakho, ngizolinda.",
        "which_part": "Iyiphi ingxenye engacaci: {title}, noma okulandelayo?",
        "step_plain": "{title} — {goal}.",
        "topic_line": "Namuhla sisebenza ku-{topic}.",
        "step_one": "Isinyathelo sokuqala: {title} — {goal}.",
        "next_step": "Isinyathelo esilandelayo: {title} — {goal}.",
        "on_step": "Sikwi-{title}: {goal}.",
        "on_current": "Mayelana no-{title}: {goal}.",
        "think_of": "Cabanga ngo-{title} njengo: {goal}",
        "smaller": "Ake sithathe isinyathelo esincane: {goal}",
        "nothing_more": "akukho okunye ngaphezu kwalokho.",
        "check": "Kuyacaca kuze kube manje?",
        "praise": "Kunjalo, wenze kahle.",
        "rephrase": "Ayikho inkinga, ake ngikusho ngendlela ehlukile.",
        "simpler": "Ake ngenze kube lula.",
        "encourage": "Thatha isikhathi sakho.",
        "next": "Kuhle, asiye phambili.",
        "example": "Ufuna isibonelo esicacile?",
        "invite": "Yini ofuna ngiyicacise?",
        "close": "Lokho ukuphela kohlelo. Senzeni okunye?",
        "switch": "Sizoqhubeka ngalolu limi manje.",
        "answer_ack": "Umbuzo omuhle.",
    },
}


# --------------------------------------------------------------------------- #
# extra variants of the lines a tutor repeats most
# --------------------------------------------------------------------------- #
#
# One fixed sentence per situation is what makes a tutor sound canned: "Does that make
# sense so far?" after every step, the same "well done" every time. These are second and
# third ways to say the same thing, picked in rotation (never immediately repeating), so a
# session sounds like a person rather than a prompt template.
PHRASE_VARIANTS: dict[str, dict[str, tuple[str, ...]]] = {
    "en": {
        "check": ("Shall I keep going?", "Want an example before we move on?",
                  "Does that land, or should I say it another way?"),
        "praise": ("That's it.", "Right, you've got it."),
        "rephrase": ("Let me come at it from another angle.", "Okay, different route."),
        "encourage": ("No rush at all.",),
        "close": ("And that's everything I wanted to cover.",),
        "going_on": ("Right — and that leads straight into this:",),
        "invite_stop": ("Jump in whenever you want.",),
        "repeat_please": ("Sorry, I didn't catch that — say it again?",
                          "Come again? The line got fuzzy on my end.",
                          "One more time, a little clearer?"),
    },
    "ar": {
        "repeat_please": ["عذرًا، لم ألتقط ما قلت — هل يمكنك إعادته؟",
                          "معاذرة، الصوت وصل مشوشًا — أعد عليّ من فضلك.",
                          "مرة أخرى وبهدوء أكثر لأفهمك جيدًا؟"],
        "check": ["أُكمل؟", "هل تحب مثالًا قبل أن نُكمل؟", "واضحة هكذا أم أعيدها بطريقة أخرى؟"],
        "praise": ["أحسنت.", "ممتاز، لقد فهمتها."],
        "rephrase": ["دعني أقترب منها من زاوية أخرى.", "حسنًا، بطريقة أخرى."],
        "encourage": ["لا داعي للعجلة، خذ وقتك."],
        "close": ["وهذا كل ما كان يجب أن نغطيه."],
        "going_on": ["حسنًا — وهذا يوصلنا إلى ما يلي:"],
        "invite_stop": ["يمكنك أن تقاطعني في أي وقت."],
    },
    "fr": {
        "check": ("Je continue ?", "Tu veux un exemple avant d'avancer ?",
                  "C'est clair, ou je le dis autrement ?"),
        "praise": ("C'est ça.", "Bravo, tu l'as."),
        "rephrase": ("Prenons-le par un autre bout.", "Je reformule autrement."),
        "encourage": ("Rien ne presse.",),
        "close": ("Et c'est tout ce que je voulais couvrir.",),
        "going_on": ("Bien — et ça nous amène directement ici :",),
        "invite_stop": ("Coupe-moi quand tu veux.",),
    },
    "sw": {
        "check": ("Niendelee?", "Unataka mfano kabla ya kuendelea?",
                  "Iko wazi, au niseme kwa njia nyingine?"),
        "praise": ("Ndiyo hivyo.", "Vizuri, umeipata."),
        "rephrase": ("Niiangalie kwa upande mwingine.", "Sawa, kwa njia nyingine."),
        "encourage": ("Hakuna haraka.",),
        "close": ("Na hayo ndiyo yote niliyotaka kufunika.",),
        "going_on": ("Sawa — na hii inatupeleka moja kwa moja hapa:",),
        "invite_stop": ("Nikate wakati wowote.",),
    },
    "am": {
        "check": ("እንቀጥል?", "ከመቀጠልህ በፊት ምሳሌ ትፈልጋለህ?",
                  "ግልጽ ነው ወይስ በሌላ መንገድ ልናገረው?"),
        "praise": ("ያው ነው።", "ጥሩ፣ ገብቶሃል።"),
        "rephrase": ("በሌላ አቅጣጫ ልመልከተው።", "እሺ፣ በሌላ መንገድ።"),
        "encourage": ("ምንም ጥድፊያ የለም።",),
        "close": ("የምፈልገው ይህ ብቻ ነበር።",),
        "going_on": ("እሺ — ይህ ደግሞ በቀጥታ ወደዚህ ይወስደናል፦",),
        "invite_stop": ("በፈለግህ ጊዜ አቋርጠኝ።",),
    },
    "ha": {
        "check": ("In ci gaba?", "Kana son misali kafin mu ci gaba?",
                  "Ya bayyana, ko in faɗe shi wata hanya?"),
        "praise": ("Shi ke nan.", "To, ka same shi."),
        "rephrase": ("Bari in duba shi ta wani gefe.", "To, wata hanya."),
        "encourage": ("Babu gaggawa.",),
        "close": ("Kuma wannan shi ne duk abin da nake so in rufe.",),
        "going_on": ("To — wannan kuma ya kai mu kai tsaye nan:",),
        "invite_stop": ("Ka tsayar da ni duk lokacin da kake so.",),
    },
    "so": {
        "check": ("Aan sii socdo?", "Miyaad rabtaa tusaale ka hor inta aanaan sii socon?",
                  "Way cad dahay, mise si kale ayaan u dhahaa?"),
        "praise": ("Taasi waa taas.", "Wanaagsan, waad heshay."),
        "rephrase": ("Aan dhinac kale ka eego.", "Hagaag, si kale."),
        "encourage": ("Degdeg ma jiro.",),
        "close": ("Tanina waa dhammaan wixii aan rabay inaan dabo.",),
        "going_on": ("Hagaag — tani waxay si toos ah ina geysaa halkan:",),
        "invite_stop": ("I jooji wakhti kasta oo aad rabto.",),
    },
    "yo": {
        "check": ("Kí n tẹ̀síwájú?", "Ṣé o fẹ́ àpẹẹrẹ kí a tó tẹ̀síwájú?",
                  "Ó yé ọ, tàbí kí n sọ ọ́ ní ọ̀nà mìíràn?"),
        "praise": ("Ìyẹn ni.", "Ó dára, o ti mọ̀ ọ́n."),
        "rephrase": ("Jẹ́ kí n wò ó ní ọ̀nà mìíràn.", "Ó dára, ọ̀nà mìíràn."),
        "encourage": ("Kò sí kánjú.",),
        "close": ("Àti èyí ni gbogbo ohun tí mo fẹ́ ṣàlàyé.",),
        "going_on": ("Ó dára — èyí sì mú wa dé ibí ní tààràtà:",),
        "invite_stop": ("Dá mi dúró nígbàkigbà tí o bá fẹ́.",),
    },
    "ig": {
        "check": ("Ka m ga n'ihu?", "Ị chọrọ atụ ma tupu anyị aga n'ihu?",
                  "Ọ doro anya, ka m kọọ ya n'ụzọ ọzọ?"),
        "praise": ("Ọ bụ ya.", "Ọ dị mma, ị ghọtara ya."),
        "rephrase": ("Ka m lee ya n'akụkụ ọzọ.", "Ọ dị mma, ụzọ ọzọ."),
        "encourage": ("Ọ dịghị ngwa ngwa.",),
        "close": ("Nke a bụkwa ihe niile m chọrọ ikpuchi.",),
        "going_on": ("Ọ dị mma — nke a na-eduga anyị kpọmkwem ebe a:",),
        "invite_stop": ("Kwụsị m oge ọ bụla ị chọrọ.",),
    },
    "zu": {
        "check": ("Ngiqhubeke?", "Ufuna isibonelo ngaphambi kokuba siqhubeke?",
                  "Kucacile, noma ngikusho ngenye indlela?"),
        "praise": ("Yikho.", "Kuhle, uyitholile."),
        "rephrase": ("Ake ngiyibheke ngakolunye uhlangothi.", "Kulungile, ngenye indlela."),
        "encourage": ("Akukho ukushesha.",),
        "close": ("Futhi yilokhu konke ebengifuna ukukuhlanganisa.",),
        "going_on": ("Kulungile — lokhu kusiholela ngqo lapha:",),
        "invite_stop": ("Ngivimbe noma nini lapho ufuna.",),
    },
}


def phrase_variants(language: str | None, key: str) -> tuple[str, ...]:
    """Every way the tutor may say one thing in a language, first variant first.

    A key may live in the main table (the first, canonical variant) and/or in
    `PHRASE_VARIANTS` (the alternatives). Keys that only exist as alternatives —
    `invite_stop`, `going_on` — still resolve, so a template never renders as nothing.
    """
    code = (language or "en").lower()
    # Egyptian (`ar-eg`) falls back to fusHa (`ar`) before English, so an uncurated
    # key still sounds Arabic rather than switching language.
    codes = [code] + (["ar"] if code.startswith("ar") and code != "ar" else [])
    out: list[str] = []
    for c in codes + (["en"] if not codes or True else []):
        if c not in INTERACTION_PHRASES and c != "en":
            continue
        base = INTERACTION_PHRASES.get(c, {}).get(key)
        extra = PHRASE_VARIANTS.get(c, {}).get(key, ())
        for line in ((base,) if base else ()) + tuple(extra):
            if line and line not in out:
                out.append(line)
        if out and c != "en":
            break
    return tuple(out) or (INTERACTION_PHRASES["en"].get(key),)


def phrase(language: str | None, key: str) -> str:
    """One interaction line in the given language (English when unknown)."""
    variants = phrase_variants(language, key)
    if variants:
        return variants[0]
    return INTERACTION_PHRASES["en"].get(key, "")



# --------------------------------------------------------------------------- #
# spoken rendering — how a step is actually said out loud
# --------------------------------------------------------------------------- #
#
# A plan entry reads like a note ("The idea of halving — sorted order is the
# precondition"), and reading that shape aloud is what makes a tutor sound like a
# machine. These are spoken leads in each language: sentence-shaped, no "Step 2:"
# labels, no em dashes. The dialogue rotates them so consecutive steps differ.
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


STEP_LEAD: dict[str, tuple[str, ...]] = {
    "en": ("{title}. {goal}.", "Okay, {title_lower}. {goal}.", "Right, {title_lower}: {goal}.",
           "{title}, and the point is this: {goal}."),
    "ar": ("{title}. {goal}.", "حسنًا، {title}. {goal}.", "الآن، {title}: {goal}.", "{title}، والفكرة هنا أنّ {goal}."),    "fr": ("{title}. {goal}.", "Bon, {title_lower}. {goal}.", "Alors, {title_lower} : {goal}.",
           "{title}, et le point important c'est que {goal}."),
    "sw": ("{title}. {goal}.", "Sawa, {title_lower}. {goal}.", "Vizuri, {title_lower}: {goal}.",
           "{title}, na jambo la muhimu ni kwamba {goal}."),
    "am": ("{title}። {goal}።", "እሺ፣ {title}። {goal}።", "ጥሩ፣ {title}: {goal}።",
           "{title}፣ እዚህ ዋናው ነጥብ {goal} ነው።"),
    "ha": ("{title}. {goal}.", "To, {title_lower}. {goal}.", "Daidai, {title_lower}: {goal}.",
           "{title}, kuma babban abu shi ne {goal}."),
    "so": ("{title}. {goal}.", "Hagaag, {title_lower}. {goal}.", "Waa hagaag, {title_lower}: {goal}.",
           "{title}, qodobka muhiimka ahina waa {goal}."),
    "yo": ("{title}. {goal}.", "Ó dára, {title_lower}. {goal}.", "Bẹ́ẹ̀ ni, {title_lower}: {goal}.",
           "{title}, kókó pàtàkì ni pé {goal}."),
    "ig": ("{title}. {goal}.", "Ọ dị mma, {title_lower}. {goal}.", "Ee, {title_lower}: {goal}.",
           "{title}, isi ihe dị mkpa bụ na {goal}."),
    "zu": ("{title}. {goal}.", "Kulungile, {title_lower}. {goal}.", "Yebo, {title_lower}: {goal}.",
           "{title}, futhi iphuzu elibalulekile ukuthi {goal}."),
}

#: Short spoken transitions before a step. Used sparingly — every turn opening the same
#: way is what makes speech sound generated.
MOVE_ON: dict[str, tuple[str, ...]] = {
    "en": ("First off.", "Okay.", "Now.", "Alright.", "Here's the thing."),
    "ar": ("أولًا.", "حسنًا.", "الآن.", "جيد.", "انظر."),    "fr": ("D'abord.", "Bon.", "Maintenant.", "Alors.", "Voilà."),
    "sw": ("Kwanza.", "Sawa.", "Sasa.", "Vizuri.", "Haya."),
    "am": ("በመጀመሪያ።", "እሺ።", "አሁን።", "ጥሩ።", "እንዲህ።"),
    "ha": ("Da farko.", "To.", "Yanzu.", "Kai.", "Ga shi."),
    "so": ("Marka hore.", "Hagaag.", "Hadda.", "Waa hagaag.", "Bal e."),
    "yo": ("Lákọ̀ọ́kọ́.", "Ó dára.", "Nísinsìnyí.", "Bẹ́ẹ̀ ni.", "Wò ó."),
    "ig": ("Nke mbụ.", "Ọ dị mma.", "Ugbu a.", "Ee.", "Lee."),
    "zu": ("Okokuqala.", "Kulungile.", "Manje.", "Yebo.", "Bheka."),
}

#: Backchannels for a student turn that carries no content — a person says "mhm",
#: a script says nothing or repeats the last line.
REACT: dict[str, tuple[str, ...]] = {
    "en": ("Mhm.", "Right.", "Okay.", "Got it."),
    "ar": ("نعم.", "حسنًا.", "فهمت.", "جيد."),
    "fr": ("Mmm.", "D'accord.", "Oui.", "Je vois."),
    "sw": ("Mhm.", "Sawa.", "Ndiyo.", "Nimekuelewa."),
    "am": ("እሺ.", "ገባኝ.", "አዎ.", "እንዲህ ነው."),
    "ha": ("Mhm.", "To.", "Iya.", "Na ji."),
    "so": ("Mhm.", "Hagaag.", "Haa.", "Waan fahmay."),
    "yo": ("Mhm.", "Ó dára.", "Bẹ́ẹ̀ ni.", "Mo gbọ́."),
    "ig": ("Mhm.", "Ọ dị mma.", "Ee.", "Anụrụ m."),
    "zu": ("Mhm.", "Kulungile.", "Yebo.", "Ngiyezwa."),
}

#: Punctuation and symbols the speech synthesiser would otherwise read as themselves
#: (or swallow). Applied only on the way to the speaker, never to the transcript.
_SPOKEN_WORDS: tuple[tuple[str, str], ...] = (
    (" — ", ", "), (" – ", ", "), ("—", ", "), ("–", ", "),
    ("//", " divided by "), ("->", " becomes "), ("=>", " becomes "),
    (">=", " greater than or equal to "), ("<=", " less than or equal to "),
    (">", " greater than "), ("<", " less than "),
    ("+", " plus "), ("*", " times "), ("=", " equals "),
    ("%", " percent "), ("&", " and "), ("#", " number "),
    ("(", ""), (")", ""), ("[", ""), ("]", ""),
    ('"', ""), ("`", ""), ("_", " "),
)


def speakable(text: str) -> str:
    """The same sentence, rewritten so a speech synthesiser reads it like speech.

    "mid = (low + high) // 2" becomes "mid equals low plus high divided by 2" instead of
    a stream of punctuation names. The written transcript is untouched — this is only the
    text handed to the voice.
    """
    out = text or ""
    for symbol, words in _SPOKEN_WORDS:
        out = out.replace(symbol, words)
    for mark in ("  ", " ,", " .", " ."):
        while mark in out:
            out = out.replace(mark, mark.strip() or " ")
    return " ".join(out.split()).strip()


def step_lead(language: str | None, title: str, goal: str, index: int = 0) -> str:
    """One plan step as a spoken sentence, in the given language."""
    options = STEP_LEAD.get((language or "en").lower(), STEP_LEAD["en"])
    template = options[index % len(options)]
    return template.format(
        title=title, title_lower=_lower_first(title), goal=_upper_first(goal)
    ).strip()


def move_on(language: str | None, index: int = 0) -> str:
    code = (language or "en").lower()
    options = MOVE_ON.get(code) or (MOVE_ON["ar"] if code.startswith("ar") else None) or MOVE_ON["en"]
    return options[index % len(options)]


def react(language: str | None, index: int = 0) -> str:
    code = (language or "en").lower()
    options = REACT.get(code) or (REACT["ar"] if code.startswith("ar") else None) or REACT["en"]
    return options[index % len(options)]


def _upper_first(text: str) -> str:
    """Capitalise a plan fragment so it can stand as its own spoken sentence."""
    if not text:
        return text
    first = text[0]
    if first.islower() and first.isascii():
        return first.upper() + text[1:]
    return text


def _lower_first(text: str) -> str:
    """Lowercase the first letter only when it is safe (Latin script, normal word)."""
    if not text:
        return text
    first = text[0]
    if first.isupper() and first.isascii() and not text[:2].isupper():
        return first.lower() + text[1:]
    return text

# --------------------------------------------------------------------------- #
# language switching
# --------------------------------------------------------------------------- #

LANGUAGE_SWITCH_MARKER = "The student switched the lesson language"




def build_language_switch_prompt(language: str, *, section: str = "", topic: str = "") -> str:
    """Ask the tutor to acknowledge a language switch *in the new language*.

    Without this a mid-lesson switch is silent: the session reconnects to a new
    provider configured for the new language, but nothing is generated until the
    student speaks, so the student hears no confirmation.
    """
    where = ""
    if topic:
        where = f" You were teaching '{topic}'"
        if section:
            where += f", at section '{section}'"
        where += "."
    return (
        f"{LANGUAGE_SWITCH_MARKER} to {language_name(language)} ({language}). "
        "In one short sentence, in that language, confirm that you will continue in it, then "
        "continue teaching the current step from where you stopped. Do not restart the lesson "
        "and do not translate what you already said." + where
    )


def is_language_switch_prompt(text: str) -> bool:
    return LANGUAGE_SWITCH_MARKER in (text or "")
