"""Round 16 docs: two Arabic registers + the humanised Azure voice.

Run once from the service root:  python3 tools/patch_docs_round16.py
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
        "| `ar` | Arabic (incl. Egyptian `ar-EG`) | ✅ | ✅ | ✅ good | ✅ | ✅ | ❌ |",
        "| `ar` | Arabic — two registers: Egyptian (`ar-EG`) and fusHa (`ar-MSA`) | ✅ | ✅ | ✅ good | ✅ | ✅ | ❌ |",
    ),
    (
        "## Resulting pipelines",
        """## Arabic is one language and two registers

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
change, and `language.changed` reports `to: "ar"` with `dialect: "ar-MSA"`.

## Resulting pipelines""",
    ),
    (
        """* Arabic sessions are instructed to use natural, spoken Egyptian Arabic for""",
        """* The Arabic **register** is a session property (`dialect`), normalised once
  (`normalise_dialect`) and accepted as an alias anywhere the API takes a
  language: `ar-MSA`, `msa`, `fusha`, `egyptian`. Aliases that the service does
  not recognise fall back to the Egyptian default rather than failing a lesson.
* Arabic sessions are instructed to use natural, spoken Egyptian Arabic for""",
    ),
])

# --------------------------------------------------------------------------- #
# API.md
# --------------------------------------------------------------------------- #

sub("docs/API.md", [
    (
        '''  "language": "ar",''',
        '''  "language": "ar",
  "dialect": "ar-MSA",''',
    ),
    (
        '''### `POST /voice/session/{id}/language`
`{"language": "sw"}` → re-plans the pipeline, keeps every piece of learning state.''',
        '''### `POST /voice/session/{id}/language`
`{"language": "sw"}` → re-plans the pipeline, keeps every piece of learning state.
For Arabic, the register rides along: `{"language": "ar-MSA"}` (or `{"language":
"ar", "dialect": "msa"}`) switches the Egyptian voice for the fusHa one without
touching the lesson. `dialect` is ignored for the other nine languages.''',
    ),
    (
        '''### `GET /voice/languages`
Static capability documentation for all ten languages: name, primary pipeline,''',
        '''### `GET /voice/languages`
Static capability documentation for all ten languages: name, primary pipeline,''',
    ),
])

# the create/change request bodies both carry `dialect`
s = read("docs/API.md")
s = s.replace('"language": "ar",\n  "dialect": "ar-MSA",', '"language": "ar",\n  "dialect": "ar-MSA",', 1)
write("docs/API.md", s)

# --------------------------------------------------------------------------- #
# WEBSOCKET_PROTOCOL.md
# --------------------------------------------------------------------------- #

sub("docs/WEBSOCKET_PROTOCOL.md", [
    (
        "| `language.changed`",
        "| `language.changed`",
    ),
])

s = read("docs/WEBSOCKET_PROTOCOL.md")
if "dialect" not in s:
    marker = "| `learning.signal`"
    addition = (
        "| `language.changed` | `from`, `to`, `dialect`, `previous_dialect`, "
        "`pipeline`, `checkpoint_preserved` — for Arabic the register is reported "
        "alongside the language (`to: \"ar\"`, `dialect: \"ar-MSA\"`). |\n"
    )
    assert marker in s
    s = s.replace(marker, addition + marker, 1)
    write("docs/WEBSOCKET_PROTOCOL.md", s)
print("LANGUAGES / API / WEBSOCKET ok")

# --------------------------------------------------------------------------- #
# README + TESTING + the report
# --------------------------------------------------------------------------- #

sub("README.md", [
    (
        "| 10 languages | English, Arabic (incl. Egyptian), French, Swahili, Amharic, Hausa, Somali, Yoruba, Igbo, Zulu — selectable mid-lesson. |",
        "| 10 languages | English, **Arabic in two registers (Egyptian `ar-EG` and fusHa `ar-MSA`)**, French, Swahili, Amharic, Hausa, Somali, Yoruba, Igbo, Zulu — selectable mid-lesson, register included. |",
    ),
    ("with 301 passing", "with 322 passing"),
    ("pytest -q                       # 301 tests", "pytest -q                       # 322 tests"),
])

sub("docs/TESTING.md", [
    ("| **Total** | | **301 passing** |", "| **Total** | | **322 passing** |"),
    ("**the coverage gate**) | **176**", "**the coverage gate**, **Arabic's two registers**) | **197**"),
    (
        "three more demo-voice tests pin the coverage gate that stops a vendor being asked for a language it has no voice for |",
        "three more demo-voice tests pin the coverage gate that stops a vendor being asked for a language it has no voice for; `test_arabic_dialects.py` (21) pins Egyptian vs fusHa — the voice each register gets, the SSML (style, pauses, emphasis), the fusHa phrase set, the register surviving a mid-lesson switch, and the style-refusal retry |",
    ),
])

sub("IMPLEMENTATION_REPORT.md", [
    ("**301/301 automated tests passing", "**322/322 automated tests passing"),
    ("| **Yes** | 301 tests, offline |", "| **Yes** | 322 tests, offline |"),
    ("pytest -q                 # 301 passed", "pytest -q                 # 322 passed"),
    (
        "| 5 | Smart checkpointing on *learning state*, not audio timestamps |",
        """| 4i | **Arabic in two registers** — Egyptian and fusHa, both first-class options | **Yes — run live on `germanywestcentral`** (MSA session: `مرحبًا بك… نتناول اليوم`, 905 KB of audio; switched to `ar-EG` mid-lesson: `هنكمل بالعربي من هنا…`, 707 KB, lesson still on "The idea of halving") | `app/voice/dialects.py` (registry + aliases), `AzureTTSProvider.voice_for(..., dialect)`, the `ar-msa` phrase set in `app/prompts/interaction.py`, the register sentence in the system instruction, `session.change_language("ar-MSA")`, and the picker's two Arabic entries. The language code stays `ar` for routing, checkpoints and the canonical-English concept store. Tests: `test_arabic_dialects.py` (21) |
| 4j | **The voice sounds human, not like an announcement** | **Yes** | `AzureTTSProvider._ssml` adds the vendor's expressive style (`cheerful`, degree 1.05), a `+2%` pitch lift, a `<break>` at sentence and clause boundaries and moderate `<emphasis>` on the English technical terms; a voice that refuses the style costs exactly one un-styled retry and is remembered. Listenable A/B: `demo-audio/arabic-humanised.wav` |
| 5 | Smart checkpointing on *learning state*, not audio timestamps |""",
    ),
])
print("README / TESTING / report ok")
