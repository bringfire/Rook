# GH Update Script Design

Date: 2026-05-29

Status: Approved design. This is not an implementation plan.

## Goal

Add a durable agent-facing script update tool for existing Grasshopper script
components.

The product problem is that `gh_set_script` is a raw source setter. That is the
right low-level contract, but it is not the right default for agents editing
RhinoCode C# Script components. RhinoCode C# stores a full
`Script_Instance : GH_ScriptInstance` source file, while agents naturally want
to send only the body of `RunScript`, matching the behavior of
`gh_create_csharp_script`.

The new tool should make the normal edit path reliable:

```text
create script component -> gh_create_script
edit existing script code -> gh_update_script
edit existing script pins -> gh_set_script_pins
raw source read/write -> gh_set_script
```

## Non-Goals

- No new native or managed companion route in v1.
- No changes to `gh_set_script` raw semantics.
- No pin edits inside `gh_update_script` v1.
- No rollback or partial-success contract for combined pin/source edits.
- No body-mode support for GH1 legacy C# until its exact source shape is
  verified live.
- No broad refactor of Grasshopper script component handling.

## Architecture

`gh_update_script` lives in the Python MCP layer, in `mcp_server/src/rook/server.py`.
It orchestrates existing companion-backed GH routes:

- `/gh/script` without `script` to read current source and runtime type.
- `/gh/component` or equivalent component metadata to read current component
  identity and pins.
- `/gh/script` with prepared source to set the script.
- `/gh/errors` to report compile/runtime diagnostics.

This keeps RookNative as the public HTTP surface and keeps all actual GH
mutation behavior companion-backed through the existing callback bridge.

The existing helpers must be reused rather than reimplemented:

- `_build_gh_csharp_wrapper`
- `_build_gh_python_preamble`
- `_build_gh_python_output_postamble`
- `_gh_component_params_to_script_pin_defs`
- existing pin normalization / payload conversion helpers where applicable

## Tool Contract

Tool name:

```text
gh_update_script
```

Input:

```json
{
  "guid": "C20",
  "code": "var r = Convert.ToDouble(R);\nA = r * 2;",
  "mode": "auto",
  "language": "auto",
  "python_preamble": true,
  "check_errors": true
}
```

Fields:

- `guid`: required. Existing script component GUID or short ID from
  `gh_snapshot`.
- `code`: required. Body code or full source depending on `mode`.
- `mode`: optional. One of `auto`, `body`, `full_source`. Default `auto`.
- `language`: optional. One of `auto`, `python`, `csharp`. Default `auto`.
- `python_preamble`: optional bool. Default `true` for RhinoCode Python 3
  body-like source when current pin metadata supports it.
- `check_errors`: optional bool. Default `true`.

`language` is not authoritative. Runtime detection comes from the component
readback and component metadata. Caller-supplied `language` only narrows or
validates the detected runtime. A mismatch fails closed.

## Code-Only Boundary

`gh_update_script` v1 only changes source code.

Signature changes are explicitly a two-step flow:

1. Call `gh_set_script_pins`.
2. Call `gh_update_script`.

`gh_update_script` must read the verified current pins after any pin changes
settle. C# wrapping must use only those current pins, never caller-claimed pins.

This avoids mixing two failure domains. If a caller needs atomic pin + source
mutation later, that should be a separate design with explicit rollback or
partial-success semantics.

## Runtime Behavior

### RhinoCode C#

For detected RhinoCode `CSharpComponent`:

- `mode: "full_source"` passes source through after validating that it appears
  to contain a full `Script_Instance` or `RunScript` source.
- `mode: "body"` wraps `code` with `_build_gh_csharp_wrapper` using current
  input and output pins.
- `mode: "auto"` treats source containing `class Script_Instance` or
  `void RunScript` as full source. Otherwise it treats source as body code and
  wraps it.

Current output pins must exclude the built-in `out` print stream. This must
match the existing create-path helper behavior. In practice, wrapper generation
uses component output pin definitions with the first print stream skipped, so
it does not generate invalid parameters such as `ref object out`.

If body-mode compilation fails with likely unknown variable/pin-name errors,
the response should include a recovery hint naming the current pins:

```text
Current inputs are R, N; outputs are A. To change the signature, call
gh_set_script_pins first, then retry gh_update_script.
```

### RhinoCode Python 3

For detected RhinoCode Python 3 Script components:

- `mode: "full_source"` writes the provided source directly and never adds a
  generated preamble or postamble.
- `mode: "body"` may add the existing Rook generated preamble/postamble when
  `python_preamble` is true and current pin metadata supports it.
- `mode: "auto"` is body-like unless the source is already prepared with Rook's
  generated sentinels.

Generated Python blocks must not be inserted twice. The implementation should
detect the existing sentinels used by the create path, including:

```text
# ── Auto-generated GH input coercion
# ── Auto-generated GH output coercion
```

If either generated block is already present in the submitted source,
`gh_update_script` should avoid duplicating that block.

### GH1 Legacy Python

GH1 legacy Python remains raw/direct in v1. No generated preamble/postamble is
added.

### GH1 Legacy C#

GH1 legacy C# supports full-source/raw updates through `gh_set_script`.

`gh_update_script` v1 fails closed for `mode: "body"` or body-like `auto` on
GH1 C# until the legacy wrapper/source shape is verified live. The error should
tell callers to use `mode: "full_source"` if supported by the detected runtime,
or use `gh_set_script` with exact source.

## Result Shape

Responses follow the existing MCP convention:

```json
{
  "success": true,
  "data": {
    "guid": "C20",
    "detected_runtime": "RhinoCode C#",
    "detected_language": "csharp",
    "mode_used": "body",
    "wrapped": true,
    "inputs_used": ["S", "imagePath", "cols"],
    "outputs_used": ["cubes"],
    "script_length": 1234,
    "component_errors": [],
    "component_warnings": [],
    "canvas_error_count": 0,
    "canvas_warning_count": 0,
    "unrelated_error_count": 0,
    "unrelated_warning_count": 0
  }
}
```

Error responses also use `{ "success": false, "data": "..." }`, with structured
fields added only when they match existing MCP result conventions.

`check_errors` defaults to `true`. When enabled, the tool must distinguish:

- errors/warnings on the updated component
- total errors/warnings on the whole canvas
- unrelated canvas errors/warnings

This lets agents distinguish "this script failed to compile" from "the canvas
already had unrelated warnings."

## Failure Cases

Fail closed when:

- `guid` is missing.
- `code` is missing.
- target component does not exist.
- target is not a supported script component.
- detected runtime cannot be mapped to Python or C# behavior.
- caller `language` conflicts with detected runtime.
- `body` is requested for unsupported GH1 C#.
- current pins cannot be read for a wrapping mode.
- source preparation fails.
- `/gh/script` write fails.

Failure text should be actionable and should name the intended recovery path:

- "Use `gh_set_script_pins` first, then retry `gh_update_script`."
- "Use `mode: full_source`."
- "Use raw `gh_set_script` for exact source."

## Tool Guidance

The public tool descriptions should make the routing clear:

- `gh_create_script`: create a new RhinoCode Python/C# script with pins and
  source.
- `gh_update_script`: update source on an existing script component; wraps C#
  body code using current pins and checks errors by default.
- `gh_set_script_pins`: change the existing script component interface.
- `gh_set_script`: advanced raw source read/write; no wrapping.

`gh_set_script` documentation should explicitly state that RhinoCode C# callers
must send full source if they use the raw setter.

## Testing

Add Python MCP tests for:

- `gh_update_script` tool registration and schema.
- RhinoCode C# body mode wraps with current pins.
- RhinoCode C# auto mode passes through full source.
- RhinoCode C# wrapper skips the built-in `out` output.
- Caller `language` mismatch fails.
- GH1 C# body mode fails closed.
- Python full source does not add preamble/postamble.
- Python body mode adds preamble/postamble once.
- Existing Rook generated Python sentinels prevent duplicate insertion.
- `check_errors` default true reports component and unrelated canvas counts.
- `check_errors: false` skips `/gh/errors`.
- Result shape is `{ success, data }`.

Live validation should cover at least:

- Existing RhinoCode C# component updated with body code and current pins.
- Same component updated with full `Script_Instance` source.
- Existing RhinoCode Python 3 component updated without duplicate generated
  blocks.
- A deliberate C# compile error returns component-filtered diagnostics plus the
  pin-signature recovery hint.

## Success Criteria

Agents can reliably edit an existing RhinoCode C# Script component by sending
only `RunScript` body code to `gh_update_script`.

Agents no longer need to read the current full C# script only to recover the
`Script_Instance` wrapper format.

Raw source mutation remains available and unchanged through `gh_set_script`.

The interface boundary stays simple:

```text
pins: gh_set_script_pins
prepared source update: gh_update_script
raw source update/read: gh_set_script
new script creation: gh_create_script
```

## Self-Review

- Placeholder scan: no TBD/TODO placeholders.
- Scope check: v1 is code-only and does not include pin edits or GH1 C# body
  wrapping.
- Boundary check: implementation stays in Python MCP orchestration and reuses
  existing companion routes.
- Ambiguity check: `language` only validates detected runtime; it never
  overrides runtime detection.
