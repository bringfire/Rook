# LM4 Phase Closeout - Workflow Scaffold And Traceability

**Date:** 2026-06-28
**Status:** CLOSED as a substrate phase. LM5 requires a new brainstorming/spec/planning cycle.
**Campaign:** Local/Internal Models roadmap - `docs/superpowers/specs/2026-06-19-rook-local-internal-models-north-star.md` (phase LM4)
**Topology bearing:** `docs/superpowers/specs/2026-06-03-rook-north-star-topology.md`

---

## Headline Guarantee

LM4 guarantees that a strict Rook workflow contract artifact can be loaded from an
already-parsed normalized schema payload, snapshotted and fingerprinted, compiled
into a bounded provider/stream scaffold, executed one current mapped step at a
time, and audited back to its compile receipt, without giving the model ownership
of planning, graph mutation, node selection, remapping, scheduling, terminal
completion, or evaluation.

This is a substrate guarantee, not a user-facing workflow guarantee. LM4 does not
accept natural language intent, does not parse workflow files, does not integrate
RookChat, and does not prove a local model can use the scaffold well. It proves
that Rook now has a bounded, inspectable scaffold for that next question.

---

## Verification Snapshot - 2026-06-28

This snapshot records evidence at the LM4 phase boundary. It is not a promise
that future gate counts remain identical.

- `main` commit: `e54c0fef`
- final LM4 PR: #374, LM4Z workflow provenance envelope source
- post-LM4Z focused PlanGraph gate: `556 passed`
- local state after LM4Z: `main` synced with `origin/main`, clean
- key live proofs:
  - LM4Q (#354): first gated execution authority reached the real declared create tool.
  - LM4T (#360): bespoke current-step stream carried the live create/verify/repair/verify chain.
  - LM4V (#367): production `CatalogCurrentStepProvider` carried the same live chain.

---

## Proof / Invariant Ledger

### 1. Artifact Identity

**Invariant:** A strict Rook workflow contract artifact has a normalized identity.

**What is now true:**
- `load_workflow_contract_payload(...)` accepts already-parsed normalized schema payloads only.
- `snapshot_workflow_contract(...)` produces a structured normalized snapshot.
- The snapshot has a deterministic SHA-256 contract fingerprint.
- Mapping key order is normalized for hashing; declared sequence order remains authored and load-bearing.
- `WorkflowCompileRecord` records compact compile facts and references the contract fingerprint.

**Evidence:**
- LM4W (#371) introduced `RookWorkflowContract` and `CompiledWorkflowScaffold`.
- LM4X (#372) added `WorkflowContractSnapshot`, stable fingerprints, and `WorkflowCompileRecord`.
- LM4Y (#373) added the strict normalized payload loader and round-trip fingerprint tests.
- Focused PlanGraph gate after LM4Z: `556 passed`.

### 2. Compile Boundary

**Invariant:** Compilation prepares a scaffold; it does not run or decide the workflow.

**What is now true:**
- `compile_workflow_contract(...)` selects and initializes the declared template, validates expected refs, stages initial execution params, compiles step specs into `Step` objects, builds `NodeStepRule`s, and returns a `CompiledWorkflowScaffold`.
- The scaffold contains graph, provider, max steps, metadata, compiled rules/steps, contract snapshot, and compile record.
- The compiler does not call the current-node proposal selector (`propose_next_node`), mapper, revalidator, executor, stream runner, live Rhino/GH seams, model surfaces, or terminal completion helpers.

**Evidence:**
- LM4W offline chain guard proves the compiled scaffold can feed the existing stream path.
- LM4X determinism tests prove repeated compiles of the same contract produce the same compile record.
- LM4Y compile assertion proves a loaded normalized payload still compiles to the same fingerprinted scaffold.

### 3. Runtime Authority

**Invariant:** Runtime authority remains bounded to current-step artifacts and delegated seams.

**What is now true:**
- LM4N proposes one uniquely ready node and owns no graph mutation.
- LM4O distrusts a proposal by re-deriving it and requiring full equality.
- LM4P maps an accepted proposal to a caller-authored `Step`; it does not construct hidden steps.
- LM4Q executes exactly one already-mapped step; it does not select, remap, evaluate, loop, fallback, or apply terminal `done`.
- LM4R threads one current mapped step through LM4Q and records flattened observations while preserving canonical objects.
- LM4S threads repeated current-step calls through a caller-fed stream, with explicit max steps and typed stop reasons.

**Evidence:**
- LM4N (#345), LM4O (#352), LM4P (#353), LM4Q (#354), LM4R (#356), and LM4S (#357) each landed as narrow authority slices with focused tests.
- LM4S stops on provider halt, provider invalid/error, execution refusal, graph not advanced, and max steps; it does not become a scheduler.
- Stale-artifact protection remains a caller contract: LM4R/LM4S record supplied artifacts and do not revalidate stale-but-still-mapped mappings.

### 4. Provider Discipline

**Invariant:** The production current-step provider is explicit catalog/rule plumbing, not planning.

**What is now true:**
- `CatalogCurrentStepProvider` is generic over caller-supplied `NodeStepRule`s.
- Every step is caller-authored before the provider call.
- Repeat behavior is literal count-indexed by prior `CurrentStepRecord.accepted_node_id`.
- Terminal halt nodes are explicit.
- The provider calls LM4N and LM4P only; LM4P embeds LM4O.
- Runtime unsupported paths return LM4S-native invalid supply shapes rather than fallback steps.

**Evidence:**
- LM4U (#365) introduced the production provider scaffold with strict construction validation and an offline chain guard.
- LM4V (#367) proved the production provider under live Rhino/GH load on the create/verify/repair/verify chain.
- LM4V pinned the same-node `repair_same_component` turn as `BindStep` first, then `ProducerStep`, derived from stream history.

### 5. Traceability

**Invariant:** Stream traces can point back to the workflow contract receipt.

**What is now true:**
- `WorkflowProvenanceEnvelopeSource` overlays compact compile identity onto LM4S supply metadata and valid supplied envelope metadata.
- LM4R copies envelope metadata into `CurrentStepRecord`, so executed records carry workflow provenance.
- Provenance metadata includes workflow id, contract schema, contract fingerprint, compiler id, provider id, and selected template id.
- Provenance is observational only. It does not authorize continuation, evaluation, remapping, or terminal completion.

**Evidence:**
- LM4Z (#374) added the provenance wrapper in `plan_graph_workflow_provenance.py`.
- LM4Z tests cover collision/refusal taxonomy, non-result passthrough, exception propagation, mutation isolation, and full offline receipt-chain integration:
  `payload -> load -> compile -> provenance source -> LM4S stream records`.

### 6. Live Load Proofs

**Invariant:** The scaffold has carried real Rhino/GH pressure in the narrow workflow it claims.

**What is now true:**
- The declared `gh_create_csharp_script:v1` ref path reached live execution.
- The declared `gh_update_script:v1` repair path reached live execution.
- The live proof preserved the terminal boundary: LM4S halted when `done` was proposed; terminal completion remained outside LM4S.
- LM4G live producer records remained test-local observations, not stream policy.

**Evidence:**
- LM4Q (#354) proved first bounded execution authority over a real declared create seam.
- LM4T (#360) proved the full live current-step stream with a bespoke provider.
- LM4V (#367) proved the same live stream using the production `CatalogCurrentStepProvider`.

### 7. Deliberate Non-Goals

**Invariant:** LM4 explicitly does not smuggle in the next phase.

**What is now true:**
- No scheduler loop was introduced.
- No RookChat behavior was changed.
- No model worker was introduced.
- No natural-language/user-intent compiler was introduced.
- No JSON/YAML/file loader was introduced.
- No terminal `done` auto-completion was introduced.
- No stream record was promoted into an evaluation verdict.
- No provenance value was treated as authority to continue.

**Evidence:**
- LM4W-Z boundary guards and tests pin compile/load/provenance surfaces away from runtime authority.
- LM4S/LM4R tests pin stop reasons and record semantics without verdict fields.
- The final LM4Z production diff is exactly the provenance bridge module.

---

## Authority Boundaries Preserved

LM4 keeps these boundaries load-bearing:

| Boundary | Preserved rule |
|---|---|
| Model vs scaffold | The model does not remember the plan or own graph mutation. |
| Proposal vs authority | LM4N proposes; it does not execute or mutate. |
| Revalidation vs trust | LM4O re-derives and compares; mapping remains canonical through LM4P. |
| Mapping vs construction | LM4P consumes caller-authored `Step`s; it does not invent steps. |
| Execution vs selection | LM4Q executes exactly one mapped step; it does not choose another step. |
| Record vs verdict | LM4R/LM4S records observations; they do not compute success policy. |
| Stream vs scheduler | LM4S loops only over caller-fed current-step artifacts with required max steps. |
| Provider vs planner | LM4U chooses from explicit rules; it does not infer node meaning. |
| Contract vs authoring UX | LM4W-Y define strict Rook artifacts; no friendly external format is implied. |
| Provenance vs permission | LM4Z attaches receipt identity; it does not authorize continuation. |

---

## Live Load Proofs

LM4's live evidence is intentionally narrow, but it is real:

1. **Declared create execution - LM4Q (#354)**
   - The first bounded execution authority executed one already-mapped step through the real declared `gh_create_csharp_script:v1` path.
   - The test proved delegation into live `RookAgent`/Grasshopper behavior without giving LM4Q selection or remapping authority.

2. **Bespoke live stream - LM4T (#360)**
   - A test-local provider prepared fresh LM4N -> LM4P artifacts per graph snapshot.
   - The stream executed create, verify, bind, repair, verify, then halted at `done`.
   - The same-node repair switch was derived from prior `CurrentStepRecord`s.

3. **Production provider live stream - LM4V (#367)**
   - The test replaced the bespoke provider with `CatalogCurrentStepProvider`.
   - It proved production catalog/rule plumbing could carry the same live path.
   - Provider metadata and terminal halt behavior remained inspectable through LM4S supply records.

These live proofs do not claim broad GH/Rhino workflow coverage. They prove the
create/verify/repair/verify pattern that LM4 was designed around.

---

## What LM4 Deliberately Does Not Do

- It does not compile user intent or natural language into workflow contracts.
- It does not load JSON/YAML/text files from disk.
- It does not introduce a friendly authoring dialect beside the strict normalized Rook payload.
- It does not give local/internal models direct PlanGraph mutation rights.
- It does not let models select, remap, schedule, or fallback to different nodes.
- It does not own retries, recovery policy, or autonomous repair loops.
- It does not integrate RookChat.
- It does not expose a new public MCP workflow tool.
- It does not evaluate stream records as passed/failed outcomes.
- It does not auto-apply terminal `done`.
- It does not fingerprint the entire compiled `PlanGraph`.
- It does not create a failed-compile receipt or run ledger.

---

## Residual Risks / Open Questions

- No graph fingerprint exists yet. Compile records summarize selected template id and graph node ids, but do not content-address full `PlanGraph` structure.
- No failed-compile receipt exists. Compile records are minted only for successful compiles.
- LM4Z does not attach provenance to provider exceptions because delegated exceptions propagate to LM4S's existing `provider_error` path.
- The payload loader accepts already-parsed normalized schema envelopes only; file/text/YAML loading remains absent.
- Live proofs cover the C# script create/verify/repair/verify workflow, not broad GH/Rhino tool families.
- Stream records remain observations, not evaluation verdicts.
- There is no full model-in-the-loop evaluation proving local/internal models improve under the scaffold.
- There is no RookChat integration proof.
- Knowledge push is represented by the scaffold direction, but scheduled live knowledge packets for model turns are not implemented.
- Bounded retry/recovery/escalation policy remains a future layer.

---

## What LM5 May Consume / Must Not Assume

| LM5 may consume | LM5 must not assume |
|---|---|
| `RookWorkflowContract` payload loader for already-parsed normalized schema envelopes | natural-language/user intent compilation exists |
| `WorkflowContractSnapshot` and stable contract fingerprints | JSON/YAML/file loading exists |
| `WorkflowCompileRecord` and `CompiledWorkflowScaffold` | a model may mutate `PlanGraph` |
| `CatalogCurrentStepProvider` | a model may select, remap, or schedule nodes directly |
| `WorkflowProvenanceEnvelopeSource` | stream records are evaluation verdicts |
| LM4S stream traces carrying workflow provenance | provenance authorizes continuation |
| live-proven create/repair workflow pattern | terminal `done` is automatic |
| current-step records and supply records as audit observations | RookChat integration exists |
| compile metadata as a receipt pointer | retries, recovery policy, or autonomous repair loops exist |

This table is the LM5 handoff contract. LM5 may stand on LM4's scaffold; it may
not treat missing layers as implied authority.

---

## Non-Binding LM5 Launch Pad

This launch pad is orientation only. It records plausible first LM5A directions
based on the completed LM4 substrate. It is not an implementation plan, not an
approved scope, and not permission to bypass brainstorming, spec, or planning for
LM5A.

### LM5A Candidate: Workflow Contract Authoring Surface

A narrow typed helper/tool that creates strict Rook workflow contract payloads
for known templates. No natural-language compiler yet. No friendly schema
dialect unless explicitly designed.

This would make artifact creation easier, but it mainly improves the production
of workflow artifacts rather than testing the local-worker premise.

### LM5A Candidate: Local Worker Consumption Harness

A deterministic harness showing how a local/internal worker receives compiled
scaffold context, current-node context, pushed knowledge, provenance, and narrow
allowed actions without gaining graph authority.

**Likely first LM5A.** This is the strongest current bearing because it tests
the central north-star premise: local/internal workers should consume Rook-owned
scaffold context and bounded actions, not own planning or graph mutation. This
is still not approved LM5A scope; it needs its own brainstorming, spec, and plan.

### LM5A Candidate: Evaluation / Probe Harness

A model-in-the-loop probe that measures whether local/internal models perform
better through the LM4 scaffold than through primitive tool exposure.

This is necessary evidence, but it is likely stronger after the worker
consumption surface is named. Otherwise the probe may measure prompt shape rather
than the scaffold contract.

---

## Compact LM4N-Z Chronology

Earlier LM4 work, plus precursor LM1/LM3 work, supplied reducer, template,
memory, verifier, live repair, and explicit-step foundations. The closeout
chronology below focuses on the N-Z ladder because it is where the current
proposal-to-provenance spine was finalized.

| Slice | PR | Purpose |
|---|---:|---|
| LM4N | #345 | `propose_next_node`: pure policy proposal, unique-ready only, no authority. |
| LM4O | #352 | `revalidate_proposal`: distrust by re-deriving and requiring full equality. |
| LM4P | #353 | `map_accepted_proposal_to_step`: accepted proposal to caller-authored `Step`. |
| LM4Q | #354 | `execute_mapped_step`: execute exactly one already-mapped step. |
| LM4R | #356 | `run_current_mapped_step`: current-step thread and non-authoritative record. |
| LM4S | #357 | `run_current_step_stream`: bounded caller-fed current-step stream. |
| LM4T | #360 | Live vertical proof with a bespoke provider and same-node bind -> producer turn. |
| LM4U | #365 | `CatalogCurrentStepProvider`: production catalog/rule provider scaffold. |
| LM4V | #367 | Live proof that production provider carries the same create/repair chain. |
| LM4W | #371 | `RookWorkflowContract` and compiled scaffold boundary. |
| LM4X | #372 | Contract snapshot, fingerprint, and compile record. |
| LM4Y | #373 | Strict normalized payload loader. |
| LM4Z | #374 | Workflow provenance bridge into supply/current-step traces. |

Pre-ladder foundation highlights:
- LM4I (#339): full live repair chain, test-only.
- LM4J (#340): declared `gh_create_csharp_script:v1` ref dispatches live.
- LM4K (#341): `bind_params_from_memory`, first memory-to-params primitive.
- LM4L (#343): `apply_memory_bound_params`, first applier consumer.
- LM4M (#344): `run_explicit_sequence`, caller-authored typed-step sequence runner.

---

## Closeout Decision

LM4 is closed as the workflow scaffold and traceability substrate phase.

The next immediate artifact should not be LM4ZA. The next phase should begin as
LM5, after its own brainstorming/spec/planning cycle. The strongest current
bearing is LM5A as a local worker consumption harness, because it tests whether a
local/internal worker can consume Rook-owned scaffold context and bounded actions
without receiving planning, graph mutation, scheduling, terminal completion, or
evaluation authority.

Until that LM5A design is approved, the only approved claim is this closeout:
LM4 provides a strict artifact-to-scaffold-to-trace substrate that future local
worker work may consume carefully.
