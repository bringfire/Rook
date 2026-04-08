"""
Agent Events
=============

Event types and pub/sub dispatcher for the agent loop.
Events drive logging, MCP status reporting, and the dashboard.

Ported from Engram's event system (pi-agent-core pattern).
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Event type constants
# ---------------------------------------------------------------------------

# Lifecycle
AGENT_START = "agent_start"              # Agent begins processing a prompt
AGENT_END = "agent_end"                  # Agent completes (idle)
TURN_START = "turn_start"                # One LLM call begins
TURN_END = "turn_end"                    # One LLM call + tool execution complete

# Messages
MESSAGE_START = "message_start"          # Model response begins
MESSAGE_UPDATE = "message_update"        # Streaming text delta
MESSAGE_END = "message_end"              # Model response complete

# Tool execution
TOOL_EXEC_START = "tool_exec_start"      # Tool call begins
TOOL_EXEC_END = "tool_exec_end"          # Tool call complete

# Knowledge middleware
KNOWLEDGE_INJECT = "knowledge_inject"    # Seam 1: knowledge injected before LLM call
CORRECTION_APPLIED = "correction_applied"  # Seam 2: parameter correction hint applied
TOOL_GROUP_LOADED = "tool_group_loaded"  # Seam 4: tool group activated
TOOL_GROUP_UNLOADED = "tool_group_unloaded"  # Seam 4: stale tools removed

# Guardian
GUARDIAN_INTERVENTION = "guardian_intervention"  # Guardian detected an issue and steered

# Conductor
CONDUCTOR_SYSTEMIC_ISSUE = "conductor_systemic_issue"  # Cross-agent systemic issue

# Checkpoints (postcondition verification between execution groups)
CHECKPOINT_PASS = "checkpoint_pass"          # All postconditions verified
CHECKPOINT_FAIL = "checkpoint_fail"          # One or more postconditions failed

# Escalation (worker asks human for help)
AGENT_ASK = "agent_ask"                      # Worker is blocked, awaiting human answer

# Planner
PLAN_CREATED = "plan_created"            # Planner produced a validated plan
PLAN_EXECUTING = "plan_executing"        # Planner began dispatching workers
PLAN_COMPLETE = "plan_complete"          # All plan tasks finished

# Errors
ERROR = "error"                          # Non-fatal error during execution


# ---------------------------------------------------------------------------
# Event data
# ---------------------------------------------------------------------------

@dataclass
class AgentEvent:
    """A single event emitted by the agent loop.

    Carries a type string and arbitrary data dict. Subscribers filter by type.
    """
    type: str
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict for JSON transport."""
        return {
            "type": self.type,
            "data": self.data,
            "timestamp": self.timestamp,
        }


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

class EventDispatcher:
    """Simple pub/sub for agent events.

    Subscribers receive every event. They should filter by type if needed.
    Subscriber exceptions are caught and logged — they never break the loop.
    """

    def __init__(self):
        self._subscribers: List[Callable[[AgentEvent], None]] = []

    def subscribe(self, callback: Callable[[AgentEvent], None]) -> Callable[[], None]:
        """Subscribe to all events.

        Args:
            callback: Function called with each AgentEvent.

        Returns:
            Unsubscribe function — call it to stop receiving events.
        """
        self._subscribers.append(callback)

        def unsubscribe():
            try:
                self._subscribers.remove(callback)
            except ValueError:
                pass  # Already removed

        return unsubscribe

    def emit(self, event: AgentEvent) -> None:
        """Emit an event to all subscribers."""
        for cb in list(self._subscribers):
            try:
                cb(event)
            except Exception as e:
                logger.debug(f"Event subscriber error on {event.type}: {e}")

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)
