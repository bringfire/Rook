"""
Phase 3 Catalog Bootstrap Tests
================================

Verifies:
A: Catalog cache round-trip (save → load → identical, edge cases, corruption)
B: spawn.py cache loading integration (actual run_task path, not tautologies)
C: WORKER.md structural validation (sections, ordering, exclusions)
D: Full dispatch coverage with catalog (Tier 0 enforcement, group mechanics)
E: Dynamic system prompt (_build_worker_prompt correctness)
"""

import asyncio
import json
import sys
import os
import re
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

passed = 0
failed = 0


def test(name):
    """Test decorator for tracking pass/fail."""
    def decorator(fn):
        global passed, failed
        try:
            result = fn()
            if asyncio.iscoroutine(result):
                asyncio.get_event_loop().run_until_complete(result)
            print(f"  PASS: {name}")
            passed += 1
        except Exception as e:
            print(f"  FAIL: {name} — {e}")
            failed += 1
        return fn
    return decorator


# =========================================================================
# A: Catalog cache round-trip — tests correctness, not just "it works"
# =========================================================================

print("\n=== A: Catalog Cache Round-Trip ===")


@test("round-trip preserves exact schema structure including nested parameters")
def _():
    from rook.agent.tool_registry import save_catalog_to_cache, load_catalog_from_cache

    # Use a realistic schema with nested parameters, required fields, enums
    catalog = {
        "gh_connect": {
            "type": "function",
            "function": {
                "name": "gh_connect",
                "description": "Wire two GH components together.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "source_guid": {"type": "string", "description": "Source GUID"},
                        "target_guid": {"type": "string", "description": "Target GUID"},
                        "source_output": {"type": "integer", "default": 0},
                    },
                    "required": ["source_guid", "target_guid"],
                },
            },
        },
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        cache_path = Path(tmpdir) / "test_catalog.json"
        save_catalog_to_cache(catalog, cache_path)
        loaded = load_catalog_from_cache(cache_path)

        # Deep equality — not just len, but exact nested structure
        assert loaded == catalog, f"Deep structure mismatch"
        # Verify nested fields survived
        params = loaded["gh_connect"]["function"]["parameters"]
        assert params["required"] == ["source_guid", "target_guid"]
        assert params["properties"]["source_output"]["default"] == 0


@test("empty catalog round-trips to empty dict, not None")
def _():
    from rook.agent.tool_registry import save_catalog_to_cache, load_catalog_from_cache

    with tempfile.TemporaryDirectory() as tmpdir:
        cache_path = Path(tmpdir) / "test_catalog.json"
        save_catalog_to_cache({}, cache_path)
        loaded = load_catalog_from_cache(cache_path)
        assert loaded == {}, f"Empty catalog should round-trip to {{}}, got {loaded}"
        assert loaded is not None, "Should be empty dict, not None"


@test("missing file returns None (not crash, not empty dict)")
def _():
    from rook.agent.tool_registry import load_catalog_from_cache

    result = load_catalog_from_cache(Path("/nonexistent/path/catalog.json"))
    assert result is None, f"Should return None for missing file, got {type(result)}"


@test("corrupted JSON returns None (not crash)")
def _():
    from rook.agent.tool_registry import load_catalog_from_cache

    with tempfile.TemporaryDirectory() as tmpdir:
        cache_path = Path(tmpdir) / "bad.json"
        cache_path.write_text("not valid json {{{{")
        result = load_catalog_from_cache(cache_path)
        assert result is None


@test("valid JSON but wrong type (array instead of dict) returns array — no type guard")
def _():
    """Proves we DON'T validate the schema — a potential bug to document."""
    from rook.agent.tool_registry import load_catalog_from_cache

    with tempfile.TemporaryDirectory() as tmpdir:
        cache_path = Path(tmpdir) / "array.json"
        cache_path.write_text('[1, 2, 3]')
        result = load_catalog_from_cache(cache_path)
        # This IS a gap — we return the array instead of None.
        # Test documents this behavior so we notice if/when we add type guards.
        assert isinstance(result, list), "Current behavior: returns raw parsed JSON without type check"


@test("atomic write: crash simulation — .tmp doesn't leak on success")
def _():
    from rook.agent.tool_registry import save_catalog_to_cache

    with tempfile.TemporaryDirectory() as tmpdir:
        cache_path = Path(tmpdir) / "test.json"
        save_catalog_to_cache({"a": 1}, cache_path)
        # Verify no .tmp leftover
        tmp_files = list(Path(tmpdir).glob("*.tmp"))
        assert len(tmp_files) == 0, f".tmp files leaked: {tmp_files}"
        # Verify final file is valid JSON
        with open(cache_path) as f:
            data = json.load(f)
        assert data == {"a": 1}


@test("overwrite: saving twice replaces content, doesn't append")
def _():
    from rook.agent.tool_registry import save_catalog_to_cache, load_catalog_from_cache

    with tempfile.TemporaryDirectory() as tmpdir:
        cache_path = Path(tmpdir) / "test.json"
        save_catalog_to_cache({"v1_tool": {}}, cache_path)
        save_catalog_to_cache({"v2_tool": {}}, cache_path)
        loaded = load_catalog_from_cache(cache_path)
        assert "v2_tool" in loaded, "Second save should overwrite"
        assert "v1_tool" not in loaded, "First save's data should be gone"


# =========================================================================
# B: spawn.py cache loading — test the ACTUAL fallback path
# =========================================================================

print("\n=== B: Spawn Cache Loading ===")


@test("get_catalog_cache_path resolves to knowledge/ at repo root")
def _():
    from rook.agent.tool_registry import get_catalog_cache_path

    path = get_catalog_cache_path()
    assert path.name == "agent_tool_catalog.json"
    assert path.parent.name == "knowledge"
    # The grandparent should be the repo root (contains mcp_server/)
    repo_root = path.parent.parent
    assert (repo_root / "mcp_server").exists(), \
        f"Path {path} doesn't resolve to repo root. Parent: {repo_root}"


@test("run_task cache fallback: catalog=None triggers load_catalog_from_cache")
def _():
    """Test the ACTUAL code path in run_task, not a manual simulation."""
    from rook.agent.spawn import run_task

    calls = []

    def tracking_load(cache_path=None):
        calls.append(cache_path)
        return {
            "rhino_ping": {
                "type": "function",
                "function": {"name": "rhino_ping", "description": "test", "parameters": {}},
            },
        }

    # Patch at the SOURCE module (tool_registry), since run_task does
    # `from .tool_registry import load_catalog_from_cache` inside the function body
    with patch("rook.agent.tool_registry.load_catalog_from_cache", side_effect=tracking_load):
        with patch("rook.agent.base_agent.RookAgent") as MockAgent:
            agent_instance = MagicMock()
            agent_instance.prompt = AsyncMock()
            agent_instance.wait_for_idle = AsyncMock()
            agent_instance.messages = []
            agent_instance._total_input_tokens = 0
            agent_instance._total_output_tokens = 0
            agent_instance._total_cost = 0.0
            agent_instance._turn_count = 0
            agent_instance.config = MagicMock()
            agent_instance.config.model = "test"
            agent_instance.config.guardian_enabled = False
            MockAgent.return_value = agent_instance

            async def _run():
                return await run_task(
                    "test task",
                    catalog=None,
                    guardian_enabled=False,
                )

            asyncio.get_event_loop().run_until_complete(_run())

        # Verify load_catalog_from_cache was actually called
        assert len(calls) >= 1, f"load_catalog_from_cache never called! calls={calls}"


@test("run_task with explicit catalog=dict does NOT trigger cache fallback")
def _():
    """When catalog is provided, the cache should NOT be consulted."""
    from rook.agent.spawn import run_task

    with patch("rook.agent.tool_registry.load_catalog_from_cache") as mock_load:
        with patch("rook.agent.base_agent.RookAgent") as MockAgent:
            agent_instance = MagicMock()
            agent_instance.prompt = AsyncMock()
            agent_instance.wait_for_idle = AsyncMock()
            agent_instance.messages = []
            agent_instance._total_input_tokens = 0
            agent_instance._total_output_tokens = 0
            agent_instance._total_cost = 0.0
            agent_instance._turn_count = 0
            agent_instance.config = MagicMock()
            agent_instance.config.model = "test"
            agent_instance.config.guardian_enabled = False
            MockAgent.return_value = agent_instance

            async def _run():
                return await run_task(
                    "test task",
                    catalog={"rhino_ping": {"type": "function", "function": {"name": "rhino_ping", "description": "t", "parameters": {}}}},
                    guardian_enabled=False,
                )

            asyncio.get_event_loop().run_until_complete(_run())

        mock_load.assert_not_called()


@test("run_plan cache fallback: catalog=None triggers load_catalog_from_cache")
def _():
    """run_plan has the same cache fallback as run_task."""
    from rook.agent.spawn import run_plan

    with patch("rook.agent.tool_registry.load_catalog_from_cache") as mock_load:
        mock_load.return_value = {"rhino_ping": {"type": "function", "function": {"name": "rhino_ping", "description": "t", "parameters": {}}}}

        with patch("rook.agent.planner.Planner") as MockPlanner:
            planner_instance = MagicMock()
            planner_instance.run = AsyncMock(return_value=MagicMock())
            MockPlanner.return_value = planner_instance

            async def _run():
                return await run_plan("test request", catalog=None)

            asyncio.get_event_loop().run_until_complete(_run())

        mock_load.assert_called_once()


# =========================================================================
# C: WORKER.md structural validation — not just substring matching
# =========================================================================

print("\n=== C: WORKER.md Content ===")


@test("WORKER.md has required sections in correct order")
def _():
    from rook.agent.base_agent import RookAgent
    prompt = RookAgent._default_system_prompt()

    # Required sections must exist
    required_sections = [
        "## Your Task",
        "## Preloaded Tools",
        "## Tool Usage Patterns",
        "## Common Gotchas",
        "## Error Recovery",
        "## Workspace Constraints",
        "## Completion",
    ]
    for section in required_sections:
        assert section in prompt, f"Missing required section: {section}"

    # Verify ordering — each section should come after the previous one
    positions = [prompt.index(s) for s in required_sections]
    for i in range(len(positions) - 1):
        assert positions[i] < positions[i + 1], \
            f"Section ordering wrong: '{required_sections[i]}' (pos {positions[i]}) " \
            f"should come before '{required_sections[i+1]}' (pos {positions[i+1]})"


@test("WORKER.md 4-step GH workflow is coherent (create->wire->set->verify)")
def _():
    from rook.agent.base_agent import RookAgent
    prompt = RookAgent._default_system_prompt()

    # Extract the Grasshopper Composition section
    gh_section_start = prompt.index("### Grasshopper Composition")
    # Find the next ### section or ## section
    next_section = prompt.find("\n### ", gh_section_start + 1)
    if next_section == -1:
        next_section = prompt.find("\n## ", gh_section_start + 1)
    gh_section = prompt[gh_section_start:next_section]

    # Must contain the 4 steps in order
    step_keywords = [
        ("gh_component", "Step 1: Create components"),
        ("gh_connect", "Step 2: Wire connections"),
        ("gh_set_value", "Step 3: Set values"),
        ("gh_errors", "Step 4: Verify"),
    ]
    last_pos = -1
    for keyword, step_name in step_keywords:
        pos = gh_section.find(keyword)
        assert pos != -1, f"{step_name} missing — '{keyword}' not found in GH section"
        assert pos > last_pos, f"{step_name} is out of order"
        last_pos = pos


@test("WORKER.md explicitly EXCLUDES gh_execute_intent")
def _():
    from rook.agent.base_agent import RookAgent
    prompt = RookAgent._default_system_prompt()

    assert "gh_execute_intent" not in prompt, \
        "WORKER.md must NOT mention gh_execute_intent (excluded from agents)"


@test("WORKER.md Preloaded Tools section lists all gh_canvas tools")
def _():
    from rook.agent.base_agent import RookAgent
    from rook.agent.tool_groups import TOOL_GROUPS

    prompt = RookAgent._default_system_prompt()

    # Extract Preloaded Tools section
    preloaded_start = prompt.index("## Preloaded Tools")
    preloaded_end = prompt.find("\n## ", preloaded_start + 1)
    preloaded_section = prompt[preloaded_start:preloaded_end]

    # Every tool in the gh_canvas group should be mentioned
    gh_canvas_tools = TOOL_GROUPS["gh_canvas"]
    missing = [t for t in gh_canvas_tools if t not in preloaded_section]
    assert not missing, \
        f"Preloaded Tools section missing gh_canvas tools: {missing}"


@test("WORKER.md Common Gotchas mentions gh_knowledge_query for GUID resolution")
def _():
    from rook.agent.base_agent import RookAgent
    prompt = RookAgent._default_system_prompt()

    gotchas_start = prompt.index("## Common Gotchas")
    gotchas_end = prompt.find("\n## ", gotchas_start + 1)
    gotchas_section = prompt[gotchas_start:gotchas_end]

    assert "gh_knowledge_query" in gotchas_section, \
        "Gotchas should mention gh_knowledge_query for GUID resolution"
    assert "never" in gotchas_section.lower() or "NEVER" in gotchas_section, \
        "Gotchas should warn against hardcoding GUIDs"


# =========================================================================
# D: Full dispatch coverage with catalog
# =========================================================================

print("\n=== D: Dispatch Coverage ===")


@test("agent_mode=True excludes ONLY gh_execute_intent, not rhino_execute_intent")
def _():
    from rook.agent.tool_registry import ToolRegistry

    # Put BOTH execute_intent tools in catalog
    catalog = {
        "gh_execute_intent": {
            "type": "function",
            "function": {"name": "gh_execute_intent", "description": "GH intent", "parameters": {}},
        },
        "rhino_execute_intent": {
            "type": "function",
            "function": {"name": "rhino_execute_intent", "description": "Rhino intent", "parameters": {}},
        },
    }
    registry = ToolRegistry(catalog=catalog, agent_mode=True)
    active = {s["function"]["name"] for s in registry.get_active_schemas()}

    assert "gh_execute_intent" not in active, "gh_execute_intent must be excluded"
    assert "rhino_execute_intent" in active, "rhino_execute_intent must be included"


@test("agent_mode=False INCLUDES gh_execute_intent (normal MCP path)")
def _():
    from rook.agent.tool_registry import ToolRegistry

    catalog = {
        "gh_execute_intent": {
            "type": "function",
            "function": {"name": "gh_execute_intent", "description": "test", "parameters": {}},
        },
    }
    registry = ToolRegistry(catalog=catalog, agent_mode=False)
    active = {s["function"]["name"] for s in registry.get_active_schemas()}

    assert "gh_execute_intent" in active, \
        "Non-agent mode should include gh_execute_intent (it's in TIER_0)"


@test("gh_canvas preload activates ALL 16 canvas tools and nothing else")
def _():
    from rook.agent.tool_registry import ToolRegistry
    from rook.agent.tool_groups import TOOL_GROUPS

    gh_canvas_tools = set(TOOL_GROUPS["gh_canvas"])

    # Build catalog with gh_canvas + some extra tools
    catalog = {}
    for name in gh_canvas_tools:
        catalog[name] = {
            "type": "function",
            "function": {"name": name, "description": f"{name} tool", "parameters": {}},
        }
    # Add a non-canvas tool that shouldn't be activated
    catalog["rhino_boolean"] = {
        "type": "function",
        "function": {"name": "rhino_boolean", "description": "Boolean", "parameters": {}},
    }

    registry = ToolRegistry(catalog=catalog, agent_mode=True)

    # Before preload: canvas tools NOT in Tier 0 should be inactive
    pre_active = {s["function"]["name"] for s in registry.get_active_schemas()}
    from rook.agent.tool_groups import AGENT_TIER_0
    non_tier0_canvas = gh_canvas_tools - AGENT_TIER_0
    for name in non_tier0_canvas:
        assert name not in pre_active, f"{name} active before preload (shouldn't be)"

    # Preload
    result = registry.request_group("gh_canvas", turn=0)
    assert result["success"] is True

    post_active = {s["function"]["name"] for s in registry.get_active_schemas()}

    # All canvas tools should now be active
    for name in gh_canvas_tools:
        assert name in post_active, f"{name} NOT active after gh_canvas preload"

    # Non-canvas tool should NOT be active (unless it's Tier 0)
    if "rhino_boolean" not in AGENT_TIER_0:
        assert "rhino_boolean" not in post_active, \
            "rhino_boolean shouldn't be activated by gh_canvas preload"


@test("max_active cap prevents infinite tool accumulation")
def _():
    from rook.agent.tool_registry import ToolRegistry

    # Create a catalog with 50 tools
    catalog = {}
    for i in range(50):
        name = f"tool_{i}"
        catalog[name] = {
            "type": "function",
            "function": {"name": name, "description": f"Tool {i}", "parameters": {}},
        }

    # Set max_active very low
    registry = ToolRegistry(catalog=catalog, agent_mode=True, max_active=10)

    # Try to search and auto-load many tools
    result = registry.search("tool", top_k=50, turn=1)

    active_count = registry.get_active_count()
    assert active_count <= 10, \
        f"Active count {active_count} exceeds max_active=10"


@test("MCP_ONLY_GROUPS are blocked for non-local tools")
def _():
    from rook.agent.tool_registry import ToolRegistry
    from rook.agent.tool_groups import MCP_ONLY_GROUPS

    # Pick an MCP-only group
    mcp_group = next(iter(MCP_ONLY_GROUPS))

    from rook.agent.tool_groups import TOOL_GROUPS
    if mcp_group not in TOOL_GROUPS:
        return  # Skip if group has no tools defined

    tools_in_group = TOOL_GROUPS[mcp_group]
    catalog = {}
    for name in tools_in_group:
        catalog[name] = {
            "type": "function",
            "function": {"name": name, "description": "test", "parameters": {}},
        }

    registry = ToolRegistry(catalog=catalog, agent_mode=True)
    result = registry.request_group(mcp_group, turn=0)

    assert result["success"] is False, \
        f"MCP-only group '{mcp_group}' should be blocked, got: {result}"


@test("Phase 2 exports and constants are unchanged (regression)")
def _():
    from rook.agent.tool_dispatcher import (
        ToolDispatcher, build_local_tools, KNOWLEDGE_WRAPPED_TOOLS,
        BRIDGE_ROUTES, TRANSFORM_FUNCTIONS,
    )
    from rook.agent.tool_groups import TIER_0, AGENT_TIER_0, TOOL_GROUPS

    # Exact counts — any change should be deliberate
    assert len(KNOWLEDGE_WRAPPED_TOOLS) == 4, \
        f"KNOWLEDGE_WRAPPED_TOOLS changed: {len(KNOWLEDGE_WRAPPED_TOOLS)} != 4"
    assert AGENT_TIER_0 == TIER_0 - {"gh_execute_intent"}, \
        "AGENT_TIER_0 is not TIER_0 minus gh_execute_intent"
    assert "gh_canvas" in TOOL_GROUPS, "gh_canvas group missing"
    assert len(TOOL_GROUPS["gh_canvas"]) == 16, \
        f"gh_canvas group size changed: {len(TOOL_GROUPS['gh_canvas'])} != 16"

    tools = build_local_tools()
    assert len(tools) >= 8, f"Expected at least 8 local tools, got {len(tools)}"


# =========================================================================
# E: Dynamic system prompt (_build_worker_prompt)
# =========================================================================

print("\n=== E: Dynamic System Prompt ===")


@test("dynamic prompt = persona base + Active Tools section (in that order)")
def _():
    from rook.agent.spawn import _build_worker_prompt
    from rook.agent.tool_registry import ToolRegistry

    registry = ToolRegistry(catalog={}, agent_mode=True)
    prompt = _build_worker_prompt(registry, ["gh_canvas"])

    # Prompt must have substantial base content (from worker persona or WORKER.md)
    active_idx = prompt.index("## Active Tools")
    base_content = prompt[:active_idx]
    assert len(base_content) > 50, \
        "Dynamic prompt must have substantial base content before Active Tools"
    # Active Tools section must come AFTER base
    assert "## Active Tools" in prompt, \
        "Active Tools section must appear in prompt"


@test("tool count in dynamic section matches registry.get_active_count()")
def _():
    from rook.agent.spawn import _build_worker_prompt
    from rook.agent.tool_registry import ToolRegistry

    catalog = {
        "rhino_ping": {
            "type": "function",
            "function": {"name": "rhino_ping", "description": "Ping.", "parameters": {}},
        },
        "rhino_objects": {
            "type": "function",
            "function": {"name": "rhino_objects", "description": "List objects.", "parameters": {}},
        },
    }
    registry = ToolRegistry(catalog=catalog, agent_mode=True)
    prompt = _build_worker_prompt(registry, [])

    # Count tool lines in the Active Tools section
    active_section = prompt[prompt.index("## Active Tools"):]
    tool_lines = [l for l in active_section.split("\n") if l.startswith("- `")]

    active_count = registry.get_active_count()
    assert len(tool_lines) == active_count, \
        f"Tool listing has {len(tool_lines)} entries but registry has {active_count} active tools"


@test("multi-sentence descriptions are truncated to first sentence only")
def _():
    from rook.agent.spawn import _build_worker_prompt
    from rook.agent.tool_registry import ToolRegistry

    catalog = {
        "rhino_ping": {
            "type": "function",
            "function": {
                "name": "rhino_ping",
                "description": "Ping the Rhino bridge. Returns pong if alive. Used for health checks.",
                "parameters": {},
            },
        },
    }
    registry = ToolRegistry(catalog=catalog, agent_mode=True)
    prompt = _build_worker_prompt(registry, [])

    active_section = prompt[prompt.index("## Active Tools"):]
    # Should have first sentence only, not the full description
    assert "Ping the Rhino bridge." in active_section
    assert "Returns pong if alive" not in active_section, \
        "Second sentence should be truncated"
    assert "Used for health checks" not in active_section, \
        "Third sentence should be truncated"


@test("empty description doesn't produce empty or broken tool line")
def _():
    from rook.agent.spawn import _build_worker_prompt
    from rook.agent.tool_registry import ToolRegistry

    catalog = {
        "rhino_ping": {
            "type": "function",
            "function": {"name": "rhino_ping", "description": "", "parameters": {}},
        },
    }
    registry = ToolRegistry(catalog=catalog, agent_mode=True)
    prompt = _build_worker_prompt(registry, [])

    active_section = prompt[prompt.index("## Active Tools"):]
    # Tool should still appear (with empty description)
    assert "`rhino_ping`" in active_section, "Tool with empty desc should still appear"
    # Should not have a dangling " -- " with nothing after
    lines = [l for l in active_section.split("\n") if "rhino_ping" in l]
    assert len(lines) == 1
    # Verify no malformed line
    assert lines[0].strip().startswith("- `rhino_ping`")


@test("preloaded group names appear in section header, sorted")
def _():
    from rook.agent.spawn import _build_worker_prompt
    from rook.agent.tool_registry import ToolRegistry

    registry = ToolRegistry(catalog={}, agent_mode=True)
    prompt = _build_worker_prompt(registry, ["rhino_geometry", "gh_canvas", "layers"])

    # Extract the header line
    header_match = re.search(r"## Active Tools \(preloaded: (.+?)\)", prompt)
    assert header_match, "Active Tools header not found"
    header_content = header_match.group(1)

    # Should be sorted
    assert "`gh_canvas`" in header_content
    assert "`layers`" in header_content
    assert "`rhino_geometry`" in header_content
    # Verify sort order
    gh_pos = header_content.index("`gh_canvas`")
    layers_pos = header_content.index("`layers`")
    rhino_pos = header_content.index("`rhino_geometry`")
    assert gh_pos < layers_pos < rhino_pos, \
        f"Groups not sorted: gh@{gh_pos}, layers@{layers_pos}, rhino@{rhino_pos}"


@test("tools are listed in sorted order for deterministic prompts")
def _():
    from rook.agent.spawn import _build_worker_prompt
    from rook.agent.tool_registry import ToolRegistry

    catalog = {
        "zebra_tool": {
            "type": "function",
            "function": {"name": "zebra_tool", "description": "Z.", "parameters": {}},
        },
        "alpha_tool": {
            "type": "function",
            "function": {"name": "alpha_tool", "description": "A.", "parameters": {}},
        },
        "middle_tool": {
            "type": "function",
            "function": {"name": "middle_tool", "description": "M.", "parameters": {}},
        },
    }
    registry = ToolRegistry(catalog=catalog, agent_mode=True)
    # Force all into active set
    for name in catalog:
        registry._active.add(name)

    prompt = _build_worker_prompt(registry, [])
    active_section = prompt[prompt.index("## Active Tools"):]
    tool_lines = [l for l in active_section.split("\n") if l.startswith("- `")]
    tool_names = [l.split("`")[1] for l in tool_lines]

    assert tool_names == sorted(tool_names), \
        f"Tool listing not sorted: {tool_names}"


@test("persona + WORKER.md missing: falls back to empty base, still has Active Tools")
def _():
    """If persona files AND WORKER.md are deleted, dynamic prompt still works."""
    from rook.agent.spawn import _build_worker_prompt
    from rook.agent.tool_registry import ToolRegistry
    from unittest.mock import patch as mock_patch
    from pathlib import Path

    registry = ToolRegistry(catalog={}, agent_mode=True)

    # Patch persona loader to return empty + WORKER.md to not exist
    original_exists = Path.exists
    def fake_exists(self):
        if "WORKER.md" in str(self):
            return False
        return original_exists(self)

    with mock_patch.object(Path, "exists", fake_exists):
        # Use a nonexistent type → empty persona, WORKER.md patched away
        prompt = _build_worker_prompt(registry, ["gh_canvas"], "nonexistent_xyz")

    # Should still have Active Tools section even without base
    assert "## Active Tools" in prompt
    assert "`request_tools`" in prompt


# =========================================================================
# Summary
# =========================================================================

print(f"\n{'='*50}")
print(f"Phase 3 Tests: {passed} passed, {failed} failed")
print(f"{'='*50}")

if failed > 0:
    sys.exit(1)
