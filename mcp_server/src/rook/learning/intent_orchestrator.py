"""Intent Runtime Orchestrator: the public API that replaces execute_intent.

Wires IntentPlanner -> SmartExecutor -> TypedReflection into a single
async call that returns the same shape as the old CommandExecutionResult,
preserving backward compatibility with the MCP tool handler.

Usage:
    from rook.bridge import call_rhino
    from rook.learning.intent_orchestrator import IntentOrchestrator

    orchestrator = IntentOrchestrator(http_caller=call_rhino)
    result = await orchestrator.run("create a sphere at 0,0,0 radius 5")
    # result == {"intent": ..., "command": ..., "success": ..., ...}
"""

from __future__ import annotations

import logging
import time
from typing import Any

from .intent_planner import IntentPlanner
from .intent_runtime import ExecutionResult
from .smart_executor import SmartExecutor, HttpCaller
from .typed_reflection import TypedReflection, KnowledgeRecorder

logger = logging.getLogger("rook.learning.intent_orchestrator")


class IntentOrchestrator:
    """Single entry point: natural language -> execution + reflection.

    Replaces HybridInvestigator.execute_intent() with the typed runtime.
    """

    def __init__(
        self,
        http_caller: HttpCaller,
        knowledge_store: Any | None = None,
        knowledge_graph: Any | None = None,
        recorder: KnowledgeRecorder | None = None,
    ) -> None:
        self._planner = IntentPlanner(
            knowledge_store=knowledge_store,
            knowledge_graph=knowledge_graph,
        )
        self._executor = SmartExecutor(http_caller=http_caller)
        self._reflector = TypedReflection(recorder=recorder)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(
        self, intent: str, context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute an intent end-to-end.

        Args:
            intent: Natural language description of desired operation.
            context: Optional geometry context (selected_ids, geometry_types).
                See ``IntentPlanner.plan()`` for details.

        Returns a dict matching the old CommandExecutionResult.to_dict()
        shape for backward compatibility:

            {
                "intent": str,
                "command": str,
                "mode": str,
                "success": bool,
                "objects_created": int,
                "error": str | None,
                "reasoning_trace": list[str],
                "time_ms": float,
            }

        On internal errors, returns the same shape with success=False
        rather than propagating the exception (I1).
        """
        start = time.time()

        try:
            # P1: Plan (M1: pass geometry context)
            plan = await self._planner.plan(intent, context=context)
            trace = list(plan.reasoning_trace)

            # P2: Execute
            result = await self._executor.execute(plan)
            trace.extend(result.reasoning_trace)

            # P3: Reflect — blocking but non-critical; recorder errors are
            # caught by TypedReflection internally (not fire-and-forget)
            correction = self._reflector.reflect(result)
            if correction and correction.get("recorded"):
                trace.append(f"Recorded correction: {correction['layer']}")

            total_ms = (time.time() - start) * 1000

            # Convert to backward-compatible shape
            return self._to_legacy_shape(plan, result, trace, total_ms)

        except Exception as e:
            # I1: Return legacy-shape dict on internal errors so downstream
            # consumers always get the expected dict structure.
            logger.error("Intent runtime internal error: %s", e, exc_info=True)
            total_ms = (time.time() - start) * 1000
            return {
                "intent": intent,
                "command": "",
                "mode": "default",
                "success": False,
                "objects_created": 0,
                "error": f"Internal error: {e}",
                "reasoning_trace": [f"Internal error: {e}"],
                "time_ms": total_ms,
                "execution_route": "error",
                "created_ids": [],
            }

    async def run_typed(
        self, intent: str, context: dict[str, Any] | None = None,
    ) -> ExecutionResult:
        """Execute and return the typed ExecutionResult (for new consumers).

        Unlike run(), this returns the rich typed result instead of
        the legacy dict shape.
        """
        plan = await self._planner.plan(intent, context=context)
        result = await self._executor.execute(plan)

        # I4: Merge planner trace into result so consumers get full telemetry
        result.reasoning_trace = list(plan.reasoning_trace) + list(result.reasoning_trace)

        self._reflector.reflect(result)
        return result

    # ------------------------------------------------------------------
    # Legacy shape conversion
    # ------------------------------------------------------------------

    @staticmethod
    def _to_legacy_shape(
        plan, result: ExecutionResult, trace: list[str], total_ms: float,
    ) -> dict[str, Any]:
        """Convert typed result to the old CommandExecutionResult.to_dict() shape."""
        summary = result.plan_summary or {}

        # Fallback chain: plan.command -> summary["command"] -> plan.operation
        # direct_api plans have no command name, so we use the operation name
        command = plan.command or summary.get("command", "")
        if not command and plan.operation:
            command = plan.operation

        return {
            "intent": result.intent,
            "command": command,
            "mode": plan.mode or summary.get("mode", "default"),
            "success": result.success,
            "objects_created": result.objects_created,
            "error": result.failure.error_detail if result.failure else None,
            "reasoning_trace": trace,
            "time_ms": total_ms,
            # New fields (backward-compatible additions)
            "execution_route": result.route_taken or plan.execution_route,
            "created_ids": result.created_ids,
        }
