"""Reconcile a sealed Prime compaction trace without contacting live systems."""

from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
import shutil
from typing import Any

from rook import gh_behavioral_acceptance as acceptance_v1
from rook import gh_behavioral_acceptance_v2 as acceptance_v2


SCHEMA = "rook.experiment.prime_compaction_trace_reconciliation:v1"
_SHA256 = re.compile(r"^[0-9A-F]{64}$")
_MANIFEST_EXCLUSIONS = {"evidence-manifest.json", "manifest-verification.json"}
_TYPE_PREFIX = re.compile(br'^\{"type":"([^"]+)"')


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _write_json(path: Path, value: Any) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes(acceptance_v1.canonical_json_bytes(value))


def _load_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _valid_reference(value: Any) -> bool:
    return (
        type(value) is dict
        and set(value) == {"path", "sha256"}
        and isinstance(value["path"], str)
        and Path(value["path"]).is_absolute()
        and isinstance(value["sha256"], str)
        and _SHA256.fullmatch(value["sha256"]) is not None
    )


def _validate_protocol(value: Any) -> dict[str, Any]:
    if (
        type(value) is not dict
        or set(value)
        != {
            "schema",
            "mode",
            "outputRoot",
            "sourceEvidence",
            "owners",
            "runner",
        }
        or value["schema"] != SCHEMA
        or value["mode"] != "offline_only"
        or not isinstance(value["outputRoot"], str)
        or not Path(value["outputRoot"]).is_absolute()
    ):
        raise ValueError("protocol_invalid")
    source = value["sourceEvidence"]
    if (
        type(source) is not dict
        or set(source)
        != {
            "root",
            "globalManifest",
            "rowRoot",
            "rowManifest",
            "sourceLog",
            "runtimeLog",
            "processResult",
            "historicalEvaluation",
        }
        or not isinstance(source["root"], str)
        or not Path(source["root"]).is_absolute()
        or not isinstance(source["rowRoot"], str)
        or not Path(source["rowRoot"]).is_absolute()
        or any(
            not _valid_reference(source[key])
            for key in {
                "globalManifest",
                "rowManifest",
                "sourceLog",
                "runtimeLog",
                "processResult",
                "historicalEvaluation",
            }
        )
    ):
        raise ValueError("protocol_invalid")
    owners = value["owners"]
    if (
        type(owners) is not dict
        or set(owners) != {"v1", "v2"}
        or not _valid_reference(owners["v1"])
        or not _valid_reference(owners["v2"])
    ):
        raise ValueError("protocol_invalid")
    if not _valid_reference(value["runner"]):
        raise ValueError("protocol_invalid")

    root = Path(source["root"]).resolve()
    row_root = Path(source["rowRoot"]).resolve()
    output_root = Path(value["outputRoot"]).resolve()
    try:
        row_root.relative_to(root)
    except ValueError as exc:
        raise ValueError("protocol_invalid") from exc
    if output_root == root or output_root.is_relative_to(root):
        raise ValueError("protocol_invalid")
    if Path(source["globalManifest"]["path"]).resolve() != root / "evidence-manifest.json":
        raise ValueError("protocol_invalid")
    if Path(source["rowManifest"]["path"]).resolve() != row_root / "evidence-manifest.json":
        raise ValueError("protocol_invalid")
    for key in {"sourceLog", "runtimeLog", "processResult", "historicalEvaluation"}:
        try:
            Path(source[key]["path"]).resolve().relative_to(row_root)
        except ValueError as exc:
            raise ValueError("protocol_invalid") from exc
    return value


def verify_evidence_manifest(
    root: Path,
    manifest_path: Path,
    *,
    hash_cache: dict[Path, str] | None = None,
) -> dict[str, Any]:
    root = Path(root).resolve()
    manifest = _load_json(manifest_path)
    mismatches: list[str] = []
    if (
        type(manifest) is not dict
        or set(manifest) != {"schema", "root", "entryCount", "entries"}
        or manifest.get("schema") != "rook.evidence_manifest:v1"
        or not isinstance(manifest.get("root"), str)
        or Path(manifest["root"]).resolve() != root
        or type(manifest.get("entryCount")) is not int
        or type(manifest.get("entries")) is not dict
        or manifest.get("entryCount") != len(manifest.get("entries", {}))
    ):
        return {"entryCount": None, "mismatches": ["manifest_shape"]}
    cache = hash_cache if hash_cache is not None else {}
    for relative, expected in manifest["entries"].items():
        relative_path = Path(relative)
        if (
            not isinstance(relative, str)
            or relative_path.is_absolute()
            or ".." in relative_path.parts
            or type(expected) is not dict
            or set(expected) != {"bytes", "sha256"}
            or type(expected["bytes"]) is not int
            or not isinstance(expected["sha256"], str)
            or _SHA256.fullmatch(expected["sha256"]) is None
        ):
            mismatches.append(str(relative))
            continue
        path = (root / relative_path).resolve()
        if not path.is_file() or path.stat().st_size != expected["bytes"]:
            mismatches.append(relative)
            continue
        if path not in cache:
            cache[path] = _sha(path)
        if cache[path] != expected["sha256"]:
            mismatches.append(relative)
    retained = set(manifest["entries"])
    actual = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
        and path.relative_to(root).as_posix() not in _MANIFEST_EXCLUSIONS
    }
    mismatches.extend(
        f"unexpected:{relative}" for relative in sorted(actual - retained)
    )
    return {"entryCount": manifest["entryCount"], "mismatches": mismatches}


def _verify_reference(value: dict[str, str], cache: dict[Path, str]) -> None:
    path = Path(value["path"]).resolve()
    if not path.is_file():
        raise ValueError("source_evidence_mismatch")
    if path not in cache:
        cache[path] = _sha(path)
    if cache[path] != value["sha256"]:
        raise ValueError("source_evidence_mismatch")


def _verify_source_evidence(protocol: dict[str, Any]) -> dict[str, Any]:
    source = protocol["sourceEvidence"]
    cache: dict[Path, str] = {}
    for key in {
        "globalManifest",
        "rowManifest",
        "sourceLog",
        "runtimeLog",
        "processResult",
        "historicalEvaluation",
    }:
        _verify_reference(source[key], cache)
    for key, module_path in {
        "v1": Path(acceptance_v1.__file__).resolve(),
        "v2": Path(acceptance_v2.__file__).resolve(),
    }.items():
        owner = protocol["owners"][key]
        if Path(owner["path"]).resolve() != module_path:
            raise ValueError("source_evidence_mismatch")
        _verify_reference(owner, cache)
    runner = protocol["runner"]
    if Path(runner["path"]).resolve() != Path(__file__).resolve():
        raise ValueError("source_evidence_mismatch")
    _verify_reference(runner, cache)

    global_result = verify_evidence_manifest(
        Path(source["root"]),
        Path(source["globalManifest"]["path"]),
        hash_cache=cache,
    )
    row_result = verify_evidence_manifest(
        Path(source["rowRoot"]),
        Path(source["rowManifest"]["path"]),
        hash_cache=cache,
    )
    if global_result["mismatches"] or row_result["mismatches"]:
        raise ValueError("source_evidence_mismatch")
    return {
        "schema": "rook.experiment.prime_compaction_source_custody:v1",
        "globalManifest": global_result,
        "rowManifest": row_result,
        "verifiedReferences": {
            key: value["sha256"]
            for key, value in source.items()
            if type(value) is dict and "sha256" in value
        },
        "owners": {
            key: protocol["owners"][key]["sha256"] for key in ("v1", "v2")
        },
        "runner": protocol["runner"]["sha256"],
        "liveContact": False,
    }


def analyze_prime_runtime(path: Path) -> dict[str, Any]:
    type_counts: dict[str, dict[str, int]] = defaultdict(
        lambda: {"rows": 0, "bytes": 0, "maxRowBytes": 0}
    )
    digest = hashlib.sha256()
    line_digests: dict[bytes, int] = defaultdict(int)
    total_rows = 0
    total_bytes = 0
    image_rows = 0
    image_row_bytes = 0
    update_subtypes: dict[str, dict[str, int]] = defaultdict(
        lambda: {"rows": 0, "bytes": 0}
    )
    update_delta_bytes = 0
    updates_with_partial = 0
    update_partial_serialized_bytes = 0
    with Path(path).open("rb") as stream:
        for raw_line in stream:
            total_rows += 1
            total_bytes += len(raw_line)
            digest.update(raw_line)
            match = _TYPE_PREFIX.match(raw_line)
            if match is not None:
                event_type = match.group(1).decode("utf-8", errors="strict")
            else:
                try:
                    parsed = json.loads(raw_line)
                    event_type = (
                        parsed.get("type", "unknown")
                        if type(parsed) is dict
                        and isinstance(parsed.get("type", "unknown"), str)
                        else "unknown"
                    )
                except (UnicodeDecodeError, json.JSONDecodeError):
                    event_type = "unknown"
            stats = type_counts[event_type]
            stats["rows"] += 1
            stats["bytes"] += len(raw_line)
            stats["maxRowBytes"] = max(stats["maxRowBytes"], len(raw_line))
            line_digests[hashlib.sha256(raw_line).digest()] += 1
            if b'"type":"image"' in raw_line or b"data:image/" in raw_line:
                image_rows += 1
                image_row_bytes += len(raw_line)
            if event_type == "message_update":
                try:
                    parsed_update = json.loads(raw_line)
                    update = parsed_update.get("assistantMessageEvent", {})
                    subtype = (
                        update.get("type", "unknown")
                        if type(update) is dict
                        and isinstance(update.get("type", "unknown"), str)
                        else "unknown"
                    )
                    update_subtypes[subtype]["rows"] += 1
                    update_subtypes[subtype]["bytes"] += len(raw_line)
                    delta = update.get("delta") if type(update) is dict else None
                    if isinstance(delta, str):
                        update_delta_bytes += len(delta.encode("utf-8"))
                    if type(update) is dict and "partial" in update:
                        updates_with_partial += 1
                        update_partial_serialized_bytes += len(
                            json.dumps(
                                update["partial"],
                                ensure_ascii=False,
                                separators=(",", ":"),
                            ).encode("utf-8")
                        )
                except (UnicodeDecodeError, json.JSONDecodeError):
                    update_subtypes["invalid"]["rows"] += 1
                    update_subtypes["invalid"]["bytes"] += len(raw_line)
    duplicate_rows = sum(count - 1 for count in line_digests.values() if count > 1)
    update_bytes = type_counts.get("message_update", {}).get("bytes", 0)
    return {
        "schema": "rook.experiment.prime_runtime_efficiency_attribution:v1",
        "runtimeLogSha256": digest.hexdigest().upper(),
        "totalRows": total_rows,
        "totalBytes": total_bytes,
        "rowsByType": dict(sorted(type_counts.items())),
        "messageUpdateByteFraction": (
            update_bytes / total_bytes if total_bytes else 0.0
        ),
        "messageUpdateSubtypes": dict(sorted(update_subtypes.items())),
        "messageUpdateDeltaBytes": update_delta_bytes,
        "messageUpdatesWithPartial": updates_with_partial,
        "messageUpdatePartialSerializedBytes": update_partial_serialized_bytes,
        "exactDuplicateRows": duplicate_rows,
        "imageBearingRows": image_rows,
        "imageBearingRowBytes": image_row_bytes,
    }


def _process_state(path: Path) -> dict[str, Any]:
    value = _load_json(path)
    try:
        exit_code = value["exitCode"]
        stdout_eof = value["stdoutEof"]
        children = value["ownedChildPids"]
    except (KeyError, TypeError) as exc:
        raise ValueError("process_result_invalid") from exc
    if type(exit_code) is not int or stdout_eof is not True or type(children) is not list:
        raise ValueError("process_result_invalid")
    return {
        "terminated": True,
        "stdout_eof": True,
        "owned_child_pids": children,
        "exit_code": exit_code,
    }


def _final_fenced_observation(
    trace: dict[str, Any], receipt: dict[str, Any]
) -> dict[str, Any]:
    events = trace["events"]
    candidates = []
    for event in events:
        if (
            event["target"] != "gh_snapshot"
            or event["arguments"].get("readiness_receipt_id")
            != receipt["receipt_id"]
            or event["result"] is None
            or event["result"].get("success") is not True
            or type(event["result"].get("data")) is not dict
        ):
            continue
        data = event["result"]["data"]
        fence = data.get("readiness_fence")
        if type(fence) is dict and fence.get("readiness_receipt_id") == receipt["receipt_id"]:
            candidates.append((event, data))
    if not candidates or candidates[-1][0]["sequence"] != len(events) - 1:
        raise ValueError("final_fenced_observation_missing")
    event, data = candidates[-1]
    components = data.get("components")
    flows = data.get("flows")
    if type(components) is not list or type(flows) is not list:
        raise ValueError("final_fenced_observation_invalid")
    projected_items = 0
    for component in components:
        if type(component) is not dict or type(component.get("outputs")) is not list:
            continue
        for output in component["outputs"]:
            count = output.get("data", {}).get("count") if type(output) is dict else None
            if type(count) is int and count >= 0:
                projected_items += count
    return {
        "sourceSequence": event["sequence"],
        "receiptId": receipt["receipt_id"],
        "componentCount": len(components),
        "flowCount": len(flows),
        "projectedOutputItemCount": projected_items,
        "diagnostics": data.get("diagnostics"),
        "readinessFence": data["readiness_fence"],
    }


def write_evidence_manifest(root: Path, manifest_path: Path) -> dict[str, Any]:
    entries: dict[str, dict[str, Any]] = {}
    for path in sorted(item for item in Path(root).rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        if relative in _MANIFEST_EXCLUSIONS:
            continue
        entries[relative] = {"bytes": path.stat().st_size, "sha256": _sha(path)}
    manifest = {
        "schema": "rook.evidence_manifest:v1",
        "root": Path(root).resolve().as_posix(),
        "entryCount": len(entries),
        "entries": entries,
    }
    _write_json(manifest_path, manifest)
    return manifest


def run_reconciliation(protocol_path: Path) -> dict[str, Any]:
    protocol = _validate_protocol(_load_json(protocol_path))
    output_root = Path(protocol["outputRoot"])
    if output_root.exists():
        raise ValueError("output_root_exists")
    custody = _verify_source_evidence(protocol)

    source = protocol["sourceEvidence"]
    output_root.mkdir(parents=True)
    try:
        copied_source = output_root / "source-v2.jsonl"
        shutil.copyfile(source["sourceLog"]["path"], copied_source)
        shutil.copyfile(protocol_path, output_root / "protocol.json")
        closure, trace = acceptance_v2.seal_and_normalize_prime_source_log(
            copied_source,
            Path(source["runtimeLog"]["path"]),
            _process_state(Path(source["processResult"]["path"])),
        )
        receipt, receipt_error = acceptance_v1._latest_terminal_receipt(trace)
        if receipt_error is not None or receipt is None:
            raise ValueError(receipt_error or "latest_terminal_receipt_missing")
        observation = _final_fenced_observation(trace, receipt)
        efficiency = analyze_prime_runtime(Path(source["runtimeLog"]["path"]))
        if efficiency["runtimeLogSha256"] != source["runtimeLog"]["sha256"]:
            raise ValueError("source_evidence_mismatch")
        result = {
            "schema": "rook.experiment.prime_compaction_shadow_evaluation:v1",
            "status": "unproven",
            "reason": "independent_judgment_required",
            "traceAdmission": "pass",
            "latestReceiptId": receipt["receipt_id"],
            "finalObservation": observation,
            "liveContact": False,
        }
        _write_json(output_root / "input-custody.json", custody)
        _write_json(output_root / "source-closure-v2.json", closure)
        _write_json(output_root / "authoring-trace-v2.json", trace)
        _write_json(output_root / "latest-terminal-receipt.json", receipt)
        _write_json(output_root / "retained-final-observation.json", observation)
        _write_json(output_root / "shadow-evaluation-v2.json", result)
        _write_json(output_root / "trace-efficiency-attribution.json", efficiency)
        write_evidence_manifest(output_root, output_root / "evidence-manifest.json")
        verification = verify_evidence_manifest(
            output_root, output_root / "evidence-manifest.json"
        )
        _write_json(output_root / "manifest-verification.json", verification)
        if verification["mismatches"]:
            raise ValueError("output_manifest_mismatch")
        return result
    except Exception:
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", required=True, type=Path)
    args = parser.parse_args()
    result = run_reconciliation(args.protocol)
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
