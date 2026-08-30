#!/usr/bin/env python3
"""Absorbing admission wrapper for the reviewed Gate 7B V4 transaction."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Callable, Mapping, Sequence


ROOK_ROOT = Path("C:/UDEV/Rook/.worktrees/task7-runtime-topology-recovery")
PRIME_ROOT = Path("D:/prime-agent/.worktrees/task7-runtime-topology-recovery")
APPROVED_PRIME_COMMIT = "51e047fc2cf1d45b93a0e75eed961a7d958cda02"
LEASE_ROOT = Path(
    "C:/RookEvidence/2026-08-30-rookchat-prime-runtime-topology-gate-7b-v4-lease"
)
DIRECT_ROOT = Path(
    "C:/RookEvidence/2026-08-30-rookchat-prime-runtime-topology-gate-7b-v4-direct"
)
PRIME_BUNDLE_MANIFEST_SHA256 = (
    "8685FC1DB52E834DA19841D5F7BB539EA2BFECD0D574F242374D8A07D4022DFA"
)
GOAL_SKILL_MANIFEST_SHA256 = (
    "D1BD71554A07F2A1DACA96FF4A683332B7B5D248769E4571E99D24B55DF8B3C7"
)
ROOK_SKILL_MANIFEST_SHA256 = (
    "2BA81A9B01B71C649A060F8CAEDE8F8F01F6BD6C979EB3F8957C05D4D93CE678"
)
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
GIT_TIMEOUT_SECONDS = 15.0


class Gate7BFailure(RuntimeError):
    pass


@dataclass(frozen=True)
class FrozenFile:
    path: Path
    sha256: str


@dataclass(frozen=True)
class Gate7BConfiguration:
    rook_root: Path
    prime_root: Path
    approved_rook_commit: str
    approved_prime_commit: str
    harness: FrozenFile
    frozen_files: tuple[FrozenFile, ...]
    lease_root: Path
    direct_root: Path
    harness_arguments: tuple[str, ...] = ()


def execute_gate_7b(
    config: Gate7BConfiguration,
    *,
    inspect_repo: Callable[[Path], tuple[str, str]],
    hash_file: Callable[[Path], str],
    run_entry: Callable[[str, Path], tuple[int, Mapping[str, object]]],
) -> dict[str, object]:
    _verify_custody(config, inspect_repo=inspect_repo, hash_file=hash_file)

    for label, root in (("lease", config.lease_root), ("direct", config.direct_root)):
        if root.exists():
            raise Gate7BFailure(f"{label} evidence root already exists")

    lease_code, lease_result = run_entry("lease-sequence", config.lease_root)
    if lease_code != 0 or _result_status(lease_result) != "passed":
        raise Gate7BFailure("lease-sequence failed; direct vertical is not admitted")
    _verify_custody(config, inspect_repo=inspect_repo, hash_file=hash_file)
    if config.direct_root.exists():
        raise Gate7BFailure("direct evidence root appeared before direct admission")

    direct_code, direct_result = run_entry("direct-vertical", config.direct_root)
    if direct_code != 0 or _result_status(direct_result) != "passed":
        raise Gate7BFailure("direct-vertical failed")
    return {"lease": dict(lease_result), "direct": dict(direct_result)}


def _verify_custody(
    config: Gate7BConfiguration,
    *,
    inspect_repo: Callable[[Path], tuple[str, str]],
    hash_file: Callable[[Path], str],
) -> None:
    for label, root, expected_commit in (
        ("Rook", config.rook_root, config.approved_rook_commit),
        ("Prime", config.prime_root, config.approved_prime_commit),
    ):
        head, status = inspect_repo(root)
        if head != expected_commit:
            raise Gate7BFailure(f"{label} commit does not match the reviewed identity")
        if status:
            raise Gate7BFailure(f"{label} worktree is not clean")

    frozen_inputs = (("harness", config.harness),) + tuple(
        ("input", item) for item in config.frozen_files
    )
    for label, frozen in frozen_inputs:
        if hash_file(frozen.path) != frozen.sha256:
            raise Gate7BFailure(f"frozen {label} SHA-256 changed")


def _result_status(result: Mapping[str, object]) -> object:
    payload = result.get("result")
    return payload.get("status") if isinstance(payload, Mapping) else None


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _run_git(root: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ("git", "-C", str(root), *arguments),
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        timeout=GIT_TIMEOUT_SECONDS,
        creationflags=CREATE_NO_WINDOW,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or "git command failed"
        raise Gate7BFailure(detail)
    return completed.stdout.strip()


def inspect_repository(root: Path) -> tuple[str, str]:
    head = _run_git(root, "rev-parse", "HEAD")
    status = _run_git(root, "status", "--porcelain", "--untracked-files=all")
    return head, status


def _load_reviewed_harness(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "rookchat_prime_runtime_topology_harness_gate_7b",
        path,
    )
    if spec is None or spec.loader is None:
        raise Gate7BFailure("reviewed harness could not be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def run_reviewed_entry(
    harness_main: Callable[[Sequence[str] | None], int],
    common_arguments: Sequence[str],
    entry: str,
    run_root: Path,
) -> tuple[int, Mapping[str, object]]:
    exit_code = harness_main(
        (entry, "--run-root", str(run_root), *common_arguments)
    )
    result_path = run_root / "evidence" / "result.json"
    if not result_path.is_file():
        raise Gate7BFailure(f"{entry} did not retain its result")
    try:
        result = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Gate7BFailure(f"{entry} retained an unreadable result") from exc
    if not isinstance(result, dict):
        raise Gate7BFailure(f"{entry} result must be a JSON object")
    return exit_code, result


def production_configuration(
    *,
    approved_rook_commit: str,
    approved_harness_sha256: str,
) -> Gate7BConfiguration:
    harness_path = ROOK_ROOT / "scripts" / "rookchat_prime_runtime_topology_harness.py"
    node_path = Path("C:/Program Files/nodejs/node.exe")
    uv_path = Path("C:/Users/bring/AppData/Local/hermes/bin/uv.exe")
    prime_bundle_manifest = (
        ROOK_ROOT
        / "docs/superpowers/experiments/inputs/2026-08-30-rookchat-prime-runtime-topology-gate-7a-v4/prime-bundle-manifest.json"
    )
    goal_skill = PRIME_ROOT / "packages/coding-agent/skills/goal/SKILL.md"
    rook_skill = ROOK_ROOT / "integrations/prime/skills/rook-full/SKILL.md"
    rook_package_manifest = rook_skill.parent / "package-manifest.json"
    common_arguments = (
        "--node-path",
        str(node_path),
        "--node-sha256",
        "F13AC3CA23248DC389507E8FE38C34489AB7EDB3E6D6700EB6DA6A0B7E128EAF",
        "--prime-dist-root",
        str(PRIME_ROOT / "packages/coding-agent/dist"),
        "--prime-bundle-manifest",
        str(prime_bundle_manifest),
        "--prime-bundle-sha256",
        PRIME_BUNDLE_MANIFEST_SHA256,
        "--uv-path",
        str(uv_path),
        "--uv-sha256",
        "68A22CBAB1674647BCDA32120B214E6480F875414E3333F49F87AE99B4B0E0FA",
        "--model",
        "openai-codex/gpt-5.6-sol",
        "--goal-skill",
        str(goal_skill),
        "--goal-skill-manifest-sha256",
        GOAL_SKILL_MANIFEST_SHA256,
        "--rook-skill",
        str(rook_skill),
        "--rook-skill-manifest-sha256",
        ROOK_SKILL_MANIFEST_SHA256,
    )
    return Gate7BConfiguration(
        rook_root=ROOK_ROOT,
        prime_root=PRIME_ROOT,
        approved_rook_commit=approved_rook_commit,
        approved_prime_commit=APPROVED_PRIME_COMMIT,
        harness=FrozenFile(harness_path, approved_harness_sha256),
        frozen_files=(
            FrozenFile(
                node_path,
                "F13AC3CA23248DC389507E8FE38C34489AB7EDB3E6D6700EB6DA6A0B7E128EAF",
            ),
            FrozenFile(
                uv_path,
                "68A22CBAB1674647BCDA32120B214E6480F875414E3333F49F87AE99B4B0E0FA",
            ),
            FrozenFile(
                prime_bundle_manifest,
                "24B21152AE64CCDB3DD4AB8330DF19EE9BEBE1587870E97E040739B02B4A19B2",
            ),
            FrozenFile(
                goal_skill,
                "91E6FDC091EE6879CB521649A7C22C2B291D03893F5811F4A127D98750B371FC",
            ),
            FrozenFile(rook_package_manifest, ROOK_SKILL_MANIFEST_SHA256),
        ),
        lease_root=LEASE_ROOT,
        direct_root=DIRECT_ROOT,
        harness_arguments=common_arguments,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approved-rook-commit", required=True)
    parser.add_argument("--approved-harness-sha256", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    namespace = build_parser().parse_args(argv)
    config = production_configuration(
        approved_rook_commit=namespace.approved_rook_commit,
        approved_harness_sha256=namespace.approved_harness_sha256,
    )
    harness: ModuleType | None = None

    def run_entry(entry: str, root: Path) -> tuple[int, Mapping[str, object]]:
        nonlocal harness
        if harness is None:
            harness = _load_reviewed_harness(config.harness.path)
        return run_reviewed_entry(
            harness.main,
            config.harness_arguments,
            entry,
            root,
        )

    try:
        execute_gate_7b(
            config,
            inspect_repo=inspect_repository,
            hash_file=_sha256_file,
            run_entry=run_entry,
        )
    except BaseException as exc:
        print(f"Gate 7B refused: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
