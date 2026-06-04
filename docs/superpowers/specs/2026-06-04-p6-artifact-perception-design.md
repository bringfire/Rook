# P6 Slice 1 — Durable Artifact Perception (design)

> **Status:** design, pending review.
> **Author:** Rook ⇄ Codex ⇄ user brainstorm, 2026-06-04.
> **Predecessors:** router plane P1–P5 (merged); test-hygiene gate (`4586d85`).
> **North-star:** `docs/superpowers/specs/2026-06-03-rook-north-star-topology.md` §5 (entity model), §5.5 (Save membrane), §8 (fan-in), §9.1 (two-speed spec).

---

## 1. One sentence

> **P5 owns process/session lifecycle. P6 owns durable artifact perception. Separate invariants, separate registries, same SQLite discipline.**

P6 Slice 1 makes **saved work products visible after their producing session is gone**, without composing them and without reopening P5.

## 2. Why this slice (and why this small)

Everything through P5 is fan-**out** (address, route, lifecycle). Fan-**in** is the under-built half. North-star §5 splits fan-in by **altitude**:

- **Document / Artifact identity** lives on the **orchestration plane** (the Rook runtime — `bridge.py`/`targeting.py`, where `fetch_document_metadata` already is). Promoting it is *surfacing existing metadata, not inventing a subsystem* (§5.2).
- **Merge Contract** (the recomposition edge) lives one altitude up on the **coordinator plane** and is *net-new* (§5.3). §9.1's two-speed discipline says design the merge schema **against observed reality** — and this slice produces that observation.

So Slice 1 is the artifact registry **only**. It mirrors P1 (see sessions → later route) one layer down (see artifacts → later compose). The danger is jumping to recomposition before artifact identity is solid; this slice refuses to.

## 3. Non-goals (hard boundaries)

- **No merge-contract vocabulary, no dependency-DAG edges** (coordinator plane, later slice).
- **No import / worksession / linked-model execution.** Perception, not recomposition.
- **No save-hooks.** Slice 1 does not touch the fragile cross-process `.3dm` save membrane (§5.5; the .NET-subprocess handle-inheritance seam). First observe; later decide how to touch save.
- **No P5 registry writes.** P5's reserved `last_document_*` columns stay NULL/untouched (see §9, Fix 2). Zero blast radius.
- **No live-session identity as document identity.** Identity is the durable path, never `document_serial_number` (§5).
- **No shared SQLite base class** (premature abstraction; revisit only if duplication becomes painful).
- **No auto-observation of adopted / attached / user / panel sessions.** Only owned Workbenches auto-populate durable rows (§9, Fix 3).

## 4. Placement & store

- New module `mcp_server/src/rook/artifacts.py` → class **`ArtifactRegistry`**.
- Own database file: `%LOCALAPPDATA%/Rook/registry/artifacts.db` (resolved by an `artifacts.py`-local `resolve_artifact_db_path()`, mirroring P5's `resolve_registry_path`).
- **Same SQLite discipline as P5, independently owned:** WAL, `busy_timeout`, `BEGIN IMMEDIATE` for writes, `check_same_thread=False` + a module `RLock`, **additive / fail-closed schema with NO destructive version wipe**, own `ARTIFACT_REGISTRY_VERSION = "p6.1"`.
- **Zero edits to `registry.py`.** The two registries hold different invariants (ownership/reclaim vs durable-artifact-memory) and version independently.

## 5. Entity & identity

A **durable artifact** is a saved `.3dm` (or other produced file) addressable by path, independent of any live session.

- **Dedup key = the normalized absolute path.** Normalization is `os.path` `normcase` + `normpath` + `realpath` (Windows is case-insensitive, so `C:/A.3dm` and `c:/a.3dm` are one artifact). Upsert is keyed on this path.
- **`artifact_id` = the full SHA-256 hex of the normalized path** — a deterministic, collision-free stable handle (re-observation is idempotent; a later slice can reference an artifact by stable id). It is **`UNIQUE`** in the schema; because it is a pure function of `path`, the two unique constraints always agree, and any (astronomically unlikely) collision **fails closed** — the conflicting insert is rejected, never overwriting a different artifact's row. Tools accept `id` or `path` (selector rules, §10.1).
- **Identity is NOT `document_serial_number`.** Serial is a live-session snapshot, not durable identity. A save-as to a new path is a *new* artifact in Slice 1 (logical-artifact-across-renames is a later concern).

## 6. Schema — `artifacts` table

| Column | Type | Notes |
|---|---|---|
| `artifact_id` | TEXT **UNIQUE** | full SHA-256 of the normalized path; pure function of `path`; collision fails closed, never overwrites |
| `path` | TEXT **UNIQUE** | normalized absolute path — the dedup identity |
| `file_state` | TEXT | **single canonical tri-state**: `present` \| `missing` \| `unreachable`. `fileExists` (true/false/null) is **derived in the tool projection**, never stored — two fields encoding one truth can disagree (a P5 lesson). |
| `source` | TEXT | **single field** collapsing provenance + scope: `owned_workbench` \| `explicit`. Extensible to `adopted`/`attached` only if auto-observe is *consciously* broadened later. One source of truth ⇒ I8 is trivially testable. |
| `origin_session_id` | TEXT? | non-authoritative breadcrumb (the `rhino-<pid>` we observed it from), NULL for `explicit`. The artifact may outlive that session; the id may no longer resolve. Not a foreign key. |
| `document_name` | TEXT? | telemetry from the observe seam (`documentName`). |
| `size_bytes` | INTEGER? | from `os.stat` at observe/refresh (cheap). |
| `mtime` | INTEGER? | file mtime from `os.stat`. |
| `label` | TEXT? | optional caller-supplied tag; no dedicated management tool in Slice 1. |
| `created_at` | INTEGER | first registration (epoch s). |
| `last_verified_at` | INTEGER? | last successful refresh/observe. |
| `last_missing_at` | INTEGER? | last time the file was confirmed absent. |

**Deferred — `document_serial_number`:** NOT in the Slice 1 schema. The observe seam (`fetch_document_metadata`, `targeting.py:1296`) supplies only `documentName`/`documentPath`/`objectCount`/`windowTitle` — **not serial.** Serial arrives in the later slice that extends the `/document` route to return it; the additive/fail-closed schema makes that a migration-free column add **with its writer and tests in the same slice.** No part of this spec implies the current seam supplies serial.

**Content hashing — deferred.** Expensive on large `.3dm`; path is identity; `size_bytes` + `mtime` suffice for Slice 1. A content hash (for version detection) is a later-slice option.

## 7. Population — two honest paths

The registry is fed two ways. **`ArtifactRegistry` never knows or infers ownership; callers pass `source`.** The owned-Workbench gate is a **policy gate that lives outside the registry.**

### 7.1 Observed (owned Workbench only)
The observe hook lives **inside the owned-Workbench listing/reconcile path** — `workbench.list_owned_workbenches()`, where ownership has **already been reconciled**, so the path *structurally* yields only owned Workbenches. **It does NOT live in `rhino_sessions`** (the fleet-perception surface, which also enumerates adopted/user sessions): keeping durable writes off that surface makes the ownership boundary **structural**, not a conditional that could leak (I8). For each owned, live Workbench:

```
for each OWNED, LIVE workbench             (structurally owned — no per-row ownership test)
   best-effort fetch_document_metadata
   if the live document has a SAVED PATH   (documentPath present & non-empty)
      and os.stat(path) SUCCEEDS           (existence proven on disk, not just open in Rhino)
   → observe_document(path, document_name, size, mtime, origin_session_id, source="owned_workbench")
```

- **Stat-gated, honest `file_state`** — a row is only ever *born* `present`, with existence proven by `os.stat`. Rhino holding a path open does **not** prove the durable file is on disk (it may have been moved/deleted/permission-blocked, or sit on a flaky drive):
  - no existing row + stat succeeds → create `present`.
  - no existing row + stat missing/unreachable → **no row** (swallow; never fabricate a phantom durable artifact).
  - existing row + stat missing/unreachable → transition to `missing`/`unreachable` (same rule as `refresh`, §8).
- **Best-effort, off-thread (`asyncio.to_thread`), failure-swallowed.** If metadata fetch / stat / upsert fails, **listing must not fail** (I4).
- Unsaved documents (no path) are **not** persisted — no durable row.
- **Adopted / attached / user / panel sessions are never auto-persisted** (I8) — structurally, because this hook never sees them.
- **No P5 `last_document_*` write** (Fix 2). The artifact snapshot lives only in `artifacts.db`; `ArtifactRegistry` receives `source` as a parameter and never infers ownership.

### 7.2 Explicit (any existing file)
`rhino_artifact_register(path)`:

- Normalize + validate the path; **require the file to exist at register time** (Slice 1 is perception, not planning — pre-registering an absent expected output is a later merge-planning concern). Absent → `artifact_file_not_found` (`retryable: false`).
- `source = "explicit"`.
- **Tool doc, load-bearing:** *registering a path is a coordinator/user **assertion** that the artifact is in scope for the campaign. It records a registry row; it **never deletes or edits the file.***
- Covers pre-existing masters, exported files, user-provided references, and sessions that opened + saved + closed between observation cycles.

## 8. Lifecycle, refresh & the removal invariant

**Mark, never auto-delete.** An artifact row is the coordinator's memory that a durable work product existed; a missing file changes the artifact's *state*, never erases its *history*.

- `rhino_artifact_refresh(id | path)` re-checks the file and **never touches it**:
  - file present → `file_state = present`, update `size_bytes`/`mtime`/`last_verified_at`.
  - file confirmed absent → `file_state = missing`, set `last_missing_at` (+ `last_verified_at`).
  - cannot check (permission / unreachable drive / OneDrive flap) → `file_state = unreachable`. **Never assert `missing` on a flap** (the "never refresh a stale reference" half of the invariant).
- `rhino_artifact_deregister(id | path)` removes the **registry row only**. **Tool doc, load-bearing:** *deregister means "forget this registry row," NOT "delete the `.3dm`."* Row deletion is semantically separate from file deletion and is the **only** destructive row operation.

**Born-present rule:** a row is only ever *created* in `present` (creation requires a successful `os.stat` — via observe §7.1 or explicit register §7.2). `missing` and `unreachable` are only ever *transitions* of an existing row, never initial states. A perceived artifact never silently un-exists — its history persists as a tombstone.

## 9. Codex review corrections folded in

1. **Serial not implied** — dropped from Slice 1; observe seam only supplies name/path (§6).
2. **No P5 writes** — observe writes only `artifacts.db`; P5 columns untouched; a snapshot writer is a separately-scoped P5 PR (§7.1).
3. **Ownership boundary** — auto-observe is owned-Workbench-only and the gate lives **outside** `ArtifactRegistry`; everything else needs explicit registration (§7, I8).

Round 2:

4. **Observed rows are stat-gated** — born `present` only on a successful `os.stat`; Rhino holding a path open is not proof of disk existence (§7.1).
5. **Observe hook is the owned-Workbench path** (`list_owned_workbenches`), never `rhino_sessions` — the ownership boundary becomes structural (§7.1, I8).
6. **`id`/`path` selector conflict defined** — `artifact_selector_conflict` / `artifact_selector_required` (§10.1), mirroring P3's `session`/`port` lesson.
7. **`artifact_id` is full SHA-256, `UNIQUE`, fail-closed** on collision (§5, §6).

## 10. Tool surface

Meta tools (session-agnostic; none accept a `session` argument — artifacts do not back-reference sessions, §5.4 disposability):

| Tool | Purpose |
|---|---|
| `rhino_artifacts` | list registered artifacts; optional `id`/`path` filter acts as get. Projection includes derived `fileExists`. |
| `rhino_artifact_register` | explicit registration (§7.2). |
| `rhino_artifact_refresh` | re-verify a row's file state (§8). |
| `rhino_artifact_deregister` | forget a row; never touches the file (§8). |

### 10.1 Selector rules (`id` / `path`)

`rhino_artifacts` (get mode), `rhino_artifact_refresh`, and `rhino_artifact_deregister` resolve a single row by `id` or `path`, mirroring P3's `session`/`port` discipline:

- exactly one of `id` / `path`, **or** both supplied and resolving to the **same** row → valid.
- both supplied and **disagree** → `artifact_selector_conflict` (`retryable: false`).
- neither supplied where a selector is required → `artifact_selector_required` (`retryable: false`).

`path` is normalized before resolution. `rhino_artifacts` with **no** selector is a full list (not an error).

**Cross-phase seams (must match the house contract):**
- Register all four in `targeting._META_TOOLS` **and** `_ALL_KNOWN_TOOLS`.
- All results are `{success: bool, data: {...}}`; every failure carries `retryable`.
- All blocking SQLite work runs via `asyncio.to_thread`.
- `_format_tool_result` renders success as `json.dumps(data)` and failure as `"Error: " + json.dumps(data)` (smokes strip the prefix).

## 11. Error handling

- Observe upsert / metadata fetch raises → swallowed; listing unaffected (I4).
- Registry unusable (version skew / fail-closed bootstrap) → tools return a structured `artifact_registry_unavailable` (`retryable: true`); the observe side-effect is swallowed so listing still succeeds.
- `register`: missing file → `artifact_file_not_found` (`retryable: false`); unreachable / permission-denied → `artifact_file_unreachable` (`retryable: true`) — tri-state honesty, not the same as not-found; malformed path → `invalid_path`.
- `refresh` / `deregister` on unknown id/path → `artifact_not_found` (`retryable: false`).
- selector ambiguity → `artifact_selector_conflict` (both disagree) / `artifact_selector_required` (none where required) — both `retryable: false`.
- `artifact_id` collision on insert (not expected with full SHA-256) → fail closed, `artifact_id_collision`, never overwrite.

## 12. Invariants

- **I1** Never lose an artifact — no auto-delete; `deregister` is the only row removal.
- **I2** Never assert `missing` when you couldn't check — tri-state honesty.
- **I3** Identity is the durable normalized path, never the serial.
- **I4** Observation never fails session listing — best-effort, off-thread, swallowed.
- **I5** `refresh` / `deregister` never touch the file.
- **I6** Zero blast radius on P5 — separate module + db; the ownership gate *reads* P5 state, never writes it.
- **I7** Schema additive / fail-closed — never drop a row or table; version skew fails closed, never wipes.
- **I8** A user/adopted document never becomes durable coordinator state without explicit registration — auto-observe is owned-Workbench-only, and the policy gate lives **outside** `ArtifactRegistry` (the registry only accepts `source`).

## 13. Testing

Mirrors P5's discipline (the now-stable non-live gate makes baseline parity trustworthy).

- **`ArtifactRegistry` unit tests:** CRUD; path-normalization dedup (case-insensitive); upsert idempotency (same path → one row, updated); refresh transitions `present`↔`missing`↔`unreachable`; schema fail-closed on version skew (never drops rows); **registry accepts `source` as a parameter and never infers ownership** (I8 at the unit level).
- **Observe-glue tests** (mocked `fetch_document_metadata` + `os.stat`): saved + **stat succeeds** → row `present`, `source=owned_workbench`; saved + **stat missing/unreachable** → no *new* row, and an *existing* row transitions to `missing`/`unreachable`; unsaved (no path) → no row; fetch/stat raises → swallowed, listing OK (I4). The owned-only boundary is **structural** (the hook lives in `list_owned_workbenches`), so it is verified by the live smoke rather than a per-row ownership branch.
- **Tool-surface tests** with an autouse isolated `artifacts.db` fixture — patch the **module-local** `resolve_artifact_db_path` name and manage the singleton manually (the P5 T9 monkeypatch-local-name lesson).
- **Live smoke `p6-artifact-perception`** (owned-Rhino harness): owned Workbench saves a `.3dm` → row `present` → close the session → **row persists as `present`** (the headline); **a non-owned session's saved doc is NOT auto-persisted** (I8 live); `deregister` removes the row while the file remains on disk (I5 live).
- **Baseline parity** vs `main` on `python -m pytest mcp_server/tests -m "not requires_rhino"` — prove failed/errors unchanged.

## 14. Files

- **Create:** `mcp_server/src/rook/artifacts.py`, `mcp_server/tests/test_artifacts.py`, `mcp_server/tools/p6_artifact_perception_live_harness.py` (+ a `p6-artifact-perception` choice in `scripts/run_rhino_runtime_harness.py`).
- **Modify:** `mcp_server/src/rook/server.py` (4 tool decls + handlers); `mcp_server/src/rook/workbench.py` (the stat-gated observe hook inside `list_owned_workbenches` — owned-only by construction; imports `ArtifactRegistry`, never the reverse); `mcp_server/src/rook/targeting.py` (`_META_TOOLS` + `_ALL_KNOWN_TOOLS` membership).
- **Untouched:** `mcp_server/src/rook/registry.py` (zero P5 edits).

## 15. Decision log

- **Scope = DocumentRegistry only** (orchestration plane). Merge contracts are coordinator-plane (§5.3) and a later slice, designed against what Slice 1 observes (§9.1).
- **Population = observe-from-owned-Workbenches + explicit register.** No save-hooks (membrane deferred).
- **Lifecycle = mark, never auto-delete;** tri-state `file_state`; explicit `deregister` is the only row removal; row deletion ≠ file deletion.
- **Store = separate module + separate `artifacts.db`** (Approach A); same SQLite discipline; no shared base class yet.
- **Codex blockers folded:** serial deferred; no P5 writes; owned-Workbench-only auto-observe with the policy gate outside the registry; `provenance`+`source_scope` collapsed into one `source` field.
