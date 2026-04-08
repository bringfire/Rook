"""Auto-wiring logic for GH components using knowledge-based heuristics.

This module provides type-based auto-wiring for Grasshopper components:
- Determines output types from component names
- Matches inputs to compatible parameters
- Generates wiring plans for gh_execute_intent

Architecture:
- Uses name-based heuristics for type detection
- Type compatibility maps define valid connections
- Integrates with gh_knowledge for enhanced type info
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


# Type mappings: component name patterns -> output type
# Keys are lowercase, matched via 'in' check
COMPONENT_TYPE_MAP = {
    "slider": "number",
    "number": "number",
    "integer": "number",
    "panel": "text",
    "boolean": "boolean",
    "toggle": "boolean",
    "point": "point",
    "construct point": "point",
    "vector": "vector",
    "unit": "vector",
    "plane": "plane",
    "xy plane": "plane",
    "circle": "curve",
    "line": "curve",
    "arc": "curve",
    "polyline": "curve",
    "sphere": "surface",
    "box": "brep",
    "cylinder": "brep",
    "cone": "brep",
}

# Type compatibility: input type -> acceptable param types (lowercase)
# A slider (number) can connect to Number, Integer, Double, Float, or Generic params
TYPE_COMPATIBILITY = {
    "number": ["number", "integer", "double", "float", "generic"],
    "text": ["text", "string", "generic"],
    "boolean": ["boolean", "bool", "generic"],
    "point": ["point", "pt", "generic", "geometry"],
    "vector": ["vector", "vec", "generic"],
    "plane": ["plane", "pln", "generic"],
    "curve": ["curve", "crv", "generic", "geometry"],
    "surface": ["surface", "srf", "generic", "geometry", "brep"],
    "brep": ["brep", "generic", "geometry"],
}

# Input component types - these are typically sources (sliders, panels, etc.)
INPUT_COMPONENT_TYPES = {"number", "text", "boolean", "point", "vector", "plane"}


class GHAutoWirer:
    """Auto-wiring for GH components using type-based heuristics.

    This class provides methods for:
    1. Determining what output type a component provides
    2. Finding compatible parameter matches
    3. Generating wiring plans from created components

    Example:
        wirer = GHAutoWirer()

        # Determine types
        slider_type = wirer.determine_output_type({"name": "Number Slider"})
        # -> "number"

        # Find matching param
        match = wirer.find_param_match(
            {"name": "Number Slider"},
            [{"name": "Radius", "nickName": "R", "type": "Number"}],
            connected_params=set()
        )
        # -> {"name": "Radius", "nickName": "R", "type": "Number"}

        # Generate full plan
        plan = wirer.generate_wiring_plan(created_components, component_params)
        # -> [{"source_guid": "...", "target_guid": "...", "target_param": "R"}]
    """

    def determine_output_type(self, component: dict) -> Optional[str]:
        """Determine what output type a component provides.

        Uses name-based heuristics to identify output types.
        This is used to match sliders/panels/etc to compatible params.

        Args:
            component: Component dict with 'name' and optionally 'component_guid'

        Returns:
            Type string (number, text, point, etc.) or None if unknown
        """
        name = component.get("name", "").lower()

        for pattern, output_type in COMPONENT_TYPE_MAP.items():
            if pattern in name:
                return output_type

        return None

    def classify_component(self, component: dict) -> str:
        """Classify a component as 'input' or 'main'.

        Input components are sources (sliders, panels, points).
        Main components are processing components (Sphere, Cylinder, etc.).

        Args:
            component: Component dict

        Returns:
            "input" or "main"
        """
        output_type = self.determine_output_type(component)
        if output_type in INPUT_COMPONENT_TYPES:
            return "input"
        return "main"

    def find_param_match(
        self,
        input_comp: dict,
        main_params: list[dict],
        connected_params: set[str],
    ) -> Optional[dict]:
        """Find a matching parameter for an input component.

        Searches through the main component's parameters to find one
        that is compatible with the input's output type and not already connected.

        Args:
            input_comp: Input component (slider/panel/etc)
            main_params: List of main component's input parameters
                         Each param should have 'name', 'nickName', 'type'
            connected_params: Set of already-connected param nicknames to skip

        Returns:
            Matching param dict or None if no compatible param found
        """
        input_type = self.determine_output_type(input_comp)
        if not input_type:
            return None

        compatible_types = TYPE_COMPATIBILITY.get(input_type, [])

        for param in main_params:
            # Get param identifier (prefer nickName for wiring)
            nick = param.get("nickName", param.get("name", ""))
            if nick in connected_params:
                continue

            param_type = param.get("type", "").lower()

            # Check type compatibility - any compatible type keyword in param type
            if any(compat in param_type for compat in compatible_types):
                return param

        return None

    def generate_wiring_plan(
        self,
        created: list[dict],
        component_params: dict[str, dict],
    ) -> list[dict]:
        """Generate a wiring plan for created components.

        Separates components into inputs vs mains, then wires each input
        to compatible parameters on main components.

        Args:
            created: List of created components
                     [{"name": "...", "instance_guid": "...", "component_guid": "..."}, ...]
            component_params: Map of instance_guid -> {"inputs": [...], "outputs": [...]}
                             Each input should have name, nickName, type

        Returns:
            Wiring plan - list of connection specs:
            [{"source_guid": "...", "target_guid": "...", "target_param": "R"}, ...]
        """
        plan = []

        # Classify components into inputs vs mains
        inputs = []
        mains = []

        for comp in created:
            if self.classify_component(comp) == "input":
                inputs.append(comp)
            else:
                mains.append(comp)

        if not inputs or not mains:
            return plan

        # Track connected params per main component
        connected: dict[str, set[str]] = {
            main.get("instance_guid", ""): set() for main in mains
        }

        # Wire each main component
        for main in mains:
            main_guid = main.get("instance_guid", "")
            params_info = component_params.get(main_guid, {})
            main_params = params_info.get("inputs", [])

            for input_comp in inputs:
                input_guid = input_comp.get("instance_guid", "")

                match = self.find_param_match(
                    input_comp,
                    main_params,
                    connected[main_guid],
                )

                if match:
                    target_param = match.get("nickName", match.get("name", ""))
                    plan.append({
                        "source_guid": input_guid,
                        "target_guid": main_guid,
                        "target_param": target_param,
                    })
                    # Mark param as connected to prevent duplicate wiring
                    connected[main_guid].add(target_param)

        return plan

    def build_value_calls(
        self,
        created: list[dict],
        values_to_set: list[dict] | None,
    ) -> list[dict]:
        """Build value-setting calls from DSPy values_to_set.

        Args:
            created: List of created components
            values_to_set: DSPy output [{component_index, value}, ...]

        Returns:
            List of {guid, value} for gh_edit set_value operations
        """
        calls = []

        for val_spec in values_to_set or []:
            idx = val_spec.get("component_index", -1)
            value = val_spec.get("value")

            if 0 <= idx < len(created) and value is not None:
                comp = created[idx]
                calls.append({
                    "guid": comp.get("instance_guid", ""),
                    "value": value,
                })

        return calls