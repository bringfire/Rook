from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]

MIGRATED_PATHS = [
    REPO_ROOT / "mcp_server" / "src" / "rook" / "scene" / "relationship_fact_projection.py",
    REPO_ROOT / "mcp_server" / "tests" / "test_relationship_fact_projection.py",
    REPO_ROOT / "mcp_server" / "tests" / "test_relationship_fact_projection_tool.py",
    REPO_ROOT / "mcp_server" / "tests" / "test_architectural_relationship_fixture.py",
    REPO_ROOT / "mcp_server" / "tests" / "architectural_fixture_helpers.py",
    REPO_ROOT / "mcp_server" / "tests" / "pearson_g002_roundtrip_helpers.py",
    REPO_ROOT / "mcp_server" / "tests" / "test_pearson_g002_roundtrip_gate.py",
    REPO_ROOT / "experiments" / "architectural_relationship_fixture" / "assembly_graph.json",
    REPO_ROOT
    / "experiments"
    / "architectural_relationship_fixture"
    / "generated"
    / "create_architectural_fixture_rhino.py",
    REPO_ROOT / "experiments" / "architectural_relationship_fixture" / "README.md",
    REPO_ROOT / "experiments" / "pearson_robot_skeleton_graph" / "assembly_graph.json",
    REPO_ROOT
    / "experiments"
    / "pearson_robot_skeleton_graph"
    / "scripts"
    / "build_skeleton_graph_rhino.py",
    REPO_ROOT
    / "experiments"
    / "pearson_robot_skeleton_graph"
    / "generated"
    / "skeleton_graph_rhino.py",
]

STALE_SCHEMA_PATTERNS = [
    re.compile(r"rook\.graph\.member_id"),
    re.compile(r"rook\.graph\.node_id"),
    re.compile(r"rook\.graph\.owner(?!_)"),
    re.compile(r"rook\.graph\.visual_type\s*=\s*member"),
    re.compile(r"rook\.graph\.visual_type\s*=\s*joint"),
    re.compile(r'rook\.graph\.visual_type[\\"]*\s*:\s*[\\"]*member'),
    re.compile(r'rook\.graph\.visual_type[\\"]*\s*:\s*[\\"]*joint'),
]


def test_migrated_authored_graph_schema_v2_paths_do_not_use_v1_usertext_keys():
    hits = []
    for path in MIGRATED_PATHS:
        text = path.read_text(encoding="utf-8")
        for pattern in STALE_SCHEMA_PATTERNS:
            if pattern.search(text):
                hits.append((str(path.relative_to(REPO_ROOT)), pattern.pattern))

    assert hits == []
