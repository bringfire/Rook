# Rook Claim-Evidence Development Discipline

Status: architecture and campaign discipline

Date: 2026-07-18

## Purpose

Rook combines deterministic infrastructure, model-authored artifacts, bounded
intelligent compilation, Rhino and Grasshopper mutation, and authoritative
verification. That combination creates two recurring risks:

1. moving too quickly and joining several unknown boundaries into one opaque
   success or failure;
2. moving too slowly and constructing a large internally coherent system
   before observing whether its load-bearing assumptions work in reality.

This document defines the operating discipline between those extremes.

The core rule is:

> Apply rigor at the boundary carrying the current claim, then seek empirical
> contact before constructing the next boundary.

The companion architectural rule is:

> Every proposed slice must explain where it fits in the system that exists,
> what durable contract it adds, which functional slice is expected to consume
> that contract next, and what observation that successor should make possible.

This is not a detailed roadmap requirement. The successor forecast is a
falsifiable architectural hypothesis. Evidence may revise it. Its purpose is
to prevent individually rational slices from accumulating into an incoherent
or parallel system.

This discipline applies primarily to:

- architecture campaigns;
- agent, Planner, worker, and model probes;
- semantic contracts and intelligent compilers;
- new validation or evidence infrastructure;
- cross-layer workflows;
- live Rhino and Grasshopper mutation campaigns.

Routine local fixes still require proportionate design and verification, but
they do not need a campaign charter unless they establish a new architectural
or behavioral claim.

## 1. Terms

### 1.1 Claim

A claim is the narrow new fact a slice could establish. It must name the
subject, conditions, denominator where applicable, and excluded conclusions.

Examples:

```text
Good:
  Under one frozen workerless semantic profile and authority bundle, GPT-5.5
  can publish a recipe that the deterministic validator accepts unchanged.

Too broad:
  The Planner harness works.
```

### 1.2 Evidence boundary

The evidence boundary is the lowest layer able to know whether the claim is
true. Evidence must be produced there and exposed upward without being
reinterpreted into a more favorable result.

Examples:

- a managed Grasshopper lifecycle callback owns solve completion truth;
- a sealed validation program owns deterministic recipe validity;
- an independent rubric owns scenario-specific semantic scoring;
- a trusted mutation receipt owns whether an authorized operation occurred.

### 1.3 Production-shaped vertical slice

A production-shaped vertical slice implements a restricted but real subset of
the intended architecture:

- it uses production artifact identities and ownership boundaries;
- its durable output can flow unchanged into the predicted successor;
- it does not require translation into a separate production representation;
- its limitations are explicit and receipted.

A versioned restricted validation profile is a production-shaped slice when it
validates the same durable artifact consumed by a later compiler.

### 1.4 Disposable probe

A disposable probe is experimental scaffolding around a durable boundary. It
may contain provider invocation, fixture scheduling, evidence collection, or
comparison accounting. It must not become an alternate product protocol.

Disposable probe code may be retired after its evidence is curated. The
artifacts, fingerprints, reports, and raw observations needed to replay its
claim remain durable.

### 1.5 Control

A control isolates one uncertain boundary from another. Common controls are:

- a hand-authored valid artifact before testing model authorship;
- a fake or recorded provider result before a live model call;
- deterministic compiler input before joining Planner output;
- a direct product smoke before routing through a worker;
- an independent wrapper audit of child-reported acceptance.

### 1.6 Observation

An observation is a recorded result from a predeclared attempt. Red results are
observations. Operational gate failures are observations when they were part of
the scheduled denominator, though they may not be evidence about the model or
semantic mechanism.

### 1.7 Deferred obligation

A deferred obligation is work intentionally omitted from the current slice.
It must identify the claim the omission prevents and the gate at which the work
becomes mandatory. A deferred obligation is not part of the current backlog
merely because it can be imagined.

### 1.8 Architectural continuity statement

The architectural continuity statement explains how a slice contributes to a
coherent product path. It identifies:

- the current owner and insertion point;
- the broad coherence path from trusted ingress to authoritative result;
- upstream durable inputs;
- durable outputs and their authority;
- disposable scaffolding;
- the next expected consumer;
- the next functional observation enabled;
- the conditions that would reveal a dead end or parallel architecture.

### 1.9 Successor forecast

The successor forecast names the next one to three functional slices in broad
terms. It predicts what each consumes, what it produces, and what question it
answers. It does not authorize implementing those slices now.

## 2. The Claim-Evidence Loop

Rook campaigns should alternate construction and observation:

```text
state one claim
-> identify its evidence boundary
-> establish the smallest trustworthy prerequisite
-> run the controlled observation
-> interpret the result narrowly
-> revise the successor forecast
-> authorize or reject the next slice
```

The default constraint is:

> Do not build more than one untested functional layer beyond the last trusted
> observation.

This does not prohibit prerequisite infrastructure. It requires each
infrastructure slice to name the immediately following observation that needs
it. If no concrete observation consumes the result next, the slice is probably
premature.

Examples:

```text
Acceptable:
  sealed semantic profile
  -> immediate model-authored recipe observation

  hand-authored compiler control
  -> immediate offline Planner/compiler join

  managed gh_edit readiness
  -> immediate receipt-fenced live compiled arrival

Suspect:
  generic semantic profile
  -> generic compiler framework
  -> generic review gateway
  -> generic router
  -> eventual observation
```

## 3. Required Slice Charter

Every architecture or empirical slice must have a short charter before its
implementation plan. The charter is part of the design spec, not an informal
chat conclusion.

### 3.1 Claim and non-claims

Record:

- the exact claim;
- the counter-hypothesis or plausible red result;
- explicit non-claims;
- whether the slice proves arrival, repeatability, transfer, scaling, or only
  deterministic substrate behavior.

### 3.2 Architectural continuity

Record:

- current architecture owner;
- insertion point;
- a broad coherence path from ingress through authoritative verification,
  marking existing, current-slice, and forecast stages;
- upstream artifact and authority;
- durable output artifact;
- whether the output reaches its successor unchanged;
- predicted next consumer;
- predicted next functional observation;
- later product path in broad terms;
- dead-end and parallel-system tests.

A slice fails architectural review when no plausible successor consumes its
durable output, when its output requires conversion into a different product
artifact, or when it duplicates an existing owner.

### 3.3 Controlled variable

State what changes relative to the best existing baseline and what remains
fixed. Fixture, model, prompt, authority, execution, and verifier changes must
not be bundled unless the combined behavior is itself the sole question and
failure attribution remains possible.

### 3.4 Evidence and attribution

Declare:

- required input artifacts;
- raw and normalized artifacts to retain;
- fingerprints and program identities;
- controls;
- terminal outcome vocabulary;
- independent audits;
- canonical attempt count;
- retry and replacement policy;
- which failure layer each outcome implicates;
- which outcomes produce no evidence about the model or mechanism.

### 3.5 Scope budget

The design must declare a bounded implementation surface:

- new durable artifact schemas;
- new subsystems or owners;
- expected modules or files;
- fixture families;
- conformance case families;
- live attempts;
- explicit anti-goals.

The scope budget is not a line-count contest. It is a stop signal. If execution
needs another subsystem, artifact family, or test campaign not named in the
budget, stop and amend or split the slice instead of silently expanding it.

### 3.6 Deferred obligations

Record each intentional omission using the matrix in Section 9. Do not list
imagined future features without naming the claim they prevent.

### 3.7 Stop conditions

State conditions that halt implementation or evidence collection, including:

- an unexpected architectural owner;
- a prerequisite contract that does not exist;
- inability to populate evidence honestly;
- uncontrolled failure attribution;
- scope-budget overflow;
- a red canonical result;
- a repeated operational gate failure;
- evidence that the predicted successor cannot consume the output unchanged.

### 3.8 Charter template

Use this shape, scaled down when the slice is simple:

```yaml
slice_id: "<slice-id>"

claim:
  statement: "<narrow falsifiable claim>"
  counter_hypothesis: "<plausible red result>"
  claim_level: deterministic_substrate | arrival | repeatability | transfer | scaling | product
  non_claims: []

architectural_continuity:
  current_owner: "<existing architectural owner>"
  insertion_point: "<existing boundary>"
  coherence_path:
    - stage: "<stage name>"
      status: existing | current_slice | forecast
      artifact_or_receipt: "<durable artifact or receipt>"
  upstream_inputs: []
  durable_outputs: []
  disposable_scaffolding: []
  unchanged_output_to_successor: true
  dead_end_conditions: []
  parallel_system_conditions: []

successor_forecast:
  - successor: "<next functional slice>"
    consumes: "<durable current output>"
    produces: "<predicted successor output>"
    functional_question: "<observation the successor enables>"

controlled_variable:
  changed: []
  held_fixed: []

evidence:
  controls: []
  retained_artifacts: []
  terminal_outcomes: []
  canonical_attempts: "<fixed count or not-applicable>"
  retry_policy: "<none or preregistered intervention>"
  replacement_policy: "<normally none>"

scope_budget:
  durable_artifact_schemas: []
  new_owners_or_subsystems: []
  expected_modules: []
  fixture_families: []
  conformance_case_families: []
  live_attempts: "<fixed count or zero>"
  anti_goals: []

deferred_obligations: []
stop_conditions: []
```

## 4. Architectural Continuity And Successor Forecasts

### 4.1 Why continuity is mandatory

Local rationality does not guarantee system coherence. A schema, registry,
adapter, or probe can be internally sound and still become stranded between
owners or duplicate a future product boundary.

The continuity statement forces each slice to answer:

```text
Where does this live now?
What broad path connects trusted ingress to authoritative verification?
Which parts of that path exist, and which remain hypotheses?
What real artifact enters it?
What durable artifact leaves it?
Who consumes that artifact next?
What new behavior becomes observable then?
What would prove this was the wrong boundary?
```

The coherence path remains deliberately broad. It proves that the slice has a
theory of system completion; it does not freeze the internal design of future
stages.

### 4.2 Unchanged-flow test

The strongest continuity test is:

> Can the durable artifact produced or accepted by this slice flow unchanged
> into the predicted successor?

If the successor requires a translated test artifact, a parallel schema, or a
new authority interpretation, the current slice is probably a spike rather
than a product-shaped vertical slice. That may still be useful, but it must be
labeled disposable and cannot establish product architecture.

### 4.3 Successor forecasts are hypotheses

A forecast should be specific enough to falsify but too general to predesign
the successor:

```text
Good:
  A bounded compiler will consume the accepted recipe unchanged and emit inert
  exact IR plus clause-coverage records. A hand-authored recipe control will
  test whether the contract is sufficient without Planner variance.

Too vague:
  This will be useful to the compiler later.

Too detailed:
  A complete task list for the future compiler, gateway, router, and runtime.
```

The evidence summary for every slice must revisit the forecast:

- confirmed;
- revised;
- blocked;
- falsified.

The next design starts from that result rather than from the old roadmap.

### 4.4 Functional successors over foundation successors

The default next consumer should produce or observe behavior. Another
foundation slice is justified only when the functional successor cannot run
trustworthily without it.

```text
Prefer:
  contract -> controlled model observation

  compiler control -> offline joined observation

  readiness receipt -> live mutation observation

Question:
  contract -> registry -> gateway -> router -> future observation
```

## 5. Scale Rigor By Consequence

Not every layer deserves the same test posture.

| Boundary | Consequence of defect | Required posture |
| --- | --- | --- |
| raw ingress, canonicalization, fingerprints, sealed validation programs | forged or irreproducible evidence | exhaustive deterministic boundaries, conformance vectors, hostile input limits |
| authority, target identity, privilege, execution authorization | unauthorized mutation | fail closed, exact provenance, adversarial negatives |
| live mutation, readiness, commit, rollback, containment | incorrect or partial document state | authoritative receipts, lifecycle correlation, failure containment, live smoke |
| offline semantic profile | incorrect artifact acceptance or rejection | representative positive and negative conformance over each distinct rule category |
| model authoring probe | uncertain model behavior | frozen inputs, unchanged raw output, independent rubric, no repair |
| probe wrapper and evidence summary | misclassified experiment | focused accounting tests and independent artifact audit |
| future feature not needed by the current claim | no current consequence | record as deferred; do not implement |

### 5.1 Representative does not mean careless

Representative semantic conformance must exercise every admitted construct and
every materially distinct failure class at least once. It does not require the
Cartesian product of all clauses, references, policies, capabilities, and
malformations.

Prefer:

- shared validators for shared invariants;
- property tests for canonical rules;
- one positive case per admitted category;
- one negative case per distinct authority or admission failure;
- a small orthogonal control fixture to detect fixture-specific code.

Avoid adding a test merely because a new literal path can be imagined. A new
case should defend a distinct rule, failure mechanism, or regression.

### 5.2 Complexity is evidence too

Large implementation or test growth is a design signal. Plans must explain
why test/support code materially larger than the production surface is needed.
The explanation may be valid for a trust kernel. It is usually not valid for
an offline semantic experiment.

When complexity grows unexpectedly, choose among:

- reuse the existing substrate;
- replace case enumeration with one generic invariant;
- narrow the admitted surface;
- split the slice;
- run an earlier observation before expanding.

Do not compress code merely to satisfy a line target. Reduce concepts and
branches instead.

## 6. Evidence And Attribution

### 6.1 Preserve the causal chain

Every empirical attempt should retain a content-addressed chain sufficient to
identify the earliest failed boundary:

```text
source task and authority context
-> rendered request
-> provider invocation metadata
-> exact bounded raw response
-> parsed or extracted artifact, unchanged
-> deterministic validation report
-> independent semantic or behavioral evaluation
-> execution and verification receipts, when applicable
-> terminal classification
```

Record exact model/provider/profile, prompt or program version, generation
parameters, timestamps, hashes, schema identities, and whether any
transformation occurred. Do not preserve hidden model reasoning as authority.

### 6.2 No repair inside an arrival claim

Unless recovery is the preregistered intervention:

- do not repair malformed model output;
- do not autofill missing authority-bearing fields;
- do not retry a declined or malformed disposition;
- do not replace failed scheduled attempts;
- do not rerun until a favorable result appears.

Recovery mechanisms require their own baseline, intervention, budget, and
evidence identity.

### 6.3 Terminal vocabulary

Terminal outcomes must separate at least:

- harness or accounting failure;
- environment or readiness gate failure;
- provider or transport failure;
- publication or serialization failure;
- profile admission failure;
- deterministic artifact invalidity;
- valid but compile-blocked disposition;
- independent semantic-fidelity failure;
- compilation failure;
- authorization failure;
- execution failure;
- verifier rejection;
- accepted.

Not every campaign needs every term, but it must not collapse failures from
different owners into one generic rejection.

### 6.4 Independent contradiction audit

Wrappers must not trust child-reported acceptance when the child artifacts can
be audited independently. If a child reports acceptance while required
artifacts, counts, fingerprints, provenance, or receipts contradict it, the
wrapper records a harness or wrapper error. It does not silently rewrite the
result into a valid rejection.

### 6.5 Limits of deduction

Evidence can identify the earliest observable failed boundary. It cannot prove
the model's hidden reasoning or infer a systematic competence failure from one
attempt.

Use these claim levels:

```text
arrival:
  one canonical attempt shows the path can work

repeatability:
  a fixed denominator estimates recurrence for the controlled fixture

transfer:
  controlled new task families preserve the relevant behavior

scaling:
  preregistered complexity growth preserves the behavior

product competence:
  actual ingress, orchestration, authority, execution, and verification path
```

Do not promote evidence from one level to another by rhetoric.

## 7. Controls Before Joins

When two uncertain layers will be joined, control each independently first.

```text
Planner authorship + compiler sufficiency:
  validate a hand-authored recipe
  -> compile the hand-authored recipe
  -> observe model-authored recipe
  -> join model-authored recipe to controlled compiler

Compiler + live mutation:
  validate inert compiled IR
  -> prove mutation readiness directly
  -> run one joined live arrival

Worker + verifier:
  prove fixture and verifier directly
  -> add worker authority
```

The controls need not become permanent product paths. They exist to make a red
joined result attributable.

## 8. Canonical Attempts And Campaign Progression

### 8.1 Predeclare the denominator

Before a canonical run, pin:

- scheduled attempt count;
- model and profile;
- fixture and authority fingerprints;
- timeouts and budgets;
- intervention availability;
- retry and replacement policy;
- canonicality predicate;
- success and terminal accounting.

Operational failures remain in the scheduled denominator unless the design
explicitly classifies a setup-only preflight before the campaign begins.

### 8.2 Progression ladder

Use this default order:

```text
deterministic contract or substrate
-> one controlled arrival
-> bounded repeatability
-> controlled transfer
-> complexity pressure
-> product integration
```

Not every campaign requires all stages. Skipping a stage requires explaining
why the resulting failure remains attributable and why the intended claim does
not rely on the missing evidence.

### 8.3 Interpret before extending

After each canonical run:

1. inspect raw artifacts;
2. independently recompute important counts and fingerprints;
3. classify the earliest failed boundary;
4. record the narrow claim and limitations;
5. revisit the architectural continuity statement;
6. decide whether the successor forecast remains sound;
7. only then design the next slice.

Do not patch the tested slice in place to improve its recorded outcome.

## 9. Deferred-Obligations Matrix

Every campaign spec should maintain a compact table:

| Deferred obligation | Why deferred | Claim it prevents | Gate where mandatory | Evidence that may change it |
| --- | --- | --- | --- | --- |
| trusted target-selection receipts | current slice creates only new controlled content | authorization for existing-object mutation | before compiled IR can target existing content | compiler control requires existing targets |
| nonempty worker slots | first semantic proof is workerless | bounded delegated implementation authorship | before compiler creates a worker request | compiler cannot lower without a bounded slot |
| repeatability | arrival is not yet proven | reliability claim | after one accepted canonical arrival | arrival artifacts define stable accounting |

Rules:

- the matrix records obligations; it does not authorize their implementation;
- an item enters current scope only when its gate is reached;
- if the next intended claim needs an omitted item, that item is no longer
  deferred;
- evidence may delete an obligation when the architecture no longer needs it;
- evidence summaries update the matrix.

## 10. Stop And Split Rules

Stop and return to design when:

- the output cannot flow unchanged to its predicted consumer;
- a new owner or protocol appears;
- the slice requires another generic framework;
- a planned representative suite becomes combinatorial;
- failure attribution now depends on two uncontrolled seams;
- the evidence artifact cannot be constructed honestly;
- live mutation lacks authoritative readiness or authorization;
- the implementation exceeds its scope budget;
- a red result falsifies the slice's central architectural assumption.

Split work by claim and owner, not by arbitrary file count. A prerequisite fix
may proceed independently when it has its own claim and verification.

## 11. Responsibilities By Stage

### 11.1 Brainstorming and design

- state the claim and counter-hypothesis;
- write the architectural continuity statement;
- compare two or three approaches;
- identify the evidence boundary;
- choose controls;
- define the scope budget and deferred obligations;
- predict the next functional successor.

### 11.2 Implementation plan

- map every task to the current claim or a named prerequisite;
- identify which existing substrate each task reuses;
- list exact proof cases by distinct rule or failure class;
- separate deterministic implementation from live evidence;
- include stop conditions and review checkpoints;
- avoid tasks whose only justification is a distant imagined feature.

### 11.3 Implementation

- do not silently expand the admitted surface;
- do not add recovery after seeing a red result;
- preserve raw artifacts and fingerprints;
- keep durable product code separate from disposable probe scaffolding;
- pause when an architectural assumption changes.

### 11.4 Review

Reviewers ask:

- What exact claim does this change enable?
- Does each new abstraction serve that claim?
- Is the evidence produced by the layer that can know the truth?
- Can the durable output flow unchanged to the predicted successor?
- Are controls sufficient to attribute a red result?
- Is test depth proportionate to consequence?
- Has future machinery entered without a reached gate?
- Does the evidence support the written conclusion and no broader one?

### 11.5 Evidence curation

- curate only after inspecting canonical raw artifacts;
- include red operational attempts when scheduled;
- report exact denominators;
- separate observed facts from interpretation;
- record limitations and dormant interventions;
- update the continuity statement and deferred-obligations matrix.

## 12. Anti-Patterns

### 12.1 Architecture by accumulation

Each slice is locally reasonable, but no successor consumes its output and no
end-to-end path becomes shorter.

Correction: require the unchanged-flow test and successor forecast.

### 12.2 Foundation after foundation

Several generic substrates land before any functional observation.

Correction: enforce the one-untested-layer rule and name the immediate
observation after every prerequisite.

### 12.3 Demo-shaped parallel path

A probe uses a special schema, adapter, or executor that production will later
replace.

Correction: use the production artifact and ownership boundary; keep only the
invocation and accounting scaffolding disposable.

### 12.4 Exhaustiveness without consequence

Thousands of tests enumerate combinations that do not represent distinct
rules or failure mechanisms.

Correction: test generic invariants and representative categories. Reserve
exhaustive campaigns for evidence, authority, and mutation boundaries.

### 12.5 Attractive artifact as success

A model emits plausible output and the campaign stops before deterministic
validation, independent semantic review, compilation, or execution.

Correction: preserve the claim level. Authorability is not contract
sufficiency or product competence.

### 12.6 Post-hoc rescue

The tested slice gains retries, autofill, prompt changes, or replacement
attempts after a red result.

Correction: curate the red evidence, preregister the intervention as a new
slice, and preserve the baseline.

### 12.7 Roadmap as authority

A forecasted slice proceeds despite evidence that its input contract or owner
is wrong.

Correction: forecasts are hypotheses. Update them after every observation.

## 13. Worked LM9 Example

The LM9 semantic-contract campaign illustrates the discipline.

### 13.1 Durable slice

```text
artifact:
  rook.planner_graph_recipe:v1

sealed validator:
  lm9a.planner_graph_recipe.workerless_core:v1

durable result:
  unchanged recipe plus deterministic validation report

disposable scaffolding:
  model provider probe, fixture scheduler, evidence wrapper
```

The workerless profile is production-shaped because an accepted recipe is the
same artifact the later compiler is expected to consume.

### 13.2 Claim sequence

```text
LM9A-S:
  deterministic workerless semantic profile accepts and blocks controlled
  fixtures honestly

LM9B-P:
  a model can author the recipe surface without repair

LM9B-C:
  a hand-authored accepted recipe contains enough meaning and authority for one
  bounded offline compiler control

LM9B-J:
  model-authored recipe output crosses the same compiler boundary unchanged

parallel prerequisite:
  gh_edit gains managed solve-readiness receipts

LM9C:
  one joined compiled path reaches live receipt-fenced verification
```

### 13.3 Controls and limits

- The original radial brief may permit either an authorized assumption or
  honest unresolved intent; it cannot score one as universally correct.
- Governed variants make a particular disposition uniquely scorable.
- A non-radial control guards against radial fixture machinery.
- The hand-authored recipe controls compiler sufficiency before the model and
  compiler are joined.
- The provider probe tests recipe authorability, not the current product
  Planner orchestration.
- Managed gh_edit readiness is mandatory before live compiled evidence.
- No full confirmation, target-selection, privileged-authorization, or worker
  machinery is implemented until a reached claim requires it.

### 13.4 Successor forecast

The workerless profile predicts that a bounded compiler can consume an
accepted recipe unchanged and emit inert exact IR plus coverage records. The
hand-authored compiler control is the immediate falsification instrument.

The forecast is falsified if compilation requires unsourced semantic values,
if the recipe must be translated into a different contract, or if compiler
authority cannot trace back to maintained clauses and trusted companions.

That red result would revise the semantic contract before broader authority or
worker features are implemented.

## 14. Decision Summary

Rook should not choose globally between rigor and speed. It should:

1. identify the boundary carrying the current claim;
2. apply rigor proportionate to the consequence of a defect there;
3. implement the smallest production-shaped surface needed;
4. retain disposable probes only around durable contracts;
5. preserve controls and exact evidence for attribution;
6. require architectural continuity and a falsifiable successor forecast;
7. seek observation before building the next functional layer;
8. let evidence, not architectural imagination, authorize expansion.

This discipline complements the existing north-star instruction to de-risk
load-bearing empirical bets early. It also preserves the OpenProse-aligned
boundary:

```text
semantic contract
-> bounded intelligent compile
-> deterministic IR validation
-> mechanical execution
-> authoritative verification
```

Each arrow becomes a controlled claim before the campaign depends on the next.
