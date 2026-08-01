from __future__ import annotations

import asyncio
import copy
import importlib.util
import json
import subprocess
import sys
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest


_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _ROOT / "scripts" / "minimal_intent_worker_real_compile_smoke.py"
_INTENT = (
    "Create a Grasshopper C# component with one A:double output "
    "and compile cleanly."
)
_PRE_DOCUMENT_ID = "pre-document"
_POST_DOCUMENT_ID = "post-document"
_COMPONENT_GUID = "real-compile-smoke-test-component"
_INITIAL_BODY = "A = DefinitelyMissingSymbol;"
_WORKER_BODY = "A = 42.0;"
_TARGET_DIAGNOSTIC = (
    "CS0103: The name 'DefinitelyMissingSymbol' does not exist "
    "in the current context."
)


def _load_smoke():
    spec = importlib.util.spec_from_file_location(
        "minimal_intent_worker_real_compile_smoke",
        _SCRIPT,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SMOKE = _load_smoke()

from rook.agent import local_worker_model_transport as transport_module  # noqa: E402


class _TraceStream:
    def __init__(
        self,
        *,
        fail_write_at: int | None = None,
        short_write_at: int | None = None,
        fail_flush_at: int | None = None,
        fail_close: bool = False,
    ) -> None:
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


class _TimelineTraceStream(_TraceStream):
    def __init__(self, timeline: list[str]) -> None:
        super().__init__()
        self._timeline = timeline

    def flush(self) -> None:
        super().flush()
        last_row = json.loads(bytes(self.content).splitlines()[-1])
        self._timeline.append(f"{last_row['event']}_flush")


class _EventFailTraceStream(_TraceStream):
    def __init__(
        self,
        *,
        fail_write_event: str | None = None,
        fail_flush_event: str | None = None,
    ) -> None:
        super().__init__()
        self._fail_write_event = fail_write_event
        self._fail_flush_event = fail_flush_event
        self._last_event: str | None = None

    def write(self, value: bytes) -> int:
        event = json.loads(value)["event"]
        self._last_event = event
        if event == self._fail_write_event:
            self.write_calls += 1
            raise OSError("TRACE_EVENT_WRITE_SENTINEL")
        return super().write(value)

    def flush(self) -> None:
        self.flush_calls += 1
        if self._last_event == self._fail_flush_event:
            raise OSError("TRACE_EVENT_FLUSH_SENTINEL")


_TRACE_TIME = datetime(2026, 7, 30, 21, 30, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _isolate_live_trace_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))


def _in_memory_trace(
    name: str = "flight.jsonl",
) -> tuple[SMOKE._JsonlFlightRecorder, SMOKE._LiveCallCounts, _TraceStream]:
    stream = _TraceStream()
    recorder = SMOKE._JsonlFlightRecorder(
        path=Path(name),
        stream=stream,
        clock=lambda: _TRACE_TIME,
    )
    return recorder, SMOKE._LiveCallCounts(), stream


def _serialized_trace_row(
    *,
    sequence: int,
    event: str,
    payload: Mapping[str, Any],
) -> bytes:
    return (
        json.dumps(
            {
                "sequence": sequence,
                "recorded_at_utc": "2026-07-30T21:30:00.000000Z",
                "event": event,
                "payload": payload,
            },
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _padding_payload_for_row_size(
    *,
    sequence: int,
    event: str,
    target_size: int,
) -> dict[str, str]:
    empty_size = len(
        _serialized_trace_row(
            sequence=sequence,
            event=event,
            payload={"padding": ""},
        )
    )
    padding_size = target_size - empty_size
    assert padding_size >= 0
    payload = {"padding": "x" * padding_size}
    assert len(
        _serialized_trace_row(
            sequence=sequence,
            event=event,
            payload=payload,
        )
    ) == target_size
    return payload


def test_flight_recorder_writes_one_flushed_jsonl_row(tmp_path: Path) -> None:
    stream = _TraceStream()
    recorder = SMOKE._JsonlFlightRecorder(
        path=tmp_path / "flight.jsonl",
        stream=stream,
        clock=lambda: _TRACE_TIME,
    )

    recorder.record("run_started", {"intent": "fixed"})

    expected = {
        "sequence": 1,
        "recorded_at_utc": "2026-07-30T21:30:00.000000Z",
        "event": "run_started",
        "payload": {"intent": "fixed"},
    }
    assert bytes(stream.content) == (
        json.dumps(expected, ensure_ascii=True, allow_nan=False, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")
    assert stream.write_calls == 1
    assert stream.flush_calls == 1
    assert recorder.sequence == 1
    assert recorder.bytes_written == len(stream.content)


def test_flight_recorder_serialization_rejection_flushes_then_raises(
    tmp_path: Path,
) -> None:
    stream = _TraceStream()
    path = tmp_path / "flight.jsonl"
    recorder = SMOKE._JsonlFlightRecorder(
        path=path,
        stream=stream,
        clock=lambda: _TRACE_TIME,
    )

    with pytest.raises(SMOKE._TraceWriteFailure) as raised:
        recorder.record("planner_response", {"raw_response": object()})

    assert str(raised.value) == "trace_write_failed"
    assert raised.value.reason == "json_serialization_failed"
    assert raised.value.path == path
    assert recorder.failed is True
    assert recorder.sequence == 1
    assert stream.write_calls == 1
    assert stream.flush_calls == 1
    lines = bytes(stream.content).splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0]) == {
        "sequence": 1,
        "recorded_at_utc": "2026-07-30T21:30:00.000000Z",
        "event": "event_serialization_failed",
        "payload": {
            "attempted_event": "planner_response",
            "rejection_reason": "json_serialization_failed",
        },
    }

    retained = bytes(stream.content)
    with pytest.raises(SMOKE._TraceWriteFailure):
        recorder.record("run_finished", {})
    assert bytes(stream.content) == retained
    assert stream.write_calls == 1
    assert stream.flush_calls == 1


@pytest.mark.parametrize(
    ("reason", "expected_event"),
    [
        ("json_serialization_failed", "event_serialization_failed"),
        ("row_size_exceeded", "event_rejected"),
        ("total_size_exceeded", "event_rejected"),
        ("exception_message_size_exceeded", "event_rejected"),
    ],
)
def test_flight_recorder_reject_always_flushes_then_raises(
    tmp_path: Path,
    reason: str,
    expected_event: str,
) -> None:
    stream = _TraceStream()
    recorder = SMOKE._JsonlFlightRecorder(
        path=tmp_path / "flight.jsonl",
        stream=stream,
        clock=lambda: _TRACE_TIME,
    )

    with pytest.raises(SMOKE._TraceWriteFailure) as raised:
        recorder._reject("planner_response", reason)

    assert raised.value.reason == reason
    assert recorder.failed is True
    assert recorder.sequence == 1
    assert stream.write_calls == 1
    assert stream.flush_calls == 1
    row = json.loads(bytes(stream.content))
    assert row["event"] == expected_event
    assert row["payload"] == {
        "attempted_event": "planner_response",
        "rejection_reason": reason,
    }


def test_flight_recorder_short_write_retains_partial_bytes_and_stops(
    tmp_path: Path,
) -> None:
    stream = _TraceStream(short_write_at=1)
    recorder = SMOKE._JsonlFlightRecorder(
        path=tmp_path / "flight.jsonl",
        stream=stream,
        clock=lambda: _TRACE_TIME,
    )

    with pytest.raises(SMOKE._TraceWriteFailure) as raised:
        recorder.record("run_started", {"intent": "fixed"})

    assert raised.value.reason == "short_write"
    assert recorder.failed is True
    assert recorder.sequence == 0
    assert recorder.bytes_written == len(stream.content)
    assert stream.write_calls == 1
    assert stream.flush_calls == 0
    assert bytes(stream.content)
    assert not bytes(stream.content).endswith(b"\n")

    retained = bytes(stream.content)
    with pytest.raises(SMOKE._TraceWriteFailure):
        recorder.record("run_finished", {})
    assert bytes(stream.content) == retained
    assert stream.write_calls == 1


def test_flight_recorder_accepts_exact_complete_row_limit(tmp_path: Path) -> None:
    stream = _TraceStream()
    recorder = SMOKE._JsonlFlightRecorder(
        path=tmp_path / "flight.jsonl",
        stream=stream,
        clock=lambda: _TRACE_TIME,
    )
    payload = _padding_payload_for_row_size(
        sequence=1,
        event="planner_response",
        target_size=256 * 1024,
    )

    recorder.record("planner_response", payload)

    assert len(stream.content) == 256 * 1024
    assert recorder.bytes_written == 256 * 1024
    assert recorder.sequence == 1
    assert recorder.failed is False


def test_flight_recorder_rejects_complete_row_limit_plus_one(
    tmp_path: Path,
) -> None:
    stream = _TraceStream()
    recorder = SMOKE._JsonlFlightRecorder(
        path=tmp_path / "flight.jsonl",
        stream=stream,
        clock=lambda: _TRACE_TIME,
    )
    payload = _padding_payload_for_row_size(
        sequence=1,
        event="planner_response",
        target_size=(256 * 1024) + 1,
    )

    with pytest.raises(SMOKE._TraceWriteFailure) as raised:
        recorder.record("planner_response", payload)

    assert raised.value.reason == "row_size_exceeded"
    row = json.loads(bytes(stream.content))
    assert row["event"] == "event_rejected"
    assert row["payload"] == {
        "attempted_event": "planner_response",
        "rejection_reason": "row_size_exceeded",
    }
    assert len(stream.content) <= 4 * 1024


def test_flight_recorder_reserves_tail_after_exact_normal_total(
    tmp_path: Path,
) -> None:
    stream = _TraceStream()
    recorder = SMOKE._JsonlFlightRecorder(
        path=tmp_path / "flight.jsonl",
        stream=stream,
        clock=lambda: _TRACE_TIME,
    )
    row_max = 256 * 1024
    normal_total = (4 * 1024 * 1024) - (4 * 1024)
    row_sizes = ([row_max] * 15) + [normal_total - (15 * row_max)]
    assert sum(row_sizes) == normal_total

    for sequence, row_size in enumerate(row_sizes, start=1):
        recorder.record(
            "tool_response",
            _padding_payload_for_row_size(
                sequence=sequence,
                event="tool_response",
                target_size=row_size,
            ),
        )

    assert recorder.bytes_written == normal_total
    assert len(stream.content) == normal_total
    with pytest.raises(SMOKE._TraceWriteFailure) as raised:
        recorder.record("run_finished", {})

    assert raised.value.reason == "total_size_exceeded"
    assert recorder.sequence == len(row_sizes) + 1
    assert recorder.failed is True
    assert recorder.bytes_written == len(stream.content)
    assert recorder.bytes_written <= 4 * 1024 * 1024
    rejection = json.loads(bytes(stream.content).splitlines()[-1])
    assert rejection["event"] == "event_rejected"
    assert rejection["payload"] == {
        "attempted_event": "run_finished",
        "rejection_reason": "total_size_exceeded",
    }


class _UnstringableException(Exception):
    def __str__(self) -> str:
        raise ValueError("UNSTRINGABLE_SENTINEL")


def test_flight_recorder_records_escaped_surrogate_exception_message(
    tmp_path: Path,
) -> None:
    stream = _TraceStream()
    recorder = SMOKE._JsonlFlightRecorder(
        path=tmp_path / "flight.jsonl",
        stream=stream,
        clock=lambda: _TRACE_TIME,
    )
    error = RuntimeError("prefix-\ud800-suffix")

    recorder.record_exception(
        "tool_exception",
        {"phase": "execution", "call_index": 1},
        error,
    )

    row = json.loads(bytes(stream.content))
    assert row["event"] == "tool_exception"
    assert row["payload"] == {
        "phase": "execution",
        "call_index": 1,
        "exception_type": "RuntimeError",
        "exception_message": "prefix-\ud800-suffix",
    }
    assert recorder.failed is False


@pytest.mark.parametrize(
    ("message_size", "should_reject"),
    [
        ((16 * 1024) - 2, False),
        ((16 * 1024) - 1, True),
    ],
)
def test_flight_recorder_bounds_ensure_ascii_exception_message(
    tmp_path: Path,
    message_size: int,
    should_reject: bool,
) -> None:
    message = "x" * message_size
    encoded = json.dumps(
        message,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")
    expected_size = 16 * 1024 if not should_reject else (16 * 1024) + 1
    assert len(encoded) == expected_size
    stream = _TraceStream()
    recorder = SMOKE._JsonlFlightRecorder(
        path=tmp_path / "flight.jsonl",
        stream=stream,
        clock=lambda: _TRACE_TIME,
    )

    if should_reject:
        with pytest.raises(SMOKE._TraceWriteFailure) as raised:
            recorder.record_exception("planner_exception", {}, RuntimeError(message))
        assert raised.value.reason == "exception_message_size_exceeded"
        row = json.loads(bytes(stream.content))
        assert row["event"] == "event_rejected"
        assert row["payload"]["rejection_reason"] == (
            "exception_message_size_exceeded"
        )
    else:
        recorder.record_exception("planner_exception", {}, RuntimeError(message))
        row = json.loads(bytes(stream.content))
        assert row["event"] == "planner_exception"
        assert row["payload"]["exception_message"] == message


def test_flight_recorder_unstringable_exception_rejects_and_stops(
    tmp_path: Path,
) -> None:
    stream = _TraceStream()
    recorder = SMOKE._JsonlFlightRecorder(
        path=tmp_path / "flight.jsonl",
        stream=stream,
        clock=lambda: _TRACE_TIME,
    )

    with pytest.raises(SMOKE._TraceWriteFailure) as raised:
        recorder.record_exception(
            "worker_exception",
            {"role": "worker", "call_index": 1},
            _UnstringableException(),
        )

    assert raised.value.reason == "json_serialization_failed"
    assert recorder.failed is True
    row = json.loads(bytes(stream.content))
    assert row["event"] == "event_serialization_failed"
    assert row["payload"] == {
        "attempted_event": "worker_exception",
        "rejection_reason": "json_serialization_failed",
    }
    assert "UNSTRINGABLE_SENTINEL" not in bytes(stream.content).decode("utf-8")

    retained = bytes(stream.content)
    with pytest.raises(SMOKE._TraceWriteFailure):
        recorder.record("run_finished", {})
    assert bytes(stream.content) == retained


def test_flight_recorder_finish_flushes_run_finished_then_closes(
    tmp_path: Path,
) -> None:
    stream = _TraceStream()
    recorder = SMOKE._JsonlFlightRecorder(
        path=tmp_path / "flight.jsonl",
        stream=stream,
        clock=lambda: _TRACE_TIME,
    )

    recorder.finish({"operator_status": "refused", "planner_calls": 0})

    row = json.loads(bytes(stream.content))
    assert row["event"] == "run_finished"
    assert row["payload"] == {
        "operator_status": "refused",
        "planner_calls": 0,
    }
    assert recorder.sequence == 1
    assert recorder.closed is True
    assert stream.write_calls == 1
    assert stream.flush_calls == 1
    assert stream.close_calls == 1


def test_open_live_flight_recorder_creates_exclusive_local_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    recorder = SMOKE._open_live_flight_recorder()

    expected_parent = (tmp_path / "Rook" / "traces").resolve()
    assert recorder.path.is_absolute()
    assert recorder.path.parent.resolve() == expected_parent
    assert recorder.path.is_file()
    assert recorder.path.name.startswith(
        "minimal-intent-worker-real-compile-"
    )
    assert recorder.path.name.endswith(".jsonl")
    assert recorder.path.read_bytes() == b""
    recorder.close_incomplete()
    assert recorder.closed is True
    assert recorder.path.read_bytes() == b""


def test_open_live_flight_recorder_uses_unbuffered_exclusive_stream(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    real_open = Path.open
    observed: list[tuple[str, int]] = []

    def capture_open(
        path: Path,
        mode: str = "r",
        buffering: int = -1,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
    ):
        observed.append((mode, buffering))
        return real_open(path, mode, buffering, encoding, errors, newline)

    monkeypatch.setattr(Path, "open", capture_open)

    recorder = SMOKE._open_live_flight_recorder()

    assert observed == [("xb", 0)]
    recorder.close_incomplete()


def test_open_live_flight_recorder_requires_nonblank_localappdata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", "   ")

    with pytest.raises(SMOKE._TraceWriteFailure) as raised:
        SMOKE._open_live_flight_recorder()

    assert raised.value.reason == "localappdata_missing"
    assert raised.value.path is None


def test_open_live_flight_recorder_refuses_name_collision_without_clobber(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FrozenDatetime:
        @classmethod
        def now(cls, tz: object) -> datetime:
            assert tz is timezone.utc
            return _TRACE_TIME

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(SMOKE, "datetime", _FrozenDatetime)
    monkeypatch.setattr(SMOKE.os, "getpid", lambda: 1234)
    monkeypatch.setattr(SMOKE.secrets, "token_hex", lambda _size: "cafebabe")
    first = SMOKE._open_live_flight_recorder()
    first.record("run_started", {"intent": "retained"})
    retained = first.path.read_bytes()

    with pytest.raises(SMOKE._TraceWriteFailure) as raised:
        SMOKE._open_live_flight_recorder()

    assert raised.value.reason == "exclusive_open_failed"
    assert raised.value.path is None
    assert first.path.read_bytes() == retained
    first.close_incomplete()


@pytest.mark.parametrize(
    ("stream", "expected_reason", "expected_bytes", "expected_flushes"),
    [
        (_TraceStream(fail_write_at=1), "write_failed", 0, 0),
        (_TraceStream(fail_flush_at=1), "flush_failed", None, 1),
    ],
)
def test_flight_recorder_write_or_flush_failure_stops_without_retry(
    tmp_path: Path,
    stream: _TraceStream,
    expected_reason: str,
    expected_bytes: int | None,
    expected_flushes: int,
) -> None:
    recorder = SMOKE._JsonlFlightRecorder(
        path=tmp_path / "flight.jsonl",
        stream=stream,
        clock=lambda: _TRACE_TIME,
    )

    with pytest.raises(SMOKE._TraceWriteFailure) as raised:
        recorder.record("run_started", {"intent": "fixed"})

    assert raised.value.reason == expected_reason
    assert recorder.failed is True
    assert recorder.sequence == 0
    assert recorder.bytes_written == len(stream.content)
    assert stream.write_calls == 1
    assert stream.flush_calls == expected_flushes
    if expected_bytes is not None:
        assert len(stream.content) == expected_bytes
    retained = bytes(stream.content)
    with pytest.raises(SMOKE._TraceWriteFailure):
        recorder.record("run_finished", {})
    assert bytes(stream.content) == retained
    assert stream.write_calls == 1


def test_flight_recorder_finish_close_failure_retains_flushed_terminal_row(
    tmp_path: Path,
) -> None:
    stream = _TraceStream(fail_close=True)
    recorder = SMOKE._JsonlFlightRecorder(
        path=tmp_path / "flight.jsonl",
        stream=stream,
        clock=lambda: _TRACE_TIME,
    )

    with pytest.raises(SMOKE._TraceWriteFailure) as raised:
        recorder.finish({"operator_status": "completed"})

    assert raised.value.reason == "close_failed"
    assert recorder.failed is True
    assert recorder.closed is False
    assert recorder.sequence == 1
    assert stream.flush_calls == 1
    assert stream.close_calls == 1
    row = json.loads(bytes(stream.content))
    assert row["event"] == "run_finished"


def test_flight_recorder_failed_close_cleanup_is_one_shot(tmp_path: Path) -> None:
    stream = _TraceStream(fail_close=True)
    recorder = SMOKE._JsonlFlightRecorder(
        path=tmp_path / "flight.jsonl",
        stream=stream,
        clock=lambda: _TRACE_TIME,
    )
    with pytest.raises(SMOKE._TraceWriteFailure) as raised:
        recorder.finish({"operator_status": "completed"})
    assert raised.value.reason == "close_failed"
    retained = bytes(stream.content)

    recorder.close_incomplete()
    recorder.close_incomplete()

    assert stream.write_calls == 1
    assert stream.flush_calls == 1
    assert stream.close_calls == 1
    assert bytes(stream.content) == retained


def test_flight_recorder_failed_flush_cleanup_does_not_repeat_io(
    tmp_path: Path,
) -> None:
    stream = _TraceStream(fail_flush_at=1)
    recorder = SMOKE._JsonlFlightRecorder(
        path=tmp_path / "flight.jsonl",
        stream=stream,
        clock=lambda: _TRACE_TIME,
    )
    with pytest.raises(SMOKE._TraceWriteFailure) as raised:
        recorder.record("run_started", {"intent": "fixed"})
    assert raised.value.reason == "flush_failed"
    retained = bytes(stream.content)

    recorder.close_incomplete()
    recorder.close_incomplete()

    assert stream.write_calls == 1
    assert stream.flush_calls == 1
    assert stream.close_calls == 1
    assert bytes(stream.content) == retained


def test_flight_recorder_closes_failed_partial_trace_without_new_row(
    tmp_path: Path,
) -> None:
    stream = _TraceStream(short_write_at=1)
    recorder = SMOKE._JsonlFlightRecorder(
        path=tmp_path / "flight.jsonl",
        stream=stream,
        clock=lambda: _TRACE_TIME,
    )
    with pytest.raises(SMOKE._TraceWriteFailure):
        recorder.record("run_started", {"intent": "fixed"})
    retained = bytes(stream.content)

    recorder.close_incomplete()

    assert recorder.closed is True
    assert recorder.failed is True
    assert stream.close_calls == 1
    assert bytes(stream.content) == retained
    assert b"run_finished" not in retained


def test_flight_recorder_rejects_unknown_event_before_write(tmp_path: Path) -> None:
    stream = _TraceStream()
    recorder = SMOKE._JsonlFlightRecorder(
        path=tmp_path / "flight.jsonl",
        stream=stream,
        clock=lambda: _TRACE_TIME,
    )

    with pytest.raises(ValueError, match="closed vocabulary"):
        recorder.record("invented_event", {})

    assert stream.write_calls == 0
    assert stream.flush_calls == 0
    assert recorder.failed is False


def test_flight_recorder_nonfinite_payload_uses_serialization_rejection(
    tmp_path: Path,
) -> None:
    stream = _TraceStream()
    recorder = SMOKE._JsonlFlightRecorder(
        path=tmp_path / "flight.jsonl",
        stream=stream,
        clock=lambda: _TRACE_TIME,
    )

    with pytest.raises(SMOKE._TraceWriteFailure) as raised:
        recorder.record("planner_response", {"value": float("nan")})

    assert raised.value.reason == "json_serialization_failed"
    row = json.loads(bytes(stream.content))
    assert row["event"] == "event_serialization_failed"
    assert row["payload"]["rejection_reason"] == "json_serialization_failed"


@pytest.mark.parametrize(
    ("stream", "expected_reason", "expected_flushes"),
    [
        (_TraceStream(fail_write_at=1), "write_failed", 0),
        (_TraceStream(fail_flush_at=1), "flush_failed", 1),
    ],
)
def test_flight_recorder_rejection_write_or_flush_failure_still_terminates(
    tmp_path: Path,
    stream: _TraceStream,
    expected_reason: str,
    expected_flushes: int,
) -> None:
    recorder = SMOKE._JsonlFlightRecorder(
        path=tmp_path / "flight.jsonl",
        stream=stream,
        clock=lambda: _TRACE_TIME,
    )

    with pytest.raises(SMOKE._TraceWriteFailure) as raised:
        recorder.record("planner_response", {"raw_response": object()})

    assert raised.value.reason == expected_reason
    assert recorder.failed is True
    assert recorder.sequence == 0
    assert recorder.bytes_written == len(stream.content)
    assert stream.write_calls == 1
    assert stream.flush_calls == expected_flushes
    retained = bytes(stream.content)
    with pytest.raises(SMOKE._TraceWriteFailure):
        recorder.record("run_finished", {})
    assert bytes(stream.content) == retained
    assert stream.write_calls == 1


def test_open_live_flight_recorder_bounds_path_resolution_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    real_resolve = Path.resolve

    def fail_trace_resolve(path: Path, *args: Any, **kwargs: Any) -> Path:
        if path.suffix == ".jsonl":
            raise OSError("PATH_RESOLVE_SENTINEL")
        return real_resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", fail_trace_resolve)

    with pytest.raises(SMOKE._TraceWriteFailure) as raised:
        SMOKE._open_live_flight_recorder()

    assert raised.value.reason == "trace_path_prepare_failed"
    assert raised.value.path is None


@pytest.mark.asyncio
async def test_recording_wrappers_flush_around_one_exact_delegate_call(
    tmp_path: Path,
) -> None:
    timeline: list[str] = []
    stream = _TimelineTraceStream(timeline)
    recorder = SMOKE._JsonlFlightRecorder(
        path=tmp_path / "flight.jsonl",
        stream=stream,
        clock=lambda: _TRACE_TIME,
    )
    counts = SMOKE._LiveCallCounts()
    prompt = {"messages": [{"role": "user", "content": "exact"}]}
    planner_response = "".join(["planner", "-response"])

    class _PlannerDelegate:
        def send(self, received: Mapping[str, Any]) -> str:
            assert received is prompt
            timeline.append("planner_delegate")
            return planner_response

    class _PreparationDelegate:
        async def dispatch(
            self,
            tool_name: str,
            params: dict[str, Any],
        ) -> dict[str, Any]:
            assert tool_name == "gh_status"
            assert params is preparation_params
            timeline.append("preparation_delegate")
            return preparation_response

    planner = SMOKE._RecordingModelTransport(
        role="planner",
        delegate=_PlannerDelegate(),
        recorder=recorder,
        counts=counts,
    )
    preparation = SMOKE._RecordingPreparationDispatcher(
        delegate=_PreparationDelegate(),
        recorder=recorder,
        counts=counts,
    )
    preparation_params: dict[str, Any] = {}
    preparation_response = {"success": True, "data": {"available": True}}

    returned_planner = planner.send(prompt)
    returned_preparation = await preparation.dispatch(
        "gh_status",
        preparation_params,
    )

    assert returned_planner is planner_response
    assert returned_preparation is preparation_response
    assert timeline == [
        "planner_request_flush",
        "planner_delegate",
        "planner_response_flush",
        "tool_request_flush",
        "preparation_delegate",
        "tool_response_flush",
    ]
    assert counts.planner == 1
    assert counts.worker == 0
    assert counts.preparation == 1
    assert counts.execution == 0


@pytest.mark.asyncio
async def test_restricted_executor_traces_admitted_calls_around_exact_delegate(
    tmp_path: Path,
) -> None:
    timeline: list[str] = []
    stream = _TimelineTraceStream(timeline)
    recorder = SMOKE._JsonlFlightRecorder(
        path=tmp_path / "flight.jsonl",
        stream=stream,
        clock=lambda: _TRACE_TIME,
    )
    counts = SMOKE._LiveCallCounts()
    create_params = {"code": _WORKER_BODY}
    create_response = {"success": True, "data": {"created": True}}

    async def dispatch(tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        timeline.append(f"{tool_name}_delegate")
        assert tool_name == "gh_create_csharp_script"
        assert params is create_params
        return create_response

    executor = SMOKE._RestrictedRealToolExecutor(
        dispatch,
        recorder=recorder,
        counts=counts,
    )

    returned_create = await executor("gh_create_csharp_script", create_params)

    assert returned_create is create_response
    assert executor.call_names == ("gh_create_csharp_script",)
    assert counts.execution == 1
    assert timeline == [
        "tool_request_flush",
        "gh_create_csharp_script_delegate",
        "tool_response_flush",
    ]
    rows = [json.loads(line) for line in bytes(stream.content).splitlines()]
    assert [row["payload"]["phase"] for row in rows] == ["execution"] * 2
    assert [row["payload"]["call_index"] for row in rows] == [1, 1]


class _BoundaryDelegateException(Exception):
    pass


def _recording_boundary(
    *,
    kind: str,
    stream: _TraceStream,
    tmp_path: Path,
    result: object,
    exception: Exception | None = None,
) -> tuple[
    SMOKE._JsonlFlightRecorder,
    SMOKE._LiveCallCounts,
    list[tuple[object, ...]],
    Any,
]:
    recorder = SMOKE._JsonlFlightRecorder(
        path=tmp_path / f"{kind}.jsonl",
        stream=stream,
        clock=lambda: _TRACE_TIME,
    )
    counts = SMOKE._LiveCallCounts()
    delegate_calls: list[tuple[object, ...]] = []

    if kind in {"planner", "worker"}:
        prompt = {"messages": [{"role": "user", "content": kind}]}

        class _Delegate:
            def send(self, received: Mapping[str, Any]) -> object:
                delegate_calls.append((received,))
                if exception is not None:
                    raise exception
                return result

        wrapper = SMOKE._RecordingModelTransport(
            role=kind,
            delegate=_Delegate(),
            recorder=recorder,
            counts=counts,
        )

        async def invoke() -> object:
            return wrapper.send(prompt)

        return recorder, counts, delegate_calls, invoke

    if kind == "preparation":
        params: dict[str, Any] = {"probe": True}

        class _Delegate:
            async def dispatch(
                self,
                tool_name: str,
                received: dict[str, Any],
            ) -> object:
                delegate_calls.append((tool_name, received))
                if exception is not None:
                    raise exception
                return result

        wrapper = SMOKE._RecordingPreparationDispatcher(
            delegate=_Delegate(),
            recorder=recorder,
            counts=counts,
        )

        async def invoke() -> object:
            return await wrapper.dispatch("gh_status", params)

        return recorder, counts, delegate_calls, invoke

    if kind == "execution":
        params = {"code": _INITIAL_BODY}

        async def dispatch(tool_name: str, received: dict[str, Any]) -> object:
            delegate_calls.append((tool_name, received))
            if exception is not None:
                raise exception
            return result

        wrapper = SMOKE._RestrictedRealToolExecutor(
            dispatch,
            recorder=recorder,
            counts=counts,
        )

        async def invoke() -> object:
            return await wrapper("gh_create_csharp_script", params)

        return recorder, counts, delegate_calls, invoke

    raise AssertionError(f"unsupported boundary kind: {kind}")


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["planner", "worker", "preparation", "execution"])
async def test_recording_boundary_preserves_return_and_exception_identity(
    kind: str,
    tmp_path: Path,
) -> None:
    result: object = "exact-response" if kind in {"planner", "worker"} else {
        "success": True
    }
    _recorder, counts, calls, invoke = _recording_boundary(
        kind=kind,
        stream=_TraceStream(),
        tmp_path=tmp_path,
        result=result,
    )

    assert await invoke() is result
    assert len(calls) == 1
    assert getattr(counts, kind) == 1

    exception = _BoundaryDelegateException("BOUNDARY_EXCEPTION_SENTINEL")
    stream = _TraceStream()
    _recorder, counts, calls, invoke = _recording_boundary(
        kind=kind,
        stream=stream,
        tmp_path=tmp_path,
        result=result,
        exception=exception,
    )

    with pytest.raises(_BoundaryDelegateException) as raised:
        await invoke()

    assert raised.value is exception
    assert len(calls) == 1
    assert getattr(counts, kind) == 1
    exception_row = json.loads(bytes(stream.content).splitlines()[-1])
    expected_event = (
        f"{kind}_exception" if kind in {"planner", "worker"} else "tool_exception"
    )
    assert exception_row["event"] == expected_event
    assert exception_row["payload"]["exception_type"] == (
        "_BoundaryDelegateException"
    )
    assert exception_row["payload"]["exception_message"] == (
        "BOUNDARY_EXCEPTION_SENTINEL"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["planner", "worker", "preparation", "execution"])
@pytest.mark.parametrize("request_fault", ["write", "short_write"])
async def test_request_trace_failure_prevents_boundary_contact(
    kind: str,
    request_fault: str,
    tmp_path: Path,
) -> None:
    stream = _TraceStream(
        fail_write_at=1 if request_fault == "write" else None,
        short_write_at=1 if request_fault == "short_write" else None,
    )
    _recorder, counts, calls, invoke = _recording_boundary(
        kind=kind,
        stream=stream,
        tmp_path=tmp_path,
        result="response" if kind in {"planner", "worker"} else {"success": True},
    )

    with pytest.raises(SMOKE._TraceWriteFailure):
        await invoke()

    assert calls == []
    assert getattr(counts, kind) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["planner", "worker", "preparation", "execution"])
async def test_response_trace_failure_supersedes_one_completed_boundary_call(
    kind: str,
    tmp_path: Path,
) -> None:
    result: object = "response" if kind in {"planner", "worker"} else {
        "success": True
    }
    _recorder, counts, calls, invoke = _recording_boundary(
        kind=kind,
        stream=_TraceStream(fail_write_at=2),
        tmp_path=tmp_path,
        result=result,
    )

    with pytest.raises(SMOKE._TraceWriteFailure) as raised:
        await invoke()

    assert raised.value.reason == "write_failed"
    assert len(calls) == 1
    assert getattr(counts, kind) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["planner", "worker", "preparation", "execution"])
async def test_exception_trace_failure_supersedes_one_raised_boundary_call(
    kind: str,
    tmp_path: Path,
) -> None:
    exception = _BoundaryDelegateException("BOUNDARY_EXCEPTION_SENTINEL")
    _recorder, counts, calls, invoke = _recording_boundary(
        kind=kind,
        stream=_TraceStream(fail_write_at=2),
        tmp_path=tmp_path,
        result="unused",
        exception=exception,
    )

    with pytest.raises(SMOKE._TraceWriteFailure) as raised:
        await invoke()

    assert raised.value.reason == "write_failed"
    assert len(calls) == 1
    assert getattr(counts, kind) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["planner", "worker", "preparation", "execution"])
async def test_unstringable_boundary_exception_rejects_trace_and_next_contact(
    kind: str,
    tmp_path: Path,
) -> None:
    stream = _TraceStream()
    recorder, counts, calls, invoke = _recording_boundary(
        kind=kind,
        stream=stream,
        tmp_path=tmp_path,
        result="unused",
        exception=_UnstringableException(),
    )

    with pytest.raises(SMOKE._TraceWriteFailure) as raised:
        await invoke()

    assert raised.value.reason == "json_serialization_failed"
    assert len(calls) == 1
    assert getattr(counts, kind) == 1
    rows = [json.loads(line) for line in bytes(stream.content).splitlines()]
    assert rows[-1]["event"] == "event_serialization_failed"
    assert rows[-1]["payload"] == {
        "attempted_event": (
            f"{kind}_exception" if kind in {"planner", "worker"} else "tool_exception"
        ),
        "rejection_reason": "json_serialization_failed",
    }

    next_calls: list[Mapping[str, Any]] = []

    class _NextDelegate:
        def send(self, prompt: Mapping[str, Any]) -> str:
            next_calls.append(prompt)
            return "must-not-run"

    next_wrapper = SMOKE._RecordingModelTransport(
        role="planner",
        delegate=_NextDelegate(),
        recorder=recorder,
        counts=counts,
    )
    with pytest.raises(SMOKE._TraceWriteFailure) as next_raised:
        next_wrapper.send({"messages": []})
    assert next_raised.value.reason == "recorder_failed"
    assert next_calls == []


@pytest.mark.asyncio
async def test_recording_boundaries_share_one_global_sequence_and_local_indexes(
    tmp_path: Path,
) -> None:
    stream = _TraceStream()
    recorder = SMOKE._JsonlFlightRecorder(
        path=tmp_path / "flight.jsonl",
        stream=stream,
        clock=lambda: _TRACE_TIME,
    )
    counts = SMOKE._LiveCallCounts()

    class _PreparationDelegate:
        async def dispatch(self, _name: str, _params: dict[str, Any]) -> dict[str, Any]:
            return {"success": True}

    class _ModelDelegate:
        def send(self, _prompt: Mapping[str, Any]) -> str:
            return "{}"

    async def execution_dispatch(
        _name: str,
        _params: dict[str, Any],
    ) -> dict[str, Any]:
        return {"success": True}

    preparation = SMOKE._RecordingPreparationDispatcher(
        delegate=_PreparationDelegate(),
        recorder=recorder,
        counts=counts,
    )
    planner = SMOKE._RecordingModelTransport(
        role="planner",
        delegate=_ModelDelegate(),
        recorder=recorder,
        counts=counts,
    )
    worker = SMOKE._RecordingModelTransport(
        role="worker",
        delegate=_ModelDelegate(),
        recorder=recorder,
        counts=counts,
    )
    executor = SMOKE._RestrictedRealToolExecutor(
        execution_dispatch,
        recorder=recorder,
        counts=counts,
    )

    for name in ("gh_status", "gh_document_new", "gh_status"):
        await preparation.dispatch(name, {})
    planner.send({"messages": [{"role": "user", "content": "planner"}]})
    worker.send({"messages": [{"role": "user", "content": "worker"}]})
    await executor("gh_create_csharp_script", {"code": _WORKER_BODY})

    rows = [json.loads(line) for line in bytes(stream.content).splitlines()]
    assert [row["sequence"] for row in rows] == list(range(1, 13))
    preparation_rows = [
        row for row in rows if row["payload"].get("phase") == "preparation"
    ]
    execution_rows = [
        row for row in rows if row["payload"].get("phase") == "execution"
    ]
    assert [row["payload"]["call_index"] for row in preparation_rows] == [
        1,
        1,
        2,
        2,
        3,
        3,
    ]
    assert [row["payload"]["call_index"] for row in execution_rows] == [
        1,
        1,
    ]
    assert [
        row["payload"]["call_index"]
        for row in rows
        if row["payload"].get("role") == "planner"
    ] == [1, 1]
    assert [
        row["payload"]["call_index"]
        for row in rows
        if row["payload"].get("role") == "worker"
    ] == [1, 1]
    assert counts == SMOKE._LiveCallCounts(
        preparation=3,
        planner=1,
        worker=1,
        execution=1,
    )


@pytest.mark.asyncio
async def test_non_object_execution_response_is_traced_before_native_rejection(
    tmp_path: Path,
) -> None:
    stream = _TraceStream()

    async def dispatch(_name: str, _params: dict[str, Any]) -> list[str]:
        return ["not", "an", "object"]

    recorder = SMOKE._JsonlFlightRecorder(
        path=tmp_path / "flight.jsonl",
        stream=stream,
        clock=lambda: _TRACE_TIME,
    )
    executor = SMOKE._RestrictedRealToolExecutor(
        dispatch,
        recorder=recorder,
        counts=SMOKE._LiveCallCounts(),
    )

    with pytest.raises(TypeError, match="dispatcher result must be an exact object"):
        await executor("gh_create_csharp_script", {"code": _INITIAL_BODY})

    rows = [json.loads(line) for line in bytes(stream.content).splitlines()]
    assert [row["event"] for row in rows] == ["tool_request", "tool_response"]
    assert rows[-1]["payload"]["raw_response"] == ["not", "an", "object"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("prefix", "attempted_tool", "attempted_params", "message"),
    [
        ((), "gh_update_script", {"code": "x"}, "sequence differs"),
        (("gh_create_csharp_script",), "gh_create_csharp_script", {}, "sequence differs"),
        (("gh_create_csharp_script",), "gh_update_script", {}, "sequence differs"),
        ((), "gh_status", {}, "sequence differs"),
        ((), "gh_create_csharp_script", {"port": 9878}, "contain port"),
        (
            ("gh_create_csharp_script",),
            "gh_update_script",
            {"port": 9878},
            "contain port",
        ),
    ],
)
async def test_restricted_executor_rejection_writes_no_event_and_enters_no_delegate(
    prefix: tuple[str, ...],
    attempted_tool: str,
    attempted_params: dict[str, Any],
    message: str,
    tmp_path: Path,
) -> None:
    stream = _TraceStream()
    recorder = SMOKE._JsonlFlightRecorder(
        path=tmp_path / "flight.jsonl",
        stream=stream,
        clock=lambda: _TRACE_TIME,
    )
    counts = SMOKE._LiveCallCounts()
    dispatch = _RecordingDispatch()
    executor = SMOKE._RestrictedRealToolExecutor(
        dispatch,
        recorder=recorder,
        counts=counts,
    )
    for tool_name in prefix:
        await executor(tool_name, {"accepted": tool_name})

    before_bytes = bytes(stream.content)
    before_calls = copy.deepcopy(dispatch.calls)
    before_names = executor.call_names
    before_count = counts.execution
    dispatch.fail_if_called = True

    with pytest.raises(ValueError, match=message):
        await executor(attempted_tool, attempted_params)

    assert bytes(stream.content) == before_bytes
    assert dispatch.calls == before_calls
    assert executor.call_names == before_names
    assert counts.execution == before_count


def _planner_payload() -> dict[str, Any]:
    return {
        "goal": _INTENT,
        "capability": "grasshopper_csharp_component",
        "interface": {
            "inputs": [],
            "outputs": [{"name": "A", "type": "double"}],
        },
        "acceptance": "clean_compile_receipt",
    }


def _worker_payload(body: str = _WORKER_BODY) -> dict[str, Any]:
    return {
        "schema": "rook.local_worker_turn_response:v1",
        "kind": "action_request",
        "action_id": "draft_create_body",
        "rationale": "Draft the complete initial body.",
        "input": {"code": body},
    }


class _RawTransport:
    def __init__(self, payload: Mapping[str, Any]) -> None:
        self._raw = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
        self.calls: list[dict[str, Any]] = []

    def send(self, prompt_artifact: Mapping[str, Any]) -> str:
        self.calls.append(copy.deepcopy(dict(prompt_artifact)))
        return self._raw


class _RaisingTransport:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def send(self, prompt_artifact: Mapping[str, Any]) -> str:
        self.calls.append(copy.deepcopy(dict(prompt_artifact)))
        raise RuntimeError("PLANNER_TRANSPORT_SENTINEL")


class _ScriptedDispatcher:
    def __init__(self, *, port: int, local_tools: dict[str, Any]) -> None:
        self.port = port
        self.local_tools = local_tools
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def dispatch(self, name: str, params: dict[str, Any]) -> dict[str, Any]:
        captured = copy.deepcopy(params)
        self.calls.append((name, captured))
        index = len(self.calls)
        if index == 1 and name == "gh_status" and captured == {}:
            return _status(_PRE_DOCUMENT_ID)
        if index == 2 and name == "gh_document_new" and captured == {}:
            return {"success": True, "data": {"created": True}}
        if index == 3 and name == "gh_status" and captured == {}:
            return _status(_POST_DOCUMENT_ID)
        if index == 4 and name == "gh_create_csharp_script":
            assert captured == {
                "code": _WORKER_BODY,
                "pins_in": (),
                "pins_out": ("A:double",),
                "name": "RookMinimalInitialBodyHandoff",
                "x": 375,
                "y": 1080,
            }
            return _created_clean(captured["code"])
        raise AssertionError(f"unexpected scripted dispatch {index}: {name}")


class _CompileErrorDispatcher(_ScriptedDispatcher):
    async def dispatch(self, name: str, params: dict[str, Any]) -> dict[str, Any]:
        captured = copy.deepcopy(params)
        self.calls.append((name, captured))
        index = len(self.calls)
        if index == 1 and name == "gh_status" and captured == {}:
            return _status(_PRE_DOCUMENT_ID)
        if index == 2 and name == "gh_document_new" and captured == {}:
            return {"success": True, "data": {"created": True}}
        if index == 3 and name == "gh_status" and captured == {}:
            return _status(_POST_DOCUMENT_ID)
        if index == 4 and name == "gh_create_csharp_script":
            assert captured["code"] == _WORKER_BODY
            return _created_with_errors(captured["code"])
        raise AssertionError(f"unexpected stopped dispatch {index}: {name}")


def _status(document_id: str) -> dict[str, Any]:
    return {
        "success": True,
        "data": {
            "available": True,
            "ready_for_edit": True,
            "has_active_document": True,
            "document_id": document_id,
            "object_count": 0,
            "document_path": "",
        },
    }


def _created_with_errors(received_body: object) -> dict[str, Any]:
    assert received_body == _WORKER_BODY
    return {
        "success": False,
        "data": {
            "script_receipt": {
                "version": 1,
                "operation": "create",
                "language": "csharp",
                "artifact_status": "created_with_errors",
                "mutation": {
                    "status": "created",
                    "component_guid": _COMPONENT_GUID,
                },
                "verification": {
                    "status": "failed",
                    "target_error_count": 1,
                },
                "repair_anchor": {
                    "component_guid": _COMPONENT_GUID,
                    "language": "csharp",
                    "target_errors": [_TARGET_DIAGNOSTIC],
                },
            }
        },
    }


def _created_clean(received_body: object) -> dict[str, Any]:
    assert received_body == _WORKER_BODY
    return {
        "success": True,
        "data": {
            "script_receipt": {
                "version": 1,
                "operation": "create",
                "language": "csharp",
                "artifact_status": "usable",
                "mutation": {
                    "status": "created",
                    "component_guid": _COMPONENT_GUID,
                },
                "verification": {
                    "status": "passed",
                    "target_error_count": 0,
                },
                "repair_anchor": {
                    "component_guid": _COMPONENT_GUID,
                    "language": "csharp",
                    "target_errors": [],
                },
            }
        },
    }


@pytest.mark.asyncio
async def test_no_contact_walking_vertical_reaches_native_terminal(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    created_dispatchers: list[_ScriptedDispatcher] = []

    def make_dispatcher(*, port: int, local_tools: dict[str, Any]):
        dispatcher = _ScriptedDispatcher(port=port, local_tools=local_tools)
        created_dispatchers.append(dispatcher)
        return dispatcher

    planner_transport = _RawTransport(_planner_payload())
    worker_transport = _RawTransport(_worker_payload())
    transports = iter((planner_transport, worker_transport))
    monkeypatch.setattr(SMOKE, "ToolDispatcher", make_dispatcher)
    monkeypatch.setattr(
        SMOKE,
        "build_local_tools",
        lambda: {
            "gh_create_csharp_script": object(),
            "gh_update_script": object(),
        },
    )
    monkeypatch.setattr(
        SMOKE,
        "LiteLLMWorkerTransport",
        lambda **_kwargs: next(transports),
    )

    roles = SMOKE._ResolvedRoles(
        profile="hybrid",
        planner_model="anthropic/claude-opus-4-6",
        worker_model="ollama_chat/qwen3-coder:30b-a3b-q8_0",
        profile_api_base=None,
    )
    stream = _TraceStream()
    recorder = SMOKE._JsonlFlightRecorder(
        path=tmp_path / "walking.jsonl",
        stream=stream,
        clock=lambda: _TRACE_TIME,
    )
    call_counts = SMOKE._LiveCallCounts()
    live_run = await SMOKE._run_live_once(
        roles,
        SMOKE._ResolvedRhinoTarget(process_id=4001, port=9877),
        recorder=recorder,
        call_counts=call_counts,
    )

    assert live_run.result.terminal_stage == "terminal"
    assert live_run.result.terminal_reason == "terminal_node_selected:done"
    assert live_run.preparation.state == "fresh_document_verified"
    assert live_run.preparation.tool_calls == 3
    assert live_run.executor.call_names == ("gh_create_csharp_script",)
    assert len(planner_transport.calls) == 1
    assert len(worker_transport.calls) == 1
    assert len(created_dispatchers) == 1
    assert created_dispatchers[0].port == 9877
    assert created_dispatchers[0].calls == [
        ("gh_status", {}),
        ("gh_document_new", {}),
        ("gh_status", {}),
        (
            "gh_create_csharp_script",
            {
                "code": _WORKER_BODY,
                "pins_in": (),
                "pins_out": ("A:double",),
                "name": "RookMinimalInitialBodyHandoff",
                "x": 375,
                "y": 1080,
            },
        ),
    ]
    assert call_counts == SMOKE._LiveCallCounts(
        preparation=3,
        planner=1,
        worker=1,
        execution=1,
    )
    rows = [json.loads(line) for line in bytes(stream.content).splitlines()]
    assert [row["event"] for row in rows] == [
        "tool_request",
        "tool_response",
        "tool_request",
        "tool_response",
        "tool_request",
        "tool_response",
        "planner_request",
        "planner_response",
        "worker_request",
        "worker_response",
        "tool_request",
        "tool_response",
    ]
    assert SMOKE._summary_from_result(roles, live_run) == {
        "operator_status": "completed",
        "operator_reason": "native_terminal",
        "trace_path": None,
        "intent": _INTENT,
        "profile": "hybrid",
        "planner_model": "anthropic/claude-opus-4-6",
        "worker_model": "ollama_chat/qwen3-coder:30b-a3b-q8_0",
        "rooknative_process_id": 4001,
        "rooknative_port": 9877,
        "document_preparation_status": "fresh_document_verified",
        "preparation_tool_calls": 3,
        "planner_calls": 1,
        "worker_calls": 1,
        "execution_tool_calls": 1,
        "terminal_stage": "terminal",
        "terminal_reason": "terminal_node_selected:done",
        "planner_adapter_status": "decoded",
        "worker_adapter_status": "response_loaded",
    }


def test_compile_error_trace_preserves_the_native_causal_chain(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    dispatcher = _CompileErrorDispatcher(port=9877, local_tools={})
    planner_transport = _RawTransport(_planner_payload())
    worker_transport = _RawTransport(_worker_payload())
    transports = iter((planner_transport, worker_transport))
    stream = _TraceStream()
    _patch_main_recorder(monkeypatch, tmp_path, stream)
    monkeypatch.setattr(SMOKE, "get_models", lambda _profile: _models())
    monkeypatch.setattr(SMOKE, "discover_instances", lambda: [_native_row()])
    monkeypatch.setattr(
        SMOKE,
        "ToolDispatcher",
        lambda *, port, local_tools: dispatcher,
    )
    monkeypatch.setattr(SMOKE, "build_local_tools", lambda: {})
    monkeypatch.setattr(
        SMOKE,
        "LiteLLMWorkerTransport",
        lambda **_kwargs: next(transports),
    )

    exit_code, summary = _invoke_main(capsys, ["--execute-live"])

    assert exit_code == 1
    assert summary["operator_reason"] == "native_stop"
    assert summary["terminal_stage"] == "verify_create"
    assert summary["terminal_reason"] == "selector_halt:none_ready"
    assert summary["planner_calls"] == 1
    assert summary["worker_calls"] == 1
    assert summary["execution_tool_calls"] == 1
    assert len(planner_transport.calls) == 1
    assert len(worker_transport.calls) == 1

    rows = [json.loads(line) for line in bytes(stream.content).splitlines()]
    events = [row["event"] for row in rows]
    raw_create = next(
        row["payload"]["raw_response"]
        for row in rows
        if row["event"] == "tool_response"
        and row["payload"]["phase"] == "execution"
    )
    native_steps = [
        row["payload"]
        for row in rows
        if row["event"] == "native_step_projection"
    ]
    final_native = next(
        row["payload"]
        for row in rows
        if row["event"] == "final_native_result"
    )

    assert raw_create == {
        "success": False,
        "data": {
            "script_receipt": {
                "version": 1,
                "operation": "create",
                "language": "csharp",
                "artifact_status": "created_with_errors",
                "mutation": {
                    "status": "created",
                    "component_guid": _COMPONENT_GUID,
                },
                "verification": {
                    "status": "failed",
                    "target_error_count": 1,
                },
                "repair_anchor": {
                    "component_guid": _COMPONENT_GUID,
                    "language": "csharp",
                    "target_errors": [_TARGET_DIAGNOSTIC],
                },
            }
        },
    }
    assert [step["accepted_node_id"] for step in native_steps] == [
        "create_script",
        "verify_create",
    ]
    assert all(
        step["receipt"] == raw_create["data"]["script_receipt"]
        for step in native_steps
    )
    assert native_steps[1]["verifier_outcome_status"] == "needs_repair"
    assert native_steps[1]["graph"]["node_statuses"] == [
        {"node_id": "create_script", "status": "succeeded"},
        {"node_id": "done", "status": "pending"},
        {"node_id": "verify_create", "status": "needs_repair"},
    ]
    assert native_steps[1]["graph"]["ready_node_ids"] == []
    assert final_native["terminal_supply"] == {
        "decision": "HALT",
        "reason": "selector_halt:none_ready",
    }
    assert final_native["terminal_stage"] == "verify_create"
    assert final_native["terminal_reason"] == "selector_halt:none_ready"
    assert _TARGET_DIAGNOSTIC not in json.dumps(summary)
    assert events[-6:] == [
        "planner_admission",
        "compiled_workflow",
        "native_step_projection",
        "native_step_projection",
        "final_native_result",
        "run_finished",
    ]


def test_completed_trace_projects_only_the_returned_native_transaction(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    _patch_complete_live_main(monkeypatch)
    stream = _TraceStream()
    _patch_main_recorder(monkeypatch, tmp_path, stream)

    exit_code, summary = _invoke_main(capsys, ["--execute-live"])

    assert exit_code == 0
    assert summary["operator_status"] == "completed"
    rows = [json.loads(line) for line in bytes(stream.content).splitlines()]
    projection_rows = [
        row
        for row in rows
        if row["event"]
        in {
            "planner_admission",
            "compiled_workflow",
            "native_step_projection",
            "final_native_result",
        }
    ]
    assert [row["event"] for row in projection_rows] == [
        "planner_admission",
        "compiled_workflow",
        "native_step_projection",
        "native_step_projection",
        "final_native_result",
    ]
    admission = projection_rows[0]["payload"]
    assert admission == {
        "adapter_status": "decoded",
        "draft": _planner_payload(),
    }
    compiled = projection_rows[1]["payload"]
    assert compiled["workflow_id"] == "minimal_csharp_initial_body_handoff"
    assert compiled["selected_template_id"] == "gh_csharp_create_verify"
    assert compiled["graph_node_ids"] == [
        "create_script",
        "done",
        "verify_create",
    ]
    steps = [row["payload"] for row in projection_rows[2:4]]
    assert [step["accepted_node_id"] for step in steps] == [
        "create_script",
        "verify_create",
    ]
    assert [step["step_index"] for step in steps] == [1, 2]
    assert steps[0]["receipt"]["operation"] == "create"
    assert steps[1]["receipt"]["operation"] == "create"
    final_native = projection_rows[-1]["payload"]
    assert final_native["terminal_stage"] == "terminal"
    assert final_native["terminal_reason"] == "terminal_node_selected:done"
    assert final_native["terminal_supply"] == {
        "decision": "HALT",
        "reason": "terminal_node_selected:done",
    }
    assert final_native["call_counts"] == {
        "preparation": 3,
        "planner": 1,
        "worker": 1,
        "execution": 1,
    }
    assert rows[-1]["event"] == "run_finished"


@pytest.mark.parametrize("planner_stop", ["transport_failed", "draft_rejected"])
def test_planner_stops_emit_no_unowned_workflow_or_graph_projection(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    planner_stop: str,
) -> None:
    dispatcher = _ScriptedDispatcher(port=9877, local_tools={})
    planner_transport: Any
    if planner_stop == "transport_failed":
        planner_transport = _RaisingTransport()
    else:
        malformed = _planner_payload()
        malformed["unexpected"] = "DRAFT_SENTINEL"
        planner_transport = _RawTransport(malformed)
    worker_transport = _RawTransport(_worker_payload())
    transports = iter((planner_transport, worker_transport))
    stream = _TraceStream()
    _patch_main_recorder(monkeypatch, tmp_path, stream)
    monkeypatch.setattr(SMOKE, "get_models", lambda _profile: _models())
    monkeypatch.setattr(SMOKE, "discover_instances", lambda: [_native_row()])
    monkeypatch.setattr(
        SMOKE,
        "ToolDispatcher",
        lambda *, port, local_tools: dispatcher,
    )
    monkeypatch.setattr(SMOKE, "build_local_tools", lambda: {})
    monkeypatch.setattr(
        SMOKE,
        "LiteLLMWorkerTransport",
        lambda **_kwargs: next(transports),
    )

    exit_code, summary = _invoke_main(capsys, ["--execute-live"])

    assert exit_code == 1
    assert summary["planner_calls"] == 1
    assert summary["worker_calls"] == 0
    assert summary["execution_tool_calls"] == 0
    assert worker_transport.calls == []
    rows = [json.loads(line) for line in bytes(stream.content).splitlines()]
    events = [row["event"] for row in rows]
    assert "planner_admission" not in events
    assert "compiled_workflow" not in events
    assert "native_step_projection" not in events
    assert events[-2:] == ["final_native_result", "run_finished"]
    final_native = rows[-2]["payload"]
    expected_stage = (
        "planner_adapter"
        if planner_stop == "transport_failed"
        else "draft_admission"
    )
    assert final_native["terminal_stage"] == expected_stage
    assert "DRAFT_SENTINEL" not in json.dumps(summary)


def test_worker_refusal_trace_retains_only_the_legitimate_native_prefix(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    dispatcher = _ScriptedDispatcher(port=9877, local_tools={})
    planner_transport = _RawTransport(_planner_payload())
    worker_transport = _RawTransport(
        {
            "schema": "rook.local_worker_turn_response:v1",
            "kind": "refusal",
            "category": "insufficient_context",
            "reason": "An initial body cannot be authored.",
        }
    )
    transports = iter((planner_transport, worker_transport))
    stream = _TraceStream()
    _patch_main_recorder(monkeypatch, tmp_path, stream)
    monkeypatch.setattr(SMOKE, "get_models", lambda _profile: _models())
    monkeypatch.setattr(SMOKE, "discover_instances", lambda: [_native_row()])
    monkeypatch.setattr(
        SMOKE,
        "ToolDispatcher",
        lambda *, port, local_tools: dispatcher,
    )
    monkeypatch.setattr(SMOKE, "build_local_tools", lambda: {})
    monkeypatch.setattr(
        SMOKE,
        "LiteLLMWorkerTransport",
        lambda **_kwargs: next(transports),
    )

    exit_code, summary = _invoke_main(capsys, ["--execute-live"])

    assert exit_code == 1
    assert summary["terminal_stage"] == "worker_disposition"
    assert summary["worker_calls"] == 1
    assert summary["execution_tool_calls"] == 0
    rows = [json.loads(line) for line in bytes(stream.content).splitlines()]
    native_steps = [
        row["payload"]
        for row in rows
        if row["event"] == "native_step_projection"
    ]
    assert native_steps == []
    assert [
        row["payload"]["tool_name"]
        for row in rows
        if row["event"] == "tool_request"
        and row["payload"]["phase"] == "execution"
    ] == []
    final_native = next(
        row["payload"] for row in rows if row["event"] == "final_native_result"
    )
    assert final_native["worker_adapter_status"] == "response_loaded"
    assert "terminal_supply" not in final_native
    assert rows[-1]["event"] == "run_finished"


def test_returned_projection_trace_failure_preserves_native_status_but_not_completion(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    _patch_complete_live_main(monkeypatch)
    stream = _EventFailTraceStream(fail_write_event="native_step_projection")
    _patch_main_recorder(monkeypatch, tmp_path, stream)

    exit_code, summary = _invoke_main(capsys, ["--execute-live"])

    assert exit_code == 1
    assert summary["operator_status"] == "failed"
    assert summary["operator_reason"] == "trace_write_failed"
    assert summary["terminal_stage"] == "terminal"
    assert summary["terminal_reason"] == "terminal_node_selected:done"
    assert summary["preparation_tool_calls"] == 3
    assert summary["planner_calls"] == 1
    assert summary["worker_calls"] == 1
    assert summary["execution_tool_calls"] == 1
    rows = [json.loads(line) for line in bytes(stream.content).splitlines()]
    events = [row["event"] for row in rows]
    assert events[-2:] == ["planner_admission", "compiled_workflow"]
    assert "native_step_projection" not in events
    assert "final_native_result" not in events
    assert "run_finished" not in events


def test_projector_exception_leaves_trace_incomplete_and_preserves_native_summary(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    _patch_complete_live_main(monkeypatch)
    stream = _TraceStream()
    _patch_main_recorder(monkeypatch, tmp_path, stream)

    def raise_projector(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("PROJECTOR_SENTINEL")

    monkeypatch.setattr(SMOKE, "_project_native_steps", raise_projector)

    exit_code, summary = _invoke_main(capsys, ["--execute-live"])

    assert exit_code == 1
    assert summary["operator_status"] == "failed"
    assert summary["operator_reason"] == "trace_write_failed"
    assert summary["terminal_stage"] == "terminal"
    assert summary["terminal_reason"] == "terminal_node_selected:done"
    assert summary["preparation_tool_calls"] == 3
    assert summary["planner_calls"] == 1
    assert summary["worker_calls"] == 1
    assert summary["execution_tool_calls"] == 1
    assert "PROJECTOR_SENTINEL" not in json.dumps(summary)
    rows = [json.loads(line) for line in bytes(stream.content).splitlines()]
    assert rows[-1]["event"] == "compiled_workflow"
    assert "run_finished" not in [row["event"] for row in rows]


@pytest.mark.asyncio
async def test_verifier_receipts_are_projected_from_their_source_nodes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    live_run = await _run_scripted_worker(monkeypatch, _worker_payload())
    handoff = live_run.result.handoff_result
    assert handoff is not None
    verify_create_graph = handoff.step_records[1].execution.graph
    assert verify_create_graph.nodes["verify_create"].evidence is not None
    verify_create_graph.nodes["verify_create"].evidence.receipt = {
        "operation": "FORGED_VERIFIER_RECEIPT"
    }

    steps = SMOKE._project_native_steps(handoff)

    assert steps[1]["accepted_node_id"] == "verify_create"
    assert steps[1]["receipt"]["operation"] == "create"
    assert "FORGED_VERIFIER_RECEIPT" not in json.dumps(steps)


@pytest.mark.asyncio
async def test_returned_projectors_reject_native_ownership_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    live_run = await _run_scripted_worker(monkeypatch, _worker_payload())
    handoff = live_run.result.handoff_result
    assert handoff is not None
    supplies = handoff.supply_records

    object.__setattr__(
        handoff,
        "supply_records",
        supplies[:-2],
    )

    with pytest.raises(ValueError, match="record and supply lengths differ"):
        SMOKE._project_native_steps(handoff)
    object.__setattr__(handoff, "supply_records", supplies)

    max_steps = handoff.scaffold.max_steps
    object.__setattr__(
        handoff.scaffold,
        "max_steps",
        max_steps + 1,
    )

    with pytest.raises(ValueError, match="maximum steps differ"):
        SMOKE._project_compiled_workflow(handoff)
    object.__setattr__(handoff.scaffold, "max_steps", max_steps)


class _EqualitySpoof:
    def __eq__(self, _other: object) -> bool:
        return True


class _DictSubclass(dict):
    pass


class _SequenceDispatcher:
    def __init__(self, responses: list[object]) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def dispatch(self, name: str, params: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((name, copy.deepcopy(params)))
        response = self._responses[len(self.calls) - 1]
        if isinstance(response, BaseException):
            raise response
        return response  # type: ignore[return-value]


def _models(
    planner: object = "anthropic/claude-opus-4-6",
    worker: object = "ollama_chat/qwen3-coder:30b-a3b-q8_0",
) -> SimpleNamespace:
    return SimpleNamespace(planner=planner, worker=worker, api_base=None)


def _native_row(
    *,
    process_id: object = 4001,
    port: object = 9877,
) -> dict[str, object]:
    return {
        "pluginType": "native",
        "processId": process_id,
        "port": port,
    }


def _fail_if_reached(*_args: object, **_kwargs: object) -> None:
    raise AssertionError("unexpected downstream capability construction")


def _invoke_main(
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
) -> tuple[int, dict[str, Any]]:
    exit_code = SMOKE.main(argv)
    captured = capsys.readouterr()
    assert captured.err == ""
    lines = captured.out.splitlines()
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert type(parsed) is dict
    return exit_code, parsed


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        ([], "live_execution_not_requested"),
        (["--execute-live"], "execute_live"),
        (["--unknown"], "invalid_arguments"),
        (["--execute-live", "extra"], "invalid_arguments"),
        (["--execute-live", "--execute-live"], "invalid_arguments"),
        ([_EqualitySpoof()], "invalid_arguments"),
    ],
)
def test_argument_classifier_is_closed(argv: list[str], expected: str) -> None:
    assert SMOKE._classify_arguments(argv) == expected


@pytest.mark.parametrize(
    ("argv", "expected_code", "expected_reason"),
    [
        ([], 0, "live_execution_not_requested"),
        (["--unknown"], 1, "invalid_arguments"),
        (["--execute-live", "extra"], 1, "invalid_arguments"),
    ],
)
def test_argument_refusal_precedes_every_capability(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    argv: list[str],
    expected_code: int,
    expected_reason: str,
) -> None:
    monkeypatch.setattr(SMOKE, "get_models", _fail_if_reached)
    monkeypatch.setattr(SMOKE, "discover_instances", _fail_if_reached)
    monkeypatch.setattr(SMOKE, "ToolDispatcher", _fail_if_reached)
    monkeypatch.setattr(SMOKE, "LiteLLMWorkerTransport", _fail_if_reached)

    exit_code, summary = _invoke_main(capsys, argv)

    assert exit_code == expected_code
    assert summary["operator_status"] == "refused"
    assert summary["operator_reason"] == expected_reason
    assert summary["document_preparation_status"] == "not_started"
    assert summary["preparation_tool_calls"] == 0
    assert summary["planner_calls"] == 0
    assert summary["worker_calls"] == 0
    assert summary["execution_tool_calls"] == 0
    assert summary["trace_path"] is None
    assert list(tmp_path.rglob("*.jsonl")) == []


def test_live_profile_refusal_writes_and_closes_one_complete_trace(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        SMOKE,
        "get_models",
        lambda _profile: _models(
            "anthropic/claude-sonnet",
            "ollama_chat/qwen3-coder:30b-a3b-q8_0",
        ),
    )
    monkeypatch.setattr(SMOKE, "discover_instances", _fail_if_reached)
    monkeypatch.setattr(SMOKE, "ToolDispatcher", _fail_if_reached)
    monkeypatch.setattr(SMOKE, "LiteLLMWorkerTransport", _fail_if_reached)

    exit_code, summary = _invoke_main(capsys, ["--execute-live"])

    assert exit_code == 1
    assert summary["operator_status"] == "refused"
    assert summary["operator_reason"] == "profile_role_mismatch"
    trace_path = Path(summary["trace_path"])
    assert trace_path.is_absolute()
    rows = [json.loads(line) for line in trace_path.read_bytes().splitlines()]
    assert [row["event"] for row in rows] == ["run_started", "run_finished"]
    assert rows[0]["payload"] == {
        "intent": _INTENT,
        "profile": "hybrid",
        "expected_planner_model": "anthropic/claude-opus-4-6",
        "expected_worker_model": "ollama_chat/qwen3-coder:30b-a3b-q8_0",
    }
    assert rows[1]["payload"] == {
        "operator_status": "refused",
        "operator_reason": "profile_role_mismatch",
        "document_preparation_status": "not_started",
        "preparation_tool_calls": 0,
        "planner_calls": 0,
        "worker_calls": 0,
        "execution_tool_calls": 0,
    }


def test_live_header_failure_refuses_before_profile_or_discovery(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    path = (tmp_path / "header-failed.jsonl").resolve()
    path.touch()
    stream = _TraceStream(fail_flush_at=1)
    recorder = SMOKE._JsonlFlightRecorder(
        path=path,
        stream=stream,
        clock=lambda: _TRACE_TIME,
    )
    monkeypatch.setattr(SMOKE, "_open_live_flight_recorder", lambda: recorder)
    monkeypatch.setattr(SMOKE, "get_models", _fail_if_reached)
    monkeypatch.setattr(SMOKE, "discover_instances", _fail_if_reached)
    monkeypatch.setattr(SMOKE, "ToolDispatcher", _fail_if_reached)
    monkeypatch.setattr(SMOKE, "LiteLLMWorkerTransport", _fail_if_reached)

    exit_code, summary = _invoke_main(capsys, ["--execute-live"])

    assert exit_code == 1
    assert summary["operator_status"] == "failed"
    assert summary["operator_reason"] == "trace_write_failed"
    assert summary["trace_path"] == str(path)
    assert stream.close_calls == 1
    assert summary["preparation_tool_calls"] == 0
    assert summary["planner_calls"] == 0
    assert summary["worker_calls"] == 0
    assert summary["execution_tool_calls"] == 0


def test_live_trace_open_failure_reports_no_path_and_no_contact(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail_open() -> None:
        raise SMOKE._TraceWriteFailure("exclusive_open_failed", None)

    monkeypatch.setattr(SMOKE, "_open_live_flight_recorder", fail_open)
    monkeypatch.setattr(SMOKE, "get_models", _fail_if_reached)
    monkeypatch.setattr(SMOKE, "discover_instances", _fail_if_reached)
    monkeypatch.setattr(SMOKE, "ToolDispatcher", _fail_if_reached)
    monkeypatch.setattr(SMOKE, "LiteLLMWorkerTransport", _fail_if_reached)

    exit_code, summary = _invoke_main(capsys, ["--execute-live"])

    assert exit_code == 1
    assert summary["operator_status"] == "failed"
    assert summary["operator_reason"] == "trace_write_failed"
    assert summary["trace_path"] is None
    assert summary["preparation_tool_calls"] == 0
    assert summary["planner_calls"] == 0
    assert summary["worker_calls"] == 0
    assert summary["execution_tool_calls"] == 0


def _patch_complete_live_main(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[_ScriptedDispatcher, _RawTransport, _RawTransport]:
    dispatcher = _ScriptedDispatcher(port=9877, local_tools={})
    planner_transport = _RawTransport(_planner_payload())
    worker_transport = _RawTransport(_worker_payload())
    transports = iter((planner_transport, worker_transport))
    monkeypatch.setattr(SMOKE, "get_models", lambda _profile: _models())
    monkeypatch.setattr(SMOKE, "discover_instances", lambda: [_native_row()])
    monkeypatch.setattr(
        SMOKE,
        "ToolDispatcher",
        lambda *, port, local_tools: dispatcher,
    )
    monkeypatch.setattr(SMOKE, "build_local_tools", lambda: {})
    monkeypatch.setattr(
        SMOKE,
        "LiteLLMWorkerTransport",
        lambda **_kwargs: next(transports),
    )
    return dispatcher, planner_transport, worker_transport


def _patch_main_recorder(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    stream: _TraceStream,
) -> SMOKE._JsonlFlightRecorder:
    recorder = SMOKE._JsonlFlightRecorder(
        path=(tmp_path / "live-trace.jsonl").resolve(),
        stream=stream,
        clock=lambda: _TRACE_TIME,
    )
    monkeypatch.setattr(SMOKE, "_open_live_flight_recorder", lambda: recorder)
    return recorder


@pytest.mark.parametrize(
    (
        "failed_write",
        "expected_counts",
        "expected_last_event",
        "expected_preparation_state",
    ),
    [
        (2, (0, 0, 0, 0), "run_started", "not_started"),
        (3, (1, 0, 0, 0), "tool_request", "status_rejected"),
        (8, (3, 0, 0, 0), "tool_response", "fresh_document_verified"),
        (9, (3, 1, 0, 0), "planner_request", "fresh_document_verified"),
        (10, (3, 1, 0, 0), "planner_response", "fresh_document_verified"),
        (11, (3, 1, 1, 0), "worker_request", "fresh_document_verified"),
        (12, (3, 1, 1, 0), "worker_response", "fresh_document_verified"),
        (13, (3, 1, 1, 1), "tool_request", "fresh_document_verified"),
    ],
)
def test_live_trace_write_failure_stops_at_the_exact_boundary(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    failed_write: int,
    expected_counts: tuple[int, int, int, int],
    expected_last_event: str,
    expected_preparation_state: str,
) -> None:
    stream = _TraceStream(fail_write_at=failed_write)
    _patch_main_recorder(monkeypatch, tmp_path, stream)
    dispatcher, planner_transport, worker_transport = _patch_complete_live_main(
        monkeypatch
    )

    exit_code, summary = _invoke_main(capsys, ["--execute-live"])

    preparation, planner, worker, execution = expected_counts
    assert exit_code == 1
    assert summary["operator_status"] == "failed"
    assert summary["operator_reason"] == "trace_write_failed"
    assert summary["document_preparation_status"] == expected_preparation_state
    assert summary["preparation_tool_calls"] == preparation
    assert summary["planner_calls"] == planner
    assert summary["worker_calls"] == worker
    assert summary["execution_tool_calls"] == execution
    assert len(dispatcher.calls) == preparation + execution
    assert len(planner_transport.calls) == planner
    assert len(worker_transport.calls) == worker
    rows = [json.loads(line) for line in bytes(stream.content).splitlines()]
    assert rows[-1]["event"] == expected_last_event
    assert all(row["event"] != "run_finished" for row in rows)


def test_live_exception_trace_failure_counts_the_call_and_blocks_the_next(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    stream = _TraceStream(fail_write_at=3)
    _patch_main_recorder(monkeypatch, tmp_path, stream)
    dispatcher = _SequenceDispatcher([RuntimeError("PREPARATION_SENTINEL")])
    monkeypatch.setattr(SMOKE, "get_models", lambda _profile: _models())
    monkeypatch.setattr(SMOKE, "discover_instances", lambda: [_native_row()])
    monkeypatch.setattr(
        SMOKE,
        "ToolDispatcher",
        lambda *, port, local_tools: dispatcher,
    )
    monkeypatch.setattr(SMOKE, "build_local_tools", lambda: {})
    monkeypatch.setattr(SMOKE, "LiteLLMWorkerTransport", _fail_if_reached)

    exit_code, summary = _invoke_main(capsys, ["--execute-live"])

    assert exit_code == 1
    assert summary["operator_reason"] == "trace_write_failed"
    assert summary["document_preparation_status"] == "status_rejected"
    assert summary["preparation_tool_calls"] == 1
    assert summary["planner_calls"] == 0
    assert summary["worker_calls"] == 0
    assert summary["execution_tool_calls"] == 0
    assert len(dispatcher.calls) == 1
    rows = [json.loads(line) for line in bytes(stream.content).splitlines()]
    assert [row["event"] for row in rows] == ["run_started", "tool_request"]
    assert "PREPARATION_SENTINEL" not in json.dumps(summary)


def test_live_trace_close_failure_preserves_run_finished_and_native_status(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    stream = _TraceStream(fail_close=True)
    _patch_main_recorder(monkeypatch, tmp_path, stream)
    _patch_complete_live_main(monkeypatch)

    exit_code, summary = _invoke_main(capsys, ["--execute-live"])

    assert exit_code == 1
    assert summary["operator_status"] == "failed"
    assert summary["operator_reason"] == "trace_write_failed"
    assert summary["document_preparation_status"] == "fresh_document_verified"
    assert summary["planner_calls"] == 1
    assert summary["worker_calls"] == 1
    assert summary["execution_tool_calls"] == 1
    assert summary["terminal_stage"] == "terminal"
    assert summary["terminal_reason"] == "terminal_node_selected:done"
    rows = [json.loads(line) for line in bytes(stream.content).splitlines()]
    assert rows[-1]["event"] == "run_finished"
    assert stream.close_calls == 1


def test_live_run_finished_write_failure_never_claims_trace_completion(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    stream = _EventFailTraceStream(fail_write_event="run_finished")
    _patch_main_recorder(monkeypatch, tmp_path, stream)
    _patch_complete_live_main(monkeypatch)

    exit_code, summary = _invoke_main(capsys, ["--execute-live"])

    assert exit_code == 1
    assert summary["operator_reason"] == "trace_write_failed"
    assert summary["terminal_stage"] == "terminal"
    assert summary["planner_calls"] == 1
    assert summary["worker_calls"] == 1
    assert summary["execution_tool_calls"] == 1
    rows = [json.loads(line) for line in bytes(stream.content).splitlines()]
    assert all(row["event"] != "run_finished" for row in rows)
    assert stream.close_calls == 1


def test_live_run_finished_flush_failure_closes_once_without_success(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    stream = _EventFailTraceStream(fail_flush_event="run_finished")
    recorder = _patch_main_recorder(monkeypatch, tmp_path, stream)
    _patch_complete_live_main(monkeypatch)

    exit_code, summary = _invoke_main(capsys, ["--execute-live"])

    assert exit_code == 1
    assert summary["operator_status"] == "failed"
    assert summary["operator_reason"] == "trace_write_failed"
    assert summary["terminal_stage"] == "terminal"
    assert summary["planner_calls"] == 1
    assert summary["worker_calls"] == 1
    assert summary["execution_tool_calls"] == 1
    assert recorder.sequence == stream.flush_calls - 1
    assert stream.close_calls == 1


@pytest.mark.parametrize(
    ("planner", "worker", "reason"),
    [
        (object(), "ollama_chat/qwen3-coder:30b-a3b-q8_0", "profile_identity_invalid"),
        ("anthropic/claude-opus-4-6", object(), "profile_identity_invalid"),
        ("anthropic/claude-sonnet", "ollama_chat/qwen3-coder:30b-a3b-q8_0", "profile_role_mismatch"),
        ("anthropic/claude-opus-4-6", "ollama_chat/other", "profile_role_mismatch"),
    ],
)
def test_profile_refusal_precedes_discovery_and_transport_construction(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    planner: object,
    worker: object,
    reason: str,
) -> None:
    monkeypatch.setattr(SMOKE, "get_models", lambda _profile: _models(planner, worker))
    monkeypatch.setattr(SMOKE, "discover_instances", _fail_if_reached)
    monkeypatch.setattr(SMOKE, "ToolDispatcher", _fail_if_reached)
    monkeypatch.setattr(SMOKE, "LiteLLMWorkerTransport", _fail_if_reached)

    exit_code, summary = _invoke_main(capsys, ["--execute-live"])

    assert exit_code == 1
    assert summary["operator_status"] == "refused"
    assert summary["operator_reason"] == reason
    assert summary["document_preparation_status"] == "not_started"
    assert summary["planner_calls"] == 0
    assert summary["worker_calls"] == 0


def test_profile_load_exception_is_safe_and_precedes_discovery(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def raise_profile(_profile: str) -> None:
        raise RuntimeError("PROFILE_LOAD_SENTINEL")

    monkeypatch.setattr(SMOKE, "get_models", raise_profile)
    monkeypatch.setattr(SMOKE, "discover_instances", _fail_if_reached)
    monkeypatch.setattr(SMOKE, "ToolDispatcher", _fail_if_reached)
    monkeypatch.setattr(SMOKE, "LiteLLMWorkerTransport", _fail_if_reached)

    exit_code, summary = _invoke_main(capsys, ["--execute-live"])

    assert exit_code == 1
    assert summary["operator_status"] == "failed"
    assert summary["operator_reason"] == "operator_internal_error"
    assert "PROFILE_LOAD_SENTINEL" not in json.dumps(summary)
    assert summary["document_preparation_status"] == "not_started"
    assert summary["preparation_tool_calls"] == 0
    assert summary["planner_calls"] == 0
    assert summary["worker_calls"] == 0
    assert summary["execution_tool_calls"] == 0


@pytest.mark.parametrize(
    ("rows", "reason"),
    [
        ([], "rooknative_instance_absent"),
        ([{"pluginType": "roadcreator", "processId": 1, "port": 2}], "rooknative_instance_absent"),
        ([_native_row(), _native_row(process_id=4002, port=9878)], "rooknative_instance_ambiguous"),
        (
            [{"pluginType": "native", "port": 9877}],
            "rooknative_identity_invalid",
        ),
        ([_native_row(process_id=True)], "rooknative_identity_invalid"),
        ([_native_row(process_id=0)], "rooknative_identity_invalid"),
        ([_native_row(process_id=-1)], "rooknative_identity_invalid"),
        ([_native_row(process_id="4001")], "rooknative_identity_invalid"),
        ([_native_row(process_id=_EqualitySpoof())], "rooknative_identity_invalid"),
        (
            [{"pluginType": "native", "processId": 4001}],
            "rooknative_identity_invalid",
        ),
        ([_native_row(port=True)], "rooknative_identity_invalid"),
        ([_native_row(port=0)], "rooknative_identity_invalid"),
        ([_native_row(port=-1)], "rooknative_identity_invalid"),
        ([_native_row(port="9877")], "rooknative_identity_invalid"),
        ([_native_row(port=_EqualitySpoof())], "rooknative_identity_invalid"),
    ],
)
def test_discovery_refusal_precedes_dispatcher_and_models(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    rows: list[dict[str, object]],
    reason: str,
) -> None:
    monkeypatch.setattr(SMOKE, "get_models", lambda _profile: _models())
    monkeypatch.setattr(SMOKE, "discover_instances", lambda: copy.deepcopy(rows))
    monkeypatch.setattr(SMOKE, "ToolDispatcher", _fail_if_reached)
    monkeypatch.setattr(SMOKE, "LiteLLMWorkerTransport", _fail_if_reached)

    exit_code, summary = _invoke_main(capsys, ["--execute-live"])

    assert exit_code == 1
    assert summary["operator_status"] == "refused"
    assert summary["operator_reason"] == reason
    assert summary["document_preparation_status"] == "not_started"
    assert summary["planner_calls"] == 0
    assert summary["worker_calls"] == 0
    trace_path = Path(summary["trace_path"])
    rows = [json.loads(line) for line in trace_path.read_bytes().splitlines()]
    assert [row["event"] for row in rows] == ["run_started", "run_finished"]


def test_discovery_freezes_the_only_exact_native_identity() -> None:
    assert SMOKE._resolve_single_rhino_target(
        [
            {"pluginType": "roadcreator", "processId": 99, "port": 9999},
            _native_row(),
        ]
    ) == SMOKE._ResolvedRhinoTarget(process_id=4001, port=9877)


def test_equality_spoof_plugin_type_does_not_become_native() -> None:
    with pytest.raises(SMOKE._TargetRefusal) as caught:
        SMOKE._resolve_single_rhino_target(
            [{"pluginType": _EqualitySpoof(), "processId": 4001, "port": 9877}]
        )
    assert caught.value.reason == "rooknative_instance_absent"


_STATUS_MUTATIONS = (
    "result_subclass",
    "result_not_dict",
    "success_missing",
    "success_false",
    "success_spoof",
    "data_missing",
    "data_subclass",
    "data_not_dict",
    "available_missing",
    "available_false",
    "available_spoof",
    "ready_missing",
    "ready_false",
    "ready_spoof",
    "active_missing",
    "active_false",
    "active_spoof",
    "document_id_missing",
    "document_id_empty",
    "document_id_spaces",
    "document_id_whitespace",
    "document_id_not_string",
    "document_id_spoof",
    "object_count_missing",
    "object_count_false",
    "object_count_true",
    "object_count_negative",
    "object_count_positive",
    "object_count_float",
    "object_count_string",
    "object_count_spoof",
    "document_path_missing",
    "document_path_not_string",
    "document_path_saved",
    "document_path_spoof",
)


def _mutated_status(case: str, document_id: str) -> object:
    row = _status(document_id)
    if case == "result_subclass":
        return _DictSubclass(row)
    if case == "result_not_dict":
        return []
    if case == "success_missing":
        row.pop("success")
    elif case == "success_false":
        row["success"] = False
    elif case == "success_spoof":
        row["success"] = _EqualitySpoof()
    elif case == "data_missing":
        row.pop("data")
    elif case == "data_subclass":
        row["data"] = _DictSubclass(row["data"])
    elif case == "data_not_dict":
        row["data"] = []
    else:
        data = row["data"]
        assert type(data) is dict
        mutations: dict[str, tuple[str, object]] = {
            "available_missing": ("available", None),
            "available_false": ("available", False),
            "available_spoof": ("available", _EqualitySpoof()),
            "ready_missing": ("ready_for_edit", None),
            "ready_false": ("ready_for_edit", False),
            "ready_spoof": ("ready_for_edit", _EqualitySpoof()),
            "active_missing": ("has_active_document", None),
            "active_false": ("has_active_document", False),
            "active_spoof": ("has_active_document", _EqualitySpoof()),
            "document_id_missing": ("document_id", None),
            "document_id_empty": ("document_id", ""),
            "document_id_spaces": ("document_id", "   "),
            "document_id_whitespace": ("document_id", "\t\r\n"),
            "document_id_not_string": ("document_id", 7),
            "document_id_spoof": ("document_id", _EqualitySpoof()),
            "object_count_missing": ("object_count", None),
            "object_count_false": ("object_count", False),
            "object_count_true": ("object_count", True),
            "object_count_negative": ("object_count", -1),
            "object_count_positive": ("object_count", 1),
            "object_count_float": ("object_count", 0.0),
            "object_count_string": ("object_count", "0"),
            "object_count_spoof": ("object_count", _EqualitySpoof()),
            "document_path_missing": ("document_path", None),
            "document_path_not_string": ("document_path", 7),
            "document_path_saved": ("document_path", "C:/saved.gh"),
            "document_path_spoof": ("document_path", _EqualitySpoof()),
        }
        key, value = mutations[case]
        if case.endswith("_missing"):
            data.pop(key)
        else:
            data[key] = value
    return row


def _patch_dispatcher_prefix(
    monkeypatch: pytest.MonkeyPatch,
    dispatcher: _SequenceDispatcher,
) -> list[dict[str, Any]]:
    model_constructions: list[dict[str, Any]] = []

    def make_model(**kwargs: Any) -> None:
        model_constructions.append(copy.deepcopy(kwargs))
        raise AssertionError("model construction reached")

    monkeypatch.setattr(
        SMOKE,
        "ToolDispatcher",
        lambda *, port, local_tools: dispatcher,
    )
    monkeypatch.setattr(SMOKE, "build_local_tools", lambda: {})
    monkeypatch.setattr(SMOKE, "LiteLLMWorkerTransport", make_model)
    return model_constructions


@pytest.mark.parametrize("case", _STATUS_MUTATIONS)
def test_status_equations_reject_every_closed_mutation(case: str) -> None:
    with pytest.raises(ValueError, match="status"):
        SMOKE._require_status(
            _mutated_status(case, _PRE_DOCUMENT_ID),
            previous_document_id=None,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["pre", "post"])
@pytest.mark.parametrize(
    "case",
    [case for case in _STATUS_MUTATIONS if not case.endswith("_spoof")],
)
async def test_status_equations_refuse_before_model_construction(
    monkeypatch: pytest.MonkeyPatch,
    phase: str,
    case: str,
) -> None:
    responses = (
        [_mutated_status(case, _PRE_DOCUMENT_ID)]
        if phase == "pre"
        else [
            _status(_PRE_DOCUMENT_ID),
            {"success": True, "data": {"created": True}},
            _mutated_status(case, _POST_DOCUMENT_ID),
        ]
    )
    dispatcher = _SequenceDispatcher(responses)
    model_constructions = _patch_dispatcher_prefix(monkeypatch, dispatcher)
    recorder, call_counts, _stream = _in_memory_trace()

    with pytest.raises(SMOKE._PreparationFailure) as caught:
        await SMOKE._run_live_once(
            SMOKE._ResolvedRoles(
                profile="hybrid",
                planner_model="anthropic/claude-opus-4-6",
                worker_model="ollama_chat/qwen3-coder:30b-a3b-q8_0",
                profile_api_base=None,
            ),
            SMOKE._ResolvedRhinoTarget(process_id=4001, port=9877),
            recorder=recorder,
            call_counts=call_counts,
        )

    expected_calls = 1 if phase == "pre" else 3
    expected_state = "status_rejected" if phase == "pre" else "document_new_started"
    assert caught.value.state == expected_state
    assert caught.value.tool_calls == expected_calls
    assert len(dispatcher.calls) == expected_calls
    assert model_constructions == []


@pytest.mark.asyncio
async def test_post_status_requires_a_different_document_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dispatcher = _SequenceDispatcher(
        [
            _status(_PRE_DOCUMENT_ID),
            {"success": True, "data": {"created": True}},
            _status(_PRE_DOCUMENT_ID),
        ]
    )
    model_constructions = _patch_dispatcher_prefix(monkeypatch, dispatcher)
    recorder, call_counts, _stream = _in_memory_trace()

    with pytest.raises(SMOKE._PreparationFailure) as caught:
        await SMOKE._run_live_once(
            SMOKE._ResolvedRoles(
                profile="hybrid",
                planner_model="anthropic/claude-opus-4-6",
                worker_model="ollama_chat/qwen3-coder:30b-a3b-q8_0",
                profile_api_base=None,
            ),
            SMOKE._ResolvedRhinoTarget(process_id=4001, port=9877),
            recorder=recorder,
            call_counts=call_counts,
        )

    assert caught.value.reason == "post_status_rejected"
    assert caught.value.state == "document_new_started"
    assert caught.value.tool_calls == 3
    assert model_constructions == []


_DOCUMENT_NEW_MUTATIONS = (
    "result_subclass",
    "result_not_dict",
    "success_missing",
    "success_false",
    "success_spoof",
    "data_missing",
    "data_subclass",
    "data_not_dict",
    "created_missing",
    "created_false",
    "created_spoof",
    "created_legacy_uppercase_only",
)


def test_document_new_accepts_actual_camel_case_wire_contract() -> None:
    SMOKE._require_document_new(
        {"success": True, "data": {"created": True}}
    )


def _mutated_document_new(case: str) -> object:
    row: dict[str, Any] = {"success": True, "data": {"created": True}}
    if case == "result_subclass":
        return _DictSubclass(row)
    if case == "result_not_dict":
        return []
    if case == "success_missing":
        row.pop("success")
    elif case == "success_false":
        row["success"] = False
    elif case == "success_spoof":
        row["success"] = _EqualitySpoof()
    elif case == "data_missing":
        row.pop("data")
    elif case == "data_subclass":
        row["data"] = _DictSubclass(row["data"])
    elif case == "data_not_dict":
        row["data"] = []
    else:
        data = row["data"]
        assert type(data) is dict
        if case == "created_missing":
            data.pop("created")
        elif case == "created_false":
            data["created"] = False
        elif case == "created_spoof":
            data["created"] = _EqualitySpoof()
        elif case == "created_legacy_uppercase_only":
            data["Created"] = data.pop("created")
        else:
            raise AssertionError(f"unknown document-new mutation: {case}")
    return row


@pytest.mark.parametrize("case", _DOCUMENT_NEW_MUTATIONS)
def test_document_new_equations_reject_every_closed_mutation(case: str) -> None:
    with pytest.raises(ValueError, match="document new"):
        SMOKE._require_document_new(_mutated_document_new(case))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [case for case in _DOCUMENT_NEW_MUTATIONS if not case.endswith("_spoof")],
)
async def test_document_new_equations_preserve_mutation_truth(
    monkeypatch: pytest.MonkeyPatch,
    case: str,
) -> None:
    dispatcher = _SequenceDispatcher(
        [_status(_PRE_DOCUMENT_ID), _mutated_document_new(case)]
    )
    model_constructions = _patch_dispatcher_prefix(monkeypatch, dispatcher)
    recorder, call_counts, _stream = _in_memory_trace()

    with pytest.raises(SMOKE._PreparationFailure) as caught:
        await SMOKE._run_live_once(
            SMOKE._ResolvedRoles(
                profile="hybrid",
                planner_model="anthropic/claude-opus-4-6",
                worker_model="ollama_chat/qwen3-coder:30b-a3b-q8_0",
                profile_api_base=None,
            ),
            SMOKE._ResolvedRhinoTarget(process_id=4001, port=9877),
            recorder=recorder,
            call_counts=call_counts,
        )

    assert caught.value.reason == "document_new_rejected"
    assert caught.value.state == "document_new_started"
    assert caught.value.tool_calls == 2
    assert len(dispatcher.calls) == 2
    assert model_constructions == []


def _patch_main_preparation(
    monkeypatch: pytest.MonkeyPatch,
    dispatcher: _SequenceDispatcher,
) -> list[dict[str, Any]]:
    monkeypatch.setattr(SMOKE, "get_models", lambda _profile: _models())
    monkeypatch.setattr(SMOKE, "discover_instances", lambda: [_native_row()])
    return _patch_dispatcher_prefix(monkeypatch, dispatcher)


@pytest.mark.parametrize("exception_type", [RuntimeError, TimeoutError])
@pytest.mark.parametrize(
    ("locus", "expected_reason", "expected_state", "expected_calls"),
    [
        ("pre", "pre_status_exception", "status_rejected", 1),
        (
            "document_new",
            "document_new_exception",
            "document_new_started",
            2,
        ),
        ("post", "post_status_exception", "document_new_started", 3),
    ],
)
def test_preparation_exceptions_are_bounded_and_construct_no_models(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    exception_type: type[Exception],
    locus: str,
    expected_reason: str,
    expected_state: str,
    expected_calls: int,
) -> None:
    failure = exception_type("PREPARATION_SENTINEL")
    responses_by_locus = {
        "pre": [failure],
        "document_new": [_status(_PRE_DOCUMENT_ID), failure],
        "post": [
            _status(_PRE_DOCUMENT_ID),
            {"success": True, "data": {"created": True}},
            failure,
        ],
    }
    dispatcher = _SequenceDispatcher(responses_by_locus[locus])
    model_constructions = _patch_main_preparation(monkeypatch, dispatcher)

    exit_code, summary = _invoke_main(capsys, ["--execute-live"])

    assert exit_code == 1
    assert summary["operator_status"] == "preparation_failed"
    assert summary["operator_reason"] == expected_reason
    assert summary["document_preparation_status"] == expected_state
    assert summary["preparation_tool_calls"] == expected_calls
    assert summary["planner_calls"] == 0
    assert summary["worker_calls"] == 0
    assert summary["execution_tool_calls"] == 0
    assert "PREPARATION_SENTINEL" not in json.dumps(summary)
    assert len(dispatcher.calls) == expected_calls
    assert model_constructions == []
    trace_path = Path(summary["trace_path"])
    rows = [json.loads(line) for line in trace_path.read_bytes().splitlines()]
    assert rows[-1]["event"] == "run_finished"


@pytest.mark.parametrize(
    "locus",
    ["first_transport", "second_transport", "planner_adapter", "integration"],
)
def test_post_preparation_exception_retains_verified_document_state(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    locus: str,
) -> None:
    dispatcher = _SequenceDispatcher(
        [
            _status(_PRE_DOCUMENT_ID),
            {"success": True, "data": {"created": True}},
            _status(_POST_DOCUMENT_ID),
        ]
    )
    monkeypatch.setattr(SMOKE, "get_models", lambda _profile: _models())
    monkeypatch.setattr(SMOKE, "discover_instances", lambda: [_native_row()])
    monkeypatch.setattr(
        SMOKE,
        "ToolDispatcher",
        lambda *, port, local_tools: dispatcher,
    )
    monkeypatch.setattr(SMOKE, "build_local_tools", lambda: {})
    transports = [_RawTransport(_planner_payload()), _RawTransport(_worker_payload())]
    constructor_calls: list[dict[str, Any]] = []

    def make_transport(**kwargs: Any) -> _RawTransport:
        constructor_calls.append(copy.deepcopy(kwargs))
        index = len(constructor_calls)
        if locus == "first_transport" and index == 1:
            raise RuntimeError("POST_PREPARATION_SENTINEL")
        if locus == "second_transport" and index == 2:
            raise RuntimeError("POST_PREPARATION_SENTINEL")
        return transports[index - 1]

    monkeypatch.setattr(SMOKE, "LiteLLMWorkerTransport", make_transport)
    if locus == "planner_adapter":
        monkeypatch.setattr(
            SMOKE,
            "MinimalPlannerDraftAdapter",
            lambda _transport: (_ for _ in ()).throw(
                RuntimeError("POST_PREPARATION_SENTINEL")
            ),
        )
    if locus == "integration":
        async def raise_integration(*_args: Any, **_kwargs: Any) -> None:
            raise RuntimeError("POST_PREPARATION_SENTINEL")

        monkeypatch.setattr(
            SMOKE,
            "run_minimal_intent_worker_initial_body_integration",
            raise_integration,
        )

    exit_code, summary = _invoke_main(capsys, ["--execute-live"])

    assert exit_code == 1
    assert summary["operator_status"] == "failed"
    assert summary["operator_reason"] == "operator_internal_error"
    assert summary["rooknative_process_id"] == 4001
    assert summary["rooknative_port"] == 9877
    assert summary["document_preparation_status"] == "fresh_document_verified"
    assert summary["preparation_tool_calls"] == 3
    assert summary["planner_calls"] == 0
    assert summary["worker_calls"] == 0
    assert summary["execution_tool_calls"] == 0
    assert summary["terminal_stage"] is None
    assert summary["terminal_reason"] is None
    assert summary["planner_adapter_status"] is None
    assert summary["worker_adapter_status"] is None
    assert "POST_PREPARATION_SENTINEL" not in json.dumps(summary)
    assert len(dispatcher.calls) == 3
    trace_rows = [
        json.loads(line)
        for line in Path(summary["trace_path"]).read_bytes().splitlines()
    ]
    traced_events = [row["event"] for row in trace_rows]
    assert ("handoff_raised" in traced_events) is (locus == "integration")
    assert "planner_admission" not in traced_events
    assert "compiled_workflow" not in traced_events
    assert "native_step_projection" not in traced_events
    assert "final_native_result" not in traced_events
    if locus == "integration":
        handoff_row = next(
            row for row in trace_rows if row["event"] == "handoff_raised"
        )
        assert handoff_row["payload"] == {
            "phase": "integration",
            "exception_type": "RuntimeError",
            "exception_message": "POST_PREPARATION_SENTINEL",
        }
    assert trace_rows[-1]["event"] == "run_finished"


class _RecordingDispatch:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.fail_if_called = False

    async def __call__(
        self,
        name: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        if self.fail_if_called:
            raise AssertionError("rejected tool call reached dispatcher")
        self.calls.append((name, copy.deepcopy(params)))
        return {}


def _roles() -> Any:
    return SMOKE._ResolvedRoles(
        profile="hybrid",
        planner_model="anthropic/claude-opus-4-6",
        worker_model="ollama_chat/qwen3-coder:30b-a3b-q8_0",
        profile_api_base=None,
    )


async def _run_scripted_worker(
    monkeypatch: pytest.MonkeyPatch,
    worker_payload: Mapping[str, Any],
    *,
    planner_payload: Mapping[str, Any] | None = None,
    dispatcher_type: type[Any] = _ScriptedDispatcher,
) -> Any:
    monkeypatch.setattr(SMOKE, "ToolDispatcher", dispatcher_type)
    monkeypatch.setattr(
        SMOKE,
        "build_local_tools",
        lambda: {
            "gh_create_csharp_script": object(),
            "gh_update_script": object(),
        },
    )
    transports = iter(
        (
            _RawTransport(
                _planner_payload() if planner_payload is None else planner_payload
            ),
            _RawTransport(worker_payload),
        )
    )
    monkeypatch.setattr(
        SMOKE,
        "LiteLLMWorkerTransport",
        lambda **_kwargs: next(transports),
    )
    recorder, call_counts, _stream = _in_memory_trace()
    return await SMOKE._run_live_once(
        _roles(),
        SMOKE._ResolvedRhinoTarget(process_id=4001, port=9877),
        recorder=recorder,
        call_counts=call_counts,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("prefix_length", [0, 1])
async def test_restricted_executor_accepts_each_legitimate_prefix(
    prefix_length: int,
) -> None:
    dispatch = _RecordingDispatch()
    executor = SMOKE._RestrictedRealToolExecutor(dispatch)
    calls = [("gh_create_csharp_script", {"create": "parameters"})]

    for name, params in calls[:prefix_length]:
        await executor(name, params)

    assert executor.call_names == tuple(name for name, _params in calls[:prefix_length])
    assert dispatch.calls == calls[:prefix_length]


@pytest.mark.asyncio
async def test_restricted_executor_rejects_update_after_create_before_dispatch() -> None:
    dispatch = _RecordingDispatch()
    executor = SMOKE._RestrictedRealToolExecutor(dispatch)
    await executor("gh_create_csharp_script", {"accepted": "create"})
    before_calls = copy.deepcopy(dispatch.calls)
    dispatch.fail_if_called = True

    with pytest.raises(ValueError, match="restricted tool sequence differs"):
        await executor("gh_update_script", {"code": "A = 1.0;"})

    assert executor.call_names == ("gh_create_csharp_script",)
    assert dispatch.calls == before_calls


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("prefix", "attempted_tool"),
    [
        ((), "gh_update_script"),
        (("gh_create_csharp_script",), "gh_create_csharp_script"),
        (("gh_create_csharp_script",), "gh_update_script"),
        ((), "gh_status"),
        (("gh_create_csharp_script",), "gh_status"),
    ],
)
async def test_restricted_executor_rejects_sequence_changes_without_mutation(
    prefix: tuple[str, ...],
    attempted_tool: str,
) -> None:
    dispatch = _RecordingDispatch()
    executor = SMOKE._RestrictedRealToolExecutor(dispatch)
    for name in prefix:
        await executor(name, {"accepted": name})
    before_executor = executor.call_names
    before_dispatch = copy.deepcopy(dispatch.calls)
    dispatch.fail_if_called = True

    with pytest.raises(ValueError, match="restricted tool sequence differs"):
        await executor(attempted_tool, {"rejected": attempted_tool})

    assert executor.call_names == before_executor
    assert dispatch.calls == before_dispatch


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name", ["gh_create_csharp_script", "gh_update_script"])
@pytest.mark.parametrize("port_value", [12345, None, 0, object()])
async def test_per_call_port_override_never_reaches_dispatcher(
    tool_name: str,
    port_value: object,
) -> None:
    dispatch = _RecordingDispatch()
    executor = SMOKE._RestrictedRealToolExecutor(dispatch)
    if tool_name == "gh_update_script":
        await executor("gh_create_csharp_script", {"accepted": "create"})
    before_executor = executor.call_names
    before_dispatch = copy.deepcopy(dispatch.calls)
    dispatch.fail_if_called = True

    with pytest.raises(ValueError, match="parameters contain port"):
        await executor(tool_name, {"port": port_value})

    assert executor.call_names == before_executor
    assert dispatch.calls == before_dispatch


@pytest.mark.asyncio
async def test_worker_refusal_stops_before_create(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    live_run = await _run_scripted_worker(
        monkeypatch,
        {
            "schema": "rook.local_worker_turn_response:v1",
            "kind": "refusal",
            "category": "insufficient_context",
            "reason": "An initial body cannot be authored.",
        },
    )

    summary = SMOKE._summary_from_result(_roles(), live_run)

    assert live_run.executor.call_names == ()
    assert live_run.result.terminal_stage == "worker_disposition"
    assert summary["operator_status"] == "failed"
    assert summary["operator_reason"] == "native_stop"
    assert summary["execution_tool_calls"] == 0
    assert summary["terminal_reason"] == "refusal_recorded"


@pytest.mark.asyncio
@pytest.mark.parametrize("prefix_length", [0])
async def test_native_terminal_requires_the_complete_executor_prefix(
    monkeypatch: pytest.MonkeyPatch,
    prefix_length: int,
) -> None:
    terminal_run = await _run_scripted_worker(monkeypatch, _worker_payload())
    dispatch = _RecordingDispatch()
    executor = SMOKE._RestrictedRealToolExecutor(dispatch)
    mismatched_run = SMOKE._LiveRun(
        result=terminal_run.result,
        target=terminal_run.target,
        preparation=terminal_run.preparation,
        executor=executor,
    )

    with pytest.raises(RuntimeError, match="executor prefix differs"):
        SMOKE._summary_from_result(_roles(), mismatched_run)


def test_operator_summary_field_order_is_closed() -> None:
    assert SMOKE._SUMMARY_FIELDS == (
        "operator_status",
        "operator_reason",
        "trace_path",
        "intent",
        "profile",
        "planner_model",
        "worker_model",
        "rooknative_process_id",
        "rooknative_port",
        "document_preparation_status",
        "preparation_tool_calls",
        "planner_calls",
        "worker_calls",
        "execution_tool_calls",
        "terminal_stage",
        "terminal_reason",
        "planner_adapter_status",
        "worker_adapter_status",
    )


@pytest.mark.parametrize(
    ("reason", "expected"),
    [
        ("terminal_node_selected:done", "terminal_node_selected:done"),
        ("refusal_recorded", "refusal_recorded"),
        (
            "response_payload_invalid:SENSITIVE_SENTINEL",
            "worker_response_payload_invalid",
        ),
        ("SENSITIVE_SENTINEL", "native_reason_unclassified"),
        (object(), "native_reason_unclassified"),
    ],
)
def test_terminal_reason_projection_is_closed_and_bounded(
    reason: object,
    expected: str,
) -> None:
    projected = SMOKE._project_terminal_reason(reason)

    assert projected == expected
    assert "SENSITIVE_SENTINEL" not in projected


@pytest.mark.asyncio
async def test_malformed_worker_content_is_reduced_to_a_safe_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    malformed = _worker_payload()
    malformed["SENSITIVE_SENTINEL"] = "untrusted worker content"
    live_run = await _run_scripted_worker(monkeypatch, malformed)

    summary = SMOKE._summary_from_result(_roles(), live_run)
    serialized = json.dumps(summary, ensure_ascii=True, separators=(",", ":"))

    assert summary["operator_status"] == "failed"
    assert summary["terminal_reason"] == "worker_response_payload_invalid"
    assert "SENSITIVE_SENTINEL" not in serialized
    assert "untrusted worker content" not in serialized


@pytest.mark.asyncio
async def test_planner_response_content_is_not_exported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    malformed = _planner_payload()
    malformed["SENSITIVE_SENTINEL"] = "untrusted Planner content"
    live_run = await _run_scripted_worker(
        monkeypatch,
        _worker_payload(),
        planner_payload=malformed,
    )

    summary = SMOKE._summary_from_result(_roles(), live_run)
    serialized = json.dumps(summary, ensure_ascii=True, separators=(",", ":"))

    assert live_run.executor.call_names == ()
    assert summary["terminal_reason"] == "draft_payload_rejected"
    assert "SENSITIVE_SENTINEL" not in serialized
    assert "untrusted Planner content" not in serialized


def test_summary_emission_refuses_additional_fields(
    capsys: pytest.CaptureFixture[str],
) -> None:
    summary = SMOKE._bounded_summary(
        operator_status="refused",
        operator_reason="live_execution_not_requested",
    )
    summary["SENSITIVE_SENTINEL"] = "untrusted"

    with pytest.raises(RuntimeError, match="summary fields differ"):
        SMOKE._emit_summary(summary)

    assert capsys.readouterr().out == ""


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "worker_payload",
    [
        {
            **_worker_payload(),
            "rationale": "SENSITIVE_SENTINEL worker rationale",
        },
        _worker_payload("SENSITIVE_SENTINEL worker code"),
    ],
)
async def test_worker_rationale_and_code_do_not_enter_the_summary(
    monkeypatch: pytest.MonkeyPatch,
    worker_payload: Mapping[str, Any],
) -> None:
    live_run = await _run_scripted_worker(monkeypatch, worker_payload)

    serialized = json.dumps(
        SMOKE._summary_from_result(_roles(), live_run),
        ensure_ascii=True,
        separators=(",", ":"),
    )

    assert "SENSITIVE_SENTINEL" not in serialized


def test_discovery_metadata_does_not_enter_the_summary(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(SMOKE, "get_models", lambda _profile: _models())
    monkeypatch.setattr(
        SMOKE,
        "discover_instances",
        lambda: [
            {
                **_native_row(),
                "metadata": "SENSITIVE_SENTINEL discovery metadata",
            }
        ],
    )

    async def fail_preparation(*_args: Any, **_kwargs: Any) -> None:
        raise SMOKE._PreparationFailure(
            "pre_status_rejected",
            "status_rejected",
            1,
        )

    monkeypatch.setattr(SMOKE, "_run_live_once", fail_preparation)

    _exit_code, summary = _invoke_main(capsys, ["--execute-live"])

    assert "SENSITIVE_SENTINEL" not in json.dumps(summary)


class _SensitiveReceiptDispatcher(_ScriptedDispatcher):
    async def dispatch(self, name: str, params: dict[str, Any]) -> dict[str, Any]:
        captured = copy.deepcopy(params)
        self.calls.append((name, captured))
        index = len(self.calls)
        if index == 1 and name == "gh_status" and captured == {}:
            return _status(_PRE_DOCUMENT_ID)
        if index == 2 and name == "gh_document_new" and captured == {}:
            return {"success": True, "data": {"created": True}}
        if index == 3 and name == "gh_status" and captured == {}:
            return _status(_POST_DOCUMENT_ID)
        if index == 4 and name == "gh_create_csharp_script":
            return {
                "success": True,
                "data": {
                    "script_receipt": {
                        "version": 1,
                        "operation": "create",
                        "language": "csharp",
                        "artifact_status": "usable",
                        "mutation": {
                            "status": "created",
                            "component_guid": "SENSITIVE_SENTINEL_GUID",
                        },
                        "verification": {
                            "status": "passed",
                            "target_error_count": 0,
                        },
                        "repair_anchor": {
                            "component_guid": "SENSITIVE_SENTINEL_GUID",
                            "language": "csharp",
                            "target_errors": [],
                        },
                    }
                },
            }
        raise AssertionError(f"unexpected sensitive dispatch {index}: {name}")


@pytest.mark.asyncio
async def test_receipt_guid_does_not_enter_the_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    live_run = await _run_scripted_worker(
        monkeypatch,
        _worker_payload(),
        dispatcher_type=_SensitiveReceiptDispatcher,
    )

    summary = SMOKE._summary_from_result(_roles(), live_run)
    serialized = json.dumps(summary, ensure_ascii=True, separators=(",", ":"))

    assert summary["operator_status"] == "completed"
    assert "SENSITIVE_SENTINEL" not in serialized


def test_final_projection_exception_returns_one_bounded_summary(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _patch_complete_live_main(monkeypatch)

    def raise_projection(_reason: object) -> str:
        raise RuntimeError("SENSITIVE_SENTINEL projection failure")

    monkeypatch.setattr(SMOKE, "_project_terminal_reason", raise_projection)

    exit_code, summary = _invoke_main(capsys, ["--execute-live"])

    assert exit_code == 1
    assert summary["operator_status"] == "failed"
    assert summary["operator_reason"] == "operator_internal_error"
    assert summary["rooknative_process_id"] == 4001
    assert summary["rooknative_port"] == 9877
    assert summary["document_preparation_status"] == "fresh_document_verified"
    assert summary["preparation_tool_calls"] == 3
    assert summary["planner_calls"] == 1
    assert summary["worker_calls"] == 1
    assert summary["execution_tool_calls"] == 1
    assert summary["terminal_stage"] is None
    assert summary["terminal_reason"] is None
    assert summary["planner_adapter_status"] is None
    assert summary["worker_adapter_status"] is None
    assert "SENSITIVE_SENTINEL" not in json.dumps(summary)
    trace_path = Path(summary["trace_path"])
    rows = [json.loads(line) for line in trace_path.read_bytes().splitlines()]
    assert rows[0]["event"] == "run_started"
    assert rows[-1]["event"] == "run_finished"
    assert rows[-1]["payload"]["preparation_tool_calls"] == 3
    assert rows[-1]["payload"]["planner_calls"] == 1
    assert rows[-1]["payload"]["worker_calls"] == 1
    assert rows[-1]["payload"]["execution_tool_calls"] == 1


@pytest.mark.asyncio
async def test_live_composition_materializes_exact_provider_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert (
        transport_module.litellm.supports_response_schema(
            model="anthropic/claude-opus-4-6"
        )
        is True
    )
    supported = transport_module.litellm.get_supported_openai_params(
        model="anthropic/claude-opus-4-6"
    )
    assert supported is not None
    assert "response_format" in supported

    real_transport_type = SMOKE.LiteLLMWorkerTransport
    planner_transport = _RawTransport(_planner_payload())
    worker_transport = _RawTransport(_worker_payload())
    fake_transports = iter((planner_transport, worker_transport))
    constructor_calls: list[dict[str, Any]] = []

    def capture_transport(**kwargs: Any) -> _RawTransport:
        constructor_calls.append(copy.deepcopy(kwargs))
        return next(fake_transports)

    created_dispatchers: list[_ScriptedDispatcher] = []

    def make_dispatcher(*, port: int, local_tools: dict[str, Any]) -> Any:
        dispatcher = _ScriptedDispatcher(port=port, local_tools=local_tools)
        created_dispatchers.append(dispatcher)
        return dispatcher

    monkeypatch.setattr(SMOKE, "LiteLLMWorkerTransport", capture_transport)
    monkeypatch.setattr(SMOKE, "ToolDispatcher", make_dispatcher)
    monkeypatch.setattr(
        SMOKE,
        "build_local_tools",
        lambda: {
            "gh_create_csharp_script": object(),
            "gh_update_script": object(),
        },
    )
    roles = SMOKE._ResolvedRoles(
        profile="hybrid",
        planner_model="anthropic/claude-opus-4-6",
        worker_model="ollama_chat/qwen3-coder:30b-a3b-q8_0",
        profile_api_base="http://localhost:11434/v1",
    )
    recorder, call_counts, _stream = _in_memory_trace()

    live_run = await SMOKE._run_live_once(
        roles,
        SMOKE._ResolvedRhinoTarget(process_id=4001, port=9877),
        recorder=recorder,
        call_counts=call_counts,
    )

    planner_kwargs = {
        "model": "anthropic/claude-opus-4-6",
        "profile_api_base": "http://localhost:11434/v1",
        "generation_params": {
            "temperature": 0,
            "max_tokens": 1024,
            "max_retries": 0,
            "response_format": SMOKE._planner_response_format(),
        },
        "structured_response_schema": None,
        "timeout_s": 120.0,
    }
    worker_kwargs = {
        "model": "ollama_chat/qwen3-coder:30b-a3b-q8_0",
        "profile_api_base": "http://localhost:11434/v1",
        "generation_params": {
            "temperature": 0,
            "max_tokens": 1024,
            "max_retries": 0,
        },
        "structured_response_schema": (
            SMOKE._local_worker_response_union_schema()
        ),
        "timeout_s": 120.0,
    }
    assert constructor_calls == [planner_kwargs, worker_kwargs]
    assert live_run.result.terminal_reason == "terminal_node_selected:done"
    assert len(created_dispatchers) == 1

    provider_calls: list[dict[str, Any]] = []

    def completion(**kwargs: Any) -> Any:
        provider_calls.append(copy.deepcopy(kwargs))
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="{}"))],
            usage=None,
        )

    monkeypatch.setattr(transport_module.litellm, "completion", completion)
    monkeypatch.setattr(
        transport_module.litellm,
        "completion_cost",
        lambda completion_response: None,
    )
    planner = real_transport_type(**planner_kwargs)
    worker = real_transport_type(**worker_kwargs)
    prompt = {"messages": [{"role": "user", "content": "fixed"}]}

    assert planner.send(prompt) == "{}"
    assert worker.send(prompt) == "{}"

    planner_call, worker_call = provider_calls
    assert planner_call["response_format"] == planner_kwargs["generation_params"][
        "response_format"
    ]
    assert "format" not in planner_call
    assert planner_call["max_tokens"] == 1024
    assert planner_call["max_retries"] == 0
    assert worker_call["format"] == worker_kwargs["structured_response_schema"]
    assert "response_format" not in worker_call
    assert worker_call["max_tokens"] == 1024
    assert worker_call["max_retries"] == 0


@pytest.mark.asyncio
@pytest.mark.filterwarnings(
    "ignore:The 'prefix' argument in InputField/OutputField is deprecated:"
    "DeprecationWarning"
)
async def test_dispatcher_construction_uses_the_existing_local_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    local_tools = SMOKE.build_local_tools()
    assert callable(local_tools["gh_create_csharp_script"])
    assert callable(local_tools["gh_update_script"])
    captured: list[tuple[int, dict[str, Any]]] = []

    def make_dispatcher(*, port: int, local_tools: dict[str, Any]) -> Any:
        captured.append((port, local_tools))
        return _ScriptedDispatcher(port=port, local_tools=local_tools)

    transports = iter(
        (_RawTransport(_planner_payload()), _RawTransport(_worker_payload()))
    )
    monkeypatch.setattr(SMOKE, "ToolDispatcher", make_dispatcher)
    monkeypatch.setattr(SMOKE, "build_local_tools", lambda: local_tools)
    monkeypatch.setattr(
        SMOKE,
        "LiteLLMWorkerTransport",
        lambda **_kwargs: next(transports),
    )
    recorder, call_counts, _stream = _in_memory_trace()

    live_run = await SMOKE._run_live_once(
        _roles(),
        SMOKE._ResolvedRhinoTarget(process_id=4001, port=9877),
        recorder=recorder,
        call_counts=call_counts,
    )

    assert live_run.result.terminal_reason == "terminal_node_selected:done"
    assert captured == [(9877, local_tools)]
    assert captured[0][1] is local_tools


@pytest.mark.parametrize(
    ("args", "expected_code", "expected_reason"),
    [
        ([], 0, "live_execution_not_requested"),
        (["--invalid-argument"], 1, "invalid_arguments"),
    ],
)
def test_operator_subprocess_refuses_without_live_contact(
    args: list[str],
    expected_code: int,
    expected_reason: str,
) -> None:
    completed = subprocess.run(
        [sys.executable, str(_SCRIPT), *args],
        cwd=_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == expected_code
    assert completed.stderr == ""
    lines = completed.stdout.splitlines()
    assert len(lines) == 1
    summary = json.loads(lines[0])
    assert summary["operator_status"] == "refused"
    assert summary["operator_reason"] == expected_reason
    assert summary["rooknative_process_id"] is None
    assert summary["rooknative_port"] is None
    assert summary["document_preparation_status"] == "not_started"
    assert summary["preparation_tool_calls"] == 0
    assert summary["planner_calls"] == 0
    assert summary["worker_calls"] == 0
    assert summary["execution_tool_calls"] == 0
