# Automatic Video Source Framing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. The user has selected native execution in this chat, followed by an independent final review. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users choose actual Fit/Fill previews in Rook, generate from those exact prepared bytes, and recover from actionable preflight errors without editing their images elsewhere.

**Architecture:** A shared managed preparation service owns bounded original reads, immutable buffers, deterministic FFmpeg rendering, and a private preview cache. Quotes and dispatch bind original and prepared identities; the panel keeps preview, route availability, and estimate state separate. Native HTTP ownership and existing durable video lifecycle rules remain intact.

**Tech Stack:** Windows x64; existing C# net48/net7.0/net8.0 companion, Win32 Job Objects through P/Invoke, bundled FFmpeg 8.1.1, existing xUnit/Node/Python checks.

**Spec:** [Approved design](../specs/2026-10-15-video-source-framing-design.md), commit `b482d365`. Product baseline: `4978b444`. Worktree: `C:/Users/aryan/.codex/worktrees/vision-prompt-fal-fallback/Rook`, branch `codex/vision-video-framing-spec`.

## Approval prerequisite discovered during planning

The committed FFmpeg configure recipe enables neither PNG nor WebP decoding. The locally available matching 8.1.1 source declares PNG decoding/encoding dependent on its zlib wrappers; the existing build has `CONFIG_ZLIB=0`. Simply adding filters cannot satisfy the approved format contract.

**Proposed, not authorized by this plan's creation:** allow one dependency exception: statically link zlib 1.3.2 into the existing FFmpeg executable, with pinned source/checksum, license, build recipe and provenance. Add no runtime DLL, NuGet/Python package, provider SDK, or network protocol. The installed MSYS2 headers identify 1.3.2, but installed headers alone are not reproducible provenance.

[AGENTS.md](../../../AGENTS.md) says **“Do not add new external dependencies”**; the spec repeats that constraint. Obtain an explicit exception with plan approval before executing Task 4 or adding this dependency. Do not reinterpret static linkage as dependency-free, substitute an unreviewed imaging stack, or reduce the promised PNG/WebP support. If the exception is declined, revise the rendering design before implementation.

## Global Constraints

- Planning approval alone does not authorize implementation. No deployment, installer release, merge, paid/live provider request, or fal Veo enablement is part of execution.
- Keep every production fal Veo continuity flag disabled. Test-only catalogs can enable synthetic bindings; never edit the production catalog to exercise a test.
- Original input: **32 MiB (33,554,432 bytes)** per artifact-role; **64 MiB (67,108,864 bytes)** total distinct references per bundle. Repeated positions remain ordered; different references reserve independently.
- Open with write/delete-excluding sharing; capture `L0` from that handle. Read chunks at most **64 KiB**, exactly `L0` bytes, then a separate one-byte EOF probe and handle-length recheck. Empty/unstable/growing/shrinking sources never become accepted snapshots.
- Reserve actual managed buffer capacities before allocation/copy: **128 MiB transient encoded buffers per active bundle**. Original reads, freezing, hash/read scratch, output reads and adapter copies participate. Transfers release one ownership charge only when another acquires it; aliases do not create free duplicate capacity.
- Every decoded/oriented source, conversion/rotation surface, scaled intermediate and canvas: **32,000,000 pixels**, maximum **16,384** on either edge. Use checked 64-bit arithmetic before process launch; account for decoder native planes/bit depth separately from 8-bit RGBA working surfaces.
- Windows-enforced **512 MiB (536,870,912 bytes) committed memory per owned renderer process group**, installed before execution. At most **two active preparation bundles and two renderer processes globally**; serialize sources, variants and encoding attempts inside a bundle.
- Preview and other pre-admission preparation get a **15-second total preflight budget per bundle**, including admission/queue waits. After job admission use the existing single **20-minute execution budget**, without resetting it. Cancel owned work immediately, independently of ledger persistence.
- Retained encoded originals/derived bytes: **256 MiB and 16 bundles**, including pins. Unpinned **30-minute idle TTL**, then LRU eviction. Jobs and open preview streams pin their own buffers. Exhaustion is retryable preparation-busy.
- Profile `video-source-framing-v1`: EXIF orientation first, Lanczos, 8-bit RGBA working surfaces, opaque black matte, metadata stripped. Fit floors scaled dimensions; Fill ceils them. Center using integer division; odd padding/excess belongs to right/bottom.
- Canvas: 720p = 1280x720 or 720x1280; 1080p = 1920x1080 or 1080x1920; 4k = 3840x2160 or 2160x3840. Do not add model capabilities; Lite still excludes 4k.
- PNG first, then MJPEG quantizers **2, 3, 4**; first encoded result at most **8,000,000 bytes** wins. Check length before bounded loading. Never silently change mode, output shape or resolution.
- Explicit framing accepts static PNG/JPEG/WebP only. Reject APNG/WebP animation declarations, including declared single-frame animations, before full decoding. Unknown frame counts do not establish stillness.
- Only affected Google Veo 3.1 and corresponding direct fal I2V/interpolation accept top-level `source_framing: "fit" | "fill"`. Explicit framing requires fingerprint plus numeric cap. Preserve omitted-field Google original bytes and renderer independence, and existing legacy confirmation behavior.
- Keep first-stop wins, dispatch intent before send, durable accepted handle before poll, unknown submission without replay, endpoint-specific pricing, and completion visibility on every artifact/sidecar/blob path.
- No native ABI/project changes, new HTTP server, thumbnail MCP tool or public thumbnail route. Native forwarding must preserve additive fields.
- Commands below run from the worktree, sequentially where they share build outputs. Always use `-p:RhinoPluginDir=` to prevent build-time deployment.
- Before each task commit, stage only that task's listed files/tests with explicit paths. Use `git add -f -- <exact path>` for ignored documentation/fixtures where required; never stage unrelated work.
- Before Task 1 execution, capture a read-only SHA256 manifest of the currently installed Rook runtime for comparison at Task 9. Do not stop Rhino or modify the installation for this implementation qualification.

## Review Focus

1. A repeated reference occupies both interpolation roles: share immutable storage while preserving both ordered entries and independently correct geometry/provenance (Tasks 1, 5, 7).
2. A caller is cancelled while queued or while another job pins identical cached media: release only that caller's ownership; no permit leaks or cancellation of another job (Tasks 1, 5).
3. A malformed chunk length, cyclic EXIF offset, or 16-bit/paletted still-image header must fail safely or use the declared conversion; never allocate from unchecked metadata (Tasks 3, 4).
4. A cached derived asset disappears or changes between preview and dispatch, while its source returns A→B→A: compare the actual immutable payload, not current filenames or preview IDs (Tasks 5, 7).
5. Settings are saved while a stale estimate/preview is still returning: keep the deliberate Fill choice and current source, refresh availability, and permit confirmation only for the current matching preview/quote (Task 8).

## File and ownership map

Paths below are repository-relative. New framing services live under `src/Rook/Services/Vision/Video/Framing/`; `Framing/` means that directory. In each Files bullet, subsequent bare filenames inherit the explicitly named directory in that bullet.

| Boundary | Responsibility / existing integration points |
| --- | --- |
| Resource ownership | Framing resource leases and bounded reads; `ArtifactOnlyVideoMediaResolver.cs`, `Generation/MediaResolutionResult.cs`, `VideoPreparedMediaSnapshot.cs` |
| Managed subprocess | New framing-only Windows Job runner; do not weaken or broadly rewrite `DefaultProcessRunner` in `Extraction/FfmpegPosterFrameExtractor.cs` |
| Still metadata / geometry | Bounded container parser and pure integer geometry; no pixel decoding on UI thread |
| Renderer / distribution | Framing renderer; `scripts/ffmpeg/*` recipe/provenance and `scripts/validate-ffmpeg-bundle.ps1`; existing bundled locator |
| Cache / private blob | Immutable buffers and nongallery preview IDs; `VisionWebSurface.cs` opens their streams through existing `/blob/{id}/{role}` handling |
| Request / route | `VideoGenerationRequest.cs`, handler parsing, coordinator, fal compatibility, Python schema and forwarding |
| Confirmation / lifecycle | Quote, prepared snapshot, provider adapters, manager routing, execution snapshot and projections |
| Panel | `Resources/index.html`, `styles.css`, `app.js` and focused Node harness |
| Real qualification | A dependency-free console qualification project references the actual companion for each target; checked-in fixtures and machine-readable reports |

### Task 1: Bound video artifact reads and account for immutable buffers

**Files**
- Create beneath `src/Rook/Services/Vision/Video/Framing/`: `VideoPreparationResources.cs`, `VideoFrozenBuffer.cs`, `BoundedVideoSourceReader.cs`, `VideoSourcePreparationErrors.cs`.
- Modify: `src/Rook/Services/Vision/Video/ArtifactOnlyVideoMediaResolver.cs`, `VideoPreparedMediaSnapshot.cs`, `VideoJobManager.cs`.
- Modify: `src/Rook/Services/Vision/Generation/MediaResolutionResult.cs`.
- Test: `src/Rook.Tests/Services/Vision/Video/VideoBoundedMediaTests.cs`; extend `VideoPreparedMediaSnapshotTests.cs`.

**Interfaces**
- `VideoPreparationResources.Shared` is the production process-wide instance; `AcquireAsync(CancellationToken) : Task<VideoPreparationLease>` returns a disposable lease exposing its `VideoBufferBudget` and one shared bundle permit. Factory/default resolver paths use `Shared`; tests may inject an isolated instance.
- `VideoBufferBudget.Reserve(int capacity) : VideoBufferReservation`; reservation is disposable/idempotent. `VideoFrozenBuffer` owns an exactly sized private array, reservation, `Length`, `Sha256` and `OpenRead() : Stream`; no mutable array getter.
- `BoundedVideoSourceReader.ReadAsync(Stream opened, long initialLength, string field, VideoPreparationLease lease, CancellationToken ct) : Task<VideoSourceReadResult>`. Result contains `VideoFrozenBuffer? Buffer` and `GenerationError? Error`. The resolver owns opening the real file with `FileShare.Read` and counting distinct admitted originals.
- Add internal `ArtifactOnlyVideoMediaResolver.ResolveSnapshotAsync(VideoGenerationRequest request, VideoPreparationLease lease, CancellationToken ct) : Task<VideoSourceSnapshotResult>`, whose result contains `VideoPreparedMediaSnapshot? Snapshot` and `GenerationError? Error`. Production preparation, including omitted framing, adopts the bounded reader's immutable storage directly; do not round-trip it through a mutable `ResolvedMedia` dictionary merely to clone it back. The existing `IMediaResolver` adapter still uses the same bounded reader and explicitly owned copies.
- Add internal `MediaResolutionResult.OkOwned(IReadOnlyDictionary<MediaRef,ResolvedMedia>, IDisposable owner)` and idempotent `Dispose()`. Existing `Ok/Fail` results have no resource owner; image behavior stays unchanged. All video consumers dispose owned results; snapshots transfer or reserve their copies before releasing resolution ownership.
- `VideoSourcePreparationErrors.Create(string code, string field, string? mode = null, string? detail = null, bool retryable = false) : GenerationError` puts the local code in `ProviderErrorCode` and only `preparation_detail` / `framing_mode` / `action` in its allowlisted `ProviderDetail`. Geometry/memory errors use `source_preparation_failed` + `render_limits_exceeded`; busy uses `source_preparation_failed` + `preparation_busy` and `Retryable=true`. Wire projection uses `detail_code` for the local code and those separate preparation fields, without raw exception text.

- [ ] **Write tests:** `Read_ExactCapAndAggregateLimit`, `Read_PathStatIsNotAdmission`, `Read_GrowthShrinkAndExtraByteDiscardSnapshot`, `Read_QueuedCancellationReleasesPermit`, `Capture_RepeatedRolesShareReservedStorage`. Use controllable seekable streams reporting changed handle lengths, plus real file sharing tests; no timing sleeps.
  ```csharp
  Assert.Equal(33_554_432, exact.Buffer!.Length);
  Assert.Equal("source_input_too_large", over.Error!.ProviderErrorCode);
  Assert.Equal(67_108_864, twoDistinct.AdmittedOriginalBytes);
  Assert.Equal("source_input_too_large", thirdDistinct.Error!.ProviderErrorCode);
  Assert.All(changedReads, r => Assert.Equal("source_changed", r.Error!.ProviderErrorCode));
  Assert.Equal(0, rejected.DecoderStarts + rejected.ProviderCalls);
  Assert.Equal(new[] { "start_frame", "end_frame" }, repeated.Slots.Select(s => s.Role));
  Assert.Equal(1, repeated.UniqueStorageCount);
  Assert.True(accounting.PeakReservedBytes <= 134_217_728);
  Assert.Equal(0, accounting.OutstandingReservationsAfterDispose);
  ```
- [ ] **RED:** `dotnet test src/Rook.Tests/Rook.Tests.csproj -p:RhinoPluginDir= --filter "FullyQualifiedName~VideoBoundedMediaTests|FullyQualifiedName~VideoPreparedMediaSnapshotTests"`. Expected: boundary/ownership assertions fail against unrestricted reads and cloning.
- [ ] Implement those interfaces. Replace the unrestricted artifact read, not merely import validation. Check length before allocation and each cumulative read; exactly one separate EOF probe. Classify within-cap growth as `source_changed` too. Include cancellation before admission, between chunks and before freezing. Never suppress cancellation in a generic catch.
- [ ] Implement ownership transfer/share in snapshots and use `ResolveSnapshotAsync` on all production video preparation paths. Reserve remaining compatibility copies and adapter buffers. Public compatibility results carry ownership until disposed; update both routed and non-routed video consumers rather than releasing the budget when returning the dictionary. Injected legacy test resolvers retain bounded-copy snapshot capture. Distinct references remain distinct for admission even when their final hashes match. Preserve ordered roles.
- [ ] **GREEN:** repeat RED command; all focused tests pass, including omitted-field legacy reads at cap/cap+1 and injected reservation denial before allocation. Compile the existing image callers of `MediaResolutionResult` without changing their wire shape.
- [ ] Commit task files: `git commit -m "fix: bound video source reads and buffer ownership"`.

### Task 2: Enforce renderer memory before its first instruction

**Files**
- Create: `Framing/WindowsFramingProcessRunner.cs`, `WindowsFramingJobNative.cs`.
- Create: `src/Rook.Framing.Qualification/Rook.Framing.Qualification.csproj`, `Program.cs`, `ProcessProbe.cs`.
- Modify: `src/Rook/Rook.csproj` only to grant this qualification assembly internal access.
- Test: `src/Rook.Tests/Services/Vision/Video/WindowsFramingProcessRunnerTests.cs`.

**Interfaces**
- `IFramingProcessRunner.RunAsync(FramingProcessRequest request, CancellationToken ct) : Task<FramingProcessResult>`. Request contains verified executable path, fixed argument list, owned working directory and output path; result includes exit classification, peak job commit, enforcement established, and bounded internal diagnostics.
- `WindowsFramingProcessRunner` implements it. Keep P/Invoke structures/constants and safe handle ownership in `WindowsFramingJobNative.cs`.
- Qualification executable: parent mode `--process-probes --report <path>` runs contained probes. Internal child modes `--probe-marker <path>`, `--probe-commit-mib <n>`, `--probe-child` are launched only by the memory-contained runner; never run the allocating child directly from a shell. Normal renderer qualification entry is added in Task 4.

- [ ] **Write tests:** `Runner_AssignsSuspendedChildBeforeResume`, `Runner_LimitInstallOrAssignmentFailureNeverExecutesProbe`, `Runner_CancelKillsOwnedTreeOnly`, `Runner_CommitLimitIsHardAndGroupWide`, `Runner_ParentJobAssignmentFailsClosed`. Use injectable native calls for ordering/failure tests; actual Windows process probes for enforcement.
  ```csharp
  Assert.True(trace.IndexOf("SetHardLimit") < trace.IndexOf("ResumeThread"));
  Assert.True(trace.IndexOf("AssignProcess") < trace.IndexOf("ResumeThread"));
  Assert.False(File.Exists(failedInstall.MarkerPath));
  Assert.True(probe.PeakJobCommitBytes <= 536_870_912);
  Assert.True(probe.AllOwnedProcessesExited);
  Assert.True(unrelatedProcess.IsAlive);
  Assert.False(cancelled.HasPublishedOutput);
  ```
- [ ] **RED:** run `dotnet test src/Rook.Tests/Rook.Tests.csproj -p:RhinoPluginDir= --filter FullyQualifiedName~WindowsFramingProcessRunnerTests`. Expected: missing enforcement/order behavior fails; ordinary `Process.Start` is insufficient.
- [ ] Implement a fresh unnamed Job Object with `JOB_OBJECT_LIMIT_JOB_MEMORY = 536870912` and `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`. Associate its completion port and read back configured limits. Create FFmpeg using `CreateProcessW(CREATE_SUSPENDED | CREATE_NO_WINDOW | EXTENDED_STARTUPINFO_PRESENT)` with the handle-list startup attributes, assign it to the job, then resume. Assignment/limit/readback failure terminates the still-suspended child and returns safe preparation failure. No breakaway flags or unprotected retry.
- [ ] Also configure `JobObjectNotificationLimitInformation` at **480 MiB**, a conservative termination threshold below the hard ceiling. Its guaranteed notification requests `QueryInformationJobObject` then `TerminateJobObject`; the 512 MiB allocation-denial cap remains independent of notification scheduling. Treat hard-limit messages and known allocation failures as limit failures; any abnormal exit/cancellation terminates the owned group and discards partial output. Do not rely solely on nonguaranteed hard-limit notifications, RSS polling or timeout. Document that valid workloads crossing the conservative threshold fail with `render_limits_exceeded`.
- [ ] Use safe handles and an explicit inherited-handle list for redirected standard streams. Drain stderr continuously but retain at most 64 KiB internally; no raw stderr or paths in UI. Close owned thread/process/job/pipe/completion-port handles on every path; finish cleanup before releasing the renderer permit. Nested-job restriction is a safe unavailable error, never permission to escape the parent job.
- [ ] Build the qualification console for `net48;net7.0;net8.0`, x64, no new package references; reference actual `Rook.csproj` and mirror `Rook.rhp` as `Rook.dll` following `Rook.Tests.csproj`. Use apphost executables for probes. Test incremental and single-large allocation attempts, aggregate parent/child commit, cancellation and a sentinel unrelated process.
- [ ] **GREEN:** repeat focused tests. For each of `net48`, `net7.0`, `net8.0` run `dotnet run --project src/Rook.Framing.Qualification/Rook.Framing.Qualification.csproj -c Release -f <target> -p:RhinoPluginDir= -- --process-probes --report artifacts/framing-process-<target>.json`; record refusal/termination, peak commit and zero marker execution on failure.
- [ ] Commit: `git commit -m "feat: contain framing renderers in Windows memory-limited jobs"`.

**Mechanism references:** Microsoft's [job limits](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_extended_limit_information), [suspended assignment](https://learn.microsoft.com/en-us/windows/win32/api/jobapi2/nf-jobapi2-assignprocesstojobobject), and [notification delivery rules](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects) distinguish a committed-memory cap from process monitoring.

### Task 3: Inspect still containers and admit exact integer geometry

**Files**
- Create: `Framing/SourceFramingMode.cs`, `VideoStillImageInspector.cs`, `VideoFramingGeometry.cs`, `VideoFramingModels.cs`.
- Test: `src/Rook.Tests/Services/Vision/Video/VideoStillImageInspectorTests.cs`, `VideoFramingGeometryTests.cs`.
- Create: `third_party/ffmpeg/fixtures/framing/manifest.json` and its named synthetic still/animation fixtures.

**Interfaces**
- Public enum `SourceFramingMode { Fit, Fill }`.
- `VideoStillImageInspector.Inspect(VideoFrozenBuffer source, string field) : VideoStillInspectionResult`; success includes MIME, stored/oriented dimensions, EXIF orientation, native depth/planes and static-container evidence. Failure includes `GenerationError`.
- `VideoFramingGeometry.Create(VideoStillImageInfo source, string resolution, string aspect, SourceFramingMode mode, string field) : VideoFramingGeometryResult`.
- `VideoFramingRecipe` stores profile/renderer identity, source/oriented/canvas/scaled dimensions, transform, pad/crop coordinates, matte, encoding and quantizer. It serializes canonically without IDs/paths/timestamps.

- [ ] **Write tests:** `Geometry_MotivatingImageAndOddEdges`, `Geometry_ExtremeFillRejectedBeforeLaunchFitAdmitted`, `Geometry_OverflowAndRotationSurfaces`, `Inspect_StaticAndDeclaredAnimation`, `Inspect_ChunkOverflowCyclicExifAndNativeDepth`.
  ```csharp
  Assert.Equal((1920, 1080), ordinary.Canvas);
  Assert.Equal((1380, 1080), ordinary.Fit.Scaled);
  Assert.Equal((1920, 1502), ordinary.Fill.Scaled);
  Assert.Equal((0, 211), ordinary.Fill.CropOrigin);
  Assert.Equal((53, 0), odd.Fit.ContentOrigin); // 119x73 -> 1280x720; padding 53 left / 54 right
  Assert.Equal("render_limits_exceeded", extreme.Fill.ErrorDetail);
  Assert.True(extreme.Fit.Success);
  Assert.Equal(0, extreme.Fill.RendererStarts);
  Assert.All(animated, r => Assert.Equal("source_animation_unsupported", r.Error!.ProviderErrorCode));
  Assert.False(malformed.Success);
  ```
- [ ] **RED:** `dotnet test src/Rook.Tests/Rook.Tests.csproj -p:RhinoPluginDir= --filter "FullyQualifiedName~VideoStillImageInspectorTests|FullyQualifiedName~VideoFramingGeometryTests"`. Expected: static/animation distinction or geometry/admission assertions fail.
- [ ] Inspect bounded immutable streams without decompressing pixel data: PNG chunk structure/CRC and `acTL/fcTL/fdAT`, WebP RIFF/VP8X animation flag/ANIM/ANMF with checked lengths/padding, JPEG marker structure and bounded EXIF TIFF offsets. Reject corrupt/inconsistent structures; a declared animated container never becomes static because a frame count is one or absent. Bound metadata traversal and reject cycles. Apply equivalent EXIF handling in PNG/WebP if present.
- [ ] Compute scaling with integer rational products: Fit chooses the limiting edge then floors the other with a minimum of one pixel; Fill chooses the covering edge then uses checked ceiling division. Test one-pixel-thin sources as well as odd dimensions. Explicitly check source/native conversion, oriented, RGBA scale, pad/crop and output surfaces before launching. The 16384x720 → 2160x3840 Fill intermediate is **87382x3840 / 335,546,880 pixels / 1,342,187,520 RGBA bytes** and fails independently of Fit.
- [ ] Freeze real fixtures with independent geometry/pixel oracles: 1166x912 edge markers, portrait, square, matching/odd shapes, EXIF orientations 1–8, alpha, 16-bit/paletted PNG, static lossy/lossless WebP, multiframe APNG/WebP, declared-single-frame animations and corrupt controls. Record generation/provenance and SHA256 in the manifest; fixture-generation tools are not product dependencies.
- [ ] **GREEN:** repeat focused command; no decoder starts for animation, malformed metadata or oversized intermediates.
- [ ] Commit: `git commit -m "feat: validate still sources and deterministic video framing geometry"`.

### Task 4: Qualify the bundled still-image rendering profile

**Files**
- Create beneath the framing directory: `VerifiedFramingRenderer.cs`, `VideoFramingRendererProfile.cs`, `FfmpegVideoSourceRenderer.cs`, `VideoPreparedSource.cs`.
- Modify: `scripts/ffmpeg/rook-ffmpeg-configure.txt`, `rook-ffmpeg-enable-allowlist.json`, `build-rook-ffmpeg.ps1`, `README.md`.
- Create, only with the dependency exception: `scripts/ffmpeg/rook-zlib-source.json`.
- Modify: `scripts/validate-ffmpeg-bundle.ps1`, `scripts/tests/ffmpeg-bundle-validation.tests.ps1`; `third_party/ffmpeg/ffmpeg.exe`, `ffmpeg-provenance.json`, `NOTICE.FFmpeg.txt`, `SOURCE.FFmpeg.txt`, `README.md`. Create `third_party/ffmpeg/LICENSE.zlib.txt` only with the exception.
- Extend the Task 2 qualification project; create `RendererQualification.cs` there.
- Test: `src/Rook.Tests/Services/Vision/Video/VideoSourceRendererTests.cs`.

**Interfaces**
- `VerifiedFramingRenderer.Resolve(string bundledPath) : VerifiedFramingRendererResult` verifies executable SHA256 against the profile/hash constant in `VideoFramingRendererProfile.cs` and installed provenance; preserves an execution read handle denying write/delete through launch. Update the constant only with the qualified binary/provenance commit. Do not select PATH/configured alternatives.
- `IVideoSourceRenderer.RenderAsync(VideoFrozenBuffer original, VideoStillImageInfo info, VideoFramingRecipe recipe, VideoPreparationLease lease, CancellationToken ct) : Task<VideoPreparedSourceResult>`. Success owns a bounded `VideoFrozenBuffer` plus final recipe/MIME/dimensions; error is safe and typed.
- Qualification command: `Rook.Framing.Qualification.exe --ffmpeg <path> --fixtures <directory> --report <path>`. Exit zero only when production runner, metadata/geometry and renderer pass all required cases; record target framework, OS, hashes, recipe, encoded outcomes and peak job commit.

- [ ] **Write tests:** `Renderer_ActualPixelsMatchGeometryAndMatte`, `Renderer_PngThenJpegFirstWithinBound`, `Renderer_OversizedOutputIsNotReadIntoMemory`, `Renderer_ProfileMismatchMissingEncoderAndCancellation`. Use actual static fixtures for pixels and a controlled encoded-output writer for exact byte-boundary/error tests.
  ```csharp
  Assert.Equal((1920, 1080), rendered.Dimensions);
  Assert.True(rendered.Fit.AllSourceEdgeMarkersVisible);
  Assert.Equal(Color.Black, rendered.Fit.SamplePadding());
  Assert.Equal(expectedCenterCrop, rendered.Fill.VisibleSourceBounds);
  Assert.Equal(new[] { "png", "mjpeg:q2", "mjpeg:q3" }, boundedFallback.Attempts);
  Assert.Equal("mjpeg:q3", boundedFallback.SelectedEncoding);
  Assert.Equal(0, oversizedPng.PayloadReadAllocations);
  Assert.True(rendered.ByteLength <= 8_000_000);
  Assert.False(failed.PublishedPartialAsset);
  ```
- [ ] **RED:** `dotnet test src/Rook.Tests/Rook.Tests.csproj -p:RhinoPluginDir= --filter FullyQualifiedName~VideoSourceRendererTests` and `dotnet run --project src/Rook.Framing.Qualification/Rook.Framing.Qualification.csproj -c Release -f net48 -p:RhinoPluginDir= -- --ffmpeg third_party/ffmpeg/ffmpeg.exe --fixtures third_party/ffmpeg/fixtures/framing --report artifacts/framing-renderer-red.json`. Expect real PNG/WebP/profile capability failure, not an assumed supported-format list.
- [ ] **Check the dependency exception is explicit before proceeding.** Pin official zlib 1.3.2 source URL/hash and license, build a static archive in an owned staging prefix, and link that exact archive. Do not silently use the installed MSYS2 library or install packages. Include its source/build metadata in the generated source bundle and provenance; fail if it is missing or mismatched.
- [ ] Extend the existing minimal FFmpeg recipe, not its version: enable `zlib`, native `png/webp` decoders, `png` encoder, still-image `image2` demuxing, needed PNG/WebP parsers, and `format,pad,crop,transpose,hflip,vflip,setsar,drawbox,split,overlay` filters alongside existing scale/MJPEG. Verify dependency selections from the pinned 8.1.1 source/build; keep network/GPL/nonfree/autodetection disabled. Retain all existing sidecar codecs and smoke cases. Update the exact flag allowlist and source-bundle validator together.
- [ ] Implement fixed arguments: one input, one output frame, one decoder/filter/complex-filter/encoder thread, no autorotation, no audio/subtitles/data, no user filters, stripped metadata, bitexact CPU flags and Lanczos. Apply the inspected orientation explicitly. Versioned color policy: use FFmpeg's pinned native conversion into 8-bit RGBA, treat resulting RGB as sRGB, apply no ICC transform, strip color/private metadata consistently. For alpha, split the oriented RGBA frame, fill one branch opaque black using `drawbox` replacement, then straight-alpha overlay the unchanged foreground onto that branch before scaling/framing. Encode opaque PNG RGB24 or JPEG YUVJ444P. Admit every branch/conversion surface before launch; actual alpha/orientation/color fixtures must prove the graph.
- [ ] Use generated owned temporary paths and immutable source bytes, never the original mutable artifact path as FFmpeg input. Check all planned surfaces before starting the memory-contained renderer. Encode PNG, inspect opened output length, then read bounded or remove it and try q2/q3/q4 serially. Validate final magic, complete container, dimensions, byte limit and digest; failures publish nothing. Always remove only the owned temporary directory.
- [ ] Extend the build script's path checks before staging cleanup; use native PowerShell deletion of a verified path inside its output root rather than passing computed deletion targets to another shell. Build with `pwsh -NoProfile -File scripts/ffmpeg/build-rook-ffmpeg.ps1 -InstallPayload`; this updates the repository payload, not the installed Rhino runtime.
- [ ] **GREEN:** focused renderer tests; `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/tests/ffmpeg-bundle-validation.tests.ps1`; `pwsh -NoProfile -File scripts/validate-ffmpeg-bundle.ps1 -SourceBundleManifestPath artifacts/ffmpeg/ffmpeg-8.1.1-rook-minimal/rook-ffmpeg-source-bundle-manifest.json`. Preserve old H264/VP9 poster/first/last extraction.
- [ ] Run real renderer qualification separately for net48/net7.0/net8.0 x64, through production code and Job runner. Freeze measured fixture hashes/encoding oracles after inspecting actual pixels. Cover every supported shape/resolution, WebP lossy/lossless/alpha, all orientations, 16-bit conversion, upscaling, real PNG→JPEG fallback, missing/mismatched binary, encoding failure, deadline and memory-limit probes. Require repeat-run and cross-target content identity; an unexplained byte difference blocks profile qualification.
- [ ] Commit: `git commit -m "feat: qualify bounded FFmpeg still-image framing profile"`. Include updated binary/provenance/recipe/license and fixture changes together; do not mark profile qualified from a build or `-filters` output alone.

**Primary source:** the [FFmpeg 8.1.1 configure source](https://github.com/FFmpeg/FFmpeg/blob/n8.1.1/configure) defines codec dependencies; [filter documentation](https://ffmpeg.org/ffmpeg-filters.html) documents the operations. The actual pinned binary/fixtures remain the release evidence.

### Task 5: Share preparation through a bounded private preview cache

**Files**
- Create: `Framing/VideoFramingPreparationService.cs`, `VideoFramingCache.cs`, `VideoPreparedBundle.cs`, `VideoFramingPreview.cs`.
- Modify: `src/Rook/Services/Vision/Video/VideoSubsystemFactory.cs` and its `VideoSubsystemBundle`.
- Test: `src/Rook.Tests/Services/Vision/Video/VideoFramingCacheTests.cs`, `VideoFramingPreparationTests.cs`.

**Interfaces**
- `VideoFramingPreviewRequest(string Model, VideoMode Mode, IReadOnlyList<VideoFramingSourceSlot> Sources, string Resolution, string AspectRatio)`; a slot has semantic role and original `MediaRef`. Validate supported model/mode and exact start/end roles without requiring a generation prompt, provider options or credentials.
- `VideoFramingPreparationService.PreviewAsync(VideoFramingPreviewRequest request, CancellationToken ct) : Task<VideoFramingPreviewResult>` returns independent Fit/Fill slot results with preview IDs/roles, original/prepared identities, dimensions, recipe and errors.
- `PrepareSelectedAsync(VideoRequestIntent intent, VideoPreparationLease lease, CancellationToken ct) : Task<VideoPreparedBundleResult>`; result contains an owned `VideoPreparedBundleLease? Bundle` or `GenerationError? Error`.
- `VideoPreparedBundleLease : IDisposable` exposes `Originals : VideoPreparedMediaSnapshot`, `Prepared : VideoPreparedMediaSnapshot`, defensive-cloned `SourcePreparation : JsonObject?` and a cache pin. For omitted framing the snapshots can share original storage; no renderer is resolved.
- `VideoFramingCache.TryOpenPreview(Guid id, string role) : Stream?` returns a read-only stream that pins the entry until disposal. `Dispose`/eviction releases only feature-owned buffers and IDs.

- [ ] **Write tests:** `Preview_BothVariantsInterpolationAndNoProviderAccess`, `Cache_ByteCountEntryCountTtlAndPinnedExhaustion`, `Cache_CancelOneCallerDoesNotReleaseAnotherPin`, `Cache_ExpiredIdsRegenerateIdenticalContent`, `Preview_ExtremeFillFailureKeepsFitUsable`.
  ```csharp
  Assert.Equal(new[] { "start_frame", "end_frame" }, preview.Fit.Slots.Select(s => s.Role));
  Assert.Equal(0, spies.SecretReads + spies.Uploads + spies.ProviderCalls + spies.JobsCreated);
  Assert.True(cache.RetainedBytes <= 268_435_456 && cache.BundleCount <= 16);
  Assert.Null(cache.TryOpenPreview(expiredId, "image"));
  Assert.Equal(first.PreparedDigests, regenerated.PreparedDigests);
  Assert.NotEqual(first.PreviewIds, regenerated.PreviewIds);
  Assert.True(otherPinnedJob.CanReadPreparedBytes);
  Assert.True(preview.Fit.Success);
  Assert.Equal("render_limits_exceeded", preview.Fill.ErrorDetail);
  ```
- [ ] **RED:** `dotnet test src/Rook.Tests/Rook.Tests.csproj -p:RhinoPluginDir= --filter "FullyQualifiedName~VideoFramingCacheTests|FullyQualifiedName~VideoFramingPreparationTests"`.
- [ ] Implement one shared resource/cache/preparer instance in `VideoSubsystemFactory`. Acquire once per preparation phase; pass the same lease through nested reads/rendering so two jobs cannot deadlock reacquiring the two bundle permits. Carry the preflight deadline from before queue admission. Process modes/slots/encoding attempts serially, releasing all owned reservations on failure/cancellation.
- [ ] Key completed-cache reuse by verified original identities, target geometry, mode and verified profile/renderer identity. Resolve originals with bounded reads before accepting content-based reuse; a ref-only or preview-token lookup cannot conceal replacement. Atomically transfer encoded-buffer ownership into retained-cache accounting before releasing transient charges; no uncounted copies. Charge unique backing capacities once, preserve every ordered role, and account pinned entries against both cache limits.
- [ ] Store preview pixels as private cache-owned immutable buffers addressed by generated GUID plus `image` role. Open them through the existing blob mechanism in Task 8; do not create main `ArtifactStore` entries. This keeps previews nongallery without filtering historical image/video artifacts. Stream pins participate in eviction; no main-store delete call is needed. Drop unknown/stale IDs, not original artifacts.
- [ ] Reuse completed work without sharing a caller's cancellation source with another job. Independent in-flight work may converge atomically on the same completed entry; do not implement unbounded in-flight queues. Preserve successful variant results when another variant fails. TTL uses injected clock; cancellation/concurrency tests use barriers and deterministic permit accounting.
- [ ] **GREEN:** repeat focused tests, including two simultaneous jobs with different sources/modes, queued timeout, cache-full pins, selected-output cancellation and cleanup. Assert original file SHA256 and picker refs unchanged.
- [ ] Commit: `git commit -m "feat: cache owned Fit and Fill source previews"`.

### Task 6: Add framing contracts and report the route that can actually run

**Files**
- Modify: `src/Rook/Services/Vision/Video/VideoGenerationRequest.cs`, `VideoRequestIntent.cs`, `NormalizedRequest.cs`, `VideoJobRecordFactory.cs`, `VideoSubmissionCoordinator.cs`, `Fal/FalVeoCompatibility.cs`, `VideoJobManager.Routing.cs`.
- Modify: `src/Rook/Handlers/VideoOpHandler.cs`; `mcp_server/src/rook/server.py`; `mcp_server/tests/test_video_mcp_tools.py`.
- Audit: `src/RookNative/Handlers/VisionHandler.cpp` and `mcp_server/src/rook/agent/tool_dispatcher.py`; modify only if additive fields are lost.
- Test: `src/Rook.Tests/Handlers/VideoFramingContractTests.cs`, `src/Rook.Tests/Services/Vision/Video/VideoFramingAvailabilityTests.cs`.

**Interfaces**
- Append optional `SourceFramingMode? SourceFraming = null` to the request constructor; preserve it through `With`, `WithPrompt` and intent normalization. Persist the optional normalized field without changing omitted-field legacy JSON.
- `VideoSubmissionCoordinator.ResolveCandidates(VideoRequestIntent, VideoPreparedMediaSnapshot, DateTimeOffset) : IReadOnlyList<VideoRouteCandidate>` uses immutable prepared metadata, eliminating compatibility-time array clones.
- Extend `ModelAvailability(string model)` with `can_generate` and safe `generation_unavailable_reason` / detail code; `new_submission_available` retains endpoint-admission meaning. Presence is configuration metadata, not valid-key attestation.
- `FalVeoCompatibility.Validate` consumes the snapshot. Explicit framing validates prepared dimensions/bytes; omitted mismatched fal frames get `framing_choice_required` on `source_framing`.

- [ ] **Write tests:** `Contract_FramingIsStrictTopLevelAndOptionalForLegacy`, `Availability_GatePrecedesIrrelevantMediaError`, `Availability_GoogleWorksWithFalDisabled`, `Availability_SecretFailureIsNotMissingKey`. Parameterize fit/fill, null/nonstring/unknown, unsupported models/modes, missing fingerprint/cap and repeated role positions.
  ```csharp
  Assert.Equal("source_framing", invalid.Error!.Field);
  Assert.Equal("framing_choice_required", legacyFal.Error!.ProviderErrorCode);
  Assert.Equal(originalBytes, legacyGoogle.ProviderSourceBytes);
  Assert.Equal(0, legacyGoogle.RendererLookups);
  Assert.Equal("video_route_unavailable", unavailable.Error!.ProviderErrorCode);
  Assert.Equal("Video generation needs a Google API key. Fal Veo fallback is currently disabled.", unavailable.Error.Message);
  Assert.True(googleConfigured.CanGenerate);
  Assert.Equal(0, googleConfigured.UnusedFalSecretDecryptions);
  Assert.Equal("secret_access_failed", inaccessible.Error!.ProviderErrorCode);
  ```
- [ ] **RED:** `dotnet test src/Rook.Tests/Rook.Tests.csproj -p:RhinoPluginDir= --filter "FullyQualifiedName~VideoFramingContractTests|FullyQualifiedName~VideoFramingAvailabilityTests"` and `C:/Users/aryan/source/repos/Rook/mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_video_mcp_tools.py -q`.
- [ ] Parse `source_framing` once into the request, outside provider options. Reject unsupported uses rather than dropping them. New explicit submissions require both fingerprint and numeric cap at handler and manager boundaries; a direct manager caller cannot bypass confirmation. Omitted-field legacy contracts, references, unsupported tier options and Google person-generation intent remain intact.
- [ ] For explicit framing, run endpoint image compatibility against the selected prepared canvas, not the raw source's shorter-side or ratio. Include a low-resolution source successfully upscaled to 720p/1080p; omitted-field legacy fal retains its separately reviewed source profile.
- [ ] Resolve endpoint admission before its source compatibility. Missing Google plus disabled fal produces the exact route-unavailable message above; it does not render to prove a dead route's compatibility or quote a fake zero price. A configured Google primary stays available despite conditional fal errors. Preview service remains independent and works without keys.
- [ ] Add `source_framing` enum/property documentation to both MCP estimate and render schemas. Preserve scalar, confirmation and error fields identically through server and internal-agent dispatcher; no preview MCP tool, no changed tool-profile counts. Test absent/fit/fill bodies and genuine error propagation. Audit native whole-body forwarding and record the result; add a native field change only if the audit proves it is required, with matching managed test.
- [ ] **GREEN:** repeat focused commands and existing `VeoCredentialRoutingTests` / `FalVeoCompatibilityTests`. Assert all production `ContinuityVerified` flags remain false.
- [ ] Commit: `git commit -m "feat: add explicit video framing and actionable route availability"`.

### Task 7: Bind previews, quotes and durable dispatch to the actual bytes

**Files**
- Modify: `src/Rook/Services/Vision/Video/VideoRouteQuoteService.cs`, `VideoRouteQuote.cs`, `VideoEstimateFingerprint.cs`, `VideoPreparedMediaSnapshot.cs`, `VideoExecutionSnapshot.cs`, `VideoJobManager.Routing.cs`, `VideoSubsystemFactory.cs`, `IPreparedMediaVideoProvider.cs`, `VideoSubmissionCoordinator.cs`, `VideoProviderOutcomeAdapters.cs`, `VideoJobError.cs`.
- Modify: `src/Rook/Services/Vision/Video/VeoProvider.cs`, `Fal/FalVideoProvider.cs`, `Fal/FalVeoQueueAdapter.cs`, `Fal/FalSourceFrameTransport.cs`.
- Test: `src/Rook.Tests/Services/Vision/Video/VideoFramingQuoteTests.cs`, `VideoFramingDispatchTests.cs`; extend `VideoExecutionSnapshotTests.cs` and existing stop/publication races.

**Interfaces**
- Add `VideoRouteQuote.SourcePreparation : JsonObject?` as a defensive clone; canonical identity includes original + prepared evidence and recipe, excludes private preview IDs/URLs.
- `VideoRouteQuoteService.QuotePreparedAsync(VideoRequestIntent, VideoPreparedBundleLease, CancellationToken) : Task<VideoRouteQuoteResult>`; initial `QuoteAsync` prepares under preflight ownership and releases its lease after projection.
- `VideoRouteQuoteService.RevalidateForDispatchAsync(VideoRequestIntent, VideoPreparedBundleLease held, VideoRouteQuote accepted, VideoSubmitConfirmation, VideoRouteCandidate, VideoPreparationLease, CancellationToken) : Task<VideoRouteQuoteResult>` uses the held payload plus a bounded fresh original check and current route/prices.
- Add `VideoPreparationLease` parameter to `IPreparedMediaVideoProvider.SubmitPreparedAsync` and the coordinator/adapter chain. `VideoPreparedMediaSnapshot.ToResolvedMedia(VideoPreparationLease) : VideoResolvedMediaLease` reserves clones and owns them until disposed. `VideoResolvedMediaLease.Media` exposes the existing dictionary only during serialization/send; fal upload copies use the same budget.

- [ ] **Write tests:** `Quote_FingerprintBindsRecipesButNotPreviewIds`, `Dispatch_PreviewEqualsGoogleInlineAndFalUploadBytes`, `Dispatch_SourceAbaCannotValidateDifferentPreparedBytes`, `Dispatch_DerivedTamperAndProfileChangeRequireReconfirmation`, `Dispatch_SeparateJobsKeepPinsRoutesPricesAndStops`.
  ```csharp
  Assert.Equal(preview.PreparedSha256, quote.SourcePreparationSha256);
  Assert.Equal(preview.PreparedSha256, Sha256(capturedGoogleInlineBytes));
  Assert.Equal(preview.PreparedSha256, Sha256(capturedFalUploadBytes));
  Assert.Equal(first.Fingerprint, regeneratedWithNewPreviewIds.Fingerprint);
  Assert.NotEqual(first.Fingerprint, changedRecipe.Fingerprint);
  Assert.Equal(0, rejectedAba.GenerationSends);
  Assert.Equal("estimate_stale", rejectedAba.Error!.ProviderErrorCode);
  Assert.Equal(expectedOrderedRoles, persisted.PreparedMediaRoles);
  Assert.Equal(persisted.PreparedSha256, Sha256(actualPayload));
  ```
- [ ] **RED:** `dotnet test src/Rook.Tests/Rook.Tests.csproj -p:RhinoPluginDir= --filter "FullyQualifiedName~VideoFramingQuoteTests|FullyQualifiedName~VideoFramingDispatchTests|FullyQualifiedName~VideoExecutionSnapshotTests"`. Use synthetic HTTP/upload handlers that capture actual bytes, not provider-name stubs. Test-only binding catalogs enable fake fal without production edits.
- [ ] Include scalar framing, original refs/digests/length/MIME/oriented size, selected prepared digests/MIME/canvas, exact recipe/encoding and verified renderer identity in canonical confirmation along with existing endpoint bindings/profiles/prices. Keep `source_preparation` response data distinct from the scalar request. Never accept client-supplied preparation evidence as authoritative.
- [ ] At admission obtain/pin the selected immutable bundle; require its identity to match the accepted estimate and persist `source_preparation`. Cache miss can regenerate deterministically, but changed output/recipe requires fresh confirmation. Retain original provenance separately; `prepared_media` records the actual sent bytes. Corrupt/unsupported preparation evidence prevents further provider work on restart; legacy execution snapshots remain readable.
- [ ] Extend the existing closed safe-code mapping in `VideoProviderOutcomeAdapters` / `VideoJobError` with the new local codes; preserve allowlisted preparation detail in `video_execution.source_preparation_error` and its projection. Assert handler/status/result/list/cancel and restart retain code, role, mode, retryability and in-app action. No raw `ProviderDetail` bag is persisted or forwarded.
- [ ] Replace dispatch's independent `QuoteAsync` preparation with `RevalidateForDispatchAsync` using the same held payload. Freshly verify original identity, held prepared identity/recipe and current routes/pricing; do not validate an unrelated replacement snapshot. Reuse the phase's resource lease for fresh reads and adapter copies. Pin cache storage for job lifetime, release active preparation permits during remote polling, and dispose reservations/copies/pins in every terminal/failure path.
- [ ] Keep the actual Google inline encoder and fal uploader reading that immutable selected snapshot. Eliminate unbudgeted `CopyBytes/ToResolvedMedia/Capture` chains in compatibility and uploads. Revalidate after payload/upload preparation and before generation send; unchanged eligible fallback reuses the same prepared bytes and confirmed candidate price.
- [ ] Preserve transition-gate checks of first stop and latest terminal state. Stop/deadline cancels pending source reads/render/upload immediately even if append blocks; final evidence must still persist before acknowledgement. Persist dispatch intent before send and acceptance before polling. Retain completed artifact when marker finalization fails.
- [ ] Add barriers at resolution → rendering → upload/payload build → admission. Mutate A→B→A, alter/evict derived assets, change renderer/price, cancel/deadline under blocked/failing append, and restore ledger snapshots with send response held. Assert zero unintended sends/replays and original winning stop/completion.
- [ ] **GREEN:** focused command plus `VideoStopSubmissionRaceTests|VideoFalFallbackRaceTests|VideoFallbackPublicationTests|VideoFalFallbackManagerTests`; include provisional/unknown video and sidecar visibility.
- [ ] Commit: `git commit -m "feat: bind framed source bytes to quotes and durable video dispatch"`.

### Task 8: Present actual framing cards and preserve actionable preflight state

**Files**
- Modify: `src/Rook/Handlers/VideoOpHandler.cs`, `src/Rook/UI/Vision/VisionWebSurface.cs`.
- Create: `src/Rook/UI/Vision/VideoFramingPreviewSession.cs`.
- Modify: `src/Rook/UI/Vision/Resources/index.html`, `styles.css`, `app.js`.
- Test: `src/Rook.Tests/Handlers/VideoFramingPreviewHandlerTests.cs`; extend `src/Rook.Tests/UI/Vision/VisionWebSurfaceTests.cs`.
- Create: `src/Rook.Tests/UI/Vision/video-framing.test.cjs` and `Fixtures/video-framing-bridge.json`; extend the existing `video-fallback.test.cjs` harness as needed.

**Interfaces**
- Handler `OpPreviewFraming = "preview_video_framing"` dispatches to Task 5's preview service; estimates project quote `source_preparation`. Add the service to handler composition without changing public HTTP ownership.
- Per-surface `VideoFramingPreviewSession.RunAsync(long revision, Func<CancellationToken,Task<ApiResponse>> prepare, CancellationToken ct)` and `Cancel(long revision)`: monotonic revision cancels older preview work only. The same preview bridge op accepts `cancel_only: true` plus `preview_revision` on leaving/hiding the flow; a cancel-only message creates no assets/quote/job. Late older revisions never restart work. Dispose session on surface shutdown.
- JS video module: `refreshFramingPreview()`, `selectFraming(mode)`, `refreshAvailability()`, `ensureCurrentEstimate()`. Keep `framingState` and `estimateState` independently in `idle|pending|ready|failed|invalidated`, each with request identity/revision, result or retained typed error.
- Blob resolution first asks the shared cache for a currently owned preview stream; normal artifacts still pass the existing video durable-completion fence. Unknown/expired previews get 404.

- [ ] **Write tests:** `PreviewHandler_NoCredentialsAndNoGenerationSideEffects`, `Blob_PrivatePreviewDoesNotLoosenVideoFence`, plus Node cases `framing cards preserve deliberate Fill`, `late responses cannot confirm another source`, `estimate failure survives Generate and retry`, `settings refresh beats stale availability`.
  ```csharp
  Assert.True(preview.Success);
  Assert.Equal(0, spy.ProviderCalls + spy.JobsCreated);
  Assert.Equal(404, expiredPreview.Status);
  Assert.Equal(404, provisionalVideo.Status);
  Assert.Equal(404, unknownOwnerSidecar.Status);
  Assert.Equal(200, completedWithFailedMarkerFinalization.Status);
  Assert.Equal(0, gallery.PreparedPreviewCount);
  ```
  ```javascript
  assert.equal(ui.selectedFraming(), "fill");
  assert.equal(ui.currentError().detail_code, "video_route_unavailable");
  assert.equal(ui.statusText().includes("adjust a field"), false);
  assert.equal(bridge.submitCalls.length, 0);
  assert.equal(ui.costModalOpen(), false); // pending/mismatched preview and quote
  assert.deepEqual(ui.sources(), originalSources);
  ```
- [ ] **RED:** `dotnet test src/Rook.Tests/Rook.Tests.csproj -p:RhinoPluginDir= --filter "FullyQualifiedName~VideoFramingPreviewHandlerTests|FullyQualifiedName~VisionWebSurfaceTests"`; `node --test src/Rook.Tests/UI/Vision/video-framing.test.cjs src/Rook.Tests/UI/Vision/video-fallback.test.cjs`.
- [ ] Route preview asynchronously off the Rhino/UI thread, with session cancellation linked to the 15-second total service budget. Preserve typed preparation failures rather than rewriting them as a generic 180-second image-op timeout. Supersession kills only the old session's owned renderer; cached bytes pinned by a job remain alive. Check revision before starting and before exposing results.
- [ ] Add accessible radio cards directly below Aspect ratio: **Fit — keep whole image** / “Adds padding automatically. Nothing is cut off.” and **Fill — crop to frame** / “Fills the output shape. Some edges may be cropped.” Default Fit once, preserve deliberate choices through ordinary edits and Settings; show both start/end previews for interpolation, source dimensions separately, visible focus/checkmark, arrow/space keyboard selection, loading/error state and upscaling hint.
- [ ] Always send selected scalar framing for the supported panel flow; omit it elsewhere. Never present an old preview as current. Failure of the other card does not invalidate the selected successful card. For oversized Fill offer **“Choose Fit to keep the whole image.”**; switch only when that action is chosen.
- [ ] Retain actual estimate failure with argument identity. Generate awaits/refreshes the current estimate, surfaces its current error/action and never opens confirmation on failure. Retry requires no dummy edit. Only real argument/media/price changes mark estimates invalidated. Require selected preview's prepared identities to match `source_preparation` before confirmation; show selected framing, effective provider and price in the existing modal.
- [ ] Place preparation errors at cards, route/credential status above Generate, price in the cost strip. Copy allowlisted local error/detail fields through handler and `bridgeCall`. Missing Google + disabled fal uses exact approved message and **Open Settings**. Refresh availability after successful Settings save and on panel return; late older results cannot overwrite it. Never automatically submit/replay when availability recovers.
- [ ] **GREEN:** repeat focused checks. Test rapid source/ratio/resolution changes, out-of-order preview/estimate/Settings replies, failed estimate then successful retry without edits, expired preview ID, modal-open invalidation, unsupported-mode hide/cancel, and end-to-end safe renderer errors. Keep original history/picker selections.
- [ ] Commit: `git commit -m "feat: add Fit and Fill previews with actionable video preflight"`.

### Task 9: Verify the integrated offline implementation and obtain independent review

**Files**
- Create: `src/Rook.Tests/Services/Vision/Video/VideoFramingAcceptanceTests.cs`.
- Create: `scripts/qualify-video-source-framing.ps1`; extend the qualification project's `RendererQualification.cs` to exercise installed-style relative lookup.
- Create: `docs/superpowers/research/2026-10-15-video-source-framing-qualification.md` with actual evidence after execution, not prewritten success claims.

- [ ] Add integrated acceptance tests through real artifact resolution, handler, quote, manager and synthetic provider HTTP capture. Parameterize **preview / estimate / submit cache miss / omitted-field legacy** for oversized, growing-within-cap, growing-past-cap, changed and cancelled reads. Assert no partial preview, quote, upload or send after rejected input. Test source orientation/animation, two independent concurrent jobs, pinned exhaustion and unmodified originals. RED: `dotnet test src/Rook.Tests/Rook.Tests.csproj -p:RhinoPluginDir= --filter FullyQualifiedName~VideoFramingAcceptanceTests`.
- [ ] Wire any remaining composition gaps using the interfaces above; do not duplicate preparation inside handlers/adapters. GREEN on acceptance tests before broad verification.
- [ ] Implement qualification orchestration: build the actual companion/console in Release, separately run **net48, net7.0, net8.0 x64**, and stage each in a temporary installed-style directory with the actual managed assembly and `ffmpeg/` payload. Mirror the existing test assembly-resolution pattern and copy required matching RhinoCommon references from already resolved/installed Rhino assets, without new package references. Exercise the production bundled locator and hash verification, real rendering and Windows probes. Inspect image pixels via an independent PNG/JPEG decoder; WebP is decoded by the qualified production path. Record binary/assembly/fixture hashes, framework/OS, actual encoding choices, output digests, peak commit, cleanup and failures. No shared source-code-only substitute for running each target.
- [ ] Run `pwsh -NoProfile -File scripts/qualify-video-source-framing.ps1 -ReportRoot artifacts/video-source-framing-qualification`. Missing runtime, unsupported filter/format, memory-enforcement failure, unexplained target-dependent bytes, or omitted fixture blocks qualification; report it and fix within scope. Do not skip a target and call the profile qualified.
- [ ] Run the established regression checks sequentially:
  ```powershell
  dotnet test src/Rook.Tests/Rook.Tests.csproj -p:RhinoPluginDir= --filter "FullyQualifiedName!~LiveSmoke&FullyQualifiedName!~SupersededSolverRaceSpec_LinksToTheNormativeLifecycleDesign&FullyQualifiedName!~Task7_original_producer_values_survive_managed_http_parser" --logger "console;verbosity=minimal"
  node --test src/Rook.Tests/UI/Vision/image-fallback.test.cjs src/Rook.Tests/UI/Vision/video-fallback.test.cjs src/Rook.Tests/UI/Vision/video-framing.test.cjs
  C:/Users/aryan/source/repos/Rook/mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_video_mcp_tools.py mcp_server/tests/test_server_tool_profiles.py -q
  dotnet build src/Rook/Rook.csproj -c Release --no-restore -p:RhinoPluginDir=
  git diff --check
  ```
  Preserve the existing exclusions: live smoke, unavailable historical solver-design fixture, and unavailable `ROOK_TASK7_HTTP_FIXTURE`. Report exact counts/warnings, exclusions and any newly discovered limits; do not copy earlier counts as new evidence.
- [ ] Verify the actual production binding catalog still denies every fal Veo submission. Confirm no native ABI/routes, MCP profile counts, or installed runtime files changed. The temporary installed-style qualification is local managed/renderer evidence; Rhino-host/native/deployed behavior, billing, quality and continuity remain separate.
- [ ] Write the qualification report linking test artifacts and unresolved limitations. Commit: `git commit -m "test: qualify automatic video framing across managed runtimes"`.
- [ ] Use `superpowers:requesting-code-review` to obtain **one fresh independent final review** of implementation commits and full branch diff against `4978b444`, with `b482d365` plus the approved plan/exception as requirements. Reviewer checks ownership/accounting, Win32 containment, actual payload identity, UI races, legacy compatibility and unchanged production gate. Fix blocking findings, rerun affected checks, and obtain reviewer confirmation before sign-off.
- [ ] Stop for human review of the result. Do not merge, deploy or enable fal under this plan.

## Acceptance coverage map

Numbers refer to the approved spec's 19 acceptance cases.

| Cases | Owning tasks / evidence |
| --- | --- |
| 1–3: motivating image, geometry, interpolation/original preservation | 3–5, 8–9: pixel oracles, actual cards, ordered roles and original hashes |
| 4: real formats, orientation/alpha/upscale/encoding/failure paths | 2–4, 9: real renderer matrix plus deterministic error tests |
| 5: preview equals actual Google/fal sent bytes | 7, 9: decoded inline/upload captures compared with prepared digests |
| 6–8: keyless preview, route gate, legacy and wire compatibility | 1, 5–6, 8–9: zero-provider spies, bounded legacy reads, handler/Python contracts |
| 9–10: fingerprints, cache identity, A→B→A and tampering | 5, 7: actual held payload barriers and regeneration identity |
| 11–12: asynchronous UI and truthful estimate retry | 8: production event handlers with controlled bridge replies |
| 13: cache expiry/pins/concurrent job ownership | 1, 5, 7: exact counters, injected clock, deterministic cancellation |
| 14–15: lifecycle/publication/gate/deployment boundaries | 7–9: stop/append/restart races, blob fence, production catalog and staged hashes |
| 16: intermediate limits/overflow/independent Fit | 3–5: no-launch assertion for extreme Fill and successful real Fit |
| 17: hard memory enforcement/global resource bounds | 1–2, 4–5, 9: Windows process/group probes plus resource counters |
| 18: original boundary across all entry paths | 1, 7, 9: real resolver and controlled-growth streams before allocation/freezing |
| 19: real animation rejection/static controls | 3–5, 9: declared-single/multiframe fixtures, no full decode/assets/provider calls |

## Planning self-review and handoff

Coverage checked against every spec section and acceptance case; resource bounds have distinct owners and tests. Interface names above are shared across tasks; no task authorizes changing production fal eligibility. Review Focus cases have owning tests. The zlib exception is the one explicit design/working-rule decision left for human approval; it is not implementation permission.

This plan awaits review. After approval of the plan **and the dependency exception**, use the preserved native execution method in this chat and finish with the independent review in Task 9.
