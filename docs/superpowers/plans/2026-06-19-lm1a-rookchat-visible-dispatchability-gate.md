# LM1A RookChat Visible Dispatchability Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic non-live gate proving that every model-visible tool in required RookChat local execution-profile surfaces has a structural internal dispatch path or a named intercept/exclusion.

**Architecture:** Add a plain-data dispatchability audit helper to the existing RookChat tool-contract policy module. Cover real active schema sets with deterministic fallback and synthetic cached catalogs, then remove currently non-dispatchable names from local RookChat visibility surfaces instead of hiding them with broad exceptions.

**Tech Stack:** Python 3, pytest, RookChat `ToolRegistry`, `ChatRunner` catalog builders, `ToolDispatcher` dispatch tables.

---

## File Structure

- Modify `mcp_server/src/rook/agent/chat/tool_contracts.py`
  - Add `DispatchContext`, `DispatchabilityFinding`, `classify_visible_tool()`, and `audit_visible_tool_dispatchability()`.
  - Keep the helper structural-only: no `ChatRunner`, no `ToolDispatcher.dispatch()`, no `call_rhino()`, no MCP calls.

- Modify `mcp_server/src/rook/agent/tool_groups.py`
  - Remove non-dispatchable server/MCP-only names from local initial surfaces.
  - Remove non-dispatchable server/MCP-only canvas names from the local `gh_canvas` group.
  - Do not touch public MCP `server.py` tool exposure.
  - Do not audit or edit `gh_canvas_readonly` in this slice.

- Create `mcp_server/tests/test_rookchat_visible_dispatchability.py`
  - Unit-test audit helper findings.
  - Test deterministic fallback/local active surfaces.
  - Test synthetic cached-catalog active surfaces for default, `gh_canvas`, and readonly initial profiles.

---

## Task 1: Add Failing Dispatchability Tests

**Files:**
- Create: `mcp_server/tests/test_rookchat_visible_dispatchability.py`

- [ ] **Step 1: Write the failing test file**

Create `mcp_server/tests/test_rookchat_visible_dispatchability.py` with this content:

```python
from __future__ import annotations

from typing import Iterable

from rook.agent.chat.chat_runner import (
    _CHAT_MODEL_TOOL_SCHEMAS,
    _build_fallback_catalog,
    _build_local_tool_catalog,
)
from rook.agent.chat.tool_contracts import (
    DispatchContext,
    audit_visible_tool_dispatchability,
    normalize_litellm_tool_schema,
)
from rook.agent.tool_dispatcher import (
    BRIDGE_ROUTES,
    STRICT_NO_ARGUMENT_BRIDGE_TOOLS,
    TRANSFORM_FUNCTIONS,
    build_local_tools,
)
from rook.agent.tool_groups import AGENT_TIER_0, READONLY_TIER_0, TOOL_GROUPS
from rook.agent.tool_registry import ToolRegistry


CHAT_MODEL_TIER0 = frozenset({"list_chat_models", "set_chat_model"})
CHATRUNNER_INTERCEPTED = frozenset({
    "request_tools",
    "search_tools",
    "ui_block",
    "list_chat_models",
    "set_chat_model",
})
GH_CANVAS_SENTINELS = frozenset({
    "gh_create_script",
    "gh_create_csharp_script",
    "gh_update_script",
    "gh_set_script",
    "gh_inspect_output",
})


def _stub_schema(name: str) -> dict:
    return normalize_litellm_tool_schema({
        "type": "function",
        "function": {
            "name": name,
            "description": f"Synthetic cached schema for {name}",
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
    })


def _fallback_local_catalog(extra_names: Iterable[str] = ()) -> dict[str, dict]:
    catalog = _build_fallback_catalog()
    catalog.update(_build_local_tool_catalog(build_local_tools()))
    catalog.update(_CHAT_MODEL_TOOL_SCHEMAS)
    for name in extra_names:
        catalog.setdefault(name, _stub_schema(name))
    return catalog


def _dispatch_context() -> DispatchContext:
    return DispatchContext(
        intercepted_names=CHATRUNNER_INTERCEPTED,
        local_tool_names=frozenset(build_local_tools().keys()),
        transform_names=frozenset(TRANSFORM_FUNCTIONS.keys()),
        bridge_names=frozenset(BRIDGE_ROUTES.keys()),
        excluded_names=frozenset(),
        strict_no_argument_names=STRICT_NO_ARGUMENT_BRIDGE_TOOLS,
    )


def _registry(catalog: dict[str, dict], tier0: set[str]) -> ToolRegistry:
    return ToolRegistry(
        catalog=catalog,
        tier0=set(tier0) | set(CHAT_MODEL_TIER0),
        agent_mode=True,
    )


def _active_schema_names(schemas: list[dict]) -> set[str]:
    names: set[str] = set()
    for schema in schemas:
        function = schema.get("function")
        if isinstance(function, dict):
            name = function.get("name")
            if isinstance(name, str):
                names.add(name)
    return names


def _assert_no_dispatchability_findings(schemas: list[dict]) -> None:
    findings = audit_visible_tool_dispatchability(schemas, _dispatch_context())
    assert findings == []


def test_dispatchability_audit_reports_malformed_duplicate_missing_and_no_arg_drift():
    context = DispatchContext(
        intercepted_names=frozenset(),
        local_tool_names=frozenset({"local_ok"}),
        transform_names=frozenset(),
        bridge_names=frozenset(),
        excluded_names=frozenset(),
        strict_no_argument_names=frozenset({"strict_zero"}),
    )
    schemas = [
        {
            "type": "function",
            "function": {
                "description": "Missing name",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
            },
        },
        _stub_schema("local_ok"),
        _stub_schema("local_ok"),
        _stub_schema("missing_tool"),
        {
            "type": "function",
            "function": {
                "name": "strict_zero",
                "description": "No-arg tool with drifted params",
                "parameters": {
                    "type": "object",
                    "properties": {"unexpected": {"type": "string"}},
                    "additionalProperties": False,
                },
            },
        },
    ]

    findings = audit_visible_tool_dispatchability(schemas, context)

    assert any(f.code == "missing_function_name" for f in findings)
    assert any(
        f.code == "duplicate_visible_name" and f.tool == "local_ok"
        for f in findings
    )
    assert any(
        f.code == "not_dispatchable" and f.tool == "missing_tool"
        for f in findings
    )
    assert any(
        f.code == "strict_no_arg_schema_drift" and f.tool == "strict_zero"
        for f in findings
    )


def test_default_local_initial_visible_tools_are_dispatchable_with_fallback_catalog():
    registry = _registry(_fallback_local_catalog(), AGENT_TIER_0)

    _assert_no_dispatchability_findings(registry.get_active_schemas())


def test_default_local_initial_visible_tools_are_dispatchable_with_synthetic_cached_catalog():
    extra_names = set(AGENT_TIER_0) | set(CHAT_MODEL_TIER0)
    registry = _registry(_fallback_local_catalog(extra_names), AGENT_TIER_0)

    _assert_no_dispatchability_findings(registry.get_active_schemas())


def test_default_local_gh_canvas_visible_tools_are_dispatchable_with_synthetic_cached_catalog():
    extra_names = set(AGENT_TIER_0) | set(TOOL_GROUPS["gh_canvas"]) | set(CHAT_MODEL_TIER0)
    registry = _registry(_fallback_local_catalog(extra_names), AGENT_TIER_0)

    result = registry.request_group("gh_canvas", turn=1)
    assert result["success"] is True
    schemas = registry.get_active_schemas()
    active_names = _active_schema_names(schemas)

    assert GH_CANVAS_SENTINELS <= active_names
    assert GH_CANVAS_SENTINELS - set(AGENT_TIER_0)
    _assert_no_dispatchability_findings(schemas)


def test_readonly_initial_visible_tools_are_dispatchable_with_synthetic_cached_catalog():
    extra_names = set(READONLY_TIER_0) | set(CHAT_MODEL_TIER0)
    registry = _registry(_fallback_local_catalog(extra_names), READONLY_TIER_0)

    _assert_no_dispatchability_findings(registry.get_active_schemas())
```

- [ ] **Step 2: Run the new tests to verify they fail before implementation**

Run:

```powershell
python -m pytest mcp_server/tests/test_rookchat_visible_dispatchability.py -q
```

Expected: FAIL during import with an error like:

```text
ImportError: cannot import name 'DispatchContext' from 'rook.agent.chat.tool_contracts'
```

- [ ] **Step 3: Commit or checkpoint the failing tests**

If the branch/workflow allows red commits, commit the failing tests:

```powershell
git add mcp_server/tests/test_rookchat_visible_dispatchability.py
git commit -m "test: add rookchat visible dispatchability gate"
```

If red commits are not allowed on the current branch, treat this as a review
checkpoint instead: leave the file unstaged, record the expected failing command
output in the task notes, and proceed to Task 2 without committing. Do not skip
the fail-first verification in Step 2.

---

## Task 2: Implement Structural Audit Helper

**Files:**
- Modify: `mcp_server/src/rook/agent/chat/tool_contracts.py`
- Test: `mcp_server/tests/test_rookchat_visible_dispatchability.py`

- [ ] **Step 1: Add imports for dataclasses and iterables**

Modify the import section in `mcp_server/src/rook/agent/chat/tool_contracts.py` from:

```python
from copy import deepcopy
from typing import Any
```

to:

```python
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Iterable
```

- [ ] **Step 2: Add dispatchability dataclasses after allowlists**

Insert this code after `DYNAMIC_NESTED_OBJECT_ALLOWLIST`:

```python
@dataclass(frozen=True)
class DispatchContext:
    intercepted_names: frozenset[str]
    local_tool_names: frozenset[str]
    transform_names: frozenset[str]
    bridge_names: frozenset[str]
    excluded_names: frozenset[str]
    strict_no_argument_names: frozenset[str]


@dataclass(frozen=True)
class DispatchabilityFinding:
    code: str
    tool: str
    classification: str
    message: str
```

- [ ] **Step 3: Add classification and audit helpers at the end of the file**

Append this code after `audit_litellm_tool_schema()`:

```python
def classify_visible_tool(tool_name: str, context: DispatchContext) -> str:
    """Classify a model-visible tool against structural dispatch surfaces.

    Precedence is intentional: ChatRunner-intercepted pseudo tools may also
    have dispatcher sentinel registrations, but the ChatRunner intercept is the
    real execution path for model-visible calls.
    """
    if tool_name in context.intercepted_names:
        return "chatrunner_intercepted"
    if tool_name in context.local_tool_names:
        return "dispatcher_local_tool"
    if tool_name in context.transform_names:
        return "dispatcher_transform"
    if tool_name in context.bridge_names:
        return "bridge_route"
    if tool_name in context.excluded_names:
        return "explicitly_excluded"
    return "failure"


def _closed_empty_parameters(parameters: Any) -> bool:
    return parameters == closed_no_arg_parameters()


def _parameters_for_schema(schema: dict[str, Any]) -> Any:
    function = schema.get("function")
    if not isinstance(function, dict):
        return None
    return function.get("parameters")


def audit_visible_tool_dispatchability(
    schemas: Iterable[dict[str, Any]],
    context: DispatchContext,
) -> list[DispatchabilityFinding]:
    """Audit model-visible tools for structural dispatchability.

    This function only inspects schema names and static dispatch membership.
    It must not execute tools, call Rhino, or ask the MCP server to dispatch.
    """
    findings: list[DispatchabilityFinding] = []
    seen: set[str] = set()

    for schema in schemas:
        tool_name = _tool_name(schema)
        if not tool_name:
            findings.append(DispatchabilityFinding(
                code="missing_function_name",
                tool="",
                classification="schema",
                message="Visible tool schema is missing function.name.",
            ))
            continue

        if tool_name in seen:
            findings.append(DispatchabilityFinding(
                code="duplicate_visible_name",
                tool=tool_name,
                classification="schema",
                message=f"Tool '{tool_name}' is visible more than once.",
            ))
            continue
        seen.add(tool_name)

        classification = classify_visible_tool(tool_name, context)

        if tool_name in context.strict_no_argument_names:
            parameters = _parameters_for_schema(schema)
            if not _closed_empty_parameters(parameters):
                findings.append(DispatchabilityFinding(
                    code="strict_no_arg_schema_drift",
                    tool=tool_name,
                    classification=classification,
                    message=(
                        f"Strict no-argument tool '{tool_name}' does not expose "
                        "closed empty parameters."
                    ),
                ))

        if classification == "failure":
            findings.append(DispatchabilityFinding(
                code="not_dispatchable",
                tool=tool_name,
                classification=classification,
                message=(
                    f"Visible tool '{tool_name}' has no ChatRunner intercept, "
                    "dispatcher local handler, transform function, bridge route, "
                    "or named exclusion."
                ),
            ))

    return findings
```

- [ ] **Step 4: Run the helper unit test**

Run:

```powershell
python -m pytest mcp_server/tests/test_rookchat_visible_dispatchability.py::test_dispatchability_audit_reports_malformed_duplicate_missing_and_no_arg_drift -q
```

Expected: PASS.

- [ ] **Step 5: Run the full new test file**

Run:

```powershell
python -m pytest mcp_server/tests/test_rookchat_visible_dispatchability.py -q
```

Expected: FAIL on synthetic cached visibility tests with findings for current non-dispatchable visible names such as:

```text
scene_graph
scene_context
scene_stats
gh_canvas_focus
gh_canvas_zoom
gh_canvas_image
chirp_create
```

The exact failure list may be shorter if those tools gained dispatch paths before this plan is executed. Do not add broad `excluded_names` to make the failure disappear.

Before moving to Task 3, compare the actual failure list to the expected names
above. If any additional visible tool fails dispatchability, stop for reviewer
decision before removing it from `tool_groups.py`. LM1A must not quietly shrink
local surfaces beyond the reviewed slice.

Also distinguish "not dispatchable by design" from "intended local handler
missing because an import failed in this environment." For each failed tool,
search `mcp_server/src/rook/agent/tool_dispatcher.py` for an intended local
registration or import block. If the tool is supposed to be registered by
`build_local_tools()` but is absent because an import/setup dependency failed,
do not remove it from `tool_groups.py`; fix the import/setup issue, isolate the
test fixture, or pause for reviewer decision.

- [ ] **Step 6: Commit the helper**

```powershell
git add mcp_server/src/rook/agent/chat/tool_contracts.py
git commit -m "feat: add rookchat visible dispatchability audit"
```

---

## Task 3: Remove Non-Dispatchable Names From Required Local Surfaces

**Files:**
- Modify: `mcp_server/src/rook/agent/tool_groups.py`
- Test: `mcp_server/tests/test_rookchat_visible_dispatchability.py`

Proceed with Task 3 only for the reviewed expected failure list:

```text
scene_graph
scene_context
scene_stats
gh_canvas_focus
gh_canvas_zoom
gh_canvas_image
chirp_create
```

If Task 2 produced a different or larger failure set, pause for reviewer
decision. Do not automatically remove additional names from local surfaces.

- [ ] **Step 1: Define local Tier-0 exclusions**

In `mcp_server/src/rook/agent/tool_groups.py`, add this block immediately after `TIER_0`:

```python
# These tools are valid MCP/server tools but do not currently have an internal
# RookChat ToolDispatcher path. Keep them out of local execution-profile Tier 0
# until they are added as ChatRunner intercepts, local tools, transforms, or
# bridge routes.
LOCAL_TIER_0_DISPATCH_EXCLUSIONS: Set[str] = {
    "scene_graph",
    "scene_context",
    "scene_stats",
}
```

- [ ] **Step 2: Apply local exclusions to `AGENT_TIER_0`**

Replace the current `AGENT_TIER_0` assignment:

```python
AGENT_TIER_0: Set[str] = (TIER_0 - {"gh_execute_intent"}) | {
```

with:

```python
AGENT_TIER_0: Set[str] = (
    TIER_0
    - {"gh_execute_intent"}
    - LOCAL_TIER_0_DISPATCH_EXCLUSIONS
) | {
```

Leave the rest of the `AGENT_TIER_0` set unchanged.

- [ ] **Step 3: Remove the same non-dispatchable names from readonly Tier 0**

In `READONLY_TIER_0`, delete these entries:

```python
    # Scene graph -- spatial awareness for all agents
    "scene_graph",
    "scene_context",
    "scene_stats",
```

Do not remove the `scene_graph` group from `READONLY_ALLOWED_GROUPS` in this slice. LM1A only audits readonly initial visibility, not exhaustive readonly groups.

- [ ] **Step 4: Remove non-dispatchable canvas names from local `gh_canvas`**

In `TOOL_GROUPS["gh_canvas"]`, replace this tail:

```python
        "gh_inspect_output", "gh_preview", "gh_bake_output",
        "gh_canvas_focus", "gh_canvas_zoom", "gh_canvas_image",
        "chirp_create",
```

with:

```python
        "gh_inspect_output", "gh_preview", "gh_bake_output",
        # gh_canvas_focus, gh_canvas_zoom, gh_canvas_image, and chirp_create
        # are MCP/server-side tools today. Do not expose them to local
        # RookChat execution profiles until ToolDispatcher paths exist.
```

Do not edit `TOOL_GROUPS["gh_canvas_readonly"]` in LM1A.

- [ ] **Step 5: Run the new dispatchability gate**

Run:

```powershell
python -m pytest mcp_server/tests/test_rookchat_visible_dispatchability.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit the local-surface cleanup**

```powershell
git add mcp_server/src/rook/agent/tool_groups.py mcp_server/tests/test_rookchat_visible_dispatchability.py
git commit -m "fix: keep non-dispatchable tools out of rookchat local surfaces"
```

---

## Task 4: Run Focused Regression Tests

**Files:**
- Test only.

- [ ] **Step 1: Run RookChat schema/contract tests**

Run:

```powershell
python -m pytest `
  mcp_server/tests/test_rookchat_visible_dispatchability.py `
  mcp_server/tests/test_rookchat_tool_schema_golden.py `
  mcp_server/tests/test_rookchat_tool_contracts.py `
  mcp_server/tests/test_rookchat_gh_script_creation_parity.py `
  -q
```

Expected: PASS.

- [ ] **Step 2: Run readonly enforcement regression tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_phase5b_readonly_enforcement.py -q
```

Expected: PASS.

If this fails because a test expected `scene_graph`, `scene_context`, or `scene_stats` in `READONLY_TIER_0`, update that test to assert only the tools that remain in readonly initial visibility:

```python
known_safe = {
    "rhino_ping", "rhino_objects", "rhino_geometry",
    "gh_snapshot", "gh_errors",
    "knowledge_query", "rhino_knowledge_query", "gh_knowledge_query",
    "request_tools", "search_tools",
}
```

Then rerun the same command and expect PASS.

- [ ] **Step 3: Run Python compile checks for touched modules**

Run:

```powershell
python -m py_compile `
  mcp_server/src/rook/agent/chat/tool_contracts.py `
  mcp_server/src/rook/agent/tool_groups.py `
  mcp_server/tests/test_rookchat_visible_dispatchability.py
```

Expected: no output and exit code 0.

- [ ] **Step 4: Commit any focused test expectation adjustment**

If Step 2 required a test-only adjustment, run:

```powershell
git add mcp_server/tests/test_phase5b_readonly_enforcement.py
git commit -m "test: align readonly tier0 with dispatchable local surface"
```

If Step 2 passed without changes, do not create an empty commit.

---

## Task 5: Final Verification And Handoff

**Files:**
- No code edits unless a verification command exposes a narrow issue in files already touched above.

- [ ] **Step 1: Run whitespace check**

Run:

```powershell
git diff --check
```

Expected: no output and exit code 0.

- [ ] **Step 2: Inspect final diff**

Run:

```powershell
git diff --stat
git diff -- mcp_server/src/rook/agent/chat/tool_contracts.py
git diff -- mcp_server/src/rook/agent/tool_groups.py
git diff -- mcp_server/tests/test_rookchat_visible_dispatchability.py
```

Expected:

- `tool_contracts.py` only adds structural audit dataclasses/helpers.
- `tool_groups.py` only removes non-dispatchable names from required local surfaces.
- `test_rookchat_visible_dispatchability.py` contains deterministic no-cache and synthetic cached fixtures.
- No PlanGraph, C# preflight, capability registry, workflow tool, or prompt cleanup changes.

- [ ] **Step 3: Run final focused test set**

Run:

```powershell
python -m pytest `
  mcp_server/tests/test_rookchat_visible_dispatchability.py `
  mcp_server/tests/test_rookchat_tool_schema_golden.py `
  mcp_server/tests/test_rookchat_tool_contracts.py `
  mcp_server/tests/test_rookchat_gh_script_creation_parity.py `
  mcp_server/tests/test_phase5b_readonly_enforcement.py `
  -q
```

Expected: PASS.

- [ ] **Step 4: Commit final verification fixes if any were needed**

If Step 3 required a narrow fix, stage only the touched LM1A files:

```powershell
git add `
  mcp_server/src/rook/agent/chat/tool_contracts.py `
  mcp_server/src/rook/agent/tool_groups.py `
  mcp_server/tests/test_rookchat_visible_dispatchability.py `
  mcp_server/tests/test_phase5b_readonly_enforcement.py
git commit -m "test: verify rookchat visible dispatchability gate"
```

If Step 3 passed with no changes since the previous commit, do not create an empty commit.

---

## Implementation Notes

- Keep `gh_errors` unexpected-argument rejection tests outside the audit helper. The helper is structural-only; dispatcher rejection belongs in existing dispatcher/schema tests.
- Do not add non-dispatchable tools to `excluded_names` for the required fixtures unless the product decision is explicitly that the tool must be visible but impossible to call. That should be rare.
- Do not call `ToolDispatcher.dispatch()` from the audit helper or tests that claim to be dispatchability audits. It is acceptable for existing dispatcher-specific tests to call it.
- Do not rely on ambient `knowledge/agent_tool_catalog.json`. The new tests must create deterministic catalogs in memory.
- Do not remove tools from public MCP `server.py`. This slice only controls local RookChat execution-profile visibility.

---

## Self-Review

- **Spec coverage:** The plan covers all required LM1A surfaces: default initial, default after `gh_canvas`, and readonly initial. It includes structural-only classification, strict no-arg schema drift findings, malformed/duplicate findings, deterministic fixture construction, and non-initial `gh_canvas` sentinels.
- **Placeholder scan:** No TODO/TBD placeholders remain. Every code step includes concrete code or exact commands.
- **Type consistency:** The test imports `DispatchContext` and `audit_visible_tool_dispatchability`; Task 2 defines both. The finding fields used in tests are `code` and `tool`; Task 2 defines them on `DispatchabilityFinding`.
