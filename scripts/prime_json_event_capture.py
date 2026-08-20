"""Bounded, evidence-preserving capture for Prime JSON event streams."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path, PurePosixPath
from typing import Any


MAX_SOURCE_ROW_BYTES = 67_108_864
SOURCE_READ_CHUNK_BYTES = 65_536
MONITOR_QUEUE_MAX_EVENTS = 1

FAILURE_CODES = frozenset(
    {
        "stdout_read_failed",
        "stdout_invalid_utf8",
        "stdout_missing_final_lf",
        "stdout_row_too_large",
        "stdout_json_invalid",
        "stdout_json_object_required",
        "stdout_json_duplicate_key",
        "compact_transform_failed",
        "compact_write_failed",
        "compact_close_failed",
        "raw_debug_write_failed",
        "raw_debug_close_failed",
        "capture_custody_write_failed",
        "capture_custody_missing",
        "capture_custody_mismatch",
        "capture_row_count_mismatch",
        "raw_debug_mismatch",
    }
)

_CONFIG_SCHEMA = "rook.prime_event_capture_config:v1"
_DELTA_SCHEMA = "rook.prime_assistant_stream_delta:v1"
_CONFIG_KEYS = {
    "schema",
    "mode",
    "retainedPath",
    "custodyPath",
    "rawDebugPath",
}
_EVENT_KEYS = {
    "text_start": {"type", "contentIndex", "partial"},
    "text_delta": {"type", "contentIndex", "delta", "partial"},
    "text_end": {"type", "contentIndex", "content", "partial"},
    "thinking_start": {"type", "contentIndex", "partial"},
    "thinking_delta": {"type", "contentIndex", "delta", "partial"},
    "thinking_end": {"type", "contentIndex", "content", "partial"},
    "toolcall_start": {"type", "contentIndex", "partial"},
    "toolcall_delta": {"type", "contentIndex", "delta", "partial"},
    "toolcall_end": {"type", "contentIndex", "toolCall", "partial"},
}


class PrimeCaptureError(RuntimeError):
    """Closed capture failure with a stable machine-readable code."""

    def __init__(self, code: str):
        if code not in FAILURE_CODES:
            raise ValueError("capture_failure_code_invalid")
        self.code = code
        super().__init__(code)


class _DuplicateKeyError(ValueError):
    pass


@dataclass(frozen=True)
class PrimeEventCaptureConfig:
    mode: str
    retained_path: PurePosixPath
    custody_path: PurePosixPath
    raw_debug_path: PurePosixPath | None


@dataclass(frozen=True)
class CapturedPrimeRow:
    source_row: int
    source_bytes: int
    parsed_event: dict[str, Any]
    retained_bytes: bytes
    compacted: bool
    raw_fallback_message_update: bool


def _operator_path(value: Any) -> PurePosixPath | None:
    if type(value) is not str or not value or "\\" in value:
        return None
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or path.as_posix() != value
        or len(path.parts) < 2
        or path.parts[0] != "operator"
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        return None
    return path


def validate_capture_config(value: Any) -> PrimeEventCaptureConfig | None:
    if value is None:
        return None
    if type(value) is not dict or set(value) != _CONFIG_KEYS:
        raise ValueError("capture_config_invalid")
    if value["schema"] != _CONFIG_SCHEMA or value["mode"] not in {
        "compact",
        "compact_with_raw_debug",
    }:
        raise ValueError("capture_config_invalid")
    retained = _operator_path(value["retainedPath"])
    custody = _operator_path(value["custodyPath"])
    raw_value = value["rawDebugPath"]
    raw = _operator_path(raw_value) if raw_value is not None else None
    if retained is None or custody is None:
        raise ValueError("capture_config_invalid")
    if value["mode"] == "compact" and raw_value is not None:
        raise ValueError("capture_config_invalid")
    if value["mode"] == "compact_with_raw_debug" and raw is None:
        raise ValueError("capture_config_invalid")
    paths = [retained, custody] + ([raw] if raw is not None else [])
    aliases = [path.as_posix().casefold() for path in paths]
    if len(set(aliases)) != len(aliases):
        raise ValueError("capture_config_invalid")
    return PrimeEventCaptureConfig(value["mode"], retained, custody, raw)


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKeyError(key)
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(value)


def _contains_nonfinite(value: Any) -> bool:
    if type(value) is float:
        return not math.isfinite(value)
    if type(value) is list:
        return any(_contains_nonfinite(item) for item in value)
    if type(value) is dict:
        return any(_contains_nonfinite(item) for item in value.values())
    return False


def _strict_source_row(raw_row: bytes) -> dict[str, Any]:
    if not raw_row.endswith(b"\n"):
        raise PrimeCaptureError("stdout_missing_final_lf")
    if len(raw_row) > MAX_SOURCE_ROW_BYTES:
        raise PrimeCaptureError("stdout_row_too_large")
    try:
        text = raw_row[:-1].decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise PrimeCaptureError("stdout_invalid_utf8") from error
    try:
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_constant,
        )
    except _DuplicateKeyError as error:
        raise PrimeCaptureError("stdout_json_duplicate_key") from error
    except (ValueError, json.JSONDecodeError) as error:
        raise PrimeCaptureError("stdout_json_invalid") from error
    if type(value) is not dict:
        raise PrimeCaptureError("stdout_json_object_required")
    if _contains_nonfinite(value):
        raise PrimeCaptureError("stdout_json_invalid")
    return value


def _same_value(left: Any, right: Any) -> bool:
    if type(left) is not type(right):
        return False
    if type(left) is dict:
        return set(left) == set(right) and all(
            _same_value(left[key], right[key]) for key in left
        )
    if type(left) is list:
        return len(left) == len(right) and all(
            _same_value(a, b) for a, b in zip(left, right)
        )
    return left == right


def _optional_string(value: dict[str, Any], key: str) -> bool:
    return key not in value or type(value[key]) is str


def _text_block(value: Any) -> bool:
    if type(value) is not dict or not {"type", "text"} <= set(value):
        return False
    if set(value) - {"type", "text", "textSignature"}:
        return False
    return (
        value["type"] == "text"
        and type(value["text"]) is str
        and _optional_string(value, "textSignature")
    )


def _thinking_block(value: Any) -> bool:
    if type(value) is not dict or not {"type", "thinking"} <= set(value):
        return False
    if set(value) - {"type", "thinking", "thinkingSignature", "redacted"}:
        return False
    return (
        value["type"] == "thinking"
        and type(value["thinking"]) is str
        and _optional_string(value, "thinkingSignature")
        and ("redacted" not in value or type(value["redacted"]) is bool)
    )


def _tool_block(value: Any, *, streaming: bool) -> bool:
    if type(value) is not dict:
        return False
    optional = {"thoughtSignature"}
    if streaming:
        optional |= {"partialArgs", "streamIndex"}
    if set(value) != {"type", "id", "name", "arguments"} | (
        set(value) & optional
    ):
        return False
    if (
        value["type"] != "toolCall"
        or type(value["id"]) is not str
        or not value["id"]
        or type(value["name"]) is not str
        or not value["name"]
        or type(value["arguments"]) is not dict
        or not _optional_string(value, "thoughtSignature")
    ):
        return False
    if "partialArgs" in value and type(value["partialArgs"]) is not str:
        return False
    if "streamIndex" in value and (
        type(value["streamIndex"]) is not int or value["streamIndex"] < 0
    ):
        return False
    return True


def _content_start(subtype: str, block: dict[str, Any]) -> dict[str, Any] | None:
    if subtype == "text_start":
        result = {"type": "text", "text": ""}
        if "textSignature" in block:
            result["textSignature"] = block["textSignature"]
        return result
    if subtype == "thinking_start":
        result = {"type": "thinking", "thinking": ""}
        for key in ("thinkingSignature", "redacted"):
            if key in block:
                result[key] = block[key]
        return result
    if subtype == "toolcall_start":
        result = {
            "type": "toolCall",
            "id": block["id"],
            "name": block["name"],
            "arguments": {},
        }
        if "thoughtSignature" in block:
            result["thoughtSignature"] = block["thoughtSignature"]
        return result
    return None


def _compact_message_update(value: dict[str, Any], source_row: int, source_bytes: int) -> bytes | None:
    if set(value) != {"type", "message", "assistantMessageEvent"}:
        return None
    if value.get("type") != "message_update":
        return None
    message = value.get("message")
    event = value.get("assistantMessageEvent")
    if type(message) is not dict or type(event) is not dict:
        return None
    if message.get("role") != "assistant" or "partial" not in event:
        return None
    if not _same_value(message, event["partial"]):
        return None
    subtype = event.get("type")
    expected_keys = _EVENT_KEYS.get(subtype)
    if expected_keys is None or set(event) != expected_keys:
        return None
    index = event.get("contentIndex")
    content = message.get("content")
    if (
        type(index) is not int
        or index < 0
        or type(content) is not list
        or index >= len(content)
    ):
        return None
    block = content[index]
    if subtype.startswith("text_"):
        valid_block = _text_block(block)
    elif subtype.startswith("thinking_"):
        valid_block = _thinking_block(block)
    elif subtype in {"toolcall_start", "toolcall_delta"}:
        valid_block = _tool_block(block, streaming=True)
    else:
        valid_block = _tool_block(block, streaming=False)
    if not valid_block:
        return None
    if subtype.endswith("_delta") and type(event.get("delta")) is not str:
        return None
    if subtype in {"text_end", "thinking_end"}:
        if type(event.get("content")) is not str:
            return None
        block_value = block["text"] if subtype == "text_end" else block["thinking"]
        if event["content"] != block_value:
            return None
    if subtype == "toolcall_end":
        if not _tool_block(event.get("toolCall"), streaming=False):
            return None
        if not _same_value(event["toolCall"], block):
            return None
    compact_event = {key: event[key] for key in event if key != "partial"}
    retained: dict[str, Any] = {
        "schema": _DELTA_SCHEMA,
        "type": "assistant_stream_delta",
        "sourceRow": source_row,
        "sourceBytes": source_bytes,
        "assistantMessageEvent": compact_event,
    }
    start = _content_start(subtype, block)
    if start is not None:
        retained["contentStart"] = start
    return _canonical_line(retained)


def _canonical_line(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )


def transform_prime_row(raw_row: bytes, source_row: int) -> CapturedPrimeRow:
    if type(source_row) is not int or source_row < 1:
        raise PrimeCaptureError("compact_transform_failed")
    parsed = _strict_source_row(raw_row)
    compact = _compact_message_update(parsed, source_row, len(raw_row))
    return CapturedPrimeRow(
        source_row=source_row,
        source_bytes=len(raw_row),
        parsed_event=parsed,
        retained_bytes=compact if compact is not None else raw_row,
        compacted=compact is not None,
        raw_fallback_message_update=(
            parsed.get("type") == "message_update" and compact is None
        ),
    )
