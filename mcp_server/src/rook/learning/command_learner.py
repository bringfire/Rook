"""Rhino Command Learning System with DSPy + MABWiser Integration.

This module provides systematic learning of Rhino command syntax patterns,
using DSPy for intelligent pattern extraction/consolidation and MABWiser
for intent-based command selection.

The learning loop:
1. Execute commands with observation capture
2. Use DSPy to extract structured patterns from raw dialogue
3. Consolidate multiple observations into canonical command knowledge
4. Train MABWiser to select commands based on user intent
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional, Any
import pickle

# DSPy imports
try:
    import dspy
    DSPY_AVAILABLE = True
except ImportError:
    DSPY_AVAILABLE = False

if DSPY_AVAILABLE:
    # Learning boundary: configure DSPy once, on first import of any module that runs an LM.
    from .dspy_config import ensure_configured as _ensure_dspy_configured
    _ensure_dspy_configured()


def is_dspy_configured() -> bool:
    """Check if DSPy has an LM configured."""
    if not DSPY_AVAILABLE:
        return False
    try:
        # Check if LM is configured
        return dspy.settings.lm is not None
    except Exception:
        return False

# MABWiser imports
try:
    from mabwiser.mab import MAB, LearningPolicy, NeighborhoodPolicy
    import numpy as np
    MABWISER_AVAILABLE = True
except ImportError:
    MABWISER_AVAILABLE = False

from .command_observer import (
    CommandObserver,
    CommandObservation,
    ObservationStore,
    DialogueStep,
    DEFAULT_OBSERVATION_STORE_PATH,
)

# Import unified CommandKnowledgeStore from meta-learning module
from .command_knowledge_store import (
    CommandKnowledgeStore,
    CommandKnowledge,
    ModeKnowledge,
)

# Type alias for backward compatibility
CommandPattern = CommandKnowledge

logger = logging.getLogger(__name__)


# =============================================================================
# Priority Commands to Learn
# =============================================================================

# Commands categorized by priority and type
# NEW FORMAT: Each variation is now a list of inputs for interactive mode
# Old format (deprecated): "variations": ["_-Box 0,0,0 10,10,0 5"]
# New format: "input_sequences": [["0,0,0", "10,10,0", "5"]]

COMMAND_LEARNING_QUEUE = {
    "priority_1_primitives": [
        # Basic 3D solids
        {"name": "Box", "command": "_-Box", "input_sequences": [
            ["0,0,0", "10,10,0", ""],  # Default height (press Enter)
            ["0,0,0", "10,10,0", "5"],  # Explicit height
            ["_Center", "5,5,0", "10,10,0", ""],  # Center mode
            ["_Diagonal", "0,0,0", "10,10,10"],  # Diagonal mode
        ], "legacy_variations": [
            "_-Box 0,0,0 10,10,0 _Enter",
            "_-Box 0,0,0 10,10,0 5",
            "_-Box _Center 5,5,0 10,10,0 _Enter",
            "_-Box _Diagonal 0,0,0 10,10,10",
        ]},
        {"name": "Sphere", "command": "_-Sphere", "input_sequences": [
            ["0,0,0", "5"],  # Center + radius
            ["_Diameter", "0,0,0", "10,0,0"],  # Diameter mode
            ["_3Point", "0,0,0", "5,0,0", "0,5,0"],  # 3Point mode
        ], "legacy_variations": [
            "_-Sphere 0,0,0 5",
            "_-Sphere _Diameter 0,0,0 10,0,0",
            "_-Sphere _3Point 0,0,0 5,0,0 0,5,0",
        ]},
        {"name": "Cylinder", "command": "_-Cylinder", "input_sequences": [
            ["0,0,0", "5", "10"],  # Center + radius + height
            ["_Diameter", "0,0,0", "10,0,0", "10"],  # Diameter mode
            ["_Vertical", "0,0,0", "5", "10"],  # Vertical mode
        ], "legacy_variations": [
            "_-Cylinder 0,0,0 5 10",
            "_-Cylinder _Diameter 0,0,0 10,0,0 10",
            "_-Cylinder _Vertical 0,0,0 5 10",
        ]},
        {"name": "Cone", "command": "_-Cone", "input_sequences": [
            ["0,0,0", "5", "10"],  # Center + radius + height
            ["_Vertical", "0,0,0", "5", "10"],  # Vertical mode
        ], "legacy_variations": [
            "_-Cone 0,0,0 5 10",
            "_-Cone _Vertical 0,0,0 5 10",
        ]},
        {"name": "Torus", "command": "_-Torus", "input_sequences": [
            ["0,0,0", "10", "3"],  # Center + major radius + minor radius
        ], "legacy_variations": [
            "_-Torus 0,0,0 10 3",
        ]},
    ],
    "priority_2_curves": [
        {"name": "Line", "command": "_-Line", "input_sequences": [
            ["0,0,0", "10,10,0"],  # Two points
            ["_Vertical", "0,0,0", "10"],  # Vertical mode
        ], "legacy_variations": [
            "_-Line 0,0,0 10,10,0",
            "_-Line _Vertical 0,0,0 10",
        ]},
        {"name": "Circle", "command": "_-Circle", "input_sequences": [
            ["0,0,0", "5"],  # Center + radius
            ["_Diameter", "0,0,0", "10,0,0"],  # Diameter mode
            ["_3Point", "0,0,0", "5,0,0", "0,5,0"],  # 3Point mode
        ], "legacy_variations": [
            "_-Circle 0,0,0 5",
            "_-Circle _Diameter 0,0,0 10,0,0",
            "_-Circle _3Point 0,0,0 5,0,0 0,5,0",
        ]},
        {"name": "Arc", "command": "_-Arc", "input_sequences": [
            ["0,0,0", "5,0,0", "10,0,0"],  # 3 points
            ["_Center", "0,0,0", "5,0,0", "0,5,0"],  # Center mode
        ], "legacy_variations": [
            "_-Arc 0,0,0 5,0,0 10,0,0",
            "_-Arc _Center 0,0,0 5,0,0 0,5,0",
        ]},
        {"name": "Polyline", "command": "_-Polyline", "input_sequences": [
            ["0,0,0", "10,0,0", "10,10,0", "0,10,0", ""],  # Multiple points + Enter
        ], "legacy_variations": [
            "_-Polyline 0,0,0 10,0,0 10,10,0 0,10,0 _Enter",
        ]},
        {"name": "Rectangle", "command": "_-Rectangle", "input_sequences": [
            ["0,0,0", "10,10,0"],  # Two corners
            ["_Center", "5,5,0", "10,10,0"],  # Center mode
        ], "legacy_variations": [
            "_-Rectangle 0,0,0 10,10,0",
            "_-Rectangle _Center 5,5,0 10,10,0",
        ]},
        {"name": "Ellipse", "command": "_-Ellipse", "input_sequences": [
            ["0,0,0", "10,0,0", "0,5,0"],  # Center + two axes
            ["_Center", "0,0,0", "10", "5"],  # Center mode with radii
        ], "legacy_variations": [
            "_-Ellipse 0,0,0 10,0,0 0,5,0",
            "_-Ellipse _Center 0,0,0 10 5",
        ]},
    ],
    "priority_3_surfaces": [
        {"name": "ExtrudeCrv", "command": "_-ExtrudeCrv", "requires_selection": True, "input_sequences": [
            ["0,0,10"],  # Direction + distance
        ], "legacy_variations": [
            "_-ExtrudeCrv _Pause 0,0,10",
        ]},
        {"name": "Loft", "command": "_-Loft", "requires_selection": True, "input_sequences": [
            [""],  # Just confirm
        ], "legacy_variations": [
            "_-Loft _Pause _Enter",
        ]},
        {"name": "PlanarSrf", "command": "_-PlanarSrf", "requires_selection": True, "input_sequences": [
            [],  # No additional input needed
        ], "legacy_variations": [
            "_-PlanarSrf _Pause",
        ]},
    ],
    "priority_4_transforms": [
        {"name": "Move", "command": "_-Move", "requires_selection": True, "input_sequences": [
            ["0,0,0", "10,0,0"],  # From point + to point
        ], "legacy_variations": [
            "_-Move _Pause 0,0,0 10,0,0",
        ]},
        {"name": "Copy", "command": "_-Copy", "requires_selection": True, "input_sequences": [
            ["0,0,0", "10,0,0", ""],  # From + to + Enter to finish
        ], "legacy_variations": [
            "_-Copy _Pause 0,0,0 10,0,0 _Enter",
        ]},
        {"name": "Rotate", "command": "_-Rotate", "requires_selection": True, "input_sequences": [
            ["0,0,0", "45"],  # Center + angle
        ], "legacy_variations": [
            "_-Rotate _Pause 0,0,0 45",
        ]},
        {"name": "Scale", "command": "_-Scale", "requires_selection": True, "input_sequences": [
            ["0,0,0", "2"],  # Center + scale factor
        ], "legacy_variations": [
            "_-Scale _Pause 0,0,0 2",
        ]},
        {"name": "Mirror", "command": "_-Mirror", "requires_selection": True, "input_sequences": [
            ["0,0,0", "0,1,0"],  # Mirror plane points
        ], "legacy_variations": [
            "_-Mirror _Pause 0,0,0 0,1,0",
        ]},
        {"name": "Array", "command": "_-Array", "requires_selection": True, "input_sequences": [
            ["_Rectangular", "3", "3", "1", "10", "10", "0"],  # Rectangular array
        ], "legacy_variations": [
            "_-Array _Pause _Rectangular 3 3 1 10 10 0",
        ]},
    ],
    "priority_5_booleans": [
        {"name": "BooleanUnion", "command": "_-BooleanUnion", "requires_selection": True, "input_sequences": [
            [],  # No additional input after selection
        ], "legacy_variations": [
            "_-BooleanUnion _Pause",
        ]},
        {"name": "BooleanDifference", "command": "_-BooleanDifference", "requires_selection": True, "input_sequences": [
            [],  # Uses pre-selected objects
        ], "legacy_variations": [
            "_-BooleanDifference _Pause _Pause",
        ]},
        {"name": "BooleanIntersection", "command": "_-BooleanIntersection", "requires_selection": True, "input_sequences": [
            [],  # Uses pre-selected objects
        ], "legacy_variations": [
            "_-BooleanIntersection _Pause",
        ]},
    ],
    "priority_6_editing": [
        {"name": "Trim", "command": "_-Trim", "requires_selection": True, "input_sequences": [
            [],  # Interactive selection
        ], "legacy_variations": [
            "_-Trim _Pause _Pause",
        ]},
        {"name": "Split", "command": "_-Split", "requires_selection": True, "input_sequences": [
            [],  # Interactive selection
        ], "legacy_variations": [
            "_-Split _Pause _Pause",
        ]},
        {"name": "Join", "command": "_-Join", "requires_selection": True, "input_sequences": [
            [],  # Uses pre-selected objects
        ], "legacy_variations": [
            "_-Join _Pause",
        ]},
        {"name": "Explode", "command": "_-Explode", "requires_selection": True, "input_sequences": [
            [],  # Uses pre-selected objects
        ], "legacy_variations": [
            "_-Explode _Pause",
        ]},
        {"name": "Fillet", "command": "_-Fillet", "requires_selection": True, "input_sequences": [
            ["_Radius", "2"],  # Set radius then select
        ], "legacy_variations": [
            "_-Fillet _Pause _Radius 2 _Pause",
        ]},
        {"name": "Chamfer", "command": "_-Chamfer", "requires_selection": True, "input_sequences": [
            ["_Distance", "2", "2"],  # Set distances
        ], "legacy_variations": [
            "_-Chamfer _Pause _Distance 2 2 _Pause",
        ]},
        {"name": "Offset", "command": "_-Offset", "requires_selection": True, "input_sequences": [
            ["5"],  # Offset distance
        ], "legacy_variations": [
            "_-Offset _Pause 5",
        ]},
    ],
}

# Keep old format for backwards compatibility
def get_legacy_variations(cmd_entry: dict) -> list[str]:
    """Get legacy variation strings from a command entry."""
    if "legacy_variations" in cmd_entry:
        return cmd_entry["legacy_variations"]
    elif "variations" in cmd_entry:
        return cmd_entry["variations"]
    return []


# =============================================================================
# Mode Extraction Functions (used by both DSPy and non-DSPy paths)
# =============================================================================

def extract_mode_from_syntax(syntax: str) -> str:
    """Extract mode from a full syntax string.

    Looks for the first token after the command name that:
    - Starts with underscore
    - Is not a coordinate (no commas)
    - Is not _Enter or _SelPrev or similar control keywords

    Examples:
    - "_-Box _Center 0,0,0 10,10,0" -> "center"
    - "_-Sphere _4Point 0,0,0 5,0,0 ..." -> "4point"
    - "_-Box 0,0,0 10,10,0 5" -> "default"
    """
    # Split on whitespace
    tokens = syntax.split()

    # Skip the command name (first token)
    for token in tokens[1:]:
        # Check if it's a mode keyword
        if token.startswith('_'):
            lower_token = token.lower()
            # Skip control/selection keywords
            if _is_control_keyword(lower_token):
                continue
            # Skip if it looks like a coordinate (has comma)
            if ',' in token:
                continue
            # This is likely a mode
            return token.lstrip('_').lower()

    return "default"


def _is_control_keyword(token_lower: str) -> bool:
    """Check if a token is a control/selection keyword (not a mode)."""
    # Control keywords that aren't modes - used for flow control and object selection
    control_keywords = {
        # Confirmation/cancellation
        '_enter', '_cancel', '_escape', '_esc',
        # Object selection keywords
        '_selprev', '_selall', '_selid', '_selnone', '_sellast',
        '_selcrv', '_selpt', '_selborder', '_seldup',
        # Interactive mode markers
        '_pause',
        # Yes/No toggles
        '_yes', '_no',
    }
    # Also skip if it starts with common selection prefixes followed by data
    if token_lower.startswith('_sel') and len(token_lower) > 4:
        return True
    return token_lower in control_keywords


def extract_mode_from_observation(obs) -> str:
    """Extract mode name from an observation's dialogue or full_syntax.

    Looks for mode keywords in:
    1. First dialogue input (if it starts with _ and is not a control keyword)
    2. Full syntax string (first token after command that starts with _)

    Returns the mode name (lowercase, without underscore) or "default".
    """
    # First try dialogue - if dialogue has steps and first input starts with _
    if obs.dialogue and len(obs.dialogue) > 0:
        for step in obs.dialogue:
            input_val = getattr(step, 'input_value', None)
            if input_val and input_val.startswith('_') and ',' not in input_val:
                lower_val = input_val.lower()
                # Skip control keywords - look for actual mode keyword
                if not _is_control_keyword(lower_val):
                    # This is a mode selection like "_4Point", "_Center"
                    return input_val.lstrip('_').lower()

    # Fall back to parsing full_syntax
    return extract_mode_from_syntax(obs.full_syntax)


# =============================================================================
# DSPy Signatures for Command Learning
# =============================================================================

if DSPY_AVAILABLE:

    class ExtractDialoguePattern(dspy.Signature):
        """Extract structured dialogue pattern from raw command history."""

        command_name: str = dspy.InputField(desc="The Rhino command name (e.g., 'Box')")
        full_syntax: str = dspy.InputField(desc="The complete command string that was executed")
        raw_history: str = dspy.InputField(desc="Raw command history text showing prompts and inputs")
        success: bool = dspy.InputField(desc="Whether the command succeeded")
        objects_created: int = dspy.InputField(desc="Number of objects created")

        mode_name: str = dspy.OutputField(desc="Name for this command mode (e.g., 'corner', 'center', 'diagonal')")
        dialogue_steps: str = dspy.OutputField(desc="JSON array of dialogue steps: [{prompt, input_type, options, default}]")
        syntax_template: str = dspy.OutputField(desc="Generalized syntax template with <placeholders>")
        gotchas: str = dspy.OutputField(desc="Semicolon-separated things that can go wrong")


    class ConsolidateCommandPattern(dspy.Signature):
        """Consolidate multiple observations into a canonical command pattern."""

        command_name: str = dspy.InputField(desc="The Rhino command name")
        observations_json: str = dspy.InputField(desc="JSON array of observation summaries")

        description: str = dspy.OutputField(desc="One sentence describing what this command does")
        modes: str = dspy.OutputField(desc="JSON object of modes: {mode_name: {syntax, dialogue, example, description}}")
        options: str = dspy.OutputField(desc="JSON object of available options and their meanings")
        preconditions: str = dspy.OutputField(desc="JSON object: {requires_selection, selection_type, clear_pending}")
        gotchas: str = dspy.OutputField(desc="JSON array of common mistakes and how to avoid them")
        related_commands: str = dspy.OutputField(desc="JSON array of related command names")


    class MapIntentToCommand(dspy.Signature):
        """Map a user intent to the best Rhino command and mode."""

        intent: str = dspy.InputField(desc="What the user wants to accomplish")
        available_commands: str = dspy.InputField(desc="JSON of known commands with descriptions")

        command: str = dspy.OutputField(desc="The Rhino command name to use")
        mode: str = dspy.OutputField(desc="Which mode of the command (e.g., 'corner', 'center')")
        syntax: str = dspy.OutputField(desc="The complete syntax to execute")
        reasoning: str = dspy.OutputField(desc="Why this command/mode fits the intent")


# =============================================================================
# DSPy Modules for Command Learning
# =============================================================================

if DSPY_AVAILABLE:

    class DialogueExtractor(dspy.Module):
        """Extracts structured dialogue patterns from raw observations."""

        def __init__(self):
            super().__init__()
            self.extract = dspy.ChainOfThought(ExtractDialoguePattern)

        def forward(self, observation: CommandObservation) -> dict:
            """Extract pattern from a single observation."""
            # Prepare raw history - combine before/after for context
            raw_history = ""
            if observation.raw_history_after:
                raw_history = observation.raw_history_after[-3000:]  # Last 3000 chars

            result = self.extract(
                command_name=observation.command,
                full_syntax=observation.full_syntax,
                raw_history=raw_history,
                success=observation.success,
                objects_created=observation.result.objects_created,
            )

            return {
                "mode_name": result.mode_name,
                "dialogue_steps": self._parse_json(result.dialogue_steps, []),
                "syntax_template": result.syntax_template,
                "gotchas": [g.strip() for g in result.gotchas.split(";") if g.strip()],
            }

        def _parse_json(self, text: str, default: Any) -> Any:
            try:
                return json.loads(text)
            except:
                return default


    class CommandConsolidator(dspy.Module):
        """Consolidates multiple observations into canonical command knowledge."""

        def __init__(self):
            super().__init__()
            self.consolidate = dspy.ChainOfThought(ConsolidateCommandPattern)

        def forward(self, command_name: str, observations: list[CommandObservation]) -> dict:
            """Consolidate observations into a command pattern."""
            # Pre-extract modes from observations for accurate mode tracking
            extracted_modes = {}  # mode_name -> list of examples

            # Summarize observations for the LLM, including pre-extracted mode
            obs_summaries = []
            for obs in observations:
                # Extract mode using our deterministic function
                mode = extract_mode_from_observation(obs)

                obs_summaries.append({
                    "syntax": obs.full_syntax,
                    "success": obs.success,
                    "objects_created": obs.result.objects_created,
                    "intent": obs.intent,
                    "dialogue_count": len(obs.dialogue),
                    "extracted_mode": mode,  # Include pre-extracted mode for DSPy
                })

                # Track modes from successful observations
                if obs.success:
                    if mode not in extracted_modes:
                        extracted_modes[mode] = []
                    extracted_modes[mode].append(obs.full_syntax)

            result = self.consolidate(
                command_name=command_name,
                observations_json=json.dumps(obs_summaries, indent=2),
            )

            # Parse DSPy result
            dspy_modes = self._parse_json(result.modes, {})

            # Merge: ensure all extracted modes are represented
            # DSPy provides rich descriptions, but we ensure mode names match observations
            final_modes = {}
            for mode_name, examples in extracted_modes.items():
                if mode_name in dspy_modes:
                    # Use DSPy's rich description
                    final_modes[mode_name] = dspy_modes[mode_name]
                else:
                    # Add mode that DSPy missed, with basic info
                    final_modes[mode_name] = {
                        "syntax": examples[0] if examples else "",
                        "example": examples[0] if examples else "",
                        "description": f"{command_name} {mode_name} mode",
                    }

            # Also include any DSPy modes not in our extracted set
            # (in case DSPy identified modes from failed observations or patterns)
            for mode_name, mode_data in dspy_modes.items():
                if mode_name not in final_modes:
                    final_modes[mode_name] = mode_data

            return {
                "command": command_name,
                "description": result.description,
                "modes": final_modes,
                "options": self._parse_json(result.options, {}),
                "preconditions": self._parse_json(result.preconditions, {}),
                "gotchas": self._parse_json(result.gotchas, []),
                "related_commands": self._parse_json(result.related_commands, []),
            }

        def _parse_json(self, text: str, default: Any) -> Any:
            try:
                return json.loads(text)
            except:
                return default


    class IntentMapper(dspy.Module):
        """Maps user intent to the best command."""

        def __init__(self):
            super().__init__()
            self.map_intent = dspy.ChainOfThought(MapIntentToCommand)

        def forward(self, intent: str, command_knowledge: dict) -> dict:
            """Map intent to command."""
            # Build command summary for the LLM
            cmd_summary = {}
            for cmd_name, cmd_data in command_knowledge.items():
                cmd_summary[cmd_name] = {
                    "description": cmd_data.get("description", ""),
                    "modes": list(cmd_data.get("modes", {}).keys()),
                }

            result = self.map_intent(
                intent=intent,
                available_commands=json.dumps(cmd_summary, indent=2),
            )

            return {
                "command": result.command,
                "mode": result.mode,
                "syntax": result.syntax,
                "reasoning": result.reasoning,
            }


# =============================================================================
# MABWiser Selector for Command Selection
# =============================================================================

if MABWISER_AVAILABLE:

    class CommandSelector:
        """MABWiser-based selector for choosing commands based on intent."""

        def __init__(self, storage_path: Optional[Path] = None):
            self.storage_path = storage_path or DEFAULT_OBSERVATION_STORE_PATH / "command_mab.pkl"
            self.mab: Optional[MAB] = None
            self.arms: list[str] = []  # command:mode pairs
            self.arm_metadata: dict[str, dict] = {}  # Additional info per arm
            self._load()

        def _load(self):
            """Load existing MAB state."""
            if self.storage_path.exists():
                try:
                    with open(self.storage_path, 'rb') as f:
                        data = pickle.load(f)
                        self.arms = data.get('arms', [])
                        self.arm_metadata = data.get('arm_metadata', {})
                        self.mab = data.get('mab')
                    logger.info(f"Loaded CommandSelector with {len(self.arms)} arms")
                except Exception as e:
                    logger.warning(f"Failed to load CommandSelector: {e}")

        def _save(self):
            """Save MAB state."""
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.storage_path, 'wb') as f:
                pickle.dump({
                    'arms': self.arms,
                    'arm_metadata': self.arm_metadata,
                    'mab': self.mab,
                }, f)

        def add_command(self, command: str, mode: str, metadata: dict = None):
            """Add a command:mode arm to the selector."""
            arm = f"{command}:{mode}"
            if arm not in self.arms:
                self.arms.append(arm)
                self.arm_metadata[arm] = metadata or {}
                self._rebuild_mab()
                self._save()

        def _rebuild_mab(self):
            """Rebuild MAB with current arms."""
            if not self.arms:
                return

            # Use LinUCB without clustering - simpler and more reliable
            self.mab = MAB(
                arms=self.arms,
                learning_policy=LearningPolicy.LinUCB(alpha=0.5),  # Lower alpha for less exploration
            )

            # Warm start - need to provide initial training data
            # Use varied contexts to initialize the linear model properly
            contexts = []
            for i, arm in enumerate(self.arms):
                ctx = self._featurize_intent("")
                # Add small variation to help LinUCB initialize
                if i < len(ctx):
                    ctx[i % len(ctx)] = 0.1
                contexts.append(ctx)

            self.mab.fit(
                decisions=self.arms,
                rewards=[0.5] * len(self.arms),
                contexts=contexts
            )

        def _featurize_intent(self, intent: str) -> np.ndarray:
            """Convert intent to feature vector."""
            intent_lower = intent.lower()
            features = []

            # Geometry type indicators
            geometry_types = [
                "box", "cube", "sphere", "ball", "cylinder", "tube", "cone",
                "torus", "donut", "line", "circle", "arc", "ellipse",
                "rectangle", "polygon", "curve", "surface", "solid"
            ]
            for gt in geometry_types:
                features.append(1.0 if gt in intent_lower else 0.0)

            # Action indicators
            actions = [
                "create", "make", "draw", "add", "build",
                "move", "copy", "rotate", "scale", "mirror",
                "delete", "remove", "trim", "split", "join",
                "extrude", "loft", "sweep", "revolve", "offset"
            ]
            for action in actions:
                features.append(1.0 if action in intent_lower else 0.0)

            # Position indicators
            positions = ["center", "corner", "origin", "diagonal", "point"]
            for pos in positions:
                features.append(1.0 if pos in intent_lower else 0.0)

            # Has dimensions mentioned
            features.append(1.0 if any(c.isdigit() for c in intent) else 0.0)

            return np.array(features)

        def select(self, intent: str) -> tuple[str, str, dict]:
            """Select the best command:mode for an intent.

            Returns:
                (command, mode, metadata)
            """
            if not self.mab or not self.arms:
                return None, None, {}

            context = self._featurize_intent(intent)
            prediction = self.mab.predict(contexts=[context])

            # MABWiser returns string directly for single context, list for multiple
            if isinstance(prediction, list):
                arm = prediction[0]
            else:
                arm = prediction

            # Parse arm format "command:mode"
            if ":" in arm:
                command, mode = arm.split(":", 1)
            else:
                command = arm
                mode = "default"

            return command, mode, self.arm_metadata.get(arm, {})

        def update(self, intent: str, command: str, mode: str, reward: float):
            """Update MAB with execution result."""
            if not self.mab:
                return

            arm = f"{command}:{mode}"
            if arm not in self.arms:
                self.add_command(command, mode)

            context = self._featurize_intent(intent)
            self.mab.partial_fit(
                decisions=[arm],
                rewards=[reward],
                contexts=[context]
            )
            self._save()

        def get_stats(self) -> dict:
            """Get selector statistics."""
            return {
                "total_arms": len(self.arms),
                "arms": self.arms,
                "storage_path": str(self.storage_path),
            }


# =============================================================================
# NOTE: CommandKnowledgeStore, CommandKnowledge, and ModeKnowledge are now
# imported from command_knowledge_store.py (the unified meta-learning module).
# CommandPattern is a type alias for CommandKnowledge for backward compatibility.
# See imports at top of file.
# =============================================================================

# Module-level knowledge store instance (used by server.py)
knowledge_store = CommandKnowledgeStore()


# =============================================================================
# Main Command Learner
# =============================================================================

class CommandLearner:
    """Systematic command learning with DSPy consolidation and MAB selection."""

    def __init__(
        self,
        observation_store: Optional[ObservationStore] = None,
        knowledge_store: Optional[CommandKnowledgeStore] = None,
        selector: Optional["CommandSelector"] = None,
    ):
        self.observation_store = observation_store or ObservationStore(DEFAULT_OBSERVATION_STORE_PATH)
        self.knowledge_store = knowledge_store or CommandKnowledgeStore()

        if MABWISER_AVAILABLE:
            self.selector = selector or CommandSelector()
        else:
            self.selector = None
            logger.warning("MABWiser not available - selector disabled")

        if DSPY_AVAILABLE:
            self.extractor = DialogueExtractor()
            self.consolidator = CommandConsolidator()
            self.intent_mapper = IntentMapper()
        else:
            self.extractor = None
            self.consolidator = None
            self.intent_mapper = None
            logger.warning("DSPy not available - intelligent extraction disabled")

    def learn_from_observation(self, observation: CommandObservation) -> dict:
        """Learn from a single observation using DSPy extraction."""
        if not self.extractor:
            return {"error": "DSPy not available"}

        try:
            # Extract pattern from observation
            extracted = self.extractor(observation)

            # Update selector with this command:mode
            if self.selector and observation.success:
                self.selector.add_command(
                    command=observation.command,
                    mode=extracted["mode_name"],
                    metadata={
                        "syntax_template": extracted["syntax_template"],
                        "example": observation.full_syntax,
                    }
                )
                # Update with positive reward for success
                if observation.intent:
                    self.selector.update(
                        intent=observation.intent,
                        command=observation.command,
                        mode=extracted["mode_name"],
                        reward=1.0 if observation.success else 0.0
                    )

            return {
                "success": True,
                "command": observation.command,
                "extracted": extracted,
            }
        except Exception as e:
            logger.error(f"Failed to learn from observation: {e}")
            return {"success": False, "error": str(e)}

    def consolidate_command(self, command: str) -> Optional[CommandPattern]:
        """Consolidate all observations for a command into a pattern."""
        if not self.consolidator:
            logger.warning("DSPy not available - using simple consolidation")
            return self._simple_consolidate(command)

        observations = self.observation_store.get_by_command(command)
        if not observations:
            return None

        try:
            # Use DSPy to consolidate
            consolidated = self.consolidator(command, observations)

            pattern = CommandPattern(
                command=command,
                description=consolidated.get("description", ""),
                modes=consolidated.get("modes", {}),
                options=consolidated.get("options", {}),
                preconditions=consolidated.get("preconditions", {}),
                gotchas=consolidated.get("gotchas", []),
                related_commands=consolidated.get("related_commands", []),
                observations_count=len(observations),
            )

            # Update stores
            self.knowledge_store.update(pattern)

            # Update selector with all modes
            if self.selector:
                for mode_name, mode_data in pattern.modes.items():
                    self.selector.add_command(
                        command=command,
                        mode=mode_name,
                        metadata={
                            "syntax": self._get_mode_attr(mode_data, "syntax", ""),
                            "example": self._get_mode_attr(mode_data, "example", ""),
                            "description": self._get_mode_attr(mode_data, "description", ""),
                        }
                    )

            return pattern

        except Exception as e:
            logger.error(f"Failed to consolidate {command}: {e}")
            return self._simple_consolidate(command)

    def _simple_consolidate(self, command: str) -> Optional[CommandPattern]:
        """Simple consolidation without DSPy."""
        observations = self.observation_store.get_by_command(command)
        if not observations:
            return None

        # Group by success
        successful = [o for o in observations if o.success]

        # Extract modes from successful observations
        modes = {}
        for obs in successful:
            # Extract mode from observation - look at full_syntax and dialogue
            mode_name = self._extract_mode_from_observation(obs)

            if mode_name not in modes:
                modes[mode_name] = {
                    "example": obs.full_syntax,
                    "observations": 1,
                    "success_rate": 1.0,
                }
            else:
                modes[mode_name]["observations"] += 1

        pattern = CommandPattern(
            command=command,
            description=f"Rhino {command} command",
            modes=modes,
            observations_count=len(observations),
        )

        self.knowledge_store.update(pattern)

        # Update MAB selector with discovered modes
        if self.selector:
            for mode_name, mode_data in modes.items():
                self.selector.add_command(
                    command=command,
                    mode=mode_name,
                    metadata={
                        "example": mode_data.get("example", ""),
                        "description": f"{command} {mode_name} mode",
                    }
                )
                # Train MAB with successful observation intent if available
                for obs in successful:
                    if obs.intent and self._mode_matches(obs.full_syntax, mode_name):
                        self.selector.update(
                            intent=obs.intent,
                            command=command,
                            mode=mode_name,
                            reward=1.0
                        )

        return pattern

    def _extract_mode_from_observation(self, obs) -> str:
        """Extract mode name from observation. Delegates to module-level function."""
        return extract_mode_from_observation(obs)

    def _extract_mode_from_syntax(self, syntax: str) -> str:
        """Extract mode from syntax string. Delegates to module-level function."""
        return extract_mode_from_syntax(syntax)

    def _mode_matches(self, syntax: str, mode_name: str) -> bool:
        """Check if a syntax string matches a mode name."""
        return extract_mode_from_syntax(syntax) == mode_name

    def _keyword_match_command(self, intent_lower: str) -> Optional[str]:
        """Match intent to command using keywords."""
        # Priority-ordered keyword mappings (more specific first)
        mappings = [
            # Solids
            (["sphere", "ball"], "-Sphere"),
            (["box", "cube"], "-Box"),
            (["cylinder", "tube"], "-Cylinder"),
            (["cone"], "-Cone"),
            (["torus", "donut", "ring"], "-Torus"),
            # Curves
            (["polyline", "pline"], "-Polyline"),
            (["rectangle", "rect"], "-Rectangle"),
            (["ellipse", "oval"], "-Ellipse"),
            (["circle"], "-Circle"),
            (["arc"], "-Arc"),
            (["line"], "-Line"),
        ]

        for keywords, command in mappings:
            if any(kw in intent_lower for kw in keywords):
                return command
        return None

    def _keyword_match_mode(self, intent_lower: str) -> Optional[str]:
        """Match intent to mode using keywords."""
        mode_keywords = {
            "center": ["center", "centered", "middle"],
            "diagonal": ["diagonal", "diag"],
            "3point": ["3 point", "three point", "3point"],
            "vertical": ["vertical", "vert", "up", "upward"],
            "diameter": ["diameter", "diam"],
        }

        for mode, keywords in mode_keywords.items():
            if any(kw in intent_lower for kw in keywords):
                return mode
        return None

    def _get_mode_attr(self, mode_data, attr: str, default=None):
        """Safely get attribute from mode data (ModeKnowledge or dict).

        Mode data can be either a ModeKnowledge dataclass or a plain dict,
        depending on how it was created (DSPy returns dicts, manual creation
        uses ModeKnowledge objects).
        """
        if mode_data is None:
            return default
        if isinstance(mode_data, dict):
            return mode_data.get(attr, default)
        # It's a ModeKnowledge dataclass - access attribute directly
        return getattr(mode_data, attr, default)

    def select_command(self, intent: str) -> dict:
        """Select the best command for an intent."""
        result = {
            "intent": intent,
            "command": None,
            "mode": None,
            "syntax": None,
            "source": None,
        }

        # First: Use keyword matching to identify the geometry type
        # This is reliable and fast
        intent_lower = intent.lower()
        keyword_command = self._keyword_match_command(intent_lower)
        keyword_mode = self._keyword_match_mode(intent_lower)

        if keyword_command:
            pattern = self.knowledge_store.get(keyword_command)
            if pattern:
                # Use keyword-matched command
                # Try keyword_mode first, then "default", then first available mode
                if keyword_mode and keyword_mode in pattern.modes:
                    mode = keyword_mode
                elif "default" in pattern.modes:
                    mode = "default"
                elif pattern.modes:
                    # Use first available mode (e.g., "center_radius", "CenterRadius")
                    mode = next(iter(pattern.modes.keys()))
                else:
                    mode = "default"

                mode_data = pattern.modes.get(mode, {})
                result["command"] = keyword_command
                result["mode"] = mode
                result["syntax"] = self._get_mode_attr(mode_data, "example")
                result["source"] = "keyword"

                # Train MAB with this selection for future improvement
                if self.selector:
                    self.selector.update(intent, keyword_command, mode, 0.8)

                return result

        # Try MAB selector as fallback
        if self.selector:
            command, mode, metadata = self.selector.select(intent)
            if command:
                result["command"] = command
                result["mode"] = mode
                result["syntax"] = metadata.get("syntax_template") or metadata.get("example")
                result["source"] = "mab"
                return result

        # Fall back to DSPy intent mapper
        if self.intent_mapper:
            try:
                knowledge = {
                    name: p.to_dict()
                    for name, p in self.knowledge_store.get_all().items()
                }
                if knowledge:
                    mapped = self.intent_mapper(intent, knowledge)
                    result["command"] = mapped.get("command")
                    result["mode"] = mapped.get("mode")
                    result["syntax"] = mapped.get("syntax")
                    result["reasoning"] = mapped.get("reasoning")
                    result["source"] = "dspy"
                    return result
            except Exception as e:
                logger.error(f"Intent mapping failed: {e}")

        # Fall back to keyword matching
        matches = self.knowledge_store.get_for_intent(intent)
        if matches:
            # get_for_intent returns a dict, get first item
            command, pattern = next(iter(matches.items()))
            modes = list(pattern.modes.keys())
            result["command"] = command
            result["mode"] = modes[0] if modes else "default"
            if modes and pattern.modes.get(modes[0]):
                mode_data = pattern.modes[modes[0]]
                result["syntax"] = self._get_mode_attr(mode_data, "example")
            result["source"] = "keyword"

        return result

    async def learn_command_interactive(
        self,
        command: str,
        inputs: list[str],
        intent: Optional[str] = None,
    ) -> dict:
        """Learn a command using interactive mode.

        This is the PREFERRED method for learning, as it captures real
        dialogue prompts from Rhino.

        Args:
            command: The command to learn (e.g., "_-Box")
            inputs: List of inputs to send (e.g., ["0,0,0", "10,10,0", "5"])
            intent: Optional description of what we're trying to do

        Returns:
            Dict with observation and learning results
        """
        # Create a temporary HTTP client if we don't have one
        from ..bridge import native_client

        async with native_client() as client:
            observer = CommandObserver(client, store=self.observation_store)
            observation = await observer.execute_interactive(
                command=command,
                inputs=inputs,
                intent=intent,
            )

        # Learn from the observation using DSPy if configured
        extracted_mode = None
        if observation.success and self.extractor and is_dspy_configured():
            try:
                extracted = self.extractor(observation)
                extracted_mode = extracted.get("mode_name", "default")

                # Update selector with this command:mode
                if self.selector:
                    self.selector.add_command(
                        command=observation.command,
                        mode=extracted_mode,
                        metadata={
                            "syntax_template": extracted.get("syntax_template", ""),
                            "example": observation.full_syntax,
                            "dialogue_steps": len(observation.dialogue),
                        }
                    )

                    if intent:
                        self.selector.update(
                            intent=intent,
                            command=observation.command,
                            mode=extracted_mode,
                            reward=1.0
                        )
            except Exception as e:
                logger.warning(f"DSPy extraction skipped: {e}")
        elif observation.success and not is_dspy_configured():
            # DSPy not configured - still update MAB selector with basic mode detection
            logger.debug("DSPy not configured - using basic mode detection")
            extracted_mode = self._detect_mode_from_syntax(observation.full_syntax)
            if self.selector:
                self.selector.add_command(
                    command=observation.command,
                    mode=extracted_mode,
                    metadata={
                        "example": observation.full_syntax,
                        "dialogue_steps": len(observation.dialogue),
                    }
                )
                if intent:
                    self.selector.update(
                        intent=intent,
                        command=observation.command,
                        mode=extracted_mode,
                        reward=1.0
                    )

        if observation.success:
            return {
                "success": True,
                "observation_id": observation.id,
                "command": observation.command,
                "objects_created": observation.result.objects_created,
                "dialogue_steps": len(observation.dialogue),
                "extracted_mode": extracted_mode,
                "dialogue": [step.to_dict() for step in observation.dialogue],
            }

        return {
            "success": observation.success,
            "observation_id": observation.id,
            "command": observation.command,
            "objects_created": observation.result.objects_created,
            "dialogue_steps": len(observation.dialogue),
            "error": observation.result.error_message,
            "dialogue": [step.to_dict() for step in observation.dialogue],
        }

    async def learn_command_variations_interactive(
        self,
        command: str,
        input_sequences: list[list[str]],
        intent: Optional[str] = None,
    ) -> list[dict]:
        """Learn multiple variations of a command using interactive mode.

        Args:
            command: The command to learn (e.g., "_-Box")
            input_sequences: List of input sequences to try
            intent: Optional description of what we're trying to do

        Returns:
            List of learning results for each variation
        """
        results = []
        for inputs in input_sequences:
            result = await self.learn_command_interactive(
                command=command,
                inputs=inputs,
                intent=intent,
            )
            results.append(result)

            # Log progress
            if result.get("success"):
                logger.info(
                    f"Learned {command} with {len(inputs)} inputs: "
                    f"{result.get('dialogue_steps')} dialogue steps, "
                    f"{result.get('objects_created')} objects"
                )
            else:
                logger.warning(f"Failed to learn {command}: {result.get('error')}")

        return results

    def get_learning_queue(self) -> list[dict]:
        """Get the prioritized list of commands to learn."""
        queue = []
        for priority, commands in sorted(COMMAND_LEARNING_QUEUE.items()):
            for cmd in commands:
                cmd_name = cmd["name"]
                # Check if we already have knowledge
                existing = self.knowledge_store.get(cmd_name)
                observations = self.observation_store.get_by_command(f"-{cmd_name}")

                # Get both new and legacy formats
                input_sequences = cmd.get("input_sequences", [])
                legacy_variations = get_legacy_variations(cmd)
                rhino_command = cmd.get("command", f"_-{cmd_name}")

                queue.append({
                    "priority": priority,
                    "command": cmd_name,
                    "rhino_command": rhino_command,
                    "input_sequences": input_sequences,
                    "legacy_variations": legacy_variations,
                    "requires_selection": cmd.get("requires_selection", False),
                    "existing_observations": len(observations),
                    "has_consolidated_knowledge": existing is not None,
                })

        return queue

    def get_stats(self) -> dict:
        """Get learning system statistics."""
        obs_stats = self.observation_store.get_stats()

        return {
            "observations": obs_stats,
            "consolidated_commands": len(self.knowledge_store.patterns),
            "selector_arms": self.selector.get_stats() if self.selector else None,
            "dspy_available": DSPY_AVAILABLE,
            "dspy_configured": is_dspy_configured(),
            "mabwiser_available": MABWISER_AVAILABLE,
        }


# =============================================================================
# Convenience Functions
# =============================================================================

def get_learning_queue() -> list[dict]:
    """Get the prioritized learning queue."""
    learner = CommandLearner()
    return learner.get_learning_queue()


def consolidate_learned_commands():
    """Consolidate all observed commands into knowledge patterns."""
    learner = CommandLearner()
    observation_store = learner.observation_store

    results = []
    for command in observation_store.get_all_commands():
        pattern = learner.consolidate_command(command)
        if pattern:
            results.append({
                "command": command,
                "modes": list(pattern.modes.keys()),
                "observations": pattern.observations_count,
            })

    return results
