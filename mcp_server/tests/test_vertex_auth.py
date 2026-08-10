from __future__ import annotations

import importlib
import json
import base64
import multiprocessing
import os
from pathlib import Path
import time
import uuid

import pytest


class _FakeProtector:
    def protect(self, plaintext: bytes) -> bytes:
        return bytes(value ^ 0xA5 for value in plaintext)

    def unprotect(self, ciphertext: bytes) -> bytes:
        return bytes(value ^ 0xA5 for value in ciphertext)


def _vertex_auth():
    return importlib.import_module("rook.providers.vertex_auth")


def _oauth_record(vertex_auth, **overrides):
    values = {
        "schema_version": 1,
        "generation": "0123456789abcdef0123456789abcdef",
        "mode": vertex_auth.VertexMode.OAUTH,
        "project_id": "company-ai-project",
        "region": "us-central1",
        "oauth_ciphertext": "ciphertext",
        "service_account_path": None,
    }
    values.update(overrides)
    return vertex_auth.VertexRecord(**values)


def _store(vertex_auth, path, *, timeout_ms=10_000):
    return vertex_auth.VertexStore(
        path,
        protector=_FakeProtector(),
        mutex_name=(
            "Local\\BringFire.Rook.VertexAuth.Test."
            + uuid.uuid4().hex
        ),
        mutex_timeout_ms=timeout_ms,
    )


def _hold_named_mutex(mutex_name, ready_path, release_path, abandon):
    vertex_auth = _vertex_auth()
    mutex = vertex_auth._WindowsNamedMutex(mutex_name, 5_000)
    mutex.__enter__()
    Path(ready_path).write_text("ready", encoding="ascii")
    if abandon:
        os._exit(0)
    try:
        deadline = time.monotonic() + 10
        while not Path(release_path).exists() and time.monotonic() < deadline:
            time.sleep(0.01)
    finally:
        mutex.__exit__(None, None, None)


def _wait_for_path(path, *, timeout=5):
    deadline = time.monotonic() + timeout
    while not path.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert path.exists()


def test_vertex_model_admission_returns_only_the_provider_relative_gemini_name():
    vertex_auth = _vertex_auth()

    assert vertex_auth.VERTEX_SCOPE == "https://www.googleapis.com/auth/cloud-platform"
    assert (
        vertex_auth.vertex_gemini_model_name("vertex_ai/gemini-2.5-pro")
        == "gemini-2.5-pro"
    )
    assert vertex_auth.vertex_gemini_model_name("gemini/gemini-2.5-pro") is None
    assert vertex_auth.vertex_gemini_model_name("anthropic/claude-opus-5") is None


@pytest.mark.parametrize(
    "model",
    [
        "vertex_ai/",
        "vertex_ai/gemini-",
        "vertex_ai/gemini-/nested",
        "vertex_ai/Gemini-2.5-pro",
        "vertex_ai/claude-sonnet",
    ],
)
def test_vertex_model_admission_rejects_every_unsupported_vertex_family(model):
    vertex_auth = _vertex_auth()

    with pytest.raises(vertex_auth.VertexAuthError) as exc_info:
        vertex_auth.vertex_gemini_model_name(model)

    assert exc_info.value.code == "vertex_model_family_unsupported"
    assert exc_info.value.public_message == (
        "This release supports only Gemini publisher models on Vertex AI "
        "(vertex_ai/gemini-*)."
    )


def test_vertex_record_has_one_closed_json_shape():
    vertex_auth = _vertex_auth()

    record = _oauth_record(vertex_auth)

    assert record.to_json_object() == {
        "schema_version": 1,
        "generation": "0123456789abcdef0123456789abcdef",
        "mode": "oauth",
        "project_id": "company-ai-project",
        "region": "us-central1",
        "oauth_ciphertext": "ciphertext",
        "service_account_path": None,
    }
    assert vertex_auth.VertexRecord.from_json_object(record.to_json_object()) == record


@pytest.mark.parametrize(
    ("overrides", "case"),
    [
        ({"schema_version": 2}, "schema"),
        ({"schema_version": True}, "boolean schema"),
        ({"generation": "ABCDEF0123456789ABCDEF0123456789"}, "generation"),
        ({"generation": "short"}, "short generation"),
        ({"project_id": "Project_With_Underscores"}, "project"),
        ({"project_id": "tiny"}, "short project"),
        ({"region": "US Central"}, "region"),
        ({"region": "us/central1"}, "region path"),
        ({"mode": "unknown"}, "mode"),
        ({"oauth_ciphertext": None}, "missing OAuth ciphertext"),
        ({"oauth_ciphertext": ""}, "blank OAuth ciphertext"),
        (
            {"service_account_path": "C:\\credentials.json"},
            "OAuth service-account collision",
        ),
    ],
)
def test_vertex_record_rejects_malformed_or_incoherent_oauth_records(overrides, case):
    vertex_auth = _vertex_auth()

    with pytest.raises(vertex_auth.VertexAuthError) as exc_info:
        _oauth_record(vertex_auth, **overrides)

    assert exc_info.value.code == "vertex_request_failed", case


def test_vertex_record_rejects_unknown_or_missing_json_fields():
    vertex_auth = _vertex_auth()
    payload = _oauth_record(vertex_auth).to_json_object()

    for malformed in (
        {**payload, "unexpected": True},
        {key: value for key, value in payload.items() if key != "region"},
        {**payload, "schema_version": 2},
    ):
        with pytest.raises(vertex_auth.VertexAuthError) as exc_info:
            vertex_auth.VertexRecord.from_json_object(malformed)
        assert exc_info.value.code == "vertex_request_failed"


def test_vertex_record_enforces_mode_specific_secret_fields(tmp_path, monkeypatch):
    vertex_auth = _vertex_auth()
    service_file = tmp_path / "service-account.json"
    service_file.write_text("{}", encoding="utf-8")

    adc = _oauth_record(
        vertex_auth,
        mode=vertex_auth.VertexMode.ADC,
        oauth_ciphertext=None,
    )
    assert adc.service_account_path is None

    service = _oauth_record(
        vertex_auth,
        mode=vertex_auth.VertexMode.SERVICE_ACCOUNT,
        oauth_ciphertext=None,
        service_account_path=str(service_file),
    )
    assert Path(service.service_account_path) == service_file.resolve()

    invalid = (
        {"mode": vertex_auth.VertexMode.ADC, "oauth_ciphertext": "secret"},
        {
            "mode": vertex_auth.VertexMode.ADC,
            "oauth_ciphertext": None,
            "service_account_path": str(service_file),
        },
        {
            "mode": vertex_auth.VertexMode.SERVICE_ACCOUNT,
            "oauth_ciphertext": None,
            "service_account_path": None,
        },
        {
            "mode": vertex_auth.VertexMode.SERVICE_ACCOUNT,
            "oauth_ciphertext": None,
            "service_account_path": str(tmp_path),
        },
    )
    for overrides in invalid:
        with pytest.raises(vertex_auth.VertexAuthError):
            _oauth_record(vertex_auth, **overrides)

    monkeypatch.chdir(tmp_path)
    with pytest.raises(vertex_auth.VertexAuthError):
        _oauth_record(
            vertex_auth,
            mode=vertex_auth.VertexMode.SERVICE_ACCOUNT,
            oauth_ciphertext=None,
            service_account_path="service-account.json",
        )


def test_vertex_store_production_path_ignores_general_data_root(monkeypatch, tmp_path):
    vertex_auth = _vertex_auth()
    local_appdata = tmp_path / "local-appdata"
    monkeypatch.setenv("LOCALAPPDATA", str(local_appdata))
    monkeypatch.setenv("ROOK_DATA_DIR", str(tmp_path / "redirected-data"))

    store = vertex_auth.VertexStore.production()

    assert store.path == local_appdata / "Rook" / "data" / "provider_auth" / "vertex.json"


def test_vertex_store_replaces_atomically_with_a_fresh_generation(tmp_path):
    vertex_auth = _vertex_auth()
    store_path = tmp_path / "provider_auth" / "vertex.json"
    store = _store(vertex_auth, store_path)
    requested = _oauth_record(vertex_auth)

    first = store.replace(requested)
    second = store.replace(requested)

    assert first.generation != requested.generation
    assert second.generation != requested.generation
    assert second.generation != first.generation
    assert store.read() == second
    assert json.loads(store_path.read_text(encoding="utf-8")) == second.to_json_object()
    assert not list(store_path.parent.glob("vertex.json.*.tmp"))


def test_vertex_store_write_failure_preserves_prior_bytes_and_removes_temporary_file(tmp_path):
    vertex_auth = _vertex_auth()
    store_path = tmp_path / "provider_auth" / "vertex.json"
    store = _store(vertex_auth, store_path)
    store.replace(_oauth_record(vertex_auth))
    before = store_path.read_bytes()

    with pytest.raises(vertex_auth.VertexAuthError) as exc_info:
        store.replace_for_test(
            _oauth_record(vertex_auth, region="europe-west1"),
            fail_before_replace=True,
        )

    assert exc_info.value.code == "vertex_request_failed"
    assert store_path.read_bytes() == before
    assert not list(store_path.parent.glob("vertex.json.*.tmp"))


def test_vertex_store_rejects_unknown_records_without_rewriting_them(tmp_path):
    vertex_auth = _vertex_auth()
    store_path = tmp_path / "provider_auth" / "vertex.json"
    store_path.parent.mkdir(parents=True)
    original = b'{"schema_version":2,"future":true}'
    store_path.write_bytes(original)
    store = _store(vertex_auth, store_path)

    with pytest.raises(vertex_auth.VertexAuthError):
        store.read()
    with pytest.raises(vertex_auth.VertexAuthError):
        store.replace(_oauth_record(vertex_auth))

    assert store_path.read_bytes() == original
    assert not list(store_path.parent.glob("vertex.json.*.tmp"))


def test_oauth_credentials_round_trip_without_plaintext_in_the_store(tmp_path):
    vertex_auth = _vertex_auth()
    store_path = tmp_path / "provider_auth" / "vertex.json"
    store = _store(vertex_auth, store_path)
    credentials = {
        "type": "authorized_user",
        "client_id": "desktop-client.apps.googleusercontent.com",
        "client_secret": "client-secret-sentinel",
        "refresh_token": "refresh-token-sentinel",
    }

    ciphertext = store.protect_authorized_user(credentials)
    committed = store.replace(_oauth_record(vertex_auth, oauth_ciphertext=ciphertext))
    runtime = store.resolve_runtime()

    assert runtime == vertex_auth.VertexRuntimeArguments(
        generation=committed.generation,
        project_id="company-ai-project",
        region="us-central1",
        vertex_credentials=credentials,
    )
    stored = store_path.read_bytes()
    assert b"client-secret-sentinel" not in stored
    assert b"refresh-token-sentinel" not in stored


@pytest.mark.parametrize(
    "credentials",
    [
        {},
        {"type": "service_account"},
        {"type": "authorized_user", "refresh_token": 123},
        {
            "type": "authorized_user",
            "client_id": "client",
            "client_secret": "secret",
            "refresh_token": "token",
            "unexpected": "field",
        },
    ],
)
def test_oauth_protection_rejects_non_authorized_user_shapes(tmp_path, credentials):
    vertex_auth = _vertex_auth()
    store = _store(vertex_auth, tmp_path / "vertex.json")

    with pytest.raises(vertex_auth.VertexAuthError) as exc_info:
        store.protect_authorized_user(credentials)

    assert exc_info.value.code == "vertex_request_failed"


def test_oauth_runtime_rejects_invalid_ciphertext_without_leaking_it(tmp_path):
    vertex_auth = _vertex_auth()
    store = _store(vertex_auth, tmp_path / "vertex.json")
    committed = store.replace(
        _oauth_record(
            vertex_auth,
            oauth_ciphertext=base64.b64encode(b"not-valid-protected-json").decode("ascii"),
        )
    )

    with pytest.raises(vertex_auth.VertexAuthError) as exc_info:
        store.resolve_runtime()

    assert exc_info.value.code == "vertex_request_failed"
    assert committed.oauth_ciphertext not in exc_info.value.public_message


def test_adc_runtime_uses_ambient_credentials_without_a_secret(tmp_path):
    vertex_auth = _vertex_auth()
    store = _store(vertex_auth, tmp_path / "vertex.json")
    committed = store.replace(
        _oauth_record(
            vertex_auth,
            mode=vertex_auth.VertexMode.ADC,
            oauth_ciphertext=None,
        )
    )

    assert store.resolve_runtime() == vertex_auth.VertexRuntimeArguments(
        generation=committed.generation,
        project_id="company-ai-project",
        region="us-central1",
        vertex_credentials=None,
    )


def test_service_account_runtime_revalidates_the_canonical_file(tmp_path):
    vertex_auth = _vertex_auth()
    service_file = tmp_path / "service-account.json"
    service_file.write_text("{}", encoding="utf-8")
    store = _store(vertex_auth, tmp_path / "vertex.json")
    committed = store.replace(
        _oauth_record(
            vertex_auth,
            mode=vertex_auth.VertexMode.SERVICE_ACCOUNT,
            oauth_ciphertext=None,
            service_account_path=str(service_file),
        )
    )

    assert store.resolve_runtime() == vertex_auth.VertexRuntimeArguments(
        generation=committed.generation,
        project_id="company-ai-project",
        region="us-central1",
        vertex_credentials=str(service_file.resolve()),
    )

    service_file.unlink()
    with pytest.raises(vertex_auth.VertexAuthError) as exc_info:
        store.resolve_runtime()
    assert exc_info.value.code == "vertex_request_failed"


def test_runtime_resolution_requires_a_record(tmp_path):
    vertex_auth = _vertex_auth()
    store = _store(vertex_auth, tmp_path / "vertex.json")

    with pytest.raises(vertex_auth.VertexAuthError) as exc_info:
        store.resolve_runtime()

    assert exc_info.value.code == "vertex_signed_out"


class _RuntimeStore:
    def __init__(self, runtime):
        self.runtime = runtime
        self.calls = 0

    def resolve_runtime(self):
        self.calls += 1
        return self.runtime


def test_apply_vertex_arguments_copies_kwargs_and_adds_only_runtime_fields():
    vertex_auth = _vertex_auth()
    credentials = {
        "type": "authorized_user",
        "client_id": "client",
        "client_secret": "secret",
        "refresh_token": "token",
    }
    store = _RuntimeStore(
        vertex_auth.VertexRuntimeArguments(
            generation="0123456789abcdef0123456789abcdef",
            project_id="company-ai-project",
            region="us-central1",
            vertex_credentials=credentials,
        )
    )
    original = {"model": "vertex_ai/gemini-2.5-pro", "temperature": 0.25}

    result = vertex_auth.apply_vertex_litellm_arguments(
        original["model"], original, store=store
    )

    assert result == {
        **original,
        "vertex_project": "company-ai-project",
        "vertex_location": "us-central1",
        "vertex_credentials": credentials,
    }
    assert result is not original
    assert original == {"model": "vertex_ai/gemini-2.5-pro", "temperature": 0.25}
    assert store.calls == 1


@pytest.mark.parametrize(
    "model",
    [
        "gemini/gemini-2.5-pro",
        "anthropic/claude-opus-5",
        "openai/gpt-5",
        "ollama/llama3",
    ],
)
def test_apply_vertex_arguments_does_not_access_store_for_other_providers(model):
    vertex_auth = _vertex_auth()
    store = _RuntimeStore(None)
    kwargs = {"model": model, "temperature": 0.25}

    result = vertex_auth.apply_vertex_litellm_arguments(model, kwargs, store=store)

    assert result == kwargs
    assert result is not kwargs
    assert store.calls == 0


def test_apply_vertex_arguments_rejects_unsupported_family_before_store_access():
    vertex_auth = _vertex_auth()
    store = _RuntimeStore(None)

    with pytest.raises(vertex_auth.VertexAuthError) as exc_info:
        vertex_auth.apply_vertex_litellm_arguments(
            "vertex_ai/claude-sonnet", {"model": "vertex_ai/claude-sonnet"}, store=store
        )

    assert exc_info.value.code == "vertex_model_family_unsupported"
    assert store.calls == 0


@pytest.mark.skipif(os.name != "nt", reason="DPAPI is a Windows-only contract")
def test_real_current_user_dpapi_round_trip_and_corruption_failure():
    vertex_auth = _vertex_auth()
    protector = vertex_auth._DpapiProtector()
    plaintext = b'Rook Vertex DPAPI sentinel that must remain protected'

    ciphertext = protector.protect(plaintext)

    assert plaintext not in ciphertext
    assert protector.unprotect(ciphertext) == plaintext
    corrupted = bytearray(ciphertext)
    corrupted[len(corrupted) // 2] ^= 0xFF
    with pytest.raises(vertex_auth.VertexAuthError):
        protector.unprotect(bytes(corrupted))


@pytest.mark.skipif(os.name != "nt", reason="named mutex is a Windows-only contract")
def test_cross_process_mutex_timeout_preserves_prior_bytes(tmp_path):
    vertex_auth = _vertex_auth()
    store_path = tmp_path / "provider_auth" / "vertex.json"
    mutex_name = "Local\\BringFire.Rook.VertexAuth.Test." + uuid.uuid4().hex
    seed_store = vertex_auth.VertexStore(
        store_path,
        protector=_FakeProtector(),
        mutex_name=mutex_name,
        mutex_timeout_ms=5_000,
    )
    seed_store.replace(_oauth_record(vertex_auth))
    before = store_path.read_bytes()
    ready_path = tmp_path / "ready"
    release_path = tmp_path / "release"
    context = multiprocessing.get_context("spawn")
    process = context.Process(
        target=_hold_named_mutex,
        args=(mutex_name, str(ready_path), str(release_path), False),
    )
    process.start()
    try:
        _wait_for_path(ready_path)
        contender = vertex_auth.VertexStore(
            store_path,
            protector=_FakeProtector(),
            mutex_name=mutex_name,
            mutex_timeout_ms=50,
        )

        with pytest.raises(vertex_auth.VertexAuthError) as exc_info:
            contender.replace(_oauth_record(vertex_auth, region="europe-west1"))

        assert exc_info.value.code == "vertex_request_failed"
        assert store_path.read_bytes() == before
    finally:
        release_path.write_text("release", encoding="ascii")
        process.join(timeout=5)
        if process.is_alive():
            process.terminate()
            process.join(timeout=5)
    assert process.exitcode == 0


@pytest.mark.skipif(os.name != "nt", reason="named mutex is a Windows-only contract")
def test_abandoned_mutex_successor_rereads_and_commits(tmp_path):
    vertex_auth = _vertex_auth()
    store_path = tmp_path / "provider_auth" / "vertex.json"
    mutex_name = "Local\\BringFire.Rook.VertexAuth.Test." + uuid.uuid4().hex
    store = vertex_auth.VertexStore(
        store_path,
        protector=_FakeProtector(),
        mutex_name=mutex_name,
        mutex_timeout_ms=5_000,
    )
    first = store.replace(_oauth_record(vertex_auth))
    ready_path = tmp_path / "abandoned-ready"
    context = multiprocessing.get_context("spawn")
    process = context.Process(
        target=_hold_named_mutex,
        args=(mutex_name, str(ready_path), str(tmp_path / "unused"), True),
    )
    process.start()
    _wait_for_path(ready_path)
    process.join(timeout=5)
    assert process.exitcode == 0

    second = store.replace(_oauth_record(vertex_auth, region="europe-west1"))

    assert second.generation != first.generation
    assert second.region == "europe-west1"
    assert store.read() == second
