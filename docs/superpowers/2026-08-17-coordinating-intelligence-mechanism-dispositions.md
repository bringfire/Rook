# Coordinating Intelligence Mechanism Dispositions

**Status:** Historical disposition pass; narrowed by the architectural reset

> These dispositions remain evidence about individual mechanisms. Current
> runtime authority and the next experiment are governed by
> `docs/superpowers/2026-08-17-coordinating-intelligence-architectural-reset.md`.
> Where this document implies deterministic semantic acceptance in the ordinary
> runtime, the reset's closed-semantics boundary controls.

**Disposition date:** 2026-08-17

**Inputs:**

- `docs/superpowers/2026-08-17-coordinating-intelligence-evidence-ledger.md`
  at commit `855f98d5`;
- `docs/superpowers/2026-08-17-coordinating-intelligence-claims-and-responsibility-map.md`
  at commit `13ade0fc`.

## 1. Purpose

This document assigns an evidence-backed disposition to mechanisms that have
appeared in Rook's coordinating-intelligence work. It determines what may enter
a later architecture comparison as an established part, a narrowed part, an
adoption-blocked part, an experiment, a suspended proposal, or a superseded
path.

It does not compose those mechanisms into a target architecture. It does not
authorize code changes, product integration, new model calls, or another test
campaign.

## 2. Disposition Rules

### 2.1 Closed dispositions

| Disposition | Meaning |
|---|---|
| `retain-as-substrate` | Evidence supports building upon the mechanism inside its stated boundary. |
| `retain-but-narrow` | The mechanism is useful, but must not absorb broader responsibility implied by earlier designs. |
| `repair-before-adoption` | The mechanism answers a real need, but a known ownership, custody, lifecycle, or integration condition blocks product adoption. |
| `continue-experimentally` | The mechanism has evidence of value and one specific unresolved question worth testing. |
| `suspend` | No further implementation or qualification is justified until a named external result changes the evidence. |
| `retire-or-supersede` | A better owner now exists or the mechanism encodes an obsolete contract. It should not re-enter later architecture comparison as an active option. |

### 2.2 Interpretation constraints

1. A retained mechanism retains only its qualified boundary.
2. A successful experiment is not automatically retained production substrate.
3. A suspended package may contain individual mechanisms with different
   dispositions.
4. A disposition is reversible when named evidence changes.
5. Experimental continuation must answer one architectural question rather than
   accumulate prompts or examples indefinitely.
6. No mechanism receives credit for another mechanism's result.
7. Current code, reviewed branch-local work, disposable artifacts, and design
   proposals remain separate states.

## 3. Disposition Summary

| Disposition | Mechanism IDs |
|---|---|
| `retain-as-substrate` | `MD-01` through `MD-05` |
| `retain-but-narrow` | `MD-06` through `MD-09` |
| `repair-before-adoption` | `MD-10` |
| `continue-experimentally` | `MD-11` through `MD-17` |
| `suspend` | `MD-18`, `MD-19` |
| `retire-or-supersede` | `MD-20`, `MD-21` |

## 4. Retain As Substrate

### MD-01: Bounded Worker box

**Current state:** Current modules with repeated historical qualification.

**Disposition:** `retain-as-substrate`

**Smallest coherent role:** Execute or decline one externally bounded repair,
transformation, or leaf task using exact context, allowed actions, and
verification supplied outside the model.

**Why:** The Worker repeatedly obeyed evidence conditions, produced strict
responses, performed scalar transformations, and repaired a real compile
failure. Its boundary is clearer and more repeatedly exercised than the general
Planner boundary.

**Must not own:** Open-ended intent interpretation, whole-definition planning,
workflow routing, acceptance-policy construction, or self-verification.

**Evidence-change trigger:** Broaden only after a new task family preserves the
same bounded contract without moving planning or acceptance into the Worker.

**Basis:** `CI-01`; `WRK-01` through `WRK-08`.

### MD-02: Canonical gateway, structured results, and strict admission

**Current state:** Merged Rook production behavior with focused passing tests.

**Disposition:** `retain-as-substrate`

**Smallest coherent role:** Provide a closed public capability boundary with
strict arguments, exact structured results and failures, preserved legacy text,
canonical tracing, and no private or dynamic bypass.

**Why:** This boundary removed catalog exposure, malformed-argument
degradation, text-only failure evidence, and cross-route projection drift.

**Must not own:** Semantic planning, component selection, or interpretation of
whether a successful capability result satisfies the user.

**Evidence-change trigger:** Revisit only when a new model-facing route cannot
preserve the same admission and evidence equations.

**Basis:** `CI-02`, `CI-05`; `GWY-01` through `GWY-03`; `PRM-02`.

### MD-03: Native component discovery and identity handoff

**Current state:** Merged production behavior, current tests, and live
post-merge qualification on one installed Grasshopper catalog.

**Disposition:** `retain-as-substrate`

**Smallest coherent role:** Rank live registered components natively, preserve
eligible duplicate identities, expose concise provenance, and hand a selected
GUID to authoritative metadata and execution identities.

**Why:** The mechanism has direct host evidence, third-party specimens,
duplicate-name coverage, direct GUID metadata, and a successful five-call live
qualification.

**Must not own:** Model search strategy, semantic component choice, portable
package identity that the host does not expose, or knowledge-based preference
for native versus third-party candidates.

**Evidence-change trigger:** Revisit provenance variants when another source
kind is observed, not by inventing speculative package schemes.

**Basis:** `CI-03`; `DSC-01` through `DSC-04`; ledger section 24.

### MD-04: Mutation receipts, solve readiness, and fenced observation

**Current state:** Merged managed/Rook behavior with focused tests and live
model-free and model-authored use.

**Disposition:** `retain-as-substrate`

**Smallest coherent role:** Correlate a covered terminal mutation to document,
mutation epoch, completed solution epoch, supersession state, and a read that
refuses stale or unrelated evidence.

**Why:** This is the strongest available answer to computationally stale
Grasshopper observation. It enabled exact perturb/restore evidence and prevented
plausible but unfenced graphs from being accepted.

**Must not own:** Semantic acceptance, synchronous solving, sleep-based guesses,
or claims about mutations outside the admitted route and trace boundary.

**Evidence-change trigger:** Extend route coverage only when a canonical
terminal mutation lacks equivalent freshness custody.

**Basis:** `CI-02`; `RCP-01` through `RCP-09`; ledger sections 20 and 22.2.

### MD-05: Empirical qualification and evidence custody process

**Current state:** Development process represented by frozen rows, manifests,
raw traces, independent inspections, and the evidence ledger. It is not a
shipped runtime feature.

**Disposition:** `retain-as-substrate`

**Smallest coherent role:** Compare model/runtime configurations through exact
inputs, retained outputs, truthful lifecycle, independent runtime evidence, and
bounded claims that distinguish model, product, operator, and orchestration
failures.

**Why:** This process repeatedly exposed incorrect assumptions about model
ability, host APIs, deployment custody, tool ergonomics, acceptance rules, and
Reviewer sensitivity.

**Must not own:** Production user routing, benchmark theater, exhaustive prompt
enumeration, or automatic promotion of an experiment into architecture.

**Evidence-change trigger:** Refine the process when it cannot distinguish a
new causal owner, not by adding ceremony that does not alter the scientific
claim.

**Basis:** `CI-04` through `CI-06`, `CI-17`, `CI-18`; incident register;
ledger sections 18-23.

## 5. Retain But Narrow

### MD-06: Deterministic PlanGraph and execution representation

**Current state:** Current modules and active roadmap; bounded compositional
live witnesses exist.

**Disposition:** `retain-but-narrow`

**Smallest coherent role:** Represent admitted execution dependencies,
identities, interfaces, and deterministic sequencing after semantic choices
have been made.

**Why:** Compositional slices materialized distinct graphs and joined one Worker
leaf to a deterministic region. The representation is useful where exact GUID,
port, and receipt identities are known.

**Must not own:** Universal semantic intent, acceptance meaning, user
clarification, or a complete world model. Retrospective recipe shapes that omit
host identities are not authoritative execution plans.

**Evidence-change trigger:** Broaden only through a prospective task that needs
a new generic execution relation, not a domain-specific semantic label.

**Basis:** `CMP-04` through `CMP-06`; `CUR-04`; `CI-02`, `CI-16`.

### MD-07: Common deterministic behavioral acceptance core

**Current state:** Merged Python module with 105 focused passing tests, seven
recognized predicates, and current task-family use. The module combines several
responsibilities in 2,177 nonblank lines.

**Disposition:** `retain-but-narrow`

**Smallest coherent role:** Admit authentic source traces and receipts, perform
bounded perturb/restore probes, project supported observations, evaluate a
small closed relation vocabulary, and return pass/fail/unproven without guessing.

**Why:** It has caught false completion, verified causal controls, and enabled
repair. Its trace/probe/restoration responsibilities are more general than any
one point-row artifact.

**Must not own:** Interpretation of arbitrary user intent, automatic invention
of predicates, qualitative judgment, or a promise to cover all Grasshopper
geometry. New task labels must not enter the generic kernel as predicates.

**Evidence-change trigger:** Add or extract an evidence operation only after a
recurring observable gap appears across structurally distinct tasks. Module
ownership should be reassessed before substantial domain growth.

**Basis:** `CI-08`, `CI-11`, `CI-18`; `ACC-01` through `ACC-05`; `OPEN-04`,
`OPEN-11`.

### MD-08: Bounded evidence-driven repair loop

**Current state:** Disposable harness behavior with repeated point-row success
and one failed grid repair; not a general product loop.

**Disposition:** `retain-but-narrow`

**Smallest coherent role:** When authentic evaluation yields a complete and
repair-eligible failure, return exact criterion evidence to the same Actor and
permit a small policy-bounded correction followed by fresh receipt-fenced
evaluation.

**Why:** Three bounded corrections converted near misses into passes without
operator topology advice. The mechanism preserves the model's opportunity to
reason from evidence.

**Must not own:** Infinite retries, repair after incomplete custody, automatic
reinterpretation of user intent, or claims of general wrong-topology recovery.

**Evidence-change trigger:** Change correction limits only from observed repair
trajectories and cost, not an assumed universal number. A new topology-repair
result would materially broaden the evidence.

**Basis:** `CI-08`; `ACC-02`, `ACC-03`, `ACC-07`; ledger section 22.2.

### MD-09: Knowledge graph, retrieval, and injection

**Current state:** Current production mechanisms and documentation; two focused
tests encode stale operation mappings. No controlled positive contribution was
located for the later Prime/Qwen workflows.

**Disposition:** `retain-but-narrow`

**Smallest coherent role:** Supply provenance-bearing advisory priors or
project-specific context where live runtime evidence is absent or expensive.

**Why:** Domain knowledge can plausibly reduce rediscovery and compensate for
model sparsity, but this corpus does not measure that benefit. Authoritative
discovery correctly excludes unrelated hints.

**Must not own:** Installed component identity, port truth, mutation outcome,
solve state, geometry truth, or silent injection into authoritative discovery
tools. It receives no assumed credit for model success.

**Evidence-change trigger:** Before expansion, run one controlled comparison on
a demonstrated model knowledge gap and measure outcome quality, calls, latency,
and stale-prior failures. Repair current stale tests independently of any
architecture claim.

**Basis:** `CI-15`; `KG-01` through `KG-03`; ledger sections 20.2 and 26.

## 6. Repair Before Adoption

### MD-10: Prime as a production coordination host

**Current state:** Useful experimental runtime. Later rows require reviewed fork
merge `27b5be22`; the structured-error behavior is absent from the observed
Prime upstream. Lifecycle and efficiency concerns remain.

**Disposition:** `repair-before-adoption`

**Smallest coherent role after repair:** Provide persistent model reasoning,
IPython state, role-scoped sessions, canonical tool access, terminal lifecycle,
and resumable evidence for an outer workflow owner.

**Why:** Prime enabled long-lived exploration and same-session correction across
models. It also exposed incomplete terminal streams, fork custody, adapter
failures, and high operational variance.

**Must not own:** Rook runtime truth, hidden recovery from failed mutations,
implicit acceptance, or product adoption through an untracked fork.

**Adoption prerequisites:** Decide fork/upstream custody; preserve structured
MCP failure evidence in the effective runtime; establish terminal lifecycle
semantics; verify actual import/runtime identity; and measure session/call
overhead under the intended product mode.

**Evidence-change trigger:** Reclassify only after those prerequisites pass in
one owned integration lane. Experiments may continue on explicitly frozen fork
bytes meanwhile.

**Basis:** `CI-10`; `PRM-01`, `PRM-02`; ledger sections 19.2, 22, and 23.

## 7. Continue Experimentally

### MD-11: Qwen3.8 as a grounded Grasshopper Actor

**Current state:** Locally installed model with several successful disposable
qualifications; no fixed product role.

**Disposition:** `continue-experimentally`

**Smallest coherent role:** Interpret an open Grasshopper request, discover and
inspect live capabilities, construct topology through canonical Rook tools,
observe the solved result, and correct itself within bounded policy.

**Why:** Exact row, open row, open grid, and helix results demonstrate more than
leaf execution. The evidence supports continued Actor-level qualification.

**Must not own:** Self-certification, runtime truth, unrestricted mutation,
acceptance-policy authority, or claims of broad reliability from four tasks.

**Evidence-change trigger:** The next useful result should test a structurally
different task and classify the failure mode, not repeat many paraphrases of an
existing point/grid/helix family.

**Basis:** `CI-04`, `CI-06` through `CI-09`; `MOD-07`, `MOD-08`.

### MD-12: Payload-first `rook_full` adapter contract

**Current state:** Successful disposable V5 adapter and skill; not Rook or Prime
product code.

**Disposition:** `continue-experimentally`

**Smallest coherent role:** Preserve exact protocol envelopes in evidence while
returning exact capability payloads to model-authored Python, with authentic
failures re-raised unchanged.

**Why:** The contract removed V4's envelope confusion and V5 passed after one
semantic repair. It gives models idiomatic values without sacrificing custody.

**Must not own:** MCP protocol truth, copied capability schemas, retries,
normalization, or exception-text parsing.

**Evidence-change trigger:** Determine the durable API owner and prove direct,
gateway, structured-failure, malformed-envelope, and mutable-payload behavior
there before adoption.

**Basis:** `CI-05`; `ACC-06`, `ACC-07`; `INC-13`.

### MD-13: Compositional semantic design graph and compiler

**Current state:** Current modules and active roadmap with two bounded live
composition slices; generality unqualified.

**Disposition:** `continue-experimentally`

**Smallest coherent role:** Let a model express semantic design choices in a
small prospective representation, then lower admitted regions into exact
execution identities and bounded Worker leaves.

**Why:** The slices demonstrated distinct topology and one Worker/deterministic
composition. The representation-fit audit also identified why a retrospective
recipe graph was insufficient.

**Must not own:** Universal IR status, hidden host identity inference,
acceptance semantics, or automatic execution after partial lowering.

**Evidence-change trigger:** One prospective open task must demonstrate that the
representation reduces model burden or improves correction compared with the
direct Actor path. Otherwise it remains an additional translation layer without
measured benefit.

**Basis:** `CMP-01` through `CMP-06`; `CUR-04`; `CI-16`.

### MD-14: Phase A typed semantic-manifest compiler

**Current state:** Branch-local disposable compiler qualification; no runtime
evaluation or production implementation.

**Disposition:** `continue-experimentally`

**Smallest coherent role:** Mechanically validate model-authored acceptance
proposals for references, types, projections, quantification, operation
signatures, authority compatibility, tolerances, and budgets.

**Why:** Phase A establishes coherent deterministic admission and precise
diagnostics for its frozen language.

**Must not own:** Intent adequacy, operation-catalog completeness, runtime
evidence collection, qualitative semantics, or final acceptance.

**Evidence-change trigger:** Continue only through a Constructor-produced
artifact for a second structurally different intent and an evaluator that uses
the compiled form against authentic runtime evidence. Do not expand the
language before that handoff exists.

**Basis:** `CI-11`, `CI-12`; `PH-03`, `PH-04`; ledger section 25.1.

### MD-15: Acceptance-contract Constructor role

**Current state:** Two offline attempts. The first failed mechanical admission;
one continuation repaired references, but semantic adequacy was not established.

**Disposition:** `continue-experimentally`

**Smallest coherent role:** Propose observable claims, authority assignments,
supported deterministic expressions, and explicitly disclosed residuals from
the user's intent and admitted evidence vocabulary.

**Why:** Product-time construction is one plausible way to avoid shipping a
bespoke acceptance artifact for every task. The current handoff result is too
weak to adopt or discard the role.

**Must not own:** Its own compiler rules, silent vocabulary extension,
unreviewed weakening of requirements, or final acceptance of its proposal.

**Evidence-change trigger:** Test whether a fresh Constructor can produce one
mechanically valid and semantically adequate artifact without frontier-model
repair, using a task different from point rows. One bounded diagnostic
continuation may be measured separately.

**Basis:** `CI-17`; `PH-01` through `PH-04`; `OPEN-04`.

### MD-16: Independent Reviewer or Critic role

**Current state:** One failed offline critic qualification and one six-case
Phase B corpus showing useful but insufficient Qwen Reviewer sensitivity.

**Disposition:** `continue-experimentally`

**Smallest coherent role:** Provide attributed advisory judgment about omitted
requirements, invented assumptions, material weakening, authority errors, and
unresolved semantic risk after mechanical admission.

**Why:** The Reviewer added information beyond the compiler and showed restraint
on the coherent control, but missed two required sensitivity classes.

**Must not own:** Final semantic authority, deterministic facts, hidden oracle
knowledge, or automatic mutation. `Adequate` is not a mechanical pass.

**Evidence-change trigger:** Any next test should target the two observed blind
spots and model-family independence, not grow an open-ended defect taxonomy.
Promotion requires evidence for both sensitivity and restraint.

**Basis:** `CI-13`; `PH-02`, `PH-05`, `PH-06`; ledger section 25.2.

### MD-17: Durable workflow state and crash recovery

**Current state:** Branch-local design motivated by real interruption and
one-shot evidence failures; no production router implementation.

**Disposition:** `continue-experimentally`

**Smallest coherent role:** Persist exact workflow phase, current owner,
immutable evidence references, terminal receipt, and whether a mutation may be
safely resumed, reevaluated, or must be escalated.

**Why:** Codex interruption, missing terminal lifecycle, partial deployment,
adapter failure, and non-replayable mutations show that conversational memory is
not sufficient workflow custody.

**Must not own:** Semantic planning, automatic replay of ambiguous mutation,
acceptance vocabulary, or a mandatory multi-agent role graph.

**Evidence-change trigger:** Qualify one minimal state machine across a
read-only interruption and one mutation-phase interruption. This mechanism can
be evaluated independently of the full Phase A/B router.

**Basis:** `CI-02`, `CI-10`, `CI-14`; `INC-04`, `INC-05`, `INC-09`, `INC-10`,
`INC-14`; `PH-07`.

## 8. Suspend

### MD-18: Full seven-stage Phase A/B workflow-router package

**Current state:** Reviewed branch-local North Star and suspended staging map;
no production implementation.

**Disposition:** `suspend`

**Reason:** The package combines several unqualified handoffs. Constructor
adequacy, runtime expression evaluation, Reviewer authority, durable role
isolation, and routing policy have not passed as an integrated chain. Adopting
the package now would make the architecture depend on its least qualified
parts.

**Preserved parts:** Phase A compiler, Constructor, Reviewer, and durable state
retain their separate experimental dispositions. Suspension does not reject
their underlying problems or results.

**Reactivation trigger:** Only after at least two adjacent handoffs are
independently qualified and a complete architecture comparison shows that the
seven-stage composition solves a measured problem better than a smaller loop.

**Basis:** `CI-14`; `PH-01` through `PH-07`.

### MD-19: Legacy autonomous Planner/Guardian/Conductor orchestration as a product path

**Current state:** Modules remain in current code; autonomous MCP creation entry
points are lifecycle-contained. Historical Planner North Stars are superseded
or non-authorizing.

**Disposition:** `suspend`

**Reason:** Module presence does not establish an active or qualified general
Planner product path. The recent evidence came from Prime/Rook disposable
integration and bounded compositional slices, not this complete legacy role
stack.

**Preserved parts:** Individual prompts, graph representations, Worker modules,
or compiler utilities may remain evidence sources or implementation assets
under their own owners.

**Reactivation trigger:** A current architecture proposal must identify a
specific responsibility that only this orchestration stack owns and compare it
with the simpler Actor/evidence loop.

**Basis:** `CUR-03`, `CUR-04`; `ARC-04`, `ARC-05`; `CI-14`, `CI-16`.

## 9. Retire Or Supersede

### MD-20: Legacy task-specific point-row acceptance wrapper as a forward architecture

**Current state:** Tracked compatibility files remain; current wrapper tests
fail four canonical-byte checks under Windows checkout, while the common
acceptance seam passes separately.

**Disposition:** `retire-or-supersede`

**Reason:** The point-row artifact was scientifically useful, but it is not the
general runtime abstraction. Its supported semantics have moved into the common
behavioral acceptance path, and its canonical-byte custody is currently brittle.

**Preservation:** Retain the historical artifact and result as evidence. Do not
use it as the template for one evaluator per future task.

**Successor:** `MD-07` for generic admitted behavior, with intelligent residual
judgment remaining outside the wrapper.

**Basis:** `ACC-01`, `ACC-04`, `ACC-05`, `ACC-08`; `INC-15`.

### MD-21: Knowledge-store or first-match component identity resolution

**Current state:** Superseded by merged native discovery and direct GUID
metadata custody. Authoritative discovery tools now skip unrelated knowledge
injection.

**Disposition:** `retire-or-supersede`

**Reason:** Registration-order substring search, early limiting, first exact
match selection, and knowledge-store detours failed duplicate-name,
third-party, provenance, and authoritative identity requirements.

**Preservation:** Knowledge may remain advisory under `MD-09`. Short canvas IDs
and existing execution identities remain separate from library discovery GUIDs.

**Successor:** `MD-03`.

**Basis:** `DSC-01` through `DSC-04`; `KG-02`; `INC-06`, `INC-07`.

## 10. Mechanism Dependencies

The dispositions imply dependency constraints without yet selecting a complete
architecture:

```text
Actor or Worker
-> canonical gateway and strict admission
-> authoritative discovery/metadata where needed
-> receipt-producing mutation
-> readiness and fenced observation
-> supported deterministic evaluation
-> advisory judgment or user escalation when unproven
-> bounded correction only from admitted evidence
```

Additional constraints:

- Prime cannot receive product adoption credit until `MD-10` prerequisites are
  closed.
- Phase A cannot become an acceptance authority without Constructor and runtime
  handoff evidence.
- Reviewer output cannot override deterministic facts.
- Knowledge cannot override live host evidence.
- The common evaluator cannot claim unsupported semantics.
- A complete router cannot be selected merely because its individual ideas are
  useful.

## 11. Evidence-Efficient Advancement Rules

To avoid replacing the finite-vocabulary noose with an infinite prompt corpus:

1. Test failure classes and handoffs, not paraphrase volume.
2. Prefer structurally different tasks over many lexical variants of one task.
3. Add generic evidence only after the same missing observation blocks more than
   one meaningful task or blocks one high-consequence task with no safe
   intelligent fallback.
4. Record unsupported meaning and route it; do not automatically encode it.
5. Require experimental mechanisms to state the one result that would change
   their disposition.
6. Stop experiments that cannot alter an architecture choice.
7. Measure latency, calls, and correction cost alongside outcome quality.
8. Preserve model freedom over topology while keeping runtime facts externally
   owned.

## 12. Parts Available For Later Architecture Comparison

### 12.1 Established parts

- bounded Worker;
- canonical gateway and strict result/admission contract;
- native discovery and identity handoff;
- mutation receipts and fenced observation; and
- empirical qualification/evidence custody.

### 12.2 Narrowed parts

- deterministic PlanGraph execution representation;
- common behavioral acceptance core;
- bounded repair loop; and
- advisory knowledge retrieval.

### 12.3 Conditional or experimental parts

- grounded Qwen3.8 Actor;
- Prime runtime after adoption prerequisites;
- payload-first adapter contract;
- compositional semantic graph/compiler;
- Phase A compiler;
- acceptance Constructor;
- independent Reviewer; and
- durable workflow state/recovery.

### 12.4 Excluded packages and paths

- the full Phase A/B router as a preselected implementation package;
- legacy autonomous role-stack orchestration as an assumed product path;
- the point-row wrapper as a general acceptance architecture; and
- knowledge-based or first-match component identity.

## 13. Explicit Nonauthorization

This disposition pass does not authorize:

- production changes;
- deployment or live contact;
- another model campaign;
- expansion of the predicate or operation catalog;
- implementation of the Phase A/B router;
- adoption of Prime;
- deletion of suspended or superseded files; or
- selection of the final coordinating-intelligence architecture.

The next interpretive step is to compose two or three complete candidate
architectures from the available parts and compare them against the same claim
and disposition record.
