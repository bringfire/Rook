# Rook Ecosystem Phase 2C: RookBIM / Rhino.Inside.Revit Diagnostics

## Status

Draft design spec for review.

This document defines the next Phase 2 diagnostics slice after Phase 2B block
mutation terminal proxy diagnostics. It authorizes design review only. It does
not authorize implementation or an implementation plan.

## Background

Phase 1 made `GET /capabilities` the authoritative live runtime capability
surface. Discovery files remain locator/bootstrap metadata only.

Phase 2 introduced additive route diagnostics for domain readiness and
dependency failures. Route diagnostics must preserve existing response behavior:
legacy `data`, HTTP status codes, headers, route ownership, callback paths, and
availability semantics.

Earlier Phase 2 slices adopted this contract for:

- `vision.media` callback-unavailable failures;
- `viewport.capture` tier-3 callback-unavailable failures;
- terminal native proxy failures for `block.definition_mutation`.

Phase 2C aligns the first-class non-GH BIM domain:

```text
bim.rhino_inside_revit
```

This slice is deliberately separate from Grasshopper. BIM has different host,
module, Revit API, active-document, and runtime evidence boundaries.

## Current BIM Route Architecture

`RookNative` remains the only public Rhino HTTP/discovery surface. Public BIM
routes are registered by native:

- `GET /bim/status`
- `GET /bim/active-document`
- `GET /bim/categories`
- `POST /bim/query-elements`
- `POST /bim/element-info`
- `POST /bim/element-parameters`
- `POST /bim/select-elements`
- `POST /bim/clear-selection`

Native BIM route flow:

```text
RookNative /bim/*
  -> native injects canonical op
  -> InvokeBimDispatchWithBody(...)
  -> managed bim_dispatch callback
  -> NativeGhBridgeRegistrar.ExecuteBimDispatchCallback(...)
  -> managed BimHandler.Dispatch(...)
  -> RookBimModuleLoader.TryActivate()
  -> RookBimRuntimeRegistry.Current
  -> optional RookBim.dll / Revit runtime
```

Native owns route registration, route/op context, callback registration
evidence, and HTTP transport headers. Managed/RookBIM owns module activation,
RookBIM runtime registry evidence, host/runtime evidence, Revit API dispatch,
active document state, and BIM operation results.

## Phase 2C Goal

Make BIM readiness, host-state, module-state, and active-document failures speak
the same `bim.rhino_inside_revit` diagnostic language exposed by
`/capabilities`, without changing route behavior or route ownership.

Phase 2C answers:

```text
When a /bim/* route fails because BIM is not ready, host-blocked,
not activated, missing its runtime module, failed to load its runtime module,
or lacks an active Revit document, does the route expose a precise additive
diagnostic?
```

Phase 2C does not answer every BIM operation failure. It is still a
readiness/dependency diagnostic slice, not a general BIM error taxonomy.

## Sub-Slice Shape

Phase 2C should be implemented later as two separately reviewable sub-slices
under this design.

### 2C-A: Native Callback-Unavailable Diagnostic

Native may emit only:

```text
bim_dispatch_callback_unavailable
```

Allowed evidence:

```text
registration.bim_dispatch == nullptr
route/op context from /bim/*
```

Native must not claim:

- `not_rhino_inside`;
- RookBIM module missing or load failure;
- Revit API state;
- active Revit document state;
- RookBIM runtime state.

Native successful callback dispatch remains opaque pass-through:

```text
res.status = statusCode
res.set_content(responseJson, "application/json")
res.set_header("X-Rook-Bim-Op", op)
```

Native must not parse `responseJson`, add diagnostics, rewrite managed
diagnostics, or inspect managed BIM error bodies after successful callback
dispatch.

### 2C-B: Managed / RookBIM Readiness Diagnostics

Managed `BimHandler` may add top-level `diagnostic` only for existing
readiness, host, module, and active-document codes that are already proven by
RookBIM runtime or module-loader evidence.

Allowed Phase 2C managed/RookBIM diagnostic reason codes:

```text
not_rhino_inside
rookbim_runtime_not_activated
rookbim_module_not_found
rookbim_module_load_failed
no_active_document
```

`BimHandler` may translate existing RookBIM/runtime readiness error codes into
diagnostics. It must not infer deeper Revit state than the runtime response or
module loader source proves.

## Explicit Non-Goals

Phase 2C does not:

- change route ownership;
- change route registration;
- change companion loading policy;
- add a public managed HTTP surface;
- add installer or module manifest work;
- add a `/capabilities` route preflight;
- move Revit API references into `src/Rook`;
- add native Revit API references;
- make native infer RookBIM module, Revit API, or active-document state;
- change MCP behavior or tool disclosure;
- add Grasshopper diagnostics;
- add broad `bim_unavailable`, `bridge_unavailable`, or
  `managed_dependency_unavailable` diagnostic reason codes;
- introduce a general BIM operation error taxonomy.

## Legacy Data Compatibility

`rookbim_unavailable` already exists as a managed legacy `data.errorCode`.

Phase 2C must preserve it where existing code emits it. It is not a Phase 2C
`diagnostic.reasonCode`.

This distinction is important:

```text
legacy data.errorCode may remain broad for compatibility
diagnostic.reasonCode must be reviewed, specific, and evidence-backed
```

Existing legacy payload fields, HTTP status codes, and `X-Rook-Bim-Op` headers
remain available.

## Reason-Code Catalog Delta

### `bim_dispatch_callback_unavailable`

```text
domainId: bim.rhino_inside_revit
failureKind: domain_unavailable
ownedBy: native
evidenceSource: native_callback_registration
emittedBy: native_route
retryable: true
userActionRequired: false
state: not_loaded
```

Allowed only when native observes:

```text
registration.bim_dispatch == nullptr
```

`state: not_loaded` is allowed only for this native callback-unavailable case
because `/capabilities` already uses `not_loaded` for missing `bim_dispatch`.

### `not_rhino_inside`

```text
domainId: bim.rhino_inside_revit
failureKind: host_blocked
ownedBy: rookbim
evidenceSource: rookbim_host_runtime
emittedBy: managed_route
retryable: false
userActionRequired: true
state: omitted
```

Allowed when the RookBIM runtime/module reports the existing
`not_rhino_inside` code.

### `rookbim_runtime_not_activated`

```text
domainId: bim.rhino_inside_revit
failureKind: dependency_unavailable
ownedBy: managed
evidenceSource: managed_rookbim_runtime_registry
emittedBy: managed_route
retryable: true
userActionRequired: false
state: omitted
```

Allowed when existing runtime registry evidence proves:

```text
RookBimRuntimeRegistry.Source == "core-fallback"
```

This reason is based on registry source, not the legacy runtime's broad
`rookbim_unavailable` error code.

### `rookbim_module_not_found`

```text
domainId: bim.rhino_inside_revit
failureKind: dependency_unavailable
ownedBy: managed
evidenceSource: managed_rookbim_module_loader
emittedBy: managed_route
retryable: false
userActionRequired: true
state: omitted
```

Allowed when existing loader evidence is:

```text
RookBimRuntimeRegistry.Source == "module-not-found"
```

This is module-loader runtime evidence. It is not an installer manifest or
`module_not_installed` claim.

### `rookbim_module_load_failed`

```text
domainId: bim.rhino_inside_revit
failureKind: dependency_degraded
ownedBy: managed
evidenceSource: managed_rookbim_module_loader
emittedBy: managed_route
retryable: true
userActionRequired: true
state: omitted
```

Allowed when existing loader evidence is:

```text
RookBimRuntimeRegistry.Source == "module-load-failed"
```

### `no_active_document`

```text
domainId: bim.rhino_inside_revit
failureKind: operation_unavailable
ownedBy: rookbim
evidenceSource: rookbim_revit_runtime
emittedBy: managed_route
retryable: true
userActionRequired: true
state: omitted
```

Allowed only when the RookBIM runtime response supplies `no_active_document`.
`BimHandler` may translate that existing runtime error code into a diagnostic,
but it must not independently infer Revit document state.

## Ownership Semantics

`ownedBy` and `emittedBy` are intentionally distinct:

```text
ownedBy: who proves the fact
emittedBy: which layer serializes the diagnostic into the route response
```

For example, `not_rhino_inside` may be:

```text
ownedBy: rookbim
emittedBy: managed_route
```

only when `BimHandler` is translating an error code returned by the RookBIM
runtime/module. `BimHandler` is not the evidence owner for Revit host or active
document facts.

## Codes Excluded As Phase 2C Diagnostic Reason Codes

The following are excluded as Phase 2C `diagnostic.reasonCode` values:

```text
rookbim_unavailable
bim_unavailable
bridge_unavailable
managed_dependency_unavailable
rookbim_module_not_activated
no_active_revit_document
missing_revit_api
revit_unavailable
invalid_scope
unbounded_document_query
invalid_category
ambiguous_category
element_not_found
document_mismatch
linked_element_unsupported
selection_failed
internal_error
```

Some of these may still appear as legacy `data.errorCode` values until a later
reviewed slice maps them. Phase 2C must not delete or rename existing legacy
payloads.

`missing_revit_api` is excluded because current RookBIM activation checks
`RevitAPIUI` and `RhinoInside.Revit` together and emits `not_rhino_inside`. A
separate `missing_revit_api` diagnostic can be reconsidered only if RookBIM
exposes direct evidence distinct from `not_rhino_inside`.

## Response Behavior

### Native Callback-Unavailable Response

When native cannot invoke `bim_dispatch`, the existing payload shape is
preserved and `diagnostic` is added as a top-level sibling:

```json
{
  "success": false,
  "data": {
    "errorCode": "rookbim_unavailable",
    "message": "BIM dispatch callback is not registered."
  },
  "diagnostic": {
    "schemaVersion": 1,
    "domainId": "bim.rhino_inside_revit",
    "route": "GET /bim/status",
    "operation": "status",
    "reasonCode": "bim_dispatch_callback_unavailable",
    "failureKind": "domain_unavailable",
    "state": "not_loaded",
    "retryable": true,
    "userActionRequired": false,
    "diagnosticRoute": {
      "method": "GET",
      "path": "/capabilities",
      "domainId": "bim.rhino_inside_revit"
    },
    "ownedBy": "native",
    "evidenceSource": "native_callback_registration",
    "emittedBy": "native_route"
  }
}
```

Compatibility requirements:

- preserve existing `data.errorCode = "rookbim_unavailable"`;
- preserve existing message;
- preserve existing HTTP `503`;
- preserve `X-Rook-Bim-Op`;
- add only top-level `diagnostic`.

### Native Branches That Stay Legacy

`ForwardBimDispatch` currently has separate result branches. Phase 2C maps only
one:

```text
ManagedCreateInvokeResult::Unavailable -> add bim_dispatch_callback_unavailable diagnostic
ManagedCreateInvokeResult::Failed -> keep legacy/local internal_error, no Phase 2C diagnostic
ManagedCreateInvokeResult::Ok -> opaque pass-through, no native response inspection
```

Native parse/body failures also stay legacy/local. `ParseBimPostBody` currently
emits `invalid_scope` before `InvokeBimDispatchWithBody` is called. Phase 2C
must not add diagnostics to those parse failures.

### Managed Response Behavior

When `BimHandler` receives existing readiness, host, module, or document
evidence from runtime or registry state, it may return:

```json
{
  "success": false,
  "data": {
    "errorCode": "not_rhino_inside",
    "message": "RookBIM requires RhinoInside.Revit and RevitAPIUI to be loaded."
  },
  "diagnostic": {
    "schemaVersion": 1,
    "domainId": "bim.rhino_inside_revit",
    "route": "GET /bim/status",
    "operation": "status",
    "reasonCode": "not_rhino_inside",
    "failureKind": "host_blocked",
    "retryable": false,
    "userActionRequired": true,
    "diagnosticRoute": {
      "method": "GET",
      "path": "/capabilities",
      "domainId": "bim.rhino_inside_revit"
    },
    "ownedBy": "rookbim",
    "evidenceSource": "rookbim_host_runtime",
    "emittedBy": "managed_route"
  }
}
```

Compatibility requirements:

- preserve existing `success`;
- preserve existing `data` object shape;
- preserve existing `data.errorCode`;
- preserve existing HTTP status;
- add only top-level `diagnostic` for reviewed Phase 2C readiness codes;
- do not add diagnostics to parse, validation, or operation taxonomy errors.

## Managed Serialization Path

Current managed BIM dispatch manually serializes only:

```csharp
new
{
    success = result.Success,
    data = result.Data,
}
```

Phase 2C-B must add an explicit managed route-diagnostic serialization path.

Recommended implementation shape for a later plan:

```text
Add optional ApiResponse.Diagnostic.
Teach only ExecuteBimDispatchCallback to include diagnostic when non-null.
```

Alternative acceptable shape:

```text
Keep ApiResponse unchanged.
Add a BIM-specific response envelope builder that emits success/data/diagnostic.
```

The recommended shape is better for long-term Phase 2 consistency, but it must
not broaden response-shape changes in Phase 2C.

Hard guard:

```text
Only ExecuteBimDispatchCallback serializes ApiResponse.Diagnostic in Phase 2C.
ExecuteApiResponseCallback, ExecuteAsyncApiResponseCallback, and
ExecuteOffUiApiResponseCallback do not start emitting diagnostic.
```

`ApiResponse.Diagnostic` must be optional and must not affect
`MapBridgeStatus`.

## Managed Translation Rule

`BimHandler` may translate existing RookBIM/runtime readiness error codes into
diagnostics. It must not infer deeper Revit state than the runtime response or
module loader source proves.

Allowed examples:

- runtime response says `not_rhino_inside` -> add `not_rhino_inside`
  diagnostic;
- runtime response says `no_active_document` -> add `no_active_document`
  diagnostic;
- registry source is `core-fallback` -> add
  `rookbim_runtime_not_activated` diagnostic;
- registry source is `module-not-found` -> add `rookbim_module_not_found`
  diagnostic;
- registry source is `module-load-failed` -> add `rookbim_module_load_failed`
  diagnostic.

Disallowed examples:

- request validation says `invalid_scope` -> no Phase 2C diagnostic;
- query returns `invalid_category` -> no Phase 2C diagnostic;
- element lookup returns `element_not_found` -> no Phase 2C diagnostic;
- managed exception maps to `internal_error` -> no Phase 2C diagnostic;
- native sees successful callback dispatch and parses response to add a
  diagnostic -> forbidden.

## Source Guard Requirements

### Native Guards

The later implementation plan should require source guards proving:

- `RouteDiagnostics.h` adds only the reviewed Phase 2C native BIM helper needed
  for `bim_dispatch_callback_unavailable`;
- native callback-unavailable branch emits `diagnostic` only when
  `InvokeBimDispatchWithBody` returns `Unavailable`;
- native `ManagedCreateInvokeResult::Failed` remains legacy/local
  `internal_error` without Phase 2C diagnostics;
- native parse/body `invalid_scope` failures remain legacy/local without Phase
  2C diagnostics;
- native successful BIM callback dispatch remains opaque pass-through:
  - no `nlohmann::json::parse(responseJson)`;
  - no inspection of `data.errorCode`;
  - no managed/RookBIM reason-code mapping in C++;
- `X-Rook-Bim-Op` remains preserved;
- HTTP `503` remains preserved for native callback-unavailable;
- existing legacy `data.errorCode = "rookbim_unavailable"` remains preserved;
- no `/capabilities` preflight appears in BIM dispatch;
- native BIM dispatch does not reference `BimHandler`, `RookBim`, `Autodesk`,
  `RevitAPI`, or `RhinoInside.Revit`.

### Managed Guards

The later implementation plan should require source guards proving:

- `ApiResponse.Diagnostic` is optional if that implementation shape is used;
- only `ExecuteBimDispatchCallback` serializes `diagnostic` in Phase 2C;
- `ExecuteApiResponseCallback`, `ExecuteAsyncApiResponseCallback`, and
  `ExecuteOffUiApiResponseCallback` do not start emitting `diagnostic`;
- `MapBridgeStatus` remains based on
  `HttpStatus ?? (Success ? 200 : 400)` and does not inspect diagnostics;
- `BimHandler` only adds diagnostics for reviewed Phase 2C codes:
  - `not_rhino_inside`;
  - `rookbim_runtime_not_activated`;
  - `rookbim_module_not_found`;
  - `rookbim_module_load_failed`;
  - `no_active_document`;
- `BimHandler` does not add diagnostics for operation or validation codes:
  - `invalid_scope`;
  - `unbounded_document_query`;
  - `invalid_category`;
  - `ambiguous_category`;
  - `element_not_found`;
  - `document_mismatch`;
  - `linked_element_unsupported`;
  - `selection_failed`;
  - `internal_error`;
- `rookbim_unavailable` remains legacy `data.errorCode` only and is not a
  diagnostic reason code;
- `BimHandler` does not infer active document or Revit API state independently
  of runtime response/module loader evidence.

### Boundary Guards

The later implementation plan should require source guards proving:

- `src/Rook` still has no Autodesk/Revit references;
- Revit API references remain isolated to `src/RookBim`;
- no `.vcxproj` or `.vcxproj.filters` changes;
- no route registration changes;
- no companion loading changes;
- no installer/module manifest work;
- no MCP behavior or tool-disclosure changes.

## Validation Gates

### Automated Validation

Required before PR processing:

- focused native BIM dispatch source tests;
- route diagnostics catalog/source tests;
- managed `BimHandler` tests for allowed readiness diagnostics;
- managed `BimHandler` tests proving validation/operation errors remain
  legacy/local;
- managed bridge serialization tests proving only BIM dispatch emits top-level
  `diagnostic`;
- RookBIM boundary tests proving Revit API references remain isolated to
  `src/RookBim`;
- `git diff --check origin/main...HEAD`;
- native MSVC 14.44 Debug x64 build if native code changes.

### Live Validation

Standalone Rhino:

- `/ping` works;
- `/capabilities` returns schemaVersion 1 and the expected domain inventory;
- when the managed callback is registered in standalone Rhino, `/capabilities`
  reports `bim.rhino_inside_revit` as `blocked_by_host` with
  `not_rhino_inside`;
- `GET /bim/status` returns the existing BIM status payload plus top-level
  `diagnostic.reasonCode = not_rhino_inside`, when RookBIM module evidence is
  available;
- existing HTTP status and `X-Rook-Bim-Op` behavior remain stable.

Rhino.Inside/Revit, if available for this slice:

- `/bim/status` works;
- with active document, readiness routes succeed and have no failure diagnostic;
- without active document, if safely reproducible, a route returns existing
  `no_active_document` payload plus top-level diagnostic.

If Rhino.Inside/Revit is not available during PR validation, source/managed
tests plus standalone Rhino live `not_rhino_inside` validation are acceptable.
Revit live validation should remain listed as a later confidence gate.

## Review Checklist

Before approving a Phase 2C implementation plan, reviewers should confirm:

- the plan keeps native and RookBIM evidence boundaries separate;
- native emits only native-observed BIM diagnostics;
- managed/RookBIM emits only diagnostics backed by existing runtime or module
  evidence;
- `rookbim_unavailable` remains legacy data only;
- no new alias vocabulary is introduced without updating `/capabilities`,
  tests, and docs consistently;
- native successful callback dispatch remains opaque;
- managed diagnostic serialization is BIM-only in this slice;
- validation/operation BIM errors remain legacy/local;
- no Revit API references move into `src/Rook` or native;
- no route ownership, loading policy, installer, MCP behavior, or public
  managed HTTP changes are introduced.

## Next Authorized Artifact

After this design is reviewed and approved, the next artifact should be a Phase
2C implementation plan only.

Do not write code from this spec until a reviewed implementation plan exists.
