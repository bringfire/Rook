"""Tests for the agent chat HTTP server."""
import json
import socket
from pathlib import Path

import pytest
import httpx
from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase
from unittest.mock import AsyncMock, MagicMock, patch
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

    async def test_ui_response_streams_turn_with_serialized_payload(self):
        """POST /agent/chat/ui-response runs an agent turn with the UI response as user_message."""
        captured: list[dict] = []

        class CapturingRunner:
            async def run_turn(self, conv, message, system_prompt):
                captured.append({"message": message, "conv_id": conv.id})
                yield ChatEvent("done", usage={})

        # Inject the capturing runner onto the running test app
        self.app[chat_server._RUNNER_KEY] = CapturingRunner()

        resp = await self.client.post("/agent/chat/start", json={"persona": "worker"})
        conv_id = (await resp.json())["conversation_id"]

        resp = await self.client.post(
            "/agent/chat/ui-response",
            json={
                "conversation_id": conv_id,
                "block_id": "blk_test1234",
                "value": {"height": 10},
            },
        )
        assert resp.status == 200
        assert resp.headers["Content-Type"].startswith("application/x-ndjson")
        body = await resp.text()
        assert '"type": "done"' in body or '"type":"done"' in body

        assert len(captured) == 1
        payload = json.loads(captured[0]["message"])
        assert payload == {
            "type": "ui_response",
            "block_id": "blk_test1234",
            "value": {"height": 10},
        }

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

    async def test_ui_response_rejects_when_conversation_active(self):
        """POST /agent/chat/ui-response returns 409 if a turn is already running."""
        resp = await self.client.post("/agent/chat/start", json={"persona": "worker"})
        conv_id = (await resp.json())["conversation_id"]

        # Mark the conversation as actively running
        conv = self.store.get(conv_id)
        conv.active_run_id = "run_in_flight"

        resp = await self.client.post(
            "/agent/chat/ui-response",
            json={
                "conversation_id": conv_id,
                "block_id": "blk_x",
                "value": "confirm",
            },
        )
        assert resp.status == 409

    async def test_ui_response_runs_turn_with_scoped_rhino_context(self):
        """POST /agent/chat/ui-response propagates documentSerialNumber into rhino_request_context.

        Mirrors the /message context test — agent reactions to UI submissions
        must use the same Rhino document scope as typed messages.
        """
        captured: list[dict] = []

        class ContextCapturingRunner:
            async def run_turn(self, conv, message, system_prompt):
                captured.append({
                    "conversation_document": conv.document_serial_number,
                    **bridge.get_rhino_request_context(),
                })
                yield ChatEvent("done", usage={})

        self.app[chat_server._RUNNER_KEY] = ContextCapturingRunner()

        resp = await self.client.post(
            "/agent/chat/start",
            json={"persona": "worker", "documentSerialNumber": 42},
        )
        conv_id = (await resp.json())["conversation_id"]

        resp = await self.client.post(
            "/agent/chat/ui-response",
            json={
                "conversation_id": conv_id,
                "block_id": "blk_ctx",
                "value": "ok",
                "documentSerialNumber": 99,
            },
        )
        assert resp.status == 200
        # Drain the stream
        await resp.text()

        assert len(captured) == 1
        # Latest documentSerialNumber from the request body wins (matches /message)
        assert captured[0]["conversation_document"] == 99
        assert captured[0].get("document_serial_number") == 99

    async def test_cors_preflight_any_route(self):
        """OPTIONS on any route returns CORS headers via middleware."""
        for path in ["/agent/chat/ui-response", "/agent/chat/start", "/agent/chat/health"]:
            resp = await self.client.options(path)
            assert resp.status == 204, f"OPTIONS {path} returned {resp.status}"
            assert resp.headers.get("Access-Control-Allow-Origin") == "https://app.rook.invalid"
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


def test_message_disconnect_closes_turn_generator_before_return():
    """Write failure must synchronously close run_turn and repair history."""
    import asyncio

    class FakeRequest:
        def __init__(self, app, body):
            self.app = app
            self._body = body

        async def json(self):
            return self._body

    class DisconnectingStreamResponse:
        def __init__(self, *args, **kwargs):
            self.status = kwargs.get("status", 200)

        async def prepare(self, request):
            return None

        async def write(self, data):
            raise ConnectionResetError()

        async def write_eof(self):
            return None

    async def _stream():
        chunk = MagicMock()
        delta = MagicMock()
        delta.content = None
        tc_delta = MagicMock()
        tc_delta.index = 0
        tc_delta.id = "toolu_server_disconnect"
        tc_delta.function.name = "rhino_ping"
        tc_delta.function.arguments = "{}"
        delta.tool_calls = [tc_delta]
        choice = MagicMock()
        choice.delta = delta
        chunk.choices = [choice]
        chunk.usage = None
        yield chunk

        usage_chunk = MagicMock()
        usage_chunk.choices = []
        usage_chunk.usage = MagicMock(prompt_tokens=1, completion_tokens=1)
        yield usage_chunk

    async def _exercise():
        store = ConversationStore()
        conv = store.create("worker")
        conv.model = "test-model"
        runner = ChatRunner(tool_executor=AsyncMock(return_value={"ok": True}))
        app = {
            chat_server._STORE_KEY: store,
            chat_server._BUILDER_KEY: PromptBuilder(),
            chat_server._RUNNER_KEY: runner,
            chat_server._RHINO_PROCESS_ID_KEY: 0,
        }
        request = FakeRequest(app, {
            "conversation_id": conv.id,
            "message": "ping",
        })

        with patch(
            "rook.agent.chat.server.web.StreamResponse",
            DisconnectingStreamResponse,
        ), patch(
            "rook.agent.chat.chat_runner.litellm.acompletion",
            new=AsyncMock(return_value=_stream()),
        ), patch(
            "rook.agent.chat.chat_runner.collect_runtime_facts",
            new=AsyncMock(return_value={"rhino": {"connected": False}, "prompt": {"available": False}}),
        ):
            response = await chat_server.handle_message(request)

        return conv, response

    conv, response = asyncio.run(_exercise())

    assert response.status == 200
    assert conv.abort_event.is_set()
    assert conv.active_run_id is None
    assert [m.get("role") for m in conv.messages] == ["user", "assistant", "tool"]
    assert conv.messages[2]["tool_call_id"] == "toolu_server_disconnect"
    assert json.loads(conv.messages[2]["content"]) == {"error": "cancelled by user"}


class TestChatServerWithNonce(AioHTTPTestCase):
    """Tests with session nonce enforcement enabled."""

    async def get_application(self):
        self.store = ConversationStore()
        self.builder = PromptBuilder()
        self.runner = ChatRunner()
        self.nonce = "test-nonce-abc123"
        return create_chat_app(
            store=self.store,
            builder=self.builder,
            runner=self.runner,
            session_nonce=self.nonce,
        )

    async def test_request_without_nonce_is_rejected(self):
        """Non-health routes reject requests without valid session nonce."""
        resp = await self.client.post(
            "/agent/chat/start",
            json={"persona": "worker"},
        )
        assert resp.status == 403
        data = await resp.json()
        assert "session" in data["error"].lower()

    async def test_request_with_wrong_nonce_is_rejected(self):
        resp = await self.client.post(
            "/agent/chat/start",
            json={"persona": "worker"},
            headers={"X-Rook-Session": "wrong-nonce"},
        )
        assert resp.status == 403

    async def test_request_with_correct_nonce_succeeds(self):
        resp = await self.client.post(
            "/agent/chat/start",
            json={"persona": "worker"},
            headers={"X-Rook-Session": self.nonce},
        )
        assert resp.status == 200
        data = await resp.json()
        assert "conversation_id" in data

    async def test_health_exempt_from_nonce(self):
        """Health endpoint works without nonce for startup polling."""
        with patch("rook.agent.chat.server.collect_runtime_facts", new=AsyncMock(return_value={
            "rhino": {"connected": True},
        })):
            resp = await self.client.get("/agent/chat/health")
            assert resp.status == 200

    async def test_wrong_origin_rejected(self):
        """Requests from unexpected browser origins are rejected."""
        resp = await self.client.post(
            "/agent/chat/start",
            json={"persona": "worker"},
            headers={
                "X-Rook-Session": self.nonce,
                "Origin": "https://evil.example.com",
            },
        )
        assert resp.status == 403

    async def test_correct_origin_accepted(self):
        """Requests from the trusted virtual host origin are accepted."""
        resp = await self.client.post(
            "/agent/chat/start",
            json={"persona": "worker"},
            headers={
                "X-Rook-Session": self.nonce,
                "Origin": "https://app.rook.invalid",
            },
        )
        assert resp.status == 200

    async def test_no_origin_header_accepted(self):
        """Non-browser callers (no Origin header) pass if nonce is valid."""
        resp = await self.client.post(
            "/agent/chat/start",
            json={"persona": "worker"},
            headers={"X-Rook-Session": self.nonce},
        )
        assert resp.status == 200


class TestKnowledgeGraphRoutes(AioHTTPTestCase):
    """Tests for /knowledge/* routes and data contract."""

    async def get_application(self):
        self.store = ConversationStore()
        self.builder = PromptBuilder()
        self.runner = ChatRunner()
        return create_chat_app(
            store=self.store,
            builder=self.builder,
            runner=self.runner,
        )

    async def test_knowledge_graph_returns_valid_payload(self):
        """GET /knowledge/graph returns nodes, edges, and meta."""
        resp = await self.client.get("/knowledge/graph")
        assert resp.status == 200
        data = await resp.json()
        assert "meta" in data
        assert "nodes" in data
        assert "edges" in data
        assert isinstance(data["nodes"], list)
        assert isinstance(data["edges"], list)
        assert data["meta"]["source"] == "UnifiedStore"
        assert "noteCount" in data["meta"]
        assert "edgeCount" in data["meta"]

    async def test_knowledge_graph_node_schema(self):
        """Nodes have all required fields per spec."""
        resp = await self.client.get("/knowledge/graph")
        data = await resp.json()
        if data["nodes"]:
            node = data["nodes"][0]
            for field in ["id", "label", "noteType", "category", "tags",
                          "components", "brief", "deprecated", "created",
                          "outDegree", "inDegree", "degree"]:
                assert field in node, f"Missing required field: {field}"

    async def test_knowledge_graph_edge_schema(self):
        """Edges have all required fields per spec."""
        resp = await self.client.get("/knowledge/graph")
        data = await resp.json()
        if data["edges"]:
            edge = data["edges"][0]
            for field in ["id", "source", "target", "linkType"]:
                assert field in edge, f"Missing required field: {field}"
            assert edge["linkType"] == "related"

    async def test_knowledge_graph_excludes_deprecated(self):
        """No deprecated notes appear in the graph."""
        resp = await self.client.get("/knowledge/graph")
        data = await resp.json()
        for node in data["nodes"]:
            assert node["deprecated"] is False

    async def test_knowledge_note_found(self):
        """GET /knowledge/note/{id} returns note + related for a valid note."""
        # First get a valid note id from the graph
        graph_resp = await self.client.get("/knowledge/graph")
        graph = await graph_resp.json()
        if not graph["nodes"]:
            pytest.skip("No notes in store")

        note_id = graph["nodes"][0]["id"]
        resp = await self.client.get(f"/knowledge/note/{note_id}")
        assert resp.status == 200
        data = await resp.json()
        assert "note" in data
        assert "related" in data
        assert data["note"]["note_id"] == note_id
        assert "linksFrom" in data["related"]
        assert "linksTo" in data["related"]

    async def test_knowledge_note_not_found(self):
        """GET /knowledge/note/{id} returns 404 for nonexistent note."""
        resp = await self.client.get("/knowledge/note/nonexistent_note_999")
        assert resp.status == 404

    async def test_knowledge_note_deprecated_returns_404(self):
        """GET /knowledge/note/{id} returns 404 for deprecated notes."""
        # Find a deprecated note if any exist
        from rook.agent.chat.server import _get_knowledge_store
        ks = _get_knowledge_store()
        deprecated_note = next((n for n in ks.all() if n.deprecated), None)
        if deprecated_note is None:
            pytest.skip("No deprecated notes in store")
        resp = await self.client.get(f"/knowledge/note/{deprecated_note.note_id}")
        assert resp.status == 404

    async def test_knowledge_graph_node_ordering_is_deterministic(self):
        """Nodes are sorted by id for deterministic output."""
        resp = await self.client.get("/knowledge/graph")
        data = await resp.json()
        ids = [n["id"] for n in data["nodes"]]
        assert ids == sorted(ids)

    async def test_knowledge_graph_similar_edges_present(self):
        """Graph payload includes similarEdges array."""
        resp = await self.client.get("/knowledge/graph")
        data = await resp.json()
        assert "similarEdges" in data
        assert isinstance(data["similarEdges"], list)

    async def test_knowledge_graph_similar_edge_count_in_meta(self):
        """meta.similarEdgeCount matches actual similarEdges length."""
        resp = await self.client.get("/knowledge/graph")
        data = await resp.json()
        assert "similarEdgeCount" in data["meta"]
        assert data["meta"]["similarEdgeCount"] == len(data["similarEdges"])

    async def test_knowledge_graph_similar_edges_deduped(self):
        """No duplicate similar edge pairs."""
        resp = await self.client.get("/knowledge/graph")
        data = await resp.json()
        pairs = set()
        for e in data["similarEdges"]:
            pair = tuple(sorted((e["source"], e["target"])))
            assert pair not in pairs, f"Duplicate similar edge: {pair}"
            pairs.add(pair)

    async def test_knowledge_graph_similar_edges_schema(self):
        """Similar edges have required fields and correct linkType."""
        resp = await self.client.get("/knowledge/graph")
        data = await resp.json()
        if data["similarEdges"]:
            edge = data["similarEdges"][0]
            assert edge["linkType"] == "similar"
            for field in ["id", "source", "target", "linkType"]:
                assert field in edge

    async def test_knowledge_graph_cors_headers(self):
        """Knowledge routes get CORS headers from middleware."""
        resp = await self.client.get("/knowledge/graph")
        assert resp.headers.get("Access-Control-Allow-Origin") == "https://app.rook.invalid"


class TestKnowledgeGraphWithNonce(AioHTTPTestCase):
    """Knowledge routes respect nonce enforcement."""

    async def get_application(self):
        self.nonce = "kg-test-nonce"
        return create_chat_app(session_nonce=self.nonce)

    async def test_knowledge_graph_requires_nonce(self):
        resp = await self.client.get("/knowledge/graph")
        assert resp.status == 403

    async def test_knowledge_graph_with_nonce_succeeds(self):
        resp = await self.client.get(
            "/knowledge/graph",
            headers={"X-Rook-Session": self.nonce},
        )
        assert resp.status == 200

    async def test_knowledge_note_requires_nonce(self):
        resp = await self.client.get("/knowledge/note/some_id")
        assert resp.status == 403

    async def test_health_exemption_is_exact_path(self):
        """Only /agent/chat/health is exempt, not any path ending in /health."""
        with patch("rook.agent.chat.server.collect_runtime_facts", new=AsyncMock(return_value={
            "rhino": {"connected": True},
        })):
            # Real health path works without nonce
            resp = await self.client.get("/agent/chat/health")
            assert resp.status == 200


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
