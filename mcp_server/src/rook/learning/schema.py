"""
Knowledge Graph V2 Schema for Autonomous Learning.

This schema is designed for knowledge cultivation - not just storage.
It tracks patterns, antipatterns, gaps, insights, relationships,
verifications, and session handoffs to enable autonomous learning.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from enum import Enum
import uuid


class GapStatus(Enum):
    """Status of a knowledge gap."""
    UNINVESTIGATED = "uninvestigated"
    INVESTIGATING = "investigating"
    RESOLVED = "resolved"
    ABANDONED = "abandoned"  # Too difficult, moved on


class GapPriority(Enum):
    """Priority level for investigation."""
    CRITICAL = "critical"  # Blocking other work
    HIGH = "high"          # Important for coverage
    MEDIUM = "medium"      # Would be nice to know
    LOW = "low"            # Minor curiosity


class ErrorCategory(Enum):
    """Categories of errors for better diagnosis."""
    MISSING_PARAM = "missing_param"
    INVALID_PARAM = "invalid_param"
    WRONG_TYPE = "wrong_type"
    PRECONDITION_FAILED = "precondition_failed"
    GEOMETRY_ERROR = "geometry_error"
    RHINO_ERROR = "rhino_error"
    NETWORK_ERROR = "network_error"
    UNKNOWN = "unknown"


class InsightCategory(Enum):
    """Categories of insights discovered."""
    TOOL_RELATIONSHIP = "tool_relationship"
    PARAMETER_PATTERN = "parameter_pattern"
    WORKFLOW_PATTERN = "workflow_pattern"
    ERROR_PATTERN = "error_pattern"
    PERFORMANCE = "performance"
    EDGE_CASE = "edge_case"


class RelationshipType(Enum):
    """Types of relationships between tools."""
    PRODUCES_INPUT_FOR = "produces_input_for"  # Tool A creates what Tool B consumes
    ALTERNATIVE_TO = "alternative_to"          # Either can accomplish the goal
    MUST_PRECEDE = "must_precede"              # A must run before B
    CONFLICTS_WITH = "conflicts_with"          # A and B don't work together
    ENHANCES = "enhances"                      # A makes B work better


def generate_id() -> str:
    """Generate a unique ID."""
    return str(uuid.uuid4())


def now_iso() -> str:
    """Get current timestamp in ISO format."""
    return datetime.utcnow().isoformat() + "Z"


@dataclass
class Pattern:
    """
    A proven approach that works.

    Patterns are the core knowledge - successful ways to accomplish tasks.
    They include preconditions, postconditions, and verification status.
    """
    id: str = field(default_factory=generate_id)
    tool: str = ""  # e.g., "rhino_transform"
    params: dict = field(default_factory=dict)  # e.g., {"operation": "move", "vector": [10,0,0]}

    # Context for when this pattern applies
    preconditions: list[str] = field(default_factory=list)  # ["object must exist", "valid ID"]
    postconditions: list[str] = field(default_factory=list)  # ["object moved by vector"]

    # Human-readable description
    note: str = ""

    # Confidence and verification
    confidence: float = 0.5  # 0.0 to 1.0, updated by MAB
    verification_count: int = 0
    last_verified: str | None = None  # ISO timestamp

    # Provenance
    discovered_by_session: str | None = None
    created_at: str = field(default_factory=now_iso)

    # Example usage
    example_workflow: list[str] = field(default_factory=list)  # ["rhino_create BOX", "get ID", "rhino_transform move"]

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "tool": self.tool,
            "params": self.params,
            "preconditions": self.preconditions,
            "postconditions": self.postconditions,
            "note": self.note,
            "confidence": self.confidence,
            "verification_count": self.verification_count,
            "last_verified": self.last_verified,
            "discovered_by_session": self.discovered_by_session,
            "created_at": self.created_at,
            "example_workflow": self.example_workflow,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Pattern":
        """Create from dictionary."""
        return cls(
            id=data.get("id", generate_id()),
            tool=data.get("tool", ""),
            params=data.get("params", {}),
            preconditions=data.get("preconditions", []),
            postconditions=data.get("postconditions", []),
            note=data.get("note", ""),
            confidence=data.get("confidence", 0.5),
            verification_count=data.get("verification_count", 0),
            last_verified=data.get("last_verified"),
            discovered_by_session=data.get("discovered_by_session"),
            created_at=data.get("created_at", now_iso()),
            example_workflow=data.get("example_workflow", []),
        )


@dataclass
class AttemptedFix:
    """Record of an attempted fix for an antipattern."""
    attempt: str  # Description of what was tried
    result: str   # "success", "failure", or description
    params_used: dict = field(default_factory=dict)


@dataclass
class Antipattern:
    """
    Something that doesn't work, with diagnosis.

    Antipatterns capture failures with analysis of WHY they failed
    and links to patterns that fix them.
    """
    id: str = field(default_factory=generate_id)
    tool: str = ""
    params: dict = field(default_factory=dict)  # The parameters that failed

    # Error information
    error: str = ""  # The actual error message
    error_category: str = ErrorCategory.UNKNOWN.value

    # Diagnosis (the valuable part)
    diagnosis: str = ""  # "The ids parameter is required even for single objects"

    # What was tried to fix it
    attempted_fixes: list[AttemptedFix] = field(default_factory=list)

    # Resolution - link to pattern that works
    resolution_pattern_id: str | None = None

    # Provenance
    discovered_by_session: str | None = None
    created_at: str = field(default_factory=now_iso)

    def add_fix_attempt(self, attempt: str, result: str, params: dict = None):
        """Add a fix attempt."""
        self.attempted_fixes.append(AttemptedFix(
            attempt=attempt,
            result=result,
            params_used=params or {}
        ))

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "tool": self.tool,
            "params": self.params,
            "error": self.error,
            "error_category": self.error_category,
            "diagnosis": self.diagnosis,
            "attempted_fixes": [
                {"attempt": af.attempt, "result": af.result, "params_used": af.params_used}
                for af in self.attempted_fixes
            ],
            "resolution_pattern_id": self.resolution_pattern_id,
            "discovered_by_session": self.discovered_by_session,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Antipattern":
        """Create from dictionary."""
        ap = cls(
            id=data.get("id", generate_id()),
            tool=data.get("tool", ""),
            params=data.get("params", {}),
            error=data.get("error", ""),
            error_category=data.get("error_category", ErrorCategory.UNKNOWN.value),
            diagnosis=data.get("diagnosis", ""),
            resolution_pattern_id=data.get("resolution_pattern_id"),
            discovered_by_session=data.get("discovered_by_session"),
            created_at=data.get("created_at", now_iso()),
        )
        for af_data in data.get("attempted_fixes", []):
            ap.attempted_fixes.append(AttemptedFix(
                attempt=af_data.get("attempt", ""),
                result=af_data.get("result", ""),
                params_used=af_data.get("params_used", {})
            ))
        return ap


@dataclass
class Gap:
    """
    Something we don't know yet.

    Gaps are investigation targets. They track what we don't understand,
    hypotheses we have, and investigation progress.
    """
    id: str = field(default_factory=generate_id)
    tool: str = ""  # Which tool this gap relates to

    # What we don't know
    unknown_aspect: str = ""  # "What curve arrangement is required for successful loft?"

    # Priority for investigation
    priority: str = GapPriority.MEDIUM.value

    # Investigation state
    status: str = GapStatus.UNINVESTIGATED.value
    investigating_session: str | None = None  # Which session is working on this
    investigation_attempts: int = 0
    last_attempt: str | None = None  # ISO timestamp

    # Hypotheses to test
    hypotheses: list[str] = field(default_factory=list)  # ["Curves must be parallel", ...]
    tested_hypotheses: list[dict] = field(default_factory=list)  # [{"hypothesis": "...", "result": "..."}]

    # Resolution
    resolution: str | None = None  # What we learned
    resolved_by_pattern_id: str | None = None  # Link to pattern that documents the solution

    # Provenance
    discovered_by_session: str | None = None
    created_at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "tool": self.tool,
            "unknown_aspect": self.unknown_aspect,
            "priority": self.priority,
            "status": self.status,
            "investigating_session": self.investigating_session,
            "investigation_attempts": self.investigation_attempts,
            "last_attempt": self.last_attempt,
            "hypotheses": self.hypotheses,
            "tested_hypotheses": self.tested_hypotheses,
            "resolution": self.resolution,
            "resolved_by_pattern_id": self.resolved_by_pattern_id,
            "discovered_by_session": self.discovered_by_session,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Gap":
        """Create from dictionary."""
        return cls(
            id=data.get("id", generate_id()),
            tool=data.get("tool", ""),
            unknown_aspect=data.get("unknown_aspect", ""),
            priority=data.get("priority", GapPriority.MEDIUM.value),
            status=data.get("status", GapStatus.UNINVESTIGATED.value),
            investigating_session=data.get("investigating_session"),
            investigation_attempts=data.get("investigation_attempts", 0),
            last_attempt=data.get("last_attempt"),
            hypotheses=data.get("hypotheses", []),
            tested_hypotheses=data.get("tested_hypotheses", []),
            resolution=data.get("resolution"),
            resolved_by_pattern_id=data.get("resolved_by_pattern_id"),
            discovered_by_session=data.get("discovered_by_session"),
            created_at=data.get("created_at", now_iso()),
        )


@dataclass
class Insight:
    """
    An observation about how tools work together.

    Insights are higher-level learnings that span multiple patterns.
    They capture relationships and meta-knowledge.
    """
    id: str = field(default_factory=generate_id)
    category: str = InsightCategory.TOOL_RELATIONSHIP.value

    # The insight itself
    observation: str = ""  # "Creation tools return IDs that modification tools consume"

    # Evidence
    derived_from_pattern_ids: list[str] = field(default_factory=list)  # Pattern IDs that support this
    derived_from_antipattern_ids: list[str] = field(default_factory=list)

    # Implications for future work
    implications: list[str] = field(default_factory=list)  # ["Always capture IDs", "Build context first"]

    # Provenance
    discovered_by_session: str | None = None
    created_at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "category": self.category,
            "observation": self.observation,
            "derived_from_pattern_ids": self.derived_from_pattern_ids,
            "derived_from_antipattern_ids": self.derived_from_antipattern_ids,
            "implications": self.implications,
            "discovered_by_session": self.discovered_by_session,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Insight":
        """Create from dictionary."""
        return cls(
            id=data.get("id", generate_id()),
            category=data.get("category", InsightCategory.TOOL_RELATIONSHIP.value),
            observation=data.get("observation", ""),
            derived_from_pattern_ids=data.get("derived_from_pattern_ids", []),
            derived_from_antipattern_ids=data.get("derived_from_antipattern_ids", []),
            implications=data.get("implications", []),
            discovered_by_session=data.get("discovered_by_session"),
            created_at=data.get("created_at", now_iso()),
        )


@dataclass
class ToolRelationship:
    """
    A relationship between two tools.

    Captures how tools work together or conflict.
    """
    id: str = field(default_factory=generate_id)
    tool_a: str = ""  # e.g., "rhino_create"
    tool_b: str = ""  # e.g., "rhino_transform"

    relationship_type: str = RelationshipType.PRODUCES_INPUT_FOR.value
    description: str = ""  # "rhino_create produces object IDs that rhino_transform consumes"

    # Example chain
    example_chain: list[str] = field(default_factory=list)  # ["rhino_create BOX → ID → rhino_transform move"]

    # Provenance
    discovered_by_session: str | None = None
    created_at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "tool_a": self.tool_a,
            "tool_b": self.tool_b,
            "relationship_type": self.relationship_type,
            "description": self.description,
            "example_chain": self.example_chain,
            "discovered_by_session": self.discovered_by_session,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ToolRelationship":
        """Create from dictionary."""
        return cls(
            id=data.get("id", generate_id()),
            tool_a=data.get("tool_a", ""),
            tool_b=data.get("tool_b", ""),
            relationship_type=data.get("relationship_type", RelationshipType.PRODUCES_INPUT_FOR.value),
            description=data.get("description", ""),
            example_chain=data.get("example_chain", []),
            discovered_by_session=data.get("discovered_by_session"),
            created_at=data.get("created_at", now_iso()),
        )


@dataclass
class Verification:
    """
    Visual verification of a pattern.

    Records that a pattern was visually confirmed to work,
    not just that the API returned success.
    """
    id: str = field(default_factory=generate_id)
    pattern_id: str = ""  # Which pattern was verified

    # When
    timestamp: str = field(default_factory=now_iso)
    session_id: str | None = None

    # Visual evidence
    viewport_hash: str | None = None  # SHA256 of viewport image (optional)

    # Verification results
    geometry_created: bool = False
    geometry_at_expected_location: bool = False
    measurements_correct: bool = False
    visual_description: str = ""  # "Box visible at expected location, correct dimensions"

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "pattern_id": self.pattern_id,
            "timestamp": self.timestamp,
            "session_id": self.session_id,
            "viewport_hash": self.viewport_hash,
            "geometry_created": self.geometry_created,
            "geometry_at_expected_location": self.geometry_at_expected_location,
            "measurements_correct": self.measurements_correct,
            "visual_description": self.visual_description,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Verification":
        """Create from dictionary."""
        return cls(
            id=data.get("id", generate_id()),
            pattern_id=data.get("pattern_id", ""),
            timestamp=data.get("timestamp", now_iso()),
            session_id=data.get("session_id"),
            viewport_hash=data.get("viewport_hash"),
            geometry_created=data.get("geometry_created", False),
            geometry_at_expected_location=data.get("geometry_at_expected_location", False),
            measurements_correct=data.get("measurements_correct", False),
            visual_description=data.get("visual_description", ""),
        )


@dataclass
class SessionHandoff:
    """
    Record of a session handoff.

    When a Claude instance reaches context limit, it hands off
    to the next instance with notes about what to work on.
    """
    id: str = field(default_factory=generate_id)
    session_id: str = ""

    # When
    timestamp: str = field(default_factory=now_iso)

    # What was accomplished
    accomplishments: list[str] = field(default_factory=list)  # ["Investigated rhino_loft", "Found 3 patterns"]
    patterns_discovered: int = 0
    antipatterns_discovered: int = 0
    gaps_resolved: int = 0
    verifications_performed: int = 0

    # What's next
    next_priorities: list[str] = field(default_factory=list)  # ["Continue rhino_sweep", "Verify booleans"]
    open_gaps: list[str] = field(default_factory=list)  # Gap IDs still being investigated

    # Context state
    context_percentage_used: float = 0.0  # 0.0 to 1.0
    reason_for_handoff: str = "context_limit"  # or "completed", "error", "manual"

    # Notes for next instance
    notes: str = ""  # Free-form notes

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "session_id": self.session_id,
            "timestamp": self.timestamp,
            "accomplishments": self.accomplishments,
            "patterns_discovered": self.patterns_discovered,
            "antipatterns_discovered": self.antipatterns_discovered,
            "gaps_resolved": self.gaps_resolved,
            "verifications_performed": self.verifications_performed,
            "next_priorities": self.next_priorities,
            "open_gaps": self.open_gaps,
            "context_percentage_used": self.context_percentage_used,
            "reason_for_handoff": self.reason_for_handoff,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SessionHandoff":
        """Create from dictionary."""
        return cls(
            id=data.get("id", generate_id()),
            session_id=data.get("session_id", ""),
            timestamp=data.get("timestamp", now_iso()),
            accomplishments=data.get("accomplishments", []),
            patterns_discovered=data.get("patterns_discovered", 0),
            antipatterns_discovered=data.get("antipatterns_discovered", 0),
            gaps_resolved=data.get("gaps_resolved", 0),
            verifications_performed=data.get("verifications_performed", 0),
            next_priorities=data.get("next_priorities", []),
            open_gaps=data.get("open_gaps", []),
            context_percentage_used=data.get("context_percentage_used", 0.0),
            reason_for_handoff=data.get("reason_for_handoff", "context_limit"),
            notes=data.get("notes", ""),
        )


@dataclass
class CultivationStats:
    """
    Statistics about knowledge cultivation.

    Tracks overall progress and health of the knowledge graph.
    """
    total_sessions: int = 0
    total_investigations: int = 0
    patterns_discovered: int = 0
    antipatterns_discovered: int = 0
    gaps_created: int = 0
    gaps_resolved: int = 0
    insights_discovered: int = 0
    verifications_performed: int = 0

    # Rates
    avg_patterns_per_session: float = 0.0
    avg_gaps_resolved_per_session: float = 0.0
    verification_rate: float = 0.0  # Patterns with verification / total patterns

    # Last update
    last_updated: str = field(default_factory=now_iso)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "total_sessions": self.total_sessions,
            "total_investigations": self.total_investigations,
            "patterns_discovered": self.patterns_discovered,
            "antipatterns_discovered": self.antipatterns_discovered,
            "gaps_created": self.gaps_created,
            "gaps_resolved": self.gaps_resolved,
            "insights_discovered": self.insights_discovered,
            "verifications_performed": self.verifications_performed,
            "avg_patterns_per_session": self.avg_patterns_per_session,
            "avg_gaps_resolved_per_session": self.avg_gaps_resolved_per_session,
            "verification_rate": self.verification_rate,
            "last_updated": self.last_updated,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CultivationStats":
        """Create from dictionary."""
        return cls(
            total_sessions=data.get("total_sessions", 0),
            total_investigations=data.get("total_investigations", 0),
            patterns_discovered=data.get("patterns_discovered", 0),
            antipatterns_discovered=data.get("antipatterns_discovered", 0),
            gaps_created=data.get("gaps_created", 0),
            gaps_resolved=data.get("gaps_resolved", 0),
            insights_discovered=data.get("insights_discovered", 0),
            verifications_performed=data.get("verifications_performed", 0),
            avg_patterns_per_session=data.get("avg_patterns_per_session", 0.0),
            avg_gaps_resolved_per_session=data.get("avg_gaps_resolved_per_session", 0.0),
            verification_rate=data.get("verification_rate", 0.0),
            last_updated=data.get("last_updated", now_iso()),
        )

    def update_rates(self):
        """Recalculate rate statistics."""
        if self.total_sessions > 0:
            self.avg_patterns_per_session = self.patterns_discovered / self.total_sessions
            self.avg_gaps_resolved_per_session = self.gaps_resolved / self.total_sessions
        if self.patterns_discovered > 0:
            self.verification_rate = self.verifications_performed / self.patterns_discovered
        self.last_updated = now_iso()


@dataclass
class KnowledgeGraphV2Data:
    """
    The complete V2 knowledge graph data structure.

    This is the root container for all knowledge graph data.
    It includes version info, stats, and all knowledge entities.
    """
    version: str = "2.0"
    last_updated: str = field(default_factory=now_iso)

    # Statistics
    cultivation_stats: CultivationStats = field(default_factory=CultivationStats)

    # Core knowledge
    patterns: list[Pattern] = field(default_factory=list)
    antipatterns: list[Antipattern] = field(default_factory=list)

    # Investigation tracking
    gaps: list[Gap] = field(default_factory=list)

    # Higher-level knowledge
    insights: list[Insight] = field(default_factory=list)
    tool_relationships: list[ToolRelationship] = field(default_factory=list)

    # Verification records
    verifications: list[Verification] = field(default_factory=list)

    # Session history
    session_handoffs: list[SessionHandoff] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "version": self.version,
            "last_updated": self.last_updated,
            "cultivation_stats": self.cultivation_stats.to_dict(),
            "patterns": [p.to_dict() for p in self.patterns],
            "antipatterns": [a.to_dict() for a in self.antipatterns],
            "gaps": [g.to_dict() for g in self.gaps],
            "insights": [i.to_dict() for i in self.insights],
            "tool_relationships": [r.to_dict() for r in self.tool_relationships],
            "verifications": [v.to_dict() for v in self.verifications],
            "session_handoffs": [h.to_dict() for h in self.session_handoffs],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "KnowledgeGraphV2Data":
        """Create from dictionary."""
        return cls(
            version=data.get("version", "2.0"),
            last_updated=data.get("last_updated", now_iso()),
            cultivation_stats=CultivationStats.from_dict(data.get("cultivation_stats", {})),
            patterns=[Pattern.from_dict(p) for p in data.get("patterns", [])],
            antipatterns=[Antipattern.from_dict(a) for a in data.get("antipatterns", [])],
            gaps=[Gap.from_dict(g) for g in data.get("gaps", [])],
            insights=[Insight.from_dict(i) for i in data.get("insights", [])],
            tool_relationships=[ToolRelationship.from_dict(r) for r in data.get("tool_relationships", [])],
            verifications=[Verification.from_dict(v) for v in data.get("verifications", [])],
            session_handoffs=[SessionHandoff.from_dict(h) for h in data.get("session_handoffs", [])],
        )
