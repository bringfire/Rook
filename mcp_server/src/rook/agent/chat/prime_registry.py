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
_SHA256 = re.compile(r"^[0-9A-F]{64}$")
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


def _absolute_path_without_resolution(value: Any, label: str = "prime_session_path") -> str:
    path = _require_nonempty_string(value, label)
    return str(Path(os.path.abspath(path)))


def _require_persisted_absolute_path(value: Any, label: str) -> str:
    path = _require_nonempty_string(value, label)
    if not Path(path).is_absolute():
        raise RegistryValidationError(f"persisted {label} must be absolute")
    return str(Path(path))


def _validate_sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise RegistryValidationError(f"{label} must be an uppercase SHA-256")
    return value


def _validate_grasshopper_document_id(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise RegistryValidationError(
            "Grasshopper document ID must be a canonical nonempty GUID"
        )
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError) as error:
        raise RegistryValidationError(
            "Grasshopper document ID must be a canonical nonempty GUID"
        ) from error
    if parsed.int == 0 or str(parsed) != value:
        raise RegistryValidationError(
            "Grasshopper document ID must be a canonical nonempty GUID"
        )
    return value


def _is_path_beneath(path: str, root: str) -> bool:
    try:
        return os.path.commonpath((path, root)) == root
    except ValueError:
        return False


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


@dataclass(frozen=True)
class RuntimePreparation:
    status: Literal["pending", "prepared"]
    interpreter_path: str | None
    prepared_at_utc: str | None

    def __post_init__(self) -> None:
        if self.status == "pending":
            if self.interpreter_path is not None or self.prepared_at_utc is not None:
                raise RegistryValidationError(
                    "pending preparation requires null interpreter and timestamp"
                )
            return
        if self.status != "prepared":
            raise RegistryValidationError("unsupported runtime preparation status")
        if self.interpreter_path is None or self.prepared_at_utc is None:
            raise RegistryValidationError(
                "prepared preparation requires interpreter and timestamp"
            )
        object.__setattr__(
            self,
            "interpreter_path",
            _absolute_path_without_resolution(
                self.interpreter_path, "runtime preparation interpreter path"
            ),
        )
        _validate_utc_timestamp(self.prepared_at_utc)


@dataclass(frozen=True)
class PrimeRuntimeContractRef:
    contract_fingerprint_sha256: str
    capability_profile: Literal["readonly", "full"]
    kernel_environment_path: str
    preparation: RuntimePreparation

    def __post_init__(self) -> None:
        _validate_sha256(
            self.contract_fingerprint_sha256, "runtime contract fingerprint"
        )
        if self.capability_profile not in {"readonly", "full"}:
            raise RegistryValidationError(
                "capability profile must be readonly or full"
            )
        environment = _absolute_path_without_resolution(
            self.kernel_environment_path, "kernel environment path"
        )
        object.__setattr__(self, "kernel_environment_path", environment)
        if not isinstance(self.preparation, RuntimePreparation):
            raise RegistryValidationError("preparation must be RuntimePreparation")
        interpreter = self.preparation.interpreter_path
        if interpreter is not None and not _is_path_beneath(interpreter, environment):
            raise RegistryValidationError(
                "prepared interpreter must be beneath the contract environment"
            )


@dataclass(frozen=True)
class TargetFingerprintV2:
    rhino_pid: int
    rhino_process_start_utc_ticks: str
    document_runtime_serial: int
    grasshopper_document_id: str | None

    def __post_init__(self) -> None:
        _require_int(self.rhino_pid, "rhino_pid", minimum=1)
        _validate_process_start_ticks(self.rhino_process_start_utc_ticks)
        _require_int(
            self.document_runtime_serial,
            "document_runtime_serial",
            minimum=1,
        )
        _validate_grasshopper_document_id(self.grasshopper_document_id)


@dataclass(frozen=True)
class PrimeConversationRecordV2:
    schema_version: Literal[2]
    conversation_id: str
    prime_session_id: str
    prime_session_path: str
    model: PrimeModelSelection
    runtime: PrimeRuntimeContractRef
    target: TargetFingerprintV2
    last_lifecycle: LifecycleRecord

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != 2:
            raise RegistryValidationError("schema_version must equal 2")
        _validate_conversation_id(self.conversation_id)
        _require_nonempty_string(self.prime_session_id, "prime_session_id")
        object.__setattr__(
            self,
            "prime_session_path",
            _absolute_path_without_resolution(self.prime_session_path),
        )
        if not isinstance(self.model, PrimeModelSelection):
            raise RegistryValidationError("model must be PrimeModelSelection")
        if not isinstance(self.runtime, PrimeRuntimeContractRef):
            raise RegistryValidationError("runtime must be PrimeRuntimeContractRef")
        if not isinstance(self.target, TargetFingerprintV2):
            raise RegistryValidationError("target must be TargetFingerprintV2")
        if not isinstance(self.last_lifecycle, LifecycleRecord):
            raise RegistryValidationError("last_lifecycle must be LifecycleRecord")


PrimeConversationRecordUnion = PrimeConversationRecord | PrimeConversationRecordV2


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
_V2_RECORD_KEYS = frozenset(
    {
        "schemaVersion",
        "conversationId",
        "primeSessionId",
        "primeSessionPath",
        "model",
        "runtime",
        "target",
        "lastLifecycle",
    }
)
_RUNTIME_KEYS = frozenset(
    {
        "contractFingerprintSha256",
        "capabilityProfile",
        "kernelEnvironmentPath",
        "preparation",
    }
)
_PREPARATION_KEYS = frozenset({"status", "interpreterPath", "preparedAtUtc"})
_V2_TARGET_KEYS = frozenset(
    {
        "rhinoPid",
        "rhinoProcessStartUtcTicks",
        "documentRuntimeSerial",
        "grasshopperDocumentId",
    }
)


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


def _record_v2_to_dict(record: PrimeConversationRecordV2) -> dict[str, Any]:
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
        "runtime": {
            "contractFingerprintSha256": (
                record.runtime.contract_fingerprint_sha256
            ),
            "capabilityProfile": record.runtime.capability_profile,
            "kernelEnvironmentPath": record.runtime.kernel_environment_path,
            "preparation": {
                "status": record.runtime.preparation.status,
                "interpreterPath": record.runtime.preparation.interpreter_path,
                "preparedAtUtc": record.runtime.preparation.prepared_at_utc,
            },
        },
        "target": {
            "rhinoPid": record.target.rhino_pid,
            "rhinoProcessStartUtcTicks": (
                record.target.rhino_process_start_utc_ticks
            ),
            "documentRuntimeSerial": record.target.document_runtime_serial,
            "grasshopperDocumentId": record.target.grasshopper_document_id,
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


def _record_v2_from_dict(value: Any) -> PrimeConversationRecordV2:
    payload = _require_mapping(value, "v2 record")
    _require_exact_keys(payload, _V2_RECORD_KEYS, "v2 record")
    model = _require_mapping(payload["model"], "model")
    runtime = _require_mapping(payload["runtime"], "runtime")
    preparation = _require_mapping(runtime["preparation"], "preparation")
    target = _require_mapping(payload["target"], "v2 target")
    lifecycle = _require_mapping(payload["lastLifecycle"], "lifecycle")
    _require_exact_keys(model, _MODEL_KEYS, "model")
    _require_exact_keys(runtime, _RUNTIME_KEYS, "runtime")
    _require_exact_keys(preparation, _PREPARATION_KEYS, "preparation")
    _require_exact_keys(target, _V2_TARGET_KEYS, "v2 target")
    _require_exact_keys(lifecycle, _LIFECYCLE_KEYS, "lifecycle")

    session_path = _require_persisted_absolute_path(
        payload["primeSessionPath"], "prime_session_path"
    )
    environment_path = _require_persisted_absolute_path(
        runtime["kernelEnvironmentPath"], "kernel environment path"
    )
    interpreter_path = preparation["interpreterPath"]
    if interpreter_path is not None:
        interpreter_path = _require_persisted_absolute_path(
            interpreter_path, "runtime preparation interpreter path"
        )
    thinking = model["thinking"]
    if thinking is not None and not isinstance(thinking, str):
        raise RegistryValidationError("model.thinking must be a string or null")
    reason = lifecycle["reason"]
    if reason is not None and not isinstance(reason, str):
        raise RegistryValidationError("lifecycle.reason must be a string or null")

    return PrimeConversationRecordV2(
        schema_version=payload["schemaVersion"],
        conversation_id=payload["conversationId"],
        prime_session_id=payload["primeSessionId"],
        prime_session_path=session_path,
        model=PrimeModelSelection(
            provider=model["provider"], id=model["id"], thinking=thinking
        ),
        runtime=PrimeRuntimeContractRef(
            contract_fingerprint_sha256=runtime["contractFingerprintSha256"],
            capability_profile=runtime["capabilityProfile"],
            kernel_environment_path=environment_path,
            preparation=RuntimePreparation(
                status=preparation["status"],
                interpreter_path=interpreter_path,
                prepared_at_utc=preparation["preparedAtUtc"],
            ),
        ),
        target=TargetFingerprintV2(
            rhino_pid=target["rhinoPid"],
            rhino_process_start_utc_ticks=target["rhinoProcessStartUtcTicks"],
            document_runtime_serial=target["documentRuntimeSerial"],
            grasshopper_document_id=target["grasshopperDocumentId"],
        ),
        last_lifecycle=LifecycleRecord(
            state=lifecycle["state"],
            reason=reason,
            updated_at_utc=lifecycle["updatedAtUtc"],
        ),
    )


def _record_union_from_dict(value: Any) -> PrimeConversationRecordUnion:
    payload = _require_mapping(value, "record")
    schema_version = payload.get("schemaVersion")
    if type(schema_version) is not int:
        raise RegistryValidationError("schemaVersion must be an integer")
    if schema_version == 1:
        return _record_from_dict(value)
    if schema_version == 2:
        return _record_v2_from_dict(value)
    raise RegistryValidationError(f"unsupported schemaVersion: {schema_version}")


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

    def exists(self, conversation_id: str) -> bool:
        self._ensure_open()
        return self._record_path(conversation_id).is_file()

    def conversation_ids(self) -> tuple[str, ...]:
        self._ensure_open()
        conversation_ids = tuple(path.stem for path in sorted(self.namespace.glob("*.json")))
        for conversation_id in conversation_ids:
            _validate_conversation_id(conversation_id)
        return conversation_ids

    def _validate_record_generation(
        self, record: PrimeConversationRecordUnion
    ) -> None:
        if (
            record.target.rhino_pid != self.rhino_pid
            or record.target.rhino_process_start_utc_ticks
            != self.rhino_process_start_utc_ticks
        ):
            raise RegistryValidationError(
                "record target does not match registry process generation"
            )

    def _write_atomic(self, record: PrimeConversationRecordUnion) -> Path:
        self._ensure_open()
        if not isinstance(record, (PrimeConversationRecord, PrimeConversationRecordV2)):
            raise RegistryValidationError("record must be a supported conversation record")
        self._validate_record_generation(record)

        target_path = self._record_path(record.conversation_id)
        temporary_path = self.namespace / (
            f".{record.conversation_id}.{uuid.uuid4().hex}.tmp"
        )
        try:
            with temporary_path.open("x", encoding="utf-8", newline="\n") as stream:
                json.dump(
                    (
                        _record_to_dict(record)
                        if isinstance(record, PrimeConversationRecord)
                        else _record_v2_to_dict(record)
                    ),
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

    def write(self, record: PrimeConversationRecordUnion) -> Path:
        self._ensure_open()
        if isinstance(record, PrimeConversationRecord):
            if self.exists(record.conversation_id):
                current = self.load(record.conversation_id)
                if not isinstance(current, PrimeConversationRecord):
                    raise RegistryValidationError("record schema version is immutable")
            return self._write_atomic(record)
        if not isinstance(record, PrimeConversationRecordV2):
            raise RegistryValidationError("record must be a supported conversation record")
        if not self.exists(record.conversation_id):
            raise RegistryValidationError("new v2 records require write_new_v2")
        current = self.load(record.conversation_id)
        if not isinstance(current, PrimeConversationRecordV2):
            raise RegistryValidationError("record schema version is immutable")
        if (
            record.runtime.contract_fingerprint_sha256
            != current.runtime.contract_fingerprint_sha256
            or record.runtime.capability_profile
            != current.runtime.capability_profile
            or record.runtime.kernel_environment_path
            != current.runtime.kernel_environment_path
            or record.target != current.target
        ):
            raise RegistryValidationError(
                "v2 runtime contract, capability profile, environment, and target are immutable"
            )
        if record.runtime.preparation != current.runtime.preparation:
            raise RegistryValidationError(
                "runtime preparation changes require an explicit transition"
            )
        return self._write_atomic(record)

    def write_new_v2(self, record: PrimeConversationRecordV2) -> Path:
        self._ensure_open()
        if not isinstance(record, PrimeConversationRecordV2):
            raise RegistryValidationError("record must be PrimeConversationRecordV2")
        if self.exists(record.conversation_id):
            raise RegistryValidationError("conversation already exists")
        if record.runtime.preparation.status != "pending":
            raise RegistryValidationError("new v2 runtime must be pending")
        return self._write_atomic(record)

    def mark_runtime_prepared(
        self,
        conversation_id: str,
        interpreter_path: str,
        prepared_at_utc: str,
    ) -> PrimeConversationRecordV2:
        current = self.load(conversation_id)
        if not isinstance(current, PrimeConversationRecordV2):
            raise RegistryValidationError("runtime preparation requires a v2 record")
        if current.runtime.preparation.status != "pending":
            raise RegistryValidationError("runtime is already prepared")
        preparation = RuntimePreparation(
            status="prepared",
            interpreter_path=interpreter_path,
            prepared_at_utc=prepared_at_utc,
        )
        updated = replace(
            current,
            runtime=replace(current.runtime, preparation=preparation),
        )
        self._write_atomic(updated)
        return updated

    def mark_pending_runtime_unavailable(
        self, conversation_id: str
    ) -> PrimeConversationRecordV2:
        current = self.load(conversation_id)
        if not isinstance(current, PrimeConversationRecordV2):
            raise RegistryValidationError("runtime failure requires a v2 record")
        if current.runtime.preparation.status != "pending":
            raise RegistryValidationError("prepared runtime cannot become unavailable")
        updated = replace(
            current,
            last_lifecycle=LifecycleRecord(
                state="failed",
                reason="runtime_contract_unavailable",
                updated_at_utc=_utc_now(),
            ),
        )
        self._write_atomic(updated)
        return updated

    def load(self, conversation_id: str) -> PrimeConversationRecordUnion:
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

        loaded = _record_union_from_dict(payload)
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
            if (
                isinstance(current, PrimeConversationRecordV2)
                and current.runtime.preparation.status == "pending"
            ):
                self.mark_pending_runtime_unavailable(conversation_id)
                changed.append(conversation_id)
                continue
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
