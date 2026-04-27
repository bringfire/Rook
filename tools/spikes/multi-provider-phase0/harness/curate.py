from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path
from typing import Any

from .env import CAPTURE_ROOT, REPO_ROOT
from .redact import redact_capture, redact_url


# Keys whose *string* values should be dropped as opaque blobs. Object/list values under these
# keys are preserved (and recursed into) — vendors sometimes return schema-bearing envelopes
# under `data`, e.g. `{"data": {"id": ..., "status": ...}}`.
BINARY_VALUE_KEYS = {"data", "image_base64", "b64_json", "bytes"}

SPIKE_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ARTIFACTS_ROOT = (REPO_ROOT / "docs" / "rook_docs" / "artifacts").resolve()

# Match http(s) URLs in markdown for token-query redaction. Stops at whitespace, angle
# brackets, or closing parens (covers prose, code fences, and exception messages).
URL_IN_MARKDOWN_RE = re.compile(r"https?://[^\s<>)]+")

# Cap on serialized response.body size in curated captures (in JSON characters, not
# bytes). Keeps shape evidence while dropping public-catalog dumps and other noise.
# Real probe responses are typically <2 KB; large bodies indicate either catalog dumps
# (Replicate /v1/models = 480 KB) or unintended payload bulk.
CURATED_RESPONSE_BODY_CAP = 8000


def main() -> None:
    parser = argparse.ArgumentParser(description="Curate redacted spike captures for commit.")
    parser.add_argument("--spike-date", required=True, help="Completion date, e.g. 2026-04-29")
    args = parser.parse_args()

    if not SPIKE_DATE_RE.match(args.spike_date):
        raise SystemExit(f"--spike-date must be YYYY-MM-DD, got: {args.spike_date!r}")

    dest = (ARTIFACTS_ROOT / f"{args.spike_date}-multi-provider-spike").resolve()
    # Defense in depth: refuse to write/rmtree anywhere outside the artifacts root.
    try:
        dest.relative_to(ARTIFACTS_ROOT)
    except ValueError as exc:
        raise SystemExit(
            f"Resolved destination {dest} escapes artifacts root {ARTIFACTS_ROOT}; aborting"
        ) from exc

    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)

    if not CAPTURE_ROOT.exists():
        raise SystemExit(f"Missing capture root: {CAPTURE_ROOT}")

    for probe_dir in sorted(path for path in CAPTURE_ROOT.iterdir() if path.is_dir()):
        out_dir = dest / probe_dir.name
        out_dir.mkdir(parents=True, exist_ok=True)
        for source in sorted(probe_dir.glob("*.json")):
            payload = json.loads(source.read_text(encoding="utf-8"))
            curated = _drop_binary_values(redact_capture(payload))
            curated = _cap_response_body(curated)
            (out_dir / source.name).write_text(
                json.dumps(curated, indent=2, sort_keys=True),
                encoding="utf-8",
            )
        # Copy all probe-written markdown evidence (notes.md, cancel_evidence.md, future *.md).
        # Run a URL-redaction pass so any signed-URL tokens that ended up in exception
        # strings or freeform notes do not reach the committed artifact directory.
        for md_file in sorted(probe_dir.glob("*.md")):
            text = md_file.read_text(encoding="utf-8")
            redacted = _redact_markdown(text)
            (out_dir / md_file.name).write_text(redacted, encoding="utf-8")

    print(dest)


def _cap_response_body(payload: Any) -> Any:
    """Truncate `response.body` if its serialized form exceeds `CURATED_RESPONSE_BODY_CAP`.

    Operates on the standard capture envelope shape:
        {"response": {"status_code": ..., "headers": {...}, "body": <any>}, ...}

    Replaces oversized `body` values with a small descriptor that preserves type and
    size metadata (no schema evidence is lost; the calling capture's stage,
    status_code, and headers all stay intact). Headers, request, and other top-level
    fields are not capped — only the response body, which is the noisy field in
    practice (e.g., Replicate /v1/models returning the public catalog).
    """
    if not isinstance(payload, dict):
        return payload
    response = payload.get("response")
    if not isinstance(response, dict):
        return payload
    body = response.get("body")
    if body is None:
        return payload
    serialized = json.dumps(body, sort_keys=True)
    if len(serialized) <= CURATED_RESPONSE_BODY_CAP:
        return payload
    descriptor: dict[str, Any] = {
        "<response_body_truncated_by_curation>": True,
        "original_size_chars": len(serialized),
        "cap_chars": CURATED_RESPONSE_BODY_CAP,
        "preview": serialized[:CURATED_RESPONSE_BODY_CAP],
    }
    if isinstance(body, dict):
        descriptor["original_type"] = "object"
        descriptor["top_level_keys"] = sorted(body.keys())[:20]
    elif isinstance(body, list):
        descriptor["original_type"] = "array"
        descriptor["original_length"] = len(body)
    else:
        descriptor["original_type"] = type(body).__name__
    response["body"] = descriptor
    return payload


def _redact_markdown(text: str) -> str:
    """Redact signed-URL token query params from any URL embedded in markdown.

    Probes can write exception strings into notes (e.g. an httpx error including the
    full result_url with a still-live signature). `redact_url` strips the token query
    params while keeping path/host structure intact for evidence value.
    """
    return URL_IN_MARKDOWN_RE.sub(lambda m: redact_url(m.group(0)), text)


def _drop_binary_values(value: Any) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            lowered = key.lower()
            if lowered in BINARY_VALUE_KEYS and isinstance(item, str):
                # Drop string values under binary-suspect keys (data URIs, base64 blobs, opaque tokens).
                # Object/list values are preserved by falling through to the recursive branch.
                result[key] = "<DROPPED_BINARY_OR_BASE64>"
            else:
                result[key] = _drop_binary_values(item)
        return result
    if isinstance(value, list):
        return [_drop_binary_values(item) for item in value]
    if isinstance(value, str) and _looks_like_data_uri_or_long_base64(value):
        return "<DROPPED_BINARY_OR_BASE64>"
    return value


def _looks_like_data_uri_or_long_base64(value: str) -> bool:
    if value.startswith("data:"):
        return True
    if len(value) < 300:
        return False
    alphabet = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=")
    return all(char in alphabet for char in value)


if __name__ == "__main__":
    main()
