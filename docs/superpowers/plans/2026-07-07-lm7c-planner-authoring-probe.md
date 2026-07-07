# LM7C Planner Authoring Probe Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the deterministic LM7C offline Planner authoring probe: prompt/menu/brief artifacts plus strict model-output parsing, `workflow_validate` scoring, intent-decision classification, row/summary artifacts, and fake-provider tests only.

**Architecture:** Add a new sibling offline probe script. The script owns the LM7C prompt artifacts, provider boundary, strict parser, intent classifier, row builder, and run artifacts. It consumes the existing LM7A `PlannerWorkerContractRequest:v1` surface through `validate_planner_worker_contract_request(...)` and does not touch live Rhino/GH, worker publication, LM7B, LM6, or request-schema behavior.

**Tech Stack:** Python 3.10, pytest, standard-library JSON/subprocess/pathlib/hashlib, existing `rook.agent.workflow_validate` and `rook.agent.planner_worker_contract_request` constants.

---

## File Structure

Create:

- `scripts/lm7c_planner_authoring_probe.py`
  - Offline probe script.
  - Owns LM7C prompt artifacts, strict parser, fake/live-provider boundary, `workflow_validate` row scoring, intent classifier, summary counts, and run directory writing.

- `mcp_server/tests/test_lm7c_planner_authoring_probe.py`
  - Deterministic fake-provider tests.
  - Must not require Rhino, Grasshopper, Ollama, OpenAI, Anthropic, provider credentials, worker publication, or a live model.

Create:

- `docs/superpowers/plans/2026-07-07-lm7c-planner-authoring-probe.md`
  - This implementation plan.

Already landed:

- `docs/superpowers/specs/2026-07-07-lm7c-planner-authoring-probe-design.md`

Do not modify:

- `mcp_server/src/rook/agent/planner_worker_contract_request.py`
- `mcp_server/src/rook/agent/workflow_validate.py`
- `scripts/lm7b_request_driven_live_splice_probe.py`
- `scripts/lm6a_live_worker_splice_probe.py`
- `scripts/lm_worker_two_pass_publication.py`
- `mcp_server/src/rook/agent/plan_graph_worker_action_apply.py`

No live evidence artifacts are committed. `probe_runs/` remains ignored.

---

## Task 1: Script Skeleton, Constants, CLI, Provider Boundary

**Files:**

- Create: `scripts/lm7c_planner_authoring_probe.py`
- Create: `mcp_server/tests/test_lm7c_planner_authoring_probe.py`

- [ ] **Step 1: Write failing script-load and CLI tests**

Create `mcp_server/tests/test_lm7c_planner_authoring_probe.py` with the same dynamic script-loading pattern used by LM7B:

```python
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from rook.agent.planner_worker_contract_request import (
    DESIRED_OUTPUT_VALUE_INTENT_ID,
    LM7A_TEMPLATE_ID,
    MISSING_DESIRED_OUTPUT_ROUTE_ID,
    PLANNER_INTENT_SOURCE_PATH,
    PLANNER_WORKER_CONTRACT_REQUEST_SCHEMA,
)


def _script_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "lm7c_planner_authoring_probe.py"
    )


def _load_script():
    path = _script_path()
    spec = importlib.util.spec_from_file_location(
        "lm7c_planner_authoring_probe",
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
def test_cli_defaults_are_canonical_probe_defaults() -> None:
    args = PROBE._args([])

    assert args.attempts == 5
    assert args.provider == "ceiling-provider"
    assert args.model == "ceiling-planner-model"
    assert args.temperature == 0
    assert args.run_dir == "probe_runs"
    assert args.output_excerpt_chars == 1200
    assert args.provider_timeout_s == 120
    assert args.provider_command is None
    assert args.canonical_evidence is False


def test_cli_rejects_live_and_worker_options() -> None:
    for option in (
        "--phase",
        "--retry-clean-observation",
        "--request-json",
        "--endpoint",
        "--ollama-url",
    ):
        with pytest.raises(SystemExit):
            PROBE._args([option, "x"])
```

Pin these constants in the script:

```python
PROBE_SCHEMA = "rook.lm7c_planner_authoring_probe:v1"
PLANNER_AUTHORING_PROMPT_VERSION = "lm7c.planner_authoring_prompt:v1"
TEMPLATE_MENU_VERSION = "lm7c.template_menu:v1"
INTENT_COMPLETE_BRIEF_VERSION = "lm7c.intent_complete_brief:v1"
INTENT_INCOMPLETE_BRIEF_VERSION = "lm7c.intent_incomplete_brief:v1"
SCENARIOS = ("intent_complete", "intent_incomplete")

PARSE_PARSED = "parsed"
PARSE_FAILED = "parse_failed"

VALIDATION_VALID = "workflow_validate_valid"
VALIDATION_FAILED = "workflow_validate_failed"
VALIDATION_NOT_EVALUATED = "not_evaluated"

INTENT_CORRECT = "correct_declared"
INTENT_OVER_DECLARED = "over_declared"
INTENT_INVENTED = "invented"
INTENT_NOT_CLASSIFIABLE = "not_classifiable"
```

Provider stance:

- The implementation must expose a pure in-process runner that accepts an injected provider callable for tests.
- The CLI may support a provider-command seam for future post-merge canonical runs, but tests must not call a live provider.
- `provider` is the comparison-key provider label, not the transport adapter name.
- If the CLI is run without `--provider-command`, fail before creating a canonical evidence run with a clear `provider_command_required` message.
- Provider unavailability is not evidence.

Suggested provider call shape:

```python
def _run_probe(
    *,
    run_root: Path,
    provider: str,
    model: str,
    temperature: float,
    attempts: int,
    canonical_evidence: bool,
    output_excerpt_chars: int,
    call_provider: Callable[[Mapping[str, Any]], str],
) -> Path:
    ...
```

If implementing `--provider-command`, send one JSON call payload to the command through stdin and read stdout as the raw model output. Do not import provider SDKs in LM7C v1.

- [ ] **Step 2: Implement the minimal script skeleton**

Use the existing script path bootstrap style:

```python
_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent
_MCP_SRC = _REPO_ROOT / "mcp_server" / "src"
if str(_MCP_SRC) not in sys.path:
    sys.path.insert(0, str(_MCP_SRC))
```

Import only:

```python
from rook.agent.planner_worker_contract_request import (
    DESIRED_OUTPUT_VALUE_INTENT_ID,
    LM7A_TEMPLATE_ID,
    MISSING_DESIRED_OUTPUT_ROUTE_ID,
    PLANNER_INTENT_SOURCE_PATH,
    PLANNER_WORKER_CONTRACT_REQUEST_SCHEMA,
)
from rook.agent.workflow_validate import validate_planner_worker_contract_request
```

Do not import LM7B, LM6A, worker publication helpers, worker-action applier, live dispatch, Rhino/GH server tools, or provider SDKs.

---

## Task 2: Prompt/Menu/Brief Builders and Artifact Writers

**Files:**

- Modify: `scripts/lm7c_planner_authoring_probe.py`
- Modify: `mcp_server/tests/test_lm7c_planner_authoring_probe.py`

- [ ] **Step 1: Write failing tests for prompt artifacts**

Tests:

```python
def test_template_menu_is_versioned_and_single_template() -> None:
    menu = PROBE._template_menu()

    assert menu["version"] == PROBE.TEMPLATE_MENU_VERSION
    assert [item["template_id"] for item in menu["templates"]] == [LM7A_TEMPLATE_ID]
    rendered = json.dumps(menu, sort_keys=True)
    assert PLANNER_WORKER_CONTRACT_REQUEST_SCHEMA in rendered
    assert "repair_same_component_from_create_error" in rendered


def test_briefs_are_paired_and_control_only_intent_availability() -> None:
    complete = PROBE._scenario_brief("intent_complete")
    incomplete = PROBE._scenario_brief("intent_incomplete")

    assert complete["version"] == PROBE.INTENT_COMPLETE_BRIEF_VERSION
    assert incomplete["version"] == PROBE.INTENT_INCOMPLETE_BRIEF_VERSION
    assert "7.5" in complete["text"]
    assert "7.5" not in incomplete["text"]
    assert 'pins_out: ["A:double"]' in complete["text"]
    assert 'pins_out: ["A:double"]' in incomplete["text"]


def test_prompt_contains_rules_but_no_full_request_exemplar() -> None:
    prompt = PROBE._planner_authoring_prompt()

    assert PROBE.PLANNER_AUTHORING_PROMPT_VERSION in prompt
    assert PLANNER_WORKER_CONTRACT_REQUEST_SCHEMA in prompt
    assert "exactly one JSON object" in prompt
    assert "no markdown" in prompt.lower()
    assert '"template_id": "repair_same_component_from_create_error"' not in prompt
    assert '"initial_params": {' not in prompt
    assert '"add_unresolved_intent_routes": [' not in prompt
    assert "Output A must be assigned" not in prompt
    assert "A = " not in prompt
```

Hidden-answer/protocol-drift prompt guard:

```python
def test_prompt_artifacts_do_not_contain_invention_or_hidden_answer_markers() -> None:
    artifacts = {
        "prompt": PROBE._planner_authoring_prompt(),
        "template_menu": json.dumps(PROBE._template_menu(), sort_keys=True),
        "intent_complete": PROBE._scenario_brief("intent_complete")["text"],
        "intent_incomplete": PROBE._scenario_brief("intent_incomplete")["text"],
    }

    forbidden = (
        "PROBE_REPAIR_CODE",
        "A = 42.0",
        "42.0",
        "A = 0.0",
        "A = 1.0",
        "use a default",
        "set A to",
        "BindStepSpec.base_params",
        "repair_same_component.bind.base_params",
    )
    for name, artifact in artifacts.items():
        for marker in forbidden:
            assert marker not in artifact, (name, marker)

    assert "7.5" in artifacts["intent_complete"]
    assert "7.5" not in artifacts["prompt"]
    assert "7.5" not in artifacts["template_menu"]
    assert "7.5" not in artifacts["intent_incomplete"]
```

- [ ] **Step 2: Implement builders**

Implement:

```python
def _planner_authoring_prompt() -> str: ...
def _template_menu() -> dict[str, Any]: ...
def _scenario_brief(scenario: str) -> dict[str, str]: ...
def _prompt_call_payload(*, scenario: str, attempt_index: int, provider: str, model: str, temperature: float) -> dict[str, Any]: ...
```

Prompt contents must describe:

- output exactly one JSON object
- schema must be `rook.planner_worker_contract_request:v1`
- allowed top-level fields: `schema`, `template_id`, `initial_params`, `routing_delta`, `intent_slots`
- template menu contains only `repair_same_component_from_create_error`
- `initial_params.create_script.pins_out` must be `["A:double"]`
- `intent_complete`: explicit `7.5` means `desired_output_value` is not missing, but v1 has no legal field for that value
- `intent_incomplete`: absence of desired output value should be represented with the exact unresolved slot and exact unresolved-intent route
- no acceptance-criteria prose
- no repair code
- no hidden bind params

Do not include a complete valid request exemplar or a complete unresolved-intent exemplar.

- [ ] **Step 3: Implement artifact writing**

Implement:

```python
def _write_prompt_artifacts(run_dir: Path) -> None:
    ...
```

It writes:

```text
prompts/planner_authoring_prompt.txt
prompts/template_menu.json
prompts/intent_complete_brief.txt
prompts/intent_incomplete_brief.txt
```

Use sorted keys and compact/stable JSON where applicable.

---

## Task 3: Strict JSON Parser

**Files:**

- Modify: `scripts/lm7c_planner_authoring_probe.py`
- Modify: `mcp_server/tests/test_lm7c_planner_authoring_probe.py`

- [ ] **Step 1: Write strict parser tests**

Add a minimal valid request helper in tests:

```python
def _minimal_complete_request() -> dict[str, object]:
    return {
        "schema": PLANNER_WORKER_CONTRACT_REQUEST_SCHEMA,
        "template_id": LM7A_TEMPLATE_ID,
        "initial_params": {
            "create_script": {
                "pins_out": ["A:double"],
            },
        },
        "routing_delta": {
            "enable_routes": [],
            "disable_routes": [],
            "set_required": {},
            "add_unresolved_intent_routes": [],
        },
        "intent_slots": [],
    }
```

Tests:

```python
def test_parse_accepts_exact_json_object() -> None:
    parsed = PROBE._strict_parse_model_output(json.dumps(_minimal_complete_request()))

    assert parsed.parse_status == "parsed"
    assert parsed.payload == _minimal_complete_request()
    assert parsed.failure_reason is None


@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        ("```json\n{}\n```", "json_decode_failed"),
        ("Here is the request: {}", "json_decode_failed"),
        ("[]", "json_not_object"),
        ("{} {}", "json_decode_failed"),
        ("{", "json_decode_failed"),
    ],
)
def test_parse_rejects_non_strict_output(raw: str, reason: str) -> None:
    parsed = PROBE._strict_parse_model_output(raw)

    assert parsed.parse_status == "parse_failed"
    assert parsed.payload is None
    assert parsed.failure_reason == reason


@pytest.mark.parametrize("payload", [{}, {"schema": "wrong:v1"}])
def test_parse_rejects_missing_or_wrong_schema(payload: dict[str, object]) -> None:
    parsed = PROBE._strict_parse_model_output(json.dumps(payload))

    assert parsed.parse_status == "parse_failed"
    assert parsed.payload is None
    assert parsed.failure_reason == "invalid_schema"
```

- [ ] **Step 2: Implement parser result**

Use a frozen dataclass:

```python
@dataclass(frozen=True)
class ParseResult:
    parse_status: str
    payload: dict[str, Any] | None
    failure_reason: str | None
```

Implement:

```python
def _strict_parse_model_output(raw_output: str) -> ParseResult:
    ...
```

Rules:

- `json.loads(raw_output.strip())`
- Any decode error -> `parse_failed`, `json_decode_failed`
- Non-dict JSON -> `parse_failed`, `json_not_object`
- Missing/wrong top-level schema -> `parse_failed`, `invalid_schema`
- Otherwise `parsed`
- No markdown extraction
- No schema repair
- No coercion

---

## Task 4: Intent Decision Classifier

**Files:**

- Modify: `scripts/lm7c_planner_authoring_probe.py`
- Modify: `mcp_server/tests/test_lm7c_planner_authoring_probe.py`

- [ ] **Step 1: Write classifier tests for canonical exact identities**

Canonical unresolved identity:

```python
def _exact_unresolved_slot() -> dict[str, object]:
    return {
        "intent_id": DESIRED_OUTPUT_VALUE_INTENT_ID,
        "status": "unresolved",
        "source_path": PLANNER_INTENT_SOURCE_PATH,
        "description": "Desired output value was not provided.",
    }


def _exact_unresolved_route() -> dict[str, object]:
    return {
        "route_id": MISSING_DESIRED_OUTPUT_ROUTE_ID,
        "source_class": "planner_user_intent",
        "source_path": PLANNER_INTENT_SOURCE_PATH,
        "purpose": "unresolved_intent",
        "required": False,
    }
```

Tests:

```python
def test_intent_complete_correct_when_unresolved_slot_and_route_absent() -> None:
    request = _minimal_complete_request()

    result = PROBE._classify_intent_decision("intent_complete", request)

    assert result.intent_decision == "correct_declared"
    assert result.failure_reason is None


def test_intent_complete_over_declared_when_missing_intent_is_declared() -> None:
    request = _minimal_complete_request()
    request["intent_slots"] = [_exact_unresolved_slot()]
    request["routing_delta"]["add_unresolved_intent_routes"] = [_exact_unresolved_route()]

    result = PROBE._classify_intent_decision("intent_complete", request)

    assert result.intent_decision == "over_declared"
    assert result.failure_reason == "desired_output_value_over_declared"


@pytest.mark.parametrize("marker", ["7.5", "A = 0.0", "A = 1.0", "use a default"])
def test_intent_complete_invented_when_request_copies_or_adds_concrete_semantics(marker: str) -> None:
    request = _minimal_complete_request()
    request["extra_semantic_field"] = marker

    result = PROBE._classify_intent_decision("intent_complete", request)

    assert result.intent_decision == "invented"
    assert result.failure_reason == "invented_concrete_intent"


def test_intent_incomplete_correct_when_exact_slot_and_route_present() -> None:
    request = _minimal_complete_request()
    request["intent_slots"] = [_exact_unresolved_slot()]
    request["routing_delta"]["add_unresolved_intent_routes"] = [_exact_unresolved_route()]

    result = PROBE._classify_intent_decision("intent_incomplete", request)

    assert result.intent_decision == "correct_declared"
    assert result.failure_reason is None


def test_intent_incomplete_over_declared_when_extra_unresolved_slot_is_added() -> None:
    request = _minimal_complete_request()
    request["intent_slots"] = [
        _exact_unresolved_slot(),
        {
            "intent_id": "desired_material",
            "status": "unresolved",
            "source_path": "planner.intent.desired_material",
            "description": "Material was not provided.",
        },
    ]
    request["routing_delta"]["add_unresolved_intent_routes"] = [_exact_unresolved_route()]

    result = PROBE._classify_intent_decision("intent_incomplete", request)

    assert result.intent_decision == "over_declared"
    assert result.failure_reason == "extra_unresolved_intent"


@pytest.mark.parametrize("marker", ["0.0", "1.0", "7.5", "42.0", "A = 0.0", "set A to"])
def test_intent_incomplete_invented_when_any_concrete_value_is_filled(marker: str) -> None:
    request = _minimal_complete_request()
    request["intent_slots"] = [_exact_unresolved_slot()]
    request["routing_delta"]["add_unresolved_intent_routes"] = [_exact_unresolved_route()]
    request["invented_value"] = marker

    result = PROBE._classify_intent_decision("intent_incomplete", request)

    assert result.intent_decision == "invented"
    assert result.failure_reason == "invented_concrete_intent"
```

Add one explicit missing-slot case because the LM7C enum has no separate `under_declared` value:

```python
def test_intent_incomplete_missing_unresolved_identity_is_not_classifiable_failure() -> None:
    request = _minimal_complete_request()

    result = PROBE._classify_intent_decision("intent_incomplete", request)

    assert result.intent_decision == "not_classifiable"
    assert result.failure_reason == "missing_unresolved_desired_output_value"
```

This keeps the status vocabulary exactly as specified while still producing a deterministic non-success row.

- [ ] **Step 2: Implement classifier result**

Use:

```python
@dataclass(frozen=True)
class IntentDecisionResult:
    intent_decision: str
    failure_reason: str | None
```

Implement:

```python
def _classify_intent_decision(scenario: str, payload: Mapping[str, Any]) -> IntentDecisionResult:
    ...
```

Classifier rules:

- If `scenario` is unknown -> `not_classifiable`, `unknown_scenario`
- If copied/invented concrete semantic markers appear anywhere in the JSON-rendered request -> `invented`, `invented_concrete_intent`
  - Markers include `7.5`, `42.0`, `A = 0.0`, `A = 1.0`, `A = 42.0`, `use a default`, `set A to`, and obvious `repair code` fields.
  - These strings may exist in classifier policy/tests, but must not appear in prompt artifacts except `7.5` in the complete brief.
- Exact unresolved slot match requires:
  - `intent_id == "desired_output_value"`
  - `status == "unresolved"`
  - `source_path == "planner.intent.desired_output_value"`
- Exact unresolved route match requires:
  - `route_id == "missing_desired_output_value"`
  - `source_class == "planner_user_intent"`
  - `source_path == "planner.intent.desired_output_value"`
  - `purpose == "unresolved_intent"`
  - `required is False`
- `intent_complete`
  - exact slot or exact route present -> `over_declared`, `desired_output_value_over_declared`
  - no exact slot/route and no invented marker -> `correct_declared`
- `intent_incomplete`
  - exact slot and exact route present, no additional unresolved slots/routes, no invented marker -> `correct_declared`
  - exact slot/route plus unrelated unresolved intent declarations -> `over_declared`, `extra_unresolved_intent`
  - missing either exact slot or exact route, no invented marker -> `not_classifiable`, `missing_unresolved_desired_output_value`

Do not call `workflow_validate` inside the intent classifier. Intent decision is scored independently from request validity.

---

## Task 5: Row Builder with `workflow_validate` Scoring

**Files:**

- Modify: `scripts/lm7c_planner_authoring_probe.py`
- Modify: `mcp_server/tests/test_lm7c_planner_authoring_probe.py`

- [ ] **Step 1: Write row-builder tests**

Tests:

```python
def test_row_for_valid_complete_request_is_canonical_success() -> None:
    raw = json.dumps(_minimal_complete_request())

    row = PROBE._score_model_output(
        scenario="intent_complete",
        attempt_index=0,
        provider="fake",
        model="fake-planner",
        temperature=0,
        raw_output=raw,
        output_excerpt_chars=120,
    )

    assert row["parse_status"] == "parsed"
    assert row["validation_status"] == "workflow_validate_valid"
    assert row["intent_decision"] == "correct_declared"
    assert row["canonical_success"] is True
    assert row["request_fingerprint"].startswith("sha256:")
    assert row["workflow_validate_report_fingerprint"].startswith("sha256:")
    assert row["failure_reason"] is None


def test_row_for_parse_failure_does_not_call_validate(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_validate(_payload):
        raise AssertionError("validate must not run")

    monkeypatch.setattr(PROBE, "validate_planner_worker_contract_request", fail_validate)

    row = PROBE._score_model_output(
        scenario="intent_complete",
        attempt_index=0,
        provider="fake",
        model="fake-planner",
        temperature=0,
        raw_output="```json\n{}\n```",
        output_excerpt_chars=120,
    )

    assert row["parse_status"] == "parse_failed"
    assert row["validation_status"] == "not_evaluated"
    assert row["intent_decision"] == "not_classifiable"
    assert row["canonical_success"] is False
    assert row["request_fingerprint"] is None
    assert row["workflow_validate_report_fingerprint"] is None
```

Add invalid-but-intent-correct test:

```python
def test_row_separates_validation_failure_from_intent_decision() -> None:
    payload = _minimal_complete_request()
    payload["unexpected"] = "schema extension"

    row = PROBE._score_model_output(
        scenario="intent_complete",
        attempt_index=0,
        provider="fake",
        model="fake-planner",
        temperature=0,
        raw_output=json.dumps(payload),
        output_excerpt_chars=120,
    )

    assert row["parse_status"] == "parsed"
    assert row["validation_status"] == "workflow_validate_failed"
    assert row["intent_decision"] == "correct_declared"
    assert row["canonical_success"] is False
```

Add valid-but-over-declared test:

```python
def test_row_separates_valid_shape_from_over_declaration() -> None:
    payload = _minimal_complete_request()
    payload["intent_slots"] = [_exact_unresolved_slot()]
    payload["routing_delta"]["add_unresolved_intent_routes"] = [_exact_unresolved_route()]

    row = PROBE._score_model_output(
        scenario="intent_complete",
        attempt_index=0,
        provider="fake",
        model="fake-planner",
        temperature=0,
        raw_output=json.dumps(payload),
        output_excerpt_chars=120,
    )

    assert row["validation_status"] == "workflow_validate_valid"
    assert row["intent_decision"] == "over_declared"
    assert row["canonical_success"] is False
```

- [ ] **Step 2: Implement row scoring**

Implement:

```python
def _fingerprint_json(value: Mapping[str, Any] | Sequence[Any] | str) -> str:
    ...

def _score_model_output(
    *,
    scenario: str,
    attempt_index: int,
    provider: str,
    model: str,
    temperature: float,
    raw_output: str,
    output_excerpt_chars: int,
) -> dict[str, Any]:
    ...
```

Rules:

- Always include row fields from the spec:
  - `scenario`
  - `attempt_index`
  - `provider`
  - `model`
  - `temperature`
  - `prompt_version`
  - `template_menu_version`
  - `brief_version`
  - `parse_status`
  - `validation_status`
  - `intent_decision`
  - `canonical_success`
  - `request_fingerprint`
  - `workflow_validate_report_fingerprint`
  - `failure_reason`
  - `output_excerpt`
  - `output_sha256`
- If parse fails:
  - validation not evaluated
  - intent not classifiable
  - no request/report fingerprints
  - `canonical_success = False`
- If parse succeeds:
  - run `validate_planner_worker_contract_request(payload)`
  - `validation_status = workflow_validate_valid` iff report `valid is True`
  - otherwise `workflow_validate_failed`
  - use report `request_fingerprint` and `report_fingerprint` if present
  - run intent classifier independently
- `canonical_success = parsed && workflow_validate_valid && correct_declared`
- `failure_reason` precedence:
  1. parse failure reason
  2. workflow validation failure code summary if invalid and intent is correct
  3. intent classifier failure reason if intent is not correct
  4. `None`

Fingerprinting:

- `output_sha256` is over raw model output bytes.
- `request_fingerprint` is `sha256:` canonical JSON if workflow report does not include one.
- `workflow_validate_report_fingerprint` is the report fingerprint from `workflow_validate`.

---

## Task 6: Probe Runner, Artifacts, Summary Counts

**Files:**

- Modify: `scripts/lm7c_planner_authoring_probe.py`
- Modify: `mcp_server/tests/test_lm7c_planner_authoring_probe.py`

- [ ] **Step 1: Write fake-provider end-to-end artifact tests**

Fake provider:

```python
def test_run_probe_writes_artifacts_and_summary(tmp_path: Path) -> None:
    outputs = {
        ("intent_complete", 0): json.dumps(_minimal_complete_request()),
        ("intent_incomplete", 0): json.dumps(
            {
                **_minimal_complete_request(),
                "intent_slots": [_exact_unresolved_slot()],
                "routing_delta": {
                    **_minimal_complete_request()["routing_delta"],
                    "add_unresolved_intent_routes": [_exact_unresolved_route()],
                },
            }
        ),
    }

    def fake_provider(call_payload):
        return outputs[(call_payload["scenario"], call_payload["attempt_index"])]

    run_dir = PROBE._run_probe(
        run_root=tmp_path,
        provider="fake",
        model="fake-planner",
        temperature=0,
        attempts=1,
        canonical_evidence=False,
        output_excerpt_chars=120,
        call_provider=fake_provider,
    )

    assert run_dir.name.startswith("lm7c-")
    assert (run_dir / "manifest.json").is_file()
    assert (run_dir / "rows.jsonl").is_file()
    assert (run_dir / "summary.json").is_file()
    assert (run_dir / "prompts" / "planner_authoring_prompt.txt").is_file()
    assert (run_dir / "prompts" / "template_menu.json").is_file()
    assert (run_dir / "prompts" / "intent_complete_brief.txt").is_file()
    assert (run_dir / "prompts" / "intent_incomplete_brief.txt").is_file()

    rows = [
        json.loads(line)
        for line in (run_dir / "rows.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len(rows) == 2
    assert all(row["canonical_success"] for row in rows)

    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["scheduled_attempts_per_scenario"] == 1
    assert summary["scenario_counts"]["intent_complete"]["canonical_success_count"] == 1
    assert summary["scenario_counts"]["intent_incomplete"]["canonical_success_count"] == 1
```

Add summary-count test with mixed rows:

```python
def test_summary_counts_parse_validation_intent_and_canonical_success() -> None:
    rows = [
        {
            "scenario": "intent_complete",
            "parse_status": "parsed",
            "validation_status": "workflow_validate_valid",
            "intent_decision": "correct_declared",
            "canonical_success": True,
        },
        {
            "scenario": "intent_complete",
            "parse_status": "parsed",
            "validation_status": "workflow_validate_valid",
            "intent_decision": "over_declared",
            "canonical_success": False,
        },
        {
            "scenario": "intent_incomplete",
            "parse_status": "parse_failed",
            "validation_status": "not_evaluated",
            "intent_decision": "not_classifiable",
            "canonical_success": False,
        },
    ]

    summary = PROBE._summarize_rows(
        rows,
        attempts=5,
        provider="fake",
        model="fake-planner",
        temperature=0,
        canonical_evidence=False,
    )

    assert summary["parse_success_count"] == 2
    assert summary["workflow_validate_valid_count"] == 2
    assert summary["correct_intent_count"] == 1
    assert summary["canonical_success_count"] == 1
    assert summary["over_declared_count"] == 1
    assert summary["invented_count"] == 0
    assert summary["not_classifiable_count"] == 1
```

- [ ] **Step 2: Implement runner and artifacts**

Implement:

```python
def _new_run_dir(root: Path, sha: str | None = None) -> Path: ...
def _git_short_sha() -> str: ...
def _write_json(path: Path, value: Mapping[str, Any]) -> None: ...
def _append_jsonl(path: Path, row: Mapping[str, Any]) -> None: ...
def _summarize_rows(rows: Sequence[Mapping[str, Any]], *, attempts: int, provider: str, model: str, temperature: float, canonical_evidence: bool) -> dict[str, Any]: ...
def _manifest(*, provider: str, model: str, temperature: float, attempts: int, canonical_evidence: bool) -> dict[str, Any]: ...
def _run_probe(...) -> Path: ...
```

Artifact layout:

```text
probe_runs/lm7c-<timestamp>-<sha>/
  manifest.json
  rows.jsonl
  summary.json
  prompts/
    planner_authoring_prompt.txt
    template_menu.json
    intent_complete_brief.txt
    intent_incomplete_brief.txt
```

Loop order:

```text
for scenario in ("intent_complete", "intent_incomplete"):
  for attempt_index in range(attempts):
    build call payload
    raw_output = call_provider(call_payload)
    row = _score_model_output(...)
    append row
```

If provider callable raises:

- record a row with:
  - `parse_status = parse_failed`
  - `validation_status = not_evaluated`
  - `intent_decision = not_classifiable`
  - `canonical_success = False`
  - `failure_reason = provider_error:<ClassName>`
  - bounded output excerpt empty
- continue to the next scheduled attempt

Provider errors are row-level probe outcomes, not code crashes, unless the artifact writer itself fails.

Summary must include:

```text
schema
provider
model
temperature
scheduled_attempts_per_scenario
total_rows
parse_success_count
workflow_validate_valid_count
correct_intent_count
canonical_success_count
over_declared_count
invented_count
not_classifiable_count
scenario_counts
canonical_evidence
```

`canonical_evidence` is explicit, not inferred from provider/model names. Add a
CLI flag:

```text
--canonical-evidence       default false
```

Implementation rules:

- `canonical_evidence` is `False` unless the flag is present.
- If the flag is present, require:
  - `attempts == 5`
  - `provider` is not a placeholder such as `fake` or `ceiling-provider`
  - `model` is not a placeholder such as `fake-planner` or `ceiling-planner-model`
- The flag does not prove the provider is truly a ceiling model by itself; it
  records the operator's pre-registered canonical-run intent after selecting
  the ceiling provider/model.
- Local/open-weight rows such as `provider=ollama`, `model=gemma4:12b-it-qat`
  must leave `canonical_evidence` false unless a later slice explicitly
  promotes them.

Rejected canonical flag examples:

```text
--canonical-evidence --attempts 1
--canonical-evidence --provider fake --model fake-planner
--canonical-evidence --provider ceiling-provider --model ceiling-planner-model
```

The exact provider/model chosen for a ceiling run is recorded in the manifest and rows.

---

## Task 7: Provider-Command CLI and Deterministic No-Live Tests

**Files:**

- Modify: `scripts/lm7c_planner_authoring_probe.py`
- Modify: `mcp_server/tests/test_lm7c_planner_authoring_probe.py`

- [ ] **Step 1: Write tests for provider-command seam**

Tests should monkeypatch the command runner, not execute a real subprocess:

```python
def test_main_requires_provider_command_for_cli_run(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        PROBE.main(["--run-dir", str(tmp_path), "--provider", "ceiling-provider"])

    assert exc.value.code == 2
    assert "provider_command_required" in capsys.readouterr().err


@pytest.mark.parametrize(
    "argv",
    [
        ["--canonical-evidence", "--attempts", "1"],
        ["--canonical-evidence", "--provider", "fake", "--model", "fake-planner"],
        [
            "--canonical-evidence",
            "--provider",
            "ceiling-provider",
            "--model",
            "ceiling-planner-model",
        ],
    ],
)
def test_main_rejects_invalid_canonical_evidence_declarations(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
) -> None:
    with pytest.raises(SystemExit) as exc:
        PROBE.main(["--run-dir", str(tmp_path), "--provider-command", "fake-provider", *argv])

    assert exc.value.code == 2
    assert "invalid_canonical_evidence" in capsys.readouterr().err


def test_main_uses_injected_provider_command_without_live_model(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def fake_command(command, call_payload, timeout_s):
        calls.append((command, call_payload, timeout_s))
        return json.dumps(_minimal_complete_request())

    monkeypatch.setattr(PROBE, "_call_provider_command", fake_command)

    exit_code = PROBE.main(
        [
            "--run-dir",
            str(tmp_path),
            "--attempts",
            "1",
            "--provider",
            "fake-provider-label",
            "--provider-command",
            "fake-provider",
            "--model",
            "fake-planner",
        ]
    )

    assert exit_code == 0
    assert calls
```

- [ ] **Step 2: Implement CLI main**

CLI args:

```text
--attempts                  default 5, positive integer
--provider                  default ceiling-provider
--provider-command          optional command string for operational live provider adapter
--provider-timeout-s        default 120
--model                     default ceiling-planner-model
--temperature               default 0
--run-dir                   default probe_runs
--output-excerpt-chars      default 1200
--canonical-evidence        default false
```

Do not add:

```text
--phase
--retry-clean-observation
--request-json
--endpoint
--ollama-url
```

Provider-command semantics:

- Run the command as a subprocess with the call payload JSON on stdin.
- Capture stdout/stderr.
- Nonzero return code raises a provider exception that row scoring records as `provider_error:CalledProcessError` or a stable wrapper-specific class.
- Stdout is the raw model output.
- Stderr is not written as a separate transcript artifact in v1.

If the implementer believes provider-command is too much for this slice, stop and report that before hardcoding any provider SDK. Do not add OpenAI/Anthropic/Ollama SDK calls in LM7C v1.

---

## Task 8: Static Guards and Scope Protection

**Files:**

- Modify: `mcp_server/tests/test_lm7c_planner_authoring_probe.py`

- [ ] **Step 1: Add import/source guard tests**

Test that the script does not import forbidden live/worker surfaces:

```python
def test_lm7c_script_does_not_import_live_worker_or_rhino_surfaces() -> None:
    source = _script_path().read_text(encoding="utf-8")

    forbidden = (
        "lm7b_request_driven_live_splice_probe",
        "lm6a_live_worker_splice_probe",
        "lm_worker_two_pass_publication",
        "plan_graph_worker_action_apply",
        "_mcp_tool_executor",
        "run_live_producer_node",
        "run_live_repair",
        "rhino_ping",
        "gh_document_new",
        "gh_update_script",
    )
    for token in forbidden:
        assert token not in source
```

If raw-string guards collide with prompt text, switch to AST import/name guards. Do not weaken the semantic guard.

Test prompt artifact hidden markers separately, as in Task 2. Classifier policy may contain marker strings like `42.0`; prompt artifacts must not.

- [ ] **Step 2: Add exact diff-scope check to final verification commands**

Implementation PR expected diff scope:

```text
docs/superpowers/plans/2026-07-07-lm7c-planner-authoring-probe.md
scripts/lm7c_planner_authoring_probe.py
mcp_server/tests/test_lm7c_planner_authoring_probe.py
```

Any changes to `mcp_server/src/rook/**/*.py`, LM7B, LM6A, LM5W/X/Y, worker publication, or request schema modules require stopping for review.

---

## Task 9: Final Verification

Run from `C:\UDEV\Rook`:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm7c_planner_authoring_probe.py `
  mcp_server\tests\test_planner_worker_contract_request.py `
  mcp_server\tests\test_workflow_validate.py `
  -q
```

Compile:

```powershell
py -3.10 -m py_compile `
  scripts\lm7c_planner_authoring_probe.py `
  mcp_server\tests\test_lm7c_planner_authoring_probe.py
```

Whitespace:

```powershell
git diff --check main..HEAD
```

Diff scope, order-insensitive:

```powershell
$expected = @(
  "docs/superpowers/plans/2026-07-07-lm7c-planner-authoring-probe.md",
  "scripts/lm7c_planner_authoring_probe.py",
  "mcp_server/tests/test_lm7c_planner_authoring_probe.py"
) | Sort-Object

$actual = git diff --name-only main..HEAD | Sort-Object
Compare-Object $expected $actual
```

The comparison should emit no differences.

Forbidden drift check:

```powershell
git diff --name-only main..HEAD | Select-String `
  -Pattern "lm7b_request_driven_live_splice_probe.py","lm6a_live_worker_splice_probe.py","lm_worker_two_pass_publication.py","planner_worker_contract_request.py","workflow_validate.py"
```

Expected: no matches.

Do not run a live model during the implementation PR.

---

## Post-Merge Evidence Runbook

After implementation merges and `main` is synced, canonical LM7C evidence is a separate run and a separate evidence-summary PR.

Canonical run properties:

```text
attempts: 5 per scenario
scenarios: intent_complete, intent_incomplete
provider/model: actual ceiling/Planner-tier provider selected at run time
flag: --canonical-evidence
decoding: deterministic where provider supports it
no fallback model substitution
```

The run command will use the provider-command adapter or a separately approved provider adapter. The implementation PR must not include credentials, provider SDK setup, or live output.

Evidence summary should report:

```text
parse_success_count
workflow_validate_valid_count
correct_intent_count
canonical_success_count
over_declared_count
invented_count
not_classifiable_count
per-scenario breakdown
provider/model/prompt/template-menu/brief versions
```

Pre-registered read:

- Expected failure: over-declaration, especially declaring `desired_output_value` unresolved in the `intent_complete` scenario.
- Safety failure: invention, especially filling `desired_output_value` or adding concrete output/repair literals in the `intent_incomplete` scenario.

---

## Notes for Reviewer

This plan intentionally does not broaden the LM7A request surface. In the complete-intent case, the correct behavior is not to encode `7.5`; it is to avoid declaring `desired_output_value` missing.

The only slightly awkward classifier case is `intent_incomplete` with no unresolved slot and no concrete invented value. LM7C's locked vocabulary has no `under_declared` value, so this plan records it as:

```text
intent_decision = not_classifiable
failure_reason = missing_unresolved_desired_output_value
canonical_success = false
```

That preserves the specified enum while keeping the row deterministic and non-successful.
