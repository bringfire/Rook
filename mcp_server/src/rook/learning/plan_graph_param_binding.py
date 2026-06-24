"""LM4K pure memory-backed param binding (learning layer).

bind_params_from_memory resolves a node's producer params from the RUNTIME
graph.memory.facts substrate (populated by apply_producer_result -> _merge_memory)
instead of from node evidence. PURE: reads only graph.memory.facts, RETURNS merged
params, never writes node metadata, never mutates the graph or base params,
deep-copies all values.

Distinct from BindingSpec/bind_parameters (plan_graph_templates), which binds an
intent-descriptor field -> memory/metadata at CONSTRUCTION time. This is RUNTIME
memory -> params binding: the seam a future runner calls to source producer params
without the model. NO agent import, NO EXECUTION_PARAMS_KEY -- the caller assigns the
returned dict into node.metadata["execution_params"].
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from rook.learning.plan_graph import PlanGraph


@dataclass(frozen=True)
class ParamBindingFinding:
    code: str
    severity: Literal["error"]
    param_key: str | None
    message: str


@dataclass(frozen=True)
class ParamBindingResult:
    params: dict | None
    findings: tuple[ParamBindingFinding, ...]


def _finding(code: str, param_key: str | None, message: str) -> ParamBindingFinding:
    return ParamBindingFinding(
        code=code, severity="error", param_key=param_key, message=message
    )


_MISSING = object()


def bind_params_from_memory(
    base_params: "Mapping",
    graph: "PlanGraph",
    bindings: "Mapping[str, tuple[str, ...]]",
) -> ParamBindingResult:
    """Merge ``base_params`` with values sourced from ``graph.memory.facts`` along the
    explicit string-tuple paths in ``bindings`` (``{param_key: path}``).

    Returns merged params on full success. Processes ALL bindings and collects ALL
    findings; if ANY error finding exists, returns ``params=None`` (no partial bind).
    Pure: never mutates ``graph`` or ``base_params``; deep-copies base and every bound
    value.
    """
    if not isinstance(base_params, Mapping):
        return ParamBindingResult(
            params=None,
            findings=(
                _finding("base_params_invalid", None, "base_params is not a Mapping."),
            ),
        )

    try:
        merged: dict = deepcopy(dict(base_params))
    except Exception:
        return ParamBindingResult(
            params=None,
            findings=(
                _finding(
                    "base_params_copy_failed", None, "Could not deep-copy base_params."
                ),
            ),
        )

    findings: list[ParamBindingFinding] = []
    facts = graph.memory.facts

    for param_key, path in bindings.items():
        if not isinstance(param_key, str) or not param_key:
            findings.append(
                _finding(
                    "param_key_invalid",
                    None,
                    f"Binding param_key {param_key!r} is not a non-empty string.",
                )
            )
            continue
        if (
            not isinstance(path, tuple)
            or len(path) == 0
            or not all(isinstance(p, str) for p in path)
        ):
            findings.append(
                _finding(
                    "memory_path_invalid",
                    param_key,
                    f"Binding path {path!r} must be a non-empty tuple of strings.",
                )
            )
            continue

        current = facts
        resolved = _MISSING
        for i, key in enumerate(path):
            if not isinstance(current, Mapping):
                findings.append(
                    _finding(
                        "memory_fact_invalid",
                        param_key,
                        f"Path element {key!r} cannot descend into a non-Mapping.",
                    )
                )
                break
            if key not in current:
                findings.append(
                    _finding(
                        "memory_fact_missing",
                        param_key,
                        f"Memory fact key {key!r} is absent.",
                    )
                )
                break
            current = current[key]
            if i == len(path) - 1:
                resolved = current

        if resolved is _MISSING:
            continue
        try:
            merged[param_key] = deepcopy(resolved)
        except Exception:
            findings.append(
                _finding(
                    "memory_value_copy_failed",
                    param_key,
                    f"Could not deep-copy the memory value for {param_key!r}.",
                )
            )

    if findings:
        return ParamBindingResult(params=None, findings=tuple(findings))
    return ParamBindingResult(params=merged, findings=())
