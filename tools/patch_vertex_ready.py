"""Make the repo ready for the Vertex service-account drop, and let the verifier
validate the credential file without printing it."""

# ---------------------------------------------------------------- .gitignore
P = ".gitignore"
s = open(P).read()
if ".secrets/" not in s:
    s = s.replace(".env\n.env.*\n!.env.example\n", ".env\n.env.*\n!.env.example\n.secrets/\n*service-account*.json\n")
open(P, "w").write(s)

# ---------------------------------------------------------------- verify script
P = "tools/verify_live_voice.py"
s = open(P).read()

s = s.replace(
    '''def load_dotenv() -> None:''',
    '''def use_service_account() -> dict:
    """Validate GOOGLE_APPLICATION_CREDENTIALS and fill GOOGLE_CLOUD_PROJECT from it.

    Reports only non-secret facts (project id, client-email domain, key presence) so a
    credential can be diagnosed in a shared terminal without leaking it.
    """
    import json

    info: dict = {"path": os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", ""), "status": "not set"}
    if not info["path"]:
        return info
    path = Path(info["path"])
    if not path.exists():
        info["status"] = f"missing file: {path}"
        return info
    try:
        data = json.loads(path.read_text())
    except Exception as exc:  # noqa: BLE001 - diagnosis only
        info["status"] = f"not valid JSON: {type(exc).__name__}"
        return info

    kind = data.get("type")
    info["type"] = kind
    info["project_id"] = data.get("project_id")
    email = data.get("client_email") or ""
    info["client_email_domain"] = email.split("@")[-1] if "@" in email else ""
    info["has_private_key"] = bool(data.get("private_key"))
    if kind != "service_account" or not info["has_private_key"]:
        info["status"] = "not a service-account key (expected type=service_account with private_key)"
        return info
    info["status"] = "ok"
    # Convenience: a blank GOOGLE_CLOUD_PROJECT is filled from the key itself.
    if not os.environ.get("GOOGLE_CLOUD_PROJECT") and info.get("project_id"):
        os.environ["GOOGLE_CLOUD_PROJECT"] = str(info["project_id"])
        info["project_filled_from_key"] = True
    return info


def load_dotenv() -> None:''',
)

s = s.replace(
    '''async def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser''',
    '''async def main() -> int:
    load_dotenv()
    cred = use_service_account()
    parser = argparse.ArgumentParser''',
)

s = s.replace(
    '''    settings = Settings()
    print(f"provider mode : {settings.voice_provider_mode}   mock: {settings.voice_enable_mock_providers}")''',
    '''    settings = Settings()
    if cred["status"] != "not set":
        print(f"credential    : {cred['status']}"
              + (f" · type={cred.get('type')}" if cred.get("type") else "")
              + (f" · project={cred.get('project_id')}" if cred.get("project_id") else "")
              + (f" · domain=@{cred['client_email_domain']}" if cred.get("client_email_domain") else "")
              + ("  (GOOGLE_CLOUD_PROJECT filled from the key)" if cred.get("project_filled_from_key") else ""))
    print(f"provider mode : {settings.voice_provider_mode}   mock: {settings.voice_enable_mock_providers}")''',
)

s = s.replace(
    '''        print("\\nNo Gemini credential found. Put one of these in .env and re-run:")''',
    '''        if cred["status"] not in ("not set", "ok"):
            print(f"\\nThe credential file is not usable: {cred['status']}")
            print(f"  path: {cred['path']}")
            print("  Fix the file (Vertex service-account JSON) or the path, then re-run.")
            return 2
        print("\\nNo Gemini credential found. Put one of these in .env and re-run:")''',
)
open(P, "w").write(s)

# ---------------------------------------------------------------- .env for Vertex
P = ".env"
from pathlib import Path

P = Path(P)
if not P.exists():
    P.write_text(
        """# Local development environment (git-ignored). No secret is written here by hand
# except by you: the Gemini credential stays in a file referenced by path.

# --- Gemini via Vertex AI / Agent Platform (primary, native audio) ---------- #
GOOGLE_GENAI_USE_VERTEXAI=true
# Filled automatically from the service-account JSON if left blank.
GOOGLE_CLOUD_PROJECT=
GOOGLE_CLOUD_LOCATION=us-central1
GOOGLE_APPLICATION_CREDENTIALS=/home/user/lerna/voice-ai/.secrets/vertex-service-account.json
GEMINI_VERTEX_LIVE_MODEL=gemini-3.8-live
GEMINI_VERTEX_TEXT_MODEL=gemini-3.8-flash
GEMINI_VOICE_NAME=Kore
GEMINI_AFFECTIVE_DIALOG=true
GEMINI_PROACTIVE_AUDIO=false

# --- Backups (add when you have them; failover stays mock-tested until then) #
ELEVENLABS_API_KEY=
DEEPGRAM_API_KEY=

# --- Service ---------------------------------------------------------------- #
VOICE_PROVIDER_MODE=auto
VOICE_SERVICE_API_KEY=
LERNA_INTEGRATION_MODE=disabled
# Live vendors: leave the mock switch OFF. Set VERTEX_DRY_RUN=1 to keep the demo on
# the mock while this file is in place (used by tools/run_live_demo.sh).
# VOICE_ENABLE_MOCK_PROVIDERS=true
""",
        encoding="utf-8",
    )

# ---------------------------------------------------------------- live run script
Path("tools/run_live_demo.sh").write_text(
    """#!/usr/bin/env bash
# Start the service on the REAL vendors (Vertex Gemini Live). Requires .env.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  echo "no .env — copy .env.example and fill it in"; exit 2
fi
if grep -q '^GOOGLE_APPLICATION_CREDENTIALS=' .env; then
  cred=$(grep '^GOOGLE_APPLICATION_CREDENTIALS=' .env | cut -d= -f2-)
  if [ -n "$cred" ] && [ ! -f "$cred" ]; then
    echo "credential file not found: $cred"
    echo "drop the service-account JSON there, or fix the path in .env"; exit 2
  fi
fi

# No VOICE_ENABLE_MOCK_PROVIDERS here on purpose: that switch is what makes the service
# serve synthetic audio instead of the vendor's own voice.
exec python3 -m uvicorn app.main:app --host 0.0.0.0 --port "${VOICE_API_PORT:-3000}"
""",
    encoding="utf-8",
)
print("vertex-ready: .gitignore, .env, tools/verify_live_voice.py, tools/run_live_demo.sh")
