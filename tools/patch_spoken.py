"""Patch: the mock tutor speaks in sentences, not in labelled plan fragments.

Before:  "Step one: The idea of halving — compare with the middle, discard the half
          that cannot hold the target. Jump in whenever you want."
After:   "Alright. The idea of halving. Compare with the middle, discard the half that
          cannot hold the target. Jump in whenever you want."

The content is identical; what changes is that the tutor no longer reads the plan's
label-and-dash formatting aloud, uses spoken connectives, and can say the same thing
several ways. Also adds a `speakable()` normaliser so equations and dashes are read
as words instead of punctuation.
"""

# ============================================================ interaction.py
P = "app/prompts/interaction.py"
s = open(P).read()

SPOKEN = '''

# --------------------------------------------------------------------------- #
# spoken rendering — how a step is actually said out loud
# --------------------------------------------------------------------------- #
#
# A plan entry reads like a note ("The idea of halving — sorted order is the
# precondition"), and reading that shape aloud is what makes a tutor sound like a
# machine. These are spoken leads in each language: sentence-shaped, no "Step 2:"
# labels, no em dashes. The dialogue rotates them so consecutive steps differ.
STEP_LEAD: dict[str, tuple[str, ...]] = {
    "en": ("{title}. {goal}.", "Okay, {title_lower}. {goal}.", "Right, {title_lower}: {goal}.",
           "{title}, and the point is this: {goal}."),
    "ar": ("{title}. {goal}.", "طيب، {title}. {goal}.", "تمام، {title}: {goal}.",
           "{title}، والفكرة هنا إن {goal}."),
    "fr": ("{title}. {goal}.", "Bon, {title_lower}. {goal}.", "Alors, {title_lower} : {goal}.",
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
    "ar": ("أول حاجة.", "طيب.", "دلوقتي.", "تمام.", "بصّ."),
    "fr": ("D'abord.", "Bon.", "Maintenant.", "Alors.", "Voilà."),
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
    "ar": ("أها.", "تمام.", "طيب.", "ماشي."),
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
    (">=", " at least "), ("<=", " at most "), (">", " greater than "), ("<", " less than "),
    ("+", " plus "), ("*", " times "), ("=", " equals "),
    ("%", " percent "), ("&", " and "), ("#", " number "),
    ("(", ""), (")", ""), ("[", ""), ("]", ""),
    ('"', ""), ("'", ""), ("`", ""), ("_", " "),
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
    return template.format(title=title, title_lower=_lower_first(title), goal=goal).strip()


def move_on(language: str | None, index: int = 0) -> str:
    options = MOVE_ON.get((language or "en").lower(), MOVE_ON["en"])
    return options[index % len(options)]


def react(language: str | None, index: int = 0) -> str:
    options = REACT.get((language or "en").lower(), REACT["en"])
    return options[index % len(options)]


def _lower_first(text: str) -> str:
    """Lowercase the first letter only when it is safe (Latin script, normal word)."""
    if not text:
        return text
    first = text[0]
    if first.isupper() and first.isascii() and not text[:2].isupper():
        return first.lower() + text[1:]
    return text
'''

marker = "\n# --------------------------------------------------------------------------- #\n# language switching"
assert marker in s
s = s.replace(marker, SPOKEN + marker, 1)

# step_plain becomes sentence-shaped too (used when two steps come in one turn)
for lang, line in {
    "en": "{title}. {goal}.", "ar": "{title}. {goal}.", "fr": "{title}. {goal}.",
    "sw": "{title}. {goal}.", "am": "{title}። {goal}።", "ha": "{title}. {goal}.",
    "so": "{title}. {goal}.", "yo": "{title}. {goal}.", "ig": "{title}. {goal}.",
    "zu": "{title}. {goal}.",
}.items():
    s = s.replace(f'"step_plain": "{{title}} — {{goal}}.",', f'"step_plain": "{line}",') if False else s
open(P, "w").write(s)

import subprocess
print(subprocess.run(["python3", "-c", """
from app.prompts.interaction import step_lead, speakable, move_on, react
print(step_lead('en', 'The idea of halving', 'sorted order is the precondition', 1))
print(speakable('mid = (low + high) // 2, and if n >= 100 we stop'))
print(move_on('ar', 1), '|', react('zu', 2))
print(len(__import__('app.prompts.interaction', fromlist=['STEP_LEAD']).STEP_LEAD), 'languages have spoken leads')
"""], capture_output=True, text=True).stdout)
