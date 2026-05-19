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
    ) -> None:
        self._call = http_caller
        self._router = router or CapabilityRouter.get()

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
            result = ExecutionResult(
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
                        "Use rhino_command_prompt and rhino_command_interactive_cancel "
                        "only for recovery."
                    ),
                ),
            )
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

    # ------------------------------------------------------------------
    # Interactive execution
    # ------------------------------------------------------------------

    async def _execute_interactive(
        self, plan: ExecutionPlan, trace: list[str],
    ) -> ExecutionResult:
        """Execute via interactive command session (multi-step prompts).

        Protocol (matches C++ CommandInteractiveHandler):
          1. POST /command/start  -> starts command
          2. GET  /command/prompt  -> poll for current prompt + is_active
          3. POST /command/send    -> send input token
          4. Repeat 2-3 until is_active == false
        """
        command = plan.command or plan.syntax
        if not command:
            return self._execution_failure(
                plan, "interactive",
                "No command name for interactive execution",
                FailureLayer.PARAMETER_SYNTHESIS,
            )

        # Strip syntax to just the command name for /command/start
        tokens = _tokenize_syntax(command)
        cmd_name = tokens[0] if tokens else command

        trace.append(f"Interactive: starting {cmd_name}")

        try:
            # Start the interactive session
            start_resp = await self._call(
                "/command/start", "POST", {"command": cmd_name},
            )

            if not start_resp.get("success", False):
                error = start_resp.get("data", "Failed to start command")
                trace.append(f"Interactive start failed: {error}")
                return self._execution_failure(
                    plan, "interactive", str(error), FailureLayer.COMMAND_EXECUTION,
                )

            # Poll prompt state after start
            prompt_state = await self._poll_prompt(trace)

            # Feed inputs from the plan's syntax (skip the command name)
            if not plan.syntax:
                trace.append("No syntax for interactive inputs; will only send _Enter")
            inputs = _tokenize_syntax(plan.syntax)[1:] if plan.syntax else []
            max_rounds = len(inputs) + 5  # safety limit

            for i in range(max_rounds):
                # Check for poll error — don't treat network failure as success
                if prompt_state.get("_poll_error"):
                    trace.append(f"Poll error, aborting: {prompt_state['_poll_error']}")
                    await self._safe_cancel(trace)
                    return self._execution_failure(
                        plan, "interactive",
                        f"Prompt poll failed: {prompt_state['_poll_error']}",
                        FailureLayer.COMMAND_EXECUTION,
                    )

                # Check if command has finished
                if not prompt_state.get("is_active", True):
                    trace.append("Interactive: command completed")
                    break

                prompt_text = prompt_state.get("prompt", "")

                # Determine next input
                if i < len(inputs):
                    next_input = inputs[i]
                else:
                    next_input = "_Enter"

                trace.append(f"Interactive [{i}]: sending '{next_input}' (prompt: {prompt_text})")

                send_resp = await self._call(
                    "/command/send", "POST", {"input": next_input},
                )

                if not send_resp.get("success", False):
                    error = send_resp.get("data", "Send failed")
                    trace.append(f"Interactive send failed: {error}")
                    await self._safe_cancel(trace)
                    return self._execution_failure(
                        plan, "interactive",
                        f"Interactive prompt failed: {error}",
                        FailureLayer.INTERACTIVE_PROMPT,
                        f"Stalled at prompt: {prompt_text}",
                    )

                # Poll prompt after each send
                prompt_state = await self._poll_prompt(trace)
            else:
                trace.append(f"Interactive: exceeded {max_rounds} rounds, cancelling")
                await self._safe_cancel(trace)
                return self._execution_failure(
                    plan, "interactive",
                    f"Interactive session exceeded {max_rounds} rounds",
                    FailureLayer.INTERACTIVE_PROMPT,
                    "Command requires more inputs than planned",
                )

            # Success — note: interactive sessions do not populate created_ids
            # or objects_created because the C++ prompt protocol does not
            # return object metadata.  P3 TypedReflection can issue a
            # follow-up query if object counts are needed.
            return ExecutionResult(
                success=True,
                intent=plan.intent,
                route_taken="interactive",
                data=prompt_state if isinstance(prompt_state, dict) else {},
            )

        except Exception as e:
            trace.append(f"Interactive execution error: {e}")
            await self._safe_cancel(trace)
            return self._execution_failure(
                plan, "interactive", str(e), FailureLayer.COMMAND_EXECUTION,
            )

    # ------------------------------------------------------------------
    # Interactive fallback (from stalled known_command)
    # ------------------------------------------------------------------

    async def _interactive_fallback(
        self,
        plan: ExecutionPlan,
        stalled_prompt: str,
        trace: list[str],
    ) -> ExecutionResult:
        """Restart a stalled command via interactive mode.

        Note: The stalled command was already cancelled by the C++ /command
        handler.  /command/start will issue an additional _Cancel as a safety
        measure (no-op when nothing is running).
        """
        # Create a modified plan for interactive execution
        interactive_plan = ExecutionPlan(
            intent=plan.intent,
            operation=plan.operation,
            params=plan.params,
            execution_route="interactive",
            command=plan.command,
            mode=plan.mode,
            syntax=plan.syntax,
            confidence=plan.confidence * 0.7,  # Reduced: fallback is less certain
            knowledge_context=plan.knowledge_context,
        )
        return await self._execute_interactive(interactive_plan, trace)

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
