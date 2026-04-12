"""
Rook MCP Server

Provides MCP tools for Claude to interact with Rhino 3D via the Rook HTTP bridge.
Supports multiple Rhino instances through automatic discovery.
"""

import ast
import asyncio
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from .runtime_paths import (
    load_runtime_dotenv,
    resolve_readable_knowledge_path,
    resolve_runtime_paths,
    resolve_writable_knowledge_path,
)

# Resolve runtime roots and load .env before local modules import environment-dependent code.
RUNTIME_PATHS = resolve_runtime_paths()
LOADED_ENV_PATH = load_runtime_dotenv(RUNTIME_PATHS)

_log_level = getattr(logging, os.environ.get("ROOK_LOG_LEVEL", "INFO").upper(), logging.INFO)
logging.basicConfig(level=_log_level)
logger = logging.getLogger("rook")

if logger.isEnabledFor(logging.DEBUG):
    logger.debug(
        "Resolved runtime roots: mode=%s install_root=%s data_root=%s logs_root=%s mcp_server_dir=%s loaded_env=%s",
        RUNTIME_PATHS.mode,
        RUNTIME_PATHS.install_root,
        RUNTIME_PATHS.data_root,
        RUNTIME_PATHS.logs_root,
        RUNTIME_PATHS.mcp_server_dir,
        LOADED_ENV_PATH or "<none>",
    )

from .bridge import call_rhino, get_rhino_host, discover_instances, TIMEOUT, DISCOVERY_FOLDER
from .knowledge import query_knowledge, query_knowledge_tiered, record_knowledge, invalidate_condensed_command_cache
from .learning.command_observer import (
    CommandObserver, ObservationStore, DEFAULT_OBSERVATION_STORE_PATH
)
from .learning.command_learner import (
    CommandLearner, CommandKnowledgeStore, get_learning_queue
)
from .learning.command_consolidator import CommandTieringSystem
from .learning.dspy_config import configure_dspy, is_configured
from .learning.sugiyama import SugiyamaLayout
from .learning.canvas_layout import CanvasLayout, LayoutSettings
from .learning.canvas_align import align_positions, distribute_positions, straighten_wire_positions
from .learning.phase_tracker import get_phase_tracker
from .learning.knowledge_injector import should_inject, inject_knowledge, record_injection_success
from .learning.unified_store import get_unified_store

# Configure DSPy at startup — resolves model from profiles (supports local models)
def _configure_dspy_if_available() -> bool:
    """Configure DSPy from model profiles. Supports both cloud and local models."""
    try:
        configure_dspy()
        logger.info("DSPy configured successfully")
        return True
    except Exception as e:
        logger.warning(f"Failed to configure DSPy: {e}")
        return False

_dspy_configured = _configure_dspy_if_available()

# NOTE: TIMEOUT, DISCOVERY_FOLDER, call_rhino, get_rhino_host,
# and discover_instances are imported from .bridge module above.

# Command observation store for learning
observation_store = ObservationStore(DEFAULT_OBSERVATION_STORE_PATH)

# Command learner with DSPy/MAB integration
command_learner = CommandLearner(observation_store=observation_store)

# Failure tracking for correction detection
# Maps command -> {"inputs": [...], "error": "...", "timestamp": ...}
from datetime import datetime, timedelta, timezone
_recent_failures: dict[str, dict] = {}
_FAILURE_EXPIRY_MINUTES = 30  # Failures older than this are ignored


def _attach_deprecation_warnings(result: dict[str, Any], warnings: list[dict[str, Any]]) -> dict[str, Any]:
    """Attach deprecation warnings to a tool result without changing success semantics."""
    if not warnings:
        return result

    merged = dict(result)
    data = merged.get("data")
    if isinstance(data, dict):
        data = dict(data)
        data["deprecation_warnings"] = warnings
    else:
        data = {
            "result": data,
            "deprecation_warnings": warnings,
        }
    merged["data"] = data
    return merged


def _merge_issue_lists(*issue_lists: Any) -> list[str]:
    merged: list[str] = []
    for issues in issue_lists:
        if not isinstance(issues, list):
            continue
        for issue in issues:
            if isinstance(issue, str) and issue not in merged:
                merged.append(issue)
    return merged


def _extract_gh_edit_partial_issues(result: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Extract nested gh_edit warnings/errors without changing top-level success."""
    data = result.get("data")
    if not isinstance(data, dict):
        return ([], [])

    edit_summary = data.get("edit_summary")
    if not isinstance(edit_summary, dict):
        return ([], [])

    errors = _merge_issue_lists(edit_summary.get("errors"))
    warnings = _merge_issue_lists(edit_summary.get("warnings"))
    return (errors, warnings)


def _attach_gh_edit_partial_warnings(result: dict[str, Any]) -> dict[str, Any]:
    """Surface edit_summary issues so callers can see partial gh_edit failures easily."""
    edit_errors, edit_warnings = _extract_gh_edit_partial_issues(result)
    if not edit_errors and not edit_warnings:
        return result

    merged = dict(result)
    data = merged.get("data")
    if isinstance(data, dict):
        data = dict(data)
    else:
        data = {"result": data}

    existing_warnings = data.get("warnings")
    data["warnings"] = _merge_issue_lists(existing_warnings, edit_warnings, edit_errors)
    merged["data"] = data
    return merged


_RHINOSCRIPTSYNTAX_INTERACTIVE_CALLS: frozenset[str] = frozenset({
    "GetBoolean",
    "GetBox",
    "GetColor",
    "GetCurveObject",
    "GetInteger",
    "GetLayer",
    "GetMeshObject",
    "GetObject",
    "GetObjects",
    "GetPoint",
    "GetPoints",
    "GetReal",
    "GetRectangle",
    "GetString",
    "GetSurfaceObject",
})


def _find_blocking_rhinoscriptsyntax_call(code: str) -> tuple[str, int] | None:
    """Return the first obvious blocking rhinoscriptsyntax input call, if any."""
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError:
        return None

    rs_aliases: set[str] = set()
    imported_names: dict[str, str] = {}
    has_star_import = False

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "rhinoscriptsyntax":
                    rs_aliases.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module == "rhinoscriptsyntax":
            for alias in node.names:
                if alias.name == "*":
                    has_star_import = True
                    continue
                imported_names[alias.asname or alias.name] = alias.name

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        func = node.func
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            if func.value.id in rs_aliases and func.attr in _RHINOSCRIPTSYNTAX_INTERACTIVE_CALLS:
                return f"{func.value.id}.{func.attr}()", getattr(node, "lineno", 1)

        if isinstance(func, ast.Name):
            original_name = imported_names.get(func.id, func.id if has_star_import else "")
            if original_name in _RHINOSCRIPTSYNTAX_INTERACTIVE_CALLS:
                return f"{func.id}()", getattr(node, "lineno", 1)

    return None


def _preflight_rhino_command(command: Any) -> dict[str, Any] | None:
    """Reject obviously malformed Rhino command strings before they hit RunScript."""
    from .preflight import preflight_rhino_command
    return preflight_rhino_command(command, command_learner.knowledge_store)


def _track_failure(command: str, inputs: list, error: str) -> None:
    """Track a command failure for potential correction detection."""
    _recent_failures[command] = {
        "inputs": inputs,
        "error": error,
        "timestamp": datetime.now(),
    }


def _check_for_correction(command: str, success: bool, objects_created: int) -> dict | None:
    """
    Check if this successful execution corrects a recent failure.
    Returns correction info if detected, None otherwise.
    """
    if not success or objects_created == 0:
        return None

    if command not in _recent_failures:
        return None

    failure = _recent_failures[command]

    # Check if failure is recent enough
    age = datetime.now() - failure["timestamp"]
    if age > timedelta(minutes=_FAILURE_EXPIRY_MINUTES):
        del _recent_failures[command]
        return None

    # This success corrects a recent failure
    correction_info = {
        "failed_inputs": failure["inputs"],
        "error": failure["error"],
    }

    # Clear the failure now that it's been corrected
    del _recent_failures[command]

    return correction_info


def _clear_failure(command: str) -> None:
    """Clear tracked failure for a command (e.g., after successful correction)."""
    _recent_failures.pop(command, None)


# gh_execute_intent correction detection (separate from per-tool tracking)
_gh_intent_failures: dict[str, dict] = {}
_GH_FAILURE_EXPIRY_MINUTES = 30

# Agent system state — tracks running/completed agents for status/abort
_active_agents: dict[str, Any] = {}  # agent_id -> {"agent": ..., "task": asyncio.Task, ...}
_agent_results: dict[str, Any] = {}  # agent_id -> SpawnResult/PlanResult
_MAX_AGENT_HISTORY = 50  # Eviction limit for agent tracking dicts

# Tools that agents must NOT have access to (prevents recursive spawning)
_AGENT_MANAGEMENT_TOOLS = frozenset({
    "spawn_agent", "plan_and_execute", "agent_status", "agent_abort", "agent_answer",
})


async def _mcp_tool_executor(tool_name: str, params: dict) -> dict:
    """Route tool calls through MCP call_tool for agent use.

    This is the canonical tool executor shared by spawn_agent and
    plan_and_execute. It converts MCP TextContent responses back
    to plain dicts that the agent loop expects.
    """
    try:
        result = await call_tool(tool_name, params)
        if isinstance(result, list) and result:
            content = result[0]
            text = getattr(content, "text", str(content))
            try:
                return json.loads(text)
            except (json.JSONDecodeError, TypeError):
                return {"success": True, "data": text}
        return {"success": True, "data": str(result)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _cleanup_agent_history() -> None:
    """Evict oldest entries when agent tracking dicts exceed limit."""
    while len(_active_agents) > _MAX_AGENT_HISTORY:
        oldest_id = next(iter(_active_agents))
        del _active_agents[oldest_id]
        _agent_results.pop(oldest_id, None)


def _track_intent_failure(intent: str, components: list, error: str) -> None:
    """Track a gh_execute_intent failure for correction detection."""
    key = intent.lower().strip()
    _gh_intent_failures[key] = {
        "intent": intent,
        "components": [c.get("name", "") for c in components] if components else [],
        "error": error,
        "timestamp": datetime.now(),
    }


def _check_intent_correction(intent: str, success: bool, created_count: int) -> dict | None:
    """Check if a successful gh_execute_intent corrects a recent failure."""
    if not success or created_count == 0:
        return None

    key = intent.lower().strip()
    failure = _gh_intent_failures.pop(key, None)
    if failure is None:
        return None

    age = datetime.now() - failure["timestamp"]
    if age > timedelta(minutes=_GH_FAILURE_EXPIRY_MINUTES):
        return None  # Expired, already popped

    return {
        "original_intent": failure["intent"],
        "failed_components": failure["components"],
        "error": failure["error"],
    }


# =============================================================================
# Session Recording Helper
# Records GH tool calls to session history for Path 2 meta-learning
# =============================================================================

async def _record_gh_to_session(
    action: str,
    params: dict,
    result: dict,
    port: int,
    *,
    components_created: list[str] | None = None,
    components_affected: list[str] | None = None,
    components_deleted: list[str] | None = None,
    connections_made: list[tuple] | None = None,
    connections_removed: list[tuple] | None = None,
    patterns_applied: list[str] | None = None,
) -> int | None:
    """Record a GH tool call to session history.

    This is called after GH tool execution to log the action for later
    pattern extraction and reflection.

    Args:
        action: Tool name (e.g., 'gh_edit')
        params: Tool parameters
        result: Raw result from the tool
        port: Rhino port (for document context)
        components_created: GUIDs of created components
        components_affected: GUIDs of modified components
        components_deleted: GUIDs of deleted components
        connections_made: List of (source, source_param, target, target_param)
        connections_removed: List of removed connections
        patterns_applied: Pattern IDs that were used in this action (Phase 2)

    Returns:
        Entry ID if recorded, None if skipped
    """
    try:
        from rook.learning.gh_session_history import get_session_recorder, GHToolResult

        # Get document context from GH
        doc_result = await call_rhino("/gh/document", "GET", port=port)
        if doc_result.get("success") and doc_result.get("data"):
            data = doc_result["data"]
            # Handle both capitalized (C#) and lowercase keys
            document = data.get("Name") or data.get("name") or "unknown.gh"
            document_path = data.get("Path") or data.get("path") or ""
        else:
            document = "unknown.gh"
            document_path = ""

        # Determine outcome from result
        success = result.get("success", False)
        data = result.get("data")
        if isinstance(data, dict):
            success = data.get("success", success)

        errors = _merge_issue_lists(result.get("errors"))
        warnings = _merge_issue_lists(result.get("warnings"))

        if isinstance(data, dict):
            errors = _merge_issue_lists(errors, data.get("errors"))
            warnings = _merge_issue_lists(warnings, data.get("warnings"))
            edit_errors, edit_warnings = _extract_gh_edit_partial_issues(result)
            errors = _merge_issue_lists(errors, edit_errors)
            warnings = _merge_issue_lists(warnings, edit_warnings)
        elif not success:
            error_msg = data if isinstance(data, str) else None
            if error_msg:
                errors = _merge_issue_lists(errors, [error_msg])

        # Determine outcome level
        if success and not errors and not warnings:
            outcome = "success"
        elif success:
            outcome = "partial"
        else:
            outcome = "failure"

        # Create GHToolResult
        tool_result = GHToolResult(
            success=success,
            outcome=outcome,
            data={},  # Don't duplicate the full data
            components_created=components_created or [],
            components_affected=components_affected or [],
            components_deleted=components_deleted or [],
            connections_made=connections_made or [],
            connections_removed=connections_removed or [],
            errors=errors,
            warnings=warnings,
        )

        # Record to session
        recorder = get_session_recorder()
        entry_id = await recorder.record(
            action=action,
            params=params,
            result=tool_result,
            document=document,
            document_path=document_path,
            patterns_applied=patterns_applied,
        )

        return entry_id

    except Exception as e:
        logger.warning(f"Failed to record {action} to session: {e}")
        return None


def _build_gh_python_preamble(pins_in: list[str]) -> str:
    """Generate a Python preamble that coerces GH Generic Data inputs to declared types.

    GH Python 3 Script components use Generic Data pins. Data arrives in three
    forms depending on what's upstream:

      1. System.Guid  — reference to a Rhino doc object (points, curves, breps, meshes).
                         Must be dereferenced via RhinoDoc.Objects.FindId().
      2. GH wrapper   — GH_Point, GH_Number, GH_Vector, etc. with a .Value property
                         holding the native Rhino/Python type.
      3. Native type   — already the correct type (rare, but possible).

    The preamble emits a single universal coercion function and one line per input
    pin that converts the raw GH input to the declared type.
    """
    # Reference geometry — stored as Rhino doc objects, may arrive as System.Guid.
    # Point is special: the doc object is rg.Point, but we want rg.Point3d (.Location).
    _DOC_GEOMETRY = {
        "Point3d": "Location",  # rg.Point → .Location → Point3d
        "Curve": None,
        "Surface": None,
        "Brep": None,
        "Mesh": None,
    }
    # Value geometry — never in the doc, always GH wrappers or native.
    _VALUE_GEOMETRY = {
        "Vector3d", "Plane", "Line", "Circle", "Arc", "Box",
        "Polyline", "Point2d", "Interval", "Rectangle3d", "Transform",
    }
    # Numeric/primitive types
    _NUMERIC_TYPES = {
        "float": "float",
        "double": "float",
        "int": "int",
        "bool": "bool",
    }

    doc_pins = []    # (var_name, accessor_or_None)
    value_pins = []  # var_name
    num_pins = []    # (var_name, python_cast)

    for pin_str in pins_in:
        parts = pin_str.split(":", 1)
        name = parts[0].strip()
        ptype = parts[1].strip() if len(parts) > 1 else "string"

        if ptype in _DOC_GEOMETRY:
            doc_pins.append((name, _DOC_GEOMETRY[ptype]))
        elif ptype in _VALUE_GEOMETRY:
            value_pins.append(name)
        elif ptype in _NUMERIC_TYPES:
            num_pins.append((name, _NUMERIC_TYPES[ptype]))
        # string and unknown types pass through unchanged

    if not doc_pins and not value_pins and not num_pins:
        return ""  # No coercion needed

    lines = [
        "# ── Auto-generated GH input coercion (do not edit) ──────────",
        "import Rhino as _rh",
        "import Rhino.Geometry as rg",
        "import System as _sys",
        "",
        "def _ghc(val, accessor=None):",
        '    """Coerce a single GH Generic Data value to its native type."""',
        "    if val is None: return None",
        "    # Case 1: System.Guid → dereference from Rhino document",
        "    if isinstance(val, _sys.Guid):",
        "        obj = _rh.RhinoDoc.ActiveDoc.Objects.FindId(val)",
        "        if obj and hasattr(obj, 'Geometry'):",
        "            g = obj.Geometry",
        "            return getattr(g, accessor) if accessor else g",
        "        return None",
        "    # Case 2: GH wrapper (GH_Point, GH_Number, etc.) → unwrap .Value",
        "    if hasattr(val, 'Value'): return val.Value",
        "    # Case 3: already native",
        "    return val",
        "",
    ]

    # Doc-referenced geometry (may be Guid, GH wrapper, or native)
    for name, accessor in doc_pins:
        acc = f"'{accessor}'" if accessor else "None"
        lines.append(f"{name} = _ghc({name}, {acc})")

    # Value geometry (GH wrapper or native — never Guid)
    for name in value_pins:
        lines.append(f"{name} = _ghc({name})")

    # Numerics (GH wrapper, native, or None → safe default)
    for name, cast in num_pins:
        lines.append(f"if {name} is not None: {name} = {cast}(_ghc({name}))")
        lines.append(f"else: {name} = {cast}(0)")

    lines.append("# ── End coercion ─────────────────────────────────────────────")
    lines.append("")

    return "\n".join(lines) + "\n"


def _build_gh_csharp_wrapper(code: str, pins_in: list[str], pins_out: list[str]) -> str:
    """Wrap user C# code in the GH_ScriptInstance boilerplate required by RhinoCode C# Script.

    If the user already provides a full class (contains 'class Script_Instance' or
    'void RunScript'), the code is returned unchanged. Otherwise, the code is treated
    as the body of RunScript and wrapped automatically.

    IMPORTANT: RhinoCode C# Script components enforce that RunScript parameters use
    the exact pin names and are always typed as `object`. The wrapper cannot rename
    or retype parameters. User code receives `object` inputs and must cast as needed.
    The wrapper does NOT auto-generate casts — the caller (Claude/agent) should write
    code that handles `object` inputs, e.g. `var r = Convert.ToDouble(R);`.
    """
    # Detect full-class code — pass through unchanged
    if "class Script_Instance" in code or "void RunScript" in code:
        return code

    def _parse_cs_pin(pin_str: str) -> str:
        parts = pin_str.split(":", 1)
        return parts[0].strip()

    # Build RunScript parameter list — all object, matching RhinoCode's enforced signature
    in_names = [_parse_cs_pin(p) for p in pins_in]
    out_names = [_parse_cs_pin(p) for p in pins_out]

    params = []
    for name in in_names:
        params.append(f"object {name}")
    for name in out_names:
        params.append(f"ref object {name}")

    param_str = ", ".join(params)

    # Indent user code
    indented = "\n".join("        " + line if line.strip() else "" for line in code.splitlines())

    return f"""using System;
using System.Collections.Generic;
using System.Drawing;
using System.Linq;
using Rhino;
using Rhino.Geometry;
using Grasshopper;
using Grasshopper.Kernel;

public class Script_Instance : GH_ScriptInstance
{{
    private void RunScript({param_str})
    {{
{indented}
    }}
}}
"""


def _extract_gh_result_guid(result: dict) -> str | None:
    """Extract a created/affected GH object guid from a tool result."""
    data = result.get("data")
    if not isinstance(data, dict):
        return None
    return data.get("Guid") or data.get("guid")


def _normalize_gh_guid_list(value: Any) -> list[str]:
    """Normalize user/result guid inputs into a compact string list."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str) and item]
    return []


# =============================================================================
# Knowledge-Aware GH Tool Wrappers
# These wrap internal GH tools with query→execute→observe pattern
# =============================================================================

import uuid as uuid_module


async def _execute_gh_connect_with_knowledge(arguments: dict, port: int) -> dict:
    """Execute gh_connect with knowledge awareness.

    1. Query operation knowledge for wiring gotchas
    2. Execute the connection
    3. Track failure or check for correction
    4. Return enriched result with observation_id and correction info
    """
    from rook.learning.gh_knowledge import gh_query_operation, get_gh_knowledge_store

    observation_id = str(uuid_module.uuid4())[:8]
    context = {
        "source_guid": arguments.get("sourceGuid"),
        "target_guid": arguments.get("targetGuid"),
        "param": arguments.get("targetParam"),
    }

    # Query operation knowledge
    op_knowledge = gh_query_operation("wire", context)
    gotchas = [g.get("message") for g in op_knowledge.get("gotchas", [])]

    # Execute the actual connection
    result = await call_rhino("/gh/connect", "POST", arguments, port=port)

    # Determine success
    success = result.get("success", False)
    if isinstance(result.get("data"), dict):
        success = result["data"].get("success", success)

    # Track or check correction
    correction_detected = False
    correction_info = None

    if not success:
        error_msg = str(result.get("data", "Connection failed"))
        _track_gh_failure("wire", context, error_msg)
    else:
        correction_info = _check_for_gh_correction("wire", context, True)
        if correction_info:
            correction_detected = True
        # Update staleness on injected gotchas
        if gotchas:
            get_gh_knowledge_store().record_gotcha_success("wire")

    # Enrich result
    if isinstance(result.get("data"), dict):
        result["data"]["observation_id"] = observation_id
        result["data"]["correction_detected"] = correction_detected
        if correction_info:
            result["data"]["correction_info"] = correction_info
        if gotchas:
            result["data"]["gotchas"] = gotchas
    else:
        result["observation_id"] = observation_id
        result["correction_detected"] = correction_detected

    # Record to session history
    entry_id = await _record_gh_to_session(
        action="gh_connect",
        params={"source": arguments.get("sourceGuid"), "target": arguments.get("targetGuid"), "param": arguments.get("targetParam")},
        result=result,
        port=port,
        connections_made=[(arguments.get("sourceGuid", ""), "output", arguments.get("targetGuid", ""), arguments.get("targetParam", ""))] if success else None,
    )
    if entry_id and isinstance(result.get("data"), dict):
        result["data"]["_entry_id"] = entry_id

    return result


async def _execute_gh_set_value_with_knowledge(arguments: dict, port: int) -> dict:
    """Execute gh_set_value with knowledge awareness."""
    from rook.learning.gh_knowledge import gh_query_operation, get_gh_knowledge_store

    observation_id = str(uuid_module.uuid4())[:8]
    context = {
        "target_guid": arguments.get("guid"),
        "value": arguments.get("value"),
    }

    # Query operation knowledge
    op_knowledge = gh_query_operation("set_value", context)
    gotchas = [g.get("message") for g in op_knowledge.get("gotchas", [])]

    # Execute the actual set value
    result = await call_rhino("/gh/value", "POST", arguments, port=port)

    # Determine success
    success = result.get("success", False)
    if isinstance(result.get("data"), dict):
        success = result["data"].get("success", success)

    # Track or check correction
    correction_detected = False
    correction_info = None

    if not success:
        error_msg = str(result.get("data", "Set value failed"))
        _track_gh_failure("set_value", context, error_msg)
    else:
        correction_info = _check_for_gh_correction("set_value", context, True)
        if correction_info:
            correction_detected = True
        if gotchas:
            get_gh_knowledge_store().record_gotcha_success("set_value")

    # Enrich result
    if isinstance(result.get("data"), dict):
        result["data"]["observation_id"] = observation_id
        result["data"]["correction_detected"] = correction_detected
        if correction_info:
            result["data"]["correction_info"] = correction_info
        if gotchas:
            result["data"]["gotchas"] = gotchas
    else:
        result["observation_id"] = observation_id
        result["correction_detected"] = correction_detected

    # Record to session history
    entry_id = await _record_gh_to_session(
        action="gh_set_value",
        params={"guid": arguments.get("guid"), "value": arguments.get("value")},
        result=result,
        port=port,
        components_affected=[arguments.get("guid")] if arguments.get("guid") and success else None,
    )
    if entry_id and isinstance(result.get("data"), dict):
        result["data"]["_entry_id"] = entry_id

    return result


async def _execute_gh_delete_with_knowledge(arguments: dict, port: int) -> dict:
    """Execute gh_delete with knowledge awareness."""
    from rook.learning.gh_knowledge import gh_query_operation, get_gh_knowledge_store

    observation_id = str(uuid_module.uuid4())[:8]
    guids = arguments.get("guids", [])
    context = {
        "guids": guids,
    }

    # Query operation knowledge
    op_knowledge = gh_query_operation("delete", context)
    gotchas = [g.get("message") for g in op_knowledge.get("gotchas", [])]

    # Execute the actual delete
    result = await call_rhino("/gh/delete", "POST", arguments, port=port)

    # Determine success
    success = result.get("success", False)
    if isinstance(result.get("data"), dict):
        success = result["data"].get("success", success)

    # Track or check correction
    correction_detected = False
    correction_info = None

    if not success:
        error_msg = str(result.get("data", "Delete failed"))
        _track_gh_failure("delete", context, error_msg)
    else:
        correction_info = _check_for_gh_correction("delete", context, True)
        if correction_info:
            correction_detected = True
        if gotchas:
            get_gh_knowledge_store().record_gotcha_success("delete")

    # Enrich result
    if isinstance(result.get("data"), dict):
        result["data"]["observation_id"] = observation_id
        result["data"]["correction_detected"] = correction_detected
        if correction_info:
            result["data"]["correction_info"] = correction_info
        if gotchas:
            result["data"]["gotchas"] = gotchas
    else:
        result["observation_id"] = observation_id
        result["correction_detected"] = correction_detected

    # Record to session history
    entry_id = await _record_gh_to_session(
        action="gh_delete",
        params={"guids": guids},
        result=result,
        port=port,
        components_deleted=guids if success else None,
    )
    if entry_id and isinstance(result.get("data"), dict):
        result["data"]["_entry_id"] = entry_id

    return result


async def _execute_gh_disconnect_with_knowledge(arguments: dict, port: int) -> dict:
    """Execute gh_disconnect with knowledge awareness."""
    from rook.learning.gh_knowledge import gh_query_operation, get_gh_knowledge_store

    observation_id = str(uuid_module.uuid4())[:8]
    context = {
        "source_guid": arguments.get("sourceGuid"),
        "target_guid": arguments.get("targetGuid"),
        "param": arguments.get("targetParam"),
    }

    # Query operation knowledge
    op_knowledge = gh_query_operation("disconnect", context)
    gotchas = [g.get("message") for g in op_knowledge.get("gotchas", [])]

    # Execute the actual disconnect
    result = await call_rhino("/gh/disconnect", "POST", arguments, port=port)

    # Determine success
    success = result.get("success", False)
    if isinstance(result.get("data"), dict):
        success = result["data"].get("success", success)

    # Track or check correction
    correction_detected = False
    correction_info = None

    if not success:
        error_msg = str(result.get("data", "Disconnect failed"))
        _track_gh_failure("disconnect", context, error_msg)
    else:
        correction_info = _check_for_gh_correction("disconnect", context, True)
        if correction_info:
            correction_detected = True
        if gotchas:
            get_gh_knowledge_store().record_gotcha_success("disconnect")

    # Enrich result
    if isinstance(result.get("data"), dict):
        result["data"]["observation_id"] = observation_id
        result["data"]["correction_detected"] = correction_detected
        if correction_info:
            result["data"]["correction_info"] = correction_info
        if gotchas:
            result["data"]["gotchas"] = gotchas
    else:
        result["observation_id"] = observation_id
        result["correction_detected"] = correction_detected

    # Record to session history
    entry_id = await _record_gh_to_session(
        action="gh_disconnect",
        params={"source": arguments.get("sourceGuid"), "target": arguments.get("targetGuid"), "param": arguments.get("targetParam")},
        result=result,
        port=port,
        connections_removed=[(arguments.get("sourceGuid", ""), "output", arguments.get("targetGuid", ""), arguments.get("targetParam", ""))] if success else None,
    )
    if entry_id and isinstance(result.get("data"), dict):
        result["data"]["_entry_id"] = entry_id

    return result


def _regenerate_tiered_knowledge(command: str | None = None) -> dict:
    """Regenerate condensed/tiered knowledge for a specific command or all commands.

    Called automatically after consolidation to keep tiered knowledge in sync.

    Args:
        command: Specific command to tier (e.g., "-PointLight"). If None, tiers all commands.

    Returns stats about the regeneration.
    """
    import json

    try:
        knowledge_path = DEFAULT_OBSERVATION_STORE_PATH / "command_knowledge.json"
        structure_path = DEFAULT_OBSERVATION_STORE_PATH / "command_structure.json"
        output_path = DEFAULT_OBSERVATION_STORE_PATH / "condensed_command_knowledge.json"

        # Only regenerate if knowledge file exists
        if not knowledge_path.exists():
            return {"regenerated": False, "reason": "No command_knowledge.json found"}

        tiering = CommandTieringSystem(
            knowledge_path=str(knowledge_path),
            structure_path=str(structure_path),
            output_path=str(output_path),
        )

        if command:
            # Tier only the specific command and update the condensed store
            commands, _ = tiering.load_data()

            # Normalize command name (handle with/without dash)
            cmd_key = command if command in commands else f"-{command.lstrip('-')}"

            if cmd_key not in commands:
                return {"regenerated": False, "reason": f"Command {command} not found in knowledge"}

            # Generate tiers for just this command
            tiered = tiering.generate_tiers_for_command(cmd_key, commands[cmd_key])

            # Load existing condensed knowledge and update it
            if output_path.exists():
                with open(output_path, "r", encoding="utf-8") as f:
                    condensed_data = json.load(f)
            else:
                condensed_data = {"commands": {}, "metadata": {}}

            # Update the specific command
            condensed_data["commands"][cmd_key] = tiered.to_dict()

            # Save back
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(condensed_data, f, indent=2)

            # Invalidate the in-memory cache so subsequent queries see the new data
            invalidate_condensed_command_cache()

            return {
                "regenerated": True,
                "command": cmd_key,
                "mode": "single_command",
            }
        else:
            # Tier all commands (slow - use sparingly)
            store = tiering.generate_all_tiers()

            # Invalidate the in-memory cache so subsequent queries see the new data
            invalidate_condensed_command_cache()

            return {
                "regenerated": True,
                "commands_tiered": store.command_count,
                "token_savings": f"{store.reduction_percent:.1f}%",
                "mode": "all_commands",
            }
    except Exception as e:
        logger.error(f"Failed to regenerate tiered knowledge: {e}")
        return {"regenerated": False, "error": str(e)}


async def _poll_for_prompt_change(
    call_rhino_func,
    previous_prompt: str | None,
    timeout_ms: int = 2000,
    poll_interval_ms: int = 100,
    stable_count_required: int = 2
) -> dict:
    """
    Poll until the command prompt changes from the previous value.

    This solves the stale prompt bug where Rhino hasn't updated its CommandPrompt
    property yet when we read it after sending a command.

    Args:
        call_rhino_func: The async function to call Rhino endpoints
        previous_prompt: The prompt text before the command was sent
        timeout_ms: Maximum time to wait for change (default 2000ms)
        poll_interval_ms: Time between polls (default 100ms)
        stable_count_required: Number of consecutive same readings to consider stable

    Returns:
        The prompt response dict with updated prompt data
    """
    import asyncio

    elapsed = 0
    stable_count = 0
    last_prompt = None
    last_response = None

    # Initial delay to let Rhino process
    await asyncio.sleep(0.1)
    elapsed += 100

    while elapsed < timeout_ms:
        response = await call_rhino_func("/command/prompt", "GET")
        current_prompt = response.get("data", {}).get("prompt", "Command")

        # If prompt has changed from previous, track stability
        if current_prompt != previous_prompt:
            if current_prompt == last_prompt:
                stable_count += 1
                if stable_count >= stable_count_required:
                    return response
            else:
                last_prompt = current_prompt
                last_response = response
                stable_count = 1

        await asyncio.sleep(poll_interval_ms / 1000)
        elapsed += poll_interval_ms

    # Timeout - return whatever we have (might be the changed prompt even if not fully stable)
    if last_response is not None:
        return last_response

    # Fall back to final read
    return await call_rhino_func("/command/prompt", "GET")


mcp = Server(
    "rook",
    instructions=(
        "Rook connects AI to Rhino 3D and Grasshopper for geometry creation, "
        "parametric modeling, and scene queries. "
        "Call rhino_ping to verify the connection — it should return pong. "
        "If all tools suddenly hang, a modal dialog is blocking Rhino's UI thread. "
        "Only the user can dismiss it by switching to the Rhino window."
    ),
)


@mcp.list_tools()
async def list_tools() -> list[Tool]:
    """List all available Rhino tools."""

    all_tools = [
        Tool(
            name="rhino_instances",
            description="List all active Rhino instances running the Rook plugin. Returns port, process ID, start time, and document name for each instance. Use this when working with multiple Rhino windows.",
            inputSchema={"type": "object", "properties": {}, "required": []}
        ),
        Tool(
            name="rhino_launch",
            description="""Launch Rhino if it is not already running. Starts the Rhino 8 process and waits for the Rook native plugin to load and respond to pings. Returns immediately if Rhino is already running.

Use this before any Rhino operations to ensure Rhino is available. Safe to call multiple times.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "timeout": {
                        "type": "integer",
                        "description": "Max seconds to wait for Rhino to start (default: 120)"
                    }
                },
                "required": []
            }
        ),
        Tool(
            name="rhino_ping",
            description="Check if Rhino bridge is running and responsive. Optional 'port' parameter to ping a specific instance.",
            inputSchema={
                "type": "object",
                "properties": {
                    "port": {"type": "integer", "description": "Specific port to ping (for multi-instance)"}
                },
                "required": []
            }
        ),
        Tool(
            name="rhino_document",
            description="Get information about the current Rhino document including name, units, object count, and a summary of objects.",
            inputSchema={"type": "object", "properties": {}, "required": []}
        ),
        Tool(
            name="rhino_layers",
            description="Get all layers in the current document with their properties (color, visibility, etc).",
            inputSchema={"type": "object", "properties": {}, "required": []}
        ),
        Tool(
            name="rhino_objects",
            description="Query objects in the document with optional filters.",
            inputSchema={
                "type": "object",
                "properties": {
                    "layer": {"type": "string", "description": "Filter by layer path"},
                    "type": {"type": "string", "description": "Filter by object type (Point, Curve, Brep, Mesh, etc)"},
                    "name": {"type": "string", "description": "Filter by name (partial match)"},
                    "limit": {"type": "integer", "description": "Maximum objects to return (default 100, max 500)"},
                    "offset": {"type": "integer", "description": "Skip this many objects (for pagination)"}
                },
                "required": []
            }
        ),
        Tool(
            name="rhino_selection",
            description="Get currently selected objects in Rhino.",
            inputSchema={"type": "object", "properties": {}, "required": []}
        ),
        Tool(
            name="rhino_select",
            description="Select objects by their IDs or by layer.",
            inputSchema={
                "type": "object",
                "properties": {
                    "ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of object GUIDs to select"
                    },
                    "layer": {"type": "string", "description": "Select all objects on this layer"},
                    "clear": {"type": "boolean", "description": "Clear existing selection first (default true)"}
                },
                "required": []
            }
        ),
        Tool(
            name="rhino_geometry",
            description="Get detailed geometry information for a specific object by ID.",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Object GUID"}
                },
                "required": ["id"]
            }
        ),
        Tool(
            name="rhino_execute",
            description="Execute a Python script in Rhino using rhinoscriptsyntax. Use 'import rhinoscriptsyntax as rs' for geometry operations.",
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Python code to execute"}
                },
                "required": ["code"]
            }
        ),
        Tool(
            name="rhino_command",
            description="Run a Rhino command string. Use underscore prefix for language-independent commands (e.g., '_Line').",
            inputSchema={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Command string to execute"},
                    "echo": {"type": "boolean", "description": "Echo command to command line (default false)"}
                },
                "required": ["command"]
            }
        ),
        Tool(
            name="rhino_viewport",
            description="Capture the current viewport to a PNG file. Returns the file path — use the Read tool to view the image. "
                        "Supports standard views (Top, Front, Perspective, etc.) and display mode override. "
                        "Use rhino_views + rhino_views_restore to capture named views.",
            inputSchema={
                "type": "object",
                "properties": {
                    "width": {"type": "integer", "description": "Image width in pixels (default 800, max 4000)"},
                    "height": {"type": "integer", "description": "Image height in pixels (default 600, max 4000)"},
                    "view": {"type": "string", "description": "View to set before capture. Standard views: 'Top', 'Bottom', 'Front', 'Back', 'Left', 'Right', 'Perspective'. Also accepts named view names (use rhino_views to list)."},
                    "displayMode": {"type": "string", "description": "Display mode override: 'Shaded', 'Rendered', 'Wireframe', 'Ghosted', 'Arctic', etc."},
                    "zoomExtents": {"type": "boolean", "description": "Zoom to fit all objects before capture (default false)"},
                    "transparentBackground": {"type": "boolean", "description": "Transparent PNG background (default false)"},
                    "scale": {"type": "integer", "description": "Output scale multiplier 1-10 (default 1)"},
                    "drawGrid": {"type": "boolean", "description": "Draw the grid in the capture (default false)"},
                    "drawWorldAxes": {"type": "boolean", "description": "Draw world axes icon (default false)"},
                    "drawCPlaneAxes": {"type": "boolean", "description": "Draw construction plane axes (default false)"}
                },
                "required": []
            }
        ),
        Tool(
            name="rhino_views",
            description="List all named views saved in the document. Returns name and index for each view. "
                        "Use rhino_views_restore to activate a named view, then rhino_viewport to capture it.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="rhino_views_restore",
            description="Restore a named view by name. Sets the active viewport to the saved camera position and projection. "
                        "Use rhino_views to list available named views first.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Name of the named view to restore"}
                },
                "required": ["name"]
            }
        ),
        Tool(
            name="rhino_views_save",
            description="Save the current viewport camera as a named view. The view is saved to the document and can be "
                        "restored later with rhino_views_restore.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Name for the saved view"}
                },
                "required": ["name"]
            }
        ),
        Tool(
            name="rhino_display_modes",
            description="List all available display modes (Wireframe, Shaded, Rendered, Artistic, custom, etc). "
                        "Shows which mode is currently active on the viewport.",
            inputSchema={
                "type": "object",
                "properties": {},
            }
        ),
        Tool(
            name="rhino_display_mode_set",
            description="Set the active viewport's display mode persistently. Accepts a display mode name "
                        "(e.g. 'Wireframe', 'Shaded', 'Rendered', 'Artistic', 'Pen') or UUID. "
                        "Use rhino_display_modes to list available modes first.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Display mode name (case-insensitive), e.g. 'Shaded', 'Wireframe', 'Rendered'"},
                    "id": {"type": "string", "description": "Display mode UUID (alternative to name)"}
                },
            }
        ),
        Tool(
            name="rhino_create",
            description="""Create geometry in Rhino. Supports: POINT, LINE, POLYLINE, CIRCLE, ARC, RECTANGLE, BOX, SPHERE, CYLINDER, CONE.

Examples:
- Point: {"type": "POINT", "point": [0, 0, 0]}
- Line: {"type": "LINE", "start": [0, 0, 0], "end": [10, 0, 0]}
- Circle: {"type": "CIRCLE", "center": [0, 0, 0], "radius": 5}
- Box: {"type": "BOX", "origin": [0, 0, 0], "width": 10, "depth": 10, "height": 5}
- Sphere: {"type": "SPHERE", "center": [0, 0, 0], "radius": 5}

Optional for all: "name", "layer", "color" (as [r,g,b] or {"r":255,"g":0,"b":0})""",
            inputSchema={
                "type": "object",
                "properties": {
                    "type": {"type": "string", "description": "Geometry type: POINT, LINE, POLYLINE, CIRCLE, ARC, RECTANGLE, BOX, SPHERE, CYLINDER, CONE"},
                    "name": {"type": "string", "description": "Object name"},
                    "layer": {"type": "string", "description": "Layer path"},
                    "color": {"description": "Color as [r,g,b] array or {r,g,b} object"},
                    "point": {"type": "array", "description": "For POINT: [x, y, z]"},
                    "start": {"type": "array", "description": "For LINE: start point [x, y, z]"},
                    "end": {"type": "array", "description": "For LINE: end point [x, y, z]"},
                    "points": {"type": "array", "description": "For POLYLINE: array of [x, y, z] points"},
                    "center": {"type": "array", "description": "For CIRCLE, ARC, SPHERE, CYLINDER, CONE: center [x, y, z]"},
                    "radius": {"type": "number", "description": "For CIRCLE, ARC, SPHERE, CYLINDER, CONE"},
                    "origin": {"type": "array", "description": "For RECTANGLE, BOX: origin [x, y, z]"},
                    "width": {"type": "number", "description": "For RECTANGLE, BOX"},
                    "height": {"type": "number", "description": "For RECTANGLE, BOX, CYLINDER, CONE"},
                    "depth": {"type": "number", "description": "For BOX"},
                    "startAngle": {"type": "number", "description": "For ARC: start angle in degrees"},
                    "endAngle": {"type": "number", "description": "For ARC: end angle in degrees"}
                },
                "required": ["type"]
            }
        ),
        # Geometry operations
        Tool(
            name="rhino_delete",
            description="Delete objects by their IDs.",
            inputSchema={
                "type": "object",
                "properties": {
                    "ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of object GUIDs to delete"
                    }
                },
                "required": ["ids"]
            }
        ),
        Tool(
            name="rhino_transform",
            description="""Transform objects (move, rotate, scale, mirror).

Examples:
- Move: {"ids": ["guid"], "operation": "move", "vector": [10, 0, 0]}
- Rotate: {"ids": ["guid"], "operation": "rotate", "angle": 45, "axis": [0, 0, 1], "center": [0, 0, 0]}
- Scale: {"ids": ["guid"], "operation": "scale", "factor": 2, "center": [0, 0, 0]}
- Mirror: {"ids": ["guid"], "operation": "mirror", "planeOrigin": [0, 0, 0], "planeNormal": [1, 0, 0]}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of object GUIDs to transform"
                    },
                    "operation": {"type": "string", "description": "Transform type: move, rotate, scale, mirror"},
                    "vector": {"type": "array", "description": "For move: translation vector [x, y, z]"},
                    "angle": {"type": "number", "description": "For rotate: angle in degrees"},
                    "axis": {"type": "array", "description": "For rotate: rotation axis [x, y, z]"},
                    "center": {"type": "array", "description": "For rotate/scale: center point [x, y, z]"},
                    "factor": {"type": "number", "description": "For scale: scale factor"},
                    "planeOrigin": {"type": "array", "description": "For mirror: plane origin [x, y, z]"},
                    "planeNormal": {"type": "array", "description": "For mirror: plane normal [x, y, z]"}
                },
                "required": ["ids", "operation"]
            }
        ),
        Tool(
            name="rhino_copy",
            description="Copy objects, optionally with an offset.",
            inputSchema={
                "type": "object",
                "properties": {
                    "ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of object GUIDs to copy"
                    },
                    "offset": {"type": "array", "description": "Optional offset vector [x, y, z]"}
                },
                "required": ["ids"]
            }
        ),
        # Layer management
        Tool(
            name="rhino_layer_create",
            description="Create a new layer with optional properties.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Layer name. Must be a single segment; do not include '::'"},
                    "color": {"description": "Layer color as [r, g, b] array"},
                    "plotColor": {"description": "Print color as [r, g, b] array"},
                    "plotWeight": {"type": "number", "description": "Print width in mm (0 = default)"},
                    "parent": {"type": "string", "description": "Existing parent layer name or full path"},
                    "visible": {"type": "boolean", "description": "Layer visibility (default true)"},
                    "locked": {"type": "boolean", "description": "Layer locked state (default false)"},
                    "linetype": {"type": "string", "description": "Linetype name (e.g. 'Continuous', 'Dashed')"},
                    "material": {"type": "string", "description": "Render material name"}
                },
                "required": ["name"]
            }
        ),
        Tool(
            name="rhino_layer_create_batch",
            description="Create multiple layers atomically from explicit key/parentKey relationships.",
            inputSchema={
                "type": "object",
                "properties": {
                    "layers": {
                        "type": "array",
                        "description": "Layer specs to create. Each item must include {key, name} and may include {parentKey, color, plotColor, plotWeight, linetype, material, visible, locked}.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "key": {"type": "string", "description": "Unique local key for this batch item"},
                                "name": {"type": "string", "description": "Single-segment layer name for this node"},
                                "parentKey": {"type": "string", "description": "Optional local key of this item's parent within the same batch"},
                                "color": {"description": "Layer color as [r, g, b] array"},
                                "plotColor": {"description": "Print color as [r, g, b] array"},
                                "plotWeight": {"type": "number", "description": "Print width in mm (0 = default)"},
                                "visible": {"type": "boolean", "description": "Layer visibility (default true)"},
                                "locked": {"type": "boolean", "description": "Layer locked state (default false)"},
                                "linetype": {"type": "string", "description": "Linetype name"},
                                "material": {"type": "string", "description": "Render material name"}
                            },
                            "required": ["key", "name"]
                        }
                    },
                    "rootParent": {"type": "string", "description": "Optional existing parent layer name or full path for top-level batch items"}
                },
                "required": ["layers"]
            }
        ),
        Tool(
            name="rhino_layer_delete",
            description="Delete an empty layer.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Layer name to delete"}
                },
                "required": ["name"]
            }
        ),
        Tool(
            name="rhino_layer_visibility",
            description="Set layer visibility.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Layer name"},
                    "visible": {"type": "boolean", "description": "Visibility state"}
                },
                "required": ["name", "visible"]
            }
        ),
        Tool(
            name="rhino_layer_lock",
            description="Set layer lock state.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Layer name"},
                    "locked": {"type": "boolean", "description": "Lock state"}
                },
                "required": ["name", "locked"]
            }
        ),
        Tool(
            name="rhino_layer_current",
            description="Set the current layer.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Layer name to set as current"}
                },
                "required": ["name"]
            }
        ),
        Tool(
            name="rhino_layer_set_properties",
            description="""Set any combination of layer properties in a single call. The 'set' object can include any subset of: rename, parent, color, plotColor, plotWeight, linetype, linetypeIndex, material, materialIndex, visible, locked. Only provided fields are modified.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Target layer (name or full path)"},
                    "set": {
                        "type": "object",
                        "description": "Properties to modify. All fields optional.",
                        "properties": {
                            "rename": {"type": "string", "description": "New name for the layer"},
                            "parent": {"type": ["string", "null"], "description": "New parent layer path, or null to make top-level"},
                            "color": {"type": "array", "items": {"type": "integer"}, "description": "[r, g, b] display color"},
                            "plotColor": {"type": "array", "items": {"type": "integer"}, "description": "[r, g, b] print color"},
                            "plotWeight": {"type": "number", "description": "Print width in mm (0 = default)"},
                            "linetype": {"type": "string", "description": "Linetype name (e.g. 'Continuous', 'Dashed')"},
                            "linetypeIndex": {"type": "integer", "description": "Linetype table index"},
                            "material": {"type": "string", "description": "Render material name"},
                            "materialIndex": {"type": "integer", "description": "Material table index"},
                            "visible": {"type": "boolean", "description": "Visibility state"},
                            "locked": {"type": "boolean", "description": "Lock state"}
                        }
                    }
                },
                "required": ["name", "set"]
            }
        ),
        Tool(
            name="rhino_layer_rename",
            description="Rename a layer. All objects remain on the layer.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Current layer name or full path"},
                    "newName": {"type": "string", "description": "New name (single segment, no :: separators)"}
                },
                "required": ["name", "newName"]
            }
        ),
        Tool(
            name="rhino_layer_move_objects",
            description="Move all objects from one layer to another. Source layer is not deleted.",
            inputSchema={
                "type": "object",
                "properties": {
                    "source": {"type": "string", "description": "Source layer name or full path"},
                    "target": {"type": "string", "description": "Target layer name or full path"}
                },
                "required": ["source", "target"]
            }
        ),
        Tool(
            name="rhino_layer_merge",
            description="Move all objects from source to target layer, then delete the source layer. Source must have no child layers and must not be the current layer.",
            inputSchema={
                "type": "object",
                "properties": {
                    "source": {"type": "string", "description": "Source layer to merge away"},
                    "target": {"type": "string", "description": "Target layer to receive objects"}
                },
                "required": ["source", "target"]
            }
        ),
        Tool(
            name="rhino_layer_dependencies",
            description="Analyze what holds a layer alive: direct objects, block definition references, child layers, and whether it is the current layer. Returns canDelete indicating if the layer can be safely deleted.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Layer name or full path to analyze"}
                },
                "required": ["name"]
            }
        ),
        # Advanced selection
        Tool(
            name="rhino_select_by_type",
            description="Select objects by their geometry type.",
            inputSchema={
                "type": "object",
                "properties": {
                    "type": {"type": "string", "description": "Object type: Point, Curve, Brep, Mesh, etc."},
                    "clear": {"type": "boolean", "description": "Clear existing selection first (default true)"}
                },
                "required": ["type"]
            }
        ),
        Tool(
            name="rhino_select_by_name",
            description="Select objects by name pattern (supports * and ? wildcards).",
            inputSchema={
                "type": "object",
                "properties": {
                    "namePattern": {"type": "string", "description": "Name pattern (e.g., 'Box*' or 'Object_?')"},
                    "clear": {"type": "boolean", "description": "Clear existing selection first (default true)"}
                },
                "required": ["namePattern"]
            }
        ),
        Tool(
            name="rhino_select_all",
            description="Select all objects.",
            inputSchema={"type": "object", "properties": {}, "required": []}
        ),
        Tool(
            name="rhino_select_none",
            description="Deselect all objects.",
            inputSchema={"type": "object", "properties": {}, "required": []}
        ),
        Tool(
            name="rhino_select_invert",
            description="Invert the current selection.",
            inputSchema={"type": "object", "properties": {}, "required": []}
        ),
        Tool(
            name="rhino_deselect",
            description="Deselect specific objects by their IDs.",
            inputSchema={
                "type": "object",
                "properties": {
                    "ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of object GUIDs to deselect"
                    }
                },
                "required": ["ids"]
            }
        ),
        # Measurement/analysis tools
        Tool(
            name="rhino_measure_distance",
            description="Measure distance between two points or two objects.",
            inputSchema={
                "type": "object",
                "properties": {
                    "from": {"type": "array", "description": "Start point [x, y, z]"},
                    "to": {"type": "array", "description": "End point [x, y, z]"},
                    "fromId": {"type": "string", "description": "First object GUID (alternative to 'from' point)"},
                    "toId": {"type": "string", "description": "Second object GUID (alternative to 'to' point)"}
                },
                "required": []
            }
        ),
        Tool(
            name="rhino_measure_area",
            description="Calculate the surface area of an object.",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Object GUID"}
                },
                "required": ["id"]
            }
        ),
        Tool(
            name="rhino_measure_volume",
            description="Calculate the volume of a closed solid.",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Object GUID (must be a closed solid)"}
                },
                "required": ["id"]
            }
        ),
        Tool(
            name="rhino_measure_length",
            description="Calculate the length of a curve.",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Curve object GUID"}
                },
                "required": ["id"]
            }
        ),
        Tool(
            name="rhino_measure_bbox",
            description="Get the bounding box of an object.",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Object GUID"}
                },
                "required": ["id"]
            }
        ),
        Tool(
            name="rhino_measure_centroid",
            description="Get the centroid/center point of an object.",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Object GUID"}
                },
                "required": ["id"]
            }
        ),
        # Boolean operations
        Tool(
            name="rhino_boolean",
            description="""Perform boolean operations on solids (union, difference, intersection).

Examples:
- Union: {"operation": "union", "ids": ["guid1", "guid2"]}
- Difference: {"operation": "difference", "targetId": "guid1", "toolIds": ["guid2"]}
- Intersection: {"operation": "intersection", "ids": ["guid1", "guid2"]}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "operation": {"type": "string", "description": "Boolean operation: union, difference, intersection"},
                    "ids": {"type": "array", "items": {"type": "string"}, "description": "Object GUIDs for union/intersection"},
                    "targetId": {"type": "string", "description": "Target object GUID for difference"},
                    "toolIds": {"type": "array", "items": {"type": "string"}, "description": "Tool object GUIDs for difference"},
                    "deleteInputs": {"type": "boolean", "description": "Delete input objects after operation (default true)"}
                },
                "required": ["operation"]
            }
        ),
        # Surface creation tools
        Tool(
            name="rhino_loft",
            description="Create a lofted surface through multiple curves.",
            inputSchema={
                "type": "object",
                "properties": {
                    "type": {"type": "string", "const": "LOFT"},
                    "curveIds": {"type": "array", "items": {"type": "string"}, "description": "Curve GUIDs to loft through"},
                    "closed": {"type": "boolean", "description": "Create closed loft (default false)"},
                    "name": {"type": "string", "description": "Object name"},
                    "layer": {"type": "string", "description": "Layer path"}
                },
                "required": ["curveIds"]
            }
        ),
        Tool(
            name="rhino_sweep",
            description="Create a swept surface along a rail curve.",
            inputSchema={
                "type": "object",
                "properties": {
                    "type": {"type": "string", "const": "SWEEP"},
                    "railId": {"type": "string", "description": "Rail curve GUID"},
                    "profileIds": {"type": "array", "items": {"type": "string"}, "description": "Profile curve GUIDs"},
                    "name": {"type": "string", "description": "Object name"},
                    "layer": {"type": "string", "description": "Layer path"}
                },
                "required": ["railId", "profileIds"]
            }
        ),
        Tool(
            name="rhino_extrude",
            description="Extrude a curve or surface along a direction.",
            inputSchema={
                "type": "object",
                "properties": {
                    "type": {"type": "string", "const": "EXTRUSION"},
                    "curveId": {"type": "string", "description": "Curve GUID to extrude"},
                    "direction": {"type": "array", "description": "Extrusion direction [x, y, z]"},
                    "distance": {"type": "number", "description": "Extrusion distance"},
                    "cap": {"type": "boolean", "description": "Cap ends if curve is closed (default true)"},
                    "name": {"type": "string", "description": "Object name"},
                    "layer": {"type": "string", "description": "Layer path"}
                },
                "required": ["curveId"]
            }
        ),
        # Import/Export
        Tool(
            name="rhino_import",
            description="Import a file into Rhino (supports 3dm, obj, stl, dwg, dxf, step, iges).",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path to import"},
                    "targetLayer": {"type": "string", "description": "Layer to place imported objects"}
                },
                "required": ["path"]
            }
        ),
        Tool(
            name="rhino_export",
            description="Export objects to a file (supports 3dm, obj, stl, dwg, dxf, step, iges).",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path to export to"},
                    "ids": {"type": "array", "items": {"type": "string"}, "description": "Object GUIDs to export (optional)"},
                    "selection": {"type": "boolean", "description": "Export selected objects (default false)"}
                },
                "required": ["path"]
            }
        ),
        # Groups
        Tool(
            name="rhino_group",
            description="Create a group from objects.",
            inputSchema={
                "type": "object",
                "properties": {
                    "ids": {"type": "array", "items": {"type": "string"}, "description": "Object GUIDs to group"},
                    "name": {"type": "string", "description": "Group name"}
                },
                "required": ["ids"]
            }
        ),
        # Blocks
        Tool(
            name="rhino_blocks",
            description="List all block definitions in the document with their instance counts.",
            inputSchema={"type": "object", "properties": {}, "required": []}
        ),
        Tool(
            name="rhino_block_create",
            description="Create a block definition from objects.",
            inputSchema={
                "type": "object",
                "properties": {
                    "ids": {"type": "array", "items": {"type": "string"}, "description": "Object GUIDs to include in block"},
                    "name": {"type": "string", "description": "Block name"},
                    "basePoint": {"type": "array", "description": "Block base point [x, y, z]"},
                    "replaceWithInstance": {"type": "boolean", "description": "Replace objects with block instance (default true)"}
                },
                "required": ["ids", "name", "basePoint"]
            }
        ),
        Tool(
            name="rhino_block_insert",
            description="""Insert a block instance at a specified point with optional scale and rotation.

Examples:
- Basic insert: {"name": "MyBlock", "point": [10, 10, 0]}
- With scale: {"name": "MyBlock", "point": [10, 10, 0], "scale": 2.0}
- With rotation: {"name": "MyBlock", "point": [10, 10, 0], "rotation": 45}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Block definition name to insert"},
                    "point": {"type": "array", "description": "Insertion point [x, y, z]"},
                    "scale": {"type": "number", "description": "Uniform scale factor (default 1.0)"},
                    "rotation": {"type": "number", "description": "Rotation angle in degrees around Z axis (default 0)"}
                },
                "required": ["name", "point"]
            }
        ),
        Tool(
            name="rhino_block_explode",
            description="Explode a block instance into individual geometry objects. The block definition is preserved.",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Block instance GUID to explode"}
                },
                "required": ["id"]
            }
        ),
        Tool(
            name="rhino_block_delete",
            description="Delete a block definition and optionally all its instances.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Block definition name to delete"},
                    "deleteInstances": {"type": "boolean", "description": "Also delete all instances of this block (default true)"}
                },
                "required": ["name"]
            }
        ),
        # Block Modification Operations (Phase 1)
        Tool(
            name="rhino_block_rename",
            description="Rename a block definition.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Current block name"},
                    "newName": {"type": "string", "description": "New block name"}
                },
                "required": ["name", "newName"]
            }
        ),
        Tool(
            name="rhino_block_description",
            description="Set or update a block's description and optional URL.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Block name"},
                    "description": {"type": "string", "description": "Block description text"},
                    "url": {"type": "string", "description": "Optional URL for block documentation"},
                    "urlDescription": {"type": "string", "description": "Description of the URL"}
                },
                "required": ["name"]
            }
        ),
        Tool(
            name="rhino_block_info",
            description="Get detailed information about a block definition including geometry, instances, and metadata.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Block name to get info for"}
                },
                "required": ["name"]
            }
        ),
        # Block Geometry Operations (Phase 2)
        Tool(
            name="rhino_block_add_objects",
            description="Add objects to an existing block definition.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Block name"},
                    "ids": {"type": "array", "items": {"type": "string"}, "description": "Object GUIDs to add to block"},
                    "deleteOriginals": {"type": "boolean", "description": "Delete original objects after adding (default true)"}
                },
                "required": ["name", "ids"]
            }
        ),
        Tool(
            name="rhino_block_remove_objects",
            description="Remove objects from a block definition by index.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Block name"},
                    "indices": {"type": "array", "items": {"type": "integer"}, "description": "Indices of objects to remove (0-based)"}
                },
                "required": ["name", "indices"]
            }
        ),
        Tool(
            name="rhino_block_replace_geometry",
            description="Replace all geometry in a block definition with new objects.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Block name"},
                    "ids": {"type": "array", "items": {"type": "string"}, "description": "Object GUIDs to use as new block geometry"},
                    "deleteOriginals": {"type": "boolean", "description": "Delete original objects after replacing (default true)"}
                },
                "required": ["name", "ids"]
            }
        ),
        Tool(
            name="rhino_block_replace_object_geometry",
            description="Replace the geometry of a single object within a block definition by index. The replacement geometry comes from a document-resident object (by GUID). Use rhino_block_objects_detailed to find indices first.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Block definition name"},
                    "index": {"type": "integer", "description": "0-based index of the object to replace"},
                    "sourceId": {"type": "string", "description": "GUID of document object to use as replacement geometry"},
                    "deleteOriginal": {"type": "boolean", "description": "Delete source object after replacement (default true)"}
                },
                "required": ["name", "index", "sourceId"]
            }
        ),
        Tool(
            name="rhino_block_transform_object",
            description="Transform (move/rotate/scale) objects within a block definition by index. Coordinates are in definition-local space (relative to the block's insertion point origin). All instances of the block update automatically. Use rhino_block_objects_detailed to find indices first.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Block definition name"},
                    "indices": {"type": "array", "items": {"type": "integer"}, "description": "0-based indices of objects to transform"},
                    "transform": {"type": "object", "description": "Transform spec: {type, ...params}. move: {type:'move', x, y, z}. rotate: {type:'rotate', angle (degrees), axis:[x,y,z], center:[x,y,z]}. scale: {type:'scale', factor, center:[x,y,z]}. scale3d: {type:'scale3d', x, y, z, center:[x,y,z]}."}
                },
                "required": ["name", "indices", "transform"]
            }
        ),
        Tool(
            name="rhino_block_set_layers",
            description="Set the layer assignments of objects within a block definition. Use 'layer' to set all objects to one layer, or 'mappings' for per-object control. Mappings override the bulk layer.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Block definition name"},
                    "layer": {"type": "string", "description": "Set all objects to this layer (optional)"},
                    "mappings": {"type": "array", "items": {
                        "type": "object",
                        "properties": {
                            "index": {"type": "integer", "description": "Object index within block"},
                            "layer": {"type": "string", "description": "Target layer full path"}
                        }, "required": ["index", "layer"]
                    }, "description": "Per-object layer assignments by index (optional, overrides 'layer')"}
                },
                "required": ["name"]
            }
        ),
        Tool(
            name="rhino_block_set_materials",
            description="Set the material assignments of objects within a block definition. Use 'material' to set all objects to one material, or 'mappings' for per-object control. Mappings override the bulk material. Materials must exist in the document first (use rhino_material_ops to create them).",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Block definition name"},
                    "material": {"type": "string", "description": "Set all objects to this material (optional)"},
                    "mappings": {"type": "array", "items": {
                        "type": "object",
                        "properties": {
                            "index": {"type": "integer", "description": "Object index within block"},
                            "material": {"type": "string", "description": "Material name"}
                        }, "required": ["index", "material"]
                    }, "description": "Per-object material assignments by index (optional, overrides 'material')"}
                },
                "required": ["name"]
            }
        ),
        # Block Instance Properties (Phase 6)
        Tool(
            name="rhino_block_set_instance_properties",
            description="Set properties on specific block instances. Supports name, layer, color, material, and userStrings. All property fields are optional — only provided ones are changed.",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Single instance GUID"},
                    "ids": {"type": "array", "items": {"type": "string"}, "description": "Multiple instance GUIDs"},
                    "name": {"type": "string", "description": "Set instance name"},
                    "layer": {"type": "string", "description": "Set instance layer"},
                    "color": {"type": "array", "items": {"type": "integer"}, "description": "Set instance color [r, g, b]"},
                    "material": {"type": "string", "description": "Set instance material name"},
                    "userStrings": {"type": "object", "description": "Key-value pairs to set as user strings"}
                },
                "required": []
            }
        ),
        Tool(
            name="rhino_block_set_instance_visibility",
            description="Hide or show block instances.",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Single instance GUID"},
                    "ids": {"type": "array", "items": {"type": "string"}, "description": "Multiple instance GUIDs"},
                    "visible": {"type": "boolean", "description": "true to show, false to hide"}
                },
                "required": ["visible"]
            }
        ),
        # Block Instance Transforms (Phase 7)
        Tool(
            name="rhino_block_transform_instance",
            description="Apply INCREMENTAL transforms to an existing block instance. Transforms compound on the instance's existing transform. Supports move, rotate (Z-axis degrees), scale (uniform or [sx,sy,sz]), and mirror. All transform fields optional, applied in order: scale → rotate → move → mirror.",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Instance GUID to transform"},
                    "move": {"type": "array", "items": {"type": "number"}, "description": "Translation [dx, dy, dz]"},
                    "rotate": {"type": "number", "description": "Rotation in degrees around Z axis at instance pivot"},
                    "scale": {"description": "Uniform number or [sx, sy, sz] array"},
                    "mirror": {"type": "object", "properties": {
                        "normal": {"type": "array", "items": {"type": "number"}, "description": "Mirror plane normal [x, y, z]"},
                        "origin": {"type": "array", "items": {"type": "number"}, "description": "Mirror plane origin [x, y, z]"}
                    }, "description": "Mirror across a plane"}
                },
                "required": ["id"]
            }
        ),
        Tool(
            name="rhino_block_array_instances",
            description="""Create a linear or circular array of block instances.

Linear: {"name": "Block", "count": 5, "direction": [10, 0, 0], "basePoint": [0, 0, 0]}
Circular: {"name": "Block", "count": 8, "center": [0, 0, 0], "radius": 10}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Block definition name"},
                    "count": {"type": "integer", "description": "Number of instances to create"},
                    "direction": {"type": "array", "items": {"type": "number"}, "description": "Linear: spacing vector [dx, dy, dz]"},
                    "basePoint": {"type": "array", "items": {"type": "number"}, "description": "Linear: start point [x, y, z] (default origin)"},
                    "center": {"type": "array", "items": {"type": "number"}, "description": "Circular: center point [x, y, z]"},
                    "radius": {"type": "number", "description": "Circular: radius"},
                    "startAngle": {"type": "number", "description": "Circular: start angle in degrees (default 0)"},
                    "endAngle": {"type": "number", "description": "Circular: end angle in degrees (default 360)"},
                    "scale": {"type": "number", "description": "Uniform scale for all instances (default 1.0)"}
                },
                "required": ["name", "count"]
            }
        ),
        # Block Object Properties (Phase 8)
        Tool(
            name="rhino_block_set_object_colors",
            description="Set colors of objects within a block definition. Use 'color' for bulk or 'mappings' for per-object control.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Block definition name"},
                    "color": {"type": "array", "items": {"type": "integer"}, "description": "Set all objects to this color [r, g, b]"},
                    "mappings": {"type": "array", "items": {
                        "type": "object",
                        "properties": {
                            "index": {"type": "integer", "description": "Object index"},
                            "color": {"type": "array", "items": {"type": "integer"}, "description": "[r, g, b]"}
                        }, "required": ["index", "color"]
                    }, "description": "Per-object color assignments"}
                },
                "required": ["name"]
            }
        ),
        Tool(
            name="rhino_block_set_object_names",
            description="Set names of objects within a block definition.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Block definition name"},
                    "mappings": {"type": "array", "items": {
                        "type": "object",
                        "properties": {
                            "index": {"type": "integer", "description": "Object index"},
                            "objectName": {"type": "string", "description": "Name for this object"}
                        }, "required": ["index", "objectName"]
                    }, "description": "Per-object name assignments"}
                },
                "required": ["name", "mappings"]
            }
        ),
        Tool(
            name="rhino_block_set_object_user_strings",
            description="Set user strings (custom metadata) on objects within a block definition. Use 'userStrings' for bulk or 'mappings' for per-object.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Block definition name"},
                    "userStrings": {"type": "object", "description": "Key-value pairs applied to ALL objects"},
                    "mappings": {"type": "array", "items": {
                        "type": "object",
                        "properties": {
                            "index": {"type": "integer", "description": "Object index"},
                            "userStrings": {"type": "object", "description": "Key-value pairs for this object"}
                        }, "required": ["index", "userStrings"]
                    }, "description": "Per-object user string assignments"}
                },
                "required": ["name"]
            }
        ),
        # Block Definition Metadata (Phase 9)
        Tool(
            name="rhino_block_user_strings",
            description="""Get, set, or delete user strings on a block definition.

Actions: 'get' (default), 'set' (requires userStrings object), 'delete' (requires keys array).
Stored in document string table under 'RookBlock::{blockName}' section.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Block definition name"},
                    "action": {"type": "string", "enum": ["get", "set", "delete"], "description": "Action to perform (default 'get')"},
                    "userStrings": {"type": "object", "description": "Key-value pairs to set (for 'set' action)"},
                    "keys": {"type": "array", "items": {"type": "string"}, "description": "Keys to delete (for 'delete' action)"}
                },
                "required": ["name"]
            }
        ),
        # Enhanced Block Queries (Phase 10)
        Tool(
            name="rhino_block_find_instances",
            description="Find block instances matching criteria. All filters optional: block name, layer, name pattern (with * wildcards), bounding box region.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Block definition name (optional — searches all if omitted)"},
                    "layer": {"type": "string", "description": "Filter by instance layer"},
                    "namePattern": {"type": "string", "description": "Filter by instance name (supports * wildcards)"},
                    "bbox": {"type": "object", "properties": {
                        "min": {"type": "array", "items": {"type": "number"}, "description": "[x, y, z]"},
                        "max": {"type": "array", "items": {"type": "number"}, "description": "[x, y, z]"}
                    }, "description": "Filter by bounding box region"}
                },
                "required": []
            }
        ),
        Tool(
            name="rhino_block_objects_detailed",
            description="Get full attribute details for all objects in a block definition. Returns name, layer, color, material, user strings, bounding box, and visibility per object. Optionally includes typed geometry detail (face counts, edge counts, curve lengths, etc.).",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Block definition name"},
                    "geometry": {"type": "boolean", "description": "Include typed geometry detail per object (default false)"}
                },
                "required": ["name"]
            }
        ),
        # Block Instance Operations (Phase 3)
        Tool(
            name="rhino_block_instances",
            description="""Get all instances of a block definition.

Returns instance details including ID, insertion point, scale, rotation, and layer.

Examples:
- Get instances: {"name": "MyBlock"}
- With nested depth: {"name": "MyBlock", "depth": 1}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Block definition name"},
                    "depth": {"type": "integer", "description": "Nesting depth to search (0 = top-level only, default 0)"}
                },
                "required": ["name"]
            }
        ),
        Tool(
            name="rhino_block_replace_instance",
            description="Replace a block instance with a different block definition.",
            inputSchema={
                "type": "object",
                "properties": {
                    "instanceId": {"type": "string", "description": "Block instance GUID to replace"},
                    "newBlockName": {"type": "string", "description": "Name of block definition to use instead"}
                },
                "required": ["instanceId", "newBlockName"]
            }
        ),
        Tool(
            name="rhino_block_reset_scale",
            description="Reset a block instance's scale to uniform 1,1,1.",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Block instance GUID"},
                    "mode": {"type": "string", "description": "Reset mode: 'uniform' or 'automatic' (default 'uniform')"}
                },
                "required": ["id"]
            }
        ),
        # Linked Block Operations (Phase 4)
        Tool(
            name="rhino_block_link",
            description="Create a linked block from an external file.",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to external file (.3dm)"},
                    "name": {"type": "string", "description": "Block definition name"},
                    "updateType": {"type": "string", "description": "Link type: 'static', 'linked', or 'linkedAndEmbedded' (default 'linked')"},
                    "insertionPoint": {"type": "array", "description": "Insertion point [x, y, z] (default [0,0,0])"}
                },
                "required": ["path", "name"]
            }
        ),
        Tool(
            name="rhino_block_refresh",
            description="Refresh a linked block from its source file.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Linked block name to refresh"}
                },
                "required": ["name"]
            }
        ),
        Tool(
            name="rhino_block_unlink",
            description="Convert a linked block to an embedded block, breaking the link to external file.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Linked block name to unlink"}
                },
                "required": ["name"]
            }
        ),
        # Block Utility Operations (Phase 5)
        Tool(
            name="rhino_block_purge",
            description="Purge unused and/or deleted block definitions from the document.",
            inputSchema={
                "type": "object",
                "properties": {
                    "unused": {"type": "boolean", "description": "Purge blocks with no instances (default true)"},
                    "deleted": {"type": "boolean", "description": "Purge deleted blocks (default true)"}
                },
                "required": []
            }
        ),
        Tool(
            name="rhino_block_duplicate",
            description="Duplicate a block definition with a new name.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Source block name"},
                    "newName": {"type": "string", "description": "New block name"}
                },
                "required": ["name", "newName"]
            }
        ),
        Tool(
            name="rhino_block_nested",
            description="Get the nested block hierarchy for a block definition.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Block name to get hierarchy for"}
                },
                "required": ["name"]
            }
        ),
        # Block Deduplication (Phase 6)
        Tool(
            name="rhino_block_compare",
            description="""Bulk geometric comparison of block definitions. Returns shape metrics,
type histograms, area/volume, and nested instance data for each definition.
Partial success is normal — unknown names appear in errors[], the call succeeds
if at least one definition resolves.

Example: {"names": ["RAILING WEST", "RAILING WEST 2", "RAILING EAST"]}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Block definition names to compare"
                    },
                    "includeNestedOriginalIds": {
                        "type": "boolean",
                        "description": "Include full nested original-object-id arrays (default false)"
                    }
                },
                "required": ["names"]
            }
        ),
        Tool(
            name="rhino_block_merge",
            description="""Merge block definitions by repointing all instances of source definitions
to a single target definition. Supports dry-run mode for review before mutation.

The model looks identical after merge — same geometry in same positions, fewer definitions.
Does NOT purge source definitions — call rhino_block_purge separately.
Execute mode is single-undo recoverable, not transactional.

Example dry run: {"target": "RAILING WEST", "sources": ["RAILING WEST 2"], "dryRun": true}
Example execute: {"target": "RAILING WEST", "sources": ["RAILING WEST 2"], "dryRun": false}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "target": {"type": "string", "description": "Canonical block definition name (must exist)"},
                    "sources": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Definitions to merge into target"
                    },
                    "dryRun": {"type": "boolean", "description": "When true (default), only report counts without mutating"},
                    "verbose": {"type": "boolean", "description": "When true, include per-source instance ID lists"}
                },
                "required": ["target", "sources"]
            }
        ),
        Tool(
            name="rhino_block_rebase",
            description="""Rebase block definition geometry in local space while compensating
all instances so the model does not move in world space. Defaults to dry-run.

Use this to normalize Revit-exported blocks with baked absolute offsets
(for example per-floor Z embedded in the definition geometry).
Blocks used as nested refs inside other definitions are rejected for now.

Example dry run: {"name": "PARTITION WALL 01", "anchor": "bbox_min", "axes": ["z"], "dryRun": true}
Example execute: {"name": "PARTITION WALL 01", "anchor": "bbox_min", "axes": ["z"], "dryRun": false}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Block definition name to rebase"},
                    "anchor": {
                        "type": "string",
                        "enum": ["bbox_min", "bbox_center", "bbox_max"],
                        "description": "Definition-space reference point used to compute the rebase translation (default bbox_min)"
                    },
                    "targetPoint": {
                        "type": "array",
                        "items": {"type": "number"},
                        "minItems": 3,
                        "maxItems": 3,
                        "description": "Target point [x, y, z] for the chosen anchor (default [0,0,0])"
                    },
                    "axes": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["x", "y", "z"]},
                        "description": "Axes to rebase (default [\"x\", \"y\", \"z\"])"
                    },
                    "dryRun": {"type": "boolean", "description": "When true (default), only report the translation without mutating"},
                    "verbose": {"type": "boolean", "description": "When true, include old→new instance ID mappings on execute"}
                },
                "required": ["name"]
            }
        ),
        Tool(
            name="rhino_block_rebase_recursive",
            description="""Rebase a leaf block definition and compensate direct parent definitions
that reference it as a nested block. Also compensates any direct document
instances of the leaf. Defaults to dry-run.

Use this for nested Revit-exported blocks where the leaf definition has
baked absolute offsets and exists only (or also) as ON_InstanceRef objects
inside parent definitions. The leaf must have at least one parent definition.

Dry-run returns the full mutation plan with planHash. Execute requires
expectedPlanHash from the dry-run to guard against stale state.

Example dry run: {"name": "InstanceDefinition 413", "anchor": "bbox_min", "axes": ["z"], "dryRun": true}
Example execute: {"name": "InstanceDefinition 413", "anchor": "bbox_min", "axes": ["z"], "dryRun": false, "expectedPlanHash": "a7f3b2c1..."}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Leaf block definition name to rebase (must have at least one parent definition)"},
                    "anchor": {
                        "type": "string",
                        "enum": ["bbox_min", "bbox_center", "bbox_max"],
                        "description": "Definition-space reference point for the rebase translation (default bbox_min)"
                    },
                    "targetPoint": {
                        "type": "array",
                        "items": {"type": "number"},
                        "minItems": 3,
                        "maxItems": 3,
                        "description": "Target point [x, y, z] for the chosen anchor (default [0,0,0])"
                    },
                    "axes": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["x", "y", "z"]},
                        "description": "Axes to rebase (default [\"x\", \"y\", \"z\"])"
                    },
                    "dryRun": {"type": "boolean", "description": "When true (default), return the mutation plan without executing"},
                    "expectedPlanHash": {"type": "string", "description": "Required on execute (dryRun=false). Must match the planHash from dry-run."},
                    "verbose": {"type": "boolean", "description": "When true, include leafRefObjectIndices per parent in output"}
                },
                "required": ["name"]
            }
        ),
        # Annotations
        Tool(
            name="rhino_text",
            description="Create a text annotation.",
            inputSchema={
                "type": "object",
                "properties": {
                    "type": {"type": "string", "const": "TEXT"},
                    "text": {"type": "string", "description": "Text content"},
                    "point": {"type": "array", "description": "Location [x, y, z]"},
                    "height": {"type": "number", "description": "Text height"},
                    "font": {"type": "string", "description": "Font name (optional)"},
                    "bold": {"type": "boolean", "description": "Bold text (optional)"},
                    "italic": {"type": "boolean", "description": "Italic text (optional)"},
                    "name": {"type": "string", "description": "Object name"},
                    "layer": {"type": "string", "description": "Layer path"}
                },
                "required": ["text", "point", "height"]
            }
        ),
        Tool(
            name="rhino_dimension",
            description="""Create dimension annotations.

Types:
- LINEAR: {"type": "DIMENSION_LINEAR", "start": [0,0,0], "end": [10,0,0], "offset": 2}
- RADIUS: {"type": "DIMENSION_RADIUS", "curveId": "guid", "anglePoint": [5,0,0]}
- ANGLE: {"type": "DIMENSION_ANGLE", "center": [0,0,0], "start": [10,0,0], "end": [0,10,0], "dimLocation": [7,7,0]}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "type": {"type": "string", "description": "Dimension type: DIMENSION_LINEAR, DIMENSION_ALIGNED, DIMENSION_RADIUS, DIMENSION_DIAMETER, DIMENSION_ANGLE"},
                    "start": {"type": "array", "description": "Start point for linear dimensions"},
                    "end": {"type": "array", "description": "End point for linear dimensions"},
                    "offset": {"type": "number", "description": "Dimension line offset distance"},
                    "curveId": {"type": "string", "description": "Curve GUID for radius/diameter dimensions"},
                    "anglePoint": {"type": "array", "description": "Point on curve for radius/diameter"},
                    "center": {"type": "array", "description": "Center point for angle dimensions"},
                    "dimLocation": {"type": "array", "description": "Dimension arc location for angle dimensions"},
                    "name": {"type": "string", "description": "Object name"},
                    "layer": {"type": "string", "description": "Layer path"}
                },
                "required": ["type"]
            }
        ),
        # Phase 4: Consolidated action-based tools
        Tool(
            name="rhino_document_ops",
            description="""Perform document operations using an action parameter.

Available actions:
- open: Open an existing .3dm file (requires 'path' parameter). Returns document name, units, object count.
- new: Create a new blank document
- save: Save the document to a file (requires 'path' parameter, optional 'small': true for SaveSmall without render meshes)
- undo: Undo the last operation
- redo: Redo the last undone operation
- set_units: Set document units (requires 'units' parameter: 'Millimeters', 'Centimeters', 'Meters', 'Inches', 'Feet', etc.)

Examples:
- Open: {"action": "open", "path": "C:/path/to/file.3dm"}
- New: {"action": "new"}
- Save: {"action": "save", "path": "/path/to/file.3dm"}
- SaveSmall: {"action": "save", "path": "/path/to/file.3dm", "small": true}
- Undo: {"action": "undo"}
- Redo: {"action": "redo"}
- Set units: {"action": "set_units", "units": "Meters"}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["open", "new", "save", "undo", "redo", "set_units"],
                        "description": "The document operation to perform"
                    },
                    "path": {
                        "type": "string",
                        "description": "File path for open or save actions"
                    },
                    "units": {
                        "type": "string",
                        "description": "Unit system for set_units action (Millimeters, Centimeters, Meters, Inches, Feet, etc.)"
                    },
                    "small": {
                        "type": "boolean",
                        "description": "When true with save action, saves without render meshes (SaveSmall)"
                    }
                },
                "required": ["action"]
            }
        ),
        Tool(
            name="rhino_curve_ops",
            description="""Perform curve operations using an action parameter.

Available actions:
- join: Join curves together (requires 'ids' parameter with array of curve GUIDs)
- explode: Explode a polycurve into segments (requires 'id' parameter)
- divide: Divide curve into points (requires 'id' and 'count' parameters)
- extend: Extend a curve (requires 'id', 'end' (0 or 1), and 'length' parameters)
- trim: Trim a curve (requires 'id' and 'parameter' or 'point' parameters)
- split: Split curve at parameter (requires 'id' and 'parameter' parameters)
- rebuild: Rebuild curve (requires 'id', optional 'degree' and 'pointCount' parameters)
- fillet: Fillet two curves (requires 'id1', 'id2', and 'radius' parameters)

Examples:
- Join: {"action": "join", "ids": ["guid1", "guid2"]}
- Explode: {"action": "explode", "id": "guid"}
- Divide: {"action": "divide", "id": "guid", "count": 10}
- Extend: {"action": "extend", "id": "guid", "end": 0, "length": 5.0}
- Trim: {"action": "trim", "id": "guid", "parameter": 0.5}
- Split: {"action": "split", "id": "guid", "parameter": 0.5}
- Rebuild: {"action": "rebuild", "id": "guid", "degree": 3, "pointCount": 20}
- Fillet: {"action": "fillet", "id1": "guid1", "id2": "guid2", "radius": 2.0}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["join", "explode", "divide", "extend", "trim", "split", "rebuild", "fillet"],
                        "description": "The curve operation to perform"
                    },
                    "id": {
                        "type": "string",
                        "description": "Curve GUID (for single-curve operations)"
                    },
                    "ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Array of curve GUIDs (for join operation)"
                    },
                    "id1": {
                        "type": "string",
                        "description": "First curve GUID (for fillet operation)"
                    },
                    "id2": {
                        "type": "string",
                        "description": "Second curve GUID (for fillet operation)"
                    },
                    "count": {
                        "type": "integer",
                        "description": "Number of division points (for divide operation)"
                    },
                    "end": {
                        "type": "integer",
                        "description": "Which end to extend: 0 = start, 1 = end (for extend operation)"
                    },
                    "length": {
                        "type": "number",
                        "description": "Extension length (for extend operation)"
                    },
                    "parameter": {
                        "type": "number",
                        "description": "Curve parameter (for trim/split operations)"
                    },
                    "point": {
                        "type": "array",
                        "description": "Point [x, y, z] for trim operation"
                    },
                    "degree": {
                        "type": "integer",
                        "description": "Curve degree (for rebuild operation)"
                    },
                    "pointCount": {
                        "type": "integer",
                        "description": "Number of control points (for rebuild operation)"
                    },
                    "radius": {
                        "type": "number",
                        "description": "Fillet radius (for fillet operation)"
                    }
                },
                "required": ["action"]
            }
        ),
        Tool(
            name="rhino_material_ops",
            description="""Perform material operations using an action parameter.

Available actions:
- list: List all materials in the document
- create: Create a new material (requires 'name' and 'color' parameters)
- delete: Delete a material (requires 'name' parameter)
- assign: Assign material to objects (requires 'name' and 'id' or 'ids' parameters)

Examples:
- List: {"action": "list"}
- Create: {"action": "create", "name": "MyMaterial", "color": [255, 0, 0]}
- Delete: {"action": "delete", "name": "MyMaterial"}
- Assign to one object: {"action": "assign", "name": "MyMaterial", "id": "guid"}
- Assign to multiple: {"action": "assign", "name": "MyMaterial", "ids": ["guid1", "guid2"]}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["list", "create", "delete", "assign"],
                        "description": "The material operation to perform"
                    },
                    "name": {
                        "type": "string",
                        "description": "Material name (for create, delete, assign actions)"
                    },
                    "color": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "RGB color array [r, g, b] (for create action)"
                    },
                    "id": {
                        "type": "string",
                        "description": "Object GUID to assign material to (for assign action)"
                    },
                    "ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Array of object GUIDs to assign material to (for assign action)"
                    },
                    "shininess": {
                        "type": "number",
                        "description": "Material shininess 0-1 (for create action)"
                    },
                    "transparency": {
                        "type": "number",
                        "description": "Material transparency 0-1 (for create action)"
                    },
                    "reflectivity": {
                        "type": "number",
                        "description": "Material reflectivity 0-1 (for create action)"
                    }
                },
                "required": ["action"]
            }
        ),
        # ========================================
        # Phase A: Core Operations (14 tools)
        # ========================================

        # Intersection tools (5)
        Tool(
            name="rhino_intersect_curves",
            description="""Find intersections between two curves.

Returns intersection points and any overlap curves.

Example:
{"curveId1": "guid1", "curveId2": "guid2"}

Optional: tolerance (default: document tolerance)""",
            inputSchema={
                "type": "object",
                "properties": {
                    "curveId1": {"type": "string", "description": "First curve GUID"},
                    "curveId2": {"type": "string", "description": "Second curve GUID"},
                    "tolerance": {"type": "number", "description": "Intersection tolerance (optional)"}
                },
                "required": ["curveId1", "curveId2"]
            }
        ),
        Tool(
            name="rhino_intersect_curve_surface",
            description="""Find intersections between a curve and a surface/brep.

Returns intersection points and overlap curves.

Example:
{"curveId": "guid1", "surfaceId": "guid2"}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "curveId": {"type": "string", "description": "Curve GUID"},
                    "surfaceId": {"type": "string", "description": "Surface or Brep GUID"},
                    "tolerance": {"type": "number", "description": "Intersection tolerance (optional)"}
                },
                "required": ["curveId", "surfaceId"]
            }
        ),
        Tool(
            name="rhino_intersect_curve_brep",
            description="""Find intersections between a curve and a brep.

Returns intersection points, overlap curves, and inside/outside point indices.

Example:
{"curveId": "guid1", "brepId": "guid2"}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "curveId": {"type": "string", "description": "Curve GUID"},
                    "brepId": {"type": "string", "description": "Brep GUID"},
                    "tolerance": {"type": "number", "description": "Intersection tolerance (optional)"}
                },
                "required": ["curveId", "brepId"]
            }
        ),
        Tool(
            name="rhino_intersect_breps",
            description="""Find intersections between two breps.

Returns intersection curves as new geometry.

Example:
{"brepId1": "guid1", "brepId2": "guid2"}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "brepId1": {"type": "string", "description": "First Brep GUID"},
                    "brepId2": {"type": "string", "description": "Second Brep GUID"},
                    "tolerance": {"type": "number", "description": "Intersection tolerance (optional)"}
                },
                "required": ["brepId1", "brepId2"]
            }
        ),
        Tool(
            name="rhino_intersect_plane",
            description="""Intersect a brep with a plane.

Returns intersection curves as new geometry.

Example:
{"brepId": "guid", "planeOrigin": [0, 0, 5], "planeNormal": [0, 0, 1]}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "brepId": {"type": "string", "description": "Brep GUID"},
                    "planeOrigin": {"type": "array", "description": "Plane origin point [x, y, z]"},
                    "planeNormal": {"type": "array", "description": "Plane normal vector [x, y, z]"},
                    "tolerance": {"type": "number", "description": "Intersection tolerance (optional)"}
                },
                "required": ["brepId", "planeOrigin", "planeNormal"]
            }
        ),

        # Project/Pull tools (4)
        Tool(
            name="rhino_project_curve",
            description="""Project curves onto a brep/surface along a direction.

Example:
{"curveIds": ["guid1", "guid2"], "brepIds": ["guid3"], "direction": [0, 0, -1]}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "curveIds": {"type": "array", "items": {"type": "string"}, "description": "Curve GUIDs to project"},
                    "brepIds": {"type": "array", "items": {"type": "string"}, "description": "Brep/Surface GUIDs to project onto"},
                    "direction": {"type": "array", "description": "Projection direction [x, y, z]"},
                    "tolerance": {"type": "number", "description": "Projection tolerance (optional)"}
                },
                "required": ["curveIds", "brepIds", "direction"]
            }
        ),
        Tool(
            name="rhino_pull_curve",
            description="""Pull a curve to the closest point on a brep face.

Example:
{"curveId": "guid1", "brepId": "guid2", "faceIndex": 0}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "curveId": {"type": "string", "description": "Curve GUID to pull"},
                    "brepId": {"type": "string", "description": "Brep GUID to pull onto"},
                    "faceIndex": {"type": "integer", "description": "Face index on brep (default 0)"},
                    "tolerance": {"type": "number", "description": "Pull tolerance (optional)"}
                },
                "required": ["curveId", "brepId"]
            }
        ),
        Tool(
            name="rhino_offset_curve",
            description="""Offset a curve in a plane.

Example:
{"curveId": "guid", "distance": 5.0, "plane": "World"}

plane options: "World", "CPlane", or custom {"origin": [0,0,0], "normal": [0,0,1]}
cornerStyle options: "None", "Sharp", "Round", "Smooth", "Chamfer" (default: Sharp)""",
            inputSchema={
                "type": "object",
                "properties": {
                    "curveId": {"type": "string", "description": "Curve GUID to offset"},
                    "distance": {"type": "number", "description": "Offset distance (positive or negative)"},
                    "plane": {"description": "Offset plane: 'World', 'CPlane', or {origin, normal}"},
                    "cornerStyle": {"type": "string", "enum": ["None", "Sharp", "Round", "Smooth", "Chamfer"], "description": "How to handle corners"},
                    "tolerance": {"type": "number", "description": "Offset tolerance (optional)"}
                },
                "required": ["curveId", "distance"]
            }
        ),
        Tool(
            name="rhino_offset_curve_on_surface",
            description="""Offset a curve on a surface.

Example:
{"curveId": "guid1", "surfaceId": "guid2", "distance": 5.0}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "curveId": {"type": "string", "description": "Curve GUID to offset"},
                    "surfaceId": {"type": "string", "description": "Surface GUID to offset on"},
                    "distance": {"type": "number", "description": "Offset distance"},
                    "tolerance": {"type": "number", "description": "Offset tolerance (optional)"}
                },
                "required": ["curveId", "surfaceId", "distance"]
            }
        ),

        # Offset Brep tool (1)
        Tool(
            name="rhino_offset_brep",
            description="""Create an offset/shell of a brep (thicken).

Returns offset breps, blend surfaces, and wall surfaces.

Example:
{"brepId": "guid", "distance": 2.0, "solid": true}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "brepId": {"type": "string", "description": "Brep GUID to offset"},
                    "distance": {"type": "number", "description": "Offset distance"},
                    "solid": {"type": "boolean", "description": "Create solid (default true)"},
                    "extend": {"type": "boolean", "description": "Extend edges (default true)"},
                    "shrink": {"type": "boolean", "description": "Shrink faces (default false)"},
                    "tolerance": {"type": "number", "description": "Offset tolerance (optional)"}
                },
                "required": ["brepId", "distance"]
            }
        ),

        # Split/Trim tools (3)
        Tool(
            name="rhino_split_brep",
            description="""Split a brep with cutting objects (plane, curves, or other breps).

Example with plane:
{"brepId": "guid", "planeOrigin": [0, 0, 5], "planeNormal": [0, 0, 1]}

Example with cutters:
{"brepId": "guid", "cutterIds": ["guid1", "guid2"]}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "brepId": {"type": "string", "description": "Brep GUID to split"},
                    "planeOrigin": {"type": "array", "description": "Cutting plane origin [x, y, z]"},
                    "planeNormal": {"type": "array", "description": "Cutting plane normal [x, y, z]"},
                    "cutterIds": {"type": "array", "items": {"type": "string"}, "description": "Cutter object GUIDs (curves or breps)"},
                    "tolerance": {"type": "number", "description": "Split tolerance (optional)"}
                },
                "required": ["brepId"]
            }
        ),
        Tool(
            name="rhino_trim_brep",
            description="""Trim a brep with a cutting plane, keeping one side.

Example:
{"brepId": "guid", "planeOrigin": [0, 0, 5], "planeNormal": [0, 0, 1], "keepSide": "positive"}

keepSide: "positive" (above plane) or "negative" (below plane)""",
            inputSchema={
                "type": "object",
                "properties": {
                    "brepId": {"type": "string", "description": "Brep GUID to trim"},
                    "planeOrigin": {"type": "array", "description": "Cutting plane origin [x, y, z]"},
                    "planeNormal": {"type": "array", "description": "Cutting plane normal [x, y, z]"},
                    "keepSide": {"type": "string", "enum": ["positive", "negative"], "description": "Which side to keep"},
                    "tolerance": {"type": "number", "description": "Trim tolerance (optional)"}
                },
                "required": ["brepId", "planeOrigin", "planeNormal", "keepSide"]
            }
        ),
        Tool(
            name="rhino_split_face",
            description="""Split a brep face with curves.

Example:
{"brepId": "guid", "faceIndex": 0, "curveIds": ["guid1", "guid2"]}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "brepId": {"type": "string", "description": "Brep GUID containing the face"},
                    "faceIndex": {"type": "integer", "description": "Face index to split"},
                    "curveIds": {"type": "array", "items": {"type": "string"}, "description": "Curve GUIDs to split with"},
                    "tolerance": {"type": "number", "description": "Split tolerance (optional)"}
                },
                "required": ["brepId", "faceIndex", "curveIds"]
            }
        ),

        # Knowledge Graph tools
        Tool(
            name="knowledge_query",
            description="""Query the Rook knowledge graph for patterns BEFORE performing Rhino operations.

IMPORTANT: Call this BEFORE every Rhino action to get relevant patterns and avoid known mistakes.

TIERS (you decide which depth you need):
- "quick" (~20 tokens): Essential facts, use when you know the tool
- "context" (~50 tokens): Specific rules for a usage context (default)
- "errors" (~30 tokens): What fails and why, use when debugging
- "raw" (~500+ tokens): Full patterns, use for deep investigation

Returns:
- tier: The tier that was returned
- source: "consolidated" or "raw" (whether tiered knowledge was available)
- data: The knowledge for your requested depth
- available_tiers: What tiers exist for this tool
- token_estimates: Approximate tokens for each tier
- available_contexts: For context tier, what contexts exist
- hint: Suggestion for what to try next if this doesn't help

Examples:
- Quick refresher: {"tool": "rhino_layer_create", "depth": "quick"}
- Specific context: {"tool": "rhino_layer_create", "intent": "create nested layer", "depth": "context"}
- Debug failure: {"tool": "rhino_layer_create", "depth": "errors"}
- Full details: {"tool": "rhino_layer_create", "depth": "raw"}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "intent": {
                        "type": "string",
                        "description": "Natural language description of what you want to accomplish"
                    },
                    "tool": {
                        "type": "string",
                        "description": "Specific MCP tool name to get patterns for"
                    },
                    "depth": {
                        "type": "string",
                        "enum": ["quick", "context", "errors", "raw"],
                        "description": "Knowledge tier to return. You decide based on your needs. Default: 'context'"
                    },
                    "context_name": {
                        "type": "string",
                        "description": "For 'context' depth, specific context to return (e.g., 'nested', 'colored')"
                    }
                },
                "required": []
            }
        ),
        Tool(
            name="knowledge_record",
            description="""Record a learning outcome to the knowledge graph AFTER performing Rhino operations.

Call this after:
- A successful operation (to reinforce patterns)
- A correction (to record what failed and what worked)

The knowledge graph persists across sessions and helps avoid repeating mistakes.

Example recording a correction:
{
    "intent": "create nested layer",
    "action": {"tool": "rhino_layer_create", "params": {"name": "child", "parent": "parent"}},
    "outcome": "success",
    "correction_of": {"params": {"name": "parent::child"}, "error": "Created literal name, not hierarchy"}
}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "intent": {
                        "type": "string",
                        "description": "What the user wanted to accomplish"
                    },
                    "action": {
                        "type": "object",
                        "description": "The action taken: {tool: string, params: object}"
                    },
                    "outcome": {
                        "type": "string",
                        "enum": ["success", "failure"],
                        "description": "Whether the action succeeded"
                    },
                    "correction_of": {
                        "type": "object",
                        "description": "If correcting a failure: {params: object, error: string}"
                    }
                },
                "required": ["intent", "action", "outcome"]
            }
        ),
        Tool(
            name="parse_command",
            description="""Parse a Rhino command string into structured parameters.

Uses the command knowledge store to match the command against known syntax patterns
and extract parameter names and values.

This is useful for:
- Understanding what a command does
- Converting raw command strings to structured data for session export
- Validating command syntax

Examples:
- parse_command(command_string="_-Box 0,0,0 10,10,0 5")
  -> {command: "-Box", mode: "default", parameters: {corner1: "0,0,0", corner2: "10,10,0", height: "5"}}

- parse_command(command_string="_-Sphere _Diameter 0,0,0 10,0,0")
  -> {command: "-Sphere", mode: "diameter", parameters: {point1: "0,0,0", point2: "10,0,0"}}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "command_string": {
                        "type": "string",
                        "description": "The full command string to parse (e.g., '_-Box 0,0,0 10,10,0 5')"
                    },
                    "mode": {
                        "type": "string",
                        "description": "Optional mode hint if known (e.g., 'center', 'diameter')"
                    }
                },
                "required": ["command_string"]
            }
        ),

        # Command Learning tools
        # rhino_command_learn — REMOVED from catalog (deprecated and hard-disabled)
        Tool(
            name="rhino_command_observations",
            description="""Query stored command observations.

Use this to see what commands have been learned and their patterns.

Returns statistics about observed commands, or detailed observations for a specific command.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Specific command to query (e.g., '_Box'). If omitted, returns stats for all commands."
                    }
                },
                "required": []
            }
        ),
        Tool(
            name="rhino_command_experiment",
            description="""Experiment with multiple command variations to learn syntax.

Tries multiple variations of a command and records observations for each.
Useful for discovering which parameter formats work.

Example:
{
    "command": "_Box",
    "variations": [
        "_-Box 0,0,0 10,10,0 _Enter",
        "_-Box _Center 5,5,0 10,10,0 _Enter",
        "_-Box _Diagonal 0,0,0 10,10,10"
    ],
    "intent": "learn box command modes"
}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Base command name (e.g., '_Box')"
                    },
                    "variations": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of full command strings to try"
                    },
                    "intent": {
                        "type": "string",
                        "description": "What you're trying to learn"
                    }
                },
                "required": ["command", "variations"]
            }
        ),
        Tool(
            name="rhino_command_queue",
            description="""Get the prioritized queue of Rhino commands to learn.

Returns a list of commands organized by priority, showing:
- Command name
- Suggested variations to try
- Whether the command requires selection
- How many observations we already have
- Whether knowledge has been consolidated

Use this to systematically learn Rhino command syntax patterns.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "priority": {
                        "type": "string",
                        "description": "Filter by priority level (e.g., 'priority_1_primitives')"
                    }
                },
                "required": []
            }
        ),
        Tool(
            name="rhino_command_consolidate",
            description="""Consolidate observations into reusable command knowledge using DSPy.

Takes all observations for a command and uses DSPy to:
1. Extract dialogue patterns from raw command history
2. Identify command modes (corner, center, diagonal, etc.)
3. Generate syntax templates with placeholders
4. Document gotchas and preconditions

The consolidated knowledge is stored and used by MABWiser for intent-based selection.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Command to consolidate (e.g., '-Box'). If omitted, consolidates all."
                    }
                },
                "required": []
            }
        ),
        Tool(
            name="rhino_command_select",
            description="""Select the best Rhino command for a user intent using MABWiser.

Given a natural language intent, uses the trained MAB selector to choose:
- The best command for the task
- The best mode within that command
- The syntax to execute

Falls back to DSPy intent mapping if MAB has insufficient data.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "intent": {
                        "type": "string",
                        "description": "What you want to accomplish (e.g., 'create a box centered at origin')"
                    }
                },
                "required": ["intent"]
            }
        ),
        Tool(
            name="rhino_command_knowledge",
            description="""Query consolidated command knowledge.

Returns the learned patterns for a specific command or all commands, including:
- Description
- Available modes with syntax templates
- Options and their meanings
- Preconditions (selection requirements, etc.)
- Common gotchas to avoid""",
            inputSchema={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Specific command to query (e.g., 'Box'). Omit for all commands."
                    }
                },
                "required": []
            }
        ),
        Tool(
            name="rhino_command_knowledge_reload",
            description="""Reload command knowledge from disk.

Call this after external edits to the knowledge JSON file (knowledge/commands/command_knowledge.json).
The MCP server caches knowledge in memory, so edits to the JSON file won't take effect until reload.

Returns the number of command patterns loaded.""",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),

        # Interactive Command Learning tools
        Tool(
            name="rhino_command_interactive_start",
            description="""Start a Rhino command interactively and get the first prompt.

This is for LEARNING command syntax step-by-step:
1. Starts the command (e.g., '_-Box')
2. Returns what Rhino is prompting for
3. You then use rhino_command_interactive_send to respond to each prompt

Example:
  Start: {"command": "_-Box"}
  Returns: {"prompt": "First corner of base ( Diagonal  3Point  Vertical  Center )", ...}
  Send: {"input": "0,0,0"}
  Returns: {"prompt": "Other corner of base or length ( 3Point )", ...}
  Continue until is_complete=true""",
            inputSchema={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The command to start (e.g., '_-Box', '_-Sphere')"
                    }
                },
                "required": ["command"]
            }
        ),
        Tool(
            name="rhino_command_interactive_send",
            description="""Send input to an active Rhino command and get the next prompt.

Use after rhino_command_interactive_start to respond to prompts.
Returns the next prompt, or is_complete=true when command finishes.

Input can be:
- Coordinates: "0,0,0" or "10,5,0"
- Numbers: "5" or "45"
- Options: "_Center" or "_Diagonal"
- Enter for default: "" (empty string)
- Cancel: "_Cancel" """,
            inputSchema={
                "type": "object",
                "properties": {
                    "input": {
                        "type": "string",
                        "description": "The input to send (coordinates, numbers, options, or empty for Enter)"
                    }
                },
                "required": ["input"]
            }
        ),
        Tool(
            name="rhino_command_interactive_prompt",
            description="""Get the current command prompt without sending input.

Use to check what Rhino is currently asking for.""",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="rhino_command_interactive_cancel",
            description="""Cancel any active command.

Use if you need to abort a command in progress.""",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="rhino_learn_interactive",
            description="""Learn a Rhino command using interactive mode with FULL DIALOGUE CAPTURE.

This is the PREFERRED learning method. Unlike rhino_command_learn (fire-and-forget),
this tool captures the actual prompts Rhino shows at each step.

Example:
{
    "command": "_-Box",
    "inputs": ["0,0,0", "10,10,0", "5"],
    "intent": "create a box at origin"
}

Returns dialogue like:
  Step 1: "First corner of base (Diagonal 3Point...)" -> 0,0,0
  Step 2: "Other corner of base or length..." -> 10,10,0
  Step 3: "Height. Press Enter to use width" -> 5

This captures OPTIONS, DEFAULT VALUES, and actual PROMPTS for learning.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The command to learn (e.g., '_-Box', '_-Sphere')"
                    },
                    "inputs": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of inputs to send (e.g., ['0,0,0', '10,10,0', '5'])"
                    },
                    "intent": {
                        "type": "string",
                        "description": "What you're trying to accomplish"
                    },
                    "use_preselection": {
                        "type": "boolean",
                        "description": "If true, use pre-selected geometry instead of auto-creating. Set this when you've already created and selected the prerequisite geometry."
                    }
                },
                "required": ["command", "inputs"]
            }
        ),
        Tool(
            name="rhino_learn_variations_interactive",
            description="""Learn multiple variations of a command using interactive mode.

Executes multiple input sequences for the same command, capturing dialogue for each.
Use this to systematically learn all modes of a command.

Example:
{
    "command": "_-Box",
    "input_sequences": [
        ["0,0,0", "10,10,0", "5"],
        ["_Center", "5,5,0", "10,10,0", ""],
        ["_Diagonal", "0,0,0", "10,10,10"]
    ],
    "intent": "learn all Box command modes"
}

Returns results for each variation with full dialogue capture.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The command to learn (e.g., '_-Box')"
                    },
                    "input_sequences": {
                        "type": "array",
                        "items": {
                            "type": "array",
                            "items": {"type": "string"}
                        },
                        "description": "List of input sequences to try"
                    },
                    "intent": {
                        "type": "string",
                        "description": "What you're trying to learn"
                    }
                },
                "required": ["command", "input_sequences"]
            }
        ),
        Tool(
            name="rhino_analyze_prompt",
            description="""Analyze a Rhino command prompt to determine what geometry is needed.

Use this when a command fails because it needs pre-existing geometry.
Pass the prompt text (e.g., "Select curves to revolve") and get back:
- What geometry type is needed (curve, surface, solid, etc.)
- The command and inputs to create that geometry

Example:
{"prompt": "Select curves to revolve"}

Returns:
{
    "needs_geometry": true,
    "geometry_type": "curve",
    "creation_command": "_-Circle",
    "creation_inputs": ["0,0,0", "5"]
}

This uses the knowledge graph to find the best way to create the needed geometry.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "The Rhino command prompt to analyze"
                    }
                },
                "required": ["prompt"]
            }
        ),
        Tool(
            name="rhino_prepare_geometry",
            description="""Create geometry needed for a command that requires selection.

Given a geometry type (curve, surface, solid, point, edge, mesh, any),
creates appropriate test geometry using learned command patterns.

Example:
{"geometry_type": "curve"}

This will create a simple curve (e.g., circle or line) that can then be
selected for commands like Revolve, Pipe, ExtrudeCrv, etc.

After calling this, use _SelLast to select the created geometry.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "geometry_type": {
                        "type": "string",
                        "description": "Type of geometry to create: curve, surface, solid, point, edge, mesh, any",
                        "enum": ["curve", "surface", "solid", "point", "edge", "mesh", "any"]
                    }
                },
                "required": ["geometry_type"]
            }
        ),

        # SubD tools
        Tool(
            name="rhino_subd_box",
            description="""Create a SubD box.

Example: {"origin": [0, 0, 0], "width": 10, "depth": 10, "height": 10, "xFaces": 2, "yFaces": 2, "zFaces": 2}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "origin": {"type": "array", "description": "Origin point [x, y, z] (default [0,0,0])"},
                    "width": {"type": "number", "description": "Width in X direction"},
                    "depth": {"type": "number", "description": "Depth in Y direction"},
                    "height": {"type": "number", "description": "Height in Z direction"},
                    "xFaces": {"type": "integer", "description": "Face divisions in X (default 2)"},
                    "yFaces": {"type": "integer", "description": "Face divisions in Y (default 2)"},
                    "zFaces": {"type": "integer", "description": "Face divisions in Z (default 2)"}
                },
                "required": ["width", "depth", "height"]
            }
        ),
        Tool(
            name="rhino_subd_sphere",
            description="""Create a SubD sphere.

Example: {"center": [0, 0, 0], "radius": 5, "divisions": 3}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "center": {"type": "array", "description": "Center point [x, y, z] (default [0,0,0])"},
                    "radius": {"type": "number", "description": "Sphere radius"},
                    "divisions": {"type": "integer", "description": "Subdivision level (default 3)"}
                },
                "required": ["radius"]
            }
        ),
        Tool(
            name="rhino_subd_cylinder",
            description="""Create a SubD cylinder.

Example: {"center": [0, 0, 0], "radius": 5, "height": 10, "circumferenceFaces": 8, "heightFaces": 1}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "center": {"type": "array", "description": "Base center point [x, y, z] (default [0,0,0])"},
                    "radius": {"type": "number", "description": "Cylinder radius"},
                    "height": {"type": "number", "description": "Cylinder height"},
                    "circumferenceFaces": {"type": "integer", "description": "Faces around circumference (default 8)"},
                    "heightFaces": {"type": "integer", "description": "Face divisions in height (default 1)"}
                },
                "required": ["radius", "height"]
            }
        ),
        Tool(
            name="rhino_subd_from_mesh",
            description="""Create a SubD from an existing mesh.

Example: {"meshId": "guid", "interpolateVertices": false}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "meshId": {"type": "string", "description": "GUID of mesh to convert"},
                    "interpolateVertices": {"type": "boolean", "description": "Interpolate mesh vertices (default false)"}
                },
                "required": ["meshId"]
            }
        ),
        Tool(
            name="rhino_subd_from_surface",
            description="""Create a SubD from a surface or brep.

Example: {"brepId": "guid", "method": "Pack"}

Methods: "Pack" (control net) or "Interpolate" """,
            inputSchema={
                "type": "object",
                "properties": {
                    "brepId": {"type": "string", "description": "GUID of surface/brep to convert"},
                    "method": {"type": "string", "description": "Conversion method: Pack or Interpolate (default Pack)"}
                },
                "required": ["brepId"]
            }
        ),
        Tool(
            name="rhino_subd_subdivide",
            description="""Subdivide a SubD to increase smoothness.

Example: {"subdId": "guid", "level": 1}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "subdId": {"type": "string", "description": "GUID of SubD to subdivide"},
                    "level": {"type": "integer", "description": "Number of subdivision levels (default 1)"}
                },
                "required": ["subdId"]
            }
        ),
        Tool(
            name="rhino_subd_crease",
            description="""Set edge creases on a SubD for sharper edges.

Example: {"subdId": "guid", "edgeIndices": [0, 1, 2], "crease": true}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "subdId": {"type": "string", "description": "GUID of SubD"},
                    "edgeIndices": {"type": "array", "items": {"type": "integer"}, "description": "Edge indices to modify"},
                    "crease": {"type": "boolean", "description": "True to add crease, false to remove (default true)"}
                },
                "required": ["subdId", "edgeIndices"]
            }
        ),
        Tool(
            name="rhino_subd_to_brep",
            description="""Convert a SubD to a NURBS Brep.

Example: {"subdId": "guid", "packFaces": false}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "subdId": {"type": "string", "description": "GUID of SubD to convert"},
                    "packFaces": {"type": "boolean", "description": "Pack faces for efficiency (default false)"}
                },
                "required": ["subdId"]
            }
        ),
        Tool(
            name="rhino_subd_to_mesh",
            description="""Convert a SubD to a mesh.

Example: {"subdId": "guid", "density": 1}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "subdId": {"type": "string", "description": "GUID of SubD to convert"},
                    "density": {"type": "integer", "description": "Mesh density 0-5 (default 1)"}
                },
                "required": ["subdId"]
            }
        ),

        # Mesh tools - Creation
        Tool(
            name="rhino_mesh_from_brep",
            description="""Create a mesh from a Brep/Surface.

Example: {"brepId": "guid", "density": 0.5}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "brepId": {"type": "string", "description": "Brep GUID to mesh"},
                    "density": {"type": "number", "description": "Mesh density (default 0.5)"},
                    "minEdgeLength": {"type": "number", "description": "Minimum edge length"},
                    "maxEdgeLength": {"type": "number", "description": "Maximum edge length"},
                    "jagged": {"type": "boolean", "description": "Allow jagged seams"},
                    "simple": {"type": "boolean", "description": "Use simple/minimal meshing"}
                },
                "required": ["brepId"]
            }
        ),
        Tool(
            name="rhino_mesh_box",
            description="""Create a mesh box.

Example: {"origin": [0, 0, 0], "width": 10, "depth": 10, "height": 10, "xCount": 2, "yCount": 2, "zCount": 2}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "origin": {"type": "array", "description": "Origin point [x, y, z] (default [0,0,0])"},
                    "width": {"type": "number", "description": "Width in X direction"},
                    "depth": {"type": "number", "description": "Depth in Y direction"},
                    "height": {"type": "number", "description": "Height in Z direction"},
                    "xCount": {"type": "integer", "description": "Subdivisions in X (default 1)"},
                    "yCount": {"type": "integer", "description": "Subdivisions in Y (default 1)"},
                    "zCount": {"type": "integer", "description": "Subdivisions in Z (default 1)"}
                },
                "required": ["width", "depth", "height"]
            }
        ),
        Tool(
            name="rhino_mesh_sphere",
            description="""Create a mesh sphere.

Example: {"center": [0, 0, 0], "radius": 5, "rings": 10, "segments": 10}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "center": {"type": "array", "description": "Center point [x, y, z] (default [0,0,0])"},
                    "radius": {"type": "number", "description": "Sphere radius"},
                    "rings": {"type": "integer", "description": "Number of rings (default 10)"},
                    "segments": {"type": "integer", "description": "Number of segments (default 10)"}
                },
                "required": ["radius"]
            }
        ),
        Tool(
            name="rhino_mesh_cylinder",
            description="""Create a mesh cylinder.

Example: {"center": [0, 0, 0], "radius": 5, "height": 10, "vertical": 10, "around": 20}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "center": {"type": "array", "description": "Base center point [x, y, z] (default [0,0,0])"},
                    "radius": {"type": "number", "description": "Cylinder radius"},
                    "height": {"type": "number", "description": "Cylinder height"},
                    "vertical": {"type": "integer", "description": "Vertical divisions (default 10)"},
                    "around": {"type": "integer", "description": "Divisions around circumference (default 20)"}
                },
                "required": ["radius", "height"]
            }
        ),
        Tool(
            name="rhino_mesh_cone",
            description="""Create a mesh cone.

Example: {"center": [0, 0, 0], "radius": 5, "height": 10, "vertical": 10, "around": 20}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "center": {"type": "array", "description": "Base center point [x, y, z] (default [0,0,0])"},
                    "radius": {"type": "number", "description": "Cone base radius"},
                    "height": {"type": "number", "description": "Cone height"},
                    "vertical": {"type": "integer", "description": "Vertical divisions (default 10)"},
                    "around": {"type": "integer", "description": "Divisions around circumference (default 20)"}
                },
                "required": ["radius", "height"]
            }
        ),

        # Mesh tools - Editing
        Tool(
            name="rhino_mesh_boolean",
            description="""Boolean operations on meshes (union, difference, intersection).

Example: {"operation": "union", "meshIds": ["guid1", "guid2"], "deleteInputs": true}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "operation": {"type": "string", "description": "Boolean operation: union, difference, intersection"},
                    "meshIds": {"type": "array", "items": {"type": "string"}, "description": "Mesh GUIDs (at least 2)"},
                    "deleteInputs": {"type": "boolean", "description": "Delete input meshes (default true)"}
                },
                "required": ["operation", "meshIds"]
            }
        ),
        Tool(
            name="rhino_mesh_reduce",
            description="""Reduce the number of faces in a mesh.

Example: {"meshId": "guid", "targetCount": 1000, "accuracy": 5}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "meshId": {"type": "string", "description": "Mesh GUID to reduce"},
                    "targetCount": {"type": "integer", "description": "Target face count"},
                    "accuracy": {"type": "integer", "description": "Accuracy 1-10 (default 5)"}
                },
                "required": ["meshId", "targetCount"]
            }
        ),
        Tool(
            name="rhino_quad_remesh",
            description="""QuadRemesh a mesh for better topology.

Example: {"meshId": "guid", "targetQuadCount": 1000, "adaptive": true}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "meshId": {"type": "string", "description": "Mesh GUID to remesh"},
                    "targetQuadCount": {"type": "integer", "description": "Target quad count (default 1000)"},
                    "adaptive": {"type": "boolean", "description": "Use adaptive sizing (default true)"}
                },
                "required": ["meshId"]
            }
        ),
        Tool(
            name="rhino_mesh_repair",
            description="""Repair a mesh (fills holes, fixes normals, etc.).

Example: {"meshId": "guid", "fillHoles": true, "rebuildNormals": true}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "meshId": {"type": "string", "description": "Mesh GUID to repair"},
                    "fillHoles": {"type": "boolean", "description": "Fill holes (default true)"},
                    "rebuildNormals": {"type": "boolean", "description": "Rebuild normals (default true)"}
                },
                "required": ["meshId"]
            }
        ),
        Tool(
            name="rhino_mesh_smooth",
            description="""Smooth a mesh.

Example: {"meshId": "guid", "factor": 0.5, "iterations": 1}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "meshId": {"type": "string", "description": "Mesh GUID to smooth"},
                    "factor": {"type": "number", "description": "Smoothing factor 0-1 (default 0.5)"},
                    "iterations": {"type": "integer", "description": "Number of iterations (default 1)"}
                },
                "required": ["meshId"]
            }
        ),
        Tool(
            name="rhino_mesh_weld",
            description="""Weld mesh vertices together at angle threshold.

Example: {"meshId": "guid", "angle": 22.5}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "meshId": {"type": "string", "description": "Mesh GUID to weld"},
                    "angle": {"type": "number", "description": "Weld angle in degrees (default 22.5)"}
                },
                "required": ["meshId"]
            }
        ),
        Tool(
            name="rhino_mesh_unweld",
            description="""Unweld mesh vertices at angle threshold.

Example: {"meshId": "guid", "angle": 22.5}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "meshId": {"type": "string", "description": "Mesh GUID to unweld"},
                    "angle": {"type": "number", "description": "Unweld angle in degrees (default 22.5)"}
                },
                "required": ["meshId"]
            }
        ),

        # Analysis tools - Curvature
        Tool(
            name="rhino_curvature_curve",
            description="""Get curvature at a parameter on a curve.

Returns curvature vector, magnitude, radius of curvature, tangent, and point.

Example: {"curveId": "guid", "parameter": 0.5}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "curveId": {"type": "string", "description": "Curve GUID"},
                    "parameter": {"type": "number", "description": "Normalized parameter 0-1 along curve"}
                },
                "required": ["curveId", "parameter"]
            }
        ),
        Tool(
            name="rhino_curvature_surface",
            description="""Get curvature at a UV point on a surface.

Returns Gaussian curvature, mean curvature, principal curvatures (kappa1, kappa2), and directions.

Example: {"surfaceId": "guid", "u": 0.5, "v": 0.5}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "surfaceId": {"type": "string", "description": "Surface or single-face Brep GUID"},
                    "u": {"type": "number", "description": "Normalized U parameter 0-1"},
                    "v": {"type": "number", "description": "Normalized V parameter 0-1"}
                },
                "required": ["surfaceId", "u", "v"]
            }
        ),
        Tool(
            name="rhino_draft_angle",
            description="""Analyze draft angles on a brep relative to a pull direction.

Returns draft angle for each face (useful for mold design).

Example: {"brepId": "guid", "direction": [0, 0, 1]}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "brepId": {"type": "string", "description": "Brep GUID"},
                    "direction": {"type": "array", "description": "Pull direction [x, y, z] (default [0,0,1])"}
                },
                "required": ["brepId"]
            }
        ),

        # Analysis tools - Point/Curve Evaluation
        Tool(
            name="rhino_closest_point",
            description="""Find the closest point on geometry to a test point.

Works with curves, surfaces, breps, and meshes.

Example: {"id": "guid", "point": [5, 5, 5]}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Object GUID"},
                    "point": {"type": "array", "description": "Test point [x, y, z]"}
                },
                "required": ["id", "point"]
            }
        ),
        Tool(
            name="rhino_curve_point_at",
            description="""Get point at a parameter on a curve.

Example: {"curveId": "guid", "parameter": 0.5}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "curveId": {"type": "string", "description": "Curve GUID"},
                    "parameter": {"type": "number", "description": "Normalized parameter 0-1 along curve"}
                },
                "required": ["curveId", "parameter"]
            }
        ),
        Tool(
            name="rhino_curve_tangent",
            description="""Get tangent vector at a parameter on a curve.

Example: {"curveId": "guid", "parameter": 0.5}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "curveId": {"type": "string", "description": "Curve GUID"},
                    "parameter": {"type": "number", "description": "Normalized parameter 0-1 along curve"}
                },
                "required": ["curveId", "parameter"]
            }
        ),
        Tool(
            name="rhino_curve_frame",
            description="""Get frame (plane) at a parameter on a curve.

Returns origin, X/Y/Z axes of the curve frame.

Example: {"curveId": "guid", "parameter": 0.5}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "curveId": {"type": "string", "description": "Curve GUID"},
                    "parameter": {"type": "number", "description": "Normalized parameter 0-1 along curve"}
                },
                "required": ["curveId", "parameter"]
            }
        ),
        Tool(
            name="rhino_surface_normal",
            description="""Get normal vector at a UV point on a surface.

Example: {"surfaceId": "guid", "u": 0.5, "v": 0.5}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "surfaceId": {"type": "string", "description": "Surface or single-face Brep GUID"},
                    "u": {"type": "number", "description": "Normalized U parameter 0-1"},
                    "v": {"type": "number", "description": "Normalized V parameter 0-1"}
                },
                "required": ["surfaceId", "u", "v"]
            }
        ),

        # Analysis tools - Topology Queries
        Tool(
            name="rhino_brep_edges",
            description="""Get edge information for a brep.

Returns edge count and details for each edge (start/end points, length, degree, valence).

Example: {"brepId": "guid"}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "brepId": {"type": "string", "description": "Brep GUID"}
                },
                "required": ["brepId"]
            }
        ),
        Tool(
            name="rhino_brep_faces",
            description="""Get face information for a brep.

Returns face count and details for each face (area, centroid, normal, loop count).

Example: {"brepId": "guid"}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "brepId": {"type": "string", "description": "Brep GUID"}
                },
                "required": ["brepId"]
            }
        ),
        Tool(
            name="rhino_brep_vertices",
            description="""Get vertex information for a brep.

Returns vertex count and details for each vertex (location, edge count).

Example: {"brepId": "guid"}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "brepId": {"type": "string", "description": "Brep GUID"}
                },
                "required": ["brepId"]
            }
        ),
        Tool(
            name="rhino_is_closed",
            description="""Check if geometry is closed/solid.

Works with curves, breps, meshes, and SubD.

Example: {"id": "guid"}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Object GUID"}
                },
                "required": ["id"]
            }
        ),
        Tool(
            name="rhino_is_valid",
            description="""Check if geometry is valid.

Returns validity status and validation log if invalid.

Example: {"id": "guid"}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Object GUID"}
                },
                "required": ["id"]
            }
        ),

        # Hybrid Investigator tools (learning and execution)
        Tool(
            name="rhino_learn_next",
            description="""Learn the next command from the learning roadmap.

Uses the Hybrid Investigator to:
1. Get the next unlearned command from the prioritized roadmap
2. Use DSPy to plan input sequences to try
3. Execute each sequence and capture dialogue
4. Consolidate learned knowledge into the knowledge store

Optional filters:
- phase: Limit to a specific phase (1-8)
- category: Limit to a specific category (e.g., "Primitives", "Curves")

Returns: Command learned, modes discovered, gotchas found, progress stats""",
            inputSchema={
                "type": "object",
                "properties": {
                    "phase": {
                        "type": "integer",
                        "description": "Optional phase filter (1-8)"
                    },
                    "category": {
                        "type": "string",
                        "description": "Optional category filter (e.g., 'Primitives', 'Curves')"
                    }
                },
                "required": []
            }
        ),
        Tool(
            name="rhino_execute_intent",
            description="""Execute a user intent using learned command knowledge.

Uses the Hybrid Investigator to:
1. Search for matching commands in the knowledge store
2. Use DSPy to resolve intent to best command+mode
3. Use MAB to select among candidates based on history
4. Build the exact syntax and execute

Example intents:
- "create a sphere at origin with radius 5"
- "draw a box from 0,0,0 to 10,10,10"
- "make a cylinder at 0,0,0 with radius 3 and height 10"

Returns: Command executed, mode used, objects created, reasoning trace""",
            inputSchema={
                "type": "object",
                "properties": {
                    "intent": {
                        "type": "string",
                        "description": "Natural language intent describing what to create/do"
                    }
                },
                "required": ["intent"]
            }
        ),
        Tool(
            name="rhino_learning_progress",
            description="""Get learning progress from the roadmap and knowledge store.

Returns:
- Total commands in roadmap
- Commands learned so far
- Percentage complete
- Current phase
- Knowledge store statistics (commands, modes, gotchas)

Use this to check progress and decide what to learn next.""",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        # Session recording tools
        Tool(
            name="session_current",
            description="""Get current recording session info.

Returns:
- Session ID
- Document name and path
- Start time
- Command count
- Statistics (MCP commands, user commands, objects created)
- Git branch/commit if in a repo

Use this to check what's being recorded in the current session.""",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="session_history",
            description="""Get command history from the current session.

Returns a list of commands with:
- Command name and source (mcp/user)
- Parameters
- Success/failure
- Objects created
- Timestamps

Use this to review what was done in the session.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Max commands to return (default 100)"},
                    "offset": {"type": "integer", "description": "Skip first N commands"},
                    "source": {
                        "type": "string",
                        "enum": ["mcp", "user", "all"],
                        "description": "Filter by command source"
                    }
                },
                "required": []
            }
        ),
        Tool(
            name="session_list",
            description="""List available sessions from disk.

Returns past sessions with:
- Session ID
- Document name
- Project folder
- Start/end times
- Command count

Use this to find previous sessions for replay or analysis.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "project": {"type": "string", "description": "Filter by project folder name"},
                    "limit": {"type": "integer", "description": "Max sessions to return (default 50)"}
                },
                "required": []
            }
        ),
        Tool(
            name="session_export",
            description="""Export session history.

Formats:
- json: Full session data (default)
- markdown: Human-readable summary""",
            inputSchema={
                "type": "object",
                "properties": {
                    "format": {
                        "type": "string",
                        "enum": ["json", "markdown"],
                        "description": "Export format (default: json)"
                    }
                },
                "required": []
            }
        ),
        # AI Gumball tools
        Tool(
            name="rhino_gumball_activate",
            description="""Enable AI Gumball mode (persistent, like the built-in gumball).

When activated, the AI Gumball works just like Rhino's built-in gumball:
- Select any object → gumball appears automatically
- Drag handles to transform (translate, rotate, scale on any axis)
- Select a different object → gumball moves to new object
- Esc pauses drag mode (gumball stays visible); selecting new objects resumes it

Every drag is tracked with full metadata:
- Which handle was used (TranslateX, RotateZ, ScaleXY, etc.)
- Full transform matrix (delta + cumulative)
- Sub-object identity, copy operations, timing

This call returns immediately. Use rhino_gumball_status to check state
and rhino_gumball_history to retrieve recorded drags.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Object GUIDs to select before activating. If omitted, uses current selection."
                    }
                },
                "required": []
            }
        ),
        Tool(
            name="rhino_gumball_deactivate",
            description="""Disable AI Gumball mode. Removes the persistent gumball and stops tracking drags.""",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="rhino_gumball_status",
            description="""Check AI Gumball state.

Returns:
- enabled: whether AI Gumball mode is on
- dragActive: whether user is currently in a drag session
- dragCount: number of drags in current session
- lastMode: last handle mode used (TranslateX, RotateZ, etc.)
- cumulativeTransform: accumulated transform matrix""",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="rhino_gumball_history",
            description="""Get AI Gumball drag history from the current session.

Returns all AIGumball command records with full drag-level detail:
- Each drag's handle mode (TranslateX, RotateZ, etc.)
- Delta and cumulative transform matrices
- Copy operations, sub-object selections, timing

Use this to analyze user manual manipulations and learn from them.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Max AIGumball commands to return (default 20)"}
                },
                "required": []
            }
        ),
        Tool(
            name="rhino_gumball_align",
            description="""Set gumball alignment mode — controls which coordinate system the gumball axes follow.

Modes:
- "object" (default): Axes from bounding box (world-aligned)
- "world": World X/Y/Z axes at object centroid
- "cplane": Active construction plane axes at object centroid

Changes take effect immediately if a gumball is visible.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "mode": {"type": "string", "description": "Alignment mode: 'world', 'cplane', or 'object'", "enum": ["world", "cplane", "object"]}
                },
                "required": ["mode"]
            }
        ),
        Tool(
            name="rhino_gumball_extrude",
            description="""Programmatic extrude via gumball — extrude a face, curve, or single-face brep along a direction.

For face extrusion: creates extrusion tool from face boundary, boolean unions with original solid.
For curve extrusion: creates solid from curve profile.
If boolean union fails, extrusion is added as separate geometry.

All operations are undoable and recorded to session history.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "ids": {"type": "array", "items": {"type": "string"}, "description": "Object GUIDs to extrude"},
                    "direction": {"type": "array", "items": {"type": "number"}, "description": "Extrude direction [x, y, z] (default [0,0,1])"},
                    "distance": {"type": "number", "description": "Extrude distance (default 1.0)"},
                    "cap": {"type": "boolean", "description": "Cap closed extrusions (default true)"},
                    "faceIndex": {"type": "integer", "description": "Brep face index to extrude (-1 for auto, default -1)"}
                },
                "required": ["ids"]
            }
        ),
        Tool(
            name="rhino_gumball_cut",
            description="""Programmatic cut/boss via gumball — boolean subtract (cut) or add (boss) by extruding a face.

Positive distance = boss (outward, boolean union).
Negative distance = cut (inward, boolean difference).

The face boundary is extruded along the direction, then boolean operation is performed with the original solid.
All operations are undoable and recorded to session history.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "ids": {"type": "array", "items": {"type": "string"}, "description": "Object GUIDs to cut/boss"},
                    "direction": {"type": "array", "items": {"type": "number"}, "description": "Cut direction [x, y, z] (default [0,0,1])"},
                    "distance": {"type": "number", "description": "Cut distance (negative=cut, positive=boss, default -1.0)"},
                    "faceIndex": {"type": "integer", "description": "Brep face index for cut profile (default 0)"}
                },
                "required": ["ids"]
            }
        ),
        Tool(
            name="rhino_gumball_settings",
            description="""Get or set AI Gumball behavior settings.

Omitted fields are left unchanged. Returns current settings after any updates.

Settings:
- dragStrength: Drag sensitivity multiplier (0.01-10.0, default 1.0). Use 0.1 for fine control, 5.0 for coarse.
- autoReset: Reset gumball session tracking after each drag (default false).
- snapEnabled: Snap translations to grid increments (default false).
- snapTranslate: Translation snap increment in model units (default 1.0).
- alignment: Gumball alignment mode ('world', 'cplane', 'object').""",
            inputSchema={
                "type": "object",
                "properties": {
                    "dragStrength": {"type": "number", "description": "Drag sensitivity multiplier (0.01-10.0)"},
                    "autoReset": {"type": "boolean", "description": "Reset gumball session after each drag"},
                    "snapEnabled": {"type": "boolean", "description": "Enable translation grid snapping"},
                    "snapTranslate": {"type": "number", "description": "Translation snap increment"},
                    "alignment": {"type": "string", "description": "Alignment mode", "enum": ["world", "cplane", "object"]}
                },
                "required": []
            }
        ),
        # Grasshopper tools
        Tool(
            name="gh_status",
            description="Check if Grasshopper is available and get canvas info (version, active document, object count).",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="gh_snapshot",
            description="""Get the complete Grasshopper canvas state as a structured document in a SINGLE call.

Returns ALL components, connections, groups, errors, and data previews.
Components use short IDs (C1, C2, ...) instead of full GUIDs.
Connections are flow strings: "C1.O0>C2.I1" (Output 0 of C1 → Input 1 of C2).

Response includes:
- components: All components with params, values, errors, warnings
- flows: All connections as compact flow strings
- groups: All groups with member short IDs
- diagnostics: Error/warning summary with component IDs
- epoch: Version number for short ID mappings (required for gh_edit)

Use gh_snapshot to understand the canvas, then gh_edit to modify it atomically.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "include_data": {
                        "type": "boolean",
                        "description": "Include output data previews (default true)"
                    },
                    "max_preview_items": {
                        "type": "integer",
                        "description": "Max items per output data preview (default 3)"
                    }
                },
                "required": []
            }
        ),
        Tool(
            name="gh_edit",
            description="""Apply batch mutations to the Grasshopper canvas atomically in a SINGLE call.

Execution order: create → disconnect → delete → set_values → connect → groups.
Returns the updated canvas snapshot with new short ID mappings.

REQUIRES 'epoch' from the most recent gh_snapshot to prevent stale edits.

Flow string format: "C1.O0>C2.I1" or "T1.O0>C3.I0"
- C prefix = existing component (from snapshot)
- T prefix = component created in this batch (via temp_id)
- O = output param index, I = input param index

Create entry types:
- By GUID: {"temp_id": "T1", "guid": "abc...", "pos": [300, 200]}
- By name: {"temp_id": "T1", "name": "Sphere", "pos": [300, 200]}
- Slider: {"temp_id": "T1", "type": "slider", "nick": "R", "min": 0, "max": 10, "value": 5, "pos": [100, 200]}
- Panel: {"temp_id": "T1", "type": "panel", "content": "Output", "pos": [600, 200]}
- Toggle: {"temp_id": "T1", "type": "toggle", "value": true, "pos": [100, 300]}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "epoch": {
                        "type": "integer",
                        "description": "epoch from most recent gh_snapshot (required)"
                    },
                    "create": {
                        "type": "array",
                        "description": "Components to create. Each needs temp_id (T1, T2, ...) plus guid/name/type.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "temp_id": {"type": "string", "description": "Temporary ID (T1, T2, ...) for referencing in connect/groups"},
                                "guid": {"type": "string", "description": "Component type GUID"},
                                "name": {"type": "string", "description": "Component name (alternative to guid)"},
                                "type": {"type": "string", "description": "Special type: 'slider', 'panel', 'toggle'"},
                                "nick": {"type": "string", "description": "Nickname"},
                                "pos": {"type": "array", "items": {"type": "number"}, "description": "[x, y] canvas position"},
                                "value": {"description": "Initial value (slider/panel/toggle)"},
                                "min": {"type": "number", "description": "Min value (slider)"},
                                "max": {"type": "number", "description": "Max value (slider)"},
                                "content": {"type": "string", "description": "Text content (panel)"}
                            },
                            "required": ["temp_id"]
                        }
                    },
                    "delete": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Short IDs of components to delete (e.g. ['C3', 'C5'])"
                    },
                    "set_values": {
                        "type": "array",
                        "description": "Value updates for sliders/panels/toggles",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string", "description": "Component short ID"},
                                "value": {"description": "New value"},
                                "min": {"type": "number"},
                                "max": {"type": "number"}
                            },
                            "required": ["id"]
                        }
                    },
                    "connect": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Flow strings to connect: 'C1.O0>C2.I1' or 'T1.O0>C3.I0'"
                    },
                    "disconnect": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Flow strings to disconnect: 'C1.O0>C2.I1'"
                    },
                    "groups": {
                        "type": "array",
                        "description": "Group operations: create/delete/add_members/remove_members",
                        "items": {
                            "type": "object",
                            "properties": {
                                "action": {"type": "string", "enum": ["create", "delete", "add_members", "remove_members"]},
                                "id": {"type": "string", "description": "Group ID (for delete/modify)"},
                                "nick": {"type": "string"},
                                "colour": {"type": "string"},
                                "members": {"type": "array", "items": {"type": "string"}}
                            },
                            "required": ["action"]
                        }
                    }
                },
                "required": ["epoch"]
            }
        ),
        Tool(
            name="gh_undo",
            description="""Undo the last operation on the Grasshopper canvas.

Reverses the most recent undo event. Each gh_edit batch and individual GH operation
(create, delete, connect, etc.) records undo events. Call multiple times to walk back
through operation history. Returns success/failure status.""",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="gh_selection",
            description="Get currently selected objects on the Grasshopper canvas. Returns list of selected components with type, name, nickname, GUID, category, position, and size.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="gh_library",
            description="""Search the Grasshopper component library.

Returns matching components with name, nickname, description, category, and GUID.
Can filter by search term and/or category.

Use exact=true for precise name matching (e.g., "Point" returns only "Point", not "Construct Point").""",
            inputSchema={
                "type": "object",
                "properties": {
                    "search": {"type": "string", "description": "Search term to filter components by name/description"},
                    "category": {"type": "string", "description": "Filter by category or subcategory (e.g., 'Surface', 'Primitive', 'Kangaroo2')"},
                    "limit": {"type": "integer", "description": "Maximum results to return (default 50)"},
                    "exact": {"type": "boolean", "description": "If true, only return components whose name exactly matches the search term (case-insensitive)"}
                },
                "required": []
            }
        ),
        Tool(
            name="gh_categories",
            description="""List all available Grasshopper component categories.

Returns categories with component counts and subcategories.
Use this to discover installed plugins and available component types.""",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="gh_set_script",
            description="""Set or read the source code on a Python 3 Script component.

To SET a script: pass guid + script (the full Python source code).
To GET the current script: pass only guid (omit script).

The component must be a Python 3 Script (Py3) component.
After setting, automatically triggers ExpireSolution so outputs recompute.

Prefer this over rhino_execute workarounds for script components.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "guid": {"type": "string", "description": "Component instance GUID or short ID (C1, C2...) from gh_snapshot"},
                    "script": {"type": "string", "description": "Python source code to set (omit to read current script)"}
                },
                "required": ["guid"]
            }
        ),
        Tool(
            name="gh_create_python_script",
            description="""Create a Python 3 Script component on the GH canvas with custom pins and code.

Single-shot tool: creates the component, configures input/output pins, writes the script,
and triggers recompilation — all in one call.

Pin format: "Name:Type" where Type is a GH/Rhino type hint (used in the script).
Common types: string, int, float, double, bool, Point3d, Vector3d, Curve, Surface, Brep, Mesh, Line, Plane, Circle, Box.

The script receives inputs as variables matching pin names, and must assign outputs
to variables matching output pin names. The 'out' print stream is always available.

Example:
{
  "code": "import Rhino.Geometry as rg\\na = rg.Point3d(x, y, 0)",
  "pins_in": ["x:float", "y:float"],
  "pins_out": ["a:Point3d"],
  "name": "Grid Point"
}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Python 3 source code for the script component"},
                    "pins_in": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": 'Input pin definitions as "Name:Type" strings, e.g. ["x:float", "y:float"]',
                    },
                    "pins_out": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": 'Output pin definitions as "Name:Type" strings, e.g. ["a:Point3d"]',
                    },
                    "name": {"type": "string", "description": "Display name for the component (default: 'Python 3 Script')"},
                    "x": {"type": "number", "description": "Canvas X position (default: 200)"},
                    "y": {"type": "number", "description": "Canvas Y position (default: 200)"},
                },
                "required": ["code", "pins_in", "pins_out"],
            }
        ),
        Tool(
            name="gh_create_csharp_script",
            description="""Create a RhinoCode C# Script component on the GH canvas with custom pins and code.

Single-shot tool: creates the component, configures input/output pins, writes the script,
and triggers recompilation — all in one call.

Pin format: "Name:Type" where Type is for documentation only.
Common types: string, int, float, double, bool, Point3d, Vector3d, Curve, Surface, Brep, Mesh, Line, Plane, Circle, Box.

IMPORTANT: RhinoCode enforces that ALL RunScript input parameters are typed as `object`.
Your code must cast inputs explicitly, e.g. `var r = Convert.ToDouble(R);` or
`var crv = (Curve)C;`. Outputs are `ref object` — assign directly by name.

You can provide EITHER:
- "Body code" — just the code inside RunScript. The tool wraps it in the required
  Script_Instance class with using directives and boilerplate automatically.
- "Full class code" — a complete Script_Instance : GH_ScriptInstance class. Detected
  when code contains 'class Script_Instance' or 'void RunScript'.

Print() is available for debug output.

Example (body code):
{
  "code": "var r = Convert.ToDouble(R);\\nvar n = Convert.ToInt32(N);\\nvar pts = new List<Point3d>();\\nfor (int i = 0; i < n; i++) {\\n  double angle = 2 * Math.PI * i / n;\\n  pts.Add(new Point3d(r * Math.Cos(angle), r * Math.Sin(angle), 0));\\n}\\nPoints = pts;",
  "pins_in": ["R:double", "N:int"],
  "pins_out": ["Points:Point3d"],
  "name": "Circle Points"
}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "C# source code — either RunScript body or full Script_Instance class"},
                    "pins_in": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": 'Input pin definitions as "Name:Type" strings, e.g. ["x:double", "y:double"]',
                    },
                    "pins_out": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": 'Output pin definitions as "Name:Type" strings, e.g. ["a:Point3d"]',
                    },
                    "name": {"type": "string", "description": "Display name for the component (default: 'C# Script')"},
                    "x": {"type": "number", "description": "Canvas X position (default: 200)"},
                    "y": {"type": "number", "description": "Canvas Y position (default: 200)"},
                },
                "required": ["code", "pins_in", "pins_out"],
            }
        ),
        Tool(
            name="chirp_create",
            description="""Create an intelligent LLM-powered C# Script component on the GH canvas.

Takes pin definitions, a DSPy signature, and a REQUIRED category. Generates a
complete C# script that calls the Chirp adapter service, and places a configured
component on the canvas.

CATEGORY is required. Must be one of:
  planner     — Brief → structured parameters (ChainOfThought)
  interpreter — Upstream Reasoning → domain-specific parameters (ChainOfThought)
  critic      — Multiple Reasonings → conflict detection (ChainOfThought)
  narrator    — Multiple Reasonings → design narrative (ChainOfThought)
  classifier  — Data → categorical decision (Predict)
  gate        — Reasoning → boolean/enum rule activations (Predict)
  editor      — Reasoning + Correction → reconciled Reasoning (ChainOfThought)

Auto-added pins (do NOT include these in pins_in/pins_out):
  Input:  "Correction" (string, optional) — human override per-node
  Output: "Reasoning" (string) — LLM chain-of-thought

Pin type format: "Name:Type" where Type is one of:
  Primitives: string, int, float, double, bool
  Geometry:   Point3d, Vector3d, Plane, Line, Curve, Surface, Brep, Mesh, Box, Circle, Arc, Polyline

Requires: Chirp adapter running (`python -m chirp` from the Chirp repo).""",
            inputSchema={
                "type": "object",
                "properties": {
                    "pins_in": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Input pin definitions (do NOT include Correction — auto-added), e.g. [\"Brief:string\"]"
                    },
                    "pins_out": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Output pin definitions (do NOT include Reasoning — auto-added), e.g. [\"Span:float\", \"Material:string\"]"
                    },
                    "signature": {
                        "type": "string",
                        "description": "DSPy signature string, e.g. \"brief -> span, material\""
                    },
                    "category": {
                        "type": "string",
                        "enum": ["planner", "interpreter", "critic", "narrator", "classifier", "gate", "editor"],
                        "description": "Component category — determines DSPy module, prompt strategy, and visual treatment"
                    },
                    "name": {
                        "type": "string",
                        "description": "Display name / NickName for the component (default: 'Chirp <Category>')"
                    },
                    "deterministic_code": {
                        "type": "string",
                        "description": "Optional C# code to run after LLM outputs are assigned (post-processing)"
                    },
                    "x": {"type": "number", "description": "Canvas X position (default 200)"},
                    "y": {"type": "number", "description": "Canvas Y position (default 200)"},
                },
                "required": ["pins_in", "pins_out", "signature", "category"]
            }
        ),
        Tool(
            name="gh_errors",
            description="""Get all components with runtime errors or warnings on the canvas.

Returns a diagnostic report with:
- Total component count
- Components with errors (red) - with error messages and input states
- Components with warnings (orange) - with warning messages and input states

Each component includes:
- GUID, name, nickname for identification
- Input connection states (which inputs are connected/disconnected)
- Actual error/warning messages

Use this to:
1. Diagnose why a definition isn't working
2. Find disconnected required inputs
3. Identify type mismatches or invalid data
4. Debug complex definitions systematically""",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="gh_set_reference",
            description="""Set a Rhino geometry object as persistent data on a GH parameter component.

Use this to reference existing Rhino geometry (curves, points, surfaces, breps, meshes) into Grasshopper.
The parameter will then output that referenced geometry for use in the GH definition.

Supported parameter types: Param_Curve, Param_Point, Param_Surface, Param_Brep, Param_Geometry, Param_Mesh.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "paramGuid": {"type": "string", "description": "GH parameter instance GUID or short ID (C1, C2...) from gh_snapshot"},
                    "rhinoObjectId": {"type": "string", "description": "GUID of the Rhino object to reference"}
                },
                "required": ["paramGuid", "rhinoObjectId"]
            }
        ),
        Tool(
            name="gh_get_reference",
            description="Get persistent geometry references from a GH parameter component.",
            inputSchema={
                "type": "object",
                "properties": {
                    "guid": {"type": "string", "description": "GH parameter instance GUID or short ID (C1, C2...) from gh_snapshot"}
                },
                "required": ["guid"]
            }
        ),
        Tool(
            name="gh_clear_reference",
            description="Clear all persistent references from a GH parameter component.",
            inputSchema={
                "type": "object",
                "properties": {
                    "guid": {"type": "string", "description": "GH parameter instance GUID or short ID (C1, C2...) from gh_snapshot"}
                },
                "required": ["guid"]
            }
        ),
        Tool(
            name="gh_preview",
            description="""Set preview visibility for Grasshopper components.

Controls whether components display their geometry in the Rhino viewport.
Use this to hide construction geometry and show only final results.

Examples:
- Hide specific components: {"guids": ["abc...", "def..."], "hidden": true}
- Show specific components: {"guids": ["abc..."], "hidden": false}
- Hide ALL components: {"hidden": true}
- Show ALL components: {"hidden": false}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "guids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Component instance GUIDs or short IDs (C1, C2...) from gh_snapshot. If empty/omitted, applies to ALL components."
                    },
                    "hidden": {
                        "type": "boolean",
                        "description": "True to hide preview, False to show preview"
                    }
                },
                "required": ["hidden"]
            }
        ),
        Tool(
            name="gh_clear",
            description="Clear all objects from the Grasshopper canvas.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="gh_document_open",
            description="""Open a GH or GHX file in Grasshopper.

Use this to load an existing Grasshopper definition for inspection or modification.
The current canvas will be replaced with the contents of the file.

Example: Open a file
{"path": "C:/path/to/definition.ghx"}

Returns:
- opened: bool
- path: Full path to the file
- fileName: Just the filename
- objectCount: Number of objects loaded""",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Full path to the GH or GHX file"
                    }
                },
                "required": ["path"]
            }
        ),
        Tool(
            name="gh_document_new",
            description="""Create a new empty Grasshopper document.

Clears the current canvas and creates a fresh document. Use this between
processing files to ensure a clean slate.""",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="gh_learn_directory",
            description="""Batch learn recipes from all GH/GHX files in a directory.

Opens each file, extracts the full recipe (components, wiring, inputs),
saves it to the unified knowledge store, then moves to the next file.

This is the automated workflow for building the recipe knowledge base
from example files like GrasshopperHowtos.

Example: Learn all files in a directory
{"directory": "C:/GrasshopperHowtos", "recursive": true}

Returns:
- processed: Number of files processed
- succeeded: Number of recipes extracted
- failed: Number of failures
- recipes: List of recipe IDs created""",
            inputSchema={
                "type": "object",
                "properties": {
                    "directory": {
                        "type": "string",
                        "description": "Path to directory containing GH/GHX files"
                    },
                    "recursive": {
                        "type": "boolean",
                        "default": True,
                        "description": "Search subdirectories (default: true)"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max files to process (for testing)"
                    }
                },
                "required": ["directory"]
            }
        ),
        Tool(
            name="gh_move",
            description="""Move Grasshopper objects to new positions on the canvas.

Use this to organize/layout components. Positions are canvas coordinates (x increases right, y increases down).

Example: Organize components left-to-right:
{"positions": [
    {"guid": "abc...", "x": 50, "y": 100},
    {"guid": "def...", "x": 250, "y": 100},
    {"guid": "ghi...", "x": 450, "y": 100}
]}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "positions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "guid": {"type": "string", "description": "Instance GUID or short ID (C1, C2...) from gh_snapshot"},
                                "x": {"type": "number", "description": "New X position"},
                                "y": {"type": "number", "description": "New Y position"}
                            },
                            "required": ["guid", "x", "y"]
                        },
                        "description": "List of objects with new positions"
                    }
                },
                "required": ["positions"]
            }
        ),
        Tool(
            name="gh_canvas_cleanup",
            description="""Automatically organize Grasshopper canvas with collision-free layout.

Uses a 10-phase pipeline adapted from Engram's graph formatter:
- Sugiyama layering (left-to-right dependency order)
- Collision detection (iterative bounding-box resolution)
- Branch centering (fans of 3+ children centered on parent)
- Wire angle optimization (expands spacing when wires >45deg)
- Group-aware padding (keeps GH_Groups intact)

Example: A messy canvas reorganized into clean flow with no overlaps:
Inputs → Math → Geometry → Outputs""",
            inputSchema={
                "type": "object",
                "properties": {
                    "start_x": {
                        "type": "number",
                        "description": "Left edge X coordinate (default: 50)",
                        "default": 50
                    },
                    "start_y": {
                        "type": "number",
                        "description": "Top edge Y coordinate (default: 50)",
                        "default": 50
                    },
                    "horizontal_gap": {
                        "type": "number",
                        "description": "Gap between layers/columns in pixels (default: 30)",
                        "default": 30
                    },
                    "vertical_gap": {
                        "type": "number",
                        "description": "Gap between nodes in same layer (default: 20)",
                        "default": 20
                    },
                    "max_layer_width": {
                        "type": "integer",
                        "description": "Max components per layer/column (default: 4).",
                        "default": 4
                    },
                    "style": {
                        "type": "string",
                        "enum": ["expanded", "compact"],
                        "description": "Layout style: 'expanded' (default) spreads nodes, 'compact' minimizes space",
                        "default": "expanded"
                    },
                    "collision_detection": {
                        "type": "boolean",
                        "description": "Enable iterative collision detection (default: true)",
                        "default": True
                    },
                    "expand_by_height": {
                        "type": "boolean",
                        "description": "Push children right when wire angle >45deg (default: true)",
                        "default": True
                    },
                    "center_branches": {
                        "type": "boolean",
                        "description": "Center fans of 3+ children around parent (default: true)",
                        "default": True
                    },
                    "anchor_guid": {
                        "type": "string",
                        "description": "GUID of component to keep in place (others move relative to it)"
                    },
                    "snap_to_grid": {
                        "type": "boolean",
                        "description": "Snap positions to grid (default: false)",
                        "default": False
                    },
                    "grid_size": {
                        "type": "number",
                        "description": "Grid cell size when snap_to_grid is true (default: 8)",
                        "default": 8
                    },
                    "dry_run": {
                        "type": "boolean",
                        "description": "If true, calculate positions but don't move components",
                        "default": False
                    }
                }
            }
        ),
        Tool(
            name="gh_canvas_focus",
            description="""Focus the Grasshopper canvas viewport on specific components or all objects.

Navigates the canvas camera to frame the specified components (or everything if no IDs given).
Use before gh_canvas_image to control what's visible in the capture.

Examples:
- Focus on everything: {}
- Focus on specific components: {"ids": ["C1", "C5", "C12"]}
- Focus with extra padding: {"ids": ["C1"], "padding": 50}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Component short IDs or GUIDs to focus on. Omit to focus on all objects."
                    },
                    "padding": {
                        "type": "number",
                        "description": "Extra padding around focused area in canvas units (default: 20)",
                        "default": 20
                    }
                }
            }
        ),
        Tool(
            name="gh_canvas_zoom",
            description="""Set the Grasshopper canvas zoom level and/or center point.

Controls the canvas viewport directly. Zoom=1.0 is 100%, 0.5 is zoomed out, 2.0 is zoomed in.
Returns the final zoom and midpoint after changes.

Examples:
- Zoom out to see more: {"zoom": 0.3}
- Zoom in: {"zoom": 2.0}
- Pan to specific location: {"centerX": 500, "centerY": 300}
- Zoom and pan: {"zoom": 0.5, "centerX": 200, "centerY": 100}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "zoom": {
                        "type": "number",
                        "description": "Zoom level (1.0 = 100%, 0.5 = zoomed out, 2.0 = zoomed in)"
                    },
                    "centerX": {
                        "type": "number",
                        "description": "X coordinate to center the viewport on"
                    },
                    "centerY": {
                        "type": "number",
                        "description": "Y coordinate to center the viewport on"
                    }
                },
                "minProperties": 1
            }
        ),
        Tool(
            name="gh_canvas_image",
            description="""Capture the current Grasshopper canvas as a PNG image.

Renders the canvas at current zoom/position to a PNG file in the temp directory.
Returns the file path — use the Read tool to view the image visually.

Typical workflow:
1. gh_canvas_focus() to frame what you want to see
2. gh_canvas_image() to capture it
3. Read the returned file path to analyze the canvas visually

Returns: { filePath, width, height, format, visibleRegion, message }""",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="gh_cluster",
            description="""Create a cluster from specified Grasshopper objects.

Clusters encapsulate components into a reusable sub-graph with exposed inputs/outputs.
Unlike groups, clusters hide internal complexity and can be reused.

Example: Cluster components into a reusable unit:
{"guids": ["abc...", "def..."], "nickname": "MyCluster"}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "guids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Instance GUIDs or short IDs (C1, C2...) from gh_snapshot"
                    },
                    "nickname": {"type": "string", "description": "Display name for the cluster"},
                    "x": {"type": "number", "description": "X position for cluster"},
                    "y": {"type": "number", "description": "Y position for cluster"}
                },
                "required": ["guids"]
            }
        ),

        # GH Canvas Alignment Tools
        Tool(
            name="gh_align",
            description="""Align Grasshopper components along an axis.

Aligns selected components to a common edge or center:
- top/bottom/left/right: Align to the extreme edge
- center_h/center_v: Align to the horizontal/vertical center

The anchor determines the reference: first, last, median, min, or max.

Example: Align 3 sliders to the same left edge:
{"guids": ["a...", "b...", "c..."], "direction": "left"}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "guids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "GUIDs of components to align"
                    },
                    "direction": {
                        "type": "string",
                        "enum": ["top", "bottom", "left", "right", "center_h", "center_v"],
                        "description": "Alignment direction"
                    },
                    "anchor": {
                        "type": "string",
                        "enum": ["first", "last", "median", "min", "max"],
                        "description": "Which component to align to (default: first)",
                        "default": "first"
                    }
                },
                "required": ["guids", "direction"]
            }
        ),
        Tool(
            name="gh_distribute",
            description="""Distribute Grasshopper components evenly along an axis.

Spaces components with equal gaps between them. If spacing is omitted,
components are distributed equally between the first and last positions.

Example: Space 5 components evenly horizontally:
{"guids": ["a...", "b...", "c...", "d...", "e..."], "axis": "horizontal"}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "guids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "GUIDs of components to distribute"
                    },
                    "axis": {
                        "type": "string",
                        "enum": ["horizontal", "vertical"],
                        "description": "Distribution axis"
                    },
                    "spacing": {
                        "type": "number",
                        "description": "Fixed gap between components (omit for equal distribution)"
                    }
                },
                "required": ["guids", "axis"]
            }
        ),
        Tool(
            name="gh_straighten_wires",
            description="""Straighten wires between connected Grasshopper components.

Adjusts Y positions of downstream components to align wire endpoints,
producing clean horizontal wires. Optionally limit to specific components.

Example: Straighten all wires:
{}
Example: Straighten wires for specific components:
{"guids": ["a...", "b..."]}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "guids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "GUIDs to straighten (omit for all connected components)"
                    }
                }
            }
        ),

        # GH Knowledge System Tools
        Tool(
            name="gh_knowledge_query",
            description="""Query the Grasshopper component knowledge system.

Returns component information at different depth levels:
- quick (~20 tokens): Essential syntax, critical gotcha
- context (~50 tokens): Mode-specific rules, params (DEFAULT)
- errors (~30 tokens): What fails and why
- raw (~300 tokens): Full component details

Example: Find components for creating a sphere:
{"intent": "sphere", "depth": "context"}

Example: Get error info for troubleshooting:
{"intent": "addition", "depth": "errors"}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "intent": {
                        "type": "string",
                        "description": "What you want to create/do (e.g., 'sphere', 'slider', 'add numbers')"
                    },
                    "depth": {
                        "type": "string",
                        "enum": ["quick", "context", "errors", "raw"],
                        "description": "Knowledge depth: quick (minimal), context (default), errors (troubleshooting), raw (full)"
                    }
                },
                "required": ["intent"]
            }
        ),
        Tool(
            name="gh_knowledge_reload",
            description="""Reload Grasshopper knowledge from disk.

Call this after editing component knowledge files (knowledge/gh/notes/) or operations knowledge (knowledge/gh/operations_knowledge.json).

Component GUID resolution uses UnifiedStore (922 component notes). Gotcha data uses tiered_knowledge.json.
Returns component note count and gotcha entry count.""",
            inputSchema={
                "type": "object",
                "properties": {},
            }
        ),
        Tool(
            name="gh_query_observations",
            description="""Query past GH operation observations for pattern discovery.

Returns past observations filtered by operation type, component, outcome, or search query.
Useful for learning from past successes, failures, and corrections.

Filters (use one):
- operation: "wire", "connect", "set_value", "delete", "disconnect"
- component: Component name or GUID (partial match)
- outcome: "success", "failure", "correction"
- search: Full-text search across observations

Returns observation list with timestamps, actions, and outcomes.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "description": "Filter by operation type (wire, set_value, delete, disconnect)"
                    },
                    "component": {
                        "type": "string",
                        "description": "Filter by component name or GUID"
                    },
                    "outcome": {
                        "type": "string",
                        "enum": ["success", "failure", "correction"],
                        "description": "Filter by outcome type"
                    },
                    "search": {
                        "type": "string",
                        "description": "Full-text search query"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum results (default: 20)"
                    }
                }
            }
        ),
        Tool(
            name="gh_record_learning",
            description="""Record a learned pattern or correction for GH operations.

Use this when correction_detected is true in a tool response, or when you discover
a new gotcha or pattern about GH operations.

Records to operations_knowledge.json for future reference.

Example - Recording a discovered gotcha:
{
    "operation": "wire",
    "pattern": "Multiply component uses 'A' and 'B' not 'Factor A'",
    "correction": "Use exact param names from gh_snapshot"
}

Example - Recording from correction detection:
{
    "operation": "set_value",
    "pattern": "Setting slider value outside bounds",
    "correction": "Query slider bounds first with gh_snapshot"
}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "description": "Operation type (wire, set_value, delete, disconnect)"
                    },
                    "pattern": {
                        "type": "string",
                        "description": "Description of the mistake pattern or gotcha"
                    },
                    "correction": {
                        "type": "string",
                        "description": "How to correct or avoid this pattern"
                    }
                },
                "required": ["operation", "pattern", "correction"]
            }
        ),
        # Session History Tools (Path 2 meta-learning)
        Tool(
            name="gh_session_current",
            description="""Get current GH session info and statistics.

Returns the active session for the current document including:
- session_id: Unique session identifier
- document: GH document name
- status: active/paused/ended
- entry_count: Total recorded actions
- summary: Success/failure counts, components created, connections made

Sessions are automatically started when GH tools are used. Each document has its own session.
Switching documents pauses the current session and resumes/creates one for the new document.""",
            inputSchema={
                "type": "object",
                "properties": {},
            }
        ),
        Tool(
            name="gh_session_history",
            description="""Query session entries with pagination.

Returns chronological list of recorded GH actions for pattern analysis and reflection.

Args:
- offset: Start index. Use negative values for recent entries (e.g., -20 = last 20 entries)
- limit: Maximum entries to return (default: 50)
- outcome: Filter by "success", "partial", or "failure"

Each entry includes:
- entry_id: Unique ID for citation by patterns
- timestamp: When the action occurred
- action: Tool name (gh_edit, gh_execute_intent, etc.)
- params: Tool parameters
- outcome: success/partial/failure
- components_created/affected/deleted: GUIDs
- connections_made/removed: Wire changes
- notes: Claude's observations (if added via gh_session_note)

Example - Get last 10 entries:
  gh_session_history(offset=-10, limit=10)

Example - Get all failures:
  gh_session_history(outcome="failure", limit=100)""",
            inputSchema={
                "type": "object",
                "properties": {
                    "offset": {
                        "type": "integer",
                        "description": "Start index. Negative = from end (-20 = last 20)"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum entries to return (default: 50)"
                    },
                    "outcome": {
                        "type": "string",
                        "enum": ["success", "partial", "failure"],
                        "description": "Filter by outcome type"
                    }
                }
            }
        ),
        Tool(
            name="gh_session_note",
            description="""Add an observation note to the session.

Use when you:
- Observe unexpected behavior that might be a pattern
- Discover a gotcha or constraint
- Want to mark a breakthrough moment for later reflection
- Need to annotate why something worked/failed

The note is attached to an entry (default: most recent) and persisted with the session.
Notes are visible in gh_session_history and can inform pattern extraction.

Example:
  gh_session_note(note="Slider changes had no visible effect - domain mismatch suspected")
  gh_session_note(note="Fixed by scaling domain by radius", entry_id=15)""",
            inputSchema={
                "type": "object",
                "properties": {
                    "note": {
                        "type": "string",
                        "description": "The observation or insight to record"
                    },
                    "entry_id": {
                        "type": "integer",
                        "description": "Specific entry to annotate (default: most recent)"
                    }
                },
                "required": ["note"]
            }
        ),
        Tool(
            name="gh_session_end",
            description="""End the current session and compute final summary.

Ends the session for the current (or specified) document. The session file is saved
to knowledge/gh/sessions/ for later analysis and pattern extraction.

Returns:
- session_id: The ended session's ID
- duration_minutes: How long the session lasted
- summary: Final statistics (successes, failures, components created, etc.)
- file_path: Where the session file was saved

Sessions auto-end after 1 hour of inactivity. Use this to end explicitly when
you've completed a logical unit of work.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "document": {
                        "type": "string",
                        "description": "Specific document session to end (default: current)"
                    }
                }
            }
        ),
        # =====================================================================
        # Constraint Tools (Phase 6 Meta-Learning)
        # =====================================================================
        Tool(
            name="gh_constraints",
            description="""Query geometric constraints for GH components.

Returns preconditions and postconditions for operations like Loft, Boolean, Sweep.
Use this to understand requirements before complex operations.

Args:
- component: Component name (e.g., "Loft", "Solid Difference")
- components: List of component names to check
- category: Filter by category (e.g., "surface_ops", "solid_ops")

Returns:
- Component-specific constraints with:
  - preconditions: What must be true before execution (severity: error/warning)
  - postconditions: What should be verified after
  - fix_suggestions: How to resolve violations

Example: Get Loft constraints
{"component": "Loft"}

Example: Get constraints for multiple components
{"components": ["Loft", "Solid Difference", "Extrude"]}

Example: Get all surface operation constraints
{"category": "surface_ops"}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "component": {
                        "type": "string",
                        "description": "Single component name to query"
                    },
                    "components": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of component names to query"
                    },
                    "category": {
                        "type": "string",
                        "description": "Category filter (surface_ops, solid_ops, curve_ops)"
                    }
                }
            }
        ),
        # =====================================================================
        # Validation Tools (Phase 7 Meta-Learning)
        # =====================================================================
        Tool(
            name="gh_validate_scenarios",
            description="""Run validation scenarios against pattern memory.

Generates synthetic test scenarios and checks if patterns match them.
Use this to validate the pattern matching system is working.

NOTE: Low match rates indicate coverage gaps, not system failure.
An empty pattern store will have 0% match rate - this is expected.
The 'guidance' field explains what to do based on results.

Args:
- n_scenarios: Number of scenarios to generate (default: 50)
- categories: Categories to test (default: all)
- seed: Random seed for reproducibility (default: 42)

Returns:
- scenarios_run: Number of scenarios tested
- patterns_found: Count of scenarios that found matching patterns
- avg_confidence: Average confidence of matched patterns
- category_coverage: Scenarios per category
- guidance: Actionable advice based on match rate""",
            inputSchema={
                "type": "object",
                "properties": {
                    "n_scenarios": {
                        "type": "integer",
                        "description": "Number of scenarios to generate (default: 50)"
                    },
                    "categories": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Categories to test (default: all)"
                    },
                    "seed": {
                        "type": "integer",
                        "description": "Random seed for reproducibility (default: 42)"
                    }
                }
            }
        ),
        Tool(
            name="gh_validate_latency",
            description="""Benchmark knowledge query latency.

Runs performance benchmarks on pattern queries to ensure they meet targets:
- p50 (median) target: 10ms
- p99 (worst case) target: 50ms

Args:
- n_samples: Number of queries to benchmark (default: 100)
- p50_target_ms: Target for 50th percentile (default: 10)
- p99_target_ms: Target for 99th percentile (default: 50)

Returns:
- n_samples: Queries benchmarked
- p50_ms, p90_ms, p99_ms: Latency percentiles
- passes_targets: Whether targets were met
- message: Pass/fail details""",
            inputSchema={
                "type": "object",
                "properties": {
                    "n_samples": {
                        "type": "integer",
                        "description": "Number of queries to benchmark (default: 100)"
                    },
                    "p50_target_ms": {
                        "type": "number",
                        "description": "Target for 50th percentile (default: 10)"
                    },
                    "p99_target_ms": {
                        "type": "number",
                        "description": "Target for 99th percentile (default: 50)"
                    }
                }
            }
        ),
        Tool(
            name="gh_validate_regression",
            description="""Check for patterns with degraded performance using sliding window analysis.

Uses a sliding window approach to detect regressions even after they've dragged down
the overall rate. Compares historical (older citations) vs recent (newest 5 uses).

A pattern is considered regressed when:
- Has at least 8 citations with outcome data
- HISTORICAL success rate (older citations, excluding recent 5) was >= 70%
- RECENT success rate (last 5 uses) is < 50%

Returns:
- total_patterns: Total patterns in store
- degraded_count: Number of regressed patterns
- degraded_patterns: List with pattern_id, name, historical_success_rate, recent_success_rate, recommendation
- confidence_stats: Breakdown by confidence level""",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        # =====================================================================
        # Reflection Tools (Phase 5 Meta-Learning)
        # =====================================================================
        Tool(
            name="gh_reflect",
            description="""Analyze session for learnable patterns.

Scans the current (or specified) session history for struggle→success sequences
where you failed 2+ times before succeeding. These are learning opportunities.

Returns DRAFT patterns - patterns are NOT auto-saved. Human approval is required.
Use gh_save_pattern to approve and save drafts to permanent memory.

Args:
- session_id: Specific session to analyze (default: current session)
- min_failures: Minimum failures before success to count as struggle (default: 2)
- use_dspy: Use DSPy/LLM for deeper analysis (default: true, falls back to heuristics)

Returns:
- struggles_found: Number of struggle sequences detected
- drafts: Array of DraftPattern objects, each containing:
  - draft_id: Unique ID for this draft (use with gh_save_pattern)
  - session_id: Source session
  - from_entries: Entry IDs that produced this pattern
  - pattern: The draft PatternNote (solution, triggers, anti-patterns)
  - recommendation: "approve", "review", or "skip"
  - recommendation_reason: Why this recommendation was made

Example: Reflect on current session
{}

Example: Reflect on specific session with stricter threshold
{"session_id": "sess_abc123", "min_failures": 3}

Workflow:
1. Call gh_reflect to find learning opportunities
2. Review each draft's recommendation and pattern
3. For drafts you want to keep: gh_save_pattern(draft_id="...")
4. Saved patterns become available via gh_query_patterns""",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Session to analyze (default: current session)"
                    },
                    "min_failures": {
                        "type": "integer",
                        "description": "Min failures before success to count as struggle (default: 2)",
                        "minimum": 1,
                        "default": 2
                    },
                    "use_dspy": {
                        "type": "boolean",
                        "description": "Use DSPy/LLM for analysis (default: true)",
                        "default": True
                    }
                }
            }
        ),
        Tool(
            name="gh_save_pattern",
            description="""Save a draft pattern to permanent memory.

Takes a draft_id from gh_reflect output and saves it to the pattern store.
The pattern becomes available for future sessions via gh_query_patterns.

Args:
- draft_id: The draft ID from gh_reflect output (required)
- modifications: Optional dict of fields to modify before saving:
  - name: Override pattern name
  - solution_brief: Override solution summary
  - tags: Override or add tags
  - trigger_intents: Override trigger intents
  - trigger_symptoms: Override trigger symptoms

Returns:
- success: Whether save succeeded
- pattern_id: The saved pattern's ID
- pattern: The saved pattern data

Example: Save a draft as-is
{"draft_id": "draft_abc12345"}

Example: Save with modifications
{
  "draft_id": "draft_abc12345",
  "modifications": {
    "tags": ["domain-math", "arc-length"],
    "name": "Scale domain by radius for concentric circles"
  }
}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "draft_id": {
                        "type": "string",
                        "description": "Draft ID from gh_reflect output (required)"
                    },
                    "modifications": {
                        "type": "object",
                        "description": "Optional modifications to apply before saving",
                        "properties": {
                            "name": {"type": "string"},
                            "solution_brief": {"type": "string"},
                            "tags": {"type": "array", "items": {"type": "string"}},
                            "trigger_intents": {"type": "array", "items": {"type": "string"}},
                            "trigger_symptoms": {"type": "array", "items": {"type": "string"}}
                        }
                    }
                },
                "required": ["draft_id"]
            }
        ),
        Tool(
            name="gh_extract_recipe",
            description="""Extract a recipe from the current canvas.

Analyzes all components and connections, classifies the pattern using DSPy,
and returns a draft for review.

Returns:
    draft_id: Unique ID for this draft (use with gh_save_recipe)
    suggested_name: DSPy-suggested name
    detected_tags: Pattern type tags
    suggested_intents: Phrases that should match this recipe
    component_count: Number of components
    connection_count: Number of connections
    input_structure: Sliders/panels with inferred roles
    output_type: What the recipe produces

Example: Extract recipe from current canvas
{}

Example: Extract with custom name
{"name": "my_custom_pattern"}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Optional override for suggested name",
                    },
                    "description": {
                        "type": "string",
                        "description": "Optional override for description",
                    },
                    "use_dspy": {
                        "type": "boolean",
                        "description": "Use DSPy for classification (default: true)",
                        "default": True,
                    },
                },
            },
        ),
        Tool(
            name="gh_save_recipe",
            description="""Save an extracted recipe draft to the pattern store.

Takes a draft_id from gh_extract_recipe output and saves it as a permanent
recipe pattern. The recipe becomes searchable via gh_query_patterns.

Returns:
    success: bool
    pattern_id: Saved pattern ID
    pattern: The saved PatternNote data

Example: Save a draft as-is
{"draft_id": "draft_abc12345"}

Example: Save with modifications
{
  "draft_id": "draft_abc12345",
  "modifications": {
    "name": "trigonometric_helix_pipe",
    "tags": ["trigonometric", "parametric", "pipe-output"],
    "intents": ["create helix pipe", "sine wave tube"]
  }
}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "draft_id": {
                        "type": "string",
                        "description": "Draft ID from gh_extract_recipe output (required)",
                    },
                    "modifications": {
                        "type": "object",
                        "description": "Optional modifications to apply before saving",
                        "properties": {
                            "name": {"type": "string"},
                            "tags": {"type": "array", "items": {"type": "string"}},
                            "intents": {"type": "array", "items": {"type": "string"}},
                            "description": {"type": "string"},
                        },
                    },
                },
                "required": ["draft_id"],
            },
        ),
        Tool(
            name="gh_learn_canvas",
            description=(
                "Learn everything from the current GH canvas in one pass.\n\n"
                "Captures knowledge across ALL stores:\n"
                "1. Extracts and saves recipe to PatternStore\n"
                "2. Captures Scribble/Panel annotations as teaching patterns\n"
                "3. Ensures all components are registered in UnifiedStore + SparseIndex + TieredKnowledge (creates or backfills)\n\n"
                "Returns a comprehensive report of what was captured.\n"
                "Use this when studying example definitions or learning new plugin components.\n\n"
                "Example: Learn from current canvas\n"
                "{}\n\n"
                "Example: Learn with custom name and tags\n"
                '{"name": "wasp_basic_aggregation", "tags": ["wasp", "discrete-design"]}'
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Optional recipe name override",
                    },
                    "description": {
                        "type": "string",
                        "description": "Optional description override",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Additional tags to apply to patterns",
                    },
                    "skip_recipe": {
                        "type": "boolean",
                        "description": "Skip recipe extraction (if already saved)",
                        "default": False,
                    },
                },
            },
        ),
        Tool(
            name="gh_replay_recipe",
            description=(
                "Replay a stored v2 recipe onto the Grasshopper canvas.\n\n"
                "Loads a recipe by pattern_id, converts its graph to a gh_edit document,\n"
                "and applies it to the canvas. Only works with v2 recipes (schema_version 2.0).\n\n"
                "The recipe's components are created with T-prefixed temp IDs, and all\n"
                "connections are wired atomically via gh_edit.\n\n"
                "Use offset_x/offset_y to avoid overlapping existing canvas content."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "pattern_id": {
                        "type": "string",
                        "description": "Pattern ID of the v2 recipe to replay (e.g., '5a0d15b5')"
                    },
                    "offset_x": {
                        "type": "integer",
                        "description": "X position offset for all components (default: 0)",
                        "default": 0
                    },
                    "offset_y": {
                        "type": "integer",
                        "description": "Y position offset for all components (default: 0)",
                        "default": 0
                    },
                },
                "required": ["pattern_id"],
            },
        ),
        Tool(
            name="gh_migration_status",
            description=(
                "Show recipe migration progress from v1 to v2 format.\n\n"
                "Returns counts of v1 vs v2 recipes and optionally lists remaining v1 patterns.\n"
                "Use this to track progress when upgrading recipes with gh_upgrade_recipe."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "show_remaining": {
                        "type": "boolean",
                        "description": "If true, include list of remaining v1 pattern IDs and names (default: false)",
                        "default": False,
                    },
                },
            },
        ),
        Tool(
            name="gh_upgrade_recipe",
            description=(
                "Upgrade a v1 recipe pattern to v2 format using the currently-open GH canvas.\n\n"
                "Opens the source .gh file in Grasshopper first, then call this tool.\n"
                "Snapshots the canvas, extracts a v2 graph, and merges it into the existing\n"
                "pattern — preserving all A-MEM metadata (links, tags, confidence, evolution).\n\n"
                "Only updates the recipe section: graph, schema_version, wiring, input_structure,\n"
                "output_type, components_needed. Everything else is untouched.\n\n"
                "Use gh_migration_status to see which patterns still need upgrading."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "pattern_id": {
                        "type": "string",
                        "description": "Pattern ID of the v1 recipe to upgrade (e.g., '04081616')",
                    },
                },
                "required": ["pattern_id"],
            },
        ),
        # =====================================================================
        # Pattern Memory Tools (Phase 2 Meta-Learning)
        # =====================================================================
        Tool(
            name="gh_query_patterns",
            description="""Query pattern memory for relevant solutions.

Use this when:
- Starting a complex GH task (get hints before diving in)
- Observing unexpected behavior (find patterns by symptoms)
- Looking for related patterns (by tags)

Returns patterns ranked by relevance and success rate.

Args:
- intent: What you're trying to do (e.g., "create wedge shape from circles")
- symptoms: What's going wrong (e.g., ["microscopic changes", "wrong angles"])
- tags: Classification tags to filter by (e.g., ["domain-math", "curves"])
- components: GH component names to filter by (e.g., ["Circle", "SubCurve"])
- depth: Detail level - "quick" (~30 tokens), "context" (~100 tokens), "full" (~300 tokens)
- limit: Max patterns to return (default 3)

Example: Find patterns for domain issues:
{"symptoms": ["microscopic slider changes", "arc angles wrong"], "depth": "context"}

Example: Find patterns by intent:
{"intent": "extract arc from circle", "limit": 5}

Example: Find patterns using specific components:
{"components": ["Circle", "Construct Domain"], "tags": ["parameterization"]}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "intent": {
                        "type": "string",
                        "description": "What you're trying to do"
                    },
                    "symptoms": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Observable symptoms or issues"
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Classification tags to filter by"
                    },
                    "components": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "GH component names to filter by"
                    },
                    "depth": {
                        "type": "string",
                        "enum": ["quick", "context", "full"],
                        "description": "Detail level (default: context)"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max patterns to return (default: 3)"
                    },
                    "pattern_type": {
                        "type": "string",
                        "description": "Filter by pattern type: 'struggle', 'recipe', 'teaching', or 'all' (default: 'all')",
                        "enum": ["struggle", "recipe", "teaching", "all"],
                        "default": "all",
                    },
                }
            }
        ),
        Tool(
            name="gh_add_pattern",
            description="""Add a new pattern to pattern memory.

Call this when you've discovered a reusable solution worth remembering.
Automatically extracts metadata (triggers, symptoms, tags) via DSPy
and links to related patterns (A-MEM style evolution).

Args:
- name: Short descriptive name for the pattern
- solution_description: What you learned and what to do (free-form text)
- session_id: Session where this was discovered (for citation)
- entry_range: [start, end] entry IDs in session (for citation)
- components: GH components involved
- skip_evolution: Skip neighbor linking (for bulk imports)

Example: Add a domain scaling pattern:
{
  "name": "Concentric Circle Arc Extraction",
  "solution_description": "When extracting arcs from concentric circles, scale the domain by each circle's radius. GH circles use arc-length parameterization (0 to 2πR), not angular (0 to 2π). Same domain value on different radii produces different angles.",
  "components": ["Circle", "Construct Domain", "SubCurve"],
  "session_id": "gh_session_20260131..."
}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Short descriptive name"
                    },
                    "solution_description": {
                        "type": "string",
                        "description": "What you learned and what to do"
                    },
                    "session_id": {
                        "type": "string",
                        "description": "Session this came from"
                    },
                    "entry_range": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "[start, end] entry IDs"
                    },
                    "components": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "GH components involved"
                    },
                    "skip_evolution": {
                        "type": "boolean",
                        "description": "Skip A-MEM evolution (default: false)"
                    }
                },
                "required": ["name", "solution_description"]
            }
        ),
        Tool(
            name="gh_pattern_links",
            description="""Explore the pattern knowledge graph.

Get a pattern and its linked neighbors to understand related knowledge.
Useful for discovering connected patterns and understanding the knowledge structure.

Args:
- pattern_id: Starting pattern ID
- depth: How many hops to traverse (1 = direct links, 2 = neighbors of neighbors)

Example: Get direct links:
{"pattern_id": "abc123", "depth": 1}

Example: Get extended neighborhood:
{"pattern_id": "abc123", "depth": 2}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "pattern_id": {
                        "type": "string",
                        "description": "Starting pattern ID"
                    },
                    "depth": {
                        "type": "integer",
                        "description": "Hops to traverse (default: 1)"
                    }
                },
                "required": ["pattern_id"]
            }
        ),
        Tool(
            name="gh_record_pattern_use",
            description="""Record that a pattern was used (updates confidence and verification).

Call this after applying a pattern to track what works. Patterns with higher
success rates rank higher in search results.

On successful use:
- Increments times_used and times_succeeded
- Refreshes last_verified timestamp (clears stale status)
- Adds citation linking pattern to this session

Args:
- pattern_id: Pattern that was used
- success: Whether it helped solve the problem
- session_id: Current session (for citation)
- notes: Optional observations

Example: Record successful use:
{"pattern_id": "abc123", "success": true, "session_id": "gh_session_...", "notes": "Worked perfectly for spiral staircase"}

Example: Record failure:
{"pattern_id": "abc123", "success": false, "notes": "Didn't work for 3D curves"}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "pattern_id": {
                        "type": "string",
                        "description": "Pattern that was used"
                    },
                    "success": {
                        "type": "boolean",
                        "description": "Whether it helped"
                    },
                    "session_id": {
                        "type": "string",
                        "description": "Current session"
                    },
                    "notes": {
                        "type": "string",
                        "description": "Optional observations"
                    }
                },
                "required": ["pattern_id", "success"]
            }
        ),
        Tool(
            name="gh_pattern_stats",
            description="""Get statistics about the pattern memory store.

Returns counts of patterns, links, tags, and success metrics.
Useful for understanding the current state of pattern knowledge.""",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="metrics_summary",
            description="""Get performance metrics summary.

Returns today's success rates, A/B comparison (with vs without knowledge injection),
top tools by usage, failing tools, average durations, corrections detected, and
first-attempt success rates. Use this to understand how well knowledge injection
is working and identify problem areas.""",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="metrics_dashboard",
            description="""Open the metrics dashboard web UI.

Starts (or returns URL of) a web dashboard at localhost:8855 showing real-time
metrics: success rates, A/B knowledge comparison, tool performance table,
timing charts, DSPy confidence, and live observation feed.""",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="gh_explore_component",
            description="""Explore a component and convert it to tiered knowledge.

This tool:
1. Creates the component on canvas (if guid provided) or uses existing (if instanceGuid provided)
2. Inspects its parameters via gh_snapshot
3. Builds tiered knowledge entry (quick, params)
4. Saves to tiered_knowledge.json and sparse_index.json

Use this to systematically convert catalog information into queryable knowledge.

Example: Explore Loft component:
{"guid": "45f19d16-1c9f-4a9a6-45a77f3d206c"}

Example: Explore existing component on canvas:
{"instanceGuid": "abc123..."}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "guid": {
                        "type": "string",
                        "description": "Component GUID to create and explore"
                    },
                    "instanceGuid": {
                        "type": "string",
                        "description": "Instance GUID of existing component on canvas"
                    },
                    "save": {
                        "type": "boolean",
                        "description": "Save to knowledge files (default: true)"
                    }
                }
            }
        ),
        Tool(
            name="gh_explore_deep",
            description="""Deep exploration of a component - captures params, data structures, and behavior.

This tool performs thorough exploration:
1. Creates component on canvas
2. Inspects static params (inputs/outputs with types)
3. Wires appropriate test inputs (sliders for numbers, points for geometry)
4. Solves and inspects output data structures (single/list/tree)
5. Tests list input behavior (broadcasts vs aggregates)
6. Captures runtime messages and errors
7. Builds rich tiered knowledge with contexts

Use this for high-quality knowledge capture. Slower than gh_explore_component but much more informative.

Example: Deep explore Sphere:
{"guid": "dabc854d-f50e-408a-b001-d043c7de151d"}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "guid": {
                        "type": "string",
                        "description": "Component GUID to explore deeply"
                    },
                    "save": {
                        "type": "boolean",
                        "description": "Save to knowledge files (default: true)"
                    },
                    "cleanup": {
                        "type": "boolean",
                        "description": "Delete test components after exploration (default: true)"
                    }
                },
                "required": ["guid"]
            }
        ),
        Tool(
            name="gh_batch_component_info",
            description="""Get full metadata and I/O parameters for multiple components by name.

Accepts component NAMES (not GUIDs). Resolves names to GUIDs internally via the
knowledge store, then queries the GH SDK for full metadata including:
- Description (from SDK proxy)
- Category / SubCategory
- Input parameters (name, nickname, type)
- Output parameters (name, nickname, type)

Returns richer data than gh_explore_component — specifically includes the SDK description
that explore_component drops.

Use this for bulk component enrichment or validation.

Example: Get info for Sphere and Loft:
{"names": ["Sphere", "Loft", "Divide Curve"]}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Component names to look up (e.g., ['Sphere', 'Loft'])"
                    }
                },
                "required": ["names"]
            }
        ),
        Tool(
            name="gh_execute_intent",
            description="""Execute a Grasshopper intent - create components and wire them together.

This is the ONLY tool for creating GH components. All component creation MUST go through this tool.
It automatically:
1. Queries the knowledge system for matching components (with gotchas and correct GUIDs)
2. Creates components using learned knowledge
3. Returns warnings about known pitfalls

OPTIONAL PLANNING (Phase 4):
For complex intents, you can submit an execution plan. Plans help organize multi-step work
and are recorded for future reflection. Planning is optional - use your judgment.

Example: Simple execution (no plan):
{"intent": "create a sphere with radius controlled by a slider"}

Example: With execution plan:
{
  "intent": "create spiral staircase treads",
  "plan": {
    "reasoning": "Need concentric circles with radius-scaled domains for wedge shapes",
    "sub_problems": ["Create inner/outer circles", "Extract equal-angle arcs", "Loft treads"],
    "sequence": ["Create circles", "Apply domain scaling", "SubCurve extraction", "Loft"],
    "success_criteria": "Wedge treads that respond to depth slider",
    "patterns_to_apply": ["concentric_circle_arcs"],
    "unknowns": ["Loft vs Ruled Surface for tread"]
  }
}

The tool uses accumulated knowledge to select correct component GUIDs and avoid known issues.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "intent": {
                        "type": "string",
                        "description": "Natural language description of what to create"
                    },
                    "x": {
                        "type": "number",
                        "description": "Base X position on canvas (default: 100)"
                    },
                    "y": {
                        "type": "number",
                        "description": "Base Y position on canvas (default: 100)"
                    },
                    "plan": {
                        "type": "object",
                        "description": "Optional execution plan for complex intents. Validated and recorded for reflection. Step tracking shows which sequence steps were executed (for Phase 5 reflection).",
                        "properties": {
                            "reasoning": {
                                "type": "string",
                                "description": "Free text explaining approach and considerations (REQUIRED)"
                            },
                            "sub_problems": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Breakdown of the intent into sub-tasks (REQUIRED)"
                            },
                            "sequence": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Ordered steps to execute (REQUIRED)"
                            },
                            "success_criteria": {
                                "type": "string",
                                "description": "What success looks like (REQUIRED)"
                            },
                            "patterns_to_apply": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Pattern IDs from pattern memory to apply (optional)"
                            },
                            "constraints_checked": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Geometric constraints verified (optional)"
                            },
                            "unknowns": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Acknowledged uncertainties - encouraged! (optional)"
                            }
                        }
                    }
                },
                "required": ["intent"]
            }
        ),

        # GH Exploration Tools (for learning and knowledge capture)
        Tool(
            name="gh_start_exploration",
            description="""Start a Grasshopper exploration session for knowledge capture.

All observations during the session are automatically recorded to the knowledge base.
Use this before experimenting with components, wiring patterns, or data structures.

Example: Start exploring data trees:
{"session_name": "data_tree_exploration"}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_name": {
                        "type": "string",
                        "description": "Descriptive name for the session (e.g., 'data_tree_exploration', 'curve_operations')"
                    }
                },
                "required": ["session_name"]
            }
        ),
        Tool(
            name="gh_end_exploration",
            description="""End the current exploration session and get a summary.

Returns the session ID and count of observations recorded.""",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="gh_explore_workflow",
            description="""Execute a workflow pattern and capture all observations.

Creates components, wires them, and records everything:
- Success/failure at each step
- Runtime messages and errors
- Output data structures (types, tree shapes)

Automatically records observations for failures and interesting discoveries.

Example: Test sphere with slider wiring:
{
  "workflow": {
    "components": [
      {"role": "input", "type": "slider", "nickname": "R", "value": 10},
      {"role": "main", "type": "sphere"}
    ],
    "wiring": [
      {"from": 0, "to": 1, "target_param": "R"}
    ]
  },
  "description": "Parametric sphere with radius slider"
}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "workflow": {
                        "type": "object",
                        "description": "Workflow definition with components and wiring",
                        "properties": {
                            "components": {
                                "type": "array",
                                "description": "Components to create, in order. Each has: role (input/main), type (slider/panel/sphere/etc), optional nickname/value"
                            },
                            "wiring": {
                                "type": "array",
                                "description": "Connections to make. Each has: from (index), to (index), target_param (name)"
                            }
                        }
                    },
                    "description": {
                        "type": "string",
                        "description": "What this workflow is testing/exploring"
                    },
                    "x": {
                        "type": "number",
                        "description": "Base X position (default: 100)"
                    },
                    "y": {
                        "type": "number",
                        "description": "Base Y position (default: 100)"
                    }
                },
                "required": ["workflow", "description"]
            }
        ),
        Tool(
            name="gh_inspect_output",
            description="""Inspect the output data structure of a component.

Returns detailed info about the output:
- Data type (number, point, curve, etc.)
- Structure (single value, list, tree)
- For trees: branch paths and item counts
- For lists: length and sample values

Essential for understanding data tree behavior.

Example: Inspect sphere output:
{"guid": "abc-123", "param": "S"}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "guid": {
                        "type": "string",
                        "description": "Component instance GUID or short ID (C1, C2...) from gh_snapshot"
                    },
                    "param": {
                        "type": "string",
                        "description": "Output parameter name or index (default: first output)"
                    }
                },
                "required": ["guid"]
            }
        ),
        Tool(
            name="gh_bake_output",
            description="""Bake Grasshopper output geometry into the Rhino document with layer control.

Materializes computed GH geometry as Rhino objects organized in deterministic layers.

Two modes:
- Explicit targets: specify instanceGuid + outputIndex for each output to bake
- Convenience: set bakeAll=true to bake all component outputs with bakeable geometry

Sublayer naming is deterministic: {layerName}::{nickname}_{guid8}::O{index}
This enables idempotent rebakes with clearExisting=true.

Clearing semantics:
- With sublayers (default): clearExisting only removes prior bake on that specific sublayer
- Without sublayers: clearExisting requires explicit clearMode="layer" (safety gate)

Provenance tags are set on every baked object for traceability.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "targets": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "instanceGuid": {"type": "string", "description": "Component instance GUID"},
                                "outputIndex": {"type": "integer", "description": "Output parameter index"},
                                "outputName": {"type": "string", "description": "Output name for validation (or name-only resolution if outputIndex omitted)"}
                            },
                            "required": ["instanceGuid"]
                        },
                        "description": "Explicit list of outputs to bake. Mutually exclusive with bakeAll."
                    },
                    "bakeAll": {
                        "type": "boolean",
                        "description": "Bake all component outputs with bakeable geometry. Mutually exclusive with targets."
                    },
                    "layerName": {
                        "type": "string",
                        "description": "Parent layer name (default: RookBake)"
                    },
                    "createSublayers": {
                        "type": "boolean",
                        "description": "Create deterministic sublayers per output (default: true)"
                    },
                    "clearExisting": {
                        "type": "boolean",
                        "description": "Clear prior geometry before baking (default: false)"
                    },
                    "clearMode": {
                        "type": "string",
                        "enum": ["layer"],
                        "description": "Required when clearExisting=true and createSublayers=false. Set to 'layer' to explicitly opt into whole-layer clearing."
                    }
                }
            }
        ),

        # GH Investigation Tools (for self-reflective learning)
        Tool(
            name="gh_investigate",
            description="""Investigate a component configuration with hypothesis-driven reasoning.

REQUIRES Claude to provide a hypothesis explaining WHY this configuration might work.
Records the attempt and result for knowledge building.

This tool:
1. Creates the component (or uses existing instance)
2. Wires inputs according to config
3. Solves and captures result (outputs, errors, warnings)
4. Records observation with hypothesis
5. Suggests next investigation step if failed

Use this after gh_explore_deep returns errors, to systematically find working configurations.

Example - Investigating Pipe cap types:
{
    "guid": "adeadd58-4e28-46ed-853a-b590507d892e",
    "hypothesis": "Error says only 0,1,2 allowed. E=0 might mean no caps.",
    "config": {"E": {"type": "integer", "value": 0}},
    "intent": "Find valid cap type for Pipe",
    "attempt": 2
}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "guid": {
                        "type": "string",
                        "description": "Component type GUID to investigate"
                    },
                    "hypothesis": {
                        "type": "string",
                        "description": "REQUIRED - Claude's reasoning for why this config might work"
                    },
                    "config": {
                        "type": "object",
                        "description": "Input configuration to try. Keys are param names, values are {type, value} or {type, source, source_guid}"
                    },
                    "intent": {
                        "type": "string",
                        "description": "What we're trying to learn from this investigation"
                    },
                    "attempt": {
                        "type": "integer",
                        "description": "Attempt number in investigation sequence (default: 1)"
                    },
                    "previousObservationId": {
                        "type": "string",
                        "description": "ID of previous failed attempt (links investigation chain)"
                    },
                    "cleanup": {
                        "type": "boolean",
                        "description": "Delete test components after investigation (default: true)"
                    }
                },
                "required": ["guid", "hypothesis", "config", "intent"]
            }
        ),
        Tool(
            name="gh_record_investigation",
            description="""Record verified learnings from an investigation sequence.

Call this after successfully investigating a component to:
1. Promote observations to knowledge
2. Add working configs to tiered_knowledge.json
3. Extract and save gotchas
4. Update the errors tier with debugging info

ONLY call when you have:
- A successful configuration
- Understanding of what failed before
- A clear gotcha to document

Example - Recording Pipe cap type learning:
{
    "component_guid": "adeadd58-4e28-46ed-853a-b590507d892e",
    "observation_ids": ["gh_obs_pipe_001", "gh_obs_pipe_002"],
    "working_config": {"id": "pipe_no_caps", "config": {"E": 0}, "description": "Open pipe"},
    "gotcha": "E must be 0, 1, or 2. 0=none, 1=flat, 2=round. Values >2 fail.",
    "context": "cap_types"
}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "component_guid": {
                        "type": "string",
                        "description": "Component type GUID"
                    },
                    "observation_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "IDs of observations in this investigation journey"
                    },
                    "working_config": {
                        "type": "object",
                        "description": "The configuration that works",
                        "properties": {
                            "id": {"type": "string", "description": "Short identifier (e.g., 'pipe_no_caps')"},
                            "description": {"type": "string", "description": "Human description"},
                            "config": {"type": "object", "description": "The actual config values"}
                        },
                        "required": ["id", "description", "config"]
                    },
                    "gotcha": {
                        "type": "string",
                        "description": "What we learned - the gotcha/warning for future use"
                    },
                    "context": {
                        "type": "string",
                        "description": "Context name for tiered knowledge (e.g., 'cap_types', 'data_flow')"
                    }
                },
                "required": ["component_guid", "observation_ids", "working_config", "gotcha"]
            }
        ),
        Tool(
            name="gh_consolidate",
            description="""Run structural consolidation on GH component knowledge using DSPy.

Discovers relationships between components:
- FAMILIES: Groups components by function (primitives, curves, surface_ops)
- SHARED BEHAVIORS: Gotchas that apply across multiple components (e.g., "enum params must be 0-2")
- SIMILAR PAIRS: Links semantically similar components (Pipe/Sweep1, Circle/Ellipse)
- IO PATTERNS: Common parameter patterns (curve_input, brep_output, enum_type)

Modes:
- full: Complete 4-stage consolidation (default, ~10-20 DSPy calls)
- incremental: Place new components into existing structure
- query: Just return current structure without modification

Output saved to knowledge/gh/component_structure.json

Example:
{
    "mode": "full"
}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "mode": {
                        "type": "string",
                        "enum": ["full", "incremental", "query"],
                        "description": "Consolidation mode (default: full)"
                    },
                    "orphan_mode": {
                        "type": "string",
                        "enum": ["legacy-include", "strict", "repair"],
                        "description": "How to handle GUIDs in tiered_knowledge but not in UnifiedStore. 'legacy-include' (default): retain with warning. 'strict': reject. 'repair': create minimal notes."
                    }
                },
                "required": []
            }
        ),
        Tool(
            name="gh_structure_query",
            description="""Query the GH component structure (families, similar pairs, behaviors).

Use this to understand relationships between components:
- What family does a component belong to?
- What components are similar to this one?
- What shared behaviors/gotchas apply?

Examples:
- Query by GUID: {"guid": "adeadd58-4e28-46ed-853a-b590507d892e"}
- Query by name: {"name": "Sphere"}
- Query by stable key: {"stable_key": "primitives|surfaces|sphere"}
- Query family: {"family": "surface_ops"}
- Overview of all structure: {} (no params)

Returns:
- families: Component groupings with shared traits
- similar_pairs: Related components that may share behaviors
- shared_behaviors: Gotchas that apply across components
- io_patterns: Common parameter patterns""",
            inputSchema={
                "type": "object",
                "properties": {
                    "guid": {
                        "type": "string",
                        "description": "Query structure info for a specific component GUID"
                    },
                    "family": {
                        "type": "string",
                        "description": "Query all components in a family (e.g., 'surface_ops', 'primitives')"
                    },
                    "name": {
                        "type": "string",
                        "description": "Query by component name (e.g., 'Sphere', 'Pipe'). Resolved to GUID via component metadata."
                    },
                    "stable_key": {
                        "type": "string",
                        "description": "Query by stable identity key (e.g., 'primitives|surfaces|sphere')"
                    }
                },
                "required": []
            }
        ),

        # ── UV Texture Mapping ────────────────────────────────────────────

        Tool(
            name="rhino_apply_uv_box_mapping",
            description="Apply object-oriented box UV mapping to Breps/Meshes. Auto-orients mapping box to geometry's dominant edge direction. Scale defaults to 1 UV unit = 1 meter (unit-aware).",
            inputSchema={
                "type": "object",
                "properties": {
                    "ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Rhino object GUIDs to apply box mapping to"
                    },
                    "scale": {
                        "type": "number",
                        "description": "Document units per UV unit (default: auto from doc units, e.g. 1000 for mm = 1 meter)"
                    },
                    "channel": {
                        "type": "integer",
                        "description": "Texture mapping channel (default: 1)"
                    }
                },
                "required": ["ids"]
            }
        ),
        Tool(
            name="rhino_apply_uv_planar_mapping",
            description="Apply planar UV mapping with plane selection. Auto mode orients to geometry's dominant edge direction. Scale defaults to 1 UV unit = 1 meter (unit-aware).",
            inputSchema={
                "type": "object",
                "properties": {
                    "ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Rhino object GUIDs to apply planar mapping to"
                    },
                    "plane": {
                        "type": "string",
                        "enum": ["auto", "world_xy", "world_yz", "world_zx"],
                        "description": "Mapping plane: auto (oriented to geometry), world_xy, world_yz, world_zx (default: auto)"
                    },
                    "scale": {
                        "type": "number",
                        "description": "Document units per UV unit (default: auto from doc units, e.g. 1000 for mm = 1 meter)"
                    },
                    "channel": {
                        "type": "integer",
                        "description": "Texture mapping channel (default: 1)"
                    }
                },
                "required": ["ids"]
            }
        ),

        Tool(
            name="rhino_apply_uv_cylinder_mapping",
            description="Apply cylindrical UV mapping. Auto-detects cylinder axis from geometry's longest dimension. Scale defaults to 1 UV unit = 1 meter (unit-aware). Best for columns, pipes, rails, round extrusions.",
            inputSchema={
                "type": "object",
                "properties": {
                    "ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Rhino object GUIDs to apply cylinder mapping to"
                    },
                    "axis": {
                        "type": "string",
                        "enum": ["auto", "x", "y", "z"],
                        "description": "Cylinder axis: auto (longest dimension), x, y, z (default: auto)"
                    },
                    "capped": {
                        "type": "boolean",
                        "description": "Whether to cap the cylinder ends with separate UV regions (default: true)"
                    },
                    "scale": {
                        "type": "number",
                        "description": "Document units per UV unit (default: auto from doc units, e.g. 1000 for mm = 1 meter)"
                    },
                    "channel": {
                        "type": "integer",
                        "description": "Texture mapping channel (default: 1)"
                    }
                },
                "required": ["ids"]
            }
        ),
        Tool(
            name="rhino_apply_uv_sphere_mapping",
            description="Apply spherical UV mapping. Centers sphere on each object's bounding box. Scale defaults to 1 UV unit = 1 meter (unit-aware). Best for domes, balls, organic shapes.",
            inputSchema={
                "type": "object",
                "properties": {
                    "ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Rhino object GUIDs to apply spherical mapping to"
                    },
                    "scale": {
                        "type": "number",
                        "description": "Document units per UV unit (default: auto from doc units, e.g. 1000 for mm = 1 meter)"
                    },
                    "channel": {
                        "type": "integer",
                        "description": "Texture mapping channel (default: 1)"
                    }
                },
                "required": ["ids"]
            }
        ),

        # ── Game Export Pipeline (Rhino-to-Games / Engram) ────────────────

        Tool(
            name="rhino_tag_object_semantic",
            description="Tag Rhino objects with game export metadata (semantic type, collision, Nanite, material intent) via user strings. These tags are preserved through Datasmith import into UE5.",
            inputSchema={
                "type": "object",
                "properties": {
                    "ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Rhino object GUIDs to tag"
                    },
                    "semantic_type": {
                        "type": "string",
                        "description": "Object type: wall, floor, ceiling, roof, column, beam, glass, door, window, stair, railing, prop, furniture, landscape, structural, other"
                    },
                    "collision": {
                        "type": "string",
                        "description": "UE5 collision type: no_collision, box, sphere, capsule, convex_decomposition, complex_as_simple, simple_as_complex"
                    },
                    "nanite": {
                        "type": "boolean",
                        "description": "Enable Nanite on this mesh in UE5"
                    },
                    "material_intent": {
                        "type": "object",
                        "description": "Material hints for UE5: {type, finish, ue_material_hint}"
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Freeform tags for filtering (e.g., ['structural', 'exterior'])"
                    }
                },
                "required": ["ids"]
            }
        ),
        Tool(
            name="rhino_tag_objects_from_layers",
            description="Batch-tag all objects with game export metadata based on layer naming convention (e.g., Architecture::Walls::Exterior → wall). Tag-once semantics: skips objects already tagged.",
            inputSchema={
                "type": "object",
                "properties": {
                    "mapping": {
                        "type": "object",
                        "description": "Custom layer keyword → tag mapping. Keys are keywords to match in layer path, values are {semantic_type, collision, nanite}."
                    },
                    "apply_defaults": {
                        "type": "boolean",
                        "description": "Use built-in defaults (Walls→wall, Floors→floor, Glass→glass, etc.). Default: true"
                    }
                },
                "required": []
            }
        ),
        Tool(
            name="rhino_validate_export",
            description="Advisory pre-flight checks before game export: naked edges, manifold meshes, material assignment, semantic tagging. Never blocks export.",
            inputSchema={
                "type": "object",
                "properties": {
                    "ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Validate specific objects (default: all)"
                    },
                    "selection": {
                        "type": "boolean",
                        "description": "Validate selected objects only"
                    }
                },
                "required": []
            }
        ),
        Tool(
            name="rhino_export_with_manifest",
            description="Export .3dm file with a companion _manifest.json for Engram/UE5 import. The manifest carries semantic types, collision settings, Nanite hints, and material mappings matched by Rhino UUID.",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Output .3dm file path"
                    },
                    "selection": {
                        "type": "boolean",
                        "description": "Export only selected objects"
                    },
                    "ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Export specific objects by GUID"
                    },
                    "settings": {
                        "type": "object",
                        "description": "Manifest-level defaults: {tessellation, chord_tolerance, default_collision, default_nanite}"
                    },
                    "material_map": {
                        "type": "object",
                        "description": "Rhino material name → UE5 material config: {ue_material, ue_material_instance, parameters}"
                    },
                    "level_placement": {
                        "type": "object",
                        "description": "UE5 placement: {origin_offset, scale_factor, target_level}"
                    }
                },
                "required": ["path"]
            }
        ),
        Tool(
            name="rhino_prepare_for_game_export",
            description="One-command game export pipeline: auto-tag objects from layers → validate geometry → export .3dm + manifest. Always runs to completion, reports all results.",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Output .3dm file path"
                    },
                    "selection": {
                        "type": "boolean",
                        "description": "Export only selected objects"
                    },
                    "ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Export specific objects by GUID"
                    },
                    "skip_tagging": {
                        "type": "boolean",
                        "description": "Skip auto-tag-from-layers step (if already tagged)"
                    },
                    "skip_validation": {
                        "type": "boolean",
                        "description": "Skip validation step"
                    },
                    "mapping": {
                        "type": "object",
                        "description": "Custom layer keyword → tag mapping (passed to tag-from-layers)"
                    },
                    "settings": {
                        "type": "object",
                        "description": "Manifest-level defaults (passed to export)"
                    },
                    "material_map": {
                        "type": "object",
                        "description": "Rhino material name → UE5 material config (passed to export)"
                    },
                    "level_placement": {
                        "type": "object",
                        "description": "UE5 placement config (passed to export)"
                    }
                },
                "required": ["path"]
            }
        ),
        # ---- Agent System ----
        Tool(
            name="spawn_agent",
            description="Spawn a single worker agent to execute a task autonomously in the background. Returns agent_id immediately. Use agent_status to poll for completion. The agent uses Haiku by default and has access to Rhino/GH tools.",
            inputSchema={
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "Natural-language task for the agent to execute"},
                    "tool_groups": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tool groups to preload (e.g. 'rhino_geometry', 'gh_canvas'). Available: rhino_geometry, rhino_transform, rhino_curves, rhino_surfaces, rhino_mesh, rhino_subd, rhino_blocks, rhino_selection, rhino_measurement, layers, viewport, rhino_commands, materials, game_export, gumball, annotation, import_export, gh_canvas, gh_exploration, gh_document, gh_references, gh_validation"
                    },
                    "model": {"type": "string", "description": "LiteLLM model ID (default: claude-haiku-4-5)"},
                    "max_turns": {"type": "integer", "description": "Max agent turns (default: 30)"},
                    "workspace_assets": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Rhino layers/objects this agent may modify (e.g. 'Layer::Walls')"
                    },
                    "guardian_enabled": {"type": "boolean", "description": "Enable Guardian trajectory monitor (default: true)"},
                    "max_input_tokens": {"type": "integer", "description": "Token budget for the task (default: 500000). Increase for complex GH definitions."}
                },
                "required": ["prompt"]
            }
        ),
        Tool(
            name="plan_and_execute",
            description="Decompose a complex task via Sonnet planner, then execute with Haiku workers in the background. Returns plan_id immediately. Use agent_status to poll for completion. Use for multi-step design tasks.",
            inputSchema={
                "type": "object",
                "properties": {
                    "request": {"type": "string", "description": "Natural-language design request to decompose and execute"},
                    "auto_approve": {"type": "boolean", "description": "Execute plan immediately without approval pause (default: true)"},
                    "planner_model": {"type": "string", "description": "Model for planning phase (default: claude-sonnet-4-5)"},
                    "worker_model": {"type": "string", "description": "Model for worker execution (default: claude-haiku-4-5)"}
                },
                "required": ["request"]
            }
        ),
        Tool(
            name="agent_status",
            description="Check the status of running or completed agents. Returns agent ID, state, turn count, cost, and active tools.",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent_id": {"type": "string", "description": "Specific agent ID to check. If omitted, returns all active agents."}
                },
                "required": []
            }
        ),
        Tool(
            name="agent_abort",
            description="Abort a running agent by ID. The agent will wrap up immediately.",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent_id": {"type": "string", "description": "Agent ID to abort"}
                },
                "required": ["agent_id"]
            }
        ),
        Tool(
            name="agent_answer",
            description=(
                "Answer a pending question from a running agent. "
                "The agent is blocked waiting for this response. "
                "Use agent_status to see if an agent has a pending_question."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "agent_id": {
                        "type": "string",
                        "description": "Agent ID that asked the question",
                    },
                    "answer": {
                        "type": "string",
                        "description": "Your response to the agent's question",
                    },
                },
                "required": ["agent_id", "answer"],
            },
        ),

        # ─── Scene Graph / Spatial Intelligence ───────────────────────
        Tool(
            name="scene_graph",
            description="""Get the scene graph — a spatial map of all objects in the Rhino scene with their classifications, metrics, and relationships (contains, supports, adjacent, above/below, near).

Use depth to control detail:
- "summary": counts and classification breakdown only
- "compact": node names/labels + edge list (default)
- "full": complete metrics, provenance, and edge data

The graph updates automatically as objects are created/modified/deleted. Call scene_graph first to understand the spatial layout before modifying objects.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "depth": {
                        "type": "string",
                        "enum": ["summary", "compact", "full"],
                        "description": "Detail level (default: compact)"
                    },
                    "port": {"type": "integer", "description": "Rhino instance port"}
                },
                "required": []
            }
        ),
        Tool(
            name="scene_context",
            description="""Get natural-language spatial context for specific objects. Returns a human-readable summary including classification, dimensions, layer, provenance (who created it and why), and all spatial relationships with neighbors.

Use this before modifying objects to understand their spatial role.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "object_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "GUIDs of objects to get context for"
                    },
                    "port": {"type": "integer", "description": "Rhino instance port"}
                },
                "required": ["object_ids"]
            }
        ),
        Tool(
            name="scene_query",
            description="""Query the scene graph with filters. Returns a subgraph matching ALL specified criteria (AND logic).

Filter by any combination of: object IDs, layers, relationship types, bounding box region, or shape classifications.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "object_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Filter to these specific object GUIDs"
                    },
                    "layers": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Filter by layer name (substring match, case-insensitive)"
                    },
                    "relationship_types": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Filter edges: contains, supports, adjacent, above, near, intersects"
                    },
                    "shape_classes": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Filter by shape class or domain label (e.g., wall, floor, column)"
                    },
                    "bbox": {
                        "type": "object",
                        "properties": {
                            "min": {"type": "array", "items": {"type": "number"}, "description": "[x, y, z]"},
                            "max": {"type": "array", "items": {"type": "number"}, "description": "[x, y, z]"}
                        },
                        "description": "Bounding box region filter"
                    },
                    "depth": {
                        "type": "string",
                        "enum": ["summary", "compact", "full"],
                        "description": "Detail level (default: compact)"
                    },
                    "port": {"type": "integer", "description": "Rhino instance port"}
                },
                "required": []
            }
        ),
        Tool(
            name="scene_stats",
            description="Get scene graph statistics: node/edge counts, classification breakdown, relationship type distribution, and graph connectivity metrics.",
            inputSchema={
                "type": "object",
                "properties": {
                    "port": {"type": "integer", "description": "Rhino instance port"}
                },
                "required": []
            }
        ),
        Tool(
            name="scene_classify",
            description="""Force reclassification of objects in the scene graph. Optionally switch the domain profile (general or architecture).

Use this after bulk geometry changes, or to switch between general-purpose labels (panel, slab, block) and architecture-specific labels (wall, floor, column, beam).""",
            inputSchema={
                "type": "object",
                "properties": {
                    "profile": {
                        "type": "string",
                        "enum": ["general", "architecture"],
                        "description": "Domain profile for classification"
                    },
                    "object_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Specific objects to reclassify (default: all)"
                    },
                    "port": {"type": "integer", "description": "Rhino instance port"}
                },
                "required": []
            }
        ),
        Tool(
            name="scene_overlay",
            description="""Toggle the scene graph viewport overlay in Rhino. Shows colored relationship lines between objects and floating classification labels.

Colors: red=supports, blue=contains, green=adjacent, yellow=near, gray=intersects, orange=above.
Labels show domain classification (e.g. WALL, FLOOR) or shape class (e.g. vertical-planar).""",
            inputSchema={
                "type": "object",
                "properties": {
                    "enabled": {
                        "type": "boolean",
                        "description": "Turn overlay on or off"
                    },
                    "show_labels": {
                        "type": "boolean",
                        "description": "Show classification labels above objects (default: true)"
                    },
                    "show_edges": {
                        "type": "boolean",
                        "description": "Show relationship lines between objects (default: true)"
                    },
                    "port": {"type": "integer", "description": "Rhino instance port"}
                },
                "required": []
            }
        ),

        # ── RoadCreator (RookRoads plugin) ─────────────────────────────────────
        Tool(
            name="rc_ping",
            description="Check that the RookRoads plugin is loaded and responsive.",
            inputSchema={"type": "object", "properties": {}, "required": []}
        ),
        Tool(
            name="rc_standards",
            description="List all Czech road categories (S6.5, S7.5, S9.5, D2×5.5, etc.) with half-width and divided-carriageway flag.",
            inputSchema={"type": "object", "properties": {}, "required": []}
        ),
        Tool(
            name="rc_roads",
            description="List all road names currently in the active Rhino document (reads RoadCreator layer hierarchy).",
            inputSchema={"type": "object", "properties": {}, "required": []}
        ),
        Tool(
            name="rc_clothoid",
            description="""Compute a clothoid (Euler spiral) transition curve.
Returns point array in local transition space, large tangent, shift, and xs.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "L": {"type": "number", "description": "Transition length (m)"},
                    "R": {"type": "number", "description": "End radius (m)"},
                },
                "required": ["L", "R"]
            }
        ),
        Tool(
            name="rc_cubic_parabola",
            description="Compute a cubic parabola transition curve. Same interface as rc_clothoid.",
            inputSchema={
                "type": "object",
                "properties": {
                    "L": {"type": "number", "description": "Transition length (m)"},
                    "R": {"type": "number", "description": "End radius (m)"},
                },
                "required": ["L", "R"]
            }
        ),
        Tool(
            name="rc_vertical_curve",
            description="""Compute a parabolic vertical curve (grade change).
Returns profile points, important points (ZZ/V/KZ), tangent length, and sag/crest flag.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "R": {"type": "number", "description": "Vertical curve radius (m)"},
                    "grade1": {"type": "number", "description": "Incoming grade (%)"},
                    "grade2": {"type": "number", "description": "Outgoing grade (%)"},
                    "vertexChainage": {"type": "number", "description": "Chainage of grade intersection (m)"},
                    "vertexElevation": {"type": "number", "description": "Elevation at grade intersection (m)"},
                },
                "required": ["R", "grade1", "grade2", "vertexChainage", "vertexElevation"]
            }
        ),
        Tool(
            name="rc_assemble_route",
            description="Combine horizontal alignment points with per-point elevations into a 3D route point array.",
            inputSchema={
                "type": "object",
                "properties": {
                    "horizontalPoints": {
                        "type": "array",
                        "items": {"type": "object", "properties": {"x": {"type": "number"}, "y": {"type": "number"}, "z": {"type": "number"}}},
                        "description": "Horizontal alignment points"
                    },
                    "elevations": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "Real-world elevation at each horizontal point"
                    },
                },
                "required": ["horizontalPoints", "elevations"]
            }
        ),
        Tool(
            name="rc_cross_section",
            description="""Compute a road cross-section profile in local space (X=lateral offset, Y=elevation change).
Use rc_standards to get valid category codes.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "category": {"type": "string", "description": "Road category code (e.g. S95, D275)"},
                    "widening": {"type": "number", "description": "Extra lane widening for curves (m, default 0)"},
                    "crossfallStraight": {"type": "number", "description": "Crossfall on straight sections (%)"},
                    "crossfallCurve": {"type": "number", "description": "Crossfall on curved sections (%)"},
                    "curveDirection": {"type": "number", "description": "1=right curve, -1=left curve, 0=straight"},
                    "includeVerge": {"type": "boolean", "description": "Include verge/shoulder (default false)"},
                },
                "required": ["category", "crossfallStraight", "crossfallCurve", "curveDirection"]
            }
        ),
        Tool(
            name="rc_road_3d",
            description="""Generate a 3D road surface brep from a road's 3D route curve.
Two modes: profile mode (profileName or inline profile) or legacy category mode.
Profile mode uses RoadProfileDefinition to define the cross-section; rejects category and includeVerge.
Legacy mode uses road category code with explicit crossfall values.
Reads the route from the document (run RC_Assemble3DRoute first), sweeps cross-sections along it,
and adds the brep to the 'RoadCreator::<road>::3D Road' layer.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "road": {"type": "string", "description": "Road name (e.g. Road_1) — required in both modes"},
                    "profileName": {"type": "string", "description": "Profile mode: name of stored RC_RoadProfile"},
                    "profile": {"type": "object", "description": "Profile mode: inline RoadProfileDefinition JSON"},
                    "category": {"type": "string", "description": "Legacy mode: road category code (e.g. S 7.5). Rejected in profile mode."},
                    "crossfallStraight": {"type": "number", "description": "Crossfall on straights (%). Required in legacy mode, optional override in profile mode."},
                    "crossfallCurve": {"type": "number", "description": "Crossfall on curves (%). Required in legacy mode, optional override in profile mode."},
                    "includeVerge": {"type": "boolean", "description": "Legacy mode only: include verge (default false). Rejected in profile mode."},
                },
                "required": ["road"]
            }
        ),
        Tool(
            name="rc_extract_offsets",
            description="""Extract perpendicular offsets from a centerline curve to feature curves.
Samples at the arc-length midpoint of the centerline, measures perpendicular distance to each
feature curve, and determines left/right side. Returns observations with curveId, layer,
objectName, side, and offset — suitable for feeding into rc_build_profile as annotated observations.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "centerlineId": {"type": "string", "description": "GUID of the centerline curve"},
                    "curveIds": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "GUIDs of feature curves (curbs, bike lanes, ROW, etc.)"
                    },
                },
                "required": ["centerlineId", "curveIds"]
            }
        ),
        Tool(
            name="road_intersection_candidates",
            description="""Enumerate viable intersection candidates between two centerline curves.

Use this first when the pair may cross more than once. Returns candidate ids, points,
angles, and profile-aware clearance scoring when profiles are supplied.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "centerlineA": {"type": "string", "description": "GUID of the first centerline curve"},
                    "centerlineB": {"type": "string", "description": "GUID of the second centerline curve"},
                    "profileA": {"type": "string", "description": "Optional road profile name for road A"},
                    "profileB": {"type": "string", "description": "Optional road profile name for road B"},
                    "tolerance": {"type": "number", "description": "Optional intersection tolerance override"},
                    "overlapTolerance": {"type": "number", "description": "Optional overlap tolerance override"},
                },
                "required": ["centerlineA", "centerlineB"]
            }
        ),
        Tool(
            name="road_intersection_resolve",
            description="""Analyze and realize one or more road intersections between two centerline curves.

Uses the native /road/intersection/resolve contract. If multiple crossings exist, set
candidateMode='all' or supply candidateId for a single crossing. If a profile has unilateral
features, provide asymmetricSideA/B explicitly.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "centerlineA": {"type": "string", "description": "GUID of the first centerline curve"},
                    "centerlineB": {"type": "string", "description": "GUID of the second centerline curve"},
                    "profileA": {"type": "string", "description": "Road profile name for road A"},
                    "profileB": {"type": "string", "description": "Road profile name for road B"},
                    "candidateMode": {
                        "type": "string",
                        "description": "Candidate resolution mode",
                        "enum": ["single", "all"]
                    },
                    "candidateId": {"type": "string", "description": "Explicit candidate id when resolving a single crossing"},
                    "asymmetricSideA": {
                        "type": "string",
                        "description": "Resolved side for unilateral features on road A",
                        "enum": ["left", "right"]
                    },
                    "asymmetricSideB": {
                        "type": "string",
                        "description": "Resolved side for unilateral features on road B",
                        "enum": ["left", "right"]
                    },
                    "targetLayerRoot": {"type": "string", "description": "Layer root for created boundary and surface output"},
                    "tolerance": {"type": "number", "description": "Optional intersection tolerance override"},
                    "overlapTolerance": {"type": "number", "description": "Optional overlap tolerance override"},
                    "filletRadii": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "Optional per-corner fillet radii override"
                    },
                    "writeApproachEdges": {"type": "boolean", "description": "Preserve approach edges for debugging"},
                    "writeApproachPatches": {"type": "boolean", "description": "Preserve approach patches for debugging"},
                    "writeDebugDots": {"type": "boolean", "description": "Preserve debug dots for debugging"},
                },
                "required": ["centerlineA", "centerlineB", "profileA", "profileB", "targetLayerRoot"]
            }
        ),

        # ── RoadCreator — Urban Design ────────────────────────────────────────
        Tool(
            name="rc_sidewalk_profile",
            description="""Compute a sidewalk + curb cross-section profile in local space.
Returns curb profile (3 points) and full profile including sidewalk (4 points).
Use to plan sidewalk dimensions before creating geometry.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "width": {"type": "number", "description": "Sidewalk width in meters (default 5.0)"},
                },
                "required": []
            }
        ),
        Tool(
            name="rc_roundabout_params",
            description="""Compute roundabout design parameters from outer diameter.
Returns standard lane width (Czech ČSN), inner island radius, apron info.
Standard lane widths are only available for diameters >= 25m. For smaller
diameters, you must supply laneWidth manually or the call will fail.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "outerDiameter": {"type": "number", "description": "Outer circle diameter in meters (14–50)"},
                    "laneWidth": {"type": "number", "description": "Manual lane width override (m). Required for diameters < 25m."},
                },
                "required": ["outerDiameter"]
            }
        ),
        Tool(
            name="rc_crossing_params",
            description="""Compute pedestrian crossing parameters — stripe count and rectangle dimensions.
Use to plan zebra crossings before creating geometry.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "crossingLength": {"type": "number", "description": "Crossing length across road (m)"},
                    "crossingWidth": {"type": "number", "description": "Crossing width along road (m, default 4.0)"},
                },
                "required": ["crossingLength"]
            }
        ),

        # ── RoadCreator — Accessories ─────────────────────────────────────────
        Tool(
            name="rc_guardrail_profile",
            description="""Get W-beam guardrail cross-section profile, post box dimensions, and bracket geometry.
Returns all profile points needed to construct guardrail geometry along a road edge.""",
            inputSchema={"type": "object", "properties": {}, "required": []}
        ),
        Tool(
            name="rc_pole_spacing",
            description="""Compute adaptive delineator pole spacing for a given curve radius.
Tighter curves get closer pole spacing per Czech standards. Returns spacing in meters.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "radius": {"type": "number", "description": "Local curve radius in meters"},
                },
                "required": ["radius"]
            }
        ),
        Tool(
            name="rc_concrete_barrier_profile",
            description="Get concrete barrier post profile points (corner coordinates of default post box).",
            inputSchema={"type": "object", "properties": {}, "required": []}
        ),
        Tool(
            name="rc_deltablok_profile",
            description="""Get DeltaBlok concrete barrier profile for a given variant.
Returns main profile, end-cap profile, and transition distance.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "variant": {
                        "type": "string",
                        "description": "DeltaBlok variant",
                        "enum": ["Blok80", "Blok100S", "Blok100", "Blok120"]
                    },
                },
                "required": []
            }
        ),

        # ── RoadCreator — Verge & Slopes ──────────────────────────────────────
        Tool(
            name="rc_verge_profile",
            description="""Compute road verge (shoulder) profile points.
Default slope is 8% outward. Returns local-space profile for sweeping along road edge.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "width": {"type": "number", "description": "Verge width in meters"},
                    "slope": {"type": "number", "description": "Outward slope as decimal (default 0.08 = 8%)"},
                },
                "required": ["width"]
            }
        ),
        Tool(
            name="rc_slope_profile",
            description="""Compute embankment/cut slope profile with optional drainage ditch.
Returns profile points for earthworks planning. Use with rc_road_3d boundary curves.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "fillRatio": {"type": "number", "description": "Fill slope ratio as 1:n (e.g. 1.75)"},
                    "cutRatio": {"type": "number", "description": "Cut slope ratio as 1:n (e.g. 1.75)"},
                    "includeDitch": {"type": "boolean", "description": "Include drainage ditch (default false)"},
                    "ditchDepth": {"type": "number", "description": "Ditch depth in meters (default 0.4)"},
                    "ditchWidth": {"type": "number", "description": "Ditch width in meters (default 0.5)"},
                },
                "required": ["fillRatio", "cutRatio"]
            }
        ),

        # ── RoadCreator — Standards ───────────────────────────────────────────
        Tool(
            name="rc_widening",
            description="""Compute lane widening for a given curve radius and road category.
Returns the extra width (m) to add per lane in curves per Czech standards.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "radius": {"type": "number", "description": "Curve radius in meters"},
                    "category": {"type": "string", "description": "Road category code (e.g. 'S 7.5')"},
                },
                "required": ["radius", "category"]
            }
        ),

        # ── RoadCreator — Terrain ─────────────────────────────────────────────
        Tool(
            name="rc_terrain_profile",
            description="""Compute a longitudinal terrain profile from chainage + elevation arrays.
Returns profile points in exaggerated profile space (default 10:1 vertical) with reference datum.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "chainages": {
                        "type": "array", "items": {"type": "number"},
                        "description": "Chainage values along route (m)"
                    },
                    "elevations": {
                        "type": "array", "items": {"type": "number"},
                        "description": "Real-world elevation at each chainage (m)"
                    },
                    "exaggeration": {"type": "number", "description": "Vertical exaggeration factor (default 10)"},
                },
                "required": ["chainages", "elevations"]
            }
        ),
        Tool(
            name="rc_contour_levels",
            description="""Classify contour levels for an elevation range.
Returns each contour elevation with its type (Main10m, Secondary5m, Minor2m).
Use to plan contour line generation from terrain.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "minElevation": {"type": "number", "description": "Minimum terrain elevation (m)"},
                    "maxElevation": {"type": "number", "description": "Maximum terrain elevation (m)"},
                    "interval": {"type": "integer", "description": "Contour interval in whole meters (default 1). Must be a positive integer."},
                },
                "required": ["minElevation", "maxElevation"]
            }
        ),

        # ── RoadCreator — Footprint ───────────────────────────────────────────
        Tool(
            name="rc_validate_profile",
            description="""Validate an OffsetProfile JSON definition.
Parses the profile, returns name, feature count, and feature details. Use before
calling RC_StoreProfile to check for errors.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "profileJson": {"type": "string", "description": "OffsetProfile JSON string"},
                },
                "required": ["profileJson"]
            }
        ),
        Tool(
            name="rc_validate_style_set",
            description="""Validate a StyleSet JSON definition.
Parses the style set, returns name, style count, and style details. Use before
calling RC_StoreStyleSet to check for errors.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "styleSetJson": {"type": "string", "description": "StyleSet JSON string"},
                },
                "required": ["styleSetJson"]
            }
        ),

        # ── RoadCreator — Parametric Geometry (document-mutating) ─────────────
        Tool(
            name="rc_sidewalk",
            description="""Create a sidewalk with raised curb along a road edge curve.
Builds curb (0.2m height) and sidewalk surface by offsetting and lofting.
Provide curveId OR road + referencePoint to identify the edge curve.
referencePoint indicates which side of the curve to place the sidewalk.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "curveId": {"type": "string", "description": "GUID of the edge curve"},
                    "road": {"type": "string", "description": "Road name (e.g. Road_1) — requires referencePoint"},
                    "referencePoint": {
                        "type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 3,
                        "description": "Point [x,y,z] indicating sidewalk side (canonical direction input)"
                    },
                    "side": {
                        "type": "string", "enum": ["left", "right"],
                        "description": "Expert override for offset direction (curveId mode only)"
                    },
                    "width": {"type": "number", "description": "Sidewalk width in meters (default 5.0, range 0.5-30.0)"},
                },
                "required": []
            }
        ),
        Tool(
            name="rc_guardrail",
            description="""Create a single-sided W-beam guardrail along a road edge.
Offsets curve, divides at 4m post spacing, places W-beam profiles and posts, lofts into beam.
Provide curveId OR road + referencePoint to identify the edge curve.
referencePoint indicates which side to offset the guardrail.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "curveId": {"type": "string", "description": "GUID of the edge curve"},
                    "road": {"type": "string", "description": "Road name — requires referencePoint"},
                    "referencePoint": {
                        "type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 3,
                        "description": "Point [x,y,z] indicating guardrail side (canonical direction input)"
                    },
                    "side": {
                        "type": "string", "enum": ["left", "right"],
                        "description": "Expert override for offset direction (curveId mode only)"
                    },
                },
                "required": []
            }
        ),
        Tool(
            name="rc_crossing",
            description="""Create a pedestrian crossing by splitting a road surface and optionally adding zebra stripes.
Single atomic operation: splits road surface at crossing location, then iteratively splits the
crossing fragment into zebra stripes. Original surface is replaced.
Returns createdIds (all fragments) and replacedIds (original surface).""",
            inputSchema={
                "type": "object",
                "properties": {
                    "surfaceId": {"type": "string", "description": "GUID of the road surface (brep or surface)"},
                    "startPoint": {
                        "type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 3,
                        "description": "Crossing start point [x,y,z] (one side of road)"
                    },
                    "endPoint": {
                        "type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 3,
                        "description": "Crossing end point [x,y,z] (other side of road)"
                    },
                    "crossingWidth": {"type": "number", "description": "Width along road direction in meters (default 4.0)"},
                    "createZebra": {"type": "boolean", "description": "Add zebra stripe splitting (default true)"},
                },
                "required": ["surfaceId", "startPoint", "endPoint"]
            }
        ),
        Tool(
            name="rc_slopes",
            description="""Generate embankment/cut slopes along both road edges with optional drainage ditches.
Sweeps slope profiles along each edge, splits against terrain for fill/cut visibility.
No referencePoint/side needed — outward direction is auto-detected from opposite edge.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "terrainId": {"type": "string", "description": "GUID of terrain (brep, surface, or mesh)"},
                    "leftEdgeId": {"type": "string", "description": "GUID of left road edge curve"},
                    "rightEdgeId": {"type": "string", "description": "GUID of right road edge curve"},
                    "fillRatio": {"type": "number", "description": "Fill slope ratio 1:n (default 1.75, range 1.0-4.0)"},
                    "cutRatio": {"type": "number", "description": "Cut slope ratio 1:n (default 1.75, range 1.0-4.0)"},
                    "includeDitch": {"type": "boolean", "description": "Add drainage ditches (default false)"},
                    "ditchDepth": {"type": "number", "description": "Ditch depth in meters (default 0.4)"},
                    "ditchWidth": {"type": "number", "description": "Ditch width in meters (default 0.5)"},
                },
                "required": ["terrainId", "leftEdgeId", "rightEdgeId"]
            }
        ),
        Tool(
            name="rc_longitudinal_profile",
            description="""Draw a 2D terrain longitudinal profile diagram for a road.
Finds the road's alignment curve via RouteDiscovery, samples terrain elevations at 2m stations,
draws baseline + terrain curve + elevation labels + km markers in profile space
(X=chainage, Y=(elevation-datum)*10). Requires 'road' name, not curveId.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "road": {"type": "string", "description": "Road name (e.g. Road_1)"},
                    "terrainId": {"type": "string", "description": "GUID of terrain (brep, surface, or mesh)"},
                    "origin": {
                        "type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 3,
                        "description": "Point [x,y,z] where to draw the 2D diagram"
                    },
                    "labelSpacing": {"type": "number", "description": "Meters between elevation labels (default 20.0)"},
                },
                "required": ["road", "terrainId", "origin"]
            }
        ),

        # ── RoadCreator — Profile Builder ─────────────────────────────────────
        Tool(
            name="rc_build_profile",
            description="""Build a canonical RoadProfileDefinition from features, semantic recipe, or observations.
Three input modes (detected by top-level keys):
- Mode A: explicit 'features' array (+ optional surfaces, elements)
- Mode B: semantic recipe with 'laneWidth' (+ optional curb, sidewalk, shoulder, median, guardrail)
- Mode C: annotated 'observations' from rc_extract_offsets (with agent-supplied role)
Returns canonical profile + validation + provenance. Input 'role' is accepted as alias for 'type'.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Profile name"},
                    "features": {"type": "array", "description": "Mode A: explicit features with id, offset, role/type, styleRef"},
                    "observations": {"type": "array", "description": "Mode C: annotated observations with curveId, side, offset, role"},
                    "laneWidth": {"type": "number", "description": "Mode B: lane width in meters"},
                    "lanesPerDirection": {"type": "integer", "description": "Mode B: lanes per direction (default 1)"},
                    "curb": {"type": "object", "description": "Mode B: { height, topWidth }"},
                    "sidewalk": {"type": "object", "description": "Mode B: { width }"},
                    "shoulder": {"type": "object", "description": "Mode B: { width }"},
                    "median": {"type": "object", "description": "Mode B: { width }"},
                    "guardrail": {"description": "Mode B: true or { postSpacing }"},
                    "surfaces": {"type": "array", "description": "Optional surface definitions for 3D"},
                    "elements": {"type": "array", "description": "Optional element definitions for 3D"},
                },
                "required": ["name"]
            }
        ),
        Tool(
            name="rc_validate_road_profile",
            description="""Validate a RoadProfileDefinition with three-tier readiness.
Returns structuralValid, footprintReady, realizationReady plus errors and warnings.
Unknown feature/surface/element types are structural errors.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "profile": {"type": "object", "description": "RoadProfileDefinition JSON"},
                },
                "required": ["profile"]
            }
        ),
        Tool(
            name="rc_store_road_profile",
            description="""Store a RoadProfileDefinition in the Rhino document under RC_RoadProfile::{name}.
Runs structural validation — rejects invalid profiles. Returns overwritten status.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "profile": {"type": "object", "description": "RoadProfileDefinition JSON"},
                },
                "required": ["profile"]
            }
        ),
        Tool(
            name="rc_project_offset_profile",
            description="""Project a RoadProfileDefinition to an OffsetProfile for 2D footprint consumers.
Drops surfaces and elements, preserves features as offset lines.
Accepts inline profile JSON or stored profile name.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "profile": {"type": "object", "description": "Inline RoadProfileDefinition JSON"},
                    "name": {"type": "string", "description": "Name of a stored road profile"},
                },
                "required": []
            }
        ),
        Tool(
            name="rc_road_footprint",
            description="""Generate 2D plan footprint curves from a centerline and an OffsetProfile.
Projects the centerline to XY (Z=0) and creates offset curves for each profile feature
with layer assignment, linetype, and print width from the active StyleSet.
This is a 2D plan linework tool — not a 3D surface generator.
Accepts stored profile/styleSet names or inline JSON.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "curveId": {"type": "string", "description": "GUID of the centerline curve"},
                    "profileName": {"type": "string", "description": "Name of a stored OffsetProfile (from rc_project_offset_profile + rc_validate_profile)"},
                    "profile": {"type": "object", "description": "Inline OffsetProfile JSON"},
                    "styleSetName": {"type": "string", "description": "Name of a stored StyleSet (optional, defaults to 'default_generic')"},
                    "styleSet": {"type": "object", "description": "Inline StyleSet JSON (optional)"},
                },
                "required": ["curveId"]
            }
        ),
        Tool(
            name="rc_resolve_edges",
            description="""Split road edge curves at intersection boundaries to produce midblock segments
with per-segment outward reference points for correct sidewalk/guardrail offset direction.

For each road's left and right edge curves, intersects with each intersection's realized
boundary curve, splits the edges, and classifies segments as midblock (outside all boundaries)
or discarded (inside an intersection).

Returns per road/side:
- midblockSegmentIds: ordered segment GUIDs
- midblockSegments: [{segmentId, midpoint, outwardReferencePoint, startPoint, endPoint, road, side}]
- discardedSegmentIds: hidden segments inside intersection boundaries
- intersectionZones: [{segmentId, intersectionId, road, side}]

Returns per intersection:
- corners: [{cornerId, curbReturnArcId, incomingRoad, incomingSide, outgoingRoad, outgoingSide, boundaryId, startPoint, endPoint, incomingBoundaryParameter, outgoingBoundaryParameter, offsetMode, outwardReferencePoint}]

The outwardReferencePoint is computed from the segment's midpoint and the closest point
on the route centerline, extended 5m outward. Use it directly as the referencePoint
parameter for rc_sidewalk and rc_guardrail calls. The corners array is the topology
handoff for rc_sidewalk_corners so corner sidewalks can use the authoritative join
contract from road_intersection_resolve rather than reconstructing corner ownership.

This is Phase 4b of the road network pipeline: after intersection resolution, before urban elements.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "roads": {
                        "type": "array",
                        "description": "Roads to process",
                        "items": {
                            "type": "object",
                            "properties": {
                                "roadName": {"type": "string", "description": "Road name (e.g. Road_1)"},
                                "routeCurveId": {"type": "string", "description": "GUID of route centerline curve (required for outward direction)"},
                                "leftEdgeCurveId": {"type": "string", "description": "GUID of left edge offset curve"},
                                "rightEdgeCurveId": {"type": "string", "description": "GUID of right edge offset curve"},
                            },
                            "required": ["roadName", "routeCurveId", "leftEdgeCurveId", "rightEdgeCurveId"]
                        }
                    },
                    "intersections": {
                        "type": "array",
                        "description": "Resolved intersections with boundary curves",
                        "items": {
                            "type": "object",
                            "properties": {
                                "intersectionId": {"type": "string", "description": "Identifier for this intersection"},
                                "boundaryId": {"type": "string", "description": "GUID of the realized boundary curve (closed)"},
                                "joinContract": {"type": "object", "description": "Optional authoritative joinContract from road_intersection_resolve; if omitted, rc_resolve_edges reads the persisted contract from the boundary object"},
                            },
                            "required": ["boundaryId"]
                        }
                    },
                },
                "required": ["roads", "intersections"]
            }
        ),
        Tool(
            name="rc_apply_intersection_ownership",
            description="""Reconcile carriageway ownership between road surfaces and resolved intersections.

For each provided road surface, splits it against the realized intersection boundary curves,
keeps only the outside fragments as road-owned approach surface, and hides the original
untrimmed road surface. The realized intersection surface remains the owner inside the
intersection boundary.

Returns per road/surface:
- hiddenOriginal: whether the original road surface was hidden
- createdIds: GUIDs of replacement road-approach surface fragments
- keptFragmentCount / discardedFragmentCount

Use this after road_intersection_resolve and before downstream surface-dependent steps
that should not see overlapping road/intersection carriageway ownership.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "roads": {
                        "type": "array",
                        "description": "Roads with one or more carriageway surface ids to reconcile",
                        "items": {
                            "type": "object",
                            "properties": {
                                "roadName": {"type": "string", "description": "Optional road name for metadata/reporting"},
                                "surfaceIds": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "GUIDs of road carriageway surfaces"
                                },
                                "surfaceId": {
                                    "type": "string",
                                    "description": "Single carriageway surface GUID (legacy convenience)"
                                },
                            }
                        }
                    },
                    "intersections": {
                        "type": "array",
                        "description": "Resolved intersections whose realized boundaries define the ownership cut",
                        "items": {
                            "type": "object",
                            "properties": {
                                "intersectionId": {"type": "string"},
                                "boundaryId": {"type": "string", "description": "GUID of the realized boundary curve"}
                            },
                            "required": ["boundaryId"]
                        }
                    }
                },
                "required": ["roads", "intersections"]
            }
        ),
        Tool(
            name="rc_apply_sidewalk_ownership",
            description="""Reconcile generated midblock sidewalk/curb surfaces against resolved intersections.

The active implementation is stable boundary-based ownership: each provided sidewalk surface is
split against the realized intersection boundary curves and only the outside fragments are kept.
The original superseded surface is hidden.

This is the sidewalk analogue of rc_apply_intersection_ownership. Use it after generating
midblock sidewalks and before combining them visually with rc_sidewalk_corners results.

Note: the richer arm-end seam-plane refinement is not the active route yet.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "surfaces": {
                        "type": "array",
                        "description": "Preferred explicit surface list. road/side fields are accepted for forward compatibility but are not required by the active boundary-based implementation.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "surfaceId": {"type": "string", "description": "GUID of sidewalk surface from rc_sidewalk"},
                                "road": {"type": "string", "description": "Optional road name, reserved for future seam-plane refinement"},
                                "side": {"type": "string", "description": "Optional road side, reserved for future seam-plane refinement"}
                            },
                            "required": ["surfaceId"]
                        }
                    },
                    "surfaceIds": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Legacy convenience: plain GUID array of sidewalk surface ids"
                    },
                    "intersections": {
                        "type": "array",
                        "description": "Resolved intersections with realized boundary ids. joinContract may be included but is not required by the active boundary-based implementation.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "intersectionId": {"type": "string"},
                                "boundaryId": {"type": "string", "description": "GUID of the realized boundary curve"},
                                "joinContract": {"type": "object", "description": "Optional joinContract from road_intersection_resolve"}
                            },
                            "required": ["boundaryId"]
                        }
                    }
                },
                "required": ["intersections"]
            }
        ),
        Tool(
            name="rc_sidewalk_corners",
            description="""Generate corner sidewalk surfaces around intersection curb return arcs.
Preferred input is the per-corner join contract returned by rc_resolve_edges:
[{cornerId, curbReturnArcId, incomingRoad, incomingSide, outgoingRoad, outgoingSide,
boundaryId, startPoint, endPoint, incomingBoundaryParameter, outgoingBoundaryParameter,
offsetMode, outwardReferencePoint}]. The endpoint extracts the true corner span from
the realized boundary when those boundary parameters are present, then applies
offsetMode directly. This avoids reconstructing a different major arc from three points.

For backward compatibility, curbReturnArcIds[] is still accepted, but that mode is less
topology-aware and may not guarantee exact joins.

Returns per corner: createdIds, curbSurfaceCount, sidewalkSurfaceCount.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "corners": {
                        "type": "array",
                        "description": "Preferred topology-aware corner contracts from rc_resolve_edges",
                        "items": {
                            "type": "object",
                            "properties": {
                                "cornerId": {"type": "string"},
                                "curbReturnArcId": {"type": "string"},
                                "incomingRoad": {"type": "string"},
                                "incomingSide": {"type": "string"},
                                "boundaryId": {"type": "string"},
                                "startPoint": {"type": "array", "items": {"type": "number"}},
                                "outgoingRoad": {"type": "string"},
                                "outgoingSide": {"type": "string"},
                                "endPoint": {"type": "array", "items": {"type": "number"}},
                                "incomingBoundaryParameter": {"type": "number"},
                                "outgoingBoundaryParameter": {"type": "number"},
                                "offsetMode": {"type": "string", "enum": ["increase_radius", "decrease_radius"]},
                                "outwardReferencePoint": {"type": "array", "items": {"type": "number"}},
                            },
                            "required": ["curbReturnArcId", "startPoint", "endPoint", "offsetMode"]
                        }
                    },
                    "curbReturnArcIds": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Legacy mode: GUIDs of curb return arc curves from road_intersection_resolve"
                    },
                    "sidewalkWidth": {"type": "number", "description": "Sidewalk width in meters (default 3.0)"},
                    "curbHeight": {"type": "number", "description": "Curb height in meters (default 0.2)"},
                    "curbTopWidth": {"type": "number", "description": "Curb top width in meters (default 0.3)"},
                }
            }
        ),
        Tool(
            name="rc_get_road_profile",
            description="""Retrieve a stored RoadProfileDefinition by name.
Returns the full profile JSON including features, surfaces, and elements.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Name of the stored road profile"},
                },
                "required": ["name"]
            }
        ),
        Tool(
            name="rc_list_road_profiles",
            description="""List all stored canonical road profile names in the current Rhino document.""",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
    ]

    return all_tools


def _record_observation(
    tool_name: str,
    arguments: dict | None,
    result: dict,
    duration_ms: float,
    injection_meta: dict | None,
) -> None:
    """Build an Observation from call context and record to MetricsStore.

    Must never raise — all exceptions are caught and logged.
    """
    try:
        from .learning.metrics_store import Observation, get_metrics_store

        args = arguments or {}
        success = result.get("success", False)
        data = result.get("data")

        # Determine knowledge_injected — either via universal injector OR
        # tools that handle knowledge internally (gh_execute_intent, rhino_execute_intent,
        # and the 4 wrapper tools which add gotchas directly).
        knowledge_injected = injection_meta is not None
        if not knowledge_injected and isinstance(data, dict):
            knowledge_injected = bool(
                data.get("knowledge_used")       # gh_execute_intent sets this
                or data.get("gotchas")            # wrapper tools add gotchas
                or data.get("knowledge_hint")     # universal injector
                or data.get("reasoning_trace")    # rhino_execute_intent uses knowledge
            )
        knowledge_hint = ""
        if isinstance(data, dict):
            knowledge_hint = data.get("knowledge_hint", "") or data.get("workflow_hint", "")

        # Extract gotchas from result data (wrapper tools add these)
        gotchas_provided = []
        if isinstance(data, dict):
            gotchas_provided = data.get("gotchas") or []

        # Correction detected
        correction_detected = False
        if isinstance(data, dict):
            correction_detected = data.get("correction_detected", False)

        # Attempt number — check failure tracker dicts
        attempt_number = 1
        intent = args.get("intent", "")
        if intent:
            normalized = intent.strip().lower()
            if normalized in _gh_intent_failures:
                attempt_number = 2

        # Phase
        phase = get_phase_tracker().current_phase().value

        # Metrics extra (stashed by gh_execute_intent) — read-only, cleaned up in call_tool()
        metrics_extra = result.get("_metrics_extra", None) or {}

        obs = Observation(
            tool_name=tool_name,
            success=success,
            duration_ms=duration_ms,
            knowledge_injected=knowledge_injected,
            knowledge_hint=knowledge_hint[:80] if knowledge_hint else "",
            gotchas_provided=gotchas_provided[:3],
            correction_detected=correction_detected,
            attempt_number=attempt_number,
            phase=phase,
            timestamp=datetime.now(timezone.utc).isoformat(),
            intent=metrics_extra.get("intent", intent),
            dspy_confidence=metrics_extra.get("dspy_confidence", 0.0),
            components_created=metrics_extra.get("components_created", 0),
            error_message=str(data)[:100] if not success and data else "",
        )

        get_metrics_store().record(obs)
    except Exception as e:
        logger.warning(f"Metrics capture skipped for {tool_name}: {e}")


# =============================================================================
# Agent system handlers
# =============================================================================

async def _handle_spawn_agent(arguments: dict) -> dict:
    """Handle the spawn_agent MCP tool call.

    Runs the agent as a background asyncio.Task so the MCP server stays
    responsive. Returns the agent_id immediately; use agent_status to poll.
    """
    import asyncio
    import uuid
    try:
        from .agent.spawn import run_task, SpawnResult
        from .agent.tool_registry import build_catalog_from_mcp_tools, save_catalog_to_cache, get_catalog_cache_path

        prompt = arguments.get("prompt", "")
        if not prompt:
            return {"success": False, "data": "Missing required 'prompt' parameter"}

        tool_groups = arguments.get("tool_groups")
        model = arguments.get("model", "")
        max_turns = arguments.get("max_turns", 30)
        max_input_tokens = arguments.get("max_input_tokens", 500_000)
        workspace_assets = arguments.get("workspace_assets")
        guardian_enabled = arguments.get("guardian_enabled", True)

        # Resolve model and/or api_base from profiles.
        # Always resolve api_base so explicit model overrides (e.g.,
        # model="openai/lmstudio-model") can reach local servers.
        api_base = None
        try:
            from .agent.model_profiles import get_models, api_base_for_model
            model_set = get_models()
            if not model:
                model = model_set.worker
            api_base = api_base_for_model(model, model_set.api_base)
        except Exception:
            pass

        # Evict oldest entries if needed
        _cleanup_agent_history()

        # Build catalog from current MCP tools, excluding agent management tools
        all_mcp_tools = await list_tools()
        catalog = build_catalog_from_mcp_tools(all_mcp_tools)
        catalog = {k: v for k, v in catalog.items() if k not in _AGENT_MANAGEMENT_TOOLS}

        # Cache for autonomous spawn (when catalog=None in run_task)
        save_catalog_to_cache(catalog, get_catalog_cache_path())

        agent_id = uuid.uuid4().hex[:8]
        _active_agents[agent_id] = {"status": "running", "prompt": prompt[:200]}

        def _on_agent_created(tid: str, agent) -> None:
            _active_agents[tid]["agent"] = agent

        async def _run_agent():
            try:
                spawn_result = await run_task(
                    prompt,
                    model=model or "",
                    api_base=api_base,
                    max_turns=max_turns,
                    max_input_tokens=max_input_tokens,
                    preload_groups=tool_groups,
                    workspace_assets=workspace_assets,
                    task_id=agent_id,
                    catalog=catalog,
                    on_agent_created=_on_agent_created,
                    guardian_enabled=guardian_enabled,
                )
                _agent_results[agent_id] = spawn_result
                _active_agents[agent_id]["status"] = spawn_result.status
            except Exception as e:
                _active_agents[agent_id]["status"] = "error"
                _active_agents[agent_id]["error"] = str(e)

        task = asyncio.create_task(_run_agent())
        _active_agents[agent_id]["task"] = task

        return {
            "success": True,
            "data": {
                "agent_id": agent_id,
                "status": "running",
                "message": "Agent spawned. Use agent_status to check progress.",
            },
        }

    except ImportError as e:
        return {"success": False, "data": f"Agent system not available: {e}"}
    except Exception as e:
        return {"success": False, "data": f"spawn_agent error: {e}"}


async def _handle_plan_and_execute(arguments: dict) -> dict:
    """Handle the plan_and_execute MCP tool call.

    Runs planner + workers as a background asyncio.Task. Returns plan_id
    immediately; use agent_status to poll for completion.
    """
    import asyncio
    import uuid
    try:
        from .agent.planner import Planner, PlannerConfig
        from .agent.tool_registry import build_catalog_from_mcp_tools, save_catalog_to_cache, get_catalog_cache_path

        request = arguments.get("request", "")
        if not request:
            return {"success": False, "data": "Missing required 'request' parameter"}

        auto_approve = arguments.get("auto_approve", True)
        planner_model = arguments.get("planner_model", "")
        worker_model = arguments.get("worker_model", "")

        config_kwargs = {}
        if planner_model:
            config_kwargs["planner_model"] = planner_model
        if worker_model:
            config_kwargs["worker_model"] = worker_model

        # Evict oldest entries if needed
        _cleanup_agent_history()

        # Build catalog, excluding agent management tools
        all_mcp_tools = await list_tools()
        catalog = build_catalog_from_mcp_tools(all_mcp_tools)
        catalog = {k: v for k, v in catalog.items() if k not in _AGENT_MANAGEMENT_TOOLS}

        # Cache for autonomous spawn (when catalog=None in run_task)
        save_catalog_to_cache(catalog, get_catalog_cache_path())

        plan_id = f"plan_{uuid.uuid4().hex[:8]}"
        _active_agents[plan_id] = {"status": "running", "prompt": request[:200]}

        def _on_worker_created(tid, agent):
            """Register child worker agents so agent_status/agent_answer can reach them."""
            _active_agents[tid] = {
                "status": "running",
                "agent": agent,
                "prompt": "",
                "parent": plan_id,
            }

        async def _run_planner():
            try:
                config = PlannerConfig.from_env(**config_kwargs)
                planner = Planner(config, catalog=catalog)
                plan_result = await planner.run(
                    request,
                    auto_approve=auto_approve,
                    on_agent_created=_on_worker_created,
                )
                _agent_results[plan_id] = plan_result
                _active_agents[plan_id]["status"] = plan_result.status

                # Transition child workers to their final status and store results
                for tr in getattr(plan_result, "task_results", []):
                    tid = getattr(tr, "task_id", None)
                    if tid and tid in _active_agents:
                        _active_agents[tid]["status"] = getattr(tr, "status", "completed")
                        _agent_results[tid] = tr
            except Exception as e:
                _active_agents[plan_id]["status"] = "error"
                _active_agents[plan_id]["error"] = str(e)

        task = asyncio.create_task(_run_planner())
        _active_agents[plan_id]["task"] = task

        return {
            "success": True,
            "data": {
                "plan_id": plan_id,
                "status": "running",
                "message": "Planner spawned. Use agent_status to check progress.",
            },
        }

    except ImportError as e:
        return {"success": False, "data": f"Agent system not available: {e}"}
    except Exception as e:
        return {"success": False, "data": f"plan_and_execute error: {e}"}


def _handle_agent_status(arguments: dict) -> dict:
    """Handle the agent_status MCP tool call."""
    agent_id = arguments.get("agent_id")

    if agent_id:
        if agent_id in _active_agents:
            info = _active_agents[agent_id]
            result_data = None
            if agent_id in _agent_results:
                r = _agent_results[agent_id]
                metrics = getattr(r, "metrics", {})
                tools_called = getattr(r, "tools_called", []) or []
                # Full tool log for orchestrator visibility (last 30 entries)
                tool_log = [
                    {"tool": t.get("tool", ""), "success": t.get("success", False), "error": t.get("error", "")}
                    for t in tools_called[-30:]
                ]
                result_data = {
                    "status": getattr(r, "status", "?"),
                    "cost_usd": metrics.get("cost_usd", 0) if isinstance(metrics, dict) else 0,
                    "summary": (getattr(r, "summary", "") or "")[:500],
                    "tools_called_count": len(tools_called),
                    "tool_log": tool_log,
                    "errors": (getattr(r, "errors", []) or [])[:5],
                    "guardian_report": getattr(r, "guardian_report", {}) or {},
                    "created_ids": getattr(r, "created_ids", []),
                }

            # Check live agent for pending question
            agent_obj = info.get("agent")
            pending_question = None
            if agent_obj is not None and hasattr(agent_obj, "pending_ask"):
                pending_question = agent_obj.pending_ask

            return {
                "success": True,
                "data": {
                    "agent_id": agent_id,
                    "status": info.get("status", "unknown"),
                    "prompt": info.get("prompt", ""),
                    "result": result_data,
                    "pending_question": pending_question,
                },
            }
        else:
            return {"success": False, "data": f"Unknown agent_id: {agent_id}"}
    else:
        agents = []
        for aid, info in _active_agents.items():
            # Check live agent for pending question
            agent_obj = info.get("agent")
            pending = None
            if agent_obj and hasattr(agent_obj, "pending_ask"):
                pending = agent_obj.pending_ask
            agents.append({
                "agent_id": aid,
                "status": info.get("status", "unknown"),
                "prompt": info.get("prompt", "")[:80],
                "parent": info.get("parent"),
                "pending_question": pending,
            })
        return {
            "success": True,
            "data": {
                "count": len(agents),
                "agents": agents,
            },
        }


def _handle_agent_abort(arguments: dict) -> dict:
    """Handle the agent_abort MCP tool call."""
    agent_id = arguments.get("agent_id", "")

    if not agent_id:
        return {"success": False, "data": "Missing required 'agent_id' parameter"}

    if agent_id not in _active_agents:
        return {"success": False, "data": f"Unknown agent_id: {agent_id}"}

    info = _active_agents[agent_id]
    agent = info.get("agent")

    if agent and hasattr(agent, "abort"):
        agent.abort()
        info["status"] = "aborting"
        return {
            "success": True,
            "data": {"agent_id": agent_id, "status": "aborting"},
        }
    else:
        info["status"] = "aborted"
        return {
            "success": True,
            "data": {
                "agent_id": agent_id,
                "status": "aborted",
                "note": "Agent reference not available; marked as aborted.",
            },
        }


def _handle_agent_answer(arguments: dict) -> dict:
    """Handle the agent_answer MCP tool call."""
    agent_id = arguments.get("agent_id", "")
    answer = arguments.get("answer", "")

    if not agent_id or not answer:
        return {"success": False, "data": "Missing required parameters (agent_id, answer)"}

    if agent_id not in _active_agents:
        return {"success": False, "data": f"Unknown agent_id: {agent_id}"}

    agent_obj = _active_agents[agent_id].get("agent")
    if not agent_obj or not hasattr(agent_obj, "resolve_ask"):
        return {"success": False, "data": "Agent does not support ask/answer"}

    if agent_obj.resolve_ask(answer):
        return {"success": True, "data": {"message": "Answer delivered", "agent_id": agent_id}}

    return {"success": False, "data": "Agent has no pending question"}


@mcp.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle tool calls."""
    import time as _time
    _t0 = _time.perf_counter()
    _tool_name = name  # Preserve original tool name — handlers may reassign `name`

    result: dict[str, Any]

    # Work on a copy to avoid mutating caller's dict (important for agent retries)
    arguments = dict(arguments) if arguments else {}
    # Extract port parameter if present (for multi-instance support)
    port = arguments.pop("port", None) if arguments else None

    match name:
        case "rhino_instances":
            instances = discover_instances()
            if not instances:
                result = {"success": True, "data": {"count": 0, "instances": [], "message": "No active Rhino instances found. Make sure Rhino is running with the RookNative or Rook plugin loaded."}}
            else:
                # Verify each instance is actually responding
                verified = []
                for inst in instances:
                    try:
                        async with httpx.AsyncClient(timeout=2.0) as client:
                            inst_host = inst.get("host", "127.0.0.1")
                            resp = await client.get(f"http://{inst_host}:{inst['port']}/ping")
                            if resp.status_code == 200:
                                verified.append(inst)
                    except:
                        pass
                result = {"success": True, "data": {"count": len(verified), "instances": verified}}

        case "rhino_launch":
            import subprocess as _sp
            import os as _os

            timeout = arguments.get("timeout", 120) if arguments else 120
            # First check if already running
            try:
                ping_result = await call_rhino("/ping")
                if ping_result.get("success"):
                    result = {"success": True, "data": {"status": "already_running", "message": "Rhino is already running"}}
                else:
                    raise Exception("ping failed")
            except Exception:
                # Not running — launch it
                rhino_exe = "C:/Program Files/Rhino 8/System/Rhino.exe"
                if not _os.path.exists(rhino_exe):
                    result = {"success": False, "data": f"Rhino not found at {rhino_exe}"}
                else:
                    _sp.Popen([rhino_exe], creationflags=_sp.DETACHED_PROCESS)
                    # Poll until native plugin responds
                    elapsed = 0
                    started = False
                    while elapsed < timeout:
                        await asyncio.sleep(2)
                        elapsed += 2
                        try:
                            ping_result = await call_rhino("/ping")
                            if ping_result.get("success"):
                                started = True
                                break
                        except Exception:
                            continue
                    if started:
                        result = {"success": True, "data": {"status": "launched", "message": f"Rhino started in {elapsed}s"}}
                    else:
                        result = {"success": False, "data": f"Rhino failed to start within {timeout}s"}

        case "rhino_ping":
            result = await call_rhino("/ping", port=port)

        case "rhino_document":
            result = await call_rhino("/document", port=port)

        case "rhino_layers":
            result = await call_rhino("/layers")

        case "rhino_objects":
            result = await call_rhino("/objects", "GET", arguments if arguments else None)

        case "rhino_selection":
            result = await call_rhino("/selection")

        case "rhino_select":
            result = await call_rhino("/select", "POST", arguments)

        case "rhino_geometry":
            result = await call_rhino("/geometry", "GET", arguments)

        case "rhino_execute":
            code = arguments.get("code", "") if arguments else ""
            blocking_call = _find_blocking_rhinoscriptsyntax_call(code) if isinstance(code, str) else None
            if blocking_call:
                call_name, line_no = blocking_call
                result = {
                    "success": False,
                    "data": (
                        f"Interactive Rhino input call {call_name} detected on line {line_no}. "
                        "rhino_execute must not invoke blocking rhinoscriptsyntax Get* prompts. "
                        "Use the prompt tools or rhino_command_interactive_* flow instead. "
                        "The script was NOT sent to Rhino."
                    ),
                }
            else:
                result = await call_rhino("/execute", "POST", arguments)

        case "rhino_command":
            preflight_error = _preflight_rhino_command(arguments.get("command") if arguments else None)
            if preflight_error is not None:
                result = preflight_error
            else:
                result = await call_rhino("/command", "POST", arguments)

        case "rhino_viewport":
            result = await call_rhino("/viewport", "POST", arguments if arguments else {})

        case "rhino_views":
            result = await call_rhino("/views", "GET", None)

        case "rhino_views_restore":
            result = await call_rhino("/views/restore", "POST", arguments)

        case "rhino_views_save":
            result = await call_rhino("/views/save", "POST", arguments)

        case "rhino_display_modes":
            result = await call_rhino("/display-modes", "GET", None)

        case "rhino_display_mode_set":
            result = await call_rhino("/display-mode", "POST", arguments)

        case "rhino_create":
            result = await call_rhino("/create", "POST", arguments)

        # Geometry operations
        case "rhino_delete":
            result = await call_rhino("/delete", "POST", arguments)

        case "rhino_transform":
            result = await call_rhino("/transform", "POST", arguments)

        case "rhino_copy":
            result = await call_rhino("/copy", "POST", arguments)

        # Layer management
        case "rhino_layer_create":
            result = await call_rhino("/layers", "POST", arguments)

        case "rhino_layer_create_batch":
            result = await call_rhino("/layers/batch", "POST", arguments)

        case "rhino_layer_delete":
            result = await call_rhino("/layers", "DELETE", arguments)

        case "rhino_layer_visibility":
            result = await call_rhino("/layers/visibility", "POST", arguments)

        case "rhino_layer_lock":
            result = await call_rhino("/layers/lock", "POST", arguments)

        case "rhino_layer_current":
            result = await call_rhino("/layers/current", "POST", arguments)

        case "rhino_layer_set_properties":
            result = await call_rhino("/layers/properties", "POST", arguments)

        case "rhino_layer_rename":
            result = await call_rhino("/layers/rename", "POST", arguments)

        case "rhino_layer_move_objects":
            result = await call_rhino("/layers/move-objects", "POST", arguments)

        case "rhino_layer_merge":
            result = await call_rhino("/layers/merge", "POST", arguments)

        case "rhino_layer_dependencies":
            result = await call_rhino("/layers/dependencies", "GET", arguments)

        # Advanced selection
        case "rhino_select_by_type":
            result = await call_rhino("/select", "POST", arguments)

        case "rhino_select_by_name":
            result = await call_rhino("/select", "POST", arguments)

        case "rhino_select_all":
            result = await call_rhino("/select", "POST", {"all": True})

        case "rhino_select_none":
            result = await call_rhino("/select", "POST", {"none": True})

        case "rhino_select_invert":
            result = await call_rhino("/select", "POST", {"invert": True})

        case "rhino_deselect":
            # Convert ids to deselectIds for the handler
            result = await call_rhino("/select", "POST", {"deselectIds": arguments.get("ids", []), "clear": False})

        # Measurement/analysis tools
        case "rhino_measure_distance":
            result = await call_rhino("/measure/distance", "POST", arguments)

        case "rhino_measure_area":
            result = await call_rhino("/measure/area", "POST", arguments)

        case "rhino_measure_volume":
            result = await call_rhino("/measure/volume", "POST", arguments)

        case "rhino_measure_length":
            result = await call_rhino("/measure/length", "POST", arguments)

        case "rhino_measure_bbox":
            result = await call_rhino("/measure/bbox", "POST", arguments)

        case "rhino_measure_centroid":
            result = await call_rhino("/measure/centroid", "POST", arguments)

        # Boolean operations
        case "rhino_boolean":
            # Handle difference operation with targetId/toolIds -> ids conversion
            args = dict(arguments)
            if args.get("operation") == "difference" and "targetId" in args:
                # Convert targetId + toolIds to ids array (target first, then tools)
                target_id = args.pop("targetId")
                tool_ids = args.pop("toolIds", [])
                args["ids"] = [target_id] + tool_ids
            result = await call_rhino("/boolean", "POST", args)

        # Surface creation (via /create endpoint)
        case "rhino_loft":
            args = dict(arguments)
            args["type"] = "LOFT"
            result = await call_rhino("/create", "POST", args)

        case "rhino_sweep":
            args = dict(arguments)
            args["type"] = "SWEEP1"
            result = await call_rhino("/create", "POST", args)

        case "rhino_extrude":
            args = dict(arguments)
            args["type"] = "EXTRUDE"
            # Multiply direction by distance to get full extrusion vector
            if "direction" in args and "distance" in args:
                direction = args["direction"]
                distance = args["distance"]
                if isinstance(direction, list) and len(direction) == 3:
                    args["direction"] = [d * distance for d in direction]
                del args["distance"]  # Remove distance since it's now baked into direction
            result = await call_rhino("/create", "POST", args)

        # Import/Export
        case "rhino_import":
            result = await call_rhino("/import", "POST", arguments)

        case "rhino_export":
            result = await call_rhino("/export", "POST", arguments)

        # Groups
        case "rhino_group":
            result = await call_rhino("/group", "POST", arguments)

        # Blocks
        case "rhino_blocks":
            result = await call_rhino("/blocks", "GET")

        case "rhino_block_create":
            result = await call_rhino("/block/create", "POST", arguments)

        case "rhino_block_insert":
            result = await call_rhino("/block/insert", "POST", arguments)

        case "rhino_block_explode":
            result = await call_rhino("/block/explode", "POST", arguments)

        case "rhino_block_delete":
            result = await call_rhino("/block", "DELETE", arguments)

        # Block Modification Operations (Phase 1)
        case "rhino_block_rename":
            result = await call_rhino("/block/rename", "POST", arguments)

        case "rhino_block_description":
            result = await call_rhino("/block/description", "POST", arguments)

        case "rhino_block_info":
            name = arguments.get("name")
            if not name:
                result = {"success": False, "data": "Missing required parameter 'name'"}
            else:
                result = await call_rhino("/block/info", "POST", {"name": name})

        # Block Geometry Operations (Phase 2)
        case "rhino_block_add_objects":
            result = await call_rhino("/block/add-objects", "POST", arguments)

        case "rhino_block_remove_objects":
            result = await call_rhino("/block/remove-objects", "POST", arguments)

        case "rhino_block_replace_geometry":
            result = await call_rhino("/block/replace-geometry", "POST", arguments)

        case "rhino_block_replace_object_geometry":
            result = await call_rhino("/block/replace-object-geometry", "POST", arguments)

        case "rhino_block_transform_object":
            result = await call_rhino("/block/transform-object", "POST", arguments)

        case "rhino_block_set_layers":
            result = await call_rhino("/block/set-layers", "POST", arguments)

        case "rhino_block_set_materials":
            result = await call_rhino("/block/set-materials", "POST", arguments)

        # Block Instance Properties (Phase 6)
        case "rhino_block_set_instance_properties":
            result = await call_rhino("/block/set-instance-properties", "POST", arguments)

        case "rhino_block_set_instance_visibility":
            result = await call_rhino("/block/set-instance-visibility", "POST", arguments)

        # Block Instance Transforms (Phase 7)
        case "rhino_block_transform_instance":
            result = await call_rhino("/block/transform-instance", "POST", arguments)

        case "rhino_block_array_instances":
            result = await call_rhino("/block/array-instances", "POST", arguments)

        # Block Object Properties (Phase 8)
        case "rhino_block_set_object_colors":
            result = await call_rhino("/block/set-object-colors", "POST", arguments)

        case "rhino_block_set_object_names":
            result = await call_rhino("/block/set-object-names", "POST", arguments)

        case "rhino_block_set_object_user_strings":
            result = await call_rhino("/block/set-object-user-strings", "POST", arguments)

        # Block Definition Metadata (Phase 9)
        case "rhino_block_user_strings":
            result = await call_rhino("/block/user-strings", "POST", arguments)

        # Enhanced Block Queries (Phase 10)
        case "rhino_block_find_instances":
            result = await call_rhino("/block/find-instances", "POST", arguments)

        case "rhino_block_objects_detailed":
            name = arguments.get("name")
            if not name:
                result = {"success": False, "data": "Missing required parameter 'name'"}
            else:
                payload = {"name": name}
                if arguments.get("geometry"):
                    payload["geometry"] = True
                result = await call_rhino("/block/objects-detailed", "POST", payload)

        # Block Instance Operations (Phase 3)
        case "rhino_block_instances":
            name = arguments.get("name")
            depth = arguments.get("depth", 0)
            if not name:
                result = {"success": False, "data": "Missing required parameter 'name'"}
            else:
                result = await call_rhino("/block/instances", "POST", {"name": name, "depth": depth})

        case "rhino_block_replace_instance":
            result = await call_rhino("/block/replace-instance", "POST", arguments)

        case "rhino_block_reset_scale":
            result = await call_rhino("/block/reset-scale", "POST", arguments)

        # Linked Block Operations (Phase 4)
        case "rhino_block_link":
            result = await call_rhino("/block/link", "POST", arguments)

        case "rhino_block_refresh":
            result = await call_rhino("/block/refresh", "POST", arguments)

        case "rhino_block_unlink":
            result = await call_rhino("/block/unlink", "POST", arguments)

        # Block Utility Operations (Phase 5)
        case "rhino_block_purge":
            result = await call_rhino("/block/purge", "POST", arguments if arguments else {})

        case "rhino_block_duplicate":
            result = await call_rhino("/block/duplicate", "POST", arguments)

        case "rhino_block_nested":
            name = arguments.get("name")
            if not name:
                result = {"success": False, "data": "Missing required parameter 'name'"}
            else:
                result = await call_rhino("/block/nested", "POST", {"name": name})

        # Block Deduplication (Phase 6)
        case "rhino_block_compare":
            result = await call_rhino("/block/compare", "POST", arguments)

        case "rhino_block_merge":
            result = await call_rhino("/block/merge", "POST", arguments)

        case "rhino_block_rebase":
            result = await call_rhino("/block/rebase", "POST", arguments)

        case "rhino_block_rebase_recursive":
            result = await call_rhino("/block/rebase-recursive", "POST", arguments)

        # Annotations (via /create endpoint)
        case "rhino_text":
            args = dict(arguments)
            args["type"] = "TEXT"
            result = await call_rhino("/create", "POST", args)

        case "rhino_dimension":
            result = await call_rhino("/create", "POST", arguments)

        # Phase 4: Consolidated action-based tools
        case "rhino_document_ops":
            action = arguments.get("action")
            if action == "open":
                path = arguments.get("path")
                if not path:
                    result = {"success": False, "data": "Missing required parameter 'path' for open action"}
                else:
                    result = await call_rhino("/document/open", "POST", {"path": path})
            elif action == "undo":
                result = await call_rhino("/undo", "POST", {})
            elif action == "redo":
                result = await call_rhino("/redo", "POST", {})
            elif action == "save":
                path = arguments.get("path")
                if not path:
                    result = {"success": False, "data": "Missing required parameter 'path' for save action"}
                else:
                    payload = {"path": path}
                    if arguments.get("small"):
                        payload["small"] = True
                    result = await call_rhino("/document/save", "POST", payload)
            elif action == "new":
                result = await call_rhino("/document/new", "POST", {})
            elif action == "set_units":
                units = arguments.get("units")
                if not units:
                    result = {"success": False, "data": "Missing required parameter 'units' for set_units action"}
                else:
                    result = await call_rhino("/document/units", "POST", {"units": units})
            else:
                result = {"success": False, "data": f"Invalid action '{action}'. Valid actions: open, new, save, undo, redo, set_units"}

        case "rhino_curve_ops":
            action = arguments.get("action")
            if action == "join":
                ids = arguments.get("ids")
                if not ids:
                    result = {"success": False, "data": "Missing required parameter 'ids' for join action"}
                else:
                    result = await call_rhino("/curve/join", "POST", {"ids": ids})
            elif action == "explode":
                curve_id = arguments.get("id")
                if not curve_id:
                    result = {"success": False, "data": "Missing required parameter 'id' for explode action"}
                else:
                    result = await call_rhino("/curve/explode", "POST", {"id": curve_id})
            elif action == "divide":
                curve_id = arguments.get("id")
                count = arguments.get("count")
                if not curve_id or not count:
                    result = {"success": False, "data": "Missing required parameters 'id' and 'count' for divide action"}
                else:
                    result = await call_rhino("/curve/divide", "POST", {"id": curve_id, "count": count})
            elif action == "extend":
                curve_id = arguments.get("id")
                end = arguments.get("end")
                length = arguments.get("length")
                if curve_id is None or end is None or length is None:
                    result = {"success": False, "data": "Missing required parameters 'id', 'end', and 'length' for extend action"}
                else:
                    # Convert end from integer (0/1) to string ("start"/"end") for C# handler
                    end_str = "start" if end == 0 else "end"
                    result = await call_rhino("/curve/extend", "POST", {"id": curve_id, "end": end_str, "length": length})
            elif action == "trim":
                curve_id = arguments.get("id")
                parameter = arguments.get("parameter")
                point = arguments.get("point")
                if not curve_id or (parameter is None and not point):
                    result = {"success": False, "data": "Missing required parameters for trim action (need 'id' and either 'parameter' or 'point')"}
                else:
                    payload = {"id": curve_id}
                    if parameter is not None:
                        payload["parameter"] = parameter
                    if point:
                        payload["point"] = point
                    result = await call_rhino("/curve/trim", "POST", payload)
            elif action == "split":
                curve_id = arguments.get("id")
                parameter = arguments.get("parameter")
                if not curve_id or parameter is None:
                    result = {"success": False, "data": "Missing required parameters 'id' and 'parameter' for split action"}
                else:
                    result = await call_rhino("/curve/split", "POST", {"id": curve_id, "parameter": parameter})
            elif action == "rebuild":
                curve_id = arguments.get("id")
                if not curve_id:
                    result = {"success": False, "data": "Missing required parameter 'id' for rebuild action"}
                else:
                    payload = {"id": curve_id}
                    if "degree" in arguments:
                        payload["degree"] = arguments["degree"]
                    if "pointCount" in arguments:
                        payload["pointCount"] = arguments["pointCount"]
                    result = await call_rhino("/curve/rebuild", "POST", payload)
            elif action == "fillet":
                id1 = arguments.get("id1")
                id2 = arguments.get("id2")
                radius = arguments.get("radius")
                if not id1 or not id2 or radius is None:
                    result = {"success": False, "data": "Missing required parameters 'id1', 'id2', and 'radius' for fillet action"}
                else:
                    result = await call_rhino("/curve/fillet", "POST", {"id1": id1, "id2": id2, "radius": radius})
            else:
                result = {"success": False, "data": f"Invalid action '{action}'. Valid actions: join, explode, divide, extend, trim, split, rebuild, fillet"}

        case "rhino_material_ops":
            action = arguments.get("action")
            if action == "list":
                result = await call_rhino("/materials", "GET", {})
            elif action == "create":
                name = arguments.get("name")
                color = arguments.get("color")
                if not name or not color:
                    result = {"success": False, "data": "Missing required parameters 'name' and 'color' for create action"}
                else:
                    payload = {"name": name, "color": color}
                    # Optional parameters
                    if "shininess" in arguments:
                        payload["shininess"] = arguments["shininess"]
                    if "transparency" in arguments:
                        payload["transparency"] = arguments["transparency"]
                    if "reflectivity" in arguments:
                        payload["reflectivity"] = arguments["reflectivity"]
                    result = await call_rhino("/materials", "POST", payload)
            elif action == "delete":
                name = arguments.get("name")
                if not name:
                    result = {"success": False, "data": "Missing required parameter 'name' for delete action"}
                else:
                    result = await call_rhino("/materials", "DELETE", {"name": name})
            elif action == "assign":
                name = arguments.get("name")
                obj_id = arguments.get("id")
                obj_ids = arguments.get("ids")
                if not name or (not obj_id and not obj_ids):
                    result = {"success": False, "data": "Missing required parameters for assign action (need 'name' and either 'id' or 'ids')"}
                else:
                    payload = {"material": name}
                    if obj_id:
                        payload["id"] = obj_id
                    if obj_ids:
                        payload["ids"] = obj_ids
                    result = await call_rhino("/materials/assign", "POST", payload)
            else:
                result = {"success": False, "data": f"Invalid action '{action}'. Valid actions: list, create, delete, assign"}

        # ========================================
        # Phase A: Core Operations (14 handlers)
        # ========================================

        # Intersection operations
        case "rhino_intersect_curves":
            # Map curveId1/curveId2 to id1/id2
            args = dict(arguments)
            if "curveId1" in args:
                args["id1"] = args.pop("curveId1")
            if "curveId2" in args:
                args["id2"] = args.pop("curveId2")
            result = await call_rhino("/intersect/curves", "POST", args)

        case "rhino_intersect_curve_surface":
            result = await call_rhino("/intersect/curve-surface", "POST", arguments)

        case "rhino_intersect_curve_brep":
            result = await call_rhino("/intersect/curve-brep", "POST", arguments)

        case "rhino_intersect_breps":
            # Map brepId1/brepId2 to id1/id2
            args = dict(arguments)
            if "brepId1" in args:
                args["id1"] = args.pop("brepId1")
            if "brepId2" in args:
                args["id2"] = args.pop("brepId2")
            result = await call_rhino("/intersect/breps", "POST", args)

        case "rhino_intersect_plane":
            # Convert planeOrigin/planeNormal to nested plane object
            args = dict(arguments)
            if "planeOrigin" in args and "planeNormal" in args:
                args["plane"] = {
                    "origin": args.pop("planeOrigin"),
                    "normal": args.pop("planeNormal")
                }
            result = await call_rhino("/intersect/plane", "POST", args)

        # Project/Pull operations
        case "rhino_project_curve":
            result = await call_rhino("/curve/project", "POST", arguments)

        case "rhino_pull_curve":
            result = await call_rhino("/curve/pull", "POST", arguments)

        case "rhino_offset_curve":
            result = await call_rhino("/curve/offset", "POST", arguments)

        case "rhino_offset_curve_on_surface":
            result = await call_rhino("/curve/offset-on-surface", "POST", arguments)

        # Offset Brep
        case "rhino_offset_brep":
            result = await call_rhino("/offset/brep", "POST", arguments)

        # Split/Trim operations
        case "rhino_split_brep":
            # Convert planeOrigin/planeNormal to nested plane object
            args = dict(arguments)
            if "planeOrigin" in args and "planeNormal" in args:
                args["plane"] = {
                    "origin": args.pop("planeOrigin"),
                    "normal": args.pop("planeNormal")
                }
            result = await call_rhino("/split/brep", "POST", args)

        case "rhino_trim_brep":
            # Convert planeOrigin/planeNormal to nested plane object
            args = dict(arguments)
            if "planeOrigin" in args and "planeNormal" in args:
                args["plane"] = {
                    "origin": args.pop("planeOrigin"),
                    "normal": args.pop("planeNormal")
                }
            # Convert keepSide from string to int
            if "keepSide" in args:
                keep_side = args["keepSide"]
                if keep_side == "positive":
                    args["keepSide"] = 0
                elif keep_side == "negative":
                    args["keepSide"] = 1
            result = await call_rhino("/trim/brep", "POST", args)

        case "rhino_split_face":
            result = await call_rhino("/split/face", "POST", arguments)

        # SubD tools
        case "rhino_subd_box":
            result = await call_rhino("/subd/box", "POST", arguments)

        case "rhino_subd_sphere":
            result = await call_rhino("/subd/sphere", "POST", arguments)

        case "rhino_subd_cylinder":
            result = await call_rhino("/subd/cylinder", "POST", arguments)

        case "rhino_subd_from_mesh":
            result = await call_rhino("/subd/from-mesh", "POST", arguments)

        case "rhino_subd_from_surface":
            result = await call_rhino("/subd/from-surface", "POST", arguments)

        case "rhino_subd_subdivide":
            result = await call_rhino("/subd/subdivide", "POST", arguments)

        case "rhino_subd_crease":
            result = await call_rhino("/subd/crease", "POST", arguments)

        case "rhino_subd_to_brep":
            args = dict(arguments)
            if "id" in args and "subdId" not in args:
                args["subdId"] = args.pop("id")
            result = await call_rhino("/subd/to-brep", "POST", args)

        case "rhino_subd_to_mesh":
            result = await call_rhino("/subd/to-mesh", "POST", arguments)

        # Mesh tools - Creation
        case "rhino_mesh_from_brep":
            result = await call_rhino("/mesh/from-brep", "POST", arguments)

        case "rhino_mesh_box":
            result = await call_rhino("/mesh/box", "POST", arguments)

        case "rhino_mesh_sphere":
            result = await call_rhino("/mesh/sphere", "POST", arguments)

        case "rhino_mesh_cylinder":
            result = await call_rhino("/mesh/cylinder", "POST", arguments)

        case "rhino_mesh_cone":
            result = await call_rhino("/mesh/cone", "POST", arguments)

        # Mesh tools - Editing
        case "rhino_mesh_boolean":
            result = await call_rhino("/mesh/boolean", "POST", arguments)

        case "rhino_mesh_reduce":
            result = await call_rhino("/mesh/reduce", "POST", arguments)

        case "rhino_quad_remesh":
            result = await call_rhino("/mesh/quad-remesh", "POST", arguments)

        case "rhino_mesh_repair":
            result = await call_rhino("/mesh/repair", "POST", arguments)

        case "rhino_mesh_smooth":
            result = await call_rhino("/mesh/smooth", "POST", arguments)

        case "rhino_mesh_weld":
            result = await call_rhino("/mesh/weld", "POST", arguments)

        case "rhino_mesh_unweld":
            result = await call_rhino("/mesh/unweld", "POST", arguments)

        # Analysis tools - Curvature
        case "rhino_curvature_curve":
            result = await call_rhino("/analysis/curvature-curve", "POST", arguments)

        case "rhino_curvature_surface":
            result = await call_rhino("/analysis/curvature-surface", "POST", arguments)

        case "rhino_draft_angle":
            result = await call_rhino("/analysis/draft-angle", "POST", arguments)

        # Analysis tools - Point/Curve Evaluation
        case "rhino_closest_point":
            result = await call_rhino("/analysis/closest-point", "POST", arguments)

        case "rhino_curve_point_at":
            result = await call_rhino("/analysis/curve-point-at", "POST", arguments)

        case "rhino_curve_tangent":
            result = await call_rhino("/analysis/curve-tangent", "POST", arguments)

        case "rhino_curve_frame":
            result = await call_rhino("/analysis/curve-frame", "POST", arguments)

        case "rhino_surface_normal":
            result = await call_rhino("/analysis/surface-normal", "POST", arguments)

        # Analysis tools - Topology Queries
        case "rhino_brep_edges":
            result = await call_rhino("/analysis/brep-edges", "POST", arguments)

        case "rhino_brep_faces":
            result = await call_rhino("/analysis/brep-faces", "POST", arguments)

        case "rhino_brep_vertices":
            result = await call_rhino("/analysis/brep-vertices", "POST", arguments)

        case "rhino_is_closed":
            result = await call_rhino("/analysis/is-closed", "POST", arguments)

        case "rhino_is_valid":
            result = await call_rhino("/analysis/is-valid", "POST", arguments)

        # Knowledge Graph tools
        case "knowledge_query":
            intent = arguments.get("intent")
            tool = arguments.get("tool")
            depth = arguments.get("depth")  # None means default to "context"
            context_name = arguments.get("context_name")
            try:
                # Use tiered query system - Claude decides the depth
                knowledge_result = query_knowledge_tiered(
                    intent=intent,
                    tool=tool,
                    depth=depth,
                    context_name=context_name,
                )
                result = {"success": True, "data": knowledge_result}
            except Exception as e:
                result = {"success": False, "data": f"Knowledge query failed: {str(e)}"}

        case "knowledge_record":
            intent = arguments.get("intent")
            action = arguments.get("action")
            outcome = arguments.get("outcome")
            correction_of = arguments.get("correction_of")

            if not intent or not action or not outcome:
                result = {"success": False, "data": "Missing required parameters: intent, action, outcome"}
            else:
                try:
                    record_result = record_knowledge(
                        intent=intent,
                        action=action,
                        outcome=outcome,
                        correction_of=correction_of
                    )
                    result = {"success": True, "data": record_result}
                except Exception as e:
                    result = {"success": False, "data": f"Knowledge record failed: {str(e)}"}

        case "parse_command":
            command_string = arguments.get("command_string")
            mode_hint = arguments.get("mode")

            if not command_string:
                result = {"success": False, "data": "Missing required parameter: command_string"}
            else:
                try:
                    parsed = command_learner.knowledge_store.parse_command_string(
                        command_string=command_string,
                        mode=mode_hint
                    )
                    if parsed:
                        result = {"success": True, "data": parsed}
                    else:
                        result = {"success": False, "data": "Could not parse command string"}
                except Exception as e:
                    result = {"success": False, "data": f"Parse failed: {str(e)}"}

        # Command Learning tools
        case "rhino_command_learn":
            result = {
                "success": False,
                "data": (
                    "rhino_command_learn is deprecated and disabled. "
                    "Use rhino_learn_interactive instead."
                ),
            }

        case "rhino_command_observations":
            command = arguments.get("command")
            try:
                if command:
                    # Get observations for specific command
                    observations = observation_store.get_by_command(command)
                    result = {
                        "success": True,
                        "data": {
                            "command": command,
                            "observation_count": len(observations),
                            "observations": [obs.to_dict() for obs in observations[-10:]]  # Last 10
                        }
                    }
                else:
                    # Get stats for all commands
                    stats = observation_store.get_stats()
                    result = {"success": True, "data": stats}
            except Exception as e:
                result = {"success": False, "data": f"Query failed: {str(e)}"}

        case "rhino_command_experiment":
            command_name = arguments.get("command")
            variations = arguments.get("variations", [])
            intent = arguments.get("intent")

            if not command_name or not variations:
                result = {"success": False, "data": "Missing required parameters: command, variations"}
            else:
                try:
                    rhino_url = get_rhino_host()
                    if rhino_url is None:
                        result = {"success": False, "data": "No Rhino instance discovered. Ensure Rhino is running with RookNative loaded."}
                    else:
                        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                            observer = CommandObserver(
                                http_client=client,
                                base_url=rhino_url,
                                store=observation_store
                            )
                            observations = await observer.experiment_with_command(
                                command_name=command_name,
                                variations=variations,
                                intent=intent
                            )
                            # Summarize results
                            summaries = []
                            for obs in observations:
                                summaries.append({
                                    "syntax": obs.full_syntax,
                                    "success": obs.success,
                                    "objects_created": obs.result.objects_created,
                                    "dialogue_steps": len(obs.dialogue),
                                    "error": obs.result.error_message
                                })

                            successful = sum(1 for obs in observations if obs.success)
                            result = {
                                "success": True,
                                "data": {
                                    "command": command_name,
                                    "variations_tried": len(variations),
                                    "successful": successful,
                                    "failed": len(variations) - successful,
                                    "results": summaries
                                }
                            }
                except Exception as e:
                    result = {"success": False, "data": f"Experiment failed: {str(e)}"}

        case "rhino_command_queue":
            priority_filter = arguments.get("priority")
            try:
                queue = command_learner.get_learning_queue()
                if priority_filter:
                    queue = [q for q in queue if q["priority"] == priority_filter]
                result = {
                    "success": True,
                    "data": {
                        "total_commands": len(queue),
                        "queue": queue
                    }
                }
            except Exception as e:
                result = {"success": False, "data": f"Queue failed: {str(e)}"}

        case "rhino_command_consolidate":
            command = arguments.get("command")
            try:
                if command:
                    # Consolidate single command
                    pattern = command_learner.consolidate_command(command)
                    if pattern:
                        # Auto-regenerate tiered knowledge for just this command (fast)
                        tiering_result = _regenerate_tiered_knowledge(command=command)
                        result = {
                            "success": True,
                            "data": {
                                "command": command,
                                "pattern": pattern.to_dict(),
                                "tiering": tiering_result
                            }
                        }
                    else:
                        result = {"success": False, "data": f"No observations found for {command}"}
                else:
                    # Consolidate all commands with observations
                    all_commands = observation_store.get_all_commands()
                    consolidated = []
                    for cmd in all_commands:
                        pattern = command_learner.consolidate_command(cmd)
                        if pattern:
                            consolidated.append({
                                "command": cmd,
                                "modes": list(pattern.modes.keys()),
                                "observations": pattern.observations_count
                            })
                    # Auto-regenerate tiered knowledge to keep it in sync
                    tiering_result = _regenerate_tiered_knowledge()
                    result = {
                        "success": True,
                        "data": {
                            "consolidated_count": len(consolidated),
                            "commands": consolidated,
                            "tiering": tiering_result
                        }
                    }
            except Exception as e:
                result = {"success": False, "data": f"Consolidation failed: {str(e)}"}

        case "rhino_command_select":
            intent = arguments.get("intent")
            if not intent:
                result = {"success": False, "data": "Missing required parameter: intent"}
            else:
                try:
                    selection = command_learner.select_command(intent)
                    result = {"success": True, "data": selection}
                except Exception as e:
                    result = {"success": False, "data": f"Selection failed: {str(e)}"}

        case "rhino_command_knowledge":
            command = arguments.get("command")
            try:
                if command:
                    pattern = command_learner.knowledge_store.get(command)
                    if pattern:
                        result = {"success": True, "data": pattern.to_dict()}
                    else:
                        result = {"success": False, "data": f"No knowledge found for {command}"}
                else:
                    all_patterns = command_learner.knowledge_store.get_all()
                    result = {
                        "success": True,
                        "data": {
                            "total_commands": len(all_patterns),
                            "commands": {
                                name: {
                                    "description": p.description,
                                    "modes": list(p.modes.keys()),
                                    "observations_count": p.observations_count
                                }
                                for name, p in all_patterns.items()
                            }
                        }
                    }
            except Exception as e:
                result = {"success": False, "data": f"Knowledge query failed: {str(e)}"}

        case "rhino_command_knowledge_reload":
            try:
                knowledge_count = command_learner.knowledge_store.reload()
                obs_count = command_learner.observation_store.reload()
                result = {
                    "success": True,
                    "data": {
                        "message": f"Reloaded {knowledge_count} command patterns and {obs_count} observations from disk",
                        "patterns_loaded": knowledge_count,
                        "observations_loaded": obs_count
                    }
                }
            except Exception as e:
                result = {"success": False, "data": f"Reload failed: {str(e)}"}

        # Hybrid Investigator handlers (learning and execution)
        case "rhino_learn_next":
            phase = arguments.get("phase")
            category = arguments.get("category")
            try:
                from .learning.hybrid_investigator import HybridInvestigator
                from .learning.graph import KnowledgeGraphV2

                # Create investigator WITH knowledge graph for meta-learning loop
                kg = KnowledgeGraphV2()
                investigator = HybridInvestigator(kg=kg)

                # Create dialogue executor using CommandObserver
                async def dialogue_executor(command: str, inputs: list[str]) -> dict:
                    """Execute command dialogue using CommandObserver."""
                    from .learning.command_observer import CommandObserver

                    async with httpx.AsyncClient() as client:
                        observer = CommandObserver(client, store=observation_store)

                        # Execute using the observer which handles dialogue properly
                        observation = await observer.execute_interactive(
                            command=command,
                            inputs=inputs,
                        )

                        return {
                            "success": observation.success and observation.result.objects_created > 0,
                            "dialogue_steps": len(observation.dialogue),
                            "objects_created": observation.result.objects_created,
                            "error": observation.result.error_message,
                            "dialogue": [
                                {
                                    "prompt": step.prompt,
                                    "input": step.input_value,
                                    "options": step.options_available,
                                }
                                for step in observation.dialogue
                            ]
                        }

                # Learn next command
                learn_result = await investigator.learn_next_from_roadmap(
                    dialogue_executor=dialogue_executor,
                    phase=phase,
                    category=category
                )

                if learn_result is None:
                    result = {
                        "success": True,
                        "data": {
                            "message": "All commands in roadmap have been learned!",
                            "progress": investigator.get_learning_progress()
                        }
                    }
                else:
                    result = {
                        "success": learn_result.success,
                        "data": {
                            **learn_result.to_dict(),
                            "progress": investigator.get_learning_progress()
                        }
                    }
            except Exception as e:
                logger.error(f"rhino_learn_next failed: {e}", exc_info=True)
                result = {"success": False, "data": f"Learning failed: {str(e)}"}

        case "rhino_execute_intent":
            intent = arguments.get("intent")
            if not intent:
                result = {"success": False, "data": "Missing required parameter: intent"}
            else:
                try:
                    from .learning.intent_orchestrator import IntentOrchestrator
                    from .learning.graph import KnowledgeGraphV2
                    from .learning.command_knowledge_store import CommandKnowledgeStore
                    # record_knowledge is already imported at module level

                    # I3: Pass knowledge_store + KG so the slow path
                    # (command-string resolution for Loft/Sweep/etc.) works.
                    kg = KnowledgeGraphV2()
                    try:
                        ks = CommandKnowledgeStore()
                    except Exception:
                        ks = None  # Graceful degradation if store not available

                    # H1: Bind the user-selected port so all internal calls
                    # (direct API, /command, interactive) target the correct
                    # Rhino instance in multi-instance scenarios.
                    async def bound_caller(endpoint, method="GET", data=None):
                        return await call_rhino(endpoint, method, data, port=port)

                    # M1: Query current selection to build geometry context.
                    # Native /selection returns {count, objects: [{id, type, ...}]}.
                    # We extract IDs and types so the planner can inject them
                    # into operations like "move the selected objects".
                    geo_context = None
                    try:
                        sel_resp = await bound_caller("/selection", "GET", None)
                        if sel_resp.get("success"):
                            sel_data = sel_resp.get("data", {})
                            if isinstance(sel_data, dict):
                                objects = sel_data.get("objects", [])
                                if objects:
                                    sel_ids = [
                                        obj["id"] for obj in objects
                                        if isinstance(obj, dict) and "id" in obj
                                    ]
                                    geo_types = {
                                        obj["id"]: obj.get("type", "object")
                                        for obj in objects
                                        if isinstance(obj, dict) and "id" in obj
                                    }
                                    if sel_ids:
                                        geo_context = {
                                            "selected_ids": sel_ids,
                                            "geometry_types": geo_types,
                                        }
                    except Exception:
                        pass  # Selection query failed — proceed without context

                    orchestrator = IntentOrchestrator(
                        http_caller=bound_caller,
                        knowledge_store=ks,
                        knowledge_graph=kg,
                        recorder=record_knowledge,
                    )
                    exec_result = await orchestrator.run(intent, context=geo_context)

                    result = {
                        "success": exec_result["success"],
                        "data": exec_result,
                    }
                except Exception as e:
                    logger.error(f"rhino_execute_intent failed: {e}", exc_info=True)
                    result = {"success": False, "data": f"Execution failed: {str(e)}"}

        case "rhino_learning_progress":
            try:
                from .learning.hybrid_investigator import HybridInvestigator
                from .learning.graph import KnowledgeGraphV2

                # Create investigator with knowledge graph for consistent behavior
                kg = KnowledgeGraphV2()
                investigator = HybridInvestigator(kg=kg)
                progress = investigator.get_learning_progress()

                result = {
                    "success": True,
                    "data": progress
                }
            except Exception as e:
                result = {"success": False, "data": f"Progress query failed: {str(e)}"}

        # Session Recording handlers
        case "session_current":
            result = await call_rhino("/session", "GET", port=port)

        case "session_history":
            result = await call_rhino("/session/history", "GET", arguments, port=port)

        case "session_list":
            result = await call_rhino("/session/list", "GET", arguments, port=port)

        case "session_export":
            result = await call_rhino("/session/export", "POST", arguments, port=port)

        # AI Gumball handlers
        case "rhino_gumball_activate":
            result = await call_rhino("/gumball/activate", "POST", arguments, port=port)

        case "rhino_gumball_deactivate":
            result = await call_rhino("/gumball/deactivate", "POST", port=port)

        case "rhino_gumball_status":
            result = await call_rhino("/gumball/status", "GET", port=port)

        case "rhino_gumball_history":
            result = await call_rhino("/gumball/history", "GET", arguments, port=port)

        case "rhino_gumball_align":
            result = await call_rhino("/gumball/align", "POST", arguments, port=port)

        case "rhino_gumball_extrude":
            result = await call_rhino("/gumball/extrude", "POST", arguments, port=port)

        case "rhino_gumball_cut":
            result = await call_rhino("/gumball/cut", "POST", arguments, port=port)

        case "rhino_gumball_settings":
            result = await call_rhino("/gumball/settings", "POST", arguments, port=port)

        # Grasshopper handlers
        case "gh_status":
            result = await call_rhino("/gh/status", "GET", port=port)

        case "gh_snapshot":
            result = await call_rhino("/gh/snapshot", "POST", arguments, port=port)

        case "gh_edit":
            if "epoch" not in arguments:
                result = {"success": False, "data": "Missing required parameter: epoch"}
            else:
                deprecation_warnings = get_unified_store().check_deprecation_warnings(
                    arguments.get("create", [])
                )
                result = await call_rhino("/gh/edit", "POST", arguments, port=port)
                result = _attach_deprecation_warnings(result, deprecation_warnings)
                result = _attach_gh_edit_partial_warnings(result)
                # Record to session history
                if result.get("success"):
                    try:
                        await _record_gh_to_session(
                            action="gh_edit",
                            params=arguments,
                            result=result,
                            port=port,
                        )
                    except Exception:
                        pass  # Don't fail the edit if session recording fails

        case "gh_undo":
            result = await call_rhino("/gh/undo", "POST", port=port)
            if result.get("success"):
                try:
                    await _record_gh_to_session(
                        action="gh_undo",
                        params={},
                        result=result,
                        port=port,
                    )
                except Exception:
                    pass

        case "gh_selection":
            result = await call_rhino("/gh/selection", "GET", port=port)

        case "gh_library":
            # Build query string for GET request
            params = {}
            if arguments.get("search"):
                params["search"] = arguments["search"]
            if arguments.get("category"):
                params["category"] = arguments["category"]
            if arguments.get("limit"):
                params["limit"] = arguments["limit"]
            if arguments.get("exact"):
                params["exact"] = True  # Server-side exact name matching
            result = await call_rhino("/gh/library", "GET", params, port=port)

        case "gh_categories":
            result = await call_rhino("/gh/categories", "GET", port=port)

        case "gh_create_component":
            result = await call_rhino("/gh/create-component", "POST", arguments, port=port)
            created_guid = _extract_gh_result_guid(result)
            await _record_gh_to_session(
                action="gh_create_component",
                params=arguments,
                result=result,
                port=port,
                components_created=[created_guid] if created_guid else [],
            )

        case "gh_create_slider":
            result = await call_rhino("/gh/create-slider", "POST", arguments, port=port)
            created_guid = _extract_gh_result_guid(result)
            await _record_gh_to_session(
                action="gh_create_slider",
                params=arguments,
                result=result,
                port=port,
                components_created=[created_guid] if created_guid else [],
            )

        case "gh_create_panel":
            result = await call_rhino("/gh/create-panel", "POST", arguments, port=port)
            created_guid = _extract_gh_result_guid(result)
            await _record_gh_to_session(
                action="gh_create_panel",
                params=arguments,
                result=result,
                port=port,
                components_created=[created_guid] if created_guid else [],
            )

        case "gh_get_value":
            guid = arguments.get("guid")
            if not guid:
                result = {"success": False, "data": "Missing required parameter: guid"}
            else:
                result = await call_rhino("/gh/value", "GET", {"guid": guid}, port=port)

        case "gh_set_value":
            result = await _execute_gh_set_value_with_knowledge(arguments, port)

        case "gh_set_script":
            guid = arguments.get("guid")
            if not guid:
                result = {"success": False, "data": "Missing required parameter: guid"}
            else:
                payload = {"guid": guid}
                if "script" in arguments:
                    payload["script"] = arguments["script"]
                result = await call_rhino("/gh/script", "POST", payload, port=port)
            await _record_gh_to_session(
                action="gh_set_script",
                params=arguments,
                result=result,
                port=port,
                components_affected=[guid] if guid else [],
            )

        case "gh_create_python_script":
            py_code = arguments.get("code")
            py_pins_in = arguments.get("pins_in", [])
            py_pins_out = arguments.get("pins_out", [])
            py_name = arguments.get("name")
            py_x = arguments.get("x", 200)
            py_y = arguments.get("y", 200)
            component_guid = None

            if not py_code:
                result = {"success": False, "data": "Missing required parameter: code"}
            elif not py_pins_in and not py_pins_out:
                result = {"success": False, "data": "Must provide at least pins_in or pins_out"}
            else:
                try:
                    # Python 3 Script component GUID (RhinoCode)
                    PY3_GUID = "719467e6-7cf5-4848-99b0-c5dd57e5442c"

                    # ── Auto-generate coercion preamble ──────────────────────
                    # GH Python 3 Script pins are Generic Data. Geometry types
                    # arrive as System.Guid references; numbers may be GH
                    # wrappers. This preamble converts every input to its
                    # declared native type so the user's code just works.
                    preamble = _build_gh_python_preamble(py_pins_in)
                    full_script = preamble + py_code

                    # Step 1: Create the Python 3 Script component
                    create_result = await call_rhino(
                        "/gh/create-component", "POST",
                        {"guid": PY3_GUID, "x": py_x, "y": py_y},
                        port=port,
                    )
                    if not create_result.get("success"):
                        result = {
                            "success": False,
                            "data": f"Failed to create Python 3 Script component: {create_result.get('data')}",
                        }
                    else:
                        cdata = create_result["data"]
                        component_guid = str(cdata.get("guid") or cdata.get("Guid"))

                        # Step 2: Configure pins (must happen before script so bindings match)
                        def _parse_pin(pin_str: str) -> dict:
                            """Parse 'Name:Type' into {'name': 'Name'}."""
                            parts = pin_str.split(":", 1)
                            return {"name": parts[0].strip()}

                        params_payload: dict = {
                            "guid": component_guid,
                            "inputs": [_parse_pin(p) for p in py_pins_in],
                            "outputs": [_parse_pin(p) for p in py_pins_out],
                        }
                        if py_name:
                            params_payload["nick"] = py_name

                        params_result = await call_rhino(
                            "/gh/script-params", "POST",
                            params_payload,
                            port=port,
                        )
                        if not params_result.get("success"):
                            result = {
                                "success": False,
                                "data": f"Component created but pin config failed: {params_result.get('data')}",
                            }
                        else:
                            # Step 3: Write the script (with preamble)
                            script_result = await call_rhino(
                                "/gh/script", "POST",
                                {"guid": component_guid, "script": full_script},
                                port=port,
                            )
                            if not script_result.get("success"):
                                result = {
                                    "success": False,
                                    "data": f"Component created but script injection failed: {script_result.get('data')}",
                                }
                            else:
                                # Step 4: Check for compilation errors
                                await asyncio.sleep(0.3)
                                errors_result = await call_rhino(
                                    "/gh/errors", "GET", {}, port=port,
                                )
                                component_errors = []
                                if errors_result.get("success"):
                                    edata = errors_result.get("data", {})
                                    for err in edata.get("errors", []):
                                        if err.get("guid") == component_guid:
                                            component_errors = err.get("errors", [])
                                            break

                                result = {
                                    "success": True,
                                    "data": {
                                        "component_guid": component_guid,
                                        "pins_in": py_pins_in,
                                        "pins_out": py_pins_out,
                                        "position": {"x": py_x, "y": py_y},
                                        "name": py_name or "Python 3 Script",
                                        "code_length": len(full_script),
                                    },
                                }
                                if component_errors:
                                    result["data"]["compilation_errors"] = component_errors
                                    result["data"]["warning"] = "Component placed but has compilation errors"

                except Exception as e:
                    result = {"success": False, "data": f"gh_create_python_script failed: {str(e)}"}

            await _record_gh_to_session(
                action="gh_create_python_script",
                params={k: v for k, v in arguments.items() if k != "code"},  # Don't log full code
                result=result,
                port=port,
                components_created=[component_guid] if component_guid else [],
            )

        case "gh_create_csharp_script":
            cs_code = arguments.get("code")
            cs_pins_in = arguments.get("pins_in", [])
            cs_pins_out = arguments.get("pins_out", [])
            cs_name = arguments.get("name")
            cs_x = arguments.get("x", 200)
            cs_y = arguments.get("y", 200)
            component_guid = None

            if not cs_code:
                result = {"success": False, "data": "Missing required parameter: code"}
            elif not cs_pins_in and not cs_pins_out:
                result = {"success": False, "data": "Must provide at least pins_in or pins_out"}
            else:
                try:
                    # RhinoCode C# Script component GUID
                    CS3_GUID = "b6ba1144-02d6-4a2d-b53c-ec62e290eeb7"

                    # Wrap user code in Script_Instance boilerplate if needed
                    full_script = _build_gh_csharp_wrapper(cs_code, cs_pins_in, cs_pins_out)

                    # Step 1: Create the C# Script component
                    create_result = await call_rhino(
                        "/gh/create-component", "POST",
                        {"guid": CS3_GUID, "x": cs_x, "y": cs_y},
                        port=port,
                    )
                    if not create_result.get("success"):
                        result = {
                            "success": False,
                            "data": f"Failed to create C# Script component: {create_result.get('data')}",
                        }
                    else:
                        cdata = create_result["data"]
                        component_guid = str(cdata.get("guid") or cdata.get("Guid"))

                        # Step 2: Configure pins (must happen before script so bindings match)
                        def _parse_pin(pin_str: str) -> dict:
                            """Parse 'Name:Type' into {'name': 'Name'}."""
                            parts = pin_str.split(":", 1)
                            return {"name": parts[0].strip()}

                        params_payload: dict = {
                            "guid": component_guid,
                            "inputs": [_parse_pin(p) for p in cs_pins_in],
                            "outputs": [_parse_pin(p) for p in cs_pins_out],
                        }
                        if cs_name:
                            params_payload["nick"] = cs_name

                        params_result = await call_rhino(
                            "/gh/script-params", "POST",
                            params_payload,
                            port=port,
                        )
                        if not params_result.get("success"):
                            result = {
                                "success": False,
                                "data": f"Component created but pin config failed: {params_result.get('data')}",
                            }
                        else:
                            # Step 3: Write the script
                            script_result = await call_rhino(
                                "/gh/script", "POST",
                                {"guid": component_guid, "script": full_script},
                                port=port,
                            )
                            if not script_result.get("success"):
                                result = {
                                    "success": False,
                                    "data": f"Component created but script injection failed: {script_result.get('data')}",
                                }
                            else:
                                # Step 4: Check for compilation errors
                                await asyncio.sleep(0.3)
                                errors_result = await call_rhino(
                                    "/gh/errors", "GET", {}, port=port,
                                )
                                component_errors = []
                                if errors_result.get("success"):
                                    edata = errors_result.get("data", {})
                                    for err in edata.get("errors", []):
                                        if err.get("guid") == component_guid:
                                            component_errors = err.get("errors", [])
                                            break

                                result = {
                                    "success": True,
                                    "data": {
                                        "component_guid": component_guid,
                                        "pins_in": cs_pins_in,
                                        "pins_out": cs_pins_out,
                                        "position": {"x": cs_x, "y": cs_y},
                                        "name": cs_name or "C# Script",
                                        "code_length": len(full_script),
                                    },
                                }
                                if component_errors:
                                    result["data"]["compilation_errors"] = component_errors
                                    result["data"]["warning"] = "Component placed but has compilation errors"

                except Exception as e:
                    result = {"success": False, "data": f"gh_create_csharp_script failed: {str(e)}"}

            await _record_gh_to_session(
                action="gh_create_csharp_script",
                params={k: v for k, v in arguments.items() if k != "code"},
                result=result,
                port=port,
                components_created=[component_guid] if component_guid else [],
            )

        case "chirp_create":
            pins_in = arguments.get("pins_in")
            pins_out = arguments.get("pins_out")
            signature = arguments.get("signature")
            category = arguments.get("category")
            chirp_name = arguments.get("name")
            deterministic_code = arguments.get("deterministic_code")
            cx = arguments.get("x", 200)
            cy = arguments.get("y", 200)

            if not pins_in or not pins_out or not signature:
                result = {"success": False, "data": "Missing required parameters: pins_in, pins_out, signature"}
            elif not category:
                result = {"success": False, "data": "Missing required parameter: category. Must be one of: planner, interpreter, critic, narrator, classifier, gate, editor"}
            else:
                # Ensure Chirp adapter is running (auto-start if needed)
                from rook.chirp_manager import ensure_chirp_running
                chirp_status = await ensure_chirp_running()
                if not chirp_status["running"]:
                    result = {"success": False, "data": chirp_status["error"]}
                else:
                    chirp_host = chirp_status.get("host", "127.0.0.1")
                    chirp_port = chirp_status["port"]
                    try:
                        # Step 1: Call Chirp adapter to generate the C# script
                        chirp_payload = {
                            "pins_in": pins_in,
                            "pins_out": pins_out,
                            "signature": signature,
                            "category": category,
                            "port": chirp_port,
                        }
                        if chirp_name:
                            chirp_payload["name"] = chirp_name
                        if deterministic_code:
                            chirp_payload["deterministic_code"] = deterministic_code

                        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as chirp_client:
                            chirp_resp = await chirp_client.post(
                                f"http://{chirp_host}:{chirp_port}/chirp/create",
                                json=chirp_payload,
                            )
                            if chirp_resp.status_code != 200:
                                error_data = chirp_resp.json()
                                result = {
                                    "success": False,
                                    "data": f"Chirp script generation failed: {error_data.get('details', chirp_resp.text)}",
                                }
                            else:
                                chirp_result = chirp_resp.json()
                                script = chirp_result["script"]

                                # Step 2: Create a RhinoCode C# Script component (not the legacy GH1 one).
                                # Using GUID directly — name "C# Script" can resolve to the legacy component.
                                create_result = await call_rhino(
                                    "/gh/create-component", "POST",
                                    {"guid": "b6ba1144-02d6-4a2d-b53c-ec62e290eeb7", "x": cx, "y": cy},
                                    port=port,
                                )
                                if not create_result.get("success"):
                                    result = {
                                        "success": False,
                                        "data": f"Failed to create C# Script component: {create_result.get('data')}",
                                    }
                                else:
                                    # C# bridge serializes with camelCase — field is "guid" not "Guid"
                                    cdata = create_result["data"]
                                    component_guid = cdata.get("guid") or cdata.get("Guid")

                                    # Step 3: Configure pins + NickName (must happen before script
                                    # injection so RunScript params match the component's parameters)
                                    display_name = chirp_result.get("name") or chirp_name
                                    params_payload = {
                                        "guid": str(component_guid),
                                        "inputs": chirp_result["pins_in"],
                                        "outputs": chirp_result["pins_out"],
                                    }
                                    if display_name:
                                        params_payload["nick"] = display_name
                                    params_result = await call_rhino(
                                        "/gh/script-params", "POST",
                                        params_payload,
                                        port=port,
                                    )
                                    if not params_result.get("success"):
                                        result = {
                                            "success": False,
                                            "data": f"Component created but pin config failed: {params_result.get('data')}",
                                        }
                                    else:
                                        # Step 4: Inject the generated script
                                        script_result = await call_rhino(
                                            "/gh/script", "POST",
                                            {"guid": str(component_guid), "script": script},
                                            port=port,
                                        )
                                        if not script_result.get("success"):
                                            result = {
                                                "success": False,
                                                "data": f"Component created but script injection failed: {script_result.get('data')}",
                                            }
                                        else:
                                            # Step 5: Validate — check for compilation errors
                                            # Small delay lets the GH solver process the new script
                                            await asyncio.sleep(0.2)
                                            errors_result = await call_rhino(
                                                "/gh/errors", "GET", {}, port=port,
                                            )
                                            component_errors = []
                                            if errors_result.get("success"):
                                                edata = errors_result.get("data", {})
                                                for err in edata.get("errors", []):
                                                    if err.get("guid") == str(component_guid):
                                                        component_errors = err.get("errors", [])
                                                        break

                                            result = {
                                                "success": True,
                                                "data": {
                                                    "component_guid": str(component_guid),
                                                    "pins_in": chirp_result["pins_in"],
                                                    "pins_out": chirp_result["pins_out"],
                                                    "position": {"x": cx, "y": cy},
                                                    "signature": signature,
                                                    "category": chirp_result.get("category", category),
                                                    "name": chirp_result.get("name", chirp_name),
                                                },
                                            }
                                            if component_errors:
                                                result["data"]["compilation_errors"] = component_errors
                                                result["data"]["warning"] = "Component placed but has compilation errors"

                    except Exception as e:
                        result = {"success": False, "data": f"chirp_create failed: {str(e)}"}

            await _record_gh_to_session(
                action="chirp_create",
                params=arguments,
                result=result,
                port=port,
                components_created=[result.get("data", {}).get("component_guid", "")] if isinstance(result.get("data"), dict) and result.get("success") else [],
            )

        case "gh_errors":
            result = await call_rhino("/gh/errors", "GET", {}, port=port)

        case "gh_set_reference":
            param_guid = arguments.get("paramGuid")
            rhino_obj_id = arguments.get("rhinoObjectId")
            if not param_guid or not rhino_obj_id:
                result = {"success": False, "data": "Missing required parameters: paramGuid and rhinoObjectId"}
            else:
                # Map to C# parameter names: guid and rhinoId
                result = await call_rhino("/gh/set-reference", "POST", {"guid": param_guid, "rhinoId": rhino_obj_id}, port=port)
            await _record_gh_to_session(
                action="gh_set_reference",
                params=arguments,
                result=result,
                port=port,
                components_affected=[param_guid] if param_guid else [],
            )

        case "gh_get_reference":
            guid = arguments.get("guid")
            if not guid:
                result = {"success": False, "data": "Missing required parameter: guid"}
            else:
                result = await call_rhino("/gh/get-reference", "GET", {"guid": guid}, port=port)

        case "gh_clear_reference":
            guid = arguments.get("guid")
            if not guid:
                result = {"success": False, "data": "Missing required parameter: guid"}
            else:
                result = await call_rhino("/gh/clear-reference", "POST", {"guid": guid}, port=port)
            await _record_gh_to_session(
                action="gh_clear_reference",
                params=arguments,
                result=result,
                port=port,
                components_affected=[guid] if guid else [],
            )

        case "gh_bake_output":
            result = await call_rhino("/gh/bake", "POST", arguments, port=port)
            # Derive affected components from result (covers bakeAll) or fall back to request targets
            affected = []
            result_data = result.get("data") if isinstance(result, dict) else None
            if isinstance(result_data, dict):
                per_target = result_data.get("perTarget", [])
                if isinstance(per_target, list) and per_target:
                    affected = [t.get("instanceGuid", "") for t in per_target if isinstance(t, dict) and t.get("instanceGuid")]
            if not affected and isinstance(arguments.get("targets"), list):
                affected = [t.get("instanceGuid", "") for t in arguments["targets"] if isinstance(t, dict) and t.get("instanceGuid")]
            await _record_gh_to_session(
                action="gh_bake_output",
                params=arguments,
                result=result,
                port=port,
                components_affected=affected,
            )

        case "gh_solve":
            result = await call_rhino("/gh/solve", "POST", arguments, port=port)
            await _record_gh_to_session(
                action="gh_solve",
                params=arguments,
                result=result,
                port=port,
            )

        case "gh_delete":
            result = await _execute_gh_delete_with_knowledge(arguments, port)

        case "gh_preview":
            result = await call_rhino("/gh/preview", "POST", arguments, port=port)
            await _record_gh_to_session(
                action="gh_preview",
                params=arguments,
                result=result,
                port=port,
                components_affected=_normalize_gh_guid_list(arguments.get("guids")),
            )

        case "gh_clear":
            result = await call_rhino("/gh/clear", "POST", port=port)
            await _record_gh_to_session(
                action="gh_clear",
                params=arguments,
                result=result,
                port=port,
            )

        case "gh_document_open":
            path = arguments.get("path")
            if not path:
                result = {"success": False, "data": "Missing required parameter: path"}
            else:
                result = await call_rhino("/gh/document/open", "POST", {"path": path}, port=port)
            await _record_gh_to_session(
                action="gh_document_open",
                params=arguments,
                result=result,
                port=port,
            )

        case "gh_document_new":
            result = await call_rhino("/gh/document/new", "POST", port=port)
            await _record_gh_to_session(
                action="gh_document_new",
                params=arguments,
                result=result,
                port=port,
            )

        case "gh_learn_directory":
            # Batch learning from directory of GH/GHX files
            directory = arguments.get("directory")
            if not directory:
                result = {"success": False, "data": "Missing required parameter: directory"}
            else:
                import os
                from pathlib import Path

                dir_path = Path(directory)
                if not dir_path.exists():
                    result = {"success": False, "data": f"Directory not found: {directory}"}
                else:
                    recursive = arguments.get("recursive", True)
                    limit = arguments.get("limit")

                    # Find all GH/GHX files
                    if recursive:
                        gh_files = list(dir_path.rglob("*.gh")) + list(dir_path.rglob("*.ghx"))
                    else:
                        gh_files = list(dir_path.glob("*.gh")) + list(dir_path.glob("*.ghx"))

                    if limit:
                        gh_files = gh_files[:limit]

                    processed = 0
                    succeeded = 0
                    failed = 0
                    recipes_created = []
                    errors = []

                    for gh_file in gh_files:
                        processed += 1
                        file_path = str(gh_file)

                        try:
                            # 1. Open the file
                            open_result = await call_rhino("/gh/document/open", "POST", {"path": file_path}, port=port)
                            if not open_result.get("success"):
                                failed += 1
                                errors.append({"file": gh_file.name, "error": f"Failed to open: {open_result.get('data')}"})
                                continue

                            # Small delay to let GH settle
                            await asyncio.sleep(0.3)

                            # 2. Extract recipe using existing tool logic
                            try:
                                from .learning.recipe_extraction import extract_recipe
                                from .learning.recipe_classification import classify_recipe

                                # Get canvas state
                                query_result = await call_rhino("/gh/query", "GET", port=port)
                                if not query_result.get("success"):
                                    failed += 1
                                    errors.append({"file": gh_file.name, "error": "Failed to query canvas"})
                                    continue

                                canvas_state = query_result.get("data", {})
                                objects = canvas_state.get("objects", [])
                                if not objects:
                                    failed += 1
                                    errors.append({"file": gh_file.name, "error": "No objects on canvas"})
                                    continue

                                # Get connection data for each component (same as gh_extract_recipe)
                                connections_data = {}
                                for obj in objects:
                                    guid = obj.get("guid")
                                    if guid:
                                        conn_result = await call_rhino("/gh/connections", "GET", {"guid": guid}, port=port)
                                        if conn_result.get("success"):
                                            comp_data = conn_result.get("data", {})
                                            if "inputs" in comp_data:
                                                transformed_inputs = []
                                                for inp in comp_data["inputs"]:
                                                    transformed_sources = []
                                                    for src in inp.get("sources", []):
                                                        transformed_sources.append({
                                                            "guid": src.get("componentGuid", ""),
                                                            "param": src.get("paramNickName") or src.get("paramName", "output"),
                                                        })
                                                    transformed_inputs.append({
                                                        "name": inp.get("paramNickName") or inp.get("paramName", ""),
                                                        "sources": transformed_sources,
                                                    })
                                                connections_data[guid] = {"inputs": transformed_inputs}

                                # Extract recipe data
                                draft = extract_recipe(
                                    canvas_state=canvas_state,
                                    connections_data=connections_data,
                                    source_definition=gh_file.name,
                                    use_dspy=True,
                                )
                                if draft:
                                    # Classify the recipe using component names
                                    component_names = [c.get("name", "") for c in draft.components]
                                    classification = classify_recipe(component_names, use_dspy=True)

                                    # Apply classification to draft
                                    if classification.get("suggested_name"):
                                        draft.suggested_name = classification["suggested_name"]
                                    if classification.get("tags"):
                                        draft.detected_tags = classification["tags"]
                                    if classification.get("intents"):
                                        draft.suggested_intents = classification["intents"]

                                    # Save to pattern store using PatternNote
                                    from .learning.pattern_store import get_pattern_store
                                    from .learning.pattern_memory import PatternNote
                                    store = get_pattern_store()

                                    recipe_name = draft.suggested_name or gh_file.stem
                                    pattern = PatternNote(
                                        name=recipe_name,
                                        pattern_type="recipe",
                                        solution_brief=draft.description or f"Recipe from {gh_file.name}",
                                        components_needed=component_names,
                                        trigger_intents=draft.suggested_intents or [],
                                        tags=draft.detected_tags or [],
                                        wiring=draft.wiring,
                                        input_structure=draft.input_structure,
                                        output_type=draft.output_type,
                                        source_definition=gh_file.name,
                                        created_from="batch_extraction",
                                    )
                                    store.add(pattern)

                                    succeeded += 1
                                    recipes_created.append({
                                        "file": gh_file.name,
                                        "pattern_id": pattern.pattern_id,
                                        "name": recipe_name,
                                        "components": len(draft.components),
                                        "connections": len(draft.wiring),
                                    })
                                else:
                                    failed += 1
                                    errors.append({"file": gh_file.name, "error": "Failed to extract recipe"})
                            except Exception as extract_err:
                                failed += 1
                                errors.append({"file": gh_file.name, "error": f"Extract error: {str(extract_err)}"})

                            # 3. Clear canvas for next file
                            await call_rhino("/gh/clear", "POST", port=port)

                        except Exception as e:
                            failed += 1
                            errors.append({"file": gh_file.name, "error": str(e)})

                    result = {
                        "success": True,
                        "data": {
                            "processed": processed,
                            "succeeded": succeeded,
                            "failed": failed,
                            "recipes": recipes_created,
                            "errors": errors[:10] if len(errors) > 10 else errors,  # Limit error output
                            "total_files_found": len(gh_files),
                        }
                    }

        case "gh_move":
            result = await call_rhino("/gh/move", "POST", arguments, port=port)
            # Record to session - track affected components
            moved_guids = arguments.get("guids", [])
            if isinstance(moved_guids, str):
                moved_guids = [moved_guids]
            await _record_gh_to_session(
                action="gh_move",
                params=arguments,
                result=result,
                port=port,
                components_affected=moved_guids,
            )

        case "gh_canvas_cleanup":
            # Get parameters with defaults
            start_x = arguments.get("start_x", 50)
            start_y = arguments.get("start_y", 50)
            horizontal_gap = arguments.get("horizontal_gap", 30)
            vertical_gap = arguments.get("vertical_gap", 20)
            max_layer_width = arguments.get("max_layer_width", 4)
            dry_run = arguments.get("dry_run", False)

            # Step 1: Query all canvas objects
            query_result = await call_rhino("/gh/query", "GET", {}, port)
            if not query_result.get("success"):
                return [TextContent(
                    type="text",
                    text=json.dumps({"error": "Failed to query canvas", "details": query_result})
                )]

            all_objects = query_result.get("data", {}).get("objects", [])
            # Filter out GH_Group objects — they have huge bounding boxes and no
            # wire connections, which poisons the layout graph (causes stretching).
            # Groups are handled separately via /gh/groups + /gh/group-resize.
            GROUP_TYPE_NAMES = {"GH_Group", "Group"}
            components = [
                obj for obj in all_objects
                if obj.get("type") not in GROUP_TYPE_NAMES
            ]
            if not components:
                return [TextContent(
                    type="text",
                    text=json.dumps({"success": True, "message": "Canvas is empty, nothing to organize"})
                )]

            # Step 2: Get connections for each component
            connections: dict[str, dict] = {}
            for comp in components:
                guid = comp.get("guid")
                if not guid:
                    continue
                conn_result = await call_rhino(f"/gh/connections?guid={guid}", "GET", {}, port)
                if conn_result.get("success"):
                    connections[guid] = conn_result.get("data", {})
                else:
                    connections[guid] = {"inputs": [], "outputs": []}

            # Step 2b: Query groups (for group-aware layout)
            groups_data = []
            try:
                groups_result = await call_rhino("/gh/groups", "GET", {}, port)
                if groups_result.get("success"):
                    groups_data = groups_result.get("data", {}).get("groups", [])
            except Exception:
                pass  # Groups endpoint may not exist on older plugin versions

            # Step 3: Build LayoutSettings from arguments
            settings = LayoutSettings(
                horizontal_gap=horizontal_gap,
                vertical_gap=vertical_gap,
                style=arguments.get("style", "expanded"),
                collision_detection=arguments.get("collision_detection", True),
                expand_by_height=arguments.get("expand_by_height", True),
                center_branches=arguments.get("center_branches", True),
                snap_to_grid=arguments.get("snap_to_grid", False),
                grid_size=arguments.get("grid_size", 8.0),
                anchor_guid=arguments.get("anchor_guid"),
            )

            # Step 4: Run CanvasLayout pipeline
            canvas_layout = CanvasLayout(settings)
            positions = canvas_layout.run(
                components=components,
                connections=connections,
                groups=groups_data,
                start_x=start_x,
                start_y=start_y,
                max_layer_width=max_layer_width,
            )

            result_data = {
                "success": True,
                "components_analyzed": len(components),
                "groups_excluded": len(all_objects) - len(components),
                "layers": canvas_layout.num_layers,
                "positions": positions,
                "settings": {
                    "style": settings.style,
                    "collision_detection": settings.collision_detection,
                    "expand_by_height": settings.expand_by_height,
                    "center_branches": settings.center_branches,
                },
            }

            # Step 5: Move components (unless dry run)
            if not dry_run and positions:
                move_positions = [
                    {"guid": guid, "x": pos["x"], "y": pos["y"]}
                    for guid, pos in positions.items()
                ]
                move_result = await call_rhino("/gh/move", "POST", {"positions": move_positions}, port)
                result_data["move_result"] = move_result
                result_data["dry_run"] = False

                # Step 6: Resize groups to fit members
                if groups_data:
                    for group in groups_data:
                        group_guid = group.get("guid") or group.get("Guid")
                        if group_guid:
                            try:
                                await call_rhino("/gh/group-resize", "POST", {
                                    "guid": group_guid,
                                    "padding": settings.group_padding,
                                }, port)
                            except Exception:
                                pass

                # Record to session
                await _record_gh_to_session(
                    action="gh_canvas_cleanup",
                    params=arguments,
                    result=result_data,
                    port=port,
                    components_affected=[p["guid"] for p in move_positions],
                )
            else:
                result_data["dry_run"] = True
                result_data["message"] = "Dry run - positions calculated but components not moved"

            return [TextContent(type="text", text=json.dumps(result_data, indent=2))]

        case "gh_canvas_focus":
            result = await call_rhino("/gh/canvas/focus", "POST", arguments, port=port)

        case "gh_canvas_zoom":
            result = await call_rhino("/gh/canvas/zoom", "POST", arguments, port=port)

        case "gh_canvas_image":
            result = await call_rhino("/gh/canvas/image", "GET", {}, port=port)

        case "gh_cluster":
            result = await call_rhino("/gh/cluster", "POST", arguments, port=port)
            # Record to session - track created cluster and removed components
            cluster_guid = None
            clustered_guids = arguments.get("guids", [])
            if isinstance(clustered_guids, str):
                clustered_guids = [clustered_guids]
            if result.get("success") and isinstance(result.get("data"), dict):
                cluster_guid = result["data"].get("Guid") or result["data"].get("guid")
            await _record_gh_to_session(
                action="gh_cluster",
                params=arguments,
                result=result,
                port=port,
                components_created=[cluster_guid] if cluster_guid else [],
                components_deleted=clustered_guids,  # Original components get absorbed into cluster
            )

        # GH Canvas Alignment handlers
        case "gh_align":
            guids = arguments.get("guids", [])
            direction = arguments.get("direction", "left")
            anchor = arguments.get("anchor", "first")

            if not guids or len(guids) < 2:
                result = {"success": False, "data": "Need at least 2 GUIDs to align"}
            else:
                # Query component positions
                query_result = await call_rhino("/gh/query", "GET", {}, port)
                if not query_result.get("success"):
                    result = {"success": False, "data": "Failed to query canvas"}
                else:
                    all_comps = query_result.get("data", {}).get("objects", [])
                    guid_set = set(guids)
                    comps = [c for c in all_comps if c.get("guid") in guid_set]
                    if len(comps) < 2:
                        result = {"success": False, "data": f"Found {len(comps)} of {len(guids)} components"}
                    else:
                        move_positions = align_positions(comps, direction, anchor)
                        move_result = await call_rhino("/gh/move", "POST", {"positions": move_positions}, port)
                        result = {"success": True, "data": {"aligned": len(move_positions), "direction": direction, "move_result": move_result}}

        case "gh_distribute":
            guids = arguments.get("guids", [])
            axis = arguments.get("axis", "horizontal")
            spacing = arguments.get("spacing")

            if not guids or len(guids) < 2:
                result = {"success": False, "data": "Need at least 2 GUIDs to distribute"}
            else:
                query_result = await call_rhino("/gh/query", "GET", {}, port)
                if not query_result.get("success"):
                    result = {"success": False, "data": "Failed to query canvas"}
                else:
                    all_comps = query_result.get("data", {}).get("objects", [])
                    guid_set = set(guids)
                    comps = [c for c in all_comps if c.get("guid") in guid_set]
                    if len(comps) < 2:
                        result = {"success": False, "data": f"Found {len(comps)} of {len(guids)} components"}
                    else:
                        move_positions = distribute_positions(comps, axis, spacing)
                        move_result = await call_rhino("/gh/move", "POST", {"positions": move_positions}, port)
                        result = {"success": True, "data": {"distributed": len(move_positions), "axis": axis, "move_result": move_result}}

        case "gh_straighten_wires":
            target_guids = arguments.get("guids")

            # Query canvas + connections
            query_result = await call_rhino("/gh/query", "GET", {}, port)
            if not query_result.get("success"):
                result = {"success": False, "data": "Failed to query canvas"}
            else:
                components = query_result.get("data", {}).get("objects", [])
                if not components:
                    result = {"success": True, "data": {"straightened": 0, "message": "Canvas is empty"}}
                else:
                    connections: dict[str, dict] = {}
                    for comp in components:
                        guid = comp.get("guid")
                        if not guid:
                            continue
                        conn_result = await call_rhino(f"/gh/connections?guid={guid}", "GET", {}, port)
                        if conn_result.get("success"):
                            connections[guid] = conn_result.get("data", {})
                        else:
                            connections[guid] = {"inputs": [], "outputs": []}

                    move_positions = straighten_wire_positions(components, connections, target_guids)
                    if move_positions:
                        move_result = await call_rhino("/gh/move", "POST", {"positions": move_positions}, port)
                        result = {"success": True, "data": {"straightened": len(move_positions), "move_result": move_result}}
                    else:
                        result = {"success": True, "data": {"straightened": 0, "message": "No wires to straighten"}}

        # GH Knowledge System handlers
        case "gh_knowledge_query":
            from rook.learning.gh_knowledge import gh_query_knowledge
            intent = arguments.get("intent", "")
            depth = arguments.get("depth", "context")
            try:
                knowledge_result = gh_query_knowledge(intent, depth)
                result = {"success": True, "data": knowledge_result}
            except Exception as e:
                result = {"success": False, "data": f"Knowledge query failed: {str(e)}"}

        case "gh_knowledge_reload":
            from rook.learning.gh_knowledge import gh_reload_knowledge
            try:
                reload_result = gh_reload_knowledge()
                result = {
                    "success": True,
                    "data": {
                        "message": f"Reloaded: {reload_result.get('intents_loaded', 0)} component notes (UnifiedStore), {reload_result.get('components_loaded', 0)} gotcha entries (tiered)",
                        **reload_result
                    }
                }
            except Exception as e:
                result = {"success": False, "data": f"Knowledge reload failed: {str(e)}"}

        case "gh_query_observations":
            from rook.learning.gh_knowledge import gh_query_observations
            try:
                query_result = gh_query_observations(
                    operation=arguments.get("operation"),
                    component=arguments.get("component"),
                    outcome=arguments.get("outcome"),
                    search=arguments.get("search"),
                    limit=arguments.get("limit", 20)
                )
                result = {"success": True, "data": query_result}
            except Exception as e:
                result = {"success": False, "data": f"Observation query failed: {str(e)}"}

        case "gh_record_learning":
            from rook.learning.gh_knowledge import get_gh_knowledge_store
            try:
                operation = arguments.get("operation", "")
                pattern = arguments.get("pattern", "")
                correction = arguments.get("correction", "")

                if not all([operation, pattern, correction]):
                    result = {"success": False, "data": "Missing required fields: operation, pattern, correction"}
                else:
                    store = get_gh_knowledge_store()
                    recorded = store.record_operation_mistake(operation, pattern, correction)
                    if recorded:
                        result = {
                            "success": True,
                            "data": {
                                "message": f"Recorded learning for {operation}: {pattern}",
                                "operation": operation,
                                "pattern": pattern,
                                "correction": correction
                            }
                        }
                    else:
                        result = {"success": False, "data": f"Failed to record - unknown operation: {operation}"}
            except Exception as e:
                result = {"success": False, "data": f"Recording failed: {str(e)}"}

        # Session History Tools (Path 2 meta-learning)
        case "gh_session_current":
            from rook.learning.gh_session_history import get_session_recorder
            try:
                recorder = get_session_recorder()
                session_info = await recorder.get_current()
                if session_info:
                    result = {"success": True, "data": session_info}
                else:
                    result = {"success": True, "data": {"message": "No active session. Sessions start automatically when GH tools are used."}}
            except Exception as e:
                result = {"success": False, "data": f"Failed to get session: {str(e)}"}

        case "gh_session_history":
            from rook.learning.gh_session_history import get_session_recorder
            try:
                recorder = get_session_recorder()
                offset = arguments.get("offset", 0)
                limit = arguments.get("limit", 50)
                outcome = arguments.get("outcome")
                history = await recorder.get_history(offset=offset, limit=limit, outcome=outcome)
                result = {"success": True, "data": history}
            except Exception as e:
                result = {"success": False, "data": f"Failed to get history: {str(e)}"}

        case "gh_session_note":
            from rook.learning.gh_session_history import get_session_recorder
            try:
                note = arguments.get("note", "")
                entry_id = arguments.get("entry_id")
                if not note:
                    result = {"success": False, "data": "Note text is required"}
                else:
                    recorder = get_session_recorder()
                    note_result = await recorder.add_note(note, entry_id)
                    result = {"success": note_result.get("success", False), "data": note_result}
            except Exception as e:
                result = {"success": False, "data": f"Failed to add note: {str(e)}"}

        case "gh_session_end":
            from rook.learning.gh_session_history import get_session_recorder
            try:
                recorder = get_session_recorder()
                document = arguments.get("document")
                end_result = await recorder.end_session(document=document)
                if "error" in end_result:
                    result = {"success": False, "data": end_result}
                else:
                    result = {"success": True, "data": end_result}
            except Exception as e:
                result = {"success": False, "data": f"Failed to end session: {str(e)}"}

        case "gh_constraints":
            from rook.learning.constraints import get_constraint_checker
            try:
                checker = get_constraint_checker()
                component = arguments.get("component")
                components = arguments.get("components", [])
                category = arguments.get("category")

                if component:
                    # Single component query
                    constraints = checker.get_constraints(component)
                    if constraints:
                        result = {
                            "success": True,
                            "data": {
                                "component": constraints.component_name,
                                "category": constraints.category,
                                "constraints": constraints.to_dict(),
                                "summary": checker.get_constraint_summary(component),
                            }
                        }
                    else:
                        result = {
                            "success": True,
                            "data": {
                                "component": component,
                                "message": f"No constraints defined for '{component}'",
                                "available_components": checker.get_all_constrained_components(),
                            }
                        }
                elif components:
                    # Multiple components query
                    warnings = checker.get_warnings_for_components(components)
                    result = {
                        "success": True,
                        "data": {
                            "components_queried": components,
                            "warnings": [w.to_dict() for w in warnings],
                            "error_count": sum(1 for w in warnings if w.severity == "error"),
                            "warning_count": sum(1 for w in warnings if w.severity == "warning"),
                        }
                    }
                elif category:
                    # Category query
                    warnings = checker.get_warnings_by_category(category)
                    result = {
                        "success": True,
                        "data": {
                            "category": category,
                            "warnings": [w.to_dict() for w in warnings],
                            "component_count": len(set(w.component for w in warnings)),
                        }
                    }
                else:
                    # No filter - return summary
                    result = {
                        "success": True,
                        "data": {
                            "total_components": len(checker),
                            "available_components": checker.get_all_constrained_components(),
                            "hint": "Use 'component', 'components', or 'category' parameter to query specific constraints"
                        }
                    }
            except Exception as e:
                import traceback
                result = {"success": False, "data": f"Constraint query failed: {str(e)}", "traceback": traceback.format_exc()}

        case "gh_validate_scenarios":
            from rook.validation import generate_test_scenarios, get_category_coverage
            from rook.learning.pattern_store import get_pattern_store
            try:
                n_scenarios = arguments.get("n_scenarios", 50)
                categories = arguments.get("categories")
                seed = arguments.get("seed", 42)

                # Generate scenarios
                scenarios = generate_test_scenarios(
                    n_scenarios=n_scenarios,
                    categories=categories,
                    seed=seed
                )

                # Get pattern store
                store = get_pattern_store()

                # Check each scenario against pattern memory
                patterns_found = 0
                total_confidence = 0.0

                for scenario in scenarios:
                    intent = scenario.get("intent", "")
                    # Search for patterns matching this scenario
                    matches = store.search(intent=intent, limit=1, verify=False)
                    if matches:
                        patterns_found += 1
                        total_confidence += matches[0].success_rate()

                avg_confidence = total_confidence / patterns_found if patterns_found > 0 else 0.0
                coverage = get_category_coverage(scenarios)

                match_rate = round(patterns_found / len(scenarios), 3) if scenarios else 0

                # Generate guidance based on results
                if len(store) == 0:
                    guidance = (
                        "Pattern store is empty. Low match rate is expected. "
                        "Use gh_save_pattern after successful workflows to build knowledge."
                    )
                elif match_rate == 0:
                    guidance = (
                        f"No scenarios matched any of the {len(store)} patterns. This indicates "
                        "pattern trigger_intents don't align with generated scenarios. "
                        "Add patterns with broader trigger_intents for better coverage."
                    )
                elif match_rate < 0.2:
                    guidance = (
                        f"Low coverage ({match_rate*100:.0f}%). Pattern memory needs more patterns "
                        "for common scenarios. Use gh_reflect + gh_save_pattern after workflows."
                    )
                elif match_rate < 0.5:
                    guidance = (
                        f"Moderate coverage ({match_rate*100:.0f}%). Good progress. Continue adding "
                        "patterns for uncovered scenarios."
                    )
                else:
                    guidance = (
                        f"Good coverage ({match_rate*100:.0f}%). Pattern memory is well-populated."
                    )

                result = {
                    "success": True,
                    "data": {
                        "scenarios_run": len(scenarios),
                        "patterns_found": patterns_found,
                        "match_rate": match_rate,
                        "avg_confidence": round(avg_confidence, 3),
                        "category_coverage": coverage,
                        "total_patterns": len(store),
                        "guidance": guidance,
                    }
                }
            except Exception as e:
                import traceback
                result = {"success": False, "data": f"Scenario validation failed: {str(e)}", "traceback": traceback.format_exc()}

        case "gh_validate_latency":
            from rook.validation import generate_test_scenarios, benchmark_query_latency, check_latency_targets
            from rook.learning.pattern_store import get_pattern_store
            try:
                n_samples = arguments.get("n_samples", 100)
                p50_target = arguments.get("p50_target_ms", 10.0)
                p99_target = arguments.get("p99_target_ms", 50.0)

                # Generate scenarios for benchmarking
                scenarios = generate_test_scenarios(n_scenarios=n_samples, seed=42)

                # Get pattern store
                store = get_pattern_store()

                # Create query function
                def query_fn(intent, tool, params):
                    matches = store.search(intent=intent, limit=5, verify=False)
                    return {
                        "patterns": [{"id": m.pattern_id, "name": m.name} for m in matches],
                        "confidence": matches[0].success_rate() if matches else 0.0
                    }

                # Run benchmark
                stats = benchmark_query_latency(query_fn, scenarios, n_iterations=1)

                # Check targets
                passes, message = check_latency_targets(stats, p50_target, p99_target)

                result = {
                    "success": True,
                    "data": {
                        "n_samples": stats.n_samples,
                        "p50_ms": stats.p50_ms,
                        "p90_ms": stats.p90_ms,
                        "p99_ms": stats.p99_ms,
                        "mean_ms": stats.mean_ms,
                        "min_ms": stats.min_ms,
                        "max_ms": stats.max_ms,
                        "passes_targets": passes,
                        "message": message,
                    }
                }
            except Exception as e:
                import traceback
                result = {"success": False, "data": f"Latency benchmark failed: {str(e)}", "traceback": traceback.format_exc()}

        case "gh_validate_regression":
            from rook.learning.pattern_store import get_pattern_store
            try:
                store = get_pattern_store()

                # Detect regressions
                regressions = store.detect_regressions()

                # Get confidence stats
                confidence_stats = store.get_confidence_stats()

                result = {
                    "success": True,
                    "data": {
                        "total_patterns": len(store),
                        "degraded_count": len(regressions),
                        "degraded_patterns": regressions,
                        "confidence_stats": confidence_stats,
                    }
                }
            except Exception as e:
                import traceback
                result = {"success": False, "data": f"Regression check failed: {str(e)}", "traceback": traceback.format_exc()}

        case "gh_reflect":
            from rook.learning.gh_session_history import get_session_recorder
            from rook.learning.reflection import (
                detect_struggles,
                analyze_struggle,
                create_draft_pattern,
            )
            try:
                recorder = get_session_recorder()
                session_id = arguments.get("session_id")
                min_failures = arguments.get("min_failures", 2)
                use_dspy = arguments.get("use_dspy", True)

                # Get session entries
                if session_id:
                    # Load specific session from file
                    from rook.learning.gh_session_history import load_session
                    session_data = load_session(session_id)
                    if not session_data:
                        result = {"success": False, "data": f"Session not found: {session_id}"}
                    else:
                        entries = session_data.get("entries", [])
                        # Convert dicts to SessionEntry objects
                        from rook.learning.gh_session_history import SessionEntry
                        entries = [SessionEntry(**e) for e in entries]
                else:
                    # Use current session
                    current = await recorder.get_current()
                    if not current:
                        result = {"success": False, "data": "No active session"}
                    else:
                        session_id = current.get("session_id", "unknown")
                        # Get entries via get_history
                        from rook.learning.gh_session_history import SessionEntry
                        history = await recorder.get_history(offset=0, limit=10000)
                        entries = [SessionEntry(**e) for e in history.get("entries", [])]

                if "result" not in dir() or result is None:
                    # Detect struggles
                    struggles = detect_struggles(entries, min_failures=min_failures)

                    # Build drafts
                    drafts = []
                    for struggle in struggles:
                        reflection = analyze_struggle(struggle, use_dspy=use_dspy)
                        draft = create_draft_pattern(session_id, struggle, reflection)
                        drafts.append(draft)

                    # Store drafts in memory for gh_save_pattern
                    if not hasattr(recorder, "_draft_patterns"):
                        recorder._draft_patterns = {}
                    for draft in drafts:
                        recorder._draft_patterns[draft.draft_id] = draft

                    result = {
                        "success": True,
                        "data": {
                            "session_id": session_id,
                            "struggles_found": len(struggles),
                            "drafts": [d.to_dict() for d in drafts],
                            "message": (
                                f"Found {len(struggles)} learning opportunities. "
                                f"Use gh_save_pattern with draft_id to save patterns you want to keep."
                            ) if drafts else "No struggle sequences found in session."
                        }
                    }
            except Exception as e:
                import traceback
                result = {"success": False, "data": f"Reflection failed: {str(e)}", "traceback": traceback.format_exc()}

        case "gh_save_pattern":
            from rook.learning.gh_session_history import get_session_recorder
            from rook.learning.pattern_store import get_pattern_store
            try:
                draft_id = arguments.get("draft_id")
                modifications = arguments.get("modifications", {})

                if not draft_id:
                    result = {"success": False, "data": "Missing required parameter: draft_id"}
                else:
                    # Get draft from memory
                    recorder = get_session_recorder()
                    if not hasattr(recorder, "_draft_patterns") or draft_id not in recorder._draft_patterns:
                        result = {"success": False, "data": f"Draft not found: {draft_id}. Run gh_reflect first."}
                    else:
                        draft = recorder._draft_patterns[draft_id]
                        pattern = draft.pattern

                        # Apply modifications
                        if modifications.get("name"):
                            pattern.name = modifications["name"]
                        if modifications.get("solution_brief"):
                            pattern.solution_brief = modifications["solution_brief"]
                        if modifications.get("tags"):
                            pattern.tags = modifications["tags"]
                        if modifications.get("trigger_intents"):
                            pattern.trigger_intents = modifications["trigger_intents"]
                        if modifications.get("trigger_symptoms"):
                            pattern.trigger_symptoms = modifications["trigger_symptoms"]

                        # Save to pattern store
                        store = get_pattern_store()
                        store.add(pattern)

                        # Remove from drafts
                        del recorder._draft_patterns[draft_id]

                        result = {
                            "success": True,
                            "data": {
                                "pattern_id": pattern.pattern_id,
                                "pattern": pattern.to_dict(),
                                "message": f"Pattern '{pattern.name}' saved to memory. Available via gh_query_patterns."
                            }
                        }
            except Exception as e:
                import traceback
                result = {"success": False, "data": f"Save pattern failed: {str(e)}", "traceback": traceback.format_exc()}

        case "gh_extract_recipe":
            from rook.learning.recipe_extraction import extract_recipe
            from rook.learning.gh_session_history import get_session_recorder
            try:
                source_def = arguments.get("source_definition", "")
                use_dspy = arguments.get("use_dspy", True)

                # Get full canvas snapshot (replaces gh_query + N gh_connections calls)
                snapshot_result = await call_rhino("/gh/snapshot", "POST", {"include_data": False}, port=port)
                if not snapshot_result.get("success"):
                    result = {"success": False, "data": f"Failed to get canvas snapshot: {snapshot_result}"}
                else:
                    snapshot_data = snapshot_result.get("data", {})
                    components = snapshot_data.get("components", [])

                    if not components:
                        result = {"success": False, "data": "No components on canvas to extract recipe from"}
                    else:
                        # Extract v2 recipe from snapshot
                        draft = extract_recipe(
                            snapshot=snapshot_data,
                            source_definition=source_def,
                            use_dspy=use_dspy,
                        )

                        # Apply overrides
                        if arguments.get("name"):
                            draft.suggested_name = arguments["name"]
                        if arguments.get("description"):
                            draft.description = arguments["description"]

                        # Store draft for later saving
                        recorder = get_session_recorder()
                        if not hasattr(recorder, "_draft_recipes"):
                            recorder._draft_recipes = {}
                        recorder._draft_recipes[draft.draft_id] = draft

                        result = {
                            "success": True,
                            "data": draft.to_dict(),
                        }
            except Exception as e:
                import traceback
                result = {"success": False, "data": f"Recipe extraction failed: {str(e)}", "traceback": traceback.format_exc()}

        case "gh_save_recipe":
            from rook.learning.gh_session_history import get_session_recorder
            from rook.learning.pattern_store import get_pattern_store
            from rook.learning.pattern_memory import PatternNote
            try:
                draft_id = arguments.get("draft_id")
                modifications = arguments.get("modifications", {})

                if not draft_id:
                    result = {"success": False, "data": "Missing required parameter: draft_id"}
                else:
                    # Get draft from memory
                    recorder = get_session_recorder()
                    if not hasattr(recorder, "_draft_recipes") or draft_id not in recorder._draft_recipes:
                        result = {"success": False, "data": f"Draft not found: {draft_id}. Run gh_extract_recipe first."}
                    else:
                        draft = recorder._draft_recipes[draft_id]

                        # Validate name is not empty
                        recipe_name = modifications.get("name") or draft.suggested_name
                        if not recipe_name:
                            result = {"success": False, "data": "Recipe must have a name. Provide modifications.name or ensure draft has suggested_name."}
                        else:
                            # Create PatternNote from draft
                            pattern = PatternNote(
                                name=recipe_name,
                                pattern_type="recipe",
                                solution_brief=modifications.get("description", draft.description),
                                components_needed=[c.get("name") or c.get("nick") or c.get("type", "") for c in draft.components],
                                trigger_intents=modifications.get("intents", draft.suggested_intents),
                                tags=modifications.get("tags", draft.detected_tags),
                                wiring=draft.wiring,
                                input_structure=draft.input_structure,
                                output_type=draft.output_type,
                                source_definition=draft.source_definition,
                                created_from="recipe_extraction",
                                schema_version=draft.schema_version,
                                graph=draft.graph,
                            )

                            # Save to pattern store
                            store = get_pattern_store()
                            store.add(pattern)

                            # Remove draft from memory
                            del recorder._draft_recipes[draft_id]

                            result = {
                                "success": True,
                                "data": {
                                    "pattern_id": pattern.pattern_id,
                                    "name": pattern.name,
                                    "pattern": pattern.to_dict(),
                                    "message": f"Recipe saved! Searchable via gh_query_patterns with intents: {pattern.trigger_intents}"
                                }
                            }
            except Exception as e:
                import traceback
                result = {"success": False, "data": f"Recipe save failed: {str(e)}", "traceback": traceback.format_exc()}

        case "gh_learn_canvas":
            from rook.learning.canvas_learner import learn_from_canvas
            try:
                learn_result = await learn_from_canvas(
                    call_rhino,
                    port=port,
                    name=arguments.get("name", ""),
                    description=arguments.get("description", ""),
                    tags=arguments.get("tags", []),
                    skip_recipe=arguments.get("skip_recipe", False),
                )
                result = {
                    "success": learn_result.get("errors", 0) == 0,
                    "data": learn_result,
                }
            except Exception as e:
                import traceback
                result = {"success": False, "data": f"Canvas learning failed: {str(e)}", "traceback": traceback.format_exc()}

        case "gh_replay_recipe":
            from rook.learning.pattern_store import get_pattern_store
            from rook.learning.recipe_extraction import recipe_to_edit
            try:
                pattern_id = arguments.get("pattern_id", "")
                if not pattern_id:
                    result = {"success": False, "data": "Missing required parameter: pattern_id"}
                else:
                    offset_x = arguments.get("offset_x", 0)
                    offset_y = arguments.get("offset_y", 0)

                    # Load recipe from pattern store
                    store = get_pattern_store()
                    pattern = store.get(pattern_id)

                    if not pattern:
                        result = {"success": False, "data": f"Pattern '{pattern_id}' not found"}
                    elif pattern.schema_version != "2.0" or not pattern.graph:
                        result = {"success": False, "data": f"Pattern '{pattern_id}' is not a v2 recipe (schema_version={pattern.schema_version})"}
                    else:
                        # Convert recipe graph to gh_edit document
                        edit_doc = recipe_to_edit(pattern.graph, offset=(offset_x, offset_y))

                        # Get current epoch from snapshot
                        snapshot_result = await call_rhino("/gh/snapshot", "POST", {"include_data": False}, port=port)
                        if not snapshot_result.get("success"):
                            result = {"success": False, "data": "Failed to get current canvas epoch"}
                        else:
                            snapshot_data = snapshot_result.get("data", {})
                            epoch = snapshot_data.get("epoch", 0)
                            edit_doc["epoch"] = epoch

                            # Submit to gh_edit
                            result = await call_rhino("/gh/edit", "POST", edit_doc, port=port)

                            # Record to session history
                            if result.get("success"):
                                try:
                                    await _record_gh_to_session(
                                        action="gh_replay_recipe",
                                        params={
                                            "pattern_id": pattern_id,
                                            "pattern_name": pattern.name,
                                            "components_created_count": len(edit_doc.get("create", [])),
                                            "connections_made_count": len(edit_doc.get("connect", [])),
                                        },
                                        result=result,
                                        port=port,
                                        patterns_applied=[pattern_id],
                                    )
                                except Exception:
                                    pass  # Don't fail the replay if session recording fails
            except Exception as e:
                import traceback
                result = {"success": False, "data": f"Recipe replay failed: {str(e)}", "traceback": traceback.format_exc()}

        case "gh_migration_status":
            from rook.learning.pattern_store import get_pattern_store
            try:
                store = get_pattern_store()
                show_remaining = arguments.get("show_remaining", False)

                recipes = [p for p in store.patterns.values() if p.pattern_type == "recipe"]
                v1 = [p for p in recipes if p.schema_version != "2.0"]
                v2 = [p for p in recipes if p.schema_version == "2.0"]

                data = {
                    "total_recipes": len(recipes),
                    "v1_count": len(v1),
                    "v2_count": len(v2),
                    "progress_pct": round(len(v2) / max(len(recipes), 1) * 100, 1),
                }

                if show_remaining:
                    data["remaining"] = [
                        {"id": p.pattern_id, "name": p.name, "source": p.source_definition}
                        for p in sorted(v1, key=lambda x: x.name)
                    ]

                result = {"success": True, "data": data}
            except Exception as e:
                import traceback
                result = {"success": False, "data": f"Migration status failed: {str(e)}", "traceback": traceback.format_exc()}

        case "gh_upgrade_recipe":
            from rook.learning.pattern_store import get_pattern_store
            from rook.learning.recipe_extraction import extract_recipe_v2, merge_v2_into_pattern
            import copy
            try:
                pattern_id = arguments.get("pattern_id", "")
                if not pattern_id:
                    result = {"success": False, "data": "Missing required parameter: pattern_id"}
                else:
                    store = get_pattern_store()
                    pattern = store.get(pattern_id)

                    if not pattern:
                        result = {"success": False, "data": f"Pattern '{pattern_id}' not found"}
                    elif pattern.pattern_type != "recipe":
                        result = {"success": False, "data": f"Pattern '{pattern_id}' is not a recipe (type={pattern.pattern_type})"}
                    elif pattern.schema_version == "2.0":
                        result = {"success": False, "data": f"Pattern '{pattern_id}' is already v2 (schema_version=2.0)"}
                    else:
                        old_component_count = len(pattern.components_needed)

                        # Snapshot current canvas
                        snapshot_result = await call_rhino("/gh/snapshot", "POST", {"include_data": False}, port=port)
                        if not snapshot_result.get("success"):
                            result = {"success": False, "data": f"Failed to get canvas snapshot: {snapshot_result}"}
                        else:
                            snapshot_data = snapshot_result.get("data", {})
                            components = snapshot_data.get("components", [])

                            if not components:
                                result = {"success": False, "data": "No components on canvas. Open the source .gh file first."}
                            else:
                                # Extract v2 from snapshot (skip DSPy — we keep existing metadata)
                                draft = extract_recipe_v2(snapshot_data, source_definition=pattern.source_definition, use_dspy=False)

                                # Work on a copy so store stays consistent if update() fails
                                upgraded = copy.deepcopy(pattern)

                                # Merge: replace only recipe fields (shared with tests)
                                merge_v2_into_pattern(upgraded, draft)

                                # Add evolution entry
                                from datetime import datetime
                                upgraded.evolution_history.append({
                                    "date": datetime.utcnow().isoformat() + "Z",
                                    "trigger": "v2_migration",
                                    "changes": f"Upgraded from v1 wiring to v2 graph format. Components: {old_component_count} -> {len(draft.components)}, Flows: {len(draft.graph.get('flows', []))}",
                                })

                                # Save back (same pattern_id, overwrites)
                                store.update(upgraded)

                                result = {
                                    "success": True,
                                    "data": {
                                        "pattern_id": upgraded.pattern_id,
                                        "name": upgraded.name,
                                        "old_component_count": old_component_count,
                                        "new_component_count": len(draft.components),
                                        "flow_count": len(draft.graph.get("flows", [])),
                                        "links_preserved": len(upgraded.links),
                                        "schema_version": "2.0",
                                        "message": f"Upgraded '{upgraded.name}' to v2. {len(upgraded.links)} links preserved.",
                                    },
                                }
            except Exception as e:
                import traceback
                result = {"success": False, "data": f"Recipe upgrade failed: {str(e)}", "traceback": traceback.format_exc()}

        case "gh_explore_component":
            from rook.learning.gh_knowledge import gh_build_knowledge, gh_reload_knowledge

            guid = arguments.get("guid")
            instance_guid = arguments.get("instanceGuid")
            save = arguments.get("save", True)
            comp_result = None

            try:
                # Step 1: Get or create component on canvas
                if instance_guid:
                    # Use existing component
                    comp_result = await call_rhino("/gh/component", "GET", {"guid": instance_guid}, port=port)
                elif guid:
                    # Create component first
                    create_result = await call_rhino("/gh/create-component", "POST", {"guid": guid, "x": 100, "y": 100}, port=port)
                    if not create_result.get("success"):
                        result = {"success": False, "data": f"Failed to create component: {create_result.get('data')}"}
                    else:
                        # Note: Response uses lowercase "guid" for instance GUID
                        instance_guid = create_result.get("data", {}).get("guid")
                        comp_result = await call_rhino("/gh/component", "GET", {"guid": instance_guid}, port=port)
                else:
                    result = {"success": False, "data": "Must provide either guid or instanceGuid"}

                if comp_result and comp_result.get("success"):
                    component_info = comp_result.get("data", {})

                    # Map PascalCase keys from C# to camelCase for gh_build_knowledge
                    if "Category" in component_info and "category" not in component_info:
                        component_info["category"] = component_info["Category"]
                    if "SubCategory" in component_info and "subCategory" not in component_info:
                        component_info["subCategory"] = component_info["SubCategory"]
                    if "NickName" in component_info and "nickName" not in component_info:
                        component_info["nickName"] = component_info["NickName"]

                    # Step 1b: Enrich with description from batch-component-info (proxy metadata)
                    if guid:
                        try:
                            batch_resp = await call_rhino(
                                "/gh/batch-component-info", "POST",
                                {"guids": [guid]}, port=port
                            )
                            if batch_resp.get("success"):
                                batch_results = batch_resp.get("data", {}).get("Results", [])
                                if batch_results and not batch_results[0].get("Error"):
                                    proxy_data = batch_results[0]
                                    component_info["description"] = proxy_data.get("Description", "")
                                    component_info["sdk_category"] = proxy_data.get("Category", "")
                                    component_info["sdk_subcategory"] = proxy_data.get("SubCategory", "")
                        except Exception:
                            pass  # Description enrichment is best-effort

                    # Step 2: Build knowledge entry (pass original component GUID, not instance GUID)
                    build_result = gh_build_knowledge(component_info, component_guid=guid, save=save)

                    # Step 3: Reload knowledge if saved
                    if save and build_result.get("saved"):
                        gh_reload_knowledge()

                    result = {
                        "success": True,
                        "data": {
                            "message": f"Explored {build_result['entry'].get('name')} - {'saved to knowledge' if build_result.get('saved') else 'not saved'}",
                            "guid": build_result.get("guid"),
                            "entry": build_result.get("entry"),
                            "saved": build_result.get("saved"),
                            "source": "knowledge" if build_result.get("saved") else "exploration"
                        }
                    }
                elif comp_result:
                    result = {"success": False, "data": f"Failed to get component info: {comp_result.get('data')}"}

            except Exception as e:
                result = {"success": False, "data": f"Exploration failed: {str(e)}"}

        case "gh_explore_deep":
            from rook.learning.gh_knowledge import gh_build_knowledge, gh_reload_knowledge, get_knowledge_builder

            component_guid = arguments.get("guid")
            save = arguments.get("save", True)
            cleanup = arguments.get("cleanup", True)

            if not component_guid:
                result = {"success": False, "data": "Missing required parameter: guid"}
            else:
                created_objects = []  # Track for cleanup
                exploration_data = {
                    "guid": component_guid,
                    "params": {},
                    "data_structures": {},
                    "contexts": {},
                    "errors": [],
                    "runtime_messages": [],
                }

                try:
                    # Helper to unwrap responses - some endpoints wrap with {success, data}, some don't
                    def unwrap(resp: dict) -> dict:
                        if "success" in resp and "data" in resp:
                            return resp.get("data", {})
                        return resp

                    # Step 1: Create the component
                    base_x, base_y = 300, 200
                    raw_result = await call_rhino("/gh/create-component", "POST", {
                        "guid": component_guid, "x": base_x, "y": base_y
                    }, port=port)
                    create_result = unwrap(raw_result)

                    if not create_result.get("created"):
                        result = {"success": False, "data": f"Failed to create component: {create_result}"}
                    else:
                        instance_guid = create_result.get("guid")
                        created_objects.append(instance_guid)
                        comp_info = create_result
                        comp_name = comp_info.get("name", "Unknown")

                        # Step 2: Extract params from create response
                        params_data = comp_info.get("params", {})
                        input_list = params_data.get("inputs", [])
                        output_list = params_data.get("outputs", [])

                        # Build params dict
                        inputs = {}
                        outputs = {}
                        for p in input_list:
                            nick = p.get("nickName", p.get("name", "?"))
                            inputs[nick] = p.get("typeName", "")
                        for p in output_list:
                            nick = p.get("nickName", p.get("name", "?"))
                            outputs[nick] = p.get("typeName", "")
                        exploration_data["params"] = {"inputs": inputs, "outputs": outputs}

                        # Step 3: Create test inputs based on param types
                        input_x = base_x - 200
                        wired_inputs = []
                        for i, param in enumerate(input_list):
                            nick = param.get("nickName", "")
                            type_name = param.get("typeName", "").lower()
                            input_y = base_y + (i * 80)
                            print(f"DEBUG: Processing input {i}: nick='{nick}', type_name='{type_name}'")

                            # Create appropriate input based on type
                            # NOTE: Check point BEFORE int because "point" contains "int"
                            if "point" in type_name:
                                # Create Construct Point with sliders for X, Y, Z
                                # Use offset values for multiple point inputs (0, 5, 10, etc.)
                                point_offset = i * 5  # Offset each point

                                # Create Construct Point component
                                pt_result = unwrap(await call_rhino("/gh/create-component", "POST", {
                                    "guid": "3581f42a-9592-4549-bd6b-1c0fc39d067b",  # Construct Point
                                    "x": input_x - 100, "y": input_y
                                }, port=port))
                                if pt_result.get("created"):
                                    pt_guid = pt_result.get("guid")
                                    created_objects.append(pt_guid)

                                    # Create sliders for X, Y, Z with offset values
                                    for coord_idx, (coord_name, coord_val) in enumerate([("X", point_offset), ("Y", 0), ("Z", 0)]):
                                        coord_slider = unwrap(await call_rhino("/gh/create-slider", "POST", {
                                            "value": coord_val, "min": -10, "max": 20,
                                            "x": input_x - 250, "y": input_y + (coord_idx * 30)
                                        }, port=port))
                                        if coord_slider.get("created"):
                                            coord_slider_guid = coord_slider.get("guid")
                                            created_objects.append(coord_slider_guid)
                                            await call_rhino("/gh/connect", "POST", {
                                                "sourceGuid": coord_slider_guid,
                                                "targetGuid": pt_guid,
                                                "targetParam": coord_name
                                            }, port=port)

                                    # Wire Construct Point to target
                                    wire_result = unwrap(await call_rhino("/gh/connect", "POST", {
                                        "sourceGuid": pt_guid,
                                        "sourceParam": "Pt",
                                        "targetGuid": instance_guid,
                                        "targetParam": nick
                                    }, port=port))
                                    if wire_result.get("connected"):
                                        wired_inputs.append({"param": nick, "type": "point", "guid": pt_guid})

                            elif "plane" in type_name:
                                # Create XY Plane component (no inputs needed)
                                plane_result = unwrap(await call_rhino("/gh/create-component", "POST", {
                                    "guid": "17b7152b-d30d-4d50-b9ef-c9fe25576fc2",  # XY Plane
                                    "x": input_x, "y": input_y
                                }, port=port))
                                if plane_result.get("created"):
                                    plane_guid = plane_result.get("guid")
                                    created_objects.append(plane_guid)

                                    # Wire XY Plane to target
                                    wire_result = unwrap(await call_rhino("/gh/connect", "POST", {
                                        "sourceGuid": plane_guid,
                                        "sourceParam": "P",
                                        "targetGuid": instance_guid,
                                        "targetParam": nick
                                    }, port=port))
                                    if wire_result.get("connected"):
                                        wired_inputs.append({"param": nick, "type": "plane", "guid": plane_guid})

                            elif "vector" in type_name:
                                # Create Unit Z component with factor slider
                                print(f"DEBUG: Creating Unit Z for vector input '{nick}', type_name='{type_name}'")
                                vec_result = unwrap(await call_rhino("/gh/create-component", "POST", {
                                    "guid": "9103c240-a6a9-4223-9b42-dbd19bf38e2b",  # Unit Z
                                    "x": input_x, "y": input_y
                                }, port=port))
                                print(f"DEBUG: vec_result = {vec_result}")
                                if vec_result.get("created"):
                                    vec_guid = vec_result.get("guid")
                                    created_objects.append(vec_guid)

                                    # Create slider for factor
                                    factor_slider = unwrap(await call_rhino("/gh/create-slider", "POST", {
                                        "value": 1, "min": 0, "max": 10,
                                        "x": input_x - 150, "y": input_y
                                    }, port=port))
                                    if factor_slider.get("created"):
                                        factor_guid = factor_slider.get("guid")
                                        created_objects.append(factor_guid)
                                        await call_rhino("/gh/connect", "POST", {
                                            "sourceGuid": factor_guid,
                                            "targetGuid": vec_guid,
                                            "targetParam": "F"
                                        }, port=port)

                                    # Wire Unit Z to target
                                    wire_result = unwrap(await call_rhino("/gh/connect", "POST", {
                                        "sourceGuid": vec_guid,
                                        "sourceParam": "V",
                                        "targetGuid": instance_guid,
                                        "targetParam": nick
                                    }, port=port))
                                    if wire_result.get("connected"):
                                        wired_inputs.append({"param": nick, "type": "vector", "guid": vec_guid})

                            elif "domain" in type_name:
                                # Create Construct Domain component with sliders for A (start) and B (end)
                                print(f"DEBUG: Creating Construct Domain for domain input '{nick}', type_name='{type_name}'")
                                dom_result = unwrap(await call_rhino("/gh/create-component", "POST", {
                                    "guid": "d1a28e95-cf96-4936-bf34-8bf142d731bf",  # Construct Domain
                                    "x": input_x, "y": input_y
                                }, port=port))
                                print(f"DEBUG: dom_result = {dom_result}")
                                if dom_result.get("created"):
                                    dom_guid = dom_result.get("guid")
                                    created_objects.append(dom_guid)

                                    # Create sliders for A (start=0) and B (end=10)
                                    for dom_idx, (dom_name, dom_val) in enumerate([("A", 0), ("B", 10)]):
                                        dom_slider = unwrap(await call_rhino("/gh/create-slider", "POST", {
                                            "value": dom_val, "min": -10, "max": 20,
                                            "x": input_x - 150, "y": input_y + (dom_idx * 30)
                                        }, port=port))
                                        if dom_slider.get("created"):
                                            dom_slider_guid = dom_slider.get("guid")
                                            created_objects.append(dom_slider_guid)
                                            await call_rhino("/gh/connect", "POST", {
                                                "sourceGuid": dom_slider_guid,
                                                "targetGuid": dom_guid,
                                                "targetParam": dom_name
                                            }, port=port)

                                    # Wire Construct Domain to target
                                    wire_result = unwrap(await call_rhino("/gh/connect", "POST", {
                                        "sourceGuid": dom_guid,
                                        "sourceParam": "I",
                                        "targetGuid": instance_guid,
                                        "targetParam": nick
                                    }, port=port))
                                    if wire_result.get("connected"):
                                        wired_inputs.append({"param": nick, "type": "domain", "guid": dom_guid})

                            elif "number" in type_name or "integer" in type_name:
                                # Create slider for number/integer inputs
                                slider_result = unwrap(await call_rhino("/gh/create-slider", "POST", {
                                    "value": 5, "min": 0, "max": 10,
                                    "x": input_x, "y": input_y
                                }, port=port))
                                if slider_result.get("created"):
                                    slider_guid = slider_result.get("guid")
                                    created_objects.append(slider_guid)
                                    # Wire it
                                    wire_result = unwrap(await call_rhino("/gh/connect", "POST", {
                                        "sourceGuid": slider_guid,
                                        "targetGuid": instance_guid,
                                        "targetParam": nick
                                    }, port=port))
                                    if wire_result.get("connected"):
                                        wired_inputs.append({"param": nick, "type": "slider", "guid": slider_guid})

                            elif "bool" in type_name:
                                # Create Boolean Toggle for boolean inputs
                                print(f"DEBUG: Creating Boolean Toggle for boolean input '{nick}', type_name='{type_name}'")
                                toggle_result = unwrap(await call_rhino("/gh/create-component", "POST", {
                                    "guid": "2e78987b-9dfb-42a2-8b76-3923ac8bd91a",  # Boolean Toggle
                                    "x": input_x, "y": input_y
                                }, port=port))
                                if toggle_result.get("created"):
                                    toggle_guid = toggle_result.get("guid")
                                    created_objects.append(toggle_guid)
                                    # Wire it
                                    wire_result = unwrap(await call_rhino("/gh/connect", "POST", {
                                        "sourceGuid": toggle_guid,
                                        "targetGuid": instance_guid,
                                        "targetParam": nick
                                    }, port=port))
                                    if wire_result.get("connected"):
                                        wired_inputs.append({"param": nick, "type": "boolean", "guid": toggle_guid})

                            elif "curve" in type_name:
                                # Create Circle component as test curve input
                                print(f"DEBUG: Creating Circle for curve input '{nick}', type_name='{type_name}'")
                                circle_result = unwrap(await call_rhino("/gh/create-component", "POST", {
                                    "guid": "807b86e3-be8d-4970-92b5-f8cdcb45b06b",  # Circle (Curve/Primitive)
                                    "x": input_x, "y": input_y
                                }, port=port))
                                if circle_result.get("created"):
                                    circle_guid = circle_result.get("guid")
                                    created_objects.append(circle_guid)
                                    # Wire Circle output C to target
                                    wire_result = unwrap(await call_rhino("/gh/connect", "POST", {
                                        "sourceGuid": circle_guid,
                                        "sourceParam": "C",
                                        "targetGuid": instance_guid,
                                        "targetParam": nick
                                    }, port=port))
                                    if wire_result.get("connected"):
                                        wired_inputs.append({"param": nick, "type": "curve", "guid": circle_guid})

                            elif "surface" in type_name:
                                # Create Sphere component as test surface input
                                print(f"DEBUG: Creating Sphere for surface input '{nick}', type_name='{type_name}'")
                                sphere_result = unwrap(await call_rhino("/gh/create-component", "POST", {
                                    "guid": "dabc854d-f50e-408a-b001-d043c7de151d",  # Sphere (Surface/Primitive)
                                    "x": input_x, "y": input_y
                                }, port=port))
                                if sphere_result.get("created"):
                                    sphere_guid = sphere_result.get("guid")
                                    created_objects.append(sphere_guid)
                                    # Wire Sphere output S to target
                                    wire_result = unwrap(await call_rhino("/gh/connect", "POST", {
                                        "sourceGuid": sphere_guid,
                                        "sourceParam": "S",
                                        "targetGuid": instance_guid,
                                        "targetParam": nick
                                    }, port=port))
                                    if wire_result.get("connected"):
                                        wired_inputs.append({"param": nick, "type": "surface", "guid": sphere_guid})

                            elif "brep" in type_name:
                                # Create Quad Sphere (closed brep) as test brep input
                                print(f"DEBUG: Creating Quad Sphere for brep input '{nick}', type_name='{type_name}'")
                                qsphere_result = unwrap(await call_rhino("/gh/create-component", "POST", {
                                    "guid": "361790d6-9d66-4808-8c5a-8de9c218c227",  # Quad Sphere (closed brep)
                                    "x": input_x, "y": input_y
                                }, port=port))
                                if qsphere_result.get("created"):
                                    qsphere_guid = qsphere_result.get("guid")
                                    created_objects.append(qsphere_guid)
                                    # Wire Quad Sphere output S to target
                                    wire_result = unwrap(await call_rhino("/gh/connect", "POST", {
                                        "sourceGuid": qsphere_guid,
                                        "sourceParam": "S",
                                        "targetGuid": instance_guid,
                                        "targetParam": nick
                                    }, port=port))
                                    if wire_result.get("connected"):
                                        wired_inputs.append({"param": nick, "type": "brep", "guid": qsphere_guid})

                            elif "geometry" in type_name or "goo" in type_name:
                                # Create Circle as generic geometry input (curves are commonly accepted)
                                print(f"DEBUG: Creating Circle for geometry input '{nick}', type_name='{type_name}'")
                                geom_result = unwrap(await call_rhino("/gh/create-component", "POST", {
                                    "guid": "807b86e3-be8d-4970-92b5-f8cdcb45b06b",  # Circle (generic geometry)
                                    "x": input_x, "y": input_y
                                }, port=port))
                                if geom_result.get("created"):
                                    geom_guid = geom_result.get("guid")
                                    created_objects.append(geom_guid)
                                    # Wire Circle output C to target
                                    wire_result = unwrap(await call_rhino("/gh/connect", "POST", {
                                        "sourceGuid": geom_guid,
                                        "sourceParam": "C",
                                        "targetGuid": instance_guid,
                                        "targetParam": nick
                                    }, port=port))
                                    if wire_result.get("connected"):
                                        wired_inputs.append({"param": nick, "type": "geometry", "guid": geom_guid})

                        # Step 4: Solve and inspect outputs
                        await call_rhino("/gh/solve", "POST", {}, port=port)
                        await asyncio.sleep(0.3)  # Wait for solution to complete

                        # Inspect each output
                        for param in output_list:
                            nick = param.get("nickName", "")
                            inspect_result = unwrap(await call_rhino("/gh/inspect-output", "GET", {
                                "guid": instance_guid, "param": nick
                            }, port=port))
                            if inspect_result.get("param_name") or inspect_result.get("structure"):
                                exploration_data["data_structures"][nick] = {
                                    "structure": inspect_result.get("structure", "unknown"),
                                    "path_count": inspect_result.get("path_count", 0),
                                    "data_count": inspect_result.get("data_count", 0),
                                }

                        # Step 5: Test with list input (Series) if we wired a slider
                        if wired_inputs:
                            # Find a wired slider
                            slider_info = next((w for w in wired_inputs if w["type"] == "slider"), None)
                            if slider_info:
                                # Create Series to replace slider
                                series_result = unwrap(await call_rhino("/gh/create-component", "POST", {
                                    "guid": "e64c5fb1-845c-4ab1-8911-5f338516ba67",  # Series GUID
                                    "x": input_x - 100, "y": base_y
                                }, port=port))
                                if series_result.get("created"):
                                    series_guid = series_result.get("guid")
                                    created_objects.append(series_guid)

                                    # Disconnect slider, connect series
                                    await call_rhino("/gh/disconnect", "POST", {
                                        "sourceGuid": slider_info["guid"],
                                        "targetGuid": instance_guid,
                                        "targetParam": slider_info["param"]
                                    }, port=port)
                                    await call_rhino("/gh/connect", "POST", {
                                        "sourceGuid": series_guid,
                                        "sourceParam": "S",
                                        "targetGuid": instance_guid,
                                        "targetParam": slider_info["param"]
                                    }, port=port)

                                    # Solve again
                                    await call_rhino("/gh/solve", "POST", {}, port=port)
                                    await asyncio.sleep(0.3)  # Wait for solution to complete

                                    # Inspect output with list input
                                    for param in output_list:
                                        nick = param.get("nickName", "")
                                        inspect_result = unwrap(await call_rhino("/gh/inspect-output", "GET", {
                                            "guid": instance_guid, "param": nick
                                        }, port=port))
                                        if inspect_result.get("param_name") or inspect_result.get("structure"):
                                            list_structure = inspect_result.get("structure", "unknown")
                                            # Record list behavior context
                                            single_structure = exploration_data["data_structures"].get(nick, {}).get("structure", "unknown")
                                            if single_structure == "single" and list_structure == "list":
                                                exploration_data["contexts"]["list_behavior"] = f"Broadcasts: single input → single output, list input → list output"
                                            elif single_structure == "single" and list_structure == "single":
                                                exploration_data["contexts"]["list_behavior"] = f"Does not broadcast: list input produces single output (aggregates)"

                        # Step 6: Get runtime messages via gh_errors (more reliable than runtimeMessages)
                        errors_response = unwrap(await call_rhino("/gh/errors", "GET", {}, port=port))
                        if errors_response:
                            # Find errors/warnings for our specific component
                            all_errors = errors_response.get("errors", []) + errors_response.get("warnings", [])
                            for comp_entry in all_errors:
                                if comp_entry.get("guid") == instance_guid:
                                    # Found our component - extract messages
                                    comp_errors = comp_entry.get("errors", [])
                                    comp_warnings = comp_entry.get("warnings", [])
                                    if comp_errors or comp_warnings:
                                        exploration_data["runtime_messages"] = {
                                            "Errors": comp_errors,
                                            "Warnings": comp_warnings
                                        }
                                    break

                        # Step 7: Build rich knowledge entry
                        builder = get_knowledge_builder()

                        # Determine family
                        comp_type = comp_info.get("type", "").lower()
                        if "sphere" in comp_type or "cylinder" in comp_type or "cone" in comp_type or "box" in comp_type:
                            family = "primitives"
                        elif "slider" in comp_type or "panel" in comp_type:
                            family = "input"
                        elif "addition" in comp_type or "subtraction" in comp_type or "multiplication" in comp_type:
                            family = "math"
                        elif "curve" in comp_type or "line" in comp_type or "circle" in comp_type:
                            family = "curves"
                        elif "loft" in comp_type or "sweep" in comp_type or "extrude" in comp_type:
                            family = "surface_ops"
                        elif "graft" in comp_type or "flatten" in comp_type:
                            family = "tree_operations"
                        else:
                            family = "unknown"

                        # Build quick description
                        input_names = list(inputs.keys())[:3]
                        output_names = list(outputs.keys())[:2]
                        quick = f"{comp_name} | {', '.join(input_names)} → {', '.join(output_names)}"

                        # Build contexts from exploration
                        contexts = {}
                        if exploration_data["contexts"].get("list_behavior"):
                            contexts["data_flow"] = exploration_data["contexts"]["list_behavior"]

                        # Add data structure info to contexts
                        structures = exploration_data["data_structures"]
                        if structures:
                            struct_desc = ", ".join([f"{k}: {v.get('structure', '?')}" for k, v in structures.items()])
                            contexts["output_structure"] = f"Default output: {struct_desc}"

                        # Build errors string from runtime messages
                        errors_str = None
                        if exploration_data.get("runtime_messages"):
                            msgs = exploration_data["runtime_messages"]
                            error_list = msgs.get("Errors", []) if isinstance(msgs, dict) else []
                            warning_list = msgs.get("Warnings", []) if isinstance(msgs, dict) else []
                            all_msgs = []
                            if error_list:
                                all_msgs.extend([f"ERROR: {e}" for e in error_list])
                            if warning_list:
                                all_msgs.extend([f"WARNING: {w}" for w in warning_list])
                            if all_msgs:
                                errors_str = " | ".join(all_msgs)

                        entry = builder.build_entry(
                            guid=component_guid,
                            name=comp_name,
                            family=family,
                            params=exploration_data["params"],
                            quick=quick,
                            contexts=contexts if contexts else None,
                            errors=errors_str,
                        )

                        # Save if requested
                        saved = False
                        if save:
                            saved = builder.save_entry(component_guid, entry)
                            builder.ensure_sparse_entry(
                                guid=component_guid,
                                name=comp_name,
                                family=family,
                                nickName=comp_info.get("nickName", comp_name[:6])
                            )
                            if saved:
                                gh_reload_knowledge()

                        # Step 8: Cleanup if requested
                        if cleanup and created_objects:
                            for obj_guid in created_objects:
                                await call_rhino("/gh/delete", "POST", {"guids": [obj_guid]}, port=port)

                        result = {
                            "success": True,
                            "data": {
                                "message": f"Deep explored {comp_name} - {'saved to knowledge' if saved else 'not saved'}",
                                "guid": component_guid,
                                "entry": entry,
                                "exploration": {
                                    "inputs_wired": len(wired_inputs),
                                    "outputs_inspected": len(exploration_data["data_structures"]),
                                    "contexts_discovered": len(contexts),
                                    "list_behavior_tested": "list_behavior" in exploration_data["contexts"],
                                },
                                "saved": saved,
                            }
                        }

                except Exception as e:
                    # Cleanup on error
                    if cleanup and created_objects:
                        for obj_guid in created_objects:
                            try:
                                await call_rhino("/gh/delete", "POST", {"guids": [obj_guid]}, port=port)
                            except:
                                pass
                    result = {"success": False, "data": f"Deep exploration failed: {str(e)}"}

        case "gh_investigate":
            # Hypothesis-driven investigation for self-reflective learning
            import uuid
            from datetime import datetime
            from pathlib import Path

            component_guid = arguments.get("guid")
            hypothesis = arguments.get("hypothesis", "")
            config = arguments.get("config", {})
            intent = arguments.get("intent", "")
            attempt = arguments.get("attempt", 1)
            previous_obs_id = arguments.get("previousObservationId")
            cleanup = arguments.get("cleanup", True)

            # Validate hypothesis is meaningful
            if not hypothesis or len(hypothesis.strip()) < 10:
                result = {
                    "success": False,
                    "data": "hypothesis must be meaningful (at least 10 chars). Explain WHY this config might work."
                }
            elif not component_guid:
                result = {"success": False, "data": "Missing required parameter: guid"}
            elif not config:
                result = {"success": False, "data": "Missing required parameter: config"}
            elif not intent:
                result = {"success": False, "data": "Missing required parameter: intent"}
            else:
                try:
                    # Load observations file
                    obs_file = resolve_writable_knowledge_path("gh", "gh_observations.json")
                    obs_read_path = obs_file if obs_file.exists() else resolve_readable_knowledge_path("gh", "gh_observations.json")

                    if obs_read_path.exists():
                        with open(obs_read_path, "r") as f:
                            observations_data = json.load(f)
                    else:
                        observations_data = {
                            "version": "1.0",
                            "description": "Investigation observations for GH components",
                            "observations": {}
                        }

                    # Generate observation ID
                    obs_id = f"gh_obs_{uuid.uuid4().hex[:12]}"

                    # Get component info from library
                    lib_result = await call_rhino("/gh/library", "POST", {"search": component_guid}, port=port)
                    component_name = "Unknown"
                    if lib_result.get("components"):
                        for comp in lib_result["components"]:
                            if comp.get("guid") == component_guid:
                                component_name = comp.get("name", "Unknown")
                                break

                    # Create session ID based on date and component
                    session_id = f"{component_name.lower()}_investigation_{datetime.now().strftime('%Y%m%d')}"

                    created_objects = []

                    # Create the component
                    create_result = await call_rhino("/gh/create-component", "POST", {
                        "guid": component_guid,
                        "x": 300,
                        "y": 100
                    }, port=port)

                    # Response may have "created" or "success", and guid may be at top level or in "data"
                    is_created = create_result.get("created") or create_result.get("success")
                    comp_instance = create_result.get("guid") or (create_result.get("data", {}).get("guid") if isinstance(create_result.get("data"), dict) else None)

                    if not is_created or not comp_instance:
                        result = {"success": False, "data": f"Failed to create component: {create_result}"}
                    else:
                        created_objects.append(comp_instance)

                        # Get component details for wiring (use GET with guid query param)
                        comp_details_raw = await call_rhino("/gh/component", "GET", {"guid": comp_instance}, port=port)
                        # Unwrap the {"success": ..., "data": ...} structure - always take data if present
                        if "data" in comp_details_raw and isinstance(comp_details_raw["data"], dict):
                            comp_details = comp_details_raw["data"]
                        elif "data" in comp_details_raw:
                            # data might be an error string
                            comp_details = {"error": comp_details_raw["data"]}
                        else:
                            comp_details = comp_details_raw
                        # Use nickName as key since that's what users typically use (E, C, R, etc.)
                        # Note: key is "inputs" (plural)
                        input_list = comp_details.get("params", {}).get("inputs", []) if isinstance(comp_details, dict) else []
                        inputs = {p.get("nickName", p.get("name", "")): p for p in input_list}

                        # Debug info
                        debug_info = {
                            "comp_instance": comp_instance,
                            "comp_details_raw_data": str(comp_details_raw.get("data", "N/A"))[:200],
                            "comp_details_keys": list(comp_details.keys()) if isinstance(comp_details, dict) else str(type(comp_details)),
                            "input_list_len": len(input_list),
                            "inputs_keys": list(inputs.keys()),
                            "config_keys": list(config.keys())
                        }

                        wired_inputs = []
                        input_values = {}

                        # Wire inputs according to config
                        for param_name, param_config in config.items():
                            if param_name not in inputs:
                                continue

                            param_type = param_config.get("type", "").lower()
                            value = param_config.get("value")
                            source_guid = param_config.get("source_guid")

                            # If source_guid provided, connect directly
                            if source_guid:
                                await call_rhino("/gh/connect", "POST", {
                                    "sourceGuid": source_guid,
                                    "targetGuid": comp_instance,
                                    "targetParam": param_name
                                }, port=port)
                                wired_inputs.append(param_name)
                                input_values[param_name] = {"source": source_guid}
                            else:
                                # Create source component based on type
                                source_x = 100
                                source_y = 100 + len(created_objects) * 80

                                if param_type in ("integer", "int"):
                                    slider = await call_rhino("/gh/create-slider", "POST", {
                                        "nickname": param_name,
                                        "min": value - 10 if value is not None else -10,
                                        "max": value + 10 if value is not None else 10,
                                        "value": value if value is not None else 0,
                                        "type": "integer",
                                        "x": source_x, "y": source_y
                                    }, port=port)
                                    # Extract guid - may be at top level or in "data"
                                    slider_guid = slider.get("guid") or (slider.get("data", {}).get("guid") if isinstance(slider.get("data"), dict) else None)
                                    debug_info["slider_response"] = str(slider)[:300]
                                    debug_info["slider_guid"] = slider_guid
                                    if slider_guid:
                                        created_objects.append(slider_guid)
                                        connect_result = await call_rhino("/gh/connect", "POST", {
                                            "sourceGuid": slider_guid,
                                            "targetGuid": comp_instance,
                                            "targetParam": param_name
                                        }, port=port)
                                        debug_info["connect_result"] = str(connect_result)[:300]
                                        wired_inputs.append(param_name)
                                        input_values[param_name] = {"type": "integer", "value": value}

                                elif param_type in ("number", "float", "double"):
                                    slider = await call_rhino("/gh/create-slider", "POST", {
                                        "nickname": param_name,
                                        "min": value - 10 if value is not None else -10,
                                        "max": value + 10 if value is not None else 10,
                                        "value": value if value is not None else 0,
                                        "type": "float",
                                        "x": source_x, "y": source_y
                                    }, port=port)
                                    # Extract guid - may be at top level or in "data"
                                    slider_guid = slider.get("guid") or (slider.get("data", {}).get("guid") if isinstance(slider.get("data"), dict) else None)
                                    if slider_guid:
                                        created_objects.append(slider_guid)
                                        await call_rhino("/gh/connect", "POST", {
                                            "sourceGuid": slider_guid,
                                            "targetGuid": comp_instance,
                                            "targetParam": param_name
                                        }, port=port)
                                        wired_inputs.append(param_name)
                                        input_values[param_name] = {"type": "number", "value": value}

                                elif param_type == "boolean":
                                    panel = await call_rhino("/gh/create-panel", "POST", {
                                        "content": "true" if value else "false",
                                        "x": source_x, "y": source_y
                                    }, port=port)
                                    # Extract guid - may be at top level or in "data"
                                    panel_guid = panel.get("guid") or (panel.get("data", {}).get("guid") if isinstance(panel.get("data"), dict) else None)
                                    if panel_guid:
                                        created_objects.append(panel_guid)
                                        await call_rhino("/gh/connect", "POST", {
                                            "sourceGuid": panel_guid,
                                            "targetGuid": comp_instance,
                                            "targetParam": param_name
                                        }, port=port)
                                        wired_inputs.append(param_name)
                                        input_values[param_name] = {"type": "boolean", "value": value}

                                elif param_type == "curve":
                                    # Create Circle as curve source
                                    circle = await call_rhino("/gh/create-component", "POST", {
                                        "guid": "807b86e3-be8d-4970-92b5-f8cdcb45b06b",  # Circle (Curve > Primitive)
                                        "x": source_x, "y": source_y
                                    }, port=port)
                                    # Extract guid - may be at top level or in "data"
                                    circle_guid = circle.get("guid") or (circle.get("data", {}).get("guid") if isinstance(circle.get("data"), dict) else None)
                                    debug_info["circle_response"] = str(circle)[:300]
                                    debug_info["circle_guid"] = circle_guid
                                    if circle_guid:
                                        created_objects.append(circle_guid)
                                        circle_connect = await call_rhino("/gh/connect", "POST", {
                                            "sourceGuid": circle_guid,
                                            "sourceParam": "C",
                                            "targetGuid": comp_instance,
                                            "targetParam": param_name
                                        }, port=port)
                                        debug_info["circle_connect_result"] = str(circle_connect)[:300]
                                        wired_inputs.append(param_name)
                                        input_values[param_name] = {"type": "curve", "source": "Circle"}

                                elif param_type == "surface":
                                    # Create Sphere for surface
                                    sphere = await call_rhino("/gh/create-component", "POST", {
                                        "guid": "dabc854d-f50e-408a-b001-d043c7de151d",  # Sphere
                                        "x": source_x, "y": source_y
                                    }, port=port)
                                    # Extract guid - may be at top level or in "data"
                                    sphere_guid = sphere.get("guid") or (sphere.get("data", {}).get("guid") if isinstance(sphere.get("data"), dict) else None)
                                    if sphere_guid:
                                        created_objects.append(sphere_guid)
                                        await call_rhino("/gh/connect", "POST", {
                                            "sourceGuid": sphere_guid,
                                            "sourceParam": "S",
                                            "targetGuid": comp_instance,
                                            "targetParam": param_name
                                        }, port=port)
                                        wired_inputs.append(param_name)
                                        input_values[param_name] = {"type": "surface", "source": "Sphere"}

                        # Solve the definition
                        await call_rhino("/gh/solve", "POST", {}, port=port)
                        await asyncio.sleep(0.2)

                        # Capture errors and outputs
                        errors_result_raw = await call_rhino("/gh/errors", "GET", {}, port=port)
                        # Unwrap the {"success": ..., "data": ...} structure
                        errors_result = errors_result_raw.get("data", errors_result_raw) if isinstance(errors_result_raw.get("data"), dict) else errors_result_raw
                        debug_info["errors_result"] = str(errors_result)[:500]
                        comp_errors = []
                        comp_warnings = []

                        # Response structure: {"errors": [{guid, errors: [], warnings: []}, ...], "warnings": [...]}
                        for err_component in errors_result.get("errors", []):
                            if err_component.get("guid") == comp_instance:
                                # Extract error messages from the component's errors array
                                comp_errors.extend(err_component.get("errors", []))

                        for warn_component in errors_result.get("warnings", []):
                            if warn_component.get("guid") == comp_instance:
                                # Extract warning messages from the component's warnings array
                                comp_warnings.extend(warn_component.get("warnings", []))

                        # Get output data structures
                        comp_details_after_raw = await call_rhino("/gh/component", "GET", {"guid": comp_instance}, port=port)
                        # Unwrap the {"success": ..., "data": ...} structure
                        comp_details_after = comp_details_after_raw.get("data", comp_details_after_raw) if isinstance(comp_details_after_raw.get("data"), dict) else comp_details_after_raw
                        outputs = {}
                        for out_param in comp_details_after.get("params", {}).get("outputs", []):
                            out_name = out_param.get("name", "?")
                            outputs[out_name] = {
                                "type": out_param.get("typeName", "unknown"),
                                "count": out_param.get("dataCount", 0)
                            }

                        # Determine status
                        if comp_errors:
                            status = "error"
                        elif comp_warnings:
                            status = "warning"
                        else:
                            status = "success"

                        # Check for correction (success after previous failure)
                        correction_detected = False
                        suggested_learning = None

                        if previous_obs_id and status == "success":
                            prev_obs = observations_data.get("observations", {}).get(previous_obs_id)
                            if prev_obs and prev_obs.get("result", {}).get("status") in ("error", "warning"):
                                correction_detected = True
                                suggested_learning = {
                                    "component_guid": component_guid,
                                    "observation_ids": [previous_obs_id, obs_id],
                                    "working_config": {
                                        "id": f"{component_name.lower()}_{len(input_values)}",
                                        "description": hypothesis[:50],
                                        "config": input_values
                                    },
                                    "gotcha": f"Corrected from attempt {attempt-1}: {hypothesis}"
                                }

                        # Generate next suggestion if failed
                        next_suggestion = None
                        if status == "error" and comp_errors:
                            error_msg = comp_errors[0].lower()
                            # Parse error for hints
                            if "only" in error_msg and "allowed" in error_msg:
                                next_suggestion = f"Error mentions allowed values. Try extracting valid values from: {comp_errors[0]}"
                            elif "null" in error_msg or "none" in error_msg:
                                next_suggestion = "Input is null/none. Try providing a valid source component."
                            elif "type" in error_msg:
                                next_suggestion = "Type mismatch. Check input type matches parameter expectation."

                        # Create observation record
                        observation = {
                            "id": obs_id,
                            "timestamp": datetime.now().isoformat() + "Z",
                            "session_id": session_id,
                            "component_guid": component_guid,
                            "component_name": component_name,
                            "attempt": attempt,
                            "hypothesis": hypothesis,
                            "intent": intent,
                            "config": input_values,
                            "result": {
                                "status": status,
                                "outputs": outputs,
                                "errors": comp_errors,
                                "warnings": comp_warnings
                            },
                            "learned": "",
                            "previous_attempt_id": previous_obs_id
                        }

                        # Save observation
                        observations_data["observations"][obs_id] = observation
                        observations_data["last_updated"] = datetime.now().isoformat() + "Z"

                        obs_file.parent.mkdir(parents=True, exist_ok=True)
                        with open(obs_file, "w") as f:
                            json.dump(observations_data, f, indent=2)

                        # Cleanup if requested
                        if cleanup and created_objects:
                            for obj_guid in created_objects:
                                try:
                                    await call_rhino("/gh/delete", "POST", {"guids": [obj_guid]}, port=port)
                                except:
                                    pass

                        result = {
                            "success": True,
                            "data": {
                                "observation_id": obs_id,
                                "result": status,
                                "outputs": outputs,
                                "errors": comp_errors,
                                "warnings": comp_warnings,
                                "next_suggestion": next_suggestion,
                                "correction_detected": correction_detected,
                                "suggested_learning": suggested_learning,
                                "_debug": debug_info
                            }
                        }

                except Exception as e:
                    import traceback
                    result = {"success": False, "data": f"Investigation failed: {str(e)}\n{traceback.format_exc()}"}

        case "gh_record_investigation":
            # Record verified learnings to knowledge graph
            from datetime import datetime
            from pathlib import Path

            component_guid = arguments.get("component_guid")
            observation_ids = arguments.get("observation_ids", [])
            working_config = arguments.get("working_config", {})
            gotcha = arguments.get("gotcha", "")
            context = arguments.get("context")

            if not component_guid:
                result = {"success": False, "data": "Missing required parameter: component_guid"}
            elif not observation_ids:
                result = {"success": False, "data": "Missing required parameter: observation_ids"}
            elif not working_config:
                result = {"success": False, "data": "Missing required parameter: working_config"}
            elif not gotcha:
                result = {"success": False, "data": "Missing required parameter: gotcha"}
            else:
                try:
                    tiered_file = resolve_writable_knowledge_path("gh", "tiered_knowledge.json")
                    tiered_read_path = tiered_file if tiered_file.exists() else resolve_readable_knowledge_path("gh", "tiered_knowledge.json")
                    obs_file = resolve_writable_knowledge_path("gh", "gh_observations.json")

                    # Load tiered knowledge
                    if tiered_read_path.exists():
                        with open(tiered_read_path, "r") as f:
                            tiered_data = json.load(f)
                    else:
                        result = {"success": False, "data": "tiered_knowledge.json not found"}
                        # Skip to match case end
                        raise FileNotFoundError("tiered_knowledge.json")

                    if not obs_file.exists():
                        result = {"success": False, "data": "gh_observations.json not found"}
                        raise FileNotFoundError("gh_observations.json")

                    with open(obs_file, "r") as f:
                        observations_data = json.load(f)

                    observations = observations_data.get("observations", {})
                    working_config_id = working_config.get("id")
                    working_config_description = working_config.get("description")
                    working_config_values = working_config.get("config")
                    validation_error = None

                    missing_observations = [
                        obs_id for obs_id in observation_ids
                        if obs_id not in observations
                    ]
                    if missing_observations:
                        validation_error = "Unknown observation_ids: " + ", ".join(missing_observations)

                    mismatched_component = [
                        obs_id
                        for obs_id in observation_ids
                        if observations.get(obs_id, {}).get("component_guid") != component_guid
                    ]
                    if validation_error is None and mismatched_component:
                        validation_error = (
                            "Observation(s) do not match component_guid: "
                            + ", ".join(mismatched_component)
                        )

                    if validation_error is None and (not isinstance(working_config_id, str) or not working_config_id.strip()):
                        validation_error = "working_config.id must be a non-empty string"
                    if validation_error is None and (
                        not isinstance(working_config_description, str) or not working_config_description.strip()
                    ):
                        validation_error = "working_config.description must be a non-empty string"
                    if validation_error is None and not isinstance(working_config_values, dict):
                        validation_error = "working_config.config must be an object"

                    successful_observations = [
                        observations[obs_id]
                        for obs_id in observation_ids
                        if observations.get(obs_id, {}).get("result", {}).get("status") == "success"
                    ]
                    if validation_error is None and not successful_observations:
                        validation_error = "At least one observation_id must reference a successful investigation result"

                    matching_success = any(
                        obs.get("config", {}) == working_config_values
                        for obs in successful_observations
                    )
                    if validation_error is None and not matching_success:
                        validation_error = (
                            "working_config.config must match the config of a successful observation in observation_ids"
                        )

                    if validation_error is not None:
                        result = {"success": False, "data": validation_error}
                    else:
                        # Find or create component entry
                        components = tiered_data.get("components", {})

                        if component_guid not in components:
                            # Get component info
                            lib_result = await call_rhino("/gh/library", "POST", {"search": component_guid}, port=port)
                            component_name = "Unknown"
                            lib_data = lib_result.get("data", lib_result) if isinstance(lib_result, dict) else {}
                            if isinstance(lib_data, dict) and lib_data.get("components"):
                                for comp in lib_data["components"]:
                                    if comp.get("guid") == component_guid:
                                        component_name = comp.get("name", "Unknown")
                                        break

                            components[component_guid] = {
                                "name": component_name,
                                "investigated": True
                            }

                        comp_entry = components[component_guid]

                        # Add investigations list if not present
                        if "investigations" not in comp_entry:
                            comp_entry["investigations"] = []

                        # Add observation IDs
                        for obs_id in observation_ids:
                            if obs_id not in comp_entry["investigations"]:
                                comp_entry["investigations"].append(obs_id)

                        # Add working_configs list if not present
                        if "working_configs" not in comp_entry:
                            comp_entry["working_configs"] = []

                        # Add the working config
                        working_config_entry = {
                            "id": working_config_id,
                            "description": working_config_description,
                            "config": working_config_values,
                            "verified": datetime.now().strftime("%Y-%m-%d"),
                            "observation_ids": observation_ids
                        }
                        comp_entry["working_configs"].append(working_config_entry)

                        # Add gotchas list if not present
                        if "gotchas" not in comp_entry:
                            comp_entry["gotchas"] = []

                        # Add the gotcha
                        gotcha_entry = {
                            "id": f"gotcha_{len(comp_entry['gotchas'])+1}",
                            "text": gotcha,
                            "source": "investigation",
                            "discovered": datetime.now().strftime("%Y-%m-%d"),
                            "observation_ids": observation_ids
                        }
                        comp_entry["gotchas"].append(gotcha_entry)

                        # Update quick reference if present
                        if "quick" in comp_entry and gotcha:
                            # Append gotcha hint to quick reference
                            quick_hint = gotcha.split(".")[0] if "." in gotcha else gotcha[:50]
                            if quick_hint not in comp_entry["quick"]:
                                comp_entry["quick"] += f" | {quick_hint}"

                        # Save updated tiered knowledge
                        tiered_data["components"] = components
                        tiered_data["last_updated"] = datetime.now().isoformat() + "Z"

                        tiered_file.parent.mkdir(parents=True, exist_ok=True)
                        with open(tiered_file, "w") as f:
                            json.dump(tiered_data, f, indent=2)

                        # Update observations with learned field
                        for obs_id in observation_ids:
                            if obs_id in observations:
                                observations[obs_id]["learned"] = gotcha

                        observations_data["observations"] = observations
                        obs_file.parent.mkdir(parents=True, exist_ok=True)
                        with open(obs_file, "w") as f:
                            json.dump(observations_data, f, indent=2)

                        result = {
                            "success": True,
                            "data": {
                                "recorded": True,
                                "knowledge_updated": True,
                                "updates": {
                                    "working_configs_added": 1,
                                    "gotchas_added": 1,
                                    "observations_linked": len(observation_ids)
                                },
                                "component": comp_entry.get("name", component_guid)
                            }
                        }

                except FileNotFoundError:
                    pass  # Result already set
                except Exception as e:
                    import traceback
                    result = {"success": False, "data": f"Recording failed: {str(e)}\n{traceback.format_exc()}"}

        case "gh_consolidate":
            # Run structural consolidation on GH component knowledge using DSPy
            mode = arguments.get("mode", "full")
            orphan_mode = arguments.get("orphan_mode", "legacy-include")

            if not _dspy_configured:
                result = {
                    "success": False,
                    "data": "DSPy not configured. Set ANTHROPIC_API_KEY in environment or .env file."
                }
            elif mode == "query":
                # Just return current structure
                from rook.learning.gh_consolidator import query_gh_structure
                try:
                    result = {"success": True, "data": query_gh_structure()}
                except Exception as e:
                    import traceback
                    result = {"success": False, "data": f"Query failed: {str(e)}\n{traceback.format_exc()}"}
            elif mode == "full":
                # Run full consolidation
                from rook.learning.gh_consolidator import GHConsolidator
                try:
                    consolidator = GHConsolidator(orphan_mode=orphan_mode)
                    structure = consolidator.consolidate_full()
                    result = {
                        "success": True,
                        "data": {
                            "mode": "full",
                            "consolidated": True,
                            "stats": {
                                "component_count": structure.component_count,
                                "raw_components": consolidator.raw_component_count,
                                "active_components": consolidator.active_component_count,
                                "deprecated_skipped": consolidator.deprecated_skipped_count,
                                "unknown_guids": consolidator.unknown_guid_count,
                                "families": len(structure.families),
                                "shared_behaviors": len(structure.shared_behaviors),
                                "similar_pairs": len(structure.similar_pairs),
                                "io_patterns": len(structure.io_patterns),
                            },
                            "families": list(structure.families.keys()),
                            "output_path": str(consolidator.structure_path),
                            "tiered_knowledge_updated": True,
                        }
                    }
                except Exception as e:
                    import traceback
                    result = {"success": False, "data": f"Consolidation failed: {str(e)}\n{traceback.format_exc()}"}
            elif mode == "incremental":
                # Incremental mode - place new components
                from rook.learning.gh_consolidator import GHConsolidator
                try:
                    consolidator = GHConsolidator(orphan_mode=orphan_mode)
                    structure = consolidator.load_structure()
                    if not structure or structure.consolidation_count == 0:
                        result = {
                            "success": False,
                            "data": "No existing structure. Run full consolidation first."
                        }
                    else:
                        # Load components and find new ones
                        components = consolidator.load_components()
                        existing_guids = set()
                        for family in structure.families.values():
                            existing_guids.update(family.components)

                        new_guids = [g for g in components.keys() if g not in existing_guids]

                        placements = []
                        for guid in new_guids:
                            placement = consolidator.place_new_component(guid, components[guid])
                            placements.append(placement)

                        result = {
                            "success": True,
                            "data": {
                                "mode": "incremental",
                                "new_components": len(new_guids),
                                "placements": placements,
                            }
                        }
                except Exception as e:
                    import traceback
                    result = {"success": False, "data": f"Incremental consolidation failed: {str(e)}\n{traceback.format_exc()}"}
            else:
                result = {"success": False, "data": f"Unknown mode: {mode}. Use 'full', 'incremental', or 'query'."}

        case "gh_structure_query":
            # Query the GH component structure
            from rook.learning.gh_consolidator import query_gh_structure

            guid = arguments.get("guid")
            family = arguments.get("family")
            name = arguments.get("name")
            stable_key = arguments.get("stable_key")

            try:
                result_data = query_gh_structure(guid=guid, family=family, name=name, stable_key=stable_key)
                result = {"success": True, "data": result_data}
            except Exception as e:
                import traceback
                result = {"success": False, "data": f"Structure query failed: {str(e)}\n{traceback.format_exc()}"}

        case "gh_batch_component_info":
            # Resolve names to active GUIDs via UnifiedStore, then query batch endpoint
            names = arguments.get("names", [])
            if not names:
                result = {"success": False, "data": "No names provided"}
            else:
                try:
                    store = get_unified_store()

                    guids_to_query = []
                    name_to_guid = {}
                    unresolved = []
                    for n in names:
                        guid = store.resolve_active_component_guid_by_name(n)
                        if guid:
                            guids_to_query.append(guid)
                            name_to_guid[n] = guid
                        else:
                            unresolved.append(n)

                    # For unresolved names, try library search
                    for n in unresolved:
                        lib_result = await call_rhino("/gh/library", "GET", {"search": n, "limit": 50}, port=port)
                        if lib_result.get("success"):
                            lib_data = lib_result.get("data", {})
                            lib_comps = lib_data.get("components", [])
                            for lc in lib_comps:
                                if lc.get("name", "").lower() == n.lower():
                                    guid = lc.get("guid", "")
                                    if guid and not store.get_deprecated_component(guid):
                                        guids_to_query.append(guid)
                                        name_to_guid[n] = guid
                                        break

                    if not guids_to_query:
                        result = {"success": False, "data": f"Could not resolve any names to GUIDs: {names}"}
                    else:
                        batch_result = await call_rhino(
                            "/gh/batch-component-info", "POST",
                            {"guids": guids_to_query}, port=port
                        )
                        if batch_result.get("success"):
                            result = {
                                "success": True,
                                "data": {
                                    "resolved": name_to_guid,
                                    "unresolved": [n for n in names if n not in name_to_guid],
                                    **batch_result.get("data", {})
                                }
                            }
                        else:
                            result = batch_result
                except Exception as e:
                    result = {"success": False, "data": f"Batch component info failed: {str(e)}"}

        case "gh_execute_intent":
            # Import the knowledge and execution components
            from rook.learning.gh_knowledge import get_gh_knowledge_store

            # Check DSPy availability
            DSPY_AVAILABLE = False
            try:
                from rook.learning.dspy_modules import GHIntentResolver, GHWiringExecutor
                from rook.learning.dspy_config import configure_dspy, is_configured
                if not is_configured():
                    configure_dspy()
                DSPY_AVAILABLE = True
            except Exception as dspy_err:
                logger.info(f"DSPy not available for GH intent resolution: {dspy_err}")

            intent = arguments.get("intent", "")
            base_x = arguments.get("x", 100)
            base_y = arguments.get("y", 100)
            plan_dict = arguments.get("plan", None)

            # Phase 4: Validate plan if provided
            validated_plan = None
            plan_validation_failed = False
            if plan_dict is not None:
                from rook.learning.plan_validator import validate_plan
                is_valid, plan_errors, validated_plan = validate_plan(plan_dict)
                if not is_valid:
                    result = {
                        "success": False,
                        "data": "Plan validation failed",
                        "errors": plan_errors,
                        "hint": "Required plan fields: reasoning, sub_problems, sequence, success_criteria"
                    }
                    plan_validation_failed = True
                else:
                    logger.info(f"Validated plan for intent '{intent}': {validated_plan.summary()}")

            if plan_validation_failed:
                pass  # result already set above
            elif not intent:
                result = {"success": False, "data": "Missing required parameter: intent"}
            else:
                try:
                    # Step 0: Query unified knowledge store for struggles and recipes
                    patterns_applied = []
                    pattern_gotchas = []
                    pattern_preconditions = []
                    pattern_verification_info = []
                    unified_recipes = []  # Recipes from unified store

                    try:
                        # Query unified store for struggles (problem→solution patterns)
                        unified_store = get_unified_store()
                        unified_struggles = unified_store.search(
                            intent=intent,
                            note_type="struggle",
                            tier="context",
                            limit=3
                        )
                        for s in unified_struggles:
                            patterns_applied.append(s.get("note_id", ""))
                            pattern_verification_info.append({
                                "pattern_id": s.get("note_id"),
                                "name": s.get("name"),
                                "source": "unified_store",
                            })
                            # Collect gotchas from anti-patterns
                            for anti in s.get("anti_patterns", []):
                                if isinstance(anti, dict):
                                    mistake = anti.get("mistake", "")
                                    symptom = anti.get("symptom", "")
                                    if mistake:
                                        gotcha = mistake
                                        if symptom:
                                            gotcha += f" (symptom: {symptom})"
                                        pattern_gotchas.append(gotcha)
                            # Collect preconditions
                            pattern_preconditions.extend(s.get("preconditions", []))

                        # Also query for matching recipes (workflow patterns)
                        unified_recipes = unified_store.search(
                            intent=intent,
                            note_type="recipe",
                            tier="context",
                            limit=3
                        )
                        for recipe in unified_recipes:
                            patterns_applied.append(recipe.get("note_id", ""))
                            pattern_verification_info.append({
                                "pattern_id": recipe.get("note_id"),
                                "name": recipe.get("name"),
                                "source": "unified_store",
                                "type": "recipe",
                                "components": recipe.get("components", [])[:5],  # First 5 components
                            })

                        # Query for teaching notes (tutorial content)
                        unified_teaching = unified_store.search(
                            intent=intent,
                            note_type="teaching",
                            tier="context",
                            limit=2
                        )
                        for teaching in unified_teaching:
                            pattern_verification_info.append({
                                "pattern_id": teaching.get("note_id"),
                                "name": teaching.get("name"),
                                "source": "unified_store",
                                "type": "teaching",
                                "solution_principle": teaching.get("solution_principle", "")[:300],
                            })

                        if unified_struggles or unified_recipes or unified_teaching:
                            logger.info(f"Unified store: {len(unified_struggles)} struggles, {len(unified_recipes)} recipes, {len(unified_teaching)} teaching for '{intent}'")
                    except Exception as unified_err:
                        logger.debug(f"Unified store query skipped: {unified_err}")

                    # Also query legacy PatternStore for backward compatibility
                    try:
                        from rook.learning.pattern_store import PatternStore
                        pattern_store = PatternStore(auto_save=False, enable_evolution=False, verify_on_search=True)
                        matching_patterns = pattern_store.search(intent=intent, limit=3, verify=True)
                        for p in matching_patterns:
                            if p.pattern_id not in patterns_applied:
                                patterns_applied.append(p.pattern_id)
                                pattern_verification_info.append({
                                    "pattern_id": p.pattern_id,
                                    "name": p.name,
                                    "verification": p.verification_to_dict(),
                                })
                                for anti in p.anti_patterns:
                                    if isinstance(anti, dict):
                                        mistake = anti.get("mistake", "")
                                        symptom = anti.get("symptom", "")
                                        if mistake:
                                            gotcha = mistake
                                            if symptom:
                                                gotcha += f" (symptom: {symptom})"
                                            pattern_gotchas.append(gotcha)
                                pattern_preconditions.extend(p.preconditions)
                        if matching_patterns:
                            verified_count = sum(1 for p in matching_patterns if p.verification_status == "verified")
                            logger.info(f"PatternStore: {len(matching_patterns)} patterns for '{intent}' ({verified_count} verified)")
                    except Exception as pattern_err:
                        logger.debug(f"Pattern memory query skipped: {pattern_err}")

                    # Step 1: Query knowledge for component candidates
                    store = get_gh_knowledge_store()
                    knowledge = store.query(intent, "context")

                    if not knowledge.get("guids"):
                        result = {
                            "success": False,
                            "data": f"No components found for intent: {intent}",
                            "hint": "Try more specific terms like 'sphere', 'slider', 'addition'",
                            # Include unified knowledge even when no components found
                            "patterns_applied": patterns_applied if patterns_applied else None,
                            "pattern_verification": pattern_verification_info if pattern_verification_info else None,
                            "unified_recipes": unified_recipes if unified_recipes else None,
                        }
                    else:
                        components = knowledge.get("components", [])
                        created = []
                        errors = []
                        spacing = 200
                        wiring_plan = None
                        values_to_set = None
                        dspy_confidence = None
                        dspy_rationale = None
                        low_confidence_rejected = False

                        # Step 2: DSPy Intent Resolution (if available)
                        if DSPY_AVAILABLE:
                            try:
                                resolver = GHIntentResolver()

                                # Get canvas state only when intent implies existing-canvas context.
                                # Default-open: uncertain intents still fetch. Only clearly pure-creation
                                # intents skip the round-trip. This saves ~30-80ms per call and improves
                                # DSPy cache hit rate by removing canvas_state from the prompt.
                                _CANVAS_CONTEXT_KEYWORDS = (
                                    "attach", "connect to", "wire to", "link to",
                                    "use selected", "from selected", "selected object",
                                    "modify", "change", "update", "edit",
                                    "add to existing", "existing",
                                    "move", "rearrange", "rewire",
                                )
                                intent_lower = intent.lower()
                                needs_canvas = any(kw in intent_lower for kw in _CANVAS_CONTEXT_KEYWORDS)
                                if needs_canvas:
                                    canvas_result = await call_rhino("/gh/query", "GET", {}, port=port)
                                    canvas_state = canvas_result.get("data", {}).get("objects", []) if canvas_result.get("success") else []
                                else:
                                    canvas_state = []

                                # Build tiered knowledge dict
                                tiered_knowledge = []
                                for c in components:
                                    tiered_knowledge.append({
                                        "guid": c.get("guid"),
                                        "name": c.get("name"),
                                        "family": c.get("family"),
                                        "quick": c.get("quick", ""),
                                        "params": c.get("params", {}),
                                        "deprecated": c.get("deprecated", False),
                                    })

                                # Call DSPy resolver
                                resolution = resolver.forward(
                                    user_intent=intent,
                                    candidate_guids=knowledge.get("guids", []),
                                    tiered_knowledge=tiered_knowledge,
                                    canvas_state=canvas_state,
                                )

                                # Extract DSPy results
                                components_to_create = resolution.components_to_create
                                wiring_plan = resolution.wiring_plan
                                values_to_set = resolution.values_to_set
                                dspy_confidence = resolution.confidence
                                dspy_rationale = resolution.rationale

                                logger.info(f"DSPy resolved intent with confidence {dspy_confidence}: {dspy_rationale}")

                                # Reject low-confidence resolutions to avoid creating wrong components
                                MIN_CONFIDENCE = 0.3
                                if dspy_confidence is not None and float(dspy_confidence) < MIN_CONFIDENCE:
                                    logger.warning(f"DSPy confidence {dspy_confidence} below threshold {MIN_CONFIDENCE}, rejecting resolution")
                                    low_confidence_rejected = True

                                # Build all_positioned from DSPy plan
                                all_positioned = []
                                if not low_confidence_rejected:
                                    # Clamp DSPy offsets to reasonable range to prevent
                                    # components scattering across the canvas
                                    MAX_OFFSET = 2000
                                    for comp_plan in components_to_create:
                                        guid = comp_plan.get("guid")
                                        # Find matching component info
                                        comp_info = next((c for c in components if c.get("guid") == guid), None)
                                        if comp_info:
                                            dx = comp_plan.get("x", 0)
                                            dy = comp_plan.get("y", 0)
                                            # Clamp offsets so components stay near base position
                                            dx = max(-MAX_OFFSET, min(MAX_OFFSET, dx))
                                            dy = max(-MAX_OFFSET, min(MAX_OFFSET, dy))
                                            x = base_x + dx
                                            y = base_y + dy
                                            all_positioned.append((comp_info, x, y))

                            except Exception as dspy_err:
                                logger.warning(f"DSPy resolution failed, using fallback: {dspy_err}")
                                DSPY_AVAILABLE = False  # Fall through to legacy logic

                        # Fallback: Hardcoded categorization (if DSPy unavailable or failed)
                        # Skip fallback if we explicitly rejected due to low confidence
                        if low_confidence_rejected:
                            result = {
                                "success": False,
                                "data": f"Intent '{intent}' could not be confidently resolved (confidence: {dspy_confidence})",
                                "dspy_confidence": dspy_confidence,
                                "dspy_rationale": dspy_rationale,
                                "hint": "Try more specific terms, or use gh_explore_component with a known GUID to place the component directly.",
                                "patterns_applied": patterns_applied if patterns_applied else None,
                            }
                        elif not DSPY_AVAILABLE or not all_positioned:
                            # GH data flows left-to-right: inputs (sliders/params) → main components
                            inputs = []  # Sliders, panels, params - go on LEFT
                            mains = []   # Main components (Sphere, Addition, etc.) - go on RIGHT

                            for comp in components:
                                family = comp.get("family", "").lower()
                                name = comp.get("name", "").lower()
                                if family == "params" or any(t in name for t in ["slider", "panel", "number", "integer", "point"]):
                                    inputs.append(comp)
                                else:
                                    mains.append(comp)

                            all_positioned = []
                            for i, comp in enumerate(inputs):
                                x = base_x - ((len(inputs) - i) * spacing)
                                all_positioned.append((comp, x, base_y))
                            for i, comp in enumerate(mains):
                                x = base_x + (i * spacing)
                                all_positioned.append((comp, x, base_y))

                        # ─── Batch execution via gh_edit ───────────────────────
                        # Assemble a single gh_edit document (create + connect +
                        # set_values) instead of N sequential HTTP calls. This
                        # collapses per-component/per-wire round-trip overhead
                        # into one atomic call.

                        # Helper: build nickName→input-index map from knowledge-store params
                        def _nick_to_input_idx(comp_info: dict) -> dict[str, int]:
                            """Map param nickNames to input indices for flow strings.

                            Knowledge-store params are {nickName: type} dicts whose key
                            order matches the GH param order (verified against live Sphere,
                            Extrude, Circle, Mesh Sphere components).
                            """
                            params = comp_info.get("params", {})
                            inputs = params.get("inputs", {})
                            if isinstance(inputs, dict):
                                return {nick: i for i, nick in enumerate(inputs.keys())}
                            return {}

                        # Step A: Get epoch for gh_edit
                        snapshot_result = await call_rhino("/gh/snapshot", "POST", {"include_data": False}, port=port)
                        edit_epoch = None
                        if snapshot_result.get("success"):
                            edit_epoch = snapshot_result.get("data", {}).get("epoch")

                        batch_ok = edit_epoch is not None

                        if batch_ok:
                            # Step B: Build create array
                            edit_create = []
                            # Track temp_id → (comp_info, name) for wiring and response
                            temp_id_map: list[tuple[dict, str, int, int]] = []  # [(comp_info, name, x, y), ...]

                            for i, (comp, x, y) in enumerate(all_positioned):
                                guid = comp.get("guid", "")
                                name = comp.get("name", "Unknown")
                                family = comp.get("family", "").lower()
                                temp_id = f"T{i + 1}"

                                # Detect sliders, panels, toggles for special create types
                                name_lower = name.lower()
                                if "slider" in name_lower and "number" in name_lower:
                                    entry = {
                                        "temp_id": temp_id,
                                        "type": "slider",
                                        "nick": comp.get("nickname", ""),
                                        "pos": [x, y],
                                    }
                                elif "panel" in name_lower and family == "params":
                                    entry = {
                                        "temp_id": temp_id,
                                        "type": "panel",
                                        "content": "",
                                        "pos": [x, y],
                                    }
                                elif "toggle" in name_lower or "boolean" in name_lower:
                                    entry = {
                                        "temp_id": temp_id,
                                        "type": "toggle",
                                        "value": True,
                                        "pos": [x, y],
                                    }
                                else:
                                    entry = {
                                        "temp_id": temp_id,
                                        "guid": guid,
                                        "pos": [x, y],
                                    }

                                edit_create.append(entry)
                                temp_id_map.append((comp, name, x, y))

                            # Step C: Build connect array from DSPy wiring_plan
                            edit_connect = []
                            wiring_results = []

                            if wiring_plan:
                                for wire_spec in wiring_plan:
                                    try:
                                        src_idx = wire_spec.get("source_index", 0)
                                        tgt_idx = wire_spec.get("target_index", 1)
                                        tgt_param = wire_spec.get("target_param", "")

                                        if src_idx < len(temp_id_map) and tgt_idx < len(temp_id_map):
                                            src_tid = f"T{src_idx + 1}"
                                            tgt_tid = f"T{tgt_idx + 1}"
                                            src_comp = temp_id_map[src_idx][0]
                                            tgt_comp = temp_id_map[tgt_idx][0]

                                            # Source is always output 0 (sliders, panels, single-output components)
                                            src_out_idx = 0

                                            # Resolve target param nickName → input index
                                            nick_map = _nick_to_input_idx(tgt_comp)
                                            tgt_in_idx = nick_map.get(tgt_param)
                                            if tgt_in_idx is None:
                                                # Try case-insensitive match
                                                tgt_param_lower = tgt_param.lower()
                                                for nick, idx in nick_map.items():
                                                    if nick.lower() == tgt_param_lower:
                                                        tgt_in_idx = idx
                                                        break
                                            if tgt_in_idx is None:
                                                # Last resort: param index 0
                                                logger.warning(f"Could not resolve param '{tgt_param}' on {tgt_comp.get('name')}, defaulting to I0")
                                                tgt_in_idx = 0

                                            flow = f"{src_tid}.O{src_out_idx}>{tgt_tid}.I{tgt_in_idx}"
                                            edit_connect.append(flow)
                                            wiring_results.append({
                                                "source": temp_id_map[src_idx][1],
                                                "target": temp_id_map[tgt_idx][1],
                                                "param": tgt_param,
                                            })
                                    except Exception as wire_err:
                                        logger.warning(f"Batch wiring plan entry failed: {wire_err}")

                            elif len(temp_id_map) > 1:
                                # Fallback: auto-wirer for connect flow strings
                                try:
                                    from rook.learning.gh_auto_wirer import GHAutoWirer
                                    auto_wirer = GHAutoWirer()

                                    # Build fake "created" list and component_params for the auto-wirer
                                    fake_created = []
                                    fake_params = {}
                                    for i, (comp, name, x, y) in enumerate(temp_id_map):
                                        fake_guid = f"T{i + 1}"  # Use temp_id as stand-in
                                        fake_created.append({
                                            "name": name,
                                            "instance_guid": fake_guid,
                                            "component_guid": comp.get("guid", ""),
                                        })
                                        # Build params from knowledge store
                                        ks_params = comp.get("params", {})
                                        if ks_params and isinstance(ks_params.get("inputs"), dict):
                                            converted = [
                                                {"name": n, "nickName": n, "type": t}
                                                for n, t in ks_params["inputs"].items()
                                            ]
                                            fake_params[fake_guid] = {"inputs": converted, "outputs": []}
                                        # else: auto-wirer will skip this component (no params)

                                    fallback_plan = auto_wirer.generate_wiring_plan(fake_created, fake_params)
                                    for wire_spec in fallback_plan:
                                        src_tid = wire_spec["source_guid"]  # Already a T-id
                                        tgt_tid = wire_spec["target_guid"]
                                        tgt_nick = wire_spec["target_param"]

                                        # Find target component index to resolve nick→input index
                                        tgt_i = int(tgt_tid[1:]) - 1
                                        tgt_comp = temp_id_map[tgt_i][0]
                                        nick_map = _nick_to_input_idx(tgt_comp)
                                        tgt_in_idx = nick_map.get(tgt_nick, 0)

                                        flow = f"{src_tid}.O0>{tgt_tid}.I{tgt_in_idx}"
                                        edit_connect.append(flow)
                                        wiring_results.append({
                                            "source": temp_id_map[int(src_tid[1:]) - 1][1],
                                            "target": temp_id_map[tgt_i][1],
                                            "param": tgt_nick,
                                        })
                                    if fallback_plan:
                                        logger.info(f"Auto-wirer generated {len(fallback_plan)} flow strings for batch")
                                except Exception as autowire_err:
                                    logger.warning(f"Batch auto-wiring failed: {autowire_err}")

                            # Step D: Build set_values from DSPy values_to_set
                            edit_set_values = []
                            values_applied = []
                            if values_to_set:
                                for val_spec in values_to_set:
                                    idx = val_spec.get("component_index", -1)
                                    value = val_spec.get("value")
                                    if 0 <= idx < len(temp_id_map) and value is not None:
                                        tid = f"T{idx + 1}"
                                        edit_set_values.append({"id": tid, "value": value})
                                        values_applied.append({
                                            "guid": tid,
                                            "value": value,
                                        })

                            # Step E: Submit single gh_edit call
                            edit_doc: dict = {"epoch": edit_epoch}
                            if edit_create:
                                edit_doc["create"] = edit_create
                            if edit_connect:
                                edit_doc["connect"] = edit_connect
                            if edit_set_values:
                                edit_doc["set_values"] = edit_set_values

                            edit_result = await call_rhino("/gh/edit", "POST", edit_doc, port=port)

                            if edit_result.get("success"):
                                edit_data = edit_result.get("data", {})
                                edit_summary = edit_data.get("edit_summary", {})

                                # gh_edit returns instance_guids: {T1: "guid", T2: "guid"}
                                # in the edit_summary (added in this refactor). Use these
                                # to populate instance_guid with real GH instance GUIDs,
                                # preserving the contract for session history and downstream.
                                guid_map = {}
                                if isinstance(edit_summary, dict):
                                    guid_map = edit_summary.get("instance_guids", {}) or {}

                                for i, (comp, name, x, y) in enumerate(temp_id_map):
                                    tid = f"T{i + 1}"
                                    instance_guid = guid_map.get(tid)
                                    created.append({
                                        "name": name,
                                        "component_guid": comp.get("guid", ""),
                                        "instance_guid": instance_guid,
                                        "x": x,
                                        "y": y,
                                    })

                                created_count = edit_summary.get("created", 0) if isinstance(edit_summary, dict) else len(temp_id_map)
                                wire_count = edit_summary.get("connected", 0) if isinstance(edit_summary, dict) else len(edit_connect)
                                logger.info(f"Batch gh_edit: created {created_count}, connected {wire_count}")

                                edit_errors = edit_summary.get("errors", []) if isinstance(edit_summary, dict) else []
                                if edit_errors:
                                    errors.extend(edit_errors)
                            else:
                                batch_ok = False
                                logger.warning(f"Batch gh_edit failed: {edit_result.get('data')}, falling back to sequential")

                        # Fallback: sequential creation if batch failed (epoch mismatch, etc.)
                        # This must replicate the full pre-batch behavior: create, wire
                        # (DSPy plan or auto-wirer), set values, so no functionality is
                        # lost when gh_edit fails.
                        if not batch_ok:
                            wiring_results = []
                            values_applied = []
                            for comp, x, y in all_positioned:
                                guid = comp.get("guid")
                                name = comp.get("name", "Unknown")
                                create_result = await call_rhino(
                                    "/gh/create-component", "POST",
                                    {"guid": guid, "name": name, "x": x, "y": y},
                                    port=port
                                )
                                if create_result.get("success"):
                                    instance_guid = create_result.get("data", {}).get("guid")
                                    created.append({
                                        "name": name,
                                        "component_guid": guid,
                                        "instance_guid": instance_guid,
                                        "x": x, "y": y,
                                    })
                                else:
                                    errors.append(f"Failed to create {name}: {create_result.get('data')}")

                            # Sequential wiring: DSPy plan first
                            if wiring_plan and len(created) > 0:
                                for wire_spec in wiring_plan:
                                    try:
                                        source_idx = wire_spec.get("source_index", 0)
                                        target_idx = wire_spec.get("target_index", 1)
                                        target_param = wire_spec.get("target_param", "")
                                        if source_idx < len(created) and target_idx < len(created):
                                            wire_result = await call_rhino(
                                                "/gh/connect", "POST",
                                                {
                                                    "sourceGuid": created[source_idx].get("instance_guid"),
                                                    "targetGuid": created[target_idx].get("instance_guid"),
                                                    "targetParam": target_param,
                                                },
                                                port=port
                                            )
                                            if wire_result.get("success"):
                                                wiring_results.append({
                                                    "source": created[source_idx].get("name"),
                                                    "target": created[target_idx].get("name"),
                                                    "param": target_param,
                                                })
                                    except Exception as wire_err:
                                        logger.warning(f"Sequential wiring failed: {wire_err}")

                            # Sequential wiring: auto-wirer fallback if DSPy didn't wire
                            if not wiring_results and len(created) > 1:
                                try:
                                    from rook.learning.gh_auto_wirer import GHAutoWirer
                                    auto_wirer = GHAutoWirer()
                                    component_params = {}
                                    for comp_entry in created:
                                        comp_guid = comp_entry.get("instance_guid")
                                        if not comp_guid:
                                            continue
                                        creation_guid = comp_entry.get("component_guid", "")
                                        ks_params = None
                                        for candidate in components:
                                            if candidate.get("guid") == creation_guid:
                                                ks_params = candidate.get("params", {})
                                                break
                                        if ks_params and isinstance(ks_params.get("inputs"), dict):
                                            converted_inputs = [
                                                {"name": n, "nickName": n, "type": t}
                                                for n, t in ks_params["inputs"].items()
                                            ]
                                            converted_outputs = []
                                            if isinstance(ks_params.get("outputs"), dict):
                                                converted_outputs = [
                                                    {"name": n, "nickName": n, "type": t}
                                                    for n, t in ks_params["outputs"].items()
                                                ]
                                            component_params[comp_guid] = {
                                                "inputs": converted_inputs,
                                                "outputs": converted_outputs,
                                            }
                                        else:
                                            comp_info = await call_rhino(
                                                "/gh/component", "GET",
                                                {"guid": comp_guid}, port=port
                                            )
                                            if comp_info.get("success"):
                                                component_params[comp_guid] = comp_info.get("data", {}).get("params", {})
                                    fallback_plan = auto_wirer.generate_wiring_plan(created, component_params)
                                    for wire_spec in fallback_plan:
                                        wire_result = await call_rhino(
                                            "/gh/connect", "POST",
                                            {
                                                "sourceGuid": wire_spec["source_guid"],
                                                "targetGuid": wire_spec["target_guid"],
                                                "targetParam": wire_spec["target_param"],
                                            },
                                            port=port
                                        )
                                        if wire_result.get("success"):
                                            source_name = next(
                                                (c["name"] for c in created if c.get("instance_guid") == wire_spec["source_guid"]),
                                                "Unknown"
                                            )
                                            target_name = next(
                                                (c["name"] for c in created if c.get("instance_guid") == wire_spec["target_guid"]),
                                                "Unknown"
                                            )
                                            wiring_results.append({
                                                "source": source_name,
                                                "target": target_name,
                                                "param": wire_spec["target_param"],
                                            })
                                    if fallback_plan:
                                        logger.info(f"Sequential auto-wirer connected {len(wiring_results)} wires")
                                except Exception as autowire_err:
                                    logger.warning(f"Sequential auto-wiring failed: {autowire_err}")

                            # Sequential values_to_set
                            if values_to_set and len(created) > 0:
                                try:
                                    from rook.learning.gh_auto_wirer import GHAutoWirer
                                    auto_wirer = GHAutoWirer()
                                    value_calls = auto_wirer.build_value_calls(created, values_to_set)
                                    for val_call in value_calls:
                                        set_result = await call_rhino(
                                            "/gh/set-value", "POST",
                                            {"guid": val_call["guid"], "value": val_call["value"]},
                                            port=port
                                        )
                                        if set_result.get("success"):
                                            values_applied.append(val_call)
                                    if values_applied:
                                        logger.info(f"Sequential: applied {len(values_applied)} initial values")
                                except Exception as val_err:
                                    logger.warning(f"Sequential value-setting failed: {val_err}")

                        # Step 3: Trigger solution
                        if created:
                            await call_rhino("/gh/solve", "POST", {"delay": 100}, port=port)

                        # Build response with DSPy info if available
                        # Merge gotchas from component knowledge and pattern memory (deduplicated)
                        all_gotchas = list(dict.fromkeys(knowledge.get("gotchas", []) + pattern_gotchas))
                        response_data = {
                            "intent": intent,
                            "components_created": created,
                            "wiring_performed": wiring_results if wiring_results else None,
                            "values_applied": values_applied if values_applied else None,
                            "errors": errors if errors else None,
                            "gotchas": all_gotchas if all_gotchas else None,
                            "knowledge_used": True,
                            "hint": "Components created and wired using type-based auto-wiring. Use gh_errors to check for issues." if wiring_results else "Components created. Auto-wiring matched what it could; manual wiring may be needed for complex setups.",
                        }

                        # Add pattern info if patterns were matched (Phase 2 + Phase 3)
                        if patterns_applied:
                            response_data["patterns_applied"] = patterns_applied
                            if pattern_preconditions:
                                # Deduplicate preconditions while preserving order
                                unique_preconditions = list(dict.fromkeys(pattern_preconditions))
                                response_data["preconditions"] = unique_preconditions
                            # Include verification status (Phase 3)
                            if pattern_verification_info:
                                response_data["pattern_verification"] = pattern_verification_info

                        # Add DSPy info if available
                        if dspy_confidence is not None:
                            response_data["dspy_confidence"] = dspy_confidence
                            response_data["dspy_rationale"] = dspy_rationale
                            response_data["resolution_method"] = "dspy"
                        else:
                            response_data["resolution_method"] = "fallback"

                        # Phase 4: Add plan info if provided
                        if validated_plan is not None:
                            response_data["plan_executed"] = True
                            response_data["plan_summary"] = validated_plan.summary()
                            # Include unknowns in response for transparency
                            if validated_plan.unknowns:
                                response_data["plan_unknowns"] = validated_plan.unknowns

                            # Phase 4 Enhancement: Step tracking for reflection
                            # Track which plan steps were executed and their status
                            overall_success = len(created) > 0 and len(errors) == 0
                            step_tracking = []
                            for i, step in enumerate(validated_plan.sequence):
                                step_tracking.append({
                                    "step_number": i + 1,
                                    "step": step,
                                    "status": "completed" if overall_success else "failed",
                                    # Link to components created in this execution
                                    "components_created": len(created) if i == len(validated_plan.sequence) - 1 else 0,
                                })
                            response_data["step_tracking"] = step_tracking
                            response_data["steps_completed"] = len(step_tracking) if overall_success else 0
                            response_data["steps_total"] = len(step_tracking)

                        # Phase 6: Add geometric constraint warnings
                        try:
                            from rook.learning.constraints import get_constraint_checker
                            constraint_checker = get_constraint_checker()
                            # Extract component names from all_positioned
                            component_names = [comp.get("name", "") for comp, x, y in all_positioned]
                            constraint_warnings = constraint_checker.get_warnings_for_components(component_names)
                            if constraint_warnings:
                                response_data["constraint_warnings"] = [w.to_dict() for w in constraint_warnings]
                        except Exception as constraint_error:
                            logger.warning(f"Failed to check constraints: {constraint_error}")

                        if low_confidence_rejected:
                            # Override with clear rejection message (result was set in the confidence check)
                            _track_intent_failure(intent, components, f"Low confidence: {dspy_confidence}")
                        else:
                            intent_success = len(created) > 0
                            result = {
                                "success": intent_success,
                                "data": response_data
                            }
                            # Correction detection for gh_execute_intent
                            if not intent_success:
                                _track_intent_failure(intent, components, "; ".join(errors) if errors else "No components created")
                            else:
                                correction = _check_intent_correction(intent, True, len(created))
                                if correction:
                                    response_data["correction_detected"] = True
                                    response_data["correction_info"] = correction
                                    logger.info(f"Correction detected for intent '{intent}': previously failed with '{correction['error']}'")

                        # Stash metrics extra for _record_observation()
                        result["_metrics_extra"] = {
                            "intent": intent,
                            "dspy_confidence": float(dspy_confidence) if dspy_confidence is not None else 0.0,
                            "components_created": len(created),
                        }

                        # Step 4: Record observation for learning
                        try:
                            from rook.learning.gh_knowledge import get_observation_recorder
                            recorder = get_observation_recorder()

                            # Record what was attempted and outcome
                            success = len(created) > 0 and len(errors) == 0
                            wiring_count = len(wiring_results) if wiring_results else 0
                            recorder.record(
                                component="gh_execute_intent",
                                observation=f"Intent '{intent}': created {len(created)} components, wired {wiring_count}" + (f" (DSPy confidence: {dspy_confidence:.2f})" if dspy_confidence else " (fallback)") + (f", used {len(patterns_applied)} patterns" if patterns_applied else ""),
                                impact="info" if success else "medium",
                                context={
                                    "type": "execute_intent",
                                    "intent": intent,
                                    "components_requested": [c.get("name") for c in components],
                                    "components_created": [c.get("name") for c in created],
                                    "wiring_attempted": wiring_count,
                                    "wiring_details": wiring_results,
                                    "wiring_plan": wiring_plan,
                                    "dspy_confidence": dspy_confidence,
                                    "dspy_rationale": dspy_rationale,
                                    "patterns_applied": patterns_applied if patterns_applied else None,
                                    "errors": errors,
                                    "success": success
                                },
                                tags=["execute_intent", "auto-wiring"] if wiring_count > 0 else ["execute_intent"]
                            )
                        except Exception as obs_error:
                            # Don't fail the main operation if recording fails
                            logger.warning(f"Failed to record observation: {obs_error}")

                        # Step 5: Record to session history for Path 2 meta-learning
                        try:
                            # Phase 4: Include plan in params for session recording
                            session_params = {"intent": intent}
                            if validated_plan is not None:
                                session_params["plan"] = validated_plan.to_dict()

                            entry_id = await _record_gh_to_session(
                                action="gh_execute_intent",
                                params=session_params,
                                result=result,
                                port=port,
                                components_created=[c.get("instance_guid") for c in created if c.get("instance_guid")],
                                connections_made=[
                                    (w.get("source", ""), "output", w.get("target", ""), w.get("param", ""))
                                    for w in (wiring_results or [])
                                ] if wiring_results else None,
                                patterns_applied=patterns_applied if patterns_applied else None,
                            )
                            if entry_id:
                                result["data"]["_entry_id"] = entry_id
                        except Exception as session_error:
                            logger.warning(f"Failed to record to session: {session_error}")

                except Exception as e:
                    # Don't overwrite low-confidence rejection messages
                    if not low_confidence_rejected:
                        import traceback
                        _track_intent_failure(intent, components if components else [], str(e))
                        result = {
                            "success": False,
                            "data": f"Intent execution failed: {str(e)}",
                            "traceback": traceback.format_exc()
                        }

        # GH Exploration handlers
        case "gh_start_exploration":
            from rook.learning.gh_knowledge import get_observation_recorder
            session_name = arguments.get("session_name", "exploration")
            try:
                recorder = get_observation_recorder()
                session_id = recorder.start_session(session_name)
                result = {
                    "success": True,
                    "data": {
                        "session_id": session_id,
                        "message": f"Started exploration session: {session_id}. All observations will be recorded."
                    }
                }
            except Exception as e:
                result = {"success": False, "data": f"Failed to start session: {str(e)}"}

        case "gh_end_exploration":
            from rook.learning.gh_knowledge import get_observation_recorder
            try:
                recorder = get_observation_recorder()
                summary = recorder.end_session()
                result = {"success": True, "data": summary}
            except Exception as e:
                result = {"success": False, "data": f"Failed to end session: {str(e)}"}

        case "gh_explore_workflow":
            from rook.learning.gh_knowledge import get_observation_recorder, get_gh_knowledge_store

            workflow = arguments.get("workflow", {})
            description = arguments.get("description", "")
            base_x = arguments.get("x", 100)
            base_y = arguments.get("y", 100)

            if not workflow or not description:
                result = {"success": False, "data": "Missing required parameters: workflow and description"}
            else:
                recorder = get_observation_recorder()
                store = get_gh_knowledge_store()
                steps = []
                created_instances = []  # Track (index, instance_guid) for wiring
                spacing = 200

                try:
                    components = workflow.get("components", [])
                    wiring = workflow.get("wiring", [])

                    # Step 1: Create components
                    for i, comp_def in enumerate(components):
                        role = comp_def.get("role", "main")
                        comp_type = comp_def.get("type", "")
                        nickname = comp_def.get("nickname", "")
                        value = comp_def.get("value")

                        # Calculate position based on role
                        if role == "input":
                            x = base_x - ((len([c for c in components if c.get("role") == "input"]) - i) * spacing)
                        else:
                            x = base_x + (i * spacing)
                        y = base_y

                        step_result = {"index": i, "type": comp_type, "role": role}

                        # Handle different component types
                        if comp_type == "slider":
                            create_resp = await call_rhino("/gh/create-slider", "POST", {
                                "nickname": nickname or "Slider",
                                "value": value if value is not None else 50,
                                "x": x, "y": y
                            }, port=port)
                        elif comp_type == "panel":
                            create_resp = await call_rhino("/gh/create-panel", "POST", {
                                "text": str(value) if value is not None else "",
                                "x": x, "y": y
                            }, port=port)
                        else:
                            # Look up component GUID from knowledge
                            knowledge = store.query(comp_type, "quick")
                            if knowledge.get("guids"):
                                guid = knowledge["guids"][0]
                                create_resp = await call_rhino("/gh/create-component", "POST", {
                                    "guid": guid, "x": x, "y": y
                                }, port=port)
                            else:
                                create_resp = {"success": False, "data": f"Unknown component type: {comp_type}"}

                        if create_resp.get("success"):
                            instance_guid = create_resp.get("data", {}).get("guid")
                            step_result["success"] = True
                            step_result["instance_guid"] = instance_guid
                            created_instances.append((i, instance_guid))
                            recorder.record_success(comp_type, f"Created {comp_type}", tags=["workflow"])
                        else:
                            step_result["success"] = False
                            step_result["error"] = create_resp.get("data")
                            recorder.record_failure(comp_type, f"Create {comp_type}", str(create_resp.get("data")), tags=["workflow"])

                        steps.append(step_result)

                    # Step 2: Wire components
                    wiring_results = []
                    for wire_def in wiring:
                        from_idx = wire_def.get("from")
                        to_idx = wire_def.get("to")
                        target_param = wire_def.get("target_param", "")

                        # Find instance GUIDs
                        source_guid = next((g for i, g in created_instances if i == from_idx), None)
                        target_guid = next((g for i, g in created_instances if i == to_idx), None)

                        wire_result = {"from": from_idx, "to": to_idx, "target_param": target_param}

                        if source_guid and target_guid:
                            wire_resp = await call_rhino("/gh/connect", "POST", {
                                "sourceGuid": source_guid,
                                "targetGuid": target_guid,
                                "targetParam": target_param
                            }, port=port)

                            if wire_resp.get("success"):
                                wire_result["success"] = True
                                recorder.record_success("wiring", f"Connected {from_idx}->{to_idx}:{target_param}", tags=["workflow", "wiring"])
                            else:
                                wire_result["success"] = False
                                wire_result["error"] = wire_resp.get("data")
                                recorder.record_failure("wiring", f"Connect {from_idx}->{to_idx}:{target_param}", str(wire_resp.get("data")), tags=["workflow", "wiring"])
                        else:
                            wire_result["success"] = False
                            wire_result["error"] = "Could not find source or target component"
                            recorder.record_failure("wiring", f"Connect {from_idx}->{to_idx}", "Missing component", tags=["workflow", "wiring"])

                        wiring_results.append(wire_result)

                    # Step 3: Trigger solution
                    await call_rhino("/gh/solve", "POST", {"delay": 100}, port=port)

                    # Step 4: Check for runtime errors
                    for i, instance_guid in created_instances:
                        comp_info = await call_rhino("/gh/component", "GET", {"guid": instance_guid}, port=port)
                        if comp_info.get("success"):
                            runtime_msgs = comp_info.get("data", {}).get("runtimeMessages")
                            if runtime_msgs:
                                recorder.record_discovery(
                                    components[i].get("type", "unknown"),
                                    f"Runtime message: {runtime_msgs}",
                                    tags=["runtime", "workflow"]
                                )

                    result = {
                        "success": True,
                        "data": {
                            "description": description,
                            "steps": steps,
                            "wiring": wiring_results,
                            "components_created": len(created_instances),
                            "observations_recorded": recorder._observation_count
                        }
                    }

                except Exception as e:
                    import traceback
                    recorder.record_failure("workflow", description, str(e), tags=["workflow", "exception"])
                    result = {
                        "success": False,
                        "data": f"Workflow exploration failed: {str(e)}",
                        "traceback": traceback.format_exc()
                    }

        case "gh_inspect_output":
            guid = arguments.get("guid")
            param = arguments.get("param", "0")

            if not guid:
                result = {"success": False, "data": "Missing required parameter: guid"}
            else:
                # Call the C# endpoint for full data inspection
                result = await call_rhino("/gh/inspect-output", "GET", {"guid": guid, "param": param}, port=port)

        # Interactive Command Learning handlers
        case "rhino_command_interactive_start":
            command = arguments.get("command")
            if not command:
                result = {"success": False, "data": "Missing required parameter: command"}
            else:
                try:
                    # Get the current prompt BEFORE starting the command
                    # This is critical for detecting when the prompt actually changes
                    initial_prompt_response = await call_rhino("/command/prompt", "GET")
                    previous_prompt = initial_prompt_response.get("data", {}).get("prompt", "Command")

                    # Send the command
                    start_response = await call_rhino("/command/start", "POST", {"command": command})

                    # Poll until prompt changes from previous value
                    # This fixes the stale prompt bug
                    prompt_response = await _poll_for_prompt_change(
                        call_rhino,
                        previous_prompt,
                        timeout_ms=2000,
                        poll_interval_ms=100
                    )

                    # Merge the responses
                    merged = {
                        "command": command,
                        "prompt": prompt_response.get("data", {}).get("prompt", "Command"),
                        "options": prompt_response.get("data", {}).get("options", []),
                        "default_value": prompt_response.get("data", {}).get("default_value"),
                        "is_active": prompt_response.get("data", {}).get("is_active", False),
                        "objects_before": start_response.get("data", {}).get("objects_before", 0),
                        "is_complete": prompt_response.get("data", {}).get("prompt") == "Command"
                    }
                    result = {"success": True, "data": merged}
                except Exception as e:
                    result = {"success": False, "data": f"Failed to start command: {str(e)}"}

        case "rhino_command_interactive_send":
            input_text = arguments.get("input", "")
            try:
                # Get current state before sending input
                doc_response = await call_rhino("/document", "GET")
                objects_before = doc_response.get("data", {}).get("objectCount", 0)

                # Get the current prompt BEFORE sending input
                initial_prompt_response = await call_rhino("/command/prompt", "GET")
                previous_prompt = initial_prompt_response.get("data", {}).get("prompt", "Command")

                # Send the input
                await call_rhino("/command/send", "POST", {"input": input_text})

                # Poll until prompt changes from previous value
                # This fixes the stale prompt bug
                prompt_response = await _poll_for_prompt_change(
                    call_rhino,
                    previous_prompt,
                    timeout_ms=2000,
                    poll_interval_ms=100
                )

                # Get object count after
                doc_response = await call_rhino("/document", "GET")
                objects_after = doc_response.get("data", {}).get("objectCount", 0)

                prompt = prompt_response.get("data", {}).get("prompt", "Command")
                is_complete = prompt == "Command"
                objects_created = objects_after - objects_before

                merged = {
                    "input_sent": input_text,
                    "prompt": prompt,
                    "options": prompt_response.get("data", {}).get("options", []),
                    "default_value": prompt_response.get("data", {}).get("default_value"),
                    "objects_before": objects_before,
                    "objects_after": objects_after,
                    "objects_created": objects_created,
                    "is_complete": is_complete
                }

                # Add learning reminder when interactive exploration completes
                if is_complete and objects_created > 0:
                    merged["learning_reminder"] = (
                        "Interactive command completed. If you discovered new patterns "
                        "(e.g., selection workflow, unexpected options, gotchas), "
                        "record them with knowledge_record() so future Claudes benefit."
                    )

                result = {"success": True, "data": merged}
            except Exception as e:
                result = {"success": False, "data": f"Failed to send input: {str(e)}"}

        case "rhino_command_interactive_prompt":
            try:
                response = await call_rhino("/command/prompt", "GET")
                result = {"success": True, "data": response}
            except Exception as e:
                result = {"success": False, "data": f"Failed to get prompt: {str(e)}"}

        case "rhino_command_interactive_cancel":
            try:
                # Send the cancel
                await call_rhino("/command/cancel", "POST")

                # Wait for Rhino to fully process the cancel
                # Note: Rhino's CommandPrompt may not update immediately even after cancel
                # The cancel IS effective, but the prompt text may be stale
                await asyncio.sleep(0.5)  # 500ms single wait

                # Get final state
                prompt_response = await call_rhino("/command/prompt", "GET")
                prompt_data = prompt_response.get("data", {})
                prompt_text = prompt_data.get("prompt", "")

                # Consider cancelled if prompt is "Command" or is_active is False
                cancelled = (prompt_text == "Command" or
                            prompt_text == "" or
                            not prompt_data.get("is_active", True))

                result = {
                    "success": True,
                    "data": {
                        "cancelled": cancelled,
                        "prompt": prompt_text if prompt_text else "Command",
                        "is_active": prompt_data.get("is_active", False),
                    }
                }
            except Exception as e:
                result = {"success": False, "data": f"Failed to cancel: {str(e)}"}

        case "rhino_learn_interactive":
            command = arguments.get("command")
            inputs = arguments.get("inputs", [])
            intent = arguments.get("intent")
            use_preselection = arguments.get("use_preselection", False)

            if not command:
                result = {"success": False, "data": "Missing required parameter: command"}
            elif not inputs:
                result = {"success": False, "data": "Missing required parameter: inputs"}
            else:
                try:
                    from .learning.command_observer import CommandObserver
                    from .learning.geometry_factory import analyze_prompt

                    # Use global observation_store to keep in-memory index in sync
                    geometry_prepared = False
                    preparation_info = None
                    actual_inputs = inputs

                    async with httpx.AsyncClient() as client:
                        observer = CommandObserver(client, store=observation_store)

                        # FIRST: Check if objects are already selected (before starting command)
                        # Use call_rhino which is known to work correctly
                        selection_data = await call_rhino("/selection")
                        pre_selected_count = selection_data.get("count", 0)

                        # Smart learning: Check if command needs geometry
                        start_result = await observer.start_command_interactive(command)
                        first_prompt = start_result.get("prompt", "")

                        # Analyze the first prompt
                        analysis = analyze_prompt(first_prompt)

                        if analysis.get("needs_geometry"):
                            # Cancel current command to prepare
                            await observer.cancel_command_interactive()

                            if use_preselection or pre_selected_count > 0:
                                # Objects already selected - use _SelPrev (respect manual composition)
                                actual_inputs = ["_SelPrev", ""] + inputs
                                preparation_info = {
                                    "pre_selected": True,
                                    "count": pre_selected_count,
                                    "use_preselection_flag": use_preselection,
                                    "note": "Using pre-selected geometry instead of auto-creating"
                                }
                            else:
                                # No pre-selection - auto-create geometry
                                creation_cmd = analysis.get("creation_command")
                                creation_inputs = analysis.get("creation_inputs", [])

                                if creation_cmd and creation_inputs:
                                    # Create the prerequisite geometry
                                    prep_observation = await observer.execute_interactive(
                                        command=creation_cmd,
                                        inputs=creation_inputs,
                                    )

                                    if prep_observation.success and prep_observation.result.objects_created > 0:
                                        geometry_prepared = True
                                        preparation_info = {
                                            "geometry_type": analysis["geometry_type"],
                                            "command": creation_cmd,
                                            "inputs": creation_inputs,
                                            "objects_created": prep_observation.result.objects_created,
                                        }
                                        # Modify inputs to select created geometry first
                                        actual_inputs = ["_SelLast", ""] + inputs

                            # Now run the actual command
                            observation = await observer.execute_interactive(
                                command=command,
                                inputs=actual_inputs,
                                intent=intent,
                            )
                        else:
                            # No geometry needed - cancel and run normally
                            await observer.cancel_command_interactive()
                            observation = await observer.execute_interactive(
                                command=command,
                                inputs=inputs,
                                intent=intent,
                            )

                    # Build base result
                    data = {
                        "observation_id": observation.id,
                        "command": observation.command,
                        "full_syntax": observation.full_syntax,
                        "success": observation.success,
                        "objects_created": observation.result.objects_created,
                        "dialogue_steps": len(observation.dialogue),
                        "dialogue": [
                            {
                                "step": i + 1,
                                "prompt": step.prompt,
                                "options": step.options_available,
                                "default": step.default_value,
                                "input": step.input_value,
                            }
                            for i, step in enumerate(observation.dialogue)
                        ],
                        "error": observation.result.error_message,
                    }

                    # Add geometry preparation info if applicable
                    # DEBUG: Always include pre_selected_count so we can see what was detected
                    data["debug_pre_selected_count"] = pre_selected_count

                    if geometry_prepared:
                        data["geometry_prepared"] = True
                        data["preparation"] = preparation_info
                    elif preparation_info and preparation_info.get("pre_selected"):
                        # Pre-selection was used instead of auto-creating
                        data["pre_selection_used"] = True
                        data["pre_selection"] = preparation_info

                    # Check for correction or track failure
                    cmd_key = observation.command  # e.g., "-Cone"
                    if not observation.success or observation.result.objects_created == 0:
                        # Track this failure for potential future correction detection
                        error_msg = observation.result.error_message or f"Command completed but created 0 objects"
                        _track_failure(cmd_key, inputs, error_msg)
                        data["failure_tracked"] = True
                    else:
                        # Check if this success corrects a recent failure
                        correction = _check_for_correction(
                            cmd_key,
                            observation.success,
                            observation.result.objects_created
                        )
                        if correction:
                            data["correction_detected"] = True
                            data["suggested_record"] = {
                                "intent": intent or f"execute {command}",
                                "action": {
                                    "tool": "rhino_command",
                                    "params": {
                                        "command": command,
                                        "inputs": inputs,
                                    }
                                },
                                "outcome": "success",
                                "correction_of": {
                                    "params": {"inputs": correction["failed_inputs"]},
                                    "error": correction["error"],
                                }
                            }

                    # AUTO-CONSOLIDATE: Update knowledge after successful learning
                    if observation.success and observation.result.objects_created > 0:
                        try:
                            pattern = command_learner.consolidate_command(observation.command)
                            if pattern:
                                data["auto_consolidated"] = True
                                data["consolidated_modes"] = list(pattern.modes.keys()) if pattern.modes else []
                        except Exception as consolidate_error:
                            # Don't fail the whole operation if consolidation fails
                            data["auto_consolidate_error"] = str(consolidate_error)

                    result = {"success": True, "data": data}
                except Exception as e:
                    result = {"success": False, "data": f"Failed to learn interactively: {str(e)}"}

        case "rhino_learn_variations_interactive":
            command = arguments.get("command")
            input_sequences = arguments.get("input_sequences", [])
            intent = arguments.get("intent")

            if not command:
                result = {"success": False, "data": "Missing required parameter: command"}
            elif not input_sequences:
                result = {"success": False, "data": "Missing required parameter: input_sequences"}
            else:
                try:
                    from .learning.command_observer import CommandObserver
                    from .learning.geometry_factory import analyze_prompt

                    # Use global observation_store to keep in-memory index in sync
                    results_list = []
                    corrections_detected = []
                    geometry_prepared = False
                    preparation_info = None

                    async with httpx.AsyncClient() as client:
                        observer = CommandObserver(client, store=observation_store)

                        # SMART GEOMETRY DETECTION: Check if command needs geometry ONCE
                        # before running variations
                        start_result = await observer.start_command_interactive(command)
                        first_prompt = start_result.get("prompt", "")
                        analysis = analyze_prompt(first_prompt)

                        # Cancel this probe - we'll restart for each variation
                        await observer.cancel_command_interactive()

                        if analysis.get("needs_geometry"):
                            # Create geometry ONCE for all variations
                            creation_cmd = analysis.get("creation_command")
                            creation_inputs = analysis.get("creation_inputs", [])

                            if creation_cmd and creation_inputs:
                                prep_observation = await observer.execute_interactive(
                                    command=creation_cmd,
                                    inputs=creation_inputs,
                                )

                                if prep_observation.success and prep_observation.result.objects_created > 0:
                                    geometry_prepared = True
                                    preparation_info = {
                                        "geometry_type": analysis["geometry_type"],
                                        "command": creation_cmd,
                                        "inputs": creation_inputs,
                                        "objects_created": prep_observation.result.objects_created,
                                    }

                        for inputs in input_sequences:
                            # If geometry was prepared, prepend selection
                            actual_inputs = inputs
                            if geometry_prepared:
                                actual_inputs = ["_SelLast", ""] + list(inputs)

                            observation = await observer.execute_interactive(
                                command=command,
                                inputs=actual_inputs,
                                intent=intent,
                            )

                            variation_result = {
                                "inputs": inputs,
                                "success": observation.success,
                                "objects_created": observation.result.objects_created,
                                "dialogue_steps": len(observation.dialogue),
                                "dialogue": [
                                    {
                                        "prompt": step.prompt[:60] + "..." if len(step.prompt) > 60 else step.prompt,
                                        "input": step.input_value,
                                    }
                                    for step in observation.dialogue
                                ],
                            }

                            # Check for correction or track failure
                            cmd_key = observation.command
                            if not observation.success or observation.result.objects_created == 0:
                                error_msg = observation.result.error_message or "Command completed but created 0 objects"
                                _track_failure(cmd_key, inputs, error_msg)
                                variation_result["failure_tracked"] = True
                            else:
                                correction = _check_for_correction(
                                    cmd_key,
                                    observation.success,
                                    observation.result.objects_created
                                )
                                if correction:
                                    variation_result["correction_detected"] = True
                                    corrections_detected.append({
                                        "working_inputs": inputs,
                                        "failed_inputs": correction["failed_inputs"],
                                        "error": correction["error"],
                                    })

                            results_list.append(variation_result)

                    data = {
                        "command": command,
                        "variations_tested": len(input_sequences),
                        "successful": sum(1 for r in results_list if r["success"] and r.get("objects_created", 0) > 0),
                        "results": results_list,
                    }

                    # Add geometry preparation info if applicable
                    if geometry_prepared:
                        data["geometry_prepared"] = True
                        data["preparation"] = preparation_info

                    # If any corrections were detected, suggest recording them
                    if corrections_detected:
                        data["corrections_detected"] = len(corrections_detected)
                        data["suggested_records"] = [
                            {
                                "intent": intent or f"execute {command}",
                                "action": {
                                    "tool": "rhino_command",
                                    "params": {"command": command, "inputs": c["working_inputs"]}
                                },
                                "outcome": "success",
                                "correction_of": {
                                    "params": {"inputs": c["failed_inputs"]},
                                    "error": c["error"],
                                }
                            }
                            for c in corrections_detected
                        ]

                    # AUTO-CONSOLIDATE: Update knowledge after learning variations
                    if data["successful"] > 0:
                        try:
                            pattern = command_learner.consolidate_command(command)
                            if pattern:
                                data["auto_consolidated"] = True
                                data["consolidated_modes"] = list(pattern.modes.keys()) if pattern.modes else []
                        except Exception as consolidate_error:
                            data["auto_consolidate_error"] = str(consolidate_error)

                    result = {"success": True, "data": data}
                except Exception as e:
                    result = {"success": False, "data": f"Failed to learn variations: {str(e)}"}

        case "rhino_analyze_prompt":
            prompt = arguments.get("prompt")
            if not prompt:
                result = {"success": False, "data": "Missing required parameter: prompt"}
            else:
                try:
                    from .learning.geometry_factory import analyze_prompt
                    analysis = analyze_prompt(prompt)
                    result = {"success": True, "data": analysis}
                except Exception as e:
                    result = {"success": False, "data": f"Failed to analyze prompt: {str(e)}"}

        case "rhino_prepare_geometry":
            geometry_type = arguments.get("geometry_type")
            if not geometry_type:
                result = {"success": False, "data": "Missing required parameter: geometry_type"}
            else:
                try:
                    from .learning.geometry_factory import get_geometry_for_type
                    creation_info = get_geometry_for_type(geometry_type, command_learner.knowledge_store)

                    if not creation_info.get("success"):
                        result = {"success": False, "data": creation_info.get("error", "Unknown error")}
                    else:
                        # Execute the creation command
                        cmd = creation_info["command"]
                        inputs = creation_info["inputs"]

                        async with httpx.AsyncClient() as client:
                            from .learning.command_observer import CommandObserver
                            observer = CommandObserver(client, store=observation_store)

                            observation = await observer.execute_interactive(
                                command=cmd,
                                inputs=inputs,
                            )

                            result = {
                                "success": True,
                                "data": {
                                    "geometry_type": geometry_type,
                                    "command_used": cmd,
                                    "inputs_used": inputs,
                                    "objects_created": observation.result.objects_created,
                                    "source": creation_info["source"],
                                    "hint": "Use _SelLast to select the created geometry"
                                }
                            }
                except Exception as e:
                    result = {"success": False, "data": f"Failed to prepare geometry: {str(e)}"}

        # =====================================================================
        # Pattern Memory Tools (Phase 2 Meta-Learning)
        # =====================================================================
        case "gh_query_patterns":
            from rook.learning.pattern_store import PatternStore
            try:
                # Enable JIT verification (Phase 3)
                store = PatternStore(auto_save=False, enable_evolution=False, verify_on_search=True)
                intent = arguments.get("intent")
                symptoms = arguments.get("symptoms")
                tags = arguments.get("tags")
                components = arguments.get("components")
                depth = arguments.get("depth", "context")
                limit = arguments.get("limit", 3)
                pattern_type = arguments.get("pattern_type", "all")

                patterns = store.search(
                    intent=intent,
                    symptoms=symptoms,
                    tags=tags,
                    components=components,
                    pattern_type=pattern_type,
                    limit=limit,
                    verify=True,  # JIT verification enabled
                )

                results = []
                # Track verification summary (Phase 3)
                verification_summary = {"verified": 0, "stale": 0, "unverifiable": 0, "no_citations": 0}

                for p in patterns:
                    # Count verification status
                    status = p.verification_status
                    if status in verification_summary:
                        verification_summary[status] += 1

                    if depth == "quick":
                        results.append({
                            "pattern_id": p.pattern_id,
                            "name": p.name,
                            "solution_brief": p.solution_brief,
                            "success_rate": p.success_rate(),
                            "verification": p.verification_to_dict(),  # Phase 3
                        })
                    elif depth == "context":
                        entry = {
                            "pattern_id": p.pattern_id,
                            "name": p.name,
                            "solution_brief": p.solution_brief,
                            "solution_principle": p.solution_principle,
                            "preconditions": p.preconditions,
                            "anti_patterns": p.anti_patterns[:2] if p.anti_patterns else [],
                            "success_rate": p.success_rate(),
                            "links": p.links,
                            "verification": p.verification_to_dict(),  # Phase 3
                        }
                        # Surface curriculum summary without full graph cost
                        curriculum = (p.graph or {}).get("curriculum", [])
                        if curriculum:
                            entry["curriculum_summary"] = {
                                "step_count": len(curriculum),
                                "steps": [
                                    {"step": s.get("step", "?"), "title": s.get("title", "")}
                                    for s in curriculum
                                ],
                            }
                        results.append(entry)
                    else:  # full
                        full_data = p.to_dict()
                        full_data["verification"] = p.verification_to_dict()  # Phase 3
                        results.append(full_data)

                # Also search UnifiedStore for teaching notes
                teaching_results = []
                if pattern_type in ("teaching", "all"):
                    try:
                        unified_store = get_unified_store()
                        teaching_tier = "context" if depth in ("context", "quick") else "raw"
                        teaching_notes = unified_store.search(
                            intent=intent,
                            tags=tags,
                            components=components,
                            note_type="teaching",
                            tier=teaching_tier,
                            limit=limit,
                        )
                        for t in teaching_notes:
                            teaching_results.append({
                                "note_id": t.get("note_id"),
                                "note_type": "teaching",
                                "name": t.get("name"),
                                "brief": t.get("brief"),
                                "solution_principle": t.get("solution_principle", "")[:500],
                                "components": t.get("components", []),
                                "tags": t.get("tags", []),
                                "keywords": t.get("keywords", []),
                            })
                    except Exception as te:
                        logger.debug(f"Teaching note search skipped: {te}")

                result = {
                    "success": True,
                    "data": {
                        "patterns": results,
                        "teaching": teaching_results,
                        "count": len(results) + len(teaching_results),
                        "query": {"intent": intent, "symptoms": symptoms, "tags": tags},
                        "verification_summary": verification_summary,  # Phase 3
                    }
                }
            except Exception as e:
                result = {"success": False, "data": f"Pattern query failed: {str(e)}"}

        case "gh_add_pattern":
            from rook.learning.pattern_store import PatternStore
            from rook.learning.pattern_memory import PatternNote
            from rook.learning.dspy_modules import PatternMetadataExtractor
            from datetime import datetime as dt

            name = arguments.get("name")
            solution_description = arguments.get("solution_description")
            session_id = arguments.get("session_id")
            entry_range = arguments.get("entry_range")
            components = arguments.get("components", [])
            skip_evolution = arguments.get("skip_evolution", False)

            if not name or not solution_description:
                result = {"success": False, "data": "Missing required: name and solution_description"}
            else:
                try:
                    store = PatternStore(auto_save=True, enable_evolution=not skip_evolution)

                    # Extract metadata via DSPy
                    extractor = PatternMetadataExtractor()
                    extraction = extractor(
                        solution_description=solution_description,
                        session_context=f"Session: {session_id}" if session_id else "",
                        components_involved=components,
                    )

                    # Create pattern
                    pattern = PatternNote(
                        name=name,
                        solution_brief=extraction.solution_brief or solution_description[:100],
                        solution_principle=extraction.solution_principle or solution_description,
                        trigger_intents=extraction.trigger_intents or [],
                        trigger_symptoms=extraction.trigger_symptoms or [],
                        tags=extraction.tags or [],
                        preconditions=extraction.preconditions or [],
                        components_needed=components,
                        created_from="manual",
                    )

                    # Add citation if session provided
                    if session_id:
                        pattern.citations.append({
                            "session_id": session_id,
                            "entry_range": entry_range or [],
                            "outcome": "success",
                            "timestamp": dt.now().isoformat(),
                        })

                    # Add with evolution
                    pattern = store.add(pattern, skip_evolution=skip_evolution)

                    result = {
                        "success": True,
                        "data": {
                            "pattern_id": pattern.pattern_id,
                            "name": pattern.name,
                            "links_created": len(pattern.links),
                            "tags": pattern.tags,
                            "evolution_enabled": not skip_evolution,
                        }
                    }
                except Exception as e:
                    result = {"success": False, "data": f"Failed to add pattern: {str(e)}"}

        case "gh_pattern_links":
            from rook.learning.pattern_store import PatternStore
            try:
                store = PatternStore(auto_save=False, enable_evolution=False)
                pattern_id = arguments.get("pattern_id")
                depth = arguments.get("depth", 1)

                pattern = store.get(pattern_id)
                if not pattern:
                    result = {"success": False, "data": f"Pattern {pattern_id} not found"}
                else:
                    data = {
                        "pattern": {
                            "id": pattern.pattern_id,
                            "name": pattern.name,
                            "brief": pattern.solution_brief,
                            "tags": pattern.tags,
                        },
                        "neighbors": [],
                    }

                    # Get direct neighbors
                    for neighbor in store.get_neighbors(pattern_id):
                        neighbor_data = {
                            "id": neighbor.pattern_id,
                            "name": neighbor.name,
                            "brief": neighbor.solution_brief,
                            "tags": neighbor.tags,
                            "depth": 1,
                        }

                        # Depth 2: get neighbors of neighbors
                        if depth > 1:
                            neighbor_data["neighbors"] = [
                                {"id": n.pattern_id, "name": n.name}
                                for n in store.get_neighbors(neighbor.pattern_id)
                                if n.pattern_id != pattern_id
                            ]

                        data["neighbors"].append(neighbor_data)

                    result = {"success": True, "data": data}
            except Exception as e:
                result = {"success": False, "data": f"Failed to get pattern links: {str(e)}"}

        case "gh_record_pattern_use":
            from rook.learning.pattern_store import PatternStore
            try:
                store = PatternStore(auto_save=True, enable_evolution=False)
                pattern_id = arguments.get("pattern_id")
                success = arguments.get("success")
                session_id = arguments.get("session_id")
                notes = arguments.get("notes")

                if not pattern_id or success is None:
                    result = {"success": False, "data": "Missing required: pattern_id and success"}
                else:
                    pattern = store.record_use(
                        pattern_id=pattern_id,
                        success=success,
                        session_id=session_id,
                        notes=notes,
                    )

                    if pattern:
                        result = {
                            "success": True,
                            "data": {
                                "pattern_id": pattern_id,
                                "times_used": pattern.times_used,
                                "times_succeeded": pattern.times_succeeded,
                                "success_rate": pattern.success_rate(),
                            }
                        }
                    else:
                        result = {"success": False, "data": f"Pattern {pattern_id} not found"}
            except Exception as e:
                result = {"success": False, "data": f"Failed to record use: {str(e)}"}

        case "gh_pattern_stats":
            from rook.learning.pattern_store import PatternStore
            try:
                store = PatternStore(auto_save=False, enable_evolution=False)
                stats = store.stats()
                result = {"success": True, "data": stats}
            except Exception as e:
                result = {"success": False, "data": f"Failed to get stats: {str(e)}"}

        case "metrics_summary":
            from rook.learning.metrics_store import get_metrics_store
            try:
                store = get_metrics_store()
                result = {"success": True, "data": store.get_summary()}
            except Exception as e:
                result = {"success": False, "data": f"Failed to get metrics: {str(e)}"}

        case "metrics_dashboard":
            # Return dashboard URL (started on demand)
            try:
                from rook.monitoring.dashboard_server import ensure_dashboard_running
                url = await ensure_dashboard_running()
                result = {"success": True, "data": {"url": url, "message": f"Dashboard running at {url}"}}
            except Exception as e:
                result = {"success": False, "data": f"Failed to start dashboard: {str(e)}"}

        # ── UV Texture Mapping ────────────────────────────────

        case "rhino_apply_uv_box_mapping":
            result = await call_rhino("/material/uv-box", "POST", arguments)

        case "rhino_apply_uv_planar_mapping":
            result = await call_rhino("/material/uv-planar", "POST", arguments)

        case "rhino_apply_uv_cylinder_mapping":
            result = await call_rhino("/material/uv-cylinder", "POST", arguments)

        case "rhino_apply_uv_sphere_mapping":
            result = await call_rhino("/material/uv-sphere", "POST", arguments)

        # ── Game Export Pipeline ──────────────────────────────

        case "rhino_tag_object_semantic":
            result = await call_rhino("/game-export/tag", "POST", arguments)

        case "rhino_tag_objects_from_layers":
            result = await call_rhino("/game-export/tag-from-layers", "POST", arguments)

        case "rhino_validate_export":
            result = await call_rhino("/game-export/validate", "POST", arguments)

        case "rhino_export_with_manifest":
            result = await call_rhino("/game-export/export", "POST", arguments)

        case "rhino_prepare_for_game_export":
            result = await call_rhino("/game-export/prepare", "POST", arguments)

        # ---- Agent System ----
        case "spawn_agent":
            result = await _handle_spawn_agent(arguments)

        case "plan_and_execute":
            result = await _handle_plan_and_execute(arguments)

        case "agent_status":
            result = _handle_agent_status(arguments)

        case "agent_abort":
            result = _handle_agent_abort(arguments)

        case "agent_answer":
            result = _handle_agent_answer(arguments)

        # ─── Scene Graph / Spatial Intelligence ───────────────────
        case "scene_graph":
            depth = arguments.get("depth", "compact")
            result = await call_rhino("/scene/graph", "GET", {"depth": depth}, port=port)

        case "scene_context":
            object_ids = arguments.get("object_ids", [])
            if not object_ids:
                result = {"success": False, "data": "Missing object_ids parameter"}
            else:
                from .scene.scene_graph import get_scene_graph
                sg = get_scene_graph()
                await sg.sync(port=port)
                context = sg.get_context(object_ids)
                result = {"success": True, "data": context}

        case "scene_query":
            query_args = {k: v for k, v in arguments.items() if k != "port"}
            result = await call_rhino("/scene/graph/query", "POST", query_args, port=port)

        case "scene_stats":
            from .scene.scene_graph import get_scene_graph
            sg = get_scene_graph()
            await sg.sync(port=port)
            result = {"success": True, "data": sg.get_stats()}

        case "scene_classify":
            classify_args = {k: v for k, v in arguments.items() if k != "port"}
            result = await call_rhino("/scene/graph/classify", "POST", classify_args, port=port)

        case "scene_overlay":
            overlay_args = {k: v for k, v in arguments.items() if k != "port"}
            result = await call_rhino("/scene/graph/overlay", "POST", overlay_args, port=port)

        # ── RoadCreator (RookRoads plugin) ─────────────────────────────────────

        case "rc_ping":
            result = await call_rhino("/rc/ping", port=port)

        case "rc_standards":
            result = await call_rhino("/rc/standards/categories", port=port)

        case "rc_roads":
            result = await call_rhino("/rc/roads", port=port)

        case "rc_clothoid":
            result = await call_rhino("/rc/alignment/clothoid", "POST", arguments, port=port)

        case "rc_cubic_parabola":
            result = await call_rhino("/rc/alignment/cubic-parabola", "POST", arguments, port=port)

        case "rc_vertical_curve":
            result = await call_rhino("/rc/alignment/vertical-curve", "POST", arguments, port=port)

        case "rc_assemble_route":
            result = await call_rhino("/rc/alignment/assemble-route", "POST", arguments, port=port)

        case "rc_cross_section":
            result = await call_rhino("/rc/road/cross-section", "POST", arguments, port=port)

        case "rc_road_3d":
            result = await call_rhino("/rc/road/3d", "POST", arguments, port=port)

        case "rc_extract_offsets":
            result = await call_rhino("/rc/extract-offsets", "POST", arguments, port=port)

        case "road_intersection_candidates":
            result = await call_rhino("/road/intersection/candidates", "POST", arguments, port=port)

        case "road_intersection_resolve":
            result = await call_rhino("/road/intersection/resolve", "POST", arguments, port=port)

        # ── RoadCreator — Urban Design ────────────────────────────────────────
        case "rc_sidewalk_profile":
            result = await call_rhino("/rc/urban/sidewalk-profile", "POST", arguments, port=port)

        case "rc_roundabout_params":
            result = await call_rhino("/rc/urban/roundabout-params", "POST", arguments, port=port)

        case "rc_crossing_params":
            result = await call_rhino("/rc/urban/crossing-params", "POST", arguments, port=port)

        # ── RoadCreator — Accessories ─────────────────────────────────────────
        case "rc_guardrail_profile":
            result = await call_rhino("/rc/accessories/guardrail-profile", port=port)

        case "rc_pole_spacing":
            result = await call_rhino("/rc/accessories/pole-spacing", "POST", arguments, port=port)

        case "rc_concrete_barrier_profile":
            result = await call_rhino("/rc/accessories/concrete-barrier-profile", port=port)

        case "rc_deltablok_profile":
            result = await call_rhino("/rc/accessories/deltablok-profile", "POST", arguments, port=port)

        # ── RoadCreator — Verge & Slopes ──────────────────────────────────────
        case "rc_verge_profile":
            result = await call_rhino("/rc/verge/profile", "POST", arguments, port=port)

        case "rc_slope_profile":
            result = await call_rhino("/rc/slope/profile", "POST", arguments, port=port)

        # ── RoadCreator — Standards ───────────────────────────────────────────
        case "rc_widening":
            result = await call_rhino("/rc/standards/widening", "POST", arguments, port=port)

        # ── RoadCreator — Terrain ─────────────────────────────────────────────
        case "rc_terrain_profile":
            result = await call_rhino("/rc/terrain/profile-points", "POST", arguments, port=port)

        case "rc_contour_levels":
            result = await call_rhino("/rc/terrain/contour-levels", "POST", arguments, port=port)

        # ── RoadCreator — Footprint ───────────────────────────────────────────
        case "rc_validate_profile":
            result = await call_rhino("/rc/footprint/validate-profile", "POST", arguments, port=port)

        case "rc_validate_style_set":
            result = await call_rhino("/rc/footprint/validate-style-set", "POST", arguments, port=port)

        # ── RoadCreator — Parametric Geometry (document-mutating) ─────────────
        case "rc_sidewalk":
            result = await call_rhino("/rc/geometry/sidewalk", "POST", arguments, port=port)

        case "rc_guardrail":
            result = await call_rhino("/rc/geometry/guardrail", "POST", arguments, port=port)

        case "rc_crossing":
            result = await call_rhino("/rc/geometry/crossing", "POST", arguments, port=port)

        case "rc_slopes":
            result = await call_rhino("/rc/geometry/slopes", "POST", arguments, port=port)

        case "rc_longitudinal_profile":
            result = await call_rhino("/rc/geometry/longitudinal-profile", "POST", arguments, port=port)

        case "rc_road_footprint":
            result = await call_rhino("/rc/geometry/road-footprint", "POST", arguments, port=port)

        # ── RoadCreator — Network Topology ────────────────────────────────────
        case "rc_resolve_edges":
            result = await call_rhino("/rc/network/resolve-edges", "POST", arguments, port=port)

        case "rc_apply_intersection_ownership":
            result = await call_rhino("/rc/network/apply-intersection-ownership", "POST", arguments, port=port)

        case "rc_apply_sidewalk_ownership":
            result = await call_rhino("/rc/network/apply-sidewalk-ownership", "POST", arguments, port=port)

        case "rc_sidewalk_corners":
            result = await call_rhino("/rc/geometry/sidewalk-corners", "POST", arguments, port=port)

        # ── RoadCreator — Profile Builder ─────────────────────────────────────
        case "rc_build_profile":
            result = await call_rhino("/rc/profile/build", "POST", arguments, port=port)

        case "rc_validate_road_profile":
            result = await call_rhino("/rc/profile/validate", "POST", arguments, port=port)

        case "rc_store_road_profile":
            result = await call_rhino("/rc/profile/store", "POST", arguments, port=port)

        case "rc_project_offset_profile":
            result = await call_rhino("/rc/profile/project-offset", "POST", arguments, port=port)

        case "rc_get_road_profile":
            result = await call_rhino("/rc/profile/get", "POST", arguments, port=port)

        case "rc_list_road_profiles":
            result = await call_rhino("/rc/profile/list", port=port)

        case _:
            result = {"success": False, "data": f"Unknown tool: {name}"}

    # Universal knowledge injection (post-call)
    get_phase_tracker().record_call(name)
    if should_inject(name, result):
        result = await inject_knowledge(name, arguments, result)

    # P2: Staleness feedback — update source knowledge on successful injection
    injection_meta = result.pop("_injection_meta", None)
    if injection_meta and result.get("success"):
        record_injection_success(injection_meta)

    # Metrics capture — after injection so we know if knowledge was injected
    _duration_ms = (_time.perf_counter() - _t0) * 1000
    _record_observation(_tool_name, arguments, result, _duration_ms, injection_meta)
    result.pop("_metrics_extra", None)  # Clean up internal key before serialization

    # Format response
    if result.get("success"):
        text = json.dumps(result.get("data"), indent=2)
    else:
        text = f"Error: {result.get('data', 'Unknown error')}"

    return [TextContent(type="text", text=text)]


def main():
    """Run the MCP server."""
    import asyncio
    import sys

    # Prevent stale .pyc bytecode caches from masking source edits
    sys.dont_write_bytecode = True

    async def run():
        async with stdio_server() as (read_stream, write_stream):
            await mcp.run(read_stream, write_stream, mcp.create_initialization_options())

    asyncio.run(run())


if __name__ == "__main__":
    main()
