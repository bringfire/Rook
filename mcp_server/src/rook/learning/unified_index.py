# mcp_server/src/rook/learning/unified_index.py
"""
UnifiedIndex - Index for fast knowledge note lookup.

Provides O(1) lookups by intent, symptom, tag, keyword, component, and category.
Tracks reverse links for DAG traversal ("what notes link to this note?").
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING
import json
import re

if TYPE_CHECKING:
    from .knowledge_note import KnowledgeNote

# Words that appear in many trigger_intents but carry no component-discriminating
# signal.  Compound intents like "create a sphere with radius slider" need these
# stripped so "sphere" and "slider" aren't drowned out by "create" (11 matches)
# and "with" (7 matches).
_COMPONENT_STOP_WORDS = frozenset({
    "the", "and", "for", "with", "from", "that", "this", "into", "onto",
    "using", "create", "make", "add", "get", "set", "put", "use", "new",
    "controlled", "connected", "driven", "based",
})


def _tokenize_component_intent(text: str) -> list[str]:
    """Tokenize user intent into normalized content words for component lookup."""
    words = [
        w for w in re.findall(r"[a-z0-9]+", text.lower())
        if len(w) > 2 and w not in _COMPONENT_STOP_WORDS
    ]
    # Basic singular normalization: "sliders" → "slider", "curves" → "curve"
    # Matches how add_note indexes component names (always singular).
    return [
        w.rstrip("s") if w.endswith("s") and not w.endswith("ss") and len(w) > 3 else w
        for w in words
    ]


@dataclass
class UnifiedIndex:
    """Single index for all knowledge notes with reverse link tracking."""

    # Forward lookups (keyword → note IDs)
    by_intent: dict[str, list[str]] = field(default_factory=dict)
    by_symptom: dict[str, list[str]] = field(default_factory=dict)
    by_tag: dict[str, list[str]] = field(default_factory=dict)
    by_keyword: dict[str, list[str]] = field(default_factory=dict)
    by_component: dict[str, list[str]] = field(default_factory=dict)
    by_category: dict[str, list[str]] = field(default_factory=dict)

    # Reverse link tracking (for DAG traversal)
    links_to: dict[str, list[str]] = field(default_factory=dict)

    # Type filtering
    by_type: dict[str, list[str]] = field(default_factory=dict)

    # All notes
    all_notes: list[str] = field(default_factory=list)
    note_count: int = 0

    def add_note(self, note: "KnowledgeNote") -> None:
        """Index a note for lookup."""
        note_id = note.note_id

        # Add to all_notes if not present
        if note_id not in self.all_notes:
            self.all_notes.append(note_id)
            self.note_count = len(self.all_notes)

        # Index by type
        self.by_type.setdefault(note.note_type, [])
        if note_id not in self.by_type[note.note_type]:
            self.by_type[note.note_type].append(note_id)

        # Index by intent (split into words)
        for intent in note.trigger_intents:
            for word in intent.lower().split():
                word = word.strip()
                if word and len(word) > 2:
                    self.by_intent.setdefault(word, [])
                    if note_id not in self.by_intent[word]:
                        self.by_intent[word].append(note_id)

        # Index by symptom (split into words)
        for symptom in note.trigger_symptoms:
            for word in symptom.lower().split():
                word = word.strip()
                if word and len(word) > 2:
                    self.by_symptom.setdefault(word, [])
                    if note_id not in self.by_symptom[word]:
                        self.by_symptom[word].append(note_id)

        # Index by tag
        for tag in note.tags:
            key = tag.lower().strip()
            if key:
                self.by_tag.setdefault(key, [])
                if note_id not in self.by_tag[key]:
                    self.by_tag[key].append(note_id)

        # Index by keyword
        for keyword in note.keywords:
            key = keyword.lower().strip()
            if key:
                self.by_keyword.setdefault(key, [])
                if note_id not in self.by_keyword[key]:
                    self.by_keyword[key].append(note_id)

        # Index by component
        for comp in note.components:
            key = comp.lower().strip()
            if key:
                self.by_component.setdefault(key, [])
                if note_id not in self.by_component[key]:
                    self.by_component[key].append(note_id)

        # Index by category
        if note.category:
            key = note.category.lower().strip()
            self.by_category.setdefault(key, [])
            if note_id not in self.by_category[key]:
                self.by_category[key].append(note_id)

        # Track reverse links
        for linked_id in note.links:
            self.links_to.setdefault(linked_id, [])
            if note_id not in self.links_to[linked_id]:
                self.links_to[linked_id].append(note_id)

    def remove_note(self, note_id: str) -> None:
        """Remove note from all indices."""
        if note_id in self.all_notes:
            self.all_notes.remove(note_id)
            self.note_count = len(self.all_notes)

        # Remove from all forward indices
        for index in [self.by_type, self.by_intent, self.by_symptom,
                      self.by_tag, self.by_keyword, self.by_component, self.by_category]:
            for key in list(index.keys()):
                if note_id in index[key]:
                    index[key].remove(note_id)
                if not index[key]:
                    del index[key]

        # Remove from reverse links
        for key in list(self.links_to.keys()):
            if note_id in self.links_to[key]:
                self.links_to[key].remove(note_id)
            if not self.links_to[key]:
                del self.links_to[key]

    def get_notes_linking_to(self, note_id: str) -> list[str]:
        """Get all notes that link TO this note (reverse traversal)."""
        return self.links_to.get(note_id, [])

    def find_candidates(
        self,
        intents: list[str] | None = None,
        symptoms: list[str] | None = None,
        tags: list[str] | None = None,
        keywords: list[str] | None = None,
        components: list[str] | None = None,
        limit: int = 10,
    ) -> list[str]:
        """Find candidate notes matching criteria. Returns best matches first."""
        scores: dict[str, int] = {}

        # Match intents
        if intents:
            for intent in intents:
                for word in intent.lower().split():
                    word = word.strip()
                    if word and len(word) > 2:
                        for note_id in self.by_intent.get(word, []):
                            scores[note_id] = scores.get(note_id, 0) + 1

        # Match symptoms (weighted 2x - more specific)
        if symptoms:
            for symptom in symptoms:
                for word in symptom.lower().split():
                    word = word.strip()
                    if word and len(word) > 2:
                        for note_id in self.by_symptom.get(word, []):
                            scores[note_id] = scores.get(note_id, 0) + 2

        # Match tags
        if tags:
            for tag in tags:
                key = tag.lower().strip()
                for note_id in self.by_tag.get(key, []):
                    scores[note_id] = scores.get(note_id, 0) + 1

        # Match keywords
        if keywords:
            for keyword in keywords:
                key = keyword.lower().strip()
                for note_id in self.by_keyword.get(key, []):
                    scores[note_id] = scores.get(note_id, 0) + 1

        # Match components
        if components:
            for comp in components:
                key = comp.lower().strip()
                for note_id in self.by_component.get(key, []):
                    scores[note_id] = scores.get(note_id, 0) + 1

        # Sort by score descending
        ranked = sorted(scores.items(), key=lambda x: -x[1])
        return [note_id for note_id, _ in ranked[:limit]]

    def find_component_candidates(self, intent: str, limit: int = 10) -> list[str]:
        """Phrase-priority candidate finding restricted to component notes.

        Replicates GHSparseIndex.lookup_multi() phrase-priority logic on top of
        the token-bag index, scoring components that match longer phrases higher.

        Scoring:
            Phase 1: Full phrase (all words match) — weight = len(words) * 10
            Phase 2: Sub-phrases (contiguous, 2+ words) — weight = len(sub) * 3
            Phase 3: Individual words — weight = 1

        Note: Words of 2 chars or fewer are filtered out (consistent with add_note
        indexing). Short intents like "pi" or "ln" will return no results — callers
        should use get_component_by_guid() or full component names for these.

        Stop words (create, make, with, etc.) are filtered to prevent noise from
        drowning out content words in compound intents like "create a sphere with
        radius slider".

        Phase 4 (coverage guarantee): After scoring, ensures every content word has
        at least one representative in the results. This prevents one concept (e.g.
        "sphere") from filling all slots and pushing out another (e.g. "slider").
        """
        words = _tokenize_component_intent(intent)
        if not words:
            return []

        component_ids = set(self.by_type.get("component", []))
        scores: dict[str, int] = {}

        def _score_phrase(phrase_words: list[str], weight: int) -> None:
            """Score component notes that match ALL words in phrase_words."""
            if not phrase_words:
                return
            # Gather candidates from both intent and keyword indices
            candidate_sets = []
            for w in phrase_words:
                hits = set(self.by_intent.get(w, [])) | set(self.by_keyword.get(w, []))
                candidate_sets.append(hits)
            if not candidate_sets:
                return
            # Intersect: note must appear in ALL word indices
            intersection = candidate_sets[0]
            for s in candidate_sets[1:]:
                intersection = intersection & s
            for note_id in intersection:
                if note_id in component_ids:
                    scores[note_id] = scores.get(note_id, 0) + weight

        # Phase 1: full phrase — highest weight
        _score_phrase(words, weight=len(words) * 10)

        # Phase 2: sub-phrases (contiguous, length >= 2)
        if len(words) > 1:
            for phrase_len in range(len(words) - 1, 1, -1):
                for i in range(len(words) - phrase_len + 1):
                    sub = words[i : i + phrase_len]
                    _score_phrase(sub, weight=phrase_len * 3)

        # Phase 3: individual words (union intent+keyword to avoid double-counting)
        for word in words:
            hits = set(self.by_intent.get(word, [])) | set(self.by_keyword.get(word, []))
            for note_id in hits:
                if note_id in component_ids:
                    scores[note_id] = scores.get(note_id, 0) + 1

        # Phase 3.5: exact name match boost.
        # When "circle" appears as a content word and there's a component whose
        # name IS "circle" (not "circle cnr", "incircle"), boost it above variants.
        # This ensures the simplest/most-generic component ranks first, giving
        # the DSPy resolver a clearer signal for common intents.
        # Weight 5: enough to break ties among score-1 candidates but below
        # Phase 1/2 phrase-match weights.
        for word in words:
            exact_hits = self.by_component.get(word, [])
            for note_id in exact_hits:
                if note_id in component_ids and note_id in scores:
                    scores[note_id] = scores.get(note_id, 0) + 5

        ranked = sorted(scores.items(), key=lambda x: -x[1])
        result_ids = [note_id for note_id, _ in ranked[:limit]]

        # Phase 4: coverage guarantee — ensure every content word has at least
        # one representative.  Without this, "sphere" components (5 matches) can
        # fill the top slots and push "slider" (2 matches) out entirely.
        result_set = set(result_ids)
        for word in words:
            word_hits = (
                set(self.by_intent.get(word, []))
                | set(self.by_keyword.get(word, []))
            ) & component_ids
            if word_hits & result_set:
                continue  # already covered
            # Pick the highest-scored uncovered component for this word
            for note_id, _ in ranked:
                if note_id in word_hits and note_id not in result_set:
                    result_ids.append(note_id)
                    result_set.add(note_id)
                    break

        return result_ids

    def to_dict(self) -> dict:
        """Serialize to dict for JSON storage."""
        return {
            "by_intent": self.by_intent,
            "by_symptom": self.by_symptom,
            "by_tag": self.by_tag,
            "by_keyword": self.by_keyword,
            "by_component": self.by_component,
            "by_category": self.by_category,
            "links_to": self.links_to,
            "by_type": self.by_type,
            "all_notes": self.all_notes,
            "note_count": self.note_count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "UnifiedIndex":
        """Deserialize from dict."""
        return cls(
            by_intent=data.get("by_intent", {}),
            by_symptom=data.get("by_symptom", {}),
            by_tag=data.get("by_tag", {}),
            by_keyword=data.get("by_keyword", {}),
            by_component=data.get("by_component", {}),
            by_category=data.get("by_category", {}),
            links_to=data.get("links_to", {}),
            by_type=data.get("by_type", {}),
            all_notes=data.get("all_notes", []),
            note_count=data.get("note_count", 0),
        )

    def save(self, path: Path) -> None:
        """Atomic save with temp file rename."""
        temp_path = path.with_suffix(".tmp")
        temp_path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        temp_path.replace(path)

    @classmethod
    def load(cls, path: Path) -> "UnifiedIndex":
        """Load index from file."""
        if not path.exists():
            return cls()
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls.from_dict(data)

    def rebuild_from_notes(self, notes: list["KnowledgeNote"]) -> "UnifiedIndex":
        """Rebuild entire index from notes (recovery operation)."""
        fresh = UnifiedIndex()
        for note in notes:
            fresh.add_note(note)
        return fresh

    def __len__(self) -> int:
        return self.note_count

    def __repr__(self) -> str:
        return f"UnifiedIndex(notes={self.note_count}, intents={len(self.by_intent)}, tags={len(self.by_tag)})"
