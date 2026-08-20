"""Causal tests for bounded Prime JSON event capture."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import sys
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
