"""Passive substrate telemetry for agent execution.

This module keeps substrate-aware execution insight read-only.
It extracts `route_taken` / `execution_route` metadata from tool results,
records compact observations, and computes advisory summaries for:

- CapabilityRouter promotion candidates
- Conductor fleet health visibility
- Downstream knowledge analytics

It intentionally does not mutate router coverage or execution policy.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, List


PROMOTABLE_SUBSTRATES = frozenset({"known_command"})
INTERACTIVE_SUBSTRATES = frozenset({"interactive"})


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
