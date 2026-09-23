"""
Recipe Classification - DSPy-based pattern classification.

Provides:
- RecipeClassifier: DSPy signature for LLM-based classification
- classify_recipe_heuristic: Fallback heuristic classification
- classify_recipe: Main entry point (tries DSPy, falls back to heuristic)

Part of the Recipe Learning System.
"""

import logging

import dspy

# Learning boundary: configure DSPy once, on first import of any module that runs an LM.
from .dspy_config import ensure_configured as _ensure_dspy_configured
_ensure_dspy_configured()

logger = logging.getLogger("rook.recipe_classification")


# =============================================================================
# DSPy Signature
# =============================================================================

class RecipeClassifier(dspy.Signature):
    """Analyze a Grasshopper component graph and classify the pattern.

    You are analyzing a Grasshopper definition to understand what kind of
    parametric pattern it implements. Based on the components used and their
    connections, suggest a name, tags, and user intents that would match.
    """

    component_names: list[str] = dspy.InputField(
        desc="Names of components in the definition (e.g., ['Series', 'Sine', 'Pipe'])"
    )
    connection_summary: str = dspy.InputField(
        desc="Summary of data flow (e.g., 'Sliders feed Series, which feeds trig functions, then to Construct Point')"
    )

    suggested_name: str = dspy.OutputField(
        desc="Short snake_case name for the recipe (e.g., 'trigonometric_helix_pipe')"
    )
    tags: list[str] = dspy.OutputField(
        desc="Pattern type tags (e.g., ['trigonometric', 'parametric', 'pipe-output'])"
    )
    intents: list[str] = dspy.OutputField(
        desc="User phrases that would need this recipe (e.g., ['create a helix pipe', 'sine wave tube'])"
    )
    description: str = dspy.OutputField(
        desc="One-sentence description of what the recipe creates"
    )


# =============================================================================
# Heuristic Classification
# =============================================================================

# Pattern detection rules
PATTERN_SIGNATURES = {
    "trigonometric": {"requires_any": ["Sine", "Sin", "Cosine", "Cos", "Tangent", "Radians"]},
    "parametric": {"min_sliders": 2},
    "pipe-output": {"requires_any": ["Pipe"]},
    "surface-creation": {"requires_any": ["Loft", "Sweep", "Sweep1", "Sweep2", "Extrude"]},
    "point-sequence": {"requires_all": ["Construct Point"]},
    "boolean": {"requires_any": ["Solid Union", "Solid Difference", "Solid Intersection"]},
    "panelization": {"requires_any": ["Divide Surface", "Isotrim", "SubSrf"]},
    "curve-division": {"requires_any": ["Divide Curve", "Divide Length"]},
    "data-tree": {"requires_any": ["Graft", "Flatten", "Tree Branch", "Path Mapper"]},
}

# Component to intent mapping
COMPONENT_INTENTS = {
    "Sphere": ["create a sphere", "parametric sphere"],
    "Box": ["create a box", "parametric box"],
    "Pipe": ["pipe a curve", "create tube", "tubular form"],
    "Loft": ["loft curves", "surface from curves"],
    "Sweep": ["sweep profile", "sweep along rail"],
    "Interpolate": ["curve through points", "smooth curve"],
    "Series": ["number sequence", "range of values"],
    "Sine": ["sine wave", "oscillation", "sinusoidal"],
    "Cosine": ["cosine wave", "oscillation"],
}


def classify_recipe_heuristic(component_names: list[str]) -> dict:
    """Classify recipe using heuristic rules.

    Fallback when DSPy is unavailable or for fast classification.

    Args:
        component_names: List of component names in the recipe

    Returns:
        Dict with "tags", "suggested_name", "intents", "description"
    """
    names_lower = [n.lower() for n in component_names]
    names_set = set(component_names)

    tags = []
    intents = set()

    # Count sliders
    slider_count = sum(1 for n in component_names if "slider" in n.lower())

    # Check each pattern signature
    for tag, rules in PATTERN_SIGNATURES.items():
        matched = False

        if "requires_any" in rules:
            if any(req in names_set for req in rules["requires_any"]):
                matched = True

        if "requires_all" in rules:
            if all(req in names_set for req in rules["requires_all"]):
                matched = True

        if "min_sliders" in rules:
            if slider_count >= rules["min_sliders"]:
                matched = True

        if matched:
            tags.append(tag)

    # Collect intents from components
    for comp in component_names:
        if comp in COMPONENT_INTENTS:
            intents.update(COMPONENT_INTENTS[comp])

    # Generate suggested name from tags
    if tags:
        suggested_name = "_".join(tags[:3])  # Max 3 tags in name
    else:
        suggested_name = "custom_workflow"

    # Generate description
    if "trigonometric" in tags and "pipe-output" in tags:
        description = "Trigonometric curve piped into 3D geometry"
    elif "surface-creation" in tags:
        description = "Surface created from curves"
    elif "parametric" in tags:
        description = f"Parametric workflow with {slider_count} adjustable parameters"
    else:
        description = f"Grasshopper workflow with {len(component_names)} components"

    return {
        "tags": tags,
        "suggested_name": suggested_name,
        "intents": list(intents),
        "description": description,
    }


# =============================================================================
# Main Classification Function
# =============================================================================

def classify_recipe(
    component_names: list[str],
    connection_summary: str = "",
    use_dspy: bool = True,
) -> dict:
    """Classify a recipe using DSPy or heuristics.

    Args:
        component_names: List of component names
        connection_summary: Optional description of data flow
        use_dspy: Whether to try DSPy first (default: True)

    Returns:
        Dict with "tags", "suggested_name", "intents", "description"
    """
    if use_dspy:
        try:
            # Try DSPy classification
            classifier = dspy.Predict(RecipeClassifier)
            result = classifier(
                component_names=component_names,
                connection_summary=connection_summary or "Components connected in sequence",
            )
            return {
                "tags": result.tags if isinstance(result.tags, list) else [result.tags],
                "suggested_name": result.suggested_name,
                "intents": result.intents if isinstance(result.intents, list) else [result.intents],
                "description": result.description,
            }
        except (ValueError, TypeError, RuntimeError, AttributeError) as e:
            logger.warning(f"DSPy classification failed, using heuristics: {e}")

    # Fallback to heuristics
    return classify_recipe_heuristic(component_names)
