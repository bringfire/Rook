# RookVision Video Sidecar Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lock RookVision generated-video sidecar consumption semantics so `poster` remains display-only, `start_frame` / `end_frame` are the only frame-picker roles, and provider payload audits are cost-gated.

**Architecture:** This is a substrate and UI-consumption slice only. The implementation adds role-level picker choice generation in `app.js`, source-level UI tests, provider non-inference tests, and audit documentation/fixtures; it does not produce new sidecar blobs or change video job persistence.

**Tech Stack:** C# xUnit tests, Rook managed Vision video services, embedded RookVision WebView assets (`index.html`, `app.js`, `styles.css`), Markdown docs, JSON sanitized examples.

---

## File Structure

- Create `src/Rook.Tests/UI/Vision/VisionVideoSidecarContractSourceTests.cs`
  - Source-level tests for `app.js` role-level picker behavior and Gallery poster/playback separation.

- Modify `src/Rook/UI/Vision/Resources/app.js`
  - Add frame-picker role constants and helper functions.
  - Update `openPicker(slot)` to request `generated_video` artifacts and flatten them into role-level choices only for `start_frame` and `end_frame`.

- Modify `src/Rook.Tests/Services/Vision/Video/VeoProviderTests.cs`
  - Add a provider-status non-inference test proving sidecar-like Veo payload fields do not create provider artifacts or sidecar state.

- Modify `src/Rook.Tests/Services/Vision/Video/Fal/FalVideoProviderTests.cs`
  - Add a fetch-result non-inference test proving sidecar-like fal fields still produce exactly one `video` artifact.

- Create `docs/rook_docs/video-provider-payload-audit.md`
  - Document the live-provider audit procedure, redaction rules, fixtures, and cost-gated follow-up checklist.

- Create `docs/rook_docs/fixtures/video-provider-payload-audit/veo-completion.sanitized.example.json`
  - Sanitized placeholder shape for a completed Veo operation payload.

- Create `docs/rook_docs/fixtures/video-provider-payload-audit/fal-result.sanitized.example.json`
  - Sanitized placeholder shape for a fal result payload.

- Create `src/Rook.Tests/Services/Vision/Video/VideoProviderPayloadAuditDocsTests.cs`
  - Source-level tests that pin redaction rules and the explicit no-live-generation boundary in the audit procedure.

---

### Task 1: Add Failing UI Contract Tests

**Files:**
- Create: `src/Rook.Tests/UI/Vision/VisionVideoSidecarContractSourceTests.cs`
- Read: `src/Rook/UI/Vision/Resources/app.js`

- [ ] **Step 1: Create the failing source-level tests**

Create `src/Rook.Tests/UI/Vision/VisionVideoSidecarContractSourceTests.cs` with this content:

```csharp
using System;
using System.IO;
using Xunit;

namespace Rook.Tests.UI.Vision
{
    public class VisionVideoSidecarContractSourceTests
    {
        [Fact]
        public void AppJs_FramePickerDefinesGeneratedVideoFrameRolesOnly()
        {
            var js = ReadVisionResource("app.js");

            Assert.Contains(
                "const GENERATED_VIDEO_FRAME_PICKER_ROLES = new Set([\"start_frame\", \"end_frame\"]);",
                js);
            Assert.Contains("function isGeneratedVideoFramePickerRole(role)", js);
            Assert.Contains("return GENERATED_VIDEO_FRAME_PICKER_ROLES.has(role);", js);
            Assert.DoesNotContain("GENERATED_VIDEO_FRAME_PICKER_ROLES = new Set([\"poster\"", js);
            Assert.DoesNotContain("GENERATED_VIDEO_FRAME_PICKER_ROLES = new Set([\"video\"", js);
        }

        [Fact]
        public void AppJs_FramePickerBuildsRoleLevelGeneratedVideoChoices()
        {
            var js = ReadVisionResource("app.js");

            Assert.Contains("function buildFramePickerChoices(artifact)", js);
            Assert.Contains("artifact.kind === \"generated_video\"", js);
            Assert.Contains("isGeneratedVideoFramePickerRole(file.role)", js);
            Assert.Contains("role: file.role", js);
            Assert.Contains("thumbRole: file.role", js);
            Assert.Contains("choice.artifact.artifact_id", js);
            Assert.Contains("choice.role", js);
        }

        [Fact]
        public void AppJs_FramePickerRequestsGeneratedVideoArtifacts()
        {
            var js = ReadVisionResource("app.js");

            Assert.Contains(
                "bridgeCall(\"list_artifacts\", { kind: \"generated_video\", limit: 100 })",
                js);
            Assert.Contains("...(vidData.artifacts || [])", js);
            Assert.Contains(".flatMap(buildFramePickerChoices)", js);
        }

        [Fact]
        public void AppJs_FramePickerDoesNotUseDisplayRoleForGeneratedVideoInputs()
        {
            var js = ReadVisionResource("app.js");

            Assert.Contains("pickDisplayRole(artifact) || \"image\"", js);
            Assert.Contains("if (artifact.kind === \"generated_video\")", js);
            Assert.DoesNotContain("pickDisplayRole(a) || \"video\"", js);
            Assert.DoesNotContain("role = pickDisplayRole(a) || \"poster\"", js);
        }

        [Fact]
        public void AppJs_GalleryKeepsPosterAsDisplayOnly()
        {
            var js = ReadVisionResource("app.js");

            Assert.Contains("const posterRole = isVideo", js);
            Assert.Contains("f.role === \"poster\"", js);
            Assert.Contains("<img src=\"${posterUrl}\" alt=\"Video poster\">", js);
            Assert.Contains("el.modalVideo.src = src;", js);
            Assert.Contains("modalDisplayRole = pickDisplayRole(modalArtifact);", js);
        }

        private static string ReadVisionResource(string fileName)
        {
            return ReadSourceFile(
                "src",
                "Rook",
                "UI",
                "Vision",
                "Resources",
                fileName);
        }

        private static string ReadSourceFile(params string[] pathParts)
        {
            var dir = new DirectoryInfo(AppContext.BaseDirectory);
            while (dir != null)
            {
                var candidate = Path.Combine(dir.FullName, Path.Combine(pathParts));
                if (File.Exists(candidate))
                    return File.ReadAllText(candidate);

                dir = dir.Parent;
            }

            throw new FileNotFoundException(
                "Could not locate source file " + string.Join("/", pathParts));
        }
    }
}
```

- [ ] **Step 2: Run the focused UI source tests and verify failure**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --no-restore --filter FullyQualifiedName~VisionVideoSidecarContractSourceTests
```

Expected: FAIL. The missing strings should reference `GENERATED_VIDEO_FRAME_PICKER_ROLES`, `buildFramePickerChoices`, and the generated-video `list_artifacts` call.

- [ ] **Step 3: Commit the failing tests**

Run:

```powershell
git add src\Rook.Tests\UI\Vision\VisionVideoSidecarContractSourceTests.cs
git commit -m "test: pin video sidecar picker contract"
```

---

### Task 2: Implement Role-Level Frame Picker Choices

**Files:**
- Modify: `src/Rook/UI/Vision/Resources/app.js`
- Test: `src/Rook.Tests/UI/Vision/VisionVideoSidecarContractSourceTests.cs`

- [ ] **Step 1: Add generated-video picker role constants and helpers**

In `src/Rook/UI/Vision/Resources/app.js`, near the video frame-picker state or before `openPicker(slot)`, add:

```javascript
    const GENERATED_VIDEO_FRAME_PICKER_ROLES = new Set(["start_frame", "end_frame"]);

    function isGeneratedVideoFramePickerRole(role) {
        return GENERATED_VIDEO_FRAME_PICKER_ROLES.has(role);
    }

    function buildFramePickerChoices(artifact) {
        if (!artifact || !artifact.artifact_id || !Array.isArray(artifact.files)) {
            return [];
        }

        if (artifact.kind === "generated_video") {
            return artifact.files
                .filter(file => file && isGeneratedVideoFramePickerRole(file.role))
                .map(file => ({
                    artifact,
                    role: file.role,
                    thumbRole: file.role,
                    label: file.role === "start_frame" ? "Start frame" : "End frame",
                }));
        }

        const role = pickDisplayRole(artifact) || "image";
        return [{
            artifact,
            role,
            thumbRole: role,
            label: artifact.kind || "",
        }];
    }
```

- [ ] **Step 2: Update `openPicker(slot)` to request generated videos**

Replace the existing three-call `Promise.all` block in `openPicker(slot)` with:

```javascript
            // Image artifacts are direct frame inputs. Generated-video
            // artifacts are role-level candidates only when they already
            // carry frame-exact sidecars. `poster` stays display-only and
            // `video` stays playback-only.
            const [genData, capData, depthData, vidData] = await Promise.all([
                bridgeCall("list_artifacts", { kind: "generated_image", limit: 100 }),
                bridgeCall("list_artifacts", { kind: "captured_viewport", limit: 100 }),
                bridgeCall("list_artifacts", { kind: "depth_map", limit: 100 }),
                bridgeCall("list_artifacts", { kind: "generated_video", limit: 100 }),
            ]);
            const items = [
                ...(genData.artifacts || []),
                ...(capData.artifacts || []),
                ...(depthData.artifacts || []),
                ...(vidData.artifacts || []),
            ]
                .flatMap(buildFramePickerChoices)
                .sort((a, b) => {
                    const t = (b.artifact.created_at || "").localeCompare(a.artifact.created_at || "");
                    if (t !== 0) return t;
                    const idCompare = (b.artifact.artifact_id || "").localeCompare(a.artifact.artifact_id || "");
                    if (idCompare !== 0) return idCompare;
                    return (a.role || "").localeCompare(b.role || "");
                });
```

- [ ] **Step 3: Update the empty-state copy**

In the `items.length === 0` branch inside `openPicker(slot)`, keep the same structure but replace the paragraph with:

```html
<p>Generate an image, capture a viewport, capture depth, or use a generated video with frame sidecars.</p>
```

- [ ] **Step 4: Update picker rendering to use role-level choices**

Replace the `items.map(a => { ... })` block with:

```javascript
            ve.pickerGrid.innerHTML = items.map(choice => {
                const artifact = choice.artifact;
                const url = `/blob/${encodeURIComponent(artifact.artifact_id)}/${encodeURIComponent(choice.thumbRole)}`;
                const when = formatTimestamp(artifact.created_at);
                const kind = artifact.kind || "";
                const label = choice.label || kind;
                return `
                    <div class="video-picker-item" data-id="${escapeAttr(artifact.artifact_id)}" data-role="${escapeAttr(choice.role)}">
                        <div class="video-picker-thumb"><img src="${url}" alt="Picker thumbnail"></div>
                        <span class="video-picker-meta">${escapeHtml(kind)}</span>
                        <span class="video-picker-meta">${escapeHtml(label)}</span>
                        <span class="video-picker-meta">${escapeHtml(when)}</span>
                    </div>`;
            }).join("");
```

Keep the existing click handler that calls:

```javascript
onArtifactPicked(item.dataset.id, item.dataset.role);
```

- [ ] **Step 5: Run the focused UI source tests and verify pass**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --no-restore --filter FullyQualifiedName~VisionVideoSidecarContractSourceTests
```

Expected: PASS.

- [ ] **Step 6: Run the existing queue source tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --no-restore --filter FullyQualifiedName~VisionQueueUiSourceTests
```

Expected: PASS.

- [ ] **Step 7: Commit the picker implementation**

Run:

```powershell
git add src\Rook\UI\Vision\Resources\app.js
git commit -m "feat: make video frame picker role-aware"
```

---

### Task 3: Add Provider Non-Inference Tests

**Files:**
- Modify: `src/Rook.Tests/Services/Vision/Video/VeoProviderTests.cs`
- Modify: `src/Rook.Tests/Services/Vision/Video/Fal/FalVideoProviderTests.cs`

- [ ] **Step 1: Add Veo status non-inference test**

In `src/Rook.Tests/Services/Vision/Video/VeoProviderTests.cs`, add this test in the `GetStatus` section near `GetStatusAsync_done_with_video_uri_returns_Complete`:

```csharp
[Fact]
public async Task GetStatusAsync_done_with_sidecar_like_fields_keeps_only_video_uri_token()
{
    var json = """
        {
          "done": true,
          "response": {
            "generateVideoResponse": {
              "generatedSamples": [
                {
                  "video": { "uri": "https://veo/result/xyz" },
                  "posterUrl": "https://provider.invalid/poster.jpg",
                  "thumbnail": { "uri": "https://provider.invalid/thumb.jpg" },
                  "firstFrame": { "uri": "https://provider.invalid/first.jpg" },
                  "lastFrame": { "uri": "https://provider.invalid/last.jpg" }
                }
              ]
            }
          }
        }
        """;
    var (provider, _) = MakeProvider(_ => JsonResponse(HttpStatusCode.OK, json));

    var outcome = await provider.GetStatusAsync(
        new ProviderJobHandle("operations/abc"), CancellationToken.None);

    var complete = Assert.IsType<ProviderCompleteStatusOutcome>(outcome);
    Assert.Equal(
        "https://veo/result/xyz",
        complete.UpdatedHandle.ProviderResultToken);
    Assert.Null(complete.UpdatedHandle.ProviderMetadata);
}
```

- [ ] **Step 2: Add fal fetch non-inference test**

In `src/Rook.Tests/Services/Vision/Video/Fal/FalVideoProviderTests.cs`, add this test near `Fetch_parses_remote_video_artifact`:

```csharp
[Fact]
public async Task Fetch_with_sidecar_like_fields_returns_only_video_artifact()
{
    var handler = new TestHttpMessageHandler
    {
        OnSend = _ => Json(HttpStatusCode.OK, @"{
          ""actual_prompt"": ""expanded prompt"",
          ""seed"": 42,
          ""posterUrl"": ""https://v3b.fal.media/files/poster.jpg"",
          ""firstFrame"": ""https://v3b.fal.media/files/first.jpg"",
          ""lastFrame"": ""https://v3b.fal.media/files/last.jpg"",
          ""video"": {
            ""url"": ""https://v3b.fal.media/files/out.mp4"",
            ""content_type"": ""video/mp4"",
            ""thumbnail"": ""https://v3b.fal.media/files/thumb.jpg"",
            ""posterUrl"": ""https://v3b.fal.media/files/video-poster.jpg"",
            ""firstFrame"": ""https://v3b.fal.media/files/video-first.jpg"",
            ""lastFrame"": ""https://v3b.fal.media/files/video-last.jpg""
          }
        }"),
    };
    var provider = Provider(handler);

    var outcome = await provider.FetchResultAsync(Handle(), CancellationToken.None);

    var success = Assert.IsType<SuccessResultOutcome>(outcome);
    var artifact = Assert.Single(success.Envelope.Artifacts);
    Assert.Equal(VideoMediaRoles.Video, artifact.Role);
    Assert.DoesNotContain(success.Envelope.Artifacts, a => a.Role == VideoMediaRoles.Poster);
    Assert.DoesNotContain(success.Envelope.Artifacts, a => a.Role == VideoMediaRoles.StartFrame);
    Assert.DoesNotContain(success.Envelope.Artifacts, a => a.Role == VideoMediaRoles.EndFrame);
}
```

- [ ] **Step 3: Run provider tests and verify pass**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~VeoProviderTests|FullyQualifiedName~FalVideoProviderTests"
```

Expected: PASS.

- [ ] **Step 4: Commit provider non-inference tests**

Run:

```powershell
git add src\Rook.Tests\Services\Vision\Video\VeoProviderTests.cs src\Rook.Tests\Services\Vision\Video\Fal\FalVideoProviderTests.cs
git commit -m "test: pin video provider sidecar non-inference"
```

---

### Task 4: Add Audit Procedure, Placeholder Fixtures, and Doc Tests

**Files:**
- Create: `docs/rook_docs/video-provider-payload-audit.md`
- Create: `docs/rook_docs/fixtures/video-provider-payload-audit/veo-completion.sanitized.example.json`
- Create: `docs/rook_docs/fixtures/video-provider-payload-audit/fal-result.sanitized.example.json`
- Create: `src/Rook.Tests/Services/Vision/Video/VideoProviderPayloadAuditDocsTests.cs`

- [ ] **Step 1: Add the audit procedure document**

Create `docs/rook_docs/video-provider-payload-audit.md` with this content:

```markdown
# Video Provider Payload Audit Procedure

Status: audit-ready procedure, no live capture performed in the sidecar-contract slice

## Purpose

This procedure records how to capture sanitized provider completion/result payloads for deciding whether Rook can ingest provider-supplied video posters, or whether Rook must derive frame sidecars through MP4 extraction.

This procedure does not authorize live provider generations. Live Veo and fal captures require explicit cost approval, model selection, credential confirmation, and a named verification task.

## Capture Targets

Capture exactly the provider responses needed to answer the sidecar question:

- Veo: completed operation payload returned by the poll/status request.
- Veo: downloaded video URI shape only, not downloaded bytes.
- fal: result payload returned by the queue response endpoint.
- fal: model identity used for the request, such as Seedance or Kling, without provider-private transport URLs.

## Redaction Rules

Sanitized payloads and findings must not contain:

- API keys.
- Signed URLs.
- Provider-private queue/status/result/cancel tokens.
- Local filesystem paths.
- Raw video bytes.
- Raw image bytes.
- Sensitive prompts.
- Account, project, bucket, tenant, or organization identifiers that are not needed for structural analysis.

Replace sensitive values with stable placeholders:

- `https://provider.invalid/redacted-video.mp4`
- `https://provider.invalid/redacted-poster.jpg`
- `<REDACTED_PROMPT>`
- `<REDACTED_PROVIDER_JOB_ID>`
- `<REDACTED_ACCOUNT>`

## Non-Inference Rule

Unknown provider fields are inert. Fields named `thumbnail`, `preview`, `image`, `frame`, `firstFrame`, `lastFrame`, `posterUrl`, or similar do not imply `poster`, `start_frame`, or `end_frame` support until a provider-specific mapping is designed, reviewed, and tested.

## Sanitized Fixtures

Example sanitized shapes live under:

- `docs/rook_docs/fixtures/video-provider-payload-audit/veo-completion.sanitized.example.json`
- `docs/rook_docs/fixtures/video-provider-payload-audit/fal-result.sanitized.example.json`

These files are placeholders for structure only. They are not evidence that any provider returns trustworthy posters or frame-exact sidecars.

## Cost-Gated Follow-Up Checklist

Before running live captures:

- Confirm the provider credentials are intentionally available for this task.
- Confirm the exact Veo model and fal model.
- Confirm the maximum number of jobs: one Veo job and one fal job.
- Confirm the cost ceiling in writing.
- Confirm where sanitized findings will be recorded.
- Confirm raw payloads will remain local and temporary until redacted.

After live captures:

- Redact payloads using the rules above.
- Update sanitized findings with only structural evidence.
- Decide whether provider-poster ingestion is viable for display-only thumbnails.
- Decide whether MP4 extraction is required for `start_frame` and `end_frame`.
- Keep extraction tooling decisions in a separate Tier 3 design.
```

- [ ] **Step 2: Add sanitized Veo placeholder fixture**

Create `docs/rook_docs/fixtures/video-provider-payload-audit/veo-completion.sanitized.example.json` with this content:

```json
{
  "provider": "veo",
  "payload_kind": "completed_operation",
  "sanitized": true,
  "note": "Example shape only. Not live provider evidence.",
  "operation": {
    "name": "<REDACTED_PROVIDER_JOB_ID>",
    "done": true,
    "response": {
      "generateVideoResponse": {
        "generatedSamples": [
          {
            "video": {
              "uri": "https://provider.invalid/redacted-video.mp4"
            },
            "posterUrl": "https://provider.invalid/redacted-poster-candidate.jpg",
            "firstFrame": "https://provider.invalid/redacted-first-frame-candidate.jpg",
            "lastFrame": "https://provider.invalid/redacted-last-frame-candidate.jpg"
          }
        ]
      }
    }
  },
  "contract": {
    "unknown_fields_are_inert": true,
    "inferred_roles": []
  }
}
```

- [ ] **Step 3: Add sanitized fal placeholder fixture**

Create `docs/rook_docs/fixtures/video-provider-payload-audit/fal-result.sanitized.example.json` with this content:

```json
{
  "provider": "fal",
  "payload_kind": "queue_result",
  "sanitized": true,
  "note": "Example shape only. Not live provider evidence.",
  "model": "<REDACTED_FAL_MODEL>",
  "result": {
    "video": {
      "url": "https://provider.invalid/redacted-video.mp4",
      "content_type": "video/mp4",
      "thumbnail": "https://provider.invalid/redacted-thumbnail-candidate.jpg",
      "posterUrl": "https://provider.invalid/redacted-poster-candidate.jpg",
      "firstFrame": "https://provider.invalid/redacted-first-frame-candidate.jpg",
      "lastFrame": "https://provider.invalid/redacted-last-frame-candidate.jpg"
    },
    "actual_prompt": "<REDACTED_PROMPT>",
    "seed": 12345
  },
  "contract": {
    "unknown_fields_are_inert": true,
    "inferred_roles": []
  }
}
```

- [ ] **Step 4: Add audit docs tests**

Create `src/Rook.Tests/Services/Vision/Video/VideoProviderPayloadAuditDocsTests.cs` with this content:

```csharp
using System;
using System.IO;
using Xunit;

namespace Rook.Tests.Services.Vision.Video
{
    public class VideoProviderPayloadAuditDocsTests
    {
        [Fact]
        public void AuditProcedure_RequiresExplicitLiveCostApproval()
        {
            var doc = ReadRepoFile("docs", "rook_docs", "video-provider-payload-audit.md");

            Assert.Contains("does not authorize live provider generations", doc);
            Assert.Contains("explicit cost approval", doc);
            Assert.Contains("one Veo job and one fal job", doc);
            Assert.Contains("cost ceiling", doc);
        }

        [Fact]
        public void AuditProcedure_DefinesRedactionRules()
        {
            var doc = ReadRepoFile("docs", "rook_docs", "video-provider-payload-audit.md");

            Assert.Contains("No API keys.", doc);
            Assert.Contains("No signed URLs.", doc);
            Assert.Contains("No provider-private queue/status/result/cancel tokens.", doc);
            Assert.Contains("No local filesystem paths.", doc);
            Assert.Contains("No raw video bytes.", doc);
            Assert.Contains("No raw image bytes.", doc);
            Assert.Contains("No sensitive prompts.", doc);
        }

        [Fact]
        public void AuditProcedure_PinsUnknownFieldNonInferenceRule()
        {
            var doc = ReadRepoFile("docs", "rook_docs", "video-provider-payload-audit.md");

            Assert.Contains("Unknown provider fields are inert.", doc);
            Assert.Contains("posterUrl", doc);
            Assert.Contains("firstFrame", doc);
            Assert.Contains("lastFrame", doc);
            Assert.Contains("do not imply `poster`, `start_frame`, or `end_frame` support", doc);
        }

        [Theory]
        [InlineData("veo-completion.sanitized.example.json")]
        [InlineData("fal-result.sanitized.example.json")]
        public void SanitizedExampleFixtures_AreMarkedAsNonEvidenceAndInferNoRoles(string fileName)
        {
            var json = ReadRepoFile(
                "docs",
                "rook_docs",
                "fixtures",
                "video-provider-payload-audit",
                fileName);

            Assert.Contains("\"sanitized\": true", json);
            Assert.Contains("Not live provider evidence.", json);
            Assert.Contains("\"unknown_fields_are_inert\": true", json);
            Assert.Contains("\"inferred_roles\": []", json);
            Assert.DoesNotContain("AIza", json);
            Assert.DoesNotContain("queue.fal.run", json);
            Assert.DoesNotContain("v3b.fal.media", json);
            Assert.DoesNotContain("C:\\\\", json);
        }

        private static string ReadRepoFile(params string[] pathParts)
        {
            var dir = new DirectoryInfo(AppContext.BaseDirectory);
            while (dir != null)
            {
                var candidate = Path.Combine(dir.FullName, Path.Combine(pathParts));
                if (File.Exists(candidate))
                    return File.ReadAllText(candidate);

                dir = dir.Parent;
            }

            throw new FileNotFoundException(
                "Could not locate repo file " + string.Join("/", pathParts));
        }
    }
}
```

- [ ] **Step 5: Run audit docs tests and verify pass**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --no-restore --filter FullyQualifiedName~VideoProviderPayloadAuditDocsTests
```

Expected: PASS.

- [ ] **Step 6: Commit audit procedure and tests**

Run:

```powershell
git add docs\rook_docs\video-provider-payload-audit.md docs\rook_docs\fixtures\video-provider-payload-audit\veo-completion.sanitized.example.json docs\rook_docs\fixtures\video-provider-payload-audit\fal-result.sanitized.example.json src\Rook.Tests\Services\Vision\Video\VideoProviderPayloadAuditDocsTests.cs
git commit -m "docs: add video provider payload audit procedure"
```

---

### Task 5: Verification and Reviewer Handoff

**Files:**
- Read: all files changed by Tasks 1-4

- [ ] **Step 1: Run the focused sidecar contract test set**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~VisionVideoSidecarContractSourceTests|FullyQualifiedName~VeoProviderTests|FullyQualifiedName~FalVideoProviderTests|FullyQualifiedName~VideoProviderPayloadAuditDocsTests"
```

Expected: PASS.

- [ ] **Step 2: Run the existing video/UI smoke tests touched by this slice**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~VisionQueueUiSourceTests|FullyQualifiedName~VideoJobManagerTests|FullyQualifiedName~VideoOpHandlerTests"
```

Expected: PASS.

- [ ] **Step 3: Check whitespace**

Run:

```powershell
git diff origin/main --check
git show --check --format=short HEAD
```

Expected: both commands produce no whitespace-error output and exit code 0. `git diff origin/main --check` validates the full committed series against the synced base; `git show --check --format=short HEAD` validates the most recent task commit.

- [ ] **Step 4: Verify no sidecar production was added**

Run:

```powershell
rg -n 'new BlobInput\("poster"|new BlobInput\("start_frame"|new BlobInput\("end_frame"|VideoMediaRoles\.Poster|VideoMediaRoles\.StartFrame|VideoMediaRoles\.EndFrame' src\Rook\Services\Vision\Video src\Rook\UI\Vision\Resources\app.js
```

Expected human-inspected result:

- `app.js` may contain `start_frame` and `end_frame` picker constants.
- `src\Rook\Services\Vision\Video\VideoMediaRoles.cs` contains the role constants.
- Existing request/media-resolution code may reference `StartFrame` / `EndFrame`.
- No `VideoJobManager` code creates new `BlobInput("poster")`, `BlobInput("start_frame")`, or `BlobInput("end_frame")`.

- [ ] **Step 5: Produce reviewer prompt**

Use this reviewer prompt:

```text
Please review the RookVision video sidecar contract implementation against docs/superpowers/specs/2026-05-10-video-sidecar-contract-design.md.

Focus areas:
- `poster` must remain display-only.
- Generated-video picker eligibility must be role-level, not artifact-level.
- `video` and `poster` must not become frame-picker inputs.
- A generated-video artifact with both `start_frame` and `end_frame` must expose two distinct picker choices.
- Unknown provider payload fields must remain inert; no provider-poster or frame-sidecar inference should be added.
- Audit docs must be cost-gated and must not require live Veo/fal generations.
- No MP4 extraction, ffmpeg/WMF decision, ArtifactStore append API, VideoJobManager sidecar production, or GH NLE work should be included.

Please report critical, important, and minor issues, and give a merge-readiness verdict.
```

- [ ] **Step 6: Confirm verification did not require extra tracked changes**

Run:

```powershell
git status --short
```

Expected: no unstaged or untracked files beyond the implementation commits created by the earlier tasks. If this command shows an unexpected file, inspect it and either commit it with the relevant earlier task or remove the generated output before requesting review.

---

## Self-Review

Spec coverage:

- Role semantics are covered by Task 1 source tests and Task 2 UI helper implementation.
- Role-level generated-video picker eligibility is covered by Task 1 and implemented in Task 2.
- Gallery poster behavior is pinned by Task 1 and intentionally left as the existing display path.
- Provider payload audit readiness is covered by Task 4.
- Unknown provider field non-inference is covered by Task 3 and Task 4.
- Out-of-scope constraints are protected by Task 5 verification.

Placeholder scan:

- This plan contains no placeholder work items or unspecified test requests.
- Each code-changing task includes exact code snippets and commands.
- Live provider capture is explicitly deferred behind cost approval and is not an implementation step.
- The final sidecar-production scan is deliberately human-inspected because legitimate role constants and existing media-reference code already contain the role names.

Type consistency:

- UI helper names are consistent across tests and implementation: `GENERATED_VIDEO_FRAME_PICKER_ROLES`, `isGeneratedVideoFramePickerRole`, and `buildFramePickerChoices`.
- Picker output remains the existing `{ kind: "artifact_id", artifact_id, role }` shape through `onArtifactPicked`.
- Provider tests use existing outcome types: `ProviderCompleteStatusOutcome`, `SuccessResultOutcome`, `ResultArtifact`, `VideoMediaRoles`.
