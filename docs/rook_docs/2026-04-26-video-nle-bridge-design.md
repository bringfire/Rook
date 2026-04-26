# Video NLE Bridge Design

**Date:** 2026-04-26
**Status:** Draft v0.1 — open for iteration
**Related:**
- [`2026-04-09-grasshopper-video-nle.md`](2026-04-09-grasshopper-video-nle.md) — the original NLE vision (token model, four phases, twelve-component palette). Read first; this doc bridges that vision to the realization steps that became plausible after V4 shipped.
- [`2026-04-22-v3-video-decisions.md`](2026-04-22-v3-video-decisions.md) — v3.1 locked video contract. Wire shapes are frozen; this design must compose with them, not amend them.
- PR #116 (V4 closeout, merged 2026-04-26) — the parity-rule restore that made the NLE substrate observable from native HTTP, MCP, and the bridge through one contract.

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
- **Submit-time media refs** accept `{kind: "artifact_id", artifact_id, role}` per V2 D2.1. The submit-side schema permits referencing *any* video artifact's *any* role as input to a new video job. Today there's nothing to reference because the manager doesn't write extra roles.
- **The full NLE design doc has not been implemented.** No `.gha` plugin exists. No `VideoClip` / `VideoFrame` tokens exist in the codebase.

**The gap, stated precisely:** the contract supports addressable per-role media references on video artifacts; the runtime never produces them; the UI is ready to consume `poster` if it appears; nothing yet consumes `start_frame` or `end_frame`.

---

## Tier breakdown

The user's instinct on 2026-04-26 was "Tier 1 video gallery thumbnails." Codex (correctly) split that into multiple tiers because two different contracts were being collapsed. The split below is the working scope.

### Tier 1A — Role contract + UI consumption (no extraction)

**Scope:** Formalize `poster` / `start_frame` / `end_frame` as first-class optional roles on `generated_video` artifacts. Make the gallery, video-frame-picker, and modal display them when present, gracefully no-op when absent. Add picker affordances ("Use end frame as start frame") that surface only when the artifact actually carries those roles. Tests pin the role-preference matrix and picker behavior. **No extraction. No provider contract change. No backend mutation.**

**Why this ships first:** The contract is the thing that's load-bearing. Once roles are first-class, anything downstream — provider ingestion, frame extraction, NLE component thumbnails — has a stable API to write into. Tier 1A is also the cheapest forward-compatibility move available; it ships even if no role-bearing artifact ever appears, because the UI is contract-driven.

**Cost:** Small UI PR. ~30 min if the gallery code is the right shape; longer if the picker affordances need new modes. Closer audit needed during scope pass.

**Dependencies:** None. Composes with V4.

**Branch name proposal:** `fix/rook-vision-video-frame-roles`.

### Tier 1B — Artifact-level frame reuse

**Scope:** When a video artifact carries `start_frame` or `end_frame` blobs, surface picker actions like "use as start frame" / "use as end frame" that emit the existing `{kind: "artifact_id", artifact_id: "<video-uuid>", role: "end_frame"}` shape. The resolver already handles this; no schema change. UI must clearly distinguish "this frame came from a video artifact" from "this frame is its own image artifact."

**Why this is the bridge to the NLE token model:** The `VideoClip` token in the original NLE doc carries `Meta.poster`. The `VideoFrame` token carries an `ImagePath`. In the Rook materialization, both reduce to `{artifact_id, role}` references against the artifact store. Tier 1B is the UI exercise of that mapping — it proves the artifact-as-token shape works for users before any GH plugin is written.

**Cost:** Tiny if Tier 1A's picker affordance is generalized correctly. Could ship in the same PR as Tier 1A or as the immediate follow-up.

**Dependencies:** Tier 1A's role contract. Vacuous in practice until something writes the frame blobs (Tier 2 or Tier 3 produces them).

### Tier 2 — Provider poster ingestion (audit-gated)

**Scope:** If the Veo provider response carries a poster URL or thumbnail asset, download it during the success path and store it on the `generated_video` artifact under `role: poster`. After this lands, every newly-generated video has a non-stub gallery thumbnail.

**Critical audit before scoping:** Read [`VeoClient.cs`](../../src/Rook/Services/Vision/Video/VeoClient.cs) and the relevant section of `VideoJobManager.cs` (around line 747 where `generated_video` is created) to verify whether Veo actually returns a poster URL. **My memory said yes (carry-over from SA_Banana); Codex correctly flagged this as unverified.** This is the load-bearing question for whether Tier 2 is one PR or two.

**Three branches from the audit:**
1. **Veo returns a poster URL we currently discard.** ~5-line ingest add in the manager's success path; can fold into Tier 1A's PR if scope stays small, or ship as Tier 1.5 standalone.
2. **Veo returns no poster.** Tier 2 becomes "extract first-frame from the MP4 to use as poster" — which is Tier 3 territory (media decoding). Tier 2 is then deferred or merged into Tier 3.
3. **Veo returns multiple representative frames.** Bonus contract: poster + sample timeline frames could be ingested with separate roles. Probably out of scope for v1.

**Cost:** Conditional. Provider-contract-extension level if (1); ffmpeg/WMF level if (2).

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
| `VideoClip.Id` | `artifact_id` of a `generated_video` artifact |
| `VideoClip.MediaPath` | `ArtifactStore.GetBlobAbsolutePath(id, "video")` |
| `VideoClip.Meta.poster` | `{artifact_id: clip.Id, role: "poster"}` (Tier 2 produces this) |
| `VideoFrame.Id` | `artifact_id` of either an image artifact OR a video artifact's frame role |
| `VideoFrame.ImagePath` | `ArtifactStore.GetBlobAbsolutePath(id, role)` where role is `start_frame` / `end_frame` / `poster` |
| `VideoClip.Upstream` | `parent_ids` on the artifact (the V2/V3 lineage chain that already exists) |

The NLE's content-hash key `(operator + parameters + upstream hashes)` maps onto the existing artifact store's content-addressed structure — `parent_ids` already chain provenance. So when Tier 4 lands, `VideoClip.Id` doesn't need to be a separate hash; it can be the artifact's own GUID, deterministic by virtue of identical-input-identical-request hitting the existing artifact-store dedup or by virtue of explicit graph caching at the Render sink.

This is the architectural payoff of doing Tier 1A first: **the NLE token model is the artifact contract, expressed twice.** The April 9 sketch invented `VideoClip` because there was nothing else available; today the artifact carries the same fields under the same identity discipline. Tier 4 is then a presentation layer over Tier 1A's contract, not a parallel system.

---

## Open questions / audits needed

These are the things we *don't know* well enough to scope past this draft.

1. **Does Veo's provider response carry a poster URL?** (Tier 2 audit, blocks Tier 2 scope decision.)
2. **Does the gallery picker UI cleanly support per-role choice today, or does it assume one-blob-per-artifact?** (Tier 1A scope sizing.)
3. **What's the right `end_frame` semantic for the NLE workflow?** Strictly the last frame of the MP4? Last keyframe? A configurable "near-last" that handles fade-out? (Tier 3 design.)
4. **Should `poster` be auto-derived from `start_frame` when `start_frame` exists?** Probably no — poster is "what looks good in a thumbnail," start_frame is "what reproduces this clip's opening." Conflating them constrains the editorial choice.
5. **Cost of Tier 3 extraction at scale.** ffmpeg first-frame extraction is milliseconds; last-frame requires a full decode pass on poorly-keyframed inputs. Worst-case time on a representative Veo clip should be measured before Tier 3 ships.
6. **Should Tier 1B's "use end_frame as start_frame" affordance be in the modal UI or only in the picker?** (Tier 1B UX.)
7. **Forward-compat with multi-clip Veo Interp.** When Interp eventually returns multiple variants, do they each get their own artifact with separate roles, or do they share an artifact with `variant_0_video`, `variant_1_video`, etc.? Affects role naming.

---

## Roadblocks

The things that could derail this if hit unprepared.

- **(a) Veo poster availability.** If Veo doesn't expose a poster, Tier 2 collapses into Tier 3 and the "easy first thumbnail win" goes away. Mitigation: audit early, before scope-passing Tier 2.
- **(b) ffmpeg licensing.** GPL-only ffmpeg builds would force Rook to ship under GPL too. Need an LGPL build, or use the system-installed binary, or use WMF. Mitigation: lock the bundling decision before Tier 3.
- **(c) Artifact-store schema rigidity.** If adding new file roles requires a schema migration (it shouldn't — roles are just keys in `files[]`), Tier 3 has more weight than expected. Mitigation: verify during Tier 1A scope.
- **(d) GH async-component lifetime.** The April 9 doc flagged this as a known risk. The Tier 4 plugin will need to handle Rhino reload, Grasshopper recompute storms, and the canonical "spinning indicator on the sink for minutes" UX. Mitigation: copy the Hops async pattern.
- **(e) Cost exposure.** A 5-clip GH graph at 4K is real money. The pre-cook estimator from Tier 4 is non-optional. Mitigation: gate the Tier 4 first-PR on having dry-run + cost estimation in the Render sink.
- **(f) Determinism.** Veo without a seed is non-deterministic; the content-hash cache only hits on byte-identical requests. Mitigation: surface seed in the Tier 4 components, default to a stable seed-per-component-guid if user doesn't specify.

---

## Edges to explore

These are the interesting "what if" angles worth poking at before locking the design.

- **Symmetric concept artifacts.** If `generated_image` artifacts gained a `start_frame` role, an image could feed directly into an I2V job without a wrapper. The contract is already shaped to allow this.
- **Frame-as-artifact promotion.** When a user picks "use end_frame as start_frame," should the system mint a new `image` artifact from the role blob, or pass the role-ref through directly? The latter is cheaper but loses lineage clarity. The former adds an artifact per pick. Probably defer until usage tells us.
- **Multi-clip chains visualized in the gallery.** If clip B has clip A in its `parent_ids` because B's `start_frame` came from A's `end_frame`, the gallery could visualize the chain. Forward compat for an NLE timeline view.
- **Provider-frame vs. extracted-frame distinction.** A Veo-provided poster might be cropped or selected; an extracted first-frame is exact. Should we record provenance metadata? Probably yes, in `metadata` not in role names.
- **Cache-as-substrate.** The April 9 doc's content-hash cache and Rook's artifact store could merge entirely — the artifact store IS the cache, and the GH graph just walks the parent chain. This is the strongest version of the "artifact is the token" claim.

---

## Paths to success

If we ship Tier 1A in the next session and the Veo audit produces a clean answer, the dominant success path is:

1. **Tier 1A** (1 PR, 1–2 days): role contract + UI. Ships forward-compat substrate.
2. **Tier 2** if Veo returns a poster (small PR, same week as 1A): newly-generated videos get gallery thumbnails. Visible user win.
3. **Tier 3** (own scope-pass cycle, 2–3 sessions): ffmpeg-vs-WMF decision, frame extraction lands, NLE substrate is complete.
4. **Tier 4 PoC** (one focused session per the original doc's §8): three-component `.gha` proves the dataflow model end-to-end with cached artifacts.
5. **Tier 4 full palette**: incremental, one or two components per PR.

Each tier ships independently and improves a real user flow. None depend on the next existing. If we stop after Tier 3, the video subsystem is feature-complete for non-NLE workflows. If we stop after Tier 1A, the contract is in place for any future implementer to fill in Tiers 2/3.

---

## What this doc is NOT trying to decide yet

- The Tier 4 GH plugin packaging (referenced in the April 9 doc as `SA_Banana.GH.gha`; needs renaming and re-scoping post-Rook-lift).
- The seed/determinism UX for the Tier 4 components.
- ffmpeg bundling decision (Tier 3 scope-pass territory).
- Whether the existing artifact store's hashing is sufficient for the NLE cache or whether Tier 4 needs its own content-hash layer.
- Multi-track timeline UI, color grading, audio — explicitly deferred per the April 9 doc.

---

## Iteration log

- **v0.1 (2026-04-26):** Initial draft. Captures the 2026-04-26 discussion thread between Claude and Codex post-V4-merge. Establishes the four-tier framing (1A / 1B / 2 / 3) plus the deferred Tier 4 GH plugin from the April 9 doc. Open for review.
