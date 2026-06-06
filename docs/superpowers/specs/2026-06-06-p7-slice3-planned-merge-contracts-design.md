# P7 Slice 3 — Planned Merge Contracts (record a future fan-in graph; activate into strict contracts)

> **Origin:** P7 of the Rook router plane — the fan-in / recomposition half. Slice 1 shipped strict
> `merge_contracts` (record + validate fan-in intent; every source+target a **registered + present** P6
> artifact). Slice 2 shipped `declared_targets` (declare intent toward a master/anchor file before it
> exists; `promote` materializes + binds it to a present P6 artifact). **This slice closes the gap
> between them:** a coordinator can record a *future fan-in graph* over typed refs (real P6 artifacts
> AND P7 declared targets) before every artifact exists, then explicitly **activate** each planned
> contract — one at a time, idempotently, in one atomic P7 transaction — into a strict, present-only
> Slice-1 `merge_contract`. **No merge executes, no geometry enters Rhino, and `merge_contracts` is
> byte-for-byte unchanged.**

## 1. One sentence

Add a separate `planned_merge_contracts` table family that records fan-in intent over **typed refs**
(`artifact:<id>` | `declared_target:<id>`) whose dependency topology is computed over a **canonical
future-artifact identity**, plus an `activate(plannedContractId)` bridge that — once every referenced
declared target has materialized and every referenced artifact is present — resolves the refs to real
P6 artifact ids and, in one atomic P7 transaction, inserts a strict Slice-1 `merge_contract` and stamps
the planned row activated.

## 2. Binding principles

- **The ladder of intent, three rungs.** `declared_targets` = *future artifact identity*;
  `planned_merge_contracts` = *future fan-in intent over typed refs*; `merge_contracts` = *strict
  present-only executable intent*. A later slice = actual Rhino merge execution. Each rung is a distinct,
  separately-stored lifecycle; activation is the one explicit, fail-closed door from the planned rung to
  the strict rung.
- **The strict table stays strict.** `merge_contracts` means "every row is a registered, present P6
  artifact id, period." Planned/future refs **never** leak into it. A future reader never has to ask "is
  this a real contract or a planned one?"
- **Typed refs, canonical topology.** Refs are stored as `(ref_kind, ref_id)`, never packed strings. The
  planned dependency graph is computed over a **canonical `plannedArtifactKey`** (the future artifact id),
  so `declared_target:dt-master` and `artifact:<dt-master's predicted id>` are recognized as the same
  node. Original typed refs are kept for activation/provenance; the canonical key drives ordering + cycles.
- **Activation is one atomic P7 transaction with a durable CAS.** Inside one `BEGIN IMMEDIATE`, the row is
  re-read: already-activated returns the existing strict contract id; still-planned inserts the strict
  contract + stamps the planned row. Two concurrent activations can never create two strict contracts
  ("the row is the lock" — the P4/P5 discipline).
- **Validity is recomputed, never stored.** Record persists only a structurally-valid, acyclic planned
  graph; *activatability* (present/materialized) is recomputed on demand because the world changes.
- **Read-only over P6.** Slice 3 makes **zero** P6 writes: `record` uses the read-only link-bar (only when
  `artifact:` refs are present — §7), `activate`/inspect use the read-only present-bar. The only P7→P6 write
  in the subsystem remains Slice 2's `promote`. Invariant intact: P7 references P6 by artifact_id; **P6 never
  references P7.**

**Main invariant:**

> A planned contract may reference not-yet-present P6 artifacts (registered) and not-yet-materialized P7
> declared targets (existing); only an explicit, fail-closed `activate` — gated on every ref resolving to
> a **present** P6 artifact and guarded by an in-transaction CAS — turns it into a strict, present-only
> `merge_contract` indistinguishable from one created by `rhino_merge_contract_record`.

## 3. Non-goals (hard boundaries)

- **No merge execution.** No worksession/import/linked-model/reference/block/report runs; no geometry
  enters any Rhino document.
- **No change to Slice 1 or Slice 2.** `merge_contracts` / `merge_contract_sources` /
  `record_merge_contract` / `validate_merge_contract` and the declared-target tables/tools are untouched.
- **No P6 writes.** P6 is read-only for resolution (link-bar at record, present-bar at activate/inspect).
- **No planned-contract delete / supersede / edit** in Slice 3 (YAGNI; re-recording yields a new
  `planned_contract_id`). **No batch activation** (coordinator-level sugar; loop over `plannedContractOrder`).
- **No demotion.** Activation is monotonic (`planned → activated`); a since-missing strict artifact is a
  Slice-1 `validate` concern, not a planned-contract regression.

## 4. Architecture

Extends the leaf `mcp_server/src/rook/work_units.py` and its `work_units.db` with **three new tables** and
**three non-routed MCP tools**. Pure logic over SQLite + a read-only P6 lookup. The topo/cycle helpers
(`_contract_graph` / `_contract_cycle`) are already id-space-agnostic and are reused verbatim over
canonical keys; `insert_contract`'s strict insert pattern is reused (extended) by the atomic activation
method. Schema advances `p7.2 → p7.3` via the additive supported-set migration Slice 2 established.

## 5. Schema — three new tables

```sql
CREATE TABLE planned_merge_contracts (
  planned_contract_id   TEXT PRIMARY KEY,          -- "pc-<uuid12>"
  target_ref_kind       TEXT NOT NULL,             -- 'artifact' | 'declared_target'
  target_ref_id         TEXT NOT NULL,             -- artifact_id OR declared_target_id
  merge_kind            TEXT NOT NULL,             -- opaque (reuses MERGE_KINDS)
  refresh_policy        TEXT NOT NULL,             -- opaque (reuses REFRESH_POLICIES)
  status                TEXT NOT NULL,             -- 'planned' | 'activated'
  activated_contract_id TEXT,                       -- NULL while planned; = strict mc-id at activation (idempotency key / CAS)
  activated_at          INTEGER,                    -- NULL while planned
  created_at            INTEGER NOT NULL
);
CREATE TABLE planned_merge_contract_sources (
  planned_contract_id   TEXT NOT NULL,
  source_ref_kind       TEXT NOT NULL,             -- 'artifact' | 'declared_target'
  source_ref_id         TEXT NOT NULL,
  PRIMARY KEY (planned_contract_id, source_ref_kind, source_ref_id)
);
-- Ownership: many-to-many, mirroring Slice 1's work_unit_merge_contracts (NOT a single column).
CREATE TABLE work_unit_planned_merge_contracts (
  work_unit_id          TEXT NOT NULL,
  planned_contract_id   TEXT NOT NULL,
  created_at            INTEGER NOT NULL,
  PRIMARY KEY (work_unit_id, planned_contract_id)
);
CREATE INDEX idx_pmcs_contract ON planned_merge_contract_sources(planned_contract_id);
CREATE INDEX idx_wupmc_wu ON work_unit_planned_merge_contracts(work_unit_id);
```

`REF_KINDS = ("artifact", "declared_target")`. Three `_REQUIRED_COLUMNS` entries added for the fail-closed
shape guard. **Ownership is a join table** because planned contracts are contracts and Slice 1 made strict
contracts many-to-many via `work_unit_merge_contracts`; a single `work_unit_id` column would create an
artificial cardinality difference and lose multi-work-unit provenance at activation. (`declared_targets`
keeps its Slice-2 single-`work_unit_id` column — an intentional, acknowledged asymmetry: a declared target
is one future artifact, a contract is a many-to-many graph edge.)

## 6. Reference model + canonical projection

The tool API takes typed refs as objects `{"kind": "artifact"|"declared_target", "id": "..."}`; stored as
`(ref_kind, ref_id)`. The planned dependency graph is computed over a canonical key:

```
_planned_artifact_key(reg, kind, id) -> (key | None, problem | None):
  kind == 'artifact'        -> (id, None)                       # the artifact id is its own future-artifact key
  kind == 'declared_target' -> dt = reg.get_declared_target(id)
                               (dt.predicted_artifact_id, None) if dt else (None, declared_target_not_found)
  else                      -> (None, invalid_ref_kind)
```

Edge `A -> B` iff `key(target(A)) ∈ { key(s) for s in sources(B) }`, via `_contract_graph`/`_contract_cycle`
unchanged. The key is **invariant across the declared→materialized transition** (because `promote` binds
`bound_artifact_id == predicted_artifact_id`), so the planned graph's *shape* never re-wires as the world
fills in — materialization only flips a node from not-activatable to activatable.

## 7. `record` — the front door (two bars, atomic, acyclic)

`rhino_planned_contract_record(target, sources[], merge_kind, refresh_policy, work_unit_id?)` — every check
before any write; one `BEGIN IMMEDIATE`. Guards P7-unusable always. **P6 is guarded conditionally:** if any
`artifact:` ref is present, P6 must be usable and each `artifact:` ref must be registered (the link-bar); if
**every** ref is `declared_target:`, record proceeds **P7-only** — declared-only future planning is not
blocked by P6 skew. (Activation still always requires P6 usable.)

1. **Well-formed typed refs:** target + each source is `{kind ∈ REF_KINDS, id: non-empty str}` →
   `invalid_argument` / `invalid_ref_kind`.
2. **Structural over canonical keys:** ≥1 source (`empty_sources`); no duplicate source keys
   (`duplicate_planned_source`); target key ∉ source keys (`planned_self_reference`); `merge_kind` /
   `refresh_policy` in vocab (`unknown_merge_kind` / `unknown_refresh_policy`).
3. **Two bars at record** (resolution, not presence):
   - every `declared_target:` ref resolves to an existing declared-target row (`declared_target_not_found`);
   - every `artifact:` ref is **registered** in P6 — the link-bar `_is_registered`, **present NOT required**
     (`artifact_not_registered`). No unregistered ghost refs; declared targets remain the only future-ref
     mechanism.
4. `work_unit_id` if given must exist (`work_unit_not_found`).
5. **Atomic candidate cycle pre-check** over the canonical planned graph (shared `_contract_cycle`) →
   `planned_contract_cycle_detected` + rollback. Then insert `planned_merge_contracts` (status='planned') +
   `planned_merge_contract_sources` + (if `work_unit_id`) one `work_unit_planned_merge_contracts` row — all
   in the one transaction. *No invalid planned graph is ever persisted.*

Re-recording yields a new `planned_contract_id` (no idempotency key at record; Slice-1 posture).

## 8. `activate` — the bridge (one-at-a-time, idempotent, all-blockers, in-tx CAS)

`rhino_planned_contract_activate(plannedContractId)`. Guards P7-unusable + P6-unusable.

**Stored-state invariant** (the idempotency key is `activated_contract_id`, NOT the `status` string):
*valid planned* = `status='planned'` ∧ `activated_contract_id IS NULL` ∧ `activated_at IS NULL`;
*valid activated* = `status='activated'` ∧ `activated_contract_id IS NOT NULL` ∧ `activated_at IS NOT NULL`;
any other combination → `planned_contract_already_invalid` (retryable false). Both the preflight AND the
in-tx CAS classify the row by this invariant — never by `status` alone.

```
load planned (else planned_contract_not_found)
classify(row) by the stored-state invariant:
  valid activated -> return {success:true, data:{plannedContractId, status:'activated',   # rule 1
                              contractId: activated_contract_id, alreadyActivated:true}}
  invalid         -> return {success:false, data:{code:'planned_contract_already_invalid', retryable:false}}
  valid planned   -> continue

blockers = _activation_blockers(reg, planned, p6_available)          # rule 2: ALL blockers, not first-error
  for each ref (target + sources), resolve to a PRESENT P6 artifact id:
    artifact:         _p6_row None        -> artifact_not_registered (no)
                      not present         -> artifact_not_present     (yes)
    declared_target:  row None            -> declared_target_not_found (no)
                      status != materialized -> declared_target_not_materialized (yes)
                      bound_artifact_id NULL -> declared_target_bound_missing (no)            # rule 3
                      bound != predicted     -> declared_target_bound_identity_changed (no)   # rule 3 (split)
                      _p6_row(bound) absent/not present -> declared_target_bound_not_present (yes)  # rule 3 (split)
  + structural re-check of the stored row -> planned_contract_already_invalid (no)            # defensive
  + strict-graph cycle (ONLY when every ref resolves): resolved candidate vs existing merge_contracts -> strict_merge_cycle_detected (no)
if blockers:
    return {success:false, data:{code:'planned_contract_not_activatable',
            blockers:[{code, ref?:{kind,id}, ...}], retryable: all(b.retryable)}}   # nothing written

# all refs resolve to present P6 artifacts -> resolve target + sources to artifact ids:
target_aid  = resolve(target)        # artifact -> id ; declared_target -> bound_artifact_id
source_aids = [resolve(s) for s in sources]
work_unit_ids = reg.work_units_for_planned_contract(plannedContractId)   # ALL ownership links
contract_id, already = reg.activate_planned_contract(                    # rule 4 + 5 + in-tx CAS
    plannedContractId, candidate_contract_id='mc-…', target=target_aid, sources=source_aids,
    merge_kind=…, refresh_policy=…, work_unit_ids=work_unit_ids, now=…)
return {success:true, data:{plannedContractId, status:'activated', contractId,
        alreadyActivated: already, target: target_aid, sources: source_aids, mergeKind, refreshPolicy}}
```

`activate_planned_contract` (the atomic registry method) — **one `BEGIN IMMEDIATE` with a durable CAS:**
```
re-read planned_merge_contracts.{status, activated_contract_id, activated_at} WHERE planned_contract_id=?
classify(row) by the stored-state invariant:
  valid activated -> return (activated_contract_id, True)   # CAS: a peer already activated
  invalid         -> raise PlannedContractInvalid           # -> planned_contract_already_invalid; rollback
  valid planned   -> proceed:
strict-graph cycle pre-check (existing merge_contracts + candidate) -> ContractCycleError -> rollback
INSERT merge_contracts + merge_contract_sources                              # rule 4: pure resolved artifact ids
for wu in work_unit_ids: INSERT OR IGNORE work_unit_merge_contracts          # copy ALL ownership links
UPDATE planned_merge_contracts SET status='activated', activated_contract_id=candidate, activated_at=now
return (candidate, False)
```
The resulting strict row is **indistinguishable from a `record_merge_contract` row**: resolved P6 artifact
ids only, no planned refs (rule 4). The P6 present-check is *before* the tx (cross-db); the P7 transition —
strict insert + ownership copy + planned stamp — is one atomic unit guarded by the in-tx CAS so two
concurrent activations never create two strict contracts (rule 5 + must-fix). The in-tx guard's
`ContractCycleError` is caught by the tool and returned in the **same** `planned_contract_not_activatable`
wrapper as the preflight strict-cycle blocker — `blockers:[{code:"strict_merge_cycle_detected", ...}]`,
`retryable:false`. **`activate`'s failure surface is stable:** an existing planned contract that cannot
activate ALWAYS returns the blocker envelope; the only other failures are `planned_contract_not_found`,
`planned_contract_already_invalid`, and registry-unavailable.

## 9. `rhino_planned_contracts` — the inspector (explicit shape; transitions nothing)

Guards P7-unusable; degrades (not fail-closed) on P6 skew like Slice 2. Shares the single
`_activation_blockers` helper with `activate`.

- **`plannedContractId` given** → exactly that contract + `observed`:
  `{ activatable, blockers, resolvedTargetArtifactId?, resolvedSourceArtifactIds[] }`
  (`resolved*` present only for refs that currently resolve). No graph order.
- **No id** → all planned contracts, each with per-row `observed`, **plus graph-level**:
  `plannedContractOrder` (topo over the canonical planned graph, deterministic tiebreak
  `(created_at, planned_contract_id)` via `lexicographical_topological_sort`), `edges`
  (`{from, to, viaArtifactKey}`), `graphOk`, `graphProblems` (structural + cycle over the whole planned
  graph). `plannedContractOrder` includes **both `planned` and `activated`** rows (each row's `status` is
  shown), so the coordinator walks one stable graph and `activate` stays idempotent for already-bridged rows.

**On P6 skew (either call shape):** `p6Available:false`, the P6-derived `observed` fields are null, AND every
row reports `observed.activatable=false` with `observed.blockers` including
`{code:"artifact_registry_unavailable", retryable:true}` — the coordinator sees the *reason* activation is
impossible, not just null fields (mirroring Slice 2's `promotionBlockedReason:"artifact_registry_unavailable"`).

## 10. Two bars, by ref kind

| Ref | Record-time bar | Activation bar |
|---|---|---|
| `artifact:<id>` | **registered** in P6 (may be missing now) | **present** in P6 |
| `declared_target:<dt>` | dt **row exists** | dt **materialized** ∧ `bound == predicted` ∧ bound **present** |

## 11. Failure taxonomy

| Code | When | retryable |
|---|---|---|
| `invalid_ref_kind` | ref kind ∉ REF_KINDS | no |
| `invalid_argument` | malformed target/sources/args | no |
| `empty_sources` | no sources (reused) | no |
| `duplicate_planned_source` | duplicate source by canonical key | no |
| `planned_self_reference` | target key ∈ source keys | no |
| `unknown_merge_kind` / `unknown_refresh_policy` | not in vocab (reused) | no |
| `artifact_not_registered` | record link-bar / activate (reused) | no |
| `artifact_not_present` | activation present-bar (reused) | yes |
| `declared_target_not_found` | ref to a non-existent dt (reused) | no |
| `declared_target_not_materialized` | dt still `declared` at activation (reused) | yes |
| `declared_target_bound_missing` | dt materialized but `bound_artifact_id` NULL (corrupt) | no |
| `declared_target_bound_identity_changed` | `bound != predicted` (drift/corruption) | no |
| `declared_target_bound_not_present` | bound == predicted but P6 artifact not present | yes |
| `work_unit_not_found` | record with absent `work_unit_id` (reused) | no |
| `planned_contract_not_found` | activate/inspect unknown id | no |
| `planned_contract_cycle_detected` | cycle in the **planned** graph (record) | no |
| `strict_merge_cycle_detected` | candidate cycles the **strict** graph (activate) | no |
| `planned_contract_already_invalid` | persisted row violates the stored-state invariant (§8) or is structurally corrupt (defensive) | no |
| `planned_contract_not_activatable` | activate with ≥1 blocker — wraps `blockers[]`; `retryable = all(b.retryable)` | (aggregate) |
| `work_units_registry_unavailable` / `artifact_registry_unavailable` | version skew (reused) | yes |

## 12. Migration — additive `p7.2 → p7.3` (and `p7.1 → p7.3`)

`WORK_UNITS_REGISTRY_VERSION = "p7.3"`; `_SUPPORTED_PRIOR_VERSIONS = frozenset({"p7.1", "p7.2"})`. Add the
three tables + two indexes + three `_REQUIRED_COLUMNS` entries. Behavior:

- A `p7.2` db → the three planned tables are created additively, meta upgraded to `p7.3`.
- A `p7.1` db (pre-Slice-2) → **both** `declared_targets` (Slice 2) **and** the three Slice-3 tables are
  created additively, meta upgraded straight to `p7.3` (version in the supported-prior set → not failed).
- The **existing-tables-only** shape guard is unchanged: missing additive tables are created; a malformed
  *existing* table (current-version or missing-meta) still fails closed to `schema_unsupported`. Never drops.

## 13. Tool surface (MCP, P5/P6/P7 naming) — three tools

| Tool | Mutates | Purpose |
|---|---|---|
| `rhino_planned_contract_record(target, sources[], merge_kind, refresh_policy, work_unit_id?)` | P7 | Record future fan-in intent over typed refs; two-bar + acyclic; atomic. |
| `rhino_planned_contract_activate(plannedContractId)` | P7 | The bridge: one-at-a-time, idempotent (in-tx CAS), all-blockers, inserts the strict contract + stamps. |
| `rhino_planned_contracts(plannedContractId?)` | none | Inspect (single) or whole-graph (order/edges/graphOk) with computed `activatable`+blockers; transitions nothing. |

All return the P5/P6/P7 `{success, data}` envelope via `_err` (the `not_activatable` shape adds `blockers[]`).
Non-routed, no Rhino — add all three to `targeting._ALL_KNOWN_TOOLS` **and** `_META_TOOLS`. Wire 3 decls + 3
dispatch cases in `server.py` next to the Slice-1/2 P7 tools (4-surface audit). `rhino_work_units` gains a
`plannedContracts` array per unit (via `work_unit_planned_merge_contracts`), mirroring `contracts` /
`declaredTargets`.

## 14. Testing (Rhino-independent, mirrors Slice 1/2)

Real P6 `ArtifactRegistry` over a throwaway temp `artifacts.db` + real temp files + Slice-2 declared targets,
no Rhino (the `_p6_with` / `_repoint_p7` / autouse-reset fixtures):

- **Schema + migration:** three tables created at `p7.3`; **`p7.2→p7.3`** additive (planned tables created,
  meta upgraded); **`p7.1→p7.3`** additive (declared_targets **and** planned tables created, meta → p7.3,
  existing data intact); malformed planned table → fail closed.
- **record:** typed-ref validation (`invalid_ref_kind`); canonical `duplicate_planned_source` /
  `planned_self_reference` (a `declared_target:` and an `artifact:` ref with the same predicted id collide);
  `declared_target_not_found`; artifact link-bar (registered-but-missing **accepted**, unregistered
  **rejected**); atomic canonical cycle pre-check (rejects + nothing written); work-unit link.
- **activate happy path:** declared target materialized + direct artifact present → one strict
  `merge_contract` created (**indistinguishable** from `record_merge_contract`: resolved artifact ids,
  ownership links copied) + planned row stamped `activated` atomically; `validate_merge_contract` then sees
  the strict contract.
- **activate idempotency + CAS:** second `activate` returns the same `contractId` with `alreadyActivated:true`,
  no second strict contract (assert `list_contracts()` count unchanged); a direct in-tx re-read path is
  exercised (simulate an already-stamped planned row → activate returns existing).
- **activate all-blockers:** refs not ready → `planned_contract_not_activatable` with the full `blockers`
  list including `declared_target_not_materialized`, `declared_target_bound_missing` (raw-insert a
  materialized dt with NULL bound), `declared_target_bound_identity_changed` (raw-insert bound != predicted →
  **retryable false**), `declared_target_bound_not_present` (bound == predicted but P6 missing → **retryable
  true**), `artifact_not_present`; aggregate `retryable` = `all(...)`; nothing written.
- **activate strict cycle:** a directly-recorded strict contract that would cycle with the activation →
  `strict_merge_cycle_detected`, nothing written.
- **inspector:** single-id shape (`observed.activatable` + `blockers` + `resolvedTargetArtifactId` +
  `resolvedSourceArtifactIds`); whole-graph `plannedContractOrder` / `edges` / `graphOk` / `graphProblems`;
  **canonical-key edge** across `artifact:` and `declared_target:` for the same future artifact; transitions
  nothing (a planned row stays `planned` after inspection); degrades on P6 skew.
- **work-unit join:** record with `work_unit_id` → `rhino_work_units` shows `plannedContracts`; after
  activation the strict contract carries the same ownership in `work_unit_merge_contracts`.
- **conditional P6 guard at record:** an all-`declared_target:` planned contract records successfully under a
  version-skewed P6 (P7-only); a planned contract with any `artifact:` ref under skewed P6 →
  `artifact_registry_unavailable`.
- **invalid stored-state guard:** a raw-inserted row violating the invariant (e.g. `status='activated'` with
  `activated_contract_id` NULL) → both `activate` and the inspector report `planned_contract_already_invalid`
  (never a null-contract "success").
- **inspector P6 skew:** under skewed P6 every row's `observed.activatable=false` with a
  `{code:"artifact_registry_unavailable", retryable:true}` blocker and `p6Available:false`.
- **order includes activated rows:** after activating one contract, whole-graph `plannedContractOrder` still
  lists it (with `status:'activated'`) in stable position.
- **Baseline parity** vs `main`: named failed/error sets unchanged both directions (current main **64 failed /
  41 errors**) — the #220 discipline, blessed non-live gate.

**Optional live smoke (deferrable):** declare a master + a leaf, save+promote them, record a planned contract
(`declared_target:` master ← `artifact:` leaf + `declared_target:` other), activate once both materialize →
strict contract + `contractOrder`. P7 never touches Rhino, so this proves the P4→P6→P7 chain but is not
required for Slice 3 correctness.

## 15. Decision log

- **Separate `planned_merge_contracts` family — `merge_contracts` untouched.** The strict table's "every row
  is registered+present" invariant is high-value; planned/future refs must not erode it. [user]
- **Typed `(ref_kind, ref_id)` refs + canonical `plannedArtifactKey` topology** (artifact → id; declared
  target → predicted_artifact_id) — kept-typed for activation/provenance, canonical for ordering/cycles;
  invariant across declared→materialized. [user]
- **Option A activate:** one-at-a-time, idempotent via `activated_contract_id`, all-blockers, **in-tx CAS**
  (re-read inside `BEGIN IMMEDIATE` — never two strict contracts), `bound_artifact_id` with a
  `== predicted` guard, pure resolved artifact ids into the strict tables. Batch is coordinator sugar
  (deferred). [user]
- **Ownership is a join table** (`work_unit_planned_merge_contracts`), mirroring strict-contract
  many-to-many; activation copies all links into `work_unit_merge_contracts`. Declared targets keep their
  single-column Slice-2 choice (intentional asymmetry). [user, must-fix]
- **Split corrupt bound-id from not-present:** `declared_target_bound_identity_changed` (retryable false) vs
  `declared_target_bound_not_present` (retryable true) vs `declared_target_bound_missing` (false). [user, must-fix]
- **Distinct cycle codes:** `planned_contract_cycle_detected` (planned graph, record) vs
  `strict_merge_cycle_detected` (strict graph, activate) — different remediation. [user, must-fix]
- **3 tools; inspector folds order + activatable** (no separate `validate`), explicit single-vs-whole-graph
  output shape. [user]
- **Record two-bar:** `artifact:` registered (link-bar, present not required), `declared_target:` exists;
  present/materialized deferred to activation. No unregistered ghosts. [user]
- **Slice 3 makes zero P6 writes** (read-only link/present bars); the lone P7→P6 write stays Slice 2
  `promote`. [Claude]
- **Additive `p7.3` migration** (supported-set `{p7.1, p7.2}`); a `p7.1` db gains both declared_targets and
  the planned tables; existing-tables-only shape guard, never drops. [user]
- **Stored-state invariant** (`planned` = all-null activation fields; `activated` = all-set) classifies rows
  at preflight AND in-tx CAS; any other combination → `planned_contract_already_invalid`. The idempotency key
  is `activated_contract_id`, never `status` alone. [user, spec review]
- **`activate` failure surface is stable:** an existing-but-unactivatable contract ALWAYS returns the
  `planned_contract_not_activatable` blocker envelope — including the in-tx TOCTOU strict cycle. [user, spec review]
- **Inspector surfaces the P6-skew reason:** `observed.activatable=false` + an `artifact_registry_unavailable`
  blocker, not just null fields (Slice-2 parity). [user, spec review]
- **Record's P6 guard is conditional:** required only when `artifact:` refs are present; all-`declared_target:`
  planning proceeds P7-only under P6 skew. [user, spec review]
- **`plannedContractOrder` includes both `planned` and `activated` rows** (status per row) — one stable graph;
  `activate` idempotent for bridged rows. [user, spec review]
- **No delete/supersede/batch/demotion** (YAGNI). [Claude]
