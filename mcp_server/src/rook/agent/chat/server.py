"""Agent Chat HTTP Server."""
import asyncio
import json
import logging
import os
import tempfile
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from aiohttp import web

from ...bridge import rhino_request_context
from ...providers.vertex_auth import VertexAuthError
from ...providers.vertex_token_lease import (
    VERTEX_IMAGE_LOCATION,
    VERTEX_IMAGE_MODEL_KEY,
    VertexTokenLease,
    VertexTokenLeaseService,
)
from .conversation_store import ConversationStore
from .prompt_builder import PromptBuilder
from .chat_runner import ChatEvent, ChatRunner
from . import model_status
from .runtime_health import collect_runtime_facts

from ..personas import available_personas, load_display_config

logger = logging.getLogger(__name__)

CHAT_SERVER_BIND_HOST = "127.0.0.1"
DISCOVERY_FOLDER = Path(tempfile.gettempdir()) / "rook"
DISCOVERY_FILE_PREFIX = "chat-service-"
SERVICE_VERSION = "1.0.0"

# Virtual host origin for WebView2 surfaces.  .invalid is reserved by
# RFC 6761 and will never resolve externally.
ALLOWED_ORIGIN = "https://app.rook.invalid"
SESSION_HEADER = "X-Rook-Session"
NONCE_ENV_VAR = "ROOK_SESSION_NONCE"

# Typed app keys (avoids aiohttp NotAppKeyWarning)
_STORE_KEY: web.AppKey[ConversationStore] = web.AppKey("_store", ConversationStore)
_BUILDER_KEY: web.AppKey[PromptBuilder] = web.AppKey("_builder", PromptBuilder)
_RUNNER_KEY: web.AppKey[ChatRunner] = web.AppKey("_runner", ChatRunner)
_PORT_STATE_KEY: web.AppKey[dict[str, int]] = web.AppKey("_port_state", dict)
_INCLUDE_GH_HEALTH_KEY: web.AppKey[bool] = web.AppKey("_include_gh_health", bool)
_OWNER_KEY: web.AppKey[str] = web.AppKey("_owner", str)
_RHINO_PROCESS_ID_KEY: web.AppKey[int] = web.AppKey("_rhino_process_id", int)
_SESSION_NONCE_KEY: web.AppKey[str] = web.AppKey("_session_nonce", str)
_WORKER_FIRST_APPLICATION_KEY: web.AppKey[object] = web.AppKey(
    "_worker_first_application", object
)
_VERTEX_TOKEN_SERVICE_KEY: web.AppKey[VertexTokenLeaseService] = web.AppKey(
    "_vertex_token_service", VertexTokenLeaseService
)

_WORKER_FIRST_CSHARP_MODE = "worker_first_csharp_v1"
_MAX_WORKER_FIRST_INTENT_BYTES = 16_384
_VERTEX_INTERNAL_TOKEN_PATH = "/internal/providers/vertex/access-token"
_VERTEX_INTERNAL_MESSAGES = {
    "vertex_internal_access_denied": (
        "The internal Vertex token route is unavailable to this caller."
    ),
    "vertex_internal_method_not_allowed": (
        "The internal Vertex token route accepts POST requests only."
    ),
    "vertex_internal_request_invalid": "The internal Vertex token request is invalid.",
    "vertex_image_model_unsupported": "The selected Vertex image model is unsupported.",
    "vertex_model_region_unsupported": (
        "Vertex AI Nano Banana 2 requires the global location."
    ),
    "vertex_signed_out": "Vertex AI is not configured for this Windows user.",
    "vertex_authorization_revoked": "Google authorization must be renewed.",
    "vertex_adc_unavailable": "Application Default Credentials are unavailable.",
    "vertex_service_account_unavailable": (
        "The selected service account is unavailable."
    ),
    "vertex_request_failed": (
        "Vertex authorization is unavailable because its local configuration is invalid."
    ),
    "vertex_authorization_changed": (
        "Vertex authorization changed during token issuance."
    ),
    "vertex_auth_dependency_missing": (
        "The installed Google authorization dependency is unavailable."
    ),
    "vertex_token_issuance_timeout": "Vertex token issuance timed out.",
    "vertex_token_issuance_failed": "Vertex token issuance failed.",
}
_VERTEX_INTERNAL_STATUSES = {
    "vertex_image_model_unsupported": 400,
    "vertex_model_region_unsupported": 400,
    "vertex_signed_out": 409,
    "vertex_authorization_revoked": 409,
    "vertex_adc_unavailable": 409,
    "vertex_service_account_unavailable": 409,
    "vertex_request_failed": 409,
    "vertex_authorization_changed": 409,
    "vertex_auth_dependency_missing": 503,
    "vertex_token_issuance_timeout": 504,
}

# Module-level singletons (initialized on first request or at startup)
_store: Optional[ConversationStore] = None
_builder: Optional[PromptBuilder] = None
_runner: Optional[ChatRunner] = None


def _get_store() -> ConversationStore:
    global _store
    if _store is None:
        _store = ConversationStore()
    return _store


def _get_builder() -> PromptBuilder:
    global _builder
    if _builder is None:
        _builder = PromptBuilder()
    return _builder


def _get_runner() -> ChatRunner:
    global _runner
    if _runner is None:
        from ...server import build_mcp_capability_gateway_executor

        tool_access = "full"
        _runner = ChatRunner(
            tool_access=tool_access,
            mcp_capability_executor=(
                build_mcp_capability_gateway_executor(tool_access)
            ),
        )
    return _runner


def _get_worker_first_application(
    request: web.Request,
) -> Callable[[str], Awaitable[Any]]:
    injected = request.app.get(_WORKER_FIRST_APPLICATION_KEY)
    if injected is not None:
        if not callable(injected):
            raise TypeError("Worker-first application must be callable")
        return injected
    from ..worker_first_csharp_application import run_worker_first_csharp_application

    return run_worker_first_csharp_application


def _run_worker_first_application_sync(
    application: Callable[[str], Awaitable[Any]],
    intent: str,
) -> Any:
    return asyncio.run(application(intent))


def _worker_first_failure_projection() -> dict[str, object]:
    return {
        "status": "failed",
        "terminal_stage": None,
        "terminal_reason": None,
        "compile_status": "unavailable",
        "error_count": None,
        "warning_count": None,
        "component_created": None,
    }


_SAFE_NATIVE_STAGES = frozenset(
    {
        "planner_adapter",
        "draft_admission",
        "worker_adapter",
        "worker_disposition",
        "action_apply",
        "create",
        "verify_create",
        "terminal",
    }
)
_SAFE_NATIVE_REASONS = frozenset(
    {
        "transport_failed",
        "response_not_string",
        "response_not_utf8",
        "response_duplicate_key",
        "response_nonfinite_number",
        "response_trailing_content",
        "response_not_object",
        "response_invalid_json",
        "response_too_large",
        "draft_payload_rejected",
        "goal_mismatch",
        "transport_error:declared",
        "transport_error:unexpected",
        "raw_output_invalid:not_text",
        "raw_output_invalid:empty",
        "raw_output_invalid:json_decode",
        "raw_output_invalid:not_mapping",
        "response_payload_invalid:unclassified",
        "invalid_template",
        "unknown_node",
        "invalid_tool_ref",
        "invalid_action_id",
        "invalid_action_input",
        "unexpected_action_input_key",
        "missing_code",
        "invalid_code",
        "invalid_execution_params",
        "code_already_present",
        "execution_params_shape_mismatch",
        "graph_copy_failed",
        "dispatch_failed",
        "selector_halt:none_ready",
        "terminal_node_selected:done",
    }
)


def _safe_native_token(value: object, allowed: frozenset[str]) -> str | None:
    if value is None:
        return None
    if type(value) is str and value in allowed:
        return value
    return "native_reason_unclassified"


def _owned_create_receipt(result: Any) -> tuple[dict[str, Any] | None, bool | None]:
    from ..minimal_intent_worker_integration import (
        MinimalIntentWorkerInitialBodyIntegrationResult,
    )

    if type(result) is not MinimalIntentWorkerInitialBodyIntegrationResult:
        raise TypeError("Worker-first application returned an invalid result")
    handoff = result.handoff_result
    if handoff is None:
        return None, False
    producer_records = [
        record
        for record in handoff.step_records
        if record.execution_kind == "producer"
        and record.producer_node_id == "create_script"
    ]
    if not producer_records:
        return None, False
    if len(producer_records) != 1:
        raise ValueError("Worker-first result has multiple create records")
    record = producer_records[0]
    node = record.execution.graph.nodes.get("create_script")
    evidence = None if node is None else node.evidence
    receipt = None if evidence is None else evidence.receipt
    if receipt is None:
        return None, None
    if type(receipt) is not dict:
        return None, None
    return receipt, None


def _project_worker_first_result(result: Any) -> dict[str, object]:
    receipt, creation_without_receipt = _owned_create_receipt(result)
    terminal_stage = _safe_native_token(result.terminal_stage, _SAFE_NATIVE_STAGES)
    terminal_reason = _safe_native_token(result.terminal_reason, _SAFE_NATIVE_REASONS)
    compile_status = "unavailable"
    error_count: int | None = None
    warning_count: int | None = None
    component_created = creation_without_receipt

    if receipt is not None:
        mutation = receipt.get("mutation")
        mutation_status = (
            mutation.get("status") if type(mutation) is dict else None
        )
        if type(mutation_status) is str and mutation_status == "created":
            component_created = True
        elif type(mutation_status) is str and mutation_status in {
            "failed",
            "not_attempted",
        }:
            component_created = False
        else:
            component_created = None

        verification = receipt.get("verification")
        verification_status = (
            verification.get("status") if type(verification) is dict else None
        )
        raw_errors = (
            verification.get("target_error_count")
            if type(verification) is dict
            else None
        )
        raw_warnings = (
            verification.get("target_warning_count")
            if type(verification) is dict
            else None
        )
        counts_are_exact = (
            type(raw_errors) is int
            and raw_errors >= 0
            and type(raw_warnings) is int
            and raw_warnings >= 0
        )
        if (
            type(verification_status) is str
            and verification_status in {"passed", "failed"}
            and counts_are_exact
        ):
            compile_status = verification_status
            error_count = raw_errors
            warning_count = raw_warnings

    succeeded = (
        terminal_stage == "terminal"
        and terminal_reason == "terminal_node_selected:done"
        and component_created is True
        and compile_status == "passed"
        and error_count == 0
        and warning_count == 0
    )
    return {
        "status": "success" if succeeded else "failed",
        "terminal_stage": terminal_stage,
        "terminal_reason": terminal_reason,
        "compile_status": compile_status,
        "error_count": error_count,
        "warning_count": warning_count,
        "component_created": component_created,
    }


async def _write_chat_event(
    response: web.StreamResponse,
    event: ChatEvent,
) -> None:
    line = json.dumps(event.to_dict(), separators=(",", ":")) + "\n"
    await response.write(line.encode("utf-8"))


def _complete_deferred_worker_first_run(task: asyncio.Task, conv, run_id: str) -> None:
    try:
        task.result()
    except asyncio.CancelledError:
        logger.info("Worker-first application task ended canceled")
    except Exception:
        logger.info("Worker-first application task ended with a bounded failure")
    finally:
        if conv.active_run_id == run_id:
            conv.active_run_id = None
            conv.touch()


async def _handle_worker_first_message(
    request: web.Request,
    conv,
    intent: str,
) -> web.StreamResponse:
    response = web.StreamResponse(
        status=200,
        reason="OK",
        headers={
            "Content-Type": "application/x-ndjson",
            "Cache-Control": "no-cache",
        },
    )
    run_id = uuid.uuid4().hex
    tool_call_id = f"{_WORKER_FIRST_CSHARP_MODE}:{run_id}"
    conv.active_run_id = run_id
    conv.abort_event.clear()
    conv.touch()
    deferred_cleanup = False
    application_task: asyncio.Task | None = None
    try:
        await response.prepare(request)
        await _write_chat_event(
            response,
            ChatEvent(
                "tool_start",
                name=_WORKER_FIRST_CSHARP_MODE,
                tool_call_id=tool_call_id,
            ),
        )
        try:
            application = _get_worker_first_application(request)
            with rhino_request_context(
                process_id=request.app.get(_RHINO_PROCESS_ID_KEY, 0),
                document_serial_number=conv.document_serial_number,
            ):
                application_task = asyncio.create_task(
                    asyncio.to_thread(
                        _run_worker_first_application_sync,
                        application,
                        intent,
                    )
                )
            try:
                result = await asyncio.shield(application_task)
            except asyncio.CancelledError:
                conv.abort_event.set()
                deferred_cleanup = True
                application_task.add_done_callback(
                    lambda completed: _complete_deferred_worker_first_run(
                        completed,
                        conv,
                        run_id,
                    )
                )
                return response
            projection = _project_worker_first_result(result)
        except Exception:
            projection = _worker_first_failure_projection()
        await _write_chat_event(
            response,
            ChatEvent(
                "tool_result",
                name=_WORKER_FIRST_CSHARP_MODE,
                tool_call_id=tool_call_id,
                result=json.dumps(projection, separators=(",", ":")),
                tool_status=projection["status"],
                verified=projection["status"] == "success",
            ),
        )
        await _write_chat_event(response, ChatEvent("done", usage={}))
        conv.touch()
    except (ConnectionResetError, ConnectionError, asyncio.CancelledError):
        conv.abort_event.set()
        if (
            application_task is not None
            and not application_task.done()
            and not deferred_cleanup
        ):
            deferred_cleanup = True
            application_task.add_done_callback(
                lambda completed: _complete_deferred_worker_first_run(
                    completed,
                    conv,
                    run_id,
                )
            )
        return response
    finally:
        if not deferred_cleanup and conv.active_run_id == run_id:
            conv.active_run_id = None
    try:
        await response.write_eof()
    except (ConnectionResetError, ConnectionError):
        pass
    return response


# --- CORS + Session Auth Middleware ---

_CORS_HEADERS = {
    "Access-Control-Allow-Origin": ALLOWED_ORIGIN,
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": f"Content-Type, {SESSION_HEADER}",
}


@web.middleware
async def cors_and_session_middleware(request: web.Request, handler):
    """Enforce origin allowlist and session nonce on all routes.

    The WebView2 chat surface loads from https://app.rook.invalid (a virtual
    host backed by embedded resources).  CORS is hygiene — it constrains
    browser behavior.  The session nonce (X-Rook-Session) is the real gate
    — it proves the caller was initialized by the C# host.

    Health endpoint is exempt from nonce checks to allow the C# host to
    poll during startup before the nonce is configured in the WebView.
    """
    if request.path == _VERTEX_INTERNAL_TOKEN_PATH:
        if "Origin" in request.headers:
            return _vertex_internal_failure("vertex_internal_access_denied", 403)
        expected_nonce = request.app.get(_SESSION_NONCE_KEY, "")
        provided_nonce = request.headers.get(SESSION_HEADER, "")
        if not expected_nonce or provided_nonce != expected_nonce:
            return _vertex_internal_failure("vertex_internal_access_denied", 403)
        if request.method != "POST":
            return _vertex_internal_failure(
                "vertex_internal_method_not_allowed",
                405,
                headers={"Allow": "POST"},
            )
        return await handler(request)

    # Handle CORS preflight for all routes
    if request.method == "OPTIONS":
        return web.Response(status=204, headers=_CORS_HEADERS)

    # Reject browser requests from unexpected origins.  Non-browser callers
    # (C# HttpClient, agents) don't send Origin, so absence is allowed —
    # the nonce gate covers those callers.
    origin = request.headers.get("Origin")
    if origin is not None and origin != ALLOWED_ORIGIN:
        return web.json_response(
            {"error": f"Origin '{origin}' not allowed"},
            status=403,
            headers=_CORS_HEADERS,
        )

    # Check session nonce (skip for health — needed during startup polling).
    # Exact path match prevents accidental exemption of future /*/health routes.
    expected_nonce = request.app.get(_SESSION_NONCE_KEY, "")
    if expected_nonce and request.path != "/agent/chat/health":
        provided = request.headers.get(SESSION_HEADER, "")
        if provided != expected_nonce:
            return web.json_response(
                {"error": "Missing or invalid session token"},
                status=403,
                headers=_CORS_HEADERS,
            )

    # Call the actual handler
    response = await handler(request)

    # Add CORS headers to all responses
    for key, value in _CORS_HEADERS.items():
        response.headers[key] = value

    return response


# --- Handlers ---


def _vertex_internal_failure(
    code: str,
    status: int,
    *,
    headers: dict[str, str] | None = None,
) -> web.Response:
    response_headers = {"Cache-Control": "no-store"}
    if headers:
        response_headers.update(headers)
    return web.json_response(
        {
            "success": False,
            "error": {
                "code": code,
                "message": _VERTEX_INTERNAL_MESSAGES[code],
            },
        },
        status=status,
        headers=response_headers,
    )


def _vertex_internal_success(lease: VertexTokenLease) -> web.Response:
    return web.json_response(
        {
            "success": True,
            "data": {
                "access_token": lease.access_token,
                "expires_at_unix_seconds": lease.expires_at_unix_seconds,
                "project_id": lease.project_id,
                "location": lease.location,
                "generation": lease.generation,
            },
        },
        headers={"Cache-Control": "no-store"},
    )


async def handle_vertex_internal_access_token(request: web.Request) -> web.Response:
    try:
        payload = await request.json()
    except (
        web.HTTPRequestEntityTooLarge,
        json.JSONDecodeError,
        UnicodeDecodeError,
        ValueError,
    ):
        return _vertex_internal_failure("vertex_internal_request_invalid", 400)
    if not isinstance(payload, dict) or set(payload) != {"model"}:
        return _vertex_internal_failure("vertex_internal_request_invalid", 400)
    model = payload.get("model")
    if not isinstance(model, str):
        return _vertex_internal_failure("vertex_internal_request_invalid", 400)
    if model != VERTEX_IMAGE_MODEL_KEY:
        return _vertex_internal_failure("vertex_image_model_unsupported", 400)

    try:
        lease = await request.app[_VERTEX_TOKEN_SERVICE_KEY].acquire(model)
    except asyncio.CancelledError:
        raise
    except VertexAuthError as exc:
        status = _VERTEX_INTERNAL_STATUSES.get(exc.code)
        if status is None:
            return _vertex_internal_failure("vertex_token_issuance_failed", 500)
        return _vertex_internal_failure(exc.code, status)
    except Exception:
        return _vertex_internal_failure("vertex_token_issuance_failed", 500)

    if (
        not isinstance(lease, VertexTokenLease)
        or not isinstance(lease.access_token, str)
        or not lease.access_token
        or type(lease.expires_at_unix_seconds) is not int
        or lease.expires_at_unix_seconds <= time.time()
        or not isinstance(lease.project_id, str)
        or not lease.project_id
        or lease.location != VERTEX_IMAGE_LOCATION
        or not isinstance(lease.generation, str)
        or not lease.generation
    ):
        return _vertex_internal_failure("vertex_token_issuance_failed", 500)
    return _vertex_internal_success(lease)


async def handle_personas(request: web.Request) -> web.Response:
    """GET /agent/chat/personas — list available agent personas."""
    personas = available_personas()
    result = []
    for p in personas:
        config = load_display_config(p)
        result.append({
            "persona": p,
            "label": config.get("label", p),
            "description": config.get("description", ""),
            "color": config.get("color", "#1d9bf0"),
            "model_role": config.get("model_role", "worker"),
        })
    return web.json_response(result)


async def handle_models(request: web.Request) -> web.Response:
    """GET /agent/chat/models — report active model routing and local models."""
    builder = request.app.get(_BUILDER_KEY) or _get_builder()
    payload = await model_status.build_models_payload(builder=builder)

    conv_id = request.query.get("conversation_id")
    if conv_id:
        store = request.app.get(_STORE_KEY) or _get_store()
        conv = store.get(conv_id)
        if conv is None:
            return web.json_response(
                {"error": "Conversation not found"},
                status=404,
                headers={
                    "Cache-Control": "no-store",
                    "Pragma": "no-cache",
                    "Expires": "0",
                },
            )
        payload = {
            **payload,
            "conversation": model_status.build_conversation_model_status(conv),
        }

    return web.json_response(
        payload,
        headers={
            "Cache-Control": "no-store",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


async def handle_health(request: web.Request) -> web.Response:
    """GET /agent/chat/health — service and Rhino bridge health."""
    include_gh = request.app.get(_INCLUDE_GH_HEALTH_KEY, False)
    runtime = await collect_runtime_facts(include_gh=include_gh)
    port_state = request.app.get(_PORT_STATE_KEY, {"value": 0})
    return web.json_response(
        {
            "service": {
                "ok": True,
                "version": SERVICE_VERSION,
                "host": CHAT_SERVER_BIND_HOST,
                "port": port_state.get("value", 0),
                "pid": os.getpid(),
                "owner": request.app.get(_OWNER_KEY, "external"),
                "rhinoProcessId": request.app.get(_RHINO_PROCESS_ID_KEY, 0),
            },
            "runtime": runtime,
        }
    )


async def handle_start(request: web.Request) -> web.Response:
    """POST /agent/chat/start — create a new conversation."""
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    persona = body.get("persona", "worker")
    raw_document_serial_number = body.get("documentSerialNumber", 0) or 0
    try:
        document_serial_number = int(raw_document_serial_number)
    except (TypeError, ValueError):
        return web.json_response(
            {"error": "documentSerialNumber must be an integer"},
            status=400,
        )
    store = request.app.get(_STORE_KEY) or _get_store()
    builder = request.app.get(_BUILDER_KEY) or _get_builder()

    resolved_model, resolved_base = builder.resolve_model_and_base(persona)
    model_override = body.get("model_override")
    override_resolution = None
    if model_override:
        try:
            override_resolution = await model_status.resolve_allowed_model_override(
                model_override
            )
        except model_status.ModelOverrideUnavailable as exc:
            return web.json_response(exc.to_payload(), status=400)

    try:
        conv = store.create(persona, document_serial_number=document_serial_number)
    except RuntimeError as e:
        return web.json_response({"error": str(e)}, status=429)

    if override_resolution is not None:
        conv.apply_model_override(
            override_resolution,
            source="start_override",
            reason="model_override supplied to /agent/chat/start",
        )
    else:
        conv.model = resolved_model
        conv.api_base = resolved_base or ""
        conv.model_source = "persona"
        conv.api_base_source = "prompt_builder" if resolved_base else "none"
    display = builder.get_display_config(persona)

    return web.json_response({
        "conversation_id": conv.id,
        "persona": persona,
        "label": display.get("label", persona),
        "color": display.get("color", "#1d9bf0"),
        "model": conv.model,
        "tool_access": display.get("tool_access", "full"),
        "documentSerialNumber": conv.document_serial_number,
    })


async def handle_set_model(request: web.Request) -> web.Response:
    """POST /agent/chat/model — apply a validated model override."""

    def conversation_processing_response() -> web.Response:
        return web.json_response(
            {
                "error": "Conversation already processing. Try again after the current turn completes.",
                "code": "conversation_processing",
            },
            status=409,
        )

    try:
        body = await request.json()
    except json.JSONDecodeError:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    conv_id = body.get("conversation_id")
    model_override = body.get("model_override")
    if not conv_id or not model_override:
        return web.json_response(
            {"error": "Missing conversation_id or model_override"},
            status=400,
        )

    store = request.app.get(_STORE_KEY) or _get_store()
    conv = store.get(conv_id)
    if conv is None:
        return web.json_response({"error": "Conversation not found"}, status=404)

    if conv.active_run_id is not None:
        return conversation_processing_response()

    try:
        resolution = await model_status.resolve_allowed_model_override(model_override)
    except model_status.ModelOverrideUnavailable as exc:
        return web.json_response(exc.to_payload(), status=400)

    if conv.active_run_id is not None:
        return conversation_processing_response()

    payload = conv.apply_model_override(
        resolution,
        source="panel_endpoint",
        reason=str(body.get("reason") or ""),
    )
    payload["conversation_id"] = conv.id
    payload["persona"] = conv.persona
    return web.json_response(payload)


async def handle_message(request: web.Request) -> web.StreamResponse:
    """POST /agent/chat/message — send a message, stream response."""
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    conv_id = body.get("conversation_id")
    message = body.get("message", "")
    mode_supplied = "execution_mode" in body
    execution_mode = body.get("execution_mode")
    raw_document_serial_number = body.get("documentSerialNumber", 0) or 0

    if mode_supplied and (
        type(execution_mode) is not str
        or execution_mode != _WORKER_FIRST_CSHARP_MODE
    ):
        return web.json_response({"error": "Unsupported execution_mode"}, status=400)

    if execution_mode == _WORKER_FIRST_CSHARP_MODE:
        if type(message) is not str or not message or message != message.strip():
            return web.json_response({"error": "Invalid Worker-first message"}, status=400)
        try:
            encoded_message = message.encode("utf-8")
        except UnicodeEncodeError:
            return web.json_response({"error": "Invalid Worker-first message"}, status=400)
        if len(encoded_message) > _MAX_WORKER_FIRST_INTENT_BYTES:
            return web.json_response({"error": "Invalid Worker-first message"}, status=400)

    if not conv_id or not message:
        return web.json_response({"error": "Missing conversation_id or message"}, status=400)

    try:
        document_serial_number = int(raw_document_serial_number)
    except (TypeError, ValueError):
        return web.json_response(
            {"error": "documentSerialNumber must be an integer"},
            status=400,
        )

    store = request.app.get(_STORE_KEY) or _get_store()
    conv = store.get(conv_id)
    if conv is None:
        return web.json_response({"error": "Conversation not found"}, status=404)

    # Guard against concurrent requests on the same conversation
    if conv.active_run_id is not None:
        return web.json_response({"error": "Conversation already processing"}, status=409)

    if document_serial_number > 0:
        conv.document_serial_number = document_serial_number

    if execution_mode == _WORKER_FIRST_CSHARP_MODE:
        return await _handle_worker_first_message(request, conv, message)

    builder = request.app.get(_BUILDER_KEY) or _get_builder()
    runner = request.app.get(_RUNNER_KEY) or _get_runner()
    system_prompt = builder.build_system(conv.persona)

    async def model_payload_builder():
        return await model_status.build_models_payload(builder=builder)

    # Stream response using chunked transfer encoding
    response = web.StreamResponse(
        status=200,
        reason="OK",
        headers={
            "Content-Type": "application/x-ndjson",
            "Cache-Control": "no-cache",
        },
    )

    turn_events = None
    preparing_run_id = "server_preparing"
    try:
        conv.active_run_id = preparing_run_id
        await response.prepare(request)
        try:
            with rhino_request_context(
                process_id=request.app.get(_RHINO_PROCESS_ID_KEY, 0),
                document_serial_number=conv.document_serial_number,
            ):
                turn_events = runner.run_turn(
                    conv,
                    message,
                    system_prompt,
                    model_payload_builder=model_payload_builder,
                )
                async for event in turn_events:
                    line = json.dumps(event.to_dict()) + "\n"
                    await response.write(line.encode("utf-8"))
        except (ConnectionResetError, ConnectionError, asyncio.CancelledError):
            logger.info(f"Client disconnected during streaming for conversation {conv_id}")
            conv.abort_event.set()
        finally:
            if turn_events is not None:
                close = getattr(turn_events, "aclose", None)
                if close is not None:
                    await close()
    finally:
        if conv.active_run_id == preparing_run_id:
            conv.active_run_id = None

    try:
        await response.write_eof()
    except (ConnectionResetError, ConnectionError):
        pass
    return response


async def handle_ui_response(request: web.Request) -> web.StreamResponse:
    """POST /agent/chat/ui-response — receive structured input from a UI block
    and run an agent turn so the agent reacts to it in real time.

    Mirrors `handle_message`'s streaming shape: NDJSON events for the duration
    of `runner.run_turn`. The user's submission is serialized as
    `{type: ui_response, block_id, value}` and passed as the user_message to
    run_turn, which appends it to conversation history and runs the loop.
    """
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    conv_id = body.get("conversation_id")
    block_id = body.get("block_id")
    value = body.get("value")
    raw_document_serial_number = body.get("documentSerialNumber", 0) or 0

    if not conv_id or not block_id:
        return web.json_response(
            {"error": "Missing conversation_id or block_id"}, status=400
        )

    try:
        document_serial_number = int(raw_document_serial_number)
    except (TypeError, ValueError):
        return web.json_response(
            {"error": "documentSerialNumber must be an integer"},
            status=400,
        )

    store = request.app.get(_STORE_KEY) or _get_store()
    conv = store.get(conv_id)
    if conv is None:
        return web.json_response({"error": "Conversation not found"}, status=404)

    # Same concurrency guard as /message — reject if a turn is already running
    if conv.active_run_id is not None:
        return web.json_response(
            {"error": "Conversation already processing"}, status=409
        )

    if document_serial_number > 0:
        conv.document_serial_number = document_serial_number

    # Serialize the structured UI response as the user_message for run_turn.
    # run_turn appends it to conv.messages itself.
    user_message = json.dumps({
        "type": "ui_response",
        "block_id": block_id,
        "value": value,
    })

    builder = request.app.get(_BUILDER_KEY) or _get_builder()
    runner = request.app.get(_RUNNER_KEY) or _get_runner()
    system_prompt = builder.build_system(conv.persona)

    async def model_payload_builder():
        return await model_status.build_models_payload(builder=builder)

    response = web.StreamResponse(
        status=200,
        reason="OK",
        headers={
            "Content-Type": "application/x-ndjson",
            "Cache-Control": "no-cache",
        },
    )

    turn_events = None
    preparing_run_id = "server_preparing"
    try:
        conv.active_run_id = preparing_run_id
        await response.prepare(request)
        try:
            with rhino_request_context(
                process_id=request.app.get(_RHINO_PROCESS_ID_KEY, 0),
                document_serial_number=conv.document_serial_number,
            ):
                turn_events = runner.run_turn(
                    conv,
                    user_message,
                    system_prompt,
                    model_payload_builder=model_payload_builder,
                )
                async for event in turn_events:
                    line = json.dumps(event.to_dict()) + "\n"
                    await response.write(line.encode("utf-8"))
        except (ConnectionResetError, ConnectionError, asyncio.CancelledError):
            logger.info(
                f"Client disconnected during ui-response streaming for conversation {conv_id}"
            )
            conv.abort_event.set()
        finally:
            if turn_events is not None:
                close = getattr(turn_events, "aclose", None)
                if close is not None:
                    await close()
    finally:
        if conv.active_run_id == preparing_run_id:
            conv.active_run_id = None

    try:
        await response.write_eof()
    except (ConnectionResetError, ConnectionError):
        pass
    return response


async def handle_stop(request: web.Request) -> web.Response:
    """POST /agent/chat/stop — end a conversation."""
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    conv_id = body.get("conversation_id")
    if not conv_id:
        return web.json_response({"error": "Missing conversation_id"}, status=400)

    store = request.app.get(_STORE_KEY) or _get_store()
    if store.stop(conv_id):
        return web.json_response({"stopped": True})
    return web.json_response({"error": "Conversation not found"}, status=404)


# --- Knowledge Graph Handlers ---

_knowledge_store = None
_command_knowledge_store = None


def _get_knowledge_store():
    """Lazy-load the UnifiedStore for knowledge graph routes."""
    global _knowledge_store
    if _knowledge_store is None:
        from ...learning.unified_store import UnifiedStore
        _knowledge_store = UnifiedStore()
    return _knowledge_store


def _get_command_knowledge_store():
    """Lazy-load the CommandKnowledgeStore for knowledge graph routes."""
    global _command_knowledge_store
    if _command_knowledge_store is None:
        from ...learning.command_knowledge_store import CommandKnowledgeStore
        _command_knowledge_store = CommandKnowledgeStore()
    return _command_knowledge_store


async def handle_knowledge_graph(request: web.Request) -> web.Response:
    """GET /knowledge/graph — full graph payload for Cytoscape."""
    from .knowledge_graph_export import build_knowledge_graph_payload
    store = _get_knowledge_store()
    command_store = _get_command_knowledge_store()
    payload = build_knowledge_graph_payload(store, command_store)
    return web.json_response(payload)


async def handle_knowledge_note(request: web.Request) -> web.Response:
    """GET /knowledge/note/{note_id} — single note detail."""
    from .knowledge_graph_export import build_note_detail_payload, build_command_detail_payload
    note_id = request.match_info["note_id"]

    # Route cmd_* IDs to the command store
    if note_id.startswith("cmd_"):
        command_store = _get_command_knowledge_store()
        payload = build_command_detail_payload(note_id, command_store)
    else:
        store = _get_knowledge_store()
        payload = build_note_detail_payload(store, note_id)

    if payload is None:
        return web.json_response({"error": "Note not found"}, status=404)
    return web.json_response(payload)


# --- App Factory ---

def create_chat_app(
    store: Optional[ConversationStore] = None,
    builder: Optional[PromptBuilder] = None,
    runner: Optional[ChatRunner] = None,
    port: int = 0,
    include_gh_health: bool = False,
    owner: str = "external",
    rhino_process_id: int = 0,
    session_nonce: Optional[str] = None,
    worker_first_application: Optional[Callable[[str], Awaitable[Any]]] = None,
    vertex_token_service: Optional[VertexTokenLeaseService] = None,
) -> web.Application:
    """Create the aiohttp application for the chat server.

    Optional dependency injection for testing — pass store/builder/runner
    to avoid module-level singletons that persist across tests.

    ``session_nonce`` is the per-lifetime bearer token generated by the C#
    host.  When set, every route (except /health) requires it as the
    ``X-Rook-Session`` header.  Read from the ``ROOK_SESSION_NONCE`` env
    var by default if not passed explicitly.
    """
    nonce = session_nonce or os.environ.get(NONCE_ENV_VAR, "")
    app = web.Application(middlewares=[cors_and_session_middleware])

    # Store injected dependencies on app dict so handlers can find them
    if store is not None:
        app[_STORE_KEY] = store
    if builder is not None:
        app[_BUILDER_KEY] = builder
    if runner is not None:
        app[_RUNNER_KEY] = runner
    if worker_first_application is not None:
        app[_WORKER_FIRST_APPLICATION_KEY] = worker_first_application
    app[_VERTEX_TOKEN_SERVICE_KEY] = vertex_token_service or VertexTokenLeaseService()
    app[_PORT_STATE_KEY] = {"value": port}
    app[_INCLUDE_GH_HEALTH_KEY] = include_gh_health
    app[_OWNER_KEY] = owner
    app[_RHINO_PROCESS_ID_KEY] = rhino_process_id
    if nonce:
        app[_SESSION_NONCE_KEY] = nonce

    app.router.add_get("/agent/chat/health", handle_health)
    app.router.add_get("/agent/chat/personas", handle_personas)
    app.router.add_get("/agent/chat/models", handle_models)
    app.router.add_post("/agent/chat/start", handle_start)
    app.router.add_post("/agent/chat/model", handle_set_model)
    app.router.add_post("/agent/chat/message", handle_message)
    app.router.add_post("/agent/chat/stop", handle_stop)
    app.router.add_post("/agent/chat/ui-response", handle_ui_response)
    app.router.add_route(
        "*",
        _VERTEX_INTERNAL_TOKEN_PATH,
        handle_vertex_internal_access_token,
    )

    # Knowledge graph routes (WebUI module, same nonce/CORS middleware)
    app.router.add_get("/knowledge/graph", handle_knowledge_graph)
    app.router.add_get("/knowledge/note/{note_id}", handle_knowledge_note)
    return app


# --- Server Lifecycle ---

_server_task: Optional[asyncio.Task] = None
_app_runner: Optional[web.AppRunner] = None
_discovery_path: Optional[Path] = None
_startup_future: Optional[asyncio.Future] = None


def _atomic_write_text(path: Path, content: str) -> None:
    """Write text atomically via a temp file in the target directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f"{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        text=True,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
            tmp_file.write(content)
            tmp_file.flush()
            os.fsync(tmp_file.fileno())
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _write_discovery_file(port: int, owner: str, rhino_process_id: int) -> Path:
    DISCOVERY_FOLDER.mkdir(parents=True, exist_ok=True)
    path = DISCOVERY_FOLDER / f"{DISCOVERY_FILE_PREFIX}{port}.json"
    payload = {
        "service": "agent-chat",
        "host": CHAT_SERVER_BIND_HOST,
        "port": port,
        "pid": os.getpid(),
        "version": SERVICE_VERSION,
        "owner": owner,
        "rhinoProcessId": rhino_process_id,
        "startTime": datetime.now().isoformat(timespec="seconds"),
    }
    _atomic_write_text(path, json.dumps(payload, indent=2))
    return path


def _remove_discovery_file(path: Optional[Path]) -> None:
    if not path:
        return
    try:
        path.unlink(missing_ok=True)
    except Exception:
        logger.debug("Could not remove chat discovery file %s", path)


async def start_chat_server(
    port: int = 0,
    include_gh_health: bool = False,
    owner: str = "external",
    rhino_process_id: int = 0,
):
    """Start the chat server as a background task.

    Port defaults to 0 (OS-assigned). The actual bound port is published
    via a discovery file in %TEMP%/rook/.
    """
    global _server_task, _app_runner, _discovery_path, _startup_future
    if _server_task is not None:
        if _startup_future is not None:
            await _startup_future
        return

    async def _run():
        global _app_runner, _discovery_path, _startup_future
        app = create_chat_app(
            port=port,
            include_gh_health=include_gh_health,
            owner=owner,
            rhino_process_id=rhino_process_id,
        )
        _app_runner = web.AppRunner(app)
        await _app_runner.setup()
        try:
            site = web.TCPSite(_app_runner, CHAT_SERVER_BIND_HOST, port)
            await site.start()
            server = getattr(site, "_server", None)
            sockets = server.sockets if server else None
            if not sockets:
                raise RuntimeError("Chat server started without an accessible bound socket")
            selected_port = int(sockets[0].getsockname()[1])
            app[_PORT_STATE_KEY]["value"] = selected_port
            _discovery_path = _write_discovery_file(selected_port, owner, rhino_process_id)
            if _startup_future is not None and not _startup_future.done():
                _startup_future.set_result(selected_port)
            logger.info(
                "Agent chat server running on http://%s:%d",
                CHAT_SERVER_BIND_HOST, selected_port,
            )
        except Exception as exc:
            logger.error(f"Chat server startup failed: {exc!r}")
            await _app_runner.cleanup()
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
            await _app_runner.cleanup()
            _app_runner = None

    _startup_future = asyncio.get_running_loop().create_future()
    _server_task = asyncio.create_task(_run())
    await _startup_future


async def wait_for_chat_server():
    """Wait for the running chat server task to complete."""
    if _server_task is None:
        raise RuntimeError("Chat server is not running")
    await _server_task


async def stop_chat_server():
    """Stop the chat server.

    Cleanup is handled by _run()'s finally block when the task is cancelled,
    so we only need to cancel the task and wait for it.  If the task already
    failed (e.g. OSError from a blocked port), awaiting it re-raises the
    original exception — we catch that too so callers can always call stop
    without risking an unhandled error.
    """
    global _server_task, _discovery_path, _startup_future
    if _server_task:
        _server_task.cancel()
        try:
            await _server_task
        except (asyncio.CancelledError, Exception):
            pass
        _server_task = None
    _startup_future = None
    _remove_discovery_file(_discovery_path)
    _discovery_path = None
