# Rook Ecosystem Phase 2A: Vision And Viewport Callback-Unavailable Diagnostics

## Status

Design spec. This document defines the next Phase 2 implementation slice after PR #204. It is not an implementation plan.

This spec authorizes only a future Phase 2A implementation plan after review. It does not authorize code changes, block mutation diagnostics, RookBIM diagnostics, Grasshopper diagnostics, MCP behavior changes, installer/module work, route ownership changes, or companion loading changes.

## Baseline

PR #204 landed Phase 2 Slice 1 at commit `10909ef` and established:

- additive top-level route `diagnostic` object
- fixed v1 `failureKind` enum
- `RouteDiagnostics.h` as a header-only native diagnostic helper
- `CRookServer::SendErrorWithDiagnostic`
- `CRookServer::SendErrorDataWithDiagnostic`
- first reason code: `vision_dispatch_callback_unavailable`
- first adoption: `GET /vision/video/models`

The global Phase 2 invariants remain unchanged:

- `RookNative` is the only public Rhino HTTP/discovery surface.
- `/capabilities` is authoritative live runtime state.
- discovery files are bootstrap/locator metadata only.
- managed companion remains internal.
- current companion loading behavior remains the compatibility baseline.
- route diagnostics are additive only.
- existing `data`, HTTP status, headers, route ownership, callback paths, and availability semantics must be preserved.

## Slice Goal

Phase 2A extends the additive diagnostic contract across native-observed callback-unavailable failures for:

```text
vision.media
viewport.capture
```

This slice aligns only domain-readiness/dependency failures. It does not become a general error rewrite.

## Eligible Failure Points

### Vision

Eligible:

```text
/vision/* unavailable paths that flow through ForwardVisionDispatch
and receive ManagedCreateInvokeResult::Unavailable
```

The implementation should extend diagnostics across `/vision/*` unavailable paths that flow through `ForwardVisionDispatch`, while preserving each route's existing parse, validation, success, and failed-dispatch behavior.

This means only this failure branch is in scope:

```text
ManagedCreateInvokeResult::Unavailable
```

Not in scope:

- JSON parse errors
- non-object body errors
- query parameter validation
- path-id match errors
- managed validation responses
- provider/model/API failures
- credential failures
- video job failures
- callback invocation `Failed`
- ordinary internal exceptions

### Viewport

Eligible:

```text
POST /viewport
captureBackend == "tier3"
InvokeViewportCaptureTier3WithBody returns ManagedCreateInvokeResult::Unavailable
```

Not in scope:

- unknown `captureBackend`
- native/legacy capture path
- no active view
- viewport file/directory failures
- native `_ViewCaptureToFile` failures
- managed callback `Failed`
- successful managed callback responses
- managed-side viewport capture errors after callback dispatch succeeds

## Native-Observed Versus Managed-Observed Facts

Native-observed facts in Phase 2A:

- current route and operation
- whether `vision_dispatch` callback is unavailable
- whether `viewport_capture_tier3` callback is unavailable
- `captureBackend == "tier3"`
- existing response status/header behavior
- existing callback dispatch result category

Managed-observed facts excluded from Phase 2A:

- provider credential state
- provider/model availability
- media artifact store state
- video job state
- managed viewport SDK capture state
- managed validation details
- service health
- Python/runtime dependencies

Phase 2A must not invent managed facts in native diagnostics.

## Reason-Code Catalog Delta

### Existing Reason Code, Expanded Adoption

```text
reasonCode: vision_dispatch_callback_unavailable
failureKind: domain_unavailable
domainId: vision.media
ownedBy: native
evidenceSource: native_callback_registration
emittedBy: native_route
retryableDefault: true
userActionRequiredDefault: false
state: not_loaded
diagnosticRoute: GET /capabilities domain vision.media
```

Phase 2A may expand this reason code from `GET /vision/video/models` to other `/vision/*` routes only where the failure is `ManagedCreateInvokeResult::Unavailable` from `ForwardVisionDispatch`.

### New Reason Code

```text
reasonCode: viewport_capture_callback_unavailable
failureKind: domain_unavailable
domainId: viewport.capture
ownedBy: native
evidenceSource: native_callback_registration
emittedBy: native_route
retryableDefault: true
userActionRequiredDefault: false
state: not_loaded
diagnosticRoute: GET /capabilities domain viewport.capture
```

This reason code may be emitted only for `POST /viewport` when `captureBackend == "tier3"` and `InvokeViewportCaptureTier3WithBody` returns `ManagedCreateInvokeResult::Unavailable`.

## Deferred Block Mutation Safety Boundary

Block mutation is explicitly excluded from Phase 2A.

Block mutation callback absence is not a route failure while `DispatchManagedCompanionRouteOrProxy` can still continue through the managed proxy fallback.

The block mutation fallback exists because native block-definition mutation has a known Rhino crash history. It is architectural safety machinery, not legacy debt.

Future block diagnostics require a separate Phase 2B design with these invariants:

```text
No block mutation route may fail only because the callback is missing
if the managed proxy fallback is still available.

No diagnostic may bypass, reorder, or weaken DispatchManagedCompanionRouteOrProxy.

block_mutation_callback_unavailable may be evidence, but not necessarily the primary failure reason.

The diagnostic is emitted only after the preserved fallback path also cannot satisfy the request.
```

Potential Phase 2B reason codes should be based on final native-observed failure evidence, not callback absence alone. Candidate names are intentionally not locked in Phase 2A, but likely examples include:

```text
block_mutation_managed_proxy_unavailable
block_mutation_managed_proxy_forward_failed
```

Phase 2A source guards should reject block mutation reason codes and should prove `DispatchManagedCompanionRouteOrProxy` remains untouched.

## Explicit Non-Goals

Phase 2A does not include:

- `block.definition_mutation`
- RookBIM
- Grasshopper
- MCP behavior or tool disclosure
- installer/module manifest work
- route ownership changes
- managed public HTTP surface
- companion loading-policy changes
- generic `/capabilities` preflight
- provider API failures
- payload validation failures
- geometry/kernel failures
- ordinary internal exceptions
- product licensing/entitlement behavior

## Response Compatibility Rules

Every adopted failure path must preserve:

- existing legacy `data`
- existing HTTP status
- existing route-specific headers
- existing success behavior
- existing failed-dispatch behavior
- existing route owner
- existing callback path
- existing parse and validation behavior

For vision unavailable paths:

```text
legacy data message remains available
HTTP status remains 503
X-Rook-Vision-Op remains set to the operation
```

For tier3 viewport unavailable path:

```text
legacy data message remains available
HTTP status remains 503
X-Rook-Viewport-Backend remains tier3-unavailable
```

## Validation Gates

### Catalog Gates

The implementation plan should add or update source guards proving:

- `RouteDiagnostics.h` contains `viewport_capture_callback_unavailable`
- `RouteDiagnostics.h` still contains `vision_dispatch_callback_unavailable`
- no block, BIM, or GH reason codes are introduced in Phase 2A
- no broad fallback reason codes are introduced as catalog entries:
  - `bridge_unavailable`
  - `plugin_not_ready`
  - `service_failed`
  - `not_available`
  - `managed_dependency_unavailable`

### Vision Gates

Source guards should prove:

- `/vision/*` adoption is centralized through `ForwardVisionDispatch`
- the diagnostic is emitted only in the `ManagedCreateInvokeResult::Unavailable` branch
- parse/validation failures remain legacy/local
- `ManagedCreateInvokeResult::Failed` remains legacy/local
- each adopted vision route preserves `X-Rook-Vision-Op`
- each adopted vision route preserves status `503` on unavailable
- no route registration changes

### Viewport Gates

Source guards should prove:

- `POST /viewport` tier3 unavailable branch emits `viewport_capture_callback_unavailable`
- the diagnostic is emitted only when `captureBackend == "tier3"` and invoke result is `Unavailable`
- unknown `captureBackend` remains legacy 400
- native/legacy viewport capture path remains unchanged
- `ManagedCreateInvokeResult::Failed` remains legacy/local
- `X-Rook-Viewport-Backend: tier3-unavailable` is preserved
- status `503` is preserved

### Block Safety Gates

Source guards should prove:

- no block mutation reason code is introduced in Phase 2A
- `DispatchManagedCompanionRouteOrProxy` still branches:
  - `callback != nullptr -> DispatchGrasshopperRoute(...)`
  - `callback == nullptr -> ProxyManagedRequest(...)`
- there is no `SendErrorWithDiagnostic` or `SendErrorDataWithDiagnostic` before the proxy fallback in `DispatchManagedCompanionRouteOrProxy`
- managed block mutation handlers still call `DispatchManagedCompanionRouteOrProxy`

### Architecture Gates

Source guards should prove:

- no `.vcxproj` or `.vcxproj.filters` edits
- no installer/module manifest work
- no public managed HTTP surface
- no companion loading-policy changes
- no generic `/capabilities` route preflight
- no route ownership changes
- no MCP behavior/tool-disclosure changes

### Build And Runtime Gates

Minimum validation before PR processing:

- focused managed/source tests for route diagnostics, vision, viewport, block safety, capability discovery, and main-thread dispatcher
- native MSVC 14.44 Debug x64 build
- `git diff --check origin/main...HEAD`

Optional live smoke:

- healthy Rhino session still returns `/ping`
- `/capabilities` still reports expected domains
- `GET /vision/video/models` still succeeds when companion is ready
- `POST /viewport` legacy/native capture still behaves as before
- `POST /viewport` tier3 capture still succeeds when companion is ready and route preconditions are met

The unavailable diagnostic path is primarily source/contract tested because a healthy Rhino session should normally have the managed companion callbacks registered.

## Recommended PR Shape

Implement Phase 2A as one PR:

```text
vision.media + viewport.capture callback-unavailable diagnostics only
```

Do not include block mutation in that PR.

Block mutation should receive its own Phase 2B design and implementation plan after Phase 2A lands and is reviewed.
