"""Single-session, model-free Gate 7C broker qualification harness."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from rook.agent.chat.prime_backend import PrimeChatBackend, PrimeRuntimeBinding
from rook.agent.chat.prime_process import (
    PrimeRpcProcess,
    PrimeRuntimeProcessFactory,
)
from rook.agent.chat.prime_registry import (
    PrimeConversationRecordV2,
    PrimeConversationRegistry,
    PrimeModelSelection,
    TargetFingerprintV2,
)
from rook.agent.chat.prime_runtime_contract import (
    build_runtime_contract,
    stage_product_package,
    verify_prime_bundle_manifest,
)


class Gate7CFailure(RuntimeError):
    pass


BASE_ENVIRONMENT_KEYS = {
    "APPDATA",
    "COMSPEC",
    "LOCALAPPDATA",
    "PATHEXT",
    "PROGRAMDATA",
    "SystemRoot",
    "TEMP",
    "TMP",
    "USERPROFILE",
    "WINDIR",
}


@dataclass(frozen=True)
class Gate7CConfiguration:
    node_path: Path
    node_sha256: str
    prime_dist_root: Path
    prime_bundle_manifest_path: Path
    prime_bundle_manifest_sha256: str
    prime_git_commit: str
    goal_skill_root: Path
    rook_package_source_root: Path
    product_root: Path
    kernel_root: Path
    registry_root: Path
    session_dir: Path
    agent_root: Path
    uv_path: Path
    uv_sha256: str
    result_path: Path
    model: PrimeModelSelection
    capability_profile: str
    target: TargetFingerprintV2
    conversation_id: str
    base_environment: Mapping[str, str]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _parse_base_environment(raw: str) -> dict[str, str]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise Gate7CFailure("frozen base environment is unreadable") from error
    if type(payload) is not dict or set(payload) != BASE_ENVIRONMENT_KEYS:
        raise Gate7CFailure("frozen base environment has an invalid shape")
    if any(type(value) is not str or not value for value in payload.values()):
        raise Gate7CFailure("frozen base environment has an invalid value")
    return {name: payload[name] for name in sorted(BASE_ENVIRONMENT_KEYS)}


def _require_file(path: Path, label: str) -> Path:
    if not path.is_absolute() or not path.is_file():
        raise Gate7CFailure(f"{label} must be an existing absolute file")
    return path.resolve(strict=True)


def _require_directory(path: Path, label: str, *, create: bool) -> Path:
    if not path.is_absolute():
        raise Gate7CFailure(f"{label} must be absolute")
    if create:
        path.mkdir(parents=True, exist_ok=True)
    if not path.is_dir():
        raise Gate7CFailure(f"{label} must be a directory")
    return path.resolve(strict=True)


def _isolated_base_environment(config: Gate7CConfiguration) -> dict[str, str]:
    admitted = {
        name: value
        for name in (
            "SystemRoot",
            "WINDIR",
            "COMSPEC",
            "TEMP",
            "TMP",
            "USERPROFILE",
            "LOCALAPPDATA",
            "APPDATA",
            "PROGRAMDATA",
            "PATHEXT",
        )
        if (value := config.base_environment.get(name))
    }
    system_root = Path(admitted.get("SystemRoot", "C:/Windows"))
    admitted.update(
        {
            "PATH": os.pathsep.join(
                (str(config.uv_path.parent), str(system_root / "System32"))
            ),
            "PRIME_AGENT_CODING_AGENT_DIR": str(config.agent_root),
            "PRIME_AGENT_SESSION_DIR": str(config.session_dir),
            "PRIME_AGENT_INSTALL_UV": "0",
            "XDG_DATA_HOME": str(config.agent_root / "data"),
        }
    )
    return admitted


def _verify_configuration(config: Gate7CConfiguration) -> None:
    _require_file(config.node_path, "Node executable")
    _require_file(config.prime_bundle_manifest_path, "Prime bundle manifest")
    _require_file(config.goal_skill_root / "SKILL.md", "goal skill")
    _require_file(config.rook_package_source_root / "SKILL.md", "Rook skill")
    _require_file(config.uv_path, "uv executable")
    if _sha256_file(config.node_path) != config.node_sha256:
        raise Gate7CFailure("Node executable hash differs from review")
    if _sha256_file(config.uv_path) != config.uv_sha256:
        raise Gate7CFailure("uv executable hash differs from review")
    for root, label in (
        (config.prime_dist_root, "Prime dist root"),
        (config.goal_skill_root, "goal skill root"),
        (config.rook_package_source_root, "Rook package source"),
    ):
        _require_directory(root, label, create=False)
    for root, label in (
        (config.product_root, "product root"),
        (config.kernel_root, "kernel root"),
        (config.registry_root, "registry root"),
        (config.session_dir, "session directory"),
        (config.agent_root, "agent root"),
    ):
        _require_directory(root, label, create=True)
    if (config.agent_root / "auth.json").exists():
        raise Gate7CFailure("isolated agent root contains auth.json")
    if config.result_path.exists():
        raise Gate7CFailure("Gate 7C result already exists")


def _write_result(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(
        payload,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")
    pending = path.parent / f".{path.name}.{uuid.uuid4().hex}.pending"
    try:
        with pending.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(pending, path)
    finally:
        pending.unlink(missing_ok=True)


async def run_gate_7c(
    config: Gate7CConfiguration,
    *,
    process_class: type[PrimeRpcProcess] = PrimeRpcProcess,
) -> dict[str, Any]:
    _verify_configuration(config)
    bundle = verify_prime_bundle_manifest(
        config.prime_dist_root,
        config.prime_bundle_manifest_path,
        expected_manifest_sha256=config.prime_bundle_manifest_sha256,
    )
    staged = stage_product_package(
        config.rook_package_source_root,
        product_root=config.product_root,
    )
    contract = build_runtime_contract(
        prime_bundle_manifest_sha256=bundle.manifest_sha256,
        prime_git_commit_provenance=config.prime_git_commit,
        goal_skill_root=config.goal_skill_root,
        goal_skill_path_identity="packages/coding-agent/skills/goal",
        rook_package=staged,
        capability_profile=config.capability_profile,
        kernel_root=config.kernel_root,
        runtime_compatibility_version=1,
    )
    binding = PrimeRuntimeBinding(
        contract=contract,
        product_root=config.product_root,
        goal_skill_root=config.goal_skill_root,
        kernel_root=config.kernel_root,
    )
    base_environment = _isolated_base_environment(config)
    def unexpected_v1_factory(*_arguments: object) -> PrimeRpcProcess:
        raise Gate7CFailure("v1 process factory was selected")
    runtime_factory = PrimeRuntimeProcessFactory(
        node_path=config.node_path,
        node_sha256=config.node_sha256,
        uv_path=config.uv_path,
        uv_sha256=config.uv_sha256,
        prime_dist_root=config.prime_dist_root,
        prime_bundle_manifest_path=config.prime_bundle_manifest_path,
        prime_bundle_manifest_sha256=config.prime_bundle_manifest_sha256,
        session_dir=config.session_dir,
        base_environment=base_environment,
        extra_args=("--offline",),
        process_class=process_class,
    )

    registry = PrimeConversationRegistry(
        config.registry_root,
        config.target.rhino_pid,
        config.target.rhino_process_start_utc_ticks,
    )
    backend = PrimeChatBackend(
        registry,
        unexpected_v1_factory,
        config.model,
        runtime_process_factory=runtime_factory,
    )
    prepared: PrimeConversationRecordV2 | None = None
    closed = None
    failure: BaseException | None = None
    try:
        prepared = await backend.create_v2(
            config.conversation_id,
            config.target,
            binding,
        )
        closed = await backend.close(config.conversation_id)
        if len(runtime_factory.created_processes) != 1:
            raise Gate7CFailure("Gate 7C created more than one Prime process")
        process = runtime_factory.created_processes[0]
        if process.command_types != (
            "get_state",
            "set_rlm_max_depth",
            "get_rlm_max_depth_status",
            "prepare_ipython_runtime",
        ):
            raise Gate7CFailure("Gate 7C emitted an unexpected command sequence")
        cleanup = process.cleanup_result
        if cleanup is None or not cleanup.succeeded or cleanup.uncertain:
            raise Gate7CFailure("Prime direct child did not close gracefully")
    except BaseException as error:
        failure = error
    finally:
        await backend.shutdown()
        registry.close()

    process_evidence = []
    for process in runtime_factory.created_processes:
        cleanup = process.cleanup_result
        process_evidence.append(
            {
                "argv": process.argv,
                "commandTypes": list(process.command_types),
                "environmentKeys": sorted(process.launch_environment),
                "cleanup": None if cleanup is None else asdict(cleanup),
            }
        )
    payload: dict[str, Any] = {
        "schemaVersion": 1,
        "status": "passed" if failure is None else "failed",
        "conversationId": config.conversation_id,
        "contractFingerprintSha256": contract.fingerprint,
        "primeBundleManifestSha256": bundle.manifest_sha256,
        "rookPackageManifestSha256": staged.manifest_sha256,
        "preparedRecord": None if prepared is None else asdict(prepared),
        "closedLifecycle": None if closed is None else asdict(closed),
        "processes": process_evidence,
        "error": None if failure is None else f"{type(failure).__name__}: {failure}",
    }
    _write_result(config.result_path, payload)
    if failure is not None:
        raise Gate7CFailure(str(failure)) from failure
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--node-path", required=True)
    parser.add_argument("--node-sha256", required=True)
    parser.add_argument("--prime-dist-root", required=True)
    parser.add_argument("--prime-bundle-manifest", required=True)
    parser.add_argument("--prime-bundle-sha256", required=True)
    parser.add_argument("--prime-commit", required=True)
    parser.add_argument("--goal-skill-root", required=True)
    parser.add_argument("--rook-package-root", required=True)
    parser.add_argument("--product-root", required=True)
    parser.add_argument("--kernel-root", required=True)
    parser.add_argument("--registry-root", required=True)
    parser.add_argument("--session-dir", required=True)
    parser.add_argument("--agent-root", required=True)
    parser.add_argument("--uv-path", required=True)
    parser.add_argument("--uv-sha256", required=True)
    parser.add_argument("--base-environment-json", required=True)
    parser.add_argument("--result", required=True)
    parser.add_argument("--provider", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--thinking")
    parser.add_argument("--profile", choices=("readonly", "full"), required=True)
    parser.add_argument("--rhino-pid", type=int, required=True)
    parser.add_argument("--process-start-ticks", required=True)
    parser.add_argument("--document-serial", type=int, required=True)
    parser.add_argument("--grasshopper-document-id", required=True)
    parser.add_argument("--conversation-id", required=True)
    return parser


def _configuration(namespace: argparse.Namespace) -> Gate7CConfiguration:
    return Gate7CConfiguration(
        node_path=Path(namespace.node_path),
        node_sha256=namespace.node_sha256,
        prime_dist_root=Path(namespace.prime_dist_root),
        prime_bundle_manifest_path=Path(namespace.prime_bundle_manifest),
        prime_bundle_manifest_sha256=namespace.prime_bundle_sha256,
        prime_git_commit=namespace.prime_commit,
        goal_skill_root=Path(namespace.goal_skill_root),
        rook_package_source_root=Path(namespace.rook_package_root),
        product_root=Path(namespace.product_root),
        kernel_root=Path(namespace.kernel_root),
        registry_root=Path(namespace.registry_root),
        session_dir=Path(namespace.session_dir),
        agent_root=Path(namespace.agent_root),
        uv_path=Path(namespace.uv_path),
        uv_sha256=namespace.uv_sha256,
        result_path=Path(namespace.result),
        model=PrimeModelSelection(
            namespace.provider,
            namespace.model,
            namespace.thinking,
        ),
        capability_profile=namespace.profile,
        target=TargetFingerprintV2(
            namespace.rhino_pid,
            namespace.process_start_ticks,
            namespace.document_serial,
            namespace.grasshopper_document_id,
        ),
        conversation_id=namespace.conversation_id,
        base_environment=_parse_base_environment(namespace.base_environment_json),
    )


def main(argv: Sequence[str] | None = None) -> int:
    config = _configuration(build_parser().parse_args(argv))
    try:
        asyncio.run(run_gate_7c(config))
    except Exception as error:
        print(f"Gate 7C failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
