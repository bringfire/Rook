"""
Guardian — Agent Trajectory Monitor
====================================

Lightweight observer that watches a spawned RookAgent's event stream
and steers it when stuck, looping, drifting, or burning budget.

Phase 1: Rule-based detection (stuck, looping, drift, budget).
Phase 2: Optional LLM trajectory analysis via cheap Haiku calls.

Ported from Engram's Guardian, adapted for Rhino/GH domain.

Usage:
    agent = RookAgent(config=config, tool_registry=registry)
    guardian = Guardian(agent, task_description="Create a box",
                        workspace_assets=["Layer::Boxes"])
    guardian.start()
    await agent.prompt(task)
    report = guardian.report()
    guardian.stop()
"""

import asyncio
import hashlib
import json
import logging
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Callable, Dict, List, Optional

from .config import GuardianConfig
from .events import AgentEvent, TOOL_EXEC_START, TOOL_EXEC_END, GUARDIAN_INTERVENTION
from .generation_params import sanitize_generation_params_for_model

logger = logging.getLogger(__name__)

# Default LLM model for trajectory analysis
DEFAULT_LLM_ANALYSIS_MODEL = "anthropic/claude-haiku-4-5-20251001"


# =============================================================================
# Report
# =============================================================================

@dataclass
class GuardianReport:
    """Trajectory analysis output, attached to SpawnResult.

    alignment_score is rule-based (1.0 = no interventions, 0.0 = max reached).
    """
    interventions: List[dict] = field(default_factory=list)
    trajectory_phases: List[str] = field(default_factory=list)
    alignment_score: float = 1.0
    total_interventions: int = 0
    stuck_count: int = 0
    loop_count: int = 0
    drift_count: int = 0
    budget_warnings: int = 0
    llm_analyses: List[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# =============================================================================
# Phase signals — Rhino/GH specific
# =============================================================================

PHASE_SIGNALS: Dict[str, str] = {
    # Rhino
    "rhino_objects": "exploring",
    "rhino_geometry": "exploring",
    "rhino_selection": "exploring",
    "rhino_layers": "exploring",
    "rhino_viewport": "exploring",
    "rhino_document": "exploring",
    "rhino_measure_": "measuring",
    "rhino_execute_intent": "creating",
    "rhino_create": "creating",
    "rhino_extrude": "creating",
    "rhino_loft": "creating",
    "rhino_sweep": "creating",
    "rhino_transform": "transforming",
    "rhino_copy": "transforming",
    "rhino_boolean": "combining",
    "rhino_material_ops": "finishing",
    "rhino_apply_uv_": "finishing",
    "rhino_export": "exporting",
    # GH
    "gh_snapshot": "exploring",
    "gh_execute_intent": "creating",
    "gh_edit": "creating",
    "gh_errors": "debugging",
    "gh_explore_": "exploring",
    # Knowledge
    "knowledge_query": "researching",
    "rhino_knowledge_query": "researching",
    "gh_knowledge_query": "researching",
}


# =============================================================================
# Helpers
# =============================================================================

def _call_hash(entry: dict) -> str:
    """Deterministic hash of tool name + sorted params for loop detection."""
    tool = entry.get("tool", "")
    params = entry.get("params", {})
    key = json.dumps({"t": tool, "p": params}, sort_keys=True, default=str)
    return hashlib.sha256(key.encode()).hexdigest()[:12]


def _summarize_tool_call(entry: dict, max_params_len: int = 60) -> str:
    """One-line summary of a tool call for the LLM analysis prompt."""
    tool = entry.get("tool", "?")
    ok = "ok" if entry.get("success") else "FAIL"
    params = entry.get("params", {})
    param_str = ", ".join(f"{k}={str(v)[:20]}" for k, v in list(params.items())[:4])
    if len(param_str) > max_params_len:
        param_str = param_str[:max_params_len - 3] + "..."
    return f"  {tool}({param_str}) -> {ok}"


# =============================================================================
# LLM analysis prompt
# =============================================================================

_LLM_ANALYSIS_PROMPT = """\
You are monitoring an AI agent working on this task:
{task_description}

The agent has made {call_count} tool calls. Recent activity (last 10):
{recent_activity}

Trajectory phases so far: {trajectory_phases}
Guardian has intervened {intervention_count} times.{intervention_summary}

Evaluate:
1. Is the agent making progress? (yes/no + brief reasoning)
2. Alignment score (0.0-1.0, where 1.0 = perfect progress, 0.0 = completely off track)
3. Should I steer the agent? If yes, provide a concise corrective message.

Respond ONLY with a JSON object (no markdown, no explanation):
{{"making_progress": true, "reasoning": "...", "alignment_score": 0.8, "should_steer": false, "steer_message": ""}}"""


# =============================================================================
# Guardian
# =============================================================================

class Guardian:
    """Monitors a RookAgent and steers it when needed.

    Subscribes to the agent's event stream and periodically evaluates
    whether the agent is on track. Can detect stuck patterns, loops,
    workspace drift, and budget burn, then inject steering messages.
    """

    def __init__(
        self,
        agent: Any,
        config: Optional[GuardianConfig] = None,
        workspace_assets: Optional[List[str]] = None,
        task_description: str = "",
    ):
        self._agent = agent
        self._config = config or GuardianConfig()
        self._workspace_assets = workspace_assets or []
        self._task_description = task_description

        # State
        self._tool_log: List[dict] = []
        self._pending_calls: Dict[str, dict] = {}
        self._interventions: List[dict] = []
        self._trajectory: List[str] = []
        self._current_phase: str = ""
        self._call_count: int = 0
        self._budget_warned: bool = False
        self._unsubscribe: Optional[Callable] = None

        # Per-rule cooldown
        self._last_stuck_at: int = -1
        self._last_loop_at: int = -1

        # LLM analysis state
        self._llm_analyses: List[dict] = []
        self._last_llm_at: int = 0
        self._llm_analysis_interval: int = (
            self._config.check_interval * self._config.llm_analysis_interval_multiplier
        )
        self._llm_running: bool = False
        self._llm_task: Optional[asyncio.Task] = None

    def start(self) -> None:
        """Subscribe to agent events."""
        self._unsubscribe = self._agent.subscribe(self._on_event)

    def stop(self) -> None:
        """Unsubscribe from events and clean up."""
        if self._unsubscribe:
            self._unsubscribe()
            self._unsubscribe = None
        self._pending_calls.clear()
        if self._llm_task and not self._llm_task.done():
            self._llm_task.cancel()
            self._llm_task = None
            self._llm_running = False

    # =========================================================================
    # Event handling
    # =========================================================================

    def _on_event(self, event: AgentEvent) -> None:
        """Process each agent event."""
        if event.type == TOOL_EXEC_START:
            call_id = event.data.get("call_id", "")
            self._pending_calls[call_id] = {
                "tool": event.data.get("tool", ""),
                "params": event.data.get("params", {}),
            }

        elif event.type == TOOL_EXEC_END:
            call_id = event.data.get("call_id", "")
            pending = self._pending_calls.pop(call_id, {})

            entry = {
                "tool": event.data.get("tool", pending.get("tool", "")),
                "success": event.data.get("success", False),
                "params": pending.get("params", {}),
            }
            self._tool_log.append(entry)
            self._call_count += 1

            self._update_phase(entry["tool"], entry["success"])

            if self._call_count % self._config.check_interval == 0:
                self._analyze()

    # =========================================================================
    # Detection rules
    # =========================================================================

    def _analyze(self) -> None:
        """Run all detection rules on recent tool history."""
        if len(self._interventions) >= self._config.max_interventions:
            return
        self._check_consecutive_failures()
        self._check_identical_loops()
        self._check_workspace_drift()
        self._check_budget()

        # LLM trajectory analysis (async, fire-and-forget)
        if (self._config.enable_llm_analysis
                and not self._llm_running
                and self._call_count - self._last_llm_at >= self._llm_analysis_interval):
            self._schedule_llm_analysis()

    def _check_consecutive_failures(self) -> None:
        """Detect same tool failing N times in a row."""
        n = self._config.max_consecutive_failures
        recent = self._tool_log[-n:]
        if len(recent) < n:
            return
        if self._last_stuck_at >= self._call_count - n:
            return

        if (all(not r.get("success", True) for r in recent)
                and len(set(r.get("tool") for r in recent)) == 1):
            tool = recent[0].get("tool", "unknown")
            self._last_stuck_at = self._call_count
            self._intervene(
                "stuck",
                f"Tool '{tool}' has failed {n} times consecutively. "
                f"Try a different approach or skip this step.",
            )

    def _check_identical_loops(self) -> None:
        """Detect same tool+params called repeatedly."""
        n = self._config.max_identical_calls
        recent = self._tool_log[-n:]
        if len(recent) < n:
            return
        if self._last_loop_at >= self._call_count - n:
            return

        hashes = [_call_hash(r) for r in recent]
        if len(set(hashes)) == 1:
            tool = recent[0].get("tool", "unknown")
            self._last_loop_at = self._call_count
            self._intervene(
                "looping",
                f"You've called '{tool}' with identical parameters {n} times. "
                f"The result won't change. Try different parameters or a different tool.",
            )

    def _check_workspace_drift(self) -> None:
        """Detect operations on assets outside workspace constraint.

        In Rook, workspace_assets can be layer names (e.g., "Layer::Walls")
        or object name prefixes. This checks if tool params reference objects
        outside the allowed workspace.
        """
        if not self._workspace_assets:
            return

        layer_assets = [a.replace("Layer::", "") for a in self._workspace_assets
                        if a.startswith("Layer::")]
        name_assets = [a for a in self._workspace_assets
                       if not a.startswith("Layer::")]

        window = self._tool_log[-self._config.check_interval:]
        for entry in window:
            params = entry.get("params", {})
            # Check layer references in common params
            layer = params.get("layer", "") or params.get("layer_name", "")
            if layer and layer_assets:
                if layer not in layer_assets:
                    self._intervene(
                        "drift",
                        f"You're modifying layer '{layer}' which is outside your workspace. "
                        f"Only modify: {self._workspace_assets}",
                    )
                    return

            # Check object name references
            if name_assets:
                obj_name = params.get("name", "") or params.get("object_name", "")
                if obj_name:
                    if not any(obj_name.startswith(prefix) for prefix in name_assets):
                        self._intervene(
                            "drift",
                            f"You're modifying object '{obj_name}' which is outside your workspace. "
                            f"Only modify objects matching: {name_assets}",
                        )
                        return

    def _check_budget(self) -> None:
        """Warn if token consumption suggests budget exhaustion."""
        if self._budget_warned:
            return

        used = self._agent.token_usage.get("input", 0)
        budget = getattr(self._agent, "config", None)
        if not budget:
            return
        max_tokens = getattr(budget, "max_input_tokens_per_task", 0)
        if max_tokens <= 0:
            return

        fraction = used / max_tokens
        if fraction >= self._config.budget_warning_threshold:
            self._budget_warned = True
            remaining_pct = int((1 - fraction) * 100)
            self._intervene(
                "budget",
                f"You've used {int(fraction * 100)}% of your token budget. "
                f"Only {remaining_pct}% remains. Wrap up or simplify your approach.",
            )

    # =========================================================================
    # LLM trajectory analysis
    # =========================================================================

    def _schedule_llm_analysis(self) -> None:
        """Schedule an async LLM analysis task."""
        try:
            loop = asyncio.get_running_loop()
            self._llm_running = True
            self._last_llm_at = self._call_count
            self._llm_task = loop.create_task(self._run_llm_analysis())
        except RuntimeError:
            logger.debug("No running event loop for LLM analysis")

    async def _run_llm_analysis(self) -> None:
        """Make a cheap Haiku LLM call to evaluate agent trajectory."""
        try:
            import litellm

            prompt = self._build_llm_analysis_prompt()

            llm_kwargs = dict(
                model=self._config.llm_analysis_model,
                messages=[
                    {"role": "system", "content": "You are a concise agent monitor. Respond only with valid JSON."},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=300,
                temperature=0.0,
            )
            llm_kwargs = sanitize_generation_params_for_model(
                self._config.llm_analysis_model,
                llm_kwargs,
            )
            if self._config.api_base:
                llm_kwargs["api_base"] = self._config.api_base
            response = await litellm.acompletion(**llm_kwargs)

            text = response.choices[0].message.content or ""
            result = self._parse_llm_analysis(text)

            try:
                cost = litellm.completion_cost(completion_response=response)
            except Exception:
                cost = 0.0

            analysis_record = {
                "call_count": self._call_count,
                "timestamp": time.time(),
                "making_progress": result.get("making_progress", True),
                "reasoning": result.get("reasoning", ""),
                "alignment_score": result.get("alignment_score", 1.0),
                "should_steer": result.get("should_steer", False),
                "steer_message": result.get("steer_message", ""),
                "cost_usd": round(cost, 6),
            }
            self._llm_analyses.append(analysis_record)

            logger.info(
                f"Guardian LLM analysis at call {self._call_count}: "
                f"progress={result.get('making_progress')}, "
                f"alignment={result.get('alignment_score')}"
            )

            if result.get("should_steer") and result.get("steer_message"):
                self._intervene("llm_analysis", result["steer_message"])

        except ImportError:
            logger.debug("litellm not available for Guardian LLM analysis")
        except Exception as e:
            logger.warning(f"Guardian LLM analysis failed: {e}")
        finally:
            self._llm_running = False

    def _build_llm_analysis_prompt(self) -> str:
        """Build the analysis prompt from current state."""
        recent = self._tool_log[-10:]
        activity_lines = [_summarize_tool_call(e) for e in recent]
        recent_activity = "\n".join(activity_lines) if activity_lines else "  (no tool calls yet)"

        phases = " -> ".join(self._trajectory) if self._trajectory else "(none yet)"

        intervention_summary = ""
        if self._interventions:
            recent_interventions = self._interventions[-3:]
            lines = [f"\n  - [{i['type']}] {i['message'][:80]}" for i in recent_interventions]
            intervention_summary = "\nRecent interventions:" + "".join(lines)

        return _LLM_ANALYSIS_PROMPT.format(
            task_description=self._task_description or "(no description provided)",
            call_count=self._call_count,
            recent_activity=recent_activity,
            trajectory_phases=phases,
            intervention_count=len(self._interventions),
            intervention_summary=intervention_summary,
        )

    @staticmethod
    def _parse_llm_analysis(text: str) -> dict:
        """Parse the LLM's JSON response, tolerating markdown fences."""
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [line for line in lines if not line.strip().startswith("```")]
            text = "\n".join(lines).strip()

        try:
            result = json.loads(text)
            if not isinstance(result, dict):
                return {}
            score = result.get("alignment_score", 1.0)
            if isinstance(score, (int, float)):
                result["alignment_score"] = max(0.0, min(1.0, float(score)))
            else:
                result["alignment_score"] = 1.0
            return result
        except (json.JSONDecodeError, ValueError):
            logger.warning(f"Failed to parse LLM analysis JSON: {text[:100]}")
            return {}

    # =========================================================================
    # Intervention
    # =========================================================================

    def _intervene(self, issue_type: str, message: str) -> None:
        """Record intervention and optionally steer the agent."""
        if len(self._interventions) >= self._config.max_interventions:
            return

        latest_tool = self._tool_log[-1].get("tool", "") if self._tool_log else ""
        intervention = {
            "turn": self._call_count,
            "type": issue_type,
            "message": message,
            "timestamp": time.time(),
            "tool": latest_tool,
        }
        self._interventions.append(intervention)

        phase = "stuck" if issue_type in ("stuck", "looping") else issue_type
        if self._current_phase != phase:
            self._current_phase = phase
            self._trajectory.append(phase)

        logger.info(f"Guardian [{issue_type}] at call {self._call_count}: {message}")

        # Emit event via public API
        self._agent.emit_event(AgentEvent(GUARDIAN_INTERVENTION, {
            "type": issue_type,
            "message": message,
            "call_count": self._call_count,
            "total_interventions": len(self._interventions),
            "tool": latest_tool,
        }))

        # Steer the agent
        at_limit = len(self._interventions) >= self._config.max_interventions
        if self._config.enable_steering:
            if at_limit:
                self._agent.steer(
                    f"[GUARDIAN - ABORT] {message} "
                    f"Too many interventions ({self._config.max_interventions}). "
                    f"Wrap up immediately with whatever progress you have."
                )
                logger.warning(
                    f"Guardian: {self._config.max_interventions} interventions reached"
                )
                self._agent.abort()
            else:
                self._agent.steer(f"[GUARDIAN - {issue_type.upper()}] {message}")

    # =========================================================================
    # Trajectory phase tracking
    # =========================================================================

    def _update_phase(self, tool_name: str, success: bool) -> None:
        """Track what phase the agent is in based on tool patterns."""
        # Recovery detection
        if self._current_phase == "stuck" and success:
            self._current_phase = "recovered"
            self._trajectory.append("recovered")
            return

        # Match tool name to phase (supports prefix matching)
        new_phase = ""
        for pattern, phase in PHASE_SIGNALS.items():
            if tool_name == pattern or tool_name.startswith(pattern):
                new_phase = phase
                break

        # Debugging detection: inspection tools after a failure
        if (tool_name in ("gh_errors", "rhino_objects", "rhino_geometry")
                and len(self._tool_log) >= 2
                and not self._tool_log[-2].get("success", True)):
            new_phase = "debugging"

        if new_phase and new_phase != self._current_phase:
            self._current_phase = new_phase
            self._trajectory.append(new_phase)

    # =========================================================================
    # Report
    # =========================================================================

    def report(self) -> GuardianReport:
        """Generate final trajectory report."""
        stuck_count = sum(1 for i in self._interventions if i["type"] == "stuck")
        loop_count = sum(1 for i in self._interventions if i["type"] == "looping")
        drift_count = sum(1 for i in self._interventions if i["type"] == "drift")
        budget_warnings = sum(1 for i in self._interventions if i["type"] == "budget")

        total = len(self._interventions)
        per_intervention = 1.0 / max(self._config.max_interventions, 1)
        alignment = max(0.0, 1.0 - (total * per_intervention))

        return GuardianReport(
            interventions=list(self._interventions),
            trajectory_phases=list(self._trajectory),
            alignment_score=round(alignment, 2),
            total_interventions=total,
            stuck_count=stuck_count,
            loop_count=loop_count,
            drift_count=drift_count,
            budget_warnings=budget_warnings,
            llm_analyses=list(self._llm_analyses),
        )
