# RookVision Video — v3.1 Promoted Decisions

**Date:** 2026-04-22 (decisions captured) / 2026-04-25 (promoted)
**Status:** **Locked** — pre-implementation reference for the video slice
**Supersedes:** the open questions in §"Addendum: Video Generation (v3)" of [`2026-04-08-sa-banana-integration.md`](2026-04-08-sa-banana-integration.md)
**Related:**
- [`2026-04-22-codex-v3-video-answers.md`](2026-04-22-codex-v3-video-answers.md) — full Codex rationale, retained verbatim
- [`2026-04-09-grasshopper-video-nle.md`](2026-04-09-grasshopper-video-nle.md) — GH/NLE proposal (downstream consumer of these decisions)
- [`2026-04-22-rookvision-image-track-checkpoint.md`](2026-04-22-rookvision-image-track-checkpoint.md) — image track context where the four questions were drafted

---

## TL;DR

The v3 video addendum posed seven questions and four open architectural choices. Codex answered four of them on 2026-04-22; a follow-up review pass on 2026-04-25 confirmed the answers, agreed on the placement, and added one amendment that removes an ABI bump from the critical path. This doc pins the resulting five-decision contract so the video slice can be planned without re-litigating.

The non-obvious bit: **the same job contract serves both the RookVision tab and the future GH NLE**, but they reach it through different transports (Pattern A bridge for the tab; native HTTP for GH `.gha` components). The contract is the seed; everything else is plumbing.

---

## The five locked decisions

### D1 — Video transport for the tab: `A+disk-sideband`

The control plane stays on the existing Pattern A bridge (PR #93). Large video bytes flow through `ArtifactStore` (PR #92), not the bridge.

**Why:** smallest new review surface that does not repaint video as a WebView-only feature; no new chat-server dependency; the same artifact IDs survive the eventual GH/NLE contract handoff. Pattern B for video was rejected as a violation of the architecture's "companion off the public HTTP path" posture ([`CURRENT_ARCHITECTURE.md:22, :26`](../Rook/docs/CURRENT_ARCHITECTURE.md), [`RookWebSurface.cs:108`](../Rook/src/Rook/UI/Web/RookWebSurface.cs#L108)).

**Fallback:** `A async-in-C#` if the sideband artifact lifecycle cannot be locked in time. Do not reintroduce Pattern B in v1.

### D2 — Artifact shape: keep the Phase 1 hedge as the v1 contract

Current `ArtifactStore` already provides stable identity, immutable finalized artifacts, `files[]`, `parent_ids`, `metadata`, and `flags` ([`ArtifactStore.cs:28, :39, :351, :472`](../Rook/src/Rook/Artifacts/ArtifactStore.cs), [`Artifact.cs:8`](../Rook/src/Rook/Artifacts/Artifact.cs)). Video uses it as-is — the primary mp4 plus poster/start/end frames live under one artifact's `files[]`, with `parent_ids` chaining to source captures.

Harden only when video produces outputs that are independently consumable and no longer share one lifecycle. Multi-blob first; linked artifacts only when retry/retain semantics actually diverge.

**Submit-time constraint (D2.1):** the `submit` route MUST NOT accept inline base64 media. SA_Banana's request shape (`StartImageBase64`, `EndImageBase64`, `ReferenceImagesBase64`) does not cross the bridge or the HTTP boundary. Submit accepts **artifact_ids** or **narrowly-validated path refs only**; the domain layer resolves bytes internally. This keeps submit/status calls under the 1 MB bridge response buffer and prevents large-payload abuse on the public HTTP surface.

### D3 — GH/NLE access path: native-owned job contract on RookNative HTTP

GH `.gha` components cannot use the WebView JS bridge — they are not in a WebView. The chat server is the wrong dependency (operational + auth posture mismatch). RookNative HTTP is the only stable public surface today ([`CURRENT_ARCHITECTURE.md:34, :93`](../Rook/docs/CURRENT_ARCHITECTURE.md)).

The semantic contract — both adapters (tab via bridge, GH via HTTP) call into the same `IVideoJobManager`:

```
submit(input_artifact_ids | path_refs, options) -> { job_id, state }

status(job_id) -> {
  job_id, state,
  progress: { pct?, stage?, message? },
  result_artifact_id?,
  error?
}

cancel(job_id) -> { job_id, state }

result(job_id) -> {
  job_id, state,
  result_artifact_id,
  files[]
}
```

**Pinned native route paths** (REST-shaped, collection + sub-resources):

| Verb | Path | Maps to |
|------|------|---------|
| `POST` | `/vision/video/jobs` | `submit` |
| `GET`  | `/vision/video/jobs/{job_id}` | `status` |
| `POST` | `/vision/video/jobs/{job_id}/cancel` | `cancel` |
| `GET`  | `/vision/video/jobs/{job_id}/result` | `result` |
| `POST` | `/vision/video/estimate` | dry-run cost estimation (first-class — both tab gating and GH dry-run consume it) |

The bridge ops mirror these: `submit_video_job`, `get_video_job`, `cancel_video_job`, `get_video_job_result`, `estimate_video_job`. One handler per op in `VisionHandler.cs`'s allowlist; native dispatch shape (body / path-id / query) chosen per route.

**Typed error codes**, each with a `retryable` flag: `invalid_request`, `unsupported_media`, `dependency_unavailable`, `execution_failed`, `cancelled`, `interrupted`. Transport errors stay transport errors and must not leak the bridge's generic `"unknown method"` / `"handler failed"` envelopes ([`BridgeDispatcher.cs:17, :21, :114, :126`](../Rook/src/Rook/UI/Web/BridgeDispatcher.cs)) into GH consumer code.

### D4 — Job state: hybrid (in-memory active + on-disk ledger)

Active execution state lives in memory. Identity and terminal/interrupted outcomes persist through a **separate `VideoJobLedger`** under the Rook data root (e.g. `%APPDATA%\Rook\video\job-ledger.jsonl`), **not** through `ArtifactStore`. The artifact store is built for finalized immutable artifacts and rejects empty `blobs` at `Create` time ([`ArtifactStore.cs:611-615`](../Rook/src/Rook/Artifacts/ArtifactStore.cs#L611-L615)) — interrupted jobs have no MP4/poster blob and would have nothing to write.

**`VideoJobLedger` record shape (v1):**

```jsonc
{
  "job_id": "uuid",
  "state": "queued|submitting|polling|downloading|saving|complete|error|cancelled|interrupted",
  "request_summary": { "model": "...", "mode": "t2v", "duration_s": 8, ... },
  "result_artifact_id": "uuid | null",
  "error": { "code": "execution_failed", "message": "...", "retryable": true } | null,
  "created_at": "iso8601",
  "updated_at": "iso8601"
}
```

Ledger is append-only JSONL with periodic compaction (out of v1 scope; size bound is small). Single-writer is the in-process `VideoJobManager`; readers (status route, MCP tools) read the latest record per `job_id`.

**Restart semantics:** plugin reload mid-job — the ledger holds the most recent pre-shutdown state; on next status poll, the manager observes no in-memory entry and emits `interrupted` (overwriting the prior in-flight state in the ledger). Not `resume` (machinery cost too high for v1), not silent `drop` (breaks poll/fetch).

When a job completes successfully, the result artifact is written to `ArtifactStore` first, then the ledger transitions to `complete` with `result_artifact_id` set. Order matters: artifact-first means `result(job_id)` never returns a missing artifact_id.

### D5 — ABI v14 reuse for native video routes (post-Codex amendment)

The native trampoline already supports body-only, path-id, and query-param dispatch through the existing `vision_dispatch` callback ([`VisionHandler.cpp:117-156`](../Rook/src/RookNative/Handlers/VisionHandler.cpp#L117-L156)). The C# side is op-discriminated with an explicit allowlist ([`VisionHandler.cs:69-88`](../Rook/src/Rook/Handlers/VisionHandler.cs#L69-L88)). Submit/poll/cancel/fetchResult all return small JSON envelopes well under the 1 MB response buffer and do not run the 6-minute Veo job inside the bridge call.

**Therefore:** new `/vision/video/*` routes forward new op names through the existing `vision_dispatch` seam; new ops are added to the C# allowlist and dispatched to a new `VideoOpHandler`. **No ABI v15 unless a pre-implementation spike proves it.**

---

## What this contract seeds for GH NLE

Four things video-in-tab v1 owes to GH NLE later, all preserved by D1–D5:

1. **D3's `submit/status/cancel/result` is the lingua franca.** Tab v1 calls it through the JS bridge; GH `.gha` calls it through native HTTP. Same domain, same job manager, same artifact contract, same error codes.
2. **D2's artifact metadata is rich enough to back a future `VideoClip` GH token** — a token is just `{ artifact_id, parent_ids, metadata }`. `parent_ids` already chains to source captures.
3. **Cost split is locked: estimation in domain, gating UX in adapter.** The cost estimator (input request → dollar amount, given the capability matrix) lives in `Services/Vision/Video/`. The "$3.20 — proceed?" modal/inline-warning is a UI concern owned by VisionTab today and a future GH dry-run sink later. Both consumers call the same estimator.
4. **`VideoJobLedger` is the cross-consumer state store.** Tab status polls and a future GH `Render` sink's poll loop both read the same ledger record by `job_id`. No second source of truth.

Explicitly **not** seeded by v1 (deferred to GH NLE phase): ffmpeg integration, content-hash-as-identity (see §"Sensitivities" below), async-component patterns, multi-track UI, content-hash cache lookups.

---

## What did NOT change

The v2.2 image-track architecture is intact. Pattern A for image generation, three-layer adapter discipline, parity rule, artifact-as-currency — all unchanged. Video is additive: it lands inside `Services/Vision/Video/`, behind the same `VisionHandler.cs` op dispatcher, returning the same artifact shape.

---

## Open questions retired vs deferred

Of the seven questions posed in v3:

| # | Question | Disposition |
|---|----------|-------------|
| 1 | Pattern A vs B for video | **Retired** — D1 (`A+disk-sideband`) |
| 2 | C#-to-Python port cost justified? | **Retired** — implied no by D1; provider clients stay in C# for v1 |
| 3 | GH NLE access path | **Retired** — D3 (native HTTP) |
| 4 | Multi-blob vs linked artifacts | **Retired** — D2 (multi-blob first; linked when lifecycle splits) |
| 5 | Job state: in-memory, on-disk, both | **Retired** — D4 (hybrid) |
| 6 | Cost estimation: domain or adapter? | **Retired** — split locked: estimation = domain, confirmation/gating UX = adapter/UI (see §"What this contract seeds for GH NLE", item 3) |
| 7 | LiteLLM timeline | **Deferred** — provider clients stay in C# for v1; LiteLLM revisit is v2 work, unaffected by these decisions |

---

## Sensitivities — what would reopen each decision

- **D1 reopens** if bridge polling for `status(job_id)` cannot meet UX needs (jitter, perceived latency on long jobs), or if `submit`/`status` calls cannot stay small and fast enough to fit the 1 MB / 180 s envelope without splitting. (Push-from-C#-to-JS is **not** required for v1 — JS-side polling on a 1–2 s timer is consistent with `A+disk-sideband` and avoids bidirectional bridge complexity.)
- **D2 reopens** the moment one job produces outputs with independent retain/retry/refetch semantics — promote to linked artifacts. **D2.1 (no inline base64) is non-negotiable** — reopening it means re-thinking the auth/payload posture, not just the artifact shape.
- **D3 reopens** if the native HTTP routes cannot ship in the v1 slice — fallback is a companion `IVideoJobs` façade with the **same contract**, mirrored to native HTTP later. Consumers always code to the contract, never the transport.
- **D4 reopens** when "interrupted" turns out to be too coarse for real workflows — promote to `resume` with checkpointed state. The `VideoJobLedger` shape is sufficient for `interrupted` today and is the seam where checkpoint fields would land.
- **D5 reopens** only if a pre-impl spike finds the bridge timeout, response buffer, or callback shape inadequate for any of the five video ops. Until that spike, ABI v14 stands.

---

## Next steps — implementation roadmap

**PR-0 — Doc promotion (one shot, after this tightening pass merges):**
- Short v3.1 pointer section in [`2026-04-08-sa-banana-integration.md`](2026-04-08-sa-banana-integration.md) directing readers here. No content duplication.
- Update [`2026-04-22-rookvision-image-track-checkpoint.md`](2026-04-22-rookvision-image-track-checkpoint.md) to mark the four v3 questions as **answered** with pointers here.

**PR-V1a — Domain contracts only:**
- `Services/Vision/Video/`: request DTOs (artifact_id-based, no base64 transport per D2.1), state/error envelopes, `VideoCapabilities` lift from SA_Banana, cost estimator interface + Veo-pricing implementation.
- Tests covering: cost-estimator math (including fail-closed on unknown models), capability-matrix validation, error-code retryable matrix, media-ref kind/role validation. Fake provider lives under `src/Rook.Tests/` as a test helper, not production source.
- No HTTP, no real Veo calls, no UI, no `VideoJobManager` yet.

**PR-V1b — Real provider + manager + ledger:**
- `VeoClient` (lifted/adapted from SA_Banana), `VideoJobManager` (in-memory state, wired to Rook companion lifecycle/shutdown cancellation; Rhino-touching work stays outside the provider loop and uses existing UI-thread dispatch paths where needed), `VideoJobLedger` (append-only JSONL under Rook data root).
- Terminal `ArtifactStore` writing on success; `interrupted` reconciliation on plugin reload.
- Tested with fake HTTP/provider paths and a real-API integration smoke gated behind a env-var.

**PR-V2 — Native + bridge transport:**
- C++ routes for the five paths in D3 forwarding through existing `vision_dispatch` (ABI v14, no bump per D5).
- C# allowlist extension in `VisionHandler.cs` plus the five op handlers.
- Tab uses these via existing Pattern A bridge; GH consumers reach them via native HTTP. Same contract, two transports.

**PR-V3 / PR-V4 — UI + MCP parity (parallel after PR-V2):**
- PR-V3: VisionTab UI for video — generation form, queue panel, status polling on 1–2 s timer, gallery integration, cost-confirmation modal consuming the domain estimator.
- PR-V4: MCP tools (`rhino_render_video`, `rhino_video_jobs`, `rhino_video_status`, `rhino_video_cancel`) + tool-catalog wiring per the parity rule.

**First GH NLE PR (post-PR-V2):**
- Three GH components — `Prompt → Clip`, `Render`, and one Chirp consumer (e.g. `Chirp Interpreter → Prompt`) — proving the Chirp↔Vision composition lane against the same native HTTP contract. Not bundled with tab v1.
