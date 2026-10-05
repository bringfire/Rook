"""Closed workforce configuration and private Python-owned session contracts."""
from __future__ import annotations

from dataclasses import dataclass, field, fields
import json
import math
import re
from typing import Any
from uuid import UUID

from .vertex_auth import VertexAuthError, VertexMode, VertexRecord, _PROJECT_ID, _REGION

IMPORT_LIMIT = 64 * 1024
CACHE_LIMIT = 256 * 1024
STORE_LIMIT = 512 * 1024
TOKEN_LIMIT = 1024 * 1024
_IDENTIFIER = re.compile(r"[a-z][a-z0-9-]{2,30}[a-z0-9]\Z")
_OPAQUE = re.compile(r"[0-9a-f]{32}\Z")
_FINGERPRINT = re.compile(r"[0-9a-f]{64}\Z")


def auth_error(code: str = "vertex_request_failed") -> VertexAuthError:
    messages = {
        "vertex_request_failed": "Firm authorization configuration is invalid or unavailable.",
        "vertex_authorization_changed": "Firm authorization changed. Sign in again deliberately.",
        "vertex_refresh_stale": "A stale firm refresh was refused.",
        "vertex_token_issuance_timeout": "Firm authorization timed out.",
        "vertex_restart_required": "Restart required: a previous managed process could not be retired.",
        "vertex_firm_sign_in_required": "Sign in with your firm to renew authorization.",
        "vertex_text_federation_unsupported": "Firm sign-in supports Google images and videos; Vertex text and Chirp require another connection.",
        "vertex_workforce_exchange_denied": "Google denied the firm's identity exchange.",
    }
    return VertexAuthError(code, messages[code])


def bounded_text(value: object, limit: int) -> str:
    if type(value) is not str or not value:
        raise auth_error()
    try:
        if len(value.encode("utf-8")) > limit:
            raise auth_error()
    except UnicodeError:
        raise auth_error() from None
    return value


def guid(value: object) -> str:
    try:
        if type(value) is not str or str(UUID(value)) != value.lower():
            raise ValueError()
        return value.lower()
    except (ValueError, AttributeError, TypeError):
        raise auth_error() from None


def user_project(value: object) -> str:
    if type(value) is not str or not (_PROJECT_ID.fullmatch(value) or re.fullmatch(r"[1-9][0-9]{5,31}", value)):
        raise auth_error()
    return value


def opaque(value: object) -> str:
    if type(value) is not str or not _OPAQUE.fullmatch(value):
        raise auth_error()
    return value


def json_object(raw: bytes, limit: int) -> dict[str, Any]:
    if type(raw) is not bytes or not raw or len(raw) > limit:
        raise auth_error()
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise auth_error()
            result[key] = value
        return result
    def invalid_constant(_):
        raise auth_error()
    try:
        result = json.loads(raw.decode("utf-8"), object_pairs_hook=unique,
                            parse_constant=invalid_constant)
        if not isinstance(result, dict):
            raise auth_error()
        return result
    except (UnicodeError, ValueError, RecursionError):
        raise auth_error() from None


@dataclass(frozen=True, repr=False)
class FirmSettings:
    schema_version: int
    label: str
    entra_tenant_id: str
    entra_client_id: str
    organization_id: str
    pool_id: str
    provider_id: str
    project_id: str
    workforce_pool_user_project: str
    quota_project_id: str | None
    region: str
    exchange: str = "sts_id_token_v1"

    def __post_init__(self):
        if type(self.schema_version) is not int or self.schema_version != 2 or self.exchange != "sts_id_token_v1":
            raise auth_error()
        bounded_text(self.label, 160)
        if any(ord(char) < 32 for char in self.label):
            raise auth_error()
        object.__setattr__(self, "entra_tenant_id", guid(self.entra_tenant_id))
        object.__setattr__(self, "entra_client_id", guid(self.entra_client_id))
        if type(self.organization_id) is not str or not re.fullmatch(r"[1-9][0-9]{0,31}", self.organization_id):
            raise auth_error()
        if any(type(value) is not str or not _IDENTIFIER.fullmatch(value) for value in (self.pool_id, self.provider_id)):
            raise auth_error()
        if type(self.project_id) is not str or not _PROJECT_ID.fullmatch(self.project_id):
            raise auth_error()
        user_project(self.workforce_pool_user_project)
        if self.quota_project_id is not None:
            user_project(self.quota_project_id)
        if type(self.region) is not str or not _REGION.fullmatch(self.region):
            raise auth_error()

    @property
    def audience(self):
        return f"//iam.googleapis.com/locations/global/workforcePools/{self.pool_id}/providers/{self.provider_id}"

    @property
    def authority(self):
        return f"https://login.microsoftonline.com/{self.entra_tenant_id}"


def parse_firm_settings(raw: bytes) -> FirmSettings:
    value = json_object(raw, IMPORT_LIMIT)
    if set(value) != {item.name for item in fields(FirmSettings)}:
        raise auth_error()
    return FirmSettings(**value)


@dataclass(frozen=True, repr=False)
class PrivatePrincipal:
    tid: str
    oid: str
    msal_account_key: str

    def __post_init__(self):
        object.__setattr__(self, "tid", guid(self.tid))
        object.__setattr__(self, "oid", guid(self.oid))
        bounded_text(self.msal_account_key, 512)


@dataclass(frozen=True, repr=False)
class VerifiedEntraAssertion:
    assertion: str
    principal: PrivatePrincipal
    expires_at: int

    def __post_init__(self):
        bounded_text(self.assertion, TOKEN_LIMIT)
        if not isinstance(self.principal, PrivatePrincipal) or type(self.expires_at) is not int or self.expires_at <= 0:
            raise auth_error()


@dataclass(frozen=True, repr=False)
class EntraSessionCandidate:
    principal: PrivatePrincipal
    serialized_cache: str
    assertion: VerifiedEntraAssertion
    operation_deadline: float | None = None

    def __post_init__(self):
        json_object(bounded_text(self.serialized_cache, CACHE_LIMIT).encode(), CACHE_LIMIT)
        if not isinstance(self.assertion, VerifiedEntraAssertion) or self.principal != self.assertion.principal:
            raise auth_error()
        if self.operation_deadline is not None and (type(self.operation_deadline) not in (float, int) or not math.isfinite(self.operation_deadline)):
            raise auth_error()


@dataclass(frozen=True, repr=False)
class WorkforceExchangeResult:
    access_token: str
    expires_at: int
    project_id: str
    workforce_pool_user_project: str
    quota_project_id: str | None

    def __post_init__(self):
        bounded_text(self.access_token, TOKEN_LIMIT)
        if type(self.expires_at) is not int or self.expires_at <= 0:
            raise auth_error()
        user_project(self.project_id)
        user_project(self.workforce_pool_user_project)
        if self.quota_project_id is not None:
            user_project(self.quota_project_id)


@dataclass(frozen=True, repr=False)
class WorkforceCredentialContext(WorkforceExchangeResult):
    generation: str
    principal_id: str
    connection_fingerprint: str

    def __post_init__(self):
        super().__post_init__()
        opaque(self.generation)
        opaque(self.principal_id)
        if type(self.connection_fingerprint) is not str or not _FINGERPRINT.fullmatch(self.connection_fingerprint):
            raise auth_error()


@dataclass(frozen=True)
class ActivationTicket:
    pending_revision: str
    authorization_epoch: str

    def __post_init__(self):
        opaque(self.pending_revision)
        opaque(self.authorization_epoch)


@dataclass(frozen=True, repr=False)
class WorkforceActiveRecord:
    settings: FirmSettings
    generation: str
    principal_id: str
    connection_fingerprint: str
    protected_session: str
    cache_revision: int
    chirp_retirement_pending: bool

    @property
    def mode(self):
        return VertexMode.WORKFORCE

    @property
    def project_id(self):
        return self.settings.project_id

    @property
    def region(self):
        return self.settings.region


ActiveVertexAuthorizationSnapshot = VertexRecord | WorkforceActiveRecord


@dataclass(frozen=True)
class FirmSignInCheckResult:
    state: str
    code: str | None
    generation: str | None
    contract_version: int = field(default=2, init=False)
    check_scope: str = field(default="identity_exchange", init=False)
    image_access: str = field(default="unverified", init=False)
    video_access: str = field(default="unverified", init=False)
    billing: str = field(default="unverified", init=False)
    quota: str = field(default="unverified", init=False)
