# Rook Ecosystem Phase 2B: Block Mutation Terminal Proxy Diagnostics

## Status

Draft design spec for review.

This document defines the next Phase 2 diagnostics slice after Phase 2A
vision/media and viewport/capture diagnostics. It authorizes design review only.
It does not authorize implementation or an implementation plan.

## Background

Phase 1 made `GET /capabilities` the authoritative live runtime capability
surface. Discovery files remain locator/bootstrap metadata only.

Phase 2 introduced additive route diagnostics for domain-readiness and
dependency failures. Route diagnostics must preserve existing response behavior:
legacy `data`, HTTP status codes, headers, route ownership, callback paths, and
availability semantics.

Phase 2A adopted this contract for:

- `vision.media` callback-unavailable failures;
- `viewport.capture` tier-3 callback-unavailable failures.

Phase 2A explicitly deferred `block.definition_mutation` because block
mutation has a safety-specific fallback path.

## Current Block Mutation Architecture

`RookNative` remains the only public Rhino HTTP/discovery surface. Block
definition mutation routes are registered by native and then delegated to the
managed companion. The companion remains internal.

The companion-backed block definition mutation route family includes:

- `POST /block/set-layers`
- `POST /block/set-layers-batch`
- `POST /block/set-materials`
- `POST /block/set-materials-batch`
- `POST /block/set-object-colors`
- `POST /block/set-object-colors-batch`
- `POST /block/set-object-names`
- `POST /block/set-object-names-batch`
- `POST /block/set-object-user-strings`
- `POST /block/set-object-user-strings-batch`
- `POST /block/replace-object-geometry`
- `POST /block/replace-object-geometry-batch`
- `POST /block/transform-object`
- `POST /block/transform-object-batch`
- `POST /block/transform-instance-batch`

The native handler path is:

```text
native /block/* route
  -> block handler in GrasshopperProxyHandler.cpp
    -> DispatchManagedCompanionRouteOrProxy(...)
      -> if callback is present:
           DispatchGrasshopperRoute(...)
      -> if callback is absent:
           ProxyManagedRequest(...)
```

The proxy fallback exists because native block-definition mutation has a known
Rhino crash history. That fallback is architectural safety machinery, not
legacy debt.

## Safety Invariant

Block mutation callback absence is not a route failure while the managed proxy
fallback can continue.

No Phase 2B work may remove, bypass, weaken, or reorder
`DispatchManagedCompanionRouteOrProxy`.

No diagnostic may cause a block route to fail earlier than it does today.

## Phase 2B Goal

Make final native-observed block mutation proxy failures identify
`block.definition_mutation` instead of returning only a generic managed proxy
failure message.

This is limited to terminal native proxy failures after the block route has
already selected and attempted the managed proxy fallback.

## Non-Goals

Phase 2B does not:

- diagnose callback absence as a block route failure;
- replace the managed proxy fallback;
- move route ownership;
- change companion loading policy;
- add managed public HTTP surface;
- add installer or module manifest work;
- add a `/capabilities` route preflight;
- parse, inspect, wrap, rewrite, or add diagnostics to managed proxy responses;
- classify managed block operation failures such as invalid payloads, missing
  block definitions, object index errors, geometry mutation failures, or ordinary
  managed exceptions;
- add generic GH bridge diagnostics;
- change MCP behavior or tool disclosure.

## Diagnostic Adoption Boundary

Phase 2B adopts diagnostics only for this sequence:

```text
callback absent
  -> managed proxy fallback selected
  -> proxy terminal failure observed natively
  -> additive block.definition_mutation diagnostic emitted
```

The callback-present branch remains unchanged:

```text
callback present
  -> DispatchGrasshopperRoute(...)
  -> no Phase 2B diagnostic adoption
```

The successful proxy branch remains unchanged:

```text
proxy forwarding succeeds
  -> native copies managed response through unchanged
```

For Phase 2B, pass-through means:

```text
If TryForwardGrasshopperRequest succeeds, native does not inspect, parse, wrap,
rewrite, or add diagnostics to the managed response.
```

This applies whether the managed response is a success or a failure. Native
treats both as successfully proxied responses in this slice.

## Shared Proxy Constraint

`ProxyManagedRequest` is shared. It is reachable from block mutation routes and
from other proxy-backed surfaces.

Phase 2B must not add a generic proxy diagnostic that silently changes every
proxy failure. Any diagnostic context must be explicit and route scoped.

Acceptable implementation shapes for a later plan include:

```text
ProxyManagedRequest(..., optional diagnostic context)
```

or an equivalent block-only wrapper.

Hard requirement:

```text
A block diagnostic context may be introduced, but only block mutation handlers
may provide it. All existing non-block ProxyManagedRequest callers must keep
current behavior and response shape.
```

If an optional diagnostic context is used, the default context must be absent.
Absent context must preserve non-block proxy failure behavior as closely as
practical, including the existing envelope shape and status codes.

## Failure Points Eligible For Diagnostics

### Managed Proxy Discovery Unavailable

Eligible when:

```text
block route selected proxy fallback
TryGetManagedPort(...) failed
```

This is native-observed evidence that the managed proxy could not be located or
read for this Rhino process. It does not necessarily prove the companion is not
loaded, so Phase 2B should not claim `state: not_loaded`.

### Managed Proxy Forwarding Failed

Eligible when:

```text
block route selected proxy fallback
TryGetManagedPort(...) succeeded
TryForwardGrasshopperRequest(...) failed
```

This is native-observed evidence that proxy forwarding failed after managed
proxy evidence existed.

### Managed Proxy Response Returned

Not eligible for new native diagnostics in Phase 2B.

When forwarding succeeds, the managed response is passed through unchanged.
Native may preserve any downstream diagnostic already present in the managed
body by pass-through, but it must not parse or rewrite it.

## Failure Points Not Eligible In Phase 2B

The following remain legacy/local:

- callback absence before proxy fallback;
- callback invocation failures through shared `DispatchGrasshopperRoute`;
- managed `BlocksHandler` operation failures;
- invalid request bodies;
- missing block definitions;
- layer/material lookup failures;
- invalid object indexes;
- geometry conversion or mutation failures;
- ordinary managed exceptions;
- WinHTTP response bodies returned successfully by the proxy.

These may be considered in later reviewed slices only if they can be tied to
real evidence and do not weaken route behavior.

## Reason Code Catalog Delta

### `block_mutation_managed_proxy_unavailable`

```text
domainId: block.definition_mutation
failureKind: dependency_unavailable
ownedBy: native
evidenceSource: native_managed_proxy_discovery
emittedBy: native_route
retryable: true
userActionRequired: false
state: omitted or unknown
```

Evidence:

```text
TryGetManagedPort failed after the block route selected the managed proxy
fallback path.
```

Recommended next step:

```text
Wait for managed companion startup, then retry. If the route remains
unavailable, inspect GET /capabilities for block.definition_mutation and check
native/companion diagnostics.
```

### `block_mutation_managed_proxy_forward_failed`

```text
domainId: block.definition_mutation
failureKind: dependency_degraded
ownedBy: native
evidenceSource: native_managed_proxy_transport
emittedBy: native_route
retryable: true
userActionRequired: false
state: omitted or unknown
```

Evidence:

```text
TryGetManagedPort succeeded, but TryForwardGrasshopperRequest failed after the
block route selected the managed proxy fallback path.
```

Recommended next step:

```text
Retry after companion startup has stabilized. If forwarding continues to fail,
inspect native and managed logs for proxy transport details.
```

## Native-Observed Versus Managed-Observed Evidence

Native may own and emit reason codes for:

- managed proxy discovery unavailable;
- managed proxy forwarding failed;
- route context proving the failure came from a block mutation fallback path.

Managed owns evidence for:

- request validation;
- active document handling inside `BlocksHandler`;
- block definition existence;
- object index validity;
- layer/material/object lookup;
- geometry conversion;
- block definition mutation success/failure;
- exceptions thrown during managed block operation execution.

Phase 2B does not introduce managed-owned block reason codes.

## Downstream Diagnostic Preservation

If the managed proxy later returns a response that already contains a
diagnostic, native may preserve it only by pass-through.

Native must not:

- parse the managed body looking for diagnostics;
- rewrite downstream reason codes;
- replace managed-owned evidence with native-owned evidence;
- add a native diagnostic around a successfully proxied managed response.

## Source Guard Requirements

The eventual Phase 2B implementation plan must require source guards proving:

- `DispatchManagedCompanionRouteOrProxy` still calls
  `DispatchGrasshopperRoute(req, res, path, callback)` when `callback != nullptr`;
- the callback-absent branch still reaches `ProxyManagedRequest` after callback
  selection, preserving fallback ordering even if optional diagnostic context is
  threaded through the call;
- no `SendErrorWithDiagnostic` or `SendErrorDataWithDiagnostic` appears before
  the proxy fallback in `DispatchManagedCompanionRouteOrProxy`;
- only block mutation handlers pass block diagnostic context;
- existing non-block `ProxyManagedRequest` callers remain without diagnostic
  context;
- native block mutation handler functions still route through
  `DispatchManagedCompanionRouteOrProxy`;
- managed `BlocksHandler` operation failures remain legacy/local and do not
  mint Phase 2B reason codes;
- successful proxy forwarding does not inspect, parse, wrap, rewrite, or add
  diagnostics to the managed response.

## Validation Gates

### Source Validation

Required:

- reason code catalog contains only reviewed Phase 2B reason codes;
- no broad reason code such as `bridge_unavailable`,
  `managed_dependency_unavailable`, `plugin_not_ready`, or `not_available` is
  introduced;
- no `/capabilities` preflight appears in block handlers or proxy helper;
- no route ownership movement appears in native route registration;
- no `.vcxproj` or `.vcxproj.filters` changes;
- non-block proxy callers preserve current call shape unless explicitly proven
  equivalent by tests.

### Managed Validation

Required:

- managed block handlers do not start returning Phase 2B diagnostics;
- managed block route-local failures remain serialized through the existing
  `ApiResponse` path.

### Native Build Validation

Required before merge of any implementation PR:

- MSVC 14.44 Debug x64 native build passes.

### Live Validation

At least one live confidence check should prove the healthy route path is not
damaged:

```text
callback registered or proxy available
block mutation route still succeeds or returns its existing managed failure
without a new native diagnostic wrapper
```

If a reliable way exists to simulate missing managed proxy discovery without
destabilizing Rhino, a smoke may also validate the diagnostic terminal failure
path. This is optional unless the implementation plan identifies a safe
repeatable harness method.

## Review Checklist

Before approving a Phase 2B implementation plan, reviewers should confirm:

- the plan touches only terminal native proxy failures for
  `block.definition_mutation`;
- callback absence remains evidence before fallback, not the primary route
  failure;
- proxy success pass-through is unchanged for managed success and managed
  failure responses;
- `ProxyManagedRequest` diagnostics are context-scoped and cannot bleed into
  non-block proxy routes;
- the planned tests prove fallback ordering before diagnostic adoption;
- no managed block operation taxonomy is introduced;
- no route ownership, loading policy, installer, MCP behavior, or public managed
  HTTP changes are introduced.

## Open Question For Review

Should `block_mutation_managed_proxy_forward_failed` remain
`dependency_degraded`, or should connection-refused/no-response cases be split
later into a more specific `dependency_unavailable` reason once native transport
evidence is categorized more finely?

The recommended Phase 2B answer is to keep one forwarding-failed reason code and
use `dependency_degraded` for now. The legacy `data` message can continue to
carry the WinHTTP detail.
