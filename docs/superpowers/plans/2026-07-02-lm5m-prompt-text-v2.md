# LM5M Prompt Text v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Change only the local-worker prompt text version and generic instruction text so LM5K can later run a controlled `prompt_text:v2` probe.

**Architecture:** LM5M keeps the existing LM5J prompt artifact pipeline intact. The request envelope, response-contract rendering, adapter, strict response loader, and probe runner remain unchanged; only `LOCAL_WORKER_PROMPT_TEXT_VERSION` and `_INSTRUCTION_TEXT` change, with deterministic tests proving the new wording is generic and boundary-safe.

**Tech Stack:** Python 3.10-compatible code, pytest, existing Rook local-worker agent modules.

---

## File Structure

Modify:

- `mcp_server/src/rook/agent/local_worker_prompt_artifact.py`
  - Change only `LOCAL_WORKER_PROMPT_TEXT_VERSION`.
  - Change only `_INSTRUCTION_TEXT`.
  - Do not edit renderers, validators, JSON rendering, imports, or public exports.

- `mcp_server/tests/test_local_worker_prompt_artifact.py`
  - Update prompt text version assertion.
  - Add deterministic tests for generic authoring-role wording.
  - Add deterministic tests for raw JSON/no-fence wording.
  - Replace the old literal guard with one that allows generic `clarification` / `refusal` vocabulary but still bans hand-listed response-envelope, field-set, category, action, and scenario literals.

Do not modify:

- `mcp_server/src/rook/agent/local_worker_adapter.py`
- `mcp_server/tests/test_local_worker_adapter.py`
- `scripts/lm5k_worker_probe.py`
- LM5A/H/I/G transport modules
- response loader/parser behavior
- probe evidence docs

The adapter tests are a verification gate only. They already compare records to `LOCAL_WORKER_PROMPT_TEXT_VERSION`; no adapter test edit is planned.

---

## Pre-Implementation Gate

**Files:**
- Inspect: repository state

- [ ] **Step 1: Confirm branch and cleanliness**

Run from repo root:

```powershell
cd C:\UDEV\Rook
git status --short --branch
git diff --name-status main..HEAD
```

Expected branch:

```text
## codex/lm5m-prompt-text-v2
```

Expected diff before implementation:

```text
A       docs/superpowers/specs/2026-07-02-lm5m-prompt-text-v2-design.md
A       docs/superpowers/plans/2026-07-02-lm5m-prompt-text-v2.md
```

If `git status --short` shows unrelated tracked changes, stop and report them.

---

## Task 1: Prompt Artifact RED Tests

**Files:**
- Modify: `mcp_server/tests/test_local_worker_prompt_artifact.py`

- [ ] **Step 1: Update the version assertion to v2**

Change `test_schema_constants()` to:

```python
def test_schema_constants() -> None:
    assert LOCAL_WORKER_PROMPT_ARTIFACT_SCHEMA == "rook.local_worker_prompt_artifact:v1"
    assert LOCAL_WORKER_PROMPT_TEXT_VERSION == "lm5m.prompt_text:v2"
```

- [ ] **Step 2: Add authoring-role and raw-JSON instruction tests**

Add these tests after `test_contract_mutation_changes_system_text()`:

```python
def test_instruction_text_explains_generic_action_input_authoring_role() -> None:
    instruction = prompt_module._INSTRUCTION_TEXT
    assert "input_schema describes the shape" in instruction
    assert "action input object" in instruction
    assert "visible context" in instruction
    assert "not a list of hidden values" in instruction
    assert "If visible context is sufficient" in instruction
    assert "clarification or refusal" in instruction
    assert "always request" not in instruction.lower()
    assert "always author" not in instruction.lower()


def test_instruction_text_requires_raw_json_without_fences_or_commentary() -> None:
    instruction = prompt_module._INSTRUCTION_TEXT
    assert "Return exactly one JSON object" in instruction
    assert "Do not use markdown fences" in instruction
    assert "backticks" in instruction
    assert "language labels" in instruction
    assert "explanatory text" in instruction
    assert "before or after the JSON object" in instruction
```

- [ ] **Step 3: Replace the literal-boundary test**

Replace `test_instruction_constant_has_no_kind_or_field_literals()` with:

```python
def test_instruction_constant_has_no_hand_listed_contract_or_scenario_literals() -> None:
    payload = _request_payload()
    contract = payload["response_contract"]
    instruction = prompt_module._INSTRUCTION_TEXT

    assert "clarification" in instruction
    assert "refusal" in instruction

    banned_response_literals = {
        "action_request",
        "clarification_request",
        "observation",
        "action_id",
        "rationale",
        "question",
        "category",
        "message",
        "data",
    }
    for literal in banned_response_literals:
        assert literal not in instruction

    for category in contract["refusal_categories"]:
        assert category not in instruction

    banned_scenario_literals = {
        "draft_repair_params",
        "code",
        "mode",
        "component_guid",
        "repair_same_component",
        "RunScript",
    }
    for literal in banned_scenario_literals:
        assert literal not in instruction
```

This intentionally allows generic `clarification` and `refusal` vocabulary.
It still bans response-envelope names, field-set names, refusal category values,
action ids, and scenario-specific literals.

- [ ] **Step 4: Run RED targeted test**

Run from `mcp_server`:

```powershell
cd C:\UDEV\Rook\mcp_server
.\.venv\Scripts\python.exe -m pytest tests\test_local_worker_prompt_artifact.py -q
```

Expected: FAIL.

Expected failing assertions include:

```text
assert 'lm5j.prompt_text:v1' == 'lm5m.prompt_text:v2'
assert 'input_schema describes the shape' in instruction
assert 'backticks' in instruction
assert 'clarification' in instruction
assert 'code' not in instruction
```

The old v1 instruction contains `code fences`, so the new scenario-literal
guard should fail before implementation. That is the intended RED evidence.

Do not commit after the RED step.

---

## Task 2: Prompt Text v2 Implementation

**Files:**
- Modify: `mcp_server/src/rook/agent/local_worker_prompt_artifact.py`
- Test: `mcp_server/tests/test_local_worker_prompt_artifact.py`

- [ ] **Step 1: Update the prompt text version**

In `mcp_server/src/rook/agent/local_worker_prompt_artifact.py`, change:

```python
LOCAL_WORKER_PROMPT_TEXT_VERSION = "lm5j.prompt_text:v1"
```

to:

```python
LOCAL_WORKER_PROMPT_TEXT_VERSION = "lm5m.prompt_text:v2"
```

- [ ] **Step 2: Replace `_INSTRUCTION_TEXT`**

Replace the existing `_INSTRUCTION_TEXT` value with exactly:

```python
_INSTRUCTION_TEXT = (
    "You are a bounded Rook worker resolving exactly one workflow node.\n"
    "The user content is a request envelope as JSON: the workflow context\n"
    "you may rely on and the contract your reply must follow.\n"
    "For an allowed action, its input_schema describes the shape of the\n"
    "action input object you may author from visible context. It is not a\n"
    "list of hidden values Rook is withholding. If visible context is\n"
    "sufficient, author that input object yourself. If not, use\n"
    "clarification or refusal.\n"
    "Return exactly one JSON object matching the response contract. Do not\n"
    "use markdown fences, backticks, language labels, or explanatory text\n"
    "before or after the JSON object.\n"
    "The object must follow exactly one of the allowed reply envelopes\n"
    "listed below, using exactly the listed entries."
)
```

Do not change any imports, helpers, validators, renderers, or JSON rendering.

- [ ] **Step 3: Run targeted prompt artifact tests**

Run:

```powershell
cd C:\UDEV\Rook\mcp_server
.\.venv\Scripts\python.exe -m pytest tests\test_local_worker_prompt_artifact.py -q
```

Expected: all tests in `test_local_worker_prompt_artifact.py` pass.

- [ ] **Step 4: Confirm production diff is limited to the two names**

Run from repo root:

```powershell
cd C:\UDEV\Rook
git diff -- mcp_server/src/rook/agent/local_worker_prompt_artifact.py
```

Expected production diff:

```diff
-LOCAL_WORKER_PROMPT_TEXT_VERSION = "lm5j.prompt_text:v1"
+LOCAL_WORKER_PROMPT_TEXT_VERSION = "lm5m.prompt_text:v2"
```

and one `_INSTRUCTION_TEXT` replacement. There should be no changes below
`render_local_worker_prompt_artifact(...)`.

- [ ] **Step 5: Commit Task 1+2 together**

Run:

```powershell
cd C:\UDEV\Rook
git add `
  mcp_server/src/rook/agent/local_worker_prompt_artifact.py `
  mcp_server/tests/test_local_worker_prompt_artifact.py
git commit -m "feat(lm5m): update local worker prompt text to v2"
```

Expected: one commit containing only the prompt artifact production change and
prompt artifact tests.

---

## Task 3: Adapter Compatibility Gate

**Files:**
- Read-only: `mcp_server/src/rook/agent/local_worker_adapter.py`
- Read-only: `mcp_server/tests/test_local_worker_adapter.py`

- [ ] **Step 1: Run adapter tests without editing adapter files**

Run:

```powershell
cd C:\UDEV\Rook\mcp_server
.\.venv\Scripts\python.exe -m pytest tests\test_local_worker_adapter.py -q
```

Expected: PASS.

The adapter imports `LOCAL_WORKER_PROMPT_TEXT_VERSION`, so records should carry
the new version without adapter source changes. If this test fails only because
of a literal expectation for `lm5j.prompt_text:v1`, stop and report the exact
failure before editing. Do not add adapter behavior assertions.

- [ ] **Step 2: Confirm no adapter diff**

Run from repo root:

```powershell
cd C:\UDEV\Rook
git diff --name-only -- mcp_server/src/rook/agent/local_worker_adapter.py mcp_server/tests/test_local_worker_adapter.py
```

Expected: no output.

No commit is needed for this task if the expected output is no output.

---

## Task 4: Final Verification Gates

**Files:**
- Verify: implementation branch

- [ ] **Step 1: Run focused prompt/adapter gate**

Run:

```powershell
cd C:\UDEV\Rook\mcp_server
.\.venv\Scripts\python.exe -m pytest `
  tests\test_local_worker_prompt_artifact.py `
  tests\test_local_worker_adapter.py `
  -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run Python 3.10 compile gate**

Run from repo root:

```powershell
cd C:\UDEV\Rook
py -3.10 -m py_compile `
  mcp_server\src\rook\agent\local_worker_prompt_artifact.py `
  mcp_server\tests\test_local_worker_prompt_artifact.py `
  mcp_server\tests\test_local_worker_adapter.py
```

Expected: no output and exit code 0.

- [ ] **Step 3: Run diff check**

Run:

```powershell
cd C:\UDEV\Rook
git diff --check main..HEAD
```

Expected: no output and exit code 0.

- [ ] **Step 4: Confirm final branch scope**

Run:

```powershell
cd C:\UDEV\Rook
git diff --name-status main..HEAD
```

Expected final branch diff:

```text
A       docs/superpowers/specs/2026-07-02-lm5m-prompt-text-v2-design.md
A       docs/superpowers/plans/2026-07-02-lm5m-prompt-text-v2.md
M       mcp_server/src/rook/agent/local_worker_prompt_artifact.py
M       mcp_server/tests/test_local_worker_prompt_artifact.py
```

Expected no diff in:

```text
mcp_server/src/rook/agent/local_worker_adapter.py
mcp_server/tests/test_local_worker_adapter.py
scripts/lm5k_worker_probe.py
docs/superpowers/probes/2026-07-02-lm5k-first-worker-model-probe.md
```

- [ ] **Step 5: Confirm worktree clean**

Run:

```powershell
cd C:\UDEV\Rook
git status --short --branch
```

Expected:

```text
## codex/lm5m-prompt-text-v2
```

with no tracked or untracked file lines.

No Task 4 commit is needed unless verification required a source or test fix.

---

## Task 5: Post-Implementation Handoff Note

**Files:**
- No file changes

- [ ] **Step 1: Report implementation status**

Report the exact observed command summaries in prose using this structure:

```text
LM5M implementation complete.
Prompt text version: lm5m.prompt_text:v2
Production change: LOCAL_WORKER_PROMPT_TEXT_VERSION + _INSTRUCTION_TEXT only
Prompt artifact targeted tests: copy the pytest summary line from Task 2.
Adapter tests: copy the pytest summary line from Task 3.
Focused prompt/adapter gate: copy the pytest summary line from Task 4.
Python 3.10 compile: passed
git diff --check main..HEAD: clean
Final scope: spec, plan, local_worker_prompt_artifact.py, test_local_worker_prompt_artifact.py
Live LM5K probe: not run in this PR
```

- [ ] **Step 2: Preserve post-merge probe boundary**

Do not run:

```powershell
scripts\lm5k_worker_probe.py
```

inside the implementation PR. The live probe happens after merge using the
runbook in the LM5M spec.
