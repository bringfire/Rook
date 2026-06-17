"""Gated live calibration for RookBIM threshold fixtures.

Offline mode validates fixture/report shape only. Live mode requires Rhino/Rook.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MCP_SRC = ROOT / "mcp_server" / "src"
if str(MCP_SRC) not in sys.path:
    sys.path.insert(0, str(MCP_SRC))

from rook.scene import calibration as cal  # noqa: E402


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model3dm", required=True)
    parser.add_argument("--sidecar", required=True)
    parser.add_argument("--validation", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--project-exact-adjacency", dest="project_exact_adjacency", action="store_true", default=True)
    parser.add_argument("--no-project-exact-adjacency", dest="project_exact_adjacency", action="store_false")
    parser.add_argument("--category", action="append", default=[])
    parser.add_argument("--cap", type=int, default=None)
    return parser.parse_args(argv)


def run_offline(args) -> dict:
    paths = cal.FixturePaths(args.model3dm, args.sidecar, args.validation)
    loaded = cal.load_fixture_bundle(paths)
    report = cal.build_offline_fixture_validation_report(
        loaded.fixture,
        paths=loaded.paths,
        fixture_id=args.name,
    )
    report["fixtures"][0]["runtime"] = {
        "projectExactAdjacency": args.project_exact_adjacency,
        "freshDocument": None,
        "graphSequence": None,
        "sceneExactNeighbors": None,
        "sceneRefineContainment": None,
        "inputObjectCount": None,
        "joinedObjectCount": None,
        "evaluatedObjectCount": None,
        "categoryFilters": args.category,
        "cap": args.cap,
    }
    cal.write_report_bundle(report, args.output_dir, args.name)
    return report


def run_live(args) -> dict:
    raise RuntimeError("live calibration orchestration is implemented in the next task")


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.offline:
        run_offline(args)
        return 0
    run_live(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
