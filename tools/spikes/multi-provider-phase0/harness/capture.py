from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from .env import CAPTURE_ROOT, ensure_runtime_dirs
from .redact import redact_capture


@dataclass(frozen=True)
class CaptureContext:
    probe_id: str
    provider: str
    model_id: str
    catalog_url: str
    price_observed: str


def write_redacted(
    stage: str,
    request: dict[str, Any],
    response: httpx.Response | dict[str, Any],
    ctx: CaptureContext,
) -> Path:
    ensure_runtime_dirs()
    probe_dir = CAPTURE_ROOT / ctx.probe_id
    probe_dir.mkdir(parents=True, exist_ok=True)

    payload: dict[str, Any] = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "context": asdict(ctx),
        "stage": stage,
        "request": request,
        "response": _response_payload(response),
    }
    redacted = redact_capture(payload)
    path = probe_dir / f"{stage}.json"
    path.write_text(json.dumps(redacted, indent=2, sort_keys=True), encoding="utf-8")
    return path


def write_manifest(ctx: CaptureContext, outcome: str, notes: dict[str, Any]) -> Path:
    ensure_runtime_dirs()
    probe_dir = CAPTURE_ROOT / ctx.probe_id
    probe_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "context": asdict(ctx),
        "outcome": outcome,
        "notes": notes,
    }
    path = probe_dir / "manifest.json"
    path.write_text(json.dumps(redact_capture(payload), indent=2, sort_keys=True), encoding="utf-8")
    return path


def append_notes(probe_id: str, text: str) -> Path:
    ensure_runtime_dirs()
    probe_dir = CAPTURE_ROOT / probe_id
    probe_dir.mkdir(parents=True, exist_ok=True)
    path = probe_dir / "notes.md"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(text.rstrip() + "\n")
    return path


_TEXTUAL_CONTENT_HINTS = ("json", "text", "xml", "javascript", "yaml", "x-www-form-urlencoded")
_TEXT_BODY_CAP = 200_000  # truncate text bodies past this many chars to avoid huge raw captures


def is_textual_content_type(content_type: str) -> bool:
    if not content_type:
        return True  # unknown → assume textual; redaction layer handles oddities
    return any(hint in content_type for hint in _TEXTUAL_CONTENT_HINTS)


def _response_payload(response: httpx.Response | dict[str, Any]) -> dict[str, Any]:
    if isinstance(response, dict):
        return response
    headers = dict(response.headers)
    content_type = response.headers.get("content-type", "").lower()
    body: Any
    if is_textual_content_type(content_type):
        try:
            body = response.json()
        except ValueError:
            text = response.text
            if len(text) > _TEXT_BODY_CAP:
                body = {
                    "<text_body_truncated>": True,
                    "content_type": content_type,
                    "captured_chars": _TEXT_BODY_CAP,
                    "total_chars": len(text),
                    "preview": text[:_TEXT_BODY_CAP],
                }
            else:
                body = text
    else:
        body = {
            "<binary_body_dropped>": True,
            "content_type": content_type,
            "content_length": response.headers.get("content-length"),
        }
    return {
        "status_code": response.status_code,
        "headers": headers,
        "body": body,
    }
