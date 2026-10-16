# Automatic video source framing — offline qualification

Implementation requirements: approved design `b482d365`, plan `c3df7f62`, and the user's explicit permission to statically link license-compatible zlib inside FFmpeg. Product comparison base: `4978b444`. Branch: `codex/vision-video-framing-spec`.

## Observed verification

Executed locally on Windows x64, October 15, 2026 (reports use UTC October 16). No installed runtime, Rhino process, provider credential, production continuity flag, or remote generation was changed.

| Check | Observed result |
| --- | --- |
| Managed tests | 4,754 passed, 0 failed, 0 skipped after the stated exclusions |
| Vision image/video/framing Node tests | 67 passed |
| Python video contracts and server profiles | 98 passed |
| Managed Release, all three target frameworks | 0 errors, 481 warnings |
| FFmpeg source/payload validation and policy tests | Passed, including existing H.264/VP9 sidecar extraction |
| Real staged renderer qualification | 39 rendering cases and 10 legacy decode cases per target, net48/net7.0/net8.0; identical prepared bytes and recipes |
| Windows process-group probes | Passed separately on all three targets |
| Installed runtime hash comparison | All 67 baselined binary/debug/provenance files unchanged |
| Branch whitespace | Passed |

The managed filter excludes `LiveSmoke`, `SupersededSolverRaceSpec_LinksToTheNormativeLifecycleDesign` (unavailable historical fixture), and `Task7_original_producer_values_survive_managed_http_parser` (unavailable `ROOK_TASK7_HTTP_FIXTURE`). No additional exclusions were added.

The initial broad run identified the existing bridge fixture's missing additive `source_preparation: null` estimate field; explicit regeneration showed that single difference. A later run observed an unrelated BIM diagnostics timing assertion (`Writer_RejectsBraceDelimitedMalformedJson`: dropped count visible before degraded state). Both focused cases and the subsequent full 4,730-test run passed. BIM code/tests were not modified.

## Renderer and containment

The orchestration script builds with `RhinoPluginDir=` and copies the qualification host, actual companion/dependencies, and actual `ffmpeg/` payload into separate temporary installed-style directories. Each host uses the **production bundled locator**, verifies its resolved adjacent executable, then runs actual rendering and Win32 probes. It does not substitute a shared-source implementation or a PATH renderer.

The 39 cases include a repeat render; the matrix covers PNG/JPEG/lossy and lossless WebP, all eight EXIF orientations against independent pixel oracles, alpha composited onto opaque black, 16-bit and palette conversion, private/ICC metadata removal, matching/square/portrait/odd/thin/extreme sources, every supported canvas in Fit and Fill, and real PNG-to-JPEG fallback on deterministic 8,308,285-byte noise. An independent PNG decoder checks pixels; Windows' independent bitmap decoder checks JPEG dimensions, grayscale and bounded quantization error. The tagged source's output equals the untagged pixel-equivalent PNG byte-for-byte. Fixture manifests are forced to LF so their identity survives Git checkout settings.

Executable SHA-256: `1AE1F5B6F39E71E7D0BD921730DE407E2495F6D23F66668CF442AA4646C0896C`.

Each renderer group has its 512 MiB hard job limit installed and read back before the suspended process resumes. Probes verify assignment/limit failure is closed, memory-limit termination, descendants, cancellation, conservative 480 MiB notification, and refusal of a single 768 MiB allocation (Win32 1455, zero successfully allocated bytes). On this Windows build, `PeakJobMemoryUsed` includes rejected charge attempts and can exceed the configured limit even when allocation is refused. Reports therefore label it `PeakJobChargeBytes`; it is not a claim of peak admitted commit. Real rendering recorded about 304 MB maximum raw job charge, below the limit.

Root MIT and zlib's permissive license are compatible with this distribution. zlib 1.3.2 is pinned by source SHA-256, linked only into the separate LGPL FFmpeg executable, with its original notice and matching source/build provenance. The validated source bundle includes both source archives, recipe, metadata, license and linker map proving the owned static archive was selected. No new runtime DLL or managed/Python package was introduced.

## Integrated behavior and implementation rulings

- One shared pool bounds two active preparation phases, two queued phases, and two renderer processes. Further admission returns retryable preparation-busy; queued time participates in the same 15-second preflight budget.
- Bounded open-handle reads and reservation ownership apply to preview, estimate, uncached submission and omitted-framing legacy paths. Twenty integrated fault cases reject oversized, growing, shrinking and cancelled reads without accepting partial media, a job, or a provider send.
- The common cache counts each selected-mode bundle toward its 16-entry/256 MiB limits; a two-mode preview uses two entries. Shared original backing capacity is charged once. Stream/job pins retain ownership until the actual consumer exits, including consumers that ignore cancellation.
- Preview images are private no-store blobs. Generated-video sidecars require the same durable-completion authority before source reading; unknown/provisional ownership cannot be laundered into a new preview. A durably completed artifact remains usable when marker finalization needs repair.
- Google inline HTTP and fal upload captures match selected prepared digests. Streaming Google content uses fixed reserved chunks; fal copies remain reserved through the actual awaited upload. Quote revalidation uses the held immutable bundle, not a newly resolved payload; A→B→A, recipe tampering and repricing tests require reconfirmation.
- Fit defaults once; deliberate Fill survives form edits and Settings. Cards use actual prepared images, show start/end sources for interpolation, expose failed alternatives independently and do not reload unchanged images during prompt edits. Document reload preserves preview revision ordering. Actual estimate errors survive Generate and provide Retry/Choose Fit/Open Settings without dummy edits or replay.
- All production fal Veo continuity flags remain false. Native ABI/routes and MCP profile counts are unchanged. Existing durable dispatch, stop, restart and publication tests remain green.

## Evidence and limits

Latest [machine-readable qualification](../../../artifacts/video-source-framing-qualification/20261016T033249-8e546982/qualification.json) links per-target assembly hashes, fixture identity, renderer/legacy decode cases and process probes for corrected product commit `27d773f0` plus the partial-row PNG test additions. The same directory's `verification/` contains test/build logs and installed-runtime baseline/final comparisons. The 67-file baseline covers DLL/RHP/PDB/EXE and FFmpeg provenance; other installed files were not baselined. The frozen content oracle is [qualified-profile.json](../../../third_party/ffmpeg/fixtures/framing/qualified-profile.json). Reproduce with `scripts/qualify-video-source-framing.ps1` after generating the local stress fixture; the script stages only inside checkout `artifacts/`.

This qualifies the managed/renderer offline paths on this machine. Native builds, Rhino-host UI behavior, the installed runtime, provider billing/quality, and endpoint continuity remain unqualified. An optional isolated HTML visual check was blocked by the browser's local-file URL policy; no workaround was attempted and browser visual QA remains unverified. No deployment, merge, push or live generation is part of this work.

## Independent final review and corrections

A fresh reviewer inspected every implementation commit and the full `4978b444..1408a3c8` branch diff, reproducing two P2 issues and one latent P3. A single correction pass, `b279456a`, addresses all three:

1. Pool saturation after job admission now returns retryable local preparation-busy before coordinator entry or durable dispatch intent. The regression asserts no provider call, no attempt receipt, safe status attribution and complete resource cleanup; genuinely uncertain sends retain conservative handling.
2. Thumbnail callbacks now belong to an exact variant and preview generation. Unselected-card failure preserves the selected successful preview/quote; selected failure blocks confirmation; a late error from an older same-key retry cannot poison the current result. Three image-event-capable Node regressions failed before the fix and pass afterwards.
3. Bounded metadata inspection preserves legacy omitted-framing APNG admission. Default/explicit still inspection continues to reject animation, and animated-WebP admission is not broadened. The regression checks legacy compatibility, explicit preparation's typed error, no prepared assets and the disabled production binding.

All three findings had demonstrated failing regressions before product changes. The full suites and staged runtime matrix above were rerun after the corrections. The same reviewer inspected the correction diff and RED/GREEN evidence, confirmed all three addressed, checked the staged net8 assembly hash against its report, and approved `b279456a` for the reviewed scope with no outstanding findings. The reviewer did not rerun the broad suites. No additional reviewer was spawned. This approval does not authorize deployment, merging, pushing or enabling production fal.

## Follow-up review: legacy compressed-pixel validation

The user's review of `5bb7763b` identified a remaining P2: metadata admission could accept a checksum-correct 57-byte PNG with empty IDAT. Legacy fal skipped framing's decoder, so that input could reach upload and generation despite having no decodable pixels. New counterexamples extend this to JPEG and WebP and place corrupt media after a valid first input. Before the fix, all nine negative cases reached one or two upload calls; the valid APNG control passed.

Correction `27d773f0` keeps quote eligibility explicitly metadata-only (`ValidateMetadata`) and adds asynchronous complete-image validation at the actual fal source-upload boundary (`ValidateForUploadAsync`). All distinct legacy source payloads are validated before **any** upload. The check decodes the complete default image in the existing verified FFmpeg executable with strict decoder flags and the suspended, memory-contained Windows process runner. Source dimensions/pixels are admitted before launch; source-copy scratch is reserved; the discarded 1×1 PNG is limited to 4 KiB before bounded reading. No decoded raster enters managed memory. Error-concealed frames, failed enforcement, invalid output, cancellation and memory failure reject safely and release temporary ownership. The existing execution token and phase are reused; the 20-minute job budget is not reset.

Validation does not frame, publish or replace the original bytes. Valid legacy APNG retains default-image acceptance and uploads the exact original payload; repeated input roles remain ordered with deduplicated validation/upload. Explicit framing retains its prior qualified pixel decode. Google-only omitted-framing requests remain independent of the renderer.

The 22 new managed cases include fifteen corrupt-bitstream upload/generation barriers, one exact-byte APNG control, and six decoder failure/cleanup checks. The final full rerun passed 4,754 managed tests with unchanged exclusions; 67 UI and 98 Python tests passed, and Release rebuilt with 0 errors/481 warnings. Each staged target separately passed 39 existing rendering cases, ten real valid/corrupt legacy decode cases and Windows containment probes. The FFmpeg payload/source bundle passed validation and its executable/recipe/profile are unchanged. Test-only configuration disables xUnit's DLL-only shadow copy so the production adjacent-bundle locator can use the actual copied test payload; test parallelism is unchanged.

The same independent reviewer approved product correction `27d773f0` with no actionable findings. Its separate harness exercised the actual corrected assembly and contained Windows runner: five valid cases were accepted and eleven malformed cases were rejected, including JPEG scan truncations and PNGs with insufficient rows. Two partial-row PNGs exit FFmpeg successfully while reporting `IEND without all image`; the diagnostic rejection caught both. Those two cases now run as upload/generation barriers in all three input modes and in the real decoder matrix on every target. Only tests, fixtures, qualification tooling and this report changed after the reviewed product commit. The reviewer inspected the recorded broad-suite evidence rather than rerunning those suites. No merge, deployment, native build, live request or production fal enablement has occurred.
