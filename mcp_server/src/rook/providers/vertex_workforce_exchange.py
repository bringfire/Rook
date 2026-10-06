"""Pinned Google SDK workforce ID-token exchange; no client secret or fallback."""
from __future__ import annotations

from dataclasses import asdict
import math
import time
from types import SimpleNamespace
from typing import Callable

from urllib.error import HTTPError
from urllib.request import Request

from .vertex_auth import VertexAuthError, VERTEX_SCOPE
from .vertex_bounded_io import SocketDeadline, bounded_opener
from .vertex_workforce_contract import (
    FirmSettings, VerifiedEntraAssertion, WorkforceExchangeResult, TOKEN_LIMIT,
    auth_error, json_object,
)

STS_URL = 'https://sts.googleapis.com/v1/token'
ID_TOKEN_TYPE = 'urn:ietf:params:oauth:token-type:id_token'
ACCESS_TOKEN_TYPE = 'urn:ietf:params:oauth:token-type:access_token'


def _check(deadline, cancel_check, monotonic):
    cancel_check()
    if not math.isfinite(deadline) or monotonic() >= deadline:
        raise auth_error('vertex_token_issuance_timeout')


class _StsRequest:
    def __init__(self, deadline, cancel_check):
        self.deadline, self.cancel_check = deadline, cancel_check

    def __call__(self, *, url, method, headers, body, **kwargs):
        deadline = min(self.deadline, time.monotonic() + 20)
        _check(deadline, self.cancel_check, time.monotonic)
        if url != STS_URL or method != 'POST' or len(body) > TOKEN_LIMIT or any(key.lower() == 'authorization' for key in headers):
            raise auth_error()
        with SocketDeadline(deadline, self.cancel_check, time.monotonic) as guard:
            opener = bounded_opener(guard)
            guard.check()  # Construction can consume the remaining deadline.
            try:
                try:
                    response = opener.open(Request(url, data=body, headers=headers, method=method), timeout=deadline - time.monotonic())
                except HTTPError as error:
                    response = error
            except Exception:
                guard.check()
                raise auth_error() from None
            with response:
                if 300 <= response.getcode() < 400:
                    raise auth_error()
                payload = bytearray()
                # Do not aggregate multiple socket reads into a 64KiB chunk:
                # a slow peer must yield control to deadline/cancellation checks.
                while True:
                    _check(deadline, self.cancel_check, time.monotonic)
                    try:
                        chunk = response.read1(min(65536, TOKEN_LIMIT + 1 - len(payload)))
                    except Exception:
                        guard.check()
                        raise auth_error() from None
                    if not chunk: break
                    payload.extend(chunk)
                    if len(payload) > TOKEN_LIMIT:
                        raise auth_error()
                _check(deadline, self.cancel_check, time.monotonic)
                return SimpleNamespace(status=response.getcode(), data=bytes(payload))


def exchange_assertion(settings: FirmSettings, assertion: VerifiedEntraAssertion, *,
                       deadline: float, cancel_check: Callable[[], None], request=None,
                       monotonic=time.monotonic, unix_time=time.time) -> WorkforceExchangeResult:
    _check(deadline, cancel_check, monotonic)
    if not isinstance(settings, FirmSettings) or not isinstance(assertion, VerifiedEntraAssertion) or assertion.principal.tid != settings.entra_tenant_id or assertion.expires_at <= unix_time():
        raise auth_error('vertex_firm_sign_in_required')
    try:
        from google.auth import identity_pool
        from importlib.metadata import version
        if version('google-auth') != '2.56.3':
            raise auth_error()
        class Supplier(identity_pool.SubjectTokenSupplier):
            def get_subject_token(self, context, _request):
                _check(deadline, cancel_check, monotonic)
                if context.audience != settings.audience or context.subject_token_type != ID_TOKEN_TYPE or assertion.expires_at <= unix_time():
                    raise auth_error('vertex_firm_sign_in_required')
                return assertion.assertion
        dispatch = request or _StsRequest(deadline, cancel_check)
        calls = 0
        received = None
        def bounded_request(**kwargs):
            nonlocal calls, received
            _check(deadline, cancel_check, monotonic)
            if calls or kwargs.get('url') != STS_URL or kwargs.get('method') != 'POST':
                raise auth_error()
            calls += 1
            response = dispatch(**kwargs)
            _check(deadline, cancel_check, monotonic)
            if response.status != 200:
                if response.status == 429 or 500 <= response.status <= 599:
                    raise auth_error('vertex_request_failed')
                raise auth_error('vertex_workforce_exchange_denied')
            received = json_object(response.data, TOKEN_LIMIT)
            if received.get('token_type') != 'Bearer' or received.get('issued_token_type') != ACCESS_TOKEN_TYPE or type(received.get('expires_in')) is not int or not 0 < received['expires_in'] <= 3600 or not isinstance(received.get('access_token'), str) or not received['access_token'] or any(ord(char) < 33 or ord(char) > 126 for char in received['access_token']):
                raise auth_error()
            return response
        credentials = identity_pool.Credentials(
            audience=settings.audience, subject_token_type=ID_TOKEN_TYPE, token_url=STS_URL,
            subject_token_supplier=Supplier(), scopes=[VERTEX_SCOPE],
            workforce_pool_user_project=settings.workforce_pool_user_project,
            quota_project_id=settings.quota_project_id,
        )
        credentials.refresh(bounded_request)
        _check(deadline, cancel_check, monotonic)
        if received is None or credentials.token != received['access_token']:
            raise auth_error()
        return WorkforceExchangeResult(credentials.token, int(unix_time()) + received['expires_in'], settings.project_id, settings.workforce_pool_user_project, settings.quota_project_id)
    except VertexAuthError:
        raise
    except ImportError:
        raise VertexAuthError('vertex_auth_dependency_missing', 'The installed Google authorization dependency is unavailable.') from None
    except Exception:
        raise auth_error() from None
