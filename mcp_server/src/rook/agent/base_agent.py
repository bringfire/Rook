"""
Rook Agent
==========

The core agent loop. Ported from Engram's EngramAgent, adapted for
Rook's HTTP bridge and knowledge stores.

Usage:
    from rook.agent import RookAgent, AgentConfig

    agent = RookAgent(config=AgentConfig())
    await agent.prompt("Create a box at the origin")
    await agent.wait_for_idle()

The loop:
    prompt -> _transform_context (Seam 1) -> model -> tool calls ->
    _execute_tool (Seam 2+3) -> _post_turn_adapt (Seam 4) -> repeat

Terminates when:
    - Model returns a response with no tool calls, AND
    - No steering messages queued, AND
    - No follow-up messages queued
"""

import asyncio
import inspect
import json
import logging
import time as _time
import uuid
from typing import Any, Callable, Dict, List, Optional, Set, TYPE_CHECKING

if TYPE_CHECKING:
    from .tool_registry import ToolRegistry
    from .plan_graph_live import LiveProducerResult
    from ..learning.plan_graph import PlanGraph

import litellm

from .config import AgentConfig
from .generation_params import sanitize_generation_params_for_model
from .events import (
    AgentEvent, EventDispatcher,
    AGENT_START, AGENT_END,
    TURN_START, TURN_END,
    MESSAGE_START, MESSAGE_UPDATE, MESSAGE_END,
    TOOL_EXEC_START, TOOL_EXEC_END,
    KNOWLEDGE_INJECT,
    TOOL_GROUP_LOADED, TOOL_GROUP_UNLOADED,
    AGENT_ASK,
    ERROR,
)
from .tool_groups import TOOL_TRANSITIONS, TOOL_GROUP_TRIGGERS
from .plan_graph_live_dispatch import run_live_producer_node_with_executor
from .substrate_analytics import (
    extract_substrate_observation,
    persist_substrate_observation,
    _compact_error as _substrate_compact_error,
)
from ..tool_lifecycle import filter_litellm_schemas, filter_local_registrations
from ..runtime_paths import (
    load_runtime_dotenv,
    resolve_readable_knowledge_path,
    resolve_writable_knowledge_path,
)

logger = logging.getLogger(__name__)

# Type alias for tool executor functions
# Signature: async (tool_name: str, params: dict) -> dict
ToolExecutor = Callable[[str, Dict[str, Any]], Any]

# Rhino write-path tools that return newly created object GUIDs via data.id.
# Mirrors CREATION_TOOLS in agent/chat/execution_policy.py — keep both in sync.
# GH tools are deliberately excluded: they use a different ID namespace
# (temp_id_map short IDs) and are validated via /gh/errors, not /geometry.
_RHINO_CREATION_TOOLS = frozenset({
    "rhino_create",     # /create → data.id (ObjectSnapshot)
    "rhino_boolean",    # /boolean → data.id
    "rhino_extrude",    # /extrude → data.id
})


# =============================================================================
# Knowledge Infrastructure (lazy-loaded singletons)
# =============================================================================

_knowledge_infra = None


def _get_knowledge_infra() -> Dict[str, Any]:
    """Lazy-load Rook knowledge singletons.

    Returns dict with None for unavailable components. This wires
    into the existing knowledge stores rather than creating new ones.
    """
    global _knowledge_infra
    if _knowledge_infra is not None:
        return _knowledge_infra

    infra: Dict[str, Any] = {
        "unified_store": None,
        "command_store": None,
        "operations_knowledge": None,
        "metrics": None,
    }

    try:
        from ..learning.unified_store import UnifiedStore
        readable_notes_dir = resolve_readable_knowledge_path("gh", "notes")
        if readable_notes_dir.exists():
            infra["unified_store"] = UnifiedStore()
    except Exception as e:
        logger.debug(f"UnifiedStore unavailable: {e}")

    try:
        from ..learning.command_knowledge_store import CommandKnowledgeStore
        command_path = resolve_readable_knowledge_path("commands", "command_knowledge.json")
        if command_path.exists():
            infra["command_store"] = CommandKnowledgeStore()
    except Exception as e:
        logger.debug(f"CommandKnowledgeStore unavailable: {e}")

    try:
        ops_path = resolve_readable_knowledge_path("gh", "operations_knowledge.json")
        if ops_path.exists():
            with open(ops_path, "r", encoding="utf-8") as f:
                infra["operations_knowledge"] = json.load(f)
    except Exception as e:
        logger.debug(f"Operations knowledge unavailable: {e}")

    try:
        from ..learning.metrics_store import MetricsStore
        metrics_path = resolve_writable_knowledge_path("agent_metrics.json")
        infra["metrics"] = MetricsStore(metrics_path)
    except Exception as e:
        logger.debug(f"Metrics store unavailable: {e}")

    _knowledge_infra = infra
    return infra


class RookAgent:
    """The agent loop. Ported from Engram's EngramAgent.

    Uses the HTTP bridge instead of a TCP socket.
    Wires into Rook's UnifiedStore/CommandKnowledgeStore instead of
    Engram's tool_knowledge packs.

    The loop:
        prompt -> _transform_context (Seam 1) -> model -> tool calls ->
        _execute_tool (Seam 2+3) -> _post_turn_adapt (Seam 4) -> repeat

    Terminates when:
        - Model returns a response with no tool calls, AND
        - No steering messages queued, AND
        - No follow-up messages queued
    """

    def __init__(
        self,
        config: Optional[AgentConfig] = None,
        tool_executor: Optional[ToolExecutor] = None,
        tool_schemas: Optional[List[dict]] = None,
        tool_registry: Optional["ToolRegistry"] = None,
    ):
        """Initialize the agent.

        Args:
            config: Agent configuration. Uses defaults if not provided.
            tool_executor: Async callable (name, params) -> dict that executes tools.
                          If None, auto-builds a ToolDispatcher (direct bridge access).
            tool_schemas: List of LiteLLM-format tool schemas. Fallback when no registry.
            tool_registry: ToolRegistry for progressive disclosure.
                          When provided, overrides tool_schemas.
        """
        self.config = config or AgentConfig()

        if tool_executor is None:
            from .tool_dispatcher import ToolDispatcher, build_local_tools
            dispatcher = ToolDispatcher()
            dispatcher.register_locals(build_local_tools())
            self._tool_executor = dispatcher.dispatch
            logger.info("Auto-built ToolDispatcher (direct bridge, no MCP overhead)")
        else:
            self._tool_executor = tool_executor
        self._tool_schemas = filter_litellm_schemas(tool_schemas or [])
        self._tool_registry = tool_registry

        # Event system
        self._events = EventDispatcher()

        # Conversation state
        self.messages: List[dict] = []
        self._session_id = str(uuid.uuid4())[:8]

        # Pi-agent-core control flow
        self._steering_queue: List[str] = []
        self._followup_queue: List[str] = []
        self._abort = False
        self._turn_count = 0
        self._state = "idle"  # "idle" | "running" | "aborting"

        # Idle event for wait_for_idle()
        self._idle_event = asyncio.Event()
        self._idle_event.set()  # Starts idle

        # Cost tracking
        self._total_cost = 0.0
        self._total_input_tokens = 0
        self._total_output_tokens = 0

        # Knowledge seam state (Seam 4)
        self._auto_loaded_groups: Set[str] = set()

        # Local tools (execute in Python, bypass bridge)
        self._local_tools: Dict[str, Any] = {}

        # Failure counting for Seam 3 attempt_number tracking
        self._failure_counts: Dict[str, int] = {}

        # Escalation: ask_human support (Phase 3)
        self._pending_ask: Optional[Dict[str, Any]] = None
        self._ask_future: Optional[asyncio.Future] = None
        self._ask_timeout: float = 300.0  # 5 minutes

        # Load .env for API keys
        self._load_env()

    # =========================================================================
    # Public API (pi-agent-core pattern)
    # =========================================================================

    async def prompt(self, message: str) -> None:
        """Start new work with a user message.

        Adds the message to conversation history and runs the loop until
        the model is done.
        """
        self.messages.append({"role": "user", "content": message})
        self._turn_count = 0
        self._abort = False
        await self._run_loop()

    async def continue_(self) -> None:
        """Resume processing from current context.

        Use when the model stopped (e.g., hit max_turns) but you want
        it to keep going.
        """
        self._turn_count = 0
        self._abort = False
        await self._run_loop()

    def steer(self, message: str) -> None:
        """Interrupt the agent mid-execution with a new directive.

        The message is injected between tool calls in the current turn.
        """
        self._steering_queue.append(message)
        logger.info(f"Steering queued: {message[:80]}...")

    def follow_up(self, message: str) -> None:
        """Queue a message for after the current work completes."""
        self._followup_queue.append(message)
        logger.info(f"Follow-up queued: {message[:80]}...")

    def abort(self) -> None:
        """Cancel the current operation.

        The loop exits after the current tool call finishes.
        """
        self._abort = True
        self._state = "aborting"
        logger.info("Abort requested")

    def subscribe(self, callback: Callable[[AgentEvent], None]) -> Callable[[], None]:
        """Subscribe to agent events. Returns unsubscribe function."""
        return self._events.subscribe(callback)

    def emit_event(self, event: AgentEvent) -> None:
        """Emit an event (used by Guardian and other observers)."""
        self._events.emit(event)

    async def wait_for_idle(self) -> None:
        """Wait until the agent finishes processing."""
        await self._idle_event.wait()

    # =========================================================================
    # Escalation: ask_human
    # =========================================================================

    async def ask_human(self, question: str, context: str = "") -> str:
        """Pause execution and ask the human a question.

        Creates an asyncio.Future, stores the question in _pending_ask,
        emits AGENT_ASK event, and awaits the future with timeout.
        Returns the human's answer string, or a timeout fallback message.
        """
        loop = asyncio.get_running_loop()
        self._ask_future = loop.create_future()
        self._pending_ask = {
            "question": question,
            "context": context,
            "timestamp": _time.time(),
        }

        self._events.emit(AgentEvent(AGENT_ASK, {
            "question": question,
            "context": context,
        }))

        logger.info(f"Agent asking human: {question[:80]}...")

        try:
            answer = await asyncio.wait_for(self._ask_future, timeout=self._ask_timeout)
            return answer
        except asyncio.TimeoutError:
            logger.warning("ask_human timed out after %.0fs", self._ask_timeout)
            return (
                f"[No human response after {self._ask_timeout:.0f}s. "
                f"Proceed with your best judgment or skip this step.]"
            )
        finally:
            self._pending_ask = None
            self._ask_future = None

    def resolve_ask(self, answer: str) -> bool:
        """Deliver the human's answer to a pending ask_human call.

        Returns True if there was a pending ask, False otherwise.
        """
        if self._ask_future is None or self._ask_future.done():
            return False
        self._ask_future.set_result(answer)
        return True

    @property
    def pending_ask(self) -> Optional[Dict[str, Any]]:
        """Return the pending question dict, or None if not waiting."""
        return self._pending_ask

    # =========================================================================
    # State management
    # =========================================================================

    def set_system_prompt(self, prompt: str) -> None:
        """Override the system prompt."""
        self.config.system_prompt = prompt

    def set_model(self, model: str) -> None:
        """Change the LLM model."""
        self.config.model = model

    def set_tool_schemas(self, schemas: List[dict]) -> None:
        """Replace the active tool schemas."""
        self._tool_schemas = filter_litellm_schemas(schemas)

    def set_tool_executor(self, executor: ToolExecutor) -> None:
        """Replace the tool executor."""
        self._tool_executor = executor

    def register_local_tools(self, tools: Dict[str, Any]) -> None:
        """Register local tools that execute in Python (bypass bridge).

        Args:
            tools: Dict mapping tool_name -> async callable(params) -> dict.
        """
        admitted = filter_local_registrations(tools)
        self._local_tools.update(admitted)
        logger.info(
            f"Registered {len(admitted)} local tools: {list(admitted.keys())}"
        )

    def clear_messages(self) -> None:
        """Clear conversation history and related seam state."""
        self.messages = []
        self._auto_loaded_groups = set()

    def reset(self) -> None:
        """Full reset: clear messages, queues, counters, tool registry."""
        self.messages = []
        self._steering_queue = []
        self._followup_queue = []
        self._abort = False
        self._turn_count = 0
        self._state = "idle"
        self._total_cost = 0.0
        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self._auto_loaded_groups = set()
        if self._tool_registry:
            self._tool_registry.reset()

    @property
    def state(self) -> str:
        return self._state

    @property
    def turn_count(self) -> int:
        return self._turn_count

    @property
    def cost(self) -> float:
        return self._total_cost

    @property
    def total_cost(self) -> float:
        return self._total_cost

    @property
    def token_usage(self) -> dict:
        return {
            "input": self._total_input_tokens,
            "output": self._total_output_tokens,
            "total": self._total_input_tokens + self._total_output_tokens,
        }

    # =========================================================================
    # The Loop
    # =========================================================================

    async def _run_loop(self) -> None:
        """Main agent loop. Runs until model has no more tool calls."""
        self._state = "running"
        self._idle_event.clear()
        self._events.emit(AgentEvent(AGENT_START, {
            "session_id": self._session_id,
            "model": self.config.model,
        }))

        try:
            _has_more_work = True
            while _has_more_work:
                _has_more_work = False  # Will be set True if follow-ups exist

                while self._turn_count < self.config.max_turns:
                    if self._abort:
                        logger.info(f"Aborted after {self._turn_count} turns")
                        break

                    # Check token budget
                    if self._total_input_tokens >= self.config.max_input_tokens_per_task:
                        logger.warning(f"Token budget exhausted: {self._total_input_tokens}")
                        self._events.emit(AgentEvent(ERROR, {
                            "message": f"Token budget exhausted ({self._total_input_tokens} tokens)"
                        }))
                        break

                    # Inject steering messages
                    if self._steering_queue:
                        msg = self._steering_queue.pop(0)
                        self.messages.append({"role": "user", "content": msg})
                        logger.info(f"Steering injected: {msg[:80]}...")

                    self._turn_count += 1
                    self._events.emit(AgentEvent(TURN_START, {
                        "turn": self._turn_count,
                        "message_count": len(self.messages),
                    }))

                    # --- SEAM 1: Transform context (knowledge injection) ---
                    context = self._transform_context(self.messages)

                    # --- Call model ---
                    self._events.emit(AgentEvent(MESSAGE_START, {
                        "model": self.config.model,
                        "tool_count": len(self._get_tool_schemas()),
                    }))

                    llm_response = await self._call_model(context)

                    if llm_response is None:
                        break

                    choice = llm_response.choices[0]
                    message = choice.message
                    self._track_usage(llm_response)

                    # Append assistant message to history
                    self.messages.append(self._message_to_dict(message))

                    # Extract text content
                    text_content = message.content or ""

                    # If no tool calls, we're done with the inner loop
                    if not message.tool_calls:
                        self._events.emit(AgentEvent(MESSAGE_END, {
                            "content": text_content,
                            "turn": self._turn_count,
                        }))
                        self._events.emit(AgentEvent(TURN_END, {
                            "turn": self._turn_count,
                            "tool_calls": 0,
                        }))
                        break

                    # Emit text preamble if present
                    if text_content:
                        self._events.emit(AgentEvent(MESSAGE_UPDATE, {
                            "content": text_content,
                        }))

                    # --- Execute tool calls sequentially ---
                    tool_names_used: Set[str] = set()
                    calls_this_turn = 0
                    interrupted = False

                    for tool_call in message.tool_calls:
                        should_skip = False

                        if self._abort:
                            should_skip = True
                        elif self._steering_queue and calls_this_turn > 0:
                            should_skip = True
                            if not interrupted:
                                logger.info("Steering interrupt - skipping remaining tools")
                                interrupted = True
                        elif calls_this_turn >= self.config.max_tool_calls_per_turn:
                            should_skip = True
                            if not interrupted:
                                logger.warning(
                                    f"Hit max_tool_calls_per_turn ({self.config.max_tool_calls_per_turn})"
                                )
                                interrupted = True

                        tool_name = tool_call.function.name
                        try:
                            tool_args = json.loads(tool_call.function.arguments)
                        except json.JSONDecodeError:
                            tool_args = {}
                            logger.warning(f"Failed to parse tool args for {tool_name}")

                        if should_skip:
                            reason = "aborted" if self._abort else "skipped (steering interrupt)"
                            self.messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": json.dumps({
                                    "success": False,
                                    "skipped": True,
                                    "reason": reason,
                                }),
                            })
                            continue

                        tool_names_used.add(tool_name)
                        calls_this_turn += 1

                        self._events.emit(AgentEvent(TOOL_EXEC_START, {
                            "tool": tool_name,
                            "params": tool_args,
                            "call_id": tool_call.id,
                        }))

                        # --- SEAM 2+3: Execute with knowledge ---
                        result = await self._execute_tool(tool_name, tool_args)

                        substrate_observation = None
                        if isinstance(result, dict):
                            substrate_observation = extract_substrate_observation(
                                tool_name,
                                result,
                            )

                        # Extract created object GUIDs from Rhino write-path tools
                        _created_ids: List[str] = []
                        if tool_name in _RHINO_CREATION_TOOLS and isinstance(result, dict):
                            _data = result.get("data", {})
                            if isinstance(_data, dict):
                                _oid = _data.get("id")
                                if _oid and isinstance(_oid, str):
                                    _created_ids.append(_oid)

                        self._events.emit(AgentEvent(TOOL_EXEC_END, {
                            "tool": tool_name,
                            "success": result.get("success", False) if isinstance(result, dict) else True,
                            "call_id": tool_call.id,
                            "error": (
                                result.get("error", "")
                                if isinstance(result, dict) and not result.get("success", True)
                                else ""
                            ),
                            "route_taken": (
                                substrate_observation.route_taken
                                if substrate_observation is not None else ""
                            ),
                            "operation": (
                                substrate_observation.operation
                                if substrate_observation is not None else ""
                            ),
                            "verified": (
                                substrate_observation.verified
                                if substrate_observation is not None else None
                            ),
                            "created_ids": _created_ids,
                        }))

                        # Append tool result to messages (with size cap)
                        result_str = json.dumps(result) if isinstance(result, dict) else str(result)
                        max_result_chars = 30_000
                        if len(result_str) > max_result_chars:
                            logger.warning(
                                f"Tool {tool_name} result truncated: "
                                f"{len(result_str)} chars -> {max_result_chars}"
                            )
                            result_str = (
                                result_str[:max_result_chars]
                                + f"\n... [TRUNCATED: {len(result_str)} chars total. "
                                f"Use more specific parameters to narrow results.]"
                            )
                        self.messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": result_str,
                        })

                    # --- SEAM 4: Post-turn adaptation ---
                    self._post_turn_adapt(tool_names_used)

                    self._events.emit(AgentEvent(TURN_END, {
                        "turn": self._turn_count,
                        "tool_calls": calls_this_turn,
                        "tools_used": list(tool_names_used),
                    }))

                # --- Follow-up queue (re-enters outer loop without recursion) ---
                if self._followup_queue and not self._abort:
                    msg = self._followup_queue.pop(0)
                    self.messages.append({"role": "user", "content": msg})
                    logger.info(f"Follow-up starting: {msg[:80]}...")
                    self._turn_count = 0
                    _has_more_work = True

        except Exception as e:
            logger.error(f"Agent loop error: {e}", exc_info=True)
            self._events.emit(AgentEvent(ERROR, {"message": str(e)}))

        finally:
            self._state = "idle"
            self._idle_event.set()
            self._events.emit(AgentEvent(AGENT_END, {
                "turns": self._turn_count,
                "cost": self._total_cost,
                "tokens": self.token_usage,
            }))

    # =========================================================================
    # Model interaction
    # =========================================================================

    async def _call_model(self, messages: List[dict]) -> Optional[Any]:
        """Single LLM call via LiteLLM."""
        tools = self._get_tool_schemas()
        system_prompt = self.config.system_prompt or self._default_system_prompt()

        try:
            kwargs = dict(
                model=self.config.model,
                messages=[{"role": "system", "content": system_prompt}] + messages,
                tools=tools if tools else None,
                tool_choice="auto" if tools else None,
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature,
            )
            kwargs = sanitize_generation_params_for_model(self.config.model, kwargs)
            if self.config.api_base:
                kwargs["api_base"] = self.config.api_base
            response = await litellm.acompletion(**kwargs)
            return response

        except Exception as e:
            logger.error(f"LLM call failed: {e}", exc_info=True)
            self._events.emit(AgentEvent(ERROR, {
                "message": f"LLM call failed: {e}",
                "model": self.config.model,
            }))
            return None

    def _get_tool_schemas(self) -> List[dict]:
        """Get current tool schemas. Uses ToolRegistry when available."""
        if self._tool_registry:
            return filter_litellm_schemas(
                self._tool_registry.get_active_schemas()
            )
        return filter_litellm_schemas(self._tool_schemas)

    def _track_usage(self, response) -> None:
        """Track token usage and cost from a ModelResponse."""
        try:
            usage = getattr(response, "usage", None)
            if usage:
                self._total_input_tokens += getattr(usage, "prompt_tokens", 0)
                self._total_output_tokens += getattr(usage, "completion_tokens", 0)
            cost = litellm.completion_cost(completion_response=response)
            self._total_cost += cost
        except Exception as e:
            logger.debug(f"Cost tracking error: {e}")

    @staticmethod
    def _default_system_prompt() -> str:
        """Default system prompt for worker agents.

        Loads WORKER.md from the prompts directory if available,
        otherwise falls back to a minimal inline prompt.
        """
        from pathlib import Path
        prompt_path = Path(__file__).parent / "prompts" / "WORKER.md"
        if prompt_path.exists():
            try:
                return prompt_path.read_text(encoding="utf-8")
            except Exception:
                pass
        return (
            "You are a Rhino 3D and Grasshopper automation agent. "
            "You have access to tools that control Rhino viewport objects "
            "and Grasshopper canvas components. Execute the user's request "
            "using the available tools. Be precise with coordinates, IDs, "
            "and parameter values. If a tool fails, try a different approach "
            "rather than repeating the same call."
        )

    # =========================================================================
    # Seam 1: Pre-LLM knowledge injection
    # =========================================================================

    def _transform_context(self, messages: List[dict]) -> List[dict]:
        """SEAM 1: Inject knowledge before LLM call.

        Predicts likely next tools from conversation history, fetches
        relevant gotchas from Rook's knowledge stores, and
        appends a knowledge context message.

        NOTE: Knowledge injection is ephemeral. The injected message is NOT
        persisted in self.messages — each turn gets a fresh injection based
        on predicted tools. This saves tokens but means the LLM cannot
        reference previous injections by name. A shallow copy of messages
        is made; self.messages is never modified.
        """
        if not self.config.knowledge_injection:
            return list(messages)

        try:
            recent_tools = self._extract_recent_tools(messages)
            if not recent_tools:
                return list(messages)

            predicted = self._predict_next_tools(recent_tools)
            if not predicted:
                return list(messages)

            knowledge_text = self._build_knowledge_context(predicted)
            if not knowledge_text:
                return list(messages)

            messages = list(messages)
            messages.append({
                "role": "user",
                "content": f"[Knowledge for upcoming operations]\n{knowledge_text}",
            })

            self._events.emit(AgentEvent(KNOWLEDGE_INJECT, {
                "predicted_tools": predicted,
                "chars_injected": len(knowledge_text),
            }))

            return messages

        except Exception as e:
            logger.debug(f"Knowledge injection failed: {e}")
            return list(messages)

    def _extract_recent_tools(self, messages: List[dict], lookback_messages: int = 5) -> List[str]:
        """Extract tool names from recent assistant messages.

        Args:
            lookback_messages: Number of assistant messages to examine (not tool calls).
                A single message can contain up to max_tool_calls_per_turn tool calls.
        """
        tools = []
        count = 0
        for msg in reversed(messages):
            if count >= lookback_messages:
                break
            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                for tc in msg["tool_calls"]:
                    name = tc.get("function", {}).get("name", "")
                    if name:
                        tools.append(name)
                count += 1
        return tools

    def _predict_next_tools(self, recent_tools: List[str], limit: int = 5) -> List[str]:
        """Predict likely next tools using TOOL_TRANSITIONS Markov map."""
        predicted: List[str] = []
        seen: Set[str] = set()
        for tool in recent_tools:
            for candidate in TOOL_TRANSITIONS.get(tool, []):
                if candidate not in seen:
                    seen.add(candidate)
                    predicted.append(candidate)
        return predicted[:limit]

    def _build_knowledge_context(
        self, predicted_tools: List[str], max_chars: int = 1600, max_per_tool: int = 2,
    ) -> str:
        """Build knowledge text for predicted tools within char budget.

        Queries Rook's UnifiedStore for GH tools and
        CommandKnowledgeStore for Rhino command tools.
        """
        infra = _get_knowledge_infra()
        unified = infra.get("unified_store")
        command = infra.get("command_store")

        if not unified and not command:
            return ""

        lines: List[str] = []
        chars_used = 0

        for tool_name in predicted_tools:
            gotchas = self._get_gotchas_for_tool(tool_name, unified, command)
            if not gotchas:
                continue

            # Take top N gotchas
            top = gotchas[:max_per_tool]

            header = f"## {tool_name}"
            if chars_used + len(header) + 2 > max_chars:
                break
            lines.append(header)
            chars_used += len(header) + 1

            for g in top:
                desc = g.replace("\n", " ").strip()
                if len(desc) > 120:
                    desc = desc[:117] + "..."
                bullet = f"- {desc}"
                if chars_used + len(bullet) + 1 > max_chars:
                    break
                lines.append(bullet)
                chars_used += len(bullet) + 1

        return "\n".join(lines)

    @staticmethod
    def _get_gotchas_for_tool(
        tool_name: str,
        unified_store: Optional[Any],
        command_store: Optional[Any],
    ) -> List[str]:
        """Get gotcha descriptions for a tool from the appropriate store.

        Returns list of gotcha description strings (simple text).
        """
        gotchas: List[str] = []

        # GH tools -> UnifiedStore
        if tool_name.startswith("gh_") and unified_store:
            try:
                results = unified_store.search(intent=tool_name, limit=3, tier="context")
                for note_dict in results:
                    # context tier returns anti_patterns as the gotcha equivalent
                    anti_patterns = note_dict.get("anti_patterns", [])
                    for ap in anti_patterns[:2]:
                        desc = ap if isinstance(ap, str) else str(ap)
                        if desc:
                            gotchas.append(desc)
            except Exception:
                pass

        # Rhino command tools -> CommandKnowledgeStore
        _TOOL_TO_COMMAND = {
            "rhino_execute_intent": None,  # Not a direct command
            "rhino_execute": None,
            "rhino_objects": None,
            "rhino_geometry": None,
            "rhino_instances": None,
            "rhino_selection": None,
            "rhino_measure_distance": "Distance",
            "rhino_measure_length": "Length",
            "rhino_measure_area": "Area",
            "rhino_measure_volume": "Volume",
            "rhino_measure_bbox": "BoundingBox",
            "rhino_measure_centroid": "AreaCentroid",
            "rhino_closest_point": "ClosestPt",
            "rhino_is_closed": None,
            "rhino_is_valid": None,
            "rhino_apply_uv_box_mapping": None,
            "rhino_apply_uv_planar_mapping": None,
            "rhino_apply_uv_cylinder_mapping": None,
            "rhino_apply_uv_sphere_mapping": None,
        }
        if tool_name.startswith("rhino_") and command_store:
            try:
                if tool_name in _TOOL_TO_COMMAND:
                    cmd_name = _TOOL_TO_COMMAND[tool_name]
                else:
                    # Fallback: derive command name (e.g., rhino_transform -> Transform)
                    cmd_name = tool_name.replace("rhino_", "").replace("_", " ").title()
                if cmd_name:
                    cmd_gotchas = command_store.get_gotchas(cmd_name)
                    gotchas.extend(cmd_gotchas[:2])
            except Exception:
                pass

        return gotchas

    # =========================================================================
    # Seam 2+3: Tool execution with knowledge middleware
    # =========================================================================

    async def _execute_tool(self, name: str, params: dict) -> dict:
        """Execute tool with Seam 2 (pre-execution) and Seam 3 (post-execution).

        Meta-tools (request_tools, search_tools) are handled internally.
        """
        # --- Meta-tools: handled by ToolRegistry ---
        if self._tool_registry and hasattr(self._tool_registry, "is_meta_tool"):
            if self._tool_registry.is_meta_tool(name):
                return self._handle_meta_tool(name, params)

        # --- Local tools: execute in Python, bypass bridge ---
        if name in self._local_tools:
            return await self._execute_local_tool(name, params)

        # --- SEAM 2: Pre-execution interception ---
        if self.config.parameter_correction:
            blocking = self._check_blocking_gotchas(name, params)
            if blocking is not None:
                self._record_observation(name, params, blocking)
                return blocking

        # --- Execute via tool_executor ---
        t0 = _time.perf_counter()
        try:
            result = self._tool_executor(name, params)
            if inspect.isawaitable(result):
                result = await result
            if not isinstance(result, dict):
                result = {"success": True, "result": str(result)}
        except Exception as e:
            logger.error(f"Tool execution failed ({name}): {e}")
            result = {"success": False, "error": str(e)}
        duration_ms = (_time.perf_counter() - t0) * 1000

        # --- SEAM 3: Post-execution recording ---
        # Record BEFORE updating failure counts so attempt_number reflects
        # the state before this call (1st attempt = 1, not 2)
        self._record_observation(name, params, result, duration_ms=duration_ms)

        # Track failures for attempt_number counting
        success = result.get("success", False) if isinstance(result, dict) else True
        if success:
            self._failure_counts.pop(name, None)
        else:
            self._failure_counts[name] = self._failure_counts.get(name, 0) + 1

        return result

    # =========================================================================
    # Seam 2 helpers: Pre-execution interception
    # =========================================================================

    def _check_blocking_gotchas(self, name: str, params: dict) -> Optional[dict]:
        """Check for critical gotchas that should block execution.

        Returns a blocking result dict if execution should be prevented,
        or None to proceed normally.
        """
        infra = _get_knowledge_infra()
        ops = infra.get("operations_knowledge")
        if not ops:
            return None

        # Check operations knowledge for this tool
        tool_ops = ops.get(name, {})
        gotchas = tool_ops.get("gotchas", [])

        for gotcha in gotchas:
            severity = gotcha.get("severity", "low")
            if severity != "critical":
                continue
            pattern = gotcha.get("error_pattern", "")
            if not pattern or "=" not in pattern:
                continue

            param_name, _, match_val = pattern.partition("=")
            param_name = param_name.strip()
            match_val = match_val.strip()
            if not match_val:
                continue  # Skip patterns with empty match value
            current_val = str(params.get(param_name, ""))

            if current_val == match_val:
                logger.warning(
                    f"Blocking {name}: critical gotcha matched ({param_name}={match_val})"
                )
                return {
                    "success": False,
                    "error": f"Blocked by critical gotcha: {gotcha.get('description', '')}",
                    "_blocked_by_gotcha": gotcha.get("id", ""),
                    "_suggestion": gotcha.get("fix", "Review parameters and retry."),
                }

        return None

    # =========================================================================
    # Seam 3 helpers: Post-execution recording
    # =========================================================================

    def _record_observation(
        self, name: str, params: dict, result: dict, *, duration_ms: float = 0.0
    ) -> None:
        """Record a tool execution for the knowledge system."""
        # Substrate persistence is an additive, independent store: it must not
        # be gated on metrics-infra availability or on config.observation_recording
        # reaching the metrics path. Kept outside the metrics early-return guards
        # so direct-bridge executions still produce route_taken telemetry when
        # the metrics store is unavailable or deliberately disabled.
        if isinstance(result, dict):
            try:
                substrate_obs = extract_substrate_observation(name, result)
                if substrate_obs is not None:
                    persist_substrate_observation(
                        substrate_obs,
                        error=_substrate_compact_error(result),
                    )
            except Exception as exc:
                logger.debug(f"Substrate persistence skipped for {name}: {exc}")

        if not self.config.observation_recording:
            return

        infra = _get_knowledge_infra()
        metrics = infra.get("metrics")
        if not metrics:
            return

        success = result.get("success", False) if isinstance(result, dict) else True

        try:
            from ..learning.metrics_store import Observation
            from datetime import datetime, timezone
            obs = Observation(
                tool_name=name,
                success=success,
                duration_ms=round(duration_ms, 2),
                knowledge_injected=self.config.knowledge_injection,
                knowledge_hint="",
                gotchas_provided=[],
                correction_detected=result.get("correction_detected", False) if isinstance(result, dict) else False,
                attempt_number=self._failure_counts.get(name, 0) + 1,
                phase="agent",
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
            metrics.record(obs)
        except Exception as e:
            logger.debug(f"Metrics recording failed: {e}")

    # =========================================================================
    # Seam 4: Post-turn tool surface adaptation
    # =========================================================================

    def _post_turn_adapt(self, tool_names_used: Set[str]) -> None:
        """SEAM 4: Adapt tool surface after each turn.

        Marks tool usage, auto-loads related groups based on triggers,
        and deactivates stale tools.
        """
        if not self._tool_registry:
            return

        # Mark tools as used
        self._tool_registry.mark_used(tool_names_used, self._turn_count)

        if not self.config.tool_surface_adaptation:
            return

        # Auto-load related groups based on tool usage
        try:
            for tool_name in tool_names_used:
                group = TOOL_GROUP_TRIGGERS.get(tool_name)
                if group and group not in self._auto_loaded_groups:
                    result = self._tool_registry.request_group(
                        group, turn=self._turn_count,
                    )
                    if result.get("success") and result.get("loaded"):
                        self._auto_loaded_groups.add(group)
                        self._events.emit(AgentEvent(TOOL_GROUP_LOADED, {
                            "group": group,
                            "loaded": result["loaded"],
                            "active_count": result["active_count"],
                            "auto": True,
                            "triggered_by": tool_name,
                        }))
        except Exception as e:
            logger.debug(f"Seam 4 auto-load failed: {e}")

        # Deactivate stale tools
        try:
            removed = self._tool_registry.deactivate_stale(
                self.config.stale_tool_turns
            )
            if removed:
                self._events.emit(AgentEvent(TOOL_GROUP_UNLOADED, {
                    "tools": removed,
                    "active_count": self._tool_registry.get_active_count(),
                }))
        except Exception as e:
            logger.debug(f"Seam 4 stale cleanup failed: {e}")

    # =========================================================================
    # Meta-tool handling (ToolRegistry phase)
    # =========================================================================

    def _handle_meta_tool(self, name: str, params: dict) -> dict:
        """Handle request_tools and search_tools internally."""
        if name == "request_tools":
            result = self._tool_registry.request_group(
                params.get("group", ""),
                turn=self._turn_count,
            )
            if result.get("success") and result.get("loaded"):
                self._events.emit(AgentEvent(TOOL_GROUP_LOADED, {
                    "group": params.get("group"),
                    "loaded": result["loaded"],
                    "active_count": result["active_count"],
                }))
            return result

        if name == "search_tools":
            return self._tool_registry.search(
                params.get("query", ""),
                top_k=params.get("top_k", 5),
                turn=self._turn_count,
            )

        return {"success": False, "error": f"Unknown meta-tool: {name}"}

    async def _execute_local_tool(self, name: str, params: dict) -> dict:
        """Execute a locally registered tool (no bridge, pure Python)."""
        fn = self._local_tools[name]
        try:
            result = fn(**params)
            if inspect.isawaitable(result):
                result = await result
            if not isinstance(result, dict):
                result = {"success": True, "result": str(result)}
            return result
        except TypeError as e:
            logger.warning(f"Local tool {name} parameter error: {e}")
            return {"success": False, "error": f"Invalid parameters for {name}: {e}"}
        except Exception as e:
            logger.error(f"Local tool {name} failed: {e}")
            return {"success": False, "error": str(e)}

    # =========================================================================
    # Utilities
    # =========================================================================

    @staticmethod
    def _message_to_dict(message) -> dict:
        """Convert a LiteLLM Message object to a dict for message history."""
        d = {"role": message.role}

        # Always include content key — some LLM providers require it on
        # assistant messages with tool_calls, even if the value is null.
        d["content"] = message.content if message.content else None

        if message.tool_calls:
            d["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": tc.type,
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    }
                }
                for tc in message.tool_calls
            ]

        return d

    async def test_connection(self) -> dict:
        """Test if the Rhino bridge is reachable via the tool executor."""
        try:
            result = self._tool_executor("rhino_ping", {})
            if inspect.isawaitable(result):
                result = await result
            if isinstance(result, dict) and result.get("success"):
                return {"connected": True, "message": "Rhino bridge responding"}
            return {"connected": False, "message": f"Unexpected response: {result}"}
        except Exception as e:
            return {"connected": False, "message": str(e)}

    async def run_live_producer_node(
        self, graph: "PlanGraph", node_id: str
    ) -> "LiveProducerResult":
        """Drive one live producer node against this agent's tool executor.

        Opt-in, one-node, non-LLM: delegates to the LM4C contract bridge using the
        agent's own ``_tool_executor``. Does not touch the LLM run loop; no
        scheduler, no graph selection. A raising executor maps to LM4A
        ``dispatch_failed``; a malformed result flows into LM4A's raw-result
        handling -- this method owns neither result shape nor error taxonomy.
        """
        return await run_live_producer_node_with_executor(
            graph, node_id, self._tool_executor
        )

    def _load_env(self) -> None:
        """Load .env file for API keys."""
        try:
            env_path = load_runtime_dotenv()
            if env_path is not None:
                logger.debug(f"Loaded .env from {env_path}")
        except ImportError:
            pass
