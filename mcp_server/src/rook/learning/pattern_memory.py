"""
Pattern Memory - Data classes for A-MEM style pattern storage.

Provides:
- PatternNote: Core entity representing a learned pattern
- PatternIndex: Fast lookup index for pattern retrieval

Part of Phase 2 of the meta-learning system. Patterns store reusable
solutions indexed by symptoms and intents, with A-MEM style evolution.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional
import uuid

# Type aliases - shared with pattern_verifier.py
# "unchecked" is only used in PatternNote (runtime status before verification)
VerificationStatus = Literal["verified", "stale", "unverifiable", "no_citations", "unchecked"]

# Staleness thresholds (shared with pattern_verifier.StalenessPolicy)
STALENESS_HIGH_CONFIDENCE_DAYS = 60  # >80% success rate
STALENESS_DEFAULT_DAYS = 30  # 50-80% success rate
STALENESS_LOW_CONFIDENCE_DAYS = 14  # <50% success rate


@dataclass
class PatternNote:
    """A pattern representing learned knowledge about GH workflows.

    Inspired by A-MEM MemoryNote but adapted for GH domain:
    - content → solution (what to do)
    - context → scope (when it applies)
    - keywords → triggers.intents + triggers.symptoms
    - links → related pattern IDs
    - evolution_history → how this pattern evolved over time

    Patterns are stored as individual JSON files in knowledge/gh/patterns/
    and indexed in pattern_index.json for fast retrieval.
    """

    # =========================================================================
    # Core Identity
    # =========================================================================

    pattern_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    """Unique identifier for the pattern (8-char UUID prefix)."""

    name: str = ""
    """Human-readable name for the pattern."""

    version: str = "1.0"
    """Pattern version (for tracking updates)."""

    created: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    """ISO timestamp when pattern was created (UTC)."""

    # =========================================================================
    # Solution Content
    # =========================================================================

    solution_brief: str = ""
    """One-sentence summary (~30 tokens). Quick reference for matching."""

    solution_principle: str = ""
    """Deeper explanation of WHY this works. The underlying principle."""

    components_needed: list[str] = field(default_factory=list)
    """GH components involved in this pattern."""

    # =========================================================================
    # Triggers (How to Find This Pattern)
    # =========================================================================

    trigger_intents: list[str] = field(default_factory=list)
    """Phrases a user might say when they need this pattern.
    Examples: ["wedge shape from circles", "pie slice", "spiral tread"]
    """

    trigger_symptoms: list[str] = field(default_factory=list)
    """Observable symptoms that indicate this pattern applies.
    Examples: ["microscopic slider changes", "same domain different angles"]
    """

    # =========================================================================
    # Scope (When It Applies)
    # =========================================================================

    scope_global: bool = True
    """If True, applies across all projects. If False, check project_types."""

    scope_project_types: list[str] = field(default_factory=list)
    """Project types where this pattern applies (e.g., ["architectural"])."""

    scope_workflow_types: list[str] = field(default_factory=list)
    """Workflow types (e.g., ["parametric_modeling", "surface_creation"])."""

    # =========================================================================
    # Anti-Patterns (What NOT to Do)
    # =========================================================================

    anti_patterns: list[dict] = field(default_factory=list)
    """Common mistakes to avoid. Each dict has:
    - mistake: What people do wrong
    - symptom: How you know you made this mistake
    - why_wrong: Explanation of why it fails
    """

    # =========================================================================
    # Constraints
    # =========================================================================

    preconditions: list[str] = field(default_factory=list)
    """Conditions that must be true before applying this pattern."""

    postconditions: list[str] = field(default_factory=list)
    """Conditions that should be true after successful application."""

    # =========================================================================
    # Verification
    # =========================================================================

    verification_test: str = ""
    """How to verify the pattern works (test procedure)."""

    verification_expected: str = ""
    """What success looks like."""

    # =========================================================================
    # Citations (Links to Session History - Phase 1 Integration)
    # =========================================================================

    citations: list[dict] = field(default_factory=list)
    """Links to session history entries. Each dict has:
    - session_id: str - Session where this was discovered/used
    - entry_range: [int, int] - Entry IDs in session (optional)
    - outcome: str - "success" | "failure" | "partial"
    - timestamp: str - ISO timestamp
    - notes: str - Optional observations (optional)
    """

    # =========================================================================
    # Confidence Tracking
    # =========================================================================

    times_used: int = 0
    """How many times this pattern was applied."""

    times_succeeded: int = 0
    """How many times application was successful."""

    last_used: Optional[str] = None
    """ISO timestamp of last use."""

    last_verified: Optional[str] = None
    """ISO timestamp of last successful verification."""

    # =========================================================================
    # A-MEM Style Linking
    # =========================================================================

    links: list[str] = field(default_factory=list)
    """Related pattern IDs (bidirectional connections)."""

    tags: list[str] = field(default_factory=list)
    """Classification tags for retrieval and grouping."""

    # =========================================================================
    # Evolution Tracking
    # =========================================================================

    created_from: str = "manual"
    """How this pattern was created: "manual", "reflection", "evolution"."""

    last_evolved: Optional[str] = None
    """ISO timestamp of last evolution."""

    evolved_by: list[str] = field(default_factory=list)
    """Pattern IDs that triggered evolution of this pattern."""

    evolution_history: list[dict] = field(default_factory=list)
    """History of evolution events. Each dict has:
    - date: str - ISO timestamp
    - trigger: str - What caused the evolution
    - changes: str - What changed
    """

    # =========================================================================
    # Recipe Fields (for pattern_type="recipe")
    # =========================================================================

    pattern_type: Literal["struggle", "recipe"] = "struggle"
    """Type of pattern: 'struggle' (A-MEM) or 'recipe' (workflow template)."""

    wiring: list[dict] = field(default_factory=list)
    """Connection graph for recipes: [{"from": guid, "from_param": str, "to": guid, "to_param": str}, ...]"""

    input_structure: dict = field(default_factory=dict)
    """Input configuration: {"sliders": [...], "panels": [...]} with semantic roles."""

    output_type: str = ""
    """What the recipe produces: "curve", "surface", "brep", "points", etc."""

    source_definition: str = ""
    """Original .ghx filename if extracted from a file."""

    # Recipe v2 graph format (N2C-compatible)
    schema_version: str = "1.0"
    """Schema version: '1.0' for v1 recipes, '2.0' for v2 graph-based recipes."""

    graph: Optional[dict] = None
    """V2 recipe graph (N2C-compatible). Structure:
    {
        "components": [{"id": "R1", "type": "Hexagonal", "guid": "125dc...", "pos": [100, 100]}, ...],
        "flows": ["R1.O0>R2.I1", ...],
        "subgraphs": [{"id": "S1", "role": "pattern_source", "nick": "...", "members": ["R1", "R2"], "inputs": [], "outputs": ["R1.O0"]}, ...]
    }
    Components use R-prefixed IDs. Flows use N2C flow string format.
    Subgraphs are optional annotations for decomposable recipes."""

    # =========================================================================
    # JIT Verification (Phase 3) - Runtime only, not persisted
    # =========================================================================

    _verification_status: Optional[VerificationStatus] = field(default=None, repr=False)
    """Runtime verification status set by PatternVerifier. Not persisted."""

    _verification_warnings: list[str] = field(default_factory=list, repr=False)
    """Runtime verification warnings. Not persisted."""

    _days_since_verified: Optional[int] = field(default=None, repr=False)
    """Days since last verification. Computed at verification time."""

    # =========================================================================
    # Methods
    # =========================================================================

    def success_rate(self) -> float:
        """Calculate success rate (0.0 to 1.0).

        Returns 0.5 (neutral prior) if never used.
        """
        if self.times_used == 0:
            return 0.5
        return self.times_succeeded / self.times_used

    @property
    def learned_from(self) -> Optional[str]:
        """Get the session ID where this pattern was first learned.

        Returns the session_id from the first successful citation,
        or None if no successful citations exist.
        """
        for citation in self.citations:
            if citation.get("outcome") == "success":
                return citation.get("session_id")
        return None

    @property
    def is_verified(self) -> bool:
        """Check if pattern has been verified recently.

        A pattern is considered verified if last_verified is set.
        Future: could add staleness check based on time threshold.
        """
        return self.last_verified is not None

    @property
    def verification_status(self) -> VerificationStatus:
        """Get JIT verification status.

        Returns the status set by PatternVerifier during retrieval,
        or 'unchecked' if verification hasn't been performed.
        """
        return self._verification_status or "unchecked"

    @property
    def verification_warnings(self) -> list[str]:
        """Get warnings from JIT verification."""
        return self._verification_warnings

    @property
    def is_stale(self) -> bool:
        """Check if pattern needs re-verification based on time threshold.

        Uses staleness thresholds (shared with pattern_verifier.StalenessPolicy):
        - High confidence (>80% success): 60 days
        - Default (50-80% success): 30 days
        - Low confidence (<50% success): 14 days
        """
        if not self.last_verified:
            return True

        try:
            timestamp_str = self.last_verified.rstrip("Z")
            timestamp = datetime.fromisoformat(timestamp_str)
            days_since = (datetime.utcnow() - timestamp).days

            # Get threshold based on success rate (uses module-level constants)
            rate = self.success_rate()
            if rate >= 0.8:
                threshold = STALENESS_HIGH_CONFIDENCE_DAYS
            elif rate < 0.5:
                threshold = STALENESS_LOW_CONFIDENCE_DAYS
            else:
                threshold = STALENESS_DEFAULT_DAYS

            return days_since > threshold
        except (ValueError, TypeError):
            return True

    def set_verification(
        self,
        status: VerificationStatus,
        warnings: list[str] | None = None,
        days_since: int | None = None,
    ) -> None:
        """Set JIT verification status (called by PatternVerifier).

        Args:
            status: Verification status
            warnings: Warning messages from verification
            days_since: Days since last successful verification
        """
        self._verification_status = status
        self._verification_warnings = warnings or []
        self._days_since_verified = days_since

    def verification_to_dict(self) -> dict:
        """Get verification info for MCP response.

        Returns dict suitable for including in tool responses.
        """
        return {
            "status": self.verification_status,
            "last_verified": self.last_verified,
            "days_since_verified": self._days_since_verified,
            "is_stale": self.is_stale,
            "warnings": self._verification_warnings,
        }

    @property
    def citation_count(self) -> int:
        """Count of citations (sessions where this pattern was used/discovered)."""
        return len(self.citations)

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict for storage."""
        return {
            "pattern_id": self.pattern_id,
            "name": self.name,
            "version": self.version,
            "created": self.created,
            "solution": {
                "brief": self.solution_brief,
                "principle": self.solution_principle,
                "components_needed": self.components_needed,
            },
            "triggers": {
                "intents": self.trigger_intents,
                "symptoms": self.trigger_symptoms,
            },
            "scope": {
                "global": self.scope_global,
                "project_types": self.scope_project_types,
                "workflow_types": self.scope_workflow_types,
            },
            "anti_patterns": self.anti_patterns,
            "constraints": {
                "preconditions": self.preconditions,
                "postconditions": self.postconditions,
            },
            "verification": {
                "test": self.verification_test,
                "expected": self.verification_expected,
            },
            "citations": self.citations,
            "confidence": {
                "times_used": self.times_used,
                "times_succeeded": self.times_succeeded,
                "last_used": self.last_used,
                "last_verified": self.last_verified,
            },
            "links": self.links,
            "tags": self.tags,
            "evolution": {
                "created_from": self.created_from,
                "last_evolved": self.last_evolved,
                "evolved_by": self.evolved_by,
                "evolution_history": self.evolution_history,
            },
            "recipe": {
                "pattern_type": self.pattern_type,
                "schema_version": self.schema_version,
                # v1 fields (kept for backward compat during migration)
                "wiring": self.wiring,
                "input_structure": self.input_structure,
                "output_type": self.output_type,
                "source_definition": self.source_definition,
                # v2 graph (only present for v2 recipes)
                **({"graph": self.graph} if self.graph else {}),
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PatternNote":
        """Create PatternNote from JSON dict.

        Handles nested structure and missing fields gracefully.
        """
        solution = data.get("solution", {})
        triggers = data.get("triggers", {})
        scope = data.get("scope", {})
        constraints = data.get("constraints", {})
        verification = data.get("verification", {})
        confidence = data.get("confidence", {})
        evolution = data.get("evolution", {})
        recipe = data.get("recipe", {})

        return cls(
            # Core identity
            pattern_id=data.get("pattern_id", ""),
            name=data.get("name", ""),
            version=data.get("version", "1.0"),
            created=data.get("created", ""),
            # Solution
            solution_brief=solution.get("brief", ""),
            solution_principle=solution.get("principle", ""),
            components_needed=solution.get("components_needed", []),
            # Triggers
            trigger_intents=triggers.get("intents", []),
            trigger_symptoms=triggers.get("symptoms", []),
            # Scope
            scope_global=scope.get("global", True),
            scope_project_types=scope.get("project_types", []),
            scope_workflow_types=scope.get("workflow_types", []),
            # Anti-patterns & constraints
            anti_patterns=data.get("anti_patterns", []),
            preconditions=constraints.get("preconditions", []),
            postconditions=constraints.get("postconditions", []),
            # Verification
            verification_test=verification.get("test", ""),
            verification_expected=verification.get("expected", ""),
            # Citations
            citations=data.get("citations", []),
            # Confidence
            times_used=confidence.get("times_used", 0),
            times_succeeded=confidence.get("times_succeeded", 0),
            last_used=confidence.get("last_used"),
            last_verified=confidence.get("last_verified"),
            # Links & tags
            links=data.get("links", []),
            tags=data.get("tags", []),
            # Evolution
            created_from=evolution.get("created_from", "manual"),
            last_evolved=evolution.get("last_evolved"),
            evolved_by=evolution.get("evolved_by", []),
            evolution_history=evolution.get("evolution_history", []),
            # Recipe fields
            pattern_type=recipe.get("pattern_type", "struggle"),
            wiring=recipe.get("wiring", []),
            input_structure=recipe.get("input_structure", {}),
            output_type=recipe.get("output_type", ""),
            source_definition=recipe.get("source_definition", ""),
            # Recipe v2 fields
            schema_version=recipe.get("schema_version", "1.0"),
            graph=recipe.get("graph"),
        )

    def __repr__(self) -> str:
        return f"PatternNote(id={self.pattern_id!r}, name={self.name!r}, success_rate={self.success_rate():.2f})"


@dataclass
class PatternIndex:
    """In-memory index for fast pattern lookup.

    Maintains multiple indices for different query types:
    - by_symptom: For debugging (what's going wrong?)
    - by_intent: For planning (what am I trying to do?)
    - by_tag: For classification/browsing
    - by_component: For component-specific patterns

    Persisted to pattern_index.json for quick startup.
    Can be rebuilt from pattern files if corrupted.
    """

    by_symptom: dict[str, list[str]] = field(default_factory=dict)
    """Symptom text (lowercase) → list of pattern IDs."""

    by_intent: dict[str, list[str]] = field(default_factory=dict)
    """Intent keyword (lowercase) → list of pattern IDs."""

    by_tag: dict[str, list[str]] = field(default_factory=dict)
    """Tag (lowercase) → list of pattern IDs."""

    by_component: dict[str, list[str]] = field(default_factory=dict)
    """Component name (lowercase) → list of pattern IDs."""

    all_patterns: list[str] = field(default_factory=list)
    """All pattern IDs for iteration."""

    def add_pattern(self, pattern: PatternNote) -> None:
        """Index a pattern for lookup.

        Call this when adding a new pattern to the store.
        """
        pid = pattern.pattern_id

        # Track in all_patterns
        if pid not in self.all_patterns:
            self.all_patterns.append(pid)

        # Index by symptom
        for symptom in pattern.trigger_symptoms:
            key = symptom.lower().strip()
            if key:
                self.by_symptom.setdefault(key, [])
                if pid not in self.by_symptom[key]:
                    self.by_symptom[key].append(pid)

        # Index by intent (split into words for partial matching)
        for intent in pattern.trigger_intents:
            for word in intent.lower().split():
                word = word.strip()
                if word and len(word) > 2:  # Skip very short words
                    self.by_intent.setdefault(word, [])
                    if pid not in self.by_intent[word]:
                        self.by_intent[word].append(pid)

        # Index by tag
        for tag in pattern.tags:
            key = tag.lower().strip()
            if key:
                self.by_tag.setdefault(key, [])
                if pid not in self.by_tag[key]:
                    self.by_tag[key].append(pid)

        # Index by component
        for comp in pattern.components_needed:
            key = comp.lower().strip()
            if key:
                self.by_component.setdefault(key, [])
                if pid not in self.by_component[key]:
                    self.by_component[key].append(pid)

    def remove_pattern(self, pattern_id: str) -> None:
        """Remove pattern from all indices.

        Call this when deleting or updating a pattern.
        For updates, call remove then add with the new pattern.
        """
        # Remove from all_patterns
        if pattern_id in self.all_patterns:
            self.all_patterns.remove(pattern_id)

        # Remove from all indices
        for index in [self.by_symptom, self.by_intent, self.by_tag, self.by_component]:
            for key in list(index.keys()):
                if pattern_id in index[key]:
                    index[key].remove(pattern_id)
                # Clean up empty lists
                if not index[key]:
                    del index[key]

    def find_candidates(
        self,
        symptoms: list[str] | None = None,
        intents: list[str] | None = None,
        tags: list[str] | None = None,
        components: list[str] | None = None,
        limit: int = 10,
    ) -> list[str]:
        """Find candidate patterns matching any of the criteria.

        Returns pattern IDs sorted by match count (most matches first).
        Symptoms are weighted 2x because they're more specific signals.

        Args:
            symptoms: Observable symptoms to match
            intents: Intent phrases/keywords to match
            tags: Classification tags to match
            components: Component names to match
            limit: Maximum number of results

        Returns:
            List of pattern IDs, best matches first
        """
        scores: dict[str, int] = {}

        # Match symptoms (weighted 2x - more specific signal)
        if symptoms:
            for symptom in symptoms:
                key = symptom.lower().strip()
                for pid in self.by_symptom.get(key, []):
                    scores[pid] = scores.get(pid, 0) + 2

        # Match intent keywords
        if intents:
            for intent in intents:
                for word in intent.lower().split():
                    word = word.strip()
                    if word and len(word) > 2:
                        for pid in self.by_intent.get(word, []):
                            scores[pid] = scores.get(pid, 0) + 1

        # Match tags
        if tags:
            for tag in tags:
                key = tag.lower().strip()
                for pid in self.by_tag.get(key, []):
                    scores[pid] = scores.get(pid, 0) + 1

        # Match components
        if components:
            for comp in components:
                key = comp.lower().strip()
                for pid in self.by_component.get(key, []):
                    scores[pid] = scores.get(pid, 0) + 1

        # Sort by score descending, return top N
        ranked = sorted(scores.items(), key=lambda x: -x[1])
        return [pid for pid, _ in ranked[:limit]]

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict for storage."""
        return {
            "by_symptom": self.by_symptom,
            "by_intent": self.by_intent,
            "by_tag": self.by_tag,
            "by_component": self.by_component,
            "all_patterns": self.all_patterns,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PatternIndex":
        """Create PatternIndex from JSON dict."""
        return cls(
            by_symptom=data.get("by_symptom", {}),
            by_intent=data.get("by_intent", {}),
            by_tag=data.get("by_tag", {}),
            by_component=data.get("by_component", {}),
            all_patterns=data.get("all_patterns", []),
        )

    def __len__(self) -> int:
        return len(self.all_patterns)

    def __repr__(self) -> str:
        return (
            f"PatternIndex(patterns={len(self.all_patterns)}, "
            f"symptoms={len(self.by_symptom)}, "
            f"intents={len(self.by_intent)}, "
            f"tags={len(self.by_tag)})"
        )
