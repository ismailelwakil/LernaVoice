"""Patch: humanise the interaction contract and add phrase variants."""

import re

P = "app/prompts/interaction.py"
s = open(P).read()

# ---------------------------------------------------------------- 1. the contract
old_suffix_start = 'INTERACTION_SUFFIX = """INTERACTION — you are a tutor in a conversation, not a lecturer'
start = s.index(old_suffix_start)
end = s.index('"""', s.index('silence is allowed."""')) + 3

NEW_SUFFIX = '''INTERACTION_SUFFIX = """INTERACTION — you are a person tutoring, not a script being read
- Talk like a real teacher: contractions, short spoken sentences, natural reactions
  ("right", "careful here", "ah, good question"). Vary how you open every single turn.
  Never reuse a sentence, phrase or question you have already used in this session.
- Teach and keep teaching. You do NOT have to ask a question at the end of every step —
  usually you just move on and let the student interrupt you. Ask something only when it
  earns its place: a tricky idea, a likely misconception, or the student has gone quiet.
- Never use "is that clear?" style check-ins, and never twice in a session. If you do ask,
  ask about the content ("what happens if only two elements are left?"), not about comfort.
- When the student speaks, react to what they actually said:
  · correct → name what was right, in a few words, then continue;
  · partly right or wrong → name the specific gap; do not re-explain everything;
  · "I don't understand" → same idea by another route: plainer words, an example, or a
    smaller step. Never repeat the sentence you just said, and do not lecture them for it;
  · a question → answer it, then pick the thread back up where you were.
- If the student is quiet, offer a choice ("want an example, or shall we try one together?").
- Use the student's name once in a while, not every turn.
- Speak the lesson's ideas in the target language. Technical terms stay as they are normally
  said (binary search, array) — that is correct, not a lapse.
- Never read the plan aloud, never say "step 2 of 4", never announce what you are about to do
  or list your steps. Just teach."""'''

s = s[:start] + NEW_SUFFIX + s[end:]

# ---------------------------------------------------------------- 2. variants
VARIANTS = '''
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
    },
    "ar": {
        "check": ("أكمل؟", "تحب مثال قبل ما نكمل؟", "واضحة كده ولا أقولها بطريقة تانية؟"),
        "praise": ("أيوة كده.", "تمام، إنت فاهمها."),
        "rephrase": ("خليني أجيها من ناحية تانية.", "طيب، بطريقة تانية."),
        "encourage": ("مفيش استعجال.",),
        "close": ("وده كل اللي كان لازم نغطيه.",),
        "going_on": ("طيب — وده بيوصلنا للي بعده:",),
        "invite_stop": ("قاطعني في أي وقت.",),
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
    """Every way the tutor may say one thing in a language, first variant first."""
    code = (language or "en").lower()
    extra = PHRASE_VARIANTS.get(code, PHRASE_VARIANTS["en"]).get(key, ())
    return (phrase(code, key),) + tuple(extra)


'''

marker = "\n# --------------------------------------------------------------------------- #\n# language switching"
assert marker in s
s = s.replace(marker, VARIANTS + marker.lstrip("\n"), 1)
open(P, "w").write(s)

import subprocess
print(subprocess.run(["python3", "-c", "import app.prompts.interaction as m; print(len(m.PHRASE_VARIANTS), 'languages'); print(m.phrase_variants('ar','check')); print(m.PHRASE_VARIANTS['zu']['going_on'])"], capture_output=True, text=True).stdout)
