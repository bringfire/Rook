# RookVision (Image Track) — Checkpoint

**Date:** 2026-04-22
**Status:** Mid-stream pause. PRs #90–#93 merged to `main`. PR-4 (Tier 3 viewport capture) is the next slice.
**Audience:** Future Claude / Codex / human picking up the SA_Banana → RookVision integration after a session gap.

---

## Locked framing

> **Lift the image subset of SA_Banana into Rook-native boundaries.** Not "bring SA_Banana over." SA_Banana is precedent; Rook architecture is the destination. Anywhere SA_Banana's shape conflicts with Rook's substrate / boundaries / conventions, **Rook wins**.

This framing governs every cut decision. Concretely:
- WebUI is **not** lifted wholesale — image-only UI subset, transport rewritten against the typed bridge.
- `MediaStorage`, `VideoHandler`, `Models/Video*.cs`, `app.js` (video-shaped) are **out**.
- Settings + artifact contracts are introduced as **neutral, image-first** Rook infrastructure (with shape that allows future video extension), not ports of SA_Banana types.

---

## Anchor docs (read these first on resume)

1. [`rook_docs/2026-04-08-sa-banana-integration.md`](./2026-04-08-sa-banana-integration.md) — master plan. v2.2 image plan is **locked**; v3 video addendum is **superseded** for binding decisions by v3.1 ([`2026-04-22-v3-video-decisions.md`](./2026-04-22-v3-video-decisions.md), locked 2026-04-25).
2. [`rook_docs/2026-04-22-v3-video-decisions.md`](./2026-04-22-v3-video-decisions.md) — **v3.1 locked video contract.** D1–D5 + retired Q6, pinned route paths, `VideoJobLedger` schema, submit-time payload constraints, sensitivities, and the PR-0 → PR-V1a/V1b → PR-V2 → PR-V3/V4 roadmap. Read before any video PR scope.
3. [`rook_docs/2026-04-09-webui-substrate-module-boundaries.md`](./2026-04-09-webui-substrate-module-boundaries.md) — what's substrate vs. shared capability vs. module; transport patterns A/B; artifact-as-currency rule.
4. [`rook_docs/2026-04-10-webui-substrate-contract.md`](./2026-04-10-webui-substrate-contract.md) — proven substrate API as of Knowledge Graph ship. **PR-3 has since extended this with the Pattern A bridge** — re-read in light of `RookWebSurface`'s current state.

---

## 7-PR sequence

| PR | Slice | Status | Notes |
|---|---|---|---|
| #90 | `test(infra)`: scaffold `Rook.Tests` xUnit project | **Merged** `8975ccf` | net48 only; net7.0 deferred (SDK 9 / NETCoreApp 7 testhost incompat) |
| #91 | `feat(settings)`: `RookSettingsStore` + `RookPaths.SettingsRoot` | **Merged** `53489c1` | `%APPDATA%\Rook\settings.json`; section-based; locked failure semantics |
| #92 | `feat(artifacts)`: `ArtifactStore` + neutral manifest contract | **Merged** `336cea5` | `%APPDATA%\Rook\artifacts\<day>\{uuid}\`; identity = directory name; multi-blob `files[]` for forward-compat with video |
| #93 | `feat(webui)`: Pattern A JS↔C# bridge in `RookWebSurface` | **Merged** `7ec6835` | `RegisterBridgeHandler` + `IsBridgeAvailable` + `OnBridgeUnavailable` + virtual `ContentSecurityPolicy` + `ComposeDocumentScripts`; `BridgeDispatcher` extracted as `internal sealed` |
| **PR-4** | **`feat(viewport)`: Tier 3 in-memory viewport capture** | **Next** | Adds `inMemory: true` (and `raytracedConverge: true`) flags to native `/viewport`, proxied via bridge callback to companion `view.CaptureToBitmap()`. Existing Tier 2 `_-ViewCaptureToFile` path stays — additive. Per the 2026-03-21 RhinoCommon capability audit's named expansion list. |
| PR-5 | `feat(vision)`: Vision domain services + native routes + bridge callbacks | Pending | Lift `GeminiClient`, `PromptEnhancer`, `DepthMapGenerator` into `src/Rook/Services/Vision/`. `VisionHandler.cs` as the single validation boundary. C++ `/vision/*` routes. **No** MCP tools yet, **no** tab UI yet. |
| PR-6 | `feat(mcp)`: Vision MCP tools + agent-facing wiring | Pending | `rhino_render_view`, `rhino_enhance_prompt`, `rhino_capture_depth`, `rhino_vision_artifacts`, `rhino_vision_get_artifact`, `rhino_vision_approve`, `rhino_vision_consume_approved`, `rhino_vision_delete_artifact`. Apply the **4-surface audit rule** (description / personas / tool-catalog / knowledge-store). |
| PR-7 | `feat(vision-tab)`: VisionTab.cs (image-only) | Pending | Rehouse the image subset of SA_Banana's WebUI under `src/Rook/UI/Vision/Resources/`. Pattern A — JS bridge calls into `VisionHandler.cs`, no `fetch()`. WebView2 hardening checklist applied. CSP override sets `connect-src 'none'`. Closes the parity rule for image. |

---

## Hard deferrals (NOT in this batch)

- **All of video.** No `VeoClient`, no `VideoJobManager`, no `VideoCapabilities`, no `MediaStorage` port, no Veo provider work, no cost gating, no NLE integration. Reopened by the v3 addendum and waiting on Codex answers (see below).
- LiteLLM provider routing (still v2 per master plan; video would force it but video is deferred).
- Artifact `flags.approved` / `consume_approved` enforcement — Vision affordance, lands with PR-6.
- `manifest.index.json` fast-enumeration cache — perf-driven, not foundational.
- Cross-process file locking on artifacts/settings — single-writer assumption holds for v1.
- `RookVision` separate `.csproj` — promote when ≥5k LOC or independent NuGet deps.

---

## Answered: v3 video questions (resolved 2026-04-25)

The four v3 video questions were sent to Codex on 2026-04-22 and answered the same day. The answers were promoted into a binding pre-implementation contract on 2026-04-25 after a two-round tightening pass.

- **Codex's verbatim answers:** [`2026-04-22-codex-v3-video-answers.md`](2026-04-22-codex-v3-video-answers.md)
- **Locked v3.1 decisions (D1–D5):** [`2026-04-22-v3-video-decisions.md`](2026-04-22-v3-video-decisions.md) — read this when scoping any video PR

The four questions map to:
- **Q1 → D1** (`A+disk-sideband`)
- **Q2 → D2 + D2.1** (Phase 1 hedge sufficient; submit MUST NOT accept inline base64)
- **Q3 → D3** (native-owned job contract; routes pinned)
- **Q4 → D4** (hybrid — in-memory active + `VideoJobLedger` for terminal/interrupted)

Plus **D5** (ABI v14 reuse, no v15 bump) and **Q6 retired** (cost split: estimation = domain, gating UX = adapter).

---

## What's already locked across PRs (don't relitigate)

These decisions came out of multi-round Codex review during PRs #91–#93. Drift = wasted review cycles.

- **Manifest casing:** uniform `snake_case` everywhere (`schema_version`, `created_at`, `parent_ids`, `files[].role`, `files[].path`). C# records are PascalCase; serialization pins via direct `JsonObject` building.
- **Identity rule for artifacts:** the directory name `{uuid}` is the identity. Manifest `id` field must equal the directory name. Day buckets are storage partitions only — **not** part of identity. Duplicate UUIDs across buckets = `InvalidDataException`. `.tmp` directories never visible to consumers.
- **Atomic create:** build into `<day>/{uuid}.tmp/`, write blobs + manifest, then `Directory.Move` to `<day>/{uuid}/`. Failure → best-effort `try/finally` cleanup of `.tmp`.
- **Read-time validation re-applies write-time invariants** — a hand-edited manifest must not deserialize into an `Artifact` that violates Create-time rules.
- **`files[].path` is flat-only in v1.** Regex `^[A-Za-z0-9][A-Za-z0-9._-]*$` + explicit `..` ban + canonicalization defense-in-depth. No subdirectories.
- **`created_at` requires explicit offset** (`Z` or `±HH:MM` / `±HHMM`). Pre-validated via regex before `DateTimeOffset.TryParse` — `RoundtripKind` alone silently accepts offset-less and treats as local time.
- **Bridge error contract:** generic only (`"invalid request"`, `"unknown method"`, `"handler failed"`). Substrate **never** leaks `ex.Message` to JS. Full exception detail goes to log only. A future v2 may add a typed `BridgeException` whose message IS forwarded — opt-in.
- **Bridge script injection order:** nonce → bridge shim → surface bootstrap. Tests pin the order.
- **Bridge availability lifecycle:** `IsBridgeAvailable` settled inside `ConfigureVirtualHost` BEFORE `Navigate`, so it's correct by the time `OnDocumentLoaded` fires. `OnBridgeUnavailable` is one-shot per surface instance.
- **CSP is virtual on `RookWebSurface`,** default preserves Pattern B (`connect-src http://127.0.0.1:*`). Vision overrides to `connect-src 'none'`. Default value is regression-pinned in tests.
- **`BridgeDispatcher` is `internal sealed`,** tests reach it via `InternalsVisibleTo("Rook.Tests")`.
- **Test project targets net48 only.** net7.0 testhost crashes under SDK 9 (`HRESULT 0x80070057`); deferred until .NET 7 SDK installs or `<RollForward>LatestMajor</RollForward>` workaround is needed.
- **No PR includes pre-existing local working-tree changes** (`AGENTS.md`, `knowledge/*`, `.scratch/`, `mcp_server/_*_test.py` probes). They've been in the working tree since the integration started; staging is always by-name, not `-A`.

---

## What PR-4 will need (investigation guide for resumption)

1. **Read** `src/RookNative/Handlers/ViewportHandler.cpp` (esp. lines 71–202) — current `/viewport` route shape, parameters, Tier 2 `_-ViewCaptureToFile` invocation point.
2. **Read** `src/Rook/InternalBridge/NativeGhBridgeRegistrar.cs` — established bridge callback registration pattern. Look at the existing non-GH callbacks (Make2d, Gumball, Block, GameExport, BakeOutput, ScriptParams) for reference shape.
3. **Read** `src/Rook/Handlers/*.cs` — specifically the handlers that already proxy from native via bridge (e.g., `BlocksHandler.cs`) — for the C# side pattern: how arguments cross the boundary, threading discipline, return shape.
4. **Decide ABI question:** is this an ABI version bump? Existing callbacks suggest the bridge ABI is versioned. Adding a new callback for `CaptureToBitmap` likely requires a bump.
5. **Decide return shape:** in-memory base64 PNG returned over HTTP, or written to a temp file the caller fetches? In-memory base64 is simpler for v1 but inflates response size. Lean: base64 for v1; revisit if perf bites.
6. **Decide raytraced convergence semantics:** how long to wait for Cycles to converge before capturing? Hard timeout? Quality-based? SA_Banana's `ViewportCapture.cs` has a working implementation — port the algorithm, don't reinvent.
7. **Threading:** capture must happen on Rhino's UI thread. The bridge callback already serializes there; verify, don't assume.
8. **Pre-code note before coding** — substrate boundary + ABI shape + new bridge callback is exactly the change profile that warrants the scope-pass rhythm we've been using.

---

## Resumption checklist

> **Note (2026-04-25):** This checkpoint covered the image-track 7-PR sequence, which has since shipped in full (PRs #90–#102 merged, plus #103–#107 follow-on polish). For **video** work, the resumption path is the v3.1 contract at [`2026-04-22-v3-video-decisions.md`](./2026-04-22-v3-video-decisions.md), not this checklist.

1. Read this doc + the anchor docs.
2. `git log --oneline main -20` to confirm post-checkpoint history.
3. For video work: read v3.1 first, then draft PR-V1a's written scope pass per the scope-pass rhythm.
4. For image-track follow-ups: see the "Known follow-ups" list in the [project_rookvision_image_track.md](../../.claude/projects/c--Users-aryan-source-repos-Rook/memory/project_rookvision_image_track.md) memory entry.

---

## Decision log: deviations from the master plan

For traceability if anyone re-reads `2026-04-08-sa-banana-integration.md` and wonders why the implementation diverges:

- Master plan v2.2 said "lift ~1,000 LOC of services + WebUI assets." After the v3 video reopen, the actual lift target dropped to image services only (~500–600 LOC + image UI subset), with video deferred. **This is the "lift the image subset" reframe.**
- Master plan put `ArtifactStore` under `%APPDATA%\Rook\artifacts\vision\`. PR-2 ships under `%APPDATA%\Rook\artifacts\` (no `vision/` subdirectory) per the "no consumer-specific affordances yet" constraint. Namespacing can be added later if multiple subsystems need separation.
- Master plan's manifest schema (`{id, type, parent_ids, created_at, created_by, document_context, blob_path, metadata, flags}`) was tightened to PR-2's neutral `{id, kind, created_at, files[], parent_ids, metadata, flags}`. Single `blob_path` → `files[]` (multi-blob); `type` → `kind` (avoid confusion with bridge protocol `type`); `created_by` and `document_context` deferred to consumer metadata; `schema_version` added at top level.
- Master plan's bridge plan was implicit. PR-3 made it explicit: typed registration, generic error contract, `OnBridgeUnavailable` hook, virtual CSP, ordered script composition.
