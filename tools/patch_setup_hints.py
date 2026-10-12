"""Patch: setup failures explain themselves in the UI (billing, auth, model, quota).

The first live bring-up failed with "This API method requires billing to be enabled" —
correct, but a student-facing screen should say what to do about it, not surface a raw
Google error string.
"""

# ---------------------------------------------------------------- hints module
from pathlib import Path

Path("app/providers/hints.py").write_text(
    '''"""Actionable hints for the setup failures a first live deployment hits.

Vendor errors are accurate but opaque to whoever is running the demo ("1008 None. This
API method requires billing…"). The service maps the ones that are actually a
*configuration* problem onto a short explanation with the link that fixes it, and those
travel to the client with the error event — so the screen can say what to do.
"""

from __future__ import annotations

import re

#: (pattern, hint) — first match wins.
_HINTS: tuple[tuple[str, str], ...] = (
    (
        r"billing|billing_disabled",
        "Gemini billing is not enabled for this GCP project. Enable it at "
        "console.developers.google.com/billing/enable?project={project} (or use a Gemini "
        "Developer API key, which has a free tier).",
    ),
    (
        r"api key not valid|api_key_invalid|invalid api key|unauthenticated|permission denied",
        "The vendor rejected the credential. Check GEMINI_API_KEY (Developer API) or the "
        "service-account file and its IAM roles (Vertex: 'Vertex AI User').",
    ),
    (
        r"quota|resource_exhausted|exceeded your current quota|429",
        "The vendor quota for this model is exhausted. Wait for the quota window to reset, "
        "or switch model / enable billing for a higher limit.",
    ),
    (
        r"not found for api version|unsupported|does not support|model.*not.*found|404.*model",
        "This model is not available for the configured project or region. Check "
        "GEMINI_VERTEX_LIVE_MODEL / GEMINI_LIVE_MODEL and GOOGLE_CLOUD_LOCATION.",
    ),
    (
        r"service_disabled|has not been used in project|api is not enabled",
        "The Vertex AI API is not enabled on the project. Enable it at "
        "console.cloud.google.com/apis/library/aiplatform.googleapis.com?project={project}.",
    ),
    (
        r"deadline exceeded|timed out|timeout",
        "The vendor did not answer in time. Retry, or raise VOICE_PROVIDER_TIMEOUT.",
    ),
)


def setup_hint(message: str, *, project: str | None = None) -> str | None:
    """A short, human explanation for a vendor setup failure, or None."""
    low = (message or "").lower()
    project = project or "<your-project>"
    for pattern, hint in _HINTS:
        if re.search(pattern, low):
            return hint.replace("{project}", project)
    return None
''',
    encoding="utf-8",
)

# ---------------------------------------------------------------- session manager
P = "app/voice/session_manager.py"
s = open(P).read()

anchor = "def _reason_for(error: Exception | None) -> str:"
assert anchor in s
s = s.replace(
    anchor,
    '''def _hint_for(error: Exception | None) -> str | None:
    """A configuration hint for the client, when the failure is 'you set this up wrong'."""
    if error is None:
        return None
    from app.config import get_settings
    from app.providers.hints import setup_hint

    return setup_hint(str(error), project=get_settings().google_cloud_project)


''' + anchor,
    1,
)

old = """                error_event(
                    code,
                    message=f"{provider} failed: {exc}","""
if old not in s:
    # locate the actual error emission inside _on_provider_error
    import re as _re

    m = _re.search(r"error_event\(\s*code,\s*message=[^,]*,[^)]*\)", s)
    print("error_event call sites:", [mm.group(0)[:120] for mm in _re.finditer(r"error_event\([^)]*\)", s, _re.S)][:4])
open(P, "w").write(s)
print("hints module + _hint_for added")
