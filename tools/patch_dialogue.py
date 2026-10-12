"""Patch: humanise the mock dialogue — varied lines, no check-in after every step."""

P = "app/providers/mock/dialogue.py"
s = open(P).read()

s = s.replace(
    "from app.prompts.interaction import phrase",
    "from app.prompts.interaction import phrase, phrase_variants",
)

# ---------------------------------------------------------------- state
s = s.replace(
    """    #: Which check-in variant to use next, so the tutor does not sound scripted.
    _variety: int = 0
    #: How many times the student has said they are lost (drives the explanation route).
    _explain_style: int = 0""",
    """    #: Rotating cursor: which variant of a repeated line to use next.
    _variety: int = 0
    #: How many times the student has said they are lost (drives the explanation route).
    _explain_style: int = 0
    #: Last variant index used per key, so a line never repeats back-to-back.
    _used: dict[str, int] = field(default_factory=dict)""",
)

# ---------------------------------------------------------------- helpers
s = s.replace(
    '''    def _p(self, key: str) -> str:
        return phrase(self.language, key)''',
    '''    def _p(self, key: str) -> str:
        return phrase(self.language, key)

    def _v(self, key: str) -> str:
        """Another way of saying `key` — rotating, never the one just used.

        A tutor that answers every turn with the same sentence ("Does that make sense so
        far?") sounds like a prompt template. Each call walks the language's variants.
        """
        options = phrase_variants(self.language, key)
        if len(options) == 1:
            return options[0]
        last = self._used.get(key, -1)
        index = (last + 1) % len(options) if last >= 0 else self._variety % len(options)
        self._used[key] = index
        self._variety += 1
        return options[index]

    def _asking(self) -> bool:
        """Should this turn end with a question?

        Deliberately not every turn: explain, keep explaining, let the student break in.
        Roughly every second step gets a check, and one is always offered at the end.
        """
        return self.step % 2 == 1''',
)

# ---------------------------------------------------------------- opening
s = s.replace(
    '''        if not self.planned:
            return f"{greeting}{who} {self._p('check')}"
        first = self.sections[0]
        return (
            f"{greeting}{who} {self._topic_line()} "
            f"{self._t('step_one', title=first['title'], goal=first.get('goal', ''))} "
            f"{self._p('check')}"
        )''',
    '''        if not self.planned:
            return f"{greeting}{who} {self._p('invite_stop')}"
        first = self.sections[0]
        # The first turn does not interrogate the student — it teaches and hands them
        # the turn ("jump in whenever you want") instead of asking if it made sense.
        return (
            f"{greeting}{who} {self._topic_line()} "
            f"{self._t('step_one', title=first['title'], goal=first.get('goal', ''))} "
            f"{self._p('invite_stop')}"
        )''',
)

# ---------------------------------------------------------------- language switch
s = s.replace(
    '''        return self._name(
            f"{self._p('switch')} "
            f"{self._t('on_step', title=step['title'], goal=step.get('goal', ''))} "
            f"{self._p('check')}"
        )''',
    '''        return self._name(
            f"{self._p('switch')} "
            f"{self._t('on_step', title=step['title'], goal=step.get('goal', ''))} {tail}"
        )'''
    if False
    else '''        tail = self._p("check") if self._asking() else self._p("invite_stop")
        return self._name(
            f"{self._p('switch')} "
            f"{self._t('on_step', title=step['title'], goal=step.get('goal', ''))} {tail}"
        )''',
)

# ---------------------------------------------------------------- respond()
start = s.index("    def respond(self, student_text: str) -> str:")
end = s.index("    def _simpler(self, section: dict[str, str]) -> str:")
NEW_RESPOND = '''    def respond(self, student_text: str) -> str:
        """The tutor's next turn, driven by what the student actually said."""
        intent = classify(student_text)
        if not self.planned:
            return self._name(self._generic(intent))

        current = self.sections[min(self.step, len(self.sections) - 1)]

        if intent is Intent.CONFUSED:
            # Do not advance, do not repeat, and do not ask them to confirm it worked:
            # explain by another route and leave the floor open.
            self._explain_style += 1
            route = self._explain_style % 3
            if route == 1:
                return self._name(
                    f"{self._v('rephrase')} {self._p('simpler')} "
                    f"{self._t('think_of', title=current['title'], goal=self._simpler(current))} "
                    f"{self._v('encourage')}"
                )
            if route == 2:
                return self._name(
                    f"{self._v('rephrase')} "
                    f"{self._t('smaller', goal=self._simpler(current))} {self._v('encourage')}"
                )
            return self._name(f"{self._v('rephrase')} {self._p('example')}")

        if intent is Intent.AFFIRM:
            self.step += 1
            if self.step >= len(self.sections):
                return self._name(f"{self._v('praise')} {self._v('close')}")
            step = self.sections[self.step]
            if self._asking():
                return self._name(
                    f"{self._v('praise')} "
                    f"{self._t('next_step', title=step['title'], goal=step.get('goal', ''))} "
                    f"{self._v('check')}"
                )
            # No question this turn: keep teaching and roll straight into the step after
            # it, so the lesson sounds like an explanation rather than an interrogation.
            line = (
                f"{self._v('praise')} "
                f"{self._t('next_step', title=step['title'], goal=step.get('goal', ''))}"
            )
            if self.step + 1 < len(self.sections):
                self.step += 1
                following = self.sections[self.step]
                line += (
                    f" {self._p('going_on')} "
                    f"{self._t('step_one', title=following['title'], goal=following.get('goal', ''))}"
                )
            return self._name(line)

        if intent is Intent.QUESTION:
            return self._name(
                f"{self._p('answer_ack')} "
                f"{self._t('on_current', title=current['title'], goal=current.get('goal', ''))} "
                f"{self._p('invite')}"
            )

        # Plain participation: carry on teaching without demanding an answer.
        return self._name(
            f"{self._t('on_step', title=current['title'], goal=current.get('goal', ''))} "
            f"{self._p('going_on')}"
        )

'''
s = s[:start] + NEW_RESPOND + s[end:]

# ---------------------------------------------------------------- generic (no plan)
s = s.replace(
    '''    def _generic(self, intent: Intent) -> str:
        if intent is Intent.CONFUSED:
            return f"{self._p('rephrase')} {self._p('check')}"
        if intent is Intent.QUESTION:
            return f"{self._p('answer_ack')} {self._p('invite')}"
        if intent is Intent.AFFIRM:
            return f"{self._p('praise')} {self._p('next')}"
        return self._p("check")''',
    '''    def _generic(self, intent: Intent) -> str:
        if intent is Intent.CONFUSED:
            return f"{self._v('rephrase')} {self._v('encourage')}"
        if intent is Intent.QUESTION:
            return f"{self._p('answer_ack')} {self._p('invite')}"
        if intent is Intent.AFFIRM:
            return f"{self._v('praise')} {self._p('next')}"
        return self._p("going_on")''',
)

open(P, "w").write(s)

import subprocess
print(subprocess.run(["python3", "-c", """
from app.providers.mock.dialogue import TutorDialogue
S=[{'title':'The idea of halving','goal':'compare with the middle'},{'title':'Choosing the midpoint','goal':'mid = (low + high) // 2'},{'title':'Halving the space','goal':'discard the impossible half'},{'title':'Stopping','goal':'know when it is absent'}]
d=TutorDialogue.from_metadata({'topic_title':'Binary Search','sections':S},'en')
print('open   :', d.opening())
for line in ['yes','yes','no, I dont understand','yes','yes','yes']:
    print('student:', line); print('tutor  :', d.respond(line))
"""], capture_output=True, text=True).stdout)
