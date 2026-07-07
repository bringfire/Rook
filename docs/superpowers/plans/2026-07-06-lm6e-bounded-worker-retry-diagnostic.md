# LM6E Bounded Worker Retry Diagnostic Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a CLI-gated, exactly-once LM6A retry for clean observation dispositions and a CLI-gated LM6C pass-through/reporting path.

**Architecture:** LM6A owns the diagnostic retry policy inside one live splice attempt; LM6C remains the scheduler and only passes the retry flag through. The shared two-pass helper stays unchanged; retry is modeled by adding one bounded retry-context packet to the second LM6A request payload and writing ordered publication-row artifacts.

**Tech Stack:** Python 3.10, pytest, direct Ollama helper already in `scripts/lm_worker_two_pass_publication.py`, JSON artifacts under ignored `probe_runs/`.

---

## File Structure

Modify only these implementation files:

- `scripts/lm6a_live_worker_splice_probe.py`
  - Add `--retry-clean-observation`, default off.
  - Add script-local retry eligibility, retry-context packet, retry request payload copy, ordered publication-row artifacts, and retry metadata in `decision.json`.
  - Preserve the existing no-retry behavior when the flag is absent.

- `scripts/lm6c_repeatability_probe.py`
  - Add `--lm6a-retry-clean-observation`, default off.
  - Pass the flag to child LM6A commands only when enabled.
  - Copy retry metadata from child `decision.json` into attempt rows.
  - Add backward-compatible retry summary counts without changing terminal accounting.

- `mcp_server/tests/test_lm6a_live_worker_splice_probe.py`
  - Add deterministic fake-only tests for LM6A retry helpers and full-flow retry outcomes.

- `mcp_server/tests/test_lm6c_repeatability_probe.py`
  - Add deterministic fake-only tests for pass-through, metadata copy, manifest, and summary fields.

Do not modify:

- `scripts/lm_worker_two_pass_publication.py`
- `mcp_server/src/**`
- acceptance-criteria assembler/extractor modules
- worker-action applier
- prompt text or pass-two formatter text
- raw `probe_runs/`

---

### Task 1: Add LM6A Retry CLI and Decision Defaults

**Files:**
- Modify: `scripts/lm6a_live_worker_splice_probe.py`
- Test: `mcp_server/tests/test_lm6a_live_worker_splice_probe.py`

- [ ] **Step 1: Add failing tests for the retry flag and retry metadata defaults**

Add these tests near the existing CLI and decision-record tests:

```python
def test_cli_retry_clean_observation_default_off() -> None:
    args = PROBE._args([])

    assert args.retry_clean_observation is False


def test_cli_retry_clean_observation_flag() -> None:
    args = PROBE._args(["--retry-clean-observation"])

    assert args.retry_clean_observation is True


def test_decision_record_includes_retry_defaults() -> None:
    decision = PROBE._decision_record(
        decision="worker_declined",
        reason="worker_observed",
        phase="worker_publication",
    )

    assert decision["retry_attempted"] is False
    assert decision["retry_count"] == 0
    assert decision["retry_eligibility_reason"] is None
    assert decision["first_worker_response_kind"] is None
    assert decision["first_worker_decline_reason"] is None
    assert decision["final_worker_response_kind"] is None
```

- [ ] **Step 2: Run the new tests and verify they fail**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm6a_live_worker_splice_probe.py::test_cli_retry_clean_observation_default_off `
  mcp_server\tests\test_lm6a_live_worker_splice_probe.py::test_cli_retry_clean_observation_flag `
  mcp_server\tests\test_lm6a_live_worker_splice_probe.py::test_decision_record_includes_retry_defaults `
  -q
```

Expected: failures because `retry_clean_observation` and retry default fields do not exist.

- [ ] **Step 3: Add the LM6A CLI flag**

In `scripts/lm6a_live_worker_splice_probe.py`, update `_args(...)`:

```python
    parser.add_argument(
        "--retry-clean-observation",
        action="store_true",
        help=(
            "Diagnostic LM6E mode: retry exactly once after a clean observation "
            "disposition. Default is off."
        ),
    )
```

- [ ] **Step 4: Add retry metadata defaults to `_decision_record(...)`**

Update `_decision_record(...)` before the returned dict:

```python
    extra.setdefault("retry_attempted", False)
    extra.setdefault("retry_count", 0)
    extra.setdefault("retry_eligibility_reason", None)
    extra.setdefault("first_worker_response_kind", None)
    extra.setdefault("first_worker_decline_reason", None)
    extra.setdefault("final_worker_response_kind", None)
```

The returned object remains:

```python
    return {
        "schema": "rook.lm6a_decision:v1",
        "decision": decision,
        "reason": reason,
        "phase": phase,
        "live_repair_dispatched": live_repair_dispatched,
        "verify_repair_ran": verify_repair_ran,
        **extra,
    }
```

- [ ] **Step 5: Pass the retry flag through `main(...)` to `_run_probe(...)`**

Update `_run_probe(...)` signature:

```python
def _run_probe(
    *,
    phase: str,
    model: str,
    endpoint: str,
    temperature: float,
    timeout_s: float,
    excerpt_chars: int,
    run_root: str | Path,
    agent: Any,
    retry_clean_observation: bool = False,
) -> Path:
```

Update the `main(...)` call:

```python
        retry_clean_observation=args.retry_clean_observation,
```

Existing tests that call `_run_probe(...)` do not need to pass the argument because the default is `False`.

- [ ] **Step 6: Run the focused tests and verify they pass**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm6a_live_worker_splice_probe.py::test_cli_retry_clean_observation_default_off `
  mcp_server\tests\test_lm6a_live_worker_splice_probe.py::test_cli_retry_clean_observation_flag `
  mcp_server\tests\test_lm6a_live_worker_splice_probe.py::test_decision_record_includes_retry_defaults `
  -q
```

Expected: `3 passed`.

---

### Task 2: Add LM6A Retry Helper Functions

**Files:**
- Modify: `scripts/lm6a_live_worker_splice_probe.py`
- Test: `mcp_server/tests/test_lm6a_live_worker_splice_probe.py`

- [ ] **Step 1: Add failing tests for row tagging, eligibility, retry context, and payload copying**

Add these tests after the `_published_payload(...)` helper:

```python
def test_publication_row_for_turn_copies_and_tags_row() -> None:
    original = {"status": "published"}

    tagged = PROBE._publication_row_for_turn(
        original,
        turn_index=1,
        turn_role="initial",
        retry_context_present=False,
    )

    assert tagged == {
        "status": "published",
        "turn_index": 1,
        "turn_role": "initial",
        "retry_context_present": False,
    }
    assert original == {"status": "published"}


def test_retry_eligibility_allows_clean_observation() -> None:
    reason = PROBE._retry_eligibility_reason(
        publication_row={
            "status": "published",
            "observation_action_intent_anomaly": False,
        },
        response_payload=_published_payload(
            "observation",
            message="Visible state.",
            data=None,
        ),
    )

    assert reason is None


def test_retry_eligibility_rejects_non_observation_and_anomaly() -> None:
    assert PROBE._retry_eligibility_reason(
        publication_row={
            "status": "published",
            "observation_action_intent_anomaly": False,
        },
        response_payload=_published_payload(
            "clarification_request",
            question="Need desired value?",
            rationale=None,
        ),
    ) == "not_retry_eligible:kind_clarification_request"

    assert PROBE._retry_eligibility_reason(
        publication_row={
            "status": "published",
            "observation_action_intent_anomaly": True,
        },
        response_payload=_published_payload("observation", message="x", data=None),
    ) == "not_retry_eligible:observation_action_intent_anomaly"


def test_retry_context_packet_is_bounded_and_factual() -> None:
    response = _published_payload(
        "observation",
        message="Observation " + ("x" * 50),
        data=None,
    )

    packet = PROBE._retry_context_packet(
        previous_response_payload=response,
        previous_reason="worker_observed",
        excerpt_chars=20,
    )

    assert packet["packet_id"] == "lm6e_bounded_retry_context"
    assert packet["kind"] == "retry_context"
    fields = packet["fields"]
    assert fields["retry_count"] == 1
    assert fields["max_retries"] == 1
    assert fields["previous_response_kind"] == "observation"
    assert fields["previous_response_reason"] == "worker_observed"
    assert fields["previous_observation_message_excerpt"].startswith("Observation ")
    assert len(fields["previous_observation_message_excerpt"]) == 20
    assert fields["previous_observation_message_sha256"].startswith("sha256:")
    assert "A = 42.0" not in json.dumps(packet, sort_keys=True)
    assert "PROBE_REPAIR_CODE" not in json.dumps(packet, sort_keys=True)


def test_request_payload_with_retry_context_appends_packet_without_mutation() -> None:
    payload = {
        "schema": "demo",
        "context": {
            "knowledge": [
                {"packet_id": "script_body_gotcha", "kind": "gotcha"},
            ],
            "allowed_actions": [{"action_id": "draft_repair_params"}],
        },
    }
    packet = {"packet_id": "lm6e_bounded_retry_context", "kind": "retry_context"}

    retry_payload = PROBE._request_payload_with_retry_context(payload, packet)

    assert retry_payload is not payload
    assert retry_payload["context"] is not payload["context"]
    assert retry_payload["context"]["knowledge"] == [
        {"packet_id": "script_body_gotcha", "kind": "gotcha"},
        {"packet_id": "lm6e_bounded_retry_context", "kind": "retry_context"},
    ]
    assert payload["context"]["knowledge"] == [
        {"packet_id": "script_body_gotcha", "kind": "gotcha"},
    ]
```

- [ ] **Step 2: Run helper tests and verify they fail**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm6a_live_worker_splice_probe.py::test_publication_row_for_turn_copies_and_tags_row `
  mcp_server\tests\test_lm6a_live_worker_splice_probe.py::test_retry_eligibility_allows_clean_observation `
  mcp_server\tests\test_lm6a_live_worker_splice_probe.py::test_retry_eligibility_rejects_non_observation_and_anomaly `
  mcp_server\tests\test_lm6a_live_worker_splice_probe.py::test_retry_context_packet_is_bounded_and_factual `
  mcp_server\tests\test_lm6a_live_worker_splice_probe.py::test_request_payload_with_retry_context_appends_packet_without_mutation `
  -q
```

Expected: failures because the helper functions do not exist.

- [ ] **Step 3: Add row tagging and observation message helpers**

Add these helpers above `_decision_from_worker_publication(...)`:

```python
def _publication_row_for_turn(
    row: Mapping[str, Any],
    *,
    turn_index: int,
    turn_role: str,
    retry_context_present: bool,
) -> dict[str, Any]:
    tagged = dict(row)
    tagged["turn_index"] = turn_index
    tagged["turn_role"] = turn_role
    tagged["retry_context_present"] = retry_context_present
    return tagged


def _observation_message(response_payload: Mapping[str, Any] | None) -> str:
    if not isinstance(response_payload, Mapping):
        return ""
    message = response_payload.get("message")
    return message if isinstance(message, str) else ""
```

- [ ] **Step 4: Add retry eligibility helper**

Add:

```python
def _retry_eligibility_reason(
    *,
    publication_row: Mapping[str, Any],
    response_payload: Mapping[str, Any] | None,
) -> str | None:
    status = publication_row.get("status")
    if status != "published":
        return f"not_retry_eligible:status_{status}"
    if not isinstance(response_payload, Mapping):
        return "not_retry_eligible:no_response_payload"
    kind = response_payload.get("kind")
    if kind != "observation":
        return f"not_retry_eligible:kind_{kind}"
    if publication_row.get("observation_action_intent_anomaly") is True:
        return "not_retry_eligible:observation_action_intent_anomaly"
    return None
```

- [ ] **Step 5: Add retry-context packet helper**

Add:

```python
def _retry_context_packet(
    *,
    previous_response_payload: Mapping[str, Any],
    previous_reason: str,
    excerpt_chars: int,
) -> dict[str, Any]:
    message = _observation_message(previous_response_payload)
    message_sha = hashlib.sha256(message.encode("utf-8")).hexdigest()
    return {
        "packet_id": "lm6e_bounded_retry_context",
        "kind": "retry_context",
        "fields": {
            "retry_count": 1,
            "max_retries": 1,
            "previous_response_kind": "observation",
            "previous_response_reason": previous_reason,
            "previous_observation_message_excerpt": message[:excerpt_chars],
            "previous_observation_message_sha256": f"sha256:{message_sha}",
            "instruction": (
                "Re-evaluate the same request after your prior observation. "
                "If the visible acceptance criteria are sufficient to draft "
                "repair parameters, publish action_request. If they are still "
                "insufficient, publish observation again."
            ),
        },
    }
```

- [ ] **Step 6: Add retry request payload copy helper**

Add:

```python
def _request_payload_with_retry_context(
    request_payload: Mapping[str, Any],
    retry_packet: Mapping[str, Any],
) -> dict[str, Any]:
    copied = json.loads(json.dumps(request_payload, default=str))
    context = copied.get("context")
    if not isinstance(context, dict):
        raise ValueError("request payload context missing")
    knowledge = context.get("knowledge")
    if not isinstance(knowledge, list):
        raise ValueError("request payload context knowledge missing")
    knowledge.append(dict(retry_packet))
    return copied
```

- [ ] **Step 7: Run helper tests and verify they pass**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm6a_live_worker_splice_probe.py::test_publication_row_for_turn_copies_and_tags_row `
  mcp_server\tests\test_lm6a_live_worker_splice_probe.py::test_retry_eligibility_allows_clean_observation `
  mcp_server\tests\test_lm6a_live_worker_splice_probe.py::test_retry_eligibility_rejects_non_observation_and_anomaly `
  mcp_server\tests\test_lm6a_live_worker_splice_probe.py::test_retry_context_packet_is_bounded_and_factual `
  mcp_server\tests\test_lm6a_live_worker_splice_probe.py::test_request_payload_with_retry_context_appends_packet_without_mutation `
  -q
```

Expected: `5 passed`.

---

### Task 3: Preserve No-Retry Behavior and Add Publication-Row List Artifacts

**Files:**
- Modify: `scripts/lm6a_live_worker_splice_probe.py`
- Test: `mcp_server/tests/test_lm6a_live_worker_splice_probe.py`

- [ ] **Step 1: Add failing tests that no-retry writes a single ordered row and final compatibility row**

Add this test near the existing full-flow tests:

```python
def test_full_flow_no_retry_writes_single_publication_rows_artifact(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        PROBE,
        "_run_phase_a_recon",
        lambda **kwargs: {
            "decision": None,
            "request_payload": {"context": {"allowed_actions": [], "knowledge": []}},
        },
    )
    monkeypatch.setattr(
        PROBE,
        "run_two_pass_worker_publication",
        lambda *args, **kwargs: type(
            "Result",
            (),
            {
                "row": {
                    "status": "published",
                    "observation_action_intent_anomaly": False,
                },
                "response_payload": {
                    "schema": "rook.local_worker_turn_response:v1",
                    "kind": "observation",
                    "message": "No action.",
                    "data": None,
                },
            },
        )(),
    )

    run_dir = PROBE._run_probe(
        phase="full",
        model="gemma4:12b-it-qat",
        endpoint="http://fake.local/api/chat",
        temperature=0,
        timeout_s=9,
        excerpt_chars=500,
        run_root=tmp_path,
        agent=None,
    )

    rows = json.loads((run_dir / "worker_publication_rows.json").read_text())
    final_row = json.loads((run_dir / "worker_publication_row.json").read_text())
    decision = json.loads((run_dir / "decision.json").read_text())
    assert len(rows) == 1
    assert rows[0]["turn_index"] == 1
    assert rows[0]["turn_role"] == "initial"
    assert rows[0]["retry_context_present"] is False
    assert final_row == rows[0]
    assert decision["decision"] == "worker_declined"
    assert decision["reason"] == "worker_observed"
    assert decision["retry_attempted"] is False
    assert decision["retry_count"] == 0
```

- [ ] **Step 2: Run the artifact test and verify it fails**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm6a_live_worker_splice_probe.py::test_full_flow_no_retry_writes_single_publication_rows_artifact `
  -q
```

Expected: failure because `worker_publication_rows.json` does not exist.

- [ ] **Step 3: Add a list-capable JSON artifact writer**

Add this helper below `_write_json(...)`:

```python
def _write_json_value(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
```

Keep `_write_json(...)` unchanged for mapping-shaped artifacts.

- [ ] **Step 4: Update `_run_probe(...)` first publication path to tag and write rows**

In `_run_probe(...)`, after the first `run_two_pass_worker_publication(...)`, replace direct use of `publication.row` with a tagged row:

```python
    publication_rows: list[dict[str, Any]] = []
    first_row = _publication_row_for_turn(
        publication.row,
        turn_index=1,
        turn_role="initial",
        retry_context_present=False,
    )
    publication_rows.append(first_row)
```

Use `first_row` for hidden-answer scanning and decision classification:

```python
    if _hidden_answer_leaks(first_row):
        decision = _decision_record(
            decision="publication_failed",
            reason="worker_publication_hidden_answer_leak",
            phase="worker_publication",
        )
        _write_json(run_dir / "decision.json", decision)
        return run_dir
```

When no hidden leak blocks row writing, write both artifacts:

```python
    _write_json_value(run_dir / "worker_publication_rows.json", publication_rows)
    _write_json(run_dir / "worker_publication_row.json", first_row)
```

Use the first row for non-action decision:

```python
    decision = _decision_from_worker_publication(
        publication_row=first_row,
        response_payload=publication.response_payload,
    )
```

This preserves the locked artifact shape: `worker_publication_rows.json` is an ordered JSON list.

- [ ] **Step 5: Update existing hidden-leak test expectation**

The existing `test_full_flow_publication_row_hidden_answer_leak_stops_before_artifact` should continue to assert:

```python
    assert not (run_dir / "worker_publication_row.json").exists()
    assert not (run_dir / "worker_publication_rows.json").exists()
```

This preserves the spec rule that a first-turn hidden-answer leak terminates on the existing no-retry path before row artifacts are published.

- [ ] **Step 6: Add first-turn response-payload leak regression**

Add:

```python
def test_full_flow_publication_response_hidden_answer_leak_stops_without_retry(
    monkeypatch,
    tmp_path: Path,
) -> None:
    calls = []

    def fake_publication(request_payload, **kwargs):
        calls.append(request_payload)
        return type(
            "Result",
            (),
            {
                "row": {
                    "status": "published",
                    "observation_action_intent_anomaly": False,
                },
                "response_payload": {
                    "schema": "rook.local_worker_turn_response:v1",
                    "kind": "observation",
                    "message": "hidden A = 42.0;",
                    "data": None,
                },
            },
        )()

    monkeypatch.setattr(
        PROBE,
        "_run_phase_a_recon",
        lambda **kwargs: {
            "decision": None,
            "request_payload": {"context": {"allowed_actions": [], "knowledge": []}},
        },
    )
    monkeypatch.setattr(PROBE, "run_two_pass_worker_publication", fake_publication)

    run_dir = PROBE._run_probe(
        phase="full",
        model="gemma4:12b-it-qat",
        endpoint="http://fake.local/api/chat",
        temperature=0,
        timeout_s=9,
        excerpt_chars=500,
        run_root=tmp_path,
        agent=None,
        retry_clean_observation=True,
    )

    decision = json.loads((run_dir / "decision.json").read_text())
    assert decision["decision"] == "publication_failed"
    assert decision["reason"] == "worker_publication_hidden_answer_leak"
    assert decision["retry_attempted"] is False
    assert decision["retry_count"] == 0
    assert len(calls) == 1
    assert not (run_dir / "worker_publication_row.json").exists()
    assert not (run_dir / "worker_publication_rows.json").exists()
```

- [ ] **Step 7: Guard first-turn response payload leaks before writing row artifacts**

In `_run_probe(...)`, after `first_row` is created and before `worker_publication_rows.json` or `worker_publication_row.json` is written, check both the first row and first response payload:

```python
    if _hidden_answer_leaks(first_row) or _hidden_answer_leaks(
        publication.response_payload
    ):
        decision = _decision_record(
            decision="publication_failed",
            reason="worker_publication_hidden_answer_leak",
            phase="worker_publication",
        )
        _write_json(run_dir / "decision.json", decision)
        return run_dir
```

Remove the older row-only hidden-answer check so the reason remains single and stable.

- [ ] **Step 8: Run focused LM6A tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm6a_live_worker_splice_probe.py::test_full_flow_no_retry_writes_single_publication_rows_artifact `
  mcp_server\tests\test_lm6a_live_worker_splice_probe.py::test_full_flow_publication_row_hidden_answer_leak_stops_before_artifact `
  mcp_server\tests\test_lm6a_live_worker_splice_probe.py::test_full_flow_publication_response_hidden_answer_leak_stops_without_retry `
  -q
```

Expected: `3 passed`.

---

### Task 4: Implement LM6A Observation Retry Outcomes

**Files:**
- Modify: `scripts/lm6a_live_worker_splice_probe.py`
- Test: `mcp_server/tests/test_lm6a_live_worker_splice_probe.py`

- [ ] **Step 1: Add failing test for retry recovery to action and accepted decision metadata**

Add this test near the full-flow tests:

```python
def test_full_flow_retry_observation_recovers_action_and_accepts(
    monkeypatch,
    tmp_path: Path,
) -> None:
    calls = []

    class _ApplyResult:
        applied = True
        reason = None
        params_sha256 = "params-sha"
        graph = object()

    def fake_publication(request_payload, **kwargs):
        calls.append(request_payload)
        if len(calls) == 1:
            return type(
                "Result",
                (),
                {
                    "row": {
                        "status": "published",
                        "observation_action_intent_anomaly": False,
                    },
                    "response_payload": {
                        "schema": "rook.local_worker_turn_response:v1",
                        "kind": "observation",
                        "message": "I see the acceptance criteria.",
                        "data": None,
                    },
                },
            )()
        return type(
            "Result",
            (),
            {
                "row": {
                    "status": "published",
                    "observation_action_intent_anomaly": False,
                },
                "response_payload": {
                    "schema": "rook.local_worker_turn_response:v1",
                    "kind": "action_request",
                    "action_id": "draft_repair_params",
                    "rationale": "Retry action.",
                    "input": {"code": "A = 0.0;", "mode": "body"},
                },
            },
        )()

    monkeypatch.setattr(
        PROBE,
        "_run_phase_a_recon",
        lambda **kwargs: {
            "decision": None,
            "graph": object(),
            "anchor_binding": {"component_guid": "GUID-1", "language": "csharp"},
            "request_payload": {"context": {"allowed_actions": [], "knowledge": []}},
        },
    )
    monkeypatch.setattr(PROBE, "run_two_pass_worker_publication", fake_publication)
    monkeypatch.setattr(
        PROBE,
        "apply_worker_action_to_node",
        lambda *args, **kwargs: _ApplyResult(),
    )
    monkeypatch.setattr(
        PROBE,
        "_dispatch_repair_and_verify",
        lambda **kwargs: {
            "decision": PROBE._decision_record(
                decision="accepted",
                reason="verify_repair_succeeded",
                phase="verify_repair",
                live_repair_dispatched=True,
                verify_repair_ran=True,
                **kwargs["action_context"],
            )
        },
    )

    run_dir = PROBE._run_probe(
        phase="full",
        model="gemma4:12b-it-qat",
        endpoint="http://fake.local/api/chat",
        temperature=0,
        timeout_s=9,
        excerpt_chars=500,
        run_root=tmp_path,
        agent=None,
        retry_clean_observation=True,
    )

    assert len(calls) == 2
    assert calls[0]["context"]["knowledge"] == []
    assert calls[1]["context"]["knowledge"][0]["packet_id"] == (
        "lm6e_bounded_retry_context"
    )
    rows = json.loads((run_dir / "worker_publication_rows.json").read_text())
    final_row = json.loads((run_dir / "worker_publication_row.json").read_text())
    decision = json.loads((run_dir / "decision.json").read_text())
    assert [row["turn_role"] for row in rows] == ["initial", "retry"]
    assert rows[1]["retry_context_present"] is True
    assert final_row == rows[1]
    assert (run_dir / "retry_context.json").exists()
    assert (run_dir / "worker_action.json").exists()
    assert decision["decision"] == "accepted"
    assert decision["retry_attempted"] is True
    assert decision["retry_count"] == 1
    assert decision["first_worker_response_kind"] == "observation"
    assert decision["first_worker_decline_reason"] == "worker_observed"
    assert decision["final_worker_response_kind"] == "action_request"
```

- [ ] **Step 2: Add failing tests for retry observation, retry anomaly, and retry publication failure**

Add:

```python
def test_full_flow_retry_observation_declines_with_retry_reason(
    monkeypatch,
    tmp_path: Path,
) -> None:
    calls = []

    def fake_publication(request_payload, **kwargs):
        calls.append(request_payload)
        return type(
            "Result",
            (),
            {
                "row": {
                    "status": "published",
                    "observation_action_intent_anomaly": False,
                },
                "response_payload": {
                    "schema": "rook.local_worker_turn_response:v1",
                    "kind": "observation",
                    "message": f"Observation {len(calls)}.",
                    "data": None,
                },
            },
        )()

    monkeypatch.setattr(
        PROBE,
        "_run_phase_a_recon",
        lambda **kwargs: {
            "decision": None,
            "request_payload": {"context": {"allowed_actions": [], "knowledge": []}},
        },
    )
    monkeypatch.setattr(PROBE, "run_two_pass_worker_publication", fake_publication)

    run_dir = PROBE._run_probe(
        phase="full",
        model="gemma4:12b-it-qat",
        endpoint="http://fake.local/api/chat",
        temperature=0,
        timeout_s=9,
        excerpt_chars=500,
        run_root=tmp_path,
        agent=None,
        retry_clean_observation=True,
    )

    decision = json.loads((run_dir / "decision.json").read_text())
    assert decision["decision"] == "worker_declined"
    assert decision["reason"] == "worker_observed_after_retry"
    assert decision["retry_attempted"] is True
    assert decision["retry_count"] == 1
    assert decision["first_worker_response_kind"] == "observation"
    assert decision["final_worker_response_kind"] == "observation"
    assert len(calls) == 2


def test_full_flow_retry_observation_anomaly_declines_with_retry_reason(
    monkeypatch,
    tmp_path: Path,
) -> None:
    calls = []

    def fake_publication(request_payload, **kwargs):
        calls.append(request_payload)
        anomaly = len(calls) == 2
        return type(
            "Result",
            (),
            {
                "row": {
                    "status": "published",
                    "observation_action_intent_anomaly": anomaly,
                    "observation_action_intent_reasons": (
                        ["observation_data_action_id_allowed"] if anomaly else []
                    ),
                },
                "response_payload": {
                    "schema": "rook.local_worker_turn_response:v1",
                    "kind": "observation",
                    "message": "Observation.",
                    "data": None,
                },
            },
        )()

    monkeypatch.setattr(
        PROBE,
        "_run_phase_a_recon",
        lambda **kwargs: {
            "decision": None,
            "request_payload": {"context": {"allowed_actions": [], "knowledge": []}},
        },
    )
    monkeypatch.setattr(PROBE, "run_two_pass_worker_publication", fake_publication)

    run_dir = PROBE._run_probe(
        phase="full",
        model="gemma4:12b-it-qat",
        endpoint="http://fake.local/api/chat",
        temperature=0,
        timeout_s=9,
        excerpt_chars=500,
        run_root=tmp_path,
        agent=None,
        retry_clean_observation=True,
    )

    decision = json.loads((run_dir / "decision.json").read_text())
    assert decision["decision"] == "worker_declined"
    assert decision["reason"] == "worker_observation_action_intent_anomaly_after_retry"
    assert decision["retry_attempted"] is True
    assert decision["retry_count"] == 1
    assert decision["final_worker_response_kind"] == "observation"


def test_full_flow_retry_publication_failure_maps_to_publication_failed(
    monkeypatch,
    tmp_path: Path,
) -> None:
    calls = []

    def fake_publication(request_payload, **kwargs):
        calls.append(request_payload)
        if len(calls) == 1:
            return type(
                "Result",
                (),
                {
                    "row": {
                        "status": "published",
                        "observation_action_intent_anomaly": False,
                    },
                    "response_payload": {
                        "schema": "rook.local_worker_turn_response:v1",
                        "kind": "observation",
                        "message": "Observation.",
                        "data": None,
                    },
                },
            )()
        return type(
            "Result",
            (),
            {
                "row": {
                    "status": "pass2_lm5g_invalid",
                    "failure_reason": "pass2_content_json_invalid:RecursionError",
                },
                "response_payload": None,
            },
        )()

    monkeypatch.setattr(
        PROBE,
        "_run_phase_a_recon",
        lambda **kwargs: {
            "decision": None,
            "request_payload": {"context": {"allowed_actions": [], "knowledge": []}},
        },
    )
    monkeypatch.setattr(PROBE, "run_two_pass_worker_publication", fake_publication)

    run_dir = PROBE._run_probe(
        phase="full",
        model="gemma4:12b-it-qat",
        endpoint="http://fake.local/api/chat",
        temperature=0,
        timeout_s=9,
        excerpt_chars=500,
        run_root=tmp_path,
        agent=None,
        retry_clean_observation=True,
    )

    decision = json.loads((run_dir / "decision.json").read_text())
    assert decision["decision"] == "publication_failed"
    assert decision["reason"] == (
        "retry_publication_failed:pass2_content_json_invalid:RecursionError"
    )
    assert decision["retry_attempted"] is True
    assert decision["retry_count"] == 1
    assert decision["final_worker_response_kind"] is None
    assert not (run_dir / "worker_action.json").exists()
```

- [ ] **Step 3: Add failing test for retry-turn hidden-answer leak**

Add:

```python
def test_full_flow_retry_publication_hidden_answer_leak_stops_without_dispatch(
    monkeypatch,
    tmp_path: Path,
) -> None:
    calls = []

    def fake_publication(request_payload, **kwargs):
        calls.append(request_payload)
        if len(calls) == 1:
            return type(
                "Result",
                (),
                {
                    "row": {
                        "status": "published",
                        "observation_action_intent_anomaly": False,
                    },
                    "response_payload": {
                        "schema": "rook.local_worker_turn_response:v1",
                        "kind": "observation",
                        "message": "Observation.",
                        "data": None,
                    },
                },
            )()
        return type(
            "Result",
            (),
            {
                "row": {
                    "status": "published",
                    "pass2_content_excerpt": "bad A = 42.0;",
                },
                "response_payload": None,
            },
        )()

    monkeypatch.setattr(
        PROBE,
        "_run_phase_a_recon",
        lambda **kwargs: {
            "decision": None,
            "request_payload": {"context": {"allowed_actions": [], "knowledge": []}},
        },
    )
    monkeypatch.setattr(PROBE, "run_two_pass_worker_publication", fake_publication)

    run_dir = PROBE._run_probe(
        phase="full",
        model="gemma4:12b-it-qat",
        endpoint="http://fake.local/api/chat",
        temperature=0,
        timeout_s=9,
        excerpt_chars=500,
        run_root=tmp_path,
        agent=None,
        retry_clean_observation=True,
    )

    decision = json.loads((run_dir / "decision.json").read_text())
    assert decision["decision"] == "publication_failed"
    assert decision["reason"] == "retry_worker_publication_hidden_answer_leak"
    assert decision["retry_attempted"] is True
    assert decision["retry_count"] == 1
    assert decision["live_repair_dispatched"] is False
    rows = json.loads((run_dir / "worker_publication_rows.json").read_text())
    final_row = json.loads((run_dir / "worker_publication_row.json").read_text())
    assert len(rows) == 1
    assert rows[0]["turn_role"] == "initial"
    assert final_row == rows[0]
    assert "A = 42.0" not in json.dumps(rows, sort_keys=True)
    assert "A = 42.0" not in json.dumps(final_row, sort_keys=True)
    assert not (run_dir / "worker_action.json").exists()
```

- [ ] **Step 4: Run retry full-flow tests and verify they fail**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm6a_live_worker_splice_probe.py::test_full_flow_retry_observation_recovers_action_and_accepts `
  mcp_server\tests\test_lm6a_live_worker_splice_probe.py::test_full_flow_retry_observation_declines_with_retry_reason `
  mcp_server\tests\test_lm6a_live_worker_splice_probe.py::test_full_flow_retry_observation_anomaly_declines_with_retry_reason `
  mcp_server\tests\test_lm6a_live_worker_splice_probe.py::test_full_flow_retry_publication_failure_maps_to_publication_failed `
  mcp_server\tests\test_lm6a_live_worker_splice_probe.py::test_full_flow_retry_publication_hidden_answer_leak_stops_without_dispatch `
  -q
```

Expected: failures because `_run_probe(...)` does not perform retry.

- [ ] **Step 5: Add retry metadata helper**

Add:

```python
def _retry_metadata(
    *,
    retry_attempted: bool,
    retry_count: int,
    first_kind: str | None,
    first_reason: str | None,
    final_kind: str | None = None,
    eligibility_reason: str | None = None,
) -> dict[str, Any]:
    return {
        "retry_attempted": retry_attempted,
        "retry_count": retry_count,
        "retry_eligibility_reason": eligibility_reason,
        "first_worker_response_kind": first_kind,
        "first_worker_decline_reason": first_reason,
        "final_worker_response_kind": final_kind,
    }
```

- [ ] **Step 6: Add retry-aware decision wrapper**

Add:

```python
def _decision_with_retry_metadata(
    decision: Mapping[str, Any],
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    merged = dict(decision)
    merged.update(metadata)
    return merged
```

- [ ] **Step 7: Implement retry branch inside `_run_probe(...)`**

In `_run_probe(...)`, after the first non-action `decision = _decision_from_worker_publication(...)`, add this branch before writing a terminal non-action decision:

```python
    if decision is not None:
        eligibility_reason = _retry_eligibility_reason(
            publication_row=first_row,
            response_payload=publication.response_payload,
        )
        first_kind = (
            publication.response_payload.get("kind")
            if isinstance(publication.response_payload, Mapping)
            else None
        )
        first_reason = decision.get("reason") if isinstance(decision, Mapping) else None
        if not retry_clean_observation or eligibility_reason is not None:
            metadata = _retry_metadata(
                retry_attempted=False,
                retry_count=0,
                first_kind=str(first_kind) if first_kind is not None else None,
                first_reason=str(first_reason) if first_reason is not None else None,
                eligibility_reason=(
                    eligibility_reason
                    if retry_clean_observation
                    else "not_retry_enabled"
                ),
                final_kind=str(first_kind) if first_kind is not None else None,
            )
            _write_json(
                run_dir / "decision.json",
                _decision_with_retry_metadata(decision, metadata),
            )
            return run_dir

        retry_packet = _retry_context_packet(
            previous_response_payload=publication.response_payload,
            previous_reason=str(first_reason or "worker_observed"),
            excerpt_chars=excerpt_chars,
        )
        if _hidden_answer_leaks(retry_packet):
            retry_decision = _decision_record(
                decision="publication_failed",
                reason="retry_context_hidden_answer_leak",
                phase="worker_publication",
                **_retry_metadata(
                    retry_attempted=True,
                    retry_count=1,
                    first_kind=str(first_kind) if first_kind is not None else None,
                    first_reason=str(first_reason) if first_reason is not None else None,
                ),
            )
            _write_json(run_dir / "decision.json", retry_decision)
            return run_dir
        _write_json(run_dir / "retry_context.json", retry_packet)
        retry_request_payload = _request_payload_with_retry_context(
            recon["request_payload"],
            retry_packet,
        )
        retry_publication = run_two_pass_worker_publication(
            retry_request_payload,
            model=model,
            endpoint=endpoint,
            temperature=temperature,
            timeout_s=timeout_s,
            excerpt_chars=excerpt_chars,
            decision_guard=_pass1_decision_hidden_answer_failure,
        )
        retry_row = _publication_row_for_turn(
            retry_publication.row,
            turn_index=2,
            turn_role="retry",
            retry_context_present=True,
        )
        retry_metadata = _retry_metadata(
            retry_attempted=True,
            retry_count=1,
            first_kind=str(first_kind) if first_kind is not None else None,
            first_reason=str(first_reason) if first_reason is not None else None,
            final_kind=(
                str(retry_publication.response_payload.get("kind"))
                if isinstance(retry_publication.response_payload, Mapping)
                else None
            ),
        )
        if _hidden_answer_leaks(retry_row) or _hidden_answer_leaks(
            retry_publication.response_payload
        ):
            retry_decision = _decision_record(
                decision="publication_failed",
                reason="retry_worker_publication_hidden_answer_leak",
                phase="worker_publication",
                **retry_metadata,
            )
            _write_json(run_dir / "decision.json", retry_decision)
            return run_dir
        publication_rows.append(retry_row)
        _write_json_value(run_dir / "worker_publication_rows.json", publication_rows)
        _write_json(run_dir / "worker_publication_row.json", retry_row)

        retry_decision = _decision_from_worker_publication(
            publication_row=retry_row,
            response_payload=retry_publication.response_payload,
        )
        if retry_decision is not None:
            retry_reason = retry_decision["reason"]
            if retry_reason == "worker_observed":
                retry_reason = "worker_observed_after_retry"
            elif retry_reason == "worker_observation_action_intent_anomaly":
                retry_reason = "worker_observation_action_intent_anomaly_after_retry"
            elif retry_decision["decision"] == "publication_failed":
                retry_reason = f"retry_publication_failed:{retry_decision['reason']}"
            retry_decision = dict(retry_decision)
            retry_decision["reason"] = retry_reason
            _write_json(
                run_dir / "decision.json",
                _decision_with_retry_metadata(retry_decision, retry_metadata),
            )
            return run_dir

        publication = retry_publication
        response_payload = retry_publication.response_payload
    else:
        response_payload = publication.response_payload
```

Then ensure the action path uses the final `response_payload` variable already set by the branch:

```python
    action_input = response_payload["input"]
```

Before dispatching action, pass retry metadata into `action_context`:

```python
    action_context.update(
        retry_metadata
        if "retry_metadata" in locals()
        else _retry_metadata(
            retry_attempted=False,
            retry_count=0,
            first_kind=response_payload.get("kind"),
            first_reason=None,
            final_kind=response_payload.get("kind"),
        )
    )
```

- [ ] **Step 8: Simplify the action-context metadata so no local variable test is needed**

Replace the `locals()` check from Step 7 with an explicit initialization before publication:

```python
    final_retry_metadata = _retry_metadata(
        retry_attempted=False,
        retry_count=0,
        first_kind=None,
        first_reason=None,
        final_kind=None,
        eligibility_reason=None,
    )
```

When retry is attempted, set:

```python
        final_retry_metadata = retry_metadata
```

For first-turn action, set before `_worker_action_context(...)`:

```python
    if response_payload.get("kind") == "action_request" and not final_retry_metadata[
        "final_worker_response_kind"
    ]:
        final_retry_metadata = _retry_metadata(
            retry_attempted=False,
            retry_count=0,
            first_kind="action_request",
            first_reason=None,
            final_kind="action_request",
            eligibility_reason="not_retry_eligible:kind_action_request",
        )
```

Then after `_worker_action_context(...)`:

```python
    action_context.update(final_retry_metadata)
```

- [ ] **Step 9: Run retry full-flow tests and verify they pass**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm6a_live_worker_splice_probe.py::test_full_flow_retry_observation_recovers_action_and_accepts `
  mcp_server\tests\test_lm6a_live_worker_splice_probe.py::test_full_flow_retry_observation_declines_with_retry_reason `
  mcp_server\tests\test_lm6a_live_worker_splice_probe.py::test_full_flow_retry_observation_anomaly_declines_with_retry_reason `
  mcp_server\tests\test_lm6a_live_worker_splice_probe.py::test_full_flow_retry_publication_failure_maps_to_publication_failed `
  mcp_server\tests\test_lm6a_live_worker_splice_probe.py::test_full_flow_retry_publication_hidden_answer_leak_stops_without_dispatch `
  -q
```

Expected: `5 passed`.

---

### Task 5: Add LM6C Retry Pass-Through and Reporting

**Files:**
- Modify: `scripts/lm6c_repeatability_probe.py`
- Test: `mcp_server/tests/test_lm6c_repeatability_probe.py`

- [ ] **Step 1: Add failing CLI, command, manifest, row, and summary tests**

Add these tests near existing LM6C CLI/summary tests:

```python
def test_cli_retry_pass_through_default_off() -> None:
    args = PROBE._args([])

    assert args.lm6a_retry_clean_observation is False


def test_cli_retry_pass_through_flag() -> None:
    args = PROBE._args(["--lm6a-retry-clean-observation"])

    assert args.lm6a_retry_clean_observation is True


def test_lm6a_command_adds_retry_flag_only_when_enabled(tmp_path: Path) -> None:
    base = PROBE._lm6a_command(
        model="gemma4:12b-it-qat",
        lm6a_runs_dir=tmp_path,
        retry_clean_observation=False,
    )
    retry = PROBE._lm6a_command(
        model="gemma4:12b-it-qat",
        lm6a_runs_dir=tmp_path,
        retry_clean_observation=True,
    )

    assert "--retry-clean-observation" not in base
    assert retry[-1] == "--retry-clean-observation"


def test_manifest_records_retry_pass_through_flag() -> None:
    manifest = PROBE._manifest(
        attempts=5,
        model="gemma4:12b-it-qat",
        lm6a_retry_clean_observation=True,
    )

    assert manifest["lm6a_retry_clean_observation"] is True


def test_attempt_row_copies_retry_metadata_from_lm6a_decision(tmp_path: Path) -> None:
    child = tmp_path / "lm6a_runs" / "lm6a-child"
    child.mkdir(parents=True)
    (child / "decision.json").write_text(
        json.dumps(
            {
                "decision": "accepted",
                "reason": "verify_repair_succeeded",
                "retry_attempted": True,
                "retry_count": 1,
                "first_worker_response_kind": "observation",
                "final_worker_response_kind": "action_request",
            }
        ),
        encoding="utf-8",
    )
    completed = subprocess.CompletedProcess(
        args=["python"],
        returncode=0,
        stdout="done",
        stderr="",
    )

    row = PROBE._row_from_completed_lm6a(
        attempt_index=1,
        completed=completed,
        child_run_dir=child,
    )

    assert row["terminal_category"] == "accepted"
    assert row["retry_attempted"] is True
    assert row["retry_count"] == 1
    assert row["first_worker_response_kind"] == "observation"
    assert row["final_worker_response_kind"] == "action_request"


def test_build_summary_adds_retry_report_counts() -> None:
    rows = [
        {
            **PROBE._base_attempt_row(attempt_index=1),
            "terminal_category": "accepted",
            "retry_attempted": True,
            "retry_count": 1,
            "final_worker_response_kind": "action_request",
        },
        {
            **PROBE._base_attempt_row(attempt_index=2),
            "terminal_category": "worker_declined",
            "retry_attempted": True,
            "retry_count": 1,
            "final_worker_response_kind": "observation",
        },
        {
            **PROBE._base_attempt_row(attempt_index=3),
            "terminal_category": "publication_failed",
            "retry_attempted": True,
            "retry_count": 1,
            "final_worker_response_kind": None,
        },
        {
            **PROBE._base_attempt_row(attempt_index=4),
            "terminal_category": "accepted",
            "retry_attempted": False,
            "retry_count": 0,
            "final_worker_response_kind": "action_request",
        },
    ]

    summary = PROBE._build_summary(
        rows,
        attempts=4,
        model="gemma4:12b-it-qat",
    )

    assert summary["retry_attempted_count"] == 3
    assert summary["retry_recovered_count"] == 1
    assert summary["retry_declined_count"] == 1
    assert summary["retry_publication_failed_count"] == 1
    assert summary["terminal_category_counts"] == {
        "accepted": 2,
        "publication_failed": 1,
        "worker_declined": 1,
    }
```

- [ ] **Step 2: Run new LM6C tests and verify they fail**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm6c_repeatability_probe.py::test_cli_retry_pass_through_default_off `
  mcp_server\tests\test_lm6c_repeatability_probe.py::test_cli_retry_pass_through_flag `
  mcp_server\tests\test_lm6c_repeatability_probe.py::test_lm6a_command_adds_retry_flag_only_when_enabled `
  mcp_server\tests\test_lm6c_repeatability_probe.py::test_manifest_records_retry_pass_through_flag `
  mcp_server\tests\test_lm6c_repeatability_probe.py::test_attempt_row_copies_retry_metadata_from_lm6a_decision `
  mcp_server\tests\test_lm6c_repeatability_probe.py::test_build_summary_adds_retry_report_counts `
  -q
```

Expected: failures because LM6C has no pass-through or retry summary fields.

- [ ] **Step 3: Add LM6C CLI flag**

Update `_args(...)`:

```python
    parser.add_argument(
        "--lm6a-retry-clean-observation",
        action="store_true",
        help=(
            "Pass --retry-clean-observation to each child LM6A run. "
            "Default is off."
        ),
    )
```

- [ ] **Step 4: Add retry fields to base attempt rows**

Update `_base_attempt_row(...)`:

```python
        "retry_attempted": False,
        "retry_count": 0,
        "first_worker_response_kind": None,
        "first_worker_decline_reason": None,
        "final_worker_response_kind": None,
```

- [ ] **Step 5: Copy retry metadata from child `decision.json`**

In `_row_from_completed_lm6a(...)`, after `lm6a_decision` and `lm6a_reason` are set, update the row with validated retry metadata:

```python
    retry_attempted = decision.get("retry_attempted")
    retry_count = decision.get("retry_count")
    row.update(
        {
            "retry_attempted": retry_attempted is True,
            "retry_count": retry_count if isinstance(retry_count, int) else 0,
            "first_worker_response_kind": (
                decision.get("first_worker_response_kind")
                if isinstance(decision.get("first_worker_response_kind"), str)
                else None
            ),
            "first_worker_decline_reason": (
                decision.get("first_worker_decline_reason")
                if isinstance(decision.get("first_worker_decline_reason"), str)
                else None
            ),
            "final_worker_response_kind": (
                decision.get("final_worker_response_kind")
                if isinstance(decision.get("final_worker_response_kind"), str)
                else None
            ),
        }
    )
```

- [ ] **Step 6: Add retry report counts to `_build_summary(...)`**

Before returning the summary, compute:

```python
    retry_rows = [row for row in rows if row.get("retry_attempted") is True]
```

Add these fields to the returned summary:

```python
        "retry_attempted_count": len(retry_rows),
        "retry_recovered_count": sum(
            1
            for row in retry_rows
            if row.get("final_worker_response_kind") == "action_request"
        ),
        "retry_declined_count": sum(
            1
            for row in retry_rows
            if row.get("terminal_category") == "worker_declined"
        ),
        "retry_publication_failed_count": sum(
            1
            for row in retry_rows
            if row.get("terminal_category") == "publication_failed"
        ),
```

- [ ] **Step 7: Update manifest, command, run probe, and main pass-through signatures**

Update `_manifest(...)`:

```python
def _manifest(
    *,
    attempts: int,
    model: str,
    lm6a_retry_clean_observation: bool,
) -> dict[str, Any]:
```

Add:

```python
        "lm6a_retry_clean_observation": lm6a_retry_clean_observation,
```

Update `_lm6a_command(...)`:

```python
def _lm6a_command(
    *,
    model: str,
    lm6a_runs_dir: Path,
    retry_clean_observation: bool,
) -> list[str]:
    command = [
        sys.executable,
        str(_REPO_ROOT / "scripts" / "lm6a_live_worker_splice_probe.py"),
        "--model",
        model,
        "--run-dir",
        str(lm6a_runs_dir),
    ]
    if retry_clean_observation:
        command.append("--retry-clean-observation")
    return command
```

Update `_run_probe(...)` signature:

```python
    lm6a_retry_clean_observation: bool = False,
```

Pass the flag to `_manifest(...)`, `_lm6a_command(...)`, and `_build_summary(...)` only where signatures require it. `_build_summary(...)` does not need the flag.

Update `main(...)`:

```python
        lm6a_retry_clean_observation=args.lm6a_retry_clean_observation,
```

- [ ] **Step 8: Run LM6C focused tests and verify they pass**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm6c_repeatability_probe.py::test_cli_retry_pass_through_default_off `
  mcp_server\tests\test_lm6c_repeatability_probe.py::test_cli_retry_pass_through_flag `
  mcp_server\tests\test_lm6c_repeatability_probe.py::test_lm6a_command_adds_retry_flag_only_when_enabled `
  mcp_server\tests\test_lm6c_repeatability_probe.py::test_manifest_records_retry_pass_through_flag `
  mcp_server\tests\test_lm6c_repeatability_probe.py::test_attempt_row_copies_retry_metadata_from_lm6a_decision `
  mcp_server\tests\test_lm6c_repeatability_probe.py::test_build_summary_adds_retry_report_counts `
  -q
```

Expected: `6 passed`.

---

### Task 6: Preserve Static Boundaries and Backward Compatibility

**Files:**
- Modify: `mcp_server/tests/test_lm6a_live_worker_splice_probe.py`
- Modify: `mcp_server/tests/test_lm6c_repeatability_probe.py`

- [ ] **Step 1: Add LM6A static guard for unchanged shared helper and no production imports**

Extend `test_script_static_forbidden_imports_and_graph_dump_guard`:

```python
    assert "def run_two_pass_worker_publication" not in source
    assert "lm_worker_two_pass_publication.py" not in source
    assert "LiteLLM" not in source
    assert "openrouter" not in source.lower()
```

The existing import of `run_two_pass_worker_publication` remains allowed:

```python
    assert "from lm_worker_two_pass_publication import run_two_pass_worker_publication" in source
```

- [ ] **Step 2: Add LM6C static guard that it does not import LM6A internals**

Extend `test_lm6c_script_does_not_import_lm6a_internals`:

```python
    assert "--retry-clean-observation" in source
    assert "import lm6a_live_worker_splice_probe" not in source
    assert "from lm6a_live_worker_splice_probe" not in source
    assert "run_two_pass_worker_publication" not in source
    assert "apply_worker_action_to_node" not in source
```

- [ ] **Step 3: Run static guard tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm6a_live_worker_splice_probe.py::test_script_static_forbidden_imports_and_graph_dump_guard `
  mcp_server\tests\test_lm6c_repeatability_probe.py::test_lm6c_script_does_not_import_lm6a_internals `
  -q
```

Expected: `2 passed`.

---

### Task 7: Full Deterministic Verification

**Files:**
- Verify: `scripts/lm6a_live_worker_splice_probe.py`
- Verify: `scripts/lm6c_repeatability_probe.py`
- Verify: `mcp_server/tests/test_lm6a_live_worker_splice_probe.py`
- Verify: `mcp_server/tests/test_lm6c_repeatability_probe.py`

- [ ] **Step 1: Run the targeted LM6E tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm6a_live_worker_splice_probe.py `
  mcp_server\tests\test_lm6c_repeatability_probe.py `
  -q
```

Expected: all tests in both files pass.

- [ ] **Step 2: Run the nearby seam gate**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm6a_live_worker_splice_probe.py `
  mcp_server\tests\test_lm6c_repeatability_probe.py `
  mcp_server\tests\test_lm_worker_two_pass_publication.py `
  mcp_server\tests\test_plan_graph_worker_action_apply.py `
  -q
```

Expected: all tests pass. Do not start Rhino, Grasshopper, Ollama, or live LM6C.

- [ ] **Step 3: Run Python 3.10 compile**

Run:

```powershell
py -3.10 -m py_compile `
  scripts\lm6a_live_worker_splice_probe.py `
  scripts\lm6c_repeatability_probe.py `
  mcp_server\tests\test_lm6a_live_worker_splice_probe.py `
  mcp_server\tests\test_lm6c_repeatability_probe.py
```

Expected: command exits `0` with no output.

- [ ] **Step 4: Run whitespace/static diff checks**

Run:

```powershell
git diff --check main..HEAD
git diff --name-only main..HEAD
git diff --name-only main..HEAD -- mcp_server/src
```

Expected:

```text
git diff --check main..HEAD
  no output

git diff --name-only main..HEAD
  docs/superpowers/specs/2026-07-06-lm6e-bounded-worker-retry-diagnostic-design.md
  docs/superpowers/plans/2026-07-06-lm6e-bounded-worker-retry-diagnostic.md
  scripts/lm6a_live_worker_splice_probe.py
  scripts/lm6c_repeatability_probe.py
  mcp_server/tests/test_lm6a_live_worker_splice_probe.py
  mcp_server/tests/test_lm6c_repeatability_probe.py

git diff --name-only main..HEAD -- mcp_server/src
  no output
```

- [ ] **Step 5: Confirm ignored raw artifacts are not staged**

Run:

```powershell
git status --short
git status --short --ignored probe_runs
```

Expected:

```text
No staged probe_runs artifacts.
Known unrelated live telemetry/untracked docs may remain unstaged.
```

Do not run:

```powershell
.\mcp_server\.venv\Scripts\python.exe scripts\lm6c_repeatability_probe.py --lm6a-retry-clean-observation
```

That command is the post-merge live evidence run only.

---

## Post-Merge Runbook

After the implementation PR merges and `C:\UDEV\Rook` is synced to `main`, run canonical LM6E evidence only with Rhino and Grasshopper open:

```powershell
cd C:\UDEV\Rook
.\mcp_server\.venv\Scripts\python.exe scripts\lm6c_repeatability_probe.py `
  --lm6a-retry-clean-observation
```

Report:

- LM6C run dir
- `summary.json`
- `attempts.jsonl`
- child LM6A `decision.json` files
- `retry_attempted_count`
- `retry_recovered_count`
- `retry_declined_count`
- `retry_publication_failed_count`
- terminal category counts
- leak marker counts

Do not replace failed scheduled attempts. Do not commit raw `probe_runs/`.

---

## Self-Review Checklist

- [ ] Spec coverage: default-off LM6A retry, default-off LM6C pass-through, observation-only eligibility, one retry, unchanged helper, retry-context packet, ordered publication-row artifacts, stable top-level decisions, retry metadata, hidden-answer handling, no production module changes, no live run.
- [ ] Placeholder scan: no `TBD`, `TODO`, "similar to", or open-ended implementation instructions.
- [ ] Type consistency: helper signatures use `Mapping[str, Any]`, `_run_probe(...)` defaults preserve existing callers, LM6C row fields use JSON-safe primitives.
- [ ] Boundary check: `scripts/lm_worker_two_pass_publication.py` remains unchanged; `mcp_server/src/**` remains unchanged.
