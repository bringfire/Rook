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
import os
import socket
import tempfile
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Iterator, Mapping

import httpx

from .crash_artifacts import find_recent_rhino_crash_artifact

logger = logging.getLogger(__name__)

# Rhino bridge connection settings
DEFAULT_HOST = "127.0.0.1"
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost"})
TIMEOUT = httpx.Timeout(connect=5.0, read=120.0, write=60.0, pool=5.0)

# The native server accepts only local Rook clients: every request must carry
# this header (a browser cannot add it without a CORS grant, which the native
# server never gives). Every httpx client that talks to the native server is
# created through native_client() so the header cannot be forgotten.
NATIVE_CLIENT_HEADER = "X-Rook-Client"
NATIVE_CLIENT_HEADERS = {NATIVE_CLIENT_HEADER: "rook-mcp"}


def native_client(**kwargs: Any) -> httpx.AsyncClient:
    """An httpx.AsyncClient pre-armed with the native server's client header."""
    headers = dict(NATIVE_CLIENT_HEADERS)
    headers.update(kwargs.pop("headers", None) or {})
    return httpx.AsyncClient(headers=headers, **kwargs)

# A session is a stable, legible name over a discovered Rhino process.
_SESSION_ID_PREFIX = "rhino-"

# P1 session targeting may touch ONLY these read-only endpoints. Mutating-route
# targeting is deliberately out of scope until a later phase; this guard fails
# closed so nothing else can be routed through a session in the meantime.
_READONLY_SESSION_ENDPOINTS = frozenset({"/ping", "/capabilities"})


class SessionEndpointNotAllowed(Exception):
    """Raised when a non-read-only endpoint is requested for a session call."""


def assert_session_readonly_endpoint(endpoint: str) -> None:
    if endpoint not in _READONLY_SESSION_ENDPOINTS:
        raise SessionEndpointNotAllowed(
            f"Endpoint {endpoint!r} is not in the P1 read-only session allowlist "
            f"{sorted(_READONLY_SESSION_ENDPOINTS)}."
        )


def resolve_discovery_folder(
    *,
    env: Mapping[str, str] | None = None,
    temp_root: str | Path | None = None,
) -> tuple[Path, list[Path], dict[str, Any]]:
    """Resolve primary and compatibility discovery roots used by MCP."""
    source_env = os.environ if env is None else env
    resolved_temp_root = Path(temp_root) if temp_root is not None else Path(tempfile.gettempdir())
    local_app_data = source_env.get("LOCALAPPDATA")
    legacy_temp_discovery = resolved_temp_root / "rook"

    if local_app_data:
        selected = Path(local_app_data) / "Rook" / "discovery"
        selection = "localappdata"
    else:
        selected = legacy_temp_discovery
        selection = "temp"

    folders = [selected]
    if legacy_temp_discovery != selected:
        folders.append(legacy_temp_discovery)

    diagnostics = {
        "selection": selection,
        "localAppData": local_app_data,
        "tempRoot": str(resolved_temp_root),
        "legacyTempDiscoveryFolder": str(legacy_temp_discovery),
        "discoveryFolders": [str(folder) for folder in folders],
    }

    return selected, folders, diagnostics


DISCOVERY_FOLDER, DISCOVERY_FOLDERS, _DISCOVERY_FOLDER_DIAGNOSTICS = resolve_discovery_folder()


def _effective_discovery_folders() -> list[Path]:
    folders = list(DISCOVERY_FOLDERS)
    if DISCOVERY_FOLDER not in folders:
        folders.insert(0, DISCOVERY_FOLDER)
    return folders


def discovery_diagnostics() -> dict[str, Any]:
    folders = _effective_discovery_folders()
    diagnostics = dict(_DISCOVERY_FOLDER_DIAGNOSTICS)
    diagnostics["discoveryFolder"] = str(DISCOVERY_FOLDER)
    diagnostics["discoveryFolders"] = [str(folder) for folder in folders]
    return diagnostics

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


def _is_port_listening(host: str, port: int, timeout: float = 0.2) -> bool:
    """Return True iff a TCP connection to host:port succeeds.

    Probed independently of PID liveness: a Rhino process can be alive while
    its RookNative listener is down (plugin reload, restart, transient). The
    caller MUST treat that case conservatively (report, do not reap).
    """
    if not port or port <= 0:
        return False
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


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


def get_bootstrap_capability_domain_summary(
    instance: dict[str, Any],
    domain_id: str,
) -> dict[str, Any] | None:
    """Return a discovery bootstrap domain summary.

    This reads stale/non-authoritative discovery metadata. It is suitable for
    bootstrap fallback only and must not drive readiness decisions when live
    ``/capabilities`` can be reached.
    """
    capabilities = instance.get("capabilities") or {}
    domain_summary = capabilities.get("domainSummary")
    if not isinstance(domain_summary, list):
        return None

    for domain in domain_summary:
        if isinstance(domain, dict) and domain.get("domainId") == domain_id:
            return domain

    return None


async def _fetch_live_capabilities(
    instance: dict[str, Any],
    timeout: httpx.Timeout | float | None = None,
) -> dict[str, Any]:
    capabilities = instance.get("capabilities") or {}
    endpoint = capabilities.get("liveEndpoint") or "/capabilities"
    if not isinstance(endpoint, str) or not endpoint.startswith("/"):
        endpoint = "/capabilities"

    host = instance.get("host") or DEFAULT_HOST
    port = instance.get("port")
    if not port:
        raise RuntimeError("discovery instance has no port")

    url = f"http://{host}:{port}{endpoint}"
    async with native_client(timeout=timeout or TIMEOUT) as client:
        response = await client.get(url)
        response.raise_for_status()
        payload = response.json()

    if not isinstance(payload, dict) or not isinstance(payload.get("domains"), list):
        raise RuntimeError("live capabilities response is missing domains")
    return payload


async def _fetch_verified_panel_capabilities(
    client: httpx.AsyncClient,
    instance: dict[str, Any],
    lock: Any,
) -> dict[str, Any]:
    host = instance.get("host") or DEFAULT_HOST
    port = instance.get("port")
    if not port:
        raise RuntimeError("panel target has no capability listener")

    response = await client.get(f"http://{host}:{port}/capabilities")
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or not isinstance(payload.get("domains"), list):
        raise RuntimeError("live capabilities response is missing domains")
    if not _targeting_module().live_capabilities_match_panel_target_lock(payload, lock):
        raise RuntimeError("live capabilities response has the wrong host generation")
    return payload


async def resolve_capabilities(
    instance: dict[str, Any],
    timeout: httpx.Timeout | float | None = None,
) -> dict[str, Any]:
    """Resolve authoritative live capabilities, with explicit bootstrap fallback."""
    try:
        payload = await _fetch_live_capabilities(instance, timeout=timeout)
        return {
            "source": "live",
            "stale": False,
            "authoritative": True,
            "liveEndpoint": (instance.get("capabilities") or {}).get("liveEndpoint", "/capabilities"),
            "capabilities": payload,
        }
    except Exception as exc:
        capabilities = instance.get("capabilities") or {}
        return {
            "source": "discovery_bootstrap_fallback",
            "stale": True,
            "authoritative": False,
            "summaryKind": capabilities.get("summaryKind", "bootstrap_snapshot"),
            "generatedUtc": capabilities.get("generatedUtc"),
            "liveEndpoint": capabilities.get("liveEndpoint", "/capabilities"),
            "fallbackReason": str(exc),
            "capabilities": capabilities,
        }


def get_resolved_capability_domain(
    resolved: dict[str, Any],
    domain_id: str,
) -> dict[str, Any] | None:
    capabilities = resolved.get("capabilities") or {}
    domains = capabilities.get("domains")
    if isinstance(domains, list):
        for domain in domains:
            if isinstance(domain, dict) and domain.get("domainId") == domain_id:
                return domain

    domain_summary = capabilities.get("domainSummary")
    if isinstance(domain_summary, list):
        for domain in domain_summary:
            if isinstance(domain, dict) and domain.get("domainId") == domain_id:
                return domain

    return None


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
    *,
    instances: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Select the best Rhino instance for an endpoint.

    If `port` is provided, it anchors selection to the same Rhino process when
    a companion native/managed server pair exists.
    """
    instances = list(instances) if instances is not None else discover_instances()
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
            return None

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

    patterns = [
        "instance-*.json",
        "native-*.json",
        "chat-service-*.json",
        "companion-*.json",
        "chirp-service-*.json",
    ]
    seen: set[Path] = set()
    seen_instances: set[tuple[object, ...]] = set()
    for folder in _effective_discovery_folders():
        if not folder.exists():
            continue

        for pattern in patterns:
            for file in folder.glob(pattern):
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
                        process_id = data.get("processId")
                        if process_id:
                            host = data.get("host")
                            route_host = (
                                host.strip().lower()
                                if isinstance(host, str) and host.strip()
                                else DEFAULT_HOST
                            )
                            instance_key = (
                                "route",
                                str(data.get("pluginType") or "native"),
                                process_id,
                                route_host,
                                data.get("port"),
                                data.get("hostGenerationId"),
                            )
                        else:
                            instance_key = ("path", file.resolve())
                        if instance_key in seen_instances:
                            continue
                        seen_instances.add(instance_key)
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


def session_id_for_instance(instance: dict[str, Any]) -> str:
    """Stable, human/agent-legible session id over a discovered Rhino process."""
    return f"{_SESSION_ID_PREFIX}{instance.get('processId')}"


def _process_id_from_session_id(session_id: Any) -> int | None:
    """Parse a session id back to its process id, or None if malformed."""
    if not isinstance(session_id, str) or not session_id.startswith(_SESSION_ID_PREFIX):
        return None
    raw = session_id[len(_SESSION_ID_PREFIX):]
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def classify_session_liveness(instance: dict[str, Any]) -> dict[str, Any]:
    """Classify a discovered session's liveness without ever reaping it.

    Probes PID and port INDEPENDENTLY so the two failure modes can be told
    apart: a dead process (safe to reap, elsewhere) vs. an alive process whose
    listener is unreachable (must be left alone — may be the user's live doc).
    """
    pid = instance.get("processId")
    host = instance.get("host") or DEFAULT_HOST
    port = instance.get("port")

    pid_alive = bool(pid) and _is_pid_alive(int(pid))
    port_listening = bool(port) and _is_port_listening(host, int(port))

    if not pid_alive:
        state, code = "dead", "rhino_session_dead"
    elif not port_listening:
        state, code = "unreachable", "rook_native_listener_unreachable"
    else:
        state, code = "live", None

    return {
        "state": state,
        "pidAlive": pid_alive,
        "portListening": port_listening,
        "code": code,
    }


def list_sessions() -> list[dict[str, Any]]:
    """Project discovered Rhino instances into named sessions with liveness.

    Read-only: reads discovery (which already reaps dead-PID files) and probes
    liveness. Never spawns, kills, or mutates. Instances without a processId are
    skipped (no stable session id).
    """
    sessions: list[dict[str, Any]] = []
    seen_process_ids: set[str] = set()
    for instance in discover_instances():
        # A session == a Rhino window, keyed by its native listener. The
        # roadcreator adapter shares the Rhino PID (bridge.py:379-381); including
        # it would emit a duplicate rhino-<pid> session. Native only.
        if instance.get("pluginType") != "native":
            continue
        pid = instance.get("processId")
        if not pid:
            continue
        process_id = str(pid)
        if process_id in seen_process_ids:
            continue
        seen_process_ids.add(process_id)
        sessions.append({
            "session": session_id_for_instance(instance),
            "processId": pid,
            "port": instance.get("port"),
            "host": instance.get("host") or DEFAULT_HOST,
            "pluginType": instance.get("pluginType"),
            "pluginVersion": instance.get("pluginVersion"),
            "rhinoInside": instance.get("rhinoInside"),
            "liveness": classify_session_liveness(instance),
        })
    return sessions


def list_sessions_result() -> dict[str, Any]:
    """MCP-facing envelope for list_sessions."""
    return {"success": True, "data": {"sessions": list_sessions()}}


async def get_session_capabilities(session_id: Any) -> dict[str, Any]:
    """Resolve live capabilities for one named session. Read-only.

    Touches only /capabilities (asserted via the read-only allowlist). Never
    spawns, kills, mutates, or reaps. Returns a structured error envelope for
    malformed ids, dead sessions, and unreachable-but-alive listeners.
    """
    process_id = _process_id_from_session_id(session_id)
    if process_id is None:
        return {
            "success": False,
            "data": {
                "code": "invalid_session_id",
                "session": session_id,
                "next_action": "Call list_sessions to get a valid session id (e.g. 'rhino-12345').",
            },
        }

    targeting = _targeting_module()
    lock, config_error = _panel_lock_state()
    if config_error is not None:
        return {"success": False, "data": config_error}
    if lock is not None and process_id != lock.process_id:
        return targeting.panel_target_locked_result()

    instances = discover_instances()
    if lock is not None:
        instance = targeting.resolve_panel_target_instance(instances, lock)
    else:
        instance = next(
            (
                inst for inst in instances
                if inst.get("processId") == process_id
                and inst.get("pluginType") == "native"
            ),
            None,
        )
    if instance is None:
        if lock is not None:
            return targeting.panel_target_unavailable_result(instances=instances)
        # No native record. Probe the PID before claiming dead (P2): the record may
        # be gone while the process lives (listener unloaded/reloading).
        gone_target = {
            "session": session_id, "processId": process_id, "port": None,
            "endpoint": "/capabilities", "method": "GET",
        }
        if _is_pid_alive(int(process_id)):
            return build_session_liveness_error(
                gone_target,
                {"state": "unreachable", "pidAlive": True, "portListening": False},
                reason="capability_query",
            )
        return build_session_liveness_error(
            gone_target,
            {"state": "dead", "pidAlive": False, "portListening": False},
            reason="capability_query",
        )

    if lock is not None:
        try:
            async with native_client(timeout=TIMEOUT) as client:
                live_capabilities = await _fetch_verified_panel_capabilities(
                    client, instance, lock
                )
        except Exception:
            return targeting.panel_target_unavailable_result(
                "The live Rook host generation could not be verified.",
                instances=instances,
            )
        return {
            "success": True,
            "data": {
                "session": session_id,
                "processId": process_id,
                "liveness": {
                    "state": "live",
                    "pidAlive": None,
                    "portListening": True,
                    "code": None,
                },
                "capabilities": {
                    "source": "live",
                    "stale": False,
                    "authoritative": True,
                    "liveEndpoint": "/capabilities",
                    "capabilities": live_capabilities,
                },
            },
        }

    liveness = classify_session_liveness(instance)
    if liveness["state"] in ("dead", "unreachable"):
        # `dead` can be the TOCTOU race (record matched at discovery, process died
        # before classification); either way report truthfully via the shared builder
        # (gains crash_artifact on dead + retryable). Never resolve stale capabilities
        # for a gone/unreachable process.
        err_target = {
            "session": session_id, "processId": process_id,
            "port": instance.get("port"), "endpoint": "/capabilities", "method": "GET",
        }
        return build_session_liveness_error(err_target, liveness, reason="capability_query")

    # Read-only: PIN the effective endpoint to a vetted, allow-listed route.
    # resolve_capabilities() otherwise honors capabilities.liveEndpoint straight
    # from the discovery record (bridge.py:197-207). A malformed/forged record
    # could point liveEndpoint at any slash-prefixed route (e.g. "/objects"), so
    # asserting a literal here is not enough — we must force it on the instance
    # we actually pass down. Sanitize a copy, then assert, then resolve.
    endpoint = "/capabilities"
    assert_session_readonly_endpoint(endpoint)
    safe_instance = dict(instance)
    safe_capabilities = dict(safe_instance.get("capabilities") or {})
    safe_capabilities["liveEndpoint"] = endpoint
    safe_instance["capabilities"] = safe_capabilities
    resolved = await resolve_capabilities(safe_instance)
    return {
        "success": True,
        "data": {
            "session": session_id,
            "processId": process_id,
            "liveness": liveness,
            "capabilities": resolved,
        },
    }


# Per-code policy: (retryable, next_action). The single source of truth for how a
# bridge-failure code maps to agent-facing guidance. Only rhino_session_dead is
# non-retryable, and the only path to it is a PID confirmed not-alive.
_BRIDGE_ERROR_POLICY: dict[str, tuple[bool, str]] = {
    "rhino_session_dead": (
        False,
        "The Rhino process is gone. Inspect crash_artifact if present, then call "
        "rhino_sessions; do not retry this session.",
    ),
    "rook_native_listener_unreachable": (
        True,
        "The Rhino process is alive but its RookNative listener is not responding "
        "(plugin reload, listener restart, or a transient). Retry shortly.",
    ),
    "rook_native_request_timeout": (
        True,
        "The request did not complete before the timeout — Rhino may be busy (a long "
        "command or a modal dialog) or a client-side stall. Retry shortly.",
    ),
    "rook_native_transport_error": (
        True,
        "The bridge request failed at the transport layer and the cause could not be "
        "confirmed. Call rhino_sessions to check live sessions, then retry.",
    ),
}


def _assemble_bridge_error(
    code: str,
    target: dict[str, Any],
    liveness: dict[str, Any] | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    """Assemble the structured `{success:False, data:{...}}` bridge-error envelope.

    Attaches a locate-only `crash_artifact` only for `rhino_session_dead`.
    """
    retryable, next_action = _BRIDGE_ERROR_POLICY[code]
    data: dict[str, Any] = {
        "code": code,
        "session": target.get("session"),
        "processId": target.get("processId"),
        "port": target.get("port"),
        "endpoint": target.get("endpoint"),
        "method": target.get("method"),
        "retryable": retryable,
        "next_action": next_action,
    }
    if liveness is not None:
        data["liveness"] = liveness
    if reason:
        data["reason"] = reason
    if code == "rhino_session_dead":
        artifact = find_recent_rhino_crash_artifact(process_id=target.get("processId"))
        if artifact is not None:
            data["crash_artifact"] = artifact
    return {"success": False, "data": data}


def build_session_liveness_error(
    target: dict[str, Any],
    liveness: dict[str, Any],
    reason: str | None = None,
) -> dict[str, Any]:
    """Build the bridge-error envelope from a resolved liveness state.

    Used by both `diagnose_bridge_failure` (connectivity branch) and
    `get_session_capabilities`. `live`/indeterminate is not a liveness *error* and
    maps to `rook_native_transport_error` (callers normally pass dead/unreachable).
    """
    code = {
        "dead": "rhino_session_dead",
        "unreachable": "rook_native_listener_unreachable",
    }.get(liveness.get("state"), "rook_native_transport_error")
    return _assemble_bridge_error(code, target, liveness=liveness, reason=reason)


# Connectivity failures: the connection could not be established or was dropped.
# ConnectTimeout is listed here on purpose (it subclasses TimeoutException) so it is
# diagnosed by probing liveness, not bucketed as a request timeout.
_CONNECTIVITY_ERRORS = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.ReadError,
    httpx.WriteError,
    httpx.CloseError,
)


def _resolve_target_liveness(target: dict[str, Any]) -> dict[str, Any]:
    """Liveness for a target, resolving a missing PID by port. Never guesses death.

    With a known PID, classify directly. Without one, look up the port in a fresh
    discover; if a native record owns it, classify that. If nothing owns the port,
    return 'indeterminate' — the caller maps that to a transport error, never a
    fabricated rhino_session_dead.
    """
    if target.get("processId"):
        return classify_session_liveness(target)
    port = target.get("port")
    inst = next(
        (i for i in discover_instances()
         if i.get("port") == port and i.get("pluginType") == "native"),
        None,
    )
    if inst is not None:
        return classify_session_liveness(inst)
    return {"state": "indeterminate", "pidAlive": None, "portListening": None}


def diagnose_bridge_failure(target: dict[str, Any], exc: Exception) -> dict[str, Any]:
    """Classify an httpx transport failure into a structured bridge-error envelope.

    Order matters: connectivity errors (incl. ConnectTimeout) are tested before the
    broad TimeoutException bucket. Timeouts PID-probe first so a death masked as a
    timeout returns rhino_session_dead, never a retryable timeout.
    """
    if isinstance(exc, _CONNECTIVITY_ERRORS):
        liveness = _resolve_target_liveness(target)
        if liveness["state"] in ("dead", "unreachable"):
            return build_session_liveness_error(target, liveness, reason="tool_call")
        return _assemble_bridge_error(
            "rook_native_transport_error", target, liveness=liveness, reason="tool_call"
        )

    if isinstance(exc, httpx.TimeoutException):  # ReadTimeout / WriteTimeout / PoolTimeout
        pid = target.get("processId")
        if pid and not _is_pid_alive(int(pid)):
            liveness = {"state": "dead", "pidAlive": False, "portListening": None}
            return build_session_liveness_error(target, liveness, reason="tool_call")
        return _assemble_bridge_error("rook_native_request_timeout", target, reason="tool_call")

    return _assemble_bridge_error("rook_native_transport_error", target, reason="tool_call")


def get_rhino_host(
    port: int | None = None,
    endpoint: str | None = None,
    process_id: int | None = None,
) -> str | None:
    """Get the Rhino host URL, optionally resolved for a specific endpoint.

    Returns None if no matching Rhino instance is discovered. Callers must
    handle None to produce clear error messages.
    """
    resolved_port = port if port is not None else _RHINO_CONTEXT_PORT.get()
    resolved_process_id = (
        process_id if process_id is not None else _RHINO_CONTEXT_PROCESS_ID.get()
    )
    if resolved_port is not None and resolved_port <= 0:
        resolved_port = None
    if resolved_process_id is not None and resolved_process_id <= 0:
        resolved_process_id = None

    instance = select_rhino_instance(
        endpoint=endpoint,
        port=resolved_port,
        process_id=resolved_process_id,
    )
    if instance and instance.get("port"):
        host = instance.get("host") or DEFAULT_HOST
        return f"http://{host}:{instance['port']}"

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
    *,
    instances: list[dict[str, Any]] | None = None,
) -> tuple[dict | None, int | None, int | None, dict[str, Any] | None]:
    targeting = _targeting_module()
    lock, config_error = _panel_lock_state()
    if config_error is not None:
        return data, port, process_id, {"success": False, "data": config_error}
    if lock is None:
        return data, port, process_id, None

    instances = list(instances) if instances is not None else discover_instances()
    locked_instance = targeting.resolve_panel_target_instance(instances, lock)
    if locked_instance is None:
        return data, port, process_id, targeting.panel_target_unavailable_result(
            instances=instances
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

    return applied, locked_instance.get("port"), lock.process_id, None


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
    instance_snapshot = discover_instances()
    data, resolved_port, resolved_process_id, panel_error = _apply_panel_lock_to_request(
        endpoint,
        data,
        resolved_port,
        resolved_process_id,
        instances=instance_snapshot,
    )
    if panel_error is not None:
        return panel_error
    data = _apply_document_context(data)
    normalized_endpoint = _normalize_endpoint(endpoint)
    selected_instance = select_rhino_instance(
        endpoint=endpoint,
        port=resolved_port,
        process_id=resolved_process_id,
        instances=instance_snapshot,
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
        instances = instance_snapshot
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
        instances = instance_snapshot
        lock, _ = _panel_lock_state()
        if (
            lock is not None
            and selected_instance.get("pluginType") == "native"
            and not _targeting_module().instance_matches_panel_target_lock(
                selected_instance, lock
            )
        ):
            return _targeting_module().panel_target_unavailable_result(
                instances=instances
            )
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
        instances = instance_snapshot
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

    # Capture the resolved target ONCE — the single source of truth for both the
    # request URL and failure diagnosis. Do NOT call get_rhino_host() here: it
    # re-runs select_rhino_instance and, under discovery churn, could resolve a
    # different instance than the one we captured, splitting the URL's target from
    # the diagnosed PID.
    if selected_instance is None or not selected_instance.get("port"):
        return {
            "success": False,
            "data": (
                "No Rhino instance discovered. "
                "Ensure Rhino is running with RookNative loaded."
            ),
        }
    target = {
        "host": selected_instance.get("host") or DEFAULT_HOST,
        "port": selected_instance.get("port"),
        "processId": selected_instance.get("processId"),
        "session": (
            session_id_for_instance(selected_instance)
            if selected_instance.get("processId") else None
        ),
        "endpoint": endpoint,
        "method": method,
    }
    url = f"http://{target['host']}:{target['port']}{endpoint}"

    async with native_client(timeout=timeout or TIMEOUT) as client:
        try:
            lock, _ = _panel_lock_state()
            if lock is not None:
                authority_instances = instance_snapshot
                authority = _targeting_module().resolve_panel_target_instance(
                    authority_instances, lock
                )
                if authority is None:
                    return _targeting_module().panel_target_unavailable_result(
                        instances=authority_instances
                    )
                try:
                    live_capabilities = await _fetch_verified_panel_capabilities(
                        client, authority, lock
                    )
                except Exception:
                    return _targeting_module().panel_target_unavailable_result(
                        "The live Rook host generation could not be verified.",
                        instances=authority_instances,
                    )
                capability_url = (
                    f"http://{authority.get('host') or DEFAULT_HOST}:"
                    f"{authority.get('port')}/capabilities"
                )
                if method == "GET" and not data and url == capability_url:
                    return live_capabilities

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
        except httpx.RequestError as exc:
            # Transport-level failure (connect / timeout / network) — diagnose it.
            return diagnose_bridge_failure(target, exc)
        except Exception as e:
            # A response was received but post-processing failed (e.g. response.json()
            # decode / body shape). NOT a bridge transport failure — preserve the
            # existing non-P2 behavior.
            return {"success": False, "data": str(e)}
