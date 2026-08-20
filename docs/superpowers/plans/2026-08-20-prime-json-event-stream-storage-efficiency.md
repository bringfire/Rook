# Prime JSON Event-Stream Storage Efficiency Implementation Plan

**Status:** APPROVED DESIGN; IMPLEMENTATION UNSTARTED AND UNQUALIFIED

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an opt-in, capture-owned Prime JSON event writer that retains complete live semantics while eliminating cumulative `message_update.partial` storage amplification, then qualify it offline against the sealed 3.54 GB Vessel stream.

**Architecture:** Prime continues to emit its complete JSON event stream unchanged. A focused Rook campaign module reads bounded binary JSONL rows, hashes the original bytes incrementally, persists exact non-update rows and closed assistant deltas, and writes a deterministic custody sidecar; the campaign runner only selects this path for protocols that explicitly admit it and routes existing consumers through one path resolver. A separate offline-only harness verifies immutable source custody, performs two deterministic replays, reconstructs terminal messages, and compares the unchanged V2 trace-admission result before any live contact is considered.

**Tech Stack:** Python 3.10+, standard-library `json`, `hashlib`, `queue`, `threading`, and `pathlib`; pytest; existing Rook campaign/evidence helpers; PowerShell verification on Windows.

**Spec:** `docs/superpowers/specs/2026-08-20-prime-json-event-stream-storage-efficiency-design.md`, SHA-256 `E5FAAE11FDCB40C184F0478E611D77F777B2C8E552B99A6736555592BC0FDC63`.

## Global Constraints

- Implement only after the independently approved design at Rook commit `1dfd45e78800b678a07dfbec6bba6afe58be9d03`, plus the approved P3 clarification incorporated with this plan.
- Work only in `C:/UDEV/Rook/.worktrees/coordinating-intelligence-evidence-ledger`; do not edit the Rook primary checkout or either Prime worktree.
- Do not modify Prime, `mcp_server/src/rook/gh_behavioral_acceptance.py`, `mcp_server/src/rook/gh_behavioral_acceptance_v2.py`, model guidance, Rook mutation behavior, Rhino, Grasshopper, or sealed historical evidence.
- Preserve V2 SHA-256 `55211B778B44C96729A21D9DAE430B2883F4636520C030E1EBFD3B8F896508FF` throughout implementation and qualification.
- The sealed source is read-only: `C:/UDEV/RookEvidence/2026-08-20-qwen38-multimodal-vessel-massing-v5/MV1/operator/prime.jsonl`, 3,543,087,572 bytes, 74,473 rows, SHA-256 `F79FF8A329993C9770B7E103B3F10620A6E118C5AD58E6184E9777EDFBFCAA3B`.
- Verify the global manifest `7BDD42FE284CDCF34AE101CE5550E9A1B5B7742A90F0437B5735C3FB5F67259D` and row manifest `FCD5205D361C1772ADB8C266CB33A9490F4679697CE28DE3B7D75636065B13A4` before creating qualification output.
- Preserve source log SHA-256 `E86FDB1F88B1357F8811F3FC8F3DDBEC078C4949B873615E0CE1D98A98B966C8` and process-result SHA-256 `4920BA546D4FFF73C1C8DDEB8887E5C1CABA3762A5775C75C516683D54342F70`.
- Use TDD for every production change. Retain a causal RED result before writing the corresponding GREEN implementation.
- Use only standard-library dependencies. Do not add compression, a cache, a database, `fsync`, a Prime fork change, or a second event protocol owner.
- Freeze `MAX_SOURCE_ROW_BYTES = 67_108_864`, `SOURCE_READ_CHUNK_BYTES = 65_536`, and `MONITOR_QUEUE_MAX_EVENTS = 1` in code. Protocols and environment variables cannot override them.
- Historical protocols without `primeEventCapture` continue to write `operator/prime.jsonl` through the current text reader and retain their current process-result shape.
- New compact capture writes `operator/prime-events.compact.jsonl` and `operator/prime-event-capture-custody.json`; it never aliases the compact representation to `operator/prime.jsonl`.
- Every admitted source row produces exactly one retained row. Unknown but valid event shapes pass through byte-for-byte; malformed rows fail capture.
- Publish an original parsed stdout event to the live monitor only after its retained row has been written.
- A complete custody record requires stdout EOF, successful close, equal source/retained row counts, and successful post-write verification. Incomplete prefixes never receive complete custody.
- No code path may call `read_bytes()` or `read_text()` on the 3.54 GB source, materialize all source rows, or create a full raw copy unless a future protocol explicitly selects `compact_with_raw_debug`.
- Default qualification must achieve at least 95% reduction using `(compact stream bytes + custody bytes) / source bytes <= 0.05`.
- No Prime, Qwen, Ollama, Rook MCP, network, Rhino, Grasshopper, or Vessel contact is authorized in this plan.
- Stop after committed offline qualification and independent implementation review. A later small non-Rhino Prime/Qwen smoke requires separate explicit approval.

---

## File And Ownership Map

| File | Change | Sole responsibility |
|---|---|---|
| `scripts/prime_json_event_capture.py` | Create | Closed protocol config, bounded LF framing, strict JSON admission, delta transformation, incremental hashing, compact/raw-debug writing, custody verification, retained-path resolution, event iteration, and terminal-message reconstruction. |
| `scripts/qwen38_self_termination_campaign_runner.py` | Modify narrowly | Opt-in compact subprocess capture, one-event live handoff, existing monitor adaptation, protocol-owned path selection at current consumers, and historical raw-path preservation. |
| `scripts/qualify_prime_json_event_capture.py` | Create | Offline-only source admission, dual sealed replay, unchanged-V2 comparison, consumer/history parity, size/determinism assertions, and qualification evidence sealing. |
| `mcp_server/tests/test_prime_json_event_capture.py` | Create | Capture-module unit and causal tests for all closed schemas, bounded ingress, backpressure, failures, custody, determinism, and reconstruction. |
| `mcp_server/tests/test_qwen38_self_termination_campaign_runner.py` | Modify narrowly | Historical/compact runner branching, path resolver use, monitor parity, and exact current-consumer entry-point parity. |
| `mcp_server/tests/test_qualify_prime_json_event_capture.py` | Create | Offline protocol custody, immutable-source admission, dual replay, V2 parity, no-contact, and manifest behavior using small fixtures. |
| `docs/superpowers/experiments/2026-08-20-prime-json-event-capture-offline-qualification-v1.json` | Create after code stabilizes | Closed source, owner, command, output-root, capture-config, and expected-result bytes for the one offline qualification. |
| `docs/superpowers/reports/2026-08-20-prime-json-event-capture-offline-qualification.md` | Create after replay | Exact test, size, hash, reconstruction, parity, limitation, and worktree evidence for independent implementation review. |

The existing `scripts/reconcile_prime_compaction_trace.py` and its protocol remain unchanged because their hashes own historical V2 reconciliation evidence.

## Stable Interfaces

`scripts/prime_json_event_capture.py` exposes this bounded surface:

```text
MAX_SOURCE_ROW_BYTES = 67_108_864
SOURCE_READ_CHUNK_BYTES = 65_536
MONITOR_QUEUE_MAX_EVENTS = 1
FAILURE_CODES: frozenset[str]

PrimeEventCaptureConfig
  mode: str
  retained_path: PurePosixPath
  custody_path: PurePosixPath
  raw_debug_path: PurePosixPath | None

CapturedPrimeRow
  source_row: int
  source_bytes: int
  parsed_event: dict[str, Any]
  retained_bytes: bytes
  compacted: bool
  raw_fallback_message_update: bool

PrimeCaptureError(RuntimeError)
  code: str

validate_capture_config(value: Any) -> PrimeEventCaptureConfig | None
transform_prime_row(raw_row: bytes, source_row: int) -> CapturedPrimeRow
iter_bounded_lf_rows(stream: BinaryIO) -> Iterator[bytes]
capture_binary_stream(
    stream: BinaryIO,
    *,
    config: PrimeEventCaptureConfig,
    row_root: Path,
    publish: Callable[[dict[str, Any]], None],
) -> dict[str, Any]
verify_capture_custody(
    config: PrimeEventCaptureConfig, row_root: Path
) -> dict[str, Any]
resolve_prime_event_path(protocol: dict[str, Any], row_root: Path) -> Path
iter_retained_prime_events(
    protocol: dict[str, Any], row_root: Path
) -> Iterator[dict[str, Any]]
reconstruct_terminal_assistant_messages(
    protocol: dict[str, Any], row_root: Path
) -> list[dict[str, Any]]
```

`validate_capture_config(None)` returns `None` for historical protocols. Every non-null config is a closed `rook.prime_event_capture_config:v1` object. Paths are relative POSIX paths rooted under `operator/`; absolute paths, `..`, duplicates, aliases, and runner-limit fields refuse.

`transform_prime_row()` accepts exactly one LF-terminated source row. It returns the original parsed event for live monitoring and either the original bytes or one canonical compact row. It never raises for an unfamiliar valid event shape; that row takes exact raw fallback.

`capture_binary_stream()` opens destinations exclusively, writes before publishing, blocks in the supplied callback when the runner's one-event queue is full, closes on EOF, writes complete custody, verifies it, and returns the verified custody object. It writes `rook.prime_event_capture_failure:v1` best-effort and raises `PrimeCaptureError` on the closed failure codes.

`resolve_prime_event_path()` returns historical `operator/prime.jsonl` when config is absent. For compact protocols it verifies complete custody and returns only the exact retained path bound by protocol and custody.

The runner adds one method without removing the historical entry point:

```text
RunMonitor.consume_prime_event(
    self, value: dict[str, Any]
) -> str | None
RunMonitor.consume_prime_line(
    self, line: str
) -> str | None
```

`consume_prime_line()` strictly parses a historical or exact-passthrough line
and delegates to `consume_prime_event()`.

The qualification harness exposes:

```text
validate_qualification_protocol(value: Any) -> dict[str, Any]
verify_source_evidence(protocol: dict[str, Any]) -> dict[str, Any]
run_qualification(protocol_path: Path) -> dict[str, Any]
```

---

### Task 1: Closed Assistant-Delta Transformation

**Files:**
- Create: `scripts/prime_json_event_capture.py`
- Create: `mcp_server/tests/test_prime_json_event_capture.py`

**Interfaces:**
- Consumes: raw LF-terminated Prime JSON rows and the nine approved source subtypes.
- Produces: `validate_capture_config()`, `transform_prime_row()`, `CapturedPrimeRow`, canonical compact rows, and closed `PrimeCaptureError` values used by every later task.

- [ ] **Step 1: Add the exact config-admission RED tests**

Create a dynamic import helper for `scripts/prime_json_event_capture.py`, then add tests asserting that `None` is historical, the approved compact and raw-debug shapes normalize exactly, and open objects, booleans, absolute paths, parent traversal, equal paths, and limit overrides refuse.

```python
CAPTURE_PATH = ROOT / "scripts" / "prime_json_event_capture.py"

@pytest.fixture
def capture():
    spec = importlib.util.spec_from_file_location(
        "prime_json_event_capture_for_tests", CAPTURE_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module

def canonical_test_line(value: dict[str, Any]) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )

def approved_capture_config() -> dict[str, Any]:
    return {
        "schema": "rook.prime_event_capture_config:v1",
        "mode": "compact",
        "retainedPath": "operator/prime-events.compact.jsonl",
        "custodyPath": "operator/prime-event-capture-custody.json",
        "rawDebugPath": None,
    }

def assistant_message(content: dict[str, Any]) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": [content],
        "api": "openai-completions",
        "provider": "ollama",
        "model": "qwen3.8:27b",
        "usage": {
            "input": 1,
            "output": 1,
            "cacheRead": 0,
            "cacheWrite": 0,
            "totalTokens": 2,
            "cost": {
                "input": 0,
                "output": 0,
                "cacheRead": 0,
                "cacheWrite": 0,
                "total": 0,
            },
        },
        "stopReason": "toolUse",
        "timestamp": 1,
    }

def source_update_row(
    subtype: str, event_payload: dict[str, Any], content: dict[str, Any]
) -> bytes:
    message = assistant_message(copy.deepcopy(content))
    event = {
        "type": subtype,
        "contentIndex": 0,
        **copy.deepcopy(event_payload),
        "partial": copy.deepcopy(message),
    }
    return canonical_test_line(
        {"type": "message_update", "message": message, "assistantMessageEvent": event}
    )

def tool_start_block() -> dict[str, Any]:
    return {
        "type": "toolCall",
        "id": "call-1",
        "name": "ipython",
        "arguments": {"code": "print(1)"},
        "partialArgs": '{"code":"print(1)"}',
        "streamIndex": 0,
    }

def final_tool_call() -> dict[str, Any]:
    return {
        "type": "toolCall",
        "id": "call-1",
        "name": "ipython",
        "arguments": {"code": "print(1)"},
    }

def passthrough_row(event_type: str) -> bytes:
    return canonical_test_line({"type": event_type})

def text_delta_source_row(delta: str) -> bytes:
    return source_update_row(
        "text_delta",
        {"delta": delta},
        {"type": "text", "text": delta},
    )

def test_capture_config_is_closed_and_paths_are_operator_local(capture):
    value = {
        "schema": "rook.prime_event_capture_config:v1",
        "mode": "compact",
        "retainedPath": "operator/prime-events.compact.jsonl",
        "custodyPath": "operator/prime-event-capture-custody.json",
        "rawDebugPath": None,
    }
    admitted = capture.validate_capture_config(value)
    assert admitted.mode == "compact"
    assert admitted.retained_path.as_posix() == value["retainedPath"]
    assert admitted.custody_path.as_posix() == value["custodyPath"]
    assert capture.validate_capture_config(None) is None

@pytest.mark.parametrize(
    "change",
    [
        {"extra": True},
        {"retainedPath": "C:/escape.jsonl"},
        {"retainedPath": "operator/../escape.jsonl"},
        {"maxSourceRowBytes": 1},
    ],
)
def test_capture_config_refuses_open_or_ambient_authority(capture, change):
    value = approved_capture_config() | change
    with pytest.raises(ValueError, match="capture_config_invalid"):
        capture.validate_capture_config(value)
```

- [ ] **Step 2: Add parameterized RED tests for all nine compact records**

Build source rows with root keys exactly `type`, `message`, and `assistantMessageEvent`; require type-sensitive structural equality between `message` and `partial`. Assert exact canonical output keys for starts, deltas, and ends. Include text/thinking signatures, `redacted`, and tool-call `thoughtSignature` as optional typed fields.

```python
@pytest.mark.parametrize(
    ("subtype", "event_payload", "content", "retained_event_keys"),
    [
        ("text_start", {}, {"type": "text", "text": "seed"}, {"type", "contentIndex"}),
        ("text_delta", {"delta": "x"}, {"type": "text", "text": "x"}, {"type", "contentIndex", "delta"}),
        ("text_end", {"content": "x"}, {"type": "text", "text": "x"}, {"type", "contentIndex", "content"}),
        ("thinking_start", {}, {"type": "thinking", "thinking": "seed"}, {"type", "contentIndex"}),
        ("thinking_delta", {"delta": "r"}, {"type": "thinking", "thinking": "r"}, {"type", "contentIndex", "delta"}),
        ("thinking_end", {"content": "r"}, {"type": "thinking", "thinking": "r"}, {"type", "contentIndex", "content"}),
        ("toolcall_start", {}, tool_start_block(), {"type", "contentIndex"}),
        ("toolcall_delta", {"delta": "{}"}, tool_start_block(), {"type", "contentIndex", "delta"}),
        ("toolcall_end", {"toolCall": final_tool_call()}, final_tool_call(), {"type", "contentIndex", "toolCall"}),
    ],
)
def test_transform_emits_each_closed_delta_shape(
    capture, subtype, event_payload, content, retained_event_keys
):
    row = source_update_row(subtype, event_payload, content)
    result = capture.transform_prime_row(row, 7)
    retained = json.loads(result.retained_bytes)
    assert result.compacted is True
    assert set(retained["assistantMessageEvent"]) == retained_event_keys
    assert retained["sourceRow"] == 7
    assert retained["sourceBytes"] == len(row)
```

- [ ] **Step 3: Add scratch-field and fail-closed RED tests**

Prove `partialArgs` and `streamIndex` are admitted only on source content blocks referenced by `toolcall_start` and `toolcall_delta`, omitted from retained `contentStart`, and forbidden on final `toolcall_end.toolCall`. Prove boolean `contentIndex`/`streamIndex`, unknown event fields, wrong content kind, unequal `partial`, and non-finite values take raw fallback or malformed refusal exactly as the spec requires.

```python
def test_tool_stream_scratch_is_admitted_then_removed(capture):
    block = {
        "type": "toolCall",
        "id": "call-1",
        "name": "ipython",
        "arguments": {"code": "print(1)"},
        "partialArgs": '{"code":"print(1)"}',
        "streamIndex": 0,
    }
    result = capture.transform_prime_row(source_update_row("toolcall_start", {}, block), 1)
    retained = json.loads(result.retained_bytes)
    assert retained["contentStart"] == {
        "type": "toolCall",
        "id": "call-1",
        "name": "ipython",
        "arguments": {},
    }

def test_unknown_valid_update_shape_falls_back_byte_exact(capture):
    row = source_update_row("future_delta", {"delta": "x"}, {"type": "text", "text": "x"})
    result = capture.transform_prime_row(row, 1)
    assert result.retained_bytes == row
    assert result.compacted is False
    assert result.raw_fallback_message_update is True
```

- [ ] **Step 4: Run the focused tests and retain the causal RED**

Run:

```powershell
$python = "C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe"
& $python -m pytest mcp_server/tests/test_prime_json_event_capture.py -q
```

Expected: collection/import fails because `scripts/prime_json_event_capture.py` does not exist.

- [ ] **Step 5: Implement the minimal closed transformer**

Implement the constants, dataclasses, strict duplicate-key parser, type-sensitive structural equality, config validation, source-shape recognizers, canonical JSON encoding, start-content projection, and byte-exact raw fallback. `json.loads()` must use a duplicate-key hook and a rejecting `parse_constant`; Python booleans must never satisfy integer checks.

```python
def _canonical_line(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )

def transform_prime_row(raw_row: bytes, source_row: int) -> CapturedPrimeRow:
    parsed = _strict_source_row(raw_row)
    compact = _compact_message_update(parsed, source_row, len(raw_row))
    return CapturedPrimeRow(
        source_row=source_row,
        source_bytes=len(raw_row),
        parsed_event=parsed,
        retained_bytes=compact if compact is not None else raw_row,
        compacted=compact is not None,
        raw_fallback_message_update=(
            parsed.get("type") == "message_update" and compact is None
        ),
    )
```

- [ ] **Step 6: Run Task 1 GREEN tests and static compilation**

Run:

```powershell
& $python -m pytest mcp_server/tests/test_prime_json_event_capture.py -q
& $python -m py_compile scripts/prime_json_event_capture.py mcp_server/tests/test_prime_json_event_capture.py
```

Expected: all Task 1 tests pass and compilation exits `0`.

- [ ] **Step 7: Commit Task 1**

```powershell
git add scripts/prime_json_event_capture.py mcp_server/tests/test_prime_json_event_capture.py
git commit -m "feat: add compact Prime event transformation"
```

---

### Task 2: Bounded Stream, Custody, And Reconstruction

**Files:**
- Modify: `scripts/prime_json_event_capture.py`
- Modify: `mcp_server/tests/test_prime_json_event_capture.py`

**Interfaces:**
- Consumes: Task 1 config and row transformation.
- Produces: `iter_bounded_lf_rows()`, `capture_binary_stream()`, `verify_capture_custody()`, `resolve_prime_event_path()`, `iter_retained_prime_events()`, and `reconstruct_terminal_assistant_messages()`.

- [ ] **Step 1: Add exact framing-boundary RED tests**

Generate valid passthrough JSON rows whose total encoded sizes, including LF, are exactly 67,108,864 and 67,108,865 bytes. Test exact-boundary admission, oversized terminated refusal, oversized unterminated refusal before EOF, strict LF/UTF-8/JSON/object/duplicate-key behavior, and bounded 65,536-byte reads.

```python
def json_row_of_size(size: int, *, lf: bool = True) -> bytes:
    prefix, suffix = b'{"payload":"', b'"}'
    newline = b"\n" if lf else b""
    fill = size - len(prefix) - len(suffix) - len(newline)
    assert fill >= 0
    return prefix + (b"a" * fill) + suffix + newline

def test_exact_maximum_row_is_admitted(capture):
    row = json_row_of_size(capture.MAX_SOURCE_ROW_BYTES)
    assert list(capture.iter_bounded_lf_rows(io.BytesIO(row))) == [row]

@pytest.mark.parametrize("terminated", [True, False])
def test_oversized_row_refuses_at_frozen_boundary(capture, terminated):
    row = json_row_of_size(capture.MAX_SOURCE_ROW_BYTES + 1, lf=terminated)
    with pytest.raises(capture.PrimeCaptureError) as caught:
        list(capture.iter_bounded_lf_rows(io.BytesIO(row)))
    assert caught.value.code == "stdout_row_too_large"
```

- [ ] **Step 2: Add writer, raw-debug, failure, and custody RED tests**

Test exclusive path creation, one output row per source row, incremental uppercase SHA-256, source maximum row, compact/fallback counts, optional byte-identical raw debug, deterministic custody bytes, missing/altered custody, changed retained bytes, removed/duplicated/reordered rows, injected write/close failures, and best-effort incomplete failure records.

Freeze the complete failure vocabulary in one causal test:

```python
def test_capture_failure_code_catalog_is_exact(capture):
    assert capture.FAILURE_CODES == {
        "stdout_read_failed",
        "stdout_invalid_utf8",
        "stdout_missing_final_lf",
        "stdout_row_too_large",
        "stdout_json_invalid",
        "stdout_json_object_required",
        "stdout_json_duplicate_key",
        "compact_transform_failed",
        "compact_write_failed",
        "compact_close_failed",
        "raw_debug_write_failed",
        "raw_debug_close_failed",
        "capture_custody_write_failed",
        "capture_custody_missing",
        "capture_custody_mismatch",
        "capture_row_count_mismatch",
        "raw_debug_mismatch",
    }
```

```python
def test_complete_capture_writes_and_verifies_custody(capture, tmp_path):
    protocol = {"primeEventCapture": approved_capture_config()}
    config = capture.validate_capture_config(protocol["primeEventCapture"])
    rows = [passthrough_row("session"), text_delta_source_row("hello")]
    published = []
    custody = capture.capture_binary_stream(
        io.BytesIO(b"".join(rows)),
        config=config,
        row_root=tmp_path,
        publish=published.append,
    )
    assert custody["source"]["rows"] == 2
    assert custody["retained"]["rows"] == 2
    assert custody["retained"]["compactedMessageUpdates"] == 1
    assert capture.verify_capture_custody(config, tmp_path) == custody
    assert [event["type"] for event in published] == ["session", "message_update"]
```

Use a private `_open_exclusive(path)` helper so tests can inject writers that fail on `write()`, `flush()`, or `close()` without adding a public dependency-injection framework.

- [ ] **Step 3: Add the stalled-consumer RED test**

Run `capture_binary_stream()` on a thread with three small rows and `queue.Queue(maxsize=1).put` as `publish`. Wait until the queue holds row one and the retained file contains two rows. Assert the capture thread is blocked, queue size remains one, no third row is persisted, and source reads never exceed the fixed chunk. Drain one event and assert the capture completes with three retained rows and valid custody.

```python
class RecordingBytesIO(io.BytesIO):
    def __init__(self, value: bytes):
        super().__init__(value)
        self.requested_sizes: list[int] = []

    def read(self, size: int = -1) -> bytes:
        self.requested_sizes.append(size)
        return super().read(size)

def retained_row_count(root: Path) -> int:
    path = root / "operator" / "prime-events.compact.jsonl"
    if not path.exists():
        return 0
    with path.open("rb") as stream:
        return sum(1 for _ in stream)

def compact_config(capture):
    return capture.validate_capture_config(approved_capture_config())

def wait_until(predicate: Callable[[], bool], timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() >= deadline:
            raise AssertionError("condition_not_reached")
        time.sleep(0.01)

def drain_until_finished(events: queue.Queue, thread: threading.Thread) -> None:
    deadline = time.monotonic() + 2.0
    while thread.is_alive():
        if time.monotonic() >= deadline:
            raise AssertionError("capture_thread_did_not_finish")
        try:
            events.get(timeout=0.05)
        except queue.Empty:
            pass
    thread.join(timeout=0)

def test_stalled_consumer_applies_one_event_backpressure(capture, tmp_path):
    events = queue.Queue(maxsize=capture.MONITOR_QUEUE_MAX_EVENTS)
    stream = RecordingBytesIO(
        b"".join(passthrough_row(f"event_{i}") for i in range(3))
    )
    thread = threading.Thread(
        target=capture.capture_binary_stream,
        kwargs={
            "stream": stream,
            "config": compact_config(capture),
            "row_root": tmp_path,
            "publish": events.put,
        },
    )
    thread.start()
    wait_until(lambda: retained_row_count(tmp_path) == 2)
    assert events.qsize() == 1
    assert thread.is_alive()
    assert max(stream.requested_sizes) <= capture.SOURCE_READ_CHUNK_BYTES
    events.get(timeout=1)
    drain_until_finished(events, thread)
    assert retained_row_count(tmp_path) == 3
```

- [ ] **Step 4: Add deterministic reconstruction RED tests**

Build interleaved text, thinking, and tool-call streams across two assistant messages. Assert reconstructed terminal messages equal exact `message_end.message` objects, raw-fallback updates remain usable, content indices do not depend on adjacency, missing starts/ends fail closed, and two captures produce byte-identical compact streams and custody records.

Add these fixture helpers in the same test module so reconstruction does not
depend on campaign-runner behavior:

```python
def assistant_with_blocks(blocks: list[dict[str, Any]]) -> dict[str, Any]:
    value = assistant_message({"type": "text", "text": ""})
    value["content"] = copy.deepcopy(blocks)
    return value

def checkpoint_row(event_type: str, message: dict[str, Any]) -> bytes:
    return canonical_test_line({"type": event_type, "message": message})

def update_for_message(
    subtype: str,
    content_index: int,
    event_payload: dict[str, Any],
    message: dict[str, Any],
) -> bytes:
    return canonical_test_line(
        {
            "type": "message_update",
            "message": copy.deepcopy(message),
            "assistantMessageEvent": {
                "type": subtype,
                "contentIndex": content_index,
                **copy.deepcopy(event_payload),
                "partial": copy.deepcopy(message),
            },
        }
    )

def two_message_reconstruction_fixture() -> tuple[bytes, list[dict[str, Any]]]:
    empty = assistant_with_blocks([])
    text_started = assistant_with_blocks([{"type": "text", "text": ""}])
    text_complete = assistant_with_blocks([{"type": "text", "text": "A"}])
    both_started = assistant_with_blocks(
        [
            {"type": "text", "text": "A"},
            {"type": "thinking", "thinking": ""},
        ]
    )
    first_final = assistant_with_blocks(
        [
            {"type": "text", "text": "A"},
            {"type": "thinking", "thinking": "B"},
        ]
    )
    tool_streaming = assistant_with_blocks([tool_start_block()])
    tool_final = assistant_with_blocks([final_tool_call()])
    rows = [
        checkpoint_row("message_start", empty),
        update_for_message("text_start", 0, {}, text_started),
        update_for_message("text_delta", 0, {"delta": "A"}, text_complete),
        update_for_message("thinking_start", 1, {}, both_started),
        update_for_message("thinking_delta", 1, {"delta": "B"}, first_final),
        update_for_message("text_end", 0, {"content": "A"}, first_final),
        update_for_message("thinking_end", 1, {"content": "B"}, first_final),
        checkpoint_row("message_end", first_final),
        checkpoint_row("message_start", empty),
        update_for_message("toolcall_start", 0, {}, tool_streaming),
        update_for_message("toolcall_delta", 0, {"delta": "{}"}, tool_streaming),
        update_for_message(
            "toolcall_end", 0, {"toolCall": final_tool_call()}, tool_final
        ),
        checkpoint_row("message_end", tool_final),
    ]
    return b"".join(rows), [first_final, tool_final]

def test_reconstruction_equals_terminal_messages(capture, tmp_path):
    source, expected = two_message_reconstruction_fixture()
    protocol = {"primeEventCapture": approved_capture_config()}
    capture.capture_binary_stream(
        io.BytesIO(source),
        config=compact_config(capture),
        row_root=tmp_path,
        publish=lambda event: None,
    )
    reconstructed = capture.reconstruct_terminal_assistant_messages(protocol, tmp_path)
    assert reconstructed == expected
```

Tool-call deltas are retained for evidence, but final arguments come from the exact `toolcall_end.toolCall`; do not implement a permissive partial-JSON parser.

- [ ] **Step 5: Run the new tests to verify RED**

Run:

```powershell
& $python -m pytest mcp_server/tests/test_prime_json_event_capture.py -q
```

Expected: framing/writer/reconstruction tests fail because the Task 2 interfaces are absent.

- [ ] **Step 6: Implement bounded capture and verification**

Implement chunked LF framing with a single mutable row buffer capped at 64 MiB, exclusive output opens, incremental digests, compact/raw-debug writers, deterministic closed custody, best-effort failure records, custody re-verification, and protocol-owned path resolution. The writer must persist each retained row before invoking `publish(parsed_event)`.

```python
def iter_bounded_lf_rows(stream: BinaryIO) -> Iterator[bytes]:
    pending = bytearray()
    while True:
        chunk = stream.read(SOURCE_READ_CHUNK_BYTES)
        if not chunk:
            break
        cursor = 0
        while cursor < len(chunk):
            newline = chunk.find(b"\n", cursor)
            if newline < 0:
                _append_bounded(pending, chunk[cursor:])
                break
            _append_bounded(pending, chunk[cursor : newline + 1])
            yield bytes(pending)
            pending.clear()
            cursor = newline + 1
    if pending:
        raise PrimeCaptureError("stdout_missing_final_lf")
```

- [ ] **Step 7: Implement terminal-message reconstruction**

Seed only from exact assistant `message_start`, apply compact starts/deltas/ends by `contentIndex`, replace final tool blocks from `toolcall_end`, accept raw-fallback `message_update.message` as an exact partial checkpoint, and compare the reconstructed value type-sensitively with each exact assistant `message_end.message` before returning it.

- [ ] **Step 8: Run Task 2 GREEN and corruption tests**

Run:

```powershell
& $python -m pytest mcp_server/tests/test_prime_json_event_capture.py -q
& $python -m py_compile scripts/prime_json_event_capture.py mcp_server/tests/test_prime_json_event_capture.py
```

Expected: all capture tests pass, including exact 64 MiB rows and stalled-consumer completion.

- [ ] **Step 9: Commit Task 2**

```powershell
git add scripts/prime_json_event_capture.py mcp_server/tests/test_prime_json_event_capture.py
git commit -m "feat: add bounded Prime event capture custody"
```

---

### Task 3: Minimal Campaign Runner Integration And Consumer Parity

**Files:**
- Modify: `scripts/qwen38_self_termination_campaign_runner.py:1652` (protocol admission), `:2377` (monitor), `:3471` and `:3602` (capture/process loop), `:3804`, `:4648`, `:4857`, `:5331`, and `:5368` (post-run consumers)
- Modify: `mcp_server/tests/test_qwen38_self_termination_campaign_runner.py:393` and the focused monitor/consumer sections

**Interfaces:**
- Consumes: Task 2 capture configuration, writer, custody verifier, resolver, and retained iterator.
- Produces: opt-in compact capture inside `_run_prime_row()`, `RunMonitor.consume_prime_event()`, and protocol-aware paths for all seven approved consumers while preserving the historical branch.

- [ ] **Step 1: Add historical-byte-compatibility and protocol RED tests**

Assert existing protocols validate with no capture field, resolve to `operator/prime.jsonl`, retain current Popen text settings and unbounded historical queue behavior, and produce no new process-result keys. Add compact protocol tests for the exact config, missing paths, limit overrides, and environment attempts to alter limits.

```python
@pytest.fixture
def runner():
    return _runner()

def runner_capture_config() -> dict[str, Any]:
    return {
        "schema": "rook.prime_event_capture_config:v1",
        "mode": "compact",
        "retainedPath": "operator/prime-events.compact.jsonl",
        "custodyPath": "operator/prime-event-capture-custody.json",
        "rawDebugPath": None,
    }

def test_historical_protocol_keeps_raw_runtime_path(runner, tmp_path):
    protocol = runner.validate_protocol(_protocol())
    assert runner.resolve_prime_event_path(protocol, tmp_path) == tmp_path / "operator" / "prime.jsonl"

def test_compact_protocol_admits_only_versioned_capture_config(runner):
    protocol = _protocol() | {"primeEventCapture": runner_capture_config()}
    admitted = runner.validate_protocol(protocol)
    assert admitted["primeEventCapture"]["mode"] == "compact"
```

- [ ] **Step 2: Add monitor and compact-thread RED tests**

Refactor tests so `RunMonitor.consume_prime_line()` and the new `consume_prime_event()` return identical token totals and ceiling decisions. With a fake binary Prime process, prove the compact branch uses `queue.Queue(maxsize=1)`, publishes parsed events after retained writes, signals EOF only after complete custody, and returns `captureStatus: pass`. Inject capture failure and prove the process tree is terminated, evidence remains incomplete, and no complete custody is claimed.

- [ ] **Step 3: Add direct function-level parity RED tests for all current consumers**

Create equivalent raw and compact row roots from one small fixture with this
test-owned helper. It uses the production compact writer rather than a second
parser:

```python
def equivalent_prime_streams(runner, tmp_path: Path, rows: list[dict[str, Any]]):
    raw_root = tmp_path / "raw"
    compact_root = tmp_path / "compact"
    raw_operator = raw_root / "operator"
    compact_operator = compact_root / "operator"
    raw_operator.mkdir(parents=True)
    compact_operator.mkdir(parents=True)
    source = b"".join(
        json.dumps(row, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        + b"\n"
        for row in rows
    )
    (raw_operator / "prime.jsonl").write_bytes(source)
    raw_protocol = runner.validate_protocol(_protocol())
    compact_protocol = runner.validate_protocol(
        _protocol() | {"primeEventCapture": runner_capture_config()}
    )
    runner.capture_binary_stream(
        io.BytesIO(source),
        config=runner.validate_capture_config(compact_protocol["primeEventCapture"]),
        row_root=compact_root,
        publish=lambda event: None,
    )
    return raw_protocol, raw_root, compact_protocol, compact_root

def test_goal_context_entry_point_has_raw_compact_parity(runner, tmp_path):
    objective = "build a row"
    budget = 2_000_000
    rows = [
        {
            "type": "goal_update",
            "goal": {
                "objective": objective,
                "status": "active",
                "tokenBudget": budget,
            },
        }
    ]
    raw_protocol, raw_root, compact_protocol, compact_root = equivalent_prime_streams(
        runner, tmp_path, rows
    )
    assert runner.prime_log_proves_goal_context(
        runner.resolve_prime_event_path(raw_protocol, raw_root), objective, budget
    )
    assert runner.prime_log_proves_goal_context(
        runner.resolve_prime_event_path(compact_protocol, compact_root), objective, budget
    )

def test_run_monitor_has_raw_compact_parity(runner):
    limits = runner.CampaignLimits(
        wall_clock_seconds=1_800,
        gateway_events=150,
        provider_tokens=2_000_000,
        prime_goal_tokens=1_900_000,
    )
    line_monitor = runner.RunMonitor(limits)
    event_monitor = runner.RunMonitor(limits)
    event = {
        "type": "message_end",
        "message": {"usage": {"totalTokens": 123}},
    }
    assert line_monitor.consume_prime_line(json.dumps(event)) == (
        event_monitor.consume_prime_event(event)
    )
    assert line_monitor.provider_tokens == event_monitor.provider_tokens == 123
```

Add five more direct tests, each invoking the named production function rather
than a substitute parser:

```text
test_write_varied_row_records_has_raw_compact_parity
  -> call _write_varied_row_records for fresh_empty sibling roots
  -> compare row-telemetry and shadow-judgment semantic fields
  -> permit only retained-stream path/hash differences

test_attachment_entry_point_has_raw_compact_parity
  -> extract the exact successful event list already used by the attachment test
  -> call audit_multimodal_attachment_sequence on both resolved paths
  -> require identical attachment ordering, call identity, hashes, and sizes

test_admit_retained_smoke_has_raw_compact_parity
  -> seal equivalent complete retained-smoke roots and call admit_retained_smoke
  -> compare budget, goal, process, semantic, and custody disposition

test_operator_normalize_has_raw_compact_parity
  -> invoke asyncio.run(_operator_normalize(namespace)) with current host fakes
  -> compare lifecycle, normalized source events, and terminal receipt

test_operator_evaluate_has_raw_compact_parity
  -> invoke asyncio.run(_operator_evaluate(namespace)) with the current MCP fake
  -> compare fenced snapshot, criteria, status, and reason
```

For `_write_varied_row_records`, create `operator/source.jsonl` and the resolved
Prime stream, use a task whose `targetFixture.baseline` is `fresh_empty`, patch
`_final_observation_snapshot` to the same solved dictionary for both calls, and
compare returned records plus JSON outputs after removing only the declared
retained path/hash fields. For the two operator functions, write the exact
frozen `protocol.json` into each campaign root and assert a missing or
byte-different protocol refuses before normalization or evaluation. Patch only
host/network executors with current test doubles.

The required inventory is exactly the two coded tests above plus the five named
tests in this step. Step 4 separately scans every production call site that can
select the retained Prime stream, so a new path consumer fails qualification
until it receives a direct raw/compact parity test.

- [ ] **Step 4: Add hard-coded path detection RED tests**

Inspect the runner AST or source tokens in a focused test and assert that compact-aware functions call the shared resolver. The historical literal may remain only in the resolver and historical capture branch. Cover `_write_varied_row_records`, `admit_retained_smoke`, multimodal attachment audit call sites, `_operator_normalize`, `_operator_evaluate`, and evidence-path records.

- [ ] **Step 5: Run runner tests to verify RED**

Run:

```powershell
& $python -m pytest `
  mcp_server/tests/test_prime_json_event_capture.py `
  mcp_server/tests/test_qwen38_self_termination_campaign_runner.py -q
```

Expected: new runner integration/parity tests fail while existing historical tests remain green.

- [ ] **Step 6: Implement the opt-in compact branch**

Import the same-directory capture module from an explicit resolved script path
and bind its six runner-used attributes in the runner module:
`validate_capture_config`, `capture_binary_stream`, `PrimeCaptureError`,
`resolve_prime_event_path`, `iter_retained_prime_events`, and
`verify_capture_custody`. Assert the imported module's resolved `__file__` is
the repository script path. Leave `_reader()` and the historical `text=True`,
replacement-decoding branch unchanged. For a compact config, launch with
binary pipes, use `queue.Queue(maxsize=1)` for stdout events and
`queue.Queue(maxsize=3)` for the three one-shot control signals, call
`capture_binary_stream()` on the stdout thread, write stderr bytes
independently, and pass parsed events to existing goal/model/budget logic.

```python
def _compact_stdout_reader(stream, config, row_root, events, controls):
    try:
        custody = capture_binary_stream(
            stream,
            config=config,
            row_root=row_root,
            publish=events.put,
        )
        controls.put(("stdout_eof", custody))
    except PrimeCaptureError as error:
        controls.put(("capture_error", error.code))
```

Keep the source-event gateway log, wall-clock monitor, process ownership, model checks, and termination behavior unchanged.

- [ ] **Step 7: Route every post-run consumer through the resolver**

Use `resolve_prime_event_path(protocol, row_root)` at the seven declared boundaries. For `_operator_normalize` and `_operator_evaluate`, load the exact frozen campaign protocol from `row_root.parent / "protocol.json"`; reject a missing or mismatched protocol rather than inferring a filename. Update evidence-path records to retain the actual resolved relative path.

- [ ] **Step 8: Make compact custody part of row custody without changing historical rows**

For compact protocols only, include this additional process-result projection and require it in `_row_outcome()`:

```json
{
  "primeEventCapture": {
    "custodyPath": "operator/prime-event-capture-custody.json",
    "retainedPath": "operator/prime-events.compact.jsonl",
    "status": "pass"
  }
}
```

Do not add this key to historical process results.

- [ ] **Step 9: Run Task 3 GREEN and historical suites**

Run:

```powershell
& $python -m pytest `
  mcp_server/tests/test_prime_json_event_capture.py `
  mcp_server/tests/test_qwen38_self_termination_campaign_runner.py `
  mcp_server/tests/test_gh_behavioral_acceptance.py `
  mcp_server/tests/test_gh_behavioral_acceptance_v2.py `
  mcp_server/tests/test_reconcile_prime_compaction_trace.py -q
& $python -m py_compile `
  scripts/prime_json_event_capture.py `
  scripts/qwen38_self_termination_campaign_runner.py
```

Expected: all listed tests pass, historical fixture bytes/hashes remain unchanged, and compilation exits `0`.

- [ ] **Step 10: Commit Task 3**

```powershell
git add scripts/qwen38_self_termination_campaign_runner.py mcp_server/tests/test_qwen38_self_termination_campaign_runner.py
git commit -m "feat: integrate compact Prime capture"
```

---

### Task 4: Offline Qualification Harness And Frozen Protocol

**Files:**
- Create: `scripts/qualify_prime_json_event_capture.py`
- Create: `mcp_server/tests/test_qualify_prime_json_event_capture.py`
- Create: `docs/superpowers/experiments/2026-08-20-prime-json-event-capture-offline-qualification-v1.json`

**Interfaces:**
- Consumes: Tasks 1-3, immutable Vessel manifests/source, existing evidence-manifest shape, and unchanged V2 owner.
- Produces: one closed offline qualification command that verifies sources before output creation and emits dual replay, reconstruction, consumer parity, V2 parity, determinism, size, and manifest artifacts.

- [ ] **Step 1: Add closed-protocol and pre-output-custody RED tests**

The protocol is a closed object with this exact nested ownership shape; every
`path` is absolute, every `sha256` is uppercase, and every nested object is
closed:

```text
root keys exactly:
  schema                     exact qualification schema string
  mode                       exact "offline_only"
  outputRoot                 absolute fresh durable directory
  captureConfig              exact rook.prime_event_capture_config:v1 object
  sourceEvidence             exact SourceEvidence object
  owners                     exact Owners object
  precontactVerification     exact PrecontactVerification object
  expected                   exact Expected object

EvidenceReference keys exactly:
  path                       absolute path string
  sha256                     uppercase 64-hex string

RuntimeReference keys exactly:
  path                       absolute path string
  sha256                     uppercase 64-hex string
  bytes                      positive JSON integer; booleans forbidden
  rows                       positive JSON integer; booleans forbidden

SourceEvidence keys exactly:
  root                       absolute source-root string
  rowRoot                    absolute row-root string beneath root
  globalManifest             EvidenceReference
  rowManifest                EvidenceReference
  runtimeLog                 RuntimeReference
  sourceLog                  EvidenceReference
  processResult              EvidenceReference

Owners keys exactly:
  captureModule              EvidenceReference
  campaignRunner             EvidenceReference
  v2                         EvidenceReference
  spec                       EvidenceReference

PrecontactVerification keys exactly:
  pythonPath                 absolute executable path
  arguments                  nonempty ordered array of nonempty strings

Expected keys exactly:
  sourceRows                 positive JSON integer
  sourceBytes                positive JSON integer
  sourceSha256               uppercase 64-hex string
  compactedMessageUpdates    nonnegative JSON integer
  rawFallbackMessageUpdates  nonnegative JSON integer
  maxRetainedRatio           finite JSON number in (0, 1]
  liveContact                exact false
```

Step 7 freezes the exact observed owner hashes and the exact focused pytest
arguments; the test fixture below derives equivalent exact references from
disposable files.

Require `schema == rook.experiment.prime_json_event_capture_offline_qualification:v1`, `mode == offline_only`, an absolute fresh output root outside the source root, exact references with uppercase SHA-256, exact module/runner/V2/spec paths and hashes, and the approved capture config. Test missing/tampered global manifest, row manifest, runtime, source log, process result, owner, runner, and spec; each must refuse before creating output.

```python
QUALIFICATION_PATH = ROOT / "scripts" / "qualify_prime_json_event_capture.py"

@pytest.fixture
def qualification():
    spec = importlib.util.spec_from_file_location(
        "qualify_prime_json_event_capture_for_tests", QUALIFICATION_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module

def load_protocol(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert type(value) is dict
    return value

def write_fixture_protocol(tmp_path: Path, value: dict[str, Any]) -> Path:
    path = tmp_path / "protocol.json"
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path

def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()

def qualification_capture_config() -> dict[str, Any]:
    return {
        "schema": "rook.prime_event_capture_config:v1",
        "mode": "compact",
        "retainedPath": "operator/prime-events.compact.jsonl",
        "custodyPath": "operator/prime-event-capture-custody.json",
        "rawDebugPath": None,
    }

def write_manifest(root: Path, path: Path) -> None:
    entries = {}
    for item in sorted(candidate for candidate in root.rglob("*") if candidate.is_file()):
        if item == path:
            continue
        entries[item.relative_to(root).as_posix()] = {
            "bytes": item.stat().st_size,
            "sha256": sha256(item),
        }
    path.write_text(
        json.dumps(
            {
                "schema": "rook.evidence_manifest:v1",
                "root": root.as_posix(),
                "entryCount": len(entries),
                "entries": entries,
            },
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

@pytest.fixture
def protocol_path(tmp_path: Path) -> Path:
    source_root = tmp_path / "source"
    row_root = source_root / "MV1"
    operator = row_root / "operator"
    owners = tmp_path / "owners"
    operator.mkdir(parents=True)
    owners.mkdir()
    runtime = operator / "prime.jsonl"
    source_log = operator / "source.jsonl"
    process = operator / "process-result.json"
    runtime.write_bytes(b'{"type":"agent_start"}\n')
    source_log.write_bytes(b'{"sequence":1,"target":"gh_snapshot"}\n')
    process.write_bytes(b'{"exitCode":0,"stdoutEof":true}\n')
    owner_paths = {}
    for name in ("captureModule", "campaignRunner", "v2", "spec"):
        owner = owners / f"{name}.txt"
        owner.write_text(name + "\n", encoding="utf-8")
        owner_paths[name] = {"path": owner.as_posix(), "sha256": sha256(owner)}
    row_manifest = row_root / "evidence-manifest.json"
    write_manifest(row_root, row_manifest)
    global_manifest = source_root / "evidence-manifest.json"
    write_manifest(source_root, global_manifest)
    protocol = {
        "schema": "rook.experiment.prime_json_event_capture_offline_qualification:v1",
        "mode": "offline_only",
        "outputRoot": (tmp_path / "output").as_posix(),
        "captureConfig": qualification_capture_config(),
        "sourceEvidence": {
            "root": source_root.as_posix(),
            "rowRoot": row_root.as_posix(),
            "globalManifest": {"path": global_manifest.as_posix(), "sha256": sha256(global_manifest)},
            "rowManifest": {"path": row_manifest.as_posix(), "sha256": sha256(row_manifest)},
            "runtimeLog": {"path": runtime.as_posix(), "sha256": sha256(runtime), "bytes": runtime.stat().st_size, "rows": 1},
            "sourceLog": {"path": source_log.as_posix(), "sha256": sha256(source_log)},
            "processResult": {"path": process.as_posix(), "sha256": sha256(process)},
        },
        "owners": owner_paths,
        "precontactVerification": {
            "pythonPath": sys.executable,
            "arguments": ["-m", "pytest", "mcp_server/tests/test_prime_json_event_capture.py", "-q"],
        },
        "expected": {
            "sourceRows": 1,
            "sourceBytes": runtime.stat().st_size,
            "sourceSha256": sha256(runtime),
            "compactedMessageUpdates": 0,
            "rawFallbackMessageUpdates": 0,
            "maxRetainedRatio": 0.05,
            "liveContact": False,
        },
    }
    return write_fixture_protocol(tmp_path, protocol)

def test_source_mismatch_refuses_before_output(qualification, protocol_path, tmp_path):
    protocol = load_protocol(protocol_path)
    protocol["sourceEvidence"]["runtimeLog"]["sha256"] = "0" * 64
    changed = write_fixture_protocol(tmp_path, protocol)
    with pytest.raises(ValueError, match="source_evidence_mismatch"):
        qualification.run_qualification(changed)
    assert not Path(protocol["outputRoot"]).exists()
```

- [ ] **Step 2: Add small-fixture dual-replay and no-contact RED tests**

Use a compact fixture containing all nine subtypes, lifecycle, tool result/error, image content, compaction, goal, IPython checkpoint, and terminal rows. Assert two replays produce byte-identical compact streams and custody; no source file is copied; no subprocess except the frozen pytest precontact command is allowed; and network/model/Rook imports are absent.

- [ ] **Step 3: Add unchanged-V2 and semantic-parity RED tests**

Copy only the small source log into `raw-v2` and `compact-v2` qualification directories. Call the unchanged `gh_behavioral_acceptance_v2.seal_and_normalize_prime_source_log()` once with the raw runtime and once with the compact runtime. Assert equal normalized events, receipt, final fenced observation, lifecycle class, and shadow status/reason; closures may differ only in `runtime_log_sha256`.

Assert exact parity for tool execution/result/error history and terminal/checkpoint messages. Assert `reconstruct_terminal_assistant_messages()` equals raw exact `message_end.message` values.

- [ ] **Step 4: Run qualification tests to verify RED**

Run:

```powershell
& $python -m pytest mcp_server/tests/test_qualify_prime_json_event_capture.py -q
```

Expected: import/behavior failures because the qualification harness is absent.

- [ ] **Step 5: Implement the offline-only harness**

Follow the existing `scripts/reconcile_prime_compaction_trace.py` evidence patterns without importing or modifying that frozen runner. Stream hashes in 1 MiB chunks; verify both historical manifests and all exact references before `outputRoot.mkdir()`; run the frozen precontact test command; perform two capture replays with no-op publishers; compare byte equality; run reconstruction and V2 parity; write canonical JSON records; seal and independently verify the output manifest.

```python
def run_qualification(protocol_path: Path) -> dict[str, Any]:
    protocol = validate_qualification_protocol(_load_json(protocol_path))
    source_custody = verify_source_evidence(protocol)
    output_root = Path(protocol["outputRoot"])
    if output_root.exists():
        raise ValueError("output_root_exists")
    output_root.mkdir(parents=True)
    _retain_protocol_and_source_custody(protocol_path, source_custody, output_root)
    _run_precontact_verification(protocol, output_root)
    replay_a = _run_replay(protocol, output_root / "replay-a")
    replay_b = _run_replay(protocol, output_root / "replay-b")
    result = _adjudicate(protocol, replay_a, replay_b, output_root)
    _seal_and_verify(output_root)
    return result
```

No exception path deletes or rewrites the output prefix. A corrected rerun uses a fresh versioned sibling.

- [ ] **Step 6: Run Task 4 GREEN tests**

Run:

```powershell
& $python -m pytest `
  mcp_server/tests/test_prime_json_event_capture.py `
  mcp_server/tests/test_qwen38_self_termination_campaign_runner.py `
  mcp_server/tests/test_qualify_prime_json_event_capture.py `
  mcp_server/tests/test_gh_behavioral_acceptance_v2.py `
  mcp_server/tests/test_reconcile_prime_compaction_trace.py -q
& $python -m py_compile `
  scripts/prime_json_event_capture.py `
  scripts/qwen38_self_termination_campaign_runner.py `
  scripts/qualify_prime_json_event_capture.py
```

Expected: all tests and compilation pass without contacting external systems.

- [ ] **Step 7: Freeze exact implementation and protocol hashes**

Run `Get-FileHash -Algorithm SHA256` over the capture module, campaign runner, qualification runner, V2 owner, approved spec, both source manifests, runtime log, source log, and process result. Use `apply_patch` to create the protocol with those exact observed hashes, the exact source bytes/rows, capture config, output root `C:/UDEV/RookEvidence/2026-08-20-prime-json-event-capture-offline-qualification-v1`, and these expected assertions:

```json
{
  "compactedMessageUpdates": 74143,
  "liveContact": false,
  "maxRetainedRatio": 0.05,
  "rawFallbackMessageUpdates": 0,
  "sourceBytes": 3543087572,
  "sourceRows": 74473,
  "sourceSha256": "F79FF8A329993C9770B7E103B3F10620A6E118C5AD58E6184E9777EDFBFCAA3B"
}
```

The precontact verification command is the exact Task 4 GREEN pytest invocation using `C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe`.

- [ ] **Step 8: Add frozen-protocol tests and verify the output root is absent**

Test exact protocol keys, paths, hashes, commands, constants, output root, no-contact declaration, and source evidence. Assert the output root does not exist. Run the focused suite again after freezing.

- [ ] **Step 9: Commit Task 4 before the 3.54 GB replay**

```powershell
git add `
  scripts/qualify_prime_json_event_capture.py `
  mcp_server/tests/test_qualify_prime_json_event_capture.py `
  docs/superpowers/experiments/2026-08-20-prime-json-event-capture-offline-qualification-v1.json
git commit -m "test: freeze Prime capture qualification"
```

---

### Task 5: Sealed Vessel Replay And Offline Qualification Report

**Files:**
- Create: `docs/superpowers/reports/2026-08-20-prime-json-event-capture-offline-qualification.md`
- Verify only: every implementation, test, protocol, source, and evidence file named above.

**Interfaces:**
- Consumes: the committed Task 4 protocol and immutable 3.54 GB source.
- Produces: sealed qualification evidence and the report submitted for independent implementation review.

- [ ] **Step 1: Perform the pre-execution custody gate**

Run:

```powershell
$repo = "C:/UDEV/Rook/.worktrees/coordinating-intelligence-evidence-ledger"
$python = "C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe"
$protocol = "$repo/docs/superpowers/experiments/2026-08-20-prime-json-event-capture-offline-qualification-v1.json"
$evidence = "C:/UDEV/RookEvidence/2026-08-20-prime-json-event-capture-offline-qualification-v1"

git -C $repo status --porcelain --untracked-files=all
git -C $repo diff --check
Test-Path -LiteralPath $evidence
& $python -m pytest `
  "$repo/mcp_server/tests/test_prime_json_event_capture.py" `
  "$repo/mcp_server/tests/test_qwen38_self_termination_campaign_runner.py" `
  "$repo/mcp_server/tests/test_qualify_prime_json_event_capture.py" `
  "$repo/mcp_server/tests/test_gh_behavioral_acceptance.py" `
  "$repo/mcp_server/tests/test_gh_behavioral_acceptance_v2.py" `
  "$repo/mcp_server/tests/test_reconcile_prime_compaction_trace.py" -q
```

Expected: clean worktree, clean whitespace, evidence root `False`, and all tests pass. Stop without replay if any check differs.

- [ ] **Step 2: Execute the offline qualification exactly once**

Run:

```powershell
$env:PYTHONPATH = "$repo/mcp_server/src;$repo/scripts"
& $python "$repo/scripts/qualify_prime_json_event_capture.py" --protocol $protocol
```

This command may read the sealed source and create only the new qualification root. It may not contact or launch Prime, Qwen, Ollama, Rook MCP, Rhino, or Grasshopper.

- [ ] **Step 3: Verify the quantitative and semantic result before reporting**

Read the retained result and independently verify:

```text
source rows                         74,473
source bytes                 3,543,087,572
source SHA-256               F79FF8A329993C9770B7E103B3F10620A6E118C5AD58E6184E9777EDFBFCAA3B
compacted updates                   74,143
raw fallback updates                     0
retained ratio                      <= 0.05
replay A/B compact bytes           identical
replay A/B custody bytes           identical
terminal reconstruction            identical
tool/result/error history          identical
lifecycle/compaction class         identical
normalized V2 events               identical
latest terminal receipt            identical
final fenced observation           identical
shadow status/reason               identical
source manifests                   unchanged
live contact                       false
```

If any assertion fails, preserve the evidence root, classify the qualification honestly as failed or incomplete, do not edit evidence, and return to the smallest implicated implementation task using a new qualification version.

- [ ] **Step 4: Write the evidence-led report**

The report must state exact source and retained sizes, reduction percentage, row/fallback counts, all relevant hashes, reconstruction scope, irrecoverable raw update-byte limitations, V2 closure-hash difference, test command/count, execution duration, memory/resource observations, manifest count/hash, source manifest reverification, zero contact, commit lineage, and clean/dirty state. It must explicitly say that the raw source hash proves capture-owner observation, not independent possession of discarded source bytes.

- [ ] **Step 5: Run final offline verification**

Run the full Step 1 suite again, compile all three scripts, verify the new evidence manifest with a fresh process, rehash both historical manifests and the V2 owner, run `git diff --check`, and confirm both Rook and Prime evaluation worktrees are clean except for the uncommitted report.

- [ ] **Step 6: Commit the report and run post-commit verification**

```powershell
git add docs/superpowers/reports/2026-08-20-prime-json-event-capture-offline-qualification.md
git commit -m "docs: qualify compact Prime event capture"
git show --check --stat HEAD
git status --porcelain --untracked-files=all
```

- [ ] **Step 7: Stop for independent implementation review**

Return the implementation commits, exact changed-file scope, commands, test counts, source/retained bytes and ratio, capture/custody/protocol/report/evidence hashes, V2 parity, limitations, zero-contact proof, and worktree state. Do not run a live smoke and do not call `goal.complete()` until independent review either accepts the offline correction as sufficient or explicitly authorizes the one small non-Rhino smoke permitted by the design.

---

## Plan Self-Review Checklist

- [x] Every approved design section maps to a task: ownership and schema in Task 1; bounded ingress, custody, crash behavior, reconstruction, and determinism in Task 2; runner and seven consumer handoffs in Task 3; immutable-source and V2 parity qualification in Task 4; sealed replay and reporting in Task 5.
- [x] Historical V1/V2 modules, reconciliation runner, Prime, model guidance, Rook mutation, Rhino, Grasshopper, and Vessel evidence have no write task.
- [x] Every production edit has a named RED command before GREEN implementation.
- [x] Public signatures and field names are consistent across all tasks.
- [x] The source evidence is verified before output creation and never copied in full.
- [x] Qualification proves the 95% size target and all named semantic/custody parity requirements.
- [x] No task authorizes model or live-system contact.
- [x] No unresolved markers or deferred implementation language remain.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-08-20-prime-json-event-stream-storage-efficiency.md`. Two execution options:

1. **Subagent-Driven (recommended)** - dispatch a fresh subagent per task with review between tasks.
2. **Inline Execution** - execute in this session using `superpowers:executing-plans`, with the task commits and offline qualification gates above.

No execution option authorizes live contact. Both stop after offline qualification for independent implementation review.
