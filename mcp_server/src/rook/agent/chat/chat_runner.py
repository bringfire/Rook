"""ChatRunner — executes conversation turns with LLM + tool dispatch.

Uses the ToolRegistry for progressive tool disclosure:
  - Tier 0: ~12 always-active tools (execute_intent, knowledge_query, objects, ping)
  - Tier 1: Named groups loaded via request_tools("gh_canvas")
  - Tier 2: Individual tools found via search_tools("boolean")
  - Auto-triggers: using rhino_create auto-loads rhino_transform group

The LLM starts with a small, focused tool set and dynamically loads more as needed.
"""
import inspect
import json
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Dict, List, Optional, Set

import litellm

from . import model_status
from .conversation_store import Conversation
# execution_policy verification (needs_verification + annotate_result) is now
# handled inside ToolDispatcher.dispatch() — the single enforcement point.
from .runtime_health import collect_runtime_facts
from .tool_contracts import (
    closed_no_arg_parameters,
    normalize_catalog,
    normalize_tool_result,
)
from ..substrate_analytics import (
    _compact_error as _substrate_compact_error,
    extract_substrate_observation,
    persist_substrate_observation,
    summarize_substrate_observations,
)
from ..tool_dispatcher import (
    BRIDGE_ROUTES,
    TRANSFORM_FUNCTIONS,
    ToolDispatcher,
    build_local_tools,
)
from ..tool_groups import AGENT_TIER_0, READONLY_TIER_0, TOOL_GROUP_TRIGGERS
from ..tool_registry import (
    ToolRegistry,
    load_catalog_from_cache,
    mcp_tool_to_litellm,
)
from ..generation_params import sanitize_generation_params_for_model
from ...tool_lifecycle import resolve_contained_tool
from ...tool_lifecycle_runtime import DispatchOrigin, deny_if_contained
from ...mcp_capability_gateway_contract import (
    MCP_CAPABILITY_GATEWAY_NAMES,
    build_mcp_capability_gateway_tools,
)

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 50  # GH definitions need many rounds (create, wire, set, verify per component)
MAX_META_ONLY_ROUNDS = 5  # Cap on consecutive rounds that only call meta-tools
STALE_TOOL_TURNS = 8  # Deactivate tools unused for this many rounds


def _patch_orphaned_tool_calls(messages: List[Dict[str, Any]]) -> int:
    """Repair history left invalid by cancelled tool dispatches.

    Anthropic requires every assistant tool_use to be followed immediately by
    matching tool_result messages. If a turn is cancelled after the assistant
    message is appended but before tool results are recorded, the next request
    fails. This inserts short synthetic results at the end of each assistant's
    contiguous tool-message run, before the next non-tool message.
    """
    synthetic_content = json.dumps({"error": "cancelled by user"})
    patched = 0
    i = 0

    while i < len(messages):
        msg = messages[i]
        if msg.get("role") != "assistant" or not msg.get("tool_calls"):
            i += 1
            continue

        expected_ids = [
            tc.get("id")
            for tc in msg.get("tool_calls", [])
            if isinstance(tc, dict) and tc.get("id")
        ]

        run_end = i + 1
        while run_end < len(messages) and messages[run_end].get("role") == "tool":
            run_end += 1

        present_ids = {
            messages[j].get("tool_call_id")
            for j in range(i + 1, run_end)
            if messages[j].get("tool_call_id")
        }

        for tc_id in expected_ids:
            if tc_id in present_ids:
                continue
            messages.insert(run_end, {
                "role": "tool",
                "tool_call_id": tc_id,
                "content": synthetic_content,
            })
            present_ids.add(tc_id)
            run_end += 1
            patched += 1

        i = run_end

    return patched


def _classify_tool_status(result: Any) -> Optional[str]:
    return normalize_tool_result(result).status


@dataclass
class ChatEvent:
    """A streaming event emitted during a conversation turn."""
    type: str  # text_delta, tool_start, tool_result, done, error, ui_block, model_update
    content: Optional[str] = None
    name: Optional[str] = None
    params: Optional[Dict] = None
    result: Optional[str] = None
    usage: Optional[Dict] = None
    model: Optional[str] = None
    applies_to: Optional[str] = None
    # ── Adaptive UI fields ──
    tool_call_id: Optional[str] = None
    block_id: Optional[str] = None
    block_type: Optional[str] = None
    block_config: Optional[Dict] = None
    verified: Optional[bool] = None
    verification_note: Optional[str] = None
    tool_status: Optional[str] = None

    def to_dict(self) -> dict:
        d = {"type": self.type}
        if self.content is not None:
            d["content"] = self.content
        if self.name is not None:
            d["name"] = self.name
        if self.params is not None:
            d["params"] = self.params
        if self.result is not None:
            d["result"] = self.result
        if self.usage is not None:
            d["usage"] = self.usage
        if self.model is not None:
            d["model"] = self.model
        if self.applies_to is not None:
            d["applies_to"] = self.applies_to
        if self.tool_call_id is not None:
            d["tool_call_id"] = self.tool_call_id
        if self.block_id is not None:
            d["block_id"] = self.block_id
        if self.block_type is not None:
            d["block_type"] = self.block_type
        if self.block_config is not None:
            d["block_config"] = self.block_config
        if self.verified is not None:
            d["verified"] = self.verified
        if self.verification_note is not None:
            d["verification_note"] = self.verification_note
        if self.tool_status is not None:
            d["tool_status"] = self.tool_status
        return d


# ─── Fallback descriptions for tools not in the cached catalog ────────────
_TOOL_DESCRIPTIONS: Dict[str, str] = {
    # Rhino core
    "rhino_ping": "Check if Rhino is responsive",
    "rhino_document": "Get current document info (name, units, path)",
    "rhino_layers": "List all layers in the document",
    "rhino_objects": "Query objects with optional filters (type, layer, name)",
    "rhino_selection": "Get currently selected objects",
    "rhino_select": "Select objects by GUID or criteria",
    "rhino_geometry": "Get geometry details for specific objects",
    "rhino_execute": "Run a Python script in Rhino (last resort — syntax/runtime failures are returned as structured errors, obvious rhinoscriptsyntax Get* prompts are rejected before dispatch, but other UI can still block Rhino)",
    "rhino_command": "Run a Rhino scripted command string via RunScript. May trigger modal dialogs if the command needs input.",
    "rhino_command_interactive_prompt": "Read Rhino's current command prompt state. Returns {prompt, is_active}. If is_active=true after execution, Rhino is waiting for input and the command did not complete.",
    "rhino_viewport": "Get or set viewport properties (camera, display mode)",
    "rhino_create": "Create geometry (points, curves, surfaces, solids)",
    "rhino_delete": "Delete objects by GUID",
    "rhino_transform": "Transform objects (move, rotate, scale, mirror)",
    "rhino_copy": "Copy objects with optional transform",
    "rhino_import": "Import geometry from file",
    "rhino_export": "Export geometry to file",
    "rhino_group": "Group or ungroup objects",
    "rhino_layer_create": "Create a new layer with optional properties (color, plotColor, plotWeight, linetype, material)",
    "rhino_layer_create_batch": "Create multiple layers in one call from key/parentKey relationships (single undo record)",
    "rhino_layer_delete": "Delete a layer",
    "rhino_layer_visibility": "Show or hide a layer",
    "rhino_layer_lock": "Lock or unlock a layer",
    "rhino_layer_current": "Set the current active layer",
    "rhino_layer_set_properties": "Set any combination of layer properties (rename, reparent, color, plotColor, plotWeight, linetype, material, visible, locked)",
    "rhino_layer_set_properties_batch": "Best-effort batch of set-properties across many layers in one undo step. Items are {name, set} with the single-target set shape; structured per-item errors on failure.",
    "rhino_layer_rename": "Rename a layer",
    "rhino_layer_move_objects": "Move all objects from one layer to another",
    "rhino_layer_merge": "Move objects from source to target layer, then delete source",
    "rhino_layer_dependencies": "Analyze what holds a layer alive (objects, block refs, children, canDelete)",
    # Material / linetype audit
    "rhino_materials": "List all materials with usage reporting (objects, layers, blocks, canPurge)",
    "rhino_material_purge": "Purge unused materials with structured blocker reporting",
    "rhino_linetypes": "List all linetypes with usage reporting (objects, layers, blocks, canPurge)",
    "rhino_linetype_purge": "Purge unused linetypes with structured blocker reporting",
    "rhino_block_layer_census": "Report which layers each block definition's geometry lives on",
    # Rhino transform tools
    "rhino_boolean": "Boolean operations (union, difference, intersection) on solids",
    "rhino_extrude": "Extrude a curve to create a surface or solid",
    "rhino_text": "Create 3D text objects",
    # Grasshopper
    "gh_status": "Get Grasshopper document status",
    "gh_snapshot": "Read the entire canvas as a structured graph document",
    "gh_edit": "Mutate the canvas atomically — create, connect, disconnect, delete, set values, manage groups",
    "gh_undo": "Undo the last canvas edit operation",
    "gh_selection": "Get selected Grasshopper components",
    "gh_categories": "List available component categories",
    "gh_errors": "Get errors and warnings from Grasshopper",
    "gh_preview": "Toggle geometry preview for components",
    "gh_clear": "Clear all components from canvas",
    "gh_move": "Move components on the canvas",
    "gh_library": "Search the component library by name or category",
    "gh_update_script": "Update source on an existing supported C#/Python script component",
    "gh_set_script": "Raw source read/write for C#/Python/GH1 script components",
    "gh_set_script_pins": "Edit pin metadata on an existing C#/Python script component",
    "gh_inspect_output": "Inspect the output data of a component",
    # Knowledge
    "knowledge_query": "Query the Rhino knowledge graph for tool patterns",
    "rhino_knowledge_query": "Alias for Rhino command knowledge lookup",
    "gh_knowledge_query": "Query the Grasshopper knowledge store for components, recipes, patterns",
    "gh_constraints": "Get wiring constraints and warnings for components",
    # Scene graph
    "scene_graph": "Build and query the spatial relationship graph of scene objects",
    "scene_context": "Get spatial context around a point or object",
    "scene_stats": "Get scene statistics (object counts, bounding box, layers)",
    # Session recording — post-execution verification
    "session_current": "Get current session summary: aggregate stats only (total commands, success/fail counts). Does NOT include per-command details.",
    "session_history": "Get individual command records with per-command success/failure status and error messages. Use after geometry operations to verify the result.",
    # Adaptive UI
    "ui_block": "Present an interactive UI element (slider, buttons, text input, confirmation) to the user. The user's response arrives as a ui_response message.",
    # Chat model controls
    "list_chat_models": "List chat models available for this conversation, including local provider status and allowed model overrides.",
    "set_chat_model": "Stage a chat model override for the next conversation turn. Use model_override from list_chat_models; do not provide api_base.",
}


def _build_fallback_catalog() -> Dict[str, dict]:
    """Build a minimal LiteLLM catalog from known tool names when no cache exists.

    Most fallback entries have descriptions but no parameter schemas
    (additionalProperties: True). Critical first-run tools get typed schemas so
    RookChat remains usable before the MCP server caches the full catalog.
    """
    catalog: Dict[str, dict] = {}

    # All known tools from ToolDispatcher tiers
    all_tools: Dict[str, str] = {}
    for name in BRIDGE_ROUTES:
        all_tools[name] = _TOOL_DESCRIPTIONS.get(
            name, f"Rhino/GH tool: {name.replace('_', ' ')}"
        )
    for name in TRANSFORM_FUNCTIONS:
        all_tools[name] = _TOOL_DESCRIPTIONS.get(
            name, f"Rhino/GH tool: {name.replace('_', ' ')}"
        )

    for tool_name, desc in all_tools.items():
        if resolve_contained_tool(tool_name) is not None:
            continue
        if tool_name == "gh_errors":
            catalog[tool_name] = _GH_ERRORS_SCHEMA
            continue
        if tool_name == "rhino_execute":
            catalog[tool_name] = _RHINO_EXECUTE_SCHEMA
            continue
        if tool_name == "rhino_command":
            catalog[tool_name] = _RHINO_COMMAND_SCHEMA
            continue
        if tool_name == "rhino_create":
            catalog[tool_name] = _RHINO_CREATE_SCHEMA
            continue
        catalog[tool_name] = {
            "type": "function",
            "function": {
                "name": tool_name,
                "description": desc,
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": True,
                },
            },
        }
    catalog["gh_update_script"] = _GH_UPDATE_SCRIPT_SCHEMA
    catalog.update(_GH_CREATE_SCRIPT_SCHEMAS)
    return normalize_catalog(catalog)


_UI_BLOCK_SCHEMA: dict = {
    "type": "function",
    "function": {
        "name": "ui_block",
        "description": _TOOL_DESCRIPTIONS.get("ui_block", "Present an interactive UI element to the user."),
        "parameters": {
            "type": "object",
            "properties": {
                "block_type": {
                    "type": "string",
                    "enum": ["slider", "buttons", "text_input", "confirmation", "composite"],
                    "description": "The type of UI block to present.",
                },
                "config": {
                    "type": "object",
                    "description": "Block configuration (title, options, min/max, etc.). Structure varies by block_type.",
                },
            },
            "required": ["block_type", "config"],
        },
    },
}

_LIST_CHAT_MODELS_SCHEMA: dict = {
    "type": "function",
    "function": {
        "name": "list_chat_models",
        "description": _TOOL_DESCRIPTIONS["list_chat_models"],
        "parameters": closed_no_arg_parameters(),
    },
}

_SET_CHAT_MODEL_SCHEMA: dict = {
    "type": "function",
    "function": {
        "name": "set_chat_model",
        "description": _TOOL_DESCRIPTIONS["set_chat_model"],
        "parameters": {
            "type": "object",
            "properties": {
                "model_override": {
                    "type": "string",
                    "description": "Allowed model override from list_chat_models.",
                },
                "reason": {
                    "type": "string",
                    "description": "Short reason for switching models.",
                },
            },
            "required": ["model_override"],
            "additionalProperties": False,
        },
    },
}

_CHAT_MODEL_TOOL_SCHEMAS: Dict[str, dict] = {
    "list_chat_models": _LIST_CHAT_MODELS_SCHEMA,
    "set_chat_model": _SET_CHAT_MODEL_SCHEMA,
}

_GH_ERRORS_SCHEMA: dict = {
    "type": "function",
    "function": {
        "name": "gh_errors",
        "description": (
            _TOOL_DESCRIPTIONS["gh_errors"]
            + " Takes no arguments; call it after create/update tools to inspect the canvas."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
}

_GH_UPDATE_SCRIPT_SCHEMA: dict = {
    "type": "function",
    "function": {
        "name": "gh_update_script",
        "description": _TOOL_DESCRIPTIONS.get(
            "gh_update_script",
            "Update source on an existing supported C#/Python script component",
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "guid": {
                    "type": "string",
                    "description": "Component instance GUID or short ID (C1, C2...) from gh_snapshot",
                },
                "code": {
                    "type": "string",
                    "description": "New source code or body code, depending on mode and detected runtime",
                },
                "mode": {
                    "type": "string",
                    "enum": ["auto", "body", "full_source"],
                    "default": "auto",
                    "description": "auto detects full source where possible; body wraps for supported runtimes; full_source writes complete source",
                },
                "language": {
                    "type": "string",
                    "enum": ["auto", "python", "csharp"],
                    "default": "auto",
                    "description": "Optional runtime language assertion; auto accepts the detected component language",
                },
                "python_preamble": {
                    "type": "boolean",
                    "default": True,
                    "description": "For RhinoCode Python 3 body edits, add generated input/output coercion helpers when needed",
                },
                "check_errors": {
                    "type": "boolean",
                    "default": True,
                    "description": "After writing, wait briefly and summarize /gh/errors for this component and the canvas",
                },
            },
            "required": ["guid", "code"],
            "additionalProperties": False,
        },
    },
}

_POINT3_SCHEMA: dict = {
    "type": "array",
    "items": {"type": "number"},
    "minItems": 3,
    "maxItems": 3,
}

_RHINO_EXECUTE_SCHEMA: dict = {
    "type": "function",
    "function": {
        "name": "rhino_execute",
        "description": _TOOL_DESCRIPTIONS["rhino_execute"],
        "parameters": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Python code to execute in Rhino.",
                },
            },
            "required": ["code"],
            "additionalProperties": False,
        },
    },
}

_RHINO_COMMAND_SCHEMA: dict = {
    "type": "function",
    "function": {
        "name": "rhino_command",
        "description": _TOOL_DESCRIPTIONS["rhino_command"],
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "pattern": "^\\s*_",
                    "description": (
                        "Known-safe, non-interactive Rhino command string. "
                        "Must start with '_' for locale-independent execution."
                    ),
                },
                "echo": {
                    "type": "boolean",
                    "description": "Echo command to the command line. Defaults to false.",
                },
            },
            "required": ["command"],
            "additionalProperties": False,
        },
    },
}

_RHINO_CREATE_SCHEMA: dict = {
    "type": "function",
    "function": {
        "name": "rhino_create",
        "description": (
            "Create geometry in Rhino. Supports POINT, LINE, POLYLINE, CIRCLE, "
            "ARC, RECTANGLE, BOX, SPHERE, CYLINDER, and CONE. "
            'For a box, use {"type":"BOX","origin":[0,0,0],'
            '"width":10,"depth":10,"height":1} or corner1/corner2.'
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "description": (
                        "Geometry type: POINT, LINE, POLYLINE, CIRCLE, ARC, "
                        "RECTANGLE, BOX, SPHERE, CYLINDER, CONE."
                    ),
                },
                "name": {"type": "string", "description": "Object name."},
                "layer": {"type": "string", "description": "Layer path."},
                "color": {
                    "description": (
                        "Color as [r,g,b] array, {r,g,b} object, or #rrggbb string."
                    ),
                },
                "point": {**_POINT3_SCHEMA, "description": "For POINT: [x, y, z]."},
                "location": {
                    **_POINT3_SCHEMA,
                    "description": "Alias for POINT point [x, y, z].",
                },
                "start": {**_POINT3_SCHEMA, "description": "For LINE: start point."},
                "end": {**_POINT3_SCHEMA, "description": "For LINE: end point."},
                "points": {
                    "type": "array",
                    "items": _POINT3_SCHEMA,
                    "description": "For POLYLINE: array of [x, y, z] points.",
                },
                "center": {
                    **_POINT3_SCHEMA,
                    "description": (
                        "For CIRCLE, ARC, SPHERE, CYLINDER, CONE: center [x, y, z]."
                    ),
                },
                "base": {
                    **_POINT3_SCHEMA,
                    "description": "Alias for CYLINDER and CONE base center [x, y, z].",
                },
                "plane": {
                    "type": "string",
                    "description": "For CIRCLE and ARC orientation: XY, XZ, or YZ.",
                },
                "radius": {
                    "type": "number",
                    "description": "For CIRCLE, ARC, SPHERE, CYLINDER, CONE.",
                },
                "origin": {
                    **_POINT3_SCHEMA,
                    "description": "For RECTANGLE and BOX: origin [x, y, z].",
                },
                "corner": {
                    **_POINT3_SCHEMA,
                    "description": "Alias for origin on RECTANGLE and BOX.",
                },
                "corner1": {
                    **_POINT3_SCHEMA,
                    "description": "For BOX: first diagonal corner [x, y, z].",
                },
                "corner2": {
                    **_POINT3_SCHEMA,
                    "description": "For BOX: second diagonal corner [x, y, z].",
                },
                "width": {
                    "type": "number",
                    "description": "For RECTANGLE and BOX: width in +X.",
                },
                "height": {
                    "type": "number",
                    "description": (
                        "For RECTANGLE and BOX: height in +Z. For CYLINDER and "
                        "CONE: height along Z."
                    ),
                },
                "depth": {"type": "number", "description": "For BOX: depth in +Y."},
                "x": {"type": "number", "description": "Alias for BOX width."},
                "y": {"type": "number", "description": "Alias for BOX depth."},
                "z": {"type": "number", "description": "Alias for BOX height."},
                "startAngle": {"type": "number", "description": "For ARC: start angle."},
                "endAngle": {"type": "number", "description": "For ARC: end angle."},
            },
            "required": ["type"],
            "additionalProperties": False,
        },
    },
}

_GH_SCRIPT_PIN_ARRAY_SCHEMA: dict = {
    "type": "array",
    "items": {
        "oneOf": [
            {"type": "string"},
            {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "type": {"type": "string"},
                    "nick": {"type": "string"},
                    "access": {
                        "type": "string",
                        "enum": ["item", "list", "tree"],
                    },
                    "optional": {"type": "boolean"},
                    "description": {"type": "string"},
                    "hidden": {"type": "boolean"},
                },
                "required": ["name"],
                "additionalProperties": False,
            },
        ]
    },
}


_GH_CSHARP_SCRIPT_CONTRACT = (
    "C# mode creates a RhinoCode C# Script component, not a Grasshopper plugin "
    "component. Prefer body-only RunScript code; the tool wraps it in "
    "Script_Instance boilerplate. Do not provide a GH_Component subclass. "
    "Only provide full source when it is a Script_Instance : GH_ScriptInstance "
    "class or contains void RunScript. Assign outputs directly by output pin "
    "name, e.g. B = box.ToBrep(). After creating or updating a script, call "
    "gh_errors when verification is requested. If gh_errors reports script "
    "errors and gh_update_script is available, fix the existing component with "
    "gh_update_script; do not just paste corrected code into chat."
)

_GH_CSHARP_CODE_DESCRIPTION = (
    "C# source for RhinoCode C# Script. Prefer body-only RunScript code. "
    "Do not send a GH_Component subclass. Full-source mode must be "
    "Script_Instance : GH_ScriptInstance or contain void RunScript."
)


def _gh_create_script_schema(
    name: str,
    description: str,
    *,
    required: list[str],
    include_language: bool,
    code_description: str | None = None,
    extra_description: str | None = None,
    pins_out_description: str | None = None,
) -> dict:
    if extra_description:
        description = f"{description}\n\n{extra_description}"
    properties: dict = {
        "code": {
            "type": "string",
            "description": code_description or "Script source code for the script component.",
        },
        "pins_in": {
            **_GH_SCRIPT_PIN_ARRAY_SCHEMA,
            "description": 'Input pin definitions as "Name:Type" strings or pin objects.',
        },
        "pins_out": {
            **_GH_SCRIPT_PIN_ARRAY_SCHEMA,
            "description": pins_out_description
            or 'Output pin definitions as "Name:Type" strings or pin objects.',
        },
        "name": {
            "type": "string",
            "description": "Display name for the component.",
        },
        "x": {
            "type": "number",
            "description": "Canvas X position.",
        },
        "y": {
            "type": "number",
            "description": "Canvas Y position.",
        },
    }
    if include_language:
        properties = {
            "language": {
                "type": "string",
                "enum": ["python", "csharp"],
                "description": "Script language: python or csharp.",
            },
            **properties,
        }
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
        },
    }


_GH_CREATE_SCRIPT_SCHEMA: dict = _gh_create_script_schema(
    "gh_create_script",
    _TOOL_DESCRIPTIONS.get(
        "gh_create_script",
        "Create a Python 3 or C# Script component with pins and code.",
    ),
    required=["language", "code"],
    include_language=True,
    code_description=(
        'Script source code. For language="csharp": '
        + _GH_CSHARP_CODE_DESCRIPTION
    ),
    extra_description=(
        'When language="csharp": ' + _GH_CSHARP_SCRIPT_CONTRACT
    ),
    pins_out_description=(
        'Output pin definitions as "Name:Type" strings or pin objects. '
        'For one Brep box output, use ["B:Brep"].'
    ),
)

_GH_CREATE_PYTHON_SCRIPT_SCHEMA: dict = _gh_create_script_schema(
    "gh_create_python_script",
    _TOOL_DESCRIPTIONS.get(
        "gh_create_python_script",
        'Alias for gh_create_script(language="python").',
    ),
    required=["code", "pins_in", "pins_out"],
    include_language=False,
)

_GH_CREATE_CSHARP_SCRIPT_SCHEMA: dict = _gh_create_script_schema(
    "gh_create_csharp_script",
    _TOOL_DESCRIPTIONS.get(
        "gh_create_csharp_script",
        'Alias for gh_create_script(language="csharp").',
    ),
    required=["code", "pins_in", "pins_out"],
    include_language=False,
    code_description=_GH_CSHARP_CODE_DESCRIPTION,
    extra_description=_GH_CSHARP_SCRIPT_CONTRACT,
    pins_out_description=(
        'Output pin definitions as "Name:Type" strings or pin objects, '
        'e.g. ["B:Brep"] for one box Brep output.'
    ),
)

_GH_CREATE_SCRIPT_SCHEMAS: Dict[str, dict] = {
    "gh_create_script": _GH_CREATE_SCRIPT_SCHEMA,
    "gh_create_python_script": _GH_CREATE_PYTHON_SCRIPT_SCHEMA,
    "gh_create_csharp_script": _GH_CREATE_CSHARP_SCRIPT_SCHEMA,
}


def _build_local_tool_catalog(local_tools: dict) -> Dict[str, dict]:
    """Build LiteLLM catalog entries for local Python tools."""
    catalog: Dict[str, dict] = {}
    for name in local_tools:
        if resolve_contained_tool(name) is not None:
            continue
        # Use the typed schema for ui_block instead of the generic fallback
        if name == "ui_block":
            catalog[name] = _UI_BLOCK_SCHEMA
            continue
        if name in _CHAT_MODEL_TOOL_SCHEMAS:
            catalog[name] = _CHAT_MODEL_TOOL_SCHEMAS[name]
            continue
        if name == "gh_update_script":
            catalog[name] = _GH_UPDATE_SCRIPT_SCHEMA
            continue
        if name in _GH_CREATE_SCRIPT_SCHEMAS:
            catalog[name] = _GH_CREATE_SCRIPT_SCHEMAS[name]
            continue
        desc = _TOOL_DESCRIPTIONS.get(name, f"Local tool: {name.replace('_', ' ')}")
        catalog[name] = {
            "type": "function",
            "function": {
                "name": name,
                "description": desc,
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": True,
                },
            },
        }
    return normalize_catalog(catalog)


class ChatRunner:
    """Executes conversation turns: LLM call + tool dispatch + streaming events.

    Uses ToolRegistry for progressive disclosure when available:
    - Agents start with ~12 Tier 0 tools
    - request_tools / search_tools meta-tools let the LLM load more
    - TOOL_GROUP_TRIGGERS auto-load related groups after tool use
    - Stale tools are deactivated after STALE_TOOL_TURNS rounds of disuse
    """

    def __init__(
        self,
        tool_executor: Optional[Any] = None,
        tool_access: str = "full",
        registry: Optional[ToolRegistry] = None,
        mcp_capability_executor: Optional[Any] = None,
    ):
        """Initialize the ChatRunner.

        Args:
            tool_executor: Async callable (name, params) -> result.
                If None, creates a ToolDispatcher with all three tiers.
            tool_access: "full" or "readonly" — controls which Tier 0 set is used.
            registry: Pre-built ToolRegistry. If None, builds one from
                cached catalog or fallback descriptions.
            mcp_capability_executor: Optional canonical MCP gateway executor.
        """
        if tool_access not in {"full", "readonly"}:
            raise ValueError("tool_access must be 'full' or 'readonly'")

        self._mcp_capability_executor = mcp_capability_executor
        self._mcp_capability_schemas = tuple(
            mcp_tool_to_litellm(tool)
            for tool in build_mcp_capability_gateway_tools()
        )

        # Set up tool execution
        if tool_executor:
            self._tool_executor = tool_executor
            self._dispatcher = None
        else:
            local_tools = build_local_tools()
            self._dispatcher = ToolDispatcher(local_tools=local_tools)
            self._tool_executor = self._dispatcher.dispatch

        # Set up progressive disclosure
        if registry is not None:
            self._registry = registry
        else:
            self._registry = self._build_registry(tool_access)

        # Track auto-loaded groups (reset per turn for shared runners)
        self._auto_loaded_groups: Set[str] = set()

        # Tool section cache — invalidated when active tool set changes
        self._tool_section_cache: Optional[str] = None
        self._tool_section_key: Optional[frozenset] = None

    def _get_active_tool_schemas(self) -> List[dict]:
        """Project the active model surface without mutating the registry."""
        schemas = [
            schema
            for schema in self._registry.get_active_schemas()
            if schema.get("function", {}).get("name")
            not in MCP_CAPABILITY_GATEWAY_NAMES
        ]
        if self._mcp_capability_executor is not None:
            schemas.extend(self._mcp_capability_schemas)
        return schemas

    def _build_registry(self, tool_access: str) -> ToolRegistry:
        """Build a ToolRegistry, preferring cached catalog with full schemas."""
        # Try cached catalog first (has parameter schemas from MCP server)
        catalog = load_catalog_from_cache()

        if catalog is None:
            # Fall back to minimal catalog (descriptions only, no param schemas)
            catalog = _build_fallback_catalog()
            logger.info(
                f"No catalog cache found — using fallback ({len(catalog)} tools). "
                f"The MCP runtime will populate the full schema cache when available."
            )
        else:
            logger.info(f"Loaded cached catalog with {len(catalog)} tools (with parameter schemas)")

        # Register local tools into catalog
        if self._dispatcher:
            local_catalog = _build_local_tool_catalog(self._dispatcher._local_tools)
            catalog.update(local_catalog)
        catalog.update(_CHAT_MODEL_TOOL_SCHEMAS)

        # Build registry with appropriate tier0
        chat_model_tier0 = {"list_chat_models", "set_chat_model"}
        if tool_access == "readonly":
            return ToolRegistry(
                catalog=catalog,
                tier0=READONLY_TIER_0 | chat_model_tier0,
                agent_mode=True,
            )
        return ToolRegistry(
            catalog=catalog,
            tier0=AGENT_TIER_0 | chat_model_tier0,
            agent_mode=True,
        )

    def _build_tool_section(self) -> str:
        """Build dynamic tool documentation to inject into the system prompt.

        Lists currently active tools and explains how to load more via
        request_tools / search_tools. This guidance is critical — without it
        the LLM doesn't know meta-tools exist and loops on the same tools.

        Cached between rounds — only rebuilt when the active tool set changes.
        """
        schemas = self._get_active_tool_schemas()
        cache_key = frozenset(
            s.get("function", {}).get("name", "") for s in schemas
        )
        if cache_key == self._tool_section_key and self._tool_section_cache is not None:
            return self._tool_section_cache
        tool_lines = []
        meta_tools = set()
        for schema in schemas:
            func = schema.get("function", {})
            name = func.get("name", "")
            desc = func.get("description", "")
            if not name:
                continue
            if self._registry.is_meta_tool(name):
                meta_tools.add(name)
                continue
            first_sentence = desc.split(". ")[0].split(".\n")[0]
            if first_sentence and not first_sentence.endswith("."):
                first_sentence += "."
            tool_lines.append(f"- `{name}` — {first_sentence}")
        tool_lines.sort()

        groups = self._registry.get_group_names()
        group_list = ", ".join(f"`{g}`" for g in groups[:15])
        if len(groups) > 15:
            group_list += f" ... ({len(groups)} total)"

        section = "\n\n## Available Tools\n\n"
        section += "These tools are loaded and ready to use:\n\n"
        section += "\n".join(tool_lines) if tool_lines else "(no tools loaded)"

        if meta_tools:
            section += "\n\n## Loading More Tools\n\n"
            section += (
                "You start with a focused set of tools. If you need tools not listed above:\n\n"
                "1. **`request_tools(group)`** — Load a named group of related tools. "
                f"Groups: {group_list}\n"
                "2. **`search_tools(query)`** — Search all tools by description and auto-load matches.\n\n"
                "**Use these BEFORE retrying a failed approach.** "
                "For example, if you need to create Grasshopper wiring, "
                "call `request_tools(\"gh_canvas\")` first.\n\n"
                "Stale tools are automatically evicted when you load new ones, "
                "so don't hesitate to load new groups as your task shifts domains "
                "(e.g., from Rhino modeling to Grasshopper wiring).\n"
            )

        self._tool_section_key = cache_key
        self._tool_section_cache = section
        return section

    def _build_runtime_fact_section(self, runtime_facts: dict[str, Any]) -> str:
        """Build a compact verified-facts section for prompt injection."""
        fact_lines = runtime_facts.get("verified_runtime_facts") or []
        if not fact_lines:
            return ""

        section = "\n\n## Verified Runtime Facts\n\n"
        section += "\n".join(f"- {line}" for line in fact_lines)
        section += (
            "\n\nTreat these facts as authoritative. Do not claim the Rhino tools are "
            "disconnected unless the verified runtime facts or a fresh tool result say so.\n"
        )
        return section

    async def _handle_list_chat_models(self, model_payload_builder: Optional[Any]) -> dict:
        """Return the chat model payload as an inline tool result."""
        if model_payload_builder is not None:
            payload = model_payload_builder()
            if inspect.isawaitable(payload):
                payload = await payload
        else:
            payload = await model_status.build_models_payload()
        return payload

    async def _handle_set_chat_model(
        self,
        conversation: Conversation,
        params: dict,
    ) -> dict:
        """Validate and stage a chat model override for the next turn."""
        if "api_base" in params:
            return {
                "success": False,
                "data": {
                    "error": "api_base is not allowed for set_chat_model.",
                    "code": "api_base_not_allowed",
                },
            }

        model_override = params.get("model_override")
        if not model_override:
            return {
                "success": False,
                "data": {
                    "error": "Missing required parameter: model_override",
                    "code": "missing_model_override",
                },
            }

        try:
            resolution = await model_status.resolve_allowed_model_override(model_override)
        except model_status.ModelOverrideUnavailable as exc:
            return {"success": False, "data": exc.to_payload()}

        reason = params.get("reason") or ""
        staged = conversation.stage_model_override(
            resolution,
            source="agent_tool",
            reason=reason,
        )
        return {
            "success": True,
            "model_override": resolution.model_override,
            "routing": resolution.routing,
            "provider": resolution.provider,
            "api_base_source": resolution.api_base_source,
            "applies_to": "next_turn",
            "message": "Model override staged for the next turn.",
            "staged": staged,
        }

    async def run_turn(
        self,
        conversation: Conversation,
        user_message: str,
        system_prompt: str,
        model_payload_builder: Optional[Any] = None,
    ) -> AsyncGenerator[ChatEvent, None]:
        """Run one conversation turn. Yields ChatEvent objects as they occur.

        Handles the full loop: LLM call -> tool calls -> LLM call -> ... -> done.
        Progressive disclosure: tool schemas update between rounds as groups
        are loaded via triggers, request_tools, or search_tools.
        """
        run_id = uuid.uuid4().hex[:8]
        conversation.active_run_id = run_id
        conversation.abort_event.clear()
        conversation.touch()

        # Repair previous cancelled turns before the new user message lands so
        # synthetic tool results stay adjacent to the assistant tool_calls.
        patched_pre = _patch_orphaned_tool_calls(conversation.messages)
        if patched_pre:
            logger.info(
                "Conversation %s: repaired %s orphaned tool_call(s) from prior cancelled turn(s)",
                conversation.id,
                patched_pre,
            )

        # Add user message to history
        conversation.messages.append({"role": "user", "content": user_message})

        total_input = 0
        total_output = 0
        start_time = time.time()
        substrate_observations: List[Any] = []
        runtime_facts = await collect_runtime_facts(
            include_gh=False, active_model=conversation.model
        )
        closing_due_to_generator_exit = False

        try:
            # Tool call loop -- keep calling LLM until it responds without tool calls
            consecutive_meta_only = 0
            for _round in range(MAX_TOOL_ROUNDS):
                if conversation.abort_event.is_set():
                    yield ChatEvent("error", content="Conversation cancelled")
                    return

                # Get current active tool schemas (changes as groups are loaded)
                tools = self._get_active_tool_schemas()

                # Build system prompt with verified runtime facts and dynamic tool
                # section (updates as tools load).
                full_prompt = (
                    system_prompt
                    + self._build_runtime_fact_section(runtime_facts)
                    + self._build_tool_section()
                )

                # Call LLM
                messages = [{"role": "system", "content": full_prompt}] + conversation.messages

                # Stream from LLM — emit text tokens as they arrive, accumulate tool calls
                text_parts: List[str] = []
                tool_calls_acc: List[Dict[str, str]] = []
                tool_call_slot_by_index: Dict[int, int] = {}

                try:
                    llm_kwargs = dict(
                        model=conversation.model,
                        messages=messages,
                        tools=tools if tools else None,
                        tool_choice="auto" if tools else None,
                        max_tokens=2048,
                        temperature=0.7,
                        stream=True,
                        stream_options={"include_usage": True},
                    )
                    llm_kwargs = sanitize_generation_params_for_model(
                        conversation.model,
                        llm_kwargs,
                    )
                    if conversation.api_base:
                        llm_kwargs["api_base"] = conversation.api_base
                    stream = await litellm.acompletion(**llm_kwargs)
                    async for chunk in stream:
                        if not chunk.choices:
                            # Final chunk may carry usage with no choices
                            if hasattr(chunk, "usage") and chunk.usage:
                                total_input += getattr(chunk.usage, "prompt_tokens", 0)
                                total_output += getattr(chunk.usage, "completion_tokens", 0)
                            continue

                        delta = chunk.choices[0].delta

                        # Stream text tokens immediately
                        if delta.content:
                            text_parts.append(delta.content)
                            yield ChatEvent("text_delta", content=delta.content)

                        # Accumulate tool call deltas by index
                        if delta.tool_calls:
                            for tc_delta in delta.tool_calls:
                                idx = tc_delta.index
                                slot = tool_call_slot_by_index.get(idx)
                                incoming_id = tc_delta.id or ""
                                if (
                                    slot is None
                                    or (
                                        incoming_id
                                        and tool_calls_acc[slot]["id"]
                                        and incoming_id != tool_calls_acc[slot]["id"]
                                    )
                                ):
                                    tool_calls_acc.append({"id": "", "name": "", "arguments": ""})
                                    slot = len(tool_calls_acc) - 1
                                    tool_call_slot_by_index[idx] = slot
                                acc = tool_calls_acc[slot]
                                if tc_delta.id:
                                    acc["id"] = tc_delta.id
                                if tc_delta.function:
                                    if tc_delta.function.name:
                                        acc["name"] += tc_delta.function.name
                                    if tc_delta.function.arguments:
                                        acc["arguments"] += tc_delta.function.arguments

                        if hasattr(chunk, "usage") and chunk.usage:
                            total_input += getattr(chunk.usage, "prompt_tokens", 0)
                            total_output += getattr(chunk.usage, "completion_tokens", 0)

                except Exception as e:
                    logger.error(f"LLM call failed: {e}")
                    yield ChatEvent("error", content=f"LLM error: {e}")
                    return

                # Reconstruct complete assistant message from accumulated stream
                full_text = "".join(text_parts)
                tool_calls_list = tool_calls_acc

                assistant_msg: Dict[str, Any] = {"role": "assistant"}
                if full_text:
                    assistant_msg["content"] = full_text
                if tool_calls_list:
                    assistant_msg["tool_calls"] = [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": tc["arguments"],
                            },
                        }
                        for tc in tool_calls_list
                    ]
                conversation.messages.append(assistant_msg)

                # No tool calls -- we're done
                if not tool_calls_list:
                    break

                # Adapt tool_calls_list to iterable with .id/.function attributes
                # so the dispatch loop below can use tc.id and tc.function.name/arguments
                class _ToolCall:
                    def __init__(self, d: dict):
                        self.id = d["id"]
                        class _Fn:
                            def __init__(self, name: str, args: str):
                                self.name = name
                                self.arguments = args
                        self.function = _Fn(d["name"], d["arguments"])

                choice_tool_calls = [_ToolCall(tc) for tc in tool_calls_list]

                # Execute tool calls
                tools_used: Set[str] = set()
                meta_only_round = True
                for tc in choice_tool_calls:
                    tool_name = tc.function.name
                    denial = deny_if_contained(tool_name, DispatchOrigin.ROOK_CHAT)
                    if denial is not None:
                        meta_only_round = False
                        conversation.messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": json.dumps(denial, separators=(",", ":")),
                        })
                        continue
                    try:
                        params = json.loads(tc.function.arguments) if tc.function.arguments else {}
                    except json.JSONDecodeError:
                        params = {}

                    # Intercept ui_block pseudo-tool — emit UI event, skip dispatch
                    if tool_name == "ui_block":
                        block_id = f"blk_{uuid.uuid4().hex[:8]}"
                        yield ChatEvent(
                            type="ui_block",
                            block_id=block_id,
                            block_type=params.get("block_type"),
                            block_config=params.get("config"),
                        )
                        conversation.messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": json.dumps({"block_id": block_id, "status": "rendered"}),
                        })
                        continue

                    if tool_name in _CHAT_MODEL_TOOL_SCHEMAS:
                        meta_only_round = False
                        tools_used.add(tool_name)
                        yield ChatEvent(
                            "tool_start",
                            name=tool_name,
                            params=params,
                            tool_call_id=tc.id,
                        )

                        if tool_name == "list_chat_models":
                            result = await self._handle_list_chat_models(model_payload_builder)
                        else:
                            result = await self._handle_set_chat_model(conversation, params)
                        result_str = json.dumps(result)

                        conversation.messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": result_str,
                        })

                        result_view = normalize_tool_result(result)

                        yield ChatEvent(
                            "tool_result",
                            name=tool_name,
                            result=result_str,
                            tool_call_id=tc.id,
                            tool_status=result_view.status,
                            verified=result_view.verified,
                            verification_note=result_view.verification_note,
                        )

                        if tool_name == "set_chat_model" and result.get("success"):
                            yield ChatEvent(
                                "model_update",
                                content=result.get("message"),
                                model=result.get("model_override"),
                                applies_to="next_turn",
                                result=result_str,
                            )
                        continue

                    yield ChatEvent("tool_start", name=tool_name, params=params, tool_call_id=tc.id)

                    # Handle meta-tools internally (request_tools, search_tools)
                    if self._registry.is_meta_tool(tool_name):
                        result = self._handle_meta_tool(tool_name, params)
                        result_str = json.dumps(result)
                    elif tool_name in MCP_CAPABILITY_GATEWAY_NAMES:
                        if tool_name == "rook_tools_call":
                            meta_only_round = False
                        try:
                            if self._mcp_capability_executor is None:
                                result = {
                                    "success": False,
                                    "error": (
                                        "Canonical MCP capability gateway is unavailable."
                                    ),
                                }
                            else:
                                result = await self._mcp_capability_executor(
                                    tool_name, params
                                )
                            result_str = (
                                json.dumps(result)
                                if isinstance(result, dict)
                                else str(result)
                            )
                        except Exception as e:
                            result = {"success": False, "error": str(e)}
                            result_str = json.dumps(result)
                    else:
                        meta_only_round = False
                        result = None
                        try:
                            result = await self._tool_executor(tool_name, params)
                            # Post-dispatch verification (needs_verification + annotate_result)
                            # is now handled inside ToolDispatcher.dispatch() — the single
                            # enforcement point for both chat and agent paths.
                            result_str = json.dumps(result) if isinstance(result, dict) else str(result)
                            if isinstance(result, dict):
                                _obs = extract_substrate_observation(tool_name, result)
                                if _obs is not None:
                                    substrate_observations.append(_obs)
                                    try:
                                        persist_substrate_observation(
                                            _obs,
                                            error=_substrate_compact_error(result),
                                            session_id=getattr(conversation, "id", "") or "",
                                        )
                                    except Exception as _persist_exc:
                                        logger.debug(
                                            "Substrate persistence skipped for %s: %s",
                                            tool_name,
                                            _persist_exc,
                                        )
                        except Exception as e:
                            result = {"success": False, "error": str(e)}
                            result_str = json.dumps(result)
                        tools_used.add(tool_name)

                    # Commit the completed result before yielding it. If the
                    # client disconnects while the event is being written, the
                    # server closes this generator and the repair pass must see
                    # the real result, not synthesize a cancellation.
                    conversation.messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result_str,
                    })

                    result_view = normalize_tool_result(result)

                    yield ChatEvent(
                        "tool_result",
                        name=tool_name,
                        result=result_str,
                        tool_call_id=tc.id,
                        verified=result_view.verified,
                        verification_note=result_view.verification_note,
                        tool_status=result_view.status,
                    )

                # Track consecutive meta-only rounds (tool discovery loops)
                if meta_only_round:
                    consecutive_meta_only += 1
                    if consecutive_meta_only >= MAX_META_ONLY_ROUNDS:
                        logger.warning(
                            f"Conversation {conversation.id}: {consecutive_meta_only} "
                            f"consecutive meta-only rounds — agent stuck in discovery loop"
                        )
                        yield ChatEvent("error", content=(
                            "Agent stuck loading tools without using them. "
                            "Try rephrasing your request."
                        ))
                        break
                else:
                    consecutive_meta_only = 0

                # Progressive disclosure: update active tools after each round
                if tools_used:
                    self._update_tool_surface(tools_used, _round)

            else:
                # Exhausted MAX_TOOL_ROUNDS without a final text-only response
                logger.warning(f"Conversation {conversation.id} hit {MAX_TOOL_ROUNDS} tool rounds limit")
                yield ChatEvent("error", content="Too many tool calls — stopping to prevent runaway loop")

        except GeneratorExit:
            closing_due_to_generator_exit = True
            raise

        finally:
            patched_post = _patch_orphaned_tool_calls(conversation.messages)
            if patched_post:
                logger.info(
                    "Conversation %s: repaired %s orphaned tool_call(s) on turn exit",
                    conversation.id,
                    patched_post,
                )

            applied_model_update = conversation.apply_pending_model_override()
            wall_time = time.time() - start_time
            conversation.active_run_id = None
            conversation.touch()
            done_usage: Dict[str, Any] = {
                "input_tokens": total_input,
                "output_tokens": total_output,
                "wall_time_s": round(wall_time, 2),
                "active_tools": len(self._get_active_tool_schemas()),
            }
            if substrate_observations:
                done_usage["substrate_summary"] = summarize_substrate_observations(substrate_observations)
            done_usage["runtime_facts"] = {
                "rhino_connected": runtime_facts.get("rhino", {}).get("connected", False),
                "prompt_available": runtime_facts.get("prompt", {}).get("available", False),
            }
            if not closing_due_to_generator_exit:
                if applied_model_update:
                    active_model = applied_model_update.get("active_model")
                    yield ChatEvent(
                        "model_update",
                        content=(
                            "Model switch applied. Future turns in this conversation will use "
                            f"{active_model}."
                        ),
                        model=active_model,
                        applies_to="active",
                        result=json.dumps(applied_model_update),
                    )
                yield ChatEvent("done", usage=done_usage)

    def _handle_meta_tool(self, name: str, params: dict) -> dict:
        """Handle request_tools and search_tools internally."""
        if name == "request_tools":
            group = params.get("group", "")
            result = self._registry.request_group(group)
            if result.get("success"):
                loaded = result.get("loaded") or []
                already_active = result.get("already_active") or []
                if loaded:
                    result["status"] = "loaded"
                    result["message"] = (
                        f"Loaded {len(loaded)} tool(s) from {group}. "
                        "Call the needed tool directly next."
                    )
                elif already_active:
                    result["status"] = "already_loaded"
                    result["message"] = (
                        f"{group} is already loaded; no new tools were added."
                    )
                    result["next_action"] = "call the needed Grasshopper tool directly."
                else:
                    result["status"] = "empty"
                    result["message"] = f"No tools were loaded for {group}."
            return result
        if name == "search_tools":
            return self._registry.search(
                params.get("query", ""),
                top_k=params.get("top_k", 5),
            )
        return {"error": f"Unknown meta-tool: {name}"}

    def _update_tool_surface(self, tools_used: Set[str], round_num: int) -> None:
        """Update progressive disclosure after tool use.

        1. Mark tools as used (for staleness tracking)
        2. Auto-load related groups via TOOL_GROUP_TRIGGERS
        3. Deactivate stale tools
        """
        self._registry.mark_used(tools_used, round_num)

        # Auto-load triggered groups
        for tool_name in tools_used:
            group = TOOL_GROUP_TRIGGERS.get(tool_name)
            if group and group not in self._auto_loaded_groups:
                result = self._registry.request_group(group, turn=round_num)
                if result.get("success") and result.get("loaded"):
                    self._auto_loaded_groups.add(group)
                    logger.info(
                        f"Auto-loaded group '{group}' (triggered by {tool_name}): "
                        f"{result['loaded']}"
                    )

        # Deactivate stale tools (only after enough rounds to be meaningful)
        if round_num >= STALE_TOOL_TURNS:
            removed = self._registry.deactivate_stale(STALE_TOOL_TURNS)
            if removed:
                logger.info(f"Deactivated {len(removed)} stale tools")

    async def cancel(self, conversation: Conversation):
        """Cancel an in-progress turn."""
        conversation.abort_event.set()
