"""Round 15b docs sync: 298 -> 301 tests + the coverage gate in PROVIDERS.md."""
import io


def sub(path, pairs):
    s = io.open(path, encoding="utf-8").read()
    for old, new in pairs:
        assert old in s, (path, old[:60])
        s = s.replace(old, new, 1)
    io.open(path, "w", encoding="utf-8").write(s)


sub("docs/TESTING.md", [
    ("| **Total** | | **298 passing** |", "| **Total** | | **301 passing** |"),
    ("**the Azure free-tier voice**) | **173**", "**the Azure free-tier voice**, **the coverage gate**) | **176**"),
    (
        "`test_azure_tts.py` (7) pins the Azure request/response contract offline |",
        "`test_azure_tts.py` (7) pins the Azure request/response contract offline; three more demo-voice tests pin the coverage gate that stops a vendor being asked for a language it has no voice for |",
    ),
])

sub("README.md", [
    ("with 298 passing", "with 301 passing"),
    ("pytest -q                       # 298 tests", "pytest -q                       # 301 tests"),
])

sub("IMPLEMENTATION_REPORT.md", [
    ("**298/298 automated tests passing", "**301/301 automated tests passing"),
    ("| **Yes** | 298 tests, offline |", "| **Yes** | 301 tests, offline |"),
    ("pytest -q                 # 298 passed", "pytest -q                 # 301 passed"),
])

GATE = (
    "The demo voice is **coverage-gated** (`CoverageGatedTTS`): a vendor is only asked\n"
    "to speak a language it actually has a voice for (`vendor_covers_language`). Azure\n"
    "declines Hausa, Yoruba and Igbo; ElevenLabs declines Igbo and Yoruba. Without the\n"
    "gate the vendor raises `unsupported`, and on a composed pipeline the router reads\n"
    "that as a *provider failure* - it fails the pipeline over mid-turn and the answer\n"
    "arrives silent. With it, those languages simply keep the synthetic voice the\n"
    "pipeline already had."
)
sub("docs/PROVIDERS.md", [
    (
        "With Azure configured, `VOICE_DEMO_VOICE=auto` picks **Azure before ElevenLabs**: 0.5M\n"
        "characters a month is ~50\u00d7 the talking time of ElevenLabs' free 10 000 credits.",
        "With Azure configured, `VOICE_DEMO_VOICE=auto` picks **Azure before ElevenLabs**: 0.5M\n"
        "characters a month is ~50\u00d7 the talking time of ElevenLabs' free 10 000 credits.\n\n" + GATE,
    ),
])

print("docs synced to 301")
