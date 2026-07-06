# LM5AA - Source Routing Validator Prototype Design

- **Date:** 2026-07-05
- **Status:** Draft for review
- **Slice:** LM5AA
- **Type:** Deterministic production prototype with tests

## 1. Purpose

LM5Z defined a standalone, node-scoped worker-visible source-routing artifact:

```text
schema: rook.worker_visible_source_routing:v1
```

LM5AA implements the first deterministic validator prototype for that artifact.
The validator is a fence, not a judge:

```text
static validation checks the artifact.
routability validation checks that statically valid routes resolve through the
existing LM5X extraction seam.
```

LM5AA must not design new worker evidence, prompt behavior, Planner/compiler
storage, or live model behavior.

## 2. Scope

Production scope:

```text
mcp_server/src/rook/agent/local_worker_source_routing_validator.py
```

Test scope:

```text
mcp_server/tests/test_local_worker_source_routing_validator.py
```

Documentation scope:

```text
docs/superpowers/specs/2026-07-05-lm5aa-source-routing-validator-prototype-design.md
docs/superpowers/plans/2026-07-05-lm5aa-source-routing-validator-prototype.md
```

Out of scope:

- No Planner/compiler integration.
- No `RookWorkflowContract` schema mutation.
- No worker-visible evidence packet change.
- No probe runner change.
- No LM5R/LM5K behavior change.
- No prompt, parser, transport, or model change.
- No live probe run.
- No YAML dependency in production.
- No package-level re-export.
- No broad source-path registry.
- No alternate extractor implementation.
- No capstone/addendum doc in this PR.

## 3. Core Doctrine

Routability uses LM5X-extracted `(source_class, source_path)` pairs only.
It must not independently walk `workflow_contract`, graph receipts, or
convention packet contents except through
`extract_acceptance_criteria_sources(...)`.

This is the heart of LM5AA. The validator may check route artifact structure,
but it must not become a second source extractor that can disagree with LM5X.

## 4. Public Module Surface

LM5AA adds one public module:

```python
from rook.agent.local_worker_source_routing_validator import ...
```

There is no package-level re-export from `rook.agent`.

Public constants:

```python
SOURCE_ROUTING_SCHEMA = "rook.worker_visible_source_routing:v1"
SOURCE_ROUTING_VALIDATION_REPORT_SCHEMA = (
    "rook.worker_visible_source_routing_validation_report:v1"
)

SOURCE_ROUTING_SEVERITIES = ("error", "warning")
SOURCE_ROUTING_DIAGNOSTIC_CODES = (...)
```

Public dataclasses:

```python
@dataclass(frozen=True)
class SourceRoutingDiagnostic:
    severity: str
    code: str
    node_id: str | None
    route_id: str | None
    source_class: str | None
    source_path: str | None
    purpose: str | None
    message: str


@dataclass(frozen=True)
class WorkerVisibleSourceRoutingValidationReport:
    schema: str
    valid: bool
    routability_evaluated: bool
    static_diagnostics: tuple[SourceRoutingDiagnostic, ...]
    routability_diagnostics: tuple[SourceRoutingDiagnostic, ...]
```

Public entrypoint:

```python
def validate_worker_visible_source_routing(
    artifact: object,
    *,
    workflow_contract: RookWorkflowContract | None = None,
    graph: PlanGraph | None = None,
    convention_packets: Sequence[WorkerKnowledgePacket] | None = None,
    worker_node_ids: Collection[str] | None = None,
) -> WorkerVisibleSourceRoutingValidationReport:
    ...
```

No plain dict report is exposed as the public result. Do not add `to_dict()` in
LM5AA unless a concrete consumer appears in the implementation plan.

`WorkerVisibleSourceRoutingValidationReport.schema` is the report schema, not
the input artifact schema:

```python
report.schema == SOURCE_ROUTING_VALIDATION_REPORT_SCHEMA
```

## 5. Entrypoint Invocation Rules

The validator supports two invocation modes:

```text
static-only
  workflow_contract=None
  graph=None
  convention_packets=None
  worker_node_ids=None

static + routability
  all four real-object inputs are provided
```

Mixed provided/missing routability inputs are caller misuse and raise
`ValueError`.

Empty `convention_packets` and empty `worker_node_ids` are valid provided
values only when explicitly passed as sequences/sets. They are not the default.

## 6. Report Validity Rules

Static validation always runs.

Routability validation follows this flow:

```text
1. Run static validation.
2. If static diagnostics contain any severity="error":
     routability_evaluated = false
     routability_diagnostics = ()
3. Else if no real-object inputs were provided:
     routability_evaluated = false
     routability_diagnostics = ()
4. Else:
     routability_evaluated = true
     run routability validation
```

Report validity:

```text
valid = no severity="error" diagnostics in either phase
```

Therefore a statically valid artifact with no real-object inputs may produce:

```text
valid = true
routability_evaluated = false
```

That means the artifact is statically valid but not yet proven routable.

## 7. Closed Diagnostic Vocabulary

Severity vocabulary:

```python
SOURCE_ROUTING_SEVERITIES = ("error", "warning")
```

Diagnostic code vocabulary:

```python
SOURCE_ROUTING_DIAGNOSTIC_CODES = (
    "invalid_schema",
    "invalid_routes_shape",
    "duplicate_node_route",
    "invalid_node_id",
    "worker_node_not_found",
    "invalid_visible_sources_shape",
    "invalid_route_id",
    "duplicate_route_id",
    "unknown_source_class",
    "unknown_purpose",
    "invalid_source_purpose",
    "invalid_source_path",
    "forbidden_source_path",
    "duplicate_route_tuple",
    "required_route_unresolved",
    "optional_route_unresolved",
)
```

Tests must assert the exact vocabulary. Diagnostic codes are stable
machine-readable outputs; `message` is human-readable and non-authoritative.

## 8. Static Artifact Validation

Static validation never touches:

```text
workflow_contract
graph
convention_packets
worker_node_ids
```

Static validation checks:

- artifact is a mapping
- `schema == SOURCE_ROUTING_SCHEMA`
- `routes` is a list
- every route entry is a mapping
- `node_id` is a non-empty string
- `node_id` is unique across route entries
- `visible_sources` is a non-empty list
- every visible source route is a mapping
- route fields are present and v1-shaped
- `route_id` is non-empty lowercase snake_case
- `route_id` is unique within a node
- `source_class` is in the closed allowlist
- `purpose` is in the closed allowlist
- `source_class`/`purpose` compatibility is valid
- `source_path` is a non-empty canonical string from the bounded path allowlist
  for that `source_class`
- source path is not forbidden
- `(source_class, source_path, purpose)` is unique within a node
- `required` is a boolean

Static validation is accumulative. It should collect all possible static
diagnostics within reason.

Routability only evaluates statically valid route entries. Static errors block
the routability phase.

## 9. Static Allowlists

Source classes:

```text
pin_contract
verifier_outcome
receipt_diagnostic
convention
planner_user_intent
```

Purposes:

```text
acceptance_criteria
evidence_context
unresolved_intent
```

Source-class/purpose compatibility:

| Source class | Allowed purposes |
|---|---|
| `pin_contract` | `acceptance_criteria`, `evidence_context` |
| `verifier_outcome` | `acceptance_criteria`, `evidence_context` |
| `receipt_diagnostic` | `acceptance_criteria`, `evidence_context` |
| `convention` | `acceptance_criteria`, `evidence_context` |
| `planner_user_intent` | `unresolved_intent` only |

Static path allowlist is keyed by `source_class`. A path that is valid for one
source class is not valid for another.

```text
pin_contract:
  create_script.initial_execution_params.pins_out
  solve_grasshopper_definition.initial_execution_params.pins_out

verifier_outcome:
  workflow_contract.rules.verify_repair.expected_outcome
  workflow_contract.rules.gh_solve.expected_outcome

receipt_diagnostic:
  create_script.receipt.script_receipt.repair_anchor.target_errors
  solve_grasshopper_definition.receipt.gh_receipt.solver_errors

convention:
  script_body_gotcha
  grasshopper_definition_style_convention

planner_user_intent:
  planner.intent.desired_output_value
```

For example, `source_class: convention` with
`source_path: create_script.initial_execution_params.pins_out` is invalid even
though that path exists in the `pin_contract` allowlist.

The GH paths are static pressure examples only. LM5AA does not implement GH
routability.

## 10. Forbidden Path Policy

Forbidden paths are versioned exact-string/prefix data, not ad hoc text scans
spread across tests.

V1 forbidden path families:

```text
hidden bind/base params
already-bound repair params
future node execution params
model-authored future outputs
PROBE_REPAIR_CODE / fixture answer constants
desired replacement literals as worker-visible acceptance/evidence sources
```

Examples:

```text
repair_same_component.bind.base_params.code
BindStepSpec.base_params.code
future_node.execution_params.code
PROBE_REPAIR_CODE
A = 42.0
```

A forbidden path emits `forbidden_source_path` even when the route is optional.

## 11. Routability Validation

Routability validation runs only after static validation has no errors and the
full real-object input set is provided.

Routability v1 uses LM5X by extracting all LM5U acceptance-criteria sources for
the passed objects:

```python
sources = extract_acceptance_criteria_sources(
    workflow_contract=workflow_contract,
    graph=graph,
    convention_packets=convention_packets,
)
```

The validator converts the extracted source bundle into `(source_class,
source_path)` pairs:

```text
(pin_contract, create_script.initial_execution_params.pins_out)
(verifier_outcome, workflow_contract.rules.verify_repair.expected_outcome)
(receipt_diagnostic, create_script.receipt.script_receipt.repair_anchor.target_errors)
(convention, script_body_gotcha)
```

Routability then checks declared routes by `(source_class, source_path)` only.
Purpose has already been checked statically.

The validator must not independently walk `workflow_contract`, graph receipts,
or convention packet contents except through
`extract_acceptance_criteria_sources(...)`.

## 12. Worker Node Validation

LM5AA v1 uses the caller-provided `worker_node_ids` only.

It does not inspect graph or contract objects to infer worker-ness.

Rule:

```text
node_id in worker_node_ids -> route-level routability may proceed
node_id not in worker_node_ids -> worker_node_not_found
```

If a node emits `worker_node_not_found`, the validator skips route-level
routability diagnostics for that node. This avoids noisy unresolved-route
cascades.

## 13. Planner/User Intent Routability

In LM5AA v1:

```text
planner_user_intent + unresolved_intent
  can be statically valid
  is not routable through LM5X yet
```

Routability behavior:

```text
required planner_user_intent route -> required_route_unresolved error
optional planner_user_intent route -> optional_route_unresolved warning
```

This is honest: the route shape is allowed, but the current resolver seam
cannot supply planner intent.

## 14. Routability Diagnostics

Routability diagnostics:

```text
worker_node_not_found
required_route_unresolved
optional_route_unresolved
```

`worker_node_not_found` means:

```text
node_id was not present in caller-provided worker_node_ids
```

It does not claim the node is absent from the graph or workflow contract.

If `extract_acceptance_criteria_sources(...)` raises `ValueError`, LM5AA may
map the failure back only to already-declared `(source_class, source_path)`
routes using known LM5X source-path fragments:

```text
create_script.initial_execution_params.pins_out
workflow_contract.rules.verify_repair.expected_outcome
create_script.receipt.script_receipt.repair_anchor.target_errors
script_body_gotcha
```

It must not parse arbitrary exception prose, inspect `workflow_contract`, graph
receipts, or convention packet contents independently, or infer missing sources
from anything other than the declared routes and those known LM5X source-path
fragments. The report should not surface raw traceback strings as diagnostic
codes.

## 15. Proof Targets

LM5AA tests should prove:

```text
valid LM5U repair route set -> static valid + routability valid
GH pressure example -> static valid + routability failure
missing required path -> required_route_unresolved error
missing optional path -> optional_route_unresolved warning
forbidden bind/base_params path -> forbidden_source_path error
unknown source_class -> unknown_source_class error
unknown purpose -> unknown_purpose error
planner_user_intent used for acceptance_criteria -> invalid_source_purpose error
duplicate route tuple -> duplicate_route_tuple error
worker node omitted from worker_node_ids -> worker_node_not_found error
partial real-object inputs -> ValueError
no real-object inputs -> static-only report with routability_evaluated false
```

No live run is part of LM5AA.

## 16. Import Boundaries

LM5AA may import:

```python
rook.agent.local_worker_acceptance_criteria_sources.extract_acceptance_criteria_sources
```

LM5AA must not import:

```text
scripts.lm5k_worker_probe
scripts.lm5r_two_pass_publication_probe
Planner
Compiler
BindStepSpec-derived hidden params
model transports
LM5G parser
```

Existing LM5W and LM5X modules must not import
`local_worker_source_routing_validator`.

No package-level re-export from `rook.agent`.

## 17. Relationship To LM5Z And Future Slices

LM5AA implements the LM5Z validation shape as a deterministic prototype.

It does not decide where routing artifacts are stored. It does not embed them
in `RookWorkflowContract`, and it does not make Planner/compiler produce them.

Next likely slice after LM5AA:

```text
LM5AB = route artifact source/fixture integration
```

or a Planner/compiler design slice that decides how real task contracts author
or reference routing declarations.

## 18. Verification Scope

Targeted tests:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_local_worker_source_routing_validator.py `
  -q
```

Nearby tests:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_local_worker_acceptance_criteria.py `
  mcp_server\tests\test_local_worker_acceptance_criteria_sources.py `
  mcp_server\tests\test_local_worker_source_routing_validator.py `
  -q
```

Static:

```powershell
py -3.10 -m py_compile `
  mcp_server\src\rook\agent\local_worker_source_routing_validator.py `
  mcp_server\tests\test_local_worker_source_routing_validator.py

git diff --check main..HEAD
```

Confirm no diff in:

```text
scripts/lm5k_worker_probe.py
scripts/lm5r_two_pass_publication_probe.py
mcp_server/src/rook/agent/local_worker_acceptance_criteria.py
mcp_server/src/rook/agent/local_worker_acceptance_criteria_sources.py
```
