"""LM3B/LM3C PlanGraph birth seam — template selection + parameter binding.

``select_template`` maps a structured intent descriptor to a registered,
hand-authored ``PlanGraph`` template (deterministic exact-match selection) and
returns a fresh copy plus an auditable selection record. ``bind_parameters``
injects declared descriptor values into a selected graph's node metadata and
graph memory facts (never structure / refs / ids / edges / status);
``select_and_bind`` composes the two. Binding deep-copies each value and emits
findings only on error.

It never builds a bespoke plan, infers from free text, scores/ranks, falls back,
interprets values, calls a model or live tool, or couples to ``planner.py``.

Production code here depends only on ``rook.learning.plan_graph``. Drive-side
modules (``plan_graph_walker`` / ``plan_graph_bridge``) are NOT imported — birth
is independent of drive.
"""

import copy
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Literal

from rook.learning.plan_graph import (
    PlanGraph,
    PlanGraphEdge,
    PlanGraphNode,
)


_SEVERITY_BY_CODE: dict[str, Literal["error", "info"]] = {
    "template_selected": "info",
    "no_matching_template": "error",
    "ambiguous_template": "error",
}

_BINDING_SEVERITY_BY_CODE: dict[str, Literal["info", "warning", "error"]] = {
    "missing_required_binding": "error",
    "unknown_binding_target": "error",
    "binding_value_copy_failed": "error",
}


@dataclass(frozen=True)
class BindingSpec:
    descriptor_field: str
    target: Literal["memory_fact", "node_metadata"]
    key: str
    node_id: str | None = None
    required: bool = False


@dataclass(frozen=True)
class TemplateEntry:
    template_id: str
    criteria: tuple[tuple[str, str], ...]
    build_graph: Callable[[], PlanGraph]
    bindings: tuple[BindingSpec, ...] = ()


@dataclass(frozen=True)
class CriterionCheck:
    field: str
    expected: str
    actual: str | None
    outcome: Literal["accepted", "missing_field", "value_mismatch"]


@dataclass(frozen=True)
class TemplateEvaluation:
    template_id: str
    matched: bool
    criteria: tuple[CriterionCheck, ...]


@dataclass(frozen=True)
class TemplateFinding:
    code: str
    severity: Literal["error", "info"]
    message: str
    template_ids: tuple[str, ...]


@dataclass(frozen=True)
class TemplateSelection:
    selected_template_id: str | None
    graph: PlanGraph | None
    evaluations: tuple[TemplateEvaluation, ...]
    findings: tuple[TemplateFinding, ...]


@dataclass(frozen=True)
class BindingFinding:
    code: str
    severity: Literal["info", "warning", "error"]
    field: str
    message: str


@dataclass(frozen=True)
class BindingResult:
    graph: PlanGraph | None
    findings: tuple[BindingFinding, ...]


@dataclass(frozen=True)
class SelectAndBindResult:
    selection: TemplateSelection
    binding: BindingResult | None


def _make_entry(
    template_id: str,
    criteria: Mapping[str, str],
    build_graph: Callable[[], PlanGraph],
    bindings: tuple[BindingSpec, ...] = (),
) -> TemplateEntry:
    return TemplateEntry(
        template_id=template_id,
        criteria=tuple(sorted(criteria.items())),
        build_graph=build_graph,
        bindings=bindings,
    )


def _finding(
    code: str, message: str, template_ids: tuple[str, ...]
) -> TemplateFinding:
    return TemplateFinding(
        code=code,
        severity=_SEVERITY_BY_CODE[code],
        message=message,
        template_ids=template_ids,
    )


def _binding_finding(code: str, field: str, message: str) -> BindingFinding:
    return BindingFinding(
        code=code,
        severity=_BINDING_SEVERITY_BY_CODE[code],
        field=field,
        message=message,
    )


def _evaluate(
    entry: TemplateEntry, descriptor: Mapping[str, str]
) -> TemplateEvaluation:
    checks: list[CriterionCheck] = []
    for field, expected in entry.criteria:
        if field not in descriptor:
            checks.append(
                CriterionCheck(
                    field=field,
                    expected=expected,
                    actual=None,
                    outcome="missing_field",
                )
            )
            continue
        actual = descriptor[field]
        checks.append(
            CriterionCheck(
                field=field,
                expected=expected,
                actual=actual,
                outcome="accepted" if actual == expected else "value_mismatch",
            )
        )
    matched = all(check.outcome == "accepted" for check in checks)
    return TemplateEvaluation(
        template_id=entry.template_id, matched=matched, criteria=tuple(checks)
    )


def _build_gh_csharp_create_repair() -> PlanGraph:
    """Bridge-drivable GH C# create-repair loop (the LM3A-proven path).

    create_script lands ``needs_repair`` from a ``created_with_errors`` receipt,
    which the ``on_repair`` edge routes to the in-place repair node; a ``usable``
    repair receipt drives the terminal repair node to ``succeeded`` → ``complete``.
    """
    return PlanGraph(
        nodes={
            "create_script": PlanGraphNode(
                id="create_script",
                intent="Create C# script component",
                execution_ref="gh_create_csharp_script:v1",
                verifier_ref="script_receipt_has_artifact_or_errors:v1",
                repair_policy_ref="repair_same_component_once:v1",
            ),
            "repair_same_component": PlanGraphNode(
                id="repair_same_component",
                intent="Repair the same component in place",
                execution_ref="gh_update_script:v1",
                repair_policy_ref="repair_same_component_once:v1",
                is_terminal=True,
            ),
        },
        edges=[
            PlanGraphEdge(
                source="create_script",
                target="repair_same_component",
                kind="on_repair",
            ),
        ],
    )


DEFAULT_REGISTRY: tuple[TemplateEntry, ...] = (
    _make_entry(
        "gh_csharp_create_repair",
        {
            "domain": "grasshopper",
            "operation": "create_repair",
            "language": "csharp",
        },
        _build_gh_csharp_create_repair,
        bindings=(
            BindingSpec("goal", "memory_fact", "goal"),
            BindingSpec(
                "component_name",
                "node_metadata",
                "component_name",
                node_id="create_script",
            ),
        ),
    ),
)


def select_template(
    descriptor: Mapping[str, str],
    registry: tuple[TemplateEntry, ...] = DEFAULT_REGISTRY,
) -> TemplateSelection:
    """Select the one template whose criteria the descriptor fully satisfies.

    Deterministic exact match: a template matches iff every declared criterion
    equals the descriptor's value for that field. Exactly one match returns a
    fresh deep copy of that template's graph; zero or many returns no graph plus
    an explicit finding. Always returns the full per-template evaluation trail.
    """
    evaluations = tuple(_evaluate(entry, descriptor) for entry in registry)
    matched_ids = sorted(ev.template_id for ev in evaluations if ev.matched)

    if len(matched_ids) == 1:
        selected_id = matched_ids[0]
        entry = next(e for e in registry if e.template_id == selected_id)
        return TemplateSelection(
            selected_template_id=selected_id,
            graph=copy.deepcopy(entry.build_graph()),
            evaluations=evaluations,
            findings=(
                _finding(
                    "template_selected",
                    f"Selected template '{selected_id}'.",
                    (selected_id,),
                ),
            ),
        )

    if not matched_ids:
        return TemplateSelection(
            selected_template_id=None,
            graph=None,
            evaluations=evaluations,
            findings=(
                _finding(
                    "no_matching_template",
                    "No registered template matched the intent descriptor.",
                    (),
                ),
            ),
        )

    return TemplateSelection(
        selected_template_id=None,
        graph=None,
        evaluations=evaluations,
        findings=(
            _finding(
                "ambiguous_template",
                "Intent descriptor matched multiple templates: "
                + ", ".join(matched_ids)
                + ".",
                tuple(matched_ids),
            ),
        ),
    )


def bind_parameters(
    graph: PlanGraph,
    bindings: tuple[BindingSpec, ...],
    descriptor: Mapping[str, object],
) -> BindingResult:
    """Apply declared bindings to a fresh copy of ``graph``.

    Writes only node metadata and graph memory facts. Each bound value is
    deep-copied. Findings are emitted only on error; any error nulls the returned
    graph (no partially-bound graph leaks). Never mutates the input graph.
    """
    working = copy.deepcopy(graph)
    findings: list[BindingFinding] = []

    for spec in bindings:
        if spec.descriptor_field not in descriptor:
            if spec.required:
                findings.append(
                    _binding_finding(
                        "missing_required_binding",
                        spec.descriptor_field,
                        f"Required binding field '{spec.descriptor_field}' is "
                        "absent from the descriptor.",
                    )
                )
            continue

        try:
            value = copy.deepcopy(descriptor[spec.descriptor_field])
        except Exception:
            findings.append(
                _binding_finding(
                    "binding_value_copy_failed",
                    spec.descriptor_field,
                    f"Could not copy the value for binding field "
                    f"'{spec.descriptor_field}'.",
                )
            )
            continue

        if spec.target == "memory_fact":
            working.memory.facts[spec.key] = value
        else:  # "node_metadata"
            if spec.node_id is None or spec.node_id not in working.nodes:
                findings.append(
                    _binding_finding(
                        "unknown_binding_target",
                        spec.descriptor_field,
                        f"Binding target node '{spec.node_id}' is not present "
                        "in the graph.",
                    )
                )
                continue
            working.nodes[spec.node_id].metadata[spec.key] = value

    if any(f.severity == "error" for f in findings):
        return BindingResult(graph=None, findings=tuple(findings))
    return BindingResult(graph=working, findings=tuple(findings))


def select_and_bind(
    descriptor: Mapping[str, str],
    registry: tuple[TemplateEntry, ...] = DEFAULT_REGISTRY,
) -> SelectAndBindResult:
    """Select a template, then bind its declared parameters from the descriptor.

    Selection and binding stay separate: ``selection.graph`` is the unbound
    selected copy; the bound graph is ``binding.graph``. ``binding`` is None when
    nothing was selected.
    """
    selection = select_template(descriptor, registry)
    if selection.graph is None:
        return SelectAndBindResult(selection=selection, binding=None)
    entry = next(
        e for e in registry if e.template_id == selection.selected_template_id
    )
    binding = bind_parameters(selection.graph, entry.bindings, descriptor)
    return SelectAndBindResult(selection=selection, binding=binding)
