# LM1C: Grasshopper C# Script Create Preflight Design

## Status

Design approved for written-spec review. This document defines the LM1C slice
only. It must not be treated as approval for the LM2 capability registry,
`gh_update_script` preflight, a C# parser, or a public MCP wire-shape redesign.

## Context

LM1A made the required RookChat local execution-profile tool surfaces
structurally dispatchable. LM1B centralized RookChat tool-result interpretation
with `ToolResultView`. The adjacent compile-status truthfulness work made
post-mutation C# script failures honest by preserving component GUIDs and
reporting compile errors as failures.

The remaining gap is earlier in the execution path: local/internal models can
still submit C# script creation requests whose contracts are obviously invalid
before Grasshopper ever needs to mutate. Examples include invalid pin variable
names, duplicate input/output variable names, plugin-component source sent to a
RhinoCode script component, and body-style code that declares an output but
never visibly assigns it.

LM1C adds a narrow, non-live C# create-contract preflight at the unified server
helper boundary. The goal is to prevent obvious bad C# contracts before the
first `/gh/create-component` mutation while preserving the existing post-create
compile verification for everything that requires RhinoCode/Grasshopper to
judge.

## Goals

- Add a pure C# script creation preflight helper.
- Run the preflight for both `gh_create_csharp_script` and
  `gh_create_script(language="csharp")`.
- Run the preflight after pin normalization and before `/gh/create-component`.
- Reject invalid or duplicate C# pin variable names.
- Validate normalized pin access values without changing legacy raw-access
  alias behavior.
- Reject obvious plugin-component source patterns.
- Conservatively reject body-style scripts that do not visibly assign declared
  outputs.
- Return structured preflight findings that LM2 can later lift into capability
  records.
- Add non-live tests proving invalid preflight requests do not call
  `/gh/create-component`.

## Non-Goals

- No LM2 capability registry or surface compiler.
- No ChatRunner, dispatcher, or `tool_contracts.py` coupling.
- No broad model-visible schema example cleanup.
- No public MCP wire-shape redesign.
- No `gh_update_script` preflight.
- No full C# parser or Roslyn dependency.
- No Rhino/live dependency.
- No method-call mutation evidence such as `B.Add(...)` as assignment proof.
- No broadening of currently accepted language aliases.

## Architecture

LM1C adds the preflight at the existing unified creation helper in
`mcp_server/src/rook/server.py`:

```text
_execute_gh_create_script(...)
  validate language
  read code/name/position
  normalize pins_in / pins_out
  require at least one input or output
  if language is csharp:
      run pure C# create-contract preflight
      return structured failure if findings exist
  build language-specific script
  call /gh/create-component
  call /gh/script-params
  call /gh/script
  call /gh/errors
```

This location is intentionally below model-visible schema handling and above
Rhino/Grasshopper mutation. It covers all existing C# create entry points
because `gh_create_csharp_script` is a back-compat alias that delegates to the
same helper as `gh_create_script(language="csharp")`.

The helper should be local to the server execution boundary for LM1C. A neutral
contract module may become appropriate during LM2, but moving this into
`tool_contracts.py` now would make server execution depend on the model-visible
schema/result interpretation module and blur the boundary too early.

## Components

### `GhCSharpCreatePreflightFinding`

Use a small immutable or plain-data structure for each finding. Required fields:

```python
{
    "code": "invalid_pin_identifier",
    "message": "Pin name '1B' is not a valid C# identifier.",
    "field": "pins_out",
    "pin": "1B",
}
```

The exact Python representation can be a dataclass internally as long as the
failure payload serializes to dictionaries. Codes should be stable enough for
tests and future capability-record mapping.

### `_preflight_gh_csharp_create_script_contract(...)`

Suggested shape:

```python
def _preflight_gh_csharp_create_script_contract(
    code: str,
    pins_in: list[dict[str, Any]],
    pins_out: list[dict[str, Any]],
) -> list[GhCSharpCreatePreflightFinding]:
    ...
```

The helper must be pure:

- no Rhino calls;
- no `call_rhino`;
- no dispatcher imports;
- no ChatRunner imports;
- no catalog or ambient cache reads;
- no mutation of `arguments`, `pins_in`, or `pins_out`.

### Failure Formatter

Preflight failures should return an ordinary internal tool failure with
`message` at both levels:

```python
{
    "success": False,
    "message": "C# script preflight failed.",
    "data": {
        "message": "C# script preflight failed.",
        "preflight_errors": [...],
        "pins_in": [...],
        "pins_out": [...],
    },
}
```

The nested `data["message"]` is load-bearing because public `server.call_tool()`
failure formatting emits the failure `data` payload after the `Error: ` prefix.
The top-level `message` keeps internal helper behavior consistent with the
recent compile-truth helpers.

## Validation Rules

### Pin Identifiers

Each normalized input and output pin name must be a valid C# identifier:

- first character is `_` or an ASCII letter;
- later characters are `_`, ASCII letters, or digits;
- name is not a C# reserved keyword.

Use a conservative reserved-keyword set that includes language keywords such as
`class`, `public`, `private`, `void`, `object`, `ref`, `out`, `params`, `namespace`,
`using`, `return`, `new`, `base`, `this`, `null`, `true`, and `false`.

Do not attempt Unicode identifier support in LM1C. Rhino-facing and JSON-facing
code in this area already uses simple ASCII names in tests and docs, and local
models should be steered toward simple pin variables.

### Duplicate Names

Reject duplicate names across the combined `pins_in` and `pins_out` namespace.
RhinoCode C# wrapper generation places both inputs and outputs in the same
`RunScript` parameter list, so an input `B` and output `B` are as invalid as two
outputs named `B`.

Duplicate detection should be case-sensitive unless current RhinoCode behavior
or existing helper behavior already enforces case-insensitive uniqueness. LM1C
should not invent a broader naming policy than the execution path needs.

### Normalized Access Values

After existing pin normalization, pin `access` must be one of:

- `item`
- `list`
- `tree`

The existing pin normalizer owns raw access parsing. It currently accepts
`single` as an alias for `item` and rejects other invalid raw access values
before LM1C's post-normalization preflight can run. LM1C must preserve that
behavior. Invalid raw access therefore keeps the current normalizer failure
shape rather than being converted into `preflight_errors`.

LM1C should still keep normalized access in the preflight rule set because the
contract payload should be complete and future LM2 capability records need an
explicit contract fact. Direct helper tests may construct a normalized pin with
an invalid access value to prove the contract rule, but call-path tests should
not expect raw invalid access to reach the LM1C preflight formatter.

### Plugin-Component Source Misuse

Reject obvious plugin/component source patterns. The first slice should catch
clear indicators that the model sent a compiled Grasshopper component class
instead of RhinoCode script component source:

- `class ... : GH_Component`
- `SolveInstance`
- `RegisterInputParams`
- `RegisterOutputParams`
- `IGH_DataAccess`
- `GH_InputParamManager`
- `GH_OutputParamManager`

This rule applies regardless of whether the source also contains
`class Script_Instance` or `void RunScript`. A plugin component class is not a
valid source shape for `gh_create_csharp_script`.

### Declared Output Assignment Evidence

For body-style script content only, each declared output pin should have simple
assignment evidence. Accept only assignment-like writes in LM1C:

- `B = ...`
- `B += ...`
- `B -= ...`
- `B *= ...`
- `B /= ...`
- `B ??= ...`

Do not accept method-call mutation such as `B.Add(...)` as assignment evidence.
For output pins, the variable itself is a `ref object`; method-call mutation can
be ambiguous and may not initialize the output variable.

The assignment check is intentionally conservative. It is not a C# parser. If
the helper cannot confidently classify source as body-style code, it should not
run missing-output-assignment failures. In uncertain full-source or mixed-source
cases, reject only obvious plugin-source misuse and leave compile/application
truth to the existing post-mutation verification.

Full-source detection should follow the current wrapper boundary: content with
`class Script_Instance` or `void RunScript` is full-source or at least not
body-only for LM1C assignment checks.

## Language Handling

LM1C should apply the preflight when the normalized language is C#.

The existing `_execute_gh_create_script` language gate currently accepts only
languages present in `_GH_SCRIPT_LANGUAGE_CONFIGS`. LM1C should not broaden that
accepted language set. After the existing language acceptance check, the C#
branch can use the canonical `language` value. If local code needs an explicit
guard, use a normalized comparison such as:

```python
str(language).lower() == "csharp"
```

Do not introduce new aliases such as `"CSharp"` or `"c#"` unless they are
already accepted before LM1C.

## Data Flow

For a valid C# request:

```text
arguments -> normalized pins -> C# preflight passes
  -> C# wrapper/full-source preparation
  -> /gh/create-component
  -> /gh/script-params
  -> /gh/script
  -> /gh/errors
  -> existing success or compile-failure truth
```

For an invalid C# request:

```text
arguments -> normalized pins -> C# preflight findings
  -> structured internal failure
  -> no /gh/create-component call
```

Python creation is unaffected.

## Testing

All LM1C tests should be non-live and deterministic.

Unit tests should cover:

- valid simple body code passes;
- invalid pin identifier fails;
- C# reserved keyword pin fails;
- duplicate input/output namespace fails;
- normalized invalid access finding behavior, if direct helper tests can
  construct such a pin without going through the normalizer;
- `single` raw access remains accepted through the existing normalizer as
  `item`;
- `GH_Component` subclass source fails;
- `SolveInstance`, `RegisterInputParams`, `RegisterOutputParams`, and
  `IGH_DataAccess` source fails;
- body-style code with declared output `B` and no assignment to `B` fails;
- body-style code with `B = ...`, `B += ...`, or `B ??= ...` passes;
- `B.Add(...)` does not satisfy assignment evidence;
- full-source `Script_Instance` or `void RunScript` does not run the missing
  body-output assignment rule.

Call-path tests should prove:

- `gh_create_csharp_script` preflight failure does not call
  `/gh/create-component`;
- `gh_create_script(language="csharp")` preflight failure does not call
  `/gh/create-component`;
- successful C# requests still reach the existing create pipeline;
- Python `gh_create_script(language="python")` is unaffected;
- public `server.call_tool()` failure text includes parseable `data["message"]`
  and `preflight_errors` after stripping the `Error: ` prefix.
- raw invalid access keeps the existing normalizer failure shape and is not
  required to include `preflight_errors`.

Regression tests should continue to cover compile-error truthfulness after
mutation. LM1C preflight is not a replacement for compile verification.

## Acceptance Criteria

- C# script creation preflight exists and is pure/non-live.
- Both `gh_create_csharp_script` and `gh_create_script(language="csharp")` share
  the same preflight gate.
- The preflight runs after pin normalization and before `/gh/create-component`.
- Invalid/duplicate C# pin variable names fail before mutation.
- Normalized invalid C# pin access values fail before mutation, while existing
  raw access alias behavior such as `single` -> `item` is preserved.
- Obvious plugin-component source fails before mutation.
- Simple missing body-output assignment fails before mutation.
- Preflight failures return `success: false`, top-level `message`, nested
  `data["message"]`, nested `data["preflight_errors"]`, and normalized pin
  context.
- Tests prove invalid preflight requests do not call `/gh/create-component`.
- Existing post-mutation compile-status truth tests still pass.
- No capability registry, ChatRunner coupling, dispatcher coupling, or public
  MCP wire-shape change is introduced.

## Risks And Carry-Forward

The assignment detector will miss some invalid C# and may reject some unusual
valid body-code patterns. That is acceptable for LM1C if the rule stays
conservative and narrow. The north-star goal is to prevent obvious bad contracts
before mutation, not to prove program correctness without RhinoCode.

LM2 can lift the preflight name, finding codes, and membership rules into a
capability registry. LM1D or a nearby guidance slice can clean up model-visible
examples so generic live guidance teaches grammar rather than task content.
Later LM3 work can extend preflight to `gh_update_script` where target component
pin context is known.

## Spec Self-Review

- **Placeholders:** none.
- **Scope:** focused on C# creation preflight only; no capability registry,
  `gh_update_script`, ChatRunner, or dispatcher work.
- **Consistency:** the gate sits in the unified server helper, after pin
  normalization and before mutation, covering both C# create entry points.
- **Ambiguity:** assignment evidence is explicitly conservative and body-mode
  only; method-call mutation is a non-goal.
