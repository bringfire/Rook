"""
Canvas Learner — one-shot knowledge capture from a Grasshopper canvas.

Orchestrates writing to ALL THREE knowledge stores:
1. PatternStore  (knowledge/gh/patterns/)  — recipes + teaching patterns
2. UnifiedStore  (knowledge/gh/notes/)     — component notes with GUIDs
3. SparseIndex   (knowledge/gh/sparse_index.json) — intent→GUID mapping

Usage (from server.py handler):
    from rook.learning.canvas_learner import learn_from_canvas
    result = await learn_from_canvas(call_rhino, port=port, name="...", tags=[...])
"""
import logging
import re
from datetime import datetime
from typing import Any, Callable, Coroutine, Optional
from ..runtime_paths import resolve_readable_knowledge_path

logger = logging.getLogger("rook.canvas_learner")

# Regex for numbered step titles: "1. Build Part", "2b. Connections from Vertex", etc.
_STEP_RE = re.compile(r"^(\d+[a-z]?)\.\s*(.+?)(?:\r?\n|$)", re.IGNORECASE)


def _step_sort_key(step: str | None) -> tuple[int, int, float]:
    """Parse a step label into a sortable tuple.

    "1" → (0, 1, 0),  "2b" → (0, 2, 1),  None → (1, 0, 0)
    Parsed labels sort before unparsed (first element 0 vs 1).
    """
    if step is None:
        return (1, 0, 0.0)  # Unparsed → sort after all parsed steps
    m = re.match(r"^(\d+)([a-z]?)$", step, re.IGNORECASE)
    if m:
        num = int(m.group(1))
        sub = ord(m.group(2).lower()) - ord("a") if m.group(2) else -1
        return (0, num, sub)
    return (1, 0, 0.0)  # Unparsable → treat as unparsed


def _is_shared_runtime_guid(guid: str, name: str) -> bool:
    """Check if a GUID is a shared GhPython runtime GUID already stored under a different name.

    This catches the identity collapse where multiple GhPython components share a single
    runtime GUID (e.g. 410755b1...) but have different proxy GUIDs. Without a proxy GUID
    from the snapshot, we cannot distinguish them, so we skip the write to avoid pollution.
    """
    import json
    if not guid:
        return False

    # Check sparse index
    sparse_path = resolve_readable_knowledge_path("gh", "sparse_index.json")
    try:
        if sparse_path.exists():
            with open(sparse_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            existing = data.get("guid_to_info", {}).get(guid)
            if existing and existing.get("name") != name:
                return True
    except Exception:
        pass

    # Check unified store
    try:
        from .unified_store import get_unified_store
        store = get_unified_store()
        existing_comp = store.get_component_by_guid(guid)
        if existing_comp and existing_comp.get("name") != name:
            return True
    except Exception:
        pass

    return False


async def learn_from_canvas(
    call_rhino: Callable[..., Coroutine[Any, Any, dict]],
    *,
    port: Optional[int] = None,
    name: str = "",
    description: str = "",
    tags: list[str] | None = None,
    skip_recipe: bool = False,
) -> dict[str, Any]:
    """Learn everything from the current GH canvas in one pass.

    Steps:
    1. Take snapshot
    2. Extract + save recipe (unless skip_recipe)
    3. Capture annotation teaching content (Scribbles, unconnected Panels)
    4. Ensure all canvas components are registered in all three stores
       (creates new entries or backfills missing stores for existing ones)

    Args:
        call_rhino: The bridge HTTP caller (async)
        port: Rhino instance port
        name: Optional recipe name override
        description: Optional description override
        tags: Additional tags to apply
        skip_recipe: Skip recipe extraction

    Returns:
        Comprehensive report dict
    """
    tags = tags or []
    report: dict[str, Any] = {
        "recipe": None,
        "patterns": [],
        "components": [],
        "annotations_captured": 0,
        "errors": 0,
        "warnings": [],
    }

    # ── Step 1: Snapshot ─────────────────────────────────────────────
    snapshot_result = await call_rhino(
        "/gh/snapshot", "POST", {"include_data": False}, port=port
    )
    if not snapshot_result.get("success"):
        report["errors"] += 1
        report["warnings"].append(f"Snapshot failed: {snapshot_result}")
        return report

    snapshot_data = snapshot_result.get("data", {})
    components = snapshot_data.get("components", [])

    if not components:
        report["warnings"].append("Canvas is empty — no components found")
        return report

    logger.info(f"Canvas snapshot: {len(components)} components")

    # ── Step 2: Extract annotations (shared by recipe + teaching) ───
    annotations = []
    try:
        annotations = _extract_raw_annotations(snapshot_data)
    except Exception as e:
        report["warnings"].append(f"Annotation extraction failed: {e}")
        logger.error(f"Annotation extraction failed: {e}", exc_info=True)

    # ── Step 3: Extract + save recipe (with embedded curriculum) ─────
    # The recipe's graph["curriculum"] is the AUTHORITATIVE teaching content,
    # co-located with the wiring graph for full context. Queried at depth="full"
    # or via curriculum_summary at depth="context" in gh_query_patterns.
    if not skip_recipe:
        try:
            recipe_info = await _extract_and_save_recipe(
                snapshot_data, annotations=annotations,
                name=name, description=description, extra_tags=tags
            )
            report["recipe"] = recipe_info
        except Exception as e:
            report["errors"] += 1
            report["warnings"].append(f"Recipe extraction failed: {e}")
            logger.error(f"Recipe extraction failed: {e}", exc_info=True)

    # ── Step 4: Save annotations as standalone teaching patterns ─────
    # These are INDEXING AIDS — separately searchable via gh_query_patterns
    # without loading the full recipe graph. Intentionally duplicates the
    # curriculum content in a coarser form for retrieval/discovery.
    try:
        annotation_patterns = _save_teaching_patterns(
            annotations, snapshot_data,
            recipe_name=name, extra_tags=tags
        )
        report["patterns"] = annotation_patterns
        report["annotations_captured"] = len(annotation_patterns)
    except Exception as e:
        report["errors"] += 1
        report["warnings"].append(f"Teaching pattern save failed: {e}")
        logger.error(f"Teaching pattern save failed: {e}", exc_info=True)

    # ── Step 5: Ensure all components registered in all stores ──────
    try:
        comp_results = await _ensure_components_registered(
            call_rhino, snapshot_data, port=port
        )
        report["components"] = comp_results

        # Count partial failures as errors
        for comp in comp_results:
            if not comp.get("saved"):
                report["errors"] += 1
                comp_name = comp.get("name", comp.get("guid", "?"))
                if comp.get("error"):
                    report["warnings"].append(f"Component {comp_name} registration failed: {comp['error']}")
                else:
                    failed = [s for s in ("tiered", "sparse", "unified")
                              if not comp.get(f"saved_{s}")]
                    report["warnings"].append(f"Component {comp_name} partial write: failed stores = {failed}")
    except Exception as e:
        report["errors"] += 1
        report["warnings"].append(f"Component registration failed: {e}")
        logger.error(f"Component registration failed: {e}", exc_info=True)

    # Reload knowledge caches after writes
    try:
        from .gh_knowledge import gh_reload_knowledge
        gh_reload_knowledge()
    except Exception:
        pass

    logger.info(
        f"Canvas learning complete: recipe={'yes' if report['recipe'] else 'no'}, "
        f"annotations={report['annotations_captured']}, "
        f"components={len(report['components'])}, "
        f"errors={report['errors']}"
    )
    return report


def _extract_raw_annotations(snapshot_data: dict) -> list[dict]:
    """Extract annotations from snapshot, sharing between recipe + teaching.

    Calls _extract_annotations_v2 with the correct fallback paths for
    components and flows (raw snapshot vs nested graph).

    Returns:
        List of annotation dicts with keys: panel_id, type, text, pos, nearby.
    """
    from .recipe_extraction import _extract_annotations_v2

    graph = snapshot_data.get("graph", {})
    components = graph.get("components", snapshot_data.get("components", []))
    flows = graph.get("flows", snapshot_data.get("flows", []))

    return _extract_annotations_v2(components, flows)


async def _extract_and_save_recipe(
    snapshot_data: dict,
    *,
    annotations: list[dict] | None = None,
    name: str = "",
    description: str = "",
    extra_tags: list[str] | None = None,
) -> dict:
    """Extract recipe from snapshot, embed curriculum from annotations, save to PatternStore."""
    from .recipe_extraction import extract_recipe
    from .pattern_store import get_pattern_store
    from .pattern_memory import PatternNote
    from datetime import timezone

    extra_tags = extra_tags or []
    annotations = annotations or []

    # Extract draft
    draft = extract_recipe(
        snapshot=snapshot_data,
        source_definition="",
        use_dspy=True,
    )

    # Apply overrides
    recipe_name = name or draft.suggested_name
    if not recipe_name:
        recipe_name = f"canvas_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

    recipe_desc = description or draft.description

    # Merge tags
    all_tags = list(set(draft.detected_tags + extra_tags))

    # ── Build curriculum from annotations ─────────────────────────
    curriculum = _build_curriculum(annotations, snapshot_data)

    # Inject curriculum into graph dict
    graph = draft.graph or {}
    if curriculum:
        graph["curriculum"] = curriculum

    # Create PatternNote
    pattern = PatternNote(
        name=recipe_name,
        pattern_type="recipe",
        solution_brief=recipe_desc,
        components_needed=[
            c.get("name") or c.get("nick") or c.get("type", "")
            for c in draft.components
        ],
        trigger_intents=draft.suggested_intents,
        tags=all_tags,
        wiring=draft.wiring,
        input_structure=draft.input_structure,
        output_type=draft.output_type,
        source_definition="",
        created_from="canvas_learner",
        schema_version=draft.schema_version,
        graph=graph,
    )

    # Save to PatternStore (with A-MEM evolution)
    store = get_pattern_store()
    store.add(pattern)

    logger.info(f"Saved recipe pattern: {pattern.pattern_id} ({recipe_name})")

    return {
        "id": pattern.pattern_id,
        "name": recipe_name,
        "component_count": len(draft.components),
        "tags": all_tags,
        "intents": draft.suggested_intents,
        "curriculum_steps": len(curriculum),
    }


def _build_curriculum(
    annotations: list[dict],
    snapshot_data: dict,
) -> list[dict]:
    """Build ordered curriculum list from annotations for recipe embedding.

    Each curriculum entry has:
    - step: int or str (parsed from "1. Title" format, or positional index)
    - title: str (first line of annotation, cleaned)
    - text: str (full annotation text)
    - nearby_components: list[str] (resolved component names)
    - annotation_type: str ("Scribble", "Panel", "Markup")
    - pos: [x, y] (canvas position)

    Entries are sorted left-to-right by x-position to preserve the
    visual reading order on the Grasshopper canvas.
    """
    if not annotations:
        return []

    # Build ID→name map for resolving nearby component references
    graph = snapshot_data.get("graph", {})
    components = graph.get("components", snapshot_data.get("components", []))
    id_to_name = {
        c.get("id", ""): c.get("name") or c.get("nick") or c.get("type", "")
        for c in components
    }

    curriculum: list[dict] = []

    for ann in annotations:
        text = ann.get("text", "").strip()
        if not text or len(text) < 10:
            continue

        ann_type = ann.get("type", "panel")
        pos = ann.get("pos", [0, 0])

        # Parse step number from text: "1. Build Part" → step=1, title="Build Part"
        first_line = text.split("\n")[0].strip()
        step_match = _STEP_RE.match(first_line)

        if step_match:
            step = step_match.group(1)  # "1", "2b", etc.
            title = step_match.group(2).strip()
        else:
            step = None  # Will assign positional index after sorting
            title = first_line[:80]

        # Resolve nearby IDs to component names
        nearby_ids = ann.get("nearby", [])
        nearby_names = [id_to_name.get(rid, rid) for rid in nearby_ids]

        curriculum.append({
            "step": step,
            "title": title,
            "text": text,
            "nearby_components": nearby_names,
            "annotation_type": ann_type,
            "pos": pos,
        })

    # Sort by parsed step label first (1, 2a, 2b, 3, ...),
    # then fall back to x-position for entries without labels
    curriculum.sort(key=lambda c: (
        _step_sort_key(c["step"]),
        c["pos"][0] if c["pos"] else 0,
    ))

    # Assign positional step numbers where step was not parsed
    for idx, entry in enumerate(curriculum):
        if entry["step"] is None:
            entry["step"] = str(idx + 1)

    logger.info(f"Built curriculum with {len(curriculum)} steps from annotations")
    return curriculum


def _save_teaching_patterns(
    annotations: list[dict],
    snapshot_data: dict,
    *,
    recipe_name: str = "",
    extra_tags: list[str] | None = None,
) -> list[dict]:
    """Save pre-extracted annotations as standalone teaching patterns."""
    from .pattern_store import get_pattern_store
    from .pattern_memory import PatternNote

    extra_tags = extra_tags or []

    if not annotations:
        return []

    # Build ID→name map for resolving nearby component references
    graph = snapshot_data.get("graph", {})
    components = graph.get("components", snapshot_data.get("components", []))
    id_to_name = {
        c.get("id", ""): c.get("name") or c.get("nick") or c.get("type", "")
        for c in components
    }

    store = get_pattern_store()
    saved: list[dict] = []

    for idx, ann in enumerate(annotations):
        text = ann.get("text", "").strip()
        if not text or len(text) < 10:
            continue  # Skip trivially short annotations

        ann_type = ann.get("type", "panel")
        # Derive a teaching pattern name from text content
        first_line = text.split("\n")[0][:60].strip()
        snippet = first_line[:20].strip().replace(" ", "_")
        pattern_name = f"{recipe_name}_teaching_{snippet}" if recipe_name else f"teaching_{first_line[:30]}"

        # Build trigger intents from annotation text words
        words = [w.lower() for w in text.split() if len(w) > 3][:10]
        intents = list(set(words))

        # Resolve nearby IDs to component names
        nearby_ids = ann.get("nearby", [])
        nearby_names = [id_to_name.get(rid, rid) for rid in nearby_ids]

        pattern = PatternNote(
            name=pattern_name,
            pattern_type="struggle",  # Teaching content maps to struggle/insight
            solution_brief=text,
            components_needed=nearby_names,
            trigger_intents=intents,
            tags=["teaching", ann_type.lower()] + extra_tags,
            created_from="canvas_learner_annotation",
        )

        try:
            store.add(pattern, skip_evolution=True)
            saved.append({
                "id": pattern.pattern_id,
                "type": ann_type,
                "text_preview": text[:80],
                "nearby_count": len(ann.get("nearby", [])),
            })
        except ValueError:
            pass  # Duplicate ID — unlikely but safe to skip

    logger.info(f"Saved {len(saved)} teaching patterns from annotations")
    return saved


async def _ensure_components_registered(
    call_rhino: Callable[..., Coroutine[Any, Any, dict]],
    snapshot_data: dict,
    *,
    port: Optional[int] = None,
) -> list[dict]:
    """Ensure all canvas components are registered in all 3 stores.

    Does NOT skip components already in UnifiedStore — gh_build_knowledge()
    handles deduplication internally while still backfilling tiered/sparse
    data for components that were only partially registered before.
    """
    from .gh_knowledge import gh_build_knowledge

    registered: list[dict] = []

    # Collect unique component GUIDs from snapshot
    seen_guids: set[str] = set()
    components_to_explore: list[dict] = []

    for comp in snapshot_data.get("components", []):
        guid = comp.get("componentGuid", "")
        if not guid or guid in seen_guids:
            continue
        seen_guids.add(guid)

        # Skip parameter components (sliders, panels, toggles, etc.)
        if comp.get("is_param", False):
            continue

        # Skip annotation and structural types (never registered as components)
        if comp.get("is_annotation", False) or comp.get("is_placeholder", False):
            continue
        ctype = (comp.get("type") or "").lower()
        if ctype in ("group", "cluster", "scribble", "markup", "broken"):
            continue

        components_to_explore.append(comp)

    if not components_to_explore:
        logger.info("No eligible components to process")
        return []

    # Batch-fetch descriptions for all component GUIDs
    guids_to_fetch = [c.get("componentGuid", "") for c in components_to_explore]
    batch_descriptions: dict[str, dict] = {}
    try:
        batch_resp = await call_rhino(
            "/gh/batch-component-info", "POST",
            {"guids": guids_to_fetch}, port=port
        )
        if batch_resp.get("success"):
            for item in batch_resp.get("data", {}).get("Results", []):
                if not item.get("Error"):
                    item_guid = item.get("Guid", "")
                    batch_descriptions[item_guid] = item
    except Exception as e:
        logger.warning(f"Batch description fetch failed (continuing without): {e}")

    # Register each component via gh_build_knowledge (now writes to all 3 stores)
    for comp in components_to_explore:
        guid = comp.get("componentGuid") or comp.get("guid", "")
        proxy_guid = comp.get("proxyGuid")  # No longer emitted by snapshot; gh_library validation below is the primary path
        comp_name = comp.get("name") or comp.get("type", "Unknown")

        # Validate GUID against gh_library (authoritative proxy.Guid source).
        # This prevents storing wrong GUIDs for GhPython .ghuser components,
        # where componentGuid from snapshot != proxy.Guid needed for CreateInstance.
        if not proxy_guid:
            try:
                lib_resp = await call_rhino(
                    "/gh/library", "GET",
                    {"search": comp_name, "limit": 50, "exact": True},
                    port=port,
                )
                if lib_resp.get("success"):
                    lib_comps = lib_resp.get("data", {}).get("components", [])
                    if len(lib_comps) == 1:
                        lib_guid = lib_comps[0].get("guid", "")
                        if lib_guid and lib_guid.lower() != guid.lower():
                            logger.info(
                                f"gh_library GUID override for {comp_name}: "
                                f"snapshot={guid[:12]}... → library={lib_guid[:12]}..."
                            )
                            proxy_guid = lib_guid
                    elif len(lib_comps) > 1:
                        logger.warning(
                            f"gh_library returned {len(lib_comps)} exact matches "
                            f"for '{comp_name}' — falling back to snapshot GUID"
                        )
            except Exception as e:
                logger.warning(f"gh_library validation failed for {comp_name}: {e}")

        # Guard: skip if this GUID is a shared runtime GUID (GhPython identity collapse)
        if not proxy_guid and _is_shared_runtime_guid(guid, comp_name):
            logger.warning(
                f"Skipping {comp_name}: GUID {guid[:12]}... belongs to "
                f"a different component in stores (shared GhPython runtime GUID)"
            )
            continue

        try:
            # Build component_info dict matching what gh_explore_component sends
            component_info = {
                "name": comp_name,
                "type": comp.get("type", ""),
                "nickName": comp.get("nick") or comp.get("nickName", ""),
                "category": comp.get("category", ""),
                "subCategory": comp.get("subCategory", ""),
                "params": {
                    "inputs": comp.get("inputs", []) if isinstance(comp.get("inputs"), list) else [],
                    "outputs": comp.get("outputs", []) if isinstance(comp.get("outputs"), list) else [],
                },
            }

            # Enrich with batch description data if available
            if guid in batch_descriptions:
                proxy = batch_descriptions[guid]
                component_info["description"] = proxy.get("Description", "")
                # Prefer snapshot category/subCategory; fall back to SDK values
                if not component_info["category"]:
                    component_info["category"] = proxy.get("Category", "")
                if not component_info["subCategory"]:
                    component_info["subCategory"] = proxy.get("SubCategory", "")

            build_result = gh_build_knowledge(
                component_info, component_guid=guid, proxy_guid=proxy_guid, save=True
            )

            entry_info = {
                "guid": guid,
                "name": component_info["name"],
                "note_id": build_result.get("unified_note_id"),
                "family": build_result.get("entry", {}).get("family", ""),
                "saved": build_result.get("saved", False),
                "saved_tiered": build_result.get("saved_tiered", False),
                "saved_sparse": build_result.get("saved_sparse", False),
                "saved_unified": build_result.get("saved_unified", False),
            }
            registered.append(entry_info)

            if not build_result.get("saved"):
                failed = [s for s in ("tiered", "sparse", "unified")
                          if not build_result.get(f"saved_{s}")]
                logger.warning(
                    f"Partial write for {component_info['name']} ({guid}): "
                    f"failed stores = {failed}"
                )

        except Exception as e:
            logger.warning(f"Failed to register component {guid}: {e}")
            registered.append({
                "guid": guid,
                "name": comp.get("name") or comp.get("type", "Unknown"),
                "saved": False,
                "error": str(e),
            })

    successful = sum(1 for r in registered if r.get("saved"))
    logger.info(f"Ensured {successful}/{len(registered)} components in all stores")
    return registered
