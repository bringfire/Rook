"""Model-free HTTP integration tests for ACP prompt ownership."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from aiohttp import ClientSession, web
from aiohttp.test_utils import TestClient, TestServer

from rook.agent.chat import server as chat_server
from rook.agent.chat import service_main
from rook.agent.chat import acp_conversation
from rook.agent.chat.acp_conversation import (
    ConversationNotOpen,
    CreateConversationRequest,
    PromptInput,
    PromptResult,
)
from rook.agent.chat.acp_presentation import PromptGeneration
from rook.agent.chat.prime_runtime import RuntimeUnavailable
from rook.runtime_paths import RuntimePaths

from .test_chat_server import FakeManager, VALID_CONVERSATION_ID, _prompt_body
from .test_chat_acp_conversation import FakeProcessFactory, _binding, _manager


@pytest.mark.asyncio
async def test_silent_http_disconnect_cancels_the_owned_prompt(tmp_path, monkeypatch):
    factory = FakeProcessFactory(block_prompt=True)
    manager, _, _, _, _ = _manager(tmp_path, factory=factory)
    view = await manager.create(CreateConversationRequest(_binding(), None, None, None))
    monkeypatch.setattr(chat_server, "_write_discovery_file", lambda *_args: None)
    response = None
    try:
        await chat_server.start_chat_server(port=0, manager=manager, expected_nonce="fixture")
        port = await chat_server._startup_future
        async with ClientSession() as client:
            response = await client.post(
                f"http://127.0.0.1:{port}/agent/chat/conversations/{view.conversation_id}/prompt",
                json=_prompt_body(), headers={chat_server.SESSION_HEADER: "fixture"},
            )
            assert response.status == 200
            process = factory.processes[0]
            await asyncio.wait_for(process.prompt_started.wait(), 1)
            supervisor = manager._resident[view.conversation_id].active_prompt
            assert supervisor is not None
            assert not process.cancelled.is_set()
            # No events have been produced; cancellation cannot rely on a failed write.
            response.close()
            await asyncio.wait_for(process.cancelled.wait(), 1)
            result = await asyncio.wait_for(supervisor.result_task, 1)
            assert process.cancel_count == 1
            assert result.outcome == "cancelled"
    finally:
        if response is not None:
            response.close()
        await manager.close(view.conversation_id)
        await chat_server.stop_chat_server()


@pytest.mark.asyncio
@pytest.mark.parametrize("replacement", [
    "same", "absent", "generation", "process", "roadcreator", "ambiguous",
    "document_closed", "document_replaced", "document_inactive", "document_unreported",
    "document_malformed", "live_generation", "document_timeout",
])
async def test_production_manager_reopen_checks_original_target(tmp_path, monkeypatch, replacement):
    from rook import bridge
    from .test_chat_acp_conversation import FakeRuntimeCatalog, NullSink, _contract, _paths

    paths = _paths(tmp_path)
    factory = FakeProcessFactory()
    catalog = FakeRuntimeCatalog(_contract(tmp_path))
    monkeypatch.setattr(service_main, "get_acp_data_paths", lambda _paths: paths)
    monkeypatch.setattr(service_main, "InstalledRuntimeCatalog", lambda _root: catalog)
    monkeypatch.setattr(service_main, "DirectAcpProcessFactory", lambda _env: factory)
    monkeypatch.setattr(service_main, "resolve_runtime_paths", lambda: RuntimePaths(
        mode="dev", install_root=tmp_path / "app", data_root=tmp_path / "data",
        logs_root=tmp_path / "logs", runtime_root=tmp_path,
        mcp_server_dir=tmp_path / "app/mcp_server", repo_root=tmp_path / "app"))
    binding = _binding()
    state = {"replacement": "same"}
    calls = []
    release = asyncio.Event()

    async def capabilities(request):
        calls.append(request.path)
        return web.json_response({"domains": [], "hostGenerationId":
            "different" if state["replacement"] == "live_generation" else binding.host_generation_id})

    async def document(request):
        calls.append(request.path)
        assert request.query["documentSerialNumber"] == str(binding.rhino_document_serial)
        kind = state["replacement"]
        if kind == "document_timeout":
            await release.wait()
        if kind == "document_closed":
            return web.json_response({"success": False, "error": "No active document"})
        # Mirror native lookup followed by active-document fallback, including an inactive original.
        original_serial = binding.rhino_document_serial
        active_serial = original_serial + 1 if kind in {"document_replaced", "document_inactive"} else original_serial
        open_documents = {active_serial}
        if kind == "document_inactive":
            open_documents.add(original_serial)
        serial = original_serial if original_serial in open_documents else active_serial
        data = {} if kind == "document_unreported" else {"documentSerialNumber":
            str(serial) if kind == "document_malformed" else serial}
        return web.json_response({"success": True, "data": data})

    app = web.Application()
    app.router.add_get("/capabilities", capabilities)
    app.router.add_get("/document", document)
    host = TestServer(app)
    await host.start_server()
    discovery = tmp_path / "discovery"
    discovery.mkdir()
    record = discovery / "instance-fixture-native.json"
    original = {"pluginType": "native", "processId": binding.route_process_id,
                "hostGenerationId": binding.host_generation_id, "port": host.port}
    record.write_text(json.dumps(original), encoding="utf-8")
    monkeypatch.setattr(bridge, "_effective_discovery_folders", lambda: [discovery])
    monkeypatch.setattr(bridge, "_is_pid_alive", lambda _pid: True)
    manager, available = service_main.build_acp_manager({})
    assert available
    view = None
    try:
        view = await manager.create(CreateConversationRequest(binding, None, None, None))
        assert view.target_available
        prompt = await manager.start_prompt(view.conversation_id, PromptInput("fixture", ()), NullSink())
        await prompt.result_task
        await manager.close(view.conversation_id)
        state["replacement"] = replacement
        calls.clear()
        if replacement == "absent":
            record.unlink()
        else:
            changed = dict(original)
            if replacement == "generation":
                changed["hostGenerationId"] = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
            elif replacement == "process":
                changed["processId"] += 1
            elif replacement == "roadcreator":
                changed["pluginType"] = "roadcreator"
            elif replacement == "ambiguous":
                changed["port"] += 1
                (discovery / "instance-second-native.json").write_text(json.dumps(changed), encoding="utf-8")
                changed = original
            record.write_text(json.dumps(changed), encoding="utf-8")
        reopened = await asyncio.wait_for(manager.reopen(view.conversation_id), 5)
        assert reopened.conversation_id == view.conversation_id
        assert reopened.durable
        assert reopened.target_available is (replacement in {"same", "document_inactive"})
        assert manager.store.get(view.conversation_id).binding == binding
        if replacement in {"same", "document_inactive"} or replacement.startswith("document_"):
            assert calls == ["/capabilities", "/document"]
        elif replacement == "live_generation":
            assert calls == ["/capabilities"]
        else:
            assert calls == []
    finally:
        release.set()
        if view is not None and view.conversation_id in manager._resident:
            await manager.close(view.conversation_id)
        await host.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("reopen", [False, True])
async def test_cancelled_availability_probe_launches_no_child_and_releases_claim(tmp_path, reopen):
    from .test_chat_acp_conversation import NullSink

    manager, store, _, factory, _ = _manager(tmp_path)
    view = await manager.create(CreateConversationRequest(_binding(), None, None, None))
    prompt = await manager.start_prompt(view.conversation_id, PromptInput("fixture", ()), NullSink())
    await prompt.result_task
    await manager.close(view.conversation_id)
    original = store.get(view.conversation_id)
    entered = asyncio.Event()

    async def held_probe(_binding):
        entered.set()
        await asyncio.Event().wait()
        return True

    manager._target_available = held_probe
    operation = asyncio.create_task(manager.reopen(view.conversation_id) if reopen else
        manager.create(CreateConversationRequest(_binding(), None, None, None)))
    try:
        await asyncio.wait_for(entered.wait(), 1)
        assert bool(list(store.paths.claims_root.glob("*.claim"))) is reopen
        operation.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(operation, 1)
        assert factory.launch_count == 1
        assert not manager._resident
        assert not list(store.paths.claims_root.glob("*.claim"))
        assert store.get(view.conversation_id) == original
    finally:
        operation.cancel()
        await asyncio.gather(operation, return_exceptions=True)
        await manager.shutdown()


class HangingSupervisor:
    def __init__(self) -> None:
        self.generation = PromptGeneration(1, "acp-1", "prompt-1")
        self.release = asyncio.Event()
        self.cancel_sources: list[str] = []
        self.owner_finally_ran = False
        self._task = asyncio.create_task(self._own_prompt())

    async def _own_prompt(self) -> PromptResult:
        try:
            await self.release.wait()
            return PromptResult("cancelled", "cancelled", "disconnected", False)
        finally:
            self.owner_finally_ran = True

    @property
    def result_task(self):
        return asyncio.shield(self._task)

    def request_cancel(self, source: str) -> bool:
        if self.cancel_sources:
            return False
        self.cancel_sources.append(source)
        return True


class HangingManager(FakeManager):
    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self.supervisor: HangingSupervisor | None = None

    async def start_prompt(self, conversation_id: str, prompt: PromptInput, sink):
        self.prompted.append((conversation_id, prompt))
        self.supervisor = HangingSupervisor()
        return self.supervisor

    async def request_cancel(self, conversation_id: str, source: str) -> bool:
        assert conversation_id == VALID_CONVERSATION_ID
        assert self.supervisor is not None
        self.cancelled.append((conversation_id, source))
        return self.supervisor.request_cancel(source)


@pytest.mark.asyncio
async def test_http_waiter_cancellation_uses_real_manager_and_preserves_clean_resident(
    tmp_path: Path,
):
    factory = FakeProcessFactory(block_prompt=True)
    manager, store, _, _, _ = _manager(tmp_path, factory=factory)
    saved = tmp_path / "saved"
    saved.mkdir()
    view = await manager.create(CreateConversationRequest(_binding(), str(saved), None, None))
    app = chat_server.create_chat_app(manager)

    class Request:
        content_length = len(json.dumps(_prompt_body()).encode("utf-8"))
        match_info = {"conversation_id": view.conversation_id}

        def __init__(self):
            self.app = app

        async def read(self):
            return json.dumps(_prompt_body()).encode("utf-8")

    class Response:
        prepared = False

        async def prepare(self, _request):
            self.prepared = True

        async def write(self, _payload):
            return None

        async def write_eof(self):
            return None

    response = Response()
    original_response = chat_server.web.StreamResponse
    chat_server.web.StreamResponse = lambda **_kwargs: response
    request_task = asyncio.create_task(
        chat_server.handle_prompt(Request())
    )
    try:
        process = factory.processes[0]
        await process.prompt_started.wait()
        resident = manager._resident[view.conversation_id]
        supervisor = resident.active_prompt
        assert supervisor is not None

        request_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await request_task
        await asyncio.sleep(0)

        result = await supervisor.result_task
        assert result.outcome == "cancelled"
        assert process.cancel_count == 1
        assert process.retire_send_close == []
        assert not process.child_exit_observed
        assert manager._resident[view.conversation_id] is resident
        assert resident.active_prompt is None
        assert store.get(view.conversation_id).prime_session_id == factory.prime_session_id
    finally:
        chat_server.web.StreamResponse = original_response
        if view.conversation_id in manager._resident:
            await manager.close(view.conversation_id)


@pytest.mark.asyncio
async def test_http_waiter_cancellation_retires_exact_child_when_settlement_is_uncertain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(acp_conversation, "PROMPT_SETTLEMENT_AFTER_CANCEL_SECONDS", 0.02)
    factory = FakeProcessFactory()
    manager, _, _, _, paths = _manager(tmp_path, factory=factory)
    saved = tmp_path / "saved"
    saved.mkdir()
    view = await manager.create(CreateConversationRequest(_binding(), str(saved), None, None))
    process = factory.processes[0]

    async def never_settles(*_args, **_kwargs):
        process.prompt_count += 1
        process.prompt_started.set()
        await asyncio.Future()

    process.prompt = never_settles
    app = chat_server.create_chat_app(manager)

    class Request:
        content_length = len(json.dumps(_prompt_body()).encode("utf-8"))
        match_info = {"conversation_id": view.conversation_id}

        def __init__(self):
            self.app = app

        async def read(self):
            return json.dumps(_prompt_body()).encode("utf-8")

    class Response:
        prepared = False

        async def prepare(self, _request):
            self.prepared = True

        async def write(self, _payload):
            return None

        async def write_eof(self):
            return None

    response = Response()
    monkeypatch.setattr(chat_server.web, "StreamResponse", lambda **_kwargs: response)
    request_task = asyncio.create_task(chat_server.handle_prompt(Request()))
    await process.prompt_started.wait()
    resident = manager._resident[view.conversation_id]
    supervisor = resident.active_prompt
    assert supervisor is not None

    request_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await request_task
    result = await asyncio.wait_for(supervisor.result_task, timeout=0.5)

    assert result.outcome == "error"
    assert process.cancel_count == 1
    assert process.retire_send_close == [False]
    assert process.child_exit_observed
    assert resident.active_prompt is None
    assert view.conversation_id not in manager._resident
    assert not list(paths.claims_root.glob("*.open.claim"))
    with pytest.raises(ConversationNotOpen):
        await manager.start_prompt(view.conversation_id, PromptInput("no replay", ()), None)


@pytest.mark.asyncio
async def test_cancel_endpoint_is_idempotent_signal_not_prompt_settlement_wait(tmp_path: Path):
    manager = HangingManager(tmp_path)
    client = TestClient(TestServer(chat_server.create_chat_app(manager)))
    await client.start_server()
    try:
        prompt_response = await client.post(
            f"/agent/chat/conversations/{VALID_CONVERSATION_ID}/prompt", json=_prompt_body()
        )
        prompt_body = asyncio.create_task(prompt_response.text())
        for _ in range(100):
            if manager.supervisor is not None:
                break
            await asyncio.sleep(0.01)
        assert manager.supervisor is not None

        first = await client.post(
            f"/agent/chat/conversations/{VALID_CONVERSATION_ID}/cancel", json={}
        )
        second = await client.post(
            f"/agent/chat/conversations/{VALID_CONVERSATION_ID}/cancel", json={}
        )
        assert json.loads(await first.text()) == {"accepted": True}
        assert json.loads(await second.text()) == {"accepted": False}
        assert not prompt_body.done()

        manager.supervisor.release.set()
        rows = [json.loads(line) for line in (await prompt_body).splitlines()]
        assert rows[-1]["outcome"] == "cancelled"
    finally:
        if manager.supervisor is not None and not manager.supervisor._task.done():
            manager.supervisor.release.set()
            await manager.supervisor.result_task
        await client.close()


def test_installed_runtime_catalog_uses_closed_current_pointer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    prime_root = tmp_path / "prime"
    prime_root.mkdir()
    runtime_id = "A" * 64
    (prime_root / "current.json").write_bytes(
        (json.dumps({"runtimeId": runtime_id}, sort_keys=True, separators=(",", ":")) + "\n").encode(
            "utf-8"
        )
    )
    calls = []
    monkeypatch.setattr(
        service_main,
        "load_and_verify_runtime",
        lambda root, selected: calls.append((root, selected)) or "contract",
    )

    catalog = service_main.InstalledRuntimeCatalog(prime_root)

    assert catalog.latest() == "contract"
    assert catalog.get(runtime_id) == "contract"
    assert calls == [(prime_root, runtime_id), (prime_root, runtime_id)]


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        b"{}\n",
        b'{"runtimeId":"bad"}\n',
        b'{"runtimeId":"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA","extra":1}\n',
    ],
)
def test_installed_runtime_catalog_refuses_invalid_current_pointer(tmp_path: Path, payload: bytes):
    prime_root = tmp_path / "prime"
    prime_root.mkdir()
    (prime_root / "current.json").write_bytes(payload)
    with pytest.raises(RuntimeUnavailable):
        service_main.InstalledRuntimeCatalog(prime_root).latest()


def test_installed_runtime_catalog_bounds_current_pointer_before_decoding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    prime_root = tmp_path / "prime"
    prime_root.mkdir()
    current = prime_root / "current.json"
    current.write_bytes(b"x" * 257)

    def unbounded_read_forbidden(_path: Path) -> bytes:
        raise AssertionError("current.json must not be read without a byte bound")

    monkeypatch.setattr(Path, "read_bytes", unbounded_read_forbidden)

    with pytest.raises(RuntimeUnavailable):
        service_main.InstalledRuntimeCatalog(prime_root).latest()


def test_service_manager_composition_uses_product_data_and_preserved_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    runtime_paths = RuntimePaths(
        mode="release",
        install_root=tmp_path / "app",
        data_root=tmp_path / "data",
        logs_root=tmp_path / "logs",
        runtime_root=tmp_path,
        mcp_server_dir=tmp_path / "app" / "mcp_server",
        repo_root=tmp_path / "app",
    )
    monkeypatch.setattr(service_main, "resolve_runtime_paths", lambda: runtime_paths)

    manager, runtime_available = service_main.build_acp_manager({"PRE_DOTENV": "yes"})

    assert manager.store.paths.root == tmp_path / "data" / "rookchat" / "acp" / "v1"
    assert manager.store.paths.conversations_root.is_dir()
    assert manager._process_factory._base_environment == {"PRE_DOTENV": "yes", "ROOK_DATA_DIR": str(tmp_path / "data")}
    assert runtime_available is False


def test_catalog_pins_one_pointer_snapshot_when_later_selection_changes(tmp_path, monkeypatch):
    prime = tmp_path / "prime"
    prime.mkdir()
    pointer = prime / "current.json"
    old, new = "A" * 64, "B" * 64
    pointer.write_bytes(('{"runtimeId":"' + old + '"}\n').encode())
    received = []

    def verify(root, selected):
        pointer.write_bytes(('{"runtimeId":"' + new + '"}\n').encode())
        received.append(selected)
        return selected

    monkeypatch.setattr(service_main, "load_and_verify_runtime", verify)
    assert service_main.InstalledRuntimeCatalog(prime).latest() == old
    assert received == [old]
