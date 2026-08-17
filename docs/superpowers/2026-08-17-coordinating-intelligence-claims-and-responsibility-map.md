# Coordinating Intelligence Claims And Responsibility Map

**Status:** First interpretive pass; no target architecture or implementation
disposition

**Interpretation date:** 2026-08-17

**Evidence baseline:**
`docs/superpowers/2026-08-17-coordinating-intelligence-evidence-ledger.md`
at commit `855f98d5`, SHA-256
`B0D7C26767FE0CAA84D0E88106EA9EB17E00057750A1F980CD8E2A7756D0D6A2`

## 1. Purpose

This document begins interpretation of the verified evidence ledger. It asks
two questions:

1. What architectural claims are currently supported, resisted, or unresolved?
2. Based on that evidence, which kind of owner is best suited to each system
   responsibility: deterministic mechanism, intelligent model, user, or a
   combination?

It does not yet:

- select a comprehensive architecture;
- assign retain, repair, suspend, or retire dispositions;
- authorize Phase A/B production work;
- define an implementation plan;
- create a universal acceptance vocabulary; or
- convert bounded experiments into general capability claims.

## 2. Interpretation Method

### 2.1 Claim states

| State | Meaning |
|---|---|
| `established-within-boundary` | Current code plus direct qualification or repeated focused verification supports the claim inside an explicit boundary. |
| `repeated-bounded` | More than one retained result supports the claim, but the tested task or environment remains narrow. |
| `provisional` | Evidence favors the claim, but important alternatives or adoption dependencies remain unresolved. |
| `unresolved` | The evidence is mixed, absent, or insufficient to choose among materially different interpretations. |
| `unsupported-by-current-corpus` | A searched proposition has no controlled positive evidence in the present corpus. |

These states are not numerical confidence scores. They do not aggregate model
runs with different prompts, providers, runtime versions, or acceptance
boundaries.

### 2.2 Rules

Every claim below includes:

- supporting evidence;
- counterevidence or limiting evidence;
- the narrowest interpretation consistent with both; and
- ledger IDs that permit traceability to the factual record.

Current production, reviewed branch-local proposals, historical designs, and
retained disposable experiments remain distinct. Mechanical success, semantic
success, lifecycle completeness, and model self-report remain distinct.

## 3. Interpretive Claim Register

### CI-01: The bounded Worker box is the most mature model-execution unit in the corpus

**State:** `repeated-bounded`

**Support:** Bounded Workers repeatedly followed strict contracts, correctly
refused incoherent or unsupported work, repaired one real compile failure, and
completed scalar transformations with repeated receipt-fenced verification.
The corresponding Worker modules remain in current main.

**Resistance:** The evidence is concentrated in C# repair and scalar families.
It does not establish broad topology design, arbitrary code generation, or
Planner competence. Some adjacent models failed output-envelope contracts.

**Interpretation:** The Worker box is comparatively stable because the world
around the model is narrow and externally owned. Its maturity supports reuse of
that bounded pattern, not expansion of the Worker into a general Planner.

**Evidence:** `WRK-01` through `WRK-08`.

### CI-02: Deterministic custody is the strongest established coordination substrate

**State:** `established-within-boundary`

**Support:** Strict argument admission, structured result custody, authoritative
identity, mutation receipts, solve readiness, fenced reads, source traces,
restoration checks, and terminal lifecycle rules repeatedly prevented stale,
malformed, ambiguous, or incomplete activity from being called success.
Current focused tests pass across these owners.

**Resistance:** Custody defects also caused incomplete experiments until their
contracts were corrected. Strict custody can prevent evaluation of a plausible
result when an unclassified or decorative mutation occurs. Out-of-band activity
outside the retained trace remains outside the claim.

**Interpretation:** Deterministic mechanisms are well suited to provenance,
identity, admission, state transitions, freshness, correlation, bounded
resource use, and exact restoration. Their success here does not imply that
they should own open-ended semantic judgment.

**Evidence:** `GWY-01` through `GWY-03`; `RCP-01` through `RCP-09`; `ACC-04`;
`INC-05` through `INC-13`; section 20 of the ledger.

### CI-03: Authoritative discovery and identity handoff are qualified infrastructure on the tested installation

**State:** `established-within-boundary`

**Support:** Native ranked search, duplicate preservation, deterministic
ordering, category filtering, direct GUID metadata, compiled provenance,
installation-local `.ghuser` provenance, and ambiguity refusal passed focused
tests and a five-call post-merge qualification. Third-party specimens were
included.

**Resistance:** The evidence covers one installed catalog and selected
third-party specimens. It does not establish portable package identity across
installations or every plugin. Models may still misuse, fail to read, or avoid
the qualified discovery surface.

**Interpretation:** Discovery is no longer an unqualified backend assumption in
the tested environment. Selection and effective use remain intelligent-agent
responsibilities, while identity and metadata truth remain host-owned.

**Evidence:** `DSC-01` through `DSC-04`; sections 21 and 24 of the ledger.

### CI-04: Runtime empirical grounding materially changes operational model capability

**State:** `repeated-bounded`

**Support:** Models improved or corrected behavior after receiving exact
schemas, ranked discovery, authoritative metadata, diagnostics, snapshots,
receipts, perturbation results, and deterministic criterion feedback. Qwen3.8
completed open point-row, grid, and helix tasks while grounded in live host
evidence.

**Resistance:** Grounding did not guarantee success. Qwen3.6 ignored metadata,
substituted semantics, and falsely self-certified. The failed XY-grid run
generated extensive activity without reaching behavioral evaluation.

**Interpretation:** Model capability in this domain is not adequately described
by weights or a static prompt alone. It is partly constituted by what the model
can inspect, how evidence is represented, and whether it can act again on the
observed result.

**Evidence:** `PLN-01` through `PLN-03`; `MOD-01` through `MOD-08`; `ACC-02`,
`ACC-03`, `ACC-06`, `ACC-07`.

### CI-05: Model-facing interface quality is part of operational intelligence

**State:** `repeated-bounded`

**Support:** Sparse Planner guidance produced 0/10 valid requests while exact
shape guidance produced 10/10 on the same constrained surface. Silent
`query`/`search` degradation, protocol-envelope leakage, candidate-shape
mismatch, and text-only structured errors each materially altered what models
could understand or recover from. Corrections removed those specific failure
modes.

**Resistance:** Better interfaces did not eliminate model semantic mistakes.
After strict admission, Qwen3.6 still chose Range/EndX instead of Series/Step.
Qwen3.8 still produced invalid arguments and inefficient discovery in some
runs.

**Interpretation:** Tool schemas, payload projection, error evidence, and
admission behavior should be evaluated as part of a model-runtime system. They
are neither incidental plumbing nor a substitute for model judgment.

**Evidence:** `PLN-01`, `PLN-02`; `GWY-01`, `GWY-02`; `MOD-02`, `MOD-03`;
`ACC-06`, `ACC-07`; `INC-03`, `INC-07`, `INC-08`, `INC-11`, `INC-13`.

### CI-06: Local-model capability is conditional, non-monotonic, and empirically discoverable

**State:** `repeated-bounded`

**Support:** Qwen and Nemotron produced materially different answers under
different reasoning settings in informal direct probes. Qwen3.6 failed point
rows under one harness, later repaired bounded point rows with deterministic
feedback, and Qwen3.8 succeeded on broader open tasks. The same model family
showed different outcomes across interface and evidence conditions.

**Resistance:** The direct reasoning-level probes were single samples. Changes
across model versions, prompts, adapters, and runtime surfaces prevent a simple
causal attribution to any one setting.

**Interpretation:** Model qualification should be empirical and contextual.
Neither model size, family name, nor reasoning level alone supports a reliable
capability prediction.

**Evidence:** `MOD-01` through `MOD-08`; empirical-model and
runtime-empiricism principles.

### CI-07: Qwen3.8 has demonstrated meaningful Grasshopper Actor capability

**State:** `repeated-bounded`

**Support:** On fresh canvases, Qwen3.8 completed an exact point row, an open
point row, an adjustable XY grid, and an adjustable helix. The latter tasks used
authoritative discovery, metadata, native components, receipt-fenced
observation, and independent control perturbations. The grid self-corrected
inside the Actor turn; the helix passed without a repair turn.

**Resistance:** The corpus contains only a few task families. The grid was
inefficient and included partial edits. The helix has an inherited endpoint
shortfall. One interrupted helix run remained incomplete. No staircase or broad
architectural-design competence was established.

**Interpretation:** Qwen3.8 should not be modeled merely as a script-filling
Worker. It has shown bounded planning, discovery, topology construction, and
self-correction ability. Its reliability and efficient operating envelope
remain unknown.

**Evidence:** `MOD-07`, `MOD-08`; sections 22.3 and 23.2 of the ledger.

### CI-08: Deterministic feedback can repair local-model near misses

**State:** `repeated-bounded`

**Support:** Point-row V1 and V3 and payload-first V5 converted exact evaluation
failures into passes with one same-session continuation. Feedback named failed
criteria without supplying topology instructions. Qwen restored correct
control identities and stopped.

**Resistance:** The repaired failures were principally control-binding or label
errors. The XY-grid evaluator did not repair a fundamentally inadequate graph.
No current evidence establishes repeated repair of wrong topology or deeply
wrong semantics.

**Interpretation:** Structured feedback is a useful correction mechanism for
some near misses. It is not yet evidence for a general synthesis loop or an
unbounded number of corrections.

**Evidence:** `ACC-02`, `ACC-03`, `ACC-07`; section 22.2 of the ledger.

### CI-09: Local-model self-certification is not a trustworthy acceptance boundary

**State:** `repeated-bounded`

**Support:** Qwen3.6 and Nemotron claimed completion for semantically wrong or
incomplete graphs. Qwen3.8 made at least one inaccurate process claim despite a
correct final result. Independent snapshots and behavioral probes distinguished
those claims from observed state.

**Resistance:** Opus self-reported a result that independent evidence also
accepted. Some Qwen3.8 claims were correct. The evidence does not show that
self-report is always wrong.

**Interpretation:** Model self-report is useful narrative evidence but cannot
be the sole acceptance owner. Acceptance needs independently obtained runtime
evidence, with intelligent judgment added where mechanical evidence is
insufficient.

**Evidence:** `MOD-01`, `MOD-03`, `MOD-04`, `MOD-07`; `ACC-01`; sections 22.1
and 22.3 of the ledger.

### CI-10: Prime is a useful exploratory Actor runtime, but product adoption is not yet closed

**State:** `provisional`

**Support:** Prime sustained multi-turn IPython work, canonical Rook gateway
use, schema discovery, mutation, inspection, and same-session correction across
multiple models and task families. Its native sessions retained reasoning and
tool interaction evidence.

**Resistance:** Some runs lacked terminal lifecycle evidence. Later
qualifications depended on a reviewed Prime fork whose structured-error change
is not in the observed upstream. Runs ranged from tens to millions of reported
tokens and from single-digit to dozens of IPython cells. Qualification adapters
also introduced failures.

**Interpretation:** Prime has demonstrated value as a persistent reasoning and
interaction environment. Lifecycle guarantees, fork custody, operational
efficiency, and the product boundary between Prime and Rook remain unresolved
adoption questions.

**Evidence:** `PRM-01`, `PRM-02`; `MOD-01`, `MOD-04`, `MOD-07`, `MOD-08`;
`RCP-06` through `RCP-08`; sections 19.2, 22, and 23 of the ledger.

### CI-11: Deterministic semantic evaluation is useful but currently bounded by an explicit vocabulary

**State:** `established-within-boundary`

**Support:** Deterministic evaluators caught false successes, verified point
sequences, Cartesian grids, fixed coordinates, control causality, diagnostics,
and exact restoration. Unsupported predicates become `unproven` rather than
being guessed. Phase A mechanically validated a typed expression corpus and
isolated 23 mutations.

**Resistance:** The common acceptance module has 2,177 nonblank lines and seven
recognized predicates. Earlier point-row and grid evaluators were task-specific.
Phase A does not execute runtime evidence or prove intent adequacy. Geometry
outside the projected evidence surface remains unavailable.

**Interpretation:** Determinism is effective for supported observable relations.
The present evidence does not justify treating its finite semantic vocabulary
as universal or requiring that it expand to encode every future user intent.

**Evidence:** `ACC-01` through `ACC-05`, `ACC-08`; `PH-03`, `PH-04`; sections
20.1 and 25.1 of the ledger.

### CI-12: Phase A qualifies compiler coherence, not acceptance-contract adequacy

**State:** `established-within-boundary`

**Support:** Two valid examples compiled and 23 isolated mutations produced
localized diagnostics across references, types, projection, quantification,
scope, tolerance, nonfinite values, and budgets. Custody was offline and
reproducible.

**Resistance:** Phase A explicitly did not test whether a Constructor can author
an adequate contract, whether runtime evidence can evaluate it, or whether its
vocabulary covers open intent. The implementation is disposable and
branch-local.

**Interpretation:** Phase A is evidence for a coherent mechanical language
boundary. Any claim that it solves semantic acceptance or should anchor the
production architecture exceeds its qualification.

**Evidence:** `PH-03`, `PH-04`; section 25.1 of the ledger.

### CI-13: Independent Reviewer judgment adds information but is not qualified as semantic authority

**State:** `established-within-boundary`

**Support:** The Phase B Reviewer recognized both disclosed residuals in all six
cases and detected requirement omission, invented assumption, and material
weakening. It behaved with restraint on the coherent control.

**Resistance:** It missed authority misrouting, miscategorized hidden unresolved
risk, and produced an unsupported additional finding. The earlier V2 Reviewer
also missed underspecified expressions. Phase B was classified
`not_qualified_on_corpus`.

**Interpretation:** Independent model judgment can contribute critique and
residual-risk detection. The tested Qwen Reviewer cannot own final semantic
acceptance without mechanical admission and an escalation path.

**Evidence:** `PH-02`, `PH-05`, `PH-06`; sections 22.4 and 25.2 of the ledger.

### CI-14: The full Phase A/B workflow-router architecture is not yet evidence-selected

**State:** `unresolved`

**Support:** Its design addresses real needs: append-only workflow state, role
separation, mechanical compilation, explicit uncertainty, judgment routing,
and crash recovery. Phase A and Phase B generated useful evidence about two
parts of that design.

**Resistance:** The architecture is branch-local and explicitly
implementation-suspended. The first Constructor handoff failed, the continuation
only qualified reference repair, Phase A stopped at compiler coherence, and
Phase B did not qualify the Reviewer. The branch also predates the merged
runtime-empiricism principle.

**Interpretation:** The router remains a candidate architecture, not the current
North Star by evidentiary default. Its useful mechanisms should be evaluated
individually before the whole design is adopted or rejected.

**Evidence:** `PH-01` through `PH-07`; sections 19.3 and 27.1 of the ledger.

### CI-15: The existing knowledge system has no demonstrated positive contribution to these later workflows

**State:** `unsupported-by-current-corpus`

**Support:** The deep search found no controlled positive comparison in which
knowledge retrieval or DSPy optimization improved the Prime/Qwen Grasshopper
outcomes. Authoritative discovery was qualified with knowledge hints suppressed.
Several adjacent experiments explicitly excluded retrieval.

**Resistance:** Rook retains multiple knowledge mechanisms, and historical
architecture describes knowledge as an intelligence subsidy. Absence in the
searched corpus is not evidence that knowledge cannot help.

**Interpretation:** Knowledge should not receive architectural credit for these
results until its effect is measured. It remains a possible advisory grounding
mechanism rather than an established authority or proven performance source.

**Evidence:** `KG-01` through `KG-03`; section 26 of the ledger.

### CI-16: The evidence favors a hybrid ownership model, but not yet one complete orchestration design

**State:** `provisional`

**Support:** Deterministic custody and observation repeatedly establish facts;
models interpret open intent, choose topology, and repair; users supply goals
and remain available for unresolved decisions. Neither deterministic semantics
alone nor model self-certification alone covers the observed workflow.

**Resistance:** The exact routing between Actor, Reviewer, user, and mechanical
gate is not qualified. Prime adoption is open, acceptance construction is open,
and knowledge retrieval is unmeasured. The corpus does not compare complete
candidate architectures.

**Interpretation:** Hybrid ownership is the best-supported direction at this
level of abstraction. The evidence does not yet select the number of model
roles, the workflow state owner, or the production routing policy.

**Evidence:** `CI-02`, `CI-04`, `CI-09`, `CI-10`, `CI-11`, `CI-13`, `CI-14`.

### CI-17: Current local-model successes depend on externally designed scaffolding

**State:** `established-within-boundary`

**Support:** Skills, adapters, schemas, receipt rules, discovery contracts,
acceptance artifacts, perturbation plans, and correction eligibility were
designed and frozen before the successful local-model runs. The first attempt
to have Qwen construct a symbolic acceptance artifact failed mechanical
admission; one continuation repaired references, but the independent Reviewer
missed semantic underspecification.

**Resistance:** Within that scaffold, Qwen3.8 independently searched, selected
components, designed topologies, mutated canvases, observed results, and
self-corrected. The scaffolding did not prescribe the concrete grid or helix
graph.

**Interpretation:** The successful runs demonstrate grounded Actor capability,
not autonomous creation of the complete coordination system. External
development-time design and review currently contribute materially. In this
project that process includes human/frontier-model collaboration, but that
authorship observation is not a runtime qualification. A product-time
acceptance Constructor remains unqualified.

**Evidence:** `ACC-01` through `ACC-07`; `MOD-07`, `MOD-08`; `PH-01` through
`PH-04`.

### CI-18: Generic evidence vocabulary should grow from observed pressure, not speculative completeness

**State:** `provisional`

**Support:** Several valuable generic mechanisms arose from observed failures:
structured results, strict admission, native discovery, provenance, receipts,
fenced reads, payload-first projection, and trace classification. Each removed
a demonstrated confound or evidence gap. The current evaluator truthfully
returns `unproven` for unsupported predicates.

**Resistance:** Reactive growth can still accumulate narrow patches and large
modules. The current semantic evaluator is already substantial, and the corpus
does not establish a sufficient operation set or a production routing response
to `unproven`.

**Interpretation:** The evidence supports empirical extension of reusable
observation and custody operations. It does not support pre-enumerating all user
semantics, automatically adding a primitive for every failed task, or treating
the current vocabulary as complete.

**Evidence:** `DSC-04`; `RCP-06` through `RCP-09`; `ACC-03` through `ACC-07`;
`INC-05` through `INC-15`; `OPEN-04`, `OPEN-11`.

## 4. Responsibility Map

This map is an interpretation of the current evidence, not a production API or
router specification. `Primary owner` means the owner type best supported for
that responsibility. It does not imply that the owner acts alone.

| Responsibility | Best-supported primary owner | Deterministic role | Intelligent role | User/escalation role | Evidence status |
|---|---|---|---|---|---|
| Preserve the original request | Deterministic custody | Store exact intent and revisions; correlate them to the run | Interpret meaning without rewriting the source of truth | Correct or refine the request | Established within boundary |
| Clarify ambiguity and missing intent | Model with user escalation | Detect closed-schema omissions and preserve decisions | Ask relevant questions; identify semantic ambiguity | Decide preferences, trade-offs, and materially underspecified requirements | Provisional |
| Decompose and plan open work | Model | Enforce budgets, admitted capabilities, and artifact shape | Propose topology, sequence, alternatives, and assumptions | Approve consequential trade-offs when needed | Repeated bounded |
| Discover available components | Shared host/model | Rank complete native candidates; expose identity and provenance | Form useful searches and select among candidates | Resolve intentional preference where multiple candidates remain valid | Established within tested installation |
| Resolve component metadata and ports | Host/Rook | Return authoritative GUID-correlated metadata and failures | Use metadata to plan wiring and values | Normally none | Established within tested installation |
| Perform bounded leaf repair or transformation | Bounded Worker model | Supply exact contract, evidence, allowed actions, and verification | Produce the requested bounded change or decline | Escalate when the contract is inadequate | Repeated bounded |
| Choose and execute Grasshopper mutations | Actor model plus Rook mutation boundary | Validate arguments, identities, route eligibility, atomic results, and receipts | Choose components, wiring, values, and correction strategy | Approve destructive or materially ambiguous changes where policy requires | Repeated bounded |
| Own mutation and solve state | Rook deterministic runtime | Issue receipts; track epochs, supersession, replacement, locks, and readiness | Consume state but never redefine it | None during ordinary operation | Established within boundary |
| Observe runtime behavior | Host/Rook deterministic runtime | Produce receipt-fenced structural, diagnostic, value, and bounded geometry evidence | Decide what to inspect and interpret observations | Inspect or override when evidence remains insufficient | Established for current projected evidence |
| Construct an acceptance proposal | Model, mechanically admitted | Validate references, types, operations, authority, budgets, and supported evidence | Translate intent into proposed observable claims and disclose residuals | Confirm requirements the system cannot infer safely | Unresolved; first handoff mixed |
| Evaluate mechanically expressible claims | Deterministic evaluator | Compute supported relations; return pass/fail/unproven; preserve evidence | Select relevant claims but not alter observed facts | Review disputed or unsupported criteria | Established only for bounded vocabulary |
| Judge residual semantic adequacy | Independent model with escalation | Admit response schema, citations, consistency, and provenance | Detect omissions, weakening, assumptions, and semantic risk | Own final decision when judgment remains consequential or contested | Reviewer contribution established; authority not qualified |
| Decide whether correction is warranted | Shared gate/model | Distinguish fail, incomplete, unsupported, and eligible repair; enforce limits | Interpret feedback and propose a correction | Permit broader reinterpretation or additional attempts where policy requires | Repeated bounded for narrow repairs |
| Perform correction | Actor model | Preserve prior evidence; require a new terminal receipt and reevaluation | Modify the implementation in response to evidence; same-session repair has bounded support | Intervene when correction changes intent or exceeds policy | Repeated bounded for near misses; routing policy unresolved |
| Supply retrieved knowledge | Advisory retrieval plus model | Preserve source/provenance and keep retrieval outside runtime authority | Use retrieved priors when relevant; prefer live evidence on conflicts | Supply project-specific knowledge and correct stale priors | Contribution unresolved in this corpus |
| Extend the evidence/tool vocabulary | Product engineering with high-capacity design assistance | Preserve backward compatibility, bounded schemas, causal tests, and explicit unsupported results | Analyze recurring runtime gaps and propose reusable observations rather than task labels | Approve product scope and domain meaning | Current growth was evidence-led; authorship is a process observation, not runtime qualification |
| Route workflow and recover after interruption | Deterministic state owner with model roles | Persist phase, ownership, evidence, and non-replayable mutation state | Resume reasoning from retained state and choose next eligible action | Resolve ambiguous recovery or unsafe replay | Design supported by failure history; production owner unresolved |
| Certify final outcome | Hybrid | Certify mechanical facts and explicitly mark unsupported facts | Judge residual meaning with attributed uncertainty | Accept unresolved qualitative or high-impact outcomes | Direction supported; exact policy unresolved |

## 5. Cross-Cutting Tensions

These tensions are visible in the evidence and should remain explicit during
later architecture comparison.

### 5.1 Finite vocabulary versus open-ended intent

Mechanical predicates are reliable where supported, but an expanding catalog
can become task-specific. Models can reason beyond the catalog, but their
self-certification is unreliable. `Unproven` is therefore a routing fact, not a
product dead end and not permission to invent a new primitive automatically.

### 5.2 Strict truthfulness versus useful progress

Strict trace and receipt rules correctly prevented false claims. They also made
runs incomplete after decorative or unclassified activity. Later design must
distinguish evidence-invalidating mutation from harmless observation without
weakening freshness custody.

### 5.3 Rich grounding versus latency and context growth

Discovery, metadata, snapshots, and perturbations enabled success. Some local
runs consumed dozens of calls and very large provider-reported context totals.
More evidence is not automatically better; the relevant question is which
evidence changes the next decision.

### 5.4 Independent judgment versus correlated blind spots

A separate Reviewer can catch defects the Actor overlooks, but it can share
model-family assumptions, miss authority errors, or invent findings. Role
separation improves independence of context and incentives; it does not create
infallible semantic authority.

### 5.5 Stored priors versus live authority

The knowledge system may reduce search and supply domain priors. Installed
component identity, actual ports, mutation results, diagnostics, and solved
geometry are runtime facts. A useful knowledge architecture must preserve that
authority ordering.

### 5.6 Autonomy versus user judgment

Routine empirical correction should not require constant user intervention.
Conversely, an intelligent product should not convert `unsupported` or
qualitative uncertainty into a false mechanical answer. Escalation must be
selective, attributed, and proportional to consequence.

## 6. Hypotheses Weakened By The Evidence

The corpus weakens, but does not universally disprove, these hypotheses:

| Hypothesis | Evidence pressure |
|---|---|
| A sufficiently detailed static prompt can substitute for runtime grounding | Interface and runtime evidence repeatedly changed outcomes. |
| A model's completion claim can serve as acceptance | Multiple false or overstated completion claims were observed. |
| One finite deterministic vocabulary can presently cover open-ended Grasshopper intent | Current coverage is bounded and Phase A does not establish intent adequacy. |
| A separate Qwen Reviewer can presently own residual semantic acceptance | Phase B was not qualified on its corpus. |
| The full Phase A/B router should be adopted because its compiler is coherent | Compiler coherence does not qualify the remaining handoffs. |
| The knowledge graph can be credited as an intelligence subsidy in current Prime/Qwen results | No controlled positive effect was located. |
| More model reasoning or more tool activity monotonically improves outcomes | Informal reasoning probes and inefficient failed runs contradict monotonicity. |
| Discovery failure remains the principal explanation for local-model semantic failure | Qualified discovery worked in later successful and unsuccessful rows. |

## 7. Current Interpretive Boundary

The current evidence supports three broad strata:

### 7.1 Established substrate

- bounded Worker contracts;
- canonical gateway and strict admission;
- native component discovery and identity handoff;
- mutation receipts, solve readiness, and fenced observation; and
- exact evidence custody and fail-closed classification.

Each remains bounded by its recorded tests and qualifications.

### 7.2 Promising but provisional coordination

- Prime as a persistent Actor environment;
- Qwen3.8 as a grounded Grasshopper Actor;
- same-session evidence-driven correction;
- model-authored acceptance proposals;
- independent model review; and
- deterministic workflow routing and recovery.

These mechanisms have different evidence strength and should not be adopted as
one indivisible package.

### 7.3 Unresolved architecture questions

- how acceptance proposals are constructed in ordinary product use;
- how mechanical `unproven` results route to intelligent judgment;
- when independent review is worth its latency;
- when the user must decide;
- whether Prime or Rook owns durable workflow state;
- whether the existing knowledge system can measurably improve decisions;
- how development-time human/frontier intelligence becomes a sustainable
  product process without hardcoding every task;
- how many corrections are useful before escalation; and
- how to preserve model freedom without weakening runtime truth.

## 8. Explicit Nondecisions

This first interpretive pass does not decide:

- whether Phase A should become production code;
- whether Phase B should be repeated or replaced;
- whether Prime should be adopted, forked, or integrated differently;
- whether the common behavioral evaluator should be split or expanded;
- whether a Constructor, Reviewer, Critic, or Policy Gate becomes a permanent
  product role;
- whether the knowledge system should be reworked;
- the final workflow routing policy; or
- the next implementation slice.

Those decisions require a subsequent mechanism-disposition pass and comparison
of complete candidate architectures against the claims above.
