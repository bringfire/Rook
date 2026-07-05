# LM5S Pass-1 Disposition Semantics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Revise the LM5R two-pass probe's pass-1 decision instruction semantics and add report-only observation action-intent anomaly evidence.

**Architecture:** LM5S updates the existing LM5R diagnostic script in place. It keeps the two-pass publication flow, pass-2 formatter, single-kind schemas, and status taxonomy unchanged, while changing only the pass-1 instruction identity/text and adding anomaly fields derived from parsed decision/response objects.

**Tech Stack:** Python 3.10, pytest, direct Ollama probe script, existing LM5G loader and LM5R test harness.

---

## File Structure

Modify:

```text
scripts/lm5r_two_pass_publication_probe.py
mcp_server/tests/test_lm5r_two_pass_publication_probe.py
```

Already written:

```text
docs/superpowers/specs/2026-07-04-lm5s-pass1-disposition-semantics-design.md
docs/superpowers/plans/2026-07-04-lm5s-pass1-disposition-semantics.md
```

Do not modify:

```text
mcp_server/src/rook/**/*.py
scripts/lm5k_worker_probe.py
scripts/lm5p_ollama_think_format_spike.py
docs/superpowers/probes/**/*.md
```

## Task 1: Pin Pass-1 Instruction v2

**Files:**
- Modify: `scripts/lm5r_two_pass_publication_probe.py`
- Test: `mcp_server/tests/test_lm5r_two_pass_publication_probe.py`

- [ ] **Step 1: Update the constant tests first**

In `mcp_server/tests/test_lm5r_two_pass_publication_probe.py`, update
`test_constants_are_pinned`:

```python
def test_constants_are_pinned() -> None:
    assert PROBE.SCRIPT_SCHEMA == "rook.lm5r_two_pass_publication_probe:v1"
    assert (
        PROBE.PASS1_DECISION_INSTRUCTION_VERSION
        == "lm5s.pass1_decision_instruction:v2"
    )
    assert PROBE.DEFAULT_MODEL == "gemma4:12b-it-qat"
    assert PROBE.SCENARIO_NAMES == (
        "evidence_absent_like",
        "evidence_present_like",
    )
    assert PROBE.DEFAULT_ATTEMPTS == 5
    assert PROBE.DEFAULT_TEMPERATURE == 0
    assert PROBE.EXCERPT_CHARS == 500
    assert PROBE.STATUSES == (
        "pass1_provider_error",
        "pass1_decision_invalid",
        "pass2_provider_error",
        "pass2_lm5g_invalid",
        "pass2_invariant_violation",
        "published",
    )
```

- [ ] **Step 2: Add instruction-content tests**

Add this test near `test_pass1_messages_use_real_lm5n_envelopes`:

```python
def test_pass1_instruction_v2_pins_generic_kind_semantics() -> None:
    text = PROBE._PASS1_DECISION_INSTRUCTION

    assert "action_request" in text
    assert "visible context is sufficient" in text
    assert "author the required action input" in text
    assert "clarification_request" in text
    assert "required information is missing" in text
    assert "refusal" in text
    assert "unsafe, unsupported, or out of scope" in text
    assert "observation" in text
    assert "visible state or evidence" in text
    assert "Do not use observation to choose, suggest, imply, or carry an action" in text
    assert "Do not put action identity or action choice" in text


def test_pass1_instruction_v2_contains_no_scenario_specific_literals() -> None:
    text = PROBE._PASS1_DECISION_INSTRUCTION

    forbidden = (
        "draft_repair_params",
        "repair_same_component",
        "component_guid",
        "RunScript",
        "DefinitelyMissingSymbol",
        '"code"',
        '"mode"',
        "gemma",
        "Gemma",
    )
    for literal in forbidden:
        assert literal not in text
```

- [ ] **Step 3: Update manifest-version assertion**

In `test_run_probe_writes_manifest_attempts_and_summary`, replace the
hardcoded version assertion:

```python
    assert (
        manifest["pass1_decision_instruction_version"]
        == "lm5r.pass1_decision_instruction:v1"
    )
```

with:

```python
    assert (
        manifest["pass1_decision_instruction_version"]
        == PROBE.PASS1_DECISION_INSTRUCTION_VERSION
    )
```

Keep the existing SHA assertion:

```python
    assert manifest["pass1_decision_instruction_sha256"] == PROBE._sha256_text(
        PROBE._PASS1_DECISION_INSTRUCTION
    )
```

- [ ] **Step 4: Run the focused tests and verify RED**

Run:

```powershell
cd C:\Users\bring\.config\superpowers\worktrees\Rook\lm5s-pass1-disposition-semantics
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py::test_constants_are_pinned `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py::test_pass1_instruction_v2_pins_generic_kind_semantics `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py::test_pass1_instruction_v2_contains_no_scenario_specific_literals `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py::test_run_probe_writes_manifest_attempts_and_summary -q
```

Expected: fail on the old `lm5r.pass1_decision_instruction:v1` value and/or
missing v2 instruction wording.

- [ ] **Step 5: Update the instruction constant and text**

In `scripts/lm5r_two_pass_publication_probe.py`, replace the current
`PASS1_DECISION_INSTRUCTION_VERSION` and `_PASS1_DECISION_INSTRUCTION` block
with:

```python
PASS1_DECISION_INSTRUCTION_VERSION = "lm5s.pass1_decision_instruction:v2"

_PASS1_DECISION_INSTRUCTION = """\
Return a small decision JSON object for this worker turn.

The object must contain kind. Choose the kind by these generic semantics:
- action_request: choose only when visible context is sufficient to author the
  required action input.
- clarification_request: choose when required information is missing.
- refusal: choose when the request is unsafe, unsupported, or out of scope.
- observation: choose only to report visible state or evidence.

Do not use observation to choose, suggest, imply, or carry an action.
Do not put action identity or action choice in observation.message or
observation.data.

Required fields per kind:
- action_request: action_id
- clarification_request: question
- refusal: category and reason
- observation: message

Optional fields: rationale, intent, action_input_intent, known_inputs,
data_intent.

Do not return a strict LM5 response envelope in this pass. This pass decides
only. The next pass will publish the chosen kind.
"""
```

- [ ] **Step 6: Run the focused tests and verify GREEN**

Run:

```powershell
cd C:\Users\bring\.config\superpowers\worktrees\Rook\lm5s-pass1-disposition-semantics
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py::test_constants_are_pinned `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py::test_pass1_instruction_v2_pins_generic_kind_semantics `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py::test_pass1_instruction_v2_contains_no_scenario_specific_literals `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py::test_run_probe_writes_manifest_attempts_and_summary -q
```

Expected: all selected tests pass.

- [ ] **Step 7: Commit Task 1**

Run:

```powershell
git add scripts\lm5r_two_pass_publication_probe.py `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py
git commit -m "test(lm5s): revise pass-one decision instruction"
```

## Task 2: Add Observation Action-Intent Helper

**Files:**
- Modify: `scripts/lm5r_two_pass_publication_probe.py`
- Test: `mcp_server/tests/test_lm5r_two_pass_publication_probe.py`

- [ ] **Step 1: Write helper tests**

Add these tests after `test_parse_pass1_decision_records_recursion_error`:

```python
def test_observation_action_intent_reasons_ignore_non_observation_payloads() -> None:
    reasons = PROBE._observation_action_intent_reasons(
        payload={"kind": "action_request", "action_id": "draft_repair_params"},
        allowed_action_ids=("draft_repair_params",),
    )

    assert reasons == ()


def test_observation_action_intent_reasons_detect_data_action_id_only_once() -> None:
    reasons = PROBE._observation_action_intent_reasons(
        payload={
            "kind": "observation",
            "message": "State report.",
            "data": {"action_id": "draft_repair_params"},
        },
        allowed_action_ids=("draft_repair_params",),
    )

    assert reasons == ("observation_data_action_id_allowed",)


def test_observation_action_intent_reasons_detect_data_action_id_containing_text() -> None:
    reasons = PROBE._observation_action_intent_reasons(
        payload={
            "kind": "observation",
            "message": "State report.",
            "data": {"action_id": "candidate action draft_repair_params"},
        },
        allowed_action_ids=("draft_repair_params",),
    )

    assert reasons == ("observation_data_mentions_allowed_action_id",)


def test_observation_action_intent_reasons_detect_message_action_id() -> None:
    reasons = PROBE._observation_action_intent_reasons(
        payload={
            "kind": "observation",
            "message": "The visible action is draft_repair_params.",
            "data": None,
        },
        allowed_action_ids=("draft_repair_params",),
    )

    assert reasons == ("observation_message_mentions_allowed_action_id",)


def test_observation_action_intent_reasons_detect_top_level_data_string_action_id_text() -> None:
    reasons = PROBE._observation_action_intent_reasons(
        payload={
            "kind": "observation",
            "message": "State report.",
            "data": "candidate action draft_repair_params",
        },
        allowed_action_ids=("draft_repair_params",),
    )

    assert reasons == ("observation_data_mentions_allowed_action_id",)


def test_observation_action_intent_reasons_detect_top_level_data_list_action_id_text() -> None:
    reasons = PROBE._observation_action_intent_reasons(
        payload={
            "kind": "observation",
            "message": "State report.",
            "data": ["other", "candidate action draft_repair_params"],
        },
        allowed_action_ids=("draft_repair_params",),
    )

    assert reasons == ("observation_data_mentions_allowed_action_id",)


def test_observation_action_intent_reasons_detect_nested_data_action_id_text() -> None:
    reasons = PROBE._observation_action_intent_reasons(
        payload={
            "kind": "observation",
            "message": "State report.",
            "data": {
                "note": "The candidate action is draft_repair_params.",
                "nested": {"items": ["plain", "draft_repair_params"]},
            },
        },
        allowed_action_ids=("draft_repair_params",),
    )

    assert reasons == ("observation_data_mentions_allowed_action_id",)


def test_observation_action_intent_reasons_detect_data_intent_action_id_text() -> None:
    reasons = PROBE._observation_action_intent_reasons(
        payload={
            "kind": "observation",
            "message": "State report.",
            "data_intent": {"action_id": "draft_repair_params"},
        },
        allowed_action_ids=("draft_repair_params",),
    )

    assert reasons == ("observation_data_intent_mentions_allowed_action_id",)


def test_observation_action_intent_reasons_sort_and_deduplicate_reasons() -> None:
    reasons = PROBE._observation_action_intent_reasons(
        payload={
            "kind": "observation",
            "message": "draft_repair_params",
            "data": {
                "action_id": "draft_repair_params",
                "note": "draft_repair_params",
            },
            "data_intent": "draft_repair_params",
        },
        allowed_action_ids=("draft_repair_params",),
    )

    assert reasons == (
        "observation_data_action_id_allowed",
        "observation_data_intent_mentions_allowed_action_id",
        "observation_data_mentions_allowed_action_id",
        "observation_message_mentions_allowed_action_id",
    )
```

The second test pins the planning note: exact `data.action_id` alone triggers
only `observation_data_action_id_allowed`, not the broader recursive data-string
reason. The containing-text action id test pins that non-exact strings in the
same field still count as data text leakage. The top-level data tests pin the
LM5S behavior that lightweight pass 1 decision artifacts can carry observation
data as a string or list.

- [ ] **Step 2: Run helper tests and verify RED**

Run:

```powershell
cd C:\Users\bring\.config\superpowers\worktrees\Rook\lm5s-pass1-disposition-semantics
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py::test_observation_action_intent_reasons_ignore_non_observation_payloads `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py::test_observation_action_intent_reasons_detect_data_action_id_only_once `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py::test_observation_action_intent_reasons_detect_data_action_id_containing_text `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py::test_observation_action_intent_reasons_detect_message_action_id `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py::test_observation_action_intent_reasons_detect_top_level_data_string_action_id_text `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py::test_observation_action_intent_reasons_detect_top_level_data_list_action_id_text `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py::test_observation_action_intent_reasons_detect_nested_data_action_id_text `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py::test_observation_action_intent_reasons_detect_data_intent_action_id_text `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py::test_observation_action_intent_reasons_sort_and_deduplicate_reasons -q
```

Expected: fail because `_observation_action_intent_reasons` does not exist.

- [ ] **Step 3: Implement helper imports and functions**

In `scripts/lm5r_two_pass_publication_probe.py`, change the import:

```python
from collections.abc import Collection, Mapping
```

Add these helpers after `_parse_pass1_decision`:

```python
def _json_value_contains_allowed_action_id(
    value: Any,
    allowed_action_ids: Collection[str],
    *,
    skip_action_id_value: bool = False,
) -> bool:
    if isinstance(value, str):
        return any(action_id in value for action_id in allowed_action_ids)
    if isinstance(value, Mapping):
        for key, item in value.items():
            if skip_action_id_value and key == "action_id":
                continue
            if _json_value_contains_allowed_action_id(
                item,
                allowed_action_ids,
                skip_action_id_value=False,
            ):
                return True
        return False
    if isinstance(value, (list, tuple)):
        return any(
            _json_value_contains_allowed_action_id(
                item,
                allowed_action_ids,
                skip_action_id_value=False,
            )
            for item in value
        )
    return False


def _observation_action_intent_reasons(
    *,
    payload: Mapping[str, Any],
    allowed_action_ids: Collection[str],
) -> tuple[str, ...]:
    if payload.get("kind") != "observation":
        return ()

    reasons: set[str] = set()
    data = payload.get("data")
    if isinstance(data, Mapping):
        action_id = data.get("action_id")
        if isinstance(action_id, str) and action_id in allowed_action_ids:
            reasons.add("observation_data_action_id_allowed")
    if data is not None and _json_value_contains_allowed_action_id(
        data,
        allowed_action_ids,
        skip_action_id_value=(
            isinstance(data, Mapping)
            and isinstance(data.get("action_id"), str)
            and data.get("action_id") in allowed_action_ids
        ),
    ):
        reasons.add("observation_data_mentions_allowed_action_id")

    data_intent = payload.get("data_intent")
    if data_intent is not None and _json_value_contains_allowed_action_id(
        data_intent,
        allowed_action_ids,
    ):
        reasons.add("observation_data_intent_mentions_allowed_action_id")

    message = payload.get("message")
    if isinstance(message, str) and any(
        action_id in message for action_id in allowed_action_ids
    ):
        reasons.add("observation_message_mentions_allowed_action_id")

    return tuple(sorted(reasons))
```

- [ ] **Step 4: Run helper tests and verify GREEN**

Run:

```powershell
cd C:\Users\bring\.config\superpowers\worktrees\Rook\lm5s-pass1-disposition-semantics
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py::test_observation_action_intent_reasons_ignore_non_observation_payloads `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py::test_observation_action_intent_reasons_detect_data_action_id_only_once `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py::test_observation_action_intent_reasons_detect_data_action_id_containing_text `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py::test_observation_action_intent_reasons_detect_message_action_id `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py::test_observation_action_intent_reasons_detect_top_level_data_string_action_id_text `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py::test_observation_action_intent_reasons_detect_top_level_data_list_action_id_text `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py::test_observation_action_intent_reasons_detect_nested_data_action_id_text `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py::test_observation_action_intent_reasons_detect_data_intent_action_id_text `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py::test_observation_action_intent_reasons_sort_and_deduplicate_reasons -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit Task 2**

Run:

```powershell
git add scripts\lm5r_two_pass_publication_probe.py `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py
git commit -m "feat(lm5s): detect observation action leaks"
```

## Task 3: Integrate Anomaly Fields Into Attempt Rows

**Files:**
- Modify: `scripts/lm5r_two_pass_publication_probe.py`
- Test: `mcp_server/tests/test_lm5r_two_pass_publication_probe.py`

- [ ] **Step 1: Update `_summary_row` test helper**

In `mcp_server/tests/test_lm5r_two_pass_publication_probe.py`, extend
`_summary_row`:

```python
def _summary_row(
    *,
    scenario: str = "evidence_absent_like",
    status: str = "published",
    pass1_kind: str | None = "clarification_request",
    pass2_response_kind: str | None = "clarification_request",
    kind_preserved: bool | None = True,
    action_id_preserved: bool | None = None,
    refusal_category_preserved: bool | None = None,
    lm5g_loadable: bool = True,
    failure_reason: str | None = None,
    observation_action_intent_anomaly: bool = False,
    observation_action_intent_reasons: list[str] | None = None,
) -> dict:
    return {
        "scenario": scenario,
        "status": status,
        "pass1_kind": pass1_kind,
        "pass2_response_kind": pass2_response_kind,
        "kind_preserved": kind_preserved,
        "action_id_preserved": action_id_preserved,
        "refusal_category_preserved": refusal_category_preserved,
        "lm5g_loadable": lm5g_loadable,
        "failure_reason": failure_reason,
        "observation_action_intent_anomaly": observation_action_intent_anomaly,
        "observation_action_intent_reasons": (
            observation_action_intent_reasons or []
        ),
    }
```

- [ ] **Step 2: Add run-attempt tests for pass-specific anomaly fields**

Add these tests after `test_run_attempt_publishes_valid_same_kind_clarification`:

```python
def test_run_attempt_records_pass1_observation_action_intent_anomaly() -> None:
    provider = _FakeProvider(
        [
            _ollama_response(
                json.dumps(
                    {
                        "kind": "observation",
                        "message": "Decision: draft_repair_params",
                        "data": {"action_id": "draft_repair_params"},
                    }
                ),
                thinking="state report",
            ),
            _ollama_response(
                json.dumps(
                    {
                        "schema": "rook.local_worker_turn_response:v1",
                        "kind": "observation",
                        "message": "State only.",
                        "data": None,
                    }
                )
            ),
        ]
    )

    row = PROBE._run_attempt(
        model="gemma4:12b-it-qat",
        scenario="evidence_absent_like",
        attempt=1,
        endpoint="http://fake.local/api/chat",
        temperature=0,
        timeout_s=9,
        excerpt_chars=500,
        post_chat=provider,
    )

    assert row["status"] == "published"
    assert row["pass1_observation_action_intent_anomaly"] is True
    assert row["pass1_observation_action_intent_reasons"] == [
        "observation_data_action_id_allowed",
        "observation_message_mentions_allowed_action_id",
    ]
    assert row["pass2_observation_action_intent_anomaly"] is False
    assert row["pass2_observation_action_intent_reasons"] == []
    assert row["observation_action_intent_anomaly"] is True
    assert row["observation_action_intent_reasons"] == [
        "observation_data_action_id_allowed",
        "observation_message_mentions_allowed_action_id",
    ]


def test_run_attempt_records_pass2_observation_action_intent_anomaly_after_lm5g_load() -> None:
    provider = _FakeProvider(
        [
            _ollama_response(
                json.dumps(
                    {
                        "kind": "observation",
                        "message": "Visible state only.",
                    }
                ),
                thinking="state report",
            ),
            _ollama_response(
                json.dumps(
                    {
                        "schema": "rook.local_worker_turn_response:v1",
                        "kind": "observation",
                        "message": "State report.",
                        "data": {"note": "draft_repair_params"},
                    }
                )
            ),
        ]
    )

    row = PROBE._run_attempt(
        model="gemma4:12b-it-qat",
        scenario="evidence_absent_like",
        attempt=1,
        endpoint="http://fake.local/api/chat",
        temperature=0,
        timeout_s=9,
        excerpt_chars=500,
        post_chat=provider,
    )

    assert row["status"] == "published"
    assert row["pass1_observation_action_intent_anomaly"] is False
    assert row["pass1_observation_action_intent_reasons"] == []
    assert row["pass2_observation_action_intent_anomaly"] is True
    assert row["pass2_observation_action_intent_reasons"] == [
        "observation_data_mentions_allowed_action_id"
    ]
    assert row["observation_action_intent_anomaly"] is True
    assert row["observation_action_intent_reasons"] == [
        "observation_data_mentions_allowed_action_id"
    ]


def test_run_attempt_does_not_score_pass2_anomaly_when_lm5g_load_fails() -> None:
    provider = _FakeProvider(
        [
            _ollama_response(
                json.dumps(
                    {
                        "kind": "observation",
                        "message": "Visible state only.",
                    }
                )
            ),
            _ollama_response(
                json.dumps(
                    {
                        "schema": "rook.local_worker_turn_response:v1",
                        "kind": "observation",
                        "message": "draft_repair_params",
                    }
                )
            ),
        ]
    )

    row = PROBE._run_attempt(
        model="gemma4:12b-it-qat",
        scenario="evidence_absent_like",
        attempt=1,
        endpoint="http://fake.local/api/chat",
        temperature=0,
        timeout_s=9,
        excerpt_chars=500,
        post_chat=provider,
    )

    assert row["status"] == "pass2_lm5g_invalid"
    assert row["failure_reason"] == "pass2_lm5g_load_failed:ValueError"
    assert row["pass2_observation_action_intent_anomaly"] is False
    assert row["pass2_observation_action_intent_reasons"] == []
```

- [ ] **Step 3: Run new integration tests and verify RED**

Run:

```powershell
cd C:\Users\bring\.config\superpowers\worktrees\Rook\lm5s-pass1-disposition-semantics
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py::test_run_attempt_records_pass1_observation_action_intent_anomaly `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py::test_run_attempt_records_pass2_observation_action_intent_anomaly_after_lm5g_load `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py::test_run_attempt_does_not_score_pass2_anomaly_when_lm5g_load_fails -q
```

Expected: fail because the row fields are not present yet.

- [ ] **Step 4: Add row defaults and allowed-action helper**

In `scripts/lm5r_two_pass_publication_probe.py`, extend `_empty_attempt_row`
by adding these keys before `"lm5g_loadable": False`:

```python
        "pass1_observation_action_intent_anomaly": False,
        "pass1_observation_action_intent_reasons": [],
        "pass2_observation_action_intent_anomaly": False,
        "pass2_observation_action_intent_reasons": [],
        "observation_action_intent_anomaly": False,
        "observation_action_intent_reasons": [],
```

Add this helper after `_observation_action_intent_reasons`:

```python
def _allowed_action_ids_from_request(
    request_payload: Mapping[str, Any],
) -> tuple[str, ...]:
    context = request_payload.get("context")
    if not isinstance(context, Mapping):
        return ()
    allowed_actions = context.get("allowed_actions")
    if not isinstance(allowed_actions, list):
        return ()

    action_ids: set[str] = set()
    for action in allowed_actions:
        if not isinstance(action, Mapping):
            continue
        action_id = action.get("action_id")
        if isinstance(action_id, str) and action_id:
            action_ids.add(action_id)
    return tuple(sorted(action_ids))
```

Add this helper after `_allowed_action_ids_from_request`:

```python
def _set_combined_observation_anomaly(row: dict[str, Any]) -> None:
    reasons = sorted(
        set(row["pass1_observation_action_intent_reasons"])
        | set(row["pass2_observation_action_intent_reasons"])
    )
    row["observation_action_intent_reasons"] = reasons
    row["observation_action_intent_anomaly"] = bool(reasons)
```

- [ ] **Step 5: Score pass 1 and pass 2 in `_run_attempt`**

In `_run_attempt`, immediately after:

```python
    row["pass1_refusal_category"] = decision.get("category")
```

insert:

```python
    allowed_action_ids = _allowed_action_ids_from_request(request_payload)
    pass1_anomaly_reasons = _observation_action_intent_reasons(
        payload=decision,
        allowed_action_ids=allowed_action_ids,
    )
    row["pass1_observation_action_intent_reasons"] = list(pass1_anomaly_reasons)
    row["pass1_observation_action_intent_anomaly"] = bool(pass1_anomaly_reasons)
    _set_combined_observation_anomaly(row)
```

In `_run_attempt`, immediately after successful
`load_local_worker_turn_response_payload(parsed_response)`, before setting
`row["lm5g_loadable"] = True`, insert:

```python
    pass2_anomaly_reasons = _observation_action_intent_reasons(
        payload=parsed_response,
        allowed_action_ids=allowed_action_ids,
    )
    row["pass2_observation_action_intent_reasons"] = list(pass2_anomaly_reasons)
    row["pass2_observation_action_intent_anomaly"] = bool(pass2_anomaly_reasons)
    _set_combined_observation_anomaly(row)
```

- [ ] **Step 6: Run new integration tests and verify GREEN**

Run:

```powershell
cd C:\Users\bring\.config\superpowers\worktrees\Rook\lm5s-pass1-disposition-semantics
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py::test_run_attempt_records_pass1_observation_action_intent_anomaly `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py::test_run_attempt_records_pass2_observation_action_intent_anomaly_after_lm5g_load `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py::test_run_attempt_does_not_score_pass2_anomaly_when_lm5g_load_fails -q
```

Expected: all selected tests pass.

- [ ] **Step 7: Commit Task 3**

Run:

```powershell
git add scripts\lm5r_two_pass_publication_probe.py `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py
git commit -m "feat(lm5s): record observation anomaly rows"
```

## Task 4: Add Summary Anomaly Counts

**Files:**
- Modify: `scripts/lm5r_two_pass_publication_probe.py`
- Test: `mcp_server/tests/test_lm5r_two_pass_publication_probe.py`

- [ ] **Step 1: Update summary test expectations**

In `test_build_summary_groups_by_status_kind_and_preservation`, change
`rows = [...]` to:

```python
    rows = [
        _summary_row(),
        _summary_row(
            scenario="evidence_present_like",
            pass1_kind="action_request",
            pass2_response_kind="action_request",
            action_id_preserved=True,
        ),
        _summary_row(
            scenario="evidence_present_like",
            status="pass2_invariant_violation",
            pass1_kind="action_request",
            pass2_response_kind="action_request",
            action_id_preserved=False,
            failure_reason="pass2_action_id_changed",
        ),
        _summary_row(
            scenario="evidence_absent_like",
            pass1_kind="observation",
            pass2_response_kind="observation",
            observation_action_intent_anomaly=True,
            observation_action_intent_reasons=[
                "observation_data_action_id_allowed",
                "observation_message_mentions_allowed_action_id",
            ],
        ),
    ]
```

Update the expected `summary["groups"]` to:

```python
    assert summary["groups"] == [
        {
            "scenario": "evidence_absent_like",
            "status": "published",
            "pass1_kind": "clarification_request",
            "pass2_response_kind": "clarification_request",
            "kind_preserved": True,
            "action_id_preserved": None,
            "refusal_category_preserved": None,
            "attempts": 1,
            "lm5g_loadable_count": 1,
            "failure_reason_counts": {},
            "observation_action_intent_anomaly_count": 0,
            "observation_action_intent_reason_counts": {},
        },
        {
            "scenario": "evidence_absent_like",
            "status": "published",
            "pass1_kind": "observation",
            "pass2_response_kind": "observation",
            "kind_preserved": True,
            "action_id_preserved": None,
            "refusal_category_preserved": None,
            "attempts": 1,
            "lm5g_loadable_count": 1,
            "failure_reason_counts": {},
            "observation_action_intent_anomaly_count": 1,
            "observation_action_intent_reason_counts": {
                "observation_data_action_id_allowed": 1,
                "observation_message_mentions_allowed_action_id": 1,
            },
        },
        {
            "scenario": "evidence_present_like",
            "status": "pass2_invariant_violation",
            "pass1_kind": "action_request",
            "pass2_response_kind": "action_request",
            "kind_preserved": True,
            "action_id_preserved": False,
            "refusal_category_preserved": None,
            "attempts": 1,
            "lm5g_loadable_count": 1,
            "failure_reason_counts": {"pass2_action_id_changed": 1},
            "observation_action_intent_anomaly_count": 0,
            "observation_action_intent_reason_counts": {},
        },
        {
            "scenario": "evidence_present_like",
            "status": "published",
            "pass1_kind": "action_request",
            "pass2_response_kind": "action_request",
            "kind_preserved": True,
            "action_id_preserved": True,
            "refusal_category_preserved": None,
            "attempts": 1,
            "lm5g_loadable_count": 1,
            "failure_reason_counts": {},
            "observation_action_intent_anomaly_count": 0,
            "observation_action_intent_reason_counts": {},
        },
    ]
```

- [ ] **Step 2: Run summary test and verify RED**

Run:

```powershell
cd C:\Users\bring\.config\superpowers\worktrees\Rook\lm5s-pass1-disposition-semantics
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py::test_build_summary_groups_by_status_kind_and_preservation -q
```

Expected: fail because summary groups do not include anomaly counts.

- [ ] **Step 3: Add reason-count helper**

In `scripts/lm5r_two_pass_publication_probe.py`, add this helper after
`_count_strings`:

```python
def _count_reason_list(rows: list[Mapping[str, Any]], key: str) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for row in rows:
        values = row.get(key)
        if not isinstance(values, list):
            continue
        for value in values:
            if isinstance(value, str) and value:
                counts[value] += 1
    return dict(sorted(counts.items()))
```

- [ ] **Step 4: Extend summary groups**

In `_build_summary`, inside each group dict, add:

```python
                "observation_action_intent_anomaly_count": sum(
                    1
                    for row in group_rows
                    if row.get("observation_action_intent_anomaly") is True
                ),
                "observation_action_intent_reason_counts": _count_reason_list(
                    group_rows,
                    "observation_action_intent_reasons",
                ),
```

Place these after `failure_reason_counts` so output is stable and easy to scan.

- [ ] **Step 5: Run summary test and verify GREEN**

Run:

```powershell
cd C:\Users\bring\.config\superpowers\worktrees\Rook\lm5s-pass1-disposition-semantics
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py::test_build_summary_groups_by_status_kind_and_preservation -q
```

Expected: selected test passes.

- [ ] **Step 6: Commit Task 4**

Run:

```powershell
git add scripts\lm5r_two_pass_publication_probe.py `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py
git commit -m "feat(lm5s): summarize observation anomalies"
```

## Task 5: Full Deterministic Verification

**Files:**
- Verify: `scripts/lm5r_two_pass_publication_probe.py`
- Verify: `mcp_server/tests/test_lm5r_two_pass_publication_probe.py`

- [ ] **Step 1: Run the targeted LM5S/LM5R test file**

Run:

```powershell
cd C:\Users\bring\.config\superpowers\worktrees\Rook\lm5s-pass1-disposition-semantics
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py -q
```

Expected: all tests in `test_lm5r_two_pass_publication_probe.py` pass.

- [ ] **Step 2: Run the nearby probe gate**

Run:

```powershell
cd C:\Users\bring\.config\superpowers\worktrees\Rook\lm5s-pass1-disposition-semantics
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py `
  mcp_server\tests\test_lm5p_ollama_think_format_spike.py `
  mcp_server\tests\test_lm5k_worker_probe.py -q
```

Expected: all selected tests pass.

- [ ] **Step 3: Run Python 3.10 compile check**

Run:

```powershell
cd C:\Users\bring\.config\superpowers\worktrees\Rook\lm5s-pass1-disposition-semantics
py -3.10 -m py_compile `
  scripts\lm5r_two_pass_publication_probe.py `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py
```

Expected: command exits 0 with no output.

- [ ] **Step 4: Run static scope and whitespace checks**

Run:

```powershell
cd C:\Users\bring\.config\superpowers\worktrees\Rook\lm5s-pass1-disposition-semantics
git diff --check origin/main..HEAD
git diff --name-only origin/main..HEAD
```

Expected diff paths:

```text
docs/superpowers/plans/2026-07-04-lm5s-pass1-disposition-semantics.md
docs/superpowers/specs/2026-07-04-lm5s-pass1-disposition-semantics-design.md
mcp_server/tests/test_lm5r_two_pass_publication_probe.py
scripts/lm5r_two_pass_publication_probe.py
```

- [ ] **Step 5: Confirm no curated evidence or raw artifacts are included**

Run:

```powershell
cd C:\Users\bring\.config\superpowers\worktrees\Rook\lm5s-pass1-disposition-semantics
git status --short --ignored
git diff --name-only --cached
```

Expected:

```text
probe_runs/ may appear as ignored
no probe_runs/ path appears in cached files
no docs/superpowers/probes/*.md file appears in diff or cached files
```

- [ ] **Step 6: Commit plan file if not already committed**

If the plan file is uncommitted, run:

```powershell
git add docs\superpowers\plans\2026-07-04-lm5s-pass1-disposition-semantics.md
git commit -m "docs(lm5s): plan pass-one disposition semantics"
```

If the plan file is already committed before implementation starts, skip this
step and report the existing commit.

## Task 6: Manual Canonical LM5S Evidence Run After Merge

**Files:**
- Read local evidence only under: `probe_runs/`

This task is not part of the implementation PR gate. Run it only after LM5S is
merged to main and deterministic gates have passed.

- [ ] **Step 1: Confirm clean synced main**

Run:

```powershell
cd C:\UDEV\Rook
git status --short --branch
git rev-parse --short HEAD origin/main
```

Expected: tracked state is clean except known unrelated untracked files, and
`HEAD` matches `origin/main` after the LM5S merge commit.

- [ ] **Step 2: Confirm Ollama model availability**

Run:

```powershell
ollama --version
ollama show gemma4:12b-it-qat
```

Expected: `ollama show` exits 0. If it fails, stop and report the exact failure.

- [ ] **Step 3: Run canonical LM5S live probe**

Run:

```powershell
cd C:\UDEV\Rook
.\mcp_server\.venv\Scripts\python.exe scripts\lm5r_two_pass_publication_probe.py `
  --model "gemma4:12b-it-qat" `
  --scenario evidence_absent_like `
  --scenario evidence_present_like `
  --attempts 5 `
  --excerpt-chars 1200
```

Expected: script writes a local ignored run directory:

```text
probe_runs/lm5r-<timestamp>-<sha>/
  manifest.json
  attempts.jsonl
  summary.json
```

- [ ] **Step 4: Report evidence without writing a curated doc**

Report:

```text
run directory
manifest git commit
pass1_decision_instruction_version
pass1_decision_instruction_sha256
status counts
pass1 kind counts by scenario
pass2 kind counts by scenario
published count
LM5G-loadable count
observation_action_intent_anomaly_count by scenario
observation_action_intent_reason_counts by scenario
bounded excerpts for any anomalous observation rows
```

Do not commit `probe_runs/`. Do not update
`docs/superpowers/probes/2026-07-02-lm5k-first-worker-model-probe.md` until the
local evidence results are reviewed.

## Final Review Notes

Do not merge a branch that changes any production `mcp_server/src` file. LM5S is
a diagnostic script/test/docs slice only.

Do not change the pass-2 formatter prompt. If a reviewer asks for pass-2 wording
changes, make that a separate slice because it changes the publication
mechanics.

Do not add generic action-intent language classification. LM5S detects only
allowed-action-id leakage from parsed observation objects.
