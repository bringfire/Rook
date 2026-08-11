"""Bounded Google desktop OAuth for the Vertex provider."""

from __future__ import annotations

import base64
import hashlib
import secrets
import time
import webbrowser
from dataclasses import dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Callable
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx

from .vertex_auth import VERTEX_SCOPE, VertexAuthError


_AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
_DEFAULT_TIMEOUT_SECONDS = 180


def _failure(code: str, message: str) -> VertexAuthError:
    return VertexAuthError(code, message)


def _request_failed() -> VertexAuthError:
    return _failure(
        "vertex_request_failed",
        "Google authorization could not be completed safely.",
    )


@dataclass(frozen=True)
class DesktopOAuthClient:
    client_id: str
    client_secret: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.client_id, str)
            or not self.client_id
            or not isinstance(self.client_secret, str)
            or not self.client_secret
        ):
            raise _request_failed()


@dataclass(frozen=True)
class _OAuthDependencies:
    listener_factory: Callable[[], object]
    browser_open: Callable[[str], bool]
    post_form: Callable[[str, dict[str, str], float], tuple[int, object]]
    verify_authorized_user: Callable[[dict[str, str], float], None]
    random_token: Callable[[int], str]
    monotonic: Callable[[], float]


class _CallbackHandler(BaseHTTPRequestHandler):
    server: "_CallbackServer"

    def do_GET(self) -> None:
        self.server.callback = parse_qs(
            urlsplit(self.path).query,
            keep_blank_values=True,
        )
        body = b"Rook received the Google authorization response. You may close this tab."
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *_args: object) -> None:
        return


class _CallbackServer(HTTPServer):
    callback: dict[str, list[str]] | None = None
    request_deadline: float | None = None

    def get_request(self):
        request, client_address = super().get_request()
        deadline = self.request_deadline
        if deadline is not None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                request.close()
                raise TimeoutError
            request.settimeout(remaining)
        return request, client_address


class _LoopbackListener:
    def __init__(self) -> None:
        self._server = _CallbackServer(("127.0.0.1", 0), _CallbackHandler)
        port = self._server.server_address[1]
        self.redirect_uri = f"http://127.0.0.1:{port}"
        self._closed = False

    def wait_for_callback(self, timeout_seconds: float) -> dict[str, list[str]]:
        self._server.request_deadline = time.monotonic() + timeout_seconds
        self._server.timeout = timeout_seconds
        try:
            self._server.handle_request()
        finally:
            self._server.request_deadline = None
        if self._server.callback is None:
            raise TimeoutError
        return self._server.callback

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._server.server_close()


def _post_form(
    url: str,
    data: dict[str, str],
    timeout_seconds: float,
) -> tuple[int, object]:
    with httpx.Client(timeout=timeout_seconds) as client:
        response = client.post(url, data=data)
    try:
        payload = response.json()
    except ValueError:
        payload = None
    return response.status_code, payload


def _verify_authorized_user(
    credentials: dict[str, str],
    timeout_seconds: float,
) -> None:
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials

        verified = Credentials.from_authorized_user_info(
            credentials,
            scopes=[VERTEX_SCOPE],
        )
        request = Request()

        def bounded_request(
            url,
            method="GET",
            body=None,
            headers=None,
            timeout=120,
            **kwargs,
        ):
            return request(
                url,
                method=method,
                body=body,
                headers=headers,
                timeout=min(float(timeout), timeout_seconds),
                **kwargs,
            )

        verified.refresh(bounded_request)
        expiry = verified.expiry
        if expiry is not None and expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        if (
            not isinstance(verified.token, str)
            or not verified.token
            or expiry is None
            or expiry <= datetime.now(timezone.utc)
        ):
            raise _request_failed()
    except VertexAuthError:
        raise
    except Exception as exc:
        raise _request_failed() from exc


def _default_dependencies() -> _OAuthDependencies:
    return _OAuthDependencies(
        listener_factory=_LoopbackListener,
        browser_open=lambda url: webbrowser.open(url, new=1),
        post_form=_post_form,
        verify_authorized_user=_verify_authorized_user,
        random_token=secrets.token_urlsafe,
        monotonic=time.monotonic,
    )


def _validate_redirect_uri(value: object) -> str:
    if not isinstance(value, str):
        raise _request_failed()
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise _request_failed() from exc
    if (
        parsed.scheme != "http"
        or parsed.hostname != "127.0.0.1"
        or parsed.username is not None
        or parsed.password is not None
        or not isinstance(port, int)
        or port <= 0
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
    ):
        raise _request_failed()
    return value


def _one(callback: object, key: str, *, required: bool = True) -> str | None:
    if not isinstance(callback, dict):
        raise _request_failed()
    values = callback.get(key)
    if values is None and not required:
        return None
    if (
        not isinstance(values, list)
        or len(values) != 1
        or not isinstance(values[0], str)
        or not values[0]
    ):
        raise _request_failed()
    return values[0]


def _authorized_user_from_token(
    payload: object,
    client: DesktopOAuthClient,
) -> dict[str, str]:
    if not isinstance(payload, dict):
        raise _request_failed()
    access_token = payload.get("access_token")
    refresh_token = payload.get("refresh_token")
    expires_in = payload.get("expires_in")
    scope = payload.get("scope")
    if (
        payload.get("token_type") != "Bearer"
        or not isinstance(access_token, str)
        or not access_token
        or not isinstance(refresh_token, str)
        or not refresh_token
        or type(expires_in) is not int
        or expires_in <= 0
        or not isinstance(scope, str)
        or set(scope.split()) != {VERTEX_SCOPE}
    ):
        raise _request_failed()
    return {
        "type": "authorized_user",
        "client_id": client.client_id,
        "client_secret": client.client_secret,
        "refresh_token": refresh_token,
    }


def authorize_desktop(
    client: DesktopOAuthClient,
    *,
    dependencies: _OAuthDependencies | None = None,
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, str]:
    """Complete one explicit desktop OAuth attempt and return refresh material."""

    if not isinstance(client, DesktopOAuthClient) or (
        not isinstance(timeout_seconds, (int, float))
        or isinstance(timeout_seconds, bool)
        or not 0 < timeout_seconds <= _DEFAULT_TIMEOUT_SECONDS
    ):
        raise _request_failed()
    runtime = dependencies or _default_dependencies()
    listener = None
    try:
        deadline = runtime.monotonic() + timeout_seconds

        def remaining() -> float:
            value = deadline - runtime.monotonic()
            if value <= 0:
                raise _failure(
                    "vertex_authorization_declined",
                    "Google authorization was cancelled or timed out.",
                )
            return value

        listener = runtime.listener_factory()
        redirect_uri = _validate_redirect_uri(getattr(listener, "redirect_uri", None))
        state = runtime.random_token(32)
        verifier = runtime.random_token(64)
        if (
            not isinstance(state, str)
            or not state
            or not isinstance(verifier, str)
            or not 43 <= len(verifier) <= 128
        ):
            raise _request_failed()
        challenge = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode("ascii")).digest()
        ).decode("ascii").rstrip("=")
        authorization_url = _AUTHORIZATION_ENDPOINT + "?" + urlencode(
            {
                "access_type": "offline",
                "client_id": client.client_id,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "prompt": "consent",
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": VERTEX_SCOPE,
                "state": state,
            }
        )
        if runtime.browser_open(authorization_url) is False:
            raise _failure(
                "vertex_authorization_declined",
                "Google authorization was cancelled before completion.",
            )
        try:
            callback = listener.wait_for_callback(remaining())
        except TimeoutError as exc:
            raise _failure(
                "vertex_authorization_declined",
                "Google authorization was cancelled or timed out.",
            ) from exc
        callback_state = _one(callback, "state")
        if not secrets.compare_digest(callback_state, state):
            raise _request_failed()
        callback_error = _one(callback, "error", required=False)
        callback_code = _one(callback, "code", required=False)
        if callback_error is not None:
            if callback_code is not None:
                raise _request_failed()
            if callback_error == "access_denied":
                raise _failure(
                    "vertex_authorization_declined",
                    "Google authorization was declined.",
                )
            if callback_error == "admin_policy_enforced":
                raise _failure(
                    "vertex_oauth_admin_blocked",
                    "A Google Workspace administrator blocked Rook authorization.",
                )
            raise _request_failed()
        if callback_code is None:
            raise _request_failed()
        status_code, payload = runtime.post_form(
            _TOKEN_ENDPOINT,
            {
                "client_id": client.client_id,
                "client_secret": client.client_secret,
                "code": callback_code,
                "code_verifier": verifier,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
            },
            remaining(),
        )
        if status_code != 200:
            raise _request_failed()
        credentials = _authorized_user_from_token(payload, client)
        runtime.verify_authorized_user(credentials, remaining())
        return credentials
    except VertexAuthError:
        raise
    except Exception as exc:
        raise _request_failed() from exc
    finally:
        if listener is not None:
            try:
                listener.close()
            except Exception:
                pass
