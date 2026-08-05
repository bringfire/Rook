"""No-contact tests for the private ChatRunner qualification operator."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import pytest


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
