"""Round 18: the two Arabic-language docs stop pointing at the Egyptian voice.

Run once from the service root:  python3 tools/patch_docs_arabic_formal2.py
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


sub("docs/FREE_VOICE_OPTIONS_AR.md", [
    (
        """إنجليزي · **مصري (ar-EG)** · فرنسي · سواحيلي · أمهري · صومالي · زولو.""",
        """إنجليزي · **عربي** · فرنسي · سواحيلي · أمهري · صومالي · زولو.
والعربي دلوقتي بيتعلّم **بالفصحى**: الصوت `ar-SA-ZariyahNeural` (وبديل رجالي
`ar-SA-HamedNeural`) — الأصوات المصرية لسه موجودة عند مايكروسوفت بس الخدمة بتكلّم
بالفصحى، وده اللي بيتحفظ في الفحص.""",
    ),
    (
        """- الأصوات المختارة لكل لغة: `ar-EG-SalmaNeural` · `ar-EG-ShakirNeural` (بديل) · `sw-KE-ZuriNeural` ·
  `am-ET-MekdesNeural` · `so-SO-UbaxNeural` · `zu-ZA-ThandoNeural` · `en-US-AvaMultilingualNeural`.""",
        """- الأصوات المختارة لكل لغة: `ar-SA-ZariyahNeural` · `ar-SA-HamedNeural` (بديل) · `sw-KE-ZuriNeural` ·
  `am-ET-MekdesNeural` · `so-SO-UbaxNeural` · `zu-ZA-ThandoNeural` · `en-US-AvaMultilingualNeural`.
  (لو عايز ترجّع الصوت المصري مؤقتًا: `AZURE_VOICE_OVERRIDES=ar:ar-EG-SalmaNeural` — من غير أي تغيير في الكود.)""",
    ),
])

sub("docs/GET_VOICE_FREE_AR.md", [
    (
        """   `Natural` (مثلاً `Microsoft Salma Online (Natural) — ar-EG` للعربي، أو `Microsoft Aria Online
   (Natural)` للإنجليزي). الصفحة بتختار الأحسن لوحدها، بس الاختيار اليدوي أوضح.""",
        """   `Natural` (مثلاً `Microsoft Maged Online (Natural) — ar-SA` للعربي، أو `Microsoft Aria Online
   (Natural)` للإنجليزي). الصفحة بتختار الأحسن لوحدها — وهي بتفضّل صوت `ar-SA` القياسي
   على أي صوت لهجة — بس الاختيار اليدوي أوضح.""",
    ),
])
print("Arabic docs point at the fusHa voice")
