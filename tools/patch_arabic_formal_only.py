"""Round 17: Arabic is taught in fusHa only - the Egyptian register is cancelled.

Promotes the fusHa lines to be *the* Arabic lines (`ar`), and drops the `ar-msa`
tables, so nothing downstream has to know about registers any more.

Run once from the service root:  python3 tools/patch_arabic_formal_only.py
"""
import io
import re

PATH = "app/prompts/interaction.py"


def read(p):
    return io.open(p, encoding="utf-8").read()


def write(p, s):
    io.open(p, "w", encoding="utf-8").write(s)


def block(text, header):
    """The literal `{...}` or `(...)` that follows `header`, braces balanced."""
    i = text.index(header)
    opener = text.index("{" if "{" in header else "(", i + len(header) - 1)
    opener = i + len(header) - 1 if text[i + len(header) - 1] in "({" else text.index(
        "{" if "{" in header.split()[-1] else "(", i
    )
    opener = i + len(header) - 1
    closer = "}" if text[opener] == "{" else ")"
    depth = 0
    k = opener
    while True:
        if text[k] == text[opener]:
            depth += 1
        elif text[k] == closer:
            depth -= 1
        if depth == 0:
            break
        k += 1
    return opener, k + 1, text[opener : k + 1]


def inner(block_text, indent="        "):
    """The body of a literal, re-indented, without the outer braces."""
    body = block_text.strip()[1:-1].strip("\n")
    lines = [ln for ln in body.split("\n")]
    stripped = [ln.strip() for ln in lines if ln.strip()]
    return "\n".join(indent + ln for ln in stripped)


s = read(PATH)

# --------------------------------------------------------------------------- #
# 1. INTERACTION_PHRASES / PHRASE_VARIANTS: fusHa becomes the Arabic table
# --------------------------------------------------------------------------- #

for name in ("INTERACTION_PHRASES", "PHRASE_VARIANTS"):
    src_start, src_end, src = block(s, f'{name}["ar-msa"] = {{')
    # the `ar` entry as it stands inside the parent dict
    dst_start, dst_end, _ = block(s, '    "ar": {')
    body = inner(src)
    s = s[:dst_start] + "{\n" + body + "\n    }" + s[dst_end:]
    # re-locate the appended source block (offsets moved) and cut it out
    src_start, src_end, _ = block(s, f'{name}["ar-msa"] = {{')
    line_start = s.rfind("\n", 0, src_start) + 1
    s = s[:line_start] + s[src_end:] + ""

# --------------------------------------------------------------------------- #
# 2. STEP_LEAD / MOVE_ON / REACT: same, for the tuples
# --------------------------------------------------------------------------- #

for name in ("STEP_LEAD", "MOVE_ON", "REACT"):
    src_start, src_end, src = block(s, f'{name}["ar-msa"] = (')
    dst_start, dst_end, _ = block(s, '    "ar": (')
    s = s[:dst_start] + src + s[dst_end:]
    src_start, src_end, _ = block(s, f'{name}["ar-msa"] = (')
    line_start = s.rfind("\n", 0, src_start) + 1
    s = s[:line_start] + s[src_end:]

# --------------------------------------------------------------------------- #
# 3. tidy the trailing section header and the docstring
# --------------------------------------------------------------------------- #

s = re.sub(
    r"\n# -{20,} #\n# Arabic in fusHa \(\"ar-msa\"\)\n# -{20,} #\n(# .*\n)*",
    "\n",
    s,
)
s = s.replace(
    """On the translations: these are brief, hand-written teaching phrases (matching the
style of `INTERRUPT_ACK` and `RESUME_TRANSITION` in `languages.py`), written to be
short and unambiguous rather than literary.""",
    """On the translations: these are brief, hand-written teaching phrases (matching the
style of `INTERRUPT_ACK` and `RESUME_TRANSITION` in `languages.py`), written to be
short and unambiguous rather than literary. Arabic is **Modern Standard Arabic**
(fusHa) throughout - the Egyptian register was removed on request; the phrase
tables are the single source for how the offline tutor speaks Arabic.""",
)
write(PATH, s)

# sanity: no register tables left, and Arabic now greets formally
left = read(PATH)
assert '"ar-msa"' not in left, "the fusHa tables should have been merged into `ar`"
assert "نتناول اليوم" in left and "النهاردة" not in left
print("interaction.py: Arabic is fusHa")
