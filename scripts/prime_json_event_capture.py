"""Bounded, evidence-preserving capture for Prime JSON event streams."""

from __future__ import annotations

import copy
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO, Callable, Iterator


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
_CUSTODY_SCHEMA = "rook.prime_event_capture_custody:v1"
_FAILURE_SCHEMA = "rook.prime_event_capture_failure:v1"
_FAILURE_PATH = PurePosixPath("operator/prime-event-capture-failure.json")
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


def _append_bounded(pending: bytearray, value: bytes) -> None:
    if len(pending) + len(value) > MAX_SOURCE_ROW_BYTES:
        raise PrimeCaptureError("stdout_row_too_large")
    pending.extend(value)


def iter_bounded_lf_rows(stream: BinaryIO) -> Iterator[bytes]:
    pending = bytearray()
    while True:
        try:
            chunk = stream.read(SOURCE_READ_CHUNK_BYTES)
        except Exception as error:
            raise PrimeCaptureError("stdout_read_failed") from error
        if type(chunk) is not bytes:
            raise PrimeCaptureError("stdout_read_failed")
        if not chunk:
            break
        cursor = 0
        while cursor < len(chunk):
            newline = chunk.find(b"\n", cursor)
            if newline < 0:
                _append_bounded(pending, chunk[cursor:])
                break
            _append_bounded(pending, chunk[cursor : newline + 1])
            yield bytes(pending)
            pending.clear()
            cursor = newline + 1
    if pending:
        raise PrimeCaptureError("stdout_missing_final_lf")


def _resolved_path(row_root: Path, relative: PurePosixPath) -> Path:
    root = Path(row_root).resolve()
    candidate = root.joinpath(*relative.parts).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise ValueError("capture_config_invalid") from error
    return candidate


def _open_exclusive(path: Path) -> BinaryIO:
    path.parent.mkdir(parents=True, exist_ok=True)
    return path.open("xb")


def _write_all(stream: BinaryIO, value: bytes, code: str) -> None:
    try:
        written = stream.write(value)
    except Exception as error:
        raise PrimeCaptureError(code) from error
    if written != len(value):
        raise PrimeCaptureError(code)


def _flush(stream: BinaryIO, code: str) -> None:
    try:
        stream.flush()
    except Exception as error:
        raise PrimeCaptureError(code) from error


def _close(stream: BinaryIO | None, code: str) -> None:
    if stream is None:
        return
    try:
        stream.close()
    except Exception as error:
        raise PrimeCaptureError(code) from error


def _best_effort_failure(
    row_root: Path,
    *,
    code: str,
    source_bytes: int,
    source_rows: int,
    retained_bytes: int,
    retained_rows: int,
    stdout_eof: bool,
) -> None:
    value = {
        "schema": _FAILURE_SCHEMA,
        "status": "incomplete",
        "code": code,
        "sourcePrefixBytes": source_bytes,
        "sourcePrefixRows": source_rows,
        "retainedPrefixBytes": retained_bytes,
        "retainedPrefixRows": retained_rows,
        "stdoutEof": stdout_eof,
    }
    try:
        stream = _open_exclusive(_resolved_path(row_root, _FAILURE_PATH))
        try:
            _write_all(stream, _canonical_line(value), "capture_custody_write_failed")
            _flush(stream, "capture_custody_write_failed")
        finally:
            stream.close()
    except Exception:
        pass


def capture_binary_stream(
    stream: BinaryIO,
    *,
    config: PrimeEventCaptureConfig,
    row_root: Path,
    publish: Callable[[dict[str, Any]], None],
) -> dict[str, Any]:
    if not isinstance(config, PrimeEventCaptureConfig):
        raise ValueError("capture_config_invalid")
    retained_stream: BinaryIO | None = None
    raw_stream: BinaryIO | None = None
    source_hash = hashlib.sha256()
    retained_hash = hashlib.sha256()
    raw_hash = hashlib.sha256()
    source_bytes = 0
    source_rows = 0
    source_max_row = 0
    retained_bytes = 0
    retained_rows = 0
    compacted = 0
    raw_fallback = 0
    raw_bytes = 0
    stdout_eof = False
    active_error: PrimeCaptureError | None = None
    try:
        try:
            retained_stream = _open_exclusive(
                _resolved_path(row_root, config.retained_path)
            )
        except Exception as error:
            raise PrimeCaptureError("compact_write_failed") from error
        if config.raw_debug_path is not None:
            try:
                raw_stream = _open_exclusive(
                    _resolved_path(row_root, config.raw_debug_path)
                )
            except Exception as error:
                raise PrimeCaptureError("raw_debug_write_failed") from error
        for raw_row in iter_bounded_lf_rows(stream):
            source_rows += 1
            source_bytes += len(raw_row)
            source_max_row = max(source_max_row, len(raw_row))
            source_hash.update(raw_row)
            result = transform_prime_row(raw_row, source_rows)
            if raw_stream is not None:
                _write_all(raw_stream, raw_row, "raw_debug_write_failed")
                raw_hash.update(raw_row)
                raw_bytes += len(raw_row)
            _write_all(retained_stream, result.retained_bytes, "compact_write_failed")
            retained_hash.update(result.retained_bytes)
            retained_bytes += len(result.retained_bytes)
            retained_rows += 1
            compacted += int(result.compacted)
            raw_fallback += int(result.raw_fallback_message_update)
            _flush(retained_stream, "compact_write_failed")
            if raw_stream is not None:
                _flush(raw_stream, "raw_debug_write_failed")
            publish(result.parsed_event)
        stdout_eof = True
        _flush(retained_stream, "compact_write_failed")
        if raw_stream is not None:
            _flush(raw_stream, "raw_debug_write_failed")
    except PrimeCaptureError as error:
        active_error = error
    except Exception as error:
        active_error = PrimeCaptureError("compact_transform_failed")
        active_error.__cause__ = error
    try:
        _close(raw_stream, "raw_debug_close_failed")
    except PrimeCaptureError as error:
        if active_error is None:
            active_error = error
    try:
        _close(retained_stream, "compact_close_failed")
    except PrimeCaptureError as error:
        if active_error is None:
            active_error = error
    if active_error is not None:
        _best_effort_failure(
            row_root,
            code=active_error.code,
            source_bytes=source_bytes,
            source_rows=source_rows,
            retained_bytes=retained_bytes,
            retained_rows=retained_rows,
            stdout_eof=(stdout_eof or active_error.code == "stdout_missing_final_lf"),
        )
        raise active_error

    custody = {
        "schema": _CUSTODY_SCHEMA,
        "status": "complete",
        "limits": {
            "maxSourceRowBytes": MAX_SOURCE_ROW_BYTES,
            "monitorQueueMaxEvents": MONITOR_QUEUE_MAX_EVENTS,
            "sourceReadChunkBytes": SOURCE_READ_CHUNK_BYTES,
        },
        "source": {
            "bytes": source_bytes,
            "maxRowBytes": source_max_row,
            "rows": source_rows,
            "sha256": source_hash.hexdigest().upper(),
            "stdoutEof": True,
        },
        "retained": {
            "bytes": retained_bytes,
            "compactedMessageUpdates": compacted,
            "path": config.retained_path.as_posix(),
            "rawFallbackMessageUpdates": raw_fallback,
            "rows": retained_rows,
            "sha256": retained_hash.hexdigest().upper(),
        },
        "rawDebug": (
            {
                "bytes": raw_bytes,
                "path": config.raw_debug_path.as_posix(),
                "sha256": raw_hash.hexdigest().upper(),
            }
            if config.raw_debug_path is not None
            else None
        ),
    }
    custody_path = _resolved_path(row_root, config.custody_path)
    custody_staging_path = custody_path.with_name(custody_path.name + ".pending")
    custody_stream: BinaryIO | None = None
    try:
        if custody_path.exists():
            raise PrimeCaptureError("capture_custody_write_failed")
        custody_stream = _open_exclusive(custody_staging_path)
        _write_all(
            custody_stream,
            _canonical_line(custody),
            "capture_custody_write_failed",
        )
        _flush(custody_stream, "capture_custody_write_failed")
        _close(custody_stream, "capture_custody_write_failed")
        custody_stream = None
        try:
            custody_staging_path.rename(custody_path)
        except OSError as error:
            raise PrimeCaptureError("capture_custody_write_failed") from error
    except PrimeCaptureError as error:
        if custody_stream is not None:
            try:
                custody_stream.close()
            except Exception:
                pass
        try:
            custody_staging_path.unlink()
        except (FileNotFoundError, OSError):
            pass
        _best_effort_failure(
            row_root,
            code=error.code,
            source_bytes=source_bytes,
            source_rows=source_rows,
            retained_bytes=retained_bytes,
            retained_rows=retained_rows,
            stdout_eof=True,
        )
        raise
    except Exception as error:
        failure = PrimeCaptureError("capture_custody_write_failed")
        failure.__cause__ = error
        if custody_stream is not None:
            try:
                custody_stream.close()
            except Exception:
                pass
        try:
            custody_staging_path.unlink()
        except (FileNotFoundError, OSError):
            pass
        _best_effort_failure(
            row_root,
            code=failure.code,
            source_bytes=source_bytes,
            source_rows=source_rows,
            retained_bytes=retained_bytes,
            retained_rows=retained_rows,
            stdout_eof=True,
        )
        raise failure
    return verify_capture_custody(config, row_root)


def _plain_int(value: Any, *, minimum: int = 0) -> bool:
    return type(value) is int and value >= minimum


def _sha256_text(value: Any) -> bool:
    return (
        type(value) is str
        and len(value) == 64
        and all(character in "0123456789ABCDEF" for character in value)
    )


def _read_single_json_object(path: Path) -> dict[str, Any]:
    try:
        value = path.read_bytes()
    except FileNotFoundError as error:
        raise PrimeCaptureError("capture_custody_missing") from error
    except OSError as error:
        raise PrimeCaptureError("capture_custody_mismatch") from error
    try:
        parsed = _strict_source_row(value)
    except PrimeCaptureError as error:
        raise PrimeCaptureError("capture_custody_mismatch") from error
    return parsed


def _valid_compact_event(value: Any, retained_row: int) -> bool:
    if type(value) is not dict:
        return False
    event = value.get("assistantMessageEvent")
    subtype = event.get("type") if type(event) is dict else None
    is_start = subtype in {"text_start", "thinking_start", "toolcall_start"}
    expected_root = {
        "schema",
        "type",
        "sourceRow",
        "sourceBytes",
        "assistantMessageEvent",
    } | ({"contentStart"} if is_start else set())
    if set(value) != expected_root:
        return False
    if (
        value["schema"] != _DELTA_SCHEMA
        or value["type"] != "assistant_stream_delta"
        or value["sourceRow"] != retained_row
        or not _plain_int(value["sourceBytes"], minimum=1)
        or value["sourceBytes"] > MAX_SOURCE_ROW_BYTES
        or subtype not in _EVENT_KEYS
        or set(event) != _EVENT_KEYS[subtype] - {"partial"}
        or not _plain_int(event.get("contentIndex"))
    ):
        return False
    if subtype.endswith("_delta") and type(event.get("delta")) is not str:
        return False
    if subtype in {"text_end", "thinking_end"} and type(event.get("content")) is not str:
        return False
    if subtype == "toolcall_end" and not _tool_block(
        event.get("toolCall"), streaming=False
    ):
        return False
    if is_start:
        block = value["contentStart"]
        if subtype == "text_start":
            return _text_block(block) and block["text"] == ""
        if subtype == "thinking_start":
            return _thinking_block(block) and block["thinking"] == ""
        return _tool_block(block, streaming=False) and block["arguments"] == {}
    return True


def _capture_file_measurements(path: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    byte_count = 0
    row_count = 0
    max_row_bytes = 0
    try:
        with path.open("rb") as stream:
            for row in iter_bounded_lf_rows(stream):
                digest.update(row)
                byte_count += len(row)
                row_count += 1
                max_row_bytes = max(max_row_bytes, len(row))
    except FileNotFoundError as error:
        raise PrimeCaptureError("capture_custody_missing") from error
    except PrimeCaptureError as error:
        raise PrimeCaptureError("capture_custody_mismatch") from error
    except OSError as error:
        raise PrimeCaptureError("capture_custody_mismatch") from error
    return {
        "bytes": byte_count,
        "maxRowBytes": max_row_bytes,
        "rows": row_count,
        "sha256": digest.hexdigest().upper(),
    }


def _retained_file_measurements(path: Path) -> dict[str, Any]:
    measurements = {
        "bytes": 0,
        "rows": 0,
        "sha256": hashlib.sha256(),
        "attributedSourceBytes": 0,
        "attributedSourceMaxRowBytes": 0,
        "compactedMessageUpdates": 0,
        "rawFallbackMessageUpdates": 0,
    }
    try:
        with path.open("rb") as stream:
            for retained_index, raw_row in enumerate(
                iter_bounded_lf_rows(stream), start=1
            ):
                measurements["sha256"].update(raw_row)
                measurements["bytes"] += len(raw_row)
                measurements["rows"] = retained_index
                value = _strict_source_row(raw_row)
                if (
                    value.get("schema") == _DELTA_SCHEMA
                    or value.get("type") == "assistant_stream_delta"
                ):
                    if not _valid_compact_event(value, retained_index):
                        raise PrimeCaptureError("capture_custody_mismatch")
                    source_bytes = value["sourceBytes"]
                    measurements["compactedMessageUpdates"] += 1
                else:
                    source_bytes = len(raw_row)
                    measurements["rawFallbackMessageUpdates"] += int(
                        value.get("type") == "message_update"
                    )
                measurements["attributedSourceBytes"] += source_bytes
                measurements["attributedSourceMaxRowBytes"] = max(
                    measurements["attributedSourceMaxRowBytes"], source_bytes
                )
    except FileNotFoundError as error:
        raise PrimeCaptureError("capture_custody_missing") from error
    except PrimeCaptureError as error:
        raise PrimeCaptureError("capture_custody_mismatch") from error
    except OSError as error:
        raise PrimeCaptureError("capture_custody_mismatch") from error
    measurements["sha256"] = measurements["sha256"].hexdigest().upper()
    return measurements


def _validate_custody_shape(
    custody: Any, config: PrimeEventCaptureConfig
) -> bool:
    if type(custody) is not dict or set(custody) != {
        "schema",
        "status",
        "limits",
        "source",
        "retained",
        "rawDebug",
    }:
        return False
    limits = custody.get("limits")
    source = custody.get("source")
    retained = custody.get("retained")
    raw_debug = custody.get("rawDebug")
    if (
        custody.get("schema") != _CUSTODY_SCHEMA
        or custody.get("status") != "complete"
        or limits
        != {
            "maxSourceRowBytes": MAX_SOURCE_ROW_BYTES,
            "monitorQueueMaxEvents": MONITOR_QUEUE_MAX_EVENTS,
            "sourceReadChunkBytes": SOURCE_READ_CHUNK_BYTES,
        }
        or type(source) is not dict
        or set(source)
        != {"bytes", "maxRowBytes", "rows", "sha256", "stdoutEof"}
        or not _plain_int(source.get("bytes"))
        or not _plain_int(source.get("maxRowBytes"))
        or source["maxRowBytes"] > MAX_SOURCE_ROW_BYTES
        or not _plain_int(source.get("rows"))
        or not _sha256_text(source.get("sha256"))
        or source.get("stdoutEof") is not True
        or type(retained) is not dict
        or set(retained)
        != {
            "bytes",
            "compactedMessageUpdates",
            "path",
            "rawFallbackMessageUpdates",
            "rows",
            "sha256",
        }
        or not _plain_int(retained.get("bytes"))
        or not _plain_int(retained.get("compactedMessageUpdates"))
        or retained.get("path") != config.retained_path.as_posix()
        or not _plain_int(retained.get("rawFallbackMessageUpdates"))
        or not _plain_int(retained.get("rows"))
        or not _sha256_text(retained.get("sha256"))
    ):
        return False
    if config.raw_debug_path is None:
        return raw_debug is None
    return (
        type(raw_debug) is dict
        and set(raw_debug) == {"bytes", "path", "sha256"}
        and _plain_int(raw_debug.get("bytes"))
        and raw_debug.get("path") == config.raw_debug_path.as_posix()
        and _sha256_text(raw_debug.get("sha256"))
    )


def verify_capture_custody(
    config: PrimeEventCaptureConfig, row_root: Path
) -> dict[str, Any]:
    if not isinstance(config, PrimeEventCaptureConfig):
        raise ValueError("capture_config_invalid")
    custody = _read_single_json_object(_resolved_path(row_root, config.custody_path))
    if not _validate_custody_shape(custody, config):
        raise PrimeCaptureError("capture_custody_mismatch")

    retained_measurements = _retained_file_measurements(
        _resolved_path(row_root, config.retained_path)
    )
    retained = custody["retained"]
    if (
        retained["bytes"] != retained_measurements["bytes"]
        or retained["sha256"] != retained_measurements["sha256"]
    ):
        raise PrimeCaptureError("capture_custody_mismatch")
    if (
        retained["rows"] != retained_measurements["rows"]
        or custody["source"]["rows"] != retained_measurements["rows"]
    ):
        raise PrimeCaptureError("capture_row_count_mismatch")

    source = custody["source"]
    if (
        source["bytes"] != retained_measurements["attributedSourceBytes"]
        or source["maxRowBytes"]
        != retained_measurements["attributedSourceMaxRowBytes"]
        or retained["compactedMessageUpdates"]
        != retained_measurements["compactedMessageUpdates"]
        or retained["rawFallbackMessageUpdates"]
        != retained_measurements["rawFallbackMessageUpdates"]
    ):
        raise PrimeCaptureError("capture_custody_mismatch")

    if config.raw_debug_path is not None:
        raw_measurements = _capture_file_measurements(
            _resolved_path(row_root, config.raw_debug_path)
        )
        raw_debug = custody["rawDebug"]
        if (
            raw_debug["bytes"] != raw_measurements["bytes"]
            or raw_debug["sha256"] != raw_measurements["sha256"]
            or source["bytes"] != raw_measurements["bytes"]
            or source["rows"] != raw_measurements["rows"]
            or source["maxRowBytes"] != raw_measurements["maxRowBytes"]
            or source["sha256"] != raw_measurements["sha256"]
        ):
            raise PrimeCaptureError("raw_debug_mismatch")
    return custody


def resolve_prime_event_path(protocol: dict[str, Any], row_root: Path) -> Path:
    if type(protocol) is not dict:
        raise ValueError("capture_config_invalid")
    if "primeEventCapture" not in protocol:
        return Path(row_root) / "operator" / "prime.jsonl"
    config = validate_capture_config(protocol["primeEventCapture"])
    if config is None:
        raise ValueError("capture_config_invalid")
    verify_capture_custody(config, row_root)
    return _resolved_path(row_root, config.retained_path)


def iter_retained_prime_events(
    protocol: dict[str, Any], row_root: Path
) -> Iterator[dict[str, Any]]:
    path = resolve_prime_event_path(protocol, row_root)
    try:
        with path.open("rb") as stream:
            for raw_row in iter_bounded_lf_rows(stream):
                yield _strict_source_row(raw_row)
    except FileNotFoundError as error:
        raise PrimeCaptureError("capture_custody_missing") from error


def _require_content_index(message: dict[str, Any], index: int) -> list[dict[str, Any]]:
    content = message.get("content")
    if type(content) is not list or index < 0 or index >= len(content):
        raise ValueError("assistant_reconstruction_incomplete")
    return content


def _apply_compact_delta(message: dict[str, Any], value: dict[str, Any]) -> None:
    event = value["assistantMessageEvent"]
    subtype = event["type"]
    index = event["contentIndex"]
    content = message.get("content")
    if type(content) is not list:
        raise ValueError("assistant_reconstruction_incomplete")
    if subtype.endswith("_start"):
        if index != len(content):
            raise ValueError("assistant_reconstruction_incomplete")
        content.append(copy.deepcopy(value["contentStart"]))
        return
    content = _require_content_index(message, index)
    block = content[index]
    if subtype == "text_delta":
        if type(block) is not dict or block.get("type") != "text":
            raise ValueError("assistant_reconstruction_incomplete")
        block["text"] += event["delta"]
    elif subtype == "thinking_delta":
        if type(block) is not dict or block.get("type") != "thinking":
            raise ValueError("assistant_reconstruction_incomplete")
        block["thinking"] += event["delta"]
    elif subtype == "toolcall_delta":
        if type(block) is not dict or block.get("type") != "toolCall":
            raise ValueError("assistant_reconstruction_incomplete")
    elif subtype == "text_end":
        if type(block) is not dict or block.get("type") != "text":
            raise ValueError("assistant_reconstruction_incomplete")
        block["text"] = event["content"]
    elif subtype == "thinking_end":
        if type(block) is not dict or block.get("type") != "thinking":
            raise ValueError("assistant_reconstruction_incomplete")
        block["thinking"] = event["content"]
    elif subtype == "toolcall_end":
        content[index] = copy.deepcopy(event["toolCall"])
    else:
        raise ValueError("assistant_reconstruction_incomplete")


def reconstruct_terminal_assistant_messages(
    protocol: dict[str, Any], row_root: Path
) -> list[dict[str, Any]]:
    current: dict[str, Any] | None = None
    terminal: list[dict[str, Any]] = []
    for value in iter_retained_prime_events(protocol, row_root):
        event_type = value.get("type")
        if event_type == "message_start":
            message = value.get("message")
            if type(message) is not dict or message.get("role") != "assistant":
                continue
            if current is not None:
                raise ValueError("assistant_reconstruction_incomplete")
            current = copy.deepcopy(message)
        elif event_type == "assistant_stream_delta":
            if current is None:
                raise ValueError("assistant_reconstruction_incomplete")
            _apply_compact_delta(current, value)
        elif event_type == "message_update":
            message = value.get("message")
            if type(message) is dict and message.get("role") == "assistant":
                if current is None:
                    raise ValueError("assistant_reconstruction_incomplete")
                current = copy.deepcopy(message)
        elif event_type == "message_end":
            message = value.get("message")
            if type(message) is not dict or message.get("role") != "assistant":
                continue
            if current is None:
                raise ValueError("assistant_reconstruction_incomplete")
            current_content = current.get("content")
            terminal_content = message.get("content")
            if (
                type(current_content) is not list
                or type(terminal_content) is not list
                or not _same_value(current_content, terminal_content)
            ):
                raise ValueError("assistant_reconstruction_mismatch")
            terminal.append(copy.deepcopy(message))
            current = None
    if current is not None:
        raise ValueError("assistant_reconstruction_incomplete")
    return terminal
