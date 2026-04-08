# mcp_server/src/rook/learning/knowledge_note.py
"""
KnowledgeNote - Unified A-MEM note for all GH knowledge.

Represents components, recipes, and struggles in a single dataclass
with tiered access (quick/context/errors/raw) and A-MEM evolution support.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional
import uuid

# Type aliases
NoteType = Literal["component", "recipe", "struggle", "teaching"]
TierLevel = Literal["quick", "context", "errors", "raw"]

# Token estimates per tier
TIER_TOKEN_ESTIMATES = {
    "quick": 25,
    "context": 80,
    "errors": 40,
    "raw": 300,
}


@dataclass
class KnowledgeNote:
    """Unified A-MEM note for all GH knowledge.

    Can represent:
    - component: GH component with GUID, inputs, outputs
    - recipe: Workflow pattern with wiring graph
    - struggle: Problem→solution pattern with anti-patterns

    All note types share the same fields for uniform evolution.
    Type-specific data goes in `type_data` dict.
    """

    # === Identity ===
    note_id: str
    note_type: NoteType
    name: str
    brief: str
    created: str
    version: str = "1.0"

    # === A-MEM Core (LLM-evolvable) ===
    context: str = ""
    keywords: list[str] = field(default_factory=list)
    category: str = "Uncategorized"
    tags: list[str] = field(default_factory=list)

    # === Triggers ===
    trigger_intents: list[str] = field(default_factory=list)
    trigger_symptoms: list[str] = field(default_factory=list)

    # === Content ===
    components: list[str] = field(default_factory=list)
    solution_principle: str = ""
    anti_patterns: list[dict] = field(default_factory=list)
    preconditions: list[str] = field(default_factory=list)
    postconditions: list[str] = field(default_factory=list)

    # === A-MEM Linking ===
    links: list[str] = field(default_factory=list)

    # === Confidence & Usage ===
    times_used: int = 0
    times_succeeded: int = 0
    retrieval_count: int = 0
    last_accessed: Optional[str] = None
    last_verified: Optional[str] = None
    citations: list[dict] = field(default_factory=list)

    # === Evolution ===
    created_from: str = "manual"
    last_evolved: Optional[str] = None
    evolved_by: list[str] = field(default_factory=list)
    evolution_history: list[dict] = field(default_factory=list)

    # === Type-specific data ===
    type_data: dict = field(default_factory=dict)
    deprecated: bool = False
    deprecated_reason: Optional[str] = None
    deprecated_by: Optional[str] = None
    deprecated_replacement_name: Optional[str] = None

    def success_rate(self) -> float:
        """Calculate success rate. Returns 0.5 (neutral prior) if never used."""
        if self.times_used == 0:
            return 0.5
        return self.times_succeeded / self.times_used

    def to_tier(self, tier: TierLevel = "context") -> dict:
        """Return note data at requested tier level."""
        if tier == "quick":
            return {
                "note_id": self.note_id,
                "note_type": self.note_type,
                "name": self.name,
                "brief": self.brief,
                "tags": self.tags[:3],
            }
        elif tier == "context":
            return {
                "note_id": self.note_id,
                "note_type": self.note_type,
                "name": self.name,
                "brief": self.brief,
                "context": self.context,
                "keywords": self.keywords,
                "tags": self.tags,
                "components": self.components,
                "solution_principle": self.solution_principle,
                "preconditions": self.preconditions,
                "anti_patterns": self.anti_patterns[:2],
            }
        elif tier == "errors":
            return {
                "note_id": self.note_id,
                "note_type": self.note_type,
                "name": self.name,
                "trigger_symptoms": self.trigger_symptoms,
                "anti_patterns": self.anti_patterns,
                "postconditions": self.postconditions,
            }
        elif tier == "raw":
            return self.to_dict()
        else:
            raise ValueError(f"Unknown tier: {tier}")

    def to_dict(self) -> dict:
        """Full serialization for storage."""
        return {
            "note_id": self.note_id,
            "note_type": self.note_type,
            "name": self.name,
            "brief": self.brief,
            "version": self.version,
            "created": self.created,
            "context": self.context,
            "keywords": self.keywords,
            "category": self.category,
            "tags": self.tags,
            "trigger_intents": self.trigger_intents,
            "trigger_symptoms": self.trigger_symptoms,
            "components": self.components,
            "solution_principle": self.solution_principle,
            "anti_patterns": self.anti_patterns,
            "preconditions": self.preconditions,
            "postconditions": self.postconditions,
            "links": self.links,
            "times_used": self.times_used,
            "times_succeeded": self.times_succeeded,
            "retrieval_count": self.retrieval_count,
            "last_accessed": self.last_accessed,
            "last_verified": self.last_verified,
            "citations": self.citations,
            "created_from": self.created_from,
            "last_evolved": self.last_evolved,
            "evolved_by": self.evolved_by,
            "evolution_history": self.evolution_history,
            "type_data": self.type_data,
            "deprecated": self.deprecated,
            "deprecated_reason": self.deprecated_reason,
            "deprecated_by": self.deprecated_by,
            "deprecated_replacement_name": self.deprecated_replacement_name,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "KnowledgeNote":
        """Create KnowledgeNote from dict. Handles missing fields gracefully."""
        return cls(
            note_id=data.get("note_id", ""),
            note_type=data.get("note_type", "component"),
            name=data.get("name", ""),
            brief=data.get("brief", ""),
            version=data.get("version", "1.0"),
            created=data.get("created", ""),
            context=data.get("context", ""),
            keywords=data.get("keywords", []),
            category=data.get("category", "Uncategorized"),
            tags=data.get("tags", []),
            trigger_intents=data.get("trigger_intents", []),
            trigger_symptoms=data.get("trigger_symptoms", []),
            components=data.get("components", []),
            solution_principle=data.get("solution_principle", ""),
            anti_patterns=data.get("anti_patterns", []),
            preconditions=data.get("preconditions", []),
            postconditions=data.get("postconditions", []),
            links=data.get("links", []),
            times_used=data.get("times_used", 0),
            times_succeeded=data.get("times_succeeded", 0),
            retrieval_count=data.get("retrieval_count", 0),
            last_accessed=data.get("last_accessed"),
            last_verified=data.get("last_verified"),
            citations=data.get("citations", []),
            created_from=data.get("created_from", "manual"),
            last_evolved=data.get("last_evolved"),
            evolved_by=data.get("evolved_by", []),
            evolution_history=data.get("evolution_history", []),
            type_data=data.get("type_data", {}),
            deprecated=data.get("deprecated", False),
            deprecated_reason=data.get("deprecated_reason"),
            deprecated_by=data.get("deprecated_by"),
            deprecated_replacement_name=data.get("deprecated_replacement_name"),
        )

    @staticmethod
    def generate_id(note_type: NoteType) -> str:
        """Generate a new note ID with type prefix."""
        prefix = {"component": "comp", "recipe": "recipe", "struggle": "struggle", "teaching": "teaching"}[note_type]
        return f"{prefix}_{uuid.uuid4().hex[:8]}"

    def __repr__(self) -> str:
        return f"KnowledgeNote(id={self.note_id!r}, type={self.note_type!r}, name={self.name!r})"
