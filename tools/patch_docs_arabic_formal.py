"""Round 18 docs: Arabic is fusHa only - LANGUAGES / API / WEBSOCKET / PROVIDERS / README / REPORT.

Run once from the service root:  python3 tools/patch_docs_arabic_formal.py
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


# --------------------------------------------------------------------------- #
# LANGUAGES.md
# --------------------------------------------------------------------------- #

sub("docs/LANGUAGES.md", [
    (
        "| `ar` | Arabic — two registers: Egyptian (`ar-EG`) and fusHa (`ar-MSA`) | ✅ | ✅ | ✅ good | ✅ | ✅ | ❌ |",
        "| `ar` | Arabic — taught in Modern Standard Arabic (fusHa) | ✅ | ✅ | ✅ good | ✅ | ✅ | ❌ |",
    ),
    (
        '''## Arabic is one language and two registers

The language code is `ar` everywhere it matters — capability matrix, pipeline
plans, checkpoints, Progress Profile signals, the canonical-English concept store.
The *register* (`app/voice/dialects.py`) only decides how the tutor sounds:

| Register | Vendor voice | Phrase set | Instruction |
|---|---|---|---|
| `ar-EG` (default) | `ar-EG-SalmaNeural` | Egyptian (`ar`) | "speak Egyptian Arabic as people speak it in Egypt" |
| `ar-MSA` | `ar-SA-ZariyahNeural` | fusHa (`ar-msa`) | "speak clear Modern Standard Arabic, a simplified lecture voice" |

Both are offered in the demo's language picker (`العربية المصرية` / `العربية الفصحى`)
and can be switched mid-lesson exactly like a language switch: `POST
/voice/session/{id}/language {"language": "ar-MSA"}` or the WebSocket
`{"type": "language", "language": "ar-MSA"}`. The lesson, the checkpoint, the
covered concepts and the next step are untouched — only the voice and the wording
change, and `language.changed` reports `to: "ar"` with `dialect: "ar-MSA"`.''',
        '''## Arabic is taught in fusHa

The language code is `ar` everywhere it matters — capability matrix, pipeline
plans, checkpoints, Progress Profile signals, the canonical-English concept store.
Modern Standard Arabic is the only register (`app/voice/dialects.py`):

| Register | Vendor voice | Phrase set | Instruction |
|---|---|---|---|
| `ar-MSA` | `ar-SA-ZariyahNeural` | fusHa (`ar`) | "speak clear Modern Standard Arabic, a simplified lecture voice" |

The demo's picker offers Arabic once (`العربية الفصحى · Arabic (fusHa)`), and the
class-level `dialect` field is still on the session and on `POST
/voice/session/{id}/language` for clients that were written against the earlier
two-register API: every Egyptian spelling — `ar-EG`, `egyptian`, `masri`, `عامية`
— resolves to `ar-MSA`, so an older client is answered in fusHa instead of
failing the lesson. `language.changed` reports `to: "ar"` with
`dialect: "ar-MSA"`.''',
    ),
    (
        '''* The Arabic **register** is a session property (`dialect`), normalised once
  (`normalise_dialect`) and accepted as an alias anywhere the API takes a
  language: `ar-MSA`, `msa`, `fusha`, `egyptian`. Aliases that the service does
  not recognise fall back to the Egyptian default rather than failing a lesson.
* Arabic sessions are instructed to use natural, spoken Egyptian Arabic for
  explanations while keeping technical terms intelligible.''',
        '''* The Arabic **register** is a session property (`dialect`), normalised once
  (`normalise_dialect`) and accepted as an alias anywhere the API takes a
  language: `ar-MSA`, `msa`, `fusha` — and the older `ar-EG`, `egyptian`,
  `masri`. Every recognised spelling resolves to `ar-MSA`; anything unknown falls
  back to the same formal register rather than failing a lesson.
* Arabic sessions are instructed to use clear, simplified Modern Standard Arabic
  for explanations while keeping technical terms in English.''',
    ),
    (
        '''express them in the session language. In the offline demo, curated Egyptian-Arabic
translations cover the demo topics (`app/curriculum_localisation.py`), so an Arabic
session is spoken entirely in Arabic; other topics keep the English plan wording''',
        '''express them in the session language. In the offline demo, curated fusHa
translations cover the demo topics (`app/curriculum_localisation.py`), so an Arabic
session is spoken entirely in Arabic; other topics keep the English plan wording''',
    ),
])

# --------------------------------------------------------------------------- #
# API.md / WEBSOCKET_PROTOCOL.md
# --------------------------------------------------------------------------- #

sub("docs/API.md", [
    (
        '''`{"language": "sw"}` → re-plans the pipeline, keeps every piece of learning state.
For Arabic, the register rides along: `{"language": "ar-MSA"}` (or `{"language":
"ar", "dialect": "msa"}`) switches the Egyptian voice for the fusHa one without
touching the lesson. `dialect` is ignored for the other nine languages.''',
        '''`{"language": "sw"}` → re-plans the pipeline, keeps every piece of learning state.
Arabic is one language and one register: `{"language": "ar"}` (or the older
`{"language": "ar-MSA"}` / `{"dialect": "egyptian"}` spellings, which normalise to
`ar-MSA`) gives the formal voice and the formal phrase set without touching the
lesson. `dialect` is ignored for the other nine languages.''',
    ),
])

sub("docs/WEBSOCKET_PROTOCOL.md", [
    (
        '''| `language.changed` | `from`, `to`, `pipeline` |
| `language.changed` | `from`, `to`, `dialect`, `previous_dialect`, `pipeline`, `checkpoint_preserved` — for Arabic the register is reported alongside the language (`to: "ar"`, `dialect: "ar-MSA"`). |''',
        '''| `language.changed` | `from`, `to`, `dialect`, `previous_dialect`, `pipeline`, `checkpoint_preserved` — Arabic is reported with its register (`to: "ar"`, `dialect: "ar-MSA"`), which no longer changes: the lesson is always fusHa. |''',
    ),
])

# --------------------------------------------------------------------------- #
# PROVIDERS.md
# --------------------------------------------------------------------------- #

sub("docs/PROVIDERS.md", [
    ("| Arabic (Egypt) | `ar-EG-SalmaNeural` (or `ar-EG-ShakirNeural`) |",
     "| Arabic (fusHa) | `ar-SA-ZariyahNeural` (or `ar-SA-HamedNeural`) |"),
    (
        '''Two of those voices are Arabic registers: `ar-EG-SalmaNeural` for Egyptian and
`ar-SA-ZariyahNeural` for fusHa (`AZURE_VOICE_OVERRIDES=ar-MSA:ar-SA-HamedNeural`
swaps either one). The SSML is written to sound like a tutor, not an''',
        '''Arabic is taught in fusHa and spoken with `ar-SA-ZariyahNeural`
(`AZURE_VOICE_OVERRIDES=ar:ar-SA-HamedNeural` swaps it; an `ar-MSA:` override key
wins over the plain `ar` one). The SSML is written to sound like a tutor, not an''',
    ),
    ("Override any voice with `AZURE_VOICE_OVERRIDES=ar:ar-EG-ShakirNeural,en:en-US-JennyNeural`.",
     "Override any voice with `AZURE_VOICE_OVERRIDES=ar:ar-SA-HamedNeural,en:en-US-JennyNeural`."),
    ("python3 tools/verify_elevenlabs_voice.py ar          # Egyptian Arabic sample + .wav",
     "python3 tools/verify_elevenlabs_voice.py ar          # Arabic sample + .wav"),
    ("python3 tools/verify_elevenlabs_voice.py ar       # Egyptian Arabic sample + .wav + latency",
     "python3 tools/verify_elevenlabs_voice.py ar       # Arabic sample + .wav + latency"),
])

# --------------------------------------------------------------------------- #
# README.md
# --------------------------------------------------------------------------- #

sub("README.md", [
    (
        "| 10 languages | English, **Arabic in two registers (Egyptian `ar-EG` and fusHa `ar-MSA`)**, French, Swahili, Amharic, Hausa, Somali, Yoruba, Igbo, Zulu — selectable mid-lesson, register included. |",
        "| 10 languages | English, **Arabic (Modern Standard Arabic, `ar-MSA`)**, French, Swahili, Amharic, Hausa, Somali, Yoruba, Igbo, Zulu — selectable mid-lesson. |",
    ),
])
print("docs: LANGUAGES / API / WEBSOCKET / PROVIDERS / README synced to fusHa-only")
