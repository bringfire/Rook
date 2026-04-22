"""Passive substrate telemetry for agent execution.

This module keeps substrate-aware execution insight read-only.
It extracts `route_taken` / `execution_route` metadata from tool results,
records compact observations, and computes advisory summaries for:

- CapabilityRouter promotion candidates
- Conductor fleet health visibility
- Downstream knowledge analytics

It intentionally does not mutate router coverage or execution policy.

Persistence: `persist_substrate_observation` appends one JSONL line per
routed tool call to `knowledge/substrate_observations.jsonl`. This enables
historical hotspot scans across sessions; the in-memory summaries returned
by `summarize_substrate_observations` remain unchanged and session-scoped.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


logger = logging.getLogger(__name__)


PROMOTABLE_SUBSTRATES = frozenset({"known_command"})
INTERACTIVE_SUBSTRATES = frozenset({"interactive"})


def _default_persist_path() -> Path:
    """Resolve the canonical substrate-observations JSONL path (lazy import)."""
    from ..runtime_paths import resolve_writable_knowledge_path
    return resolve_writable_knowledge_path("substrate_observations.jsonl")


@dataclass
class SubstrateObservation:
    """Compact execution record for one tool call."""

    tool: str
    route_taken: str
    success: bool
    operation: str = ""
    verified: bool | None = None
    task_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _result_payload(result: dict[str, Any]) -> dict[str, Any]:
    """Return the nested result payload when present."""
    data = result.get("data", {})
    return data if isinstance(data, dict) else result


def extract_route_taken(result: dict[str, Any]) -> str:
    """Extract execution substrate from a tool result."""
    if not isinstance(result, dict):
        return ""

    payload = _result_payload(result)
    route = payload.get("route_taken") or payload.get("execution_route")
    if isinstance(route, str):
        return route

    route = result.get("route_taken") or result.get("execution_route")
    return route if isinstance(route, str) else ""


def extract_operation(tool_name: str, result: dict[str, Any]) -> str:
    """Best-effort operation key for telemetry aggregation."""
    payload = _result_payload(result)

    for key in ("operation", "command", "intent"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value

    for key in ("operation", "command", "intent"):
        value = result.get(key)
        if isinstance(value, str) and value:
            return value

    return tool_name


def extract_substrate_observation(
    tool_name: str,
    result: dict[str, Any],
    *,
    task_id: str = "",
) -> SubstrateObservation | None:
    """Build a telemetry record from a tool result.

    Returns None when the result has no substrate signal.
    """
    route_taken = extract_route_taken(result)
    if not route_taken:
        return None

    verified = result.get("verified")
    if not isinstance(verified, bool):
        verified = None

    return SubstrateObservation(
        tool=tool_name,
        route_taken=route_taken,
        success=bool(result.get("success", False)),
        operation=extract_operation(tool_name, result),
        verified=verified,
        task_id=task_id,
    )


def _compact_error(result: dict[str, Any], max_len: int = 120) -> str:
    """Derive a compact error string from a tool result.

    Mirrors the metrics_store fallback posture: prefer top-level `error`,
    then nested `data.error`, then stringified `data`. Returns empty string
    when the call succeeded or when no error payload is available.
    """
    if not isinstance(result, dict):
        return ""
    if result.get("success", False):
        return ""

    top_err = result.get("error")
    if isinstance(top_err, str) and top_err:
        return top_err[:max_len]

    data = result.get("data")
    if isinstance(data, dict):
        nested_err = data.get("error")
        if isinstance(nested_err, str) and nested_err:
            return nested_err[:max_len]

    if data:
        return str(data)[:max_len]
    return ""


def persist_substrate_observation(
    observation: "SubstrateObservation",
    *,
    error: str = "",
    session_id: str = "",
    path: Optional[Path] = None,
) -> None:
    """Append one JSONL line for a substrate observation.

    Best-effort — any I/O or serialization failure is logged and swallowed.
    Never raises, so telemetry can never break tool execution.

    Schema per line (key order stable for greppability):
        timestamp, session_id, tool, operation, route_taken,
        success, verified, error

    Args:
        observation: The SubstrateObservation returned by
            `extract_substrate_observation`.
        error: Compact error string (use `_compact_error(result)` at call site).
        session_id: Stable conversation/session identifier when available;
            empty string when the call site has no session handle.
        path: Override for the JSONL file path (primarily for tests).
    """
    try:
        target = path if path is not None else _default_persist_path()
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": session_id or observation.task_id or "",
            "tool": observation.tool,
            "operation": observation.operation or observation.tool,
            "route_taken": observation.route_taken,
            "success": bool(observation.success),
            "verified": observation.verified,
            "error": error,
        }
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False))
            fh.write("\n")
            fh.flush()
    except Exception as exc:
        logger.warning(
            "substrate_observations persist failed for tool=%s: %s",
            getattr(observation, "tool", "?"),
            exc,
        )


def load_substrate_observations_jsonl(
    path: Optional[Path] = None,
) -> List[dict[str, Any]]:
    """Read back persisted substrate observations (best-effort).

    Returns an empty list when the file is absent or unreadable.
    Malformed lines are skipped silently (JSONL is append-only, partial
    writes should be rare but not fatal to analysis).
    """
    target = path if path is not None else _default_persist_path()
    if not target.exists():
        return []
    records: List[dict[str, Any]] = []
    try:
        with target.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError as exc:
        logger.warning("substrate_observations read failed: %s", exc)
    return records


def summarize_substrate_observations(
    observations: Iterable[SubstrateObservation | dict[str, Any]],
) -> dict[str, Any]:
    """Produce passive telemetry summaries from execution observations."""
    normalized: List[dict[str, Any]] = []
    for obs in observations:
        if isinstance(obs, SubstrateObservation):
            normalized.append(obs.to_dict())
        elif isinstance(obs, dict) and obs.get("route_taken"):
            normalized.append(obs)

    if not normalized:
        return {
            "total_observations": 0,
            "route_counts": {},
            "tool_route_counts": {},
            "promotion_candidates": [],
            "interactive_hotspots": [],
        }

    route_counts: Dict[str, int] = {}
    tool_route_counts: Dict[str, Dict[str, int]] = {}
    op_route_stats: Dict[tuple[str, str, str], dict[str, Any]] = {}

    for obs in normalized:
        route = str(obs.get("route_taken", ""))
        tool = str(obs.get("tool", ""))
        operation = str(obs.get("operation") or tool)
        success = bool(obs.get("success", False))
        verified = obs.get("verified")
        unverified = verified is False

        route_counts[route] = route_counts.get(route, 0) + 1
        tool_route_counts.setdefault(tool, {})
        tool_route_counts[tool][route] = tool_route_counts[tool].get(route, 0) + 1

        key = (tool, operation, route)
        stats = op_route_stats.setdefault(
            key,
            {
                "tool": tool,
                "operation": operation,
                "route_taken": route,
                "count": 0,
                "successes": 0,
                "failures": 0,
                "unverified": 0,
            },
        )
        stats["count"] += 1
        if success:
            stats["successes"] += 1
        else:
            stats["failures"] += 1
        if unverified:
            stats["unverified"] += 1

    promotion_candidates: List[dict[str, Any]] = []
    interactive_hotspots: List[dict[str, Any]] = []

    for stats in op_route_stats.values():
        success_rate = (
            stats["successes"] / stats["count"] if stats["count"] else 0.0
        )
        entry = {
            **stats,
            "success_rate": round(success_rate, 3),
        }

        if (
            stats["route_taken"] in PROMOTABLE_SUBSTRATES
            and stats["successes"] >= 3
            and success_rate >= 0.8
        ):
            promotion_candidates.append(entry)

        if (
            stats["route_taken"] in INTERACTIVE_SUBSTRATES
            and (stats["count"] >= 2 or stats["unverified"] > 0 or stats["failures"] > 0)
        ):
            interactive_hotspots.append(entry)

    promotion_candidates.sort(
        key=lambda item: (-item["successes"], item["failures"], item["operation"])
    )
    interactive_hotspots.sort(
        key=lambda item: (-item["count"], -item["unverified"], item["operation"])
    )

    return {
        "total_observations": len(normalized),
        "route_counts": route_counts,
        "tool_route_counts": tool_route_counts,
        "promotion_candidates": promotion_candidates[:10],
        "interactive_hotspots": interactive_hotspots[:10],
    }
