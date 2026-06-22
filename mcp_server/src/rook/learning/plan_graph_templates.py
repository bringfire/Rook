"""LM3B PlanGraph birth seam — deterministic template selector.

A pure router that maps a small *structured* intent descriptor to a registered,
hand-authored ``PlanGraph`` template and returns a fresh copy of that template
plus an auditable selection record.

It proves graph birth, not graph binding: it never builds a bespoke plan, infers
from free text, scores/ranks, falls back, calls a model or live tool, or couples
to ``planner.py``. A template matches iff EVERY declared criterion equals the
descriptor's value for that field. Parameter binding is deferred to LM3C.

Production code here depends only on ``rook.learning.plan_graph`` (to build the
template). Drive-side modules (``plan_graph_walker`` / ``plan_graph_bridge``) are
NOT imported — birth is independent of drive.
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


@dataclass(frozen=True)
class TemplateEntry:
    template_id: str
    criteria: tuple[tuple[str, str], ...]
    build_graph: Callable[[], PlanGraph]


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


def _make_entry(
    template_id: str,
    criteria: Mapping[str, str],
    build_graph: Callable[[], PlanGraph],
) -> TemplateEntry:
    return TemplateEntry(
        template_id=template_id,
        criteria=tuple(sorted(criteria.items())),
        build_graph=build_graph,
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
