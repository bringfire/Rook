# LM7D Planner Shape Guidance Probe Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a versioned `shape_guidance_v2` prompt profile to the existing LM7C offline Planner authoring probe so LM7D can test request-shape learnability without changing parser, validator, classifier, scenarios, or live/runtime behavior.

**Architecture:** Extend `scripts/lm7c_planner_authoring_probe.py` in place with prompt-profile routing. `sparse_v1` remains the default LM7C profile; `shape_guidance_v2` changes only the prompt text and related metadata. The existing fake-provider tests remain deterministic, with new tests covering prompt profile selection, canonical gating, stable artifact filenames, metadata, and report-only marker scanning.

**Tech Stack:** Python 3.10, stdlib only, pytest, existing `workflow_validate` and `PlannerWorkerContractRequest:v1` surface.

## Global Constraints

- Existing `PlannerWorkerContractRequest:v1` schema unchanged.
- `workflow_validate` unchanged.
- Strict parser unchanged.
- `intent_decision` classifier unchanged unless a direct LM7C scoring bug is discovered; this plan does not change it.
- Same two scenarios: `intent_complete`, `intent_incomplete`.
- Same template: `repair_same_component_from_create_error`.
- Same canonical provider/model target: `codex-cli-chatgpt` / `gpt-5.5`.
- Same `N=5` per scenario for canonical evidence.
- No Rhino/GH.
- No worker path.
- No live splice.
- No prompt repair loop.
- No JSON repair.
- No full canonical request exemplar.
- No concrete output value copied into prompt except the existing `7.5` in the `intent_complete` brief.
- No provider SDK addition.
- No live model call in the implementation PR.
- Prompt artifact filenames stay stable:
  - `prompts/planner_authoring_prompt.txt`
  - `prompts/template_menu.json`
  - `prompts/intent_complete_brief.txt`
  - `prompts/intent_incomplete_brief.txt`

---

## File Structure

- Modify: `scripts/lm7c_planner_authoring_probe.py`
  - Add prompt profile constants and CLI argument.
  - Render sparse and shape-guidance prompt profiles.
  - Thread `prompt_profile` and `prompt_version` through call payloads, rows, manifest, and summary.
  - Add report-only hidden-marker scanning over bounded prompt/output evidence.
  - Keep all provider, parser, validator, and classifier behavior unchanged.

- Modify: `mcp_server/tests/test_lm7c_planner_authoring_probe.py`
  - Add deterministic tests for profile defaults and canonical gating.
  - Add prompt-content tests for `shape_guidance_v2`.
  - Add artifact/row/manifest metadata tests.
  - Add marker-scan tests proving scan is report-only.
  - Preserve existing LM7C `sparse_v1` compatibility tests.

- Create: `docs/superpowers/plans/2026-07-07-lm7d-planner-shape-guidance-probe.md`
  - This plan.

Expected implementation diff scope:

```text
docs/superpowers/plans/2026-07-07-lm7d-planner-shape-guidance-probe.md
scripts/lm7c_planner_authoring_probe.py
mcp_server/tests/test_lm7c_planner_authoring_probe.py
```

Do not modify:

```text
mcp_server/src/rook/agent/planner_worker_contract_request.py
mcp_server/src/rook/agent/workflow_validate.py
scripts/lm7b_request_driven_live_splice_probe.py
scripts/lm6a_live_worker_splice_probe.py
```

---

### Task 1: CLI Prompt Profile and Canonical Gating

**Files:**
- Modify: `scripts/lm7c_planner_authoring_probe.py`
- Modify: `mcp_server/tests/test_lm7c_planner_authoring_probe.py`

**Interfaces:**
- Consumes: existing `_args(argv)` and `_canonical_evidence_is_valid(args)`.
- Produces:
  - `PROMPT_PROFILE_SPARSE_V1 = "sparse_v1"`
  - `PROMPT_PROFILE_SHAPE_GUIDANCE_V2 = "shape_guidance_v2"`
  - `PROMPT_PROFILES = (PROMPT_PROFILE_SPARSE_V1, PROMPT_PROFILE_SHAPE_GUIDANCE_V2)`
  - CLI option `--prompt-profile`, defaulting to `sparse_v1`
  - canonical evidence validation requiring `shape_guidance_v2`

- [ ] **Step 1: Add failing CLI default test**

Add to `mcp_server/tests/test_lm7c_planner_authoring_probe.py`:

```python
def test_cli_defaults_to_sparse_prompt_profile() -> None:
    args = PROBE._args([])

    assert args.prompt_profile == "sparse_v1"
```

Also update `test_cli_defaults_are_canonical_probe_defaults`:

```python
    assert args.prompt_profile == "sparse_v1"
```

- [ ] **Step 2: Run the focused failing test**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm7c_planner_authoring_probe.py::test_cli_defaults_to_sparse_prompt_profile `
  -q
```

Expected: fail with `AttributeError` or argparse missing `prompt_profile`.

- [ ] **Step 3: Implement prompt profile constants and CLI arg**

In `scripts/lm7c_planner_authoring_probe.py`, replace the current prompt version block:

```python
PLANNER_AUTHORING_PROMPT_VERSION = "lm7c.planner_authoring_prompt:v1"
```

with:

```python
PROMPT_PROFILE_SPARSE_V1 = "sparse_v1"
PROMPT_PROFILE_SHAPE_GUIDANCE_V2 = "shape_guidance_v2"
PROMPT_PROFILES = (
    PROMPT_PROFILE_SPARSE_V1,
    PROMPT_PROFILE_SHAPE_GUIDANCE_V2,
)

SPARSE_PROMPT_VERSION = "lm7c.planner_authoring_prompt:v1"
SHAPE_GUIDANCE_PROMPT_VERSION = (
    "lm7d.planner_authoring_prompt_shape_guidance:v2"
)
PLANNER_AUTHORING_PROMPT_VERSION = SPARSE_PROMPT_VERSION
```

Add helper:

```python
def _prompt_version(prompt_profile: str) -> str:
    if prompt_profile == PROMPT_PROFILE_SPARSE_V1:
        return SPARSE_PROMPT_VERSION
    if prompt_profile == PROMPT_PROFILE_SHAPE_GUIDANCE_V2:
        return SHAPE_GUIDANCE_PROMPT_VERSION
    raise ValueError(f"unknown_prompt_profile:{prompt_profile}")
```

In `_args(argv)`, add after `--output-excerpt-chars`:

```python
    parser.add_argument(
        "--prompt-profile",
        choices=PROMPT_PROFILES,
        default=PROMPT_PROFILE_SPARSE_V1,
    )
```

- [ ] **Step 4: Run default test**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm7c_planner_authoring_probe.py::test_cli_defaults_to_sparse_prompt_profile `
  mcp_server\tests\test_lm7c_planner_authoring_probe.py::test_cli_defaults_are_canonical_probe_defaults `
  -q
```

Expected: pass.

- [ ] **Step 5: Add canonical evidence profile rejection tests**

Extend `test_main_rejects_invalid_canonical_evidence_declarations` parameter list with:

```python
        ["--canonical-evidence", "--prompt-profile", "sparse_v1"],
```

Add a positive test that canonical evidence accepts `shape_guidance_v2` with a non-placeholder non-local provider/model:

```python
def test_main_accepts_lm7d_canonical_evidence_with_shape_guidance_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    def fake_command(command, call_payload, timeout_s):
        calls.append((command, call_payload, timeout_s))
        return json.dumps(_scenario_correct_request(call_payload["scenario"]))

    monkeypatch.setattr(PROBE, "_call_provider_command", fake_command)

    exit_code = PROBE.main(
        [
            "--run-dir",
            str(tmp_path),
            "--canonical-evidence",
            "--prompt-profile",
            "shape_guidance_v2",
            "--provider",
            "codex-cli-chatgpt",
            "--model",
            "gpt-5.5",
            "--provider-command",
            "fake-provider",
        ]
    )

    assert exit_code == 0
    assert len(calls) == len(PROBE.SCENARIOS) * 5
    assert all(
        call_payload["prompt_profile"] == "shape_guidance_v2"
        for _command, call_payload, _timeout_s in calls
    )
```

Update the existing
`test_main_accepts_canonical_evidence_when_only_provider_or_model_matches_local_pair`
so its `PROBE.main(...)` argv includes:

```python
            "--prompt-profile",
            "shape_guidance_v2",
```

Keep the purpose of that test unchanged: it should still prove that matching
only the provider or only the model from the rejected local pair is allowed for
canonical evidence when the selected prompt profile is the LM7D canonical
profile.

- [ ] **Step 6: Run canonical tests and verify failure**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm7c_planner_authoring_probe.py::test_main_rejects_invalid_canonical_evidence_declarations `
  mcp_server\tests\test_lm7c_planner_authoring_probe.py::test_main_accepts_lm7d_canonical_evidence_with_shape_guidance_profile `
  -q
```

Expected: fail because `_canonical_evidence_is_valid` does not yet require `shape_guidance_v2`, and call payloads do not yet include `prompt_profile`.

- [ ] **Step 7: Implement canonical profile gating**

In `_canonical_evidence_is_valid(args)`, add after the `attempts != 5` check:

```python
    if args.prompt_profile != PROMPT_PROFILE_SHAPE_GUIDANCE_V2:
        return False
```

This means LM7D canonical evidence requires `shape_guidance_v2`. Non-canonical LM7C-style sparse runs remain allowed because the function returns early when `args.canonical_evidence` is false.

- [ ] **Step 8: Thread prompt_profile into `_run_probe` call shape minimally**

Update `_prompt_call_payload` signature:

```python
def _prompt_call_payload(
    *,
    scenario: str,
    attempt_index: int,
    provider: str,
    model: str,
    temperature: float,
    prompt_profile: str,
) -> dict[str, Any]:
```

Add these fields to its returned dict:

```python
        "prompt_profile": prompt_profile,
        "prompt_version": _prompt_version(prompt_profile),
```

For this task, keep `"prompt": _planner_authoring_prompt()` unchanged; Task 2 will profile it.

Update the `_prompt_call_payload(...)` call inside `_run_probe` to pass:

```python
                prompt_profile=prompt_profile,
```

Add `prompt_profile: str` to `_run_probe(...)` signature and pass it from `main`:

```python
        prompt_profile=args.prompt_profile,
```

Update existing `_run_probe(...)` test calls in
`mcp_server/tests/test_lm7c_planner_authoring_probe.py` to pass:

```python
        prompt_profile="sparse_v1",
```

This preserves existing sparse LM7C test behavior until subsequent steps add
shape-guidance-specific assertions.

- [ ] **Step 9: Run canonical tests again**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm7c_planner_authoring_probe.py::test_main_rejects_invalid_canonical_evidence_declarations `
  mcp_server\tests\test_lm7c_planner_authoring_probe.py::test_main_accepts_lm7d_canonical_evidence_with_shape_guidance_profile `
  -q
```

Expected: pass.

- [ ] **Step 10: Commit Task 1**

Commit only after focused tests pass:

```powershell
git add scripts\lm7c_planner_authoring_probe.py mcp_server\tests\test_lm7c_planner_authoring_probe.py
git commit -m "Add LM7D prompt profile CLI gate"
```

---

### Task 2: Shape-Guidance Prompt Renderer

**Files:**
- Modify: `scripts/lm7c_planner_authoring_probe.py`
- Modify: `mcp_server/tests/test_lm7c_planner_authoring_probe.py`

**Interfaces:**
- Consumes: `PROMPT_PROFILE_SPARSE_V1`, `PROMPT_PROFILE_SHAPE_GUIDANCE_V2`, `_prompt_version(prompt_profile)`.
- Produces:
  - `_planner_authoring_prompt(prompt_profile: str = PROMPT_PROFILE_SPARSE_V1) -> str`
  - `shape_guidance_v2` prompt text with isolated snippets and conditional unresolved-intent rule

- [ ] **Step 1: Add tests for sparse compatibility and shape-guidance content**

Update existing `test_prompt_contains_rules_but_no_full_request_exemplar` so it explicitly calls the sparse profile:

```python
    prompt = PROBE._planner_authoring_prompt("sparse_v1")
```

Add:

```python
def test_shape_guidance_prompt_includes_isolated_shape_snippets_only() -> None:
    prompt = PROBE._planner_authoring_prompt("shape_guidance_v2")

    assert PROBE.SHAPE_GUIDANCE_PROMPT_VERSION in prompt
    assert '"enable_routes": []' in prompt
    assert '"disable_routes": []' in prompt
    assert '"set_required": {}' in prompt
    assert '"add_unresolved_intent_routes": []' in prompt
    assert '"intent_id": "desired_output_value"' in prompt
    assert '"status": "unresolved"' in prompt
    assert '"source_path": "planner.intent.desired_output_value"' in prompt
    assert '"description": "Desired output value was not provided."' in prompt
    assert '"route_id": "missing_desired_output_value"' in prompt
    assert '"source_class": "planner_user_intent"' in prompt
    assert '"purpose": "unresolved_intent"' in prompt
    assert '"required": false' in prompt
    assert "Use these only when desired_output_value is missing from the brief" in prompt
    assert "Omit them when desired output intent is present" in prompt
    assert '"template_id": "repair_same_component_from_create_error"' not in prompt
    assert '"initial_params": {' not in prompt
    assert '"schema": "rook.planner_worker_contract_request:v1"' not in prompt
    assert "7.5" not in prompt
    assert "A = " not in prompt
```

Add:

```python
def test_prompt_version_follows_prompt_profile() -> None:
    assert PROBE._prompt_version("sparse_v1") == "lm7c.planner_authoring_prompt:v1"
    assert (
        PROBE._prompt_version("shape_guidance_v2")
        == "lm7d.planner_authoring_prompt_shape_guidance:v2"
    )
```

- [ ] **Step 2: Run prompt tests to verify they fail**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm7c_planner_authoring_probe.py::test_prompt_contains_rules_but_no_full_request_exemplar `
  mcp_server\tests\test_lm7c_planner_authoring_probe.py::test_shape_guidance_prompt_includes_isolated_shape_snippets_only `
  mcp_server\tests\test_lm7c_planner_authoring_probe.py::test_prompt_version_follows_prompt_profile `
  -q
```

Expected: fail until `_planner_authoring_prompt` accepts a profile and renders v2.

- [ ] **Step 3: Refactor sparse prompt into profile-aware renderer**

Replace `_planner_authoring_prompt()` with:

```python
def _planner_authoring_prompt(
    prompt_profile: str = PROMPT_PROFILE_SPARSE_V1,
) -> str:
    if prompt_profile == PROMPT_PROFILE_SPARSE_V1:
        return _sparse_planner_authoring_prompt()
    if prompt_profile == PROMPT_PROFILE_SHAPE_GUIDANCE_V2:
        return _shape_guidance_planner_authoring_prompt()
    raise ValueError(f"unknown_prompt_profile:{prompt_profile}")


def _sparse_planner_authoring_prompt() -> str:
    return "\n".join(
        [
            f"version: {SPARSE_PROMPT_VERSION}",
            "",
            "Author one PlannerWorkerContractRequest from the supplied scenario brief.",
            f"The schema must be {PLANNER_WORKER_CONTRACT_REQUEST_SCHEMA}.",
            "Output exactly one JSON object and no markdown or surrounding prose.",
            "Allowed top-level fields are schema, template_id, initial_params, "
            "routing_delta, and intent_slots.",
            "The template menu contains only the LM7A repair template.",
            'The create_script pins_out field must be ["A:double"].',
            "When the brief provides the desired output intent, it is not missing, "
            "and v1 has no legal field for that concrete value.",
            "When the brief omits the desired output intent, declare only the "
            "canonical unresolved desired_output_value slot and emit the matching "
            "missing_desired_output_value unresolved-intent route with required=false.",
            "Do not write repair code, acceptance prose, hidden bind params, or "
            "fields outside the request schema.",
        ]
    )
```

- [ ] **Step 4: Add shape-guidance prompt implementation**

Add:

```python
def _shape_guidance_planner_authoring_prompt() -> str:
    routing_delta_shape = json.dumps(
        {
            "enable_routes": [],
            "disable_routes": [],
            "set_required": {},
            "add_unresolved_intent_routes": [],
        },
        indent=2,
        sort_keys=True,
    )
    unresolved_slot_shape = json.dumps(
        {
            "intent_id": DESIRED_OUTPUT_VALUE_INTENT_ID,
            "status": "unresolved",
            "source_path": PLANNER_INTENT_SOURCE_PATH,
            "description": "Desired output value was not provided.",
        },
        indent=2,
        sort_keys=True,
    )
    unresolved_route_shape = json.dumps(
        {
            "route_id": MISSING_DESIRED_OUTPUT_ROUTE_ID,
            "source_class": "planner_user_intent",
            "source_path": PLANNER_INTENT_SOURCE_PATH,
            "purpose": "unresolved_intent",
            "required": False,
        },
        indent=2,
        sort_keys=True,
    )
    return "\n".join(
        [
            f"version: {SHAPE_GUIDANCE_PROMPT_VERSION}",
            "",
            "Author one PlannerWorkerContractRequest from the supplied scenario brief.",
            f"The schema must be {PLANNER_WORKER_CONTRACT_REQUEST_SCHEMA}.",
            "Output exactly one JSON object and no markdown or surrounding prose.",
            "Required top-level fields are schema, template_id, initial_params, "
            "routing_delta, and intent_slots.",
            "Include required empty arrays and objects instead of omitting them.",
            "The template menu contains only the LM7A repair template.",
            'The create_script pins_out field must be ["A:double"].',
            "When the brief provides the desired output intent, it is not missing, "
            "and v1 has no legal field for that concrete value.",
            "When no intent is missing, intent_slots is [].",
            "When no unresolved-intent route is needed, "
            "routing_delta.add_unresolved_intent_routes is [].",
            "",
            "routing_delta container shape:",
            routing_delta_shape,
            "",
            "Canonical unresolved desired_output_value slot shape:",
            unresolved_slot_shape,
            "",
            "Canonical missing_desired_output_value unresolved-intent route shape:",
            unresolved_route_shape,
            "",
            "Use these only when desired_output_value is missing from the brief.",
            "Omit them when desired output intent is present.",
            "Do not write repair code, acceptance prose, hidden bind params, or "
            "fields outside the request schema.",
        ]
    )
```

Do not include a full solved request object. The snippets above are isolated fragments and do not include a top-level `schema` plus `template_id` plus `initial_params` object.

- [ ] **Step 5: Thread prompt profile into call payload prompt text**

In `_prompt_call_payload`, change:

```python
        "prompt": _planner_authoring_prompt(),
```

to:

```python
        "prompt": _planner_authoring_prompt(prompt_profile),
```

- [ ] **Step 6: Run prompt tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm7c_planner_authoring_probe.py::test_prompt_contains_rules_but_no_full_request_exemplar `
  mcp_server\tests\test_lm7c_planner_authoring_probe.py::test_shape_guidance_prompt_includes_isolated_shape_snippets_only `
  mcp_server\tests\test_lm7c_planner_authoring_probe.py::test_prompt_version_follows_prompt_profile `
  -q
```

Expected: pass.

- [ ] **Step 7: Update prompt marker guard for both profiles**

Replace `test_prompt_artifacts_do_not_contain_invention_or_hidden_answer_markers` with a profile-aware version:

```python
@pytest.mark.parametrize("prompt_profile", ["sparse_v1", "shape_guidance_v2"])
def test_prompt_artifacts_do_not_contain_invention_or_hidden_answer_markers(
    prompt_profile: str,
) -> None:
    artifacts = {
        "prompt": PROBE._planner_authoring_prompt(prompt_profile),
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
            assert marker not in artifact, (prompt_profile, name, marker)

    assert "7.5" in artifacts["intent_complete"]
    assert "7.5" not in artifacts["prompt"]
    assert "7.5" not in artifacts["template_menu"]
    assert "7.5" not in artifacts["intent_incomplete"]
```

- [ ] **Step 8: Run all prompt artifact tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm7c_planner_authoring_probe.py `
  -k "prompt or brief or template_menu" `
  -q
```

Expected: pass.

- [ ] **Step 9: Commit Task 2**

```powershell
git add scripts\lm7c_planner_authoring_probe.py mcp_server\tests\test_lm7c_planner_authoring_probe.py
git commit -m "Add LM7D shape guidance prompt profile"
```

---

### Task 3: Profile Metadata in Rows, Manifest, Summary, and Artifacts

**Files:**
- Modify: `scripts/lm7c_planner_authoring_probe.py`
- Modify: `mcp_server/tests/test_lm7c_planner_authoring_probe.py`

**Interfaces:**
- Consumes:
  - `_prompt_version(prompt_profile: str) -> str`
  - `_planner_authoring_prompt(prompt_profile: str) -> str`
- Produces:
  - `_base_row(..., prompt_profile: str, ...)`
  - `_score_model_output(..., prompt_profile: str, ...)`
  - `_write_prompt_artifacts(run_dir: Path, prompt_profile: str) -> None`
  - `_manifest(..., prompt_profile: str, ...)`
  - `_summarize_rows(..., prompt_profile: str, ...)`

- [ ] **Step 1: Add row metadata test**

Add:

```python
def test_row_records_prompt_profile_and_prompt_version() -> None:
    row = PROBE._score_model_output(
        scenario="intent_complete",
        attempt_index=0,
        provider="fake",
        model="fake-planner",
        temperature=0,
        prompt_profile="shape_guidance_v2",
        raw_output=json.dumps(_minimal_complete_request()),
        output_excerpt_chars=120,
    )

    assert row["prompt_profile"] == "shape_guidance_v2"
    assert row["prompt_version"] == "lm7d.planner_authoring_prompt_shape_guidance:v2"
```

- [ ] **Step 2: Run row metadata test to verify failure**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm7c_planner_authoring_probe.py::test_row_records_prompt_profile_and_prompt_version `
  -q
```

Expected: fail because `_score_model_output` does not accept `prompt_profile`.

- [ ] **Step 3: Thread prompt profile through scoring**

Update `_base_row` signature:

```python
def _base_row(
    *,
    scenario: str,
    attempt_index: int,
    provider: str,
    model: str,
    temperature: float,
    prompt_profile: str,
    raw_output: str,
    output_excerpt_chars: int,
) -> dict[str, Any]:
```

In returned row, replace:

```python
        "prompt_version": PLANNER_AUTHORING_PROMPT_VERSION,
```

with:

```python
        "prompt_profile": prompt_profile,
        "prompt_version": _prompt_version(prompt_profile),
```

Update `_score_model_output` signature to include `prompt_profile: str`, and pass it into `_base_row(...)`.

Update `_provider_error_row` signature to include `prompt_profile: str`, and pass it into `_base_row(...)`.

Update all existing test calls to `_score_model_output(...)` and `_provider_error_row(...)` through `_run_probe(...)` by passing:

```python
        prompt_profile="sparse_v1",
```

Use `sparse_v1` for existing LM7C compatibility tests unless the test specifically exercises `shape_guidance_v2`.

- [ ] **Step 4: Run row/scoring tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm7c_planner_authoring_probe.py `
  -k "row or score or intent or parse" `
  -q
```

Expected: pass.

- [ ] **Step 5: Add run artifact metadata test**

Update `test_run_probe_writes_artifacts_and_summary` call to `_run_probe`:

```python
        prompt_profile="shape_guidance_v2",
```

Add assertions:

```python
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["prompt_profile"] == "shape_guidance_v2"
    assert manifest["prompt_version"] == "lm7d.planner_authoring_prompt_shape_guidance:v2"

    assert all(row["prompt_profile"] == "shape_guidance_v2" for row in rows)
    assert all(
        row["prompt_version"] == "lm7d.planner_authoring_prompt_shape_guidance:v2"
        for row in rows
    )
    assert summary["prompt_profile"] == "shape_guidance_v2"
    assert summary["prompt_version"] == "lm7d.planner_authoring_prompt_shape_guidance:v2"
```

Keep existing artifact filename assertions unchanged:

```python
    assert (run_dir / "prompts" / "planner_authoring_prompt.txt").is_file()
    assert (run_dir / "prompts" / "template_menu.json").is_file()
    assert (run_dir / "prompts" / "intent_complete_brief.txt").is_file()
    assert (run_dir / "prompts" / "intent_incomplete_brief.txt").is_file()
```

- [ ] **Step 6: Run artifact test to verify failure**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm7c_planner_authoring_probe.py::test_run_probe_writes_artifacts_and_summary `
  -q
```

Expected: fail because manifest/summary/artifacts are not profile-aware yet.

- [ ] **Step 7: Thread profile through prompt artifacts, manifest, summary, and run loop**

Update `_write_prompt_artifacts` signature:

```python
def _write_prompt_artifacts(run_dir: Path, prompt_profile: str) -> None:
```

Change prompt write:

```python
        _planner_authoring_prompt(prompt_profile) + "\n",
```

Do not change filenames.

Update `_summarize_rows` signature:

```python
def _summarize_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    attempts: int,
    provider: str,
    model: str,
    temperature: float,
    canonical_evidence: bool,
    prompt_profile: str,
) -> dict[str, Any]:
```

Add to returned dict:

```python
        "prompt_profile": prompt_profile,
        "prompt_version": _prompt_version(prompt_profile),
```

Update `_manifest` signature:

```python
def _manifest(
    *,
    provider: str,
    model: str,
    temperature: float,
    attempts: int,
    canonical_evidence: bool,
    prompt_profile: str,
) -> dict[str, Any]:
```

Replace manifest prompt version:

```python
        "prompt_profile": prompt_profile,
        "prompt_version": _prompt_version(prompt_profile),
```

Update `_run_probe(...)`:

```python
    _write_prompt_artifacts(run_dir, prompt_profile)
```

Pass `prompt_profile` into `_manifest`, `_prompt_call_payload`, `_provider_error_row`, `_score_model_output`, and `_summarize_rows`.

- [ ] **Step 8: Run full LM7C/LM7D test file**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm7c_planner_authoring_probe.py `
  -q
```

Expected: pass.

- [ ] **Step 9: Commit Task 3**

```powershell
git add scripts\lm7c_planner_authoring_probe.py mcp_server\tests\test_lm7c_planner_authoring_probe.py
git commit -m "Record LM7D prompt profile metadata"
```

---

### Task 4: Report-Only Hidden Marker Scan

**Files:**
- Modify: `scripts/lm7c_planner_authoring_probe.py`
- Modify: `mcp_server/tests/test_lm7c_planner_authoring_probe.py`

**Interfaces:**
- Consumes: rows with `output_excerpt`, prompt artifacts generated by `_planner_authoring_prompt`, `_template_menu`, `_scenario_brief`.
- Produces:
  - `HIDDEN_MARKER_SCAN_TERMS`
  - `_hidden_marker_matches(rows: Sequence[Mapping[str, Any]], *, prompt_profile: str) -> list[dict[str, Any]]`
  - summary fields `hidden_marker_match_count`, `hidden_marker_matches`

- [ ] **Step 1: Add summary marker scan tests**

Add:

```python
def test_summary_reports_hidden_marker_matches_without_changing_classification() -> None:
    rows = [
        {
            "scenario": "intent_complete",
            "parse_status": "parse_failed",
            "validation_status": "not_evaluated",
            "intent_decision": "not_classifiable",
            "canonical_success": False,
            "output_excerpt": "bad model output PROBE_REPAIR_CODE",
        },
        {
            "scenario": "intent_incomplete",
            "parse_status": "parsed",
            "validation_status": "workflow_validate_valid",
            "intent_decision": "correct_declared",
            "canonical_success": True,
            "output_excerpt": "{}",
        },
    ]

    summary = PROBE._summarize_rows(
        rows,
        attempts=1,
        provider="fake",
        model="fake-planner",
        temperature=0,
        canonical_evidence=False,
        prompt_profile="shape_guidance_v2",
    )

    assert summary["parse_success_count"] == 1
    assert summary["workflow_validate_valid_count"] == 1
    assert summary["correct_intent_count"] == 1
    assert summary["canonical_success_count"] == 1
    assert summary["hidden_marker_match_count"] == 1
    assert summary["hidden_marker_matches"] == [
        {
            "artifact": "rows[0].output_excerpt",
            "marker": "PROBE_REPAIR_CODE",
        }
    ]
```

Add prompt-artifact guard:

```python
def test_marker_scan_checks_prompt_artifacts_but_allows_only_complete_brief_value() -> None:
    matches = PROBE._hidden_marker_matches([], prompt_profile="shape_guidance_v2")

    assert matches == []
```

- [ ] **Step 2: Run marker tests to verify failure**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm7c_planner_authoring_probe.py::test_summary_reports_hidden_marker_matches_without_changing_classification `
  mcp_server\tests\test_lm7c_planner_authoring_probe.py::test_marker_scan_checks_prompt_artifacts_but_allows_only_complete_brief_value `
  -q
```

Expected: fail because marker scan functions/summary fields do not exist.

- [ ] **Step 3: Add marker constants**

In `scripts/lm7c_planner_authoring_probe.py`, near the marker/classifier constants, add:

```python
HIDDEN_MARKER_SCAN_TERMS = (
    "PROBE_REPAIR_CODE",
    "A = 42.0",
    "A = 0.0",
    "A = 1.0",
    "BindStepSpec.base_params",
    "repair_same_component.bind.base_params",
)
```

Do not include `"7.5"` in this marker scan. `7.5` is already controlled by prompt-artifact tests and classifier invention logic; it is allowed in the complete brief only.

- [ ] **Step 4: Implement report-only marker scan**

Add:

```python
def _hidden_marker_matches(
    rows: Sequence[Mapping[str, Any]],
    *,
    prompt_profile: str,
) -> list[dict[str, str]]:
    artifacts: list[tuple[str, str]] = [
        ("prompts/planner_authoring_prompt.txt", _planner_authoring_prompt(prompt_profile)),
        ("prompts/template_menu.json", _canonical_json(_template_menu())),
        (
            "prompts/intent_complete_brief.txt",
            _scenario_brief("intent_complete")["text"],
        ),
        (
            "prompts/intent_incomplete_brief.txt",
            _scenario_brief("intent_incomplete")["text"],
        ),
    ]
    artifacts.extend(
        (
            f"rows[{index}].output_excerpt",
            str(row.get("output_excerpt") or ""),
        )
        for index, row in enumerate(rows)
    )

    matches: list[dict[str, str]] = []
    for artifact, text in artifacts:
        for marker in HIDDEN_MARKER_SCAN_TERMS:
            if marker in text:
                matches.append({"artifact": artifact, "marker": marker})
    return matches
```

This function only observes bounded artifacts. It must not mutate rows or alter parse/validation/intent/canonical fields.

- [ ] **Step 5: Add marker scan fields to summary**

In `_summarize_rows(...)`, before returning, compute:

```python
    marker_matches = _hidden_marker_matches(rows, prompt_profile=prompt_profile)
```

Add to returned dict:

```python
        "hidden_marker_match_count": len(marker_matches),
        "hidden_marker_matches": marker_matches,
```

- [ ] **Step 6: Run marker tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm7c_planner_authoring_probe.py::test_summary_reports_hidden_marker_matches_without_changing_classification `
  mcp_server\tests\test_lm7c_planner_authoring_probe.py::test_marker_scan_checks_prompt_artifacts_but_allows_only_complete_brief_value `
  -q
```

Expected: pass.

- [ ] **Step 7: Add run-probe summary marker field assertion**

In `test_run_probe_writes_artifacts_and_summary`, add:

```python
    assert summary["hidden_marker_match_count"] == 0
    assert summary["hidden_marker_matches"] == []
```

- [ ] **Step 8: Run full LM7C/LM7D test file**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm7c_planner_authoring_probe.py `
  -q
```

Expected: pass.

- [ ] **Step 9: Commit Task 4**

```powershell
git add scripts\lm7c_planner_authoring_probe.py mcp_server\tests\test_lm7c_planner_authoring_probe.py
git commit -m "Add LM7D report-only marker scan"
```

---

### Task 5: Boundary Guards, Nearby Tests, and Final Scope

**Files:**
- Modify: `mcp_server/tests/test_lm7c_planner_authoring_probe.py`
- Verify only: `scripts/lm7c_planner_authoring_probe.py`

**Interfaces:**
- Consumes all Task 1-4 outputs.
- Produces final deterministic implementation confidence before PR.

- [ ] **Step 1: Strengthen no-live/no-worker guard**

Update `test_lm7c_script_does_not_import_live_worker_or_rhino_surfaces` to also reject LM7D-prohibited surfaces:

```python
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
        "validate_worker_visible_source_routing",
        "materialize_planner_worker_contract_request",
        "extract_acceptance_criteria_sources",
        "assemble_acceptance_criteria_packet",
    )
```

Do not ban `validate_planner_worker_contract_request`; it is the intended LM7C/LM7D scorer.

- [ ] **Step 2: Add no markdown/repair-loop prompt guard**

Add:

```python
def test_lm7d_does_not_add_repair_loop_or_json_repair() -> None:
    sparse = PROBE._planner_authoring_prompt("sparse_v1").lower()
    shaped = PROBE._planner_authoring_prompt("shape_guidance_v2").lower()
    for prompt in (sparse, shaped):
        assert "validator feedback" not in prompt
        assert "repair loop" not in prompt
        assert "retry" not in prompt
        assert "```json" not in prompt
```

Use the narrower prompt assertion if the raw-source version is too blunt.

- [ ] **Step 3: Run full focused and nearby planner gates**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm7c_planner_authoring_probe.py `
  mcp_server\tests\test_planner_worker_contract_request.py `
  mcp_server\tests\test_workflow_validate.py `
  -q
```

Expected: all pass. Current nearby baseline before LM7D was `100 passed` for LM7C + adjacent planner gates; exact count may increase because LM7D adds tests.

- [ ] **Step 4: Python 3.10 compile**

Run:

```powershell
py -3.10 -m py_compile `
  scripts\lm7c_planner_authoring_probe.py `
  mcp_server\tests\test_lm7c_planner_authoring_probe.py
```

Expected: no output and exit code `0`.

- [ ] **Step 5: Verify exact diff scope**

Run:

```powershell
$expected = @(
  "docs/superpowers/plans/2026-07-07-lm7d-planner-shape-guidance-probe.md",
  "docs/superpowers/specs/2026-07-07-lm7d-planner-shape-guidance-probe-design.md",
  "scripts/lm7c_planner_authoring_probe.py",
  "mcp_server/tests/test_lm7c_planner_authoring_probe.py"
) | Sort-Object

$actual = git diff --name-only main..HEAD | Sort-Object
Compare-Object $expected $actual
```

Expected: no output.

Note: if the spec and plan land in separate PRs, remove the spec file from `$expected` for the implementation PR. Do not include unrelated local telemetry or Rook2 docs.

- [ ] **Step 6: Whitespace check**

Run:

```powershell
git diff --check main..HEAD
```

Expected: no output.

- [ ] **Step 7: Commit final guard/test task**

```powershell
git add mcp_server\tests\test_lm7c_planner_authoring_probe.py
git commit -m "Guard LM7D planner authoring boundaries"
```

---

## Final Verification Before PR

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm7c_planner_authoring_probe.py `
  mcp_server\tests\test_planner_worker_contract_request.py `
  mcp_server\tests\test_workflow_validate.py `
  -q

py -3.10 -m py_compile `
  scripts\lm7c_planner_authoring_probe.py `
  mcp_server\tests\test_lm7c_planner_authoring_probe.py

git diff --check main..HEAD
```

Expected:

```text
pytest: all tests pass
py_compile: no output
git diff --check: no output
```

Manual diff-scope check:

```powershell
git diff --name-only main..HEAD
```

Expected implementation files:

```text
docs/superpowers/plans/2026-07-07-lm7d-planner-shape-guidance-probe.md
scripts/lm7c_planner_authoring_probe.py
mcp_server/tests/test_lm7c_planner_authoring_probe.py
```

If this plan and the LM7D spec share one PR, the spec file is also expected:

```text
docs/superpowers/specs/2026-07-07-lm7d-planner-shape-guidance-probe-design.md
```

No live model run belongs in the implementation PR. The post-merge canonical evidence command will be selected after merge and must include:

```powershell
.\mcp_server\.venv\Scripts\python.exe scripts\lm7c_planner_authoring_probe.py `
  --prompt-profile shape_guidance_v2 `
  --canonical-evidence `
  --provider codex-cli-chatgpt `
  --model gpt-5.5 `
  --provider-command "<approved provider adapter command>"
```

---

## Self-Review Checklist

- Spec coverage:
  - Prompt profile CLI: Task 1.
  - `sparse_v1` default and LM7C replayability: Tasks 1-3.
  - `shape_guidance_v2` version and snippets: Task 2.
  - Stable artifact filenames: Task 3.
  - Manifest/row metadata: Task 3.
  - Canonical LM7D evidence constraints: Task 1.
  - Report-only marker scan: Task 4.
  - No schema/validator/classifier/live/worker drift: Task 5.

- Placeholder scan targets:
  - No unresolved placeholder markers.
  - No unfinished work markers.
  - No undefined helper names.
  - No references to prior tasks without concrete code.

- Type consistency:
  - `prompt_profile` is a `str`.
  - `_prompt_version(prompt_profile: str) -> str`.
  - `_planner_authoring_prompt(prompt_profile: str = PROMPT_PROFILE_SPARSE_V1) -> str`.
  - `_hidden_marker_matches(...) -> list[dict[str, str]]`.
