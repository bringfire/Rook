# RookVision Reveal Artifact File Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a per-image `Show in Folder` button to the RookVision Gallery modal that opens Windows Explorer with the modal's currently displayed artifact image selected.

**Architecture:** The client passes the artifact id and the exact display role already chosen by `pickDisplayRole`. The C# bridge routes a new off-UI op, `reveal_artifact_file`, to `VisionHandler`, which resolves the role through `ArtifactStore.GetBlobAbsolutePath` and launches `explorer.exe /select,"<absolute-path>"`. Unit tests cover op routing, path resolution, exception mapping helpers, embedded resource wiring, and the Explorer `ProcessStartInfo`; they do not launch Explorer.

**Tech Stack:** C#/.NET, xUnit, Rhino companion `Rook` project, WebView2 embedded resources, plain JavaScript, CSS, Windows Explorer shell integration.

---

## Source Documents

- Design: `C:\Users\aryan\source\repos\rook_docs\2026-04-25-vision-reveal-artifact-design.md`
- Work queue: `C:\Users\aryan\source\repos\rook_docs\work-queue.md`
- Repo root: `C:\Users\aryan\source\repos\Rook`

Before implementing, fix these wording issues in the design doc if they are still present:

- Replace `VisionWebSurface._opRoutes` with `VisionWebSurface.OpRoutes`.
- Replace `VisionHandler.DispatchUi` with `VisionHandler.Dispatch` or "sync UI-thread dispatcher".
- Replace "modal status mechanism" with "existing `showStatus(message, \"error\")` mechanism".

The wording cleanup is documentation-only and should not change the implementation below.

---

## Files To Modify

- `src/Rook/Handlers/VisionHandler.cs`
  - Add `reveal_artifact_file` to the off-UI dispatcher.
  - Add the op to wrong-dispatcher rejection chains in `Dispatch` and `DispatchAsync`.
  - Add role validation, path resolver, Explorer helper, and `RevealArtifactFile`.

- `src/Rook/UI/Vision/VisionWebSurface.cs`
  - Add `["reveal_artifact_file"] = VisionOpRoute.OffUi` to `OpRoutes`.

- `src/Rook/UI/Vision/Resources/index.html`
  - Add `modal-reveal-btn` between Approve and Delete in the modal action row.

- `src/Rook/UI/Vision/Resources/app.js`
  - Track `modalDisplayRole`.
  - Wire the button to `bridgeCall("reveal_artifact_file", { artifact_id, role })`.

- `src/Rook/UI/Vision/Resources/styles.css`
  - Add `flex-wrap: wrap` to `.modal-actions`.

- `src/Rook.Tests/Handlers/VisionHandlerTests.cs`
  - Add helper tests for reveal path resolution, argument validation, failure mapping, and `BuildRevealFileStartInfo`.

- `src/Rook.Tests/UI/Vision/VisionWebSurfaceTests.cs`
  - Update op routing tests from 14 to 15 ops.
  - Add embedded-resource tests for modal button and JS wiring.

---

## Task 1: Add Server-Side Helper Tests

**Files:**
- Modify: `src/Rook.Tests/Handlers/VisionHandlerTests.cs`
- Later implementation target: `src/Rook/Handlers/VisionHandler.cs`

- [ ] **Step 1: Add `using System.Diagnostics;` only if the compiler requires it**

`VisionHandlerTests.cs` already has most required imports. If assertions against `ProcessStartInfo` compile without an extra using, do not add one.

- [ ] **Step 2: Add these helper methods inside `VisionHandlerTests`**

Place these near the top of the class after the existing artifact kind tests, before the model catalog tests.

```csharp
private static Dictionary<string, JsonElement> ParseArgs(string json)
    => VisionHandler.ParseObjectBody(json);

private static string CreateTempRoot(string name)
{
    var root = Path.Combine(Path.GetTempPath(), name + "-" + Guid.NewGuid().ToString("N"));
    Directory.CreateDirectory(root);
    return root;
}
```

- [ ] **Step 3: Add a failing test for the Explorer helper**

Add this test after `BuildOpenFolderStartInfo_UsesShellExecuteForCanonicalFolderPath`.

```csharp
[Fact]
public void BuildRevealFileStartInfo_SelectsCanonicalFilePath()
{
    var path = Path.Combine(Path.GetTempPath(), "rook vision image.png");

    var psi = VisionHandler.BuildRevealFileStartInfo(path);

    Assert.Equal("explorer.exe", psi.FileName);
    Assert.Equal($"/select,\"{Path.GetFullPath(path)}\"", psi.Arguments);
}
```

- [ ] **Step 4: Add failing tests for argument validation and successful path resolution**

Add these tests after the Explorer helper test.

```csharp
[Fact]
public void ResolveArtifactFilePathForReveal_ReturnsCanonicalBlobPath()
{
    var root = CreateTempRoot("rook-vision-reveal-success");
    try
    {
        var store = new ArtifactStore(root);
        var artifact = store.Create(
            VisionHandler.ArtifactKindGeneratedImage,
            new[] { new BlobInput("image", new byte[] { 1, 2, 3 }, "png") });
        var args = ParseArgs(
            $"{{\"artifact_id\":\"{artifact.Id:D}\",\"role\":\"image\"}}");

        var path = VisionHandler.ResolveArtifactFilePathForReveal(store, args);

        Assert.Equal(Path.GetFullPath(Path.Combine(
            root,
            artifact.CreatedAt.ToString("yyyy-MM-dd"),
            artifact.Id.ToString("D"),
            "image.png")), path);
    }
    finally
    {
        try { Directory.Delete(root, recursive: true); } catch { }
    }
}

[Theory]
[InlineData("{}")]
[InlineData("{\"artifact_id\":42,\"role\":\"image\"}")]
[InlineData("{\"artifact_id\":\"\",\"role\":\"image\"}")]
[InlineData("{\"artifact_id\":\"not-a-guid\",\"role\":\"image\"}")]
public void ResolveArtifactFilePathForReveal_RequiresArtifactId(string json)
{
    var root = CreateTempRoot("rook-vision-reveal-bad-id");
    try
    {
        var store = new ArtifactStore(root);
        var args = ParseArgs(json);

        Assert.Throws<ArgumentException>(() =>
            VisionHandler.ResolveArtifactFilePathForReveal(store, args));
    }
    finally
    {
        try { Directory.Delete(root, recursive: true); } catch { }
    }
}

[Theory]
[InlineData("{\"artifact_id\":\"00000000-0000-0000-0000-000000000000\"}")]
[InlineData("{\"artifact_id\":\"00000000-0000-0000-0000-000000000000\",\"role\":42}")]
[InlineData("{\"artifact_id\":\"00000000-0000-0000-0000-000000000000\",\"role\":\"\"}")]
[InlineData("{\"artifact_id\":\"00000000-0000-0000-0000-000000000000\",\"role\":\"   \"}")]
public void ResolveArtifactFilePathForReveal_RequiresRole(string json)
{
    var root = CreateTempRoot("rook-vision-reveal-bad-role");
    try
    {
        var store = new ArtifactStore(root);
        var args = ParseArgs(json);

        Assert.Throws<ArgumentException>(() =>
            VisionHandler.ResolveArtifactFilePathForReveal(store, args));
    }
    finally
    {
        try { Directory.Delete(root, recursive: true); } catch { }
    }
}
```

- [ ] **Step 5: Add failing tests for role-missing, file-missing, and traversal behavior**

Add these tests after the validation tests.

```csharp
[Fact]
public void ResolveArtifactFilePathForReveal_MissingRole_ThrowsKeyNotFound()
{
    var root = CreateTempRoot("rook-vision-reveal-missing-role");
    try
    {
        var store = new ArtifactStore(root);
        var artifact = store.Create(
            VisionHandler.ArtifactKindGeneratedImage,
            new[] { new BlobInput("thumbnail", new byte[] { 1 }, "png") });
        var args = ParseArgs(
            $"{{\"artifact_id\":\"{artifact.Id:D}\",\"role\":\"image\"}}");

        Assert.Throws<KeyNotFoundException>(() =>
            VisionHandler.ResolveArtifactFilePathForReveal(store, args));
    }
    finally
    {
        try { Directory.Delete(root, recursive: true); } catch { }
    }
}

[Fact]
public void ResolveArtifactFilePathForReveal_MissingBlob_ThrowsFileNotFound()
{
    var root = CreateTempRoot("rook-vision-reveal-missing-file");
    try
    {
        var store = new ArtifactStore(root);
        var artifact = store.Create(
            VisionHandler.ArtifactKindGeneratedImage,
            new[] { new BlobInput("image", new byte[] { 1 }, "png") });
        var blobPath = store.GetBlobAbsolutePath(artifact.Id, "image");
        File.Delete(blobPath);
        var args = ParseArgs(
            $"{{\"artifact_id\":\"{artifact.Id:D}\",\"role\":\"image\"}}");

        Assert.Throws<FileNotFoundException>(() =>
            VisionHandler.ResolveArtifactFilePathForReveal(store, args));
    }
    finally
    {
        try { Directory.Delete(root, recursive: true); } catch { }
    }
}

[Fact]
public void ResolveArtifactFilePathForReveal_TraversalManifest_SurfacesInvalidData()
{
    var root = CreateTempRoot("rook-vision-reveal-traversal");
    try
    {
        var store = new ArtifactStore(root);
        var artifact = store.Create(
            VisionHandler.ArtifactKindGeneratedImage,
            new[] { new BlobInput("image", new byte[] { 1 }, "png") });
        var artifactDir = Path.GetDirectoryName(store.GetBlobAbsolutePath(artifact.Id, "image"))!;
        var manifestPath = Path.Combine(artifactDir, "manifest.json");
        var manifest = File.ReadAllText(manifestPath)
            .Replace("\"path\": \"image.png\"", "\"path\": \"..\\\\outside.png\"");
        File.WriteAllText(manifestPath, manifest);
        var args = ParseArgs(
            $"{{\"artifact_id\":\"{artifact.Id:D}\",\"role\":\"image\"}}");

        var ex = Assert.Throws<InvalidDataException>(() =>
            VisionHandler.ResolveArtifactFilePathForReveal(store, args));
        Assert.Contains("path", ex.Message, StringComparison.OrdinalIgnoreCase);
    }
    finally
    {
        try { Directory.Delete(root, recursive: true); } catch { }
    }
}
```

- [ ] **Step 6: Run the handler tests and verify they fail for missing members**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~VisionHandlerTests" 
```

Expected: build fails because `BuildRevealFileStartInfo` and `ResolveArtifactFilePathForReveal` do not exist yet.

---

## Task 2: Implement Server-Side Reveal Helpers And Handler

**Files:**
- Modify: `src/Rook/Handlers/VisionHandler.cs`
- Test: `src/Rook.Tests/Handlers/VisionHandlerTests.cs`

- [ ] **Step 1: Add constants and role validation helper**

In `VisionHandler.cs`, near the artifact-management helpers around `RequireArtifactId`, add:

```csharp
internal const string RevealFileUnavailableMessage =
    "Image file is no longer available on disk.";

internal static string RequireNonEmptyString(
    Dictionary<string, JsonElement> args, string field)
{
    if (!args.TryGetValue(field, out var el) || el.ValueKind != JsonValueKind.String)
    {
        throw new ArgumentException($"Missing or non-string field '{field}'.");
    }

    var raw = el.GetString();
    if (string.IsNullOrWhiteSpace(raw))
    {
        throw new ArgumentException($"Field '{field}' must be non-empty.");
    }

    return raw;
}
```

- [ ] **Step 2: Add the testable path resolver**

Add this near `RequireArtifactId` and `RequireNonEmptyString`:

```csharp
internal static string ResolveArtifactFilePathForReveal(
    ArtifactStore artifactStore,
    Dictionary<string, JsonElement> args)
{
    if (artifactStore is null)
    {
        throw new ArgumentNullException(nameof(artifactStore));
    }

    var id = RequireArtifactId(args);
    var role = RequireNonEmptyString(args, "role");
    return artifactStore.GetBlobAbsolutePath(id, role);
}
```

- [ ] **Step 3: Add the Explorer helper**

Add this next to `BuildOpenFolderStartInfo`:

```csharp
internal static ProcessStartInfo BuildRevealFileStartInfo(string filePath)
    => new()
    {
        FileName = "explorer.exe",
        Arguments = $"/select,\"{Path.GetFullPath(filePath)}\"",
    };
```

- [ ] **Step 4: Add the `RevealArtifactFile` handler**

Place this immediately after `OpenArtifactsFolder` so the two shell operations stay together.

```csharp
// ─── op: reveal_artifact_file (off-UI) ───────────────────────────

/// <summary>
/// Reveal a specific artifact blob in Explorer. The caller supplies
/// the artifact id and role; the path itself is resolved through the
/// artifact store so callers cannot pass arbitrary filesystem paths.
/// </summary>
internal ApiResponse RevealArtifactFile(Dictionary<string, JsonElement> args)
{
    string filePath;
    try
    {
        filePath = ResolveArtifactFilePathForReveal(_artifactStore, args);
    }
    catch (KeyNotFoundException)
    {
        return Fail(RevealFileUnavailableMessage);
    }
    catch (FileNotFoundException)
    {
        return Fail(RevealFileUnavailableMessage);
    }

    using var shellProcess = Process.Start(BuildRevealFileStartInfo(filePath));

    return Ok(new Dictionary<string, object?>
    {
        ["path"] = Path.GetFullPath(filePath),
        ["opened"] = true,
    });
}
```

Do not catch `InvalidDataException` here. `DispatchOffUi` already catches it and returns its real message, which is required for traversal or manifest-integrity failures.

- [ ] **Step 5: Wire `reveal_artifact_file` into `DispatchOffUi`**

In `DispatchOffUi`, add the new op next to `open_artifacts_folder`:

```csharp
"open_artifacts_folder" => OpenArtifactsFolder(args),
"reveal_artifact_file" => RevealArtifactFile(args),
```

- [ ] **Step 6: Add wrong-dispatcher rejection in `Dispatch`**

In the off-UI rejection group inside `Dispatch`, include `reveal_artifact_file`:

```csharp
"list_artifacts" or "get_artifact" or "approve_artifact"
    or "delete_artifact" or "consume_approved"
    or "set_api_key" or "get_settings_overview"
    or "open_artifacts_folder" or "reveal_artifact_file" => Fail(
    $"op '{op}' must be routed through the off-UI dispatcher, not the sync UI-thread dispatcher."),
```

- [ ] **Step 7: Add wrong-dispatcher rejection in `DispatchAsync`**

In the off-UI rejection group inside `DispatchAsync`, include `reveal_artifact_file`:

```csharp
"list_artifacts" or "get_artifact" or "approve_artifact"
    or "delete_artifact" or "consume_approved"
    or "set_api_key" or "get_settings_overview"
    or "open_artifacts_folder" or "reveal_artifact_file" => Fail(
    $"op '{op}' must be routed through the off-UI dispatcher, not the async dispatcher."),
```

- [ ] **Step 8: Run the focused handler tests**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~VisionHandlerTests"
```

Expected: handler tests pass, except possible compile failures from missing op routing tests added in later tasks are not present yet.

- [ ] **Step 9: Commit server helper work**

```powershell
git add src/Rook/Handlers/VisionHandler.cs src/Rook.Tests/Handlers/VisionHandlerTests.cs
git commit -m "Add Vision artifact reveal helpers"
```

---

## Task 3: Add Bridge Op Route Tests And Routing

**Files:**
- Modify: `src/Rook/UI/Vision/VisionWebSurface.cs`
- Modify: `src/Rook.Tests/UI/Vision/VisionWebSurfaceTests.cs`

- [ ] **Step 1: Update `OpRoutes_Contains_All_Expected_Ops`**

In `VisionWebSurfaceTests.cs`, add `reveal_artifact_file` after `open_artifacts_folder`:

```csharp
"set_api_key", "get_settings_overview",
"open_artifacts_folder", "reveal_artifact_file",
```

The count assertion should remain:

```csharp
Assert.Equal(expected.Length, VisionWebSurface.OpRoutes.Count);
```

- [ ] **Step 2: Update `OpRoutes_Map_To_Correct_Dispatchers`**

Add this inline data next to `open_artifacts_folder`:

```csharp
[InlineData("reveal_artifact_file", "OffUi")]
```

- [ ] **Step 3: Run route tests and verify failure**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~VisionWebSurfaceTests.OpRoutes"
```

Expected: tests fail because `VisionWebSurface.OpRoutes` does not include `reveal_artifact_file` yet.

- [ ] **Step 4: Add the op to `VisionWebSurface.OpRoutes`**

In `src/Rook/UI/Vision/VisionWebSurface.cs`, add:

```csharp
["open_artifacts_folder"] = VisionOpRoute.OffUi,
["reveal_artifact_file"] = VisionOpRoute.OffUi,
```

- [ ] **Step 5: Run route tests again**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~VisionWebSurfaceTests.OpRoutes"
```

Expected: op-route tests pass.

- [ ] **Step 6: Commit route work**

```powershell
git add src/Rook/UI/Vision/VisionWebSurface.cs src/Rook.Tests/UI/Vision/VisionWebSurfaceTests.cs
git commit -m "Route Vision artifact reveal op"
```

---

## Task 4: Add Modal Button HTML And Embedded Resource Tests

**Files:**
- Modify: `src/Rook/UI/Vision/Resources/index.html`
- Modify: `src/Rook/UI/Vision/Resources/styles.css`
- Modify: `src/Rook.Tests/UI/Vision/VisionWebSurfaceTests.cs`

- [ ] **Step 1: Add failing HTML and CSS resource tests**

In `VisionWebSurfaceTests.cs`, add these tests near the existing embedded-resource tests:

```csharp
[Fact]
public void IndexHtml_Modal_ExposesRevealButtonBetweenApproveAndDelete()
{
    var html = ReadVisionResource("index.html");
    var approveIndex = html.IndexOf("id=\"modal-approve-btn\"", StringComparison.Ordinal);
    var revealIndex = html.IndexOf("id=\"modal-reveal-btn\"", StringComparison.Ordinal);
    var deleteIndex = html.IndexOf("id=\"modal-delete-btn\"", StringComparison.Ordinal);

    Assert.True(approveIndex >= 0, "modal approve button is missing.");
    Assert.True(revealIndex >= 0, "modal reveal button is missing.");
    Assert.True(deleteIndex >= 0, "modal delete button is missing.");
    Assert.True(approveIndex < revealIndex, "reveal button should come after approve.");
    Assert.True(revealIndex < deleteIndex, "reveal button should come before delete.");
    Assert.Contains("Show in Folder", html);
    Assert.Contains("title=\"Show this image file in its artifact folder\"", html);
    Assert.Contains("aria-label=\"Show this image file in its artifact folder\"", html);
}

[Fact]
public void StylesCss_ModalActions_CanWrap()
{
    var css = ReadVisionResource("styles.css");
    Assert.Contains(".modal-actions", css);
    Assert.Contains("flex-wrap: wrap;", css);
}
```

- [ ] **Step 2: Run resource tests and verify failure**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~IndexHtml_Modal_ExposesRevealButtonBetweenApproveAndDelete|FullyQualifiedName~StylesCss_ModalActions_CanWrap"
```

Expected: tests fail because `modal-reveal-btn` and `flex-wrap: wrap` are not present.

- [ ] **Step 3: Add the modal button**

In `src/Rook/UI/Vision/Resources/index.html`, replace the modal action row with this exact structure:

```html
<div class="modal-actions">
    <button id="modal-approve-btn" class="btn btn-secondary" title="Mark this image as approved so Rook can use it as the selected concept for downstream workflows." aria-label="Mark this image as approved so Rook can use it as the selected concept for downstream workflows.">Approve</button>
    <button id="modal-reveal-btn" class="btn btn-secondary" title="Show this image file in its artifact folder" aria-label="Show this image file in its artifact folder">Show in Folder</button>
    <button id="modal-delete-btn" class="btn btn-secondary btn-danger">Delete</button>
</div>
```

This preserves the approved placement: `[Approve] [Show in Folder] [Delete]`.

- [ ] **Step 4: Add wrapping to modal actions**

In `src/Rook/UI/Vision/Resources/styles.css`, update `.modal-actions`:

```css
.modal-actions {
    display: flex;
    gap: var(--space-1);
    flex-wrap: wrap;
}
```

- [ ] **Step 5: Run resource tests again**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~IndexHtml_Modal_ExposesRevealButtonBetweenApproveAndDelete|FullyQualifiedName~StylesCss_ModalActions_CanWrap"
```

Expected: both tests pass.

- [ ] **Step 6: Commit modal resource work**

```powershell
git add src/Rook/UI/Vision/Resources/index.html src/Rook/UI/Vision/Resources/styles.css src/Rook.Tests/UI/Vision/VisionWebSurfaceTests.cs
git commit -m "Add Vision modal reveal button"
```

---

## Task 5: Add JavaScript State And Bridge Wiring

**Files:**
- Modify: `src/Rook/UI/Vision/Resources/app.js`
- Modify: `src/Rook.Tests/UI/Vision/VisionWebSurfaceTests.cs`

- [ ] **Step 1: Add failing JavaScript resource test**

In `VisionWebSurfaceTests.cs`, add this near the existing `AppJs_GalleryToolbar_OpensArtifactsFolder` test:

```csharp
[Fact]
public void AppJs_ModalRevealButton_RevealsCurrentArtifactRole()
{
    var js = ReadVisionResource("app.js");
    Assert.Contains("let modalDisplayRole = null;", js);
    Assert.Contains("modalDisplayRole = pickDisplayRole(modalArtifact);", js);
    Assert.Contains("async function revealCurrentArtifact()", js);
    Assert.Contains("bridgeCall(\"reveal_artifact_file\"", js);
    Assert.Contains("role: modalDisplayRole", js);
    Assert.Contains("el.modalRevealBtn = $(\"modal-reveal-btn\");", js);
    Assert.Contains("el.modalRevealBtn.addEventListener(\"click\", revealCurrentArtifact);", js);
}
```

- [ ] **Step 2: Run JS resource test and verify failure**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~AppJs_ModalRevealButton_RevealsCurrentArtifactRole"
```

Expected: test fails because the JS wiring does not exist.

- [ ] **Step 3: Add modal display role state**

In `src/Rook/UI/Vision/Resources/app.js`, in the state block near `modalArtifact`, change:

```js
let modalArtifact = null;             // currently-open gallery item
let modelCatalog = [];                 // [{ short_name, supported_resolutions, ... }]
```

to:

```js
let modalArtifact = null;             // currently-open gallery item
let modalDisplayRole = null;          // blob role currently rendered in the modal image
let modelCatalog = [];                 // [{ short_name, supported_resolutions, ... }]
```

- [ ] **Step 4: Store the display role in `openArtifactModal`**

In `openArtifactModal`, replace:

```js
const role = pickDisplayRole(modalArtifact);
const src = role
    ? `/blob/${encodeURIComponent(id)}/${encodeURIComponent(role)}?ts=${Date.now()}`
    : "";
```

with:

```js
modalDisplayRole = pickDisplayRole(modalArtifact);
const src = modalDisplayRole
    ? `/blob/${encodeURIComponent(id)}/${encodeURIComponent(modalDisplayRole)}?ts=${Date.now()}`
    : "";
```

- [ ] **Step 5: Reset display role in `closeModal`**

In `closeModal`, change:

```js
modalArtifact = null;
```

to:

```js
modalArtifact = null;
modalDisplayRole = null;
```

- [ ] **Step 6: Add `revealCurrentArtifact`**

Place this function after `approveCurrentArtifact` and before `deleteCurrentArtifact`:

```js
async function revealCurrentArtifact() {
    if (!modalArtifact || !modalDisplayRole) return;
    try {
        await bridgeCall("reveal_artifact_file", {
            artifact_id: modalArtifact.artifact_id,
            role: modalDisplayRole,
        });
    } catch (e) {
        showStatus(e.message, "error");
    }
}
```

- [ ] **Step 7: Cache the reveal button element**

In `init`, in the Modal element block, change:

```js
el.modalApproveBtn = $("modal-approve-btn");
el.modalDeleteBtn = $("modal-delete-btn");
el.modalClose = document.querySelector(".modal-close");
```

to:

```js
el.modalApproveBtn = $("modal-approve-btn");
el.modalRevealBtn = $("modal-reveal-btn");
el.modalDeleteBtn = $("modal-delete-btn");
el.modalClose = document.querySelector(".modal-close");
```

- [ ] **Step 8: Wire the click handler**

In `init`, in the modal event block, insert this between approve and delete:

```js
el.modalRevealBtn.addEventListener("click", revealCurrentArtifact);
```

The surrounding block should read:

```js
el.modalApproveBtn.addEventListener("click", () => {
    if (modalArtifact) approveCurrentArtifact(modalArtifact.artifact_id);
});
el.modalRevealBtn.addEventListener("click", revealCurrentArtifact);
el.modalDeleteBtn.addEventListener("click", () => {
    if (modalArtifact) deleteCurrentArtifact(modalArtifact.artifact_id);
});
```

- [ ] **Step 9: Run JS resource test again**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~AppJs_ModalRevealButton_RevealsCurrentArtifactRole"
```

Expected: test passes.

- [ ] **Step 10: Commit JS wiring**

```powershell
git add src/Rook/UI/Vision/Resources/app.js src/Rook.Tests/UI/Vision/VisionWebSurfaceTests.cs
git commit -m "Wire Vision modal reveal action"
```

---

## Task 6: Add Failure Mapping Coverage Without Launching Explorer

**Files:**
- Modify: `src/Rook.Tests/Handlers/VisionHandlerTests.cs`
- Modify: `src/Rook/Handlers/VisionHandler.cs`

This task adds a tiny static mapper so tests can pin the UX message policy without calling `Process.Start`.

- [ ] **Step 1: Add failing mapper tests**

In `VisionHandlerTests.cs`, add these after the resolver tests:

```csharp
[Fact]
public void TryMapRevealArtifactFileException_MapsMissingArtifactAndMissingBlob()
{
    Assert.True(VisionHandler.TryMapRevealArtifactFileException(
        new KeyNotFoundException("missing"), out var keyMessage));
    Assert.Equal(VisionHandler.RevealFileUnavailableMessage, keyMessage);

    Assert.True(VisionHandler.TryMapRevealArtifactFileException(
        new FileNotFoundException("missing"), out var fileMessage));
    Assert.Equal(VisionHandler.RevealFileUnavailableMessage, fileMessage);
}

[Fact]
public void TryMapRevealArtifactFileException_DoesNotMaskInvalidDataOrBadArgs()
{
    Assert.False(VisionHandler.TryMapRevealArtifactFileException(
        new InvalidDataException("Manifest path escapes artifact directory."), out var invalidDataMessage));
    Assert.Null(invalidDataMessage);

    Assert.False(VisionHandler.TryMapRevealArtifactFileException(
        new ArgumentException("Missing role."), out var argumentMessage));
    Assert.Null(argumentMessage);
}
```

- [ ] **Step 2: Run mapper tests and verify failure**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~TryMapRevealArtifactFileException"
```

Expected: tests fail because the mapper does not exist.

- [ ] **Step 3: Implement the mapper**

In `VisionHandler.cs`, near `ResolveArtifactFilePathForReveal`, add:

```csharp
internal static bool TryMapRevealArtifactFileException(
    Exception ex,
    out string? message)
{
    if (ex is KeyNotFoundException or FileNotFoundException)
    {
        message = RevealFileUnavailableMessage;
        return true;
    }

    message = null;
    return false;
}
```

- [ ] **Step 4: Use the mapper in `RevealArtifactFile`**

Replace the two specific catch blocks in `RevealArtifactFile`:

```csharp
catch (KeyNotFoundException)
{
    return Fail(RevealFileUnavailableMessage);
}
catch (FileNotFoundException)
{
    return Fail(RevealFileUnavailableMessage);
}
```

with:

```csharp
catch (Exception ex) when (TryMapRevealArtifactFileException(ex, out var message))
{
    return Fail(message!);
}
```

Do not catch `InvalidDataException` or `ArgumentException` through this mapper.

- [ ] **Step 5: Run mapper and handler tests**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~VisionHandlerTests"
```

Expected: all `VisionHandlerTests` pass.

- [ ] **Step 6: Commit failure mapping**

```powershell
git add src/Rook/Handlers/VisionHandler.cs src/Rook.Tests/Handlers/VisionHandlerTests.cs
git commit -m "Pin Vision reveal failure mapping"
```

---

## Task 7: Run Full Focused Validation

**Files:**
- No source edits expected.

- [ ] **Step 1: Run the full Vision handler and web-surface test slice**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~VisionWebSurfaceTests|FullyQualifiedName~VisionHandlerTests"
```

Expected:

```text
Passed!
```

Record the total test count in the PR body. The previous baseline after PR #105 was 190 tests for this slice; the count should increase by the tests added in this plan.

- [ ] **Step 2: Build and deploy the managed companion**

Run:

```powershell
dotnet build src/Rook/Rook.csproj -f net7.0
```

Expected:

```text
Build succeeded.
    0 Warning(s)
    0 Error(s)
```

The project deploy target should copy `Rook.rhp` to `%APPDATA%\McNeel\Rhinoceros\8.0\Plug-ins\RookNative`.

- [ ] **Step 3: Verify deployed file timestamp**

Run:

```powershell
Get-Item "$env:APPDATA\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\Rook.rhp" |
    Select-Object FullName,LastWriteTime,Length
```

Expected: `LastWriteTime` updates to the current build time and `Length` is non-zero.

- [ ] **Step 4: Manual Rhino smoke**

In Rhino 8:

1. Run `/ShowRookVision`.
2. Open Gallery.
3. Click a generated image to open the modal.
4. Click `Show in Folder`.
5. Confirm Explorer opens the artifact directory with the displayed image selected.
6. Confirm `Approve` and `Delete` still work from the same modal.
7. Confirm the modal action row wraps cleanly if the panel is docked narrow.

Expected: no new artifacts are created by clicking `Show in Folder`; this is a read-only file reveal.

---

## Task 8: Prepare PR

**Files:**
- Include only files touched by this feature.
- Do not stage unrelated local dirt such as `knowledge/*`, scratch files, or MCP probe scripts.

- [ ] **Step 1: Inspect status**

Run:

```powershell
git status -sb
```

Expected: only the planned Vision files are modified or staged.

- [ ] **Step 2: If tasks were committed separately, keep commits or squash locally by preference**

For a small branch, either multiple clear commits or one squash commit is acceptable before opening the PR. If squashing locally, use non-interactive commands only.

- [ ] **Step 3: Push branch**

Run:

```powershell
git push -u origin <branch-name>
```

- [ ] **Step 4: Open draft PR**

Use this PR body structure:

```markdown
## Summary
- Adds per-image `Show in Folder` to the RookVision Gallery modal.
- Routes new off-UI `reveal_artifact_file` op through the Vision bridge.
- Resolves files by artifact id + role through `ArtifactStore.GetBlobAbsolutePath`.
- Opens Explorer with `/select,` so the displayed image is highlighted.

## Validation
- `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~VisionWebSurfaceTests|FullyQualifiedName~VisionHandlerTests"` - passed, <count> tests.
- `dotnet build src/Rook/Rook.csproj -f net7.0` - succeeded.
- Rhino smoke: `/ShowRookVision` -> Gallery modal -> `Show in Folder` opened Explorer with selected image.

## Notes
- `open_artifacts_folder` remains the global artifact-root action.
- `reveal_artifact_file` is role-explicit and does not accept arbitrary filesystem paths.
- Missing artifact role or missing blob returns `Image file is no longer available on disk.`
```

---

## Self-Review Checklist

- [ ] The design doc wording uses `VisionWebSurface.OpRoutes`, not `_opRoutes`.
- [ ] The design doc wording uses `VisionHandler.Dispatch`, not `DispatchUi`.
- [ ] The implementation does not add a generic arbitrary-path reveal op.
- [ ] The JS passes `modalDisplayRole`; the server does not re-run display-role selection.
- [ ] `InvalidDataException` is not masked as `Image file is no longer available on disk.`
- [ ] Unit tests do not launch Explorer.
- [ ] `.modal-actions` has `flex-wrap: wrap`.
- [ ] Focused tests and `net7.0` build were run after the final source edit.
