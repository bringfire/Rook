"""MSAL public-client sessions with bounded I/O and independently verified identity."""
from __future__ import annotations

from dataclasses import replace
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import logging
import math
import time
from typing import Callable
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
import webbrowser

from .vertex_auth import VertexAuthError
from .vertex_workforce_contract import (
    ActivationTicket, CACHE_LIMIT, EntraSessionCandidate, FirmSettings, PrivatePrincipal,
    TOKEN_LIMIT, VerifiedEntraAssertion, auth_error, bounded_text, guid, json_object,
)


def _check(deadline, cancel_check, monotonic):
    cancel_check()
    if not math.isfinite(deadline) or monotonic() >= deadline:
        raise auth_error("vertex_token_issuance_timeout")


def _allowed_url(url, settings, *, authorize=False):
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError:
        raise auth_error() from None
    paths = {
        f"/{settings.entra_tenant_id}/v2.0/.well-known/openid-configuration",
        f"/{settings.entra_tenant_id}/oauth2/v2.0/token",
        f"/{settings.entra_tenant_id}/discovery/v2.0/keys",
        "/common/discovery/v2.0/keys",  # Microsoft's signing-key endpoint, not account discovery.
    }
    if authorize:
        paths = {f"/{settings.entra_tenant_id}/oauth2/v2.0/authorize"}
    if parsed.scheme != "https" or parsed.hostname != "login.microsoftonline.com" or parsed.username or parsed.password or port not in (None, 443) or parsed.path not in paths or parsed.fragment:
        raise auth_error()


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class _JsonResponse:
    def __init__(self, status, headers, body):
        self.status_code = status
        self.headers = dict(headers)
        self.text = body.decode("utf-8")
        self._body = body

    def json(self):
        return json_object(self._body, TOKEN_LIMIT)


class BoundedEntraHttpClient:
    """MSAL's public HTTP interface; no request logging, redirects or automatic retries."""
    def __init__(self, settings, deadline, cancel_check, monotonic=time.monotonic, *, opener=None):
        self.settings, self.deadline = settings, deadline
        self.cancel_check, self.monotonic = cancel_check, monotonic
        self.opener = opener or build_opener(_NoRedirect())

    def get(self, url, **kwargs):
        return self._request("GET", url, **kwargs)

    def post(self, url, **kwargs):
        return self._request("POST", url, **kwargs)

    def _request(self, method, url, data=None, headers=None, params=None, **kwargs):
        deadline = min(self.deadline, self.monotonic() + 20)
        _check(deadline, self.cancel_check, self.monotonic)
        _allowed_url(url, self.settings)
        if params:
            url += ("&" if "?" in url else "?") + urlencode(params)
        body = urlencode(data, doseq=True).encode() if data is not None else None
        if body is not None and len(body) > TOKEN_LIMIT:
            raise auth_error()
        request_headers = dict(headers or {})
        if body is not None:
            request_headers["Content-Type"] = "application/x-www-form-urlencoded"
        try:
            try:
                _check(deadline, self.cancel_check, self.monotonic)
                response = self.opener.open(Request(url, data=body, headers=request_headers, method=method), timeout=deadline - self.monotonic())
            except HTTPError as error:
                response = error
            with response:
                status = response.getcode()
                if 300 <= status < 400:
                    raise auth_error()
                payload = bytearray()
                while True:
                    _check(deadline, self.cancel_check, self.monotonic)
                    # read() buffers until its requested length and can hide a
                    # continuously dripping peer from the aggregate checks.
                    chunk = response.read1(min(65536, TOKEN_LIMIT + 1 - len(payload)))
                    if not chunk:
                        break
                    payload.extend(chunk)
                    if len(payload) > TOKEN_LIMIT:
                        raise auth_error()
                _check(deadline, self.cancel_check, self.monotonic)
                return _JsonResponse(status, response.headers, bytes(payload))
        except VertexAuthError:
            raise
        except Exception:
            raise auth_error() from None


class _EntraCallbackHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        self.send_error(405)

    def do_POST(self):
        try:
            expected_host = f"localhost:{self.server.server_address[1]}"
            lengths = self.headers.get_all("Content-Length", [])
            if self.headers.get("Transfer-Encoding") or len(lengths) != 1 or not lengths[0].isdigit() or not 0 < int(lengths[0]) <= 64 * 1024:
                raise auth_error()
            # Consume only a bounded, length-delimited body before rejecting its
            # target. Closing with unread bytes can reset a Windows connection
            # before the browser receives the fixed rejection response.
            raw = self.rfile.read(int(lengths[0]))
            if len(raw) != int(lengths[0]):
                raise auth_error()
            if self.path != "/" or self.headers.get("Host") != expected_host or self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/x-www-form-urlencoded":
                raise auth_error()
            if self.headers.get("Origin") not in (None, "https://login.microsoftonline.com"):
                raise auth_error()
            fields = parse_qs(raw.decode("utf-8"), keep_blank_values=True, strict_parsing=True, max_num_fields=16)
            if set(fields) - {"code", "state", "session_state", "error", "error_description", "error_uri"} or any(len(values) != 1 or not values[0] for values in fields.values()) or "state" not in fields or (("code" in fields) == ("error" in fields)):
                raise auth_error()
            if self.server.callback is not None:
                raise auth_error()
            self.server.callback = {key: values[0] for key, values in fields.items()}
            body = b"Rook received the firm sign-in response. You may close this tab."
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception:
            self.server.callback_error = True
            self.send_error(400, "Invalid firm sign-in callback")


class _EntraCallbackServer(HTTPServer):
    callback = None
    callback_error = False

    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(0.5)
        return connection, address


class EntraLoopbackListener:
    def __init__(self):
        self._server = _EntraCallbackServer(("127.0.0.1", 0), _EntraCallbackHandler)
        self._server.timeout = 0.05
        self.redirect_uri = f"http://localhost:{self._server.server_address[1]}"
        self._consumed = False

    def wait_for_callback(self, deadline, cancel_check, monotonic):
        if self._consumed:
            raise auth_error()
        while self._server.callback is None:
            _check(deadline, cancel_check, monotonic)
            self._server.handle_request()
            if self._server.callback_error:
                raise auth_error()
        self._consumed = True
        _check(deadline, cancel_check, monotonic)
        return self._server.callback

    def close(self):
        self._server.server_close()


class EntraSessionAdapter:
    def __init__(self, *, http_client_factory=None, browser_open=webbrowser.open,
                 listener_factory=EntraLoopbackListener, monotonic=time.monotonic,
                 unix_time=time.time):
        self._http_client_factory = http_client_factory or BoundedEntraHttpClient
        self._browser_open, self._listener_factory = browser_open, listener_factory
        self._monotonic, self._unix_time = monotonic, unix_time
        self._keys = {}

    def _http(self, settings, deadline, cancel_check):
        _check(deadline, cancel_check, self._monotonic)
        return self._http_client_factory(settings, deadline, cancel_check, self._monotonic)

    def _document(self, http, url, settings, deadline, cancel_check):
        _check(deadline, cancel_check, self._monotonic)
        _allowed_url(url, settings)
        response = http.get(url)
        _check(deadline, cancel_check, self._monotonic)
        if response.status_code != 200:
            raise auth_error()
        return json_object(response.text.encode(), TOKEN_LIMIT)

    def verify_assertion(self, raw: str, settings: FirmSettings, *, expected_nonce: str | None,
                         expected_principal: PrivatePrincipal | None, deadline: float,
                         cancel_check: Callable[[], None]) -> VerifiedEntraAssertion:
        _check(deadline, cancel_check, self._monotonic)
        try:
            import jwt
            bounded_text(raw, TOKEN_LIMIT)
            header = jwt.get_unverified_header(raw)
            if header.get("alg") != "RS256" or not isinstance(header.get("kid"), str) or not 0 < len(header["kid"]) <= 128 or header.get("crit"):
                raise auth_error("vertex_firm_sign_in_required")
            http = self._http(settings, deadline, cancel_check)
            cached = self._keys.get(settings.entra_tenant_id)
            keys = cached[1] if cached is not None and cached[0] > self._monotonic() else None
            selected = None
            for _ in range(2):
                if keys is None:
                    metadata = self._document(http, settings.authority + "/v2.0/.well-known/openid-configuration", settings, deadline, cancel_check)
                    if metadata.get("issuer") != settings.authority + "/v2.0" or not isinstance(metadata.get("jwks_uri"), str):
                        raise auth_error()
                    keys = self._document(http, metadata["jwks_uri"], settings, deadline, cancel_check).get("keys")
                    if not isinstance(keys, list) or len(keys) > 128:
                        raise auth_error()
                    self._keys[settings.entra_tenant_id] = (self._monotonic() + 600, keys)
                matching = [key for key in keys if isinstance(key, dict) and key.get("kid") == header["kid"] and key.get("kty") == "RSA" and key.get("alg", "RS256") == "RS256" and key.get("use", "sig") == "sig"]
                if len(matching) == 1:
                    selected = jwt.PyJWK.from_dict(matching[0], algorithm="RS256").key
                    break
                keys = None
            if selected is None:
                raise auth_error("vertex_firm_sign_in_required")
            value = jwt.decode(raw, selected, algorithms=["RS256"], issuer=settings.authority + "/v2.0", audience=settings.entra_client_id,
                               options={"verify_exp": False, "verify_nbf": False, "verify_iat": False,
                                        "require": ["iss", "aud", "tid", "oid", "exp", "nbf", "iat"]})
            now = self._unix_time()
            if value["aud"] != settings.entra_client_id or guid(value["tid"]) != settings.entra_tenant_id or any(type(value[name]) is not int for name in ("exp", "nbf", "iat")) or value["exp"] <= now or value["nbf"] > now + 60 or value["iat"] > now + 60:
                raise auth_error("vertex_firm_sign_in_required")
            if expected_nonce is not None and value.get("nonce") != expected_nonce:
                raise auth_error("vertex_firm_sign_in_required")
            principal = PrivatePrincipal(value["tid"], value["oid"], expected_principal.msal_account_key if expected_principal else "unbound")
            if expected_principal is not None and principal != expected_principal:
                raise auth_error("vertex_authorization_changed")
            _check(deadline, cancel_check, self._monotonic)
            return VerifiedEntraAssertion(raw, principal, value["exp"])
        except VertexAuthError:
            raise
        except Exception:
            raise auth_error("vertex_firm_sign_in_required") from None

    def _application(self, settings, serialized_cache, deadline, cancel_check):
        try:
            import msal
            from importlib.metadata import version
            if version("msal") != "1.39.0":
                raise auth_error()
            logger = logging.getLogger("msal")
            logger.handlers = [logging.NullHandler()]
            logger.propagate = False
            cache = msal.SerializableTokenCache()
            if serialized_cache is not None:
                json_object(bounded_text(serialized_cache, CACHE_LIMIT).encode(), CACHE_LIMIT)
                cache.deserialize(serialized_cache)
            http = self._http(settings, deadline, cancel_check)
            app = msal.PublicClientApplication(settings.entra_client_id, authority=settings.authority,
                token_cache=cache, http_client=http,
                instance_discovery=False, enable_broker_on_windows=False, enable_pii_log=False)
            _check(deadline, cancel_check, self._monotonic)
            return app, cache, http
        except VertexAuthError:
            raise
        except ImportError:
            raise VertexAuthError("vertex_auth_dependency_missing", "The installed firm sign-in dependency is unavailable.") from None
        except Exception:
            raise auth_error("vertex_firm_sign_in_required") from None

    def _candidate(self, cache, verified, deadline, cancel_check):
        _check(deadline, cancel_check, self._monotonic)
        serialized = cache.serialize()
        _check(deadline, cancel_check, self._monotonic)
        return EntraSessionCandidate(verified.principal, serialized, verified, deadline)

    def begin(self, settings: FirmSettings, ticket: ActivationTicket, *, cancel_check: Callable[[], None], deadline_changed=None) -> EntraSessionCandidate:
        listener = None
        try:
            browser_deadline = self._monotonic() + 180
            initial_deadline = min(browser_deadline, self._monotonic() + 30)
            if deadline_changed is not None: deadline_changed(initial_deadline)
            app, cache, http = self._application(settings, None, initial_deadline, cancel_check)
            listener = self._listener_factory()
            flow = app.initiate_auth_code_flow([], response_mode="form_post", redirect_uri=listener.redirect_uri)
            _allowed_url(flow["auth_uri"], settings, authorize=True)
            query = parse_qs(urlsplit(flow["auth_uri"]).query)
            if len(query.get("nonce", [])) != 1 or not query["nonce"][0] or query.get("code_challenge_method") != ["S256"] or set(query.get("scope", [""])[0].split()) != {"openid", "profile", "offline_access"}:
                raise auth_error()
            _check(browser_deadline, cancel_check, self._monotonic)
            if deadline_changed is not None: deadline_changed(browser_deadline)
            if not self._browser_open(flow["auth_uri"]):
                raise auth_error()
            callback = listener.wait_for_callback(browser_deadline, cancel_check, self._monotonic)
            if "error" in callback:
                raise VertexAuthError("vertex_authorization_declined", "Firm sign-in was declined.")
            deadline = min(browser_deadline + 30, self._monotonic() + 30)
            if deadline_changed is not None: deadline_changed(deadline)
            # Rebind MSAL's bounded transport after the user may have spent minutes in the browser.
            http.deadline = deadline
            result = app.acquire_token_by_auth_code_flow(flow, callback)
            _check(deadline, cancel_check, self._monotonic)
            if not isinstance(result, dict) or "id_token" not in result or "error" in result:
                raise auth_error("vertex_firm_sign_in_required")
            verified = self.verify_assertion(result["id_token"], settings, expected_nonce=query["nonce"][0], expected_principal=None, deadline=deadline, cancel_check=cancel_check)
            accounts = [account for account in app.get_accounts() if account.get("realm") == verified.principal.tid and account.get("local_account_id") == verified.principal.oid]
            if len(accounts) != 1:
                raise auth_error("vertex_firm_sign_in_required")
            principal = PrivatePrincipal(verified.principal.tid, verified.principal.oid, accounts[0]["home_account_id"])
            return self._candidate(cache, replace(verified, principal=principal), deadline, cancel_check)
        except VertexAuthError:
            raise
        except Exception:
            raise auth_error("vertex_firm_sign_in_required") from None
        finally:
            if listener is not None:
                listener.close()

    def refresh(self, settings: FirmSettings, serialized_cache: str, expected: PrivatePrincipal, *, deadline: float, cancel_check: Callable[[], None]) -> EntraSessionCandidate:
        try:
            _check(deadline, cancel_check, self._monotonic)
            app, cache, _ = self._application(settings, serialized_cache, deadline, cancel_check)
            accounts = [account for account in app.get_accounts() if account.get("home_account_id") == expected.msal_account_key and account.get("realm") == expected.tid and account.get("local_account_id") == expected.oid]
            if len(accounts) != 1:
                raise auth_error("vertex_firm_sign_in_required")
            result = app.acquire_token_silent_with_error([], account=accounts[0], force_refresh=True)
            _check(deadline, cancel_check, self._monotonic)
            if not isinstance(result, dict) or "id_token" not in result or "error" in result:
                raise auth_error("vertex_firm_sign_in_required")
            verified = self.verify_assertion(result["id_token"], settings, expected_nonce=None, expected_principal=expected, deadline=deadline, cancel_check=cancel_check)
            return self._candidate(cache, verified, deadline, cancel_check)
        except VertexAuthError:
            raise
        except Exception:
            raise auth_error("vertex_firm_sign_in_required") from None
