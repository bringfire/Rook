from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import importlib
import threading

import pytest


MODEL = "vertex_ai/gemini-3.1-flash-image"
GENERATION_A = "0123456789abcdef0123456789abcdef"
GENERATION_B = "fedcba9876543210fedcba9876543210"


def _lease_module():
    return importlib.import_module("rook.providers.vertex_token_lease")


def _auth_module():
    return importlib.import_module("rook.providers.vertex_auth")


def _record(*, generation=GENERATION_A, region="global"):
    auth = _auth_module()
    return auth.VertexRecord(
        schema_version=auth.VERTEX_SCHEMA_VERSION,
        generation=generation,
        mode=auth.VertexMode.ADC,
        project_id="company-ai-project",
        region=region,
        oauth_ciphertext=None,
        service_account_path=None,
    )


class _Store:
    def __init__(self, record):
        self.record = record
        self.read_error = None
        self.reads = 0
        self.runtime_calls = 0
        self.read_sequence = []

    def read(self):
        self.reads += 1
        if self.read_error is not None:
            raise self.read_error
        if self.read_sequence:
            return self.read_sequence.pop(0)
        return self.record

    def resolve_runtime(self):
        self.runtime_calls += 1
        record = self.record
        if record is None:
            raise _auth_module().VertexAuthError(
                "vertex_signed_out",
                "Vertex AI is not configured for this Windows user.",
            )
        return _auth_module().VertexRuntimeArguments(
            generation=record.generation,
            project_id=record.project_id,
            region=record.region,
            vertex_credentials=None,
        )


class _Clock:
    def __init__(self, *, monotonic=100.0, unix=1_800_000_000.0):
        self.monotonic_value = monotonic
        self.unix_value = unix

    def monotonic(self):
        return self.monotonic_value

    def time(self):
        return self.unix_value


class _Refresher:
    def __init__(self, clock, *, token="short-lived-token", expires_in=600):
        self.clock = clock
        self.token = token
        self.expires_in = expires_in
        self.calls = []

    def __call__(self, runtime, deadline, monotonic):
        self.calls.append((runtime, deadline, monotonic()))
        return _lease_module().RefreshedVertexAccessToken(
            access_token=self.token,
            expires_at_unix_seconds=int(self.clock.time() + self.expires_in),
        )


def _service(store, clock, refresher):
    return _lease_module().VertexTokenLeaseService(
        store=store,
        refresh_access_token=refresher,
        monotonic=clock.monotonic,
        unix_time=clock.time,
    )


@pytest.mark.asyncio
async def test_cache_hit_re_reads_current_record_before_returning():
    lease = _lease_module()
    clock = _Clock()
    store = _Store(_record())
    refresher = _Refresher(clock)
    service = _service(store, clock, refresher)

    await service.acquire(MODEL)
    reads_after_refresh = store.reads
    result = await service.acquire(MODEL)

    assert result.generation == GENERATION_A
    assert store.reads >= reads_after_refresh + 2
    assert len(refresher.calls) == 1


@pytest.mark.asyncio
async def test_signed_out_record_clears_cache_and_rejects():
    lease = _lease_module()
    clock = _Clock()
    store = _Store(_record())
    refresher = _Refresher(clock)
    service = _service(store, clock, refresher)
    await service.acquire(MODEL)

    store.record = None
    with pytest.raises(_auth_module().VertexAuthError) as caught:
        await service.acquire(MODEL)

    assert caught.value.code == "vertex_signed_out"
    assert service._cached_lease is None
    assert len(refresher.calls) == 1


@pytest.mark.asyncio
async def test_media_image_global_does_not_mutate_text_region():
    clock = _Clock()
    store = _Store(_record(region="us-central1"))
    before = store.record
    refresher = _Refresher(clock)
    result = await _service(store, clock, refresher).acquire(MODEL, "global")
    assert result.location == "global"
    assert store.record == before
    assert refresher.calls[0][0].region == "us-central1"


@pytest.mark.asyncio
async def test_wrong_model_fails_before_store_access():
    clock = _Clock()
    store = _Store(_record())
    refresher = _Refresher(clock)

    with pytest.raises(_auth_module().VertexAuthError) as caught:
        await _service(store, clock, refresher).acquire("vertex_ai/gemini-3-pro-image")

    assert caught.value.code == "vertex_image_model_unsupported"
    assert store.reads == 0
    assert refresher.calls == []


@pytest.mark.asyncio
async def test_matching_token_with_more_than_300_seconds_is_reused():
    clock = _Clock()
    store = _Store(_record())
    refresher = _Refresher(clock, expires_in=301)
    service = _service(store, clock, refresher)

    first = await service.acquire(MODEL)
    second = await service.acquire(MODEL)

    assert first == second
    assert len(refresher.calls) == 1


@pytest.mark.asyncio
async def test_token_at_300_second_boundary_is_refreshed():
    clock = _Clock()
    store = _Store(_record())
    refresher = _Refresher(clock, expires_in=300)
    service = _service(store, clock, refresher)

    await service.acquire(MODEL)
    await service.acquire(MODEL)

    assert len(refresher.calls) == 2


@pytest.mark.asyncio
async def test_concurrent_misses_share_one_refresh():
    lease = _lease_module()
    clock = _Clock()
    store = _Store(_record())
    entered = threading.Event()
    release = threading.Event()
    calls = []

    def refresh(runtime, deadline, monotonic):
        calls.append((runtime, deadline, monotonic()))
        entered.set()
        assert release.wait(timeout=2)
        return lease.RefreshedVertexAccessToken(
            access_token="shared-token",
            expires_at_unix_seconds=int(clock.time() + 600),
        )

    service = _service(store, clock, refresh)
    first = asyncio.create_task(service.acquire(MODEL))
    assert await asyncio.to_thread(entered.wait, 2)
    second = asyncio.create_task(service.acquire(MODEL))
    await asyncio.sleep(0)
    release.set()

    results = await asyncio.gather(first, second)
    assert results[0] == results[1]
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_generation_change_during_refresh_discards_token():
    lease = _lease_module()
    clock = _Clock()
    first = _record(generation=GENERATION_A)
    changed = _record(generation=GENERATION_B)
    store = _Store(first)
    store.read_sequence = [first, first, changed]

    service = _service(store, clock, _Refresher(clock))
    with pytest.raises(_auth_module().VertexAuthError) as caught:
        await service.acquire(MODEL)

    assert caught.value.code == "vertex_authorization_changed"
    assert service._cached_lease is None


@pytest.mark.asyncio
async def test_failed_rotation_cannot_restore_and_reuse_the_stale_token():
    lease = _lease_module()
    auth = _auth_module()
    clock = _Clock()
    store = _Store(_record(generation=GENERATION_A))
    issued_tokens = iter(["generation-a-token", "generation-a-replacement-token"])
    calls = []

    def refresh(runtime, _deadline, _monotonic):
        calls.append(runtime.generation)
        if runtime.generation == GENERATION_B:
            raise auth.VertexAuthError(
                "vertex_adc_unavailable",
                "Application Default Credentials are unavailable.",
            )
        return lease.RefreshedVertexAccessToken(
            access_token=next(issued_tokens),
            expires_at_unix_seconds=int(clock.time() + 600),
        )

    service = _service(store, clock, refresh)
    first = await service.acquire(MODEL)
    assert first.access_token == "generation-a-token"

    store.record = _record(generation=GENERATION_B)
    with pytest.raises(auth.VertexAuthError) as caught:
        await service.acquire(MODEL)
    assert caught.value.code == "vertex_adc_unavailable"

    store.record = _record(generation=GENERATION_A)
    restored = await service.acquire(MODEL)

    assert restored.access_token == "generation-a-replacement-token"
    assert calls == [GENERATION_A, GENERATION_B, GENERATION_A]


@pytest.mark.asyncio
async def test_regional_rotation_cannot_restore_and_reuse_the_stale_token():
    lease = _lease_module()
    auth = _auth_module()
    clock = _Clock()
    store = _Store(_record(generation=GENERATION_A))
    issued_tokens = iter(["generation-a-token", "generation-a-replacement-token"])
    calls = []

    def refresh(runtime, _deadline, _monotonic):
        calls.append(runtime.generation)
        return lease.RefreshedVertexAccessToken(
            access_token=next(issued_tokens),
            expires_at_unix_seconds=int(clock.time() + 600),
        )

    service = _service(store, clock, refresh)
    first = await service.acquire(MODEL)
    assert first.access_token == "generation-a-token"

    store.record = _record(generation=GENERATION_B, region="us-central1")
    with pytest.raises(auth.VertexAuthError) as caught:
        await service.acquire(MODEL, "us-central1")
    assert caught.value.code == "vertex_model_region_unsupported"

    store.record = _record(generation=GENERATION_A)
    restored = await service.acquire(MODEL)

    assert restored.access_token == "generation-a-replacement-token"
    assert calls == [GENERATION_A, GENERATION_A]


@pytest.mark.asyncio
async def test_invalid_record_recovery_cannot_reuse_the_stale_token():
    lease = _lease_module()
    auth = _auth_module()
    clock = _Clock()
    store = _Store(_record(generation=GENERATION_A))
    issued_tokens = iter(["generation-a-token", "generation-a-replacement-token"])
    calls = []

    def refresh(runtime, _deadline, _monotonic):
        calls.append(runtime.generation)
        return lease.RefreshedVertexAccessToken(
            access_token=next(issued_tokens),
            expires_at_unix_seconds=int(clock.time() + 600),
        )

    service = _service(store, clock, refresh)
    first = await service.acquire(MODEL)
    assert first.access_token == "generation-a-token"

    store.read_error = auth.VertexAuthError(
        "vertex_request_failed",
        "Vertex authorization is unavailable because its local configuration is invalid.",
    )
    with pytest.raises(auth.VertexAuthError) as caught:
        await service.acquire(MODEL)
    assert caught.value.code == "vertex_request_failed"

    store.read_error = None
    restored = await service.acquire(MODEL)

    assert restored.access_token == "generation-a-replacement-token"
    assert calls == [GENERATION_A, GENERATION_A]


def test_refresh_transport_is_20_seconds_and_outer_budget_is_30(monkeypatch):
    lease = _lease_module()
    auth = _auth_module()
    clock = _Clock(monotonic=25.0)
    observed = []

    class Credentials:
        token = "transport-token"
        expiry = datetime.fromtimestamp(clock.time() + 600, tz=timezone.utc)

        def refresh(self, request):
            request(url="https://oauth2.googleapis.com/token", method="POST")

    def transport(**kwargs):
        observed.append(kwargs["timeout"])
        return object()

    monkeypatch.setattr(
        lease,
        "_load_google_credentials",
        lambda _runtime: (Credentials(), "vertex_adc_unavailable", transport),
    )
    runtime = auth.VertexRuntimeArguments(
        generation=GENERATION_A,
        project_id="company-ai-project",
        region="global",
        vertex_credentials=None,
    )

    refreshed = lease.refresh_access_token(runtime, 55.0, clock.monotonic)

    assert refreshed.access_token == "transport-token"
    assert observed == [20.0]
    assert 55.0 - 25.0 == lease.TOKEN_ISSUANCE_TIMEOUT_SECONDS


@pytest.mark.asyncio
async def test_lock_wait_and_refresh_share_the_same_30_second_budget():
    clock = _Clock(monotonic=100.0)
    store = _Store(_record())
    refresher = _Refresher(clock)
    service = _service(store, clock, refresher)

    await service._refresh_lock.acquire()
    task = asyncio.create_task(service.acquire(MODEL))
    await asyncio.sleep(0)
    clock.monotonic_value = 129.0
    service._refresh_lock.release()
    await task

    assert refresher.calls[0][1] == 130.0
    assert refresher.calls[0][2] == 129.0


@pytest.mark.asyncio
async def test_exhausted_outer_budget_returns_the_stable_timeout():
    clock = _Clock(monotonic=100.0)
    values = iter([100.0, 131.0])
    clock.monotonic = lambda: next(values)
    store = _Store(_record())

    with pytest.raises(_auth_module().VertexAuthError) as caught:
        await _service(store, clock, _Refresher(clock)).acquire(MODEL)

    assert caught.value.code == "vertex_token_issuance_timeout"
    assert store.reads == 0


@pytest.mark.asyncio
async def test_external_cancellation_remains_cancellation():
    lease = _lease_module()
    clock = _Clock()
    store = _Store(_record())
    entered = threading.Event()
    release = threading.Event()

    def refresh(_runtime, _deadline, _monotonic):
        entered.set()
        assert release.wait(timeout=2)
        return lease.RefreshedVertexAccessToken(
            access_token="cancelled-call-token",
            expires_at_unix_seconds=int(clock.time() + 600),
        )

    task = asyncio.create_task(_service(store, clock, refresh).acquire(MODEL))
    assert await asyncio.to_thread(entered.wait, 2)
    task.cancel()
    try:
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        release.set()


def test_lock_wait_leaves_only_remaining_budget_for_each_google_request(monkeypatch):
    lease = _lease_module()
    auth = _auth_module()
    clock = _Clock(monotonic=129.0)
    observed = []

    class Credentials:
        token = "remaining-token"
        expiry = datetime.fromtimestamp(clock.time() + 600, tz=timezone.utc)

        def refresh(self, request):
            request(url="https://oauth2.googleapis.com/token", method="POST")
            clock.monotonic_value = 129.75
            request(url="https://oauth2.googleapis.com/token", method="POST")

    def transport(**kwargs):
        observed.append(kwargs["timeout"])
        return object()

    monkeypatch.setattr(
        lease,
        "_load_google_credentials",
        lambda _runtime: (Credentials(), "vertex_adc_unavailable", transport),
    )
    runtime = auth.VertexRuntimeArguments(
        generation=GENERATION_A,
        project_id="company-ai-project",
        region="global",
        vertex_credentials=None,
    )

    lease.refresh_access_token(runtime, 130.0, clock.monotonic)

    assert observed == [1.0, 0.25]


def test_google_transport_timeout_keeps_the_token_timeout_taxonomy(monkeypatch):
    from google.auth import exceptions as google_exceptions
    from requests import exceptions as requests_exceptions

    lease = _lease_module()
    auth = _auth_module()
    clock = _Clock(monotonic=100.0)

    class Credentials:
        token = None
        expiry = None

        def refresh(self, request):
            request(url="https://oauth2.googleapis.com/token", method="POST")

    def transport(**_kwargs):
        timeout = requests_exceptions.ReadTimeout("private transport detail")
        raise google_exceptions.TransportError(timeout) from timeout

    monkeypatch.setattr(
        lease,
        "_load_google_credentials",
        lambda _runtime: (Credentials(), "vertex_adc_unavailable", transport),
    )
    runtime = auth.VertexRuntimeArguments(
        generation=GENERATION_A,
        project_id="company-ai-project",
        region="global",
        vertex_credentials=None,
    )

    with pytest.raises(auth.VertexAuthError) as caught:
        lease.refresh_access_token(runtime, 130.0, clock.monotonic)

    assert caught.value.code == "vertex_token_issuance_timeout"
    assert str(caught.value) == "Vertex token issuance timed out."
    assert "private transport detail" not in str(caught.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("token", "expiry"),
    [
        ("", 1_800_000_600),
        ("token", 1_800_000_000),
        ("token", float("nan")),
        ("token", "1800000600"),
    ],
)
async def test_expiry_must_be_finite_and_future(token, expiry):
    lease = _lease_module()
    clock = _Clock()
    store = _Store(_record())

    def refresh(_runtime, _deadline, _monotonic):
        return lease.RefreshedVertexAccessToken(
            access_token=token,
            expires_at_unix_seconds=expiry,
        )

    with pytest.raises(_auth_module().VertexAuthError) as caught:
        await _service(store, clock, refresh).acquire(MODEL)

    assert caught.value.code == "vertex_token_issuance_failed"


@pytest.mark.asyncio
async def test_access_token_never_appears_in_failure_or_log_projection():
    lease = _lease_module()
    clock = _Clock()
    store = _Store(_record())
    token = "bearer-secret-must-not-escape"

    refreshed = lease.RefreshedVertexAccessToken(
        access_token=token,
        expires_at_unix_seconds=int(clock.time() + 600),
    )
    assert token not in repr(refreshed)

    service = _service(store, clock, lambda *_args: refreshed)
    acquired = await service.acquire(MODEL)
    assert token not in repr(acquired)

    def fail(*_args):
        raise RuntimeError(token)

    failing = _service(store, clock, fail)
    with pytest.raises(_auth_module().VertexAuthError) as caught:
        await failing.acquire(MODEL)
    assert caught.value.code == "vertex_token_issuance_failed"
    assert token not in str(caught.value)


@pytest.mark.parametrize(
    ("credentials", "expected_code"),
    [
        ({"type": "authorized_user"}, "vertex_authorization_revoked"),
        (None, "vertex_adc_unavailable"),
        ("C:/credentials/service-account.json", "vertex_service_account_unavailable"),
    ],
)
def test_credential_setup_failures_keep_their_bounded_mode_code(
    monkeypatch,
    credentials,
    expected_code,
):
    lease = _lease_module()
    auth = _auth_module()
    runtime = auth.VertexRuntimeArguments(
        generation=GENERATION_A,
        project_id="company-ai-project",
        region="global",
        vertex_credentials=credentials,
    )
    monkeypatch.setattr(
        lease,
        "_load_google_credentials",
        lambda _runtime: (_ for _ in ()).throw(RuntimeError("private credential detail")),
    )

    with pytest.raises(auth.VertexAuthError) as caught:
        lease.refresh_access_token(runtime, 130.0, lambda: 100.0)

    assert caught.value.code == expected_code
    assert "private credential detail" not in str(caught.value)


@pytest.mark.asyncio
async def test_expected_binding_rejects_rotation_before_refresh():
    clock = _Clock(); store = _Store(_record()); refresher = _Refresher(clock)
    service = _service(store, clock, refresher)
    first = await service.acquire(MODEL, "global")
    store.record = _record(generation=GENERATION_B)
    with pytest.raises(_auth_module().VertexAuthError, match="authorization changed"):
        await service.acquire(MODEL, "global", first.binding)
    assert len(refresher.calls) == 1
    assert store.runtime_calls == 1

@pytest.mark.asyncio
async def test_ordinary_refresh_preserves_binding_and_validate_does_not_refresh():
    clock = _Clock(); store = _Store(_record(region="us-central1")); refresher = _Refresher(clock)
    service = _service(store, clock, refresher)
    first = await service.acquire(MODEL, "global")
    service.validate_binding(first.binding)
    assert len(refresher.calls) == 1
    clock.unix_value += 400
    second = await service.acquire(MODEL, "global", first.binding)
    assert first.binding == second.binding
    assert len(refresher.calls) == 2
    assert "short-lived-token" not in repr(second)

@pytest.mark.asyncio
async def test_locations_are_validated_per_media_model():
    lease = _lease_module(); clock = _Clock(); store = _Store(_record(region="us-central1")); refresher = _Refresher(clock)
    service = _service(store, clock, refresher)
    image = await service.acquire(MODEL, "global")
    video = await service.acquire(lease.VERTEX_VIDEO_MODEL_KEY, "us-central1")
    assert video.location == "us-central1" and image.location == "global"
    assert len(refresher.calls) == 1
    for model, location in [(MODEL,"us-central1"),(lease.VERTEX_VIDEO_MODEL_KEY,"global")]:
        with pytest.raises(_auth_module().VertexAuthError): await service.acquire(model,location)
    assert store.record.region == "us-central1"

@pytest.mark.asyncio
async def test_rotation_during_bound_refresh_returns_no_token():
    lease = _lease_module(); clock = _Clock(); store = _Store(_record())
    def refresh(runtime, deadline, monotonic):
        store.record = _record(generation=GENERATION_B)
        return lease.RefreshedVertexAccessToken("secret-discard", int(clock.time()+600))
    binding = lease.VertexMediaBinding(1, GENERATION_A, "company-ai-project", "global", MODEL)
    with pytest.raises(_auth_module().VertexAuthError) as caught:
        await _service(store,clock,refresh).acquire(MODEL,"global",binding)
    assert caught.value.code == "vertex_authorization_changed"
    assert "secret-discard" not in str(caught.value)

from .test_vertex_workforce_store import fixture as workforce_fixture, activate as activate_workforce


@pytest.mark.asyncio
async def test_same_principal_refresh_preserves_v2_binding(workforce_fixture):
    from dataclasses import asdict
    from rook.providers.vertex_workforce_contract import WorkforceCredentialContext
    _, store, _, _, _, exchange = workforce_fixture
    context = activate_workforce(workforce_fixture)
    store.mark_chirp_retired(context.generation, deadline=__import__('time').monotonic() + 30, cancel_check=lambda: None)
    calls = []
    def refresh(**kwargs):
        calls.append(kwargs)
        return WorkforceCredentialContext(**asdict(exchange), generation=context.generation, principal_id=context.principal_id, connection_fingerprint=context.connection_fingerprint)
    service = _lease_module().VertexTokenLeaseService(store=store.base, workforce_store=store, workforce_refresher=refresh)
    first = await service.acquire(MODEL, contract_version=2)
    service._cached_lease = None
    second = await service.acquire(MODEL, expected_binding=first.binding, contract_version=2)
    assert first.binding == second.binding and first.generation == second.generation
    assert len(first.binding.to_wire()) == 9 and first.contract_version == 2
    count = len(calls)
    service.validate_binding(first.binding)
    assert len(calls) == count
    with pytest.raises(_auth_module().VertexAuthError) as error:
        await service.acquire(MODEL, expected_binding=first.binding, contract_version=1)
    assert error.value.code == 'vertex_client_upgrade_required' and len(calls) == count
    store.disconnect_all()
    with pytest.raises(_auth_module().VertexAuthError):
        service.validate_binding(first.binding)


@pytest.mark.asyncio
async def test_retirement_pending_blocks_cached_and_fresh_lease(workforce_fixture):
    _, store, *_ = workforce_fixture
    activate_workforce(workforce_fixture)
    service = _lease_module().VertexTokenLeaseService(store=store.base, workforce_store=store, workforce_refresher=lambda **kwargs: pytest.fail('No refresh during retirement'))
    with pytest.raises(_auth_module().VertexAuthError) as error:
        await service.acquire(MODEL, contract_version=2)
    assert error.value.code == 'vertex_restart_required' and service._cached_lease is None
    active = store.snapshot_active()
    service._cached_lease = _lease_module().VertexTokenLease('cached-sentinel', int(__import__('time').time()) + 3600, active.project_id, 'global', active.generation, service._binding(active, MODEL, 'global'), 2, active.settings.quota_project_id)
    with pytest.raises(_auth_module().VertexAuthError) as error:
        await service.acquire(MODEL, contract_version=2)
    assert error.value.code == 'vertex_restart_required' and service._cached_lease is None


@pytest.mark.asyncio
@pytest.mark.parametrize('reason', ['timeout', 'caller-cancel', 'disconnect'])
async def test_acquire_revokes_worker_before_unlock_and_newer_refresh(reason, workforce_fixture, monkeypatch):
    from dataclasses import asdict
    from rook.providers.vertex_workforce_contract import WorkforceCredentialContext
    import time
    _, store, _, _, _, exchange = workforce_fixture
    context = activate_workforce(workforce_fixture)
    store.mark_chirp_retired(context.generation, deadline=time.monotonic() + 30, cancel_check=lambda: None)
    entered, release = threading.Event(), threading.Event()
    observed = []
    checks = []
    def refresh(**kwargs):
        if not checks:
            checks.append(kwargs['cancel_check'])
            entered.set()
            assert release.wait(3)
            try: kwargs['cancel_check']()
            except _auth_module().VertexAuthError: observed.append('revoked'); raise
        return WorkforceCredentialContext(**asdict(exchange), generation=context.generation, principal_id=context.principal_id, connection_fingerprint=context.connection_fingerprint)
    service = _lease_module().VertexTokenLeaseService(store=store.base, workforce_store=store, workforce_refresher=refresh)
    monkeypatch.setattr(_lease_module(), 'TOKEN_ISSUANCE_TIMEOUT_SECONDS', .1 if reason == 'timeout' else 30)
    task = asyncio.create_task(service.acquire(MODEL, contract_version=2))
    assert await asyncio.to_thread(entered.wait, 2)
    if reason == 'caller-cancel': task.cancel()
    if reason == 'disconnect': store.disconnect_all(); task.cancel()
    with pytest.raises((asyncio.CancelledError, _auth_module().VertexAuthError)):
        await task
    assert not service._refresh_lock.locked()
    with pytest.raises(_auth_module().VertexAuthError): checks[0]()
    if reason != 'disconnect':
        newer = await service.acquire(MODEL, contract_version=2)
        assert newer.access_token == exchange.access_token
    release.set()
    await asyncio.gather(*list(service._workers), return_exceptions=True)
    assert observed == ['revoked'] and not service._workers
    if reason != 'disconnect': assert service._cached_lease == newer
