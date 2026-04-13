"""Knowledge graph exporter for the WebUI visualizer.

Walks the UnifiedStore and CommandKnowledgeStore to produce normalized
JSON payloads matching the ``/knowledge/graph`` and
``/knowledge/note/{id}`` contracts defined in the knowledge-graph-
visualizer spec.
"""
from datetime import datetime, timezone
from typing import Optional

from ...learning.unified_store import UnifiedStore
from ...learning.command_knowledge_store import CommandKnowledgeStore


def build_knowledge_graph_payload(
    store: UnifiedStore,
    command_store: Optional[CommandKnowledgeStore] = None,
) -> dict:
    """Build the full graph payload for ``GET /knowledge/graph``.

    Rules:
    - Exclude deprecated notes
    - Drop edges whose source or target is missing after filtering
    - Deduplicate edges (same source→target)
    - Compute inDegree, outDegree, degree per node
    - Merge Rhino command nodes/edges when *command_store* is provided
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

    # Build GH nodes
    nodes = []
    for note in active:
        od = out_degree.get(note.note_id, 0)
        ind = in_degree.get(note.note_id, 0)

        node: dict = {
            "id": note.note_id,
            "label": note.name,
            "noteType": note.note_type,
            "source": "gh",
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

    # ── Rhino command nodes + edges ──────────────────────────────
    command_count = 0
    if command_store is not None:
        all_cmds = command_store.get_all()
        cmd_ids = {f"cmd_{name}" for name in all_cmds}
        command_count = len(all_cmds)

        # Degree tracking for commands
        cmd_out: dict[str, int] = {cid: 0 for cid in cmd_ids}
        cmd_in: dict[str, int] = {cid: 0 for cid in cmd_ids}

        # Build internal edges from related_commands
        for cmd_name, cmd in all_cmds.items():
            src_id = f"cmd_{cmd_name}"
            for rel_name in cmd.related_commands:
                # related_commands stores names without dash prefix
                target_id = f"cmd_-{rel_name}" if not rel_name.startswith("-") else f"cmd_{rel_name}"
                if target_id not in cmd_ids:
                    continue
                edge_key = (src_id, target_id)
                if edge_key in edge_set:
                    continue
                edge_set.add(edge_key)

                edges.append({
                    "id": f"{src_id}->{target_id}",
                    "source": src_id,
                    "target": target_id,
                    "linkType": "related",
                })
                cmd_out[src_id] = cmd_out.get(src_id, 0) + 1
                cmd_in[target_id] = cmd_in.get(target_id, 0) + 1

        # Build command nodes
        for cmd_name, cmd in all_cmds.items():
            cid = f"cmd_{cmd_name}"
            od = cmd_out.get(cid, 0)
            ind = cmd_in.get(cid, 0)

            family = command_store.get_family(cmd_name)
            category = family if family else "uncategorized"

            nodes.append({
                "id": cid,
                "label": cmd_name,
                "noteType": "command",
                "source": "rhino",
                "category": category,
                "tags": [],
                "components": [],
                "brief": cmd.description or "",
                "deprecated": False,
                "created": None,
                "outDegree": od,
                "inDegree": ind,
                "degree": od + ind,
                "componentGuid": None,
            })

    # Build similar_to edges (component-only, GUID-based, undirected, deduped).
    # similar_to stores component GUIDs, not note IDs — resolve via map.
    guid_to_note_id: dict[str, str] = {}
    for note in active:
        if note.note_type == "component":
            guid = (note.type_data or {}).get("guid")
            if guid:
                guid_to_note_id[guid] = note.note_id

    similar_edges = []
    similar_pair_set: set[tuple[str, str]] = set()

    for note in active:
        if note.note_type != "component":
            continue
        similar_guids = (note.type_data or {}).get("similar_to", [])
        if not similar_guids:
            continue
        for target_guid in similar_guids:
            target_id = guid_to_note_id.get(target_guid)
            if target_id is None or target_id == note.note_id:
                continue
            # Deduplicate: sort pair alphabetically for undirected edge
            pair = tuple(sorted((note.note_id, target_id)))
            if pair in similar_pair_set:
                continue
            similar_pair_set.add(pair)
            similar_edges.append({
                "id": f"similar:{pair[0]}|{pair[1]}",
                "source": pair[0],
                "target": pair[1],
                "linkType": "similar",
            })

    # Sort for deterministic output (spec requirement).
    nodes.sort(key=lambda n: n["id"])
    edges.sort(key=lambda e: (e["source"], e["target"]))
    similar_edges.sort(key=lambda e: (e["source"], e["target"]))

    return {
        "meta": {
            "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source": "UnifiedStore+CommandKnowledgeStore" if command_count > 0 else "UnifiedStore",
            "noteCount": len(nodes),
            "commandCount": command_count,
            "edgeCount": len(edges),
            "excludedDeprecatedCount": deprecated_count,
            "excludedDanglingEdgeCount": dangling_count,
            "similarEdgeCount": len(similar_edges),
        },
        "nodes": nodes,
        "edges": edges,
        "similarEdges": similar_edges,
    }


def command_to_note_dict(
    cmd: "CommandKnowledge",
    command_store: CommandKnowledgeStore,
) -> dict:
    """Adapt a CommandKnowledge object to the note-detail contract.

    Returns a dict shaped like ``KnowledgeNote.to_dict()`` so the
    frontend ``renderNoteDetail()`` works unchanged.
    """
    cmd_id = f"cmd_{cmd.command}"
    family = command_store.get_family(cmd.command)

    return {
        "note_id": cmd_id,
        "name": cmd.command,
        "note_type": "command",
        "source": "rhino",
        "category": family or "uncategorized",
        "brief": cmd.description or "",
        "context": None,
        "tags": [],
        "components": [],
        "links": [
            f"cmd_-{r}" if not r.startswith("-") else f"cmd_{r}"
            for r in cmd.related_commands
        ],
        "deprecated": False,
        "created": None,
        "solution_principle": None,
        "type_data": {
            "modes": cmd.modes,
            "options": cmd.options,
            "preconditions": cmd.preconditions,
            "gotchas": cmd.gotchas,
        },
    }


def build_command_detail_payload(
    cmd_name: str,
    command_store: CommandKnowledgeStore,
) -> Optional[dict]:
    """Build the note detail payload for a Rhino command.

    Returns None if the command does not exist.
    """
    # Strip the cmd_ prefix to get the actual command name
    actual_name = cmd_name[4:] if cmd_name.startswith("cmd_") else cmd_name
    cmd = command_store.get_command(actual_name)
    if cmd is None:
        return None

    note_dict = command_to_note_dict(cmd, command_store)

    # Build related: linksFrom (outgoing) and linksTo (backlinks)
    all_cmds = command_store.get_all()
    cmd_ids = {f"cmd_{n}" for n in all_cmds}

    links_from = [
        link_id for link_id in note_dict["links"]
        if link_id in cmd_ids
    ]

    links_to = []
    for other_name, other_cmd in all_cmds.items():
        if other_name == actual_name:
            continue
        other_related_ids = [
            f"cmd_-{r}" if not r.startswith("-") else f"cmd_{r}"
            for r in other_cmd.related_commands
        ]
        if note_dict["note_id"] in other_related_ids:
            links_to.append(f"cmd_{other_name}")

    return {
        "note": note_dict,
        "related": {
            "linksFrom": links_from,
            "linksTo": links_to,
        },
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

    note_data = note.to_dict()
    note_data["source"] = "gh"

    return {
        "note": note_data,
        "related": {
            "linksFrom": related.get("links_from", []),
            "linksTo": related.get("links_to", []),
        },
    }
