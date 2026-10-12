"""Container/deployment contract — the checks that decide whether a managed build
( Railway, Fly, any Docker host ) succeeds or fails before the app is ever started.

The bug this guards against: `python:3.12-slim` is Debian, and Debian's
`base-passwd` already ships a **`voice` group (GID 22)**. A bare
`useradd --create-home voice` therefore aborts the whole image build with
`useradd: group voice exists - if you want to add this user to that group, use -g`,
which surfaced on Railway as "Deployment failed during build process".
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = ROOT / "Dockerfile"
DOCKERIGNORE = ROOT / ".dockerignore"


@pytest.fixture(scope="module")
def dockerfile() -> str:
    assert DOCKERFILE.is_file(), "the service must ship a Dockerfile"
    return DOCKERFILE.read_text(encoding="utf-8")


def test_user_creation_is_idempotent(dockerfile: str) -> None:
    """`useradd voice` must reuse an existing `voice` group, never assume none."""
    assert "useradd" in dockerfile
    for line in dockerfile.splitlines():
        if "useradd" not in line or line.strip().startswith("#"):
            continue
        assert re.search(r"(-g|--gid)\s+voice", line), (
            "every useradd must pass -g voice: Debian base images already define a "
            f"`voice` group and a bare useradd fails the build — offending line: {line!r}"
        )
    # Guard rails for both base-image shapes (group present / absent).
    assert "getent group voice" in dockerfile
    assert "id -u voice" in dockerfile


def test_service_user_is_non_root(dockerfile: str) -> None:
    assert re.search(r"^USER\s+(?!root)\S+", dockerfile, re.M), "container must not run as root"
    assert "chown" in dockerfile


def test_port_is_injected_not_hardcoded(dockerfile: str) -> None:
    """Managed hosts (Railway) inject PORT; binding a fixed port breaks the proxy."""
    cmd = re.search(r"^CMD\s+(.*)$", dockerfile, re.M)
    assert cmd, "the image must declare a CMD"
    assert "${PORT}" in cmd.group(1), f"CMD must honour ${PORT}: {cmd.group(1)!r}"
    assert "--host 0.0.0.0" in cmd.group(1)
    assert "--workers 1" in cmd.group(1), "voice sessions are in-process; one worker"


def test_health_endpoint_is_curled(dockerfile: str) -> None:
    assert "/health" in dockerfile
    assert "curl" in dockerfile, "the healthcheck needs curl present in the image"


def test_env_files_never_enter_the_image() -> None:
    """A `.dockerignore` must keep secrets and local state out of the build context."""
    assert DOCKERIGNORE.is_file(), "ship a .dockerignore so .env/.secrets stay local"
    rules = {ln.strip() for ln in DOCKERIGNORE.read_text(encoding="utf-8").splitlines()}
    for needed in (".env", ".secrets/", "__pycache__/"):
        assert needed in rules, f".dockerignore must exclude {needed}"
    assert "!.env.example" in rules, ".env.example is a template and must keep shipping"


@pytest.mark.skipif(shutil.which("getent") is None, reason="getent unavailable")
def test_voice_group_really_exists_on_debian() -> None:
    """Documents the actual root cause: Debian defines `voice` in base-passwd.

    If the running host is Debian-based (including the CI image), the group is
    present and the idempotency above is not theoretical.
    """
    release = Path("/etc/os-release")
    if release.is_file() and "debian" not in release.read_text(encoding="utf-8").lower():
        pytest.skip("not a Debian-based host")
    proc = subprocess.run(["getent", "group", "voice"], capture_output=True, text=True)
    if proc.returncode != 0:
        pytest.skip("host image has no `voice` group")
    assert proc.stdout.startswith("voice:"), proc.stdout
