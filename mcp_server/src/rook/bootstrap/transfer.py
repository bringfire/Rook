"""
Knowledge Transfer

Handles promotion of validated knowledge from local to canonical graph.
Works with NetworkX-compatible JSON format (nodes/links).
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from ..runtime_paths import resolve_readable_knowledge_path, resolve_writable_knowledge_path

logger = logging.getLogger("rook.transfer")


def _default_local_path() -> Path:
    return resolve_writable_knowledge_path("local.json")


def _default_canonical_path() -> Path:
    return resolve_writable_knowledge_path("canonical.json")


def _default_canonical_read_path() -> Path:
    return resolve_readable_knowledge_path("canonical.json")


TRANSFER_LOG_PATH = resolve_writable_knowledge_path("transfer_log.json")


@dataclass
class TransferResult:
    """Result of a knowledge transfer operation."""
    nodes_transferred: int = 0
    nodes_skipped: int = 0
    nodes_duplicate: int = 0
    links_transferred: int = 0
    links_skipped: int = 0
    timestamp: str = ""
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes_transferred": self.nodes_transferred,
            "nodes_skipped": self.nodes_skipped,
            "nodes_duplicate": self.nodes_duplicate,
            "links_transferred": self.links_transferred,
            "links_skipped": self.links_skipped,
            "timestamp": self.timestamp,
            "errors": self.errors,
        }


class KnowledgeTransfer:
    """
    Manages transfer of validated knowledge from local to canonical graph.

    The knowledge files use NetworkX node_link_data format:
    {
        "directed": true,
        "multigraph": false,
        "graph": {...},
        "nodes": [...],
        "links": [...]
    }

    Node types: intent, action, pattern, antipattern, context
    Link types: solved_by, requires, avoid, when, supersedes

    Workflow:
    1. Review local knowledge (nodes pending validation)
    2. Mark entries as validated
    3. Transfer validated entries to canonical
    4. Optionally clear transferred entries from local
    """

    def __init__(self):
        self.local_path = _default_local_path()
        self.canonical_path = _default_canonical_path()

    def _get_canonical_read_path(self) -> Path:
        """Return the effective canonical read path for the current process."""
        if self.canonical_path.exists():
            return self.canonical_path
        return _default_canonical_read_path()

    def load_local(self) -> dict[str, Any]:
        """Load local knowledge graph."""
        if not self.local_path.exists():
            return self._empty_graph("local")
        try:
            return json.loads(self.local_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse local.json: {e}")
            return self._empty_graph("local")

    def load_canonical(self) -> dict[str, Any]:
        """Load canonical knowledge graph."""
        read_path = self._get_canonical_read_path()
        if not read_path.exists():
            return self._empty_graph("canonical")
        try:
            return json.loads(read_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse canonical.json: {e}")
            return self._empty_graph("canonical")

    def _empty_graph(self, name: str) -> dict[str, Any]:
        """Create an empty graph structure."""
        return {
            "directed": True,
            "multigraph": False,
            "graph": {
                "name": name,
                "version": "0.1.0",
                "created": datetime.now().isoformat(),
                "updated": datetime.now().isoformat(),
            },
            "nodes": [],
            "links": [],
        }

    def save_local(self, data: dict[str, Any]):
        """Save local knowledge graph."""
        data["graph"]["updated"] = datetime.now().isoformat()
        self.local_path.parent.mkdir(parents=True, exist_ok=True)
        self.local_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def save_canonical(self, data: dict[str, Any]):
        """Save canonical knowledge graph."""
        data["graph"]["updated"] = datetime.now().isoformat()
        self.canonical_path.parent.mkdir(parents=True, exist_ok=True)
        self.canonical_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def get_local_summary(self) -> dict[str, Any]:
        """Get summary of local knowledge graph."""
        local = self.load_local()
        nodes = local.get("nodes", [])
        links = local.get("links", [])

        # Count by type
        type_counts = {}
        validated_count = 0
        pending_count = 0

        for node in nodes:
            node_type = node.get("type", "unknown")
            type_counts[node_type] = type_counts.get(node_type, 0) + 1
            if node.get("validated", False):
                validated_count += 1
            else:
                pending_count += 1

        return {
            "total_nodes": len(nodes),
            "total_links": len(links),
            "by_type": type_counts,
            "validated": validated_count,
            "pending": pending_count,
        }

    def get_canonical_summary(self) -> dict[str, Any]:
        """Get summary of canonical knowledge graph."""
        read_path = self._get_canonical_read_path()
        if not read_path.exists():
            return {"exists": False}

        canonical = self.load_canonical()
        nodes = canonical.get("nodes", [])
        links = canonical.get("links", [])

        # Count by type
        type_counts = {}
        for node in nodes:
            node_type = node.get("type", "unknown")
            type_counts[node_type] = type_counts.get(node_type, 0) + 1

        # Get unique tools covered
        tools = set()
        for node in nodes:
            if node.get("type") == "action":
                tools.add(node.get("tool", "unknown"))

        return {
            "exists": True,
            "total_nodes": len(nodes),
            "total_links": len(links),
            "by_type": type_counts,
            "tools_covered": sorted(tools),
            "last_updated": canonical.get("graph", {}).get("updated"),
        }

    def get_pending_review(self) -> dict[str, Any]:
        """Get nodes pending human review."""
        local = self.load_local()
        nodes = local.get("nodes", [])

        pending_patterns = []
        pending_antipatterns = []
        pending_other = []

        for i, node in enumerate(nodes):
            if node.get("validated", False):
                continue

            node_type = node.get("type", "unknown")
            entry = {
                "index": i,
                "id": node.get("id"),
                "type": node_type,
                "note": node.get("note", ""),
                "params": node.get("params"),
                "weight": node.get("weight", 0.5),
            }

            if node_type == "pattern":
                pending_patterns.append(entry)
            elif node_type == "antipattern":
                pending_antipatterns.append(entry)
            else:
                pending_other.append(entry)

        return {
            "patterns": pending_patterns,
            "antipatterns": pending_antipatterns,
            "other": pending_other,
            "total_pending": len(pending_patterns) + len(pending_antipatterns) + len(pending_other),
        }

    def mark_validated(
        self,
        indices: list[int],
        validated_by: str = "human"
    ):
        """Mark specific node indices as validated."""
        local = self.load_local()
        nodes = local.get("nodes", [])

        for i in indices:
            if 0 <= i < len(nodes):
                nodes[i]["validated"] = True
                nodes[i]["validated_by"] = validated_by
                nodes[i]["validated_at"] = datetime.now().isoformat()

        self.save_local(local)

    def mark_all_validated(self, validated_by: str = "human"):
        """Mark all pending nodes as validated."""
        local = self.load_local()

        for node in local.get("nodes", []):
            if not node.get("validated", False):
                node["validated"] = True
                node["validated_by"] = validated_by
                node["validated_at"] = datetime.now().isoformat()

        self.save_local(local)

    def transfer_validated(self, min_weight: float = 0.5) -> TransferResult:
        """
        Transfer validated nodes from local to canonical.

        Args:
            min_weight: Minimum weight threshold for transfer (default 0.5)

        Returns:
            TransferResult with counts and any errors
        """
        local = self.load_local()
        canonical = self.load_canonical()

        result = TransferResult(timestamp=datetime.now().isoformat())

        # Build set of existing canonical node IDs for deduplication
        canonical_ids = {node.get("id") for node in canonical.get("nodes", [])}

        # Build set of existing canonical links for deduplication
        canonical_links = {
            (link.get("source"), link.get("target"), link.get("relation"))
            for link in canonical.get("links", [])
        }

        # Track which local node IDs are being transferred
        transferred_ids = set()

        # Transfer validated nodes
        for node in local.get("nodes", []):
            node_id = node.get("id", "")

            # Skip if not validated
            if not node.get("validated", False):
                result.nodes_skipped += 1
                continue

            # Skip if below weight threshold
            if node.get("weight", 0.5) < min_weight:
                result.nodes_skipped += 1
                continue

            # Skip if already in canonical
            if node_id in canonical_ids:
                result.nodes_duplicate += 1
                continue

            # Create canonical version of node
            canonical_node = {
                "id": node_id.replace("local_", "canonical_"),
                "type": node.get("type"),
                "source": "canonical",
                "transferred_from": "local",
                "transferred_at": result.timestamp,
            }

            # Copy relevant fields based on type
            for field in ["labels", "description", "tool", "params", "note", "weight"]:
                if field in node:
                    canonical_node[field] = node[field]

            # Boost weight slightly for validated patterns
            if canonical_node.get("weight"):
                canonical_node["weight"] = min(1.0, canonical_node["weight"] * 1.1)

            canonical["nodes"].append(canonical_node)
            transferred_ids.add(node_id)
            result.nodes_transferred += 1

        # Transfer links that connect transferred nodes
        for link in local.get("links", []):
            source = link.get("source", "")
            target = link.get("target", "")
            relation = link.get("relation", "")

            # Only transfer if both endpoints are in the transfer set
            if source not in transferred_ids or target not in transferred_ids:
                result.links_skipped += 1
                continue

            # Create canonical version of link
            canonical_source = source.replace("local_", "canonical_")
            canonical_target = target.replace("local_", "canonical_")

            # Check if link already exists
            if (canonical_source, canonical_target, relation) in canonical_links:
                result.links_skipped += 1
                continue

            canonical["links"].append({
                "source": canonical_source,
                "target": canonical_target,
                "relation": relation,
                "weight": link.get("weight", 1.0),
                "transferred_at": result.timestamp,
            })
            result.links_transferred += 1

        # Save updated canonical
        self.save_canonical(canonical)

        # Log transfer
        self._log_transfer(result)

        return result

    def _log_transfer(self, result: TransferResult):
        """Log transfer to transfer log."""
        if TRANSFER_LOG_PATH.exists():
            try:
                log = json.loads(TRANSFER_LOG_PATH.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                log = {"transfers": []}
        else:
            log = {"transfers": []}

        log["transfers"].append(result.to_dict())
        log["last_transfer"] = result.timestamp

        TRANSFER_LOG_PATH.write_text(json.dumps(log, indent=2), encoding="utf-8")

    def clear_transferred(self):
        """Remove transferred (validated) nodes from local graph."""
        local = self.load_local()

        # Keep only non-validated nodes
        remaining_nodes = [
            node for node in local.get("nodes", [])
            if not node.get("validated", False)
        ]

        # Get IDs of remaining nodes
        remaining_ids = {node.get("id") for node in remaining_nodes}

        # Keep only links where both endpoints remain
        remaining_links = [
            link for link in local.get("links", [])
            if link.get("source") in remaining_ids and link.get("target") in remaining_ids
        ]

        local["nodes"] = remaining_nodes
        local["links"] = remaining_links

        self.save_local(local)


def interactive_review():
    """Interactive CLI for reviewing and validating knowledge."""
    transfer = KnowledgeTransfer()

    print("\n" + "=" * 60)
    print("KNOWLEDGE TRANSFER - Interactive Review")
    print("=" * 60)

    # Show summaries
    local_summary = transfer.get_local_summary()
    canonical_summary = transfer.get_canonical_summary()

    print(f"\nLocal Graph: {local_summary['total_nodes']} nodes, {local_summary['total_links']} links")
    print(f"  Validated: {local_summary['validated']}, Pending: {local_summary['pending']}")
    print(f"  By type: {local_summary['by_type']}")

    print(f"\nCanonical Graph: {canonical_summary.get('total_nodes', 0)} nodes, {canonical_summary.get('total_links', 0)} links")
    print(f"  By type: {canonical_summary.get('by_type', {})}")

    # Show pending items
    pending = transfer.get_pending_review()

    print(f"\n--- Pending Patterns ({len(pending['patterns'])}) ---")
    for p in pending["patterns"][:10]:  # Show first 10
        print(f"  [{p['index']}] {p['note'][:60]}..." if len(p.get('note', '')) > 60 else f"  [{p['index']}] {p.get('note', 'no note')}")
    if len(pending["patterns"]) > 10:
        print(f"  ... and {len(pending['patterns']) - 10} more")

    print(f"\n--- Pending Antipatterns ({len(pending['antipatterns'])}) ---")
    for a in pending["antipatterns"][:10]:
        print(f"  [{a['index']}] {a['note'][:60]}..." if len(a.get('note', '')) > 60 else f"  [{a['index']}] {a.get('note', 'no note')}")
    if len(pending["antipatterns"]) > 10:
        print(f"  ... and {len(pending['antipatterns']) - 10} more")

    print(f"\nTotal pending: {pending['total_pending']}")
    print("\nCommands:")
    print("  validate_all  - Mark all as validated")
    print("  validate N    - Mark specific index as validated")
    print("  transfer      - Transfer validated to canonical")
    print("  clear         - Clear transferred from local")
    print("  quit          - Exit")

    return pending


def run_transfer(validate_all: bool = False, min_weight: float = 0.5) -> TransferResult:
    """
    Run the transfer process programmatically.

    Args:
        validate_all: If True, validate all pending before transfer
        min_weight: Minimum weight threshold for transfer

    Returns:
        TransferResult with counts
    """
    transfer = KnowledgeTransfer()

    if validate_all:
        transfer.mark_all_validated(validated_by="auto")

    result = transfer.transfer_validated(min_weight=min_weight)

    print(f"\nTransfer complete:")
    print(f"  Nodes transferred: {result.nodes_transferred}")
    print(f"  Nodes skipped: {result.nodes_skipped}")
    print(f"  Nodes duplicate: {result.nodes_duplicate}")
    print(f"  Links transferred: {result.links_transferred}")
    print(f"  Links skipped: {result.links_skipped}")

    return result


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        if sys.argv[1] == "review":
            interactive_review()
        elif sys.argv[1] == "transfer":
            validate_all = "--validate-all" in sys.argv
            run_transfer(validate_all=validate_all)
        elif sys.argv[1] == "summary":
            transfer = KnowledgeTransfer()
            print("\nLocal:", json.dumps(transfer.get_local_summary(), indent=2))
            print("\nCanonical:", json.dumps(transfer.get_canonical_summary(), indent=2))
        else:
            print("Usage: python -m rook.bootstrap.transfer [review|transfer|summary]")
            print("  review              - Interactive review of pending knowledge")
            print("  transfer            - Transfer validated knowledge to canonical")
            print("  transfer --validate-all - Validate all and transfer")
            print("  summary             - Show knowledge graph summaries")
    else:
        interactive_review()
