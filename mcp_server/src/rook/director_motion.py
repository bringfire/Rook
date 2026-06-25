"""Pure object-motion compilation for RookVisionDirector PR4.

No I/O, no native calls, no MCP. Compiles per-object keyframe tracks of
relative TRS deltas into per-frame nested-4x4 transform matrices consumed by
native /director/replay. See
docs/superpowers/specs/2026-06-24-rookvisiondirector-animation-compiler-design.md
"""
from __future__ import annotations

import math

EASING_NAMES = frozenset({"linear", "ease_in", "ease_out", "ease_in_out"})


def apply_easing(name: str, u: float) -> float:
    """Map segment progress u in [0,1] -> eased progress. Endpoints fixed."""
    if u <= 0.0:
        return 0.0
    if u >= 1.0:
        return 1.0
    if name == "linear":
        return u
    if name == "ease_in":
        return u * u
    if name == "ease_out":
        return 1.0 - (1.0 - u) * (1.0 - u)
    if name == "ease_in_out":
        # smoothstep
        return u * u * (3.0 - 2.0 * u)
    # Unknown names are rejected upstream (Task 2); be defensive.
    raise MotionError("invalid_keyframe", f"unknown easing: {name}")


class MotionError(ValueError):
    """Keyframe/motion-domain validation failure carrying a stable error code."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
