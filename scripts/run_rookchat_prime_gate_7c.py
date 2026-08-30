"""Absorbing admission wrapper for the reviewed Gate 7C broker harness."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType


class Gate7CAdmissionFailure(RuntimeError):
    pass


@dataclass(frozen=True)
class Gate7CAdmission:
    rook_root: Path
    prime_root: Path
    approved_rook_commit: str
    approved_prime_commit: str
    harness_path: Path
    harness_sha256: str
    result_path: Path


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def inspect_repository(root: Path) -> tuple[str, str]:
    head = subprocess.run(
        ("git", "rev-parse", "HEAD"),
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    ).stdout.strip()
    status = subprocess.run(
        ("git", "status", "--porcelain", "--untracked-files=all"),
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    ).stdout
    return head, status


def _load_harness(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location("reviewed_gate_7c_harness", path)
    if spec is None or spec.loader is None:
        raise Gate7CAdmissionFailure("unable to load reviewed Gate 7C harness")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def invoke_harness(path: Path, arguments: Sequence[str]) -> int:
    module = _load_harness(path)
    main = getattr(module, "main", None)
    if not callable(main):
        raise Gate7CAdmissionFailure("reviewed Gate 7C harness has no main entry")
    return int(main(list(arguments)))


def execute_gate_7c(
    admission: Gate7CAdmission,
    harness_arguments: Sequence[str],
    *,
    repository_inspector: Callable[[Path], tuple[str, str]] = inspect_repository,
    file_hasher: Callable[[Path], str] = _sha256_file,
    harness_invoker: Callable[[Path, Sequence[str]], int] = invoke_harness,
) -> dict[str, object]:
    if any(
        argument == "--result" or argument.startswith("--result=")
        for argument in harness_arguments
    ):
        raise Gate7CAdmissionFailure("Gate 7C result path is wrapper-owned")
    if admission.result_path.parent.exists():
        raise Gate7CAdmissionFailure("Gate 7C evidence root already exists")
    if not admission.harness_path.is_file():
        raise Gate7CAdmissionFailure("reviewed Gate 7C harness is missing")
    if file_hasher(admission.harness_path) != admission.harness_sha256:
        raise Gate7CAdmissionFailure("Gate 7C harness differs from review")
    for root, expected, label in (
        (admission.rook_root, admission.approved_rook_commit, "Rook"),
        (admission.prime_root, admission.approved_prime_commit, "Prime"),
    ):
        head, status = repository_inspector(root)
        if head != expected:
            raise Gate7CAdmissionFailure(f"{label} HEAD differs from review")
        if status:
            raise Gate7CAdmissionFailure(f"{label} worktree is dirty")
    result = harness_invoker(
        admission.harness_path,
        (*harness_arguments, "--result", str(admission.result_path)),
    )
    if result != 0:
        raise Gate7CAdmissionFailure(
            f"Gate 7C harness failed with exit code {result}; do not retry"
        )
    if not admission.result_path.is_file():
        raise Gate7CAdmissionFailure("Gate 7C harness returned without a result")
    try:
        payload = json.loads(admission.result_path.read_text(encoding="ascii"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise Gate7CAdmissionFailure("Gate 7C result is unreadable") from error
    if not isinstance(payload, dict) or payload.get("status") != "passed":
        raise Gate7CAdmissionFailure("Gate 7C result did not pass")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rook-root", required=True)
    parser.add_argument("--prime-root", required=True)
    parser.add_argument("--approved-rook-commit", required=True)
    parser.add_argument("--approved-prime-commit", required=True)
    parser.add_argument("--harness", required=True)
    parser.add_argument("--harness-sha256", required=True)
    parser.add_argument("--result", required=True)
    parser.add_argument("harness_arguments", nargs=argparse.REMAINDER)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    namespace = build_parser().parse_args(argv)
    arguments = list(namespace.harness_arguments)
    if arguments[:1] == ["--"]:
        arguments = arguments[1:]
    admission = Gate7CAdmission(
        rook_root=Path(namespace.rook_root),
        prime_root=Path(namespace.prime_root),
        approved_rook_commit=namespace.approved_rook_commit,
        approved_prime_commit=namespace.approved_prime_commit,
        harness_path=Path(namespace.harness),
        harness_sha256=namespace.harness_sha256,
        result_path=Path(namespace.result),
    )
    try:
        execute_gate_7c(admission, arguments)
    except Exception as error:
        print(f"Gate 7C admission failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
