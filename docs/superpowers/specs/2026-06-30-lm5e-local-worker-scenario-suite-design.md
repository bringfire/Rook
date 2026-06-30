# LM5E - Local Worker Scenario Suite Design

**Date:** 2026-06-30
**Status:** Approved design for implementation planning
**Campaign:** Rook local/internal models north-star, LM5 worker boundary
**Predecessors:** LM5A local worker turn context, LM5B local worker response contract, LM5C response disposition, LM5D one-turn harness

---

## 1. Goal

LM5E adds a deterministic, Rook-shaped scenario suite around the landed local
worker box:

```text
LocalWorkerTurnContext
-> deterministic test-local worker
-> LocalWorkerTurnResponse
-> LocalWorkerTurnAttemptRecord
-> LocalWorkerTurnDispositionRecord
-> LocalWorkerTurnHarnessRecord
```

LM5A-D named the production worker boundary. LM5E puts realistic pressure on
that boundary without widening it.

The suite is empirical in the narrow sense: it watches the existing worker box
behave across Rook-specific situations, including gotcha-derived failure
families, while staying deterministic and model-free.

LM5E does **not** add a model call, prompt renderer, production worker,
dispatcher, action executor, graph mutation, stream continuation, retry loop,
fallback chain, critic loop, oversight loop, scenario registry, or public
scenario API.

---

## 2. Production Scope

LM5E is test-only.

Add one test file:

```text
mcp_server/tests/test_local_worker_turn_scenarios.py
```

Do not add or edit production modules.

Specifically, do not edit:

```text
mcp_server/src/rook/agent/local_worker_turn_context.py
mcp_server/src/rook/agent/local_worker_turn_response.py
mcp_server/src/rook/agent/local_worker_turn_disposition.py
mcp_server/src/rook/agent/local_worker_turn_harness.py
```

If the scenario suite exposes a genuine bug in LM5A-D, treat that as a separate
finding. Do not casually bundle production fixes into LM5E.

No package-level exports are added.

---

## 3. Scenario Philosophy

LM5E should prove that the existing worker artifacts can carry meaningful Rook
turns, not only abstract response algebra.

Default scenario flow:

```text
RookWorkflowContract
-> compile_workflow_contract(...)
-> build_local_worker_turn_context(...)
-> test-local deterministic worker
-> run_local_worker_turn(...)
-> assert the LM5A-D audit trail
```

The real compiled create/verify/repair workflow context is the default fixture.
Hand-built `LocalWorkerTurnContext` values are allowed only where the repair
workflow setup would obscure a small edge case.

The suite should read like named Rook stories. Prefer explicit test functions:

```python
def test_repair_node_with_script_body_gotcha_requests_body_style_repair_action():
    ...
```

Avoid a top-level scenario table as the primary structure. Limited
parametrization is acceptable only for mechanical edges where it improves
clarity.

---

## 4. Knowledge Gotcha Trust Model

Knowledge gotchas are scenario seeds, not trusted rules.

```text
knowledge gotcha -> hardcoded test packet -> deterministic LM5A-D proof
not: knowledge gotcha -> accepted Rook policy
```

LM5E may create explicit `WorkerKnowledgePacket` fixtures with provenance-like
fields:

```python
WorkerKnowledgePacket(
    packet_id="gh_csharp_script_body_gotcha",
    kind="gotcha",
    title="C# script components use body-style code",
    content={
        "source": "docs/...",
        "trust": "high",
        "failure_family": "wrong_code_shape",
        "guidance": (
            "Use RhinoCode C# script body code, not a GH_Component subclass."
        ),
    },
)
```

These fields are test-local convention, not a production schema.

Rules:

- `trust` is scenario metadata, not enforcement.
- `source` is an audit hint, not a loader or fetch instruction.
- canned workers may branch on packets to simulate bounded worker behavior.
- no knowledge-store reads are allowed.
- no hidden global gotcha registry is allowed.

Hardcoded source strings are enough. Tests must not open those source files.

---

## 5. Canned Workers

Canned deterministic workers are test-local functions.

Use plain functions and small closures:

```python
def repair_action_worker(context: LocalWorkerTurnContext) -> LocalWorkerTurnResponse:
    ...


def action_worker(action_id: str):
    def worker(context: LocalWorkerTurnContext) -> LocalWorkerTurnResponse:
        ...

    return worker
```

Do not add:

- production canned workers;
- worker classes;
- worker registries;
- worker ids;
- worker configuration objects;
- reusable worker base classes.

Test-local workers may inspect `LocalWorkerTurnContext` and return typed LM5B
responses. They must not execute tools, mutate graphs, run streams, dispatch
actions, fetch knowledge, or call models.

---

## 6. Minimum Scenario Set

LM5E must include at least the following twelve scenarios unless implementation
reveals that two are exact duplicates. If a scenario is dropped as a duplicate,
the plan/review must name why and preserve the coverage group.

### 1. Repair Node Requests Allowed Action

Given:

```text
current_node_id="repair_same_component"
allowed action "draft_repair_params" exists
```

Worker:

```text
requests "draft_repair_params"
```

Assert:

```text
record.status == "completed"
record.reason == "completed:candidate_action_request"
record.response.payload is WorkerActionRequest
record.disposition.disposition == "candidate_action_request"
record.disposition.attempt.valid is True
record.disposition.attempt.action_id == "draft_repair_params"
```

### 2. Terminal Done Node Observes Completion

Given:

```text
current_node_id="done"
allowed action exists
context.current_node.is_terminal is True
```

Worker:

```text
returns WorkerObservation
```

Assert:

```text
record.status == "completed"
record.response.payload is WorkerObservation
record.disposition.disposition == "observation_recorded"
record.disposition.attempt.action_id is None
```

No terminal `done` application, stream halt assertion, or provider call belongs
in this scenario.

### 3. Execution Ref Used As Action Id Is Blocked

Given:

```text
current_node_id="repair_same_component"
context.current_node.execution_ref == "gh_update_script:v1"
allowed action is "draft_repair_params"
```

Worker:

```text
wrongly requests action_id="gh_update_script:v1"
```

Assert:

```text
record.status == "completed"
record.reason == "completed:blocked"
record.disposition.disposition == "blocked"
record.disposition.attempt.failure == "unknown_action_id"
record.disposition.attempt.action_id == "gh_update_script:v1"
```

The execution ref is visible context, not authority.

### 4. No Allowed Actions Blocks Action Request

Given:

```text
context.allowed_actions == ()
```

Worker:

```text
requests "draft_repair_params"
```

Assert:

```text
record.status == "completed"
record.disposition.disposition == "blocked"
record.disposition.attempt.failure == "unknown_action_id"
```

Clarification, refusal, and observation remain valid when no actions are
available; this scenario probes action requests specifically.

### 5. Script-Body Gotcha Produces Body-Style Repair Request

Given:

```text
WorkerKnowledgePacket(
  packet_id="gh_csharp_script_body_gotcha",
  kind="gotcha",
  content={
    "trust": "high",
    "failure_family": "wrong_code_shape",
    "guidance": "Use RhinoCode C# script body code, not a GH_Component subclass.",
  },
)
```

Worker:

```text
requests "draft_repair_params" with body-style repair input
```

Assert the response evidence, not schema validation:

```python
payload = record.response.payload
assert isinstance(payload, WorkerActionRequest)
assert payload.action_id == "draft_repair_params"
assert payload.input["mode"] == "body"
assert "GH_Component" not in payload.input["code"]
```

This is not a C# validator. It proves that explicit gotcha knowledge can shape a
bounded action request away from a known-wrong code form.

### 6. Missing Script-Body Gotcha Produces Clarification

Given:

```text
same repair context as scenario 5
no gh_csharp_script_body_gotcha packet
```

Worker:

```text
asks clarification instead of inventing repair assumptions
```

Assert:

```text
record.status == "completed"
record.response.payload is WorkerClarificationRequest
record.disposition.disposition == "clarification_needed"
record.disposition.attempt.action_id is None
```

This proves gotcha packets are explicit inputs, not hidden global context.

### 7. Public MCP Wire-Shape Gotcha Produces Observation

Given a hardcoded packet:

```text
failure_family="wire_shape_confusion"
guidance="MCP success text parses as the data payload itself, not data.data."
source="docs/CURRENT_ARCHITECTURE.md"
```

Worker:

```text
returns WorkerObservation acknowledging the interpretation boundary
```

Assert:

```text
record.status == "completed"
record.response.payload is WorkerObservation
record.disposition.disposition == "observation_recorded"
record.disposition.attempt.action_id is None
```

No MCP parsing helper, tool call, or docs read is allowed.

### 8. GH Bridge Capability Uncertainty Produces Clarification

Given a caller-pushed capability note:

```text
kind="capability_note"
content={
  "trust": "medium",
  "capability": "grasshopper_bridge",
  "status": "unknown_or_unavailable",
  "guidance": "Clarify availability before requesting GH-affecting action.",
}
```

Worker:

```text
asks clarification before requesting GH-affecting action
```

Assert:

```text
record.status == "completed"
record.response.payload is WorkerClarificationRequest
record.disposition.disposition == "clarification_needed"
record.disposition.attempt.action_id is None
```

No live GH/Rhino check, MCP call, server status query, or capability registry is
allowed.

### 9. Recent Needs-Repair History Requests Bounded Repair Action

History scenarios use direct `CurrentStepRecord` and `EnvelopeSupplyRecord`
fixtures. They populate only the flattened fields LM5A summarizes. They may use
`object()` placeholders for canonical runtime objects.

Given:

```text
CurrentStepRecord:
  accepted_node_id="verify_create"
  execution_kind="verifier"
  ran=True
  execution_failure=None

EnvelopeSupplyRecord:
  decision="SUPPLY"
  metadata={"selected_node_id": "repair_same_component"}
```

Worker:

```text
sees recent supply selected the repair node / history hint
requests "draft_repair_params"
```

Assert:

```text
context.history.recent_supplies[-1].selected_node_id == "repair_same_component"
record.disposition.disposition == "candidate_action_request"
record.disposition.attempt.action_id == "draft_repair_params"
```

No LM4S, LM4R, provider, runner, mapper, executor, or graph advancement belongs
in this scenario.

### 10. Recent Blocked Unknown Action Is Knowledge-Packet Led

Recent blocked unknown action is represented by an explicit
`WorkerKnowledgePacket`, because LM5A history summarizes LM4S records, not LM5D
harness records.

Given:

```text
WorkerKnowledgePacket(
  kind="attempt_memory",
  content={
    "prior_failure": "unknown_action_id",
    "action_id": "gh_update_script:v1",
    "guidance": "Do not repeat the same invalid action id.",
  },
)
```

Worker:

```text
returns clarification or observation and does not repeat the bad action id
```

Assert:

```text
record.status == "completed"
record.disposition.disposition in {"clarification_needed", "observation_recorded"}
record.disposition.attempt.action_id is None
```

Do not smuggle LM5D harness records into LM5A history.

### 11. Out-Of-Scope Operation Is Refused

Given:

```text
caller-pushed knowledge says the requested operation is outside declared scope
allowed actions may exist
```

Worker:

```text
returns WorkerRefusal(category="out_of_scope", reason=...)
```

Assert:

```text
record.status == "completed"
record.response.payload is WorkerRefusal
record.response.payload.category == "out_of_scope"
record.disposition.disposition == "refusal_recorded"
record.disposition.attempt.valid is True
record.disposition.attempt.action_id is None
```

This is not a safety policy engine, classifier, or escalation mechanism. It
proves the response channel can carry a refusal cleanly.

### 12. Worker Exception Smoke Is Anchored

Given:

```text
real repair context
```

Worker:

```text
raises ValueError
```

Assert:

```text
record.status == "worker_error"
record.response is None
record.disposition is None
record.failure == "worker_exception"
record.reason == "worker_exception:ValueError"
record.context_workflow_id == context.workflow.workflow_id
record.context_contract_fingerprint == context.workflow.contract_fingerprint
```

This is the only harness-failure smoke required by LM5E. LM5D owns the detailed
failure matrix.

---

## 7. Assertion Style

LM5E should inspect the useful LM5A-D trail, not just top-level harness status.

Common assertions should include:

```text
record.status
record.reason
record.response payload kind
record.disposition.disposition
record.disposition.attempt.valid / failure / action_id
record.context_workflow_id / context_contract_fingerprint
```

Small test-local assertion helpers are allowed, for example:

```python
_assert_completed_action(record, context, action_id)
_assert_blocked_unknown_action(record, context, action_id)
_assert_completed_observation(record, context)
_assert_completed_clarification(record, context)
_assert_completed_refusal(record, context, category)
```

Keep scenario-specific facts visible in the test body, especially gotcha packet
contents and action input assertions.

---

## 8. Import And Boundary Rules

Allowed test imports include:

- LM5A public context APIs;
- LM5B public response APIs;
- LM5C public disposition APIs if needed for assertions;
- LM5D `run_local_worker_turn`;
- LM4 workflow contract compiler APIs for fixture creation;
- `CurrentStepRecord` and `EnvelopeSupplyRecord` constructors for direct
  history fixtures;
- ordinary pytest and dataclass/type inspection helpers.

LM5E tests must not import or call:

- `run_current_step_stream`;
- `run_current_mapped_step`;
- `execute_mapped_step`;
- `map_accepted_proposal_to_step`;
- `revalidate_proposal`;
- `propose_next_node`;
- `CatalogCurrentStepProvider`;
- `WorkflowProvenanceEnvelopeSource`;
- live Rhino/GH runner surfaces;
- RookChat, model, prompt, server, dispatcher, or tool execution surfaces;
- retry, fallback, critic, or oversight machinery;
- production scenario modules or canned workers.

LM5E should not import `json` at all unless the AST guard itself truly needs it,
which it should not. Hardcoded packet fixtures need no JSON parsing or dumping.

File and knowledge reads are banned:

- no `operations_knowledge.json` reads;
- no component catalog reads;
- no session log reads;
- no docs file reads;
- no knowledge-store APIs;
- no `Path`, `read_text`, `open`, `json.load`, or fixture generation from files.

The AST/import guard should prefer `inspect.getsource(module)` over file IO. If
implementation needs a direct source read for the guard, it must be scoped to
the scenario test module source itself. It must not read docs, knowledge files,
catalogs, logs, or fixture files.

---

## 9. Tests And Verification

Targeted:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server/tests/test_local_worker_turn_scenarios.py -q
```

Nearby LM5 regression:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server/tests/test_local_worker_turn_context.py `
  mcp_server/tests/test_local_worker_turn_response.py `
  mcp_server/tests/test_local_worker_turn_disposition.py `
  mcp_server/tests/test_local_worker_turn_harness.py `
  mcp_server/tests/test_local_worker_turn_scenarios.py `
  -q
```

Focused PlanGraph/local-worker gate:

```powershell
$files = Get-ChildItem mcp_server\tests -Filter 'test_plan_graph*.py' | Sort-Object Name | ForEach-Object { $_.FullName }
mcp_server\.venv\Scripts\python.exe -m pytest @files `
  mcp_server\tests\test_local_worker_turn_context.py `
  mcp_server\tests\test_local_worker_turn_response.py `
  mcp_server\tests\test_local_worker_turn_disposition.py `
  mcp_server\tests\test_local_worker_turn_harness.py `
  mcp_server\tests\test_local_worker_turn_scenarios.py `
  -q
```

Static/scope checks:

- `git diff --check`;
- diff contains only:
  - this spec;
  - the LM5E plan;
  - `mcp_server/tests/test_local_worker_turn_scenarios.py`;
- production diff is empty;
- no LM5A/B/C/D production source diffs;
- no `base_agent.py`, `src/Rook`, `src/RookNative`, or
  `knowledge/gh/operations_knowledge.json` drift;
- AST/import guard over `test_local_worker_turn_scenarios.py` for banned
  stream/runtime/live/model/file/knowledge-store surfaces.

No live test, model test, RookChat test, stream test, or dispatcher test belongs
to LM5E.

---

## 10. Non-Goals

LM5E does not add:

- production code;
- public scenario dataclasses;
- public scenario builders;
- production canned workers;
- scenario registry;
- model calls;
- prompt rendering;
- raw worker payload parsing;
- response serialization;
- action input schema validation;
- action authorization;
- action dispatch or execution;
- graph mutation;
- stream continuation;
- retry-with-learning;
- fallback-chain;
- worker-critic;
- oversight;
- timing, timeouts, or budgets;
- knowledge retrieval;
- knowledge trust policy;
- file/text/JSON/YAML loading;
- RookChat integration;
- live Rhino/GH coverage.

LM5E is only a deterministic, test-local scenario suite proving the existing
LM5A-D worker boundary carries Rook-shaped situations and produces useful audit
trails.
