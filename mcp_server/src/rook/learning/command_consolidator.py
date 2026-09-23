"""DSPy-based Command Knowledge Structural Consolidation.

This module transforms flat command knowledge into structured, hierarchical knowledge
with families, shared gotchas, similar command pairs, and mode patterns.

The Core Problem:
    83 commands with 147 modes and 307 gotchas exist as flat, disconnected facts.
    No relationships exist between similar commands (Sphere/Ellipsoid),
    no gotcha propagation across families, no mode pattern sharing.

The Solution:
    Use DSPy to discover and build structural relationships:
    - FAMILIES: Group commands by function (primitives, curves, surfaces, transforms)
    - SHARED GOTCHAS: Identify gotchas that apply across multiple commands
    - SIMILAR PAIRS: Link commands with shared modes/behaviors
    - MODE PATTERNS: Extract common modes (center, 3point, diameter) with syntax

Architecture:
    Flat Command Knowledge --> DSPy Consolidator --> Structured JSON
    (83 commands)              (Discovers structure,  (Families, pairs,
                                links, propagates)     patterns, gotchas)

API Key Requirement:
    This module requires ANTHROPIC_API_KEY. Load from .env:
        from dotenv import load_dotenv
        load_dotenv()  # Loads from project root .env
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import dspy

# Learning boundary: configure DSPy once, on first import of any module that runs an LM.
from .dspy_config import ensure_configured as _ensure_dspy_configured
_ensure_dspy_configured()
from dotenv import load_dotenv

logger = logging.getLogger(__name__)


# =============================================================================
# DSPy Signatures for Structural Consolidation
# =============================================================================


class IdentifyCommandFamilies(dspy.Signature):
    """Group Rhino commands into semantic families based on function and parameters.

    Analyze command names, descriptions, modes, and gotchas to identify natural groupings.
    Families should be meaningful for:
    - Gotcha propagation (similar commands share similar issues)
    - Mode inheritance (family members often share modes like 'center', '3point')
    - Intent routing (user intent maps to family, then to specific command)

    Expected families include: primitives, curves, surfaces, transforms, booleans,
    annotations, editing, analysis. But discover based on actual data.
    """

    commands_json: str = dspy.InputField(
        desc="JSON array of command objects with: command, description, modes (names), gotchas (count)"
    )

    families_json: str = dspy.OutputField(
        desc='JSON object: {"family_name": {"commands": ["cmd1", "cmd2"], "description": "what this family does", "shared_traits": ["trait1", "trait2"]}}'
    )


class FindSharedGotchas(dspy.Signature):
    """Identify gotchas that apply across multiple commands.

    Look for semantic patterns in gotcha text that indicate shared concerns:
    - "Curve must be closed" applies to multiple surface creation commands
    - "Points cannot be collinear" applies to all 3-point mode commands
    - "Direction must be 3D coordinates" applies to commands with direction input

    Return gotchas with the commands they apply to and confidence levels.
    """

    commands_with_gotchas_json: str = dspy.InputField(
        desc="JSON array of {command, gotchas: [gotcha_text, ...]}"
    )
    families_json: str = dspy.InputField(
        desc="Previously identified family structure"
    )

    shared_gotchas_json: str = dspy.OutputField(
        desc='JSON object: {"gotcha_id": {"text": "the gotcha", "applies_to": ["cmd1", "cmd2"], "family": "family_name or null if cross-family", "confidence": 0.0-1.0}}'
    )
    propagation_candidates_json: str = dspy.OutputField(
        desc='JSON array of {"gotcha": "text", "source_command": "cmd", "candidate_commands": ["cmd1"], "reason": "why it might apply"}'
    )


class IdentifySimilarCommands(dspy.Signature):
    """Find pairs of commands that are semantically similar.

    Similar commands:
    - Share multiple modes (both have center, diameter, 3point)
    - Have related gotchas (both fail on collinear points)
    - Perform analogous operations (Sphere vs Ellipsoid, Move vs Copy)
    - Are 2D/3D variants of each other (Circle vs Sphere, Rectangle vs Box)

    Similarity enables gotcha propagation and mode inheritance.
    """

    commands_with_modes_json: str = dspy.InputField(
        desc="JSON array of {command, modes: [mode_names], description}"
    )
    families_json: str = dspy.InputField(
        desc="Previously identified families"
    )

    similar_pairs_json: str = dspy.OutputField(
        desc='JSON array: [{"cmd1": "-Sphere", "cmd2": "-Ellipsoid", "similarity_score": 0.92, "shared_modes": ["center", "diameter"], "reason": "why similar"}]'
    )


class IdentifyModePatterns(dspy.Signature):
    """Find mode patterns that appear across multiple commands.

    Mode patterns enable:
    - Syntax prediction (if you know 'center' mode syntax for Box, predict it for Circle)
    - Gotcha inheritance (3point mode always has collinearity gotcha)
    - Learning acceleration (new command with 'center' mode inherits pattern)

    Common patterns: center, 3point, diameter, vertical, diagonal, tangent
    """

    commands_with_modes_json: str = dspy.InputField(
        desc="JSON array of {command, modes: {mode_name: {syntax, example}}}"
    )

    mode_patterns_json: str = dspy.OutputField(
        desc='JSON object: {"mode_name": {"commands": ["cmd1", "cmd2"], "typical_syntax": "_ModeOption <params>", "typical_gotcha": "common gotcha or null"}}'
    )


# =============================================================================
# DSPy Signatures for Command Tiering (Phase 3)
# =============================================================================


class GenerateQuickTier(dspy.Signature):
    """Generate a ~20 token QUICK tier summary for a command.

    The QUICK tier contains ONLY:
    - Command name
    - Primary syntax (most common usage)
    - One-line description
    - Most critical gotcha (if any)

    This tier is for when Claude already knows how to use the command
    and just needs a quick reminder.
    """

    command_name: str = dspy.InputField(desc="Name of the Rhino command (e.g., '-Box')")
    description: str = dspy.InputField(desc="Full description of the command")
    modes_json: str = dspy.InputField(desc="JSON of all modes with syntax")
    gotchas: list[str] = dspy.InputField(desc="List of gotcha strings")
    family_name: str = dspy.InputField(desc="The command family name")

    quick_summary: str = dspy.OutputField(
        desc="~20 token summary: '<syntax> | <critical_gotcha_if_any>'. Example: '_-Sphere center radius | Collinear points fail in 3Point'"
    )


class GenerateContextTier(dspy.Signature):
    """Generate a ~50 token CONTEXT tier for a specific usage context.

    The CONTEXT tier contains:
    - Specific syntax for this context/mode
    - Relevant options
    - Context-specific gotchas
    - Example if helpful

    Contexts are derived from mode names or common intents:
    - "center" -> Center mode usage
    - "3point" -> 3Point mode usage
    - "default" -> Default mode usage
    """

    command_name: str = dspy.InputField(desc="Name of the Rhino command")
    context_name: str = dspy.InputField(desc="The specific context/mode (e.g., 'center', '3point', 'default')")
    mode_details_json: str = dspy.InputField(desc="JSON of the specific mode: {syntax, dialogue, example, description}")
    relevant_options: list[str] = dspy.InputField(desc="Options relevant to this context")
    relevant_gotchas: list[str] = dspy.InputField(desc="Gotchas relevant to this context")
    family_shared_gotchas: list[str] = dspy.InputField(desc="Shared gotchas from the command's family")

    context_summary: str = dspy.OutputField(
        desc="~50 token summary with syntax, key options, and gotchas for this specific context. Include example if non-obvious."
    )


class GenerateErrorsTier(dspy.Signature):
    """Generate a ~30 token ERRORS tier for debugging command failures.

    The ERRORS tier contains:
    - What commonly fails
    - Why it fails
    - How to fix it

    This tier is for when Claude needs to understand why a command
    didn't work as expected.
    """

    command_name: str = dspy.InputField(desc="Name of the Rhino command")
    gotchas: list[str] = dspy.InputField(desc="All gotchas for this command")
    shared_gotchas: list[str] = dspy.InputField(desc="Shared gotchas from family/similar commands")
    preconditions_json: str = dspy.InputField(desc="JSON of preconditions {requires_selection, selection_type}")

    errors_summary: str = dspy.OutputField(
        desc="~30 token summary of what fails: 'FAILS: <reason1>, <reason2>. FIX: <how>'. Focus on most common failures."
    )


class GenerateAllTiers(dspy.Signature):
    """Generate all three tiers for a command in one pass.

    More efficient than three separate calls. Returns structured JSON.
    """

    command_name: str = dspy.InputField(desc="Name of the Rhino command (e.g., '-Box')")
    command_json: str = dspy.InputField(desc="Full command JSON with all fields")
    family_name: str = dspy.InputField(desc="The command family name")
    family_shared_gotchas: list[str] = dspy.InputField(desc="Shared gotchas from the family")
    similar_commands: list[str] = dspy.InputField(desc="List of similar command names")

    tiers_json: str = dspy.OutputField(
        desc='''JSON object with all tiers:
{
    "quick": "<~20 tokens: syntax | critical_gotcha>",
    "contexts": {
        "<mode_name>": "<~50 tokens: context-specific info>",
        ...
    },
    "errors": "<~30 tokens: what fails and why>"
}'''
    )


# =============================================================================
# DSPy Signatures for Incremental Learning (Phase 5)
# =============================================================================


class PlaceNewCommand(dspy.Signature):
    """Determine where a newly learned command fits in existing structure.

    When a new command is learned, determine:
    - Which family it belongs to
    - Which existing command it's most similar to
    - What gotchas it should inherit from family/similar commands
    - What new shared gotchas it contributes
    """

    new_command_json: str = dspy.InputField(
        desc="JSON of newly learned command with modes and gotchas"
    )
    existing_families_json: str = dspy.InputField(
        desc="Current family structure"
    )
    existing_similar_pairs_json: str = dspy.InputField(
        desc="Existing similarity links"
    )

    family: str = dspy.OutputField(desc="Family name this command belongs to")
    similar_to: str = dspy.OutputField(desc="Most similar existing command name")
    inherited_gotchas_json: str = dspy.OutputField(
        desc="JSON array of gotchas to inherit from family/similar"
    )
    new_shared_gotchas_json: str = dspy.OutputField(
        desc="JSON array of gotchas this command shares with others"
    )


class PropagateGotcha(dspy.Signature):
    """Check if a discovered gotcha applies to related commands.

    When a gotcha is discovered for one command, check if it should
    propagate to similar commands or family members.
    """

    gotcha_text: str = dspy.InputField(desc="The gotcha text discovered")
    source_command: str = dspy.InputField(desc="Command where gotcha was found")
    candidate_commands_json: str = dspy.InputField(
        desc="JSON array of {command, description, modes} for related commands"
    )

    applies_to_json: str = dspy.OutputField(
        desc='JSON object: {"command_name": confidence_0_to_1}'
    )
    reasoning: str = dspy.OutputField(
        desc="Why gotcha does/doesn't apply to each candidate"
    )


class RefineStructure(dspy.Signature):
    """Periodically re-analyze structure for improvements.

    After learning more commands, the initial structure may need refinement:
    - Wrong family assignments to correct
    - New similarities to add
    - Stale connections to remove
    - New shared gotchas from accumulated evidence
    """

    current_structure_json: str = dspy.InputField(
        desc="Current structure (families, pairs, gotchas, patterns)"
    )
    new_commands_json: str = dspy.InputField(
        desc="Commands added since last consolidation"
    )
    recent_failures_json: str = dspy.InputField(
        desc="Recent command failures that might reveal patterns"
    )

    structure_updates_json: str = dspy.OutputField(
        desc="JSON of corrections to family assignments"
    )
    new_connections_json: str = dspy.OutputField(
        desc="JSON of new similarities discovered"
    )
    deprecated_connections_json: str = dspy.OutputField(
        desc="JSON of connections to remove"
    )


# =============================================================================
# Data Classes for Structured Knowledge
# =============================================================================


@dataclass
class CommandFamily:
    """A family of related commands."""

    name: str
    description: str
    commands: list[str] = field(default_factory=list)
    shared_traits: list[str] = field(default_factory=list)
    shared_gotchas: list[str] = field(default_factory=list)


@dataclass
class SharedGotcha:
    """A gotcha that applies to multiple commands."""

    id: str
    text: str
    applies_to: list[str] = field(default_factory=list)
    family: Optional[str] = None
    confidence: float = 1.0


@dataclass
class SimilarPair:
    """Two commands that are semantically similar."""

    cmd1: str
    cmd2: str
    similarity_score: float
    shared_modes: list[str] = field(default_factory=list)
    shared_gotchas: list[str] = field(default_factory=list)
    reason: str = ""


@dataclass
class ModePattern:
    """A mode that appears across multiple commands."""

    name: str
    commands: list[str] = field(default_factory=list)
    typical_syntax: str = ""
    typical_gotcha: Optional[str] = None


@dataclass
class TieredCommandKnowledge:
    """Tiered knowledge for a single command.

    Token targets:
    - quick: ~20 tokens
    - contexts: ~50 tokens each
    - errors: ~30 tokens
    """

    command: str
    family: str
    quick: str  # ~20 tokens: primary syntax | critical gotcha
    contexts: dict[str, str] = field(default_factory=dict)  # mode_name -> ~50 token context summary
    errors: str = ""  # ~30 tokens: what fails and why

    # Metadata
    similar_commands: list[str] = field(default_factory=list)
    token_estimate: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "command": self.command,
            "family": self.family,
            "quick": self.quick,
            "contexts": self.contexts,
            "errors": self.errors,
            "similar_commands": self.similar_commands,
            "token_estimate": self.token_estimate,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TieredCommandKnowledge":
        return cls(
            command=data["command"],
            family=data["family"],
            quick=data["quick"],
            contexts=data.get("contexts", {}),
            errors=data.get("errors", ""),
            similar_commands=data.get("similar_commands", []),
            token_estimate=data.get("token_estimate", {}),
        )


@dataclass
class CondensedKnowledgeStore:
    """Complete tiered knowledge for all commands.

    This is the output of Phase 3 tiering - a dramatically reduced
    token footprint for command knowledge queries.
    """

    version: str = "1.0"
    created: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    command_count: int = 0
    total_token_estimate: int = 0
    original_token_estimate: int = 0
    reduction_percent: float = 0.0

    commands: dict[str, TieredCommandKnowledge] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "created": self.created,
            "command_count": self.command_count,
            "total_token_estimate": self.total_token_estimate,
            "original_token_estimate": self.original_token_estimate,
            "reduction_percent": self.reduction_percent,
            "commands": {
                name: cmd.to_dict() for name, cmd in self.commands.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CondensedKnowledgeStore":
        store = cls(
            version=data.get("version", "1.0"),
            created=data.get("created", datetime.utcnow().isoformat()),
            command_count=data.get("command_count", 0),
            total_token_estimate=data.get("total_token_estimate", 0),
            original_token_estimate=data.get("original_token_estimate", 0),
            reduction_percent=data.get("reduction_percent", 0.0),
        )
        for name, cmd_data in data.get("commands", {}).items():
            store.commands[name] = TieredCommandKnowledge.from_dict(cmd_data)
        return store


@dataclass
class CommandStructure:
    """Complete structural knowledge for commands."""

    version: str = "2.0"
    created: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    last_consolidation: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    consolidation_count: int = 0
    command_count: int = 0

    families: dict[str, CommandFamily] = field(default_factory=dict)
    shared_gotchas: dict[str, SharedGotcha] = field(default_factory=dict)
    similar_pairs: list[SimilarPair] = field(default_factory=list)
    mode_patterns: dict[str, ModePattern] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dictionary."""
        return {
            "version": self.version,
            "created": self.created,
            "last_consolidation": self.last_consolidation,
            "consolidation_count": self.consolidation_count,
            "command_count": self.command_count,
            "families": {
                name: {
                    "name": f.name,
                    "description": f.description,
                    "commands": f.commands,
                    "shared_traits": f.shared_traits,
                    "shared_gotchas": f.shared_gotchas,
                }
                for name, f in self.families.items()
            },
            "shared_gotchas": {
                id: {
                    "id": g.id,
                    "text": g.text,
                    "applies_to": g.applies_to,
                    "family": g.family,
                    "confidence": g.confidence,
                }
                for id, g in self.shared_gotchas.items()
            },
            "similar_pairs": [
                {
                    "cmd1": p.cmd1,
                    "cmd2": p.cmd2,
                    "similarity_score": p.similarity_score,
                    "shared_modes": p.shared_modes,
                    "shared_gotchas": p.shared_gotchas,
                    "reason": p.reason,
                }
                for p in self.similar_pairs
            ],
            "mode_patterns": {
                name: {
                    "name": m.name,
                    "commands": m.commands,
                    "typical_syntax": m.typical_syntax,
                    "typical_gotcha": m.typical_gotcha,
                }
                for name, m in self.mode_patterns.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CommandStructure":
        """Create from dictionary."""
        structure = cls(
            version=data.get("version", "2.0"),
            created=data.get("created", datetime.utcnow().isoformat()),
            last_consolidation=data.get("last_consolidation", datetime.utcnow().isoformat()),
            consolidation_count=data.get("consolidation_count", 0),
            command_count=data.get("command_count", 0),
        )

        for name, f_data in data.get("families", {}).items():
            structure.families[name] = CommandFamily(
                name=f_data["name"],
                description=f_data["description"],
                commands=f_data.get("commands", []),
                shared_traits=f_data.get("shared_traits", []),
                shared_gotchas=f_data.get("shared_gotchas", []),
            )

        for id, g_data in data.get("shared_gotchas", {}).items():
            structure.shared_gotchas[id] = SharedGotcha(
                id=g_data["id"],
                text=g_data["text"],
                applies_to=g_data.get("applies_to", []),
                family=g_data.get("family"),
                confidence=g_data.get("confidence", 1.0),
            )

        for p_data in data.get("similar_pairs", []):
            structure.similar_pairs.append(
                SimilarPair(
                    cmd1=p_data["cmd1"],
                    cmd2=p_data["cmd2"],
                    similarity_score=p_data.get("similarity_score", 0.0),
                    shared_modes=p_data.get("shared_modes", []),
                    shared_gotchas=p_data.get("shared_gotchas", []),
                    reason=p_data.get("reason", ""),
                )
            )

        for name, m_data in data.get("mode_patterns", {}).items():
            structure.mode_patterns[name] = ModePattern(
                name=m_data["name"],
                commands=m_data.get("commands", []),
                typical_syntax=m_data.get("typical_syntax", ""),
                typical_gotcha=m_data.get("typical_gotcha"),
            )

        return structure


# =============================================================================
# Command Consolidator Class
# =============================================================================


class CommandConsolidator:
    """Orchestrates structural consolidation of command knowledge.

    This is a batch-processing orchestrator (not a DSPy module) that analyzes
    the full command knowledge base to extract families, relationships, and
    shared gotchas across related commands.

    Relationship to other Consolidators:
        - PatternConsolidator: DSPy module for merging individual patterns.
          Used for real-time pattern deduplication during learning.
        - IntelligentConsolidator: DSPy module for tiered knowledge generation.
          Used for creating token-aware knowledge tiers.
        - CommandConsolidator: (THIS) Orchestrator class for structural analysis.
          Used for batch processing command families and relationships.

    Pipeline:
    1. Load current command knowledge
    2. Run IdentifyCommandFamilies
    3. Run FindSharedGotchas (uses family output)
    4. Run IdentifySimilarCommands (uses family output)
    5. Run IdentifyModePatterns
    6. Merge into unified structure
    7. Save to command_structure.json

    Usage:
        # Load .env for API key
        from dotenv import load_dotenv
        load_dotenv()

        # Configure DSPy
        from rook.learning.dspy_config import configure_dspy
        configure_dspy(model='claude-3-5-haiku-latest')

        # Run consolidation
        consolidator = CommandConsolidator('knowledge/commands/command_knowledge.json')
        structure = consolidator.consolidate()
    """

    # Batch size for processing commands (to avoid token limits)
    BATCH_SIZE = 15

    def __init__(
        self,
        knowledge_path: str | Path,
        structure_path: str | Path | None = None,
    ):
        """Initialize the consolidator.

        Args:
            knowledge_path: Path to command_knowledge.json
            structure_path: Path to save command_structure.json (default: same dir)
        """
        self.knowledge_path = Path(knowledge_path)
        self.structure_path = Path(structure_path) if structure_path else (
            self.knowledge_path.parent / "command_structure.json"
        )

        # DSPy predictors (initialized lazily)
        self._family_identifier: Optional[dspy.Predict] = None
        self._gotcha_finder: Optional[dspy.Predict] = None
        self._similarity_finder: Optional[dspy.Predict] = None
        self._mode_extractor: Optional[dspy.Predict] = None

        # Loaded data
        self._commands: Optional[dict] = None
        self._structure: Optional[CommandStructure] = None

    @property
    def family_identifier(self) -> dspy.Predict:
        if self._family_identifier is None:
            self._family_identifier = dspy.Predict(IdentifyCommandFamilies)
        return self._family_identifier

    @property
    def gotcha_finder(self) -> dspy.Predict:
        if self._gotcha_finder is None:
            self._gotcha_finder = dspy.Predict(FindSharedGotchas)
        return self._gotcha_finder

    @property
    def similarity_finder(self) -> dspy.Predict:
        if self._similarity_finder is None:
            self._similarity_finder = dspy.Predict(IdentifySimilarCommands)
        return self._similarity_finder

    @property
    def mode_extractor(self) -> dspy.Predict:
        if self._mode_extractor is None:
            self._mode_extractor = dspy.Predict(IdentifyModePatterns)
        return self._mode_extractor

    def load_commands(self) -> dict:
        """Load command knowledge from JSON file."""
        if self._commands is None:
            with open(self.knowledge_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._commands = data.get("commands", {})
            logger.info(f"Loaded {len(self._commands)} commands from {self.knowledge_path}")
        return self._commands

    def consolidate(self) -> CommandStructure:
        """Run the full consolidation pipeline.

        Returns:
            CommandStructure with families, shared gotchas, similar pairs, and mode patterns.
        """
        commands = self.load_commands()
        logger.info(f"Starting consolidation of {len(commands)} commands")

        # Step 1: Identify families
        logger.info("Step 1: Identifying command families...")
        families = self._identify_families(commands)
        logger.info(f"Identified {len(families)} families")

        # Step 2: Find shared gotchas
        logger.info("Step 2: Finding shared gotchas...")
        shared_gotchas, propagation_candidates = self._find_shared_gotchas(commands, families)
        logger.info(f"Found {len(shared_gotchas)} shared gotchas")

        # Step 3: Find similar commands
        logger.info("Step 3: Finding similar command pairs...")
        similar_pairs = self._find_similar_commands(commands, families)
        logger.info(f"Found {len(similar_pairs)} similar pairs")

        # Step 4: Extract mode patterns
        logger.info("Step 4: Extracting mode patterns...")
        mode_patterns = self._extract_mode_patterns(commands)
        logger.info(f"Extracted {len(mode_patterns)} mode patterns")

        # Step 5: Build structure
        self._structure = CommandStructure(
            command_count=len(commands),
            consolidation_count=1,
            families=families,
            shared_gotchas=shared_gotchas,
            similar_pairs=similar_pairs,
            mode_patterns=mode_patterns,
        )

        # Step 6: Save
        self._save_structure()
        logger.info(f"Structure saved to {self.structure_path}")

        return self._structure

    def _identify_families(self, commands: dict) -> dict[str, CommandFamily]:
        """Identify command families using DSPy."""
        # Prepare command summary for DSPy (reduced to fit token limits)
        command_summaries = []
        for name, cmd in commands.items():
            command_summaries.append({
                "command": name,
                "description": cmd.get("description", "")[:100],
                "modes": list(cmd.get("modes", {}).keys()),
                "gotcha_count": len(cmd.get("gotchas", [])),
            })

        # Call DSPy
        result = self.family_identifier(
            commands_json=json.dumps(command_summaries, indent=2)
        )

        # Parse result
        try:
            families_data = json.loads(result.families_json)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse families JSON: {e}")
            logger.error(f"Raw output: {result.families_json}")
            families_data = {}

        # Convert to CommandFamily objects
        families = {}
        for name, data in families_data.items():
            families[name] = CommandFamily(
                name=name,
                description=data.get("description", ""),
                commands=data.get("commands", []),
                shared_traits=data.get("shared_traits", []),
            )

        return families

    def _find_shared_gotchas(
        self, commands: dict, families: dict[str, CommandFamily]
    ) -> tuple[dict[str, SharedGotcha], list[dict]]:
        """Find gotchas shared across commands."""
        # Prepare gotcha data
        gotcha_data = []
        for name, cmd in commands.items():
            gotcha_data.append({
                "command": name,
                "gotchas": cmd.get("gotchas", []),
            })

        # Prepare families JSON
        families_json = {
            name: {
                "description": f.description,
                "commands": f.commands,
            }
            for name, f in families.items()
        }

        # Call DSPy
        result = self.gotcha_finder(
            commands_with_gotchas_json=json.dumps(gotcha_data, indent=2),
            families_json=json.dumps(families_json, indent=2),
        )

        # Parse results
        try:
            shared_data = json.loads(result.shared_gotchas_json)
        except json.JSONDecodeError:
            logger.error(f"Failed to parse shared gotchas: {result.shared_gotchas_json}")
            shared_data = {}

        try:
            propagation = json.loads(result.propagation_candidates_json)
        except json.JSONDecodeError:
            propagation = []

        # Convert to SharedGotcha objects
        shared_gotchas = {}
        for id, data in shared_data.items():
            shared_gotchas[id] = SharedGotcha(
                id=id,
                text=data.get("text", ""),
                applies_to=data.get("applies_to", []),
                family=data.get("family"),
                confidence=data.get("confidence", 1.0),
            )

        return shared_gotchas, propagation

    def _find_similar_commands(
        self, commands: dict, families: dict[str, CommandFamily]
    ) -> list[SimilarPair]:
        """Find similar command pairs."""
        # Prepare command data
        command_data = []
        for name, cmd in commands.items():
            command_data.append({
                "command": name,
                "modes": list(cmd.get("modes", {}).keys()),
                "description": cmd.get("description", "")[:100],
            })

        families_json = {
            name: {"commands": f.commands}
            for name, f in families.items()
        }

        # Call DSPy
        result = self.similarity_finder(
            commands_with_modes_json=json.dumps(command_data, indent=2),
            families_json=json.dumps(families_json, indent=2),
        )

        # Parse results
        try:
            pairs_data = json.loads(result.similar_pairs_json)
        except json.JSONDecodeError:
            logger.error(f"Failed to parse similar pairs: {result.similar_pairs_json}")
            pairs_data = []

        # Convert to SimilarPair objects
        similar_pairs = []
        for data in pairs_data:
            similar_pairs.append(
                SimilarPair(
                    cmd1=data.get("cmd1", ""),
                    cmd2=data.get("cmd2", ""),
                    similarity_score=data.get("similarity_score", 0.0),
                    shared_modes=data.get("shared_modes", []),
                    reason=data.get("reason", ""),
                )
            )

        return similar_pairs

    def _extract_mode_patterns(self, commands: dict) -> dict[str, ModePattern]:
        """Extract common mode patterns."""
        # Prepare mode data
        mode_data = []
        for name, cmd in commands.items():
            modes_info = {}
            for mode_name, mode_details in cmd.get("modes", {}).items():
                modes_info[mode_name] = {
                    "syntax": mode_details.get("syntax", ""),
                    "example": mode_details.get("example", ""),
                }
            mode_data.append({
                "command": name,
                "modes": modes_info,
            })

        # Call DSPy
        result = self.mode_extractor(
            commands_with_modes_json=json.dumps(mode_data, indent=2)
        )

        # Parse results
        try:
            patterns_data = json.loads(result.mode_patterns_json)
        except json.JSONDecodeError:
            logger.error(f"Failed to parse mode patterns: {result.mode_patterns_json}")
            patterns_data = {}

        # Convert to ModePattern objects
        mode_patterns = {}
        for name, data in patterns_data.items():
            mode_patterns[name] = ModePattern(
                name=name,
                commands=data.get("commands", []),
                typical_syntax=data.get("typical_syntax", ""),
                typical_gotcha=data.get("typical_gotcha"),
            )

        return mode_patterns

    def _save_structure(self) -> None:
        """Save structure to JSON file."""
        if self._structure is None:
            raise RuntimeError("No structure to save. Run consolidate() first.")

        self.structure_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.structure_path, "w", encoding="utf-8") as f:
            json.dump(self._structure.to_dict(), f, indent=2)

    def load_structure(self) -> Optional[CommandStructure]:
        """Load existing structure from file."""
        if self.structure_path.exists():
            with open(self.structure_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._structure = CommandStructure.from_dict(data)
            return self._structure
        return None


# =============================================================================
# Reconsolidation Manager (Phase 7)
# =============================================================================


@dataclass
class StructureVersion:
    """A versioned snapshot of the command structure."""

    version_id: str
    created: str
    command_count: int
    family_count: int
    reason: str  # Why this version was created
    structure_path: Path

    def to_dict(self) -> dict:
        return {
            "version_id": self.version_id,
            "created": self.created,
            "command_count": self.command_count,
            "family_count": self.family_count,
            "reason": self.reason,
            "structure_path": str(self.structure_path),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "StructureVersion":
        return cls(
            version_id=data["version_id"],
            created=data["created"],
            command_count=data["command_count"],
            family_count=data["family_count"],
            reason=data["reason"],
            structure_path=Path(data["structure_path"]),
        )


@dataclass
class ReconsolidationState:
    """Tracks state for reconsolidation triggers."""

    commands_since_last: int = 0
    last_consolidation: str = ""
    recent_failures: list[dict] = field(default_factory=list)
    new_commands: list[str] = field(default_factory=list)
    versions: list[StructureVersion] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "commands_since_last": self.commands_since_last,
            "last_consolidation": self.last_consolidation,
            "recent_failures": self.recent_failures,
            "new_commands": self.new_commands,
            "versions": [v.to_dict() for v in self.versions],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ReconsolidationState":
        return cls(
            commands_since_last=data.get("commands_since_last", 0),
            last_consolidation=data.get("last_consolidation", ""),
            recent_failures=data.get("recent_failures", []),
            new_commands=data.get("new_commands", []),
            versions=[
                StructureVersion.from_dict(v)
                for v in data.get("versions", [])
            ],
        )


class ReconsolidationManager:
    """Manages periodic re-consolidation of command structure.

    Features:
    - Tracks commands learned since last consolidation
    - Triggers reconsolidation when threshold is reached (default: 10 commands)
    - Uses RefineStructure signature for incremental updates
    - Maintains structure versions for rollback capability

    Usage:
        manager = ReconsolidationManager(
            structure_path='knowledge/commands/command_structure.json',
            knowledge_path='knowledge/commands/command_knowledge.json'
        )

        # Called when new command is learned
        manager.record_new_command("NewCommand", command_data)

        # Called on command failure
        manager.record_failure("Command", "failure reason", {context})

        # Check if reconsolidation needed and run if so
        if manager.should_reconsolidate():
            result = manager.reconsolidate()
    """

    # Default threshold for reconsolidation
    DEFAULT_THRESHOLD = 10

    # Maximum failure history to keep
    MAX_FAILURE_HISTORY = 50

    # Maximum versions to keep
    MAX_VERSIONS = 10

    def __init__(
        self,
        structure_path: str | Path,
        knowledge_path: str | Path,
        state_path: str | Path | None = None,
        threshold: int = DEFAULT_THRESHOLD,
    ):
        """Initialize the reconsolidation manager.

        Args:
            structure_path: Path to command_structure.json
            knowledge_path: Path to command_knowledge.json
            state_path: Path to save reconsolidation state (default: same dir)
            threshold: Number of new commands before triggering reconsolidation
        """
        self.structure_path = Path(structure_path)
        self.knowledge_path = Path(knowledge_path)
        self.state_path = Path(state_path) if state_path else (
            self.structure_path.parent / "reconsolidation_state.json"
        )
        self.versions_dir = self.structure_path.parent / "structure_versions"
        self.threshold = threshold

        # DSPy predictor for RefineStructure
        self._refiner: Optional[dspy.Predict] = None

        # State
        self._state: Optional[ReconsolidationState] = None
        self._load_state()

    @property
    def refiner(self) -> dspy.Predict:
        if self._refiner is None:
            self._refiner = dspy.Predict(RefineStructure)
        return self._refiner

    def _load_state(self) -> None:
        """Load reconsolidation state from file."""
        if self.state_path.exists():
            with open(self.state_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._state = ReconsolidationState.from_dict(data)
            logger.info(f"Loaded reconsolidation state: {self._state.commands_since_last} commands since last")
        else:
            self._state = ReconsolidationState(
                last_consolidation=datetime.utcnow().isoformat()
            )
            logger.info("Initialized new reconsolidation state")

    def _save_state(self) -> None:
        """Save reconsolidation state to file."""
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.state_path, "w", encoding="utf-8") as f:
            json.dump(self._state.to_dict(), f, indent=2)

    def record_new_command(self, command_name: str, command_data: dict) -> None:
        """Record that a new command was learned.

        Args:
            command_name: Name of the learned command
            command_data: Command data including modes, gotchas, etc.
        """
        if command_name not in self._state.new_commands:
            self._state.new_commands.append(command_name)
            self._state.commands_since_last += 1
            self._save_state()
            logger.info(f"Recorded new command: {command_name} ({self._state.commands_since_last} since last consolidation)")

    def record_failure(
        self,
        command: str,
        reason: str,
        context: Optional[dict] = None
    ) -> None:
        """Record a command failure for pattern detection.

        Args:
            command: The command that failed
            reason: Why it failed
            context: Additional context (intent, inputs, etc.)
        """
        failure = {
            "command": command,
            "reason": reason,
            "context": context or {},
            "timestamp": datetime.utcnow().isoformat(),
        }
        self._state.recent_failures.append(failure)

        # Trim to max history
        if len(self._state.recent_failures) > self.MAX_FAILURE_HISTORY:
            self._state.recent_failures = self._state.recent_failures[-self.MAX_FAILURE_HISTORY:]

        self._save_state()
        logger.debug(f"Recorded failure for {command}: {reason}")

    def should_reconsolidate(self) -> bool:
        """Check if reconsolidation should be triggered.

        Returns:
            True if threshold reached or significant failures detected
        """
        # Threshold-based trigger
        if self._state.commands_since_last >= self.threshold:
            logger.info(f"Reconsolidation triggered: {self._state.commands_since_last} >= {self.threshold} commands")
            return True

        # Failure pattern trigger (5+ failures on related commands)
        command_failures = {}
        for failure in self._state.recent_failures:
            cmd = failure["command"]
            command_failures[cmd] = command_failures.get(cmd, 0) + 1

        # If any command has 3+ failures, might need structure review
        for cmd, count in command_failures.items():
            if count >= 3:
                logger.info(f"Reconsolidation triggered: {cmd} has {count} failures")
                return True

        return False

    def _create_version(self, reason: str) -> StructureVersion:
        """Create a versioned backup of the current structure.

        Args:
            reason: Why this version is being created

        Returns:
            StructureVersion metadata
        """
        # Ensure versions directory exists
        self.versions_dir.mkdir(parents=True, exist_ok=True)

        # Generate version ID with microseconds for uniqueness
        now = datetime.utcnow()
        version_id = now.strftime("%Y%m%d_%H%M%S") + f"_{now.microsecond:06d}"
        version_path = self.versions_dir / f"structure_v{version_id}.json"

        # Handle collision (rare but possible)
        counter = 1
        while version_path.exists():
            version_id = now.strftime("%Y%m%d_%H%M%S") + f"_{now.microsecond:06d}_{counter}"
            version_path = self.versions_dir / f"structure_v{version_id}.json"
            counter += 1

        # Copy current structure
        if self.structure_path.exists():
            import shutil
            shutil.copy2(self.structure_path, version_path)

            # Load to get metadata
            with open(self.structure_path, "r", encoding="utf-8") as f:
                structure_data = json.load(f)
            command_count = structure_data.get("command_count", 0)
            family_count = len(structure_data.get("families", {}))
        else:
            command_count = 0
            family_count = 0

        version = StructureVersion(
            version_id=version_id,
            created=datetime.utcnow().isoformat(),
            command_count=command_count,
            family_count=family_count,
            reason=reason,
            structure_path=version_path,
        )

        self._state.versions.append(version)

        # Trim to max versions
        if len(self._state.versions) > self.MAX_VERSIONS:
            old_version = self._state.versions.pop(0)
            # Delete old version file
            if old_version.structure_path.exists():
                old_version.structure_path.unlink()

        self._save_state()
        logger.info(f"Created structure version {version_id}: {reason}")

        return version

    def rollback(self, version_id: str) -> bool:
        """Rollback to a previous structure version.

        Args:
            version_id: The version ID to rollback to

        Returns:
            True if rollback successful
        """
        # Find version
        target_version = None
        for v in self._state.versions:
            if v.version_id == version_id:
                target_version = v
                break

        if target_version is None:
            logger.error(f"Version {version_id} not found")
            return False

        if not target_version.structure_path.exists():
            logger.error(f"Version file missing: {target_version.structure_path}")
            return False

        # Create backup of current before rollback
        self._create_version(f"pre-rollback to {version_id}")

        # Copy version to current
        import shutil
        shutil.copy2(target_version.structure_path, self.structure_path)

        logger.info(f"Rolled back to version {version_id}")
        return True

    def get_versions(self) -> list[dict]:
        """Get list of available versions.

        Returns:
            List of version metadata dicts
        """
        return [v.to_dict() for v in self._state.versions]

    def reconsolidate(self) -> dict:
        """Run incremental reconsolidation using RefineStructure.

        Returns:
            Dict with updates applied, connections added/removed
        """
        logger.info("Starting reconsolidation...")

        # Create backup version first
        self._create_version(f"pre-reconsolidation ({self._state.commands_since_last} new commands)")

        # Load current structure
        if not self.structure_path.exists():
            logger.warning("No structure to reconsolidate - run full consolidation first")
            return {"error": "No structure found"}

        with open(self.structure_path, "r", encoding="utf-8") as f:
            structure_data = json.load(f)

        # Load command knowledge for new commands
        with open(self.knowledge_path, "r", encoding="utf-8") as f:
            knowledge_data = json.load(f)
        commands = knowledge_data.get("commands", {})

        # Prepare new commands data
        new_commands_data = {}
        for cmd_name in self._state.new_commands:
            if cmd_name in commands:
                new_commands_data[cmd_name] = commands[cmd_name]

        # Prepare failures data
        failures_data = self._state.recent_failures[-20:]  # Last 20 failures

        # Call RefineStructure
        try:
            result = self.refiner(
                current_structure_json=json.dumps(structure_data, indent=2),
                new_commands_json=json.dumps(new_commands_data, indent=2),
                recent_failures_json=json.dumps(failures_data, indent=2),
            )

            # Parse results
            try:
                structure_updates = json.loads(result.structure_updates_json)
            except json.JSONDecodeError:
                structure_updates = {}

            try:
                new_connections = json.loads(result.new_connections_json)
            except json.JSONDecodeError:
                new_connections = []

            try:
                deprecated_connections = json.loads(result.deprecated_connections_json)
            except json.JSONDecodeError:
                deprecated_connections = []

            # Apply updates
            updates_applied = self._apply_updates(
                structure_data,
                structure_updates,
                new_connections,
                deprecated_connections
            )

            # Save updated structure
            with open(self.structure_path, "w", encoding="utf-8") as f:
                json.dump(structure_data, f, indent=2)

            # Reset state
            self._state.commands_since_last = 0
            self._state.new_commands = []
            self._state.recent_failures = []
            self._state.last_consolidation = datetime.utcnow().isoformat()
            self._save_state()

            logger.info(f"Reconsolidation complete: {updates_applied}")
            return updates_applied

        except Exception as e:
            logger.error(f"Reconsolidation failed: {e}")
            return {"error": str(e)}

    def _apply_updates(
        self,
        structure: dict,
        updates: dict,
        new_connections: list,
        deprecated: list
    ) -> dict:
        """Apply structure updates from RefineStructure.

        Args:
            structure: The structure dict to update (modified in place)
            updates: Family assignment corrections
            new_connections: New similarity pairs to add
            deprecated: Connections to remove

        Returns:
            Summary of changes applied
        """
        changes = {
            "family_corrections": 0,
            "connections_added": 0,
            "connections_removed": 0,
        }

        # Apply family corrections
        for cmd, new_family in updates.items():
            families = structure.get("families", {})

            # Remove from old family
            for family_name, family_data in families.items():
                if cmd in family_data.get("commands", []):
                    family_data["commands"].remove(cmd)
                    logger.info(f"Moved {cmd} from {family_name} to {new_family}")

            # Add to new family
            if new_family in families:
                if cmd not in families[new_family].get("commands", []):
                    families[new_family].setdefault("commands", []).append(cmd)
                    changes["family_corrections"] += 1

        # Add new similarity pairs
        similar_pairs = structure.get("similar_pairs", [])
        for conn in new_connections:
            # Check if already exists
            exists = False
            for pair in similar_pairs:
                if (pair.get("cmd1") == conn.get("cmd1") and
                    pair.get("cmd2") == conn.get("cmd2")):
                    exists = True
                    break

            if not exists:
                similar_pairs.append(conn)
                changes["connections_added"] += 1
                logger.info(f"Added similarity: {conn.get('cmd1')} <-> {conn.get('cmd2')}")

        # Remove deprecated connections
        for dep in deprecated:
            cmd1 = dep.get("cmd1")
            cmd2 = dep.get("cmd2")

            for i, pair in enumerate(similar_pairs):
                if (pair.get("cmd1") == cmd1 and pair.get("cmd2") == cmd2) or \
                   (pair.get("cmd1") == cmd2 and pair.get("cmd2") == cmd1):
                    similar_pairs.pop(i)
                    changes["connections_removed"] += 1
                    logger.info(f"Removed similarity: {cmd1} <-> {cmd2}")
                    break

        structure["similar_pairs"] = similar_pairs
        structure["last_consolidation"] = datetime.utcnow().isoformat()
        structure["consolidation_count"] = structure.get("consolidation_count", 0) + 1

        return changes

    def get_stats(self) -> dict:
        """Get reconsolidation statistics.

        Returns:
            Dict with state info and version count
        """
        return {
            "commands_since_last": self._state.commands_since_last,
            "last_consolidation": self._state.last_consolidation,
            "new_commands": self._state.new_commands,
            "failure_count": len(self._state.recent_failures),
            "version_count": len(self._state.versions),
            "threshold": self.threshold,
            "will_trigger": self.should_reconsolidate(),
        }


# =============================================================================
# Command Tiering System (Phase 3)
# =============================================================================


class CommandTieringSystem:
    """Generates tiered (condensed) knowledge for all commands.

    Takes the output of structural consolidation (command_structure.json)
    and the full command knowledge (command_knowledge.json) and produces
    condensed tiers for each command.

    Token reduction targets:
    - QUICK tier: ~20 tokens per command
    - CONTEXT tier: ~50 tokens per mode
    - ERRORS tier: ~30 tokens per command

    For 83 commands with avg 1.8 modes:
    - Original: ~400 tokens per command = 33,200 tokens total
    - Tiered: 20 + (1.8 * 50) + 30 = 140 tokens per command = 11,620 tokens
    - But queries only retrieve ONE tier, so actual usage:
      - Quick query: 20 tokens (95% reduction)
      - Context query: 50 tokens (87.5% reduction)
      - Errors query: 30 tokens (92.5% reduction)

    Usage:
        tiering = CommandTieringSystem(
            knowledge_path='knowledge/commands/command_knowledge.json',
            structure_path='knowledge/commands/command_structure.json'
        )
        store = tiering.generate_all_tiers()
        # Saved to knowledge/commands/condensed_command_knowledge.json
    """

    def __init__(
        self,
        knowledge_path: str | Path,
        structure_path: str | Path,
        output_path: str | Path | None = None,
    ):
        self.knowledge_path = Path(knowledge_path)
        self.structure_path = Path(structure_path)
        self.output_path = Path(output_path) if output_path else (
            self.knowledge_path.parent / "condensed_command_knowledge.json"
        )

        # DSPy predictor
        self._tier_generator: Optional[dspy.Predict] = None

        # Loaded data
        self._commands: Optional[dict] = None
        self._structure: Optional[CommandStructure] = None
        self._condensed: Optional[CondensedKnowledgeStore] = None

    @property
    def tier_generator(self) -> dspy.Predict:
        if self._tier_generator is None:
            self._tier_generator = dspy.Predict(GenerateAllTiers)
        return self._tier_generator

    def load_data(self) -> tuple[dict, CommandStructure]:
        """Load command knowledge and structure."""
        # Load commands
        with open(self.knowledge_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self._commands = data.get("commands", {})

        # Load structure
        with open(self.structure_path, "r", encoding="utf-8") as f:
            structure_data = json.load(f)
        self._structure = CommandStructure.from_dict(structure_data)

        logger.info(f"Loaded {len(self._commands)} commands and structure with {len(self._structure.families)} families")
        return self._commands, self._structure

    def _get_family_for_command(self, command_name: str) -> str:
        """Get the family name for a command."""
        for family_name, family in self._structure.families.items():
            if command_name in family.commands:
                return family_name
        return "Unknown"

    def _get_similar_commands(self, command_name: str) -> list[str]:
        """Get similar commands for a command."""
        similar = []
        for pair in self._structure.similar_pairs:
            if pair.cmd1 == command_name:
                similar.append(pair.cmd2)
            elif pair.cmd2 == command_name:
                similar.append(pair.cmd1)
        return similar

    def _get_family_shared_gotchas(self, family_name: str) -> list[str]:
        """Get shared gotchas that apply to a family."""
        gotchas = []
        for gotcha in self._structure.shared_gotchas.values():
            if gotcha.family == family_name:
                gotchas.append(gotcha.text)
        return gotchas

    def _estimate_tokens(self, text: str) -> int:
        """Rough token estimation (4 chars per token on average)."""
        return len(text) // 4

    def generate_tiers_for_command(self, command_name: str, command_data: dict) -> TieredCommandKnowledge:
        """Generate tiered knowledge for a single command."""
        family_name = self._get_family_for_command(command_name)
        similar_commands = self._get_similar_commands(command_name)
        family_shared_gotchas = self._get_family_shared_gotchas(family_name)

        # Call DSPy to generate all tiers at once
        result = self.tier_generator(
            command_name=command_name,
            command_json=json.dumps(command_data, indent=2),
            family_name=family_name,
            family_shared_gotchas=family_shared_gotchas,
            similar_commands=similar_commands,
        )

        # Parse result
        try:
            tiers_data = json.loads(result.tiers_json)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse tiers JSON for {command_name}: {e}")
            logger.error(f"Raw output: {result.tiers_json}")
            # Fallback to basic tiers
            tiers_data = {
                "quick": f"_{command_name} <params>",
                "contexts": {"default": f"Use _{command_name} with appropriate parameters"},
                "errors": "Check parameters and preconditions",
            }

        # Build tiered knowledge
        tiered = TieredCommandKnowledge(
            command=command_name,
            family=family_name,
            quick=tiers_data.get("quick", ""),
            contexts=tiers_data.get("contexts", {}),
            errors=tiers_data.get("errors", ""),
            similar_commands=similar_commands,
        )

        # Estimate tokens
        tiered.token_estimate = {
            "quick": self._estimate_tokens(tiered.quick),
            "contexts": sum(self._estimate_tokens(c) for c in tiered.contexts.values()),
            "errors": self._estimate_tokens(tiered.errors),
        }

        return tiered

    def generate_all_tiers(self) -> CondensedKnowledgeStore:
        """Generate tiered knowledge for all commands.

        Returns:
            CondensedKnowledgeStore with tiered knowledge for all commands.
        """
        commands, structure = self.load_data()

        # Estimate original token count (rough: 400 tokens per full command)
        original_estimate = len(commands) * 400

        self._condensed = CondensedKnowledgeStore(
            command_count=len(commands),
            original_token_estimate=original_estimate,
        )

        total_tokens = 0
        processed = 0

        for name, cmd_data in commands.items():
            logger.info(f"Generating tiers for {name} ({processed + 1}/{len(commands)})")

            try:
                tiered = self.generate_tiers_for_command(name, cmd_data)
                self._condensed.commands[name] = tiered

                # Sum token estimates
                cmd_tokens = sum(tiered.token_estimate.values())
                total_tokens += cmd_tokens

            except Exception as e:
                logger.error(f"Failed to generate tiers for {name}: {e}")
                # Create minimal entry
                self._condensed.commands[name] = TieredCommandKnowledge(
                    command=name,
                    family=self._get_family_for_command(name),
                    quick=f"_{name} - see full docs",
                    errors="Generation failed - use full knowledge",
                )

            processed += 1

        # Calculate reduction
        self._condensed.total_token_estimate = total_tokens
        if original_estimate > 0:
            reduction = (1 - total_tokens / original_estimate) * 100
            self._condensed.reduction_percent = round(reduction, 1)

        # Save
        self._save_condensed()
        logger.info(f"Tiered knowledge saved to {self.output_path}")
        logger.info(f"Token reduction: {self._condensed.reduction_percent}%")

        return self._condensed

    def _save_condensed(self) -> None:
        """Save condensed knowledge to JSON file."""
        if self._condensed is None:
            raise RuntimeError("No condensed knowledge to save. Run generate_all_tiers() first.")

        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.output_path, "w", encoding="utf-8") as f:
            json.dump(self._condensed.to_dict(), f, indent=2)

    def load_condensed(self) -> Optional[CondensedKnowledgeStore]:
        """Load existing condensed knowledge from file."""
        if self.output_path.exists():
            with open(self.output_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._condensed = CondensedKnowledgeStore.from_dict(data)
            return self._condensed
        return None


# =============================================================================
# Convenience Functions
# =============================================================================


def tier_commands(
    knowledge_path: str = "knowledge/commands/command_knowledge.json",
    structure_path: str = "knowledge/commands/command_structure.json",
    output_path: str = "knowledge/commands/condensed_command_knowledge.json",
    model: str | None = None,
) -> CondensedKnowledgeStore:
    """Convenience function to run command tiering.

    Args:
        knowledge_path: Path to command_knowledge.json
        structure_path: Path to command_structure.json
        output_path: Path to save condensed_command_knowledge.json
        model: Anthropic model to use (reads DSPY_MODEL env var if not provided)

    Returns:
        CondensedKnowledgeStore with tiered knowledge for all commands.
    """
    # Load environment
    load_dotenv()

    # Configure DSPy
    from rook.learning.dspy_config import configure_dspy
    configure_dspy(model=model, temperature=0.3)

    # Run tiering
    tiering = CommandTieringSystem(knowledge_path, structure_path, output_path)
    return tiering.generate_all_tiers()


def consolidate_commands(
    knowledge_path: str = "knowledge/commands/command_knowledge.json",
    output_path: str = "knowledge/commands/command_structure.json",
    model: str | None = None,
) -> CommandStructure:
    """Convenience function to run full consolidation.

    Args:
        knowledge_path: Path to command_knowledge.json
        output_path: Path to save command_structure.json
        model: Anthropic model to use (reads DSPY_MODEL env var if not provided)

    Returns:
        CommandStructure with all discovered relationships
    """
    # Load environment
    load_dotenv()

    # Configure DSPy
    from rook.learning.dspy_config import configure_dspy
    configure_dspy(model=model, temperature=0.3)

    # Run consolidation
    consolidator = CommandConsolidator(knowledge_path, output_path)
    return consolidator.consolidate()


if __name__ == "__main__":
    # Run consolidation when executed directly
    import sys

    logging.basicConfig(level=logging.INFO)

    knowledge_path = sys.argv[1] if len(sys.argv) > 1 else "knowledge/commands/command_knowledge.json"
    structure = consolidate_commands(knowledge_path)

    print(f"\nConsolidation complete!")
    print(f"  Families: {len(structure.families)}")
    print(f"  Shared Gotchas: {len(structure.shared_gotchas)}")
    print(f"  Similar Pairs: {len(structure.similar_pairs)}")
    print(f"  Mode Patterns: {len(structure.mode_patterns)}")
