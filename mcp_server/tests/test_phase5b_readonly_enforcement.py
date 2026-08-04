"""
Phase 5b: Registry-Level Readonly Enforcement
===============================================

Tests for:
A. READONLY_TIER_0 / READONLY_ALLOWED_GROUPS constants
B. ToolRegistry enforcement for readonly agents
C. gh_canvas_readonly / layers_readonly / viewport_readonly group definitions
D. spawn.py run_task integration with readonly personas
E. Backward compatibility (worker/specialist unrestricted)
F. Auto-load trigger rejection and preload swap
"""

import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# --- Path setup ---
REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from rook.agent.tool_groups import (
    TIER_0,
    AGENT_TIER_0,
    TOOL_GROUPS,
    READONLY_TIER_0,
    READONLY_ALLOWED_GROUPS,
)
from rook.agent.tool_registry import ToolRegistry
from rook.agent.personas import load_display_config


# =============================================================================
# A: Constants correctness
# =============================================================================

class TestReadonlyConstants(unittest.TestCase):
    """READONLY_TIER_0 and READONLY_ALLOWED_GROUPS are well-formed."""

    def test_readonly_tier0_excludes_execute_intents(self):
        self.assertNotIn("rhino_execute_intent", READONLY_TIER_0)
        self.assertNotIn("gh_execute_intent", READONLY_TIER_0)

    def test_readonly_tier0_has_inspection_tools(self):
        for tool in ("rhino_ping", "rhino_objects", "gh_snapshot",
                      "gh_errors", "knowledge_query"):
            self.assertIn(tool, READONLY_TIER_0, f"Missing: {tool}")

    def test_readonly_tier0_has_meta_tools(self):
        self.assertIn("request_tools", READONLY_TIER_0)
        self.assertIn("search_tools", READONLY_TIER_0)

    def test_readonly_tier0_only_safe_tools(self):
        """READONLY_TIER_0 should only contain known read-safe tools."""
        known_safe = {
            "rhino_ping", "rhino_objects", "rhino_geometry",
            "gh_snapshot", "gh_errors",
            "knowledge_query", "rhino_knowledge_query", "gh_knowledge_query",
            "scene_graph", "scene_context", "scene_stats",
            "request_tools", "search_tools",
        }
        extra = READONLY_TIER_0 - known_safe
        self.assertFalse(extra, f"Unexpected tools in READONLY_TIER_0: {extra}")

    def test_readonly_allowed_groups_no_write_groups(self):
        """Full write groups must not appear in READONLY_ALLOWED_GROUPS."""
        write_groups = {
            "rhino_geometry", "rhino_transform", "rhino_curves",
            "rhino_surfaces", "rhino_mesh", "rhino_subd", "rhino_blocks",
            "materials", "game_export", "gumball", "annotation",
            "import_export", "rhino_groups", "gh_canvas",
            "gh_patterns", "gh_document", "gh_references",
            "rhino_commands",
            # Full versions of groups that have readonly variants
            "layers", "viewport",
        }
        overlap = READONLY_ALLOWED_GROUPS & write_groups
        self.assertFalse(overlap, f"Write groups in READONLY: {overlap}")

    def test_readonly_uses_readonly_group_variants(self):
        """READONLY_ALLOWED_GROUPS uses _readonly variants, not full groups."""
        self.assertIn("layers_readonly", READONLY_ALLOWED_GROUPS)
        self.assertNotIn("layers", READONLY_ALLOWED_GROUPS)
        self.assertIn("viewport_readonly", READONLY_ALLOWED_GROUPS)
        self.assertNotIn("viewport", READONLY_ALLOWED_GROUPS)

    def test_gh_canvas_readonly_in_tool_groups(self):
        self.assertIn("gh_canvas_readonly", TOOL_GROUPS)

    def test_gh_canvas_readonly_in_allowed_groups(self):
        self.assertIn("gh_canvas_readonly", READONLY_ALLOWED_GROUPS)


# =============================================================================
# B: ToolRegistry enforcement
# =============================================================================

def _make_catalog(*tool_names):
    """Build a minimal catalog from tool names."""
    return {
        name: {
            "type": "function",
            "function": {"name": name, "description": f"{name} tool", "parameters": {}},
        }
        for name in tool_names
    }


class TestRegistryReadonlyEnforcement(unittest.TestCase):
    """ToolRegistry blocks write tools when configured with readonly constraints."""

    def test_blocks_gh_canvas_group(self):
        catalog = _make_catalog("gh_component", "gh_connect", "gh_set_value")
        registry = ToolRegistry(
            catalog=catalog,
            tier0=READONLY_TIER_0,
            allowed_groups=READONLY_ALLOWED_GROUPS,
        )
        result = registry.request_group("gh_canvas", turn=0)
        self.assertFalse(result["success"])

    def test_blocks_full_layers_group(self):
        """Full 'layers' group (with create/delete) is blocked."""
        catalog = _make_catalog("rhino_layers", "rhino_layer_create", "rhino_layer_delete")
        registry = ToolRegistry(
            catalog=catalog,
            tier0=READONLY_TIER_0,
            allowed_groups=READONLY_ALLOWED_GROUPS,
        )
        result = registry.request_group("layers", turn=0)
        self.assertFalse(result["success"])

    def test_blocks_full_viewport_group(self):
        """Full 'viewport' group (with document_ops) is blocked."""
        catalog = _make_catalog("rhino_viewport", "rhino_document", "rhino_document_ops")
        registry = ToolRegistry(
            catalog=catalog,
            tier0=READONLY_TIER_0,
            allowed_groups=READONLY_ALLOWED_GROUPS,
        )
        result = registry.request_group("viewport", turn=0)
        self.assertFalse(result["success"])

    def test_allows_measurement_group(self):
        catalog = _make_catalog("rhino_measure_distance", "rhino_measure_length")
        registry = ToolRegistry(
            catalog=catalog,
            tier0=READONLY_TIER_0,
            allowed_groups=READONLY_ALLOWED_GROUPS,
        )
        result = registry.request_group("rhino_measurement", turn=0)
        self.assertTrue(result["success"])

    def test_allows_gh_canvas_readonly(self):
        catalog = _make_catalog("gh_get_value", "gh_inspect_output", "gh_connections")
        registry = ToolRegistry(
            catalog=catalog,
            tier0=READONLY_TIER_0,
            allowed_groups=READONLY_ALLOWED_GROUPS,
        )
        result = registry.request_group("gh_canvas_readonly", turn=0)
        self.assertTrue(result["success"])

    def test_allows_layers_readonly(self):
        catalog = _make_catalog("rhino_layers", "rhino_layer_visibility")
        registry = ToolRegistry(
            catalog=catalog,
            tier0=READONLY_TIER_0,
            allowed_groups=READONLY_ALLOWED_GROUPS,
        )
        result = registry.request_group("layers_readonly", turn=0)
        self.assertTrue(result["success"])

    def test_allows_viewport_readonly(self):
        catalog = _make_catalog("rhino_viewport", "rhino_document")
        registry = ToolRegistry(
            catalog=catalog,
            tier0=READONLY_TIER_0,
            allowed_groups=READONLY_ALLOWED_GROUPS,
        )
        result = registry.request_group("viewport_readonly", turn=0)
        self.assertTrue(result["success"])

    def test_search_filters_write_tools(self):
        """search() should not load tools from disallowed groups."""
        catalog = _make_catalog(
            "rhino_ping", "rhino_create", "rhino_boolean",
            "rhino_measure_distance",
        )
        registry = ToolRegistry(
            catalog=catalog,
            tier0=READONLY_TIER_0,
            allowed_groups=READONLY_ALLOWED_GROUPS,
        )
        result = registry.search("rhino", turn=1)
        loaded = set(result.get("loaded", []))
        # Write tools from rhino_geometry (not allowed) should be filtered
        self.assertNotIn("rhino_create", loaded)
        self.assertNotIn("rhino_boolean", loaded)

    def test_autoload_trigger_blocked_for_readonly(self):
        """Auto-loaded write groups are rejected by allowed_groups."""
        catalog = _make_catalog("rhino_create", "rhino_transform")
        registry = ToolRegistry(
            catalog=catalog,
            tier0=READONLY_TIER_0,
            allowed_groups=READONLY_ALLOWED_GROUPS,
        )
        # Simulate what base_agent._post_turn_adapt does via triggers
        result = registry.request_group("rhino_geometry", turn=1)
        self.assertFalse(result["success"])
        result = registry.request_group("rhino_transform", turn=1)
        self.assertFalse(result["success"])


# =============================================================================
# C: Readonly group definitions
# =============================================================================

class TestGhCanvasReadonlyGroup(unittest.TestCase):
    """gh_canvas_readonly contains only read-safe tools."""

    def test_no_write_tools(self):
        write_tools = {
            "gh_component", "gh_connect", "gh_disconnect",
            "gh_set_value", "gh_delete", "gh_set_script",
            "gh_move", "gh_group", "gh_canvas_cleanup", "gh_clear",
        }
        readonly_tools = set(TOOL_GROUPS["gh_canvas_readonly"])
        overlap = readonly_tools & write_tools
        self.assertFalse(overlap, f"Write tools in gh_canvas_readonly: {overlap}")

    def test_has_inspection_tools(self):
        readonly_tools = set(TOOL_GROUPS["gh_canvas_readonly"])
        for tool in ("gh_snapshot", "gh_inspect_output"):
            self.assertIn(tool, readonly_tools, f"Missing: {tool}")
        # gh_canvas_image intentionally excluded: MCP/server-side only (returns a
        # PNG, no agent dispatch path). See #303.
        self.assertNotIn("gh_canvas_image", readonly_tools)


class TestLayersReadonlyGroup(unittest.TestCase):
    """layers_readonly excludes write tools."""

    def test_exists(self):
        self.assertIn("layers_readonly", TOOL_GROUPS)

    def test_no_write_tools(self):
        write_tools = {"rhino_layer_create", "rhino_layer_delete", "rhino_layer_current"}
        readonly_tools = set(TOOL_GROUPS["layers_readonly"])
        overlap = readonly_tools & write_tools
        self.assertFalse(overlap, f"Write tools in layers_readonly: {overlap}")

    def test_has_query_tools(self):
        readonly_tools = set(TOOL_GROUPS["layers_readonly"])
        self.assertIn("rhino_layers", readonly_tools)
        self.assertIn("rhino_layer_visibility", readonly_tools)


class TestViewportReadonlyGroup(unittest.TestCase):
    """viewport_readonly excludes document_ops."""

    def test_exists(self):
        self.assertIn("viewport_readonly", TOOL_GROUPS)

    def test_no_document_ops(self):
        readonly_tools = set(TOOL_GROUPS["viewport_readonly"])
        self.assertNotIn("rhino_document_ops", readonly_tools)

    def test_has_read_tools(self):
        readonly_tools = set(TOOL_GROUPS["viewport_readonly"])
        self.assertIn("rhino_viewport", readonly_tools)
        self.assertIn("rhino_document", readonly_tools)


# =============================================================================
# D: spawn.py integration
# =============================================================================

class TestSpawnReadonlyIntegration(unittest.TestCase):
    """run_task creates restricted registry for readonly personas."""

    def test_profile_failure_uses_sonnet_5_worker_default(self):
        from rook.agent.spawn import run_task

        with patch(
            "rook.agent.model_profiles.get_models",
            side_effect=RuntimeError("profile unavailable"),
        ):
            with patch("rook.agent.base_agent.RookAgent") as mock_agent:
                instance = MagicMock()
                instance.prompt = AsyncMock()
                instance.wait_for_idle = AsyncMock()
                instance.messages = []
                instance._total_input_tokens = 0
                instance._total_output_tokens = 0
                instance._total_cost = 0.0
                instance._turn_count = 0
                instance.config = MagicMock()
                instance.config.model = "anthropic/claude-sonnet-5"
                instance.config.guardian_enabled = False
                mock_agent.return_value = instance

                asyncio.run(
                    run_task(
                        "test task",
                        catalog={},
                        guardian_enabled=False,
                        tool_executor=AsyncMock(),
                    )
                )

        assert mock_agent.call_args.kwargs["config"].model == (
            "anthropic/claude-sonnet-5"
        )

    def test_swarm_profile_failure_uses_sonnet_5_worker_default(self):
        from rook.agent.spawn import SpawnResult, run_swarm

        with patch(
            "rook.agent.model_profiles.get_models",
            side_effect=RuntimeError("profile unavailable"),
        ):
            with patch(
                "rook.agent.spawn.run_task",
                new_callable=AsyncMock,
                return_value=SpawnResult(
                    task_id="worker-1",
                    status="success",
                    task="test task",
                ),
            ) as mock_run_task:
                asyncio.run(
                    run_swarm(
                        [{"task": "test task", "task_id": "worker-1"}],
                        guardian_enabled=False,
                        catalog={},
                        tool_executor=AsyncMock(),
                    )
                )

        assert mock_run_task.call_args.kwargs["model"] == (
            "anthropic/claude-sonnet-5"
        )

    def _run_with_agent_type(self, agent_type):
        """Run run_task with given agent_type, capture registry kwargs."""
        from rook.agent.spawn import run_task

        captured = {}
        original_init = ToolRegistry.__init__

        def spy_init(self, *args, **kwargs):
            captured["allowed_groups"] = kwargs.get("allowed_groups")
            captured["tier0"] = kwargs.get("tier0")
            captured["agent_mode"] = kwargs.get("agent_mode", False)
            original_init(self, *args, **kwargs)

        with patch.object(ToolRegistry, "__init__", spy_init):
            with patch("rook.agent.base_agent.RookAgent") as MockAgent:
                inst = MagicMock()
                inst.prompt = AsyncMock()
                inst.wait_for_idle = AsyncMock()
                inst.messages = []
                inst._total_input_tokens = 0
                inst._total_output_tokens = 0
                inst._total_cost = 0.0
                inst._turn_count = 0
                inst.config = MagicMock()
                inst.config.model = "test"
                inst.config.guardian_enabled = False
                MockAgent.return_value = inst

                catalog = _make_catalog("rhino_ping")
                asyncio.run(
                    run_task(
                        "test task",
                        agent_type=agent_type,
                        catalog=catalog,
                        guardian_enabled=False,
                    )
                )
        return captured

    def test_explorer_gets_readonly_registry(self):
        captured = self._run_with_agent_type("explorer")
        self.assertEqual(captured["allowed_groups"], READONLY_ALLOWED_GROUPS)
        self.assertEqual(captured["tier0"], READONLY_TIER_0)

    def test_worker_gets_unrestricted_registry(self):
        captured = self._run_with_agent_type("worker")
        self.assertIsNone(captured["allowed_groups"])
        self.assertTrue(captured["agent_mode"])


# =============================================================================
# E: Backward compatibility
# =============================================================================

class TestBackwardCompatibility(unittest.TestCase):
    """Existing behavior preserved for full-access personas."""

    def test_unknown_persona_defaults_to_full(self):
        config = load_display_config("nonexistent_agent_xyz")
        self.assertEqual(config["tool_access"], "full")

    def test_all_write_personas_have_full_access(self):
        for name in ("worker", "specialist", "scripter"):
            config = load_display_config(name)
            self.assertEqual(config["tool_access"], "full",
                             f"{name} should have full access")

    def test_all_readonly_personas_have_readonly_access(self):
        for name in ("explorer", "planner", "guardian"):
            config = load_display_config(name)
            self.assertEqual(config["tool_access"], "readonly",
                             f"{name} should have readonly access")


# =============================================================================
# F: Preload swap verification
# =============================================================================

class TestPreloadSwap(unittest.TestCase):
    """Readonly agents get gh_canvas_readonly instead of gh_canvas."""

    def test_readonly_preload_swaps_gh_canvas(self):
        """Explorer should preload gh_canvas_readonly, not gh_canvas."""
        from rook.agent.spawn import run_task

        preloaded = []
        original_request = ToolRegistry.request_group

        def spy_request(self, group_name, **kwargs):
            preloaded.append(group_name)
            return original_request(self, group_name, **kwargs)

        with patch.object(ToolRegistry, "request_group", spy_request):
            with patch("rook.agent.base_agent.RookAgent") as MockAgent:
                inst = MagicMock()
                inst.prompt = AsyncMock()
                inst.wait_for_idle = AsyncMock()
                inst.messages = []
                inst._total_input_tokens = 0
                inst._total_output_tokens = 0
                inst._total_cost = 0.0
                inst._turn_count = 0
                inst.config = MagicMock()
                inst.config.model = "test"
                inst.config.guardian_enabled = False
                MockAgent.return_value = inst

                catalog = _make_catalog("rhino_ping", "gh_get_value")
                asyncio.run(
                    run_task(
                        "inspect canvas",
                        agent_type="explorer",
                        catalog=catalog,
                        guardian_enabled=False,
                    )
                )

        self.assertIn("gh_canvas_readonly", preloaded)
        self.assertNotIn("gh_canvas", preloaded)

    def test_worker_preload_keeps_gh_canvas(self):
        """Worker should preload gh_canvas, not gh_canvas_readonly."""
        from rook.agent.spawn import run_task

        preloaded = []
        original_request = ToolRegistry.request_group

        def spy_request(self, group_name, **kwargs):
            preloaded.append(group_name)
            return original_request(self, group_name, **kwargs)

        with patch.object(ToolRegistry, "request_group", spy_request):
            with patch("rook.agent.base_agent.RookAgent") as MockAgent:
                inst = MagicMock()
                inst.prompt = AsyncMock()
                inst.wait_for_idle = AsyncMock()
                inst.messages = []
                inst._total_input_tokens = 0
                inst._total_output_tokens = 0
                inst._total_cost = 0.0
                inst._turn_count = 0
                inst.config = MagicMock()
                inst.config.model = "test"
                inst.config.guardian_enabled = False
                MockAgent.return_value = inst

                catalog = _make_catalog("rhino_ping", "gh_component")
                asyncio.run(
                    run_task(
                        "create box",
                        agent_type="worker",
                        catalog=catalog,
                        guardian_enabled=False,
                    )
                )

        self.assertIn("gh_canvas", preloaded)
        self.assertNotIn("gh_canvas_readonly", preloaded)


if __name__ == "__main__":
    unittest.main(verbosity=2)
