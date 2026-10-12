"""Patch: use the service-account file from settings, not only from the process env.

Real failure caught by the live probe: `.env` had GOOGLE_APPLICATION_CREDENTIALS, but
pydantic-settings reads `.env` into *Settings*, not into os.environ — so the Google SDK
fell back to Application Default Credentials, found nothing, and every provider failed
with DefaultCredentialsError instead of reaching the (billing) error that actually
mattered.
"""

# ---------------------------------------------------------------- config field
P = "app/config.py"
s = open(P).read()
if "google_application_credentials" not in s:
    s = s.replace(
        "    google_cloud_project: str | None = None",
        '''    google_cloud_project: str | None = None
    #: Path to a service-account JSON (Vertex). Read here *and* handed to the SDK
    #: explicitly — `.env` does not populate os.environ for third-party libraries.
    google_application_credentials: str | None = None''',
        1,
    )
open(P, "w").write(s)

# ---------------------------------------------------------------- client construction
P = "app/providers/gemini/client.py"
s = open(P).read()

old = """    if s.google_genai_use_vertexai:
        if not s.google_cloud_project:
            raise ProviderAuthError(
                "GOOGLE_GENAI_USE_VERTEXAI=true requires GOOGLE_CLOUD_PROJECT", provider="gemini"
            )
        return genai.Client(
            vertexai=True,
            project=s.google_cloud_project,
            location=s.google_cloud_location,
        )"""
new = """    if s.google_genai_use_vertexai:
        if not s.google_cloud_project:
            raise ProviderAuthError(
                "GOOGLE_GENAI_USE_VERTEXAI=true requires GOOGLE_CLOUD_PROJECT", provider="gemini"
            )
        credentials = _vertex_credentials(s)
        kwargs: dict[str, Any] = {
            "vertexai": True,
            "project": s.google_cloud_project,
            "location": s.google_cloud_location,
        }
        if credentials is not None:
            kwargs["credentials"] = credentials
        return genai.Client(**kwargs)"""
assert old in s
s = s.replace(old, new)

anchor = "def genai_types() -> Any:"
assert anchor in s
s = s.replace(
    anchor,
    '''def _vertex_credentials(settings: Settings) -> Any:
    """Service-account credentials from configuration, or None to use ADC.

    `GOOGLE_APPLICATION_CREDENTIALS` in `.env` is visible to *our* settings but not to the
    Google SDK (which reads the process environment) — and a missing credential then
    surfaces as a confusing "default credentials were not found" instead of the real
    problem. Loading the file here makes the configured path authoritative.
    """
    path = settings.google_application_credentials or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not path:
        return None
    if not Path(path).exists():
        raise ProviderAuthError(
            f"GOOGLE_APPLICATION_CREDENTIALS points at a file that does not exist: {path}",
            provider="gemini",
        )
    try:
        from google.oauth2 import service_account  # type: ignore
    except ImportError:  # pragma: no cover - google-auth ships with google-genai
        return None
    try:
        return service_account.Credentials.from_service_account_file(
            path, scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
    except Exception as exc:  # noqa: BLE001 - re-raised as a classified provider error
        raise ProviderAuthError(
            f"the service-account file could not be loaded: {type(exc).__name__}", provider="gemini"
        ) from exc


''' + anchor,
    1,
)

if "\nimport os\n" not in s:
    s = s.replace("from __future__ import annotations\n\nfrom typing import Any",
                  "from __future__ import annotations\n\nimport os\nfrom pathlib import Path\nfrom typing import Any", 1)
open(P, "w").write(s)

# ---------------------------------------------------------------- hint for ADC
P = "app/providers/hints.py"
s = open(P).read()
s = s.replace(
    '''    (
        r"quota|resource_exhausted|exceeded your current quota|429",''',
    '''    (
        r"default credentials were not found|defaultcredentials|application default credentials",
        "No Google credentials were found. Point GOOGLE_APPLICATION_CREDENTIALS at the "
        "service-account JSON (or set GEMINI_API_KEY with GOOGLE_GENAI_USE_VERTEXAI=false).",
    ),
    (
        r"quota|resource_exhausted|exceeded your current quota|429",''',
)
open(P, "w").write(s)

import subprocess
print(subprocess.run(["python3", "-c", """
from app.config import Settings
from app.providers.gemini.client import _vertex_credentials
s = Settings()
print('credentials path from .env:', bool(s.google_application_credentials))
print('loaded object      :', type(_vertex_credentials(s)).__name__)
"""], capture_output=True, text=True).stdout)
