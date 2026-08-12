# Prime Point-Row Repair Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans with Inline Execution. This is one tightly coupled disposable task; no subagent handoff is intended.

**Goal:** Build and inertly qualify one disposable Prime/Qwen operator that evaluates an initial Grasshopper result and permits at most one same-session repair turn.

**Architecture:** Adapt the proven Qwen operator in a fresh temporary sibling. PowerShell owns the bounded two-phase process state machine; the existing Python inspector owns exact feedback projection and authentic operator snapshots. The merged evaluator remains unchanged and owns semantic outcomes.

**Tech Stack:** PowerShell 7, Python 3.11, pytest, Prime Agent 0.7.0, existing `rook_full` MCP skill, existing point-row evaluator.

## Global Constraints

- Base is exact merge `ad4d3b2798ab38b2245d7d9d12fdadd344b16de5`.
- Disposable root is `C:/Users/bring/AppData/Local/Temp/prime-rook-qwen-point-row-repair-loop-v1`.
- Prime and Rook repositories receive no production changes.
- Initial and optional repair turns use one exact persisted Prime session.
- Evaluator `pass` alone permits success; `fail` and `incomplete` admit one repair and otherwise block completion.
- No retry, cleanup, fallback model, Opus call, Critic call, second campaign, MCP pooling, or topology advice.
- Offline verification excludes Anthropic live tests and unrelated containment/panel-lock failures.
- Stop after one independent pre-contact review. Target freezing and the live transaction remain separately authorized.

---

### Task 1: Construct and inertly qualify the disposable repair loop

**Files:**

- Copy unchanged common artifacts from: `C:/Users/bring/AppData/Local/Temp/prime-rook-qwen-strict-retest-v1/local/`
- Create/adapt: `C:/Users/bring/AppData/Local/Temp/prime-rook-qwen-point-row-repair-loop-v1/operator/run.ps1`
- Create/adapt: `C:/Users/bring/AppData/Local/Temp/prime-rook-qwen-point-row-repair-loop-v1/operator/inspection.py`
- Create: `C:/Users/bring/AppData/Local/Temp/prime-rook-qwen-point-row-repair-loop-v1/operator/test_repair_loop.py`
- Create/update frozen disposable contracts: `operator/row.json`, `operator/manifest.json`, `operator/evidence-contract.json`, `operator/intent.txt`
- Copy unchanged: `operator/acceptance.json`, `operator/evaluator.py`, agent settings/model/skill/adapter, checkpoint, requirements, kernel, and dependency evidence

**Interfaces:**

- `inspection.build_repair_feedback(intent: str, evaluation: dict) -> dict` copies the six ordered `{criterion_id,status,evidence}` entries and adds only the closed repair boundary.
- `inspection.run_snapshot(row_path: Path, target_path: Path, process_ledger_path: Path, prime_jsonl: Path, session_path: Path, evidence_path: Path, remaining_seconds: float) -> bool` retains an authentic create-new request/result JSONL after one admitted Prime phase.
- `run.ps1::Invoke-PrimePhase([string]$Phase, [string]$Prompt, [AllowEmptyString()][string]$ResumeSessionPath, [double]$RemainingSeconds) -> hashtable` launches one owned Prime process and returns its exact stdout, stderr, ledger, session, elapsed time, and admission status.
- `run.ps1::Invoke-IndependentSnapshot([int]$Phase, [hashtable]$PhaseResult, [double]$RemainingSeconds) -> bool` invokes the inspector once for that admitted phase.
- `run.ps1::Invoke-PhaseEvaluation([int]$Phase) -> hashtable` invokes the frozen evaluator once and retains its exact result.
- `run.ps1::Invoke-RepairLoop([string]$RequestedRowPath) -> int` performs exactly one initial snapshot/evaluation and conditionally one same-session repair snapshot/evaluation.

- [ ] **Step 1: Create a fresh sibling without consumed evidence**

Copy only immutable configuration, kernel, skill, adapter, dependency artifacts, and operator sources. Exclude all existing sessions, logs, target, snapshots, evaluations, stdout, stderr, and process ledgers.

Required initial absence:

```text
agent/sessions/*.jsonl
operator/target.json
operator/initial-inspection.jsonl
operator/initial-prime.jsonl
operator/repair-prime.jsonl
operator/phase-1-snapshot.jsonl
operator/phase-2-snapshot.jsonl
operator/evaluation-1.json
operator/evaluation-2.json
operator/repair-feedback.json
```

- [ ] **Step 2: Copy the merged semantic authorities unchanged**

Copy from the merge-based worktree:

```text
scripts/grasshopper_point_row_acceptance.json -> operator/acceptance.json
scripts/grasshopper_point_row_acceptance.py   -> operator/evaluator.py
```

Assert SHA-256:

```text
acceptance.json = 376C429878536C01B58DB403F440DD54C612AD627299C1EA62CA533B4A39A7C0
evaluator.py    = 0CB6DE02B86D3A2B7B5D6D5F59AFC10365D0AB4D23DF1E4ED2119D136377BC80
```

- [ ] **Step 3: Write RED tests for exact feedback projection**

Tests must require:

```python
feedback == {
    "original_intent": EXACT_INTENT,
    "criteria": [
        {
            "criterion_id": item["criterion_id"],
            "status": item["status"],
            "evidence": item["evidence"],
        }
        for item in evaluation["criteria"]
    ],
    "repair_boundary": {
        "turns_remaining": 1,
        "may_inspect_before_repair": True,
        "may_modify": "execution_owned_components_only",
    },
}
```

Reject wrong overall values, missing/extra/reordered criteria, unknown criterion IDs, statuses outside `pass/fail/unproven`, altered evidence, extra diagnosis/topology keys, and non-object evidence.

Run:

```powershell
$root = 'C:/Users/bring/AppData/Local/Temp/prime-rook-qwen-point-row-repair-loop-v1'
& "$root/kernel-venv/Scripts/python.exe" "$root/operator/test_repair_loop.py" -v
```

Expected: failure because the feedback helper and orchestration seam do not exist.

- [ ] **Step 4: Write RED causal orchestration tests**

Use inert fakes around `Invoke-PrimePhase`, `Invoke-IndependentSnapshot`, and `Invoke-PhaseEvaluation`. Prove these exact timelines:

```text
evaluation-1 pass:
  prime:initial -> snapshot:1 -> evaluate:1 -> stop:pass

evaluation-1 fail or incomplete, evaluation-2 pass:
  prime:initial -> snapshot:1 -> evaluate:1
  -> feedback -> prime:resume:<same-session>
  -> snapshot:2 -> evaluate:2 -> stop:pass

evaluation-2 fail or incomplete:
  same prefix -> stop:<exact non-pass>; no third Prime call
```

Also prove lifecycle/target/write/evaluator/timeout failures stop at their exact prefix, and first-pass creates no repair artifacts.

- [ ] **Step 5: Implement strict feedback and generic snapshot custody**

In `inspection.py`:

```python
CRITERION_IDS = (
    "adjustable_controls_present",
    "point_count_equals_count",
    "first_x_equals_start",
    "successive_x_difference_equals_step",
    "all_yz_zero",
    "no_runtime_errors",
)

def build_repair_feedback(intent: str, evaluation: dict) -> dict:
    if set(evaluation) != {
        "schema", "acceptance_schema", "snapshot_sha256",
        "overall", "failure_ids", "criteria",
    } or evaluation["overall"] not in {"fail", "incomplete"}:
        raise ValueError("invalid_evaluation")
    criteria = evaluation["criteria"]
    if not isinstance(criteria, list) or tuple(
        item.get("criterion_id") for item in criteria if isinstance(item, dict)
    ) != CRITERION_IDS:
        raise ValueError("invalid_criteria")
    projected = []
    for item in criteria:
        if set(item) != {"criterion_id", "status", "failure_ids", "evidence"}:
            raise ValueError("invalid_criterion")
        if item["status"] not in {"pass", "fail", "unproven"}:
            raise ValueError("invalid_status")
        if not isinstance(item["evidence"], dict):
            raise ValueError("invalid_evidence")
        projected.append({
            key: item[key]
            for key in ("criterion_id", "status", "evidence")
        })
    return {
        "original_intent": intent,
        "criteria": projected,
        "repair_boundary": {
            "turns_remaining": 1,
            "may_inspect_before_repair": True,
            "may_modify": "execution_owned_components_only",
        },
    }

async def run_snapshot(
    row_path: Path,
    target_path: Path,
    process_ledger_path: Path,
    prime_jsonl: Path,
    session_path: Path,
    evidence_path: Path,
    remaining_seconds: float,
) -> bool:
    try:
        row = _load_json(row_path)
        target = _load_json(target_path)
        ledger = _load_json(process_ledger_path)
        facts = {
            "natural": ledger.get("naturalTermination") is True,
            "evidence": (
                prime_jsonl_has_terminal_agent_end(prime_jsonl)
                and _jsonl_valid(session_path)
            ),
            "remaining": ledger.get("remaining"),
            "primeExitCode": ledger.get("primeExitCode"),
        }
        if not final_evidence_eligible(facts) or remaining_seconds <= 0:
            return False
        process_id = _positive(target["processId"])
        native_port = _positive(target["nativePort"])
        if not target_matches(process_id, native_port):
            return False
        handle = _open_evidence(evidence_path)
    except (OSError, UnicodeError, ValueError, TypeError, KeyError):
        return False
    completed = False
    try:
        try:
            _write_and_flush(
                handle,
                "request",
                {"name": SNAPSHOT_NAME, "arguments": SNAPSHOT_ARGUMENTS},
            )
        except (OSError, UnicodeError, ValueError, TypeError):
            return False
        os.environ.update(target_environment(target))
        try:
            async with asyncio.timeout(remaining_seconds):
                returned = await _call_snapshot(
                    SNAPSHOT_NAME,
                    dict(SNAPSHOT_ARGUMENTS),
                )
        except Exception:
            return False
        try:
            _write_and_flush(handle, "result", returned)
        except (OSError, UnicodeError, ValueError, TypeError):
            return False
        completed = target_matches(process_id, native_port)
    finally:
        try:
            handle.close()
        except OSError:
            completed = False
    return completed
```

Keep snapshot arguments exactly:

```json
{"include_data":true,"max_preview_items":3}
```

- [ ] **Step 6: Implement the two-phase PowerShell state machine**

`Invoke-RepairLoop` must:

1. Admit frozen hashes, model manifest, target, empty initial evidence, one-shot paths, and total 1800-second ceiling.
2. Run the exact original intent once with `--offline --no-extensions --mode json --model ollama_chat/qwen3.6:35b --thinking medium`.
3. Require one final `agent_end`, one native session, natural process termination, zero owned children, unchanged target/runtime/model/hash custody.
4. Snapshot and run evaluator 1 once.
5. Stop immediately on `pass`.
6. On `fail` or `incomplete`, write exact feedback create-new and run Prime once with `--resume <exact sole session path>` plus the canonical feedback JSON.
7. Require the same session path remains the sole session and repeat lifecycle custody.
8. Snapshot and run evaluator 2 once, then stop on its exact outcome.

No loop construct may surround Prime, snapshot, or evaluator calls.

- [ ] **Step 7: Freeze disposable contracts and hashes**

Update the row to declare:

```json
{
  "actorTurnsMaximum": 2,
  "repairsMaximum": 1,
  "evaluationsMaximum": 2,
  "operatorSnapshotsMaximum": 2,
  "totalWallClockSeconds": 1800,
  "primeSessionCount": 1,
  "rookSourceMerge": "ad4d3b2798ab38b2245d7d9d12fdadd344b16de5"
}
```

Retain the existing Qwen manifest/layer identity and common artifact hashes. Manifest every frozen file, including acceptance and evaluator. Do not include future target or evidence files until the target-freeze phase.

- [ ] **Step 8: Run the complete inert gate**

Run:

```powershell
$root = 'C:/Users/bring/AppData/Local/Temp/prime-rook-qwen-point-row-repair-loop-v1'
& "$root/kernel-venv/Scripts/python.exe" "$root/operator/test_repair_loop.py" -v
& "$root/kernel-venv/Scripts/python.exe" -m py_compile `
  "$root/operator/inspection.py" `
  "$root/operator/evaluator.py" `
  "$root/operator/test_repair_loop.py"
```

Then verify every manifest hash, exact Qwen manifest/blob presence, Prime `c98941a2`, Rook branch base `ad4d3b27`, no target/evidence/session files, and no qualification-owned processes.

- [ ] **Step 9: Record the implementation delta and stop for one review**

Report:

- exact disposable changed/copied files and hashes;
- inert test count and command;
- adapter, skill, Prime, Qwen manifest, acceptance, and evaluator identities;
- proof that target, empty snapshot, Prime/session/evaluation evidence, and live contact are absent;
- confirmation that repository production code is unchanged.

Request one independent pre-contact review. Do not create `target.json`, contact Rhino/Ollama/MCP, or start Prime before approval.

---

## Post-Review Continuation

After approval, corroborate the currently opened fresh Grasshopper document, perform one explicitly authorized read-only empty-canvas snapshot, freeze target/manifest evidence, rerun the inert gate, and stop for one authorization covering the complete Actor/evaluate/optional-repair/final-evaluate transaction.
