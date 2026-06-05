from __future__ import annotations

import argparse
import sys
from pathlib import Path


DEFAULT_RHINO_EXE = Path(r"C:\Program Files\Rhino 8\System\Rhino.exe")
DEFAULT_ARTIFACT_ROOT = Path(r".scratch\rhino-runtime-harness")
RUNSCRIPT_SAFETY_TIMEOUT_SECONDS = 120.0
RUNSCRIPT_SAFETY_READINESS_TIMEOUT_SECONDS = 90.0
COMMAND_CONTROL_SATURATION_TIMEOUT_SECONDS = 45.0
COMMAND_CONTROL_SATURATION_READINESS_TIMEOUT_SECONDS = 45.0


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
    if name == "gh-readiness":
        return (
            [
                sys.executable,
                "mcp_server/tools/gh_readiness_live_harness.py",
                "--mode",
                "full",
                "--allow-mutation",
            ],
            repo_root,
        )
    if name == "gh-python-geometry-output":
        return (
            [
                sys.executable,
                "mcp_server/tools/gh_python_geometry_output_live_harness.py",
            ],
            repo_root,
        )
    if name == "p2-bridge-diagnosis":
        return (
            [
                sys.executable,
                "mcp_server/tools/p2_bridge_diagnosis_live_harness.py",
            ],
            repo_root,
        )
    if name == "p3-session-mutation":
        return (
            [
                sys.executable,
                "mcp_server/tools/p3_session_mutation_live_harness.py",
            ],
            repo_root,
        )
    if name == "p4-workbench-lifecycle":
        return (
            [
                sys.executable,
                "mcp_server/tools/p4_workbench_lifecycle_live_harness.py",
            ],
            repo_root,
        )
    if name == "p5-registry-reclaim":
        return (
            [
                sys.executable,
                "mcp_server/tools/p5_registry_reclaim_live_harness.py",
            ],
            repo_root,
        )
    if name == "p6-artifact-perception":
        return (
            [
                sys.executable,
                "mcp_server/tools/p6_artifact_perception_live_harness.py",
            ],
            repo_root,
        )
    if name == "runscript-safety":
        return (
            [
                sys.executable,
                "-m",
                "pytest",
                "tests/test_runscript_safety_live.py",
                "-m",
                "requires_rhino and runscript_safety_live and not runscript_safety_hooks",
                "-v",
            ],
            repo_root / "mcp_server",
        )
    if name == "runscript-safety-hooks":
        return (
            [
                sys.executable,
                "-m",
                "pytest",
                "tests/test_runscript_safety_live.py",
                "-m",
                "requires_rhino and runscript_safety_live and runscript_safety_hooks",
                "-v",
            ],
            repo_root / "mcp_server",
        )
    if name == "command-control-saturation":
        return (
            [
                sys.executable,
                "-m",
                "pytest",
                "tests/test_native_command_control_live.py",
                "-m",
                "requires_rhino and command_control_live",
                "-v",
            ],
            repo_root / "mcp_server",
        )
    raise ValueError(f"unknown smoke command: {name}")


def _smoke_timeout_seconds(name: str) -> float | None:
    if name in {"runscript-safety", "runscript-safety-hooks"}:
        return RUNSCRIPT_SAFETY_TIMEOUT_SECONDS
    if name == "command-control-saturation":
        return COMMAND_CONTROL_SATURATION_TIMEOUT_SECONDS
    return None


def _readiness_timeout_seconds(name: str, requested: float | None) -> float:
    if requested is not None:
        return requested
    if name in {"runscript-safety", "runscript-safety-hooks"}:
        return RUNSCRIPT_SAFETY_READINESS_TIMEOUT_SECONDS
    if name == "command-control-saturation":
        return COMMAND_CONTROL_SATURATION_READINESS_TIMEOUT_SECONDS
    return 30.0


def _launch_env_overrides(name: str) -> dict[str, str | None]:
    if name == "runscript-safety":
        return {
            "ROOK_ENABLE_INTERACTIVE_COMMAND_LEARNING": None,
            "ROOK_ENABLE_RUNSCRIPT_SAFETY_TEST_HOOKS": None,
        }
    if name == "runscript-safety-hooks":
        return {
            "ROOK_ENABLE_INTERACTIVE_COMMAND_LEARNING": None,
            "ROOK_ENABLE_RUNSCRIPT_SAFETY_TEST_HOOKS": "1",
        }
    if name == "command-control-saturation":
        return {
            "ROOK_ENABLE_INTERACTIVE_COMMAND_LEARNING": "1",
        }
    return {}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Start one owned Rhino process, run scoped smoke tests, capture artifacts, and clean it up.",
    )
    parser.add_argument("--rhino-exe", type=Path, default=DEFAULT_RHINO_EXE)
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--readiness-timeout", type=float, default=None)
    parser.add_argument("--cleanup-timeout", type=float, default=10.0)
    parser.add_argument(
        "--smoke",
        choices=[
            "ping-only",
            "pytest-select",
            "rhino-operational",
            "gh-readiness",
            "gh-python-geometry-output",
            "p2-bridge-diagnosis",
            "p3-session-mutation",
            "p4-workbench-lifecycle",
            "p5-registry-reclaim",
            "p6-artifact-perception",
            "runscript-safety",
            "runscript-safety-hooks",
            "command-control-saturation",
        ],
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
        smoke_timeout_seconds=_smoke_timeout_seconds(args.smoke),
        launch_env_overrides=_launch_env_overrides(args.smoke),
        readiness_timeout_seconds=_readiness_timeout_seconds(args.smoke, args.readiness_timeout),
        cleanup_timeout_seconds=args.cleanup_timeout,
    )
    print(f"Artifact directory: {result.artifact_dir}")
    return 0 if result.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
