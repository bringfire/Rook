from __future__ import annotations

import importlib
import threading
import uuid

import pytest


def _backend():
    return importlib.import_module("rook.providers.vertex_backend")


def _auth():
    return importlib.import_module("rook.providers.vertex_auth")


class _FakeProtector:
    def protect(self, plaintext):
        return bytes(value ^ 0xA5 for value in plaintext)

    def unprotect(self, ciphertext):
        return bytes(value ^ 0xA5 for value in ciphertext)


def _store(tmp_path):
    auth = _auth()
    return auth.VertexStore(
        tmp_path / "provider_auth" / "vertex.json",
        protector=_FakeProtector(),
        mutex_name="Local\\BringFire.Rook.VertexBackend.Test." + uuid.uuid4().hex,
        mutex_timeout_ms=5_000,
    )


def _record(auth, *, mode=None, ciphertext=None, service_account_path=None):
    selected = mode or auth.VertexMode.ADC
    return auth.VertexRecord(
        schema_version=1,
        generation="0123456789abcdef0123456789abcdef",
        mode=selected,
        project_id="company-ai-project",
        region="us-central1",
        oauth_ciphertext=ciphertext,
        service_account_path=service_account_path,
    )


def _authorized_user():
    return {
        "type": "authorized_user",
        "client_id": "rook-desktop.apps.googleusercontent.com",
        "client_secret": "desktop-client-material",
        "refresh_token": "refresh-token-sentinel",
    }


class _RuntimeStore:
    def __init__(self, runtime=None, error=None):
        self.runtime = runtime
        self.error = error
        self.calls = 0

    def resolve_runtime(self):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.runtime


_DEFAULT_PAYLOAD = object()


class _ReadinessHarness:
    def __init__(
        self,
        status_code=200,
        payload=_DEFAULT_PAYLOAD,
        *,
        region="us-central1",
    ):
        auth = _auth()
        self.store = _RuntimeStore(
            auth.VertexRuntimeArguments(
                generation="0123456789abcdef0123456789abcdef",
                project_id="company-ai-project",
                region=region,
                vertex_credentials={
                    "type": "authorized_user",
                    "client_id": "client",
                    "client_secret": "secret",
                    "refresh_token": "refresh",
                },
            )
        )
        self.status_code = status_code
        self.payload = {"totalTokens": 5} if payload is _DEFAULT_PAYLOAD else payload
        self.token_calls = []
        self.http_calls = []

    def token_loader(self, runtime):
        self.token_calls.append(runtime)
        return "access-token"

    def post_json(self, url, body, headers, timeout_seconds):
        self.http_calls.append((url, body, headers, timeout_seconds))
        return self.status_code, self.payload


def _error_payload(status, details, *, hostile_message="raw-provider-secret"):
    return {
        "error": {
            "code": 403,
            "status": status,
            "message": hostile_message,
            "details": details,
        }
    }


@pytest.mark.parametrize(
    ("region", "expected_url"),
    [
        (
            "us-central1",
            "https://us-central1-aiplatform.googleapis.com/v1/"
            "projects/company-ai-project/locations/us-central1/"
            "publishers/google/models/gemini-2.5-pro:countTokens",
        ),
        (
            "global",
            "https://aiplatform.googleapis.com/v1/"
            "projects/company-ai-project/locations/global/"
            "publishers/google/models/gemini-2.5-pro:countTokens",
        ),
    ],
)
def test_vertex_readiness_uses_exact_regional_or_global_count_tokens_url(
    region,
    expected_url,
):
    backend = _backend()
    harness = _ReadinessHarness(region=region)

    result = backend.probe_vertex_readiness(
        "vertex_ai/gemini-2.5-pro",
        store=harness.store,
        token_loader=harness.token_loader,
        post_json=harness.post_json,
    )

    assert result == backend.VertexOperationResult(
        success=True,
        code=None,
        message="Vertex AI readiness passed.",
        generation="0123456789abcdef0123456789abcdef",
    )
    assert len(harness.token_calls) == 1
    assert harness.http_calls == [
        (
            expected_url,
            {
                "contents": [
                    {
                        "role": "user",
                        "parts": [{"text": "Rook Vertex readiness probe"}],
                    }
                ]
            },
            {"Authorization": "Bearer access-token"},
            30,
        )
    ]


@pytest.mark.parametrize(
    "model",
    ["vertex_ai/claude-sonnet", "gemini/gemini-2.5-pro"],
)
def test_vertex_readiness_rejects_unsupported_family_before_store_or_network(model):
    backend = _backend()
    harness = _ReadinessHarness()

    result = backend.probe_vertex_readiness(
        model,
        store=harness.store,
        token_loader=harness.token_loader,
        post_json=harness.post_json,
    )

    assert result.success is False
    assert result.code == "vertex_model_family_unsupported"
    assert result.message == (
        "This release supports only Gemini publisher models on Vertex AI "
        "(vertex_ai/gemini-*)."
    )
    assert harness.store.calls == 0
    assert harness.token_calls == []
    assert harness.http_calls == []


@pytest.mark.parametrize(
    ("status", "details", "expected_code"),
    [
        (
            "PERMISSION_DENIED",
            [
                {
                    "@type": "type.googleapis.com/google.rpc.ErrorInfo",
                    "reason": "CONSUMER_INVALID",
                    "domain": "googleapis.com",
                    "metadata": {"consumer": "projects/invalid"},
                }
            ],
            "vertex_project_inaccessible",
        ),
        (
            "PERMISSION_DENIED",
            [
                {
                    "@type": "type.googleapis.com/google.rpc.ErrorInfo",
                    "reason": "SERVICE_DISABLED",
                    "domain": "googleapis.com",
                    "metadata": {"service": "aiplatform.googleapis.com"},
                }
            ],
            "vertex_api_disabled",
        ),
        (
            "PERMISSION_DENIED",
            [
                {
                    "@type": "type.googleapis.com/google.rpc.ErrorInfo",
                    "reason": "BILLING_DISABLED",
                    "domain": "googleapis.com",
                    "metadata": {"service": "aiplatform.googleapis.com"},
                }
            ],
            "vertex_billing_unavailable",
        ),
        (
            "PERMISSION_DENIED",
            [
                {
                    "@type": "type.googleapis.com/google.rpc.ErrorInfo",
                    "reason": "IAM_PERMISSION_DENIED",
                    "domain": "aiplatform.googleapis.com",
                    "metadata": {"permission": "aiplatform.endpoints.predict"},
                }
            ],
            "vertex_permission_missing",
        ),
        (
            "INVALID_ARGUMENT",
            [
                {
                    "@type": "type.googleapis.com/google.rpc.BadRequest",
                    "fieldViolations": [
                        {"field": "location", "description": "raw-provider-secret"}
                    ],
                }
            ],
            "vertex_region_invalid",
        ),
        (
            "NOT_FOUND",
            [
                {
                    "@type": "type.googleapis.com/google.rpc.ResourceInfo",
                    "resourceType": "aiplatform.googleapis.com/PublisherModel",
                    "resourceName": "projects/p/locations/r/publishers/google/models/m",
                }
            ],
            "vertex_model_unavailable",
        ),
    ],
)
def test_vertex_readiness_classifies_only_closed_structured_evidence(
    status,
    details,
    expected_code,
):
    backend = _backend()
    harness = _ReadinessHarness(
        status_code=403,
        payload=_error_payload(status, details),
    )

    result = backend.probe_vertex_readiness(
        "vertex_ai/gemini-2.5-pro",
        store=harness.store,
        token_loader=harness.token_loader,
        post_json=harness.post_json,
    )

    assert result.success is False
    assert result.code == expected_code
    assert "raw-provider-secret" not in result.message


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        {"totalTokens": -1},
        {"totalTokens": True},
        _error_payload("PERMISSION_DENIED", []),
        _error_payload(
            "PERMISSION_DENIED",
            [
                {
                    "@type": "type.googleapis.com/google.rpc.ErrorInfo",
                    "reason": "UNKNOWN_REASON",
                    "domain": "googleapis.com",
                    "metadata": {},
                }
            ],
        ),
    ],
)
def test_vertex_readiness_maps_malformed_or_unknown_responses_to_generic_failure(payload):
    backend = _backend()
    harness = _ReadinessHarness(status_code=500, payload=payload)

    result = backend.probe_vertex_readiness(
        "vertex_ai/gemini-2.5-pro",
        store=harness.store,
        token_loader=harness.token_loader,
        post_json=harness.post_json,
    )

    assert result.success is False
    assert result.code == "vertex_request_failed"
    assert "raw-provider-secret" not in result.message


@pytest.mark.parametrize(
    "code",
    [
        "vertex_signed_out",
        "vertex_authorization_revoked",
        "vertex_adc_unavailable",
        "vertex_service_account_unavailable",
        "vertex_auth_dependency_missing",
    ],
)
def test_vertex_readiness_preserves_local_credential_failure_codes(code):
    backend = _backend()
    auth = _auth()
    store = _RuntimeStore(error=auth.VertexAuthError(code, "bounded local failure"))
    network_calls = []

    result = backend.probe_vertex_readiness(
        "vertex_ai/gemini-2.5-pro",
        store=store,
        token_loader=lambda _runtime: network_calls.append("token"),
        post_json=lambda *_args: network_calls.append("http"),
    )

    assert result.success is False
    assert result.code == code
    assert network_calls == []


def test_vertex_readiness_does_not_expose_provider_or_exception_details():
    backend = _backend()
    harness = _ReadinessHarness()

    def fail_network(*_args):
        raise RuntimeError("access-token-and-provider-body-must-not-escape")

    result = backend.probe_vertex_readiness(
        "vertex_ai/gemini-2.5-pro",
        store=harness.store,
        token_loader=harness.token_loader,
        post_json=fail_network,
    )

    assert result.success is False
    assert result.code == "vertex_request_failed"
    assert "access-token-and-provider-body-must-not-escape" not in result.message


def test_default_token_loader_uses_shared_30_second_refresh_deadline(monkeypatch):
    backend = _backend()
    auth = _auth()
    lease = importlib.import_module("rook.providers.vertex_token_lease")
    observed = []
    runtime = auth.VertexRuntimeArguments(
        generation="0123456789abcdef0123456789abcdef",
        project_id="company-ai-project",
        region="global",
        vertex_credentials=None,
    )

    monkeypatch.setattr(backend.time, "monotonic", lambda: 75.0)

    def refresh(selected_runtime, deadline, monotonic):
        observed.append((selected_runtime, deadline, monotonic()))
        return lease.RefreshedVertexAccessToken(
            access_token="readiness-token",
            expires_at_unix_seconds=2_000_000_000,
        )

    monkeypatch.setattr(backend, "refresh_access_token", refresh)

    assert backend._default_token_loader(runtime) == "readiness-token"
    assert observed == [(runtime, 105.0, 75.0)]


def test_connect_commits_protected_oauth_then_recycles_with_the_new_generation(tmp_path):
    backend = _backend()
    oauth = importlib.import_module("rook.providers.vertex_oauth")
    auth = _auth()
    store = _store(tmp_path)
    previous = store.replace(_record(auth))
    recycled = []

    result = backend.connect_vertex_oauth(
        oauth.DesktopOAuthClient(
            client_id="rook-desktop.apps.googleusercontent.com",
            client_secret="desktop-client-material",
        ),
        "company-ai-project",
        "us-central1",
        store=store,
        recycler=recycled.append,
        authorize=lambda _client: _authorized_user(),
    )

    committed = store.read()
    assert result.success is True
    assert result.generation == committed.generation
    assert committed.generation != previous.generation
    assert committed.mode is auth.VertexMode.OAUTH
    assert store.resolve_runtime().vertex_credentials == _authorized_user()
    assert b"refresh-token-sentinel" not in store.path.read_bytes()
    assert recycled == [committed.generation]


def test_connect_failure_preserves_prior_record_and_never_recycles(tmp_path):
    backend = _backend()
    oauth = importlib.import_module("rook.providers.vertex_oauth")
    auth = _auth()
    store = _store(tmp_path)
    store.replace(_record(auth))
    before = store.path.read_bytes()
    recycled = []

    def fail_authorization(_client):
        raise auth.VertexAuthError(
            "vertex_authorization_declined",
            "Google authorization was declined.",
        )

    result = backend.connect_vertex_oauth(
        oauth.DesktopOAuthClient("client", "material"),
        "company-ai-project",
        "us-central1",
        store=store,
        recycler=recycled.append,
        authorize=fail_authorization,
    )

    assert result.success is False
    assert result.code == "vertex_authorization_declined"
    assert store.path.read_bytes() == before
    assert recycled == []


def test_connect_holds_the_cross_process_mutex_during_authorization(tmp_path):
    backend = _backend()
    oauth = importlib.import_module("rook.providers.vertex_oauth")
    auth = _auth()
    store = _store(tmp_path)
    store.replace(_record(auth))
    contender_codes = []

    def authorize_while_contended(_client):
        def contend():
            try:
                with auth._WindowsNamedMutex(store._mutex_name, 50):
                    contender_codes.append("acquired")
            except auth.VertexAuthError as exc:
                contender_codes.append(exc.code)

        thread = threading.Thread(target=contend)
        thread.start()
        thread.join(timeout=2)
        assert not thread.is_alive()
        return _authorized_user()

    result = backend.connect_vertex_oauth(
        oauth.DesktopOAuthClient("client", "material"),
        "company-ai-project",
        "us-central1",
        store=store,
        recycler=lambda _generation: None,
        authorize=authorize_while_contended,
    )

    assert result.success is True
    assert contender_codes == ["vertex_request_failed"]


def test_save_configuration_supports_adc_service_account_and_existing_oauth(tmp_path):
    backend = _backend()
    auth = _auth()
    store = _store(tmp_path)
    recycled = []

    adc = backend.save_vertex_configuration(
        auth.VertexMode.ADC,
        "company-ai-project",
        "us-central1",
        store=store,
        recycler=recycled.append,
    )
    assert adc.success is True
    assert store.read().mode is auth.VertexMode.ADC

    service_file = tmp_path / "service-account.json"
    service_file.write_text("{}", encoding="utf-8")
    service = backend.save_vertex_configuration(
        auth.VertexMode.SERVICE_ACCOUNT,
        "company-ai-project",
        "europe-west1",
        service_account_path=str(service_file),
        store=store,
        recycler=recycled.append,
    )
    assert service.success is True
    assert store.read().service_account_path == str(service_file.resolve())

    ciphertext = store.protect_authorized_user(_authorized_user())
    store.replace(_record(auth, mode=auth.VertexMode.OAUTH, ciphertext=ciphertext))
    oauth = backend.save_vertex_configuration(
        auth.VertexMode.OAUTH,
        "company-ai-project",
        "asia-northeast1",
        store=store,
        recycler=recycled.append,
    )
    assert oauth.success is True
    assert store.read().oauth_ciphertext == ciphertext
    assert store.read().region == "asia-northeast1"
    assert recycled == [adc.generation, service.generation, oauth.generation]


@pytest.mark.parametrize(
    ("project_id", "region", "expected_code"),
    [
        ("", "us-central1", "vertex_project_required"),
        ("BAD_PROJECT", "us-central1", "vertex_project_required"),
        ("company-ai-project", "", "vertex_region_required"),
        ("company-ai-project", "US Central", "vertex_region_required"),
    ],
)
def test_save_configuration_rejects_invalid_project_or_region_without_mutation(
    tmp_path,
    project_id,
    region,
    expected_code,
):
    backend = _backend()
    auth = _auth()
    store = _store(tmp_path)
    store.replace(_record(auth))
    before = store.path.read_bytes()
    recycled = []

    result = backend.save_vertex_configuration(
        auth.VertexMode.ADC,
        project_id,
        region,
        store=store,
        recycler=recycled.append,
    )

    assert result.success is False
    assert result.code == expected_code
    assert store.path.read_bytes() == before
    assert recycled == []


def test_save_oauth_without_existing_oauth_fails_closed(tmp_path):
    backend = _backend()
    auth = _auth()
    store = _store(tmp_path)
    store.replace(_record(auth))
    before = store.path.read_bytes()

    result = backend.save_vertex_configuration(
        auth.VertexMode.OAUTH,
        "company-ai-project",
        "us-central1",
        store=store,
        recycler=lambda _generation: None,
    )

    assert result.success is False
    assert result.code == "vertex_signed_out"
    assert store.path.read_bytes() == before


def test_recycler_failure_reports_restart_required_after_commit(tmp_path):
    backend = _backend()
    auth = _auth()
    store = _store(tmp_path)

    def fail_recycler(_generation):
        raise RuntimeError("recycler detail must not escape")

    result = backend.save_vertex_configuration(
        auth.VertexMode.ADC,
        "company-ai-project",
        "us-central1",
        store=store,
        recycler=fail_recycler,
    )

    assert result.success is False
    assert result.code == "vertex_restart_required"
    assert result.generation == store.read().generation
    assert "recycler detail" not in result.message


def test_save_uses_managed_chirp_recycler_by_default(tmp_path, monkeypatch):
    backend = _backend()
    auth = _auth()
    manager = importlib.import_module("rook.chirp_manager")
    store = _store(tmp_path)
    recycled = []
    monkeypatch.setattr(manager, "recycle_after_vertex_commit", recycled.append)

    result = backend.save_vertex_configuration(
        auth.VertexMode.ADC,
        "company-ai-project",
        "us-central1",
        store=store,
    )

    assert result.success is True
    assert recycled == [store.read().generation]


@pytest.mark.parametrize("revocation_outcome", [True, False, RuntimeError("network-secret")])
def test_disconnect_deletes_oauth_even_when_best_effort_revocation_fails(
    tmp_path,
    revocation_outcome,
):
    backend = _backend()
    auth = _auth()
    store = _store(tmp_path)
    ciphertext = store.protect_authorized_user(_authorized_user())
    store.replace(_record(auth, mode=auth.VertexMode.OAUTH, ciphertext=ciphertext))
    sibling = store.path.parent / "gemini.json"
    sibling.write_bytes(b"gemini-unchanged")
    revoked = []
    recycled = []

    def revoke(refresh_token):
        revoked.append(refresh_token)
        if isinstance(revocation_outcome, Exception):
            raise revocation_outcome
        return revocation_outcome

    result = backend.disconnect_vertex(
        store=store,
        recycler=recycled.append,
        revoke=revoke,
    )

    assert result.success is True
    assert result.revocation == ("revoked" if revocation_outcome is True else "failed")
    assert result.local_deletion == "deleted"
    assert revoked == ["refresh-token-sentinel"]
    assert recycled == [None]
    assert not store.path.exists()
    assert sibling.read_bytes() == b"gemini-unchanged"


@pytest.mark.parametrize("mode", ["adc", "service_account"])
def test_disconnect_non_oauth_modes_do_not_call_revocation(tmp_path, mode):
    backend = _backend()
    auth = _auth()
    store = _store(tmp_path)
    service_file = tmp_path / "service-account.json"
    service_file.write_text("{}", encoding="utf-8")
    selected = auth.VertexMode(mode)
    store.replace(
        _record(
            auth,
            mode=selected,
            service_account_path=(
                str(service_file) if selected is auth.VertexMode.SERVICE_ACCOUNT else None
            ),
        )
    )
    revoke_calls = []

    result = backend.disconnect_vertex(
        store=store,
        recycler=lambda _generation: None,
        revoke=lambda _token: revoke_calls.append(_token),
    )

    assert result.success is True
    assert result.revocation == "not_applicable"
    assert result.local_deletion == "deleted"
    assert revoke_calls == []


def test_disconnect_is_idempotent_when_store_is_absent(tmp_path):
    backend = _backend()
    store = _store(tmp_path)
    side_effects = []

    result = backend.disconnect_vertex(
        store=store,
        recycler=lambda _generation: side_effects.append("recycle"),
        revoke=lambda _token: side_effects.append("revoke"),
    )

    assert result.success is True
    assert result.revocation == "not_applicable"
    assert result.local_deletion == "absent"
    assert side_effects == []
