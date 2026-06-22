# Reconstruction: Resolved Import Role Display Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Reconstruct result panel state, before import, the role the importer will actually use — computed by the same C# resolver the native import path uses, so it cannot drift from the real import.

**Architecture:** Backend adds one field, `resolved_import_role`, to `ReconstructionOpHandler.PackageSummary`, computed by the existing pure `ResolveAssetRole(package, manifest, requestedRole: null, …)`. The Reconstruct view (`app.js renderResult`) displays it as an "Import will use" line and disables the Import button when it is null. No native change, no JS-side resolution, no mutating preview call.

**Tech Stack:** C# (.NET Framework net48, xUnit), vanilla JS WebView (Pattern A bridge), CSS.

## Global Constraints

- Base: origin/main `896ea949`. Worktree: `.worktrees/reconstruction-resolved-role`, branch `feature/reconstruction-resolved-import-role`.
- `ResolveAssetRole` is the single source of truth — do **not** reimplement fallback resolution in JavaScript.
- Field name is exactly `resolved_import_role`. `preferred_asset_role` stays unchanged (catalog/declared preference).
- UI copy, verbatim: `Available assets: <roles>`, `Catalog preferred: <role>`, `Import will use: <role>`; null → `Import unavailable: no importable model asset`.
- On `resolved_import_role == null`: disable the Import button regardless of `result_available`.
- No native importer change, no second importer, no WebView direct HTTP (Pattern A preserved).
- No `prepare_import` (mutating op) call for preview — call only the pure `ResolveAssetRole` helper.
- No target-layer UI, no assetRole override UI, no select/zoom, no duplicate-confirm.
- Mandatory **panel-dark gate** after any JS/HTML change: `node --check`, no duplicate IDs, every `$("id")` in the Reconstruct module exists in `index.html`, no stale symbols.
- Merge gate: live Hunyuan textured smoke on a managed Release build/deploy of `src/Rook/Rook.csproj`.
- Run all C# tests with `dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug` (Debug skips the %AppData% Rhino deploy).

---

### Task 1: Backend — add `resolved_import_role` to `PackageSummary`

**Files:**
- Modify: `src/Rook/Handlers/ReconstructionOpHandler.cs` (`PackageSummary`, ~lines 828-849)
- Test: `src/Rook.Tests/Handlers/ReconstructionOpHandlerTests.cs`

**Interfaces:**
- Consumes: existing private `ResolveAssetRole(Artifact package, JsonObject manifest, string? requestedRole, out ReconstructionFailure? failure) → string?` (pure: reads in-memory manifest + `package.Files`, no I/O writes, no staging, no import-id). Existing private `ReadImportManifest(Guid, out failure) → JsonObject?`. Existing test helpers `CreateFixture()`, `BuildPackageAsync(fixture, JsonNode resultJson, Guid? jobId = null)`, `fixture.Store.GetBlobAbsolutePath(id, role)`, `ReconstructionFileRoles.ImportManifest/ModelObj`.
- Produces: `job_result` `package` summary dict now contains key `resolved_import_role` (string or null), alongside existing `artifact_id`, `kind`, `asset_roles`, `preferred_asset_role`.

- [ ] **Step 1: Write the failing tests**

Add these three tests to `ReconstructionOpHandlerTests.cs`. They drive `job_result` and read the `package` summary.

```csharp
[Fact]
public async Task Result_ResolvedImportRole_PreferredPresent_EqualsPreferred()
{
    // glb delivered → manifest preferred_asset (model_glb) is present → resolver returns preferred.
    var fixture = CreateFixture();
    fixture.Downloader.Files["https://example.test/model.glb"] = new byte[] { 1, 2, 3 };
    var jobId = Guid.NewGuid();
    var package = await BuildPackageAsync(fixture, JsonNode.Parse("""
    { "model_urls": { "glb": {"url": "https://example.test/model.glb"} } }
    """)!, jobId);
    fixture.Ledger.Append(ReconstructionJobLedgerRecord.Complete(jobId, package.Id));

    var response = fixture.Handler.DispatchOffUi(
        $"{{\"op\":\"job_result\",\"job_id\":\"{jobId}\"}}");

    Assert.True(response.Success, JsonSerializer.Serialize(response.Data));
    var data = Assert.IsType<Dictionary<string, object?>>(response.Data);
    var summary = Assert.IsType<Dictionary<string, object?>>(data["package"]);
    Assert.Equal("model_glb", summary["preferred_asset_role"]);
    Assert.Equal("model_glb", summary["resolved_import_role"]);
}

[Fact]
public async Task Result_ResolvedImportRole_PreferredMissing_FallbackPresent_EqualsFallback()
{
    // obj+mtl+texture delivered, NO glb → preferred (model_glb) absent → fallback resolves to model_obj.
    var fixture = CreateFixture();
    fixture.Downloader.Files["https://example.test/model.obj"] = new byte[] { 1, 2, 3 };
    fixture.Downloader.Files["https://example.test/material.mtl"] = new byte[] { 4, 5, 6 };
    fixture.Downloader.Files["https://example.test/texture.png"] = new byte[] { 7, 8, 9 };
    var jobId = Guid.NewGuid();
    var package = await BuildPackageAsync(fixture, JsonNode.Parse("""
    {
      "model_urls": {
        "obj": {"url": "https://example.test/model.obj"},
        "mtl": {"url": "https://example.test/material.mtl"}
      },
      "texture": {"url": "https://example.test/texture.png"}
    }
    """)!, jobId);
    fixture.Ledger.Append(ReconstructionJobLedgerRecord.Complete(jobId, package.Id));

    var response = fixture.Handler.DispatchOffUi(
        $"{{\"op\":\"job_result\",\"job_id\":\"{jobId}\"}}");

    Assert.True(response.Success, JsonSerializer.Serialize(response.Data));
    var data = Assert.IsType<Dictionary<string, object?>>(response.Data);
    var summary = Assert.IsType<Dictionary<string, object?>>(data["package"]);
    Assert.Equal("model_glb", summary["preferred_asset_role"]);          // catalog preference, absent here
    Assert.Equal("model_obj", summary["resolved_import_role"]);          // what import will actually use
    Assert.NotEqual(summary["preferred_asset_role"], summary["resolved_import_role"]);
}

[Fact]
public async Task Result_ResolvedImportRole_NoImportableRole_IsNull_AndDoesNotThrow()
{
    // Materializer guarantees glb|obj, and the static fallback lists both — so null is unreachable for a
    // natural package. Force the defensive path: overwrite the manifest so no named role is present.
    var fixture = CreateFixture();
    fixture.Downloader.Files["https://example.test/model.obj"] = new byte[] { 1, 2, 3 };
    var jobId = Guid.NewGuid();
    var package = await BuildPackageAsync(fixture, JsonNode.Parse("""
    { "model_urls": { "obj": {"url": "https://example.test/model.obj"} } }
    """)!, jobId);
    fixture.Ledger.Append(ReconstructionJobLedgerRecord.Complete(jobId, package.Id));

    // Degenerate manifest: preferred names an absent role, fallback empty → ResolveAssetRole returns null.
    var manifestPath = fixture.Store.GetBlobAbsolutePath(package.Id, ReconstructionFileRoles.ImportManifest);
    File.WriteAllText(manifestPath, "{\"schema_version\":1,\"preferred_asset\":\"model_glb\",\"fallback_order\":[]}");

    var response = fixture.Handler.DispatchOffUi(
        $"{{\"op\":\"job_result\",\"job_id\":\"{jobId}\"}}");

    Assert.True(response.Success, JsonSerializer.Serialize(response.Data));
    var data = Assert.IsType<Dictionary<string, object?>>(response.Data);
    var summary = Assert.IsType<Dictionary<string, object?>>(data["package"]);
    Assert.Null(summary["resolved_import_role"]);
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug --filter "FullyQualifiedName~ResolvedImportRole"`
Expected: FAIL — the three tests fail on `summary["resolved_import_role"]` because the key does not exist yet (the dictionary lookup returns null for case 1/2, so `Assert.Equal("model_glb", null)` / `Assert.Equal("model_obj", null)` fail; case 3 would pass accidentally, which is fine — cases 1 and 2 prove the field is missing).

- [ ] **Step 3: Add the field in `PackageSummary`**

In `src/Rook/Handlers/ReconstructionOpHandler.cs`, `PackageSummary` currently reads the manifest for `preferred`. Compute the resolved role from that same manifest and add the field. Replace:

```csharp
            var preferred = (string?)null;
            var manifest = ReadImportManifest(packageId, out _);
            if (manifest is not null)
                preferred = ReadString(manifest, "preferred_asset");

            return new Dictionary<string, object?>
            {
                ["artifact_id"] = package.Id.ToString("D"),
                ["kind"] = package.Kind,
                ["asset_roles"] = package.Files
                    .Select(f => f.Role)
                    .Where(IsAssetRole)
                    .ToArray(),
                ["preferred_asset_role"] = preferred,
            };
```

with:

```csharp
            var preferred = (string?)null;
            var resolvedImportRole = (string?)null;
            var manifest = ReadImportManifest(packageId, out _);
            if (manifest is not null)
            {
                preferred = ReadString(manifest, "preferred_asset");
                // Same resolver the native import path uses (via prepare_import); passive — null on
                // unresolvable packages, never throws. Keeps the panel's "Import will use" honest.
                resolvedImportRole = ResolveAssetRole(package, manifest, requestedRole: null, out _);
            }

            return new Dictionary<string, object?>
            {
                ["artifact_id"] = package.Id.ToString("D"),
                ["kind"] = package.Kind,
                ["asset_roles"] = package.Files
                    .Select(f => f.Role)
                    .Where(IsAssetRole)
                    .ToArray(),
                ["preferred_asset_role"] = preferred,
                ["resolved_import_role"] = resolvedImportRole,
            };
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug --filter "FullyQualifiedName~ResolvedImportRole"`
Expected: PASS (3 passed).

- [ ] **Step 5: Extend the existing summary test**

In `DispatchOffUi_Result_ReturnsCompactPackageSummary`, after the existing `preferred_asset_role` assertion (~line 497), add:

```csharp
        Assert.Equal("model_glb", summary["resolved_import_role"]);
```

- [ ] **Step 6: Run the full handler test class**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug --filter "FullyQualifiedName~ReconstructionOpHandlerTests"`
Expected: PASS (all green).

- [ ] **Step 7: Commit**

```bash
git add src/Rook/Handlers/ReconstructionOpHandler.cs src/Rook.Tests/Handlers/ReconstructionOpHandlerTests.cs
git commit -m "feat(reconstruction): expose resolved_import_role in package summary"
```

---

### Task 2: Parity regression — panel prediction equals the import plan

**Files:**
- Test: `src/Rook.Tests/Handlers/ReconstructionOpHandlerTests.cs`

**Interfaces:**
- Consumes: `resolved_import_role` from Task 1; the existing `prepare_import` op (`DispatchOffUi`, returns `data["asset_role"]`). Test helpers as in Task 1.
- Produces: none (test-only guard).

This is the load-bearing test: it proves the exact promise — the panel's "Import will use" role equals the role the import plan will use — by exercising both `job_result` and `prepare_import` against the same package and asserting equality. It guards against the two paths drifting if either resolver changes.

- [ ] **Step 1: Write the parity test**

```csharp
[Fact]
public async Task ResolvedImportRole_MatchesPrepareImportAssetRole_ForSamePackage()
{
    // Preferred (model_glb) missing, fallback (model_obj) present — the live textured-Hunyuan shape.
    var fixture = CreateFixture();
    fixture.Downloader.Files["https://example.test/model.obj"] = new byte[] { 1, 2, 3 };
    fixture.Downloader.Files["https://example.test/material.mtl"] = new byte[] { 4, 5, 6 };
    fixture.Downloader.Files["https://example.test/texture.png"] = new byte[] { 7, 8, 9 };
    var jobId = Guid.NewGuid();
    var package = await BuildPackageAsync(fixture, JsonNode.Parse("""
    {
      "model_urls": {
        "obj": {"url": "https://example.test/model.obj"},
        "mtl": {"url": "https://example.test/material.mtl"}
      },
      "texture": {"url": "https://example.test/texture.png"}
    }
    """)!, jobId);
    fixture.Ledger.Append(ReconstructionJobLedgerRecord.Complete(jobId, package.Id));

    // Panel-side prediction.
    var resultResponse = fixture.Handler.DispatchOffUi(
        $"{{\"op\":\"job_result\",\"job_id\":\"{jobId}\"}}");
    Assert.True(resultResponse.Success, JsonSerializer.Serialize(resultResponse.Data));
    var resultData = Assert.IsType<Dictionary<string, object?>>(resultResponse.Data);
    var summary = Assert.IsType<Dictionary<string, object?>>(resultData["package"]);
    var predicted = Assert.IsType<string>(summary["resolved_import_role"]);
    Assert.Equal("model_obj", predicted);

    // Import-plan role for the SAME package, no assetRole override.
    var prepareResponse = fixture.Handler.DispatchOffUi(
        "{" +
        "\"op\":\"prepare_import\"," +
        $"\"package_id\":\"{package.Id}\"," +
        "\"import_id\":\"cafe1234-cafe-cafe-cafe-cafecafecafe\"" +
        "}");
    Assert.True(prepareResponse.Success, JsonSerializer.Serialize(prepareResponse.Data));
    var prepareData = Assert.IsType<Dictionary<string, object?>>(prepareResponse.Data);

    // The promise: the panel's prediction equals the import plan's role.
    Assert.Equal(predicted, prepareData["asset_role"]);
}
```

- [ ] **Step 2: Run the parity test**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug --filter "FullyQualifiedName~ResolvedImportRole_MatchesPrepareImportAssetRole"`
Expected: PASS — both paths derive from `ResolveAssetRole`, so the prediction equals the plan role. (This regression guard exercises already-correct behavior from Task 1; if the field were wrong or the two paths diverged, it would fail.)

- [ ] **Step 3: Commit**

```bash
git add src/Rook.Tests/Handlers/ReconstructionOpHandlerTests.cs
git commit -m "test(reconstruction): pin resolved_import_role == prepare_import asset_role"
```

---

### Task 3: UI — "Import will use" line + unimportable button state

**Files:**
- Modify: `src/Rook/UI/Vision/Resources/app.js` (`Reconstruct` module `renderResult`)
- Modify: `src/Rook/UI/Vision/Resources/styles.css` (one new class)

**Interfaces:**
- Consumes: `pkg.resolved_import_role` (Task 1) on `result.package` inside `renderResult`. Existing module state `currentPackageId`, `currentResultAvailable`; existing els `re.resultMeta`, `re.importBtn`, `setImportStatus`.
- Produces: none (UI display only). No new `index.html` id — the new line is a class-styled div inside the existing `#reconstruct-result-meta` container.

- [ ] **Step 1: Update the result-meta rendering and button gating**

In `app.js`, `renderResult`, replace the meta block and the button-state block. Find:

```javascript
        re.resultMeta.innerHTML = [
            `<div class="reconstruct-result-id">Package ${escapeHtml(packageId || "—")}</div>`,
            roles.length
                ? `<div class="reconstruct-result-roles">Assets: ${escapeHtml(roles.join(", "))}</div>`
                : "",
            preferred
                ? `<div class="reconstruct-result-preferred">Catalog preferred: ${escapeHtml(preferred)}</div>`
                : "",
        ].join("");

        renderWarnings(result.warnings);

        currentPackageId = packageId || null;
        currentResultAvailable = !!(packageId && result.result_available);
        re.importBtn.disabled = !currentResultAvailable;
        re.importBtn.textContent = "Import to Rhino";
        setImportStatus("", "");
```

Replace with:

```javascript
        const resolvedRole = pkg.resolved_import_role || "";
        re.resultMeta.innerHTML = [
            `<div class="reconstruct-result-id">Package ${escapeHtml(packageId || "—")}</div>`,
            roles.length
                ? `<div class="reconstruct-result-roles">Available assets: ${escapeHtml(roles.join(", "))}</div>`
                : "",
            preferred
                ? `<div class="reconstruct-result-preferred">Catalog preferred: ${escapeHtml(preferred)}</div>`
                : "",
            resolvedRole
                ? `<div class="reconstruct-result-resolved">Import will use: ${escapeHtml(resolvedRole)}</div>`
                : `<div class="reconstruct-result-resolved unavailable">Import unavailable: no importable model asset</div>`,
        ].join("");

        renderWarnings(result.warnings);

        // Import is possible only when the package is available AND the resolver names a role.
        const importable = !!(packageId && result.result_available && resolvedRole);
        currentPackageId = packageId || null;
        currentResultAvailable = importable;
        re.importBtn.disabled = !importable;
        re.importBtn.textContent = "Import to Rhino";
        setImportStatus("", "");
```

(`resolvedRole` is read from the field by code — never inferred from `asset_roles`. `currentResultAvailable` already gates the post-import-failure re-enable in `importPackage`'s `finally`, so an unimportable package stays disabled.)

- [ ] **Step 2: Add the style for the resolved line**

In `src/Rook/UI/Vision/Resources/styles.css`, after the `.reconstruct-result-id` rule (~line 2717), add:

```css
.reconstruct-result-resolved { font-weight: 600; }
.reconstruct-result-resolved.unavailable { color: var(--accent-red); font-weight: 400; }
```

- [ ] **Step 3: Run the panel-dark gate**

```bash
# Syntax check
node --check src/Rook/UI/Vision/Resources/app.js
# Duplicate-id scan in index.html (expect no output)
grep -oE 'id="[^"]+"' src/Rook/UI/Vision/Resources/index.html | sort | uniq -d
# Every $("id") referenced in the Reconstruct module must exist in index.html.
# List Reconstruct cacheEls ids and confirm each appears in index.html:
grep -oE '\$\("reconstruct-[^"]+"\)' src/Rook/UI/Vision/Resources/app.js | sort -u
```
Expected: `node --check` prints nothing (valid); duplicate-id scan prints nothing; every `reconstruct-*` id listed is present in `index.html` (no new ids were introduced this task — verify the set is unchanged from origin/main). No stale/removed symbols referenced.

- [ ] **Step 4: Commit**

```bash
git add src/Rook/UI/Vision/Resources/app.js src/Rook/UI/Vision/Resources/styles.css
git commit -m "feat(reconstruction-ui): show resolved import role; disable import when unimportable"
```

---

### Task 4: Full suite + live-smoke gate

**Files:** none (verification only).

- [ ] **Step 1: Run the full C# test suite**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug`
Expected: all green (prior baseline 2887/2887 plus the 4 new tests → 2891 passing; confirm zero failures).

- [ ] **Step 2: Managed Release build + deploy (Rhino closed)**

```bash
dotnet build-server shutdown   # release any MSBuild/Roslyn locks first
dotnet build src/Rook/Rook.csproj -c Release
```
Expected: build succeeds; `DeployToRhino` copies `Rook.rhp` into `%APPDATA%\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\{net48,net7.0,net8.0}`.

- [ ] **Step 3: Live smoke (merge gate)**

Open Rhino, open the Rook Vision panel → Reconstruct view. Run a real Hunyuan **textured** reconstruction whose catalog preferred is `model_glb` and delivered roles are `model_obj, material_mtl, texture, thumbnail`. Verify, before import:
- `Available assets: model_obj, material_mtl, texture, thumbnail`
- `Catalog preferred: model_glb`
- `Import will use: model_obj`

Then click **Import to Rhino** and verify the post-import copy `Imported N object(s) as model_obj` — i.e. the pre-import prediction and the post-import role agree.

- [ ] **Step 4: Finish the branch**

Use superpowers:finishing-a-development-branch to verify tests, then push + open PR (non-squash merge per project convention, on user direction).

---

## Self-Review

**Spec coverage:** backend field (Task 1), three resolution cases (Task 1), existing-summary-test extension (Task 1 Step 5), parity regression (Task 2), UI line + relabel + null button state (Task 3), panel-dark gate (Task 3 Step 3), full suite + live smoke (Task 4). All spec sections covered.

**Placeholder scan:** no TBD/TODO; all code blocks complete; exact commands with expected output.

**Type consistency:** field `resolved_import_role` used identically in backend dict, all tests, and `pkg.resolved_import_role` in JS. `ResolveAssetRole` signature matches its definition. `currentResultAvailable`/`currentPackageId`/`importable` consistent with the existing module state set by `resetResultForNewRun` and read in `importPackage`'s `finally`.
