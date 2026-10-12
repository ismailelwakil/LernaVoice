"""Patch: the dialogue speaks in sentences and reacts like a person."""

P = "app/providers/mock/dialogue.py"
s = open(P).read()

s = s.replace(
    "from app.prompts.interaction import phrase, phrase_variants",
    "from app.prompts.interaction import (\n"
    "    phrase,\n"
    "    phrase_variants,\n"
    "    move_on,\n"
    "    react,\n"
    "    speakable,\n"
    "    step_lead,\n"
    ")",
)

# ------------------------------------------------------------------ helpers
s = s.replace(
    '''    def _asking(self) -> bool:''',
    '''    def _lead(self, section: dict[str, str], offset: int = 0) -> str:
        """One plan step as a spoken sentence, rotating the way it is introduced."""
        return step_lead(
            self.language,
            section.get("title", ""),
            section.get("goal", ""),
            index=self._variety + self.step + offset,
        )

    def _asking(self) -> bool:''',
)

# ------------------------------------------------------------------ opening
old_open = s[s.index("    def opening(self)") : s.index("    def _topic_line(self)")]
new_open = '''    def opening(self) -> str:
        """Greet (in the lesson language), name the topic, teach step one."""
        greeting = LOCALISED_GREETINGS.get(self.language, LOCALISED_GREETINGS["en"])
        who = f" {self.student_name}." if self.student_name else ""
        if not self.planned:
            return f"{greeting}{who} {self._p('invite_stop')}"
        first = self.sections[0]
        # A person sets the scene before the first idea, then hands the turn over.
        return (
            f"{greeting}{who} {self._topic_line()} "
            f"{move_on(self.language, 0)} {self._lead(first)} "
            f"{self._p('invite_stop')}"
        )

'''
s = s.replace(old_open, new_open)

# ------------------------------------------------------------------ language switch
old_sw = s[s.index("    def language_switch(self)") : s.index("    def respond(")]
new_sw = '''    def language_switch(self) -> str:
        """Confirm the switch in the new language and carry on from here."""
        if not self.planned:
            return self._name(f"{self._p('switch')} {self._p('invite_stop')}")
        step = self.sections[min(self.step, len(self.sections) - 1)]
        tail = self._p("check") if self._asking() else self._p("invite_stop")
        return self._name(f"{self._p('switch')} {self._lead(step, offset=1)} {tail}")

'''
s = s.replace(old_sw, new_sw)

# ------------------------------------------------------------------ respond
old_respond = s[s.index("    def respond(self") : s.index("    def _simpler(")]
new_respond = '''    def respond(self, student_text: str) -> str:
        """The tutor's next turn, driven by what the student actually said."""
        intent = classify(student_text)
        if not self.planned:
            return self._name(self._generic(intent))

        current = self.sections[min(self.step, len(self.sections) - 1)]

        if intent is Intent.CONFUSED:
            # Another route each time, and never the same words as the first attempt:
            # reworded content (speakable()), a different lead, a smaller step, or a
            # direct question about which part is fuzzy.
            self._explain_style += 1
            route = self._explain_style % 3
            plainer = speakable(self._simpler(current))
            if route == 1:
                return self._name(
                    f"{self._v('rephrase')} {self._p('simpler')} "
                    f"{self._t('think_of', title=self._title_lower(current), goal=plainer)} "
                    f"{self._v('encourage')}"
                )
            if route == 2:
                return self._name(
                    f"{self._v('rephrase')} "
                    f"{self._t('smaller', goal=plainer)} {self._v('encourage')}"
                )
            return self._name(
                f"{self._v('rephrase')} {self._p('example')} "
                f"{self._t('which_part', title=self._title_lower(current))}"
            )

        if intent is Intent.QUESTION:
            return self._name(
                f"{self._p('answer_ack')} "
                f"{self._t('on_current', title=self._title_lower(current), goal=self._goal(current))} "
                f"{self._p('invite')}"
            )

        if self.done:
            # The plan is finished; do not keep saying goodbye. Hand the floor back.
            return self._name(f"{self._v('praise')} {self._p('invite')}")

        if intent is Intent.AFFIRM:
            self.step += 1
            if self.step >= len(self.sections):
                self.done = True
                return self._name(f"{self._v('praise')} {self._v('close')}")
            step = self.sections[self.step]
            if self._asking():
                return self._name(
                    f"{self._v('praise')} {self._lead(step)} {self._v('check')}"
                )
            # No question this turn: keep teaching and roll into the step after it, so
            # the lesson sounds like an explanation rather than an interrogation.
            line = f"{self._v('praise')} {self._lead(step)}"
            if self.step + 1 < len(self.sections):
                self.step += 1
                line += f" {self._p('going_on')} {self._lead(self.sections[self.step], offset=2)}"
            return self._name(line)

        # Plain participation ("mhm", "okay") — a person acknowledges and carries on.
        return self._name(f"{react(self.language, self._variety)} {self._lead(current)}")

    def _title_lower(self, section: dict[str, str]) -> str:
        title = section.get("title", "")
        return title[:1].lower() + title[1:] if title[:1].isupper() else title

    def _goal(self, section: dict[str, str]) -> str:
        goal = section.get("goal", "")
        return goal[:1].upper() + goal[1:] if goal[:1].islower() else goal

'''
s = s.replace(old_respond, new_respond)

# `which_part` template in every language
WHICH = {
    "en": "Which part is fuzzy — the {title}, or what comes after it?",
    "ar": "أي جزء مش واضح — {title}، ولا اللي بعدها؟",
    "fr": "Quelle partie est floue : {title}, ou ce qui vient après ?",
    "sw": "Sehemu ipi haiko wazi: {title}, au kinachofuata?",
    "am": "የትኛው ክፍል ነው የማይገባህ — {title}፣ ወይስ ቀጣዩ?",
    "ha": "Wane bangare ba shi da kyau: {title}, ko abin da ke biyo baya?",
    "so": "Qaybtee aan caddayn: {title}, mise tan xigta?",
    "yo": "Apá wo ni kò yé ọ: {title}, tàbí èyí tó ń bọ̀?",
    "ig": "Akụkụ ole na-edoghị anya: {title}, ka nke na-esote?",
    "zu": "Iyiphi ingxenye engacaci: {title}, noma okulandelayo?",
}
for lang, line in WHICH.items():
    s = s.replace(f'        "step_plain":', f'        "which_part": "{line}",\n        "step_plain":', 1)

# generic (no plan) path also benefits from backchannels
s = s.replace(
    '''        if intent is Intent.AFFIRM:
            return f"{self._v('praise')} {self._p('next')}"
        return self._p("going_on")''',
    '''        if intent is Intent.AFFIRM:
            return f"{self._v('praise')} {self._p('next')}"
        return f"{react(self.language, self._variety)} {self._p('going_on')}"''',
)
open(P, "w").write(s)

import subprocess
print(subprocess.run(["python3", "-c", """
from app.providers.mock.dialogue import TutorDialogue
S=[{'title':'The idea of halving','goal':'sorted order is the precondition'},
   {'title':'Choosing the midpoint','goal':'mid = (low + high) // 2'},
   {'title':'Halving the space','goal':'discard the half that cannot hold the target'},
   {'title':'Stopping','goal':'know when the target is absent'}]
d=TutorDialogue.from_metadata({'topic_title':'Binary Search','sections':S},'en')
print('tutor:', d.opening()); print()
for line in ['mhm','yes','mhm','I dont get it','no','yes','yes','yes']:
    print('you  :', line); print('tutor:', d.respond(line)); print()
a=TutorDialogue.from_metadata({'topic_title':'Binary Search','sections':S},'ar')
print('ar   :', a.opening()); print('ar   :', a.respond('نعم'))
"""], capture_output=True, text=True).stdout)
