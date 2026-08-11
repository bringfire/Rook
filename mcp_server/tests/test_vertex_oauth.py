from __future__ import annotations

import importlib
import socket
import threading
from urllib.parse import parse_qs, urlsplit

import pytest


def _oauth():
    return importlib.import_module("rook.providers.vertex_oauth")


class _FakeListener:
    def __init__(self, captured, *, redirect_uri="http://127.0.0.1:54321", callback=None):
        self.captured = captured
        self.redirect_uri = redirect_uri
        self.callback = callback
        self.closed = False
        self.wait_calls = []

    def wait_for_callback(self, timeout_seconds):
        self.wait_calls.append(timeout_seconds)
        if self.callback is TimeoutError:
            raise TimeoutError
        if callable(self.callback):
            return self.callback()
        if self.callback is not None:
            return self.callback
        query = parse_qs(urlsplit(self.captured["authorization_url"]).query)
        return {"state": [query["state"][0]], "code": ["authorization-code"]}

    def close(self):
        self.closed = True


class _OAuthHarness:
    def __init__(self, *, callback=None, redirect_uri="http://127.0.0.1:54321"):
        self.captured = {}
        self.listener = _FakeListener(
            self.captured,
            redirect_uri=redirect_uri,
            callback=callback,
        )
        self.token_payload = {
            "access_token": "short-lived-access-token",
            "expires_in": 3600,
            "refresh_token": "long-lived-refresh-token",
            "scope": "https://www.googleapis.com/auth/cloud-platform",
            "token_type": "Bearer",
        }
        self.token_status = 200
        self.verified = []
        self.browser_result = True
        self.random_values = iter(["state-value", "v" * 64])
        self.clock = lambda: 0.0

    def browser_open(self, url):
        self.captured["authorization_url"] = url
        return self.browser_result

    def post_form(self, url, data, timeout_seconds):
        self.captured["token_request"] = (url, dict(data), timeout_seconds)
        return self.token_status, self.token_payload

    def verify_authorized_user(self, credentials, timeout_seconds):
        self.verified.append((dict(credentials), timeout_seconds))

    def random_token(self, _bytes):
        return next(self.random_values)

    def dependencies(self, oauth):
        return oauth._OAuthDependencies(
            listener_factory=lambda: self.listener,
            browser_open=self.browser_open,
            post_form=self.post_form,
            verify_authorized_user=self.verify_authorized_user,
            random_token=self.random_token,
            monotonic=self.clock,
        )


def _client(oauth):
    return oauth.DesktopOAuthClient(
        client_id="rook-desktop.apps.googleusercontent.com",
        client_secret="desktop-client-material",
    )


def test_desktop_oauth_uses_pkce_loopback_state_and_offline_access():
    oauth = _oauth()
    harness = _OAuthHarness()

    credentials = oauth.authorize_desktop(
        _client(oauth),
        dependencies=harness.dependencies(oauth),
        timeout_seconds=120,
    )

    query = parse_qs(urlsplit(harness.captured["authorization_url"]).query)
    assert query == {
        "access_type": ["offline"],
        "client_id": ["rook-desktop.apps.googleusercontent.com"],
        "code_challenge": ["w1TpKUdYE9hUAcNSeeSRFioHDxfUxuHho_JHAfZ_vDM"],
        "code_challenge_method": ["S256"],
        "prompt": ["consent"],
        "redirect_uri": ["http://127.0.0.1:54321"],
        "response_type": ["code"],
        "scope": ["https://www.googleapis.com/auth/cloud-platform"],
        "state": ["state-value"],
    }
    token_url, token_form, token_timeout = harness.captured["token_request"]
    assert token_url == "https://oauth2.googleapis.com/token"
    assert token_form == {
        "client_id": "rook-desktop.apps.googleusercontent.com",
        "client_secret": "desktop-client-material",
        "code": "authorization-code",
        "code_verifier": "v" * 64,
        "grant_type": "authorization_code",
        "redirect_uri": "http://127.0.0.1:54321",
    }
    assert token_timeout == 120
    assert credentials == {
        "type": "authorized_user",
        "client_id": "rook-desktop.apps.googleusercontent.com",
        "client_secret": "desktop-client-material",
        "refresh_token": "long-lived-refresh-token",
    }
    assert harness.verified == [(credentials, 120)]
    assert harness.listener.wait_calls == [120]
    assert harness.listener.closed is True


@pytest.mark.parametrize(
    ("callback", "expected_code"),
    [
        ({"state": ["wrong"], "code": ["code"]}, "vertex_request_failed"),
        ({"state": ["state-value"]}, "vertex_request_failed"),
        (
            {"state": ["state-value"], "code": ["one", "two"]},
            "vertex_request_failed",
        ),
        (
            {"state": ["state-value", "state-value"], "code": ["code"]},
            "vertex_request_failed",
        ),
        (
            {"state": ["state-value"], "error": ["access_denied"]},
            "vertex_authorization_declined",
        ),
        (
            {"state": ["state-value"], "error": ["admin_policy_enforced"]},
            "vertex_oauth_admin_blocked",
        ),
        (
            {"state": ["state-value"], "error": ["unknown_error"]},
            "vertex_request_failed",
        ),
        (TimeoutError, "vertex_authorization_declined"),
    ],
)
def test_desktop_oauth_rejects_invalid_declined_admin_and_timeout_callbacks(
    callback,
    expected_code,
):
    oauth = _oauth()
    harness = _OAuthHarness(callback=callback)

    with pytest.raises(oauth.VertexAuthError) as exc_info:
        oauth.authorize_desktop(
            _client(oauth),
            dependencies=harness.dependencies(oauth),
            timeout_seconds=30,
        )

    assert exc_info.value.code == expected_code
    assert harness.listener.closed is True
    assert "token_request" not in harness.captured


@pytest.mark.parametrize(
    "redirect_uri",
    [
        "http://localhost:54321",
        "http://0.0.0.0:54321",
        "https://127.0.0.1:54321",
        "http://user@127.0.0.1:54321",
        "http://127.0.0.1:54321/callback?secret=yes",
    ],
)
def test_desktop_oauth_rejects_every_noncanonical_loopback_listener(redirect_uri):
    oauth = _oauth()
    harness = _OAuthHarness(redirect_uri=redirect_uri)

    with pytest.raises(oauth.VertexAuthError) as exc_info:
        oauth.authorize_desktop(_client(oauth), dependencies=harness.dependencies(oauth))

    assert exc_info.value.code == "vertex_request_failed"
    assert harness.listener.closed is True
    assert "authorization_url" not in harness.captured


@pytest.mark.parametrize(
    "token_payload",
    [
        {},
        {
            "access_token": "token",
            "expires_in": 3600,
            "refresh_token": "refresh",
            "scope": "https://www.googleapis.com/auth/cloud-platform",
            "token_type": "bearer",
        },
        {
            "access_token": "",
            "expires_in": 3600,
            "refresh_token": "refresh",
            "scope": "https://www.googleapis.com/auth/cloud-platform",
            "token_type": "Bearer",
        },
        {
            "access_token": "token",
            "expires_in": 0,
            "refresh_token": "refresh",
            "scope": "https://www.googleapis.com/auth/cloud-platform",
            "token_type": "Bearer",
        },
        {
            "access_token": "token",
            "expires_in": 3600,
            "refresh_token": "",
            "scope": "https://www.googleapis.com/auth/cloud-platform",
            "token_type": "Bearer",
        },
        {
            "access_token": "token",
            "expires_in": 3600,
            "refresh_token": "refresh",
            "scope": "openid https://www.googleapis.com/auth/cloud-platform",
            "token_type": "Bearer",
        },
        {
            "access_token": "token",
            "expires_in": 3600,
            "refresh_token": "refresh",
            "scope": "",
            "token_type": "Bearer",
        },
    ],
)
def test_desktop_oauth_rejects_incoherent_token_responses(token_payload):
    oauth = _oauth()
    harness = _OAuthHarness()
    harness.token_payload = token_payload

    with pytest.raises(oauth.VertexAuthError) as exc_info:
        oauth.authorize_desktop(_client(oauth), dependencies=harness.dependencies(oauth))

    assert exc_info.value.code == "vertex_request_failed"
    assert harness.verified == []
    assert harness.listener.closed is True


def test_desktop_oauth_rejects_failed_exchange_and_refresh_without_raw_details():
    oauth = _oauth()
    exchange = _OAuthHarness()
    exchange.token_status = 400
    exchange.token_payload = {"error": "invalid_grant", "secret": "do-not-expose"}

    with pytest.raises(oauth.VertexAuthError) as exchange_error:
        oauth.authorize_desktop(_client(oauth), dependencies=exchange.dependencies(oauth))

    assert exchange_error.value.code == "vertex_request_failed"
    assert "do-not-expose" not in exchange_error.value.public_message

    refresh = _OAuthHarness()

    def fail_refresh(_credentials, _timeout_seconds):
        raise RuntimeError("refresh-token-must-not-escape")

    dependencies = refresh.dependencies(oauth)
    dependencies = oauth._OAuthDependencies(
        listener_factory=dependencies.listener_factory,
        browser_open=dependencies.browser_open,
        post_form=dependencies.post_form,
        verify_authorized_user=fail_refresh,
        random_token=dependencies.random_token,
        monotonic=dependencies.monotonic,
    )
    with pytest.raises(oauth.VertexAuthError) as refresh_error:
        oauth.authorize_desktop(_client(oauth), dependencies=dependencies)

    assert refresh_error.value.code == "vertex_request_failed"
    assert "refresh-token-must-not-escape" not in refresh_error.value.public_message
    assert refresh.listener.closed is True


def test_desktop_oauth_closes_listener_when_browser_cannot_open():
    oauth = _oauth()
    harness = _OAuthHarness()
    harness.browser_result = False

    with pytest.raises(oauth.VertexAuthError) as exc_info:
        oauth.authorize_desktop(_client(oauth), dependencies=harness.dependencies(oauth))

    assert exc_info.value.code == "vertex_authorization_declined"
    assert harness.listener.closed is True


def test_desktop_oauth_uses_one_total_budget_across_wait_exchange_and_refresh():
    oauth = _oauth()
    harness = _OAuthHarness()
    clock_values = iter([10.0, 10.0, 20.0, 30.0])
    harness.clock = lambda: next(clock_values)

    credentials = oauth.authorize_desktop(
        _client(oauth),
        dependencies=harness.dependencies(oauth),
        timeout_seconds=60,
    )

    assert credentials["type"] == "authorized_user"
    assert harness.listener.wait_calls == [60]
    assert harness.captured["token_request"][2] == 50
    assert harness.verified == [(credentials, 40)]


@pytest.mark.parametrize(
    "timeout_seconds",
    [float("nan"), float("inf"), 180.0001, 181],
)
def test_desktop_oauth_rejects_nonfinite_or_excessive_total_budget(timeout_seconds):
    oauth = _oauth()
    harness = _OAuthHarness()

    with pytest.raises(oauth.VertexAuthError) as exc_info:
        oauth.authorize_desktop(
            _client(oauth),
            dependencies=harness.dependencies(oauth),
            timeout_seconds=timeout_seconds,
        )

    assert exc_info.value.code == "vertex_request_failed"
    assert harness.listener.wait_calls == []


def test_real_loopback_listener_binds_an_ephemeral_ipv4_port_and_closes():
    oauth = _oauth()

    listener = oauth._LoopbackListener()
    try:
        parsed = urlsplit(listener.redirect_uri)
        assert parsed.scheme == "http"
        assert parsed.hostname == "127.0.0.1"
        assert isinstance(parsed.port, int) and parsed.port > 0
    finally:
        listener.close()


def test_real_loopback_listener_bounds_a_stalled_accepted_request():
    oauth = _oauth()
    listener = oauth._LoopbackListener()
    parsed = urlsplit(listener.redirect_uri)
    outcomes = []

    def wait_for_callback():
        try:
            listener.wait_for_callback(0.2)
        except Exception as exc:
            outcomes.append(exc)

    waiter = threading.Thread(target=wait_for_callback)
    client = None
    try:
        waiter.start()
        client = socket.create_connection(("127.0.0.1", parsed.port), timeout=1)
        client.sendall(b"GET /?state=issued HTTP/1.1\r\nHost:")
        waiter.join(timeout=0.8)

        assert not waiter.is_alive()
        assert len(outcomes) == 1
        assert isinstance(outcomes[0], TimeoutError)
    finally:
        if client is not None:
            client.close()
        listener.close()
        waiter.join(timeout=1)
