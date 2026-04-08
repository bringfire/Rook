"""
Reflection - Analyze sessions for learnable patterns.

Provides:
- StruggleSequence: A failure→success pattern in session history
- detect_struggles: Find struggle sequences in entries
- ReflectionResult: Analysis of a struggle sequence
- DraftPattern: A pattern draft awaiting human approval

Part of Phase 5 of the meta-learning system.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Optional
from uuid import uuid4

from .gh_session_history import SessionEntry
from .pattern_memory import PatternNote

logger = logging.getLogger("rook.reflection")


# =============================================================================
# Data Structures
# =============================================================================

@dataclass
class StruggleSequence:
    """A sequence of failures followed by success.

    Represents a learning opportunity where Claude struggled with something
    and eventually succeeded. The contrast between failure and success
    often reveals actionable insights.
    """

    failures: list[SessionEntry]
    """The failed attempts (in chronological order)."""

    success: SessionEntry
    """The successful attempt that resolved the struggle."""

    common_action: str
    """The action/tool that was being attempted (e.g., 'gh_edit')."""

    common_intent: Optional[str] = None
    """The intent if this was an execute_intent sequence."""

    def __post_init__(self):
        if not self.failures:
            raise ValueError("StruggleSequence requires at least one failure")

    @property
    def entry_ids(self) -> list[int]:
        """All entry IDs in this sequence."""
        return [e.entry_id for e in self.failures] + [self.success.entry_id]

    @property
    def failure_count(self) -> int:
        """Number of failures before success."""
        return len(self.failures)

    @property
    def duration_entries(self) -> int:
        """Total entries in this struggle (failures + success)."""
        return len(self.failures) + 1

    def get_error_messages(self) -> list[str]:
        """Extract unique error messages from failures."""
        errors = []
        for entry in self.failures:
            if entry.errors:
                for err in entry.errors:
                    if err not in errors:
                        errors.append(err)
        return errors

    def get_failure_params(self) -> list[dict]:
        """Get params from failed attempts."""
        return [e.params for e in self.failures]

    def get_success_params(self) -> dict:
        """Get params from successful attempt."""
        return self.success.params

    def describe(self) -> str:
        """Human-readable description of the struggle."""
        return (
            f"{self.failure_count} failed attempts at '{self.common_action}' "
            f"followed by success (entries {self.entry_ids[0]}-{self.entry_ids[-1]})"
        )


@dataclass
class ReflectionResult:
    """Analysis results from reflecting on a struggle sequence.

    Contains the answers to the 5 reflection questions and
    the derived pattern components.
    """

    # Was this hard-won?
    is_hard_won: bool
    """True if this required significant effort (multiple failures)."""

    hard_won_reason: str
    """Explanation of why this was (or wasn't) hard-won."""

    # What was the breakthrough?
    breakthrough: str
    """What changed between last failure and success."""

    breakthrough_insight: str
    """The underlying insight or principle discovered."""

    # Is this generalizable?
    is_generalizable: bool
    """True if this pattern would help with similar problems."""

    generalization_scope: str
    """Description of when this pattern applies."""

    # Recognition triggers
    trigger_intents: list[str]
    """Intents that should trigger this pattern."""

    trigger_symptoms: list[str]
    """Symptoms that indicate this pattern applies."""

    # Solution
    solution_brief: str
    """One-line summary of the solution."""

    solution_principle: str
    """Underlying principle (the 'why')."""

    # Constraints
    preconditions: list[str]
    """What must be true before applying this pattern."""

    postconditions: list[str]
    """What should be true after successful application."""

    # Anti-patterns
    anti_patterns: list[dict[str, str]]
    """What NOT to do: [{mistake, symptom, why_wrong}, ...]"""

    # Recommendation
    recommendation: Literal["approve", "review", "skip"]
    """Suggested action for human reviewer."""

    recommendation_reason: str
    """Why this recommendation was made."""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for JSON serialization."""
        return {
            "is_hard_won": self.is_hard_won,
            "hard_won_reason": self.hard_won_reason,
            "breakthrough": self.breakthrough,
            "breakthrough_insight": self.breakthrough_insight,
            "is_generalizable": self.is_generalizable,
            "generalization_scope": self.generalization_scope,
            "trigger_intents": self.trigger_intents,
            "trigger_symptoms": self.trigger_symptoms,
            "solution_brief": self.solution_brief,
            "solution_principle": self.solution_principle,
            "preconditions": self.preconditions,
            "postconditions": self.postconditions,
            "anti_patterns": self.anti_patterns,
            "recommendation": self.recommendation,
            "recommendation_reason": self.recommendation_reason,
        }


@dataclass
class DraftPattern:
    """A pattern draft awaiting human approval.

    Contains the pattern data plus metadata about its source
    and the analysis that produced it.
    """

    draft_id: str
    """Unique ID for this draft."""

    session_id: str
    """Session this pattern was extracted from."""

    from_entries: list[int]
    """Entry IDs that contributed to this pattern."""

    pattern: PatternNote
    """The draft pattern (not yet saved)."""

    reflection: ReflectionResult
    """The reflection analysis that produced this."""

    created: str
    """ISO timestamp when draft was created."""

    @classmethod
    def create(
        cls,
        session_id: str,
        struggle: StruggleSequence,
        reflection: ReflectionResult,
        pattern: PatternNote,
    ) -> "DraftPattern":
        """Create a new draft pattern."""
        return cls(
            draft_id=f"draft_{uuid4().hex[:8]}",
            session_id=session_id,
            from_entries=struggle.entry_ids,
            pattern=pattern,
            reflection=reflection,
            created=datetime.utcnow().isoformat() + "Z",
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for MCP response."""
        return {
            "draft_id": self.draft_id,
            "session_id": self.session_id,
            "from_entries": self.from_entries,
            "pattern": self.pattern.to_dict(),
            "confidence_assessment": self.reflection.hard_won_reason,
            "recommendation": self.reflection.recommendation,
            "recommendation_reason": self.reflection.recommendation_reason,
            "created": self.created,
        }


# =============================================================================
# Struggle Detection
# =============================================================================

def detect_struggles(
    entries: list[SessionEntry],
    min_failures: int = 2,
    group_by_intent: bool = True,
) -> list[StruggleSequence]:
    """Detect struggle→success sequences in session entries.

    A struggle is defined as:
    - 2+ consecutive failures on similar action/intent
    - Followed by a success on the same action/intent

    Args:
        entries: Session entries in chronological order
        min_failures: Minimum failures before success (default: 2)
        group_by_intent: If True, group by intent for execute_intent actions

    Returns:
        List of detected struggle sequences
    """
    if not entries:
        return []

    struggles = []
    current_failures: list[SessionEntry] = []
    current_key: Optional[str] = None

    def get_grouping_key(entry: SessionEntry) -> str:
        """Get key to group similar entries."""
        if group_by_intent and entry.action == "gh_execute_intent":
            intent = entry.params.get("intent", "")
            if intent:
                return f"intent:{intent}"
        return f"action:{entry.action}"

    def flush_if_success(entry: SessionEntry) -> None:
        """Check if current entry completes a struggle sequence."""
        nonlocal current_failures, current_key

        if not current_failures:
            return

        key = get_grouping_key(entry)

        # If success matches the current failure pattern
        if key == current_key and entry.outcome == "success":
            if len(current_failures) >= min_failures:
                # Extract common action and intent
                common_action = current_failures[0].action
                common_intent = None
                if common_action == "gh_execute_intent":
                    common_intent = current_failures[0].params.get("intent")

                struggles.append(StruggleSequence(
                    failures=current_failures.copy(),
                    success=entry,
                    common_action=common_action,
                    common_intent=common_intent,
                ))
            current_failures = []
            current_key = None

    for entry in entries:
        key = get_grouping_key(entry)

        if entry.outcome in ("failure", "partial"):
            # Accumulate failures
            if current_key is None or current_key == key:
                current_failures.append(entry)
                current_key = key
            else:
                # Different key - reset
                current_failures = [entry]
                current_key = key

        elif entry.outcome == "success":
            flush_if_success(entry)
            # Reset after success
            current_failures = []
            current_key = None

    return struggles


def filter_routine_successes(entries: list[SessionEntry]) -> list[SessionEntry]:
    """Filter out entries that are routine successes (no learning value).

    Routine successes are:
    - Single successful attempts (no struggle)
    - Standard operations without complications

    Args:
        entries: All session entries

    Returns:
        Entries that may contain learning opportunities
    """
    # For now, just return all entries - the detect_struggles function
    # will filter for actual struggle sequences
    return entries


# =============================================================================
# Pattern Building
# =============================================================================

def build_pattern_from_reflection(
    session_id: str,
    struggle: StruggleSequence,
    reflection: ReflectionResult,
) -> PatternNote:
    """Build a PatternNote from reflection analysis.

    Args:
        session_id: Source session ID
        struggle: The struggle sequence analyzed
        reflection: Reflection analysis results

    Returns:
        PatternNote draft (not yet saved)
    """
    # Generate a pattern ID from the solution brief
    words = reflection.solution_brief.lower().split()[:4]
    safe_words = [w for w in words if w.isalnum()]
    base_id = "_".join(safe_words) if safe_words else "pattern"
    pattern_id = f"{base_id}_{uuid4().hex[:6]}"

    # Build citations
    citations = [
        {
            "session_id": session_id,
            "entry_range": [struggle.entry_ids[0], struggle.entry_ids[-1]],
            "outcome": "success",
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
    ]

    # Build anti-patterns from reflection
    anti_patterns = reflection.anti_patterns or []

    return PatternNote(
        pattern_id=pattern_id,
        name=reflection.solution_brief[:50],  # Truncate for name
        solution_brief=reflection.solution_brief,
        solution_principle=reflection.solution_principle,
        trigger_intents=reflection.trigger_intents,
        trigger_symptoms=reflection.trigger_symptoms,
        preconditions=reflection.preconditions,
        postconditions=reflection.postconditions,
        anti_patterns=anti_patterns,
        citations=citations,
        tags=[struggle.common_action],
        # Initial confidence
        times_used=1,
        times_succeeded=1,
        last_verified=datetime.utcnow().isoformat() + "Z",
    )


def create_draft_pattern(
    session_id: str,
    struggle: StruggleSequence,
    reflection: ReflectionResult,
) -> DraftPattern:
    """Create a complete draft pattern for human review.

    Args:
        session_id: Source session ID
        struggle: The struggle sequence
        reflection: Reflection analysis

    Returns:
        DraftPattern ready for human approval
    """
    pattern = build_pattern_from_reflection(session_id, struggle, reflection)
    return DraftPattern.create(
        session_id=session_id,
        struggle=struggle,
        reflection=reflection,
        pattern=pattern,
    )


# =============================================================================
# DSPy-Powered Analysis
# =============================================================================

def analyze_struggle_with_dspy(struggle: StruggleSequence) -> Optional[ReflectionResult]:
    """Analyze a struggle sequence using DSPy/LLM.

    Uses the ReflectionAnalyzer DSPy module to answer the 5 reflection
    questions and generate pattern components.

    Args:
        struggle: The struggle sequence to analyze

    Returns:
        ReflectionResult if analysis succeeded, None if DSPy unavailable
    """
    try:
        from .dspy_modules import ReflectionAnalyzer
        from .dspy_config import is_configured, configure_dspy

        if not is_configured():
            configure_dspy()

        analyzer = ReflectionAnalyzer()

        # Build summaries for DSPy
        failures_summary = (
            f"{len(struggle.failures)} failed attempts at '{struggle.common_action}'. "
            f"Errors: {', '.join(struggle.get_error_messages()[:3])}"
        )
        success_summary = (
            f"Succeeded with params: {struggle.get_success_params()}"
        )

        # Call DSPy module
        result = analyzer.forward(
            failures_summary=failures_summary,
            success_summary=success_summary,
            action_type=struggle.common_action,
            intent=struggle.common_intent or "",
            error_messages=struggle.get_error_messages(),
            failure_params=struggle.get_failure_params(),
            success_params=struggle.get_success_params(),
        )

        # Convert DSPy output to ReflectionResult
        return ReflectionResult(
            is_hard_won=result.is_hard_won,
            hard_won_reason=result.hard_won_reason,
            breakthrough=result.breakthrough,
            breakthrough_insight=result.breakthrough_insight,
            is_generalizable=result.is_generalizable,
            generalization_scope=result.generalization_scope,
            trigger_intents=result.trigger_intents,
            trigger_symptoms=result.trigger_symptoms,
            solution_brief=result.solution_brief,
            solution_principle=result.solution_principle,
            preconditions=result.preconditions,
            postconditions=result.postconditions,
            anti_patterns=result.anti_patterns,
            recommendation=result.recommendation,
            recommendation_reason=result.recommendation_reason,
        )

    except Exception as e:
        logger.warning(f"DSPy reflection analysis failed: {e}")
        return None


def analyze_struggle_heuristic(struggle: StruggleSequence) -> ReflectionResult:
    """Analyze a struggle using heuristics (fallback when DSPy unavailable).

    Provides basic analysis without LLM reasoning. Less insightful but
    always available.

    Args:
        struggle: The struggle sequence to analyze

    Returns:
        ReflectionResult with heuristic-based analysis
    """
    errors = struggle.get_error_messages()
    failure_count = struggle.failure_count

    # Basic heuristics
    is_hard_won = failure_count >= 2
    is_generalizable = failure_count >= 3  # More failures = more likely reusable

    # Build simple anti-patterns from errors
    anti_patterns = []
    for i, error in enumerate(errors[:3]):  # Max 3
        anti_patterns.append({
            "mistake": f"Attempt {i+1}",
            "symptom": error[:100],  # Truncate
            "why_wrong": "Resulted in error",
        })

    return ReflectionResult(
        is_hard_won=is_hard_won,
        hard_won_reason=f"{failure_count} failures before success",
        breakthrough="Changed parameters between last failure and success",
        breakthrough_insight="Parameters need adjustment for this operation",
        is_generalizable=is_generalizable,
        generalization_scope=f"Operations involving {struggle.common_action}",
        trigger_intents=[struggle.common_intent] if struggle.common_intent else [],
        trigger_symptoms=errors[:2],  # First 2 errors as symptoms
        solution_brief=f"Successful {struggle.common_action} after {failure_count} attempts",
        solution_principle="Iteration and parameter adjustment",
        preconditions=[],
        postconditions=[],
        anti_patterns=anti_patterns,
        recommendation="review",  # Heuristics always need human review
        recommendation_reason="Heuristic analysis - human review recommended",
    )


def analyze_struggle(
    struggle: StruggleSequence,
    use_dspy: bool = True,
) -> ReflectionResult:
    """Analyze a struggle sequence.

    Tries DSPy first for better insights, falls back to heuristics.

    Args:
        struggle: The struggle sequence to analyze
        use_dspy: Whether to try DSPy analysis (default: True)

    Returns:
        ReflectionResult from DSPy or heuristics
    """
    if use_dspy:
        result = analyze_struggle_with_dspy(struggle)
        if result is not None:
            return result

    return analyze_struggle_heuristic(struggle)
