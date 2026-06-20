# LM1D: GH Script Post-Mutation Truth And Repair Anchors Design

## Status

Design draft for senior review. This document defines the LM1D slice only. It
must not be treated as approval for PlanGraph, LM2 capability registry work,
ChatRunner event changes, a public MCP wire migration, full compilation, or a
general tool-result ontology.

## Context

LM1A proved that the required local RookChat-visible tools are structurally
dispatchable. LM1B added `ToolResultView` so ChatRunner can consistently
decorate tool events from existing result dictionaries. LM1C added C# script
preflight before Grasshopper mutation.

The next reliability gap is after a GH script create/update mutation has
started. Current results can blur distinct states:

- the script contract passed preflight,
- a component was created or source was written,
- verification ran or did not run,
- target-scoped compile errors were found,
- unrelated canvas errors existed,
- the component is a usable artifact or a repair target.

For sparse/local models, that blur matters. A model repairing a script needs a
compact, stable receipt of what Rook actually did and what the target component
currently reports. LM1D adds that evidence without changing existing coarse
success semantics.

## Goals

- Add a producer-side `data["script_receipt"]` for structured GH script
  create/update results.
- Emit the receipt from the helper boundary where phase transitions are known:
  `_execute_gh_create_script(...)` and `_execute_gh_update_script(...)`.
- Preserve existing top-level `success`, `message`, and legacy `data` fields.
- Represent verification uncertainty explicitly, especially deferred,
  unavailable, and not-requested states.
- Add repair anchors for future repair loops: component identity, language,
  mode, pins, source shape, target diagnostics, and existing recovery hint.
- Cover the unified helper paths for Python and C# while centering tests and
  narrative on C# repair reliability.
- Keep tests deterministic and non-live.

## Non-Goals

- No `gh_set_script` changes.
- No PlanGraph.
- No LM2 capability registry.
- No public MCP wire-shape migration.
- No universal result-envelope redesign.
- No generic result ontology across all tools.
- No Roslyn or full C# compilation.
- No Python preflight, Python wrapper changes, or Python-specific repair
  semantics.
- No output-assignment hard reject.
- No ChatRunner event wiring or prompt behavior change.
- No live Rhino dependency for the first implementation tests.
- No conversion of existing early string failures into dict-shaped envelopes.

## Current Shape Inventory

### Create Path

`mcp_server/src/rook/server.py` contains the unified create helper:

- `_execute_gh_create_script(...)`
- `_gh_create_script_result_from_data(...)`

That helper backs:

- `gh_create_script(language="python" | "csharp", ...)`
- `gh_create_python_script(...)`
- `gh_create_csharp_script(...)`

Current create behavior:

- `success=True` when the component is created, pins are configured, source is
  written, and no target compile errors are detected.
- `success=False` with dict-shaped `data` when the component is created but
  target compile errors are detected.
- `success=False` with string `data` for early validation, preflight, or
  mutation failures.
- `data` currently includes fields such as `component_guid`, `pins_in`,
  `pins_out`, `position`, `name`, `code_length`, and optional
  `compilation_errors` / `warning`.
- If `/gh/errors` fails or returns malformed data, the create path can look too
  much like "no target errors found" because `component_errors` remains empty.

### Update Path

`mcp_server/src/rook/server.py` contains the update helper:

- `_execute_gh_update_script(...)`
- `_gh_update_script_result_from_data(...)`
- `_summarize_gh_update_script_errors(...)`
- `_summarize_gh_update_script_snapshot(...)`
- `_gh_update_script_should_defer(...)`

Current update behavior:

- `success=True` when source is written and no target compile errors are
  detected.
- `success=False` with dict-shaped `data` when source is written but the target
  script component still has compile errors.
- `success=False` with string `data` for early validation, preflight, runtime,
  or write failures.
- Deferred verification flags exist but are flat:
  `verification_deferred`, `verification_note`, `solver_locked`,
  `solver_state_known`, and `solve_scheduled`.
- Verification failure markers exist but are flat:
  `error_check_failed` and `snapshot_check_failed`.
- Repair facts exist only incidentally across fields such as `guid`,
  `target_guid`, `detected_language`, `mode_used`, `wrapped`, `inputs_used`,
  `outputs_used`, `component_errors`, `component_warnings`, and
  `recovery_hint`.

### Problem Statement

Existing top-level `success` remains necessary for compatibility, but it is too
coarse for repair planning. LM1B can classify success/failure for ChatRunner
events, but it cannot expose phase evidence that was never made stable in the
tool payload.

LM1D stabilizes post-mutation GH script evidence before PlanGraph, LM2, or local
repair loops consume it.

## Receipt Emission Boundary

LM1D emits `data["script_receipt"]` only when the helper reaches structured
post-mutation result data shaped by the create/update helper itself. The
boundary is not "any dict": pass-through failures from lower routes remain
unchanged even if their existing `data` happens to be dict-shaped.

Required emission cases:

- Create path after component creation, pin configuration, and script write
  succeed, regardless of whether target verification passes, fails, or is
  unavailable.
- Update path after source write succeeds, regardless of whether target
  verification passes, fails, is deferred, is unavailable, or was not requested.

Unchanged cases:

- Early validation failures that currently return string `data`.
- LM1C preflight failures that currently return string `data`.
- Mutation failures that currently return string `data`, such as component
  creation failure, pin configuration failure, or script injection/write
  failure.
- Generic exception wrappers that currently return string `data`.

The receipt schema reserves `mutation.status="failed"` and
`mutation.status="not_attempted"` for future structured failure coverage, but
LM1D does not need to force receipts onto existing string-failure paths to
exercise those enum values.

## Receipt Contract

The canonical artifact is a plain dict attached additively:

```python
data["script_receipt"] = {
    "version": 1,
    "operation": "create" | "update",
    "language": "csharp" | "python" | "unknown",
    "mutation": {
        "status": "created" | "written" | "failed" | "not_attempted",
        "method": "gh_create_component_then_script" | "gh_script_write",
        "component_guid": "...",
        "note": None,
    },
    "verification": {
        "status": "passed" | "failed" | "deferred" | "unavailable" | "not_requested",
        "method": "gh_errors" | "gh_snapshot_fallback" | "none",
        "target_error_count": 0,
        "target_warning_count": 0,
        "unrelated_error_count": 0,
        "unrelated_warning_count": 0,
        "note": None,
    },
    "artifact_status": (
        "usable"
        | "created_with_errors"
        | "written_with_errors"
        | "verification_pending"
        | "unknown"
    ),
    "repair_anchor": {
        "component_guid": "...",
        "requested_guid": "...",
        "language": "csharp",
        "mode_used": "body",
        "wrapped": True,
        "pins_in": [...],
        "pins_out": [...],
        "source_shape": {
            "input_code_length": 42,
            "prepared_source_length": 938,
            "full_source_detected": False,
        },
        "target_errors": [...] | None,
        "target_warnings": [...] | None,
        "recovery_hint": "...",
    },
}
```

### Version

- `version` is an integer.
- LM1D emits `version == 1`.
- Tests should assert `version == 1`.
- There is no semantic versioning, negotiation, or registry.
- Future incompatible semantic changes increment the version. Additive fields
  can remain on version 1 if they do not alter existing meanings.

### Operation And Language

- `operation` is `"create"` or `"update"`.
- Create language comes from the validated create language/config.
- Update language comes from detected runtime when available.
- Receipts are emitted for both Python and C# on the unified helper paths.
- LM1D acceptance remains C#-centered; Python receipts must not trigger new
  Python preflight or repair behavior.

### Mutation

Create success path:

```python
"mutation": {
    "status": "created",
    "method": "gh_create_component_then_script",
    "component_guid": component_guid,
    "note": None,
}
```

Update success path:

```python
"mutation": {
    "status": "written",
    "method": "gh_script_write",
    "component_guid": resolved_guid,
    "note": None,
}
```

`failed` and `not_attempted` are schema-reserved for later structured failure
coverage.

### Verification

Verification is target-scoped. `passed` means the target script component has no
measured target errors; it does not mean the whole canvas is clean.

Count contract:

```python
target_error_count: int | None
target_warning_count: int | None
unrelated_error_count: int | None
unrelated_warning_count: int | None
```

- Measured absence is `0`.
- Unmeasured or unknown is `None`.
- Warnings are preserved but do not block `artifact_status="usable"`.

Verification status values:

- `passed`: verification check succeeded and found no target errors.
- `failed`: verification check succeeded and found target errors.
- `deferred`: the write/solver path explicitly says verification did not run.
- `unavailable`: the verification route/check failed, returned malformed data,
  or could not be interpreted.
- `not_requested`: the caller intentionally disabled verification, such as
  `check_errors=False`.

Verification precedence:

1. `deferred`
2. `not_requested`
3. `unavailable` from route/snapshot failure or malformed response
4. `failed` from measured target errors
5. `passed` from measured no target errors

`method` means the verification mechanism used or attempted:

- `gh_errors`
- `gh_snapshot_fallback`
- `none`

### Artifact Status

`artifact_status` is derived from mutation/write plus target-scoped
verification. It explains artifact state; it does not override top-level
`success`.

Mapping:

- `usable`: mutation/write succeeded, target verification passed, and measured
  target error count is `0`. Target warnings may exist.
- `created_with_errors`: create succeeded and target errors exist.
- `written_with_errors`: update write succeeded and target errors exist.
- `verification_pending`: mutation/write succeeded, but verification is
  `deferred` or `not_requested`.
- `unknown`: mutation/write succeeded, but verification is `unavailable`.

### Repair Anchor

`repair_anchor` is a repair handle, not a source archive. It carries identity,
pins, mode, source metadata, and target diagnostics. It must not include the
full prepared source text.

Required fields where known:

- `component_guid`
- `requested_guid` for update when it differs from `component_guid` or when
  the caller used a short id
- `language`
- `mode_used`
- `wrapped`
- `pins_in`
- `pins_out`
- `source_shape.input_code_length`
- `source_shape.prepared_source_length`
- `source_shape.full_source_detected`
- `target_errors`
- `target_warnings`
- `recovery_hint`

`target_errors` and `target_warnings` are diagnostic lists when target
diagnostics were measured. They are `None` when verification is deferred,
unavailable, or not requested; unknown diagnostics must not be represented as
empty lists.

For create, `mode_used`, `wrapped`, and `full_source_detected` should reflect
the same source-shape decision used by script preparation. For Python create,
values may use the existing language preparation facts without adding new Python
semantics.

## Helper Module Boundary

Add a small pure module:

`mcp_server/src/rook/gh_script_receipts.py`

Responsibilities:

- Define small constants/literals if useful.
- Build `script_receipt` dicts from facts passed by `server.py`.
- Derive verification status.
- Derive artifact status.
- Build repair anchors.

Constraints:

- Plain functions returning plain dicts.
- No class hierarchy.
- No `call_rhino`.
- No server imports.
- No dispatcher imports.
- No ChatRunner imports.
- Deterministic unit-testable behavior.

`server.py` remains responsible for:

- executing Rhino calls,
- gathering raw facts,
- preserving existing string-vs-dict result boundaries,
- attaching `data["script_receipt"]`.

## Before / After Examples

### Created With Compile Errors

Before:

```python
{
    "success": False,
    "message": "Component was created, but the target script component has compile errors.",
    "data": {
        "message": "Component was created, but the target script component has compile errors.",
        "component_guid": "created-guid",
        "name": "Box Maker",
        "pins_out": [{"name": "B", "type": "Brep"}],
        "compilation_errors": ["Cannot convert Box to Brep"],
    },
}
```

After:

```python
{
    "success": False,
    "message": "Component was created, but the target script component has compile errors.",
    "data": {
        "message": "Component was created, but the target script component has compile errors.",
        "component_guid": "created-guid",
        "name": "Box Maker",
        "pins_out": [{"name": "B", "type": "Brep"}],
        "compilation_errors": ["Cannot convert Box to Brep"],
        "script_receipt": {
            "version": 1,
            "operation": "create",
            "language": "csharp",
            "mutation": {
                "status": "created",
                "method": "gh_create_component_then_script",
                "component_guid": "created-guid",
                "note": None,
            },
            "verification": {
                "status": "failed",
                "method": "gh_errors",
                "target_error_count": 1,
                "target_warning_count": 0,
                "unrelated_error_count": 0,
                "unrelated_warning_count": 0,
                "note": None,
            },
            "artifact_status": "created_with_errors",
            "repair_anchor": {
                "component_guid": "created-guid",
                "language": "csharp",
                "mode_used": "body",
                "wrapped": True,
                "pins_in": [],
                "pins_out": [{"name": "B", "type": "Brep"}],
                "source_shape": {
                    "input_code_length": 14,
                    "prepared_source_length": 900,
                    "full_source_detected": False,
                },
                "target_errors": ["Cannot convert Box to Brep"],
                "target_warnings": [],
                "recovery_hint": None,
            },
        },
    },
}
```

### Update Deferred Because Solver Is Locked

Before:

```python
{
    "success": True,
    "data": {
        "guid": "script-guid",
        "detected_language": "csharp",
        "mode_used": "body",
        "wrapped": True,
        "inputs_used": [],
        "outputs_used": [{"name": "A", "type": "Point3d"}],
        "verification_deferred": True,
        "verification_note": (
            "Grasshopper solver is locked or its state is unknown; the script "
            "source was written but not recompiled. Unlock the solver and run "
            "gh_solve to verify."
        ),
    },
}
```

After:

```python
{
    "success": True,
    "data": {
        "guid": "script-guid",
        "detected_language": "csharp",
        "mode_used": "body",
        "wrapped": True,
        "inputs_used": [],
        "outputs_used": [{"name": "A", "type": "Point3d"}],
        "verification_deferred": True,
        "verification_note": (
            "Grasshopper solver is locked or its state is unknown; the script "
            "source was written but not recompiled. Unlock the solver and run "
            "gh_solve to verify."
        ),
        "script_receipt": {
            "version": 1,
            "operation": "update",
            "language": "csharp",
            "mutation": {
                "status": "written",
                "method": "gh_script_write",
                "component_guid": "script-guid",
                "note": None,
            },
            "verification": {
                "status": "deferred",
                "method": "none",
                "target_error_count": None,
                "target_warning_count": None,
                "unrelated_error_count": None,
                "unrelated_warning_count": None,
                "note": (
                    "Grasshopper solver is locked or its state is unknown; the "
                    "script source was written but not recompiled. Unlock the "
                    "solver and run gh_solve to verify."
                ),
            },
            "artifact_status": "verification_pending",
            "repair_anchor": {
                "component_guid": "script-guid",
                "language": "csharp",
                "mode_used": "body",
                "wrapped": True,
                "pins_in": [],
                "pins_out": [{"name": "A", "type": "Point3d"}],
                "source_shape": {
                    "input_code_length": 19,
                    "prepared_source_length": 930,
                    "full_source_detected": False,
                },
                "target_errors": None,
                "target_warnings": None,
                "recovery_hint": None,
            },
        },
    },
}
```

### Verification Unavailable

Before:

```python
{
    "success": True,
    "data": {
        "component_guid": "created-guid",
        "pins_in": [],
        "pins_out": [{"name": "B", "type": "Brep"}],
        "name": "Box Maker",
        "code_length": 900,
    },
}
```

After:

```python
{
    "success": True,
    "data": {
        "component_guid": "created-guid",
        "pins_in": [],
        "pins_out": [{"name": "B", "type": "Brep"}],
        "name": "Box Maker",
        "code_length": 900,
        "script_receipt": {
            "version": 1,
            "operation": "create",
            "language": "csharp",
            "mutation": {
                "status": "created",
                "method": "gh_create_component_then_script",
                "component_guid": "created-guid",
                "note": None,
            },
            "verification": {
                "status": "unavailable",
                "method": "gh_errors",
                "target_error_count": None,
                "target_warning_count": None,
                "unrelated_error_count": None,
                "unrelated_warning_count": None,
                "note": "/gh/errors failed or returned malformed data; target compile state is unknown.",
            },
            "artifact_status": "unknown",
            "repair_anchor": {
                "component_guid": "created-guid",
                "language": "csharp",
                "mode_used": "body",
                "wrapped": True,
                "pins_in": [],
                "pins_out": [{"name": "B", "type": "Brep"}],
                "source_shape": {
                    "input_code_length": 14,
                    "prepared_source_length": 900,
                    "full_source_detected": False,
                },
                "target_errors": None,
                "target_warnings": None,
                "recovery_hint": None,
            },
        },
    },
}
```

## Test Strategy

Non-live tests should cover:

- Pure receipt helper unit tests:
  - `version == 1`.
  - measured no errors yields `verification.status == "passed"` and integer
    zero counts.
  - measured target errors yield `verification.status == "failed"`.
  - deferred beats route interpretation and uses `None` counts.
  - not-requested beats measured interpretation when checks are disabled.
  - route/snapshot failure yields `verification.status == "unavailable"` and
    `None` counts.
  - `artifact_status` derivation for usable, created-with-errors,
    written-with-errors, verification-pending, and unknown.
  - warnings do not block `artifact_status == "usable"`.
- Create helper tests:
  - C# compile-error result keeps old fields and adds receipt.
  - Create `/gh/errors` failure or malformed response keeps top-level
    `success=True` but emits `verification.status == "unavailable"` and
    `artifact_status == "unknown"`.
  - Python create structured path receives a receipt without Python-specific
    repair expansion.
- Update helper tests:
  - C# compile-error result keeps old fields, top-level `success=False`, and
    adds receipt with `artifact_status == "written_with_errors"`.
  - Deferred verification emits `verification.status == "deferred"` with
    `None` counts.
  - `check_errors=False` emits `verification.status == "not_requested"`.
  - `error_check_failed` emits `verification.status == "unavailable"` with
    method `gh_errors`.
  - `snapshot_check_failed` after fallback emits
    `verification.status == "unavailable"` with method
    `gh_snapshot_fallback`.
  - `requested_guid` appears only when the caller's id differs from the
    resolved component id or the caller used a short id.
- Compatibility tests:
  - old dict fields remain present.
  - compile-error cases still produce top-level `success=False`.
  - `normalize_tool_result(...)` still classifies existing top-level truth
    correctly.
  - early string-failure paths remain string-shaped and do not acquire
    receipts.

## Acceptance Criteria

- `script_receipt` is emitted on structured post-mutation create/update paths.
- Existing coarse `success` behavior is preserved.
- Existing old fields remain present.
- Verification unavailable/deferred/not-requested states are explicit and do
  not collapse to zero-error success.
- Unknown counts are `None`; measured absence is `0`.
- Repair anchors contain identity, pins, mode, source shape, target diagnostics,
  and recovery hint without full prepared source text.
- No `gh_set_script` behavior changes.
- No ChatRunner behavior changes.
- No live Rhino dependency for the first implementation tests.

## Implementation Notes For The Later Plan

The implementation plan should start with pure helper tests and helper
implementation, then wire create/update result attachment, then add
non-live server-helper tests and compatibility checks. It should not begin with
server wiring.

Stop for senior review before writing that plan.
