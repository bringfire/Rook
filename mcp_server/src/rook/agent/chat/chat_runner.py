"""ChatRunner — executes conversation turns with LLM + tool dispatch.

Uses the ToolRegistry for progressive tool disclosure:
  - Tier 0: ~12 always-active tools (execute_intent, knowledge_query, objects, ping)
  - Tier 1: Named groups loaded via request_tools("gh_canvas")
  - Tier 2: Individual tools found via search_tools("boolean")
  - Auto-triggers: using rhino_create auto-loads rhino_transform group

The LLM starts with a small, focused tool set and dynamically loads more as needed.
"""
import json
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Dict, List, Optional, Set

import litellm

from .conversation_store import Conversation
# execution_policy verification (needs_verification + annotate_result) is now
# handled inside ToolDispatcher.dispatch() — the single enforcement point.
from .runtime_health import collect_runtime_facts
from ..substrate_analytics import extract_substrate_observation, summarize_substrate_observations
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
)

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 50  # GH definitions need many rounds (create, wire, set, verify per component)
MAX_META_ONLY_ROUNDS = 5  # Cap on consecutive rounds that only call meta-tools
STALE_TOOL_TURNS = 8  # Deactivate tools unused for this many rounds


@dataclass
class ChatEvent:
    """A streaming event emitted during a conversation turn."""
    type: str  # text_delta, tool_start, tool_result, done, error, ui_block
    content: Optional[str] = None
    name: Optional[str] = None
    params: Optional[Dict] = None
    result: Optional[str] = None
    usage: Optional[Dict] = None
    # ── Adaptive UI fields ──
    tool_call_id: Optional[str] = None
    block_id: Optional[str] = None
    block_type: Optional[str] = None
    block_config: Optional[Dict] = None
    verified: Optional[bool] = None
    verification_note: Optional[str] = None

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
    "rhino_command_prompt": "Read Rhino's current command prompt state. Returns {prompt, is_active}. If is_active=true after execution, Rhino is waiting for input and the command did not complete.",
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
    "rhino_layer_rename": "Rename a layer",
    "rhino_layer_move_objects": "Move all objects from one layer to another",
    "rhino_layer_merge": "Move objects from source to target layer, then delete source",
    "rhino_layer_dependencies": "Analyze what holds a layer alive (objects, block refs, children, canDelete)",
    # Rhino transform tools
    "rhino_boolean": "Boolean operations (union, difference, intersection) on solids",
    "rhino_loft": "Create a surface by lofting through curves",
    "rhino_sweep": "Sweep a profile curve along a rail curve",
    "rhino_extrude": "Extrude a curve to create a surface or solid",
    "rhino_text": "Create 3D text objects",
    "rhino_execute_intent": "Execute a Rhino intent through the typed runtime. It prefers direct API routes, but can fall back to command or interactive substrates for ambiguous requests.",
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
    "gh_set_script": "Set the script content of a C#/Python script component",
    "gh_inspect_output": "Inspect the output data of a component",
    # Knowledge
    "knowledge_query": "Query the Rhino command knowledge store",
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
}


def _build_fallback_catalog() -> Dict[str, dict]:
    """Build a minimal LiteLLM catalog from known tool names when no cache exists.

    This catalog has descriptions but no parameter schemas (additionalProperties: True).
    Once the MCP server caches a full catalog (via spawn_agent), subsequent ChatRunner
    instances will get proper parameter schemas automatically.
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
    return catalog


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


def _build_local_tool_catalog(local_tools: dict) -> Dict[str, dict]:
    """Build LiteLLM catalog entries for local Python tools."""
    catalog: Dict[str, dict] = {}
    for name in local_tools:
        # Use the typed schema for ui_block instead of the generic fallback
        if name == "ui_block":
            catalog[name] = _UI_BLOCK_SCHEMA
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
    return catalog


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
    ):
        """Initialize the ChatRunner.

        Args:
            tool_executor: Async callable (name, params) -> result.
                If None, creates a ToolDispatcher with all three tiers.
            tool_access: "full" or "readonly" — controls which Tier 0 set is used.
            registry: Pre-built ToolRegistry. If None, builds one from
                cached catalog or fallback descriptions.
        """
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

    def _build_registry(self, tool_access: str) -> ToolRegistry:
        """Build a ToolRegistry, preferring cached catalog with full schemas."""
        # Try cached catalog first (has parameter schemas from MCP server)
        catalog = load_catalog_from_cache()

        if catalog is None:
            # Fall back to minimal catalog (descriptions only, no param schemas)
            catalog = _build_fallback_catalog()
            logger.info(
                f"No catalog cache found — using fallback ({len(catalog)} tools). "
                f"Run spawn_agent once to generate full catalog with parameter schemas."
            )
        else:
            logger.info(f"Loaded cached catalog with {len(catalog)} tools (with parameter schemas)")

        # Register local tools into catalog
        if self._dispatcher:
            local_catalog = _build_local_tool_catalog(self._dispatcher._local_tools)
            catalog.update(local_catalog)

        # Build registry with appropriate tier0
        if tool_access == "readonly":
            return ToolRegistry(
                catalog=catalog,
                tier0=READONLY_TIER_0,
                agent_mode=True,
            )
        return ToolRegistry(catalog=catalog, agent_mode=True)

    def _build_tool_section(self) -> str:
        """Build dynamic tool documentation to inject into the system prompt.

        Lists currently active tools and explains how to load more via
        request_tools / search_tools. This guidance is critical — without it
        the LLM doesn't know meta-tools exist and loops on the same tools.

        Cached between rounds — only rebuilt when the active tool set changes.
        """
        schemas = self._registry.get_active_schemas()
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

    async def run_turn(
        self,
        conversation: Conversation,
        user_message: str,
        system_prompt: str,
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

        # Add user message to history
        conversation.messages.append({"role": "user", "content": user_message})

        total_input = 0
        total_output = 0
        start_time = time.time()
        substrate_observations: List[Any] = []
        runtime_facts = await collect_runtime_facts(include_gh=False)

        try:
            # Tool call loop -- keep calling LLM until it responds without tool calls
            consecutive_meta_only = 0
            for _round in range(MAX_TOOL_ROUNDS):
                if conversation.abort_event.is_set():
                    yield ChatEvent("error", content="Conversation cancelled")
                    return

                # Get current active tool schemas (changes as groups are loaded)
                tools = self._registry.get_active_schemas()

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
                tool_calls_acc: Dict[int, Dict[str, str]] = {}  # index -> {id, name, arguments}

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
                                if idx not in tool_calls_acc:
                                    tool_calls_acc[idx] = {"id": "", "name": "", "arguments": ""}
                                if tc_delta.id:
                                    tool_calls_acc[idx]["id"] = tc_delta.id
                                if tc_delta.function:
                                    if tc_delta.function.name:
                                        tool_calls_acc[idx]["name"] += tc_delta.function.name
                                    if tc_delta.function.arguments:
                                        tool_calls_acc[idx]["arguments"] += tc_delta.function.arguments

                        if hasattr(chunk, "usage") and chunk.usage:
                            total_input += getattr(chunk.usage, "prompt_tokens", 0)
                            total_output += getattr(chunk.usage, "completion_tokens", 0)

                except Exception as e:
                    logger.error(f"LLM call failed: {e}")
                    yield ChatEvent("error", content=f"LLM error: {e}")
                    return

                # Reconstruct complete assistant message from accumulated stream
                full_text = "".join(text_parts)
                tool_calls_list = [tool_calls_acc[i] for i in sorted(tool_calls_acc.keys())]

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

                    yield ChatEvent("tool_start", name=tool_name, params=params, tool_call_id=tc.id)

                    # Handle meta-tools internally (request_tools, search_tools)
                    if self._registry.is_meta_tool(tool_name):
                        result = self._handle_meta_tool(tool_name, params)
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
                        except Exception as e:
                            result_str = f"Error: {e}"
                        tools_used.add(tool_name)

                    # Hoist verification fields onto the event for frontend rendering
                    _verified = None
                    _verification_note = None
                    if isinstance(result, dict):
                        _verified = result.get("verified")
                        _verification_note = result.get("verification_note")

                    yield ChatEvent(
                        "tool_result",
                        name=tool_name,
                        result=result_str,
                        tool_call_id=tc.id,
                        verified=_verified,
                        verification_note=_verification_note,
                    )

                    # Add tool result to history
                    conversation.messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result_str,
                    })

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

        finally:
            wall_time = time.time() - start_time
            conversation.active_run_id = None
            conversation.touch()
            done_usage: Dict[str, Any] = {
                "input_tokens": total_input,
                "output_tokens": total_output,
                "wall_time_s": round(wall_time, 2),
                "active_tools": self._registry.get_active_count(),
            }
            if substrate_observations:
                done_usage["substrate_summary"] = summarize_substrate_observations(substrate_observations)
            done_usage["runtime_facts"] = {
                "rhino_connected": runtime_facts.get("rhino", {}).get("connected", False),
                "prompt_available": runtime_facts.get("prompt", {}).get("available", False),
            }
            yield ChatEvent("done", usage=done_usage)

    def _handle_meta_tool(self, name: str, params: dict) -> dict:
        """Handle request_tools and search_tools internally."""
        if name == "request_tools":
            return self._registry.request_group(params.get("group", ""))
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
