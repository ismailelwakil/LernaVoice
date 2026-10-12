"""Sync the implementation report with the live ElevenLabs bring-up."""

P = "IMPLEMENTATION_REPORT.md"
s = open(P).read()

# 1) row 4f: no longer "unverified"
old_start = "| 4f | Real human voice for the **offline** demo"
i = s.index(old_start)
j = s.index("\n", i)
row = s[i:j]
assert "unverified" in row, row
new_row = (
    "| 4f | Real human voice for the **offline** demo \u2014 the dialogue stays local, "
    "the speech comes from a vendor (`VOICE_DEMO_VOICE`) | **Yes \u2014 verified against the "
    "live vendor** (en/ar/fr streamed, 666\u20131048 ms to first audio; sw/am/ha/so/zu over REST "
    "with `eleven_v4_turbo`, 599\u20131032 ms) | `app/voice/demo_voice.py` + "
    "`ProviderFactory.build_pipeline()`; the vendor's PCM bytes reach the student unchanged "
    "(`tools/check_demo_voice_live.py` proves it from a real WebSocket: speech has thousands of "
    "distinct samples per second, the synthetic tone a few dozen), a failing vendor falls back "
    "and is counted, `/health` reports the voice name only, `GET /voice/voices` lists voices "
    "server-side. Tests: `test_demo_voice.py` (15), `test_elevenlabs_transport.py` (12) |"
)
s = s[:i] + new_row + s[j:]

# 2) limitation 13: now covered by curated translations for the demo topics
old13 = "13. **In the offline mock, the lesson *content* is English while the *tutoring*"
i = s.index(old13)
j = s.index("14. **", i)
new13 = (
    "13. **In the offline mock the lesson content is English, except where curated\n"
    "    translations exist.** `app/curriculum_localisation.py` carries hand-written\n"
    "    Egyptian-Arabic translations for the demo topics (Binary Search, Merge Sort,\n"
    "    Recursion), so an Arabic session is spoken entirely in Arabic \u2014 plan wording\n"
    "    included \u2014 while the service keeps the catalogue's own (English) naming for\n"
    "    state, checkpoints and resume. Other topics, and the other nine languages, are\n"
    "    still spoken as written, wrapped in localised scaffolding. Live vendor sessions\n"
    "    do not need this: the model receives the plan with the instruction to express it\n"
    "    in the target language.\n"
)
s = s[:i] + new13 + s[j:]

# 3) a new limitation for the free-plan realities, renumbering the Streamlit one
old14 = "14. **The Streamlit app is a developer harness, not a frontend.**"
i = s.index(old14)
s = s[:i] + (
    "14. **The demo voice runs on the ElevenLabs free plan.** 10 000 credits/month\n"
    "    (\u2248 10 minutes of speech), non-commercial, and *library* voices are refused\n"
    "    through the API (HTTP 402: \"Free users cannot use library voices\") \u2014 the demo\n"
    "    uses a voice the plan allows and `tools/verify_elevenlabs_voice.py` probes\n"
    "    alternatives automatically. ElevenLabs TTS covers 8 of the 10 mandatory\n"
    "    languages (no Igbo, no Yoruba): those two keep the Gemini/browser voice.\n"
    "15. **The Streamlit app is a developer harness, not a frontend.**" + s[i + len(old14):]
)
open(P, "w").write(s)
print("report updated:", "verified against the live vendor" in s, "15. **The Streamlit" in s)
