"""Tests for the agent chat HTTP server."""
import json
import socket
from pathlib import Path

import pytest
import httpx
from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase
from unittest.mock import AsyncMock, patch
from rook.agent.chat import server as chat_server
from rook.agent.chat.server import create_chat_app
from rook.agent.chat.conversation_store import ConversationStore
from rook.agent.chat.prompt_builder import PromptBuilder
from rook.agent.chat.chat_runner import ChatRunner, ChatEvent
from rook import bridge


class TestChatServer(AioHTTPTestCase):
    async def get_application(self):
        # Inject fresh dependencies per test to avoid cross-test contamination
        self.store = ConversationStore()
        self.builder = PromptBuilder()
        self.runner = ChatRunner()
        return create_chat_app(
            store=self.store,
            builder=self.builder,
            runner=self.runner,
        )

    async def test_list_personas(self):
        resp = await self.client.get("/agent/chat/personas")
        assert resp.status == 200
        data = await resp.json()
        # Should list available personas
        assert isinstance(data, list)
        assert len(data) > 0
        # Each should have label and persona name
        assert "persona" in data[0]
        assert "label" in data[0]

    async def test_health(self):
        with patch("rook.agent.chat.server.collect_runtime_facts", new=AsyncMock(return_value={
            "rhino": {"connected": True, "data": "pong"},
            "prompt": {"available": True, "is_active": False, "prompt": "Command"},
            "verified_runtime_facts": ["Rhino bridge is connected and tool execution is available."],
        })):
            resp = await self.client.get("/agent/chat/health")
            assert resp.status == 200
            data = await resp.json()
            assert data["service"]["ok"] is True
            assert data["runtime"]["rhino"]["connected"] is True

    async def test_start_conversation(self):
        resp = await self.client.post(
            "/agent/chat/start",
            json={"persona": "worker"},
        )
        assert resp.status == 200
        data = await resp.json()
        assert "conversation_id" in data
        assert data["persona"] == "worker"

    async def test_start_conversation_records_document_serial_number(self):
        resp = await self.client.post(
            "/agent/chat/start",
            json={"persona": "worker", "documentSerialNumber": 77},
        )
        assert resp.status == 200
        data = await resp.json()
        conv = self.store.get(data["conversation_id"])
        assert conv is not None
        assert conv.document_serial_number == 77
        assert data["documentSerialNumber"] == 77

    async def test_stop_conversation(self):
        # Start one first
        resp = await self.client.post(
            "/agent/chat/start",
            json={"persona": "worker"},
        )
        data = await resp.json()
        conv_id = data["conversation_id"]

        # Stop it
        resp = await self.client.post(
            "/agent/chat/stop",
            json={"conversation_id": conv_id},
        )
        assert resp.status == 200
        stop_data = await resp.json()
        assert stop_data["stopped"] is True

    async def test_stop_nonexistent(self):
        resp = await self.client.post(
            "/agent/chat/stop",
            json={"conversation_id": "conv_doesnotexist"},
        )
        assert resp.status == 404

    async def test_ui_response_accepted(self):
        """POST /agent/chat/ui-response appends message to conversation."""
        # Start a conversation first
        resp = await self.client.post(
            "/agent/chat/start",
            json={"persona": "worker"},
        )
        data = await resp.json()
        conv_id = data["conversation_id"]

        # Send a UI response
        resp = await self.client.post(
            "/agent/chat/ui-response",
            json={
                "conversation_id": conv_id,
                "block_id": "blk_test1234",
                "value": {"height": 10},
            },
        )
        assert resp.status == 200
        result = await resp.json()
        assert result["accepted"] is True

        # Verify CORS header is present
        assert resp.headers.get("Access-Control-Allow-Origin") == "*"

    async def test_ui_response_missing_fields(self):
        """POST /agent/chat/ui-response rejects missing conversation_id or block_id."""
        resp = await self.client.post(
            "/agent/chat/ui-response",
            json={"conversation_id": "conv_x"},
        )
        assert resp.status == 400

        resp = await self.client.post(
            "/agent/chat/ui-response",
            json={"block_id": "blk_x"},
        )
        assert resp.status == 400

    async def test_ui_response_not_found(self):
        """POST /agent/chat/ui-response returns 404 for unknown conversation."""
        resp = await self.client.post(
            "/agent/chat/ui-response",
            json={
                "conversation_id": "conv_nonexistent",
                "block_id": "blk_test",
                "value": "confirm",
            },
        )
        assert resp.status == 404

    async def test_ui_response_cors_preflight(self):
        """OPTIONS /agent/chat/ui-response returns CORS headers."""
        resp = await self.client.options("/agent/chat/ui-response")
        assert resp.status == 204
        assert resp.headers.get("Access-Control-Allow-Origin") == "*"
        assert "POST" in resp.headers.get("Access-Control-Allow-Methods", "")

    async def test_message_runs_turn_with_scoped_rhino_context(self):
        captured: list[dict[str, int | None]] = []

        class ContextCapturingRunner:
            async def run_turn(self, conv, message, system_prompt):
                captured.append({
                    "conversation_document": conv.document_serial_number,
                    **bridge.get_rhino_request_context(),
                })
                yield ChatEvent("done", usage={})

        self.app[chat_server._RUNNER_KEY] = ContextCapturingRunner()
        self.app[chat_server._RHINO_PROCESS_ID_KEY] = 2468

        start = await self.client.post(
            "/agent/chat/start",
            json={"persona": "worker"},
        )
        assert start.status == 200
        conv_id = (await start.json())["conversation_id"]

        resp = await self.client.post(
            "/agent/chat/message",
            json={
                "conversation_id": conv_id,
                "message": "make a sphere",
                "documentSerialNumber": 91,
            },
        )
        assert resp.status == 200
        await resp.text()

        assert captured == [{
            "conversation_document": 91,
            "port": None,
            "process_id": 2468,
            "document_serial_number": 91,
        }]
        conv = self.store.get(conv_id)
        assert conv is not None
        assert conv.document_serial_number == 91


def test_write_discovery_file_uses_atomic_replace(monkeypatch, tmp_path):
    replaced: dict[str, str] = {}

    def fake_replace(src: str, dst: str) -> None:
        replaced["src"] = src
        replaced["dst"] = dst
        Path(dst).write_text(Path(src).read_text(encoding="utf-8"), encoding="utf-8")
        Path(src).unlink()

    monkeypatch.setattr(chat_server, "DISCOVERY_FOLDER", tmp_path)
    monkeypatch.setattr(chat_server.os, "replace", fake_replace)

    path = chat_server._write_discovery_file(4321, "rhino-panel", 2468)

    assert path == tmp_path / "chat-service-4321.json"
    assert Path(replaced["dst"]) == path
    assert replaced["src"].endswith(".tmp")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["host"] == "127.0.0.1"
    assert payload["port"] == 4321
    assert payload["owner"] == "rhino-panel"
    assert payload["rhinoProcessId"] == 2468


@pytest.mark.asyncio
async def test_start_chat_server_port_zero_writes_actual_bound_port(monkeypatch, tmp_path):
    monkeypatch.setattr(chat_server, "DISCOVERY_FOLDER", tmp_path)
    monkeypatch.setattr(
        chat_server,
        "collect_runtime_facts",
        AsyncMock(return_value={"rhino": {"connected": True}}),
    )

    try:
        await chat_server.start_chat_server(
            port=0,
            owner="rhino-panel",
            rhino_process_id=2468,
        )

        files = list(tmp_path.glob("chat-service-*.json"))
        assert len(files) == 1

        payload = json.loads(files[0].read_text(encoding="utf-8"))
        assert payload["service"] == "agent-chat"
        assert payload["host"] == "127.0.0.1"
        assert payload["owner"] == "rhino-panel"
        assert payload["rhinoProcessId"] == 2468
        assert payload["port"] > 0
        assert files[0].name == f"chat-service-{payload['port']}.json"

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"http://127.0.0.1:{payload['port']}/agent/chat/health",
                timeout=5.0,
            )

        assert response.status_code == 200
        health = response.json()
        assert health["service"]["host"] == "127.0.0.1"
        assert health["service"]["port"] == payload["port"]
        assert health["service"]["owner"] == "rhino-panel"
        assert health["service"]["rhinoProcessId"] == 2468
    finally:
        await chat_server.stop_chat_server()


@pytest.mark.asyncio
async def test_start_chat_server_blocked_port_raises(monkeypatch, tmp_path):
    """Fixed port that is already in use raises OSError — no range fallback."""
    monkeypatch.setattr(chat_server, "DISCOVERY_FOLDER", tmp_path)
    monkeypatch.setattr(
        chat_server,
        "collect_runtime_facts",
        AsyncMock(return_value={"rhino": {"connected": True}}),
    )

    blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    blocker.bind(("127.0.0.1", 0))
    blocker.listen(1)
    blocked_port = blocker.getsockname()[1]

    try:
        with pytest.raises(OSError):
            await chat_server.start_chat_server(
                port=blocked_port,
                owner="rhino-panel",
                rhino_process_id=1357,
            )

        # No discovery file should be written on failure
        files = list(tmp_path.glob("chat-service-*.json"))
        assert len(files) == 0
    finally:
        blocker.close()
        await chat_server.stop_chat_server()
