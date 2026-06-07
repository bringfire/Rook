# P7 Slice 5 — Chained Linked-Block Recomposition (proof/harness)

- **Date:** 2026-06-07
- **Status:** Design — converged through a Rook ⇄ user ⇄ Codex brainstorm. Pending spec review before plan.
- **Author:** Claude (synthesis of the brainstorm; the full-graph-filtered ordering correction is the user's, verified at source).
- **Area:** `mcp_server/src/rook/work_units.py` (one pure helper + one shared-ordering factor); `mcp_server/tests/` (offline unit tests + one `requires_rhino` live harness). **No native, no `server.py`, no `targeting.py`, no new tool.**
- **Relationship to other docs:**
  - Sits on top of `docs/superpowers/specs/2026-06-07-p7-linked-block-executor-design.md` (Slice 4 — the per-contract executor `rhino_merge_contract_execute`) and the strict `merge_contracts` registry (Slice 1).
  - Realizes the fan-in proof named in `docs/superpowers/specs/2026-06-03-rook-north-star-topology.md` §5.5 (the Save membrane) and §8 (fan-in is serialized on dependencies). This is the first time chained recomposition is exercised against real Rhino.

---

## 1. Why this slice exists

The per-contract linked-block executor (Slice 4) and the deterministic contract-DAG order (`validate_merge_contract` → `_validate_graph` → `contractOrder`) are both merged and proven *individually*. What has **never** been observed is the two composing across a dependency chain:

> sources `s1, s2` → **intermediate** → **master**, where the intermediate is contract A's *target* and contract B's *source*, producing **nested** linked blocks in the master (`master → intermediate → s1/s2`).

That composition lands squarely on the north-star's single most fragile seam — the **Save membrane** (§5.5): the instant contract A saves the intermediate `.3dm`, that file becomes contract B's link source. Rhino's nested-linked-block refresh-after-save behavior, the `sourcePath` forms it records, and any file-lock / stale-read symptom across save→consume are **unknowns we must observe before freezing any public graph-execution contract.**

Therefore this slice is a **proof/harness**, not a tool. Its job is to (a) assert that the existing primitives compose on the claims we are confident about, and (b) *characterize* the nested-refresh behavior as input to a future tool slice.

## 2. Scope — what this slice is and is not

**Is:**
- One narrow, pure, Rhino-free ordering helper in `work_units.py`, unit-tested offline (green in CI).
- One `requires_rhino` live regression proving chained/nested recomposition end-to-end.
- A written record of the observed Save-membrane / nested-link behavior.

**Is not:**
- `rhino_merge_contract_execute_order` or any graph-execution **tool** (deferred; its shape is an *output* of this slice's observations).
- An extension of `rhino_merge_contract_execute` (its clean single-target-identity gate must not be overloaded with multi-target sequencing).
- A change to native C++, `server.py`, `targeting.py`, or the MCP tool surface.
- Owned-Workbench / multi-session concurrency (no P5 / `#222` launcher variables). One Rhino, document-switched by the harness.

## 3. Component 1 — the pure ordering helper (the only production code)

### 3.1 One source of truth for contract order

Factor the ordering out of `_validate_graph` into a shared pure function, so there is exactly one topological-sort implementation:

```python
def _ordered_contract_ids(pairs, order_key):
    """The ONE source of truth for strict-contract execution order. pairs: list of
    (contract_id, target_artifact_id, sources_list); order_key: cid -> (created_at, contract_id).
    Returns (order, None) on success or (None, cycle) on a cyclic graph. Reused by
    _validate_graph (whole graph) and plan_linked_block_execution (scoped, but ordered over
    the whole graph)."""
    g, _, _ = _contract_graph(pairs)
    try:
        return list(nx.lexicographical_topological_sort(g, key=lambda n: order_key[n])), None
    except nx.NetworkXUnfeasible:
        return None, _contract_cycle(pairs)
```

`_validate_graph` is refactored to call it and is **output-identical** (a regression/parity check guards this):

```python
    contract_order, cycle = _ordered_contract_ids(pairs, order_key)
    if cycle is not None:
        problems.append({"code": "merge_cycle_detected", "cycle": cycle})
```

### 3.2 `plan_linked_block_execution` — scoped, but ordered over the full graph

```python
def plan_linked_block_execution(reg, contract_ids):
    """Pure, Rhino-free. Derive the deterministic linked-block execution plan for a requested
    subset of strict contracts. Order is computed over the WHOLE contract graph and then
    filtered to the requested ids (NOT over a scoped subgraph — a scoped subgraph drops
    transitive edges through omitted contracts and can invert order). Consumes contract ids,
    not sessions. Does NOT execute, inspect Rhino, check the present-bar, or define any
    execution-result envelope."""
```

Algorithm:
1. **Gate requested ids** (collect all problems, `_validate_*` style — plain `{"code", ...}` dicts, not `_err` envelopes):
   - `reg.get_contract(cid) is None` → `{"code": "contract_not_found", "contractId": cid}`
   - `contract.merge_kind != "linked_block"` → `{"code": "unsupported_merge_kind", "contractId": cid, "mergeKind": contract.merge_kind}`
   - If any problems → `return {"ok": False, "problems": problems}`.
2. **Order over the whole graph:** build `pairs` from `reg.list_contracts()` (each `(cid, target_artifact_id, reg.sources_for(cid))`) and `order_key[cid] = (created_at, contract_id)`; call `_ordered_contract_ids`.
3. **Defensive cycle:** the graph is acyclic-by-construction (`insert_contract` rejects cycles atomically), so this never fires in practice; if it does → `return {"ok": False, "problems": [{"code": "merge_cycle_detected", "cycle": cycle}]}` (fail closed).
4. **Filter, preserving global order:** `plan = [{"contractId": cid, "targetArtifactId": target_of[cid]} for cid in full_order if cid in requested_set]`.
5. `return {"ok": True, "plan": plan}`.

Empty / duplicate requested ids: dedupe to a set; an empty set yields `{"ok": True, "plan": []}` (no special-casing).

### 3.3 Omitted-producer policy: **allow** (with rationale)

If a requested contract depends — directly or transitively, in the full graph — on a contract **not** in the requested set, the plan still orders the requested ids correctly and raises **no** problem. This is not merely "narrower"; it is **more correct**: a pure orderer has no basis to decide whether the upstream artifact will be produced by an omitted contract versus is already present on disk. **Artifact availability is the executor's strict present-bar, evaluated against live P6/disk state at execution time** — so a genuinely missing intermediate fails closed *there*, where the authority lives, not in a pure planner guessing about the future.

Consequently this slice **declines** both `dependency_not_requested` (fail-closed) and upstream-producer reporting. The whole graph is already built, so direct-producer reporting is a one-line `g.predecessors(cid)` addition if a future coordinator needs it surfaced — but it is out of scope here to keep the helper a pure order+gate, not a scheduler.

### 3.4 Where it lives and why

`work_units.py`, next to `_contract_graph` / `_ordered_contract_ids` / `_validate_graph`. It needs the contract-DAG machinery; putting it in the pure `linked_blocks.py` would force a `work_units` import (breaking that module's purity) or a duplicate graph implementation — the exact second-implementation this design forbids. It is a module-level function (no leading underscore) so the harness and offline tests import it cleanly; it is **internal** — not wired as an MCP tool this slice.

## 4. Component 2 — the live harness (`tests/test_merge_contract_chain_live.py`, `requires_rhino`)

### 4.1 Hermetic registries

Monkeypatch `work_units.resolve_work_units_db_path` and `artifacts.resolve_artifact_db_path` to temp files and reset the registry singletons (same shape as the offline `temp_registries` fixture). The in-process contract graph is then exactly `{A, B}` — so the scoped plan is unambiguous — and the test does not pollute the real P6/P7 stores (the Slice-4 live test wrote to the real DBs and left dangling not-present rows when it deleted its files; this slice creates four artifacts, so hermeticity is the right hygiene). Rhino is a separate process and never reads these DBs.

### 4.2 Flow (one Rhino; harness switches the active document)

Per the standing fixture rule, the live test confirms a throwaway Rhino document context (`fresh_document`) before mutating, and only runs when Rhino is reachable (skips cleanly otherwise).

1. Create + save `s1`, `s2`, `intermediate`, `master`: for each, `rhino_document_ops(action="new")` → `rhino_create` a distinguishing box → `rhino_document_ops(action="save", path=…)`. P6-register each via `artifacts.register_artifact` and capture its `artifactId`.
2. Record contract **A** = `[s1, s2] → intermediate` and **B** = `[intermediate] → master`, both `merge_kind="linked_block"`, `refresh_policy="refresh_on_demand"`, via `work_units.record_merge_contract`. Capture `cid_A`, `cid_B`.
3. `plan_linked_block_execution(reg, [cid_A, cid_B])` → **assert** ordered plan `== [(cid_A, intermediate_id), (cid_B, master_id)]`.
4. Select the live session `S` (assert exactly one live Rhino; reject ambiguity). For each plan step in order: `rhino_document_ops(action="open", path=target_path)` (makes it the active document on `S`) → `rhino_merge_contract_execute(contractId=cid, session=S, expectedMergeKind="linked_block")` → **immediately assert that step's created defs while its target is still active** (§5: `created_link` + `saved` + each `name(cid, sid)` resolves `isLinked` by `rhino_block_info` on `S`). Per-step interleaving is **required** because Rhino holds one document per window — opening the next step's target closes the previous one, so its block table is no longer readable on `S` without a reopen.
5. Idempotent re-run: for each plan step in order, while its target is active snapshot the expected deterministic-name set, then re-open + re-execute and assert outcome `refreshed_existing` + `saved` + the name set unchanged (§5 no-dup).
6. Record observations (§6) — including a final close+reopen of `master` for the `sourcePath` / nested-view characterization — and clean up temp files in `finally`.

`open` → `POST /document/open`; Rhino's single-document model makes the opened file the active document, which the executor's session→active-doc identity gate then resolves to. With one Rhino, ambient routing for `open`/`save` and the explicit `session` on `execute` address the same instance. Because Rhino holds one document per window, opening `master` closes `intermediate`, so in this topology **B consumes the intermediate from a closed, on-disk file** (see §7).

## 5. Hard assertions (tied to our deterministic naming, not Rhino's table presentation)

Let `name(cid, sid) = linked_blocks.block_def_name(cid, sid)`.

- Scoped plan/order `== [cid_A, cid_B]` (Component 1, offline-independent of Rhino).
- **Execute A:** outcome `created_link`; intermediate `saved`. On session `S` (active doc = intermediate): `rhino_block_info(name(cid_A, s1_id))` and `rhino_block_info(name(cid_A, s2_id))` each exist and report `isLinked == True`.
- **Execute B:** outcome `created_link`; master `saved`. On session `S` (active doc = master): `rhino_block_info(name(cid_B, intermediate_id))` exists and `isLinked == True`. The master's deterministic def is keyed on **B's source = the intermediate's artifact id**, never on `s1`/`s2` — this asserts master consumes the intermediate, not the raw sources.
- **Idempotent re-run:** outcomes `refreshed_existing` (both contracts, `refresh_on_demand`); both `saved`. **No duplicate definitions, via our naming, not table counts:** per target doc, the expected deterministic-name set (intermediate → `{name(A,s1), name(A,s2)}`; master → `{name(B,intermediate_id)}`) each resolves once by `rhino_block_info`, and that set is unchanged before vs. after the re-run for the doc under test. Total `/blocks` counts are **not** asserted (Rhino may surface nested source defs — an observation, §6).

Rationale: deterministic `block_def_name` is a contract Rook owns; the flat-vs-nested `/blocks` presentation is exactly the quirk this slice exists to observe. Hard assertions bind to the former.

## 6. Recorded observations (logged, non-failing — the membrane unknowns)

Captured into the test output / spec follow-up / memory; they do **not** fail the test:

- The exact `sourcePath` form Rhino records per linked def (absolute vs. relative; how the intermediate's path appears *inside* master), **after save** and **after a close+reopen of master**.
- Whether master's nested view reflects A's re-refresh of the intermediate on the idempotent pass — **nested-refresh propagation is observed, not asserted.** We have never watched Rhino do nested linked-block refresh-after-save; asserting a specific propagation outcome now risks encoding a wrong expectation, which is the over-freezing this slice exists to avoid.
- Whether `/blocks` surfaces nested source defs globally (flat table includes `name(A,s1)` etc. when master is active).
- Any file-lock / stale-read symptom across the save→consume handoff.

## 7. Scope notes and explicit deferrals

- **Single-Rhino doc-switching observes save→consume-from-disk.** Because opening `master` closes `intermediate`, the intermediate is a closed on-disk file when B consumes it — so the save→consume-**while-still-open** file-lock case cannot appear in this topology. That is the *smaller* test of the membrane, deliberately. The while-open lock case belongs to a future **two-owned-Workbench** slice and is deferred here.
- **The future graph-execution tool** (`execute_order`), its session map (`{targetArtifactId: session}`), and any partial-success / outcome-aggregation envelope are all deferred — their shape is an output of this slice's observations. In particular, partial-success semantics (executed-prefix durability when a later contract fails) are **characterized live, not frozen in code** this round.

## 8. Test plan

**Offline (`tests/test_work_units.py`, no Rhino, green in CI):**
1. `plan_linked_block_execution` happy path: a 2-contract chain `A→B` (B consumes A's target) → plan `== [A, B]` with correct `targetArtifactId`s.
2. **Unrelated-contract isolation:** an unrelated contract `D` elsewhere in the global graph — including one whose source is unregistered/not-present — does **not** alter the requested `[A,B]` plan or order. (The helper does not consult the present-bar, so this holds by construction; the test pins it.)
3. **Transitive omitted-dependency (regression for the inverted-order bug):** insert `A→C→B` (`C.sources=[target(A)]`, `B.sources=[target(C)]`) directly via `reg.insert_contract(..., now=…)`, choosing `now` so `key(B) < key(A)` (B created first). Request `[A, B]`; assert plan `== [A, B]` (not `[B, A]`) and that omitting `C` raises **no** problem. The `created_at` choice is what makes this a true regression — a scoped-only subgraph impl would tie-break to `[B, A]` here.
4. Gate — unknown id: request an unknown `cid` → `{"ok": False, problems:[{code: "contract_not_found", …}]}`.
5. Gate — unsupported kind: a requested contract with `merge_kind != "linked_block"` (e.g. `"import"`) → `{"ok": False, problems:[{code: "unsupported_merge_kind", …}]}`.
6. `_validate_graph` parity: the refactor to `_ordered_contract_ids` leaves `_validate_graph`'s output unchanged for a representative multi-contract graph (existing `_validate_graph` tests remain green; add one explicit assertion if not already covered).

Offline contracts are built via the low-level `reg.insert_contract(...)` (which does the cycle pre-check but **no** present-bar), so arbitrary acyclic graphs can be constructed without registering P6 artifacts.

**Live (`tests/test_merge_contract_chain_live.py`, `requires_rhino`, gated/skipped in CI):** the §4 harness; asserts §5; records §6.

**Baseline parity:** full `pytest -m "not requires_rhino"` run on the branch vs. `main`, comparing named FAILED/ERROR sets in **both** directions (counts alone are insufficient). No regression permitted.

## 9. Files

- `mcp_server/src/rook/work_units.py` — add `_ordered_contract_ids`; refactor `_validate_graph` to use it; add `plan_linked_block_execution`.
- `mcp_server/tests/test_work_units.py` — offline unit tests (§8.1–§8.6).
- `mcp_server/tests/test_merge_contract_chain_live.py` — new live harness (§4).
- This spec; the implementation plan; a memory update on completion.

## 10. Decision log

- **Proof/harness slice, not a tool** — observe the Save membrane + nested-link behavior before encoding/freezing any graph-execution contract (north-star §1, §5.5; project observe-before-theorizing).
- **One pure helper, narrow** — scoped order + gate (`contract_not_found`, `unsupported_merge_kind`, defensive `merge_cycle_detected`); no execute, no Rhino, no present-bar, no result envelope.
- **One source of truth for order** — factor `_ordered_contract_ids`, reused by `_validate_graph` and the helper.
- **Order over the full graph, then filter** (not over a scoped subgraph) — a scoped subgraph drops transitive edges through omitted contracts and can invert order; full-graph-filtered order is the global order restricted to the subset.
- **Omitted producers allowed** — artifact availability is the executor's runtime present-bar, not a pure planner's call; decline `dependency_not_requested` and producer-reporting (cheap to add later).
- **Hermetic live registries** — temp P6/P7 DBs; no pollution; unambiguous `{A,B}` graph.
- **One-Rhino doc-switching** — smallest test of the membrane; observes save→consume-from-disk; two-session while-open lock case deferred.
- **Hard-assert deterministic names; observe nested refresh** — bind assertions to `block_def_name`, characterize Rhino's nested presentation.
