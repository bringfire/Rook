"""Signed synthetic Entra assertions; no Microsoft/Google network or private data."""
from __future__ import annotations

import base64
import json
import time
from urllib.parse import parse_qs, urlsplit

from cryptography.hazmat.primitives.asymmetric import rsa
import jwt
import pytest

from rook.providers.vertex_auth import VertexAuthError
from rook.providers.vertex_workforce_contract import FirmSettings, PrivatePrincipal, ActivationTicket


@pytest.fixture
def settings():
    return FirmSettings(2, "Synthetic firm", "11111111-1111-1111-1111-111111111111", "22222222-2222-2222-2222-222222222222", "123456789", "synthetic-pool", "synthetic-provider", "synthetic-firm-project", "synthetic-firm-project", None, "us-central1")


@pytest.fixture(scope="module")
def key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def claims(settings, **changes):
    now = int(time.time())
    value = {"iss": settings.authority + "/v2.0", "aud": settings.entra_client_id, "tid": settings.entra_tenant_id, "oid": "33333333-3333-3333-3333-333333333333", "sub": "synthetic-subject", "iat": now, "nbf": now - 10, "exp": now + 3600, "nonce": "wire-nonce"}
    value.update(changes)
    return value


def signed(key, value, kid="test-key"):
    return jwt.encode(value, key, algorithm="RS256", headers={"kid": kid})


class Response:
    def __init__(self, payload, status=200):
        self.status_code = status
        self.headers = {}
        self.text = json.dumps(payload)
        self.payload = payload

    def json(self):
        return self.payload


class EntraTransport:
    def __init__(self, settings, key):
        self.settings, self.key = settings, key
        self.calls = []
        self.token = None
        self.nonce = "wire-nonce"
        self.missing_claim = None
        self.subject_changes = {}

    def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        if url.endswith("/.well-known/openid-configuration"):
            return Response({"issuer": self.settings.authority + "/v2.0", "authorization_endpoint": self.settings.authority + "/oauth2/v2.0/authorize", "token_endpoint": self.settings.authority + "/oauth2/v2.0/token", "jwks_uri": self.settings.authority + "/discovery/v2.0/keys"})
        assert url == self.settings.authority + "/discovery/v2.0/keys"
        jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.key.public_key()))
        jwk.update(kid="test-key", use="sig", alg="RS256")
        return Response({"keys": [jwk]})

    def post(self, url, data, **kwargs):
        assert url == self.settings.authority + "/oauth2/v2.0/token"
        self.calls.append(("POST", url, data))
        value = claims(self.settings, nonce=self.nonce, **self.subject_changes)
        if self.missing_claim:
            value.pop(self.missing_claim)
        token = signed(self.key, value)
        client_info = base64.urlsafe_b64encode(json.dumps({"uid": "33333333-3333-3333-3333-333333333333", "utid": self.settings.entra_tenant_id}).encode()).decode().rstrip("=")
        return Response({"access_token": "entra-access-sentinel", "id_token": token, "token_type": "Bearer", "expires_in": 3600, "refresh_token": "entra-refresh-sentinel", "client_info": client_info, "scope": "openid profile offline_access"})


@pytest.fixture
def adapter(settings, key):
    from rook.providers.vertex_entra import EntraSessionAdapter
    transport = EntraTransport(settings, key)
    return EntraSessionAdapter(http_client_factory=lambda *args: transport), transport


@pytest.mark.parametrize("missing", ["oid", "tid"], ids=["missing-oid", "missing-tid"])
def test_missing_oid_or_tid_stops_before_exchange(adapter, settings, key, missing):
    instance, transport = adapter
    value = claims(settings)
    value.pop(missing)
    with pytest.raises(VertexAuthError):
        instance.verify_assertion(signed(key, value), settings, expected_nonce="wire-nonce", expected_principal=None, deadline=time.monotonic() + 10, cancel_check=lambda: None)
    assert all("googleapis.com" not in url for _, url, _ in transport.calls)


@pytest.mark.parametrize("change", ["issuer", "audience", "tenant", "identity", "expiry", "future", "nonce", "signature", "algorithm", "missing-key"])
def test_assertion_verifies_signature_claims_nonce_and_identity(adapter, settings, key, change):
    instance, transport = adapter
    value = claims(settings)
    changes = {"issuer": {"iss": "https://untrusted.invalid"}, "audience": {"aud": "wrong"}, "tenant": {"tid": "44444444-4444-4444-4444-444444444444"}, "identity": {"oid": "44444444-4444-4444-4444-444444444444"}, "expiry": {"exp": int(time.time()) - 61}, "future": {"nbf": int(time.time()) + 61}, "nonce": {"nonce": "wrong"}}
    value.update(changes.get(change, {}))
    signing_key = rsa.generate_private_key(public_exponent=65537, key_size=2048) if change == "signature" else key
    raw = jwt.encode(value, "synthetic-secret" * 3, algorithm="HS256", headers={"kid": "test-key"}) if change == "algorithm" else signed(signing_key, value, kid="unknown" if change == "missing-key" else "test-key")
    expected = PrivatePrincipal(settings.entra_tenant_id, claims(settings)["oid"], "bound-account")
    with pytest.raises(VertexAuthError):
        instance.verify_assertion(raw, settings, expected_nonce="wire-nonce", expected_principal=expected, deadline=time.monotonic() + 10, cancel_check=lambda: None)
    assert sum(url.endswith("/keys") for _, url, _ in transport.calls) <= 2


def _begin(instance, transport, settings):
    class Listener:
        redirect_uri = "http://localhost:45678"
        closed = False
        def wait_for_callback(self, *args, **kwargs):
            return {"code": "synthetic-auth-code", "state": flow_state[0]}
        def close(self):
            self.closed = True
    listener = Listener()
    flow_state = []
    def browser(url):
        query = parse_qs(urlsplit(url).query)
        transport.nonce = query["nonce"][0]
        flow_state.append(query["state"][0])
        assert query["scope"][0].split() and set(query["scope"][0].split()) == {"openid", "profile", "offline_access"}
        assert query["code_challenge_method"] == ["S256"]
        return True
    instance._listener_factory = lambda: listener
    instance._browser_open = browser
    candidate = instance.begin(settings, ActivationTicket("a" * 32, "b" * 32), cancel_check=lambda: None)
    assert listener.closed
    return candidate


def test_refresh_uses_explicit_account_and_required_scopes(adapter, settings):
    instance, transport = adapter
    candidate = _begin(instance, transport, settings)
    refreshed = instance.refresh(settings, candidate.serialized_cache, candidate.principal, deadline=time.monotonic() + 10, cancel_check=lambda: None)
    assert refreshed.principal == candidate.principal
    grants = [data for method, _, data in transport.calls if method == "POST"]
    assert [grant["grant_type"] for grant in grants] == ["authorization_code", "refresh_token"]
    assert all(set(grant["scope"].split()) == {"openid", "profile", "offline_access"} for grant in grants)
    assert all("client_secret" not in grant for grant in grants)


def test_refresh_missing_oid_preserves_cache(adapter, settings):
    instance, transport = adapter
    candidate = _begin(instance, transport, settings)
    before = candidate.serialized_cache
    transport.missing_claim = "oid"
    with pytest.raises(VertexAuthError):
        instance.refresh(settings, before, candidate.principal, deadline=time.monotonic() + 10, cancel_check=lambda: None)
    assert candidate.serialized_cache == before


def test_refreshed_tid_oid_must_match(adapter, settings):
    instance, transport = adapter
    candidate = _begin(instance, transport, settings)
    transport.subject_changes["oid"] = "44444444-4444-4444-4444-444444444444"
    with pytest.raises(VertexAuthError):
        instance.refresh(settings, candidate.serialized_cache, candidate.principal, deadline=time.monotonic() + 10, cancel_check=lambda: None)


def test_cancel_before_refresh_never_dispatches(adapter, settings):
    instance, transport = adapter
    candidate = _begin(instance, transport, settings)
    before = len(transport.calls)
    def cancelled():
        raise VertexAuthError("vertex_authorization_declined", "Cancelled.")
    with pytest.raises(VertexAuthError):
        instance.refresh(settings, candidate.serialized_cache, candidate.principal, deadline=time.monotonic() + 10, cancel_check=cancelled)
    assert len(transport.calls) == before


def test_browser_wait_does_not_expire_exchange_transport(settings, key):
    from rook.providers.vertex_entra import EntraSessionAdapter
    clock = [100.0]
    class DeadlineTransport(EntraTransport):
        def post(self, *args, **kwargs):
            if clock[0] >= self.deadline:
                raise VertexAuthError("vertex_token_issuance_timeout", "Timed out.")
            return super().post(*args, **kwargs)
    transport = DeadlineTransport(settings, key)
    def factory(_settings, deadline, *args):
        transport.deadline = deadline
        return transport
    instance = EntraSessionAdapter(http_client_factory=factory, monotonic=lambda: clock[0])
    class Listener:
        redirect_uri = "http://localhost:45678"
        def wait_for_callback(self, *args):
            clock[0] += 60
            return {"code": "synthetic-auth-code", "state": state[0]}
        def close(self):
            pass
    state = []
    def browser(url):
        query = parse_qs(urlsplit(url).query)
        state.append(query["state"][0])
        transport.nonce = query["nonce"][0]
        return True
    instance._listener_factory = Listener
    instance._browser_open = browser
    result = instance.begin(settings, ActivationTicket("a" * 32, "b" * 32), cancel_check=lambda: None)
    assert result.principal.oid == claims(settings)["oid"]
    assert result.operation_deadline == 190.0

@pytest.mark.parametrize('problem', ['host', 'port', 'path', 'duplicate', 'origin', 'get', 'replay'])
def test_loopback_rejects_wrong_target_duplicate_form_and_replay(problem):
    from rook.providers.vertex_entra import EntraLoopbackListener
    from http.client import HTTPConnection
    from concurrent.futures import ThreadPoolExecutor
    listener = EntraLoopbackListener()
    port = urlsplit(listener.redirect_uri).port
    def send(body='code=synthetic-code&state=synthetic-state'):
        connection = HTTPConnection('127.0.0.1', port, timeout=2)
        host = 'wrong.invalid' if problem == 'host' else f'localhost:{port + (problem == "port")}'
        path = '/wrong' if problem == 'path' else '/'
        headers = {'Host': host, 'Content-Type': 'application/x-www-form-urlencoded'}
        if problem == 'origin':
            headers['Origin'] = 'https://untrusted.invalid'
        if problem == 'duplicate':
            body += '&state=second'
        connection.request('GET' if problem == 'get' else 'POST', path, body, headers)
        response = connection.getresponse()
        result = response.status
        response.read()
        connection.close()
        return result
    try:
        with ThreadPoolExecutor() as pool:
            request = pool.submit(send)
            if problem in ('get', 'replay'):
                listener._server.handle_request()
            else:
                with pytest.raises(VertexAuthError):
                    listener.wait_for_callback(time.monotonic() + 2, lambda: None, time.monotonic)
            assert request.result() == (405 if problem == 'get' else 200 if problem == 'replay' else 400)
            if problem == 'replay':
                assert listener.wait_for_callback(time.monotonic() + 2, lambda: None, time.monotonic)['state'] == 'synthetic-state'
                with pytest.raises(VertexAuthError):
                    listener.wait_for_callback(time.monotonic() + 2, lambda: None, time.monotonic)
    finally:
        listener.close()


def test_rejected_origin_consumes_bounded_body_before_closing():
    from io import BytesIO
    from email.message import Message
    from types import SimpleNamespace
    from rook.providers.vertex_entra import _EntraCallbackHandler
    handler = object.__new__(_EntraCallbackHandler)
    body = b'code=synthetic-code&state=synthetic-state'
    handler.rfile = BytesIO(body)
    handler.headers = Message()
    for key, value in {'Host': 'localhost:45678', 'Content-Type': 'application/x-www-form-urlencoded', 'Content-Length': str(len(body)), 'Origin': 'https://untrusted.invalid'}.items():
        handler.headers[key] = value
    handler.path = '/'
    handler.server = SimpleNamespace(server_address=('127.0.0.1', 45678), callback=None, callback_error=False)
    errors = []
    handler.send_error = lambda status, *args: errors.append(status)
    handler.do_POST()
    assert errors == [400] and handler.server.callback is None and handler.server.callback_error
    assert handler.rfile.tell() == len(body)


def test_wrong_state_rejected_by_msal_before_token_post(adapter, settings):
    instance, transport = adapter
    class Listener:
        redirect_uri = 'http://localhost:45678'
        closed = False
        def wait_for_callback(self, *args):
            return {'code': 'synthetic-code', 'state': 'wrong-state'}
        def close(self):
            self.closed = True
    listener = Listener()
    instance._listener_factory = lambda: listener
    instance._browser_open = lambda _: True
    with pytest.raises(VertexAuthError):
        instance.begin(settings, ActivationTicket('a' * 32, 'b' * 32), cancel_check=lambda: None)
    assert listener.closed and not any(method == 'POST' for method, _, _ in transport.calls)


def test_interaction_deadline_closes_listener(settings, key):
    from rook.providers.vertex_entra import EntraSessionAdapter
    clock = [100.0]
    transport = EntraTransport(settings, key)
    class Listener:
        redirect_uri = 'http://localhost:45678'
        closed = False
        def wait_for_callback(self, deadline, cancel, monotonic):
            from rook.providers.vertex_entra import _check
            assert deadline == 280
            clock[0] = 280
            _check(deadline, cancel, monotonic)
        def close(self):
            self.closed = True
    listener = Listener()
    instance = EntraSessionAdapter(http_client_factory=lambda *args: transport, monotonic=lambda: clock[0], listener_factory=lambda: listener, browser_open=lambda _: True)
    with pytest.raises(VertexAuthError) as error:
        instance.begin(settings, ActivationTicket('a' * 32, 'b' * 32), cancel_check=lambda: None)
    assert error.value.code == 'vertex_token_issuance_timeout'
    assert listener.closed and not any(method == 'POST' for method, _, _ in transport.calls)


@pytest.mark.parametrize('failure', ['redirect', 'oversize', 'request-deadline', 'aggregate-deadline', 'cancel-after-response', 'cancel-before-dispatch', 'arbitrary-url', 'invalid-port'])
def test_bounded_http_refuses_unsafe_or_late_response(settings, failure):
    from rook.providers.vertex_entra import BoundedEntraHttpClient
    import io
    clock = [100.0]
    cancelled = [failure == 'cancel-before-dispatch']
    calls = []
    class Stream(io.BytesIO):
        headers = {}
        def getcode(self):
            return 302 if failure == 'redirect' else 200
        def read(self, limit):
            chunk = super().read(limit)
            if failure in ('request-deadline', 'aggregate-deadline'):
                clock[0] += 21
            if failure == 'cancel-after-response':
                cancelled[0] = True
            return chunk
    class Opener:
        def open(self, request, timeout):
            calls.append(request)
            assert timeout <= 20
            return Stream(b'x' * (1024 * 1024 + 1) if failure == 'oversize' else b'{}')
    def cancel():
        if cancelled[0]:
            raise VertexAuthError('vertex_authorization_declined', 'Cancelled.')
    client = BoundedEntraHttpClient(settings, 105 if failure == 'aggregate-deadline' else 130, cancel, lambda: clock[0], opener=Opener())
    url = settings.authority + '/oauth2/v2.0/token'
    if failure == 'arbitrary-url':
        url = 'https://untrusted.invalid/token'
    if failure == 'invalid-port':
        url = 'https://login.microsoftonline.com:invalid/token'
    with pytest.raises(VertexAuthError):
        client.post(url, data={'code': 'synthetic-secret'})
    assert len(calls) == (0 if failure in ('arbitrary-url', 'invalid-port', 'cancel-before-dispatch') else 1)


def test_refresh_deadline_and_cancel_after_token_do_not_return_candidate(adapter, settings):
    instance, transport = adapter
    candidate = _begin(instance, transport, settings)
    original_post = transport.post
    cancelled = [False]
    def post(*args, **kwargs):
        result = original_post(*args, **kwargs)
        cancelled[0] = True
        return result
    transport.post = post
    def check():
        if cancelled[0]:
            raise VertexAuthError('vertex_authorization_declined', 'Cancelled.')
    with pytest.raises(VertexAuthError):
        instance.refresh(settings, candidate.serialized_cache, candidate.principal, deadline=time.monotonic() + 30, cancel_check=check)
    before = len(transport.calls)
    with pytest.raises(VertexAuthError):
        instance.refresh(settings, candidate.serialized_cache, candidate.principal, deadline=time.monotonic(), cancel_check=lambda: None)
    assert len(transport.calls) == before


def test_candidate_serialization_bound_and_cancellation(adapter, settings):
    instance, _ = adapter
    from rook.providers.vertex_workforce_contract import VerifiedEntraAssertion
    principal = PrivatePrincipal(settings.entra_tenant_id, claims(settings)['oid'], 'bound-account')
    verified = VerifiedEntraAssertion('synthetic-assertion', principal, int(time.time()) + 60)
    cancelled = [False]
    class Cache:
        def serialize(self):
            return json.dumps({'cache': 'x' * (256 * 1024)})
    with pytest.raises(VertexAuthError):
        instance._candidate(Cache(), verified, time.monotonic() + 30, lambda: None)
    class LateCache:
        def serialize(self):
            cancelled[0] = True
            return '{}'
    def cancel():
        if cancelled[0]:
            raise VertexAuthError('vertex_authorization_declined', 'Cancelled.')
    with pytest.raises(VertexAuthError):
        instance._candidate(LateCache(), verified, time.monotonic() + 30, cancel)


def test_msal_pii_logging_does_not_propagate(adapter, settings, caplog):
    import logging
    instance, transport = adapter
    _begin(instance, transport, settings)
    logging.getLogger('msal.synthetic').warning('private-sentinel')
    assert 'private-sentinel' not in caplog.text
