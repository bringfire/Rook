"""Command Knowledge Store for Rook.

Provides a clean interface to read/write command_knowledge.json,
which stores learned Rhino command syntax, modes, and gotchas.

This is used by:
- Learning mode: Write new knowledge as commands are learned
- Execution mode: Read knowledge to execute commands correctly
"""

import json
import logging
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ..runtime_paths import resolve_readable_knowledge_path, resolve_writable_knowledge_path

logger = logging.getLogger(__name__)


def _default_command_knowledge_path() -> Path:
    return resolve_writable_knowledge_path("commands", "command_knowledge.json")


def _default_command_knowledge_read_path() -> Path:
    return resolve_readable_knowledge_path("commands", "command_knowledge.json")


def _default_command_structure_path() -> Path:
    return resolve_readable_knowledge_path("commands", "command_structure.json")


def _default_condensed_command_path() -> Path:
    return resolve_readable_knowledge_path("commands", "condensed_command_knowledge.json")


@dataclass
class ModeKnowledge:
    """Knowledge about a specific mode of a command.

    Example:
        ModeKnowledge(
            name="diameter",
            syntax="_-Sphere _Diameter <point1> <point2>",
            dialogue="Specify first diameter endpoint, then second endpoint",
            example="_-Sphere _Diameter 0,0,0 10,0,0",
            description="Creates sphere using two points as diameter endpoints"
        )
    """
    name: str
    syntax: str
    dialogue: str = ""
    example: str = ""
    description: str = ""

    @classmethod
    def from_dict(cls, name: str, data: dict) -> "ModeKnowledge":
        """Create from dictionary (JSON format)."""
        return cls(
            name=name,
            syntax=data.get("syntax", ""),
            dialogue=data.get("dialogue", ""),
            example=data.get("example", ""),
            description=data.get("description", ""),
        )

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON storage."""
        return {
            "syntax": self.syntax,
            "dialogue": self.dialogue,
            "example": self.example,
            "description": self.description,
        }


@dataclass
class CommandKnowledge:
    """Complete knowledge about a Rhino command.

    Example:
        CommandKnowledge(
            command="-Sphere",
            description="Creates a sphere...",
            modes={"default": ModeKnowledge(...), "diameter": ModeKnowledge(...)},
            options={"_Diameter": "Create sphere using diameter endpoints"},
            gotchas=["Three collinear points cannot define a sphere"],
            ...
        )

    Note: The __post_init__ method normalizes modes to always be ModeKnowledge
    objects, ensuring consistent data types throughout the meta-learning loop.
    """
    command: str
    description: str = ""
    modes: dict[str, ModeKnowledge] = field(default_factory=dict)
    options: dict[str, str] = field(default_factory=dict)
    preconditions: dict = field(default_factory=dict)
    gotchas: list[str] = field(default_factory=list)
    related_commands: list[str] = field(default_factory=list)
    observations_count: int = 0
    last_updated: str = ""

    def __post_init__(self):
        """Normalize modes to ensure they are always ModeKnowledge objects.

        This is critical for the meta-learning loop - the hybrid investigator
        uses knowledge graph data to decide what to investigate, then updates
        the graph with what it learns. Consistent data types enable this
        dynamic loop without scattered type checks.
        """
        normalized_modes = {}
        for mode_name, mode_data in self.modes.items():
            if isinstance(mode_data, ModeKnowledge):
                normalized_modes[mode_name] = mode_data
            elif isinstance(mode_data, dict):
                normalized_modes[mode_name] = ModeKnowledge.from_dict(mode_name, mode_data)
            else:
                # Fallback for unexpected types
                normalized_modes[mode_name] = ModeKnowledge(
                    name=mode_name,
                    syntax=str(mode_data),
                )
        self.modes = normalized_modes

    @classmethod
    def from_dict(cls, command: str, data: dict) -> "CommandKnowledge":
        """Create from dictionary (JSON format)."""
        modes = {}
        for mode_name, mode_data in data.get("modes", {}).items():
            modes[mode_name] = ModeKnowledge.from_dict(mode_name, mode_data)

        return cls(
            command=command,
            description=data.get("description", ""),
            modes=modes,
            options=data.get("options", {}),
            preconditions=data.get("preconditions", {}),
            gotchas=data.get("gotchas", []),
            related_commands=data.get("related_commands", []),
            observations_count=data.get("observations_count", 0),
            last_updated=data.get("last_updated", ""),
        )

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON storage."""
        # Modes are guaranteed to be ModeKnowledge by __post_init__
        modes_dict = {name: mode.to_dict() for name, mode in self.modes.items()}

        return {
            "command": self.command,
            "description": self.description,
            "modes": modes_dict,
            "options": self.options,
            "preconditions": self.preconditions,
            "gotchas": self.gotchas,
            "related_commands": self.related_commands,
            "observations_count": self.observations_count,
            "last_updated": self.last_updated,
        }


@dataclass
class CommandCandidate:
    """A command that might match a user intent."""
    command: str
    mode: str
    confidence: float
    reason: str


class CommandKnowledgeStore:
    """Interface to command_knowledge.json with caching and consolidation.

    Usage:
        store = CommandKnowledgeStore()

        # Read operations
        box = store.get_command("-Box")
        modes = store.get_modes("-Box")
        syntax = store.get_syntax("-Box", "center")
        candidates = store.search_by_intent("create a sphere")

        # Write operations
        store.add_mode("-Box", "3point", {...})
        store.add_gotcha("-Box", "New gotcha here")
        store.save()
    """

    def __init__(
        self,
        path: Optional[Path] = None,
        structure_path: Optional[Path] = None,
        condensed_path: Optional[Path] = None,
    ):
        """Initialize the store.

        Args:
            path: Optional path to command_knowledge.json.
                  Defaults to knowledge/commands/command_knowledge.json
        """
        self._uses_default_path = path is None
        self.path = Path(path) if path is not None else _default_command_knowledge_path()
        self._uses_default_structure_path = structure_path is None
        self._uses_default_condensed_path = condensed_path is None
        self.structure_path = Path(structure_path) if structure_path is not None else _default_command_structure_path()
        self.condensed_path = Path(condensed_path) if condensed_path is not None else _default_condensed_command_path()
        self._cache: Optional[dict] = None
        self._dirty: bool = False

        # Structure-aware caches (Phase 4 enhancement)
        self._structure_cache: Optional[dict] = None
        self._condensed_cache: Optional[dict] = None

        # Reverse lookup: command -> family
        self._command_to_family: dict[str, str] = {}

        self._load()
        self._load_structure()
        self._load_condensed()

    # =========================================================================
    # READ OPERATIONS
    # =========================================================================

    def get_command(self, command: str) -> Optional[CommandKnowledge]:
        """Get knowledge for a specific command.

        Args:
            command: Command name (e.g., "-Box", "-Sphere")

        Returns:
            CommandKnowledge object or None if not found
        """
        if self._cache is None:
            return None

        # Normalize command name (handle with/without dash)
        normalized = self._normalize_command(command)

        commands = self._cache.get("commands", {})
        if normalized in commands:
            return CommandKnowledge.from_dict(normalized, commands[normalized])

        return None

    def get_modes(self, command: str) -> list[str]:
        """Get known modes for a command.

        Args:
            command: Command name

        Returns:
            List of mode names (e.g., ["default", "center", "diagonal"])
        """
        cmd = self.get_command(command)
        if cmd is None:
            return []
        return list(cmd.modes.keys())

    def get_syntax(self, command: str, mode: str = "default") -> Optional[str]:
        """Get syntax template for command+mode.

        Args:
            command: Command name
            mode: Mode name (defaults to "default")

        Returns:
            Syntax template string or None
        """
        cmd = self.get_command(command)
        if cmd is None:
            return None

        mode_data = cmd.modes.get(mode)
        if mode_data is None:
            return None

        # Handle both ModeKnowledge objects and plain dicts
        if isinstance(mode_data, dict):
            return mode_data.get("syntax")
        return mode_data.syntax

    def get_gotchas(self, command: str) -> list[str]:
        """Get known gotchas for a command.

        Args:
            command: Command name

        Returns:
            List of gotcha strings
        """
        cmd = self.get_command(command)
        if cmd is None:
            return []
        return cmd.gotchas

    def get_options(self, command: str) -> dict[str, str]:
        """Get known options for a command.

        Args:
            command: Command name

        Returns:
            Dict of option -> description
        """
        cmd = self.get_command(command)
        if cmd is None:
            return {}
        return cmd.options

    def get_related_commands(self, command: str) -> list[str]:
        """Get commands related to this one.

        Args:
            command: Command name

        Returns:
            List of related command names
        """
        cmd = self.get_command(command)
        if cmd is None:
            return []
        return cmd.related_commands

    def search_by_intent(self, intent: str, limit: int = 5) -> list[CommandCandidate]:
        """Find commands that might match an intent.

        Uses keyword matching against command descriptions and mode names.

        Args:
            intent: Natural language intent (e.g., "create a sphere at origin")
            limit: Maximum number of candidates to return

        Returns:
            List of CommandCandidate objects, ordered by confidence
        """
        if self._cache is None:
            return []

        candidates = []
        intent_lower = intent.lower()
        intent_words = set(intent_lower.split())

        commands = self._cache.get("commands", {})

        for cmd_name, cmd_data in commands.items():
            # Check command name
            cmd_clean = cmd_name.lstrip("-").lower()
            if cmd_clean in intent_lower:
                # Direct command name match
                candidates.append(CommandCandidate(
                    command=cmd_name,
                    mode="default",
                    confidence=0.9,
                    reason=f"Command name '{cmd_clean}' found in intent"
                ))
                continue

            # Check description
            description = cmd_data.get("description", "").lower()
            desc_words = set(description.split())
            overlap = intent_words & desc_words

            if overlap:
                # Find best mode based on overlap
                best_mode = "default"
                best_score = len(overlap) / max(len(intent_words), 1)

                for mode_name, mode_data in cmd_data.get("modes", {}).items():
                    mode_desc = mode_data.get("description", "").lower()
                    mode_words = set(mode_desc.split())
                    mode_overlap = intent_words & mode_words
                    mode_score = len(mode_overlap) / max(len(intent_words), 1)

                    if mode_score > best_score:
                        best_score = mode_score
                        best_mode = mode_name

                if best_score > 0.1:  # Minimum threshold
                    candidates.append(CommandCandidate(
                        command=cmd_name,
                        mode=best_mode,
                        confidence=min(best_score, 0.85),
                        reason=f"Description match: {', '.join(overlap)}"
                    ))

        # Sort by confidence and limit
        candidates.sort(key=lambda c: c.confidence, reverse=True)
        return candidates[:limit]

    def get_for_intent(self, intent: str, limit: int = 5) -> dict[str, "CommandKnowledge"]:
        """Get command knowledge matching an intent.

        Similar to search_by_intent but returns full CommandKnowledge objects
        instead of CommandCandidate objects.

        Args:
            intent: Natural language intent
            limit: Maximum number of commands to return

        Returns:
            Dict mapping command names to CommandKnowledge objects
        """
        candidates = self.search_by_intent(intent, limit=limit)
        result = {}
        seen_commands = set()

        for candidate in candidates:
            if candidate.command not in seen_commands:
                cmd = self.get_command(candidate.command)
                if cmd:
                    result[candidate.command] = cmd
                    seen_commands.add(candidate.command)

        return result

    def get_all_commands(self) -> list[str]:
        """Get list of all known command names.

        Returns:
            List of command names
        """
        if self._cache is None:
            return []
        return list(self._cache.get("commands", {}).keys())

    def get_command_count(self) -> int:
        """Get total number of known commands.

        Returns:
            Number of commands in knowledge base
        """
        if self._cache is None:
            return 0
        return len(self._cache.get("commands", {}))

    def get(self, command: str) -> Optional[CommandKnowledge]:
        """Alias for get_command() for backward compatibility.

        Args:
            command: Command name (e.g., "-Box", "Box", "_-Box")

        Returns:
            CommandKnowledge object or None if not found
        """
        return self.get_command(command)

    def get_all(self) -> dict[str, CommandKnowledge]:
        """Get all command knowledge as a dictionary.

        Returns:
            Dict mapping command names to CommandKnowledge objects
        """
        if self._cache is None:
            return {}
        result = {}
        for cmd_name, cmd_data in self._cache.get("commands", {}).items():
            result[cmd_name] = CommandKnowledge.from_dict(cmd_name, cmd_data)
        return result

    @property
    def patterns(self) -> dict[str, CommandKnowledge]:
        """Alias for get_all() for backward compatibility.

        Returns:
            Dict mapping command names to CommandKnowledge objects
        """
        return self.get_all()

    # =========================================================================
    # STRUCTURE-AWARE READ OPERATIONS (Phase 4.1)
    # =========================================================================

    def get_family(self, command: str) -> Optional[str]:
        """Get the family a command belongs to.

        Args:
            command: Command name (e.g., "-Box", "Sphere")

        Returns:
            Family name (e.g., "Primitives", "Curves") or None if not in a family
        """
        normalized = self._normalize_command(command)
        return self._command_to_family.get(normalized)

    def get_family_info(self, command: str) -> Optional[dict]:
        """Get full family information for a command.

        Args:
            command: Command name

        Returns:
            Dict with family name, description, commands, shared_traits, shared_gotchas
            or None if command not in a family
        """
        family_name = self.get_family(command)
        if family_name is None or self._structure_cache is None:
            return None

        families = self._structure_cache.get("families", {})
        return families.get(family_name)

    def get_family_info_by_name(self, family_name: str) -> Optional[dict]:
        """Get full family information by family name.

        Args:
            family_name: Family name (e.g., "Primitives", "Curves")

        Returns:
            Dict with name, description, commands, shared_traits, shared_gotchas
            or None if family not found
        """
        if self._structure_cache is None:
            return None

        families = self._structure_cache.get("families", {})
        return families.get(family_name)

    def get_similar_commands(self, command: str) -> list[dict]:
        """Get commands similar to this one.

        Args:
            command: Command name

        Returns:
            List of similar command info dicts with:
            - command: The similar command name
            - similarity_score: How similar (0-1)
            - shared_modes: Modes both commands share
            - shared_gotchas: Gotchas that apply to both
            - reason: Why they're similar
        """
        if self._structure_cache is None:
            return []

        normalized = self._normalize_command(command)
        similar_pairs = self._structure_cache.get("similar_pairs", [])
        results = []

        for pair in similar_pairs:
            cmd1 = self._normalize_command(pair.get("cmd1", ""))
            cmd2 = self._normalize_command(pair.get("cmd2", ""))

            if cmd1 == normalized:
                results.append({
                    "command": cmd2,
                    "similarity_score": pair.get("similarity_score", 0),
                    "shared_modes": pair.get("shared_modes", []),
                    "shared_gotchas": pair.get("shared_gotchas", []),
                    "reason": pair.get("reason", ""),
                })
            elif cmd2 == normalized:
                results.append({
                    "command": cmd1,
                    "similarity_score": pair.get("similarity_score", 0),
                    "shared_modes": pair.get("shared_modes", []),
                    "shared_gotchas": pair.get("shared_gotchas", []),
                    "reason": pair.get("reason", ""),
                })

        # Sort by similarity score descending
        results.sort(key=lambda x: x["similarity_score"], reverse=True)
        return results

    def get_shared_gotchas(self, command: str) -> list[dict]:
        """Get shared gotchas that apply to this command.

        These are gotchas discovered to apply across multiple commands
        (e.g., "collinearity_gotcha" applies to Sphere, Cylinder, Cone, etc.)

        Args:
            command: Command name

        Returns:
            List of shared gotcha dicts with:
            - id: Gotcha identifier
            - text: The gotcha text
            - applies_to: List of commands this applies to
            - confidence: How confident we are this applies
        """
        if self._structure_cache is None:
            return []

        normalized = self._normalize_command(command)
        shared_gotchas = self._structure_cache.get("shared_gotchas", {})
        results = []

        for gotcha_id, gotcha_data in shared_gotchas.items():
            applies_to = gotcha_data.get("applies_to", [])
            # Check if this command is in the applies_to list
            for cmd in applies_to:
                if self._normalize_command(cmd) == normalized:
                    results.append({
                        "id": gotcha_id,
                        "text": gotcha_data.get("text", ""),
                        "applies_to": applies_to,
                        "confidence": gotcha_data.get("confidence", 0),
                        "family": gotcha_data.get("family"),
                    })
                    break

        # Sort by confidence descending
        results.sort(key=lambda x: x["confidence"], reverse=True)
        return results

    def get_commands_in_family(self, family_name: str) -> list[str]:
        """Get all commands in a family.

        Args:
            family_name: Family name (e.g., "Primitives", "Curves")

        Returns:
            List of command names in the family
        """
        if self._structure_cache is None:
            return []

        families = self._structure_cache.get("families", {})
        family_data = families.get(family_name, {})
        return family_data.get("commands", [])

    def get_all_families(self) -> list[str]:
        """Get list of all family names.

        Returns:
            List of family names
        """
        if self._structure_cache is None:
            return []
        return list(self._structure_cache.get("families", {}).keys())

    def get_mode_pattern(self, mode_name: str) -> Optional[dict]:
        """Get a common mode pattern by name.

        Mode patterns are modes that appear across multiple commands
        with similar syntax (e.g., "center", "3point", "diameter").

        Args:
            mode_name: Mode name (e.g., "center", "3point")

        Returns:
            Dict with:
            - name: Mode name
            - commands: Commands that have this mode
            - typical_syntax: Typical syntax template
            - typical_gotcha: Common gotcha for this mode
        """
        if self._structure_cache is None:
            return None

        mode_patterns = self._structure_cache.get("mode_patterns", {})
        return mode_patterns.get(mode_name)

    # =========================================================================
    # TIERED ACCESS METHODS (Phase 4.2)
    # =========================================================================

    def get_quick(self, command: str) -> Optional[str]:
        """Get the QUICK tier summary for a command (~20 tokens).

        The quick tier contains essential facts only - use when you
        know the tool and just need a refresher.

        Args:
            command: Command name

        Returns:
            Quick summary string or None if not available
        """
        if self._condensed_cache is None:
            return None

        normalized = self._normalize_command(command)
        commands = self._condensed_cache.get("commands", {})
        cmd_data = commands.get(normalized)

        if cmd_data is None:
            return None

        return cmd_data.get("quick")

    def get_context(self, command: str, context_name: Optional[str] = None) -> Optional[str]:
        """Get the CONTEXT tier for a command (~50 tokens per context).

        The context tier contains specific rules for a usage context.
        If context_name is provided, returns just that context.
        Otherwise returns all contexts.

        Args:
            command: Command name
            context_name: Optional specific context (mode) name

        Returns:
            Context string or dict of contexts, or None if not available
        """
        if self._condensed_cache is None:
            return None

        normalized = self._normalize_command(command)
        commands = self._condensed_cache.get("commands", {})
        cmd_data = commands.get(normalized)

        if cmd_data is None:
            return None

        contexts = cmd_data.get("contexts", {})

        if context_name is not None:
            return contexts.get(context_name)

        return contexts if contexts else None

    def get_errors(self, command: str) -> Optional[str]:
        """Get the ERRORS tier for a command (~30 tokens).

        The errors tier contains what fails and why - use when debugging.

        Args:
            command: Command name

        Returns:
            Errors summary string or None if not available
        """
        if self._condensed_cache is None:
            return None

        normalized = self._normalize_command(command)
        commands = self._condensed_cache.get("commands", {})
        cmd_data = commands.get(normalized)

        if cmd_data is None:
            return None

        return cmd_data.get("errors")

    def get_tiered(
        self,
        command: str,
        tier: str = "context",
        context_name: Optional[str] = None
    ) -> Optional[dict]:
        """Get tiered knowledge for a command.

        This is the main entry point for tiered access. Returns the
        appropriate tier based on the depth parameter.

        Args:
            command: Command name
            tier: One of "quick", "context", "errors"
            context_name: For "context" tier, optional specific context

        Returns:
            Dict with:
            - tier: The tier level
            - data: The tier content
            - family: The command's family (if known)
            - similar_commands: Similar commands (if any)
            - token_estimate: Approximate token count
        """
        normalized = self._normalize_command(command)
        family = self.get_family(command)
        similar = [s["command"] for s in self.get_similar_commands(command)[:3]]

        if tier == "quick":
            data = self.get_quick(command)
            token_estimate = 20
        elif tier == "context":
            data = self.get_context(command, context_name)
            token_estimate = 50 if context_name else 100
        elif tier == "errors":
            data = self.get_errors(command)
            token_estimate = 30
        else:
            return None

        if data is None:
            return None

        return {
            "command": normalized,
            "tier": tier,
            "data": data,
            "family": family,
            "similar_commands": similar,
            "token_estimate": token_estimate,
        }

    def has_tiered_knowledge(self, command: str) -> bool:
        """Check if tiered knowledge is available for a command.

        Args:
            command: Command name

        Returns:
            True if tiered knowledge exists
        """
        if self._condensed_cache is None:
            return False

        normalized = self._normalize_command(command)
        commands = self._condensed_cache.get("commands", {})
        return normalized in commands

    def update(self, knowledge: CommandKnowledge) -> bool:
        """Update or add a command with full knowledge object.

        This method is used by CommandLearner.consolidate_command() to store
        consolidated command patterns.

        Args:
            knowledge: CommandKnowledge object with all fields populated

        Returns:
            True if updated successfully
        """
        if self._cache is None:
            self._cache = {"version": "1.0", "commands": {}}

        if "commands" not in self._cache:
            self._cache["commands"] = {}

        normalized = self._normalize_command(knowledge.command)
        now = datetime.now(timezone.utc).isoformat()

        # Convert modes to dict format
        modes_dict = {}
        for mode_name, mode in knowledge.modes.items():
            if isinstance(mode, ModeKnowledge):
                modes_dict[mode_name] = {
                    "syntax": mode.syntax,
                    "dialogue": mode.dialogue,
                    "example": mode.example,
                    "description": mode.description,
                }
            elif isinstance(mode, dict):
                modes_dict[mode_name] = mode
            else:
                modes_dict[mode_name] = {"syntax": str(mode)}

        cmd_data = {
            "command": normalized,
            "description": knowledge.description,
            "modes": modes_dict,
            "options": knowledge.options or {},
            "preconditions": knowledge.preconditions or {},
            "gotchas": knowledge.gotchas or [],
            "related_commands": knowledge.related_commands or [],
            "observations_count": knowledge.observations_count,
            "last_updated": now,
        }

        self._cache["commands"][normalized] = cmd_data
        self._dirty = True

        # Auto-save
        self.save()

        logger.info(f"Updated command knowledge for {normalized}")
        return True

    # =========================================================================
    # WRITE OPERATIONS
    # =========================================================================

    def add_command(self, command: str, description: str = "") -> CommandKnowledge:
        """Add a new command to the knowledge base.

        Args:
            command: Command name (e.g., "-Loft")
            description: Command description

        Returns:
            The created CommandKnowledge object
        """
        if self._cache is None:
            self._cache = {"version": "1.0", "commands": {}}

        normalized = self._normalize_command(command)

        if "commands" not in self._cache:
            self._cache["commands"] = {}

        now = datetime.now(timezone.utc).isoformat()

        cmd_data = {
            "command": normalized,
            "description": description,
            "modes": {},
            "options": {},
            "preconditions": {},
            "gotchas": [],
            "related_commands": [],
            "observations_count": 0,
            "last_updated": now,
        }

        self._cache["commands"][normalized] = cmd_data
        self._dirty = True

        return CommandKnowledge.from_dict(normalized, cmd_data)

    def add_mode(
        self,
        command: str,
        mode_name: str,
        syntax: str,
        dialogue: str = "",
        example: str = "",
        description: str = "",
    ) -> bool:
        """Add a new mode to a command.

        Args:
            command: Command name
            mode_name: Mode name (e.g., "center", "3point")
            syntax: Syntax template
            dialogue: Dialogue description
            example: Example usage
            description: Mode description

        Returns:
            True if added, False if command not found
        """
        normalized = self._normalize_command(command)

        if self._cache is None or normalized not in self._cache.get("commands", {}):
            # Create command if it doesn't exist
            self.add_command(normalized)

        cmd_data = self._cache["commands"][normalized]

        if "modes" not in cmd_data:
            cmd_data["modes"] = {}

        cmd_data["modes"][mode_name] = {
            "syntax": syntax,
            "dialogue": dialogue,
            "example": example,
            "description": description,
        }

        cmd_data["last_updated"] = datetime.now(timezone.utc).isoformat()
        self._dirty = True

        return True

    def update_mode(
        self,
        command: str,
        mode_name: str,
        updates: dict,
    ) -> bool:
        """Update an existing mode.

        Args:
            command: Command name
            mode_name: Mode name to update
            updates: Dictionary of fields to update

        Returns:
            True if updated, False if not found
        """
        normalized = self._normalize_command(command)

        if self._cache is None:
            return False

        commands = self._cache.get("commands", {})
        if normalized not in commands:
            return False

        cmd_data = commands[normalized]
        modes = cmd_data.get("modes", {})

        if mode_name not in modes:
            return False

        modes[mode_name].update(updates)
        cmd_data["last_updated"] = datetime.now(timezone.utc).isoformat()
        self._dirty = True

        return True

    def add_gotcha(self, command: str, gotcha: str) -> bool:
        """Add a new gotcha to a command.

        Args:
            command: Command name
            gotcha: Gotcha string to add

        Returns:
            True if added, False if command not found or duplicate
        """
        normalized = self._normalize_command(command)

        if self._cache is None:
            return False

        commands = self._cache.get("commands", {})
        if normalized not in commands:
            return False

        cmd_data = commands[normalized]

        if "gotchas" not in cmd_data:
            cmd_data["gotchas"] = []

        # Avoid duplicates
        if gotcha in cmd_data["gotchas"]:
            return False

        cmd_data["gotchas"].append(gotcha)
        cmd_data["last_updated"] = datetime.now(timezone.utc).isoformat()
        self._dirty = True

        return True

    def add_option(self, command: str, option: str, description: str) -> bool:
        """Add a new option to a command.

        Args:
            command: Command name
            option: Option flag (e.g., "_Center")
            description: Option description

        Returns:
            True if added, False if command not found
        """
        normalized = self._normalize_command(command)

        if self._cache is None:
            return False

        commands = self._cache.get("commands", {})
        if normalized not in commands:
            return False

        cmd_data = commands[normalized]

        if "options" not in cmd_data:
            cmd_data["options"] = {}

        cmd_data["options"][option] = description
        cmd_data["last_updated"] = datetime.now(timezone.utc).isoformat()
        self._dirty = True

        return True

    def increment_observations(self, command: str) -> bool:
        """Increment the observation count for a command.

        Args:
            command: Command name

        Returns:
            True if incremented, False if command not found
        """
        normalized = self._normalize_command(command)

        if self._cache is None:
            return False

        commands = self._cache.get("commands", {})
        if normalized not in commands:
            return False

        cmd_data = commands[normalized]
        cmd_data["observations_count"] = cmd_data.get("observations_count", 0) + 1
        cmd_data["last_updated"] = datetime.now(timezone.utc).isoformat()
        self._dirty = True

        return True

    def set_description(self, command: str, description: str) -> bool:
        """Set the description for a command.

        Args:
            command: Command name
            description: New description

        Returns:
            True if set, False if command not found
        """
        normalized = self._normalize_command(command)

        if self._cache is None:
            return False

        commands = self._cache.get("commands", {})
        if normalized not in commands:
            return False

        cmd_data = commands[normalized]
        cmd_data["description"] = description
        cmd_data["last_updated"] = datetime.now(timezone.utc).isoformat()
        self._dirty = True

        return True

    def set_related_commands(self, command: str, related: list[str]) -> bool:
        """Set related commands for a command.

        Args:
            command: Command name
            related: List of related command names

        Returns:
            True if set, False if command not found
        """
        normalized = self._normalize_command(command)

        if self._cache is None:
            return False

        commands = self._cache.get("commands", {})
        if normalized not in commands:
            return False

        cmd_data = commands[normalized]
        cmd_data["related_commands"] = related
        cmd_data["last_updated"] = datetime.now(timezone.utc).isoformat()
        self._dirty = True

        return True

    # =========================================================================
    # STALENESS TRACKING (P2)
    # =========================================================================

    def record_gotcha_success(self, command: str) -> bool:
        """Record that a gotcha was injected and the tool succeeded.

        Updates the command's observations_count and last_updated timestamp.
        Marks dirty but does NOT persist immediately — the next save() or
        batch operation will flush to disk.

        Args:
            command: Command name (e.g. "-Box").

        Returns:
            True if updated, False if command not found.
        """
        normalized = self._normalize_command(command)

        if self._cache is None:
            return False

        commands = self._cache.get("commands", {})
        if normalized not in commands:
            return False

        cmd_data = commands[normalized]
        cmd_data["observations_count"] = cmd_data.get("observations_count", 0) + 1
        cmd_data["last_updated"] = datetime.now(timezone.utc).isoformat()
        self._dirty = True

        return True

    # =========================================================================
    # PERSISTENCE
    # =========================================================================

    def save(self) -> bool:
        """Persist changes to disk.

        Returns:
            True if saved successfully
        """
        if self._cache is None:
            return False

        if not self._dirty:
            logger.debug("No changes to save")
            return True

        try:
            # Update metadata
            self._cache["last_updated"] = datetime.now(timezone.utc).isoformat()

            # Ensure directory exists
            self.path.parent.mkdir(parents=True, exist_ok=True)

            # Write atomically
            temp_path = self.path.with_suffix(".tmp")
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(self._cache, f, indent=2, ensure_ascii=False)

            temp_path.replace(self.path)

            self._dirty = False
            logger.info(f"Saved command knowledge to {self.path}")
            return True

        except Exception as e:
            logger.error(f"Failed to save command knowledge: {e}")
            return False

    def reload(self) -> int:
        """Reload all knowledge from disk (discard caches).

        Reloads:
        - command_knowledge.json (flat command patterns)
        - command_structure.json (families, similar pairs, shared gotchas)
        - condensed_command_knowledge.json (tiered knowledge)

        Returns:
            Number of commands loaded
        """
        self._cache = None
        self._structure_cache = None
        self._condensed_cache = None
        self._command_to_family = {}
        self._dirty = False

        self._load()
        self._load_structure()
        self._load_condensed()

        return self.get_command_count()

    def _load(self) -> bool:
        """Load knowledge from disk."""
        read_path = _default_command_knowledge_read_path() if self._uses_default_path else self.path

        if not read_path.exists():
            logger.warning(f"Command knowledge file not found: {read_path}")
            self._cache = {"version": "1.0", "commands": {}}
            return False

        try:
            with open(read_path, 'r', encoding='utf-8') as f:
                self._cache = json.load(f)

            cmd_count = len(self._cache.get("commands", {}))
            logger.debug(f"Loaded command knowledge: {cmd_count} commands")
            return True

        except Exception as e:
            logger.error(f"Failed to load command knowledge: {e}")
            self._cache = {"version": "1.0", "commands": {}}
            return False

    def _load_structure(self) -> bool:
        """Load command structure (families, similar pairs, shared gotchas) from disk."""
        structure_path = _default_command_structure_path() if self._uses_default_structure_path else self.structure_path

        if not structure_path.exists():
            logger.debug(f"Command structure file not found: {structure_path}")
            self._structure_cache = None
            return False

        try:
            with open(structure_path, 'r', encoding='utf-8') as f:
                self._structure_cache = json.load(f)

            # Build reverse lookup: command -> family
            self._command_to_family = {}
            for family_name, family_data in self._structure_cache.get("families", {}).items():
                for cmd in family_data.get("commands", []):
                    normalized = self._normalize_command(cmd)
                    self._command_to_family[normalized] = family_name

            family_count = len(self._structure_cache.get("families", {}))
            logger.debug(f"Loaded command structure: {family_count} families")
            return True

        except Exception as e:
            logger.error(f"Failed to load command structure: {e}")
            self._structure_cache = None
            return False

    def _load_condensed(self) -> bool:
        """Load condensed (tiered) command knowledge from disk."""
        condensed_path = _default_condensed_command_path() if self._uses_default_condensed_path else self.condensed_path

        if not condensed_path.exists():
            logger.debug(f"Condensed knowledge file not found: {condensed_path}")
            self._condensed_cache = None
            return False

        try:
            with open(condensed_path, 'r', encoding='utf-8') as f:
                self._condensed_cache = json.load(f)

            cmd_count = len(self._condensed_cache.get("commands", {}))
            logger.debug(f"Loaded condensed knowledge: {cmd_count} commands")
            return True

        except Exception as e:
            logger.error(f"Failed to load condensed knowledge: {e}")
            self._condensed_cache = None
            return False

    def _normalize_command(self, command: str) -> str:
        """Normalize command name to storage format.

        Args:
            command: Command name in any format

        Returns:
            Normalized command name (e.g., "-Box")
        """
        # Remove leading underscore if present
        cmd = command.lstrip("_")

        # Ensure dash prefix
        if not cmd.startswith("-"):
            cmd = "-" + cmd

        return cmd

    # =========================================================================
    # PARSING / REVERSE ENGINEERING
    # =========================================================================

    def parse_command_string(
        self,
        command_string: str,
        mode: Optional[str] = None
    ) -> Optional[dict]:
        """Parse a command string into structured parameters.

        Given a command string like "_-Box 0,0,0 10,10,0 5", this method:
        1. Extracts the command name
        2. Finds the matching syntax template
        3. Maps values to parameter names

        Args:
            command_string: Full command string (e.g., "_-Box 0,0,0 10,10,0 5")
            mode: Optional mode hint (if known)

        Returns:
            Dict with parsed info, or None if parsing fails:
            {
                "command": "-Box",
                "mode": "default",
                "syntax": "_-Box <corner1> <corner2> [height]",
                "parameters": {"corner1": "0,0,0", "corner2": "10,10,0", "height": "5"},
                "options_used": ["_Center"] (if any)
            }
        """
        if not command_string or not command_string.strip():
            return None

        # Split command string into tokens
        tokens = command_string.strip().split()
        if not tokens:
            return None

        # Extract command name (first token)
        cmd_token = tokens[0]
        cmd_name = self._normalize_command(cmd_token)

        # Get command knowledge
        cmd_knowledge = self.get_command(cmd_name)
        if cmd_knowledge is None:
            # Return basic parse without template matching
            return {
                "command": cmd_name,
                "mode": "unknown",
                "syntax": None,
                "parameters": {},
                "raw_values": tokens[1:],
                "options_used": []
            }

        # Detect mode from command string if not provided
        detected_mode = mode
        if detected_mode is None:
            detected_mode = self._detect_mode_from_tokens(tokens[1:], cmd_knowledge)

        # Get syntax template for this mode
        mode_knowledge = cmd_knowledge.modes.get(detected_mode)
        if mode_knowledge is None:
            mode_knowledge = cmd_knowledge.modes.get("default")
            detected_mode = "default"

        if mode_knowledge is None:
            return {
                "command": cmd_name,
                "mode": detected_mode,
                "syntax": None,
                "parameters": {},
                "raw_values": tokens[1:],
                "options_used": []
            }

        syntax_template = mode_knowledge.syntax

        # Parse values using syntax template
        result = parse_command_with_template(command_string, syntax_template)

        return {
            "command": cmd_name,
            "mode": detected_mode,
            "syntax": syntax_template,
            "parameters": result.get("parameters", {}),
            "options_used": result.get("options_used", []),
            "raw_values": result.get("unmatched", [])
        }

    def _detect_mode_from_tokens(
        self,
        tokens: list[str],
        cmd_knowledge: CommandKnowledge
    ) -> str:
        """Detect mode from command tokens.

        Looks for mode option keywords in the tokens.

        Args:
            tokens: Command tokens (excluding command name)
            cmd_knowledge: Command knowledge to check modes against

        Returns:
            Detected mode name or "default"
        """
        # Check each token for mode keywords
        for token in tokens:
            if token.startswith('_') and ',' not in token:
                token_lower = token.lstrip('_').lower()
                # Check if this matches a known mode
                for mode_name in cmd_knowledge.modes.keys():
                    if mode_name.lower() == token_lower:
                        return mode_name
                # Check options that might indicate modes
                for option in cmd_knowledge.options.keys():
                    if option.lstrip('_').lower() == token_lower:
                        # Option might correspond to a mode
                        if token_lower in cmd_knowledge.modes:
                            return token_lower

        return "default"

    # =========================================================================
    # STATS AND UTILITIES
    # =========================================================================

    def get_stats(self) -> dict:
        """Get statistics about the knowledge base.

        Returns:
            Dictionary with stats including structure and tiered knowledge
        """
        stats = {
            "commands": 0,
            "modes": 0,
            "gotchas": 0,
            "options": 0,
            "version": "unknown",
            "last_updated": "unknown",
            # Structure stats
            "families": 0,
            "similar_pairs": 0,
            "shared_gotchas": 0,
            "mode_patterns": 0,
            "has_structure": False,
            # Tiered knowledge stats
            "tiered_commands": 0,
            "has_tiered_knowledge": False,
            "token_reduction_percent": 0,
        }

        # Flat knowledge stats
        if self._cache is not None:
            commands = self._cache.get("commands", {})
            stats["commands"] = len(commands)
            stats["version"] = self._cache.get("version", "unknown")
            stats["last_updated"] = self._cache.get("last_updated", "unknown")

            for cmd_data in commands.values():
                stats["modes"] += len(cmd_data.get("modes", {}))
                stats["gotchas"] += len(cmd_data.get("gotchas", []))
                stats["options"] += len(cmd_data.get("options", {}))

        # Structure stats
        if self._structure_cache is not None:
            stats["has_structure"] = True
            stats["families"] = len(self._structure_cache.get("families", {}))
            stats["similar_pairs"] = len(self._structure_cache.get("similar_pairs", []))
            stats["shared_gotchas"] = len(self._structure_cache.get("shared_gotchas", {}))
            stats["mode_patterns"] = len(self._structure_cache.get("mode_patterns", {}))

        # Tiered knowledge stats
        if self._condensed_cache is not None:
            stats["has_tiered_knowledge"] = True
            stats["tiered_commands"] = len(self._condensed_cache.get("commands", {}))
            stats["token_reduction_percent"] = self._condensed_cache.get("reduction_percent", 0)

        return stats

    def is_dirty(self) -> bool:
        """Check if there are unsaved changes.

        Returns:
            True if there are unsaved changes
        """
        return self._dirty


# =============================================================================
# UTILITY FUNCTIONS FOR COMMAND PARSING
# =============================================================================


def parse_syntax_template(template: str) -> tuple[str, list[tuple[str, bool]]]:
    """Parse a syntax template to extract parameter placeholders.

    Args:
        template: Syntax template (e.g., "_-Box <corner1> <corner2> [height]")

    Returns:
        Tuple of (command_pattern, [(param_name, is_optional), ...])

    Example:
        parse_syntax_template("_-Box <corner1> <corner2> [height]")
        -> ("_-Box", [("corner1", False), ("corner2", False), ("height", True)])
    """
    # Extract command (first token)
    parts = template.split()
    if not parts:
        return ("", [])

    command = parts[0]
    params = []

    # Find all required params <name> and optional params [name]
    for part in parts[1:]:
        if part.startswith('<') and part.endswith('>'):
            param_name = part[1:-1]
            params.append((param_name, False))  # Required
        elif part.startswith('[') and part.endswith(']'):
            param_name = part[1:-1]
            params.append((param_name, True))  # Optional
        elif part.startswith('_'):
            # Mode option keyword - not a parameter
            pass

    return (command, params)


def parse_command_with_template(command_string: str, template: str) -> dict:
    """Parse a command string using a syntax template.

    Args:
        command_string: Full command (e.g., "_-Box 0,0,0 10,10,0 5")
        template: Syntax template (e.g., "_-Box <corner1> <corner2> [height]")

    Returns:
        Dict with:
        - parameters: {param_name: value}
        - options_used: [option keywords found]
        - unmatched: [values that couldn't be matched]

    Example:
        parse_command_with_template(
            "_-Box 0,0,0 10,10,0 5",
            "_-Box <corner1> <corner2> [height]"
        )
        -> {
            "parameters": {"corner1": "0,0,0", "corner2": "10,10,0", "height": "5"},
            "options_used": [],
            "unmatched": []
        }
    """
    result = {
        "parameters": {},
        "options_used": [],
        "unmatched": []
    }

    if not command_string or not template:
        return result

    # Parse template
    _, param_specs = parse_syntax_template(template)

    # Split command into tokens
    cmd_tokens = command_string.strip().split()
    if not cmd_tokens:
        return result

    # Skip command name (first token)
    value_tokens = cmd_tokens[1:]

    # Separate options from values
    options = []
    values = []
    for token in value_tokens:
        if token.startswith('_') and ',' not in token:
            # This is an option keyword
            options.append(token)
        else:
            # This is a value
            values.append(token)

    result["options_used"] = options

    # Match values to parameters in order
    param_idx = 0
    for value in values:
        if param_idx < len(param_specs):
            param_name, is_optional = param_specs[param_idx]
            result["parameters"][param_name] = value
            param_idx += 1
        else:
            result["unmatched"].append(value)

    return result


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_command_knowledge_store: CommandKnowledgeStore | None = None


def get_command_knowledge_store() -> CommandKnowledgeStore:
    """Get the global CommandKnowledgeStore singleton."""
    global _command_knowledge_store
    if _command_knowledge_store is None:
        _command_knowledge_store = CommandKnowledgeStore()
    return _command_knowledge_store
