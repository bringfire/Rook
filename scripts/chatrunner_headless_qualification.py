#!/usr/bin/env python3
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import secrets
import subprocess
import sys
import time
from typing import Any, BinaryIO, Callable, Mapping
from urllib.parse import urlsplit

import rook
from rook.agent.chat.chat_runner import ChatRunner
from rook.agent.chat.conversation_store import Conversation
from rook.agent.chat.prompt_builder import PromptBuilder
from rook.agent.tool_dispatcher import ToolDispatcher, build_local_tools
from rook.bridge import get_rhino_request_context, rhino_request_context
from rook.mcp_tool_profiles import resolve_profile
from rook.server import build_mcp_capability_gateway_executor
from rook.targeting import InstanceRef, clear_active_target, get_active_target, set_active_target

_ROW_MAX_BYTES = 256 * 1024
_TRACE_MAX_BYTES = 4 * 1024 * 1024
_ROW_KEYS = frozenset({"model", "api_base", "intent", "skill_path", "rhino_target"})
_TARGET_KEYS = frozenset({"port", "process_id", "document_serial_number"})
_TARGET_CONTROL_TOOLS = frozenset({"rhino_set_active_instance", "rhino_clear_active_instance"})
_ROUTING_KEYS = frozenset({"port", "session", "documentSerialNumber"})
_TRACE_KINDS = frozenset(
    {
        "run_started",
        "chat_event",
        "qualification_refusal",
        "stream_exception",
        "run_cancelled",
        "target_drift",
        "snapshot_request",
        "snapshot_result",
        "run_finished",
    }
)


@dataclass(frozen=True)
class _RhinoTarget:
    port: int
    process_id: int
    document_serial_number: int


@dataclass(frozen=True)
class _QualificationRow:
    source_path: Path
    source_sha256: str
    model: str
    api_base: str
    intent: str
    skill_path: Path
    skill_sha256: str
    skill_text: str
    target: _RhinoTarget


class _TraceWriteFailure(RuntimeError):
    def __init__(self, reason: str, path: Path | None) -> None:
        super().__init__("trace_write_failed")
        self.reason = reason
        self.path = path


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_json_key")
        result[key] = value
    return result


def _reject_json_constant(_: str) -> None:
    raise ValueError("invalid_json_constant")


def _read_strict_utf8(path: Path, invalid_reason: str) -> tuple[bytes, str]:
    try:
        raw = path.read_bytes()
    except Exception:
        raise ValueError(invalid_reason) from None
    try:
        return raw, raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        raise ValueError(invalid_reason) from None


def _require_nonblank_string(value: Any, reason: str) -> str:
    if type(value) is not str or not value.strip():
        raise ValueError(reason)
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeEncodeError:
        raise ValueError(reason) from None
    return value


def _validate_api_base(value: Any) -> str:
    api_base = _require_nonblank_string(value, "invalid_api_base")
    try:
        parsed = urlsplit(api_base)
        _ = parsed.port
    except ValueError:
        raise ValueError("invalid_api_base") from None
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("invalid_api_base")
    return api_base


def _load_row(path: Path) -> _QualificationRow:
    try:
        source_path = path.resolve(strict=True)
    except Exception:
        raise ValueError("invalid_row_file") from None
    row_bytes, row_text = _read_strict_utf8(source_path, "invalid_row_utf8")
    try:
        document = json.loads(
            row_text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_json_constant,
        )
    except ValueError as exc:
        if str(exc) == "duplicate_json_key":
            raise
        raise ValueError("invalid_row_json") from None
    if type(document) is not dict or frozenset(document) != _ROW_KEYS:
        raise ValueError("invalid_row_keys")

    model = _require_nonblank_string(document["model"], "invalid_model")
    api_base = _validate_api_base(document["api_base"])
    intent = _require_nonblank_string(document["intent"], "invalid_intent")
    skill_value = _require_nonblank_string(
        document["skill_path"],
        "invalid_skill_path",
    )

    target = document["rhino_target"]
    if type(target) is not dict:
        raise ValueError("invalid_rhino_target")
    if frozenset(target) != _TARGET_KEYS:
        raise ValueError("invalid_rhino_target_keys")
    target_values: dict[str, int] = {}
    for field in _TARGET_KEYS:
        value = target[field]
        if type(value) is not int or value <= 0:
            raise ValueError(f"invalid_{field}")
        target_values[field] = value

    try:
        skill_path = Path(skill_value).resolve(strict=True)
    except Exception:
        raise ValueError("invalid_skill_file") from None
    if not skill_path.is_file():
        raise ValueError("invalid_skill_file")
    skill_bytes, skill_text = _read_strict_utf8(skill_path, "invalid_skill_utf8")

    return _QualificationRow(
        source_path=source_path,
        source_sha256=hashlib.sha256(row_bytes).hexdigest(),
        model=model,
        api_base=api_base,
        intent=intent,
        skill_path=skill_path,
        skill_sha256=hashlib.sha256(skill_bytes).hexdigest(),
        skill_text=skill_text,
        target=_RhinoTarget(**target_values),
    )


class _JsonlRecorder:
    def __init__(
        self,
        *,
        path: Path,
        stream: BinaryIO,
        wall_clock: Callable[[], str],
    ) -> None:
        self._path = path
        self._stream = stream
        self._wall_clock = wall_clock
        self._bytes_written = 0
        self._sequence = 0
        self._failed = False
        self._closed = False
        self._close_attempted = False

    @property
    def path(self) -> Path:
        return self._path

    @property
    def bytes_written(self) -> int:
        return self._bytes_written

    @property
    def sequence(self) -> int:
        return self._sequence

    @property
    def failed(self) -> bool:
        return self._failed

    @property
    def closed(self) -> bool:
        return self._closed

    def record(self, kind: str, payload: Mapping[str, Any]) -> None:
        self._require_writable()
        if type(kind) is not str or kind not in _TRACE_KINDS:
            raise ValueError("invalid_trace_kind")
        next_sequence = self._sequence + 1
        try:
            row = (
                json.dumps(
                    {
                        "sequence": next_sequence,
                        "recorded_at_utc": self._wall_clock(),
                        "kind": kind,
                        "payload": payload,
                    },
                    ensure_ascii=True,
                    allow_nan=False,
                    separators=(",", ":"),
                )
                + "\n"
            ).encode("utf-8")
        except Exception:
            self._fail("json_serialization_failed")
        if len(row) > _ROW_MAX_BYTES:
            self._fail("row_size_exceeded")
        if self._bytes_written + len(row) > _TRACE_MAX_BYTES:
            self._fail("total_size_exceeded")

        try:
            written = self._stream.write(row)
        except Exception:
            self._fail("write_failed")
        if type(written) is not int or written < 0 or written > len(row):
            self._fail("invalid_write_count")
        self._bytes_written += written
        if written != len(row):
            self._fail("short_write")
        try:
            self._stream.flush()
        except Exception:
            self._fail("flush_failed")
        self._sequence = next_sequence

    def close(self) -> None:
        if self._close_attempted:
            return
        self._close_attempted = True
        try:
            self._stream.close()
        except Exception:
            self._failed = True
            raise _TraceWriteFailure("close_failed", self._path) from None
        self._closed = True

    def _require_writable(self) -> None:
        if self._failed:
            raise _TraceWriteFailure("recorder_failed", self._path)
        if self._closed:
            raise _TraceWriteFailure("recorder_closed", self._path)

    def _fail(self, reason: str) -> None:
        self._failed = True
        raise _TraceWriteFailure(reason, self._path)


def _utc_now_string() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _open_recorder() -> _JsonlRecorder:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if type(local_app_data) is not str or not local_app_data.strip():
        raise _TraceWriteFailure("localappdata_missing", None)
    trace_directory = Path(local_app_data) / "Rook" / "traces"
    try:
        trace_directory.mkdir(parents=True, exist_ok=True)
    except Exception:
        raise _TraceWriteFailure("trace_directory_create_failed", None) from None
    try:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        filename = (
            f"chatrunner-headless-qualification-{stamp}-"
            f"p{os.getpid()}-{secrets.token_hex(4)}.jsonl"
        )
        path = (trace_directory / filename).resolve()
    except Exception:
        raise _TraceWriteFailure("trace_path_prepare_failed", None) from None
    try:
        stream = path.open("xb", buffering=0)
    except Exception:
        raise _TraceWriteFailure("trace_open_failed", path) from None
    return _JsonlRecorder(path=path, stream=stream, wall_clock=_utc_now_string)


def _targeting_refusal(event: Any) -> str | None:
    if event.type != "tool_start":
        return None
    params = event.params if type(event.params) is dict else {}
    if event.name in _TARGET_CONTROL_TOOLS:
        return "target_control_forbidden"
    if event.name == "rook_tools_call":
        if params.get("name") in _TARGET_CONTROL_TOOLS:
            return "target_control_forbidden"
        arguments = params.get("arguments")
        if type(arguments) is dict and _ROUTING_KEYS.intersection(arguments):
            return "target_override_forbidden"
        return None
    if _ROUTING_KEYS.intersection(params):
        return "target_override_forbidden"
    return None


async def _consume_events(
    *, recorder: _JsonlRecorder, runner: Any, conversation: Any, intent: str,
    system_prompt: str, canonical_executor: Callable[..., Any], target_matches: Callable[[], bool],
    monotonic: Callable[[], float],
) -> str:
    started = monotonic()
    stream = runner.run_turn(conversation, intent, system_prompt)
    exhausted = done_observed = chat_error_observed = False
    usage: Mapping[str, Any] | None = None
    status = "refused"

    try:
        while True:
            try:
                event = await anext(stream)
            except StopAsyncIteration:
                exhausted = True
                break
            recorder.record("chat_event", event.to_dict())
            if not target_matches():
                recorder.record("target_drift", {"stage": "chat_event"})
                break
            refusal = _targeting_refusal(event)
            if refusal is not None:
                recorder.record("qualification_refusal",
                                {"reason": refusal, "tool_name": event.name})
                break
            done_observed = done_observed or event.type == "done"
            chat_error_observed = chat_error_observed or event.type == "error"
            if event.type == "done":
                usage = event.usage
    except asyncio.CancelledError:
        try:
            recorder.record("run_cancelled", {})
        except _TraceWriteFailure:
            status = "trace_write_failed"
    except _TraceWriteFailure:
        status = "trace_write_failed"
    except Exception as exc:
        try:
            recorder.record("stream_exception", {"exception_type": type(exc).__name__,
                                                  "exception_message": str(exc)})
        except _TraceWriteFailure:
            status = "trace_write_failed"
    finally:
        try:
            await stream.aclose()
        except Exception:
            pass

    if status != "trace_write_failed" and exhausted and done_observed:
        try:
            if not target_matches():
                recorder.record("target_drift", {"stage": "before_snapshot"})
            else:
                request = {"name": "gh_snapshot", "arguments": {
                    "include_data": False, "max_preview_items": 0}}
                recorder.record("snapshot_request", request)
                result = await canonical_executor("rook_tools_call", request)
                if not target_matches():
                    recorder.record("target_drift", {"stage": "after_snapshot"})
                else:
                    recorder.record("snapshot_result", result)
                    recorder.record(
                        "run_finished",
                        {
                            "stream_exhausted": True, "done_observed": True,
                            "chat_error_observed": chat_error_observed, "usage": usage,
                            "inspection_attempted": True, "inspection_result_recorded": True,
                            "elapsed_seconds": monotonic() - started,
                        },
                    )
                    status = "completed"
        except _TraceWriteFailure:
            status = "trace_write_failed"
        except Exception:
            status = "refused"

    return _close_recorder(recorder, status)


def _close_recorder(recorder: _JsonlRecorder, status: str) -> str:
    try:
        recorder.close()
    except _TraceWriteFailure:
        return "trace_write_failed"
    return status


def _runtime_identity() -> dict[str, Any]:
    root = Path(__file__).resolve().parents[1]

    def git(*args: str) -> str:
        return subprocess.check_output(
            ["git", *args], cwd=root, text=True).strip()

    return {
        "git_head": git("rev-parse", "HEAD"), "git_dirty": bool(git("status", "--porcelain")),
        "python_executable": sys.executable, "python_version": platform.python_version(),
        "rook_module_path": str(Path(rook.__file__).resolve()), "litellm_version": importlib.metadata.version("litellm"),
    }


def _target_matches(row: _QualificationRow) -> bool:
    target = row.target
    context = {"port": target.port, "process_id": target.process_id,
        "document_serial_number": target.document_serial_number}
    return (get_active_target() == InstanceRef(target.port, target.process_id)
            and get_rhino_request_context() == context)


async def _run_row(row: _QualificationRow) -> tuple[str, Path | None]:
    try:
        recorder = _open_recorder()
    except _TraceWriteFailure as exc:
        return "trace_write_failed", exc.path
    prompt = (PromptBuilder().build_system("architect")
              + "\n\n## Explicit qualification skill\n\n" + row.skill_text)
    target = row.target
    previous_target = get_active_target()
    set_active_target(InstanceRef(target.port, target.process_id))
    try:
        with rhino_request_context(port=target.port, process_id=target.process_id,
                                   document_serial_number=target.document_serial_number):
            if not _target_matches(row):
                recorder.record("target_drift", {"stage": "before_start"})
                return _close_recorder(recorder, "refused"), recorder.path
            started = _runtime_identity() | {
                "row_path": str(row.source_path), "row_sha256": row.source_sha256,
                "model": row.model, "api_base": row.api_base,
                "mcp_profile": resolve_profile(os.environ).value, "intent": row.intent,
                "skill_path": str(row.skill_path), "skill_sha256": row.skill_sha256,
                "system_prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                "rhino_target": {"port": target.port, "process_id": target.process_id,
                                 "document_serial_number": target.document_serial_number},
            }
            recorder.record("run_started", started)
            dispatcher = ToolDispatcher(port=target.port, local_tools=build_local_tools())
            canonical = build_mcp_capability_gateway_executor("full")
            runner = ChatRunner(tool_executor=dispatcher.dispatch, tool_access="full",
                                mcp_capability_executor=canonical)
            conversation = Conversation(id="qualification", persona="architect",
                document_serial_number=target.document_serial_number,
                model=row.model, api_base=row.api_base)
            status = await _consume_events(recorder=recorder, runner=runner,
                conversation=conversation, intent=row.intent, system_prompt=prompt,
                canonical_executor=canonical, target_matches=lambda: _target_matches(row),
                monotonic=time.monotonic)
            return status, recorder.path
    except _TraceWriteFailure:
        return _close_recorder(recorder, "trace_write_failed"), recorder.path
    except Exception:
        return _close_recorder(recorder, "refused"), recorder.path
    finally:
        clear_active_target()
        if previous_target is not None:
            set_active_target(previous_target)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    status, trace_path = "refused", None
    if len(args) == 1:
        try:
            status, trace_path = asyncio.run(_run_row(_load_row(Path(args[0]))))
        except Exception:
            pass
    result = {"status": status, "trace_path": trace_path.as_posix() if trace_path else None}
    print(json.dumps(result, separators=(",", ":")))
    return 0 if status == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
