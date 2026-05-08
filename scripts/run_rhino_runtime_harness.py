from __future__ import annotations

import argparse
import sys
from pathlib import Path


DEFAULT_RHINO_EXE = Path(r"C:\Program Files\Rhino 8\System\Rhino.exe")
DEFAULT_ARTIFACT_ROOT = Path(r".scratch\rhino-runtime-harness")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _add_mcp_src_to_path(repo_root: Path) -> None:
    mcp_src = repo_root / "mcp_server" / "src"
    sys.path.insert(0, str(mcp_src))


def _smoke_command(name: str, repo_root: Path) -> tuple[list[str], Path]:
    if name == "ping-only":
        return (["ping-only"], repo_root)
    if name == "pytest-select":
        return (
            [
                sys.executable,
                "-m",
                "pytest",
                "tests/test_select_additive_live.py",
                "-m",
                "requires_rhino",
                "-v",
            ],
            repo_root / "mcp_server",
        )
    if name == "rhino-operational":
        return (
            [sys.executable, "scripts/validate_rhino_operational_suite.py"],
            repo_root,
        )
    raise ValueError(f"unknown smoke command: {name}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Start one owned Rhino process, run scoped smoke tests, capture artifacts, and clean it up.",
    )
    parser.add_argument("--rhino-exe", type=Path, default=DEFAULT_RHINO_EXE)
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_ARTIFACT_ROOT)
    parser.add_argument(
        "--smoke",
        choices=["ping-only", "pytest-select", "rhino-operational"],
        default="pytest-select",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    repo_root = _repo_root()
    _add_mcp_src_to_path(repo_root)

    from rook.runtime_harness import run_rhino_runtime_harness

    args = build_parser().parse_args(argv)
    command, cwd = _smoke_command(args.smoke, repo_root)
    artifact_root = args.artifact_root
    if not artifact_root.is_absolute():
        artifact_root = repo_root / artifact_root

    result = run_rhino_runtime_harness(
        rhino_exe=args.rhino_exe,
        artifact_root=artifact_root,
        smoke_command=command,
        smoke_kind=args.smoke,
        smoke_cwd=cwd,
    )
    print(f"Artifact directory: {result.artifact_dir}")
    return 0 if result.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
