"""The service serves its own demo screen at `/` (same origin as the API).

This matters operationally: behind a port proxy the client must be able to reach
the REST API *and* the WebSocket without cross-port URLs. These tests pin that
contract — page served, config injected, no hardcoded host, provider keys never
leaked into the page.
"""

from __future__ import annotations

import json
import re

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client() -> TestClient:
    from app.main import app

    with TestClient(app) as c:
        yield c


def _cfg(html: str) -> dict:
    block = re.search(r'<script id="cfg" type="application/json">(.*?)</script>', html, re.S)
    assert block, "the page must ship a config block"
    return json.loads(block.group(1))


def test_root_serves_the_voice_screen(client: TestClient):
    r = client.get("/")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert "id=\"orb\"" in r.text and "id=\"bar\"" in r.text


def test_page_is_self_contained(client: TestClient):
    """No CDN assets: the preview iframe has no network access."""
    html = client.get("/").text
    assert "http://cdn" not in html and "https://cdn" not in html
    assert "<script src=" not in html and "<link rel=\"stylesheet\"" not in html
    assert "<style>" in html and "<script>" in html


def test_page_targets_its_own_origin(client: TestClient):
    """Default config must be origin-relative, not a cross-port URL."""
    cfg = _cfg(client.get("/").text)
    assert cfg["serviceUrl"] == "", "an empty serviceUrl means 'use my own origin'"
    assert "localhost" not in client.get("/").text


def test_page_config_carries_the_ten_languages(client: TestClient):
    cfg = _cfg(client.get("/").text)
    assert set(cfg["languages"]) == {"en", "ar", "fr", "sw", "am", "ha", "so", "yo", "ig", "zu"}


def test_page_never_receives_provider_credentials(client: TestClient, monkeypatch):
    """Provider keys are server-side only (§37) — they must not reach the page."""
    monkeypatch.setenv("ELEVENLABS_API_KEY", "sk-leak-canary")
    monkeypatch.setenv("DEEPGRAM_API_KEY", "dg-leak-canary")
    monkeypatch.setenv("GEMINI_API_KEY", "gm-leak-canary")
    html = client.get("/").text
    for canary in ("sk-leak-canary", "dg-leak-canary", "gm-leak-canary"):
        assert canary not in html


def test_served_pages_do_not_trust_the_document_origin(client: TestClient):
    """In a sandboxed preview iframe `location.origin` is "null" — build URLs from
    protocol + host instead, or the socket points at "null/…" and nothing works."""
    for path in ("/", "/voice", "/console"):
        html = client.get(path).text
        assert "location.origin +" not in html, path
        assert "location.protocol + '//' + location.host" in html, path
    # ... and the voice screen offers its own top-level tab when it is framed.
    assert "its own tab" in client.get("/").text


def test_voice_screen_surfaces_setup_hints(client: TestClient):
    """Billing/credential failures must be readable on the screen, not only in the log."""
    html = client.get("/").text
    assert "e.hint" in html
    assert "banner(" in html


def test_console_is_still_available(client: TestClient):
    r = client.get("/console")
    assert r.status_code == 200
    assert "voice session" in r.text.lower() or "interrupt" in r.text.lower()


def test_topics_page_lists_the_catalogue(client: TestClient):
    """The picker is the entry point: courses, topics and every language, all
    embedded server-side so it renders even with no network in the frame."""
    r = client.get("/topics")
    assert r.status_code == 200
    block = re.search(r'<script id="catalog" type="application/json">(.*?)</script>', r.text, re.S)
    assert block, "the picker must carry the catalogue inline"
    data = json.loads(block.group(1))
    assert len(data["courses"]) >= 4
    assert data["stats"]["topics"] >= 15
    titles = [t["title"] for c in data["courses"] for t in c["topics"]]
    assert "Binary Search" in titles and "Photosynthesis" in titles
    assert [lang["code"] for lang in data["languages"]] == [
        "en", "ar", "fr", "sw", "am", "ha", "so", "yo", "ig", "zu"
    ]
    assert all(t["sections"] for c in data["courses"] for t in c["topics"]), "every topic needs steps"


def test_topics_page_flags_composed_pipelines(client: TestClient):
    data = json.loads(
        re.search(r'<script id="catalog" type="application/json">(.*?)</script>',
                  client.get("/topics").text, re.S).group(1)
    )
    by_code = {lang["code"]: lang for lang in data["languages"]}
    assert by_code["en"]["realtime_native"] is True
    assert by_code["ig"]["realtime_native"] is False
    assert "cascade" in by_code["ig"]["primary_pipeline"]["signature"]


def test_voice_screen_is_reachable_at_voice_and_root(client: TestClient):
    root, alias = client.get("/"), client.get("/voice")
    assert root.status_code == alias.status_code == 200
    assert root.text == alias.text


def test_dev_panel_shows_the_current_plan_step(client: TestClient):
    """The drawer proves the lesson is moving: it marks which step is being taught."""
    html = client.get("/").text
    assert "current_section" in html
    assert "step " in html and "'/'+plan.length" in html.replace('"', "'")


def test_voice_screen_carries_the_catalogue_for_its_picker(client: TestClient):
    cfg = _cfg(client.get("/voice").text)
    assert cfg["courses"], "the session drawer needs the catalogue"
    assert cfg["languageRouting"] and len(cfg["languageRouting"]) == 10


def test_voice_screen_switches_language_on_a_live_session(client: TestClient):
    """Picking a language mid-lesson must reach the tutor, not just the form.

    The page sends the `language` control message on the open socket when a session
    is running, and only falls back to "applies on connect" when it is not — that is
    what makes the tutor answer in the new language without a restart.
    """
    html = client.get("/").text
    assert "{type:'language'" in html.replace('"', "'")
    assert "applies when you connect" in html
    assert "language.changed" in html  # the service's acknowledgement is handled


def test_info_endpoint_still_reports_json(client: TestClient):
    r = client.get("/info")
    assert r.status_code == 200
    assert r.json()["health"] == "/health"
