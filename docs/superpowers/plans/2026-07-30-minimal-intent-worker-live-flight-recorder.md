# Minimal Intent/Worker Live Flight Recorder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one private, bounded, append-only JSONL flight recorder to the real compile smoke so a returned native stop can be diagnosed from exact local boundary payloads and returned native records.

**Architecture:** Keep product modules unchanged. Add a private recorder, preparation/model/tool wrappers, explicit returned-record projectors, and one centralized operator finalization path inside the existing smoke script. Every request is flushed before its call; every response or exception is flushed before any next call; returned projections are appended only after their owning native objects exist.

**Tech Stack:** Python 3.11+, standard-library `json`, `datetime`, `pathlib`, `secrets`, binary file I/O, existing Rook agent dataclasses/functions, pytest.

## Global Constraints

- Base implementation commit is `619ca24e8a34cb83a02db828d37d1dc7a3c8d2e3` plus the two specification commits on this branch.
- Modify only `scripts/minimal_intent_worker_real_compile_smoke.py` and `mcp_server/tests/test_minimal_intent_worker_real_compile_smoke.py`; this plan and the approved specification are documentation only.
- Keep every recorder type, constant, wrapper, and projector private to the operator script.
- Do not modify `mcp_server/src/rook/**` or any product contract.
- Do not add a shared tracing API, observer callback, registry, reader, verifier, archive, manifest, checksum, fingerprint, database, or lifecycle protocol.
- Do not change prompts, models, generation parameters, retries, workflow compilation, tool contracts, worker behavior, or native terminal meanings.
- Do not execute `--execute-live` during implementation or review.
- Capture exact adapter-boundary values serialized into JSON, not HTTP wire bytes, provider headers, credentials, or LiteLLM internals.
- Open one exclusive file under `%LOCALAPPDATA%\Rook\traces\` after exact live-argument admission and before profile resolution, discovery, transport construction, or tool contact.
- Complete JSONL row plus newline is bounded to `256 * 1024` bytes.
- Actual trace bytes are bounded to `4 * 1024 * 1024`; normal rows may consume only that total minus an exact `4 * 1024` byte rejection reserve.
- Exception messages attempt exact `str(exc)` and are bounded by their
  `ensure_ascii=True` JSON-string encoding to `16 * 1024` bytes;
  message-extraction failure enters the fixed serialization-rejection path.
- No truncation, compression, lossy summary, substitute hash, retry, fallback, second trace, or reopened trace is permitted.
- Every request row flushes before delegate entry. Every response/exception row flushes before a later external call.
- Trace failure supersedes normal propagation and stops the next external call; completed calls remain truthfully counted.
- `run_finished` requires every applicable ownership-backed projection, not a native result that does not exist.
- A close failure after a successfully flushed `run_finished` still yields `trace_write_failed`; the retained row claims logical stream completion only.
- Stdout retains its existing bounded fields and adds only `trace_path`.

## File structure

### `scripts/minimal_intent_worker_real_compile_smoke.py`

Owns recorder constants/vocabularies, `_TraceWriteFailure`,
`_JsonlFlightRecorder`, exclusive trace-file creation, all boundary wrappers,
exact call counts, trace-failure precedence, returned-record projectors,
`trace_path`, and close-before-success output.

### `mcp_server/tests/test_minimal_intent_worker_real_compile_smoke.py`

Owns stream fault fakes, deterministic clock/token seams, exact resource-bound
tests, wrapper ordering/identity tests, lifecycle faults, conditional projection
tests, the current returned-stop witness, stdout secrecy, and full regression.

---

### Task 1: Private bounded JSONL recorder

**Files:**
- Modify: `scripts/minimal_intent_worker_real_compile_smoke.py:1-216`
- Test: `mcp_server/tests/test_minimal_intent_worker_real_compile_smoke.py`

**Interfaces:**
- Consumes: binary streams exposing `write(bytes)`, `flush()`, `close()`; UTC clock; `%LOCALAPPDATA%`.
- Produces:
  - `_TraceWriteFailure(reason: str, path: Path | None)`
  - `_JsonlFlightRecorder(path: Path, stream: BinaryIO, clock: Callable[[], datetime])`
  - `_open_live_flight_recorder() -> _JsonlFlightRecorder`
  - `record(event: str, payload: Mapping[str, Any]) -> None`
  - `record_exception(event: str, payload: Mapping[str, Any], exc: Exception) -> None`
  - `finish(payload: Mapping[str, Any]) -> None`
  - `close_incomplete() -> None`
  - read-only `path`, `bytes_written`, `failed`, `closed`, and `sequence`.

- [ ] **Step 1: Add recorder test fakes and the behavioral RED**

Add a binary stream fake that retains bytes and can fail exact write, flush, or
close calls:

```python
class _TraceStream:
    def __init__(
        self,
        *,
        fail_write_at=None,
        short_write_at=None,
        fail_flush_at=None,
        fail_close=False,
    ):
        self.content = bytearray()
        self.write_calls = 0
        self.flush_calls = 0
        self.close_calls = 0
        self.fail_write_at = fail_write_at
        self.short_write_at = short_write_at
        self.fail_flush_at = fail_flush_at
        self.fail_close = fail_close

    def write(self, value: bytes) -> int:
        self.write_calls += 1
        if self.write_calls == self.fail_write_at:
            raise OSError("TRACE_WRITE_SENTINEL")
        if self.write_calls == self.short_write_at:
            written = max(0, len(value) - 1)
            self.content.extend(value[:written])
            return written
        self.content.extend(value)
        return len(value)

    def flush(self) -> None:
        self.flush_calls += 1
        if self.flush_calls == self.fail_flush_at:
            raise OSError("TRACE_FLUSH_SENTINEL")

    def close(self) -> None:
        self.close_calls += 1
        if self.fail_close:
            raise OSError("TRACE_CLOSE_SENTINEL")
```

Write a test constructing the wished-for recorder with a fixed path, stream,
and UTC clock. Record `run_started`; parse the line and require exact sequence,
timestamp, event, payload, newline, byte count, and one flush.

- [ ] **Step 2: Run the RED and verify the intended missing behavior**

```powershell
& C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_minimal_intent_worker_real_compile_smoke.py::test_flight_recorder_writes_one_flushed_jsonl_row -q
```

Expected: FAIL because `_JsonlFlightRecorder` does not exist. Import, fixture,
timestamp, and path errors are invalid RED states.

- [ ] **Step 3: Implement the closed vocabulary and core writer**

Add the exact resource constants and mappings:

```python
_TRACE_ROW_MAX_BYTES = 256 * 1024
_TRACE_TOTAL_MAX_BYTES = 4 * 1024 * 1024
_TRACE_REJECTION_RESERVE_BYTES = 4 * 1024
_TRACE_NORMAL_MAX_BYTES = _TRACE_TOTAL_MAX_BYTES - _TRACE_REJECTION_RESERVE_BYTES
_TRACE_EXCEPTION_MESSAGE_MAX_JSON_BYTES = 16 * 1024

_TRACE_REJECTION_EVENTS = {
    "json_serialization_failed": "event_serialization_failed",
    "row_size_exceeded": "event_rejected",
    "total_size_exceeded": "event_rejected",
    "exception_message_size_exceeded": "event_rejected",
}
```

Define the closed vocabulary directly:

```python
_TRACE_EVENTS = frozenset(
    {
        "run_started",
        "tool_request",
        "tool_response",
        "tool_exception",
        "planner_request",
        "planner_response",
        "planner_exception",
        "worker_request",
        "worker_response",
        "worker_exception",
        "planner_admission",
        "compiled_workflow",
        "native_step_projection",
        "final_native_result",
        "handoff_raised",
        "event_rejected",
        "event_serialization_failed",
        "run_finished",
    }
)
```

Add `_TraceWriteFailure` whose public message is only `trace_write_failed` and
whose fields retain a fixed internal reason and optional path.

Implement `record()` with this order:

1. refuse after failure/close;
2. require a closed event name;
3. build next sequence and UTC timestamp;
4. serialize with `ensure_ascii=True`, `allow_nan=False`, compact separators,
   and one newline;
5. route serialization, row, and total failures through one rejection write;
6. perform one binary write and add its returned nonnegative byte count to
   actual `bytes_written` immediately;
7. require that count to equal the full encoded row length;
8. flush;
9. advance sequence only after the complete row and flush both succeed.

Use one raw writer. A short write or OS write/flush failure sets failed state
and raises without trying a second trace row.

- [ ] **Step 4: Add exact-bound and rejection RED tests**

Construct payload lengths from actual serialized row bytes. Prove:

```text
complete row == 256 KiB     -> accepted
complete row == 256 KiB + 1 -> event_rejected / row_size_exceeded
normal total boundary       -> accepted through 4 MiB - 4 KiB
next normal byte            -> one event_rejected / total_size_exceeded
second post-rejection write -> zero bytes, _TraceWriteFailure
```

Use an unserializable value to require
`event_serialization_failed / json_serialization_failed`. Require every
rejection row to name its attempted event, fit in 4 KiB, and keep total bytes at
or below 4 MiB. Add a short-write RED where the stream retains only the written
prefix and returns a count smaller than the row. Require `_TraceWriteFailure`,
no flush, no retry or rejection-row attempt, no second row, and byte-for-byte
unchanged partial content after every refused later write.

- [ ] **Step 5: Implement rejection and exception-message behavior**

Implement `_reject(attempted_event, reason)` without recursively calling
`record()`. Its payload is exactly:

```python
{
    "attempted_event": attempted_event,
    "rejection_reason": reason,
}
```

After flushing one reserve row, mark the recorder failed and prevent every
later write.

`record_exception()` first extracts and measures the message inside an ordinary
exception boundary:

```python
try:
    message = str(exc)
except Exception:
    self._reject(event, "json_serialization_failed")

encoded_message = json.dumps(
    message,
    ensure_ascii=True,
    allow_nan=False,
    separators=(",", ":"),
).encode("utf-8")
```

At or below 16 KiB, record exact `exception_type` and `exception_message`.
Bound-plus-one rejects the attempted exception event without truncation. Add a
lone-surrogate regression proving no `UnicodeEncodeError`. Add an exception
whose `__str__()` raises; it must flush exactly one
`event_serialization_failed / json_serialization_failed` row, mark the recorder
incomplete, and reject every later write.

- [ ] **Step 6: Add open, finish, and close fault tests**

With `LOCALAPPDATA=tmp_path`, prove exclusive creation under
`Rook/traces`, collision-resistant filenames, no-clobber behavior, and an
absolute path. Test:

```text
finish -> run_finished write -> flush -> close
close succeeds -> closed true
close fails -> parseable run_finished retained + trace_write_failed
prior failure -> close_incomplete writes no run_finished
```

- [ ] **Step 7: Implement exclusive open and finalization**

`_open_live_flight_recorder()` accepts no path/configuration arguments. Read
exact nonblank `%LOCALAPPDATA%`, create `Rook/traces`, and use:

```python
stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
name = (
    f"minimal-intent-worker-real-compile-{stamp}-"
    f"p{os.getpid()}-{secrets.token_hex(4)}.jsonl"
)
stream = path.open("xb")
```

Production uses the real UTC clock; direct tests inject a fixed clock into the
private recorder. `finish()` records/flushed `run_finished` then closes.
`close_incomplete()` writes nothing and closes. Any close exception becomes
`_TraceWriteFailure("close_failed", path)`.

- [ ] **Step 8: Run Task 1 tests**

```powershell
& C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_minimal_intent_worker_real_compile_smoke.py `
  -k "flight_recorder or no_arguments or invalid_arguments" -q
```

Expected: all selected tests pass; no live transport or tool is constructed.

- [ ] **Step 9: Commit Task 1 and stop for independent review**

```powershell
git add scripts/minimal_intent_worker_real_compile_smoke.py `
  mcp_server/tests/test_minimal_intent_worker_real_compile_smoke.py
git commit -m "feat(smoke): add bounded JSONL flight recorder"
```

Mandatory review gate: close row/total/rejection/flush/close semantics before
adding any boundary wrapper.

---

### Task 2: Transparent preparation, model, and execution wrappers

**Files:**
- Modify: `scripts/minimal_intent_worker_real_compile_smoke.py:217-498`
- Test: `mcp_server/tests/test_minimal_intent_worker_real_compile_smoke.py`

**Interfaces:**
- Consumes: Task 1 recorder, existing `ToolDispatcher.dispatch`, existing `LiteLLMWorkerTransport.send`, existing restricted executor checks.
- Produces:
  - `_LiveCallCounts(preparation, planner, worker, execution)`
  - `_RecordingPreparationDispatcher(delegate, recorder, counts)`
  - `_RecordingModelTransport(role, delegate, recorder, counts)`
  - recorder-aware `_RestrictedRealToolExecutor(dispatch, recorder, counts)`.

- [ ] **Step 1: Write the wrapper ordering RED**

Create sync model and async tool delegates that append entry sentinels. Use a
recording stream that appends a sentinel after each flush. Require:

```text
request flush
delegate entry exactly once
response flush
```

Require returned raw string/tool mapping object identity to be unchanged.

- [ ] **Step 2: Run the RED**

Run the exact new test. Expected: FAIL because the recording wrappers do not
exist; delegate behavior itself must be valid.

- [ ] **Step 3: Implement call counts and preparation wrapper**

```python
@dataclass(slots=True)
class _LiveCallCounts:
    preparation: int = 0
    planner: int = 0
    worker: int = 0
    execution: int = 0
```

Preparation assigns `call_index=counts.preparation + 1`, records/flushed
`tool_request` with `phase="preparation"`, increments count immediately before
delegation, delegates once, then records raw response or exception before
return/raise.

- [ ] **Step 4: Implement the closed Planner/Worker transport wrapper**

Accept only exact roles `planner` and `worker`. `send()` writes role-local
request index and exact prompt artifact, increments the role count immediately
before one delegate call, then writes exact raw response or exception. Never
record provider kwargs, headers, call telemetry, or transport attributes.

- [ ] **Step 5: Make the restricted execution wrapper recorder-aware**

Preserve all existing sequence and `port` checks before any trace event. For an
admitted call, write phase `execution`, execution-local call index, tool name,
and exact params; increment before delegation; record raw response before exact
dict validation. A non-dict response is traced before the existing `TypeError`.

- [ ] **Step 6: Add identity, exception, and trace-failure tests**

For every wrapper prove:

```text
successful tracing + return    -> exact result identity
successful tracing + exception -> exact exception identity
request trace failure          -> zero delegate calls
response trace failure         -> one delegate call, no propagated result
exception trace failure        -> one delegate call, trace failure supersedes
```

Exception rows retain local type/message. Stdout-facing trace failures contain
no sentinel message. Repeat the matrix with a request short write and with a
delegate exception whose `__str__()` raises. The short request write enters no
delegate; the unstringable delegate exception counts that one delegate call,
flushes the fixed serialization-rejection row, and prevents the next external
call.

- [ ] **Step 7: Add phase/index and zero-dispatch tests**

Drive preparation `[1,2,3]`, execution `[1,2]`, Planner `[1]`, and Worker `[1]`.
Require one global recorder sequence without gaps. Port override,
update-before-create, repeated/substituted calls, and post-update calls must
write no admitted request event and enter no delegate.

- [ ] **Step 8: Run Task 2 tests**

```powershell
& C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_minimal_intent_worker_real_compile_smoke.py `
  mcp_server\tests\test_minimal_intent_worker_model_smoke.py `
  mcp_server\tests\test_minimal_intent_worker_integration.py `
  mcp_server\tests\test_local_worker_adapter.py -q
```

- [ ] **Step 9: Commit Task 2**

```powershell
git add scripts/minimal_intent_worker_real_compile_smoke.py `
  mcp_server/tests/test_minimal_intent_worker_real_compile_smoke.py
git commit -m "feat(smoke): trace live call boundaries"
```

### Task 3: Own the operator lifecycle and trace-failure precedence

**Files:**

- Modify: `scripts/minimal_intent_worker_real_compile_smoke.py`
- Modify: `mcp_server/tests/test_minimal_intent_worker_real_compile_smoke.py`

This task connects the private recorder to the existing operator lifecycle. It
does not change live eligibility, preparation equations, model configuration,
the product integration runner, or native stop meanings.

- [ ] **Step 1: Write lifecycle RED tests**

Add tests using a temporary `LOCALAPPDATA` and injected private seams. Prove:

```text
no arguments / invalid arguments
-> trace_path is null
-> discovery, tools, Planner, and Worker remain at zero

exact --execute-live + profile or discovery refusal
-> run_started and run_finished are flushed
-> no live capability is constructed or called

trace open/header failure
-> trace_write_failed
-> trace_path reports the absolute path only when the file was created
-> discovery, tools, Planner, and Worker remain at zero
```

The live-flag tests remain controlled in-process tests. They must not launch the
operator script or contact an external system.

- [ ] **Step 2: Run the lifecycle RED**

Run only the new tests. Expected: FAIL because `main()` does not own a trace
and the summary has no `trace_path`.

- [ ] **Step 3: Add the bounded summary field and failure projector**

Add `trace_path` to `_SUMMARY_FIELDS` and every `_bounded_summary()` result.
Use an exact string path only after a trace path is allocated; otherwise use
`None`. Add one private projector:

```python
def _trace_write_failure_summary(
    *,
    trace_path: Path | None,
    preparation_status: str,
    target: _DiscoveredTarget | None,
    call_counts: _LiveCallCounts | None,
    known_native_summary: Mapping[str, object] | None = None,
) -> dict[str, object]:
    ...
```

It emits the fixed operator status/reason `failed / trace_write_failed`, never
an exception message. It may preserve safely known native status fields after
normal native completion, but it sets any unprovable later counts or fields to
`None`.

- [ ] **Step 4: Open and flush `run_started` before live contact**

After exact argument admission, allocate the no-clobber trace path, open the
recorder, and flush `run_started` before discovery, Rhino, Planner, or Worker
contact. Its payload is closed and local:

```python
{
    "intent": _FIXED_INTENT,
    "profile": _PROFILE,
    "expected_planner_model": _PLANNER_MODEL,
    "expected_worker_model": _WORKER_MODEL,
}
```

Do not include authorization claims, credentials, environment dumps, model
responses, or provider metadata.

- [ ] **Step 5: Thread one recorder and one call counter through the run**

Update only private script functions. The top-level exact-live path in `main()`
owns recorder creation, `_LiveCallCounts`, every early-stop `run_finished`, and
final close. It opens the recorder before profile resolution and discovery,
then passes the same recorder and counters into `_run_live_once()`:

```python
async def _run_live_once(
    roles: _ResolvedRoles,
    target: _ResolvedRhinoTarget,
    *,
    recorder: _JsonlFlightRecorder,
    call_counts: _LiveCallCounts,
) -> _LiveRun:
    ...
```

`_run_live_once()` must not create, finish, close, or replace either object.
It passes both into `_run_prepared_once()`, which constructs the recording
Planner/Worker transports and recording restricted executor. The same
monotonically increasing recorder sequence spans pre-role/profile stops,
discovery, preparation, Planner, execution tools, and Worker.

- [ ] **Step 6: Enforce trace-failure precedence after every phase**

Product adapters may convert ordinary transport exceptions into native typed
stops. Therefore the operator must inspect the recorder failure state after
each preparation call, Planner return, integration return, and projection
batch. Once trace recording fails:

```text
the already-entered call remains counted
no subsequent model or tool call occurs
no original return value is propagated across the failed trace boundary
stdout reports only bounded trace_write_failed
```

Use the existing graph/control flow to stop downstream execution; do not add a
retry, product observer, or replacement result inside product modules.

- [ ] **Step 7: Centralize logical completion and physical close**

Add private helpers with equivalent closed responsibilities:

```python
def _run_finished_payload(summary: Mapping[str, object]) -> dict[str, object]:
    ...

def _finish_trace_or_failure(
    recorder: _JsonlFlightRecorder,
    summary: Mapping[str, object],
    ...,
) -> dict[str, object]:
    ...
```

For every ordinary completed stop, write and flush `run_finished` after all
applicable ownership-backed projections. Then flush and close the file before
emitting a successful or ordinary-stop summary. If close fails after
`run_finished`, the row remains in the incomplete trace, but stdout becomes
`trace_write_failed`. A failure before `run_finished` leaves the last
successfully flushed row as the physical end; no repair row is appended later.
The `run_finished` payload is an explicit projection of only
`operator_status`, `operator_reason`, and the safely known preparation,
Planner, Worker, and execution-tool call counts.

- [ ] **Step 8: Add the complete failure-locus matrix**

Cover open, header, request, response, exception, projection, `run_finished`,
final flush, and close failures. For each case assert exact call counts and the
last successfully flushed event. Also prove:

```text
open/header/request failure before call -> zero calls at that boundary
response/exception write failure        -> entered call counted once
failure before run_finished              -> run_finished absent
close failure after run_finished flush   -> run_finished may remain
```

No sentinel exception message may reach stdout or stderr.

- [ ] **Step 9: Run Task 3 tests**

```powershell
& C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_minimal_intent_worker_real_compile_smoke.py `
  mcp_server\tests\test_minimal_intent_worker_model_smoke.py `
  mcp_server\tests\test_minimal_intent_worker_integration.py -q
```

- [ ] **Step 10: Commit Task 3**

```powershell
git add scripts/minimal_intent_worker_real_compile_smoke.py `
  mcp_server/tests/test_minimal_intent_worker_real_compile_smoke.py
git commit -m "feat(smoke): own live trace lifecycle"
```

### Task 4: Project the returned native causal chain

**Files:**

- Modify: `scripts/minimal_intent_worker_real_compile_smoke.py`
- Modify: `mcp_server/tests/test_minimal_intent_worker_real_compile_smoke.py`

These are explicit, script-local projectors over already returned native
objects. They are telemetry only. They never replace existing typed receipts,
graph state, native results, or product validation.

- [ ] **Step 1: Write the observed-stop RED witness**

Use the causal fake dispatcher to return a create response whose normalized
receipt is retained but whose producer projection prevents `verify_create`
from becoming ready. Drive the real integration until its returned stop is:

```text
create response retained
-> create producer outcome projected
-> verify_create not ready
-> empty ready-node set
-> selector_halt:none_ready
```

Require exactly one Planner call, one execution-tool call, and zero Worker
calls. Assert the JSONL event subsequence includes the raw create response,
the retained normalized receipt, producer outcome, resulting node statuses,
empty ready-node set, and `selector_halt:none_ready`. Expected initial result:
FAIL because returned-record projectors do not exist.

- [ ] **Step 2: Add the Planner-admission projector**

Implement:

```python
def _project_planner_admission(result: MinimalIntentWorkerIntegrationResult) -> dict[str, object]:
    ...
```

Emit it only when the validated draft exists. Include only the admitted four
fields and the adapter status needed to understand admission. Do not serialize
raw dataclasses, prompts, provider metadata, or nonexistent placeholders.

- [ ] **Step 3: Add the compiled-workflow projector**

Implement:

```python
def _project_compiled_workflow(result: MinimalCSharpRepairHandoffResult) -> dict[str, object]:
    ...
```

Emit an explicit bounded summary only when the handoff exists. Project the
existing `WorkflowCompileRecord` field by field: workflow/compiler/schema and
contract identities, provider/template identities, ordered graph/initial/rule/
terminal node IDs, expected refs, step kinds by rule, and `max_steps`. Require
the scaffold workflow ID, node IDs, and `max_steps` to agree with that retained
record. Do not copy execution parameters, C# code, component GUIDs, prompts, or
full graph rules into this summary.

- [ ] **Step 4: Add native step and graph-state projectors**

Implement explicit field projectors rather than `asdict()`:

```python
def _project_native_steps(
    result: MinimalCSharpRepairHandoffResult,
) -> tuple[dict[str, object], ...]:
    ...

def _project_graph_state(graph: PlanGraph) -> dict[str, object]:
    return {
        "node_statuses": [
            {"node_id": node_id, "status": graph.nodes[node_id].status}
            for node_id in sorted(graph.nodes)
        ],
        "ready_node_ids": sorted(node.id for node in runnable_nodes(graph)),
    }
```

Each step event is owned by the same-index `CurrentStepRecord`, same-index
supply record, and that step's returned graph. Include bounded fields for step
index, accepted node, execution kind/failure, producer outcome, verifier
outcome, normalized receipt projection, graph state, and supply decision/reason.
Reject record/supply/graph length disagreement as an internal projection error.

- [ ] **Step 5: Add the final native-result projector**

Implement:

```python
def _project_final_native_result(
    integration: MinimalIntentWorkerIntegrationResult,
    call_counts: _LiveCallCounts,
) -> dict[str, object]:
    ...
```

When a handoff exists, retain terminal stage/reason, exact entered call counts,
the final graph state/ready set, and any terminal/control supply row not owned
by a `CurrentStepRecord`. When no handoff exists, project only the integration
stop fields and entered call counts. The local trace retains the exact returned
native reason. Only the separate stdout summary passes that reason through the
existing safe reason projector, so model-authored diagnostic text does not leak
to stdout.

- [ ] **Step 6: Emit projections only from owning returns**

After a normal integration return, emit in order when applicable:

```text
planner_admission
compiled_workflow
native_step_projection (zero or more)
final_native_result
run_finished
```

Profile, discovery, and preparation stops emit none of the first four. Planner
or draft-admission stops may emit only the projections whose owning objects
exist. If the integration raises, write `handoff_raised` with bounded local
exception type/message and do not fabricate workflow, graph, or native-result
projections.

- [ ] **Step 7: Complete the ownership and prefix test matrix**

Cover:

```text
role/discovery/preparation stop -> no Planner/workflow/native placeholders
Planner transport stop          -> Planner request/response or exception only
draft-admission stop            -> admission ownership respected
create stop                     -> one native step and returned graph state
worker refusal/failure          -> legitimate [create] execution prefix
completed path                  -> legitimate [create, update] execution prefix
integration raise               -> handoff_raised only after observed calls
```

Add sentinel payloads to raw model/tool trace events and prove they are present
in the local JSONL but absent from stdout/stderr.

- [ ] **Step 8: Run Task 4 tests**

```powershell
& C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_minimal_intent_worker_real_compile_smoke.py `
  mcp_server\tests\test_minimal_intent_worker_integration.py `
  mcp_server\tests\test_minimal_csharp_repair_handoff.py `
  mcp_server\tests\test_plan_graph_current_step_runner.py `
  mcp_server\tests\test_plan_graph_current_step_stream.py -q
```

- [ ] **Step 9: Commit Task 4**

```powershell
git add scripts/minimal_intent_worker_real_compile_smoke.py `
  mcp_server/tests/test_minimal_intent_worker_real_compile_smoke.py
git commit -m "feat(smoke): trace native graph transitions"
```

### Task 5: Verify the complete seam and reconcile the durable plan

**Files:**

- Modify: `docs/superpowers/plans/2026-07-30-minimal-intent-worker-live-flight-recorder.md`

- [ ] **Step 1: Run the full focused regression seam**

```powershell
& C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_minimal_intent_worker_real_compile_smoke.py `
  mcp_server\tests\test_minimal_intent_worker_model_smoke.py `
  mcp_server\tests\test_minimal_intent_worker_integration.py `
  mcp_server\tests\test_minimal_csharp_repair_handoff.py `
  mcp_server\tests\test_plan_graph_workflow_contract.py `
  mcp_server\tests\test_local_worker_turn_context.py `
  mcp_server\tests\test_local_worker_turn_harness.py `
  mcp_server\tests\test_plan_graph_worker_action_apply.py `
  mcp_server\tests\test_gh_edit_contract.py `
  mcp_server\tests\test_plan_graph_workflow_contract_chain.py `
  mcp_server\tests\test_plan_graph_live_dispatch.py `
  mcp_server\tests\test_plan_graph_current_step_stream.py `
  mcp_server\tests\test_plan_graph_current_step_runner.py `
  mcp_server\tests\test_local_worker_adapter.py `
  mcp_server\tests\test_local_worker_turn_request.py `
  mcp_server\tests\test_local_worker_turn_response.py `
  mcp_server\tests\test_local_worker_turn_disposition.py -q
```

Record the exact count and duration. Any failure returns to the owning task; do
not weaken a test or broaden the recorder.

- [ ] **Step 2: Run compilation and repository hygiene checks**

```powershell
& C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe -m compileall `
  scripts\minimal_intent_worker_real_compile_smoke.py `
  mcp_server\tests\test_minimal_intent_worker_real_compile_smoke.py
git diff --check
git status --short
```

- [ ] **Step 3: Audit the final surface**

Require the complete merge diff to contain exactly:

```text
docs/superpowers/specs/2026-07-30-minimal-intent-worker-live-flight-recorder-design.md
docs/superpowers/plans/2026-07-30-minimal-intent-worker-live-flight-recorder.md
scripts/minimal_intent_worker_real_compile_smoke.py
mcp_server/tests/test_minimal_intent_worker_real_compile_smoke.py
```

Verify no `mcp_server/src/rook/**` product module changed. Search the script for
forbidden expansion terms and manually inspect every match:

```powershell
rg -n "manifest|checksum|fingerprint|seal|archive|database|retry|fallback|observer|registry" `
  scripts\minimal_intent_worker_real_compile_smoke.py
```

Only the approved local trace path and ordinary existing live-run terminology
may remain; no evidence-lifecycle framework is allowed.

- [ ] **Step 4: Run only safe subprocess refusals**

Run the script with no arguments and with one invalid argument. Assert one
bounded JSON line, empty stderr, refusal exit codes, `trace_path: null`, and no
trace file. Do not run `--execute-live` during implementation or review.

- [ ] **Step 5: Reconcile the plan execution ledger**

Mark every operational checkbox complete only after its evidence exists. Append
an execution record containing:

- final feature HEAD;
- focused test count and duration;
- compile result;
- `git diff --check` result;
- exact four-file scope;
- safe refusal outputs;
- confirmation that no provider, worker box, Rhino, or Grasshopper contact
  occurred;
- the deterministic current-stop trace witness result.

- [ ] **Step 6: Commit the documentation-only reconciliation**

```powershell
git add docs/superpowers/plans/2026-07-30-minimal-intent-worker-live-flight-recorder.md
git commit -m "docs: reconcile live flight recorder plan"
```

- [ ] **Step 7: Stop for final independent implementation review**

Do not push, open a PR, merge, or execute the live flag. Report the exact HEAD,
test evidence, diff scope, and clean worktree for independent review.

## Completion Criteria

- [ ] The recorder is private to the real compile smoke script.
- [ ] A no-clobber JSONL trace is opened and flushed before any live contact.
- [ ] Every admitted external request is flushed before its call.
- [ ] Every raw response or ordinary exception is flushed before a later call.
- [ ] Rows and total bytes obey the exact 256 KiB / 4 MiB-minus-4-KiB rules.
- [ ] Rejection rows use the closed event/reason mapping and reserve.
- [ ] Trace failure stops subsequent contact and yields bounded stdout.
- [ ] `run_finished` reflects logical completion; close success remains separate.
- [ ] Returned-record projectors emit only ownership-backed native facts.
- [ ] The observed `selector_halt:none_ready` chain is visible end to end.
- [ ] Existing product modules and native receipt/result authority remain unchanged.
- [ ] The full focused seam passes and the worktree is clean.
- [ ] No external system is contacted during implementation or review.
