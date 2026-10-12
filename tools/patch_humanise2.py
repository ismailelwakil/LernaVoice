"""Patch 2: make variant-only keys first-class, add a neutral step template, close once."""

import re

# ----------------------------------------------------------------- interaction.py
P = "app/prompts/interaction.py"
s = open(P).read()

# remove the old phrase() and define phrase/phrase_variants together after the table
old_phrase = '''def phrase(language: str | None, key: str) -> str:
    """One interaction line in the given language (English when unknown)."""
    table = INTERACTION_PHRASES.get((language or "en").lower(), INTERACTION_PHRASES["en"])
    return table.get(key) or INTERACTION_PHRASES["en"].get(key, "")


'''
assert old_phrase in s
s = s.replace(old_phrase, "", 1)

old_pv = '''def phrase_variants(language: str | None, key: str) -> tuple[str, ...]:
    """Every way the tutor may say one thing in a language, first variant first."""
    code = (language or "en").lower()
    extra = PHRASE_VARIANTS.get(code, PHRASE_VARIANTS["en"]).get(key, ())
    return (phrase(code, key),) + tuple(extra)
'''
new_pv = '''def phrase_variants(language: str | None, key: str) -> tuple[str, ...]:
    """Every way the tutor may say one thing in a language, first variant first.

    A key may live in the main table (the first, canonical variant) and/or in
    `PHRASE_VARIANTS` (the alternatives). Keys that only exist as alternatives —
    `invite_stop`, `going_on` — still resolve, so a template never renders as nothing.
    """
    code = (language or "en").lower()
    base = INTERACTION_PHRASES.get(code, INTERACTION_PHRASES["en"]).get(key)
    extra = PHRASE_VARIANTS.get(code, PHRASE_VARIANTS["en"]).get(key, ())
    out: list[str] = []
    for line in ((base,) if base else ()) + tuple(extra):
        if line and line not in out:
            out.append(line)
    return tuple(out)


def phrase(language: str | None, key: str) -> str:
    """One interaction line in the given language (English when unknown)."""
    variants = phrase_variants(language, key)
    if variants:
        return variants[0]
    return INTERACTION_PHRASES["en"].get(key, "")
'''
assert old_pv in s
s = s.replace(old_pv, new_pv, 1)

# a step with no ordinal framing, for a step that flows straight out of the previous one
STEP_PLAIN = {
    "en": "{title} — {goal}.",
    "ar": "{title} — {goal}.",
    "fr": "{title} — {goal}.",
    "sw": "{title} — {goal}.",
    "am": "{title} — {goal}።",
    "ha": "{title} — {goal}.",
    "so": "{title} — {goal}.",
    "yo": "{title} — {goal}.",
    "ig": "{title} — {goal}.",
    "zu": "{title} — {goal}.",
}
for lang, line in STEP_PLAIN.items():
    marker = f'    "{lang}": {{\n'
    assert marker in s, lang
    s = s.replace(marker, marker + f'        "step_plain": "{line}",\n', 1)

open(P, "w").write(s)

# ----------------------------------------------------------------- dialogue.py
P = "app/providers/mock/dialogue.py"
s = open(P).read()

s = s.replace(
    """    #: Last variant index used per key, so a line never repeats back-to-back.
    _used: dict[str, int] = field(default_factory=dict)""",
    """    #: Last variant index used per key, so a line never repeats back-to-back.
    _used: dict[str, int] = field(default_factory=dict)
    #: True once the whole plan has been taught: further turns must not re-close it.
    done: bool = False""",
)

s = s.replace(
    """        if intent is Intent.AFFIRM:
            self.step += 1
            if self.step >= len(self.sections):
                return self._name(f"{self._v('praise')} {self._v('close')}")""",
    """        if self.done:
            # The plan is finished; do not keep saying goodbye. Hand the floor back.
            return self._name(f"{self._v('praise')} {self._p('invite')}")

        if intent is Intent.AFFIRM:
            self.step += 1
            if self.step >= len(self.sections):
                self.done = True
                return self._name(f"{self._v('praise')} {self._v('close')}")""",
)

s = s.replace(
    """                line += (
                    f" {self._p('going_on')} "
                    f"{self._t('step_one', title=following['title'], goal=following.get('goal', ''))}"
                )""",
    """                line += (
                    f" {self._p('going_on')} "
                    f"{self._t('step_plain', title=following['title'], goal=following.get('goal', ''))}"
                )""",
)

open(P, "w").write(s)

import subprocess
print(subprocess.run(["python3", "-c", """
from app.providers.mock.dialogue import TutorDialogue
S=[{'title':'The idea of halving','goal':'compare with the middle'},{'title':'Choosing the midpoint','goal':'mid = (low + high) // 2'},{'title':'Halving the space','goal':'discard the impossible half'},{'title':'Stopping','goal':'know when it is absent'}]
d=TutorDialogue.from_metadata({'topic_title':'Binary Search','sections':S},'en')
print('open :', d.opening())
for line in ['yes','yes','no, I dont understand','yes','yes','yes','yes']:
    print('you  :', line); print('tutor:', d.respond(line))
print()
a=TutorDialogue.from_metadata({'topic_title':'Binary Search','sections':S},'ar')
print('ar   :', a.opening()); print('ar   :', a.respond('نعم')); print('ar   :', a.respond('نعم'))
"""], capture_output=True, text=True).stdout)
