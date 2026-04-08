"""Roadmap Manager for Rook.

Provides interface to learning_roadmap.json for tracking command learning progress.

This is used by:
- Learning mode: Get next command to learn, mark as learned
- Progress tracking: Show overall and per-phase progress
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from ..runtime_paths import resolve_readable_knowledge_path, resolve_writable_knowledge_path

logger = logging.getLogger(__name__)


def _default_roadmap_path() -> Path:
    return resolve_writable_knowledge_path("commands", "learning_roadmap.json")


def _default_roadmap_read_path() -> Path:
    return resolve_readable_knowledge_path("commands", "learning_roadmap.json")


@dataclass
class CommandToLearn:
    """A command from the learning roadmap.

    Example:
        CommandToLearn(
            name="Sphere",
            category="Primitives",
            phase=1,
            learned=False,
            attempts=0,
            last_attempt=None
        )
    """
    name: str
    category: str
    phase: int
    learned: bool = False
    attempts: int = 0
    last_attempt: Optional[str] = None
    priority: int = 0  # Lower = higher priority

    @property
    def command_name(self) -> str:
        """Get the Rhino command name format (with dash prefix)."""
        return f"-{self.name}"


@dataclass
class PhaseProgress:
    """Progress for a single phase.

    Example:
        PhaseProgress(
            phase=1,
            name="Core geometry creation and manipulation",
            total=50,
            learned=12,
            percentage=24.0,
            categories=["Primitives", "Curves", ...]
        )
    """
    phase: int
    name: str
    total: int
    learned: int
    percentage: float
    categories: list[str] = field(default_factory=list)


@dataclass
class OverallProgress:
    """Overall learning progress.

    Example:
        OverallProgress(
            total_commands=1119,
            learned_commands=49,
            percentage=4.4,
            total_phases=7,
            completed_phases=0,
            current_phase=1
        )
    """
    total_commands: int
    learned_commands: int
    percentage: float
    total_phases: int
    completed_phases: int
    current_phase: int


class RoadmapManager:
    """Interface to learning_roadmap.json with progress tracking.

    Usage:
        rm = RoadmapManager()

        # Get next command to learn
        cmd = rm.get_next_unlearned()
        print(f"Next: {cmd.name} ({cmd.category})")

        # Mark as learned
        rm.mark_learned("Sphere")
        rm.save()

        # Check progress
        progress = rm.get_overall_progress()
        print(f"{progress.percentage:.1f}% complete")
    """

    def __init__(self, path: Optional[Path] = None):
        """Initialize the manager.

        Args:
            path: Optional path to learning_roadmap.json.
                  Defaults to knowledge/commands/learning_roadmap.json
        """
        self._uses_default_path = path is None
        self.path = Path(path) if path is not None else _default_roadmap_path()
        self._cache: Optional[dict] = None
        self._dirty: bool = False
        self._load()

    # =========================================================================
    # READ OPERATIONS
    # =========================================================================

    def get_next_unlearned(self, phase: Optional[int] = None, category: Optional[str] = None) -> Optional[CommandToLearn]:
        """Get the next unlearned command.

        Commands are returned in priority order:
        1. Current phase first
        2. Within phase, by category order
        3. Within category, alphabetically

        Args:
            phase: Optional phase filter (1-7)
            category: Optional category filter

        Returns:
            CommandToLearn object or None if all learned
        """
        if self._cache is None:
            return None

        for phase_data in self._cache.get("phases", []):
            phase_num = phase_data.get("phase", 0)

            # Skip if phase filter doesn't match
            if phase is not None and phase_num != phase:
                continue

            for cmd_data in phase_data.get("commands", []):
                # Skip learned commands
                if cmd_data.get("learned", False):
                    continue

                # Skip if category filter doesn't match
                cmd_category = cmd_data.get("category", "")
                if category is not None and cmd_category != category:
                    continue

                return CommandToLearn(
                    name=cmd_data.get("name", ""),
                    category=cmd_category,
                    phase=phase_num,
                    learned=False,
                    attempts=cmd_data.get("attempts", 0),
                    last_attempt=cmd_data.get("last_attempt"),
                    priority=cmd_data.get("priority", 0),
                )

        return None

    def get_unlearned_commands(self, limit: int = 10, phase: Optional[int] = None) -> list[CommandToLearn]:
        """Get multiple unlearned commands.

        Args:
            limit: Maximum number to return
            phase: Optional phase filter

        Returns:
            List of CommandToLearn objects
        """
        if self._cache is None:
            return []

        result = []

        for phase_data in self._cache.get("phases", []):
            phase_num = phase_data.get("phase", 0)

            if phase is not None and phase_num != phase:
                continue

            for cmd_data in phase_data.get("commands", []):
                if cmd_data.get("learned", False):
                    continue

                result.append(CommandToLearn(
                    name=cmd_data.get("name", ""),
                    category=cmd_data.get("category", ""),
                    phase=phase_num,
                    learned=False,
                    attempts=cmd_data.get("attempts", 0),
                    last_attempt=cmd_data.get("last_attempt"),
                    priority=cmd_data.get("priority", 0),
                ))

                if len(result) >= limit:
                    return result

        return result

    def get_command(self, name: str) -> Optional[CommandToLearn]:
        """Get a specific command from the roadmap.

        Args:
            name: Command name (with or without dash prefix)

        Returns:
            CommandToLearn object or None if not found
        """
        if self._cache is None:
            return None

        # Normalize name
        normalized = name.lstrip("-")

        for phase_data in self._cache.get("phases", []):
            phase_num = phase_data.get("phase", 0)

            for cmd_data in phase_data.get("commands", []):
                if cmd_data.get("name", "").lower() == normalized.lower():
                    return CommandToLearn(
                        name=cmd_data.get("name", ""),
                        category=cmd_data.get("category", ""),
                        phase=phase_num,
                        learned=cmd_data.get("learned", False),
                        attempts=cmd_data.get("attempts", 0),
                        last_attempt=cmd_data.get("last_attempt"),
                        priority=cmd_data.get("priority", 0),
                    )

        return None

    def get_phase_progress(self, phase_num: int) -> Optional[PhaseProgress]:
        """Get progress for a specific phase.

        Args:
            phase_num: Phase number (1-7)

        Returns:
            PhaseProgress object or None if phase not found
        """
        if self._cache is None:
            return None

        for phase_data in self._cache.get("phases", []):
            if phase_data.get("phase") == phase_num:
                total = len(phase_data.get("commands", []))
                learned = sum(1 for c in phase_data.get("commands", []) if c.get("learned", False))

                return PhaseProgress(
                    phase=phase_num,
                    name=phase_data.get("name", ""),
                    total=total,
                    learned=learned,
                    percentage=100.0 * learned / max(total, 1),
                    categories=phase_data.get("categories", []),
                )

        return None

    def get_overall_progress(self) -> OverallProgress:
        """Get overall learning progress.

        Returns:
            OverallProgress object with totals and percentages
        """
        if self._cache is None:
            return OverallProgress(
                total_commands=0,
                learned_commands=0,
                percentage=0.0,
                total_phases=0,
                completed_phases=0,
                current_phase=1,
            )

        total = 0
        learned = 0
        completed_phases = 0
        current_phase = 1
        total_phases = len(self._cache.get("phases", []))

        for phase_data in self._cache.get("phases", []):
            phase_num = phase_data.get("phase", 0)
            phase_total = len(phase_data.get("commands", []))
            phase_learned = sum(1 for c in phase_data.get("commands", []) if c.get("learned", False))

            total += phase_total
            learned += phase_learned

            if phase_learned == phase_total and phase_total > 0:
                completed_phases += 1
            elif phase_learned < phase_total:
                # This is the current phase (first incomplete one)
                if current_phase == 1 or phase_num < current_phase:
                    current_phase = phase_num

        return OverallProgress(
            total_commands=total,
            learned_commands=learned,
            percentage=100.0 * learned / max(total, 1),
            total_phases=total_phases,
            completed_phases=completed_phases,
            current_phase=current_phase,
        )

    def get_categories(self, phase: Optional[int] = None) -> list[str]:
        """Get all categories.

        Args:
            phase: Optional phase filter

        Returns:
            List of category names
        """
        if self._cache is None:
            return []

        categories = set()
        for phase_data in self._cache.get("phases", []):
            if phase is not None and phase_data.get("phase") != phase:
                continue
            categories.update(phase_data.get("categories", []))

        return sorted(categories)

    def get_phases(self) -> list[PhaseProgress]:
        """Get progress for all phases.

        Returns:
            List of PhaseProgress objects
        """
        if self._cache is None:
            return []

        result = []
        for phase_data in self._cache.get("phases", []):
            phase_num = phase_data.get("phase", 0)
            progress = self.get_phase_progress(phase_num)
            if progress:
                result.append(progress)

        return result

    # =========================================================================
    # WRITE OPERATIONS
    # =========================================================================

    def mark_learned(self, name: str) -> bool:
        """Mark a command as learned.

        Args:
            name: Command name (with or without dash prefix)

        Returns:
            True if marked, False if not found
        """
        if self._cache is None:
            return False

        normalized = name.lstrip("-")

        for phase_data in self._cache.get("phases", []):
            for cmd_data in phase_data.get("commands", []):
                if cmd_data.get("name", "").lower() == normalized.lower():
                    cmd_data["learned"] = True
                    cmd_data["last_attempt"] = datetime.now(timezone.utc).isoformat()
                    self._dirty = True
                    return True

        return False

    def mark_unlearned(self, name: str) -> bool:
        """Mark a command as not learned (reset).

        Args:
            name: Command name

        Returns:
            True if marked, False if not found
        """
        if self._cache is None:
            return False

        normalized = name.lstrip("-")

        for phase_data in self._cache.get("phases", []):
            for cmd_data in phase_data.get("commands", []):
                if cmd_data.get("name", "").lower() == normalized.lower():
                    cmd_data["learned"] = False
                    self._dirty = True
                    return True

        return False

    def record_attempt(self, name: str, success: bool) -> bool:
        """Record a learning attempt.

        Args:
            name: Command name
            success: Whether the attempt succeeded

        Returns:
            True if recorded, False if not found
        """
        if self._cache is None:
            return False

        normalized = name.lstrip("-")

        for phase_data in self._cache.get("phases", []):
            for cmd_data in phase_data.get("commands", []):
                if cmd_data.get("name", "").lower() == normalized.lower():
                    cmd_data["attempts"] = cmd_data.get("attempts", 0) + 1
                    cmd_data["last_attempt"] = datetime.now(timezone.utc).isoformat()

                    if success:
                        cmd_data["learned"] = True

                    self._dirty = True
                    return True

        return False

    def set_priority(self, name: str, priority: int) -> bool:
        """Set priority for a command (lower = higher priority).

        Args:
            name: Command name
            priority: Priority value (0 = highest)

        Returns:
            True if set, False if not found
        """
        if self._cache is None:
            return False

        normalized = name.lstrip("-")

        for phase_data in self._cache.get("phases", []):
            for cmd_data in phase_data.get("commands", []):
                if cmd_data.get("name", "").lower() == normalized.lower():
                    cmd_data["priority"] = priority
                    self._dirty = True
                    return True

        return False

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
            # Ensure directory exists
            self.path.parent.mkdir(parents=True, exist_ok=True)

            # Write atomically
            temp_path = self.path.with_suffix(".tmp")
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(self._cache, f, indent=2, ensure_ascii=False)

            temp_path.replace(self.path)

            self._dirty = False
            logger.info(f"Saved learning roadmap to {self.path}")
            return True

        except Exception as e:
            logger.error(f"Failed to save learning roadmap: {e}")
            return False

    def reload(self) -> bool:
        """Reload from disk (discard cache).

        Returns:
            True if loaded successfully
        """
        self._cache = None
        self._dirty = False
        return self._load()

    def _load(self) -> bool:
        """Load roadmap from disk."""
        read_path = _default_roadmap_read_path() if self._uses_default_path else self.path

        if not read_path.exists():
            logger.warning(f"Learning roadmap file not found: {read_path}")
            self._cache = {"phases": []}
            return False

        try:
            with open(read_path, 'r', encoding='utf-8') as f:
                self._cache = json.load(f)

            progress = self.get_overall_progress()
            logger.debug(f"Loaded learning roadmap: {progress.learned_commands}/{progress.total_commands} learned")
            return True

        except Exception as e:
            logger.error(f"Failed to load learning roadmap: {e}")
            self._cache = {"phases": []}
            return False

    # =========================================================================
    # STATS AND UTILITIES
    # =========================================================================

    def get_stats(self) -> dict:
        """Get statistics about the roadmap.

        Returns:
            Dictionary with stats
        """
        progress = self.get_overall_progress()

        return {
            "total_commands": progress.total_commands,
            "learned_commands": progress.learned_commands,
            "percentage": progress.percentage,
            "total_phases": progress.total_phases,
            "completed_phases": progress.completed_phases,
            "current_phase": progress.current_phase,
            "categories": self.get_categories(),
        }

    def is_dirty(self) -> bool:
        """Check if there are unsaved changes.

        Returns:
            True if there are unsaved changes
        """
        return self._dirty

    def find_commands_by_category(self, category: str, learned_only: bool = False) -> list[CommandToLearn]:
        """Find all commands in a category.

        Args:
            category: Category name
            learned_only: If True, only return learned commands

        Returns:
            List of CommandToLearn objects
        """
        if self._cache is None:
            return []

        result = []

        for phase_data in self._cache.get("phases", []):
            phase_num = phase_data.get("phase", 0)

            for cmd_data in phase_data.get("commands", []):
                if cmd_data.get("category", "") != category:
                    continue

                is_learned = cmd_data.get("learned", False)
                if learned_only and not is_learned:
                    continue

                result.append(CommandToLearn(
                    name=cmd_data.get("name", ""),
                    category=category,
                    phase=phase_num,
                    learned=is_learned,
                    attempts=cmd_data.get("attempts", 0),
                    last_attempt=cmd_data.get("last_attempt"),
                    priority=cmd_data.get("priority", 0),
                ))

        return result
