# `gh_inspect_output` Selector Design

## Goal

Prevent an explicit but unrecognized or invalid output selector from silently reading output 0. Preserve existing named and numeric-string `param` calls, and preserve output 0 only as the true no-selector default.

## Contract

| Submitted fields | Meaning | Result |
| --- | --- | --- |
| Neither `param` nor `outputIndex` present | Legacy default | Read output 0. |
| `param: "Result"` | Name or nickname | Read the matching output or return `invalid_request`. |
| `param: "5"` | Existing numeric-string selector | Read output 5 or return `invalid_request`. Use the existing numeric-string parsing semantics. |
| `outputIndex: 5` | New explicit zero-based selector | Read output 5 or return `invalid_request`. |
| Both fields present | Conflicting selectors | Return `invalid_request`, even if both identify the same output or either value is null. |
| Either field present as null, empty, whitespace-only, malformed, negative, unknown, or out of range | Explicit invalid selector | Return `invalid_request`; never read output 0. |

The governing invariant is:

> Default to output 0 only when no recognized selector field was supplied.

The successful response continues to report the resolved output through the existing `param_name`, `param_nickname`, and `index` fields. No duplicate response vocabulary is added.

## Affected Boundaries

1. **MCP schema and Python dispatch**
   - Keep `param` as a string.
   - Add `outputIndex` as an integer with `minimum: 0`.
   - Reject simultaneous selectors and malformed explicit values before transport.
   - Forward the selected field unchanged. When both fields are absent, forward neither and let the managed contract apply the legacy default.

2. **Native proxy**
   - No change. `BuildRequestJson` already serializes every GET query parameter into the registered managed callback request.

3. **Managed callback and output resolver**
   - Preserve field presence separately from parsed value so absence cannot be confused with null or malformed input.
   - Accept the string representation of `outputIndex` produced by GET query transport, while the public MCP field remains integer-only.
   - Resolve names, nicknames, numeric-string `param` values, and explicit indices against the actual output collection.
   - Inspect `VolatileData` only after a selector has resolved successfully.
   - Keep the implementation local to `gh_inspect_output`; do not generalize the connection selector machinery.

## Error Behavior

MCP schema or Python-dispatch rejection uses the existing MCP invalid-arguments/tool-result envelope and does not make an HTTP request. A request that reaches the managed bridge returns `Success = false`, HTTP 400 through the existing bridge mapping, and structured data containing `code: "invalid_request"`, a relevant field (`param`, `outputIndex`, or `selector`), and a bounded message. Both paths reject before output inspection or output-0 fallback. Conflict detection is based on field presence, not parsed values.

Existing readiness fencing, missing-component behavior, and successful output-data extraction remain unchanged.

## Focused Test Matrix

| Case | Expected proof |
| --- | --- |
| Named `param` | Existing name/nickname resolution succeeds. |
| Numeric-string `param` | Existing numeric parsing remains compatible. |
| Integer `outputIndex` | Schema advertises it and dispatch/managed resolution select the requested output. |
| Neither selector | Output 0 remains the documented default. |
| Both selectors | Fails as `invalid_request` before output inspection. |
| Null, empty, or whitespace selector | Presence is retained and fails; it is not treated as omission. |
| Wrong JSON type or malformed value | Fails as `invalid_request`. |
| Negative or out-of-range index | Fails as `invalid_request`. |
| Unknown name | Fails as `invalid_request`. |
| Explicit invalid selector with a valid output 0 available | Proves output 0 is not read as a fallback. |
| Native callback forwarding | Proves `outputIndex` reaches the managed selector without a C++ change. |

## Scope Boundary

No native C++ changes, generalized selector framework, telemetry changes, live-host requirement, or unrelated schema hardening are included.
