"""Vertex AI authorization storage and local model admission."""

from __future__ import annotations

import base64
import ctypes
import json
import os
import re
import secrets
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any
from ctypes import wintypes


_VERTEX_PREFIX = "vertex_ai/"
_VERTEX_GEMINI_MODEL = re.compile(r"gemini-[a-z0-9][a-z0-9._-]{0,127}\Z")
_UNSUPPORTED_MODEL_MESSAGE = (
    "This release supports only Gemini publisher models on Vertex AI "
    "(vertex_ai/gemini-*)."
)
_GENERATION = re.compile(r"[0-9a-f]{32}\Z")
_PROJECT_ID = re.compile(r"[a-z][a-z0-9-]{4,28}[a-z0-9]\Z")
_REGION = re.compile(r"(?:global|[a-z][a-z0-9]*(?:-[a-z0-9]+)+)\Z")
_RECORD_FIELDS = frozenset(
    {
        "schema_version",
        "generation",
        "mode",
        "project_id",
        "region",
        "oauth_ciphertext",
        "service_account_path",
    }
)
_AUTHORIZED_USER_FIELDS = frozenset(
    {"type", "client_id", "client_secret", "refresh_token"}
)
_DPAPI_ENTROPY = b"BringFire.Rook.VertexAuth.v1"
_CRYPTPROTECT_UI_FORBIDDEN = 0x1

VERTEX_SCHEMA_VERSION = 1
VERTEX_SCOPE = "https://www.googleapis.com/auth/cloud-platform"
VERTEX_MUTEX_NAME = r"Local\BringFire.Rook.VertexAuth.v1"
VERTEX_MUTEX_TIMEOUT_MS = 10_000

_WAIT_OBJECT_0 = 0x00000000
_WAIT_ABANDONED = 0x00000080
_WAIT_TIMEOUT = 0x00000102
_WAIT_FAILED = 0xFFFFFFFF


class VertexAuthError(RuntimeError):
    """Bounded public failure from the Vertex authorization boundary."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.public_message = message
        super().__init__(message)


class VertexMode(str, Enum):
    OAUTH = "oauth"
    ADC = "adc"
    SERVICE_ACCOUNT = "service_account"


@dataclass(frozen=True)
class VertexRuntimeArguments:
    generation: str
    project_id: str
    region: str
    vertex_credentials: dict[str, str] | str | None


class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
    ]


def _data_blob(value: bytes) -> tuple[_DataBlob, ctypes.Array]:
    buffer = ctypes.create_string_buffer(value, len(value))
    return (
        _DataBlob(
            cbData=len(value),
            pbData=ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)),
        ),
        buffer,
    )


class _DpapiProtector:
    def _transform(self, value: bytes, *, protect: bool) -> bytes:
        if os.name != "nt" or not isinstance(value, bytes) or not value:
            raise _invalid_record()
        crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        function = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
        if protect:
            function.argtypes = [
                ctypes.POINTER(_DataBlob),
                wintypes.LPCWSTR,
                ctypes.POINTER(_DataBlob),
                ctypes.c_void_p,
                ctypes.c_void_p,
                wintypes.DWORD,
                ctypes.POINTER(_DataBlob),
            ]
        else:
            function.argtypes = [
                ctypes.POINTER(_DataBlob),
                ctypes.c_void_p,
                ctypes.POINTER(_DataBlob),
                ctypes.c_void_p,
                ctypes.c_void_p,
                wintypes.DWORD,
                ctypes.POINTER(_DataBlob),
            ]
        function.restype = wintypes.BOOL
        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        kernel32.LocalFree.restype = ctypes.c_void_p
        input_blob, input_buffer = _data_blob(value)
        entropy_blob, entropy_buffer = _data_blob(_DPAPI_ENTROPY)
        output_blob = _DataBlob()
        if not function(
            ctypes.byref(input_blob),
            None,
            ctypes.byref(entropy_blob),
            None,
            None,
            _CRYPTPROTECT_UI_FORBIDDEN,
            ctypes.byref(output_blob),
        ):
            raise _invalid_record()
        # Keep both source buffers alive through the native call.
        del input_buffer, entropy_buffer
        try:
            return ctypes.string_at(output_blob.pbData, output_blob.cbData)
        finally:
            kernel32.LocalFree(output_blob.pbData)

    def protect(self, plaintext: bytes) -> bytes:
        return self._transform(plaintext, protect=True)

    def unprotect(self, ciphertext: bytes) -> bytes:
        return self._transform(ciphertext, protect=False)


def _invalid_record() -> VertexAuthError:
    return VertexAuthError(
        "vertex_request_failed",
        "Vertex authorization is unavailable because its local configuration is invalid.",
    )


@dataclass(frozen=True)
class VertexRecord:
    schema_version: int
    generation: str
    mode: VertexMode
    project_id: str
    region: str
    oauth_ciphertext: str | None
    service_account_path: str | None

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != VERTEX_SCHEMA_VERSION:
            raise _invalid_record()
        if not isinstance(self.generation, str) or not _GENERATION.fullmatch(self.generation):
            raise _invalid_record()
        try:
            mode = self.mode if isinstance(self.mode, VertexMode) else VertexMode(self.mode)
        except (TypeError, ValueError) as exc:
            raise _invalid_record() from exc
        object.__setattr__(self, "mode", mode)
        if not isinstance(self.project_id, str) or not _PROJECT_ID.fullmatch(self.project_id):
            raise _invalid_record()
        if not isinstance(self.region, str) or not _REGION.fullmatch(self.region):
            raise _invalid_record()

        if mode is VertexMode.OAUTH:
            if (
                not isinstance(self.oauth_ciphertext, str)
                or not self.oauth_ciphertext
                or self.service_account_path is not None
            ):
                raise _invalid_record()
            return

        if self.oauth_ciphertext is not None:
            raise _invalid_record()
        if mode is VertexMode.ADC:
            if self.service_account_path is not None:
                raise _invalid_record()
            return

        if not isinstance(self.service_account_path, str):
            raise _invalid_record()
        service_path = Path(self.service_account_path)
        if not service_path.is_absolute() or not service_path.is_file():
            raise _invalid_record()
        object.__setattr__(self, "service_account_path", str(service_path.resolve()))

    def to_json_object(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "generation": self.generation,
            "mode": self.mode.value,
            "project_id": self.project_id,
            "region": self.region,
            "oauth_ciphertext": self.oauth_ciphertext,
            "service_account_path": self.service_account_path,
        }

    @classmethod
    def from_json_object(cls, value: object) -> "VertexRecord":
        if not isinstance(value, dict) or set(value) != _RECORD_FIELDS:
            raise _invalid_record()
        try:
            return cls(**value)
        except TypeError as exc:
            raise _invalid_record() from exc


class _WindowsNamedMutex:
    def __init__(self, name: str, timeout_ms: int):
        if (
            not isinstance(name, str)
            or not name
            or not isinstance(timeout_ms, int)
            or timeout_ms < 0
        ):
            raise _invalid_record()
        self._name = name
        self._timeout_ms = timeout_ms
        self._handle: int | None = None
        self.was_abandoned = False

    def __enter__(self) -> "_WindowsNamedMutex":
        if os.name != "nt":
            raise VertexAuthError("vertex_request_failed", "Vertex authorization requires Windows.")
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel32.WaitForSingleObject.restype = wintypes.DWORD
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        handle = kernel32.CreateMutexW(None, False, self._name)
        if not handle:
            raise VertexAuthError(
                "vertex_request_failed",
                "Vertex authorization lock is unavailable.",
            )
        self._handle = int(handle)
        wait_result = kernel32.WaitForSingleObject(handle, self._timeout_ms)
        if wait_result == _WAIT_OBJECT_0:
            return self
        if wait_result == _WAIT_ABANDONED:
            self.was_abandoned = True
            return self
        kernel32.CloseHandle(handle)
        self._handle = None
        if wait_result == _WAIT_TIMEOUT:
            raise VertexAuthError("vertex_request_failed", "Vertex authorization is busy.")
        if wait_result == _WAIT_FAILED:
            raise VertexAuthError("vertex_request_failed", "Vertex authorization lock failed.")
        raise VertexAuthError(
            "vertex_request_failed",
            "Vertex authorization lock returned an invalid state.",
        )

    def __exit__(self, exc_type, exc, traceback) -> None:
        handle = self._handle
        self._handle = None
        if handle is None:
            return
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.ReleaseMutex.argtypes = [wintypes.HANDLE]
        kernel32.ReleaseMutex.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        try:
            kernel32.ReleaseMutex(handle)
        finally:
            kernel32.CloseHandle(handle)


class VertexStore:
    def __init__(
        self,
        path: Path | str,
        *,
        protector: object | None = None,
        mutex_name: str = VERTEX_MUTEX_NAME,
        mutex_timeout_ms: int = VERTEX_MUTEX_TIMEOUT_MS,
    ):
        self.path = Path(path)
        self._protector = _DpapiProtector() if protector is None else protector
        self._mutex_name = mutex_name
        self._mutex_timeout_ms = mutex_timeout_ms

    @classmethod
    def production(cls) -> "VertexStore":
        local_appdata = os.environ.get("LOCALAPPDATA")
        if not local_appdata:
            raise VertexAuthError(
                "vertex_request_failed",
                "Vertex authorization storage is unavailable.",
            )
        return cls(Path(local_appdata) / "Rook" / "data" / "provider_auth" / "vertex.json")

    def read(self) -> VertexRecord | None:
        return self._read_unlocked()

    def protect_authorized_user(self, credentials: object) -> str:
        normalized = _authorized_user(credentials)
        plaintext = json.dumps(
            normalized,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        try:
            protected = self._protector.protect(plaintext)
            return base64.b64encode(protected).decode("ascii")
        except VertexAuthError:
            raise
        except Exception as exc:
            raise _invalid_record() from exc

    def resolve_runtime(self) -> VertexRuntimeArguments:
        record = self.read()
        if record is None:
            raise VertexAuthError(
                "vertex_signed_out",
                "Vertex AI is not configured for this Windows user.",
            )
        credentials: dict[str, str] | str | None
        if record.mode is VertexMode.OAUTH:
            try:
                protected = base64.b64decode(record.oauth_ciphertext, validate=True)
                plaintext = self._protector.unprotect(protected)
                credentials = _authorized_user(json.loads(plaintext.decode("utf-8")))
            except VertexAuthError:
                raise
            except Exception as exc:
                raise _invalid_record() from exc
        elif record.mode is VertexMode.ADC:
            credentials = None
        else:
            service_path = Path(record.service_account_path)
            if not service_path.is_absolute() or not service_path.is_file():
                raise _invalid_record()
            credentials = str(service_path.resolve())
        return VertexRuntimeArguments(
            generation=record.generation,
            project_id=record.project_id,
            region=record.region,
            vertex_credentials=credentials,
        )

    def _read_unlocked(self) -> VertexRecord | None:
        if not self.path.exists():
            return None
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            return VertexRecord.from_json_object(payload)
        except VertexAuthError:
            raise
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise _invalid_record() from exc

    def replace(self, record: VertexRecord) -> VertexRecord:
        return self._replace(record, fail_before_replace=False)

    def replace_for_test(
        self,
        record: VertexRecord,
        *,
        fail_before_replace: bool,
    ) -> VertexRecord:
        return self._replace(record, fail_before_replace=fail_before_replace)

    def _replace(self, record: VertexRecord, *, fail_before_replace: bool) -> VertexRecord:
        if not isinstance(record, VertexRecord):
            raise _invalid_record()
        temp_path: Path | None = None
        try:
            with _WindowsNamedMutex(self._mutex_name, self._mutex_timeout_ms):
                self._read_unlocked()
                committed = VertexRecord.from_json_object(
                    {**record.to_json_object(), "generation": secrets.token_hex(16)}
                )
                self.path.parent.mkdir(parents=True, exist_ok=True)
                descriptor, temp_name = tempfile.mkstemp(
                    prefix=f"{self.path.name}.",
                    suffix=".tmp",
                    dir=str(self.path.parent),
                )
                temp_path = Path(temp_name)
                payload = (
                    json.dumps(
                        committed.to_json_object(),
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    + "\n"
                ).encode("utf-8")
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
                if fail_before_replace:
                    raise OSError("injected failure before atomic replace")
                os.replace(temp_path, self.path)
                temp_path = None
                return committed
        except VertexAuthError:
            raise
        except OSError as exc:
            raise VertexAuthError(
                "vertex_request_failed",
                "Vertex authorization could not be saved.",
            ) from exc
        finally:
            if temp_path is not None:
                try:
                    temp_path.unlink(missing_ok=True)
                except OSError:
                    pass


def vertex_gemini_model_name(model: object) -> str | None:
    """Return the provider-relative Gemini model or reject other Vertex families."""

    if not isinstance(model, str) or not model.startswith(_VERTEX_PREFIX):
        return None
    publisher_model = model[len(_VERTEX_PREFIX) :]
    if _VERTEX_GEMINI_MODEL.fullmatch(publisher_model):
        return publisher_model
    raise VertexAuthError("vertex_model_family_unsupported", _UNSUPPORTED_MODEL_MESSAGE)


def _authorized_user(value: object) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) != _AUTHORIZED_USER_FIELDS:
        raise _invalid_record()
    if value.get("type") != "authorized_user":
        raise _invalid_record()
    if any(
        not isinstance(value.get(field), str) or not value[field]
        for field in _AUTHORIZED_USER_FIELDS
    ):
        raise _invalid_record()
    return {field: value[field] for field in sorted(_AUTHORIZED_USER_FIELDS)}


def apply_vertex_litellm_arguments(
    model: object,
    kwargs: dict[str, Any],
    *,
    store: VertexStore | None = None,
) -> dict[str, Any]:
    result = dict(kwargs)
    publisher_model = vertex_gemini_model_name(model)
    if publisher_model is None:
        return result
    runtime = (store or VertexStore.production()).resolve_runtime()
    result["vertex_project"] = runtime.project_id
    result["vertex_location"] = runtime.region
    if runtime.vertex_credentials is not None:
        result["vertex_credentials"] = runtime.vertex_credentials
    return result
