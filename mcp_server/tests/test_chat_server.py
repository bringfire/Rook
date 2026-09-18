"""HTTP contract tests for the ACP-backed RookChat service."""

from __future__ import annotations

import asyncio
import base64
import json
from io import BytesIO
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

import pytest
from aiohttp.test_utils import TestClient, TestServer
from PIL import Image

from rook.agent.chat import server as chat_server
from rook.agent.chat.acp_conversation import (
    CloseResult,
    ConversationBusy,
    ConversationNotOpen,
    ConversationView,
    CreateConversationRequest,
    DeleteResult,
    ImageUnsupported,
    PromptInput,
    PromptResult,
    TargetUnavailable,
)
from rook.agent.chat.acp_images import ImageAdmissionError
from rook.agent.chat.acp_presentation import PresentationCache, ProjectedEvent, PromptGeneration
from rook.agent.chat.acp_process import AcpCapabilityError
from rook.agent.chat.acp_storage import (
    AssociationAlreadyExists,
    InitializationFailed,
    PublicationAlreadyExists,
    PublicationUnsupported,
    RuntimeUnavailable as StoredRuntimeUnavailable,
    SessionRecoveryRequired,
    SessionUnavailable,
    WorkingDirectoryUnavailable,
)
from rook.agent.chat.prime_runtime import PrimeLaunchError, RuntimeUnavailable


VALID_CONVERSATION_ID = "1" * 32
VALID_HOST_GENERATION_ID = "21b9e56c-0114-4f88-bca4-4882ba2cd1cc"
_png_buffer = BytesIO()
Image.new("RGB", (1, 1), (10, 20, 30)).save(_png_buffer, format="PNG")
PNG_1X1 = base64.b64encode(_png_buffer.getvalue()).decode("ascii")


@dataclass(frozen=True)
class _Association:
    conversation_id: str = VALID_CONVERSATION_ID
    prime_session_id: str = "prime-session"
    runtime_id: str = "A" * 64
    requested_initial_model: str | None = "anthropic/claude"
    requested_initial_reasoning: str | None = "high"
    binding: object = field(
        default_factory=lambda: SimpleNamespace(
            profile="full",
            host_generation_id=VALID_HOST_GENERATION_ID,
            rhino_document_serial=42,
            route_process_id=2468,
        )
    )


class _Store:
    def __init__(self, root: Path) -> None:
        self._association = _Association()
        self.paths = SimpleNamespace(
            presentation_path=lambda conversation_id: root / "presentation" / conversation_id
        )

    def list(self):
        return (self._association,)

    def get(self, conversation_id: str):
        if conversation_id != self._association.conversation_id:
            raise SessionUnavailable("association is missing")
        return self._association


class _CompletedSupervisor:
    def __init__(self, coroutine) -> None:
        self.generation = PromptGeneration(1, "acp-1", "prompt-1")
        self._task = asyncio.create_task(coroutine)
        self.cancel_sources: list[str] = []

    @property
    def result_task(self):
        return asyncio.shield(self._task)

    def request_cancel(self, source: str) -> bool:
        if self.cancel_sources:
            return False
        self.cancel_sources.append(source)
        return True


class FakeManager:
    def __init__(self, root: Path) -> None:
        self.store = _Store(root)
        self.created: CreateConversationRequest | None = None
        self.reopened: list[str] = []
        self.prompted: list[tuple[str, PromptInput]] = []
        self.cancelled: list[tuple[str, str]] = []
        self.closed: list[str] = []
        self.deleted: list[str] = []
        self.shutdown_calls = 0
        self.raise_from: dict[str, Exception] = {}

    async def create(self, request: CreateConversationRequest) -> ConversationView:
        self._raise("create")
        self.created = request
        return ConversationView(VALID_CONVERSATION_ID, False, True)

    async def reopen(self, conversation_id: str) -> ConversationView:
        self._raise("reopen")
        self.reopened.append(conversation_id)
        return ConversationView(conversation_id, True, False)

    async def start_prompt(self, conversation_id: str, prompt: PromptInput, sink):
        self._raise("prompt")
        self.prompted.append((conversation_id, prompt))

        async def complete():
            await sink.write(ProjectedEvent(1, "agent_message_chunk", "m1", "hello", None))
            return PromptResult("settled", "end_turn", "delivered", True)

        return _CompletedSupervisor(complete())

    async def request_cancel(self, conversation_id: str, source: str) -> bool:
        self._raise("cancel")
        self.cancelled.append((conversation_id, source))
        return True

    async def close(self, conversation_id: str) -> CloseResult:
        self._raise("close")
        self.closed.append(conversation_id)
        return CloseResult("clean", True)

    async def delete(self, conversation_id: str) -> DeleteResult:
        self._raise("delete")
        self.deleted.append(conversation_id)
        return DeleteResult(True, True)

    async def shutdown(self):
        self.shutdown_calls += 1
        return ()

    def _raise(self, operation: str) -> None:
        error = self.raise_from.get(operation)
        if error is not None:
            raise error


@asynccontextmanager
async def _client(manager: FakeManager, *, nonce: str | None = None):
    app = chat_server.create_chat_app(manager, expected_nonce=nonce)
    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        yield client
    finally:
        await client.close()


def _create_body(**overrides):
    body = {
        "profile": "full",
        "hostGenerationId": VALID_HOST_GENERATION_ID,
        "documentSerialNumber": 42,
        "routeProcessId": 2468,
        "savedDocumentDirectory": None,
        "model": "anthropic/claude",
        "reasoning": "high",
    }
    body.update(overrides)
    return body


def _prompt_body(**overrides):
    body = {"text": "hello", "images": []}
    body.update(overrides)
    return body


async def _json(response):
    return json.loads(await response.text())


@pytest.mark.asyncio
async def test_task7_http_view_and_ordered_settings_status(tmp_path):
    from .test_chat_acp_conversation import _manager
    from .test_chat_acp_client import _settings_update
    manager, _, _, factory, _ = _manager(tmp_path)
    async with _client(manager) as client:
        response = await client.post("/agent/chat/conversations", json=_create_body(savedDocumentDirectory=None))
        view = await response.json()
        assert view.get("effectiveSettings") == {"provider": None, "model": None, "reasoning": None}
        latest = {"provider": "actual", "model": "c", "reasoning": "off"}
        process = factory.processes[0]
        await process.client.session_update(process.session_id, _settings_update(latest))
        response = await client.post(f"/agent/chat/conversations/{view['conversationId']}/prompt", json=_prompt_body())
        rows = [json.loads(line) for line in (await response.text()).splitlines()]
        assert rows[0] == {"type": "session_status", "effectiveSettings": latest}
        assert rows[-1]["type"] == "terminal"
        assert not any(row["type"] == "tool_update" for row in rows)


@pytest.mark.asyncio
async def test_replacement_route_contract_and_health_are_acp_only(tmp_path: Path):
    manager = FakeManager(tmp_path)
    async with _client(manager) as client:
        health = await client.get("/agent/chat/health")
        assert health.status == 200
        payload = await _json(health)
        assert payload["service"]["status"] == "ok"
        assert payload["runtime"]["available"] is True
        assert payload["configurationAvailable"] is False
        assert payload["authentication"] == {"owner": "Prime", "disclosure": "Prime-managed"}
        assert "provider_keys" not in json.dumps(payload)

        allowed = (
            ("post", "/agent/chat/configuration"),
            ("post", "/agent/chat/configuration/reply"),
            ("post", "/agent/chat/configuration/cancel"),
            ("get", "/agent/chat/conversations"),
            ("post", "/agent/chat/conversations"),
            ("post", "/agent/chat/conversations/{conversation_id}/reopen"),
            ("get", "/agent/chat/conversations/{conversation_id}/history"),
            ("post", "/agent/chat/conversations/{conversation_id}/prompt"),
            ("post", "/agent/chat/conversations/{conversation_id}/cancel"),
            ("post", "/agent/chat/conversations/{conversation_id}/close"),
            ("delete", "/agent/chat/conversations/{conversation_id}"),
        )
        registered = {(route.method.lower(), route.resource.canonical) for route in client.server.app.router.routes()}
        for route in allowed:
            assert route in registered

        for legacy in (
            "/agent/chat/personas",
            "/agent/chat/models",
            "/agent/chat/model",
            "/agent/chat/start",
            "/agent/chat/message",
            "/agent/chat/stop",
            "/agent/chat/ui-response",
            "/agent/chat/worker-first",
        ):
            assert (await client.get(legacy)).status == 404


@pytest.mark.asyncio
async def test_nonce_middleware_still_protects_every_non_health_route(tmp_path: Path):
    async with _client(FakeManager(tmp_path), nonce="secret") as client:
        assert (await client.get("/agent/chat/health")).status == 200
        assert (await client.get("/agent/chat/conversations")).status == 403
        for path in ("configuration", "configuration/reply", "configuration/cancel"):
            refused = await client.post(f"/agent/chat/{path}", json={})
            assert refused.status == 403
            assert refused.headers["Cache-Control"] == "no-store"
        response = await client.get(
            "/agent/chat/conversations", headers={chat_server.SESSION_HEADER: "secret"}
        )
        assert response.status == 200


@pytest.mark.asyncio
async def test_create_maps_closed_body_to_manager_request(tmp_path: Path):
    manager = FakeManager(tmp_path)
    async with _client(manager) as client:
        response = await client.post("/agent/chat/conversations", json=_create_body())
        payload = await _json(response)
    assert response.status == 201
    assert payload == {
        "conversationId": VALID_CONVERSATION_ID,
        "durable": False,
        "targetAvailable": True,
    }
    assert manager.created is not None
    assert manager.created.saved_document_directory is None
    assert manager.created.requested_initial_model == "anthropic/claude"
    assert manager.created.requested_initial_reasoning == "high"
    assert manager.created.binding.profile == "full"
    assert manager.created.binding.host_generation_id == VALID_HOST_GENERATION_ID
    assert manager.created.binding.rhino_document_serial == 42
    assert manager.created.binding.route_process_id == 2468


@pytest.mark.asyncio
async def test_create_preserves_slashes_within_model_id(tmp_path: Path):
    manager = FakeManager(tmp_path)
    body = _create_body()
    body["model"] = "openrouter/anthropic/claude-sonnet-4.5"
    async with _client(manager) as client:
        response = await client.post("/agent/chat/conversations", json=body)
        assert response.status == 201
    assert manager.created.requested_initial_model == body["model"]


@pytest.mark.asyncio
async def test_list_reopen_history_cancel_close_and_delete_project_manager_outcomes(tmp_path: Path):
    manager = FakeManager(tmp_path)
    cache = PresentationCache(manager.store.paths.presentation_path(VALID_CONVERSATION_ID))
    cache.publish_fallback(stop_reason="cancelled", original_byte_counts={"user": 5, "assistant": 2})
    async with _client(manager) as client:
        listing = await _json(await client.get("/agent/chat/conversations"))
        assert listing["conversations"][0]["conversationId"] == VALID_CONVERSATION_ID
        assert listing["conversations"][0]["requestedInitialModel"] == "anthropic/claude"

        reopened = await _json(
            await client.post(f"/agent/chat/conversations/{VALID_CONVERSATION_ID}/reopen", json={})
        )
        assert reopened == {
            "conversationId": VALID_CONVERSATION_ID,
            "durable": True,
            "targetAvailable": False,
        }

        history = await _json(
            await client.get(f"/agent/chat/conversations/{VALID_CONVERSATION_ID}/history")
        )
        assert history["available"] is True
        assert history["turns"][0]["fallback"] is True

        cancel = await _json(
            await client.post(f"/agent/chat/conversations/{VALID_CONVERSATION_ID}/cancel", json={})
        )
        assert cancel == {"accepted": True}

        close = await _json(
            await client.post(f"/agent/chat/conversations/{VALID_CONVERSATION_ID}/close", json={})
        )
        assert close == {"outcome": "clean", "childExitObserved": True}

        deleted = await _json(
            await client.delete(f"/agent/chat/conversations/{VALID_CONVERSATION_ID}")
        )
        assert deleted == {"associationRemoved": True, "artifactsRemoved": True}

    assert manager.reopened == [VALID_CONVERSATION_ID]
    assert manager.cancelled == [(VALID_CONVERSATION_ID, "http_cancel")]
    assert manager.closed == [VALID_CONVERSATION_ID]
    assert manager.deleted == [VALID_CONVERSATION_ID]


@pytest.mark.asyncio
async def test_prompt_stream_maps_projected_and_terminal_outcomes_separately(tmp_path: Path):
    manager = FakeManager(tmp_path)
    async with _client(manager) as client:
        response = await client.post(
            f"/agent/chat/conversations/{VALID_CONVERSATION_ID}/prompt", json=_prompt_body()
        )
        rows = [json.loads(line) for line in (await response.text()).splitlines()]

    assert response.status == 200
    assert rows == [
        {"type": "text_delta", "sourceOrdinal": 1, "messageId": "m1", "text": "hello"},
        {
            "type": "terminal",
            "outcome": "settled",
            "stopReason": "end_turn",
            "presentationOutcome": "delivered",
            "cachePublished": True,
        },
    ]
    assert manager.prompted[0] == (VALID_CONVERSATION_ID, PromptInput("hello", ()))


@pytest.mark.asyncio
async def test_repeated_responses_do_not_present_prime_completion_metadata_as_tools(tmp_path: Path):
    from acp.schema import AgentMessageChunk, SessionInfoUpdate
    from rook.agent.chat.acp_client import RookChatAcpClient
    from rook.agent.chat.acp_presentation import BoundedPromptProjection, PresentationQueue

    class MetadataManager(FakeManager):
        async def start_prompt(self, conversation_id, prompt, sink):
            async def complete():
                generation = PromptGeneration(1, "acp-session", "prompt")
                projection = BoundedPromptProjection(
                    generation=generation, queue=PresentationQueue(), user_text=prompt.text,
                )
                callback = RookChatAcpClient()
                callback.activate_prompt(generation, projection, asyncio.Event())
                await callback.session_update("acp-session", AgentMessageChunk.model_validate({
                    "sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": "hello"},
                }))
                for metadata in (
                    {"terminalQuiescenceExpected": True},
                    {"quiescence": {"outstandingSubagents": 0}},
                    {"quiescence": {"outstandingSubagents": 0}},
                ):
                    await callback.session_update("acp-session", SessionInfoUpdate.model_validate({
                        "sessionUpdate": "session_info_update",
                        "_meta": {"ai.primeintellect.prime-agent": metadata},
                    }))
                # Metadata still reaches the real callback and ordered projection.
                events = projection.queue.snapshot()
                assert [event.source_ordinal for event in events] == [0, 1, 2, 3]
                assert callback.prime_meta.unknown.records
                assert projection.finalize("end_turn").tool_cards == ()
                for event in events:
                    await sink.write(event)
                return PromptResult("settled", "end_turn", "delivered", True)
            return _CompletedSupervisor(complete())

    async with _client(MetadataManager(tmp_path)) as client:
        for _ in range(2):
            response = await client.post(
                f"/agent/chat/conversations/{VALID_CONVERSATION_ID}/prompt", json=_prompt_body()
            )
            rows = [json.loads(line) for line in (await response.text()).splitlines()]
            assert response.status == 200
            assert rows == [
                {"type": "text_delta", "sourceOrdinal": 0, "messageId": None, "text": "hello"},
                {"type": "terminal", "outcome": "settled", "stopReason": "end_turn",
                 "presentationOutcome": "delivered", "cachePublished": True},
            ]


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["tool_call", "tool_call_update", "available_commands_update",
                                  "current_mode_update", "config_option_update", "future_update"])
async def test_http_tool_cards_require_actual_tool_event_kinds(kind):
    class Response:
        def __init__(self):
            self.rows = []

        async def write(self, data):
            self.rows.append(json.loads(data))

    response = Response()
    sink = chat_server._HttpPresentationSink(response)
    sink.mark_prepared()
    payload = {"toolCallId": "tool-1", "status": "completed"}
    await sink.write(ProjectedEvent(7, kind, "tool-1", "Inspect", payload))
    assert response.rows == ([{
        "type": "tool_update", "sourceOrdinal": 7, "kind": kind,
        "messageId": "tool-1", "text": "Inspect", "payload": payload,
    }] if kind in {"tool_call", "tool_call_update"} else [])
    assert await sink.drain(1.0)


@pytest.mark.asyncio
async def test_stream_and_early_refusal_send_fixed_cors_headers_on_the_wire(tmp_path: Path):
    origin = {"Origin": chat_server.ALLOWED_ORIGIN}
    async with _client(FakeManager(tmp_path), nonce="secret") as client:
        stream = await client.post(
            f"/agent/chat/conversations/{VALID_CONVERSATION_ID}/prompt",
            json=_prompt_body(),
            headers={**origin, chat_server.SESSION_HEADER: "secret"},
        )
        assert stream.status == 200
        assert stream.headers["Access-Control-Allow-Origin"] == chat_server.ALLOWED_ORIGIN
        await stream.read()

        refused = await client.get("/agent/chat/conversations", headers=origin)
        assert refused.status == 403
        assert refused.headers["Access-Control-Allow-Origin"] == chat_server.ALLOWED_ORIGIN

        wrong_origin = await client.get(
            "/agent/chat/conversations",
            headers={"Origin": "https://unexpected.example", chat_server.SESSION_HEADER: "secret"},
        )
        assert wrong_origin.status == 403
        assert wrong_origin.headers["Access-Control-Allow-Origin"] == chat_server.ALLOWED_ORIGIN


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/agent/chat/conversations", None),
        ("/agent/chat/conversations", []),
        (f"/agent/chat/conversations/{VALID_CONVERSATION_ID}/reopen", []),
        (f"/agent/chat/conversations/{VALID_CONVERSATION_ID}/cancel", "cancel"),
        (f"/agent/chat/conversations/{VALID_CONVERSATION_ID}/close", 1),
    ],
)
async def test_non_object_json_is_refused(tmp_path: Path, path: str, body):
    async with _client(FakeManager(tmp_path)) as client:
        response = await client.post(path, json=body)
        assert response.status == 400
        assert (await _json(response))["error"]["code"] == "invalid_request"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"profile": "admin"}, "invalid_profile"),
        ({"documentSerialNumber": 0}, "invalid_document_serial"),
        ({"routeProcessId": 0}, "invalid_route_process_id"),
        ({"hostGenerationId": "not-a-uuid"}, "invalid_host_generation_id"),
        ({"model": "not-qualified"}, "invalid_model"),
        ({"reasoning": "extreme"}, "invalid_reasoning"),
        ({"unexpected": True}, "invalid_request"),
    ],
)
async def test_create_rejects_invalid_closed_fields(tmp_path: Path, overrides, code: str):
    async with _client(FakeManager(tmp_path)) as client:
        response = await client.post("/agent/chat/conversations", json=_create_body(**overrides))
        assert response.status == 400
        assert (await _json(response))["error"]["code"] == code


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "body", "code"),
    [
        ("/agent/chat/conversations", _create_body(model="anthropic/\ud800"), "invalid_model"),
        (
            "/agent/chat/conversations",
            _create_body(savedDocumentDirectory="C:/bad/\ud800"),
            "invalid_saved_document_directory",
        ),
        (
            f"/agent/chat/conversations/{VALID_CONVERSATION_ID}/prompt",
            _prompt_body(text="\ud800"),
            "invalid_prompt",
        ),
        (
            f"/agent/chat/conversations/{VALID_CONVERSATION_ID}/prompt",
            _prompt_body(
                images=[
                    {"fileName": "\ud800.png", "mimeType": "image/png", "base64Data": PNG_1X1}
                ]
            ),
            "invalid_image",
        ),
    ],
)
async def test_scalar_fields_refuse_non_utf8_unicode(
    tmp_path: Path, path: str, body: dict[str, object], code: str
):
    async with _client(FakeManager(tmp_path)) as client:
        response = await client.post(path, json=body)
        assert response.status == 400
        assert (await _json(response))["error"]["code"] == code


@pytest.mark.asyncio
async def test_path_identity_is_the_only_conversation_identity(tmp_path: Path):
    manager = FakeManager(tmp_path)
    async with _client(manager) as client:
        invalid = await client.post("/agent/chat/conversations/not-a-conversation/reopen", json={})
        assert invalid.status == 400
        assert (await _json(invalid))["error"]["code"] == "invalid_conversation_id"
        extra = await client.post(
            f"/agent/chat/conversations/{VALID_CONVERSATION_ID}/reopen",
            json={"conversationId": VALID_CONVERSATION_ID},
        )
        assert extra.status == 400
        assert (await _json(extra))["error"]["code"] == "invalid_request"
    assert manager.reopened == []


@pytest.mark.asyncio
async def test_prompt_admits_strict_camel_case_images_and_never_echoes_bytes(tmp_path: Path):
    manager = FakeManager(tmp_path)
    async with _client(manager) as client:
        response = await client.post(
            f"/agent/chat/conversations/{VALID_CONVERSATION_ID}/prompt",
            json=_prompt_body(
                images=[
                    {"fileName": "pixel.png", "mimeType": "image/png", "base64Data": PNG_1X1}
                ]
            ),
        )
        body = await response.text()
    assert response.status == 200
    assert PNG_1X1 not in body
    image = manager.prompted[0][1].images[0]
    assert image.file_name == "pixel.png"
    assert image.binary_bytes == len(base64.b64decode(PNG_1X1))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "image",
    [
        {"fileName": "bad.gif", "mimeType": "image/gif", "base64Data": "AAAA"},
        {"fileName": "bad.png", "mimeType": "image/png", "base64Data": "%%%"},
        {
            "fileName": "bad.png",
            "mimeType": "image/png",
            "base64Data": base64.b64encode(b"GIF89a").decode(),
        },
    ],
)
async def test_prompt_rejects_invalid_image_mime_base64_and_magic(tmp_path: Path, image):
    async with _client(FakeManager(tmp_path)) as client:
        response = await client.post(
            f"/agent/chat/conversations/{VALID_CONVERSATION_ID}/prompt",
            json=_prompt_body(images=[image]),
        )
        assert response.status == 400
        assert (await _json(response))["error"]["code"] == "invalid_image"


@pytest.mark.asyncio
@pytest.mark.parametrize("detail", ["image binary size is invalid", "image dimensions are invalid"])
async def test_prompt_maps_image_size_and_dimension_refusals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, detail: str
):
    def refuse(*_args, **_kwargs):
        raise ImageAdmissionError(detail)

    monkeypatch.setattr(chat_server, "validate_images", refuse)
    async with _client(FakeManager(tmp_path)) as client:
        response = await client.post(
            f"/agent/chat/conversations/{VALID_CONVERSATION_ID}/prompt", json=_prompt_body()
        )
        assert response.status == 400
        assert (await _json(response))["error"]["code"] == "invalid_image"


@pytest.mark.asyncio
async def test_encoded_body_limit_refuses_before_json_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(chat_server, "MAX_HTTP_BODY_BYTES", 8)
    manager = FakeManager(tmp_path)
    async with _client(manager) as client:
        response = await client.post(
            "/agent/chat/conversations",
            data=b'{"more":true}',
            headers={"Content-Type": "application/json"},
        )
        assert response.status == 413
        assert (await _json(response))["error"]["code"] == "request_too_large"
    assert manager.created is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "code", "status"),
    [
        (ConversationNotOpen(VALID_CONVERSATION_ID), "conversation_not_open", 409),
        (ConversationBusy(VALID_CONVERSATION_ID), "conversation_busy", 409),
        (TargetUnavailable(), "target_unavailable", 409),
        (ImageUnsupported(), "image_unsupported", 409),
        (SessionUnavailable(), "session_unavailable", 409),
        (StoredRuntimeUnavailable(), "runtime_unavailable", 503),
        (WorkingDirectoryUnavailable(), "working_directory_unavailable", 409),
        (SessionRecoveryRequired(), "session_recovery_required", 409),
        (InitializationFailed(), "initialization_failed", 502),
        (PublicationUnsupported(), "publication_unsupported", 409),
        (PublicationAlreadyExists(), "publication_already_exists", 409),
        (AssociationAlreadyExists(), "association_already_exists", 409),
        (RuntimeUnavailable("missing"), "runtime_unavailable", 503),
        (PrimeLaunchError("invalid_model"), "invalid_model", 400),
        (AcpCapabilityError("session_close_required"), "session_close_required", 502),
    ],
)
async def test_closed_manager_and_acp_errors_use_stable_envelopes(
    tmp_path: Path, error: Exception, code: str, status: int
):
    manager = FakeManager(tmp_path)
    manager.raise_from["reopen"] = error
    async with _client(manager) as client:
        response = await client.post(
            f"/agent/chat/conversations/{VALID_CONVERSATION_ID}/reopen", json={}
        )
        payload = await _json(response)
    assert response.status == status
    assert payload["error"]["code"] == code
    assert isinstance(payload["error"]["message"], str)
    assert len(payload["error"]["message"].encode("utf-8")) <= 1024


@pytest.mark.asyncio
async def test_history_reports_cache_unavailable_without_blocking_conversation(tmp_path: Path):
    manager = FakeManager(tmp_path)
    path = manager.store.paths.presentation_path(VALID_CONVERSATION_ID)
    path.mkdir(parents=True)
    (path / "invalid.json").write_text("{}", encoding="utf-8")
    async with _client(manager) as client:
        response = await client.get(f"/agent/chat/conversations/{VALID_CONVERSATION_ID}/history")
        payload = await _json(response)
    assert response.status == 200
    assert payload == {
        "available": False,
        "turns": [],
        "earlierHistoryOmitted": False,
        "message": "presentation history unavailable",
    }


@pytest.mark.asyncio
async def test_application_cleanup_delegates_only_to_manager_shutdown(tmp_path: Path):
    manager = FakeManager(tmp_path)
    async with _client(manager):
        pass
    assert manager.shutdown_calls == 1
