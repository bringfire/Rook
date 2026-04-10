"""Knowledge graph exporter for the WebUI visualizer.

Walks the UnifiedStore and produces normalized JSON payloads matching
the ``/knowledge/graph`` and ``/knowledge/note/{id}`` contracts defined
in the knowledge-graph-visualizer spec.
"""
from datetime import datetime, timezone
from typing import Optional

from ...learning.unified_store import UnifiedStore


def build_knowledge_graph_payload(store: UnifiedStore) -> dict:
    """Build the full graph payload for ``GET /knowledge/graph``.

    Rules:
    - Exclude deprecated notes
    - Drop edges whose source or target is missing after filtering
    - Deduplicate edges (same source→target)
    - Compute inDegree, outDegree, degree per node
    """
    all_notes = store.all()

    # Filter to active notes only
    active = [n for n in all_notes if not n.deprecated]
    active_ids = {n.note_id for n in active}
    deprecated_count = len(all_notes) - len(active)

    # Build edges: one directed edge per link, deduplicated
    edges = []
    edge_set: set[tuple[str, str]] = set()
    dangling_count = 0

    # Degree tracking
    out_degree: dict[str, int] = {n.note_id: 0 for n in active}
    in_degree: dict[str, int] = {n.note_id: 0 for n in active}

    for note in active:
        for target_id in note.links:
            if target_id not in active_ids:
                dangling_count += 1
                continue

            edge_key = (note.note_id, target_id)
            if edge_key in edge_set:
                continue
            edge_set.add(edge_key)

            edges.append({
                "id": f"{note.note_id}->{target_id}",
                "source": note.note_id,
                "target": target_id,
                "linkType": "related",
            })

            out_degree[note.note_id] = out_degree.get(note.note_id, 0) + 1
            in_degree[target_id] = in_degree.get(target_id, 0) + 1

    # Build nodes
    nodes = []
    for note in active:
        od = out_degree.get(note.note_id, 0)
        ind = in_degree.get(note.note_id, 0)

        node: dict = {
            "id": note.note_id,
            "label": note.name,
            "noteType": note.note_type,
            "category": note.category,
            "tags": note.tags,
            "components": note.components,
            "brief": note.brief,
            "deprecated": False,
            "created": note.created,
            "outDegree": od,
            "inDegree": ind,
            "degree": od + ind,
        }

        # Optional: componentGuid for component notes
        if note.note_type == "component":
            guid = (note.type_data or {}).get("guid")
            node["componentGuid"] = guid
        else:
            node["componentGuid"] = None

        nodes.append(node)

    # Sort for deterministic output (spec requirement).
    nodes.sort(key=lambda n: n["id"])
    edges.sort(key=lambda e: (e["source"], e["target"]))

    return {
        "meta": {
            "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source": "UnifiedStore",
            "noteCount": len(nodes),
            "edgeCount": len(edges),
            "excludedDeprecatedCount": deprecated_count,
            "excludedDanglingEdgeCount": dangling_count,
        },
        "nodes": nodes,
        "edges": edges,
    }


def build_note_detail_payload(
    store: UnifiedStore, note_id: str
) -> Optional[dict]:
    """Build the note detail payload for ``GET /knowledge/note/{id}``.

    Returns None if the note does not exist.

    Directionality contract (from UnifiedStore.get_related):
    - linksFrom = forward links (note.links)
    - linksTo = backlinks (notes linking TO this note)
    """
    note = store.get(note_id, track_access=False)
    if note is None or note.deprecated:
        return None

    related = store.get_related(note_id)

    return {
        "note": note.to_dict(),
        "related": {
            "linksFrom": related.get("links_from", []),
            "linksTo": related.get("links_to", []),
        },
    }
