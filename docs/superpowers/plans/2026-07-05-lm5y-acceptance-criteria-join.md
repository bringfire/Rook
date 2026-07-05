# LM5Y Acceptance-Criteria Join Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the LM5U v3 evidence packet to build its `acceptance_criteria` section through LM5X extraction plus LM5W assembly, while keeping the worker-visible packet unchanged.

**Architecture:** `scripts/lm5k_worker_probe.py` becomes the first intentional runtime consumer of the LM5W/LM5X seam. It extracts typed sources from the existing probe contract, graph receipt, and gotcha packet, assembles the LM5W packet, then legacy-projects criteria back to the LM5U worker-visible shape. LM5R continues to consume rendered LM5K contexts indirectly and does not import the new modules directly.

**Tech Stack:** Python 3.10, pytest, existing LM5K/LM5R probe harness, LM5W `local_worker_acceptance_criteria`, LM5X `local_worker_acceptance_criteria_sources`.

---

## Files

Modify:

```text
scripts/lm5k_worker_probe.py
mcp_server/tests/test_lm5k_worker_probe.py
mcp_server/tests/test_local_worker_acceptance_criteria.py
mcp_server/tests/test_local_worker_acceptance_criteria_sources.py
```

Modify only if required by an existing import guard:

```text
mcp_server/tests/test_lm5r_two_pass_publication_probe.py
```

Do not modify:

```text
mcp_server/src/rook/agent/local_worker_acceptance_criteria.py
mcp_server/src/rook/agent/local_worker_acceptance_criteria_sources.py
scripts/lm5r_two_pass_publication_probe.py
```

Add plan doc only:

```text
docs/superpowers/plans/2026-07-05-lm5y-acceptance-criteria-join.md
```

## Task 1: RED Tests For Joined Acceptance Criteria

**Files:**
- Modify: `mcp_server/tests/test_lm5k_worker_probe.py`

- [ ] **Step 1: Add imports for LM5W/LM5X in the test file**

Add these imports near the existing test imports:

```python
from rook.agent.local_worker_acceptance_criteria import (
    assemble_acceptance_criteria_packet,
)
from rook.agent.local_worker_acceptance_criteria_sources import (
    extract_acceptance_criteria_sources,
)
```

- [ ] **Step 2: Add a local legacy projection helper**

Place this helper near the existing `_jsonable` helper if present, or near the acceptance-criteria tests:

```python
def _legacy_acceptance_criteria_projection(criteria):
    return [
        {
            "criterion_id": criterion["criterion_id"],
            "description": criterion["description"],
            "source": criterion["source"],
        }
        for criterion in criteria
    ]
```

- [ ] **Step 3: Add a test proving v3 visible criteria come from LM5X/LM5W**

Add this test near `test_acceptance_criteria_evidence_v3_fields_are_bounded_and_provenance_tagged`:

```python
def test_acceptance_criteria_v3_uses_assembled_legacy_projection() -> None:
    _scaffold, result = PROBE.derive_probe_graph_state()
    packet = PROBE._acceptance_criteria_evidence_packet(result.final_graph)
    sources = extract_acceptance_criteria_sources(
        workflow_contract=PROBE._probe_contract(),
        graph=result.final_graph,
        convention_packets=(PROBE._script_body_gotcha_packet(),),
    )
    assembled = assemble_acceptance_criteria_packet(sources)

    assert packet.content["fields"]["acceptance_criteria"]["criteria"] == (
        _legacy_acceptance_criteria_projection(assembled["criteria"])
    )
```

This test may pass before implementation because the hand-built criteria currently match LM5W. That is acceptable as an anchor, but the next test must fail.

- [ ] **Step 4: Add a test proving the v3 builder calls the join seam**

Add this test after the projection test:

```python
def test_acceptance_criteria_v3_calls_extractor_and_assembler(monkeypatch) -> None:
    _scaffold, result = PROBE.derive_probe_graph_state()
    calls = {"extract": 0, "assemble": 0}

    real_extract = PROBE.extract_acceptance_criteria_sources
    real_assemble = PROBE.assemble_acceptance_criteria_packet

    def recording_extract(**kwargs):
        calls["extract"] += 1
        assert kwargs["workflow_contract"] == PROBE._probe_contract()
        assert kwargs["graph"] is result.final_graph
        assert kwargs["convention_packets"] == (PROBE._script_body_gotcha_packet(),)
        return real_extract(**kwargs)

    def recording_assemble(sources):
        calls["assemble"] += 1
        return real_assemble(sources)

    monkeypatch.setattr(PROBE, "extract_acceptance_criteria_sources", recording_extract)
    monkeypatch.setattr(PROBE, "assemble_acceptance_criteria_packet", recording_assemble)

    packet = PROBE._acceptance_criteria_evidence_packet(result.final_graph)

    assert calls == {"extract": 1, "assemble": 1}
    assert packet.content["fields"]["acceptance_criteria"]["source"] == (
        "workflow_contract + create_script.initial_execution_params + "
        "create_script.receipt.script_receipt.repair_anchor + script_body_gotcha"
    )
```

Expected before implementation: fails with an `AttributeError` because `PROBE` does not yet expose the imported functions, or fails because the call counts stay zero.

- [ ] **Step 5: Add a test proving assembled metadata remains hidden**

Add this test near `test_lm5u_acceptance_criteria_boundary_guard`:

```python
def test_acceptance_criteria_v3_hides_assembled_packet_metadata() -> None:
    _scaffold, result = PROBE.derive_probe_graph_state()
    packet = PROBE._acceptance_criteria_evidence_packet(result.final_graph)
    rendered = json.dumps(_jsonable(packet.content), sort_keys=True)

    assert "rook.acceptance_criteria_packet:v1" not in rendered
    assert "source_class" not in rendered
    assert "source_set" not in rendered
    assert "unresolved_intent" not in rendered
    assert "fingerprint" not in rendered
```

This may pass before implementation; it locks the no-visible-shape-drift requirement.

- [ ] **Step 6: Run RED tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm5k_worker_probe.py::test_acceptance_criteria_v3_calls_extractor_and_assembler `
  -q
```

Expected before implementation:

```text
FAILED ... AttributeError
```

or:

```text
FAILED ... assert {'extract': 0, 'assemble': 0} == {'extract': 1, 'assemble': 1}
```

- [ ] **Step 7: Commit RED tests**

```powershell
git add mcp_server\tests\test_lm5k_worker_probe.py
git commit -m "test(lm5y): require joined acceptance criteria construction"
```

## Task 2: Wire LM5K V3 Construction Through LM5W/LM5X

**Files:**
- Modify: `scripts/lm5k_worker_probe.py`

- [ ] **Step 1: Import the LM5W/LM5X functions**

Add near the other `rook.agent...` imports:

```python
from rook.agent.local_worker_acceptance_criteria import (
    assemble_acceptance_criteria_packet,
)
from rook.agent.local_worker_acceptance_criteria_sources import (
    extract_acceptance_criteria_sources,
)
```

- [ ] **Step 2: Add a legacy source constant**

Near the evidence packet constants, add:

```python
ACCEPTANCE_CRITERIA_LEGACY_SOURCE = (
    "workflow_contract + create_script.initial_execution_params + "
    "create_script.receipt.script_receipt.repair_anchor + script_body_gotcha"
)
```

Do not change packet ids, scenario ids, scenario versions, or packet titles.

- [ ] **Step 3: Replace or retire the hand-built `_acceptance_criteria()` implementation**

Replace the current hand-built `_acceptance_criteria()` body with a graph-aware helper:

```python
def _acceptance_criteria(graph) -> dict:
    sources = extract_acceptance_criteria_sources(
        workflow_contract=_probe_contract(),
        graph=graph,
        convention_packets=(_script_body_gotcha_packet(),),
    )
    packet = assemble_acceptance_criteria_packet(sources)
    return {
        "source": ACCEPTANCE_CRITERIA_LEGACY_SOURCE,
        "criteria": [
            {
                "criterion_id": criterion["criterion_id"],
                "description": criterion["description"],
                "source": criterion["source"],
            }
            for criterion in packet["criteria"]
        ],
    }
```

If the existing function name conflicts with tests or readability, keep the name and change only its signature/body. Do not expose `packet["fingerprint"]`, `packet["schema"]`, `packet["source_set"]`, `packet["unresolved_intent"]`, or `criterion["source_class"]`.

- [ ] **Step 4: Update the v3 packet builder call site**

In `_acceptance_criteria_evidence_packet(graph)`, change:

```python
"acceptance_criteria": _acceptance_criteria(),
```

to:

```python
"acceptance_criteria": _acceptance_criteria(graph),
```

- [ ] **Step 5: Run the RED test and full LM5K file**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm5k_worker_probe.py::test_acceptance_criteria_v3_calls_extractor_and_assembler `
  mcp_server\tests\test_lm5k_worker_probe.py::test_acceptance_criteria_v3_uses_assembled_legacy_projection `
  mcp_server\tests\test_lm5k_worker_probe.py::test_acceptance_criteria_v3_hides_assembled_packet_metadata `
  -q
```

Expected:

```text
3 passed
```

Then run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm5k_worker_probe.py `
  -q
```

Expected: all tests in the file pass. The exact count may increase from the new tests.

- [ ] **Step 6: Commit the join implementation**

```powershell
git add scripts\lm5k_worker_probe.py mcp_server\tests\test_lm5k_worker_probe.py
git commit -m "feat(lm5y): join acceptance criteria construction"
```

## Task 3: Update Import Guards For The Intentional Join

**Files:**
- Modify: `mcp_server/tests/test_local_worker_acceptance_criteria.py`
- Modify: `mcp_server/tests/test_local_worker_acceptance_criteria_sources.py`
- Modify only if necessary: `mcp_server/tests/test_lm5r_two_pass_publication_probe.py`

- [ ] **Step 1: Run the boundary guard test files to expose old guard failures**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_local_worker_acceptance_criteria.py::test_probe_scripts_do_not_import_acceptance_criteria_boundary `
  mcp_server\tests\test_local_worker_acceptance_criteria_sources.py `
  -q
```

Expected before guard update:

```text
FAILED test_probe_scripts_do_not_import_acceptance_criteria_boundary
FAILED test_probe_scripts_do_not_import_acceptance_criteria_sources
```

The failures occur because `scripts/lm5k_worker_probe.py` now intentionally
imports both the assembler and extractor.

- [ ] **Step 2: Update the LM5W assembler import guard**

In `test_probe_scripts_do_not_import_acceptance_criteria_boundary`, change the
test so it only checks `scripts/lm5r_two_pass_publication_probe.py` for direct
assembler imports.

Replace:

```python
for relative in (
    "scripts/lm5k_worker_probe.py",
    "scripts/lm5r_two_pass_publication_probe.py",
):
```

with:

```python
for relative in ("scripts/lm5r_two_pass_publication_probe.py",):
```

Keep the AST import check.

- [ ] **Step 3: Update the LM5X extractor import guard**

In `test_probe_scripts_do_not_import_acceptance_criteria_sources`, change the test so it only checks `scripts/lm5r_two_pass_publication_probe.py` for the extractor import.

Replace:

```python
for relative in (
    "scripts/lm5k_worker_probe.py",
    "scripts/lm5r_two_pass_publication_probe.py",
):
```

with:

```python
for relative in ("scripts/lm5r_two_pass_publication_probe.py",):
```

Keep both the raw source and AST import checks.

- [ ] **Step 4: Add a positive guard for LM5K's allowed imports**

Add this test near the probe import guard:

```python
def test_lm5k_probe_is_the_only_probe_script_joining_acceptance_sources():
    root = Path(__file__).resolve().parents[2]
    lm5k_source = (root / "scripts" / "lm5k_worker_probe.py").read_text(
        encoding="utf-8"
    )
    lm5r_source = (
        root / "scripts" / "lm5r_two_pass_publication_probe.py"
    ).read_text(encoding="utf-8")

    assert "local_worker_acceptance_criteria import" in lm5k_source
    assert "local_worker_acceptance_criteria_sources import" in lm5k_source
    assert "local_worker_acceptance_criteria_sources" not in lm5r_source
    assert "local_worker_acceptance_criteria import" not in lm5r_source
```

This pins the LM5Y import-rule shift without allowing LM5R to couple directly to the assembler/extractor.

- [ ] **Step 5: Ensure no LM5R test import guard needs a matching update**

Search:

```powershell
rg -n "local_worker_acceptance_criteria|local_worker_acceptance_criteria_sources" `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py
```

If no output appears, do not edit `test_lm5r_two_pass_publication_probe.py`.

If an existing guard appears there and references LM5K as forbidden, update it to match the same rule:

```text
LM5K may import LM5W/LM5X.
LM5R may not import LM5W/LM5X directly.
```

- [ ] **Step 6: Run guard tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_local_worker_acceptance_criteria.py `
  mcp_server\tests\test_local_worker_acceptance_criteria_sources.py `
  -q
```

Expected:

```text
all tests pass
```

- [ ] **Step 7: Commit guard update**

```powershell
git add `
  mcp_server\tests\test_local_worker_acceptance_criteria.py `
  mcp_server\tests\test_local_worker_acceptance_criteria_sources.py
git commit -m "test(lm5y): allow lm5k acceptance source join"
```

If `test_lm5r_two_pass_publication_probe.py` was touched, include it in the commit.

## Task 4: Visible Evidence Stability And Leak Guards

**Files:**
- Modify: `mcp_server/tests/test_lm5k_worker_probe.py`

- [ ] **Step 1: Strengthen the v3 visible packet test**

In `test_acceptance_criteria_evidence_v3_fields_are_bounded_and_provenance_tagged`, keep all existing assertions and add these assertions after the acceptance criteria shape checks:

```python
    assert acceptance == {
        "source": (
            "workflow_contract + create_script.initial_execution_params + "
            "create_script.receipt.script_receipt.repair_anchor + script_body_gotcha"
        ),
        "criteria": [
            {
                "criterion_id": "output_a_assigned",
                "description": "Output A must be assigned.",
                "source": "create_script.initial_execution_params.pins_out",
            },
            {
                "criterion_id": "output_a_double_compatible",
                "description": "Output A must be double-compatible.",
                "source": "create_script.initial_execution_params.pins_out",
            },
            {
                "criterion_id": "verify_repair_succeeds",
                "description": (
                    "The repaired body must satisfy the verify_repair "
                    "expected_outcome: succeeded."
                ),
                "source": "workflow_contract.rules.verify_repair.expected_outcome",
            },
            {
                "criterion_id": "preserve_body_mode",
                "description": "The repair must preserve body-style code.",
                "source": "script_body_gotcha",
            },
            {
                "criterion_id": "resolve_target_diagnostics",
                "description": (
                    "The repair must resolve the current target diagnostics."
                ),
                "source": (
                    "create_script.receipt.script_receipt.repair_anchor."
                    "target_errors"
                ),
            },
            {
                "criterion_id": "remove_unresolved_symbol",
                "description": (
                    "The repaired body must not leave DefinitelyMissingSymbol "
                    "unresolved."
                ),
                "source": (
                    "create_script.receipt.script_receipt.repair_anchor."
                    "target_errors"
                ),
            },
        ],
    }
```

If this exact assertion duplicates existing weaker checks, leave the exact assertion and remove only truly redundant local lines if needed for readability.

- [ ] **Step 2: Strengthen rendered envelope leak checks**

In `test_acceptance_criteria_v3_does_not_publish_replacement_literals`, add:

```python
    assert "rook.acceptance_criteria_packet:v1" not in rendered
    assert "source_class" not in rendered
    assert "source_set" not in rendered
    assert "unresolved_intent" not in rendered
    assert "fingerprint" not in rendered
```

Do not remove the existing hidden answer checks.

- [ ] **Step 3: Run LM5K tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm5k_worker_probe.py `
  -q
```

Expected: all tests pass.

- [ ] **Step 4: Commit stability guard update**

```powershell
git add mcp_server\tests\test_lm5k_worker_probe.py
git commit -m "test(lm5y): pin visible acceptance evidence"
```

## Task 5: Final Verification And Review

**Files:**
- No code changes expected.

- [ ] **Step 1: Run targeted deterministic gate**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm5k_worker_probe.py `
  mcp_server\tests\test_local_worker_acceptance_criteria_sources.py `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py `
  -q
```

Expected: all tests pass.

- [ ] **Step 2: Run nearby gate**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_local_worker_acceptance_criteria.py `
  mcp_server\tests\test_local_worker_acceptance_criteria_sources.py `
  mcp_server\tests\test_lm5k_worker_probe.py `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py `
  -q
```

Expected: all tests pass.

- [ ] **Step 3: Run Python 3.10 compile**

Run:

```powershell
py -3.10 -m py_compile `
  scripts\lm5k_worker_probe.py `
  mcp_server\tests\test_lm5k_worker_probe.py `
  mcp_server\tests\test_local_worker_acceptance_criteria.py `
  mcp_server\tests\test_local_worker_acceptance_criteria_sources.py
```

If `test_lm5r_two_pass_publication_probe.py` was touched, include it:

```powershell
py -3.10 -m py_compile `
  scripts\lm5k_worker_probe.py `
  mcp_server\tests\test_lm5k_worker_probe.py `
  mcp_server\tests\test_local_worker_acceptance_criteria.py `
  mcp_server\tests\test_local_worker_acceptance_criteria_sources.py `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py
```

Expected: exit code `0`.

- [ ] **Step 4: Confirm exact diff scope**

Run:

```powershell
$expected = @(
  "docs/superpowers/plans/2026-07-05-lm5y-acceptance-criteria-join.md",
  "docs/superpowers/specs/2026-07-05-lm5y-acceptance-criteria-join-design.md",
  "scripts/lm5k_worker_probe.py",
  "mcp_server/tests/test_lm5k_worker_probe.py",
  "mcp_server/tests/test_local_worker_acceptance_criteria.py",
  "mcp_server/tests/test_local_worker_acceptance_criteria_sources.py"
)
$actual = git diff --name-only main..HEAD
Compare-Object $expected $actual
```

Expected: no output.

If `test_lm5r_two_pass_publication_probe.py` was legitimately touched for an import guard, add it to `$expected`.

- [ ] **Step 5: Confirm no forbidden production drift**

Run:

```powershell
$matches = git diff --name-only main..HEAD |
  rg "mcp_server/src/rook/agent/local_worker_acceptance_criteria\.py|mcp_server/src/rook/agent/local_worker_acceptance_criteria_sources\.py|mcp_server/src/rook/agent/__init__\.py|scripts/lm5r_two_pass_publication_probe\.py"
if ($LASTEXITCODE -eq 1) { exit 0 }
$matches
exit $LASTEXITCODE
```

Expected: no output and exit code `0`.

- [ ] **Step 6: Run diff check and status**

Run:

```powershell
git diff --check main..HEAD
git status --short --branch
```

Expected:

```text
git diff --check main..HEAD
# no output

## codex/lm5y-acceptance-criteria-join
# known unrelated untracked files may remain
```

- [ ] **Step 7: Request final code review**

Request a final review over `main..HEAD`. Include:

```text
LM5Y should only join v3 acceptance criteria construction through LM5W/LM5X.
Worker-visible v3 packet must remain legacy-shaped and unchanged.
No mcp_server/src changes.
No LM5R runtime changes.
No manifest/artifact changes.
No live run in PR.
```

- [ ] **Step 8: Commit final verification/doc updates if any**

If Task 5 required any plan/doc correction, commit it:

```powershell
git add docs\superpowers\plans\2026-07-05-lm5y-acceptance-criteria-join.md
git commit -m "docs(lm5y): finalize acceptance criteria join plan"
```

If no files changed, do not create an empty commit.

## Post-Merge Runbook

After the implementation PR merges, from clean synced `main`, run:

```powershell
cd C:\UDEV\Rook

.\mcp_server\.venv\Scripts\python.exe scripts\lm5r_two_pass_publication_probe.py `
  --scenario evidence_absent_like `
  --scenario evidence_present_v3_like `
  --attempts 5
```

Report:

```text
run_dir
manifest commit
model + quantization
Ollama version
pass1 instruction version/hash
total rows
status counts overall and by scenario
published and LM5G-loadable counts
pass1/pass2 kind counts by scenario
action_request counts by scenario
observation_action_intent_anomaly_count by scenario
failure_reason counts
representative action inputs / clarifications
hidden answer leak check for PROBE_REPAIR_CODE / A = 42.0
```

Do not commit `probe_runs/`.
Do not write a curated evidence summary until the live rerun result is reviewed.
