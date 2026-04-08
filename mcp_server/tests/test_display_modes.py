"""Tests for display mode MCP tools.

Covers:
  1. BRIDGE_ROUTES entries for rhino_display_modes, rhino_display_mode_set
  2. Dispatch routing for both tools
  3. Tool group membership
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, patch

from rook.agent.tool_dispatcher import (
    ToolDispatcher,
    BRIDGE_ROUTES,
)
from rook.agent.tool_groups import TOOL_GROUPS


# =============================================================================
# BRIDGE_ROUTES coverage
# =============================================================================

class TestDisplayModeRouting:
    """Display mode tools must be in BRIDGE_ROUTES with correct endpoints."""

    def test_display_modes_in_bridge_routes(self):
        assert "rhino_display_modes" in BRIDGE_ROUTES
        endpoint, method = BRIDGE_ROUTES["rhino_display_modes"]
        assert endpoint == "/display-modes"
        assert method == "GET"

    def test_display_mode_set_in_bridge_routes(self):
        assert "rhino_display_mode_set" in BRIDGE_ROUTES
        endpoint, method = BRIDGE_ROUTES["rhino_display_mode_set"]
        assert endpoint == "/display-mode"
        assert method == "POST"


# =============================================================================
# Dispatcher: rhino_display_modes (GET /display-modes)
# =============================================================================

class TestDisplayModesDispatch:
    """Dispatch routing for display mode listing."""

    @pytest.fixture
    def dispatcher(self):
        return ToolDispatcher(port=9950)

    @pytest.mark.asyncio
    async def test_dispatches_to_correct_endpoint(self, dispatcher):
        mock_result = {
            "success": True,
            "data": {
                "count": 3,
                "modes": [
                    {"name": "Wireframe", "id": "uuid-1", "isActive": False},
                    {"name": "Shaded", "id": "uuid-2", "isActive": True},
                    {"name": "Rendered", "id": "uuid-3", "isActive": False},
                ],
            },
        }

        with patch("rook.agent.tool_dispatcher.call_rhino", new_callable=AsyncMock) as mock_rhino:
            mock_rhino.return_value = mock_result
            result = await dispatcher.dispatch("rhino_display_modes", {})

        mock_rhino.assert_called_once()
        call_args = mock_rhino.call_args
        assert call_args[0][0] == "/display-modes"
        assert call_args[0][1] == "GET"
        assert result["success"] is True
        assert result["data"]["count"] == 3


# =============================================================================
# Dispatcher: rhino_display_mode_set (POST /display-mode)
# =============================================================================

class TestDisplayModeSetDispatch:
    """Dispatch routing for setting display mode."""

    @pytest.fixture
    def dispatcher(self):
        return ToolDispatcher(port=9950)

    @pytest.mark.asyncio
    async def test_dispatches_name_to_correct_endpoint(self, dispatcher):
        mock_result = {
            "success": True,
            "data": {"name": "Wireframe", "id": "uuid-1", "applied": True},
        }

        with patch("rook.agent.tool_dispatcher.call_rhino", new_callable=AsyncMock) as mock_rhino:
            mock_rhino.return_value = mock_result
            result = await dispatcher.dispatch(
                "rhino_display_mode_set", {"name": "Wireframe"}
            )

        mock_rhino.assert_called_once()
        call_args = mock_rhino.call_args
        assert call_args[0][0] == "/display-mode"
        assert call_args[0][1] == "POST"
        assert result["success"] is True
        assert result["data"]["applied"] is True

    @pytest.mark.asyncio
    async def test_dispatches_id_to_correct_endpoint(self, dispatcher):
        mock_result = {
            "success": True,
            "data": {"name": "Shaded", "id": "uuid-2", "applied": True},
        }

        with patch("rook.agent.tool_dispatcher.call_rhino", new_callable=AsyncMock) as mock_rhino:
            mock_rhino.return_value = mock_result
            result = await dispatcher.dispatch(
                "rhino_display_mode_set", {"id": "uuid-2"}
            )

        mock_rhino.assert_called_once()
        payload = mock_rhino.call_args[0][2]
        assert payload["id"] == "uuid-2"
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_not_found_propagated(self, dispatcher):
        mock_result = {"success": False, "data": "Display mode 'NoSuch' not found"}

        with patch("rook.agent.tool_dispatcher.call_rhino", new_callable=AsyncMock) as mock_rhino:
            mock_rhino.return_value = mock_result
            result = await dispatcher.dispatch(
                "rhino_display_mode_set", {"name": "NoSuch"}
            )

        assert result["success"] is False


# =============================================================================
# Tool groups
# =============================================================================

class TestDisplayModeToolGroups:
    """Display mode tools belong in the correct tool groups."""

    def test_in_viewport_group(self):
        assert "rhino_display_modes" in TOOL_GROUPS["viewport"]
        assert "rhino_display_mode_set" in TOOL_GROUPS["viewport"]

    def test_list_in_viewport_readonly(self):
        assert "rhino_display_modes" in TOOL_GROUPS["viewport_readonly"]

    def test_set_not_in_viewport_readonly(self):
        assert "rhino_display_mode_set" not in TOOL_GROUPS["viewport_readonly"]
