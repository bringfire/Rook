# LM3C PlanGraph Parameter Binding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a pure `bind_parameters` primitive and a thin `select_and_bind` composer that inject declared descriptor values into a selected template's node metadata / graph memory facts (never structure), with deep-copied values and error-only findings.

**Architecture:** Extend the merged `plan_graph_templates.py` beside the LM3B selector. `select_template` stays selection-only (its `TemplateEntry`/`_make_entry` gain a defaulted `bindings`). New `bind_parameters(graph, bindings, descriptor)` is registry-agnostic and pure; `select_and_bind` composes select + bind, keeping the unbound selected graph and the bound graph separate.

**Tech Stack:** Python 3.12, pytest. Stdlib only inside the module (`copy`, `collections.abc`, `dataclasses`, `typing`) plus `rook.learning.plan_graph` — unchanged from LM3B (no new imports).

## Global Constraints

- **Binding writes ONLY** `node.metadata[key]` and `graph.memory.facts[key]`. Forbidden: node ids, edges, `execution_ref`/`verifier_ref`/`repair_policy_ref`, retry, status, any structural change.
- **Values copied, never interpreted.** Each bound value is `copy.deepcopy`-ed before storage; if deepcopy raises → `binding_value_copy_failed` (error) + `graph=None`.
- **Findings only on error.** Optional-missing and successful bindings emit nothing. Error codes (single-source `_BINDING_SEVERITY_BY_CODE`, all `error`): `missing_required_binding`, `unknown_binding_target`, `binding_value_copy_failed`.
- **Any error nulls the graph — no partially-bound graph leaks** (watchpoint 1). All errors collected, not first-only.
- **`select_and_bind` keeps `selection.graph` UNBOUND** even on successful binding (watchpoint 2); only `binding.graph` carries bound values.
- **`bind_parameters` never mutates its input graph** (operates on a deep copy).
- **`bind_parameters` descriptor is `Mapping[str, object]`** (robust to any value type); `select_template`/`select_and_bind` keep `Mapping[str, str]`.
- **Import-light unchanged:** module imports only `rook.learning.plan_graph` among rook modules (+ stdlib). The existing AST allowlist test and subprocess probe regress-guard this (no new imports added).
- **Governing invariant:** a bound graph must still be drivable to `complete` by `walk_plan_graph` + `apply_tool_result`.
- Test commands run from repo root (`C:\UDEV\Rook`) with the repo venv: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider ...`.

## File Structure

- `mcp_server/src/rook/learning/plan_graph_templates.py` (modify) — add binding types/helpers/functions; extend `TemplateEntry`/`_make_entry`/`DEFAULT_REGISTRY`.
- `mcp_server/tests/test_plan_graph_templates.py` (modify) — add LM3C tests; extend the import line.

---

### Task 1: `bind_parameters` + `select_and_bind`

**Files:**
- Modify: `mcp_server/src/rook/learning/plan_graph_templates.py`
- Modify: `mcp_server/tests/test_plan_graph_templates.py`

**Interfaces:**
- Consumes (existing in module): `TemplateEntry`, `TemplateSelection`, `select_template`, `DEFAULT_REGISTRY`, `_make_entry`, `PlanGraph`, `PlanGraphNode`.
- Consumes in TEST ONLY: `rook.learning.plan_graph_walker.walk_plan_graph`.
- Produces: `BindingSpec`, `BindingFinding`, `BindingResult`, `SelectAndBindResult`, `bind_parameters(graph: PlanGraph, bindings: tuple[BindingSpec, ...], descriptor: Mapping[str, object]) -> BindingResult`, `select_and_bind(descriptor: Mapping[str, str], registry: tuple[TemplateEntry, ...] = DEFAULT_REGISTRY) -> SelectAndBindResult`; `TemplateEntry.bindings: tuple[BindingSpec, ...] = ()`.

- [ ] **Step 1: Add the failing LM3C tests**

In `mcp_server/tests/test_plan_graph_templates.py`, replace the existing import block:

```python
from rook.learning.plan_graph_templates import (
    TemplateEntry,
    select_template,
)
```

with:

```python
from rook.learning.plan_graph_templates import (
    BindingSpec,
    TemplateEntry,
    bind_parameters,
    select_and_bind,
    select_template,
)
```

Then append these tests to the end of the file:

```python
def _bindable_graph() -> PlanGraph:
    return PlanGraph(
        nodes={"create_script": PlanGraphNode(id="create_script", intent="Create")}
    )


def test_bind_parameters_writes_memory_fact_and_node_metadata():
    graph = _bindable_graph()
    bindings = (
        BindingSpec("goal", "memory_fact", "goal"),
        BindingSpec(
            "component_name", "node_metadata", "component_name", node_id="create_script"
        ),
    )

    result = bind_parameters(
        graph, bindings, {"goal": "make a box", "component_name": "BoxMaker"}
    )

    assert result.findings == ()
    assert result.graph is not None
    assert result.graph.memory.facts["goal"] == "make a box"
    assert result.graph.nodes["create_script"].metadata["component_name"] == "BoxMaker"
    # input graph unmutated
    assert graph.memory.facts == {}
    assert graph.nodes["create_script"].metadata == {}


def test_bind_parameters_applies_all_bindings_in_order():
    graph = _bindable_graph()
    bindings = (
        BindingSpec("a", "memory_fact", "a"),
        BindingSpec("b", "memory_fact", "b"),
    )

    result = bind_parameters(graph, bindings, {"a": "1", "b": "2"})

    assert result.findings == ()
    assert result.graph.memory.facts == {"a": "1", "b": "2"}


def test_bind_parameters_required_missing_returns_none_with_error():
    graph = _bindable_graph()
    bindings = (
        BindingSpec(
            "component_name",
            "node_metadata",
            "component_name",
            node_id="create_script",
            required=True,
        ),
    )

    result = bind_parameters(graph, bindings, {})

    assert result.graph is None
    assert [f.code for f in result.findings] == ["missing_required_binding"]
    assert result.findings[0].severity == "error"
    assert result.findings[0].field == "component_name"


def test_bind_parameters_optional_missing_skips_silently():
    graph = _bindable_graph()
    bindings = (BindingSpec("goal", "memory_fact", "goal"),)

    result = bind_parameters(graph, bindings, {})

    assert result.findings == ()
    assert result.graph is not None
    assert "goal" not in result.graph.memory.facts


def test_bind_parameters_unknown_node_target_returns_none_with_error():
    graph = _bindable_graph()
    bindings = (BindingSpec("x", "node_metadata", "x", node_id="does_not_exist"),)

    result = bind_parameters(graph, bindings, {"x": "v"})

    assert result.graph is None
    assert [f.code for f in result.findings] == ["unknown_binding_target"]


def test_bind_parameters_node_metadata_without_node_id_returns_none_with_error():
    graph = _bindable_graph()
    bindings = (BindingSpec("x", "node_metadata", "x", node_id=None),)

    result = bind_parameters(graph, bindings, {"x": "v"})

    assert result.graph is None
    assert [f.code for f in result.findings] == ["unknown_binding_target"]


def test_bind_parameters_deepcopies_mutable_value():
    graph = _bindable_graph()
    payload = {"nested": ["a"]}
    bindings = (BindingSpec("cfg", "memory_fact", "cfg"),)

    result = bind_parameters(graph, bindings, {"cfg": payload})

    # mutate the descriptor value AFTER binding
    payload["nested"].append("b")
    payload["added"] = True

    assert result.graph.memory.facts["cfg"] == {"nested": ["a"]}


def test_bind_parameters_copy_failure_returns_none_with_error():
    class _Uncopyable:
        def __deepcopy__(self, memo):
            raise RuntimeError("nope")

    graph = _bindable_graph()
    bindings = (BindingSpec("cfg", "memory_fact", "cfg"),)

    result = bind_parameters(graph, bindings, {"cfg": _Uncopyable()})

    assert result.graph is None
    assert [f.code for f in result.findings] == ["binding_value_copy_failed"]


def test_bind_parameters_later_failure_discards_earlier_success():
    # Watchpoint 1: a later failure must null the graph; no partial bind leaks.
    graph = _bindable_graph()
    bindings = (
        BindingSpec("goal", "memory_fact", "goal"),  # would succeed
        BindingSpec("missing", "memory_fact", "missing", required=True),  # fails
    )

    result = bind_parameters(graph, bindings, {"goal": "g"})

    assert result.graph is None
    assert [f.code for f in result.findings] == ["missing_required_binding"]


def test_bind_parameters_reports_all_errors():
    graph = _bindable_graph()
    bindings = (
        BindingSpec("a", "node_metadata", "a", node_id="nope"),  # unknown target
        BindingSpec("b", "memory_fact", "b", required=True),  # required missing
    )

    result = bind_parameters(graph, bindings, {"a": "v"})

    assert result.graph is None
    assert sorted(f.code for f in result.findings) == [
        "missing_required_binding",
        "unknown_binding_target",
    ]


def test_select_and_bind_binds_only_binding_graph():
    descriptor = {**_DESCRIPTOR, "component_name": "BoxMaker", "goal": "make a box"}

    result = select_and_bind(descriptor)

    assert result.binding is not None
    assert result.binding.graph is not None
    assert (
        result.binding.graph.nodes["create_script"].metadata["component_name"]
        == "BoxMaker"
    )
    assert result.binding.graph.memory.facts["goal"] == "make a box"
    # Watchpoint 2: selection.graph stays UNBOUND
    assert (
        "component_name"
        not in result.selection.graph.nodes["create_script"].metadata
    )
    assert "goal" not in result.selection.graph.memory.facts
    # findings streams separate
    assert [f.code for f in result.selection.findings] == ["template_selected"]
    assert result.binding.findings == ()


def test_select_and_bind_no_match_has_no_binding():
    result = select_and_bind({**_DESCRIPTOR, "language": "python"})

    assert result.binding is None
    assert [f.code for f in result.selection.findings] == ["no_matching_template"]


def test_bound_default_template_drives_to_complete_through_walker():
    from rook.learning.plan_graph_walker import walk_plan_graph

    descriptor = {**_DESCRIPTOR, "component_name": "BoxMaker"}
    result = select_and_bind(descriptor)
    graph = result.binding.graph
    assert graph.nodes["create_script"].metadata["component_name"] == "BoxMaker"

    report = walk_plan_graph(
        graph,
        [
            ("create_script", _create_result()),
            ("repair_same_component", _update_result()),
        ],
    )

    assert report.final_graph_status == "complete"
    assert report.halted is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_plan_graph_templates.py -v`
Expected: collection/import error — `ImportError: cannot import name 'BindingSpec' from 'rook.learning.plan_graph_templates'` (the binding API does not exist yet).

- [ ] **Step 3: Implement the binding API (surgical edits to `plan_graph_templates.py`)**

**Edit 3a — replace the module docstring** (the current lines 1-15, from `"""LM3B...` through the closing `"""`):

```python
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
```

**Edit 3b — add the binding severity table** immediately after the `_SEVERITY_BY_CODE` dict (after its closing `}`):

```python
_BINDING_SEVERITY_BY_CODE: dict[str, Literal["info", "warning", "error"]] = {
    "missing_required_binding": "error",
    "unknown_binding_target": "error",
    "binding_value_copy_failed": "error",
}
```

**Edit 3c — define `BindingSpec` immediately BEFORE `TemplateEntry`** (it is referenced by `TemplateEntry`'s new field; the module has no `from __future__ import annotations`, so it must be defined first):

```python
@dataclass(frozen=True)
class BindingSpec:
    descriptor_field: str
    target: Literal["memory_fact", "node_metadata"]
    key: str
    node_id: str | None = None
    required: bool = False
```

**Edit 3d — replace the `TemplateEntry` class** to add the `bindings` field:

```python
@dataclass(frozen=True)
class TemplateEntry:
    template_id: str
    criteria: tuple[tuple[str, str], ...]
    build_graph: Callable[[], PlanGraph]
    bindings: tuple[BindingSpec, ...] = ()
```

**Edit 3e — add the binding result types** immediately after the `TemplateSelection` class:

```python
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
```

**Edit 3f — replace `_make_entry`** to thread `bindings`:

```python
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
```

**Edit 3g — add the `_binding_finding` helper** immediately after the existing `_finding` function:

```python
def _binding_finding(code: str, field: str, message: str) -> BindingFinding:
    return BindingFinding(
        code=code,
        severity=_BINDING_SEVERITY_BY_CODE[code],
        field=field,
        message=message,
    )
```

**Edit 3h — replace the `DEFAULT_REGISTRY` definition** to declare the template's bindings:

```python
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
```

**Edit 3i — append `bind_parameters` and `select_and_bind`** at the end of the file (after `select_template`):

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_plan_graph_templates.py -v`
Expected: all PASS (9 existing LM3B + 13 new LM3C = 22).

- [ ] **Step 5: Regression — PlanGraph suites + py_compile**

Run:
```
mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_plan_graph_templates.py mcp_server/tests/test_plan_graph.py mcp_server/tests/test_plan_graph_outcomes.py mcp_server/tests/test_plan_graph_bridge.py mcp_server/tests/test_plan_graph_walker.py -v
mcp_server/.venv/Scripts/python.exe -m py_compile mcp_server/src/rook/learning/plan_graph_templates.py
```
Expected: all PASS; py_compile silent. The existing LM3B purity tests (`test_templates_module_imports_only_plan_graph_among_rook`, `test_importing_templates_does_not_load_drive_or_heavy_modules`) must stay green — LM3C adds no imports, so they regress-guard the import boundary.

- [ ] **Step 6: Commit**

```bash
git add mcp_server/src/rook/learning/plan_graph_templates.py mcp_server/tests/test_plan_graph_templates.py
git commit -m "feat(lm3c): PlanGraph parameter binding (descriptor -> metadata/memory)"
```

---

## Post-implementation (controller, not a task)

After Task 1 + the final whole-branch review:
- Open a PR `codex/lm3c-plan-graph-param-binding` → `main`. **Stop before merge — explicit human approval required (no self-merge).**
- Final reviewer EXTRA instructions:
  - (a) Binding writes ONLY node metadata / memory facts — never ids/edges/`*_ref`/status/retry/structure.
  - (b) `bind_parameters` deep-copies the input graph (never mutates it) AND deep-copies each bound value; a `__deepcopy__` failure → `binding_value_copy_failed` + `graph=None`.
  - (c) **Watchpoint 1:** any error (required-missing / unknown-target / copy-failure), even after an earlier successful bind, returns `graph=None` — no partially-bound graph leaks. All errors collected.
  - (d) **Watchpoint 2:** `select_and_bind` leaves `selection.graph` UNBOUND on success; only `binding.graph` carries bound values; selection vs binding findings stay in separate streams.
  - (e) Findings only on error; optional-missing and success emit none. `select_template` selection behavior is unchanged (LM3B tests still green).
  - (f) Import boundary unchanged — module still imports only `rook.learning.plan_graph` among rook modules; existing AST + subprocess probes still pass.
  - (g) Governing invariant — the bound default-template graph reaches `complete` through `walk_plan_graph` + `apply_tool_result`.
- No deployed-runtime verification needed (pure learning-layer module; no wire/surface/runtime impact).
