"""Tests for the agent chat HTTP server."""
import asyncio
import copy
import json
import socket
import sys
import threading
from pathlib import Path
from dataclasses import replace
from typing import Any

import pytest
import httpx
from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, TestClient, TestServer
from unittest.mock import AsyncMock, MagicMock, patch
from rook.agent.chat import server as chat_server
from rook.agent.chat import service_main as chat_service_main
from rook.agent.chat import model_status
from rook.agent.chat.server import create_chat_app
from rook.agent.chat.conversation_store import ConversationStore
from rook.agent.chat.prompt_builder import PromptBuilder
from rook.agent.chat.chat_runner import ChatRunner, ChatEvent
from rook.agent.chat.prime_backend import PrimeBackendError, PrimeChatBackend
from rook.agent.chat.prime_process import PrimeRpcProcess
from rook.agent.chat.prime_registry import (
    LifecycleRecord,
    PrimeConversationRecord,
    PrimeConversationRegistry,
    PrimeModelSelection,
    TargetFingerprint,
)
from rook.agent.minimal_intent_worker_integration import (
    MinimalPlannerDraftAdapter,
    run_minimal_intent_worker_initial_body_integration,
)
from rook.learning.plan_graph import NodeEvidence
from rook import bridge


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
            assert "backend" not in (await resp.json())["service"]

    async def test_authenticated_health_reports_legacy_backend(self):
        with patch(
            "rook.agent.chat.server.collect_runtime_facts",
            new=AsyncMock(return_value={"rhino": {"connected": True}}),
        ):
            resp = await self.client.get(
                "/agent/chat/health",
                headers={"X-Rook-Session": self.nonce},
            )
        assert resp.status == 200
        assert (await resp.json())["service"]["backend"] == "legacy"

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


class _ExplodingLegacyRunner:
    def __init__(self) -> None:
        self.calls = 0

    def run_turn(self, *_args, **_kwargs):
        self.calls += 1
        raise AssertionError("legacy ChatRunner must not run in Prime mode")


class _FakePrimeSubscription:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = list(rows)
        self.closed = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._rows:
            raise StopAsyncIteration
        return self._rows.pop(0)

    async def close(self) -> None:
        self.closed = True


class _FakePrimeRegistry:
    def __init__(self, backend: "_FakePrimeBackend") -> None:
        self.backend = backend

    def load(self, conversation_id: str) -> PrimeConversationRecord:
        try:
            return self.backend.records[conversation_id]
        except KeyError as error:
            raise PrimeBackendError("conversation_not_found") from error


class _FakePrimeBackend:
    def __init__(self) -> None:
        self.records: dict[str, PrimeConversationRecord] = {}
        self.registry = _FakePrimeRegistry(self)
        self.calls: list[tuple[str, Any]] = []
        self.shutdown_calls = 0
        self.subscription: _FakePrimeSubscription | None = None
        self.model_error: PrimeBackendError | None = None
        self.next_rows: list[dict[str, Any]] | None = None

    @staticmethod
    def _record(
        conversation_id: str,
        target: TargetFingerprint,
        *,
        lifecycle: str = "idle",
    ) -> PrimeConversationRecord:
        return PrimeConversationRecord(
            schema_version=1,
            conversation_id=conversation_id,
            prime_session_id=f"session-{conversation_id}",
            prime_session_path=f"C:/prime-sessions/{conversation_id}.jsonl",
            model=PrimeModelSelection("openai-codex", "gpt-5.6-sol", "xhigh"),
            target=target,
            last_lifecycle=LifecycleRecord(
                state=lifecycle,
                reason=None,
                updated_at_utc="2026-08-27T12:00:00Z",
            ),
        )

    async def create(
        self, conversation_id: str, target: TargetFingerprint
    ) -> PrimeConversationRecord:
        self.calls.append(("create", conversation_id, target))
        record = self._record(conversation_id, target)
        self.records[conversation_id] = record
        return record

    async def reopen(
        self, conversation_id: str, target: TargetFingerprint
    ) -> PrimeConversationRecord:
        self.calls.append(("reopen", conversation_id, target))
        record = self.records.get(conversation_id)
        if record is None:
            raise PrimeBackendError("conversation_not_found")
        if record.target != target:
            raise PrimeBackendError("target_mismatch")
        return record

    async def start_prompt(
        self, conversation_id: str, message: str
    ) -> _FakePrimeSubscription:
        self.calls.append(("message", conversation_id, message))
        self.subscription = _FakePrimeSubscription(
            self.next_rows
            or [
                    {"type": "text_delta", "content": "hello"},
                    {"type": "status", "status": "agent_segment"},
                    {"type": "done", "reason": "completed"},
                ]
        )
        return self.subscription

    async def cancel(self, conversation_id: str) -> LifecycleRecord:
        self.calls.append(("cancel", conversation_id))
        return LifecycleRecord(
            state="cancel_requested",
            reason=None,
            updated_at_utc="2026-08-27T12:00:01Z",
        )

    async def close(self, conversation_id: str) -> LifecycleRecord:
        self.calls.append(("close", conversation_id))
        return LifecycleRecord(
            state="closed",
            reason="user_closed",
            updated_at_utc="2026-08-27T12:00:02Z",
        )

    async def models(self, conversation_id: str) -> list[dict[str, Any]]:
        self.calls.append(("models", conversation_id))
        return [
            {
                "id": "openai-codex/gpt-5.6-sol",
                "provider": "openai-codex",
                "model": "gpt-5.6-sol",
                "contextWindow": 272000,
                "reasoning": True,
            }
        ]

    async def set_model(
        self,
        conversation_id: str,
        provider: str,
        model_id: str,
        thinking: str | None,
    ) -> PrimeModelSelection:
        self.calls.append(("set_model", conversation_id, provider, model_id, thinking))
        if self.model_error is not None:
            raise self.model_error
        return PrimeModelSelection(provider, model_id, thinking)

    async def shutdown(self) -> None:
        self.shutdown_calls += 1


class TestPrimeChatServer(AioHTTPTestCase):
    conversation_id = "conv_0123456789abcdef0123456789abcdef"
    target_payload = {
        "rhinoPid": 2468,
        "rhinoProcessStartUtcTicks": "638918000000000000",
        "documentRuntimeSerial": 42,
    }

    async def get_application(self):
        self.nonce = "prime-test-nonce"
        self.backend = _FakePrimeBackend()
        return create_chat_app(
            runner=_ExplodingLegacyRunner(),
            backend_mode="prime",
            prime_backend=self.backend,
            rhino_process_id=2468,
            rhino_process_start_utc_ticks="638918000000000000",
            session_nonce=self.nonce,
        )

    def _headers(self) -> dict[str, str]:
        return {"X-Rook-Session": self.nonce}

    async def test_health_advertises_backend_only_to_exact_nonce(self):
        with patch(
            "rook.agent.chat.server.collect_runtime_facts",
            new=AsyncMock(return_value={}),
        ):
            public = await self.client.get("/agent/chat/health")
            wrong = await self.client.get(
                "/agent/chat/health", headers={"X-Rook-Session": "wrong"}
            )
            admitted = await self.client.get(
                "/agent/chat/health", headers=self._headers()
            )

        assert "backend" not in (await public.json())["service"]
        assert "backend" not in (await wrong.json())["service"]
        assert (await admitted.json())["service"]["backend"] == "prime"

    async def test_prime_create_and_reopen_use_closed_target_schema(self):
        create_body = {
            "action": "create",
            "conversation_id": self.conversation_id,
            "target": dict(self.target_payload),
        }
        created = await self.client.post(
            "/agent/chat/start", json=create_body, headers=self._headers()
        )
        reopened = await self.client.post(
            "/agent/chat/start",
            json={**create_body, "action": "reopen"},
            headers=self._headers(),
        )

        assert created.status == 200
        assert reopened.status == 200
        assert (await created.json())["conversation_id"] == self.conversation_id
        assert (await reopened.json())["backend"] == "prime"
        assert [call[0] for call in self.backend.calls] == ["create", "reopen"]

        mixed = await self.client.post(
            "/agent/chat/start",
            json={**create_body, "persona": "worker"},
            headers=self._headers(),
        )
        assert mixed.status == 400
        assert (await mixed.json())["code"] == "invalid_prime_start_request"

    async def test_prime_rejects_wrong_target_before_backend_dispatch(self):
        response = await self.client.post(
            "/agent/chat/start",
            json={
                "action": "create",
                "conversation_id": self.conversation_id,
                "target": {
                    **self.target_payload,
                    "rhinoProcessStartUtcTicks": "638918000000000001",
                },
            },
            headers=self._headers(),
        )

        assert response.status == 409
        assert (await response.json())["code"] == "target_mismatch"
        assert self.backend.calls == []

    async def test_prime_streams_only_broker_rows_and_never_calls_legacy(self):
        await self.backend.create(
            self.conversation_id,
            TargetFingerprint(2468, "638918000000000000", 42),
        )
        response = await self.client.post(
            "/agent/chat/message",
            json={"conversation_id": self.conversation_id, "message": "hello"},
            headers=self._headers(),
        )

        assert response.status == 200
        rows = [json.loads(line) for line in (await response.text()).splitlines()]
        assert rows == [
            {"type": "text_delta", "content": "hello"},
            {"type": "status", "status": "agent_segment"},
            {"type": "done", "reason": "completed"},
        ]
        assert self.backend.subscription is not None
        assert self.backend.subscription.closed is True

    async def test_prime_refuses_unadmitted_slash_command_before_backend(self):
        await self.backend.create(
            self.conversation_id,
            TargetFingerprint(2468, "638918000000000000", 42),
        )
        calls_before = list(self.backend.calls)

        response = await self.client.post(
            "/agent/chat/message",
            json={"conversation_id": self.conversation_id, "message": "/compact"},
            headers=self._headers(),
        )

        assert response.status == 409
        assert (await response.json())["code"] == "prime_command_not_admitted"
        assert self.backend.calls == calls_before

    async def test_prime_forwards_only_correlated_terminal_outcomes(self):
        await self.backend.create(
            self.conversation_id,
            TargetFingerprint(2468, "638918000000000000", 42),
        )
        for expected in (
            {"type": "done", "reason": "completed_before_abort"},
            {"type": "cancelled", "reason": "aborted"},
            {
                "type": "error",
                "code": "settlement_unknown",
                "message": "process lost",
            },
        ):
            self.backend.next_rows = [expected]
            response = await self.client.post(
                "/agent/chat/message",
                json={"conversation_id": self.conversation_id, "message": "hello"},
                headers=self._headers(),
            )
            assert response.status == 200
            assert json.loads((await response.text()).strip()) == expected

    async def test_prime_stream_disconnect_only_unsubscribes(self):
        class DisconnectingResponse:
            def __init__(self, *args, **kwargs):
                self.status = kwargs.get("status", 200)

            async def prepare(self, _request):
                return None

            async def write(self, _data):
                raise ConnectionResetError

            async def write_eof(self):
                return None

        class Request:
            def __init__(self, app):
                self.app = app

            async def json(self):
                return {
                    "conversation_id": TestPrimeChatServer.conversation_id,
                    "message": "hello",
                }

        await self.backend.create(
            self.conversation_id,
            TargetFingerprint(2468, "638918000000000000", 42),
        )
        with patch(
            "rook.agent.chat.server.web.StreamResponse", DisconnectingResponse
        ):
            response = await chat_server.handle_message(Request(self.app))

        assert response.status == 200
        assert self.backend.subscription is not None
        assert self.backend.subscription.closed is True
        assert [call[0] for call in self.backend.calls] == ["create", "message"]
        assert self.backend.records[self.conversation_id].last_lifecycle.state == "idle"

    async def test_prime_stream_prepare_failure_closes_subscription(self):
        class FailingPrepareResponse:
            def __init__(self, *args, **kwargs):
                self.status = kwargs.get("status", 200)

            async def prepare(self, _request):
                raise RuntimeError("prepare failed")

        class Request:
            def __init__(self, app):
                self.app = app

            async def json(self):
                return {
                    "conversation_id": TestPrimeChatServer.conversation_id,
                    "message": "hello",
                }

        await self.backend.create(
            self.conversation_id,
            TargetFingerprint(2468, "638918000000000000", 42),
        )
        with patch("rook.agent.chat.server.web.StreamResponse", FailingPrepareResponse):
            with pytest.raises(RuntimeError, match="prepare failed"):
                await chat_server.handle_message(Request(self.app))

        assert self.backend.subscription is not None
        assert self.backend.subscription.closed is True

    async def test_prime_message_and_stop_reject_non_object_json(self):
        for body in ("null", "[]", '"scalar"', "42"):
            message = await self.client.post(
                "/agent/chat/message",
                data=body,
                headers={**self._headers(), "Content-Type": "application/json"},
            )
            stopped = await self.client.post(
                "/agent/chat/stop",
                data=body,
                headers={**self._headers(), "Content-Type": "application/json"},
            )

            assert message.status == 400
            assert (await message.json())["code"] == "invalid_prime_message_request"
            assert stopped.status == 400
            assert (await stopped.json())["code"] == "invalid_prime_stop_request"

    async def test_prime_routes_reject_noncanonical_conversation_ids_before_backend(self):
        malformed = (None, "", 42, "../conv_escape")

        for conversation_id in malformed:
            query = (
                {}
                if conversation_id is None
                else {"conversation_id": str(conversation_id)}
            )
            models = await self.client.get(
                "/agent/chat/models",
                params=query,
                headers=self._headers(),
            )
            models_payload = await models.json()
            assert models.status == 400
            assert models_payload["code"] in {
                "missing_conversation_id",
                "invalid_prime_model_request",
            }

            model_body = {
                "model_override": "openai-codex/gpt-5.6-sol",
                "thinking": "xhigh",
            }
            message_body = {"message": "hello"}
            stop_body = {}
            cancel_body = {}
            if conversation_id is not None:
                model_body["conversation_id"] = conversation_id
                message_body["conversation_id"] = conversation_id
                stop_body["conversation_id"] = conversation_id
                cancel_body["conversation_id"] = conversation_id

            requests = (
                (
                    "/agent/chat/model",
                    model_body,
                    "invalid_prime_model_request",
                ),
                (
                    "/agent/chat/message",
                    message_body,
                    "invalid_prime_message_request",
                ),
                (
                    "/agent/chat/stop",
                    stop_body,
                    "invalid_prime_stop_request",
                ),
                (
                    "/agent/chat/cancel",
                    cancel_body,
                    "invalid_prime_cancel_request",
                ),
            )
            for path, body, expected_code in requests:
                response = await self.client.post(
                    path,
                    json=body,
                    headers=self._headers(),
                )
                assert response.status == 400
                assert (await response.json())["code"] == expected_code

        assert self.backend.calls == []

    async def test_prime_rejects_execution_mode_and_ui_response(self):
        message = await self.client.post(
            "/agent/chat/message",
            json={
                "conversation_id": self.conversation_id,
                "message": "hello",
                "execution_mode": "worker_first_csharp_v1",
            },
            headers=self._headers(),
        )
        ui = await self.client.post(
            "/agent/chat/ui-response", json={}, headers=self._headers()
        )

        assert message.status == 400
        assert ui.status == 400
        assert (await message.json())["code"] == "unsupported_in_prime_text_slice"
        assert (await ui.json())["code"] == "unsupported_in_prime_text_slice"

    async def test_prime_models_cancel_close_and_model_reconciliation(self):
        target = TargetFingerprint(2468, "638918000000000000", 42)
        await self.backend.create(self.conversation_id, target)

        models = await self.client.get(
            f"/agent/chat/models?conversation_id={self.conversation_id}",
            headers=self._headers(),
        )
        updated = await self.client.post(
            "/agent/chat/model",
            json={
                "conversation_id": self.conversation_id,
                "model_override": "openai-codex/gpt-5.6-sol",
                "thinking": "high",
            },
            headers=self._headers(),
        )
        cancelled = await self.client.post(
            "/agent/chat/cancel",
            json={"conversation_id": self.conversation_id},
            headers=self._headers(),
        )
        stopped = await self.client.post(
            "/agent/chat/stop",
            json={"conversation_id": self.conversation_id},
            headers=self._headers(),
        )

        assert models.status == 200
        assert (await models.json())["models"][0]["id"] == "openai-codex/gpt-5.6-sol"
        assert updated.status == 200
        assert (await updated.json())["actual"]["thinking"] == "high"
        assert (await cancelled.json())["state"] == "cancel_requested"
        assert (await stopped.json())["state"] == "closed"

        actual = PrimeModelSelection("openai-codex", "gpt-5.6-sol", "low")
        self.backend.model_error = PrimeBackendError(
            "model_update_failed_reconciled", actual_model=actual
        )
        reconciled = await self.client.post(
            "/agent/chat/model",
            json={
                "conversation_id": self.conversation_id,
                "model_override": "openai-codex/gpt-5.6-sol",
                "thinking": "xhigh",
            },
            headers=self._headers(),
        )
        assert reconciled.status == 409
        assert (await reconciled.json())["actual"]["thinking"] == "low"

        self.backend.model_error = PrimeBackendError("model_reconciliation_failed")
        failed = await self.client.post(
            "/agent/chat/model",
            json={
                "conversation_id": self.conversation_id,
                "model_override": "openai-codex/gpt-5.6-sol",
                "thinking": "xhigh",
            },
            headers=self._headers(),
        )
        assert failed.status == 502
        assert (await failed.json())["code"] == "model_reconciliation_failed"

    async def test_cleanup_shuts_prime_backend_down_once(self):
        await self.app.shutdown()
        assert self.backend.shutdown_calls == 1


@pytest.mark.asyncio
async def test_prime_vertical_http_cancel_race_is_correlated_and_model_free(
    tmp_path: Path,
) -> None:
    conversation_id = "conv_abcdef0123456789abcdef0123456789"
    target = TargetFingerprint(2468, "638918000000000000", 42)
    registry = PrimeConversationRegistry(
        tmp_path / "registry",
        rhino_pid=target.rhino_pid,
        rhino_process_start_utc_ticks=target.rhino_process_start_utc_ticks,
    )
    fixture = Path(__file__).parent / "fixtures" / "prime_rpc_fake_child.py"
    processes: list[PrimeRpcProcess] = []

    def process_factory(
        generation: int,
        model: PrimeModelSelection,
        resume_session_path: str | None,
    ) -> PrimeRpcProcess:
        process = PrimeRpcProcess(
            node_path=sys.executable,
            cli_path=fixture,
            session_dir=tmp_path / "sessions",
            generation=generation,
            provider=model.provider,
            model_id=model.id,
            thinking=model.thinking,
            resume_session_path=resume_session_path,
            extra_args=("--scenario", "vertical_cancel_race"),
        )
        processes.append(process)
        return process

    backend = PrimeChatBackend(
        registry,
        process_factory,
        PrimeModelSelection("fixture", "model", None),
        retirement_grace_seconds=0.1,
    )
    legacy = _ExplodingLegacyRunner()
    nonce = "vertical-test-nonce"
    app = create_chat_app(
        runner=legacy,
        backend_mode="prime",
        prime_backend=backend,
        rhino_process_id=target.rhino_pid,
        rhino_process_start_utc_ticks=target.rhino_process_start_utc_ticks,
        session_nonce=nonce,
    )
    client = TestClient(TestServer(app))
    headers = {"X-Rook-Session": nonce}

    try:
        await client.start_server()
        created = await client.post(
            "/agent/chat/start",
            json={
                "action": "create",
                "conversation_id": conversation_id,
                "target": {
                    "rhinoPid": target.rhino_pid,
                    "rhinoProcessStartUtcTicks": (
                        target.rhino_process_start_utc_ticks
                    ),
                    "documentRuntimeSerial": target.document_runtime_serial,
                },
            },
            headers=headers,
        )
        assert created.status == 200

        response = await client.post(
            "/agent/chat/message",
            json={"conversation_id": conversation_id, "message": "hello"},
            headers=headers,
        )
        leading = [
            json.loads((await asyncio.wait_for(response.content.readline(), 2)).decode())
            for _ in range(4)
        ]
        assert leading == [
            {"type": "text_delta", "content": "segment-1"},
            {"type": "status", "status": "segment_end"},
            {"type": "text_delta", "content": "segment-2"},
            {"type": "status", "status": "segment_end"},
        ]
        assert not any(row.get("type") == "done" for row in leading)

        cancelled = await client.post(
            "/agent/chat/cancel",
            json={"conversation_id": conversation_id},
            headers=headers,
        )
        assert cancelled.status == 200
        terminal_rows = [
            json.loads(line)
            for line in (await response.text()).splitlines()
            if line
        ]
        assert terminal_rows == [
            {"type": "done", "reason": "completed_before_abort"}
        ]

        record = registry.load(conversation_id)
        assert record.conversation_id == conversation_id
        assert record.prime_session_id == Path(record.prime_session_path).stem
        assert record.target == target
        assert record.last_lifecycle.state == "idle"
        assert record.last_lifecycle.reason == "completed_before_abort"
        assert legacy.calls == 0

        stopped = await client.post(
            "/agent/chat/stop",
            json={"conversation_id": conversation_id},
            headers=headers,
        )
        assert stopped.status == 200
        assert registry.load(conversation_id).last_lifecycle.state == "closed"
    finally:
        await client.close()
        registry.close()

    assert processes
    assert all(process._retired for process in processes)


def test_invalid_chat_backend_refuses_app_creation(monkeypatch):
    monkeypatch.setenv("ROOK_CHAT_BACKEND", "invalid")
    with pytest.raises(ValueError, match="ROOK_CHAT_BACKEND"):
        create_chat_app()


def test_prime_chat_backend_requires_explicit_owner():
    with pytest.raises(ValueError, match="prime_backend"):
        create_chat_app(backend_mode="prime")


def test_absent_chat_backend_remains_legacy(monkeypatch):
    monkeypatch.delenv("ROOK_CHAT_BACKEND", raising=False)
    app = create_chat_app(store=ConversationStore(), runner=ChatRunner())
    assert app[chat_server._BACKEND_MODE_KEY] == "legacy"


def test_explicit_legacy_chat_backend_remains_legacy(monkeypatch):
    monkeypatch.setenv("ROOK_CHAT_BACKEND", "legacy")
    app = create_chat_app(store=ConversationStore(), runner=ChatRunner())
    assert app[chat_server._BACKEND_MODE_KEY] == "legacy"


def test_prime_service_configuration_is_closed_and_absolute(tmp_path):
    node = tmp_path / "node.exe"
    cli = tmp_path / "cli.js"
    node.write_bytes(b"node")
    cli.write_text("// cli", encoding="utf-8")
    registry = tmp_path / "registry"

    config = chat_service_main._build_service_configuration(
        rhino_process_id=2468,
        rhino_process_start_utc_ticks="638918000000000000",
        environment={
            "ROOK_CHAT_BACKEND": "prime",
            "ROOK_PRIME_NODE_PATH": str(node),
            "ROOK_PRIME_CLI_PATH": str(cli),
            "ROOK_PRIME_MODEL": "openai-codex/gpt-5.6-sol",
            "ROOK_PRIME_THINKING": "xhigh",
            "ROOK_PRIME_REGISTRY_ROOT": str(registry),
        },
    )

    try:
        assert config.backend_mode == "prime"
        assert config.node_path == node.absolute()
        assert config.cli_path == cli.absolute()
        assert config.registry_root == registry.absolute()
        assert config.default_model == PrimeModelSelection(
            "openai-codex", "gpt-5.6-sol", "xhigh"
        )
    finally:
        assert config.registry is not None
        config.registry.close()


@pytest.mark.parametrize(
    ("override", "match"),
    [
        ({"ROOK_PRIME_NODE_PATH": "relative/node.exe"}, "absolute"),
        ({"ROOK_PRIME_CLI_PATH": "relative/cli.js"}, "absolute"),
        ({"ROOK_PRIME_MODEL": "missing-provider"}, "provider/model"),
        ({"ROOK_PRIME_THINKING": "impossible"}, "thinking"),
        ({"ROOK_PRIME_REGISTRY_ROOT": "relative/registry"}, "absolute"),
    ],
)
def test_prime_service_configuration_refuses_drift(tmp_path, override, match):
    node = tmp_path / "node.exe"
    cli = tmp_path / "cli.js"
    node.write_bytes(b"node")
    cli.write_text("// cli", encoding="utf-8")
    environment = {
        "ROOK_CHAT_BACKEND": "prime",
        "ROOK_PRIME_NODE_PATH": str(node),
        "ROOK_PRIME_CLI_PATH": str(cli),
        "ROOK_PRIME_MODEL": "openai-codex/gpt-5.6-sol",
        "ROOK_PRIME_THINKING": "xhigh",
        "ROOK_PRIME_REGISTRY_ROOT": str((tmp_path / "registry").absolute()),
        **override,
    }
    with pytest.raises(ValueError, match=match):
        chat_service_main._build_service_configuration(
            rhino_process_id=2468,
            rhino_process_start_utc_ticks="638918000000000000",
            environment=environment,
        )


def test_legacy_service_configuration_needs_no_prime_values():
    config = chat_service_main._build_service_configuration(
        rhino_process_id=2468,
        rhino_process_start_utc_ticks="638918000000000000",
        environment={"ROOK_CHAT_BACKEND": "legacy"},
    )
    assert config.backend_mode == "legacy"
    assert config.prime_backend is None


def test_prime_service_configuration_can_inherit_prime_model(tmp_path):
    node = tmp_path / "node.exe"
    cli = tmp_path / "cli.js"
    node.write_bytes(b"node")
    cli.write_text("// cli", encoding="utf-8")
    config = chat_service_main._build_service_configuration(
        rhino_process_id=2468,
        rhino_process_start_utc_ticks="638918000000000000",
        environment={
            "ROOK_CHAT_BACKEND": "prime",
            "ROOK_PRIME_NODE_PATH": str(node),
            "ROOK_PRIME_CLI_PATH": str(cli),
            "ROOK_PRIME_REGISTRY_ROOT": str((tmp_path / "registry").absolute()),
        },
    )
    try:
        assert config.default_model is None
        assert config.prime_backend is not None
    finally:
        assert config.registry is not None
        config.registry.close()


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
