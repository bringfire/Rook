# Rook Ecosystem Phase 2: Domain Diagnostics And Route Error Alignment

## Status

Design spec. This document defines the Phase 2 architecture boundary and review standard. It is not an implementation plan.

Phase 2 implementation plans may be written from this spec after this document is reviewed. The first implementation plan should target only Slice 1: Contract, shared diagnostic helper, catalog tests, and one minimal route adoption.

## Related Documents

- `docs/CURRENT_ARCHITECTURE.md`
- `docs/superpowers/specs/2026-05-31-rook-ecosystem-architecture-roadmap.md`
- `docs/superpowers/specs/2026-05-31-rook-ecosystem-master-decomposition-design.md`
- `docs/superpowers/plans/2026-05-31-rook-ecosystem-phase-1-capability-discovery.md`

## Phase 1 Baseline

Phase 1 established Rook's live runtime capability surface:

- `RookNative` remains the only public Rhino HTTP and discovery surface.
- Discovery files are locator and bootstrap metadata only.
- `GET /capabilities` is the authoritative live runtime capability state.
- MCP resolves live `/capabilities` first and uses discovery summaries only as stale, non-authoritative fallback.
- Managed companion remains internal.
- Managed companion evidence is surfaced through native `/capabilities`.
- Current deferred/eager companion loading remains the compatibility baseline.
- The recent-file `_Open` companion-load stabilization preserves startup safety.

Phase 1 answers:

```text
What domains exist?
Which domains are ready, unavailable, blocked, degraded, or unknown?
What evidence supports that state?
```

Phase 2 answers:

```text
When a route fails because of domain readiness or dependency state,
does the route failure speak the same domain language?
```

## Problem Statement

Some route failures still expose older local language:

```text
bridge unavailable
requires companion plugin
dispatch failed
not available
```

Those messages are not precise enough for external LLM clients, MCP tools, support diagnostics, or future product surfaces. A failure should identify the relevant domain, reason, retryability, diagnostic route, and recommended next step when the failure is caused by domain readiness or dependency state.

Phase 2 aligns route failures with the Phase 1 domain model without changing current route behavior.

## Phase 2 Scope

Phase 2 v1 covers route failures caused by:

- domain readiness state
- host state
- managed companion dependency state
- callback or dispatch availability
- known runtime dependency state
- known configuration or authorization dependency state, when already observed by the route family

Phase 2 v1 does not automatically cover every failure. The following remain legacy/local unless a later Phase 2 slice explicitly maps them:

- syntax and parse errors
- payload validation failures
- invalid object IDs
- geometry or kernel failures
- provider API failures after a provider call is made
- ordinary internal exceptions
- licensing and entitlement behavior
- installer/module-not-installed claims

The boundary is intentional. Phase 2 starts with domain-readiness and dependency failures. It does not become a general error framework in the first pass.

## Non-Goals

Phase 2 does not authorize:

- route ownership changes
- managed companion loading-policy changes
- on-demand companion or domain loading changes
- installer/module manifest work
- module path reorganization
- new public managed HTTP surface
- broad handler rewrites
- generic route preflight through `/capabilities`
- replacing live `/capabilities` as the runtime truth
- MCP minting Rhino-domain runtime reason codes
- claiming installer evidence that does not exist yet

## Additive Route Diagnostic Contract

Phase 2 introduces an additive top-level `diagnostic` object on compatible route failures.

Existing route response shape must be preserved. If a route currently returns the standard error envelope:

```json
{
  "success": false,
  "data": "Vision routes require the Rook companion plugin..."
}
```

then Phase 2 may add:

```json
{
  "success": false,
  "data": "Vision routes require the Rook companion plugin...",
  "diagnostic": {
    "schemaVersion": 1,
    "domainId": "vision.media",
    "route": "POST /vision/generate",
    "operation": "image_generation",
    "reasonCode": "vision_dispatch_callback_unavailable",
    "failureKind": "domain_unavailable",
    "state": "not_loaded",
    "retryable": true,
    "userActionRequired": false,
    "diagnosticRoute": {
      "method": "GET",
      "path": "/capabilities",
      "domainId": "vision.media"
    },
    "recommendedNextStep": "Wait for companion startup, then retry. If it remains unavailable, inspect /capabilities."
  }
}
```

Rules:

- `diagnostic` is additive and client-optional.
- `diagnostic.schemaVersion` is independent from `/capabilities.schemaVersion`. Both may start at `1`, but they describe different contracts and may evolve separately.
- Existing `data` remains available.
- Existing HTTP status is preserved where already established.
- Existing success/failure conditions are preserved.
- Existing route owner is preserved.
- Existing callback dispatch path is preserved.
- Existing managed/native boundary is preserved.
- `legacyMessage` is optional and should be used only when `data` is not already the legacy string or when mapping a legacy managed error object.
- `state` is included only when derived from the same local evidence that caused the route failure.
- If the route does not know live state, it must omit `state` and rely on `failureKind` plus `reasonCode`.
- `diagnosticRoute` is structured. URL fragments such as `/capabilities#vision.media` are not a route contract.
- If a route cannot safely add `diagnostic` without changing response shape, defer that route.

## Failure Kind Enum

`failureKind` is a small fixed v1 enum. It is the coarse machine-action bucket.

Allowed v1 values:

```text
domain_unavailable
host_blocked
dependency_unavailable
dependency_degraded
operation_unavailable
configuration_required
authorization_required
unknown
```

Rules:

- `failureKind` must be stable and client-actionable.
- `failureKind` must not become domain-specific.
- `reasonCode` carries domain-specific detail.
- Do not add `internal_error` in v1 unless a later reviewed slice intentionally brings ordinary server failures into scope.
- Provider and credential cases should usually map to `configuration_required`, `authorization_required`, or `dependency_degraded` with a specific `reasonCode`.
- `authorization_required` means already-observed provider, service, or credential authorization state. It does not mean Rook product licensing or entitlement; licensing remains out of scope until that domain is explicitly implemented.

## Reason-Code Catalog

`reasonCode` is the domain-specific explanation under the fixed `failureKind`.

Example codes:

```text
vision_dispatch_callback_unavailable
viewport_capture_callback_unavailable
block_mutation_callback_unavailable
bim_dispatch_callback_unavailable
not_rhino_inside
rookbim_module_not_found
vision_credentials_missing
gh_canvas_not_available
```

Every new reason code must declare:

```text
reasonCode
failureKind
domainId
ownedBy
evidenceSource
emittedBy
retryableDefault
userActionRequiredDefault
recommendedNextStep
diagnosticRoute
```

Allowed `ownedBy` values:

```text
native
managed
rookbim
mcp_client
```

`ownedBy`, `evidenceSource`, and `emittedBy` are distinct:

```text
ownedBy: who owns the meaning of the reason code
evidenceSource: where the proof came from
emittedBy: which layer emitted the diagnostic object
```

Example:

```text
reasonCode: not_rhino_inside
failureKind: host_blocked
domainId: bim.rhino_inside_revit
ownedBy: native
evidenceSource: native_host_state
emittedBy: native_route
retryableDefault: false
userActionRequiredDefault: true
recommendedNextStep: Open Rhino through Rhino.Inside.Revit, then retry.
diagnosticRoute: GET /capabilities domain bim.rhino_inside_revit
```

Another BIM example may be owned by `rookbim` if the evidence comes from RookBIM runtime code rather than native host state.

## Reviewed Catalog Location

The reason-code catalog is a reviewed design and test contract. It is not runtime truth.

Runtime truth comes from real evidence at the route, capability, managed companion, RookBIM, or MCP transport layer. The catalog documents which codes are allowed, what they mean, who owns them, and what evidence is required before they may be emitted.

Implementation slices may mirror catalog entries as constants or helpers, but the first Phase 2 work should not introduce a full shared runtime registry.

## Evidence Rules

Diagnostics must be emitted from real evidence:

- callback registration state
- companion dispatch result
- managed companion status evidence
- RookBIM runtime evidence
- native host state
- route-local operation availability
- provider, credential, or service checks already performed by the owning layer
- MCP transport failures for MCP-owned codes only

Diagnostics must not be emitted from:

- bootstrap discovery summaries
- speculative installer assumptions
- broad route-family assumptions
- generic `/capabilities` preflight sweeps
- hand-maintained readiness duplicates

A route may preserve a downstream diagnostic if it identifies the downstream owner and does not rewrite the downstream `reasonCode` as its own evidence.

## Anti-Drift Rules

The following should be review blockers:

- vague broad reason codes used as primary codes
- reason codes without catalog metadata
- reason codes that merely duplicate `failureKind`
- MCP-minted Rhino-domain runtime reason codes
- route diagnostics that claim live domain state without local evidence
- diagnostics that replace legacy route payloads instead of adding to them

Avoid broad replacement codes:

```text
bridge_unavailable
plugin_not_ready
service_failed
not_available
```

Source guards should reject those values as reason codes or catalog entries, not as arbitrary legacy message text. Existing route messages may legitimately contain broad words while the additive diagnostic contract is being introduced.

`managed_dependency_unavailable` may exist only as a family fallback. When a specific callback or dependency is known, use the specific reason code instead:

```text
vision_dispatch_callback_unavailable
viewport_capture_callback_unavailable
block_mutation_callback_unavailable
```

## Adoption Slices

### Slice 1: Contract, Helper, Catalog, And One Example Adoption

Purpose:

```text
Establish the diagnostic response shape, fixed failureKind enum,
reason-code catalog rules, source guards, and one minimal route adoption.
```

Allowed:

- additive native diagnostic helper
- fixed `failureKind` enum
- reason-code catalog documentation
- source/contract tests for schema and anti-drift rules
- one tiny, low-risk route adoption where callback-missing already returns a legacy unavailable message

The example adoption should be the smallest existing failure path with a stable legacy message and no Rhino document mutation.

Not allowed:

- broad route rewrites
- new route registration
- route movement between native and managed
- callback signature changes
- managed public HTTP
- installer changes
- loading-policy changes
- generic `/capabilities` route preflight

### Slice 2: Companion-Backed Native Routes

Primary domains:

```text
vision.media
viewport.capture
block.definition_mutation
```

Mapped failures:

```text
vision_dispatch_callback_unavailable
viewport_capture_callback_unavailable
block_mutation_callback_unavailable
```

Keep legacy/local for now:

- bad payloads
- invalid object IDs
- geometry conversion errors
- provider API failures
- vision operation errors after dispatch reaches managed code
- viewport capture failures after callback succeeds

### Slice 3: RookBIM

Primary domain:

```text
bim.rhino_inside_revit
```

Mapped failures, only where evidence already exists:

```text
not_rhino_inside
bim_dispatch_callback_unavailable
rookbim_module_not_activated
rookbim_module_not_found
rookbim_module_load_failed
no_active_revit_document
missing_revit_api
```

Rules:

- RookBIM is early but separate.
- Revit API references remain isolated to `src/RookBim`.
- Native may emit native-observed host or callback facts.
- Native may preserve downstream RookBIM diagnostics.
- Native must not invent deeper Revit state it did not observe.
- `rookbim_module_not_found` must come from existing runtime evidence, not install assumptions.

### Slice 4: Grasshopper

Primary domains:

```text
gh.bridge
gh.canvas
```

Mapped failures:

```text
gh_bridge_callback_unavailable
gh_canvas_not_available
gh_document_not_available
gh_operation_unavailable
```

Rules:

- GH gets its own reviewed pass.
- Bridge readiness, canvas readiness, document state, mutation status, and solve lifecycle must not collapse into one broad GH readiness code.
- Existing callback bridge registration remains unchanged.

### Slice 5A: MCP Preservation

MCP preservation may happen early once the first diagnostics exist.

Allowed:

- preserve `diagnostic` objects from Rook responses
- surface diagnostic fields in client-facing errors
- use MCP-owned transport codes for MCP transport failures

MCP-owned codes may include:

```text
rook_unreachable
capabilities_unavailable
diagnostic_fetch_failed
transport_timeout
```

MCP must not mint Rhino-domain runtime reason codes such as:

```text
gh_bridge_unavailable
not_rhino_inside
vision_credentials_missing
```

unless those came from RookNative, managed companion, or RookBIM and MCP is simply preserving them.

### Slice 5B: MCP Behavior And Tool Disclosure

MCP behavior or tool-disclosure changes must wait until enough route families are mapped.

Rules:

- tool disclosure remains based on live `/capabilities`, not bootstrap discovery
- route diagnostics may explain failures but do not replace capability truth
- bootstrap fallback remains non-authoritative
- any behavior change must be explicitly reviewed

## Validation Gates

### Global Phase 2 Gates

Every PR derived from Phase 2 must show:

- same HTTP status where already established
- same success/failure condition
- same route owner
- same callback dispatch path
- same managed/native boundary
- same legacy `data` payload available
- no route ownership changes
- no companion loading-policy changes
- no managed public HTTP surface
- no installer/module manifest work
- no generic `/capabilities` preflight sweep
- diagnostic is additive

### Catalog Diff Gate

Every PR adding diagnostics must include a catalog delta:

```text
added reason codes
failureKind for each reason code
ownedBy/evidenceSource/emittedBy
routes adopting each reason code
tests proving each reason code
```

### Slice 1 Gates

Required:

- `diagnostic` preserves legacy `data`
- `failureKind` is one of the fixed v1 enum values
- `reasonCode` exists in the reviewed catalog
- reason-code metadata includes `ownedBy`, `evidenceSource`, and `emittedBy`
- `diagnosticRoute` is structured
- `state` is omitted unless locally evidenced
- `legacyMessage` is optional
- example adoption adds no route registration
- example adoption moves no route between native and managed
- example adoption changes no callback signature

Source guards should reject:

```text
bridge_unavailable
plugin_not_ready
service_failed
not_available
```

as primary reason codes or catalog entries. They should not scan arbitrary legacy message text.

### Slice 2 Gates

Required:

- `vision.media` callback-missing failure emits diagnostic
- `viewport.capture` tier3 callback-missing failure emits diagnostic
- `block.definition_mutation` callback-missing failure emits diagnostic
- legacy messages remain available
- successful dispatch behavior is unchanged
- managed callback invocation is unchanged
- `managed_dependency_unavailable` is not used as the primary reason when a specific callback-missing reason exists

### Slice 3 Gates

Required:

- `bim.rhino_inside_revit` failures identify the BIM domain
- at least one stable BIM status or diagnostic route proves host-blocked behavior outside Rhino.Inside/Revit
- `not_rhino_inside` maps to `host_blocked`
- BIM dispatch callback unavailable maps to a specific BIM reason code
- RookBIM module not activated/found/failed is emitted only from existing runtime evidence
- Revit API references remain isolated to `src/RookBim`
- native does not invent deeper Revit facts

Source guards:

- no Autodesk/Revit references added to `src/Rook`
- no `module_not_installed` claims
- no installer evidence claims

### Slice 4 Gates

Required:

- GH bridge callback unavailable is distinct from canvas/document unavailable
- GH canvas/document state is only claimed where locally evidenced
- GH route success paths are unchanged
- GH callback bridge registration is unchanged

Live validation:

- GH bridge still registers
- existing GH route smoke still passes
- canvas-unavailable route returns domain diagnostic only where reproducible

### Slice 5A Gates

Required:

- MCP preserves `diagnostic` from Rook responses
- MCP does not rewrite Rhino-domain `reasonCode`
- MCP does not mint Rhino-domain `reasonCode`
- MCP transport failures use `mcp_client`-owned codes only

### Slice 5B Gates

Required:

- tool-disclosure changes are based on live `/capabilities`
- bootstrap discovery remains non-authoritative
- route diagnostics explain failures but do not replace capability truth
- behavior changes are explicitly reviewed

## Live Validation Guidance

Phase 2 is mostly source and contract-test driven. Live validation should be narrow and route-family specific.

Required live checks should be added only when a slice touches behavior that depends on Rhino host state, companion registration, GH lifecycle, RookBIM host state, or viewport capture state.

Recent-file `_Open` startup remains a regression gate for changes that touch startup, companion activation, command-active dispatch, or managed companion readiness. Phase 2 diagnostic work should not normally touch those areas.

## Review Checklist

Every PR derived from this Phase 2 spec should answer:

```text
Which slice is this?
Which domains are touched?
Which routes are touched?
Which reason codes are added?
Who owns each reason code?
What evidence permits each diagnostic?
Does the route preserve existing HTTP status?
Does the route preserve existing success/failure condition?
Does the route preserve existing legacy data?
Does the route preserve existing owner and dispatch path?
Did any client-visible contract change?
Did any schema/version change?
Were live gates skipped? If yes, why?
```

## Next Authorized Artifact

This spec authorizes only the Phase 2 Slice 1 implementation plan after this design is reviewed.

It does not authorize immediate implementation, Phase 2 Slice 2 planning, Phase 3 installer/module work, route ownership movement, or loading-policy changes.
