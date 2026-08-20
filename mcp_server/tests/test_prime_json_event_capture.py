"""Causal tests for bounded Prime JSON event capture."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import queue
import sys
import threading
import time
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[2]
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


def approved_capture_config(*, mode: str = "compact") -> dict[str, Any]:
    return {
        "schema": "rook.prime_event_capture_config:v1",
        "mode": mode,
        "retainedPath": "operator/prime-events.compact.jsonl",
        "custodyPath": "operator/prime-event-capture-custody.json",
        "rawDebugPath": (
            "operator/prime-events.raw.jsonl"
            if mode == "compact_with_raw_debug"
            else None
        ),
    }


def assistant_message(blocks: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": copy.deepcopy(blocks),
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
    subtype: str,
    event_payload: dict[str, Any],
    blocks: list[dict[str, Any]],
    *,
    content_index: int = 0,
    root_extra: dict[str, Any] | None = None,
) -> bytes:
    message = assistant_message(blocks)
    value = {
        "type": "message_update",
        "message": message,
        "assistantMessageEvent": {
            "type": subtype,
            "contentIndex": content_index,
            **copy.deepcopy(event_payload),
            "partial": copy.deepcopy(message),
        },
    }
    if root_extra:
        value.update(root_extra)
    return canonical_test_line(value)


def text_block(text: str = "") -> dict[str, Any]:
    return {"type": "text", "text": text}


def thinking_block(thinking: str = "") -> dict[str, Any]:
    return {"type": "thinking", "thinking": thinking}


def tool_block(*, streaming: bool) -> dict[str, Any]:
    value: dict[str, Any] = {
        "type": "toolCall",
        "id": "call-1",
        "name": "ipython",
        "arguments": {} if streaming else {"code": "print(1)"},
        "thoughtSignature": "signed",
    }
    if streaming:
        value.update({"partialArgs": '{"code":', "streamIndex": 0})
    return value


def final_tool_call() -> dict[str, Any]:
    return tool_block(streaming=False)


def compact_value(result) -> dict[str, Any]:
    return json.loads(result.retained_bytes)


def test_capture_config_is_closed_and_operator_local(capture):
    compact = capture.validate_capture_config(approved_capture_config())
    assert compact.mode == "compact"
    assert compact.retained_path.as_posix() == "operator/prime-events.compact.jsonl"
    assert compact.custody_path.as_posix() == (
        "operator/prime-event-capture-custody.json"
    )
    assert compact.raw_debug_path is None

    debug = capture.validate_capture_config(
        approved_capture_config(mode="compact_with_raw_debug")
    )
    assert debug.mode == "compact_with_raw_debug"
    assert debug.raw_debug_path.as_posix() == "operator/prime-events.raw.jsonl"
    assert capture.validate_capture_config(None) is None


@pytest.mark.parametrize(
    "value",
    [
        True,
        [],
        {},
        approved_capture_config() | {"extra": True},
        approved_capture_config() | {"mode": "raw"},
        approved_capture_config() | {"retainedPath": "C:/escape.jsonl"},
        approved_capture_config() | {"retainedPath": "operator/../escape.jsonl"},
        approved_capture_config() | {"retainedPath": "prime.jsonl"},
        approved_capture_config() | {"rawDebugPath": "operator/raw.jsonl"},
        approved_capture_config(mode="compact_with_raw_debug")
        | {"rawDebugPath": None},
        approved_capture_config(mode="compact_with_raw_debug")
        | {"rawDebugPath": "operator/prime-events.compact.jsonl"},
        approved_capture_config() | {"maxSourceRowBytes": 1},
    ],
)
def test_capture_config_refuses_invalid_or_ambient_authority(capture, value):
    with pytest.raises(ValueError, match="capture_config_invalid"):
        capture.validate_capture_config(value)


@pytest.mark.parametrize(
    ("subtype", "event_payload", "block", "event_keys", "content_start"),
    [
        (
            "text_start",
            {},
            {"type": "text", "text": "seed", "textSignature": "sig"},
            {"type", "contentIndex"},
            {"type": "text", "text": "", "textSignature": "sig"},
        ),
        (
            "text_delta",
            {"delta": "next"},
            text_block("next"),
            {"type", "contentIndex", "delta"},
            None,
        ),
        (
            "text_end",
            {"content": "done"},
            text_block("done"),
            {"type", "contentIndex", "content"},
            None,
        ),
        (
            "thinking_start",
            {},
            {
                "type": "thinking",
                "thinking": "seed",
                "thinkingSignature": "sig",
                "redacted": False,
            },
            {"type", "contentIndex"},
            {
                "type": "thinking",
                "thinking": "",
                "thinkingSignature": "sig",
                "redacted": False,
            },
        ),
        (
            "thinking_delta",
            {"delta": "reason"},
            thinking_block("reason"),
            {"type", "contentIndex", "delta"},
            None,
        ),
        (
            "thinking_end",
            {"content": "done"},
            thinking_block("done"),
            {"type", "contentIndex", "content"},
            None,
        ),
        (
            "toolcall_start",
            {},
            tool_block(streaming=True),
            {"type", "contentIndex"},
            {
                "type": "toolCall",
                "id": "call-1",
                "name": "ipython",
                "arguments": {},
                "thoughtSignature": "signed",
            },
        ),
        (
            "toolcall_delta",
            {"delta": '{"code":'},
            tool_block(streaming=True),
            {"type", "contentIndex", "delta"},
            None,
        ),
        (
            "toolcall_end",
            {"toolCall": final_tool_call()},
            final_tool_call(),
            {"type", "contentIndex", "toolCall"},
            None,
        ),
    ],
)
def test_transform_emits_all_nine_closed_shapes(
    capture, subtype, event_payload, block, event_keys, content_start
):
    row = source_update_row(subtype, event_payload, [block])
    result = capture.transform_prime_row(row, 7)
    retained = compact_value(result)
    assert result.compacted is True
    assert result.raw_fallback_message_update is False
    assert result.parsed_event == json.loads(row)
    assert set(retained) == {
        "schema",
        "type",
        "sourceRow",
        "sourceBytes",
        "assistantMessageEvent",
    } | ({"contentStart"} if content_start is not None else set())
    assert retained["schema"] == "rook.prime_assistant_stream_delta:v1"
    assert retained["type"] == "assistant_stream_delta"
    assert retained["sourceRow"] == 7
    assert retained["sourceBytes"] == len(row)
    assert set(retained["assistantMessageEvent"]) == event_keys
    assert retained.get("contentStart") == content_start


@pytest.mark.parametrize("scratch", [{}, {"partialArgs": "x"}, {"streamIndex": 2}])
def test_tool_start_accepts_each_scratch_subset_and_omits_it(capture, scratch):
    block = {
        "type": "toolCall",
        "id": "call-1",
        "name": "ipython",
        "arguments": {},
        **scratch,
    }
    result = capture.transform_prime_row(
        source_update_row("toolcall_start", {}, [block]), 1
    )
    assert compact_value(result)["contentStart"] == {
        "type": "toolCall",
        "id": "call-1",
        "name": "ipython",
        "arguments": {},
    }


def test_nonassistant_and_unrecognized_valid_rows_fall_back_byte_exact(capture):
    unknown = source_update_row(
        "future_delta", {"delta": "x"}, [text_block("x")]
    )
    root_open = source_update_row(
        "text_delta", {"delta": "x"}, [text_block("x")], root_extra={"meta": 1}
    )
    wrong_role_value = json.loads(
        source_update_row("text_delta", {"delta": "x"}, [text_block("x")])
    )
    wrong_role_value["message"]["role"] = "user"
    wrong_role_value["assistantMessageEvent"]["partial"]["role"] = "user"
    wrong_role = canonical_test_line(wrong_role_value)
    for row in (unknown, root_open, wrong_role):
        result = capture.transform_prime_row(row, 1)
        assert result.retained_bytes == row
        assert result.compacted is False
        assert result.raw_fallback_message_update is True


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value["assistantMessageEvent"].update({"contentIndex": True}),
        lambda value: value["assistantMessageEvent"].update({"contentIndex": 4}),
        lambda value: value["assistantMessageEvent"].update({"extra": 1}),
        lambda value: value["assistantMessageEvent"]["partial"].update(
            {"timestamp": 2}
        ),
        lambda value: value["message"]["content"][0].update({"extra": 1}),
        lambda value: value["message"]["content"][0].update(
            {"type": "thinking", "thinking": "x"}
        ),
    ],
)
def test_nonexact_message_updates_take_visible_raw_fallback(capture, mutate):
    value = json.loads(
        source_update_row("text_delta", {"delta": "x"}, [text_block("x")])
    )
    mutate(value)
    row = canonical_test_line(value)
    result = capture.transform_prime_row(row, 1)
    assert result.retained_bytes == row
    assert result.raw_fallback_message_update is True


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value["message"]["content"][0].update(
            {"streamIndex": True}
        ),
        lambda value: value["assistantMessageEvent"]["toolCall"].update(
            {"partialArgs": "{}"}
        ),
    ],
)
def test_invalid_tool_scratch_or_final_shape_falls_back(capture, mutate):
    value = json.loads(
        source_update_row(
            "toolcall_end", {"toolCall": final_tool_call()}, [final_tool_call()]
        )
    )
    mutate(value)
    value["assistantMessageEvent"]["partial"] = copy.deepcopy(value["message"])
    row = canonical_test_line(value)
    result = capture.transform_prime_row(row, 1)
    assert result.retained_bytes == row
    assert result.raw_fallback_message_update is True


def test_nonupdate_event_passes_through_byte_exact(capture):
    row = b'{"future":true,"type":"new_prime_event"}\n'
    result = capture.transform_prime_row(row, 1)
    assert result.parsed_event == {"future": True, "type": "new_prime_event"}
    assert result.retained_bytes == row
    assert result.compacted is False
    assert result.raw_fallback_message_update is False


@pytest.mark.parametrize(
    ("row", "code"),
    [
        (b'{"type":"session"}', "stdout_missing_final_lf"),
        (b'[]\n', "stdout_json_object_required"),
        (b'{"type":"session","type":"duplicate"}\n', "stdout_json_duplicate_key"),
        (b'{"type":"session","value":NaN}\n', "stdout_json_invalid"),
        (b'{"type":\xff}\n', "stdout_invalid_utf8"),
    ],
)
def test_transform_refuses_malformed_source_rows(capture, row, code):
    with pytest.raises(capture.PrimeCaptureError) as caught:
        capture.transform_prime_row(row, 1)
    assert caught.value.code == code


def test_source_row_must_be_one_based(capture):
    with pytest.raises(capture.PrimeCaptureError) as caught:
        capture.transform_prime_row(b'{"type":"session"}\n', 0)
    assert caught.value.code == "compact_transform_failed"


def json_row_of_size(size: int, *, lf: bool = True) -> bytes:
    prefix, suffix = b'{"payload":"', b'"}'
    newline = b"\n" if lf else b""
    fill = size - len(prefix) - len(suffix) - len(newline)
    assert fill >= 0
    return prefix + (b"a" * fill) + suffix + newline


class RecordingBytesIO(io.BytesIO):
    def __init__(self, value: bytes):
        super().__init__(value)
        self.requested_sizes: list[int] = []

    def read(self, size: int = -1) -> bytes:
        self.requested_sizes.append(size)
        return super().read(size)


def test_exact_maximum_row_is_admitted_in_fixed_chunks(capture):
    row = json_row_of_size(capture.MAX_SOURCE_ROW_BYTES)
    stream = RecordingBytesIO(row)
    assert list(capture.iter_bounded_lf_rows(stream)) == [row]
    assert set(stream.requested_sizes) == {capture.SOURCE_READ_CHUNK_BYTES}


@pytest.mark.parametrize("terminated", [True, False])
def test_oversized_row_refuses_at_frozen_boundary(capture, terminated):
    row = json_row_of_size(capture.MAX_SOURCE_ROW_BYTES + 1, lf=terminated)
    stream = RecordingBytesIO(row)
    with pytest.raises(capture.PrimeCaptureError) as caught:
        list(capture.iter_bounded_lf_rows(stream))
    assert caught.value.code == "stdout_row_too_large"
    assert max(stream.requested_sizes) == capture.SOURCE_READ_CHUNK_BYTES


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


def text_delta_source_row(delta: str) -> bytes:
    return source_update_row("text_delta", {"delta": delta}, [text_block(delta)])


def capture_config(capture, *, mode: str = "compact"):
    return capture.validate_capture_config(approved_capture_config(mode=mode))


def test_complete_capture_writes_and_verifies_deterministic_custody(
    capture, tmp_path
):
    rows = [b'{"type":"session"}\n', text_delta_source_row("hello")]
    published: list[dict[str, Any]] = []
    custody = capture.capture_binary_stream(
        io.BytesIO(b"".join(rows)),
        config=capture_config(capture),
        row_root=tmp_path,
        publish=published.append,
    )
    retained = tmp_path / "operator" / "prime-events.compact.jsonl"
    custody_path = tmp_path / "operator" / "prime-event-capture-custody.json"
    assert custody == capture.verify_capture_custody(capture_config(capture), tmp_path)
    assert custody_path.read_bytes() == canonical_test_line(custody)
    assert custody["source"] == {
        "bytes": sum(map(len, rows)),
        "maxRowBytes": max(map(len, rows)),
        "rows": 2,
        "sha256": hashlib.sha256(b"".join(rows)).hexdigest().upper(),
        "stdoutEof": True,
    }
    assert custody["retained"]["rows"] == 2
    assert custody["retained"]["compactedMessageUpdates"] == 1
    assert custody["retained"]["rawFallbackMessageUpdates"] == 0
    assert custody["retained"]["bytes"] == retained.stat().st_size
    assert custody["rawDebug"] is None
    assert [event["type"] for event in published] == ["session", "message_update"]


def test_raw_debug_is_exact_and_bound_to_source(capture, tmp_path):
    rows = [b'{"type":"session"}\n', text_delta_source_row("hello")]
    config = capture_config(capture, mode="compact_with_raw_debug")
    custody = capture.capture_binary_stream(
        io.BytesIO(b"".join(rows)),
        config=config,
        row_root=tmp_path,
        publish=lambda event: None,
    )
    raw = tmp_path / "operator" / "prime-events.raw.jsonl"
    assert raw.read_bytes() == b"".join(rows)
    assert custody["rawDebug"] == {
        "bytes": raw.stat().st_size,
        "path": "operator/prime-events.raw.jsonl",
        "sha256": hashlib.sha256(raw.read_bytes()).hexdigest().upper(),
    }
    assert capture.verify_capture_custody(config, tmp_path) == custody


def test_two_captures_are_byte_deterministic(capture, tmp_path):
    source = b'{"type":"session"}\n' + text_delta_source_row("hello")
    outputs = []
    for name in ("a", "b"):
        root = tmp_path / name
        capture.capture_binary_stream(
            io.BytesIO(source),
            config=capture_config(capture),
            row_root=root,
            publish=lambda event: None,
        )
        outputs.append(
            (
                (root / "operator" / "prime-events.compact.jsonl").read_bytes(),
                (root / "operator" / "prime-event-capture-custody.json").read_bytes(),
            )
        )
    assert outputs[0] == outputs[1]


@pytest.mark.parametrize("corruption", ["missing", "changed", "duplicate", "reordered"])
def test_retained_corruption_refuses_custody(capture, tmp_path, corruption):
    config = capture_config(capture)
    source = b'{"type":"session"}\n' + text_delta_source_row("hello")
    capture.capture_binary_stream(
        io.BytesIO(source),
        config=config,
        row_root=tmp_path,
        publish=lambda event: None,
    )
    retained = tmp_path / "operator" / "prime-events.compact.jsonl"
    rows = retained.read_bytes().splitlines(keepends=True)
    if corruption == "missing":
        retained.unlink()
    elif corruption == "changed":
        retained.write_bytes(rows[0] + rows[1].replace(b"hello", b"hullo"))
    elif corruption == "duplicate":
        retained.write_bytes(rows[0] + rows[1] + rows[1])
    else:
        retained.write_bytes(rows[1] + rows[0])
    with pytest.raises(capture.PrimeCaptureError) as caught:
        capture.verify_capture_custody(config, tmp_path)
    assert caught.value.code in {"capture_custody_missing", "capture_custody_mismatch"}


def test_existing_destination_refuses_without_overwrite(capture, tmp_path):
    retained = tmp_path / "operator" / "prime-events.compact.jsonl"
    retained.parent.mkdir(parents=True)
    retained.write_bytes(b"protected\n")
    with pytest.raises(capture.PrimeCaptureError) as caught:
        capture.capture_binary_stream(
            io.BytesIO(b'{"type":"session"}\n'),
            config=capture_config(capture),
            row_root=tmp_path,
            publish=lambda event: None,
        )
    assert caught.value.code == "compact_write_failed"
    assert retained.read_bytes() == b"protected\n"
    failure = json.loads(
        (tmp_path / "operator" / "prime-event-capture-failure.json").read_bytes()
    )
    assert failure["status"] == "incomplete"
    assert failure["code"] == "compact_write_failed"


class WriteFailure(io.BytesIO):
    def write(self, value: bytes) -> int:
        raise OSError("injected")


class CloseFailure(io.BytesIO):
    def close(self) -> None:
        raise OSError("injected")


@pytest.mark.parametrize(
    ("writer", "code"),
    [(WriteFailure, "compact_write_failed"), (CloseFailure, "compact_close_failed")],
)
def test_injected_retained_writer_failure_is_incomplete(
    capture, monkeypatch, tmp_path, writer, code
):
    real_open = capture._open_exclusive

    def injected(path: Path):
        if path.name == "prime-events.compact.jsonl":
            return writer()
        return real_open(path)

    monkeypatch.setattr(capture, "_open_exclusive", injected)
    with pytest.raises(capture.PrimeCaptureError) as caught:
        capture.capture_binary_stream(
            io.BytesIO(b'{"type":"session"}\n'),
            config=capture_config(capture),
            row_root=tmp_path,
            publish=lambda event: None,
        )
    assert caught.value.code == code
    assert not (tmp_path / "operator" / "prime-event-capture-custody.json").exists()


def retained_row_count(root: Path) -> int:
    path = root / "operator" / "prime-events.compact.jsonl"
    if not path.exists():
        return 0
    with path.open("rb") as stream:
        return sum(1 for _ in stream)


def wait_until(predicate, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() >= deadline:
            raise AssertionError("condition_not_reached")
        time.sleep(0.01)


def test_stalled_consumer_applies_one_event_backpressure(capture, tmp_path):
    events: queue.Queue = queue.Queue(maxsize=capture.MONITOR_QUEUE_MAX_EVENTS)
    stream = RecordingBytesIO(
        b"".join(b'{"type":"event_' + str(i).encode() + b'"}\n' for i in range(3))
    )
    outcome: dict[str, Any] = {}

    def run_capture() -> None:
        try:
            outcome["custody"] = capture.capture_binary_stream(
                stream,
                config=capture_config(capture),
                row_root=tmp_path,
                publish=events.put,
            )
        except BaseException as error:  # retained for assertion in the parent thread
            outcome["error"] = error

    thread = threading.Thread(target=run_capture)
    thread.start()
    wait_until(lambda: retained_row_count(tmp_path) == 2)
    assert events.qsize() == 1
    assert thread.is_alive()
    assert max(stream.requested_sizes) <= capture.SOURCE_READ_CHUNK_BYTES
    events.get(timeout=1)
    wait_until(lambda: retained_row_count(tmp_path) == 3)
    assert events.qsize() == 1
    events.get(timeout=1)
    thread.join(timeout=2)
    assert not thread.is_alive()
    assert "error" not in outcome
    assert outcome["custody"]["retained"]["rows"] == 3


def checkpoint_row(event_type: str, message: dict[str, Any]) -> bytes:
    return canonical_test_line({"type": event_type, "message": message})


def update_for_message(
    subtype: str,
    content_index: int,
    event_payload: dict[str, Any],
    message: dict[str, Any],
    *,
    root_extra: dict[str, Any] | None = None,
) -> bytes:
    value = {
        "type": "message_update",
        "message": copy.deepcopy(message),
        "assistantMessageEvent": {
            "type": subtype,
            "contentIndex": content_index,
            **copy.deepcopy(event_payload),
            "partial": copy.deepcopy(message),
        },
    }
    if root_extra:
        value.update(root_extra)
    return canonical_test_line(value)


def two_message_reconstruction_fixture() -> tuple[bytes, list[dict[str, Any]]]:
    empty = assistant_message([])
    text_started = assistant_message([text_block("")])
    text_complete = assistant_message([text_block("A")])
    both_started = assistant_message([text_block("A"), thinking_block("")])
    first_final = assistant_message([text_block("A"), thinking_block("B")])
    tool_started = assistant_message([tool_block(streaming=True)])
    tool_final = assistant_message([final_tool_call()])
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
        update_for_message("toolcall_start", 0, {}, tool_started),
        update_for_message("toolcall_delta", 0, {"delta": "{}"}, tool_started),
        update_for_message(
            "toolcall_end", 0, {"toolCall": final_tool_call()}, tool_final
        ),
        checkpoint_row("message_end", tool_final),
    ]
    return b"".join(rows), [first_final, tool_final]


def test_reconstruction_equals_exact_terminal_messages(capture, tmp_path):
    source, expected = two_message_reconstruction_fixture()
    protocol = {"primeEventCapture": approved_capture_config()}
    capture.capture_binary_stream(
        io.BytesIO(source),
        config=capture_config(capture),
        row_root=tmp_path,
        publish=lambda event: None,
    )
    assert capture.reconstruct_terminal_assistant_messages(protocol, tmp_path) == expected


def test_raw_fallback_update_remains_reconstructable(capture, tmp_path):
    empty = assistant_message([])
    final = assistant_message([text_block("raw")])
    source = b"".join(
        [
            checkpoint_row("message_start", empty),
            update_for_message(
                "text_delta",
                0,
                {"delta": "raw"},
                final,
                root_extra={"future": True},
            ),
            checkpoint_row("message_end", final),
        ]
    )
    protocol = {"primeEventCapture": approved_capture_config()}
    custody = capture.capture_binary_stream(
        io.BytesIO(source),
        config=capture_config(capture),
        row_root=tmp_path,
        publish=lambda event: None,
    )
    assert custody["retained"]["rawFallbackMessageUpdates"] == 1
    assert capture.reconstruct_terminal_assistant_messages(protocol, tmp_path) == [final]


def test_missing_terminal_checkpoint_refuses_reconstruction(capture, tmp_path):
    source = checkpoint_row("message_start", assistant_message([]))
    protocol = {"primeEventCapture": approved_capture_config()}
    capture.capture_binary_stream(
        io.BytesIO(source),
        config=capture_config(capture),
        row_root=tmp_path,
        publish=lambda event: None,
    )
    with pytest.raises(ValueError, match="assistant_reconstruction_incomplete"):
        capture.reconstruct_terminal_assistant_messages(protocol, tmp_path)
