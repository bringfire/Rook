"""
Rhino HTTP Bridge
=================

Shared HTTP bridge for calling the Rhino plugin on localhost.

Used by both the MCP server (server.py) for Claude Code tool calls
and the agent ToolDispatcher for direct agent tool execution.

Extracted from server.py to avoid circular imports.
"""

import ctypes
import json
import logging
import tempfile
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Iterator

import httpx

logger = logging.getLogger(__name__)

# Rhino bridge connection settings
DEFAULT_HOST = "127.0.0.1"
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost"})
TIMEOUT = httpx.Timeout(connect=5.0, read=120.0, write=60.0, pool=5.0)

# Discovery folder (matches C# side)
DISCOVERY_FOLDER = Path(tempfile.gettempdir()) / "rook"

GH_ROUTE_PREFIX = "/gh/"
RC_ROUTE_PREFIX = "/rc/"

_RHINO_CONTEXT_PORT: ContextVar[int | None] = ContextVar(
    "rook_rhino_context_port",
    default=None,
)
_RHINO_CONTEXT_PROCESS_ID: ContextVar[int | None] = ContextVar(
    "rook_rhino_context_process_id",
    default=None,
)
_RHINO_CONTEXT_DOCUMENT_SN: ContextVar[int | None] = ContextVar(
    "rook_rhino_context_document_sn",
    default=None,
)

# GH route discovery is auto-derived from C++ RegisterRoutes() and written
# to the native discovery file as capabilities.ghRoutes.  No hand-maintained
# Python set is needed — see RookServer.cpp s_ghBaseRoutes / s_ghCgpRoutes.

def _is_pid_alive(pid: int) -> bool:
    """Check if a process with the given PID is alive (Windows)."""
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    handle = ctypes.windll.kernel32.OpenProcess(
        PROCESS_QUERY_LIMITED_INFORMATION, False, pid
    )
    if not handle:
        return False
    try:
        exit_code = ctypes.c_ulong()
        ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
        return exit_code.value == 259  # STILL_ACTIVE
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def _normalize_endpoint(endpoint: str | None) -> str | None:
    """Normalize endpoint strings for capability matching."""
    if not endpoint:
        return None
    return endpoint.split("?", 1)[0]


def _default_capabilities(plugin_type: str) -> dict[str, Any]:
    """Backfill capabilities for older discovery files.

    For native instances the actual ghRoutes list comes from the C++ discovery
    file (auto-derived from RegisterRoutes).  The managed plugin type no longer
    exists — returning an empty route list ensures stale discovery files don't
    accidentally match.
    """
    return {
        "ghProvider": "callback" if plugin_type == "native" else "managed",
        "ghRoutes": [],
    }


def _normalize_instance(data: dict[str, Any]) -> dict[str, Any]:
    """Normalize discovery records across plugin generations."""
    plugin_type = data.get("pluginType") or "native"
    capabilities = dict(_default_capabilities(plugin_type))
    capabilities.update(data.get("capabilities") or {})
    if "ghRoutes" not in capabilities:
        capabilities["ghRoutes"] = _default_capabilities(plugin_type)["ghRoutes"]

    data = dict(data)
    data["pluginType"] = plugin_type
    data["capabilities"] = capabilities

    # Validate discovery host is loopback — prevents forged discovery files
    # from redirecting tool traffic to an attacker-controlled server.
    host = data.get("host")
    if not isinstance(host, str) or not host:
        data["host"] = DEFAULT_HOST
    else:
        normalized_host = host.strip().lower()
        if normalized_host not in _LOOPBACK_HOSTS:
            logger.warning(
                "Discovery file contains non-loopback host %r; overriding to %s",
                host,
                DEFAULT_HOST,
            )
            data["host"] = DEFAULT_HOST
        else:
            data["host"] = normalized_host

    return data


def _supports_endpoint(instance: dict[str, Any], endpoint: str | None) -> bool:
    """Check whether a discovered instance advertises a route."""
    if not endpoint or not endpoint.startswith(GH_ROUTE_PREFIX):
        return True

    capabilities = instance.get("capabilities", {})
    gh_routes = capabilities.get("ghRoutes") or []
    if endpoint in gh_routes:
        return True

    if capabilities.get("ghProvider") == "proxy":
        gh_proxy_routes = capabilities.get("ghProxyRoutes") or []
        return endpoint in gh_proxy_routes

    return False


def _is_endpoint_ready(
    instance: dict[str, Any],
    endpoint: str | None,
    instances: list[dict[str, Any]],
) -> bool:
    """Check whether an advertised endpoint is actually ready to serve."""
    if not endpoint or not endpoint.startswith(GH_ROUTE_PREFIX):
        return True

    capabilities = instance.get("capabilities", {})
    if capabilities.get("ghProvider") == "proxy":
        pid = instance.get("processId")
        if not pid:
            return False

        return any(
            other.get("processId") == pid
            and other.get("pluginType") == "csharp"
            and _supports_endpoint(other, endpoint)
            for other in instances
        )

    return endpoint in (capabilities.get("ghRoutes") or [])


@contextmanager
def rhino_request_context(
    *,
    port: int | None = None,
    process_id: int | None = None,
    document_serial_number: int | None = None,
) -> Iterator[None]:
    """Bind default Rhino routing context for the current async/task scope."""
    port_token = process_token = doc_token = None
    try:
        if port and port > 0:
            port_token = _RHINO_CONTEXT_PORT.set(port)
        if process_id and process_id > 0:
            process_token = _RHINO_CONTEXT_PROCESS_ID.set(process_id)
        if document_serial_number and document_serial_number > 0:
            doc_token = _RHINO_CONTEXT_DOCUMENT_SN.set(document_serial_number)
        yield
    finally:
        if doc_token is not None:
            _RHINO_CONTEXT_DOCUMENT_SN.reset(doc_token)
        if process_token is not None:
            _RHINO_CONTEXT_PROCESS_ID.reset(process_token)
        if port_token is not None:
            _RHINO_CONTEXT_PORT.reset(port_token)


def get_rhino_request_context() -> dict[str, int | None]:
    """Return the currently bound default Rhino routing context."""
    return {
        "port": _RHINO_CONTEXT_PORT.get(),
        "process_id": _RHINO_CONTEXT_PROCESS_ID.get(),
        "document_serial_number": _RHINO_CONTEXT_DOCUMENT_SN.get(),
    }


def select_rhino_instance(
    endpoint: str | None = None,
    port: int | None = None,
    process_id: int | None = None,
) -> dict[str, Any] | None:
    """Select the best Rhino instance for an endpoint.

    If `port` is provided, it anchors selection to the same Rhino process when
    a companion native/managed server pair exists.
    """
    instances = discover_instances()
    if not instances:
        return None

    normalized_endpoint = _normalize_endpoint(endpoint)
    if port is not None and port <= 0:
        port = None
    if process_id is not None and process_id <= 0:
        process_id = None
    scoped_instances = instances
    if port is not None:
        anchor = next((inst for inst in instances if inst.get("port") == port), None)
        if anchor is None:
            return {"port": port} if process_id is None else None

        if process_id is not None and anchor.get("processId") != process_id:
            return None

        if not normalized_endpoint or (
            not normalized_endpoint.startswith(GH_ROUTE_PREFIX)
            and not normalized_endpoint.startswith(RC_ROUTE_PREFIX)
        ):
            return anchor

        pid = anchor.get("processId")
        if pid:
            scoped_instances = [
                inst for inst in instances if inst.get("processId") == pid
            ]
        else:
            scoped_instances = [anchor]
    elif process_id is not None:
        scoped_instances = [
            inst for inst in instances if inst.get("processId") == process_id
        ]
        if not scoped_instances:
            return None

    if normalized_endpoint and normalized_endpoint.startswith(RC_ROUTE_PREFIX):
        rc_candidates = [
            inst for inst in scoped_instances
            if inst.get("pluginType") == "roadcreator"
        ]
        return rc_candidates[0] if rc_candidates else None

    if normalized_endpoint and normalized_endpoint.startswith(GH_ROUTE_PREFIX):
        native_candidates = [
            inst
            for inst in scoped_instances
            if inst.get("pluginType") == "native"
            and _supports_endpoint(inst, normalized_endpoint)
            and _is_endpoint_ready(inst, normalized_endpoint, scoped_instances)
        ]
        if native_candidates:
            return native_candidates[0]

        candidates = [
            inst
            for inst in scoped_instances
            if _supports_endpoint(inst, normalized_endpoint)
            and _is_endpoint_ready(inst, normalized_endpoint, scoped_instances)
        ]
        if not candidates:
            return None

        candidates.sort(key=lambda inst: inst.get("pluginType") != "native")
        return candidates[0]

    scoped_instances.sort(key=lambda inst: inst.get("pluginType") != "native")
    return scoped_instances[0]


def _has_native_host_port_collision(
    instance: dict[str, Any],
    instances: list[dict[str, Any]],
) -> bool:
    """Return True if more than one native instance advertises the same host:port."""
    if instance.get("pluginType") != "native":
        return False

    host = instance.get("host") or DEFAULT_HOST
    port = instance.get("port")
    pid = instance.get("processId")
    if not host or not port or not pid:
        return False

    for other in instances:
        if other is instance or other.get("pluginType") != "native":
            continue
        other_host = other.get("host") or DEFAULT_HOST
        if other_host == host and other.get("port") == port and other.get("processId") != pid:
            return True
    return False


def _cleanup_stale_discovery_files() -> list[dict[str, Any]]:
    """Remove stale discovery files and return surviving instance records.

    Covers every file type in the discovery folder:
      - instance-*-native.json  (C++ native plugin)
      - instance-rc-*.json      (RookRoads adapter)
      - chat-service-*.json     (chat HTTP service)
      - companion-*.json        (legacy C# companion)
      - native-*.json           (deprecated C++ native format)

    Each file is expected to contain a JSON object with a "pid" or
    "processId" field.  If the process is dead, the file is removed.

    Returns the parsed data for surviving ``instance-*.json`` files so
    that ``discover_instances()`` can skip a second read pass.
    """
    surviving_instances: list[dict[str, Any]] = []

    if not DISCOVERY_FOLDER.exists():
        return surviving_instances

    patterns = [
        "instance-*.json",
        "native-*.json",
        "chat-service-*.json",
        "companion-*.json",
        "chirp-service-*.json",
    ]
    seen: set[Path] = set()
    for pattern in patterns:
        for file in DISCOVERY_FOLDER.glob(pattern):
            if file in seen:
                continue
            seen.add(file)
            try:
                data = json.loads(file.read_text(encoding="utf-8"))
                pid = data.get("processId") or data.get("pid")
                if pid and not _is_pid_alive(int(pid)):
                    logger.debug(f"Removing stale discovery file {file.name} (PID {pid} dead)")
                    file.unlink(missing_ok=True)
                    continue

                # Keep surviving instance-* records for discover_instances()
                if file.name.startswith("instance-"):
                    surviving_instances.append(data)
            except Exception:
                # Malformed file — remove it
                try:
                    file.unlink(missing_ok=True)
                except Exception:
                    pass

    return surviving_instances


def discover_instances() -> list[dict[str, Any]]:
    """Discover all active Rook instances by reading discovery files.

    A cleanup pass removes stale files (dead PIDs) across all discovery file
    types and returns the surviving instance data in a single read pass.
    """
    # Clean ALL stale discovery files and collect surviving instance records
    raw_instances = _cleanup_stale_discovery_files()

    instances = []
    for data in raw_instances:
        try:
            instances.append(_normalize_instance(data))
        except Exception as e:
            logger.debug(f"Could not normalize instance data: {e}")

    return [
        inst for inst in instances if inst.get("pluginType") in ("native", "roadcreator")
    ]


def get_rhino_host(
    port: int | None = None,
    endpoint: str | None = None,
    process_id: int | None = None,
) -> str | None:
    """Get the Rhino host URL, optionally resolved for a specific endpoint.

    Returns None if no Rhino instance is discovered and no explicit port
    was provided. Callers must handle None to produce clear error messages.
    """
    resolved_port = port if port is not None else _RHINO_CONTEXT_PORT.get()
    resolved_process_id = (
        process_id if process_id is not None else _RHINO_CONTEXT_PROCESS_ID.get()
    )
    if resolved_port is not None and resolved_port <= 0:
        resolved_port = None
    if resolved_process_id is not None and resolved_process_id <= 0:
        resolved_process_id = None

    if resolved_port and endpoint is None and resolved_process_id is None:
        return f"http://{DEFAULT_HOST}:{resolved_port}"

    instance = select_rhino_instance(
        endpoint=endpoint,
        port=resolved_port,
        process_id=resolved_process_id,
    )
    if instance and instance.get("port"):
        host = instance.get("host") or DEFAULT_HOST
        return f"http://{host}:{instance['port']}"

    if resolved_port and resolved_process_id is None:
        return f"http://{DEFAULT_HOST}:{resolved_port}"

    return None


def _apply_document_context(data: dict | None) -> dict | None:
    document_serial_number = _RHINO_CONTEXT_DOCUMENT_SN.get()
    if not document_serial_number:
        return data

    if data is None:
        return {"documentSerialNumber": document_serial_number}

    if "documentSerialNumber" in data:
        return dict(data)

    scoped = dict(data)
    scoped["documentSerialNumber"] = document_serial_number
    return scoped


def _targeting_module():
    from . import targeting

    return targeting


def _panel_lock_state():
    targeting = _targeting_module()
    return targeting.get_panel_target_lock(), targeting.get_panel_target_config_error()


def _apply_panel_lock_to_request(
    endpoint: str,
    data: dict | None,
    port: int | None,
    process_id: int | None,
) -> tuple[dict | None, int | None, int | None, dict[str, Any] | None]:
    targeting = _targeting_module()
    lock, config_error = _panel_lock_state()
    if config_error is not None:
        return data, port, process_id, {"success": False, "data": config_error}
    if lock is None:
        return data, port, process_id, None

    instances = discover_instances()
    locked_instances = [
        instance
        for instance in instances
        if instance.get("processId") == lock.process_id
    ]
    if not locked_instances:
        return data, port, process_id, targeting.route_error_result(
            targeting.ToolRoute(
                success=False,
                error="panel_target_stale",
                instances=instances,
            )
        )

    if process_id is not None and process_id > 0 and process_id != lock.process_id:
        return data, port, process_id, targeting.panel_target_locked_result()

    if port is not None and port > 0:
        explicit = next(
            (instance for instance in instances if instance.get("port") == port),
            None,
        )
        if explicit is None or explicit.get("processId") != lock.process_id:
            return data, port, process_id, targeting.panel_target_locked_result()
        port = None

    applied = targeting.apply_locked_document_context(data)
    if isinstance(applied, dict) and applied.get("success") is False:
        return data, port, process_id, applied

    return applied, port, lock.process_id, None


async def call_rhino(
    endpoint: str,
    method: str = "GET",
    data: dict | None = None,
    port: int | None = None,
    process_id: int | None = None,
    timeout: httpx.Timeout | float | None = None,
) -> dict[str, Any]:
    """Make an HTTP request to the Rhino bridge.

    Args:
        endpoint: The API endpoint (e.g., "/ping")
        method: HTTP method ("GET", "POST", "DELETE")
        data: Optional JSON data to send
        port: Optional specific port to connect to (for multi-instance support)
        process_id: Optional specific Rhino process ID to connect to
        timeout: Optional per-call HTTP timeout override
    """
    resolved_port = port if port is not None else _RHINO_CONTEXT_PORT.get()
    resolved_process_id = (
        process_id if process_id is not None else _RHINO_CONTEXT_PROCESS_ID.get()
    )
    if resolved_port is not None and resolved_port <= 0:
        resolved_port = None
    if resolved_process_id is not None and resolved_process_id <= 0:
        resolved_process_id = None
    data, resolved_port, resolved_process_id, panel_error = _apply_panel_lock_to_request(
        endpoint,
        data,
        resolved_port,
        resolved_process_id,
    )
    if panel_error is not None:
        return panel_error
    data = _apply_document_context(data)
    normalized_endpoint = _normalize_endpoint(endpoint)
    selected_instance = select_rhino_instance(
        endpoint=endpoint,
        port=resolved_port,
        process_id=resolved_process_id,
    )
    if normalized_endpoint and normalized_endpoint.startswith(RC_ROUTE_PREFIX) and selected_instance is None:
        return {
            "success": False,
            "data": (
                "No RookRoads plugin found. "
                "Load RookRoads (RookRC.rhp) in Rhino (Plug-ins → Install)."
            ),
        }

    if (
        normalized_endpoint
        and normalized_endpoint.startswith(GH_ROUTE_PREFIX)
        and selected_instance is None
    ):
        instances = discover_instances()
        if instances:
            ports_info = ", ".join(
                f"{inst['port']} ({inst.get('pluginType', 'unknown')})"
                for inst in instances
            )
            if port is not None:
                return {
                    "success": False,
                    "data": (
                        f"No same-process Rhino bridge supports {normalized_endpoint} "
                        f"for the selected instance on port {port}. "
                        f"Discovered instances: {ports_info}."
                    ),
                }
            return {
                "success": False,
                "data": (
                    f"No available Rhino bridge supports {normalized_endpoint}. "
                    f"Discovered instances: {ports_info}."
            ),
        }

    if selected_instance is not None:
        instances = discover_instances()
        if _has_native_host_port_collision(selected_instance, instances):
            host = selected_instance.get("host") or DEFAULT_HOST
            port_value = selected_instance.get("port")
            pid = selected_instance.get("processId")
            return {
                "success": False,
                "data": (
                    f"Ambiguous native bridge discovery for PID {pid}: "
                    f"multiple native instances advertise {host}:{port_value}. "
                    "Refusing to route request because the target Rhino process is not uniquely addressable."
                ),
            }

    if resolved_process_id is not None and selected_instance is None:
        instances = discover_instances()
        if instances:
            processes_info = ", ".join(
                f"PID {inst.get('processId')} @ {inst.get('port')}"
                for inst in instances
            )
            return {
                "success": False,
                "data": (
                    f"No Rhino bridge found for process {resolved_process_id}. "
                    f"Discovered instances: {processes_info}."
                ),
            }
        return {
            "success": False,
            "data": (
                f"No Rhino bridge found for process {resolved_process_id}. "
                "Is the owning Rhino instance running with RookNative loaded?"
            ),
        }

    host = get_rhino_host(
        resolved_port,
        endpoint=endpoint,
        process_id=resolved_process_id,
    )
    if host is None:
        return {
            "success": False,
            "data": (
                "No Rhino instance discovered. "
                "Ensure Rhino is running with RookNative loaded."
            ),
        }
    url = f"{host}{endpoint}"

    async with httpx.AsyncClient(timeout=timeout or TIMEOUT) as client:
        try:
            if method == "GET":
                if data:
                    # Pass GET data as query parameters, not body JSON.
                    # httplib (C++ plugin) drops GET request bodies per HTTP spec;
                    # query params work universally across both C++ and C# plugins.
                    params = {k: str(v) for k, v in data.items() if v is not None}
                    response = await client.get(url, params=params)
                else:
                    response = await client.get(url)
            elif method == "DELETE":
                response = await client.request(
                    "DELETE",
                    url,
                    content=json.dumps(data) if data else None,
                    headers={"Content-Type": "application/json"} if data else None,
                )
            else:
                response = await client.post(url, json=data)

            result = response.json()
            return result
        except httpx.ConnectError:
            instances = discover_instances()
            if instances:
                ports_info = ", ".join(str(i["port"]) for i in instances)
                return {
                    "success": False,
                    "data": (
                        f"Cannot connect to Rhino on {host}. "
                        f"Available instances on ports: {ports_info}. "
                        f"Use rhino_instances tool to see all instances."
                    ),
                }
            return {
                "success": False,
                "data": (
                    "Cannot connect to Rhino. "
                    "Is Rhino running with RookNative loaded?"
                ),
            }
        except Exception as e:
            return {"success": False, "data": str(e)}
