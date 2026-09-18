"""Durable identity envelope and crash-fence custody for ACP RookChat."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from rook.runtime_paths import AcpDataPaths


MAX_SESSION_HEADER_BYTES = 64 * 1024
MAX_ASSOCIATION_BYTES = 64 * 1024
SUPPORTED_SESSION_HEADER_VERSIONS = frozenset({3})
ASSOCIATION_SCHEMA_VERSION = 1
_WINDOWS_ATOMIC_PUBLISH = os.name == "nt"


class AcpStorageError(RuntimeError):
    code = "storage_error"

    def __init__(self, detail: str | None = None) -> None:
        super().__init__(self.code if detail is None else f"{self.code}: {detail}")


class SessionUnavailable(AcpStorageError):
    code = "session_unavailable"


class RuntimeUnavailable(AcpStorageError):
    code = "runtime_unavailable"


class WorkingDirectoryUnavailable(AcpStorageError):
    code = "working_directory_unavailable"


class SessionRecoveryRequired(AcpStorageError):
    code = "session_recovery_required"


class InitializationFailed(AcpStorageError):
    code = "initialization_failed"


class PublicationUnsupported(AcpStorageError):
    code = "publication_unsupported"


class PublicationAlreadyExists(AcpStorageError):
    code = "publication_already_exists"


class AssociationAlreadyExists(AcpStorageError):
    code = "association_already_exists"


@dataclass(frozen=True)
class RookBinding:
    profile: Literal["readonly", "full"]
    host_generation_id: str
    rhino_document_serial: int
    route_process_id: int

    def __post_init__(self) -> None:
        if type(self.profile) is not str or self.profile not in {"readonly", "full"}:
            raise ValueError("Rook capability profile is invalid")
        if type(self.host_generation_id) is not str:
            raise ValueError("host generation ID must be a UUID")
        try:
            parsed = uuid.UUID(self.host_generation_id)
        except (ValueError, AttributeError) as exc:
            raise ValueError("host generation ID must be a UUID") from exc
        object.__setattr__(self, "host_generation_id", str(parsed))
        if type(self.rhino_document_serial) is not int or self.rhino_document_serial <= 0:
            raise ValueError("Rhino document serial must be positive")
        if type(self.route_process_id) is not int or self.route_process_id <= 0:
            raise ValueError("route process ID must be positive")


@dataclass(frozen=True)
class PrimeSessionHeader:
    version: int
    session_id: str
    working_directory: str


@dataclass(frozen=True)
class ProvisionalAssociation:
    conversation_id: str
    session_path: str
    working_directory: str
    runtime_id: str
    binding: RookBinding
    requested_initial_model: str | None
    requested_initial_reasoning: str | None


@dataclass(frozen=True)
class ConversationAssociation:
    schema_version: int
    conversation_id: str
    session_path: str
    prime_session_id: str
    working_directory: str
    runtime_id: str
    binding: RookBinding
    requested_initial_model: str | None
    requested_initial_reasoning: str | None
    created_at_utc: str


def _canonical_path(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def _same_path(left: Path, right: Path) -> bool:
    return os.path.normcase(str(_canonical_path(left))) == os.path.normcase(str(_canonical_path(right)))


def _is_under(path: Path, root: Path) -> bool:
    try:
        _canonical_path(path).relative_to(_canonical_path(root))
    except ValueError:
        return False
    return True


def _is_symlink_or_reparse(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    if is_junction is not None and is_junction():
        return True
    try:
        attributes = os.lstat(path).st_file_attributes
    except (AttributeError, FileNotFoundError, OSError):
        return False
    return bool(attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def _assert_direct_regular_file(path: Path, root: Path) -> None:
    canonical_root = _canonical_path(root)
    if not root.exists() or _is_symlink_or_reparse(root):
        raise SessionUnavailable("session root is unavailable")
    if path.parent.resolve(strict=False) != canonical_root or not _is_under(path, canonical_root):
        raise SessionUnavailable("session path is outside the product root")
    if _is_symlink_or_reparse(path):
        raise SessionUnavailable("session path is a symlink or reparse point")
    try:
        mode = os.lstat(path).st_mode
    except OSError as exc:
        raise SessionUnavailable("session file is missing") from exc
    if not stat.S_ISREG(mode):
        raise SessionUnavailable("session path is not a regular file")


def validate_prime_session_header(
    session_path: Path,
    *,
    expected_id: str | None,
    expected_cwd: Path,
    sessions_root: Path,
) -> PrimeSessionHeader:
    _assert_direct_regular_file(session_path, sessions_root)
    try:
        with session_path.open("rb") as handle:
            line = handle.readline(MAX_SESSION_HEADER_BYTES + 1)
    except OSError as exc:
        raise SessionUnavailable("session header cannot be read") from exc
    if not line or len(line) > MAX_SESSION_HEADER_BYTES:
        raise SessionUnavailable("session header is empty or oversized")
    try:
        payload = json.loads(line.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SessionUnavailable("session header is not valid UTF-8 JSON") from exc
    if not isinstance(payload, dict) or payload.get("type") != "session":
        raise SessionUnavailable("session header type is invalid")
    version = payload.get("version")
    session_id = payload.get("id")
    stored_cwd = payload.get("cwd")
    if type(version) is not int or version not in SUPPORTED_SESSION_HEADER_VERSIONS:
        raise SessionUnavailable("session header version is unsupported")
    if not isinstance(session_id, str) or not session_id.strip():
        raise SessionUnavailable("session header ID is invalid")
    if expected_id is not None and session_id != expected_id:
        raise SessionUnavailable("session header ID does not match the association")
    if not isinstance(stored_cwd, str) or not stored_cwd.strip():
        raise SessionUnavailable("session working directory is invalid")
    stored_path = Path(stored_cwd)
    if not stored_path.is_absolute() or not _same_path(stored_path, expected_cwd):
        raise SessionUnavailable("session working directory does not match the association")
    return PrimeSessionHeader(
        version=version,
        session_id=session_id,
        working_directory=str(_canonical_path(stored_path)),
    )


def atomic_publish_noreplace(final_path: Path, payload: bytes) -> None:
    if not _WINDOWS_ATOMIC_PUBLISH:
        raise PublicationUnsupported("Windows no-replacement publication is required")
    final_path.parent.mkdir(parents=True, exist_ok=True)
    if _is_symlink_or_reparse(final_path.parent):
        raise PublicationUnsupported("publication parent is a reparse point")
    temporary = final_path.with_name(f".{final_path.name}.{uuid.uuid4().hex}.tmp")
    descriptor: int | None = None
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = None
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.rename(temporary, final_path)
        except FileExistsError as exc:
            raise PublicationAlreadyExists(str(final_path)) from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


class OpenClaim:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._released = False

    @classmethod
    def acquire(cls, claims_root: Path, canonical_session_path: str) -> "OpenClaim":
        claims_root.mkdir(parents=True, exist_ok=True)
        if _is_symlink_or_reparse(claims_root):
            raise SessionRecoveryRequired("claims root is a reparse point")
        digest = hashlib.sha256(canonical_session_path.encode("utf-8")).hexdigest()
        path = claims_root / f"{digest}.open.claim"
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o600)
        except FileExistsError as exc:
            raise SessionRecoveryRequired() from exc
        os.close(descriptor)
        return cls(path)

    def release_after_observed_exit(self) -> None:
        self._release()

    def release_no_child_created(self) -> None:
        self._release()

    def _release(self) -> None:
        if self._released:
            return
        self.path.unlink()
        self._released = True


class AssociationStore:
    def __init__(self, paths: AcpDataPaths) -> None:
        self.paths = paths
        self.paths.create_roots()

    def reserve_provisional(
        self,
        *,
        binding: RookBinding,
        runtime_id: str,
        working_directory: Path,
        requested_model: str | None,
        requested_reasoning: str | None,
    ) -> ProvisionalAssociation:
        canonical_cwd = _canonical_path(working_directory)
        if not working_directory.is_absolute() or not canonical_cwd.is_dir():
            raise WorkingDirectoryUnavailable()
        if not isinstance(runtime_id, str) or not runtime_id.strip():
            raise RuntimeUnavailable()
        conversation_id = uuid.uuid4().hex
        association_path = self.paths.conversation_path(conversation_id)
        session_path = self.paths.session_path(conversation_id)
        if association_path.exists() or session_path.exists():
            raise AssociationAlreadyExists(conversation_id)
        return ProvisionalAssociation(
            conversation_id=conversation_id,
            session_path=str(session_path.resolve(strict=False)),
            working_directory=str(canonical_cwd),
            runtime_id=runtime_id,
            binding=binding,
            requested_initial_model=requested_model,
            requested_initial_reasoning=requested_reasoning,
        )

    def publish(
        self,
        provisional: ProvisionalAssociation,
        header: PrimeSessionHeader,
    ) -> ConversationAssociation:
        expected_session = self.paths.session_path(provisional.conversation_id).resolve(strict=False)
        if not _same_path(Path(provisional.session_path), expected_session):
            raise SessionUnavailable("provisional session path is not product-owned")
        if not _same_path(Path(header.working_directory), Path(provisional.working_directory)):
            raise SessionUnavailable("header working directory does not match the provisional association")
        association = ConversationAssociation(
            schema_version=ASSOCIATION_SCHEMA_VERSION,
            conversation_id=provisional.conversation_id,
            session_path=str(expected_session),
            prime_session_id=header.session_id,
            working_directory=str(_canonical_path(Path(provisional.working_directory))),
            runtime_id=provisional.runtime_id,
            binding=provisional.binding,
            requested_initial_model=provisional.requested_initial_model,
            requested_initial_reasoning=provisional.requested_initial_reasoning,
            created_at_utc=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        )
        payload = json.dumps(asdict(association), sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
            "utf-8"
        ) + b"\n"
        try:
            atomic_publish_noreplace(self.paths.conversation_path(association.conversation_id), payload)
        except PublicationAlreadyExists as exc:
            raise AssociationAlreadyExists(association.conversation_id) from exc
        return association

    def get(self, conversation_id: str) -> ConversationAssociation:
        path = self.paths.conversation_path(conversation_id)
        if _is_symlink_or_reparse(path):
            raise SessionUnavailable("association is a reparse point")
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise SessionUnavailable("association is missing") from exc
        if not raw or len(raw) > MAX_ASSOCIATION_BYTES:
            raise SessionUnavailable("association is empty or oversized")
        try:
            payload = json.loads(raw.decode("utf-8", errors="strict"))
            association = _association_from_payload(payload)
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise SessionUnavailable("association is malformed") from exc
        if association.conversation_id != conversation_id:
            raise SessionUnavailable("association ID mismatch")
        if not _same_path(Path(association.session_path), self.paths.session_path(conversation_id)):
            raise SessionUnavailable("association session path mismatch")
        return association

    def list(self) -> tuple[ConversationAssociation, ...]:
        records = [self.get(path.stem) for path in sorted(self.paths.conversations_root.glob("*.json"))]
        return tuple(records)

    def delete_record(self, association: ConversationAssociation) -> None:
        current = self.get(association.conversation_id)
        if current != association:
            raise SessionUnavailable("association changed before deletion")
        self.paths.conversation_path(association.conversation_id).unlink()

    def locate_session(self, conversation_id: str) -> str:
        path = self.paths.conversation_path(conversation_id)
        if not path.is_file() or _is_symlink_or_reparse(path):
            raise SessionUnavailable("association is unavailable")
        return str(self.paths.session_path(conversation_id).resolve(strict=False))


def _association_from_payload(payload: Any) -> ConversationAssociation:
    if not isinstance(payload, dict) or set(payload) != {
        "schema_version",
        "conversation_id",
        "session_path",
        "prime_session_id",
        "working_directory",
        "runtime_id",
        "binding",
        "requested_initial_model",
        "requested_initial_reasoning",
        "created_at_utc",
    }:
        raise ValueError("association keys are invalid")
    if type(payload["schema_version"]) is not int or payload["schema_version"] != ASSOCIATION_SCHEMA_VERSION:
        raise ValueError("association schema version is unsupported")
    binding_payload = payload["binding"]
    if not isinstance(binding_payload, dict) or set(binding_payload) != {
        "profile",
        "host_generation_id",
        "rhino_document_serial",
        "route_process_id",
    }:
        raise ValueError("binding is invalid")
    binding = RookBinding(**binding_payload)
    required_strings = (
        "conversation_id",
        "session_path",
        "prime_session_id",
        "working_directory",
        "runtime_id",
        "created_at_utc",
    )
    if any(not isinstance(payload[key], str) or not payload[key] for key in required_strings):
        raise ValueError("association string field is invalid")
    for key in ("requested_initial_model", "requested_initial_reasoning"):
        if payload[key] is not None and not isinstance(payload[key], str):
            raise ValueError("association disclosure field is invalid")
    return ConversationAssociation(binding=binding, **{key: value for key, value in payload.items() if key != "binding"})
