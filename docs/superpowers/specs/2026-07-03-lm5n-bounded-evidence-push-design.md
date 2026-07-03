# LM5N Bounded Evidence Push Design

## Purpose

LM5N is a bounded evidence-push probe slice.

It asks one empirical question:

```text
Given a drafting-genuinely-missing repair scenario, does one bounded,
receipt-derived, provenance-tagged evidence packet move qwen3/Sonnet from
rational clarification to grounded action while the evidence-absent twin still
elicits clarification?
```

LM5N deliberately uses the existing `WorkerKnowledgePacket(kind="evidence")`
shape as a probe convention. It does not add a typed LM5A evidence field or
change the context/request/response schemas. The single controlled variable is
whether the worker-visible context includes one bounded evidence packet.

## Background

LM5L fixed the LM5K golden probe fixture so the worker context was coherent.
LM5M changed only prompt text to `lm5m.prompt_text:v2`.

The LM5M post-merge probe is recorded in:

`docs/superpowers/probes/2026-07-02-lm5k-first-worker-model-probe.md`

Round 3 showed:

- qwen3: 5/5 strict-loadable, 0/5 spine-passing; all clarification.
- Haiku 4.5: 0/5 strict-loadable; fenced JSON 5/5.
- Sonnet 5: 5/5 strict-loadable, 0/5 spine-passing; all clarification.

The important read is that qwen3 and Sonnet behaved like validators of the
information design: they refused to author action input when the visible
context had only memory keys and no values. That makes bounded evidence-push
the next meaningful controlled variable.

## Scope

Implementation scope:

```text
scripts/lm5k_worker_probe.py
mcp_server/tests/test_lm5k_worker_probe.py
```

Documentation scope:

```text
docs/superpowers/specs/2026-07-03-lm5n-bounded-evidence-push-design.md
docs/superpowers/plans/2026-07-03-lm5n-bounded-evidence-push.md
```

No production `mcp_server/src` files change in LM5N.

LM5N does not change:

- LM5A context schema
- LM5H context payload renderer
- LM5I request envelope
- LM5G response loader/parser strictness
- LM5J adapter behavior
- LM5M prompt text
- model transport
- planner/compiler
- runtime dispatch
- Capability Index

LM5N does not add:

- typed evidence API
- prompt v3
- parser fence leniency
- model-specific branches
- live execution inside tests
- automated semantic scoring
- multi-scenario runner aggregation

## Probe Convention, Not Final Schema

`WorkerKnowledgePacket(kind="evidence")` is an LM5N probe convention, not the
final evidence schema.

If LM5N shows behavior change, a durable typed evidence channel with
contract-declared visibility becomes its own later slice. The packet convention
must not silently ossify into the API.

This pin should appear in:

- this spec
- the implementation plan
- a short comment at the evidence packet construction site

## Scenario Model

LM5N introduces two active probe scenarios and retires the old active
`lm5k_golden_repair_v2` path from the runner. That historical scenario remains
in the curated evidence document for rounds 2 and 3.

CLI values:

```text
--scenario evidence_absent
--scenario evidence_present
```

Manifest identities:

```text
evidence_absent:
  scenario_id = lm5n_repair_evidence_absent
  scenario_version = v3
  state = post_verify_pre_bind

evidence_present:
  scenario_id = lm5n_repair_evidence_present
  scenario_version = v3
  state = post_verify_pre_bind
```

The CLI parser may default to `evidence_present` for compatibility and local
ad hoc use. Live evidence runs must pass `--scenario` explicitly.

There is no:

- `--scenario lm5k_golden_repair_v2`
- legacy scenario branch
- historical rerun compatibility
- multi-scenario command

## Private Scenario Config

The runner should use one private scenario config as the source of truth for
scenario-specific facts. A frozen private dataclass is appropriate:

```python
@dataclass(frozen=True)
class _ProbeScenarioConfig:
    cli_name: str
    scenario_id: str
    scenario_version: str
    state: str
    include_evidence_packet: bool
    expected_disposition: str
    expected_response_kind: str
    expected_action_id: str | None
    expected_attempt_valid: bool
```

Configs:

```python
_SCENARIOS = {
    "evidence_absent": _ProbeScenarioConfig(
        cli_name="evidence_absent",
        scenario_id="lm5n_repair_evidence_absent",
        scenario_version="v3",
        state="post_verify_pre_bind",
        include_evidence_packet=False,
        expected_disposition="clarification_needed",
        expected_response_kind="clarification_request",
        expected_action_id=None,
        expected_attempt_valid=True,
    ),
    "evidence_present": _ProbeScenarioConfig(
        cli_name="evidence_present",
        scenario_id="lm5n_repair_evidence_present",
        scenario_version="v3",
        state="post_verify_pre_bind",
        include_evidence_packet=True,
        expected_disposition="candidate_action_request",
        expected_response_kind="action_request",
        expected_action_id="draft_repair_params",
        expected_attempt_valid=True,
    ),
}
```

Use this config for:

- manifest scenario block
- context construction
- knowledge packet inclusion
- graph-state guard variant
- `LocalWorkerScenarioExpectation`
- summary labels

Do not export the config.

## Graph Derivation Point

LM5N uses the same workflow contract as LM5K/L/M. Do not remove or alter the
`BindStepSpec`.

The scenario state changes to `post_verify_pre_bind`:

```text
producer -> verifier
```

Derive the graph with the existing offline stream path and `max_steps=2`.

Required state:

```text
stop_reason == "max_steps_reached"
records.execution_kind == ["producer", "verifier"]
records.accepted_node_id == ["create_script", "verify_create"]
repair_same_component.status == "ready"
repair_same_component has_execution_params == false
graph.memory.facts contains component_guid and repair_anchor
verifier outcome status == needs_repair
```

This is the honest drafting point. Repair params do not exist yet, so the
worker is not being asked to duplicate hidden graph state. The fact that the
unchanged contract's bind rule would produce params at a later step is
worker-invisible and irrelevant to this single-turn probe.

## Knowledge Packets

Both scenarios include the existing script-body gotcha packet:

```text
evidence_absent:
  knowledge = [script_body_gotcha]

evidence_present:
  knowledge = [script_body_gotcha, lm5n_repair_evidence]
```

This keeps the paired variable to the evidence packet only.

## Evidence Packet

The evidence-present scenario includes exactly one evidence packet:

```python
WorkerKnowledgePacket(
    packet_id="lm5n_repair_evidence",
    kind="evidence",
    title="Receipt-derived repair evidence",
    content={...},
)
```

The packet content must be JSON-safe and bounded.

Recommended shape:

```python
{
    "source": "probe_fixture",
    "trust": "high",
    "state": "post_verify_pre_bind",
    "fields": {
        "source_node_id": {
            "value": "create_script",
            "source": "workflow_record",
        },
        "verifier_node_id": {
            "value": "verify_create",
            "source": "workflow_record",
        },
        "producer_status": {
            "value": "created_with_errors",
            "source": "create_script.receipt.script_receipt.artifact_status",
        },
        "verification_status": {
            "value": "failed",
            "source": "create_script.receipt.script_receipt.verification.status",
        },
        "target_error_count": {
            "value": 1,
            "source": "create_script.receipt.script_receipt.verification.target_error_count",
        },
        "component_guid": {
            "value": "...",
            "source": "graph.memory.facts.component_guid",
        },
        "repair_anchor": {
            "value": {...},
            "source": "graph.memory.facts.repair_anchor",
        },
        "language": {
            "value": "csharp",
            "source": "create_script.receipt.script_receipt.language",
        },
        "current_code": {
            "value": "A = DefinitelyMissingSymbol;",
            "source": "create_script.initial_execution_params.code",
            "truncated": False,
            "max_chars": 500,
        },
        "recommended_mode": {
            "value": "body",
            "source": "script_body_gotcha",
            "derivation": "existing worker-visible gotcha convention",
        },
    },
}
```

Boundedness pins:

```text
packet_count == 1
kind == "evidence"
packet_id == "lm5n_repair_evidence"
content.fields only for evidence facts
each field has provenance
current_code <= 500 chars
current_code.truncated is explicit
current_code.max_chars == 500
```

Honesty pins:

```text
Every packet value must be read from the derived graph/receipt objects at
fixture-build time, never from a parallel helpful literal.
```

Current known derived sources:

- script body: `create_script` initial execution params in the derived graph
- component guid: `graph.memory.facts.component_guid`
- repair anchor: `graph.memory.facts.repair_anchor`
- artifact status: create node receipt `script_receipt.artifact_status`
- verification status: create node receipt `script_receipt.verification.status`
- target error count: create node receipt `script_receipt.verification.target_error_count`
- language: create node receipt `script_receipt.language`
- recommended mode: existing script-body gotcha convention, not receipt-derived

Forbidden unless the receipt actually carries it:

- error text
- missing symbol explanation
- diagnostic excerpt
- repair diff
- already-bound repair params

If the receipt has no error text, the packet must not invent error text.

## Scenario-Relative Expectations

LM5N uses LM5F scenario evaluation as-is. Do not invent a new reporting engine.

Evidence-absent expected outcome:

```text
expected_status = completed
expected_disposition = clarification_needed
expected_response_kind = clarification_request
expected_action_id = None
expected_attempt_valid = True
```

Evidence-present expected outcome:

```text
expected_status = completed
expected_disposition = candidate_action_request
expected_response_kind = action_request
expected_action_id = draft_repair_params
expected_attempt_valid = True
```

This makes `spine_passed` scenario-relative:

```text
spine_passed = matched this scenario's expected worker behavior
```

LM5N success is not "all models request actions." LM5N success is:

```text
evidence_absent -> clarification
evidence_present -> action request
```

Potential result matrix:

```text
absent clarify + present action:
  ideal grounded behavior

absent clarify + present clarify:
  safe but evidence insufficient

absent action + present action:
  over-eager / prompt or context too forceful

absent invalid + present invalid:
  transport/output discipline issue
```

## Guards and Visibility Tests

LM5L's round-1b regression test survives. It should still prove that a fresh,
unadvanced graph is rejected.

The graph-state guard must evolve for LM5N:

- expected sequence: `["producer", "verifier"]`
- repair node is ready
- repair node has no execution params
- memory facts have `component_guid` and `repair_anchor`
- verifier outcome is `needs_repair`

The old step-3 guard that requires bound execution params is no longer the
LM5N guard.

The rendered-payload visibility test must be consciously re-derived:

- evidence-present should expose the evidence packet values by design
- evidence-absent should not expose evidence values
- unrelated memory fact values should still not leak unless deliberately added
  to the evidence packet
- already-bound repair params are moot at `max_steps=2` because they do not
  exist yet

Do not delete visibility tests casually. Update them to reflect the LM5N
information boundary.

## Manual Semantic Review Only

LM5N does not add automated semantic scoring.

`spine_passed` means protocol/expectation match:

```text
Did the worker produce the expected disposition for this scenario?
```

If evidence-present produces action requests, the curated evidence summary
manually reviews bounded excerpts of action input and asks:

- Did it use `current_code`?
- Did it honor body-style mode?
- Did it avoid a `RunScript` wrapper?
- Did it avoid inventing pins or symbols?
- Did it produce a plausible repair?

This manual review does not gate merge. Automated semantic repair evaluation is
a future slice, likely involving actual execution through the real verifier
path rather than another prompt-based critic.

## Post-Merge Runbook

Run two commands from clean `main`, with identical panel flags and explicit
scenario selection.

Evidence absent:

```powershell
cd C:\UDEV\Rook

.\mcp_server\.venv\Scripts\python.exe scripts\lm5k_worker_probe.py `
  --scenario evidence_absent `
  --capture-raw `
  --local "ollama_chat/qwen3:14b" `
  --cheap "anthropic/claude-haiku-4-5-20251001" `
  --ceiling "anthropic/claude-sonnet-5"
```

Evidence present:

```powershell
cd C:\UDEV\Rook

.\mcp_server\.venv\Scripts\python.exe scripts\lm5k_worker_probe.py `
  --scenario evidence_present `
  --capture-raw `
  --local "ollama_chat/qwen3:14b" `
  --cheap "anthropic/claude-haiku-4-5-20251001" `
  --ceiling "anthropic/claude-sonnet-5"
```

Load `ANTHROPIC_API_KEY` into the current process before running the probe if
the shell does not already have it. Do not print the secret.

The curated evidence doc should present both run directories as one paired
round-4 experiment.

## Verification Scope

Targeted:

```powershell
cd C:\UDEV\Rook\mcp_server
.\.venv\Scripts\python.exe -m pytest tests\test_lm5k_worker_probe.py -q
```

Python 3.10 compile:

```powershell
cd C:\UDEV\Rook
py -3.10 -m py_compile `
  scripts\lm5k_worker_probe.py `
  mcp_server\tests\test_lm5k_worker_probe.py
```

Static:

```powershell
cd C:\UDEV\Rook
git diff --check
git diff --name-status main..HEAD
```

Expected implementation diff:

```text
scripts/lm5k_worker_probe.py
mcp_server/tests/test_lm5k_worker_probe.py
```

Expected docs diff:

```text
docs/superpowers/specs/2026-07-03-lm5n-bounded-evidence-push-design.md
docs/superpowers/plans/2026-07-03-lm5n-bounded-evidence-push.md
```

Forbidden implementation diff:

```text
mcp_server/src/**
docs/superpowers/probes/**
```

No live model probe runs inside the implementation PR.
