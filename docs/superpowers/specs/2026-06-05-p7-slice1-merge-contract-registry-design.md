# P7 Slice 1 — Merge-Contract Registry (record + validate fan-in intent)

> **Origin:** P7 of the Rook router plane — the fan-in / recomposition half. The prerequisite
> stack is coherent: P1 sees sessions, P2 tells the truth about failures, P3 routes by session,
> P4 creates disposable Workbenches, P5 remembers ownership, P6 Slice 1 remembers artifacts, and
> #218/#222 made the tool + live-smoke surface reliable. P7 Slice 1 is the first fan-in brick:
> **record merge intent + validate merge contracts — perception and durable intent before action**
> (analogous to P1/P6). **No merge is executed; no geometry enters Rhino.**

## 1. One sentence

Add a coordinator-plane registry that records **Work Units**, links the durable P6 artifacts they
produce/consume, and records **Merge Contracts** (a dependency DAG of `sources → target`) — then
**validates** that a contract is well-formed and references only currently-present P6 artifacts,
returning the **topological order in which the coordinator would recompose** — all without
executing any merge.

## 2. Binding principles

- **Intent before action.** P7 Slice 1 records and validates; it never imports/attaches/worksessions
  geometry, never schedules execution, never mutates a Rhino document.
- **Reference-only across planes.** P7 references P6 artifacts by `artifact_id`; **P6 never
  references P7 work units** (no schema change to P6; the lower plane never learns the coordinator's
  vocabulary — §5.3 of the north-star topology).
- **No ghost artifacts.** Every *persisted* reference resolves to a registered P6 artifact currently
  marked `present`. This is enforced at **record** time AND re-checked at **validate** time.
- **Validation is pure and on-demand.** Validity is never stored as a status — it is recomputed each
  call, because file state can change after a contract is recorded. The verdict is binary and honest.
- **Opaque strategies.** `merge_kind` / `refresh_policy` are *declared* coordinator vocabulary for
  well-formedness — **not** executable Rhino command names. Slice 1 promises no execution semantics.

**Main invariant:**

> P7 stores coordinator intent only, but every *persisted* merge contract must reference only
> currently-present P6 artifacts; later validation recomputes truth and may fail if the world changed.

## 3. Non-goals (hard boundaries)

- No merge execution: no worksession/import/linked-model/reference/block/report is *run*; no geometry
  enters any Rhino document.
- No mutation of P6: the artifact registry is read **read-only** for resolution; never written.
- No "planned" / "declared" / "future" artifacts: all referenced artifacts must already exist and be
  present. A planned-master state machine is a **later slice**, explicitly out of scope.
- No coordinator scheduling, retries, or conflict resolution.
- No change to session routing (P3), registry semantics (P5), artifact perception (P6), or launch (P4/#222).

## 4. Architecture — a coordinator-plane registry

A new leaf module `mcp_server/src/rook/work_units.py` owning a durable SQLite store in a **separate
file** `work_units.db` (mirrors P5 `owned_sessions.db` / P6 `artifacts.db`):

- Resolution: `%LOCALAPPDATA%/Rook/registry/work_units.db`, falling back to
  `%TEMP%/rook/registry/work_units.db` (verbatim shape of `resolve_artifact_db_path`).
- Connection: `BEGIN IMMEDIATE` + WAL + `busy_timeout`, schema **additive / version-gated /
  fail-closed (never DROP)** — the `_ImmediateTx` + `_ensure_schema` pattern copied from
  `artifacts.py` (duplication accepted; no shared base in Slice 1).
- The store reads P6 artifacts through the existing `ArtifactRegistry` (a read-only resolution call);
  it never opens or mutates `artifacts.db` directly.

**Altitude:** Work Unit + Merge Contract are coordinator-plane (what the coordinator *intends*),
kept in their own registry — distinct from the orchestration-plane Session (P5) and Artifact (P6)
registries. This store is Rhino-independent: it is pure logic over SQLite + a read-only P6 lookup.

## 5. Schema — five tables, many-to-many throughout

```sql
-- 1. The Work Unit node (coordinator assignment)
CREATE TABLE work_units (
  work_unit_id TEXT PRIMARY KEY,   -- coordinator-supplied slug ("facade-study") or generated
  label        TEXT NOT NULL,
  role         TEXT,               -- free text: what this assignment is
  metadata     TEXT,               -- opaque JSON (constraints / expected-output); not interpreted in Slice 1
  created_at   INTEGER NOT NULL
);

-- 2. Provenance: which work unit produced/consumed which P6 artifact (many-to-many)
CREATE TABLE work_unit_artifacts (
  work_unit_id TEXT NOT NULL,
  artifact_id  TEXT NOT NULL,      -- P6 artifact_id (REFERENCE only — no FK into artifacts.db)
  relation     TEXT NOT NULL,      -- "produced" | "consumed"
  created_at   INTEGER NOT NULL,
  PRIMARY KEY (work_unit_id, artifact_id, relation)
);

-- 3. The Merge Contract (hyperedge: N sources -> 1 target, with a declared strategy)
CREATE TABLE merge_contracts (
  contract_id        TEXT PRIMARY KEY,   -- generated
  target_artifact_id TEXT NOT NULL,      -- P6 artifact_id (the master/consumer)
  merge_kind         TEXT NOT NULL,      -- opaque declared strategy (§6)
  refresh_policy     TEXT NOT NULL,      -- opaque declared ordering hint (§6)
  created_at         INTEGER NOT NULL
);

-- 4. The contract's source artifacts (the inputs of the hyperedge)
CREATE TABLE merge_contract_sources (
  contract_id       TEXT NOT NULL,
  source_artifact_id TEXT NOT NULL,      -- P6 artifact_id
  PRIMARY KEY (contract_id, source_artifact_id)
);

-- 5. Which work unit(s) a contract serves (many-to-many) — keeps the graph fully connected
CREATE TABLE work_unit_merge_contracts (
  work_unit_id TEXT NOT NULL,
  contract_id  TEXT NOT NULL,
  created_at   INTEGER NOT NULL,
  PRIMARY KEY (work_unit_id, contract_id)
);
```

`work_unit_artifacts` (provenance: *who produced/consumed*) and `merge_contract_sources` (the merge
edge: *what feeds this target*) are orthogonal — an artifact produced by work unit W can be a source
in contract C without redundancy.

## 6. Declared strategies (opaque vocabulary, NOT executable)

- `merge_kind ∈ { worksession, import, linked_block, reference, block, report }` — the north-star's
  composition primitives, captured as **intent vocabulary** for well-formedness. These overlap
  conceptually (e.g. `reference` / `worksession` / `linked_block`); that is acceptable because Slice 1
  is pure vocabulary capture. **They are not Rhino command names and carry no execution semantics.**
- `refresh_policy ∈ { refresh_after_save, refresh_on_demand }` — the per-contract ordering hint.

Validation checks only that the value is in the declared set (`unknown_merge_kind` /
`unknown_refresh_policy` otherwise). The vocabulary may grow in later slices; no value implies a runnable action.

## 7. `record` — present-bar enforced at write

`rhino_merge_contract_record(target_artifact_id, source_artifact_ids[], merge_kind, refresh_policy,
work_unit_id?)` — **every check runs BEFORE any write; the write is one atomic transaction:**

1. **Local well-formedness:** `source_artifact_ids` non-empty (`empty_sources`); **no duplicate source
   ids — duplicates are rejected, never silently deduped (`duplicate_contract_source`)**; `merge_kind` /
   `refresh_policy` in vocabulary (`unknown_merge_kind` / `unknown_refresh_policy`); target ∉ sources
   (`merge_self_reference`).
2. **Present-bar (same as validate):** every source AND the target resolves to a P6 row
   (`artifact_not_registered` else) currently `present` (`artifact_not_present` else). A shared
   `_resolve_present(artifact_ids) -> problems[]` helper backs both `record` and `validate`.
3. If `work_unit_id` is given, it must exist (`work_unit_not_found`).
4. **Atomic, all-or-nothing:** only after ALL of 1–3 pass clean does a single `BEGIN IMMEDIATE`
   transaction insert the `merge_contracts` row + every `merge_contract_sources` row + the optional
   `work_unit_merge_contracts` join. On ANY failure the `_err(<code>, …)` envelope is returned and
   **no partial contract row or source rows exist** (the transaction never opens).

Re-recording the same logical contract creates a **new `contract_id`** — Slice 1 invents **no
idempotency key** (add one later only if a caller actually needs dedupe). **Acyclicity is NOT checked
at record** — a cycle is an emergent property of the whole graph and is a `validate`-time concern.

## 8. `validate` — pure, on-demand; returns the recompose order

`rhino_merge_contract_validate(contract_id?)`:

- **`contract_id` given:** validate that one contract — re-run the present-bar (file state may have
  changed since record) + local structural checks; report whether it participates in a cycle.
- **No `contract_id`:** validate the **whole graph** and return the recompose ordering.

**Checks** (problems accumulate; each is `{code, contract_id?, artifact_id?, detail}`):
- Present-bar re-check on every contract's sources + target (`artifact_not_registered` /
  `artifact_not_present`).
- Structural: `empty_sources`, `merge_self_reference`, `unknown_merge_kind`, `unknown_refresh_policy`.
- **Acyclicity + ordering over the CONTRACT dependency graph.** The precedence rule is explicit:
  **Contract A precedes Contract B when `target_artifact_id(A)` appears in `sources(B)`** (nodes =
  contracts; directed edge `A → B`). A cycle → `merge_cycle_detected` with the contract cycle path.
  The topological sort is **deterministic**: contracts with no path between them are independent and
  ordered by a stable tiebreak `(created_at, contract_id)`, so `contractOrder` is reproducible and
  tests are not flaky. (Cycle detection + a stable topological sort via the existing `networkx`
  dependency — e.g. `lexicographical_topological_sort` keyed by the `(created_at, contract_id)` tiebreak.)

**Success output** (`{success: True, data: {…}}`):
```jsonc
{
  "ok": true,
  "contractOrder": ["contract_3", "contract_1", "contract_2"],   // LOAD-BEARING: apply in this order
  "artifactOrder": ["A", "B", "site-master"],                    // secondary: artifact topo-order
  "edges": [{"from": "contract_3", "to": "contract_1", "viaArtifact": "B"}],  // explanation
  "contracts": [{"contract_id": "...", "target": "...", "sources": ["..."],
                 "mergeKind": "linked_block", "refreshPolicy": "refresh_after_save"}]
}
```

**Failure output:** `{success: True, data: {"ok": false, "problems": [{"code": "...", ...}]}}` — a
*well-formed validate call that found problems* is a successful call returning `ok:false` (mirrors P6).
A malformed *request* (e.g. `contract_id` not found) returns `_err("contract_not_found", …)`.

## 9. Tool surface (MCP, P5/P6 naming) — five tools

| Tool | Purpose |
|---|---|
| `rhino_work_unit_register(label, role?, metadata?, work_unit_id?)` | Create a work unit (generated id if none given). |
| `rhino_work_unit_link_artifact(work_unit_id, artifact_id, relation)` | Link a P6 artifact as `produced`/`consumed`. Requires the artifact to be **registered** in P6 (`artifact_not_registered`); provenance is historical, so a since-missing artifact is still a valid link — **`present` is NOT required for a link**, only for merge-contract references (§7). |
| `rhino_merge_contract_record(target_artifact_id, source_artifact_ids[], merge_kind, refresh_policy, work_unit_id?)` | Record a contract; present-bar enforced at write (§7). |
| `rhino_merge_contract_validate(contract_id?)` | Validate one contract, or the whole graph → `contractOrder` (§8). Also the graph inspector. |
| `rhino_work_units(work_unit_id?)` | List/inspect work units with their linked artifacts AND contracts — answers "what fan-in intent belongs to this assignment?" |

All return the P5/P6 `{success, data}` envelope via a local `_err`. Registry-unusable (schema version
skew) fails closed exactly as P5/P6 (`registry_schema_unsupported`). These are coordinator-plane
read/record tools; they are **non-routed** (no `session` targeting) and need no Rhino — add them to
`targeting._ALL_KNOWN_TOOLS` so the meta-classifier treats them correctly at 0/1/many Rhinos.

## 10. Testing

**Slice 1 is Rhino-independent** (pure logic over SQLite + a read-only P6 lookup), so the primary
coverage needs **no Rhino**:

- **Unit (`test_work_units.py`):** schema bootstrap (additive / version-gated / fail-closed, mirroring
  P5/P6 tests); work-unit register + many-to-many artifact/contract links; `record` present-bar
  (reject not_registered / not_present at write); `record` local structural rejects (empty_sources,
  `duplicate_contract_source`, self_reference, unknown kind/policy); **`record` atomicity — a failing
  record (e.g. one missing source) leaves NO contract/source/join rows**; `validate` matrix — valid
  graph; not_registered / not_present re-check after the world changes; `merge_self_reference`;
  `merge_cycle_detected` (two- and three-contract cycles); **`contractOrder` correctness AND
  determinism** for a multi-stage fan-in (A,B → M1; M1,C → master) **including independent contracts
  ordered by the `(created_at, contract_id)` tiebreak (run twice → identical order)**; the
  work-unit-centric query returns the right artifacts + contracts. Uses a real `ArtifactRegistry` over
  a throwaway temp `artifacts.db` + real temp files (no Rhino).
- **Baseline parity** vs `main` (named failed/error sets unchanged) — the #220 discipline.
- **Optional end-to-end live smoke (deferrable):** `--smoke p7-merge-contract` through the now-reliable
  harness — launch an owned Workbench, save 2 real source `.3dm` + 1 master, register them in P6,
  register a work unit + link, record a 2-source contract, validate → `ok` + `contractOrder`;
  deregister a source in P6 → re-validate → `artifact_not_registered`. This proves the P4→P6→P7 chain
  but adds nothing to P7's own logic coverage (P7 never touches Rhino), so it is **optional** for
  Slice 1 — include it for end-to-end confidence, skip it without loss of P7 correctness.

## 11. Decision log

- **Linkage = coordinator-plane join, P6 untouched.** Invariant: P7 references P6 by `artifact_id`;
  P6 never references P7. Preserves §5.3 altitude + P6's "artifact perception only" scope; many-to-many
  without regret. [user]
- **Present-bar = all referenced artifacts (sources + target) registered AND `present`.** No
  planned/declared artifacts in Slice 1; the master is the pre-existing Attached/anchor doc, which must
  already be a registered+present P6 artifact. Codes: `artifact_not_registered` / `artifact_not_present`,
  applied equally to sources and target. [user]
- **`record` enforces the same present-bar as `validate`** (no ghost artifacts via the record door);
  `validate` re-checks because file state can change. [user]
- **Merge Contract = hyperedge (Approach A):** `merge_contracts` + `merge_contract_sources`; the
  contract is the addressable unit. Rejected flat `merge_edges` (loses the N→1 grouping) and in-memory
  (violates durable intent). [Claude, endorsed]
- **`contractOrder` is the load-bearing validate output** (topo over the contract dependency graph),
  with `artifactOrder` + edges as explanation; cycle detection on the contract graph. The validator
  returning the recompose order is the Slice-1 payoff — fan-in *perception* without executing a merge. [user]
- **5th table `work_unit_merge_contracts`** so the provenance graph isn't half-connected — "what fan-in
  intent belongs to this assignment?" is a query, not an inference. [user]
- **`merge_kind` / `refresh_policy` are opaque declared strategies**, not executable Rhino command
  names; no execution semantics promised. [user]
- **Validation is pure / on-demand / never stored** — recomputed each call to avoid staleness. [Claude]
- **Two bars, by intent:** a *provenance link* (`work_unit_artifacts`) requires only that the artifact
  is **registered** (provenance is historical — a since-missing artifact was still produced); a *merge
  reference* (`record`/`validate`) requires **present** (you cannot merge a missing file). [Claude, self-review]
- **`record` is atomic / all-or-nothing:** all checks run before any write; one `BEGIN IMMEDIATE`
  transaction inserts contract + sources + optional join; no partial rows on failure. Duplicate source
  ids in one contract are **rejected** (`duplicate_contract_source`), never silently deduped.
  Re-recording creates a new `contract_id`; no idempotency key in Slice 1. [user]
- **Deterministic topo order:** precedence is "A precedes B when `target(A)` ∈ `sources(B)`";
  independent contracts tiebreak on `(created_at, contract_id)` so `contractOrder` is reproducible
  (non-flaky tests). [user]
