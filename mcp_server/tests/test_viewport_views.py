"""Tests for viewport capture and named view MCP tools.

Covers:
  1. BRIDGE_ROUTES entries for rhino_views, rhino_views_restore, rhino_views_save
  2. Dispatch routing for all three named view tools
  3. rhino_viewport parameter passthrough (new capture settings)
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

class TestViewToolRouting:
    """Named view tools must be in BRIDGE_ROUTES with correct endpoints."""

    def test_views_in_bridge_routes(self):
        assert "rhino_views" in BRIDGE_ROUTES
        endpoint, method = BRIDGE_ROUTES["rhino_views"]
        assert endpoint == "/views"
        assert method == "GET"

    def test_views_restore_in_bridge_routes(self):
        assert "rhino_views_restore" in BRIDGE_ROUTES
        endpoint, method = BRIDGE_ROUTES["rhino_views_restore"]
        assert endpoint == "/views/restore"
        assert method == "POST"

    def test_views_save_in_bridge_routes(self):
        assert "rhino_views_save" in BRIDGE_ROUTES
        endpoint, method = BRIDGE_ROUTES["rhino_views_save"]
        assert endpoint == "/views/save"
        assert method == "POST"

    def test_viewport_still_in_bridge_routes(self):
        """Existing viewport tool should be POST (changed from GET for param support)."""
        assert "rhino_viewport" in BRIDGE_ROUTES
        endpoint, method = BRIDGE_ROUTES["rhino_viewport"]
        assert endpoint == "/viewport"
        assert method == "POST"


# =============================================================================
# Dispatcher: rhino_views (GET /views)
# =============================================================================

class TestViewsDispatch:
    """Dispatch routing for named view listing."""

    @pytest.fixture
    def dispatcher(self):
        return ToolDispatcher(port=9950)

    @pytest.mark.asyncio
    async def test_dispatches_to_correct_endpoint(self, dispatcher):
        mock_result = {
            "success": True,
            "data": {
                "count": 2,
                "views": [
                    {"name": "Front Elevation", "index": 0},
                    {"name": "Section A", "index": 1},
                ],
            },
        }

        with patch("rook.agent.tool_dispatcher.call_rhino", new_callable=AsyncMock) as mock_rhino:
            mock_rhino.return_value = mock_result
            result = await dispatcher.dispatch("rhino_views", {})

        mock_rhino.assert_called_once()
        call_args = mock_rhino.call_args
        assert call_args[0][0] == "/views"
        assert call_args[0][1] == "GET"
        assert result["success"] is True
        assert result["data"]["count"] == 2


# =============================================================================
# Dispatcher: rhino_views_restore (POST /views/restore)
# =============================================================================

class TestViewsRestoreDispatch:
    """Dispatch routing for named view restoration."""

    @pytest.fixture
    def dispatcher(self):
        return ToolDispatcher(port=9950)

    @pytest.mark.asyncio
    async def test_dispatches_to_correct_endpoint(self, dispatcher):
        mock_result = {
            "success": True,
            "data": {"name": "Front Elevation", "restored": True},
        }

        with patch("rook.agent.tool_dispatcher.call_rhino", new_callable=AsyncMock) as mock_rhino:
            mock_rhino.return_value = mock_result
            result = await dispatcher.dispatch(
                "rhino_views_restore", {"name": "Front Elevation"}
            )

        mock_rhino.assert_called_once()
        call_args = mock_rhino.call_args
        assert call_args[0][0] == "/views/restore"
        assert call_args[0][1] == "POST"
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_not_found_propagated(self, dispatcher):
        mock_result = {"success": False, "data": "Named view 'NoSuch' not found"}

        with patch("rook.agent.tool_dispatcher.call_rhino", new_callable=AsyncMock) as mock_rhino:
            mock_rhino.return_value = mock_result
            result = await dispatcher.dispatch(
                "rhino_views_restore", {"name": "NoSuch"}
            )

        assert result["success"] is False


# =============================================================================
# Dispatcher: rhino_views_save (POST /views/save)
# =============================================================================

class TestViewsSaveDispatch:
    """Dispatch routing for named view saving."""

    @pytest.fixture
    def dispatcher(self):
        return ToolDispatcher(port=9950)

    @pytest.mark.asyncio
    async def test_dispatches_to_correct_endpoint(self, dispatcher):
        mock_result = {
            "success": True,
            "data": {"name": "My View", "index": 3},
        }

        with patch("rook.agent.tool_dispatcher.call_rhino", new_callable=AsyncMock) as mock_rhino:
            mock_rhino.return_value = mock_result
            result = await dispatcher.dispatch(
                "rhino_views_save", {"name": "My View"}
            )

        mock_rhino.assert_called_once()
        call_args = mock_rhino.call_args
        assert call_args[0][0] == "/views/save"
        assert call_args[0][1] == "POST"
        assert result["success"] is True


# =============================================================================
# Dispatcher: rhino_viewport parameter passthrough
# =============================================================================

class TestViewportCaptureParams:
    """New capture parameters should be forwarded to the HTTP endpoint."""

    @pytest.fixture
    def dispatcher(self):
        return ToolDispatcher(port=9950)

    @pytest.mark.asyncio
    async def test_transparent_background_passthrough(self, dispatcher):
        mock_result = {
            "success": True,
            "data": {
                "format": "png",
                "width": 1920,
                "height": 1080,
                "savedToFile": True,
                "filePath": "/tmp/rook/viewports/viewport_test.png",
            },
        }

        with patch("rook.agent.tool_dispatcher.call_rhino", new_callable=AsyncMock) as mock_rhino:
            mock_rhino.return_value = mock_result
            result = await dispatcher.dispatch(
                "rhino_viewport",
                {
                    "width": 1920,
                    "height": 1080,
                    "transparentBackground": True,
                    "drawGrid": True,
                    "scale": 2,
                },
            )

        mock_rhino.assert_called_once()
        call_args = mock_rhino.call_args
        payload = call_args[0][2]  # third positional arg is the data dict
        assert payload["transparentBackground"] is True
        assert payload["drawGrid"] is True
        assert payload["scale"] == 2
        assert result["success"] is True
