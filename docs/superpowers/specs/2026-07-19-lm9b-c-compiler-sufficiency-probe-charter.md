# LM9B-C Compiler Sufficiency Probe Charter

**Status:** Experimental probe charter

**Date:** 2026-07-19

**Question:** Can the frozen R01 Planner Graph Recipe be lowered into one inert,
full-source Grasshopper C# `Script_Instance` without inventing a material
semantic outcome?

## Purpose

LM9B-C is a disposable empirical probe around the durable
`rook.planner_graph_recipe:v1` contract. It tests the most expensive remaining
assumption before more of LM9A-S is implemented: whether the recipe carries
enough meaning for bounded intelligent compilation.

The probe may demonstrate one bounded lowering, identify a precise contract
gap, expose a candidate failure, or remain inconclusive. One run never proves
the contract sufficient in general.

## Review Rule

A finding blocks LM9B-C only when it would:

1. leak the expected solution;
2. permit mutation, retrieval, or authority expansion;
3. prevent preservation of raw evidence;
4. make failure causes fundamentally indistinguishable; or
5. make the probe incapable of answering its question.

Other imperfections are frozen configuration, recorded limitations, observed
failures, or future hardening.

## Frozen Representation

The only admitted candidate representation is:

```text
one inert full-source Grasshopper C# Script_Instance
exact input and output pin declarations
exact source preserved
no auxiliary canvas components
no execution
```

The representation profile is generic and frozen independently of R01. The
compiler receives no radial example, expected topology, worked C# solution, or
task-specific component catalog. This probe tests lowering into the fixed C#
representation. It does not test representation selection or native-component
topology construction.

## Compiler Input

The deterministic renderer supplies two model-visible partitions.

### Semantic Source

- the exact frozen R01 recipe bytes;
- complete exact bytes for every authority artifact referenced by R01;
- raw hashes and canonical artifact identities.

Complete artifacts do not authorize semantic borrowing. A material semantic
decision must trace to a `maintains` clause and its legally scoped source,
assumption, or derived-fact support. Goal or delegation alone is insufficient.

### Implementation Context

- the generic full-source C# `Script_Instance` representation contract;
- schemas and vocabularies needed to interpret R01;
- task-independent capability evidence for the fixed representation;
- the closed terminal-result schema.

An implementation decision must cite a supporting maintained obligation, an
applicable shape delegation, and available implementation-context capability.
A guard or read-only decision may cite `requires` or an invariant where
applicable.

### Exclusion Policy

The exclusion policy is fingerprinted controller configuration, not semantic
model input. The controller exposes:

- no product-agent context or knowledge injection;
- no filesystem, network, Rhino, or Grasshopper tools;
- no provider retrieval;
- no raw user brief, expected answer, evaluator rubric, or LM9A-S expected
  report;
- exactly one local tool: `submit_compiler_result`.

The model's pretrained knowledge is not an enforceable exclusion claim.

The evidence retains original artifact bytes and hashes, exact rendered request
bytes and hash, renderer identity, and prompt/model/provider/tool/budget
identities.

## Bounded Compiler Session

One attempt is one bounded intelligent session over fixed inputs. It may contain
multiple visible model turns, but no retry with changed inputs, post-run repair,
or human steering.

```text
maximum turns:                    6
tool calls per turn:              1
per-call completion-token limit:  16,384
provider-call timeout:            180 seconds
overall monotonic deadline:       600 seconds
cumulative reported-token stop:   120,000
cumulative reported-cost stop:    USD 10.00
```

Turns, per-call output tokens, call timeout, and the overall deadline are
pre-enforceable bounds. Cumulative token and cost values are post-response stop
thresholds, not hard caps; unavailable provider accounting is recorded as
unknown rather than inferred.

Exactly one `submit_compiler_result` call is allowed per turn. Unknown,
duplicate, parallel, malformed, or absent terminal calls receive bounded
mechanical feedback while a turn remains. Free text never becomes an artifact.
A valid submission terminates immediately.

The provider-facing function schema has one required string field,
`submission_json`, because provider function declarations support a narrower
schema dialect than the terminal union. The controller parses that string once
and applies the complete frozen compiler-result schema locally. The evaluator
uses the equivalent `evaluation_json` carrier. These strings are structured
tool arguments, not assistant free text, and malformed or extra wrapper fields
receive mechanical feedback rather than becoming evidence.

Permitted feedback is limited to:

```text
JSON or schema violation
unknown or dangling recipe reference
duplicate identity
missing required trace row
wrong result-variant shape
```

Feedback cannot supply topology, representation advice, semantic values,
radial corrections, rubric answers, or candidate repairs.

This demonstrates only within-session reconsideration after deterministic
structural or trace feedback. It does not demonstrate runtime surprise from
world-state changes, authority arrival, or failed execution.

## Terminal Result

The single closed compiler-result schema has two variants:

```text
compiled_candidate
  exact full C# source
  exact pin declarations
  material-decision trace
  compiler-authored verification_plan
  unused recipe paths

contract_insufficient
  exact missing or ambiguous decision
  affected clause IDs
  absent authority location
  why fixed representation latitude cannot resolve it
```

Invalid C# remains a possible `candidate_failure`. Offline C# compilation is a
useful later measurement, not a prerequisite for the first run.

## Independent Evaluation

A provider/control failure, exhausted bound, or absence of a schema-valid
terminal result is `inconclusive`; no semantic evaluator runs.

Otherwise exactly one independent evaluation session receives:

- the same semantic source;
- the same implementation context;
- the terminal compiler result;
- the deterministic trace-check result; and
- the frozen rubric.

It does not receive the compiler transcript by default and never sends feedback
to the compiler. Its report is evidence, not execution authority.

The rubric examines:

1. closed-authority source fidelity for every material decision;
2. coverage of maintained truth and postconditions;
3. coherence of the full-source C# representation and pins;
4. absence of material invention;
5. whether the verification plan observes contract truth instead of trusting
   implementation self-attestation; and
6. for `contract_insufficient`, whether the named meaning is absent from R01,
   necessary for conforming lowering, and outside delegated latitude.

## Observation Outcomes

The harness derives exactly one observation:

```text
bounded_lowering_demonstrated
  schema-valid candidate and independent evaluation accepts the bounded claim

contract_gap_demonstrated
  exact absent meaning is independently judged necessary for conforming lowering

candidate_failure
  schema-valid terminal result is rejected without demonstrating a contract gap

inconclusive
  provider/control/evidence failure, invalid terminal output, exhausted bound,
  or unusable evaluation
```

## Evidence Layout

Raw evidence remains local under:

```text
probe_runs/lm9b-c-<timestamp>-<git-sha>/
  manifest.json
  inputs/
    recipe.json
    authority/
    implementation_context/
    exclusion_policy.json
  prompts/
  schemas/
  compiler/
    turns/
    session_summary.json
    terminal_result.json
  deterministic_trace_check.json
  evaluator/
    request.json
    raw_response.json
    report.json
  decision.json
```

Every visible compiler turn, exact provider request and response, tool arguments
and results, usage record, timing record, and fingerprint is preserved. No
hidden reasoning is requested or required. Absent conditional artifacts are
recorded explicitly in the summary rather than fabricated.

## Non-Claims

LM9B-C does not claim:

- that R01 passed LM9A-S or any unimplemented semantic validator;
- general Planner Graph Recipe sufficiency;
- Planner authorship competence;
- representation selection or native Grasshopper topology competence;
- C# compilation, execution safety, or runtime correctness;
- authorization to mutate Rhino or Grasshopper;
- live readiness or authoritative post-execution verification; or
- product-harness integration.

The probe is complete when one frozen attempt produces preserved diagnostic
evidence and one of the four outcomes. Red or inconclusive evidence is retained;
the run is never repaired or repeated toward success.
