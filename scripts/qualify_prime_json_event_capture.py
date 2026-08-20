"""Qualify compact Prime event capture from immutable offline evidence."""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib
import importlib.util
from itertools import zip_longest
import json
import math
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import time
from typing import Any, Iterator


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "rook.experiment.prime_json_event_capture_offline_qualification:v1"
RESULT_SCHEMA = "rook.experiment.prime_json_event_capture_offline_result:v1"
_SHA_CHUNK_BYTES = 1024 * 1024
_MANIFEST_EXCLUSIONS = {"evidence-manifest.json", "manifest-verification.json"}
_CAPTURE_PATH = (ROOT / "scripts" / "prime_json_event_capture.py").resolve()
_RUNNER_PATH = (
    ROOT / "scripts" / "qwen38_self_termination_campaign_runner.py"
).resolve()
_SPEC_PATH = (
    ROOT
    / "docs"
    / "superpowers"
    / "specs"
    / "2026-08-20-prime-json-event-stream-storage-efficiency-design.md"
).resolve()
_ORACLE_DELTA_SCHEMA = "rook.prime_assistant_stream_delta:v1"
_ORACLE_EVENT_KEYS = {
    "text_start": {"type", "contentIndex", "partial"},
    "text_delta": {"type", "contentIndex", "delta", "partial"},
    "text_end": {"type", "contentIndex", "content", "partial"},
    "thinking_start": {"type", "contentIndex", "partial"},
    "thinking_delta": {"type", "contentIndex", "delta", "partial"},
    "thinking_end": {"type", "contentIndex", "content", "partial"},
    "toolcall_start": {"type", "contentIndex", "partial"},
    "toolcall_delta": {"type", "contentIndex", "delta", "partial"},
    "toolcall_end": {"type", "contentIndex", "toolCall", "partial"},
}


def _load_local_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("qualification_owner_import_failed")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    if Path(module.__file__).resolve() != path.resolve():
        raise RuntimeError("qualification_owner_import_mismatch")
    return module


capture = _load_local_module("rook_prime_capture_qualification", _CAPTURE_PATH)
acceptance_v1 = importlib.import_module("rook." + "gh_behavioral_acceptance")
acceptance_v2 = importlib.import_module("rook." + "gh_behavioral_acceptance_v2")


def _canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(_canonical_bytes(value))
        stream.flush()


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _measure(path: Path, *, count_rows: bool = False) -> dict[str, Any]:
    digest = hashlib.sha256()
    byte_count = 0
    rows = 0
    last = b""
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(_SHA_CHUNK_BYTES), b""):
            digest.update(chunk)
            byte_count += len(chunk)
            if count_rows:
                rows += chunk.count(b"\n")
                last = chunk[-1:]
    result = {
        "bytes": byte_count,
        "sha256": digest.hexdigest().upper(),
    }
    if count_rows:
        if byte_count and last != b"\n":
            raise ValueError("source_evidence_mismatch")
        result["rows"] = rows
    return result


def _is_sha(value: Any) -> bool:
    return (
        type(value) is str
        and len(value) == 64
        and all(character in "0123456789ABCDEF" for character in value)
    )


def _positive_int(value: Any) -> bool:
    return type(value) is int and value > 0


def _nonnegative_int(value: Any) -> bool:
    return type(value) is int and value >= 0


def _absolute_path(value: Any) -> bool:
    return type(value) is str and Path(value).is_absolute()


def _reference(value: Any) -> bool:
    return (
        type(value) is dict
        and set(value) == {"path", "sha256"}
        and _absolute_path(value.get("path"))
        and _is_sha(value.get("sha256"))
    )


def _runtime_reference(value: Any) -> bool:
    return (
        type(value) is dict
        and set(value) == {"path", "sha256", "bytes", "rows"}
        and _absolute_path(value.get("path"))
        and _is_sha(value.get("sha256"))
        and _positive_int(value.get("bytes"))
        and _positive_int(value.get("rows"))
    )


def validate_qualification_protocol(value: Any) -> dict[str, Any]:
    root_keys = {
        "schema",
        "mode",
        "outputRoot",
        "captureConfig",
        "sourceEvidence",
        "owners",
        "precontactVerification",
        "expected",
    }
    if (
        type(value) is not dict
        or set(value) != root_keys
        or value.get("schema") != SCHEMA
        or value.get("mode") != "offline_only"
        or not _absolute_path(value.get("outputRoot"))
    ):
        raise ValueError("qualification_protocol_invalid")
    try:
        config = capture.validate_capture_config(value["captureConfig"])
    except ValueError as error:
        raise ValueError("qualification_protocol_invalid") from error
    if config is None or config.mode != "compact":
        raise ValueError("qualification_protocol_invalid")

    source = value.get("sourceEvidence")
    if (
        type(source) is not dict
        or set(source)
        != {
            "root",
            "rowRoot",
            "globalManifest",
            "rowManifest",
            "runtimeLog",
            "sourceLog",
            "processResult",
        }
        or not _absolute_path(source.get("root"))
        or not _absolute_path(source.get("rowRoot"))
        or not _reference(source.get("globalManifest"))
        or not _reference(source.get("rowManifest"))
        or not _runtime_reference(source.get("runtimeLog"))
        or not _reference(source.get("sourceLog"))
        or not _reference(source.get("processResult"))
    ):
        raise ValueError("qualification_protocol_invalid")
    root = Path(source["root"]).resolve()
    row_root = Path(source["rowRoot"]).resolve()
    output_root = Path(value["outputRoot"]).resolve()
    try:
        row_root.relative_to(root)
    except ValueError as error:
        raise ValueError("qualification_protocol_invalid") from error
    if output_root == root or output_root.is_relative_to(root):
        raise ValueError("qualification_protocol_invalid")
    if Path(source["globalManifest"]["path"]).resolve() != root / "evidence-manifest.json":
        raise ValueError("qualification_protocol_invalid")
    if Path(source["rowManifest"]["path"]).resolve() != row_root / "evidence-manifest.json":
        raise ValueError("qualification_protocol_invalid")
    for field in ("runtimeLog", "sourceLog", "processResult"):
        try:
            Path(source[field]["path"]).resolve().relative_to(row_root)
        except ValueError as error:
            raise ValueError("qualification_protocol_invalid") from error

    owners = value.get("owners")
    expected_owner_paths = {
        "captureModule": _CAPTURE_PATH,
        "campaignRunner": _RUNNER_PATH,
        "v2": Path(acceptance_v2.__file__).resolve(),
        "spec": _SPEC_PATH,
    }
    if type(owners) is not dict or set(owners) != set(expected_owner_paths):
        raise ValueError("qualification_protocol_invalid")
    for name, expected_path in expected_owner_paths.items():
        if not _reference(owners[name]) or Path(owners[name]["path"]).resolve() != expected_path:
            raise ValueError("qualification_protocol_invalid")

    verification = value.get("precontactVerification")
    if (
        type(verification) is not dict
        or set(verification) != {"pythonPath", "arguments"}
        or not _absolute_path(verification.get("pythonPath"))
        or type(verification.get("arguments")) is not list
        or not verification["arguments"]
        or any(type(item) is not str or not item for item in verification["arguments"])
    ):
        raise ValueError("qualification_protocol_invalid")

    expected = value.get("expected")
    if (
        type(expected) is not dict
        or set(expected)
        != {
            "sourceRows",
            "sourceBytes",
            "sourceSha256",
            "compactedMessageUpdates",
            "rawFallbackMessageUpdates",
            "maxRetainedRatio",
            "liveContact",
        }
        or not _positive_int(expected.get("sourceRows"))
        or not _positive_int(expected.get("sourceBytes"))
        or not _is_sha(expected.get("sourceSha256"))
        or not _nonnegative_int(expected.get("compactedMessageUpdates"))
        or not _nonnegative_int(expected.get("rawFallbackMessageUpdates"))
        or type(expected.get("maxRetainedRatio")) not in {int, float}
        or not math.isfinite(expected["maxRetainedRatio"])
        or not 0 < expected["maxRetainedRatio"] <= 1
        or expected.get("liveContact") is not False
    ):
        raise ValueError("qualification_protocol_invalid")
    return value


def verify_evidence_manifest(
    root: Path,
    manifest_path: Path,
    *,
    cache: dict[Path, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    try:
        manifest = _load_json(manifest_path)
    except (OSError, ValueError):
        return {"entryCount": None, "mismatches": ["manifest_shape"]}
    if (
        type(manifest) is not dict
        or set(manifest) != {"schema", "root", "entryCount", "entries"}
        or manifest.get("schema") != "rook.evidence_manifest:v1"
        or not _absolute_path(manifest.get("root"))
        or Path(manifest["root"]).resolve() != root
        or type(manifest.get("entryCount")) is not int
        or type(manifest.get("entries")) is not dict
        or manifest["entryCount"] != len(manifest["entries"])
    ):
        return {"entryCount": None, "mismatches": ["manifest_shape"]}
    observed = cache if cache is not None else {}
    mismatches: list[str] = []
    for relative, expected in manifest["entries"].items():
        relative_path = Path(relative)
        if (
            type(relative) is not str
            or relative_path.is_absolute()
            or ".." in relative_path.parts
            or type(expected) is not dict
            or set(expected) != {"bytes", "sha256"}
            or not _nonnegative_int(expected.get("bytes"))
            or not _is_sha(expected.get("sha256"))
        ):
            mismatches.append(str(relative))
            continue
        path = (root / relative_path).resolve()
        if not path.is_file():
            mismatches.append(relative)
            continue
        if path not in observed:
            observed[path] = _measure(path)
        if (
            observed[path]["bytes"] != expected["bytes"]
            or observed[path]["sha256"] != expected["sha256"]
        ):
            mismatches.append(relative)
    retained = set(manifest["entries"])
    actual = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
        and path.relative_to(root).as_posix() not in _MANIFEST_EXCLUSIONS
    }
    mismatches.extend(f"unexpected:{item}" for item in sorted(actual - retained))
    return {"entryCount": manifest["entryCount"], "mismatches": mismatches}


def verify_source_evidence(protocol: dict[str, Any]) -> dict[str, Any]:
    source = protocol["sourceEvidence"]
    cache: dict[Path, dict[str, Any]] = {}
    references = {
        **{name: source[name] for name in ("globalManifest", "rowManifest", "sourceLog", "processResult")},
        **{f"owner:{name}": value for name, value in protocol["owners"].items()},
    }
    for name, reference in references.items():
        path = Path(reference["path"]).resolve()
        if not path.is_file():
            raise ValueError("source_evidence_mismatch")
        cache[path] = _measure(path)
        if cache[path]["sha256"] != reference["sha256"]:
            raise ValueError("source_evidence_mismatch")
    runtime_reference = source["runtimeLog"]
    runtime_path = Path(runtime_reference["path"]).resolve()
    if not runtime_path.is_file():
        raise ValueError("source_evidence_mismatch")
    runtime = _measure(runtime_path, count_rows=True)
    cache[runtime_path] = runtime
    expected = protocol["expected"]
    if (
        any(runtime[key] != runtime_reference[key] for key in ("sha256", "bytes", "rows"))
        or expected["sourceRows"] != runtime_reference["rows"]
        or expected["sourceBytes"] != runtime_reference["bytes"]
        or expected["sourceSha256"] != runtime_reference["sha256"]
    ):
        raise ValueError("source_evidence_mismatch")
    global_result = verify_evidence_manifest(
        Path(source["root"]), Path(source["globalManifest"]["path"]), cache=cache
    )
    row_result = verify_evidence_manifest(
        Path(source["rowRoot"]), Path(source["rowManifest"]["path"]), cache=cache
    )
    if global_result["mismatches"] or row_result["mismatches"]:
        raise ValueError("source_evidence_mismatch")
    return {
        "schema": "rook.experiment.prime_json_event_capture_source_custody:v1",
        "globalManifest": global_result,
        "rowManifest": row_result,
        "runtime": runtime,
        "references": {name: value["sha256"] for name, value in references.items()},
        "liveContact": False,
    }


def _run_precontact(protocol: dict[str, Any], output_root: Path) -> dict[str, Any]:
    verification = protocol["precontactVerification"]
    command = [verification["pythonPath"], *verification["arguments"]]
    completed = subprocess.run(
        command,
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=600,
    )
    (output_root / "precontact-stdout.txt").write_text(
        completed.stdout, encoding="utf-8"
    )
    (output_root / "precontact-stderr.txt").write_text(
        completed.stderr, encoding="utf-8"
    )
    record = {
        "schema": "rook.experiment.prime_json_event_capture_precontact:v1",
        "command": command,
        "exitCode": completed.returncode,
        "stdoutSha256": _measure(output_root / "precontact-stdout.txt")["sha256"],
        "stderrSha256": _measure(output_root / "precontact-stderr.txt")["sha256"],
        "liveContact": False,
    }
    _write_json(output_root / "precontact-result.json", record)
    if completed.returncode != 0:
        raise RuntimeError("precontact_verification_failed")
    return record


def _run_replay(protocol: dict[str, Any], replay_root: Path) -> dict[str, Any]:
    config = capture.validate_capture_config(protocol["captureConfig"])
    with Path(protocol["sourceEvidence"]["runtimeLog"]["path"]).open("rb") as source:
        custody = capture.capture_binary_stream(
            source,
            config=config,
            row_root=replay_root,
            publish=lambda event: None,
        )
    return {
        "root": replay_root,
        "custody": custody,
        "retainedPath": replay_root.joinpath(*config.retained_path.parts),
        "custodyPath": replay_root.joinpath(*config.custody_path.parts),
    }


def _iter_jsonl(path: Path) -> Iterator[tuple[bytes, dict[str, Any]]]:
    with path.open("rb") as stream:
        for raw in stream:
            if not raw.endswith(b"\n"):
                raise ValueError("offline_parity_invalid")
            value = json.loads(raw)
            if type(value) is not dict:
                raise ValueError("offline_parity_invalid")
            yield raw, value


def _oracle_same_value(left: Any, right: Any) -> bool:
    if type(left) is not type(right):
        return False
    if type(left) is dict:
        return set(left) == set(right) and all(
            _oracle_same_value(left[key], right[key]) for key in left
        )
    if type(left) is list:
        return len(left) == len(right) and all(
            _oracle_same_value(a, b) for a, b in zip(left, right)
        )
    return left == right


def _oracle_optional_string(value: dict[str, Any], key: str) -> bool:
    return key not in value or type(value[key]) is str


def _oracle_text_block(value: Any) -> bool:
    return (
        type(value) is dict
        and {"type", "text"} <= set(value)
        and not set(value) - {"type", "text", "textSignature"}
        and value["type"] == "text"
        and type(value["text"]) is str
        and _oracle_optional_string(value, "textSignature")
    )


def _oracle_thinking_block(value: Any) -> bool:
    return (
        type(value) is dict
        and {"type", "thinking"} <= set(value)
        and not set(value)
        - {"type", "thinking", "thinkingSignature", "redacted"}
        and value["type"] == "thinking"
        and type(value["thinking"]) is str
        and _oracle_optional_string(value, "thinkingSignature")
        and ("redacted" not in value or type(value["redacted"]) is bool)
    )


def _oracle_tool_block(value: Any, *, streaming: bool) -> bool:
    if type(value) is not dict:
        return False
    optional = {"thoughtSignature"}
    if streaming:
        optional |= {"partialArgs", "streamIndex"}
    if set(value) != {"type", "id", "name", "arguments"} | (
        set(value) & optional
    ):
        return False
    return (
        value["type"] == "toolCall"
        and type(value["id"]) is str
        and bool(value["id"])
        and type(value["name"]) is str
        and bool(value["name"])
        and type(value["arguments"]) is dict
        and _oracle_optional_string(value, "thoughtSignature")
        and ("partialArgs" not in value or type(value["partialArgs"]) is str)
        and (
            "streamIndex" not in value
            or (type(value["streamIndex"]) is int and value["streamIndex"] >= 0)
        )
    )


def _oracle_content_start(
    subtype: str, block: dict[str, Any]
) -> dict[str, Any] | None:
    if subtype == "text_start":
        result = {"type": "text", "text": ""}
        if "textSignature" in block:
            result["textSignature"] = block["textSignature"]
        return result
    if subtype == "thinking_start":
        result = {"type": "thinking", "thinking": ""}
        for key in ("thinkingSignature", "redacted"):
            if key in block:
                result[key] = block[key]
        return result
    if subtype == "toolcall_start":
        result = {
            "type": "toolCall",
            "id": block["id"],
            "name": block["name"],
            "arguments": {},
        }
        if "thoughtSignature" in block:
            result["thoughtSignature"] = block["thoughtSignature"]
        return result
    return None


def _oracle_compact_projection(
    source: dict[str, Any], source_row: int, source_bytes: int
) -> dict[str, Any] | None:
    if set(source) != {"type", "message", "assistantMessageEvent"}:
        return None
    if source.get("type") != "message_update":
        return None
    message = source.get("message")
    event = source.get("assistantMessageEvent")
    if type(message) is not dict or type(event) is not dict:
        return None
    if (
        message.get("role") != "assistant"
        or "partial" not in event
        or not _oracle_same_value(message, event["partial"])
    ):
        return None
    subtype = event.get("type")
    if subtype not in _ORACLE_EVENT_KEYS or set(event) != _ORACLE_EVENT_KEYS[subtype]:
        return None
    index = event.get("contentIndex")
    content = message.get("content")
    if (
        type(index) is not int
        or index < 0
        or type(content) is not list
        or index >= len(content)
    ):
        return None
    block = content[index]
    if subtype.startswith("text_"):
        valid_block = _oracle_text_block(block)
    elif subtype.startswith("thinking_"):
        valid_block = _oracle_thinking_block(block)
    elif subtype in {"toolcall_start", "toolcall_delta"}:
        valid_block = _oracle_tool_block(block, streaming=True)
    else:
        valid_block = _oracle_tool_block(block, streaming=False)
    if not valid_block:
        return None
    if subtype.endswith("_delta") and type(event.get("delta")) is not str:
        return None
    if subtype in {"text_end", "thinking_end"}:
        if type(event.get("content")) is not str:
            return None
        block_value = block["text"] if subtype == "text_end" else block["thinking"]
        if event["content"] != block_value:
            return None
    if subtype == "toolcall_end" and (
        not _oracle_tool_block(event.get("toolCall"), streaming=False)
        or not _oracle_same_value(event["toolCall"], block)
    ):
        return None
    projection: dict[str, Any] = {
        "schema": _ORACLE_DELTA_SCHEMA,
        "type": "assistant_stream_delta",
        "sourceRow": source_row,
        "sourceBytes": source_bytes,
        "assistantMessageEvent": {
            key: copy.deepcopy(value)
            for key, value in event.items()
            if key != "partial"
        },
    }
    content_start = _oracle_content_start(subtype, block)
    if content_start is not None:
        projection["contentStart"] = content_start
    return projection


def _oracle_canonical_line(value: Any) -> bytes:
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


def _independent_row_parity(source_path: Path, retained_path: Path) -> dict[str, Any]:
    result = {
        "status": "pass",
        "sourceRows": 0,
        "retainedRows": 0,
        "compactedMessageUpdates": 0,
        "rawFallbackMessageUpdates": 0,
        "passthroughRows": 0,
        "firstMismatch": None,
    }
    source_rows = _iter_jsonl(source_path)
    retained_rows = _iter_jsonl(retained_path)
    for row_index, pair in enumerate(
        zip_longest(source_rows, retained_rows), start=1
    ):
        source_item, retained_item = pair
        if source_item is None or retained_item is None:
            result["status"] = "fail"
            result["firstMismatch"] = {
                "row": row_index,
                "reason": "row_count_mismatch",
            }
            break
        source_raw, source = source_item
        retained_raw, retained = retained_item
        result["sourceRows"] += 1
        result["retainedRows"] += 1
        if retained.get("type") == "assistant_stream_delta":
            projection = _oracle_compact_projection(
                source, row_index, len(source_raw)
            )
            if projection is None:
                result["status"] = "fail"
                result["firstMismatch"] = {
                    "row": row_index,
                    "reason": "compact_source_invalid",
                }
                break
            if retained_raw != _oracle_canonical_line(projection):
                result["status"] = "fail"
                result["firstMismatch"] = {
                    "row": row_index,
                    "reason": "compact_projection_mismatch",
                }
                break
            result["compactedMessageUpdates"] += 1
            continue
        if retained_raw != source_raw:
            result["status"] = "fail"
            result["firstMismatch"] = {
                "row": row_index,
                "reason": "passthrough_mismatch",
            }
            break
        result["passthroughRows"] += 1
        result["rawFallbackMessageUpdates"] += int(
            source.get("type") == "message_update"
        )
    return result


def _raw_terminal_assistant_messages(path: Path) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for _, value in _iter_jsonl(path):
        if value.get("type") != "message_end":
            continue
        message = value.get("message")
        if type(message) is dict and message.get("role") == "assistant":
            messages.append(copy.deepcopy(message))
    return messages


def _process_state(path: Path) -> dict[str, Any]:
    process = _load_json(path)
    return {
        "terminated": True,
        "stdout_eof": process.get("stdoutEof") is True,
        "owned_child_pids": process.get("ownedChildPids", []),
        "exit_code": process.get("exitCode"),
    }


def _without_runtime_hash(value: dict[str, Any]) -> dict[str, Any]:
    projected = copy.deepcopy(value)
    projected.pop("runtime_log_sha256", None)
    return projected


def _final_observation(trace: dict[str, Any]) -> Any:
    return next(
        (
            copy.deepcopy(event.get("result"))
            for event in reversed(trace.get("events", []))
            if event.get("target") == "gh_snapshot"
        ),
        None,
    )


def _run_v2_parity(
    protocol: dict[str, Any], output_root: Path, raw_runtime: Path, compact_runtime: Path
) -> dict[str, Any]:
    process = _process_state(Path(protocol["sourceEvidence"]["processResult"]["path"]))
    source = Path(protocol["sourceEvidence"]["sourceLog"]["path"])
    results = []
    for name, runtime in (("raw", raw_runtime), ("compact", compact_runtime)):
        root = output_root / f"{name}-v2"
        root.mkdir()
        source_copy = root / "source.jsonl"
        shutil.copy2(source, source_copy)
        closure, trace = acceptance_v2.seal_and_normalize_prime_source_log(
            source_copy, runtime, process
        )
        results.append((closure, trace))
    raw_closure, raw_trace = results[0]
    compact_closure, compact_trace = results[1]
    latest_raw = acceptance_v1._latest_terminal_receipt(raw_trace)
    latest_compact = acceptance_v1._latest_terminal_receipt(compact_trace)
    status = "pass" if (
        _without_runtime_hash(raw_closure) == _without_runtime_hash(compact_closure)
        and raw_trace["events"] == compact_trace["events"]
        and latest_raw == latest_compact
        and _final_observation(raw_trace) == _final_observation(compact_trace)
    ) else "fail"
    record = {
        "schema": "rook.experiment.prime_json_event_capture_v2_parity:v1",
        "status": status,
        "rawRuntimeSha256": raw_closure["runtime_log_sha256"],
        "compactRuntimeSha256": compact_closure["runtime_log_sha256"],
        "normalizedEventsEqual": raw_trace["events"] == compact_trace["events"],
        "latestTerminalReceiptEqual": latest_raw == latest_compact,
        "finalFencedObservationEqual": _final_observation(raw_trace)
        == _final_observation(compact_trace),
        "lifecycleClassEqual": raw_closure["terminal_marker"]
        == compact_closure["terminal_marker"],
        "shadowStatus": "unproven",
        "shadowReason": "independent_judgment_required",
    }
    _write_json(output_root / "v2-parity.json", record)
    return record


def write_evidence_manifest(root: Path, manifest_path: Path) -> dict[str, Any]:
    entries = {}
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        if relative in _MANIFEST_EXCLUSIONS:
            continue
        measured = _measure(path)
        entries[relative] = measured
    manifest = {
        "schema": "rook.evidence_manifest:v1",
        "root": root.resolve().as_posix(),
        "entryCount": len(entries),
        "entries": entries,
    }
    _write_json(manifest_path, manifest)
    return manifest


def _seal_and_verify(output_root: Path) -> dict[str, Any]:
    manifest_path = output_root / "evidence-manifest.json"
    manifest = write_evidence_manifest(output_root, manifest_path)
    verification = verify_evidence_manifest(output_root, manifest_path)
    verification["manifestSha256"] = _measure(manifest_path)["sha256"]
    _write_json(output_root / "manifest-verification.json", verification)
    if verification["mismatches"]:
        raise RuntimeError("qualification_manifest_invalid")
    return {"entryCount": manifest["entryCount"], **verification}


def run_qualification(protocol_path: Path) -> dict[str, Any]:
    protocol_path = Path(protocol_path).resolve()
    protocol = validate_qualification_protocol(_load_json(protocol_path))
    source_custody = verify_source_evidence(protocol)
    output_root = Path(protocol["outputRoot"])
    if output_root.exists():
        raise ValueError("output_root_exists")
    output_root.mkdir(parents=True)
    (output_root / "protocol.json").write_bytes(protocol_path.read_bytes())
    _write_json(output_root / "source-custody.json", source_custody)
    started = time.monotonic()
    _run_precontact(protocol, output_root)
    replay_a = _run_replay(protocol, output_root / "replay-a")
    replay_b = _run_replay(protocol, output_root / "replay-b")

    compact_a = replay_a["retainedPath"]
    compact_b = replay_b["retainedPath"]
    custody_a = replay_a["custodyPath"]
    custody_b = replay_b["custodyPath"]
    deterministic = _measure(compact_a) == _measure(compact_b) and (
        custody_a.read_bytes() == custody_b.read_bytes()
    )
    raw_runtime = Path(protocol["sourceEvidence"]["runtimeLog"]["path"])
    compact_protocol = {"primeEventCapture": protocol["captureConfig"]}
    reconstructed = capture.reconstruct_terminal_assistant_messages(
        compact_protocol, replay_a["root"]
    )
    raw_terminal = _raw_terminal_assistant_messages(raw_runtime)
    reconstruction_pass = reconstructed == raw_terminal
    row_parity = _independent_row_parity(raw_runtime, compact_a)
    passthrough_pass = row_parity["status"] == "pass"
    v2_parity = _run_v2_parity(
        protocol, output_root, raw_runtime, compact_a
    )
    expected = protocol["expected"]
    custody = replay_a["custody"]
    custody_bytes = custody_a.stat().st_size
    persisted_bytes = custody["retained"]["bytes"] + custody_bytes
    retained_ratio = persisted_bytes / custody["source"]["bytes"]
    assertions = {
        "source": custody["source"]
        == {
            "bytes": expected["sourceBytes"],
            "maxRowBytes": custody["source"]["maxRowBytes"],
            "rows": expected["sourceRows"],
            "sha256": expected["sourceSha256"],
            "stdoutEof": True,
        },
        "compactedMessageUpdates": custody["retained"]["compactedMessageUpdates"]
        == expected["compactedMessageUpdates"],
        "rawFallbackMessageUpdates": custody["retained"]["rawFallbackMessageUpdates"]
        == expected["rawFallbackMessageUpdates"],
        "retainedRatio": retained_ratio <= expected["maxRetainedRatio"],
        "determinism": deterministic,
        "terminalReconstruction": reconstruction_pass,
        "independentRowParity": row_parity["status"] == "pass"
        and row_parity["sourceRows"] == expected["sourceRows"]
        and row_parity["retainedRows"] == expected["sourceRows"]
        and row_parity["compactedMessageUpdates"]
        == expected["compactedMessageUpdates"]
        and row_parity["rawFallbackMessageUpdates"]
        == expected["rawFallbackMessageUpdates"],
        "passthroughParity": passthrough_pass,
        "v2Parity": v2_parity["status"] == "pass",
        "liveContact": expected["liveContact"] is False,
    }
    result = {
        "schema": RESULT_SCHEMA,
        "status": "qualified" if all(assertions.values()) else "not_qualified",
        "source": custody["source"],
        "retained": custody["retained"],
        "custodyBytes": custody_bytes,
        "persistedBytes": persisted_bytes,
        "retainedRatio": retained_ratio,
        "reduction": 1 - retained_ratio,
        "determinism": "pass" if deterministic else "fail",
        "terminalReconstruction": "pass" if reconstruction_pass else "fail",
        "passthroughParity": "pass" if passthrough_pass else "fail",
        "rowParity": row_parity,
        "v2Parity": v2_parity,
        "assertions": assertions,
        "elapsedSeconds": time.monotonic() - started,
        "liveContact": False,
    }
    _write_json(output_root / "qualification-result.json", result)
    _seal_and_verify(output_root)
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    result = run_qualification(_parser().parse_args(argv).protocol)
    print(json.dumps(result, ensure_ascii=True, allow_nan=False, separators=(",", ":")))
    return 0 if result["status"] == "qualified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
