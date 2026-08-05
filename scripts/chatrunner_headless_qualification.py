#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
from typing import Any, BinaryIO, Callable, Mapping
from urllib.parse import urlsplit

_ROW_MAX_BYTES = 256 * 1024
_TRACE_MAX_BYTES = 4 * 1024 * 1024
_ROW_KEYS = frozenset({"model", "api_base", "intent", "skill_path", "rhino_target"})
_TARGET_KEYS = frozenset({"port", "process_id", "document_serial_number"})
_TRACE_KINDS = frozenset(
    {
        "run_started",
        "chat_event",
        "qualification_refusal",
        "stream_exception",
        "run_cancelled",
        "target_drift",
        "snapshot_request",
        "snapshot_result",
        "run_finished",
    }
)


@dataclass(frozen=True)
class _RhinoTarget:
    port: int
    process_id: int
    document_serial_number: int


@dataclass(frozen=True)
class _QualificationRow:
    source_path: Path
    source_sha256: str
    model: str
    api_base: str
    intent: str
    skill_path: Path
    skill_sha256: str
    skill_text: str
    target: _RhinoTarget


class _TraceWriteFailure(RuntimeError):
    def __init__(self, reason: str, path: Path | None) -> None:
        super().__init__("trace_write_failed")
        self.reason = reason
        self.path = path


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_json_key")
        result[key] = value
    return result


def _reject_json_constant(_: str) -> None:
    raise ValueError("invalid_json_constant")


def _read_strict_utf8(path: Path, invalid_reason: str) -> tuple[bytes, str]:
    try:
        raw = path.read_bytes()
    except Exception:
        raise ValueError(invalid_reason) from None
    try:
        return raw, raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        raise ValueError(invalid_reason) from None


def _require_nonblank_string(value: Any, reason: str) -> str:
    if type(value) is not str or not value.strip():
        raise ValueError(reason)
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeEncodeError:
        raise ValueError(reason) from None
    return value


def _validate_api_base(value: Any) -> str:
    api_base = _require_nonblank_string(value, "invalid_api_base")
    try:
        parsed = urlsplit(api_base)
        _ = parsed.port
    except ValueError:
        raise ValueError("invalid_api_base") from None
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("invalid_api_base")
    return api_base


def _load_row(path: Path) -> _QualificationRow:
    try:
        source_path = path.resolve(strict=True)
    except Exception:
        raise ValueError("invalid_row_file") from None
    row_bytes, row_text = _read_strict_utf8(source_path, "invalid_row_utf8")
    try:
        document = json.loads(
            row_text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_json_constant,
        )
    except ValueError as exc:
        if str(exc) == "duplicate_json_key":
            raise
        raise ValueError("invalid_row_json") from None
    if type(document) is not dict or frozenset(document) != _ROW_KEYS:
        raise ValueError("invalid_row_keys")

    model = _require_nonblank_string(document["model"], "invalid_model")
    api_base = _validate_api_base(document["api_base"])
    intent = _require_nonblank_string(document["intent"], "invalid_intent")
    skill_value = _require_nonblank_string(
        document["skill_path"],
        "invalid_skill_path",
    )

    target = document["rhino_target"]
    if type(target) is not dict:
        raise ValueError("invalid_rhino_target")
    if frozenset(target) != _TARGET_KEYS:
        raise ValueError("invalid_rhino_target_keys")
    target_values: dict[str, int] = {}
    for field in _TARGET_KEYS:
        value = target[field]
        if type(value) is not int or value <= 0:
            raise ValueError(f"invalid_{field}")
        target_values[field] = value

    try:
        skill_path = Path(skill_value).resolve(strict=True)
    except Exception:
        raise ValueError("invalid_skill_file") from None
    if not skill_path.is_file():
        raise ValueError("invalid_skill_file")
    skill_bytes, skill_text = _read_strict_utf8(skill_path, "invalid_skill_utf8")

    return _QualificationRow(
        source_path=source_path,
        source_sha256=hashlib.sha256(row_bytes).hexdigest(),
        model=model,
        api_base=api_base,
        intent=intent,
        skill_path=skill_path,
        skill_sha256=hashlib.sha256(skill_bytes).hexdigest(),
        skill_text=skill_text,
        target=_RhinoTarget(**target_values),
    )


class _JsonlRecorder:
    def __init__(
        self,
        *,
        path: Path,
        stream: BinaryIO,
        wall_clock: Callable[[], str],
    ) -> None:
        self._path = path
        self._stream = stream
        self._wall_clock = wall_clock
        self._bytes_written = 0
        self._sequence = 0
        self._failed = False
        self._closed = False
        self._close_attempted = False

    @property
    def path(self) -> Path:
        return self._path

    @property
    def bytes_written(self) -> int:
        return self._bytes_written

    @property
    def sequence(self) -> int:
        return self._sequence

    @property
    def failed(self) -> bool:
        return self._failed

    @property
    def closed(self) -> bool:
        return self._closed

    def record(self, kind: str, payload: Mapping[str, Any]) -> None:
        self._require_writable()
        if type(kind) is not str or kind not in _TRACE_KINDS:
            raise ValueError("invalid_trace_kind")
        next_sequence = self._sequence + 1
        try:
            row = (
                json.dumps(
                    {
                        "sequence": next_sequence,
                        "recorded_at_utc": self._wall_clock(),
                        "kind": kind,
                        "payload": payload,
                    },
                    ensure_ascii=True,
                    allow_nan=False,
                    separators=(",", ":"),
                )
                + "\n"
            ).encode("utf-8")
        except Exception:
            self._fail("json_serialization_failed")
        if len(row) > _ROW_MAX_BYTES:
            self._fail("row_size_exceeded")
        if self._bytes_written + len(row) > _TRACE_MAX_BYTES:
            self._fail("total_size_exceeded")

        try:
            written = self._stream.write(row)
        except Exception:
            self._fail("write_failed")
        if type(written) is not int or written < 0 or written > len(row):
            self._fail("invalid_write_count")
        self._bytes_written += written
        if written != len(row):
            self._fail("short_write")
        try:
            self._stream.flush()
        except Exception:
            self._fail("flush_failed")
        self._sequence = next_sequence

    def close(self) -> None:
        if self._close_attempted:
            return
        self._close_attempted = True
        try:
            self._stream.close()
        except Exception:
            self._failed = True
            raise _TraceWriteFailure("close_failed", self._path) from None
        self._closed = True

    def _require_writable(self) -> None:
        if self._failed:
            raise _TraceWriteFailure("recorder_failed", self._path)
        if self._closed:
            raise _TraceWriteFailure("recorder_closed", self._path)

    def _fail(self, reason: str) -> None:
        self._failed = True
        raise _TraceWriteFailure(reason, self._path)


def _utc_now_string() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _open_recorder() -> _JsonlRecorder:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if type(local_app_data) is not str or not local_app_data.strip():
        raise _TraceWriteFailure("localappdata_missing", None)
    trace_directory = Path(local_app_data) / "Rook" / "traces"
    try:
        trace_directory.mkdir(parents=True, exist_ok=True)
    except Exception:
        raise _TraceWriteFailure("trace_directory_create_failed", None) from None
    try:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        filename = (
            f"chatrunner-headless-qualification-{stamp}-"
            f"p{os.getpid()}-{secrets.token_hex(4)}.jsonl"
        )
        path = (trace_directory / filename).resolve()
    except Exception:
        raise _TraceWriteFailure("trace_path_prepare_failed", None) from None
    try:
        stream = path.open("xb", buffering=0)
    except Exception:
        raise _TraceWriteFailure("trace_open_failed", path) from None
    return _JsonlRecorder(path=path, stream=stream, wall_clock=_utc_now_string)
