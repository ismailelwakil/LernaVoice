"""The student's level, where the tutor reads it.

LERNA owns the real profile (Progress Profile, §30) and this service must never
build a second one. But the level changes everything the tutor says, so the
behaviour has to be built and tested *here* before the website integration is
switched on. This module therefore keeps a small local mirror of the three
fields the tutor actually needs:

    level     — beginner | intermediate | advanced   (the teaching style)
    name      — how the tutor addresses the student
    language  — the student's preferred session language

Resolution order, always:

  1. what the caller passed for this session (highest priority — the demo's
     level picker uses it);
  2. LERNA's Progress Profile, when the bridge is available (`LERNA_INTEGRATION_MODE`
     is not `disabled`) — LERNA wins as soon as it answers;
  3. the local store (a JSON file under `demo-data/`, so the demo remembers);
  4. `default_level` (intermediate).

Writes go to whichever layer is authoritative: to LERNA when it is available,
to the local store otherwise. Nothing here is secret — the store holds a level,
a name and a language code.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.learning.levels import DEFAULT_LEVEL, is_known_level, normalise_level
from app.logging_setup import get_logger

log = get_logger(__name__)

DEFAULT_STORE_PATH = "demo-data/learner_profiles.json"
PROFILE_FIELDS = ("level", "name", "language")


@dataclass
class LearnerProfile:
    student_id: str
    level: str = DEFAULT_LEVEL
    name: str | None = None
    language: str | None = None
    #: Which layer answered: "request" | "lerna" | "store" | "default".
    source: str = "default"
    note: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "student_id": self.student_id,
            "level": self.level,
            "name": self.name,
            "language": self.language,
            "source": self.source,
            "note": self.note,
        }

    def as_prompt_context(self) -> dict[str, Any]:
        return {"student_name": self.name, "student_level": self.level}


class LearnerProfileStore:
    """A tiny JSON-file profile store — deliberate, reviewable, no database."""

    def __init__(self, path: str | os.PathLike[str] | None = DEFAULT_STORE_PATH):
        self.path = Path(path) if path else None
        self._memory: dict[str, dict[str, Any]] = {}
        self._load()

    # ------------------------------------------------------------------ io
    def _load(self) -> None:
        if self.path is None or not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                self._memory = {str(k): dict(v) for k, v in data.items() if isinstance(v, dict)}
        except Exception as exc:  # a corrupt demo file must not break teaching
            log.warning("learner profile store unreadable", extra={"error_type": type(exc).__name__})

    def _save(self) -> None:
        if self.path is None:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", dir=str(self.path.parent), delete=False
            ) as handle:
                json.dump(self._memory, handle, ensure_ascii=False, indent=2, sort_keys=True)
                temp_name = handle.name
            os.replace(temp_name, self.path)
        except Exception as exc:
            log.warning("learner profile store unwritable", extra={"error_type": type(exc).__name__})

    # --------------------------------------------------------------- access
    def get(self, student_id: str) -> dict[str, Any] | None:
        found = self._memory.get(str(student_id))
        return dict(found) if found else None

    def upsert(self, student_id: str, **fields: Any) -> dict[str, Any]:
        entry = self._memory.setdefault(str(student_id), {})
        for key, value in fields.items():
            if key in PROFILE_FIELDS and value is not None:
                entry[key] = value
        self._save()
        return dict(entry)

    def all(self) -> dict[str, dict[str, Any]]:
        return {key: dict(value) for key, value in self._memory.items()}


def resolve_profile(
    student_id: str,
    *,
    stored: dict[str, Any] | None = None,
    lerna: dict[str, Any] | None = None,
    requested_level: str | None = None,
    default_level: str = DEFAULT_LEVEL,
) -> LearnerProfile:
    """Merge request > LERNA > local store > default, in that order."""
    profile = LearnerProfile(student_id=student_id, level=normalise_level(default_level, default_level))
    if stored:
        profile.level = normalise_level(stored.get("level"), profile.level)
        profile.name = stored.get("name") or profile.name
        profile.language = stored.get("language") or profile.language
        profile.source = "store"
    if lerna:
        if is_known_level(lerna.get("level")):
            profile.level = normalise_level(lerna.get("level"))
            profile.source = "lerna"
        profile.name = lerna.get("name") or profile.name
        profile.language = lerna.get("preferred_language") or profile.language
        if not lerna.get("available", True):
            profile.note = str(lerna.get("note") or "LERNA profile unavailable")
        elif profile.source != "lerna":
            profile.source = profile.source if profile.source != "default" else "lerna"
    if is_known_level(requested_level):
        profile.level = normalise_level(requested_level)
        profile.source = "request"
    return profile
