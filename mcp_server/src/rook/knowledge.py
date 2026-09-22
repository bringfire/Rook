"""
Knowledge Graph module for Rook GraphRAG system.

Provides intent → solution mapping with pattern and antipattern tracking.
Uses NetworkX-compatible JSON format for graph storage and traversal.
Uses MABWiser for adaptive weight learning via Thompson Sampling.

Phase 4 Update: Contextual MAB integration for context-aware pattern ranking.
Phase 5 Update: Tiered knowledge with Claude-controlled depth selection.

Tier System:
    - QUICK (~20 tokens): Essential facts, for Claude who knows the tool
    - CONTEXT (~50 tokens): Specific rules for a usage context
    - ERRORS (~30 tokens): What fails and why, for debugging
    - RAW (~500+ tokens): Full patterns, for deep investigation

Design Principle: Claude decides which tier to request. The system provides
visibility into what's available, Claude makes the call. This leverages
future Claude improvements and assumes falling token costs over time.
"""

import json
import hashlib
import logging
import pickle
from pathlib import Path
from typing import Any, Optional, Literal
from difflib import SequenceMatcher

from .runtime_paths import resolve_readable_knowledge_path, resolve_writable_knowledge_path

logger = logging.getLogger("rook.knowledge")

# Tier type for type hints
TierLevel = Literal["quick", "context", "errors", "raw"]

# Knowledge graph file paths
CANONICAL_PATH = resolve_readable_knowledge_path("canonical.json")
LOCAL_PATH = resolve_writable_knowledge_path("local.json")
MAB_PATH = resolve_writable_knowledge_path("mab_model.pkl")

# Command-specific paths (Phase 3 tiering)
COMMANDS_DIR = resolve_writable_knowledge_path("commands")

# Token estimates per tier (approximate)
TIER_TOKEN_ESTIMATES = {
    "quick": 20,
    "context": 50,
    "errors": 30,
    "raw": 500,  # Can be much higher depending on pattern count
}

# MABWiser integration - graceful fallback if not installed.
#
# Both bandit stacks are imported on first use, not at module import: mabwiser
# pulls in numpy, pandas and scikit-learn (several seconds on a cold disk), and
# this module is imported by the MCP server before it can answer `initialize`.
# The availability flags stay module globals (None = not probed yet) so tests can
# still patch them to force a branch; the loaders bind the imported names into
# module globals so every existing use site below keeps working unchanged.
_mab_available: Optional[bool] = None
_contextual_mab_available: Optional[bool] = None


def _mab_ready() -> bool:
    """Import the context-free bandit on first use and report availability."""
    global _mab_available, MAB, LearningPolicy
    if _mab_available is False:
        return False
    if _mab_available is None or "MAB" not in globals():
        try:
            from mabwiser.mab import MAB, LearningPolicy
            _mab_available = True
        except ImportError:
            _mab_available = False
            logger.warning("MABWiser not installed. Using static weights. Install with: pip install mabwiser")
    return bool(_mab_available)


def _contextual_ready() -> bool:
    """Import the contextual bandit stack (Phase 4) on first use and report availability."""
    global _contextual_mab_available
    global encode_context, ContextHistory, ScalerManager, CONTEXT_HISTORY_PATH, SCALER_PATH
    global ContextualMAB, MABConfig, warm_start_mab, CONTEXTUAL_MAB_PATH
    if _contextual_mab_available is False:
        return False
    if _contextual_mab_available is None or "encode_context" not in globals():
        try:
            from .context import encode_context
            from .context_storage import ContextHistory, ScalerManager, CONTEXT_HISTORY_PATH, SCALER_PATH
            from .contextual_mab import (
                ContextualMAB, MABConfig, warm_start_mab,
                is_mabwiser_available, CONTEXTUAL_MAB_PATH
            )
            available = is_mabwiser_available()
        except ImportError as e:
            logger.warning(f"Contextual MAB not available: {e}")
            available = False
        if _contextual_mab_available is None:
            _contextual_mab_available = available
    return bool(_contextual_mab_available)

# Global instances for contextual MAB (lazy initialized)
_context_history: Optional["ContextHistory"] = None
_scaler: Optional["ScalerManager"] = None
_contextual_mab: Optional["ContextualMAB"] = None

# Phase 5: Retrieval MAB for context selection (lazy initialized)
_retrieval_mab_available = False
_retrieval_mab: Optional["KnowledgeRetrievalMAB"] = None
_pending_queries: dict[str, dict] = {}  # tool -> {context, features, timestamp, intent}
RETRIEVAL_MAB_PATH = resolve_writable_knowledge_path("retrieval_mab.pkl")


def _get_condensed_knowledge_path() -> Path:
    return resolve_readable_knowledge_path("condensed_knowledge.json")


def _get_condensed_command_knowledge_path() -> Path:
    return resolve_readable_knowledge_path("commands", "condensed_command_knowledge.json")


def _get_command_structure_path() -> Path:
    return resolve_readable_knowledge_path("commands", "command_structure.json")

def _lazy_import_retrieval_mab():
    """Lazy import to avoid circular dependency."""
    global _retrieval_mab_available
    try:
        # Import directly from module file to avoid circular import via learning/__init__.py
        from rook.learning import retrieval_mab as rm_module
        return rm_module.KnowledgeRetrievalMAB, rm_module.initialize_retrieval_mab_from_condensed
    except ImportError as e:
        logger.debug(f"Retrieval MAB not available: {e}")
        return None, None


# Command Knowledge Store integration (Phase 6: Unified Knowledge)
_command_knowledge_store: Optional["CommandKnowledgeStore"] = None

def _get_command_knowledge_store():
    """Get or initialize command knowledge store (lazy import to avoid circular dependency)."""
    global _command_knowledge_store
    if _command_knowledge_store is None:
        try:
            from .learning.command_knowledge_store import CommandKnowledgeStore
            _command_knowledge_store = CommandKnowledgeStore()
            logger.debug(f"Loaded command knowledge store with {len(_command_knowledge_store.patterns)} commands")
        except ImportError as e:
            logger.debug(f"Command knowledge store not available: {e}")
            return None
    return _command_knowledge_store


# =============================================================================
# Contextual MAB Initialization Helpers
# =============================================================================

def _get_context_history() -> Optional["ContextHistory"]:
    """Get or initialize context history manager."""
    global _context_history
    if not _contextual_ready():
        return None
    if _context_history is None:
        _context_history = ContextHistory()
    return _context_history


def _get_scaler() -> Optional["ScalerManager"]:
    """Get or initialize scaler manager."""
    global _scaler
    if not _contextual_ready():
        return None
    if _scaler is None:
        _scaler = ScalerManager()
        _scaler.load()  # Load from disk if exists
    return _scaler


def _get_contextual_mab() -> Optional["ContextualMAB"]:
    """Get or initialize contextual MAB."""
    global _contextual_mab
    if not _contextual_ready():
        return None
    if _contextual_mab is None:
        _contextual_mab = ContextualMAB()
        # Try to load from disk
        if CONTEXTUAL_MAB_PATH.exists():
            _contextual_mab.load()
    return _contextual_mab


def _initialize_contextual_mab_from_graph(graph: dict) -> bool:
    """Initialize contextual MAB with patterns from knowledge graph."""
    mab = _get_contextual_mab()
    if mab is None:
        return False

    # Extract pattern IDs from graph (include both patterns and antipatterns)
    pattern_ids = [
        node["id"] for node in graph.get("nodes", [])
        if node.get("type") in ("pattern", "antipattern")
    ]

    if not pattern_ids:
        logger.warning("No patterns found in graph for MAB initialization")
        return False

    logger.info(f"Initializing contextual MAB with {len(pattern_ids)} arms")

    # Initialize MAB with patterns
    if not mab.initialize(pattern_ids):
        return False

    # Try warm start from context history
    history = _get_context_history()
    if history and len(history.get_observations()) >= mab.config.min_observations:
        scaler = _get_scaler()
        if warm_start_mab(mab, history, scaler):
            # Save the fitted model
            mab.save()
            logger.info(f"Contextual MAB warm-started and saved with {len(mab.arms)} arms")
            return True
        else:
            logger.warning("Warm start failed - MAB initialized but not fitted")
            return False
    else:
        logger.warning("Not enough observations for warm start")
        return False


# =============================================================================
# Phase 5: Retrieval MAB Helpers
# =============================================================================

def _get_retrieval_mab() -> Optional["KnowledgeRetrievalMAB"]:
    """Get or initialize the retrieval MAB."""
    global _retrieval_mab, _retrieval_mab_available

    # Lazy import to avoid circular dependency
    KnowledgeRetrievalMAB, initialize_retrieval_mab_from_condensed = _lazy_import_retrieval_mab()
    if KnowledgeRetrievalMAB is None:
        _retrieval_mab_available = False
        return None

    _retrieval_mab_available = True

    if _retrieval_mab is None:
        if RETRIEVAL_MAB_PATH.exists():
            _retrieval_mab = KnowledgeRetrievalMAB.load(RETRIEVAL_MAB_PATH)
        else:
            # Initialize from condensed knowledge
            _retrieval_mab = initialize_retrieval_mab_from_condensed(
                _get_condensed_knowledge_path(), RETRIEVAL_MAB_PATH
            )
    return _retrieval_mab


def _track_query(tool: str, context: str, intent: str, features: Any = None) -> None:
    """Track a query for later feedback."""
    global _pending_queries
    from datetime import datetime
    _pending_queries[tool] = {
        "context": context,
        "features": features,
        "intent": intent,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }
    logger.debug(f"Tracked query for {tool}: context={context}")


def _get_pending_query(tool: str) -> Optional[dict]:
    """Get and clear the pending query for a tool."""
    global _pending_queries
    return _pending_queries.pop(tool, None)


def _update_retrieval_mab(tool: str, context: str, succeeded: bool, features: Any = None) -> bool:
    """Update retrieval MAB with feedback."""
    mab = _get_retrieval_mab()
    if mab is None:
        return False

    arm = f"{tool}:{context}"
    try:
        mab.record_outcome(arm, succeeded, features)
        mab.save(RETRIEVAL_MAB_PATH)
        logger.debug(f"Updated retrieval MAB: {arm} -> {'success' if succeeded else 'failure'}")
        return True
    except Exception as e:
        logger.warning(f"Failed to update retrieval MAB: {e}")
        return False


def load_graph(path: Path) -> dict[str, Any]:
    """Load a knowledge graph from JSON file."""
    if not path.exists():
        return {
            "directed": True,
            "multigraph": False,
            "graph": {"name": "local", "version": "0.1.0"},
            "nodes": [],
            "links": []
        }
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error(f"Failed to load knowledge graph from {path}: {e}")
        return {"directed": True, "multigraph": False, "nodes": [], "links": []}


def save_graph(graph: dict[str, Any], path: Path) -> bool:
    """Save a knowledge graph to JSON file."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(graph, indent=2), encoding="utf-8")
        return True
    except Exception as e:
        logger.error(f"Failed to save knowledge graph to {path}: {e}")
        return False


def load_mab() -> "MAB | None":
    """Load the MAB model from disk, or return None if not available."""
    if not _mab_ready():
        return None
    if not MAB_PATH.exists():
        return None
    try:
        with open(MAB_PATH, 'rb') as f:
            return pickle.load(f)
    except Exception as e:
        logger.error(f"Failed to load MAB model: {e}")
        return None


def save_mab(mab: "MAB") -> bool:
    """Save the MAB model to disk."""
    try:
        MAB_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(MAB_PATH, 'wb') as f:
            pickle.dump(mab, f)
        return True
    except Exception as e:
        logger.error(f"Failed to save MAB model: {e}")
        return False


def merge_graphs(canonical: dict, local: dict) -> dict:
    """Merge local graph into canonical, with local taking precedence."""
    merged = {
        "directed": True,
        "multigraph": False,
        "graph": canonical.get("graph", {}),
        "nodes": [],
        "links": []
    }

    # Index nodes by ID
    node_index = {}
    for node in canonical.get("nodes", []):
        node_index[node["id"]] = node.copy()
    for node in local.get("nodes", []):
        # Local overrides canonical
        node_index[node["id"]] = node.copy()

    merged["nodes"] = list(node_index.values())

    # Index links by source-target-relation tuple
    link_index = {}
    for link in canonical.get("links", []):
        key = (link["source"], link["target"], link["relation"])
        link_index[key] = link.copy()
    for link in local.get("links", []):
        key = (link["source"], link["target"], link["relation"])
        link_index[key] = link.copy()

    merged["links"] = list(link_index.values())

    return merged


def similarity(s1: str, s2: str) -> float:
    """Calculate string similarity ratio."""
    return SequenceMatcher(None, s1.lower(), s2.lower()).ratio()


def match_intent(intent: str, labels: list[str], threshold: float = 0.5) -> float:
    """Check if intent matches any of the labels, return max similarity.

    Matching rules:
    1. Full intent contained in label (label is more specific) -> 1.0
    2. Full label contained in intent AND label has multiple words -> 0.95
       (prevents single-word labels like "sphere" from matching everything)
    3. Fuzzy similarity match -> use ratio if above threshold
    """
    intent_lower = intent.lower()
    max_sim = 0.0

    for label in labels:
        label_lower = label.lower()
        label_word_count = len(label_lower.split())

        # Full intent is contained in label (label is more specific/detailed)
        if intent_lower in label_lower:
            return 1.0

        # Label contained in intent - only count if label has 2+ words
        # This prevents single-word labels like "sphere" from matching "split sphere..."
        if label_lower in intent_lower and label_word_count >= 2:
            return 0.95

        # Fuzzy match - use similarity ratio
        sim = similarity(intent, label)
        max_sim = max(max_sim, sim)

    return max_sim if max_sim >= threshold else 0.0


def query_knowledge(
    intent: str | None = None,
    tool: str | None = None,
    params: dict | None = None,
    include_context_score: bool = False
) -> dict[str, Any]:
    """
    Query the knowledge graph for relevant patterns.

    Args:
        intent: Natural language description of what user wants
        tool: Optional specific MCP tool name to get patterns for
        params: Optional tool parameters for context extraction (Phase 4)
        include_context_score: If True, include MAB scores in response (Phase 4)

    Returns:
        Terse structured response with patterns and antipatterns
    """
    # Load and merge graphs
    canonical = load_graph(CANONICAL_PATH)
    local = load_graph(LOCAL_PATH)
    graph = merge_graphs(canonical, local)

    # Build indexes
    nodes_by_id = {n["id"]: n for n in graph.get("nodes", [])}
    links_by_source = {}
    for link in graph.get("links", []):
        src = link["source"]
        if src not in links_by_source:
            links_by_source[src] = []
        links_by_source[src].append(link)

    result = {
        "patterns": [],
        "avoid": [],
        "confidence": 0.0
    }

    # Track matched actions with their edge weights (action_id -> max_weight)
    matched_actions: dict[str, float] = {}

    # Match by intent if provided - find the BEST match, not all matches
    if intent:
        intent_matches = []
        for node in graph.get("nodes", []):
            if node.get("type") != "intent":
                continue
            labels = node.get("labels", [])
            match_score = match_intent(intent, labels)
            if match_score > 0:
                # Calculate specificity: more labels matched = more specific
                specificity = sum(1 for label in labels if label.lower() in intent.lower())
                intent_matches.append((node, match_score, specificity))

        # Sort by match score first, then specificity
        intent_matches.sort(key=lambda x: (x[1], x[2]), reverse=True)

        # Only use the best matching intent(s) - use a threshold to filter similar scores
        if intent_matches:
            best_score = intent_matches[0][1]
            # Include intents within 0.15 of the best score, or anything above 0.75
            # This allows semantically similar intents to contribute their action paths
            score_threshold = max(best_score - 0.15, 0.75)
            logger.debug(f"Intent query '{intent}': best_score={best_score:.3f}, threshold={score_threshold:.3f}")
            for node, score, spec in intent_matches:
                if score < score_threshold:
                    break
                logger.debug(f"  Matched intent: {node.get('labels', [])} score={score:.3f}")
                # Traverse to find actions via solved_by edges - track edge weights
                for link in links_by_source.get(node["id"], []):
                    if link["relation"] == "solved_by":
                        action_id = link["target"]
                        edge_weight = link.get("weight", 0.5)
                        # Keep the highest weight if action seen multiple times
                        if action_id not in matched_actions or edge_weight > matched_actions[action_id]:
                            matched_actions[action_id] = edge_weight
                        logger.debug(f"    -> action: {action_id} (edge_weight: {edge_weight:.2f})")
                        result["confidence"] = max(result["confidence"], score)

    # Match by tool directly if provided
    if tool:
        tool_id = f"action:{tool}"  # Use full tool name
        if tool_id in nodes_by_id:
            matched_actions[tool_id] = max(matched_actions.get(tool_id, 0), 1.0)
            result["confidence"] = max(result["confidence"], 1.0)
        # Also try matching by tool property
        for node in graph.get("nodes", []):
            if node.get("type") == "action" and node.get("tool") == tool:
                matched_actions[node["id"]] = max(matched_actions.get(node["id"], 0), 1.0)
                result["confidence"] = max(result["confidence"], 1.0)

    # Collect patterns and antipatterns for matched actions (using dicts to deduplicate)
    # Incorporate edge weights from intent->action into pattern ranking
    pattern_entries = {}
    antipattern_entries = {}

    for action_id, action_edge_weight in matched_actions.items():
        for link in links_by_source.get(action_id, []):
            target_node = nodes_by_id.get(link["target"])
            if not target_node:
                continue

            if link["relation"] == "requires" and target_node.get("type") == "pattern":
                pattern_id = target_node["id"]
                # Combine action edge weight with pattern's static weight
                # action_edge_weight reflects how preferred this action path is
                pattern_static_weight = target_node.get("weight", 0.5)
                combined_weight = action_edge_weight * pattern_static_weight

                # Only add if not already present, or if this path has higher weight
                if pattern_id not in pattern_entries or combined_weight > pattern_entries[pattern_id]["_static_weight"]:
                    pattern_entry = {
                        "id": pattern_id,
                        "params": target_node.get("params", {}),
                        "note": target_node.get("note", ""),
                        "_static_weight": combined_weight,
                        "_action_weight": action_edge_weight  # Track for debugging
                    }
                    if link.get("context"):
                        pattern_entry["when"] = link["context"]
                    pattern_entries[pattern_id] = pattern_entry

            elif link["relation"] == "avoid" and target_node.get("type") == "antipattern":
                anti_id = target_node["id"]
                anti_static_weight = target_node.get("weight", 0.5)
                combined_weight = action_edge_weight * anti_static_weight

                # Only add if not already present, or if this path has higher weight
                if anti_id not in antipattern_entries or combined_weight > antipattern_entries[anti_id]["_static_weight"]:
                    antipattern_entries[anti_id] = {
                        "id": anti_id,
                        "params": target_node.get("params", {}),
                        "reason": target_node.get("reason", ""),
                        "_static_weight": combined_weight
                    }

    # Phase 4: Get contextual MAB expectations if available
    context_vector = None
    contextual_mab_expectations = {}

    if (intent or tool) and _contextual_ready():
        try:
            # Encode context from intent, tool, and params
            context_vector = encode_context(intent or "", tool or "", params or {})

            # Get contextual MAB predictions
            cmab = _get_contextual_mab()
            if cmab is not None and cmab.is_fitted:
                contextual_mab_expectations = cmab.predict_expectations(context_vector)
                logger.debug(f"Contextual MAB expectations for {len(contextual_mab_expectations)} patterns")
        except Exception as e:
            logger.warning(f"Contextual MAB failed, falling back to static: {e}")

    # Fallback to context-free MAB if contextual failed
    mab_expectations = {}
    if not contextual_mab_expectations:
        mab = load_mab()
        if mab is not None:
            try:
                mab_expectations = mab.predict_expectations()
            except Exception as e:
                logger.warning(f"MAB predict_expectations failed: {e}")

    # Build result with combined weights (iterate over deduplicated dicts)
    for pid, entry in pattern_entries.items():
        static_weight = entry.pop("_static_weight")
        pattern_id = entry.pop("id")  # Keep for scoring but don't expose
        entry.pop("_action_weight", None)  # Remove debug field if present

        # Priority: contextual MAB > context-free MAB > static weight
        if pattern_id in contextual_mab_expectations:
            entry["_weight"] = contextual_mab_expectations[pattern_id]
            if include_context_score:
                entry["_context_score"] = contextual_mab_expectations[pattern_id]
        elif pattern_id in mab_expectations:
            entry["_weight"] = mab_expectations[pattern_id]
        else:
            entry["_weight"] = static_weight

        result["patterns"].append(entry)

    for aid, entry in antipattern_entries.items():
        static_weight = entry.pop("_static_weight")
        anti_id = entry.pop("id")

        # For antipatterns, higher MAB weight = more things to avoid
        if anti_id in contextual_mab_expectations:
            entry["_weight"] = contextual_mab_expectations[anti_id]
            if include_context_score:
                entry["_context_score"] = contextual_mab_expectations[anti_id]
        elif anti_id in mab_expectations:
            entry["_weight"] = mab_expectations[anti_id]
        else:
            entry["_weight"] = static_weight

        result["avoid"].append(entry)

    # Sort by weight descending
    result["patterns"].sort(key=lambda p: p.pop("_weight", 0.5), reverse=True)
    result["avoid"].sort(key=lambda a: a.pop("_weight", 0.5), reverse=True)

    # Add context info to result if requested
    if include_context_score and context_vector is not None:
        result["_context"] = {
            "vector_dim": len(context_vector),
            "contextual_mab_used": bool(contextual_mab_expectations)
        }

    return result


def find_similar_intent(intent: str, graph: dict, threshold: float = 0.75) -> tuple[str | None, dict | None]:
    """
    Find an existing intent node that semantically matches the given intent.

    Args:
        intent: The intent string to match
        graph: The knowledge graph to search
        threshold: Minimum similarity score to consider a match

    Returns:
        Tuple of (intent_id, intent_node) if found, (None, None) otherwise
    """
    best_match = None
    best_score = 0.0

    for node in graph.get("nodes", []):
        if node.get("type") != "intent":
            continue
        labels = node.get("labels", [])
        score = match_intent(intent, labels, threshold=threshold)
        if score > best_score:
            best_score = score
            best_match = node

    if best_match and best_score >= threshold:
        return best_match["id"], best_match
    return None, None


def record_knowledge(
    intent: str,
    action: dict[str, Any],
    outcome: str,
    correction_of: dict[str, Any] | None = None,
    context_override: list[float] | None = None
) -> dict[str, Any]:
    """
    Record a learning outcome to the local knowledge graph and update MAB.

    Args:
        intent: What the user wanted to accomplish
        action: The action taken (tool name and params)
        outcome: "success" or "failure"
        correction_of: If this was a correction, what was the failed attempt
        context_override: Optional manual context vector (Phase 4)

    Returns:
        Status of the recording operation
    """
    local = load_graph(LOCAL_PATH)

    # Also load canonical to search for existing intents across both graphs
    canonical = load_graph(CANONICAL_PATH)
    merged = merge_graphs(canonical, local)

    tool = action.get("tool", "unknown")
    params = action.get("params", {})

    # Fix #7: Validate and normalize tool name format
    if tool != "unknown" and not tool.startswith("rhino_"):
        logger.warning(f"Tool name '{tool}' missing 'rhino_' prefix. Consider using full tool name.")

    # Generate IDs - use 12 hex chars (48 bits) for collision resistance (Fix #8)
    action_id = f"action:{tool}"  # Keep full name: action:rhino_create
    pattern_hash = hashlib.md5(json.dumps(params, sort_keys=True).encode()).hexdigest()[:12]
    pattern_id = f"pattern:local_{pattern_hash}"

    # Ensure nodes exist - use mutable set that we update as we add nodes (Fix #3)
    existing_ids = {n["id"] for n in local.get("nodes", [])}

    # Try to find a semantically similar existing intent (search merged graph)
    existing_intent_id, existing_intent_node = find_similar_intent(intent, merged, threshold=0.75)

    if existing_intent_id:
        intent_id = existing_intent_id
        # Add this intent label to the existing node if it's in local graph
        for node in local.get("nodes", []):
            if node["id"] == intent_id:
                if intent.lower() not in node.get("labels", []):
                    node["labels"].append(intent.lower())
                break
        logger.debug(f"Reusing existing intent: {intent_id}")
    else:
        # Create new intent ID
        intent_hash = hashlib.md5(intent.lower().encode()).hexdigest()[:12]
        intent_id = f"intent:local_{intent_hash}"
        logger.debug(f"Creating new intent: {intent_id}")

    mab_updated = False
    antipattern_id = None
    intent_reused = existing_intent_id is not None

    if outcome == "success":
        # Create pattern node if new
        if pattern_id not in existing_ids:
            pattern_node = {
                "id": pattern_id,
                "type": "pattern",
                "params": params,
                "note": f"Successful approach for: {intent[:50]}",
                "weight": 0.7,
                "source": "local"
            }
            local["nodes"].append(pattern_node)
            existing_ids.add(pattern_id)  # Fix #3: Track added node

        # Create action node if new - this links patterns to tools for coverage tracking
        if action_id not in existing_ids:
            action_node = {
                "id": action_id,
                "type": "action",
                "tool": tool,
                "description": f"Action for tool: {tool}",
                "source": "local"
            }
            local["nodes"].append(action_node)
            existing_ids.add(action_id)

        # Create intent if new (only if we didn't find a similar existing one)
        if intent_id not in existing_ids:
            intent_node = {
                "id": intent_id,
                "type": "intent",
                "labels": [intent.lower()],
                "description": intent[:100],
                "source": "local"
            }
            local["nodes"].append(intent_node)
            existing_ids.add(intent_id)  # Fix #3: Track added node

        # Add links (check for duplicates) - also need to check merged graph for existing links
        existing_links = {(l["source"], l["target"], l["relation"]) for l in local.get("links", [])}
        merged_links = {(l["source"], l["target"], l["relation"]): l for l in merged.get("links", [])}

        # For solved_by: add new link or boost weight if link exists
        link_key = (intent_id, action_id, "solved_by")
        if link_key not in existing_links:
            # Check if this link exists in merged (canonical) graph
            if link_key in merged_links:
                # Boost weight of existing link by copying to local with higher weight
                existing_weight = merged_links[link_key].get("weight", 0.7)
                new_weight = min(existing_weight + 0.1, 1.0)  # Boost by 0.1, cap at 1.0
                local["links"].append({
                    "source": intent_id,
                    "target": action_id,
                    "relation": "solved_by",
                    "weight": new_weight
                })
                logger.debug(f"Boosted weight for {intent_id} -> {action_id}: {existing_weight:.2f} -> {new_weight:.2f}")
            else:
                # New link - if intent was reused, this is an alternative solution
                # Start with slightly lower weight than existing paths
                initial_weight = 0.6 if intent_reused else 0.7
                local["links"].append({
                    "source": intent_id,
                    "target": action_id,
                    "relation": "solved_by",
                    "weight": initial_weight
                })
                logger.debug(f"New solved_by link: {intent_id} -> {action_id} (weight: {initial_weight})")
        else:
            # Link exists in local - boost its weight
            for link in local["links"]:
                if (link["source"], link["target"], link["relation"]) == link_key:
                    old_weight = link.get("weight", 0.7)
                    link["weight"] = min(old_weight + 0.1, 1.0)
                    logger.debug(f"Boosted local weight: {old_weight:.2f} -> {link['weight']:.2f}")
                    break

        if (action_id, pattern_id, "requires") not in existing_links:
            local["links"].append({
                "source": action_id,
                "target": pattern_id,
                "relation": "requires",
                "weight": 0.7
            })

        # If this corrected a previous failure, record antipattern
        if correction_of:
            failed_params = correction_of.get("params", {})
            anti_hash = hashlib.md5(json.dumps(failed_params, sort_keys=True).encode()).hexdigest()[:12]  # Fix #8
            antipattern_id = f"antipattern:local_{anti_hash}"

            if antipattern_id not in existing_ids:
                anti_node = {
                    "id": antipattern_id,
                    "type": "antipattern",
                    "params": failed_params,
                    "reason": correction_of.get("error", "Did not work"),
                    "weight": 0.8,
                    "source": "local"
                }
                local["nodes"].append(anti_node)
                existing_ids.add(antipattern_id)  # Fix #3: Track added node

            if (action_id, antipattern_id, "avoid") not in existing_links:
                local["links"].append({
                    "source": action_id,
                    "target": antipattern_id,
                    "relation": "avoid",
                    "weight": 0.8
                })

            if (antipattern_id, pattern_id, "corrected_by") not in existing_links:
                local["links"].append({
                    "source": antipattern_id,
                    "target": pattern_id,
                    "relation": "corrected_by",
                    "weight": 1.0
                })

        # Update MAB with success
        if _mab_ready():
            mab = load_mab()
            if mab is None:
                # Create new MAB with this pattern
                mab = MAB([pattern_id], LearningPolicy.ThompsonSampling(), seed=42)
                mab.fit([pattern_id], [1])  # First success
            else:
                # Add arm if new, then update
                if pattern_id not in mab.arms:
                    mab.add_arm(pattern_id)
                mab.partial_fit([pattern_id], [1])  # Record success

            # If there was a correction, record the antipattern failure (Fix #5)
            # Note: For antipatterns, we track them to surface them in "avoid" lists
            # A high MAB weight means "frequently encountered" not "good to use"
            if antipattern_id:
                if antipattern_id not in mab.arms:
                    mab.add_arm(antipattern_id)
                mab.partial_fit([antipattern_id], [1])  # Record observation of this antipattern

            save_mab(mab)
            mab_updated = True

    elif outcome == "failure":
        # Fix #4: Create intent node on failure (same as success)
        if intent_id not in existing_ids:
            intent_node = {
                "id": intent_id,
                "type": "intent",
                "labels": [intent.lower()],
                "description": intent[:100],
                "source": "local"
            }
            local["nodes"].append(intent_node)
            existing_ids.add(intent_id)

        # Record failure - create antipattern
        anti_hash = hashlib.md5(json.dumps(params, sort_keys=True).encode()).hexdigest()[:12]  # Fix #8
        antipattern_id = f"antipattern:local_{anti_hash}"

        if antipattern_id not in existing_ids:
            anti_node = {
                "id": antipattern_id,
                "type": "antipattern",
                "params": params,
                "reason": f"Failed for: {intent[:50]}",
                "weight": 0.8,
                "source": "local"
            }
            local["nodes"].append(anti_node)
            existing_ids.add(antipattern_id)  # Fix #3: Track added node

        existing_links = {(l["source"], l["target"], l["relation"]) for l in local.get("links", [])}

        # Fix #4: Link intent to action (even on failure, so we know what was tried)
        if (intent_id, action_id, "solved_by") not in existing_links:
            local["links"].append({
                "source": intent_id,
                "target": action_id,
                "relation": "solved_by",
                "weight": 0.3  # Lower weight for failed attempts
            })

        if (action_id, antipattern_id, "avoid") not in existing_links:
            local["links"].append({
                "source": action_id,
                "target": antipattern_id,
                "relation": "avoid",
                "weight": 0.8
            })

        # Fix #6: Update MAB with failure and antipattern tracking
        if _mab_ready():
            mab = load_mab()
            if mab is None:
                # Create new MAB with the antipattern
                mab = MAB([antipattern_id], LearningPolicy.ThompsonSampling(), seed=42)
                mab.fit([antipattern_id], [1])  # Record antipattern observation
                mab_updated = True
            else:
                # If this pattern exists, record a failure
                if pattern_id in mab.arms:
                    mab.partial_fit([pattern_id], [0])  # Record failure
                    mab_updated = True
                # Track the antipattern
                if antipattern_id not in mab.arms:
                    mab.add_arm(antipattern_id)
                mab.partial_fit([antipattern_id], [1])  # Record antipattern observation
                mab_updated = True
            save_mab(mab)

    # Save updated graph
    graph_saved = save_graph(local, LOCAL_PATH)

    # Phase 4: Record context observation for contextual MAB
    context_recorded = False
    contextual_mab_updated = False

    if _contextual_ready():
        try:
            # Encode context (use override if provided)
            if context_override is not None:
                context_vector = context_override
            else:
                context_vector = encode_context(intent, tool, params)

            # Record observation in context history
            history = _get_context_history()
            if history is not None:
                # Use pattern_id for success, antipattern_id for failure
                obs_pattern_id = pattern_id if outcome == "success" else antipattern_id
                if obs_pattern_id:
                    history.add_observation(
                        context=context_vector,
                        pattern_id=obs_pattern_id,
                        outcome=outcome,
                        intent=intent,
                        tool=tool,
                        metadata={"params_hash": pattern_hash}
                    )
                    context_recorded = True

            # Update contextual MAB if fitted, or initialize if enough observations
            cmab = _get_contextual_mab()
            if cmab is not None:
                if cmab.is_fitted:
                    # MAB already fitted - do online update
                    reward = 1 if outcome == "success" else 0
                    obs_pattern_id = pattern_id if outcome == "success" else antipattern_id
                    if obs_pattern_id and obs_pattern_id in cmab.arms:
                        cmab.partial_fit(context_vector, obs_pattern_id, reward)
                        cmab.save()
                        contextual_mab_updated = True
                    elif obs_pattern_id:
                        # New pattern - add arm and update
                        cmab.add_arm(obs_pattern_id)
                        cmab.partial_fit(context_vector, obs_pattern_id, reward)
                        cmab.save()
                        contextual_mab_updated = True
                else:
                    # MAB not fitted - check if we have enough observations to initialize
                    if history is not None:
                        obs_count = len(history.get_observations())
                        if obs_count >= cmab.config.min_observations:
                            logger.info(f"Contextual MAB has {obs_count} observations, initializing...")
                            # Load merged graph to get all patterns
                            canonical = load_graph(CANONICAL_PATH)
                            local_graph = load_graph(LOCAL_PATH)
                            merged = merge_graphs(canonical, local_graph)

                            # Initialize from graph patterns
                            if _initialize_contextual_mab_from_graph(merged):
                                contextual_mab_updated = True
                                logger.info("Contextual MAB initialized and warm-started successfully")

        except Exception as e:
            logger.warning(f"Failed to record context observation: {e}")

    # Phase 5: Update retrieval MAB with feedback
    retrieval_mab_updated = False
    pending_query = _get_pending_query(tool)
    if pending_query:
        succeeded = outcome == "success"
        context_used = pending_query.get("context")
        if context_used:
            retrieval_mab_updated = _update_retrieval_mab(
                tool=tool,
                context=context_used,
                succeeded=succeeded,
                features=pending_query.get("features"),
            )
            if retrieval_mab_updated:
                logger.debug(f"Retrieval MAB feedback: {tool}:{context_used} -> {outcome}")

    return {
        "success": graph_saved,
        "message": f"Recorded {outcome} for {tool}",
        "nodes_added": len(local.get("nodes", [])),
        "links_added": len(local.get("links", [])),
        "mab_updated": mab_updated,
        "context_recorded": context_recorded,
        "contextual_mab_updated": contextual_mab_updated,
        "retrieval_mab_updated": retrieval_mab_updated,
    }


# =============================================================================
# Phase 4.3: Introspection Methods
# =============================================================================

def get_pattern_statistics(pattern_id: str | None = None) -> dict[str, Any]:
    """
    Get learning statistics for a pattern or all patterns.

    Args:
        pattern_id: Optional specific pattern ID. If None, returns all.

    Returns:
        Statistics including observation counts, success rates, etc.
    """
    result = {
        "patterns": {},
        "total_observations": 0,
        "contextual_mab_available": _contextual_ready()
    }

    if not _contextual_ready():
        return result

    history = _get_context_history()
    if history is None:
        return result

    observations = history.get_observations()
    result["total_observations"] = len(observations)

    # Group observations by pattern
    pattern_stats: dict[str, dict] = {}
    for obs in observations:
        pid = obs.get("pattern_id", "unknown")

        if pattern_id is not None and pid != pattern_id:
            continue

        if pid not in pattern_stats:
            pattern_stats[pid] = {
                "total": 0,
                "success": 0,
                "failure": 0,
                "last_updated": None
            }

        pattern_stats[pid]["total"] += 1
        if obs.get("outcome") == "success":
            pattern_stats[pid]["success"] += 1
        else:
            pattern_stats[pid]["failure"] += 1

        # Track most recent timestamp
        ts = obs.get("timestamp")
        if ts and (pattern_stats[pid]["last_updated"] is None or
                   ts > pattern_stats[pid]["last_updated"]):
            pattern_stats[pid]["last_updated"] = ts

    # Calculate success rates
    for pid, stats in pattern_stats.items():
        if stats["total"] > 0:
            stats["success_rate"] = round(stats["success"] / stats["total"], 3)
        else:
            stats["success_rate"] = 0.0

    result["patterns"] = pattern_stats
    return result


def explain_recommendation(
    intent: str,
    tool: str,
    params: dict | None = None
) -> dict[str, Any]:
    """
    Explain why patterns were ranked a certain way for given context.

    Args:
        intent: Natural language intent
        tool: MCP tool name
        params: Optional tool parameters

    Returns:
        Explanation including context vector, scores, and reasoning
    """
    result = {
        "intent": intent,
        "tool": tool,
        "context_vector": None,
        "pattern_scores": {},
        "contextual_mab_used": False,
        "reasoning": ""
    }

    if not _contextual_ready():
        result["reasoning"] = "Contextual MAB not available, using static weights"
        return result

    try:
        # Encode context
        context_vector = encode_context(intent, tool, params or {})
        result["context_vector"] = context_vector

        # Get contextual MAB predictions
        cmab = _get_contextual_mab()
        if cmab is not None and cmab.is_fitted:
            expectations = cmab.predict_expectations(context_vector)
            result["pattern_scores"] = expectations
            result["contextual_mab_used"] = True

            # Generate reasoning
            if expectations:
                top_patterns = sorted(
                    expectations.items(),
                    key=lambda x: x[1],
                    reverse=True
                )[:3]
                top_str = ", ".join(f"{p[0]} ({p[1]:.3f})" for p in top_patterns)
                result["reasoning"] = (
                    f"Based on contextual MAB with {len(cmab.arms)} patterns. "
                    f"Top 3 for this context: {top_str}"
                )
            else:
                result["reasoning"] = "Contextual MAB fitted but no expectations returned"
        else:
            result["reasoning"] = (
                "Contextual MAB not yet fitted. "
                "Need more observations for context-aware recommendations."
            )

        # Add similar past contexts info
        history = _get_context_history()
        if history:
            all_obs = history.get_observations(limit=100)
            # Find observations with similar intents
            similar = [
                obs for obs in all_obs
                if similarity(intent, obs.get("intent", "")) > 0.5
            ]
            result["similar_past_contexts"] = len(similar)

    except Exception as e:
        result["reasoning"] = f"Error during explanation: {e}"

    return result


def get_learning_summary() -> dict[str, Any]:
    """
    Get overall learning summary for the knowledge system.

    Returns:
        Summary of knowledge graph, MAB, and context history state
    """
    # Load graphs
    canonical = load_graph(CANONICAL_PATH)
    local = load_graph(LOCAL_PATH)
    graph = merge_graphs(canonical, local)

    # Count node types
    node_counts = {}
    for node in graph.get("nodes", []):
        ntype = node.get("type", "unknown")
        node_counts[ntype] = node_counts.get(ntype, 0) + 1

    result = {
        "knowledge_graph": {
            "total_nodes": len(graph.get("nodes", [])),
            "total_links": len(graph.get("links", [])),
            "node_types": node_counts,
            "canonical_path": str(CANONICAL_PATH),
            "local_path": str(LOCAL_PATH)
        },
        "mab": {
            "available": _mab_ready(),
            "model_path": str(MAB_PATH),
            "model_exists": MAB_PATH.exists()
        },
        "contextual_mab": {
            "available": _contextual_ready(),
            "model_path": str(CONTEXTUAL_MAB_PATH) if _contextual_ready() else None,
            "model_exists": CONTEXTUAL_MAB_PATH.exists() if _contextual_ready() else False,
            "is_fitted": False,
            "num_arms": 0
        },
        "context_history": {
            "available": _contextual_ready(),
            "path": str(CONTEXT_HISTORY_PATH) if _contextual_ready() else None,
            "total_observations": 0
        }
    }

    # Add contextual MAB details
    if _contextual_ready():
        cmab = _get_contextual_mab()
        if cmab is not None:
            result["contextual_mab"]["is_fitted"] = cmab.is_fitted
            result["contextual_mab"]["num_arms"] = len(cmab.arms)

        history = _get_context_history()
        if history is not None:
            result["context_history"]["total_observations"] = len(history.get_observations())

    return result


# =============================================================================
# Phase 5: Tiered Knowledge Query System
# =============================================================================

def _load_condensed_knowledge() -> dict[str, Any]:
    """Load consolidated knowledge from disk."""
    condensed_path = _get_condensed_knowledge_path()
    if not condensed_path.exists():
        return {}
    try:
        with open(condensed_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Failed to load condensed knowledge: {e}")
        return {}


# Cache for condensed command knowledge
_condensed_command_cache: Optional[dict[str, Any]] = None


def invalidate_condensed_command_cache() -> None:
    """Invalidate the condensed command knowledge cache.

    Call this after updating condensed_command_knowledge.json to ensure
    subsequent queries see the new data.
    """
    global _condensed_command_cache
    _condensed_command_cache = None
    logger.debug("Condensed command knowledge cache invalidated")


def _load_condensed_command_knowledge() -> dict[str, Any]:
    """Load condensed command knowledge from disk.

    This is the tiered knowledge generated by Phase 3 CommandTieringSystem.
    Structure:
        {
            "commands": {
                "-Box": {
                    "quick": "...",
                    "contexts": {"default": "...", "center": "...", ...},
                    "errors": "...",
                    "family": "Primitives",
                    "similar_commands": ["-Rectangle"]
                },
                ...
            }
        }
    """
    global _condensed_command_cache

    if _condensed_command_cache is not None:
        return _condensed_command_cache

    condensed_command_path = _get_condensed_command_knowledge_path()
    if not condensed_command_path.exists():
        logger.debug(f"Condensed command knowledge not found at {condensed_command_path}")
        return {}

    try:
        with open(condensed_command_path, "r", encoding="utf-8") as f:
            _condensed_command_cache = json.load(f)
            logger.debug(f"Loaded condensed command knowledge: {_condensed_command_cache.get('command_count', 0)} commands")
            return _condensed_command_cache
    except Exception as e:
        logger.warning(f"Failed to load condensed command knowledge: {e}")
        return {}


def _get_command_tiered_knowledge(
    command_name: str,
    depth: TierLevel = "context",
    context_name: str | None = None,
) -> dict[str, Any] | None:
    """Get tiered knowledge for a specific Rhino command.

    Args:
        command_name: Command name (e.g., "-Box" or "Box")
        depth: Tier to return - "quick", "context", "errors", or "raw"
        context_name: For "context" tier, specific mode to return

    Returns:
        Tiered knowledge dict, or None if not found
    """
    condensed = _load_condensed_command_knowledge()
    commands = condensed.get("commands", {})

    # Normalize command name (add dash if missing)
    if not command_name.startswith("-"):
        command_name = f"-{command_name}"

    cmd_data = commands.get(command_name)
    if not cmd_data:
        return None

    # Build response based on requested tier
    result = {
        "command": command_name,
        "family": cmd_data.get("family", "Unknown"),
        "similar_commands": cmd_data.get("similar_commands", []),
        "tier": depth,
        "source": "consolidated",
    }

    if depth == "quick":
        result["data"] = cmd_data.get("quick", "")
        result["token_estimate"] = cmd_data.get("token_estimate", {}).get("quick", 20)

    elif depth == "context":
        contexts = cmd_data.get("contexts", {})
        result["available_contexts"] = list(contexts.keys())

        if context_name and context_name in contexts:
            # Return specific context
            result["data"] = {context_name: contexts[context_name]}
        elif contexts:
            # Return all contexts (they're already condensed)
            result["data"] = contexts
        else:
            result["data"] = {}

        result["token_estimate"] = cmd_data.get("token_estimate", {}).get("contexts", 50)

    elif depth == "errors":
        result["data"] = cmd_data.get("errors", "")
        result["token_estimate"] = cmd_data.get("token_estimate", {}).get("errors", 30)

    else:  # raw - fall back to full command knowledge store
        return None  # Signal to caller to use raw knowledge

    return result


def _get_available_tiers(tool: str, condensed: dict) -> list[str]:
    """Determine which tiers are available for a tool."""
    available = []

    tool_data = condensed.get("tools", {}).get(tool, {})

    # Quick tier: available if we have a quick summary
    if tool_data.get("quick"):
        available.append("quick")

    # Context tier: available if we have any contexts
    if tool_data.get("contexts"):
        available.append("context")

    # Errors tier: available if we have error categories
    if tool_data.get("errors"):
        available.append("errors")

    # Raw tier: always available (falls back to raw knowledge graph)
    available.append("raw")

    return available


def _estimate_tokens(tier: str, tool_data: dict, raw_result: dict) -> int:
    """Estimate token count for a tier's response."""
    if tier == "quick":
        quick = tool_data.get("quick", "")
        return len(quick.split()) + 10  # Words + overhead
    elif tier == "context":
        # Estimate based on context data
        contexts = tool_data.get("contexts", {})
        if contexts:
            # Average context size
            total_words = sum(
                len(c.get("summary", "").split()) +
                len(c.get("gotchas", "").split()) + 20
                for c in contexts.values()
            )
            return total_words // len(contexts) + 20
        return TIER_TOKEN_ESTIMATES["context"]
    elif tier == "errors":
        errors = tool_data.get("errors", {})
        return len(errors) * 15 + 10  # ~15 words per error
    else:  # raw
        patterns = raw_result.get("patterns", [])
        avoid = raw_result.get("avoid", [])
        return (len(patterns) + len(avoid)) * 30 + 20  # ~30 words per pattern


def query_knowledge_tiered(
    intent: str | None = None,
    tool: str | None = None,
    depth: TierLevel | None = None,
    context_name: str | None = None,
) -> dict[str, Any]:
    """
    Query knowledge with tier-aware response.

    This is the primary query interface. Claude decides which tier to request.
    The system returns the requested depth plus metadata about what's available.

    Args:
        intent: Natural language description of what you want to accomplish
        tool: Specific MCP tool name to get patterns for
        depth: Tier to return - "quick", "context", "errors", or "raw"
               If None, returns "context" tier by default
        context_name: For "context" tier, specific context to return
                      If None with context tier, returns best-matching context

    Returns:
        {
            "tier": "context",
            "source": "consolidated" | "raw",
            "data": { ... tier-specific data ... },
            "available_tiers": ["quick", "context", "errors", "raw"],
            "token_estimates": {"quick": 20, "context": 50, ...},
            "available_contexts": ["basic", "nested", "colored"],
            "hint": "If this fails, try depth='errors' to see common mistakes"
        }

    Design Principle:
        Claude decides the depth. The system provides visibility into what's
        available. This leverages future Claude improvements and assumes
        falling token costs over time.
    """
    # Default depth
    if depth is None:
        depth = "context"

    # =================================================================
    # Phase 3 Integration: Check for Rhino command tiered knowledge
    # =================================================================
    # If the tool parameter looks like a Rhino command (or if intent mentions
    # a command name), try to return tiered command knowledge first.
    command_to_check = None

    # Check if tool is a Rhino command name
    if tool:
        # Normalize: remove leading dash/underscore for comparison
        normalized = tool.lstrip("-_")
        # Check if it's a known command pattern (starts with uppercase)
        if normalized and normalized[0].isupper():
            command_to_check = tool

    # Also try to extract command from intent
    if not command_to_check and intent:
        condensed_cmds = _load_condensed_command_knowledge().get("commands", {})
        # Look for command names in intent (e.g., "create Box", "use Sphere")
        # Find ALL matches, then prefer the longest (most specific) match
        matches = []
        # Normalize intent by removing spaces for matching compound commands
        # e.g., "point light" -> "pointlight" matches "PointLight"
        intent_normalized = intent.lower().replace(" ", "")
        for cmd_name in condensed_cmds:
            bare_name = cmd_name.lstrip("-")
            # Check both with and without space normalization
            if bare_name.lower() in intent.lower() or bare_name.lower() in intent_normalized:
                matches.append((cmd_name, len(bare_name)))

        if matches:
            # Sort by length descending to prefer longer/more specific matches
            # e.g., "PointLight" over "Point" for intent "create point light"
            matches.sort(key=lambda x: x[1], reverse=True)
            command_to_check = matches[0][0]

    # If we found a command, return tiered command knowledge
    if command_to_check and depth != "raw":
        cmd_tiered = _get_command_tiered_knowledge(
            command_name=command_to_check,
            depth=depth,
            context_name=context_name,
        )
        if cmd_tiered:
            # Build full response with tiered command knowledge
            condensed_cmds = _load_condensed_command_knowledge()
            cmd_data = condensed_cmds.get("commands", {}).get(cmd_tiered["command"], {})

            result = {
                "tier": depth,
                "source": "consolidated",
                "command": cmd_tiered["command"],
                "family": cmd_tiered["family"],
                "similar_commands": cmd_tiered["similar_commands"],
                "data": cmd_tiered["data"],
                "available_tiers": ["quick", "context", "errors", "raw"],
                "token_estimates": cmd_data.get("token_estimate", {}),
                "available_contexts": cmd_tiered.get("available_contexts", []),
            }

            # Add appropriate hint based on tier
            if depth == "quick":
                result["hint"] = "For mode-specific info, try depth='context'"
            elif depth == "context":
                result["hint"] = "If this fails, try depth='errors' to see common mistakes"
            elif depth == "errors":
                result["hint"] = "For full pattern details, try depth='raw'"

            return result

    # =================================================================
    # Fallback to general knowledge system
    # =================================================================

    # Load condensed knowledge
    condensed = _load_condensed_knowledge()

    # Get raw knowledge (for RAW tier and as fallback)
    raw_result = query_knowledge(intent=intent, tool=tool)

    # Build response structure
    result = {
        "tier": depth,
        "source": "raw",  # Will update if using consolidated
        "data": {},
        "available_tiers": ["raw"],  # Minimum
        "token_estimates": {},
        "available_contexts": [],
        "confidence": raw_result.get("confidence", 0.0),
    }

    # Check if we have consolidated knowledge for this tool
    tool_data = condensed.get("tools", {}).get(tool, {}) if tool else {}

    if tool_data:
        result["available_tiers"] = _get_available_tiers(tool, condensed)
        result["available_contexts"] = list(tool_data.get("contexts", {}).keys())

        # Calculate token estimates
        for tier in result["available_tiers"]:
            result["token_estimates"][tier] = _estimate_tokens(tier, tool_data, raw_result)
    else:
        # Only raw available
        result["token_estimates"]["raw"] = _estimate_tokens("raw", {}, raw_result)

    # Return appropriate tier data
    if depth == "quick" and tool_data.get("quick"):
        result["source"] = "consolidated"
        result["data"] = {
            "summary": tool_data["quick"],
        }
        result["hint"] = "For specific usage patterns, try depth='context'"

    elif depth == "context" and tool_data.get("contexts"):
        result["source"] = "consolidated"
        contexts = tool_data["contexts"]
        selected_context_name = None
        selection_method = "none"

        # Select context using priority: explicit > MAB > keyword > first
        if context_name and context_name in contexts:
            # Specific context requested
            selected_context_name = context_name
            selection_method = "explicit"
        else:
            # Try retrieval MAB first (learns from feedback)
            mab = _get_retrieval_mab()
            if mab is not None and tool:
                mab_context = mab.select_context(
                    tool=tool,
                    intent=intent or "",
                    recent_failures=None,  # Could track this in future
                )
                if mab_context and mab_context in contexts:
                    selected_context_name = mab_context
                    selection_method = "mab"
                    logger.debug(f"MAB selected context '{mab_context}' for {tool}")

            # Fall back to keyword matching
            if not selected_context_name and intent:
                keyword_ctx = _match_intent_to_context(intent, contexts)
                if keyword_ctx:
                    selected_context_name = keyword_ctx
                    selection_method = "keyword"

            # Final fallback: first context or "basic" if available
            if not selected_context_name:
                if "basic" in contexts:
                    selected_context_name = "basic"
                else:
                    selected_context_name = next(iter(contexts.keys()), None)
                selection_method = "default"

        # Track query for feedback loop (Phase 5)
        if selected_context_name and tool:
            _track_query(tool, selected_context_name, intent or "")

        # Build response
        if selected_context_name and selected_context_name in contexts:
            ctx = contexts[selected_context_name]
            result["data"] = {
                "context_name": selected_context_name,
                "description": ctx.get("description", ""),
                "summary": ctx.get("summary", ""),
                "required_params": ctx.get("required_params", ""),
                "optional_params": ctx.get("optional_params", ""),
                "gotchas": ctx.get("gotchas", ""),
                "example": ctx.get("example", {}),
                "success_rate": ctx.get("success_rate", 0.0),
                "selection_method": selection_method,  # For debugging/transparency
            }
        else:
            # Return all contexts if selection failed
            result["data"] = {
                "contexts": {
                    name: {
                        "summary": ctx.get("summary", ""),
                        "gotchas": ctx.get("gotchas", ""),
                    }
                    for name, ctx in contexts.items()
                }
            }
        result["hint"] = "If this fails, try depth='errors' to see common mistakes"

    elif depth == "errors" and tool_data.get("errors"):
        result["source"] = "consolidated"
        result["data"] = {
            "errors": {
                name: {
                    "description": err.get("description", ""),
                    "avoidance": err.get("avoidance", ""),
                    "count": err.get("count", 0),
                }
                for name, err in tool_data["errors"].items()
            }
        }
        result["hint"] = "For full pattern details, try depth='raw'"

    else:
        # RAW tier or fallback
        result["tier"] = "raw"
        result["source"] = "raw"
        result["data"] = {
            "patterns": raw_result.get("patterns", []),
            "avoid": raw_result.get("avoid", []),
        }
        result["hint"] = "This is the full raw knowledge. Consider depth='context' for a summary."

    # Phase 6: Unified Knowledge - Also search command knowledge store
    # This integrates DSPy-learned command patterns into the query result
    command_store = _get_command_knowledge_store()
    if command_store and intent:
        command_matches = command_store.get_for_intent(intent)
        if command_matches:
            # Include matching command patterns in the result
            # Helper to safely get mode attributes (ModeKnowledge or dict)
            def _get_mode_attr(mode, attr, default=""):
                if isinstance(mode, dict):
                    return mode.get(attr, default)
                return getattr(mode, attr, default)

            result["command_knowledge"] = {
                "source": "dspy_learned",
                "count": len(command_matches),
                "commands": {
                    cmd_name: {
                        "description": pattern.description,
                        "modes": {
                            name: {
                                "syntax": _get_mode_attr(mode, "syntax", ""),
                                "example": _get_mode_attr(mode, "example", ""),
                                "description": _get_mode_attr(mode, "description", ""),
                            }
                            for name, mode in pattern.modes.items()
                        },
                        "options": pattern.options,
                        "gotchas": pattern.gotchas,
                        "preconditions": pattern.preconditions if isinstance(pattern.preconditions, dict) else {
                            "requires_selection": getattr(pattern.preconditions, 'requires_selection', False),
                            "selection_type": getattr(pattern.preconditions, 'selection_type', 'none'),
                        },
                        "observations_count": pattern.observations_count,
                    }
                    for cmd_name, pattern in list(command_matches.items())[:3]  # Top 3 matches
                }
            }
            # Update hint to mention command knowledge
            if "command_knowledge" in result:
                result["hint"] = (
                    result.get("hint", "") +
                    f" Also found {len(command_matches)} relevant command patterns from learned knowledge."
                )

    return result


def _match_intent_to_context(intent: str, contexts: dict) -> str | None:
    """Match an intent to the best context based on keywords."""
    intent_lower = intent.lower()

    # Simple keyword matching
    for ctx_name, ctx_data in contexts.items():
        ctx_lower = ctx_name.lower()
        desc_lower = ctx_data.get("description", "").lower()

        # Direct name match
        if ctx_lower in intent_lower:
            return ctx_name

        # Check description keywords
        desc_words = desc_lower.split()
        matches = sum(1 for word in desc_words if word in intent_lower and len(word) > 3)
        if matches >= 2:
            return ctx_name

    return None
