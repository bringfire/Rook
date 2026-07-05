# LM5W - Acceptance-Criteria Assembly Boundary Design

- **Date:** 2026-07-05
- **Status:** Draft for review
- **Slice:** LM5W
- **Type:** Deterministic production boundary with tests

## 1. Purpose

LM5U produced the first positive worker evidence-push result in the LM5
campaign:

```text
diagnostics alone -> clarification
diagnostics + acceptance criteria -> action
```

The hidden repair answer did not leak:

```text
PROBE_REPAIR_CODE absent
A = 42.0 absent
```

The narrow claim is:

```text
Acceptance criteria, not hidden answers, moved worker decision behavior.
```

LM5W extracts that winning acceptance-criteria section out of the probe fixture
and gives it a pure, deterministic, provenance-bearing assembly boundary.

LM5W is allowed to be strict and fixture-shaped in v1. Generalization is not a
bug fix; it is a later evidence-backed version.

## 2. Scope

In scope:

- Add a pure acceptance-criteria assembly module.
- Define a versioned packet schema string:
  `rook.acceptance_criteria_packet:v1`.
- Assemble the exact six LM5U criteria from explicit typed source inputs.
- Preserve deterministic ordering and provenance.
- Compute a stable SHA-256 fingerprint over canonical JSON.
- Represent unresolved planner/user intent as a first-class packet field when
  explicitly supplied.
- Prove the assembled criteria reproduce the LM5U
  `acceptance_criteria.criteria` section.

Out of scope:

- No Planner integration.
- No Compiler integration.
- No Rook2 integration.
- No KG retrieval.
- No probe runner behavior changes.
- No model calls.
- No live runs.
- No prompt, parser, transport, or publication changes.
- No repair-quality scoring.
- No generic diagnostic interpretation beyond the LM5U fixture anchor.
- No package-level re-export.

Production scope:

```text
mcp_server/src/rook/agent/local_worker_acceptance_criteria.py
```

Test scope:

```text
mcp_server/tests/test_local_worker_acceptance_criteria.py
```

Documentation scope:

```text
docs/superpowers/specs/2026-07-05-lm5w-acceptance-criteria-assembly-boundary-design.md
docs/superpowers/plans/2026-07-05-lm5w-acceptance-criteria-assembly-boundary.md
```

## 3. Doctrine

Workers act on checkable acceptance criteria, not answers.

LM5W assembles criteria from already-selected source facts. It does not
discover those facts by walking Planner, Compiler, scaffold, graph, receipt, or
probe internals.

This keeps ownership split across layers:

- Source extraction is a later Planner/Compiler/verifier/receipt boundary.
- Criteria assembly is LM5W.
- Worker evidence packet construction remains outside LM5W.

Hidden bind params cannot leak because they are not representable as LM5W
source inputs.

## 4. Public Module Surface

LM5W adds one public module:

```python
from rook.agent.local_worker_acceptance_criteria import ...
```

There is no package-level re-export from `rook.agent`.

The public module surface is:

```python
ACCEPTANCE_CRITERIA_PACKET_SCHEMA = "rook.acceptance_criteria_packet:v1"

@dataclass(frozen=True)
class AcceptanceCriteriaSource:
    source_class: str
    source_path: str
    value: Any

@dataclass(frozen=True)
class UnresolvedIntentEntry:
    intent_id: str
    description: str
    source_class: str
    source_path: str
    reason: str

@dataclass(frozen=True)
class AcceptanceCriteriaSources:
    pin_contract: AcceptanceCriteriaSource
    verifier_outcome: AcceptanceCriteriaSource
    receipt_diagnostic: AcceptanceCriteriaSource
    convention: AcceptanceCriteriaSource
    unresolved_intent: tuple[UnresolvedIntentEntry, ...] = ()

def assemble_acceptance_criteria_packet(
    sources: AcceptanceCriteriaSources,
) -> dict[str, Any]:
    ...
```

`__all__` is exactly:

```python
__all__ = (
    "ACCEPTANCE_CRITERIA_PACKET_SCHEMA",
    "AcceptanceCriteriaSource",
    "UnresolvedIntentEntry",
    "AcceptanceCriteriaSources",
    "assemble_acceptance_criteria_packet",
)
```

Return type is a fresh mutable `dict[str, Any]`, following the LM5I/LM5J
renderer pattern.

## 5. Source Dataclasses

Source dataclasses are frozen, inert containers.

`AcceptanceCriteriaSource.value` remains `Any`. The source object does not
perform structural validation.

`UnresolvedIntentEntry` stays plain and frozen.

`AcceptanceCriteriaSources.__post_init__` may normalize
`unresolved_intent` to a tuple using `object.__setattr__`. It should not
validate source classes or values.

All fail-closed boundary validation belongs to
`assemble_acceptance_criteria_packet(...)`.

## 6. Closed Source Class Allowlist

LM5W v1 accepts exactly these source classes:

```text
pin_contract
verifier_outcome
receipt_diagnostic
convention
planner_user_intent
```

Required family mappings:

```text
pin_contract.source_class == "pin_contract"
verifier_outcome.source_class == "verifier_outcome"
receipt_diagnostic.source_class == "receipt_diagnostic"
convention.source_class == "convention"
unresolved_intent[*].source_class == "planner_user_intent"
```

Canonical criterion ownership:

```text
output_a_assigned -> pin_contract
output_a_double_compatible -> pin_contract
verify_repair_succeeds -> verifier_outcome
preserve_body_mode -> convention
resolve_target_diagnostics -> receipt_diagnostic
remove_unresolved_symbol -> receipt_diagnostic
```

`planner_user_intent` is accepted only for `unresolved_intent`. It does not
produce any of the canonical six criteria in v1.

Unknown source classes raise `ValueError`.

## 7. Expected Source Values

LM5W v1 uses one source object per criterion family:

```python
AcceptanceCriteriaSources(
    pin_contract=AcceptanceCriteriaSource(...),
    verifier_outcome=AcceptanceCriteriaSource(...),
    receipt_diagnostic=AcceptanceCriteriaSource(...),
    convention=AcceptanceCriteriaSource(...),
    unresolved_intent=(),
)
```

Expected values:

```text
pin_contract.value:
  {"pins_out": ["A:double"]}

verifier_outcome.value:
  "succeeded"

receipt_diagnostic.value:
  [
    "CS0103: The name 'DefinitelyMissingSymbol' does not exist in the current context."
  ]

convention.value:
  {"mode": "body"}
```

LM5W v1 is intentionally strict. It raises `ValueError` for:

- missing required source family
- wrong source class
- missing or empty source path
- malformed `pin_contract.value`
- missing `pins_out`
- empty `pins_out`
- more than one output pin
- output pin not shaped as `<name>:<type>`
- verifier outcome other than `succeeded`
- convention mode other than `body`
- diagnostics not a `list[str]`
- empty diagnostics
- any diagnostic item that is not a string
- diagnostics that do not contain `DefinitelyMissingSymbol`
- unresolved intent entries with malformed fields or wrong source class

The strict `DefinitelyMissingSymbol` rule exists because
`remove_unresolved_symbol` is an LM5U fixture-anchored criterion. It is not a
general diagnostic interpretation policy.

## 8. Canonical Criteria

LM5W v1 emits exactly six criteria in this order:

```text
output_a_assigned
output_a_double_compatible
verify_repair_succeeds
preserve_body_mode
resolve_target_diagnostics
remove_unresolved_symbol
```

Each criterion has exactly these fields:

```text
criterion_id
description
source
source_class
```

There is no `source_path` field inside criteria in v1. `source` preserves the
LM5U field name and means source path.

Using `source` for criteria and `source_path` for unresolved-intent entries is a
v1 reproduction tradeoff. A later v2 may unify naming after LM5W is no longer
anchored to the LM5U packet section.

Canonical output:

| Criterion ID | Description | Source | Source Class |
|---|---|---|---|
| `output_a_assigned` | `Output A must be assigned.` | `create_script.initial_execution_params.pins_out` | `pin_contract` |
| `output_a_double_compatible` | `Output A must be double-compatible.` | `create_script.initial_execution_params.pins_out` | `pin_contract` |
| `verify_repair_succeeds` | `The repaired body must satisfy the verify_repair expected_outcome: succeeded.` | `workflow_contract.rules.verify_repair.expected_outcome` | `verifier_outcome` |
| `preserve_body_mode` | `The repair must preserve body-style code.` | `script_body_gotcha` | `convention` |
| `resolve_target_diagnostics` | `The repair must resolve the current target diagnostics.` | `create_script.receipt.script_receipt.repair_anchor.target_errors` | `receipt_diagnostic` |
| `remove_unresolved_symbol` | `The repaired body must not leave DefinitelyMissingSymbol unresolved.` | `create_script.receipt.script_receipt.repair_anchor.target_errors` | `receipt_diagnostic` |

`A` and `double` are mechanically derived from `pins_out == ["A:double"]`.

LM5W v1 validates that the receipt diagnostics contain
`DefinitelyMissingSymbol`. If they do not, assembly raises `ValueError`.
Therefore `remove_unresolved_symbol` is always present in a valid v1 packet.
This preserves the LM5U reproduction target without claiming a general
diagnostic parsing policy.

## 9. Packet Shape

The assembled packet shape is:

```python
{
    "schema": "rook.acceptance_criteria_packet:v1",
    "source_set": {
        "source_classes": [...],
        "source_paths": [...],
    },
    "criteria": [...],
    "unresolved_intent": [...],
    "fingerprint": "sha256:...",
}
```

`source_set.source_classes`:

- sorted unique
- includes only actually used source classes
- includes `planner_user_intent` only when unresolved intent entries exist

`source_set.source_paths`:

- sorted unique
- derived from criterion `source` values plus unresolved-intent
  `source_path` values

`source_set` is an index, not authority. Each criterion's own `source` and
`source_class` remain the authoritative provenance for that criterion.

`unresolved_intent`:

- is always present
- defaults to `[]`
- is copied only from explicitly supplied `UnresolvedIntentEntry` values
- is sorted deterministically by `intent_id`
- participates in the fingerprint
- is informational and non-blocking in v1

LM5W v1 does not infer unresolved intent.

## 10. Fingerprint

`fingerprint` is:

```text
sha256:<hex digest>
```

It is computed over canonical JSON for the packet with `fingerprint` omitted.

Canonical JSON:

```python
json.dumps(value, sort_keys=True, separators=(",", ":"))
```

The fingerprint includes:

- `schema`
- `source_set`
- `criteria`
- `unresolved_intent`

The fingerprint must change when any criterion text, source path, source class,
or unresolved-intent entry changes.

The fingerprint must not change because of dict insertion order.

## 11. Freshness And Aliasing

Each call returns fresh mutable containers.

The output must not retain references to mutable source values. Mutating one
returned packet must not affect later calls or source inputs.

## 12. Fixture Reproduction Anchor

LM5W tests include a fixture reproduction anchor:

```text
LM5U probe fixture sources
-> AcceptanceCriteriaSources
-> assemble_acceptance_criteria_packet(...)
-> legacy criteria projection equals the LM5U evidence_present_v3
   acceptance_criteria.criteria
```

The direction stays one-way:

```text
tests compare new boundary to old fixture
runtime behavior unchanged
```

The probe scripts must not import the new module:

```text
scripts/lm5k_worker_probe.py must not import local_worker_acceptance_criteria
scripts/lm5r_two_pass_publication_probe.py must not import local_worker_acceptance_criteria
```

## 13. Tests

Targeted reproduction tests:

- Assemble from LM5U-equivalent source inputs.
- Assert the exact six criterion ids, descriptions, sources, and source classes
  in order.
- Assert `schema == "rook.acceptance_criteria_packet:v1"`.
- Assert `unresolved_intent == []`.
- Assert `source_set` contains only actually used source classes and paths.
- Assert fingerprint has the `sha256:` prefix.

Freshness and fingerprint tests:

- Mutate one returned packet, call assembler again, and assert the second
  result is clean.
- Same semantic sources with different dict insertion order produce the same
  fingerprint.
- Criterion-affecting source changes change the fingerprint.
- Unresolved intent entries are sorted and affect the fingerprint.

Fail-closed validation tests:

- wrong source class
- missing or empty source path
- malformed `pins_out`
- multiple output pins
- verifier outcome not `succeeded`
- convention mode not `body`
- diagnostics empty
- diagnostics not `list[str]`
- non-string diagnostic item
- diagnostics missing `DefinitelyMissingSymbol`
- unresolved intent with wrong source class
- malformed unresolved intent fields

Fixture reproduction anchor:

- Import LM5K probe fixture helpers in the test.
- Build the `evidence_present_v3` context/packet.
- Build `AcceptanceCriteriaSources` from the same visible source facts.
- Confirm the LM5U packet path exists:

```python
lm5u_packet_acceptance_criteria = (
    lm5u_packet["fields"]["acceptance_criteria"]["criteria"]
)
```

- Compare through a legacy projection because LM5W adds `source_class` while
  the historical LM5U packet section has only `criterion_id`, `description`,
  and `source`.
- Assert:

```python
legacy_projection = [
    {
        "criterion_id": criterion["criterion_id"],
        "description": criterion["description"],
        "source": criterion["source"],
    }
    for criterion in assembled["criteria"]
]
assert legacy_projection == lm5u_packet_acceptance_criteria
```

Then assert `source_class` values separately in exact order.

Static guards:

- Production diff is exactly the new module.
- Test diff is exactly the new test file.
- No package-level re-export edits.
- The new module imports no plan graph, compiler, probe script, model,
  transport, runtime, file, JSON/YAML parser, or action execution surfaces,
  except Python stdlib `json` for canonical fingerprinting.
- `git diff --check` is clean.
- Python 3.10 compile passes.

## 14. Anti-Goals

LM5W does not:

- replace LM5U evidence packet construction
- edit `scripts/lm5k_worker_probe.py`
- edit `scripts/lm5r_two_pass_publication_probe.py`
- add Planner source extraction
- add Compiler source extraction
- inspect `RookWorkflowContract`
- inspect scaffolds, graphs, receipts, or bind specs
- accept hidden bind params
- generalize beyond one output pin
- generalize beyond the `DefinitelyMissingSymbol` fixture diagnostic
- generate one criterion per arbitrary diagnostic
- infer missing planner/user intent
- add repair execution or semantic scoring
- update curated evidence docs

## 15. Next Slice

After LM5W, the next slice should target source extraction:

```text
How do Planner, Compiler, verifier, receipt, and convention layers produce
AcceptanceCriteriaSources for the assembler?
```

That should be a narrow design/implementation target. It should not collapse
all criteria into `RookWorkflowContract`, and it should not start by wiring the
assembler into runtime worker evidence packets.

Path resolvability belongs to that next source-extraction slice. LM5W validates
source class and source path shape, but it does not walk upstream objects to
prove source paths are resolvable.

LM5W creates the seam. Later slices decide how real upstream systems feed it.
