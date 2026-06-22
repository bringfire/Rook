# LM3B PlanGraph Template Selector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a pure, deterministic `select_template` that maps a structured intent descriptor to a registered hand-authored `PlanGraph` template via exact criteria satisfaction, returning a fresh deep copy of that template plus an auditable selection record.

**Architecture:** One new import-light module `plan_graph_templates.py`: frozen record dataclasses (`TemplateEntry`, `CriterionCheck`, `TemplateEvaluation`, `TemplateFinding`, `TemplateSelection`), a `_SEVERITY_BY_CODE` table, a `_make_entry` helper (immutable sorted criteria), a graph-factory registry `DEFAULT_REGISTRY` holding one entry (the bridge-drivable GH C# create-repair loop), and `select_template`. Birth is independent of drive: production code imports only `plan_graph`.

**Tech Stack:** Python 3.12, pytest. Stdlib only inside the module (`copy`, `collections.abc`, `dataclasses`, `typing`) plus `rook.learning.plan_graph`.

## Global Constraints

- **Selection only — no binding.** Never mutate node ids/edges/refs/metadata/memory/retry. Return a fresh deep copy of the template. Parameter binding is deferred to LM3C.
- **Deterministic router.** Exact criteria satisfaction: a template matches iff EVERY declared criterion equals the descriptor's value for that field. No scoring, no ranking, no fallback. Exactly one match → selected; zero → `no_matching_template` (error); two-plus → `ambiguous_template` (error, no tiebreak).
- **Per-criterion rejection distinguishes** `missing_field` (field absent from descriptor) from `value_mismatch` (present but unequal).
- **Findings** (single-source `_SEVERITY_BY_CODE`): `template_selected`=info, `no_matching_template`=error, `ambiguous_template`=error.
- **Registry holds graph FACTORIES, not stored graph instances.** `TemplateEntry.build_graph: Callable[[], PlanGraph]`; criteria stored as immutable sorted tuples. No long-lived mutable graph anywhere.
- **Descriptor** is `Mapping[str, str]` (structured, not free text). `registry` is a defaulted param; `DEFAULT_REGISTRY` is a public module constant.
- **Birth independent of drive (import boundary).** The production module imports ONLY `rook.learning.plan_graph` among rook modules (+ stdlib). It must NOT import `plan_graph_bridge`, `plan_graph_walker`, `rook.agent.planner`, `rook.agent.tool_dispatcher`, `rook.server`, `dspy`, or `litellm`. Proven by an AST allowlist test AND a subprocess probe. The walker is imported ONLY inside the composition-proof test.
- **No model calls, no live tools, no `planner.py`.**
- Test commands run from repo root (`C:\UDEV\Rook`) with the repo venv: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider ...`.

## File Structure

- `mcp_server/src/rook/learning/plan_graph_templates.py` (new) — selector + registry + record types + the one template factory.
- `mcp_server/tests/test_plan_graph_templates.py` (new) — full behavior + composition + purity suite.

---

### Task 1: `select_template` deterministic template selector

**Files:**
- Create: `mcp_server/src/rook/learning/plan_graph_templates.py`
- Create: `mcp_server/tests/test_plan_graph_templates.py`

**Interfaces:**
- Consumes (from `rook.learning.plan_graph`): `PlanGraph`, `PlanGraphNode`, `PlanGraphEdge`. (PlanGraphNode is a NON-frozen dataclass; `node.status` default is `"pending"`; `PlanGraph.edges` is a list.)
- Consumes in the composition TEST ONLY (from `rook.learning.plan_graph_walker`): `walk_plan_graph(graph, steps) -> WalkReport` with `.final_graph_status` and `.halted`.
- Produces: `TemplateEntry`, `CriterionCheck`, `TemplateEvaluation`, `TemplateFinding`, `TemplateSelection`, `DEFAULT_REGISTRY`, and `select_template(descriptor: Mapping[str, str], registry: tuple[TemplateEntry, ...] = DEFAULT_REGISTRY) -> TemplateSelection`.

- [ ] **Step 1: Write the failing tests**

Create `mcp_server/tests/test_plan_graph_templates.py`:

```python
from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

from rook.learning.plan_graph import PlanGraph, PlanGraphNode
from rook.learning.plan_graph_templates import (
    TemplateEntry,
    select_template,
)


_DESCRIPTOR = {
    "domain": "grasshopper",
    "operation": "create_repair",
    "language": "csharp",
}

COMPONENT_GUID = "fbfd3ba5-5951-4064-8478-ee1d173150a9"


def _create_result() -> dict:
    return {
        "success": False,
        "message": "Component created with compile errors.",
        "data": {
            "script_receipt": {
                "version": 1,
                "operation": "create",
                "language": "csharp",
                "artifact_status": "created_with_errors",
                "mutation": {"status": "created", "component_guid": COMPONENT_GUID},
                "verification": {"status": "failed", "target_error_count": 1},
                "repair_anchor": {"component_guid": COMPONENT_GUID, "language": "csharp"},
            }
        },
    }


def _update_result() -> dict:
    return {
        "success": True,
        "message": "Script updated; component is usable.",
        "data": {
            "script_receipt": {
                "version": 1,
                "operation": "update",
                "language": "csharp",
                "artifact_status": "usable",
                "mutation": {"status": "written", "component_guid": COMPONENT_GUID},
                "verification": {"status": "passed", "target_error_count": 0},
                "repair_anchor": {"component_guid": COMPONENT_GUID, "language": "csharp"},
            }
        },
    }


def test_single_exact_match_selects_template():
    selection = select_template(_DESCRIPTOR)

    assert selection.selected_template_id == "gh_csharp_create_repair"
    assert selection.graph is not None
    assert "create_script" in selection.graph.nodes
    assert [f.code for f in selection.findings] == ["template_selected"]
    assert selection.findings[0].severity == "info"
    assert selection.findings[0].template_ids == ("gh_csharp_create_repair",)

    evaluation = next(
        e for e in selection.evaluations if e.template_id == "gh_csharp_create_repair"
    )
    assert evaluation.matched is True
    assert all(c.outcome == "accepted" for c in evaluation.criteria)


def test_two_selections_are_independent_and_do_not_corrupt_registry():
    first = select_template(_DESCRIPTOR)
    second = select_template(_DESCRIPTOR)

    # mutate the first selection's graph structure
    first.graph.nodes["create_script"].status = "succeeded"
    first.graph.nodes["create_script"].intent = "MUTATED"
    first.graph.nodes["injected"] = PlanGraphNode(id="injected", intent="X")
    first.graph.edges.clear()

    # second selection is pristine
    assert second.graph.nodes["create_script"].status == "pending"
    assert second.graph.nodes["create_script"].intent == "Create C# script component"
    assert "injected" not in second.graph.nodes
    assert len(second.graph.edges) == 1

    # a fresh selection is also pristine (registry source uncorrupted)
    third = select_template(_DESCRIPTOR)
    assert third.graph.nodes["create_script"].status == "pending"
    assert "injected" not in third.graph.nodes
    assert len(third.graph.edges) == 1


def test_value_mismatch_yields_no_matching_template():
    descriptor = {**_DESCRIPTOR, "language": "python"}
    selection = select_template(descriptor)

    assert selection.selected_template_id is None
    assert selection.graph is None
    assert [f.code for f in selection.findings] == ["no_matching_template"]
    assert selection.findings[0].severity == "error"

    evaluation = selection.evaluations[0]
    lang_check = next(c for c in evaluation.criteria if c.field == "language")
    assert lang_check.outcome == "value_mismatch"
    assert lang_check.actual == "python"
    assert lang_check.expected == "csharp"


def test_missing_field_is_distinct_from_value_mismatch():
    descriptor = {"domain": "grasshopper", "operation": "create_repair"}  # no language
    selection = select_template(descriptor)

    assert selection.graph is None
    assert selection.findings[0].code == "no_matching_template"

    evaluation = selection.evaluations[0]
    lang_check = next(c for c in evaluation.criteria if c.field == "language")
    assert lang_check.outcome == "missing_field"
    assert lang_check.actual is None


def test_ambiguous_intent_matches_multiple_templates():
    crit = (("kind", "x"),)
    registry = (
        TemplateEntry(
            "alpha",
            crit,
            lambda: PlanGraph(nodes={"a": PlanGraphNode(id="a", intent="A")}),
        ),
        TemplateEntry(
            "beta",
            crit,
            lambda: PlanGraph(nodes={"b": PlanGraphNode(id="b", intent="B")}),
        ),
    )
    selection = select_template({"kind": "x"}, registry=registry)

    assert selection.selected_template_id is None
    assert selection.graph is None
    assert [f.code for f in selection.findings] == ["ambiguous_template"]
    assert selection.findings[0].severity == "error"
    assert selection.findings[0].template_ids == ("alpha", "beta")


def test_selected_template_drives_to_complete_through_walker():
    from rook.learning.plan_graph_walker import walk_plan_graph

    selection = select_template(_DESCRIPTOR)
    report = walk_plan_graph(
        selection.graph,
        [
            ("create_script", _create_result()),
            ("repair_same_component", _update_result()),
        ],
    )

    assert report.final_graph_status == "complete"
    assert report.halted is False


def test_evaluations_are_deterministic():
    a = select_template(_DESCRIPTOR)
    b = select_template(_DESCRIPTOR)

    assert [e.template_id for e in a.evaluations] == [e.template_id for e in b.evaluations]
    fields_a = [c.field for c in a.evaluations[0].criteria]
    fields_b = [c.field for c in b.evaluations[0].criteria]
    assert fields_a == fields_b
    assert fields_a == sorted(fields_a)  # criteria normalized to sorted order


def _direct_import_modules(path: str) -> set[str]:
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            prefix = "." * node.level
            modules.add(f"{prefix}{node.module or ''}")
    return modules


def test_templates_module_imports_only_plan_graph_among_rook():
    imports = _direct_import_modules(
        "mcp_server/src/rook/learning/plan_graph_templates.py"
    )
    assert "rook.learning.plan_graph" in imports
    assert "rook.learning.plan_graph_bridge" not in imports
    assert "rook.learning.plan_graph_walker" not in imports
    assert "rook.agent.planner" not in imports
    assert "rook.agent.tool_dispatcher" not in imports
    assert "rook.server" not in imports
    rook_or_relative = {
        m for m in imports if m.startswith("rook.") or m.startswith(".")
    }
    assert rook_or_relative == {"rook.learning.plan_graph"}


def test_importing_templates_does_not_load_drive_or_heavy_modules():
    env = os.environ.copy()
    src_path = str(Path("mcp_server/src").resolve())
    env["PYTHONPATH"] = (
        src_path
        if not env.get("PYTHONPATH")
        else f"{src_path}{os.pathsep}{env['PYTHONPATH']}"
    )

    probe = (
        "import sys\n"
        "import rook.learning.plan_graph_templates\n"
        "for mod in (\n"
        "    'rook.learning.plan_graph_walker',\n"
        "    'rook.learning.plan_graph_bridge',\n"
        "    'rook.agent.planner',\n"
        "    'rook.agent.tool_dispatcher',\n"
        "    'dspy',\n"
        "    'litellm',\n"
        "):\n"
        "    if mod in sys.modules:\n"
        "        raise SystemExit(mod + ' loaded')\n"
    )

    subprocess.run(
        [sys.executable, "-c", probe],
        check=True,
        env=env,
    )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_plan_graph_templates.py -v`
Expected: collection/import error — `ModuleNotFoundError: No module named 'rook.learning.plan_graph_templates'`.

- [ ] **Step 3: Implement the selector module**

Create `mcp_server/src/rook/learning/plan_graph_templates.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_plan_graph_templates.py -v`
Expected: all 9 PASS.

- [ ] **Step 5: Regression — PlanGraph suites + py_compile**

Run:
```
mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_plan_graph_templates.py mcp_server/tests/test_plan_graph.py mcp_server/tests/test_plan_graph_outcomes.py mcp_server/tests/test_plan_graph_bridge.py mcp_server/tests/test_plan_graph_walker.py -v
mcp_server/.venv/Scripts/python.exe -m py_compile mcp_server/src/rook/learning/plan_graph_templates.py
```
Expected: all PASS; py_compile silent. (The selector adds no behavior to the other PlanGraph modules, so their suites must stay green.)

- [ ] **Step 6: Commit**

```bash
git add mcp_server/src/rook/learning/plan_graph_templates.py mcp_server/tests/test_plan_graph_templates.py
git commit -m "feat(lm3b): deterministic PlanGraph template selector (birth seam)"
```

---

## Post-implementation (controller, not a task)

After Task 1 + the final whole-branch review:
- Open a PR `codex/lm3b-plan-graph-template-selector` → `main`. **Stop before merge — explicit human approval required (no self-merge).**
- Final reviewer EXTRA instructions:
  - (a) Selection only — `select_template` never mutates the template (no node/edge/ref/metadata/memory/retry changes); it returns `copy.deepcopy(entry.build_graph())`.
  - (b) Deterministic exact match — no scoring/ranking/fallback; zero→`no_matching_template`, many→`ambiguous_template` (no tiebreak); `missing_field` vs `value_mismatch` distinct.
  - (c) Registry holds graph factories (no stored mutable graph); criteria are immutable sorted tuples; `DEFAULT_REGISTRY` is a tuple (safe as a default arg).
  - (d) Import boundary — production module imports ONLY `rook.learning.plan_graph` among rook modules; the AST allowlist test AND subprocess probe confirm no `plan_graph_walker`/`plan_graph_bridge`/`planner`/`tool_dispatcher`/`rook.server`/`dspy`/`litellm` load. The walker import lives only in the composition test.
  - (e) No binding (deferred to LM3C); no `planner.py` coupling.
- Note for the reviewer/PR body: the registered template is the **2-node `on_repair`** create-repair loop, NOT a 5-node verifier-mediated shape — the latter is not bridge-drivable to `complete` (the adapter collapses `created_with_errors`→`needs_repair` at the create node, so a `requires` edge to a verifier never unlocks). The spec was corrected on-branch to the bridge-drivable shape, which is the path LM3A proved end-to-end.
- No deployed-runtime verification needed (pure learning-layer module; no wire/surface/runtime impact).
