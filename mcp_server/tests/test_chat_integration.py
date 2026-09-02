"""Model-free HTTP integration tests for ACP prompt ownership."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from aiohttp.test_utils import TestClient, TestServer

from rook.agent.chat import server as chat_server
from rook.agent.chat import service_main
from rook.agent.chat.acp_conversation import PromptInput, PromptResult
from rook.agent.chat.acp_presentation import PromptGeneration
from rook.agent.chat.prime_runtime import RuntimeUnavailable
from rook.runtime_paths import RuntimePaths

from .test_chat_server import FakeManager, VALID_CONVERSATION_ID, _prompt_body


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
async def test_http_waiter_cancellation_does_not_cancel_service_owned_prompt(tmp_path: Path):
    manager = HangingManager(tmp_path)
    app = chat_server.create_chat_app(manager)

    class Request:
        content_length = len(json.dumps(_prompt_body()).encode("utf-8"))
        match_info = {"conversation_id": VALID_CONVERSATION_ID}

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
        for _ in range(100):
            if manager.supervisor is not None:
                break
            await asyncio.sleep(0.01)
        supervisor = manager.supervisor
        assert supervisor is not None

        request_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await request_task
        await asyncio.sleep(0)

        assert supervisor.cancel_sources == ["http_waiter"]
        assert not supervisor._task.cancelled()
        assert not supervisor.owner_finally_ran

        supervisor.release.set()
        result = await supervisor.result_task
        assert result.outcome == "cancelled"
        assert supervisor.owner_finally_ran
    finally:
        chat_server.web.StreamResponse = original_response
        if manager.supervisor is not None and not manager.supervisor._task.done():
            manager.supervisor.release.set()
            await manager.supervisor.result_task


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
    current.write_bytes(b"x" * (service_main._MAX_CURRENT_POINTER_BYTES + 1))

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
    assert manager._process_factory._base_environment == {"PRE_DOTENV": "yes"}
    assert runtime_available is False
