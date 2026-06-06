# P7 Slice 2 — Declared-Target State Machine (declare + promote a master before it exists)

> **Origin:** P7 of the Rook router plane — the fan-in / recomposition half. Slice 1 shipped the
> coordinator-plane merge-contract registry (`record` + `validate` fan-in intent) under a strict
> **present-bar**: every referenced artifact must already be a registered, `present` P6 row. Slice 1
> deliberately deferred (§3) *"planned / declared / future artifacts… a planned-master state machine
> is a later slice."* **This is that slice.** It adds a durable way to declare intent toward a
> master/anchor file **before it exists**, and an explicit, drift-safe step that binds the declaration
> to the real P6 artifact once the file is saved. **No merge executes; no geometry enters Rhino; the
> Slice 1 present-bar and `merge_contracts` semantics are unchanged.**

## 1. One sentence

Add a P7-only `declared_targets` ledger that records a coordinator's intent toward an anchor file by
its intended path (`status='declared'`, carrying a **predicted** artifact id computed from the path),
plus an explicit `promote` that registers the file through P6's public API and binds the declaration to
the real artifact (`status='materialized'`) — drift-checked, idempotent, and with no change to P6's
meaning or to Slice 1.

## 2. Binding principles

- **Prediction, not proof.** `artifact_id_for(normalize_path(p))` is a pure function of the path, so a
  declared target has a *computable* `predicted_artifact_id` before any file exists. That id is a
  **prediction**. It never makes P6 aware of the target, and it is re-verified against the real world at
  promotion — never trusted as proof of existence.
- **P6 stays "registered real rows only."** `declared_targets` live in P7's `work_units.db` only. P6's
  `artifacts.db` learns nothing about declared targets. The **only** P7→P6 contact is promotion, which
  calls P6's *public* `register_artifact()` to register a **plain artifact row carrying no P7
  vocabulary** (§6, §8). The §5.4 north-star invariant holds: *P6 never references P7.*
- **Promotion is the only mutating transition.** `declare` creates a `declared` row; `promote` is the
  sole path to `materialized`. `declared_targets` (list/inspect) **computes observations and transitions
  nothing** — the same discipline as Slice 1's "validity is never stored."
- **Two stored states, monotonic.** `status ∈ {declared, materialized}`. `conflict` / `missing` /
  `unreachable` / drift are **observations and results**, never stored lifecycle. Materialization never
  demotes (§7).
- **Drift is fail-closed.** Promotion recomputes the normalized path and id at promote time; any mismatch
  with the stored prediction (the `realpath`/symlink-in-parent trap) fails closed
  (`declared_target_path_identity_changed`).

**Main invariant:**

> P7 stores coordinator intent toward a not-yet-existing anchor as a *prediction*; only an explicit,
> drift-verified promotion — registering the real file through P6's public API — flips it to
> `materialized` and binds it to the real artifact id. `materialized` records that the bind once
> succeeded; current file existence is always recomputed, never asserted from the stored state.

## 3. Non-goals (hard boundaries)

- **No merge execution.** No worksession/import/linked-model/reference/block/report runs; no geometry
  enters any Rhino document. (Unchanged from Slice 1.)
- **No change to Slice 1.** `rhino_merge_contract_record` / `rhino_merge_contract_validate` keep the
  strict present-bar. **No `declared_contracts` / `planned_merge_contracts` table** — referencing a
  declared (not-yet-present) target from a contract is a *later* slice. To put a declared target into a
  merge contract today, `promote` it first; then record a normal strict contract.
- **No P6 mutation except explicit promotion.** P7 never edits or deletes P6 rows; promotion only
  *registers* (via P6's own `register_artifact`). Promotion never rolls back / deletes from P6 (§6).
- **No declared-target deregister, no reverse transition, no auto-promotion.** `declared_targets` never
  promotes as a side effect of listing.
- **No cross-database atomic transaction.** There is no transaction spanning `artifacts.db` and
  `work_units.db`; the non-atomic window is specified and made safe by idempotent retry (§6), not by
  distributed-transaction machinery.

## 4. Architecture

Extends the Slice 1 leaf `mcp_server/src/rook/work_units.py` and its store `work_units.db` with **one new
table** (`declared_targets`) and **three new tools**. The store remains Rhino-independent: pure logic over
SQLite plus a read-only P6 lookup, with the single exception of promotion's call into P6's public
`register_artifact()` (a normal artifact registration, §6). Schema stays **additive / version-gated /
fail-closed (never DROP)**; the version advances `p7.1 → p7.2` via a supported-set migration (§10).

**Altitude (unchanged):** declared targets are coordinator-plane intent, kept in P7's registry, distinct
from the orchestration-plane Session (P5) and Artifact (P6) registries. A declared target is the
artifact-side **anticipation** of a node that has not yet crossed the Save membrane (north-star §5.5).

## 5. Schema — one new table

```sql
CREATE TABLE declared_targets (
  declared_target_id    TEXT PRIMARY KEY,        -- generated "dt-<uuid12>"
  work_unit_id          TEXT,                     -- optional; validated-if-present at declare (§7)
  intended_path         TEXT NOT NULL,            -- raw path as the coordinator supplied it
  normalized_path       TEXT NOT NULL,            -- normalize_path(intended_path) captured at declare time
  predicted_artifact_id TEXT NOT NULL UNIQUE,     -- artifact_id_for(normalized_path) — prediction; UNIQUE = one decl/path
  status                TEXT NOT NULL,            -- 'declared' | 'materialized' (no other value is ever stored)
  bound_artifact_id     TEXT,                      -- NULL while declared; = predicted_artifact_id at promote
  label                 TEXT,
  created_at            INTEGER NOT NULL,
  materialized_at       INTEGER                    -- NULL while declared
);
CREATE INDEX idx_declared_targets_work_unit ON declared_targets(work_unit_id);
```

- `UNIQUE(predicted_artifact_id)` enforces **one declaration per intended path** (a second declare of the
  same normalized path fails closed — §7). The id is the SHA-256 of the normalized path, so "same path"
  and "same predicted id" are the same constraint.
- Added to `_REQUIRED_COLUMNS` (the fail-closed shape guard). The guard checks the table's columns **only
  if the table exists** — so a valid `p7.1` db that predates this table is *not* failed closed before the
  additive migration creates it (§10).
- `intended_path` (raw) and `normalized_path` (resolved) are both stored: the raw value is what the
  coordinator declared; the normalized value is the dedup/identity basis and the reference for the
  promote-time drift recompute.

## 6. `promote` — the only transition; the cross-DB window made safe

`rhino_declared_target_promote(declared_target_id)` is the sole path to `materialized`. Algorithm:

```
guard P7 registry usable (work_units_registry_unavailable)
guard P6 registry usable (artifact_registry_unavailable)         # promotion reads+writes P6
row = registry.get_declared_target(declared_target_id)
    └─ None → declared_target_not_found
if row.status == 'materialized':                                  # idempotent: bind already done
    return { declaredTargetId, status:'materialized', boundArtifactId: row.bound_artifact_id, … }

# (a) declared-path drift check — pure P7 recompute, no P6/disk write
if artifact_id_for(normalize_path(row.intended_path)) != row.predicted_artifact_id:
    → declared_target_path_identity_changed                       # symlink/realpath drift — FAIL CLOSED

# register the real file through P6's PUBLIC api (reuse; do not reinvent stat/upsert).
# register_artifact returns a {success, data} ENVELOPE, not an exception — promote MUST branch on
# r["success"] and map by r["data"]["code"]; a P6 failure is never treated as generic/opaque:
r = await artifacts.register_artifact(row.intended_path)
if r["success"] is False:
    code = r["data"]["code"]
    artifact_file_not_found        → declared_target_not_materialized (retryable)   # file not saved yet
    artifact_file_unreachable      → declared_target_unreachable      (retryable)   # perm / drive flap
    artifact_id_collision          → declared_target_path_conflict    (fail closed) # a DIFFERENT path owns this id
    artifact_registry_unavailable  → return r unchanged (already guarded above; pass through)
    <any other code>               → fail closed PRESERVING the P6 code: declared_target_promotion_failed
                                      with p6Code=code (never collapse an unknown P6 failure to generic)
artifact = r["data"]["artifact"]   # success → { artifactId, fileState:'present', … }

# (b) bind verification — the real P6 row must match the prediction and be present
if artifact["artifactId"] != row.predicted_artifact_id or artifact["fileState"] != 'present':
    → declared_target_path_identity_changed                       # defensive; shared hash ⇒ ~impossible

# P7 bind (single work_units.db transaction)
UPDATE declared_targets SET status='materialized',
       bound_artifact_id = predicted_artifact_id, materialized_at = now WHERE declared_target_id = ?
return { declaredTargetId, status:'materialized', boundArtifactId, path: normalized_path }
```

### 6.1 The cross-database non-atomic window (specified, accepted, made safe)

Promotion writes **P6 first** (`register_artifact`) then **P7** (the bind `UPDATE`). There is **no atomic
transaction across `artifacts.db` and `work_units.db`**, and Slice 2 does **not** add distributed-
transaction machinery. The window is acceptable for these reasons, which the implementation and tests
must honor:

- **Failure mode.** If P6 registration succeeds but the P7 bind fails or the process crashes between them,
  the result is a **plain P6 artifact row** plus a **still-`declared`** target. The two stores are merely
  out of step; neither is corrupt.
- **Recovery by idempotent retry.** Re-running `promote` is the recovery path. The target is still
  `declared`, so promotion proceeds; the drift check passes; `register_artifact` on the already-registered
  present path is an **idempotent upsert** that returns the *same* present row; bind verification passes;
  the P7 bind completes. Promotion is therefore **naturally re-entrant** — no special crash-recovery code
  is needed, only the guarantee that the bind step is safe to repeat.
- **Not a leak.** The orphaned-looking P6 row is a legitimate, fully-formed artifact row that **carries no
  P7 vocabulary**. It is exactly what `rhino_artifact_register` would have produced. Nothing references a
  non-existent P7 entity; nothing in P6 needs P7 to be valid.
- **No P6 rollback.** Promotion **never** deletes or edits the P6 row on P7 failure. Tearing down a
  legitimately-registered artifact to "undo" a half-promotion would corrupt P6's independent perception of
  a real file. The P7 bind is the only thing that retries; P6 is left as the truthful record it is.

## 7. `declare` and the lifecycle

`rhino_declared_target_declare(intended_path, label?, work_unit_id?)`:

1. Guard P7 registry usable. (Declare does **not** touch P6 and does **not** require the file to exist —
   the predicted id is pure computation.)
2. Validate `intended_path` is a non-empty string (`invalid_path`).
3. If `work_unit_id` is given, it must exist (`work_unit_not_found`); absent is allowed but discouraged.
4. Compute `normalized_path = normalize_path(intended_path)` and
   `predicted_artifact_id = artifact_id_for(normalized_path)`; generate `declared_target_id = dt-<uuid12>`.
5. Insert `status='declared'`. A `UNIQUE(predicted_artifact_id)` violation (the path is already declared)
   fails closed — and a conflict is **not** a successful declaration. On the violation, look up the
   existing row's id and return the explicit envelope:
   `{ success:false, data:{ code:"declared_target_path_conflict", existingDeclaredTargetId:<id>,
   retryable:false } }`. **Never return `success:true` for the pre-existing row** — an agent must not read
   a conflict as a fresh declaration. (Reject-never-silently-dedupe, the Slice 1 `duplicate_contract_source`
   posture.)

**State machine (monotonic, two states):**

```
   declare                          promote (registers via P6 + binds; the ONLY transition)
∅ ────────▶ declared ───────────────────────────────────────────────────▶ materialized
               │   drift ∨ not-present ∨ unreachable → fail closed, stays 'declared' (no partial flip)
               └── declared_targets(): computes observations, transitions NOTHING
```

`materialized` is **non-authoritative for current file existence.** It means *"promotion once succeeded
and bound this declaration to the predicted artifact id."* If the file is later deleted or its P6 row is
deregistered, P7 does **not** demote — the bind genuinely happened. Current truth is recomputed on read
(§9), never inferred from `status`. There is no reverse transition and no declared-target deregister in
Slice 2.

## 8. `declared_targets` — list/inspect with computed observations (no transition)

`rhino_declared_targets(declared_target_id?)`: with an id, that one; without, all (ordered
`created_at, declared_target_id`). Guards P7 registry usable. For every row it returns the stored fields
**plus a read-only `observed` block computed at call time** — a fresh `os.stat` of the current normalized
path (no P6 write) and a read-only P6 lookup:

| `observed` field | Meaning | Source |
|---|---|---|
| `fileState` | `present` / `missing` / `unreachable` of the intended path **right now** | fresh `stat_file_state` (read-only) |
| `pathIdentityStable` | `artifact_id_for(normalize_path(intended_path)) == predicted_artifact_id` | pure recompute (drift detector) |
| `p6Available` | the P6 registry is usable (not version-skewed) — promotion's hard precondition | read-only P6 guard |
| `artifactRegistered` | a P6 row exists for `predicted_artifact_id` (`null` if `p6Available` is false) | read-only `_p6_row` |
| `boundArtifactPresent` | for `materialized`: is `bound_artifact_id` a `present` P6 row now? (`null` while `declared`, or if P6 unavailable) | read-only `_p6_row` |
| `promotable` | `status=='declared' ∧ p6Available ∧ pathIdentityStable ∧ fileState=='present'` (a `promote` would now succeed) | computed |
| `promotionBlockedReason` | when `promotable` is false, the first failing precondition (token, in promote's own order); `null` when promotable | computed |

`promotionBlockedReason` is computed in promote's own precondition order, so it predicts what `promote`
would return right now: `already_materialized` (status is `materialized`) → `artifact_registry_unavailable`
(`p6Available` false) → `declared_target_path_identity_changed` (drift) → `declared_target_unreachable`
(`fileState=='unreachable'`) → `declared_target_not_materialized` (`fileState=='missing'`) → else `null`
(promotable). **`promotable` deliberately includes `p6Available`** — a version-skewed P6 makes `promote`
fail at its `artifact_registry_unavailable` guard, so reporting `promotable:true` then would be a lie.

This answers both coordinator questions — *"which declared anchors are ready to promote?"* and *"is my
materialized anchor still on disk?"* — without mutating anything. **Degrade, not fail-closed, on P6 skew:**
if the P6 registry is version-skewed, `declared_targets` still returns (perception is not blocked by a
P6-side skew), but `p6Available` is false, the P6-derived fields (`artifactRegistered`,
`boundArtifactPresent`) are `null`, and every `declared` row reports `promotable:false` with
`promotionBlockedReason:"artifact_registry_unavailable"`. The work-unit join
(`idx_declared_targets_work_unit`) also lets `rhino_work_units(work_unit_id)` surface "future outputs of
this assignment" alongside its existing artifacts/contracts.

## 9. Failure taxonomy (Slice 2 additions)

| Code | Raised when | `retryable` |
|---|---|---|
| `declared_target_not_found` | `promote`/inspect an unknown `declared_target_id` | `false` |
| `declared_target_path_conflict` | `declare` a path already declared (`UNIQUE`; returns `existingDeclaredTargetId`); or P6 `artifact_id_collision` at `promote` | `false` |
| `declared_target_not_materialized` | `promote`, but the file is not present yet (P6 `artifact_file_not_found`) | **`true`** |
| `declared_target_unreachable` | `promote`, file unreachable (permission / drive flap; P6 `artifact_file_unreachable`) | **`true`** |
| `declared_target_path_identity_changed` | `promote`-time recompute ≠ stored prediction, or bind verification mismatch | `false` (fail closed) |
| `declared_target_promotion_failed` | `promote`, an **unmapped** P6 `success:false` code — surfaced verbatim as `p6Code`, never masked | `false` |
| `work_unit_not_found` | `declare` with a `work_unit_id` that does not exist | `false` (reused) |
| `invalid_path` / `invalid_argument` | malformed inputs | `false` |
| `work_units_registry_unavailable` / `artifact_registry_unavailable` | P7 / P6 schema version skew | `true` (reused) |

## 10. Migration — additive `p7.1 → p7.2` (do not brick Slice 1 dbs)

Adding a table is additive and backward-compatible, but Slice 1's `_ensure_schema` is a **strict-equality**
version gate; naively bumping the version would make every existing `p7.1` `work_units.db` read as
`schema_unsupported`. Fix with a **supported-set** gate:

```
WORK_UNITS_REGISTRY_VERSION = "p7.2"
_SUPPORTED_PRIOR_VERSIONS   = {"p7.1"}            # additive-compatible predecessors

_ensure_schema():
  CREATE TABLE IF NOT EXISTS meta …
  stored = SELECT value FROM meta WHERE key='work_units_registry_version'
  if stored is not None and stored not in ({CURRENT} ∪ _SUPPORTED_PRIOR_VERSIONS):
      schema_unsupported = stored; return        # unknown/newer → fail closed (old binary on p7.2 db, etc.)
  # shape guard — EXISTING tables only (a p7.1 db lacking declared_targets is skipped, NOT failed)
  for table, required in _REQUIRED_COLUMNS.items():
      if table exists and not required ⊆ columns(table):
          schema_unsupported = "unknown"; return
  CREATE TABLE IF NOT EXISTS … (all six tables, incl. declared_targets) ; CREATE INDEX IF NOT EXISTS …
  INSERT OR REPLACE INTO meta VALUES('work_units_registry_version', CURRENT)   # fresh→p7.2; p7.1→p7.2 upgrade; p7.2→no-op
```

Properties: **never drops**; a `p7.1` db is migrated **forward** (table created, then meta upgraded to
`p7.2`); the shape guard runs on **existing tables only**, so a pre-migration `p7.1` db is never failed
closed for *lacking* the new table; a malformed *existing* `declared_targets` still fails closed; and an
**older binary still fails closed on a `p7.2` db** (correct direction). This is the additive-migration
template future slices reuse.

## 11. Tool surface (MCP, P5/P6/P7 naming) — three tools

| Tool | Mutates | Purpose |
|---|---|---|
| `rhino_declared_target_declare(intended_path, label?, work_unit_id?)` | P7 | Record intent toward a not-yet-existing anchor; computes `predicted_artifact_id` (no P6 contact). |
| `rhino_declared_target_promote(declared_target_id)` | P7 + P6 | Materialize: register the file through P6, drift-verify, bind. The only transition; idempotent/re-entrant (§6). |
| `rhino_declared_targets(declared_target_id?)` | none | List/inspect with computed `observed` block (§8); no transition. |

All return the P5/P6/P7 `{success, data}` envelope via the existing `_err`. They are **non-routed** (no
`session` targeting) and need **no Rhino** — add all three to `targeting._ALL_KNOWN_TOOLS` **and**
`targeting._META_TOOLS` so the meta-classifier treats them as `requires_rhino=False` at 0/1/many Rhinos
(exactly as the five Slice 1 tools). Wire 3 tool decls + 3 dispatch cases in `server.py` next to the Slice
1 P7 tools (4-surface audit: description / personas / tool-catalog / knowledge per the handler-acceptance
rule).

## 12. Testing (Rhino-independent, mirrors `test_work_units.py`)

Pure logic over SQLite + a real `ArtifactRegistry` over a throwaway temp `artifacts.db` + real temp files
(no Rhino), using the Slice 1 `_p6_with` / `_repoint_p7` / autouse-reset fixtures:

- **Schema + migration:** `declared_targets` created with the six-table set; **additive `p7.1→p7.2`** —
  open a db whose `meta` says `p7.1` and which lacks `declared_targets`; assert the table is created,
  `meta` upgraded to `p7.2`, and `schema_unsupported is None`; malformed existing `declared_targets`
  (missing required columns) → `schema_unsupported`; unknown version → fail closed.
- **declare:** `predicted_artifact_id == artifact_id_for(normalize_path(path))`; `status='declared'`;
  `UNIQUE` second-declare → `success:false` + `declared_target_path_conflict` + `existingDeclaredTargetId`
  (the first row's id; **never** `success:true`); `work_unit_id` validated (`work_unit_not_found`);
  `invalid_path`.
- **promote happy path:** a real temp file at the intended path that is **not** pre-registered → `promote`
  registers it in P6, binds, `status='materialized'`, `bound_artifact_id == predicted`; the P6 registry
  now holds a `present` row for that id.
- **promote not-materialized / unreachable:** declare a path with no file → `promote` →
  `declared_target_not_materialized` (`retryable=true`); status stays `declared`, nothing bound. (Asserts
  promote maps P6's `{success, data}` envelope by `data.code`, not exceptions.)
- **promote drift (deterministic, no symlink):** raw-insert a `declared_targets` row with a deliberately
  **wrong** `predicted_artifact_id`, create the real file, `promote` → `declared_target_path_identity_changed`;
  status stays `declared`.
- **promote idempotency + crash-window recovery:** promote a materialized target again → success, same
  binding; and simulate the §6.1 window (P6 row already registered present, target still `declared`) →
  `promote` completes the bind to `materialized` without error and without a second/duplicate P6 row.
- **materialized non-authoritative:** after materialize, delete the file + `set_state(missing)` in P6 →
  `declared_targets` reports `observed.boundArtifactPresent=false` / `fileState='missing'` while `status`
  stays `materialized` (no demotion).
- **`promotable` honors P6 availability:** with a version-skewed P6, a `declared` row whose file is present
  and path-stable returns `observed.promotable=false`,
  `promotionBlockedReason='artifact_registry_unavailable'`, `p6Available=false` (never a `promotable:true`
  lie); the row still lists (degrade, not fail-closed).
- **declared_targets transitions nothing:** declare (no file) → `observed.promotable=false`,
  `artifactRegistered=false`; create the file → `promotable=true` but `status` still `declared` (proves
  listing never promotes); then `promote` → `materialized`.
- **work-unit join:** declare with `work_unit_id` → both `declared_targets` and
  `rhino_work_units(work_unit_id)` surface the link.
- **tools meta/no-Rhino:** the three new names are in `_ALL_KNOWN_TOOLS` **and** `_META_TOOLS` and
  classify `requires_rhino=False` (extend `test_work_units_tools.py`), plus a `call_tool` dispatch smoke
  for `declare`.
- **Baseline parity** vs `main`: named failed/error sets unchanged both directions (current main baseline
  **64 failed / 41 errors**) — the #220 discipline.

**Optional live smoke (deferrable, adds nothing to P7 logic coverage):** through the reliable harness —
launch an owned Workbench, `declare` an intended master path, save a real `.3dm` there, `promote` →
`materialized` + bound id, `declared_targets` → `boundArtifactPresent:true`. P7 never touches Rhino, so
this proves the P4→P6→P7 chain end-to-end but is **not** required for Slice 2 correctness.

## 13. Decision log

- **Option A only — declared-target lifecycle, planned contracts deferred.** Planned contracts depend on
  this primitive but are not it; building both at once would couple two state machines (target
  materialization + relaxed contract validation) — the same "several hard things at once" shape rejected
  for execution. [user]
- **Stored states are exactly `{declared, materialized}`;** `conflict` / `missing` / `unreachable` / drift
  are observations and results, never stored — Slice 1's "validity is never stored" applied to a new
  noun. [user]
- **`predicted_artifact_id` is a prediction (pure path hash), not proof;** re-verified at promotion,
  never trusted as existence, never injected into P6. [user]
- **Promotion is the only transition** and reuses P6's public `register_artifact()`; two drift checks
  (declared-path recompute + bind verification) fail closed with `declared_target_path_identity_changed`. [Claude]
- **Judgment call #1 accepted — P7→P6 *write* is allowed at promotion** because it is explicit, uses the
  public P6 API, and writes a plain artifact row with **no P7 vocabulary** (the §5.4 invariant holds). [user]
- **Cross-DB non-atomic window accepted and specified (§6.1):** P6-then-P7, crash leaves a real P6 row +
  a still-`declared` target, recovered by **idempotent retry**, **never** by P6 rollback; not a leak
  because P6 carries no P7 vocabulary. [user]
- **`materialized` is non-authoritative for current existence (§7):** it records that the bind once
  succeeded; current truth (`fileState` / `artifactRegistered` / `boundArtifactPresent` / `promotable`)
  is recomputed on read; no demotion. [user]
- **Judgment call #2 accepted — additive `p7.1→p7.2` supported-set migration (§10):** shape guard checks
  existing tables only, then `CREATE TABLE IF NOT EXISTS`, then meta→`p7.2`; never drops; old binary still
  fails closed on a `p7.2` db. Bricking every `p7.1` db for an additive table would be the wrong
  strictness. [user]
- **`UNIQUE(predicted_artifact_id)` — one declaration per intended path;** a second declare fails closed
  with `declared_target_path_conflict` (reject-never-silently-dedupe). [Claude]
- **`work_unit_id` optional but encouraged, validated-if-present, indexed** — the "future outputs of this
  assignment" join is first-class, not an afterthought. [user]
- **`merge_contracts` untouched; no `declared_contracts` table in Slice 2.** [user]
- **Tool name `promote` retained** (action = "materialize this declaration"), defined explicitly in §6;
  `materialize` was the considered alternative to mirror the state name. [user suggestion]
- **`promotable` includes `p6Available`; `promotionBlockedReason` names the first failing precondition** in
  promote's own order — a computed observation must never imply promotion can succeed when a version-skewed
  P6 would block it at the `artifact_registry_unavailable` guard. [user, spec review]
- **Promotion parses P6's `{success, data}` envelope by `data.code`** (not exceptions): the three known
  codes map to P7 codes; an unmapped P6 failure is surfaced verbatim (`declared_target_promotion_failed` +
  `p6Code`), never collapsed to generic. [user, spec review]
- **Second-declare returns `success:false` + `declared_target_path_conflict` + `existingDeclaredTargetId`**
  (`retryable:false`) — a conflict is never a successful declaration. [user, spec review]
