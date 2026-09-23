from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from rook import server, targeting
from rook.agent import tool_dispatcher, tool_groups
from rook.mcp_tool_profiles import (
    PUBLIC_LEAN_TOOL_NAMES,
    PUBLIC_READONLY_TOOL_NAMES,
    Profile,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
CURRENT_GUIDANCE = (
    "AGENTS.md",
    "README.md",
    "docs/CURRENT_ARCHITECTURE.md",
    "docs/AGENT_ARCHITECTURE.md",
)
APPROVED_DIRECTOR_BOUNDARY = (
    "- Director is retired from MCP discovery, profiles, meta-tools, targeting, "
    "and internal-agent dispatch. Native `/director/*` routes and implementation "
    "modules remain temporarily preserved for disposition review; they are not a "
    "public or agent-callable capability."
)
CURRENT_DIRECTOR_GUIDANCE_DOCS = frozenset(
    {
        "docs/CURRENT_ARCHITECTURE.md",
        "docs/AGENT_ARCHITECTURE.md",
    }
)
BOUNDARY_GUIDANCE = frozenset(
    {
        "AGENTS.md",
        *CURRENT_DIRECTOR_GUIDANCE_DOCS,
    }
)
DIRECTOR_DOC_PATTERN = re.compile(
    r"rhino_director_|"
    r"(?<![A-Za-z0-9_])/director(?:/|\b)|"
    r"\b(?:Rook)?VisionDirector\b|"
    r"test_director_mcp_tools\.py",
    re.IGNORECASE,
)
# The retirement design/plan and the superpowers evidence docs were pruned from the
# public tree on 2026-09-22 (preserved in the private archive); only the docs that
# remain tracked are classified here.
CURRENT_DIRECTOR_RETIREMENT_DOCS = frozenset()
HISTORICAL_DIRECTOR_EVIDENCE_DOCS = frozenset(
    {
        "docs/TROUBLESHOOTING.md",
    }
)
ACTIONABLE_DIRECTOR_DOCS = frozenset(
    {
        "docs/rook_docs/2026-04-15-typed-route-gap-analysis.md",
    }
)
PARTIAL_SUPERSESSION_NOTICE = "\n".join(
    (
        "> **PARTIALLY SUPERSEDED — Director MCP retirement (2026-07-13):** The general",
        "> non-Director architecture and dated evidence in this document remain available.",
        "> All `rhino_director_*`, `/director`, VisionDirector, and Director-domain examples,",
        "> allowlist entries, count assumptions, acceptance criteria, and positive dispatch",
        "> tests are superseded as of 2026-07-13. Replace those examples with",
        "> non-Director fixtures when maintaining or replaying this work. This document must",
        "> not be used to restore a Director MCP tool. See the",
        "> [Director MCP Surface Retirement Design][director-mcp-retirement].",
    )
)
HISTORICAL_EVIDENCE_NOTICE = "\n".join(
    (
        "> **DIRECTOR HISTORICAL EVIDENCE — classified 2026-07-13:** Director routes,",
        "> tool names, and workflows below are retained only as dated evidence. They are not",
        "> current instructions and must not be used to restore a Director MCP tool. See the",
        "> [Director MCP Surface Retirement Design][director-mcp-retirement].",
    )
)
PARTIAL_REFERENCE_BY_DIRECTORY = {
    "docs/rook_docs/": (
        "[director-mcp-retirement]: "
        "../superpowers/specs/2026-07-13-director-mcp-surface-retirement-design.md"
    ),
}
HISTORICAL_REFERENCE_BY_DOCUMENT = {
    "docs/TROUBLESHOOTING.md": (
        "[director-mcp-retirement]: "
        "superpowers/specs/2026-07-13-director-mcp-surface-retirement-design.md"
    ),
}
TRACKED_GUIDANCE_ROOTS = (
    ".agents",
    ".claude/skills",
    ".claude-plugin",
    "hooks",
    "installer",
)
TRACKED_GUIDANCE_SUFFIXES = {
    ".iss", ".json", ".md", ".ps1", ".py", ".toml", ".txt", ".yaml", ".yml"
}


RETIRED_DIRECTOR_TOOLS = (
    "rhino_director_run",
    "rhino_director_curve_samples",
    "rhino_director_assemble_video",
    "rhino_director_publish_video",
    "rhino_director_canvas_extract",
    "rhino_director_replay",
    "rhino_director_replay_cancel",
    "rhino_director_compile_motion",
    "rhino_director_package_take",
    "rhino_director_prepare_take",
    "rhino_director_compile_take",
    "rhino_director_worker_play",
    "rhino_director_capture_take",
    "rhino_director_preview_motion",
    "rhino_director_capture_source_occurrence_v2",
    "rhino_director_build_actor_set_from_source_occurrence_v2",
    "rhino_director_write_actor_metadata_v2",
    "rhino_director_read_actor_metadata_v2",
)

DIRECTOR_PREFIX_PROBES = RETIRED_DIRECTOR_TOOLS + (
    "rhino_director_migrate_actor_metadata_v2",
    "rhino_director_future_probe",
)


MEDIA_SENTINELS = frozenset(
    {
        "rhino_render_video",
        "rhino_video_status",
        "rhino_video_cancel",
        "rhino_video_result",
        "rhino_video_estimate",
        "rhino_video_jobs",
        "rhino_video_models",
        "rhino_viewport",
        "rhino_capture_depth",
        "rhino_display_modes",
        "rhino_display_mode_set",
        "rhino_vision_artifacts",
        "rhino_vision_get_artifact",
        "rhino_vision_approve",
        "rhino_vision_delete_artifact",
        "rhino_vision_consume_approved",
        "rhino_vision_presentation",
    }
)

READONLY_MEDIA_SENTINELS = frozenset(
    {
        "rhino_video_status",
        "rhino_video_result",
        "rhino_video_estimate",
        "rhino_video_jobs",
        "rhino_video_models",
        "rhino_display_modes",
        "rhino_vision_artifacts",
        "rhino_vision_get_artifact",
    }
)


def _serialized_tools(tools) -> str:
    return json.dumps(
        [
            {
                "name": tool.name,
                "description": tool.description,
                "inputSchema": tool.inputSchema,
            }
            for tool in tools
        ],
        sort_keys=True,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("profile", ("full", "lean", "readonly"))
async def test_serialized_discovery_contains_no_director_guidance(monkeypatch, profile):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", profile)
    payload = _serialized_tools(await server.list_tools())
    lowered = payload.lower()
    assert "rhino_director_" not in lowered
    assert "/director" not in lowered
    assert "visiondirector" not in lowered
    assert '\"director\"' not in lowered


def _forbidden_sync(label):
    def fail(*args, **kwargs):
        raise AssertionError(f"{label} must not run")

    return fail


def _forbidden_async(label):
    async def fail(*args, **kwargs):
        raise AssertionError(f"{label} must not run")

    return fail


@pytest.mark.asyncio
@pytest.mark.parametrize("profile", ("full", "lean", "readonly"))
@pytest.mark.parametrize("tool_name", DIRECTOR_PREFIX_PROBES)
async def test_director_prefix_stops_before_targeting_and_dispatch(
    monkeypatch, profile, tool_name
):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", profile)
    discovery_calls = []

    def no_live_instances():
        discovery_calls.append("entered")
        return []

    monkeypatch.setattr(
        server.targeting, "policy_for_tool", _forbidden_sync("targeting policy")
    )
    monkeypatch.setattr(
        server.targeting,
        "get_panel_target_config_error",
        _forbidden_sync("panel policy"),
    )
    monkeypatch.setattr(
        server.targeting, "get_panel_target_lock", _forbidden_sync("panel lock")
    )
    monkeypatch.setattr(
        server.targeting, "discover_instances", no_live_instances
    )
    monkeypatch.setattr(
        server.targeting, "resolve_tool_route", _forbidden_sync("target resolution")
    )
    monkeypatch.setattr(
        server, "_call_tool_dispatch", _forbidden_async("tool dispatch")
    )

    result = await server.call_tool(
        tool_name,
        {"port": 9950, "session": "conflicting-target"},
    )
    text = result[0].text
    if profile == "readonly":
        assert "tool_profile_blocked" in text
        assert tool_name in text
    else:
        assert text == f"Error: Unknown tool: {tool_name}"
    assert discovery_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("profile", ("full", "lean", "readonly"))
async def test_non_director_unknown_keeps_existing_policy_path(monkeypatch, profile):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", profile)
    calls = []

    def policy_for_tool(name):
        calls.append(("policy", name))
        return SimpleNamespace(requires_rhino=False)

    async def dispatch(name, arguments):
        calls.append(("dispatch", name))
        return {"success": False, "data": f"Unknown tool: {name}"}

    monkeypatch.setattr(server.targeting, "policy_for_tool", policy_for_tool)
    monkeypatch.setattr(server, "_call_tool_dispatch", dispatch)
    result = await server.call_tool("rhino_unknown_future_probe", {})

    if profile == "readonly":
        assert "tool_profile_blocked" in result[0].text
        assert calls == []
    else:
        assert result[0].text == "Error: Unknown tool: rhino_unknown_future_probe"
        assert calls == [
            ("policy", "rhino_unknown_future_probe"),
            ("dispatch", "rhino_unknown_future_probe"),
        ]


def test_server_has_no_active_director_runtime_imports():
    for attribute in (
        "canvas_director",
        "director",
        "director_actor_metadata",
        "director_compiler",
        "director_preview",
        "director_publish",
        "director_take_package",
        "director_video",
        "director_worker_capture",
        "director_worker_compile",
        "director_worker_play",
        "director_worker_prepare",
    ):
        assert not hasattr(server, attribute), attribute


def test_director_case_labels_are_absent():
    labels = server._scan_dispatch_case_labels()
    assert set(DIRECTOR_PREFIX_PROBES).isdisjoint(labels)


def test_secondary_callable_registries_contain_no_director_surface():
    assert "director" not in tool_groups.TOOL_GROUPS
    assert "director_readonly" not in tool_groups.TOOL_GROUPS
    assert "director" not in tool_groups.MCP_ONLY_GROUPS
    assert "director_readonly" not in tool_groups.READONLY_ALLOWED_GROUPS
    grouped_names = {
        name for names in tool_groups.TOOL_GROUPS.values() for name in names
    }
    assert not any(name.startswith("rhino_director_") for name in grouped_names)
    assert not any(
        name.startswith("rhino_director_")
        for name in tool_dispatcher.BRIDGE_ROUTES
    )
    assert not any(
        name.startswith("rhino_director_") for name in targeting._ALL_KNOWN_TOOLS
    )
    assert not any(
        name.startswith("rhino_director_") for name in targeting.TOOL_POLICIES
    )
    assert not any(
        name.startswith("rhino_director_") for name in PUBLIC_LEAN_TOOL_NAMES
    )
    assert not any(
        name.startswith("rhino_director_") for name in PUBLIC_READONLY_TOOL_NAMES
    )


@pytest.mark.asyncio
async def test_live_agent_inventory_contains_no_director_record():
    tools = await server._all_live_tools()
    records = server._collect_agent_records(tools)
    assert "rhino_objects" in records
    assert not any(name.startswith("rhino_director_") for name in records)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("profile", "expected_error"),
    (
        (Profile.FULL, "not_mcp_dispatchable"),
        (Profile.LEAN, "not_mcp_dispatchable"),
        (Profile.READONLY, "tool_profile_blocked"),
    ),
)
@pytest.mark.parametrize("tool_name", DIRECTOR_PREFIX_PROBES)
async def test_meta_dispatch_cannot_recover_director(
    monkeypatch, profile, expected_error, tool_name
):
    server._reset_capability_index_cache()

    async def forbidden_call_tool(*args, **kwargs):
        raise AssertionError("meta dispatcher must not re-enter call_tool")

    monkeypatch.setattr(server, "call_tool", forbidden_call_tool)
    result = await server._handle_meta_tool(
        "rook_tools_call",
        {"name": tool_name, "arguments": {}},
        profile,
    )
    assert expected_error in result[0].text


@pytest.mark.asyncio
async def test_progressive_catalog_has_no_director_record_or_path():
    server._reset_capability_index_cache()
    index = await server._get_capability_index()
    assert not any(record.name.startswith("rhino_director_") for record in index.records)
    assert not any(record.domain == "director" for record in index.records)
    assert index.read("rhino_director_preview_motion") is None
    root = index.ls("/", depth=1)
    assert "/director" not in root["children"]
    assert not any(entry["domain"] == "director" for entry in root["entries"])


@pytest.mark.asyncio
async def test_media_sentinels_keep_discovery_dispatch_and_targeting(monkeypatch):
    monkeypatch.delenv("ROOK_MCP_TOOL_PROFILE", raising=False)
    full = {tool.name for tool in await server.list_tools()}
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "lean")
    lean = {tool.name for tool in await server.list_tools()}
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "readonly")
    readonly = {tool.name for tool in await server.list_tools()}

    assert MEDIA_SENTINELS <= full
    assert MEDIA_SENTINELS.isdisjoint(lean)
    assert MEDIA_SENTINELS & readonly == READONLY_MEDIA_SENTINELS
    assert MEDIA_SENTINELS <= server._dispatchable_tool_names()

    for name in MEDIA_SENTINELS:
        policy = targeting.policy_for_tool(name)
        assert policy.requires_rhino is True
        assert policy.risk == (
            "read" if name in READONLY_MEDIA_SENTINELS else "mutate"
        )


@pytest.mark.asyncio
async def test_scanner_failure_cannot_gate_normal_direct_dispatch(monkeypatch):
    def source_unavailable(*args, **kwargs):
        raise OSError("source unavailable in frozen build")

    monkeypatch.setattr(server.inspect, "getsource", source_unavailable)
    assert server._scan_dispatch_case_labels() == server.META_TOOL_NAMES
    monkeypatch.setattr(
        server, "_DISPATCHABLE_TOOL_NAMES", server.META_TOOL_NAMES
    )
    monkeypatch.setattr(
        server.targeting,
        "policy_for_tool",
        lambda name: SimpleNamespace(requires_rhino=False),
    )

    called = []

    async def dispatch(name, arguments):
        called.append(name)
        return {"success": True, "data": {"name": name}}

    monkeypatch.setattr(server, "_call_tool_dispatch", dispatch)
    result = await server.call_tool("rhino_objects", {})
    assert json.loads(result[0].text) == {"name": "rhino_objects"}
    assert called == ["rhino_objects"]


def _git_tracked_relative_paths(*roots: str) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z", "--", *roots],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    )
    return [
        relative
        for relative in result.stdout.decode("utf-8").split("\0")
        if relative
    ]


def _route_aware_director_documents() -> dict[str, str]:
    matches = {}
    for relative in _git_tracked_relative_paths("docs"):
        if not relative.startswith("docs/") or not relative.endswith(".md"):
            continue
        path = REPO_ROOT / relative
        text = path.read_text(encoding="utf-8", errors="replace")
        if DIRECTOR_DOC_PATTERN.search(text):
            matches[relative] = text
    return matches


def test_current_guidance_has_no_actionable_director_instruction():
    for relative in CURRENT_GUIDANCE:
        text = (REPO_ROOT / relative).read_text(encoding="utf-8")
        expected_boundary_count = 1 if relative in BOUNDARY_GUIDANCE else 0
        assert text.count(APPROVED_DIRECTOR_BOUNDARY) == expected_boundary_count, (
            relative
        )
        remaining = text.replace(APPROVED_DIRECTOR_BOUNDARY, "")
        assert DIRECTOR_DOC_PATTERN.search(remaining) is None, relative
        assert "director-based" not in remaining.lower(), relative


def _partial_reference_for(relative: str) -> str:
    matches = [
        reference
        for directory, reference in PARTIAL_REFERENCE_BY_DIRECTORY.items()
        if relative.startswith(directory)
    ]
    assert len(matches) == 1, relative
    return matches[0]


def _assert_exact_notice_block(
    text: str,
    notice: str,
    reference: str,
    relative: str,
) -> None:
    block = f"{notice}\n\n{reference}"
    assert text.count(block) == 1, relative
    assert text.count(notice) == 1, relative
    references = re.findall(
        r"(?m)^\[director-mcp-retirement\]: .+$",
        text,
    )
    assert references == [reference], relative


def test_every_route_aware_director_document_is_classified():
    documents = _route_aware_director_documents()
    groups = (
        CURRENT_DIRECTOR_GUIDANCE_DOCS,
        CURRENT_DIRECTOR_RETIREMENT_DOCS,
        HISTORICAL_DIRECTOR_EVIDENCE_DOCS,
        ACTIONABLE_DIRECTOR_DOCS,
    )
    assert [len(group) for group in groups] == [2, 0, 1, 1]
    for index, group in enumerate(groups):
        for other in groups[index + 1 :]:
            assert group.isdisjoint(other)
    expected_documents = frozenset().union(*groups)
    assert len(expected_documents) == 4
    assert set(documents) == expected_documents
    assert set(HISTORICAL_REFERENCE_BY_DOCUMENT) == (
        HISTORICAL_DIRECTOR_EVIDENCE_DOCS
    )

    for relative in sorted(ACTIONABLE_DIRECTOR_DOCS):
        _assert_exact_notice_block(
            documents[relative],
            PARTIAL_SUPERSESSION_NOTICE,
            _partial_reference_for(relative),
            relative,
        )
    for relative in sorted(HISTORICAL_DIRECTOR_EVIDENCE_DOCS):
        _assert_exact_notice_block(
            documents[relative],
            HISTORICAL_EVIDENCE_NOTICE,
            HISTORICAL_REFERENCE_BY_DOCUMENT[relative],
            relative,
        )


def test_installed_agent_assets_do_not_teach_director_mcp():
    tracked = [
        REPO_ROOT / relative
        for relative in _git_tracked_relative_paths(*TRACKED_GUIDANCE_ROOTS)
    ]
    assert tracked
    for path in tracked:
        if path.suffix.lower() not in TRACKED_GUIDANCE_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        assert DIRECTOR_DOC_PATTERN.search(text) is None, path


def test_director_artifact_preservation_guard_remains():
    guard = (
        REPO_ROOT / "scripts/tests/release-installer-guards.tests.ps1"
    ).read_text(encoding="utf-8")
    assert "RookVisionDirector" in guard
