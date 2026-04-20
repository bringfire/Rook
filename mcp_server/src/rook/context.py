"""
Context Feature Extraction for Contextual MAB

This module extracts context features from intents and tool calls
for use in contextual multi-armed bandit pattern ranking.

Context Vector Structure (23 dimensions):
- Tool category (one-hot, 12 categories): indices 0-11
- Geometry type (multi-hot, 8 types): indices 10-17
- Operation characteristics (3 features): indices 20-22
  - param_count (normalized)
  - has_selection_dependency
  - is_destructive
"""

from typing import Any, Optional
import re


# =============================================================================
# Tool Category Mapping (12 categories)
# =============================================================================

TOOL_CATEGORIES = {
    # Create category - geometry creation tools
    "rhino_create": "create",
    "rhino_loft": "create",
    "rhino_sweep": "create",
    "rhino_extrude": "create",
    "rhino_text": "create",
    "rhino_dimension": "create",
    "rhino_block_create": "create",

    # Layer category - layer management
    "rhino_layers": "layer",
    "rhino_layer_create": "layer",
    "rhino_layer_create_batch": "layer",
    "rhino_layer_delete": "layer",
    "rhino_layer_visibility": "layer",
    "rhino_layer_lock": "layer",
    "rhino_layer_current": "layer",
    "rhino_layer_set_properties": "layer",
    "rhino_layer_set_properties_batch": "layer",
    "rhino_layer_rename": "layer",
    "rhino_layer_move_objects": "layer",
    "rhino_layer_merge": "layer",
    "rhino_layer_dependencies": "layer",

    # Material audit/purge
    "rhino_materials": "material",
    "rhino_material_purge": "material",

    # Linetype category
    "rhino_linetypes": "linetype",
    "rhino_linetype_purge": "linetype",

    # Block analysis
    "rhino_block_layer_census": "block",

    # Boolean category - boolean operations
    "rhino_boolean": "boolean",

    # Curve category - curve operations
    "rhino_curve_ops": "curve",

    # Transform category - transformation and copying
    "rhino_transform": "transform",
    "rhino_copy": "transform",
    "rhino_delete": "transform",
    "rhino_group": "transform",

    # Viewport category - view and capture
    "rhino_viewport": "viewport",

    # Measure category - measurement and analysis
    "rhino_measure_distance": "measure",
    "rhino_measure_area": "measure",
    "rhino_measure_volume": "measure",
    "rhino_measure_length": "measure",
    "rhino_measure_bbox": "measure",
    "rhino_measure_centroid": "measure",

    # Material category - materials and rendering
    "rhino_material_ops": "material",

    # Select category - selection operations
    "rhino_selection": "select",
    "rhino_select": "select",
    "rhino_select_by_type": "select",
    "rhino_select_by_name": "select",
    "rhino_select_all": "select",
    "rhino_select_none": "select",
    "rhino_select_invert": "select",

    # Document category - document operations and queries
    "rhino_document": "document",
    "rhino_document_ops": "document",
    "rhino_objects": "document",
    "rhino_geometry": "document",
    "rhino_ping": "document",
    "rhino_instances": "document",
    "rhino_execute": "document",
    "rhino_command": "document",
    "rhino_import": "document",
    "rhino_export": "document",

    # Knowledge tools - mapped to document category (metadata operations)
    "knowledge_query": "document",
    "knowledge_record": "document",

    # User-text tools - mapped to document category (metadata operations,
    # same bucket as knowledge-metadata calls above). Phase 2 PR-9
    # (object-level) + PR-10 (document-level + reserved-prefix denylist).
    "rhino_usertext_object_set": "document",
    "rhino_usertext_object_get": "document",
    "rhino_usertext_document_set": "document",
    "rhino_usertext_document_get": "document",
}

# Ordered list of categories for one-hot encoding
CATEGORY_ORDER = [
    "create",
    "layer",
    "boolean",
    "curve",
    "transform",
    "viewport",
    "measure",
    "material",
    "select",
    "document",
    "linetype",
    "block",
]

# Tools that require selected objects to function
SELECTION_DEPENDENT_TOOLS = {
    "rhino_transform",
    "rhino_copy",
    "rhino_delete",
    "rhino_group",
    "rhino_export",
    "rhino_block_create",
}

# Tools that modify or delete existing geometry
DESTRUCTIVE_TOOLS = {
    "rhino_delete",
    "rhino_boolean",
    "rhino_transform",
    "rhino_layer_delete",
    "rhino_document_ops",  # can create new doc
}


# =============================================================================
# Geometry Keywords (8 types)
# =============================================================================

GEOMETRY_KEYWORDS = {
    "point": ["point", "vertex", "location", "pt"],
    "line": ["line", "segment", "edge"],
    "polyline": ["polyline", "polygon", "pline"],
    "circle": ["circle", "ellipse", "oval"],
    "arc": ["arc", "curve segment"],
    "surface": ["surface", "plane", "face", "srf"],
    "brep": ["box", "sphere", "cylinder", "cone", "brep", "solid", "extrude",
             "loft", "sweep", "cube", "torus", "pipe"],
    "mesh": ["mesh", "triangulate", "polygon mesh"],
}

# Ordered list of geometry types for multi-hot encoding
GEOMETRY_ORDER = [
    "point",
    "line",
    "polyline",
    "circle",
    "arc",
    "surface",
    "brep",
    "mesh",
]


# =============================================================================
# Context Extraction Functions
# =============================================================================

def get_tool_category(tool_name: str) -> Optional[str]:
    """
    Get the category for a tool name.

    Args:
        tool_name: The MCP tool name (e.g., 'rhino_layer_create')

    Returns:
        Category string or None if tool is unknown
    """
    if not tool_name:
        return None
    return TOOL_CATEGORIES.get(tool_name)


def parse_intent(intent: Optional[str]) -> dict[str, list[str]]:
    """
    Parse an intent string to extract keywords.

    Args:
        intent: Natural language intent string

    Returns:
        Dictionary with:
        - geometry_keywords: List of geometry types mentioned
        - action_keywords: List of action verbs mentioned
        - modifiers: List of modifier words (nested, multiple, etc.)
    """
    result = {
        "geometry_keywords": [],
        "action_keywords": [],
        "modifiers": [],
    }

    if not intent:
        return result

    intent_lower = intent.lower()

    # Extract geometry keywords
    for geom_type, keywords in GEOMETRY_KEYWORDS.items():
        for keyword in keywords:
            if keyword in intent_lower:
                if geom_type not in result["geometry_keywords"]:
                    result["geometry_keywords"].append(geom_type)
                break

    # Extract action keywords
    action_verbs = [
        "create", "make", "add", "draw", "build",
        "delete", "remove", "erase", "destroy",
        "move", "translate", "shift",
        "rotate", "spin", "turn",
        "scale", "resize", "grow", "shrink",
        "copy", "duplicate", "clone",
        "select", "pick", "choose",
        "measure", "calculate", "compute",
        "export", "save", "output",
        "import", "load", "open",
        "modify", "change", "edit", "update",
        "hide", "show", "toggle",
        "lock", "unlock",
        "group", "ungroup",
        "join", "split", "divide", "trim", "extend",
        "loft", "sweep", "extrude",
        "boolean", "union", "difference", "intersect",
    ]

    for verb in action_verbs:
        if verb in intent_lower:
            if verb not in result["action_keywords"]:
                result["action_keywords"].append(verb)

    # Extract modifiers
    modifier_words = [
        "nested", "sublayer", "child", "parent",
        "multiple", "many", "several", "batch",
        "all", "every", "each",
        "new", "existing",
        "recursive", "hierarchy",
    ]

    for mod in modifier_words:
        if mod in intent_lower:
            if mod not in result["modifiers"]:
                result["modifiers"].append(mod)

    return result


def analyze_tool(tool_name: Optional[str], params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """
    Analyze a tool to extract contextual information.

    Args:
        tool_name: The MCP tool name
        params: Tool parameters (optional)

    Returns:
        Dictionary with:
        - category: Tool category string
        - param_count: Number of parameters
        - has_selection_dependency: Whether tool needs selected objects
        - is_destructive: Whether tool modifies/deletes geometry
    """
    result = {
        "category": None,
        "param_count": 0,
        "has_selection_dependency": False,
        "is_destructive": False,
    }

    if tool_name:
        result["category"] = get_tool_category(tool_name)
        result["has_selection_dependency"] = tool_name in SELECTION_DEPENDENT_TOOLS
        result["is_destructive"] = tool_name in DESTRUCTIVE_TOOLS

    if params:
        result["param_count"] = len(params)

    return result


def encode_context(
    intent: Optional[str] = None,
    tool: Optional[str] = None,
    params: Optional[dict[str, Any]] = None
) -> list[float]:
    """
    Encode operation context as a feature vector.

    Args:
        intent: Natural language intent string
        tool: MCP tool name
        params: Tool parameters

    Returns:
        23-dimensional normalized feature vector:
        - [0-11]: Tool category (one-hot, 12 dims)
        - [12-19]: Geometry types (multi-hot, 8 dims)
        - [20]: Param count (normalized 0-1)
        - [21]: Has selection dependency (0 or 1)
        - [22]: Is destructive (0 or 1)
    """
    # Initialize 23-dimensional vector
    context = [0.0] * 23

    # Parse intent
    intent_data = parse_intent(intent)

    # Analyze tool
    tool_data = analyze_tool(tool, params)

    # --- Tool category (one-hot, indices 0-11) ---
    category = tool_data["category"]
    if category and category in CATEGORY_ORDER:
        cat_idx = CATEGORY_ORDER.index(category)
        context[cat_idx] = 1.0

    # --- Geometry types (multi-hot, indices 12-19) ---
    num_categories = len(CATEGORY_ORDER)  # 12
    for geom_type in intent_data["geometry_keywords"]:
        if geom_type in GEOMETRY_ORDER:
            geom_idx = num_categories + GEOMETRY_ORDER.index(geom_type)
            context[geom_idx] = 1.0

    # Also detect geometry from tool params if present
    if params:
        geom_type_param = params.get("type", "")
        if isinstance(geom_type_param, str):
            geom_type_param = geom_type_param.lower()
            for geom_type, keywords in GEOMETRY_KEYWORDS.items():
                for keyword in keywords:
                    if keyword in geom_type_param:
                        geom_idx = num_categories + GEOMETRY_ORDER.index(geom_type)
                        context[geom_idx] = 1.0
                        break

    # --- Operation characteristics (indices 20-22) ---
    num_geom = len(GEOMETRY_ORDER)  # 8
    op_base = num_categories + num_geom  # 20

    # Param count normalized (assume max 10 params)
    param_count = tool_data["param_count"]
    context[op_base] = min(param_count / 10.0, 1.0)

    # Selection dependency
    context[op_base + 1] = 1.0 if tool_data["has_selection_dependency"] else 0.0

    # Destructive operation
    context[op_base + 2] = 1.0 if tool_data["is_destructive"] else 0.0

    return context


# =============================================================================
# Utility Functions
# =============================================================================

def get_all_tool_names() -> list[str]:
    """Get list of all known tool names."""
    return list(TOOL_CATEGORIES.keys())


def get_all_categories() -> list[str]:
    """Get list of all tool categories in order."""
    return CATEGORY_ORDER.copy()


def get_all_geometry_types() -> list[str]:
    """Get list of all geometry types in order."""
    return GEOMETRY_ORDER.copy()
