"""Parse only exact Rook public result envelopes delivered through ACP."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ParsedRookResult:
    success: bool
    data: Any


def parse_rook_envelope(content: str) -> ParsedRookResult | None:
    try:
        payload = json.loads(content)
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or "success" not in payload or "data" not in payload:
        return None
    if not isinstance(payload["success"], bool):
        return None
    return ParsedRookResult(success=payload["success"], data=payload["data"])
