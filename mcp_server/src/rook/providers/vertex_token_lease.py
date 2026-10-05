"""Bounded, generation-aware Vertex access-token leases for RookVision."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
import math
import time
from typing import Callable

from .vertex_auth import (
    VERTEX_SCOPE,
    VertexAuthError,
    VertexRecord,
    VertexRuntimeArguments,
    VertexStore,
)


VERTEX_IMAGE_MODEL_KEY = "vertex_ai/gemini-3.1-flash-image"
VERTEX_IMAGE_LOCATION = "global"
VERTEX_VIDEO_MODEL_KEY = "vertex_ai/veo-3.1-fast-generate-001"
VERTEX_VIDEO_LOCATION = "us-central1"
TOKEN_REUSE_SLACK_SECONDS = 300
TOKEN_TRANSPORT_TIMEOUT_SECONDS = 20.0
TOKEN_ISSUANCE_TIMEOUT_SECONDS = 30.0

_MESSAGES = {
    "vertex_image_model_unsupported": "The selected Vertex image model is unsupported.",
    "vertex_model_region_unsupported": (
        "The selected Vertex media model location is unsupported."
    ),
    "vertex_signed_out": "Vertex AI is not configured for this Windows user.",
    "vertex_authorization_changed": (
        "Vertex authorization changed during token issuance."
    ),
    "vertex_auth_dependency_missing": (
        "The installed Google authorization dependency is unavailable."
    ),
    "vertex_authorization_revoked": "Google authorization must be renewed.",
    "vertex_adc_unavailable": "Application Default Credentials are unavailable.",
    "vertex_service_account_unavailable": (
        "The selected service account is unavailable."
    ),
    "vertex_token_issuance_timeout": "Vertex token issuance timed out.",
    "vertex_token_issuance_failed": "Vertex token issuance failed.",
}


@dataclass(frozen=True)
class VertexMediaBinding:
    binding_version: int
    authorization_generation: str
    project_id: str
    location: str
    model_id: str

    @classmethod
    def from_wire(cls, value):
        keys = {"binding_version", "authorization_generation", "project_id", "location", "model_id"}
        if not isinstance(value, dict) or set(value) != keys or type(value["binding_version"]) is not int or value["binding_version"] != 1:
            raise ValueError("Invalid binding")
        if any(type(value[k]) is not str or not value[k] or len(value[k]) > 256 for k in keys - {"binding_version"}):
            raise ValueError("Invalid binding")
        return cls(**value)


@dataclass(frozen=True)
class RefreshedVertexAccessToken:
    access_token: str = field(repr=False)
    expires_at_unix_seconds: int


@dataclass(frozen=True)
class VertexTokenLease:
    access_token: str = field(repr=False)
    expires_at_unix_seconds: int
    project_id: str
    location: str
    generation: str
    binding: VertexMediaBinding


class _DeadlineRequest:
    """Apply one aggregate monotonic deadline to every google-auth request."""

    def __init__(self, delegate: object, deadline: float, monotonic: Callable[[], float]):
        self._delegate = delegate
        self._deadline = deadline
        self._monotonic = monotonic

    def __call__(
        self,
        url: str,
        method: str = "GET",
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
        **kwargs,
    ):
        del timeout
        remaining = self._deadline - self._monotonic()
        if not math.isfinite(remaining) or remaining <= 0:
            raise VertexAuthError(
                "vertex_token_issuance_timeout",
                _MESSAGES["vertex_token_issuance_timeout"],
            )
        try:
            return self._delegate(
                url=url,
                method=method,
                body=body,
                headers=headers,
                timeout=min(TOKEN_TRANSPORT_TIMEOUT_SECONDS, remaining),
                **kwargs,
            )
        except Exception as exc:
            if _is_transport_timeout(exc):
                raise VertexAuthError(
                    "vertex_token_issuance_timeout",
                    _MESSAGES["vertex_token_issuance_timeout"],
                ) from exc
            raise


def _is_transport_timeout(error: BaseException) -> bool:
    try:
        from requests.exceptions import Timeout as RequestsTimeout
    except ImportError:
        timeout_types: tuple[type[BaseException], ...] = (TimeoutError,)
    else:
        timeout_types = (TimeoutError, RequestsTimeout)

    pending = [error]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, timeout_types):
            return True
        if isinstance(current.__cause__, BaseException):
            pending.append(current.__cause__)
        if isinstance(current.__context__, BaseException):
            pending.append(current.__context__)
        pending.extend(value for value in current.args if isinstance(value, BaseException))
    return False


def _load_google_credentials(
    runtime: VertexRuntimeArguments,
) -> tuple[object, str, object]:
    try:
        import google.auth
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials as UserCredentials
        from google.oauth2.service_account import Credentials as ServiceCredentials
    except ImportError as exc:
        raise VertexAuthError(
            "vertex_auth_dependency_missing",
            _MESSAGES["vertex_auth_dependency_missing"],
        ) from exc

    credentials = runtime.vertex_credentials
    if isinstance(credentials, dict):
        resolved = UserCredentials.from_authorized_user_info(
            credentials,
            scopes=[VERTEX_SCOPE],
        )
        failure_code = "vertex_authorization_revoked"
    elif credentials is None:
        resolved, _ = google.auth.default(scopes=[VERTEX_SCOPE])
        failure_code = "vertex_adc_unavailable"
    else:
        resolved = ServiceCredentials.from_service_account_file(
            credentials,
            scopes=[VERTEX_SCOPE],
        )
        failure_code = "vertex_service_account_unavailable"
    return resolved, failure_code, Request()


def _credential_failure_code(runtime: VertexRuntimeArguments) -> str:
    credentials = runtime.vertex_credentials
    if isinstance(credentials, dict):
        return "vertex_authorization_revoked"
    if credentials is None:
        return "vertex_adc_unavailable"
    return "vertex_service_account_unavailable"


def _expiry_unix_seconds(expiry: object) -> int:
    if not isinstance(expiry, datetime):
        raise VertexAuthError(
            "vertex_token_issuance_failed",
            _MESSAGES["vertex_token_issuance_failed"],
        )
    normalized = expiry
    if normalized.tzinfo is None:
        normalized = normalized.replace(tzinfo=timezone.utc)
    timestamp = normalized.timestamp()
    if not math.isfinite(timestamp):
        raise VertexAuthError(
            "vertex_token_issuance_failed",
            _MESSAGES["vertex_token_issuance_failed"],
        )
    return int(timestamp)


def refresh_access_token(
    runtime: VertexRuntimeArguments,
    deadline: float,
    monotonic: Callable[[], float] = time.monotonic,
) -> RefreshedVertexAccessToken:
    """Refresh one token while sharing the caller's monotonic deadline."""

    failure_code = _credential_failure_code(runtime)
    try:
        resolved, failure_code, request = _load_google_credentials(runtime)
        resolved.refresh(_DeadlineRequest(request, deadline, monotonic))
    except VertexAuthError:
        raise
    except Exception as exc:
        raise VertexAuthError(failure_code, _MESSAGES[failure_code]) from exc

    token = getattr(resolved, "token", None)
    if not isinstance(token, str) or not token:
        raise VertexAuthError(
            "vertex_token_issuance_failed",
            _MESSAGES["vertex_token_issuance_failed"],
        )
    return RefreshedVertexAccessToken(
        access_token=token,
        expires_at_unix_seconds=_expiry_unix_seconds(getattr(resolved, "expiry", None)),
    )


class VertexTokenLeaseService:
    """Issue short-lived Vertex leases without moving credential ownership."""

    def __init__(
        self,
        *,
        store: VertexStore | None = None,
        refresh_access_token: Callable[
            [VertexRuntimeArguments, float, Callable[[], float]],
            RefreshedVertexAccessToken,
        ]
        | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        unix_time: Callable[[], float] = time.time,
    ) -> None:
        self._store = store
        self._refresh_access_token = refresh_access_token or globals()[
            "refresh_access_token"
        ]
        self._monotonic = monotonic
        self._unix_time = unix_time
        self._refresh_lock = asyncio.Lock()
        self._cached_lease: VertexTokenLease | None = None

    async def acquire(self, model: str, location: str = VERTEX_IMAGE_LOCATION, expected_binding: VertexMediaBinding | None = None) -> VertexTokenLease:
        deadline = self._monotonic() + TOKEN_ISSUANCE_TIMEOUT_SECONDS
        remaining = deadline - self._monotonic()
        if not math.isfinite(remaining) or remaining <= 0:
            raise self._error("vertex_token_issuance_timeout")
        try:
            return await asyncio.wait_for(
                self._acquire_admitted(model, location, expected_binding, deadline),
                timeout=remaining,
            )
        except asyncio.TimeoutError as exc:
            raise self._error("vertex_token_issuance_timeout") from exc
        except VertexAuthError:
            raise
        except Exception as exc:
            raise self._error("vertex_token_issuance_failed") from exc

    async def _acquire_admitted(
        self,
        model: str,
        location: str,
        expected_binding: VertexMediaBinding | None,
        deadline: float,
    ) -> VertexTokenLease:
        if model not in {VERTEX_IMAGE_MODEL_KEY, VERTEX_VIDEO_MODEL_KEY}:
            raise self._error("vertex_image_model_unsupported")

        store = self._store or VertexStore.production()
        record = self._read_current_record(store)
        self._require_record(record)
        self._admit(record, model, location, expected_binding)

        async with self._refresh_lock:
            record = self._read_current_record(store)
            self._require_record(record)
            self._admit(record, model, location, expected_binding)
            cached = self._cached_lease
            if (
                cached is not None
                and cached.generation == record.generation
                and cached.project_id == record.project_id
                and cached.expires_at_unix_seconds - self._unix_time()
                > TOKEN_REUSE_SLACK_SECONDS
            ):
                return replace(cached, location=location, binding=self._binding(record, model, location))

            try:
                runtime = store.resolve_runtime()
            except Exception:
                self._cached_lease = None
                raise
            if (
                runtime.generation != record.generation
                or runtime.project_id != record.project_id
                or runtime.region != record.region
            ):
                self._cached_lease = None
                raise self._error("vertex_authorization_changed")
            refreshed = await asyncio.to_thread(
                self._refresh_access_token,
                runtime,
                deadline,
                self._monotonic,
            )
            current = self._read_current_record(store)
            if current is None or current.generation != record.generation or current.project_id != record.project_id or current.region != record.region:
                self._cached_lease = None
                raise self._error("vertex_authorization_changed")
            self._admit(current, model, location, expected_binding)
            self._validate_refreshed(refreshed)
            lease = VertexTokenLease(
                access_token=refreshed.access_token,
                expires_at_unix_seconds=refreshed.expires_at_unix_seconds,
                project_id=current.project_id,
                location=location,
                binding=self._binding(current, model, location),
                generation=current.generation,
            )
            self._cached_lease = lease
            return lease

    def _require_record(self, record: VertexRecord | None) -> None:
        if record is not None:
            return
        self._cached_lease = None
        raise self._error("vertex_signed_out")

    def _read_current_record(self, store: VertexStore) -> VertexRecord | None:
        try:
            record = store.read()
        except Exception:
            self._cached_lease = None
            raise
        cached = self._cached_lease
        if record is None or (
            cached is not None and cached.generation != record.generation
        ):
            self._cached_lease = None
        return record

    @staticmethod
    def _binding(record, model, location):
        return VertexMediaBinding(1, record.generation, record.project_id, location, model)

    def _admit(self, record, model, location, expected):
        if expected is not None and expected != self._binding(record, model, location):
            self._cached_lease = None
            raise self._error("vertex_authorization_changed")
        supported = (model == VERTEX_IMAGE_MODEL_KEY and location == VERTEX_IMAGE_LOCATION) or (model == VERTEX_VIDEO_MODEL_KEY and location == VERTEX_VIDEO_LOCATION and record.region == location)
        if not supported:
            raise self._error("vertex_model_region_unsupported")

    def validate_binding(self, binding: VertexMediaBinding) -> None:
        record = self._read_current_record(self._store or VertexStore.production())
        if record is None:
            raise self._error("vertex_authorization_changed")
        self._admit(record, binding.model_id, binding.location, binding)

    def _validate_refreshed(self, refreshed: object) -> None:
        if (
            not isinstance(refreshed, RefreshedVertexAccessToken)
            or not isinstance(refreshed.access_token, str)
            or not refreshed.access_token
            or type(refreshed.expires_at_unix_seconds) is not int
            or refreshed.expires_at_unix_seconds <= self._unix_time()
        ):
            raise self._error("vertex_token_issuance_failed")

    @staticmethod
    def _error(code: str) -> VertexAuthError:
        return VertexAuthError(code, _MESSAGES[code])
