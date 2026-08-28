"""Durable per-conversation registry for the opt-in Prime chat backend."""

from __future__ import annotations

import json
import msvcrt
import os
import re
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Mapping, Sequence, cast


LifecycleState = Literal[
    "idle",
    "running",
    "cancel_requested",
    "failed",
    "closed",
]

_LIFECYCLE_STATES = frozenset(
    {"idle", "running", "cancel_requested", "failed", "closed"}
)
_CONVERSATION_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_CANONICAL_DECIMAL = re.compile(r"^(0|[1-9][0-9]*)$")
_UTC_TIMESTAMP = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?Z$"
)
_MAX_INT64 = (1 << 63) - 1


class RegistryError(RuntimeError):
    """Base error for durable registry operations."""


class RegistryValidationError(RegistryError, ValueError):
    """A registry identity or persisted record violates the closed contract."""


class RegistryLockError(RegistryError):
    """The process-generation namespace already has a writer."""


def _require_exact_keys(
    value: Mapping[str, Any], expected: frozenset[str], label: str
) -> None:
    actual = frozenset(value)
    if actual != expected:
        missing = sorted(expected - actual)
        unknown = sorted(actual - expected)
        raise RegistryValidationError(
            f"invalid {label} keys: missing={missing}, unknown={unknown}"
        )


def _require_nonempty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise RegistryValidationError(f"{label} must be a non-empty string")
    return value


def _require_int(value: Any, label: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise RegistryValidationError(f"{label} must be an integer >= {minimum}")
    return value


def _validate_conversation_id(value: Any) -> str:
    conversation_id = _require_nonempty_string(value, "conversation_id")
    if _CONVERSATION_ID.fullmatch(conversation_id) is None:
        raise RegistryValidationError("conversation_id is not path-safe")
    return conversation_id


def _validate_process_start_ticks(value: Any) -> str:
    if not isinstance(value, str) or _CANONICAL_DECIMAL.fullmatch(value) is None:
        raise RegistryValidationError(
            "process start ticks must be a canonical decimal string"
        )
    if int(value) > _MAX_INT64:
        raise RegistryValidationError("process start ticks exceed signed 64-bit range")
    return value


def _validate_utc_timestamp(value: Any) -> str:
    timestamp = _require_nonempty_string(value, "updated_at_utc")
    if _UTC_TIMESTAMP.fullmatch(timestamp) is None:
        raise RegistryValidationError("updated_at_utc must be an ISO-8601 UTC timestamp")
    try:
        datetime.fromisoformat(timestamp[:-1] + "+00:00")
    except ValueError as error:
        raise RegistryValidationError(
            "updated_at_utc must be an ISO-8601 UTC timestamp"
        ) from error
    return timestamp


def _absolute_path_without_resolution(value: Any) -> str:
    session_path = _require_nonempty_string(value, "prime_session_path")
    return str(Path(os.path.abspath(session_path)))


@dataclass(frozen=True)
class TargetFingerprint:
    rhino_pid: int
    rhino_process_start_utc_ticks: str
    document_runtime_serial: int

    def __post_init__(self) -> None:
        _require_int(self.rhino_pid, "rhino_pid", minimum=1)
        _validate_process_start_ticks(self.rhino_process_start_utc_ticks)
        _require_int(
            self.document_runtime_serial,
            "document_runtime_serial",
            minimum=1,
        )


@dataclass(frozen=True)
class PrimeModelSelection:
    provider: str
    id: str
    thinking: str | None

    def __post_init__(self) -> None:
        _require_nonempty_string(self.provider, "model.provider")
        _require_nonempty_string(self.id, "model.id")
        if self.thinking is not None:
            _require_nonempty_string(self.thinking, "model.thinking")


@dataclass(frozen=True)
class LifecycleRecord:
    state: LifecycleState
    reason: str | None
    updated_at_utc: str

    def __post_init__(self) -> None:
        if self.state not in _LIFECYCLE_STATES:
            raise RegistryValidationError(f"unsupported lifecycle state: {self.state}")
        if self.reason is not None:
            _require_nonempty_string(self.reason, "lifecycle.reason")
        _validate_utc_timestamp(self.updated_at_utc)


@dataclass(frozen=True)
class PrimeConversationRecord:
    schema_version: Literal[1]
    conversation_id: str
    prime_session_id: str
    prime_session_path: str
    model: PrimeModelSelection
    target: TargetFingerprint
    last_lifecycle: LifecycleRecord

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise RegistryValidationError("schema_version must equal 1")
        _validate_conversation_id(self.conversation_id)
        _require_nonempty_string(self.prime_session_id, "prime_session_id")
        object.__setattr__(
            self,
            "prime_session_path",
            _absolute_path_without_resolution(self.prime_session_path),
        )
        if not isinstance(self.model, PrimeModelSelection):
            raise RegistryValidationError("model must be PrimeModelSelection")
        if not isinstance(self.target, TargetFingerprint):
            raise RegistryValidationError("target must be TargetFingerprint")
        if not isinstance(self.last_lifecycle, LifecycleRecord):
            raise RegistryValidationError("last_lifecycle must be LifecycleRecord")


_RECORD_KEYS = frozenset(
    {
        "schemaVersion",
        "conversationId",
        "primeSessionId",
        "primeSessionPath",
        "model",
        "target",
        "lastLifecycle",
    }
)
_MODEL_KEYS = frozenset({"provider", "id", "thinking"})
_TARGET_KEYS = frozenset(
    {"rhinoPid", "rhinoProcessStartUtcTicks", "documentRuntimeSerial"}
)
_LIFECYCLE_KEYS = frozenset({"state", "reason", "updatedAtUtc"})


def _record_to_dict(record: PrimeConversationRecord) -> dict[str, Any]:
    return {
        "schemaVersion": record.schema_version,
        "conversationId": record.conversation_id,
        "primeSessionId": record.prime_session_id,
        "primeSessionPath": record.prime_session_path,
        "model": {
            "provider": record.model.provider,
            "id": record.model.id,
            "thinking": record.model.thinking,
        },
        "target": {
            "rhinoPid": record.target.rhino_pid,
            "rhinoProcessStartUtcTicks": (
                record.target.rhino_process_start_utc_ticks
            ),
            "documentRuntimeSerial": record.target.document_runtime_serial,
        },
        "lastLifecycle": {
            "state": record.last_lifecycle.state,
            "reason": record.last_lifecycle.reason,
            "updatedAtUtc": record.last_lifecycle.updated_at_utc,
        },
    }


def _require_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise RegistryValidationError(f"{label} must be an object")
    return cast(Mapping[str, Any], value)


def _record_from_dict(value: Any) -> PrimeConversationRecord:
    payload = _require_mapping(value, "record")
    _require_exact_keys(payload, _RECORD_KEYS, "record")
    model = _require_mapping(payload["model"], "model")
    target = _require_mapping(payload["target"], "target")
    lifecycle = _require_mapping(payload["lastLifecycle"], "lifecycle")
    _require_exact_keys(model, _MODEL_KEYS, "model")
    _require_exact_keys(target, _TARGET_KEYS, "target")
    _require_exact_keys(lifecycle, _LIFECYCLE_KEYS, "lifecycle")

    session_path = _require_nonempty_string(
        payload["primeSessionPath"], "prime_session_path"
    )
    if not Path(session_path).is_absolute():
        raise RegistryValidationError("persisted prime_session_path must be absolute")

    thinking = model["thinking"]
    if thinking is not None and not isinstance(thinking, str):
        raise RegistryValidationError("model.thinking must be a string or null")
    reason = lifecycle["reason"]
    if reason is not None and not isinstance(reason, str):
        raise RegistryValidationError("lifecycle.reason must be a string or null")

    return PrimeConversationRecord(
        schema_version=payload["schemaVersion"],
        conversation_id=payload["conversationId"],
        prime_session_id=payload["primeSessionId"],
        prime_session_path=session_path,
        model=PrimeModelSelection(
            provider=model["provider"],
            id=model["id"],
            thinking=thinking,
        ),
        target=TargetFingerprint(
            rhino_pid=target["rhinoPid"],
            rhino_process_start_utc_ticks=target[
                "rhinoProcessStartUtcTicks"
            ],
            document_runtime_serial=target["documentRuntimeSerial"],
        ),
        last_lifecycle=LifecycleRecord(
            state=lifecycle["state"],
            reason=reason,
            updated_at_utc=lifecycle["updatedAtUtc"],
        ),
    )


def _reject_duplicate_keys(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RegistryValidationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


class PrimeConversationRegistry:
    """One-writer atomic registry for one Rhino process generation."""

    def __init__(
        self,
        registry_root: str | os.PathLike[str],
        rhino_pid: int,
        rhino_process_start_utc_ticks: str,
    ) -> None:
        self.rhino_pid = _require_int(rhino_pid, "rhino_pid", minimum=1)
        self.rhino_process_start_utc_ticks = _validate_process_start_ticks(
            rhino_process_start_utc_ticks
        )
        self.namespace = Path(registry_root).absolute() / (
            f"{self.rhino_pid}-{self.rhino_process_start_utc_ticks}"
        )
        self.namespace.mkdir(parents=True, exist_ok=True)
        self._lock_file = None
        self._closed = False
        self._acquire_writer_lock()

    def _acquire_writer_lock(self) -> None:
        lock_path = self.namespace / ".writer.lock"
        lock_file = lock_path.open("a+b")
        try:
            lock_file.seek(0, os.SEEK_END)
            if lock_file.tell() == 0:
                lock_file.write(b"\0")
                lock_file.flush()
            lock_file.seek(0)
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as error:
            lock_file.close()
            raise RegistryLockError(
                f"registry namespace already has a writer: {self.namespace}"
            ) from error
        self._lock_file = lock_file

    def _ensure_open(self) -> None:
        if self._closed or self._lock_file is None:
            raise RegistryError("registry is closed")

    def _record_path(self, conversation_id: str) -> Path:
        return self.namespace / f"{_validate_conversation_id(conversation_id)}.json"

    def write(self, record: PrimeConversationRecord) -> Path:
        self._ensure_open()
        if not isinstance(record, PrimeConversationRecord):
            raise RegistryValidationError("record must be PrimeConversationRecord")
        if (
            record.target.rhino_pid != self.rhino_pid
            or record.target.rhino_process_start_utc_ticks
            != self.rhino_process_start_utc_ticks
        ):
            raise RegistryValidationError(
                "record target does not match registry process generation"
            )

        target_path = self._record_path(record.conversation_id)
        temporary_path = self.namespace / (
            f".{record.conversation_id}.{uuid.uuid4().hex}.tmp"
        )
        try:
            with temporary_path.open("x", encoding="utf-8", newline="\n") as stream:
                json.dump(
                    _record_to_dict(record),
                    stream,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_path, target_path)
        except BaseException:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise
        return target_path

    def load(self, conversation_id: str) -> PrimeConversationRecord:
        self._ensure_open()
        path = self._record_path(conversation_id)
        try:
            payload = json.loads(
                path.read_text(encoding="utf-8"),
                object_pairs_hook=_reject_duplicate_keys,
            )
        except RegistryValidationError:
            raise
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise RegistryValidationError(
                f"unable to read registry record: {conversation_id}"
            ) from error

        loaded = _record_from_dict(payload)
        if loaded.conversation_id != conversation_id:
            raise RegistryValidationError(
                "conversation ID does not match registry filename"
            )
        if (
            loaded.target.rhino_pid != self.rhino_pid
            or loaded.target.rhino_process_start_utc_ticks
            != self.rhino_process_start_utc_ticks
        ):
            raise RegistryValidationError(
                "record target does not match registry process generation"
            )
        return loaded

    def reconcile_interrupted_records(self) -> tuple[str, ...]:
        self._ensure_open()
        changed: list[str] = []
        for path in sorted(self.namespace.glob("*.json")):
            conversation_id = path.stem
            current = self.load(conversation_id)
            if current.last_lifecycle.state not in {
                "running",
                "cancel_requested",
            }:
                continue
            lifecycle = LifecycleRecord(
                state="failed",
                reason="broker_restart_interrupted",
                updated_at_utc=_utc_now(),
            )
            self.write(replace(current, last_lifecycle=lifecycle))
            changed.append(conversation_id)
        return tuple(changed)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        lock_file = self._lock_file
        self._lock_file = None
        if lock_file is None:
            return
        try:
            lock_file.seek(0)
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
        finally:
            lock_file.close()

    def __enter__(self) -> PrimeConversationRegistry:
        self._ensure_open()
        return self

    def __exit__(self, _exc_type: object, _exc: object, _tb: object) -> None:
        self.close()
