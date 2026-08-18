"""Run the bounded Qwen3.8 Grasshopper self-termination campaign.

The runner owns experimental custody and resource enforcement. It deliberately
does not provide runtime semantic feedback to the Actor.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import threading
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROTOCOL = (
    ROOT
    / "docs"
    / "superpowers"
    / "experiments"
    / "2026-08-18-qwen38-self-termination-campaign-v3.json"
)
POINT_ACCEPTANCE = ROOT / "scripts" / "grasshopper_point_row_acceptance.json"
PREFLIGHT_SCRIPT = ROOT / "scripts" / "prime_goal_kernel_preflight.ts"
_MANIFEST_EXCLUSIONS = {"evidence-manifest.json", "manifest-verification.json"}


def _canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(_canonical_bytes(value))
        stream.flush()
        os.fsync(stream.fileno())


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


@dataclass(frozen=True)
class CampaignLimits:
    wall_clock_seconds: int
    gateway_events: int
    provider_tokens: int
    prime_goal_tokens: int

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "CampaignLimits":
        names = {
            "wallClockSecondsPerRun": "wall_clock_seconds",
            "gatewayEventsPerRun": "gateway_events",
            "providerReportedTokensPerRun": "provider_tokens",
            "primeGoalTokenBudget": "prime_goal_tokens",
        }
        parsed: dict[str, int] = {}
        for source, target in names.items():
            if source not in value:
                raise ValueError(f"limit_missing:{source}")
            item = value[source]
            if type(item) is not int or item <= 0:
                raise ValueError(f"limit_invalid:{source}")
            parsed[target] = item
        if parsed["provider_tokens"] != parsed["prime_goal_tokens"]:
            raise ValueError("token_budget_mismatch")
        return cls(**parsed)


def validate_protocol(protocol: dict[str, Any]) -> dict[str, Any]:
    if type(protocol) is not dict or protocol.get("schema") != (
        "rook.experiment.qwen38_self_termination_campaign:v3"
    ):
        raise ValueError("protocol_invalid")
    limits = CampaignLimits.from_mapping(protocol.get("limits", {}))
    prime = protocol.get("prime")
    if type(prime) is not dict or prime.get("settings") != {
        "enableBuiltinSkills": True,
        "packages": [],
        "extensions": [],
    }:
        raise ValueError("builtin_skills_not_enabled")
    tasks = protocol.get("tasks")
    order = protocol.get("executionOrder")
    if type(tasks) is not dict or order != ["T3", "T1", "T2", "T4"]:
        raise ValueError("task_order_invalid")
    if protocol.get("smokeTask") != "T3" or set(tasks) != set(order):
        raise ValueError("smoke_task_invalid")
    versioned = protocol.get("versionedInputs")
    if type(versioned) is not dict:
        raise ValueError("versioned_inputs_invalid")
    for field in ("skillSha256", "checkpointSha256", "adapterInitSha256"):
        digest = versioned.get(field)
        if (
            type(digest) is not str
            or len(digest) != 64
            or any(character not in "0123456789ABCDEF" for character in digest)
        ):
            raise ValueError(f"versioned_hash_invalid:{field}")
    python_environment = protocol.get("pythonEnvironment")
    if type(python_environment) is not dict or set(python_environment) != {
        "pythonPathEntries",
        "dllPathEntries",
        "manifestRoots",
    }:
        raise ValueError("python_environment_contract_invalid")
    for field in ("pythonPathEntries", "dllPathEntries"):
        entries = python_environment.get(field)
        if (
            type(entries) is not list
            or not entries
            or len(entries) != len(set(entries))
            or any(type(item) is not str or not item or not Path(item).is_absolute() for item in entries)
        ):
            raise ValueError("python_environment_contract_invalid")
    manifest_roots = python_environment.get("manifestRoots")
    if type(manifest_roots) is not dict or not manifest_roots:
        raise ValueError("python_environment_contract_invalid")
    for name, manifest in manifest_roots.items():
        if (
            type(name) is not str
            or not name
            or type(manifest) is not dict
            or set(manifest) != {
                "path",
                "entryCount",
                "totalBytes",
                "manifestSha256",
            }
            or type(manifest.get("path")) is not str
            or not Path(manifest["path"]).is_absolute()
            or type(manifest.get("entryCount")) is not int
            or manifest["entryCount"] <= 0
            or type(manifest.get("totalBytes")) is not int
            or manifest["totalBytes"] <= 0
            or type(manifest.get("manifestSha256")) is not str
            or len(manifest["manifestSha256"]) != 64
            or any(character not in "0123456789ABCDEF" for character in manifest["manifestSha256"])
        ):
            raise ValueError("python_environment_manifest_invalid")
    tool_surface = protocol.get("toolSurface")
    if (
        type(tool_surface) is not dict
        or set(tool_surface)
        != {
            "profile",
            "serializedCatalogCount",
            "serializedCatalogBytes",
            "serializedCatalogSha256",
        }
        or tool_surface.get("profile") != "full"
        or type(tool_surface.get("serializedCatalogCount")) is not int
        or type(tool_surface.get("serializedCatalogBytes")) is not int
    ):
        raise ValueError("tool_surface_contract_invalid")
    for task_id in order:
        task = tasks[task_id]
        if (
            type(task) is not dict
            or task.get("id") != task_id
            or type(task.get("prompt")) is not str
            or not task["prompt"].strip()
        ):
            raise ValueError(f"task_invalid:{task_id}")
    _ = limits
    return protocol


def validate_evidence_root(path: Path) -> Path:
    resolved = Path(path)
    lowered = resolved.as_posix().lower().rstrip("/")
    if "/appdata/local/temp/" in lowered or lowered.endswith("/appdata/local/temp"):
        raise ValueError("durable_evidence_root_required")
    if not lowered.startswith("c:/udev/rookevidence/"):
        raise ValueError("durable_evidence_root_required")
    return resolved


def build_prime_launch(
    protocol: dict[str, Any],
    *,
    task: dict[str, Any],
    row_root: Path,
    target: dict[str, Any],
) -> tuple[list[str], dict[str, str]]:
    validate_protocol(protocol)
    limits = CampaignLimits.from_mapping(protocol["limits"])
    prime = protocol["prime"]
    command = [
        prime["bashPath"],
        prime["launcherPath"],
        "--dist",
        "--cwd",
        str(row_root),
        "--offline",
        "--no-extensions",
        "--mode",
        "json",
        "--model",
        prime["model"],
        "--thinking",
        prime["thinkingLevel"],
        "--goal",
        task["prompt"],
        "--goal-token-budget",
        str(limits.prime_goal_tokens),
        "Begin the active goal now.",
    ]
    source_log = row_root / "operator" / "source.jsonl"
    adapter_source = row_root / "agent" / "skills" / "rook-full" / "src"
    environment = python_runtime_environment(
        protocol, dict(os.environ), adapter_source
    )
    environment.update(
        {
            "PRIME_AGENT_CODING_AGENT_DIR": str(row_root / "agent"),
            "PRIME_AGENT_KERNEL_PYTHON": prime["sealedKernelPython"],
            "ROOK_GH_AUTHORING_SOURCE_LOG": str(source_log),
            "ROOK_MCP_TARGET_MODE": "panel_locked",
            "ROOK_MCP_TARGET_PROCESS_ID": str(target["processId"]),
            "ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER": str(
                target["documentSerialNumber"]
            ),
            "ROOK_MCP_TOOL_PROFILE": "full",
            "ROOK_GATEWAY_CALL_LIMIT": str(limits.gateway_events),
            "PRIME_AGENT_INTERNAL_LEGACY_OWNED_WORKER_FRONTEND": "1",
            "PI_SKIP_VERSION_CHECK": "1",
        }
    )
    environment.pop("ANTHROPIC_API_KEY", None)
    environment.pop("ANTHROPIC_OAUTH_TOKEN", None)
    return command, environment


def python_runtime_environment(
    protocol: dict[str, Any],
    environment: dict[str, str],
    adapter_source: Path,
) -> dict[str, str]:
    configured = protocol.get("pythonEnvironment")
    if type(configured) is not dict:
        installed = protocol["rookCustody"]["installedPythonRoot"]
        return environment | {"PYTHONPATH": f"{adapter_source};{installed}"}
    python_paths = configured.get("pythonPathEntries")
    dll_paths = configured.get("dllPathEntries")
    if (
        type(python_paths) is not list
        or not python_paths
        or any(type(item) is not str or not item for item in python_paths)
        or type(dll_paths) is not list
        or not dll_paths
        or any(type(item) is not str or not item for item in dll_paths)
    ):
        raise ValueError("python_environment_paths_invalid")
    result = dict(environment)
    result["PYTHONPATH"] = os.pathsep.join(
        [Path(adapter_source).as_posix(), *python_paths]
    )
    existing_path = result.get("PATH", "")
    result["PATH"] = os.pathsep.join(
        [*dll_paths, *([existing_path] if existing_path else [])]
    )
    return result


class RunMonitor:
    def __init__(self, limits: CampaignLimits):
        self.limits = limits
        self.provider_tokens = 0

    def consume_prime_line(self, line: str) -> str | None:
        try:
            value = json.loads(line)
        except (TypeError, ValueError):
            return None
        if type(value) is not dict or value.get("type") != "message_end":
            return None
        message = value.get("message")
        usage = message.get("usage") if type(message) is dict else None
        tokens = usage.get("totalTokens") if type(usage) is dict else None
        if type(tokens) is int and tokens >= 0:
            self.provider_tokens += tokens
        if self.provider_tokens > self.limits.provider_tokens:
            return "provider_token_ceiling"
        return None

    def observe_gateway_count(self, count: int) -> str | None:
        return "gateway_call_ceiling" if count > self.limits.gateway_events else None

    def observe_elapsed(self, seconds: float) -> str | None:
        return "wall_clock_ceiling" if seconds >= self.limits.wall_clock_seconds else None


def _goal_context_text(value: dict[str, Any]) -> str | None:
    if value.get("type") == "goal_context":
        goal = value.get("goal")
        if type(goal) is dict:
            return (
                f"<objective>\n{goal.get('objective')}\n</objective>\n"
                f"- status: {goal.get('status')}\n"
                f"- token budget: {goal.get('token_budget')}"
            )
    if value.get("type") != "session_action_update":
        return None
    actions = value.get("actions")
    follow_ups = actions.get("followUps") if type(actions) is dict else None
    if type(follow_ups) is not list:
        return None
    return next(
        (item for item in follow_ups if type(item) is str and "<goal_context>" in item),
        None,
    )


def goal_context_matches(value: dict[str, Any], objective: str, budget: int) -> bool:
    if value.get("type") == "goal_update":
        goal = value.get("goal")
        return (
            type(goal) is dict
            and goal.get("objective") == objective
            and goal.get("status") == "active"
            and goal.get("tokenBudget") == budget
        )
    message = value.get("message")
    if (
        value.get("type") in {"message_start", "message_end"}
        and type(message) is dict
        and message.get("customType") == "goal_context"
        and type(message.get("content")) is str
    ):
        text = message["content"]
    else:
        text = _goal_context_text(value)
    if text is None:
        return False
    return (
        f"<objective>\n{objective}\n</objective>" in text
        and "- status: active" in text
        and f"- token budget: {budget}" in text
    )


def prime_log_proves_goal_context(
    path: Path, objective: str, budget: int
) -> bool:
    with Path(path).open("r", encoding="utf-8") as stream:
        for line in stream:
            try:
                value = json.loads(line)
            except ValueError:
                continue
            if type(value) is dict and goal_context_matches(value, objective, budget):
                return True
    return False


def validate_preflight_record(
    record: dict[str, Any], expected_python: Path, budget: int
) -> dict[str, Any]:
    expected_keys = {
        "schema",
        "pythonExecutable",
        "goalFile",
        "rlmFile",
        "rookFullFile",
        "goalPreimported",
        "getStatus",
        "getTokenBudget",
        "completeStatus",
        "requests",
        "kernelClosed",
    }
    try:
        valid = (
            type(record) is dict
            and set(record) == expected_keys
            and record["schema"] == "rook.experiment.prime_goal_preflight:v2"
            and Path(record["pythonExecutable"]).resolve() == Path(expected_python).resolve()
            and Path(record["goalFile"]).name == "__init__.py"
            and Path(record["goalFile"]).parent.name == "goal"
            and Path(record["rlmFile"]).name == "__init__.py"
            and Path(record["rlmFile"]).parent.name == "rlm"
            and Path(record["rookFullFile"]).name == "__init__.py"
            and Path(record["rookFullFile"]).parent.name == "rook_full"
            and record["goalPreimported"] is True
            and record["getStatus"] == "active"
            and record["getTokenBudget"] == budget
            and record["completeStatus"] == "complete"
            and record["requests"] == ["goal.get", "goal.complete"]
            and record["kernelClosed"] is True
        )
    except (KeyError, TypeError, ValueError):
        valid = False
    if not valid:
        raise ValueError("preflight_invalid")
    return record


def validate_tool_surface_record(
    record: dict[str, Any], expected: dict[str, Any]
) -> dict[str, Any]:
    if record != {
        "schema": "rook.experiment.tool_surface:v1",
        "profile": expected["profile"],
        "count": expected["serializedCatalogCount"],
        "bytes": expected["serializedCatalogBytes"],
        "sha256": expected["serializedCatalogSha256"],
    }:
        raise ValueError("tool_surface_mismatch")
    return record


def write_evidence_manifest(root: Path, manifest_path: Path) -> dict[str, Any]:
    root = Path(root)
    entries: dict[str, dict[str, Any]] = {}
    for path in sorted((item for item in root.rglob("*") if item.is_file())):
        relative = path.relative_to(root).as_posix()
        if relative in _MANIFEST_EXCLUSIONS:
            continue
        entries[relative] = {"sha256": _sha(path), "bytes": path.stat().st_size}
    manifest = {
        "schema": "rook.evidence_manifest:v1",
        "root": root.as_posix(),
        "entryCount": len(entries),
        "entries": entries,
    }
    _write_json(manifest_path, manifest)
    return manifest


def verify_evidence_manifest(root: Path, manifest_path: Path) -> dict[str, Any]:
    manifest = _load_json(manifest_path)
    mismatches: list[str] = []
    for relative, expected in manifest.get("entries", {}).items():
        path = Path(root) / Path(relative)
        if (
            not path.is_file()
            or path.stat().st_size != expected.get("bytes")
            or _sha(path) != expected.get("sha256")
        ):
            mismatches.append(relative)
    retained = set(manifest.get("entries", {}))
    actual = {
        path.relative_to(root).as_posix()
        for path in Path(root).rglob("*")
        if path.is_file() and path.relative_to(root).as_posix() not in _MANIFEST_EXCLUSIONS
    }
    mismatches.extend(f"unexpected:{relative}" for relative in sorted(actual - retained))
    return {"entryCount": manifest.get("entryCount"), "mismatches": mismatches}


def smoke_allows_cohort(result: dict[str, Any]) -> bool:
    return result == {
        "semanticStatus": "pass",
        "goalStatus": "complete",
        "budgetStatus": "pass",
        "custodyStatus": "pass",
    }


def cohort_after_smoke(
    protocol: dict[str, Any], smoke_result: dict[str, Any]
) -> list[str]:
    if not smoke_allows_cohort(smoke_result):
        return []
    return [item for item in protocol["executionOrder"] if item != protocol["smokeTask"]]


def _copy_versioned_inputs(protocol: dict[str, Any], row_root: Path) -> None:
    agent = row_root / "agent"
    agent.mkdir(parents=True)
    _write_json(agent / "settings.json", protocol["prime"]["settings"])
    _write_json(agent / "models.json", protocol["prime"]["models"])
    _write_json(agent / "auth.json", {})
    skill_source = ROOT / protocol["versionedInputs"]["skillPath"]
    checkpoint_source = ROOT / protocol["versionedInputs"]["checkpointPath"]
    skill_target = agent / "skills" / "prime-execute-grasshopper"
    (skill_target / "references").mkdir(parents=True)
    shutil.copy2(skill_source, skill_target / "SKILL.md")
    shutil.copy2(
        checkpoint_source,
        skill_target / "references" / "checkpoint-protocol.md",
    )
    adapter_source = ROOT / protocol["versionedInputs"]["adapterRoot"]
    shutil.copytree(adapter_source, agent / "skills" / "rook-full")
    (agent / "sessions").mkdir()


def _write_row_input_custody(
    protocol: dict[str, Any], task: dict[str, Any], row_root: Path, target: dict[str, Any]
) -> dict[str, Any]:
    agent = row_root / "agent"
    operator = row_root / "operator"
    files = {
        "settings": agent / "settings.json",
        "models": agent / "models.json",
        "skill": agent / "skills" / "prime-execute-grasshopper" / "SKILL.md",
        "checkpoint": agent
        / "skills"
        / "prime-execute-grasshopper"
        / "references"
        / "checkpoint-protocol.md",
        "adapter": agent / "skills" / "rook-full" / "src" / "rook_full" / "__init__.py",
        "target": operator / "target.json",
    }
    custody = {
        "schema": "rook.experiment.qwen38_campaign_row_input_custody:v1",
        "task": task,
        "taskSha256": hashlib.sha256(_canonical_bytes(task)).hexdigest().upper(),
        "target": target,
        "files": {
            name: {
                "path": path.relative_to(row_root).as_posix(),
                "sha256": _sha(path),
                "bytes": path.stat().st_size,
            }
            for name, path in files.items()
        },
    }
    versioned = protocol["versionedInputs"]
    expected = {
        "skill": versioned["skillSha256"],
        "checkpoint": versioned["checkpointSha256"],
        "adapter": versioned["adapterInitSha256"],
    }
    for name, digest in expected.items():
        if custody["files"][name]["sha256"] != digest:
            raise RuntimeError(f"staged_input_mismatch:{name}")
    _write_json(operator / "input-custody.json", custody)
    return custody


def _verify_sha(path: Path, expected: str, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise RuntimeError(f"custody_missing:{label}")
    actual = _sha(path)
    if actual != expected:
        raise RuntimeError(f"custody_mismatch:{label}")
    return {"path": path.as_posix(), "sha256": actual, "bytes": path.stat().st_size}


def _verify_model_blobs(model_custody: dict[str, Any]) -> dict[str, Any]:
    manifest = _load_json(Path(model_custody["manifestPath"]))
    actual_config = manifest.get("config") if type(manifest) is dict else None
    actual_layers = manifest.get("layers") if type(manifest) is dict else None
    expected_config = model_custody["config"]
    expected_layers = model_custody["layers"]
    if (
        type(actual_config) is not dict
        or {
            "digest": actual_config.get("digest"),
            "size": actual_config.get("size"),
        }
        != expected_config
        or type(actual_layers) is not list
        or [
            {"digest": item.get("digest"), "size": item.get("size")}
            for item in actual_layers
            if type(item) is dict
        ]
        != expected_layers
    ):
        raise RuntimeError("custody_mismatch:model_manifest_content")
    blobs: list[dict[str, Any]] = []
    for item in [expected_config, *expected_layers]:
        digest = item["digest"]
        path = Path(model_custody["blobRoot"]) / digest.replace(":", "-")
        if not path.is_file() or path.stat().st_size != item["size"]:
            raise RuntimeError(f"custody_mismatch:model_blob:{digest}")
        blobs.append(
            {"digest": digest, "path": path.as_posix(), "bytes": path.stat().st_size}
        )
    return {"config": expected_config, "layers": expected_layers, "blobs": blobs}


def _verify_prime_runtime_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    root = Path(bundle["root"])
    entries: dict[str, dict[str, Any]] = {}
    for subtree in bundle["subtrees"]:
        subtree_root = root / subtree
        if not subtree_root.is_dir():
            raise RuntimeError(f"custody_missing:prime_bundle:{subtree}")
        for path in sorted(item for item in subtree_root.rglob("*") if item.is_file()):
            entries[path.relative_to(root).as_posix()] = {
                "sha256": _sha(path),
                "bytes": path.stat().st_size,
            }
    manifest_sha = hashlib.sha256(_canonical_bytes(entries)).hexdigest().upper()
    total_bytes = sum(item["bytes"] for item in entries.values())
    if (
        len(entries) != bundle["entryCount"]
        or total_bytes != bundle["totalBytes"]
        or manifest_sha != bundle["manifestSha256"]
    ):
        raise RuntimeError("custody_mismatch:prime_runtime_bundle")
    return {
        "root": root.as_posix(),
        "subtrees": bundle["subtrees"],
        "entryCount": len(entries),
        "totalBytes": total_bytes,
        "manifestSha256": manifest_sha,
        "entries": entries,
    }


def path_manifest(root: Path) -> dict[str, Any]:
    root = Path(root)
    if root.is_file():
        paths = [root]
        relative = lambda path: path.name
    elif root.is_dir():
        paths = sorted(item for item in root.rglob("*") if item.is_file())
        relative = lambda path: path.relative_to(root).as_posix()
    else:
        raise RuntimeError(f"python_environment_missing:{root.as_posix()}")
    entries = {
        relative(path): {
            "sha256": _sha(path),
            "bytes": path.stat().st_size,
        }
        for path in paths
    }
    summary = {
        "entryCount": len(entries),
        "totalBytes": sum(item["bytes"] for item in entries.values()),
        "manifestSha256": hashlib.sha256(_canonical_bytes(entries))
        .hexdigest()
        .upper(),
    }
    return {"root": root.as_posix(), "summary": summary, "entries": entries}


def directory_manifest(root: Path) -> dict[str, Any]:
    return path_manifest(root)


def capture_python_environment_custody(
    protocol: dict[str, Any],
) -> dict[str, Any]:
    configured = protocol.get("pythonEnvironment")
    roots = configured.get("manifestRoots") if type(configured) is dict else None
    if type(roots) is not dict or not roots:
        raise ValueError("python_environment_manifest_roots_invalid")
    actual: dict[str, Any] = {}
    mismatches: list[str] = []
    for name, expected in roots.items():
        if type(name) is not str or type(expected) is not dict:
            raise ValueError("python_environment_manifest_root_invalid")
        manifest = path_manifest(Path(expected.get("path", "")))
        actual[name] = manifest
        expected_projection = {
            "entryCount": expected.get("entryCount"),
            "totalBytes": expected.get("totalBytes"),
            "manifestSha256": expected.get("manifestSha256"),
        }
        if manifest["summary"] != expected_projection:
            mismatches.append(name)
    return {
        "schema": "rook.experiment.python_environment_custody:v1",
        "roots": actual,
        "mismatches": mismatches,
    }


def require_python_environment_custody(record: dict[str, Any]) -> dict[str, Any]:
    mismatches = record.get("mismatches")
    if type(mismatches) is not list:
        raise RuntimeError("python_environment_custody_invalid")
    if mismatches:
        raise RuntimeError(f"python_environment_drift:{','.join(mismatches)}")
    return record


def _write_python_environment_custody(
    protocol: dict[str, Any], path: Path
) -> dict[str, Any] | None:
    if "pythonEnvironment" not in protocol:
        return None
    record = capture_python_environment_custody(protocol)
    _write_json(path, record)
    return require_python_environment_custody(record)


def _runtime_custody(protocol: dict[str, Any]) -> dict[str, Any]:
    prime = protocol["prime"]
    prime_commit = subprocess.run(
        ["git", "-C", prime["sourceRoot"], "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if prime_commit != prime["commit"]:
        raise RuntimeError("custody_mismatch:prime_commit")
    repository_commit = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    repository_status = subprocess.run(
        ["git", "-C", str(ROOT), "status", "--porcelain"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    if repository_status:
        raise RuntimeError("custody_mismatch:campaign_repository_dirty")
    node = _verify_sha(Path(prime["nodePath"]), prime["nodeSha256"], "node")
    node_version = subprocess.run(
        [prime["nodePath"], "--version"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if node_version != prime["nodeVersion"]:
        raise RuntimeError("custody_mismatch:node_version")
    versioned = protocol["versionedInputs"]
    skill_path = ROOT / versioned["skillPath"]
    checkpoint_path = ROOT / versioned["checkpointPath"]
    adapter_path = ROOT / versioned["adapterRoot"] / "src" / "rook_full" / "__init__.py"
    files = {
        "rookNativePlugin": _verify_sha(
            Path(protocol["rookCustody"]["nativePluginPath"]),
            protocol["rookCustody"]["nativePluginSha256"],
            "rook_native_plugin",
        ),
        "rookManagedNet8Plugin": _verify_sha(
            Path(protocol["rookCustody"]["managedNet8PluginPath"]),
            protocol["rookCustody"]["managedNet8PluginSha256"],
            "rook_managed_net8_plugin",
        ),
        "ollama": _verify_sha(
            Path(protocol["modelCustody"]["runtimePath"]),
            protocol["modelCustody"]["runtimeSha256"],
            "ollama",
        ),
        "ollamaManifest": _verify_sha(
            Path(protocol["modelCustody"]["manifestPath"]),
            protocol["modelCustody"]["manifestSha256"],
            "ollama_manifest",
        ),
        "rookServer": _verify_sha(
            Path(protocol["rookCustody"]["serverPath"]),
            protocol["rookCustody"]["serverSha256"],
            "rook_server",
        ),
        "rookBehavioralAcceptance": _verify_sha(
            Path(protocol["rookCustody"]["behavioralAcceptancePath"]),
            protocol["rookCustody"]["behavioralAcceptanceSha256"],
            "rook_behavioral_acceptance",
        ),
        "sealedKernel": {
            "path": Path(prime["sealedKernelPython"]).as_posix(),
            "sha256": _sha(Path(prime["sealedKernelPython"])),
        },
        "versionedSkill": _verify_sha(
            skill_path, versioned["skillSha256"], "versioned_skill"
        ),
        "versionedCheckpoint": _verify_sha(
            checkpoint_path,
            versioned["checkpointSha256"],
            "versioned_checkpoint",
        ),
        "versionedAdapter": _verify_sha(
            adapter_path, versioned["adapterInitSha256"], "versioned_adapter"
        ),
        "campaignProtocol": {
            "path": DEFAULT_PROTOCOL.as_posix(),
            "sha256": _sha(DEFAULT_PROTOCOL),
            "bytes": DEFAULT_PROTOCOL.stat().st_size,
        },
        "campaignRunner": {
            "path": Path(__file__).resolve().as_posix(),
            "sha256": _sha(Path(__file__).resolve()),
            "bytes": Path(__file__).resolve().stat().st_size,
        },
        "goalPreflight": {
            "path": PREFLIGHT_SCRIPT.as_posix(),
            "sha256": _sha(PREFLIGHT_SCRIPT),
            "bytes": PREFLIGHT_SCRIPT.stat().st_size,
        },
    }
    return {
        "schema": "rook.experiment.qwen38_campaign_runtime_custody:v1",
        "campaignRepositoryCommit": repository_commit,
        "primeCommit": prime_commit,
        "node": node | {"version": node_version},
        "primeRuntimeBundle": _verify_prime_runtime_bundle(prime["runtimeBundle"]),
        "modelContent": _verify_model_blobs(protocol["modelCustody"]),
        "files": files,
    }


def _run_preflight(
    protocol: dict[str, Any], evidence_root: Path
) -> dict[str, Any]:
    prime_root = Path(protocol["prime"]["sourceRoot"])
    preflight_root = evidence_root / "preflight"
    preflight_root.mkdir()
    command = [
        "node",
        str(prime_root / "node_modules" / "tsx" / "dist" / "cli.mjs"),
        str(PREFLIGHT_SCRIPT),
        str(prime_root),
        str(preflight_root / "kernel-session"),
        str(protocol["limits"]["primeGoalTokenBudget"]),
        str(ROOT / protocol["versionedInputs"]["adapterRoot"]),
    ]
    adapter_source = (
        ROOT
        / protocol["versionedInputs"]["adapterRoot"]
        / "src"
    )
    environment = python_runtime_environment(
        protocol, dict(os.environ), adapter_source
    )
    environment["PRIME_AGENT_KERNEL_PYTHON"] = protocol["prime"][
        "sealedKernelPython"
    ]
    result = subprocess.run(
        command,
        cwd=prime_root,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=180,
    )
    (preflight_root / "stderr.txt").write_text(result.stderr, encoding="utf-8")
    (preflight_root / "stdout.txt").write_text(result.stdout, encoding="utf-8")
    if result.returncode != 0:
        raise RuntimeError(f"prime_goal_preflight_failed:{result.returncode}")
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    record = json.loads(lines[-1])
    validate_preflight_record(
        record,
        Path(protocol["prime"]["sealedKernelPython"]),
        protocol["limits"]["primeGoalTokenBudget"],
    )
    _write_json(preflight_root / "result.json", record)
    return record


def _source_event_count(path: Path) -> int:
    if not path.is_file():
        return 0
    count = 0
    with path.open("r", encoding="utf-8") as stream:
        for line in stream:
            try:
                value = json.loads(line)
            except ValueError:
                continue
            if type(value) is dict and type(value.get("sequence")) is int:
                count += 1
    return count


def _reader(stream, destination: Path, channel: str, output: queue.Queue) -> None:
    with destination.open("xb") as retained:
        for line in iter(stream.readline, ""):
            retained.write(line.encode("utf-8"))
            retained.flush()
            output.put((channel, line))
    output.put((channel, None))


def _kill_tree(pid: int) -> None:
    subprocess.run(
        ["taskkill", "/PID", str(pid), "/T", "/F"],
        check=False,
        capture_output=True,
        text=True,
    )


def _process_snapshot() -> list[dict[str, Any]]:
    script = """
Get-CimInstance Win32_Process | ForEach-Object {
  [pscustomobject]@{
    processId = [int]$_.ProcessId
    parentProcessId = [int]$_.ParentProcessId
    creationDate = if ($_.CreationDate) { $_.CreationDate.ToUniversalTime().ToString('o') } else { $null }
    commandLine = $_.CommandLine
  }
} | ConvertTo-Json -Compress
"""
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError("process_snapshot_failed")
    if not result.stdout.strip():
        return []
    value = json.loads(result.stdout)
    rows = [value] if type(value) is dict else value
    if type(rows) is not list or any(type(item) is not dict for item in rows):
        raise RuntimeError("process_snapshot_invalid")
    return rows


def extend_owned_processes(
    tracked: dict[int, str | None],
    processes: list[dict[str, Any]],
    root_pids: set[int],
) -> dict[int, str | None]:
    by_parent: dict[int, list[int]] = {}
    by_pid: dict[int, dict[str, Any]] = {}
    for process in processes:
        pid = process.get("processId")
        parent = process.get("parentProcessId")
        if type(pid) is not int or type(parent) is not int:
            continue
        by_pid[pid] = process
        by_parent.setdefault(parent, []).append(pid)
    closure = set(root_pids)
    for pid, creation in tracked.items():
        process = by_pid.get(pid)
        if process is not None and process.get("creationDate") == creation:
            closure.add(pid)
    pending = list(closure)
    while pending:
        parent = pending.pop()
        for child in by_parent.get(parent, []):
            if child not in closure:
                closure.add(child)
                pending.append(child)
    updated = dict(tracked)
    for pid in closure:
        process = by_pid.get(pid)
        if process is not None:
            creation = process.get("creationDate")
            identity = creation if type(creation) is str else None
            if pid not in updated or updated[pid] == identity:
                updated[pid] = identity
    return updated


def live_owned_processes(
    tracked: dict[int, str | None],
    processes: list[dict[str, Any]],
    row_marker: str,
) -> list[int]:
    normalized_marker = row_marker.replace("\\", "/").lower()
    live: set[int] = set()
    for process in processes:
        pid = process.get("processId")
        if type(pid) is not int:
            continue
        creation = process.get("creationDate")
        command = process.get("commandLine")
        same_identity = pid in tracked and tracked[pid] == (
            creation if type(creation) is str else None
        )
        marked = (
            type(command) is str
            and normalized_marker in command.replace("\\", "/").lower()
        )
        if same_identity or marked:
            live.add(pid)
    return sorted(live)


def retained_live_processes(
    processes: list[dict[str, Any]], row_marker: str
) -> list[int]:
    parents = {
        item.get("processId"): item.get("parentProcessId")
        for item in processes
        if type(item.get("processId")) is int
        and type(item.get("parentProcessId")) is int
    }
    verifier_ancestry: set[int] = set()
    current = os.getpid()
    while current not in verifier_ancestry and type(current) is int:
        verifier_ancestry.add(current)
        current = parents.get(current)
        if current is None:
            break
    return [
        pid
        for pid in live_owned_processes({}, processes, row_marker)
        if pid not in verifier_ancestry
    ]


def _run_prime_row(
    protocol: dict[str, Any], task: dict[str, Any], row_root: Path, target: dict[str, Any]
) -> dict[str, Any]:
    limits = CampaignLimits.from_mapping(protocol["limits"])
    command, environment = build_prime_launch(
        protocol, task=task, row_root=row_root, target=target
    )
    operator = row_root / "operator"
    operator.mkdir(exist_ok=True)
    source = operator / "source.jsonl"
    source.write_bytes(
        b'{"row_emitter":"prime_rook_adapter","schema":"rook.gh_authoring_source_log:v1"}\n'
    )
    stdout_path = operator / "prime.jsonl"
    stderr_path = operator / "stderr.txt"
    events: queue.Queue = queue.Queue()
    process = subprocess.Popen(
        command,
        cwd=protocol["prime"]["sourceRoot"],
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    assert process.stdout is not None and process.stderr is not None
    readers = [
        threading.Thread(
            target=_reader,
            args=(process.stdout, stdout_path, "stdout", events),
            daemon=True,
        ),
        threading.Thread(
            target=_reader,
            args=(process.stderr, stderr_path, "stderr", events),
            daemon=True,
        ),
    ]
    for thread in readers:
        thread.start()
    monitor = RunMonitor(limits)
    started = time.monotonic()
    last_process_poll = 0.0
    tracked_processes: dict[int, str | None] = {}
    breach: str | None = None
    stdout_eof = False
    goal_context_verified = False
    while (
        process.poll() is None
        or any(thread.is_alive() for thread in readers)
        or not events.empty()
    ):
        try:
            channel, line = events.get(timeout=0.1)
        except queue.Empty:
            channel, line = None, None
        if channel == "stdout" and line is None:
            stdout_eof = True
        elif channel == "stdout" and line is not None:
            breach = breach or monitor.consume_prime_line(line)
            try:
                value = json.loads(line)
            except ValueError:
                value = None
            if type(value) is dict and goal_context_matches(
                value, task["prompt"], limits.prime_goal_tokens
            ):
                goal_context_verified = True
        breach = breach or monitor.observe_gateway_count(_source_event_count(source))
        breach = breach or monitor.observe_elapsed(time.monotonic() - started)
        if time.monotonic() - last_process_poll >= 2.0:
            tracked_processes = extend_owned_processes(
                tracked_processes, _process_snapshot(), {process.pid}
            )
            last_process_poll = time.monotonic()
        if breach is not None and process.poll() is None:
            _kill_tree(process.pid)
    for thread in readers:
        thread.join(timeout=5)
    elapsed = time.monotonic() - started
    exit_code = process.wait(timeout=10)
    final_snapshot = _process_snapshot()
    tracked_processes = extend_owned_processes(
        tracked_processes, final_snapshot, set()
    )
    children = live_owned_processes(
        tracked_processes, final_snapshot, row_root.as_posix()
    )
    for child in children:
        _kill_tree(child)
    if children:
        time.sleep(0.5)
        children = live_owned_processes(
            tracked_processes, _process_snapshot(), row_root.as_posix()
        )
    result = {
        "schema": "rook.experiment.qwen38_campaign_process_result:v1",
        "task": task["id"],
        "rootPid": process.pid,
        "exitCode": exit_code,
        "elapsedSeconds": elapsed,
        "providerReportedTokens": monitor.provider_tokens,
        "gatewayEvents": _source_event_count(source),
        "goalContextVerified": goal_context_verified,
        "limitBreach": breach,
        "stdoutEof": stdout_eof,
        "trackedProcessIdentities": {
            str(pid): creation for pid, creation in sorted(tracked_processes.items())
        },
        "ownedChildPids": children,
    }
    _write_json(operator / "process-result.json", result)
    return result


def _goal_status(row_root: Path) -> str:
    sessions = sorted((row_root / "agent" / "sessions").glob("*.jsonl"))
    if len(sessions) != 1:
        return "unknown"
    status = "unknown"
    with sessions[0].open("r", encoding="utf-8") as stream:
        for line in stream:
            try:
                value = json.loads(line)
            except ValueError:
                continue
            if (
                value.get("type") == "custom"
                and value.get("customType") == "thread_goal_state"
            ):
                goal = value.get("data")
                if type(goal) is dict and type(goal.get("status")) is str:
                    status = goal["status"]
    return status


def _operator_command(
    protocol: dict[str, Any], args: list[str], *, capture: bool = True
) -> subprocess.CompletedProcess:
    environment = {
        **os.environ,
        "PYTHONPATH": protocol["rookCustody"]["installedPythonRoot"],
        "ROOK_MCP_TOOL_PROFILE": "full",
        "ROOK_ENABLE_INTERACTIVE_COMMAND_LEARNING": "0",
    }
    return subprocess.run(
        [
            "C:/Users/bring/AppData/Local/Rook/venv/Scripts/python.exe",
            str(Path(__file__).resolve()),
            *args,
        ],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=capture,
        text=True,
        timeout=180,
    )


def operator_envelope(value: Any) -> dict[str, Any]:
    if type(value) is dict and value.get("success") is False:
        if set(value) == {"success", "data"}:
            return value
        return {"success": False, "data": value.get("data", value.get("error"))}
    return {"success": True, "data": value}


def operator_payload(value: Any, label: str) -> Any:
    envelope = operator_envelope(value)
    if envelope["success"] is not True:
        raise RuntimeError(f"operator_call_failed:{label}")
    return envelope["data"]


def _collect_tool_surface(
    protocol: dict[str, Any], evidence_root: Path
) -> dict[str, Any]:
    output = evidence_root / "tool-surface.json"
    result = _operator_command(
        protocol, ["_operator-tool-surface", "--output", str(output)]
    )
    (evidence_root / "tool-surface-stderr.txt").write_text(
        result.stderr, encoding="utf-8"
    )
    if result.returncode != 0:
        raise RuntimeError(f"tool_surface_collection_failed:{result.returncode}")
    record = _load_json(output)
    return validate_tool_surface_record(record, protocol["toolSurface"])


def _prepare_target(
    protocol: dict[str, Any], task: dict[str, Any], row_root: Path, document_serial: int, process_id: int | None
) -> dict[str, Any]:
    output = row_root / "operator" / "target.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    arguments = [
        "_operator-prepare",
        "--task",
        task["id"],
        "--document-serial",
        str(document_serial),
        "--output",
        str(output),
    ]
    if process_id is not None:
        arguments.extend(["--process-id", str(process_id)])
    result = _operator_command(protocol, arguments)
    if result.returncode != 0:
        raise RuntimeError(f"target_prepare_failed:{result.stderr.strip()}")
    return _load_json(output)


def _post_actor_evaluation(
    protocol: dict[str, Any], task: dict[str, Any], row_root: Path, process_result: dict[str, Any]
) -> str:
    arguments = [
        "_operator-evaluate",
        "--task",
        task["id"],
        "--row-root",
        str(row_root),
        "--exit-code",
        str(process_result["exitCode"]),
    ]
    result = _operator_command(protocol, arguments)
    if result.returncode != 0:
        (row_root / "operator" / "evaluation-error.txt").write_text(
            result.stderr, encoding="utf-8"
        )
        return "incomplete"
    evaluation = _load_json(row_root / "operator" / "hidden-evaluation.json")
    return evaluation["status"]


def _row_outcome(
    protocol: dict[str, Any], task: dict[str, Any], row_root: Path, process_result: dict[str, Any]
) -> dict[str, Any]:
    semantic = _post_actor_evaluation(protocol, task, row_root, process_result)
    goal_status = _goal_status(row_root)
    budget_pass = (
        process_result["limitBreach"] is None
        and process_result["goalContextVerified"] is True
        and process_result["providerReportedTokens"]
        <= protocol["limits"]["providerReportedTokensPerRun"]
        and process_result["gatewayEvents"]
        <= protocol["limits"]["gatewayEventsPerRun"]
        and process_result["elapsedSeconds"]
        < protocol["limits"]["wallClockSecondsPerRun"]
    )
    custody_pass = (
        process_result["stdoutEof"] is True
        and process_result["ownedChildPids"] == []
        and process_result["exitCode"] == 0
    )
    return {
        "semanticStatus": semantic,
        "goalStatus": goal_status,
        "budgetStatus": "pass" if budget_pass else "fail",
        "custodyStatus": "pass" if custody_pass else "fail",
    }


def _finalize_campaign(evidence_root: Path, summary: dict[str, Any]) -> dict[str, Any]:
    _write_json(evidence_root / "campaign-summary.json", summary)
    manifest_path = evidence_root / "evidence-manifest.json"
    manifest = write_evidence_manifest(evidence_root, manifest_path)
    verification = verify_evidence_manifest(evidence_root, manifest_path)
    _write_json(
        evidence_root / "manifest-verification.json",
        verification | {"manifestSha256": _sha(manifest_path)},
    )
    if verification["mismatches"]:
        raise RuntimeError("evidence_manifest_verification_failed")
    return summary | {
        "evidenceRoot": evidence_root.as_posix(),
        "manifestEntryCount": manifest["entryCount"],
        "manifestSha256": _sha(manifest_path),
    }


def admit_retained_smoke(
    protocol: dict[str, Any],
    retained_root: Path,
    expected_protocol_path: Path = DEFAULT_PROTOCOL,
) -> dict[str, Any]:
    retained_root = validate_evidence_root(retained_root)
    manifest_path = retained_root / "evidence-manifest.json"
    manifest = _load_json(manifest_path)
    if (
        manifest.get("root") != retained_root.as_posix()
        or manifest.get("entryCount") != len(manifest.get("entries", {}))
    ):
        raise RuntimeError("retained_smoke_manifest_invalid")
    verification = verify_evidence_manifest(retained_root, manifest_path)
    if verification["mismatches"]:
        raise RuntimeError("retained_smoke_manifest_invalid")
    retained_protocol = retained_root / "protocol.json"
    if (
        retained_protocol.read_bytes() != Path(expected_protocol_path).read_bytes()
        or _load_json(retained_protocol) != protocol
    ):
        raise RuntimeError("retained_smoke_protocol_mismatch")

    row_root = retained_root / protocol["smokeTask"]
    operator = row_root / "operator"
    outcome = _load_json(operator / "outcome.json")
    process = _load_json(operator / "process-result.json")
    evaluation = _load_json(operator / "hidden-evaluation.json")
    objective = protocol["tasks"][protocol["smokeTask"]]["prompt"]
    limits = CampaignLimits.from_mapping(protocol["limits"])
    context_verified = prime_log_proves_goal_context(
        operator / "prime.jsonl", objective, limits.prime_goal_tokens
    )
    goal_status = _goal_status(row_root)
    live_processes = retained_live_processes(
        _process_snapshot(), retained_root.as_posix()
    )
    process_matches = outcome.get("process") == process
    budget_pass = (
        process_matches
        and process.get("limitBreach") is None
        and context_verified
        and type(process.get("providerReportedTokens")) is int
        and process["providerReportedTokens"] <= limits.provider_tokens
        and type(process.get("gatewayEvents")) is int
        and process["gatewayEvents"] <= limits.gateway_events
        and type(process.get("elapsedSeconds")) in {int, float}
        and process["elapsedSeconds"] < limits.wall_clock_seconds
    )
    custody_pass = (
        process_matches
        and process.get("stdoutEof") is True
        and process.get("ownedChildPids") == []
        and process.get("exitCode") == 0
        and live_processes == []
    )
    admitted = {
        "semanticStatus": (
            "pass"
            if outcome.get("semanticStatus") == "pass"
            and evaluation.get("status") == "pass"
            else "fail"
        ),
        "goalStatus": goal_status,
        "budgetStatus": "pass" if budget_pass else "fail",
        "custodyStatus": "pass" if custody_pass else "fail",
        "retainedOriginalBudgetStatus": outcome.get("budgetStatus"),
        "retainedEvidenceRoot": retained_root.as_posix(),
        "retainedManifestSha256": _sha(manifest_path),
        "retainedOutcomeSha256": _sha(operator / "outcome.json"),
    }
    smoke_projection = {
        key: admitted[key]
        for key in (
            "semanticStatus",
            "goalStatus",
            "budgetStatus",
            "custodyStatus",
        )
    }
    if not smoke_allows_cohort(smoke_projection):
        raise RuntimeError("retained_smoke_not_admissible")
    return admitted


def run_campaign(
    protocol_path: Path,
    evidence_root: Path,
    document_serial: int,
    process_id: int | None,
    accepted_smoke_root: Path | None = None,
) -> dict[str, Any]:
    protocol = validate_protocol(_load_json(protocol_path))
    evidence_root = validate_evidence_root(evidence_root)
    evidence_root.mkdir(parents=True, exist_ok=False)
    shutil.copy2(protocol_path, evidence_root / "protocol.json")
    outcomes: dict[str, Any] = {}
    try:
        _write_json(evidence_root / "runtime-custody.json", _runtime_custody(protocol))
        _collect_tool_surface(protocol, evidence_root)
        _run_preflight(protocol, evidence_root)
        _write_python_environment_custody(
            protocol, evidence_root / "python-environment-baseline.json"
        )

        if accepted_smoke_root is None:
            tasks_to_run = [protocol["smokeTask"]]
        else:
            retained_smoke = admit_retained_smoke(
                protocol, accepted_smoke_root, protocol_path
            )
            _write_json(evidence_root / "retained-smoke-admission.json", retained_smoke)
            outcomes[protocol["smokeTask"]] = retained_smoke
            tasks_to_run = cohort_after_smoke(
                protocol,
                {
                    key: retained_smoke[key]
                    for key in (
                        "semanticStatus",
                        "goalStatus",
                        "budgetStatus",
                        "custodyStatus",
                    )
                },
            )
        while tasks_to_run:
            task_id = tasks_to_run.pop(0)
            task = protocol["tasks"][task_id]
            row_root = evidence_root / task_id
            row_root.mkdir()
            _copy_versioned_inputs(protocol, row_root)
            _write_python_environment_custody(
                protocol, row_root / "operator" / "python-environment-pre.json"
            )
            target = _prepare_target(
                protocol, task, row_root, document_serial, process_id
            )
            _write_row_input_custody(protocol, task, row_root, target)
            process_result = _run_prime_row(protocol, task, row_root, target)
            _write_python_environment_custody(
                protocol, row_root / "operator" / "python-environment-post.json"
            )
            outcome = _row_outcome(protocol, task, row_root, process_result)
            outcomes[task_id] = outcome | {"process": process_result, "target": target}
            _write_json(row_root / "operator" / "outcome.json", outcomes[task_id])
            _write_json(
                row_root / "operator" / "runtime-custody-postrun.json",
                _runtime_custody(protocol),
            )
            if task_id == protocol["smokeTask"]:
                tasks_to_run.extend(cohort_after_smoke(protocol, outcome))
    except BaseException as exc:
        failure = {
            "schema": "rook.experiment.qwen38_campaign_failure:v1",
            "errorType": type(exc).__name__,
            "error": str(exc),
            "completedRows": sorted(outcomes),
        }
        _write_json(evidence_root / "campaign-failure.json", failure)
        _finalize_campaign(
            evidence_root,
            {
                "schema": "rook.experiment.qwen38_self_termination_campaign_result:v2",
                "status": "incomplete",
                "outcomes": outcomes,
                "failure": failure,
            },
        )
        raise

    return _finalize_campaign(
        evidence_root,
        {
            "schema": "rook.experiment.qwen38_self_termination_campaign_result:v2",
            "status": "complete" if len(outcomes) == 4 else "stopped_at_smoke_gate",
            "outcomes": outcomes,
        },
    )


async def _operator_prepare(args: argparse.Namespace) -> int:
    from rook.bridge import DISCOVERY_FOLDER, discover_instances
    from rook.server import _mcp_tool_executor

    instances = [item for item in discover_instances() if item.get("pluginType") == "native"]
    if args.process_id is not None:
        instances = [item for item in instances if item.get("processId") == args.process_id]
    if len(instances) != 1:
        raise RuntimeError(f"target_count:{len(instances)}")
    instance = instances[0]
    process_id = instance["processId"]
    discovery_path = Path(DISCOVERY_FOLDER) / f"instance-{process_id}-native.json"
    os.environ.update(
        {
            "ROOK_MCP_TARGET_MODE": "panel_locked",
            "ROOK_MCP_TARGET_PROCESS_ID": str(process_id),
            "ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER": str(args.document_serial),
            "ROOK_MCP_TOOL_PROFILE": "full",
        }
    )
    created = operator_payload(
        await _mcp_tool_executor("gh_document_new", {}), "gh_document_new"
    )
    _write_json(Path(args.output).parent / "document-new.json", created)
    snapshot = operator_payload(
        await _mcp_tool_executor(
            "gh_snapshot", {"include_data": True, "max_preview_items": 200}
        ),
        "initial_gh_snapshot",
    )
    data = snapshot
    if type(data) is not dict or data.get("components") != [] or data.get("flows") != []:
        raise RuntimeError("fresh_canvas_not_empty")
    initial_snapshot_path = Path(args.output).parent / "initial-inspection.json"
    _write_json(initial_snapshot_path, snapshot)
    seed = None
    if args.task == "T3":
        edit_arguments = {
            "documentSerialNumber": args.document_serial,
            "epoch": data["epoch"],
            "create": [
                {"temp_id": "T1", "type": "slider", "nick": "Start", "min": 0, "max": 100, "value": 0, "pos": [60, 60]},
                {"temp_id": "T2", "type": "slider", "nick": "Step", "min": 0.1, "max": 10, "value": 1, "pos": [60, 180]},
                {"temp_id": "T3", "type": "slider", "nick": "Count", "min": 1, "max": 100, "value": 10, "pos": [60, 300]},
                {"temp_id": "T4", "type": "slider", "nick": "Fault Divisor", "min": 0, "max": 10, "value": 0, "pos": [300, 320]},
                {"temp_id": "T5", "guid": "e64c5fb1-845c-4ab1-8911-5f338516ba67", "pos": [320, 160]},
                {"temp_id": "T6", "guid": "9c85271f-89fa-4e9f-9f4a-d75802120ccc", "pos": [540, 160]},
                {"temp_id": "T7", "guid": "3581f42a-9592-4549-bd6b-1c0fc39d067b", "pos": [760, 160]},
            ],
            "connect": [
                "T1.O0>T5.I0", "T2.O0>T5.I1", "T3.O0>T5.I2",
                "T5.O0>T6.I0", "T4.O0>T6.I1", "T6.O0>T7.I0",
            ],
        }
        edit = operator_payload(
            await _mcp_tool_executor("gh_edit", edit_arguments), "seed_gh_edit"
        )
        receipt = edit.get("solve_readiness_receipt")
        if type(receipt) is not dict:
            raise RuntimeError("seed_receipt_missing")
        wait = operator_payload(
            await _mcp_tool_executor(
                "gh_wait_for_solve_readiness",
                {"readiness_receipt_id": receipt["receipt_id"], "timeout_ms": 10_000},
            ),
            "seed_wait",
        )
        ready = wait.get("receipt")
        if type(ready) is not dict or ready.get("status") != "ready":
            raise RuntimeError("seed_receipt_not_ready")
        seeded = operator_payload(
            await _mcp_tool_executor(
                "gh_snapshot",
                {
                    "include_data": True,
                    "max_preview_items": 200,
                    "readiness_receipt_id": ready["receipt_id"],
                },
            ),
            "seed_snapshot",
        )
        seeded_data = seeded
        if (
            type(seeded_data) is not dict
            or seeded_data.get("diagnostics", {}).get("errors") != 1
            or len(seeded_data.get("components", [])) != 7
            or len(seeded_data.get("flows", [])) != 6
        ):
            raise RuntimeError("seed_fixture_invalid")
        seed = {
            "edit": operator_envelope(edit),
            "wait": operator_envelope(wait),
            "snapshot": operator_envelope(seeded),
        }
        _write_json(Path(args.output).parent / "seed-evidence.json", seed)
    target = {
        "schema": "rook.experiment.target:v2",
        "task": args.task,
        "processId": process_id,
        "nativePort": instance["port"],
        "documentSerialNumber": args.document_serial,
        "discoverySha256": _sha(discovery_path),
        "initialSnapshotSha256": _sha(initial_snapshot_path),
        "seeded": seed is not None,
    }
    _write_json(Path(args.output), target)
    return 0


async def _operator_tool_surface(args: argparse.Namespace) -> int:
    from rook.server import list_tools

    tools = await list_tools()
    catalog = [
        {
            "name": tool.name,
            "description": tool.description,
            "inputSchema": tool.inputSchema,
        }
        for tool in tools
    ]
    output = Path(args.output)
    catalog_path = output.parent / "tool-catalog.json"
    _write_json(catalog_path, catalog)
    _write_json(
        output,
        {
            "schema": "rook.experiment.tool_surface:v1",
            "profile": os.environ.get("ROOK_MCP_TOOL_PROFILE"),
            "count": len(catalog),
            "bytes": catalog_path.stat().st_size,
            "sha256": _sha(catalog_path),
        },
    )
    return 0


async def _operator_evaluate(args: argparse.Namespace) -> int:
    from rook.gh_behavioral_acceptance import (
        _latest_terminal_receipt,
        canonical_json_bytes,
        evaluate_behavioral_probe,
        normalize_authoring_trace,
        run_behavioral_probe,
        seal_prime_source_log,
    )
    from rook.server import _mcp_tool_executor

    row_root = Path(args.row_root)
    operator = row_root / "operator"
    source = operator / "source.jsonl"
    runtime = operator / "prime.jsonl"
    process = _load_json(operator / "process-result.json")
    process_state = {
        "terminated": True,
        "stdout_eof": process["stdoutEof"],
        "owned_child_pids": process["ownedChildPids"],
        "exit_code": args.exit_code,
    }
    try:
        closure = seal_prime_source_log(source, runtime, process_state)
        trace = normalize_authoring_trace(source, runtime)
    except (OSError, ValueError) as exc:
        _write_json(
            operator / "hidden-evaluation.json",
            {"schema": "rook.experiment.hidden_evaluation:v1", "status": "incomplete", "reason": str(exc)},
        )
        return 0
    _write_json(operator / "source-closure.json", closure)
    _write_json(operator / "authoring-trace.json", trace)

    if args.task in {"T1", "T3"}:
        artifact = json.loads(POINT_ACCEPTANCE.read_text(encoding="utf-8"))

        async def envelope_executor(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
            return operator_envelope(await _mcp_tool_executor(name, arguments))

        probe = await run_behavioral_probe(artifact, trace, envelope_executor)
        evaluation = evaluate_behavioral_probe(artifact, trace, probe)
        _write_json(operator / "hidden-probe.json", probe)
        _write_json(operator / "hidden-evaluation.json", evaluation)
        return 0

    # Open tasks retain a receipt-fenced final observation for independent
    # judgment; this runner does not invent another task-specific evaluator.
    latest_receipt, receipt_error = _latest_terminal_receipt(trace)
    observation: dict[str, Any] | None = None
    if type(latest_receipt) is dict and receipt_error is None:
        wait = operator_payload(
            await _mcp_tool_executor(
                "gh_wait_for_solve_readiness",
                {"readiness_receipt_id": latest_receipt["receipt_id"], "timeout_ms": 10_000},
            ),
            "final_wait",
        )
        ready = wait.get("receipt")
        if type(ready) is dict and ready.get("status") == "ready":
            snapshot = operator_payload(
                await _mcp_tool_executor(
                    "gh_snapshot",
                    {
                        "include_data": True,
                        "max_preview_items": 200,
                        "readiness_receipt_id": ready["receipt_id"],
                    },
                ),
                "final_snapshot",
            )
            observation = {
                "wait": operator_envelope(wait),
                "snapshot": operator_envelope(snapshot),
            }
            _write_json(operator / "hidden-final-observation.json", observation)
    _write_json(
        operator / "hidden-evaluation.json",
        {
            "schema": "rook.experiment.hidden_evaluation:v1",
            "status": "unproven",
            "reason": (
                "independent_judgment_required"
                if observation
                else receipt_error or "fenced_observation_unavailable"
            ),
        },
    )
    _ = canonical_json_bytes
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run")
    run.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    run.add_argument("--evidence-root", type=Path, required=True)
    run.add_argument("--document-serial", type=int, required=True)
    run.add_argument("--process-id", type=int)
    run.add_argument("--accepted-smoke-root", type=Path)

    prepare = sub.add_parser("_operator-prepare")
    prepare.add_argument("--task", required=True)
    prepare.add_argument("--document-serial", type=int, required=True)
    prepare.add_argument("--process-id", type=int)
    prepare.add_argument("--output", type=Path, required=True)

    tool_surface = sub.add_parser("_operator-tool-surface")
    tool_surface.add_argument("--output", type=Path, required=True)

    evaluate = sub.add_parser("_operator-evaluate")
    evaluate.add_argument("--task", required=True)
    evaluate.add_argument("--row-root", type=Path, required=True)
    evaluate.add_argument("--exit-code", type=int, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "run":
        result = run_campaign(
            args.protocol,
            args.evidence_root,
            args.document_serial,
            args.process_id,
            args.accepted_smoke_root,
        )
        print(json.dumps(result, ensure_ascii=True, allow_nan=False, separators=(",", ":")))
        return 0
    if args.command == "_operator-prepare":
        return asyncio.run(_operator_prepare(args))
    if args.command == "_operator-tool-surface":
        return asyncio.run(_operator_tool_surface(args))
    if args.command == "_operator-evaluate":
        return asyncio.run(_operator_evaluate(args))
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
