# LM4U - Catalog Current-Step Provider Design

**Date:** 2026-06-25
**Status:** Design approved (pending spec review)
**Campaign:** LM north-star internal DAG agent coordination push - reusable provider scaffold
**Predecessors:** LM4N (#345) `propose_next_node` · LM4O (#352) `revalidate_proposal` · LM4P (#353) `map_accepted_proposal_to_step` · LM4Q (#354) `execute_mapped_step` · LM4R (#356) `run_current_mapped_step` · LM4S (#357) `run_current_step_stream` · LM4T (#360) live current-step stream proof

---

## 1. Goal

LM4U introduces the first reusable current-step provider scaffold for LM4S.

LM4T proved that a test-local provider can thread the full current-step ladder through a
live repair stream:

```text
LM4N propose
-> LM4P map (embedding LM4O revalidation)
-> LM4Q execute
-> LM4R record
-> LM4S stream
```

The load-bearing provider pattern from LM4T was:

- a caller-authored fixed Step catalog;
- an explicit same-node rule for `repair_same_component` bind-then-producer;
- fresh proposal and mapping per graph snapshot;
- halt when LM4N selected `done`;
- no Step construction inside the provider;
- no graph mutation, execution, fallback, terminal application, or model involvement.

LM4U promotes only the reusable catalog/rule plumbing into production. It does not promote
the LM4T template itself, and it does not add scheduler authority.

---

## 2. Production Module

Add:

```text
mcp_server/src/rook/agent/plan_graph_current_step_provider.py
```

This module belongs in the agent layer because it:

- imports LM4M Step types;
- emits LM4S `EnvelopeSupplyResult` and `CurrentStepEnvelope`;
- calls LM4N `propose_next_node`;
- calls LM4P `map_accepted_proposal_to_step`;
- builds caller-authored step-map views for LM4P.

It must not import:

- LM4O directly;
- LM4Q / step executor;
- LM4R current-step runner;
- `run_current_step_stream` from LM4S (the provider may import `EnvelopeSupplyResult`
  only);
- sequence runner execution helpers;
- `RookAgent`, server, dispatcher, or model surfaces;
- terminal application seams such as `apply_outcome`.

---

## 3. Public Types

The module defines a literal, count-indexed rule:

```python
@dataclass(frozen=True)
class NodeStepRule:
    node_id: str
    steps_by_seen_count: tuple[Step, ...]
```

The provider is a frozen dataclass callable directly by LM4S:

```python
@dataclass(frozen=True)
class CatalogCurrentStepProvider:
    rules: tuple[NodeStepRule, ...]
    terminal_node_ids: frozenset[str] = frozenset()

    def __call__(
        self,
        current_graph: PlanGraph,
        records: tuple[CurrentStepRecord, ...],
        supply_records: tuple[EnvelopeSupplyRecord, ...],
    ) -> EnvelopeSupplyResult:
        ...
```

`supply_records` is accepted to match LM4S's provider signature. LM4U does not need it for
selection, and it must not use it as hidden policy memory.

The provider has no mutable decision state: no proposal list, counters, caches, or
internal record accumulation. The only history source for repeat rules is the `records`
tuple LM4S passes in.

---

## 4. Rule Semantics

All executable node mappings are expressed as `NodeStepRule`. There is no separate
one-shot catalog path.

For a selected non-terminal node:

1. Count prior current-step records where
   `record.accepted_node_id == selected_node_id`.
2. Use that count as the index into `steps_by_seen_count`.
3. Build a one-entry per-call step map:

   ```python
   {selected_node_id: chosen_step}
   ```

4. Call `map_accepted_proposal_to_step(proposal, current_graph, step_map)`.
5. Return `EnvelopeSupplyResult("SUPPLY", CurrentStepEnvelope(mapping, metadata), reason, metadata)`.

Examples:

```python
NodeStepRule("create_script", (ProducerStep("create_script"),))
NodeStepRule("verify_create", (VerifierStep("verify_create", "create_script"),))
NodeStepRule(
    "repair_same_component",
    (
        BindStep("repair_same_component", base_params, bindings),
        ProducerStep("repair_same_component"),
    ),
)
NodeStepRule("verify_repair", (VerifierStep("verify_repair", "repair_same_component"),))
```

For the repair rule:

- prior count `0` selects the `BindStep`;
- prior count `1` selects the `ProducerStep`;
- prior count `2` is an exhausted rule and returns an intentionally invalid supply shape.

The chosen Step still goes through LM4P. Step target mismatch, malformed map values, and
snapshot revalidation remain LM4P/LM4O's canonical responsibility.

---

## 5. Selector and Mapping Flow

Each provider call performs exactly:

```text
proposal = propose_next_node(current_graph)               # LM4N
per-call step_map = explicit rule lookup by selected node
mapping = map_accepted_proposal_to_step(...)              # LM4P, embedding LM4O
return EnvelopeSupplyResult(...)
```

LM4U must not call LM4O directly. LM4P already embeds LM4O and returns the canonical
`StepMappingResult`. A separate LM4O call would duplicate truth and create a second
revalidation object that could drift.

For supplied steps, the canonical audit chain is:

```text
EnvelopeSupplyResult.envelope.mapping
-> StepMappingResult.revalidation
-> RevalidationResult.proposal / fresh_proposal
```

LM4U does not attach proposal objects separately.

---

## 6. Halt and Invalid Runtime Semantics

LM4N selector halts become valid provider halts:

- `HALT_NONE_READY` ->
  `EnvelopeSupplyResult("HALT", None, "selector_halt:none_ready", metadata)`
- `HALT_AMBIGUOUS_READY` ->
  `EnvelopeSupplyResult("HALT", None, "selector_halt:ambiguous_ready", metadata)`

A selected terminal node becomes a valid provider halt:

- selected node in `terminal_node_ids` ->
  `EnvelopeSupplyResult("HALT", None, f"terminal_node_selected:{node_id}", metadata)`

Unsupported runtime paths become intentionally invalid LM4S-native supply shapes:

- selected non-terminal node has no rule ->
  `EnvelopeSupplyResult("SUPPLY", None, f"no_step_rule_for_node:{node_id}", metadata)`
- selected non-terminal node's rule is exhausted ->
  `EnvelopeSupplyResult("SUPPLY", None, f"step_rule_exhausted:{node_id}:{seen_count}", metadata)`

LM4S owns the stream stop taxonomy. These invalid supply shapes let LM4S record
`invalid_reason="supply_missing_envelope"` and stop with `stop_reason="provider_invalid"`.

LM4U does not retry, substitute a different rule, fall back to another node, or reinterpret
LM4S stop reasons.

---

## 7. Construction Validation

`CatalogCurrentStepProvider.__post_init__` performs light static validation.

Raise `ValueError` for:

- duplicate `NodeStepRule.node_id`;
- empty `NodeStepRule.node_id`;
- empty `steps_by_seen_count`;
- Step target mismatch with `node_id`;
- any `terminal_node_ids` entry that also has a rule.

Raise `TypeError` for:

- any `steps_by_seen_count` value that is not a `ProducerStep`, `VerifierStep`, or
  `BindStep`.

Step target checks use the same semantics as LM4P:

- `VerifierStep` targets `verifier_node_id`;
- `ProducerStep` and `BindStep` target `node_id`.

Terminal nodes have no Step rule in LM4U. If a caller wants a terminal action, it remains
outside this provider and outside LM4S.

---

## 8. Metadata Contract

Provider metadata is versioned and observational only:

```python
{
    "provider": "catalog_current_step_provider:v1",
    "proposal_decision": proposal.decision,
    "selected_node_id": proposal.selected_node_id,
    "candidate_node_ids": tuple(proposal.candidate_node_ids),
    "ready_count": proposal.ready_count,
    "selector_id": proposal.selector_id,
    "seen_count": seen_count_or_none,
    "rule_step_count": rule_step_count_or_none,
    "step_kind": step_kind_or_none,
}
```

`step_kind` is one of:

- `"producer"`;
- `"verifier"`;
- `"bind"`;
- `None` when no Step is selected.

For supplied steps, metadata is convenience data for stream-level inspection. Canonical
mapping truth remains `EnvelopeSupplyResult.envelope.mapping`.

For halts and invalid supply shapes, there is no mapping artifact, so flattened proposal
facts in metadata are the audit surface.

Metadata must not include verdict fields such as:

- `ok`;
- `passed`;
- `completed`;
- `should_continue`;
- `success`.

---

## 9. Tests

Add:

```text
mcp_server/tests/test_plan_graph_current_step_provider.py
```

### Unit Tests

Constructor validation:

- duplicate node ids raise `ValueError`;
- empty node id raises `ValueError`;
- empty `steps_by_seen_count` raises `ValueError`;
- non-Step value raises `TypeError`;
- Step target mismatch raises `ValueError`;
- terminal node also having a rule raises `ValueError`.

Call behavior:

- no ready nodes returns valid HALT with reason `selector_halt:none_ready`;
- ambiguous ready nodes return valid HALT with reason `selector_halt:ambiguous_ready`;
- selected terminal node returns valid HALT with reason `terminal_node_selected:<node_id>`;
- selected non-terminal with no rule returns invalid SUPPLY with reason
  `no_step_rule_for_node:<node_id>`;
- exhausted repeat rule returns invalid SUPPLY with reason
  `step_rule_exhausted:<node_id>:<seen_count>`;
- supplied step returns a `CurrentStepEnvelope` whose mapping is an LM4P
  `StepMappingResult`;
- supplied mapping carries the canonical LM4P revalidation result;
- provider metadata contains the explicit versioned fields and no verdict language.

### Offline Chain Guard

Use the LM4T repair catalog shape with deterministic fake execution seams:

```text
create_script           -> producer
verify_create           -> verifier
repair_same_component   -> bind
repair_same_component   -> producer
verify_repair           -> verifier
done                    -> provider HALT, non-executed
```

Run `CatalogCurrentStepProvider` through `run_current_step_stream` and assert:

- `result.stop_reason == "provider_halt"`;
- `len(result.records) == 5`;
- `len(result.supply_records) == 6`;
- supply/current-step records align by mapping identity for executed steps;
- final supply record is HALT with reason `terminal_node_selected:done`;
- accepted ids are exactly the five-node trace above;
- execution kinds are exactly `producer`, `verifier`, `bind`, `producer`, `verifier`;
- the two `repair_same_component` records use the same accepted node id and differ as
  bind then producer.

No live Rhino test is needed in LM4U. LM4T already proved the full live vertical path.
LM4U's novelty is reusable provider structure.

---

## 10. Boundary Guards

Tests should include an AST/import boundary guard for the production module.

Allowed direct production dependencies:

- `rook.agent.plan_graph_current_step_runner.CurrentStepEnvelope`;
- `rook.agent.plan_graph_current_step_stream.EnvelopeSupplyResult`;
- LM4M Step types from `rook.agent.plan_graph_sequence_runner`;
- `rook.agent.plan_graph_step_mapping.map_accepted_proposal_to_step`;
- `rook.learning.plan_graph_selector.propose_next_node`;
- standard-library dataclass/typing helpers.

Disallowed:

- `revalidate_proposal`;
- LM4Q executor;
- LM4R runner;
- `run_current_step_stream` from LM4S (the provider may import `EnvelopeSupplyResult`
  only);
- sequence runner execution;
- `run_live_producer_node`;
- `build_live_producer_record`;
- `apply_verifier_step`;
- `apply_memory_bound_params`;
- `apply_outcome`;
- `runnable_nodes`;
- `select_template`;
- server, dispatcher, `RookAgent`, or model imports.

The module should not contain loops over future execution steps. Small loops for
configuration validation and counting prior records are allowed; a stream or scheduler
loop is not.

---

## 11. Out of Scope

LM4U does not add:

- template-specific production knowledge;
- node role or metadata inference;
- Step construction from graph data;
- a production repair-chain provider factory;
- direct LM4O calls;
- execution authority;
- graph mutation;
- fallback to another node or another Step;
- terminal `done` application;
- async provider support;
- live test coverage.

---

## 12. North-Star Fit

LM4U adds structural load without giving the model or the provider ownership of the plan.
The caller still authors every Step and every repeat rule. The provider only observes the
current graph through LM4N, maps the accepted current node through LM4P, and packages the
result for LM4S.

This moves a proven LM4T test-local pattern into reusable Rook scaffold while preserving
the campaign boundary:

```text
contracts, PlanGraph state, verifier gates, repair anchors, memory propagation, policy,
mapping, and execution authority live outside the model.
```

The model still does not remember the plan, mutate the graph, choose execution steps, or
own continuation.
