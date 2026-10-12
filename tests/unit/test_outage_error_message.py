"""Round 29 — a provider outage must NOT be mislabelled as "language unsupported".

Regression for the console toast "Could not process that request:
UnsupportedLanguageError": when the language *is* supported but every available
pipeline failed to connect, the session should surface the provider-unavailable
error, not claim the language is unsupported.
"""

import pytest

from app.voice.provider_router import UnsupportedLanguageError


@pytest.mark.asyncio
async def test_exhausted_pipelines_report_outage_not_unsupported_language(dialogue_session):
    session = dialogue_session
    queue = session.subscribe()

    # We already tried (and failed) at least one pipeline for this language...
    session._failed_signatures.add("realtime:gemini")
    # ...and now the router finds no *remaining* plan. This is the outage case.
    def _no_plan(language, *, exclude=()):
        raise UnsupportedLanguageError(f"no plan for {language}")

    session.router.select_pipeline = _no_plan

    with pytest.raises(Exception):
        await session._connect(reason="initial_selection")

    codes = []
    while not queue.empty():
        wire = queue.get_nowait().to_wire()
        if wire.get("code"):
            codes.append(wire["code"])
    assert "VOICE_LANGUAGE_UNSUPPORTED" not in codes, codes


@pytest.mark.asyncio
async def test_genuinely_unsupported_language_still_reported(dialogue_session):
    session = dialogue_session
    queue = session.subscribe()
    session._failed_signatures.clear()          # no pipeline was ever tried

    def _no_plan(language, *, exclude=()):
        raise UnsupportedLanguageError(f"no plan for {language}")

    session.router.select_pipeline = _no_plan

    with pytest.raises(UnsupportedLanguageError):
        await session._connect(reason="initial_selection")

    codes = []
    while not queue.empty():
        wire = queue.get_nowait().to_wire()
        if wire.get("code"):
            codes.append(wire["code"])
    assert "VOICE_LANGUAGE_UNSUPPORTED" in codes, codes
