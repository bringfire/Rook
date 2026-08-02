# Rook Planner Harness North-Star — The Three-Box Internal Agent Topology

> **Historical status (2026-08-02):** This document remains evidence for the
> durable Planner → deterministic Runner → bounded Worker allocation. Its staged LM
> sequencing and experiment-specific authoring ladder are superseded for active
> product work by the
> [Compositional Agent Harness Roadmap](../../roadmaps/2026-08-02-compositional-agent-harness-roadmap.md).
> Do not use this document by itself to authorize implementation.

- **Date:** 2026-07-02
- **Status:** Brainstorm synthesis / design draft for review. **Not approved for implementation.** This document is "another voice in the room" for the in-flux DAG-coordination architecture discussion; slices derived from it require their own specs and approval.
- **Revision:** 2026-07-02 r2 — patched for LM5I (PR #394); senior-review round 1 folded in (adapter consumes the request envelope; softened near-term claims; external affordance vs internal harness separation; capability-authority rule; mutation-verification lint categories; replan-frontier as runner-interpreted marker; `subworkflow` pushed to LM7 horizon; published-state vocabulary; planner-envelope symmetry labeled a pattern).
- **Author:** Claude (Fable) brainstorm synthesis with the user; grounded in the LM campaign codebase, OpenProse/Reactor (`D:\prose`), and the RLM paper (arXiv 2512.24601).
- **Area:** `mcp_server/src/rook/agent/` — planner harness (net-new), PlanGraph runtime (LM4N–Z), local worker boundary (LM5A–I), `planner` execution profile (LM2F), RookChat as front-end.
- **Relationship to other docs:**
  - Extends `docs/superpowers/specs/2026-06-03-rook-north-star-topology.md` (macro two-tier coordinator) and `docs/superpowers/specs/2026-06-19-rook-local-internal-models-north-star.md` (bounded local workers). Those documents define the top and bottom tiers; **this document defines the internal harness that connects them: who authors the plan, who runs it, who executes a node, and how failure flows upward.**
  - Consumes, does not modify, the LM4 contract layer (`plan_graph_workflow_contract.py`, LM4X fingerprint, LM4Y payload loader, LM4Z provenance) and the LM5 worker boundary (`local_worker_turn_*.py`, through LM5I's request envelope, PR #394).
  - Gives the LM2F `planner` execution profile its first consumer.
  - External guideposts: OpenProse/Reactor's compile-time-intelligence/deterministic-runtime discipline, and the Recursive Language Models paper's context-as-environment, metadata-only-history, and depth-1-recursion findings.

---

## 1. Why this document exists

The LM campaign has built the bottom half of a multi-agent execution system:

```text
RookWorkflowContract (LM4W)
  -> compile_workflow_contract -> CompiledWorkflowScaffold
  -> fingerprint (LM4X), payload loader (LM4Y), provenance (LM4Z)
  -> live runner spine (LM4N–V: propose -> revalidate -> map -> execute
     -> record -> stream -> provider, live-proven)
  -> frozen worker turn boundary (LM5A–I: context -> response -> disposition
     -> harness -> scenario eval -> loaders/renderers -> request envelope)
```

Every contract so far is hand-authored. Nothing in the system yet *authors* a
contract, and nothing yet *calls a real model* at the worker seam. As real model
calls approach, three questions need architectural answers:

1. **How does a smarter Planner model decompose a task into the contract that
   is pushed through execution?**
2. **How do external coordinators (Claude Code, Codex, others) engage the same
   system and form the same contracts?**
3. **How does the architecture extend to deep/long-running tasks, using the RLM
   paper and OpenProse as guideposts?**

The core observation grounding all three answers: **the contract payload is the
interface.** The missing piece is not a new interface — it is the authoring
loop around the existing compiler, plus the model adapter at the existing
worker seam.

A second grounding observation: the codebase already contains **two harness
loops with opposite philosophies** and **three plan artifacts**:

| Existing thing | Philosophy | Tier |
|---|---|---|
| `chat/chat_runner.py` `ChatRunner` | model owns the loop; progressive disclosure; conversational | frontier-style chat |
| `local_worker_turn_*` (LM5) | scaffold owns the loop; one frozen turn; closed response contract | bounded worker |
| `agent/planner.py` `Plan`/`TaskSpec` | macro decomposition into agent tasks with `validate()`, postconditions, execution groups | conductor / macro |
| `RookWorkflowContract` → PlanGraph | declarative micro workflow; deterministic compile + runner | workflow / micro |
| `ExecutionPlan` | single operation | node substrate |

The planner harness proposed here is a **third harness shape** — an
artifact-producing loop — not a reuse of `ChatRunner` and not a replacement for
the macro `Plan`.

---

## 2. Decisions made in this brainstorm

Three structural decisions were made explicitly during the 2026-07-02
brainstorm session. The full option sets considered at each fork, with
trade-offs as presented, are preserved in **Appendix A — Branching points**;
this section records only the outcomes.

1. **Planner loop shape: plan-then-execute with declared replan-frontier
   nodes.** The Planner compiles a full contract up front. A contract may
   contain an explicit *replan-frontier* node whose meaning is "halt, gather
   receipts, re-invoke the Planner for the remainder." Interleaved planning is
   therefore a declared, auditable choice inside the artifact — not a second
   harness mode. Strict-interleaved proposal (a model choosing every next node
   live) is rejected as the spine; the LM4N/LM4O propose/revalidate seams
   remain runner-internal mechanisms.
2. **Authoring altitude: a staged ladder gated by evals.**
   - **Stage 1:** select a template + bind initial params (`select_template`,
     LM4K/LM4L binding machinery already exist).
   - **Stage 2:** chain multiple templates into one contract.
   - **Stage 3:** free node authoring against the compiler.
   Each stage ships with its own decomposition eval suite before the next
   unlocks. This matches the RLM finding that first-decomposition quality
   dominates task outcomes.
3. **Harness home: a pure agent-layer loop; RookChat is a view.** The planner
   harness is a pure module family beside the PlanGraph/LM5 slices,
   deterministic-testable with a fake model, no chat imports. The RookChat
   service, MCP tools, and the future conductor all invoke the same loop.
   Chat-service-embedded and separate-process options were rejected.

---

## 3. The three-box architecture

```text
┌─ PLANNER BOX (Opus / Fable / Sonnet) ───────────────────────────┐
│ input:  task intent + PUSHED evidence                            │
│         (template catalog digest, capability summaries,          │
│          knowledge packets, canvas/scene digest,                 │
│          prior receipts when replanning)                         │
│ loop:   draft contract payload (LM4Y schema)                     │
│           -> load_workflow_contract_payload                      │
│           -> compile_workflow_contract                           │
│           -> structured diagnostics                              │
│           -> revise (bounded attempts)                           │
│ tools:  `planner` execution profile (LM2F, read-only)            │
│         + contract-validate as its one meta-action               │
│ output: compiled, fingerprinted contract.                        │
│         Its terminal act is an ARTIFACT, never a mutation.       │
└──────────────────────────┬───────────────────────────────────────┘
                           ▼
┌─ RUNNER BOX (no model — LM4S/LM4U, already live-proven) ────────┐
│ owns: node ordering, verifier gates, repair policy, budgets,     │
│       provenance receipts (LM4Z), escalation decisions,          │
│       replan-frontier halts                                      │
└──────────────────────────┬───────────────────────────────────────┘
                           ▼
┌─ WORKER BOX (Sonnet / Haiku / local — LM5A–I) ──────────────────┐
│ missing piece: the MODEL ADAPTER at the LM5I seam:               │
│   request envelope (LM5I) -> prompt + transport -> model call    │
│   -> response payload -> LM5G loader                             │
│ one adapter interface; LiteLLM / Ollama / LM Studio behind it    │
└──────────────────────────────────────────────────────────────────┘

escalation loop:
  worker clarification/refusal (LM5B)
    -> runner disposition + policy
    -> re-invoke PLANNER with receipts as evidence
    -> amended contract (new fingerprint, provenance links parent)
    -> runner resumes
```

### 3.1 Why this shape (the guidepost mapping)

**OpenProse/Reactor discipline, applied to planning.** Reactor's core move is
*intelligence frozen at compile time; the runtime reconciler is deliberately
dumb — there is no judge step, no LLM in the wake/commit decision*. Rook's
runner already obeys this. The planner box extends the same discipline upward:
the expensive model reasons **once** into a compiled artifact; nothing
model-shaped sits inside the execution loop. Reactor's postcondition-gated
commits map directly to Rook's verifier-gated nodes: a failed run commits
nothing, the prior state stands, and a receipt records why.

**RLM discipline, applied to the coordinator.** The RLM root model never holds
the whole environment in context — it holds metadata and probes slices
programmatically, and its history is metadata-only. The Rook analog: the
Planner's context is contract fingerprints, node status tables, digests, and
LM4Z receipts — **never worker transcripts**. When it needs detail it issues a
bounded read (a read-only tool call or a status drill-down), the way an RLM
root prints a slice. LM5A/LM5H already enforce the same posture at the worker
tier (current-node registers, summarized history, handles not blobs).

**Model tiers are a property of the box, not the harness.** The north-star
inversion ("for local models the scaffold is the planner; the model is a node
resolver") is structural. A Sonnet worker runs in the same LM5 box as a Haiku
or local worker; it just fails less. Opus/Fable/Sonnet at the planner tier and
Sonnet/Haiku/local at the worker tier are different **boxes**, not different
configurations of one harness. Model choice stays a swap (LiteLLM routing),
never a rearchitecture.

**The escalation loop is what makes "smart directing dumb" converge.** The RLM
paper's depth>1 failure mode is silent error propagation. Rook's mitigation is
structural: a worker cannot propagate errors upward silently, because its only
upward channel is a typed LM5B response, and the runner — not the worker —
decides whether that becomes a repair node, a replan, or a user question.

---

## 4. The Planner box

### 4.1 Planner turn context (mirror of LM5A, planner-tier)

The planner harness gets its own frozen context artifact, constructed by Rook
and pushed to the model — the planner-tier sibling of `LocalWorkerTurnContext`:

- task intent (user-level, verbatim-preserved);
- template catalog digest (ids, intents, node vocabularies, param schemas);
- capability summaries for the relevant tool families (from capability
  records / Capability Index, not raw schemas);
- scheduled knowledge packets (recipes, gotchas, soft ordering priors);
- canvas/scene digest when relevant (summary, not raw snapshot);
- on replan: the parent contract fingerprint, the receipt trail up to the
  frontier, and the rolling memory needed to plan the remainder.

Construction, validation, and freezing follow the LM5A pattern. The renderer
follows the LM5H pattern (strict schema-tagged JSON-ready payload, exact key
sets, no prompt text, no response protocol).

**Planner-envelope symmetry is a pattern, not a commitment.** The LM5I
request-envelope shape (context + response schema identity + machine-readable
contract description) is the natural template for an eventual planner request
envelope (planner context + contract payload schema + diagnostics contract).
No planner-envelope family is built before the first planner validation slice
proves what diagnostics and evidence actually need to look like.

### 4.2 The authoring loop

```text
planner turn context
  -> model drafts a contract payload (LM4Y schema)
  -> load_workflow_contract_payload (structural validation)
  -> compile_workflow_contract (semantic validation)
  -> on failure: structured diagnostics appended as evidence; bounded retry
  -> on success: CompiledWorkflowScaffold + LM4X fingerprint
  -> terminal artifact recorded with provenance
```

The compiler is the type-checker; the Planner iterates against it the way a
strong model iterates against a compiler. Diagnostics must therefore be
corrective in the C#-preflight style ("Declared output `B`; assign `B = ...`"),
not merely rejecting. Authoring attempts are bounded; exhausting the budget is
an escalation (to a stronger model or the user), not a loop.

### 4.3 Tool surface

The planner box consumes the LM2F `planner` execution profile: read-only
inspection and query tools, no mutation. Its one meta-action is
*validate-this-contract-payload* (the load+compile path run as a dry-run
action). The Planner never calls mutating tools; the runner and workers do.
This keeps "visible implies dispatchable" trivially true for the planner
profile and makes planner transcripts safe to replay.

**Discoverable metadata ≠ callable authority.** The Capability Index may help
the Planner discover possible `execution_ref`s and tool families; it must
never imply dispatch permission. Contract validation checks that references
exist; the runner and its action gates own execution authority. This is the
authoring-side complement of the LM north-star's visible-implies-dispatchable
rule, and it must hold even as the Capability Index and capability records
converge.

### 4.4 The staged authoring ladder

| Stage | Planner may write | Compiler/lint gates | Unlock gate |
|---|---|---|---|
| 1 | template selection + `InitialNodeParams` binding | existing LM4W validation | stage-1 decomposition eval suite green |
| 2 | multiple templates chained into one contract | LM4W + **mutation-verification lint** (warn) | stage-2 eval suite green |
| 3 | free nodes/edges/steps | LM4W + lint (fail) + expected-ref discipline | stage-3 eval suite green |

The **mutation-verification lint** encodes the doctrine in one rule, scoped by
node category:

> Every declared **mutating producer** must have a verifier, a terminal
> verifier, or an explicit declared deferred-verification reason.

Warning at stage 2; failure at stage 3. Non-mutating node categories are
exempt by construction: read-only/observer nodes, clarification/frontier
nodes, pure bind/planning nodes, and terminal/report nodes. The
deferred-verification escape must be declared in the contract (auditable),
mirroring the result-truth rule that verification may be explicitly deferred
but never silently skipped. The lint forces the Planner to decompose in the
create → verify → repair shape the runtime is built around, without teaching
planning style in prose.

The ladder converts "can the Planner plan?" from one large empirical bet into
three small ones, each with its own eval gate — consistent with the LM6
evaluation doctrine and with the topology doc's §12 instruction to de-risk the
load-bearing bet early.

### 4.5 Replan frontiers

A replan-frontier is a **declared contract marker interpreted by the runner —
not a node a worker resolves.** The existing runtime already has the precedent:
terminal nodes HALT at the provider without execution (LM4W's chain guard:
`done -> provider HALT, non-executed`). A replan-frontier is architecturally a
*non-terminal HALT with a replan disposition*. This keeps two facts that must
never be confused separate by construction:

```text
worker did something            (a worker turn, LM5 boundary)
runner reached a declared       (a runner halt/disposition,
  planning boundary               no model involved)
```

The frontier's re-entry contract is verifier-shaped:

- **precondition:** the runner has reached the frontier with receipts R;
- **effect:** the Planner is re-invoked with (parent fingerprint, R, rolling
  memory) as evidence;
- **postcondition:** an amended contract compiles, its fingerprint links the
  parent (LM4X lineage recorded via LM4Z provenance), and the runner resumes
  on the amendment.

Replan count is budgeted like repair (`bounded, then escalate`). The runner
stays model-free even during replanning: it *halts and requests*; the planner
box does the thinking; the artifact chain records the decision. Whether the
marker is later promoted to a first-class node kind is an implementation
question for the slice that builds it, not a commitment here.

---

## 5. The Worker box: the model adapter seam

**Update (2026-07-02, same day as this brainstorm): LM5I (PR #394, merge
`3271cc8f`) closed the deterministic half of this seam.**
`render_local_worker_turn_request_payload` in
`agent/local_worker_turn_request.py` composes the LM5H context payload, the
LM5G response schema identity, and a machine-readable response-contract
description (response kinds, per-kind field sets, required-nullable fields,
refusal categories) into one schema-tagged artifact:
`rook.local_worker_turn_request:v1`. The request envelope is the first
production layer allowed to compose the outbound context schema with the
inbound response schema — and it deliberately stops there.

The worker-side missing piece is therefore narrower than originally drafted:
a single adapter interface consuming the **request envelope**, not the raw
context payload:

```text
WorkerModelAdapter:
  input:  request envelope (rook.local_worker_turn_request:v1, LM5I)
          + prompt/transport policy
  output: response payload -> load_local_worker_turn_response_payload (LM5G)
```

The adapter's remaining scope is exactly the set of questions LM5I declines to
answer: how the prompt text is written, which model/provider runs, how raw
model output is parsed into a response payload — and nothing more
(admissibility stays with LM5G/LM5B validation and LM5C disposition; execution
stays with the runner).

**Scope of the claim:** LM5I makes the first real worker-model adapter slice
*possible without inventing any more transport shape*. That is not the same as
being one slice from reliable real-model execution, which additionally
requires:

- prompt/message artifact discipline (versioned, attributable);
- provider/raw-output failure handling (transport truth, never synthesized
  responses);
- deterministic/recorded adapter tests;
- model probe evals per the LM6 doctrine.

Requirements:

- one interface; LiteLLM-routed cloud models and Ollama/LM Studio local models
  are implementations behind it — the harness cannot tell which model ran;
- strict structured-output enforcement (schema-constrained decoding where the
  provider supports it; strict parse + LM5G loader rejection otherwise);
- no progressive disclosure, no streaming conversation, no tool loop — the
  worker sees `allowed_actions` from the payload and answers with exactly one
  typed response;
- adapter failures are transport-status facts, never synthesized responses.

Prompt *text* rendering (turning the LM5I envelope into model-facing
instructions) is the adapter's concern, per LM5H §11 and LM5I's layer split.
Prompt text is a versioned artifact so worker evals are attributable. Note
that the envelope's machine-readable `response_contract` means the prompt
layer can be largely mechanical — describing the contract rather than
inventing it — which shrinks the surface where prompt drift can diverge from
the validated schema.

### 5.1 Next empirical pressure (decided 2026-07-02)

The worker-model adapter is the next empirical pressure — chosen over
`workflow_validate`-first and over both-in-parallel, so the first real-model
signal stays clean (one seam under test, failures attributable). The first
slice is a **narrow adapter/probe boundary, not a broad worker loop**. The
question it answers is exactly:

> Given a real LM5I request envelope from the hand-authored repair workflow,
> can a model produce a strict LM5G-loadable response payload that passes
> LM5B/C/D/F evaluation?

Explicitly out of scope for that slice: dispatch, graph mutation, stream
continuation, `workflow_validate`, planner contract authoring. Just the first
real worker behind the already-built worker box.

Candidate naming (the slice's own spec decides): `LM5J` as a single
model-adapter probe, or `LM5J` (worker adapter contract, non-live seam) +
`LM5K` (first model probe) if one more deterministic seam is wanted first.

`workflow_validate` is expected to be the first Planner-Harness slice *after*
an initial worker-model read exists.

### 5.2 Addendum: evidence through LM7E and next pressure (2026-07-08)

The LM5-LM7 campaign has now discharged the original worker/planner harness
pressure in a stronger form than this section anticipated:

- the bounded worker path reached live Rhino/GH repair and verification;
- the bounded retry variant was added without changing the default protocol;
- a `PlannerWorkerContractRequest:v1` can head the live provenance chain;
- a Planner-tier model can author that request under shape guidance;
- the model-authored request can drive the frozen worker splice to a live
  `verify_repair_succeeded` receipt.

The next empirical pressure is therefore no longer "can the worker-model
adapter work?" or "can the planner handoff surface work?" It is whether the
same protocol transfers to a second task family without confusing domain
transfer with complexity growth.

LM8 opens that pressure with a GH-native scalar solve/output expectation family.
After the first receipted scalar run, the preferred discipline is to pressure
the scalar family before broadening: non-identity scalar relations, numeric
tolerance, multiple candidate scalar targets, multi-fact criteria, and
repeatability should come before missing-wire repair, component replacement,
small edit batches, or a router. A router becomes evidence-driven once multiple
families expose stable differences in model/task assignment; it should not be
introduced merely because one exploratory local Planner row succeeded.

### 5.3 Addendum: LM8 closure and semantic-recipe pressure (2026-07-10)

LM8 discharged the second-family and same-family-depth questions. The bounded
worker path transferred from script repair to GH-native scalar mutation,
progressed from identity through non-identity and affine projection, and
repeated the affine case `20/20`. LM8K then replaced the measured settle-read
seam with a managed Grasshopper solve-readiness receipt; LM8M repeated the
affine case `20/20` with one managed wait and one receipt-fenced output read per
child, zero settle reads, and no provenance discrepancies.

The next pressure belongs above the worker box. It is not another arithmetic
step and not a router. It is whether the existing Planner box can produce a
validated semantic source artifact for graph construction. A fixed compiler
program may then use bounded intelligent delegates for representation and
semantic lowering, while a deterministic harness validates the resulting IR
before mechanical execution.

Candidate slice:

```text
LM9A = Planner Graph Recipe Surface
```

The first fixture should remain the previously discussed `10 x 10` radial box
height field. The Planner owns the semantic goal, requirements, maintained
truth, explicit assumptions, unresolved intent, invariants, verifier
expectations, capability boundary, and any bounded worker slots. The compile
layer owns representation decisions and exact tool/verifier IR, including
script/template choice, short IDs, temp IDs, epochs, GUIDs, connections, and
`gh_edit` batches. Compile-time model judgment is narrower than Planner judgment
and must emit schema-bounded, provenance-linked artifacts that deterministic IR
validation can reject. A worker may fill a declared formula or script-body slot,
but does not author the batch.

LM9A should introduce this recipe as a sibling Stage-1 semantic artifact inside
the existing Planner harness, rather than overloading the worker-specific
`PlannerWorkerContractRequest:v1` or creating a second Planner. The first slice
is offline and deterministic: schema, validator, fixture, diagnostics, and
proof tests only. Model authorship and live execution remain separate evidence
questions.

Before a later live recipe-to-`gh_edit` run, the `gh_edit` mutation path must
emit or participate in a managed solve-readiness receipt so the verifier can
make the same freshness claim proven by LM8K/LM8M. That prerequisite does not
block the LM9A authoring surface or a following bounded-intelligent-compile and
deterministic-IR-validation slice.

---

## 6. Two plan tiers and RLM depth

The macro `Plan`/`TaskSpec` (agent/conductor tier) and the micro
`RookWorkflowContract` (workflow tier) are **depth levels, not competitors**:

```text
root Planner (macro)           — decomposes across sessions/files
  -> TaskSpec[n]               — each eventually carries/references
       a compiled workflow contract (micro)
         -> PlanGraph nodes    — each resolved by a bounded worker turn
```

- `TaskSpec.postconditions` are macro-level verifier gates; the micro
  contract's terminal receipt is what satisfies them.
- A **`subworkflow` node kind** ("compile and run this child contract; return
  its terminal receipt") is the recursion primitive. It is named roadmap here,
  not scheduled — an **LM6/LM7-horizon concept**, firmly out of near-term
  planner-harness and worker-adapter slices; it becomes eligible only after
  contract authoring, validation, and worker-adapter evidence exist.
- **Recursion is capped at depth 1** initially, per the RLM paper's
  error-propagation finding. Rook's typed escalation is the mitigation the
  paper lacks, but the cap stands until evals justify more.

This is the LM7/topology fan-out story expressed in artifacts that already
exist; the point of naming it now is to prevent a second competing planner
from being built at either tier.

---

## 7. External coordinators converge on the same contract

Claude Code, Codex, and other harnesses engage through **MCP tools over the
same contract layer** — the internal planner harness and external coordinators
converge on the same LM4Y payload and the same compiler, so internal-first does
not fork the contract:

| Tool (naming illustrative) | Role |
|---|---|
| template/capability discovery (reuse `rook_tools_*`) | what exists to compose |
| `workflow_validate` | dry-run load+compile; returns compiled summary (fingerprint, node table) or structured diagnostics; pure, no execution |
| `workflow_run` | compile + execute under the runner; returns run id |
| `workflow_status` / events | LM4Z provenance, receipts, current node, escalations |
| `workflow_answer` / `workflow_abort` | respond to escalations (mirrors `agent_answer`/`agent_abort`) |

`workflow_validate` is the load-bearing affordance: it lets any external model
iterate to a correct contract without touching Rhino. Escalations (worker
clarification/refusal surfaced through status) are part of the external
contract — that is the fan-in of structured failure the topology doc promises
the macro tier (LM7 exit criteria).

**`workflow_validate` is not the internal planner harness.** The two must not
become the same module by accident. They share the compiler, nothing more:

```text
External coordinator affordance:
  workflow_validate(payload) -> compiled summary | diagnostics

Internal Planner harness:
  planner context -> model draft -> validate/compile
    -> attempt receipt -> compiled artifact
```

The external tool is a stateless dry-run over the load+compile path. The
internal harness owns planner context construction, evidence push, bounded
retry, attempt receipts, and escalation — none of which belong in an MCP tool.

RookChat's role: the panel is the Planner's conversational front-end. The user
talks to the Planner model; contract authoring happens behind the
conversation; execution streams back as runner events (LM4S already streams).
The chat is a **view** over the planner box, not the harness.

---

## 8. Long-running tasks: depth from RLM, duration from OpenProse

The two guideposts answer different axes:

- **RLM answers depth** — one large task decomposed recursively. Rook adopts:
  receipts-not-transcripts planner context (§3.1), the `subworkflow` node kind
  (§6), the depth-1 cap, and decomposition-first evals (§9).
- **OpenProse/Reactor answers duration** — standing truth re-rendered only on
  surprise. Rook adopts the **pattern, not the dependency**: represent a
  standing deliverable as **published (canonical) state** whose facets are
  maintained by workflow contracts, memo-keyed by **LM4X contract fingerprint
  + input artifact fingerprints**, with LM4Z receipts as the ledger. The
  expensive Planner then fires only when something material moved — inference
  cost scales with surprise, not wall-clock, which is what the two-tier
  economic gradient needs at campaign timescales. (Vocabulary note: Rook docs
  say *published/canonical state* where OpenProse says "world-model" — same
  concept, engineer-plain term.)

Fingerprint-keyed memoization of workflow runs ("do not re-run a contract
whose fingerprint and material inputs are unchanged") is the single cheapest
Reactor idea to adopt and is named roadmap. Whether Reactor itself ever hosts
Rook contracts as a runtime is explicitly deferred until after real-model
evidence exists.

---

## 9. Evaluation doctrine for the planner tier

Extending the LM north-star's evaluation doctrine (its §11 / phase LM6) upward:

- **Decomposition-first.** The first real-model evals measure whether the
  Planner picks the right template/chain and binds the right params — before
  execution-quality evals. (RLM: the first decomposition choice dominates.)
- **Deterministic harness.** The planner loop is testable with a fake model
  exactly as LM5D/LM5F test the worker box: scenario suites of
  (intent, evidence) → expected contract properties (selected template, node
  count, verifier coverage, fingerprint stability), no live model in merge
  gates.
- **Failure taxonomy extension.** Add planner-tier classes to the existing
  taxonomy: template selection failure, binding failure, contract mechanics
  failure (compiles only after N diagnostics), decomposition failure (compiles
  but wrong shape), replan failure.
- **Attributability.** Stage gates (§4.4) exist so a failure is attributable
  to decomposition vs contract mechanics vs worker execution — never "the
  multi-agent system failed."

---

## 10. Anti-goals

- No model inside the runner box — the wake/commit/ordering decisions stay
  deterministic (no judge step).
- No `ChatRunner` reuse for the planner loop; no progressive tool disclosure
  or conversational tool loop inside either the planner or worker boxes.
- No worker-authored graph mutation; workers answer, the runner decides.
- No recursion beyond depth 1 until evals justify it.
- No second planner at either tier; macro `Plan` and micro contract are the
  same system at two depths.
- No per-harness external integrations; externals get the contract tools, not
  bespoke bridges.
- No Reactor runtime dependency in this horizon; adopt fingerprint-memoization
  and receipts as patterns.
- No implementation work from this document without per-slice specs and
  explicit approval.

---

## 11. Open questions (deliberately unresolved)

1. **Evidence-push composition:** exactly which digests/knowledge packets the
   planner context carries per task family, and their budgets. Needs the LM5A
   pattern applied planner-side against real tasks.
2. **Amendment mechanics:** whether a replan emits a full new contract or a
   validated subgraph patch. Full recompile is simpler and fingerprint-clean;
   patches preserve more runner state. Recommendation to test first: full
   recompile of the remainder.
3. **Memo-key composition for run memoization:** contract fingerprint is
   settled (LM4X); what constitutes "material inputs" (document state digest?
   artifact fingerprints?) is not.
4. **Planner-tier phase naming:** suggested prefix `PH` (Planner Harness) to
   avoid colliding with LM/P phases; to be confirmed when slicing begins.
5. **Chat streaming surface:** how planner-box activity (drafts, diagnostics,
   compiled summary) renders in the RookChat panel without leaking prompt
   internals into conversation state.

---

## 12. Decision log

- The contract payload is the interface; the missing pieces are the authoring
  loop (planner box) and the model adapter (worker seam) — not a new protocol.
- The planner harness is a third harness shape: an artifact-producing loop,
  distinct from `ChatRunner` and from the LM5 worker box.
- **Plan-then-execute with declared replan frontiers** is the spine;
  interleaving is a declared contract marker, not a harness mode (user
  decision, 2026-07-02). Early implementation: a runner halt/disposition in
  the terminal-HALT family, not a worker-resolved node (review round 1).
- **Staged authoring ladder** (select+bind → chain → free authoring), each
  stage gated by decomposition evals (user decision, 2026-07-02).
- **Agent-layer pure loop; RookChat is a view** (user decision, 2026-07-02).
- The LM2F `planner` execution profile is the planner box's tool envelope.
- Model tier assignment (Opus/Fable/Sonnet planning; Sonnet/Haiku/local
  working) is a property of the box, not the harness; adapters make model
  choice a swap.
- Escalation is typed and flows worker → runner → planner as receipts;
  transcripts never travel upward.
- Macro `Plan`/`TaskSpec` and micro `RookWorkflowContract` are depth levels;
  `subworkflow` is the depth-1 recursion primitive; depth is capped at 1.
- Externals converge via MCP contract tools (`workflow_validate` is
  load-bearing); internal-first does not fork the contract.
- RLM supplies the depth doctrine; OpenProse supplies the duration doctrine
  (fingerprint memoization + receipts adopted as patterns, Reactor runtime
  deferred). Rook docs say *published/canonical state*, not "world-model"
  (review round 1).
- **Mutation-verification lint:** every declared mutating producer needs a
  verifier, terminal verifier, or explicit declared deferred-verification
  reason; non-mutating node categories exempt (review round 1 refinement).
- **Discoverable metadata ≠ callable authority:** the Capability Index informs
  authoring; the runner/action gates own execution authority (review round 1).
- `workflow_validate` (external, stateless) and the internal planner harness
  share the compiler, never a module (review round 1).
- LM5I makes the first worker-adapter slice possible without new transport
  shape; reliable real-model execution additionally needs prompt artifact
  discipline, failure handling, recorded adapter tests, and probe evals
  (review round 1).
- Planner-envelope symmetry with LM5I is a pattern, not scheduled scope
  (review round 1).
- **Next empirical pressure: the worker-model adapter, as a narrow probe**
  ("can a model produce a strict LM5G-loadable response to a real LM5I
  envelope that passes LM5B/C/D/F?") — no dispatch, no graph mutation, no
  stream continuation. Not `workflow_validate` first (tests the safer
  planner-side bet), not both-in-parallel (blurs failure attribution).
  `workflow_validate` follows once an initial worker-model read exists (user
  decision, 2026-07-02).
- **LM8 closes the current worker-family qualification line.** The scalar
  family transferred, deepened, repeated, and migrated to managed
  receipt-fenced verification without changing bounded worker authority
  (2026-07-10 addendum).
- **LM9 pressure moves to Planner semantic contracts, bounded intelligent
  compile, and deterministic IR validation.** The Planner authors meaning; a
  fixed compiler program delegates narrower representation and lowering
  judgments, then accepts only schema-valid, provenance-linked exact execution
  IR. Router policy remains deferred (2026-07-10 addendum).

---

## Appendix A — Branching points considered (2026-07-02 session)

The forks below are recorded verbatim-in-substance so the roads not taken stay
visible when this architecture is revisited. **Chosen answers are marked
`✅ CHOSEN`.** Rejected options are not wrong forever; they are wrong for this
horizon, for the stated reasons.

### A.0 System entry point: external-first vs internal harness

*Asked in the opening assessment as "Where does the Planner run first?"; the
user resolved this in prose rather than from the option list.*

- **External frontier model authoring contracts via MCP first** — Claude
  Desktop / Claude Code / Codex as the macro coordinator per the topology
  north-star; cheapest to ship, exercises the same contract surface, defers
  model-adapter work. *(Assistant's original recommendation.)*
- ✅ **CHOSEN: Rook-internal harness first (the RookChat angle).** Claude Code
  and Codex already have solid harnesses; Rook builds its own internal harness
  where the Planner-level model may be Opus/Fable/Sonnet and the worker-level
  model may be Sonnet/Haiku/local. Deferring work was explicitly *not* the
  concern; shaping the architecture was. Externals still converge on the same
  contract layer via MCP tools (§7), so this choice does not fork the
  contract.

### A.1 Planner loop shape

*Question: "How should the Planner box relate to execution — whole contract up
front, or interleaved node proposal?"*

- ✅ **CHOSEN: Plan-then-execute + replan nodes** *(recommended)* — Planner
  compiles a full contract up front (LM4W path). Contracts may contain
  explicit "replan frontier" nodes where the runner halts and re-invokes the
  planner with accumulated receipts. Interleaved behavior becomes a declared,
  auditable choice inside the artifact rather than a second harness mode.
- **Strict plan-then-execute** — whole contract up front; planner re-enters
  only on escalation (worker refusal, verifier failure past repair budget).
  Simplest, most deterministic, most memoizable — but open-ended design tasks
  must be decomposed into multiple sequential contracts by hand.
- **Interleaved proposal as the spine** — planner proposes each next node via
  the LM4N/LM4O propose→revalidate path as evidence accumulates. Most adaptive
  for exploratory design work, but the plan is never a complete artifact —
  weaker replay, memoization, and fingerprint semantics; a model sits closer
  to the execution loop.
- **Both as peer modes** — ship both loops behind the planner harness and let
  task type select the mode. Maximum flexibility but two loops to test, eval,
  and keep coherent — and the mode-selection policy itself becomes a new
  design problem.

### A.2 Authoring altitude

*Question: "What vocabulary does the Planner compose contracts from — what can
it write into a `RookWorkflowContract`?"*

- ✅ **CHOSEN: Staged ladder, gated by evals** *(recommended)* — Stage 1:
  select a template + bind initial params (`select_template`/LM4K binding
  already exist). Stage 2: chain multiple templates into one contract.
  Stage 3: free node authoring against the compiler. Each stage ships with its
  own decomposition eval suite before the next unlocks. Matches the RLM
  finding that first-decomposition quality dominates outcomes.
- **Templates only, indefinitely** — planner never authors nodes; it only
  selects and parameterizes registry templates. Maximum safety and
  evaluability, but the template library becomes the bottleneck — every new
  workflow shape needs a human-authored template first, and the smart model's
  composition ability goes unused.
- **Free node authoring from day one** — planner composes arbitrary
  nodes/edges/steps immediately; the LM4W compiler plus an added
  "no unverified mutation nodes" lint are the only gates. Exercises
  frontier-model strength fully, but evals can't distinguish bad decomposition
  from bad contract mechanics, and early failures are hard to attribute.

### A.3 Harness home

*Question: "Where does the Planner harness live, and how does RookChat relate
to it?"*

- ✅ **CHOSEN: Agent-layer loop; chat is a view** *(recommended)* — a pure
  module family beside the PlanGraph/LM5 slices (e.g.
  `agent/planner_turn_*.py`): frozen planner-turn context, authoring loop,
  compile diagnostics feedback — deterministic-testable with a fake model, no
  chat imports. The RookChat service, MCP tools, and the future conductor all
  invoke the same loop. Matches the LM campaign's pure-module discipline.
- **Built into the chat service** — extend `ChatRunner`/the chat server with a
  planner mode. Fastest path to a demo in the panel, but couples the planner
  loop to conversation state, streaming, and the chat service process — harder
  to test deterministically and unusable from conductor/MCP without the chat
  runtime.
- **Separate planner service/process** — a standalone process like the chat
  server with its own discovery file and HTTP surface. Cleanest isolation and
  independent lifecycle, but adds a process, port discovery, and deployment
  surface before any evidence justifies it.
