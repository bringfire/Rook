# Coordinating Intelligence Architectural Reset

**Status:** Authoritative direction for the next bounded experiment

**Decision date:** 2026-08-17

**Evidence base:**

- `docs/superpowers/2026-08-17-coordinating-intelligence-evidence-ledger.md`
- `docs/superpowers/2026-08-17-coordinating-intelligence-claims-and-responsibility-map.md`
- `docs/superpowers/2026-08-17-coordinating-intelligence-mechanism-dispositions.md`
- `docs/superpowers/2026-08-17-coordinating-intelligence-candidate-architectures.md`

## Decision

Rook will use a model-led empirical loop as the coordinating-intelligence
baseline for ordinary interactive Grasshopper work.

The project had begun asking deterministic machinery to establish open-ended
semantic completion. That responsibility has no currently qualified universal
automatic owner. Finite checks remain valuable, but they do not become general
semantic authority merely because one example can be measured.

The governing boundary is:

> Runtime determinism may certify facts with closed semantics. It may not
> acquire authority over open-ended completion merely because one example can
> be measured.

This decision does not discard the evidence ledger, the bounded Worker,
PlanGraph, deterministic evaluators, advisory knowledge, or the Phase A and B
experiments. It narrows their authority and restores the simplest architecture
consistent with the observed results.

## What We Are Building

Rook is an empirical perception-and-action environment that allows an
intelligent model to work competently inside Rhino and Grasshopper.

The baseline loop is:

```text
user intent
-> Prime maintains reasoning continuity
-> Qwen investigates the live environment through Rook
-> Qwen forms a hypothesis
-> Qwen acts through admitted Rook operations
-> Rook returns authentic post-solve observations
-> Qwen reasons about the consequences
-> Qwen investigates, corrects, asks, or reports uncertainty
-> Qwen states its evidence-grounded professional conclusion
-> the user retains acceptance authority
```

Rook is not a universal semantic verifier, an exhaustive Grasshopper ontology,
a compiler for every possible design intention, or a deterministic replacement
for model judgment.

## Ownership

| Responsibility | Owner |
|---|---|
| Natural-language interpretation and design judgment | Qwen in the frozen operational configuration |
| Reasoning continuity, working context, and goal persistence | Prime |
| Capability schemas, target identity, component identity, and exact metadata | Rook |
| Admitted operations and bounded mutation | Rook |
| Mutation outcome, solve readiness, and observable post-solve state | Rook receipts and fenced observations |
| Meaning of the observed evidence for the requested design | Qwen |
| Evidence-grounded belief that the work is complete | Qwen through Prime's existing goal interface |
| Professional recommendation and disclosure of uncertainty | Qwen |
| Acceptance, especially for aesthetic or underspecified intent | User |
| High-risk or destructive authorization | Product policy and user |

Rook supplies authentic observations of the reality it can sense. Its
observability limits remain explicit. Qwen remains responsible for its best
professional judgment; user acceptance does not imply routine manual technical
verification of every result.

## Deterministic Boundary

Determinism protects the integrity of the model's contact with the host:

- strict tool arguments and closed result envelopes;
- exact target, component, and operation identity;
- ambiguity refusal;
- mutation and partial-commit receipts;
- solve readiness and receipt-fenced observation;
- current errors and warnings;
- structured topology, output, geometry, and viewport observations;
- source traces and bounded resource use;
- refusal to replay ambiguous mutations; and
- explicit authorization for dangerous operations.

Runtime deterministic authority is allowed only for:

1. host, protocol, identity, and custody invariants with closed semantics;
2. fixed safety or product policy;
3. an explicit user-specified measurable acceptance criterion; or
4. another finite contract whose owner and semantics are independently
   justified.

A useful regression probe does not automatically become a runtime gate. A
task-specific predicate does not automatically become a general acceptance
vocabulary. A model mistake does not by itself justify another orchestration
subsystem.

When a question falls outside a supported finite contract, the system does not
pretend certainty. Qwen reasons from available evidence, investigates further,
asks the user when necessary, or reports the uncertainty.

## Evidence And Completion Discipline

The versioned Prime Grasshopper skill owns this behavioral guidance:

1. Restate the intended result.
2. Inspect fresh post-solve state after the latest mutation.
3. Compare the observed result with the intent.
4. Investigate material uncertainties.
5. Exercise important controls when appropriate and report what is observed,
   inferred, and unresolved.
6. Call `goal.complete()` as a dedicated final step only when the model believes
   the request is satisfied, with no later Rook mutation in that iteration.

This is guidance to intelligent behavior, not a host-enforced semantic gate.
The next campaign measures whether Qwen follows it.

Minimal lifecycle meanings are:

- `goal.complete()` records Prime/Qwen's evidence-grounded completion belief.
- Material uncertainty requires further investigation, an honest incomplete
  report, or user input.
- Budget exhaustion is not completion.
- After interruption or restart, the model reorients from current Rook state
  before any further mutation.
- Ambiguous mutations are never automatically replayed.
- No post-`goal.complete()` transport-revocation or hostile-Python containment
  guarantee is claimed.

No new completion state machine, dispatch-lease protocol, supervisor, or
semantic acceptance service is authorized by this discipline.

## Conditional Mechanisms

Existing mechanisms remain available inside their evidenced boundaries:

- **Bounded Workers:** conditional execution for an externally bounded leaf
  task. They do not own open-ended intent or whole-definition completion.
- **PlanGraph:** deterministic lowering for an admitted exact region. It need
  not represent the full semantic request.
- **Knowledge:** advisory context that cannot override live host evidence.
- **Deterministic evaluators:** development and shadow evaluation by default;
  runtime authority only for the finite contracts defined above.
- **Specialist Reviewer or Critic:** a bounded optional mechanism only after a
  measured failure shows value beyond better observation and skill guidance.
- **Phase A and Phase B artifacts:** retained research evidence. They are not
  the ordinary runtime foundation.

Prime/Qwen is the empirical coordinating-intelligence baseline. It does not
silently replace Rook Chat, public MCP, bounded Worker, or other existing
product entry paths.

## Learning Rule

Observed failures are classified before proposing infrastructure:

```text
stale or missing fact
-> improve observation

misleading payload or capability contract
-> improve adapter or tool projection

missing domain fact
-> improve advisory knowledge

poor empirical behavior despite available evidence
-> improve skill guidance and retest

persistent judgment failure despite clear evidence and guidance
-> qualify the model limit, use a stronger model, or test a bounded specialist
```

Infrastructure is added only after repeated evidence identifies a stable need.

## Next Experiment

The next experiment is a four-task Qwen3.8 self-termination campaign. It will:

- freeze the complete operational configuration, including Prime commit, model
  and runtime identity, reasoning settings, skill bytes, adapter bytes, Rook
  build, exposed tool surface, target baseline, and prompt;
- use a clean target and separate evidence log for every run;
- include a known smoke task, an underspecified request, recoverable tool
  errors, meaningful controls, and geometry-bearing evidence across the four
  tasks;
- provide no evaluator feedback or configuration tuning during the campaign;
- retain intermediate evidence for post-run analysis;
- apply hidden evaluators only after Qwen stops; and
- produce one evidence report before any product change is considered.

The campaign measures false completion, unnecessary continuation, evidence
freshness, response to diagnostics, investigation of material uncertainty,
correction behavior, and honest incomplete or blocked reporting. An
underspecified task is judged on investigation and disclosure, not on guessing
an unstated aesthetic preference.

Any change to the skill, adapter, model, reasoning setting, Prime, Rook, tool
surface, target policy, or prompt creates a new experimental cohort.

## Disposition Of The Terminalization Work

The Prime goal terminalization and Rook dispatch-gate specification and plan
are suspended, unimplemented, and unqualified. They remain in Git as evidence
of the explored guarantee and the integration cost discovered during review.
They are not current implementation guidance and must not be executed without
a new architecture decision.

The external-supervisor default is also suspended. No supervisor or replacement
completion protocol will be built in anticipation of a failure not yet observed
under this reset.

## Nonauthorization

This reset authorizes documentation, the minimal versioned skill guidance, and
the frozen offline campaign protocol. It does not authorize campaign execution,
Rook deployment, Rhino or Grasshopper contact, model calls, product changes,
semantic-vocabulary expansion, a new Reviewer, or terminalization work.
