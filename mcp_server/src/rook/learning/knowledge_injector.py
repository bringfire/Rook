"""Universal post-call knowledge injection for Rook.

Enriches every MCP tool response with relevant gotchas/hints from the
appropriate knowledge store. Ported from the Engram universal injection
pattern, adapted for Rook's richer knowledge graph.

Design:
    - Injects at the universal result-formatting point in server.py
    - Routes to the correct store based on tool name prefix
    - Scores gotchas using severity × log(occurrence) × recency × confidence + link boost
    - Skips tools already enriched by dedicated wrappers
    - Adds staleness fields lazily on first read (no upfront migration)

Token budget: ~20 tokens per-tool (quick tier), ~40 tokens workflow (context tier).
"""

import json
import logging
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .phase_tracker import WorkflowPhase, get_phase_tracker

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Injection capture logger — writes structured JSONL for later analysis.
# Activated when ROOK_INJECTION_LOG env var is set to a path,
# or defaults to mcp_server/injection_capture.jsonl when
# ROOK_LOG_LEVEL is DEBUG.
# ---------------------------------------------------------------------------
_capture_logger: logging.Logger | None = None


def _get_capture_logger() -> logging.Logger | None:
    """Lazily initialize the capture file logger."""
    global _capture_logger
    if _capture_logger is not None:
        return _capture_logger if _capture_logger.handlers else None

    log_path = os.environ.get("ROOK_INJECTION_LOG")
    if not log_path:
        if os.environ.get("ROOK_LOG_LEVEL", "").upper() == "DEBUG":
            log_path = str(
                Path(__file__).parent.parent.parent.parent.parent
                / "injection_capture.jsonl"
            )
        else:
            _capture_logger = logging.getLogger("rook.injection.noop")
            return None

    cap = logging.getLogger("rook.injection.capture")
    cap.setLevel(logging.DEBUG)
    cap.propagate = False
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(message)s"))
    cap.addHandler(fh)
    _capture_logger = cap
    logger.info(f"Injection capture log → {log_path}")
    return cap


def _capture(event: dict) -> None:
    """Write a structured event to the capture log (if active)."""
    cap = _get_capture_logger()
    if cap and cap.handlers:
        event["ts"] = datetime.now(timezone.utc).isoformat()
        cap.info(json.dumps(event, default=str))


# ---------------------------------------------------------------------------
# Tools that already get knowledge from dedicated wrappers in server.py.
# The injector skips these entirely.
# ---------------------------------------------------------------------------
_WRAPPED_TOOLS = frozenset({
    # Canvas Graph Protocol: gh_edit handles its own knowledge/session recording.
    # No individual GH tools need dedicated wrappers anymore.
})

# Meta-tools and authoritative Grasshopper results that should never get injection.
_SKIP_TOOLS = frozenset({
    "knowledge_query", "rhino_knowledge_query", "gh_knowledge_query", "knowledge_record",
    "gh_knowledge_reload", "gh_record_learning",
    "rhino_command_knowledge", "rhino_command_knowledge_reload",
    "rhino_command_observations",
    "gh_library", "gh_batch_component_info",
    "gh_edit", "gh_snapshot", "gh_status", "gh_errors",
})


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def should_inject(tool_name: str, result: dict) -> bool:
    """Check whether this result needs knowledge injection.

    Returns False if:
    - Tool is already enriched by a dedicated wrapper
    - Tool is a meta-tool (knowledge query/record)
    - Result failed (only inject on success)
    - Result data is not a dict (can't enrich scalars)
    """
    if tool_name in _WRAPPED_TOOLS or tool_name in _SKIP_TOOLS:
        return False

    if not result.get("success"):
        return False

    data = result.get("data")
    if not isinstance(data, dict):
        return False

    # Already enriched (by wrapper or previous injection)
    if "gotchas" in data or "knowledge_hint" in data:
        return False

    return True


async def inject_knowledge(
    tool_name: str,
    arguments: dict | None,
    result: dict,
) -> dict:
    """Inject quick-tier knowledge into a tool result.

    This is the main entry point, called from server.py after every tool
    execution. It is designed to be safe: any exception returns the original
    result unchanged.

    Args:
        tool_name: MCP tool name (e.g. "rhino_create", "gh_edit").
        arguments: Original tool arguments (may be None or mutated).
        result: The tool result dict (mutated in-place on success).

    Returns:
        The (possibly enriched) result dict.
    """
    try:
        store_type = _route_to_store(tool_name)
        tracker = get_phase_tracker()
        phase = tracker.current_phase()
        args = arguments or {}

        hint, meta = _fetch_and_score(store_type, tool_name, args, phase)

        data = result.get("data")
        if isinstance(data, dict):
            if hint:
                data["knowledge_hint"] = hint
                logger.info(f"P0 hint → {tool_name}: {hint[:80]}")
                _capture({
                    "event": "p0_inject",
                    "tool": tool_name,
                    "store": store_type,
                    "phase": phase.value,
                    "source": meta.get("source") if meta else None,
                    "hint": hint[:120],
                })
            elif tracker.should_inject_workflow_hint():
                # P1: Workflow-level hint only when no per-tool hint was injected
                wf_hint = _fetch_workflow_hint(phase)
                if wf_hint:
                    data["workflow_hint"] = wf_hint
                    logger.info(f"P1 workflow hint → {tool_name} (phase={phase.value})")
                    _capture({
                        "event": "p1_workflow",
                        "tool": tool_name,
                        "phase": phase.value,
                        "hint": wf_hint[:120],
                    })
            else:
                _capture({
                    "event": "no_hint",
                    "tool": tool_name,
                    "store": store_type,
                    "phase": phase.value,
                })

        # P2: Stash metadata for staleness feedback (not in data — won't serialize)
        if meta:
            result["_injection_meta"] = meta

    except Exception as e:
        # Never break tool execution because of injection failure.
        logger.warning(f"Knowledge injection skipped for {tool_name}: {e}")
        _capture({"event": "error", "tool": tool_name, "error": str(e)})

    return result


def record_injection_success(meta: dict) -> None:
    """Record that an injected hint was used on a successful tool call.

    Called from server.py after the tool result is formatted. Updates
    staleness fields (last_verified, times_used, observations_count) on
    the knowledge source that produced the hint.

    Args:
        meta: The _injection_meta dict stashed by inject_knowledge().
              Keys: store ("unified"|"command"|"gh"|"general"), plus
              note_id (for unified) or command (for command store).
    """
    try:
        store = meta.get("store")

        if store == "unified":
            note_id = meta.get("note_id")
            if note_id:
                from .unified_store import get_unified_store
                get_unified_store().mark_used_successfully(note_id)
                _capture({"event": "p2_staleness", "store": "unified", "note_id": note_id})

        elif store == "command":
            command = meta.get("command", "").strip()
            if command and command != "-":
                from .command_knowledge_store import get_command_knowledge_store
                get_command_knowledge_store().record_gotcha_success(command)
                _capture({"event": "p2_staleness", "store": "command", "command": command})

        elif store == "gh" and meta.get("source") == "gh_operation":
            operation = meta.get("operation") or ""
            gotcha_id = meta.get("gotcha_id")
            if operation:
                from .gh_knowledge import get_gh_knowledge_store
                get_gh_knowledge_store().record_gotcha_success(operation, gotcha_id)
                _capture({"event": "p2_staleness", "store": "gh", "operation": operation, "gotcha_id": gotcha_id})

        # "general" store doesn't have per-entry staleness yet
    except Exception as e:
        logger.warning(f"Staleness feedback failed: {e}")


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

def _route_to_store(tool_name: str) -> Optional[str]:
    """Map tool name to knowledge store type.

    Returns "gh", "rhino", or "general".
    Callers must filter via should_inject() first.
    """
    if tool_name.startswith("gh_"):
        return "gh"
    elif tool_name.startswith("rhino_"):
        return "rhino"
    else:
        return "general"


# ---------------------------------------------------------------------------
# Fetching + scoring
# ---------------------------------------------------------------------------

def _fetch_and_score(
    store_type: str,
    tool_name: str,
    arguments: dict,
    phase: WorkflowPhase,
) -> tuple[Optional[str], Optional[dict]]:
    """Fetch knowledge from the appropriate store, score, and return the
    best quick-tier hint + metadata for staleness tracking.

    Returns:
        (hint_text, metadata_dict) — metadata contains store_type and
        source identifier (note_id or command) for P2 feedback.
    """
    if store_type == "gh":
        return _fetch_gh(tool_name, arguments, phase)
    elif store_type == "rhino":
        return _fetch_rhino(tool_name, arguments, phase)
    elif store_type == "general":
        return _fetch_general(tool_name, arguments, phase)
    return None, None


_INTENT_TOOLS = frozenset({"gh_execute_intent"})


def _fetch_gh(
    tool_name: str, arguments: dict, phase: WorkflowPhase,
) -> tuple[Optional[str], Optional[dict]]:
    """Fetch from GH knowledge stores.

    Priority order for most tools:
    1. Operation-level gotchas (context-aware, from operations_knowledge.json)
    2. Component-level knowledge (from GHKnowledgeStore)
    3. Recipe/workflow knowledge (from UnifiedStore)

    For intent-based tools (gh_execute_intent), component knowledge
    comes first since the intent/name carries more specific information
    than the generic operation type.
    """
    from .gh_knowledge import get_gh_knowledge_store
    from .unified_store import get_unified_store

    store = get_gh_knowledge_store()
    intent = _gh_intent(tool_name, arguments)
    is_intent_tool = tool_name in _INTENT_TOOLS
    operation = _gh_operation(tool_name)

    # For intent-based tools: component knowledge first, then operation
    # For all other tools: operation knowledge first, then component
    if is_intent_tool:
        steps = [("component", intent), ("operation", operation)]
    else:
        steps = [("operation", operation), ("component", intent)]

    for step_type, key in steps:
        if not key:
            continue
        if step_type == "operation":
            op_result = store.query_operation(key, arguments)
            op_gotchas = op_result.get("gotchas", [])
            if op_gotchas:
                gotcha = op_gotchas[0]
                msg = gotcha.get("message", "")
                if msg:
                    return msg[:120], {
                        "store": "gh",
                        "source": "gh_operation",
                        "operation": key,
                        "gotcha_id": gotcha.get("id"),
                    }
        else:
            result = store.query(key, depth="quick")
            gotchas = result.get("gotchas", [])
            if gotchas and gotchas[0]:
                return gotchas[0][:120], {"store": "gh", "source": "gh_knowledge"}

    # Fallback to UnifiedStore (recipes / workflow knowledge)
    unified = get_unified_store()
    search_term = intent or tool_name.replace("_", " ")
    results = unified.search(intent=search_term, limit=1, tier="quick")
    if results:
        note = results[0]
        scored = _score_note(note, phase)
        if scored > 0.1:
            note_id = note.get("note_id", "")
            return note.get("brief", "")[:120], {"store": "unified", "note_id": note_id}

    return None, None


def _fetch_rhino(
    tool_name: str, arguments: dict, phase: WorkflowPhase,
) -> tuple[Optional[str], Optional[dict]]:
    """Fetch from CommandKnowledgeStore."""
    from .command_knowledge_store import get_command_knowledge_store

    store = get_command_knowledge_store()

    # Extract command name from arguments or tool name
    command = _rhino_command_name(tool_name, arguments)
    if not command:
        return None, None

    cmd = store.get_command(command)
    if cmd is None:
        return None, None

    # Score gotchas
    gotchas_with_scores = []
    for g in cmd.gotchas:
        entry = _ensure_staleness_fields(g, cmd)
        score = _score_gotcha(entry)
        gotchas_with_scores.append((score, entry))

    if not gotchas_with_scores:
        return None, None

    gotchas_with_scores.sort(reverse=True, key=lambda x: x[0])
    best_score, best_entry = gotchas_with_scores[0]

    if best_score < 0.1:
        return None, None

    msg = best_entry if isinstance(best_entry, str) else best_entry.get("message", "")
    return msg[:120], {"store": "command", "command": command}


def _fetch_general(
    tool_name: str, arguments: dict, phase: WorkflowPhase,
) -> tuple[Optional[str], Optional[dict]]:
    """Fetch from the general knowledge graph."""
    from rook.knowledge import query_knowledge_tiered

    result = query_knowledge_tiered(tool=tool_name, depth="quick")
    data = result.get("data")
    if not data:
        return None, None

    # Quick tier returns {"summary": "..."} or similar
    if isinstance(data, dict):
        summary = data.get("summary", "")
        if summary:
            return summary[:120], {"store": "general"}
    elif isinstance(data, str) and data:
        return data[:120], {"store": "general"}

    return None, None


# ---------------------------------------------------------------------------
# Workflow-level hints (P1)
# ---------------------------------------------------------------------------

# Tags used to search UnifiedStore for workflow-level hints per phase.
_WORKFLOW_SEARCH_TAGS: dict[WorkflowPhase, list[str]] = {
    WorkflowPhase.GH_BUILD: ["workflow", "recipe", "grasshopper"],
    WorkflowPhase.RHINO_MODEL: ["geometry", "modeling", "rhino"],
    WorkflowPhase.DEBUGGING: ["error", "debug", "troubleshooting"],
}


def _fetch_workflow_hint(phase: WorkflowPhase) -> Optional[str]:
    """Fetch a workflow-level hint from UnifiedStore for the current phase.

    Searches for notes tagged with phase-relevant keywords, scores them,
    and returns the best context-tier brief (~40 tokens). Only called when
    PhaseTracker detects a sustained phase.
    """
    tags = _WORKFLOW_SEARCH_TAGS.get(phase)
    if not tags:
        return None

    from .unified_store import get_unified_store

    unified = get_unified_store()
    results = unified.search(tags=tags, limit=3, tier="context")
    if not results:
        return None

    # Score and pick best
    best_score = 0.0
    best_hint = None
    for note in results:
        score = _score_note(note, phase)
        if score > best_score:
            best_score = score
            # Use context field for richer hint, fall back to brief
            text = note.get("context") or note.get("brief", "")
            best_hint = text[:200]  # ~40 tokens

    if best_score < 0.1:
        return None

    return best_hint


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def _score_gotcha(gotcha: str | dict) -> float:
    """Score a gotcha entry.

    Formula: severity × log10(occurrence + 1) × recency_decay × confidence + link_boost

    Works with both plain string gotchas (score = 0.5) and dict gotchas
    with staleness metadata.
    """
    if isinstance(gotcha, str):
        # Unstructured gotcha — give it a neutral score
        return 0.5

    severity = _severity_weight(gotcha.get("severity", "medium"))
    try:
        occurrence = max(int(gotcha.get("occurrence_count", 1)), 1)
        confidence = max(min(float(gotcha.get("confidence", 0.7)), 1.0), 0.0)
        link_boost = min(float(gotcha.get("link_count", 0)) * 0.05, 0.3)
    except (TypeError, ValueError):
        return 0.5
    recency = _recency_decay(gotcha.get("last_verified"))

    base = severity * math.log10(occurrence + 1) * recency * confidence
    return base + link_boost


def _score_note(note: dict, phase: WorkflowPhase) -> float:
    """Score a UnifiedStore quick-tier note dict for relevance."""
    # Link-based boost from A-MEM edges
    link_count = len(note.get("links", []))
    link_boost = min(link_count * 0.05, 0.3)

    # Phase match: boost if note tags overlap with phase keywords
    phase_keywords = _PHASE_TAG_MAP.get(phase, set())
    note_tags = set(note.get("tags", []))
    phase_match = 1.2 if (note_tags & phase_keywords) else 1.0

    base = 0.5 * phase_match  # Neutral base for quick-tier notes
    return base + link_boost


_PHASE_TAG_MAP: dict[WorkflowPhase, set[str]] = {
    WorkflowPhase.GH_BUILD: {"grasshopper", "component", "wiring", "recipe"},
    WorkflowPhase.RHINO_MODEL: {"geometry", "modeling", "rhino", "command"},
    WorkflowPhase.DEBUGGING: {"error", "debug", "troubleshooting", "fail"},
    WorkflowPhase.EXPLORATION: set(),
}


def _severity_weight(severity: str) -> float:
    return {
        "low": 1.0, "medium": 2.0, "high": 3.0, "critical": 5.0,
    }.get(severity, 2.0)


def _recency_decay(last_verified: str | None) -> float:
    """Exponential decay with ~21-day half-life, clamped to [0.3, 1.0]."""
    if not last_verified:
        return 0.5  # Never verified = neutral

    try:
        verified = datetime.fromisoformat(last_verified.replace("Z", "+00:00"))
        age_days = max((datetime.now(timezone.utc) - verified).total_seconds() / 86400, 0)
        # Half-life of 21 days
        decay = 2 ** (-age_days / 21.0)
        return max(min(decay, 1.0), 0.3)
    except Exception:
        return 0.5


# ---------------------------------------------------------------------------
# Staleness lazy migration
# ---------------------------------------------------------------------------

def _ensure_staleness_fields(gotcha: str | dict, cmd: object | None = None) -> dict:
    """Ensure a gotcha has staleness fields. Lazy migration on read.

    If gotcha is a plain string, wraps it into a dict with default fields.
    If gotcha is already a dict, backfills any missing fields.
    Does NOT write back to disk — the store handles persistence on next save.
    """
    if isinstance(gotcha, str):
        return {
            "message": gotcha,
            "severity": "medium",
            "occurrence_count": getattr(cmd, "observations_count", 1) if cmd else 1,
            "last_verified": getattr(cmd, "last_updated", None) if cmd else None,
            "confidence": 0.7,
            "link_count": 0,
        }

    # Backfill missing fields on existing dicts
    gotcha.setdefault("severity", "medium")
    gotcha.setdefault("occurrence_count", 1)
    gotcha.setdefault("last_verified", None)
    gotcha.setdefault("confidence", 0.7)
    gotcha.setdefault("link_count", 0)

    if "message" not in gotcha:
        # Shouldn't happen, but be safe
        gotcha["message"] = str(gotcha)

    return gotcha


# ---------------------------------------------------------------------------
# GH tool → operation mapping
# ---------------------------------------------------------------------------

# Maps gh_* tool names to operation keys in operations_knowledge.json.
# Tools not listed here fall through to component/recipe knowledge only.
_GH_TOOL_OPERATION: dict[str, str] = {
    # Canvas Graph Protocol — atomic edit + read
    "gh_edit": "edit",
    "gh_snapshot": "query",
    "gh_undo": "edit",
    # Intent-based creation
    "gh_execute_intent": "create",
    # Canvas layout
    "gh_move": "move",
    "gh_canvas_cleanup": "canvas_cleanup",
    # Grouping
    "gh_cluster": "group",
    # Canvas queries
    "gh_status": "query",
    "gh_selection": "query",
    "gh_errors": "query",
    "gh_library": "query",
    "gh_categories": "query",
    # Reference management
    "gh_set_reference": "reference",
    "gh_get_reference": "reference",
    "gh_clear_reference": "reference",
    # Canvas clear
    "gh_clear": "canvas_cleanup",
    # Document management
    "gh_document_open": "document",
    "gh_document_new": "document",
    # Exploration
    "gh_explore_component": "explore",
    "gh_explore_deep": "explore",
    "gh_explore_workflow": "explore",
    # Inspection / debugging
    "gh_inspect_output": "inspect_output",
    "gh_investigate": "investigate",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _gh_operation(tool_name: str) -> Optional[str]:
    """Map a GH tool name to an operation key for operations_knowledge.json."""
    return _GH_TOOL_OPERATION.get(tool_name)


def _gh_intent(tool_name: str, arguments: dict) -> str:
    """Extract a search intent from GH tool name + arguments."""
    # gh_execute_intent has an "intent" arg
    intent = arguments.get("intent", "")
    if intent:
        return intent

    # gh_edit operations may carry a "name" in sub-operations
    name = arguments.get("name", "")
    if name:
        return name

    # Fall back to tool name as intent
    return tool_name.replace("gh_", "").replace("_", " ")


def _rhino_command_name(tool_name: str, arguments: dict) -> str:
    """Extract the Rhino command name for CommandKnowledgeStore lookup."""
    # rhino_command / rhino_execute_intent carry the command in arguments
    command = arguments.get("command", "")
    if command:
        # Normalize: ensure leading dash for store lookup
        bare = command.lstrip("-_")
        return f"-{bare}" if bare else ""

    # rhino_execute_intent has "intent" — extract command name if present
    intent = arguments.get("intent", "")
    if intent:
        # Try to find a capitalized word that looks like a command
        for word in intent.split():
            if word and word[0].isupper() and word.isalpha():
                return f"-{word}"

    return ""


