# LM1A RookChat Visible Dispatchability Gate Design

- **Date:** 2026-06-19
- **Status:** Design spec, ready for implementation planning after review.
- **North-star parent:** `docs/superpowers/specs/2026-06-19-rook-local-internal-models-north-star.md`
- **Scope:** RookChat local execution-profile tool visibility. Non-live Python tests only.

---

## 1. Goal

Add a deterministic non-live gate proving that every model-visible tool in the required RookChat local execution-profile surfaces has a structural internal dispatch path, or is explicitly intercepted/excluded by name.

The center of gravity is:

```text
actual active schemas -> classify each visible tool -> assert no failure findings
```

This is a tripwire and fixture foundation for LM1/LM2. It is not the capability registry.

---

## 2. Required Surfaces

LM1A audits exactly these surfaces:

1. Default `rookchat_local` initial active set, using the current default `ChatRunner` registry path.
2. Default `rookchat_local` after `request_tools("gh_canvas")`.
3. Readonly initial active set, using `ChatRunner(tool_access="readonly")`.

The readonly audit is a thin smoke target only. Do not expand LM1A into exhaustive `READONLY_ALLOWED_GROUPS` coverage. The helper should make that next audit cheap, but it is not part of this slice.

---

## 3. Non-Goals

- No PlanGraph work.
- No C# script preflight.
- No capability-registry rewrite.
- No workflow tools.
- No broad prompt or schema-description cleanup.
- No exhaustive readonly group audit.
- No live Rhino dependency.
- No public MCP wire-shape change.
- No tool execution as part of dispatchability auditing.

If the work starts designing the whole capability registry, stop. LM1A is only the structural visibility tripwire.

---

## 4. Audit Helper

Add a small reusable helper, likely under the RookChat/tool-contract area, that accepts actual LiteLLM-style active schemas and a plain-data dispatch context.

Suggested shape:

```python
@dataclass(frozen=True)
class DispatchContext:
    intercepted_names: frozenset[str]
    local_tool_names: frozenset[str]
    transform_names: frozenset[str]
    bridge_names: frozenset[str]
    excluded_names: frozenset[str]
    strict_no_argument_names: frozenset[str]

def audit_visible_tool_dispatchability(
    schemas: Iterable[dict],
    context: DispatchContext,
) -> list[DispatchabilityFinding]:
    ...
```

Keep `DispatchContext` plain data so the helper can be reused without importing or constructing `ChatRunner`. Tests may build the context from `ToolDispatcher`, `build_local_tools()`, `TRANSFORM_FUNCTIONS`, `BRIDGE_ROUTES`, and known ChatRunner intercepts.

The helper inspects structure only. It must never call `ToolDispatcher.dispatch()`, `call_rhino()`, MCP `server.call_tool()`, or any function that could touch Rhino.

---

## 5. Classification

Each visible tool should classify into exactly one primary category:

- `chatrunner_intercepted`: `request_tools`, `search_tools`, `ui_block`, `list_chat_models`, `set_chat_model`, or another named ChatRunner-handled pseudo/meta tool.
- `dispatcher_local_tool`: present in local tool names.
- `dispatcher_transform`: present in `TRANSFORM_FUNCTIONS`.
- `bridge_route`: present in `BRIDGE_ROUTES`.
- `explicitly_excluded`: named MCP-only/server-only exception.
- `failure`: visible but not structurally dispatchable or intentionally excluded.

Classification precedence must be explicit because some ChatRunner-intercepted pseudo-tools are also registered as dispatcher local sentinel tools. Use either of these equivalent approaches:

1. Give `chatrunner_intercepted` precedence over all dispatcher categories.
2. Build the context with intercepted names subtracted from `local_tool_names`, `transform_names`, and `bridge_names`.

Preferred precedence:

```text
chatrunner_intercepted -> dispatcher_local_tool -> dispatcher_transform -> bridge_route -> explicitly_excluded -> failure
```

Missing names and duplicates are findings before category assignment.

For LM1A, `explicitly_excluded` should be empty for the three required fixtures unless current reality forces an exception. A visible MCP-only/server-only tool in these fixtures should fail first and be treated as a bug until proven intentional.

---

## 6. Findings

The helper should return structured findings, not raise. Required finding types:

- `missing_function_name`: visible schema has no `function.name`.
- `duplicate_visible_name`: the active schema set exposes the same name more than once.
- `not_dispatchable`: visible name is not intercepted, local, transform, bridge, or explicitly excluded.
- `strict_no_arg_schema_drift`: a visible strict no-argument tool does not expose closed empty parameters.

Optional useful fields:

```python
{
    "code": "not_dispatchable",
    "tool": "scene_graph",
    "classification": "failure",
    "message": "Visible tool has no ChatRunner intercept or ToolDispatcher path.",
}
```

Keep findings compact and stable enough for assertion messages.

---

## 7. Test Fixtures

Add focused non-live tests around real active schemas.

### 7.1 Default Initial

Build `ChatRunner()` using its normal registry path. Read:

```python
schemas = runner._registry.get_active_schemas()
```

Audit with a context built from the current dispatch surfaces. Assert findings are empty.

### 7.2 Default Plus `gh_canvas`

Build the same default runner or registry path. Call:

```python
result = runner._registry.request_group("gh_canvas", turn=1)
assert result["success"] is True
schemas = runner._registry.get_active_schemas()
```

The test must also assert that the post-request active names contain a small sentinel set proving the group actually loaded and the audit is not accidentally running against only the initial surface. Include both already-critical and non-initial GH canvas tools. Suggested sentinel set:

```python
{
    "gh_create_script",
    "gh_create_csharp_script",
    "gh_update_script",
    "gh_set_script",
    "gh_inspect_output",
}
```

If implementation chooses different sentinels, they must include at least one tool not already in the default initial active set. `gh_canvas_image` is also a useful sentinel if it remains intentionally visible; if it is visible but not structurally dispatchable, the audit should fail rather than silently dropping it.

Audit and assert findings are empty.

This is the load-bearing fixture because it covers the script tools and the GH canvas names weaker local models actually see.

### 7.3 Readonly Initial

Build:

```python
runner = ChatRunner(tool_access="readonly")
schemas = runner._registry.get_active_schemas()
```

Audit and assert findings are empty.

Do not request every readonly group in LM1A.

### 7.4 Schema Path Coverage

The fixtures should use deterministic construction paths equivalent to RookChat, not ambient machine-local state:

- a no-cache/fallback path that explicitly builds the fallback catalog plus local override catalog entries;
- normalized active schemas returned by `ToolRegistry.get_active_schemas()`;
- if cached-catalog behavior needs coverage, a synthetic cached-catalog fixture built in test memory or a temp path.

Do not rely on ambient `knowledge/agent_tool_catalog.json`. `ChatRunner` may use `load_catalog_from_cache()` when a cache exists, so tests that instantiate `ChatRunner()` directly must monkeypatch cache loading or otherwise force a deterministic catalog source. LM1A should have at least one no-cache/fallback fixture path and may add one synthetic cached-catalog path if it is cheap.

---

## 8. Strict No-Argument Discipline

LM1A is not a broad schema-hardening slice, but it must preserve the existing strict no-argument guarantee.

When a strict no-argument tool is visible, the audit should require:

```json
{
  "type": "object",
  "properties": {},
  "additionalProperties": false
}
```

Existing dispatcher behavior that rejects unexpected arguments remains unchanged. LM1A may add a focused test that `gh_errors` still rejects unexpected args if not already sufficiently covered, but the primary LM1A gate is structural schema visibility, not dispatch execution.

---

## 9. Expected First Failures

The current code may reveal visible-but-non-dispatchable names in `AGENT_TIER_0` or `gh_canvas`, especially names that exist as MCP/server cases but not in `ToolDispatcher` local/transform/bridge surfaces.

LM1A should not paper over those by default. The preferred resolution order is:

1. If the tool is not meant for local RookChat, remove it from the visible surface or group for that execution profile.
2. If it is a true ChatRunner pseudo/meta tool, add it to `intercepted_names` with a test.
3. If it is intentionally MCP-only/server-only but must remain visible, add a named `explicitly_excluded` exception with a rationale in the test.
4. If it should be callable, add or fix the dispatch path in a later implementation slice, not inside the audit helper.

Do not auto-route malformed or unknown calls.

---

## 10. Acceptance Criteria

- Non-live Python tests fail if any required active schema exposes a visible tool with no structural dispatch path or named intercept/exclusion.
- Required surfaces covered:
  - default `rookchat_local` initial active set;
  - default `rookchat_local` after `request_tools("gh_canvas")`;
  - readonly initial active set.
- The audit helper classifies visible tools using plain dispatch-context data.
- The helper detects missing `function.name`, duplicate visible names, not-dispatchable tools, and strict no-argument schema drift.
- Strict no-argument tools still expose closed no-arg schemas when visible and keep dispatcher rejection behavior.
- Fallback/local/catalog-normalized schema paths are covered by deterministic tests or explicit fixture construction; tests do not depend on ambient `knowledge/agent_tool_catalog.json`.
- The `gh_canvas` fixture asserts `request_group("gh_canvas")` succeeds and that the post-request active set contains expected `gh_canvas` sentinel tools, including at least one non-initial tool.
- Any pseudo-tool or MCP-only/server-only exception is named in code/tests.
- No Rhino live dependency.
- No public MCP wire-shape change.
- No capability-registry rewrite.

---

## 11. Spec Self-Review

- **Placeholders:** none.
- **Scope:** focused on structural dispatchability for three active schema fixtures.
- **Consistency:** the helper inspects visible schemas and plain dispatch-context data; it does not execute tools.
- **Ambiguity:** `explicitly_excluded` is intentionally empty unless current reality forces a named exception.
