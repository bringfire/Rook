"""Pending/active workforce envelope around the existing Vertex DPAPI store."""
from __future__ import annotations

import base64
from contextlib import contextmanager
from dataclasses import asdict, fields, replace
import hashlib
import hmac
import json
import math
import os
import secrets
import tempfile
import time
from pathlib import Path
from typing import Callable

from .vertex_auth import VertexRecord, VertexStore, _WindowsNamedMutex
from .vertex_workforce_contract import (
    ActivationTicket, ActiveVertexAuthorizationSnapshot, CACHE_LIMIT, EntraSessionCandidate, FirmSettings,
    PrivatePrincipal, STORE_LIMIT, WorkforceActiveRecord, WorkforceCredentialContext,
    WorkforceExchangeResult, auth_error, bounded_text, json_object, opaque,
    parse_firm_settings,
)


def _encoded(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


class VertexWorkforceStore:
    def __init__(self, store: VertexStore, *, monotonic=time.monotonic, unix_time=time.time):
        self.base = store
        self._monotonic = monotonic
        self._unix_time = unix_time

    @classmethod
    def production(cls):
        return cls(VertexStore.production())

    def _check(self, deadline: float, cancel_check: Callable[[], None]):
        cancel_check()
        if not math.isfinite(deadline) or self._monotonic() >= deadline:
            raise auth_error("vertex_token_issuance_timeout")

    @contextmanager
    def _locked(self, *, deadline=None, cancel_check=lambda: None):
        if deadline is None:
            deadline = self._monotonic() + self.base._mutex_timeout_ms / 1000
        self._check(deadline, cancel_check)
        timeout = max(0, min(self.base._mutex_timeout_ms, int((deadline - self._monotonic()) * 1000)))
        with _WindowsNamedMutex(self.base._mutex_name, timeout):
            self._check(deadline, cancel_check)
            yield deadline

    def _read_envelope(self):
        if not self.base.path.exists():
            return {"schema_version": 2, "authorization_epoch": secrets.token_hex(16), "pending": None, "active": None}
        try:
            with self.base.path.open("rb") as stream:
                raw = stream.read(STORE_LIMIT + 1)
            value = json_object(raw, STORE_LIMIT)
            if type(value.get("schema_version")) is int and value["schema_version"] == 1:
                if len(raw) > 64 * 1024:
                    raise auth_error()
                legacy = VertexRecord.from_json_object(value)
                return {"schema_version": 2, "authorization_epoch": legacy.generation, "pending": None, "active": legacy.to_json_object()}
            self._validate_envelope(value)
            return value
        except OSError:
            raise auth_error() from None

    def _validate_envelope(self, value):
        if set(value) != {"schema_version", "authorization_epoch", "pending", "active"} or type(value["schema_version"]) is not int or value["schema_version"] != 2:
            raise auth_error()
        opaque(value["authorization_epoch"])
        pending = value["pending"]
        if pending is not None:
            if not isinstance(pending, dict) or set(pending) != {"revision", "settings"}:
                raise auth_error()
            opaque(pending["revision"])
            parse_firm_settings(_encoded(pending["settings"]))
        self._parse_active(value["active"])

    def _parse_active(self, value):
        if value is None:
            return None
        if not isinstance(value, dict):
            raise auth_error()
        if type(value.get("schema_version")) is int and value["schema_version"] == 1:
            return VertexRecord.from_json_object(value)
        expected = {item.name for item in fields(WorkforceActiveRecord)} | {"schema_version", "mode"}
        if set(value) != expected or type(value["schema_version"]) is not int or value["schema_version"] != 2 or value["mode"] != "workforce":
            raise auth_error()
        settings = parse_firm_settings(_encoded(value["settings"]))
        opaque(value["generation"])
        opaque(value["principal_id"])
        if type(value["cache_revision"]) is not int or not 0 <= value["cache_revision"] < 2**63 or type(value["chirp_retirement_pending"]) is not bool:
            raise auth_error()
        bounded_text(value["protected_session"], STORE_LIMIT)
        record = WorkforceActiveRecord(**{key: settings if key == "settings" else value[key] for key in expected - {"schema_version", "mode"}})
        self._decode_session(record)
        return record

    def _protect(self, session):
        try:
            return base64.b64encode(self.base._protector.protect(_encoded(session))).decode("ascii")
        except Exception:
            raise auth_error() from None

    def _decode_session(self, record):
        try:
            protected = base64.b64decode(record.protected_session, validate=True)
            session = json_object(self.base._protector.unprotect(protected), STORE_LIMIT)
            if set(session) != {"principal", "cache", "key", "generation", "principal_id", "cache_revision", "chirp_retirement_pending"}:
                raise auth_error()
            if not isinstance(session["principal"], dict) or set(session["principal"]) != {"tid", "oid", "msal_account_key"}:
                raise auth_error()
            principal = PrivatePrincipal(**session["principal"])
            if principal.tid != record.settings.entra_tenant_id:
                raise auth_error()
            self._validate_cache(session["cache"])
            for key in ("generation", "principal_id", "cache_revision", "chirp_retirement_pending"):
                if type(session[key]) is not type(getattr(record, key)) or session[key] != getattr(record, key):
                    raise auth_error()
            key = bytes.fromhex(session["key"])
            if len(key) != 32 or not isinstance(record.connection_fingerprint, str) or not hmac.compare_digest(record.connection_fingerprint, self._fingerprint(record.settings, key)):
                raise auth_error()
            return principal, session
        except Exception:
            raise auth_error() from None

    @staticmethod
    def _fingerprint(settings, key):
        return hmac.new(key, _encoded(asdict(settings)), hashlib.sha256).hexdigest()

    @staticmethod
    def _validate_cache(cache):
        json_object(bounded_text(cache, CACHE_LIMIT).encode(), CACHE_LIMIT)

    @staticmethod
    def _active_json(record):
        if record is None:
            return None
        if isinstance(record, VertexRecord):
            return record.to_json_object()
        return {**asdict(record), "schema_version": 2, "mode": "workforce"}

    def _write_envelope(self, value, *, deadline, cancel_check, fail_before_replace=False):
        temporary = None
        try:
            self._validate_envelope(value)
            payload = _encoded(value) + b"\n"
            if len(payload) > STORE_LIMIT:
                raise auth_error()
            self.base.path.parent.mkdir(parents=True, exist_ok=True)
            descriptor, name = tempfile.mkstemp(prefix=self.base.path.name + ".", suffix=".tmp", dir=self.base.path.parent)
            temporary = Path(name)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            self._check(deadline, cancel_check)
            if fail_before_replace:
                raise OSError()
            os.replace(temporary, self.base.path)
            temporary = None
        except (OSError, ValueError, TypeError):
            raise auth_error() from None
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass

    def read_pending(self) -> tuple[FirmSettings, ActivationTicket] | None:
        value = self._read_envelope()
        pending = value["pending"]
        if pending is None:
            return None
        return parse_firm_settings(_encoded(pending["settings"])), ActivationTicket(pending["revision"], value["authorization_epoch"])

    def snapshot_active(self) -> ActiveVertexAuthorizationSnapshot | None:
        return self._parse_active(self._read_envelope()["active"])

    def import_pending(self, settings: FirmSettings, *, deadline=None, cancel_check=lambda: None) -> ActivationTicket:
        settings = parse_firm_settings(_encoded(asdict(settings)))
        with self._locked(deadline=deadline, cancel_check=cancel_check) as deadline:
            value = self._read_envelope()
            revision = secrets.token_hex(16)
            value["pending"] = {"revision": revision, "settings": asdict(settings)}
            self._write_envelope(value, deadline=deadline, cancel_check=cancel_check)
            return ActivationTicket(revision, value["authorization_epoch"])

    def discard_pending(self, *, deadline=None, cancel_check=lambda: None) -> None:
        with self._locked(deadline=deadline, cancel_check=cancel_check) as deadline:
            value = self._read_envelope()
            value["pending"] = None
            self._write_envelope(value, deadline=deadline, cancel_check=cancel_check)

    def prepare_reconnect(self, expected_generation: str, *, deadline=None, cancel_check=lambda: None) -> ActivationTicket:
        with self._locked(deadline=deadline, cancel_check=cancel_check) as deadline:
            value = self._read_envelope()
            active = self._require_active(value, expected_generation)
            revision = secrets.token_hex(16)
            value["pending"] = {"revision": revision, "settings": asdict(active.settings)}
            self._write_envelope(value, deadline=deadline, cancel_check=cancel_check)
            return ActivationTicket(revision, value["authorization_epoch"])

    def authorization_epoch(self) -> str | None:
        return self._read_envelope()["authorization_epoch"] if self.base.path.exists() else None

    def has_v2_envelope(self) -> bool:
        if not self.base.path.exists():
            return False
        with self.base.path.open("rb") as stream:
            value = json_object(stream.read(STORE_LIMIT + 1), STORE_LIMIT)
        return value.get("schema_version") == 2

    def activate_legacy(self, expected_epoch: str | None, record: VertexRecord, *, deadline: float, cancel_check: Callable[[], None]) -> VertexRecord:
        with self._locked(deadline=deadline, cancel_check=cancel_check):
            value = self._read_envelope()
            if (expected_epoch is None and self.base.path.exists()) or (expected_epoch is not None and value["authorization_epoch"] != expected_epoch):
                raise auth_error("vertex_authorization_changed")
            committed = replace(record, generation=secrets.token_hex(16))
            value.update(active=committed.to_json_object(), authorization_epoch=secrets.token_hex(16))
            self._write_envelope(value, deadline=deadline, cancel_check=cancel_check)
            return committed

    def disconnect_all(self) -> None:
        with self._locked() as deadline:
            value = self._read_envelope()
            value.update(active=None, pending=None, authorization_epoch=secrets.token_hex(16))
            self._write_envelope(value, deadline=deadline, cancel_check=lambda: None)

    def activate(self, ticket: ActivationTicket, candidate: EntraSessionCandidate, exchange: WorkforceExchangeResult, *, cancel_check: Callable[[], None]) -> WorkforceCredentialContext:
        if not isinstance(candidate, EntraSessionCandidate):
            raise auth_error()
        with self._locked(deadline=candidate.operation_deadline, cancel_check=cancel_check) as deadline:
            value = self._read_envelope()
            pending = value["pending"]
            if pending is None or ActivationTicket(pending["revision"], value["authorization_epoch"]) != ticket:
                raise auth_error("vertex_authorization_changed")
            settings = parse_firm_settings(_encoded(pending["settings"]))
            if not isinstance(candidate, EntraSessionCandidate) or not isinstance(exchange, WorkforceExchangeResult) or candidate.principal.tid != settings.entra_tenant_id or candidate.assertion.expires_at <= self._unix_time() or exchange.expires_at <= self._unix_time():
                raise auth_error()
            if (exchange.project_id, exchange.workforce_pool_user_project, exchange.quota_project_id) != (settings.project_id, settings.workforce_pool_user_project, settings.quota_project_id):
                raise auth_error()
            generation, principal_id, key = secrets.token_hex(16), secrets.token_hex(16), secrets.token_bytes(32)
            session = {"principal": asdict(candidate.principal), "cache": candidate.serialized_cache, "key": key.hex(), "generation": generation, "principal_id": principal_id, "cache_revision": 0, "chirp_retirement_pending": True}
            active = WorkforceActiveRecord(settings, generation, principal_id, self._fingerprint(settings, key), self._protect(session), 0, True)
            value.update(active=self._active_json(active), pending=None, authorization_epoch=secrets.token_hex(16))
            self._write_envelope(value, deadline=deadline, cancel_check=cancel_check)
            return WorkforceCredentialContext(**asdict(exchange), generation=generation, principal_id=principal_id, connection_fingerprint=active.connection_fingerprint)

    def _require_active(self, value, expected_generation):
        active = self._parse_active(value["active"])
        if not isinstance(active, WorkforceActiveRecord) or active.generation != expected_generation:
            raise auth_error("vertex_authorization_changed")
        return active

    def load_active_session(self, expected_generation: str) -> tuple[FirmSettings, PrivatePrincipal, str, int]:
        active = self._require_active(self._read_envelope(), expected_generation)
        principal, session = self._decode_session(active)
        return active.settings, principal, session["cache"], active.cache_revision

    def commit_refreshed_cache(self, expected_generation: str, expected_cache_revision: int, principal: PrivatePrincipal, serialized_cache: str, *, deadline: float, cancel_check: Callable[[], None]) -> int:
        self._validate_cache(serialized_cache)
        with self._locked(deadline=deadline, cancel_check=cancel_check):
            value = self._read_envelope()
            active = self._require_active(value, expected_generation)
            bound, session = self._decode_session(active)
            if bound != principal:
                raise auth_error("vertex_authorization_changed")
            if type(expected_cache_revision) is not int or active.cache_revision != expected_cache_revision or expected_cache_revision >= 2**63 - 1:
                raise auth_error("vertex_refresh_stale")
            revision = expected_cache_revision + 1
            session.update(cache=serialized_cache, cache_revision=revision)
            value["active"] = self._active_json(replace(active, protected_session=self._protect(session), cache_revision=revision))
            self._write_envelope(value, deadline=deadline, cancel_check=cancel_check)
            return revision

    def mark_chirp_retired(self, expected_generation: str, *, deadline: float, cancel_check: Callable[[], None]) -> None:
        with self._locked(deadline=deadline, cancel_check=cancel_check):
            value = self._read_envelope()
            active = self._require_active(value, expected_generation)
            _, session = self._decode_session(active)
            session["chirp_retirement_pending"] = False
            value["active"] = self._active_json(replace(active, protected_session=self._protect(session), chirp_retirement_pending=False))
            self._write_envelope(value, deadline=deadline, cancel_check=cancel_check)

    def _replace_legacy_unlocked(self, committed, *, fail_before_replace):
        value = self._read_envelope()
        value.update(active=committed.to_json_object(), authorization_epoch=secrets.token_hex(16))
        self._write_envelope(value, deadline=self._monotonic() + self.base._mutex_timeout_ms / 1000, cancel_check=lambda: None, fail_before_replace=fail_before_replace)
        return committed
