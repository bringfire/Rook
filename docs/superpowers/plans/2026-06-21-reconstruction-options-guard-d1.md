# Reconstruction Options Guard (D1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reject the empirically-proven self-defeating reconstruction option combination `enable_pbr:true` + `enable_geometry:true` at submit time, before any fal job is spent.

**Architecture:** Add one fail-closed guard plus a strict JSON-boolean helper to `ReconstructionJobManager.SubmitAsync`, placed after the existing `preprocessing_chain` validation and before source lookup. The guard reuses the existing `invalid_request` failure code and `SubmitFail` helper. No DTO, contract, response-shape, or failure-code changes. The options bag stays an opaque `JsonObject`; the guard only reads two keys from it.

**Tech Stack:** C# (.NET), `System.Text.Json.Nodes` (`JsonObject`/`JsonValue`), xUnit.

## Global Constraints

- Fail-closed applies to **only** the `enable_pbr:true` + `enable_geometry:true` contradiction. No other option combination is rejected.
- The guard depends on **no** catalog metadata (`supports_pbr`/`output_roles` are untouched — that is Slice 2).
- `IsJsonTrue` accepts **only** a JSON boolean literal `true`. Missing key, JSON `null`, the string `"true"`, the number `1`, and any non-boolean node must **not** trigger the guard.
- Error message, verbatim: `enable_geometry=true requests geometry-only output and cannot be combined with enable_pbr=true. Remove enable_geometry to request textured output, or remove enable_pbr to request geometry-only output.`
- Failure shape: `Code="invalid_request"`, `Field="options"`, `Retryable=false`.
- Insertion point: `ReconstructionJobManager.SubmitAsync`, after the `preprocessing_chain` block (current line 113) and before `var source = _store.Get(request.SourceArtifactId);` (current line 115). No ledger record is created for a rejected request.
- Tests must be deterministic and offline — use the existing `CreateFixture()` fakes; assert the next fake boundary (`Provider.SubmitRequests`, `Publisher.Published`) rather than relying on a real source path or live fal.

---

### Task 1: Fail-closed `enable_pbr`+`enable_geometry` submit guard

**Files:**
- Modify: `src/Rook/Services/Reconstruction/ReconstructionJobManager.cs` — add guard in `SubmitAsync` (after line 113, before line 115) and add the `IsJsonTrue` private static helper (next to `SubmitFail`, ~line 572).
- Test: `src/Rook.Tests/Services/Reconstruction/ReconstructionJobManagerTests.cs` — append six `[Fact]` methods.

**Interfaces:**
- Consumes (already present, do not change):
  - `ReconstructionSubmitRequest` record with `JsonObject Options` (built by `Request(Guid)` test helper; default options `{"enable_pbr":true,"enable_geometry":false}`).
  - `private static ReconstructionSubmitResult SubmitFail(string code, string message, string? field)` → produces `Failure(code, message, field)` with `Retryable=false` by default.
  - Test fixture: `CreateFixture()` → `Fixture(Store, Ledger, Provider, Downloader, Publisher, Manager)`; `fixture.Provider.SubmitRequests` (List), `fixture.Publisher.Published` (List), `fixture.Manager.List(10).Jobs`, `fixture.Store.Create("generated_image", new[]{ new BlobInput("image", bytes, "png") })`, and `Request(Guid sourceId)`.
  - `using System.Text.Json.Nodes;` is already imported in both files — no new using required.
- Produces:
  - `private static bool IsJsonTrue(JsonObject options, string key)` on `ReconstructionJobManager`.

- [ ] **Step 1: Write the failing tests**

Append these six methods to `ReconstructionJobManagerTests.cs`, immediately before the `private static readonly JsonNode GlbResultJson` field (i.e. after the last existing `[Fact]`, `Result_CompleteJobWithDeletedPackage_ReturnsMissingArtifactWarning`):

```csharp
    [Fact]
    public async Task Submit_PbrAndGeometryBothTrue_RejectedBeforeSourceLookup_ProviderAndPublisherNotInvoked()
    {
        var fixture = CreateFixture();
        // Deliberately do NOT create the source artifact. The guard runs before source lookup, so a
        // contradictory request must fail with field "options" (not "source_artifact_id"). That field
        // value is the proof the guard precedes the source check.
        var request = Request(Guid.NewGuid()) with
        {
            Options = JsonNode.Parse(@"{""enable_pbr"":true,""enable_geometry"":true}")!.AsObject(),
        };

        var result = await fixture.Manager.SubmitAsync(request, CancellationToken.None);

        Assert.False(result.Success);
        Assert.Equal("invalid_request", result.Failure!.Code);
        Assert.Equal("options", result.Failure.Field);
        Assert.False(result.Failure.Retryable);
        Assert.Equal(
            "enable_geometry=true requests geometry-only output and cannot be combined with "
            + "enable_pbr=true. Remove enable_geometry to request textured output, or remove "
            + "enable_pbr to request geometry-only output.",
            result.Failure.Message);
        Assert.Empty(fixture.Provider.SubmitRequests);   // no fal job spent
        Assert.Empty(fixture.Publisher.Published);         // no source-image upload
        Assert.Empty(fixture.Manager.List(10).Jobs);       // no ledger record for an invalid request
    }

    [Fact]
    public async Task Submit_EnablePbrTrueOnly_PassesGuard_ReachesProvider()
    {
        var fixture = CreateFixture();
        var source = fixture.Store.Create(
            "generated_image",
            new[] { new BlobInput("image", new byte[] { 1, 2, 3 }, "png") });
        var request = Request(source.Id) with
        {
            Options = JsonNode.Parse(@"{""enable_pbr"":true}")!.AsObject(),
        };

        var result = await fixture.Manager.SubmitAsync(request, CancellationToken.None);

        Assert.True(result.Success);
        Assert.Single(fixture.Provider.SubmitRequests);    // next fake boundary reached
    }

    [Fact]
    public async Task Submit_EnableGeometryTrueOnly_PassesGuard_ReachesProvider()
    {
        var fixture = CreateFixture();
        var source = fixture.Store.Create(
            "generated_image",
            new[] { new BlobInput("image", new byte[] { 1, 2, 3 }, "png") });
        var request = Request(source.Id) with
        {
            Options = JsonNode.Parse(@"{""enable_pbr"":false,""enable_geometry"":true}")!.AsObject(),
        };

        var result = await fixture.Manager.SubmitAsync(request, CancellationToken.None);

        Assert.True(result.Success);
        Assert.Single(fixture.Provider.SubmitRequests);
    }

    [Fact]
    public async Task Submit_StringTrueOptions_DoNotTriggerGuard_ReachesProvider()
    {
        var fixture = CreateFixture();
        var source = fixture.Store.Create(
            "generated_image",
            new[] { new BlobInput("image", new byte[] { 1, 2, 3 }, "png") });
        // Strings, not JSON booleans — must NOT be coerced into the guard.
        var request = Request(source.Id) with
        {
            Options = JsonNode.Parse(@"{""enable_pbr"":""true"",""enable_geometry"":""true""}")!.AsObject(),
        };

        var result = await fixture.Manager.SubmitAsync(request, CancellationToken.None);

        Assert.True(result.Success);
        Assert.Single(fixture.Provider.SubmitRequests);
    }

    [Fact]
    public async Task Submit_NumericOneOptions_DoNotTriggerGuard_ReachesProvider()
    {
        var fixture = CreateFixture();
        var source = fixture.Store.Create(
            "generated_image",
            new[] { new BlobInput("image", new byte[] { 1, 2, 3 }, "png") });
        // Numbers, not JSON booleans — must NOT be coerced into the guard.
        var request = Request(source.Id) with
        {
            Options = JsonNode.Parse(@"{""enable_pbr"":1,""enable_geometry"":1}")!.AsObject(),
        };

        var result = await fixture.Manager.SubmitAsync(request, CancellationToken.None);

        Assert.True(result.Success);
        Assert.Single(fixture.Provider.SubmitRequests);
    }

    [Fact]
    public async Task Submit_EmptyOptions_DoNotTriggerGuard_ReachesProvider()
    {
        var fixture = CreateFixture();
        var source = fixture.Store.Create(
            "generated_image",
            new[] { new BlobInput("image", new byte[] { 1, 2, 3 }, "png") });
        var request = Request(source.Id) with
        {
            Options = new JsonObject(),
        };

        var result = await fixture.Manager.SubmitAsync(request, CancellationToken.None);

        Assert.True(result.Success);
        Assert.Single(fixture.Provider.SubmitRequests);
    }
```

- [ ] **Step 2: Run the tests to verify the rejection test fails**

Run:
```
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ReconstructionJobManagerTests"
```
Expected: `Submit_PbrAndGeometryBothTrue_RejectedBeforeSourceLookup_ProviderAndPublisherNotInvoked` **FAILS** — without the guard, the bogus source id falls through to the source-lookup check and returns `Field="source_artifact_id"`, so `Assert.Equal("options", result.Failure.Field)` fails. (The five pass-through tests already pass — they are over-trigger regression guards.)

Note: a managed test build deploys `Rook.rhp` into `%AppData%` as a side effect — this is expected for `Rook.Tests`, not a failure. Do not treat a "Deployed Rook.rhp" line as an error.

- [ ] **Step 3: Add the `IsJsonTrue` helper**

In `src/Rook/Services/Reconstruction/ReconstructionJobManager.cs`, add this private static method directly above the `SubmitFail` helper (~line 572):

```csharp
    private static bool IsJsonTrue(JsonObject options, string key)
    {
        if (options is null) return false;
        if (!options.TryGetPropertyValue(key, out var node)) return false;
        if (node is not JsonValue value) return false;
        return value.TryGetValue<bool>(out var parsed) && parsed;
    }
```

- [ ] **Step 4: Add the guard in `SubmitAsync`**

In the same file, in `SubmitAsync`, insert the guard between the `preprocessing_chain` block and the source lookup. The surrounding context becomes:

```csharp
        if (request.PreprocessingChain.Count != 0)
        {
            return SubmitFail(
                "invalid_request",
                "preprocessing_chain execution is not implemented in v0.",
                "preprocessing_chain");
        }

        if (IsJsonTrue(request.Options, "enable_pbr") && IsJsonTrue(request.Options, "enable_geometry"))
        {
            return SubmitFail(
                "invalid_request",
                "enable_geometry=true requests geometry-only output and cannot be combined with "
                + "enable_pbr=true. Remove enable_geometry to request textured output, or remove "
                + "enable_pbr to request geometry-only output.",
                "options");
        }

        var source = _store.Get(request.SourceArtifactId);
        if (source is null)
            return SubmitFail("invalid_request", "source_artifact_id was not found.", "source_artifact_id");
```

- [ ] **Step 5: Run the tests to verify all pass**

Run:
```
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ReconstructionJobManagerTests"
```
Expected: PASS — all `ReconstructionJobManagerTests` green, including the six new methods and the pre-existing ones (e.g. `Submit_QueuesJobAndRecordsProviderPollingHandle`, which uses the default `enable_pbr:true,enable_geometry:false` request and must still reach the provider).

- [ ] **Step 6: Run the full C# test suite (no regressions)**

Run:
```
dotnet test src/Rook.Tests/Rook.Tests.csproj
```
Expected: PASS — full suite green. This catches any incidental break from the manager edit.

- [ ] **Step 7: Commit**

```bash
git add src/Rook/Services/Reconstruction/ReconstructionJobManager.cs src/Rook.Tests/Services/Reconstruction/ReconstructionJobManagerTests.cs
git commit -m "feat(reconstruction): fail-closed guard for enable_pbr+enable_geometry contradiction (D1)"
```

---

## Self-Review

**1. Spec coverage:**
- Doctrine tier 1 (reject known-impossible intent) → Task 1 guard. ✓
- D1 placement (after preprocessing, before source lookup; no ledger record) → Step 4 + the `Assert.Empty(List(10).Jobs)` assertion. ✓
- `invalid_request` / `field=options` / `retryable=false` → Step 4 + rejection-test assertions. ✓
- Verbatim two-alternative message → Global Constraints + Step 4 + rejection-test assertion. ✓
- Strict `IsJsonTrue` (bool-only) → Step 3 + string/numeric/empty tests. ✓
- Spec test 1 (rejected w/ structured failure) + test 2 (provider/publisher never invoked) → combined in `Submit_PbrAndGeometryBothTrue_RejectedBeforeSourceLookup_ProviderAndPublisherNotInvoked`. ✓
- Spec tests 3–7 (pbr-alone, geometry-alone, string, numeric, missing/empty all pass guard) → five pass-through tests. ✓
- D2/D3 → explicitly **not** in this plan (deferred per spec). ✓

**2. Placeholder scan:** No TBD/TODO/"handle edge cases"/vague steps. Every code step shows complete code. ✓

**3. Type consistency:** `IsJsonTrue(JsonObject, string)` signature matches its two call sites in Step 4. `SubmitFail(code, message, field)` matches the existing helper. `Request(Guid) with { Options = ... }` matches the record shape. Fixture member names (`Provider.SubmitRequests`, `Publisher.Published`, `Manager.List(10).Jobs`, `Store.Create`) match `ReconstructionJobManagerTests.cs`. ✓
