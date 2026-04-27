from __future__ import annotations

import copy
import re
from collections.abc import Mapping
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


REDACTED = "<REDACTED>"

AUTH_HEADER_PATTERNS = (
    "authorization",
    "x-api-key",
    "api-key",
    "x-goog-api-key",
    "fal-key",
)

TOKEN_QUERY_RE = re.compile(
    r"(?i)(token|signature|x-amz-[^=&\s]+|x-goog-signature|access_key|expires|credential)"
)

BASE64_LIKE_RE = re.compile(r"^[A-Za-z0-9+/]{160,}={0,2}$")

ORG_KEYS = {
    "user",
    "user_id",
    "userid",
    "owner",
    "owner_id",
    "org",
    "org_id",
    "organization",
    "organization_id",
    "project",
    "project_id",
    "account",
    "account_id",
}


def redact_value(value: object) -> object:
    if isinstance(value, Mapping):
        return redact_mapping(value)
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, str):
        if value.startswith("data:"):
            return "<REDACTED_DATA_URI>"
        if _looks_like_url(value):
            return redact_url(value)
        if BASE64_LIKE_RE.match(value):
            return "<REDACTED_BASE64>"
        return value
    return value


def redact_mapping(mapping: Mapping[str, object]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in mapping.items():
        normalized = key.lower().replace("-", "_")
        header_normalized = key.lower()
        if any(pattern in header_normalized for pattern in AUTH_HEADER_PATTERNS):
            result[key] = REDACTED
        elif normalized in ORG_KEYS:
            result[key] = REDACTED
        else:
            result[key] = redact_value(value)
    return result


def redact_url(url: str) -> str:
    parts = urlsplit(url)
    if not parts.scheme or not parts.netloc:
        return url

    pairs = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if TOKEN_QUERY_RE.search(key):
            pairs.append((key, REDACTED))
        else:
            pairs.append((key, value))
    query = urlencode(pairs)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))


def redact_capture(payload: Mapping[str, object]) -> dict[str, object]:
    return copy.deepcopy(redact_mapping(payload))


def _looks_like_url(value: str) -> bool:
    return value.startswith("http://") or value.startswith("https://")
