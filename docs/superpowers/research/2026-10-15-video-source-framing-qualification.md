# Automatic video source framing — offline qualification

Implementation requirements: approved design `b482d365`, plan `c3df7f62`, and the user's explicit permission to statically link license-compatible zlib inside FFmpeg. Product comparison base: `4978b444`. Branch: `codex/vision-video-framing-spec`.

## Observed verification

Executed locally on Windows x64, October 15, 2026 (reports use UTC October 16). No installed runtime, Rhino process, provider credential, production continuity flag, or remote generation was changed.

| Check | Observed result |
| --- | --- |
| Managed tests | 4,730 passed, 0 failed, 0 skipped after the stated exclusions |
| Vision image/video/framing Node tests | 64 passed |
| Python video contracts and server profiles | 98 passed |
| Managed Release, all three target frameworks | 0 errors, 481 warnings |
| FFmpeg source/payload validation and policy tests | Passed, including existing H.264/VP9 sidecar extraction |
| Real staged renderer qualification | 39 cases per target, net48/net7.0/net8.0; identical prepared bytes and recipes |
| Windows process-group probes | Passed separately on all three targets |
| Installed runtime hash comparison | All 67 baseline files unchanged |
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

Latest [machine-readable qualification](../../../artifacts/video-source-framing-qualification/20261016T013404-00a6cb49/qualification.json) links per-target assembly hashes, fixture identity, renderer cases and process probes. The same directory's `verification/` contains test/build logs and installed-runtime baseline/final comparisons. The frozen content oracle is [qualified-profile.json](../../../third_party/ffmpeg/fixtures/framing/qualified-profile.json). Reproduce with `scripts/qualify-video-source-framing.ps1` after generating the local stress fixture; the script stages only inside checkout `artifacts/`.

This qualifies the managed/renderer offline paths on this machine. Native builds, Rhino-host UI behavior, the installed runtime, provider billing/quality, and endpoint continuity remain unqualified. No deployment, merge, push or live generation is part of this work. Independent final review is pending at this report's initial commit.
