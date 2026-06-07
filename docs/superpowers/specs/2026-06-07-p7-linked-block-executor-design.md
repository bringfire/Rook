# P7 Linked-Block Merge Executor — Design Spec

**Status:** Approved for plan-writing (brainstorm complete; user + Codex review pending on this file)
**Date:** 2026-06-07
**Slice:** P7 Slice 4 — first merge *execution* slice
**Predecessors:** P7 Slice 1 (strict `merge_contracts`), Slice 2 (declared targets), Slice 3 (planned contracts), PR #227 (linked-block read substrate)

---

## 1. North star

Take an already-activated strict `merge_contract` whose `merge_kind == "linked_block"` and drive **real Rhino mutation**: ensure each source artifact is linked into the target document as a deterministic linked block, save the target, and report a structured execution result. This is where P7 intent finally crosses from the coordinator plane into geometry/document mutation.

This is the **first** P7 tool that touches Rhino. Every prior P7 tool (`merge_contract_record`/`validate`, declared, planned) is pure coordinator-plane (`requires_rhino: False`, no Rhino I/O). The executor is the seam where that changes — and it is deliberately narrow.

## 2. Scope

**In scope (Slice 4):**
- One new tool: `rhino_merge_contract_execute(contractId, session, expectedMergeKind, dryRun=false)`.
- Execution of **`linked_block`** contracts only; all other kinds fail closed.
- Idempotent ensure of linked block definitions, keyed on a deterministic block name.
- A non-mutating `dryRun` preview that classifies purely from read surfaces.
- A pure per-source planner in `linked_blocks.py`; an I/O orchestrator in a new `merge_execution.py`.
- Save the target document once, only on full success.
- Structured per-source results; no durable execution status written anywhere.

**Out of scope (explicitly deferred):**
- Other merge kinds: `import`, `worksession`, `reference`, `block`, `report`. `import` in particular uses `RunScript`, duplicates geometry on rerun, and is not idempotent — it remains out.
- Planned-contract *activation* (this slice consumes already-activated strict contracts; it does not activate).
- Any new P7 registry schema. No durable writes from the executor at all.
- Opening/launching the target document. The target must already be open in the selected session.
- Any UI automation; any C++/native change (the read substrate shipped in #227).
- Background/automatic refresh (no source-save watcher). `refresh_after_save` is honored only as far as a watcher-free slice can honestly honor it.
- Source-change detection (mtime/hash). `refresh_on_demand` refreshes unconditionally.
- P6 writes (the executor stays P6-read-only, even after saving the target).

## 3. Tool contract

```
rhino_merge_contract_execute(
    contractId:        str,    # strict merge_contract id (mc-…)
    session:           str,    # required session selector (rhino-<pid>); no ambient fallback
    expectedMergeKind: str,    # required; caller's declared intent; Slice 4 supports "linked_block"
    dryRun:            bool = false,
)
```

**Targeting policy (Finding 1 — non-routed *mutating* tool, NOT meta):**
The tool must be non-routed at the public dispatcher so it can own `session`, resolve it once, and pin a concrete port. But it *mutates Rhino* via internal sub-calls, so labeling it `meta` is semantically false. Policy:
- `requires_rhino: False`, `risk: "mutate"` → `RhinoToolPolicy(False, "mutate")`.
- Membership: add to `_ALL_KNOWN_TOOLS`, `_RHINO_INDEPENDENT_MUTATE_TOOLS` (which yields exactly `(False, "mutate")` — same bucket as `capture_script_artifact`), and `_NON_ROUTED_SESSION_ARGUMENT_TOOLS`.
- **Not** in `_META_TOOLS`.
- The set name `_RHINO_INDEPENDENT_MUTATE_TOOLS` is imperfect for a tool that does cause Rhino mutation; the load-bearing fact is the `(False, "mutate")` policy + non-routed status. A dedicated set is a possible future cleanup (YAGNI for one tool now).

## 4. Module boundary & wiring

**`linked_blocks.py` (MODIFY) — stays strictly pure** (no `server`/Rhino/`artifacts`/`work_units` imports):
- existing `block_def_name(contract_id, source_artifact_id)`.
- new `plan_source_action(...)` (pure decision function, §6).
- new small `PlannedAction` / `Outcome` string-enums (or a frozen set of literals).

**`merge_execution.py` (CREATE) — the I/O shell**, the first Rhino-touching P7 module:
- `async execute_merge_contract(*, contract_id, session, expected_merge_kind, dry_run, call_tool)`.
- Imports `work_units` (contract + sources read), `artifacts` (P6 read + `normalize_path`/`artifact_id_for`), `linked_blocks` (pure core), `targeting` (route resolution for the pin), `bridge` (`rhino_request_context` for the routing-context wrapper).
- Computes `observed_source_artifact_id`/`source_present` from P6 + raw Rhino `sourcePath`, feeds plain strings into the pure planner.
- Builds the dry-run and execute envelopes. **No durable writes.**

**`server.py` (MODIFY):**
- Declare `rhino_merge_contract_execute` in the tool list.
- Dispatch `case "rhino_merge_contract_execute":` calls `merge_execution.execute_merge_contract(..., call_tool=_call_tool_dispatch)`.

**The injected `call_tool` seam + the routing-context wrapper (Finding 1):**
Inject **`_call_tool_dispatch`** (server.py:12864) — the *internal* dispatcher that returns `{success, data}` dicts directly. Do **not** inject `_mcp_tool_executor` or the public `call_tool`; both flatten the envelope to public text via `_format_tool_result` (server.py:19496) (`success → data only`; `failure → "Error: "+json`), and re-parsing that text is the recurring footgun that cost a ~13-run detour in P6 / motivated #220. Internal contract:

```python
async def call_tool(name: str, args: dict) -> dict:   # returns internal {success, data}; never MCP text
```

**Pinning is via the routing context, NOT via an args `port`.** `_call_tool_dispatch` pops `port` into a local, but the dispatch cases the executor uses (`rhino_blocks`, `rhino_block_info`, `rhino_block_link`, `rhino_block_refresh`, `rhino_document`, `rhino_document_ops`) call `call_rhino(...)` **without forwarding it**; `call_rhino` resolves its port from a contextvar — `resolved_port = port if port is not None else _RHINO_CONTEXT_PORT.get()` (bridge.py:992). Public `call_tool` works only because it wraps dispatch in `rhino_request_context(...)` (server.py:19613) — and for a **non-routed** tool like the executor it binds **no context at all** (server.py:19579-19583 dispatches directly, then `call_rhino` would auto-pick an instance). So the executor MUST bind the context itself: after resolving the route once (§8), it wraps **every** sub-call in

```python
with bridge.rhino_request_context(
        port=route.target.port,
        process_id=route.target.process_id,
        document_serial_number=route.document_serial_number):   # None on a session route; harmless
    ...   # all `await call_tool(name, args)` sub-calls live inside this block
```

Sub-call `args` carry only the tool's domain params (e.g. `{name, path}`) — never `port`/`session`; routing comes from the bound context. One route resolution, one context, the concrete pinned instance for every sub-call, internal dict surface throughout.

**Unit tests** inject a fake `call_tool` returning canned `{success, data}` dicts — the orchestrator is fully testable with zero Rhino.

## 5. Precondition ladder (fail closed, in order, before any mutation)

| # | Check | Failure code | retryable |
|---|---|---|---|
| 1 | work-units registry usable | `work_units_registry_unavailable` | true |
| 2 | P6 artifact registry usable | `artifact_registry_unavailable` | true |
| 3a | `contractId` non-empty string | `invalid_argument` | false |
| 3b | `expectedMergeKind ∈ MERGE_KINDS` (typo guard) | `invalid_argument` | false |
| 3c | `session` present & non-empty | `session_required` | false |
| 4 | contract exists | `contract_not_found` | false |
| 5 | `contract.merge_kind == expectedMergeKind` | `merge_kind_mismatch` | false |
| 6 | `contract.merge_kind == "linked_block"` (supported) | `unsupported_merge_kind` (+ `supportedMergeKinds:["linked_block"]`) | false |
| 7 | resolve `session` → concrete port (§8) | session-resolution codes (§8) | varies |
| 8 | active doc on pinned port ↔ contract target (§9) | `target_not_open` / `target_document_mismatch` | true |

Order matters: argument/contract/kind checks precede session resolution and any Rhino read, so a malformed call never touches Rhino. `session_required` (3c) fires before resolution — there is **no ambient/active/auto fallback**.

## 6. Per-source planner (pure, `linked_blocks.py`)

`plan_source_action` is a pure function of read-derived facts. Same function drives dry-run and execute. The orchestrator supplies:
- `block_facts`: the target document's block-table entry for the deterministic name, or `None` if absent. When present: `{ "isLinked": bool, "sourcePath": str, "blockType": str }` (the #227 fields, read from a single `/blocks` snapshot).
- `expected_source_artifact_id`: the contract source id (64-hex).
- `observed_source_artifact_id`: `artifact_id_for(resolved observed block sourcePath)`, or `None` if the observed path can't be resolved (§9 path rule).
- `source_present`: `True` iff the source artifact resolves to a P6 row with `file_state == "present"` (a usable path exists).
- `refresh_policy`: the contract's policy.

**Decision (precedence top-to-bottom):**

```
if block_facts is None:
    return would_create_link if source_present else source_artifact_not_present
if not block_facts.isLinked:
    return conflict_nonlinked                      # name taken by an embedded/static def
if observed_source_artifact_id is None:
    return source_path_unresolvable                # linked, but sourcePath unparseable
if observed_source_artifact_id != expected_source_artifact_id:
    return conflict_different_source               # linked to the WRONG source
# linked to the SAME source — prove source presence BEFORE refresh-vs-no-op (Finding 2):
if not source_present:
    return source_artifact_not_present            # present-bar applies to already_linked too
if refresh_policy == "refresh_on_demand":
    return would_refresh_existing
return already_linked                              # refresh_after_save → presence-only no-op
```

Notes:
- Hard conflicts (`conflict_nonlinked`, `conflict_different_source`) dominate — source presence is irrelevant when the name is already taken by the wrong thing, and a conflict is a blocker regardless. (Reporting the non-retryable structural conflict before the retryable presence problem avoids a two-round-trip discovery.)
- **Present-bar invariant (Finding 2):** source presence gates EVERY success-eligible action — `would_create_link`, `would_refresh_existing`, **and** `already_linked`. No success path admits a source that is not P6-present; `refresh_policy` chooses refresh-vs-no-op only *after* presence is proven. This preserves the strict present-bar that Slice 1's `record`/`validate` enforce (sources must resolve to a P6 row with `file_state == "present"`).
- `source_path_unresolvable` is the defensive edge: a def marked `isLinked` whose `sourcePath` can't be normalized/compared, so same-vs-different cannot be decided. Fail closed rather than guess.

**Policy mapping (Q4):** new/missing link is created under *both* policies; `refresh_policy` only governs the already-correct case. `refresh_on_demand` → `would_refresh_existing` (an explicit execute *is* the demand). `refresh_after_save` → `already_linked` (no watcher exists; presence guaranteed, freshness not forced). On-demand refresh is **unconditional** (no mtime/hash detection); `block_refresh` is an idempotent reload.

## 7. Apply + save (execute mode, `dryRun:false`)

1. **Pre-flight gate.** Read the `/blocks` snapshot *once*; if that read itself fails, return `block_table_read_failed` — **zero mutation, zero save** (a failed read must never be mistaken for an empty block table, which would let mutation proceed past a failed pre-flight; this fail-closed check precedes the `dryRun`/execute branch, so it holds in both modes). Otherwise classify *all* sources against the snapshot. If any source is a hard blocker (`conflict_nonlinked`, `conflict_different_source`, `source_artifact_not_present`, `source_path_unresolvable`), return `merge_contract_not_executable` with the full per-source plan + blockers — **zero mutation, zero save**. Conflicts are caught before the document is touched.
2. **Apply** only an all-clear plan (every source ∈ {`would_create_link`, `would_refresh_existing`, `already_linked`}), in deterministic source order. **Every sub-call below runs inside the §4 `bridge.rhino_request_context(...)`; args carry only domain params — never `port`/`session` (routing comes from the bound context):**
   - `would_create_link` → `call_tool("rhino_block_link", {"path": source_row.path, "name": name, "updateType": "linked", "insertionPoint": [0, 0, 0]})`. Passing `insertionPoint` also places one instance at origin (native behavior), so the merged source is visible. Idempotent: link is never re-called once the def exists, so the single instance is created exactly once.
   - `would_refresh_existing` → `call_tool("rhino_block_refresh", {"name": name})`.
   - `already_linked` → no-op.
3. **Re-verify** active-doc identity == target (§9) immediately before save; drift → `target_document_mismatch`, no save.
4. **Save** once → `call_tool("rhino_document_ops", {"action": "save", "path": active_document_path})`. Save to the path Rhino reported for the active doc (the OS path), not the case-folded normalized form. (Save is always performed on full success, including an all-`already_linked` run; a skip-when-no-mutation optimization is deferred.)

Mutations occur on the pinned port (the verified target document). The executor writes nothing durable; the saved `.3dm` is the execution artifact.

## 8. Session resolution & pinning (Finding 2)

Resolve the selector **once**, up front, with `has_explicit_session=True` — this is load-bearing:

```python
route = targeting.resolve_tool_route(
    "rhino_document",
    explicit_session=session,
    has_explicit_session=True,   # REQUIRED: without it, resolve_tool_route ignores
                                 # explicit_session and falls through to active/auto.
)
```

`resolve_tool_route` gates the session rung on `if has_explicit_session:` (targeting.py:961). Passing `explicit_session` alone silently resolves as if no session was given — the exact ambient fallback this slice forbids. Use the routed-read tool name `"rhino_document"` as the resolution proxy (the executor's own name is non-routed, so it would resolve to `selection="none"`).

On success, **bind** `bridge.rhino_request_context(port=route.target.port, process_id=route.target.process_id, document_serial_number=route.document_serial_number)` around every Rhino sub-call (§4 — pinning is via the context, not an args `port`; `document_serial_number` is `None` on a session route, which is harmless — port + process_id pin the instance, and §7 re-verifies active-doc identity before save). On failure, map `route.error` → the executor's session codes:

| `route.error` | executor code | retryable |
|---|---|---|
| `invalid_session_id` | `invalid_session_id` | false |
| `rhino_session_not_found` | `rhino_session_not_found` | false |
| `panel_target_config_error` / `panel_target_stale` / `panel_target_locked` | passthrough (panel-lock semantics) | varies |

(With an explicit session and no port, `selector_conflict` / `requested_port_not_discovered` / `multiple_rhino_instances` do not arise from the executor's own resolution.)

## 9. Path identity rules (Q6 path comparison)

- **Target identity:** `rhino_document` on the pinned port → `documentPath` (fallback `path`). Empty/absent → `target_not_open` (no active doc, or unsaved with no path). Else `artifact_id_for(normalize_path(documentPath))` must equal `contract.target_artifact_id`, else `target_document_mismatch`.
- **Source → link path:** source artifact id → P6 row → `row.path` (already normalized; P6 stores normalized paths). That `path` is fed to `block_link`.
- **Existing-block identity:** the observed block's `sourcePath` is the raw `LinkedFilePath()` (the #227 observation found it absolute in the same-drive case). If absolute → `artifact_id_for(normalize_path(sourcePath))`. If relative → resolve against the **target document's directory** (dirname of the verified active `documentPath`) first, then normalize, then `artifact_id_for`. Unparseable → planner returns `source_path_unresolvable`.

The executor does not pin P6 mtime/size after save (the artifact id is path-derived and unchanged; freshness is telemetry, healed by a later `rhino_artifact_refresh`).

## 10. Result envelope

| Case | `success` | `data` |
|---|---|---|
| `dryRun:true` (any plan) | **true** | `{ dryRun:true, executable:<bool>, blockers:[…], perSource:[…planned…] }` |
| pre-flight blocker (`dryRun:false`) | false | `{ code:"merge_contract_not_executable", blockers:[…], perSource:[…] }` |
| applied + saved | true | `{ executed:true, saved:true, perSource:[…outcome…] }` |
| applied, save fails | false | `{ code:"document_save_failed", executed:true, saved:false, perSource:[…] }` (complete, unpersisted) |
| mid-apply failure | false | `{ code:"merge_contract_execution_incomplete", executed:false, saved:false, perSource:[…] }` (partial, unsaved) |

`dryRun:true` always returns `success:true` — blockers are the *point* of the call, not a failure. `executed:true/saved:false` (complete-but-unpersisted) is a distinct truth from `executed:false/saved:false` (incomplete); both note that the live target holds unsaved changes that a close-without-save discards.

**`perSource` entry:**
```
{
  "sourceArtifactId": "<64hex>",
  "blockName":        "rook_p7lb_<hash8>_<id16>",
  "plannedAction":    "would_create_link" | "would_refresh_existing" | "already_linked"
                      | "conflict_nonlinked" | "conflict_different_source"
                      | "source_artifact_not_present" | "source_path_unresolvable",
  "outcome":          "created_link" | "refreshed_existing" | "already_linked"
                      | "block_link_failed" | "block_refresh_failed"
                      | <terminal planner code>,        # execute mode only
  "observedSourcePath":       <str|null>,
  "observedSourceArtifactId": <str|null>,
  "isLinked":                 <bool|null>,
  "blockType":                <str|null>
}
```

Two-layer naming: dry-run `plannedAction` → execute `outcome` (`would_create_link`→`created_link`, `would_refresh_existing`→`refreshed_existing`, `already_linked`→`already_linked`; terminal conflict/not-present/unresolvable codes identical in both). Execute-only `block_link_failed` / `block_refresh_failed` capture unexpected native errors despite a clean plan.

## 11. Failure taxonomy (top-level codes)

| code | retryable | meaning |
|---|---|---|
| `work_units_registry_unavailable` | true | P7 registry version skew |
| `artifact_registry_unavailable` | true | P6 version skew |
| `invalid_argument` | false | bad `contractId` / unknown `expectedMergeKind` |
| `session_required` | false | no `session` selector |
| `invalid_session_id` | false | malformed session string |
| `rhino_session_not_found` | false | no live native session for that pid |
| `contract_not_found` | false | no such `mc-…` |
| `merge_kind_mismatch` | false | `contract.merge_kind != expectedMergeKind` |
| `unsupported_merge_kind` | false | kind not `linked_block` (+ `supportedMergeKinds`) |
| `target_not_open` | true | active doc absent / unsaved (no path) |
| `target_document_mismatch` | true | active doc artifact id ≠ contract target |
| `block_table_read_failed` | true | the `/blocks` snapshot read itself failed — fail closed (a failed read must NOT be mistaken for an empty block table); no mutation, no save, in both modes |
| `merge_contract_not_executable` | false | pre-flight blockers present (carries `blockers` + `perSource`) |
| `document_save_failed` | true | full apply ok, save errored (`executed:true, saved:false`) |
| `merge_contract_execution_incomplete` | true | mid-apply native/race failure (`executed:false, saved:false`) |

Per-source blocker codes inside `merge_contract_not_executable.blockers`: `conflict_nonlinked` (false), `conflict_different_source` (false), `source_artifact_not_present` (true), `source_path_unresolvable` (false).

## 12. Idempotency & atomicity

- **Idempotency** is structural: the deterministic `block_def_name` makes the *definition* the idempotency key, and `block_link` is create-only. A re-run sees each def already present and correct → `refreshed_existing` (on_demand) or `already_linked` (after_save) — never a duplicate def or instance. The saved target document is the source of truth; a re-run re-derives state from it and converges. **No durable execution status is written.**
- **Present-bar (Finding 2):** every contract source must resolve to a P6 row with `file_state == "present"` for *any* success outcome — including `already_linked`. A success path never admits a since-missing source, preserving the Slice-1 invariant; a source that has gone missing yields `source_artifact_not_present` (retryable) at the pre-flight gate.
- **Atomicity** is honest-not-transactional: Rhino mutation can't be DB-atomic. The pre-flight gate makes the realistic failure (conflicts) fully non-mutating. The only path to a partial document is an unexpected mid-apply native/race error, which is reported as `merge_contract_execution_incomplete` with the live doc left dirty-but-unsaved. No registry state ever claims success the document doesn't back.

## 13. Testing

- **Pure planner** (`test_linked_blocks.py`, MODIFY): a decision table over every §6 row — both policies, source present/absent, absolute vs relative observed path, the `None`/unparseable edges. Includes the **present-bar branch (Finding 2): same-source + source absent → `source_artifact_not_present`, never `already_linked`/`would_refresh_existing`.** Zero Rhino, zero mocking.
- **Orchestrator** (`test_merge_execution.py`, CREATE): inject a fake `call_tool` returning canned `{success, data}` dicts + monkeypatch `targeting.resolve_tool_route` to return a canned `ToolRoute`; repoint `work_units`/`artifacts` singletons to temp dbs (existing fixtures). Cover: precondition ladder (each code), `dryRun` plan, pre-flight gate (no mutation), full success + save, `document_save_failed`, mid-apply failure, **idempotent re-run** (second execute → all `already_linked`/`refreshed_existing`, no dup), `target_document_mismatch`, `session_required` (and the `has_explicit_session=True` resolution call), kind gates (`merge_kind_mismatch`, `unsupported_merge_kind`), the **present-bar on `already_linked`** (source not P6-present but a matching link already exists → `source_artifact_not_present`, never a save), and the **routing-context binding (Finding 1): the fake `call_tool` asserts `bridge.get_rhino_request_context()["port"] == route.target.port` on every sub-call.**
- **Targeting policy** (`test_work_units_tools.py` + `test_session_routing.py`, MODIFY/ADD): new test asserts `policy_for_tool("rhino_merge_contract_execute") == RhinoToolPolicy(False, "mutate")` and `allows_non_routed_session_argument(...) is True`; update the exact-set assertion in `test_non_routed_session_argument_tools_membership`. The executor must **not** be added to any `_are_meta_no_rhino` list.
- **Live smoke** (`test_merge_contract_execute_live.py`, CREATE; `requires_rhino`, throwaway session): build a target + two source `.3dm`; register all three as P6 artifacts; record a `linked_block` `merge_contract`; open the target in the selected session; execute → assert both linked defs present + isLinked + correct sourcePath, `saved:true`; re-run → assert idempotent (`already_linked`/`refreshed_existing`, no duplication).

## 14. Acceptance & honesty discipline

- **No native build** this slice — the read substrate shipped in #227; this is pure Python. Editable install suffices for pytest. The live smoke needs a Rhino running the #227-built RookNative (already deployed).
- **Baseline parity** before PR: named FAILED/ERROR sets compared in both directions vs `main` (counts lie). Blessed gate: `pytest mcp_server/tests -m "not requires_rhino" -p no:cacheprovider -q -rfE --tb=no`.
- **Live observation is gated evidence, not a merge blocker.** The live smoke either runs and records its result, or is explicitly reported as blocked with a reason (Rhino unreachable). An absent toolchain is a graceful skip, never a fake pass.
- The executor writes nothing durable and makes no P6 writes; correctness is verifiable from the saved target document and from re-run convergence.

## 15. Open confirmations folded from review

- Outcome names `created_link` / `refreshed_existing`, top-level `merge_contract_execution_incomplete`: confirmed.
- Inject `_call_tool_dispatch` (internal dict surface), never `_mcp_tool_executor`/public `call_tool`: confirmed.
- Executor is a **non-routed mutating** tool (`RhinoToolPolicy(False, "mutate")`), not `meta`.
- **Finding 1 (P1):** pinning is via `bridge.rhino_request_context(port=route.target.port, process_id=route.target.process_id, document_serial_number=route.document_serial_number)` wrapping the sub-calls — NOT an args `port`. Verified: block dispatch cases don't forward the popped local `port`; `call_rhino` reads `_RHINO_CONTEXT_PORT` (bridge.py:992); and the non-routed dispatch path (server.py:19579-19583) binds no context. Corrected in §4/§8/§13.
- **Finding 2 (P1):** the strict present-bar applies to every success outcome including `already_linked`; the planner proves source presence *before* `refresh_policy` chooses refresh-vs-no-op. Corrected in §6/§12/§13.
- Route resolution must pass `has_explicit_session=True` (else `resolve_tool_route` ignores `explicit_session` and falls through to ambient): §8.
