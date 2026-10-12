"""Add browser-harness checks: the page must speak the naturalised text."""

P = "tests/browser/test_client_audio.py"
s = open(P).read()

s = s.replace('"embeddedHint,tabUrl,"', '"embeddedHint,tabUrl,speakable,"')

marker = "/* 11 - browser mode counts the PCM without playing it (diagnostics stay honest) */"
marker_unicode = "/* 11 \u2014 browser mode counts the PCM without playing it (diagnostics stay honest) */"
target = marker if marker in s else marker_unicode
assert target in s, "harness marker not found"

checks = (
    "/* 10b \u2014 the voice reads the *spoken* form, not the written one. A synthesiser\n"
    "   given \"mid = (low + high) // 2\" says punctuation names; a tutor says words. */\n"
    "check('speakable_turns_maths_into_words',\n"
    "      client.speakable('mid = (low + high) // 2') === 'mid equals low plus high divided by 2',\n"
    "      client.speakable('mid = (low + high) // 2'));\n"
    "check('speakable_removes_dashes_and_brackets',\n"
    "      client.speakable('first \u2014 then (again)') === 'first, then again',\n"
    "      client.speakable('first \u2014 then (again)'));\n"
    "spoken.length = 0;\n"
    "client.setVoiceMode('browser');\n"
    "handle({ event:'assistant.text.delta', text:'The midpoint is mid = (low + high) // 2.' });\n"
    "check('the_voice_hears_words_not_symbols',\n"
    "      spoken.length > 0 && !/[\\\\/|=]|\\\\(/.test(spoken.join(' ')), spoken.slice());\n"
    "client.setVoiceMode('both');\n\n"
)
s = s.replace(target, checks + target, 1)
open(P, "w").write(s)
print("harness updated:", "speakable_turns_maths_into_words" in open(P).read())
