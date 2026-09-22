"""Tests for the agent chat HTTP server."""
import asyncio
import copy
import importlib
import json
import socket
import threading
from pathlib import Path
from dataclasses import replace
from typing import Any

import pytest
import httpx
from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase
from unittest.mock import AsyncMock, MagicMock, patch
from rook.agent.chat import server as chat_server
from rook.agent.chat import model_status
from rook.agent.chat.server import create_chat_app
from rook.agent.chat.conversation_store import ConversationStore
from rook.agent.chat.prompt_builder import PromptBuilder
from rook.agent.chat.chat_runner import ChatRunner, ChatEvent
from rook.agent.minimal_intent_worker_integration import (
    MinimalPlannerDraftAdapter,
    run_minimal_intent_worker_initial_body_integration,
)
from rook.learning.plan_graph import NodeEvidence
from rook import bridge
from rook.providers.vertex_auth import VertexAuthError


_WORKER_FIRST_INTENT = "Create one clean C# component"
_WORKER_FIRST_BODY = "A = 42.0;"


class _ApplicationSlot:
    def __init__(self) -> None:
        self.callback = self._unexpected

    async def _unexpected(self, intent: str):
        raise AssertionError(f"unexpected Worker-first application call: {intent}")

    async def __call__(self, intent: str):
        return await self.callback(intent)


class _RoutePlannerTransport:
    def __init__(self, *, failure: bool = False) -> None:
        self.failure = failure

    def send(self, prompt):
        if self.failure:
            raise RuntimeError("private Planner failure")
        return json.dumps(
            {
                "goal": _WORKER_FIRST_INTENT,
                "capability": "grasshopper_csharp_component",
                "interface": {
                    "inputs": [],
                    "outputs": [{"name": "A", "type": "double"}],
                },
                "acceptance": "clean_compile_receipt",
            },
            separators=(",", ":"),
        )


class _RouteWorkerTransport:
    def __init__(self, *, refuse: bool = False) -> None:
        self.refuse = refuse

    def send(self, prompt):
        payload = (
            {
                "schema": "rook.local_worker_turn_response:v1",
                "kind": "refusal",
                "category": "unsupported_action",
                "reason": "SENTINEL Worker-authored refusal",
            }
            if self.refuse
            else {
                "schema": "rook.local_worker_turn_response:v1",
                "kind": "action_request",
                "action_id": "draft_create_body",
                "rationale": "Author the initial body.",
                "input": {"code": _WORKER_FIRST_BODY},
            }
        )
        return json.dumps(payload, separators=(",", ":"))


class _RouteCreateExecutor:
    def __init__(
        self,
        *,
        errors: int = 0,
        warnings: int = 0,
        raise_after_entry: bool = False,
        mutation_status: str = "created",
    ) -> None:
        self.errors = errors
        self.warnings = warnings
        self.raise_after_entry = raise_after_entry
        self.mutation_status = mutation_status
        self.contexts: list[dict[str, int | None]] = []

    def __call__(self, tool_name: str, params: dict[str, Any]):
        self.contexts.append(bridge.get_rhino_request_context())
        if tool_name != "gh_create_csharp_script":
            raise AssertionError(f"unexpected tool: {tool_name}")
        if params.get("code") != _WORKER_FIRST_BODY:
            raise AssertionError("unexpected Worker-authored body")
        if self.raise_after_entry:
            raise RuntimeError("private post-dispatch failure")
        verification_status = "failed" if self.errors else "passed"
        return {
            "success": verification_status == "passed",
            "data": {
                "script_receipt": {
                    "version": 1,
                    "operation": "create",
                    "language": "csharp",
                    "artifact_status": (
                        "created_with_errors" if self.errors else "usable"
                    ),
                    "mutation": {
                        "status": self.mutation_status,
                        "component_guid": "private-guid",
                    },
                    "verification": {
                        "status": verification_status,
                        "target_error_count": self.errors,
                        "target_warning_count": self.warnings,
                    },
                    "repair_anchor": {
                        "component_guid": "private-guid",
                        "language": "csharp",
                        "target_errors": ["private diagnostic"] * self.errors,
                    },
                }
            },
        }


class _NativeWorkerFirstApplication:
    def __init__(
        self,
        *,
        planner_failure: bool = False,
        worker_refusal: bool = False,
        executor: _RouteCreateExecutor | None = None,
    ) -> None:
        self.planner_failure = planner_failure
        self.worker_refusal = worker_refusal
        self.executor = executor or _RouteCreateExecutor()
        self.contexts: list[dict[str, int | None]] = []

    async def __call__(self, intent: str):
        self.contexts.append(bridge.get_rhino_request_context())
        return await run_minimal_intent_worker_initial_body_integration(
            intent,
            planner_adapter=MinimalPlannerDraftAdapter(
                _RoutePlannerTransport(failure=self.planner_failure)
            ),
            worker_transport=_RouteWorkerTransport(refuse=self.worker_refusal),
            tool_executor=self.executor,
        )


class TestChatServer(AioHTTPTestCase):
    async def get_application(self):
        # Inject fresh dependencies per test to avoid cross-test contamination
        self.store = ConversationStore()
        self.builder = PromptBuilder()
        self.runner = ChatRunner()
        self.worker_first_application = _ApplicationSlot()
        return create_chat_app(
            store=self.store,
            builder=self.builder,
            runner=self.runner,
            worker_first_application=self.worker_first_application,
            rhino_process_id=2468,
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

    async def test_models_without_conversation_id_preserves_slice1_payload(self):
        payload = {
            "active_profile": "cloud",
            "profile_source": "file",
            "roles": {},
            "personas": [],
            "local_providers": {},
            "allowed_model_overrides": [],
        }
        build_models_payload = AsyncMock(return_value=payload)
        with patch(
            "rook.agent.chat.server.model_status.build_models_payload",
            new=build_models_payload,
        ):
            resp = await self.client.get("/agent/chat/models")

        assert resp.status == 200
        assert await resp.json() == payload
        build_models_payload.assert_awaited_once_with(builder=self.builder)
        assert resp.headers["Cache-Control"] == "no-store"
        assert resp.headers["Pragma"] == "no-cache"
        assert resp.headers["Expires"] == "0"

    async def test_models_with_conversation_id_includes_conversation_status(self):
        conv = self.store.create("worker")
        conv.model = "anthropic/worker"
        conv.api_base = ""
        conv.model_source = "persona"
        conv.api_base_source = "none"
        conv.pending_model = "ollama_chat/qwen3:30b"
        conv.pending_api_base = ""
        conv.pending_model_source = "agent_tool"
        conv.pending_api_base_source = "none"

        payload = {
            "active_profile": "cloud",
            "profile_source": "file",
            "roles": {},
            "personas": [],
            "local_providers": {},
            "allowed_model_overrides": [],
        }
        with patch(
            "rook.agent.chat.server.model_status.build_models_payload",
            new=AsyncMock(return_value=payload),
        ):
            resp = await self.client.get(
                f"/agent/chat/models?conversation_id={conv.id}"
            )

        assert resp.status == 200
        data = await resp.json()
        assert data["conversation"]["conversation_id"] == conv.id
        assert data["conversation"]["active_model"] == "anthropic/worker"
        assert data["conversation"]["pending_model"] == "ollama_chat/qwen3:30b"
        assert "api_base" not in data["conversation"]

    async def test_models_with_unknown_conversation_id_returns_404(self):
        resp = await self.client.get("/agent/chat/models?conversation_id=conv_missing")
        assert resp.status == 404

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

    async def test_start_rejects_unavailable_model_override(self):
        resolver = AsyncMock(
            side_effect=model_status.ModelOverrideUnavailable(
                "openai/not-allowed",
                ["anthropic/worker"],
            )
        )

        with patch(
            "rook.agent.chat.server.model_status.resolve_allowed_model_override",
            new=resolver,
        ):
            resp = await self.client.post(
                "/agent/chat/start",
                json={
                    "persona": "worker",
                    "model_override": "openai/not-allowed",
                    "api_base": "https://malicious.example/v1",
                },
            )

        assert resp.status == 400
        data = await resp.json()
        assert data["code"] == "model_override_unavailable"
        assert data["model_override"] == "openai/not-allowed"
        assert len(self.store._conversations) == 0
        resolver.assert_awaited_once_with("openai/not-allowed")

    async def test_start_applies_detected_lmstudio_resolution(self):
        resolution = model_status.ModelOverrideResolution(
            model_override="openai/lmstudio-community/qwen",
            api_base="http://127.0.0.1:1234/v1",
            routing="local",
            provider="openai",
            api_base_source="detected_lmstudio",
        )
        resolver = AsyncMock(return_value=resolution)

        with patch(
            "rook.agent.chat.server.model_status.resolve_allowed_model_override",
            new=resolver,
        ):
            resp = await self.client.post(
                "/agent/chat/start",
                json={
                    "persona": "worker",
                    "model_override": "openai/lmstudio-community/qwen",
                    "api_base": "https://malicious.example/v1",
                },
            )

        assert resp.status == 200
        data = await resp.json()
        conv = self.store.get(data["conversation_id"])
        assert conv is not None
        assert data["model"] == "openai/lmstudio-community/qwen"
        assert conv.model == "openai/lmstudio-community/qwen"
        assert conv.api_base == "http://127.0.0.1:1234/v1"
        assert conv.model_source == "start_override"
        assert conv.api_base_source == "detected_lmstudio"
        resolver.assert_awaited_once_with("openai/lmstudio-community/qwen")

    async def test_set_conversation_model_rejects_while_active(self):
        conv = self.store.create("worker")
        conv.active_run_id = "running"

        resp = await self.client.post(
            "/agent/chat/model",
            json={
                "conversation_id": conv.id,
                "model_override": "ollama_chat/qwen3",
            },
        )

        assert resp.status == 409
        data = await resp.json()
        assert data["code"] == "conversation_processing"

    async def test_set_conversation_model_applies_when_inactive(self):
        conv = self.store.create("worker")
        resolution = model_status.ModelOverrideResolution(
            model_override="ollama_chat/qwen3",
            api_base="http://127.0.0.1:11434",
            routing="local",
            provider="ollama_chat",
            api_base_source="active_profile",
        )
        resolver = AsyncMock(return_value=resolution)

        with patch(
            "rook.agent.chat.server.model_status.resolve_allowed_model_override",
            new=resolver,
        ):
            resp = await self.client.post(
                "/agent/chat/model",
                json={
                    "conversation_id": conv.id,
                    "model_override": "ollama_chat/qwen3",
                    "api_base": "https://malicious.example/v1",
                    "reason": "panel selected model",
                },
            )

        assert resp.status == 200
        data = await resp.json()
        assert data["conversation_id"] == conv.id
        assert data["persona"] == "worker"
        assert data["active_model"] == "ollama_chat/qwen3"
        assert conv.model == "ollama_chat/qwen3"
        assert conv.api_base == "http://127.0.0.1:11434"
        assert conv.model_source == "panel_endpoint"
        assert conv.api_base_source == "active_profile"
        resolver.assert_awaited_once_with("ollama_chat/qwen3")

    async def test_set_conversation_model_rejects_if_conversation_becomes_active_during_resolution(self):
        conv = self.store.create("worker")
        conv.model = "anthropic/current"
        conv.api_base = ""
        resolution = model_status.ModelOverrideResolution(
            model_override="ollama_chat/qwen3",
            api_base="http://127.0.0.1:11434",
            routing="local",
            provider="ollama_chat",
            api_base_source="active_profile",
        )

        async def resolve_with_race(model_override):
            conv.active_run_id = "running"
            return resolution

        with patch(
            "rook.agent.chat.server.model_status.resolve_allowed_model_override",
            new=resolve_with_race,
        ):
            resp = await self.client.post(
                "/agent/chat/model",
                json={
                    "conversation_id": conv.id,
                    "model_override": "ollama_chat/qwen3",
                },
            )

        assert resp.status == 409
        data = await resp.json()
        assert data["code"] == "conversation_processing"
        assert conv.model == "anthropic/current"
        assert conv.api_base == ""

    async def _exercise_prepare_model_set_race(self, handler, body):
        class FakeRequest:
            def __init__(self, app, request_body):
                self.app = app
                self._body = request_body

            async def json(self):
                return self._body

        class PreparingStreamResponse:
            nested_response = None

            def __init__(self, *args, **kwargs):
                self.status = kwargs.get("status", 200)

            async def prepare(self, request):
                model_request = FakeRequest(request.app, {
                    "conversation_id": body["conversation_id"],
                    "model_override": "ollama_chat/qwen3",
                })
                self.__class__.nested_response = await chat_server.handle_set_model(
                    model_request
                )
                return None

            async def write(self, data):
                return None

            async def write_eof(self):
                return None

        class CapturingRunner:
            def __init__(self):
                self.turn_start_models = []

            async def run_turn(
                self, conv, message, system_prompt, model_payload_builder=None
            ):
                self.turn_start_models.append(conv.model)
                yield ChatEvent("done", usage={})

        conv = self.store.create("worker")
        conv.model = "anthropic/current"
        conv.api_base = ""
        body["conversation_id"] = conv.id
        runner = CapturingRunner()
        app = {
            chat_server._STORE_KEY: self.store,
            chat_server._BUILDER_KEY: self.builder,
            chat_server._RUNNER_KEY: runner,
            chat_server._RHINO_PROCESS_ID_KEY: 0,
        }
        resolution = model_status.ModelOverrideResolution(
            model_override="ollama_chat/qwen3",
            api_base="http://127.0.0.1:11434",
            routing="local",
            provider="ollama_chat",
            api_base_source="active_profile",
        )

        with patch(
            "rook.agent.chat.server.web.StreamResponse",
            PreparingStreamResponse,
        ), patch(
            "rook.agent.chat.server.model_status.resolve_allowed_model_override",
            new=AsyncMock(return_value=resolution),
        ):
            response = await handler(FakeRequest(app, body))

        return conv, runner, response, PreparingStreamResponse.nested_response

    async def test_message_rejects_model_set_during_stream_prepare(self):
        conv, runner, response, nested_response = await self._exercise_prepare_model_set_race(
            chat_server.handle_message,
            {
                "message": "start this turn",
            },
        )

        assert response.status == 200
        assert nested_response.status == 409
        data = json.loads(nested_response.text)
        assert data["code"] == "conversation_processing"
        assert runner.turn_start_models == ["anthropic/current"]
        assert conv.model == "anthropic/current"
        assert conv.active_run_id is None

    async def test_ui_response_rejects_model_set_during_stream_prepare(self):
        conv, runner, response, nested_response = await self._exercise_prepare_model_set_race(
            chat_server.handle_ui_response,
            {
                "block_id": "blk_prepare_race",
                "value": {"accepted": True},
            },
        )

        assert response.status == 200
        assert nested_response.status == 409
        data = json.loads(nested_response.text)
        assert data["code"] == "conversation_processing"
        assert runner.turn_start_models == ["anthropic/current"]
        assert conv.model == "anthropic/current"
        assert conv.active_run_id is None

    async def _exercise_build_system_failure_does_not_reserve(self, handler, body):
        class FakeRequest:
            def __init__(self, app, request_body):
                self.app = app
                self._body = request_body

            async def json(self):
                return self._body

        class BrokenBuilder:
            def build_system(self, persona):
                raise RuntimeError(f"prompt build failed for {persona}")

        conv = self.store.create("worker")
        body["conversation_id"] = conv.id
        app = {
            chat_server._STORE_KEY: self.store,
            chat_server._BUILDER_KEY: BrokenBuilder(),
            chat_server._RUNNER_KEY: self.runner,
            chat_server._RHINO_PROCESS_ID_KEY: 0,
        }

        with pytest.raises(RuntimeError, match="prompt build failed"):
            await handler(FakeRequest(app, body))

        assert conv.active_run_id is None

    async def test_message_build_system_failure_does_not_leave_processing_sentinel(self):
        await self._exercise_build_system_failure_does_not_reserve(
            chat_server.handle_message,
            {
                "message": "start this turn",
            },
        )

    async def test_ui_response_build_system_failure_does_not_leave_processing_sentinel(self):
        await self._exercise_build_system_failure_does_not_reserve(
            chat_server.handle_ui_response,
            {
                "block_id": "blk_prompt_failure",
                "value": {"accepted": True},
            },
        )

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
            async def run_turn(self, conv, message, system_prompt, model_payload_builder=None):
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
            async def run_turn(self, conv, message, system_prompt, model_payload_builder=None):
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
            async def run_turn(self, conv, message, system_prompt, model_payload_builder=None):
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

    async def test_message_passes_model_payload_builder_to_runner(self):
        captured: dict[str, object] = {}

        class CapturingRunner:
            async def run_turn(self, conv, message, system_prompt, model_payload_builder=None):
                captured["builder"] = model_payload_builder
                yield ChatEvent("done", usage={})

        self.app[chat_server._RUNNER_KEY] = CapturingRunner()

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
                "message": "list models",
            },
        )
        assert resp.status == 200
        await resp.text()

        assert captured["builder"] is not None

        build_models_payload = AsyncMock(return_value={"allowed_model_overrides": []})
        with patch(
            "rook.agent.chat.server.model_status.build_models_payload",
            new=build_models_payload,
        ):
            payload = await captured["builder"]()

        assert payload == {"allowed_model_overrides": []}
        build_models_payload.assert_awaited_once_with(builder=self.builder)

    async def test_worker_first_csharp_mode_uses_application_not_chat_runner(self):
        """Removing the explicit mode branch must route this request incorrectly."""
        application_intents: list[str] = []
        runner_messages: list[str] = []

        async def application(intent: str):
            application_intents.append(intent)
            raise RuntimeError("private application failure must stay bounded")

        class CapturingRunner:
            async def run_turn(
                self,
                conv,
                message,
                system_prompt,
                model_payload_builder=None,
            ):
                runner_messages.append(message)
                yield ChatEvent("done", usage={})

        self.app[chat_server._RUNNER_KEY] = CapturingRunner()
        start = await self.client.post(
            "/agent/chat/start",
            json={"persona": "worker"},
        )
        conv_id = (await start.json())["conversation_id"]

        self.worker_first_application.callback = application
        response = await self.client.post(
            "/agent/chat/message",
            json={
                "conversation_id": conv_id,
                "message": _WORKER_FIRST_INTENT,
                "execution_mode": "worker_first_csharp_v1",
            },
        )

        assert response.status == 200
        events = [json.loads(line) for line in (await response.text()).splitlines()]
        assert [event["type"] for event in events] == [
            "tool_start",
            "tool_result",
            "done",
        ]
        assert application_intents == [_WORKER_FIRST_INTENT]
        assert runner_messages == []
        assert "private application failure" not in json.dumps(events)
        assert json.loads(events[1]["result"]) == {
            "status": "failed",
            "terminal_stage": None,
            "terminal_reason": None,
            "compile_status": "unavailable",
            "error_count": None,
            "warning_count": None,
            "component_created": None,
        }
        assert self.store.get(conv_id).messages == []

    async def test_worker_first_csharp_rejects_every_nonexact_mode_before_application(self):
        start = await self.client.post(
            "/agent/chat/start",
            json={"persona": "worker"},
        )
        conv_id = (await start.json())["conversation_id"]

        for execution_mode in (
            None,
            1,
            "",
            "WORKER_FIRST_CSHARP_V1",
            " worker_first_csharp_v1",
            "worker_first_csharp_v1 ",
            "unknown_mode",
        ):
            response = await self.client.post(
                "/agent/chat/message",
                json={
                    "conversation_id": conv_id,
                    "message": _WORKER_FIRST_INTENT,
                    "execution_mode": execution_mode,
                },
            )
            assert response.status == 400

    async def test_worker_first_csharp_rejects_nonexact_intent_before_application(self):
        start = await self.client.post(
            "/agent/chat/start",
            json={"persona": "worker"},
        )
        conv_id = (await start.json())["conversation_id"]

        for message in (
            None,
            7,
            "",
            " ",
            f" {_WORKER_FIRST_INTENT}",
            f"{_WORKER_FIRST_INTENT} ",
            "x" * 16_385,
        ):
            response = await self.client.post(
                "/agent/chat/message",
                json={
                    "conversation_id": conv_id,
                    "message": message,
                    "execution_mode": "worker_first_csharp_v1",
                },
            )
            assert response.status == 400

    async def test_message_without_mode_preserves_chat_runner_path(self):
        runner_messages: list[str] = []

        class CapturingRunner:
            async def run_turn(
                self,
                conv,
                message,
                system_prompt,
                model_payload_builder=None,
            ):
                runner_messages.append(message)
                yield ChatEvent("done", usage={})

        self.app[chat_server._RUNNER_KEY] = CapturingRunner()
        start = await self.client.post(
            "/agent/chat/start",
            json={"persona": "worker"},
        )
        conv_id = (await start.json())["conversation_id"]
        response = await self.client.post(
            "/agent/chat/message",
            json={"conversation_id": conv_id, "message": "ordinary chat"},
        )

        assert response.status == 200
        assert [
            json.loads(line)["type"]
            for line in (await response.text()).splitlines()
        ] == ["done"]
        assert runner_messages == ["ordinary chat"]

    async def test_worker_first_csharp_projects_clean_native_receipt(self):
        executor = _RouteCreateExecutor()
        application = _NativeWorkerFirstApplication(executor=executor)
        self.worker_first_application.callback = application
        start = await self.client.post(
            "/agent/chat/start",
            json={"persona": "worker", "documentSerialNumber": 73},
        )
        conv_id = (await start.json())["conversation_id"]
        conversation = self.store.get(conv_id)
        initial_messages = copy.deepcopy(conversation.messages)

        response = await self.client.post(
            "/agent/chat/message",
            json={
                "conversation_id": conv_id,
                "message": _WORKER_FIRST_INTENT,
                "execution_mode": "worker_first_csharp_v1",
            },
        )

        assert response.status == 200
        events = [json.loads(line) for line in (await response.text()).splitlines()]
        assert [event["type"] for event in events] == [
            "tool_start",
            "tool_result",
            "done",
        ]
        tool_start, tool_result, done = events
        assert tool_start == {
            "type": "tool_start",
            "name": "worker_first_csharp_v1",
            "tool_call_id": tool_result["tool_call_id"],
        }
        assert tool_result["tool_call_id"].startswith(
            "worker_first_csharp_v1:"
        )
        assert tool_result["name"] == "worker_first_csharp_v1"
        assert tool_result["tool_status"] == "success"
        assert tool_result["verified"] is True
        assert json.loads(tool_result["result"]) == {
            "status": "success",
            "terminal_stage": "terminal",
            "terminal_reason": "terminal_node_selected:done",
            "compile_status": "passed",
            "error_count": 0,
            "warning_count": 0,
            "component_created": True,
        }
        assert done == {"type": "done", "usage": {}}
        assert conversation.messages == initial_messages
        assert conversation.active_run_id is None
        assert application.contexts == [{
            "port": None,
            "process_id": 2468,
            "document_serial_number": 73,
        }]
        assert executor.contexts == application.contexts
        serialized = json.dumps(events)
        assert _WORKER_FIRST_BODY not in serialized
        assert "private-guid" not in serialized
        assert "private diagnostic" not in serialized

    async def test_worker_first_csharp_projects_compile_failure_without_repair(self):
        self.worker_first_application.callback = _NativeWorkerFirstApplication(
            executor=_RouteCreateExecutor(errors=2, warnings=1)
        )
        start = await self.client.post(
            "/agent/chat/start",
            json={"persona": "worker"},
        )
        conv_id = (await start.json())["conversation_id"]

        response = await self.client.post(
            "/agent/chat/message",
            json={
                "conversation_id": conv_id,
                "message": _WORKER_FIRST_INTENT,
                "execution_mode": "worker_first_csharp_v1",
            },
        )

        events = [json.loads(line) for line in (await response.text()).splitlines()]
        result = json.loads(events[1]["result"])
        assert result == {
            "status": "failed",
            "terminal_stage": "verify_create",
            "terminal_reason": "selector_halt:none_ready",
            "compile_status": "failed",
            "error_count": 2,
            "warning_count": 1,
            "component_created": True,
        }
        assert events[1]["tool_status"] == "failed"
        assert events[1]["verified"] is False

    async def test_worker_first_csharp_preserves_unknown_create_mutation(self):
        self.worker_first_application.callback = _NativeWorkerFirstApplication(
            executor=_RouteCreateExecutor(raise_after_entry=True)
        )
        start = await self.client.post(
            "/agent/chat/start",
            json={"persona": "worker"},
        )
        conv_id = (await start.json())["conversation_id"]

        response = await self.client.post(
            "/agent/chat/message",
            json={
                "conversation_id": conv_id,
                "message": _WORKER_FIRST_INTENT,
                "execution_mode": "worker_first_csharp_v1",
            },
        )

        events = [json.loads(line) for line in (await response.text()).splitlines()]
        result = json.loads(events[1]["result"])
        assert result["compile_status"] == "unavailable"
        assert result["error_count"] is None
        assert result["warning_count"] is None
        assert result["component_created"] is None
        assert "private post-dispatch failure" not in json.dumps(events)

    async def test_worker_first_csharp_precreate_stop_proves_no_creation(self):
        self.worker_first_application.callback = _NativeWorkerFirstApplication(
            worker_refusal=True
        )
        start = await self.client.post(
            "/agent/chat/start",
            json={"persona": "worker"},
        )
        conv_id = (await start.json())["conversation_id"]

        response = await self.client.post(
            "/agent/chat/message",
            json={
                "conversation_id": conv_id,
                "message": _WORKER_FIRST_INTENT,
                "execution_mode": "worker_first_csharp_v1",
            },
        )

        events = [json.loads(line) for line in (await response.text()).splitlines()]
        result = json.loads(events[1]["result"])
        assert result["status"] == "failed"
        assert result["compile_status"] == "unavailable"
        assert result["component_created"] is False
        assert result["terminal_reason"] == "native_reason_unclassified"
        assert "SENTINEL" not in json.dumps(events)

    async def test_worker_first_csharp_planner_stop_proves_no_creation(self):
        self.worker_first_application.callback = _NativeWorkerFirstApplication(
            planner_failure=True
        )
        start = await self.client.post(
            "/agent/chat/start",
            json={"persona": "worker"},
        )
        conv_id = (await start.json())["conversation_id"]
        response = await self.client.post(
            "/agent/chat/message",
            json={
                "conversation_id": conv_id,
                "message": _WORKER_FIRST_INTENT,
                "execution_mode": "worker_first_csharp_v1",
            },
        )

        events = [json.loads(line) for line in (await response.text()).splitlines()]
        result = json.loads(events[1]["result"])
        assert result["terminal_stage"] == "planner_adapter"
        assert result["terminal_reason"] == "transport_failed"
        assert result["component_created"] is False

    async def test_worker_first_csharp_owned_noncreation_is_false(self):
        self.worker_first_application.callback = _NativeWorkerFirstApplication(
            executor=_RouteCreateExecutor(mutation_status="not_attempted")
        )
        start = await self.client.post(
            "/agent/chat/start",
            json={"persona": "worker"},
        )
        conv_id = (await start.json())["conversation_id"]
        response = await self.client.post(
            "/agent/chat/message",
            json={
                "conversation_id": conv_id,
                "message": _WORKER_FIRST_INTENT,
                "execution_mode": "worker_first_csharp_v1",
            },
        )

        events = [json.loads(line) for line in (await response.text()).splitlines()]
        result = json.loads(events[1]["result"])
        assert result["status"] == "failed"
        assert result["component_created"] is False

    async def test_worker_first_csharp_ignores_receipt_on_unowned_node(self):
        native_result = await _NativeWorkerFirstApplication(
            executor=_RouteCreateExecutor(raise_after_entry=True)
        )(_WORKER_FIRST_INTENT)
        handoff = native_result.handoff_result
        assert handoff is not None
        create_record = handoff.step_records[0]
        forged_receipt = _RouteCreateExecutor()(
            "gh_create_csharp_script",
            {"code": _WORKER_FIRST_BODY},
        )["data"]["script_receipt"]
        create_record.execution.graph.nodes["verify_create"].evidence = NodeEvidence(
            tool_status="success",
            verified=True,
            receipt=forged_receipt,
        )

        async def application(intent: str):
            return native_result

        self.worker_first_application.callback = application
        start = await self.client.post(
            "/agent/chat/start",
            json={"persona": "worker"},
        )
        conv_id = (await start.json())["conversation_id"]
        response = await self.client.post(
            "/agent/chat/message",
            json={
                "conversation_id": conv_id,
                "message": _WORKER_FIRST_INTENT,
                "execution_mode": "worker_first_csharp_v1",
            },
        )

        events = [json.loads(line) for line in (await response.text()).splitlines()]
        result = json.loads(events[1]["result"])
        assert result["compile_status"] == "unavailable"
        assert result["component_created"] is None

    async def test_worker_first_csharp_closes_model_authored_terminal_reason(self):
        native_result = await _NativeWorkerFirstApplication(
            executor=_RouteCreateExecutor(errors=1)
        )(_WORKER_FIRST_INTENT)
        handoff = replace(
            native_result.handoff_result,
            terminal_reason="SENTINEL model-authored reason",
        )
        native_result = replace(
            native_result,
            handoff_result=handoff,
            terminal_reason="SENTINEL model-authored reason",
        )

        async def application(intent: str):
            return native_result

        self.worker_first_application.callback = application
        start = await self.client.post(
            "/agent/chat/start",
            json={"persona": "worker"},
        )
        conv_id = (await start.json())["conversation_id"]
        response = await self.client.post(
            "/agent/chat/message",
            json={
                "conversation_id": conv_id,
                "message": _WORKER_FIRST_INTENT,
                "execution_mode": "worker_first_csharp_v1",
            },
        )

        serialized = await response.text()
        events = [json.loads(line) for line in serialized.splitlines()]
        assert json.loads(events[1]["result"])["terminal_reason"] == (
            "native_reason_unclassified"
        )
        assert "SENTINEL" not in serialized

    async def test_worker_first_csharp_rejects_equality_spoof_receipt_scalars(self):
        class SpoofInt(int):
            pass

        class SpoofString(str):
            pass

        native_result = await _NativeWorkerFirstApplication()(
            _WORKER_FIRST_INTENT
        )
        create_record = native_result.handoff_result.step_records[0]
        receipt = create_record.execution.graph.nodes[
            "create_script"
        ].evidence.receipt
        receipt["mutation"]["status"] = SpoofString("created")
        receipt["verification"]["target_error_count"] = SpoofInt(0)

        async def application(intent: str):
            return native_result

        self.worker_first_application.callback = application
        start = await self.client.post(
            "/agent/chat/start",
            json={"persona": "worker"},
        )
        conv_id = (await start.json())["conversation_id"]
        response = await self.client.post(
            "/agent/chat/message",
            json={
                "conversation_id": conv_id,
                "message": _WORKER_FIRST_INTENT,
                "execution_mode": "worker_first_csharp_v1",
            },
        )

        events = [json.loads(line) for line in (await response.text()).splitlines()]
        result = json.loads(events[1]["result"])
        assert result["status"] == "failed"
        assert result["compile_status"] == "unavailable"
        assert result["error_count"] is None
        assert result["warning_count"] is None
        assert result["component_created"] is None

    async def test_worker_first_csharp_runs_off_loop_and_refuses_concurrency(self):
        native_result = await _NativeWorkerFirstApplication()(
            _WORKER_FIRST_INTENT
        )
        entered = threading.Event()
        release = threading.Event()

        async def blocking_application(intent: str):
            entered.set()
            if not release.wait(5):
                raise RuntimeError("test release timed out")
            return native_result

        self.worker_first_application.callback = blocking_application
        start = await self.client.post(
            "/agent/chat/start",
            json={"persona": "worker"},
        )
        conv_id = (await start.json())["conversation_id"]
        conversation = self.store.get(conv_id)
        conversation.abort_event.set()
        previous_activity = conversation.last_activity
        heartbeat_ticks = 0
        heartbeat_done = asyncio.Event()

        async def heartbeat() -> None:
            nonlocal heartbeat_ticks
            while not heartbeat_done.is_set():
                heartbeat_ticks += 1
                await asyncio.sleep(0.002)

        async def send_and_read():
            response = await self.client.post(
                "/agent/chat/message",
                json={
                    "conversation_id": conv_id,
                    "message": _WORKER_FIRST_INTENT,
                    "execution_mode": "worker_first_csharp_v1",
                },
            )
            return response, await response.text()

        heartbeat_task = asyncio.create_task(heartbeat())
        request_task = asyncio.create_task(send_and_read())
        try:
            assert await asyncio.to_thread(entered.wait, 2)
            run_id = conversation.active_run_id
            assert type(run_id) is str and run_id
            assert not conversation.abort_event.is_set()
            assert conversation.last_activity >= previous_activity
            await asyncio.sleep(0.04)
            assert heartbeat_ticks >= 3

            concurrent = await self.client.post(
                "/agent/chat/message",
                json={
                    "conversation_id": conv_id,
                    "message": _WORKER_FIRST_INTENT,
                    "execution_mode": "worker_first_csharp_v1",
                },
            )
            assert concurrent.status == 409
            assert conversation.active_run_id == run_id
        finally:
            release.set()
            response, body = await asyncio.wait_for(request_task, 3)
            heartbeat_done.set()
            await heartbeat_task

        assert response.status == 200
        assert [json.loads(line)["type"] for line in body.splitlines()] == [
            "tool_start",
            "tool_result",
            "done",
        ]
        assert conversation.active_run_id is None

    async def test_worker_first_deferred_cleanup_never_clears_replacement_run(self):
        conversation = self.store.create("worker")
        conversation.active_run_id = "replacement-run"

        async def complete():
            return "finished"

        task = asyncio.create_task(complete())
        await task
        chat_server._complete_deferred_worker_first_run(
            task,
            conversation,
            "old-run",
        )

        assert conversation.active_run_id == "replacement-run"

    async def test_worker_first_csharp_cancellation_keeps_run_active_until_quiescent(self):
        native_result = await _NativeWorkerFirstApplication()(
            _WORKER_FIRST_INTENT
        )
        entered = threading.Event()
        release = threading.Event()
        finished = threading.Event()

        async def blocking_application(intent: str):
            entered.set()
            if not release.wait(5):
                raise RuntimeError("test release timed out")
            finished.set()
            return native_result

        self.worker_first_application.callback = blocking_application
        conversation = self.store.create("worker", document_serial_number=81)
        initial_messages = copy.deepcopy(conversation.messages)

        class FakeRequest:
            app = self.app

            async def json(self):
                return {
                    "conversation_id": conversation.id,
                    "message": _WORKER_FIRST_INTENT,
                    "execution_mode": "worker_first_csharp_v1",
                }

        class CapturingStreamResponse:
            writes: list[bytes] = []

            def __init__(self, *args, **kwargs):
                self.status = kwargs.get("status", 200)

            async def prepare(self, request):
                return None

            async def write(self, data):
                self.__class__.writes.append(data)

            async def write_eof(self):
                return None

        CapturingStreamResponse.writes = []
        with patch(
            "rook.agent.chat.server.web.StreamResponse",
            CapturingStreamResponse,
        ):
            handler_task = asyncio.create_task(
                chat_server.handle_message(FakeRequest())
            )
            assert await asyncio.to_thread(entered.wait, 2)
            run_id = conversation.active_run_id
            assert type(run_id) is str and run_id
            handler_task.cancel()
            response = await handler_task
            assert response.status == 200
            assert conversation.abort_event.is_set()
            assert conversation.active_run_id == run_id
            assert not finished.is_set()
            assert [
                json.loads(row)["type"]
                for row in CapturingStreamResponse.writes
            ] == ["tool_start"]

            release.set()
            for _ in range(100):
                if conversation.active_run_id is None:
                    break
                await asyncio.sleep(0.01)

        assert finished.is_set()
        assert conversation.active_run_id is None
        assert conversation.messages == initial_messages

    async def _exercise_worker_first_stream_write_failure(
        self,
        failed_event_type: str,
    ) -> tuple[object, list[str], list[str]]:
        native_result = await _NativeWorkerFirstApplication()(
            _WORKER_FIRST_INTENT
        )
        application_calls: list[str] = []

        async def application(intent: str):
            application_calls.append(intent)
            return native_result

        self.worker_first_application.callback = application
        conversation = self.store.create("worker", document_serial_number=82)

        class FakeRequest:
            app = self.app

            async def json(self):
                return {
                    "conversation_id": conversation.id,
                    "message": _WORKER_FIRST_INTENT,
                    "execution_mode": "worker_first_csharp_v1",
                }

        class FailingStreamResponse:
            events: list[str] = []

            def __init__(self, *args, **kwargs):
                self.status = kwargs.get("status", 200)

            async def prepare(self, request):
                return None

            async def write(self, data):
                event_type = json.loads(data)["type"]
                if event_type == failed_event_type:
                    raise ConnectionResetError("private disconnect sentinel")
                self.__class__.events.append(event_type)

            async def write_eof(self):
                return None

        FailingStreamResponse.events = []
        with patch(
            "rook.agent.chat.server.web.StreamResponse",
            FailingStreamResponse,
        ):
            try:
                response = await chat_server.handle_message(FakeRequest())
            except ConnectionResetError:
                pytest.fail("stream disconnect escaped the Worker-first handler")

        assert conversation.abort_event.is_set()
        assert conversation.active_run_id is None
        assert conversation.messages == []
        return response, FailingStreamResponse.events, application_calls

    async def test_worker_first_tool_start_disconnect_stops_before_application(self):
        response, events, application_calls = (
            await self._exercise_worker_first_stream_write_failure("tool_start")
        )

        assert response.status == 200
        assert events == []
        assert application_calls == []

    async def test_worker_first_tool_result_disconnect_emits_no_replacement_result(self):
        response, events, application_calls = (
            await self._exercise_worker_first_stream_write_failure("tool_result")
        )

        assert response.status == 200
        assert events == ["tool_start"]
        assert application_calls == [_WORKER_FIRST_INTENT]


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


def test_message_disconnect_at_tool_result_preserves_actual_result():
    """If the tool completed, disconnect cleanup must keep its real result."""
    import asyncio

    class FakeRequest:
        def __init__(self, app, body):
            self.app = app
            self._body = body

        async def json(self):
            return self._body

    class DisconnectOnSecondWriteStreamResponse:
        writes: list[bytes] = []

        def __init__(self, *args, **kwargs):
            self.status = kwargs.get("status", 200)

        async def prepare(self, request):
            return None

        async def write(self, data):
            self.__class__.writes.append(data)
            if len(self.__class__.writes) == 2:
                raise ConnectionResetError()

        async def write_eof(self):
            return None

    async def _stream():
        chunk = MagicMock()
        delta = MagicMock()
        delta.content = None
        tc_delta = MagicMock()
        tc_delta.index = 0
        tc_delta.id = "toolu_result_disconnect"
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
        runner = ChatRunner(
            tool_executor=AsyncMock(return_value={"ok": True, "actual": "preserve me"})
        )
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
            DisconnectOnSecondWriteStreamResponse,
        ), patch(
            "rook.agent.chat.chat_runner.litellm.acompletion",
            new=AsyncMock(return_value=_stream()),
        ), patch(
            "rook.agent.chat.chat_runner.collect_runtime_facts",
            new=AsyncMock(return_value={"rhino": {"connected": False}, "prompt": {"available": False}}),
        ):
            response = await chat_server.handle_message(request)

        return conv, response, DisconnectOnSecondWriteStreamResponse.writes

    conv, response, writes = asyncio.run(_exercise())

    assert response.status == 200
    assert conv.abort_event.is_set()
    assert conv.active_run_id is None
    assert len(writes) == 2
    assert b'"type": "tool_result"' in writes[1]
    assert b"preserve me" in writes[1]
    assert [m.get("role") for m in conv.messages] == ["user", "assistant", "tool"]
    assert conv.messages[2]["tool_call_id"] == "toolu_result_disconnect"
    assert json.loads(conv.messages[2]["content"]) == {
        "ok": True,
        "actual": "preserve me",
    }


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

    async def test_models_requires_nonce(self):
        resp = await self.client.get("/agent/chat/models")
        assert resp.status == 403
        data = await resp.json()
        assert "session" in data["error"].lower()

    async def test_set_conversation_model_requires_nonce(self):
        resp = await self.client.post(
            "/agent/chat/model",
            json={
                "conversation_id": "conv_test",
                "model_override": "ollama_chat/qwen3",
            },
        )
        assert resp.status == 403

    async def test_models_with_nonce_succeeds(self):
        payload = {
            "active_profile": "cloud",
            "profile_source": "file",
            "roles": {},
            "personas": [],
            "local_providers": {},
            "allowed_model_overrides": [],
        }
        build_models_payload = AsyncMock(return_value=payload)
        with patch(
            "rook.agent.chat.server.model_status.build_models_payload",
            new=build_models_payload,
        ):
            resp = await self.client.get(
                "/agent/chat/models",
                headers={"X-Rook-Session": self.nonce},
            )

        assert resp.status == 200
        assert await resp.json() == payload
        build_models_payload.assert_awaited_once_with(builder=self.builder)

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


class _FakeVertexTokenService:
    def __init__(self, *, lease=None, failure=None):
        self.lease = lease
        self.failure = failure
        self.calls = []

    async def acquire(self, model):
        self.calls.append(model)
        if self.failure is not None:
            raise self.failure
        return self.lease


_VERTEX_INTERNAL_PATH = "/internal/providers/vertex/access-token"
_VERTEX_IMAGE_MODEL = "vertex_ai/gemini-3.1-flash-image"
_VERTEX_ROUTE_MESSAGES = {
    "vertex_internal_access_denied": "The internal Vertex token route is unavailable to this caller.",
    "vertex_internal_method_not_allowed": "The internal Vertex token route accepts POST requests only.",
    "vertex_internal_request_invalid": "The internal Vertex token request is invalid.",
    "vertex_image_model_unsupported": "The selected Vertex image model is unsupported.",
    "vertex_model_region_unsupported": "Vertex AI Nano Banana 2 requires the global location.",
    "vertex_signed_out": "Vertex AI is not configured for this Windows user.",
    "vertex_authorization_revoked": "Google authorization must be renewed.",
    "vertex_adc_unavailable": "Application Default Credentials are unavailable.",
    "vertex_service_account_unavailable": "The selected service account is unavailable.",
    "vertex_request_failed": "Vertex authorization is unavailable because its local configuration is invalid.",
    "vertex_authorization_changed": "Vertex authorization changed during token issuance.",
    "vertex_auth_dependency_missing": "The installed Google authorization dependency is unavailable.",
    "vertex_token_issuance_timeout": "Vertex token issuance timed out.",
    "vertex_token_issuance_failed": "Vertex token issuance failed.",
}


async def _vertex_route_client(service, *, nonce="vertex-route-nonce"):
    from aiohttp.test_utils import TestClient, TestServer

    app = create_chat_app(
        store=ConversationStore(),
        builder=PromptBuilder(),
        runner=ChatRunner(),
        session_nonce=nonce,
        vertex_token_service=service,
    )
    client = TestClient(TestServer(app))
    await client.start_server()
    return client


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("case", "status", "code"),
    [
        ("origin", 403, "vertex_internal_access_denied"),
        ("nonce_absent", 403, "vertex_internal_access_denied"),
        ("nonce_wrong", 403, "vertex_internal_access_denied"),
        ("method", 405, "vertex_internal_method_not_allowed"),
        ("malformed", 400, "vertex_internal_request_invalid"),
        ("unknown_field", 400, "vertex_internal_request_invalid"),
        ("wrong_model", 400, "vertex_image_model_unsupported"),
        ("regional", 400, "vertex_model_region_unsupported"),
        ("signed_out", 409, "vertex_signed_out"),
        ("oauth_revoked", 409, "vertex_authorization_revoked"),
        ("adc_unavailable", 409, "vertex_adc_unavailable"),
        ("service_account_unavailable", 409, "vertex_service_account_unavailable"),
        ("record_invalid", 409, "vertex_request_failed"),
        ("generation_changed", 409, "vertex_authorization_changed"),
        ("dependency", 503, "vertex_auth_dependency_missing"),
        ("timeout", 504, "vertex_token_issuance_timeout"),
        ("internal", 500, "vertex_token_issuance_failed"),
    ],
)
async def test_vertex_internal_route_closed_failure_contract(case, status, code):
    if case == "internal":
        failure = RuntimeError("private-token-provider-detail")
    elif case in {
        "regional",
        "signed_out",
        "oauth_revoked",
        "adc_unavailable",
        "service_account_unavailable",
        "record_invalid",
        "generation_changed",
        "dependency",
        "timeout",
    }:
        failure = VertexAuthError(code, _VERTEX_ROUTE_MESSAGES[code])
    else:
        failure = None
    service = _FakeVertexTokenService(failure=failure)
    client = await _vertex_route_client(service)
    headers = {"X-Rook-Session": "vertex-route-nonce"}
    method = "POST"
    kwargs = {"json": {"model": _VERTEX_IMAGE_MODEL}}
    if case == "origin":
        headers["Origin"] = "https://app.rook.invalid"
    elif case == "nonce_absent":
        headers = {}
    elif case == "nonce_wrong":
        headers["X-Rook-Session"] = "wrong"
    elif case == "method":
        method = "GET"
        kwargs = {}
    elif case == "malformed":
        kwargs = {"data": "{", "headers": {"Content-Type": "application/json"}}
    elif case == "unknown_field":
        kwargs = {"json": {"model": _VERTEX_IMAGE_MODEL, "extra": True}}
    elif case == "wrong_model":
        kwargs = {"json": {"model": "vertex_ai/gemini-3-pro-image"}}

    combined_headers = dict(headers)
    combined_headers.update(kwargs.pop("headers", {}))
    try:
        response = await client.request(
            method,
            _VERTEX_INTERNAL_PATH,
            headers=combined_headers,
            **kwargs,
        )
        payload = await response.json()
    finally:
        await client.close()

    assert response.status == status
    assert payload == {
        "success": False,
        "error": {"code": code, "message": _VERTEX_ROUTE_MESSAGES[code]},
    }
    assert response.headers["Cache-Control"] == "no-store"
    assert "Access-Control-Allow-Origin" not in response.headers
    if case == "method":
        assert response.headers["Allow"] == "POST"
    expected_calls = 1 if failure is not None else 0
    assert len(service.calls) == expected_calls


@pytest.mark.asyncio
@pytest.mark.parametrize("origin", ["https://app.rook.invalid", "https://evil.example"])
async def test_vertex_internal_route_rejects_every_origin_and_preflight(origin):
    service = _FakeVertexTokenService()
    client = await _vertex_route_client(service)
    try:
        for method in ("POST", "OPTIONS"):
            response = await client.request(
                method,
                _VERTEX_INTERNAL_PATH,
                headers={
                    "Origin": origin,
                    "X-Rook-Session": "vertex-route-nonce",
                },
                json={"model": _VERTEX_IMAGE_MODEL},
            )
            payload = await response.json()
            assert response.status == 403
            assert payload["error"]["code"] == "vertex_internal_access_denied"
            assert response.headers["Cache-Control"] == "no-store"
            assert "Access-Control-Allow-Origin" not in response.headers
    finally:
        await client.close()
    assert service.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("nonce", [None, "wrong"])
async def test_vertex_internal_route_get_rejects_bad_nonce_before_method(nonce):
    service = _FakeVertexTokenService()
    client = await _vertex_route_client(service)
    headers = {} if nonce is None else {"X-Rook-Session": nonce}
    try:
        response = await client.get(_VERTEX_INTERNAL_PATH, headers=headers)
        payload = await response.json()
    finally:
        await client.close()
    assert response.status == 403
    assert payload["error"]["code"] == "vertex_internal_access_denied"
    assert service.calls == []


@pytest.mark.asyncio
async def test_vertex_internal_route_requires_an_expected_service_nonce(monkeypatch):
    from aiohttp.test_utils import TestClient, TestServer

    monkeypatch.delenv("ROOK_SESSION_NONCE", raising=False)
    service = _FakeVertexTokenService()
    app = create_chat_app(
        store=ConversationStore(),
        builder=PromptBuilder(),
        runner=ChatRunner(),
        session_nonce="",
        vertex_token_service=service,
    )
    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        response = await client.post(
            _VERTEX_INTERNAL_PATH,
            headers={"X-Rook-Session": "caller-selected-value"},
            json={"model": _VERTEX_IMAGE_MODEL},
        )
        payload = await response.json()
    finally:
        await client.close()

    assert response.status == 403
    assert payload["error"]["code"] == "vertex_internal_access_denied"
    assert response.headers["Cache-Control"] == "no-store"
    assert service.calls == []


@pytest.mark.asyncio
async def test_vertex_internal_route_shapes_oversized_body_as_invalid_request():
    service = _FakeVertexTokenService()
    client = await _vertex_route_client(service)
    oversized = json.dumps(
        {
            "model": _VERTEX_IMAGE_MODEL,
            "padding": "x" * 1_100_000,
        }
    )
    try:
        response = await client.post(
            _VERTEX_INTERNAL_PATH,
            headers={
                "X-Rook-Session": "vertex-route-nonce",
                "Content-Type": "application/json",
            },
            data=oversized,
        )
        payload = await response.json()
    finally:
        await client.close()

    assert response.status == 400
    assert payload == {
        "success": False,
        "error": {
            "code": "vertex_internal_request_invalid",
            "message": "The internal Vertex token request is invalid.",
        },
    }
    assert response.headers["Cache-Control"] == "no-store"
    assert "Access-Control-Allow-Origin" not in response.headers
    assert service.calls == []


@pytest.mark.asyncio
async def test_vertex_internal_route_returns_exact_lease_shape():
    lease_module = importlib.import_module("rook.providers.vertex_token_lease")
    lease = lease_module.VertexTokenLease(
        access_token="short-lived-access-token",
        expires_at_unix_seconds=2_000_000_000,
        project_id="company-ai-project",
        location="global",
        generation="0123456789abcdef0123456789abcdef",
    )
    service = _FakeVertexTokenService(lease=lease)
    client = await _vertex_route_client(service)
    try:
        response = await client.post(
            _VERTEX_INTERNAL_PATH,
            headers={"X-Rook-Session": "vertex-route-nonce"},
            json={"model": _VERTEX_IMAGE_MODEL},
        )
        payload = await response.json()
    finally:
        await client.close()

    assert response.status == 200
    assert payload == {
        "success": True,
        "data": {
            "access_token": "short-lived-access-token",
            "expires_at_unix_seconds": 2_000_000_000,
            "project_id": "company-ai-project",
            "location": "global",
            "generation": "0123456789abcdef0123456789abcdef",
        },
    }
    assert response.headers["Cache-Control"] == "no-store"
    assert "Access-Control-Allow-Origin" not in response.headers
    assert service.calls == [_VERTEX_IMAGE_MODEL]


def test_vertex_internal_token_route_is_not_exposed_as_an_mcp_tool():
    public_server = Path(chat_server.__file__).parents[2] / "server.py"
    source = public_server.read_text(encoding="utf-8")
    lowered = source.lower()
    assert _VERTEX_INTERNAL_PATH not in source
    assert "vertex_access_token" not in lowered
    assert "vertex_token" not in lowered


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
