# RookVisionDirector Animation Compiler — PR4 Design (object-motion slice)

Date: 2026-06-24
Status: approved design (pre-plan)
Branch: `feature/rookvisiondirector-animation-compiler` (worktree off `origin/main` @ `a4956779`)
Roadmap: implements PR4 of
`docs/superpowers/specs/2026-06-24-rookvisiondirector-animation-authoring-roadmap.md`

## 1. Purpose & Scope

PR2 (`#346`) and PR3 (`#350`) made native `/director/replay` a stable, guarded,
display-only executor of a **baked replay track**. Today nothing *authors* that
track: the only object motion in the codebase is the single hard-coded
`expand_radial_bbox_center` (radial explode) in `director.py`, and that feeds the
frame-capture manifest, not the replay track.

This slice adds the **smallest valuable compiler**: a Python layer that turns a
compact, agent-friendly **object-motion authoring spec** into a validated baked
replay track that drops straight into `/director/replay`, with **zero native or
C# changes**. The camera half is reused as-is from `camera_planner.py`; the novel
contribution is object-motion keyframes with easing.

Out of scope is enumerated in §11. In one line: object-motion keyframes only —
no camera shot vocabulary, no persistence, no native contract change.

## 2. Architecture (Approach A)

Two new pure-Python modules plus one MCP tool. No native, no C#, and no
production change to `director.py`.

- **`mcp_server/src/rook/director_motion.py`** — pure, no I/O. Easing functions,
  normalized-`t` keyframe interpolation of **relative TRS deltas**, S→R→T
  composition about a pivot → per-frame **nested 4×4** matrix. Independently
  unit-testable without Rhino.
- **`mcp_server/src/rook/director_compiler.py`** — orchestration/I/O. Validates
  the spec, normalizes the timeline, expands groups, resolves live source state
  through an **injected** native resolver, drives `director_motion` for
  `object_frames`, drives `camera_planner` for `camera_frames`, and assembles
  `{track, provenance}`.
- **`rhino_director_compile_motion`** — MCP tool in `server.py`. Thin wrapper:
  compile-only, returns `{track, provenance}`, never calls replay, never mutates
  the document.

Reused **untouched**: `timeline.py`, `camera_planner.py`, and the native routes
`/director/object-states`, `/director/view-state`, `/director/curve-samples`
(reached only via the injected `call_native`). The compiler does **not** import
private helpers from `director.py`; if a genuinely shared helper is ever needed,
that is a deliberate, reviewed extraction — not a silent dependency. The
preferred outcome remains no `director.py` production change at all.

## 3. Output target — the baked replay track (source of truth)

The compiler's output must satisfy the native parser in
`src/RookNative/Handlers/DirectorReplayHandler.cpp` and the shared per-frame
parser in `DirectorFrame.cpp`. The relevant, **verified** constraints:

- `track.transform_semantics == "absolute_from_source"` (exact string).
- `track.animated_object_ids`: non-empty array of **unique** strings, **≤ 256**.
- `track.frame_count`: integer in **1..3000**.
- `track.camera_frames`: array, length **== frame_count**, each
  `{frame_index, camera}` with `frame_index == i+1` in order.
- `track.object_frames`: array, length **== frame_count**, each
  `{frame_index, object_transforms}` with `frame_index == i+1` in order.
- For **every** frame, the set of `object_transforms[].object_id` must **exactly
  equal** `animated_object_ids` (no missing, no extra, no duplicates).
- Each object's `source_state.bbox_*` must be **identical across all frames**
  (tolerance 1e-4) — satisfied automatically because the compiler resolves one
  source bbox per object and reuses it.
- `object_transforms[].transform`: **nested 4×4** numeric array (list of 4 rows ×
  4 cols — *not* flat-16). `transform[i][j] → ON_Xform.m_xform[i][j]`; OpenNURBS
  row-major, column-vector (`posed = M · source_point`), translation in column 3
  (`[i][3]`). The matrix is **inverted on parse** → it must be **invertible**.
- `object_transforms[].source_state`: `validation_strength` must be `"bbox_only"`;
  `bbox_min` and `bbox_max` are required 3-number arrays; the bbox must be valid.
- `track.fps` (optional to the runtime; default 24) — the compiler always emits it
  so the returned track is replay-ready without a separate `fps` argument.

The camera object shape inside `camera_frames[].camera` is exactly what
`camera_planner` already emits and what the shared `ParseCamera` consumes; no
new camera shape is introduced.

## 4. Input schema (authoring spec)

```jsonc
{
  "groups": {                      // optional; names local to THIS request
    "towers": ["<uuid>", "<uuid>"]
  },

  "timeline": { "fps": 24, "duration_seconds": 5 },   // OR { "fps": 24, "frame_count": 120 }
  "default_easing": "linear",      // optional track-level default; one of linear|ease_in|ease_out|ease_in_out
  "resolution": { "width": 1920, "height": 1080 },    // optional; default 1920x1080 (camera aspect only)

  "motion": [                      // >= 1 target track
    {
      "target": "towers",          // a group name OR a bare object uuid
      "keyframes": [               // >= 1; unique t in [0,1]
        {
          "t": 1.0,
          "translate": [0, 0, 50],                          // optional, default [0,0,0]
          "rotate": {                                       // optional, default none
            "axis": [0, 0, 1],
            "angle_degrees": 90,                            // |angle| <= 180 (shortest-arc; see 6.3)
            "pivot": "object_center"                        // default; OR [x,y,z] world point
          },
          "scale": 1.5,                                     // optional; scalar OR [sx,sy,sz]; default 1; each > 0
          "ease_from_previous": "ease_in_out"               // optional; default = default_easing
        }
      ]
    }
  ],

  "camera": { /* camera_planner: strategy keyframes | curve_follow_target */ }   // optional; default = hold active view
}
```

Field semantics established during design:

- **Addressing** (`target`): a declared group name or a bare object UUID. Groups
  expand to explicit object ids at compile time and never reach the runtime. The
  group-vs-UUID ambiguity is resolved by a hard rule, not precedence — see §4.1.
- **Timing** (`t`): normalized in `[0,1]`. `t=0` is source; `t=1` is final.
- **Easing**: per-segment override lives on the **destination** keyframe
  (`ease_from_previous`); the implicit `t=0 identity → first keyframe` segment
  uses that first keyframe's `ease_from_previous`, else `default_easing`
  (default `linear`).
- **Reference frame**: TRS are **relative deltas from source pose**. Omitted
  components are no-ops (`translate [0,0,0]`, no rotation, `scale 1`).
- **`t=0`**: an explicit `t=0` keyframe is allowed but **must be identity**
  (preserving "frame 1 = source"); a non-identity `t=0` is rejected (§7).

### 4.1 Target resolution (no group/UUID collision)

`motion[].target` is a single string that can mean a group name or an object id.
To prevent ambiguous authoring, resolution follows a hard rule rather than
precedence:

- `groups` keys are local symbolic names and **must not parse as Rhino UUIDs**.
  A UUID-shaped group name is rejected up front as `invalid_input` (we do not
  rely on resolution order to disambiguate).
- Group **member** entries must each be valid object UUID strings.
- `target` resolves as:
  1. if it matches a declared group name, resolve that group's members;
  2. otherwise it must be a valid object UUID string (resolved as a single
     object);
  3. anything else → `unknown_group` if it looks intended as a group reference,
     or `invalid_input` otherwise, with a message naming the offending `target`.

Because group names are forbidden from being UUID-shaped, a UUID-valued `target`
can only ever mean an object id, and a non-UUID `target` can only ever mean a
group name — the two namespaces cannot collide.

## 5. Timeline adapter (deliberate, source-verified)

`timeline.py::resolve_timeline` was read and does **not** support the PR4 shape
untouched:

- With a `timeline` block it **requires** `fps` (positive **integer**) **and**
  `duration_seconds` (> 0), and derives `frame_count = round_half_up(duration *
  fps)`. A top-level `frame_count`, if present, must equal that.
- With **no** `timeline` block it requires top-level `frame_count` and returns
  **`fps: None`**.
- There is **no** `timeline: {fps, frame_count}` path. `fps` is positive-integer
  only (fractional fps rejected).

PR4 therefore defines a **compiler-local timeline adapter** in
`director_compiler.py` that normalizes to `{fps, frame_count, duration_seconds}`
with a concrete integer `fps`:

- `timeline: {fps, duration_seconds}` → delegate to `timeline.resolve_timeline`
  (reuse verbatim) and read back `{fps, frame_count, duration_seconds}`.
- `timeline: {fps, frame_count}` → the compiler validates `fps` and `frame_count`
  as positive integers itself and sets `duration_seconds = frame_count / fps`.
  (It does **not** pretend `timeline.py` accepts this shape.)
- The **fps-None path is rejected** in PR4 (`invalid_timeline`) because `track.fps`
  must be concrete and the dwell/duration caps depend on it.

For the camera half, the compiler reuses `timeline.normalize_director_request`
(which maps camera keyframe `frame_index`/`time`/`at` → `frame_index`) by handing
it a request carrying `timeline: {fps, duration_seconds}` (the adapter always has
a concrete `duration_seconds`), so camera-keyframe timing normalization stays
identical to `run_director`.

## 6. Object-motion math (`director_motion.py`, pure)

### 6.1 Per-object setup
After group expansion, each animated object has a resolved source bbox →
`object_center = bbox center`. Segments are: an implicit identity at `t=0`, then
the target's authored keyframes sorted by `t`.

### 6.2 Per-frame sampling
- `frame i` (1-based) → `t_i = (i-1)/(N-1)`; if `N == 1`, `t_i = 0`. Hence frame 1
  is exactly source/identity and frame N is exactly `t=1`.
- Bracket `t_i` by surrounding keyframes `(kf_a at t_a ≤ t_i, kf_b at t_b ≥ t_i)`;
  local `u = (t_i − t_a)/(t_b − t_a)`; ease by `kf_b.ease_from_previous` → `e`.
- Before a target's first authored keyframe: interpolate from identity. After its
  last authored keyframe: **hold** the last delta through `t=1`.

### 6.3 Component interpolation
- **translate, scale**: component-wise lerp by `e`.
- **rotation**: each keyframe's `(axis, angle_degrees)` → quaternion;
  **slerp** by `e`. Easing applies to the segment progress uniformly across all
  TRS components (no per-component easing).
- **Rotation is shortest-arc only.** Quaternion slerp cannot represent multi-turn
  spin (e.g. a `360°` axis-angle collapses to identity in quaternion space).
  PR4 therefore **rejects `|angle_degrees| > 180`** as `invalid_keyframe`;
  spin/multi-turn rotation is explicitly deferred (future slice).
- **Pivot**: must resolve **consistently across a single target's rotation
  keyframes** (default `object_center` is per-object constant; mixing pivots, or
  mixing `object_center` with an explicit point, on one target → `inconsistent_pivot`).

### 6.4 Composition
Per frame: `M = Trans(translate) · Trans(p) · R · S · Trans(−p)` where `p` is the
pivot — scale and rotate happen about `p`, then the world translate is applied
(S→R→T relative to source). Output as a nested 4×4 row-major array with the
translate in column 3. The matrix must be invertible: every `scale` component
must be `> 0` (≤ 0 → `invalid_keyframe`), and the rotation axis must be a finite,
non-degenerate vector.

## 7. Data flow, validation & error contract

Flow (all failures are **compile-time**, before any track is produced or any
replay is attempted):

```
validate spec shape
  -> resolve compiler timeline (fps, frame_count, duration_seconds)
  -> expand groups; build per-object motion tracks; detect duplicate targets
  -> pre-validate native caps (objects, frames, dwell, duration)
  -> resolve live source state (injected call_native -> /director/object-states)
  -> director_motion -> object_frames
  -> camera_frames (camera_planner; default = hold active view)
  -> assemble { track, provenance }
```

The compiler **pre-mirrors the native caps** so replay is never the first place a
limit surfaces.

| Error code | Trigger |
|---|---|
| `invalid_input` | malformed top-level spec shapes (e.g. `motion` not a list, `target` missing); a **UUID-shaped group name**; a group member that is not a valid UUID string; a `target` that is neither a declared group nor a valid UUID (§4.1) |
| `invalid_timeline` | bad/zero fps, missing duration & frame_count, frame_count ≠ derived, or the fps-None path |
| `unknown_group` | a non-UUID `target` (group-shaped) that names a group not declared in `groups` (§4.1) |
| `empty_group` | a referenced group resolves to no objects |
| `duplicate_object_target` | an object is claimed by **two motion tracks** anywhere in `motion[]` (see below) |
| `invalid_keyframe` | bad/duplicate/out-of-range `t`; non-identity `t=0`; unknown easing name; `scale ≤ 0`; non-finite/degenerate axis; `\|angle_degrees\| > 180` |
| `inconsistent_pivot` | a target's rotation keyframes use differing pivots |
| `invalid_camera` | camera spec validation failure (`camera_planner.CameraPlanError`) |
| `camera_resolution_failed` | native camera resolution failure (`/director/view-state` or `/director/curve-samples`) |
| `source_resolution_failed` | a referenced object/group target cannot be resolved live (names the target) |
| `object_count_exceeds_cap` | animated objects > 256 |
| `frame_count_exceeds_cap` | frame_count > 3000 |
| `frame_dwell_exceeds_cap` | `1000/fps > 250ms` (fps < 4) |
| `replay_duration_exceeds_cap` | `frame_count * (1000/fps) > 60000ms` |

**Duplicate target semantics (tightened):** reject duplicate resolved objects
across the **entire** `motion[]` expansion, not merely within one frame's target
set. One object must have exactly one motion track; an object appearing in two
motion entries (via two groups, a group + a bare id, or two bare ids) →
`duplicate_object_target`. Sequential motion for an object belongs in that single
track's keyframes. (Within one group, duplicate ids collapse to a set; an empty
result is `empty_group`.)

**Camera errors (named, not conflated):** `camera_planner.CameraPlanError` maps to
`invalid_camera`; a failed native call during camera resolution maps to
`camera_resolution_failed`. Neither is conflated with `invalid_input` or
`source_resolution_failed`, so camera failures are distinguishable from object /
source failures.

## 8. Source-state acquisition

The public authoring payload carries **no** source bbox/state. The compiler
resolves live state by calling `/director/object-states` with the union of
resolved object ids (the same route `run_director::_resolve_objects` uses),
through an **injected** `call_native` so unit tests run without Rhino. From each
resolved object it takes `bbox_min`/`bbox_max` (→ `object_center` pivot and the
emitted `source_state`), `state_hash` (passed through), and emits
`validation_strength = "bbox_only"`. If **any** referenced object cannot be
resolved, compilation fails with `source_resolution_failed` naming the target —
replay is never the first place missing source state surfaces (barring true
document drift between compile and replay, which the runtime's frame-0 check
catches).

## 9. Output shape

`compile_motion(...)` and the MCP tool return `{track, provenance}`:

- **`track`** — replay-ready, per §3: `transform_semantics`, `fps`, `frame_count`,
  `animated_object_ids` (sorted union), `camera_frames`, `object_frames` (every
  animated object present in every frame; identity matrix when motionless;
  identical `source_state` across frames).
- **`provenance`** — sibling metadata (never sent to the runtime):
  `frame_count`, `fps`, `duration_ms`, `animated_object_ids`,
  `group_expansion` (`{name: [object_ids]}`), `segment_mapping` (per target: the
  resolved keyframe `t`s and per-segment easing), and `warnings` (always a list;
  empty when none).

The compiler invents neither `replay_session_id` nor `restore_on_finish` — those
are `rhino_director_replay`'s execution options. Callers pass `track` to
`rhino_director_replay`; `fps` rides inside `track`.

## 10. Camera handling

`camera_frames` are mandatory in the track. The compiler delegates to
`camera_planner.resolve_camera_plan` (existing `keyframes` / `curve_follow_target`
strategies), then wraps `frames[i]` as `{frame_index: i+1, camera: frames[i]}`.
**If `camera` is omitted**, the compiler defaults to a static hold: a single
`active_view` keyframe, so the current view holds across all N frames. Camera
keyframes keep their existing `frame_index`/`time`/`at` contract (reused as-is —
**not** redesigned to normalized-`t` in this slice). Both halves resolve against
the same `frame_count`.

## 11. Non-goals (scope fence)

Explicitly deferred: camera shot vocabulary (orbit/dolly/pan/truck — later
slice/PR7), absolute target poses, per-component easing, raw-4×4 keyframes,
multi-turn/spin rotation, request-supplied source state, a compile-and-replay
convenience tool, persistent animation artifacts (PR6), visibility/material/
display semantics (PR7), and **any native or C# contract change**.

## 12. Test plan

1. **Pure unit — `mcp_server/tests/test_director_motion.py`**: easing curves;
   single-keyframe hold; two-keyframe translate/scale lerp; rotation slerp;
   shortest-arc + `|angle|>180` rejection; pivot composition (`object_center` vs
   explicit world point); S→R→T order; nested-4×4 output shape & column-3
   translation; invertibility / `scale ≤ 0` rejection; endpoint pinning (frame 1
   = identity, frame N = `t=1`); hold-after-last.
2. **Compiler integration — `mcp_server/tests/test_director_compiler.py`**
   (injected fake `call_native`): group expansion (explicit / group / mixed);
   `duplicate_object_target` across `motion[]`; `unknown_group` / `empty_group`;
   timeline adapter (`{fps,duration_seconds}` and `{fps,frame_count}`, fps-None
   rejection, fractional-fps rejection); `animated_object_ids` = sorted union;
   every object in every frame; `source_state` embedded + `bbox_only`; camera
   default-hold + reused keyframes; `invalid_camera` vs `camera_resolution_failed`
   vs `source_resolution_failed` distinction; provenance shape; cap
   pre-validation (objects/frames/dwell/duration); and the emitted track passing a
   structural mirror of the native track rules from §3.
3. **Live smoke gate** (Rhino up, throwaway doc — confirmed with the user first):
   compile a real 2-object + group spec against live objects → pass the returned
   `track` to `/director/replay` → expect `status:"completed"`, `restored:true`.
   No native change, so this is a smoke proving the emitted track actually
   replays, not a 6/6 native gate.

## 13. Deliverables summary

- New: `director_motion.py`, `director_compiler.py`,
  `rhino_director_compile_motion` MCP tool (+ registration in `server.py`).
- New tests: `test_director_motion.py`, `test_director_compiler.py`.
- No native, no C#, no `director.py` production change, no replay/runtime change.
- Reuses `timeline.py`, `camera_planner.py`, `/director/object-states`, and the
  camera native routes via injected `call_native`.
