# Grasshopper Authoring Capability Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refuse ordinary model-facing creation of supported modern script components and hand callers to the canonical script-authoring tools before target mutation.

**Architecture:** A small pure Python contract module owns the existing two script identities, selector classification, model-facing caller classification, and one structured handoff constructor. Canonical MCP and direct ToolDispatcher apply it before target dispatch; dedicated script routes share `_execute_gh_create_script`; raw `/gh/create-component` remains capability-neutral.

**Tech Stack:** Python 3.11+, pytest, MCP SDK, existing Rook bridge and skill Markdown.

## Global Constraints

- Baseline is exact `ad4d3b2798ab38b2245d7d9d12fdadd344b16de5`.
- No Rhino, Grasshopper, model, or live MCP contact.
- No managed/native change, new tool, external dependency, retry, fallback, caller flag, or copied identity registry.
- Preserve `gh_update_script`, `gh_set_script_pins`, T*/C*, `gh_snapshot`, receipts, and evaluator behavior.
- Stop if the implementation needs a second production policy owner or materially exceeds the files listed below.

---

### Task 1: Close model-facing script creation routing

**Files:**
- Create: `mcp_server/src/rook/gh_authoring_contract.py`
- Create: `mcp_server/tests/test_gh_authoring_capability_routing.py`
- Modify: `mcp_server/src/rook/server.py`
- Modify: `mcp_server/src/rook/agent/tool_dispatcher.py`
- Modify: `.agents/skills/execute-grasshopper/SKILL.md`
- Modify: `docs/CURRENT_ARCHITECTURE.md`

**Interfaces:**
- Produces: `GH_SCRIPT_LANGUAGE_CONFIGS`, `model_facing_script_handoff(tool_name: str, arguments: Mapping[str, Any]) -> dict[str, Any] | None`, and `resolved_script_handoff(source_tool: str, request: Mapping[str, Any], components: Iterable[Mapping[str, Any]]) -> dict[str, Any] | None`.
- Consumes: existing `_execute_gh_create_script`, MCP result projection, `call_rhino`, ToolDispatcher, and lifecycle containment.

- [x] **Step 1: Write RED pure-contract tests**

Add tests that assert:

```python
@pytest.mark.parametrize("language", ["python", "csharp"])
@pytest.mark.parametrize("selector_kind", ["guid", "name", "nickname"])
def test_supported_script_selectors_produce_one_closed_handoff(language, selector_kind):
    result = model_facing_script_handoff("gh_edit", request_for(language, selector_kind))
    assert result["success"] is False
    assert result["data"]["code"] == "script_component_requires_dedicated_tool"
    assert result["data"]["recommended_tool"] == "gh_create_script"
    assert result["data"]["recommended_language"] == language

def test_non_script_and_instance_only_requests_are_admitted():
    assert model_facing_script_handoff("gh_edit", non_script_edit()) is None
    assert model_facing_script_handoff(
        "gh_explore_component",
        {"guid": PYTHON_GUID, "instanceGuid": "existing-instance"},
    ) is None
```

Cover .NET N/D/B/P/X text forms for the two known GUIDs, contradictory
GUID/name input, mixed batches, exact request retention, closed fields, and
case-insensitive exact name/nickname matching. Assert fuzzy/legacy names do not
match.

- [x] **Step 2: Run the RED contract seam**

Run:

```powershell
& "C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe" -m pytest `
  mcp_server/tests/test_gh_authoring_capability_routing.py -q
```

Expected: collection/import failure because `rook.gh_authoring_contract` does
not exist.

- [x] **Step 3: Implement the pure contract owner**

Create `gh_authoring_contract.py` with:

```python
GH_SCRIPT_LANGUAGE_CONFIGS = {
    "python": {
        "guid": "719467e6-7cf5-4848-99b0-c5dd57e5442c",
        "names": ("Python 3 Script", "Py3"),
        "alias": "gh_create_python_script",
    },
    "csharp": {
        "guid": "b6ba1144-02d6-4a2d-b53c-ec62e290eeb7",
        "names": ("C# Script", "C#"),
        "alias": "gh_create_csharp_script",
    },
}

MODEL_FACING_COMPONENT_CREATION_ROUTES = frozenset({
    "gh_edit",
    "gh_explore_component",
    "gh_explore_deep",
    "gh_investigate",
})
```

Generate the accepted N/D/B/P/X strings from each canonical GUID. Do not parse
unknown caller GUIDs or accept `urn:uuid:` as a supported identity. Scan every
supplied `guid` and `name`; first supported selector in request order owns the
handoff. Return the exact response defined by the specification, including the
original request and internal `_is_handoff` marker.

- [x] **Step 4: Write RED ingress and no-dispatch tests**

Patch `call_rhino` with a hostile fake and prove:

```python
async def fail_if_contacted(*args, **kwargs):
    raise AssertionError("target dispatch occurred")
```

Exercise canonical `gh_edit`, direct `ToolDispatcher.dispatch("gh_edit", ...)`,
and the three active exploration routes for Python and C#. Assert identical
public `data`, `success=False`, no `_is_handoff` leakage, and zero target calls.
Add non-script controls that make exactly one unchanged bridge call. Add a
canonical MCP assertion for `structuredContent.success=False` and `isError=True`.

- [x] **Step 5: Apply the shared ingress guard**

In `server._call_tool_dispatch`, call `model_facing_script_handoff` after
containment and defensive argument copying, but before removing `port` or
entering the tool match. Return the handoff immediately.

In `ToolDispatcher.dispatch`, apply the same function after defensive copying
and before removing `port`; remove the private marker before returning the
public direct result. Do not add a second classifier.

Replace the old server-local language/map/handoff construction with imports
from the shared owner. Keep the retired `gh_execute_intent` post-resolution
check by delegating to `resolved_script_handoff`.

- [x] **Step 6: Route Chirp through canonical script creation**

Write a failing test that patches `_execute_gh_create_script`, invokes the
successful `chirp_create` branch with inert Chirp HTTP output, and asserts:

```python
assert helper_call.language == "csharp"
assert helper_call.arguments["code"] == generated_script
assert helper_call.arguments["pins_in"] == normalized_inputs
assert helper_call.arguments["pins_out"] == normalized_outputs
assert raw_create_calls == []
```

Replace Chirp's direct create/params/script sequence with one call to
`_execute_gh_create_script("csharp", ...)`; preserve Chirp's signature,
category, name, and session-facing result fields by enriching the helper result.

- [x] **Step 7: Add the closed caller-graph regression**

Parse `server.py` with `ast`, enumerate literal `/gh/create-component` and
`/gh/edit` calls and their enclosing helper or `case` arm, and compare them to
the reviewed classification:

```text
dedicated: _execute_gh_create_script
guarded active: gh_edit, gh_explore_component, gh_explore_deep, gh_investigate
contained defense-in-depth: gh_execute_intent
contained: gh_explore_workflow, gh_replay_recipe
fixed non-script exploration support: gh_explore_deep, gh_investigate
internal unadvertised primitive: gh_create_component
```

Also assert `gh_create_component` is absent from public tool schemas, targeting,
and ToolDispatcher bridge routes; contained callers remain in the lifecycle
registry. A new unclassified caller must fail this test.

- [x] **Step 8: Pin canonical script request preservation**

Add an inert four-input Point3d-list request through `gh_create_script` and
assert the helper sends the exact source and normalized four input/one output pin
definitions through its existing create/params/script sequence. Assert
`gh_create_script` remains present in `list_tools()` and readable through
`rook_tools_read` without model or host contact.

- [x] **Step 9: Update the skill and architecture ledger**

Amend the existing skill with the three-route split from the specification and
one sentence instructing the caller to follow a handoff rather than repeat the
refused ordinary route. Add a compact architecture paragraph naming the shared
model-facing guard and the neutral raw primitive. Do not add task topology.

- [x] **Step 10: Run focused and adjacent verification**

Run:

```powershell
& "C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe" -m pytest `
  mcp_server/tests/test_gh_authoring_capability_routing.py `
  mcp_server/tests/test_gh_edit_contract.py `
  mcp_server/tests/test_rookchat_gh_script_creation_parity.py `
  mcp_server/tests/test_server_contract_hardening.py `
  mcp_server/tests/test_tool_lifecycle.py -q

& "C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe" -m compileall -q `
  mcp_server/src/rook/gh_authoring_contract.py `
  mcp_server/src/rook/server.py `
  mcp_server/src/rook/agent/tool_dispatcher.py

git diff --check
```

Expected: all selected tests pass, compilation succeeds, and `diff --check`
prints nothing.

- [x] **Step 11: Self-review the production boundary**

Verify the diff contains only the listed files; raw `/gh/create-component`,
managed/native code, update/pin tools, snapshots, T*/C*, receipts, acceptance,
and runtime budgets are unchanged. Report production additions/deletions and
stop if a second policy owner or unclassified caller exists.
