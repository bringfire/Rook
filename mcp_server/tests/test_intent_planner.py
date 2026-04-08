"""Tests for the IntentPlanner (P1): intent -> ExecutionPlan.

Tests the fast path (regex + CapabilityRouter), the plan_direct API,
and the command fallback path with mocked dependencies.
"""

import asyncio
import pytest
from unittest.mock import MagicMock
from dataclasses import dataclass

from rook.learning.intent_runtime import CapabilityRouter, ExecutionPlan
from rook.learning.intent_planner import (
    IntentPlanner,
    _extract_creation_params,
    _extract_ids,
    _parse_confidence,
    _parse_params,
)


def run(coro):
    """Run an async coroutine synchronously."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_router():
    CapabilityRouter.reset()
    yield
    CapabilityRouter.reset()


@pytest.fixture
def planner():
    """Planner with no knowledge store (fast path only)."""
    p = IntentPlanner()
    # Disable DSPy so we only test regex fast path
    p._ensure_dspy = lambda: False
    return p


@pytest.fixture
def mock_knowledge_store():
    """Mocked CommandKnowledgeStore."""
    store = MagicMock()

    @dataclass
    class FakeCandidate:
        command: str
        mode: str
        confidence: float
        reason: str = ""

    @dataclass
    class FakeCommand:
        description: str
        modes: dict

    store.search_by_intent.return_value = [
        FakeCandidate(command="_-Loft", mode="default", confidence=0.8),
    ]
    store.get_command.return_value = FakeCommand(
        description="Loft curves to create a surface",
        modes={"default": MagicMock(), "tight": MagicMock()},
    )
    store.get_syntax.return_value = "_-Loft _SelID <curve1> _SelID <curve2> _Enter"
    store.get_gotchas.return_value = ["Curves must be in order"]

    return store


# ---------------------------------------------------------------------------
# Regex extraction (zero LLM calls)
# ---------------------------------------------------------------------------

class TestRegexExtraction:

    def test_create_sphere_with_coords_and_radius(self, planner):
        plan = run(planner.plan("create a sphere at 0,0,0 with radius 5"))
        assert plan.execution_route == "direct_api"
        assert plan.operation == "create_sphere"
        assert plan.params["center"] == [0.0, 0.0, 0.0]
        assert plan.params["radius"] == 5.0
        assert plan.confidence >= 0.8

    def test_create_box_with_dimensions(self, planner):
        plan = run(planner.plan("create a box at 0,0,0 10 by 8 by 6"))
        assert plan.execution_route == "direct_api"
        assert plan.operation == "create_box"
        assert plan.params.get("width") == 10.0

    def test_create_cylinder(self, planner):
        plan = run(planner.plan("create a cylinder at 5,5,0 radius 3 height 10"))
        assert plan.execution_route == "direct_api"
        assert plan.operation == "create_cylinder"
        assert plan.params["radius"] == 3.0
        assert plan.params["height"] == 10.0

    def test_create_line(self, planner):
        plan = run(planner.plan("create a line from 0,0,0 to 10,5,0"))
        assert plan.execution_route == "direct_api"
        assert plan.operation == "create_line"
        assert plan.params["start"] == [0.0, 0.0, 0.0]
        assert plan.params["end"] == [10.0, 5.0, 0.0]

    def test_create_point(self, planner):
        plan = run(planner.plan("create a point at 3,4,5"))
        assert plan.execution_route == "direct_api"
        assert plan.operation == "create_point"
        assert plan.params["location"] == [3.0, 4.0, 5.0]

    def test_delete_with_guids(self, planner):
        guid = "12345678-1234-1234-1234-123456789abc"
        plan = run(planner.plan(f"delete {guid}"))
        assert plan.execution_route == "direct_api"
        assert plan.operation == "delete"
        assert guid in plan.params["ids"]

    def test_select_all(self, planner):
        plan = run(planner.plan("select all objects"))
        assert plan.execution_route == "direct_api"
        assert plan.operation == "select_objects"
        assert plan.params.get("all") is True

    def test_move_with_vector(self, planner):
        plan = run(planner.plan("move by 10, 0, 0"))
        assert plan.execution_route == "direct_api"
        assert plan.operation == "move"
        assert plan.params["vector"] == [10.0, 0.0, 0.0]

    def test_unrecognized_intent_without_dspy(self, planner):
        plan = run(planner.plan("loft through these curves"))
        assert plan.execution_route == "unknown"

    def test_sphere_keyword_without_params(self, planner):
        """Even with just the keyword, should route to correct operation."""
        plan = run(planner.plan("make a sphere"))
        assert plan.operation == "create_sphere"
        assert plan.execution_route == "direct_api"

    def test_create_rectangle(self, planner):
        plan = run(planner.plan("create a rectangle at 0,0,0 width 20 height 10"))
        assert plan.execution_route == "direct_api"
        assert plan.operation == "create_rectangle"
        assert plan.params["width"] == 20.0
        assert plan.params["height"] == 10.0

    def test_cone_with_height(self, planner):
        plan = run(planner.plan("create a cone at 0,0,0 radius 4 height 12"))
        assert plan.execution_route == "direct_api"
        assert plan.operation == "create_cone"


# ---------------------------------------------------------------------------
# plan_direct (zero LLM calls, explicit operation)
# ---------------------------------------------------------------------------

class TestPlanDirect:

    def test_valid_operation_and_params(self, planner):
        plan = planner.plan_direct(
            "create_sphere", {"center": [0, 0, 0], "radius": 5}
        )
        assert plan.execution_route == "direct_api"
        assert plan.route_spec is not None
        assert plan.route_spec.endpoint == "/create"
        assert plan.confidence == 1.0

    def test_missing_required_params(self, planner):
        plan = planner.plan_direct("create_sphere", {"center": [0, 0, 0]})
        assert plan.execution_route == "direct_api"
        assert plan.confidence == 0.5
        assert any("Missing" in t for t in plan.reasoning_trace)

    def test_unknown_operation(self, planner):
        plan = planner.plan_direct("loft", {"curves": ["a", "b"]})
        assert plan.execution_route == "unknown"
        assert plan.confidence == 0.0


# ---------------------------------------------------------------------------
# Command fallback path (mocked DSPy)
# ---------------------------------------------------------------------------

class TestCommandPath:

    def test_falls_back_to_command_path(self, mock_knowledge_store):
        planner = IntentPlanner(knowledge_store=mock_knowledge_store)
        planner._ensure_dspy = lambda: False

        plan = run(planner.plan("loft through these curves"))
        assert plan.execution_route == "known_command"
        assert plan.command == "_-Loft"
        assert plan.syntax is not None
        assert "interactive" in plan.fallbacks

    def test_command_path_with_gotchas(self, mock_knowledge_store):
        planner = IntentPlanner(knowledge_store=mock_knowledge_store)
        planner._ensure_dspy = lambda: False

        plan = run(planner.plan("loft through these curves"))
        assert "Curves must be in order" in plan.knowledge_context

    def test_no_candidates_returns_unknown(self, mock_knowledge_store):
        mock_knowledge_store.search_by_intent.return_value = []
        planner = IntentPlanner(knowledge_store=mock_knowledge_store)
        planner._ensure_dspy = lambda: False

        plan = run(planner.plan("do something impossible"))
        assert plan.execution_route == "unknown"

    def test_no_syntax_still_returns_plan(self, mock_knowledge_store):
        """Even without syntax, command plan should have command/mode."""
        mock_knowledge_store.get_syntax.return_value = None
        planner = IntentPlanner(knowledge_store=mock_knowledge_store)
        planner._ensure_dspy = lambda: False

        plan = run(planner.plan("loft through these curves"))
        assert plan.execution_route == "known_command"
        assert plan.command == "_-Loft"
        assert plan.syntax is None
        assert plan.confidence < 0.8  # Reduced confidence without syntax


# ---------------------------------------------------------------------------
# Helper function unit tests
# ---------------------------------------------------------------------------

class TestRegexWordBoundary:
    """Verify H2/H3 fixes: word-boundary matching, no false positives."""

    def test_centerline_does_not_match_line(self, planner):
        plan = run(planner.plan("the centerline is at 5,5,5"))
        # "centerline" should NOT match "line"
        assert plan.operation != "create_line"

    def test_viewpoint_does_not_match_point(self, planner):
        plan = run(planner.plan("create a viewpoint at 0,0,0"))
        # "viewpoint" should NOT match "point"
        assert plan.operation != "create_point"

    def test_polyline_matches_before_line(self, planner):
        plan = run(planner.plan("create a polyline through 0,0,0 and 1,1,1 and 2,2,2"))
        assert plan.operation == "create_polyline"

    def test_remove_triggers_delete(self, planner):
        guid = "12345678-1234-1234-1234-123456789abc"
        plan = run(planner.plan(f"remove {guid}"))
        assert plan.operation == "delete"

    def test_incidental_mention_no_verb(self, planner):
        """'sphere' without a creation verb should not match when no params."""
        plan = run(planner.plan("the sphere is interesting"))
        assert plan.execution_route == "unknown"


class TestDspyExtractorMocked:
    """L2: Test the DSPy fast path with a mocked extractor."""

    def test_extractor_returns_known_operation(self):
        planner = IntentPlanner()
        planner._dspy_configured = True

        mock_ext = MagicMock()
        mock_ext.return_value = MagicMock(
            operation="create_sphere",
            params={"center": [0, 0, 0], "radius": 5},
            confidence=0.95,
        )
        planner._extractor = mock_ext

        plan = run(planner.plan("please generate a sphere radius 5 at origin"))
        assert plan.execution_route == "direct_api"
        assert plan.operation == "create_sphere"

    def test_extractor_returns_unknown(self):
        planner = IntentPlanner()
        planner._dspy_configured = True

        mock_ext = MagicMock()
        mock_ext.return_value = MagicMock(
            operation="unknown",
            params={},
            confidence=0.1,
        )
        planner._extractor = mock_ext

        plan = run(planner.plan("do something exotic"))
        # Should fall through to unknown (no knowledge store)
        assert plan.execution_route == "unknown"


class TestGotchaAugmentation:
    """L3: Test _augment_gotchas with mocked KG."""

    def test_augments_from_kg(self):
        kg = MagicMock()
        # _augment_gotchas calls kg.query twice; cmd_name is "sphere" (stripped from "_-Sphere")
        # The avoid reason must contain the cmd_name for the filter to pass
        kg.query.return_value = {
            "avoid": [{"reason": "sphere: use center not origin"}],
            "patterns": [],
        }
        planner = IntentPlanner(knowledge_graph=kg)
        gotchas = ["existing gotcha"]
        result = planner._augment_gotchas(gotchas, "_-Sphere", "create sphere", [])

        assert "existing gotcha" in result
        assert any("AVOID:" in g for g in result)
        # Original list should NOT be mutated (M2 fix)
        assert len(gotchas) == 1

    def test_no_kg_returns_original(self):
        planner = IntentPlanner()
        gotchas = ["a", "b"]
        result = planner._augment_gotchas(gotchas, "_-Box", "create box", [])
        assert result == gotchas


class TestExtractCreationParams:

    def test_sphere_with_at_and_radius(self):
        params = _extract_creation_params(
            "create a sphere at 0,0,0 with radius 5", "sphere"
        )
        assert params is not None
        assert params["center"] == [0.0, 0.0, 0.0]
        assert params["radius"] == 5.0

    def test_box_with_by_pattern(self):
        params = _extract_creation_params(
            "create box at 0,0,0 10 by 8 by 6", "box"
        )
        assert params is not None
        assert params["width"] == 10.0
        assert params["depth"] == 8.0
        assert params["height"] == 6.0

    def test_line_two_coords(self):
        params = _extract_creation_params(
            "line from 0,0,0 to 10,5,0", "line"
        )
        assert params is not None
        assert params["start"] == [0.0, 0.0, 0.0]
        assert params["end"] == [10.0, 5.0, 0.0]

    def test_line_one_coord_returns_none(self):
        params = _extract_creation_params("line from 0,0,0", "line")
        assert params is None

    def test_no_params_returns_none(self):
        params = _extract_creation_params("create a sphere", "sphere")
        assert params is None

    def test_rectangle_with_dimensions(self):
        params = _extract_creation_params(
            "rectangle at 0,0,0 width 20 height 10", "rectangle"
        )
        assert params is not None
        assert params["width"] == 20.0
        assert params["height"] == 10.0


class TestExtractIds:

    def test_single_guid(self):
        ids = _extract_ids("delete 12345678-1234-1234-1234-123456789abc")
        assert len(ids) == 1

    def test_multiple_guids(self):
        text = "select 12345678-1234-1234-1234-123456789abc and abcdef01-2345-6789-abcd-ef0123456789"
        ids = _extract_ids(text)
        assert len(ids) == 2

    def test_no_guids(self):
        assert _extract_ids("select everything") == []


class TestParseConfidence:

    def test_normal_float(self):
        assert _parse_confidence(0.85) == 0.85

    def test_string_float(self):
        assert _parse_confidence("0.9") == 0.9

    def test_clamp_above_1(self):
        assert _parse_confidence(1.5) == 1.0

    def test_clamp_below_0(self):
        assert _parse_confidence(-0.5) == 0.0

    def test_invalid_returns_default(self):
        assert _parse_confidence("not a number") == 0.5


class TestParseParams:

    def test_dict_passthrough(self):
        d = {"center": [0, 0, 0]}
        assert _parse_params(d) == d

    def test_json_string(self):
        assert _parse_params('{"radius": 5}') == {"radius": 5}

    def test_invalid_string(self):
        assert _parse_params("not json") == {}

    def test_none(self):
        assert _parse_params(None) == {}


# ---------------------------------------------------------------------------
# Geometry context injection (M1)
# ---------------------------------------------------------------------------

class TestGeometryContextInjection:
    """M1: Verify that selected_ids from context are injected into plans."""

    def test_move_injects_selected_ids(self, planner):
        """'move by 10,0,0' with selected objects should populate ids."""
        ctx = {"selected_ids": ["guid-a", "guid-b"]}
        plan = run(planner.plan("move by 10, 0, 0", context=ctx))
        assert plan.operation == "move"
        assert plan.params["ids"] == ["guid-a", "guid-b"]
        assert plan.params["vector"] == [10.0, 0.0, 0.0]

    def test_delete_injects_selected_ids(self, planner):
        """'delete the selected objects' without GUIDs should use selection."""
        ctx = {"selected_ids": ["guid-1", "guid-2", "guid-3"]}
        plan = run(planner.plan("delete the selected objects", context=ctx))
        assert plan.operation == "delete"
        assert plan.params["ids"] == ["guid-1", "guid-2", "guid-3"]

    def test_explicit_guids_not_overwritten(self, planner):
        """When intent has explicit GUIDs, context should NOT overwrite."""
        guid = "12345678-1234-1234-1234-123456789abc"
        ctx = {"selected_ids": ["other-guid"]}
        plan = run(planner.plan(f"delete {guid}", context=ctx))
        assert plan.operation == "delete"
        assert guid in plan.params["ids"]
        # The explicit GUID from text should be used, not the context
        assert "other-guid" not in plan.params["ids"]

    def test_no_context_no_injection(self, planner):
        """Without context, move should not have ids."""
        plan = run(planner.plan("move by 5, 0, 0"))
        assert plan.operation == "move"
        assert "ids" not in plan.params

    def test_empty_selection_no_injection(self, planner):
        """Empty selected_ids should not inject."""
        ctx = {"selected_ids": []}
        plan = run(planner.plan("move by 5, 0, 0", context=ctx))
        assert plan.operation == "move"
        assert "ids" not in plan.params

    def test_creation_ops_not_injected(self, planner):
        """Creation operations should NOT get selected_ids injected."""
        ctx = {"selected_ids": ["guid-1"]}
        plan = run(planner.plan("create a sphere at 0,0,0 with radius 5", context=ctx))
        assert plan.operation == "create_sphere"
        assert "ids" not in plan.params

    def test_context_trace_logged(self, planner):
        """Planner should log context info in reasoning trace."""
        ctx = {"selected_ids": ["guid-a", "guid-b"]}
        plan = run(planner.plan("move by 10, 0, 0", context=ctx))
        assert any("2 selected" in t for t in plan.reasoning_trace)
        assert any("Injected" in t for t in plan.reasoning_trace)

    def test_fillet_injects_single_id(self, planner):
        """Fillet uses 'id' (singular) not 'ids'."""
        # Fillet won't match regex fast path, but _inject_context_ids
        # is tested directly via the static method
        from rook.learning.intent_planner import _ID_INJECTABLE_OPS
        assert "fillet_edge" in _ID_INJECTABLE_OPS

        # Test the static method directly
        ctx = {"selected_ids": ["brep-guid"]}
        trace: list[str] = []
        result = IntentPlanner._inject_context_ids(
            "fillet_edge", {"radius": 2.0}, ctx, trace,
        )
        assert result["id"] == "brep-guid"
        assert result["radius"] == 2.0

    def test_inject_does_not_mutate_input(self, planner):
        """_inject_context_ids must not mutate the input params dict."""
        original = {"vector": [1, 0, 0]}
        ctx = {"selected_ids": ["guid-1"]}
        trace: list[str] = []
        result = IntentPlanner._inject_context_ids(
            "move", original, ctx, trace,
        )
        assert "ids" in result
        assert "ids" not in original  # Original must be untouched
