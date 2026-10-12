"""Round 18 counts + wording (part 1: README, TESTING).

Run once from the service root:  python3 tools/patch_counts_324a.py
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


sub("README.md", [
    ("> **Status:** feature-complete against the implementation spec, with 322 passing",
     "> **Status:** feature-complete against the implementation spec, with 324 passing"),
    ("pytest -q                       # 322 tests",
     "pytest -q                       # 324 tests"),
    ("""- **browser voice** (demo default) — each sentence is spoken the moment it
  completes, using the best voice installed for the session language, so the
  answer starts immediately. Nothing to install; no network.""",
     """- **browser voice** (demo default) — each sentence is spoken the moment it
  completes, using the best voice installed for the session language (the
  standard Arabic voice, `ar-SA`, ahead of a dialect one), so the answer starts
  immediately. Nothing to install; no network.
- **service PCM** is the *humanised* path whenever a vendor key is present:
  Azure AI Speech, with `mstts:express-as style="cheerful"`, a small pitch lift,
  breaths at sentence and clause boundaries and emphasis on English terms."""),
    ("cp .env.example .env      # add ELEVENLABS_API_KEY / GEMINI_API_KEY / DEEPGRAM_API_KEY",
     "cp .env.example .env      # add AZURE_SPEECH_KEY + AZURE_SPEECH_REGION / GEMINI_API_KEY / …"),
    ("| `ELEVENLABS_API_KEY`, `DEEPGRAM_API_KEY` | Backup vendors |",
     "| `AZURE_SPEECH_KEY`, `AZURE_SPEECH_REGION` | The demo's humanised voice (free F0 tier, 0.5M chars/month) |\n| `ELEVENLABS_API_KEY`, `DEEPGRAM_API_KEY` | Backup vendors |"),
])

sub("docs/TESTING.md", [
    ("**Arabic's two registers**) | **197**",
     "**Arabic's fusHa register and the Egyptian aliases that normalise to it**) | **199**"),
    ("`test_arabic_dialects.py` (21) pins Egyptian vs fusHa — the voice each register gets, the SSML (style, pauses, emphasis), the fusHa phrase set, the register surviving a mid-lesson switch, and the style-refusal retry |",
     "`test_arabic_dialects.py` (23) pins the formal register — the voice it gets, the SSML (style, pauses, emphasis), the fusHa phrase table, the Egyptian spellings that normalise to `ar-MSA` instead of failing, and the style-refusal retry |"),
    ("| **Total** | | **322 passing** |",
     "| **Total** | | **324 passing** |"),
])
print("README + TESTING at 324 / fusHa")
