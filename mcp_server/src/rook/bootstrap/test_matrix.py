"""
Test Matrix Definition

Defines all test cases for bootstrapping the knowledge graph.
Each test case specifies:
- Tool to test
- Parameters to use
- Expected outcome (success/failure)
- What pattern should be learned
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TestPhase(Enum):
    """Phases of bootstrap testing."""
    PHASE_1_QUERY = 1          # Read-only tools
    PHASE_2_CREATE = 2         # Geometry creation
    PHASE_3_LAYER = 3          # Layer management
    PHASE_4_SELECT = 4         # Selection tools
    PHASE_5_TRANSFORM = 5      # Modification tools
    PHASE_6_ADVANCED = 6       # Boolean, loft, sweep, extrude
    PHASE_7_MEASURE = 7        # Measurement tools (distance, area, volume, etc.)
    PHASE_8_CURVE = 8          # Curve operations
    PHASE_9_DOCUMENT = 9       # Document & material ops
    PHASE_10_SCRIPT = 10       # Script execution
    PHASE_11_IO = 11           # Import/export, groups
    PHASE_12_EDGE = 12         # Edge cases across all tools
    PHASE_13_BLOCKS = 13       # Block operations (list, create, insert, explode, delete)


class ExpectedOutcome(Enum):
    """Expected result of a test."""
    SUCCESS = "success"
    FAILURE = "failure"
    EITHER = "either"  # For tests where we're exploring behavior


@dataclass
class TestCase:
    """Single test case definition."""
    id: str                              # Unique identifier
    tool: str                            # MCP tool name
    params: dict[str, Any]               # Parameters to pass
    expected: ExpectedOutcome            # What we expect
    phase: TestPhase                     # Which phase this belongs to
    description: str                     # Human-readable description
    intent: str                          # Intent string for knowledge recording
    tags: list[str] = field(default_factory=list)  # Categorization tags
    depends_on: list[str] = field(default_factory=list)  # Test IDs this depends on
    cleanup_ids: list[str] = field(default_factory=list)  # Object IDs to delete after
    learn_on_success: str = ""           # Pattern note if succeeds
    learn_on_failure: str = ""           # Pattern note if fails


@dataclass
class TestMatrix:
    """Collection of test cases with metadata."""
    cases: list[TestCase]

    def get_phase(self, phase: TestPhase) -> list[TestCase]:
        """Get all tests for a specific phase."""
        return [c for c in self.cases if c.phase == phase]

    def get_by_tool(self, tool: str) -> list[TestCase]:
        """Get all tests for a specific tool."""
        return [c for c in self.cases if c.tool == tool]

    def get_by_tag(self, tag: str) -> list[TestCase]:
        """Get all tests with a specific tag."""
        return [c for c in self.cases if tag in c.tags]

    def get_by_id(self, test_id: str) -> TestCase | None:
        """Get a specific test by ID."""
        for c in self.cases:
            if c.id == test_id:
                return c
        return None


# =============================================================================
# PHASE 1: Query Tools (Read-Only)
# =============================================================================

PHASE_1_TESTS = [
    TestCase(
        id="query-001",
        tool="rhino_ping",
        params={},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_1_QUERY,
        description="Basic connectivity test",
        intent="check if Rhino is connected and responding",
        tags=["connectivity", "basic"],
        learn_on_success=(
            "To check Rhino connection: use rhino_ping with no parameters. "
            "Returns {success: true, data: 'pong'} if connected. "
            "Always call this first before any Rhino operations to verify the bridge is running."
        ),
    ),
    TestCase(
        id="query-002",
        tool="rhino_document",
        params={},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_1_QUERY,
        description="Get document info",
        intent="get current Rhino document information including name and units",
        tags=["document", "info"],
        learn_on_success=(
            "To get document info: use rhino_document with no parameters. "
            "Returns {name: 'filename.3dm', units: 'Millimeters', objectCount: N, summary: {...}}. "
            "Use this to understand the current model context before creating geometry."
        ),
    ),
    TestCase(
        id="query-003",
        tool="rhino_layers",
        params={},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_1_QUERY,
        description="List all layers",
        intent="list all layers in the document with their properties",
        tags=["layers", "info"],
        learn_on_success=(
            "To list layers: use rhino_layers with no parameters. "
            "Returns array of {name, fullPath, color, visible, locked, objectCount}. "
            "Nested layers use '::' separator in fullPath (e.g., 'Parent::Child'). "
            "Check this before creating objects to place them on the correct layer."
        ),
    ),
    TestCase(
        id="query-004",
        tool="rhino_objects",
        params={},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_1_QUERY,
        description="Query all objects (no filter)",
        intent="list all geometry objects in the document",
        tags=["objects", "query"],
        learn_on_success=(
            "To list all objects: use rhino_objects with no parameters. "
            "Returns array of {id (GUID), type, name, layer, bbox}. "
            "Use limit/offset params for large models. Default limit is 100, max 500. "
            "Object IDs (GUIDs) are needed for transform, delete, select operations."
        ),
    ),
    TestCase(
        id="query-005",
        tool="rhino_objects",
        params={"type": "Curve"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_1_QUERY,
        description="Query objects by type",
        intent="find all curve objects in the document",
        tags=["objects", "query", "filter"],
        learn_on_success=(
            "To filter objects by type: use rhino_objects with type param. "
            "Valid types: 'Point', 'Curve', 'Brep' (solids/surfaces), 'Mesh', 'Extrusion', 'TextDot'. "
            "Example: {type: 'Brep'} returns all solid/surface geometry. "
            "Type names are case-sensitive and match RhinoCommon ObjectType enum."
        ),
    ),
    TestCase(
        id="query-006",
        tool="rhino_objects",
        params={"layer": "Default"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_1_QUERY,
        description="Query objects by layer",
        intent="find all objects on a specific layer",
        tags=["objects", "query", "filter"],
        learn_on_success=(
            "To filter objects by layer: use rhino_objects with layer param. "
            "Layer is the full path string (e.g., 'Default' or 'Parent::Child'). "
            "Can combine with type filter: {layer: 'Default', type: 'Curve'}."
        ),
    ),
    TestCase(
        id="query-007",
        tool="rhino_selection",
        params={},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_1_QUERY,
        description="Get current selection",
        intent="get the currently selected objects in Rhino",
        tags=["selection", "query"],
        learn_on_success=(
            "To get selected objects: use rhino_selection with no parameters. "
            "Returns array of selected objects with {id, type, name, layer, bbox}. "
            "Returns empty array if nothing selected. "
            "Use rhino_select to programmatically select objects by ID or layer."
        ),
    ),
    TestCase(
        id="query-008",
        tool="rhino_viewport",
        params={},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_1_QUERY,
        description="Capture viewport (default settings)",
        intent="capture a screenshot of the current Rhino viewport",
        tags=["viewport", "capture"],
        learn_on_success=(
            "To capture viewport: use rhino_viewport. Returns base64-encoded PNG image. "
            "Default size is 800x600. Use width/height params to customize. "
            "The image shows the active viewport (Perspective by default)."
        ),
    ),
    TestCase(
        id="query-009",
        tool="rhino_viewport",
        params={"view": "Top", "width": 400, "height": 300},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_1_QUERY,
        description="Capture specific viewport with size",
        intent="capture a top view at a specific resolution",
        tags=["viewport", "capture", "params"],
        learn_on_success=(
            "To capture specific view: use rhino_viewport with view param. "
            "Valid views: 'Top', 'Bottom', 'Front', 'Back', 'Left', 'Right', 'Perspective'. "
            "Example: {view: 'Top', width: 800, height: 600}. "
            "Useful for generating documentation or checking geometry from different angles."
        ),
    ),
    # NOTE: rhino_instances is an MCP-level tool, not an HTTP endpoint.
    # It discovers Rhino instances via temp files, not by calling Rhino.
    # Removed from Phase 1 as it can't be tested via HTTP executor.
    # TestCase(
    #     id="query-010",
    #     tool="rhino_instances",
    #     ...
    # ),
]


# =============================================================================
# PHASE 2: Creation Tools
# =============================================================================

PHASE_2_TESTS = [
    # POINT
    TestCase(
        id="create-001",
        tool="rhino_create",
        params={"type": "POINT", "point": [0, 0, 0]},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_2_CREATE,
        description="Create point at origin",
        intent="create a point at the origin in Rhino",
        tags=["create", "point", "basic"],
        learn_on_success=(
            "To create a POINT: use rhino_create with {type: 'POINT', point: [x, y, z]}. "
            "Returns {success: true, data: {id: 'GUID'}}. "
            "The returned id is needed for transforms, selection, or deletion."
        ),
    ),
    TestCase(
        id="create-002",
        tool="rhino_create",
        params={"type": "POINT"},
        expected=ExpectedOutcome.SUCCESS,  # Actually succeeds - defaults to origin
        phase=TestPhase.PHASE_2_CREATE,
        description="Create point without coordinates (defaults to origin)",
        intent="create a point without specifying location",
        tags=["create", "point", "default"],
        learn_on_success=(
            "POINT without 'point' param defaults to origin [0,0,0]. "
            "Rhino is permissive - missing coords don't cause errors."
        ),
    ),

    # LINE
    TestCase(
        id="create-003",
        tool="rhino_create",
        params={"type": "LINE", "start": [0, 0, 0], "end": [10, 0, 0]},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_2_CREATE,
        description="Create line between two points",
        intent="create a line from origin extending along X axis",
        tags=["create", "line", "basic"],
        learn_on_success=(
            "To create a LINE: use rhino_create with {type: 'LINE', start: [x,y,z], end: [x,y,z]}. "
            "Both start and end are required. "
            "Creates a LineCurve object (type 'Curve' in queries)."
        ),
    ),
    TestCase(
        id="create-004",
        tool="rhino_create",
        params={"type": "LINE", "start": [0, 0, 0]},
        expected=ExpectedOutcome.FAILURE,
        phase=TestPhase.PHASE_2_CREATE,
        description="Create line without end point",
        intent="create a line without specifying endpoint",
        tags=["create", "line", "invalid"],
        learn_on_failure=(
            "LINE requires both 'start' AND 'end' params. "
            "Missing 'end' returns {success: false}. "
            "Always provide both endpoints when creating lines."
        ),
    ),

    # CIRCLE
    TestCase(
        id="create-005",
        tool="rhino_create",
        params={"type": "CIRCLE", "center": [0, 0, 0], "radius": 5},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_2_CREATE,
        description="Create circle at origin",
        intent="create a circle with radius 5 centered at origin",
        tags=["create", "circle", "basic"],
        learn_on_success=(
            "To create a CIRCLE: use rhino_create with {type: 'CIRCLE', center: [x,y,z], radius: N}. "
            "Circle is on XY plane by default (Z=0). "
            "Creates an ArcCurve object (type 'Curve' in queries)."
        ),
    ),
    TestCase(
        id="create-006",
        tool="rhino_create",
        params={"type": "CIRCLE", "center": [0, 0, 0], "radius": -5},
        expected=ExpectedOutcome.SUCCESS,  # Rhino uses absolute value
        phase=TestPhase.PHASE_2_CREATE,
        description="Create circle with negative radius (uses absolute value)",
        intent="create a circle with negative radius value",
        tags=["create", "circle", "edge-case"],
        learn_on_success=(
            "CIRCLE with negative radius uses absolute value - Rhino is permissive. "
            "radius: -5 creates same circle as radius: 5. "
            "No need to validate radius sign before calling."
        ),
    ),
    TestCase(
        id="create-007",
        tool="rhino_create",
        params={"type": "CIRCLE", "center": [0, 0, 0], "radius": 0},
        expected=ExpectedOutcome.SUCCESS,  # Creates degenerate circle
        phase=TestPhase.PHASE_2_CREATE,
        description="Create circle with zero radius (creates degenerate)",
        intent="create a circle with zero radius",
        tags=["create", "circle", "edge-case"],
        learn_on_success=(
            "CIRCLE with radius 0 creates a degenerate (point-like) circle. "
            "Rhino allows this but it's essentially invisible. "
            "Use POINT instead for zero-radius locations."
        ),
    ),

    # SPHERE
    TestCase(
        id="create-008",
        tool="rhino_create",
        params={"type": "SPHERE", "center": [0, 0, 0], "radius": 5},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_2_CREATE,
        description="Create sphere at origin",
        intent="create a sphere with radius 5 at the origin",
        tags=["create", "sphere", "solid", "basic"],
        learn_on_success=(
            "To create a SPHERE: use rhino_create with {type: 'SPHERE', center: [x,y,z], radius: N}. "
            "Creates a closed Brep (solid). Type is 'Brep' in queries. "
            "Can add 'name' and 'layer' params for organization."
        ),
    ),
    TestCase(
        id="create-009",
        tool="rhino_create",
        params={"type": "SPHERE", "center": [0, 0, 0], "radius": 5, "color": [255, 0, 0]},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_2_CREATE,
        description="Create red sphere with color array",
        intent="create a red sphere using RGB array",
        tags=["create", "sphere", "color", "basic"],
        learn_on_success=(
            "To set object color: add 'color' param as [R, G, B] array (0-255 each). "
            "Example: color: [255, 0, 0] for red, [0, 255, 0] for green. "
            "Color is applied to object display, not material."
        ),
    ),
    TestCase(
        id="create-010",
        tool="rhino_create",
        params={"type": "SPHERE", "center": [0, 0, 0], "radius": 5, "color": {"r": 255, "g": 0, "b": 0}},
        expected=ExpectedOutcome.EITHER,  # Testing if this format works
        phase=TestPhase.PHASE_2_CREATE,
        description="Create sphere with color object",
        intent="create a red sphere using RGB object notation",
        tags=["create", "sphere", "color", "edge-case"],
        learn_on_success=(
            "Color as {r: N, g: N, b: N} object format also works. "
            "Both [R,G,B] array and {r,g,b} object are accepted."
        ),
        learn_on_failure=(
            "Color must be [R, G, B] array format. "
            "Object format {r, g, b} is not supported - use array instead."
        ),
    ),
    TestCase(
        id="create-011",
        tool="rhino_create",
        params={"type": "SPHERE", "center": [0, 0, 0], "radius": 5, "color": "red"},
        expected=ExpectedOutcome.SUCCESS,  # Actually works! Rhino parses color names
        phase=TestPhase.PHASE_2_CREATE,
        description="Create sphere with color string (Rhino parses names)",
        intent="create a red sphere using color name string",
        tags=["create", "sphere", "color"],
        learn_on_success=(
            "Color strings like 'red', 'blue', 'green' work! Rhino parses common color names. "
            "Supported: 'red', 'green', 'blue', 'yellow', 'cyan', 'magenta', 'white', 'black'. "
            "Use this for quick prototyping, [R,G,B] for precise colors."
        ),
    ),

    # BOX
    TestCase(
        id="create-012",
        tool="rhino_create",
        params={"type": "BOX", "origin": [0, 0, 0], "width": 10, "depth": 10, "height": 5},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_2_CREATE,
        description="Create box at origin",
        intent="create a box (rectangular solid) at the origin",
        tags=["create", "box", "solid", "basic"],
        learn_on_success=(
            "To create a BOX: use rhino_create with {type: 'BOX', origin: [x,y,z], width: N, depth: N, height: N}. "
            "Origin is corner, not center. Box extends in +X (width), +Y (depth), +Z (height). "
            "Creates closed Brep (solid). For centered box, offset origin by half dimensions."
        ),
    ),
    TestCase(
        id="create-013",
        tool="rhino_create",
        params={"type": "BOX", "origin": [0, 0, 0], "width": -10, "depth": 10, "height": 5},
        expected=ExpectedOutcome.EITHER,
        phase=TestPhase.PHASE_2_CREATE,
        description="Create box with negative width",
        intent="create a box with a negative dimension value",
        tags=["create", "box", "edge-case"],
        learn_on_success=(
            "BOX accepts negative dimensions - extends in negative direction. "
            "width: -10 creates box extending in -X direction from origin."
        ),
        learn_on_failure=(
            "BOX requires positive dimensions. Negative values cause failure. "
            "Use origin offset instead of negative dimensions."
        ),
    ),

    # CYLINDER
    TestCase(
        id="create-014",
        tool="rhino_create",
        params={"type": "CYLINDER", "center": [0, 0, 0], "radius": 5, "height": 10},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_2_CREATE,
        description="Create cylinder",
        intent="create a cylinder at the origin",
        tags=["create", "cylinder", "solid", "basic"],
        learn_on_success=(
            "To create a CYLINDER: use rhino_create with {type: 'CYLINDER', center: [x,y,z], radius: N, height: N}. "
            "Center is base center, extends in +Z direction. "
            "Creates closed Brep (solid). Use rhino_transform to rotate if needed."
        ),
    ),

    # CONE
    TestCase(
        id="create-015",
        tool="rhino_create",
        params={"type": "CONE", "center": [0, 0, 0], "radius": 5, "height": 10},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_2_CREATE,
        description="Create cone",
        intent="create a cone at the origin",
        tags=["create", "cone", "solid", "basic"],
        learn_on_success=(
            "To create a CONE: use rhino_create with {type: 'CONE', center: [x,y,z], radius: N, height: N}. "
            "Center is base center, tip at center + [0,0,height]. "
            "Creates closed Brep (solid). Radius is base radius."
        ),
    ),

    # POLYLINE
    TestCase(
        id="create-016",
        tool="rhino_create",
        params={"type": "POLYLINE", "points": [[0, 0, 0], [10, 0, 0], [10, 10, 0], [0, 10, 0]]},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_2_CREATE,
        description="Create polyline from points",
        intent="create a polyline connecting multiple points",
        tags=["create", "polyline", "curve", "basic"],
        learn_on_success=(
            "To create a POLYLINE: use rhino_create with {type: 'POLYLINE', points: [[x,y,z], [x,y,z], ...]}. "
            "Minimum 2 points required. Creates open curve connecting points in order. "
            "For closed shape, repeat first point at end or use RECTANGLE."
        ),
    ),
    TestCase(
        id="create-017",
        tool="rhino_create",
        params={"type": "POLYLINE", "points": [[0, 0, 0]]},
        expected=ExpectedOutcome.FAILURE,
        phase=TestPhase.PHASE_2_CREATE,
        description="Create polyline with single point",
        intent="create a polyline with only one point",
        tags=["create", "polyline", "invalid"],
        learn_on_failure=(
            "POLYLINE requires at least 2 points. "
            "Single point returns {success: false}. "
            "Use POINT for single locations."
        ),
    ),

    # RECTANGLE
    TestCase(
        id="create-018",
        tool="rhino_create",
        params={"type": "RECTANGLE", "origin": [0, 0, 0], "width": 10, "height": 5},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_2_CREATE,
        description="Create rectangle",
        intent="create a rectangular curve on the XY plane",
        tags=["create", "rectangle", "curve", "basic"],
        learn_on_success=(
            "To create a RECTANGLE: use rhino_create with {type: 'RECTANGLE', origin: [x,y,z], width: N, height: N}. "
            "Origin is corner. Creates closed polyline (curve) on XY plane. "
            "For 3D rectangular solid, use BOX instead."
        ),
    ),

    # ARC
    TestCase(
        id="create-019",
        tool="rhino_create",
        params={"type": "ARC", "center": [0, 0, 0], "radius": 5, "startAngle": 0, "endAngle": 90},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_2_CREATE,
        description="Create arc",
        intent="create a 90 degree arc curve",
        tags=["create", "arc", "curve", "basic"],
        learn_on_success=(
            "To create an ARC: use rhino_create with {type: 'ARC', center: [x,y,z], radius: N, startAngle: N, endAngle: N}. "
            "Angles in degrees. 0=+X axis, 90=+Y axis (counterclockwise). "
            "For full circle, use CIRCLE. Arc is on XY plane at center Z."
        ),
    ),

    # Named object
    TestCase(
        id="create-020",
        tool="rhino_create",
        params={"type": "SPHERE", "center": [0, 0, 0], "radius": 5, "name": "TestSphere"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_2_CREATE,
        description="Create named sphere",
        intent="create a sphere with a specific name for later reference",
        tags=["create", "sphere", "naming"],
        learn_on_success=(
            "To name objects: add 'name' param to any rhino_create call. "
            "Example: {type: 'SPHERE', center: [0,0,0], radius: 5, name: 'MySphere'}. "
            "Names appear in Rhino properties panel and can be used with rhino_select_by_name."
        ),
    ),

    # Object on layer
    TestCase(
        id="create-021",
        tool="rhino_create",
        params={"type": "SPHERE", "center": [0, 0, 0], "radius": 5, "layer": "Default"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_2_CREATE,
        description="Create sphere on specific layer",
        intent="create a sphere on a specific layer",
        tags=["create", "sphere", "layer"],
        learn_on_success=(
            "To place objects on a layer: add 'layer' param to any rhino_create call. "
            "Example: {type: 'SPHERE', ..., layer: 'MyLayer'}. "
            "Layer must exist. Use rhino_layer_create first if needed. "
            "Nested layers use '::' separator: 'Parent::Child'."
        ),
    ),
]


# =============================================================================
# PHASE 3: Layer Management
# =============================================================================

PHASE_3_TESTS = [
    TestCase(
        id="layer-001",
        tool="rhino_layer_create",
        params={"name": "TestLayer"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_3_LAYER,
        description="Create simple layer",
        intent="create new layer",
        tags=["layer", "create", "basic"],
        learn_on_success="rhino_layer_create requires 'name' param",
    ),
    TestCase(
        id="layer-002",
        tool="rhino_layer_create",
        params={"name": "ColoredLayer", "color": [255, 128, 0]},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_3_LAYER,
        description="Create layer with color",
        intent="create orange layer",
        tags=["layer", "create", "color"],
        learn_on_success="Layer color as [r, g, b] array",
    ),
    TestCase(
        id="layer-003",
        tool="rhino_layer_create",
        params={"name": "ChildLayer", "parent": "TestLayer"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_3_LAYER,
        description="Create nested layer using parent param",
        intent="create sublayer",
        tags=["layer", "create", "nested"],
        depends_on=["layer-001"],
        learn_on_success="Nested layers use 'parent' param, not 'Parent::Child' syntax",
    ),
    TestCase(
        id="layer-004",
        tool="rhino_layer_create",
        params={"name": "Parent::Child"},
        expected=ExpectedOutcome.FAILURE,
        phase=TestPhase.PHASE_3_LAYER,
        description="Create nested layer using :: syntax",
        intent="create sublayer with path syntax",
        tags=["layer", "create", "nested", "edge-case"],
        learn_on_failure="'Parent::Child' is rejected; use 'name' plus 'parent' or rhino_layer_create_batch",
    ),
    TestCase(
        id="layer-005",
        tool="rhino_layer_create_batch",
        params={
            "layers": [
                {"key": "A", "name": "A"},
                {"key": "A1", "name": "1", "parentKey": "A"},
                {"key": "A2", "name": "2", "parentKey": "A"},
            ]
        },
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_3_LAYER,
        description="Create nested layers atomically via batch API",
        intent="create a parent layer with multiple children efficiently",
        tags=["layer", "create", "nested", "batch"],
        learn_on_success="Use rhino_layer_create_batch with {key, name, parentKey} items for atomic hierarchy creation",
    ),
    TestCase(
        id="layer-006",
        tool="rhino_layer_visibility",
        params={"name": "TestLayer", "visible": False},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_3_LAYER,
        description="Hide layer",
        intent="hide layer",
        tags=["layer", "visibility"],
        depends_on=["layer-001"],
        learn_on_success="rhino_layer_visibility toggles layer visibility",
    ),
    TestCase(
        id="layer-007",
        tool="rhino_layer_lock",
        params={"name": "TestLayer", "locked": True},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_3_LAYER,
        description="Lock layer",
        intent="lock layer",
        tags=["layer", "lock"],
        depends_on=["layer-001"],
        learn_on_success="rhino_layer_lock toggles layer lock state",
    ),
    TestCase(
        id="layer-008",
        tool="rhino_layer_current",
        params={"name": "TestLayer"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_3_LAYER,
        description="Set current layer",
        intent="set current layer",
        tags=["layer", "current"],
        depends_on=["layer-001"],
        learn_on_success="rhino_layer_current sets the active layer",
    ),
    TestCase(
        id="layer-009",
        tool="rhino_layer_delete",
        params={"name": "ChildLayer"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_3_LAYER,
        description="Delete empty layer",
        intent="delete layer",
        tags=["layer", "delete"],
        depends_on=["layer-003"],
        learn_on_success="rhino_layer_delete removes empty layers",
    ),
]


# =============================================================================
# Phase 4: Selection Tools
# =============================================================================

PHASE_4_TESTS = [
    # Note: These tests depend on geometry from Phase 2 being present in the document
    TestCase(
        id="select-001",
        tool="rhino_selection",
        params={},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_4_SELECT,
        description="Get current selection (should be empty initially)",
        intent="query current selection",
        tags=["selection", "query", "basic"],
        learn_on_success=(
            "rhino_selection returns {count, objects[]} with currently selected objects. "
            "Call with no parameters. Returns empty list if nothing selected."
        ),
    ),
    TestCase(
        id="select-002",
        tool="rhino_select_all",
        params={},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_4_SELECT,
        description="Select all objects in document",
        intent="select all objects",
        tags=["selection", "all"],
        learn_on_success=(
            "rhino_select_all selects all visible, unlocked objects. "
            "No parameters needed. Returns {selectedCount: N}."
        ),
    ),
    TestCase(
        id="select-003",
        tool="rhino_selection",
        params={},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_4_SELECT,
        description="Verify objects are selected after select all",
        intent="verify selection state",
        tags=["selection", "query"],
        depends_on=["select-002"],
        learn_on_success="After rhino_select_all, rhino_selection.count should be > 0",
    ),
    TestCase(
        id="select-004",
        tool="rhino_select_none",
        params={},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_4_SELECT,
        description="Deselect all objects",
        intent="clear selection",
        tags=["selection", "deselect"],
        depends_on=["select-002"],
        learn_on_success=(
            "rhino_select_none clears the selection. "
            "No parameters needed. Returns {selectedCount: 0}."
        ),
    ),
    TestCase(
        id="select-005",
        tool="rhino_select_by_type",
        params={"type": "Brep"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_4_SELECT,
        description="Select all Brep (solid) objects",
        intent="select by geometry type",
        tags=["selection", "type", "brep"],
        learn_on_success=(
            "rhino_select_by_type with {type: 'Brep'} selects solid objects. "
            "Spheres, boxes, cylinders, cones are Breps. "
            "Valid types: Point, Curve, Brep, Mesh, Surface, Extrusion."
        ),
    ),
    TestCase(
        id="select-006",
        tool="rhino_select_by_type",
        params={"type": "Curve"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_4_SELECT,
        description="Select all Curve objects",
        intent="select curves",
        tags=["selection", "type", "curve"],
        learn_on_success=(
            "rhino_select_by_type with {type: 'Curve'} selects lines, circles, arcs, polylines. "
            "All curve-like geometry shares the 'Curve' type."
        ),
    ),
    TestCase(
        id="select-007",
        tool="rhino_select_by_type",
        params={"type": "Point"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_4_SELECT,
        description="Select all Point objects",
        intent="select points",
        tags=["selection", "type", "point"],
        learn_on_success="rhino_select_by_type with {type: 'Point'} selects point objects.",
    ),
    TestCase(
        id="select-008",
        tool="rhino_select_by_type",
        params={"type": "InvalidType"},
        expected=ExpectedOutcome.SUCCESS,  # Returns 0 selected, doesn't fail
        phase=TestPhase.PHASE_4_SELECT,
        description="Select by invalid type (should succeed with 0 selected)",
        intent="select with invalid type",
        tags=["selection", "type", "edge-case"],
        learn_on_success=(
            "Invalid type in rhino_select_by_type doesn't error - it selects nothing. "
            "Check selectedCount in response to verify objects were found."
        ),
    ),
    TestCase(
        id="select-009",
        tool="rhino_select_by_name",
        params={"namePattern": "TestSphere"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_4_SELECT,
        description="Select objects by exact name",
        intent="select by name",
        tags=["selection", "name"],
        learn_on_success=(
            "rhino_select_by_name with {namePattern: 'ExactName'} selects objects with that name. "
            "Only works if objects were created with 'name' parameter."
        ),
    ),
    TestCase(
        id="select-010",
        tool="rhino_select_by_name",
        params={"namePattern": "Test*"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_4_SELECT,
        description="Select objects by wildcard pattern",
        intent="select by pattern",
        tags=["selection", "name", "wildcard"],
        learn_on_success=(
            "rhino_select_by_name supports wildcards: * matches any chars, ? matches single char. "
            "Pattern 'Test*' matches 'TestSphere', 'TestBox', etc."
        ),
    ),
    TestCase(
        id="select-011",
        tool="rhino_select",
        params={"layer": "Default"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_4_SELECT,
        description="Select all objects on a specific layer",
        intent="select by layer",
        tags=["selection", "layer"],
        learn_on_success=(
            "rhino_select with {layer: 'LayerName'} selects all objects on that layer. "
            "Works with layer name or full path for nested layers."
        ),
    ),
    TestCase(
        id="select-012",
        tool="rhino_select_invert",
        params={},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_4_SELECT,
        description="Invert current selection",
        intent="invert selection",
        tags=["selection", "invert"],
        depends_on=["select-011"],
        learn_on_success=(
            "rhino_select_invert swaps selected/unselected objects. "
            "Previously selected become unselected, and vice versa."
        ),
    ),
    TestCase(
        id="select-013",
        tool="rhino_select",
        params={"ids": [], "clear": True},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_4_SELECT,
        description="Select with empty ID list clears selection",
        intent="clear selection with empty ids",
        tags=["selection", "clear", "edge-case"],
        learn_on_success=(
            "rhino_select with {ids: [], clear: true} clears selection. "
            "This is equivalent to rhino_select_none."
        ),
    ),
    TestCase(
        id="select-014",
        tool="rhino_select",
        params={"ids": ["00000000-0000-0000-0000-000000000000"]},
        expected=ExpectedOutcome.SUCCESS,  # Succeeds but selects nothing
        phase=TestPhase.PHASE_4_SELECT,
        description="Select with non-existent GUID",
        intent="select invalid id",
        tags=["selection", "id", "edge-case"],
        learn_on_success=(
            "rhino_select with non-existent GUID doesn't error - selectedCount is 0. "
            "Always check selectedCount to verify objects were found."
        ),
    ),
    TestCase(
        id="select-015",
        tool="rhino_select_by_type",
        params={"type": "Curve", "clear": False},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_4_SELECT,
        description="Add to selection with clear=false",
        intent="add to selection",
        tags=["selection", "add", "clear"],
        depends_on=["select-007"],  # After selecting points
        learn_on_success=(
            "Set clear: false to ADD to existing selection instead of replacing. "
            "Default is clear: true which replaces selection."
        ),
    ),
    TestCase(
        id="select-016",
        tool="rhino_deselect",
        params={"ids": ["00000000-0000-0000-0000-000000000000"]},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_4_SELECT,
        description="Deselect specific objects by ID",
        intent="deselect specific objects",
        tags=["selection", "deselect", "id"],
        learn_on_success=(
            "rhino_deselect with {ids: ['guid1', 'guid2']} removes specific objects from selection. "
            "Does not affect other selected objects. Returns {deselectedCount: N}."
        ),
    ),
]


# =============================================================================
# Phase 5: Transform Tools
# =============================================================================

PHASE_5_TESTS = [
    # Note: These tests require objects to exist. We'll create test objects first.
    # In practice, tests should be run after Phase 2 creates geometry.

    # MOVE operations
    TestCase(
        id="transform-001",
        tool="rhino_create",
        params={"type": "SPHERE", "center": [0, 0, 0], "radius": 5, "name": "TransformTestSphere"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_5_TRANSFORM,
        description="Create sphere for transform tests",
        intent="create object for transform testing",
        tags=["transform", "setup"],
        learn_on_success="Create named objects for transform tests to track them by name",
    ),
    TestCase(
        id="transform-002",
        tool="rhino_transform",
        params={"ids": ["PLACEHOLDER"], "operation": "move", "vector": [10, 0, 0]},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_5_TRANSFORM,
        description="Move object along X axis",
        intent="move object",
        tags=["transform", "move", "basic"],
        depends_on=["transform-001"],
        learn_on_success=(
            "rhino_transform with operation: 'move' and vector: [x, y, z] moves objects. "
            "Vector is relative displacement, not absolute position. "
            "Example: {ids: ['guid'], operation: 'move', vector: [10, 0, 0]} moves 10 units in +X."
        ),
    ),
    TestCase(
        id="transform-003",
        tool="rhino_transform",
        params={"ids": ["PLACEHOLDER"], "operation": "move", "vector": [0, 0, 0]},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_5_TRANSFORM,
        description="Move with zero vector (no-op)",
        intent="move object by zero distance",
        tags=["transform", "move", "edge-case"],
        depends_on=["transform-001"],
        learn_on_success=(
            "Move with zero vector [0,0,0] succeeds but doesn't change position. "
            "This is a valid no-op transform."
        ),
    ),

    # ROTATE operations
    TestCase(
        id="transform-004",
        tool="rhino_transform",
        params={
            "ids": ["PLACEHOLDER"],
            "operation": "rotate",
            "angle": 45,
            "axis": [0, 0, 1],
            "center": [0, 0, 0]
        },
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_5_TRANSFORM,
        description="Rotate object 45 degrees around Z axis",
        intent="rotate object",
        tags=["transform", "rotate", "basic"],
        depends_on=["transform-001"],
        learn_on_success=(
            "rhino_transform with operation: 'rotate' requires angle, axis, and center. "
            "Angle in degrees. Axis [0,0,1] = Z axis (top view rotation). "
            "Center is the rotation pivot point. "
            "Example: {operation: 'rotate', angle: 90, axis: [0,0,1], center: [0,0,0]}"
        ),
    ),
    TestCase(
        id="transform-005",
        tool="rhino_transform",
        params={
            "ids": ["PLACEHOLDER"],
            "operation": "rotate",
            "angle": 90,
            "axis": [1, 0, 0],
            "center": [0, 0, 0]
        },
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_5_TRANSFORM,
        description="Rotate object 90 degrees around X axis",
        intent="rotate object around X axis",
        tags=["transform", "rotate"],
        depends_on=["transform-001"],
        learn_on_success=(
            "Axis [1,0,0] = X axis rotation (front view rotation). "
            "Axis [0,1,0] = Y axis rotation (side view rotation). "
            "Axis [0,0,1] = Z axis rotation (top view rotation)."
        ),
    ),
    TestCase(
        id="transform-006",
        tool="rhino_transform",
        params={
            "ids": ["PLACEHOLDER"],
            "operation": "rotate",
            "angle": 360,
            "axis": [0, 0, 1],
            "center": [0, 0, 0]
        },
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_5_TRANSFORM,
        description="Rotate object 360 degrees (full rotation)",
        intent="rotate object full circle",
        tags=["transform", "rotate", "edge-case"],
        depends_on=["transform-001"],
        learn_on_success="360 degree rotation returns object to original orientation (no-op visually).",
    ),

    # SCALE operations
    TestCase(
        id="transform-007",
        tool="rhino_transform",
        params={
            "ids": ["PLACEHOLDER"],
            "operation": "scale",
            "factor": 2,
            "center": [0, 0, 0]
        },
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_5_TRANSFORM,
        description="Scale object by factor of 2",
        intent="scale object larger",
        tags=["transform", "scale", "basic"],
        depends_on=["transform-001"],
        learn_on_success=(
            "rhino_transform with operation: 'scale' requires factor and center. "
            "Factor > 1 enlarges, factor < 1 shrinks. Factor = 1 is no-op. "
            "Center is the scale origin - object moves away/toward center. "
            "Example: {operation: 'scale', factor: 2, center: [0,0,0]} doubles size."
        ),
    ),
    TestCase(
        id="transform-008",
        tool="rhino_transform",
        params={
            "ids": ["PLACEHOLDER"],
            "operation": "scale",
            "factor": 0.5,
            "center": [0, 0, 0]
        },
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_5_TRANSFORM,
        description="Scale object by factor of 0.5 (shrink)",
        intent="scale object smaller",
        tags=["transform", "scale"],
        depends_on=["transform-001"],
        learn_on_success="Scale factor 0.5 halves the object size. Works for any positive factor.",
    ),
    TestCase(
        id="transform-009",
        tool="rhino_transform",
        params={
            "ids": ["PLACEHOLDER"],
            "operation": "scale",
            "factor": 0,
            "center": [0, 0, 0]
        },
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_5_TRANSFORM,
        description="Scale by zero (degenerate)",
        intent="scale object to zero size",
        tags=["transform", "scale", "edge-case"],
        depends_on=["transform-001"],
        learn_on_success=(
            "Scale factor 0 succeeds but collapses object to a point at center. "
            "Creates degenerate geometry - avoid unless intentional."
        ),
    ),
    TestCase(
        id="transform-010",
        tool="rhino_transform",
        params={
            "ids": ["PLACEHOLDER"],
            "operation": "scale",
            "factor": -1,
            "center": [0, 0, 0]
        },
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_5_TRANSFORM,
        description="Scale by negative factor (mirror + scale)",
        intent="scale object with negative factor",
        tags=["transform", "scale", "edge-case"],
        depends_on=["transform-001"],
        learn_on_success=(
            "Negative scale factor succeeds and mirrors through center point. "
            "factor=-1 is equivalent to point mirror. factor=-2 mirrors and doubles size."
        ),
    ),

    # MIRROR operations
    TestCase(
        id="transform-011",
        tool="rhino_transform",
        params={
            "ids": ["PLACEHOLDER"],
            "operation": "mirror",
            "planeOrigin": [0, 0, 0],
            "planeNormal": [1, 0, 0]
        },
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_5_TRANSFORM,
        description="Mirror object across YZ plane",
        intent="mirror object",
        tags=["transform", "mirror", "basic"],
        depends_on=["transform-001"],
        learn_on_success=(
            "rhino_transform with operation: 'mirror' requires planeOrigin and planeNormal. "
            "PlaneNormal [1,0,0] = YZ plane (mirror in X). "
            "PlaneNormal [0,1,0] = XZ plane (mirror in Y). "
            "PlaneNormal [0,0,1] = XY plane (mirror in Z). "
            "PlaneOrigin is a point on the mirror plane."
        ),
    ),
    TestCase(
        id="transform-012",
        tool="rhino_transform",
        params={
            "ids": ["PLACEHOLDER"],
            "operation": "mirror",
            "planeOrigin": [10, 0, 0],
            "planeNormal": [1, 0, 0]
        },
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_5_TRANSFORM,
        description="Mirror with offset plane origin",
        intent="mirror object across offset plane",
        tags=["transform", "mirror"],
        depends_on=["transform-001"],
        learn_on_success=(
            "PlaneOrigin offsets the mirror plane. "
            "planeOrigin: [10,0,0] with normal [1,0,0] creates YZ plane at X=10."
        ),
    ),

    # COPY operations
    TestCase(
        id="transform-013",
        tool="rhino_copy",
        params={"ids": ["PLACEHOLDER"]},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_5_TRANSFORM,
        description="Copy object in place",
        intent="copy object",
        tags=["transform", "copy", "basic"],
        depends_on=["transform-001"],
        learn_on_success=(
            "rhino_copy duplicates objects. Without offset, copy is at same location. "
            "Returns {ids: ['new_guid1', ...]} with new object IDs."
        ),
    ),
    TestCase(
        id="transform-014",
        tool="rhino_copy",
        params={"ids": ["PLACEHOLDER"], "offset": [20, 0, 0]},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_5_TRANSFORM,
        description="Copy object with offset",
        intent="copy object to new location",
        tags=["transform", "copy"],
        depends_on=["transform-001"],
        learn_on_success=(
            "rhino_copy with offset: [x,y,z] copies and moves in one operation. "
            "Offset is relative displacement from original position. "
            "Example: {ids: ['guid'], offset: [20, 0, 0]} copies 20 units in +X."
        ),
    ),

    # DELETE operations
    TestCase(
        id="transform-015",
        tool="rhino_create",
        params={"type": "POINT", "point": [100, 100, 100], "name": "DeleteTestPoint"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_5_TRANSFORM,
        description="Create point for delete test",
        intent="create object to delete",
        tags=["transform", "delete", "setup"],
        learn_on_success="Create named objects for delete tests",
    ),
    TestCase(
        id="transform-016",
        tool="rhino_delete",
        params={"ids": ["PLACEHOLDER"]},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_5_TRANSFORM,
        description="Delete object by ID",
        intent="delete object",
        tags=["transform", "delete", "basic"],
        depends_on=["transform-015"],
        learn_on_success=(
            "rhino_delete removes objects by ID. "
            "Pass {ids: ['guid1', 'guid2', ...]} to delete multiple objects. "
            "Returns {deleted: N} with count of deleted objects. "
            "Deletion is permanent (use Undo in Rhino to recover)."
        ),
    ),
    TestCase(
        id="transform-017",
        tool="rhino_delete",
        params={"ids": ["00000000-0000-0000-0000-000000000000"]},
        expected=ExpectedOutcome.FAILURE,  # Returns error with failedIds
        phase=TestPhase.PHASE_5_TRANSFORM,
        description="Delete non-existent object",
        intent="delete invalid id",
        tags=["transform", "delete", "edge-case"],
        learn_on_failure=(
            "rhino_delete with non-existent GUID returns error with failedIds list. "
            "Check deletedCount vs requestedCount to detect partial failures."
        ),
    ),
    TestCase(
        id="transform-018",
        tool="rhino_delete",
        params={"ids": []},
        expected=ExpectedOutcome.FAILURE,  # Returns "No valid IDs provided"
        phase=TestPhase.PHASE_5_TRANSFORM,
        description="Delete with empty ID list",
        intent="delete nothing",
        tags=["transform", "delete", "edge-case"],
        learn_on_failure="rhino_delete with empty ids list returns error 'No valid IDs provided'.",
    ),

    # Multiple object transforms
    TestCase(
        id="transform-019",
        tool="rhino_create",
        params={"type": "BOX", "origin": [50, 0, 0], "width": 5, "depth": 5, "height": 5, "name": "TransformTestBox"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_5_TRANSFORM,
        description="Create second object for multi-object transform",
        intent="create box for transform testing",
        tags=["transform", "setup"],
        learn_on_success="Create multiple named objects to test multi-object transforms",
    ),
    TestCase(
        id="transform-020",
        tool="rhino_transform",
        params={"ids": ["PLACEHOLDER1", "PLACEHOLDER2"], "operation": "move", "vector": [0, 10, 0]},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_5_TRANSFORM,
        description="Move multiple objects at once",
        intent="move multiple objects",
        tags=["transform", "move", "multiple"],
        depends_on=["transform-001", "transform-019"],
        learn_on_success=(
            "All transform operations accept multiple IDs in the ids array. "
            "All specified objects are transformed together. "
            "Example: {ids: ['guid1', 'guid2'], operation: 'move', vector: [0,10,0]}"
        ),
    ),
]


# =============================================================================
# Phase 6: Advanced Geometry (Boolean, Loft, Sweep, Extrude)
# =============================================================================

PHASE_6_TESTS = [
    # Setup: Create solids for boolean operations
    TestCase(
        id="advanced-001",
        tool="rhino_create",
        params={"type": "BOX", "origin": [0, 0, 0], "width": 10, "depth": 10, "height": 10, "name": "BooleanBox1"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_6_ADVANCED,
        description="Create first box for boolean operations",
        intent="create solid for boolean testing",
        tags=["advanced", "boolean", "setup"],
        learn_on_success="Create named solids (Brep objects) for boolean operations",
    ),
    TestCase(
        id="advanced-002",
        tool="rhino_create",
        params={"type": "BOX", "origin": [5, 5, 5], "width": 10, "depth": 10, "height": 10, "name": "BooleanBox2"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_6_ADVANCED,
        description="Create second overlapping box for boolean operations",
        intent="create overlapping solid for boolean",
        tags=["advanced", "boolean", "setup"],
        learn_on_success="Position solids to overlap for boolean union/intersection/difference",
    ),

    # BOOLEAN UNION
    TestCase(
        id="advanced-003",
        tool="rhino_boolean",
        params={"operation": "union", "ids": ["PLACEHOLDER1", "PLACEHOLDER2"]},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_6_ADVANCED,
        description="Boolean union of two boxes",
        intent="combine two solids into one",
        tags=["advanced", "boolean", "union"],
        depends_on=["advanced-001", "advanced-002"],
        learn_on_success=(
            "rhino_boolean with operation: 'union' combines multiple solids into one. "
            "Pass {operation: 'union', ids: ['guid1', 'guid2', ...]}. "
            "Input objects are deleted by default. Set deleteInputs: false to keep them."
        ),
    ),

    # Create new solids for difference test
    TestCase(
        id="advanced-004",
        tool="rhino_create",
        params={"type": "BOX", "origin": [30, 0, 0], "width": 20, "depth": 20, "height": 20, "name": "DiffTarget"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_6_ADVANCED,
        description="Create target box for boolean difference",
        intent="create target solid for subtraction",
        tags=["advanced", "boolean", "setup"],
        learn_on_success="Boolean difference requires a target (solid to cut from) and tools (solids to subtract)",
    ),
    TestCase(
        id="advanced-005",
        tool="rhino_create",
        params={"type": "SPHERE", "center": [40, 10, 10], "radius": 8, "name": "DiffTool"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_6_ADVANCED,
        description="Create sphere tool for boolean difference",
        intent="create tool solid for subtraction",
        tags=["advanced", "boolean", "setup"],
        learn_on_success="Sphere positioned inside/overlapping box will create a spherical void",
    ),

    # BOOLEAN DIFFERENCE
    TestCase(
        id="advanced-006",
        tool="rhino_boolean",
        params={"operation": "difference", "targetId": "PLACEHOLDER1", "toolIds": ["PLACEHOLDER2"]},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_6_ADVANCED,
        description="Boolean difference (subtract sphere from box)",
        intent="cut solid from another solid",
        tags=["advanced", "boolean", "difference"],
        depends_on=["advanced-004", "advanced-005"],
        learn_on_success=(
            "rhino_boolean with operation: 'difference' subtracts toolIds from targetId. "
            "Pass {operation: 'difference', targetId: 'target_guid', toolIds: ['tool_guid1', ...]}. "
            "Note: difference uses targetId + toolIds, NOT ids array."
        ),
    ),

    # Create solids for intersection test
    TestCase(
        id="advanced-007",
        tool="rhino_create",
        params={"type": "BOX", "origin": [60, 0, 0], "width": 15, "depth": 15, "height": 15, "name": "IntersectBox1"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_6_ADVANCED,
        description="Create first box for intersection",
        intent="create solid for intersection test",
        tags=["advanced", "boolean", "setup"],
        learn_on_success="Boolean intersection finds the common volume between solids",
    ),
    TestCase(
        id="advanced-008",
        tool="rhino_create",
        params={"type": "SPHERE", "center": [67.5, 7.5, 7.5], "radius": 10, "name": "IntersectSphere"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_6_ADVANCED,
        description="Create sphere overlapping box for intersection",
        intent="create overlapping solid for intersection",
        tags=["advanced", "boolean", "setup"],
        learn_on_success="Position solids to overlap - intersection returns only the overlapping volume",
    ),

    # BOOLEAN INTERSECTION
    TestCase(
        id="advanced-009",
        tool="rhino_boolean",
        params={"operation": "intersection", "ids": ["PLACEHOLDER1", "PLACEHOLDER2"]},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_6_ADVANCED,
        description="Boolean intersection of box and sphere",
        intent="find common volume of two solids",
        tags=["advanced", "boolean", "intersection"],
        depends_on=["advanced-007", "advanced-008"],
        learn_on_success=(
            "rhino_boolean with operation: 'intersection' returns only the overlapping volume. "
            "Pass {operation: 'intersection', ids: ['guid1', 'guid2']}. "
            "Useful for finding where two solids meet."
        ),
    ),

    # Boolean edge cases
    TestCase(
        id="advanced-010",
        tool="rhino_create",
        params={"type": "BOX", "origin": [100, 0, 0], "width": 10, "depth": 10, "height": 10, "name": "NoOverlapBox1"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_6_ADVANCED,
        description="Create first non-overlapping box",
        intent="create non-overlapping solid",
        tags=["advanced", "boolean", "setup", "edge-case"],
        learn_on_success="Non-overlapping solids test boolean edge cases",
    ),
    TestCase(
        id="advanced-011",
        tool="rhino_create",
        params={"type": "BOX", "origin": [120, 0, 0], "width": 10, "depth": 10, "height": 10, "name": "NoOverlapBox2"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_6_ADVANCED,
        description="Create second non-overlapping box",
        intent="create non-overlapping solid",
        tags=["advanced", "boolean", "setup", "edge-case"],
        learn_on_success="Boxes separated by gap to test no-overlap boolean",
    ),
    TestCase(
        id="advanced-012",
        tool="rhino_boolean",
        params={"operation": "intersection", "ids": ["PLACEHOLDER1", "PLACEHOLDER2"]},
        expected=ExpectedOutcome.EITHER,
        phase=TestPhase.PHASE_6_ADVANCED,
        description="Boolean intersection of non-overlapping boxes",
        intent="intersect non-overlapping solids",
        tags=["advanced", "boolean", "intersection", "edge-case"],
        depends_on=["advanced-010", "advanced-011"],
        learn_on_success="Intersection of non-overlapping solids may return empty/null or fail",
        learn_on_failure="Boolean intersection fails when solids don't overlap - check geometry first",
    ),

    # EXTRUDE - Setup curves
    TestCase(
        id="advanced-013",
        tool="rhino_create",
        params={"type": "CIRCLE", "center": [0, 50, 0], "radius": 5, "name": "ExtrudeCircle"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_6_ADVANCED,
        description="Create circle for extrusion",
        intent="create closed curve for extrusion",
        tags=["advanced", "extrude", "setup"],
        learn_on_success="Create closed curves (circles, rectangles) for solid extrusions",
    ),

    # EXTRUDE with distance
    TestCase(
        id="advanced-014",
        tool="rhino_extrude",
        params={"curveId": "PLACEHOLDER", "distance": 20},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_6_ADVANCED,
        description="Extrude circle into cylinder",
        intent="extrude closed curve into solid",
        tags=["advanced", "extrude", "basic"],
        depends_on=["advanced-013"],
        learn_on_success=(
            "rhino_extrude with {curveId: 'guid', distance: N} extrudes curve by distance in Z direction. "
            "Closed curves create capped solids by default (set cap: false to leave open). "
            "Distance is vertical extrusion height."
        ),
    ),

    # EXTRUDE with direction
    TestCase(
        id="advanced-015",
        tool="rhino_create",
        params={"type": "RECTANGLE", "origin": [20, 50, 0], "width": 10, "height": 8, "name": "ExtrudeRect"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_6_ADVANCED,
        description="Create rectangle for directional extrusion",
        intent="create rectangle for extrusion",
        tags=["advanced", "extrude", "setup"],
        learn_on_success="Rectangles extrude into boxes",
    ),
    TestCase(
        id="advanced-016",
        tool="rhino_extrude",
        params={"curveId": "PLACEHOLDER", "direction": [0, 0, 1], "distance": 15},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_6_ADVANCED,
        description="Extrude rectangle with explicit direction",
        intent="extrude curve in specified direction",
        tags=["advanced", "extrude"],
        depends_on=["advanced-015"],
        learn_on_success=(
            "rhino_extrude with direction: [x, y, z] specifies extrusion vector. "
            "direction: [0, 0, 1] extrudes in +Z. direction: [1, 0, 0] extrudes in +X. "
            "Distance scales the direction vector."
        ),
    ),

    # EXTRUDE open curve
    TestCase(
        id="advanced-017",
        tool="rhino_create",
        params={"type": "LINE", "start": [40, 50, 0], "end": [60, 55, 0], "name": "ExtrudeLine"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_6_ADVANCED,
        description="Create open line for surface extrusion",
        intent="create open curve for surface extrusion",
        tags=["advanced", "extrude", "setup"],
        learn_on_success="Open curves extrude into surfaces, not solids",
    ),
    TestCase(
        id="advanced-018",
        tool="rhino_extrude",
        params={"curveId": "PLACEHOLDER", "distance": 10, "cap": False},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_6_ADVANCED,
        description="Extrude open line into surface",
        intent="extrude open curve into surface",
        tags=["advanced", "extrude", "surface"],
        depends_on=["advanced-017"],
        learn_on_success=(
            "Extruding open curves creates surfaces, not solids. "
            "The cap parameter is ignored for open curves. "
            "Result is a planar surface extending from the curve."
        ),
    ),

    # LOFT - Create curves at different heights
    TestCase(
        id="advanced-019",
        tool="rhino_create",
        params={"type": "CIRCLE", "center": [0, 100, 0], "radius": 10, "name": "LoftCircle1"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_6_ADVANCED,
        description="Create first circle for loft (bottom)",
        intent="create loft profile curve",
        tags=["advanced", "loft", "setup"],
        learn_on_success="Loft requires 2+ profile curves at different positions",
    ),
    TestCase(
        id="advanced-020",
        tool="rhino_create",
        params={"type": "CIRCLE", "center": [0, 100, 15], "radius": 6, "name": "LoftCircle2"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_6_ADVANCED,
        description="Create second circle for loft (middle)",
        intent="create loft profile curve",
        tags=["advanced", "loft", "setup"],
        learn_on_success="Multiple circles at different Z heights create tapered loft",
    ),
    TestCase(
        id="advanced-021",
        tool="rhino_create",
        params={"type": "CIRCLE", "center": [0, 100, 30], "radius": 8, "name": "LoftCircle3"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_6_ADVANCED,
        description="Create third circle for loft (top)",
        intent="create loft profile curve",
        tags=["advanced", "loft", "setup"],
        learn_on_success="Three or more curves allow complex loft shapes",
    ),

    # LOFT operation
    TestCase(
        id="advanced-022",
        tool="rhino_loft",
        params={"curveIds": ["PLACEHOLDER1", "PLACEHOLDER2", "PLACEHOLDER3"]},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_6_ADVANCED,
        description="Loft through three circles",
        intent="create lofted surface through curves",
        tags=["advanced", "loft", "basic"],
        depends_on=["advanced-019", "advanced-020", "advanced-021"],
        learn_on_success=(
            "rhino_loft with {curveIds: ['guid1', 'guid2', ...]} creates surface through curves. "
            "Curves must be ordered from start to end. "
            "Closed curves (circles) create closed surfaces. "
            "Use closed: true for periodic loft (loops back to first curve)."
        ),
    ),

    # LOFT with closed parameter
    TestCase(
        id="advanced-023",
        tool="rhino_create",
        params={"type": "CIRCLE", "center": [30, 100, 0], "radius": 5, "name": "ClosedLoftCircle1"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_6_ADVANCED,
        description="Create first circle for closed loft",
        intent="create loft profile",
        tags=["advanced", "loft", "setup"],
        learn_on_success="Closed loft creates a torus-like shape connecting end to start",
    ),
    TestCase(
        id="advanced-024",
        tool="rhino_create",
        params={"type": "CIRCLE", "center": [40, 100, 10], "radius": 5, "name": "ClosedLoftCircle2"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_6_ADVANCED,
        description="Create second circle for closed loft",
        intent="create loft profile",
        tags=["advanced", "loft", "setup"],
        learn_on_success="Position circles in arc for closed loft loop",
    ),
    TestCase(
        id="advanced-025",
        tool="rhino_create",
        params={"type": "CIRCLE", "center": [30, 100, 20], "radius": 5, "name": "ClosedLoftCircle3"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_6_ADVANCED,
        description="Create third circle for closed loft",
        intent="create loft profile",
        tags=["advanced", "loft", "setup"],
        learn_on_success="Third point creates curved closed loft path",
    ),
    TestCase(
        id="advanced-026",
        tool="rhino_loft",
        params={"curveIds": ["PLACEHOLDER1", "PLACEHOLDER2", "PLACEHOLDER3"], "closed": True},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_6_ADVANCED,
        description="Create closed loft (loops back)",
        intent="create periodic loft surface",
        tags=["advanced", "loft", "closed"],
        depends_on=["advanced-023", "advanced-024", "advanced-025"],
        learn_on_success=(
            "rhino_loft with closed: true creates periodic surface that connects last curve back to first. "
            "Creates a continuous loop surface. "
            "Useful for creating ring/torus shapes."
        ),
    ),

    # SWEEP - Create rail and profile curves
    TestCase(
        id="advanced-027",
        tool="rhino_create",
        params={"type": "ARC", "center": [60, 100, 0], "radius": 20, "startAngle": 0, "endAngle": 180, "name": "SweepRail"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_6_ADVANCED,
        description="Create arc rail for sweep",
        intent="create sweep rail curve",
        tags=["advanced", "sweep", "setup"],
        learn_on_success="Sweep rail defines the path the profile follows",
    ),
    TestCase(
        id="advanced-028",
        tool="rhino_create",
        params={"type": "CIRCLE", "center": [80, 100, 0], "radius": 3, "name": "SweepProfile"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_6_ADVANCED,
        description="Create circle profile for sweep",
        intent="create sweep profile curve",
        tags=["advanced", "sweep", "setup"],
        learn_on_success="Sweep profile is the shape that travels along the rail",
    ),

    # SWEEP operation
    TestCase(
        id="advanced-029",
        tool="rhino_sweep",
        params={"railId": "PLACEHOLDER_RAIL", "profileIds": ["PLACEHOLDER_PROFILE"]},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_6_ADVANCED,
        description="Sweep circle along arc rail",
        intent="create swept surface",
        tags=["advanced", "sweep", "basic"],
        depends_on=["advanced-027", "advanced-028"],
        learn_on_success=(
            "rhino_sweep with {railId: 'rail_guid', profileIds: ['profile_guid']} sweeps profile along rail. "
            "Profile should be at or near the start of the rail. "
            "Closed profiles create closed surfaces (pipes). "
            "Multiple profiles can morph shape along the rail."
        ),
    ),

    # SWEEP with multiple profiles
    TestCase(
        id="advanced-030",
        tool="rhino_create",
        params={"type": "LINE", "start": [100, 100, 0], "end": [100, 100, 30], "name": "SweepRail2"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_6_ADVANCED,
        description="Create vertical line rail for multi-profile sweep",
        intent="create sweep rail",
        tags=["advanced", "sweep", "setup"],
        learn_on_success="Straight rail with multiple profiles creates morphing shape",
    ),
    TestCase(
        id="advanced-031",
        tool="rhino_create",
        params={"type": "CIRCLE", "center": [100, 100, 0], "radius": 8, "name": "SweepProfileStart"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_6_ADVANCED,
        description="Create large circle at start",
        intent="create sweep start profile",
        tags=["advanced", "sweep", "setup"],
        learn_on_success="Larger profile at start, smaller at end creates tapered sweep",
    ),
    TestCase(
        id="advanced-032",
        tool="rhino_create",
        params={"type": "CIRCLE", "center": [100, 100, 30], "radius": 4, "name": "SweepProfileEnd"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_6_ADVANCED,
        description="Create small circle at end",
        intent="create sweep end profile",
        tags=["advanced", "sweep", "setup"],
        learn_on_success="Profile at end of rail defines final shape",
    ),
    TestCase(
        id="advanced-033",
        tool="rhino_sweep",
        params={"railId": "PLACEHOLDER_RAIL", "profileIds": ["PLACEHOLDER_START", "PLACEHOLDER_END"]},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_6_ADVANCED,
        description="Sweep with two profiles (morphing)",
        intent="create morphing swept surface",
        tags=["advanced", "sweep", "multi-profile"],
        depends_on=["advanced-030", "advanced-031", "advanced-032"],
        learn_on_success=(
            "rhino_sweep with multiple profileIds morphs between profiles along the rail. "
            "Profiles should be positioned at or near their rail locations. "
            "Creates smooth transition between shapes."
        ),
    ),

    # Edge case: Boolean with single solid
    TestCase(
        id="advanced-034",
        tool="rhino_create",
        params={"type": "SPHERE", "center": [150, 0, 0], "radius": 10, "name": "SingleSolid"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_6_ADVANCED,
        description="Create single solid for single-object boolean test",
        intent="create solid for edge case test",
        tags=["advanced", "boolean", "edge-case"],
        learn_on_success="Test boolean operations with insufficient operands",
    ),
    TestCase(
        id="advanced-035",
        tool="rhino_boolean",
        params={"operation": "union", "ids": ["PLACEHOLDER"]},
        expected=ExpectedOutcome.EITHER,
        phase=TestPhase.PHASE_6_ADVANCED,
        description="Boolean union with single object",
        intent="test boolean with one operand",
        tags=["advanced", "boolean", "edge-case"],
        depends_on=["advanced-034"],
        learn_on_success="Union of single object may succeed (returns same object) or fail",
        learn_on_failure="Boolean union requires at least 2 objects - provide multiple ids",
    ),

    # Edge case: Loft with only 2 curves
    TestCase(
        id="advanced-036",
        tool="rhino_create",
        params={"type": "CIRCLE", "center": [150, 50, 0], "radius": 5, "name": "TwoLoftCircle1"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_6_ADVANCED,
        description="Create first circle for 2-curve loft",
        intent="create loft profile",
        tags=["advanced", "loft", "setup"],
        learn_on_success="Loft with 2 curves is the minimum - creates simple ruled surface",
    ),
    TestCase(
        id="advanced-037",
        tool="rhino_create",
        params={"type": "RECTANGLE", "origin": [145, 45, 20], "width": 10, "height": 10, "name": "TwoLoftRect"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_6_ADVANCED,
        description="Create rectangle for mixed-shape loft",
        intent="create loft profile with different shape",
        tags=["advanced", "loft", "setup"],
        learn_on_success="Lofting between different curve shapes (circle to rectangle) creates morphing surface",
    ),
    TestCase(
        id="advanced-038",
        tool="rhino_loft",
        params={"curveIds": ["PLACEHOLDER1", "PLACEHOLDER2"]},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_6_ADVANCED,
        description="Loft between circle and rectangle",
        intent="loft between different shapes",
        tags=["advanced", "loft", "morph"],
        depends_on=["advanced-036", "advanced-037"],
        learn_on_success=(
            "Lofting between different closed shapes morphs smoothly between them. "
            "Circle to rectangle creates gradual corner transition. "
            "Both curves must be closed for closed loft surface."
        ),
    ),
]


# =============================================================================
# PHASE 7: Measurement Tools
# =============================================================================

PHASE_7_TESTS = [
    # -------------------------------------------------------------------------
    # Setup: Create geometry for measurement tests
    # -------------------------------------------------------------------------
    TestCase(
        id="measure-001",
        tool="rhino_create",
        params={"type": "BOX", "origin": [200, 0, 0], "width": 10, "depth": 10, "height": 10, "name": "MeasureBox"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_7_MEASURE,
        description="Create box for measurement tests",
        intent="create geometry to measure",
        tags=["measure", "setup"],
        learn_on_success="Create 10x10x10 box for measurement testing",
    ),
    TestCase(
        id="measure-002",
        tool="rhino_create",
        params={"type": "SPHERE", "center": [220, 0, 0], "radius": 5, "name": "MeasureSphere"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_7_MEASURE,
        description="Create sphere for measurement tests",
        intent="create sphere to measure",
        tags=["measure", "setup"],
        learn_on_success="Create sphere with radius 5 for measurement testing",
    ),
    TestCase(
        id="measure-003",
        tool="rhino_create",
        params={"type": "LINE", "start": [240, 0, 0], "end": [260, 0, 0], "name": "MeasureLine"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_7_MEASURE,
        description="Create line for length measurement",
        intent="create line to measure length",
        tags=["measure", "setup"],
        learn_on_success="Create 20-unit line for length measurement",
    ),
    TestCase(
        id="measure-004",
        tool="rhino_create",
        params={"type": "CIRCLE", "center": [280, 0, 0], "radius": 10, "name": "MeasureCircle"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_7_MEASURE,
        description="Create circle for length measurement",
        intent="create circle curve to measure",
        tags=["measure", "setup"],
        learn_on_success="Create circle for circumference measurement (2*pi*r)",
    ),
    TestCase(
        id="measure-005",
        tool="rhino_create",
        params={"type": "CYLINDER", "center": [300, 0, 0], "radius": 5, "height": 20, "name": "MeasureCylinder"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_7_MEASURE,
        description="Create cylinder for volume measurement",
        intent="create cylinder to measure",
        tags=["measure", "setup"],
        learn_on_success="Create cylinder for volume measurement (pi*r^2*h)",
    ),

    # -------------------------------------------------------------------------
    # Distance measurements
    # -------------------------------------------------------------------------
    TestCase(
        id="measure-006",
        tool="rhino_measure_distance",
        params={"from": [0, 0, 0], "to": [10, 0, 0]},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_7_MEASURE,
        description="Measure distance between two points (10 units)",
        intent="measure distance between points",
        tags=["measure", "distance"],
        learn_on_success=(
            "Use rhino_measure_distance with 'from' and 'to' arrays for point-to-point distance. "
            "Returns distance value. Points are [x, y, z] arrays."
        ),
    ),
    TestCase(
        id="measure-007",
        tool="rhino_measure_distance",
        params={"from": [0, 0, 0], "to": [3, 4, 0]},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_7_MEASURE,
        description="Measure distance (3-4-5 right triangle = 5 units)",
        intent="verify distance calculation with known triangle",
        tags=["measure", "distance", "validation"],
        learn_on_success="Distance from origin to (3,4,0) should be exactly 5 (Pythagorean theorem)",
    ),
    TestCase(
        id="measure-008",
        tool="rhino_measure_distance",
        params={"from": [0, 0, 0], "to": [1, 1, 1]},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_7_MEASURE,
        description="Measure 3D diagonal distance",
        intent="measure distance in 3D space",
        tags=["measure", "distance", "3d"],
        learn_on_success="Distance from origin to (1,1,1) is sqrt(3) ≈ 1.732",
    ),
    TestCase(
        id="measure-009",
        tool="rhino_measure_distance",
        params={"fromId": "PLACEHOLDER", "toId": "PLACEHOLDER"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_7_MEASURE,
        description="Measure distance between two objects",
        intent="measure distance between objects using IDs",
        tags=["measure", "distance", "objects"],
        depends_on=["measure-001", "measure-002"],
        learn_on_success=(
            "Use fromId and toId to measure distance between objects. "
            "Returns minimum distance between object geometries, not just centers."
        ),
    ),

    # -------------------------------------------------------------------------
    # Bounding box measurements
    # -------------------------------------------------------------------------
    TestCase(
        id="measure-010",
        tool="rhino_measure_bbox",
        params={"id": "PLACEHOLDER"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_7_MEASURE,
        description="Get bounding box of 10x10x10 box",
        intent="get object bounding box",
        tags=["measure", "bbox"],
        depends_on=["measure-001"],
        learn_on_success=(
            "rhino_measure_bbox returns min and max corners of axis-aligned bounding box. "
            "For 10x10x10 box at (200,0,0), bbox is from (200,0,0) to (210,10,10)."
        ),
    ),
    TestCase(
        id="measure-011",
        tool="rhino_measure_bbox",
        params={"id": "PLACEHOLDER"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_7_MEASURE,
        description="Get bounding box of sphere",
        intent="get sphere bounding box",
        tags=["measure", "bbox"],
        depends_on=["measure-002"],
        learn_on_success=(
            "Sphere bbox is a cube with side = 2*radius. "
            "Sphere centered at (220,0,0) with r=5 has bbox from (215,-5,-5) to (225,5,5)."
        ),
    ),

    # -------------------------------------------------------------------------
    # Centroid measurements
    # -------------------------------------------------------------------------
    TestCase(
        id="measure-012",
        tool="rhino_measure_centroid",
        params={"id": "PLACEHOLDER"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_7_MEASURE,
        description="Get centroid of box",
        intent="get object center point",
        tags=["measure", "centroid"],
        depends_on=["measure-001"],
        learn_on_success=(
            "rhino_measure_centroid returns the center of mass as [x,y,z]. "
            "For 10x10x10 box at origin (200,0,0), centroid is (205,5,5)."
        ),
    ),
    TestCase(
        id="measure-013",
        tool="rhino_measure_centroid",
        params={"id": "PLACEHOLDER"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_7_MEASURE,
        description="Get centroid of sphere (should be center)",
        intent="get sphere center point",
        tags=["measure", "centroid"],
        depends_on=["measure-002"],
        learn_on_success="Sphere centroid equals its center point",
    ),

    # -------------------------------------------------------------------------
    # Length measurements (curves)
    # -------------------------------------------------------------------------
    TestCase(
        id="measure-014",
        tool="rhino_measure_length",
        params={"id": "PLACEHOLDER"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_7_MEASURE,
        description="Measure length of 20-unit line",
        intent="measure curve length",
        tags=["measure", "length", "line"],
        depends_on=["measure-003"],
        learn_on_success=(
            "rhino_measure_length returns the arc length of a curve. "
            "For a line from (240,0,0) to (260,0,0), length is 20."
        ),
    ),
    TestCase(
        id="measure-015",
        tool="rhino_measure_length",
        params={"id": "PLACEHOLDER"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_7_MEASURE,
        description="Measure circumference of circle (2*pi*r)",
        intent="measure circle circumference",
        tags=["measure", "length", "circle"],
        depends_on=["measure-004"],
        learn_on_success="Circle circumference = 2*pi*r. For r=10, length ≈ 62.83",
    ),

    # -------------------------------------------------------------------------
    # Area measurements
    # -------------------------------------------------------------------------
    TestCase(
        id="measure-016",
        tool="rhino_measure_area",
        params={"id": "PLACEHOLDER"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_7_MEASURE,
        description="Measure surface area of 10x10x10 box",
        intent="measure surface area of solid",
        tags=["measure", "area", "box"],
        depends_on=["measure-001"],
        learn_on_success=(
            "rhino_measure_area returns total surface area. "
            "For 10x10x10 box: 6 faces * 100 = 600 square units."
        ),
    ),
    TestCase(
        id="measure-017",
        tool="rhino_measure_area",
        params={"id": "PLACEHOLDER"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_7_MEASURE,
        description="Measure surface area of sphere (4*pi*r^2)",
        intent="measure sphere surface area",
        tags=["measure", "area", "sphere"],
        depends_on=["measure-002"],
        learn_on_success="Sphere surface area = 4*pi*r^2. For r=5, area ≈ 314.16",
    ),
    TestCase(
        id="measure-018",
        tool="rhino_measure_area",
        params={"id": "PLACEHOLDER"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_7_MEASURE,
        description="Measure surface area of cylinder",
        intent="measure cylinder surface area",
        tags=["measure", "area", "cylinder"],
        depends_on=["measure-005"],
        learn_on_success="Cylinder area = 2*pi*r*h + 2*pi*r^2. For r=5, h=20, area ≈ 785.4",
    ),

    # -------------------------------------------------------------------------
    # Volume measurements
    # -------------------------------------------------------------------------
    TestCase(
        id="measure-019",
        tool="rhino_measure_volume",
        params={"id": "PLACEHOLDER"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_7_MEASURE,
        description="Measure volume of 10x10x10 box (1000 cubic units)",
        intent="measure volume of box",
        tags=["measure", "volume", "box"],
        depends_on=["measure-001"],
        learn_on_success=(
            "rhino_measure_volume returns volume of closed solids. "
            "For 10x10x10 box, volume is 1000 cubic units."
        ),
    ),
    TestCase(
        id="measure-020",
        tool="rhino_measure_volume",
        params={"id": "PLACEHOLDER"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_7_MEASURE,
        description="Measure volume of sphere (4/3 * pi * r^3)",
        intent="measure sphere volume",
        tags=["measure", "volume", "sphere"],
        depends_on=["measure-002"],
        learn_on_success="Sphere volume = 4/3*pi*r^3. For r=5, volume ≈ 523.6",
    ),
    TestCase(
        id="measure-021",
        tool="rhino_measure_volume",
        params={"id": "PLACEHOLDER"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_7_MEASURE,
        description="Measure volume of cylinder (pi * r^2 * h)",
        intent="measure cylinder volume",
        tags=["measure", "volume", "cylinder"],
        depends_on=["measure-005"],
        learn_on_success="Cylinder volume = pi*r^2*h. For r=5, h=20, volume ≈ 1570.8",
    ),

    # -------------------------------------------------------------------------
    # Edge cases
    # -------------------------------------------------------------------------
    TestCase(
        id="measure-022",
        tool="rhino_measure_length",
        params={"id": "PLACEHOLDER"},
        expected=ExpectedOutcome.FAILURE,
        phase=TestPhase.PHASE_7_MEASURE,
        description="Try to measure length of a solid (should fail)",
        intent="measure length of non-curve",
        tags=["measure", "length", "edge-case"],
        depends_on=["measure-001"],
        learn_on_failure="rhino_measure_length only works on curves, not solids. Use rhino_measure_bbox for solid dimensions.",
    ),
    TestCase(
        id="measure-023",
        tool="rhino_measure_volume",
        params={"id": "PLACEHOLDER"},
        expected=ExpectedOutcome.FAILURE,
        phase=TestPhase.PHASE_7_MEASURE,
        description="Try to measure volume of open curve (should fail)",
        intent="measure volume of curve",
        tags=["measure", "volume", "edge-case"],
        depends_on=["measure-003"],
        learn_on_failure="rhino_measure_volume requires a closed solid. Open curves and surfaces have no volume.",
    ),
    TestCase(
        id="measure-024",
        tool="rhino_measure_bbox",
        params={"id": "invalid-guid-12345"},
        expected=ExpectedOutcome.FAILURE,
        phase=TestPhase.PHASE_7_MEASURE,
        description="Measure bbox with invalid ID",
        intent="handle invalid object ID in measurement",
        tags=["measure", "bbox", "edge-case"],
        learn_on_failure="Measurement tools return error for invalid object IDs",
    ),
    TestCase(
        id="measure-025",
        tool="rhino_measure_distance",
        params={"from": [0, 0, 0], "to": [0, 0, 0]},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_7_MEASURE,
        description="Measure zero distance (same point)",
        intent="measure distance to same point",
        tags=["measure", "distance", "edge-case"],
        learn_on_success="Distance between identical points is 0",
    ),
]


# =============================================================================
# PHASE 8: Curve Operations
# =============================================================================

PHASE_8_TESTS = [
    # -------------------------------------------------------------------------
    # Setup: Create curves for curve operation tests
    # -------------------------------------------------------------------------
    TestCase(
        id="curve-001",
        tool="rhino_create",
        params={"type": "LINE", "start": [400, 0, 0], "end": [410, 0, 0], "name": "CurveLine1"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_8_CURVE,
        description="Create first line segment for join",
        intent="create line for curve operations",
        tags=["curve", "setup"],
        learn_on_success="Create line segment for curve join testing",
    ),
    TestCase(
        id="curve-002",
        tool="rhino_create",
        params={"type": "LINE", "start": [410, 0, 0], "end": [420, 5, 0], "name": "CurveLine2"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_8_CURVE,
        description="Create second line segment (connected to first)",
        intent="create connected line for join",
        tags=["curve", "setup"],
        learn_on_success="Create connected line segment - endpoints must match for join",
    ),
    TestCase(
        id="curve-003",
        tool="rhino_create",
        params={"type": "LINE", "start": [420, 5, 0], "end": [430, 0, 0], "name": "CurveLine3"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_8_CURVE,
        description="Create third line segment (connected to second)",
        intent="create third segment for polyline join",
        tags=["curve", "setup"],
        learn_on_success="Three connected lines form a polyline when joined",
    ),
    TestCase(
        id="curve-004",
        tool="rhino_create",
        params={"type": "LINE", "start": [450, 0, 0], "end": [470, 0, 0], "name": "DivideLine"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_8_CURVE,
        description="Create line for divide operation",
        intent="create line to divide into points",
        tags=["curve", "setup", "divide"],
        learn_on_success="20-unit line for divide testing",
    ),
    TestCase(
        id="curve-005",
        tool="rhino_create",
        params={"type": "LINE", "start": [500, 0, 0], "end": [520, 0, 0], "name": "ExtendLine"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_8_CURVE,
        description="Create line for extend operation",
        intent="create line to extend",
        tags=["curve", "setup", "extend"],
        learn_on_success="Line for extend testing",
    ),
    TestCase(
        id="curve-006",
        tool="rhino_create",
        params={"type": "LINE", "start": [550, 0, 0], "end": [570, 0, 0], "name": "SplitLine"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_8_CURVE,
        description="Create line for split operation",
        intent="create line to split",
        tags=["curve", "setup", "split"],
        learn_on_success="Line for split testing at parameter",
    ),
    TestCase(
        id="curve-007",
        tool="rhino_create",
        params={"type": "LINE", "start": [600, 0, 0], "end": [620, 10, 0], "name": "FilletLine1"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_8_CURVE,
        description="Create first line for fillet",
        intent="create line for fillet operation",
        tags=["curve", "setup", "fillet"],
        learn_on_success="First line for fillet - lines should intersect or nearly meet",
    ),
    TestCase(
        id="curve-008",
        tool="rhino_create",
        params={"type": "LINE", "start": [620, 10, 0], "end": [640, 0, 0], "name": "FilletLine2"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_8_CURVE,
        description="Create second line for fillet (meets first at corner)",
        intent="create second line for fillet",
        tags=["curve", "setup", "fillet"],
        learn_on_success="Second line meets first at (620,10,0) - creates corner for fillet",
    ),
    TestCase(
        id="curve-009",
        tool="rhino_create",
        params={
            "type": "POLYLINE",
            "points": [[700, 0, 0], [710, 5, 0], [720, 0, 0], [730, 5, 0]],
            "name": "ExplodePolyline"
        },
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_8_CURVE,
        description="Create polyline for explode operation",
        intent="create polyline to explode into segments",
        tags=["curve", "setup", "explode"],
        learn_on_success="Polyline with 4 points creates 3 segments when exploded",
    ),
    TestCase(
        id="curve-010",
        tool="rhino_create",
        params={"type": "CIRCLE", "center": [750, 0, 0], "radius": 10, "name": "RebuildCircle"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_8_CURVE,
        description="Create circle for rebuild operation",
        intent="create circle to rebuild with different point count",
        tags=["curve", "setup", "rebuild"],
        learn_on_success="Circle for rebuild testing - can change control point count",
    ),

    # -------------------------------------------------------------------------
    # Join operations
    # -------------------------------------------------------------------------
    TestCase(
        id="curve-011",
        tool="rhino_curve_ops",
        params={"action": "join", "ids": ["PLACEHOLDER1", "PLACEHOLDER2"]},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_8_CURVE,
        description="Join two connected line segments",
        intent="join curves into polycurve",
        tags=["curve", "join"],
        depends_on=["curve-001", "curve-002"],
        learn_on_success=(
            "Use rhino_curve_ops with action='join' and ids array to join curves. "
            "Curves must share endpoints to join. Returns new polycurve ID."
        ),
    ),
    TestCase(
        id="curve-012",
        tool="rhino_curve_ops",
        params={"action": "join", "ids": ["PLACEHOLDER1", "PLACEHOLDER2", "PLACEHOLDER3"]},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_8_CURVE,
        description="Join three connected line segments",
        intent="join multiple curves at once",
        tags=["curve", "join", "multi"],
        depends_on=["curve-001", "curve-002", "curve-003"],
        learn_on_success="Can join multiple curves in single operation if they form a chain",
    ),
    TestCase(
        id="curve-013",
        tool="rhino_curve_ops",
        params={"action": "join", "ids": []},
        expected=ExpectedOutcome.FAILURE,
        phase=TestPhase.PHASE_8_CURVE,
        description="Join with empty array (should fail)",
        intent="handle empty join input",
        tags=["curve", "join", "edge-case"],
        learn_on_failure="Join requires at least one curve ID in the ids array",
    ),

    # -------------------------------------------------------------------------
    # Divide operations
    # -------------------------------------------------------------------------
    TestCase(
        id="curve-014",
        tool="rhino_curve_ops",
        params={"action": "divide", "id": "PLACEHOLDER", "count": 5},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_8_CURVE,
        description="Divide line into 5 segments (6 points)",
        intent="divide curve into equal segments",
        tags=["curve", "divide"],
        depends_on=["curve-004"],
        learn_on_success=(
            "Divide curve with count=5 creates 6 points (count+1). "
            "For 20-unit line, points are at 0, 4, 8, 12, 16, 20 units."
        ),
    ),
    TestCase(
        id="curve-015",
        tool="rhino_curve_ops",
        params={"action": "divide", "id": "PLACEHOLDER", "count": 10},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_8_CURVE,
        description="Divide line into 10 segments",
        intent="divide curve into many segments",
        tags=["curve", "divide"],
        depends_on=["curve-004"],
        learn_on_success="count=10 creates 11 evenly spaced points along curve",
    ),
    TestCase(
        id="curve-016",
        tool="rhino_curve_ops",
        params={"action": "divide", "id": "PLACEHOLDER", "count": 1},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_8_CURVE,
        description="Divide with count=1 (2 points: start and end)",
        intent="divide curve minimally",
        tags=["curve", "divide", "edge-case"],
        depends_on=["curve-004"],
        learn_on_success="count=1 returns just start and end points",
    ),

    # -------------------------------------------------------------------------
    # Extend operations
    # -------------------------------------------------------------------------
    TestCase(
        id="curve-017",
        tool="rhino_curve_ops",
        params={"action": "extend", "id": "PLACEHOLDER", "end": 1, "length": 10},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_8_CURVE,
        description="Extend line at end by 10 units",
        intent="extend curve at endpoint",
        tags=["curve", "extend"],
        depends_on=["curve-005"],
        learn_on_success=(
            "Extend curve with end=1 extends the end point. "
            "end=0 extends start, end=1 extends end. Length is extension amount."
        ),
    ),
    TestCase(
        id="curve-018",
        tool="rhino_curve_ops",
        params={"action": "extend", "id": "PLACEHOLDER", "end": 0, "length": 5},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_8_CURVE,
        description="Extend line at start by 5 units",
        intent="extend curve at start point",
        tags=["curve", "extend"],
        depends_on=["curve-005"],
        learn_on_success="end=0 extends the start of the curve in its tangent direction",
    ),

    # -------------------------------------------------------------------------
    # Split operations
    # -------------------------------------------------------------------------
    TestCase(
        id="curve-019",
        tool="rhino_curve_ops",
        params={"action": "split", "id": "PLACEHOLDER", "parameter": 0.5},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_8_CURVE,
        description="Split line at midpoint (parameter 0.5)",
        intent="split curve at parameter",
        tags=["curve", "split"],
        depends_on=["curve-006"],
        learn_on_success=(
            "Split curve at parameter 0.5 divides it at midpoint. "
            "Parameter range is 0.0 (start) to 1.0 (end). Returns two new curve IDs."
        ),
    ),
    TestCase(
        id="curve-020",
        tool="rhino_curve_ops",
        params={"action": "split", "id": "PLACEHOLDER", "parameter": 0.25},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_8_CURVE,
        description="Split line at 1/4 point",
        intent="split curve at quarter point",
        tags=["curve", "split"],
        depends_on=["curve-006"],
        learn_on_success="parameter=0.25 splits curve 25% from start",
    ),

    # -------------------------------------------------------------------------
    # Fillet operations
    # -------------------------------------------------------------------------
    TestCase(
        id="curve-021",
        tool="rhino_curve_ops",
        params={"action": "fillet", "id1": "PLACEHOLDER1", "id2": "PLACEHOLDER2", "radius": 2},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_8_CURVE,
        description="Fillet two lines with radius 2",
        intent="fillet curves at intersection",
        tags=["curve", "fillet"],
        depends_on=["curve-007", "curve-008"],
        learn_on_success=(
            "Fillet creates rounded corner between two curves. "
            "Curves must intersect or nearly meet. Radius determines arc size."
        ),
    ),
    TestCase(
        id="curve-022",
        tool="rhino_curve_ops",
        params={"action": "fillet", "id1": "PLACEHOLDER1", "id2": "PLACEHOLDER2", "radius": 5},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_8_CURVE,
        description="Fillet with larger radius",
        intent="fillet with different radius",
        tags=["curve", "fillet"],
        depends_on=["curve-007", "curve-008"],
        learn_on_success="Larger radius creates more gradual curve transition",
    ),
    TestCase(
        id="curve-023",
        tool="rhino_curve_ops",
        params={"action": "fillet", "id1": "PLACEHOLDER1", "id2": "PLACEHOLDER2", "radius": 0},
        expected=ExpectedOutcome.EITHER,
        phase=TestPhase.PHASE_8_CURVE,
        description="Fillet with zero radius",
        intent="fillet with zero radius",
        tags=["curve", "fillet", "edge-case"],
        depends_on=["curve-007", "curve-008"],
        learn_on_success="radius=0 may create sharp corner or fail depending on implementation",
    ),

    # -------------------------------------------------------------------------
    # Explode operations
    # -------------------------------------------------------------------------
    TestCase(
        id="curve-024",
        tool="rhino_curve_ops",
        params={"action": "explode", "id": "PLACEHOLDER"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_8_CURVE,
        description="Explode polyline into individual segments",
        intent="explode polycurve into segments",
        tags=["curve", "explode"],
        depends_on=["curve-009"],
        learn_on_success=(
            "Explode breaks polycurve into individual curve segments. "
            "4-point polyline becomes 3 line segments. Returns array of new curve IDs."
        ),
    ),

    # -------------------------------------------------------------------------
    # Rebuild operations
    # -------------------------------------------------------------------------
    TestCase(
        id="curve-025",
        tool="rhino_curve_ops",
        params={"action": "rebuild", "id": "PLACEHOLDER", "pointCount": 20},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_8_CURVE,
        description="Rebuild circle with 20 control points",
        intent="rebuild curve with different point count",
        tags=["curve", "rebuild"],
        depends_on=["curve-010"],
        learn_on_success=(
            "Rebuild changes curve's control point count while maintaining shape. "
            "More points = smoother curve, fewer points = simpler curve."
        ),
    ),
    TestCase(
        id="curve-026",
        tool="rhino_curve_ops",
        params={"action": "rebuild", "id": "PLACEHOLDER", "degree": 5, "pointCount": 15},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_8_CURVE,
        description="Rebuild circle with degree 5 and 15 points",
        intent="rebuild curve with custom degree",
        tags=["curve", "rebuild"],
        depends_on=["curve-010"],
        learn_on_success="Can specify both degree (curve smoothness) and pointCount",
    ),
    TestCase(
        id="curve-027",
        tool="rhino_curve_ops",
        params={"action": "rebuild", "id": "PLACEHOLDER", "degree": 3},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_8_CURVE,
        description="Rebuild with only degree specified",
        intent="rebuild curve changing only degree",
        tags=["curve", "rebuild"],
        depends_on=["curve-010"],
        learn_on_success="Can rebuild with just degree parameter, keeping similar point count",
    ),

    # -------------------------------------------------------------------------
    # Edge cases
    # -------------------------------------------------------------------------
    TestCase(
        id="curve-028",
        tool="rhino_curve_ops",
        params={"action": "divide", "id": "invalid-guid", "count": 5},
        expected=ExpectedOutcome.FAILURE,
        phase=TestPhase.PHASE_8_CURVE,
        description="Divide with invalid ID",
        intent="handle invalid curve ID",
        tags=["curve", "divide", "edge-case"],
        learn_on_failure="Curve operations return error for invalid object IDs",
    ),
    TestCase(
        id="curve-029",
        tool="rhino_curve_ops",
        params={"action": "split", "id": "PLACEHOLDER", "parameter": 1.5},
        expected=ExpectedOutcome.FAILURE,
        phase=TestPhase.PHASE_8_CURVE,
        description="Split with parameter outside valid range",
        intent="handle invalid parameter value",
        tags=["curve", "split", "edge-case"],
        depends_on=["curve-006"],
        learn_on_failure="Parameter must be between 0.0 and 1.0 for split operation",
    ),
    TestCase(
        id="curve-030",
        tool="rhino_curve_ops",
        params={"action": "extend", "id": "PLACEHOLDER", "end": 2, "length": 5},
        expected=ExpectedOutcome.FAILURE,
        phase=TestPhase.PHASE_8_CURVE,
        description="Extend with invalid end parameter",
        intent="handle invalid end value",
        tags=["curve", "extend", "edge-case"],
        depends_on=["curve-005"],
        learn_on_failure="end parameter must be 0 (start) or 1 (end)",
    ),
]


# =============================================================================
# PHASE 9: Document Operations
# =============================================================================

PHASE_9_TESTS = [
    # -------------------------------------------------------------------------
    # Setup: Create geometry to test undo/redo
    # -------------------------------------------------------------------------
    TestCase(
        id="doc-001",
        tool="rhino_create",
        params={"type": "BOX", "origin": [900, 0, 0], "width": 10, "depth": 10, "height": 10, "name": "UndoTestBox"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_9_DOCUMENT,
        description="Create box for undo testing",
        intent="create geometry for undo test",
        tags=["document", "setup", "undo"],
        learn_on_success="Create geometry before testing undo operation",
    ),

    # -------------------------------------------------------------------------
    # Undo operations
    # -------------------------------------------------------------------------
    TestCase(
        id="doc-002",
        tool="rhino_document_ops",
        params={"action": "undo"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_9_DOCUMENT,
        description="Undo the last operation",
        intent="undo last operation",
        tags=["document", "undo"],
        depends_on=["doc-001"],
        learn_on_success=(
            "Use rhino_document_ops with action='undo' to undo the last operation. "
            "Returns success if there was something to undo."
        ),
    ),
    TestCase(
        id="doc-003",
        tool="rhino_document_ops",
        params={"action": "undo"},
        expected=ExpectedOutcome.EITHER,
        phase=TestPhase.PHASE_9_DOCUMENT,
        description="Undo when nothing to undo",
        intent="undo with empty history",
        tags=["document", "undo", "edge-case"],
        learn_on_success="Undo may succeed or fail when history is empty depending on document state",
    ),

    # -------------------------------------------------------------------------
    # Redo operations
    # -------------------------------------------------------------------------
    TestCase(
        id="doc-004",
        tool="rhino_document_ops",
        params={"action": "redo"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_9_DOCUMENT,
        description="Redo the last undone operation",
        intent="redo last undone operation",
        tags=["document", "redo"],
        depends_on=["doc-002"],
        learn_on_success=(
            "Use rhino_document_ops with action='redo' after undo. "
            "Restores the previously undone operation."
        ),
    ),
    TestCase(
        id="doc-005",
        tool="rhino_document_ops",
        params={"action": "redo"},
        expected=ExpectedOutcome.EITHER,
        phase=TestPhase.PHASE_9_DOCUMENT,
        description="Redo when nothing to redo",
        intent="redo with empty redo stack",
        tags=["document", "redo", "edge-case"],
        learn_on_success="Redo may succeed or fail when redo stack is empty",
    ),

    # -------------------------------------------------------------------------
    # Unit operations
    # -------------------------------------------------------------------------
    TestCase(
        id="doc-006",
        tool="rhino_document_ops",
        params={"action": "set_units", "units": "Millimeters"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_9_DOCUMENT,
        description="Set document units to Millimeters",
        intent="set document units",
        tags=["document", "units"],
        learn_on_success=(
            "Use rhino_document_ops with action='set_units' and units parameter. "
            "Valid units: Millimeters, Centimeters, Meters, Inches, Feet, etc."
        ),
    ),
    TestCase(
        id="doc-007",
        tool="rhino_document_ops",
        params={"action": "set_units", "units": "Meters"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_9_DOCUMENT,
        description="Set document units to Meters",
        intent="change units to meters",
        tags=["document", "units"],
        learn_on_success="Changing units affects all geometry display but not actual coordinates",
    ),
    TestCase(
        id="doc-008",
        tool="rhino_document_ops",
        params={"action": "set_units", "units": "Inches"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_9_DOCUMENT,
        description="Set document units to Inches",
        intent="change units to inches",
        tags=["document", "units"],
        learn_on_success="Imperial units (Inches, Feet) are also supported",
    ),
    TestCase(
        id="doc-009",
        tool="rhino_document_ops",
        params={"action": "set_units", "units": "Centimeters"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_9_DOCUMENT,
        description="Set document units to Centimeters",
        intent="change units to centimeters",
        tags=["document", "units"],
        learn_on_success="Centimeters is a common unit for detailed work",
    ),
    TestCase(
        id="doc-010",
        tool="rhino_document_ops",
        params={"action": "set_units", "units": "InvalidUnit"},
        expected=ExpectedOutcome.FAILURE,
        phase=TestPhase.PHASE_9_DOCUMENT,
        description="Set units to invalid value",
        intent="handle invalid unit value",
        tags=["document", "units", "edge-case"],
        learn_on_failure="Invalid unit names return error. Use standard Rhino unit names.",
    ),

    # -------------------------------------------------------------------------
    # Get document info (verify units changed)
    # -------------------------------------------------------------------------
    TestCase(
        id="doc-011",
        tool="rhino_document",
        params={},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_9_DOCUMENT,
        description="Get document info to verify units",
        intent="check document properties",
        tags=["document", "info"],
        learn_on_success="rhino_document returns current document info including units",
    ),

    # -------------------------------------------------------------------------
    # Save operations (use temp path)
    # -------------------------------------------------------------------------
    TestCase(
        id="doc-012",
        tool="rhino_document_ops",
        params={"action": "save", "path": "C:/temp/rook_test_save.3dm"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_9_DOCUMENT,
        description="Save document to file",
        intent="save document to path",
        tags=["document", "save"],
        learn_on_success=(
            "Use rhino_document_ops with action='save' and path parameter. "
            "Path must be absolute and writable. Creates .3dm file."
        ),
    ),
    TestCase(
        id="doc-013",
        tool="rhino_document_ops",
        params={"action": "save"},
        expected=ExpectedOutcome.FAILURE,
        phase=TestPhase.PHASE_9_DOCUMENT,
        description="Save without path (should fail)",
        intent="save without required path",
        tags=["document", "save", "edge-case"],
        learn_on_failure="Save action requires 'path' parameter",
    ),

    # -------------------------------------------------------------------------
    # Undo/Redo sequence test
    # -------------------------------------------------------------------------
    TestCase(
        id="doc-014",
        tool="rhino_create",
        params={"type": "SPHERE", "center": [950, 0, 0], "radius": 5, "name": "UndoRedoSphere"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_9_DOCUMENT,
        description="Create sphere for undo/redo sequence",
        intent="create geometry for undo sequence",
        tags=["document", "setup", "undo-redo"],
        learn_on_success="Create geometry to test undo/redo sequence",
    ),
    TestCase(
        id="doc-015",
        tool="rhino_delete",
        params={"ids": ["PLACEHOLDER"]},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_9_DOCUMENT,
        description="Delete sphere (to be undone)",
        intent="delete geometry to test undo",
        tags=["document", "delete", "undo-redo"],
        depends_on=["doc-014"],
        learn_on_success="Delete geometry - can be undone to restore",
    ),
    TestCase(
        id="doc-016",
        tool="rhino_document_ops",
        params={"action": "undo"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_9_DOCUMENT,
        description="Undo delete to restore sphere",
        intent="undo deletion",
        tags=["document", "undo", "restore"],
        depends_on=["doc-015"],
        learn_on_success="Undo after delete restores the deleted geometry",
    ),
    TestCase(
        id="doc-017",
        tool="rhino_document_ops",
        params={"action": "redo"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_9_DOCUMENT,
        description="Redo to delete sphere again",
        intent="redo deletion",
        tags=["document", "redo", "delete"],
        depends_on=["doc-016"],
        learn_on_success="Redo after undo-delete removes the geometry again",
    ),
    TestCase(
        id="doc-018",
        tool="rhino_document_ops",
        params={"action": "undo"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_9_DOCUMENT,
        description="Undo again to restore sphere",
        intent="multiple undo operations",
        tags=["document", "undo", "multiple"],
        depends_on=["doc-017"],
        learn_on_success="Can undo multiple times in sequence",
    ),

    # -------------------------------------------------------------------------
    # Reset units to default
    # -------------------------------------------------------------------------
    TestCase(
        id="doc-019",
        tool="rhino_document_ops",
        params={"action": "set_units", "units": "Millimeters"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_9_DOCUMENT,
        description="Reset units to Millimeters (cleanup)",
        intent="reset units to default",
        tags=["document", "units", "cleanup"],
        learn_on_success="Reset units after testing to restore document state",
    ),
]


# =============================================================================
# PHASE 10: Script Execution (rhino_execute, rhino_command)
# =============================================================================

PHASE_10_TESTS = [
    # -------------------------------------------------------------------------
    # rhino_execute - Python script execution
    # -------------------------------------------------------------------------
    TestCase(
        id="script-001",
        tool="rhino_execute",
        params={"code": "import rhinoscriptsyntax as rs\nresult = 2 + 2"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_10_SCRIPT,
        description="Execute simple Python math expression",
        intent="execute basic Python code in Rhino",
        tags=["script", "python", "basic"],
        learn_on_success=(
            "rhino_execute runs Python code in Rhino's IronPython environment. "
            "Always import rhinoscriptsyntax as rs for Rhino operations. "
            "Returns execution result and any printed output."
        ),
    ),
    TestCase(
        id="script-002",
        tool="rhino_execute",
        params={"code": "import rhinoscriptsyntax as rs\npt = rs.AddPoint(500, 0, 0)"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_10_SCRIPT,
        description="Create geometry via Python script",
        intent="create point using rhinoscriptsyntax",
        tags=["script", "python", "geometry"],
        learn_on_success=(
            "Use rs.AddPoint(x, y, z) to create points. "
            "rhinoscriptsyntax functions return GUIDs of created objects. "
            "This is useful for complex operations not covered by MCP tools."
        ),
    ),
    TestCase(
        id="script-003",
        tool="rhino_execute",
        params={"code": "import rhinoscriptsyntax as rs\nbox = rs.AddBox([(510, 0, 0), (520, 0, 0), (520, 10, 0), (510, 10, 0), (510, 0, 10), (520, 0, 10), (520, 10, 10), (510, 10, 10)])"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_10_SCRIPT,
        description="Create box via Python script (8 corner points)",
        intent="create box using rhinoscriptsyntax",
        tags=["script", "python", "geometry", "box"],
        learn_on_success=(
            "rs.AddBox takes 8 corner points to define a box. "
            "Order: [bottom-front-left, bottom-front-right, bottom-back-right, bottom-back-left, "
            "top-front-left, top-front-right, top-back-right, top-back-left]."
        ),
    ),
    TestCase(
        id="script-004",
        tool="rhino_execute",
        params={"code": "import rhinoscriptsyntax as rs\nobjs = rs.AllObjects()\nprint('Object count:', len(objs) if objs else 0)"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_10_SCRIPT,
        description="Query document via Python script",
        intent="query document info using rhinoscriptsyntax",
        tags=["script", "python", "query"],
        learn_on_success=(
            "rs.AllObjects() returns list of all object GUIDs in document. "
            "Use len() to count objects. Use print() to output - it's captured in result."
        ),
    ),
    TestCase(
        id="script-005",
        tool="rhino_execute",
        params={"code": "import rhinoscriptsyntax as rs\nlayers = rs.LayerNames()\nfor layer in layers:\n    print(layer)"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_10_SCRIPT,
        description="List all layers via Python script",
        intent="list layers using rhinoscriptsyntax",
        tags=["script", "python", "layers"],
        learn_on_success="rs.LayerNames() returns list of all layer names in the document",
    ),
    TestCase(
        id="script-006",
        tool="rhino_execute",
        params={"code": "import Rhino\ndoc = Rhino.RhinoDoc.ActiveDoc\nprint('Units:', doc.ModelUnitSystem)"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_10_SCRIPT,
        description="Access RhinoCommon directly in Python",
        intent="use RhinoCommon API in Python script",
        tags=["script", "python", "rhinocommon"],
        learn_on_success=(
            "Can import Rhino module to access RhinoCommon directly. "
            "Use Rhino.RhinoDoc.ActiveDoc to get current document. "
            "This provides access to lower-level APIs than rhinoscriptsyntax."
        ),
    ),
    TestCase(
        id="script-007",
        tool="rhino_execute",
        params={"code": "import rhinoscriptsyntax as rs\ncircle = rs.AddCircle((530, 0, 0), 5)\nif circle:\n    rs.ObjectName(circle, 'ScriptCircle')"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_10_SCRIPT,
        description="Create and name object via script",
        intent="create named geometry using script",
        tags=["script", "python", "geometry", "naming"],
        learn_on_success=(
            "rs.AddCircle(center, radius) creates a circle. "
            "rs.ObjectName(id, name) sets object name. "
            "Check return values - they are None if operation fails."
        ),
    ),
    TestCase(
        id="script-008",
        tool="rhino_execute",
        params={"code": "this is not valid python"},
        expected=ExpectedOutcome.FAILURE,
        phase=TestPhase.PHASE_10_SCRIPT,
        description="Handle Python syntax error",
        intent="test error handling for invalid Python",
        tags=["script", "python", "error"],
        learn_on_failure=(
            "Invalid Python syntax returns an error. "
            "The error message contains the syntax error details. "
            "Always validate Python code before sending to rhino_execute."
        ),
    ),
    TestCase(
        id="script-009",
        tool="rhino_execute",
        params={"code": "import rhinoscriptsyntax as rs\nrs.UndefinedFunction()"},
        expected=ExpectedOutcome.FAILURE,
        phase=TestPhase.PHASE_10_SCRIPT,
        description="Handle undefined function error",
        intent="test error handling for undefined function",
        tags=["script", "python", "error"],
        learn_on_failure=(
            "Calling undefined functions raises AttributeError. "
            "Check rhinoscriptsyntax documentation for available functions. "
            "Error message includes the function name that was not found."
        ),
    ),
    TestCase(
        id="script-010",
        tool="rhino_execute",
        params={"code": "import rhinoscriptsyntax as rs\nimport math\npoints = []\nfor i in range(36):\n    angle = math.radians(i * 10)\n    x = 550 + 10 * math.cos(angle)\n    y = 10 * math.sin(angle)\n    points.append((x, y, 0))\nrs.AddPolyline(points + [points[0]])"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_10_SCRIPT,
        description="Create complex geometry with math",
        intent="generate geometry using Python math",
        tags=["script", "python", "geometry", "math"],
        learn_on_success=(
            "Use Python's math module for trigonometry. "
            "Can generate complex geometry programmatically. "
            "rs.AddPolyline(points) creates a polyline through points."
        ),
    ),

    # -------------------------------------------------------------------------
    # rhino_command - Rhino command string execution
    # -------------------------------------------------------------------------
    TestCase(
        id="script-011",
        tool="rhino_command",
        params={"command": "_SelNone"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_10_SCRIPT,
        description="Run Rhino command to deselect all",
        intent="run Rhino selection command",
        tags=["script", "command", "selection"],
        learn_on_success=(
            "rhino_command executes Rhino command-line strings. "
            "Use underscore prefix (_Command) for language-independent commands. "
            "_SelNone deselects all objects."
        ),
    ),
    TestCase(
        id="script-012",
        tool="rhino_command",
        params={"command": "_Point 600,0,0"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_10_SCRIPT,
        description="Create point using Rhino command",
        intent="create geometry via Rhino command",
        tags=["script", "command", "geometry"],
        learn_on_success=(
            "Create a point at specific coordinates using _Point command. "
            "Coordinates can be passed as 'x,y,z' format (no spaces). "
            "This is equivalent to typing in Rhino command line."
        ),
    ),
    TestCase(
        id="script-013",
        tool="rhino_command",
        params={"command": "_Circle 610,0,0 5"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_10_SCRIPT,
        description="Create circle using Rhino command",
        intent="create circle via Rhino command",
        tags=["script", "command", "geometry"],
        learn_on_success=(
            "_Circle command takes center point and radius. "
            "Format: _Circle center,point radius. "
            "Use Enter or space to complete command."
        ),
    ),
    TestCase(
        id="script-014",
        tool="rhino_command",
        params={"command": "_Line 620,0,0 640,0,0"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_10_SCRIPT,
        description="Create line using Rhino command",
        intent="create line via Rhino command",
        tags=["script", "command", "geometry"],
        learn_on_success=(
            "_Line command takes start and end points. "
            "Format: _Line startX,startY,startZ endX,endY,endZ. "
            "Creates a line segment between two points."
        ),
    ),
    TestCase(
        id="script-015",
        tool="rhino_command",
        params={"command": "_-Box _Corner 650,0,0 660,10,10"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_10_SCRIPT,
        description="Create box using Rhino command (corners)",
        intent="create box via Rhino command",
        tags=["script", "command", "geometry"],
        learn_on_success=(
            "Use _-Box (hyphen prefix) for command-line mode without prompts. "
            "_Corner option specifies corner-to-corner mode. "
            "Format: _-Box _Corner corner1 corner2."
        ),
    ),
    TestCase(
        id="script-016",
        tool="rhino_command",
        params={"command": "_Zoom _All _Extents"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_10_SCRIPT,
        description="Zoom to extents using Rhino command",
        intent="control viewport via command",
        tags=["script", "command", "viewport"],
        learn_on_success=(
            "_Zoom _All _Extents zooms all viewports to show all objects. "
            "Chain command options with underscores. "
            "Useful after creating geometry to see the result."
        ),
    ),
    TestCase(
        id="script-017",
        tool="rhino_command",
        params={"command": "_SelLast"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_10_SCRIPT,
        description="Select last created object",
        intent="select recently created objects",
        tags=["script", "command", "selection"],
        learn_on_success=(
            "_SelLast selects the most recently created object(s). "
            "Useful after creating geometry via commands to then manipulate it."
        ),
    ),
    TestCase(
        id="script-018",
        tool="rhino_command",
        params={"command": "_SetObjectName ScriptTestName", "echo": True},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_10_SCRIPT,
        description="Set object name with echo enabled",
        intent="name selected object via command",
        tags=["script", "command", "naming"],
        depends_on=["script-017"],
        learn_on_success=(
            "_SetObjectName sets name of selected objects. "
            "echo: true shows the command in Rhino's command line. "
            "Useful for debugging command execution."
        ),
    ),
    TestCase(
        id="script-019",
        tool="rhino_command",
        params={"command": "_InvalidCommand"},
        expected=ExpectedOutcome.FAILURE,
        phase=TestPhase.PHASE_10_SCRIPT,
        description="Handle invalid Rhino command",
        intent="test error handling for invalid command",
        tags=["script", "command", "error"],
        learn_on_failure=(
            "Invalid commands return an error or are ignored. "
            "Check Rhino command reference for valid command names. "
            "Always use underscore prefix for language-independent commands."
        ),
    ),
    TestCase(
        id="script-020",
        tool="rhino_command",
        params={"command": "_-Layer _New ScriptLayer _Enter"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_10_SCRIPT,
        description="Create layer using command-line mode",
        intent="create layer via command",
        tags=["script", "command", "layers"],
        learn_on_success=(
            "Prefix with hyphen (-Layer) for command-line mode (no dialog). "
            "_New creates a new layer, name follows. "
            "_Enter completes the command. This is useful for scripted automation."
        ),
    ),
]


# =============================================================================
# PHASE 11: I/O & Organization (import, export, group, block)
# =============================================================================

PHASE_11_TESTS = [
    # -------------------------------------------------------------------------
    # Setup: Create geometry for grouping and export tests
    # -------------------------------------------------------------------------
    TestCase(
        id="io-001",
        tool="rhino_create",
        params={"type": "BOX", "origin": [700, 0, 0], "width": 10, "depth": 10, "height": 10, "name": "GroupBox1"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_11_IO,
        description="Create first box for grouping",
        intent="create geometry for group test",
        tags=["io", "setup", "group"],
        learn_on_success="Create geometry to use in group operations",
    ),
    TestCase(
        id="io-002",
        tool="rhino_create",
        params={"type": "BOX", "origin": [720, 0, 0], "width": 10, "depth": 10, "height": 10, "name": "GroupBox2"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_11_IO,
        description="Create second box for grouping",
        intent="create geometry for group test",
        tags=["io", "setup", "group"],
        learn_on_success="Create second geometry for group",
    ),
    TestCase(
        id="io-003",
        tool="rhino_create",
        params={"type": "SPHERE", "center": [750, 0, 0], "radius": 5, "name": "GroupSphere"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_11_IO,
        description="Create sphere for grouping",
        intent="create geometry for group test",
        tags=["io", "setup", "group"],
        learn_on_success="Create sphere to include in group",
    ),

    # -------------------------------------------------------------------------
    # rhino_group - Create groups
    # -------------------------------------------------------------------------
    TestCase(
        id="io-004",
        tool="rhino_group",
        params={"ids": ["PLACEHOLDER", "PLACEHOLDER"], "name": "TestGroup"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_11_IO,
        description="Create named group from two boxes",
        intent="group objects together",
        tags=["io", "group"],
        depends_on=["io-001", "io-002"],
        learn_on_success=(
            "rhino_group creates a named group from object IDs. "
            "Grouped objects can be selected together. "
            "Provide array of GUIDs and optional group name."
        ),
    ),
    TestCase(
        id="io-005",
        tool="rhino_group",
        params={"ids": ["PLACEHOLDER"]},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_11_IO,
        description="Create unnamed group (single object)",
        intent="group single object",
        tags=["io", "group"],
        depends_on=["io-003"],
        learn_on_success="Can create group with single object. Name is optional.",
    ),
    TestCase(
        id="io-006",
        tool="rhino_group",
        params={"ids": [], "name": "EmptyGroup"},
        expected=ExpectedOutcome.FAILURE,
        phase=TestPhase.PHASE_11_IO,
        description="Fail to create empty group",
        intent="test empty group error handling",
        tags=["io", "group", "error"],
        learn_on_failure="Cannot create a group with no objects. Requires at least one ID.",
    ),
    TestCase(
        id="io-007",
        tool="rhino_group",
        params={"ids": ["00000000-0000-0000-0000-000000000000"], "name": "InvalidGroup"},
        expected=ExpectedOutcome.FAILURE,
        phase=TestPhase.PHASE_11_IO,
        description="Fail to create group with invalid ID",
        intent="test invalid ID error handling",
        tags=["io", "group", "error"],
        learn_on_failure="Invalid GUIDs are rejected. Verify object IDs exist before grouping.",
    ),

    # -------------------------------------------------------------------------
    # rhino_block_create - Create block definitions
    # -------------------------------------------------------------------------
    TestCase(
        id="io-008",
        tool="rhino_create",
        params={"type": "BOX", "origin": [800, 0, 0], "width": 5, "depth": 5, "height": 5, "name": "BlockSourceBox"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_11_IO,
        description="Create box for block definition",
        intent="create geometry for block",
        tags=["io", "setup", "block"],
        learn_on_success="Create geometry to convert into a block definition",
    ),
    TestCase(
        id="io-009",
        tool="rhino_create",
        params={"type": "SPHERE", "center": [810, 5, 5], "radius": 3, "name": "BlockSourceSphere"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_11_IO,
        description="Create sphere for block definition",
        intent="create second geometry for block",
        tags=["io", "setup", "block"],
        learn_on_success="Create additional geometry for compound block",
    ),
    TestCase(
        id="io-010",
        tool="rhino_block_create",
        params={"ids": ["PLACEHOLDER", "PLACEHOLDER"], "name": "TestBlock", "basePoint": [800, 0, 0]},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_11_IO,
        description="Create block definition from multiple objects",
        intent="create block definition",
        tags=["io", "block"],
        depends_on=["io-008", "io-009"],
        learn_on_success=(
            "rhino_block_create creates a reusable block definition. "
            "Requires object IDs, block name, and base point. "
            "Base point becomes the insertion point for block instances. "
            "By default, replaces source objects with a block instance."
        ),
    ),
    TestCase(
        id="io-011",
        tool="rhino_create",
        params={"type": "CIRCLE", "center": [850, 0, 0], "radius": 10, "name": "BlockKeepCircle"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_11_IO,
        description="Create circle to keep after block creation",
        intent="create geometry for block with replaceWithInstance=false",
        tags=["io", "setup", "block"],
        learn_on_success="Setup for testing replaceWithInstance option",
    ),
    TestCase(
        id="io-012",
        tool="rhino_block_create",
        params={"ids": ["PLACEHOLDER"], "name": "KeepSourceBlock", "basePoint": [850, 0, 0], "replaceWithInstance": False},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_11_IO,
        description="Create block but keep original objects",
        intent="create block without replacing source",
        tags=["io", "block"],
        depends_on=["io-011"],
        learn_on_success=(
            "Set replaceWithInstance: false to keep original objects. "
            "Block definition is created but source geometry remains unchanged."
        ),
    ),
    TestCase(
        id="io-013",
        tool="rhino_block_create",
        params={"ids": [], "name": "EmptyBlock", "basePoint": [0, 0, 0]},
        expected=ExpectedOutcome.FAILURE,
        phase=TestPhase.PHASE_11_IO,
        description="Fail to create empty block",
        intent="test empty block error handling",
        tags=["io", "block", "error"],
        learn_on_failure="Cannot create block with no objects. Requires at least one geometry ID.",
    ),

    # -------------------------------------------------------------------------
    # rhino_export - Export geometry to files
    # -------------------------------------------------------------------------
    TestCase(
        id="io-014",
        tool="rhino_create",
        params={"type": "BOX", "origin": [900, 0, 0], "width": 10, "depth": 10, "height": 10, "name": "ExportBox"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_11_IO,
        description="Create box for export test",
        intent="create geometry for export",
        tags=["io", "setup", "export"],
        learn_on_success="Create geometry to export",
    ),
    TestCase(
        id="io-015",
        tool="rhino_export",
        params={"path": "C:/temp/test_export.3dm", "ids": ["PLACEHOLDER"]},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_11_IO,
        description="Export single object to 3dm file",
        intent="export geometry to Rhino file",
        tags=["io", "export", "3dm"],
        depends_on=["io-014"],
        learn_on_success=(
            "rhino_export saves objects to a file. "
            "Supports 3dm, obj, stl, dwg, dxf, step, iges formats. "
            "Provide path and array of object IDs to export."
        ),
    ),
    TestCase(
        id="io-016",
        tool="rhino_export",
        params={"path": "C:/temp/test_export.obj", "ids": ["PLACEHOLDER"]},
        expected=ExpectedOutcome.FAILURE,
        phase=TestPhase.PHASE_11_IO,
        description="Export to OBJ format (may fail depending on geometry)",
        intent="export geometry to OBJ file",
        tags=["io", "export", "obj"],
        depends_on=["io-014"],
        learn_on_failure=(
            "OBJ export may fail for certain geometry types. "
            "Works best with meshes. Breps may need conversion first."
        ),
    ),
    TestCase(
        id="io-017",
        tool="rhino_export",
        params={"path": "C:/temp/test_export.stl", "ids": ["PLACEHOLDER"]},
        expected=ExpectedOutcome.FAILURE,
        phase=TestPhase.PHASE_11_IO,
        description="Export to STL format (may fail depending on geometry)",
        intent="export geometry to STL file",
        tags=["io", "export", "stl"],
        depends_on=["io-014"],
        learn_on_failure=(
            "STL export may fail for non-mesh geometry. "
            "Convert Breps to meshes first, or use 3dm format."
        ),
    ),
    TestCase(
        id="io-018",
        tool="rhino_select",
        params={"ids": ["PLACEHOLDER"]},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_11_IO,
        description="Select object for selection-based export",
        intent="setup for selection export",
        tags=["io", "setup", "export"],
        depends_on=["io-014"],
        learn_on_success="Select object before export with selection option",
    ),
    TestCase(
        id="io-019",
        tool="rhino_export",
        params={"path": "C:/temp/test_export_selection.3dm", "selection": True},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_11_IO,
        description="Export selected objects",
        intent="export using selection",
        tags=["io", "export", "selection"],
        depends_on=["io-018"],
        learn_on_success=(
            "Use selection: true to export currently selected objects. "
            "Alternative to providing explicit IDs array."
        ),
    ),
    TestCase(
        id="io-020",
        tool="rhino_export",
        params={"path": "C:/invalid/path/export.3dm", "ids": ["PLACEHOLDER"]},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_11_IO,
        description="Export to path (Rhino creates directories)",
        intent="test export path handling",
        tags=["io", "export"],
        depends_on=["io-014"],
        learn_on_success=(
            "Rhino may create directories if they don't exist. "
            "Export generally succeeds if the drive is writable."
        ),
    ),

    # -------------------------------------------------------------------------
    # rhino_import - Import files
    # -------------------------------------------------------------------------
    TestCase(
        id="io-021",
        tool="rhino_import",
        params={"path": "C:/temp/test_export.3dm"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_11_IO,
        description="Import 3dm file",
        intent="import Rhino file",
        tags=["io", "import", "3dm"],
        depends_on=["io-015"],
        learn_on_success=(
            "rhino_import loads geometry from a file into current document. "
            "Supports 3dm, obj, stl, dwg, dxf, step, iges formats. "
            "Imported objects are added to the document."
        ),
    ),
    TestCase(
        id="io-022",
        tool="rhino_import",
        params={"path": "C:/temp/test_export.obj"},
        expected=ExpectedOutcome.FAILURE,
        phase=TestPhase.PHASE_11_IO,
        description="Import OBJ file (depends on successful export)",
        intent="import OBJ file",
        tags=["io", "import", "obj"],
        depends_on=["io-016"],
        learn_on_failure="OBJ import fails if file doesn't exist (export failed).",
    ),
    TestCase(
        id="io-023",
        tool="rhino_import",
        params={"path": "C:/temp/test_export.stl"},
        expected=ExpectedOutcome.FAILURE,
        phase=TestPhase.PHASE_11_IO,
        description="Import STL file (depends on successful export)",
        intent="import STL file",
        tags=["io", "import", "stl"],
        depends_on=["io-017"],
        learn_on_failure="STL import fails if file doesn't exist (export failed).",
    ),
    TestCase(
        id="io-024",
        tool="rhino_import",
        params={"path": "C:/temp/test_export.3dm", "targetLayer": "ImportedObjects"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_11_IO,
        description="Import to specific layer",
        intent="import with target layer",
        tags=["io", "import", "layer"],
        depends_on=["io-015"],
        learn_on_success=(
            "Use targetLayer to place imported objects on a specific layer. "
            "Layer is created if it doesn't exist."
        ),
    ),
    TestCase(
        id="io-025",
        tool="rhino_import",
        params={"path": "C:/nonexistent/file.3dm"},
        expected=ExpectedOutcome.FAILURE,
        phase=TestPhase.PHASE_11_IO,
        description="Fail import of nonexistent file",
        intent="test missing file error handling",
        tags=["io", "import", "error"],
        learn_on_failure="Import fails if file doesn't exist. Verify path before importing.",
    ),
    TestCase(
        id="io-026",
        tool="rhino_import",
        params={"path": "C:/temp/test_export.xyz"},
        expected=ExpectedOutcome.FAILURE,
        phase=TestPhase.PHASE_11_IO,
        description="Fail import of unsupported format",
        intent="test unsupported format error handling",
        tags=["io", "import", "error"],
        learn_on_failure=(
            "Import fails for unsupported file formats. "
            "Supported: 3dm, obj, stl, dwg, dxf, step, iges."
        ),
    ),
]


# =============================================================================
# PHASE 12: Annotations, Materials, Viewport, and Instances
# =============================================================================

PHASE_12_TESTS = [
    # -------------------------------------------------------------------------
    # rhino_text - Text annotations
    # -------------------------------------------------------------------------
    TestCase(
        id="ann-001",
        tool="rhino_text",
        params={"text": "Hello Rhino", "point": [1000, 0, 0], "height": 5},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_12_EDGE,
        description="Create basic text annotation",
        intent="create text in model",
        tags=["annotation", "text"],
        learn_on_success=(
            "rhino_text creates a text annotation at a point. "
            "Requires text content, point [x,y,z], and height. "
            "Text is placed in the XY plane by default."
        ),
    ),
    TestCase(
        id="ann-002",
        tool="rhino_text",
        params={"text": "Bold Italic", "point": [1020, 0, 0], "height": 5, "bold": True, "italic": True},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_12_EDGE,
        description="Create styled text",
        intent="create bold italic text",
        tags=["annotation", "text", "style"],
        learn_on_success="Use bold: true and italic: true for styled text.",
    ),
    TestCase(
        id="ann-003",
        tool="rhino_text",
        params={"text": "Named Text", "point": [1040, 0, 0], "height": 5, "name": "MyTextLabel"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_12_EDGE,
        description="Create named text annotation",
        intent="create text with object name",
        tags=["annotation", "text", "naming"],
        learn_on_success="Use name parameter to set the object name for the text.",
    ),
    TestCase(
        id="ann-004",
        tool="rhino_text",
        params={"text": "", "point": [1060, 0, 0], "height": 5},
        expected=ExpectedOutcome.FAILURE,
        phase=TestPhase.PHASE_12_EDGE,
        description="Fail to create empty text",
        intent="test empty text error handling",
        tags=["annotation", "text", "error"],
        learn_on_failure="Empty text string fails. Text content is required.",
    ),

    # -------------------------------------------------------------------------
    # rhino_dimension - Dimension annotations
    # -------------------------------------------------------------------------
    TestCase(
        id="ann-005",
        tool="rhino_create",
        params={"type": "LINE", "start": [1100, 0, 0], "end": [1150, 0, 0], "name": "DimensionLine"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_12_EDGE,
        description="Create line for dimension test",
        intent="setup line for dimensioning",
        tags=["annotation", "setup", "dimension"],
        learn_on_success="Create line to dimension",
    ),
    TestCase(
        id="ann-006",
        tool="rhino_dimension",
        params={"type": "DIMENSION_LINEAR", "start": [1100, 0, 0], "end": [1150, 0, 0], "offset": 10},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_12_EDGE,
        description="Create linear dimension",
        intent="create linear dimension",
        tags=["annotation", "dimension", "linear"],
        learn_on_success=(
            "DIMENSION_LINEAR creates a horizontal/vertical dimension. "
            "Requires start point, end point, and offset distance. "
            "Offset is the distance from the line to the dimension."
        ),
    ),
    TestCase(
        id="ann-007",
        tool="rhino_create",
        params={"type": "CIRCLE", "center": [1200, 0, 0], "radius": 15, "name": "DimensionCircle"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_12_EDGE,
        description="Create circle for radius dimension",
        intent="setup circle for radius dimension",
        tags=["annotation", "setup", "dimension"],
        learn_on_success="Create circle to add radius dimension",
    ),
    TestCase(
        id="ann-008",
        tool="rhino_dimension",
        params={"type": "DIMENSION_RADIUS", "curveId": "PLACEHOLDER", "anglePoint": [1215, 0, 0]},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_12_EDGE,
        description="Create radius dimension on circle",
        intent="create radius dimension",
        tags=["annotation", "dimension", "radius"],
        depends_on=["ann-007"],
        learn_on_success=(
            "DIMENSION_RADIUS dimensions a curve's radius. "
            "Requires curveId (circle/arc GUID) and anglePoint (where to place dimension)."
        ),
    ),
    TestCase(
        id="ann-009",
        tool="rhino_dimension",
        params={"type": "DIMENSION_ANGLE", "center": [1250, 0, 0], "start": [1260, 0, 0], "end": [1250, 10, 0], "dimLocation": [1258, 8, 0]},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_12_EDGE,
        description="Create angle dimension",
        intent="create angle dimension",
        tags=["annotation", "dimension", "angle"],
        learn_on_success=(
            "DIMENSION_ANGLE measures angle between two lines from a center point. "
            "Requires center, start point, end point, and dimLocation for arc placement."
        ),
    ),

    # -------------------------------------------------------------------------
    # rhino_material_ops - Material operations
    # -------------------------------------------------------------------------
    TestCase(
        id="ann-010",
        tool="rhino_material_ops",
        params={"action": "list"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_12_EDGE,
        description="List all materials",
        intent="list materials in document",
        tags=["material", "list"],
        learn_on_success=(
            "rhino_material_ops with action: 'list' returns all materials. "
            "Returns array of material names and properties."
        ),
    ),
    TestCase(
        id="ann-011",
        tool="rhino_material_ops",
        params={"action": "create", "name": "RedMaterial", "color": [255, 0, 0]},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_12_EDGE,
        description="Create red material",
        intent="create new material",
        tags=["material", "create"],
        learn_on_success=(
            "Create material with action: 'create', name, and color [r,g,b]. "
            "Color values are 0-255. Material can be assigned to objects."
        ),
    ),
    TestCase(
        id="ann-012",
        tool="rhino_material_ops",
        params={"action": "create", "name": "GlassMaterial", "color": [200, 200, 255], "transparency": 0.8},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_12_EDGE,
        description="Create transparent material",
        intent="create material with transparency",
        tags=["material", "create", "transparency"],
        learn_on_success="Use transparency (0-1) to create glass-like materials. 0=opaque, 1=fully transparent.",
    ),
    TestCase(
        id="ann-013",
        tool="rhino_create",
        params={"type": "BOX", "origin": [1300, 0, 0], "width": 10, "depth": 10, "height": 10, "name": "MaterialBox"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_12_EDGE,
        description="Create box for material assignment",
        intent="create geometry for material test",
        tags=["material", "setup"],
        learn_on_success="Create geometry to assign material to",
    ),
    TestCase(
        id="ann-014",
        tool="rhino_material_ops",
        params={"action": "assign", "name": "RedMaterial", "id": "PLACEHOLDER"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_12_EDGE,
        description="Assign material to object",
        intent="assign material to geometry",
        tags=["material", "assign"],
        depends_on=["ann-011", "ann-013"],
        learn_on_success=(
            "Assign material with action: 'assign', material name, and object id. "
            "Can also use 'ids' array for multiple objects."
        ),
    ),
    TestCase(
        id="ann-015",
        tool="rhino_material_ops",
        params={"action": "delete", "name": "GlassMaterial"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_12_EDGE,
        description="Delete material",
        intent="remove material from document",
        tags=["material", "delete"],
        depends_on=["ann-012"],
        learn_on_success="Delete material with action: 'delete' and material name.",
    ),
    TestCase(
        id="ann-016",
        tool="rhino_material_ops",
        params={"action": "assign", "name": "NonExistentMaterial", "id": "PLACEHOLDER"},
        expected=ExpectedOutcome.FAILURE,
        phase=TestPhase.PHASE_12_EDGE,
        description="Fail to assign non-existent material",
        intent="test material assignment error",
        tags=["material", "error"],
        depends_on=["ann-013"],
        learn_on_failure="Assigning non-existent material fails. Create material first.",
    ),

    # -------------------------------------------------------------------------
    # rhino_viewport - Viewport capture
    # -------------------------------------------------------------------------
    TestCase(
        id="ann-017",
        tool="rhino_viewport",
        params={},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_12_EDGE,
        description="Capture default viewport",
        intent="capture viewport image",
        tags=["viewport", "capture"],
        learn_on_success=(
            "rhino_viewport captures the current viewport as base64 PNG. "
            "Default size is 800x600. Returns image data for analysis."
        ),
    ),
    TestCase(
        id="ann-018",
        tool="rhino_viewport",
        params={"width": 1920, "height": 1080},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_12_EDGE,
        description="Capture high-resolution viewport",
        intent="capture large viewport image",
        tags=["viewport", "capture", "resolution"],
        learn_on_success="Use width and height to set capture resolution.",
    ),
    TestCase(
        id="ann-019",
        tool="rhino_viewport",
        params={"view": "Top"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_12_EDGE,
        description="Capture Top view",
        intent="capture specific viewport",
        tags=["viewport", "capture", "view"],
        learn_on_success="Use view parameter to capture specific view: 'Top', 'Front', 'Right', 'Perspective'.",
    ),
    TestCase(
        id="ann-020",
        tool="rhino_viewport",
        params={"view": "Perspective", "width": 800, "height": 600},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_12_EDGE,
        description="Capture Perspective view with size",
        intent="capture perspective viewport",
        tags=["viewport", "capture", "perspective"],
        learn_on_success="Combine view name with dimensions for precise control.",
    ),

    # -------------------------------------------------------------------------
    # rhino_instances - Multi-instance discovery
    # -------------------------------------------------------------------------
    TestCase(
        id="ann-021",
        tool="rhino_instances",
        params={},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_12_EDGE,
        description="Discover running Rhino instances",
        intent="list Rhino instances",
        tags=["instances", "discovery"],
        learn_on_success=(
            "rhino_instances discovers all running Rhino instances with the Rook plugin loaded. "
            "Returns port, process ID, start time, and document name for each. "
            "Use for multi-Rhino workflows."
        ),
    ),

    # -------------------------------------------------------------------------
    # Edge cases and cleanup
    # -------------------------------------------------------------------------
    TestCase(
        id="ann-022",
        tool="rhino_dimension",
        params={"type": "INVALID_TYPE", "start": [0, 0, 0], "end": [10, 0, 0]},
        expected=ExpectedOutcome.FAILURE,
        phase=TestPhase.PHASE_12_EDGE,
        description="Fail with invalid dimension type",
        intent="test invalid dimension type error",
        tags=["annotation", "dimension", "error"],
        learn_on_failure=(
            "Invalid dimension types fail. Valid types: "
            "DIMENSION_LINEAR, DIMENSION_ALIGNED, DIMENSION_RADIUS, DIMENSION_DIAMETER, DIMENSION_ANGLE."
        ),
    ),
    TestCase(
        id="ann-023",
        tool="rhino_material_ops",
        params={"action": "invalid"},
        expected=ExpectedOutcome.FAILURE,
        phase=TestPhase.PHASE_12_EDGE,
        description="Fail with invalid material action",
        intent="test invalid action error",
        tags=["material", "error"],
        learn_on_failure="Invalid actions fail. Valid: list, create, delete, assign.",
    ),
]


# =============================================================================
# PHASE 13: Block Operations (rhino_blocks, rhino_block_create, rhino_block_insert, rhino_block_explode, rhino_block_delete)
# =============================================================================

PHASE_13_TESTS = [
    # -------------------------------------------------------------------------
    # rhino_blocks - List block definitions
    # -------------------------------------------------------------------------
    TestCase(
        id="block-001",
        tool="rhino_blocks",
        params={},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_13_BLOCKS,
        description="List all block definitions",
        intent="list blocks in document",
        tags=["block", "list"],
        learn_on_success=(
            "rhino_blocks returns all block definitions in the document. "
            "Each block includes: index, id, name, description, objectCount, instanceCount. "
            "Use this to discover available blocks before inserting."
        ),
    ),

    # -------------------------------------------------------------------------
    # Setup: Create geometry for block operations
    # -------------------------------------------------------------------------
    TestCase(
        id="block-002",
        tool="rhino_create",
        params={"type": "BOX", "origin": [1400, 0, 0], "width": 10, "depth": 10, "height": 10, "name": "BlockSrcBox1"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_13_BLOCKS,
        description="Create first box for block",
        intent="create geometry for block definition",
        tags=["block", "setup"],
        learn_on_success="Create geometry to include in block definition",
    ),
    TestCase(
        id="block-003",
        tool="rhino_create",
        params={"type": "SPHERE", "center": [1420, 5, 5], "radius": 3, "name": "BlockSrcSphere1"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_13_BLOCKS,
        description="Create sphere for block",
        intent="create additional geometry for block",
        tags=["block", "setup"],
        learn_on_success="Add multiple geometry types to block definition",
    ),

    # -------------------------------------------------------------------------
    # rhino_block_create - Create block definitions
    # -------------------------------------------------------------------------
    TestCase(
        id="block-004",
        tool="rhino_block_create",
        params={"ids": ["PLACEHOLDER", "PLACEHOLDER"], "name": "CompoundBlock", "basePoint": [1400, 0, 0]},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_13_BLOCKS,
        description="Create block from multiple objects",
        intent="create block definition",
        tags=["block", "create"],
        depends_on=["block-002", "block-003"],
        learn_on_success=(
            "rhino_block_create creates a reusable block definition. "
            "Requires: ids (object GUIDs), name (unique block name), basePoint (insertion point). "
            "By default, source objects are replaced with a block instance (replaceWithInstance: true)."
        ),
    ),
    TestCase(
        id="block-005",
        tool="rhino_create",
        params={"type": "CYLINDER", "center": [1450, 0, 0], "radius": 5, "height": 15, "name": "BlockSrcCyl"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_13_BLOCKS,
        description="Create cylinder for block",
        intent="create geometry for single-object block",
        tags=["block", "setup"],
        learn_on_success="Setup for single-object block creation",
    ),
    TestCase(
        id="block-006",
        tool="rhino_block_create",
        params={"ids": ["PLACEHOLDER"], "name": "CylinderBlock", "basePoint": [1450, 0, 0], "replaceWithInstance": True},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_13_BLOCKS,
        description="Create block with single object, replace source",
        intent="create block and replace source geometry",
        tags=["block", "create"],
        depends_on=["block-005"],
        learn_on_success="replaceWithInstance: true (default) replaces source objects with block instance",
    ),
    TestCase(
        id="block-007",
        tool="rhino_create",
        params={"type": "CONE", "center": [1480, 0, 0], "radius": 8, "height": 12, "name": "BlockSrcCone"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_13_BLOCKS,
        description="Create cone for block (keep source)",
        intent="create geometry for block without replacement",
        tags=["block", "setup"],
        learn_on_success="Setup for block creation with replaceWithInstance: false",
    ),
    TestCase(
        id="block-008",
        tool="rhino_block_create",
        params={"ids": ["PLACEHOLDER"], "name": "ConeBlockKeep", "basePoint": [1480, 0, 0], "replaceWithInstance": False},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_13_BLOCKS,
        description="Create block but keep source geometry",
        intent="create block without replacing source",
        tags=["block", "create"],
        depends_on=["block-007"],
        learn_on_success=(
            "replaceWithInstance: false keeps original objects after block creation. "
            "Block definition is created but source geometry remains in place."
        ),
    ),
    TestCase(
        id="block-009",
        tool="rhino_block_create",
        params={"ids": [], "name": "EmptyBlock", "basePoint": [0, 0, 0]},
        expected=ExpectedOutcome.FAILURE,
        phase=TestPhase.PHASE_13_BLOCKS,
        description="Fail to create empty block",
        intent="handle empty block error",
        tags=["block", "create", "error"],
        learn_on_failure="Cannot create block with no objects. Requires at least one geometry ID.",
    ),
    TestCase(
        id="block-010",
        tool="rhino_block_create",
        params={"ids": ["invalid-guid"], "name": "InvalidBlock", "basePoint": [0, 0, 0]},
        expected=ExpectedOutcome.FAILURE,
        phase=TestPhase.PHASE_13_BLOCKS,
        description="Fail to create block with invalid ID",
        intent="handle invalid ID in block creation",
        tags=["block", "create", "error"],
        learn_on_failure="Invalid object GUIDs are rejected. Verify objects exist before creating block.",
    ),

    # -------------------------------------------------------------------------
    # rhino_block_insert - Insert block instances
    # -------------------------------------------------------------------------
    TestCase(
        id="block-011",
        tool="rhino_block_insert",
        params={"name": "CompoundBlock", "point": [1500, 0, 0]},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_13_BLOCKS,
        description="Insert block at point",
        intent="insert block instance",
        tags=["block", "insert"],
        depends_on=["block-004"],
        learn_on_success=(
            "rhino_block_insert creates an instance of a block definition. "
            "Requires: name (block name) and point [x, y, z] (insertion location). "
            "Returns the instance GUID."
        ),
    ),
    TestCase(
        id="block-012",
        tool="rhino_block_insert",
        params={"name": "CompoundBlock", "point": [1550, 0, 0], "scale": 2.0},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_13_BLOCKS,
        description="Insert block with scale factor",
        intent="insert scaled block instance",
        tags=["block", "insert", "scale"],
        depends_on=["block-004"],
        learn_on_success="scale parameter applies uniform scaling. scale: 2.0 doubles the block size.",
    ),
    TestCase(
        id="block-013",
        tool="rhino_block_insert",
        params={"name": "CompoundBlock", "point": [1600, 0, 0], "rotation": 45},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_13_BLOCKS,
        description="Insert block with rotation",
        intent="insert rotated block instance",
        tags=["block", "insert", "rotation"],
        depends_on=["block-004"],
        learn_on_success="rotation parameter rotates around Z axis in degrees. rotation: 45 rotates 45 degrees.",
    ),
    TestCase(
        id="block-014",
        tool="rhino_block_insert",
        params={"name": "CompoundBlock", "point": [1650, 0, 0], "scale": 0.5, "rotation": 90},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_13_BLOCKS,
        description="Insert block with both scale and rotation",
        intent="insert scaled and rotated block",
        tags=["block", "insert", "scale", "rotation"],
        depends_on=["block-004"],
        learn_on_success="Combine scale and rotation for complex transformations. Applied in order: scale then rotate.",
    ),
    TestCase(
        id="block-015",
        tool="rhino_block_insert",
        params={"name": "CylinderBlock", "point": [1700, 0, 0]},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_13_BLOCKS,
        description="Insert second block type",
        intent="insert different block definition",
        tags=["block", "insert"],
        depends_on=["block-006"],
        learn_on_success="Can insert any block definition by name. Each insert creates a new instance.",
    ),
    TestCase(
        id="block-016",
        tool="rhino_block_insert",
        params={"name": "NonExistentBlock", "point": [0, 0, 0]},
        expected=ExpectedOutcome.FAILURE,
        phase=TestPhase.PHASE_13_BLOCKS,
        description="Fail to insert non-existent block",
        intent="handle missing block definition",
        tags=["block", "insert", "error"],
        learn_on_failure="Insert fails if block name doesn't exist. Use rhino_blocks to list available blocks.",
    ),

    # -------------------------------------------------------------------------
    # rhino_block_explode - Explode block instances
    # -------------------------------------------------------------------------
    TestCase(
        id="block-017",
        tool="rhino_block_insert",
        params={"name": "CompoundBlock", "point": [1750, 0, 0]},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_13_BLOCKS,
        description="Insert block to explode",
        intent="create instance for explode test",
        tags=["block", "setup", "explode"],
        depends_on=["block-004"],
        learn_on_success="Insert block instance to test explode operation",
    ),
    TestCase(
        id="block-018",
        tool="rhino_block_explode",
        params={"id": "PLACEHOLDER"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_13_BLOCKS,
        description="Explode block instance",
        intent="explode block into geometry",
        tags=["block", "explode"],
        depends_on=["block-017"],
        learn_on_success=(
            "rhino_block_explode breaks a block instance into individual geometry objects. "
            "Returns createdCount and createdIds array. "
            "Block definition remains intact - only the instance is exploded."
        ),
    ),
    TestCase(
        id="block-019",
        tool="rhino_block_explode",
        params={"id": "invalid-guid"},
        expected=ExpectedOutcome.FAILURE,
        phase=TestPhase.PHASE_13_BLOCKS,
        description="Fail to explode invalid ID",
        intent="handle invalid explode ID",
        tags=["block", "explode", "error"],
        learn_on_failure="Explode fails for invalid GUIDs. Verify instance ID exists.",
    ),
    TestCase(
        id="block-020",
        tool="rhino_create",
        params={"type": "BOX", "origin": [1800, 0, 0], "width": 5, "depth": 5, "height": 5, "name": "NotABlock"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_13_BLOCKS,
        description="Create regular geometry (not a block)",
        intent="create non-block for explode test",
        tags=["block", "setup", "explode"],
        learn_on_success="Create regular geometry to test explode on non-block",
    ),
    TestCase(
        id="block-021",
        tool="rhino_block_explode",
        params={"id": "PLACEHOLDER"},
        expected=ExpectedOutcome.FAILURE,
        phase=TestPhase.PHASE_13_BLOCKS,
        description="Fail to explode non-block object",
        intent="handle explode of non-block",
        tags=["block", "explode", "error"],
        depends_on=["block-020"],
        learn_on_failure="Explode fails for regular geometry. Only block instances can be exploded.",
    ),

    # -------------------------------------------------------------------------
    # rhino_block_delete - Delete block definitions
    # -------------------------------------------------------------------------
    TestCase(
        id="block-022",
        tool="rhino_create",
        params={"type": "BOX", "origin": [1850, 0, 0], "width": 5, "depth": 5, "height": 5, "name": "DeleteBlockSrc"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_13_BLOCKS,
        description="Create geometry for deletable block",
        intent="setup for block deletion test",
        tags=["block", "setup", "delete"],
        learn_on_success="Create geometry for block to be deleted",
    ),
    TestCase(
        id="block-023",
        tool="rhino_block_create",
        params={"ids": ["PLACEHOLDER"], "name": "ToBeDeleted", "basePoint": [1850, 0, 0]},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_13_BLOCKS,
        description="Create block to delete",
        intent="create block for deletion test",
        tags=["block", "create", "delete"],
        depends_on=["block-022"],
        learn_on_success="Create block definition that will be deleted",
    ),
    TestCase(
        id="block-024",
        tool="rhino_block_insert",
        params={"name": "ToBeDeleted", "point": [1900, 0, 0]},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_13_BLOCKS,
        description="Insert instance of block to delete",
        intent="create instance before block deletion",
        tags=["block", "insert", "delete"],
        depends_on=["block-023"],
        learn_on_success="Insert instance to test deleteInstances option",
    ),
    TestCase(
        id="block-025",
        tool="rhino_block_delete",
        params={"name": "ToBeDeleted"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_13_BLOCKS,
        description="Delete block definition and instances",
        intent="delete block definition",
        tags=["block", "delete"],
        depends_on=["block-024"],
        learn_on_success=(
            "rhino_block_delete removes a block definition from the document. "
            "By default (deleteInstances: true), all instances are also deleted. "
            "Returns deletedBlock name, instancesDeleted count, instancesExisted count."
        ),
    ),
    TestCase(
        id="block-026",
        tool="rhino_create",
        params={"type": "SPHERE", "center": [1950, 0, 0], "radius": 5, "name": "KeepInstancesSrc"},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_13_BLOCKS,
        description="Create geometry for keep-instances test",
        intent="setup for deleteInstances: false test",
        tags=["block", "setup", "delete"],
        learn_on_success="Create geometry for testing deleteInstances option",
    ),
    TestCase(
        id="block-027",
        tool="rhino_block_create",
        params={"ids": ["PLACEHOLDER"], "name": "KeepInstancesBlock", "basePoint": [1950, 0, 0]},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_13_BLOCKS,
        description="Create block for keep-instances test",
        intent="create block for deleteInstances test",
        tags=["block", "create", "delete"],
        depends_on=["block-026"],
        learn_on_success="Create block to test deleting with instances kept",
    ),
    TestCase(
        id="block-028",
        tool="rhino_block_insert",
        params={"name": "KeepInstancesBlock", "point": [2000, 0, 0]},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_13_BLOCKS,
        description="Insert instance for keep-instances test",
        intent="create instance that should remain",
        tags=["block", "insert", "delete"],
        depends_on=["block-027"],
        learn_on_success="Insert instance that should not be deleted",
    ),
    TestCase(
        id="block-029",
        tool="rhino_block_delete",
        params={"name": "KeepInstancesBlock", "deleteInstances": False},
        expected=ExpectedOutcome.EITHER,
        phase=TestPhase.PHASE_13_BLOCKS,
        description="Delete block but keep instances (may fail)",
        intent="delete block definition only",
        tags=["block", "delete"],
        depends_on=["block-028"],
        learn_on_success=(
            "deleteInstances: false attempts to delete only the definition. "
            "This may fail if instances exist (depends on Rhino version). "
            "Use with caution - orphaned instances may cause issues."
        ),
        learn_on_failure=(
            "Deleting block with deleteInstances: false may fail if instances exist. "
            "Rhino may require all instances to be deleted first. "
            "Use deleteInstances: true (default) for clean deletion."
        ),
    ),
    TestCase(
        id="block-030",
        tool="rhino_block_delete",
        params={"name": "NonExistentBlock"},
        expected=ExpectedOutcome.FAILURE,
        phase=TestPhase.PHASE_13_BLOCKS,
        description="Fail to delete non-existent block",
        intent="handle missing block deletion",
        tags=["block", "delete", "error"],
        learn_on_failure="Delete fails for non-existent block names. Use rhino_blocks to verify existence.",
    ),

    # -------------------------------------------------------------------------
    # Verify blocks list after operations
    # -------------------------------------------------------------------------
    TestCase(
        id="block-031",
        tool="rhino_blocks",
        params={},
        expected=ExpectedOutcome.SUCCESS,
        phase=TestPhase.PHASE_13_BLOCKS,
        description="List blocks after all operations",
        intent="verify block state after tests",
        tags=["block", "list", "verification"],
        learn_on_success="Use rhino_blocks to verify block definitions exist after operations.",
    ),
]


# =============================================================================
# Combine all phases
# =============================================================================

TOOL_TESTS = TestMatrix(
    cases=PHASE_1_TESTS + PHASE_2_TESTS + PHASE_3_TESTS + PHASE_4_TESTS + PHASE_5_TESTS + PHASE_6_TESTS + PHASE_7_TESTS + PHASE_8_TESTS + PHASE_9_TESTS + PHASE_10_TESTS + PHASE_11_TESTS + PHASE_12_TESTS + PHASE_13_TESTS
    # All phases defined
)


def get_test_count_by_phase() -> dict[TestPhase, int]:
    """Get count of tests per phase."""
    counts = {}
    for phase in TestPhase:
        counts[phase] = len(TOOL_TESTS.get_phase(phase))
    return counts


def get_total_test_count() -> int:
    """Get total number of defined tests."""
    return len(TOOL_TESTS.cases)
