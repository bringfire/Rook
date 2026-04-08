"""MABWiser-based selectors for choosing between DSPy-generated candidates.

These selectors bridge DSPy's generation capabilities with MABWiser's
principled exploration/exploitation tradeoff.

Architecture:
- HypothesisSelector: Choose which hypothesis to test from DSPy Planner
- FixSelector: Choose which fix to try from DSPy Diagnoser
- PrioritySelector: Reorder investigation targets by expected value

All selectors use Thompson Sampling for exploration/exploitation balance
and persist their learned parameters across sessions.
"""

import hashlib
import json
import logging
import pickle
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
from ..runtime_paths import resolve_writable_knowledge_path

logger = logging.getLogger("rook.learning.mab_selectors")

# Try to import MABWiser
try:
    from mabwiser.mab import MAB, LearningPolicy, NeighborhoodPolicy
    MAB_AVAILABLE = True
except ImportError:
    MAB_AVAILABLE = False
    logger.warning("MABWiser not available - selectors will use fallback behavior")

# MAB Dormant Mode
# When True, MAB selectors return low confidence forcing DSPy to handle all decisions.
# Updates still run to collect data for future analysis.
# Set to False when ready to enable MAB-based selection.
MAB_DORMANT = True

# Default persistence directory
SELECTORS_DIR = resolve_writable_knowledge_path("selectors")


@dataclass
class SelectionContext:
    """Context for MAB selection decisions.

    This context is converted to a feature vector for contextual bandits,
    enabling context-aware exploration/exploitation tradeoffs.
    """
    tool_name: str
    existing_pattern_count: int = 0
    existing_antipattern_count: int = 0
    session_progress: float = 0.0  # 0-1, how far into session
    recent_success_rate: float = 0.5  # 0-1, success rate in recent attempts
    geometry_available: list[str] = field(default_factory=list)

    # Tool category mapping for one-hot encoding
    _TOOL_CATEGORIES = {
        "create": 0, "transform": 1, "measure": 2, "boolean": 3,
        "curve": 4, "brep": 5, "mesh": 6, "subd": 7, "block": 8,
        "layer": 9, "select": 10, "other": 11
    }

    def to_vector(self) -> list[float]:
        """Convert to feature vector for contextual MAB.

        Returns a 17-dimensional vector:
        - 12 dimensions: tool category one-hot encoding
        - 5 dimensions: normalized context features
        """
        # Determine tool category
        category = "other"
        for cat in self._TOOL_CATEGORIES:
            if cat in self.tool_name.lower():
                category = cat
                break

        # Build one-hot vector for category
        vector = [0.0] * 12
        vector[self._TOOL_CATEGORIES[category]] = 1.0

        # Add normalized context features
        vector.extend([
            min(self.existing_pattern_count / 10.0, 1.0),  # Normalize to [0,1]
            min(self.existing_antipattern_count / 5.0, 1.0),
            self.session_progress,
            self.recent_success_rate,
            min(len(self.geometry_available) / 5.0, 1.0),
        ])

        return vector


class HypothesisSelector:
    """Selects which hypothesis to test from DSPy-generated candidates.

    Uses Thompson Sampling to balance exploration (trying uncertain
    hypotheses) vs exploitation (trying hypotheses that worked before).

    Arms are hypothesis strings - each unique hypothesis becomes an arm.
    This allows learning across sessions about which types of hypotheses
    tend to be successful.
    """

    def __init__(self, persist_path: Optional[Path] = None):
        self.persist_path = persist_path or (SELECTORS_DIR / "hypothesis_selector.pkl")
        self.mab: Optional[MAB] = None
        self._arm_metadata: dict[str, dict] = {}  # arm_id -> metadata
        self._load()

    def select(
        self,
        hypotheses: list[str],
        context: SelectionContext,
    ) -> tuple[str, int]:
        """Select which hypothesis to test.

        Args:
            hypotheses: List of hypothesis strings from DSPy Planner
            context: Current context for selection

        Returns:
            Tuple of (selected_hypothesis, index in original list)
        """
        if not hypotheses:
            return "", 0

        if not MAB_AVAILABLE:
            # Fallback: return first hypothesis
            return hypotheses[0], 0

        # Ensure all hypotheses are registered as arms
        for hyp in hypotheses:
            self._ensure_arm(hyp)

        if self.mab is None or not self.mab.arms:
            return hypotheses[0], 0

        try:
            # Get predictions for all hypothesis arms
            valid_arms = [h for h in hypotheses if h in self.mab.arms]
            if not valid_arms:
                return hypotheses[0], 0

            # Get expected values for each arm
            expectations = self.mab.predict_expectations()

            # Find best among current hypotheses
            best_hyp = max(valid_arms, key=lambda h: expectations.get(h, 0.5))
            return best_hyp, hypotheses.index(best_hyp)

        except Exception as e:
            logger.warning(f"MAB prediction failed: {e}")
            return hypotheses[0], 0

    def update(
        self,
        hypothesis: str,
        success: bool,
        context: SelectionContext,
        nuanced_reward: Optional[float] = None,
    ):
        """Update MAB with outcome.

        Args:
            hypothesis: The hypothesis that was tested
            success: Whether it worked (for binary reward)
            context: Context at time of selection
            nuanced_reward: Optional nuanced reward from FeedbackComputer (0.0-1.0)
        """
        if not MAB_AVAILABLE or self.mab is None:
            return

        self._ensure_arm(hypothesis)

        # Use nuanced reward if available, otherwise binary
        # Thompson Sampling requires binary rewards - binarize continuous rewards
        if nuanced_reward is not None:
            reward = 1 if nuanced_reward > 0.5 else 0
        else:
            reward = 1 if success else 0

        try:
            self.mab.partial_fit([hypothesis], [reward])
            self._save()
        except Exception as e:
            logger.warning(f"MAB update failed: {e}")

    def _ensure_arm(self, hypothesis: str):
        """Ensure hypothesis is a valid arm in the MAB."""
        if self.mab is None:
            self.mab = MAB(
                arms=[hypothesis],
                learning_policy=LearningPolicy.ThompsonSampling(),
                seed=42
            )
            # Initialize with optimistic prior (binary: 1 = success)
            # Thompson Sampling requires binary rewards
            self.mab.fit([hypothesis], [1])
        elif hypothesis not in self.mab.arms:
            self.mab.add_arm(hypothesis)

    def _load(self):
        """Load MAB state from disk."""
        if self.persist_path.exists():
            try:
                with open(self.persist_path, 'rb') as f:
                    data = pickle.load(f)
                    self.mab = data.get('mab')
                    self._arm_metadata = data.get('metadata', {})
                logger.debug(f"Loaded hypothesis selector with {len(self.mab.arms) if self.mab else 0} arms")
            except Exception as e:
                logger.warning(f"Failed to load hypothesis selector: {e}")

    def _save(self):
        """Save MAB state to disk."""
        try:
            self.persist_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.persist_path, 'wb') as f:
                pickle.dump({
                    'mab': self.mab,
                    'metadata': self._arm_metadata
                }, f)
        except Exception as e:
            logger.warning(f"Failed to save hypothesis selector: {e}")

    def get_stats(self) -> dict:
        """Get selector statistics."""
        if self.mab is None:
            return {"arms": 0, "total_updates": 0}

        return {
            "arms": len(self.mab.arms),
            "top_arms": self._get_top_arms(5),
        }

    def _get_top_arms(self, n: int) -> list[tuple[str, float]]:
        """Get top n arms by expected value."""
        if self.mab is None:
            return []

        try:
            expectations = self.mab.predict_expectations()
            sorted_arms = sorted(expectations.items(), key=lambda x: x[1], reverse=True)
            return sorted_arms[:n]
        except Exception:
            return []


class FixSelector:
    """Selects which fix suggestion to try from DSPy-generated candidates.

    Similar to HypothesisSelector but specialized for error recovery.
    Arms are derived from fix content + error category + tool name,
    allowing learning about which types of fixes work for which errors.
    """

    def __init__(self, persist_path: Optional[Path] = None):
        self.persist_path = persist_path or (SELECTORS_DIR / "fix_selector.pkl")
        self.mab: Optional[MAB] = None
        self._load()

    def select(
        self,
        fixes: list[dict],
        error_category: str,
        tool_name: str,
    ) -> tuple[dict, int]:
        """Select which fix to try.

        Args:
            fixes: List of fix suggestions from DSPy Diagnoser
            error_category: Category of error being fixed
            tool_name: Tool that failed

        Returns:
            Tuple of (selected_fix, index in original list)
        """
        if not fixes:
            return {}, 0

        if not MAB_AVAILABLE:
            return fixes[0], 0

        # Create arm IDs from fix content
        arm_ids = [self._fix_to_arm_id(f, error_category, tool_name) for f in fixes]

        for arm_id in arm_ids:
            self._ensure_arm(arm_id)

        if self.mab is None:
            return fixes[0], 0

        try:
            expectations = self.mab.predict_expectations()
            valid_arms = [a for a in arm_ids if a in self.mab.arms]
            if not valid_arms:
                return fixes[0], 0

            best_arm = max(valid_arms, key=lambda a: expectations.get(a, 0.5))
            idx = arm_ids.index(best_arm)
            return fixes[idx], idx

        except Exception as e:
            logger.warning(f"Fix selector prediction failed: {e}")
            return fixes[0], 0

    def update(
        self,
        fix: dict,
        success: bool,
        error_category: str,
        tool_name: str,
        nuanced_reward: Optional[float] = None,
    ):
        """Update with outcome.

        Args:
            fix: The fix that was tried
            success: Whether it worked
            error_category: Category of error
            tool_name: Tool that was being fixed
            nuanced_reward: Optional nuanced reward (0.0-1.0)
        """
        if not MAB_AVAILABLE or self.mab is None:
            return

        arm_id = self._fix_to_arm_id(fix, error_category, tool_name)
        self._ensure_arm(arm_id)

        # Thompson Sampling requires binary rewards - binarize continuous rewards
        if nuanced_reward is not None:
            reward = 1 if nuanced_reward > 0.5 else 0
        else:
            reward = 1 if success else 0

        try:
            self.mab.partial_fit([arm_id], [reward])
            self._save()
        except Exception as e:
            logger.warning(f"Fix selector update failed: {e}")

    def _fix_to_arm_id(self, fix: dict, error_category: str, tool_name: str) -> str:
        """Convert fix to unique arm ID.

        Uses a hash of the fix content, error category, and tool name
        to create a stable identifier.
        """
        content = json.dumps({
            "fix": fix,
            "category": error_category,
            "tool": tool_name
        }, sort_keys=True)
        return f"fix:{hashlib.md5(content.encode()).hexdigest()[:8]}"

    def _ensure_arm(self, arm_id: str):
        """Ensure arm exists in MAB."""
        if self.mab is None:
            self.mab = MAB(
                arms=[arm_id],
                learning_policy=LearningPolicy.ThompsonSampling(),
                seed=42
            )
            # Thompson Sampling requires binary rewards (0 or 1)
            self.mab.fit([arm_id], [1])
        elif arm_id not in self.mab.arms:
            self.mab.add_arm(arm_id)

    def _load(self):
        """Load from disk."""
        if self.persist_path.exists():
            try:
                with open(self.persist_path, 'rb') as f:
                    self.mab = pickle.load(f)
                logger.debug(f"Loaded fix selector with {len(self.mab.arms) if self.mab else 0} arms")
            except Exception as e:
                logger.warning(f"Failed to load fix selector: {e}")

    def _save(self):
        """Save to disk."""
        try:
            self.persist_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.persist_path, 'wb') as f:
                pickle.dump(self.mab, f)
        except Exception as e:
            logger.warning(f"Failed to save fix selector: {e}")


class PrioritySelector:
    """Selects investigation priority using contextual bandits.

    Uses K-Nearest neighborhood policy for context-aware prioritization.
    This allows learning that certain targets are more promising in
    certain contexts (e.g., geometry-related tools when geometry is available).
    """

    def __init__(self, persist_path: Optional[Path] = None):
        self.persist_path = persist_path or (SELECTORS_DIR / "priority_selector.pkl")
        self.mab: Optional[MAB] = None
        self._load()

    def select(
        self,
        targets: list[str],
        context: SelectionContext,
    ) -> list[str]:
        """Reorder targets by expected value.

        Args:
            targets: List of investigation targets (tool names or gap IDs)
            context: Current context

        Returns:
            Targets reordered by expected value (highest first)
        """
        if not targets:
            return targets

        if not MAB_AVAILABLE or self.mab is None:
            return targets

        # Ensure all targets are arms
        for target in targets:
            self._ensure_arm(target)

        try:
            context_vector = context.to_vector()
            # For contextual MAB, predict with context
            expectations = self.mab.predict_expectations([context_vector])

            # Sort by expected value
            target_values = [(t, expectations.get(t, 0.5)) for t in targets]
            target_values.sort(key=lambda x: x[1], reverse=True)

            return [t for t, _ in target_values]

        except Exception as e:
            logger.warning(f"Priority selector failed: {e}")
            return targets

    def update(
        self,
        target: str,
        success: bool,
        context: SelectionContext,
        nuanced_reward: Optional[float] = None,
    ):
        """Update with outcome.

        Args:
            target: The target that was investigated
            success: Whether investigation was successful
            context: Context at time of selection
            nuanced_reward: Optional nuanced reward (0.0-1.0)
        """
        if not MAB_AVAILABLE:
            return

        self._ensure_arm(target)

        # Thompson Sampling requires binary rewards - binarize continuous rewards
        if nuanced_reward is not None:
            reward = 1 if nuanced_reward > 0.5 else 0
        else:
            reward = 1 if success else 0

        try:
            context_vector = context.to_vector()
            self.mab.partial_fit(
                [target],
                [reward],
                [context_vector]
            )
            self._save()
        except Exception as e:
            logger.warning(f"Priority selector update failed: {e}")

    def _ensure_arm(self, target: str):
        """Ensure target exists as arm in contextual MAB."""
        if self.mab is None:
            self.mab = MAB(
                arms=[target],
                learning_policy=LearningPolicy.ThompsonSampling(),
                neighborhood_policy=NeighborhoodPolicy.KNearest(k=5),
                seed=42
            )
        elif target not in self.mab.arms:
            self.mab.add_arm(target)

    def _load(self):
        """Load from disk."""
        if self.persist_path.exists():
            try:
                with open(self.persist_path, 'rb') as f:
                    self.mab = pickle.load(f)
                logger.debug(f"Loaded priority selector with {len(self.mab.arms) if self.mab else 0} arms")
            except Exception as e:
                logger.warning(f"Failed to load priority selector: {e}")

    def _save(self):
        """Save to disk."""
        try:
            self.persist_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.persist_path, 'wb') as f:
                pickle.dump(self.mab, f)
        except Exception as e:
            logger.warning(f"Failed to save priority selector: {e}")

    def get_stats(self) -> dict:
        """Get selector statistics."""
        if self.mab is None:
            return {"arms": 0}

        return {
            "arms": len(self.mab.arms),
            "neighborhood_policy": "KNearest(k=5)",
        }


class ActionSelector:
    """General-purpose action selector for investigation decisions.

    Uses Thompson Sampling with optional context for flexible action selection
    during investigation workflows.
    """

    def __init__(self, name: str = "default", persist_path: Optional[Path] = None):
        self.name = name
        self.persist_path = persist_path or (SELECTORS_DIR / f"action_selector_{name}.pkl")
        self.mab: Optional[MAB] = None
        self._load()

    def select(
        self,
        actions: list[dict],
        context: Optional[SelectionContext] = None,
    ) -> tuple[dict, int, float]:
        """Select an action from available options.

        Args:
            actions: List of action dicts with at least 'name' key
            context: Optional context for contextual selection

        Returns:
            Tuple of (selected_action, index, expected_value)
        """
        if not actions:
            return {}, 0, 0.5

        if not MAB_AVAILABLE:
            return actions[0], 0, 0.5

        # Use action names as arms
        arm_ids = [a.get('name', str(i)) for i, a in enumerate(actions)]

        for arm_id in arm_ids:
            self._ensure_arm(arm_id)

        if self.mab is None:
            return actions[0], 0, 0.5

        try:
            expectations = self.mab.predict_expectations()
            valid_arms = [a for a in arm_ids if a in self.mab.arms]
            if not valid_arms:
                return actions[0], 0, 0.5

            best_arm = max(valid_arms, key=lambda a: expectations.get(a, 0.5))
            idx = arm_ids.index(best_arm)
            expected_value = expectations.get(best_arm, 0.5)

            return actions[idx], idx, expected_value

        except Exception as e:
            logger.warning(f"Action selector prediction failed: {e}")
            return actions[0], 0, 0.5

    def update(
        self,
        action_name: str,
        success: bool,
        nuanced_reward: Optional[float] = None,
    ):
        """Update with outcome."""
        if not MAB_AVAILABLE or self.mab is None:
            return

        self._ensure_arm(action_name)
        # Thompson Sampling requires binary rewards - binarize continuous rewards
        if nuanced_reward is not None:
            reward = 1 if nuanced_reward > 0.5 else 0
        else:
            reward = 1 if success else 0

        try:
            self.mab.partial_fit([action_name], [reward])
            self._save()
        except Exception as e:
            logger.warning(f"Action selector update failed: {e}")

    def _ensure_arm(self, arm_id: str):
        """Ensure arm exists."""
        if self.mab is None:
            self.mab = MAB(
                arms=[arm_id],
                learning_policy=LearningPolicy.ThompsonSampling(),
                seed=42
            )
            # Thompson Sampling requires binary rewards (0 or 1)
            self.mab.fit([arm_id], [1])
        elif arm_id not in self.mab.arms:
            self.mab.add_arm(arm_id)

    def _load(self):
        """Load from disk."""
        if self.persist_path.exists():
            try:
                with open(self.persist_path, 'rb') as f:
                    self.mab = pickle.load(f)
            except Exception as e:
                logger.warning(f"Failed to load action selector {self.name}: {e}")

    def _save(self):
        """Save to disk."""
        try:
            self.persist_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.persist_path, 'wb') as f:
                pickle.dump(self.mab, f)
        except Exception as e:
            logger.warning(f"Failed to save action selector {self.name}: {e}")


# =============================================================================
# Command Learning Context Dataclasses
# =============================================================================

@dataclass
class IntentContext:
    """Context for command selection based on user intent.

    Used by CommandSelector to provide context-aware selection
    of commands for user intents.
    """
    intent_keywords: list[str] = field(default_factory=list)
    geometry_types_available: list[str] = field(default_factory=list)
    recent_commands_used: list[str] = field(default_factory=list)
    session_success_rate: float = 0.5

    # Command category mapping for one-hot encoding
    _COMMAND_CATEGORIES = {
        "create": 0, "edit": 1, "transform": 2, "analyze": 3,
        "curve": 4, "surface": 5, "solid": 6, "mesh": 7,
        "select": 8, "view": 9, "export": 10, "other": 11
    }

    def to_vector(self) -> list[float]:
        """Convert to feature vector for contextual MAB.

        Returns a 20-dimensional vector:
        - 12 dimensions: inferred command category one-hot
        - 8 dimensions: context features
        """
        # Infer category from keywords
        category = "other"
        category_keywords = {
            "create": ["create", "make", "add", "new", "draw"],
            "edit": ["edit", "modify", "change", "trim", "split", "fillet"],
            "transform": ["move", "rotate", "scale", "mirror", "copy"],
            "analyze": ["measure", "distance", "area", "volume", "length"],
            "curve": ["curve", "line", "arc", "circle", "polyline", "spline"],
            "surface": ["surface", "loft", "sweep", "revolve", "extrude"],
            "solid": ["box", "sphere", "cylinder", "cone", "boolean"],
            "mesh": ["mesh", "polygon", "vertex"],
            "select": ["select", "pick", "choose"],
            "view": ["view", "zoom", "pan", "rotate view"],
        }

        for cat, keywords in category_keywords.items():
            if any(kw in " ".join(self.intent_keywords).lower() for kw in keywords):
                category = cat
                break

        # Build one-hot vector
        vector = [0.0] * 12
        vector[self._COMMAND_CATEGORIES[category]] = 1.0

        # Add context features
        vector.extend([
            min(len(self.geometry_types_available) / 5.0, 1.0),
            1.0 if "curve" in self.geometry_types_available else 0.0,
            1.0 if "brep" in self.geometry_types_available else 0.0,
            1.0 if "mesh" in self.geometry_types_available else 0.0,
            min(len(self.recent_commands_used) / 10.0, 1.0),
            self.session_success_rate,
            min(len(self.intent_keywords) / 10.0, 1.0),
            1.0 if any(kw.isdigit() or ',' in kw for kw in self.intent_keywords) else 0.0,  # Has coordinates
        ])

        return vector


@dataclass
class ModeContext:
    """Context for mode selection within a command.

    Used by ModeSelector to choose the best mode of a command
    based on available parameters and geometry.
    """
    command: str = ""
    available_params: list[str] = field(default_factory=list)
    geometry_available: bool = False
    previous_mode_used: Optional[str] = None
    param_count: int = 0

    def to_vector(self) -> list[float]:
        """Convert to feature vector.

        Returns a 10-dimensional vector for mode selection context.
        """
        return [
            min(len(self.available_params) / 5.0, 1.0),
            1.0 if self.geometry_available else 0.0,
            1.0 if self.previous_mode_used else 0.0,
            min(self.param_count / 5.0, 1.0),
            1.0 if "center" in " ".join(self.available_params).lower() else 0.0,
            1.0 if "diameter" in " ".join(self.available_params).lower() else 0.0,
            1.0 if "point" in " ".join(self.available_params).lower() else 0.0,
            1.0 if "radius" in " ".join(self.available_params).lower() else 0.0,
            1.0 if any(p.replace('.', '').replace('-', '').replace(',', '').isdigit()
                      for p in self.available_params) else 0.0,
            0.5,  # Placeholder for future features
        ]


@dataclass
class LearningContext:
    """Context for input sequence selection during learning.

    Used by InputSequenceSelector to choose which input sequence
    to try when learning a command's dialogue.
    """
    command: str = ""
    mode: str = ""
    attempts_so_far: int = 0
    successes_so_far: int = 0
    unexplored_options: list[str] = field(default_factory=list)
    geometry_types_available: list[str] = field(default_factory=list)

    def to_vector(self) -> list[float]:
        """Convert to feature vector.

        Returns a 10-dimensional vector for learning context.
        """
        success_rate = self.successes_so_far / max(self.attempts_so_far, 1)
        return [
            min(self.attempts_so_far / 10.0, 1.0),
            success_rate,
            min(len(self.unexplored_options) / 5.0, 1.0),
            1.0 if self.unexplored_options else 0.0,  # Has unexplored options
            min(len(self.geometry_types_available) / 3.0, 1.0),
            1.0 if "curve" in self.geometry_types_available else 0.0,
            1.0 if "brep" in self.geometry_types_available else 0.0,
            1.0 if self.mode == "default" else 0.0,
            1.0 if self.attempts_so_far == 0 else 0.0,  # First attempt
            min(self.successes_so_far / 3.0, 1.0),
        ]


# =============================================================================
# Command Learning Selectors
# =============================================================================

class CommandSelector:
    """Selects which command to use for a user intent.

    Uses Thompson Sampling to learn which commands work best
    for different types of intents. Arms are command names.
    """

    def __init__(self, persist_path: Optional[Path] = None):
        self.persist_path = persist_path or (SELECTORS_DIR / "command_selector.pkl")
        self.mab: Optional[MAB] = None
        self._confidence_cache: dict[str, float] = {}
        self._load()

    def select(
        self,
        candidates: list[str],
        context: IntentContext,
    ) -> tuple[str, int]:
        """Select the best command for an intent.

        Args:
            candidates: List of command names that might work
            context: Intent context for selection

        Returns:
            Tuple of (selected_command, index in candidates)
        """
        if not candidates:
            return "", 0

        if not MAB_AVAILABLE:
            return candidates[0], 0

        # DON'T add candidates to MAB during selection - this causes cold-start bug
        # where new arms with default priors (0.5) beat trained arms with bad history.
        # Only select from commands that have been previously used and updated.
        # New commands will fall through to DSPy.

        if self.mab is None:
            # No MAB trained yet - set low confidence so DSPy takes over
            self._confidence_cache[candidates[0]] = 0.0
            return candidates[0], 0

        try:
            expectations = self.mab.predict_expectations()
            valid_arms = [c for c in candidates if c in self.mab.arms]
            if not valid_arms:
                # No trained arms match candidates - set low confidence so DSPy takes over
                self._confidence_cache[candidates[0]] = 0.0
                return candidates[0], 0

            best_cmd = max(valid_arms, key=lambda c: expectations.get(c, 0.5))
            self._confidence_cache[best_cmd] = expectations.get(best_cmd, 0.5)
            return best_cmd, candidates.index(best_cmd)

        except Exception as e:
            logger.warning(f"Command selector prediction failed: {e}")
            # Exception fallback - set low confidence so DSPy takes over
            self._confidence_cache[candidates[0]] = 0.0
            return candidates[0], 0

    def update(
        self,
        command: str,
        success: bool,
        context: IntentContext,
        nuanced_reward: Optional[float] = None,
    ):
        """Update with outcome.

        Args:
            command: The command that was used
            success: Whether it worked
            context: Context at selection time
            nuanced_reward: Optional nuanced reward (0.0-1.0)
        """
        if not MAB_AVAILABLE:
            return

        self._ensure_arm(command)

        if nuanced_reward is not None:
            reward = 1 if nuanced_reward > 0.5 else 0
        else:
            reward = 1 if success else 0

        try:
            if self.mab:
                self.mab.partial_fit([command], [reward])
                self._save()
        except Exception as e:
            logger.warning(f"Command selector update failed: {e}")

    def get_confidence(self, command: str) -> float:
        """Get cached confidence for a command."""
        return self._confidence_cache.get(command, 0.5)

    def _ensure_arm(self, command: str):
        """Ensure command exists as arm."""
        if self.mab is None:
            self.mab = MAB(
                arms=[command],
                learning_policy=LearningPolicy.ThompsonSampling(),
                seed=42
            )
            self.mab.fit([command], [1])
        elif command not in self.mab.arms:
            self.mab.add_arm(command)

    def _load(self):
        """Load from disk."""
        if self.persist_path.exists():
            try:
                with open(self.persist_path, 'rb') as f:
                    data = pickle.load(f)
                    self.mab = data.get('mab')
                    self._confidence_cache = data.get('confidence', {})
                logger.debug(f"Loaded command selector with {len(self.mab.arms) if self.mab else 0} arms")
            except Exception as e:
                logger.warning(f"Failed to load command selector: {e}")

    def _save(self):
        """Save to disk."""
        try:
            self.persist_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.persist_path, 'wb') as f:
                pickle.dump({
                    'mab': self.mab,
                    'confidence': self._confidence_cache
                }, f)
        except Exception as e:
            logger.warning(f"Failed to save command selector: {e}")

    def get_stats(self) -> dict:
        """Get selector statistics."""
        if self.mab is None:
            return {"arms": 0}

        return {
            "arms": len(self.mab.arms),
            "learning_policy": "ThompsonSampling",
        }


class ModeSelector:
    """Selects which mode of a command to use.

    Each command has multiple modes (e.g., _-Sphere has default, diameter, 3point).
    This selector learns which modes work best in different contexts.
    Arms are "{command}:{mode}" strings.
    """

    def __init__(self, persist_path: Optional[Path] = None):
        self.persist_path = persist_path or (SELECTORS_DIR / "mode_selector.pkl")
        self.mab: Optional[MAB] = None
        self._load()

    def select(
        self,
        command: str,
        modes: list[str],
        context: ModeContext,
    ) -> tuple[str, int]:
        """Select the best mode for a command.

        Args:
            command: The command name
            modes: List of available modes
            context: Mode selection context

        Returns:
            Tuple of (selected_mode, index in modes)
        """
        if not modes:
            return "default", 0

        if not MAB_AVAILABLE:
            return modes[0], 0

        # Create arm IDs for this command's modes
        arm_ids = [f"{command}:{mode}" for mode in modes]

        # DON'T add arms on-the-fly during selection - same fix as CommandSelector
        # This prevents cold-start bug where new arms beat trained ones.

        if self.mab is None:
            return modes[0], 0

        try:
            expectations = self.mab.predict_expectations()
            valid_arms = [a for a in arm_ids if a in self.mab.arms]
            if not valid_arms:
                # No trained modes for this command - return first mode
                return modes[0], 0

            best_arm = max(valid_arms, key=lambda a: expectations.get(a, 0.5))
            idx = arm_ids.index(best_arm)
            return modes[idx], idx

        except Exception as e:
            logger.warning(f"Mode selector prediction failed: {e}")
            return modes[0], 0

    def update(
        self,
        command: str,
        mode: str,
        success: bool,
        context: Optional[ModeContext] = None,
        nuanced_reward: Optional[float] = None,
    ):
        """Update with outcome.

        Args:
            command: The command that was used
            mode: The mode that was used
            success: Whether it worked
            context: Context at selection time
            nuanced_reward: Optional nuanced reward (0.0-1.0)
        """
        if not MAB_AVAILABLE:
            return

        arm_id = f"{command}:{mode}"
        self._ensure_arm(arm_id)

        if nuanced_reward is not None:
            reward = 1 if nuanced_reward > 0.5 else 0
        else:
            reward = 1 if success else 0

        try:
            if self.mab:
                self.mab.partial_fit([arm_id], [reward])
                self._save()
        except Exception as e:
            logger.warning(f"Mode selector update failed: {e}")

    def _ensure_arm(self, arm_id: str):
        """Ensure arm exists."""
        if self.mab is None:
            self.mab = MAB(
                arms=[arm_id],
                learning_policy=LearningPolicy.ThompsonSampling(),
                seed=42
            )
            self.mab.fit([arm_id], [1])
        elif arm_id not in self.mab.arms:
            self.mab.add_arm(arm_id)

    def _load(self):
        """Load from disk."""
        if self.persist_path.exists():
            try:
                with open(self.persist_path, 'rb') as f:
                    self.mab = pickle.load(f)
                logger.debug(f"Loaded mode selector with {len(self.mab.arms) if self.mab else 0} arms")
            except Exception as e:
                logger.warning(f"Failed to load mode selector: {e}")

    def _save(self):
        """Save to disk."""
        try:
            self.persist_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.persist_path, 'wb') as f:
                pickle.dump(self.mab, f)
        except Exception as e:
            logger.warning(f"Failed to save mode selector: {e}")

    def get_stats(self) -> dict:
        """Get selector statistics."""
        if self.mab is None:
            return {"arms": 0}

        return {
            "arms": len(self.mab.arms),
            "learning_policy": "ThompsonSampling",
        }


class InputSequenceSelector:
    """Selects which input sequence to try during command learning.

    When learning a command's dialogue, DSPy generates multiple input
    sequences to try. This selector learns which sequences are more
    likely to succeed and discover new modes/options.

    Arms are hashes of input sequences.
    """

    def __init__(self, persist_path: Optional[Path] = None):
        self.persist_path = persist_path or (SELECTORS_DIR / "input_sequence_selector.pkl")
        self.mab: Optional[MAB] = None
        self._sequence_cache: dict[str, list[str]] = {}  # arm_id -> sequence
        self._load()

    def select(
        self,
        sequences: list[list[str]],
        context: LearningContext,
    ) -> tuple[list[str], int]:
        """Select the best input sequence to try.

        Args:
            sequences: List of input sequences to choose from
            context: Learning context

        Returns:
            Tuple of (selected_sequence, index in sequences)
        """
        if not sequences:
            return [], 0

        if not MAB_AVAILABLE:
            return sequences[0], 0

        # Create arm IDs from sequences
        arm_ids = [self._sequence_to_arm_id(seq, context.command) for seq in sequences]

        # Cache sequences for later retrieval
        for arm_id, seq in zip(arm_ids, sequences):
            self._sequence_cache[arm_id] = seq

        for arm_id in arm_ids:
            self._ensure_arm(arm_id)

        if self.mab is None:
            return sequences[0], 0

        try:
            expectations = self.mab.predict_expectations()
            valid_arms = [a for a in arm_ids if a in self.mab.arms]
            if not valid_arms:
                return sequences[0], 0

            best_arm = max(valid_arms, key=lambda a: expectations.get(a, 0.5))
            idx = arm_ids.index(best_arm)
            return sequences[idx], idx

        except Exception as e:
            logger.warning(f"Input sequence selector prediction failed: {e}")
            return sequences[0], 0

    def update(
        self,
        sequence: list[str],
        success: bool,
        knowledge_gained: bool,
        context: LearningContext,
    ):
        """Update with outcome.

        Args:
            sequence: The input sequence that was tried
            success: Whether execution succeeded
            knowledge_gained: Whether we learned something new
            context: Learning context
        """
        if not MAB_AVAILABLE:
            return

        arm_id = self._sequence_to_arm_id(sequence, context.command)
        self._ensure_arm(arm_id)

        # Reward is higher if we gained knowledge
        if knowledge_gained:
            reward = 1
        elif success:
            reward = 1  # Still good, just not novel
        else:
            reward = 0

        try:
            if self.mab:
                self.mab.partial_fit([arm_id], [reward])
                self._save()
        except Exception as e:
            logger.warning(f"Input sequence selector update failed: {e}")

    def _sequence_to_arm_id(self, sequence: list[str], command: str) -> str:
        """Convert sequence to unique arm ID."""
        content = json.dumps({"cmd": command, "seq": sequence}, sort_keys=True)
        return f"seq:{hashlib.md5(content.encode()).hexdigest()[:12]}"

    def _ensure_arm(self, arm_id: str):
        """Ensure arm exists."""
        if self.mab is None:
            self.mab = MAB(
                arms=[arm_id],
                learning_policy=LearningPolicy.ThompsonSampling(),
                seed=42
            )
            self.mab.fit([arm_id], [1])
        elif arm_id not in self.mab.arms:
            self.mab.add_arm(arm_id)

    def _load(self):
        """Load from disk."""
        if self.persist_path.exists():
            try:
                with open(self.persist_path, 'rb') as f:
                    data = pickle.load(f)
                    self.mab = data.get('mab')
                    self._sequence_cache = data.get('cache', {})
                logger.debug(f"Loaded input sequence selector with {len(self.mab.arms) if self.mab else 0} arms")
            except Exception as e:
                logger.warning(f"Failed to load input sequence selector: {e}")

    def _save(self):
        """Save to disk."""
        try:
            self.persist_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.persist_path, 'wb') as f:
                pickle.dump({
                    'mab': self.mab,
                    'cache': self._sequence_cache
                }, f)
        except Exception as e:
            logger.warning(f"Failed to save input sequence selector: {e}")

    def get_stats(self) -> dict:
        """Get selector statistics."""
        if self.mab is None:
            return {"arms": 0, "cached_sequences": 0}

        return {
            "arms": len(self.mab.arms),
            "cached_sequences": len(self._sequence_cache),
            "learning_policy": "ThompsonSampling",
        }


# =============================================================================
# Knowledge Tier Selection
# =============================================================================

@dataclass
class TierContext:
    """Context for selecting knowledge tier depth.

    Used by TierSelector to choose between quick/context/errors tiers
    based on the query situation.
    """
    command: str = ""
    intent: str = ""
    is_debugging: bool = False  # Are we recovering from an error?
    has_prior_failures: int = 0  # Number of recent failures
    session_command_count: int = 0  # Commands executed so far
    command_familiarity: float = 0.5  # 0-1, how well-known is this command

    def to_vector(self) -> list[float]:
        """Convert to feature vector for contextual MAB.

        Returns a 10-dimensional vector for tier selection.
        """
        return [
            1.0 if self.is_debugging else 0.0,
            min(self.has_prior_failures / 3.0, 1.0),
            min(self.session_command_count / 20.0, 1.0),
            self.command_familiarity,
            1.0 if self.session_command_count == 0 else 0.0,  # First command
            1.0 if self.has_prior_failures > 0 else 0.0,
            1.0 if len(self.intent.split()) > 5 else 0.0,  # Complex intent
            1.0 if "error" in self.intent.lower() or "fail" in self.intent.lower() else 0.0,
            1.0 if "help" in self.intent.lower() or "how" in self.intent.lower() else 0.0,
            0.5,  # Placeholder
        ]


class TierSelector:
    """Selects which knowledge tier to use for command queries.

    Learns which tier (quick, context, errors) leads to successful
    command execution in different contexts.

    Arms are tier names: "quick", "context", "errors"
    """

    TIERS = ["quick", "context", "errors"]

    def __init__(self, persist_path: Optional[Path] = None):
        self.persist_path = persist_path or (SELECTORS_DIR / "tier_selector.pkl")
        self.mab: Optional[MAB] = None
        self._tier_stats: dict[str, dict] = {tier: {"uses": 0, "successes": 0} for tier in self.TIERS}
        self._load()

    def select(
        self,
        context: TierContext,
        available_tiers: Optional[list[str]] = None,
    ) -> str:
        """Select the best knowledge tier.

        Args:
            context: Tier selection context
            available_tiers: Optional subset of tiers to choose from

        Returns:
            Selected tier name ("quick", "context", or "errors")
        """
        tiers = available_tiers or self.TIERS

        if not MAB_AVAILABLE:
            # Fallback logic: use context by default, errors if debugging
            if context.is_debugging or context.has_prior_failures > 0:
                return "errors"
            return "context"

        # Ensure all tiers are arms
        for tier in tiers:
            self._ensure_arm(tier)

        if self.mab is None:
            return "context"

        try:
            expectations = self.mab.predict_expectations()
            valid_tiers = [t for t in tiers if t in self.mab.arms]
            if not valid_tiers:
                return "context"

            # Apply context-based adjustments
            adjusted = {}
            for tier in valid_tiers:
                base = expectations.get(tier, 0.5)
                # Boost errors tier if debugging
                if tier == "errors" and context.is_debugging:
                    base += 0.2
                # Boost quick tier for familiar commands
                if tier == "quick" and context.command_familiarity > 0.8:
                    base += 0.1
                # Boost context tier for complex intents
                if tier == "context" and len(context.intent.split()) > 5:
                    base += 0.1
                adjusted[tier] = min(base, 1.0)

            best_tier = max(adjusted, key=lambda t: adjusted[t])
            return best_tier

        except Exception as e:
            logger.warning(f"Tier selector prediction failed: {e}")
            return "context"

    def update(
        self,
        tier: str,
        success: bool,
        context: TierContext,
    ):
        """Update with outcome.

        Args:
            tier: The tier that was used
            success: Whether the subsequent command execution succeeded
            context: Context at selection time
        """
        if tier not in self.TIERS:
            return

        # Update stats
        self._tier_stats[tier]["uses"] += 1
        if success:
            self._tier_stats[tier]["successes"] += 1

        if not MAB_AVAILABLE:
            return

        self._ensure_arm(tier)
        reward = 1 if success else 0

        try:
            if self.mab:
                self.mab.partial_fit([tier], [reward])
                self._save()
        except Exception as e:
            logger.warning(f"Tier selector update failed: {e}")

    def _ensure_arm(self, tier: str):
        """Ensure tier exists as arm."""
        if self.mab is None:
            self.mab = MAB(
                arms=self.TIERS,
                learning_policy=LearningPolicy.ThompsonSampling(),
                seed=42
            )
            # Initialize with slightly optimistic priors
            self.mab.fit(self.TIERS, [1, 1, 1])
        elif tier not in self.mab.arms:
            self.mab.add_arm(tier)

    def _load(self):
        """Load from disk."""
        if self.persist_path.exists():
            try:
                with open(self.persist_path, 'rb') as f:
                    data = pickle.load(f)
                    self.mab = data.get('mab')
                    self._tier_stats = data.get('stats', self._tier_stats)
                logger.debug(f"Loaded tier selector")
            except Exception as e:
                logger.warning(f"Failed to load tier selector: {e}")

    def _save(self):
        """Save to disk."""
        try:
            self.persist_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.persist_path, 'wb') as f:
                pickle.dump({
                    'mab': self.mab,
                    'stats': self._tier_stats
                }, f)
        except Exception as e:
            logger.warning(f"Failed to save tier selector: {e}")

    def get_stats(self) -> dict:
        """Get selector statistics."""
        stats = {
            "tiers": self._tier_stats,
            "learning_policy": "ThompsonSampling",
        }

        if self.mab:
            try:
                expectations = self.mab.predict_expectations()
                stats["expectations"] = {t: round(expectations.get(t, 0.5), 3) for t in self.TIERS}
            except Exception:
                pass

        return stats


# =============================================================================
# Factory Functions
# =============================================================================

def create_all_selectors(base_path: Optional[Path] = None) -> dict[str, Any]:
    """Create instances of all selectors.

    Args:
        base_path: Optional base path for persistence files

    Returns:
        Dictionary of selector name -> selector instance
    """
    base = base_path or SELECTORS_DIR

    return {
        # MCP tool investigation selectors
        "hypothesis": HypothesisSelector(base / "hypothesis_selector.pkl"),
        "fix": FixSelector(base / "fix_selector.pkl"),
        "priority": PrioritySelector(base / "priority_selector.pkl"),
        "action": ActionSelector("default", base / "action_selector_default.pkl"),
        # Command learning selectors
        "command": CommandSelector(base / "command_selector.pkl"),
        "mode": ModeSelector(base / "mode_selector.pkl"),
        "input_sequence": InputSequenceSelector(base / "input_sequence_selector.pkl"),
        # Knowledge tier selector
        "tier": TierSelector(base / "tier_selector.pkl"),
    }


def clear_all_selectors(base_path: Optional[Path] = None):
    """Clear all persisted selector state (for testing/reset).

    Args:
        base_path: Optional base path for persistence files
    """
    base = base_path or SELECTORS_DIR

    if base.exists():
        for pkl_file in base.glob("*.pkl"):
            try:
                pkl_file.unlink()
                logger.info(f"Cleared selector state: {pkl_file.name}")
            except Exception as e:
                logger.warning(f"Failed to clear {pkl_file}: {e}")
