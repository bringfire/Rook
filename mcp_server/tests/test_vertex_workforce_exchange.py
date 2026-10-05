from __future__ import annotations
from dataclasses import replace
import json
import threading
import time
from types import SimpleNamespace
from urllib.parse import parse_qs, unquote
import pytest
from .test_vertex_workforce_store import fixture, activate
from rook.providers.vertex_auth import VertexAuthError, VertexMode, VertexRecord, apply_vertex_litellm_arguments
from rook.providers.vertex_workforce_contract import WorkforceActiveRecord


def test_sts_id_token_contract_has_no_client_auth(fixture):
    from rook.providers.vertex_workforce_exchange import exchange_assertion
    _, _, settings, _, candidate, _ = fixture
    captured = []
    def request(**kwargs):
        captured.append(kwargs)
        return SimpleNamespace(status=200, data=json.dumps({'access_token': 'synthetic-google-token', 'expires_in': 3600, 'token_type': 'Bearer', 'issued_token_type': 'urn:ietf:params:oauth:token-type:access_token'}).encode())
    result = exchange_assertion(settings, candidate.assertion, deadline=time.monotonic() + 30, cancel_check=lambda: None, request=request)
    assert len(captured) == 1
    call = captured[0]
    form = {key: values[0] for key, values in parse_qs(call['body'].decode()).items()}
    assert call['url'] == 'https://sts.googleapis.com/v1/token' and call['method'] == 'POST'
    assert form['grant_type'] == 'urn:ietf:params:oauth:grant-type:token-exchange'
    assert form['subject_token_type'] == 'urn:ietf:params:oauth:token-type:id_token'
    assert form['requested_token_type'] == 'urn:ietf:params:oauth:token-type:access_token'
    assert form['audience'] == settings.audience and form['scope'] == 'https://www.googleapis.com/auth/cloud-platform'
    assert form['subject_token'] == candidate.assertion.assertion
    assert json.loads(unquote(form['options'])) == {'userProject': settings.workforce_pool_user_project}
    assert 'authorization' not in {name.lower() for name in call['headers']}
    assert not {'client_id', 'client_secret'} & form.keys()
    assert result.project_id == settings.project_id and result.quota_project_id == settings.quota_project_id


@pytest.mark.parametrize('problem', ['denied', 'type', 'expiry', 'oversize', 'duplicate', 'expired-assertion', 'wrong-tenant'])
def test_sts_response_and_assertion_fail_closed(fixture, problem):
    from rook.providers.vertex_workforce_exchange import exchange_assertion
    _, _, settings, principal, candidate, _ = fixture
    assertion = candidate.assertion
    if problem == 'expired-assertion':
        assertion = replace(assertion, expires_at=int(time.time()) - 1)
    if problem == 'wrong-tenant':
        assertion = replace(assertion, principal=replace(principal, tid='44444444-4444-4444-4444-444444444444'))
    calls = []
    def request(**kwargs):
        calls.append(kwargs)
        value = {'access_token': 'sentinel', 'expires_in': 3600, 'token_type': 'Bearer', 'issued_token_type': 'urn:ietf:params:oauth:token-type:access_token'}
        if problem == 'type': value['token_type'] = 'Other'
        if problem == 'expiry': value['expires_in'] = True
        raw = json.dumps(value).encode()
        if problem == 'oversize': raw = b'x' * (1024 * 1024 + 1)
        if problem == 'duplicate': raw = b'{"access_token":"a","access_token":"b"}'
        return SimpleNamespace(status=403 if problem == 'denied' else 200, data=raw)
    with pytest.raises(VertexAuthError) as error:
        exchange_assertion(settings, assertion, deadline=time.monotonic() + 30, cancel_check=lambda: None, request=request)
    assert 'sentinel' not in str(error.value)
    assert len(calls) == (0 if problem in ('expired-assertion', 'wrong-tenant') else 1)


@pytest.mark.parametrize('change', ['login-failure', 'cancel', 'reimport', 'disconnect', 'legacy-save'])
def test_pending_connect_never_reactivates_stale_candidate(fixture, monkeypatch, change):
    from rook.providers import vertex_backend as backend
    base, store, settings, _, candidate, exchange = fixture
    prior = base.replace(VertexRecord(1, '0' * 32, VertexMode.ADC, 'legacy-firm-project', 'europe-west1', None, None))
    ticket = store.import_pending(settings)
    cancelled = [False]
    def begin(*args, **kwargs):
        if change == 'login-failure': raise VertexAuthError('vertex_firm_sign_in_required', 'Sign in required.')
        return replace(candidate, operation_deadline=time.monotonic() + 30)
    def fake_exchange(*args, **kwargs):
        if change == 'cancel': cancelled[0] = True
        if change == 'reimport': store.import_pending(settings)
        if change == 'disconnect': store.disconnect_all()
        if change == 'legacy-save': base.replace(prior)
        return exchange
    monkeypatch.setattr(backend, 'exchange_assertion', fake_exchange)
    retired = []
    def check():
        if cancelled[0]: raise VertexAuthError('vertex_authorization_declined', 'Cancelled.')
    result = backend.connect_vertex_workforce(ticket, store=store, entra=SimpleNamespace(begin=begin), cancel_check=check, retire=lambda *args: retired.append(args))
    assert not result.success and retired == []
    active = store.snapshot_active()
    assert not isinstance(active, WorkforceActiveRecord)
    assert active is None if change == 'disconnect' else active.mode is VertexMode.ADC


@pytest.mark.parametrize('failure', [False, True])
def test_workforce_activation_and_retirement_failure_preserve_committed_state(fixture, monkeypatch, failure):
    from rook.providers import vertex_backend as backend
    _, store, settings, _, candidate, exchange = fixture
    ticket = store.import_pending(settings)
    monkeypatch.setattr(backend, 'exchange_assertion', lambda *args, **kwargs: exchange)
    calls = []
    def retire(*args):
        calls.append(args)
        if failure: raise RuntimeError('private-sentinel')
    result = backend.connect_vertex_workforce(ticket, store=store, entra=SimpleNamespace(begin=lambda *args, **kwargs: replace(candidate, operation_deadline=time.monotonic() + 30)), cancel_check=lambda: None, retire=retire)
    active = store.snapshot_active()
    assert active.generation == result.generation
    assert active.chirp_retirement_pending is failure
    assert len(calls) == 1 and result.success is not failure
    if failure:
        assert result.code == 'vertex_restart_required'
        with pytest.raises(VertexAuthError) as error:
            backend.refresh_vertex_workforce(store=store, entra=None, expected_generation=active.generation, deadline=time.monotonic() + 30, cancel_check=lambda: None)
        assert error.value.code == 'vertex_restart_required'


@pytest.mark.parametrize('outcome', ['timeout', 'newer', 'cancel', 'disconnect'])
def test_old_refresh_cannot_write_or_return_context(fixture, monkeypatch, outcome):
    from rook.providers import vertex_backend as backend
    _, store, _, _, candidate, exchange = fixture
    context = activate(fixture)
    store.mark_chirp_retired(context.generation, deadline=time.monotonic() + 30, cancel_check=lambda: None)
    entered, release, cancelled = threading.Event(), threading.Event(), threading.Event()
    clock = [100.0]
    store._monotonic = lambda: clock[0]
    def refresh(*args, **kwargs):
        entered.set()
        assert release.wait(3)
        return replace(candidate, serialized_cache='{"cache":"old"}', operation_deadline=130)
    calls = []
    monkeypatch.setattr(backend, 'exchange_assertion', lambda *args, **kwargs: calls.append(args) or exchange)
    def check():
        if cancelled.is_set(): raise VertexAuthError('vertex_authorization_declined', 'Cancelled.')
    errors = []
    def run():
        try:
            backend.refresh_vertex_workforce(store=store, entra=SimpleNamespace(refresh=refresh), expected_generation=context.generation, deadline=130, cancel_check=check, monotonic=lambda: clock[0])
        except VertexAuthError as error: errors.append(error.code)
    worker = threading.Thread(target=run)
    worker.start()
    assert entered.wait(3)
    if outcome == 'timeout': clock[0] = 130
    if outcome == 'cancel': cancelled.set()
    if outcome == 'disconnect': store.disconnect_all()
    if outcome == 'newer': store.commit_refreshed_cache(context.generation, 0, candidate.principal, '{"cache":"new"}', deadline=130, cancel_check=lambda: None)
    release.set()
    worker.join(3)
    assert not worker.is_alive() and len(errors) == 1
    if outcome != 'newer': assert calls == []
    if outcome == 'newer': assert store.load_active_session(context.generation)[2:] == ('{"cache":"new"}', 1)


def test_workforce_text_refused_before_adc_or_child_start(fixture):
    from rook.providers.vertex_backend import probe_vertex_readiness
    base, *_ = fixture
    activate(fixture)
    with pytest.raises(VertexAuthError) as error:
        apply_vertex_litellm_arguments('vertex_ai/gemini-2.5-flash', {}, store=base)
    assert error.value.code == 'vertex_text_federation_unsupported'
    result = probe_vertex_readiness('vertex_ai/gemini-2.5-flash', store=base, token_loader=lambda _: pytest.fail('No token load'), post_json=lambda *args: pytest.fail('No model probe'))
    assert result.code == 'vertex_text_federation_unsupported'




def test_pending_retirement_recovery_is_explicit_and_generation_conditional(fixture):
    from rook.providers.vertex_backend import finish_workforce_retirement
    _, store, _, _, _, _ = fixture
    context = activate(fixture)
    calls = []
    assert store.snapshot_active().chirp_retirement_pending
    finish_workforce_retirement(store=store, expected_generation=context.generation, deadline=time.monotonic() + 30, cancel_check=lambda: None, retire=lambda *args: calls.append(args))
    assert not store.snapshot_active().chirp_retirement_pending and len(calls) == 1
    new = activate(fixture)
    with pytest.raises(VertexAuthError):
        finish_workforce_retirement(store=store, expected_generation=context.generation, deadline=time.monotonic() + 30, cancel_check=lambda: None, retire=lambda *args: pytest.fail('No old retirement'))
    assert store.snapshot_active().generation == new.generation and store.snapshot_active().chirp_retirement_pending
