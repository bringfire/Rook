# Video NLE Bridge Design

**Date:** 2026-04-26
**Status:** Draft v0.4 — open for iteration
**Related:**
- [`2026-04-09-grasshopper-video-nle.md`](2026-04-09-grasshopper-video-nle.md) — the original NLE vision (token model, four phases, twelve-component palette). Read first; this doc bridges that vision to the realization steps that became plausible after V4 shipped.
- [`2026-04-22-v3-video-decisions.md`](2026-04-22-v3-video-decisions.md) — v3.1 locked video contract. Wire shapes are frozen; this design must compose with them, not amend them.
- PR #116 (V4 closeout, merged 2026-04-26) — the parity-rule restore that made the NLE substrate observable from native HTTP, MCP, and the bridge through one contract.
- [Google AI for Developers: Generate videos with Veo 3.1 in Gemini API](https://ai.google.dev/gemini-api/docs/video) — current examples extract `.response.generateVideoResponse.generatedSamples[0].video.uri`.
- [Google Cloud: Generate videos with Veo on Vertex AI](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/video/overview) — current overview documents first/last frames as inputs and generated videos as video outputs.

---

## TL;DR

The original NLE doc (April 9) framed Grasshopper as a node-based video editor where wires carry `VideoClip` and `VideoFrame` *descriptors*, not pixels. That vision is still right. What's changed since April 9: the SA_Banana code that backed the proposal has been lifted into Rook-native boundaries (image track #90–#107, video track V1–V4), the artifact contract is now formalized, and the role-addressed media-ref shape (`{kind: "artifact_id", artifact_id, role}`) that the NLE token model needs is shipped and live-verified.

The remaining gap is mechanical, not architectural: **video artifacts today carry a single `video` blob; the NLE needs them to carry addressable `poster` / `start_frame` / `end_frame` blobs as well.** This doc proposes a tiered path from "where we are" to "GH components can compose video clips."

The non-obvious framing (credited to Codex round 1 on this thread, 2026-04-26): *poster is display metadata; end_frame is a reusable media input. They are different contracts.* Treating them as the same Tier 1 collapses two scopes that should ship separately.

---

## What V3/V4 actually shipped (load-bearing inventory)

Verified against `main` at commit `835d705`:

- **`VideoMediaRoles`** ([src/Rook/Services/Vision/Video/VideoMediaRoles.cs](../../src/Rook/Services/Vision/Video/VideoMediaRoles.cs)) defines `Poster`, `StartFrame`, `EndFrame` constants. The role *names* exist in the contract.
- **`VideoJobManager`** writes `generated_video` artifacts with **only one blob: `video`**. No code currently writes `poster` / `start_frame` / `end_frame` blobs onto a generated video.
- **`ArtifactOnlyVideoMediaResolver`** resolves `{kind: "artifact_id", artifact_id, role}` to a blob path via `ArtifactStore.GetBlobAbsolutePath`. The resolver is role-agnostic — any role on any artifact resolves the same way.
- **Vision gallery JS** ([src/Rook/UI/Vision/Resources/app.js:708–726](../../src/Rook/UI/Vision/Resources/app.js)) is already poster-aware: if a `generated_video` artifact has a `files[]` entry with `role === "poster"`, it renders `<img src="/blob/{id}/poster">`. If not, it shows a `"no video"` stub. The Codex review on PR #115 explicitly forbade eager MP4 preload; the poster-or-stub pattern is the locked v1 behavior.
- **Video frame picker JS** is not yet role-complete. It explicitly lists only `generated_image`, `captured_viewport`, and `depth_map` artifacts for start/end/reference frame selection. It does not list `generated_video` artifacts, even if they eventually carry `start_frame` or `end_frame` blobs. Tier 1B is therefore a real UI change, not just a backend contract exercise.
- **Submit-time media refs** accept `{kind: "artifact_id", artifact_id, role}` per V2 D2.1. The submit-side schema permits referencing *any* video artifact's *any* role as input to a new video job. Today there's nothing to reference because the manager doesn't write extra roles.
- **`ProviderFetchResult` currently carries exactly one byte payload.** It exposes `Bytes`, `MimeType`, and `Error`, not a collection of media blobs. `VideoJobManager` therefore cannot store `video + poster` without either extending the provider result shape or doing an extra manager-side fetch.
- **`ArtifactStore` identity is UUID-based, not content-addressed.** `ArtifactStore.Create` calls `Guid.NewGuid()` and has no dedup/index today. The artifact graph records provenance via `parent_ids`, but it is not yet a deterministic cache key.
- **The full NLE design doc has not been implemented.** No `.gha` plugin exists. No `VideoClip` / `VideoFrame` tokens exist in the codebase.
- **GH SDK grounding is available locally.** The extracted Grasshopper SDK reference now lives in-tree at `docs/gh_sdk_extracted/` (126 MB; gitignored via `.gitignore` line 2 since 2026-04-26 — was previously at `Rook-private-archive/docs/gh_sdk_extracted/` until v0.4 of this doc consolidated it). The installed Rhino 8 `Grasshopper.dll` is at `C:\Program Files\Rhino 8\Plug-ins\Grasshopper\Grasshopper.dll`. The SDK confirms the extension points we need for richer canvas UI: `GH_Component.CreateAttributes()`, `Grasshopper.Kernel.Attributes.GH_ComponentAttributes.Layout()`, `Render(GH_Canvas, Graphics, GH_CanvasChannel)`, and mouse handlers such as `RespondToMouseDown`. That makes in-component start/end thumbnails and buttons plausible, but still worth a focused spike because no Rook-owned component currently uses custom attributes. Future readers without the local extraction must re-extract from their Rhino 8 install (the SDK ships with Rhino as a `.chm` that decompiles to the same HTML tree).
- **Current Rook GH support is bridge automation, not a component library.** `GrasshopperHandler` and `GrasshopperCore` manipulate/query the active GH document through reflection and the native callback bridge. They can bootstrap definitions and inspect canvas state, but they are not a substitute for a first-class `.gha` NLE component assembly.

**The gap, stated precisely:** the contract supports addressable per-role media references on video artifacts; the runtime never produces them; the UI is ready to consume `poster` if it appears; nothing yet consumes `start_frame` or `end_frame`.

---

## Codex review notes for v0.2

These are the current implementation-pressure points that should shape the next revision.

1. **Do not assume Veo returns poster media.** Current Rook code extracts only a generated video URI from Veo and downloads only MP4 bytes. Current public Google docs for Veo also document generated output as video URI / GCS URI / base64 video bytes, while documenting first/last frames as inputs, not poster outputs. The Tier 2 audit should capture raw operation JSON from a real generation before any provider-poster design is accepted.
2. **Tier 1A is mostly contract/tests; Tier 1B is the first visible picker change.** The gallery already has poster display behavior. The picker is deliberately image-kind-only, so "use end frame as start frame" requires adding generated-video artifacts to the picker only when a frame role exists, and choosing the frame role rather than the `video` role.
3. **`poster` must stay display-only.** A poster can be provider-selected, cropped, or representative. `start_frame` and `end_frame` are exact media inputs for generation. The UI can display a poster, but chaining should use `end_frame` or `start_frame` only.
4. **The GH cache needs its own deterministic key.** Artifact GUIDs are durable handles, not content hashes. A `VideoClip.Id` can be a graph/content hash, but the materialized artifact id is a cache value looked up by that hash, probably through a new metadata field or cache index rather than by changing artifact identity.
5. **Provider multi-media output should be explicit.** If Tier 2 lands, prefer a provider-neutral shape such as `ProviderMediaBlob(role, bytes, mimeType, provenance)` over adding ad hoc `PosterBytes` properties. This keeps the door open for `poster`, `start_frame`, `end_frame`, timeline samples, and future provider variants without another interface churn.
6. **Native HTTP is the right GH integration surface post-V4.** A future `.gha` should call the RookNative HTTP video routes, not the old SA_Banana server and not managed internals. That implies a small port-discovery story for GH components, likely reusing the existing Rook instance discovery files rather than hard-coding a port.
7. **Separate planned frames from actual frames in the GH model.** For seamless chaining, `RequestedEndFrame` is not enough. The model may drift from the supplied target, so clip N+1 should eventually consume clip N's extracted `ActualEndFrame` as its `StartFrame`. Until Tier 3 extraction exists, the GH UI should label frame chaining as planned continuity rather than actual continuity.
8. **Do not let normal GH recompute submit provider jobs.** Rook video generation spends quota and can run for minutes. The GH palette should keep descriptor components mostly pure and route submission through an explicit `Run`/`Submit` action or render sink. `GH_TaskCapableComponent` is a useful reference for background work, but long-running provider polling should be designed deliberately rather than treated like a normal solve.

---

## v0.3 pre-scope decisions

Two v0.2 questions are important enough that future scope passes should treat them as provisional decisions unless an audit disproves them.

1. **Prefer extract-before-publish over append-after-create for Tier 3.** `ArtifactStore.Create` currently gives us the clean atomicity story: all blobs and the manifest become visible together. Tier 3 should preserve that if practical. The manager should download the MP4, extract `start_frame` / `end_frame` / optional `poster` into memory or temporary files, then publish one `generated_video` artifact containing all roles. A new append-blob API should be a fallback only if extraction-before-publish proves too slow, too memory-heavy, or incompatible with the provider success path.
2. **Run the Veo raw-payload audit before scoping Tier 2.** Tier 2 is unscopable until we know whether completed Veo operations expose poster-like media. The cheapest forward move is a non-product audit: capture one sanitized completed operation JSON from a real generation, record the exact response paths present, and update this doc. The audit must redact API keys, signed URLs, prompts if sensitive, and any raw bytes. It can live under `.scratch/` or as a one-off script, but only the findings should graduate into the design doc.

These decisions intentionally do **not** choose FFmpeg vs. WMF, the GH cache-index storage location, or the final GH component palette.

---

## FFmpeg dependency posture (provisional)

The current leaning is: **if Tier 3 uses FFmpeg, bundle a minimal LGPL-only FFmpeg executable with Rook rather than requiring users or office machines to install FFmpeg separately.** This is not a final legal decision, but it is the recommended engineering posture to preserve low-friction installs while avoiding GPL obligations for Rook.

What "bundle" means here:

- The Rook installer ships a normal `ffmpeg.exe` file, for example under `tools/ffmpeg/ffmpeg.exe`.
- Rook calls that executable as a subprocess for a narrow frame-extraction command contract.
- Users do not need to modify `PATH` or install FFmpeg manually.
- The executable remains visible and replaceable; it is not renamed, hidden, statically linked, or treated as an inseparable part of Rook.

LGPL-safe constraints:

- Use a build compiled without `--enable-gpl` and without `--enable-nonfree`.
- Avoid GPL libraries/features such as `libx264` / `libx265` in the bundled build.
- Verify the bundled binary with `ffmpeg -version` and archive the exact configure flags.
- Include FFmpeg license notices, version, source/build reference, and third-party attribution in Rook's installer/docs/about surface.
- Provide the corresponding FFmpeg source or exact source link/archive for the bundled binary.
- Do not prohibit reverse engineering of the LGPL component in any future EULA.

Replaceability contract:

- Rook should resolve FFmpeg in this order: admin/user configured path, bundled LGPL executable, optionally `PATH`.
- A replacement must be FFmpeg-compatible and support the exact commands Rook uses, starting with `ffmpeg -version` and first/last-frame extraction from MP4 to PNG/JPEG.
- Rook is responsible for surfacing clear errors from unsupported replacements, not for supporting arbitrary custom FFmpeg builds beyond the documented command contract.
- Power users or IT may choose a different FFmpeg build locally, including one with broader codec support, but that choice is outside Rook's bundled licensing posture.

This recommendation holds even if a future Grasshopper NLE layer is open source. Open-sourcing GH components is a product/support decision, not a licensing requirement for using an LGPL FFmpeg subprocess. The simpler default is to keep the NLE implementation in the normal Rook distribution and satisfy the LGPL obligations carefully for the bundled tool.

---

## Tier breakdown

The user's instinct on 2026-04-26 was "Tier 1 video gallery thumbnails." Codex (correctly) split that into multiple tiers because two different contracts were being collapsed. The split below is the working scope.

### Tier 1A — Role contract + UI consumption (no extraction)

**Scope:** Formalize `poster` / `start_frame` / `end_frame` as first-class optional roles on `generated_video` artifacts. Pin the existing gallery behavior: `poster` is preferred for gallery tiles, `video` remains the modal/playback role, and absent sidecars produce a graceful stub rather than eager MP4 preload. Add tests around this contract. **No extraction. No provider contract change. No backend mutation.**

**Why this ships first:** The contract is the thing that's load-bearing. Once roles are first-class, anything downstream — provider ingestion, frame extraction, NLE component thumbnails — has a stable API to write into. Tier 1A is also the cheapest forward-compatibility move available; it ships even if no role-bearing artifact ever appears, because the UI is contract-driven.

**Cost:** Small UI/test PR. ~30 min if limited to gallery contract and tests.

**Dependencies:** None. Composes with V4.

**Branch name proposal:** `fix/rook-vision-video-frame-roles`.

### Tier 1B — Artifact-level frame reuse

**Scope:** When a video artifact carries `start_frame` or `end_frame` blobs, surface picker actions like "use as start frame" / "use as end frame" that emit the existing `{kind: "artifact_id", artifact_id: "<video-uuid>", role: "end_frame"}` shape. The resolver already handles this; no schema change. The picker must list generated-video artifacts only for roles that are image-compatible sidecars; it must not offer the primary `video` role as a start/end/reference frame. UI must clearly distinguish "this frame came from a video artifact" from "this frame is its own image artifact."

**Why this is the bridge to the NLE token model:** The `VideoClip` token in the original NLE doc carries `Meta.poster`. The `VideoFrame` token carries an `ImagePath`. In the Rook materialization, both reduce to `{artifact_id, role}` references against the artifact store. Tier 1B is the UI exercise of that mapping — it proves the artifact-as-token shape works for users before any GH plugin is written.

**Cost:** Small UI PR. The current picker has an image-kind-only query path, so this is not just toggling existing markup; it needs a role-aware merge of image artifacts plus generated-video sidecar roles.

**Dependencies:** Tier 1A's role contract. Vacuous in practice until something writes the frame blobs (Tier 2 or Tier 3 produces them).

### Tier 2 — Provider poster ingestion (audit-gated)

**Scope:** If the Veo provider response carries a poster URL or thumbnail asset, download it during the success path and store it on the `generated_video` artifact under `role: poster`. After this lands, every newly-generated video has a non-stub gallery thumbnail.

**Critical audit before scoping:** Read [`VeoClient.cs`](../../src/Rook/Services/Vision/Video/VeoClient.cs), the relevant section of `VideoJobManager.cs` (around line 747 where `generated_video` is created), and one raw completed Veo operation payload to verify whether Veo actually returns a poster URL. **My memory said yes (carry-over from SA_Banana); Codex correctly flagged this as unverified.** As of the 2026-04-26 Codex review, current public Google docs describe generated output as a video URI / GCS URI / base64 video bytes and describe first/last frames as inputs, not poster outputs. Treat poster output as unproven until a live payload says otherwise.

**Three branches from the audit:**
1. **Veo returns a poster URL we currently discard.** ~5-line ingest add in the manager's success path; can fold into Tier 1A's PR if scope stays small, or ship as Tier 1.5 standalone.
2. **Veo returns a poster URL, but the provider interface cannot carry it.** Extend `ProviderFetchResult` into a media-collection result, then update the manager to store `video` plus optional sidecars. This is still straightforward, but it is not a 5-line manager patch.
3. **Veo returns no poster.** Tier 2 becomes "extract first-frame from the MP4 to use as poster" — which is Tier 3 territory (media decoding). Tier 2 is then deferred or merged into Tier 3.
4. **Veo returns multiple representative frames.** Bonus contract: poster + sample timeline frames could be ingested with separate roles. Probably out of scope for v1.

**Cost:** Conditional. Small if the current provider can expose a poster without interface churn; provider-contract-extension level if a media-collection result is needed; ffmpeg/WMF level if extraction is required.

**Dependencies:** Tier 1A's role contract (so the ingested poster has somewhere to land).

### Tier 3 — Arbitrary frame extraction (ffmpeg vs. WMF)

**Scope:** On video job completion, extract `start_frame` (exact first frame) and `end_frame` (exact last frame) and store them as sidecar blobs on the `generated_video` artifact. Optionally extract additional `poster` if Tier 2 didn't already produce one, picking either the first frame or a representative middle frame.

**The substantive decision:** ffmpeg vs. Windows Media Foundation.
- **ffmpeg pros:** cross-platform, handles every codec, deterministic per-frame seeking, well-known idiom (`-ss <time> -frames:v 1`). **Cons:** ~20 MB binary footprint to bundle (or detect on PATH); separate process spawn; license is LGPL/GPL depending on build.
- **WMF pros:** Windows-native, no extra binary, in-process. **Cons:** Windows-only (we're already Windows-only via Rhino), per-codec quirks, more code to write, uncertain frame-accurate seeking with H.264 IDR-frame layouts.
- **Hybrid:** Detect ffmpeg on PATH first, fall back to bundled minimal build, fall back to WMF if neither.

**Why this is its own scope pass:** Adds media tooling, adds a binary dependency decision, touches backend artifact creation for every new video, has determinism and codec implications. Cannot be folded into a UI polish PR.

**Dependencies:** Tier 1A's role contract. Independent of Tier 2 (extraction can produce the poster frame too).

### Tier 4 (out of scope here, named for completeness) — GH plugin

The original NLE doc's Phase 1–4: tokens, render sink, twelve-component palette, editing experience. Built on top of the Tier 3 substrate. Separate plugin (`SA_Banana.GH.gha` per the original doc, probably renamed to `Rook.GH.Vision.gha` in light of the SA_Banana → Rook lift). Cost gating, dry-run, content-hash caching all live here. Not addressed in this design pass.

---

## Mapping to the original NLE doc's token model

Every token field in the April 9 sketch resolves to a Rook artifact reference under this scheme:

| NLE token field | Rook materialization |
|---|---|
| `VideoClip.Id` | Deterministic graph/content hash in the GH layer; resolves to an artifact id after materialization |
| `VideoClip.MediaPath` | `ArtifactStore.GetBlobAbsolutePath(id, "video")` |
| `VideoClip.Meta.poster` | `{artifact_id: materializedArtifactId, role: "poster"}` (Tier 2 or Tier 3 produces this) |
| `VideoFrame.Id` | Deterministic frame-token id, or direct artifact-role ref for already-materialized media |
| `VideoFrame.ImagePath` | `ArtifactStore.GetBlobAbsolutePath(artifactId, role)` where role is `image` / `start_frame` / `end_frame` / `poster` |
| `VideoClip.Upstream` | `parent_ids` on the artifact (the V2/V3 lineage chain that already exists) |

The NLE's content-hash key `(operator + parameters + upstream hashes)` maps onto the artifact store only after a cache lookup. Today the artifact store is UUID-addressed and non-deduplicating: `ArtifactStore.Create` mints a fresh GUID for every materialization. `parent_ids` chain provenance, but they do not create deterministic identity. So when Tier 4 lands, `VideoClip.Id` should remain a graph/content hash owned by the GH layer, and the Render sink needs a cache index from `clip_hash -> artifact_id` (or equivalent metadata lookup) before deciding whether to submit a new provider job.

This is the architectural payoff of doing Tier 1A first: **the NLE token model is the artifact contract, expressed twice.** The April 9 sketch invented `VideoClip` because there was nothing else available; today the artifact store can carry the same media roles and lineage, while the GH layer supplies the deterministic cache key that the store intentionally does not own yet. Tier 4 is then a presentation/cache layer over Tier 1A's contract, not a parallel media system.

---

## Open questions / audits needed

These are the things we *don't know* well enough to scope past this draft.

1. **Does Veo's provider response carry a poster URL?** (Tier 2 audit, blocks Tier 2 scope decision.)
2. **What is the cleanest picker UI for video sidecar roles?** Today the picker is image-kind-only. Tier 1B needs a role-aware listing that can show generated-video artifacts only when they carry `start_frame` / `end_frame` image sidecars.
3. **What's the right `end_frame` semantic for the NLE workflow?** Strictly the last frame of the MP4? Last keyframe? A configurable "near-last" that handles fade-out? (Tier 3 design.)
4. **Should `poster` be auto-derived from `start_frame` when `start_frame` exists?** Probably no — poster is "what looks good in a thumbnail," start_frame is "what reproduces this clip's opening." Conflating them constrains the editorial choice.
5. **Cost of Tier 3 extraction at scale.** ffmpeg first-frame extraction is milliseconds; last-frame requires a full decode pass on poorly-keyframed inputs. Worst-case time on a representative Veo clip should be measured before Tier 3 ships.
6. **Should Tier 1B's "use end_frame as start_frame" affordance be in the modal UI or only in the picker?** (Tier 1B UX.)
7. **Forward-compat with multi-clip Veo Interp.** When Interp eventually returns multiple variants, do they each get their own artifact with separate roles, or do they share an artifact with `variant_0_video`, `variant_1_video`, etc.? Affects role naming.
8. **How should GH discover the active RookNative port?** MCP already has instance discovery; a `.gha` running inside Rhino needs either a shared discovery helper, a native command/API, or a documented per-process instance file path.
9. **Where does the deterministic cache index live?** Options: artifact metadata (`graph_hash`), a separate `video_nle_cache.json`, or a future artifact-store index. This must be answered before Tier 4, because artifact ids are random GUIDs.
10. **Can Tier 3 preserve extract-before-publish under real performance constraints?** Provisional v0.3 decision: yes, prefer extracting sidecars before publishing the artifact so all roles become visible atomically. Reopen only if representative clips make that impractical.
11. **What is the exact MIME/extension policy for frame sidecars?** PNG is lossless and safe for provider inputs; JPEG is smaller. Start/end frames used as generation inputs probably want PNG unless provider limits force JPEG.
12. **How much provider raw response should be persisted?** A sanitized provider-output metadata snapshot would make future poster/sidecar audits easier, but raw response persistence can leak provider URLs, prompts, or policy metadata. Needs a redaction rule.

---

## Roadblocks

The things that could derail this if hit unprepared.

- **(a) Veo poster availability.** If Veo doesn't expose a poster, Tier 2 collapses into Tier 3 and the "easy first thumbnail win" goes away. Mitigation: audit early, before scope-passing Tier 2.
- **(b) ffmpeg licensing.** GPL-only ffmpeg builds would force Rook to ship under GPL too. Need an LGPL build, or use the system-installed binary, or use WMF. Mitigation: lock the bundling decision before Tier 3.
- **(c) Artifact-store schema rigidity.** If adding new file roles requires a schema migration (it shouldn't — roles are just keys in `files[]`), Tier 3 has more weight than expected. Mitigation: verify during Tier 1A scope.
- **(d) GH async-component lifetime.** The April 9 doc flagged this as a known risk. The Tier 4 plugin will need to handle Rhino reload, Grasshopper recompute storms, and the canonical "spinning indicator on the sink for minutes" UX. Mitigation: copy the Hops async pattern.
- **(e) Cost exposure.** A 5-clip GH graph at 4K is real money. The pre-cook estimator from Tier 4 is non-optional. Mitigation: gate the Tier 4 first-PR on having dry-run + cost estimation in the Render sink.
- **(f) Determinism.** Veo without a seed is non-deterministic; the content-hash cache only hits on byte-identical requests. Mitigation: surface seed in the Tier 4 components, default to a stable seed-per-component-guid if user doesn't specify.
- **(g) Append-after-create pressure.** Exact `start_frame` / `end_frame` extraction happens after MP4 download, while the current artifact store wants all blobs at create time. Mitigation: v0.3 prefers extracting before publishing the artifact; scope an explicit `AppendBlob`/`ReplaceArtifactWithSidecars` API only if extract-before-publish fails under measurement.
- **(h) GH transport discovery.** The old NLE doc assumed SA_Banana's fixed localhost server. Post-V4, the correct surface is RookNative's discovered HTTP instance. Mitigation: make port discovery a Tier 4 spike, and reuse existing MCP instance discovery semantics so multi-Rhino sessions do not accidentally submit jobs to the wrong document.
- **(i) Cache correctness.** `parent_ids` prove lineage after materialization; they do not prevent duplicate expensive generations. Mitigation: put a deterministic graph hash in the GH token and require the Render sink to do an estimate/cache dry run before any submit.

---

## Edges to explore

These are the interesting "what if" angles worth poking at before locking the design.

- **Symmetric concept artifacts.** If `generated_image` artifacts gained a `start_frame` role, an image could feed directly into an I2V job without a wrapper. The contract is already shaped to allow this.
- **Frame-as-artifact promotion.** When a user picks "use end_frame as start_frame," should the system mint a new `image` artifact from the role blob, or pass the role-ref through directly? The latter is cheaper but loses lineage clarity. The former adds an artifact per pick. Probably defer until usage tells us.
- **Multi-clip chains visualized in the gallery.** If clip B has clip A in its `parent_ids` because B's `start_frame` came from A's `end_frame`, the gallery could visualize the chain. Forward compat for an NLE timeline view.
- **Provider-frame vs. extracted-frame distinction.** A Veo-provided poster might be cropped or selected; an extracted first-frame is exact. Should we record provenance metadata? Probably yes, in `metadata` not in role names.
- **Cache-as-substrate.** The April 9 doc's content-hash cache and Rook's artifact store could eventually merge if the store gains a deterministic hash index. Today the artifact store is the media/lineage substrate; the GH layer must still own graph-hash lookup.
- **Sidecar provenance metadata.** For each non-primary role, record `provenance.kind` such as `provider_poster`, `extracted_first_frame`, `extracted_last_frame`, or `user_promoted_frame`. The role answers "what can this blob be used for"; provenance answers "where did it come from."
- **Frame role compatibility by mode.** A generated video's `end_frame` can feed I2V start-frame input, and both `start_frame` / `end_frame` can feed Interp. A `poster` should be display-only by default unless the user explicitly promotes it to an image artifact or frame role.

---

## Paths to success

If the Veo audit produces a clean answer, the dominant success path is:

0. **Veo raw-payload audit** (non-product, low risk): capture one sanitized completed operation JSON and decide whether Tier 2 exists independently of Tier 3.
1. **Tier 1A** (1 small PR): role contract + gallery tests. Ships forward-compat substrate without pretending thumbnails exist yet.
2. **Tier 1B** (1 small UI PR): role-aware picker support for existing sidecar blobs. Vacuous until sidecars exist, but proves the artifact-ref shape.
3. **Tier 2** if Veo returns a poster (small-to-medium PR depending on provider result shape): newly-generated videos get gallery thumbnails. Visible user win.
4. **Tier 3** (own scope-pass cycle, 2–3 sessions): ffmpeg-vs-WMF decision, frame extraction lands, NLE substrate is complete.
5. **Tier 4 PoC** (one focused session per the original doc's §8): three-component `.gha` proves the dataflow model end-to-end with cached artifacts.
6. **Tier 4 full palette**: incremental, one or two components per PR.

Each tier ships independently and improves a real user flow. None depend on the next existing. If we stop after Tier 3, the video subsystem is feature-complete for non-NLE workflows. If we stop after Tier 1A, the contract is in place for any future implementer to fill in Tiers 2/3.

---

## What this doc is NOT trying to decide yet

- The Tier 4 GH plugin packaging (referenced in the April 9 doc as `SA_Banana.GH.gha`; needs renaming and re-scoping post-Rook-lift).
- The seed/determinism UX for the Tier 4 components.
- Final FFmpeg-vs-WMF decision and legal review. v0.3 records a provisional LGPL-bundled-FFmpeg posture only.
- Whether the existing artifact store's hashing is sufficient for the NLE cache or whether Tier 4 needs its own content-hash layer.
- A productized Veo payload-capture tool. The v0.3 audit can be one-off; only its sanitized findings matter.
- Multi-track timeline UI, color grading, audio — explicitly deferred per the April 9 doc.

---

## Iteration log

- **v0.1 (2026-04-26):** Initial draft. Captures the 2026-04-26 discussion thread between Claude and Codex post-V4-merge. Establishes the four-tier framing (1A / 1B / 2 / 3) plus the deferred Tier 4 GH plugin from the April 9 doc. Open for review.
- **v0.2 (2026-04-26):** Codex review pass. Added implementation corrections: current picker is image-kind-only; current provider fetch result carries one payload; public Veo docs do not prove poster output; artifact ids are UUIDs, not deterministic content hashes. Split Tier 1A (contract/gallery tests) from Tier 1B (role-aware picker), added GH port-discovery and cache-index questions, and tightened Tier 2 around raw-provider-response audit.
- **v0.3 (2026-04-26):** Claude/Codex convergence pass. Promoted two pre-scope decisions: Tier 3 should prefer extract-before-publish to preserve ArtifactStore atomicity, and Tier 2 must start with a sanitized raw Veo operation payload audit before any provider-poster implementation is scoped. Added provisional FFmpeg dependency posture: prefer bundled LGPL-only executable, keep it replaceable/configurable, and avoid requiring user-installed FFmpeg or a separate open-source GH NLE solely for licensing reasons.
- **v0.4 (2026-04-26):** Path-stability pass. Moved the `gh_sdk_extracted/` reference (126 MB) from the transient `Rook-private-archive/` location into the current Rook repo at `docs/gh_sdk_extracted/`, gitignored. The inventory item now references the stable in-repo path so future Tier 4 spikes don't depend on the archive directory's lifecycle. Mechanical change only — no architectural revisions.
