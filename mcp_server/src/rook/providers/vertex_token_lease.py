"""Bounded, generation-aware Vertex access-token leases for RookVision."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
import math
import time
import threading
from typing import Callable

from .vertex_auth import (
    VERTEX_SCOPE,
    VertexAuthError,
    VertexRecord,
    VertexRuntimeArguments,
    VertexStore,
    VertexMode,
    _PROJECT_ID,
    _REGION,
)


VERTEX_IMAGE_MODEL_KEY = "vertex_ai/gemini-3.1-flash-image"
VERTEX_IMAGE_LOCATION = "global"
VERTEX_VIDEO_MODEL_KEY = "vertex_ai/veo-3.1-fast-generate-001"
VERTEX_VIDEO_LOCATION = "us-central1"
from .vertex_workforce_contract import WorkforceActiveRecord, WorkforceCredentialContext, opaque, user_project
from .vertex_workforce_store import VertexWorkforceStore
from .vertex_backend import refresh_vertex_workforce
from .vertex_entra import EntraSessionAdapter

TOKEN_REUSE_SLACK_SECONDS = 300
TOKEN_TRANSPORT_TIMEOUT_SECONDS = 20.0
TOKEN_ISSUANCE_TIMEOUT_SECONDS = 30.0

_MESSAGES = {
    "vertex_client_upgrade_required": "Update Rook before using firm sign-in for Google media.",
    "vertex_restart_required": "Restart required: a previous managed process could not be retired.",
    "vertex_firm_sign_in_required": "Sign in with your firm to renew authorization.",
    "vertex_workforce_exchange_denied": "Google denied the firm's identity exchange.",
    "vertex_refresh_stale": "A stale firm refresh was refused.",
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
    principal_id: str | None = None
    connection_fingerprint: str | None = None
    workforce_pool_user_project: str | None = None
    quota_project_id: str | None = None

    def __post_init__(self):
        if type(self.binding_version) is not int or self.binding_version not in (1, 2):
            raise ValueError("Invalid binding")
        opaque(self.authorization_generation)
        if type(self.project_id) is not str or not _PROJECT_ID.fullmatch(self.project_id) or type(self.location) is not str or not _REGION.fullmatch(self.location) or type(self.model_id) is not str or not 0 < len(self.model_id) <= 256:
            raise ValueError("Invalid binding")
        if self.binding_version == 1:
            if any(value is not None for value in (self.principal_id, self.connection_fingerprint, self.workforce_pool_user_project, self.quota_project_id)):
                raise ValueError("Invalid binding")
        else:
            opaque(self.principal_id)
            if type(self.connection_fingerprint) is not str or len(self.connection_fingerprint) != 64 or any(char not in '0123456789abcdef' for char in self.connection_fingerprint):
                raise ValueError("Invalid binding")
            user_project(self.workforce_pool_user_project)
            if self.quota_project_id is not None:
                user_project(self.quota_project_id)

    def to_wire(self):
        from dataclasses import asdict
        value = asdict(self)
        if self.binding_version == 1:
            for key in ('principal_id', 'connection_fingerprint', 'workforce_pool_user_project', 'quota_project_id'):
                value.pop(key)
        return value

    @classmethod
    def from_wire(cls, value):
        keys = {"binding_version", "authorization_generation", "project_id", "location", "model_id"}
        if isinstance(value, dict) and type(value.get('binding_version')) is int and value['binding_version'] == 2:
            keys |= {'principal_id', 'connection_fingerprint', 'workforce_pool_user_project', 'quota_project_id'}
        if not isinstance(value, dict) or set(value) != keys:
            raise ValueError("Invalid binding")
        try:
            return cls(**value)
        except VertexAuthError:
            raise ValueError("Invalid binding") from None


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
    contract_version: int = 1
    quota_project_id: str | None = None

    def to_wire(self):
        from dataclasses import asdict
        value = asdict(self)
        value['binding'] = self.binding.to_wire()
        if self.contract_version == 1:
            value.pop('contract_version')
            value.pop('quota_project_id')
        return value


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
    """Issue bounded leases; revoked threads may settle but cannot install them."""
    def __init__(self, *, store=None, refresh_access_token=None, monotonic=time.monotonic,
                 unix_time=time.time, workforce_store=None, workforce_refresher=None, entra=None):
        self._store = store
        self._refresh_access_token = refresh_access_token or globals()['refresh_access_token']
        self._monotonic, self._unix_time = monotonic, unix_time
        self._refresh_lock = asyncio.Lock()
        self._cached_lease = None
        self._workforce_store = workforce_store
        self._workforce_refresher = workforce_refresher or refresh_vertex_workforce
        self._entra = entra or EntraSessionAdapter(monotonic=monotonic, unix_time=unix_time)
        self._workers = set()

    def _settled(self, worker):
        self._workers.discard(worker)
        if not worker.cancelled():
            worker.exception()  # Observe a revoked worker's eventual fixed failure.

    async def acquire(self, model, location=VERTEX_IMAGE_LOCATION, expected_binding=None, *, contract_version=1):
        if type(contract_version) is not int or contract_version not in (1, 2):
            raise ValueError('Invalid contract version')
        deadline = self._monotonic() + TOKEN_ISSUANCE_TIMEOUT_SECONDS
        remaining = deadline - self._monotonic()
        if not math.isfinite(remaining) or remaining <= 0:
            raise self._error('vertex_token_issuance_timeout')
        try:
            return await asyncio.wait_for(self._acquire_admitted(model, location, expected_binding, deadline, contract_version), timeout=remaining)
        except asyncio.TimeoutError:
            raise self._error('vertex_token_issuance_timeout') from None
        except VertexAuthError:
            raise
        except Exception:
            raise self._error('vertex_token_issuance_failed') from None

    async def _acquire_admitted(self, model, location, expected_binding, deadline, contract_version):
        if model not in {VERTEX_IMAGE_MODEL_KEY, VERTEX_VIDEO_MODEL_KEY}:
            raise self._error('vertex_image_model_unsupported')
        store = self._store or VertexStore.production()
        record = self._read_current_record(store)
        self._require_record(record)
        self._admit(record, model, location, expected_binding, contract_version)
        async with self._refresh_lock:
            record = self._read_current_record(store)
            self._require_record(record)
            self._admit(record, model, location, expected_binding, contract_version)
            revoked = threading.Event()
            def check_worker():
                if revoked.is_set():
                    raise self._error('vertex_authorization_changed')
                if self._monotonic() >= deadline:
                    raise self._error('vertex_token_issuance_timeout')
            check_worker()
            cached = self._cached_lease
            binding = self._binding(record, model, location)
            if cached is not None and cached.generation == record.generation and cached.project_id == record.project_id and self._binding(record, cached.binding.model_id, cached.location) == cached.binding and cached.expires_at_unix_seconds - self._unix_time() > TOKEN_REUSE_SLACK_SECONDS:
                return replace(cached, location=location, binding=binding, contract_version=contract_version)
            try:
                if isinstance(record, WorkforceActiveRecord):
                    def refresh():
                        return self._workforce_refresher(store=self._workforce_store or VertexWorkforceStore(store, monotonic=self._monotonic, unix_time=self._unix_time), entra=self._entra, expected_generation=record.generation, deadline=deadline, cancel_check=check_worker, monotonic=self._monotonic)
                else:
                    runtime = store.resolve_runtime()
                    if (runtime.generation, runtime.project_id, runtime.region) != (record.generation, record.project_id, record.region):
                        raise self._error('vertex_authorization_changed')
                    def refresh():
                        check_worker()
                        result = self._refresh_access_token(runtime, deadline, self._monotonic)
                        check_worker()
                        return result
                worker = asyncio.create_task(asyncio.to_thread(refresh))
                self._workers.add(worker)
                worker.add_done_callback(self._settled)
                refreshed = await asyncio.shield(worker)
                check_worker()
                current = self._read_current_record(store)
                if current is None or self._binding(current, model, location) != binding or current.region != record.region:
                    raise self._error('vertex_authorization_changed')
                self._admit(current, model, location, expected_binding, contract_version)
                if isinstance(record, WorkforceActiveRecord):
                    if not isinstance(refreshed, WorkforceCredentialContext) or (refreshed.generation, refreshed.principal_id, refreshed.connection_fingerprint, refreshed.project_id, refreshed.workforce_pool_user_project, refreshed.quota_project_id) != (binding.authorization_generation, binding.principal_id, binding.connection_fingerprint, binding.project_id, binding.workforce_pool_user_project, binding.quota_project_id):
                        raise self._error('vertex_authorization_changed')
                    token = RefreshedVertexAccessToken(refreshed.access_token, refreshed.expires_at)
                else:
                    token = refreshed
                self._validate_refreshed(token)
                lease = VertexTokenLease(token.access_token, token.expires_at_unix_seconds, current.project_id, location, current.generation, binding, contract_version, binding.quota_project_id)
                check_worker()
                self._cached_lease = lease
                return lease
            except BaseException:
                revoked.set()  # Must precede async lock release, including wait_for cancellation.
                self._cached_lease = None
                raise

    def _require_record(self, record):
        if record is None:
            self._cached_lease = None
            raise self._error('vertex_signed_out')

    def _read_current_record(self, store):
        try:
            record = store.read()
        except Exception:
            self._cached_lease = None
            raise
        if record is None or self._cached_lease is not None and self._cached_lease.generation != record.generation:
            self._cached_lease = None
        return record

    @staticmethod
    def _binding(record, model, location):
        if isinstance(record, WorkforceActiveRecord):
            return VertexMediaBinding(2, record.generation, record.project_id, location, model, record.principal_id, record.connection_fingerprint, record.settings.workforce_pool_user_project, record.settings.quota_project_id)
        return VertexMediaBinding(1, record.generation, record.project_id, location, model)

    def _admit(self, record, model, location, expected, contract_version=2):
        if isinstance(record, WorkforceActiveRecord):
            if contract_version != 2:
                self._cached_lease = None
                raise self._error('vertex_client_upgrade_required')
            if record.chirp_retirement_pending:
                self._cached_lease = None
                raise self._error('vertex_restart_required')
        if expected is not None and expected != self._binding(record, model, location):
            self._cached_lease = None
            raise self._error('vertex_authorization_changed')
        supported = model == VERTEX_IMAGE_MODEL_KEY and location == VERTEX_IMAGE_LOCATION or model == VERTEX_VIDEO_MODEL_KEY and location == VERTEX_VIDEO_LOCATION and record.region == location
        if not supported:
            raise self._error('vertex_model_region_unsupported')

    def validate_binding(self, binding):
        record = self._read_current_record(self._store or VertexStore.production())
        if record is None:
            raise self._error('vertex_authorization_changed')
        self._admit(record, binding.model_id, binding.location, binding)

    def _validate_refreshed(self, refreshed):
        if not isinstance(refreshed, RefreshedVertexAccessToken) or not isinstance(refreshed.access_token, str) or not refreshed.access_token or type(refreshed.expires_at_unix_seconds) is not int or refreshed.expires_at_unix_seconds <= self._unix_time():
            raise self._error('vertex_token_issuance_failed')

    @staticmethod
    def _error(code):
        return VertexAuthError(code, _MESSAGES[code])
