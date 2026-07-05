# LM5X - Acceptance-Criteria Source Extraction Boundary Design

- **Date:** 2026-07-05
- **Status:** Draft for review
- **Slice:** LM5X
- **Type:** Deterministic production boundary with tests

## 1. Purpose

LM5U proved that worker-visible acceptance criteria moved the bounded worker
from clean clarification to bounded action without leaking the hidden repair
answer:

```text
diagnostics alone -> clarification
diagnostics + acceptance criteria -> action
```

LM5W extracted the LM5U acceptance-criteria section into a pure assembler:

```text
AcceptanceCriteriaSources -> rook.acceptance_criteria_packet:v1
```

LM5X creates the preceding boundary:

```text
real passed objects -> AcceptanceCriteriaSources
```

The anchor is:

```python
packet = assemble_acceptance_criteria_packet(
    extract_acceptance_criteria_sources(...)
)
```

For the real LM5U fixture objects, that packet must be fingerprint-equal to
the LM5W/LM5U expected packet.

LM5X is deterministic only. It does not change worker evidence packet
construction, probe behavior, prompt text, parser behavior, transport behavior,
or live model behavior.

## 2. Scope

Production scope:

```text
mcp_server/src/rook/agent/local_worker_acceptance_criteria_sources.py
```

Test scope:

```text
mcp_server/tests/test_local_worker_acceptance_criteria_sources.py
```

Documentation scope:

```text
docs/superpowers/specs/2026-07-05-lm5x-acceptance-criteria-source-extraction-boundary-design.md
docs/superpowers/plans/2026-07-05-lm5x-acceptance-criteria-source-extraction-boundary.md
```

Out of scope:

- No edits to `scripts/lm5k_worker_probe.py`.
- No edits to `scripts/lm5r_two_pass_publication_probe.py`.
- No worker evidence packet wiring.
- No live run.
- No model calls.
- No Planner integration.
- No Compiler integration.
- No Rook2 integration.
- No KG retrieval.
- No hidden bind-param access.
- No repair-quality scoring.
- No general knowledge-packet interpreter.
- No changes to LM5W assembler strictness.
- No package-level re-export.

## 3. Doctrine

LM5W assembles already-selected typed sources. LM5X extracts those typed sources
from real objects that are passed explicitly.

LM5X is a pure projection boundary. It does not discover objects through global
lookup, infer missing intent, or walk hidden bind outputs.

The seam hierarchy is:

```text
real objects -> extractor -> typed sources -> assembler -> packet
```

Import direction is one-way:

```text
local_worker_acceptance_criteria_sources imports LM5W assembler types.
local_worker_acceptance_criteria must not import local_worker_acceptance_criteria_sources.
```

This preserves the LM5W assembler as the lower-level packet boundary and keeps
source extraction as a separate upstream projection.

## 4. Public Surface

LM5X adds one public module:

```python
from rook.agent.local_worker_acceptance_criteria_sources import ...
```

There is no package-level re-export from `rook.agent`.

The public surface is one orchestration function:

```python
def extract_acceptance_criteria_sources(
    *,
    workflow_contract: RookWorkflowContract,
    graph: PlanGraph,
    convention_packets: Sequence[WorkerKnowledgePacket],
) -> AcceptanceCriteriaSources:
    ...
```

Private per-source extractors keep ownership visible inside the module:

```python
_extract_pin_contract_source(...)
_extract_verifier_outcome_source(...)
_extract_receipt_diagnostic_source(...)
_extract_convention_source(...)
_extract_unresolved_intent_entries(...)
```

Only `extract_acceptance_criteria_sources(...)` is public in v1.

`__all__` is exactly:

```python
__all__ = ("extract_acceptance_criteria_sources",)
```

## 5. Accepted Inputs

`workflow_contract` is the durable source for compiler/task-contract and
verifier outcome facts.

`graph` is the durable source for captured producer receipt evidence.

`convention_packets` are the durable source for worker-visible convention
evidence in this fixture.

LM5X v1 takes passed objects only. It must not call probe helper functions,
load files, query global stores, or reconstruct the LM5U fixture internally.

## 6. Extracted Sources

LM5X v1 emits:

```python
AcceptanceCriteriaSources(
    pin_contract=...,
    verifier_outcome=...,
    receipt_diagnostic=...,
    convention=...,
    unresolved_intent=(),
)
```

### Pin Contract

Extract from:

```text
workflow_contract.initial_params
  -> node_id == "create_script"
  -> execution_params["pins_out"]
```

Emit:

```python
AcceptanceCriteriaSource(
    source_class="pin_contract",
    source_path="create_script.initial_execution_params.pins_out",
    value={"pins_out": copied_pins_out},
)
```

Extractor resolution failures:

- `create_script` initial params missing
- duplicate `create_script` initial params
- `execution_params` missing or not a mapping
- `pins_out` missing
- `pins_out` not `list[str]`

The extractor does not enforce `pins_out == ["A:double"]`; LM5W assembler v1
owns packet semantics.

### Verifier Outcome

Extract from:

```text
workflow_contract.rules
  -> rule.node_id == "verify_repair"
  -> VerifierStepSpec.expected_outcome
```

Emit:

```python
AcceptanceCriteriaSource(
    source_class="verifier_outcome",
    source_path="workflow_contract.rules.verify_repair.expected_outcome",
    value=copied_expected_outcome,
)
```

Extractor resolution failures:

- `verify_repair` rule missing
- duplicate `verify_repair` rules
- no verifier step in the rule
- more than one verifier outcome candidate
- `expected_outcome` missing
- `expected_outcome` not a non-empty string

The extractor does not enforce `expected_outcome == "succeeded"`; LM5W
assembler v1 owns packet semantics.

### Receipt Diagnostic

Extract from:

```text
graph.nodes["create_script"].evidence.receipt["repair_anchor"]["target_errors"]
```

Emit:

```python
AcceptanceCriteriaSource(
    source_class="receipt_diagnostic",
    source_path=(
        "create_script.receipt.script_receipt.repair_anchor.target_errors"
    ),
    value=copied_target_errors,
)
```

Extractor resolution failures:

- `create_script` node missing
- `create_script.evidence` missing
- `receipt` missing or not a mapping
- `repair_anchor` missing or not a mapping
- `target_errors` missing
- `target_errors` not `list[str]`

The extractor does not enforce the LM5U target diagnostic value; LM5W assembler
v1 owns packet semantics.

### Convention

Extract from exactly one worker-visible script-body gotcha packet.

Candidate selection:

```text
packet_id == "script_body_gotcha"
```

Validation rule for the single selected candidate:

```text
kind == "gotcha"
title == "C# script components use body-style code"
```

Emit:

```python
AcceptanceCriteriaSource(
    source_class="convention",
    source_path="script_body_gotcha",
    value={"mode": "body"},
)
```

Extractor resolution failures:

- no packet with `packet_id == "script_body_gotcha"`
- more than one packet with `packet_id == "script_body_gotcha"`
- selected `script_body_gotcha` packet has unexpected `kind`
- selected `script_body_gotcha` packet has unexpected `title`

LM5X v1 must not parse the gotcha prose loosely. The current packet has
structured identity and title; it does not expose a structured `"mode"` field.
The v1 extractor projects body mode from that exact packet id, kind, and title
only.

### Unresolved Intent

LM5X v1 emits:

```python
unresolved_intent=()
```

The extractor does not infer missing planner/user intent from the fixture.
Planner-owned unresolved intent remains a later source-extraction concern.

## 7. Validation Split

Extractor responsibility:

- Can the named source be resolved from the right upstream owner?
- Is the resolved value the expected basic shape?
- Was the value copied out without aliasing?

Assembler responsibility:

- Is the source bundle valid for `rook.acceptance_criteria_packet:v1`?
- Is `pins_out` exactly `["A:double"]`?
- Is verifier outcome exactly `"succeeded"`?
- Is the diagnostic exactly the LM5U target diagnostic?
- Is convention mode exactly `"body"`?

LM5X must not duplicate all LM5W semantic validation. Composition tests should
prove the two layers work together:

```python
sources = extract_acceptance_criteria_sources(...)
packet = assemble_acceptance_criteria_packet(sources)
```

## 8. Error Reporting

LM5X uses `ValueError` for source-resolution failures.

Error messages should include the canonical source path or packet id that failed
to resolve, for example:

```text
create_script.initial_execution_params.pins_out missing
workflow_contract.rules.verify_repair.expected_outcome missing
create_script.receipt.script_receipt.repair_anchor.target_errors not list[str]
script_body_gotcha missing
```

Tests should assert key path fragments, not exact prose.

## 9. Aliasing

All extracted values must be copied before being placed into
`AcceptanceCriteriaSource.value`.

Mutating the original contract, graph receipt, or packet objects after
extraction must not mutate the extracted sources.

Mutating extracted source values must not mutate the original upstream objects.

## 10. Fixture Anchor

LM5X tests use the real LM5U fixture objects only in tests:

```python
probe = _load_lm5k_probe_script()
scaffold, result = probe.derive_probe_graph_state()
workflow_contract = probe._probe_contract()
graph = result.final_graph
convention_packets = [probe._script_body_gotcha_packet()]
```

Then:

```python
sources = extract_acceptance_criteria_sources(
    workflow_contract=workflow_contract,
    graph=graph,
    convention_packets=convention_packets,
)
packet = assemble_acceptance_criteria_packet(sources)
```

The packet must be fingerprint-equal to the packet assembled from the LM5W
expected source bundle.

The legacy criteria projection should also match the LM5U
`evidence_present_v3` packet section:

```text
lm5u_packet["fields"]["acceptance_criteria"]["criteria"]
```

The test direction remains one-way:

```text
tests compare extractor output to the existing fixture
runtime probe behavior unchanged
```

## 11. Tests

Targeted tests:

- Public surface exposes only `extract_acceptance_criteria_sources`.
- Extractor returns `AcceptanceCriteriaSources`.
- Extracted source classes, paths, and copied values match the LM5U source
  ownership map.
- `unresolved_intent == ()`.
- `assemble_acceptance_criteria_packet(extract(...))` is fingerprint-equal to
  the LM5W expected packet.
- Legacy criteria projection matches the LM5U packet section.
- Mutating source objects after extraction does not mutate extracted values.
- Mutating extracted values does not mutate source objects.

Shape-resolution failure tests:

- Missing `create_script` initial params raises `ValueError` containing
  `create_script.initial_execution_params.pins_out`.
- Missing `verify_repair` rule raises `ValueError` containing
  `workflow_contract.rules.verify_repair.expected_outcome`.
- `target_errors` not `list[str]` raises `ValueError` containing
  `create_script.receipt.script_receipt.repair_anchor.target_errors`.
- Missing `script_body_gotcha` raises `ValueError` containing
  `script_body_gotcha`.

Composition-boundary test:

- `target_errors` shaped as `list[str]` but containing the wrong diagnostic
  extracts successfully.
- Passing those sources to `assemble_acceptance_criteria_packet(...)` raises the
  LM5W semantic `ValueError`.

Static guards:

- `local_worker_acceptance_criteria_sources` imports LM5W assembler types.
- `local_worker_acceptance_criteria` does not import
  `local_worker_acceptance_criteria_sources`.
- The source module imports no `BindStepSpec`.
- The source module does not read `base_params`.
- The source module imports no probe scripts.
- Probe scripts do not import `local_worker_acceptance_criteria_sources`.
- No package-level re-export is added.
- `git diff --check` is clean.
- Python 3.10 compile passes.

## 12. Anti-Goals

LM5X does not:

- wire LM5W into LM5U packet construction
- edit probe scripts
- edit LM5W assembler strictness
- support arbitrary pins
- support arbitrary diagnostics
- interpret all gotcha packets
- infer unresolved planner/user intent
- read bind specs
- read `base_params`
- read `PROBE_REPAIR_CODE`
- inspect hidden future repair params
- run live models
- update curated evidence docs

## 13. LM5Y Joining Commitment

LM5X is intentionally not the end of the line.

The next slice must be the joining slice:

```text
LM5Y = wire probe packet construction to assemble(extract(real objects))
```

LM5Y should:

- replace the hand-built LM5U acceptance-criteria packet section with the
  assembled packet output, or a deliberate projection of it
- keep the evidence packet semantics stable
- rerun deterministic gates
- run the live LM5U/LM5Y probe after merge

This prevents the campaign from accumulating elegant seams without reconnecting
them to live worker evidence.
