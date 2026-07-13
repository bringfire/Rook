# Director v3 Slice 3: File-Backed Compile + Delta Worker Playback — Implementation Plan

> **PARTIALLY SUPERSEDED — Director MCP retirement (2026-07-13):** The general
> non-Director architecture and dated evidence in this document remain available.
> All `rhino_director_*`, `/director`, VisionDirector, and Director-domain examples,
> allowlist entries, count assumptions, acceptance criteria, and positive dispatch
> tests are superseded as of 2026-07-13. Replace those examples with
> non-Director fixtures when maintaining or replaying this work. This document must
> not be used to restore a Director MCP tool. See the
> [Director MCP Surface Retirement Design][director-mcp-retirement].

[director-mcp-retirement]: ../specs/2026-07-13-director-mcp-surface-retirement-design.md

> **For agentic workers:** This plan is written for an external implementer (Codex) executing task-by-task with a review checkpoint after every task. Steps use checkbox (`- [ ]`) syntax. **STOP at the end of each task and wait for review sign-off before starting the next task.**

**Goal:** Compile a prepared take into `track.json` (file-backed, cap-free, tight-bbox evidence) and play it in the worker document via a new capture-less native route with in-loop delta math, pristine gates, and drift detection.

**Architecture:** One shared Python module (`director_worker_common.py`) extracts the S2 document machinery and adds the double-hop reload; prepare gains the `prepared.3dm` snapshot; a new compiler module (`director_worker_compile.py`) reuses `director_compiler`'s timeline/target/TRS math but owns tight-bbox source-state evidence; a new self-contained native handler (`DirectorWorkerPlayHandler.cpp`) plays absolute tracks delta-wise; an orchestrator (`director_worker_play.py`) plus two MCP tools expose it.

**Tech Stack:** Python 3 asyncio + pytest (`mcp_server/`), C++ Rhino SDK (`src/RookNative/`), MCP registration in `server.py`.

**Spec:** `docs/superpowers/specs/2026-07-06-director-v3-slice3-compile-playback-design.md` (this branch — the binding contract; read it first). Parent: `docs/superpowers/specs/2026-07-06-director-v3-snapshot-boundary-design.md`.

## Execution Contract (read before Task 1)

- **Branch/worktree:** `codex/director-v3-slice3-compile-play` at `.worktrees/director-v3-slice3-compile-play`. Commit there, conventional-commit messages, one commit per green test cycle.
- **Python tests:** `cd mcp_server && python -m pytest tests/<file> -v`. Full covering set before each commit: the task's new file + `tests/test_director_worker_prepare.py` + `tests/test_director_take_package.py`.
- **Native build:** `cmd /c scripts\build-native.bat` from the worktree root. Never raw msbuild. There is no native unit harness — the compile gate + live gates are the native tests.
- **NEVER touch Rhino:** do not deploy, launch, close, or send commands to a live Rhino. Live gates are run by the controller with the human. Unit tests use the fake-native pattern only.
- **Frozen surfaces (do not modify):** `compile_motion`, `validate_caps`, `resolve_source_states`, `build_object_frames` in `director_compiler.py`; `DirectorReplayHandler.{h,cpp}`; `DirectorFrame.{h,cpp}` (its parser hard-rejects `validation_strength != "bbox_only"` at `DirectorFrame.cpp:589-590` — that is why the worker handler parses its own track); `director_take_package.py` except where a task explicitly says otherwise.
- **STOP FOR REVIEW** at the end of every task: report status (DONE / DONE_WITH_CONCERNS / BLOCKED / NEEDS_CONTEXT), commits, test evidence (RED and GREEN output for TDD tasks), files changed, and any deviation from this plan with its reason. Do not start the next task until the reviewer signs off.
- If the plan contradicts the code you find, STOP and report — do not silently improvise. The spec is the authority over this plan; this plan is the authority over your judgment calls.

## Global Constraints

- **Error taxonomy (exact `code` strings).** Reused from S2 verbatim: `invalid_input`, `package_invalid`, `package_hash_mismatch`, `document_not_saved`, `document_open_failed`, `wrong_document`, `take_copy_not_pristine`. New in S3: `compile_source_state_not_tight`, `compile_track_mismatch`, `compile_failed`, `track_invalid`, `track_objects_missing`, `worker_scene_not_pristine`, `playback_drift_detected`, `play_route_failed`. No other codes.
- **Role-aware dirty-doc policy:** a dirty document whose (case/slash-normalized) path is NOT this package's `scene.3dm`/`prepared.3dm` blocks with `document_not_saved`; a dirty package document is discardable during open/reset/double-hop.
- **Subset semantics:** `animated_object_ids ⊆ member-map created ids`; any unknown id → `compile_track_mismatch`. Static members need no identity tracks.
- **Tight-bbox evidence:** every track `source_state` carries `bbox_method: "tight_object"` + `validation_strength: "tight_bbox"`; compile fails `compile_source_state_not_tight` otherwise.
- **Pristine/drift gates:** frame-0 pristine = tight-bbox EQUALITY within tolerance; `fromFrame > 0` pristine and the final drift gate = CONTAINMENT in the transformed source-bbox-corner envelope (+ tolerance) with centroid/diagonal diagnostics; exact equality is asserted only by proof fixtures. Default tolerance = 10 × doc absolute tolerance, request-overridable.
- **Worker constant:** `WORKER_MAX_FRAME_COUNT = 100_000` in `director_worker_compile.py`. No object cap. `validate_caps` is never called on the worker path.
- **Canonical JSON:** all package artifacts are written/hashed via `canonical_json_text` / `write_canonical_json` / `sha256_file` from `director_take_package.py` (the ONE serialization all hashes are computed over). All-or-nothing writes: serialize + hash everything, then write; `status.json` last.
- **Native registration pattern (S2-verified):** free function in `Rook::Handlers`, direct lambda registration next to the director siblings in `RookServer.cpp` (~line 1000) — NO member forwarder, NO `McpRequestGuard` (the real siblings have none). `Rook::Infrastructure::GetLayerFullPath`-style shared helpers must be namespace-qualified.
- **Pinned MCP counts** go 439 → 441. Find every site with `rg -n "rhino_director_prepare_take" mcp_server/src mcp_server/tests` and mirror it; both new tools are MUTATE (never in `_RHINO_READ_TOOLS` or any read-only list).

## Wire + Artifact Contracts

**`POST /director/worker-play` request** (camelCase, matching native style):

```json
{
  "expectedDocumentPath": "C:/takes/take1/prepared.3dm",
  "trackPath": "C:/takes/take1/track.json",
  "fromFrame": 0,
  "playTo": 48,
  "probeFrames": [24, 48],
  "driftTolerance": null
}
```

Defaults: `fromFrame` 0, `playTo` frame_count, `probeFrames` [] (max 32). `driftTolerance`: **absent or JSON `null` → default (10 × doc absolute tolerance); present and non-null → must be a positive finite number, anything else is `track_invalid`.** Constraint `0 <= fromFrame < playTo <= frame_count`.

**Success response `data`:**

```json
{
  "documentPath": "...", "playedFrom": 0, "playedTo": 48,
  "frameCount": 48, "objectCount": 3,
  "probes": [{"frameIndex": 24, "objects": [
      {"objectId": "...", "bboxMin": [x,y,z], "bboxMax": [x,y,z]}]}],
  "drift": {"tolerance": 0.01, "worstCentroidOffset": 0.0003,
             "worstDiagonalRatio": 1.0001},
  "timing": {"totalMs": 412.0, "perFrameMs": [8.5, 8.4]}
}
```

**Failure shape:** `WriteResult` failure with `data.reason` ∈ {`wrong_document`, `track_invalid`, `track_objects_missing`, `worker_scene_not_pristine`, `playback_drift_detected`} plus evidence fields (per-object lists where applicable). Python maps envelope failures to `play_route_failed` EXCEPT when `data.reason` names one of these codes, in which case it re-raises that code (mirror how S2 handled `wrong_document` defense-in-depth, but now surfacing the native reason as the Python code).

**`track.json`** = existing schema (`transform_semantics: "absolute_from_source"`, `fps`, `frame_count`, `animated_object_ids`, `camera_frames`, `object_frames`) with two S3 changes: each `object_transforms[].source_state` is the worker evidence dict `{bbox_min, bbox_max, bbox_method: "tight_object", validation_strength: "tight_bbox", state_hash}`, and a top-level `"derived_from": {"resolved_motion_sha256", "member_map_sha256", "prepared_3dm_sha256"}` block.

**`member_map.json` addition (S2 extension, additive, no version bump):** `"prepared_scene": {"file": "prepared.3dm", "sha256": "...", "bytes": N}`.

**`status.json`:** compile advances phase to `"compiled"` and merges evidence `{track_json_sha256, compile_provenance_sha256, prepared_scene_sha256}`; play appends to `evidence.play_runs` a `{at_utc, played_from, played_to, probe_count, drift, timing_total_ms}` entry (list, most recent last; plays are evidence, not a phase).

---

### Task 1: `director_worker_common.py` — shared document machinery + double-hop

**Files:**
- Create: `mcp_server/src/rook/director_worker_common.py`
- Modify: `mcp_server/src/rook/director_worker_prepare.py` (delegate `_norm_path`, `_native`, `_open_scene_document` internals to common; behavior-preserving)
- Test: `mcp_server/tests/test_director_worker_common.py`

**Interfaces (later tasks consume these exactly):**

```python
# director_worker_common.py
class DirectorWorkerError(Exception):
    def __init__(self, code: str, message: str): ...
    def to_data(self) -> dict: ...

def norm_path(value: str) -> str: ...
async def native_call(call_native, endpoint, method, data, port,
                      error_code, error_cls) -> Any: ...
async def get_document(call_native, port, error_cls) -> dict: ...
async def open_package_document(call_native, package_root: Path,
                                target: Path, *, port, error_cls,
                                mode: str) -> None:
    """mode='fail_closed' (S2 prepare semantics: alreadyOpen -> error) or
    mode='require_fresh' (compile/reset: alreadyOpen -> double-hop reload
    via the OTHER package file)."""
def enforce_save_copy_evidence(evidence: dict, error_cls) -> None: ...
```

- [ ] **Step 1: Write the failing tests**

`tests/test_director_worker_common.py`. Build a stateful fake native like `make_fake_native` in `tests/test_director_worker_prepare.py` (read it first — same call/return conventions), extended so `/document/open` records every open in order and can be configured to return `alreadyOpen: true` for same-path opens only. Tests (11):

1. `test_norm_path_case_and_slashes` — `norm_path("C:\\A\\b.3dm") == norm_path("c:/a/B.3DM".lower().replace(...))` style equality assertions.
2. `test_dirty_nonpackage_doc_blocks` — live doc = unrelated path, modified → `document_not_saved`; `/document/open` never called.
3. `test_dirty_scene_doc_is_discardable` — live doc = package `scene.3dm`, modified → open of `prepared.3dm` proceeds (no error).
4. `test_dirty_prepared_doc_is_discardable_on_reset` — live doc = `prepared.3dm`, modified, mode `require_fresh`, target `prepared.3dm` → proceeds (dirty package doc), open issued.
5. `test_fail_closed_mode_rejects_already_open` — same-path open returns `alreadyOpen` → `take_copy_not_pristine`.
6. `test_require_fresh_double_hops_on_already_open` — target `prepared.3dm`, first open returns `alreadyOpen` → helper opens `scene.3dm` then `prepared.3dm`; assert the recorded open sequence is exactly `[prepared, scene, prepared]` and no error.
7. `test_double_hop_via_file_missing_fails` — `scene.3dm` deleted from the package dir → `take_copy_not_pristine` (cannot force reload).
8. `test_double_hop_still_wrong_path_fails` — after double-hop the fake reports a different active path → `wrong_document`.
9. `test_wrong_path_after_plain_open_fails` — non-alreadyOpen open, active path ≠ target → `wrong_document`.
10. `test_enforce_save_copy_evidence_passes_and_fails` — the seven-field contract: complete+consistent evidence passes; missing field / changed path / `save_small_used: true` each raise `error_cls` with code `save_copy_invariant_violation` (the exact code S1 uses — read `director_take_package.py:236-249` and keep it verbatim).
11. `test_error_cls_is_respected` — pass a custom subclass; the raised error is an instance of it.

- [ ] **Step 2: Run to verify failure**

Run: `cd mcp_server && python -m pytest tests/test_director_worker_common.py -v`
Expected: FAIL, `ModuleNotFoundError: rook.director_worker_common`.

- [ ] **Step 3: Implement the module**

Extract from `director_worker_prepare.py`: `_norm_path` body → `norm_path`; `_native` body → `native_call` with an `error_cls` parameter replacing the hardcoded exception. `get_document` = GET `/document` via `native_call` with error_code `document_open_failed`. `enforce_save_copy_evidence` = the S1 field-and-equality checks (`director_take_package.py:236-249`) as a pure function raising `error_cls("save_copy_invariant_violation", ...)`.

`open_package_document` (the named shared function — the highest-risk orchestration detail, per review):

```python
async def open_package_document(call_native, package_root: Path, target: Path,
                                *, port: int | None, error_cls, mode: str) -> None:
    if mode not in ("fail_closed", "require_fresh"):
        raise ValueError(f"unknown mode: {mode}")
    scene = package_root / "scene.3dm"
    prepared = package_root / "prepared.3dm"
    package_norms = {norm_path(str(scene)), norm_path(str(prepared))}

    live = await get_document(call_native, port, error_cls)
    live_norm = norm_path(live.get("path") or "")
    # Role-aware dirty policy: never discard a user's work; package copies
    # are disposable by definition (spec Decision 2).
    if bool(live.get("modified")) and live_norm not in package_norms:
        raise error_cls(
            "document_not_saved",
            "the current document has unsaved changes; opening the take "
            "copy would silently discard them — save the document first")

    async def _open(path: Path) -> dict:
        data = await native_call(call_native, "/document/open", "POST",
                                 {"path": str(path)}, port,
                                 "document_open_failed", error_cls)
        return data if isinstance(data, dict) else {}

    opened = await _open(target)
    if opened.get("alreadyOpen"):
        if mode == "fail_closed":
            raise error_cls(
                "take_copy_not_pristine",
                "the take copy was already the active document and Rhino "
                "did not reload it from disk; close the document in Rhino, "
                "then re-run")
        # require_fresh: double-hop through the OTHER package file — two
        # genuine path changes, so neither open can no-op.
        via = scene if norm_path(str(target)) == norm_path(str(prepared)) else prepared
        if not via.is_file():
            raise error_cls(
                "take_copy_not_pristine",
                f"cannot force-reload {target.name}: intermediate "
                f"{via.name} is missing from the package")
        await _open(via)
        await _open(target)

    after = await get_document(call_native, port, error_cls)
    if norm_path(after.get("path") or "") != norm_path(str(target)):
        raise error_cls(
            "wrong_document",
            f"active document is {after.get('path')!r}; expected {target}")
```

Then rewire `director_worker_prepare.py`: `_norm_path = norm_path`, `_native(...)` delegates to `native_call(..., error_cls=DirectorWorkerPrepareError)`, and `_open_scene_document` becomes a thin wrapper calling `open_package_document(..., target=scene, mode="fail_closed", error_cls=DirectorWorkerPrepareError)` — note the S2 wrapper must preserve its exact current behavior; the pristine `/block/instances` gate stays in prepare, untouched.

- [ ] **Step 4: Run all covering suites**

Run: `cd mcp_server && python -m pytest tests/test_director_worker_common.py tests/test_director_worker_prepare.py tests/test_director_take_package.py -v`
Expected: 11 new PASS + all 21 prepare tests PASS unchanged + all take-package tests PASS. The S2 tests are the regression proof that the extraction is behavior-preserving — if any needs editing, STOP and report (that is a behavior change, not a refactor).

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/director_worker_common.py mcp_server/src/rook/director_worker_prepare.py mcp_server/tests/test_director_worker_common.py
git commit -m "feat(director): shared worker document machinery with double-hop reload"
```

**STOP FOR REVIEW.**

---

### Task 2: `prepared.3dm` snapshot in prepare (S2 extension)

**Files:**
- Modify: `mcp_server/src/rook/director_worker_prepare.py`
- Test: `mcp_server/tests/test_director_worker_prepare.py` (extend)

**Interfaces:** `member_map.json` gains `prepared_scene` (contract above); status evidence gains `prepared_scene_sha256`. Consumed by Task 3's hash chain.

- [ ] **Step 1: Write the failing tests** (extend the existing file; extend `make_fake_native` with a `/document/save-copy` endpoint returning the S1-shaped seven-field evidence, configurable to be missing/invalid; the fake must also create the staging file on disk when called — write `b"prepared-3dm-bytes"` to the requested path so the rename+hash path is real):

1. `test_prepare_writes_prepared_scene_snapshot` — happy path: `prepared.3dm` exists in the package; `member_map["prepared_scene"]` has file/sha256/bytes matching the disk file; status evidence carries `prepared_scene_sha256`; no `.prepared.3dm.staging` residue.
2. `test_prepare_save_copy_invariant_violation_fails` — evidence with `save_small_used: true` → error code `save_copy_invariant_violation`; no `member_map.json`, no `prepared.3dm`, no staging residue (all-or-nothing preserved).
3. `test_reprepare_overwrites_prepared_scene` — run prepare twice (fresh fake each time, same package after resetting status phase to `packaged` and deleting artifacts as a prior S2 re-run would); second run's `prepared.3dm` content/hash replaces the first.

- [ ] **Step 2: Run to verify the new tests fail** (existing 21 still pass).

- [ ] **Step 3: Implement.** In `prepare_take`, after `_verify_and_map` succeeds and BEFORE the member-map hashing block:

```python
    staging = pkg["root"] / ".prepared.3dm.staging"
    evidence = await _native(call_native, "/document/save-copy", "POST",
                             {"path": str(staging)}, port, "save_copy_failed")
    enforce_save_copy_evidence(evidence, DirectorWorkerPrepareError)
    if not staging.is_file() or staging.stat().st_size == 0:
        raise DirectorWorkerPrepareError(
            "save_copy_failed", "prepared.3dm staging missing or empty")
    prepared_path = pkg["root"] / "prepared.3dm"
    os.replace(staging, prepared_path)   # atomic promote; overwrites on re-prepare
    prepared_sha = sha256_file(prepared_path)
    prepared_scene = {"file": "prepared.3dm", "sha256": prepared_sha,
                      "bytes": prepared_path.stat().st_size}
```

Add `"prepared_scene": prepared_scene` to the `member_map` dict; add `"prepared_scene_sha256": prepared_sha` to the status-evidence merge; add `prepared_scene` to the return summary. `save_copy_failed` joins the module's used codes (it exists in the S1 taxonomy; reuse, don't invent). Import `os` and `sha256_file`.

- [ ] **Step 4: Run covering suites** (`test_director_worker_prepare.py` now 24, plus common + take-package). Expected: all PASS.

- [ ] **Step 5: Commit** — `feat(director): prepare persists prepared.3dm as authoritative reset artifact`

**STOP FOR REVIEW.**

---

### Task 3: `director_worker_compile.py` (TDD)

**Files:**
- Create: `mcp_server/src/rook/director_worker_compile.py`
- Test: `mcp_server/tests/test_director_worker_compile.py`

**Interfaces:**
- Consumes: Task 1 common helpers; Task 2 package layout; `director_compiler.resolve_compiler_timeline` / `expand_targets` / `build_camera_frames`; `director_motion.compile_object_track` + `EASING_NAMES`; native `/director/object-states` (returns per object `bbox_min`, `bbox_max`, `bbox_method`, `state_hash` — see `SerializeObjectState`, `DirectorHandler.cpp:522`).
- Produces: `async def compile_take(arguments={"package_root"}, *, call_native=call_rhino, port=None, now_fn=utc_now_iso) -> dict`; `DirectorWorkerCompileError(DirectorWorkerError-alike; own class, code/message/to_data)`; `track.json` + `compile_provenance.json` + status advance per the contracts above. Task 5 (play) and Task 6 (MCP) consume these.

**Module skeleton (implement exactly; ~230 lines):**

```python
WORKER_MAX_FRAME_COUNT = 100_000

class DirectorWorkerCompileError(Exception):
    # same shape as S2's error class (code, message, to_data)

def _load_compiled_package(package_root_arg) -> dict:
    # files required: scene_manifest.json, scene.3dm, motion.json, status.json,
    #   member_map.json, resolved_motion.json, prepared.3dm
    #   (prepared.3dm missing -> package_invalid,
    #    "missing prepared.3dm; re-run prepare")
    # status phase in ("prepared", "compiled") -> else package_invalid
    # hash chain (package_hash_mismatch listing every mismatch):
    #   sha256(scene_manifest.json bytes) == status["scene_manifest_sha256"]
    #   sha256(member_map.json text) == status["evidence"]["member_map_sha256"]
    #   sha256(resolved_motion.json text) == status["evidence"]["resolved_motion_sha256"]
    #   resolved_motion["derived_from"]["member_map_sha256"] == sha256(member_map.json text)
    #   member_map["prepared_scene"]["sha256"] == sha256_file(prepared.3dm)
    # returns {root, status, member_map, resolved_motion, camera (json or None)}

def _created_id_set(member_map) -> set[str]:
    # union of created_object_ids across all actor_sets[].members[]

async def resolve_worker_source_states(call_native, object_ids, port) -> dict:
    # POST /director/object-states {"object_ids": sorted ids}
    # -> per object require bbox_method == "tight_object"
    #    offenders -> compile_source_state_not_tight (list all)
    # -> {oid: {"bbox_min", "bbox_max",
    #           "bbox_method": "tight_object",
    #           "validation_strength": "tight_bbox",
    #           "state_hash": st.get("state_hash")}}

def build_worker_object_frames(expanded, worker_source_states, frame_count,
                               default_easing) -> list:
    # mirrors director_compiler.build_object_frames (director_compiler.py:181)
    # EXACTLY except each transforms entry's "source_state" is
    # worker_source_states[oid] verbatim (already the tight evidence dict).
    # Uses director_motion.compile_object_track with the bbox center from
    # the worker source state; wraps MotionError -> compile_failed
    # (original code+message in the detail).

async def compile_take(arguments, *, call_native=call_rhino, port=None,
                       now_fn=utc_now_iso) -> dict:
    # 1. _load_compiled_package
    # 2. open_package_document(target=prepared.3dm, mode="require_fresh",
    #                          error_cls=DirectorWorkerCompileError)
    # 3. spec = resolved_motion; timeline via
    #    director_compiler.resolve_compiler_timeline(spec) and
    #    expanded = director_compiler.expand_targets(spec)
    #    — both wrapped: DirectorCompileError as exc ->
    #      DirectorWorkerCompileError("compile_failed",
    #        f"{exc.code}: {exc}") from exc
    #    frame_count > WORKER_MAX_FRAME_COUNT -> compile_failed
    #    default_easing = spec.get("default_easing", "linear");
    #    not in director_motion.EASING_NAMES -> compile_failed
    # 4. subset check: unknown = sorted(set(expanded) - _created_id_set(...))
    #    -> compile_track_mismatch listing them
    # 5. resolve_worker_source_states; build_worker_object_frames
    # 6. camera_frames = await director_compiler.build_camera_frames(
    #        {"camera": pkg["camera"]}, frame_count,
    #        director_compiler._resolution(spec), duration_seconds, fps,
    #        call_native, port)   # wrap DirectorCompileError -> compile_failed
    # 7. assemble track dict (contract above) + derived_from block;
    #    provenance mirrors compile_motion's provenance shape
    #    (director_compiler.py:276-292) minus nothing — copy the structure.
    # 8. all-or-nothing: canonical_json_text + hashes for track and
    #    provenance BEFORE any write; then write track.json,
    #    compile_provenance.json; then status (phase "compiled",
    #    heartbeat, evidence merge with track_json_sha256 +
    #    compile_provenance_sha256 + prepared_scene_sha256).
    # 9. return {package_root, take_id, package_id, phase: "compiled",
    #            frame_count, fps, animated_object_count,
    #            track_json_sha256, compile_provenance_sha256}
```

- [ ] **Step 1: Write the failing tests** (~15; build `make_compiled_package(tmp_path, ...)` on top of the Task 2 fixtures — a helper that fabricates a fully-hashed post-prepare package: scene.3dm + prepared.3dm bytes, manifest, member_map with `prepared_scene`, resolved_motion with correct `derived_from`, status phase `prepared` with correct evidence hashes; parameterize for each tamper case. Fake native adds `/director/object-states` returning configurable `bbox_method` and bboxes, and reuses the Task 1 open/document fake):

1. missing prepared.3dm → `package_invalid` (message mentions re-run prepare)
2. wrong phase (`packaged`) → `package_invalid`
3. member_map hash tamper → `package_hash_mismatch`
4. resolved_motion derived_from tamper → `package_hash_mismatch`
5. prepared.3dm content tamper → `package_hash_mismatch`
6. `alreadyOpen` on prepared triggers double-hop then compiles (assert open sequence `[prepared, scene, prepared]`)
7. animated id not in member map → `compile_track_mismatch`
8. `bbox_method: "loose_fallback"` from object-states → `compile_source_state_not_tight` (offender listed)
9. happy path: track.json written; every `source_state.validation_strength == "tight_bbox"`; `derived_from` hashes match the package files; status phase `compiled` with evidence hashes matching disk
10. happy path camera: `camera_frames` length == frame_count
11. **cap-free proof:** 300 animated objects (well past the preview 256 cap) compiles cleanly — the test would fail if `validate_caps` leaked in
12. frame_count > `WORKER_MAX_FRAME_COUNT` → `compile_failed`
13. `DirectorCompileError` from `expand_targets` (e.g. UUID-shaped group name) → `compile_failed` with original code in the message
14. recompile (phase already `compiled`) overwrites track.json and updates hashes
15. **subset compile succeeds (the product decision, tested directly):** member_map has 4 created objects, resolved_motion animates exactly 1 of them (its group expands to that single id) → compile SUCCEEDS; `track.json["animated_object_ids"]` contains only that id (never the static three); every `object_frames[].object_transforms` list has exactly 1 entry

- [ ] **Step 2: RED run.** `cd mcp_server && python -m pytest tests/test_director_worker_compile.py -v` → ModuleNotFoundError.

- [ ] **Step 3: Implement per the skeleton.** Where the skeleton names a `director_compiler` line number, read that code first and mirror its structure — especially `build_object_frames` (`:181-210`) and the provenance block (`:276-292`).

- [ ] **Step 4: GREEN run + full covering set** (compile + common + prepare + take-package). Expected: all PASS.

- [ ] **Step 5: Commit** — `feat(director): file-backed worker compiler with tight-bbox evidence`

**STOP FOR REVIEW.**

---

### Task 4: Native `POST /director/worker-play` (`DirectorWorkerPlayHandler`)

**Files:**
- Create: `src/RookNative/Handlers/DirectorWorkerPlayHandler.h` (mirror `DirectorPrepareHandler.h`: one free function `HandleDirectorWorkerPlay`)
- Create: `src/RookNative/Handlers/DirectorWorkerPlayHandler.cpp`
- Modify: `src/RookNative/RookServer.cpp` (registration next to `/director/prepare-take`), `RookServer.h` if and only if the prepare-take sibling has a declaration there (S2 finding: it does not — verify and mirror)
- Modify: `src/RookNative/RookNative.vcxproj` + `.filters` (entries adjacent to `DirectorPrepareHandler`)

**Interfaces:** the wire contract above. Consumed by Task 5.

**Implementation contract (complete the .cpp from this; ~350 lines):**

- Include set: mirror `DirectorPrepareHandler.cpp` (stdafx, MainThreadDispatcher, JsonHelpers, WriteResult, DocumentHelpers, RookServer.h, `<fstream>`, `<chrono>`, `<map>`, `<set>`, `<string>`, `<vector>`).
- Anonymous-namespace helpers:
  - `NormalizePathForCompare` — copy verbatim from `DirectorPrepareHandler.cpp` (file-local duplicate is the established pattern; do not extract).
  - `ParseXform(const nlohmann::json& m) -> ON_Xform` — expects a 4×4 nested array (the shape `director_motion` emits; see `test` fixtures and `_mat_id` in `director_motion.py:52`); throw `std::invalid_argument` on any non-4×4/non-number.
  - `EnvelopeOfTransformedBbox(const ON_BoundingBox& src, const ON_Xform& xf) -> ON_BoundingBox` — transform the 8 corners, take min/max.
  - `BboxFromMinMax(const nlohmann::json& mn, const nlohmann::json& mx)`.
  - `FailureResult(const char* reason, nlohmann::json evidence) -> WriteResult` — `success=false`, `data["reason"]=reason`, merge evidence.
- Request parsing (before dispatch): required string `expectedDocumentPath`, required string `trackPath` — missing/mistyped REQUEST fields are plain `SendError` (caller bugs, `play_route_failed` on the Python side is correct for those). But everything about the TRACK and the play parameters carries the taxonomy: optional ints `fromFrame` (default 0) / `playTo` (default −1 = frame_count); `probeFrames` array of ints, > 32 entries → `SendErrorData` with `data.reason = "track_invalid"`; `driftTolerance` absent or JSON `null` → default, present non-null must be a positive finite number else `data.reason = "track_invalid"`.
- Read `trackPath` with `std::ifstream` and `nlohmann::json::parse`. **File-open failure, read failure, JSON parse failure, every schema-validation failure, and the frame-range check all return `SendErrorData` with `data.reason = "track_invalid"` plus evidence (which check, what was found)** — never generic `SendError`, which would collapse the taxonomy to `play_route_failed` on the Python side. (These run before dispatch; build the same `{"reason": ..., ...evidence}` JSON that `FailureResult` produces inside the dispatch and pass it to `CRookServer::SendErrorData` directly.) **Do NOT use the `DirectorFrame` parser** — it rejects `validation_strength != "bbox_only"` (`DirectorFrame.cpp:589`). Validate locally: `transform_semantics == "absolute_from_source"`; `frame_count` int ≥ 1; `object_frames` array of exactly `frame_count`, each with ordered `frame_index` (1-based) and `object_transforms` arrays; every `object_transforms` entry has `object_id`, `source_state.bbox_min/bbox_max`, `source_state.validation_strength == "tight_bbox"`, and `transform` parseable by `ParseXform`; the per-frame object id sets are identical across frames and equal `animated_object_ids`. Any violation → `FailureResult("track_invalid", {...which check, where...})`.
- Range check `0 <= fromFrame < playTo <= frame_count` → `track_invalid`.
- Dispatch once via `CMainThreadDispatcher::Instance().Dispatch` (the whole play is one UI-thread call; chunking is the caller's tool). Inside:
  1. `ResolveDoc`; document-path gate vs `expectedDocumentPath` (normalized) → `FailureResult("wrong_document", ...)` exactly like prepare-take.
  2. Resolve every animated id via `pDoc->LookupObject`; misses → `FailureResult("track_objects_missing", {"missingIds": [...]})`.
  3. Tolerance = `driftTolerance > 0 ? driftTolerance : 10.0 * pDoc->AbsoluteTolerance()`.
  4. **Pristine gate:** for each object, observed = `GetTightBoundingBox` (invalid → `track_objects_missing`-style failure with reason `worker_scene_not_pristine` and the id). If `fromFrame == 0`: every min/max coordinate within tolerance of `source_state` bbox (equality). Else: observed ⊆ `EnvelopeOfTransformedBbox(source_bbox, A_fromFrame)` inflated by tolerance (containment; also record centroid offset + diagonal ratio diagnostics). Violations → `FailureResult("worker_scene_not_pristine", {"objects": [{objectId, observedMin/Max, expectedMin/Max or envelope, centroidOffset}]})` — collect ALL offenders before failing.
  5. **UndoScope** (`L"Director worker play"`), then the loop: keep `std::map<std::string, ON_Xform> prev` seeded with `A_fromFrame` per object (identity when `fromFrame == 0`). For `i = fromFrame+1 .. playTo`: per object, `ON_Xform inv = prev[id]; if (!inv.Invert()) -> FailureResult("track_invalid", non-invertible at frame i)`; `ON_Xform delta = A_i * inv;` apply exactly as the proven idiom: `CRhinoObjRef objRef(pDoc->RuntimeSerialNumber(), uuid); pDoc->TransformObject(objRef, delta, true, false, true);` a false return → `FailureResult("track_invalid", transform failed at frame i for id)`. Update `prev[id] = A_i`. Record per-frame wall-clock (`std::chrono::steady_clock`). After applying frame `i`, if `i` ∈ probeFrames: record every animated object's observed tight bbox.
  6. **Drift gate at `playTo`:** per object, envelope = `EnvelopeOfTransformedBbox(source_bbox, A_playTo)` inflated by tolerance; observed tight bbox must be contained. Track worst centroid offset (envelope center vs observed center) and worst diagonal ratio (observed diagonal / envelope diagonal) across objects for the success payload. Violations → `FailureResult("playback_drift_detected", {"tolerance": tol, "objects": [per-object evidence]})` — collect all.
  7. `pDoc->Redraw();` once. Build the success `WriteResult` per the response contract (camelCase keys exactly).
- `future.get()` / `SendSuccess` / `SendErrorData` / catch → `SendError`, same tail as `HandleDirectorPrepareTake`.
- Registration: lambda `m_server->Post("/director/worker-play", ...)` calling `Rook::Handlers::HandleDirectorWorkerPlay(req, res)` directly, placed beside `/director/prepare-take`; include added beside the `DirectorPrepareHandler.h` include; vcxproj + filters entries beside the prepare-handler ones.

- [ ] **Step 1: Implement per the contract.**
- [ ] **Step 2: Build.** Run: `cmd /c scripts\build-native.bat` → zero errors. (Compile gate is this task's test; the math proofs come in Tasks 5/7.)
- [ ] **Step 3: Commit** — `feat(native): capture-less director worker-play route with delta math and drift gate`

**STOP FOR REVIEW.**

---

### Task 5: `director_worker_play.py` orchestrator + matrix oracle (TDD)

**Files:**
- Create: `mcp_server/src/rook/director_worker_play.py`
- Test: `mcp_server/tests/test_director_worker_play.py`

**Interfaces:**
- Consumes: Task 1 common (`open_package_document`, `norm_path`, `native_call`, `get_document`); Task 3 package/track contracts; Task 4 wire contract.
- Produces: `async def play_take(arguments={"package_root", "from_frame"?, "play_to"?, "probe_frames"?, "drift_tolerance"?, "reset"?}, *, call_native=call_rhino, port=None, now_fn=utc_now_iso) -> dict`; `DirectorWorkerPlayError` (same class shape).

**Behavior:** load/validate (phase `compiled`; `sha256(track.json)` == status evidence; `track.derived_from.member_map_sha256`/`prepared_3dm_sha256` re-verified against disk) → document handling per spec Decision 4 step 2 (default: active-path check, genuine-switch open when elsewhere, NO forced reopen; `reset: true` → `open_package_document(target=prepared, mode="require_fresh")`) → POST `/director/worker-play` with the request contract (native failure `data.reason` naming a known code re-raises as that code; otherwise `play_route_failed`) → append `evidence.play_runs` entry to status.json → return `{package_root, take_id, played_from, played_to, drift, timing_total_ms, probe_count, run_index}`.

**The matrix oracle lives in the test file** — pure functions, no imports from `director_motion`/`director_compiler`:

```python
def mat_mul(a, b): ...            # 4x4 row-major
def mat_inv(m): ...               # general 4x4 inverse via Gauss-Jordan (write it out)
def apply_pt(m, p): ...
def envelope(bbox_min, bbox_max, m): ...  # transform 8 corners, min/max
def chain_deltas_correct(mats):   # prev=I; delta=A_i·inv(prev); pose=delta·pose_prev
def chain_deltas_wrong(mats):     # delta=inv(prev)·A_i  (the reversed order)
```

- [ ] **Step 1: Write the failing tests** (~11):

1–5. Guard matrix mirroring Task 3's pattern: wrong phase, track hash tamper, missing track, active doc elsewhere + dirty non-package → `document_not_saved`, `reset: true` issues the reload (assert open call sequence).
6. default mode does NOT reopen when active doc is already prepared.3dm (assert no `/document/open` call).
7. happy path: native fake returns the success contract → status `play_runs` gains one entry; return summary fields correct; second play appends a second entry.
8. native failure with `data.reason: "worker_scene_not_pristine"` → raised code `worker_scene_not_pristine`; with unknown reason → `play_route_failed`.
9. **Oracle lemma — delta chain reproduces absolutes:** build 5 hand-constructed TRS matrices (translate + rotate about pivot [5,0,0] + non-uniform scale — write the matrices out numerically in the test); `chain_deltas_correct` reproduces each `A_i` within 1e-9.
10. **Oracle lemma — composition order is distinguishable:** `chain_deltas_wrong` diverges from `A_i` by a max-abs-difference > 1e-2 on those same matrices (i.e., orders of magnitude beyond any gate tolerance — a proof that cannot fail is not a proof, so this asserts the fixture CAN fail).
11. **Envelope prediction:** `envelope` of the 1×2×3 box under `A_final` matches hand-computed expected min/max (write the expected numbers in the test).

- [ ] **Step 2: RED run.** → ModuleNotFoundError.
- [ ] **Step 3: Implement the module** (~150 lines; reuse common helpers; mirror S2/S3 module structure).
- [ ] **Step 4: GREEN + full covering set** (play + compile + common + prepare + take-package). Expected: all PASS.
- [ ] **Step 5: Commit** — `feat(director): worker play orchestrator with matrix oracle`

**STOP FOR REVIEW.**

---

### Task 6: MCP tools + classification (439 → 441)

**Files:**
- Modify: `mcp_server/src/rook/server.py`, `mcp_server/src/rook/targeting.py`, `mcp_server/src/rook/agent/tool_groups.py`
- Test: `mcp_server/tests/test_director_worker_compile.py` + `test_director_worker_play.py` (one dispatch test each), `mcp_server/tests/test_server_tool_profiles.py` (pins)

Mirror `rhino_director_prepare_take` at EVERY site found by `rg -n "rhino_director_prepare_take" mcp_server/src mcp_server/tests`:

- `rhino_director_compile_take` — inputSchema `{package_root}` required; description states it OPENS prepared.3dm as the active document (double-hop reload if needed) and writes track.json.
- `rhino_director_worker_play` — inputSchema `{package_root, from_frame?, play_to?, probe_frames?, drift_tolerance?, reset?}`; description states it plays the compiled track in the open prepared.3dm, mutating the copy; `reset: true` forces a fresh reload first.
- Both MUTATE: in `_ALL_KNOWN_TOOLS` + director tool group; NOT in `_RHINO_READ_TOOLS` or any read-only list. Update every pinned count 439 → 441 including test-name suffixes (S2 renamed `test_full_surface_is_438...` → `_439...`; continue the pattern), balance assertions land both tools on the excluded side. Update pin comments in place; no changelog accretion.
- Dispatch tests mirror `test_mcp_dispatch_prepare_take` exactly (module-attribute AsyncMock patch; the wire success text is `json.dumps(data)` — the Slice 1 authority test's style).

- [ ] Steps: failing dispatch tests → RED → register + classify → run `test_director_worker_compile.py`, `test_director_worker_play.py`, `test_server_tool_profiles.py`, `test_director_worker_prepare.py`, `test_director_take_package.py` → all PASS → commit `feat(mcp): director compile-take and worker-play tools + classification`.

**STOP FOR REVIEW.**

---

### Task 7: Live gate file (written by implementer, RUN by controller + human)

**Files:**
- Test: `mcp_server/tests/test_director_worker_play_live.py`

Follow `test_director_worker_prepare_live.py` as the template (helpers, `_require_host`, opt-in env — new var `ROOK_S3_DOC_SWITCH`, scratch-doc docstring warning, save+cleanup flow — NEVER the evaporation flow; read that file's docstring for why). One test function per gate:

- `test_gate_a_composition_order`: fixture = block containing one 1×2×3 box off-origin (via `_create_brep` corners `[4,0,0]`,`[5,2,3]` then `/block/create`); motion = single member target with keyframes `[{t: 0}, {t: 1, translate: [10,0,0], rotate: {axis: [0,0,1], angle_deg: 45, pivot: [5,0,0]}, scale: [1,1.5,2]}]` (verify the exact keyframe field names against `director_motion.py`'s parser before writing — `_parse_scale`/`_parse_translate`/`_resolve_pivot` are the authority; adjust to the real vocabulary and note the adjustment). Flow: save doc → `package_take` → `prepare_take` → `compile_take` → `play_take(probe_frames=[mid, final])`. Assert: probe bboxes at BOTH frames match the oracle envelopes computed from the **track.json absolute matrices** (read the file, use the test-local oracle from Task 5 — import the oracle helpers from `tests/test_director_worker_play.py`) within `10 × doc tolerance`; for this box fixture assert near-equality (each coordinate), not just containment.
- `test_gate_b_reset_authority`: after Gate A's flow, `play_take(reset=True, probe_frames=[final])` twice; the two runs' final probe bboxes agree within tolerance; `status.play_runs` grew by 2.
- `test_gate_c_pristine_gate_fires`: play full, then immediately `play_take(reset=False)` again → expect `worker_scene_not_pristine` (the copy is at final pose, not source).
- `test_gate_d_throughput_measurement`: fixture block with ~300 boxes (create via a loop of `_create_brep` + one `/block/create`; keep coordinates spread so tight bboxes differ); 60-frame translate track; full play; PRINT (not assert) `timing.totalMs` and mean per-frame ms; assert only success + drift pass. Mark with an additional skip-env `ROOK_S3_SCALE=1` so the default gate run stays fast.
- Cleanup in every test: reopen original doc, `_delete_block` fixtures, save, assert object count restored (the S2 pattern verbatim).

- [ ] Steps: write file → `python -m pytest tests/test_director_worker_play_live.py --collect-only -q` (4 collected, no import errors) → unit suites still green → commit `test(director): slice 3 live gates — composition order, reset authority, pristine trip, throughput`.

**STOP FOR REVIEW.** The controller then runs the deploy handoff (human closes Rhino → `cmd /c scripts\deploy-native.bat` → human reopens with a saved scratch doc) and executes the gates.

---

## Self-Review Notes (writing-plans checklist)

- **Spec coverage:** Decision 1 → Task 2; Decision 2 → Task 3 (incl. `build_worker_object_frames`, subset semantics, cap-free proof, double-hop via Task 1); Decision 3 → Task 4 (own parser, frame-0 equality vs containment split, in-loop drift gate, camelCase wire); Decision 4 → Tasks 5–6 (reset modes, play_runs evidence, MUTATE classification); proof gates → Tasks 5 (oracle lemmas) + 7 (live A–D). Double-hop is a named shared function with dedicated unit coverage (review note honored).
- **Out of scope honored:** no capture, no camera application (camera_frames compiled but unused), no lifecycle, replay/DirectorFrame untouched.
- **Type consistency:** error classes per module with common `code/message/to_data` shape; `error_cls` threading keeps S2's exception identity intact (S2 tests unchanged is the regression gate).
- **Known dependency:** Pearson-scale play blocked on TL_Brep chip (`task_a06e920a`); Gate D uses a synthetic block instead.
