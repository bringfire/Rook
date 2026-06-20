# Reconstruction — `StatusFor` HTTP status mapping for typed failures

- Date: 2026-06-20
- Status: Approved (brainstorm complete; ready for implementation plan)
- Branch: `codex/reconstruction-statusfor-http-mapping` (off `origin/main` `e347c7ed`)
- Follow-up polish to: reconstruction substrate convergence (PR #285) and typed
  `missing_credential` (PR #287)

## Problem

`ReconstructionOpHandler.StatusFor(ReconstructionFailure)` maps a failure code to
the HTTP status returned on the reconstruction route. Today it maps `not_found`
→ 404 and a set of `invalid_*` / `filename_collision` codes → 400, and sends
**everything else to 500** via the `default` arm. That bucket now includes the
*typed* provider failures the recent slices introduced — `provider_unavailable`,
`quota_exceeded`, `missing_credential`, `content_policy` — so a caller that hits a
quota limit, a missing key, or a refused-content response receives an opaque
`500 Internal Server Error` instead of a status that reflects what happened. The
failure bodies are already typed and actionable; only the HTTP status is wrong.

## Goal

Map the typed reconstruction failure codes to appropriate non-500 HTTP statuses in
`StatusFor`, so the route's status line matches the typed failure body. Genuine
internal/unexpected failures keep returning 500.

## Non-goals

- No rename of `RookSubsystemRoot.DisposeVideoSubsystemIfCreated` — that is a
  separate, wider rename slice (it touches `RookPlugin`, source-assertion tests,
  and Vision/video test files).
- No `poll_failed`/`submit_failed` changes — after the prior slices these are the
  correct last-resort buckets for genuinely unexpected exceptions.
- No `Retry-After` (or any) response header work. `ApiResponse` carries only an
  integer status; the `retryable` flag already conveys retry-ability in the body.
- No data-driven rewrite of `StatusFor`; extend the existing `switch` in place.
- No change to any failure code, message, or `retryable` value — status mapping
  only.

## Design

### Mapping table (locked)

Extend the `StatusFor` `switch`. The first two rows are unchanged; the four
**bold** rows are the additions; the `default` is unchanged.

| Code | Status | Rationale |
|------|--------|-----------|
| `not_found` | 404 | unchanged |
| `invalid_json`, `invalid_request`, `filename_collision`, `invalid_package`, `invalid_source_role`, `invalid_source_artifact`, `invalid_source_file`, `invalid_source_dimensions` | 400 | unchanged |
| **`missing_credential`** | **400** | required configuration is absent, so the request cannot be fulfilled (see note) |
| **`quota_exceeded`** | **429** | Too Many Requests |
| **`provider_unavailable`** | **503** | downstream fal auth/5xx/network — retry later |
| **`content_policy`** | **422** | request is syntactically valid but the provider refuses to process the content |
| `submit_failed`, `poll_failed`, `provider_failed`, anything else | 500 | genuine internal/unexpected — `default` stays |

### `missing_credential` → 400 (phrasing note)

`missing_credential` is technically a server/operator configuration gap, not
something every caller can fix directly. `400` is nonetheless the right status
here: this route is a local tool/API surface, the request cannot be fulfilled
because required configuration is absent, and the failure body already carries the
actionable remediation text. It must **not** be presented as retryable or as a
provider-side outage — the retryable/provider-outage class is covered separately by
`provider_unavailable` → 503. (The failure's `Retryable` flag is already `false`
from `ReconstructionErrorMapping.MissingCredentialFailure()`; this slice does not
touch it.)

### `cancelled` / `interrupted`

These are job *states* surfaced inside `Ok(...)` status payloads, not failures
routed through `Fail`/`StatusFor`, so they need no mapping. (They would fall to the
500 `default`, but never reach `StatusFor`.) Out of scope; no special-casing.

### Testability: `StatusFor` becomes `internal`

`StatusFor` is currently `private static`. Some mapped codes have no end-to-end
provocation on a handler operation today — notably `content_policy` (the fal
reconstruction error mapper never yields `GenerationErrorCode.ContentPolicy`), and
`quota_exceeded`/`provider_unavailable` are awkward to provoke through the handler
fixture. To test the mapping directly and completely, change `StatusFor` from
`private static` to `internal static` (Rook already exposes internals to
`Rook.Tests` via `InternalsVisibleTo` in `Rook.csproj`). It remains an
implementation detail — not part of the public contract; the visibility change
exists only so the mapping table can be asserted directly. The end-to-end wiring
(handler operation → `Fail(failure, StatusFor(failure))` → `ApiResponse.HttpStatus`)
is already proven by the existing
`DispatchAsync_SubmitMissingSource_ReturnsStructuredFailure` test
(`invalid_request` → 400), so this slice does not add a new end-to-end wiring test.

## Testing

Direct, table-driven `StatusFor` tests (now `internal`) covering every new row plus
guards, each built from the **same `ReconstructionFailure` shape the production
paths build** — not hand-rolled code strings — so the tests track the real
contract:

| Failure built via | Expected status |
|-------------------|-----------------|
| `ReconstructionErrorMapping.MissingCredentialFailure()` | 400 |
| `ReconstructionErrorMapping.ToFailure(new GenerationError(GenerationErrorCode.QuotaExceeded, …))` | 429 |
| `ReconstructionErrorMapping.ToFailure(new GenerationError(GenerationErrorCode.DependencyUnavailable, …))` | 503 |
| `ReconstructionErrorMapping.ToFailure(new GenerationError(GenerationErrorCode.ContentPolicy, …))` | 422 |
| `ReconstructionErrorMapping.ToFailure(new GenerationError(GenerationErrorCode.InvalidRequest, …))` (guard) | 400 |
| `ReconstructionErrorMapping.ToFailure(new GenerationError(GenerationErrorCode.ExecutionFailed, …))` → `provider_failed` (guard, hits `default`) | 500 |

`ReconstructionErrorMapping.ToFailure` and `MissingCredentialFailure` are `public`;
`GenerationError`/`GenerationErrorCode` are read-only (constructing an error value
is not a Vision behavior change). The 500 guard uses `ExecutionFailed` → the real
production code `provider_failed`, which hits the unchanged `default` arm (avoids
asserting a hand-rolled `"submit_failed"`).

End-to-end wiring is already covered by the existing
`DispatchAsync_SubmitMissingSource_ReturnsStructuredFailure` test, so no new
end-to-end test is added.

## Risks

- Low blast radius: one method in one file plus tests. The only behavioral change
  is the HTTP status integer for four codes; failure bodies are unchanged.
- Build safety: run C# tests with `-c Debug` (the `%AppData%` `DeployToRhino`
  target is `Release`-gated; Debug skips it). The string "Deployed Rook.rhp" must
  not appear in test output.

## Files touched

- `src/Rook/Handlers/ReconstructionOpHandler.cs` (`StatusFor` switch).
- `src/Rook.Tests/Handlers/ReconstructionOpHandlerTests.cs` (status-mapping tests).

## Verification target

Full Debug C# suite green + 17/17 MCP reconstruction parity green. No Vision files
touched; no failure code/message/retryable change.
