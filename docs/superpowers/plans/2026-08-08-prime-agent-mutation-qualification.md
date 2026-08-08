# Prime Agent Supervised Mutation Qualification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and inertly qualify one disposable Prime Agent sibling that may mutate one fresh Grasshopper canvas through Rook's full, panel-locked MCP surface and then retain one independent final snapshot.

**Architecture:** Reuse the proven readonly Prime adapter byte-for-byte except for the reviewed identity/profile substitutions, derive one Prime-compatible skill from the merge-owned `execute-grasshopper` skill, and run the exact comparison intent through one isolated Prime process. After normal Prime termination, one small operator helper reconstructs the frozen target, writes the fixed inspection request before dispatch, invokes exactly one canonical `gh_snapshot`, and retains the exact returned value.

**Tech Stack:** Windows PowerShell, Python 3.11, `unittest`, Prime Agent commit `c98941a2`, Prime's `McpIntegration`, MCP Python SDK `1.28.0`, deployed Rook MCP, Ollama OpenAI-completions compatibility, Grasshopper.

## Global Constraints

- Bind all source skill and Rook documentation evidence to exact merge `2187bbcee26b6eaf94007dc400a60203203f86ae`.
- Create no Rook or Prime repository production/test changes.
- Create exactly one disposable root: `C:/Users/bring/AppData/Local/Temp/prime-rook-full-mutation-qualification`.
- Preserve the primary checkout and every existing disposable qualification directory unchanged.
- The only adapter deltas from v2 are `readonly -> full` and the reviewed `rook_readonly`/`RookReadonly`/`rook-readonly` to `rook_full`/`RookFull`/`rook-full` identity substitutions.
- Use exact model `ollama/qwen3.6:35b` and exact credential-free API base `http://127.0.0.1:11434/v1`.
- Preserve the exact intent: `Create a Grasshopper definition that generates a row of points along the X axis using adjustable Start, Step, and Count controls, with Y and Z fixed at zero.`
- Use only offline dependency installation from local caches/checkouts; missing material is a blocker, not authorization for network contact.
- No model, Ollama, MCP, Rook, Rhino, or Grasshopper contact is permitted during implementation or inert review.
- One independent pre-contact review is mandatory after all inert tests and hashes pass.
- The later live authorization permits exactly one Prime process and exactly one operator-owned final snapshot, with no operator rerun, adapter retry, cleanup, or fallback.
- Prime may follow the reviewed skill's bounded correction method; the operator must not prescribe topology, components, tool count, or implementation language.
- Do not add a framework, registry, schema copy, dispatch table, recorder platform, scoring system, database, or reusable evidence abstraction.

## File Map

The task creates these disposable files outside both repositories:

- `C:/Users/bring/AppData/Local/Temp/prime-rook-full-mutation-qualification/agent/settings.json` — isolated Prime settings with built-ins, packages, and extensions disabled.
- `C:/Users/bring/AppData/Local/Temp/prime-rook-full-mutation-qualification/agent/models.json` — exact local Ollama provider/model definition.
- `C:/Users/bring/AppData/Local/Temp/prime-rook-full-mutation-qualification/agent/skills/rook-full/pyproject.toml` — local skill package metadata with `mcp==1.28.0`.
- `C:/Users/bring/AppData/Local/Temp/prime-rook-full-mutation-qualification/agent/skills/rook-full/src/rook_full/__init__.py` — transport-only full-profile sibling of the proven v2 adapter.
- `C:/Users/bring/AppData/Local/Temp/prime-rook-full-mutation-qualification/agent/skills/prime-execute-grasshopper/SKILL.md` — minimal Prime preamble plus exact reviewed skill body.
- `C:/Users/bring/AppData/Local/Temp/prime-rook-full-mutation-qualification/agent/skills/prime-execute-grasshopper/references/checkpoint-protocol.md` — exact merge-owned reference bytes.
- `C:/Users/bring/AppData/Local/Temp/prime-rook-full-mutation-qualification/operator/run.ps1` — closed-row, one-shot Prime launcher and final-inspection handoff.
- `C:/Users/bring/AppData/Local/Temp/prime-rook-full-mutation-qualification/operator/final_inspection.py` — evidence admission, Windows target corroboration, fixed snapshot call, and two-row evidence writer.
- `C:/Users/bring/AppData/Local/Temp/prime-rook-full-mutation-qualification/operator/test_adapter.py` — complete inert causal test seam.
- `C:/Users/bring/AppData/Local/Temp/prime-rook-full-mutation-qualification/operator/offline-install-commands.txt` — exact offline setup commands actually executed.
- `C:/Users/bring/AppData/Local/Temp/prime-rook-full-mutation-qualification/operator/manifest.json` — SHA-256 inventory of reviewed static artifacts and, after live preflight, the frozen row.
- `C:/Users/bring/AppData/Local/Temp/prime-rook-full-mutation-qualification/operator/row.json` — absent during inert implementation; atomically created after pre-contact approval with the exact model, API base, intent, derived-skill path/hashes, checkpoint path/hash, and real reviewed target.
- `C:/Users/bring/AppData/Local/Temp/prime-rook-full-mutation-qualification/operator/prime.jsonl` — exclusively created by the one live launcher.
- `C:/Users/bring/AppData/Local/Temp/prime-rook-full-mutation-qualification/operator/stderr.txt` — exclusively created by the one live launcher.
- `C:/Users/bring/AppData/Local/Temp/prime-rook-full-mutation-qualification/operator/final-inspection.jsonl` — exclusively created after Prime termination or post-Prime refusal.

The only repository modification during implementation is the evidence ledger in this plan after the mandatory review. The disposable implementation itself is not promoted into either repository.

---

### Task 1: Build and inertly qualify the disposable mutation sibling

**Files:**

- Create: the disposable files listed in **File Map** except live evidence and `row.json`
- Read unchanged: `C:/Users/bring/AppData/Local/Temp/prime-rook-readonly-qualification-v2/agent/skills/rook-readonly/src/rook_readonly/__init__.py`
- Read unchanged: `C:/Users/bring/AppData/Local/Temp/prime-rook-readonly-qualification-v2/agent/skills/rook-readonly/pyproject.toml`
- Read unchanged: `C:/UDEV/Rook/.worktrees/prime-agent-mutation-qualification-design/.agents/skills/execute-grasshopper/SKILL.md`
- Read unchanged: `C:/UDEV/Rook/.worktrees/prime-agent-mutation-qualification-design/.agents/skills/execute-grasshopper/references/checkpoint-protocol.md`
- Modify after review only: `docs/superpowers/plans/2026-08-08-prime-agent-mutation-qualification.md`

**Interfaces:**

- Consumes: proven v2 `McpIntegration._open_session(AsyncExitStack) -> ClientSession`, exact Prime model configuration, merge-owned skill bytes, reviewed row, and deployed panel-locked Rook environment.
- Produces: importable singleton `rook_full`, the exact operator entry `run.ps1 -RowPath C:/Users/bring/AppData/Local/Temp/prime-rook-full-mutation-qualification/operator/row.json`, and `final_inspection.run(row_path: Path, lifecycle_natural: bool) -> bool`; `True` means a complete request/result record was flushed, while refusal or operational failure returns `False` and retains only the evidence permitted by the specification.
- Final evidence: complete `refusal`, complete `request -> result`, valid request-only evidence, or the explicitly permitted failed-write byte prefix.

- [ ] **Step 1: Reconfirm immutable source evidence before creating the sibling**

Run these read-only commands:

```powershell
$Lane = 'C:/UDEV/Rook/.worktrees/prime-agent-mutation-qualification-design'
$V2 = 'C:/Users/bring/AppData/Local/Temp/prime-rook-readonly-qualification-v2'
$Root = 'C:/Users/bring/AppData/Local/Temp/prime-rook-full-mutation-qualification'

git -C $Lane rev-parse HEAD
git -C $Lane status --short
git -C D:/prime-agent rev-parse HEAD
git -C D:/prime-agent status --short
Get-FileHash "$V2/agent/skills/rook-readonly/src/rook_readonly/__init__.py" -Algorithm SHA256
Get-FileHash "$Lane/.agents/skills/execute-grasshopper/SKILL.md" -Algorithm SHA256
Get-FileHash "$Lane/.agents/skills/execute-grasshopper/references/checkpoint-protocol.md" -Algorithm SHA256
Test-Path -LiteralPath $Root
```

Expected:

- exact design commits `9aabe182f68038c92511a48bddf1d152f4bc504c` and `7c3bdab21373d6a7113f08615316d3a2388ff8a8` are ancestors of the implementation lane, whose actual plan commit is recorded in the ledger before work begins;
- lane worktree is clean;
- Prime HEAD is `c98941a2` and its worktree is clean;
- reviewed skill hash is `6858503160507411D5C227B36B4576FE6BA885A45B6D6A0F7EFA8B26BDA5040B`;
- v2 adapter hash is `E8B3BC41AA6DB224F430A80B52614568AF31798771379C9C8F9F491D964A3FC4`; and
- the new sibling root does not exist.

If the sibling root exists, stop. Do not delete, reuse, or overwrite it.

- [ ] **Step 2: Create the inert test module first**

Create the directory skeleton and `operator/test_adapter.py`. Before the
implementation files exist, define these exact `unittest` cases:

- `AdapterParityTests.test_only_reviewed_identity_and_profile_substitutions_differ`
- `AdapterParityTests.test_open_session_uses_full_panel_locked_deployed_contract`
- `AdapterParityTests.test_stdio_errlog_has_real_fileno_and_stack_owned_lifetime`
- `AdapterParityTests.test_no_schema_copy_dispatch_retry_or_fallback`
- `DerivedSkillTests.test_preamble_only_maps_tool_names_to_rook_full`
- `DerivedSkillTests.test_reviewed_body_is_byte_exact_from_first_heading`
- `DerivedSkillTests.test_checkpoint_reference_is_byte_exact`
- `ClosedRowAndLauncherTests.test_exact_model_api_skill_intent_target_and_no_field_overrides`
- `ClosedRowAndLauncherTests.test_array_or_extra_row_fields_refuse_before_evidence`
- `ClosedRowAndLauncherTests.test_existing_stdout_stderr_session_or_inspection_refuses`
- `ClosedRowAndLauncherTests.test_launcher_uses_offline_no_extensions_and_full_profile`
- `PrimeEvidenceTests.test_nonzero_exit_with_natural_lifecycle_and_valid_evidence_is_eligible`
- `PrimeEvidenceTests.test_model_change_pair_and_every_assistant_identity_must_agree`
- `PrimeEvidenceTests.test_refusal_precedence_is_lifecycle_then_missing_then_invalid_then_target`
- `FinalInspectionTests.test_target_match_flushes_request_then_calls_once_then_flushes_exact_result`
- `FinalInspectionTests.test_target_or_listener_mismatch_writes_only_refusal_and_calls_zero`
- `FinalInspectionTests.test_request_write_or_flush_failure_calls_zero`
- `FinalInspectionTests.test_result_write_failure_occurs_after_one_call_without_fabrication`
- `FinalInspectionTests.test_invocation_exception_retains_request_and_bounded_status`
- `FinalInspectionTests.test_failed_snapshot_return_is_still_exact_result`

Import not-yet-created sibling modules inside individual test methods. Missing
artifacts must produce executed assertion failures; a module collection/import
failure is not a valid RED.

Use temporary directories and injected fakes only at these external boundaries:

```python
fake_stdio_client
fake_client_session
fake_prime_process
fake_native_discovery
fake_listener_owner
fake_rook_tools_call
fake_row_writer
```

The causal success test must assert exact ordering:

```python
self.assertEqual(
    observed,
    [
        "request_write",
        "request_flush",
        "snapshot_call",
        "result_write",
        "result_flush",
        "close",
    ],
)
self.assertEqual(snapshot_calls, [
    {
        "name": "gh_snapshot",
        "arguments": {"include_data": True, "max_preview_items": 3},
    }
])
```

The model test must use real Prime session shapes:

```python
{"type": "model_change", "provider": "ollama", "modelId": "qwen3.6:35b"}
{"type": "message", "message": {"role": "assistant", "provider": "ollama", "model": "qwen3.6:35b"}}
```

The refusal-precedence table is exact:

```python
[
    ("cancelled", "prime_termination_ineligible"),
    ("missing", "required_evidence_missing"),
    ("malformed_or_multiple_or_mismatch", "required_evidence_invalid"),
    ("target_or_listener", "target_mismatch"),
]
```

- [ ] **Step 3: Run the tests and verify valid RED behavior**

Use the already-proven v2 kernel only as an inert test interpreter:

```powershell
& 'C:/Users/bring/AppData/Local/Temp/prime-rook-readonly-qualification-v2/kernel-venv/Scripts/python.exe' `
  'C:/Users/bring/AppData/Local/Temp/prime-rook-full-mutation-qualification/operator/test_adapter.py' -v
```

Expected: tests load and fail because the new adapter, skill, launcher, final inspector, configuration, and manifest do not exist. Collection/import failure caused by a malformed test file is not a valid RED.

- [ ] **Step 4: Materialize the transport-only full adapter**

Create `rook-full/pyproject.toml` from the v2 file with only:

```text
prime-agent-skill-rook-readonly -> prime-agent-skill-rook-full
rook_readonly                  -> rook_full
```

Retain dependencies exactly:

```toml
dependencies = [
    "mcp==1.28.0",
    "prime-agent-runtime",
]
```

Create `rook_full/__init__.py` by applying only this reviewed normalization to the v2 source:

```text
RookReadonly -> RookFull
rook_readonly -> rook_full
rook-readonly -> rook-full
"ROOK_MCP_TOOL_PROFILE": "readonly"
->
"ROOK_MCP_TOOL_PROFILE": "full"
```

The resulting `_open_session()` must still contain the same stack-owned descriptor sequence:

```python
errlog = stack.enter_context(open(os.devnull, "w", encoding="utf-8"))
read, write = await stack.enter_async_context(
    stdio_client(parameters, errlog=errlog)
)
session = await stack.enter_async_context(ClientSession(read, write))
await session.initialize()
return session
```

Do not add methods, schemas, retries, wrappers, or policy logic.

- [ ] **Step 5: Materialize isolated Prime configuration and the derived skill**

Create `agent/settings.json` exactly:

```json
{
  "enableBuiltinSkills": false,
  "packages": [],
  "extensions": []
}
```

Create `agent/models.json` exactly:

```json
{
  "providers": {
    "ollama": {
      "baseUrl": "http://127.0.0.1:11434/v1",
      "api": "openai-completions",
      "apiKey": "ollama",
      "compat": {
        "supportsDeveloperRole": false,
        "supportsReasoningEffort": false
      },
      "models": [
        {"id": "qwen3.6:35b"}
      ]
    }
  }
}
```

Build `prime-execute-grasshopper/SKILL.md` deterministically. Its complete new
prefix is exactly:

```markdown
---
name: prime-execute-grasshopper
description: Use when Prime Agent is explicitly assigned a reviewed Grasshopper mutation qualification through Rook.
---

# Prime invocation compatibility

This disposable qualification skill uses the reviewed Rook method below.
In IPython, import `rook_full`. When the reviewed method names a Rook tool,
await the same-named attribute on `rook_full`, preserving the tool name and
keyword arguments exactly.
```

Append the exact source bytes from the first Markdown heading of merge-owned
`execute-grasshopper/SKILL.md` through EOF immediately after that prefix.

The preamble must not enumerate tools or mention a component, topology, C# script, slider, Series, point-row solution, expected call count, retry, or fallback. Copy `checkpoint-protocol.md` byte-for-byte to the derived skill's `references` directory.

- [ ] **Step 6: Implement the final-inspection helper with literal evidence ownership**

Create `operator/final_inspection.py` with these local interfaces:

```python
REFUSAL_REASONS = (
    "prime_termination_ineligible",
    "required_evidence_missing",
    "required_evidence_invalid",
    "target_mismatch",
)

SNAPSHOT_REQUEST = {
    "name": "gh_snapshot",
    "arguments": {"include_data": True, "max_preview_items": 3},
}

def classify_prime_evidence(root: Path, *, lifecycle_natural: bool) -> str | None:
    """Return the first refusal token, or None when evidence is eligible."""

def discover_native_target(discovery_root: Path, process_id: int) -> tuple[int, int] | None:
    """Return the unique exact (process_id, port) from an instance-*.json native record."""

def windows_listener_owner(port: int) -> int | None:
    """Return the unique listening PID from Get-NetTCPConnection, or None."""

async def run(row_path: Path, *, lifecycle_natural: bool) -> bool:
    """Write permitted evidence; true only after request and result both flush."""
```

`classify_prime_evidence()` must apply this order without falling through:

```text
non-natural lifecycle -> prime_termination_ineligible
missing prime.jsonl, stderr.txt, or session -> required_evidence_missing
malformed JSONL, multiple sessions, model/intent mismatch -> required_evidence_invalid
otherwise -> None
```

Prime identity is:

```text
at least one model_change
AND every model_change has provider == ollama and modelId == qwen3.6:35b
AND every assistant message carrying identity has provider == ollama and model == qwen3.6:35b
AND retained user intent equals the row intent exactly
```

Target admission must require one native discovery record whose exact integer `processId` and `port` equal the row, plus one Windows listener owner equal to the same PID. The helper may read `%LOCALAPPDATA%/Rook/discovery/instance-*.json` and invoke only this fixed OS query:

```powershell
Get-NetTCPConnection -State Listen -LocalPort $ReviewedPort -ErrorAction Stop |
  Select-Object -ExpandProperty OwningProcess -Unique
```

Set these exact variables from the row before importing `rook_full`:

```python
os.environ["ROOK_MCP_TARGET_MODE"] = "panel_locked"
os.environ["ROOK_MCP_TARGET_PROCESS_ID"] = str(row["rhino_target"]["process_id"])
os.environ["ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER"] = str(
    row["rhino_target"]["document_serial_number"]
)
os.environ["ROOK_MCP_TOOL_PROFILE"] = "full"
```

The writer must exclusively create `final-inspection.jsonl`, serialize compact UTF-8 JSON plus `\n`, and flush every complete row. It may produce only:

```python
{"kind": "refusal", "payload": {"reason": refusal_reason}}
{"kind": "request", "payload": SNAPSHOT_REQUEST}
{"kind": "result", "payload": returned_value}
```

Request failure means zero calls. Result failure happens after one call. Invocation exception retains request-only evidence and returns `inspection_failed` without promising exception-text retention. Do not reopen, truncate, repair, retry, or fabricate rows.

- [ ] **Step 7: Implement the one-shot PowerShell launcher**

Derive `operator/run.ps1` from the v2 launcher and retain its closed row checks, type-exact string/integer checks, exclusive evidence creation, isolated Prime environment, `--offline`, `--no-extensions`, JSON mode, and hidden process creation. Extend the closed row only with the approved `api_base` and `skill` custody fields. Require the API base to equal both the reviewed loopback value and `models.json`; require the resolved skill/reference paths and uppercase SHA-256 values to equal the actual files and static manifest before evidence creation.

Change only the qualification facts and the necessary post-Prime handoff:

```text
expected intent -> exact point-row comparison intent
readonly profile -> full
rook-readonly identity/path -> rook-full identity/path
existing-evidence set -> prime.jsonl, stderr.txt, any session, final-inspection.jsonl
after WaitForExit and both drain tasks -> call final_inspection.py once
```

The external launcher interface remains exactly:

```powershell
run.ps1 -RowPath C:/Users/bring/AppData/Local/Temp/prime-rook-full-mutation-qualification/operator/row.json
```

It accepts no model, API-base, intent, skill, profile, PID, port, document, retry, or output override. Set `lifecycle_natural` only after `WaitForExit()` and both stdout/stderr copy tasks complete. A nonzero Prime exit remains eligible. On cancellation, forced termination, failed drain, or failed evidence close, invoke the helper only to write `prime_termination_ineligible`; make no snapshot call.

- [ ] **Step 8: Record and execute offline-only environment installation**

Create `offline-install-commands.txt` with the exact commands before running them. Use:

```powershell
$Root = 'C:/Users/bring/AppData/Local/Temp/prime-rook-full-mutation-qualification'
$UvCache = 'C:/Users/bring/AppData/Local/uv/cache'
$PrimeWheel = "$Root/cache/prime_agent_runtime-0.1.0-py3-none-any.whl"

uv venv --offline --python 3.11 "$Root/kernel-venv"
uv pip install --offline --cache-dir $UvCache --python "$Root/kernel-venv/Scripts/python.exe" `
  $PrimeWheel mcp==1.28.0 ipykernel
uv pip install --offline --cache-dir $UvCache --python "$Root/kernel-venv/Scripts/python.exe" `
  --editable "$Root/agent/skills/rook-full"
```

Copy
`C:/Users/bring/AppData/Local/Temp/prime-rook-readonly-qualification-v2/cache/prime_agent_runtime-0.1.0-py3-none-any.whl`
to the new cache before the commands and require its source/destination SHA-256
values to match. If any artifact is absent from local storage or any command
attempts resolution outside the local cache, stop and report the blocker. Do not
add an index URL or relax offline mode.

- [ ] **Step 9: Run the complete inert seam and make it green**

Run:

```powershell
& 'C:/Users/bring/AppData/Local/Temp/prime-rook-full-mutation-qualification/kernel-venv/Scripts/python.exe' `
  'C:/Users/bring/AppData/Local/Temp/prime-rook-full-mutation-qualification/operator/test_adapter.py' -v

& 'C:/Users/bring/AppData/Local/Temp/prime-rook-full-mutation-qualification/kernel-venv/Scripts/python.exe' `
  -m py_compile `
  'C:/Users/bring/AppData/Local/Temp/prime-rook-full-mutation-qualification/agent/skills/rook-full/src/rook_full/__init__.py' `
  'C:/Users/bring/AppData/Local/Temp/prime-rook-full-mutation-qualification/operator/final_inspection.py' `
  'C:/Users/bring/AppData/Local/Temp/prime-rook-full-mutation-qualification/operator/test_adapter.py'
```

Expected: every inert test passes, compilation passes, and fake contact counters prove zero Prime, Ollama, MCP, Rook, Rhino, or Grasshopper calls.

- [ ] **Step 10: Freeze the static manifest without creating live evidence**

Write `manifest.json` as a sorted mapping from sibling-relative path to uppercase SHA-256 for:

```text
agent/settings.json
agent/models.json
agent/skills/rook-full/pyproject.toml
agent/skills/rook-full/src/rook_full/__init__.py
agent/skills/prime-execute-grasshopper/SKILL.md
agent/skills/prime-execute-grasshopper/references/checkpoint-protocol.md
operator/run.ps1
operator/final_inspection.py
operator/test_adapter.py
operator/offline-install-commands.txt
cache/prime_agent_runtime-0.1.0-py3-none-any.whl
```

Recompute every hash independently and require exact equality. Also require:

```powershell
Test-Path "$Root/operator/row.json"                 # False
Test-Path "$Root/operator/prime.jsonl"             # False
Test-Path "$Root/operator/stderr.txt"               # False
Test-Path "$Root/operator/final-inspection.jsonl"  # False
@(Get-ChildItem "$Root/agent/sessions" -File -ErrorAction SilentlyContinue).Count  # 0
```

- [ ] **Step 11: Stop at the mandatory independent pre-contact review**

Report exactly:

- disposable root;
- source Rook/Prime commits and source hashes;
- every created static file and hash;
- exact inert test count and command;
- exact compilation result;
- adapter structural-parity result;
- derived skill/reference byte-parity result;
- manifest verification result;
- absence of row and evidence;
- proof that no external contact occurred; and
- confirmation that both repositories remain unchanged.

Do not create `row.json`, inspect the live target, start Prime, load Ollama, start Rook MCP, or contact Rhino/Grasshopper. Wait for independent approval.

## Separately Authorized Live Continuation

This is not a second implementation task and is not authorized by Task 1 approval.

After independent pre-contact approval:

1. Prepare one fresh empty disposable Grasshopper canvas.
2. Read the current native discovery record and corroborate exact PID/port with the Windows listener owner.
3. Obtain the exact document serial from the active panel-bound target.
4. After the operator has reviewed exact positive integers `$ReviewedProcessId`,
   `$ReviewedPort`, and `$ReviewedDocumentSerial`, atomically create
   `operator/row.json` from the static manifest:

   ```powershell
   $Root = 'C:/Users/bring/AppData/Local/Temp/prime-rook-full-mutation-qualification'
   $Operator = "$Root/operator"
   $Manifest = Get-Content -Raw -LiteralPath "$Operator/manifest.json" | ConvertFrom-Json
   $SkillRelative = 'agent/skills/prime-execute-grasshopper/SKILL.md'
   $ReferenceRelative = 'agent/skills/prime-execute-grasshopper/references/checkpoint-protocol.md'
   $SkillPath = (Resolve-Path -LiteralPath "$Root/$SkillRelative").Path.Replace('\', '/')
   $ReferencePath = (Resolve-Path -LiteralPath "$Root/$ReferenceRelative").Path.Replace('\', '/')

   $Row = [ordered]@{
       model = 'ollama/qwen3.6:35b'
       api_base = 'http://127.0.0.1:11434/v1'
       intent = 'Create a Grasshopper definition that generates a row of points along the X axis using adjustable Start, Step, and Count controls, with Y and Z fixed at zero.'
       skill = [ordered]@{
           path = $SkillPath
           sha256 = $Manifest.PSObject.Properties[$SkillRelative].Value
           checkpoint_path = $ReferencePath
           checkpoint_sha256 = $Manifest.PSObject.Properties[$ReferenceRelative].Value
       }
       rhino_target = [ordered]@{
           process_id = $ReviewedProcessId
           expected_port = $ReviewedPort
           document_serial_number = $ReviewedDocumentSerial
       }
   }
   $TempRow = "$Operator/row.json.tmp"
   [System.IO.File]::WriteAllText(
       $TempRow,
       ($Row | ConvertTo-Json -Depth 5 -Compress),
       [System.Text.UTF8Encoding]::new($false)
   )
   Move-Item -LiteralPath $TempRow -Destination "$Operator/row.json"
   ```

   The three reviewed integer variables must come from the immediately preceding
   discovery/panel/listener corroboration. No other row substitution is allowed.
5. Add the row hash to `manifest.json`, verify every manifest hash, and re-run the inert suite without contact.
6. Report the frozen row identity and obtain explicit authorization for exactly one live mutation qualification.
7. Invoke once:

   ```powershell
   powershell.exe -NoLogo -NoProfile -NonInteractive -File `
     'C:/Users/bring/AppData/Local/Temp/prime-rook-full-mutation-qualification/operator/run.ps1' `
     -RowPath 'C:/Users/bring/AppData/Local/Temp/prime-rook-full-mutation-qualification/operator/row.json'
   ```

8. Do not rerun regardless of outcome. Retain Prime JSONL, stderr, the one native session, and final-inspection evidence exactly as written.
9. Hash retained evidence and assess only:

   > Do the retained tool records and final snapshot establish adjustable Start, Step, and Count controls producing the requested point row with fixed Y/Z and no runtime errors? Any unsupported part remains explicitly unproven.

10. Stop. Mutation cleanup, a second witness, ChatRunner repair, Prime console-window work, product integration, or another model is separately designed and authorized work.

## Evidence Ledger

- Design baseline: `2187bbcee26b6eaf94007dc400a60203203f86ae`
- Approved design commits: `9aabe182f68038c92511a48bddf1d152f4bc504c`, `7c3bdab21373d6a7113f08615316d3a2388ff8a8`
- Task 1 implementation: not executed by this plan-writing commit
- Task 1 inert test count: not executed by this plan-writing commit
- Independent pre-contact review: not requested before implementation
- Live authorization: not requested
- Live result: no contact performed
