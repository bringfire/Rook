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
VARIED_COHORT_SCHEMA = "rook.experiment.qwen38_varied_product_cohort:v1"
TARGET_FIXTURE_SCHEMA = "rook.experiment.gh_target_fixture:v1"
SHADOW_ADJUDICATION_SCHEMA = (
    "rook.experiment.varied_product_shadow_adjudication:v1"
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


def _is_sha256(value: Any) -> bool:
    return (
        type(value) is str
        and len(value) == 64
        and all(character in "0123456789ABCDEF" for character in value)
    )


def validate_target_fixture(fixture: Any) -> dict[str, Any]:
    if type(fixture) is not dict or set(fixture) != {
        "schema",
        "baseline",
        "seedEdit",
        "seedExpectations",
        "preservation",
    }:
        raise ValueError("target_fixture_invalid")
    if fixture.get("schema") != TARGET_FIXTURE_SCHEMA:
        raise ValueError("target_fixture_invalid")
    baseline = fixture.get("baseline")
    if baseline == "fresh_empty":
        if any(fixture.get(field) is not None for field in (
            "seedEdit",
            "seedExpectations",
            "preservation",
        )):
            raise ValueError("target_fixture_invalid")
        return fixture
    if baseline != "seeded_working_definition":
        raise ValueError("target_fixture_invalid")

    seed = fixture.get("seedEdit")
    expected = fixture.get("seedExpectations")
    preservation = fixture.get("preservation")
    if type(seed) is not dict or set(seed) != {"create", "connect"}:
        raise ValueError("target_fixture_seed_invalid")
    create = seed.get("create")
    connect = seed.get("connect")
    if (
        type(create) is not list
        or not create
        or any(type(item) is not dict for item in create)
        or type(connect) is not list
        or any(type(item) is not str or not item for item in connect)
    ):
        raise ValueError("target_fixture_seed_invalid")
    temp_ids = [item.get("temp_id") for item in create]
    if (
        any(
            type(item) is not str
            or not item.startswith("T")
            or not item[1:].isdigit()
            or item[1] == "0"
            for item in temp_ids
        )
        or len(temp_ids) != len(set(temp_ids))
    ):
        raise ValueError("target_fixture_seed_invalid")
    if type(expected) is not dict or set(expected) != {
        "components",
        "flows",
        "errors",
        "warnings",
    } or any(type(expected[field]) is not int or expected[field] < 0 for field in expected):
        raise ValueError("target_fixture_expectations_invalid")
    if type(preservation) is not dict or set(preservation) != {
        "protectedComponents",
        "protectedFlows",
        "exactIncidentFlowRoles",
    }:
        raise ValueError("target_fixture_preservation_invalid")
    protected = preservation.get("protectedComponents")
    protected_flows = preservation.get("protectedFlows")
    exact_incident_roles = preservation.get("exactIncidentFlowRoles")
    if (
        type(protected) is not list
        or not protected
        or type(protected_flows) is not list
        or any(type(flow) is not str or not flow for flow in protected_flows)
        or type(exact_incident_roles) is not list
        or any(type(role) is not str or not role for role in exact_incident_roles)
    ):
        raise ValueError("target_fixture_preservation_invalid")
    roles: list[str] = []
    for item in protected:
        if type(item) is not dict or set(item) != {"role", "temp_id", "fields"}:
            raise ValueError("target_fixture_preservation_invalid")
        role = item.get("role")
        temp_id = item.get("temp_id")
        fields = item.get("fields")
        if (
            type(role) is not str
            or not role
            or temp_id not in temp_ids
            or type(fields) is not list
            or not fields
            or len(fields) != len(set(fields))
            or any(field not in {"type", "nick", "value", "componentGuid"} for field in fields)
        ):
            raise ValueError("target_fixture_preservation_invalid")
        roles.append(role)
    if len(roles) != len(set(roles)):
        raise ValueError("target_fixture_preservation_invalid")
    if any(role not in roles for role in exact_incident_roles):
        raise ValueError("target_fixture_preservation_invalid")
    return fixture


def validate_shadow_adjudication(
    artifact: Any, protocol: dict[str, Any]
) -> dict[str, Any]:
    if type(artifact) is not dict or set(artifact) != {
        "schema",
        "status",
        "purpose",
        "evaluatorFeedbackDuringRun",
        "evidenceLabels",
        "dispositions",
        "aggregateScore",
        "rules",
        "tasks",
    }:
        raise ValueError("shadow_adjudication_invalid")
    if (
        artifact.get("schema") != SHADOW_ADJUDICATION_SCHEMA
        or artifact.get("status") != "frozen_precontact"
        or artifact.get("evaluatorFeedbackDuringRun") is not False
        or artifact.get("evidenceLabels") != ["observed", "inferred", "unresolved"]
        or artifact.get("dispositions")
        != ["credible_success", "partial_success", "semantic_failure", "incomplete"]
        or artifact.get("aggregateScore") is not None
        or type(artifact.get("rules")) is not list
        or not artifact["rules"]
        or any(type(rule) is not str or not rule for rule in artifact["rules"])
    ):
        raise ValueError("shadow_adjudication_invalid")
    tasks = artifact.get("tasks")
    if type(tasks) is not dict or set(tasks) != set(protocol.get("executionOrder", [])):
        raise ValueError("shadow_adjudication_tasks_invalid")
    for task_id, task in tasks.items():
        if type(task) is not dict or set(task) != {"class", "questions"}:
            raise ValueError("shadow_adjudication_task_invalid")
        if task.get("class") != protocol["tasks"][task_id].get("class"):
            raise ValueError("shadow_adjudication_task_invalid")
        questions = task.get("questions")
        if type(questions) is not list or not questions:
            raise ValueError("shadow_adjudication_task_invalid")
        identifiers: list[str] = []
        for question in questions:
            if (
                type(question) is not dict
                or set(question) != {"id", "text"}
                or type(question.get("id")) is not str
                or not question["id"]
                or type(question.get("text")) is not str
                or not question["text"]
            ):
                raise ValueError("shadow_adjudication_task_invalid")
            identifiers.append(question["id"])
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("shadow_adjudication_task_invalid")
    return artifact


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
    schema = protocol.get("schema") if type(protocol) is dict else None
    if schema not in {
        "rook.experiment.qwen38_self_termination_campaign:v3",
        "rook.experiment.qwen38_self_termination_campaign:v4",
        "rook.experiment.qwen38_self_termination_campaign:v5",
        "rook.experiment.qwen38_self_termination_campaign:v6",
        VARIED_COHORT_SCHEMA,
    }:
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
    expected_order = {
        "rook.experiment.qwen38_self_termination_campaign:v3": [
            "T3",
            "T1",
            "T2",
            "T4",
        ],
        "rook.experiment.qwen38_self_termination_campaign:v4": ["T3", "T2", "T4"],
        "rook.experiment.qwen38_self_termination_campaign:v5": ["T4"],
        "rook.experiment.qwen38_self_termination_campaign:v6": ["T4"],
        VARIED_COHORT_SCHEMA: ["VP1", "VP2", "VP3"],
    }[schema]
    if type(tasks) is not dict or order != expected_order:
        raise ValueError("focused_retest_invalid" if schema.endswith(":v5") else "task_order_invalid")
    if set(tasks) != set(order):
        raise ValueError("task_order_invalid")
    if schema == VARIED_COHORT_SCHEMA:
        if "smokeTask" in protocol:
            raise ValueError("varied_cohort_smoke_forbidden")
    else:
        expected_smoke = "T4" if schema.endswith((":v5", ":v6")) else "T3"
        if protocol.get("smokeTask") != expected_smoke:
            raise ValueError("smoke_task_invalid")
    if schema in {
        "rook.experiment.qwen38_self_termination_campaign:v4",
        "rook.experiment.qwen38_self_termination_campaign:v5",
        "rook.experiment.qwen38_self_termination_campaign:v6",
        VARIED_COHORT_SCHEMA,
    }:
        if prime.get("thinkingLevel") != "low":
            raise ValueError("thinking_level_invalid")
        verification = protocol.get("precontactVerification")
        if (
            type(verification) is not dict
            or set(verification) != {"pythonPath", "arguments"}
            or type(verification.get("pythonPath")) is not str
            or not Path(verification["pythonPath"]).is_absolute()
            or type(verification.get("arguments")) is not list
            or not verification["arguments"]
            or any(
                type(argument) is not str or not argument
                for argument in verification["arguments"]
            )
        ):
            raise ValueError("precontact_verification_invalid")
    if schema == "rook.experiment.qwen38_self_termination_campaign:v5":
        if protocol.get("focusedRetest") != {
            "sourceEvidenceManifestSha256": (
                "99A1D37E45A4410CC668A53CB6ADD97A827C8080201C389C3F3BA9F5A4F9BF16"
            ),
            "onlyChangedOperationalInput": "versioned_prime_skill",
            "successCriteria": [
                "mechanically_healthy_helix",
                "important_controls_exercised_and_restored",
                "adequate_fresh_post_restore_checkpoint",
                "goal_complete",
                "budget_pass",
                "custody_pass",
            ],
            "decisionTelemetry": {
                "firstSufficientEvidence": "independent_post_run_timeline_adjudication",
                "formalCompletion": "persisted_goal_complete",
            },
            "evaluatorFeedbackDuringRun": False,
        }:
            raise ValueError("focused_retest_invalid")
    if schema == "rook.experiment.qwen38_self_termination_campaign:v6":
        if protocol.get("focusedRetest") != {
            "sourceEvidenceManifestSha256": (
                "336E1A539C25B1DEA4E3625B9E526FBC28033ABB7E8C5593C57AC36D17DC059C"
            ),
            "onlyChangedOperationalInput": "versioned_prime_instructions",
            "changedInstructionInputs": ["skillSha256", "checkpointSha256"],
            "successCriteria": [
                "mechanically_healthy_helix",
                "important_controls_exercised_and_restored",
                "model_facing_receipt_wait_ready",
                "model_facing_receipt_fenced_snapshot",
                "no_later_gateway_call",
                "goal_complete",
                "budget_pass",
                "custody_pass",
            ],
            "decisionTelemetry": {
                "firstQualifiedEvidence": "receipt_fenced_snapshot_tool_result",
                "formalCompletion": "persisted_goal_complete",
                "perTurnInputOutput": "retained_prime_message_usage",
            },
            "evaluatorFeedbackDuringRun": False,
        }:
            raise ValueError("focused_retest_invalid")
    if schema == VARIED_COHORT_SCHEMA:
        continuation = protocol.get("continuationPolicy")
        if continuation != {
            "modelOrSemanticFailureContinues": True,
            "budgetLimitTerminationContinuesAfterCleanShutdown": True,
            "stopConditions": [
                "runtime_custody_drift",
                "python_environment_drift",
                "tool_surface_drift",
                "target_contamination",
                "process_custody_failure",
                "evaluator_infrastructure_failure",
                "unexpected_runner_failure",
            ],
        }:
            raise ValueError("continuation_policy_invalid")
        source = protocol.get("sourceCampaignProtocol")
        if (
            type(source) is not dict
            or set(source) != {"path", "sha256"}
            or source.get("path")
            != "docs/superpowers/experiments/2026-08-18-qwen38-self-termination-campaign-v6.json"
            or not _is_sha256(source.get("sha256"))
        ):
            raise ValueError("source_campaign_invalid")
        source_path = ROOT / source["path"]
        if not source_path.is_file() or _sha(source_path) != source["sha256"]:
            raise ValueError("source_campaign_invalid")
        evaluator = protocol.get("offlineEvaluator")
        if (
            type(evaluator) is not dict
            or set(evaluator)
            != {
                "sourceCampaignProtocolSha256",
                "reviewedCorrectionCommit",
                "behavioralAcceptancePath",
                "behavioralAcceptanceSha256",
                "scope",
            }
            or evaluator.get("sourceCampaignProtocolSha256") != source["sha256"]
            or evaluator.get("reviewedCorrectionCommit")
            != "efe0615466b84079263fd190336831bfce59343a"
            or evaluator.get("scope") != "silent_post_run_trace_normalization_only"
            or not _is_sha256(evaluator.get("behavioralAcceptanceSha256"))
        ):
            raise ValueError("offline_evaluator_invalid")
        evaluator_path = ROOT / evaluator["behavioralAcceptancePath"]
        if (
            not evaluator_path.is_file()
            or _sha(evaluator_path) != evaluator["behavioralAcceptanceSha256"]
        ):
            raise ValueError("offline_evaluator_invalid")
        adjudication = protocol.get("shadowAdjudication")
        if (
            type(adjudication) is not dict
            or set(adjudication) != {"path", "sha256"}
            or not _is_sha256(adjudication.get("sha256"))
        ):
            raise ValueError("shadow_adjudication_invalid")
        adjudication_path = ROOT / adjudication["path"]
        if (
            not adjudication_path.is_file()
            or _sha(adjudication_path) != adjudication["sha256"]
        ):
            raise ValueError("shadow_adjudication_invalid")
        validate_shadow_adjudication(_load_json(adjudication_path), protocol)
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
        if schema == VARIED_COHORT_SCHEMA:
            if set(task) != {
                "id",
                "class",
                "targetBaseline",
                "evaluator",
                "prompt",
                "targetFixture",
            } or task.get("evaluator") != "independent_shadow_judgment":
                raise ValueError(f"task_invalid:{task_id}")
            validate_target_fixture(task["targetFixture"])
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


def run_precontact_verification(
    protocol: dict[str, Any], evidence_root: Path
) -> dict[str, Any] | None:
    configured = protocol.get("precontactVerification")
    if configured is None:
        return None
    command = [configured["pythonPath"], *configured["arguments"]]
    completed = subprocess.run(
        command,
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=False,
    )
    stdout_path = Path(evidence_root) / "precontact-tests.stdout.txt"
    stderr_path = Path(evidence_root) / "precontact-tests.stderr.txt"
    stdout_path.write_bytes(completed.stdout)
    stderr_path.write_bytes(completed.stderr)
    record = {
        "schema": "rook.experiment.precontact_verification:v1",
        "command": command,
        "cwd": ROOT.as_posix(),
        "exitCode": completed.returncode,
        "stdoutBytes": len(completed.stdout),
        "stdoutSha256": _sha(stdout_path),
        "stderrBytes": len(completed.stderr),
        "stderrSha256": _sha(stderr_path),
    }
    _write_json(Path(evidence_root) / "precontact-verification.json", record)
    if completed.returncode != 0:
        raise RuntimeError(f"precontact_verification_failed:{completed.returncode}")
    return record


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


def offline_evaluator_environment(
    protocol: dict[str, Any], environment: dict[str, str]
) -> dict[str, str]:
    if protocol.get("schema") != VARIED_COHORT_SCHEMA:
        raise ValueError("varied_cohort_protocol_required")
    evaluator = protocol["offlineEvaluator"]
    source = ROOT / evaluator["behavioralAcceptancePath"]
    if not source.is_file() or _sha(source) != evaluator["behavioralAcceptanceSha256"]:
        raise RuntimeError("offline_evaluator_custody_mismatch")
    result = dict(environment)
    existing = result.get("PYTHONPATH")
    entries = [(ROOT / "mcp_server" / "src").as_posix()]
    if existing:
        entries.append(existing)
    result["PYTHONPATH"] = os.pathsep.join(entries)
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
    fixture_path = operator / "task-fixture.json"
    if fixture_path.is_file():
        files["targetFixture"] = fixture_path
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


def _runtime_custody(
    protocol: dict[str, Any], protocol_path: Path = DEFAULT_PROTOCOL
) -> dict[str, Any]:
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
            "path": Path(protocol_path).as_posix(),
            "sha256": _sha(Path(protocol_path)),
            "bytes": Path(protocol_path).stat().st_size,
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
    if protocol.get("schema") == VARIED_COHORT_SCHEMA:
        evaluator = protocol["offlineEvaluator"]
        source = protocol["sourceCampaignProtocol"]
        adjudication = protocol["shadowAdjudication"]
        files["offlineBehavioralAcceptance"] = _verify_sha(
            ROOT / evaluator["behavioralAcceptancePath"],
            evaluator["behavioralAcceptanceSha256"],
            "offline_behavioral_acceptance",
        )
        files["sourceCampaignProtocol"] = _verify_sha(
            ROOT / source["path"], source["sha256"], "source_campaign_protocol"
        )
        files["shadowAdjudication"] = _verify_sha(
            ROOT / adjudication["path"],
            adjudication["sha256"],
            "shadow_adjudication",
        )
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
        "thinkingLevelVerified": prime_session_proves_thinking_level(
            row_root, protocol["prime"]["thinkingLevel"]
        ),
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


def prime_session_proves_thinking_level(row_root: Path, expected: str) -> bool:
    sessions = sorted((Path(row_root) / "agent" / "sessions").glob("*.jsonl"))
    if len(sessions) != 1:
        return False
    observed: list[str] = []
    with sessions[0].open("r", encoding="utf-8") as stream:
        for line in stream:
            try:
                value = json.loads(line)
            except ValueError:
                continue
            if (
                type(value) is dict
                and value.get("type") == "thinking_level_change"
                and type(value.get("thinkingLevel")) is str
            ):
                observed.append(value["thinkingLevel"])
    return bool(observed) and all(level == expected for level in observed)


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


def _offline_evaluator_command(
    protocol: dict[str, Any], args: list[str]
) -> subprocess.CompletedProcess:
    verification = protocol["precontactVerification"]
    environment = offline_evaluator_environment(protocol, dict(os.environ))
    return subprocess.run(
        [verification["pythonPath"], str(Path(__file__).resolve()), *args],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
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
    fixture = task.get("targetFixture")
    if fixture is not None:
        validate_target_fixture(fixture)
        fixture_path = output.parent / "task-fixture.json"
        _write_json(fixture_path, fixture)
        arguments.extend(["--fixture", str(fixture_path)])
    if process_id is not None:
        arguments.extend(["--process-id", str(process_id)])
    result = _operator_command(protocol, arguments)
    if result.returncode != 0:
        raise RuntimeError(f"target_prepare_failed:{result.stderr.strip()}")
    return _load_json(output)


def _post_actor_evaluation(
    protocol: dict[str, Any], task: dict[str, Any], row_root: Path, process_result: dict[str, Any]
) -> str:
    presealed = protocol.get("schema") == VARIED_COHORT_SCHEMA
    infrastructure_path = row_root / "operator" / "evaluation-infrastructure.json"
    if presealed:
        normalize_arguments = [
            "_operator-normalize",
            "--row-root",
            str(row_root),
            "--exit-code",
            str(process_result["exitCode"]),
        ]
        normalized = _offline_evaluator_command(protocol, normalize_arguments)
        if normalized.returncode != 0:
            (row_root / "operator" / "normalization-error.txt").write_text(
                normalized.stderr, encoding="utf-8"
            )
            _write_json(
                infrastructure_path,
                {"status": "fail", "stage": "offline_trace_normalization"},
            )
            return "incomplete"
        retained_evaluation = row_root / "operator" / "hidden-evaluation.json"
        retained_trace = row_root / "operator" / "authoring-trace.json"
        if retained_evaluation.is_file() and not retained_trace.is_file():
            _write_json(
                infrastructure_path,
                {"status": "pass", "stage": "actor_evidence_incomplete"},
            )
            return _load_json(retained_evaluation)["status"]
    arguments = [
        "_operator-evaluate",
        "--task",
        task["id"],
        "--row-root",
        str(row_root),
        "--exit-code",
        str(process_result["exitCode"]),
    ]
    if presealed:
        arguments.append("--presealed")
    result = _operator_command(protocol, arguments)
    if result.returncode != 0:
        (row_root / "operator" / "evaluation-error.txt").write_text(
            result.stderr, encoding="utf-8"
        )
        if presealed:
            _write_json(
                infrastructure_path,
                {"status": "fail", "stage": "live_final_observation"},
            )
        return "incomplete"
    if presealed:
        _write_json(
            infrastructure_path,
            {"status": "pass", "stage": "complete"},
        )
    evaluation = _load_json(row_root / "operator" / "hidden-evaluation.json")
    return evaluation["status"]


def audit_actor_final_checkpoint(events: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted(
        (
            event
            for event in events
            if type(event) is dict and type(event.get("sequence")) is int
        ),
        key=lambda event: event["sequence"],
    )

    def result(
        status: str,
        reason: str | None,
        receipt_id: str | None = None,
        mutation_sequence: int | None = None,
        wait_sequence: int | None = None,
        snapshot_sequence: int | None = None,
    ) -> dict[str, Any]:
        return {
            "schema": "rook.experiment.actor_final_checkpoint:v1",
            "status": status,
            "reason": reason,
            "receiptId": receipt_id,
            "mutationSequence": mutation_sequence,
            "waitSequence": wait_sequence,
            "snapshotSequence": snapshot_sequence,
            "gatewayEventCount": len(ordered),
        }

    terminal = [
        event
        for event in ordered
        if event.get("mutation", {}).get("classification") == "terminal"
        and event.get("mutation", {}).get("commit_status") == "committed"
    ]
    if not terminal:
        return result("fail", "final_terminal_receipt_missing")
    mutation = terminal[-1]
    receipt = mutation.get("mutation", {}).get("solve_readiness_receipt")
    receipt_id = receipt.get("receipt_id") if type(receipt) is dict else None
    if type(receipt_id) is not str or not receipt_id:
        return result(
            "fail",
            "final_terminal_receipt_missing",
            mutation_sequence=mutation["sequence"],
        )

    later = [event for event in ordered if event["sequence"] > mutation["sequence"]]
    waits = []
    for event in later:
        payload = event.get("result", {}).get("data")
        ready = payload.get("receipt") if type(payload) is dict else None
        if (
            event.get("target") == "gh_wait_for_solve_readiness"
            and event.get("arguments", {}).get("readiness_receipt_id") == receipt_id
            and event.get("result", {}).get("success") is True
            and type(payload) is dict
            and payload.get("wait_status") == "ready"
            and type(ready) is dict
            and ready.get("receipt_id") == receipt_id
            and ready.get("status") == "ready"
        ):
            waits.append(event)
    if not waits:
        return result(
            "fail",
            "final_receipt_wait_missing",
            receipt_id,
            mutation["sequence"],
        )
    wait = waits[0]

    snapshots = [
        event
        for event in later
        if event["sequence"] > wait["sequence"]
        and event.get("target") == "gh_snapshot"
        and event.get("arguments", {}).get("readiness_receipt_id") == receipt_id
        and event.get("result", {}).get("success") is True
    ]
    if not snapshots:
        return result(
            "fail",
            "final_receipt_fenced_snapshot_missing",
            receipt_id,
            mutation["sequence"],
            wait["sequence"],
        )
    snapshot = snapshots[0]
    if any(event["sequence"] > snapshot["sequence"] for event in ordered):
        return result(
            "fail",
            "later_gateway_call",
            receipt_id,
            mutation["sequence"],
            wait["sequence"],
            snapshot["sequence"],
        )
    return result(
        "pass",
        None,
        receipt_id,
        mutation["sequence"],
        wait["sequence"],
        snapshot["sequence"],
    )


def _source_events(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as stream:
        for line in stream:
            value = json.loads(line)
            if type(value) is dict and type(value.get("sequence")) is int:
                events.append(value)
    return events


def _jsonl_objects(path: Path) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    if not path.is_file():
        return values
    with path.open("r", encoding="utf-8") as stream:
        for line in stream:
            try:
                value = json.loads(line)
            except ValueError:
                continue
            if type(value) is dict:
                values.append(value)
    return values


def _envelope_data(value: Any) -> Any:
    if type(value) is dict and value.get("success") is True:
        return value.get("data")
    return None


def evaluate_seed_preservation(
    fixture: dict[str, Any],
    seed_evidence: dict[str, Any],
    final_snapshot: dict[str, Any],
) -> dict[str, Any]:
    validate_target_fixture(fixture)
    if fixture["baseline"] != "seeded_working_definition":
        raise ValueError("seed_preservation_not_applicable")
    edit = _envelope_data(seed_evidence.get("edit"))
    baseline = _envelope_data(seed_evidence.get("snapshot"))
    temp_map = (
        edit.get("edit_summary", {}).get("temp_id_map")
        if type(edit) is dict
        else None
    )
    if (
        type(temp_map) is not dict
        or type(baseline) is not dict
        or type(final_snapshot) is not dict
    ):
        raise ValueError("seed_preservation_evidence_invalid")
    baseline_components = {
        item.get("id"): item
        for item in baseline.get("components", [])
        if type(item) is dict and type(item.get("id")) is str
    }
    final_components = {
        item.get("id"): item
        for item in final_snapshot.get("components", [])
        if type(item) is dict and type(item.get("id")) is str
    }
    violations: list[dict[str, Any]] = []
    preservation = fixture["preservation"]
    for protected in preservation["protectedComponents"]:
        role = protected["role"]
        component_id = temp_map.get(protected["temp_id"])
        before = baseline_components.get(component_id)
        after = final_components.get(component_id)
        if type(component_id) is not str or type(before) is not dict:
            raise ValueError("seed_preservation_evidence_invalid")
        if type(after) is not dict:
            violations.append(
                {"code": "protected_component_missing", "role": role}
            )
            continue
        for field in protected["fields"]:
            if before.get(field) != after.get(field):
                violations.append(
                    {
                        "code": "protected_field_changed",
                        "role": role,
                        "field": field,
                    }
                )

    final_flows = set(final_snapshot.get("flows", []))
    for symbolic_flow in preservation["protectedFlows"]:
        concrete_flow = symbolic_flow
        for temp_id, component_id in sorted(
            temp_map.items(), key=lambda pair: len(pair[0]), reverse=True
        ):
            concrete_flow = concrete_flow.replace(temp_id, component_id)
        if concrete_flow not in final_flows:
            violations.append(
                {"code": "protected_flow_missing", "flow": symbolic_flow}
            )
    baseline_flows = set(baseline.get("flows", []))
    role_to_id = {
        item["role"]: temp_map[item["temp_id"]]
        for item in preservation["protectedComponents"]
    }
    for role in preservation["exactIncidentFlowRoles"]:
        component_id = role_to_id[role]
        marker = f"{component_id}."
        before = sorted(flow for flow in baseline_flows if marker in flow)
        after = sorted(flow for flow in final_flows if marker in flow)
        if before != after:
            violations.append(
                {"code": "protected_incident_flows_changed", "role": role}
            )
    return {
        "schema": "rook.experiment.seed_preservation:v1",
        "status": "fail" if violations else "pass",
        "violations": violations,
    }


def summarize_row_telemetry(
    source_events: list[dict[str, Any]], prime_events: list[dict[str, Any]]
) -> dict[str, Any]:
    ordered = sorted(
        (
            event
            for event in source_events
            if type(event) is dict and type(event.get("sequence")) is int
        ),
        key=lambda event: event["sequence"],
    )
    discovery_targets = {
        "rook_tools_search",
        "rook_tools_read",
        "gh_library",
        "gh_batch_component_info",
    }
    mutation_events = [
        event
        for event in ordered
        if event.get("target")
        in {
            "gh_edit",
            "gh_execute_intent",
            "gh_set_value",
            "gh_create_script",
            "gh_update_script",
            "gh_set_script_pins",
            "chirp_create",
        }
    ]
    committed = [
        event
        for event in mutation_events
        if event.get("mutation", {}).get("commit_status") == "committed"
    ]
    refused_or_failed = []
    for event in ordered:
        result = event.get("result")
        if type(event.get("exception")) is dict or (
            type(result) is dict and result.get("success") is False
        ):
            refused_or_failed.append(event)
    per_turn: list[dict[str, Any]] = []
    for value in prime_events:
        if type(value) is not dict or value.get("type") != "message_end":
            continue
        message = value.get("message")
        usage = message.get("usage") if type(message) is dict else None
        if type(usage) is not dict:
            continue
        input_tokens = usage.get("input", usage.get("inputTokens"))
        output_tokens = usage.get("output", usage.get("outputTokens"))
        total_tokens = usage.get("totalTokens")
        if any(type(item) is not int or item < 0 for item in (
            input_tokens,
            output_tokens,
            total_tokens,
        )):
            continue
        per_turn.append(
            {
                "turn": len(per_turn) + 1,
                "timestamp": value.get("timestamp"),
                "inputTokens": input_tokens,
                "outputTokens": output_tokens,
                "totalTokens": total_tokens,
            }
        )
    return {
        "schema": "rook.experiment.varied_product_row_telemetry:v1",
        "observed": {
            "gatewayCalls": len(ordered),
            "discoveryCalls": sum(
                event.get("target") in discovery_targets for event in ordered
            ),
            "mutationCalls": len(mutation_events),
            "committedMutations": len(committed),
            "refusedOrFailedCalls": len(refused_or_failed),
            "perTurnUsage": per_turn,
        },
        "inferred": {
            "candidateCorrectionMutations": max(0, len(committed) - 1),
            "qualification": "mutation_order_only_not_semantic_correction",
        },
        "unresolved": ["first_sufficient_fenced_evidence_turn"],
    }


def varied_row_allows_continuation(
    protocol: dict[str, Any], outcome: dict[str, Any]
) -> bool:
    if protocol.get("schema") != VARIED_COHORT_SCHEMA:
        raise ValueError("varied_cohort_protocol_required")
    process = outcome.get("process")
    if type(process) is not dict:
        return False
    clean_limit_breach = process.get("limitBreach") in {
        "provider_token_ceiling",
        "gateway_call_ceiling",
        "wall_clock_ceiling",
    }
    return (
        outcome.get("evaluationInfrastructureStatus") == "pass"
        and
        process.get("stdoutEof") is True
        and process.get("ownedChildPids") == []
        and process.get("thinkingLevelVerified") is True
        and (process.get("exitCode") == 0 or clean_limit_breach)
    )


def _final_observation_snapshot(row_root: Path) -> dict[str, Any] | None:
    path = row_root / "operator" / "hidden-final-observation.json"
    if not path.is_file():
        return None
    observation = _load_json(path)
    snapshot = observation.get("snapshot") if type(observation) is dict else None
    data = _envelope_data(snapshot)
    return data if type(data) is dict else None


def _write_varied_row_records(
    protocol: dict[str, Any],
    task: dict[str, Any],
    row_root: Path,
    final_checkpoint: dict[str, Any],
) -> dict[str, Any]:
    operator = row_root / "operator"
    source_events = _source_events(operator / "source.jsonl")
    prime_events = _jsonl_objects(operator / "prime.jsonl")
    telemetry = summarize_row_telemetry(source_events, prime_events)
    snapshot = _final_observation_snapshot(row_root)
    diagnostics = snapshot.get("diagnostics") if type(snapshot) is dict else None
    telemetry["observed"]["finalDiagnostics"] = (
        {
            "errors": diagnostics.get("errors"),
            "warnings": diagnostics.get("warnings"),
        }
        if type(diagnostics) is dict
        else None
    )
    telemetry["observed"]["actorFinalCheckpoint"] = final_checkpoint
    _write_json(operator / "row-telemetry.json", telemetry)

    fixture = task["targetFixture"]
    if fixture["baseline"] == "fresh_empty":
        preservation = {
            "schema": "rook.experiment.seed_preservation:v1",
            "status": "not_applicable",
            "violations": [],
        }
    elif snapshot is None:
        preservation = {
            "schema": "rook.experiment.seed_preservation:v1",
            "status": "incomplete",
            "violations": [
                {"code": "fenced_final_snapshot_unavailable"}
            ],
        }
    else:
        preservation = evaluate_seed_preservation(
            fixture,
            _load_json(operator / "seed-evidence.json"),
            snapshot,
        )
    _write_json(operator / "preservation-evaluation.json", preservation)

    evidence_paths = {
        "primeRuntime": operator / "prime.jsonl",
        "sourceLog": operator / "source.jsonl",
        "processResult": operator / "process-result.json",
        "evaluationInfrastructure": operator / "evaluation-infrastructure.json",
        "authoringTrace": operator / "authoring-trace.json",
        "finalObservation": operator / "hidden-final-observation.json",
        "actorFinalCheckpoint": operator / "actor-final-checkpoint.json",
        "preservation": operator / "preservation-evaluation.json",
        "telemetry": operator / "row-telemetry.json",
    }
    judgment_input = {
        "schema": "rook.experiment.varied_product_shadow_judgment_input:v1",
        "status": "pending_independent_judgment",
        "taskId": task["id"],
        "taskSha256": hashlib.sha256(_canonical_bytes(task)).hexdigest().upper(),
        "adjudicationContract": protocol["shadowAdjudication"],
        "evidence": {
            name: (
                {
                    "path": path.relative_to(row_root).as_posix(),
                    "sha256": _sha(path),
                    "bytes": path.stat().st_size,
                }
                if path.is_file()
                else None
            )
            for name, path in evidence_paths.items()
        },
        "requiredEvidenceLabels": ["observed", "inferred", "unresolved"],
        "runtimeFeedbackProvided": False,
    }
    _write_json(operator / "shadow-judgment-input.json", judgment_input)
    return {
        "telemetry": telemetry,
        "preservation": preservation,
        "shadowJudgmentStatus": judgment_input["status"],
    }


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
    final_checkpoint: dict[str, Any] | None = None
    if protocol["schema"] in {
        "rook.experiment.qwen38_self_termination_campaign:v6",
        VARIED_COHORT_SCHEMA,
    }:
        final_checkpoint = audit_actor_final_checkpoint(
            _source_events(row_root / "operator" / "source.jsonl")
        )
        _write_json(
            row_root / "operator" / "actor-final-checkpoint.json",
            final_checkpoint,
        )
    custody_pass = (
        process_result["stdoutEof"] is True
        and process_result["ownedChildPids"] == []
        and process_result["exitCode"] == 0
        and (
            protocol["schema"]
            not in {
                "rook.experiment.qwen38_self_termination_campaign:v4",
                "rook.experiment.qwen38_self_termination_campaign:v5",
                "rook.experiment.qwen38_self_termination_campaign:v6",
                VARIED_COHORT_SCHEMA,
            }
            or process_result.get("thinkingLevelVerified") is True
        )
        and (
            final_checkpoint is None
            or protocol["schema"] == VARIED_COHORT_SCHEMA
            or final_checkpoint["status"] == "pass"
        )
    )
    outcome = {
        "semanticStatus": semantic,
        "goalStatus": goal_status,
        "budgetStatus": "pass" if budget_pass else "fail",
        "custodyStatus": "pass" if custody_pass else "fail",
    }
    if final_checkpoint is not None:
        outcome["actorFinalCheckpointStatus"] = final_checkpoint["status"]
    if protocol["schema"] == VARIED_COHORT_SCHEMA:
        infrastructure = _load_json(
            row_root / "operator" / "evaluation-infrastructure.json"
        )
        records = _write_varied_row_records(
            protocol,
            task,
            row_root,
            final_checkpoint,
        )
        outcome["preservationStatus"] = records["preservation"]["status"]
        outcome["shadowJudgmentStatus"] = records["shadowJudgmentStatus"]
        outcome["evaluationInfrastructureStatus"] = infrastructure["status"]
    return outcome


def campaign_completion_status(
    protocol: dict[str, Any], outcomes: dict[str, Any]
) -> str:
    return (
        "complete"
        if len(outcomes) == len(protocol["executionOrder"])
        else "stopped_at_smoke_gate"
    )


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


def _seal_row_evidence(row_root: Path) -> dict[str, Any]:
    manifest_path = row_root / "evidence-manifest.json"
    manifest = write_evidence_manifest(row_root, manifest_path)
    verification = verify_evidence_manifest(row_root, manifest_path)
    _write_json(
        row_root / "manifest-verification.json",
        verification | {"manifestSha256": _sha(manifest_path)},
    )
    if verification["mismatches"]:
        raise RuntimeError("row_evidence_manifest_verification_failed")
    return {
        "entryCount": manifest["entryCount"],
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
        run_precontact_verification(protocol, evidence_root)
        _write_json(
            evidence_root / "runtime-custody.json",
            _runtime_custody(protocol, protocol_path),
        )
        _collect_tool_surface(protocol, evidence_root)
        _run_preflight(protocol, evidence_root)
        _write_python_environment_custody(
            protocol, evidence_root / "python-environment-baseline.json"
        )

        if protocol["schema"] == VARIED_COHORT_SCHEMA:
            if accepted_smoke_root is not None:
                raise RuntimeError("varied_cohort_retained_smoke_forbidden")
            tasks_to_run = list(protocol["executionOrder"])
        elif accepted_smoke_root is None:
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
                _runtime_custody(protocol, protocol_path),
            )
            if protocol["schema"] == VARIED_COHORT_SCHEMA:
                _seal_row_evidence(row_root)
                if outcome.get("evaluationInfrastructureStatus") != "pass":
                    raise RuntimeError(
                        f"evaluator_infrastructure_failure:{task_id}"
                    )
                if not varied_row_allows_continuation(protocol, outcomes[task_id]):
                    raise RuntimeError(f"process_custody_failure:{task_id}")
            elif task_id == protocol["smokeTask"]:
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
            "status": campaign_completion_status(protocol, outcomes),
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
    fixture = None
    if args.fixture is not None:
        fixture = validate_target_fixture(_load_json(args.fixture))
    if fixture is not None and fixture["seedEdit"] is not None:
        edit_arguments = json.loads(json.dumps(fixture["seedEdit"]))
        edit_arguments["documentSerialNumber"] = args.document_serial
        edit_arguments["epoch"] = data["epoch"]
        edit = operator_payload(
            await _mcp_tool_executor("gh_edit", edit_arguments), "seed_gh_edit"
        )
        receipt = edit.get("solve_readiness_receipt")
        if type(receipt) is not dict:
            raise RuntimeError("seed_receipt_missing")
        wait = operator_payload(
            await _mcp_tool_executor(
                "gh_wait_for_solve_readiness",
                {
                    "readiness_receipt_id": receipt["receipt_id"],
                    "timeout_ms": 10_000,
                },
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
        expectations = fixture["seedExpectations"]
        diagnostics = seeded.get("diagnostics") if type(seeded) is dict else None
        if (
            type(seeded) is not dict
            or len(seeded.get("components", [])) != expectations["components"]
            or len(seeded.get("flows", [])) != expectations["flows"]
            or type(diagnostics) is not dict
            or diagnostics.get("errors") != expectations["errors"]
            or diagnostics.get("warnings") != expectations["warnings"]
        ):
            raise RuntimeError("seed_fixture_invalid")
        seed = {
            "edit": operator_envelope(edit),
            "wait": operator_envelope(wait),
            "snapshot": operator_envelope(seeded),
        }
        _write_json(Path(args.output).parent / "seed-evidence.json", seed)
    elif args.task == "T3":
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
    if fixture is not None:
        target["targetFixtureSha256"] = _sha(args.fixture)
        target["targetBaseline"] = fixture["baseline"]
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


async def _operator_normalize(args: argparse.Namespace) -> int:
    from rook.gh_behavioral_acceptance import (
        normalize_authoring_trace,
        seal_prime_source_log,
    )

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
            {
                "schema": "rook.experiment.hidden_evaluation:v1",
                "status": "incomplete",
                "reason": str(exc),
            },
        )
        return 0
    _write_json(operator / "source-closure.json", closure)
    _write_json(operator / "authoring-trace.json", trace)
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
    if args.presealed:
        trace = _load_json(operator / "authoring-trace.json")
    else:
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
    prepare.add_argument("--fixture", type=Path)
    prepare.add_argument("--output", type=Path, required=True)

    tool_surface = sub.add_parser("_operator-tool-surface")
    tool_surface.add_argument("--output", type=Path, required=True)

    evaluate = sub.add_parser("_operator-evaluate")
    evaluate.add_argument("--task", required=True)
    evaluate.add_argument("--row-root", type=Path, required=True)
    evaluate.add_argument("--exit-code", type=int, required=True)
    evaluate.add_argument("--presealed", action="store_true")

    normalize = sub.add_parser("_operator-normalize")
    normalize.add_argument("--row-root", type=Path, required=True)
    normalize.add_argument("--exit-code", type=int, required=True)
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
    if args.command == "_operator-normalize":
        return asyncio.run(_operator_normalize(args))
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
