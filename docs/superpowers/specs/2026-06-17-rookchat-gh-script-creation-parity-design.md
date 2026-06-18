# RookChat GH Script Creation Parity Design

## Problem

RookChat currently teaches agents to use `gh_create_script`,
`gh_create_python_script`, and `gh_create_csharp_script` for Grasshopper script
component creation, but the embedded chat execution path cannot actually
dispatch those tools.

The mismatch is visible across the stack:

- `mcp_server/src/rook/server.py` implements the three tools through
  `_execute_gh_create_script`.
- `mcp_server/src/rook/agent/tool_groups.py` advertises all three in
  `TOOL_GROUPS["gh_canvas"]`.
- persona prompts tell agents to use `gh_create_script(language=...)` or the
  aliases for script creation.
- `mcp_server/src/rook/agent/tool_dispatcher.py::build_local_tools()` only
  registers `gh_update_script` and `gh_set_script_pins`; the create tools are
  not local, not transform-backed, and not bridge-backed.

This makes the RookChat panel's tool contract inconsistent: an agent can be
taught or discover a script-creation tool that the direct chat dispatcher
reports as unknown. The fair first fix is to make the documented script
creation path executable before changing model prompts or comparing model
quality.

## Goal

Make RookChat's direct tool execution surface truthful for Grasshopper script
creation: every `gh_create_*` tool advertised to panel agents must have a
dispatcher path, a useful local schema, and regression coverage.

## Scope

In scope:

- Add local dispatcher wrappers for:
  - `gh_create_script`
  - `gh_create_python_script`
  - `gh_create_csharp_script`
- Preserve existing server helper behavior and response semantics.
- Add ChatRunner local-catalog schemas for those tools so fallback/local
  catalogs give the model the same required fields as the MCP/server surface.
- Add tests that prove prompt/tool-group/catalog/dispatcher consistency and
  prevent the `Unknown tool` path for the create tools.

Out of scope:

- No prompt or model-behavior guardrail PR in this slice.
- No retry-policy changes.
- No Workbench launcher changes.
- No Rhino process/session topology changes.
- No deploy, OCCT, native, or `.vcxproj` changes.
- No staging or reverting of `knowledge/*` runtime artifacts.

## Existing Contracts To Preserve

`server._execute_gh_create_script(language, arguments, port, tool_name=...)`
already defines the canonical create pipeline:

1. validate `language`;
2. normalize pins;
3. prepare language-specific source;
4. create the fixed RhinoCode script component;
5. set pins;
6. inject script;
7. check component errors.

The local chat path must delegate to this helper instead of reimplementing the
pipeline.

Alias semantics must remain exact:

- `gh_create_script` passes the caller-provided `language` through.
- `gh_create_python_script` forces `language="python"`.
- `gh_create_csharp_script` forces `language="csharp"`.
- each entry point passes its own `tool_name` into `_execute_gh_create_script`
  so unexpected failure prefixes remain coherent.

## Design

### Dispatcher Reachability

Add three async local wrappers near the existing script local wrappers in
`mcp_server/src/rook/agent/tool_dispatcher.py`:

- `_local_gh_create_script(port=None, **kwargs)`
- `_local_gh_create_python_script(port=None, **kwargs)`
- `_local_gh_create_csharp_script(port=None, **kwargs)`

Each wrapper imports `_execute_gh_create_script` lazily from `rook.server`,
matching the existing `_local_gh_update_script` pattern. The unified wrapper
reads `kwargs.get("language")`; the aliases pass fixed language values.

Register all three in `build_local_tools()`.

This keeps the chat panel on the same implementation path as MCP/server calls
without adding a new HTTP bridge route or duplicating Grasshopper-specific
script creation behavior.

### Local Catalog Schema Parity

`ChatRunner` builds a local LiteLLM tool catalog when tools are registered
locally. Today only `gh_update_script` has a typed local schema; other local
tools get an open `additionalProperties` schema.

This slice should add hand-authored local schemas beside
`_GH_UPDATE_SCRIPT_SCHEMA` in `mcp_server/src/rook/agent/chat/chat_runner.py`.
They should mirror the server tool contract closely enough for model use:

- `gh_create_script`
  - required: `language`, `code`
  - `language` enum: `["python", "csharp"]`
  - optional: `pins_in`, `pins_out`, `name`, `x`, `y`
- `gh_create_python_script`
  - required: `code`, `pins_in`, `pins_out`
  - no caller-facing `language` requirement
  - optional: `name`, `x`, `y`
- `gh_create_csharp_script`
  - required: `code`, `pins_in`, `pins_out`
  - no caller-facing `language` requirement
  - optional: `name`, `x`, `y`

The unified and alias schemas are intentionally asymmetric because the server
schemas are asymmetric today. The unified tool accepts omitted pin arrays and
lets the helper enforce the "at least one of `pins_in` or `pins_out`" runtime
rule. The alias MCP schemas currently require both pin arrays. This slice should
preserve that server shape rather than broaden alias input compatibility.

Chosen schema source: hand-authored schemas beside `_GH_UPDATE_SCRIPT_SCHEMA`.
This avoids importing or awaiting `server.list_tools()` during ChatRunner
construction and matches the current local-schema pattern. Drift risk is
managed with focused tests that compare required fields and language enum
against the server MCP definitions.

### Regression Tests

Add focused tests under existing Python test files rather than requiring live
Rhino:

- `build_local_tools()` includes the three `gh_create_*` tools.
- `ToolDispatcher.dispatch("gh_create_script", ...)` reaches the mocked server
  helper and no longer returns `Unknown tool`.
- Alias dispatch forces the correct language and passes the alias `tool_name`.
- `_build_local_tool_catalog()` emits typed schemas for all three create tools.
- Local schema requirements match the server tool schema for:
  - unified required `language` and `code`;
  - alias required `code`, `pins_in`, and `pins_out`;
  - unified language enum.
- A dispatcher-reachability guard covers `TOOL_GROUPS["gh_canvas"]` script
  create tools: each must be reachable through local, transform, or bridge
  dispatch.

The tests should mock `server._execute_gh_create_script` or the wrapper import
boundary, not call Rhino.

## Error Handling

The wrappers should not add new error translation. `_execute_gh_create_script`
already returns structured `{"success": False, "data": ...}` failures for bad
language, missing code, pin normalization failures, creation failures, pin
configuration failures, script injection failures, and unexpected exceptions.

`ToolDispatcher` already catches local-tool exceptions in `_call_local`; this
slice should rely on that existing boundary.

## Verification

Non-live verification for the implementation PR:

- focused Python tests for chat prompt/catalog/dispatcher/script creation
  parity;
- existing server contract tests around `gh_create_script`;
- `git diff --check`.

Live Rhino verification is optional for this slice because no Grasshopper
creation pipeline behavior changes; the implementation only exposes the
already-tested server helper to the RookChat local dispatcher.

## Success Criteria

- A RookChat agent that loads or searches for `gh_create_script` can execute it
  through the direct chat dispatcher.
- The model sees a useful schema for script creation even without relying on a
  cached MCP catalog.
- `gh_create_csharp_script` is no longer a prompt-advertised but
  dispatcher-unknown capability.
- Prompt/model-behavior guardrails remain deferred to the next slice, where the
  same C# grid task can be rerun against a truthful tool surface.
