# `StatusFor` HTTP status mapping — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Map the typed reconstruction failure codes (`missing_credential`, `quota_exceeded`, `provider_unavailable`, `content_policy`) to appropriate non-500 HTTP statuses in `ReconstructionOpHandler.StatusFor`; internal/unexpected codes keep returning 500.

**Architecture:** Extend the existing `StatusFor` `switch` in place with four arms, and relax its visibility from `private static` to `internal static` (matching `ImageJobOpHandler.MapStatusFromCode` / `VideoOpHandler.MapStatusFromCode`) so a table-driven test can assert the full mapping directly. No failure code/message/retryable change.

**Tech Stack:** C# (net48), xUnit. Spec: `docs/superpowers/specs/2026-06-20-reconstruction-statusfor-http-mapping-design.md`.

**Command environment:** verification commands run via the Bash tool (Git Bash), where `grep` is available; the interactive session shell is PowerShell (substitute `Select-String` for `grep` there).

## Global Constraints

- Map exactly these four new codes; leave every other arm unchanged:
  `missing_credential` → 400, `quota_exceeded` → 429, `provider_unavailable` → 503,
  `content_policy` → 422. Default (`submit_failed`, `poll_failed`, `provider_failed`,
  anything else) stays 500.
- No change to any failure code, message, or `retryable` value — HTTP status mapping only.
- No `Retry-After` / header work; no data-driven rewrite; extend the `switch`.
- `StatusFor` stays an implementation detail (`internal`, not `public`).
- Out of scope: the `DisposeVideoSubsystemIfCreated` rename, any `poll_failed` change.
- Run C# tests with `-c Debug` (the `%AppData%` `DeployToRhino` target is `Release`-gated).
  The string "Deployed Rook.rhp" must NOT appear in test output.
- Branch: `codex/reconstruction-statusfor-http-mapping` (already created off `origin/main`
  `e347c7ed`). Stage explicit files only — never `git add -A`/`-a`.

---

### Task 1: Map typed failures to HTTP statuses

**Files:**
- Modify: `src/Rook/Handlers/ReconstructionOpHandler.cs` (`StatusFor`: visibility + 4 arms)
- Test: `src/Rook.Tests/Handlers/ReconstructionOpHandlerTests.cs`

**Interfaces:**
- Produces: `internal static int ReconstructionOpHandler.StatusFor(ReconstructionFailure failure)`.
- Consumes (existing, unchanged): `ReconstructionErrorMapping.MissingCredentialFailure()` and
  `ReconstructionErrorMapping.ToFailure(GenerationError)` (both `public`); `GenerationError(GenerationErrorCode, string, bool Retryable = …)`.

- [ ] **Step 1: Relax `StatusFor` visibility so the test can reference it**

In `src/Rook/Handlers/ReconstructionOpHandler.cs`, change the signature line of `StatusFor` from:

```csharp
        private static int StatusFor(ReconstructionFailure failure)
```

to:

```csharp
        internal static int StatusFor(ReconstructionFailure failure)
```

(Leave the `switch` body unchanged for now — this step only changes visibility so Step 2 compiles. `Rook` already exposes internals to `Rook.Tests` via `InternalsVisibleTo` in `Rook.csproj`.)

- [ ] **Step 2: Write the failing table-driven test**

In `src/Rook.Tests/Handlers/ReconstructionOpHandlerTests.cs`, add this member-data source and theory to the `ReconstructionOpHandlerTests` class (e.g. just before the `Dispose()` method or after the last `[Fact]`):

```csharp
    public static IEnumerable<object[]> StatusForMappings() => new[]
    {
        // typed failures map to specific non-500 statuses
        new object[] { ReconstructionErrorMapping.MissingCredentialFailure(), 400 },
        new object[] { MappedFailure(GenerationErrorCode.QuotaExceeded), 429 },
        new object[] { MappedFailure(GenerationErrorCode.DependencyUnavailable), 503 },
        new object[] { MappedFailure(GenerationErrorCode.ContentPolicy), 422 },
        // guards: an existing 400 arm stays 400; the default arm stays 500
        new object[] { MappedFailure(GenerationErrorCode.InvalidRequest), 400 },
        new object[] { MappedFailure(GenerationErrorCode.ExecutionFailed), 500 }, // -> provider_failed
    };

    private static ReconstructionFailure MappedFailure(GenerationErrorCode code)
        => ReconstructionErrorMapping.ToFailure(new GenerationError(code, "x", Retryable: false));

    [Theory]
    [MemberData(nameof(StatusForMappings))]
    public void StatusFor_MapsTypedFailureToHttpStatus(ReconstructionFailure failure, int expected)
    {
        Assert.Equal(expected, ReconstructionOpHandler.StatusFor(failure));
    }
```

(The file already imports `System.Collections.Generic`, `Rook.Handlers`, `Rook.Services.Reconstruction`, `Rook.Services.Vision.Generation`, and `Xunit` — no new usings.)

- [ ] **Step 3: Run the test to verify it fails**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug --filter "FullyQualifiedName~StatusFor_MapsTypedFailureToHttpStatus" 2>&1 | grep -iE "Expected:|Actual:|Failed!|Passed!|error CS"`
Expected: FAIL — the `missing_credential`/`quota_exceeded`/`provider_unavailable`/`content_policy` cases currently fall to the `default` and return `500`, e.g. `Expected: 400` / `Actual: 500` (the `InvalidRequest`→400 and `ExecutionFailed`→500 guard rows already pass).

- [ ] **Step 4: Add the four mapping arms**

In `src/Rook/Handlers/ReconstructionOpHandler.cs`, replace the `StatusFor` body:

```csharp
        internal static int StatusFor(ReconstructionFailure failure)
            => failure.Code switch
            {
                "not_found" => 404,
                "invalid_json" or "invalid_request" or "filename_collision" or "invalid_package"
                    or "invalid_source_role"
                    or "invalid_source_artifact" or "invalid_source_file"
                    or "invalid_source_dimensions" => 400,
                _ => 500,
            };
```

with:

```csharp
        internal static int StatusFor(ReconstructionFailure failure)
            => failure.Code switch
            {
                "not_found" => 404,
                "invalid_json" or "invalid_request" or "filename_collision" or "invalid_package"
                    or "invalid_source_role"
                    or "invalid_source_artifact" or "invalid_source_file"
                    or "invalid_source_dimensions" => 400,
                // Required configuration absent — the request cannot be fulfilled. Not retryable and
                // not a provider outage (provider_unavailable -> 503 covers that); the body carries the
                // remediation text.
                "missing_credential" => 400,
                "quota_exceeded" => 429,
                "provider_unavailable" => 503,
                "content_policy" => 422,
                _ => 500,
            };
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug --filter "FullyQualifiedName~StatusFor_MapsTypedFailureToHttpStatus" 2>&1 | grep -iE "Deployed Rook|Failed!|Passed!|error CS"`
Expected: `Passed!` (6 theory cases), no "Deployed Rook" line.

- [ ] **Step 6: Run the handler regression guard + commit**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug --filter "FullyQualifiedName~ReconstructionOpHandlerTests" 2>&1 | grep -iE "Deployed Rook|Failed!|Passed!|error CS"`
Expected: `Passed!` (includes `DispatchAsync_SubmitMissingSource_ReturnsStructuredFailure`, which pins the end-to-end `invalid_request` → `HttpStatus == 400` wiring).

```bash
git add src/Rook/Handlers/ReconstructionOpHandler.cs src/Rook.Tests/Handlers/ReconstructionOpHandlerTests.cs
git commit -m "feat(reconstruction): map typed failures to HTTP statuses in StatusFor"
```

---

### Task 2: Full-suite verification gate

**Files:** none (verification only).

- [ ] **Step 1: Run the full Debug C# suite**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug 2>&1 | grep -iE "Deployed Rook|Failed!|Passed!|Passed:|Failed:|Total:|error CS"`
Expected: `Passed!` with `Failed: 0`. No "Deployed Rook" line. (Baseline before this slice was 2830 passing; this slice adds one theory with 6 cases → expect ~2836 passing, 0 failed.)

- [ ] **Step 2: Run the MCP reconstruction parity tests**

Run: `python -m pytest mcp_server/tests/test_reconstruction_mcp_tools.py -q 2>&1 | tail -3`
Expected: `17 passed` (the `.pytest_cache` permission warning is pre-existing and fine).

- [ ] **Step 3: Confirm the constraint gate (diff-scoped)**

Run (Bash tool):

```bash
git diff --name-only origin/main...HEAD | grep -i "Services/Vision" && echo "VIOLATION: Vision file touched" || echo "OK: no Vision files touched"
git diff origin/main...HEAD -- src/Rook/Handlers/ReconstructionOpHandler.cs | grep -nE '"missing_credential" =>|"quota_exceeded" =>|"provider_unavailable" =>|"content_policy" =>' || echo "WARN: expected new arms not found in diff"
```

Expected: `OK: no Vision files touched`, and the four new `=> nnn` arms appear in the diff. (Only `StatusFor`'s visibility + four arms should differ in production.)

- [ ] **Step 4: No commit** (verification only). If anything is red, return to Task 1.

---

## Self-Review

**Spec coverage:**
- Mapping table (spec "Design") → Task 1 Step 4 (four arms; default unchanged). ✓
- `StatusFor` → `internal` for direct testing (spec "Testability") → Task 1 Step 1. ✓
- Table-driven tests via real `ReconstructionErrorMapping` shapes (spec "Testing"), incl. the
  `ExecutionFailed`→`provider_failed`→500 default guard the reviewer requested → Task 1 Step 2. ✓
- End-to-end wiring already covered by `DispatchAsync_SubmitMissingSource_ReturnsStructuredFailure`
  (spec "Testability") → re-run in Task 1 Step 6; no new e2e test added. ✓
- Non-goals (no rename, no poll_failed change, no headers, no code/message/retryable change) →
  respected; verified in Task 2 Step 3. ✓

**Placeholder scan:** No TBD/TODO; every code step shows complete code. ✓

**Type consistency:** `StatusFor(ReconstructionFailure) : int` (internal static) used verbatim in the
test. `ReconstructionErrorMapping.MissingCredentialFailure()` and `ToFailure(GenerationError)` are the
real public APIs (from PR #287 / existing). `GenerationError(GenerationErrorCode, string, bool Retryable)`
matches existing call sites. `ReconstructionFailure.Code` is the switched property. ✓
