"""Round 17 (take 2): make the fusHa lines *the* Arabic lines, drop `ar-msa`.

Renders the `ar` entries from the runtime fusHa tables (already loaded) instead of
splicing braces in text - the first attempt mangled the table.

Run once from the service root:  python3 tools/patch_arabic_formal_only2.py
"""
import io
import json
import sys

sys.path.insert(0, ".")
from app.prompts import interaction as I  # noqa: E402  (reads the current file)

PATH = "app/prompts/interaction.py"
s = io.open(PATH, encoding="utf-8").read()


def replace_entry(text, name, rendered):
    """Swap the `"ar"` entry of a top-level table for `rendered`."""
    start = text.index("\n" + name)
    i = text.index('    "ar":', start)
    end = text.index('\n    "', i + 5)          # the next language starts here
    return text[:i] + rendered + text[end + 1 :]


def as_dict_block(table, indent="    "):
    lines = [f'{indent}"ar": {{']
    for key, value in table.items():
        lines.append(f'{indent}    {json.dumps(key)}: {json.dumps(value, ensure_ascii=False)},')
    lines.append(f"{indent}}},")
    return "\n".join(lines)


def as_tuple_block(values, indent="    "):
    body = ", ".join(json.dumps(v, ensure_ascii=False) for v in values)
    return f'{indent}"ar": ({body}),'


s = replace_entry(s, "INTERACTION_PHRASES", as_dict_block(I.INTERACTION_PHRASES["ar-msa"]))
s = replace_entry(s, "PHRASE_VARIANTS", as_dict_block(I.PHRASE_VARIANTS["ar-msa"]))
for name in ("STEP_LEAD", "MOVE_ON", "REACT"):
    s = replace_entry(s, name, as_tuple_block(getattr(I, name)["ar-msa"]))

# cut the appended fusHa section out entirely
marker = '# Arabic in fusHa ("ar-msa")'
banner = s.index(marker)
banner = s.rindex("# ------", 0, banner)
tail = s.index("REACT[\"ar-msa\"] = (", banner)
tail_end = s.index("\n", tail) + 1
s = s[:banner] + s[tail_end:]

s = s.replace(
    """short and unambiguous rather than literary. They exist so the demo can be heard in
each language without a vendor key; with real credentials the model produces its
own, natively fluent phrasing and these are only used for the mock.""",
    """short and unambiguous rather than literary. They exist so the demo can be heard in
each language without a vendor key; with real credentials the model produces its
own, natively fluent phrasing and these are only used for the mock. Arabic is
**Modern Standard Arabic (fusHa)** throughout: the Egyptian register was removed
on request, and `ar` is the only Arabic phrase table.""",
)
io.open(PATH, "w", encoding="utf-8").write(s)
print("written")
