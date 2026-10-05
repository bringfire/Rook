from __future__ import annotations

from dataclasses import asdict
import json
import time
import threading
import uuid

import pytest

from rook.providers.vertex_auth import VertexAuthError, VertexMode, VertexRecord, VertexStore


class Protector:
    def protect(self, value):
        return bytes(byte ^ 0xA5 for byte in value)

    unprotect = protect


@pytest.fixture
def fixture(tmp_path):
    from rook.providers.vertex_workforce_contract import FirmSettings, PrivatePrincipal, VerifiedEntraAssertion, EntraSessionCandidate, WorkforceExchangeResult
    from rook.providers.vertex_workforce_store import VertexWorkforceStore

    base = VertexStore(tmp_path / "vertex.json", protector=Protector(), mutex_name="Local\\Rook.Workforce.Test." + uuid.uuid4().hex)
    settings = FirmSettings(2, "Synthetic firm", "11111111-1111-1111-1111-111111111111", "22222222-2222-2222-2222-222222222222", "123456789", "synthetic-pool", "synthetic-provider", "synthetic-firm-project", "synthetic-firm-project", "synthetic-firm-project", "us-central1")
    principal = PrivatePrincipal(settings.entra_tenant_id, "33333333-3333-3333-3333-333333333333", "bound-account")
    assertion = VerifiedEntraAssertion("assertion-sentinel", principal, int(time.time()) + 3600)
    candidate = EntraSessionCandidate(principal, '{"refresh":"refresh-sentinel"}', assertion)
    exchange = WorkforceExchangeResult("bearer-sentinel", int(time.time()) + 3600, settings.project_id, settings.workforce_pool_user_project, settings.quota_project_id)
    return base, VertexWorkforceStore(base), settings, principal, candidate, exchange


def activate(fixture):
    base, store, settings, principal, candidate, exchange = fixture
    ticket = store.import_pending(settings)
    context = store.activate(ticket, candidate, exchange, cancel_check=lambda: None)
    return context


def test_v1_active_survives_pending_import(fixture):
    base, store, settings, *_ = fixture
    prior = base.replace(VertexRecord(1, "0" * 32, VertexMode.ADC, "legacy-firm-project", "europe-west1", None, None))
    ticket = store.import_pending(settings)
    assert store.snapshot_active() == prior and base.read() == prior
    assert base.resolve_runtime().region == "europe-west1"
    assert store.read_pending() == (settings, ticket)
    store.discard_pending()
    assert base.read() == prior and store.read_pending() is None


def test_import_failure_cancel_and_disconnect_keep_slots_consistent(fixture):
    base, store, settings, principal, candidate, exchange = fixture
    ticket = store.import_pending(settings)
    before = base.path.read_bytes()
    from rook.providers.vertex_workforce_contract import parse_firm_settings
    with pytest.raises(VertexAuthError):
        parse_firm_settings(b'{"schema_version":2,"secret":"forbidden"}')
    assert base.path.read_bytes() == before
    def cancelled():
        raise VertexAuthError("vertex_authorization_declined", "Cancelled.")
    with pytest.raises(VertexAuthError):
        store.activate(ticket, candidate, exchange, cancel_check=cancelled)
    assert base.path.read_bytes() == before
    store.disconnect_all()
    assert store.snapshot_active() is None and store.read_pending() is None
    with pytest.raises(VertexAuthError):
        store.activate(ticket, candidate, exchange, cancel_check=lambda: None)
    assert store.snapshot_active() is None


def test_same_employee_reconnect_rotates_generation(fixture):
    first = activate(fixture)
    second = activate(fixture)
    assert first.generation != second.generation
    assert first.principal_id != second.principal_id


def test_reimport_and_legacy_save_invalidate_candidate(fixture):
    base, store, settings, principal, candidate, exchange = fixture
    old = store.import_pending(settings)
    store.import_pending(settings)
    with pytest.raises(VertexAuthError):
        store.activate(old, candidate, exchange, cancel_check=lambda: None)
    current = store.read_pending()[1]
    base.replace(VertexRecord(1, "0" * 32, VertexMode.ADC, "legacy-firm-project", "global", None, None))
    with pytest.raises(VertexAuthError):
        store.activate(current, candidate, exchange, cancel_check=lambda: None)
    assert base.read().project_id == "legacy-firm-project"


def test_old_cache_revision_cannot_overwrite_new_refresh(fixture):
    _, store, _, principal, *_ = fixture
    context = activate(fixture)
    settings, loaded, cache, revision = store.load_active_session(context.generation)
    newer = store.commit_refreshed_cache(context.generation, revision, principal, '{"refresh":"new-sentinel"}', deadline=time.monotonic() + 10, cancel_check=lambda: None)
    with pytest.raises(VertexAuthError) as error:
        store.commit_refreshed_cache(context.generation, revision, principal, cache, deadline=time.monotonic() + 10, cancel_check=lambda: None)
    assert error.value.code == "vertex_refresh_stale"
    assert store.load_active_session(context.generation)[2:] == ('{"refresh":"new-sentinel"}', newer)
    assert store.snapshot_active().generation == context.generation


@pytest.mark.parametrize("expired", [False, True])
def test_cache_commit_rejects_cancelled_or_expired_worker(fixture, expired):
    base, store, _, principal, *_ = fixture
    context = activate(fixture)
    revision = store.load_active_session(context.generation)[3]
    before = base.path.read_bytes()
    def check():
        if not expired:
            raise VertexAuthError("vertex_authorization_declined", "Cancelled.")
    with pytest.raises(VertexAuthError):
        store.commit_refreshed_cache(context.generation, revision, principal, "{}", deadline=time.monotonic() + (-1 if expired else 10), cancel_check=check)
    assert base.path.read_bytes() == before


def test_retirement_flag_is_generation_conditional(fixture):
    first = activate(fixture)
    _, store, *_ = fixture
    assert store.snapshot_active().chirp_retirement_pending is True
    store.mark_chirp_retired(first.generation, deadline=time.monotonic() + 10, cancel_check=lambda: None)
    assert store.snapshot_active().chirp_retirement_pending is False
    second = activate(fixture)
    with pytest.raises(VertexAuthError):
        store.mark_chirp_retired(first.generation, deadline=time.monotonic() + 10, cancel_check=lambda: None)
    assert store.snapshot_active().generation == second.generation
    assert store.snapshot_active().chirp_retirement_pending is True


def test_private_session_has_no_plaintext_or_token_in_store_or_repr(fixture):
    base, store, _, principal, candidate, exchange = fixture
    context = activate(fixture)
    assert store.load_active_session(context.generation)[1:3] == (principal, candidate.serialized_cache)
    raw = base.path.read_bytes().decode()
    for private in [principal.tid, principal.oid, principal.msal_account_key, candidate.serialized_cache, "refresh-sentinel", "assertion-sentinel", "bearer-sentinel"]:
        # Tenant is public configuration, but must not appear in identity diagnostics.
        if private != principal.tid:
            assert private not in raw
        assert private not in repr(principal) + repr(candidate) + repr(exchange) + repr(context) + repr(store.snapshot_active())


@pytest.mark.parametrize("bad", [b'{"schema_version":2,"schema_version":2}', b'{}' * 32769, b'{"schema_version":99}', b'[]'], ids=["duplicate", "oversize", "future", "array"])
def test_import_rejects_unknown_duplicate_or_oversized_settings(bad):
    from rook.providers.vertex_workforce_contract import parse_firm_settings
    with pytest.raises(VertexAuthError):
        parse_firm_settings(bad)


def test_settings_roundtrip_and_fixed_endpoints(fixture):
    from rook.providers.vertex_workforce_contract import parse_firm_settings
    _, _, settings, *_ = fixture
    assert parse_firm_settings(json.dumps(asdict(settings)).encode()) == settings
    assert settings.audience == "//iam.googleapis.com/locations/global/workforcePools/synthetic-pool/providers/synthetic-provider"
    assert settings.authority == "https://login.microsoftonline.com/11111111-1111-1111-1111-111111111111"


def test_cache_envelope_bounds_and_write_failure_preserve_prior(fixture, monkeypatch):
    import os
    base, store, _, principal, *_ = fixture
    context = activate(fixture)
    before = base.path.read_bytes()
    revision = store.load_active_session(context.generation)[3]
    with pytest.raises(VertexAuthError):
        store.commit_refreshed_cache(context.generation, revision, principal, "x" * (256 * 1024 + 1), deadline=time.monotonic() + 10, cancel_check=lambda: None)
    def fail(*args):
        raise OSError("synthetic interrupted atomic replacement")
    monkeypatch.setattr(os, "replace", fail)
    with pytest.raises(VertexAuthError):
        store.commit_refreshed_cache(context.generation, revision, principal, "{}", deadline=time.monotonic() + 10, cancel_check=lambda: None)
    assert base.path.read_bytes() == before
    assert not list(base.path.parent.glob("*.tmp"))


def test_deliberate_legacy_reconnect_rotates_firm_authorization(fixture):
    base, store, *_ = fixture
    prior = activate(fixture)
    committed = base.replace(VertexRecord(1, "0" * 32, VertexMode.ADC, "legacy-firm-project", "global", None, None))
    assert committed.generation != prior.generation
    assert store.snapshot_active() == committed
    with pytest.raises(VertexAuthError):
        store.load_active_session(prior.generation)


def test_cancelled_mutex_wait_cannot_commit(fixture, monkeypatch):
    from rook.providers.vertex_auth import _WindowsNamedMutex
    base, store, _, principal, *_ = fixture
    context = activate(fixture)
    revision = store.load_active_session(context.generation)[3]
    before = base.path.read_bytes()
    entered, cancelled = threading.Event(), threading.Event()
    errors = []
    def check():
        if cancelled.is_set():
            raise VertexAuthError("vertex_authorization_declined", "Cancelled.")
    def commit():
        try:
            store.commit_refreshed_cache(context.generation, revision, principal, "{}", deadline=time.monotonic() + 5, cancel_check=check)
        except VertexAuthError as error:
            errors.append(error.code)
    with _WindowsNamedMutex(base._mutex_name, 1000):
        original_enter = _WindowsNamedMutex.__enter__
        def enter_lock(self):
            entered.set()
            return original_enter(self)
        monkeypatch.setattr(_WindowsNamedMutex, "__enter__", enter_lock)
        worker = threading.Thread(target=commit)
        worker.start()
        assert entered.wait(1)
        cancelled.set()
    worker.join(2)
    assert not worker.is_alive()
    assert errors == ["vertex_authorization_declined"]
    assert base.path.read_bytes() == before


def test_deadline_expiring_after_fsync_cannot_replace_cache(fixture, monkeypatch):
    import os
    base, store, _, principal, *_ = fixture
    context = activate(fixture)
    revision = store.load_active_session(context.generation)[3]
    before = base.path.read_bytes()
    clock = [100.0]
    store._monotonic = lambda: clock[0]
    original_fsync = os.fsync
    def expire_after_flush(fd):
        original_fsync(fd)
        clock[0] = 102.0
    monkeypatch.setattr(os, "fsync", expire_after_flush)
    with pytest.raises(VertexAuthError) as error:
        store.commit_refreshed_cache(context.generation, revision, principal, "{}", deadline=101.0, cancel_check=lambda: None)
    assert error.value.code == "vertex_token_issuance_timeout"
    assert base.path.read_bytes() == before
    assert not list(base.path.parent.glob("*.tmp"))


@pytest.mark.parametrize("mutation", ["future", "oversize", "tampered-settings", "tampered-revision", "tampered-retirement"])
def test_corrupt_envelope_is_refused_without_rewrite(fixture, mutation):
    base, store, *_ = fixture
    activate(fixture)
    value = json.loads(base.path.read_bytes())
    if mutation == "future":
        value["schema_version"] = 99
    elif mutation == "oversize":
        value["padding"] = "x" * (512 * 1024)
    elif mutation == "tampered-settings":
        value["active"]["settings"]["project_id"] = "another-firm-project"
    elif mutation == "tampered-revision":
        value["active"]["cache_revision"] += 1
    else:
        value["active"]["chirp_retirement_pending"] = False
    raw = json.dumps(value).encode()
    base.path.write_bytes(raw)
    with pytest.raises(VertexAuthError):
        store.snapshot_active()
    with pytest.raises(VertexAuthError):
        store.disconnect_all()
    assert base.path.read_bytes() == raw


@pytest.mark.parametrize("operation", ["import", "discard", "reconnect"])
def test_pending_mutations_recheck_cancellation_after_flush(fixture, monkeypatch, operation):
    import os
    base, store, settings, *_ = fixture
    context = activate(fixture)
    store.import_pending(settings)
    before = base.path.read_bytes()
    cancelled = threading.Event()
    fsync = os.fsync
    def flush(fd):
        fsync(fd)
        cancelled.set()
    def check():
        if cancelled.is_set():
            raise VertexAuthError("vertex_authorization_declined", "Cancelled.")
    monkeypatch.setattr(os, "fsync", flush)
    with pytest.raises(VertexAuthError):
        kwargs = dict(deadline=time.monotonic() + 5, cancel_check=check)
        if operation == "import":
            store.import_pending(settings, **kwargs)
        elif operation == "discard":
            store.discard_pending(**kwargs)
        else:
            store.prepare_reconnect(context.generation, **kwargs)
    assert base.path.read_bytes() == before
    assert not list(base.path.parent.glob("*.tmp"))
