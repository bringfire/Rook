"""
Conductor — Fleet Coordinator
==============================

Sits above per-agent Guardians during parallel (swarm) execution.
Monitors 2+ agents for systemic issues in real-time and produces
aggregate reports after all agents complete.

Detection:
  - Systemic bridge failure: 2+ agents stuck on HTTP bridge simultaneously
  - Common tool failure: 2+ agents failing the same tool
  - Deduplication window: 60s suppression of repeated issues

Ported from Engram's Conductor, adapted for Rook's HTTP bridge.

Usage:
    conductor = Conductor()
    conductor.register_agent("t1", agent1)
    conductor.register_agent("t2", agent2)
    await conductor.start()
    # ... agents run ...
    report = conductor.report()
    await conductor.stop()
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Callable, Dict, List, Optional, Set

from .config import ConductorConfig
from .events import AgentEvent, GUARDIAN_INTERVENTION, TOOL_EXEC_END
from .substrate_analytics import summarize_substrate_observations

logger = logging.getLogger(__name__)


# =============================================================================
# Report
# =============================================================================

@dataclass
class ConductorReport:
    """Fleet-level aggregate report."""
    total_agents: int = 0
    completed: int = 0
    errored: int = 0
    total_cost_usd: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_wall_time_s: float = 0.0
    systemic_issues: List[dict] = field(default_factory=list)
    per_agent_summaries: List[dict] = field(default_factory=list)
    common_failure_tools: List[str] = field(default_factory=list)
    avg_alignment_score: float = 1.0
    substrate_summary: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


# =============================================================================
# Conductor
# =============================================================================

class Conductor:
    """Fleet coordinator for parallel agent execution.

    Subscribes to each registered agent's event stream and looks for
    cross-agent patterns that indicate systemic infrastructure issues
    (e.g., Rhino HTTP bridge down, common tool broken).
    """

    def __init__(self, config: Optional[ConductorConfig] = None):
        self._config = config or ConductorConfig()
        self._agents: Dict[str, Any] = {}           # task_id -> agent
        self._unsubscribes: Dict[str, Callable] = {} # task_id -> unsub fn
        self._results: Dict[str, Any] = {}           # task_id -> SpawnResult

        # Real-time monitoring state
        self._interventions: List[dict] = []         # all guardian interventions
        self._tool_failures: List[dict] = []         # all tool failures
        self._systemic_issues: List[dict] = []
        self._dedup_keys: Dict[str, float] = {}      # key -> last_reported_time

        self._monitor_task: Optional[asyncio.Task] = None
        self._running = False
        self._start_time: float = 0.0

    # =========================================================================
    # Registration
    # =========================================================================

    def register_agent(self, task_id: str, agent: Any) -> None:
        """Register an agent for fleet monitoring.

        Args:
            task_id: Unique identifier for this agent's task.
            agent: RookAgent instance.
        """
        self._agents[task_id] = agent

        def on_event(event: AgentEvent) -> None:
            self._on_agent_event(task_id, event)

        unsub = agent.subscribe(on_event)
        self._unsubscribes[task_id] = unsub

        logger.debug(f"Conductor: registered agent '{task_id}'")

    def add_result(self, task_id: str, result: Any) -> None:
        """Record a completed SpawnResult for post-hoc reporting."""
        self._results[task_id] = result

    # =========================================================================
    # Lifecycle
    # =========================================================================

    async def start(self) -> None:
        """Start the background monitor loop."""
        self._running = True
        self._start_time = time.time()
        try:
            loop = asyncio.get_running_loop()
            self._monitor_task = loop.create_task(self._monitor_loop())
        except RuntimeError:
            logger.debug("No event loop for Conductor monitor")

    async def stop(self) -> None:
        """Stop monitoring and unsubscribe from all agents."""
        self._running = False
        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            self._monitor_task = None

        for task_id, unsub in self._unsubscribes.items():
            try:
                unsub()
            except Exception:
                pass
        self._unsubscribes.clear()

    # =========================================================================
    # Event handling
    # =========================================================================

    def _on_agent_event(self, task_id: str, event: AgentEvent) -> None:
        """Process events from individual agents."""
        if event.type == GUARDIAN_INTERVENTION:
            self._interventions.append({
                "task_id": task_id,
                "type": event.data.get("type", ""),
                "message": event.data.get("message", ""),
                "tool": event.data.get("tool", ""),
                "timestamp": time.time(),
            })

        elif event.type == TOOL_EXEC_END:
            if not event.data.get("success", True):
                self._tool_failures.append({
                    "task_id": task_id,
                    "tool": event.data.get("tool", ""),
                    "error": event.data.get("error", ""),
                    "timestamp": time.time(),
                })

    # =========================================================================
    # Monitor loop
    # =========================================================================

    async def _monitor_loop(self) -> None:
        """Periodically check for cross-agent patterns."""
        while self._running:
            try:
                await asyncio.sleep(self._config.check_interval_seconds)
                self._check_systemic_bridge_failure()
                self._check_common_tool_failure()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"Conductor monitor error: {e}")

    def _check_systemic_bridge_failure(self) -> None:
        """Detect when multiple agents are stuck on HTTP bridge errors."""
        lookback = 30.0  # seconds
        now = time.time()
        cutoff = now - lookback

        # Find agents with recent "stuck" interventions
        stuck_agents: Set[str] = set()
        for intervention in self._interventions:
            if (intervention["timestamp"] > cutoff
                    and intervention["type"] in ("stuck", "looping")):
                stuck_agents.add(intervention["task_id"])

        if len(stuck_agents) >= self._config.bridge_failure_quorum:
            key = f"bridge_stuck_{len(stuck_agents)}"
            if self._should_report(key):
                issue = {
                    "type": "systemic_bridge_failure",
                    "message": (
                        f"{len(stuck_agents)} agents stuck simultaneously. "
                        f"Rhino HTTP bridge may be down."
                    ),
                    "affected_agents": sorted(stuck_agents),
                    "timestamp": now,
                }
                self._systemic_issues.append(issue)
                logger.warning(f"Conductor: {issue['message']}")

                # Steer affected agents to abort
                for tid in stuck_agents:
                    agent = self._agents.get(tid)
                    if agent and hasattr(agent, "steer"):
                        agent.steer(
                            "[CONDUCTOR] Rhino bridge appears down. "
                            "Wrap up with whatever progress you have."
                        )
                        agent.abort()

    def _check_common_tool_failure(self) -> None:
        """Detect when multiple agents fail on the same tool."""
        lookback = 30.0
        now = time.time()
        cutoff = now - lookback

        # Count failures per tool across agents
        tool_agents: Dict[str, Set[str]] = {}
        for failure in self._tool_failures:
            if failure["timestamp"] > cutoff:
                tool = failure["tool"]
                if tool not in tool_agents:
                    tool_agents[tool] = set()
                tool_agents[tool].add(failure["task_id"])

        for tool, agents in tool_agents.items():
            if len(agents) >= self._config.systemic_tool_quorum:
                key = f"tool_failure_{tool}"
                if self._should_report(key):
                    issue = {
                        "type": "common_tool_failure",
                        "tool": tool,
                        "message": (
                            f"Tool '{tool}' failing across {len(agents)} agents. "
                            f"May indicate a systemic issue."
                        ),
                        "affected_agents": sorted(agents),
                        "timestamp": now,
                    }
                    self._systemic_issues.append(issue)
                    logger.warning(f"Conductor: {issue['message']}")

    def _should_report(self, key: str) -> bool:
        """Deduplication: suppress same issue within window."""
        now = time.time()
        last = self._dedup_keys.get(key, 0)
        if now - last < self._config.dedup_window_seconds:
            return False
        self._dedup_keys[key] = now
        return True

    # =========================================================================
    # Report
    # =========================================================================

    def report(self) -> ConductorReport:
        """Generate fleet-level aggregate report from collected results."""
        total = len(self._results)
        completed = 0
        errored = 0
        total_cost = 0.0
        total_input = 0
        total_output = 0
        alignment_scores = []
        per_agent = []
        failure_tool_counts: Dict[str, int] = {}

        for task_id, result in self._results.items():
            metrics = getattr(result, "metrics", {})
            if isinstance(metrics, dict):
                total_cost += metrics.get("cost_usd", 0)
                total_input += metrics.get("input_tokens", 0)
                total_output += metrics.get("output_tokens", 0)

            status = getattr(result, "status", "unknown")
            if status == "success":
                completed += 1
            else:
                errored += 1

            # Guardian alignment
            guardian_report = getattr(result, "guardian_report", {})
            if isinstance(guardian_report, dict):
                score = guardian_report.get("alignment_score", 1.0)
                alignment_scores.append(score)

            # Broken tools
            broken = getattr(result, "broken_tools", [])
            for tool in broken:
                failure_tool_counts[tool] = failure_tool_counts.get(tool, 0) + 1

            per_agent.append({
                "task_id": task_id,
                "status": status,
                "cost_usd": metrics.get("cost_usd", 0) if isinstance(metrics, dict) else 0,
                "turns": metrics.get("turns", 0) if isinstance(metrics, dict) else 0,
                "substrate_summary": getattr(result, "substrate_summary", {}) or {},
            })

        # Common failure tools (appearing in 2+ agents)
        common_failures = sorted(
            t for t, c in failure_tool_counts.items()
            if c >= self._config.systemic_tool_quorum
        )

        avg_alignment = (
            sum(alignment_scores) / len(alignment_scores)
            if alignment_scores else 1.0
        )

        wall_time = round(time.time() - self._start_time, 2) if self._start_time else 0.0
        all_tool_observations: List[dict] = []
        for result in self._results.values():
            tools_called = getattr(result, "tools_called", []) or []
            if isinstance(tools_called, list):
                all_tool_observations.extend(
                    tool
                    for tool in tools_called
                    if isinstance(tool, dict) and tool.get("route_taken")
                )
        substrate_summary = summarize_substrate_observations(all_tool_observations)

        return ConductorReport(
            total_agents=total,
            completed=completed,
            errored=errored,
            total_cost_usd=round(total_cost, 6),
            total_input_tokens=total_input,
            total_output_tokens=total_output,
            total_wall_time_s=wall_time,
            systemic_issues=list(self._systemic_issues),
            per_agent_summaries=per_agent,
            common_failure_tools=common_failures,
            avg_alignment_score=round(avg_alignment, 3),
            substrate_summary=substrate_summary,
        )
