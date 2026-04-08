"""Geometry Factory - Dynamic geometry creation for command learning.

This module provides intelligent geometry preparation for commands that require
pre-existing geometry. Instead of hardcoding prerequisites, it:

1. Parses command prompts to understand what geometry is needed
2. Queries the knowledge graph to find commands that create that geometry
3. Uses learned patterns to create appropriate test geometry

This is recursive/meta: we use what we've learned to prepare for learning more.
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


# =============================================================================
# Geometry Type Detection from Prompts
# =============================================================================

@dataclass
class GeometryRequirement:
    """Represents what geometry a command needs."""
    geometry_type: str  # curve, surface, solid, point, edge, mesh, etc.
    plural: bool  # True if multiple objects needed
    raw_prompt: str  # Original prompt text
    selection_prompt: bool  # True if this is a "Select..." prompt


# Patterns to detect geometry types from Rhino prompts
GEOMETRY_PATTERNS = [
    # Curves (including polycurves which are curves with multiple segments)
    (r"Select\s+(?:open\s+)?curves?", "curve"),
    (r"Select\s+polycurves?", "polycurve"),  # For FilletCorners, etc.
    (r"Select\s+rail", "curve"),  # For Sweep, Pipe
    (r"Select\s+sweep\s+shapes?", "curve"),  # For Sweep profiles
    (r"Select\s+profile", "curve"),
    (r"Select\s+path", "curve"),
    (r"Select\s+(?:cutting\s+)?curves?", "curve"),

    # Surfaces
    (r"Select\s+surfaces?", "surface"),
    (r"Select\s+(?:surfaces?|polysurfaces?)\s+to\s+offset", "surface"),
    (r"Select\s+surfaces?\s+to\s+extrude", "surface"),
    (r"Select\s+face", "surface"),

    # Solids/Breps
    (r"Select\s+(?:solids?|polysurfaces?|breps?)", "solid"),
    (r"Select\s+objects?\s+to\s+(?:fillet|chamfer|shell)", "solid"),
    (r"Select\s+objects?\s+to\s+cap", "solid"),  # Open polysurface

    # Edges (sub-object)
    (r"Select\s+edges?", "edge"),

    # Points
    (r"Select\s+points?", "point"),
    (r"Select\s+point\s+clouds?", "pointcloud"),

    # Meshes
    (r"Select\s+mesh(?:es)?", "mesh"),

    # Generic objects (any geometry)
    (r"Select\s+objects?\s+to\s+(?:array|copy|move|rotate|scale|mirror)", "any"),
    (r"Select\s+objects?\s+to\s+(?:join|explode|group)", "any"),
    (r"Select\s+objects?", "any"),
]


def parse_prompt_for_geometry(prompt: str) -> Optional[GeometryRequirement]:
    """Parse a Rhino command prompt to determine what geometry is needed.

    Args:
        prompt: The prompt string from Rhino (e.g., "Select curves to revolve")

    Returns:
        GeometryRequirement if geometry selection is needed, None otherwise
    """
    if not prompt:
        return None

    prompt_lower = prompt.lower()

    # Check if this is a selection prompt
    if not prompt_lower.startswith("select"):
        return None

    # Try each pattern
    for pattern, geom_type in GEOMETRY_PATTERNS:
        match = re.search(pattern, prompt, re.IGNORECASE)
        if match:
            # Check if plural
            matched_text = match.group(0)
            plural = "s " in matched_text.lower() or matched_text.lower().endswith("s")

            return GeometryRequirement(
                geometry_type=geom_type,
                plural=plural,
                raw_prompt=prompt,
                selection_prompt=True
            )

    return None


# =============================================================================
# Geometry Type to Command Category Mapping
# =============================================================================

# Maps geometry types to the kinds of commands that create them
GEOMETRY_CREATORS = {
    "curve": {
        "categories": ["curves", "primitives"],
        "preferred_commands": [
            "-Circle",   # Simple, always works
            "-Line",     # Very simple
            "-Rectangle", # Closed curve
            "-Arc",      # Simple curve
            "-Ellipse",  # Another option
        ],
        "simple_creation": {
            "-Circle": ["0,0,0", "5"],
            "-Line": ["0,0,0", "10,0,0"],
            "-Rectangle": ["0,0,0", "10,10,0"],
        }
    },
    "polycurve": {
        # Polycurve is a curve with multiple segments - Rectangle is a perfect example
        "categories": ["curves", "primitives"],
        "preferred_commands": [
            "-Rectangle",  # 4-segment polycurve, perfect for FilletCorners
            "-Polygon",    # Multi-segment closed curve
        ],
        "simple_creation": {
            "-Rectangle": ["0,0,0", "10,10,0"],
            "-Polygon": ["_NumSides=6", "0,0,0", "5"],
        }
    },
    "surface": {
        "categories": ["surfaces"],
        "preferred_commands": [
            "-Plane",    # Simplest surface
            "-PlanarSrf", # From curves (needs curve first)
        ],
        "simple_creation": {
            "-Plane": ["0,0,0", "10,10,0"],
        }
    },
    "solid": {
        "categories": ["primitives", "solids"],
        "preferred_commands": [
            "-Box",      # Simple solid
            "-Sphere",   # Another simple solid
            "-Cylinder", # Good for edge operations
        ],
        "simple_creation": {
            "-Box": ["0,0,0", "10,10,0", "10"],
            "-Sphere": ["0,0,0", "5"],
            "-Cylinder": ["0,0,0", "5", "10"],
        }
    },
    "point": {
        "categories": ["points"],
        "preferred_commands": [
            "-Point",
            "-Points",
        ],
        "simple_creation": {
            "-Point": ["0,0,0"],
            "-Points": ["0,0,0", "5,0,0", "10,0,0", ""],
        }
    },
    "mesh": {
        "categories": ["mesh"],
        "preferred_commands": [
            "-Mesh",  # From other geometry
        ],
        "simple_creation": {}  # Needs solid first
    },
    "edge": {
        # Edges require a solid - we create a solid and note that edges must be sub-selected
        "categories": ["primitives"],
        "preferred_commands": [
            "-Box",  # Has nice edges
        ],
        "simple_creation": {
            "-Box": ["0,0,0", "10,10,0", "10"],
        },
        "note": "Edges are sub-objects of solids. Create solid, then select edges interactively."
    },
    "any": {
        # Any geometry - use simplest
        "categories": ["primitives"],
        "preferred_commands": [
            "-Box",
            "-Circle",
            "-Line",
        ],
        "simple_creation": {
            "-Box": ["0,0,0", "10,10,0", "10"],
            "-Circle": ["0,0,0", "5"],
            "-Line": ["0,0,0", "10,0,0"],
        }
    },
}


# =============================================================================
# Knowledge-Based Geometry Creation
# =============================================================================

class GeometryFactory:
    """Creates geometry dynamically using learned command knowledge."""

    def __init__(self, knowledge_store=None):
        """Initialize with optional knowledge store for learned patterns.

        Args:
            knowledge_store: KnowledgeStore instance for querying learned commands
        """
        self.knowledge_store = knowledge_store
        self._created_objects: List[str] = []  # Track created object GUIDs

    def get_creation_command(self, geometry_type: str) -> Optional[Dict[str, Any]]:
        """Get the best command to create a given geometry type.

        First tries to use learned knowledge, falls back to built-in mappings.

        Args:
            geometry_type: Type of geometry needed (curve, surface, solid, etc.)

        Returns:
            Dict with 'command' and 'inputs' keys, or None if unknown type
        """
        creator_info = GEOMETRY_CREATORS.get(geometry_type)
        if not creator_info:
            logger.warning(f"Unknown geometry type: {geometry_type}")
            return None

        # Try knowledge store first if available
        if self.knowledge_store:
            for cmd_name in creator_info["preferred_commands"]:
                # Strip leading dash for lookup
                lookup_name = cmd_name.lstrip("-")
                knowledge = self.knowledge_store.get(lookup_name)
                if knowledge:
                    # Use the default mode's syntax if available
                    modes = knowledge.get("modes", {})
                    if "default" in modes:
                        mode_info = modes["default"]
                        # Try to extract inputs from syntax or use simple_creation fallback
                        if cmd_name in creator_info.get("simple_creation", {}):
                            return {
                                "command": f"_-{lookup_name}",
                                "inputs": creator_info["simple_creation"][cmd_name],
                                "source": "knowledge+fallback"
                            }

        # Fall back to simple_creation
        simple = creator_info.get("simple_creation", {})
        if simple:
            # Use first available
            cmd_name = list(simple.keys())[0]
            return {
                "command": f"_{cmd_name}",
                "inputs": simple[cmd_name],
                "source": "builtin"
            }

        return None

    def get_creation_commands_for_prompt(self, prompt: str) -> Optional[Dict[str, Any]]:
        """Analyze a prompt and return how to create the needed geometry.

        Args:
            prompt: Rhino command prompt (e.g., "Select curves to revolve")

        Returns:
            Dict with creation info, or None if no geometry needed
        """
        requirement = parse_prompt_for_geometry(prompt)
        if not requirement:
            return None

        creation_cmd = self.get_creation_command(requirement.geometry_type)
        if not creation_cmd:
            return None

        return {
            "requirement": {
                "geometry_type": requirement.geometry_type,
                "plural": requirement.plural,
                "raw_prompt": requirement.raw_prompt,
            },
            "creation": creation_cmd,
            "note": GEOMETRY_CREATORS.get(requirement.geometry_type, {}).get("note"),
        }


# =============================================================================
# High-Level Functions for MCP Integration
# =============================================================================

def analyze_prompt(prompt: str) -> Dict[str, Any]:
    """Analyze a Rhino prompt and return geometry requirements.

    This is the main entry point for the MCP tool.

    Args:
        prompt: The prompt from Rhino

    Returns:
        Dict with analysis results
    """
    requirement = parse_prompt_for_geometry(prompt)

    if not requirement:
        return {
            "needs_geometry": False,
            "prompt": prompt,
        }

    factory = GeometryFactory()
    creation_info = factory.get_creation_command(requirement.geometry_type)

    result = {
        "needs_geometry": True,
        "prompt": prompt,
        "geometry_type": requirement.geometry_type,
        "plural": requirement.plural,
    }

    if creation_info:
        result["creation_command"] = creation_info["command"]
        result["creation_inputs"] = creation_info["inputs"]
        result["creation_source"] = creation_info["source"]

    note = GEOMETRY_CREATORS.get(requirement.geometry_type, {}).get("note")
    if note:
        result["note"] = note

    return result


def get_geometry_for_type(geometry_type: str, knowledge_store=None) -> Dict[str, Any]:
    """Get the command and inputs to create a specific geometry type.

    Args:
        geometry_type: curve, surface, solid, point, mesh, edge, any
        knowledge_store: Optional knowledge store for learned patterns

    Returns:
        Dict with command and inputs, or error info
    """
    factory = GeometryFactory(knowledge_store)
    creation_info = factory.get_creation_command(geometry_type)

    if not creation_info:
        return {
            "success": False,
            "error": f"Unknown geometry type: {geometry_type}",
            "known_types": list(GEOMETRY_CREATORS.keys()),
        }

    return {
        "success": True,
        "geometry_type": geometry_type,
        "command": creation_info["command"],
        "inputs": creation_info["inputs"],
        "source": creation_info["source"],
    }

