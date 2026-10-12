"""Round 18 counts + wording (part 2: IMPLEMENTATION_REPORT).

Run once from the service root:  python3 tools/patch_counts_324b.py
"""
import io


def read(p):
    return io.open(p, encoding="utf-8").read()


def write(p, s):
    io.open(p, "w", encoding="utf-8").write(s)


def sub(path, pairs):
    s = read(path)
    for old, new in pairs:
        assert old in s, (path, old[:70])
        s = s.replace(old, new, 1)
    write(path, s)


row_4i_old = "| 4i | **Arabic in two registers** \u2014 Egyptian and fusHa, both first-class options"
row_4i_new = "| 4i | **Arabic is taught in Modern Standard Arabic (fusHa) only** \u2014 one register, end to end"

p = "IMPLEMENTATION_REPORT.md"
s = read(p)
start = s.index(row_4i_old)
end = s.index("\n", start)
new_row = (
    row_4i_new
    + " | **Yes \u2014 run live on `germanywestcentral`** (fusHa session: "
    + "\u00abمرحبًا بك، لنبدأ الدرس. نتناول اليوم البحث الثنائي\u2026\u00bb, 905 KB of audio; "
    + "the plan, the checkpoint and the concepts are untouched by the register) | "
    + "`app/voice/dialects.py` (a single `ar-MSA` entry; every Egyptian spelling \u2014 "
    + "`ar-EG`, `egyptian`, `masri` \u2014 normalises to it, so an older client is "
    + "answered in fusHa instead of failing), `AzureTTSProvider.voice_for(\u2026, dialect)` "
    + "\u2192 `ar-SA-ZariyahNeural`, the formal phrase table in `app/prompts/interaction.py`, "
    + "the formal greeting and the runtime instruction (`app/prompts/languages.py`), "
    + "`app/curriculum_localisation.py` in fusHa, and the picker's single Arabic entry. "
    + "The language code stays `ar` for routing, checkpoints and the canonical-English "
    + "concept store. Tests: `test_arabic_dialects.py` (23) |"
)
write(p, s[:start] + new_row + s[end:])

sub("IMPLEMENTATION_REPORT.md", [
    ("Python 3.13 \u00b7 **322/322 automated tests passing, zero paid credentials required.**",
     "Python 3.13 \u00b7 **324/324 automated tests passing, zero paid credentials required.**"),
    ("| 29 | pytest suites incl. mocks, no paid credentials | **Yes** | 322 tests, offline |",
     "| 29 | pytest suites incl. mocks, no paid credentials | **Yes** | 324 tests, offline |"),
    ("pytest -q                 # 322 passed",
     "pytest -q                 # 324 passed"),
    ("the browser picks the most natural installed voice, prefers an Egyptian voice for Arabic, and reports when the device has none.",
     "the browser picks the most natural installed voice, prefers the standard Arabic voice (`ar-SA`) over a dialect one, and reports when the device has none."),
    ("| Arabic (incl. Egyptian) | Gemini Live | STT \u00d73, TTS \u00d72 | no Deepgram TTS |",
     "| Arabic (fusHa) | Gemini Live | STT \u00d73, TTS \u00d72 | no Deepgram TTS |"),
    ("Egyptian-Arabic translations for the demo topics (Binary Search, Merge Sort,",
     "fusHa translations for the demo topics (Binary Search, Merge Sort,"),
])
print("IMPLEMENTATION_REPORT at 324 / fusHa-only")
