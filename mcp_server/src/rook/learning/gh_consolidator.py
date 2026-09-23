"""DSPy-based GH Component Knowledge Structural Consolidation.

This module transforms flat GH component knowledge into structured, hierarchical knowledge
with families, shared behaviors, similar component pairs, and I/O patterns.

The Core Problem:
    ~50 GH components with params, gotchas, and observations exist as flat, disconnected facts.
    No relationships exist between similar components (Pipe/Sweep1),
    no behavior propagation across families, no I/O pattern sharing.

The Solution:
    Use DSPy to discover and build structural relationships:
    - FAMILIES: Group components by function (primitives, curves, surface_ops, transforms)
    - SHARED BEHAVIORS: Identify behaviors that apply across multiple components
    - SIMILAR PAIRS: Link components with shared I/O patterns and behaviors
    - IO PATTERNS: Extract common parameter patterns (curve_input, enum_param)

Architecture:
    Flat Component Knowledge --> DSPy Consolidator --> Structured JSON
    (50 components)             (Discovers structure,  (Families, pairs,
                                 links, propagates)     patterns, behaviors)

API Key Requirement:
    This module requires ANTHROPIC_API_KEY. Load from .env:
        from dotenv import load_dotenv
        load_dotenv()  # Loads from project root .env
"""

from __future__ import annotations

import json
import logging
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import dspy

# Learning boundary: configure DSPy once, on first import of any module that runs an LM.
from .dspy_config import ensure_configured as _ensure_dspy_configured
_ensure_dspy_configured()
from dotenv import load_dotenv
from ..runtime_paths import resolve_readable_knowledge_path, resolve_writable_knowledge_path

logger = logging.getLogger(__name__)


# =============================================================================
# DSPy Signatures for GH Structural Consolidation
# =============================================================================


class IdentifyComponentFamilies(dspy.Signature):
    """Group GH components into semantic families based on function and I/O patterns.

    Analyze component names, descriptions, input/output params to identify natural groupings.
    Families should be meaningful for:
    - Behavior propagation (similar components share similar issues)
    - I/O inheritance (family members often share input types like 'curve', 'plane')
    - Intent routing (user intent maps to family, then to specific component)

    Expected families include: primitives, curves, surface_ops, transforms, math, input,
    tree_operations, analysis, boolean. But discover based on actual data.
    """

    components_json: str = dspy.InputField(
        desc="JSON array of component objects with: guid, name, category, inputs (param names/types), outputs (param names/types), gotcha_count"
    )

    families_json: str = dspy.OutputField(
        desc='JSON object: {"family_name": {"components": ["guid1", "guid2"], "description": "what this family does", "shared_traits": ["trait1", "trait2"]}}'
    )


class FindSharedBehaviors(dspy.Signature):
    """Identify behaviors/gotchas that apply across multiple components.

    Look for semantic patterns in gotcha text, errors, AND real-world observations
    that indicate shared concerns:
    - "Must be 0, 1, or 2" applies to multiple enum-param components (Pipe, Sweep1)
    - "Curve input required" applies to all curve-processing components
    - "Invalid miter type" applies to sweep-like operations
    - Observations record actual wiring successes/failures from runtime

    Return behaviors with the components they apply to and confidence levels.
    """

    components_with_gotchas_json: str = dspy.InputField(
        desc="JSON array of {guid, name, gotchas: [gotcha_text, ...], errors: [...], inputs: {...}, observations: [...]}"
    )
    families_json: str = dspy.InputField(
        desc="Previously identified family structure"
    )

    shared_behaviors_json: str = dspy.OutputField(
        desc='JSON object: {"behavior_id": {"text": "the behavior", "applies_to": ["guid1", "guid2"], "family": "family_name or null if cross-family", "confidence": 0.0-1.0}}'
    )
    propagation_candidates_json: str = dspy.OutputField(
        desc='JSON array of {"behavior": "text", "source_guid": "guid", "candidate_guids": ["guid1"], "reason": "why it might apply"}'
    )


class IdentifySimilarComponents(dspy.Signature):
    """Find pairs of GH components that are semantically similar.

    Similar components:
    - Share multiple input/output param types (both take Curve, output Brep)
    - Have related gotchas (both fail on invalid enum values)
    - Perform analogous operations (Pipe vs Sweep1, Circle vs Ellipse)
    - Have shared enum parameters (both have cap/miter type integer params)

    Similarity enables behavior propagation and input pattern inheritance.
    """

    components_with_params_json: str = dspy.InputField(
        desc="JSON array of {guid, name, inputs: {param: type}, outputs: {param: type}, description}"
    )
    families_json: str = dspy.InputField(
        desc="Previously identified families"
    )

    similar_pairs_json: str = dspy.OutputField(
        desc='JSON array: [{"comp1_guid": "guid1", "comp2_guid": "guid2", "similarity_score": 0.92, "shared_io_pattern": ["curve_input", "brep_output"], "reason": "why similar"}]'
    )


class IdentifyIOPatterns(dspy.Signature):
    """Find I/O parameter patterns that appear across multiple components.

    I/O patterns enable:
    - Input prediction (if component has "Curve" input, predict wiring options)
    - Behavior inheritance (enum params always need 0-2 validation)
    - Auto-wiring (know that Circle.C -> Pipe.C is valid curve connection)

    Common patterns: curve_input, plane_base, radius_param, enum_type, brep_output
    """

    components_with_params_json: str = dspy.InputField(
        desc="JSON array of {guid, name, inputs: {param_nick: type_name}, outputs: {param_nick: type_name}}"
    )

    io_patterns_json: str = dspy.OutputField(
        desc='JSON object: {"pattern_name": {"components": ["guid1", "guid2"], "typical_type": "Curve", "typical_gotcha": "common gotcha or null", "param_role": "input or output"}}'
    )


# =============================================================================
# Data Classes for GH Structured Knowledge
# =============================================================================


@dataclass
class ComponentFamily:
    """A family of related GH components."""

    name: str
    description: str
    components: list[str] = field(default_factory=list)  # GUIDs
    shared_traits: list[str] = field(default_factory=list)
    shared_behaviors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "components": self.components,
            "shared_traits": self.shared_traits,
            "shared_behaviors": self.shared_behaviors,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ComponentFamily":
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            components=data.get("components", []),
            shared_traits=data.get("shared_traits", []),
            shared_behaviors=data.get("shared_behaviors", []),
        )


@dataclass
class SharedBehavior:
    """A behavior/gotcha that applies to multiple components."""

    id: str
    text: str
    applies_to: list[str] = field(default_factory=list)  # GUIDs
    family: Optional[str] = None
    confidence: float = 1.0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "text": self.text,
            "applies_to": self.applies_to,
            "family": self.family,
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SharedBehavior":
        return cls(
            id=data["id"],
            text=data.get("text", ""),
            applies_to=data.get("applies_to", []),
            family=data.get("family"),
            confidence=data.get("confidence", 1.0),
        )


@dataclass
class SimilarComponentPair:
    """Two components that are semantically similar."""

    comp1_guid: str
    comp2_guid: str
    similarity_score: float
    shared_io_pattern: list[str] = field(default_factory=list)
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "comp1_guid": self.comp1_guid,
            "comp2_guid": self.comp2_guid,
            "similarity_score": self.similarity_score,
            "shared_io_pattern": self.shared_io_pattern,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SimilarComponentPair":
        return cls(
            comp1_guid=data["comp1_guid"],
            comp2_guid=data["comp2_guid"],
            similarity_score=data.get("similarity_score", 0.0),
            shared_io_pattern=data.get("shared_io_pattern", []),
            reason=data.get("reason", ""),
        )


@dataclass
class IOPattern:
    """A parameter pattern that appears across multiple components."""

    name: str  # "curve_input", "radius_param", etc.
    components: list[str] = field(default_factory=list)  # GUIDs
    typical_type: str = ""  # "Curve", "Number", "Integer"
    typical_gotcha: Optional[str] = None
    param_role: str = "input"  # "input" or "output"

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "components": self.components,
            "typical_type": self.typical_type,
            "typical_gotcha": self.typical_gotcha,
            "param_role": self.param_role,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "IOPattern":
        return cls(
            name=data["name"],
            components=data.get("components", []),
            typical_type=data.get("typical_type", ""),
            typical_gotcha=data.get("typical_gotcha"),
            param_role=data.get("param_role", "input"),
        )


@dataclass
class ComponentStructure:
    """Complete structural knowledge for GH components."""

    version: str = "1.0"
    created: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
    last_consolidation: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
    consolidation_count: int = 0
    component_count: int = 0

    families: dict[str, ComponentFamily] = field(default_factory=dict)
    shared_behaviors: dict[str, SharedBehavior] = field(default_factory=dict)
    similar_pairs: list[SimilarComponentPair] = field(default_factory=list)
    io_patterns: dict[str, IOPattern] = field(default_factory=dict)
    # GUID → {name, stable_key} for name/stable_key-based queries
    component_metadata: dict[str, dict[str, str]] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dictionary."""
        result = {
            "version": self.version,
            "created": self.created,
            "last_consolidation": self.last_consolidation,
            "consolidation_count": self.consolidation_count,
            "component_count": self.component_count,
            "families": {
                name: f.to_dict()
                for name, f in self.families.items()
            },
            "shared_behaviors": {
                id: b.to_dict()
                for id, b in self.shared_behaviors.items()
            },
            "similar_pairs": [p.to_dict() for p in self.similar_pairs],
            "io_patterns": {
                name: p.to_dict()
                for name, p in self.io_patterns.items()
            },
        }
        if self.component_metadata:
            result["component_metadata"] = self.component_metadata
        return result

    @classmethod
    def from_dict(cls, data: dict) -> "ComponentStructure":
        """Create from dictionary."""
        structure = cls(
            version=data.get("version", "1.0"),
            created=data.get("created", datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")),
            last_consolidation=data.get("last_consolidation", datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")),
            consolidation_count=data.get("consolidation_count", 0),
            component_count=data.get("component_count", 0),
        )

        for name, f_data in data.get("families", {}).items():
            structure.families[name] = ComponentFamily.from_dict(f_data)

        for id, b_data in data.get("shared_behaviors", {}).items():
            structure.shared_behaviors[id] = SharedBehavior.from_dict(b_data)

        for p_data in data.get("similar_pairs", []):
            structure.similar_pairs.append(SimilarComponentPair.from_dict(p_data))

        for name, p_data in data.get("io_patterns", {}).items():
            structure.io_patterns[name] = IOPattern.from_dict(p_data)

        structure.component_metadata = data.get("component_metadata", {})

        return structure

    def save(self, path: Path | str) -> None:
        """Save structure to JSON file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)
        logger.info(f"Saved component structure to {path}")

    @classmethod
    def load(cls, path: Path | str) -> "ComponentStructure":
        """Load structure from JSON file."""
        path = Path(path)
        if not path.exists():
            return cls()
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)


# =============================================================================
# GH Consolidator Class
# =============================================================================


class GHConsolidator:
    """Orchestrates structural consolidation of GH component knowledge.

    Pipeline:
    1. Load current component knowledge from tiered_knowledge.json
    2. Load observations from gh_observations.json
    3. Run IdentifyComponentFamilies
    4. Run FindSharedBehaviors (uses family output)
    5. Run IdentifySimilarComponents (uses family output)
    6. Run IdentifyIOPatterns
    7. Merge into unified structure
    8. Save to component_structure.json

    Usage:
        # Load .env for API key
        from dotenv import load_dotenv
        load_dotenv()

        # Configure DSPy
        from rook.learning.dspy_config import configure_dspy
        configure_dspy(model='claude-3-5-haiku-latest')

        # Run consolidation
        consolidator = GHConsolidator()
        structure = consolidator.consolidate_full()
    """

    # Batch size for processing components (to avoid token limits)
    BATCH_SIZE = 15

    # Orphan GUID handling modes
    ORPHAN_MODE_LEGACY = "legacy-include"  # retain with warning (default)
    ORPHAN_MODE_STRICT = "strict"          # reject unknown GUIDs
    ORPHAN_MODE_REPAIR = "repair"          # attempt to create notes

    def __init__(
        self,
        knowledge_path: str | Path | None = None,
        structure_path: str | Path | None = None,
        observations_path: str | Path | None = None,
        orphan_mode: str = "legacy-include",
    ):
        """Initialize the consolidator.

        Args:
            knowledge_path: Path to tiered_knowledge.json
            structure_path: Path to save component_structure.json (default: same dir)
            observations_path: Path to component_observations.json
            orphan_mode: How to handle GUIDs in tiered but not in UnifiedStore.
                "legacy-include" (default): retain with warning.
                "strict": reject unknown GUIDs (fail-closed).
                "repair": attempt to create minimal notes for unknown GUIDs.
        """
        self._uses_default_knowledge_path = knowledge_path is None
        self.knowledge_path = Path(knowledge_path) if knowledge_path else resolve_writable_knowledge_path("gh", "tiered_knowledge.json")
        self.structure_path = Path(structure_path) if structure_path else resolve_writable_knowledge_path("gh", "component_structure.json")
        self.observations_path = Path(observations_path) if observations_path else resolve_readable_knowledge_path("gh", "component_observations.json")
        self.orphan_mode = orphan_mode

        # DSPy predictors (initialized lazily)
        self._family_identifier: Optional[dspy.Predict] = None
        self._behavior_finder: Optional[dspy.Predict] = None
        self._similarity_finder: Optional[dspy.Predict] = None
        self._pattern_extractor: Optional[dspy.Predict] = None

        # Loaded data
        self._components: Optional[dict] = None
        self._observations: Optional[dict] = None
        self._structure: Optional[ComponentStructure] = None

        # Filter stats (populated by load_components)
        self.raw_component_count: int = 0
        self.active_component_count: int = 0
        self.deprecated_skipped_count: int = 0
        self.unknown_guid_count: int = 0

    @property
    def family_identifier(self) -> dspy.Predict:
        if self._family_identifier is None:
            self._family_identifier = dspy.Predict(IdentifyComponentFamilies)
        return self._family_identifier

    @property
    def behavior_finder(self) -> dspy.Predict:
        if self._behavior_finder is None:
            self._behavior_finder = dspy.Predict(FindSharedBehaviors)
        return self._behavior_finder

    @property
    def similarity_finder(self) -> dspy.Predict:
        if self._similarity_finder is None:
            self._similarity_finder = dspy.Predict(IdentifySimilarComponents)
        return self._similarity_finder

    @property
    def pattern_extractor(self) -> dspy.Predict:
        if self._pattern_extractor is None:
            self._pattern_extractor = dspy.Predict(IdentifyIOPatterns)
        return self._pattern_extractor

    def load_components(self) -> dict:
        """Load component knowledge from UnifiedStore (primary) + tiered_knowledge.json (supplementary).

        Primary source: active component notes from UnifiedStore. Note type_data
        contains guid, category, inputs, outputs, similar_to, stable_key.

        Supplementary: tiered_knowledge.json adds quick, contexts, errors,
        wiring_patterns, gotchas. These are merged into the component dict.

        Fallback: if UnifiedStore is unavailable, loads from tiered_knowledge.json
        only (legacy behavior).
        """
        if self._components is None:
            # Try UnifiedStore as primary source
            store = None
            try:
                from .unified_store import get_unified_store
                store = get_unified_store()
            except Exception as e:
                logger.warning(f"Could not load UnifiedStore: {e}")

            # Load tiered_knowledge.json as supplementary data
            tiered_components: dict[str, dict] = {}
            knowledge_read_path = self.knowledge_path if (not self._uses_default_knowledge_path or self.knowledge_path.exists()) else resolve_readable_knowledge_path("gh", "tiered_knowledge.json")
            if knowledge_read_path.exists():
                with open(knowledge_read_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                tiered_components = data.get("components", {})

            if store is not None:
                # Primary path: build from UnifiedStore notes
                filtered: dict[str, dict] = {}
                deprecated_guids = store.get_deprecated_component_guid_set()
                all_raw_guids = set()

                for note in store.all():
                    if note.note_type != "component":
                        continue
                    td = note.type_data or {}
                    guid = td.get("guid")
                    if not guid:
                        continue

                    all_raw_guids.add(guid)

                    if note.deprecated:
                        continue

                    # Build component dict from note
                    comp_data = {
                        "name": note.name or "",
                        "family": td.get("family", td.get("category", "unknown")),
                        "params": {
                            "inputs": td.get("inputs", {}),
                            "outputs": td.get("outputs", {}),
                        },
                        "quick": note.brief or "",
                        "stable_key": td.get("stable_key", ""),
                    }

                    # Merge supplementary data from tiered_knowledge
                    tiered = tiered_components.get(guid, {})
                    for key in ("gotchas", "errors", "contexts", "wiring_patterns"):
                        if key in tiered:
                            comp_data[key] = tiered[key]

                    # Prefer tiered family if note has none
                    if comp_data["family"] == "unknown" and tiered.get("family", "unknown") != "unknown":
                        comp_data["family"] = tiered["family"]

                    filtered[guid] = comp_data

                # Handle tiered-only GUIDs not in UnifiedStore (orphans)
                unknown_count = 0
                repaired_count = 0
                for guid, comp_data in tiered_components.items():
                    if guid not in filtered and guid not in deprecated_guids:
                        if guid not in all_raw_guids:
                            unknown_count += 1
                            if self.orphan_mode == self.ORPHAN_MODE_STRICT:
                                logger.warning(f"Strict mode: rejecting orphan GUID {guid}")
                            elif self.orphan_mode == self.ORPHAN_MODE_REPAIR:
                                # Create a minimal note in UnifiedStore
                                try:
                                    from .knowledge_note import KnowledgeNote
                                    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                                    note = KnowledgeNote(
                                        note_id=f"repair_{guid[:8]}",
                                        note_type="component",
                                        name=comp_data.get("name", "Unknown"),
                                        brief=comp_data.get("quick", "Repaired from tiered_knowledge"),
                                        created=now,
                                        type_data={
                                            "guid": guid,
                                            "category": comp_data.get("family", "unknown"),
                                            "inputs": comp_data.get("params", {}).get("inputs", {}),
                                            "outputs": comp_data.get("params", {}).get("outputs", {}),
                                        },
                                    )
                                    store.add(note, skip_evolution=True)
                                    filtered[guid] = comp_data
                                    repaired_count += 1
                                    logger.info(f"Repair mode: created note for orphan GUID {guid}")
                                except Exception as e:
                                    logger.warning(f"Repair failed for orphan GUID {guid}: {e}")
                                    filtered[guid] = comp_data  # still include on repair failure
                            else:
                                # legacy-include: retain with warning
                                filtered[guid] = comp_data

                self._components = filtered
                self.raw_component_count = len(all_raw_guids) + unknown_count
                self.active_component_count = len(filtered)
                self.deprecated_skipped_count = len(deprecated_guids & set(tiered_components.keys()))
                self.unknown_guid_count = unknown_count

                mode_label = self.orphan_mode
                extra = ""
                if repaired_count:
                    extra = f", {repaired_count} repaired"
                logger.info(
                    f"Loaded {self.active_component_count} components from UnifiedStore "
                    f"({self.deprecated_skipped_count} deprecated skipped, "
                    f"{unknown_count} orphans [{mode_label}]{extra})"
                )
            else:
                # Fallback: load from tiered_knowledge.json only
                self.raw_component_count = len(tiered_components)
                self._components = tiered_components
                self.active_component_count = len(tiered_components)
                self.deprecated_skipped_count = 0
                self.unknown_guid_count = 0
                logger.warning(
                    f"Loaded {self.raw_component_count} components from {self.knowledge_path} "
                    f"(UnifiedStore unavailable, no deprecated filtering)"
                )

        return self._components

    def load_observations(self) -> dict:
        """Load observations from component_observations.json, normalized to GUID keys.

        component_observations.json stores a list of dicts keyed by component name.
        This method groups them by GUID using UnifiedStore's name→GUID resolution,
        so they can be joined with GUID-keyed component data in the DSPy pipeline.
        """
        if self._observations is None:
            if not self.observations_path.exists():
                logger.warning(f"Observations file not found: {self.observations_path}")
                self._observations = {}
                return self._observations

            with open(self.observations_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            raw_observations = data.get("observations", [])

            # Normalize: component_observations.json is a list of
            # {component, observation, impact, resolution, tags, ...}.
            # Group by GUID using UnifiedStore name→GUID resolution.
            try:
                from .unified_store import get_unified_store
                store = get_unified_store()
            except Exception as e:
                logger.warning(f"Could not load UnifiedStore for observation normalization: {e}")
                store = None

            guid_observations: dict[str, list[dict]] = {}

            if isinstance(raw_observations, list):
                # Name→GUID cache to avoid repeated lookups
                name_to_guid_cache: dict[str, str | None] = {}
                for obs in raw_observations:
                    comp_name = obs.get("component", "")
                    if not comp_name:
                        continue

                    # Resolve name → GUID
                    if comp_name not in name_to_guid_cache:
                        guid = None
                        if store:
                            guid = store.resolve_active_component_guid_by_name(comp_name)
                        name_to_guid_cache[comp_name] = guid

                    guid = name_to_guid_cache[comp_name]
                    if guid:
                        guid_observations.setdefault(guid, []).append(obs)
                    # Observations without a matching GUID are dropped
                    # (component may have been deprecated or not yet cataloged)

                resolved = sum(1 for g in name_to_guid_cache.values() if g)
                logger.info(
                    f"Loaded {len(raw_observations)} observations from {self.observations_path}, "
                    f"resolved {resolved}/{len(name_to_guid_cache)} component names to GUIDs, "
                    f"covering {sum(len(v) for v in guid_observations.values())} observations"
                )
            elif isinstance(raw_observations, dict):
                # Legacy format: already GUID-keyed dict
                guid_observations = raw_observations
                logger.info(f"Loaded {len(guid_observations)} GUID-keyed observations (legacy format)")

            self._observations = guid_observations
        return self._observations

    def consolidate_full(self) -> ComponentStructure:
        """Run the full consolidation pipeline.

        Loads components with deprecated filtering (see load_components()),
        then runs the 4-step DSPy pipeline on active components only.

        Returns:
            ComponentStructure with families, shared behaviors, similar pairs, and I/O patterns.
        """
        components = self.load_components()
        observations = self.load_observations()

        if not components:
            logger.warning("No components to consolidate")
            return ComponentStructure()

        logger.info(
            f"Starting consolidation of {len(components)} active components "
            f"(from {self.raw_component_count} raw, {self.deprecated_skipped_count} deprecated skipped)"
        )

        # Step 1: Identify families
        logger.info("Step 1: Identifying component families...")
        families = self._identify_families(components)
        logger.info(f"Identified {len(families)} families")

        # Step 2: Find shared behaviors
        logger.info("Step 2: Finding shared behaviors...")
        shared_behaviors, propagation_candidates = self._find_shared_behaviors(components, families, observations)
        logger.info(f"Found {len(shared_behaviors)} shared behaviors")

        # Step 3: Find similar components
        logger.info("Step 3: Finding similar component pairs...")
        similar_pairs = self._find_similar_components(components, families)
        logger.info(f"Found {len(similar_pairs)} similar pairs")

        # Step 4: Extract I/O patterns
        logger.info("Step 4: Extracting I/O patterns...")
        io_patterns = self._extract_io_patterns(components)
        logger.info(f"Extracted {len(io_patterns)} I/O patterns")

        # Step 5: Build structure
        self._structure = ComponentStructure(
            component_count=len(components),
            consolidation_count=1,
            families=families,
            shared_behaviors=shared_behaviors,
            similar_pairs=similar_pairs,
            io_patterns=io_patterns,
        )

        # Step 5b: Enrich with stable_key metadata from UnifiedStore
        self._structure.component_metadata = self._build_component_metadata(components)

        # Step 6: Save
        self._save_structure()
        logger.info(f"Structure saved to {self.structure_path}")

        # Step 7: Update tiered_knowledge.json with structure info
        updates = self.update_tiered_knowledge()
        logger.info(f"Tiered knowledge updated: {updates}")

        return self._structure

    def _identify_families(self, components: dict) -> dict[str, ComponentFamily]:
        """Identify component families using DSPy with batching.

        Uses existing family hints from tiered_knowledge.json and processes
        components in batches to avoid token limits.
        """
        # First, collect existing family assignments as hints
        existing_families: dict[str, list[str]] = {}  # family_name -> [guids]
        components_needing_family: list[dict] = []

        for guid, comp in components.items():
            params = comp.get("params", {})
            inputs = params.get("inputs", {})
            outputs = params.get("outputs", {})
            gotchas = comp.get("gotchas", [])
            gotcha_count = len(gotchas) if isinstance(gotchas, list) else 0

            existing_family = comp.get("family", "unknown")

            summary = {
                "guid": guid,
                "name": comp.get("name", "Unknown"),
                "family": existing_family,
                "inputs": inputs,
                "outputs": outputs,
                "gotcha_count": gotcha_count,
            }

            # Track existing assignments
            if existing_family and existing_family != "unknown":
                if existing_family not in existing_families:
                    existing_families[existing_family] = []
                existing_families[existing_family].append(guid)
            else:
                components_needing_family.append(summary)

        logger.info(f"Found {len(existing_families)} existing families with {sum(len(v) for v in existing_families.values())} components")
        logger.info(f"Components needing family assignment: {len(components_needing_family)}")

        # Build initial families from existing assignments
        families: dict[str, ComponentFamily] = {}
        for family_name, guids in existing_families.items():
            families[family_name] = ComponentFamily(
                name=family_name,
                description=f"Components in {family_name} category",
                components=guids,
                shared_traits=[],
            )

        # If no components need family assignment, return existing
        if not components_needing_family:
            logger.info("All components already have family assignments")
            return families

        # Process components needing families in batches
        batch_size = self.BATCH_SIZE
        batches = [
            components_needing_family[i:i + batch_size]
            for i in range(0, len(components_needing_family), batch_size)
        ]

        logger.info(f"Processing {len(batches)} batches of {batch_size} components each")

        # Prepare existing families summary for context
        existing_families_context = {
            name: {
                "component_count": len(guids),
                "sample_names": [
                    components.get(g, {}).get("name", "Unknown")
                    for g in guids[:3]  # Show up to 3 sample names
                ]
            }
            for name, guids in existing_families.items()
        }

        for batch_idx, batch in enumerate(batches):
            logger.info(f"Processing family batch {batch_idx + 1}/{len(batches)} ({len(batch)} components)")

            # Add existing families context to help DSPy assign to known families
            batch_with_context = {
                "existing_families": existing_families_context,
                "components_to_assign": batch,
            }

            try:
                result = self.family_identifier(
                    components_json=json.dumps(batch_with_context, indent=2)
                )

                # Parse result
                families_data = self._parse_json_response(result.families_json, "families")

                # Merge batch results into families
                for family_name, data in families_data.items():
                    if family_name not in families:
                        families[family_name] = ComponentFamily(
                            name=family_name,
                            description=data.get("description", ""),
                            components=[],
                            shared_traits=data.get("shared_traits", []),
                        )

                    # Add new components to family
                    new_components = data.get("components", [])
                    families[family_name].components.extend(new_components)

                    # Update description if provided
                    if data.get("description"):
                        families[family_name].description = data.get("description")

            except Exception as e:
                logger.error(f"Error processing family batch {batch_idx + 1}: {e}")
                # Assign remaining components to "unknown" family
                if "unknown" not in families:
                    families["unknown"] = ComponentFamily(
                        name="unknown",
                        description="Components not yet classified",
                        components=[],
                        shared_traits=[],
                    )
                for comp in batch:
                    families["unknown"].components.append(comp["guid"])

        logger.info(f"Family identification complete: {len(families)} families")
        return families

    def _parse_json_response(self, response: str, context: str) -> dict | list:
        """Parse JSON from DSPy response, handling common formatting issues."""
        if not response:
            logger.error(f"Empty response for {context}")
            return {} if context != "similar_pairs" else []

        # Try direct parsing first
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            pass

        # Try stripping markdown code blocks
        cleaned = response.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse {context} JSON: {e}")
            logger.error(f"Raw response (first 500 chars): {response[:500]}")
            return {} if context != "similar_pairs" else []

    def _find_shared_behaviors(
        self,
        components: dict,
        families: dict[str, ComponentFamily],
        observations: dict,
    ) -> tuple[dict[str, SharedBehavior], list[dict]]:
        """Find behaviors shared across components with batching.

        Merges gotchas, errors, AND runtime observations into a single evidence
        payload per component so DSPy can discover cross-component patterns from
        all available evidence.
        """
        # Build evidence for each component: gotchas + errors + observations
        gotcha_data = []
        for guid, comp in components.items():
            comp_gotchas = []
            gotchas_field = comp.get("gotchas", [])
            if isinstance(gotchas_field, list):
                for g in gotchas_field:
                    if isinstance(g, dict):
                        comp_gotchas.append(g.get("text", ""))
                    elif isinstance(g, str):
                        comp_gotchas.append(g)

            errors = comp.get("errors", "")
            if errors:
                comp_gotchas.append(errors)

            # Gather runtime observations for this GUID
            comp_observations = []
            guid_obs = observations.get(guid, [])
            for obs in guid_obs:
                obs_text = obs.get("observation", "")
                resolution = obs.get("resolution", "")
                if obs_text:
                    entry = obs_text
                    if resolution:
                        entry += f" → {resolution}"
                    comp_observations.append(entry)

            # Include component if it has any evidence (gotchas, errors, or observations)
            if comp_gotchas or comp_observations:
                gotcha_data.append({
                    "guid": guid,
                    "name": comp.get("name", "Unknown"),
                    "family": comp.get("family", "unknown"),
                    "gotchas": comp_gotchas,
                    "errors": [errors] if errors else [],
                    "inputs": comp.get("params", {}).get("inputs", {}),
                    "observations": comp_observations,
                })

        logger.info(f"Finding shared behaviors among {len(gotcha_data)} components with gotchas")

        if not gotcha_data:
            return {}, []

        # Prepare compact families summary
        families_summary = {
            name: {"components": f.components[:5], "count": len(f.components)}
            for name, f in families.items()
        }

        # Process in batches
        batch_size = self.BATCH_SIZE * 2  # Larger batches since only components with gotchas
        batches = [
            gotcha_data[i:i + batch_size]
            for i in range(0, len(gotcha_data), batch_size)
        ]

        shared_behaviors: dict[str, SharedBehavior] = {}
        all_propagation: list[dict] = []

        for batch_idx, batch in enumerate(batches):
            logger.info(f"Processing behavior batch {batch_idx + 1}/{len(batches)}")

            try:
                result = self.behavior_finder(
                    components_with_gotchas_json=json.dumps(batch, indent=2),
                    families_json=json.dumps(families_summary, indent=2),
                )

                shared_data = self._parse_json_response(result.shared_behaviors_json, "shared_behaviors")
                propagation = self._parse_json_response(result.propagation_candidates_json, "propagation")

                # Merge results
                for id, data in shared_data.items():
                    if id not in shared_behaviors:
                        shared_behaviors[id] = SharedBehavior(
                            id=id,
                            text=data.get("text", ""),
                            applies_to=data.get("applies_to", []),
                            family=data.get("family"),
                            confidence=data.get("confidence", 1.0),
                        )
                    else:
                        # Merge applies_to lists
                        shared_behaviors[id].applies_to.extend(data.get("applies_to", []))

                if isinstance(propagation, list):
                    all_propagation.extend(propagation)

            except Exception as e:
                logger.error(f"Error processing behavior batch {batch_idx + 1}: {e}")

        logger.info(f"Found {len(shared_behaviors)} shared behaviors")
        return shared_behaviors, all_propagation

    def _find_similar_components(
        self, components: dict, families: dict[str, ComponentFamily]
    ) -> list[SimilarComponentPair]:
        """Find similar component pairs with batching by family."""
        # Group components by family for more targeted similarity search
        family_components: dict[str, list[dict]] = {}

        for guid, comp in components.items():
            params = comp.get("params", {})
            family = comp.get("family", "unknown")

            comp_data = {
                "guid": guid,
                "name": comp.get("name", "Unknown"),
                "inputs": params.get("inputs", {}),
                "outputs": params.get("outputs", {}),
                "description": comp.get("quick", "")[:80],
            }

            if family not in family_components:
                family_components[family] = []
            family_components[family].append(comp_data)

        logger.info(f"Finding similar components across {len(family_components)} families")

        similar_pairs: list[SimilarComponentPair] = []
        seen_pairs: set[tuple[str, str]] = set()

        # First, find similarities within each family (most likely to be similar)
        for family_name, comps in family_components.items():
            if len(comps) < 2:
                continue

            # Process family in batches if large
            batch_size = self.BATCH_SIZE
            if len(comps) <= batch_size:
                batches = [comps]
            else:
                batches = [comps[i:i + batch_size] for i in range(0, len(comps), batch_size)]

            for batch in batches:
                if len(batch) < 2:
                    continue

                try:
                    result = self.similarity_finder(
                        components_with_params_json=json.dumps(batch, indent=2),
                        families_json=json.dumps({family_name: {"components": [c["guid"] for c in batch]}}),
                    )

                    pairs_data = self._parse_json_response(result.similar_pairs_json, "similar_pairs")

                    for data in pairs_data:
                        guid1 = data.get("comp1_guid", "")
                        guid2 = data.get("comp2_guid", "")

                        # Avoid duplicates
                        pair_key = tuple(sorted([guid1, guid2]))
                        if pair_key in seen_pairs or not guid1 or not guid2:
                            continue
                        seen_pairs.add(pair_key)

                        similar_pairs.append(
                            SimilarComponentPair(
                                comp1_guid=guid1,
                                comp2_guid=guid2,
                                similarity_score=data.get("similarity_score", 0.0),
                                shared_io_pattern=data.get("shared_io_pattern", []),
                                reason=data.get("reason", ""),
                            )
                        )

                except Exception as e:
                    logger.error(f"Error finding similar components in family {family_name}: {e}")

        # Cross-family similarity (sample from each family)
        all_families = list(family_components.keys())
        if len(all_families) > 1:
            # Take representative samples from each family
            cross_family_sample = []
            for family_name, comps in family_components.items():
                # Take up to 3 components per family for cross-family comparison
                cross_family_sample.extend(comps[:3])

            if len(cross_family_sample) > self.BATCH_SIZE:
                cross_family_sample = cross_family_sample[:self.BATCH_SIZE]

            if len(cross_family_sample) >= 2:
                try:
                    result = self.similarity_finder(
                        components_with_params_json=json.dumps(cross_family_sample, indent=2),
                        families_json=json.dumps({"cross_family": {"components": [c["guid"] for c in cross_family_sample]}}),
                    )

                    pairs_data = self._parse_json_response(result.similar_pairs_json, "similar_pairs")

                    for data in pairs_data:
                        guid1 = data.get("comp1_guid", "")
                        guid2 = data.get("comp2_guid", "")

                        pair_key = tuple(sorted([guid1, guid2]))
                        if pair_key in seen_pairs or not guid1 or not guid2:
                            continue
                        seen_pairs.add(pair_key)

                        similar_pairs.append(
                            SimilarComponentPair(
                                comp1_guid=guid1,
                                comp2_guid=guid2,
                                similarity_score=data.get("similarity_score", 0.0),
                                shared_io_pattern=data.get("shared_io_pattern", []),
                                reason=data.get("reason", ""),
                            )
                        )

                except Exception as e:
                    logger.error(f"Error finding cross-family similar components: {e}")

        logger.info(f"Found {len(similar_pairs)} similar component pairs")
        return similar_pairs

    def _extract_io_patterns(self, components: dict) -> dict[str, IOPattern]:
        """Extract common I/O parameter patterns with batching."""
        # Prepare param data
        param_data = []
        for guid, comp in components.items():
            params = comp.get("params", {})
            param_data.append({
                "guid": guid,
                "name": comp.get("name", "Unknown"),
                "inputs": params.get("inputs", {}),
                "outputs": params.get("outputs", {}),
            })

        logger.info(f"Extracting I/O patterns from {len(param_data)} components")

        # Process in batches
        batch_size = self.BATCH_SIZE * 2  # Larger batches for simpler I/O extraction
        batches = [
            param_data[i:i + batch_size]
            for i in range(0, len(param_data), batch_size)
        ]

        io_patterns: dict[str, IOPattern] = {}

        for batch_idx, batch in enumerate(batches):
            logger.info(f"Processing I/O pattern batch {batch_idx + 1}/{len(batches)}")

            try:
                result = self.pattern_extractor(
                    components_with_params_json=json.dumps(batch, indent=2)
                )

                patterns_data = self._parse_json_response(result.io_patterns_json, "io_patterns")

                # Merge results
                for name, data in patterns_data.items():
                    if name not in io_patterns:
                        io_patterns[name] = IOPattern(
                            name=name,
                            components=data.get("components", []),
                            typical_type=data.get("typical_type", ""),
                            typical_gotcha=data.get("typical_gotcha"),
                            param_role=data.get("param_role", "input"),
                        )
                    else:
                        # Merge component lists
                        io_patterns[name].components.extend(data.get("components", []))

            except Exception as e:
                logger.error(f"Error processing I/O pattern batch {batch_idx + 1}: {e}")

        logger.info(f"Extracted {len(io_patterns)} I/O patterns")
        return io_patterns

    def _build_component_metadata(self, components: dict) -> dict[str, dict[str, str]]:
        """Build GUID → {name, stable_key} map from UnifiedStore notes.

        Falls back to component names from tiered_knowledge when UnifiedStore
        doesn't have a matching note.
        """
        metadata: dict[str, dict[str, str]] = {}

        # Try UnifiedStore first for stable_key
        guid_to_note: dict[str, Any] = {}
        try:
            from .unified_store import get_unified_store
            store = get_unified_store()
            for note in store.all():
                if note.note_type == "component" and not note.deprecated:
                    td = note.type_data or {}
                    guid = td.get("guid")
                    if guid:
                        guid_to_note[guid] = note
        except Exception as e:
            logger.warning(f"Could not load UnifiedStore for metadata enrichment: {e}")

        for guid in components:
            entry: dict[str, str] = {"guid": guid}

            note = guid_to_note.get(guid)
            if note:
                entry["name"] = note.name or ""
                entry["stable_key"] = (note.type_data or {}).get("stable_key", "")
            else:
                # Fallback to tiered component name
                entry["name"] = components[guid].get("name", "")
                entry["stable_key"] = ""

            metadata[guid] = entry

        return metadata

    def _save_structure(self) -> None:
        """Save structure to JSON file."""
        if self._structure is None:
            raise RuntimeError("No structure to save. Run consolidate_full() first.")

        self._structure.save(self.structure_path)

    def update_tiered_knowledge(self) -> dict:
        """Write consolidation results to UnifiedStore notes AND tiered_knowledge.json.

        Primary target: UnifiedStore notes (type_data["family"], type_data["similar_to"]).
        Secondary target: tiered_knowledge.json (derived cache for legacy readers).

        Returns:
            Dict with update stats
        """
        if self._structure is None:
            return {"error": "No structure loaded. Run consolidate_full() first."}

        # Build guid -> family map
        guid_to_family: dict[str, str] = {}
        for family_name, family in self._structure.families.items():
            for guid in family.components:
                guid_to_family[guid] = family_name

        # Build guid -> similar_to map
        guid_to_similar: dict[str, list[str]] = {}
        for pair in self._structure.similar_pairs:
            guid_to_similar.setdefault(pair.comp1_guid, []).append(pair.comp2_guid)
            guid_to_similar.setdefault(pair.comp2_guid, []).append(pair.comp1_guid)

        updates = {
            "unified_store_updates": 0,
            "tiered_family_updates": 0,
            "tiered_similar_updates": 0,
        }

        # ── Primary: write to UnifiedStore notes ──
        try:
            from .unified_store import get_unified_store
            store = get_unified_store()

            # Build GUID → note mapping (O(n) once)
            guid_to_note = {
                n.type_data.get("guid"): n
                for n in store.all()
                if n.note_type == "component" and n.type_data.get("guid")
            }

            for guid, note in guid_to_note.items():
                changed = False

                if guid in guid_to_family:
                    new_family = guid_to_family[guid]
                    if note.type_data.get("family") != new_family:
                        note.type_data["family"] = new_family
                        changed = True

                # Set similar_to from new map, or clear stale links
                new_similar = guid_to_similar.get(guid, [])
                if note.type_data.get("similar_to") != new_similar:
                    note.type_data["similar_to"] = new_similar
                    changed = True

                if changed:
                    store.update(note)
                    updates["unified_store_updates"] += 1

            logger.info(f"Updated {updates['unified_store_updates']} UnifiedStore notes with consolidation results")
        except Exception as e:
            logger.warning(f"Failed to write consolidation results to UnifiedStore: {e}")

        # ── Secondary: write to tiered_knowledge.json (derived cache) ──
        knowledge_read_path = self.knowledge_path if (not self._uses_default_knowledge_path or self.knowledge_path.exists()) else resolve_readable_knowledge_path("gh", "tiered_knowledge.json")
        if knowledge_read_path.exists():
            try:
                with open(knowledge_read_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                components = data.get("components", {})

                for guid, comp in components.items():
                    if guid in guid_to_family:
                        new_family = guid_to_family[guid]
                        if comp.get("family") != new_family:
                            comp["family"] = new_family
                            updates["tiered_family_updates"] += 1

                    # Set similar_to from new map, or clear stale links
                    new_similar = guid_to_similar.get(guid, [])
                    if comp.get("similar_to") != new_similar:
                        comp["similar_to"] = new_similar
                        updates["tiered_similar_updates"] += 1

                data["components"] = components
                data["last_structure_update"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

                self.knowledge_path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.knowledge_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)

                logger.info(f"Updated tiered_knowledge.json (derived cache): {updates}")
            except Exception as e:
                logger.warning(f"Failed to update tiered_knowledge.json: {e}")

        return updates

    def load_structure(self) -> Optional[ComponentStructure]:
        """Load existing structure from file."""
        if self.structure_path.exists():
            self._structure = ComponentStructure.load(self.structure_path)
            return self._structure
        return None

    def place_new_component(self, guid: str, component_data: dict) -> dict:
        """Place a newly explored component in existing structure.

        Args:
            guid: Component GUID
            component_data: Component info from tiered_knowledge

        Returns:
            Dict with family assignment and similar components
        """
        # Load current structure
        structure = self.load_structure()
        if not structure:
            return {"error": "No structure found. Run consolidate_full() first."}

        # Find best matching family based on params and traits
        params = component_data.get("params", {})
        inputs = params.get("inputs", {})
        outputs = params.get("outputs", {})

        best_family = None
        best_score = 0

        for family_name, family in structure.families.items():
            score = 0

            # Check if similar to existing family members
            for member_guid in family.components:
                if member_guid in self._components:
                    member = self._components[member_guid]
                    member_inputs = member.get("params", {}).get("inputs", {})
                    member_outputs = member.get("params", {}).get("outputs", {})

                    # Score based on shared input types
                    for in_type in inputs.values():
                        if in_type in member_inputs.values():
                            score += 1

                    # Score based on shared output types
                    for out_type in outputs.values():
                        if out_type in member_outputs.values():
                            score += 1

            if score > best_score:
                best_score = score
                best_family = family_name

        # Find similar components
        similar = []
        for pair in structure.similar_pairs:
            if pair.comp1_guid == guid:
                similar.append(pair.comp2_guid)
            elif pair.comp2_guid == guid:
                similar.append(pair.comp1_guid)

        return {
            "guid": guid,
            "suggested_family": best_family or "unknown",
            "match_score": best_score,
            "similar_components": similar,
        }


# =============================================================================
# Convenience Functions
# =============================================================================


def consolidate_gh_components(
    knowledge_path: str | None = None,
    output_path: str | None = None,
    model: str | None = None,
    orphan_mode: str = "legacy-include",
) -> ComponentStructure:
    """Convenience function to run full GH consolidation.

    Args:
        knowledge_path: Path to tiered_knowledge.json
        output_path: Path to save component_structure.json
        model: Anthropic model to use (reads DSPY_MODEL env var if not provided)
        orphan_mode: How to handle GUIDs in tiered but not in UnifiedStore.
            "legacy-include" (default), "strict", or "repair".

    Returns:
        ComponentStructure with all discovered relationships
    """
    # Load environment
    load_dotenv()

    # Configure DSPy
    from rook.learning.dspy_config import configure_dspy
    configure_dspy(model=model, temperature=0.3)

    # Run consolidation
    consolidator = GHConsolidator(knowledge_path, output_path, orphan_mode=orphan_mode)
    return consolidator.consolidate_full()


def query_gh_structure(
    guid: Optional[str] = None,
    family: Optional[str] = None,
    name: Optional[str] = None,
    stable_key: Optional[str] = None,
    structure_path: Optional[str | Path] = None,
) -> dict:
    """Query the component structure by GUID, name, stable_key, or family.

    Args:
        guid: Specific component GUID to query
        family: Family name to query
        name: Component name to query (resolved to GUID via component_metadata)
        stable_key: Stable identity key to query (resolved to GUID via component_metadata)
        structure_path: Override path to component_structure.json (for testing)

    Returns:
        Dict with structure info
    """
    if structure_path is None:
        structure_path = resolve_readable_knowledge_path("gh", "component_structure.json")
    else:
        structure_path = Path(structure_path)

    if not structure_path.exists():
        return {"error": "No structure file found. Run gh_consolidate first."}

    structure = ComponentStructure.load(structure_path)

    result = {
        "version": structure.version,
        "component_count": structure.component_count,
        "consolidation_count": structure.consolidation_count,
        "last_consolidation": structure.last_consolidation,
    }

    # Resolve name or stable_key to GUID using component_metadata
    if not guid and (name or stable_key):
        metadata = structure.component_metadata or {}
        for meta_guid, meta in metadata.items():
            if name and meta.get("name", "").lower() == name.lower():
                guid = meta_guid
                break
            if stable_key and meta.get("stable_key") == stable_key:
                guid = meta_guid
                break
        if not guid:
            query_desc = f"name='{name}'" if name else f"stable_key='{stable_key}'"
            result["error"] = f"No component found for {query_desc}"
            return result

    if guid:
        # Find component in structure
        component_info = {"guid": guid}

        # Enrich with metadata if available
        meta = (structure.component_metadata or {}).get(guid, {})
        if meta.get("name"):
            component_info["name"] = meta["name"]
        if meta.get("stable_key"):
            component_info["stable_key"] = meta["stable_key"]

        # Find family
        for family_name, fam in structure.families.items():
            if guid in fam.components:
                component_info["family"] = family_name
                component_info["family_traits"] = fam.shared_traits
                break

        # Find similar components
        similar = []
        for pair in structure.similar_pairs:
            other_guid = None
            if pair.comp1_guid == guid:
                other_guid = pair.comp2_guid
            elif pair.comp2_guid == guid:
                other_guid = pair.comp1_guid

            if other_guid:
                entry = {
                    "guid": other_guid,
                    "score": pair.similarity_score,
                    "reason": pair.reason,
                }
                # Enrich similar component with name/stable_key
                other_meta = (structure.component_metadata or {}).get(other_guid, {})
                if other_meta.get("name"):
                    entry["name"] = other_meta["name"]
                if other_meta.get("stable_key"):
                    entry["stable_key"] = other_meta["stable_key"]
                similar.append(entry)
        component_info["similar_components"] = similar

        # Find applicable behaviors
        behaviors = []
        for behavior_id, behavior in structure.shared_behaviors.items():
            if guid in behavior.applies_to:
                behaviors.append({
                    "id": behavior_id,
                    "text": behavior.text,
                    "confidence": behavior.confidence,
                })
        component_info["shared_behaviors"] = behaviors

        result["component"] = component_info

    elif family:
        if family in structure.families:
            fam = structure.families[family]
            result["family"] = fam.to_dict()
        else:
            result["error"] = f"Family '{family}' not found"
            result["available_families"] = list(structure.families.keys())
    else:
        # Return overview
        result["families"] = {
            fname: {
                "component_count": len(fam.components),
                "description": fam.description,
            }
            for fname, fam in structure.families.items()
        }
        result["shared_behaviors_count"] = len(structure.shared_behaviors)
        result["similar_pairs_count"] = len(structure.similar_pairs)
        result["io_patterns"] = list(structure.io_patterns.keys())

    return result


if __name__ == "__main__":
    # Run consolidation when executed directly
    import sys

    logging.basicConfig(level=logging.INFO)

    knowledge_path = sys.argv[1] if len(sys.argv) > 1 else None
    structure = consolidate_gh_components(knowledge_path)

    print(f"\nConsolidation complete!")
    print(f"  Families: {len(structure.families)}")
    print(f"  Shared Behaviors: {len(structure.shared_behaviors)}")
    print(f"  Similar Pairs: {len(structure.similar_pairs)}")
    print(f"  I/O Patterns: {len(structure.io_patterns)}")
