# Prime MCP Structured Error Custody Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve exact MCP structured failure evidence in Prime while retaining failed-call control flow, then use that evidence to admit only fully classified Rook Gate B traces.

**Architecture:** Prime adds one evidence field to `McpToolError` and otherwise leaves MCP behavior unchanged. Rook adds one public error-recording helper and tightens existing trace admission; a disposable adapter correlates the two boundaries while re-raising the same exception. Prime and Rook remain separate repositories and commits.

**Tech Stack:** Python 3.10/3.11, `unittest`, `pytest`, MCP Python SDK, Prime `rlm`, Rook `gh_behavioral_acceptance`, PowerShell, Git.

## Global Constraints

- Gate A passed and must not run again.
- Preserve `C:/Users/bring/AppData/Local/Temp/rook-solve-fenced-gate-b-v2` byte-for-byte.
- Its `evidence-manifest.json` SHA-256 remains `030165216D5D1AF56ABCA2F4195D8424AB0EA6FAF65915CBDB5D915AF35E3AD3`.
- Prime and Rook changes use separate focused commits in separate repositories.
- Prime imports no Rook logic, receipt vocabulary, refusal codes, retries, or error interpretation.
- Rook production imports no Prime module and never parses exception text as JSON.
- Do not change the managed receipt registry, scheduler, fenced snapshot, behavioral evaluator semantics, or Gate A.
- No Rhino, Grasshopper, Rook MCP, Ollama, Qwen, provider, or other live contact during Tasks 1–3.
- Stop for independent offline review after Task 3.
- Task 4 requires separate post-review authorization and exactly one fresh Gate B run.
- No new framework, recorder schema, retry layer, or production module.

---

## File Map

### Prime repository

- `prime-agent-runtime/src/rlm/mcp_base.py` — sole owner of `CallToolResult` projection and `McpToolError`.
- `prime-agent-runtime/test/test_mcp_base.py` — causal runtime tests with fake sessions; no network.

### Rook repository

- `mcp_server/src/rook/gh_behavioral_acceptance.py` — existing source-event classification and trace admission owner.
- `mcp_server/tests/test_gh_behavioral_acceptance.py` — causal recorder, projection, receipt-selection, and zero-probe tests.

### Fresh disposable Gate B sibling

- `agent/skills/rook-full/src/rook_full/__init__.py` — thin Prime/Rook integration adapter.
- `operator/test_adapter.py` — exact-kernel adapter tests.
- `operator/adapter_preflight.py` — no-contact import/call preflight.
- Existing Gate B launcher/evaluator inputs copied by a closed allowlist and adjusted only for the fresh sibling, reviewed commits, kernel, and later target.

No other production file is admitted.

---

### Task 1: Prime Runtime Preserves Structured MCP Errors

**Files:**
- Modify: `D:/prime-agent/.worktrees/mcp-error-structured-content/prime-agent-runtime/src/rlm/mcp_base.py:52-54,306-324`
- Modify: `D:/prime-agent/.worktrees/mcp-error-structured-content/prime-agent-runtime/test/test_mcp_base.py:20-45,146-186`

**Interfaces:**
- Consumes: MCP SDK-shaped results exposing `content`, `isError`, and `structuredContent`.
- Produces: `McpToolError(message: str, *, structured_content: Any = None)` with unchanged `str(exception)` and exact `structured_content` identity.

- [ ] **Step 1: Create an isolated Prime worktree from the audited upstream head**

Use `superpowers:using-git-worktrees`. Fetch without modifying `D:/prime-agent/main`, verify that upstream still has no equivalent fix, then create:

```powershell
$PrimeRepo = 'D:/prime-agent'
$PrimeWorktree = 'D:/prime-agent/.worktrees/mcp-error-structured-content'
git -C $PrimeRepo fetch origin
git -C $PrimeRepo log --oneline -5 origin/main -- prime-agent-runtime/src/rlm/mcp_base.py
git -C $PrimeRepo worktree add -b codex/mcp-error-structured-content $PrimeWorktree origin/main
git -C $PrimeWorktree status --short
git -C $PrimeWorktree rev-parse HEAD
```

Expected baseline: `7787f07415d843b9a800f6a4720e0c739bd608e5`, unless a later fetched upstream commit already implements the exact contract. If an exact upstream fix exists, stop and review/reuse it instead of duplicating it.

- [ ] **Step 2: Write RED exception-custody tests**

Extend `_FakeSession.call_tool()` so an exception-valued fake result is raised after the call is retained:

```python
async def call_tool(self, name, arguments):
    self.calls.append((name, arguments))
    if isinstance(self._result, Exception):
        raise self._result
    return self._result
```

Replace the single loose error test with exact cases equivalent to:

```python
def test_error_result_preserves_exact_structured_content_and_text(self):
    payload = {"success": False, "data": {"error": "denied"}}
    block = type("B", (), {"text": "boom"})()
    result = type(
        "R", (),
        {"isError": True, "content": [block], "structuredContent": payload},
    )()
    with self.assertRaises(McpToolError) as ctx:
        mcp_base._parse_result(result)
    self.assertIsInstance(ctx.exception, RuntimeError)
    self.assertEqual(str(ctx.exception), "boom")
    self.assertIs(ctx.exception.structured_content, payload)

def test_structured_only_error_uses_legacy_fallback_text(self):
    payload = {"success": False, "data": [1, 2]}
    result = type(
        "R", (),
        {"isError": True, "content": [], "structuredContent": payload},
    )()
    with self.assertRaises(McpToolError) as ctx:
        mcp_base._parse_result(result)
    self.assertEqual(str(ctx.exception), "MCP tool returned an error")
    self.assertIs(ctx.exception.structured_content, payload)

def test_text_only_error_does_not_reconstruct_json(self):
    text = '{"success":false,"data":{"error":"looks_structured"}}'
    block = type("B", (), {"text": text})()
    result = type(
        "R", (),
        {"isError": True, "content": [block], "structuredContent": None},
    )()
    with self.assertRaises(McpToolError) as ctx:
        mcp_base._parse_result(result)
    self.assertEqual(str(ctx.exception), text)
    self.assertIsNone(ctx.exception.structured_content)

def test_success_returns_exact_structured_object(self):
    payload = {"success": True, "data": {"ok": True}}
    result = type(
        "R", (),
        {"isError": False, "content": [], "structuredContent": payload},
    )()
    self.assertIs(mcp_base._parse_result(result), payload)

def test_transport_exception_is_unchanged_and_not_retried(self):
    failure = ConnectionError("transport down")
    session = _FakeSession(tools=[], result=failure)
    with self._patch_session(session):
        with self.assertRaises(ConnectionError) as ctx:
            _run(_Integration().call_tool("demo", {"x": 1}))
    self.assertIs(ctx.exception, failure)
    self.assertEqual(session.calls, [("demo", {"x": 1})])

def test_structured_tool_error_calls_session_once(self):
    payload = {"success": False, "data": {"error": "denied"}}
    result = type(
        "R", (),
        {"isError": True, "content": [], "structuredContent": payload},
    )()
    session = _FakeSession(tools=[], result=result)
    with self._patch_session(session):
        with self.assertRaises(McpToolError) as ctx:
            _run(_Integration().call_tool("demo", {"x": 1}))
    self.assertIs(ctx.exception.structured_content, payload)
    self.assertEqual(session.calls, [("demo", {"x": 1})])
```

Retain the existing success/text tests. These tests must not import Rook.

- [ ] **Step 3: Run the Prime test file and confirm RED**

```powershell
$Python = 'C:/Users/bring/AppData/Local/Programs/Python/Python310/python.exe'
$env:PYTHONPATH = 'D:/prime-agent/.worktrees/mcp-error-structured-content/prime-agent-runtime/src'
& $Python 'D:/prime-agent/.worktrees/mcp-error-structured-content/prime-agent-runtime/test/test_mcp_base.py' -v
```

Expected: new tests fail because `McpToolError` has no `structured_content` field; existing unrelated tests remain green.

- [ ] **Step 4: Implement the minimal Prime correction**

Use this exact class boundary:

```python
class McpToolError(RuntimeError):
    """Raised when an MCP tool call returns a result flagged as an error."""

    def __init__(self, message: str, *, structured_content: Any = None):
        self.structured_content = structured_content
        super().__init__(message)
```

Read the SDK field before the `isError` branch and pass it unchanged:

```python
structured = getattr(result, "structuredContent", None)
if getattr(result, "isError", False):
    raise McpToolError(
        "\n".join(texts) or "MCP tool returned an error",
        structured_content=structured,
    )

if structured is not None:
    return structured
```

Do not add copying, validation, serialization, retries, or interpretation.

- [ ] **Step 5: Run Prime verification**

Run the exact test file, compilation, and static boundary checks:

```powershell
$PrimeWorktree = 'D:/prime-agent/.worktrees/mcp-error-structured-content'
$Python = 'C:/Users/bring/AppData/Local/Programs/Python/Python310/python.exe'
$env:PYTHONPATH = "$PrimeWorktree/prime-agent-runtime/src"
& $Python "$PrimeWorktree/prime-agent-runtime/test/test_mcp_base.py" -v
& $Python -m py_compile "$PrimeWorktree/prime-agent-runtime/src/rlm/mcp_base.py" "$PrimeWorktree/prime-agent-runtime/test/test_mcp_base.py"
rg -n "rook|receipt|refusal|retry|json\.loads\(.*exception|json\.loads\(.*exc" "$PrimeWorktree/prime-agent-runtime/src/rlm/mcp_base.py"
git -C $PrimeWorktree diff --check
```

Expected: all tests pass; compilation and diff check pass; the static scan finds no Rook-specific or exception-text parsing additions.

- [ ] **Step 6: Commit only the Prime change**

```powershell
$PrimeWorktree = 'D:/prime-agent/.worktrees/mcp-error-structured-content'
git -C $PrimeWorktree add -- prime-agent-runtime/src/rlm/mcp_base.py prime-agent-runtime/test/test_mcp_base.py
git -C $PrimeWorktree diff --cached --check
git -C $PrimeWorktree commit -m "fix(runtime): preserve structured MCP error results"
git -C $PrimeWorktree status --short
```

Expected: one focused Prime commit and a clean worktree.

---

### Task 2: Rook Records Authentic Structured Failures And Fails Closed

**Files:**
- Modify: `mcp_server/src/rook/gh_behavioral_acceptance.py:18-28,355-453,571-627,1058-1080`
- Modify: `mcp_server/tests/test_gh_behavioral_acceptance.py:353-479,869-1007,1582-1663`

**Interfaces:**
- Consumes: an ordinary exception plus its untrusted `structured_content` value from a disposable adapter.
- Produces: `append_canonical_gateway_error_source_event(source_path, target, arguments, *, exception, structured_content) -> dict[str, Any]` and whole-trace unknown-event refusal.

- [ ] **Step 1: Write RED public-helper tests**

Add the new name to the exact `__all__` expectation, then add tests that create a Prime-owned source header and assert:

```python
result = {"success": False, "data": {"error": "unknown_or_non_dispatchable"}}
error = RuntimeError("legacy text remains an exception")
event = acceptance.append_canonical_gateway_error_source_event(
    source_path,
    "rook_tools_read",
    {"name": "gh_canvas/gh_edit"},
    exception=error,
    structured_content=result,
)
assert event["result"] is result
assert event["exception"] is None
assert event["dispatch"] == {
    "status": "refused_before_dispatch",
    "target_call_count": 0,
}
assert event["mutation"]["classification"] == "observational"
```

Parametrize invalid evidence with `None`, a list, missing/extra keys, nonboolean success,
and `{"success": True, "data": {}}`. Every case must append the exact exception/unknown
event instead of a result event.

- [ ] **Step 2: Write RED Gate B sequence and uncertainty tests**

Use existing `_receipt`, `_event`, `_trace`, and `_Executor` helpers. Build a source sequence
through the public appenders with:

```python
first = _receipt("partial", mutation_epoch=1)
second = _receipt("latest", mutation_epoch=2)
partial = _event(
    1, "gh_edit", classification="terminal",
    commit_status="committed", receipt=first,
)
partial["result"]["success"] = False
partial["result"]["data"]["errors"] = ["later operation failed"]
later = _event(
    2, "gh_edit", classification="terminal",
    commit_status="committed", receipt=second,
)
snapshot = _event(3, "gh_snapshot")
```

Prepend the known failed read from Step 1. Set `executor.pending = second`, run
`run_behavioral_probe()`, and require the first executor call to wait on receipt `latest`.
Assert the partial event retains receipt `partial` and exact edit counters.

Add a parametrized zero-call test for:

- an exception event before the terminal mutation;
- a transport exception after it;
- malformed structured content recorded as exception/unknown;
- a failed mutation without commit evidence;
- an unknown refusal/error code before or after it; and
- a structurally valid event whose mutation or commit status is `unknown`.

Every case must return `authoring_trace_invalid` and `executor.calls == []`.

- [ ] **Step 3: Run the focused Rook test and confirm RED**

```powershell
$Rook = 'C:/UDEV/Rook/.worktrees/grasshopper-solve-fenced-acceptance-design'
$Python = 'C:/Users/bring/AppData/Local/Programs/Python/Python310/python.exe'
& $Python -m pytest "$Rook/mcp_server/tests/test_gh_behavioral_acceptance.py" -q
```

Expected: new helper/import and earlier-unknown admission tests fail; existing tests pass.

- [ ] **Step 4: Add the public error-source helper**

Export and implement exactly:

```python
def append_canonical_gateway_error_source_event(
    source_path: Path,
    target: str,
    arguments: dict[str, Any],
    *,
    exception: Exception,
    structured_content: Any,
) -> dict[str, Any]:
    """Record authentic structured MCP failure evidence or fail closed."""

    if not isinstance(exception, Exception):
        raise ValueError("invalid_gateway_event_exception")
    if _valid_result(structured_content) and structured_content["success"] is False:
        return append_canonical_gateway_source_event(
            source_path,
            target,
            arguments,
            result=structured_content,
        )
    return append_canonical_gateway_source_event(
        source_path,
        target,
        arguments,
        exception=exception,
    )
```

This helper imports no Prime type and changes no event schema.

- [ ] **Step 5: Make failed observational results and whole-trace unknowns ineligible**

In `_expected_mutation()`, retain the recognized zero-dispatch branch first. Before the
ordinary observational-target branch, add:

```python
if result["success"] is False and target in _OBSERVATIONAL_TARGETS:
    return _unknown_mutation()
```

In `_latest_terminal_receipt()`, reject uncertainty before selecting any receipt:

```python
for index, event in enumerate(trace["events"]):
    mutation = event["mutation"]
    if (
        event["exception"] is not None
        or event["dispatch"]["status"] == "unknown"
        or mutation["classification"] == "unknown"
        or mutation["commit_status"] == "unknown"
    ):
        return None, "authoring_trace_invalid"
    # existing terminal receipt selection follows unchanged
```

Do not change selection of the latest committed terminal receipt or the rule that only
observations may follow it.

- [ ] **Step 6: Run the complete owner-focused offline Rook verification**

```powershell
$Rook = 'C:/UDEV/Rook/.worktrees/grasshopper-solve-fenced-acceptance-design'
$Python = 'C:/Users/bring/AppData/Local/Programs/Python/Python310/python.exe'
& $Python -m pytest "$Rook/mcp_server/tests/test_gh_behavioral_acceptance.py" -q
& $Python -m py_compile "$Rook/mcp_server/src/rook/gh_behavioral_acceptance.py" "$Rook/mcp_server/tests/test_gh_behavioral_acceptance.py"
rg -n "json\.loads\(.*exception|json\.loads\(.*exc|McpToolError" "$Rook/mcp_server/src/rook/gh_behavioral_acceptance.py"
git -C $Rook diff --check
```

Expected: the entire behavioral-acceptance owner suite passes; no live-marked test runs; no Prime import or exception-text parsing appears. Broader Rook suites are outside this two-file correction and must not be used to contact Rhino.

- [ ] **Step 7: Reverify the consumed Gate B V2 manifest**

```powershell
$V2 = 'C:/Users/bring/AppData/Local/Temp/rook-solve-fenced-gate-b-v2'
$Actual = (Get-FileHash -Algorithm SHA256 -LiteralPath "$V2/evidence-manifest.json").Hash
if ($Actual -cne '030165216D5D1AF56ABCA2F4195D8424AB0EA6FAF65915CBDB5D915AF35E3AD3') {
    throw "consumed_v2_changed:$Actual"
}
```

- [ ] **Step 8: Commit only the Rook production/test correction**

```powershell
$Rook = 'C:/UDEV/Rook/.worktrees/grasshopper-solve-fenced-acceptance-design'
git -C $Rook add -- mcp_server/src/rook/gh_behavioral_acceptance.py mcp_server/tests/test_gh_behavioral_acceptance.py
git -C $Rook diff --cached --check
git -C $Rook commit -m "fix: admit structured MCP failure evidence"
git -C $Rook status --short
```

Expected: the pre-existing specification commit remains separate; this commit contains exactly two files.

---

### Task 3: Fresh Disposable Adapter And Offline Cross-Boundary Proof

**Files:**
- Create: `C:/Users/bring/AppData/Local/Temp/rook-solve-fenced-gate-b-v3/agent/skills/rook-full/src/rook_full/__init__.py`
- Create: `C:/Users/bring/AppData/Local/Temp/rook-solve-fenced-gate-b-v3/operator/test_adapter.py`
- Create: `C:/Users/bring/AppData/Local/Temp/rook-solve-fenced-gate-b-v3/operator/adapter_preflight.py`
- Create: fresh non-target Gate B inputs and `precontact-manifest.json` in the same sibling.
- Never modify: `C:/Users/bring/AppData/Local/Temp/rook-solve-fenced-gate-b-v2/**`

**Interfaces:**
- Consumes: Prime `McpToolError.structured_content` and Rook `append_canonical_gateway_error_source_event()`.
- Produces: one source result event for an authentic structured MCP failure, followed by re-raising the same exception object.

- [ ] **Step 1: Create the sibling from a closed input allowlist**

Create `rook-solve-fenced-gate-b-v3` new. Copy only these V2 inputs:

```text
agent/auth.json
agent/models.json
agent/settings.json
agent/skills/prime-execute-grasshopper/**
agent/skills/rook-full/pyproject.toml
agent/skills/rook-full/src/prime_agent_skill_rook_full.egg-info/**
operator/run_gate_b.ps1
operator/evaluate_gate_b.py
operator/adapter_preflight.py
operator/test_adapter.py
```

Do not copy `logs`, `sessions`, `session-artifacts`, `session-leases`, target files, source
logs, Prime JSONL, snapshots, closures, probes, evaluations, process ledgers, stderr, or any
other consumed evidence. Update only sibling paths and the reviewed Prime/Rook source hashes.

- [ ] **Step 2: Write RED adapter tests using the real Prime exception class**

Run the test with `PYTHONPATH` ordering:

```text
fresh adapter source
Prime worktree prime-agent-runtime/src
Rook worktree mcp_server/src
```

Add tests equivalent to:

```python
def _rows(self):
    return [
        json.loads(line)
        for line in self.source_path.read_text(encoding="utf-8").splitlines()
    ]

def test_structured_mcp_error_records_result_then_reraises_same_exception(self):
    payload = {"success": False, "data": {"error": "unknown_or_non_dispatchable"}}
    error = McpToolError("legacy text", structured_content=payload)
    self.rook_full._integration = _FakeIntegration(error=error)
    with self.assertRaises(McpToolError) as ctx:
        asyncio.run(self.rook_full.read("gh_canvas/gh_edit"))
    self.assertIs(ctx.exception, error)
    row = self._rows()[1]
    self.assertEqual(row["result"], payload)
    self.assertIsNone(row["exception"])
    self.assertEqual(row["dispatch"]["target_call_count"], 0)

def test_malformed_structured_error_records_unknown_and_reraises(self):
    error = McpToolError("legacy text", structured_content={"success": False})
    self.rook_full._integration = _FakeIntegration(error=error)
    with self.assertRaises(McpToolError) as ctx:
        asyncio.run(self.rook_full.call("gh_edit", {"epoch": 1}))
    self.assertIs(ctx.exception, error)
    row = self._rows()[1]
    self.assertIsNone(row["result"])
    self.assertEqual(row["mutation"]["classification"], "unknown")

def test_recorder_failure_cannot_replace_original_mcp_error(self):
    error = McpToolError("legacy text", structured_content={"success": False, "data": {}})
    self.rook_full._integration = _FakeIntegration(error=error)
    with mock.patch.object(
        self.rook_full._acceptance,
        "append_canonical_gateway_error_source_event",
        side_effect=OSError("recorder failed"),
    ):
        with self.assertRaises(McpToolError) as ctx:
            asyncio.run(self.rook_full.call("gh_edit", {"epoch": 1}))
    self.assertIs(ctx.exception, error)
    self.assertEqual(len(self._rows()), 1)
```

Import `mock` from `unittest.mock` and import `McpToolError` from
`rlm.mcp_base`; do not create a local stand-in exception class.

Retain the existing ingress-deepcopy and ordinary transport-exception cases.

- [ ] **Step 3: Run adapter tests and confirm RED**

```powershell
$V3 = 'C:/Users/bring/AppData/Local/Temp/rook-solve-fenced-gate-b-v3'
$Prime = 'D:/prime-agent/.worktrees/mcp-error-structured-content'
$Rook = 'C:/UDEV/Rook/.worktrees/grasshopper-solve-fenced-acceptance-design'
$Python = 'C:/Users/bring/AppData/Local/Temp/prime-rook-operational-comparison-v3/local/kernel-venv/Scripts/python.exe'
$env:PYTHONPATH = "$V3/agent/skills/rook-full/src;$Prime/prime-agent-runtime/src;$Rook/mcp_server/src"
& $Python "$V3/operator/test_adapter.py" -v
```

Expected: structured-error adapter tests fail while existing tests remain green. This command uses fake integration only and must not contact MCP.

- [ ] **Step 4: Implement the thin adapter catch boundary**

Import the real runtime class:

```python
from rlm.mcp_base import McpToolError
```

Use this catch ordering inside `_recorded_call()`:

```python
try:
    result = await operation
except McpToolError as exc:
    try:
        _acceptance.append_canonical_gateway_error_source_event(
            source_path,
            target,
            retained_arguments,
            exception=exc,
            structured_content=exc.structured_content,
        )
    except Exception:
        # The missing event makes closure incomplete; never mask the authentic call error.
        pass
    raise
except Exception as exc:
    try:
        _acceptance.append_canonical_gateway_source_event(
            source_path,
            target,
            retained_arguments,
            exception=exc,
        )
    except Exception:
        pass
    raise
```

The success path remains unchanged. Do not inspect `str(exc)`.

- [ ] **Step 5: Extend the standalone no-contact preflight**

Use a fake integration that raises a real enriched `McpToolError`. The preflight must catch
the same object, observe one exact result event, confirm zero network entry, and write a
create-new success artifact. A malformed payload must produce one exception/unknown event.
No actual `_RookFull._open_session()` call is permitted.

- [ ] **Step 6: Run the exact-kernel cross-boundary suite**

```powershell
$V3 = 'C:/Users/bring/AppData/Local/Temp/rook-solve-fenced-gate-b-v3'
$Prime = 'D:/prime-agent/.worktrees/mcp-error-structured-content'
$Rook = 'C:/UDEV/Rook/.worktrees/grasshopper-solve-fenced-acceptance-design'
$Python = 'C:/Users/bring/AppData/Local/Temp/prime-rook-operational-comparison-v3/local/kernel-venv/Scripts/python.exe'
$env:PYTHONPATH = "$V3/agent/skills/rook-full/src;$Prime/prime-agent-runtime/src;$Rook/mcp_server/src"
& $Python "$V3/operator/test_adapter.py" -v
& $Python -m py_compile "$V3/agent/skills/rook-full/src/rook_full/__init__.py" "$V3/operator/adapter_preflight.py" "$V3/operator/test_adapter.py"
```

Then run `adapter_preflight.py` against fresh temporary output paths and verify it reports one
delegate call, one valid event, the same re-raised exception identity, and zero network entry.

- [ ] **Step 7: Freeze the pre-contact manifest**

Hash every non-target V3 input, both reviewed repository commits, the Prime runtime source,
the Rook acceptance source, the exact Qwen manifest, and the point-row acceptance artifact.
The manifest excludes all future target and live evidence. It records:

```text
Prime commit
Rook commit
Prime mcp_base.py SHA-256
Rook gh_behavioral_acceptance.py SHA-256
adapter/preflight/test SHA-256 values
model manifest SHA-256
acceptance artifact SHA-256
V2 evidence-manifest SHA-256 non-mutation proof
```

All paths are exact and all hashes are 64 uppercase hexadecimal characters.

- [ ] **Step 8: Mandatory independent no-contact review gate**

The reviewer independently reruns:

- Prime unit tests and compilation;
- the complete Rook behavioral-acceptance owner suite;
- exact-kernel adapter tests and preflight;
- both repository commit/scope/clean checks;
- V3 manifest verification and absence of target/live evidence; and
- V2 manifest hash verification.

The reviewer must confirm no Rhino, MCP, Ollama, Qwen, or provider contact occurred. Stop here.
Do not deploy or create a target without approval after this review.

---

### Task 4: Separately Authorized Deployment And Single Fresh Gate B

**Files:**
- Create only fresh V3 runtime/target/evidence artifacts after review.
- Do not change Prime or Rook production source in this task.

**Interfaces:**
- Consumes: independently approved Prime and Rook commits plus the frozen V3 pre-contact manifest.
- Produces: one truthful Gate B `pass`, `fail`, or `incomplete` evidence package.

- [ ] **Step 1: Obtain explicit post-review authorization**

Authorization must cover one standard Rook Release deployment, one fresh kernel build from
the frozen requirements plus the reviewed Prime runtime, one fresh empty target, and exactly
one Gate B model run/evaluation. It does not authorize Gate A, retry, repair, cleanup, or a
second model invocation.

- [ ] **Step 2: Deploy exact Rook and build a fresh Prime kernel**

With Rhino and MCP processes closed, use `rook:deploy-local-testing` and the standard command:

```powershell
$Rook = 'C:/UDEV/Rook/.worktrees/grasshopper-solve-fenced-acceptance-design'
& pwsh -NoProfile -File "$Rook/scripts/deploy-local-testing.ps1" -Configuration Release
```

Do not use `-PayloadOnly`, `-SkipBuild`, `-UseRepoVenv`, or `-DevPythonRuntime`.

Create a new V3 kernel venv from the exact retained
`prime-rook-operational-comparison-v3/local/operator/kernel-requirements.txt`, then reinstall
the reviewed local Prime runtime with no dependency changes:

```powershell
$V3 = 'C:/Users/bring/AppData/Local/Temp/rook-solve-fenced-gate-b-v3'
$Prime = 'D:/prime-agent/.worktrees/mcp-error-structured-content'
$Requirements = 'C:/Users/bring/AppData/Local/Temp/prime-rook-operational-comparison-v3/local/operator/kernel-requirements.txt'
uv venv --python 3.11 "$V3/kernel-venv"
uv pip install --python "$V3/kernel-venv/Scripts/python.exe" --requirement $Requirements
uv pip install --python "$V3/kernel-venv/Scripts/python.exe" --no-deps --reinstall "$Prime/prime-agent-runtime"
```

Hash installed `rlm/mcp_base.py` against the reviewed Prime source and installed
`rook/gh_behavioral_acceptance.py` against the reviewed Rook source. Any mismatch stops.

- [ ] **Step 3: Restart Rhino and freeze one fresh empty target**

Start Rhino after deployment, open Grasshopper with a new empty document, and open Rook Chat.
Corroborate PID, process creation identity, native port/listener ownership, and the exact
Rook Chat document serial. Take one initial `gh_snapshot` as part of the authorized
transaction and require:

```text
components == []
flows == []
groups absent or []
relays absent or []
diagnostics.total == 0
diagnostics.errors == 0
diagnostics.warnings == 0
```

Write `target.json` create-new, add its hash and the initial-snapshot hash to the V3 live
manifest, rerun the exact-kernel adapter preflight, and proceed directly. A nonempty target,
runtime drift, or failed preflight stops without a model call.

- [ ] **Step 4: Run Gate B exactly once**

Invoke the frozen V3 `run_gate_b.ps1` once. It permits one unchanged Qwen/Prime point-row
attempt with the retained intent, skill, model, reasoning, 30-minute limit, and no repair.
No retry or second Prime process is admitted.

After natural Prime termination and zero remaining owned children, seal the complete runtime,
normalize the source, select the latest authentic terminal receipt, run the same fenced
behavioral probe, and evaluate the frozen point-row artifact. Prime prose is not acceptance
evidence.

- [ ] **Step 5: Preserve and verify the result**

Retain and hash:

```text
target and initial snapshot
Prime JSONL and native session
authoring source and closure
normalized authoring trace
process ledger and stderr
behavioral probe and evaluation
final Gate B result
runtime/source/model/adapter hashes
```

Report `pass`, `fail`, or `incomplete` truthfully. Explicitly verify:

- failed-call exceptions remain visible in Prime's native evidence;
- valid structured failures appear as exact Rook result events;
- the known read is zero-dispatch observational;
- the partial edit retains its exact committed receipt, if that event occurs;
- a later committed edit supersedes it, if present;
- later observations do not displace the selected receipt;
- uncertain evidence causes zero behavioral probe calls; and
- no owned process remains.

- [ ] **Step 6: Requirement-by-requirement completion audit**

Compare the final source, commits, tests, V3 evidence, and preserved V2 manifest against every
Prime correction, Prime test, Rook correction, offline regression, constraint, and bounded
claim in the specification. Any missing or indirect evidence remains incomplete; do not
upgrade it to success.

Only when every requirement is directly supported may the goal be marked complete with the
bounded claim from the specification.
