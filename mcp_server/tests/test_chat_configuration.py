"""Finite configuration boundary tests; only synthetic child processes are admitted."""

import asyncio
import json
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
import pytest_asyncio
from aiohttp.test_utils import TestClient, TestServer

from rook.agent.chat import prime_runtime, server
from .test_chat_server import FakeManager
from .test_chat_prime_runtime import _write_runtime
from rook.agent.chat.service_main import InstalledRuntimeCatalog

NONCE = "synthetic-nonce"
HEADERS = {server.SESSION_HEADER: NONCE, "Origin": server.ALLOWED_ORIGIN}


def begin(operation="status", **inputs):
    return {"v": 1, "type": "begin", "operationId": "a" * 32, "operation": operation, "input": inputs}


@pytest_asyncio.fixture
async def configured(tmp_path, monkeypatch):
    from rook.agent.chat import configuration_process as process
    from rook.agent.chat.configuration_http import ConfigurationHttp

    root = tmp_path / "prime"
    runtime_id, runtime_root = _write_runtime(root)
    catalog = InstalledRuntimeCatalog(root)
    # Only a synthetic manifest is admitted in this test. No installed pointer is read.
    monkeypatch.setattr(catalog, "latest", lambda: catalog.get(runtime_id))
    contract = catalog.latest()
    monkeypatch.setattr(prime_runtime, "SUPPORTED_CONFIGURATION_COMMITS", frozenset({contract.compatibility_patch_commit}))
    monkeypatch.setattr(process, "COOPERATIVE_SECONDS", 0.15)
    monkeypatch.setattr(process, "CLEANUP_SECONDS", 1.0)
    monkeypatch.setattr(process, "OPERATION_SECONDS", {operation: 2.0 for operation in process.OPERATION_SECONDS})
    real_spawn = asyncio.create_subprocess_exec
    calls, children = [], []

    async def synthetic_spawn(*argv, **kwargs):
        assert argv == (str(runtime_root / "pi.exe"), "configuration", "--stdio", "--configuration-policy", "rookchat")
        assert kwargs["cwd"] == str(tmp_path)
        assert kwargs["env"]["PRIME_AGENT_CODING_AGENT_DIR"] == str(tmp_path / "prime-config")
        assert not any("SYNTHETIC_KEY_NAME" in arg for arg in argv)
        assert "SYNTHETIC_KEY_NAME" not in kwargs["env"].values()
        assert kwargs["stdin"] == asyncio.subprocess.PIPE
        calls.append((argv, kwargs))
        child = await real_spawn(sys.executable, "-I", str(Path(__file__).parent / "fixtures/fake_prime_configuration.py"),
                                 *argv[1:], **kwargs)
        children.append(child)
        return child

    monkeypatch.setattr(asyncio, "create_subprocess_exec", synthetic_spawn)
    environment = {key: value for key, value in os.environ.items() if key.upper() in {"SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP"}}
    environment.update({"PRIME_AGENT_CODING_AGENT_DIR": "wrong", "prime_agent_coding_agent_dir": "also-wrong",
                        "ROOK_CONFIGURATION_TEST_CASE": "normal", "HTTP_PROXY": "http://127.0.0.1:1"})
    dependency = ConfigurationHttp(catalog, environment, tmp_path)
    try:
        yield dependency, calls, children, runtime_root
    finally:
        try:
            await asyncio.wait_for(dependency.shutdown(), 3)
        finally:
            unsettled = [child for child in children if child.returncode is None]
            for child in unsettled:
                child.kill()
                await asyncio.wait_for(child.wait(), 2)
            assert not unsettled, "Owner left a synthetic child active; fixture settled its exact child"


@asynccontextmanager
async def client_for(tmp_path, dependency):
    manager = FakeManager(tmp_path)
    for method in ("create", "reopen", "start_prompt"):
        async def forbidden(*args, **kwargs):
            raise AssertionError("Configuration entered the conversation path")
        setattr(manager, method, forbidden)
    async with TestClient(TestServer(server.create_chat_app(manager, expected_nonce=NONCE, configuration=dependency))) as client:
        yield client


async def rows(response):
    return [json.loads(line) for line in (await asyncio.wait_for(response.text(), 4)).splitlines()]


@pytest.mark.asyncio
async def test_http_to_verified_child_private_key_and_settlement(configured, tmp_path, caplog):
    dependency, calls, children, _ = configured
    async with client_for(tmp_path, dependency) as client:
        response = await client.post("/agent/chat/configuration", headers=HEADERS,
                                     json=begin("apiKey.set", provider="synthetic", key="SYNTHETIC_KEY_NAME"))
        assert response.status == 200 and response.headers["Cache-Control"] == "no-store"
        assert response.headers.get("Access-Control-Allow-Origin") == server.ALLOWED_ORIGIN
        events = await rows(response)
        assert events[0]["persistence"] == "saved"
        assert events[-1] == {"type": "configuration_settled", "result": events[0], "exit_code": 0,
                              "cleanup": "exited", "failure_code": None}
        assert len(calls) == 1 and children[0].returncode == 0
        assert calls[0][1]["env"]["HTTP_PROXY"] == "http://127.0.0.1:1"
        assert not any(key == "prime_agent_coding_agent_dir" for key in calls[0][1]["env"])
        assert "SYNTHETIC_KEY_NAME" not in json.dumps(events) + caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("case,code", [("saved-nonzero", "child_exit_failed"), ("saved-hang", "cleanup_failed"),
                                       ("saved-invalid", "protocol_error")])
async def test_saved_result_survives_failed_cleanup_or_late_protocol(configured, tmp_path, case, code):
    dependency, _, children, _ = configured
    dependency.base_environment["ROOK_CONFIGURATION_TEST_CASE"] = case
    async with client_for(tmp_path, dependency) as client:
        events = await rows(await client.post("/agent/chat/configuration", headers=HEADERS,
                                            json=begin("apiKey.set", provider="synthetic", key="SYNTHETIC_KEY_NAME")))
        settlement = events[-1]
        assert settlement["result"]["persistence"] == "saved"
        assert settlement["result"]["outcome"] == "completed"
        assert settlement["failure_code"] == code and settlement["cleanup"] == "exited"
        assert children[0].returncode is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("case,code", [("invalid", "protocol_error"), ("partial", "protocol_error"),
    ("unicode", "protocol_error"), ("frame-overflow", "bounds_exceeded"), ("stderr-overflow", "bounds_exceeded"),
    ("count-overflow", "bounds_exceeded"), ("no-result", "missing_result")])
async def test_real_child_protocol_and_output_failures_are_safe(configured, tmp_path, caplog, case, code):
    dependency, _, children, _ = configured
    dependency.base_environment["ROOK_CONFIGURATION_TEST_CASE"] = case
    async with client_for(tmp_path, dependency) as client:
        events = await rows(await client.post("/agent/chat/configuration", headers=HEADERS, json=begin()))
        assert events[-1]["result"] is None
        assert events[-1]["failure_code"] == code
        assert events[-1]["cleanup"] == "exited" and children[0].returncode is not None
        assert "SYNTHETIC_PRIVATE" not in json.dumps(events) + caplog.text


@pytest.mark.asyncio
async def test_oauth_instructions_busy_correlation_and_cancel(configured, tmp_path, caplog):
    dependency, calls, children, _ = configured
    dependency.base_environment["ROOK_CONFIGURATION_TEST_CASE"] = "oauth"
    async with client_for(tmp_path, dependency) as client:
        response = await client.post("/agent/chat/configuration", headers=HEADERS, json=begin("oauth.connect", provider="synthetic"))
        authorization = json.loads(await asyncio.wait_for(response.content.readline(), 2))
        request = json.loads(await asyncio.wait_for(response.content.readline(), 2))
        assert authorization["instructions"] == "SYNTHETIC_DEVICE_CODE"
        assert request["requestId"] == 1
        busy = await client.post("/agent/chat/configuration", headers=HEADERS, json=begin())
        assert busy.status == 409 and len(calls) == 1
        wrong = await client.post("/agent/chat/configuration/reply", headers=HEADERS, json={
            "v": 1, "type": "reply", "operationId": "b" * 32, "requestId": 1, "value": "SYNTHETIC_REPLY"})
        assert wrong.status == 400
        cancel = await client.post("/agent/chat/configuration/cancel", headers=HEADERS,
                                   json={"v": 1, "type": "cancel", "operationId": "a" * 32})
        assert cancel.status == 204
        events = await rows(response)
        assert events[-1]["result"]["persistence"] == "unchanged"
        assert events[-1]["cleanup"] == "exited" and children[0].returncode == 1
        assert "SYNTHETIC_DEVICE_CODE" not in caplog.text and "SYNTHETIC_REPLY" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("case,value", [("oauth", "SYNTHETIC_REPLY"), ("select", "chosen")])
async def test_reply_reaches_child_once_and_late_reply_refuses(configured, tmp_path, case, value):
    dependency, _, _, _ = configured
    dependency.base_environment["ROOK_CONFIGURATION_TEST_CASE"] = case
    async with client_for(tmp_path, dependency) as client:
        response = await client.post("/agent/chat/configuration", headers=HEADERS, json=begin("oauth.connect", provider="synthetic"))
        await response.content.readline()
        await response.content.readline()
        operation = dependency.active
        reply = {"v": 1, "type": "reply", "operationId": "a" * 32, "requestId": 1, "value": value}
        assert (await client.post("/agent/chat/configuration/reply", headers=HEADERS, json=reply)).status == 204
        events = await rows(response)
        assert events[-1]["result"]["persistence"] == "saved"
        assert operation._stdin_count == 2
        assert (await client.post("/agent/chat/configuration/reply", headers=HEADERS, json=reply)).status == 400


@pytest.mark.asyncio
async def test_disconnect_retains_cleanup_task(configured, tmp_path):
    dependency, _, children, _ = configured
    dependency.base_environment["ROOK_CONFIGURATION_TEST_CASE"] = "oauth"
    async with client_for(tmp_path, dependency) as client:
        response = await client.post("/agent/chat/configuration", headers=HEADERS, json=begin("oauth.connect", provider="synthetic"))
        await response.content.readline()
        await response.content.readline()
        task = dependency.task
        response.close()
        settlement = await asyncio.wait_for(asyncio.shield(task), 3)
        assert settlement.cleanup == "exited" and settlement.result.persistence == "unchanged"
        assert not task.cancelled() and children[0].returncode is not None


@pytest.mark.asyncio
async def test_app_shutdown_cancels_pending_oauth(configured, tmp_path):
    dependency, _, children, _ = configured
    dependency.base_environment["ROOK_CONFIGURATION_TEST_CASE"] = "oauth"
    async with client_for(tmp_path, dependency) as client:
        response = await client.post("/agent/chat/configuration", headers=HEADERS, json=begin("oauth.connect", provider="synthetic"))
        await response.content.readline()
        await response.content.readline()
        task = dependency.task
        await asyncio.wait_for(client.server.app.shutdown(), 3)
        assert (await task).cleanup == "exited" and children[0].returncode is not None
        await response.read()


@pytest.mark.asyncio
@pytest.mark.parametrize("headers", [{}, {**HEADERS, "Origin": "https://wrong.invalid"}, {**HEADERS, server.SESSION_HEADER: "wrong"}])
async def test_authentication_and_origin_refuse_before_spawn(configured, tmp_path, headers):
    dependency, calls, _, _ = configured
    async with client_for(tmp_path, dependency) as client:
        response = await client.post("/agent/chat/configuration", headers=headers, json=begin())
        assert response.status == 403 and not calls
        assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.asyncio
async def test_runtime_tampering_refuses_before_spawn(configured, tmp_path):
    dependency, calls, _, root = configured
    (root / "pi.exe").write_bytes(b"tampered synthetic executable")
    async with client_for(tmp_path, dependency) as client:
        response = await client.post("/agent/chat/configuration", headers=HEADERS, json=begin())
        assert response.status == 503 and not calls


@pytest.mark.parametrize("raw", [b'{"v":1,"v":1}', b'{"key":"\\ud800"}', b'{"key":NaN}', b'[]', b'\xff'])
def test_closed_json_refuses_without_echo(raw):
    from rook.agent.chat.configuration_protocol import ConfigurationError, parse_record
    with pytest.raises(ConfigurationError, match="^invalid_request$"):
        parse_record(raw)


@pytest.mark.asyncio
async def test_configuration_is_unavailable_without_adopted_runtime(tmp_path: Path):
    manager = FakeManager(tmp_path)
    async with TestClient(TestServer(server.create_chat_app(manager, expected_nonce="synthetic-nonce"))) as client:
        response = await client.post("/agent/chat/configuration", headers={
            server.SESSION_HEADER: "synthetic-nonce", "Origin": server.ALLOWED_ORIGIN,
        }, json={"v": 1, "type": "begin", "operationId": "a" * 32, "operation": "status", "input": {}})
        assert response.status == 503
        assert (await response.json())["error"]["code"] == "configuration_unavailable"
        assert response.headers["Cache-Control"] == "no-store"
        assert manager.created is None and not manager.prompted


def test_configuration_launch_contract_exists_but_support_set_is_empty():
    assert callable(getattr(prime_runtime, "build_configuration_argv", None))
    assert prime_runtime.SUPPORTED_CONFIGURATION_COMMITS == frozenset()


@pytest.mark.asyncio
async def test_cancel_during_spawn_uses_cleanup_budget(configured, monkeypatch):
    from rook.agent.chat import configuration_process as process
    from rook.agent.chat.configuration_protocol import validate_begin
    dependency, _, children, _ = configured
    spawn = asyncio.create_subprocess_exec
    started, release = asyncio.Event(), asyncio.Event()

    async def held_spawn(*args, **kwargs):
        child = await spawn(*args, **kwargs)
        started.set()
        await release.wait()
        return child

    monkeypatch.setattr(asyncio, "create_subprocess_exec", held_spawn)
    owner = process.PrimeConfigurationOperation(dependency.catalog.latest(), validate_begin(begin()),
                                                dependency.base_environment, dependency.data_root)
    async def emit(record):
        raise AssertionError("No begin was sent")
    task = asyncio.create_task(owner.run(emit))
    try:
        await asyncio.wait_for(started.wait(), 2)
        owner.cancel("a" * 32)
        # Release acquisition during the original cooperative allowance.
        await asyncio.sleep(0.03)
        release.set()
        settlement = await asyncio.wait_for(asyncio.shield(task), 1.5)
        assert settlement.cleanup == "exited" and owner._stdin_count == 0
        assert children[0].returncode is not None
    finally:
        release.set()
        owner.cancel("a" * 32)
        await asyncio.wait_for(asyncio.shield(task), 3)


@pytest.mark.asyncio
async def test_unconfirmed_spawn_returns_within_original_cleanup_budget(configured, monkeypatch):
    from rook.agent.chat.configuration_protocol import validate_begin
    dependency, _, children, _ = configured
    spawn = asyncio.create_subprocess_exec
    started, release = asyncio.Event(), asyncio.Event()
    async def held_spawn(*args, **kwargs):
        child = await spawn(*args, **kwargs)
        started.set()
        await release.wait()
        return child
    async def emit(record):
        raise AssertionError("No begin was sent")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", held_spawn)
    owner = dependency.start(validate_begin(begin()), emit)
    task = dependency.task
    try:
        await asyncio.wait_for(started.wait(), 2)
        owner.cancel("a" * 32)
        settlement = await asyncio.wait_for(asyncio.shield(task), 1.5)
        assert settlement.cleanup == "unconfirmed" and dependency.active is owner
    finally:
        release.set()
        owner.cancel("a" * 32)
        await asyncio.wait_for(asyncio.shield(task), 3)
        if owner._spawn:
            await asyncio.wait_for(asyncio.shield(owner._spawn), 2)
        for child in children:
            if child.returncode is None:
                child.kill()
            await asyncio.wait_for(child.wait(), 2)


@pytest.mark.asyncio
async def test_saved_result_with_unconfirmed_exit_retains_slot(configured, tmp_path, monkeypatch):
    dependency, _, children, _ = configured
    dependency.base_environment["ROOK_CONFIGURATION_TEST_CASE"] = "saved-hang"
    spawn = asyncio.create_subprocess_exec

    class Unsignalable:
        def __init__(self, child):
            self.child = child
        def __getattr__(self, key):
            return getattr(self.child, key)
        def terminate(self):
            raise PermissionError("SYNTHETIC_PRIVATE")
        kill = terminate

    async def unsignalable_spawn(*args, **kwargs):
        return Unsignalable(await spawn(*args, **kwargs))
    monkeypatch.setattr(asyncio, "create_subprocess_exec", unsignalable_spawn)
    async with client_for(tmp_path, dependency) as client:
        try:
            events = await rows(await client.post("/agent/chat/configuration", headers=HEADERS,
                                                 json=begin("apiKey.set", provider="synthetic", key="SYNTHETIC_KEY_NAME")))
            assert events[-1]["cleanup"] == "unconfirmed" and events[-1]["exit_code"] is None
            assert events[-1]["result"]["persistence"] == "saved"
            assert dependency.active is not None
            assert (await client.post("/agent/chat/configuration", headers=HEADERS, json=begin())).status == 409
        finally:
            # The test, not the owner, restores its deliberately refused synthetic signal boundary.
            for child in children:
                if child.returncode is None:
                    child.kill()
                await asyncio.wait_for(child.wait(), 2)


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["double-input", "cancel-hang"])
async def test_input_violation_and_uncooperative_cancellation_settle(configured, tmp_path, case):
    dependency, _, children, _ = configured
    dependency.base_environment["ROOK_CONFIGURATION_TEST_CASE"] = case
    async with client_for(tmp_path, dependency) as client:
        response = await client.post("/agent/chat/configuration", headers=HEADERS, json=begin("oauth.connect", provider="synthetic"))
        await response.content.readline()
        await response.content.readline()
        if case == "cancel-hang":
            assert (await client.post("/agent/chat/configuration/cancel", headers=HEADERS,
                                     json={"v": 1, "type": "cancel", "operationId": "a" * 32})).status == 204
        events = await rows(response)
        assert events[-1]["failure_code"] == ("protocol_error" if case == "double-input" else "cleanup_failed")
        assert events[-1]["cleanup"] == "exited" and children[0].returncode is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("operation,inputs", [
    ("status", {}), ("models", {"provider": "synthetic"}), ("endpoint.read", {"provider": "synthetic"}),
    ("oauth.disconnect", {"provider": "synthetic"}), ("apiKey.remove", {"provider": "synthetic"}),
    ("defaults.save", {"provider": "synthetic", "model": "exact-model", "reasoning": "low"}),
    ("endpoint.save", {"provider": "ollama", "baseUrl": "http://127.0.0.1:11434/v1", "api": "openai-completions",
                       "authHeader": False, "headers": {"action": "keep"}, "models": [],
                       "compat": {"supportsDeveloperRole": False}}),
])
async def test_finite_operations_forward_prime_results_not_inference(configured, tmp_path, operation, inputs):
    dependency, calls, _, _ = configured
    async with client_for(tmp_path, dependency) as client:
        events = await rows(await client.post("/agent/chat/configuration", headers=HEADERS, json=begin(operation, **inputs)))
        assert events[-1]["failure_code"] is None and events[-1]["exit_code"] == 0
        result = events[-1]["result"]
        if operation == "models":
            assert result["data"]["access"] == "unverified"
        if operation == "endpoint.read":
            assert result["data"]["entry"]["headerNames"] == ["X-Example"]
            assert "headers" not in result["data"]["entry"]
        assert len(calls) == 1


@pytest.mark.asyncio
async def test_operation_deadline_does_not_become_success(configured, tmp_path, monkeypatch):
    from rook.agent.chat import configuration_process as process
    dependency, _, children, _ = configured
    dependency.base_environment["ROOK_CONFIGURATION_TEST_CASE"] = "deadline"
    monkeypatch.setitem(process.OPERATION_SECONDS, "status", 0.15)
    async with client_for(tmp_path, dependency) as client:
        events = await rows(await client.post("/agent/chat/configuration", headers=HEADERS, json=begin()))
        assert events[-1]["failure_code"] == "deadline_exceeded"
        assert events[-1]["result"] is None and events[-1]["cleanup"] == "exited"
        assert children[0].returncode is not None


@pytest.mark.asyncio
async def test_reply_cancel_race_never_sends_late_reply(configured, tmp_path):
    dependency, _, _, _ = configured
    dependency.base_environment["ROOK_CONFIGURATION_TEST_CASE"] = "oauth"
    async with client_for(tmp_path, dependency) as client:
        response = await client.post("/agent/chat/configuration", headers=HEADERS, json=begin("oauth.connect", provider="synthetic"))
        await response.content.readline()
        await response.content.readline()
        owner = dependency.active
        await owner._input_lock.acquire()
        task = asyncio.create_task(owner.reply("a" * 32, 1, "SYNTHETIC_REPLY"))
        try:
            await asyncio.sleep(0)
            owner.cancel("a" * 32)
        finally:
            owner._input_lock.release()
        from rook.agent.chat.configuration_protocol import ConfigurationError
        with pytest.raises(ConfigurationError, match="^cancelled$"):
            await asyncio.wait_for(task, 2)
        events = await rows(response)
        assert owner._stdin_count <= 2  # begin, at most one cancellation; never the stale reply
        assert events[-1]["cleanup"] == "exited"
        assert events[-1]["result"]["persistence"] == "unchanged"
        assert events[-1]["result"]["code"] == "cancelled"
        assert events[-1]["exit_code"] == 1 and events[-1]["failure_code"] == "child_exit_failed"


@pytest.mark.asyncio
@pytest.mark.parametrize("request_id,value", [(2, "SYNTHETIC_REPLY"), (1, "not-a-choice")])
async def test_wrong_request_or_choice_refuses_and_retires(configured, tmp_path, request_id, value):
    dependency, _, _, _ = configured
    dependency.base_environment["ROOK_CONFIGURATION_TEST_CASE"] = "select"
    async with client_for(tmp_path, dependency) as client:
        response = await client.post("/agent/chat/configuration", headers=HEADERS, json=begin("oauth.connect", provider="synthetic"))
        await response.content.readline()
        await response.content.readline()
        owner = dependency.active
        refusal = await client.post("/agent/chat/configuration/reply", headers=HEADERS,
                                    json={"v": 1, "type": "reply", "operationId": "a" * 32, "requestId": request_id, "value": value})
        assert refusal.status == 400
        events = await rows(response)
        assert events[-1]["failure_code"] == "protocol_error" and events[-1]["cleanup"] == "exited"
        assert owner._stdin_count == 1  # Untrusted protocol: no further cancellation request.


@pytest.mark.asyncio
async def test_service_dependency_uses_existing_paths_without_creating_configuration(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from rook.agent.chat import service_main
    paths = SimpleNamespace(install_root=tmp_path / "install", data_root=tmp_path / "data")
    monkeypatch.setattr(service_main, "resolve_runtime_paths", lambda: paths)
    def forbidden(*args, **kwargs):
        raise AssertionError("Capability check must not launch or construct a conversation")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", forbidden)
    monkeypatch.setattr(service_main, "build_acp_manager", forbidden)
    dependency = service_main.build_configuration_service({"SYSTEMROOT": "C:/Windows"})
    assert dependency.data_root == paths.data_root
    assert dependency.catalog._prime_root == paths.install_root / "prime"
    assert not dependency.available()
    async with client_for(tmp_path, dependency) as client:
        health = await (await client.get("/agent/chat/health")).json()
        assert not health["configurationAvailable"] and health["runtime"]["available"]
    assert not paths.data_root.exists() and not paths.install_root.exists()


@pytest.mark.asyncio
async def test_absent_nonce_cannot_admit_configuration(configured, tmp_path):
    dependency, calls, _, _ = configured
    async with TestClient(TestServer(server.create_chat_app(FakeManager(tmp_path), expected_nonce="", configuration=dependency))) as client:
        response = await client.post("/agent/chat/configuration", json=begin())
        assert response.status == 403 and not calls


@pytest.mark.asyncio
async def test_terminal_http_delivery_uses_remaining_cleanup_budget(configured, tmp_path, monkeypatch):
    from aiohttp import web
    dependency, _, _, _ = configured
    write = web.StreamResponse.write
    attempted = asyncio.Event()
    async def blocked_settlement(self, data):
        if b'"type":"configuration_settled"' in data:
            attempted.set()
            await asyncio.Event().wait()
        await write(self, data)
    monkeypatch.setattr(web.StreamResponse, "write", blocked_settlement)
    async with client_for(tmp_path, dependency) as client:
        response = await client.post("/agent/chat/configuration", headers=HEADERS, json=begin())
        await asyncio.wait_for(attempted.wait(), 2)
        events = await asyncio.wait_for(rows(response), 1.5)
        assert events[0]["outcome"] == "completed"
        assert all(row["type"] != "configuration_settled" for row in events)


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["duplicate", "surrogate", "extra", "key-limit", "body-limit", "operation", "nul"])
async def test_http_closed_input_refuses_before_spawn(configured, tmp_path, case, caplog):
    dependency, calls, _, _ = configured
    value = begin()
    if case == "extra":
        value["secret"] = "SYNTHETIC_PRIVATE"
    elif case == "key-limit":
        value = begin("apiKey.set", provider="synthetic", key="x" * 16385)
    elif case == "operation":
        value["operation"] = "inference"
    raw = json.dumps(value).encode()
    if case == "duplicate":
        raw = b'{"v":1,' + raw[1:]
    elif case == "surrogate":
        raw = b'{"x":"\\ud800"}'
    elif case == "body-limit":
        raw = b"x" * (256 * 1024 + 1)
    elif case == "nul":
        raw = b'{"x":"\\u0000"}'
    async with client_for(tmp_path, dependency) as client:
        response = await client.post("/agent/chat/configuration", headers=HEADERS, data=raw)
        assert response.status == 400 and not calls
        assert "SYNTHETIC_PRIVATE" not in (await response.text()) + caplog.text


@pytest.mark.asyncio
async def test_cancel_before_run_discards_private_input_without_spawn(configured):
    from rook.agent.chat.configuration_process import PrimeConfigurationOperation
    from rook.agent.chat.configuration_protocol import validate_begin
    dependency, calls, _, _ = configured
    request = validate_begin(begin("apiKey.set", provider="synthetic", key="SYNTHETIC_KEY_NAME"))
    owner = PrimeConfigurationOperation(dependency.catalog.latest(), request, dependency.base_environment, dependency.data_root)
    async def emit(record):
        raise AssertionError("No child may emit")
    owner.cancel(request.operation_id)
    settlement = await owner.run(emit)
    assert not calls and not request.input
    assert settlement.cleanup == "exited" and settlement.failure_code == "cancelled"


@pytest.mark.asyncio
async def test_spawn_error_is_safe_and_releases_slot(configured, tmp_path, monkeypatch, caplog):
    dependency, _, _, _ = configured
    async def failed_spawn(*args, **kwargs):
        raise OSError("SYNTHETIC_PRIVATE")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", failed_spawn)
    async with client_for(tmp_path, dependency) as client:
        events = await rows(await client.post("/agent/chat/configuration", headers=HEADERS, json=begin()))
        assert events[-1]["failure_code"] == "spawn_failed" and events[-1]["cleanup"] == "exited"
        assert dependency.active is None
        assert "SYNTHETIC_PRIVATE" not in json.dumps(events) + caplog.text


@pytest.mark.asyncio
async def test_output_delivery_failure_preserves_saved_result(configured, caplog):
    from rook.agent.chat.configuration_protocol import validate_begin
    dependency, _, children, _ = configured
    async def failed_emit(record):
        raise RuntimeError("SYNTHETIC_PRIVATE")
    owner = dependency.start(validate_begin(begin("apiKey.set", provider="synthetic", key="SYNTHETIC_KEY_NAME")), failed_emit)
    settlement = await asyncio.wait_for(asyncio.shield(dependency.task), 3)
    assert settlement.result.persistence == "saved" and settlement.failure_code == "output_failed"
    assert settlement.cleanup == "exited" and children[0].returncode is not None
    assert not owner.begin.input and "SYNTHETIC_PRIVATE" not in caplog.text


@pytest.mark.asyncio
async def test_caller_cancellation_retains_exact_child_cleanup(configured, tmp_path):
    dependency, _, children, _ = configured
    dependency.base_environment["ROOK_CONFIGURATION_TEST_CASE"] = "oauth"
    async with client_for(tmp_path, dependency) as client:
        response = await client.post("/agent/chat/configuration", headers=HEADERS, json=begin("oauth.connect", provider="synthetic"))
        await response.content.readline()
        await response.content.readline()
        task = dependency.task
        task.cancel()
        settlement = await asyncio.wait_for(asyncio.shield(task), 3)
        assert not task.cancelled() and settlement.cleanup == "exited"
        assert children[0].returncode is not None
        await response.read()


@pytest.mark.parametrize("case", ["secret-field", "provider-count", "adapter-count", "wrong-id", "code-object"])
def test_closed_output_projection_rejects_extra_or_oversized_data(case):
    from rook.agent.chat import configuration_protocol as wire
    data = {"providers": [], "apis": [], "defaults": {"provider": None, "model": None, "reasoning": None}}
    event = {"v": 1, "type": "result", "operationId": "a" * 32, "outcome": "completed",
             "persistence": "not_applicable", "code": "ok", "data": data}
    if case == "secret-field":
        data["credential"] = "SYNTHETIC_PRIVATE"
    elif case == "provider-count":
        data["providers"] = [{}] * 257
    elif case == "adapter-count":
        data["apis"] = [str(i) for i in range(65)]
    elif case == "wrong-id":
        event["operationId"] = "b" * 32
    else:
        event["code"] = {}
    with pytest.raises(wire.ConfigurationError):
        wire.validate_event(event, wire.validate_begin(begin()))


def test_valid_supplementary_unicode_preserves_exact_bytes():
    from rook.agent.chat import configuration_protocol as wire
    event = {"v": 1, "type": "authorize", "operationId": "a" * 32, "url": "https://example.invalid/",
             "instructionCode": "open_browser", "instructions": "code \U0001f511"}
    assert wire.validate_event(wire.parse_record(wire.encode_record(event, wire.OUTPUT_RECORD)),
                               wire.validate_begin(begin("oauth.connect", provider="synthetic"))) == event
