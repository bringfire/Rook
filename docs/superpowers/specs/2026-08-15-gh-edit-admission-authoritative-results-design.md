# Grasshopper Edit Admission And Authoritative Results

**Status:** Approved design for implementation planning
**Date:** 2026-08-15
**Baseline:** `61c686c5e1204ded860fc9a22f8acc65c4f99db6`

## Objective

Make the existing `gh_edit` request boundary fail closed before target contact or
mutation when a batch contains an invalid, duplicate, or unresolved temporary
reference. At the same time, remove unrelated knowledge hints from four
authoritative Grasshopper capability results.

This is a small cross-owner contract correction. It adds no endpoint, production
module, identity family, planner, critic, scheduler, evaluator, predicate catalog,
or copied tool schema.

## Evidence

The retained three-run Qwen3.8 campaign showed that `gh_edit` correctly refused
flows containing undeclared `N*` temporary identifiers, but only after component
creation and deletion had already committed. Qwen recovered from the partial state,
yet the invalid references should have refused the complete request before target
dispatch.

The same campaign retained unrelated universal knowledge hints on authoritative
`gh_edit`, `gh_snapshot`, `gh_status`, and `gh_errors` results. These capabilities
report live host facts and must not have their payloads or receipts decorated by
knowledge retrieval.

## Ownership

### Python admission owner

The existing `mcp_server/src/rook/gh_edit_contract.py` owns one pure request
admission function in addition to its current result projection. Both canonical MCP
dispatch and direct `ToolDispatcher` dispatch call that function after their existing
profile, containment, meta-tool, and schema walls but before target resolution,
document enrichment, or native dispatch.

No route may independently reinterpret the grammar.

### Managed admission owner

`GrasshopperHandler.ApplyEdit()` independently applies the same closed contract to
raw `/gh/edit` requests before `EnsureGrasshopperReadyForEdit()`, component-server
access, document access, receipt reservation, undo creation, solve suspension, or
mutation.

The managed guard protects the internal primitive from non-Python callers. It does
not move orchestration policy into another endpoint.

### Knowledge owner

The existing universal knowledge-injection skip set owns the authoritative-result
boundary. Direct dispatch already bypasses universal injection; canonical dispatch
must produce the same unmodified capability data.

## Closed Temporary-ID Contract

### Declared identifiers

Every `create[*]` entry must contain `temp_id`, preserving the current public MCP
schema. It must be a concrete string matching:

```text
^T[A-Za-z0-9_]{1,63}$
```

The total length is therefore 2 through 64 characters. The leading `T` is
case-sensitive. Examples:

```text
admitted: T1, TActorSetControl, T_CLEAN
refused:  T, t1, N1, T-hyphen, T<65-total-characters>
```

Every temporary identifier must be unique within the request under exact
ordinal comparison. The guard never rewrites, folds, or renumbers identifiers.

### Reference locations

The guard examines every component reference in:

- both endpoints of every `connect` flow;
- both endpoints of every `disconnect` flow;
- every `set_values[*].id`;
- every `groups[*].members[*]` entry.

A component reference is admitted only when it is either:

1. an existing short-instance identity matching `^C[1-9][0-9]*$`; or
2. an exact temporary identifier declared by `create[*].temp_id` in the same batch.

The admission phase proves only the syntax of `C*` references. Existing managed
instance resolution remains authoritative for whether a syntactically valid `C*`
exists on the selected canvas. An undeclared `T*` reference is always an admission
failure. Any other prefix, including `N*`, is an invalid reference.

Group operation identities such as the group `id` remain under their existing
`G*` contract. Only group member component references are governed here. Delete
identities are also unchanged because they do not reference newly declared
temporary objects.

### Complete-batch refusal

Admission scans the complete caller request without contacting a target. It emits
issues in the fixed semantic field order `create`, `disconnect`, `set_values`,
`connect`, `groups`, preserving array order within each field, and then either admits
the whole request or refuses the whole request. There is no partial admission.

A flow that cannot be parsed as exactly one source component/output and one target
component/input is `invalid_flow`. A syntactically complete flow whose component
token is neither an admitted `C*` nor a declared `T*` uses the component-reference
codes below. No malformed flow survives admission to the existing mutation phases.

The refusal data is closed:

```json
{
  "error": "gh_edit_admission_failed",
  "issues": [
    {
      "path": "/create/1/temp_id",
      "code": "duplicate_temp_id",
      "value": "TActorSetControl"
    }
  ]
}
```

The data object has exactly `error` and `issues`. Each issue has exactly `path`,
`code`, and `value`. `path` is an RFC 6901 JSON Pointer to the caller-owned field;
`value` is the exact caller value; and `code` is one of:

```text
invalid_temp_id
duplicate_temp_id
invalid_flow
invalid_component_reference
unresolved_temp_reference
```

Python returns this data through the route's existing result-envelope and MCP
projection. Managed raw dispatch returns the same data through the existing
`ApiResponse` envelope. No layer adds target context, document identity, knowledge,
or mutation evidence to an admission refusal.

## Ordering Invariants

Canonical MCP:

```text
containment/profile/meta/schema admission
-> gh_edit request admission
-> target resolution and document enrichment
-> one native dispatch
```

Direct `ToolDispatcher`:

```text
tool/schema admission
-> gh_edit request admission
-> one native dispatch
```

Managed raw route:

```text
body parse
-> gh_edit request admission
-> Grasshopper readiness and target access
-> mutation lifecycle
```

For every admission refusal:

```text
native target dispatches == 0
managed canvas/readiness accesses == 0
receipt reservations == 0
mutations == 0
```

The existing valid request path, `C*`/`T*` correlation, edit receipt, solve receipt,
partial-failure behavior after admitted mutation begins, and result projection remain
unchanged.

## Authoritative Result Boundary

Universal knowledge injection is skipped for exactly these additional tools:

```text
gh_edit
gh_snapshot
gh_status
gh_errors
```

The existing skips remain unchanged:

```text
gh_library
gh_batch_component_info
```

For both direct dispatch and canonical gateway dispatch, the capability's original
arguments, success classification, data value, mutation receipt, solve-readiness
receipt, observations, errors, and diagnostics pass through unchanged. No
`knowledge_hint` or equivalent enrichment is added.

This does not delete, redesign, or suppress knowledge for any other capability.

## Compatibility

- Valid descriptive temporary identifiers remain valid.
- Existing `C*` and `T*` execution identities are unchanged.
- Existing valid `gh_edit` callers require no request or response change.
- Invalid batches change intentionally from possible partial mutation to truthful
  pre-contact refusal.
- Existing managed runtime resolution remains authoritative after admission.
- No prompt or model-specific workaround is added.

## Verification Contract

Test-first implementation must causally prove:

1. `T1`, `TActorSetControl`, and `T_CLEAN` are admitted.
2. Invalid syntax and duplicate declared IDs refuse deterministically.
3. Undeclared `T*` and invalid `N*` references refuse in connections,
   disconnections, values, and groups.
4. Mixed valid/invalid batches refuse as a whole.
5. Python canonical and direct paths return the same refusal data and make zero
   native target calls.
6. The managed raw route makes zero readiness, document, receipt, or mutation calls
   on refusal.
7. A valid descriptive-ID batch still creates, connects, sets values, groups, and
   returns its existing receipts and correlation maps.
8. Direct and canonical calls to all six authoritative tools retain the exact
   capability data with no knowledge hint.
9. Unrelated knowledge injection behavior remains unchanged.

Focused Python and managed seams run first, followed by adjacent suites. The known
unrelated knowledge-test baseline failures are recorded separately and are not
absorbed into this correction.

## Production Scope

Expected production owners are limited to:

- `src/Rook/Handlers/GrasshopperHandler.cs`
- `mcp_server/src/rook/gh_edit_contract.py`
- `mcp_server/src/rook/server.py`
- `mcp_server/src/rook/agent/tool_dispatcher.py`
- `mcp_server/src/rook/learning/knowledge_injector.py`

Stop if implementation requires a new production module, endpoint, identity system,
or architectural owner.

## Post-Merge Experiment Boundary

After independent review, merge, and standard Release deployment, one disposable
Qwen3.8 helix experiment may reuse the proven Prime adapter, model configuration,
canonical gateway, receipt fencing, and evidence custody. Its task-local probe may
test radial periodic XY behavior, monotonic Z, claimed-control causality, exact
restoration, and clean diagnostics. Unsupported properties remain `unproven`.

The experiment is not part of this production correction and must stop before live
contact for explicit authorization.
