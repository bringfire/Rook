"""No-contact tests for the private ChatRunner qualification operator."""

from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from rook.agent.chat.chat_runner import ChatEvent, ChatRunner
from rook.agent.chat.conversation_store import Conversation
from rook.agent.tool_registry import ToolRegistry
from rook.targeting import get_active_target


_SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "chatrunner_headless_qualification.py"
)
_SPEC = importlib.util.spec_from_file_location(
    "chatrunner_headless_qualification_for_tests",
    _SCRIPT_PATH,
)
assert _SPEC is not None and _SPEC.loader is not None
OPERATOR = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = OPERATOR
_SPEC.loader.exec_module(OPERATOR)

_STAMP = "2026-08-04T22:00:00.000000Z"


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
        self.write_calls = self.flush_calls = self.close_calls = 0
        self.fail_write_at = fail_write_at
        self.short_write_at = short_write_at
        self.fail_flush_at = fail_flush_at
        self.fail_close = fail_close

    def write(self, row: bytes) -> int:
        self.write_calls += 1
        if self.write_calls == self.fail_write_at:
            raise OSError("WRITE_SENTINEL")
        if self.write_calls == self.short_write_at:
            count = max(0, len(row) - 1)
            self.content.extend(row[:count])
            return count
        self.content.extend(row)
        return len(row)

    def flush(self) -> None:
        self.flush_calls += 1
        if self.flush_calls == self.fail_flush_at:
            raise OSError("FLUSH_SENTINEL")

    def close(self) -> None:
        self.close_calls += 1
        if self.fail_close:
            raise OSError("CLOSE_SENTINEL")


class _TimelineStream(_TraceStream):
    def __init__(self, timeline, **kwargs):
        super().__init__(**kwargs)
        self.timeline = timeline

    def flush(self):
        super().flush()
        row = json.loads(bytes(self.content).splitlines()[-1])
        suffix = ""
        if row["kind"] == "chat_event":
            suffix = f":{row['payload']['type']}"
        self.timeline.append(f"flush:{row['kind']}{suffix}")


class _CausalRunner:
    def __init__(self, events, timeline):
        self.events = events
        self.timeline = timeline
        self.call = None

    async def run_turn(self, conversation, intent, system_prompt):
        self.call = (conversation, intent, system_prompt)
        for event in self.events:
            self.timeline.append(f"yield:{event.type}")
            yield event
            self.timeline.append(f"resume:{event.type}")


class _ExceptionRunner:
    def __init__(self, exception):
        self.exception = exception

    async def run_turn(self, conversation, intent, system_prompt):
        if False:
            yield None
        raise self.exception


def _valid_row(tmp_path: Path) -> tuple[Path, Path, bytes]:
    skill = tmp_path / "SKILL.md"
    skill_bytes = "# Exact skill\nPreserve π.\n".encode("utf-8")
    skill.write_bytes(skill_bytes)
    row = tmp_path / "row.json"
    row.write_text(
        json.dumps(
            {
                "model": "  local/model  ",
                "api_base": "http://127.0.0.1:11434",
                "intent": "  preserve edge whitespace  ",
                "skill_path": str(skill),
                "rhino_target": {
                    "port": 19800,
                    "process_id": 1234,
                    "document_serial_number": 77,
                },
            },
            ensure_ascii=True,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    return row, skill, skill_bytes


def _expected_row_bytes(sequence: int, kind: str, payload: dict) -> bytes:
    return (
        json.dumps(
            {
                "sequence": sequence,
                "recorded_at_utc": _STAMP,
                "kind": kind,
                "payload": payload,
            },
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _payload_for_exact_size(sequence: int, size: int) -> dict:
    empty = _expected_row_bytes(sequence, "chat_event", {"data": ""})
    assert len(empty) <= size
    payload = {"data": "x" * (size - len(empty))}
    assert len(_expected_row_bytes(sequence, "chat_event", payload)) == size
    return payload


def _recorder(stream=None, *, wall_clock=None):
    return OPERATOR._JsonlRecorder(
        path=Path("trace.jsonl"),
        stream=stream or _TraceStream(),
        wall_clock=wall_clock or (lambda: _STAMP),
    )


def _admitted_row(tmp_path):
    row_path, _, _ = _valid_row(tmp_path)
    return OPERATOR._load_row(row_path)


def _trace_rows(stream):
    return [json.loads(line) for line in bytes(stream.content).splitlines()]


def _gateway_stream():
    async def _gen():
        chunk = MagicMock()
        chunk.choices = [MagicMock()]
        chunk.choices[0].delta.content = None
        tool = MagicMock()
        tool.index = 0
        tool.id = "gateway_call"
        tool.function.name = "rook_tools_call"
        tool.function.arguments = json.dumps(
            {"name": "gh_library", "arguments": {"search": "Series"}}
        )
        chunk.choices[0].delta.tool_calls = [tool]
        chunk.usage = None
        yield chunk

    return _gen()


def _text_stream():
    async def _gen():
        chunk = MagicMock()
        chunk.choices = [MagicMock()]
        chunk.choices[0].delta.content = "Complete"
        chunk.choices[0].delta.tool_calls = None
        chunk.usage = None
        yield chunk

    return _gen()


def test_row_loader_retains_exact_values_and_hashes(tmp_path):
    row_path, skill_path, skill_bytes = _valid_row(tmp_path)

    admitted = OPERATOR._load_row(row_path)

    assert admitted.source_path == row_path.resolve()
    assert admitted.source_sha256 == hashlib.sha256(row_path.read_bytes()).hexdigest()
    assert admitted.model == "  local/model  "
    assert admitted.api_base == "http://127.0.0.1:11434"
    assert admitted.intent == "  preserve edge whitespace  "
    assert admitted.skill_path == skill_path.resolve()
    assert admitted.skill_sha256 == hashlib.sha256(skill_bytes).hexdigest()
    assert admitted.skill_text == skill_bytes.decode("utf-8")
    assert admitted.target == OPERATOR._RhinoTarget(19800, 1234, 77)


def test_row_loader_rejects_duplicate_keys(tmp_path):
    path = tmp_path / "row.json"
    path.write_text(
        '{"model":"first","model":"second"}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate_json_key"):
        OPERATOR._load_row(path)


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        (lambda row: row.pop("model"), "invalid_row_keys"),
        (lambda row: row.update(extra=True), "invalid_row_keys"),
        (lambda row: row.update(model=1), "invalid_model"),
        (lambda row: row.update(model=" \t"), "invalid_model"),
        (lambda row: row.update(intent=False), "invalid_intent"),
        (lambda row: row.update(intent="\n"), "invalid_intent"),
        (lambda row: row.update(api_base=123), "invalid_api_base"),
        (lambda row: row.update(skill_path=[]), "invalid_skill_path"),
        (lambda row: row.update(rhino_target=[]), "invalid_rhino_target"),
        (
            lambda row: row["rhino_target"].update(extra=1),
            "invalid_rhino_target_keys",
        ),
    ],
)
def test_row_loader_rejects_non_exact_shapes(tmp_path, mutation, reason):
    row_path, _, _ = _valid_row(tmp_path)
    document = json.loads(row_path.read_text(encoding="utf-8"))
    mutation(document)
    row_path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match=reason):
        OPERATOR._load_row(row_path)


@pytest.mark.parametrize(
    ("field", "reason"),
    [("model", "invalid_model"), ("intent", "invalid_intent")],
)
def test_row_loader_rejects_escaped_lone_surrogates(tmp_path, field, reason):
    row_path, _, _ = _valid_row(tmp_path)
    document = json.loads(row_path.read_text(encoding="utf-8"))
    document[field] = "\ud800"
    row_path.write_text(
        json.dumps(document, ensure_ascii=True),
        encoding="ascii",
    )

    with pytest.raises(ValueError, match=reason):
        OPERATOR._load_row(row_path)


@pytest.mark.parametrize("value", [True, False, 0, -1, 1.0, "1"])
@pytest.mark.parametrize("field", ["port", "process_id", "document_serial_number"])
def test_row_loader_requires_exact_positive_target_integers(tmp_path, field, value):
    row_path, _, _ = _valid_row(tmp_path)
    document = json.loads(row_path.read_text(encoding="utf-8"))
    document["rhino_target"][field] = value
    row_path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match=f"invalid_{field}"):
        OPERATOR._load_row(row_path)


@pytest.mark.parametrize(
    "api_base",
    [
        "https://example.com:11434",
        "ftp://127.0.0.1:11434",
        "http://user:pass@127.0.0.1:11434",
        "http://127.0.0.1:11434/path?secret=yes",
        "http://127.0.0.1:11434/path#fragment",
        "http://127.0.0.2:11434",
        "http://",
    ],
)
def test_row_loader_rejects_non_loopback_or_credentialed_api_base(tmp_path, api_base):
    row_path, _, _ = _valid_row(tmp_path)
    document = json.loads(row_path.read_text(encoding="utf-8"))
    document["api_base"] = api_base
    row_path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="invalid_api_base"):
        OPERATOR._load_row(row_path)


@pytest.mark.parametrize("api_base", ["http://localhost:11434", "https://[::1]:11434"])
def test_row_loader_accepts_explicit_loopback_api_base(tmp_path, api_base):
    row_path, _, _ = _valid_row(tmp_path)
    document = json.loads(row_path.read_text(encoding="utf-8"))
    document["api_base"] = api_base
    row_path.write_text(json.dumps(document), encoding="utf-8")

    assert OPERATOR._load_row(row_path).api_base == api_base


def test_row_loader_rejects_missing_directory_and_invalid_utf8_skills(tmp_path):
    row_path, skill_path, _ = _valid_row(tmp_path)
    document = json.loads(row_path.read_text(encoding="utf-8"))

    document["skill_path"] = str(tmp_path / "missing.md")
    row_path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="invalid_skill_file"):
        OPERATOR._load_row(row_path)

    document["skill_path"] = str(tmp_path)
    row_path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="invalid_skill_file"):
        OPERATOR._load_row(row_path)

    skill_path.write_bytes(b"\xff")
    document["skill_path"] = str(skill_path)
    row_path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="invalid_skill_utf8"):
        OPERATOR._load_row(row_path)


def test_row_loader_rejects_invalid_row_utf8(tmp_path):
    row_path = tmp_path / "row.json"
    row_path.write_bytes(b"\xff")

    with pytest.raises(ValueError, match="invalid_row_utf8"):
        OPERATOR._load_row(row_path)


def test_row_loader_ignores_environment_overrides(tmp_path, monkeypatch):
    row_path, _, _ = _valid_row(tmp_path)
    monkeypatch.setenv("ROOK_MODEL", "environment/model")
    monkeypatch.setenv("ROOK_API_BASE", "http://localhost:9999")
    monkeypatch.setenv("ROOK_RHINO_PORT", "9999")

    admitted = OPERATOR._load_row(row_path)

    assert admitted.model == "  local/model  "
    assert admitted.api_base == "http://127.0.0.1:11434"
    assert admitted.target.port == 19800


def test_chat_event_payload_is_flat_and_exact():
    stream = _TraceStream()
    recorder = _recorder(stream)
    event = {"type": "tool_start", "name": "gh_edit", "params": {"epoch": 7}}

    recorder.record("chat_event", event)

    row = json.loads(bytes(stream.content))
    assert row == {
        "sequence": 1,
        "recorded_at_utc": _STAMP,
        "kind": "chat_event",
        "payload": event,
    }
    assert bytes(stream.content) == _expected_row_bytes(1, "chat_event", event)
    assert stream.flush_calls == 1


def test_recorder_rejects_unknown_kind_without_writing():
    stream = _TraceStream()
    recorder = _recorder(stream)

    with pytest.raises(ValueError, match="invalid_trace_kind"):
        recorder.record("invented", {})

    assert stream.write_calls == stream.flush_calls == 0
    assert recorder.failed is False


def test_recorder_accepts_exact_row_limit_and_rejects_one_byte_over():
    exact_stream = _TraceStream()
    exact = _recorder(exact_stream)
    exact.record("chat_event", _payload_for_exact_size(1, OPERATOR._ROW_MAX_BYTES))
    assert exact.bytes_written == OPERATOR._ROW_MAX_BYTES

    over_stream = _TraceStream()
    over = _recorder(over_stream)
    with pytest.raises(OPERATOR._TraceWriteFailure) as raised:
        over.record(
            "chat_event",
            _payload_for_exact_size(1, OPERATOR._ROW_MAX_BYTES + 1),
        )
    assert raised.value.reason == "row_size_exceeded"
    assert over.failed is True
    assert over_stream.write_calls == over_stream.flush_calls == 0


def test_recorder_counts_actual_bytes_and_rejects_total_overflow():
    stream = _TraceStream()
    recorder = _recorder(stream)
    rows = OPERATOR._TRACE_MAX_BYTES // OPERATOR._ROW_MAX_BYTES
    for sequence in range(1, rows + 1):
        recorder.record(
            "chat_event",
            _payload_for_exact_size(sequence, OPERATOR._ROW_MAX_BYTES),
        )
    assert recorder.bytes_written == OPERATOR._TRACE_MAX_BYTES

    with pytest.raises(OPERATOR._TraceWriteFailure) as raised:
        recorder.record("chat_event", {})
    assert raised.value.reason == "total_size_exceeded"
    assert stream.write_calls == rows
    assert stream.flush_calls == rows


def test_recorder_rejects_non_json_values_without_writing():
    stream = _TraceStream()
    recorder = _recorder(stream)

    with pytest.raises(OPERATOR._TraceWriteFailure) as raised:
        recorder.record("chat_event", {"value": float("nan")})

    assert raised.value.reason == "json_serialization_failed"
    assert recorder.failed is True
    assert stream.write_calls == stream.flush_calls == 0


@pytest.mark.parametrize(
    ("stream", "reason", "expected_bytes", "expected_flushes"),
    [
        (_TraceStream(fail_write_at=1), "write_failed", 0, 0),
        (_TraceStream(short_write_at=1), "short_write", None, 0),
        (_TraceStream(fail_flush_at=1), "flush_failed", None, 1),
    ],
)
def test_recorder_write_faults_stop_without_retry(
    stream, reason, expected_bytes, expected_flushes
):
    recorder = _recorder(stream)

    with pytest.raises(OPERATOR._TraceWriteFailure) as raised:
        recorder.record("chat_event", {"value": 1})

    assert raised.value.reason == reason
    assert recorder.failed is True
    assert recorder.sequence == 0
    if expected_bytes is not None:
        assert recorder.bytes_written == expected_bytes
    else:
        assert recorder.bytes_written == len(stream.content)
    assert stream.write_calls == 1
    assert stream.flush_calls == expected_flushes

    with pytest.raises(OPERATOR._TraceWriteFailure, match="trace_write_failed"):
        recorder.record("chat_event", {"value": 2})
    assert stream.write_calls == 1
    assert stream.flush_calls == expected_flushes


def test_recorder_advances_sequence_only_after_write_and_flush():
    stamps = iter(
        [
            "2026-08-04T22:00:01.000000Z",
            "2026-08-04T22:00:00.000000Z",
        ]
    )
    stream = _TraceStream()
    recorder = _recorder(stream, wall_clock=lambda: next(stamps))

    recorder.record("run_started", {"run": 1})
    recorder.record("chat_event", {"type": "done"})

    rows = [json.loads(line) for line in bytes(stream.content).splitlines()]
    assert [row["sequence"] for row in rows] == [1, 2]
    assert [row["recorded_at_utc"] for row in rows] == [
        "2026-08-04T22:00:01.000000Z",
        "2026-08-04T22:00:00.000000Z",
    ]
    assert recorder.sequence == 2


@pytest.mark.parametrize("fail_close", [False, True])
def test_recorder_close_is_attempted_once(fail_close):
    stream = _TraceStream(fail_close=fail_close)
    recorder = _recorder(stream)

    if fail_close:
        with pytest.raises(OPERATOR._TraceWriteFailure) as raised:
            recorder.close()
        assert raised.value.reason == "close_failed"
        assert recorder.failed is True
    else:
        recorder.close()
        assert recorder.closed is True

    recorder.close()
    assert stream.close_calls == 1


def test_open_recorder_uses_local_app_data_and_exclusive_binary_file(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(OPERATOR, "_utc_now_string", lambda: _STAMP)

    recorder = OPERATOR._open_recorder()
    try:
        assert recorder.path.parent == (tmp_path / "Rook" / "traces").resolve()
        assert recorder.path.exists()
        recorder.record("run_started", {"ok": True})
    finally:
        recorder.close()

    assert recorder.path.read_bytes() == _expected_row_bytes(
        1,
        "run_started",
        {"ok": True},
    )


def test_open_recorder_refuses_without_local_app_data(monkeypatch):
    monkeypatch.delenv("LOCALAPPDATA", raising=False)

    with pytest.raises(OPERATOR._TraceWriteFailure) as raised:
        OPERATOR._open_recorder()

    assert raised.value.reason == "localappdata_missing"
    assert raised.value.path is None


@pytest.mark.asyncio
async def test_event_stream_flushes_before_resume_and_finishes_with_snapshot(tmp_path):
    timeline = []
    stream = _TimelineStream(timeline)
    recorder = _recorder(stream)
    recorder.record("run_started", {"identity": "exact"})
    events = [
        ChatEvent(
            "tool_start",
            name="gh_edit",
            params={"epoch": 7},
            tool_call_id="c1",
        ),
        ChatEvent(
            "tool_result",
            name="gh_edit",
            result='{"success":true}',
            tool_call_id="c1",
        ),
        ChatEvent("text_delta", content="Complete"),
        ChatEvent(
            "done",
            usage={"input_tokens": 10, "output_tokens": 3, "wall_time_s": 1.2},
        ),
    ]
    runner = _CausalRunner(events, timeline)
    conversation = Conversation(
        id="qualification",
        persona="architect",
        model="local/model",
        api_base="http://127.0.0.1:11434",
    )

    async def canonical(name, arguments):
        timeline.append("snapshot:call")
        assert name == "rook_tools_call"
        assert arguments == {
            "name": "gh_snapshot",
            "arguments": {"include_data": False, "max_preview_items": 0},
        }
        return {"success": True, "data": {"epoch": 7, "components": []}}

    elapsed = iter([10.0, 12.5])
    status = await OPERATOR._consume_events(
        recorder=recorder,
        runner=runner,
        conversation=conversation,
        intent="Exact intent",
        system_prompt="Exact prompt",
        canonical_executor=canonical,
        target_matches=lambda: True,
        monotonic=lambda: next(elapsed),
    )

    assert status == "completed"
    assert runner.call == (conversation, "Exact intent", "Exact prompt")
    for event in events:
        assert timeline.index(f"flush:chat_event:{event.type}") < timeline.index(
            f"resume:{event.type}"
        )
    assert timeline.index("flush:snapshot_request") < timeline.index("snapshot:call")
    rows = _trace_rows(stream)
    assert [row["payload"] for row in rows if row["kind"] == "chat_event"] == [
        event.to_dict() for event in events
    ]
    assert [row["kind"] for row in rows[-3:]] == [
        "snapshot_request",
        "snapshot_result",
        "run_finished",
    ]
    assert rows[-1]["payload"] == {
        "stream_exhausted": True,
        "done_observed": True,
        "chat_error_observed": False,
        "usage": events[-1].usage,
        "inspection_attempted": True,
        "inspection_result_recorded": True,
        "elapsed_seconds": 2.5,
    }
    assert recorder.closed is True


@pytest.mark.asyncio
async def test_real_chatrunner_uses_same_canonical_callable_for_gateway_and_snapshot():
    direct_executor = AsyncMock()
    canonical_executor = AsyncMock(
        side_effect=[
            {"success": True, "data": {"matches": ["Series"]}},
            {"success": True, "data": {"epoch": 7, "components": []}},
        ]
    )
    runner = ChatRunner(
        tool_executor=direct_executor,
        registry=ToolRegistry(catalog={}, agent_mode=True),
        mcp_capability_executor=canonical_executor,
    )
    conversation = Conversation(
        id="qualification",
        persona="architect",
        model="local/model",
        api_base="http://127.0.0.1:11434",
    )
    stream = _TraceStream()
    recorder = _recorder(stream)
    recorder.record("run_started", {"identity": "exact"})
    completion = AsyncMock(side_effect=[_gateway_stream(), _text_stream()])

    with patch(
        "rook.agent.chat.chat_runner.litellm.acompletion",
        completion,
    ), patch(
        "rook.agent.chat.chat_runner.collect_runtime_facts",
        new=AsyncMock(return_value={}),
    ):
        status = await OPERATOR._consume_events(
            recorder=recorder,
            runner=runner,
            conversation=conversation,
            intent="Exact intent",
            system_prompt="Exact prompt",
            canonical_executor=canonical_executor,
            target_matches=lambda: True,
            monotonic=iter([1.0, 2.0]).__next__,
        )

    assert status == "completed"
    assert canonical_executor.await_args_list == [
        call(
            "rook_tools_call",
            {"name": "gh_library", "arguments": {"search": "Series"}},
        ),
        call(
            "rook_tools_call",
            {
                "name": "gh_snapshot",
                "arguments": {"include_data": False, "max_preview_items": 0},
            },
        ),
    ]
    direct_executor.assert_not_awaited()
    assert [
        row["payload"]["type"]
        for row in _trace_rows(stream)
        if row["kind"] == "chat_event"
    ] == ["tool_start", "tool_result", "text_delta", "done"]


@pytest.mark.parametrize(
    ("event", "reason"),
    [
        (ChatEvent("tool_start", name="gh_edit", params={"port": 9999}), "target_override_forbidden"),
        (ChatEvent("tool_start", name="gh_edit", params={"session": "s"}), "target_override_forbidden"),
        (
            ChatEvent(
                "tool_start",
                name="gh_edit",
                params={"documentSerialNumber": 3},
            ),
            "target_override_forbidden",
        ),
        (
            ChatEvent("tool_start", name="rhino_set_active_instance", params={}),
            "target_control_forbidden",
        ),
        (
            ChatEvent("tool_start", name="rhino_clear_active_instance", params={}),
            "target_control_forbidden",
        ),
        (
            ChatEvent(
                "tool_start",
                name="rook_tools_call",
                params={"name": "gh_edit", "arguments": {"port": 9999}},
            ),
            "target_override_forbidden",
        ),
        (
            ChatEvent(
                "tool_start",
                name="rook_tools_call",
                params={"name": "gh_edit", "arguments": {"session": "s"}},
            ),
            "target_override_forbidden",
        ),
        (
            ChatEvent(
                "tool_start",
                name="rook_tools_call",
                params={
                    "name": "gh_edit",
                    "arguments": {"documentSerialNumber": 3},
                },
            ),
            "target_override_forbidden",
        ),
        (
            ChatEvent(
                "tool_start",
                name="rook_tools_call",
                params={"name": "rhino_set_active_instance", "arguments": {}},
            ),
            "target_control_forbidden",
        ),
        (
            ChatEvent(
                "tool_start",
                name="rook_tools_call",
                params={"name": "rhino_clear_active_instance", "arguments": {}},
            ),
            "target_control_forbidden",
        ),
    ],
)
def test_targeting_refusal_is_shallow_and_closed(event, reason):
    assert OPERATOR._targeting_refusal(event) == reason


def test_targeting_refusal_does_not_scan_domain_payloads_recursively():
    event = ChatEvent(
        "tool_start",
        name="rook_tools_call",
        params={
            "name": "gh_edit",
            "arguments": {"payload": {"session": "domain value"}},
        },
    )
    assert OPERATOR._targeting_refusal(event) is None


@pytest.mark.asyncio
async def test_forbidden_tool_start_stops_before_generator_resume():
    timeline = []
    stream = _TimelineStream(timeline)
    recorder = _recorder(stream)
    recorder.record("run_started", {})
    runner = _CausalRunner(
        [ChatEvent("tool_start", name="gh_edit", params={"port": 9999})],
        timeline,
    )
    canonical = AsyncMock()

    status = await OPERATOR._consume_events(
        recorder=recorder,
        runner=runner,
        conversation=Conversation(id="q", persona="architect"),
        intent="intent",
        system_prompt="prompt",
        canonical_executor=canonical,
        target_matches=lambda: True,
        monotonic=lambda: 1.0,
    )

    assert status == "refused"
    assert "resume:tool_start" not in timeline
    canonical.assert_not_awaited()
    assert [row["kind"] for row in _trace_rows(stream)] == [
        "run_started",
        "chat_event",
        "qualification_refusal",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("runner", "kind"),
    [
        (_ExceptionRunner(RuntimeError("STREAM_SENTINEL")), "stream_exception"),
        (_ExceptionRunner(asyncio.CancelledError()), "run_cancelled"),
    ],
)
async def test_stream_failure_records_bounded_terminal_prefix(runner, kind):
    stream = _TraceStream()
    recorder = _recorder(stream)
    recorder.record("run_started", {})
    canonical = AsyncMock()

    status = await OPERATOR._consume_events(
        recorder=recorder,
        runner=runner,
        conversation=Conversation(id="q", persona="architect"),
        intent="intent",
        system_prompt="prompt",
        canonical_executor=canonical,
        target_matches=lambda: True,
        monotonic=lambda: 1.0,
    )

    assert status == "refused"
    canonical.assert_not_awaited()
    rows = _trace_rows(stream)
    assert rows[-1]["kind"] == kind
    assert all(row["kind"] != "run_finished" for row in rows)
    if kind == "stream_exception":
        assert rows[-1]["payload"] == {
            "exception_type": "RuntimeError",
            "exception_message": "STREAM_SENTINEL",
        }


@pytest.mark.asyncio
async def test_missing_done_and_target_drift_skip_snapshot():
    for target_matches, final_kind in [
        (lambda: True, "chat_event"),
        (lambda: False, "target_drift"),
    ]:
        stream = _TraceStream()
        recorder = _recorder(stream)
        recorder.record("run_started", {})
        canonical = AsyncMock()
        status = await OPERATOR._consume_events(
            recorder=recorder,
            runner=_CausalRunner([ChatEvent("text_delta", content="partial")], []),
            conversation=Conversation(id="q", persona="architect"),
            intent="intent",
            system_prompt="prompt",
            canonical_executor=canonical,
            target_matches=target_matches,
            monotonic=lambda: 1.0,
        )
        assert status == "refused"
        canonical.assert_not_awaited()
        assert _trace_rows(stream)[-1]["kind"] == final_kind


@pytest.mark.asyncio
async def test_chat_error_followed_by_done_remains_snapshot_eligible():
    stream = _TraceStream()
    recorder = _recorder(stream)
    recorder.record("run_started", {})
    status = await OPERATOR._consume_events(
        recorder=recorder,
        runner=_CausalRunner(
            [ChatEvent("error", content="bounded"), ChatEvent("done", usage={})],
            [],
        ),
        conversation=Conversation(id="q", persona="architect"),
        intent="intent",
        system_prompt="prompt",
        canonical_executor=AsyncMock(return_value={"success": False, "error": "offline"}),
        target_matches=lambda: True,
        monotonic=iter([1.0, 2.0]).__next__,
    )
    assert status == "completed"
    rows = _trace_rows(stream)
    assert rows[-1]["kind"] == "run_finished"
    assert rows[-1]["payload"]["chat_error_observed"] is True
    assert rows[-2]["payload"] == {"success": False, "error": "offline"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("fail_write_at", "events", "resumed"),
    [
        (2, [ChatEvent("tool_start", name="gh_edit", params={})], None),
        (
            3,
            [
                ChatEvent("tool_start", name="gh_edit", params={}),
                ChatEvent("tool_result", name="gh_edit", result="{}"),
            ],
            "resume:tool_start",
        ),
    ],
)
async def test_event_write_failure_blocks_every_subsequent_call(
    fail_write_at, events, resumed
):
    timeline = []
    stream = _TimelineStream(timeline, fail_write_at=fail_write_at)
    recorder = _recorder(stream)
    recorder.record("run_started", {})
    canonical = AsyncMock()
    status = await OPERATOR._consume_events(
        recorder=recorder,
        runner=_CausalRunner(events, timeline),
        conversation=Conversation(id="q", persona="architect"),
        intent="intent",
        system_prompt="prompt",
        canonical_executor=canonical,
        target_matches=lambda: True,
        monotonic=lambda: 1.0,
    )
    assert status == "trace_write_failed"
    canonical.assert_not_awaited()
    if resumed is None:
        assert not any(item.startswith("resume:") for item in timeline)
    else:
        assert resumed in timeline
        assert "resume:tool_result" not in timeline


@pytest.mark.asyncio
async def test_snapshot_exception_or_post_call_drift_never_records_result():
    for canonical, checks in [
        (AsyncMock(side_effect=RuntimeError("SNAPSHOT_SENTINEL")), iter([True, True])),
        (
            AsyncMock(return_value={"success": True, "data": {"epoch": 7}}),
            iter([True, True, False]),
        ),
    ]:
        stream = _TraceStream()
        recorder = _recorder(stream)
        recorder.record("run_started", {})
        status = await OPERATOR._consume_events(
            recorder=recorder,
            runner=_CausalRunner([ChatEvent("done", usage={})], []),
            conversation=Conversation(id="q", persona="architect"),
            intent="intent",
            system_prompt="prompt",
            canonical_executor=canonical,
            target_matches=lambda: next(checks),
            monotonic=lambda: 1.0,
        )
        assert status == "refused"
        kinds = [row["kind"] for row in _trace_rows(stream)]
        assert "snapshot_request" in kinds
        assert "snapshot_result" not in kinds
        assert "run_finished" not in kinds


@pytest.mark.asyncio
async def test_close_failure_preserves_run_finished_but_reports_trace_failure():
    stream = _TraceStream(fail_close=True)
    recorder = _recorder(stream)
    recorder.record("run_started", {})
    status = await OPERATOR._consume_events(
        recorder=recorder,
        runner=_CausalRunner([ChatEvent("done", usage={})], []),
        conversation=Conversation(id="q", persona="architect"),
        intent="intent",
        system_prompt="prompt",
        canonical_executor=AsyncMock(return_value={"success": True}),
        target_matches=lambda: True,
        monotonic=iter([1.0, 2.0]).__next__,
    )
    assert status == "trace_write_failed"
    assert _trace_rows(stream)[-1]["kind"] == "run_finished"
    assert stream.close_calls == 1


@pytest.mark.asyncio
async def test_run_row_composes_exact_identity_prompt_target_and_gateway(
    tmp_path, monkeypatch
):
    row = _admitted_row(tmp_path)
    trace_stream = _TraceStream()
    recorder = _recorder(trace_stream)
    runner = _CausalRunner([ChatEvent("done", usage={})], [])
    dispatcher = MagicMock(dispatch=AsyncMock())
    canonical = AsyncMock(return_value={"success": True, "data": {"epoch": 7}})
    runner_factory = MagicMock(return_value=runner)
    previous_target = get_active_target()

    monkeypatch.setattr(OPERATOR, "_open_recorder", lambda: recorder)
    monkeypatch.setattr(
        OPERATOR,
        "_runtime_identity",
        lambda: {
            "git_head": "abc123",
            "git_dirty": False,
            "python_executable": "python",
            "python_version": "3.12.12",
            "rook_module_path": "rook/__init__.py",
            "litellm_version": "1.89.4",
        },
        raising=False,
    )
    monkeypatch.setattr(
        OPERATOR,
        "PromptBuilder",
        lambda: MagicMock(build_system=MagicMock(return_value="ARCHITECT")),
        raising=False,
    )
    monkeypatch.setattr(OPERATOR, "build_local_tools", lambda: {}, raising=False)
    monkeypatch.setattr(
        OPERATOR,
        "ToolDispatcher",
        lambda *, port, local_tools: dispatcher,
        raising=False,
    )
    monkeypatch.setattr(
        OPERATOR,
        "build_mcp_capability_gateway_executor",
        lambda access: canonical,
        raising=False,
    )
    monkeypatch.setattr(OPERATOR, "ChatRunner", runner_factory, raising=False)
    monkeypatch.setattr(
        OPERATOR,
        "resolve_profile",
        lambda env: MagicMock(value="full"),
        raising=False,
    )

    status, path = await OPERATOR._run_row(row)

    assert (status, path) == ("completed", Path("trace.jsonl"))
    conversation, intent, prompt = runner.call
    assert conversation.persona == "architect"
    assert conversation.model == row.model
    assert conversation.api_base == row.api_base
    assert conversation.document_serial_number == row.target.document_serial_number
    assert intent == row.intent
    assert prompt == f"ARCHITECT\n\n## Explicit qualification skill\n\n{row.skill_text}"
    assert runner_factory.call_args.kwargs == {
        "tool_executor": dispatcher.dispatch,
        "tool_access": "full",
        "mcp_capability_executor": canonical,
    }
    assert get_active_target() == previous_target
    started = _trace_rows(trace_stream)[0]
    assert started["kind"] == "run_started"
    assert started["payload"] == {
        "row_path": str(row.source_path),
        "row_sha256": row.source_sha256,
        "git_head": "abc123",
        "git_dirty": False,
        "python_executable": "python",
        "python_version": "3.12.12",
        "rook_module_path": "rook/__init__.py",
        "litellm_version": "1.89.4",
        "model": row.model,
        "api_base": row.api_base,
        "mcp_profile": "full",
        "intent": row.intent,
        "skill_path": str(row.skill_path),
        "skill_sha256": row.skill_sha256,
        "system_prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "rhino_target": {
            "port": row.target.port,
            "process_id": row.target.process_id,
            "document_serial_number": row.target.document_serial_number,
        },
    }


@pytest.mark.asyncio
async def test_run_started_write_failure_causes_zero_contact(tmp_path, monkeypatch):
    row = _admitted_row(tmp_path)
    recorder = _recorder(_TraceStream(fail_write_at=1))
    runner = _CausalRunner([ChatEvent("done", usage={})], [])
    canonical = AsyncMock()
    monkeypatch.setattr(OPERATOR, "_open_recorder", lambda: recorder)
    monkeypatch.setattr(OPERATOR, "_runtime_identity", lambda: {}, raising=False)
    monkeypatch.setattr(
        OPERATOR,
        "PromptBuilder",
        lambda: MagicMock(build_system=MagicMock(return_value="ARCHITECT")),
        raising=False,
    )
    monkeypatch.setattr(OPERATOR, "build_local_tools", lambda: {}, raising=False)
    monkeypatch.setattr(
        OPERATOR,
        "ToolDispatcher",
        lambda **kwargs: MagicMock(dispatch=AsyncMock()),
        raising=False,
    )
    monkeypatch.setattr(
        OPERATOR,
        "build_mcp_capability_gateway_executor",
        lambda access: canonical,
        raising=False,
    )
    monkeypatch.setattr(OPERATOR, "ChatRunner", lambda **kwargs: runner, raising=False)
    monkeypatch.setattr(
        OPERATOR,
        "resolve_profile",
        lambda env: MagicMock(value="full"),
        raising=False,
    )

    status, path = await OPERATOR._run_row(row)

    assert (status, path) == ("trace_write_failed", Path("trace.jsonl"))
    assert runner.call is None
    canonical.assert_not_awaited()


def test_main_emits_only_bounded_status_and_trace_path(tmp_path, monkeypatch, capsys):
    row = _admitted_row(tmp_path)
    monkeypatch.setattr(OPERATOR, "_load_row", lambda path: row)

    async def run(_row):
        return "completed", Path("C:/trace.jsonl")

    monkeypatch.setattr(OPERATOR, "_run_row", run, raising=False)
    assert OPERATOR.main([str(row.source_path)]) == 0
    assert capsys.readouterr() == (
        '{"status":"completed","trace_path":"C:/trace.jsonl"}\n',
        "",
    )


def test_main_refuses_invalid_argument_count_without_exception_text(capsys):
    assert OPERATOR.main([]) == 1
    assert capsys.readouterr() == (
        '{"status":"refused","trace_path":null}\n',
        "",
    )
