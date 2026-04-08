"""Tests for block definition geometry editing capabilities.

Covers:
  1. /block/objects-detailed geometry flag (Phase 1 — read path)
  2. /block/replace-object-geometry dispatch routing (Phase 2 — write path)
  3. /block/transform-object dispatch routing (Phase 2 — write path)
  4. BRIDGE_ROUTES coverage for new tools
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, patch

from rook.agent.tool_dispatcher import (
    ToolDispatcher,
    BRIDGE_ROUTES,
)


# =============================================================================
# BRIDGE_ROUTES coverage
# =============================================================================

class TestBlockToolRouting:
    """New block tools must be in BRIDGE_ROUTES with correct endpoints."""

    def test_replace_object_geometry_in_bridge_routes(self):
        assert "rhino_block_replace_object_geometry" in BRIDGE_ROUTES
        endpoint, method = BRIDGE_ROUTES["rhino_block_replace_object_geometry"]
        assert endpoint == "/block/replace-object-geometry"
        assert method == "POST"

    def test_transform_object_in_bridge_routes(self):
        assert "rhino_block_transform_object" in BRIDGE_ROUTES
        endpoint, method = BRIDGE_ROUTES["rhino_block_transform_object"]
        assert endpoint == "/block/transform-object"
        assert method == "POST"

    def test_objects_detailed_in_bridge_routes(self):
        """objects-detailed should remain in BRIDGE_ROUTES (existing)."""
        assert "rhino_block_objects_detailed" in BRIDGE_ROUTES

    def test_rebase_in_bridge_routes(self):
        assert "rhino_block_rebase" in BRIDGE_ROUTES
        endpoint, method = BRIDGE_ROUTES["rhino_block_rebase"]
        assert endpoint == "/block/rebase"
        assert method == "POST"


# =============================================================================
# Dispatcher: /block/replace-object-geometry
# =============================================================================

class TestReplaceObjectGeometryDispatch:
    """Dispatch routing for the per-object geometry replacement tool."""

    @pytest.fixture
    def dispatcher(self):
        return ToolDispatcher(port=9950)

    @pytest.mark.asyncio
    async def test_dispatches_to_correct_endpoint(self, dispatcher):
        """Should call /block/replace-object-geometry via POST."""
        mock_result = {
            "success": True,
            "data": {
                "blockName": "TestBlock",
                "objectCount": 3,
                "replacedIndex": 1,
                "newGeometryType": "Brep",
                "sourceDeleted": True,
            },
        }

        with patch("rook.agent.tool_dispatcher.call_rhino", new_callable=AsyncMock) as mock_rhino:
            mock_rhino.return_value = mock_result
            result = await dispatcher.dispatch(
                "rhino_block_replace_object_geometry",
                {"name": "TestBlock", "index": 1, "sourceId": "abc-123"},
            )

        mock_rhino.assert_called_once()
        call_args = mock_rhino.call_args
        assert call_args[0][0] == "/block/replace-object-geometry"
        assert call_args[0][1] == "POST"
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_failure_propagated(self, dispatcher):
        """Rhino failure should propagate cleanly."""
        mock_result = {"success": False, "data": "Block not found"}

        with patch("rook.agent.tool_dispatcher.call_rhino", new_callable=AsyncMock) as mock_rhino:
            mock_rhino.return_value = mock_result
            result = await dispatcher.dispatch(
                "rhino_block_replace_object_geometry",
                {"name": "NoSuchBlock", "index": 0, "sourceId": "xyz"},
            )

        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_no_verification_annotation(self, dispatcher):
        """Block write tools are NOT in CREATION_TOOLS or MODAL_RISK_TOOLS,
        so they should not get verification annotation."""
        mock_result = {
            "success": True,
            "data": {"blockName": "B", "objectCount": 1, "replacedIndex": 0},
        }

        with patch("rook.agent.tool_dispatcher.call_rhino", new_callable=AsyncMock) as mock_rhino:
            mock_rhino.return_value = mock_result
            result = await dispatcher.dispatch(
                "rhino_block_replace_object_geometry",
                {"name": "B", "index": 0, "sourceId": "id"},
            )

        assert "verified" not in result
        assert "verification_note" not in result


# =============================================================================
# Dispatcher: /block/transform-object
# =============================================================================

class TestTransformObjectDispatch:
    """Dispatch routing for the per-object transform tool."""

    @pytest.fixture
    def dispatcher(self):
        return ToolDispatcher(port=9950)

    @pytest.mark.asyncio
    async def test_dispatches_to_correct_endpoint(self, dispatcher):
        """Should call /block/transform-object via POST."""
        mock_result = {
            "success": True,
            "data": {
                "blockName": "TestBlock",
                "objectCount": 3,
                "transformedIndices": [0, 2],
                "transformType": "move",
            },
        }

        with patch("rook.agent.tool_dispatcher.call_rhino", new_callable=AsyncMock) as mock_rhino:
            mock_rhino.return_value = mock_result
            result = await dispatcher.dispatch(
                "rhino_block_transform_object",
                {
                    "name": "TestBlock",
                    "indices": [0, 2],
                    "transform": {"type": "move", "x": 5, "y": 0, "z": 0},
                },
            )

        mock_rhino.assert_called_once()
        call_args = mock_rhino.call_args
        assert call_args[0][0] == "/block/transform-object"
        assert call_args[0][1] == "POST"
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_transform_failure_propagated(self, dispatcher):
        """Transform rejection should propagate as success=False."""
        mock_result = {
            "success": False,
            "data": "Transform failed for object(s) at index 0. No changes applied.",
        }

        with patch("rook.agent.tool_dispatcher.call_rhino", new_callable=AsyncMock) as mock_rhino:
            mock_rhino.return_value = mock_result
            result = await dispatcher.dispatch(
                "rhino_block_transform_object",
                {
                    "name": "TestBlock",
                    "indices": [0],
                    "transform": {"type": "scale", "factor": 0, "center": [0, 0, 0]},
                },
            )

        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_no_verification_annotation(self, dispatcher):
        """Block transform is not in CREATION_TOOLS or MODAL_RISK_TOOLS."""
        mock_result = {
            "success": True,
            "data": {"blockName": "B", "objectCount": 1, "transformedIndices": [0]},
        }

        with patch("rook.agent.tool_dispatcher.call_rhino", new_callable=AsyncMock) as mock_rhino:
            mock_rhino.return_value = mock_result
            result = await dispatcher.dispatch(
                "rhino_block_transform_object",
                {"name": "B", "indices": [0], "transform": {"type": "move", "x": 1, "y": 0, "z": 0}},
            )

        assert "verified" not in result


# =============================================================================
# Dispatcher: /block/rebase
# =============================================================================

class TestBlockRebaseDispatch:
    """Dispatch routing for block definition rebasing."""

    @pytest.fixture
    def dispatcher(self):
        return ToolDispatcher(port=9950)

    @pytest.mark.asyncio
    async def test_dispatches_to_correct_endpoint(self, dispatcher):
        mock_result = {
            "success": True,
            "data": {
                "blockName": "PARTITION WALL 01",
                "dryRun": True,
                "executed": False,
                "definitionTranslation": [0, 0, -12000],
                "instanceCompensationTranslation": [0, 0, 12000],
            },
        }

        with patch("rook.agent.tool_dispatcher.call_rhino", new_callable=AsyncMock) as mock_rhino:
            mock_rhino.return_value = mock_result
            result = await dispatcher.dispatch(
                "rhino_block_rebase",
                {"name": "PARTITION WALL 01", "anchor": "bbox_min", "axes": ["z"], "dryRun": True},
            )

        mock_rhino.assert_called_once()
        call_args = mock_rhino.call_args
        assert call_args[0][0] == "/block/rebase"
        assert call_args[0][1] == "POST"
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_rebase_failure_propagated(self, dispatcher):
        mock_result = {"success": False, "data": "Requested rebase is a no-op for the selected axes"}

        with patch("rook.agent.tool_dispatcher.call_rhino", new_callable=AsyncMock) as mock_rhino:
            mock_rhino.return_value = mock_result
            result = await dispatcher.dispatch(
                "rhino_block_rebase",
                {"name": "PARTITION WALL 01", "anchor": "bbox_min", "axes": ["z"], "dryRun": False},
            )

        assert result["success"] is False


# =============================================================================
# Dispatcher: /block/rebase-recursive
# =============================================================================

class TestBlockRebaseRecursiveRouting:
    """Route registration and dispatch for recursive block rebase."""

    def test_rebase_recursive_in_bridge_routes(self):
        assert "rhino_block_rebase_recursive" in BRIDGE_ROUTES
        endpoint, method = BRIDGE_ROUTES["rhino_block_rebase_recursive"]
        assert endpoint == "/block/rebase-recursive"
        assert method == "POST"

    @pytest.fixture
    def dispatcher(self):
        return ToolDispatcher(port=9950)

    @pytest.mark.asyncio
    async def test_dispatches_to_correct_endpoint(self, dispatcher):
        mock_result = {
            "success": True,
            "data": {
                "dryRun": True,
                "executed": False,
                "planHash": "abc123",
                "leaf": {"name": "InstanceDef 413", "objectCount": 1},
                "parentDefinitions": [],
                "summary": {
                    "parentDefinitionsRewritten": 0,
                    "totalNestedRefsCompensated": 0,
                    "directInstancesCompensated": 0,
                },
            },
        }

        with patch("rook.agent.tool_dispatcher.call_rhino", new_callable=AsyncMock) as mock_rhino:
            mock_rhino.return_value = mock_result
            result = await dispatcher.dispatch(
                "rhino_block_rebase_recursive",
                {"name": "InstanceDef 413", "anchor": "bbox_min", "axes": ["z"], "dryRun": True},
            )

        mock_rhino.assert_called_once()
        call_args = mock_rhino.call_args
        assert call_args[0][0] == "/block/rebase-recursive"
        assert call_args[0][1] == "POST"
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_no_parent_rejection_propagated(self, dispatcher):
        """A leaf with no parents should fail with guidance to use flat rebase."""
        mock_result = {
            "success": False,
            "data": "has no ancestor definitions; use rhino_block_rebase instead",
        }

        with patch("rook.agent.tool_dispatcher.call_rhino", new_callable=AsyncMock) as mock_rhino:
            mock_rhino.return_value = mock_result
            result = await dispatcher.dispatch(
                "rhino_block_rebase_recursive",
                {"name": "TopLevelBlock", "dryRun": True},
            )

        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_missing_plan_hash_rejection(self, dispatcher):
        """Execute without expectedPlanHash should fail."""
        mock_result = {
            "success": False,
            "data": "expectedPlanHash required for execute; run dry-run first",
        }

        with patch("rook.agent.tool_dispatcher.call_rhino", new_callable=AsyncMock) as mock_rhino:
            mock_rhino.return_value = mock_result
            result = await dispatcher.dispatch(
                "rhino_block_rebase_recursive",
                {"name": "Leaf", "dryRun": False},
            )

        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_wrong_plan_hash_rejection(self, dispatcher):
        """Execute with wrong expectedPlanHash should fail."""
        mock_result = {
            "success": False,
            "data": "Plan changed since dry-run; re-run dry-run",
        }

        with patch("rook.agent.tool_dispatcher.call_rhino", new_callable=AsyncMock) as mock_rhino:
            mock_rhino.return_value = mock_result
            result = await dispatcher.dispatch(
                "rhino_block_rebase_recursive",
                {"name": "Leaf", "dryRun": False, "expectedPlanHash": "wrong"},
            )

        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_execute_with_valid_plan_hash(self, dispatcher):
        """Execute with matching expectedPlanHash should succeed."""
        mock_result = {
            "success": True,
            "data": {
                "dryRun": False,
                "executed": True,
                "planHash": "4c9b7f45f41f5e9c",
                "leaf": {"name": "InstanceDef 415", "objectCount": 26},
                "parentDefinitions": [
                    {
                        "definitionName": "RAILING WEST",
                        "referencedChildName": "InstanceDef 415",
                        "nestedRefsToLeaf": 1,
                    }
                ],
                "summary": {
                    "parentDefinitionsRewritten": 1,
                    "totalNestedRefsCompensated": 1,
                    "directInstancesCompensated": 0,
                },
            },
        }

        with patch("rook.agent.tool_dispatcher.call_rhino", new_callable=AsyncMock) as mock_rhino:
            mock_rhino.return_value = mock_result
            result = await dispatcher.dispatch(
                "rhino_block_rebase_recursive",
                {
                    "name": "InstanceDef 415",
                    "anchor": "bbox_min",
                    "axes": ["x", "y", "z"],
                    "dryRun": False,
                    "expectedPlanHash": "4c9b7f45f41f5e9c",
                },
            )

        assert result["success"] is True
        assert result["data"]["executed"] is True
        assert result["data"]["summary"]["parentDefinitionsRewritten"] == 1


# =============================================================================
# Dispatcher: /block/objects-detailed geometry flag passthrough
# =============================================================================

class TestObjectsDetailedGeometryFlag:
    """The geometry flag should be forwarded to the HTTP endpoint."""

    @pytest.fixture
    def dispatcher(self):
        return ToolDispatcher(port=9950)

    @pytest.mark.asyncio
    async def test_without_geometry_flag(self, dispatcher):
        """Default call should not include geometry field."""
        mock_result = {
            "success": True,
            "data": {
                "blockName": "B",
                "objectCount": 1,
                "objects": [{"index": 0, "type": "Brep"}],
            },
        }

        with patch("rook.agent.tool_dispatcher.call_rhino", new_callable=AsyncMock) as mock_rhino:
            mock_rhino.return_value = mock_result
            result = await dispatcher.dispatch(
                "rhino_block_objects_detailed", {"name": "B"}
            )

        call_args = mock_rhino.call_args
        payload = call_args[0][2]  # third positional arg is the data dict
        # Should not have geometry key, or geometry should be absent/falsy
        assert payload.get("geometry") is not True

    @pytest.mark.asyncio
    async def test_with_geometry_flag(self, dispatcher):
        """geometry=true should forward to Rhino."""
        mock_result = {
            "success": True,
            "data": {
                "blockName": "B",
                "objectCount": 1,
                "objects": [
                    {
                        "index": 0,
                        "type": "Brep",
                        "geometryType": "Brep",
                        "geometry": {"type": "Brep", "faceCount": 6},
                    }
                ],
            },
        }

        with patch("rook.agent.tool_dispatcher.call_rhino", new_callable=AsyncMock) as mock_rhino:
            mock_rhino.return_value = mock_result
            result = await dispatcher.dispatch(
                "rhino_block_objects_detailed", {"name": "B", "geometry": True}
            )

        call_args = mock_rhino.call_args
        payload = call_args[0][2]
        assert payload.get("geometry") is True
        assert result["success"] is True
