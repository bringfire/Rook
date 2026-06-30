"""Public MCP tool-exposure profiles.

Single source of truth for the ``ROOK_MCP_TOOL_PROFILE`` contract. This module
is intentionally pure: it MUST NOT import ``server.py`` (one-way dependency --
``server.py`` consumes this module, never the reverse).
"""

from __future__ import annotations

from enum import Enum
from typing import Mapping

ENV_VAR = "ROOK_MCP_TOOL_PROFILE"


class Profile(str, Enum):
    FULL = "full"
    LEAN = "lean"
    READONLY = "readonly"


class InvalidProfileError(ValueError):
    """Raised when ROOK_MCP_TOOL_PROFILE is set to an unrecognized value."""


def resolve_profile(env: Mapping[str, str]) -> Profile:
    """Resolve the active profile from an environment mapping.

    Absent or empty/whitespace => FULL (backward-compatible default).
    Any other unrecognized value => InvalidProfileError (never a silent fallback).
    """
    raw = env.get(ENV_VAR)
    if raw is None:
        return Profile.FULL
    normalized = raw.strip().lower()
    if normalized == "":
        return Profile.FULL
    try:
        return Profile(normalized)
    except ValueError:
        raise InvalidProfileError(
            f"Invalid {ENV_VAR}={raw!r}. Expected one of: full, lean, readonly."
        ) from None
