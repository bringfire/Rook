# LM1C: Grasshopper C# Script Preflight Design

## Status

Design draft for review. This document defines the LM1C slice only. It must
not be treated as approval for PlanGraph, repair loops, a capability registry,
full C# compilation, or a Grasshopper execution redesign.

## Context

LM1A proved that local RookChat-visible tools are structurally dispatchable.
LM1B added a shared result-view adapter so ChatRunner can interpret existing
tool results without changing dispatcher or MCP wire semantics.

The next local-model reliability gap is C# script component creation. Sparse
models can produce C# that is plausible in ordinary Grasshopper plugin
development but categorically wrong for RhinoCode C# script components. Today,
some invalid payloads can reach the Grasshopper mutation path before the system
discovers the mistake.

The LM1C goal is not to make models better at C#. It is to reject obvious
script-contract violations before they mutate the canvas.

## Goals

- Add a small shared C# script preflight helper that is importable and unit
  testable outside `server.py`.
- Run the preflight for C# script creation after language and pin
  normalization, before `/gh/create-component`.
- Run the preflight for C# script updates after runtime and pin discovery,
  before the `/gh/script` write mutation.
- Preserve existing public MCP wire shape.
- Preserve existing dispatcher behavior except for receiving the new failure
  result from the existing script helper path.
- Add deterministic, non-live tests proving invalid C# payloads do not call
  `/gh/create-component` or mutate `/gh/script`.

## Non-Goals

- No PlanGraph.
- No eval harness.
- No component repair loop.
- No full C# compilation or Roslyn integration.
- No RhinoCommon method validation.
- No geometry-task recipe/examples expansion.
- No capability registry.
- No broad dispatcher refactor.
- No individual tool migration beyond the smallest C# preflight wiring.
- No live Rhino requirement for the first implementation.
- No public MCP wire-shape change.
- No `gh_set_script` migration. Raw `gh_set_script` remains an explicit escape
  hatch and is out of scope for LM1C.
- No hard rejection for "declared output pins not assigned". That is useful
  contract analysis, but it is heuristic and can false-positive.

## Current Code Paths

The RookChat/local path reaches script creation through:

- `mcp_server/src/rook/agent/chat/chat_runner.py`
  - `_GH_CREATE_SCRIPT_SCHEMA`
  - `_GH_CREATE_CSHARP_SCRIPT_SCHEMA`
  - `_GH_CSHARP_SCRIPT_CONTRACT`
- `mcp_server/src/rook/agent/tool_dispatcher.py`
  - `_normalize_gh_create_script_kwargs(...)`
  - `_local_gh_create_script(...)`
  - `_local_gh_create_csharp_script(...)`
  - `_local_gh_update_script(...)`
  - `_transform_gh_set_script(...)`
- `mcp_server/src/rook/server.py`
  - `_normalize_gh_script_pins(...)`
  - `_build_gh_csharp_wrapper(...)`
  - `_prepare_gh_update_script_source(...)`
  - `_execute_gh_update_script(...)`
  - `_execute_gh_create_script(...)`

`_execute_gh_create_script(...)` backs both the unified MCP helper
`gh_create_script` and the local aliases `gh_create_python_script` /
`gh_create_csharp_script`. Wiring preflight there is broader than
RookChat-local, but that is acceptable for LM1C because it preserves response
shape and enforces the invariant before `/gh/create-component`.

The create mutation sequence is currently:

1. normalize language/code/pins;
2. build language-specific source;
3. `POST /gh/create-component`;
4. `POST /gh/script-params`;
5. `POST /gh/script`;
6. `GET /gh/errors`.

LM1C inserts C# preflight after step 1 and before step 2/3.

The update path currently:

1. validates `guid` and `code`;
2. reads `/gh/script`;
3. reads `/gh/component`;
4. classifies runtime and extracts current pins;
5. prepares source via `_prepare_gh_update_script_source(...)`;
6. writes `POST /gh/script`;
7. optionally checks `/gh/errors`.

LM1C inserts C# preflight after step 4, inside or immediately before source
preparation, before the step 6 write mutation. The read calls are acceptable:
the preflight needs current runtime and pin structure for updates.

## Helper Location

Add a small module such as:

```text
mcp_server/src/rook/gh_csharp_preflight.py
```

or:

```text
mcp_server/src/rook/gh_script_preflight.py
```

Recommendation: use `gh_csharp_preflight.py` if the first implementation is
C#-only; use `gh_script_preflight.py` only if the module is structured to hold
future language-specific validators without expanding LM1C now.

The helper should not live only in `server.py`. `server.py` already owns the
mutation orchestration; the C# script contract should remain separately
testable.

## Preflight Contract

The helper should expose plain data and avoid any Rhino, Grasshopper, MCP, or
dispatcher imports where practical.

One acceptable shape:

```python
@dataclass(frozen=True)
class CSharpScriptPreflightResult:
    ok: bool
    message: str | None = None
    code: str | None = None


def preflight_csharp_script(
    *,
    code: Any,
    pins_in: Sequence[Mapping[str, Any]],
    pins_out: Sequence[Mapping[str, Any]],
    mode: str = "auto",
) -> CSharpScriptPreflightResult:
    ...
```

The helper should return a result rather than raise for ordinary validation
failures. Callers may still treat unexpected helper errors as ordinary tool
exceptions.

The helper should be structural and side-effect free:

- no Rhino calls;
- no Grasshopper calls;
- no compilation;
- no mutation of input dicts/lists;
- no generated code examples;
- no model-facing prompt changes as part of validation.

## C# Source Mode Detection

LM1C must not leave two subtly different definitions of "recognized
full-source C#" in the codebase.

Extract the current wrapper predicate into one shared helper, for example:

```python
def is_recognized_csharp_full_source(code: Any) -> bool:
    return isinstance(code, str) and (
        "class Script_Instance" in code or "void RunScript" in code
    )
```

`preflight_csharp_script(...)`, `_build_gh_csharp_wrapper(...)`, and the C#
branch of `_prepare_gh_update_script_source(...)` should use that same
predicate. The LM1C implementation should not broaden full-source recognition
beyond the current rule. Plugin-component patterns such as `GH_Component` still
fail even when the shared predicate also matches.

## Hard-Reject Conditions

LM1C should reject only structural category errors and impossible wrapper
inputs.

### Code Shape

Reject when:

- `code` is not a string;
- `code` is empty or whitespace;
- code contains Grasshopper plugin-component patterns that do not belong in a
  RhinoCode script component:
  - `: GH_Component`
  - `SolveInstance`
  - `RegisterInputParams`
  - `RegisterOutputParams`
  - `IGH_DataAccess`
  - `GH_InputParamManager`
  - `GH_OutputParamManager`
- code contains a class declaration that would be wrapped as body code instead
  of being recognized as valid full-source script code;
- body-style code contains top-level `using ...;` directives.

Top-level `using ...;` should be allowed only when the code is being treated as
recognized full-source RhinoCode `Script_Instance` / `RunScript` source. It
should not be allowed in body-style code that `_build_gh_csharp_wrapper(...)`
will place inside `RunScript`.

Plugin-component patterns should be rejected even if they appear alongside a
`RunScript` token. `GH_Component` subclass code is the wrong category for this
tool.

### Pin Variable Shape

Reject when any normalized input or output pin name:

- is missing or not a string;
- is not a valid C# identifier;
- is a C# reserved keyword;
- duplicates another input or output variable name.

Duplicate detection should be conservative and should consider the combined
input/output parameter namespace used by `_build_gh_csharp_wrapper(...)`.
LM1C should use case-sensitive duplicate detection to match C# parameter rules.
Case-insensitive duplicate policy can be considered later, but it must not be a
hard reject in this slice.

### Explicitly Not A Hard Reject

LM1C must not reject merely because:

- the declared output variable is not obviously assigned;
- the code might reference a nonexistent RhinoCommon member;
- the code has ordinary C# syntax errors that require compilation to prove;
- the geometry produced may not match the user's design intent;
- the model used a RhinoCommon type name that may or may not exist.

Those belong to later compile/repair/eval slices.

## Failure Shape

Preflight failures should use the existing tool result shape:

```python
{
    "success": False,
    "data": "C# script preflight failed: <specific reason>"
}
```

Do not introduce a new public envelope. Do not add MCP-visible result fields
unless an existing internal wrapper already requires them.

LM1B `ToolResultView` already interprets top-level `success: False` as
`status == "failed"`. The `data` string remains the raw serialized content for
ChatRunner history. The adapter does not participate in serialization.

The failure should occur before mutation:

- create: before any `/gh/create-component` call;
- update: before any `/gh/script` write call.

## Create Wiring

In `_execute_gh_create_script(...)`, keep the existing language validation,
code lookup, and pin normalization. Then:

1. If `language == "csharp"`, call `preflight_csharp_script(...)`.
2. If preflight fails, return the standard failure dict immediately.
3. If preflight passes, continue to `_build_gh_csharp_wrapper(...)`.
4. Only after source preparation succeeds may the code call
   `/gh/create-component`.

This protects:

- local `gh_create_csharp_script`;
- unified local/MCP `gh_create_script` when `language == "csharp"`;
- any future caller that reuses `_execute_gh_create_script(...)`.

Python creation remains unchanged.

## Update Wiring

In the update flow, C# preflight needs the detected runtime and current pins.
The right boundary is after `_classify_gh_update_script_runtime(...)` and
`_gh_component_params_to_script_pin_defs(...)`, before the `/gh/script` write.

The cleanest implementation is likely inside `_prepare_gh_update_script_source(...)`
for C# runtimes:

- determine whether the C# update is recognized full-source or body-style using
  the shared full-source predicate used by preflight and wrapper behavior;
- call `preflight_csharp_script(...)` with current `inputs`, `outputs`, and the
  selected mode;
- raise `ValueError("C# script preflight failed: ...")` or return a structured
  failure through the caller.

The implementation plan should choose one of two failure plumbing styles:

- Return a preflight failure dict directly from `_execute_gh_update_script(...)`
  before calling `_prepare_gh_update_script_source(...)`.
- Raise `ValueError` from `_prepare_gh_update_script_source(...)` and let the
  existing exception wrapper return `{"success": False, "data":
  "gh_update_script failed: C# script preflight failed: ..."}`.

Recommendation: prefer direct failure dict plumbing if it is simple, because it
keeps the preflight failure message parallel to create. If direct plumbing
requires awkward duplication of mode logic, use the existing `ValueError` path
and test the exact message.

## `gh_set_script` Boundary

`gh_set_script` is deliberately out of scope for LM1C.

It is a raw script write escape hatch transformed by `_transform_gh_set_script(...)`.
It does not carry enough local C# script contract information by itself, and it
is already referenced as the escape hatch for cases that cannot be safely
wrapped or updated. Do not silently migrate it into this slice.

Future work may add an explicit C#-aware raw write validator, but that should
be a separate design because it needs runtime inspection and escape-hatch
policy decisions.

## Tests

All LM1C tests should be deterministic and non-live.

### Unit Tests

Add focused tests for the helper covering:

- valid body-style code with valid pins passes;
- valid recognized full-source `Script_Instance` / `RunScript` code passes;
- non-string code fails;
- empty code fails;
- invalid C# identifier pin names fail;
- reserved keyword pin names fail;
- duplicate pin names fail;
- `GH_Component` subclass code fails;
- `SolveInstance` / `RegisterInputParams` / `RegisterOutputParams` patterns
  fail;
- top-level `using ...;` fails in body-style mode;
- top-level `using ...;` is allowed in recognized full-source mode;
- missing output assignment is not a hard reject;
- helper does not mutate input pin data.

### Create Path Tests

Extend or add tests around the existing RookChat/GH script creation parity
suite:

- `gh_create_csharp_script` with `GH_Component` subclass code returns
  `success: False`;
- the same failure path does not call mocked `/gh/create-component`;
- unified `gh_create_script(language="csharp")` has the same guard;
- Python `gh_create_script(language="python")` is unaffected;
- common alias normalization through `_normalize_gh_create_script_kwargs(...)`
  still reaches preflight with the normalized `code` field.

### Update Path Tests

Use mocked `call_rhino(...)` responses:

- allow read-only `/gh/script` and `/gh/component` calls needed to classify the
  target component;
- return C# runtime metadata and pins;
- pass invalid C# update code;
- assert the result fails before any `/gh/script` write mutation;
- assert Python update remains unaffected.

### Result Interpretation Test

LM1B already covers `ToolResultView` precedence. LM1C only needs a narrow
regression if useful:

- `normalize_tool_result({"success": False, "data": "C# script preflight failed: ..."})`
  returns `status == "failed"`.

Do not expand ChatRunner result-history tests unless implementation changes
ChatRunner behavior. LM1C should not need ChatRunner event wiring.

## Acceptance Criteria

- A small importable C# script preflight helper exists outside `server.py`.
- C# script creation preflight runs after pin normalization and before
  `/gh/create-component`.
- C# script update preflight runs after runtime/pin discovery and before
  `/gh/script` write mutation.
- Public MCP result shape remains unchanged.
- `ToolResultView` classifies preflight failures through existing top-level
  `success: False`.
- `gh_set_script` remains an explicitly documented out-of-scope escape hatch.
- Non-live tests prove rejected C# create payloads do not call
  `/gh/create-component`.
- Non-live tests prove rejected C# update payloads do not call `/gh/script`
  write mutation.
- No live Rhino dependency is introduced.

## Risks And Carry-Forward

This slice intentionally catches only category errors and impossible wrapper
inputs. It will not catch every bad script. A script can pass LM1C and still
fail compilation, produce no useful geometry, or use a nonexistent RhinoCommon
method. That is acceptable.

The next likely slice after LM1C may inspect compile errors and repair loops,
but LM1C should stop at deterministic pre-mutation rejection.

The output-assignment contract remains important for local models, but it is
not a hard LM1C preflight condition. It should be considered later as either a
warning, a repair hint, or a more careful validator once false-positive policy
is settled.
