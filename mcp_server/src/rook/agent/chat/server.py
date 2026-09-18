"""Authenticated HTTP presentation boundary for ACP-backed RookChat."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from aiohttp import web

from .acp_conversation import (
    AcpConversationManager,
    ConversationBusy,
    ConversationNotOpen,
    ConversationView,
    CreateConversationRequest,
    ImageUnsupported,
    PromptInput,
    TargetUnavailable,
)
from .acp_images import (
    MAX_HTTP_BODY_BYTES,
    MAX_IMAGE_FILE_NAME_UTF8_BYTES,
    ImageAdmissionError,
    validate_images,
)
from .acp_presentation import MAX_USER_TEXT_BYTES, PresentationCache, ProjectedEvent
from .acp_process import AcpCapabilityError
from .acp_storage import AcpStorageError, RookBinding
from .prime_runtime import PrimeLaunchError, RuntimeUnavailable, SUPPORTED_REASONING


logger = logging.getLogger(__name__)

CHAT_SERVER_BIND_HOST = "127.0.0.1"
DISCOVERY_FOLDER = Path(tempfile.gettempdir()) / "rook"
DISCOVERY_FILE_PREFIX = "chat-service-"
SERVICE_VERSION = "2.0.0"

ALLOWED_ORIGIN = "https://app.rook.invalid"
SESSION_HEADER = "X-Rook-Session"
NONCE_ENV_VAR = "ROOK_SESSION_NONCE"

MAX_ERROR_MESSAGE_UTF8_BYTES = 1024
MAX_MODEL_UTF8_BYTES = 512
MAX_SAVED_DOCUMENT_DIRECTORY_UTF8_BYTES = 4096

_ACP_MANAGER_KEY: web.AppKey[AcpConversationManager] = web.AppKey(
    "_acp_conversation_manager", AcpConversationManager
)
_PORT_STATE_KEY: web.AppKey[dict[str, int]] = web.AppKey("_port_state", dict)
_OWNER_KEY: web.AppKey[str] = web.AppKey("_owner", str)
_RHINO_PROCESS_ID_KEY: web.AppKey[int] = web.AppKey("_rhino_process_id", int)
_SESSION_NONCE_KEY: web.AppKey[str] = web.AppKey("_session_nonce", str)
_RUNTIME_AVAILABLE_KEY: web.AppKey[bool] = web.AppKey("_runtime_available", bool)


class _HttpContractError(ValueError):
    def __init__(self, code: str, message: str, status: int = 400) -> None:
        self.code = code
        self.status = status
        super().__init__(message)


def _bounded_text(value: object, limit: int = MAX_ERROR_MESSAGE_UTF8_BYTES) -> str:
    raw = str(value).encode("utf-8", errors="replace")
    if len(raw) <= limit:
        return raw.decode("utf-8", errors="replace")
    marker = b" [truncated]"
    return (raw[: max(0, limit - len(marker))] + marker).decode("utf-8", errors="ignore")


def _error_response(code: str, message: object, status: int) -> web.Response:
    return web.json_response(
        {"error": {"code": code, "message": _bounded_text(message)}}, status=status
    )


def _validate_utf8_scalar(
    value: object,
    *,
    code: str,
    label: str,
    max_bytes: int,
) -> str:
    if type(value) is not str:
        raise _HttpContractError(code, f"{label} is invalid")
    try:
        size = len(value.encode("utf-8", errors="strict"))
    except UnicodeEncodeError as exc:
        raise _HttpContractError(code, f"{label} is invalid") from exc
    if size > max_bytes:
        raise _HttpContractError(code, f"{label} is invalid")
    return value


def _classified_error(exc: Exception) -> tuple[str, int]:
    code = getattr(exc, "code", None)
    if isinstance(exc, _HttpContractError):
        return exc.code, exc.status
    if isinstance(exc, RuntimeUnavailable) or code == "runtime_unavailable":
        return "runtime_unavailable", 503
    if isinstance(exc, PrimeLaunchError):
        return exc.code, 400 if exc.code in {"invalid_model", "invalid_reasoning"} else 503
    if isinstance(exc, AcpCapabilityError):
        detail = str(exc)
        if detail in {"protocol_version_mismatch", "session_close_required"}:
            return detail, 502
        return "acp_capability_error", 502
    if isinstance(exc, ConversationNotOpen):
        return exc.code, 409
    if isinstance(exc, ConversationBusy):
        return exc.code, 409
    if isinstance(exc, (TargetUnavailable, ImageUnsupported)):
        return exc.code, 409
    if isinstance(exc, AcpStorageError):
        status = 502 if exc.code == "initialization_failed" else 409
        return exc.code, status
    if isinstance(exc, ImageAdmissionError):
        return exc.code, 400
    return "internal_error", 500


def _exception_response(exc: Exception) -> web.Response:
    code, status = _classified_error(exc)
    message = code if status == 500 else str(exc)
    return _error_response(code, message, status)


_CORS_HEADERS = {
    "Access-Control-Allow-Origin": ALLOWED_ORIGIN,
    "Access-Control-Allow-Methods": "GET, POST, DELETE, OPTIONS",
    "Access-Control-Allow-Headers": f"Content-Type, {SESSION_HEADER}",
}


def _with_cors(response: web.StreamResponse) -> web.StreamResponse:
    for key, value in _CORS_HEADERS.items():
        response.headers[key] = value
    return response


@web.middleware
async def cors_and_session_middleware(request: web.Request, handler):
    if request.method == "OPTIONS":
        return _with_cors(web.Response(status=204))

    origin = request.headers.get("Origin")
    if origin is not None and origin != ALLOWED_ORIGIN:
        return _with_cors(_error_response("origin_refused", "Origin is not allowed", 403))

    expected_nonce = request.app.get(_SESSION_NONCE_KEY, "")
    if expected_nonce and request.path != "/agent/chat/health":
        if request.headers.get(SESSION_HEADER, "") != expected_nonce:
            return _with_cors(
                _error_response("invalid_session_token", "Missing or invalid session token", 403)
            )

    response = await handler(request)
    return _with_cors(response)


async def _read_json_object(
    request: web.Request,
    *,
    required: frozenset[str],
    allowed: frozenset[str],
) -> dict[str, Any]:
    content_length = request.content_length
    if content_length is not None and content_length > MAX_HTTP_BODY_BYTES:
        raise _HttpContractError("request_too_large", "Encoded HTTP request is oversized", 413)
    try:
        raw = await request.read()
    except web.HTTPRequestEntityTooLarge as exc:
        raise _HttpContractError("request_too_large", "Encoded HTTP request is oversized", 413) from exc
    if len(raw) > MAX_HTTP_BODY_BYTES:
        raise _HttpContractError("request_too_large", "Encoded HTTP request is oversized", 413)
    try:
        body = json.loads(raw.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _HttpContractError("invalid_request", "Request body must be valid UTF-8 JSON") from exc
    if not isinstance(body, dict):
        raise _HttpContractError("invalid_request", "Request body must be a JSON object")
    keys = frozenset(body)
    if not required.issubset(keys) or not keys.issubset(allowed):
        raise _HttpContractError("invalid_request", "Request body keys are invalid")
    return body


def _conversation_id(request: web.Request) -> str:
    value = request.match_info.get("conversation_id", "")
    try:
        parsed = uuid.UUID(hex=value)
    except (ValueError, AttributeError) as exc:
        raise _HttpContractError("invalid_conversation_id", "Conversation ID is invalid") from exc
    if parsed.hex != value:
        raise _HttpContractError("invalid_conversation_id", "Conversation ID is invalid")
    return value


def _view_payload(view: ConversationView) -> dict[str, object]:
    return {
        "conversationId": view.conversation_id,
        "durable": view.durable,
        "targetAvailable": view.target_available,
    }


def _association_payload(association) -> dict[str, object]:
    return {
        "conversationId": association.conversation_id,
        "primeSessionId": association.prime_session_id,
        "runtimeId": association.runtime_id,
        "profile": association.binding.profile,
        "hostGenerationId": association.binding.host_generation_id,
        "documentSerialNumber": association.binding.rhino_document_serial,
        "routeProcessId": association.binding.route_process_id,
        "requestedInitialModel": association.requested_initial_model,
        "requestedInitialReasoning": association.requested_initial_reasoning,
    }


def _parse_create(body: dict[str, Any]) -> CreateConversationRequest:
    profile = body["profile"]
    if type(profile) is not str or profile not in {"readonly", "full"}:
        raise _HttpContractError("invalid_profile", "Capability profile is invalid")
    host_generation = body["hostGenerationId"]
    if type(host_generation) is not str:
        raise _HttpContractError("invalid_host_generation_id", "Host generation ID is invalid")
    document_serial = body["documentSerialNumber"]
    if type(document_serial) is not int or document_serial <= 0:
        raise _HttpContractError("invalid_document_serial", "Document serial must be positive")
    route_process_id = body["routeProcessId"]
    if type(route_process_id) is not int or route_process_id <= 0:
        raise _HttpContractError("invalid_route_process_id", "Route process ID must be positive")
    try:
        binding = RookBinding(profile, host_generation, document_serial, route_process_id)
    except ValueError as exc:
        raise _HttpContractError("invalid_host_generation_id", "Host generation ID is invalid") from exc

    saved_directory = body.get("savedDocumentDirectory")
    if saved_directory is not None:
        saved_directory = _validate_utf8_scalar(
            saved_directory,
            code="invalid_saved_document_directory",
            label="Saved document directory",
            max_bytes=MAX_SAVED_DOCUMENT_DIRECTORY_UTF8_BYTES,
        )
    model = body.get("model")
    if model is not None:
        model = _validate_utf8_scalar(
            model,
            code="invalid_model",
            label="Model",
            max_bytes=MAX_MODEL_UTF8_BYTES,
        )
        if "/" not in model or any(not part.strip() for part in model.split("/", 1)):
            raise _HttpContractError("invalid_model", "Model must be fully qualified")
    reasoning = body.get("reasoning")
    if reasoning is not None and (type(reasoning) is not str or reasoning not in SUPPORTED_REASONING):
        raise _HttpContractError("invalid_reasoning", "Reasoning level is invalid")
    return CreateConversationRequest(binding, saved_directory, model, reasoning)


def _parse_prompt(body: dict[str, Any], encoded_size: int) -> PromptInput:
    text = _validate_utf8_scalar(
        body["text"],
        code="invalid_prompt",
        label="Prompt text",
        max_bytes=MAX_USER_TEXT_BYTES,
    )
    images = body["images"]
    if not isinstance(images, list) or not all(isinstance(item, dict) for item in images):
        raise _HttpContractError("invalid_image", "Images must be objects")
    normalized = []
    for image in images:
        if set(image) != {"fileName", "mimeType", "base64Data"}:
            raise _HttpContractError("invalid_image", "Image keys are invalid")
        file_name = _validate_utf8_scalar(
            image["fileName"],
            code="invalid_image",
            label="Image file name",
            max_bytes=MAX_IMAGE_FILE_NAME_UTF8_BYTES,
        )
        normalized.append(
            {
                "file_name": file_name,
                "mime_type": image["mimeType"],
                "base64_data": image["base64Data"],
            }
        )
    return PromptInput(text, validate_images(normalized, encoded_http_body_bytes=encoded_size))


class _HttpPresentationSink:
    def __init__(self, response: web.StreamResponse) -> None:
        self._response = response
        self._prepared = asyncio.Event()
        self._failed = False
        self._supervisor = None

    def attach(self, supervisor) -> None:
        self._supervisor = supervisor

    def mark_prepared(self) -> None:
        self._prepared.set()

    async def write(self, event: ProjectedEvent) -> None:
        await self._prepared.wait()
        if event.kind == "agent_message_chunk":
            payload = {
                "type": "text_delta",
                "sourceOrdinal": event.source_ordinal,
                "messageId": event.message_id,
                "text": event.text,
            }
        elif event.kind == "agent_thought_chunk":
            payload = {
                "type": "thought_delta",
                "sourceOrdinal": event.source_ordinal,
                "messageId": event.message_id,
                "text": event.text,
            }
        elif event.kind in {"tool_call", "tool_call_update"}:
            payload = {
                "type": "tool_update",
                "sourceOrdinal": event.source_ordinal,
                "kind": event.kind,
                "messageId": event.message_id,
                "text": event.text,
                "payload": event.payload,
            }
        else:
            # Session/configuration metadata is not an in-progress tool. The
            # ACP callback has already observed it; omit it from panel cards.
            return
        try:
            await self._response.write(_ndjson(payload))
        except (ConnectionResetError, ConnectionError):
            self._failed = True
            if self._supervisor is not None:
                self._supervisor.request_cancel("http_stream")
            raise

    async def drain(self, deadline_seconds: float) -> bool:
        del deadline_seconds
        return not self._failed


def _ndjson(payload: dict[str, object]) -> bytes:
    return (json.dumps(payload, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


async def handle_health(request: web.Request) -> web.Response:
    return web.json_response(
        {
            "service": {
                "status": "ok",
                "version": SERVICE_VERSION,
                "host": CHAT_SERVER_BIND_HOST,
                "port": request.app[_PORT_STATE_KEY]["value"],
                "pid": os.getpid(),
                "owner": request.app[_OWNER_KEY],
                "rhinoProcessId": request.app[_RHINO_PROCESS_ID_KEY],
            },
            "runtime": {"available": request.app[_RUNTIME_AVAILABLE_KEY]},
            "authentication": {"owner": "Prime", "disclosure": "Prime-managed"},
        }
    )


async def handle_list(request: web.Request) -> web.Response:
    try:
        records = request.app[_ACP_MANAGER_KEY].store.list()
        return web.json_response({"conversations": [_association_payload(item) for item in records]})
    except Exception as exc:
        return _exception_response(exc)


async def handle_create(request: web.Request) -> web.Response:
    try:
        body = await _read_json_object(
            request,
            required=frozenset({"profile", "hostGenerationId", "documentSerialNumber", "routeProcessId"}),
            allowed=frozenset(
                {
                    "profile",
                    "hostGenerationId",
                    "documentSerialNumber",
                    "routeProcessId",
                    "savedDocumentDirectory",
                    "model",
                    "reasoning",
                }
            ),
        )
        view = await request.app[_ACP_MANAGER_KEY].create(_parse_create(body))
        return web.json_response(_view_payload(view), status=201)
    except Exception as exc:
        return _exception_response(exc)


async def handle_reopen(request: web.Request) -> web.Response:
    try:
        conversation_id = _conversation_id(request)
        await _read_json_object(request, required=frozenset(), allowed=frozenset())
        return web.json_response(
            _view_payload(await request.app[_ACP_MANAGER_KEY].reopen(conversation_id))
        )
    except Exception as exc:
        return _exception_response(exc)


async def handle_history(request: web.Request) -> web.Response:
    try:
        conversation_id = _conversation_id(request)
        manager = request.app[_ACP_MANAGER_KEY]
        manager.store.get(conversation_id)
        history = PresentationCache(manager.store.paths.presentation_path(conversation_id)).load()
        return web.json_response(
            {
                "available": history.available,
                "turns": list(history.turns),
                "earlierHistoryOmitted": history.earlier_history_omitted,
                "message": history.message,
            }
        )
    except Exception as exc:
        return _exception_response(exc)


async def handle_prompt(request: web.Request) -> web.StreamResponse | web.Response:
    supervisor = None
    response = web.StreamResponse(
        status=200,
        headers={
            "Content-Type": "application/x-ndjson",
            "Cache-Control": "no-store",
            **_CORS_HEADERS,
        },
    )
    sink = _HttpPresentationSink(response)
    try:
        conversation_id = _conversation_id(request)
        body = await _read_json_object(
            request,
            required=frozenset({"text", "images"}),
            allowed=frozenset({"text", "images"}),
        )
        prompt = _parse_prompt(body, request.content_length or 0)
        supervisor = await request.app[_ACP_MANAGER_KEY].start_prompt(conversation_id, prompt, sink)
        sink.attach(supervisor)
        try:
            await response.prepare(request)
            sink.mark_prepared()
        except BaseException:
            supervisor.request_cancel("http_prepare")
            raise
        result = await asyncio.shield(supervisor.result_task)
        await response.write(
            _ndjson(
                {
                    "type": "terminal",
                    "outcome": result.outcome,
                    "stopReason": result.stop_reason,
                    "presentationOutcome": result.presentation_outcome,
                    "cachePublished": result.cache_published,
                }
            )
        )
        with contextlib.suppress(ConnectionResetError, ConnectionError):
            await response.write_eof()
        return response
    except (asyncio.CancelledError, ConnectionResetError, ConnectionError):
        if supervisor is not None:
            supervisor.request_cancel("http_waiter")
        raise
    except Exception as exc:
        if supervisor is not None:
            supervisor.request_cancel("http_error")
        if response.prepared:
            with contextlib.suppress(ConnectionResetError, ConnectionError):
                code, _ = _classified_error(exc)
                await response.write(_ndjson({"type": "terminal", "outcome": "error", "errorCode": code}))
                await response.write_eof()
            return response
        return _exception_response(exc)


async def handle_cancel(request: web.Request) -> web.Response:
    try:
        conversation_id = _conversation_id(request)
        await _read_json_object(request, required=frozenset(), allowed=frozenset())
        accepted = await request.app[_ACP_MANAGER_KEY].request_cancel(conversation_id, "http_cancel")
        return web.json_response({"accepted": accepted})
    except Exception as exc:
        return _exception_response(exc)


async def handle_close(request: web.Request) -> web.Response:
    try:
        conversation_id = _conversation_id(request)
        await _read_json_object(request, required=frozenset(), allowed=frozenset())
        result = await request.app[_ACP_MANAGER_KEY].close(conversation_id)
        return web.json_response(
            {"outcome": result.outcome, "childExitObserved": result.child_exit_observed}
        )
    except Exception as exc:
        return _exception_response(exc)


async def handle_delete(request: web.Request) -> web.Response:
    try:
        conversation_id = _conversation_id(request)
        result = await request.app[_ACP_MANAGER_KEY].delete(conversation_id)
        return web.json_response(
            {
                "associationRemoved": result.association_removed,
                "artifactsRemoved": result.artifacts_removed,
            }
        )
    except Exception as exc:
        return _exception_response(exc)


_knowledge_store = None
_command_knowledge_store = None


def _get_knowledge_store():
    global _knowledge_store
    if _knowledge_store is None:
        from ...learning.unified_store import UnifiedStore

        _knowledge_store = UnifiedStore()
    return _knowledge_store


def _get_command_knowledge_store():
    global _command_knowledge_store
    if _command_knowledge_store is None:
        from ...learning.command_knowledge_store import CommandKnowledgeStore

        _command_knowledge_store = CommandKnowledgeStore()
    return _command_knowledge_store


async def handle_knowledge_graph(request: web.Request) -> web.Response:
    from .knowledge_graph_export import build_knowledge_graph_payload

    return web.json_response(
        build_knowledge_graph_payload(_get_knowledge_store(), _get_command_knowledge_store())
    )


async def handle_knowledge_note(request: web.Request) -> web.Response:
    from .knowledge_graph_export import build_command_detail_payload, build_note_detail_payload

    note_id = request.match_info["note_id"]
    if note_id.startswith("cmd_"):
        payload = build_command_detail_payload(note_id, _get_command_knowledge_store())
    else:
        payload = build_note_detail_payload(_get_knowledge_store(), note_id)
    if payload is None:
        return _error_response("note_not_found", "Note not found", 404)
    return web.json_response(payload)


def register_chat_routes(app: web.Application) -> None:
    app.router.add_get("/agent/chat/health", handle_health)
    app.router.add_get("/agent/chat/conversations", handle_list)
    app.router.add_post("/agent/chat/conversations", handle_create)
    app.router.add_post("/agent/chat/conversations/{conversation_id}/reopen", handle_reopen)
    app.router.add_get("/agent/chat/conversations/{conversation_id}/history", handle_history)
    app.router.add_post("/agent/chat/conversations/{conversation_id}/prompt", handle_prompt)
    app.router.add_post("/agent/chat/conversations/{conversation_id}/cancel", handle_cancel)
    app.router.add_post("/agent/chat/conversations/{conversation_id}/close", handle_close)
    app.router.add_delete("/agent/chat/conversations/{conversation_id}", handle_delete)


def register_knowledge_routes(app: web.Application) -> None:
    app.router.add_get("/knowledge/graph", handle_knowledge_graph)
    app.router.add_get("/knowledge/note/{note_id}", handle_knowledge_note)


async def _shutdown_manager(app: web.Application) -> None:
    await app[_ACP_MANAGER_KEY].shutdown()


def create_chat_app(
    manager: AcpConversationManager,
    *,
    expected_nonce: str | None = None,
    port: int = 0,
    owner: str = "external",
    rhino_process_id: int = 0,
    runtime_available: bool = True,
) -> web.Application:
    app = web.Application(
        middlewares=[cors_and_session_middleware], client_max_size=MAX_HTTP_BODY_BYTES
    )
    app[_ACP_MANAGER_KEY] = manager
    app[_PORT_STATE_KEY] = {"value": port}
    app[_OWNER_KEY] = owner
    app[_RHINO_PROCESS_ID_KEY] = rhino_process_id
    app[_RUNTIME_AVAILABLE_KEY] = runtime_available
    nonce = expected_nonce if expected_nonce is not None else os.environ.get(NONCE_ENV_VAR, "")
    if nonce:
        app[_SESSION_NONCE_KEY] = nonce
    register_chat_routes(app)
    register_knowledge_routes(app)
    app.on_cleanup.append(_shutdown_manager)
    return app


_server_task: asyncio.Task | None = None
_app_runner: web.AppRunner | None = None
_discovery_path: Path | None = None
_startup_future: asyncio.Future | None = None


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f"{path.name}.", suffix=".tmp", dir=path.parent, text=True
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as temporary:
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise


def _write_discovery_file(port: int, owner: str, rhino_process_id: int) -> Path:
    DISCOVERY_FOLDER.mkdir(parents=True, exist_ok=True)
    path = DISCOVERY_FOLDER / f"{DISCOVERY_FILE_PREFIX}{port}.json"
    _atomic_write_text(
        path,
        json.dumps(
            {
                "service": "agent-chat",
                "host": CHAT_SERVER_BIND_HOST,
                "port": port,
                "pid": os.getpid(),
                "version": SERVICE_VERSION,
                "owner": owner,
                "rhinoProcessId": rhino_process_id,
                "startTime": datetime.now().isoformat(timespec="seconds"),
            },
            indent=2,
        ),
    )
    return path


def _remove_discovery_file(path: Path | None) -> None:
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.debug("Could not remove chat discovery file %s", path)


async def start_chat_server(
    manager: AcpConversationManager | None = None,
    *,
    port: int = 0,
    include_gh_health: bool = False,
    owner: str = "external",
    rhino_process_id: int = 0,
    expected_nonce: str | None = None,
    prime_base_environment: dict[str, str] | None = None,
) -> None:
    global _server_task, _app_runner, _discovery_path, _startup_future
    del include_gh_health
    if _server_task is not None:
        if _startup_future is not None:
            await _startup_future
        return

    if manager is None:
        from .service_main import build_acp_manager

        manager, runtime_available = build_acp_manager(prime_base_environment or {})
    else:
        runtime_available = True

    async def run() -> None:
        global _app_runner, _discovery_path, _startup_future
        app = create_chat_app(
            manager,
            expected_nonce=expected_nonce,
            port=port,
            owner=owner,
            rhino_process_id=rhino_process_id,
            runtime_available=runtime_available,
        )
        runner = web.AppRunner(app, handler_cancellation=True)
        _app_runner = runner
        await runner.setup()
        try:
            site = web.TCPSite(runner, CHAT_SERVER_BIND_HOST, port)
            await site.start()
            sockets = getattr(getattr(site, "_server", None), "sockets", None)
            if not sockets:
                raise RuntimeError("Chat server started without an accessible bound socket")
            selected_port = int(sockets[0].getsockname()[1])
            app[_PORT_STATE_KEY]["value"] = selected_port
            _discovery_path = _write_discovery_file(selected_port, owner, rhino_process_id)
            if _startup_future is not None and not _startup_future.done():
                _startup_future.set_result(selected_port)
        except Exception as exc:
            await runner.cleanup()
            _app_runner = None
            if _startup_future is not None and not _startup_future.done():
                _startup_future.set_exception(exc)
            raise
        try:
            while True:
                await asyncio.sleep(3600)
        finally:
            _remove_discovery_file(_discovery_path)
            _discovery_path = None
            await runner.cleanup()
            _app_runner = None

    _startup_future = asyncio.get_running_loop().create_future()
    _server_task = asyncio.create_task(run())
    await _startup_future


async def wait_for_chat_server() -> None:
    if _server_task is None:
        raise RuntimeError("Chat server is not running")
    await _server_task


async def stop_chat_server() -> None:
    global _server_task, _discovery_path, _startup_future
    if _server_task is not None:
        _server_task.cancel()
        try:
            await _server_task
        except (asyncio.CancelledError, Exception):
            pass
        _server_task = None
    _startup_future = None
    _remove_discovery_file(_discovery_path)
    _discovery_path = None
