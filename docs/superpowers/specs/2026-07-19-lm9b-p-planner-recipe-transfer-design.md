# LM9B-P Planner Recipe Transfer Design

- Date: 2026-07-19
- Status: Design approved; implementation and canonical model run not started
- Base: `main` at `39681eab`
- Scope: One offline empirical slice joining Planner authorship to the existing
  LM9B-C compiler path

## 1. Purpose

LM9B-P tests the next unproven functional seam in Rook's internal-agent
architecture:

> Can a Planner-tier frontier model author a compiler-usable
> `rook.planner_graph_recipe:v1` directly from a governed brief and trusted
> authority context, without seeing R01, an expected recipe, expected topology,
> or implementation code?

The experiment has two independently scored checkpoints and one unchanged
artifact crossing their boundary:

```text
Checkpoint 1: Planner authorship
governed brief + authority
-> raw recipe
-> frozen probe mechanical gate
-> independent semantic evaluation

Checkpoint 2: Joined transfer
probe_candidate_ready raw recipe bytes
-> unchanged LM9B-C input/archive boundary, byte-for-byte
-> unchanged deterministic compiler-request projection
-> existing structural, trace, C# preflight, and independent-evaluation checks
```

Canonical success requires both checkpoints. A result at either checkpoint must
remain attributable to that checkpoint.

## 2. Grounding

LM9B-P follows evidence already established by earlier slices:

- LM7D showed that GPT-5.5, and exploratorily Gemma 4 12B, could author the
  older `PlannerWorkerContractRequest:v1` when given exact shape guidance
  without a solved example.
- LM7E joined one model-authored Planner request to the local worker and live
  verification path.
- The generic validation kernel is landed and trusted infrastructure. It does
  not yet include the unfinished LM9A semantic contribution.
- LM9B-C showed that hand-authored R01 carried enough semantic information for
  one bounded intelligent compiler session to emit an authority-traced C#
  candidate that passed Rook's exact representation boundary and generated the
  intended geometry in live Grasshopper.
- LM9B-C did not test Planner authorship, compiler generality, repeatability,
  product orchestration, worker slots, or execution authorization.

The OpenProse alignment remains the architectural guide:

```text
durable semantic source
-> bounded intelligent compile
-> disposable exact IR
-> mechanical execution
-> authoritative verification
```

Ambiguity is surfaced rather than guessed. Intelligent sessions may spend
multiple bounded turns responding to deterministic feedback, but a changed
input or a new session is a new attempt.

LM9B-P deliberately does not complete LM9A-S before model contact. It uses a
non-authoritative observation gate so the campaign can test the Planner/compiler
handoff without creating either a scenario-specific product validator or a
shadow implementation of LM9A semantics.

## 3. Claim And Counter-Hypotheses

### 3.1 Narrow Claim

> Given the frozen radial brief and a content-addressed, LM9A-replayable
> authority context preserving the historical R01 context's semantic facts, one
> bounded frontier Planner session can author a
> `rook.planner_graph_recipe:v1` that is mechanically admissible under the
> frozen probe gate, independently recommended as semantically faithful and
> ready, supplied byte-for-byte at the unchanged LM9B-C input and archive
> boundary, and accepted after the existing LM9B-C renderer deterministically
> projects it into the compiler request.

The joined transfer is demonstrated only when:

```text
Checkpoint 1: probe_candidate_ready

and

Checkpoint 2: unchanged LM9B-C structural, trace, C# preflight,
              and independent-evaluation checks accept the inert candidate
```

This is one controlled observation. It is not a reliability or generality
claim.

### 3.2 Checkpoint Counter-Hypotheses

Checkpoint 1 counter-hypothesis:

> The Planner cannot author a mechanically admissible and semantically faithful
> candidate from the governed source without answer leakage, post-session
> repair, or semantic invention.

Checkpoint 2 counter-hypothesis:

> A mechanically admissible and semantically faithful model-authored candidate
> cannot cross the proven compiler's input boundary unchanged and produce an
> accepted inert candidate through its existing deterministic renderer and
> checks.

An honest `probe_candidate_blocked` supports neither counter-hypothesis. It is a
legitimate Planner observation and leaves Checkpoint 2 unevaluated.

### 3.3 Explicit Non-Claims

LM9B-P does not establish:

- authoritative LM9A validity or compile readiness;
- product Planner integration;
- Planner or compiler repeatability;
- generality beyond the controlled radial scenario;
- local-model competence;
- native-node, hybrid, Python, or worker-slot lowering;
- product orchestration or execution authorization;
- live Rhino or Grasshopper behavior;
- runtime surprise from changing world state, new authority, or failed
  execution.

## 4. Architectural Position

LM9B-P occupies one production-shaped vertical seam while retaining disposable
probe orchestration:

```text
mechanical ingress                         forecast
-> product Planner                        forecast
-> rook.planner_graph_recipe:v1           durable contract, current artifact
-> authoritative LM9A validation          deferred
-> bounded compiler                       existing LM9B-C experimental consumer
-> IR validation and review               partial probe checks only
-> mechanical execution                   deferred
-> authoritative runtime verification     deferred
```

The experiment itself is:

```text
frozen radial brief + trusted authority
-> bounded Planner session
-> exact submitted recipe bytes
-> frozen non-authoritative probe gate
-> independent Planner semantic evaluation
-> controller-derived probe classification

probe_candidate_ready only
-> exact same recipe bytes at the LM9B-C input/archive boundary
-> unchanged LM9B-C deterministic request projection + unchanged companions
-> unchanged LM9B-C compiler session
-> existing LM9B-C checks and evaluator
-> joined-transfer observation
```

The probe gate controls experiment flow only. It grants no product authority,
mutation permission, target authority, or execution permission.

## 5. Visibility And Authority Boundaries

### 5.1 Planner

The Planner receives:

- the frozen radial brief;
- the trusted task, environment, policy, capability, and vocabulary context;
- the generic `rook.planner_graph_recipe:v1` authoring contract and shape
  guidance;
- deterministic mechanical feedback generated within its one bounded session.

One content-addressed probe exclusion policy is shared by request rendering and
the mechanical gate. Its exact fingerprint participates in attempt identity;
changing its closed forbidden-marker set changes both rendered-request identity
and gate behavior. Production probe code contains no second hardcoded marker
list.

The Planner does not receive:

- R01 or an expected recipe;
- expected topology or C# source;
- the Planner-evaluation rubric;
- compiler or evaluator output;
- prior candidate output;
- live Rhino or Grasshopper state.

### 5.2 Planner Evaluator

The independent Planner evaluator receives:

- the same frozen brief and trusted authority context;
- the final mechanically accepted recipe;
- the frozen scenario rubric.

It does not receive:

- R01 or an expected recipe;
- the Planner transcript or earlier submissions;
- compiler input, output, or diagnostics;
- implementation source or expected topology.

The evaluator emits a frozen structured recommendation. It does not emit the
public probe classification and does not issue product authority.

### 5.3 Compiler

The compiler receives:

- the unchanged LM9B-C rendered recipe projection, containing the parsed recipe
  object plus its raw hash and historical canonical fingerprint;
- the unchanged complete authority-artifact projections;
- the unchanged derived legal-trace reference catalog;
- the unchanged terminal-result schema;
- the unchanged implementation context.

The exact final Planner-submitted bytes enter the LM9B-C input record and
archive unchanged. The existing loader parses that record, and the existing
renderer serializes the parsed object into the larger compiler request. The
compiler model therefore does not consume the literal submitted byte stream.
The rendered request bytes and hash are separately preserved.

It does not receive:

- the raw brief;
- the Planner evaluation or classification;
- R01;
- the Planner transcript;
- semantic hints produced after Planner submission.

Complete companion artifacts may contain facts not referenced by the recipe.
Their presence does not authorize the compiler to borrow unreferenced semantic
values. The existing LM9B-C trace and independent-evaluation checks remain the
experimental guard against that behavior.

## 6. Canonical Scenario And Controls

The canonical attempt uses the same radial brief and the same semantic task,
environment, and policy facts underlying R01. LM9B-P replaces the historical
fixtures' placeholder payload-schema and typed-value fingerprints with exact
content-addressed values and supplies the matching payload-schema registry.
The historical R01 context is therefore semantically matched but not
byte-identical. This remains the cleanest available matched historical control
while ensuring the authored recipe and its bound authority context can be
replayed unchanged by future LM9A-S.

R01 is:

- hidden from the Planner, Planner evaluator, and compiler;
- non-normative;
- never used as an answer key or literal-equality target;
- available only for post-run comparison after all classifications are frozen.

R01 is a matched historical control, not a strict single-variable experimental
control. The new Planner controller, prompt, mechanical gate, and evaluator are
additional procedural differences.

The authority context intentionally permits more than one honest Planner
posture:

```text
authorized assumption selected
-> probe_candidate_ready may be appropriate

material value left honestly unresolved
-> probe_candidate_blocked may be appropriate
```

The context is not altered to force the model toward R01's choices. For this
frozen scenario, `probe_candidate_blocked` is specifically reserved for honest
unresolved intent because the supplied policy and capability context removes
the other legitimate blocker classes.

The attempt also binds one content-addressed probe context with a fixed
`evaluated_at`, deterministic clock source, and exact task, environment, and
capability-registry session IDs. Authority freshness and session agreement are
mechanical input-admission checks against that context before any model call;
ambient wall time is never consulted. The context fingerprint is part of the
Planner request identity, checkpoint evidence, aggregate identity, and LM9B-C
handoff manifest. This does not create an LM9A validation report or authorize
compilation or execution.

The scenario-specific semantic rubric is allowed and necessary. It may evaluate
every authority-valid outcome. It must not require exact R01 structure or encode
an expected implementation.

Forbidden contamination includes:

- radial-specific mechanical validation;
- exact R01 structure matching;
- radial assumptions in compiler or join code;
- solved examples or candidate snippets in authoring guidance;
- expected topology in either model request.

## 7. Sessions And Attempt Boundary

The complete attempt budget is:

```text
one Planner session
zero or one Planner-evaluator session
zero or one compiler session
zero or one compiler-evaluator session
```

Each session is independently bounded by turns, per-call completion tokens,
overall monotonic deadline, provider-call timeout, and recorded token/cost stop
thresholds. None may be retried.

The Planner session may contain multiple visible turns and multiple recipe
submissions. This is bounded surprise handling inside one attempt, not a retry.
Only deterministic mechanical findings may be returned to the Planner.

The submission protocol carries the proposed recipe as exact UTF-8 JSON text,
not as an SDK-reconstructed mapping. The controller preserves the raw provider
response and the exact recipe-text argument before parsing. All later byte and
hash claims bind that text encoded as UTF-8. If a provider adapter cannot expose
the submitted argument without reconstructing or normalizing it, the attempt is
`probe_inconclusive` and no evaluator or compiler runs.

Permitted feedback includes:

- invalid JSON or frozen probe-schema mismatch;
- malformed or duplicate identifiers;
- dangling or malformed references;
- missing supplied artifacts or pointers;
- claimed hash mismatch;
- recipe fingerprint mismatch, with the deterministic sealing behavior below.

Forbidden feedback includes:

- semantic values or suggested assumptions;
- policy conclusions or authority approval;
- expected clause structure;
- radial-specific corrections;
- topology or representation guidance;
- evaluator, compiler, or R01-derived advice.

The evaluator never returns feedback to the Planner. Compiler output never
returns to the Planner.

## 8. Non-Authoritative Mechanical Gate

The frozen gate may establish only these mechanical facts:

- submitted bytes are valid JSON and conform to the frozen probe schema;
- identifiers and references are well formed;
- referenced artifacts and pointers exist in the supplied bundle;
- claimed hashes match the supplied artifacts;
- prohibited injected context is absent from the rendered request;
- submitted bytes are preserved unchanged.

Authority-context binding means resolvability and identity matching only. The
gate must not derive:

- policy authorization;
- semantic fidelity or entailment;
- whether an assumption is appropriate;
- official `valid` or `compile_ready`;
- any LM9A validation result.

### 8.1 Deterministic Fingerprint Sealing

The Planner is not expected to calculate SHA-256. The one allowed sealing
handshake is:

```text
Planner submits a complete semantic recipe
-> gate computes the canonical recipe fingerprint
-> claimed fingerprint matches
     -> submission may pass the mechanical gate
-> claimed fingerprint differs
     -> feedback returns the exact computed fingerprint
     -> Planner may resubmit inside the same bounded session
```

The feedback supplies no semantic correction. Every submission and the exact
computed-fingerprint response are preserved. Only final bytes explicitly
submitted by the model may cross Checkpoint 1. The controller never inserts the
fingerprint, edits the submission, or synthesizes replacement bytes.

The computed value uses the ratified recipe-fingerprint projection and
canonicalization rules, including exclusion of the `recipe_fingerprint` field
itself. The gate does not invent a second fingerprint algorithm or include the
claimed fingerprint in its own hash input.

### 8.2 Canonical Normal Form Compatibility

Existing LM9B-C computes its recipe fingerprint from the parsed recipe while
preserving submitted array order. The ratified recipe fingerprint instead
normalizes schema-designated set-like collections before hashing. The frozen
gate must therefore verify, without rewriting, that the final submitted recipe
is already in ratified canonical semantic normal form:

- every schema-designated set-like collection is in its ratified deterministic
  order;
- duplicate identities and references are absent;
- the submitted recipe value excluding `recipe_fingerprint` equals its ratified
  normalized projection;
- the ratified recipe fingerprint equals the unchanged historical LM9B-C
  fingerprint over that parsed value.

This requirement concerns semantic collection order, not raw JSON formatting.
The gate may return a bounded mechanical normal-form diagnostic, but it may not
return normalized recipe bytes, reorder a collection, or repair the submission.
Only a later model submission that is already in normal form may pass.

Repeated invalid submissions followed by normal turn-limit exhaustion produce
`probe_mechanically_rejected`. Provider failure, timeout, unavailable evidence,
or controller failure produces `probe_inconclusive`.

## 9. Checkpoint 1 Classification

The controller derives exactly one public classification mechanically from:

- Planner session termination;
- final mechanical-gate status;
- Planner-evaluator invocation and structured recommendation status.

The evaluator never authors the classification.

```text
probe_mechanically_rejected
  No submission cleared the frozen mechanical gate before normal turn-limit
  exhaustion.

probe_candidate_ready
  Final bytes cleared the mechanical gate and the evaluator recommended the
  recipe as faithful and ready under the frozen scenario rubric.

probe_candidate_blocked
  Final bytes cleared the gate and the evaluator recommended the recipe as
  faithful but honestly blocked by unresolved intent.

probe_planner_failure
  A mechanically accepted recipe was recommended as unauthorized, invented,
  contradictory, or semantically unfaithful.

probe_inconclusive
  Provider failure, timeout, malformed evaluator output, unavailable evidence,
  or another control failure prevents interpretation.
```

`probe_candidate_ready` controls only whether this experiment proceeds to the
compiler. It does not authorize compilation in the product sense, mutation, or
execution.

`probe_candidate_blocked` is a legitimate observation, not a Planner failure.
It terminates the attempt with Checkpoint 2 marked `not_evaluated`.

## 10. Checkpoint 2 Handoff And Classification

Only `probe_candidate_ready` enters Checkpoint 2.

A probe-local join adapter may wrap and content-address the recipe alongside the
unchanged LM9B-C companions. The adapter itself may not parse and reserialize,
normalize, translate, enrich, repair, or otherwise rewrite the recipe. The
handoff record must prove exact byte equality and matching raw SHA-256 between:

- the final mechanically accepted Planner submission;
- the recipe record supplied to the compiler renderer;
- the recipe bytes archived in compiler evidence.

The run-specific content-addressed input manifest is handoff evidence, not a
translation artifact. After the input boundary, the existing LM9B-C loader and
renderer parse the recipe and produce the deterministic compiler request
described in Section 5.3. The attempt preserves that rendered projection and its
hash; it does not claim that the compiler model consumed the raw byte stream.

Manifest construction, frozen-input loading, contract-index derivation, or
request rendering may fail before the existing compiler session and classifier
run. Any such failure produces aggregate `inconclusive`, records a bounded
pre-session failure locus, and starts neither the compiler session nor the
compiler evaluator. It produces no contract, Planner, or compiler-model verdict.

"Unchanged LM9B-C" means these existing components and behaviors remain fixed:

- compiler request renderer;
- bounded compiler controller;
- compiler terminal union schema;
- trace-reference derivation and trace validation;
- RhinoCode C# broad preflight and exact representation gate;
- compiler outcome classifier;
- compiler evaluator request, rubric, and interpretation;
- implementation context and admitted C# representation;
- compiler and compiler-evaluator model profiles.

Checkpoint 2 retains the existing LM9B-C outcomes:

```text
bounded_lowering_demonstrated
contract_gap_demonstrated
candidate_failure
inconclusive
```

`contract_gap_demonstrated` requires an explicit, schema-valid, trace-valid
compiler `contract_insufficient` result accepted by the existing independent
evaluation. It is never inferred from malformed output, failed trace checks,
failed C# preflight, representation rejection, or evaluator rejection. Those
remain `candidate_failure` under existing LM9B-C behavior.

Combined interpretation is:

```text
probe_candidate_ready + bounded_lowering_demonstrated
  -> canonical joined-transfer success

probe_candidate_blocked + not_evaluated
  -> legitimate Planner observation; joined transfer untested

probe_mechanically_rejected
  -> Planner mechanical-authoring failure

probe_planner_failure
  -> Planner semantic-authoring failure

probe_candidate_ready + contract_gap_demonstrated
  -> contract/compiler sufficiency gap, not Planner failure

probe_candidate_ready + candidate_failure
  -> compiler-stage failure, not Planner failure

any inconclusive stage
  -> no architectural verdict and no replacement attempt

probe_candidate_ready + pre-session handoff failure
  -> aggregate inconclusive; compiler session not evaluated
```

One compiler failure on one model-authored recipe is a transfer failure until
attributed to recipe quality, contract insufficiency, or compiler behavior. It
is not by itself evidence of a parallel architecture.

## 11. Persistence And Evidence

### 11.1 Durable Architecture

- `rook.planner_graph_recipe:v1` remains the semantic handoff artifact.
- The existing LM9B-C compiler boundary remains its downstream experimental
  consumer.
- No second recipe dialect or translation layer is introduced.

### 11.2 Durable Scientific Evidence

The attempt preserves:

- exact brief and authority-artifact bytes and hashes;
- the exact frozen evaluation context, session bindings, and fingerprint;
- complete rendered Planner requests and raw provider responses;
- every visible Planner turn, tool submission, and mechanical response;
- all deterministic diagnostics;
- every submitted recipe and its raw/canonical fingerprints;
- final recipe bytes and classification inputs;
- model, provider, profile, prompt, gate, schema, controller, and rubric
  identities;
- usage, timing, turn, token, and cost records;
- complete Planner-evaluator request, raw response, and structured
  recommendation;
- the content-addressed compiler handoff and byte-equality proof;
- complete existing LM9B-C compiler and evaluator evidence;
- controller-derived checkpoint and aggregate outcomes;
- post-run matched-control comparison and reviewed summary.

The probe requests and preserves no hidden chain-of-thought. Visible messages,
tool calls, deterministic feedback, and terminal outputs are sufficient audit
evidence.

### 11.3 Disposable Machinery

- Planner session controller and request renderer;
- non-authoritative mechanical gate;
- Planner-evaluation wrapper and scenario rubric;
- join adapter and run-manifest assembly;
- probe accounting, comparison, and evidence scripts.

Disposable does not mean unreviewed or unrecorded. These components are frozen
for the canonical attempt and identified in its evidence, but they do not become
product authority surfaces.

## 12. Deterministic Proof Before Model Contact

Implementation review must establish with recorded/fake providers that:

- the gate accepts and rejects only the approved mechanical facts;
- authority freshness and session bindings are evaluated against the frozen
  probe clock before provider contact;
- no mechanical finding claims policy authorization or semantic fidelity;
- every submission and feedback turn is preserved;
- the fingerprint sealing handshake returns only the computed fingerprint and
  never edits model output;
- classification is controller-derived from frozen gate/evaluator/session
  states;
- an honest blocked recommendation prevents compiler invocation without
  becoming Planner failure;
- malformed evaluator output and provider/control failures become
  `probe_inconclusive`;
- only `probe_candidate_ready` can invoke the compiler;
- the join adapter demonstrates byte equality and never parses/reserializes the
  recipe;
- a mechanically accepted, non-R01 ready fixture crosses the join, completes
  frozen-input loading and request rendering, and reaches a fake compiler
  provider before any canonical model contact;
- manifest, load, contract-index, and render failures produce aggregate
  `inconclusive` without invoking either compiler-stage provider;
- the compiler renderer, controller, checks, evaluator, implementation context,
  and model profiles are unchanged;
- compiler feedback cannot reach the Planner;
- R01, expected topology, implementation source, rubric, credentials, machine
  paths, and prior candidates do not leak into the Planner request;
- the Planner transcript and R01 do not leak into the Planner-evaluator request;
- the brief and Planner evaluation do not leak into the compiler request;
- all checkpoint outcomes are reachable through authentic frozen controls;
- evidence manifests bind every preserved input and output.

These are representative proof targets, not an exhaustive semantic-validation
campaign. No model or live Rhino/Grasshopper run occurs before implementation
review accepts the deterministic probe surface.

## 13. Scope Budget And Stop Conditions

LM9B-P includes:

- one disposable Planner probe controller;
- one frozen non-authoritative mechanical gate;
- one scenario-specific Planner-evaluation rubric and wrapper;
- one byte-preserving join into existing LM9B-C;
- deterministic tests and one post-review canonical frontier-model attempt.

LM9B-P excludes:

- validation-kernel changes;
- an LM9A semantic contribution or authoritative validation report;
- new recipe syntax or semantic vocabulary;
- fixture-specific production logic;
- changes to LM9B-C compiler semantics or representation;
- worker slots, routers, product Planner integration, mutation, or live
  execution;
- a repeatability panel or local-model row.

Stop the slice if:

- the mechanical gate must infer policy or semantic truth;
- exact scoring requires radial-specific mechanical validation or R01 matching;
- radial assumptions must enter compiler or join code;
- the recipe must be translated, normalized, enriched, or repaired;
- the compiler requires the brief or Planner evaluation;
- existing LM9B-C behavior must change rather than receive different recipe
  bytes;
- exact visible evidence cannot be preserved;
- implementation expands into authoritative LM9A-S validation.

A demonstrated generic defect in existing probe plumbing may be fixed narrowly,
with its own review and evidence. It must not become a pretext for expanding the
semantic architecture.

## 14. Deferred Obligations

The following remain separate slices:

- authoritative LM9A-S replay and comparison;
- Planner repeatability;
- local-model transfer with all other variables fixed;
- additional uniquely governed scenarios;
- native-node, hybrid, Python, and worker-slot representations;
- product ingress and Planner orchestration;
- semantic-review gateway and executable-IR authorization;
- mutation readiness, live execution, and authoritative runtime verification;
- runtime surprise from external change or new authority.

## 15. Successor Forecast And Dead-End Signals

If joined transfer succeeds:

```text
preserve exact Planner-authored recipe
-> replay through future authoritative LM9A-S
-> compare probe recommendation with authoritative validation
-> run repeatability or local-Planner transfer with downstream path fixed
```

If the recipe is honestly blocked, preserve it for later authoritative blocker
replay. Do not alter the authority context or rerun toward readiness.

If Planner or compiler behavior fails, the next slice is chosen from the
observed failure locus rather than from a forecasted taxonomy.

Evidence of architectural divergence includes:

- a second recipe dialect is required;
- semantic translation or enrichment is required before compilation;
- the compiler needs the raw brief or post-Planner semantic advice;
- fixture-specific production rules are required for the handoff;
- future authoritative validation cannot replay the exact artifact.

An ordinary failed model attempt is not itself proof of divergence. It remains
a bounded observation until the failure is attributed.

## 16. Interpretation

The strongest successful LM9B-P claim is:

> In one controlled radial attempt, a frontier Planner authored a real
> `rook.planner_graph_recipe:v1` without R01 or implementation leakage; the
> frozen probe gate mechanically admitted the model's final bytes, an independent
> evaluator recommended them as faithful and ready, those exact bytes crossed
> the unchanged LM9B-C input and archive boundary, and the existing deterministic
> renderer projected them into a compiler request that produced an inert
> candidate accepted by the existing structural, trace, C# representation, and
> independent-evaluation checks.

Any weaker result is recorded at its exact checkpoint without repair, retry, or
promotion into a broader claim.

---

## Addendum (2026-07-22) — evaluator authority boundary

Amended by `2026-07-22-lm9b-p-evaluator-authority-boundary-design.md` after the
sealed visibility-intervention run. Governing invariant: **models propose and
judge meaning; deterministic authority decides whether the system may advance.**

The evaluator recommendation vocabulary is semantic-only:
`semantically_faithful`, `semantically_unfaithful`, `evaluation_inconclusive`.
The controller derives advancement deterministically, bound to the independent
post-session `checkpoint_gate`: the `MechanicalGateResult` recomputed from the
final recipe under the frozen checkpoint inputs, validated for every accepted
session before any evaluator branch. It must exactly match the accepted turn's
retained gate result and bind the same final bytes as the session (any
mismatch is a control failure, never a classification); sealing rederives the
classification through the same carrier:

```text
mechanically admissible + semantically_faithful   + unresolved_intent_present -> probe_candidate_blocked
mechanically admissible + semantically_faithful   + no explicit blocker       -> probe_candidate_ready
mechanically admissible + semantically_unfaithful                             -> probe_planner_failure
mechanically admissible + evaluation_inconclusive                             -> probe_inconclusive
```

`derive_probe_explicit_blockers` establishes only `unresolved_intent_present`;
this probe does not establish the absence of policy/capability/selection/
authorization blockers (LM9A-S territory). `probe_candidate_ready` remains
eligibility for the inert compiler experiment only. The exact report schema and
recommendation meanings are rendered into the evaluator request from the
parser's single source of truth.
