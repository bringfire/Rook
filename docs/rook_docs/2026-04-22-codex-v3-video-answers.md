# Codex v3 Video Addendum — Answers

**Date:** 2026-04-22
**Source:** `codex exec` session `019db7b5-29b2-77f3-8879-473a7d1f6631` (gpt-5.4, reasoning effort high)
**Status:** Answers captured. **Not yet pinned into the master plan** (`2026-04-08-sa-banana-integration.md`) — awaiting review. Do not code against these until promoted.

## Context

The four v3 video questions from the RookVision image-track checkpoint
(`2026-04-22-rookvision-image-track-checkpoint.md`) were sent to Codex as
parallel async work during the PR-4 pre-code phase. Cover instruction
required flat numbered sections, one recommendation + one fallback per
question, and explicit rejection rationale for the other options.

**Caveat on grounding:** Codex ran from `C:\Users\aryan\source\repos\Rook`
and could not locate the two anchor docs because `rook_docs/` is a sibling
directory, not inside the Rook repo. Codex's answers are therefore
grounded in the prompt context plus direct reads of shipped code
([RookWebSurface.cs](../Rook/src/Rook/UI/Web/RookWebSurface.cs),
[BridgeDispatcher.cs](../Rook/src/Rook/UI/Web/BridgeDispatcher.cs),
[ArtifactStore.cs](../Rook/src/Rook/Artifacts/ArtifactStore.cs),
[CURRENT_ARCHITECTURE.md](../Rook/docs/CURRENT_ARCHITECTURE.md)), not
direct reads of the master plan or the addendum options.

---

## 1. Video transport (v1)

**Recommendation: `A+disk-sideband`.** Keep the control plane on the
shipped Pattern A bridge (PR #93) and move large video inputs/results
through the artifact store (PR #92). Smallest new review surface that
avoids repainting video as a WebView-only feature. No new chat-server
dependency, no second transport to debug, and the same artifact IDs/results
can later sit behind the GH/NLE contract.

Why the other three lose now:
- **`A async-in-C#`** keeps video payload semantics bridge-local and
  raises later rewrite cost once GH/NLE arrive.
- **`A+B hybrid`** adds both bridge and HTTP failure modes immediately.
- **`full B`** violates the live architecture's explicit "companion off
  the public HTTP path; chat server is a separate operational dependency"
  posture (`CURRENT_ARCHITECTURE.md:22`, `:26`, `RookWebSurface.cs:108`,
  `ChatServiceManager.cs:903`).

**Fallback:** `A async-in-C#` if the sideband artifact lifecycle cannot
be locked in time. Still do not reintroduce `B` in v1.

---

## 2. Artifact shape

**Recommendation: yes, the Phase 1 hedge is sufficient as the locked v1
contract.** Current store already gives stable identity, immutable
finalized artifacts, `files[]`, `parent_ids`, `metadata`, and `flags`
without overcommitting to a video-specific shape (`ArtifactStore.cs:28`,
`:39`, `:351`, `:472`, `Artifact.cs:8`).

Harden only when video produces outputs that are independently consumable
and no longer share one lifecycle:
- **Multi-blob under one artifact id** — when one job still yields one
  logical result bundle.
- **Linked artifacts** — when outputs must be separately retried,
  retained, reused downstream, or completed on different timelines.

**Fallback:** if early hardening is forced, choose multi-blob first;
linked artifacts should wait for the first real lifecycle split.

---

## 3. GH/NLE access path

**Recommendation: a native-owned job contract**, not JS bridge method
names and not chat-server routes — because RookNative is the only public
HTTP surface today (`CURRENT_ARCHITECTURE.md:34`, `:93`).

Contract consumers should write against:

```
submit(input_artifact_id | input_path_ref, options) -> { job_id, state }

poll(job_id) -> {
  job_id, state,
  progress: { pct?, stage?, message? },
  result_artifact_id?,
  error?
}

cancel(job_id) -> { job_id, state }

fetchResult(job_id) -> {
  job_id, state,
  result_artifact_id,
  files[]
}
```

Error semantics — typed job-layer codes, each with `retryable`:
- `invalid_request`
- `unsupported_media`
- `dependency_unavailable`
- `execution_failed`
- `cancelled`
- `interrupted`

Transport errors stay transport errors. They must **not** leak the
WebView bridge's generic `"unknown method"` / `"handler failed"`
substrate contract into GH/NLE (`BridgeDispatcher.cs:17`, `:21`, `:114`,
`:126`).

**Fallback:** if native HTTP cannot land in the first video slice,
define exactly this schema behind a companion `IVideoJobs` façade and
mirror it 1:1 later. Consumers should still code to the job schema, not
the bridge transport.

---

## 4. Video job state (v1)

**Recommendation: `hybrid` state.** Keep active execution state
in-memory, but persist enough on disk to preserve job identity and
terminal/interrupted outcomes through the artifact store boundary. Best
v1 cost/resilience trade.

- **"On-disk via artifact store" alone is wrong:** the artifact store is
  built for finalized immutable artifacts, not as a live mutable
  scheduler store (`.tmp` commit, no index, single-writer assumption —
  `ArtifactStore.cs:21`, `:39`, `:43`, `:132`).
- **"In-memory only" is cheaper** but gives bad restart semantics.

**Restart semantics: on plugin reload mid-job, v1 should surface
`interrupted`.** Not `resume` (too much machinery for v1), not silent
`drop` (breaks poll/fetch semantics for GH/NLE).

**Fallback:** if even interrupted tombstones are too much for the slice,
use in-memory only and explicitly drop on reload — but keep the public
state enum ready for `interrupted` so consumers do not need a rewrite
later.

---

## Next actions (not yet taken)

1. Review these answers against the master plan and the v3 addendum.
2. Promote accepted decisions into `2026-04-08-sa-banana-integration.md`
   under a v3.1 section (or create a dedicated `2026-04-22-v3-video-
   decisions.md` if the master plan is getting unwieldy).
3. Update the RookVision checkpoint to mark the four questions as
   **answered** with pointers to the promoted decisions.
4. None of this blocks PR-4 through PR-7 (image track). Video slice work
   begins only after image track lands.
