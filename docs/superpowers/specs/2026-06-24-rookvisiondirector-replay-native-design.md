# RookVisionDirector Native Replay — Design (PR2 proper)

- **Status:** Draft for review
- **Date:** 2026-06-24
- **Feature:** RookVisionDirector arbitrary-motion replay — PR2 "native replay"
- **Branch:** `feature/rookvisiondirector-replay-native` (off `main`)
- **Predecessors:**
  - Pump spike (validated the guard): `docs/superpowers/specs/2026-06-24-rookvisiondirector-replay-pumpspike-design.md` — landed `DispatchDrainSuspension` on `main` (PR #342, merge `9e80359d`).
  - PR1 baked track (the payload replay consumes): `docs/superpowers/specs/2026-06-19-rookvisiondirector-arbitrary-motion-replay-design.md` (on branch `feature/rookvisiondirector-arbitrary-motion-replay`).

## Why this exists

PR2 lands **native live replay** of a baked animation track: a synchronous, guarded, cancellable playback of the track's per-frame object poses + camera directly in the Rhino viewport. It is a **display-only preview** — the product flow is **bake track → live replay/preview → accept → capture/export (separately)**. Capture already exists as its own validated path (`/director/frame-capture` / capture-from-track); replay does not duplicate it.

The pump spike already settled the load-bearing risk: a synchronous replay can hold the Rhino UI thread and bounded-pump the message loop **without** reentrantly draining the dispatcher, as long as the held pump runs under `DispatchDrainSuspension`. PR2 builds on that validated guard.

## Architecture facts this design rests on

1. **`/director/frame-capture` already does the per-frame work.** `HandleDirectorFrameCapture` applies a frame's `object_transforms[]` from source, sets the camera, captures to a file, and restores objects to source. Replay reuses the *apply / camera / restore* primitives and swaps the file capture for a **redraw + bounded-pump dwell**.
2. **The PR1 track is lossless to what native consumes.** A track frame's `object_transforms[]` entry (`object_id`, `source_state`, 4×4 `transform`) is exactly frame-capture's input shape — no adapter. `transform_semantics: "absolute_from_source"` means each frame is an **absolute pose from the object's source state**, restored after; playback is frame-order independent and drift-free.
3. **Replay holds the UI thread.** Because the replay loop runs inside a `Dispatch`ed lambda under a single `DispatchDrainSuspension` for its whole duration, (a) **only one replay can be active at a time**, (b) **no other operation can mutate the document mid-replay** (all HTTP→UI work is deferred until the loop ends), and (c) **cancel must be a pure worker-thread operation** — it cannot go through the blocked UI dispatcher.

## Scope

### In scope
- Native `POST /director/replay` (synchronous, guarded, single active replay).
- Native `POST /director/replay/cancel` (worker-thread cancel signal).
- Python MCP tools `rhino_director_replay` and `rhino_director_replay_cancel`.
- Extracted shared `DirectorFrame` per-frame primitives (behavior-preserving for frame-capture).
- The synchronous replay loop wrapping per-frame bounded pumping in `DispatchDrainSuspension`.
- Single active-slot cancellation with caller-provided `replay_session_id`.

### Out of scope (hard boundaries)
- **No capture/export during replay** — no PNG/frame file output, no output-directory parameter, no `capture` flag, no reuse of frame-capture's file-writing side. Replay may reuse the per-frame *application* logic only.
- `loop: true` behavior — **rejected**, not silently ignored (deferred).
- Per-frame timestamps; `frame_dwell_ms`.
- Client-disconnect / ESC-key cancellation detection.
- A session map / concurrent replays.
- A separate normalized `frames[]` input shape.
- Any broad director refactor or semantic change to `/director/frame-capture`.
- Any dependence on PR1's `animation_track.py` classes being present on `main`. Native consumes the track *JSON shape*; the Python tool forwards JSON without reshaping.

## Input contract — `POST /director/replay`

The request carries the **full baked track inline** plus replay controls:

```jsonc
{
  "replay_session_id": "<caller-provided id, e.g. uuid4 hex>",
  "track": { /* full baked animation_track.json content */ },
  "fps": 24,                  // optional override
  "restore_on_finish": true,  // optional, default true
  "loop": false               // optional, default false; true -> rejected
}
```

Native owns validation and replay normalization:
- validate the track envelope as **untrusted input**;
- require `transform_semantics == "absolute_from_source"`;
- validate frame counts and `frame_index` sequence consistency across `camera_frames` and `object_frames`;
- **zip/align `camera_frames[i]` + `object_frames[i]` natively** per frame;
- reuse the shared per-frame `object_transforms[]` / source-state validation;
- enforce payload / frame / object / duration / dwell caps natively;
- **ignore track fields irrelevant to live replay — explicitly `resolution` and `provenance`.**

There is exactly **one** input contract: the full track. No normalized `frames[]` shape.

**`replay_session_id` shape (pinned so native and Python tests agree):** a non-empty string, **≤128 chars**, composed only of safe printable token characters `[A-Za-z0-9._-]`. Anything else → `invalid_session_id`. The Python default remains `uuid4().hex` (which satisfies this rule). Both `/director/replay` and `/director/replay/cancel` apply the same rule.

**Object-count cap counting rule:** `object_count_exceeds_cap` (256) is measured as the count of **unique `object_id`s across the whole track** (i.e. `len(animated_object_ids)`). Because PR1's completeness rule makes every frame carry exactly that set, this also bounds any single frame; native may additionally reject any frame whose `object_transforms[]` length exceeds the cap, which follows naturally.

## Frame timing

FPS-driven dwell — faithful to the baked rate, no new timing model:

- `effective_fps = request.fps ?? track.fps ?? 24`; validate it is **finite and positive** (else `invalid_fps`).
- `dwell_ms = 1000 / effective_fps`.
- **Reject, do not clamp:**
  - if `dwell_ms > max_per_frame_dwell_ms` (250) → `frame_dwell_exceeds_cap` (silent clamping would change authored timing);
  - if `frame_count * dwell_ms > max_effective_replay_duration_ms` (60000) → `replay_duration_exceeds_cap`.
- The **entire replay loop runs under a single `DispatchDrainSuspension`** (constructed once at loop start, released on loop exit) — matching the spike's validated S2 pattern. This is load-bearing: it guarantees that no pump slice, at any frame, reentrantly drains the dispatcher, and that **no other HTTP→UI work interleaves between frames** to mutate the document mid-replay.
- Each frame: apply pose + set camera + redraw, then **hold `dwell_ms` as interruptible ~16ms pump slices** (each slice pumps the message loop for redraw/responsiveness and checks the cancel flag), then advance.
- Cancel is checked **before each frame and between pump slices**.
- `loop: true` → `unsupported_replay_option` (`{option: "loop"}`). `loop` omitted/false → proceed. Never silently ignored.

## Lifecycle & restore contract

Core invariant: **a preview must not mutate the document unless explicitly told to.** Native snapshots the pre-replay object xforms + camera and restores from that snapshot.

| Exit path | Objects | Camera | Returns |
|---|---|---|---|
| **Pre-flight validation failure** (worker- or UI-phase) | untouched (nothing applied) | untouched | error envelope (`code` + `message`) |
| **Success — completed** | `restore_on_finish:true` (default) → restored to pre-replay state; `false` → left at the final completed frame | same as objects | `{status:"completed", ...}` |
| **Cancel** | **always** restored to pre-replay state | **always** restored | `{status:"cancelled", cancelled:true, frames_played, restored:true}` |
| **Runtime apply failure** (post-validation, unexpected) | **always** restored | **always** restored | error with `frame_index` (+ `object_id` if attributable) |

- `restore_on_finish:false` applies **only to a clean, completed replay** (objects *and* camera left at the final frame). It never applies to validation failure, cancel, or runtime error — those always restore.
- **Camera restoration is part of the preview state, not a side effect** — stated explicitly because a live replay is a viewport preview.

### Snapshot timing / mutation boundary

The pre-replay snapshot (object xforms + camera) is taken **only after**:
1. worker-thread validation has succeeded, **and**
2. the replay slot has been reserved,

and it is taken **inside the UI-thread replay lambda, before the first frame is applied.** If UI-thread pre-apply validation (e.g. `object_not_found`) fails, **no frame is applied**, and the restore path is a safe no-op or restores exactly what was snapped (whichever the snapshot order makes natural). No partial mutation persists on any failure path; the active slot is released by RAII regardless.

## Cancellation & session semantics

- **Single active slot** (not a map): `{ mutex, active:bool, session_id:string, cancel:atomic<bool> }`. One UI-thread replay can exist at a time.
- **`POST /director/replay` (worker thread):** validate → **reserve the slot** under the mutex; if already `active` → reject `replay_already_active` *before any Dispatch* (a second replay must not queue behind the guard and tie up a worker for up to 60s) → Dispatch the replay lambda → loop checks `cancel` lock-free → **release the slot via RAII on every path** → return the terminal outcome.
- **`POST /director/replay/cancel` (pure worker thread, no Dispatch, no Rhino-doc API):**
  - matching active session → set `cancel` → `{cancel_requested:true, replay_session_id}`;
  - no active replay → `{cancel_requested:false, reason:"no_active_replay", replay_session_id}`;
  - session mismatch → `{cancel_requested:false, reason:"session_mismatch", replay_session_id}` (does **not** touch the other session's flag; **does not leak** the active session id).
- **Cancel is a signal, not the terminal outcome.** The original `/director/replay` response is the authoritative terminal result; cancel only *requests* cancellation. If cancel arrives after replay has completed and released the slot → `no_active_replay`.
- **Abandoned replay** (disconnect, no explicit cancel): deferred for v1; the **60s `max_effective_replay_duration` is the hard backstop** — any replay self-terminates within the cap, so a dropped client cannot wedge Rhino.

## Response & error schema

Standard Rook envelope `{success, data}` (`SendSuccess`→`success:true`/200; `SendErrorData`→`success:false`/400). **`status` discriminates success outcomes; `code` discriminates errors.**

**Success — completed** (`success:true`):
```jsonc
{ "status":"completed", "replay_session_id":"…", "frames_played":N, "frame_count":N,
  "effective_fps":24, "dwell_ms":41.67, "planned_duration_ms":1000, "restored":true }
```
**Success — cancelled** (`success:true` — a requested outcome, not an error):
```jsonc
{ "status":"cancelled", "cancelled":true, "replay_session_id":"…",
  "frames_played":K, "frame_count":N, "restored":true }
```
**Cancel route** (`success:true`): `{ "cancel_requested":bool, "reason"?:"no_active_replay"|"session_mismatch", "replay_session_id":"…" }`.

### `frames_played` semantics
- Counts frames whose pose/camera were **actually applied**.
- Cancel observed **before** applying frame 0 → `frames_played = 0`.
- Cancel observed **during frame K's dwell** (after K was applied) → frame K **counts** as played.

### `restored` field
- completed + `restore_on_finish:true` → `restored:true`; completed + `false` → `restored:false`.
- cancel / runtime failure → always `restored:true`.

### Two-phase validation
- **Worker-thread phase:** JSON shape, `replay_session_id`, `fps`, `loop`, caps, payload size, track-envelope consistency (`transform_semantics`, frame counts/sequence). Runs before any Dispatch.
- **UI-thread pre-apply phase:** document-dependent checks (`object_not_found`) — Rhino document access must stay on the UI thread. UI-phase failures still return validation-style errors; the slot is released by RAII and no frame mutation persists.

### Error codes & ownership

**Python-only** (thin resolver, before any native call):
| code | when |
|---|---|
| `invalid_track_input` | both or neither of `track` / `track_path` provided |
| `track_not_found` | `track_path` does not exist |
| `track_read_failed` | `track_path` unreadable / not valid JSON |

**Native-side** (route validation + replay lifecycle):
| code | when |
|---|---|
| `replay_already_active` | a replay is already in progress (pre-dispatch reject) |
| `invalid_session_id` | missing/malformed `replay_session_id` |
| `track_invalid` | malformed envelope / frame-count or `frame_index` sequence mismatch |
| `unsupported_transform_semantics` | not `absolute_from_source` |
| `unsupported_replay_option` | `loop:true` (`{option:"loop"}`) |
| `invalid_fps` | `effective_fps` not finite/positive |
| `frame_dwell_exceeds_cap` | `dwell_ms > 250` (`{dwell_ms, cap_ms}`) |
| `replay_duration_exceeds_cap` | `frame_count*dwell > 60000` (`{planned_duration_ms, cap_ms}`) |
| `frame_count_exceeds_cap` / `object_count_exceeds_cap` / `payload_too_large` | the 3000 / 256 / 8 MiB caps |
| `object_not_found` | a track object id absent from the doc (`{object_id}`) — UI-phase |
| `frame_apply_failed` | post-validation unexpected per-frame failure (`{frame_index, object_id?}`) |

This split keeps MCP tests asserting Python-layer codes and native tests asserting native-layer codes.

## Native implementation shape

**Files:**
- `src/RookNative/Handlers/DirectorReplayHandler.{cpp,h}` — `HandleDirectorReplay`, `HandleDirectorReplayCancel`, and the file-scope single active-slot registry.
- `src/RookNative/Handlers/DirectorFrame.{h,cpp}` — shared per-frame primitives: `ValidateFrameObjects` (**moved** here from `DirectorHandler.cpp`, not duplicated), `ApplyObjectTransforms`, `SetCameraFromFrame`, `SnapshotPreReplayState`, `RestoreToSnapshot`.
- `src/RookNative/Handlers/DirectorHandler.cpp` — `HandleDirectorFrameCapture` refactored to call the shared helpers, **behavior-preserving**.
- `src/RookNative/RookServer.cpp` — two `m_server->Post(...)` registrations beside the existing `/director/*` routes.

**Replay handler flow (worker thread):** parse → worker-phase validation (caps, track consistency, fps→dwell, `loop`, session id) → reserve slot (or `replay_already_active`) → `Dispatch` the replay lambda → block on its future → RAII-release slot → return outcome.

**Replay lambda (UI thread, the held loop):**
1. `SnapshotPreReplayState` (objects + camera) — after slot reserved, before first frame. The snapshot is **the source reference**: each frame's absolute transform is applied from it, the between-non-final-frames object restore returns to it, and the final restore (`restore_on_finish:true`, or any cancel/error) returns to it.
2. UI-phase pre-apply validation (`ValidateFrameObjects` → `object_not_found`).
3. Construct **one** `DispatchDrainSuspension` for the whole loop (not per frame). For each frame `i` (objects are at the snapshot/source before applying): `ApplyObjectTransforms` (absolute, from the snapshot) → `SetCameraFromFrame` (absolute) → redraw → **sliced dwell** (pump ~16ms slices until `dwell_ms` elapses, checking `cancel` each slice). Then:
   - **non-final frame** (`i < frame_count-1`): restore **objects** to the snapshot so frame `i+1` applies cleanly from source. (Camera is set absolutely every frame, so there is no camera restore-between.)
   - check `cancel` before advancing to the next frame.
4. **Terminal restore** (the single point that resolves `restore_on_finish`):
   - **completed + `restore_on_finish:true`** → restore **objects and camera** to the snapshot.
   - **completed + `restore_on_finish:false`** → leave objects at the final frame's pose and the camera at the final frame; **no final restore**.
   - **cancel / runtime error** (at any frame) → **always** `RestoreToSnapshot` (objects and camera), regardless of `restore_on_finish`.
   On loop exit by any path the guard releases (its wake-on-release drains deferred HTTP→UI work).

**Parity is the reason for the extraction:** both `HandleDirectorFrameCapture` and `HandleDirectorReplay` apply transforms, set the camera, and restore through the **same** `DirectorFrame` primitives, so the live preview matches what capture will later produce — guaranteed by construction, not by inspection.

**`frame-capture` stays behaviorally unchanged:** validate → shared apply → shared camera → capture file → shared restore. No semantic change to `/director/frame-capture`.

## Python MCP surface

- **`rhino_director_replay`** — Python-mediated. `director.run_replay(arguments, *, call_native=call_rhino, port=None)`:
  - resolve the track: exactly one of `track` (inline object) / `track_path` (string) — both/neither → `DirectorError("invalid_track_input")`; path missing → `track_not_found`; unreadable/bad JSON → `track_read_failed`. **Read/forward only; no reshaping.**
  - `replay_session_id = arguments.get("replay_session_id") or uuid4().hex`.
  - POST `{replay_session_id, track, fps?, restore_on_finish, loop}` to `/director/replay`; return native `data` on success, raise `DirectorError` (→ error envelope) on native failure.
- **`rhino_director_replay_cancel`** — thin passthrough. `director.cancel_replay(...)`: require `replay_session_id` (else `DirectorError`); POST `{replay_session_id}` to `/director/replay/cancel`; return native `data`. **No Python replay-state registry, no Rhino dispatch, no attempt to cancel the initiating synchronous call from the same agent.**
- MCP schemas: no `oneOf`/`anyOf`; no capture/output/`capture` fields present; `rhino_director_replay` exposes `track` / `track_path` / `replay_session_id?` / `fps?` / `restore_on_finish?` / `loop?`.

`cancel` is **out-of-band**: because `rhino_director_replay` blocks the caller for the replay duration, cancel is for the Vision/chat UI hitting the native route directly, a separate session, or tests — never the initiating agent.

## Caps (constants, enforced natively)

| constant | value |
|---|---|
| `pump_slice_ms` | ≈16 |
| `max_per_frame_dwell_ms` | 250 |
| `max_effective_replay_duration_ms` | 60000 |
| `max_frame_count` | 3000 |
| `max_object_count` | 256 |
| `max_payload_bytes` | 8 MiB |

`payload_too_large` is checked against the **raw request body size before full JSON parse** where practical.

## Testing & acceptance

**1. Native source-analysis** (`mcp_server/tests/test_director_replay_native_source.py`, static — no Rhino):
- both routes registered in `RookServer.cpp`;
- **parity (load-bearing):** both `HandleDirectorFrameCapture` and `HandleDirectorReplay` call the shared `DirectorFrame` helpers;
- replay wraps its pump in `DispatchDrainSuspension`;
- **no-capture boundary:** replay handler has no `CaptureViewportToFile` / `output_path`;
- **worker-thread cancel:** `HandleDirectorReplayCancel` contains **no `CMainThreadDispatcher::Instance().Dispatch`** (scoped to the dispatch assertion — not an over-broad "no Rhino API" grep, which would be brittle against comments/includes/helper names);
- `transform_semantics=="absolute_from_source"` required; caps constants present; RAII slot release present;
- frame-capture still does capture + restore (extraction didn't break it).

**2. Python unit + MCP** (`mcp_server/tests/test_director_replay.py` + additions to `test_director_mcp_tools.py`, `FakeNative` handling `/director/replay` + `/director/replay/cancel`):
- `run_replay` track resolution (inline / path-read / both-or-neither / missing / bad JSON), session-id gen vs passthrough, correct posted request, native error → `DirectorError`;
- `cancel_replay` requires `replay_session_id`, posts `{replay_session_id}`, returns data;
- MCP contracts: both tools registered; schema valid (no `oneOf`/`anyOf`, no capture/output fields); dispatch routing; error-envelope shape.

**3. Live Rhino** (`mcp_server/tests/test_director_replay_live.py`, `fresh_document` fixture):
- **restore smoke (cheap behavioral parity):** simple object + two-frame track; `restore_on_finish:false` → object and camera left at the expected final-frame state; same track `restore_on_finish:true` → object and camera restored to pre-replay state;
- **cancel mid-replay (load-bearing):** a concurrent `asyncio` task POSTs `/director/replay/cancel` while the replay blocks → `status:"cancelled"`, `frames_played < frame_count`, `restored:true`. *This is the only test that proves a worker-thread atomic interrupts a held UI-thread loop — it must run live.*
- `replay_already_active` (two concurrent replays → second rejected);
- key validation errors live (`loop:true` → `unsupported_replay_option`; wrong `transform_semantics`; `object_not_found`).

**Acceptance gates:**
- existing frame-capture tests stay **green** (behavior-preserving extraction proof);
- new source/unit/live tests green;
- native build clean; dispatcher source tests still 22/22 (guard untouched);
- **structural-primary parity** (shared helpers) — no full live replay-vs-capture parity harness in v1.

## Deferred (explicitly out of v1)

`loop:true` playback; client-disconnect / ESC cancellation; a full live replay-vs-capture parity harness; a session map / concurrent replays; per-frame timestamps; the normalized `frames[]` shape; deriving viewport aspect from the track's `resolution`.
