"""Closed internal Vertex media token boundary; never exposed through MCP."""
from dataclasses import asdict
import json
from aiohttp import web
from ...providers.vertex_token_lease import VertexMediaBinding, VertexTokenLeaseService, _MESSAGES
from ...providers.vertex_auth import VertexAuthError

MAX_BODY = 8192

def failure(code, message, status):
    return web.json_response({"success": False, "error": {"code": code, "message": message}}, status=status)

async def read_body(request):
    if request.content_length is not None and request.content_length > MAX_BODY:
        raise ValueError("oversized")
    raw = bytearray()
    async for chunk in request.content.iter_chunked(4096):
        raw.extend(chunk)
        if len(raw) > MAX_BODY: raise ValueError("oversized")
    body = json.loads(raw.decode("utf-8"))
    if not isinstance(body, dict): raise ValueError("object required")
    return body

def register_vertex_media_routes(app, service: VertexTokenLeaseService):
    async def token(request):
        try:
            body = await read_body(request)
            if set(body) != {"operation", "model", "location", "expected_binding"} or body["operation"] not in {"acquire", "validate"}:
                raise ValueError("closed keys")
            if type(body["model"]) is not str or type(body["location"]) is not str: raise ValueError("invalid model/location")
            binding = None if body["expected_binding"] is None else VertexMediaBinding.from_wire(body["expected_binding"])
            if body["operation"] == "validate":
                if binding is None or binding.model_id != body["model"] or binding.location != body["location"]: raise ValueError("binding required")
                service.validate_binding(binding)
                return web.json_response({"success": True, "data": {"validated": True}})
            lease = await service.acquire(body["model"], body["location"], binding)
            return web.json_response({"success": True, "data": asdict(lease)})
        except VertexAuthError as exc:
            code = exc.code if exc.code in _MESSAGES else "vertex_request_failed"
            status = 400 if code in {"vertex_image_model_unsupported", "vertex_model_region_unsupported"} else 504 if code == "vertex_token_issuance_timeout" else 503 if code == "vertex_auth_dependency_missing" else 500 if code == "vertex_token_issuance_failed" else 409
            return failure(code, _MESSAGES.get(code, "Vertex authorization is unavailable because its local configuration is invalid."), status)
        except (ValueError, UnicodeError, KeyError, TypeError):
            return failure("vertex_internal_request_invalid", "The internal Vertex token request is invalid.", 400)
        except Exception:
            return failure("vertex_token_issuance_failed", _MESSAGES["vertex_token_issuance_failed"], 500)
    app.router.add_route("*", "/internal/providers/vertex/access-token", token)
