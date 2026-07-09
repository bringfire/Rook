# LM8I Affine Publication Shape Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `scripts/lm8i_affine_publication_shape_support_probe.py`, a sibling live probe that tests whether one exact-only publication-support turn can recover the LM8H skeletal pass-1 `action_request` missing `action_id` failure.

**Architecture:** Copy/adapt LM8H's affine live probe into a new LM8I script, then add script-local publication-support policy around the existing unchanged `run_two_pass_worker_publication(...)` helper. LM8I owns eligibility, support packet construction, ordered publication rows, final-row compatibility, and decision metadata; the shared two-pass helper still owns pass-1/pass-2 mechanics and row shape.

**Tech Stack:** Python 3.10, existing Rook MCP server test harness, existing scalar applier modules, existing local worker turn rendering modules, pytest fake GH tool executors and fake publication runners.

## Global Constraints

- New sibling script: `scripts/lm8i_affine_publication_shape_support_probe.py`.
- New focused tests: `mcp_server/tests/test_lm8i_affine_publication_shape_support_probe.py`.
- Do not modify `scripts/lm_worker_two_pass_publication.py`.
- Do not modify LM8H behavior or evidence.
- Use the same canonical affine fixture as LM8H.
- Use the same canonical worker model: `gemma4:12b-it-qat`.
- Use the same action authority: `draft_gh_set_value_params {"value": number}`.
- Use exactly one support turn, only when exact eligibility matches.
- No action id autofill.
- No raw pass-1 provider transcript persistence for eligibility.
- Eligibility uses only `pass1_content_excerpt` and `pass1_content_sha256` from the shared publication row.
- No hidden derived value `3.0` in worker-visible/support/pre-publication artifacts or script source.
- No raw target GUID in worker-visible/support/request/decision/verifier artifacts.
- No worker-authored GH tools, topology, wiring, scripts, code, or `gh_edit`.
- No retry loop, no model panel, no Planner model, no N=5.
- No live run in the implementation PR.

---

## File Structure

- Create `scripts/lm8i_affine_publication_shape_support_probe.py`.
  - Responsibility: LM8I canonical CLI, affine fixture/runtime copied from LM8H, exact publication-support policy, artifact writing, decision records, and live dispatch after a valid final action.
- Create `mcp_server/tests/test_lm8i_affine_publication_shape_support_probe.py`.
  - Responsibility: fake-tool/fake-publication coverage for LM8I CLI, support eligibility, support packet authority, publication rows, final compatibility row, no raw transcript, and terminal metadata.
- Modify no shared publication helper files.
- Modify no LM8H script or tests unless a pure import/collision issue is proven by tests; default expectation is no LM8H changes.

---

### Task 1: Scaffold LM8I Sibling Script And Test Harness

**Files:**
- Create: `scripts/lm8i_affine_publication_shape_support_probe.py`
- Create: `mcp_server/tests/test_lm8i_affine_publication_shape_support_probe.py`

**Interfaces:**
- Consumes: LM8H script structure from `scripts/lm8h_affine_scalar_depth_probe.py`.
- Produces:
  - `SCRIPT_SCHEMA = "rook.lm8i_affine_publication_shape_support_probe:v1"`
  - `DECISION_SCHEMA = "rook.lm8i_affine_publication_shape_support_decision:v1"`
  - `_args(argv: Sequence[str] | None = None) -> argparse.Namespace`
  - `_new_run_dir(root: str | Path) -> Path`
  - `_manifest(...) -> dict[str, Any]`

- [ ] **Step 1: Copy LM8H script to LM8I path**

Copy `scripts/lm8h_affine_scalar_depth_probe.py` to `scripts/lm8i_affine_publication_shape_support_probe.py`, then update the top-level identity constants:

```python
SCRIPT_SCHEMA = "rook.lm8i_affine_publication_shape_support_probe:v1"
DECISION_SCHEMA = "rook.lm8i_affine_publication_shape_support_decision:v1"
RUN_PREFIX = "lm8i"
```

Keep the affine fixture constants unchanged:

```python
INITIAL_EDITABLE_VALUE = 2.0
FACTOR_VALUE = 2.0
OFFSET_VALUE = 1.5
INITIAL_OBSERVED_OUTPUT = 5.5
EXPECTED_OUTPUT_VALUE = 7.5
ACTION_ID = "draft_gh_set_value_params"
```

Do not introduce a `3.0` constant. Tests may use `3.0`; the LM8I script must not contain raw `"3.0"`.

- [ ] **Step 2: Update CLI identity and unsupported flags**

Keep LM8H's canonical defaults:

```python
def _args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="LM8I affine publication shape support live probe."
    )
    parser.add_argument("--model", default="gemma4:12b-it-qat")
    parser.add_argument("--endpoint", default="http://localhost:11434/api/chat")
    parser.add_argument("--temperature", type=float, default=0)
    parser.add_argument("--timeout-s", type=float, default=120)
    parser.add_argument("--excerpt-chars", type=int, default=1200)
    parser.add_argument("--run-dir", default="probe_runs")
    parser.add_argument("--canonical-evidence", action="store_true", default=True)
    args, unknown = parser.parse_known_args(argv)
    if unknown:
        parser.error(f"unsupported arguments: {' '.join(unknown)}")
    args.canonical_evidence = (
        args.model == "gemma4:12b-it-qat"
        and args.temperature == 0
        and args.canonical_evidence is True
    )
    return args
```

Preserve rejection of these unsupported surfaces through the `unknown` path:

```text
--phase
--attempts
--retry-clean-observation
--planner-provider-command
--prompt-profile
--request-json
--gh-edit
```

- [ ] **Step 3: Write scaffold tests**

Add the loader/test helpers by adapting the LM8H test harness:

```python
import importlib.util
import inspect
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest


def _script_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "lm8i_affine_publication_shape_support_probe.py"
    )


def _load_script():
    path = _script_path()
    spec = importlib.util.spec_from_file_location(
        "lm8i_affine_publication_shape_support_probe",
        path,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


PROBE = _load_script()
```

Add tests:

```python
def test_cli_defaults_are_canonical_lm8i_shape():
    args = PROBE._args([])

    assert args.model == "gemma4:12b-it-qat"
    assert args.endpoint == "http://localhost:11434/api/chat"
    assert args.temperature == 0
    assert args.timeout_s == 120
    assert args.excerpt_chars == 1200
    assert args.run_dir == "probe_runs"
    assert args.canonical_evidence is True


def test_cli_rejects_non_lm8i_surfaces():
    forbidden = [
        ["--phase", "receipt_recon"],
        ["--attempts", "5"],
        ["--retry-clean-observation"],
        ["--planner-provider-command", "x"],
        ["--prompt-profile", "shape_guidance_v2"],
        ["--request-json", "request.json"],
        ["--gh-edit"],
    ]
    for argv in forbidden:
        with pytest.raises(SystemExit):
            PROBE._args(argv)


def test_manifest_records_lm8i_identity():
    manifest = PROBE._manifest(
        model="gemma4:12b-it-qat",
        endpoint="http://localhost:11434/api/chat",
        temperature=0,
        canonical_evidence=True,
    )

    assert manifest["schema"] == "rook.lm8i_affine_publication_shape_support_probe:v1"
    assert manifest["attempts"] == 1
    assert manifest["publication_support_enabled"] is True
    assert manifest["publication_support_budget"] == 1
    assert manifest["support_eligibility"] == "exact_skeletal_action_request_missing_action_id"
    assert manifest["worker_retry_enabled"] is False
    assert manifest["planner_model"] is None
    assert manifest["gh_edit_enabled"] is False
```

- [ ] **Step 4: Run scaffold tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_lm8i_affine_publication_shape_support_probe.py -q
```

Expected at this point: scaffold tests pass after the script identity is corrected. If failures mention LM8H schema or run prefix, finish the identity rename before continuing.

- [ ] **Step 5: Commit Task 1**

```powershell
git add scripts\lm8i_affine_publication_shape_support_probe.py mcp_server\tests\test_lm8i_affine_publication_shape_support_probe.py
git commit -m "feat(lm8i): scaffold affine publication support probe"
```

---

### Task 2: Exact Support Eligibility And Support Context Helpers

**Files:**
- Modify: `scripts/lm8i_affine_publication_shape_support_probe.py`
- Modify: `mcp_server/tests/test_lm8i_affine_publication_shape_support_probe.py`

**Interfaces:**
- Consumes: shared publication row fields `status`, `failure_reason`, `pass1_content_excerpt`, `pass1_content_sha256`.
- Produces:
  - `_publication_support_eligibility(row: Mapping[str, Any]) -> dict[str, Any]`
  - `_publication_support_context(row: Mapping[str, Any], *, excerpt_chars: int) -> dict[str, Any]`

- [ ] **Step 1: Write exact eligibility tests**

Add tests:

```python
def _pass1_missing_row(excerpt, *, sha="sha256:abc"):
    return {
        "status": "pass1_decision_invalid",
        "failure_reason": "pass1_missing_action_id",
        "pass1_content_excerpt": excerpt,
        "pass1_content_sha256": sha,
    }


def test_support_eligibility_accepts_exact_skeletal_action_request_excerpt():
    result = PROBE._publication_support_eligibility(
        _pass1_missing_row('{"kind": "action_request"}')
    )

    assert result == {
        "support_eligible": True,
        "support_not_attempted_reason": None,
        "previous_response_kind": "action_request",
        "previous_response_excerpt": '{"kind": "action_request"}',
        "previous_response_sha256": "sha256:abc",
    }


@pytest.mark.parametrize(
    ("excerpt", "reason"),
    [
        ('{"kind":"action_reques', "pass1_excerpt_not_exact_skeletal_json"),
        ('{"kind":"action_request"}', "pass1_excerpt_not_exact_skeletal_json"),
        (' {"kind": "action_request"}', "pass1_excerpt_not_exact_skeletal_json"),
        ('{"kind": "action_request"} ', "pass1_excerpt_not_exact_skeletal_json"),
        ('{"kind": "observation", "kind": "action_request"}', "pass1_excerpt_not_exact_skeletal_json"),
        ('{"kind":"action_request","action_id":""}', "pass1_excerpt_not_exact_skeletal_json"),
        ('{"kind":"action_request","action_id":"wrong"}', "pass1_excerpt_not_exact_skeletal_json"),
        ('{"kind":"action_request","input":{"value":3.0}}', "pass1_excerpt_not_exact_skeletal_json"),
        ('{"kind":"observation"}', "pass1_excerpt_not_exact_skeletal_json"),
        ("not json", "pass1_excerpt_not_exact_skeletal_json"),
    ],
)
def test_support_eligibility_rejects_non_exact_excerpts(excerpt, reason):
    result = PROBE._publication_support_eligibility(_pass1_missing_row(excerpt))

    assert result["support_eligible"] is False
    assert result["support_not_attempted_reason"] == reason


def test_support_eligibility_rejects_wrong_status_or_failure_reason():
    wrong_status = PROBE._publication_support_eligibility(
        {
            "status": "published",
            "failure_reason": None,
            "pass1_content_excerpt": '{"kind": "action_request"}',
            "pass1_content_sha256": "sha256:abc",
        }
    )
    wrong_reason = PROBE._publication_support_eligibility(
        {
            "status": "pass1_decision_invalid",
            "failure_reason": "pass1_unknown_kind",
            "pass1_content_excerpt": '{"kind": "action_request"}',
            "pass1_content_sha256": "sha256:abc",
        }
    )

    assert wrong_status["support_eligible"] is False
    assert wrong_status["support_not_attempted_reason"] == (
        "first_publication_not_exact_skeletal_missing_action_id"
    )
    assert wrong_reason["support_eligible"] is False
    assert wrong_reason["support_not_attempted_reason"] == (
        "first_publication_not_exact_skeletal_missing_action_id"
    )
```

These tests must not require raw provider output.

- [ ] **Step 2: Implement `_publication_support_eligibility`**

Add:

```python
SUPPORT_PACKET_ID = "lm8i_publication_support_context"
SUPPORT_REASON = "previous_pass1_missing_action_id"


def _publication_support_eligibility(row: Mapping[str, Any]) -> dict[str, Any]:
    if (
        row.get("status") != "pass1_decision_invalid"
        or row.get("failure_reason") != "pass1_missing_action_id"
    ):
        return {
            "support_eligible": False,
            "support_not_attempted_reason": "first_publication_not_exact_skeletal_missing_action_id",
            "previous_response_kind": None,
            "previous_response_excerpt": None,
            "previous_response_sha256": row.get("pass1_content_sha256"),
        }

    excerpt = row.get("pass1_content_excerpt")
    sha256 = row.get("pass1_content_sha256")
    if not isinstance(sha256, str) or not sha256:
        return {
            "support_eligible": False,
            "support_not_attempted_reason": "pass1_content_sha256_missing",
            "previous_response_kind": None,
            "previous_response_excerpt": excerpt if isinstance(excerpt, str) else None,
            "previous_response_sha256": sha256,
        }
    if not isinstance(excerpt, str):
        return {
            "support_eligible": False,
            "support_not_attempted_reason": "pass1_excerpt_not_exact_skeletal_json",
            "previous_response_kind": None,
            "previous_response_excerpt": None,
            "previous_response_sha256": sha256,
        }

    if excerpt != '{"kind": "action_request"}':
        return {
            "support_eligible": False,
            "support_not_attempted_reason": "pass1_excerpt_not_exact_skeletal_json",
            "previous_response_kind": None,
            "previous_response_excerpt": excerpt,
            "previous_response_sha256": sha256,
        }

    return {
        "support_eligible": True,
        "support_not_attempted_reason": None,
        "previous_response_kind": "action_request",
        "previous_response_excerpt": excerpt,
        "previous_response_sha256": sha256,
    }
```

This intentionally matches the observed LM8H bounded excerpt exactly. It rejects
compact/whitespace-varied equivalents, trailing prose, extra fields, empty
`action_id`, wrong `action_id`, embedded `input`, duplicate-key tricks, and
missing `pass1_content_sha256`.

- [ ] **Step 3: Write support context tests**

Add:

```python
def test_publication_support_context_is_bounded_and_contains_no_authority_leaks():
    row = _pass1_missing_row('{"kind": "action_request"}', sha="sha256:pass1")

    context = PROBE._publication_support_context(row, excerpt_chars=1200)
    rendered = json.dumps(context, sort_keys=True)

    assert context["packet_id"] == "lm8i_publication_support_context"
    assert context["kind"] == "publication_support"
    assert context["fields"]["support_reason"] == "previous_pass1_missing_action_id"
    assert context["fields"]["previous_response_kind"] == "action_request"
    assert context["fields"]["previous_response_excerpt"] == '{"kind": "action_request"}'
    assert context["fields"]["previous_response_sha256"] == "sha256:pass1"
    assert context["fields"]["required_action_id"] == "draft_gh_set_value_params"
    assert context["fields"]["pass1_decision_required_fields_if_acting"] == [
        "kind",
        "action_id",
    ]
    assert "3.0" not in rendered
    assert "EDITABLE-GUID-1" not in rendered
    assert '"gh_set_value"' not in rendered
    assert '"tool"' not in rendered
    assert '"tool_name"' not in rendered
    assert "gh_edit" not in rendered
    assert "topology" not in rendered.casefold()


def test_publication_support_context_refuses_ineligible_row():
    with pytest.raises(ValueError, match="support_context_requires_exact_eligibility"):
        PROBE._publication_support_context(
            _pass1_missing_row('{"kind":"action_request","action_id":""}'),
            excerpt_chars=1200,
        )
```

- [ ] **Step 4: Implement `_publication_support_context`**

Add:

```python
def _publication_support_context(
    row: Mapping[str, Any],
    *,
    excerpt_chars: int,
) -> dict[str, Any]:
    eligibility = _publication_support_eligibility(row)
    if eligibility["support_eligible"] is not True:
        raise ValueError("support_context_requires_exact_eligibility")
    previous_excerpt = str(eligibility["previous_response_excerpt"] or "")
    return {
        "packet_id": SUPPORT_PACKET_ID,
        "kind": "publication_support",
        "title": "Publication shape support",
        "fields": {
            "support_reason": SUPPORT_REASON,
            "previous_response_kind": "action_request",
            "previous_response_excerpt": previous_excerpt[:excerpt_chars],
            "previous_response_sha256": eligibility["previous_response_sha256"],
            "required_action_id": ACTION_ID,
            "pass1_decision_required_fields_if_acting": ["kind", "action_id"],
            "instruction": (
                "Your prior pass-1 response selected action_request but omitted "
                "the required action_id. Re-evaluate the same evidence. If action "
                f"is still warranted, publish action_request with action_id {ACTION_ID}. "
                "If action is not warranted, publish a non-action response."
            ),
        },
    }
```

Do not include `3.0`, GUIDs, GH tool names, action input suggestions, topology, wiring, scripts, or code.

- [ ] **Step 5: Run Task 2 tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_lm8i_affine_publication_shape_support_probe.py -q
```

Expected: all scaffold and helper tests pass.

- [ ] **Step 6: Commit Task 2**

```powershell
git add scripts\lm8i_affine_publication_shape_support_probe.py mcp_server\tests\test_lm8i_affine_publication_shape_support_probe.py
git commit -m "feat(lm8i): add exact publication support eligibility"
```

---

### Task 3: Add Support Packet To The Second Worker Request

**Files:**
- Modify: `scripts/lm8i_affine_publication_shape_support_probe.py`
- Modify: `mcp_server/tests/test_lm8i_affine_publication_shape_support_probe.py`

**Interfaces:**
- Consumes: `_publication_support_context(...)`.
- Produces:
  - `_publication_support_knowledge_packet(context: Mapping[str, Any]) -> WorkerKnowledgePacket`
  - `_build_local_turn_payload(..., publication_support_context: Mapping[str, Any] | None = None) -> dict[str, Any]`

- [ ] **Step 1: Write request payload tests**

Add:

```python
def test_support_payload_adds_second_knowledge_packet_without_changing_allowed_action():
    graph = PROBE._graph_from_affine_receipt(_valid_affine_fixture()["receipt"])
    runtime = PROBE._affine_runtime_context(
        graph=graph,
        workflow_contract_payload=PROBE._affine_scalar_contract_payload(),
        convention_packets=(),
    )
    support_context = PROBE._publication_support_context(
        _pass1_missing_row('{"kind": "action_request"}', sha="sha256:pass1"),
        excerpt_chars=1200,
    )

    payload = PROBE._build_local_turn_payload(
        graph=graph,
        packet=runtime["packet"],
        worker_visible=runtime["worker_visible"],
        publication_support_context=support_context,
    )

    knowledge = payload["context"]["knowledge"]
    packets_by_id = {packet["packet_id"]: packet for packet in knowledge}
    support = packets_by_id["lm8i_publication_support_context"]

    assert "gh_affine_scalar_transform_evidence" in packets_by_id
    assert support["kind"] == "publication_support"
    assert support["content"]["required_action_id"] == "draft_gh_set_value_params"
    assert support["content"]["previous_response_sha256"] == "sha256:pass1"
    assert payload["context"]["allowed_actions"] == [
        {
            "action_id": "draft_gh_set_value_params",
            "kind": "stage_params",
            "description": "Draft parameters for setting the trusted editable GH scalar value.",
            "input_schema": {
                "type": "object",
                "required": ["value"],
                "properties": {"value": {"type": "number"}},
                "additionalProperties": False,
            },
        }
    ]
    rendered = json.dumps(payload, sort_keys=True)
    support_rendered = json.dumps(support, sort_keys=True)
    assert "3.0" not in rendered
    assert "EDITABLE-GUID-1" not in rendered
    assert '"gh_set_value"' not in support_rendered
    assert '"tool"' not in support_rendered
    assert '"tool_name"' not in support_rendered
```

- [ ] **Step 2: Implement support knowledge packet**

Add:

```python
def _publication_support_knowledge_packet(
    context: Mapping[str, Any],
) -> WorkerKnowledgePacket:
    if context.get("packet_id") != SUPPORT_PACKET_ID:
        raise ValueError("unexpected_publication_support_packet_id")
    fields = context.get("fields")
    if not isinstance(fields, Mapping):
        raise ValueError("publication_support_fields_not_mapping")
    return WorkerKnowledgePacket(
        packet_id=SUPPORT_PACKET_ID,
        kind="publication_support",
        title="Publication shape support",
        content=dict(fields),
    )
```

- [ ] **Step 3: Update `_build_local_turn_payload` signature**

Change the LM8H-copied helper from:

```python
def _build_local_turn_payload(
    *,
    graph: PlanGraph,
    packet: Mapping[str, Any],
    worker_visible: Mapping[str, Any],
) -> dict[str, Any]:
```

to:

```python
def _build_local_turn_payload(
    *,
    graph: PlanGraph,
    packet: Mapping[str, Any],
    worker_visible: Mapping[str, Any],
    publication_support_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
```

Build the knowledge tuple explicitly:

```python
knowledge_packets: list[WorkerKnowledgePacket] = [
    _affine_scalar_worker_evidence_packet(
        packet=packet,
        worker_visible=worker_visible,
    )
]
if publication_support_context is not None:
    knowledge_packets.append(
        _publication_support_knowledge_packet(publication_support_context)
    )
context = build_local_worker_turn_context(
    _affine_scalar_scaffold(graph),
    graph,
    records=(),
    supply_records=(),
    current_node_id=WORKER_NODE_ID,
    knowledge=tuple(knowledge_packets),
    allowed_actions=(_affine_scalar_allowed_action(),),
)
return dict(render_local_worker_turn_request_payload(context))
```

- [ ] **Step 4: Run request payload tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_lm8i_affine_publication_shape_support_probe.py -q
```

Expected: tests pass, including the new support packet request test.

- [ ] **Step 5: Commit Task 3**

```powershell
git add scripts\lm8i_affine_publication_shape_support_probe.py mcp_server\tests\test_lm8i_affine_publication_shape_support_probe.py
git commit -m "feat(lm8i): render publication support packet"
```

---

### Task 4: Orchestrate First Publication, Optional Support Turn, And Artifacts

**Files:**
- Modify: `scripts/lm8i_affine_publication_shape_support_probe.py`
- Modify: `mcp_server/tests/test_lm8i_affine_publication_shape_support_probe.py`

**Interfaces:**
- Consumes: `_publication_support_eligibility`, `_publication_support_context`, `_build_local_turn_payload`.
- Produces:
  - `_annotate_publication_row(row: Mapping[str, Any], *, turn_index: int, turn_role: str, publication_support_context_present: bool) -> dict[str, Any]`
  - `_publication_safety_failure(publication: Any, component_guids: Sequence[str]) -> str | None`
  - `worker_publication_rows.json`
  - `worker_publication_row.json`
  - `publication_support_context.json`
  - support metadata in every post-publication decision

- [ ] **Step 1: Add fake publication helpers for support tests**

Add to the test file:

```python
class FakeToolExecutor:
    def __init__(self, responses):
        self.responses = dict(responses)
        self.calls = []

    async def __call__(self, tool_name, args):
        self.calls.append((tool_name, dict(args)))
        value = self.responses[tool_name]
        if isinstance(value, list):
            value = value.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


class FakePublication:
    def __init__(self, row, response_payload=None):
        self.row = row
        self.response_payload = response_payload


def _pass1_missing_publication(excerpt='{"kind": "action_request"}'):
    return FakePublication(
        row={
            "status": "pass1_decision_invalid",
            "failure_reason": "pass1_missing_action_id",
            "pass1_content_excerpt": excerpt,
            "pass1_content_sha256": "sha256:pass1",
            "observation_action_intent_anomaly": False,
        },
        response_payload=None,
    )


def _published_action(value=3.0):
    return FakePublication(
        row={
            "status": "published",
            "pass2_response_kind": "action_request",
            "observation_action_intent_anomaly": False,
        },
        response_payload={
            "schema": "rook.local_worker_turn_response:v1",
            "kind": "action_request",
            "action_id": "draft_gh_set_value_params",
            "rationale": "Use the affine relationship to match the expected output.",
            "input": {"value": value},
        },
    )
```

Reuse LM8H's fake fixture response shape, with `gh_inspect_output` returning `5.5` before publication and `7.5` after `gh_set_value`.

- [ ] **Step 2: Write support recovery integration test**

Add:

```python
def test_run_probe_supports_exact_skeletal_pass1_then_accepts(tmp_path):
    executor = FakeToolExecutor(_fixture_responses_for_success())
    captured_payloads = []
    publications = [_pass1_missing_publication(), _published_action(3.0)]

    def fake_publication_runner(payload, **_kwargs):
        captured_payloads.append(payload)
        return publications.pop(0)

    run_dir = PROBE._run_probe(
        model="gemma4:12b-it-qat",
        endpoint="http://localhost:11434/api/chat",
        temperature=0,
        timeout_s=120,
        excerpt_chars=1200,
        run_root=tmp_path,
        canonical_evidence=True,
        tool_executor=executor,
        publication_runner=fake_publication_runner,
    )

    decision = json.loads((run_dir / "decision.json").read_text(encoding="utf-8"))
    rows = json.loads((run_dir / "worker_publication_rows.json").read_text(encoding="utf-8"))
    final_row = json.loads((run_dir / "worker_publication_row.json").read_text(encoding="utf-8"))
    support_context = json.loads((run_dir / "publication_support_context.json").read_text(encoding="utf-8"))
    worker_action = json.loads((run_dir / "worker_action.json").read_text(encoding="utf-8"))

    assert len(captured_payloads) == 2
    assert decision["decision"] == "accepted"
    assert decision["reason"] == "verify_scalar_output_succeeded"
    assert decision["publication_support_attempted"] is True
    assert decision["publication_support_count"] == 1
    assert decision["support_eligible"] is True
    assert decision["first_publication_status"] == "pass1_decision_invalid"
    assert decision["first_publication_failure_reason"] == "pass1_missing_action_id"
    assert decision["final_publication_status"] == "published"
    assert decision["final_worker_response_kind"] == "action_request"
    assert rows[0]["turn_index"] == 0
    assert rows[0]["turn_role"] == "initial"
    assert rows[0]["publication_support_context_present"] is False
    assert rows[1]["turn_index"] == 1
    assert rows[1]["turn_role"] == "publication_support"
    assert rows[1]["publication_support_context_present"] is True
    assert final_row == rows[1]["row"]
    assert support_context["fields"]["previous_response_sha256"] == "sha256:pass1"
    assert worker_action["input"] == {"value": 3.0}
    assert "lm8i_publication_support_context" in json.dumps(
        captured_payloads[1]["context"]["knowledge"],
        sort_keys=True,
    )
```

- [ ] **Step 3: Write non-eligible/no-support tests**

Add:

```python
@pytest.mark.parametrize(
    "publication",
    [
        _pass1_missing_publication('{"kind":"action_request","action_id":""}'),
        _pass1_missing_publication('{"kind":"action_request","action_id":"wrong"}'),
        _pass1_missing_publication('{"kind":"action_request","input":{"value":3.0}}'),
        _pass1_missing_publication('{"kind":"action_reques'),
    ],
)
def test_run_probe_does_not_support_non_exact_pass1_rows(tmp_path, publication):
    executor = FakeToolExecutor(_fixture_responses_for_success())
    calls = []

    def fake_publication_runner(payload, **_kwargs):
        calls.append(payload)
        return publication

    run_dir = PROBE._run_probe(
        model="gemma4:12b-it-qat",
        endpoint="http://localhost:11434/api/chat",
        temperature=0,
        timeout_s=120,
        excerpt_chars=1200,
        run_root=tmp_path,
        canonical_evidence=True,
        tool_executor=executor,
        publication_runner=fake_publication_runner,
    )

    decision = json.loads((run_dir / "decision.json").read_text(encoding="utf-8"))
    rows = json.loads((run_dir / "worker_publication_rows.json").read_text(encoding="utf-8"))
    final_row = json.loads((run_dir / "worker_publication_row.json").read_text(encoding="utf-8"))

    assert len(calls) == 1
    assert decision["decision"] == "publication_failed"
    assert decision["publication_support_attempted"] is False
    assert decision["publication_support_count"] == 0
    assert decision["support_eligible"] is False
    assert decision["support_not_attempted_reason"] in {
        "pass1_excerpt_not_exact_skeletal_json",
        "first_publication_not_exact_skeletal_missing_action_id",
    }
    assert len(rows) == 1
    assert rows[0]["turn_role"] == "initial"
    assert final_row == rows[0]["row"]
    assert not (run_dir / "publication_support_context.json").exists()
    assert not (run_dir / "worker_action.json").exists()
```

- [ ] **Step 4: Write support-repeat-failure and support-non-action tests**

Add:

```python
def test_run_probe_support_repeat_missing_action_id_remains_publication_failed(tmp_path):
    executor = FakeToolExecutor(_fixture_responses_for_success())
    publications = [_pass1_missing_publication(), _pass1_missing_publication()]

    run_dir = PROBE._run_probe(
        model="gemma4:12b-it-qat",
        endpoint="http://localhost:11434/api/chat",
        temperature=0,
        timeout_s=120,
        excerpt_chars=1200,
        run_root=tmp_path,
        canonical_evidence=True,
        tool_executor=executor,
        publication_runner=lambda *_args, **_kwargs: publications.pop(0),
    )

    decision = json.loads((run_dir / "decision.json").read_text(encoding="utf-8"))
    rows = json.loads((run_dir / "worker_publication_rows.json").read_text(encoding="utf-8"))

    assert decision["decision"] == "publication_failed"
    assert decision["reason"] == "pass1_decision_invalid:pass1_missing_action_id"
    assert decision["publication_support_attempted"] is True
    assert decision["publication_support_count"] == 1
    assert len(rows) == 2
    assert not (run_dir / "worker_action.json").exists()


def test_run_probe_support_non_action_maps_to_worker_declined(tmp_path):
    executor = FakeToolExecutor(_fixture_responses_for_success())
    publications = [
        _pass1_missing_publication(),
        FakePublication(
            row={
                "status": "published",
                "pass2_response_kind": "observation",
                "observation_action_intent_anomaly": False,
            },
            response_payload={
                "schema": "rook.local_worker_turn_response:v1",
                "kind": "observation",
                "message": "I will not act.",
                "data": None,
            },
        ),
    ]

    run_dir = PROBE._run_probe(
        model="gemma4:12b-it-qat",
        endpoint="http://localhost:11434/api/chat",
        temperature=0,
        timeout_s=120,
        excerpt_chars=1200,
        run_root=tmp_path,
        canonical_evidence=True,
        tool_executor=executor,
        publication_runner=lambda *_args, **_kwargs: publications.pop(0),
    )

    decision = json.loads((run_dir / "decision.json").read_text(encoding="utf-8"))

    assert decision["decision"] == "worker_declined"
    assert decision["reason"] == "worker_observed"
    assert decision["publication_support_attempted"] is True
    assert decision["final_worker_response_kind"] == "observation"
    assert not (run_dir / "worker_action.json").exists()
```

- [ ] **Step 5: Implement row annotation and support metadata helpers**

Add:

```python
def _annotate_publication_row(
    row: Mapping[str, Any],
    *,
    turn_index: int,
    turn_role: str,
    publication_support_context_present: bool,
) -> dict[str, Any]:
    if turn_role not in {"initial", "publication_support"}:
        raise ValueError("unsupported_publication_turn_role")
    return {
        "turn_index": turn_index,
        "turn_role": turn_role,
        "publication_support_context_present": publication_support_context_present,
        "row": dict(row),
    }


def _publication_safety_failure(
    publication: Any,
    *,
    component_guids: Sequence[str],
) -> str | None:
    if _hidden_marker_leaks(publication.row) or _hidden_marker_leaks(
        publication.response_payload
    ):
        return "worker_publication_hidden_answer_leak"
    for component_guid in component_guids:
        if _raw_component_guid_leaks(
            publication.row, component_guid
        ) or _raw_component_guid_leaks(publication.response_payload, component_guid):
            return "worker_publication_guid_leak"
    return None


def _redacted_publication_row(
    publication: Any,
    *,
    redaction_reason: str,
) -> dict[str, Any]:
    """Hash-only publication row summary for unsafe helper rows/payloads."""
    ...


def _support_metadata(
    *,
    attempted: bool,
    count: int,
    eligibility: Mapping[str, Any],
    first_row: Mapping[str, Any],
    final_row: Mapping[str, Any],
    final_payload: Mapping[str, Any] | None,
) -> dict[str, Any]:
    return {
        "publication_support_attempted": attempted,
        "publication_support_count": count,
        "support_eligible": bool(eligibility.get("support_eligible")),
        "support_not_attempted_reason": eligibility.get("support_not_attempted_reason"),
        "first_publication_status": first_row.get("status"),
        "first_publication_failure_reason": first_row.get("failure_reason"),
        "final_publication_status": final_row.get("status"),
        "final_publication_failure_reason": final_row.get("failure_reason"),
        "final_worker_response_kind": (
            final_payload.get("kind") if isinstance(final_payload, Mapping) else None
        ),
    }
```

- [ ] **Step 6: Update `_run_probe` publication section**

Replace the single publication call/write/classify section with this control flow:

```python
first_publication = publisher(
    request_payload,
    model=model,
    endpoint=endpoint,
    temperature=temperature,
    timeout_s=timeout_s,
    excerpt_chars=excerpt_chars,
)
component_guids = (
    editable_component_guid,
    factor_component_guid,
    offset_component_guid,
    multiplication_component_guid,
    addition_component_guid,
)
safety_failure = _publication_safety_failure(
    first_publication,
    component_guids=component_guids,
)
if safety_failure is not None:
    # Write redacted/hash-only row artifacts; never persist the unsafe helper row.
    redacted_row = _redacted_publication_row(
        first_publication,
        redaction_reason=safety_failure,
    )
    annotated_row = _annotate_publication_row(
        redacted_row,
        turn_index=0,
        turn_role="initial",
        publication_support_context_present=False,
    )
    _write_json_value(run_dir / "worker_publication_rows.json", [annotated_row])
    _write_json(run_dir / "worker_publication_row.json", redacted_row)
    _write_json(
        run_dir / "decision.json",
        _decision_record(
            decision="publication_failed",
            reason=safety_failure,
            phase="worker_publication",
            canonical_evidence=canonical_evidence,
            scalar_runtime_ready=True,
            live_fixture_created=True,
            worker_publication_ran=True,
            component_guid=editable_component_guid,
        ),
    )
    return run_dir

publication_rows = [
    _annotate_publication_row(
        first_publication.row,
        turn_index=0,
        turn_role="initial",
        publication_support_context_present=False,
    )
]
eligibility = _publication_support_eligibility(first_publication.row)
support_attempted = False
support_count = 0
final_publication = first_publication

if eligibility["support_eligible"] is True:
    support_context = _publication_support_context(
        first_publication.row,
        excerpt_chars=excerpt_chars,
    )
    _write_json(run_dir / "publication_support_context.json", support_context)
    support_payload = _build_local_turn_payload(
        graph=graph,
        packet=runtime["packet"],
        worker_visible=runtime["worker_visible"],
        publication_support_context=support_context,
    )
    support_attempted = True
    support_count = 1
    final_publication = publisher(
        support_payload,
        model=model,
        endpoint=endpoint,
        temperature=temperature,
        timeout_s=timeout_s,
        excerpt_chars=excerpt_chars,
    )
    safety_failure = _publication_safety_failure(
        final_publication,
        component_guids=component_guids,
    )
    if safety_failure is not None:
        # Replace the support row with a redacted/hash-only summary before writing.
        redacted_row = _redacted_publication_row(
            final_publication,
            redaction_reason=safety_failure,
        )
        publication_rows[-1] = _annotate_publication_row(
            redacted_row,
            turn_index=1,
            turn_role="publication_support",
            publication_support_context_present=True,
        )
        _write_json_value(run_dir / "worker_publication_rows.json", publication_rows)
        _write_json(run_dir / "worker_publication_row.json", redacted_row)
        _write_json(
            run_dir / "decision.json",
            _decision_record(
                decision="publication_failed",
                reason=safety_failure,
                phase="worker_publication",
                canonical_evidence=canonical_evidence,
                scalar_runtime_ready=True,
                live_fixture_created=True,
                worker_publication_ran=True,
                component_guid=editable_component_guid,
                extra=_support_metadata(
                    attempted=support_attempted,
                    count=support_count,
                    eligibility=eligibility,
                    first_row=first_publication.row,
                    final_row=final_publication.row,
                    final_payload=final_publication.response_payload,
                ),
            ),
        )
        return run_dir
    publication_rows.append(
        _annotate_publication_row(
            final_publication.row,
            turn_index=1,
            turn_role="publication_support",
            publication_support_context_present=True,
        )
    )

_write_json_value(run_dir / "worker_publication_rows.json", publication_rows)
_write_json(run_dir / "worker_publication_row.json", final_publication.row)
support_extra = _support_metadata(
    attempted=support_attempted,
    count=support_count,
    eligibility=eligibility,
    first_row=first_publication.row,
    final_row=final_publication.row,
    final_payload=final_publication.response_payload,
)
```

Then use `final_publication.row` and `final_publication.response_payload` for `_decision_from_publication(...)`, `_published_action_payload_failure_reason(...)`, `worker_action.json`, applier, live dispatch, and verifier. When writing any post-publication decision, merge `support_extra` into the existing `extra` dict.

Do not write `worker_action.json` until the final publication row is valid,
`_published_action_payload_failure_reason(...)` returns `None`, and the scalar
action applier accepts the worker input.

Publication hidden-marker/raw-GUID safety overrides raw row artifact compatibility.
When a helper row or response payload fails the publication safety gate, write
only redacted/hash-only publication row summaries to `worker_publication_rows.json`
and `worker_publication_row.json`; do not persist the unsafe helper row or
response payload verbatim.

- [ ] **Step 7: Run Task 4 tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_lm8i_affine_publication_shape_support_probe.py -q
```

Expected: support orchestration tests pass.

- [ ] **Step 8: Commit Task 4**

```powershell
git add scripts\lm8i_affine_publication_shape_support_probe.py mcp_server\tests\test_lm8i_affine_publication_shape_support_probe.py
git commit -m "feat(lm8i): orchestrate publication support turn"
```

---

### Task 5: Authority, Drift, And Final Verification Guards

**Files:**
- Modify: `scripts/lm8i_affine_publication_shape_support_probe.py`
- Modify: `mcp_server/tests/test_lm8i_affine_publication_shape_support_probe.py`

**Interfaces:**
- Consumes: completed LM8I script.
- Produces: final deterministic guard suite and implementation-readiness proof.

- [ ] **Step 1: Add no raw transcript artifact test**

Add:

```python
def test_run_probe_does_not_write_raw_pass1_transcript_artifact(tmp_path):
    executor = FakeToolExecutor(_fixture_responses_for_success())
    publications = [_pass1_missing_publication(), _published_action(3.0)]

    run_dir = PROBE._run_probe(
        model="gemma4:12b-it-qat",
        endpoint="http://localhost:11434/api/chat",
        temperature=0,
        timeout_s=120,
        excerpt_chars=1200,
        run_root=tmp_path,
        canonical_evidence=True,
        tool_executor=executor,
        publication_runner=lambda *_args, **_kwargs: publications.pop(0),
    )

    artifact_names = {path.name for path in run_dir.iterdir()}
    forbidden_names = {
        "pass1_raw.txt",
        "pass1_provider_output.txt",
        "worker_pass1_transcript.txt",
        "raw_provider_output.txt",
    }
    assert artifact_names.isdisjoint(forbidden_names)
    assert all("transcript" not in name for name in artifact_names)
    rows = json.loads((run_dir / "worker_publication_rows.json").read_text(encoding="utf-8"))
    assert rows[0]["row"]["pass1_content_excerpt"] == '{"kind": "action_request"}'
    assert rows[0]["row"]["pass1_content_sha256"] == "sha256:pass1"
```

- [ ] **Step 2: Add support/pre-publication hidden value test**

Add:

```python
def test_run_probe_support_and_prepublication_artifacts_do_not_contain_hidden_value(tmp_path):
    executor = FakeToolExecutor(_fixture_responses_for_success())
    publications = [_pass1_missing_publication(), _published_action(3.0)]

    run_dir = PROBE._run_probe(
        model="gemma4:12b-it-qat",
        endpoint="http://localhost:11434/api/chat",
        temperature=0,
        timeout_s=120,
        excerpt_chars=1200,
        run_root=tmp_path,
        canonical_evidence=True,
        tool_executor=executor,
        publication_runner=lambda *_args, **_kwargs: publications.pop(0),
    )

    forbidden_pre_publication = [
        "scalar_sources.json",
        "acceptance_criteria_packet.json",
        "worker_visible_acceptance_criteria.json",
        "worker_request_payload.json",
        "publication_support_context.json",
        "worker_publication_rows.json",
    ]
    for filename in forbidden_pre_publication:
        rendered = (run_dir / filename).read_text(encoding="utf-8")
        assert "3.0" not in rendered

    allowed_post_publication = [
        "worker_action.json",
        "live_set_value_summary.json",
        "decision.json",
    ]
    assert any(
        "3.0" in (run_dir / filename).read_text(encoding="utf-8")
        for filename in allowed_post_publication
    )
```

- [ ] **Step 3: Add no autofill regression**

Add:

```python
def test_lm8i_never_autofills_missing_action_id(tmp_path):
    executor = FakeToolExecutor(_fixture_responses_for_success())
    publications = [_pass1_missing_publication(), _pass1_missing_publication()]

    run_dir = PROBE._run_probe(
        model="gemma4:12b-it-qat",
        endpoint="http://localhost:11434/api/chat",
        temperature=0,
        timeout_s=120,
        excerpt_chars=1200,
        run_root=tmp_path,
        canonical_evidence=True,
        tool_executor=executor,
        publication_runner=lambda *_args, **_kwargs: publications.pop(0),
    )

    decision = json.loads((run_dir / "decision.json").read_text(encoding="utf-8"))
    rows = json.loads((run_dir / "worker_publication_rows.json").read_text(encoding="utf-8"))

    assert decision["decision"] == "publication_failed"
    assert decision["reason"] == "pass1_decision_invalid:pass1_missing_action_id"
    assert all(row["row"].get("pass1_action_id") in {None, ""} for row in rows)
    assert not (run_dir / "worker_action.json").exists()
    assert not (run_dir / "live_set_value_summary.json").exists()
```

- [ ] **Step 4: Add raw source/drift guard**

Add:

```python
def test_lm8i_source_does_not_import_lm8h_lm8g_repair_planner_retry_or_gh_edit_paths():
    source = inspect.getsource(PROBE)
    forbidden_import_or_call_fragments = (
        "lm8h_affine_scalar_depth_probe",
        "lm8g_scalar_transform_repeatability_probe",
        "lm6a_live_worker_splice_probe",
        "lm7e_model_authored_live_splice_probe",
        "planner_worker_contract_request",
        "workflow_validate",
        "--retry-clean-observation",
        '"gh_edit"',
        "'gh_edit'",
        "gh_update_script",
    )
    for fragment in forbidden_import_or_call_fragments:
        assert fragment not in source


def test_lm8i_source_does_not_contain_hidden_worker_value_literal():
    source = inspect.getsource(PROBE)
    assert "3.0" not in source
    assert "EXPECTED_WORKER_VALUE" not in source
    assert "set editable value to 3.0" not in source
    assert "use 3.0" not in source


def test_lm8i_does_not_modify_or_import_shared_publication_helper_for_support_policy():
    source = inspect.getsource(PROBE)
    assert "run_two_pass_worker_publication" in source
    assert "pass1_content_excerpt" in source
    assert "pass1_content_sha256" in source
    helper_source = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "lm_worker_two_pass_publication.py"
    ).read_text(encoding="utf-8")
    assert "lm8i_publication_support_context" not in helper_source
```

The raw source guard may include policy marker strings for hidden marker scanning. Do not ban policy strings that are needed for the guard itself.

- [ ] **Step 5: Run focused and nearby tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm8i_affine_publication_shape_support_probe.py `
  mcp_server\tests\test_lm8h_affine_scalar_depth_probe.py `
  mcp_server\tests\test_lm_worker_two_pass_publication.py `
  -q
```

Expected: all selected tests pass. LM8H must remain green.

- [ ] **Step 6: Compile scripts and tests**

Run:

```powershell
py -3.10 -m py_compile `
  scripts\lm8i_affine_publication_shape_support_probe.py `
  mcp_server\tests\test_lm8i_affine_publication_shape_support_probe.py
```

Expected: no output and exit code 0.

- [ ] **Step 7: Verify diff hygiene**

Run:

```powershell
git diff --check main..HEAD
git diff --name-only main..HEAD
```

Expected changed files:

```text
docs/superpowers/specs/2026-07-09-lm8i-affine-publication-shape-support-design.md
docs/superpowers/plans/2026-07-09-lm8i-affine-publication-shape-support.md
scripts/lm8i_affine_publication_shape_support_probe.py
mcp_server/tests/test_lm8i_affine_publication_shape_support_probe.py
```

No `probe_runs/` artifacts, telemetry files, or unrelated docs should be staged.

- [ ] **Step 8: Commit Task 5**

```powershell
git add scripts\lm8i_affine_publication_shape_support_probe.py mcp_server\tests\test_lm8i_affine_publication_shape_support_probe.py
git commit -m "test(lm8i): guard publication support boundaries"
```

---

## Final Review Checklist

- [ ] `scripts/lm_worker_two_pass_publication.py` is unchanged.
- [ ] `scripts/lm8h_affine_scalar_depth_probe.py` is unchanged.
- [ ] LM8I support eligibility uses only `pass1_content_excerpt` and `pass1_content_sha256`.
- [ ] Truncated excerpts are not eligible.
- [ ] Empty-string `action_id` is not eligible.
- [ ] Wrong `action_id` is not eligible.
- [ ] Input-only skeletal-ish objects are not eligible.
- [ ] `worker_publication_rows.json` is an ordered list.
- [ ] `worker_publication_row.json` is the final compatibility row.
- [ ] `publication_support_context.json` is written only when support is attempted.
- [ ] No raw pass-1 transcript artifact is written.
- [ ] No pre-publication/support/request artifact contains `3.0`.
- [ ] No action id autofill exists.
- [ ] No live LM8I run was performed in the implementation PR.

## Post-Merge Runbook

After implementation merge and sync to `main`, run exactly one canonical LM8I attempt with Rhino and Grasshopper open:

```powershell
cd C:\UDEV\Rook
.\mcp_server\.venv\Scripts\python.exe scripts\lm8i_affine_publication_shape_support_probe.py
```

Do not replace the attempt. If support is not exercised, if support fails, or if verifier fails after a valid final action, the receipted terminal outcome is the evidence.
