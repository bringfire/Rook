"""Typed Reflection: ExecutionResult -> structured learning.

The reflector is the third stage of the intent runtime. It examines typed
execution results and converts failures into structured corrections for the
knowledge stores. Successes are optionally recorded as pattern reinforcements.

Each FailureLayer maps to a specific correction strategy:

  PLANNING           -> Gap: intent couldn't map to any operation
  ROUTING            -> Gap: operation known but no HTTP endpoint
  PARAMETER_SYNTHESIS -> Antipattern: right route, wrong/missing params
  COMMAND_EXECUTION   -> Antipattern: C++ plugin rejected the call
  INTERACTIVE_PROMPT  -> Antipattern: command stalled at interactive prompt
  WRONG_RESULT        -> Antipattern: succeeded but wrong output
  TIMEOUT             -> Antipattern: UI thread blocked

The reflector emits dicts compatible with the knowledge_record() API
(intent, action, outcome, correction_of).
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from .intent_runtime import ExecutionResult, ExecutionFailure, FailureLayer

logger = logging.getLogger("rook.learning.typed_reflection")

# Type for the knowledge recorder: (intent, action, outcome, correction_of) -> result
KnowledgeRecorder = Callable[
    [str, dict[str, Any], str, dict[str, Any] | None], dict[str, Any]
]


class TypedReflection:
    """Converts ExecutionResults into structured knowledge updates.

    Usage:
        from rook.knowledge import record_knowledge

        reflector = TypedReflection(recorder=record_knowledge)
        correction = reflector.reflect(result)

        if correction:
            print(f"Recorded: {correction['type']}")
    """

    def __init__(
        self,
        recorder: KnowledgeRecorder | None = None,
    ) -> None:
        self._recorder = recorder

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def reflect(self, result: ExecutionResult) -> dict[str, Any] | None:
        """Analyze an execution result and emit a correction if needed.

        Returns a correction dict on failure, None on uninteresting success.
        If a recorder is configured, the correction is also persisted.
        """
        if result.success:
            return self._reflect_success(result)
        return self._reflect_failure(result)

    def build_correction(self, result: ExecutionResult) -> dict[str, Any] | None:
        """Build a correction dict without recording it.

        Useful for inspection or when the caller wants to batch-record.
        """
        if result.success:
            return None
        if result.failure is None:
            return None
        return self._build_failure_correction(result)

    # ------------------------------------------------------------------
    # Success reflection
    # ------------------------------------------------------------------

    def _reflect_success(self, result: ExecutionResult) -> dict[str, Any] | None:
        """Optionally record a successful execution as a pattern reinforcement.

        Per CLAUDE.md: "Record corrections, not successes." We only record
        success when it corrects a prior failure (future: correction chain).
        For now, return None for plain successes.
        """
        return None

    # ------------------------------------------------------------------
    # Failure reflection
    # ------------------------------------------------------------------

    def _reflect_failure(self, result: ExecutionResult) -> dict[str, Any] | None:
        """Build and optionally record a failure correction."""
        if result.failure is None:
            return None

        correction = self._build_failure_correction(result)
        if correction is None:
            return None

        # Record to knowledge store if recorder is configured
        if self._recorder is not None:
            try:
                self._recorder(
                    correction["intent"],
                    correction["action"],
                    "failure",
                    correction["correction_of"],
                )
                correction["recorded"] = True
                logger.debug("Recorded correction for %s", result.failure.layer.value)
            except Exception as e:
                logger.warning("Failed to record correction: %s", e)
                correction["recorded"] = False
                correction["record_error"] = str(e)

        return correction

    # ------------------------------------------------------------------
    # Correction builders by failure layer
    # ------------------------------------------------------------------

    @staticmethod
    def _action_params(
        failure: ExecutionFailure, summary: dict, extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build action params, always including the operation to avoid hash collisions (I1)."""
        params = dict(summary.get("params", {}))
        params["_operation"] = failure.operation
        if extra:
            params.update(extra)
        return params

    def _build_failure_correction(self, result: ExecutionResult) -> dict[str, Any] | None:
        """Dispatch to the appropriate correction builder."""
        assert result.failure is not None  # S1: callers guarantee this
        failure: ExecutionFailure = result.failure
        layer = failure.layer
        summary = result.plan_summary or {}

        # Common fields
        # I2: empty-string route_taken (dataclass default) treated as unset
        base = {
            "type": "execution_failure",
            "layer": layer.value,
            "intent": result.intent,
            "route_taken": result.route_taken or failure.attempted_route,
            "time_ms": result.time_ms,
        }

        if layer == FailureLayer.PLANNING:
            return {**base, **self._correction_planning(failure, result.intent, summary)}
        elif layer == FailureLayer.ROUTING:
            return {**base, **self._correction_routing(failure, summary)}
        elif layer == FailureLayer.PARAMETER_SYNTHESIS:
            return {**base, **self._correction_params(failure, summary)}
        elif layer == FailureLayer.COMMAND_EXECUTION:
            return {**base, **self._correction_execution(failure, summary)}
        elif layer == FailureLayer.INTERACTIVE_PROMPT:
            return {**base, **self._correction_interactive(failure, summary)}
        elif layer == FailureLayer.WRONG_RESULT:
            return {**base, **self._correction_wrong_result(failure, summary)}
        elif layer == FailureLayer.TIMEOUT:
            return {**base, **self._correction_timeout(failure, summary)}
        else:
            logger.warning("Unknown failure layer: %s", layer)
            return {**base, **self._correction_generic(failure, summary)}

    def _correction_planning(
        self, failure: ExecutionFailure, intent: str, summary: dict,
    ) -> dict[str, Any]:
        """Intent couldn't map to any operation — knowledge gap."""
        return {
            "gap_type": "unmapped_intent",
            "action": {
                "tool": "rhino_execute_intent",
                "params": {"intent": intent},  # I3: use canonical result.intent
            },
            "correction_of": {
                "error": failure.error_detail,
                "category": "planning_gap",
                "diagnosis": (
                    "No operation in CapabilityRouter matched this intent. "
                    "May need a new route or a command-knowledge entry."
                ),
            },
            "recovery": failure.recovery_suggestion,
        }

    def _correction_routing(
        self, failure: ExecutionFailure, summary: dict,
    ) -> dict[str, Any]:
        """Operation recognized but no HTTP endpoint — route gap."""
        return {
            "gap_type": "missing_route",
            "action": {
                "tool": "rhino_execute_intent",
                "params": {
                    "operation": failure.operation,
                    "route": failure.attempted_route,
                },
            },
            "correction_of": {
                "error": failure.error_detail,
                "category": "routing_gap",
                "diagnosis": (
                    f"Operation '{failure.operation}' has no direct API route. "
                    "Consider adding a command-knowledge entry or C++ endpoint."
                ),
            },
            "recovery": failure.recovery_suggestion,
        }

    def _correction_params(
        self, failure: ExecutionFailure, summary: dict,
    ) -> dict[str, Any]:
        """Right route, wrong or missing parameters."""
        return {
            "gap_type": "parameter_error",
            "action": {
                "tool": "rhino_execute_intent",
                "params": self._action_params(failure, summary),
            },
            "correction_of": {
                "params": summary.get("params", {}),
                "error": failure.error_detail,
                "category": "parameter_synthesis",
                "diagnosis": (
                    f"Operation '{failure.operation}' via {failure.attempted_route}: "
                    f"{failure.error_detail}"
                ),
            },
            "recovery": failure.recovery_suggestion,
        }

    def _correction_execution(
        self, failure: ExecutionFailure, summary: dict,
    ) -> dict[str, Any]:
        """C++ plugin rejected the call."""
        return {
            "gap_type": "execution_error",
            "action": {
                "tool": "rhino_execute_intent",
                "params": self._action_params(failure, summary),
            },
            "correction_of": {
                "params": summary.get("params", {}),
                "error": failure.error_detail,
                "category": "command_execution",
                "diagnosis": (
                    f"C++ plugin returned error for '{failure.operation}' "
                    f"via {failure.attempted_route}: {failure.error_detail}"
                ),
            },
            "recovery": failure.recovery_suggestion,
        }

    def _correction_interactive(
        self, failure: ExecutionFailure, summary: dict,
    ) -> dict[str, Any]:
        """Command stalled at an interactive prompt."""
        return {
            "gap_type": "interactive_stall",
            "action": {
                "tool": "rhino_execute_intent",
                "params": {
                    "command": summary.get("command", ""),
                    "syntax": summary.get("syntax", ""),
                },
            },
            "correction_of": {
                "params": summary.get("params", {}),
                "error": failure.error_detail,
                "category": "interactive_prompt",
                "diagnosis": (
                    f"Command '{failure.operation}' stalled at an interactive prompt. "
                    "The syntax may be incomplete or the command requires "
                    "pre-selected objects."
                ),
            },
            "recovery": failure.recovery_suggestion,
        }

    def _correction_wrong_result(
        self, failure: ExecutionFailure, summary: dict,
    ) -> dict[str, Any]:
        """Command succeeded but produced unexpected output."""
        return {
            "gap_type": "wrong_result",
            "action": {
                "tool": "rhino_execute_intent",
                "params": self._action_params(failure, summary),
            },
            "correction_of": {
                "params": summary.get("params", {}),
                "error": failure.error_detail,
                "category": "wrong_result",
                "diagnosis": (
                    f"Operation '{failure.operation}' completed but produced "
                    f"unexpected results: {failure.error_detail}"
                ),
            },
            "recovery": failure.recovery_suggestion,
        }

    def _correction_timeout(
        self, failure: ExecutionFailure, summary: dict,
    ) -> dict[str, Any]:
        """Rhino UI thread was blocked."""
        return {
            "gap_type": "timeout",
            "action": {
                "tool": "rhino_execute_intent",
                "params": self._action_params(failure, summary),
            },
            "correction_of": {
                "params": summary.get("params", {}),
                "error": failure.error_detail,
                "category": "timeout",
                "diagnosis": (
                    "Rhino UI thread timed out. This usually means a modal "
                    "dialog is blocking or the operation is very expensive."
                ),
            },
            "recovery": failure.recovery_suggestion or (
                "Check for modal dialogs in Rhino. "
                "Consider breaking the operation into smaller steps."
            ),
        }

    def _correction_generic(
        self, failure: ExecutionFailure, summary: dict,
    ) -> dict[str, Any]:
        """Fallback for unknown failure layers."""
        return {
            "gap_type": "unknown",
            "action": {
                "tool": "rhino_execute_intent",
                "params": self._action_params(failure, summary),
            },
            "correction_of": {
                "error": failure.error_detail,
                "category": failure.layer.value,
                "diagnosis": failure.error_detail,
            },
            "recovery": failure.recovery_suggestion,
        }
