"""Owned-runtime smoke for GH Python geometry output usability.

This script is meant to be launched by scripts/run_rhino_runtime_harness.py.
It requires the owned harness env, prepares Grasshopper through the existing
readiness helper, then runs the focused Point3d bake regression.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys


TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from gh_readiness_live_harness import call, prepare_gh_open  # noqa: E402


TARGET_TEST = (
    "mcp_server/tests/test_gh_create_script_live.py::"
    "test_gh_create_script_python_point_list_bakes_as_geometry"
)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _positive_int_from_env(name: str) -> int:
    raw = os.environ.get(name)
    if raw is None:
        raise AssertionError(
            f"{name} must be set by the Rhino runtime harness for this smoke."
        )
    try:
        value = int(raw)
    except ValueError as exc:
        raise AssertionError(f"{name} must be a positive integer, got {raw!r}.") from exc
    if value <= 0:
        raise AssertionError(f"{name} must be a positive integer, got {raw!r}.")
    return value


def resolve_owned_base_url() -> str:
    port = _positive_int_from_env("ROOK_RHINO_PORT")
    _positive_int_from_env("ROOK_RHINO_PROCESS_ID")
    return f"http://127.0.0.1:{port}"


def assert_owned_ping(base_url: str) -> None:
    result = call(base_url, "GET", "/ping")
    if result.get("success") is not True:
        raise AssertionError(f"Owned RookNative /ping failed before GH smoke: {result}")


def run_selected_pytest(root: Path) -> int:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            TARGET_TEST,
            "-m",
            "requires_rhino",
            "-v",
        ],
        cwd=root,
        check=False,
    )
    return result.returncode


def build_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(
        description=(
            "Prepare Grasshopper in the owned Rhino runtime and run the focused "
            "GH Python Point3d bake regression."
        )
    )


def main(argv: list[str] | None = None) -> int:
    build_parser().parse_args(argv)
    base_url = resolve_owned_base_url()
    assert_owned_ping(base_url)
    prepare_gh_open(base_url)
    return run_selected_pytest(repo_root())


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
