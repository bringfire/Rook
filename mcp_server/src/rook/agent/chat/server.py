"""Agent Chat HTTP Server."""
import asyncio
import json
import logging
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from aiohttp import web

from ...bridge import rhino_request_context
from .conversation_store import ConversationStore
from .prompt_builder import PromptBuilder
from .chat_runner import ChatRunner
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
        _runner = ChatRunner()
    return _runner


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

    try:
        conv = store.create(persona, document_serial_number=document_serial_number)
    except RuntimeError as e:
        return web.json_response({"error": str(e)}, status=429)

    # Resolve model, api_base, and display config.
    resolved_model, resolved_base = builder.resolve_model_and_base(persona)
    model_override = body.get("model_override")
    conv.model = model_override or resolved_model

    # When model_override changes the provider, re-filter api_base for the
    # actual model.  resolved_base was filtered for resolved_model's provider,
    # so it's wrong if the override swaps between cloud and local.
    if model_override and model_override != resolved_model:
        from ..model_profiles import get_models, api_base_for_model
        model_set = get_models()
        conv.api_base = api_base_for_model(conv.model, model_set.api_base) or ""
    else:
        conv.api_base = resolved_base or ""
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


async def handle_message(request: web.Request) -> web.StreamResponse:
    """POST /agent/chat/message — send a message, stream response."""
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    conv_id = body.get("conversation_id")
    message = body.get("message", "")
    raw_document_serial_number = body.get("documentSerialNumber", 0) or 0

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

    builder = request.app.get(_BUILDER_KEY) or _get_builder()
    runner = request.app.get(_RUNNER_KEY) or _get_runner()
    system_prompt = builder.build_system(conv.persona)

    # Stream response using chunked transfer encoding
    response = web.StreamResponse(
        status=200,
        reason="OK",
        headers={
            "Content-Type": "application/x-ndjson",
            "Cache-Control": "no-cache",
        },
    )
    await response.prepare(request)

    try:
        with rhino_request_context(
            process_id=request.app.get(_RHINO_PROCESS_ID_KEY, 0),
            document_serial_number=conv.document_serial_number,
        ):
            async for event in runner.run_turn(conv, message, system_prompt):
                line = json.dumps(event.to_dict()) + "\n"
                await response.write(line.encode("utf-8"))
    except (ConnectionResetError, ConnectionError, asyncio.CancelledError):
        logger.info(f"Client disconnected during streaming for conversation {conv_id}")
        conv.abort_event.set()

    try:
        await response.write_eof()
    except (ConnectionResetError, ConnectionError):
        pass
    return response


async def handle_ui_response(request: web.Request) -> web.Response:
    """POST /agent/chat/ui-response — receive structured input from a UI block.

    Called from the WebView via fetch().  The WebView loads from
    https://app.rook.invalid (virtual host backed by embedded resources).
    CORS and session nonce are enforced by cors_and_session_middleware.

    NOTE: This endpoint only appends the UI response to the conversation history.
    It does NOT trigger a new LLM turn automatically — the agent sees the response
    on the next user-initiated /message call. Auto-triggering is a known future
    enhancement (requires the WebView to initiate a streaming response).
    """
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    conv_id = body.get("conversation_id")
    block_id = body.get("block_id")
    value = body.get("value")

    if not conv_id or not block_id:
        return web.json_response({"error": "Missing conversation_id or block_id"}, status=400)

    store = request.app.get(_STORE_KEY) or _get_store()
    conv = store.get(conv_id)
    if conv is None:
        return web.json_response({"error": "Conversation not found"}, status=404)

    # Inject as a structured user message so the LLM sees the response
    conv.messages.append({
        "role": "user",
        "content": json.dumps({
            "type": "ui_response",
            "block_id": block_id,
            "value": value,
        }),
    })

    return web.json_response({"accepted": True})


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
    app[_PORT_STATE_KEY] = {"value": port}
    app[_INCLUDE_GH_HEALTH_KEY] = include_gh_health
    app[_OWNER_KEY] = owner
    app[_RHINO_PROCESS_ID_KEY] = rhino_process_id
    if nonce:
        app[_SESSION_NONCE_KEY] = nonce

    app.router.add_get("/agent/chat/health", handle_health)
    app.router.add_get("/agent/chat/personas", handle_personas)
    app.router.add_post("/agent/chat/start", handle_start)
    app.router.add_post("/agent/chat/message", handle_message)
    app.router.add_post("/agent/chat/stop", handle_stop)
    app.router.add_post("/agent/chat/ui-response", handle_ui_response)

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
