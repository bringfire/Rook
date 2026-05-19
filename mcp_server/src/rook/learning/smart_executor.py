"""Smart Executor: ExecutionPlan -> ExecutionResult via safe substrates.

The executor is the second stage of the intent runtime. It takes a typed
ExecutionPlan (produced by IntentPlanner) and executes it through safe
normal execution substrates:

  1. DIRECT API — typed HTTP call to C++ plugin
  2. KNOWN COMMAND — known-safe fully scripted command string via /command

Autonomous interactive prompt driving is deprecated. The executor does not
call /command/start or /command/send as fallback for normal execution.

The executor never plans. It only executes plans.

Recovery helpers (C++ CommandInteractiveHandler):
  GET  /command/prompt  -> {prompt, is_active, options, default_value}
  POST /command/cancel  -> cancels active command
"""

from __future__ import annotations

import asyncio
import json
import logging
import shlex
import time
from typing import Any, Callable, Awaitable

from .intent_runtime import (
    ExecutionPlan,
    ExecutionResult,
    ExecutionFailure,
    FailureLayer,
    CapabilityRouter,
)
from ..preflight import preflight_rhino_command

logger = logging.getLogger("rook.learning.smart_executor")

# Type for the HTTP caller: (endpoint, method, data) -> response_dict
HttpCaller = Callable[[str, str, dict[str, Any] | None], Awaitable[dict[str, Any]]]


def _tokenize_syntax(syntax: str) -> list[str]:
    """Tokenize command syntax preserving quoted multi-token arguments.

    Uses shlex to handle quotes, falling back to plain split if shlex
    fails (e.g., unbalanced quotes in Rhino underscore syntax).

    Examples:
        '_-Loft _SelID a _Enter'           -> ['_-Loft', '_SelID', 'a', '_Enter']
        '_-Import "C:/path with spaces/f"'  -> ['_-Import', 'C:/path with spaces/f']
        '_-SetUnits "Small Objects"'        -> ['_-SetUnits', 'Small Objects']
    """
    try:
        return shlex.split(syntax, posix=False)
    except ValueError:
        return syntax.split()


class SmartExecutor:
    """Executes an ExecutionPlan through the best available substrate.

    Usage:
        from rook.bridge import call_rhino

        executor = SmartExecutor(http_caller=call_rhino)
        result = await executor.execute(plan)

        if result.success:
            print(f"Created {result.objects_created} objects")
        else:
            print(f"Failed at {result.failure.layer}: {result.failure.error_detail}")
    """

    def __init__(
        self,
        http_caller: HttpCaller,
        router: CapabilityRouter | None = None,
        command_knowledge_store: Any | None = None,
    ) -> None:
        self._call = http_caller
        self._router = router or CapabilityRouter.get()
        self._command_knowledge_store = command_knowledge_store

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def execute(self, plan: ExecutionPlan) -> ExecutionResult:
        """Execute the plan through the appropriate substrate."""
        start = time.time()
        trace: list[str] = []

        if plan.execution_route == "direct_api":
            result = await self._execute_direct(plan, trace)
        elif plan.execution_route == "known_command":
            result = await self._execute_command(plan, trace)
        elif plan.execution_route == "interactive":
            trace.append("Interactive execution route is deprecated")
            result = self._interactive_disabled_result(plan)
        else:
            result = ExecutionResult(
                success=False,
                intent=plan.intent,
                failure=ExecutionFailure(
                    layer=FailureLayer.ROUTING,
                    operation=plan.operation,
                    attempted_route=plan.execution_route,
                    error_detail=f"Unknown execution route: {plan.execution_route}",
                    recovery_suggestion="Use IntentPlanner to produce a valid plan",
                ),
            )

        result.plan_summary = plan.to_dict()
        result.time_ms = (time.time() - start) * 1000
        result.reasoning_trace = trace
        return result

    # ------------------------------------------------------------------
    # Direct API execution
    # ------------------------------------------------------------------

    async def _execute_direct(
        self, plan: ExecutionPlan, trace: list[str],
    ) -> ExecutionResult:
        """Execute via typed HTTP endpoint (fastest, most reliable)."""
        spec = plan.route_spec
        if spec is None:
            spec = self._router.route(plan.operation)
        if spec is None:
            trace.append(f"No route spec for {plan.operation}")
            return self._routing_failure(plan, "No route spec for direct_api execution")

        # Validate params
        valid, missing = self._router.validate_params(plan.operation, plan.params)
        if not valid:
            trace.append(f"Missing required params: {missing}")
            return ExecutionResult(
                success=False,
                intent=plan.intent,
                failure=ExecutionFailure(
                    layer=FailureLayer.PARAMETER_SYNTHESIS,
                    operation=plan.operation,
                    attempted_route="direct_api",
                    error_detail=f"Missing required parameters: {missing}",
                    recovery_suggestion=f"Provide: {', '.join(missing)}",
                ),
            )

        # Build payload and call
        payload = self._router.build_payload(plan.operation, plan.params)
        trace.append(f"Direct API: {spec.method} {spec.endpoint}")

        try:
            response = await self._call(spec.endpoint, spec.method, payload)
        except Exception as e:
            trace.append(f"HTTP call failed: {e}")
            return self._execution_failure(
                plan, "direct_api", str(e), FailureLayer.COMMAND_EXECUTION,
            )

        return self._parse_response(plan, "direct_api", response, trace)

    # ------------------------------------------------------------------
    # Known command execution
    # ------------------------------------------------------------------

    async def _execute_command(
        self, plan: ExecutionPlan, trace: list[str],
    ) -> ExecutionResult:
        """Execute via known-safe fully scripted command string."""
        if not plan.syntax:
            trace.append("No syntax in plan")
            return self._execution_failure(
                plan, "known_command",
                "Plan has no command syntax",
                FailureLayer.PARAMETER_SYNTHESIS,
                "Re-plan with IntentPlanner to resolve syntax",
            )

        trace.append(f"Command: {plan.syntax}")

        preflight_error = preflight_rhino_command(
            plan.syntax,
            self._resolve_command_knowledge_store(),
        )
        if preflight_error is not None:
            detail = json.dumps(preflight_error.get("data", preflight_error), sort_keys=True)
            trace.append(f"Command safety preflight rejected command: {detail}")
            return self._execution_failure(
                plan,
                "known_command",
                detail,
                FailureLayer.ROUTING,
                "Use typed Rook tools or a known-safe fully scripted command.",
            )

        try:
            response = await self._call("/command", "POST", {"command": plan.syntax})
        except Exception as e:
            trace.append(f"Command call failed: {e}")
            return self._execution_failure(
                plan, "known_command", str(e), FailureLayer.COMMAND_EXECUTION,
            )

        # Check for stalled command (interactive prompt waiting)
        # C++ CommandHandler returns success:false + waitingFor when command goes interactive
        data = response.get("data", {})
        if not response.get("success", False) and isinstance(data, dict) and data.get("waitingFor"):
            stalled_prompt = data["waitingFor"]
            trace.append(f"Command stalled at prompt: {stalled_prompt}")

            return ExecutionResult(
                success=False,
                intent=plan.intent,
                route_taken="known_command",
                failure=ExecutionFailure(
                    layer=FailureLayer.INTERACTIVE_PROMPT,
                    operation=plan.operation,
                    attempted_route="known_command",
                    error_detail=f"Command stalled at prompt: {stalled_prompt}",
                    recovery_suggestion=(
                        "The command requires interactive input, but interactive prompt "
                        "driving is disabled for normal execution. Provide complete "
                        "parameters, use typed Rook tools, or use a known-safe fully "
                        "scripted command."
                    ),
                ),
            )

        return self._parse_response(plan, "known_command", response, trace)

    def _resolve_command_knowledge_store(self) -> Any | None:
        if self._command_knowledge_store is not None:
            return self._command_knowledge_store
        try:
            from ..server import command_learner
            return command_learner.knowledge_store
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Interactive execution
    # ------------------------------------------------------------------

    async def _execute_interactive(
        self, plan: ExecutionPlan, trace: list[str],
    ) -> ExecutionResult:
        """Refuse legacy interactive execution without driving prompts."""
        trace.append("Interactive execution route is deprecated")
        return self._interactive_disabled_result(plan)

    # ------------------------------------------------------------------
    # Interactive fallback (from stalled known_command)
    # ------------------------------------------------------------------

    async def _interactive_fallback(
        self,
        plan: ExecutionPlan,
        stalled_prompt: str,
        trace: list[str],
    ) -> ExecutionResult:
        """Refuse legacy fallback without driving prompts."""
        trace.append(f"Interactive fallback is deprecated; stalled prompt was: {stalled_prompt}")
        return self._interactive_disabled_result(plan)

    def _interactive_disabled_result(self, plan: ExecutionPlan) -> ExecutionResult:
        return ExecutionResult(
            success=False,
            intent=plan.intent,
            route_taken="interactive",
            failure=ExecutionFailure(
                layer=FailureLayer.ROUTING,
                operation=plan.operation,
                attempted_route="interactive",
                error_detail=(
                    "Interactive Rhino command execution is disabled for normal execution."
                ),
                recovery_suggestion=(
                    "Use typed Rook tools or a known-safe fully scripted command. "
                    "Use rhino_command_interactive_prompt and rhino_command_interactive_cancel "
                    "only for recovery."
                ),
            ),
        )

    # ------------------------------------------------------------------
    # Response parsing
    # ------------------------------------------------------------------

    def _parse_response(
        self,
        plan: ExecutionPlan,
        route: str,
        response: dict[str, Any],
        trace: list[str],
    ) -> ExecutionResult:
        """Parse a response from call_rhino into an ExecutionResult."""
        success = response.get("success", False)
        data = response.get("data", {})

        if isinstance(data, str):
            # Error string response
            if success:
                trace.append(f"Success: {data}")
                return ExecutionResult(
                    success=True, intent=plan.intent, route_taken=route,
                    data={"message": data},
                )
            else:
                trace.append(f"Failed: {data}")

                # Check for timeout
                if "timed out" in data.lower():
                    return ExecutionResult(
                        success=False, intent=plan.intent, route_taken=route,
                        failure=ExecutionFailure(
                            layer=FailureLayer.TIMEOUT,
                            operation=plan.operation,
                            attempted_route=route,
                            error_detail=data,
                            recovery_suggestion="Rhino UI thread may be blocked. Check for modal dialogs.",
                        ),
                    )

                return ExecutionResult(
                    success=False, intent=plan.intent, route_taken=route,
                    failure=ExecutionFailure(
                        layer=FailureLayer.COMMAND_EXECUTION,
                        operation=plan.operation,
                        attempted_route=route,
                        error_detail=data,
                    ),
                )

        if not isinstance(data, dict):
            data = {}

        if success:
            # Extract created object IDs
            created_ids = data.get("objectIds", data.get("ids", []))
            if isinstance(created_ids, str):
                created_ids = [created_ids]
            objects_created = data.get("objectsCreated", data.get("count", len(created_ids)))

            trace.append(f"Success: {objects_created} objects created")
            return ExecutionResult(
                success=True,
                intent=plan.intent,
                route_taken=route,
                created_ids=created_ids,
                objects_created=objects_created,
                data=data,
            )
        else:
            error = data.get("error", data.get("message", str(data)))
            trace.append(f"Failed: {error}")
            return ExecutionResult(
                success=False,
                intent=plan.intent,
                route_taken=route,
                failure=ExecutionFailure(
                    layer=FailureLayer.COMMAND_EXECUTION,
                    operation=plan.operation,
                    attempted_route=route,
                    error_detail=str(error),
                ),
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _poll_prompt(self, trace: list[str]) -> dict[str, Any]:
        """Poll GET /command/prompt for the current interactive state.

        C++ returns: {prompt, is_active, options, default_value}.
        When is_active is false, the command has finished.

        On poll failure, returns ``_poll_error`` so the caller can
        distinguish "command completed" from "network error".
        """
        await asyncio.sleep(0.15)  # Allow Rhino message loop to process
        try:
            resp = await self._call("/command/prompt", "GET", None)
            data = resp.get("data", {})
            if isinstance(data, str):
                return {"prompt": data, "is_active": False}
            if isinstance(data, dict):
                return data
            return {"is_active": False}
        except Exception as e:
            trace.append(f"Prompt poll failed: {e}")
            return {"is_active": False, "_poll_error": str(e)}

    async def _safe_cancel(self, trace: list[str]) -> None:
        """Cancel any active interactive command, swallowing errors."""
        try:
            await self._call("/command/cancel", "POST", None)
            trace.append("Cancelled interactive command")
        except Exception as e:
            trace.append(f"Cancel failed (non-critical): {e}")

    def _routing_failure(
        self, plan: ExecutionPlan, detail: str,
    ) -> ExecutionResult:
        return ExecutionResult(
            success=False,
            intent=plan.intent,
            failure=ExecutionFailure(
                layer=FailureLayer.ROUTING,
                operation=plan.operation,
                attempted_route=plan.execution_route,
                error_detail=detail,
            ),
        )

    def _execution_failure(
        self,
        plan: ExecutionPlan,
        route: str,
        detail: str,
        layer: FailureLayer = FailureLayer.COMMAND_EXECUTION,
        suggestion: str | None = None,
    ) -> ExecutionResult:
        return ExecutionResult(
            success=False,
            intent=plan.intent,
            route_taken=route,
            failure=ExecutionFailure(
                layer=layer,
                operation=plan.operation,
                attempted_route=route,
                error_detail=detail,
                recovery_suggestion=suggestion,
            ),
        )
