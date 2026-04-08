"""Tests for the intent runtime: ExecutionPlan, CapabilityRouter, typed failures."""

import pytest

from rook.learning.intent_runtime import (
    CapabilityRouter,
    CATEGORIES,
    ExecutionFailure,
    ExecutionPlan,
    ExecutionResult,
    FailureLayer,
    RouteSpec,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset the CapabilityRouter singleton between tests."""
    CapabilityRouter.reset()
    yield
    CapabilityRouter.reset()


@pytest.fixture
def router():
    return CapabilityRouter.get()


# ---------------------------------------------------------------------------
# CapabilityRouter: basics
# ---------------------------------------------------------------------------

class TestCapabilityRouterBasics:

    def test_singleton(self):
        a = CapabilityRouter.get()
        b = CapabilityRouter.get()
        assert a is b

    def test_reset_creates_new_instance(self):
        a = CapabilityRouter.get()
        CapabilityRouter.reset()
        b = CapabilityRouter.get()
        assert a is not b

    def test_operation_count_is_positive(self, router):
        assert router.operation_count >= 90

    def test_list_operations_sorted(self, router):
        ops = router.list_operations()
        assert ops == sorted(ops)
        assert len(ops) == router.operation_count


# ---------------------------------------------------------------------------
# CapabilityRouter: routing
# ---------------------------------------------------------------------------

class TestCapabilityRouterRouting:

    def test_create_sphere_routes_to_create(self, router):
        spec = router.route("create_sphere")
        assert spec is not None
        assert spec.endpoint == "/create"
        assert spec.method == "POST"
        assert spec.base_params == {"type": "SPHERE"}
        assert "center" in spec.required_params
        assert "radius" in spec.required_params

    def test_move_routes_to_transform(self, router):
        spec = router.route("move")
        assert spec is not None
        assert spec.endpoint == "/transform"
        assert spec.base_params == {"operation": "move"}
        assert "ids" in spec.required_params
        assert "vector" in spec.required_params

    def test_boolean_union(self, router):
        spec = router.route("boolean_union")
        assert spec is not None
        assert spec.endpoint == "/boolean"
        assert spec.base_params == {"operation": "union"}

    def test_fillet_edge(self, router):
        spec = router.route("fillet_edge")
        assert spec is not None
        assert spec.endpoint == "/fillet"
        assert "id" in spec.required_params
        assert "radius" in spec.required_params

    def test_join_curves(self, router):
        spec = router.route("join_curves")
        assert spec is not None
        assert spec.endpoint == "/curve/join"

    def test_delete_layer_is_delete_method(self, router):
        spec = router.route("delete_layer")
        assert spec is not None
        assert spec.method == "DELETE"

    def test_unknown_operation_returns_none(self, router):
        assert router.route("loft_surface") is None
        assert router.route("sweep_along_rail") is None
        assert router.route("nonexistent") is None

    def test_has_direct_route(self, router):
        assert router.has_direct_route("create_box") is True
        assert router.has_direct_route("loft_surface") is False


# ---------------------------------------------------------------------------
# CapabilityRouter: param validation
# ---------------------------------------------------------------------------

class TestCapabilityRouterValidation:

    def test_valid_params(self, router):
        valid, missing = router.validate_params(
            "create_sphere", {"center": [0, 0, 0], "radius": 5}
        )
        assert valid is True
        assert missing == []

    def test_missing_required_params(self, router):
        valid, missing = router.validate_params(
            "create_sphere", {"center": [0, 0, 0]}
        )
        assert valid is False
        assert "radius" in missing

    def test_extra_params_are_fine(self, router):
        valid, missing = router.validate_params(
            "create_sphere", {"center": [0, 0, 0], "radius": 5, "color": [255, 0, 0]}
        )
        assert valid is True

    def test_unknown_operation(self, router):
        valid, missing = router.validate_params("loft_surface", {})
        assert valid is False
        assert "unknown operation" in missing[0]

    def test_no_required_params(self, router):
        """select_objects has no required params, only optional."""
        valid, missing = router.validate_params("select_objects", {})
        assert valid is True


# ---------------------------------------------------------------------------
# CapabilityRouter: payload building
# ---------------------------------------------------------------------------

class TestCapabilityRouterPayload:

    def test_build_payload_merges_base(self, router):
        payload = router.build_payload(
            "create_sphere", {"center": [0, 0, 0], "radius": 5}
        )
        assert payload == {
            "type": "SPHERE",
            "center": [0, 0, 0],
            "radius": 5,
        }

    def test_build_payload_user_wins_on_conflict(self, router):
        """User params override base_params if they conflict."""
        payload = router.build_payload(
            "create_sphere", {"type": "CUSTOM", "center": [0, 0, 0], "radius": 5}
        )
        assert payload["type"] == "CUSTOM"

    def test_build_payload_unknown_operation(self, router):
        """Unknown operation just returns params as-is."""
        payload = router.build_payload("loft_surface", {"curves": ["a", "b"]})
        assert payload == {"curves": ["a", "b"]}

    def test_build_payload_transform_move(self, router):
        payload = router.build_payload(
            "move", {"ids": ["guid-1"], "vector": [10, 0, 0]}
        )
        assert payload == {
            "operation": "move",
            "ids": ["guid-1"],
            "vector": [10, 0, 0],
        }


# ---------------------------------------------------------------------------
# CapabilityRouter: search and categories
# ---------------------------------------------------------------------------

class TestCapabilityRouterSearch:

    def test_find_operations_by_keyword(self, router):
        sphere_ops = router.find_operations("sphere")
        assert "create_sphere" in sphere_ops
        assert "create_mesh_sphere" in sphere_ops
        assert "create_subd_sphere" in sphere_ops

    def test_find_operations_case_insensitive(self, router):
        assert router.find_operations("SPHERE") == router.find_operations("sphere")

    def test_find_operations_no_match(self, router):
        assert router.find_operations("xyznonexistent") == []

    def test_category_for_operation(self, router):
        assert router.category_for("create_sphere") == "creation"
        assert router.category_for("move") == "transform"
        assert router.category_for("boolean_union") == "boolean"
        assert router.category_for("join_curves") == "curves"
        assert router.category_for("loft_surface") is None

    def test_categories_cover_all_operations(self, router):
        """Every operation in CATEGORIES should exist in the route table."""
        for cat, ops in CATEGORIES.items():
            for op in ops:
                assert router.has_direct_route(op), (
                    f"Category '{cat}' lists '{op}' but it's not in the route table"
                )

    def test_summary(self, router):
        s = router.summary()
        assert s["total_operations"] >= 90
        assert "categories" in s
        assert "endpoints" in s


# ---------------------------------------------------------------------------
# ExecutionPlan
# ---------------------------------------------------------------------------

class TestExecutionPlan:

    def test_to_dict_direct_api(self):
        plan = ExecutionPlan(
            intent="create a sphere at origin with radius 5",
            operation="create_sphere",
            params={"center": [0, 0, 0], "radius": 5},
            execution_route="direct_api",
            route_spec=RouteSpec(endpoint="/create", base_params={"type": "SPHERE"}),
            confidence=1.0,
        )
        d = plan.to_dict()
        assert d["operation"] == "create_sphere"
        assert d["execution_route"] == "direct_api"
        assert d["endpoint"] == "/create"
        assert "command" not in d

    def test_to_dict_command_path(self):
        plan = ExecutionPlan(
            intent="loft through these curves",
            operation="loft",
            params={"curves": ["a", "b"]},
            execution_route="known_command",
            command="_-Loft",
            mode="default",
            syntax="_-Loft _SelID a _SelID b _Enter",
            confidence=0.8,
        )
        d = plan.to_dict()
        assert d["command"] == "_-Loft"
        assert d["syntax"] == "_-Loft _SelID a _SelID b _Enter"
        assert "endpoint" not in d

    def test_to_dict_omits_empty_fields(self):
        plan = ExecutionPlan(intent="test", operation="test")
        d = plan.to_dict()
        assert "fallbacks" not in d
        assert "knowledge_context" not in d
        assert "reasoning_trace" not in d


# ---------------------------------------------------------------------------
# ExecutionResult
# ---------------------------------------------------------------------------

class TestExecutionResult:

    def test_success_result(self):
        result = ExecutionResult(
            success=True,
            intent="create a sphere",
            plan_summary={"operation": "create_sphere", "route": "direct_api"},
            created_ids=["guid-1"],
            objects_created=1,
            route_taken="direct_api",
            time_ms=42.5,
        )
        d = result.to_dict()
        assert d["success"] is True
        assert d["objects_created"] == 1
        assert d["created_ids"] == ["guid-1"]
        assert d["time_ms"] == 42.5
        assert "failure" not in d

    def test_failure_result(self):
        failure = ExecutionFailure(
            layer=FailureLayer.COMMAND_EXECUTION,
            operation="fillet_edge",
            attempted_route="known_command",
            error_detail="Command stalled at prompt: Select edges",
            recovery_suggestion="Select objects first with rhino_select",
        )
        result = ExecutionResult(
            success=False,
            intent="fillet the edges",
            failure=failure,
            route_taken="known_command",
        )
        d = result.to_dict()
        assert d["success"] is False
        assert d["failure"]["layer"] == "command_execution"
        assert "Select edges" in d["failure"]["error_detail"]


# ---------------------------------------------------------------------------
# ExecutionFailure
# ---------------------------------------------------------------------------

class TestExecutionFailure:

    def test_to_dict(self):
        f = ExecutionFailure(
            layer=FailureLayer.INTERACTIVE_PROMPT,
            operation="sweep",
            attempted_route="interactive",
            error_detail="Stalled at: Select rail curve",
            recovery_suggestion="Provide rail curve ID",
        )
        d = f.to_dict()
        assert d["layer"] == "interactive_prompt"
        assert d["operation"] == "sweep"
        assert d["recovery_suggestion"] == "Provide rail curve ID"

    def test_to_dict_omits_none_suggestion(self):
        f = ExecutionFailure(
            layer=FailureLayer.TIMEOUT,
            operation="boolean_union",
            attempted_route="direct_api",
            error_detail="30s timeout",
        )
        d = f.to_dict()
        assert "recovery_suggestion" not in d

    def test_to_correction(self):
        f = ExecutionFailure(
            layer=FailureLayer.PARAMETER_SYNTHESIS,
            operation="create_box",
            attempted_route="direct_api",
            error_detail="Missing height parameter",
            recovery_suggestion="Extract height from intent",
        )
        c = f.to_correction()
        assert c["type"] == "execution_failure"
        assert c["layer"] == "parameter_synthesis"
        assert c["route"] == "direct_api"

    def test_all_failure_layers(self):
        """Verify all enum values are distinct strings."""
        values = [fl.value for fl in FailureLayer]
        assert len(values) == len(set(values))
        assert len(values) == 7


# ---------------------------------------------------------------------------
# Route table completeness
# ---------------------------------------------------------------------------

class TestRouteTableCompleteness:
    """Verify the route table matches the C++ plugin's capabilities."""

    def test_all_geometry_creation_ops(self, router):
        geo_create = CATEGORIES["creation"]
        # 13 NURBS + 4 mesh + 3 SubD = 20
        assert len(geo_create) == 20
        for op in geo_create:
            assert router.has_direct_route(op), f"Missing creation op: {op}"

    def test_all_transform_ops(self, router):
        for op in ("move", "rotate", "scale", "mirror", "copy", "delete"):
            assert router.has_direct_route(op), f"Missing transform op: {op}"

    def test_all_boolean_ops(self, router):
        for op in ("boolean_union", "boolean_difference", "boolean_intersection", "boolean_split"):
            assert router.has_direct_route(op)

    def test_all_curve_ops(self, router):
        curve_ops = CATEGORIES["curves"]
        assert len(curve_ops) == 12
        for op in curve_ops:
            assert router.has_direct_route(op), f"Missing curve op: {op}"

    def test_all_intersection_ops(self, router):
        for op in CATEGORIES["intersection"]:
            assert router.has_direct_route(op)

    def test_all_mesh_ops(self, router):
        for op in CATEGORIES["mesh"]:
            assert router.has_direct_route(op)

    def test_all_subd_ops(self, router):
        for op in CATEGORIES["subd"]:
            assert router.has_direct_route(op)

    def test_all_layer_ops(self, router):
        for op in CATEGORIES["layers"]:
            assert router.has_direct_route(op)

    def test_all_block_ops(self, router):
        for op in CATEGORIES["blocks"]:
            assert router.has_direct_route(op)
