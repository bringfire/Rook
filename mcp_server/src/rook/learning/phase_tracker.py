"""Lightweight workflow phase tracker for Rook.

Tracks recent tool calls and infers the current workflow phase.
Used by the knowledge injector to boost phase-relevant gotchas.

Phases:
    - gh_build: Creating/wiring Grasshopper definitions
    - rhino_model: Rhino geometry creation/manipulation
    - debugging: Querying errors, inspecting state
    - exploration: Knowledge queries, learning, mixed tools
"""

import logging
from collections import deque
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class WorkflowPhase(Enum):
    GH_BUILD = "gh_build"
    RHINO_MODEL = "rhino_model"
    DEBUGGING = "debugging"
    EXPLORATION = "exploration"


# Tool name substrings that indicate each phase.
_PHASE_PATTERNS: dict[WorkflowPhase, list[str]] = {
    WorkflowPhase.DEBUGGING: [
        "gh_errors", "gh_investigate", "rhino_objects", "rhino_selection",
    ],
    WorkflowPhase.GH_BUILD: [
        "gh_execute_intent", "gh_edit", "gh_cluster",
    ],
    WorkflowPhase.RHINO_MODEL: [
        "rhino_execute_intent", "rhino_command", "rhino_create",
        "rhino_boolean", "rhino_transform", "rhino_extrude",
        "rhino_loft", "rhino_sweep",
    ],
    WorkflowPhase.EXPLORATION: [
        "knowledge_query", "gh_knowledge_query", "gh_explore",
        "gh_library", "gh_snapshot",
    ],
}

# Minimum matches in the recent window to declare a phase (prevents flickering)
_PHASE_THRESHOLD = 3


class PhaseTracker:
    """Tracks recent tool calls and infers current workflow phase."""

    def __init__(self, window_size: int = 15):
        self._calls: deque[str] = deque(maxlen=window_size)
        self._last_workflow_phase: Optional[WorkflowPhase] = None

    def record_call(self, tool_name: str) -> None:
        """Record a tool call."""
        self._calls.append(tool_name)

    def current_phase(self) -> WorkflowPhase:
        """Detect current workflow phase from recent calls."""
        if len(self._calls) < _PHASE_THRESHOLD:
            return WorkflowPhase.EXPLORATION

        recent = list(self._calls)[-10:]  # Score last 10

        best_phase = WorkflowPhase.EXPLORATION
        best_count = 0

        for phase, patterns in _PHASE_PATTERNS.items():
            count = sum(
                1 for tool in recent
                if any(p in tool for p in patterns)
            )
            if count >= _PHASE_THRESHOLD and count > best_count:
                best_count = count
                best_phase = phase

        return best_phase

    def should_inject_workflow_hint(self) -> bool:
        """Check if a workflow-level hint should be injected.

        Returns True when the user is in a sustained non-exploration phase
        (4/5 recent calls match) AND we haven't already injected for this
        phase entry. Resets when the phase changes.
        """
        phase = self.current_phase()
        if phase == WorkflowPhase.EXPLORATION:
            self._last_workflow_phase = None
            return False

        # Need at least 5 calls for sustained detection
        recent = list(self._calls)[-5:]
        if len(recent) < 5:
            return False

        patterns = _PHASE_PATTERNS.get(phase, [])
        matches = sum(1 for tool in recent if any(p in tool for p in patterns))
        if matches < 4:
            return False

        # Already injected for this phase entry?
        if phase == self._last_workflow_phase:
            return False

        self._last_workflow_phase = phase
        return True

    def recent_tools(self, n: int = 5) -> list[str]:
        """Get last N tool names (for debugging)."""
        return list(self._calls)[-n:]


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_phase_tracker: PhaseTracker | None = None


def get_phase_tracker() -> PhaseTracker:
    """Get the global PhaseTracker singleton."""
    global _phase_tracker
    if _phase_tracker is None:
        _phase_tracker = PhaseTracker()
    return _phase_tracker
