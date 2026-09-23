"""GH Component Tiering Pipeline.

Generates tiered knowledge (quick/contexts/errors) for all 924 Grasshopper
components. Modeled on the working CommandTieringSystem in command_consolidator.py.

Data sources (priority order):
1. Notes (922 component notes with type_data.guid) — broad coverage backbone
2. gh_observations.json (9 GUID-keyed investigations) — strongest per-component grounding
3. component_observations.json (443 name-keyed entries) — supplementary, requires normalization

The tiered_knowledge.json file is updated in-place. The GHTieredKnowledge.get()
facade in gh_knowledge.py already returns these tiers — no downstream changes needed.

Usage:
    # Dry run on 5 components
    python -m rook.learning.gh_component_tiering --dry-run 5

    # Single component
    python -m rook.learning.gh_component_tiering --guid adeadd58-4e28-46ed-853a-b590507d892e

    # Full run (all 924 components)
    python -m rook.learning.gh_component_tiering
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Optional

import dspy

# Learning boundary: configure DSPy once, on first import of any module that runs an LM.
from .dspy_config import ensure_configured as _ensure_dspy_configured
_ensure_dspy_configured()
from dotenv import load_dotenv
from ..runtime_paths import resolve_readable_knowledge_path, resolve_writable_knowledge_path

logger = logging.getLogger(__name__)

# ─── Paths ────────────────────────────────────────────────────────────────────

TIERED_KNOWLEDGE_READ_PATH = resolve_readable_knowledge_path("gh", "tiered_knowledge.json")
TIERED_KNOWLEDGE_WRITE_PATH = resolve_writable_knowledge_path("gh", "tiered_knowledge.json")
SPARSE_INDEX_PATH = resolve_readable_knowledge_path("gh", "sparse_index.json")
GH_OBSERVATIONS_PATH = resolve_readable_knowledge_path("gh", "gh_observations.json")
COMPONENT_OBSERVATIONS_PATH = resolve_readable_knowledge_path("gh", "component_observations.json")
COMPONENT_STRUCTURE_PATH = resolve_readable_knowledge_path("gh", "component_structure.json")
NOTES_DIR = resolve_readable_knowledge_path("gh", "notes")


# ─── DSPy Signature ──────────────────────────────────────────────────────────

class GenerateGHTiers(dspy.Signature):
    """Generate tiered knowledge for a Grasshopper component.

    You are given real data about a Grasshopper component: its I/O params,
    what family it belongs to, what its neighbor components do, and any
    grounded observations from actual usage.

    Generate concise, actionable tiers. Do NOT invent facts — only
    reference information from the provided inputs. If no observations
    exist, infer likely errors from I/O types and neighbor behavior.
    """

    component_name: str = dspy.InputField(desc="Component name (e.g., 'Loft')")
    component_json: str = dspy.InputField(
        desc="Component data: guid, category, inputs, outputs, description"
    )
    observations_json: str = dspy.InputField(
        desc="JSON array of grounded observations from actual usage (may be empty [])"
    )
    neighbor_summaries: str = dspy.InputField(
        desc="Brief summaries of linked neighbor components"
    )
    family_name: str = dspy.InputField(desc="Component family (e.g., 'surface_ops')")
    family_shared_behaviors: str = dspy.InputField(
        desc="Known shared behaviors/gotchas for this family (may be empty)"
    )

    tiers_json: str = dspy.OutputField(
        desc="""{
    "quick": "<~20 tokens: what it does | critical gotcha or key input constraint>",
    "contexts": {
        "<use_case>": "<~50 tokens: typical wiring, input types, common pattern>"
    },
    "errors": "<~30 tokens: what fails and why, based on observations or I/O constraints>"
}"""
    )


# ─── Token budget limits (2x target = reject threshold) ─────────────────────

TOKEN_LIMITS = {
    "quick": 40,
    "contexts_per_key": 100,
    "errors": 60,
}

# Mechanical quick pattern to detect regurgitation.
# All 920 existing mechanical entries match "Name | Inputs: ... → ..." with the arrow.
# This catches names with digits (Box 2Pt), superscripts (R¹), and other non-alpha chars.
MECHANICAL_QUICK_RE = re.compile(
    r"^.+\|.*\u2192", re.IGNORECASE  # \u2192 = →
)


# ─── Main System ─────────────────────────────────────────────────────────────

class GHComponentTieringSystem:
    """Generates tiered knowledge for all GH components.

    Follows the same pattern as CommandTieringSystem:
    load_data() → gather context per component → DSPy call → validate → write back.
    """

    def __init__(
        self,
        tiered_path: Path | None = None,
        sparse_path: Path | None = None,
        gh_obs_path: Path | None = None,
        comp_obs_path: Path | None = None,
        structure_path: Path | None = None,
        notes_dir: Path | None = None,
    ):
        self._uses_default_tiered_path = tiered_path is None
        self.tiered_path = Path(tiered_path) if tiered_path is not None else TIERED_KNOWLEDGE_WRITE_PATH
        self.sparse_path = Path(sparse_path) if sparse_path is not None else SPARSE_INDEX_PATH
        self.gh_obs_path = Path(gh_obs_path) if gh_obs_path is not None else GH_OBSERVATIONS_PATH
        self.comp_obs_path = Path(comp_obs_path) if comp_obs_path is not None else COMPONENT_OBSERVATIONS_PATH
        self.structure_path = Path(structure_path) if structure_path is not None else COMPONENT_STRUCTURE_PATH
        self.notes_dir = Path(notes_dir) if notes_dir is not None else NOTES_DIR

        # DSPy predictor
        self._tier_generator: Optional[dspy.Predict] = None

        # Loaded data
        self._tiered_data: Optional[dict] = None
        self._components: Optional[dict[str, dict]] = None
        self._sparse_index: Optional[dict] = None
        self._guid_to_info: Optional[dict[str, dict]] = None
        self._name_to_guid: Optional[dict[str, str]] = None
        self._guid_to_note: Optional[dict[str, dict]] = None
        self._deprecated_guids: set[str] = set()  # GUIDs from deprecated notes
        self._gh_observations: Optional[dict[str, list[dict]]] = None
        self._comp_observations: Optional[dict[str, list[dict]]] = None
        self._structure: Optional[dict] = None

        # Stats
        self.stats = {
            "total": 0,
            "with_gh_observations": 0,
            "with_comp_observations": 0,
            "neighbor_only": 0,
            "fallback_mechanical": 0,
            "backfilled": 0,
        }

    @property
    def tier_generator(self) -> dspy.Predict:
        if self._tier_generator is None:
            self._tier_generator = dspy.Predict(GenerateGHTiers)
        return self._tier_generator

    # ─── Data Loading ────────────────────────────────────────────────────

    def load_data(self) -> None:
        """Load all data sources into memory."""
        self._load_tiered_knowledge()
        self._load_sparse_index()
        self._load_notes()
        self._load_gh_observations()
        self._load_component_observations()
        self._load_structure()

        logger.info(
            f"Data loaded: {len(self._components)} tiered components, "
            f"{len(self._guid_to_info)} sparse GUIDs, "
            f"{len(self._guid_to_note)} notes, "
            f"{len(self._gh_observations)} GH observation groups, "
            f"{sum(len(v) for v in self._comp_observations.values())} component observations"
        )

    def _load_tiered_knowledge(self) -> None:
        read_path = self.tiered_path if (not self._uses_default_tiered_path or self.tiered_path.exists()) else TIERED_KNOWLEDGE_READ_PATH
        if not read_path.exists():
            logger.warning(f"Tiered knowledge not found: {self.tiered_path} — starting fresh")
            self._tiered_data = {"version": "1.1", "components": {}}
            self._components = {}
            return
        with open(read_path, "r", encoding="utf-8") as f:
            self._tiered_data = json.load(f)
        self._components = self._tiered_data.get("components", {})
        logger.info(f"Loaded {len(self._components)} tiered components")

    def _load_sparse_index(self) -> None:
        if not self.sparse_path.exists():
            raise FileNotFoundError(
                f"Sparse index not found: {self.sparse_path} — "
                "this file is required as the GUID enumeration source"
            )
        with open(self.sparse_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self._guid_to_info = data.get("guid_to_info", {})
        self._sparse_index = data
        self._build_name_to_guid_index()
        logger.info(f"Loaded sparse index: {len(self._guid_to_info)} GUIDs")

    def _build_name_to_guid_index(self) -> None:
        """Build name→GUID index from sparse_index for component_observations normalization."""
        self._name_to_guid = {}
        for guid, info in self._guid_to_info.items():
            name = info.get("name", "")
            if name:
                # Store lowercase for case-insensitive matching
                self._name_to_guid[name.lower()] = guid
                # Also store nickName if different
                nick = info.get("nickName", "")
                if nick and nick.lower() != name.lower():
                    self._name_to_guid[nick.lower()] = guid

    def _load_notes(self) -> None:
        """Build GUID→note and note_id→note indexes from notes/comp_*.json.

        Deprecated notes are excluded from the active indexes and their GUIDs
        are collected in ``_deprecated_guids`` so ``generate_all_tiers()`` can
        skip them.
        """
        self._guid_to_note = {}
        self._note_id_to_note: dict[str, dict] = {}
        self._deprecated_guids = set()
        if not self.notes_dir.exists():
            logger.warning(f"Notes directory not found: {self.notes_dir}")
            return

        deprecated_count = 0
        for note_path in self.notes_dir.glob("comp_*.json"):
            try:
                with open(note_path, "r", encoding="utf-8") as f:
                    note = json.load(f)

                # Track deprecated GUIDs but exclude from active indexes
                if note.get("deprecated"):
                    guid = note.get("type_data", {}).get("guid")
                    if guid:
                        self._deprecated_guids.add(guid)
                    deprecated_count += 1
                    continue

                note_id = note.get("note_id", "")
                if note_id:
                    self._note_id_to_note[note_id] = note
                guid = note.get("type_data", {}).get("guid")
                if guid:
                    self._guid_to_note[guid] = note
            except Exception as e:
                logger.warning(f"Failed to load note {note_path.name}: {e}")

        logger.info(
            f"Loaded {len(self._guid_to_note)} active notes with GUIDs "
            f"({deprecated_count} deprecated excluded, "
            f"{len(self._deprecated_guids)} deprecated GUIDs tracked)"
        )

    def _load_gh_observations(self) -> None:
        """Load gh_observations.json, indexed by component_guid."""
        self._gh_observations = {}
        if not self.gh_obs_path.exists():
            logger.warning(f"GH observations not found: {self.gh_obs_path}")
            return

        with open(self.gh_obs_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        for obs in data.get("observations", {}).values():
            guid = obs.get("component_guid")
            if guid:
                self._gh_observations.setdefault(guid, []).append(obs)

        logger.info(
            f"Loaded GH observations: {sum(len(v) for v in self._gh_observations.values())} "
            f"entries across {len(self._gh_observations)} components"
        )

    def _load_component_observations(self) -> None:
        """Load component_observations.json, normalize name→GUID.

        Note: Most entries (428/443) are session-level topics like 'gh_execute_intent'
        or 'library_search', not actual component names. Only ~15 entries map to real
        GUIDs. This low normalization rate is expected — component_observations is the
        weakest data source (priority 3).
        """
        self._comp_observations = {}
        if not self.comp_obs_path.exists():
            logger.warning(f"Component observations not found: {self.comp_obs_path}")
            return

        with open(self.comp_obs_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        observations = data if isinstance(data, list) else data.get("observations", [])
        skipped = 0

        for obs in observations:
            # component_observations is name-keyed, normalize to GUID
            comp_name = obs.get("component_name", "") or obs.get("component", "")
            if not comp_name:
                continue
            guid = self._name_to_guid.get(comp_name.lower())
            if guid:
                self._comp_observations.setdefault(guid, []).append(obs)
            else:
                skipped += 1

        normalized = sum(len(v) for v in self._comp_observations.values())
        logger.info(
            f"Normalized component observations: "
            f"{normalized} entries across {len(self._comp_observations)} components "
            f"({skipped} skipped — session-level topics without GUID match)"
        )

    def _load_structure(self) -> None:
        """Load component_structure.json for family info."""
        self._structure = {}
        if not self.structure_path.exists():
            logger.warning(f"Component structure not found: {self.structure_path}")
            return

        with open(self.structure_path, "r", encoding="utf-8") as f:
            self._structure = json.load(f)

        families = self._structure.get("families", {})
        logger.info(f"Loaded component structure: {len(families)} families")

    # ─── Context Gathering ───────────────────────────────────────────────

    def gather_component_context(self, guid: str) -> dict[str, Any]:
        """Merge all data sources for one component.

        Returns a dict with keys ready for the DSPy signature inputs.
        """
        context: dict[str, Any] = {
            "component_name": "",
            "component_json": {},
            "observations": [],
            "neighbor_summaries": [],
            "family_name": "Unknown",
            "family_shared_behaviors": [],
            "has_gh_observations": False,
            "has_comp_observations": False,
        }

        # 1. Tiered entry (name, params, description, family)
        tiered = self._components.get(guid, {})
        sparse_info = self._guid_to_info.get(guid, {})
        name = tiered.get("name") or sparse_info.get("name", "Unknown")
        context["component_name"] = name
        context["component_json"] = {
            "guid": guid,
            "name": name,
            "category": tiered.get("family") or sparse_info.get("family", ""),
            "description": tiered.get("description", ""),
            "params": tiered.get("params", {}),
            "similar_to": tiered.get("similar_to", []),
        }
        context["family_name"] = tiered.get("family") or sparse_info.get("family", "Unknown")

        # 2. Note (brief, solution_principle, links)
        note = self._guid_to_note.get(guid)
        if note:
            context["component_json"]["brief"] = note.get("brief", "")
            context["component_json"]["solution_principle"] = note.get("solution_principle", "")
            context["component_json"]["keywords"] = note.get("keywords", [])
            # Enrich params from note type_data if tiered is sparse
            if not context["component_json"]["params"]:
                td = note.get("type_data", {})
                context["component_json"]["params"] = {
                    "inputs": td.get("inputs", {}),
                    "outputs": td.get("outputs", {}),
                }
            # Category fallback
            if context["component_json"]["category"] == "":
                context["component_json"]["category"] = note.get("category", "")

        # 3. Neighbor summaries (briefs of up to 5 linked notes)
        # Dedup by component name to avoid near-duplicates from link vs similar_to paths
        seen_neighbor_names: set[str] = set()
        neighbor_briefs: list[str] = []

        if note and note.get("links"):
            for link_id in note["links"]:
                if len(neighbor_briefs) >= 5:
                    break
                linked_note = self._note_id_to_note.get(link_id)
                if linked_note:
                    n_name = linked_note.get("name", "?")
                    if n_name not in seen_neighbor_names:
                        seen_neighbor_names.add(n_name)
                        neighbor_briefs.append(
                            f"{n_name}: "
                            f"{linked_note.get('solution_principle') or linked_note.get('brief', '')}"
                        )

        # Also check similar_to GUIDs from tiered/note
        similar_guids = tiered.get("similar_to", [])
        if note:
            similar_guids = list(set(similar_guids + (note.get("type_data", {}).get("similar_to", []))))
        for sim_guid in similar_guids:
            if len(neighbor_briefs) >= 5:
                break
            sim_note = self._guid_to_note.get(sim_guid)
            if sim_note:
                n_name = sim_note.get("name", "?")
                if n_name not in seen_neighbor_names:
                    seen_neighbor_names.add(n_name)
                    neighbor_briefs.append(
                        f"{n_name}: {sim_note.get('solution_principle') or sim_note.get('brief', '')}"
                    )

        context["neighbor_summaries"] = neighbor_briefs

        # 4. GH observations (GUID match) — strongest grounding
        gh_obs = self._gh_observations.get(guid, [])
        if gh_obs:
            context["has_gh_observations"] = True
            for obs in gh_obs:
                context["observations"].append({
                    "source": "investigation",
                    "learned": obs.get("learned", ""),
                    "hypothesis": obs.get("hypothesis", ""),
                    "result_status": obs.get("result", {}).get("status", ""),
                    "errors": obs.get("result", {}).get("errors", []),
                })

        # 5. Component observations (name→GUID normalized)
        comp_obs = self._comp_observations.get(guid, [])
        if comp_obs:
            context["has_comp_observations"] = True
            for obs in comp_obs:
                context["observations"].append({
                    "source": "usage",
                    "tag": obs.get("tag", ""),
                    "detail": obs.get("detail", obs.get("observation", "")),
                })

        # 6. Family shared_behaviors from component_structure.json
        families = self._structure.get("families", {})
        family_data = families.get(context["family_name"], {})
        context["family_shared_behaviors"] = family_data.get("shared_behaviors", [])

        return context

    # ─── Tier Generation ─────────────────────────────────────────────────

    def generate_tiers_for_component(
        self, guid: str, ctx: dict[str, Any] | None = None,
    ) -> Optional[dict]:
        """Generate tiered knowledge for a single component.

        Args:
            guid: Component GUID.
            ctx: Pre-gathered context (avoids redundant gather call in bulk mode).

        Returns dict with quick/contexts/errors keys, or None on failure.
        """
        if ctx is None:
            ctx = self.gather_component_context(guid)

        result = self.tier_generator(
            component_name=ctx["component_name"],
            component_json=json.dumps(ctx["component_json"], indent=2),
            observations_json=json.dumps(ctx["observations"], indent=2),
            neighbor_summaries="\n".join(ctx["neighbor_summaries"]) if ctx["neighbor_summaries"] else "(none)",
            family_name=ctx["family_name"],
            family_shared_behaviors="\n".join(ctx["family_shared_behaviors"]) if ctx["family_shared_behaviors"] else "(none)",
        )

        # Validate
        tiers = self._validate_tiers(ctx["component_name"], result.tiers_json, ctx)
        return tiers

    def _validate_tiers(self, name: str, raw_json: str, ctx: dict) -> Optional[dict]:
        """Validate and clean DSPy output. Returns dict or None on failure."""
        # 1. JSON parse
        try:
            tiers = json.loads(raw_json)
        except json.JSONDecodeError as e:
            logger.warning(f"[{name}] JSON parse failed: {e}")
            return None

        if not isinstance(tiers, dict):
            logger.warning(f"[{name}] Output is not a dict")
            return None

        quick = tiers.get("quick", "")
        contexts = tiers.get("contexts", {})
        errors = tiers.get("errors", "")

        # 2. Regurgitation check — reject if quick matches mechanical pattern
        if MECHANICAL_QUICK_RE.match(quick):
            logger.warning(f"[{name}] Regurgitation detected in quick tier")
            return None

        # 3. Token budget check
        if self._estimate_tokens(quick) > TOKEN_LIMITS["quick"]:
            logger.warning(f"[{name}] Quick tier exceeds {TOKEN_LIMITS['quick']} token limit")
            return None

        if self._estimate_tokens(errors) > TOKEN_LIMITS["errors"]:
            logger.warning(f"[{name}] Errors tier exceeds {TOKEN_LIMITS['errors']} token limit")
            return None

        for key, val in contexts.items():
            if not isinstance(val, str):
                logger.warning(f"[{name}] Context '{key}' is not a string, rejecting")
                return None
            if self._estimate_tokens(val) > TOKEN_LIMITS["contexts_per_key"]:
                logger.warning(f"[{name}] Context '{key}' exceeds {TOKEN_LIMITS['contexts_per_key']} token limit")
                return None

        # 4. Grounding gate — when gh_observations exist (only 3 components),
        # the errors tier MUST reference at least one keyword from the learned facts.
        # This is the strongest data we have; accepting ungrounded output here
        # would repeat the original DSPy garbage problem.
        if ctx.get("has_gh_observations") and errors:
            learned_keywords = set()
            for obs in ctx["observations"]:
                if obs.get("source") == "investigation":
                    for word in obs.get("learned", "").lower().split():
                        if len(word) > 3:
                            learned_keywords.add(word)
            errors_lower = errors.lower()
            overlap = sum(1 for kw in learned_keywords if kw in errors_lower)
            if learned_keywords and overlap == 0:
                logger.warning(
                    f"[{name}] REJECTED — errors tier does not reference any "
                    f"grounded observation keywords ({len(learned_keywords)} available)"
                )
                return None

        return {
            "quick": quick,
            "contexts": contexts if isinstance(contexts, dict) else {},
            "errors": errors,
        }

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Rough token estimation (~4 chars per token)."""
        return len(text) // 4

    # ─── Bulk Generation ─────────────────────────────────────────────────

    def generate_all_tiers(
        self,
        limit: int | None = None,
        target_guid: str | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Generate tiered knowledge for components.

        Args:
            limit: Process only this many components.
            target_guid: Process a single component by GUID.
            dry_run: If True, process components but do NOT write to disk.

        Returns:
            Stats dict with counts.
        """
        self.load_data()

        # Determine which GUIDs to process
        if target_guid:
            if target_guid in self._deprecated_guids:
                logger.warning(
                    f"GUID {target_guid} is deprecated — skipping. "
                    "Use a non-deprecated GUID or remove --guid to process all active components."
                )
                return self.stats
            all_guids = [target_guid]
        else:
            # All sparse GUIDs minus deprecated — this covers the 4 missing
            # from tiered while excluding the ~17 deprecated GUIDs
            all_guids = [
                g for g in self._guid_to_info.keys()
                if g not in self._deprecated_guids
            ]
            if self._deprecated_guids:
                logger.info(
                    f"Filtered {len(self._deprecated_guids)} deprecated GUIDs "
                    f"from enumeration ({len(all_guids)} active remaining)"
                )

        if limit:
            all_guids = all_guids[:limit]

        self.stats["total"] = len(all_guids)
        processed = 0

        for guid in all_guids:
            name = (self._components.get(guid, {}).get("name")
                    or self._guid_to_info.get(guid, {}).get("name", guid[:8]))
            processed += 1
            logger.info(f"[{processed}/{len(all_guids)}] Generating tiers for {name}")

            # Track whether this is a backfill
            is_backfill = guid not in self._components

            # Gather context once — reused for DSPy call, validation, stats, and write
            ctx = self.gather_component_context(guid)

            try:
                tiers = self.generate_tiers_for_component(guid, ctx=ctx)
            except Exception as e:
                logger.error(f"[{name}] DSPy call failed: {e}")
                # Retry once after a brief pause for transient API errors
                time.sleep(2)
                try:
                    tiers = self.generate_tiers_for_component(guid, ctx=ctx)
                    logger.info(f"[{name}] Retry succeeded")
                except Exception as e2:
                    logger.error(f"[{name}] Retry also failed: {e2}")
                    tiers = None

            if tiers is None:
                self.stats["fallback_mechanical"] += 1
                logger.info(f"[{name}] Keeping existing mechanical quick")
                # Still backfill missing entries with mechanical data
                if is_backfill:
                    self._backfill_entry(guid)
                    self.stats["backfilled"] += 1
                continue

            # Classify for stats
            if ctx["has_gh_observations"]:
                self.stats["with_gh_observations"] += 1
            elif ctx["has_comp_observations"]:
                self.stats["with_comp_observations"] += 1
            else:
                self.stats["neighbor_only"] += 1

            if is_backfill:
                self.stats["backfilled"] += 1

            # Write into components dict
            self._write_tiers(guid, tiers, ctx)

        # Save (skip on dry run)
        if dry_run:
            logger.info("DRY RUN — skipping write to disk")
        else:
            self._save_tiered_knowledge()

        logger.info("=" * 60)
        logger.info(f"GH Tiering complete: {self.stats}")
        return self.stats

    def _backfill_entry(self, guid: str) -> None:
        """Create a minimal tiered entry for a GUID missing from tiered_knowledge."""
        info = self._guid_to_info.get(guid, {})
        note = self._guid_to_note.get(guid)

        name = info.get("name", "Unknown")
        family = info.get("family", "")

        # Build mechanical quick from note if available
        if note:
            quick = note.get("brief", f"{name} | GH component")
        else:
            quick = f"{name} | GH component"

        params = {}
        if note:
            td = note.get("type_data", {})
            params = {"inputs": td.get("inputs", {}), "outputs": td.get("outputs", {})}

        self._components[guid] = {
            "name": name,
            "family": family,
            "quick": quick,
            "params": params,
            "description": note.get("solution_principle", "") if note else "",
        }

    def _write_tiers(self, guid: str, tiers: dict, ctx: dict) -> None:
        """Write generated tiers into the components dict."""
        entry = self._components.get(guid, {})

        # Preserve existing fields, overwrite tiers
        entry["quick"] = tiers["quick"]
        entry["contexts"] = tiers["contexts"]
        entry["errors"] = tiers["errors"]

        # Ensure name and family are set
        if not entry.get("name"):
            entry["name"] = ctx["component_name"]
        if not entry.get("family"):
            entry["family"] = ctx["family_name"]
        if not entry.get("params"):
            entry["params"] = ctx["component_json"].get("params", {})
        if not entry.get("description"):
            entry["description"] = ctx["component_json"].get("description", "")

        self._components[guid] = entry

    def _save_tiered_knowledge(self) -> None:
        """Write updated tiered_knowledge.json atomically (write temp, then rename)."""
        self._tiered_data["components"] = self._components
        self.tiered_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.tiered_path.with_suffix(".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(self._tiered_data, f, indent=2, ensure_ascii=False)
        # Atomic rename — prevents corruption on crash/Ctrl+C
        os.replace(str(tmp_path), str(self.tiered_path))
        logger.info(f"Saved {len(self._components)} components to {self.tiered_path}")


# ─── CLI Entry Point ─────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="GH Component Tiering Pipeline")
    parser.add_argument(
        "--dry-run", type=int, metavar="N", default=None,
        help="Process only N components (for testing)",
    )
    parser.add_argument(
        "--guid", type=str, default=None,
        help="Process a single component by GUID",
    )
    parser.add_argument(
        "--model", type=str, default=None,
        help="Override DSPy model (e.g., 'claude-3-5-haiku-latest')",
    )
    parser.add_argument(
        "--temperature", type=float, default=0.3,
        help="LLM temperature (default: 0.3 for consistency)",
    )
    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # Load .env for ANTHROPIC_API_KEY
    load_dotenv(Path(__file__).parent.parent.parent.parent / ".env")

    # Configure DSPy
    from rook.learning.dspy_config import configure_dspy
    configure_dspy(
        model=args.model,
        temperature=args.temperature,
        max_tokens=2048,
    )

    # Run
    system = GHComponentTieringSystem()
    is_dry_run = args.dry_run is not None
    stats = system.generate_all_tiers(
        limit=args.dry_run,
        target_guid=args.guid,
        dry_run=is_dry_run,
    )

    # Print summary
    print("\n" + "=" * 60)
    print("GH Component Tiering Summary")
    print("=" * 60)
    for key, val in stats.items():
        print(f"  {key}: {val}")
    print("=" * 60)


if __name__ == "__main__":
    main()
