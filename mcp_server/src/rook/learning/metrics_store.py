"""Metrics capture and storage for Rook.

Records per-tool observations with timing, success, knowledge injection status,
and aggregates into daily PeriodMetrics and per-tool ToolMetrics. Enables A/B
comparison of tool success rates with vs without knowledge injection.

Adapted from Engram's MetricsStore pattern, with additions for DSPy confidence
tracking and workflow phase awareness.

Storage: knowledge/metrics.json (auto-saved every 10 observations).
"""

import copy
import json
import logging
import os
import uuid
from collections import deque
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from ..runtime_paths import resolve_writable_knowledge_path
from ..tool_lifecycle import DispatchOrigin, LifecycleEntry

logger = logging.getLogger(__name__)

DEFAULT_METRICS_PATH = resolve_writable_knowledge_path("metrics.json")
_PROCESS_START_TOKEN = uuid.uuid4().hex


@dataclass
class Observation:
    """Single tool call observation."""

    tool_name: str
    success: bool
    duration_ms: float
    knowledge_injected: bool
    knowledge_hint: str
    gotchas_provided: list[str]
    correction_detected: bool
    attempt_number: int
    phase: str
    timestamp: str
    # Optional enrichments
    intent: str = ""
    dspy_confidence: float = 0.0
    components_created: int = 0
    error_message: str = ""
    origin: str = "native"  # "native" (direct MCP) | "meta" (via rook_tools_call re-entry)


@dataclass
class PeriodMetrics:
    """Daily aggregate metrics with A/B fields."""

    date: str
    total_calls: int = 0
    successes: int = 0
    failures: int = 0
    # A/B: with vs without knowledge
    calls_with_knowledge: int = 0
    successes_with_knowledge: int = 0
    calls_without_knowledge: int = 0
    successes_without_knowledge: int = 0
    # Timing
    total_duration_ms: float = 0.0
    max_duration_ms: float = 0.0
    # Knowledge
    corrections_detected: int = 0
    first_attempt_successes: int = 0
    first_attempt_total: int = 0
    # DSPy
    dspy_calls: int = 0
    dspy_total_confidence: float = 0.0

    @property
    def success_rate(self) -> float:
        return self.successes / self.total_calls if self.total_calls else 0.0

    @property
    def success_rate_with_knowledge(self) -> float:
        return (self.successes_with_knowledge / self.calls_with_knowledge
                if self.calls_with_knowledge else 0.0)

    @property
    def success_rate_without_knowledge(self) -> float:
        return (self.successes_without_knowledge / self.calls_without_knowledge
                if self.calls_without_knowledge else 0.0)

    @property
    def avg_duration_ms(self) -> float:
        return self.total_duration_ms / self.total_calls if self.total_calls else 0.0

    @property
    def first_attempt_success_rate(self) -> float:
        return (self.first_attempt_successes / self.first_attempt_total
                if self.first_attempt_total else 0.0)

    @property
    def dspy_avg_confidence(self) -> float:
        return (self.dspy_total_confidence / self.dspy_calls
                if self.dspy_calls else 0.0)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["success_rate"] = round(self.success_rate, 4)
        d["success_rate_with_knowledge"] = round(self.success_rate_with_knowledge, 4)
        d["success_rate_without_knowledge"] = round(self.success_rate_without_knowledge, 4)
        d["avg_duration_ms"] = round(self.avg_duration_ms, 1)
        d["first_attempt_success_rate"] = round(self.first_attempt_success_rate, 4)
        d["dspy_avg_confidence"] = round(self.dspy_avg_confidence, 4)
        return d


@dataclass
class ToolMetrics:
    """Per-tool aggregate metrics."""

    tool_name: str
    calls: int = 0
    successes: int = 0
    failures: int = 0
    total_duration_ms: float = 0.0
    with_knowledge: int = 0
    successes_with_knowledge: int = 0
    corrections: int = 0

    @property
    def success_rate(self) -> float:
        return self.successes / self.calls if self.calls else 0.0

    @property
    def avg_duration_ms(self) -> float:
        return self.total_duration_ms / self.calls if self.calls else 0.0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["success_rate"] = round(self.success_rate, 4)
        d["avg_duration_ms"] = round(self.avg_duration_ms, 1)
        return d


class MetricsStore:
    """Singleton metrics store with auto-save.

    Records observations, updates daily PeriodMetrics and per-tool ToolMetrics,
    and persists to a JSON file every 10 observations.
    """

    def __init__(self, path: Path = DEFAULT_METRICS_PATH):
        self._path = path
        self._periods: dict[str, PeriodMetrics] = {}
        self._tools: dict[str, ToolMetrics] = {}
        self._recent: deque[dict] = deque(maxlen=50)
        self._containment_denials: deque[dict[str, str]] = deque(maxlen=50)
        self._dirty_count = 0
        self._recording_failures = 0
        self._load()

    def _load(self) -> None:
        """Load metrics from disk."""
        if not self._path.exists():
            return
        try:
            with open(self._path, encoding="utf-8") as f:
                data = json.load(f)

            for date_str, pdata in data.get("periods", {}).items():
                pdata.pop("success_rate", None)
                pdata.pop("success_rate_with_knowledge", None)
                pdata.pop("success_rate_without_knowledge", None)
                pdata.pop("avg_duration_ms", None)
                pdata.pop("first_attempt_success_rate", None)
                pdata.pop("dspy_avg_confidence", None)
                self._periods[date_str] = PeriodMetrics(**pdata)

            for tool_name, tdata in data.get("tools", {}).items():
                tdata.pop("success_rate", None)
                tdata.pop("avg_duration_ms", None)
                self._tools[tool_name] = ToolMetrics(**tdata)

            for obs in data.get("recent", []):
                self._recent.append(obs)

            for event in data.get("containment_denials", []):
                self._containment_denials.append(event)

            logger.info(f"Loaded metrics: {len(self._periods)} periods, {len(self._tools)} tools")
        except Exception as e:
            logger.warning(f"Failed to load metrics from {self._path}: {e}")

    def save(self) -> None:
        """Persist metrics to disk."""
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "periods": {k: v.to_dict() for k, v in self._periods.items()},
                "tools": {k: v.to_dict() for k, v in self._tools.items()},
                "recent": list(self._recent),
                "containment_denials": list(self._containment_denials),
            }
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            self._dirty_count = 0
        except Exception as e:
            logger.warning(f"Failed to save metrics: {e}")

    def record(self, obs: Observation) -> None:
        """Record one observation. Updates period and tool metrics."""
        try:
            today = obs.timestamp[:10]  # "2026-02-07"

            # Period metrics
            period = self._periods.get(today)
            if not period:
                period = PeriodMetrics(date=today)
                self._periods[today] = period

            period.total_calls += 1
            period.total_duration_ms += obs.duration_ms
            period.max_duration_ms = max(period.max_duration_ms, obs.duration_ms)

            if obs.success:
                period.successes += 1
            else:
                period.failures += 1

            if obs.knowledge_injected:
                period.calls_with_knowledge += 1
                if obs.success:
                    period.successes_with_knowledge += 1
            else:
                period.calls_without_knowledge += 1
                if obs.success:
                    period.successes_without_knowledge += 1

            if obs.correction_detected:
                period.corrections_detected += 1

            if obs.attempt_number == 1:
                period.first_attempt_total += 1
                if obs.success:
                    period.first_attempt_successes += 1

            if obs.dspy_confidence > 0:
                period.dspy_calls += 1
                period.dspy_total_confidence += obs.dspy_confidence

            # Tool metrics
            tool = self._tools.get(obs.tool_name)
            if not tool:
                tool = ToolMetrics(tool_name=obs.tool_name)
                self._tools[obs.tool_name] = tool

            tool.calls += 1
            tool.total_duration_ms += obs.duration_ms
            if obs.success:
                tool.successes += 1
            else:
                tool.failures += 1
            if obs.knowledge_injected:
                tool.with_knowledge += 1
                if obs.success:
                    tool.successes_with_knowledge += 1
            if obs.correction_detected:
                tool.corrections += 1

            # Recent observations (for live feed)
            self._recent.append({
                "tool": obs.tool_name,
                "success": obs.success,
                "duration_ms": round(obs.duration_ms, 1),
                "knowledge": obs.knowledge_injected,
                "hint": obs.knowledge_hint[:80] if obs.knowledge_hint else "",
                "phase": obs.phase,
                "timestamp": obs.timestamp,
                "intent": obs.intent,
                "error": obs.error_message[:100] if obs.error_message else "",
            })

            # Auto-save
            self._dirty_count += 1
            if self._dirty_count >= 10:
                self.save()

        except Exception as e:
            self._recording_failures += 1
            logger.warning(f"Failed to record observation: {e}")

    def record_containment_denial(
        self,
        entry: LifecycleEntry,
        origin: DispatchOrigin,
    ) -> None:
        """Append one closed-schema lifecycle denial event."""
        if type(entry) is not LifecycleEntry:
            raise TypeError("entry must be a LifecycleEntry")
        if type(origin) is not DispatchOrigin:
            raise TypeError("origin must be a DispatchOrigin")

        timestamp = (
            datetime.now(timezone.utc)
            .isoformat(timespec="microseconds")
            .replace("+00:00", "Z")
        )
        self._containment_denials.append(
            {
                "tool": entry.name,
                "disposition": entry.disposition.value,
                "origin": origin.value,
                "timestamp": timestamp,
            }
        )
        self._dirty_count += 1
        if self._dirty_count >= 10:
            self.save()

    def get_containment_denials_snapshot(self) -> dict[str, object]:
        """Return a process-bound defensive copy of the denial ring."""
        return {
            "process_id": os.getpid(),
            "process_start_token": _PROCESS_START_TOKEN,
            "events": copy.deepcopy(list(self._containment_denials)),
        }

    def get_current_period(self) -> Optional[PeriodMetrics]:
        """Get today's period metrics."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return self._periods.get(today)

    def get_tool_metrics(self) -> dict[str, dict]:
        """Get all tool metrics as dicts."""
        return {k: v.to_dict() for k, v in self._tools.items()}

    def get_recent(self, n: int = 20) -> list[dict]:
        """Get last N observations."""
        return list(self._recent)[-n:]

    def get_period_history(self, days: int = 30) -> dict[str, dict]:
        """Get the last N days of period metrics as dicts."""
        sorted_periods = sorted(self._periods.items())[-days:]
        return {k: v.to_dict() for k, v in sorted_periods}

    def get_summary(self) -> dict:
        """Get a summary suitable for the metrics_summary MCP tool."""
        today = self.get_current_period()

        # Top 5 most-called tools
        sorted_tools = sorted(
            self._tools.values(), key=lambda t: t.calls, reverse=True
        )[:10]

        # Top 5 failing tools (by failure count, min 2 failures)
        failing_tools = sorted(
            [t for t in self._tools.values() if t.failures >= 2],
            key=lambda t: t.failures,
            reverse=True,
        )[:5]

        summary = {
            "today": today.to_dict() if today else None,
            "all_time": {
                "total_calls": sum(p.total_calls for p in self._periods.values()),
                "total_successes": sum(p.successes for p in self._periods.values()),
                "total_failures": sum(p.failures for p in self._periods.values()),
                "days_tracked": len(self._periods),
                "tools_tracked": len(self._tools),
            },
            "top_tools": [t.to_dict() for t in sorted_tools],
            "failing_tools": [t.to_dict() for t in failing_tools],
        }

        # A/B comparison (all-time)
        total_with = sum(p.calls_with_knowledge for p in self._periods.values())
        success_with = sum(p.successes_with_knowledge for p in self._periods.values())
        total_without = sum(p.calls_without_knowledge for p in self._periods.values())
        success_without = sum(p.successes_without_knowledge for p in self._periods.values())

        summary["ab_comparison"] = {
            "with_knowledge": {
                "calls": total_with,
                "successes": success_with,
                "success_rate": round(success_with / total_with, 4) if total_with else 0.0,
            },
            "without_knowledge": {
                "calls": total_without,
                "successes": success_without,
                "success_rate": round(success_without / total_without, 4) if total_without else 0.0,
            },
        }

        summary["recording_health"] = {
            "failures": self._recording_failures,
            "status": "healthy" if self._recording_failures == 0 else "degraded",
        }

        return summary


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_metrics_store: MetricsStore | None = None


def get_metrics_store() -> MetricsStore:
    """Get the global MetricsStore singleton."""
    global _metrics_store
    if _metrics_store is None:
        _metrics_store = MetricsStore()
    return _metrics_store
