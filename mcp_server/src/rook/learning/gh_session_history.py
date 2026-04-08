"""
GH Session History - Automatic session recording for Grasshopper tools.

Provides:
- GHToolResult: Standardized return type for all mutating GH tools
- GHSessionRecorder: Manages session lifecycle and persistence
- @records_to_session: Decorator for automatic recording
- @query_only: Marker for read-only tools (not recorded)

Part of Path 2 meta-learning system. Sessions provide entry IDs for pattern citations.
"""

import asyncio
import functools
import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Literal, Optional, TypeVar
from ..runtime_paths import resolve_writable_knowledge_path

logger = logging.getLogger("rook.gh_session")

# Type aliases
OutcomeType = Literal["success", "partial", "failure"]
SessionStatus = Literal["active", "paused", "ended"]

# Storage paths
SESSIONS_DIR = resolve_writable_knowledge_path("gh", "sessions")
ACTIVE_DIR = SESSIONS_DIR / "_active"
INDEX_PATH = SESSIONS_DIR / "_index.json"

# Configuration
SESSION_IDLE_TIMEOUT = timedelta(hours=1)
WRITE_EVERY_ENTRY = True  # Write to disk after every entry


# =============================================================================
# Data Structures
# =============================================================================

@dataclass
class GHToolResult:
    """Standardized result from GH tools for session recording.

    All mutating GH tools should return this type. The decorator extracts
    recording data from it automatically.
    """

    success: bool
    """Whether the operation completed without errors."""

    outcome: OutcomeType
    """More nuanced outcome:
    - success: Operation completed as intended
    - partial: Operation completed but with warnings or unexpected results
    - failure: Operation failed
    """

    data: dict[str, Any] = field(default_factory=dict)
    """Tool-specific result data (returned to Claude)."""

    components_created: list[str] = field(default_factory=list)
    """GUIDs of components created by this operation."""

    components_affected: list[str] = field(default_factory=list)
    """GUIDs of components modified (not created) by this operation."""

    components_deleted: list[str] = field(default_factory=list)
    """GUIDs of components removed by this operation."""

    connections_made: list[tuple[str, str, str, str]] = field(default_factory=list)
    """Connections created: [(source_id, source_param, target_id, target_param), ...]"""

    connections_removed: list[tuple[str, str, str, str]] = field(default_factory=list)
    """Connections removed."""

    errors: list[str] = field(default_factory=list)
    """Error messages from the operation."""

    warnings: list[str] = field(default_factory=list)
    """Warning messages (operation succeeded but with caveats)."""

    def to_response(self) -> dict:
        """Convert to MCP response dict (what Claude sees)."""
        response = {
            "success": self.success,
            **self.data,
        }
        if self.errors:
            response["errors"] = self.errors
        if self.warnings:
            response["warnings"] = self.warnings
        return response

    def to_entry_data(self) -> dict:
        """Convert to session entry data (what gets recorded)."""
        data = {"outcome": self.outcome}

        if self.components_created:
            data["components_created"] = self.components_created
        if self.components_affected:
            data["components_affected"] = self.components_affected
        if self.components_deleted:
            data["components_deleted"] = self.components_deleted
        if self.connections_made:
            data["connections_made"] = [list(c) for c in self.connections_made]
        if self.connections_removed:
            data["connections_removed"] = [list(c) for c in self.connections_removed]
        if self.errors:
            data["errors"] = self.errors
        if self.warnings:
            data["warnings"] = self.warnings

        return data


@dataclass
class SessionEntry:
    """A single recorded action in a session."""

    entry_id: int
    """Unique ID within this session (1-indexed for human readability)."""

    timestamp: str
    """ISO format timestamp."""

    action: str
    """Tool name (e.g., 'gh_edit', 'gh_execute_intent')."""

    params: dict[str, Any]
    """Tool parameters (inputs)."""

    outcome: OutcomeType
    """Operation outcome."""

    # From GHToolResult
    components_created: Optional[list[str]] = None
    components_affected: Optional[list[str]] = None
    components_deleted: Optional[list[str]] = None
    connections_made: Optional[list[list[str]]] = None
    connections_removed: Optional[list[list[str]]] = None
    errors: Optional[list[str]] = None
    warnings: Optional[list[str]] = None

    # Explicit annotation
    notes: Optional[str] = None
    """Claude's observation about this action (via gh_session_note)."""

    # Phase 4: Execution plan
    plan: Optional[dict[str, Any]] = None
    """Execution plan if gh_execute_intent was called with a plan."""

    def to_dict(self) -> dict:
        """Convert to dict for JSON serialization."""
        d = {
            "entry_id": self.entry_id,
            "timestamp": self.timestamp,
            "action": self.action,
            "params": self.params,
            "outcome": self.outcome,
        }

        # Only include non-None optional fields
        if self.components_created:
            d["components_created"] = self.components_created
        if self.components_affected:
            d["components_affected"] = self.components_affected
        if self.components_deleted:
            d["components_deleted"] = self.components_deleted
        if self.connections_made:
            d["connections_made"] = self.connections_made
        if self.connections_removed:
            d["connections_removed"] = self.connections_removed
        if self.errors:
            d["errors"] = self.errors
        if self.warnings:
            d["warnings"] = self.warnings
        if self.notes:
            d["notes"] = self.notes
        if self.plan:
            d["plan"] = self.plan

        return d

    @classmethod
    def from_dict(cls, d: dict) -> "SessionEntry":
        """Create from dict."""
        return cls(
            entry_id=d["entry_id"],
            timestamp=d["timestamp"],
            action=d["action"],
            params=d.get("params", {}),
            outcome=d["outcome"],
            components_created=d.get("components_created"),
            components_affected=d.get("components_affected"),
            components_deleted=d.get("components_deleted"),
            connections_made=d.get("connections_made"),
            connections_removed=d.get("connections_removed"),
            errors=d.get("errors"),
            warnings=d.get("warnings"),
            notes=d.get("notes"),
            plan=d.get("plan"),
        )


@dataclass
class SessionSummary:
    """Summary statistics for a session."""

    total_entries: int = 0
    successes: int = 0
    partials: int = 0
    failures: int = 0
    components_created: int = 0
    components_deleted: int = 0
    connections_made: int = 0
    connections_removed: int = 0
    patterns_applied: list[str] = field(default_factory=list)
    patterns_discovered: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "SessionSummary":
        return cls(**d)

    def update_from_entry(self, entry: SessionEntry) -> None:
        """Update summary with a new entry."""
        self.total_entries += 1

        if entry.outcome == "success":
            self.successes += 1
        elif entry.outcome == "partial":
            self.partials += 1
        else:
            self.failures += 1

        if entry.components_created:
            self.components_created += len(entry.components_created)
        if entry.components_deleted:
            self.components_deleted += len(entry.components_deleted)
        if entry.connections_made:
            self.connections_made += len(entry.connections_made)
        if entry.connections_removed:
            self.connections_removed += len(entry.connections_removed)


@dataclass
class Session:
    """A recording session for a single GH document."""

    session_id: str
    """Unique session identifier."""

    document: str
    """GH document name."""

    document_path: str
    """Full path to the document."""

    started: str
    """ISO timestamp when session started."""

    status: SessionStatus = "active"
    """Current session status."""

    ended: Optional[str] = None
    """ISO timestamp when session ended (if ended)."""

    entries: list[SessionEntry] = field(default_factory=list)
    """Chronological list of recorded actions."""

    summary: SessionSummary = field(default_factory=SessionSummary)
    """Running summary statistics."""

    last_activity: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    """Last activity timestamp for timeout detection."""

    def to_dict(self) -> dict:
        """Convert to dict for JSON serialization."""
        return {
            "session_id": self.session_id,
            "document": self.document,
            "document_path": self.document_path,
            "started": self.started,
            "status": self.status,
            "ended": self.ended,
            "last_activity": self.last_activity,
            "entries": [e.to_dict() for e in self.entries],
            "summary": self.summary.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Session":
        """Create from dict."""
        session = cls(
            session_id=d["session_id"],
            document=d["document"],
            document_path=d.get("document_path", ""),
            started=d["started"],
            status=d.get("status", "active"),
            ended=d.get("ended"),
            last_activity=d.get("last_activity", d["started"]),
        )
        session.entries = [SessionEntry.from_dict(e) for e in d.get("entries", [])]
        if "summary" in d:
            session.summary = SessionSummary.from_dict(d["summary"])
        return session

    def add_entry(
        self,
        action: str,
        params: dict,
        result: GHToolResult,
    ) -> SessionEntry:
        """Add a new entry to the session."""
        entry_id = len(self.entries) + 1
        now = datetime.utcnow().isoformat() + "Z"

        entry_data = result.to_entry_data()

        # Phase 4: Extract plan from params if present
        plan = params.get("plan") if isinstance(params, dict) else None

        entry = SessionEntry(
            entry_id=entry_id,
            timestamp=now,
            action=action,
            params=params,
            outcome=entry_data["outcome"],
            components_created=entry_data.get("components_created"),
            components_affected=entry_data.get("components_affected"),
            components_deleted=entry_data.get("components_deleted"),
            connections_made=entry_data.get("connections_made"),
            connections_removed=entry_data.get("connections_removed"),
            errors=entry_data.get("errors"),
            warnings=entry_data.get("warnings"),
            plan=plan,
        )

        self.entries.append(entry)
        self.summary.update_from_entry(entry)
        self.last_activity = now

        return entry

    def add_note(self, note: str, entry_id: Optional[int] = None) -> bool:
        """Add a note to an entry (default: most recent)."""
        if not self.entries:
            return False

        target_id = entry_id if entry_id is not None else len(self.entries)

        for entry in self.entries:
            if entry.entry_id == target_id:
                if entry.notes:
                    entry.notes += f"\n{note}"
                else:
                    entry.notes = note
                self.last_activity = datetime.utcnow().isoformat() + "Z"
                return True

        return False

    def is_timed_out(self) -> bool:
        """Check if session has exceeded idle timeout."""
        try:
            last = datetime.fromisoformat(self.last_activity.rstrip("Z"))
            return datetime.utcnow() - last > SESSION_IDLE_TIMEOUT
        except (ValueError, TypeError):
            return False

    def get_entries(
        self,
        offset: int = 0,
        limit: int = 50,
        outcome: Optional[OutcomeType] = None,
    ) -> list[SessionEntry]:
        """Get entries with pagination and optional filtering.

        Args:
            offset: Start index. Negative values count from end (-10 = last 10).
            limit: Maximum entries to return.
            outcome: Filter by outcome type.
        """
        entries = self.entries

        # Filter by outcome if specified
        if outcome:
            entries = [e for e in entries if e.outcome == outcome]

        # Handle negative offset (from end)
        if offset < 0:
            start = max(0, len(entries) + offset)
        else:
            start = offset

        end = min(start + limit, len(entries))

        return entries[start:end]


# =============================================================================
# Session Recorder
# =============================================================================

class GHSessionRecorder:
    """Manages GH session recording with multi-document support.

    Singleton pattern - use get_session_recorder() to access.
    """

    def __init__(self, storage_dir: Optional[Path] = None):
        self.storage_dir = storage_dir or SESSIONS_DIR
        self.active_dir = self.storage_dir / "_active"
        self.index_path = self.storage_dir / "_index.json"

        # In-memory session cache: doc_key -> Session
        self._sessions: dict[str, Session] = {}

        # Currently active document
        self._active_doc: Optional[str] = None

        # Lock for thread safety
        self._lock = asyncio.Lock()

        # Ensure directories exist
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.active_dir.mkdir(parents=True, exist_ok=True)

    def _doc_key(self, document: str, document_path: str) -> str:
        """Create a unique key for a document."""
        # Use path if available, otherwise just name
        if document_path:
            return document_path.replace("\\", "/").lower()
        return document.lower()

    def _session_file(self, doc_key: str, active: bool = True) -> Path:
        """Get file path for a session."""
        # Sanitize doc_key for filename
        safe_name = doc_key.replace("/", "_").replace(":", "_").replace("\\", "_")
        if len(safe_name) > 100:
            safe_name = safe_name[-100:]

        if active:
            return self.active_dir / f"{safe_name}.json"
        else:
            # Completed sessions go to main dir with session ID
            return self.storage_dir / f"{safe_name}.json"

    async def _load_session(self, doc_key: str) -> Optional[Session]:
        """Load session from disk if exists."""
        path = self._session_file(doc_key, active=True)

        if not path.exists():
            return None

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return Session.from_dict(data)
        except Exception as e:
            logger.error(f"Failed to load session from {path}: {e}")
            return None

    async def _save_session(self, session: Session, doc_key: str) -> bool:
        """Save session to disk."""
        path = self._session_file(doc_key, active=session.status != "ended")

        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(session.to_dict(), f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            logger.error(f"Failed to save session to {path}: {e}")
            return False

    async def _create_session(self, document: str, document_path: str) -> Session:
        """Create a new session."""
        now = datetime.utcnow()
        session_id = f"gh_session_{now.strftime('%Y%m%d_%H%M%S')}"

        session = Session(
            session_id=session_id,
            document=document,
            document_path=document_path,
            started=now.isoformat() + "Z",
            status="active",
        )

        logger.info(f"Created session {session_id} for {document}")
        return session

    async def _check_timeout(self, session: Session, doc_key: str) -> bool:
        """Check if session timed out and end it if so. Returns True if timed out."""
        if session.is_timed_out():
            logger.info(f"Session {session.session_id} timed out, ending")
            await self._end_session(session, doc_key)
            return True
        return False

    async def _end_session(self, session: Session, doc_key: str) -> None:
        """End a session and move to completed storage."""
        session.status = "ended"
        session.ended = datetime.utcnow().isoformat() + "Z"

        # Save to completed location
        completed_path = self.storage_dir / f"{session.session_id}.json"
        try:
            with open(completed_path, "w", encoding="utf-8") as f:
                json.dump(session.to_dict(), f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save completed session: {e}")

        # Remove from active
        active_path = self._session_file(doc_key, active=True)
        if active_path.exists():
            try:
                active_path.unlink()
            except Exception as e:
                logger.warning(f"Failed to remove active session file: {e}")

        # Remove from memory
        if doc_key in self._sessions:
            del self._sessions[doc_key]

    async def ensure_session(self, document: str, document_path: str) -> Session:
        """Get or create session for document. Auto-switches if doc changed.

        Args:
            document: GH document name
            document_path: Full path to document

        Returns:
            Active session for this document
        """
        async with self._lock:
            doc_key = self._doc_key(document, document_path)

            # Check if we're switching documents
            if self._active_doc and self._active_doc != doc_key:
                # Pause current session
                if self._active_doc in self._sessions:
                    old_session = self._sessions[self._active_doc]
                    if old_session.status == "active":
                        old_session.status = "paused"
                        await self._save_session(old_session, self._active_doc)
                        logger.info(f"Paused session for {old_session.document}")

            # Get or create session for this document
            if doc_key in self._sessions:
                session = self._sessions[doc_key]

                # Check timeout
                if await self._check_timeout(session, doc_key):
                    # Timed out - create new
                    session = await self._create_session(document, document_path)
                    self._sessions[doc_key] = session
                elif session.status == "paused":
                    # Resume
                    session.status = "active"
                    session.last_activity = datetime.utcnow().isoformat() + "Z"
                    logger.info(f"Resumed session {session.session_id}")
            else:
                # Try to load from disk
                session = await self._load_session(doc_key)

                if session:
                    if await self._check_timeout(session, doc_key):
                        session = await self._create_session(document, document_path)
                    elif session.status == "paused":
                        session.status = "active"
                        session.last_activity = datetime.utcnow().isoformat() + "Z"
                else:
                    session = await self._create_session(document, document_path)

                self._sessions[doc_key] = session

            self._active_doc = doc_key
            return session

    async def record(
        self,
        action: str,
        params: dict,
        result: GHToolResult,
        document: str,
        document_path: str,
        patterns_applied: Optional[list[str]] = None,
    ) -> int:
        """Record an entry to the session.

        Args:
            action: Tool name
            params: Tool parameters
            result: GHToolResult from tool execution
            document: GH document name
            document_path: Full document path
            patterns_applied: Optional list of pattern IDs that were used in this action
                             (Phase 2 integration)

        Returns:
            Entry ID of the recorded action
        """
        session = await self.ensure_session(document, document_path)

        async with self._lock:
            entry = session.add_entry(action, params, result)

            # Track patterns applied (Phase 2 integration)
            if patterns_applied:
                for pattern_id in patterns_applied:
                    if pattern_id not in session.summary.patterns_applied:
                        session.summary.patterns_applied.append(pattern_id)

            if WRITE_EVERY_ENTRY:
                doc_key = self._doc_key(document, document_path)
                await self._save_session(session, doc_key)

            logger.debug(f"Recorded entry #{entry.entry_id}: {action}")
            return entry.entry_id

    async def add_note(
        self,
        note: str,
        entry_id: Optional[int] = None,
        document: Optional[str] = None,
        document_path: Optional[str] = None,
    ) -> dict:
        """Add a note to an entry.

        Args:
            note: The observation text
            entry_id: Specific entry to annotate (default: most recent)
            document: Document name (default: current active)
            document_path: Document path (default: current active)

        Returns:
            {"success": bool, "attached_to_entry": int}
        """
        async with self._lock:
            # Find the session
            if document and document_path:
                doc_key = self._doc_key(document, document_path)
            elif self._active_doc:
                doc_key = self._active_doc
            else:
                return {"success": False, "error": "No active session"}

            if doc_key not in self._sessions:
                return {"success": False, "error": "Session not found"}

            session = self._sessions[doc_key]

            # Add the note
            target_id = entry_id if entry_id is not None else len(session.entries)
            success = session.add_note(note, target_id)

            if success and WRITE_EVERY_ENTRY:
                await self._save_session(session, doc_key)

            return {
                "success": success,
                "attached_to_entry": target_id if success else None,
                "error": None if success else "Entry not found",
            }

    async def get_current(self) -> Optional[dict]:
        """Get current session info and stats."""
        async with self._lock:
            if not self._active_doc or self._active_doc not in self._sessions:
                return None

            session = self._sessions[self._active_doc]

            return {
                "session_id": session.session_id,
                "document": session.document,
                "document_path": session.document_path,
                "status": session.status,
                "started": session.started,
                "entry_count": len(session.entries),
                "last_entry_id": len(session.entries),
                "last_activity": session.last_activity,
                "summary": session.summary.to_dict(),
            }

    async def get_history(
        self,
        offset: int = 0,
        limit: int = 50,
        outcome: Optional[OutcomeType] = None,
        document: Optional[str] = None,
        document_path: Optional[str] = None,
    ) -> dict:
        """Query session entries with pagination.

        Args:
            offset: Start index (negative = from end)
            limit: Maximum entries
            outcome: Filter by outcome type
            document: Specific document (default: current)
            document_path: Document path

        Returns:
            {"session_id", "total_entries", "returned", "offset", "entries"}
        """
        async with self._lock:
            # Find session
            if document and document_path:
                doc_key = self._doc_key(document, document_path)
            elif self._active_doc:
                doc_key = self._active_doc
            else:
                return {"error": "No active session", "entries": []}

            if doc_key not in self._sessions:
                # Try loading from disk
                session = await self._load_session(doc_key)
                if not session:
                    return {"error": "Session not found", "entries": []}
                self._sessions[doc_key] = session
            else:
                session = self._sessions[doc_key]

            entries = session.get_entries(offset, limit, outcome)

            return {
                "session_id": session.session_id,
                "document": session.document,
                "total_entries": len(session.entries),
                "returned": len(entries),
                "offset": offset,
                "entries": [e.to_dict() for e in entries],
            }

    async def end_session(
        self,
        document: Optional[str] = None,
        document_path: Optional[str] = None,
    ) -> dict:
        """End a session and compute final summary.

        Args:
            document: Document name (default: current)
            document_path: Document path

        Returns:
            {"session_id", "ended", "duration_minutes", "summary", "file_path"}
        """
        async with self._lock:
            # Find session
            if document and document_path:
                doc_key = self._doc_key(document, document_path)
            elif document:
                # Try to find session by document name alone
                doc_key = self._doc_key(document, "")
                if doc_key not in self._sessions:
                    # Search for a session matching this document name
                    for key, session in self._sessions.items():
                        if session.document.lower() == document.lower():
                            doc_key = key
                            break
            elif self._active_doc:
                doc_key = self._active_doc
            else:
                return {"error": "No active session"}

            if doc_key not in self._sessions:
                return {"error": "Session not found"}

            session = self._sessions[doc_key]

            # Calculate duration
            try:
                started = datetime.fromisoformat(session.started.rstrip("Z"))
                duration = (datetime.utcnow() - started).total_seconds() / 60
            except (ValueError, TypeError):
                duration = 0

            # End the session
            await self._end_session(session, doc_key)

            # Clear active doc if this was it
            if self._active_doc == doc_key:
                self._active_doc = None

            return {
                "session_id": session.session_id,
                "ended": session.ended,
                "duration_minutes": round(duration, 1),
                "summary": session.summary.to_dict(),
                "file_path": str(self.storage_dir / f"{session.session_id}.json"),
            }

    async def list_sessions(self, limit: int = 20) -> list[dict]:
        """List recent sessions."""
        sessions = []

        # Get completed sessions
        for path in sorted(self.storage_dir.glob("gh_session_*.json"), reverse=True)[:limit]:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                sessions.append({
                    "session_id": data.get("session_id"),
                    "document": data.get("document"),
                    "started": data.get("started"),
                    "ended": data.get("ended"),
                    "status": data.get("status", "ended"),
                    "entry_count": len(data.get("entries", [])),
                })
            except Exception as e:
                logger.warning(f"Failed to read session {path}: {e}")

        # Add active sessions
        for doc_key, session in self._sessions.items():
            if session.status in ("active", "paused"):
                sessions.insert(0, {
                    "session_id": session.session_id,
                    "document": session.document,
                    "started": session.started,
                    "ended": None,
                    "status": session.status,
                    "entry_count": len(session.entries),
                })

        return sessions[:limit]


# =============================================================================
# Global Instance
# =============================================================================

_session_recorder: Optional[GHSessionRecorder] = None


def get_session_recorder() -> GHSessionRecorder:
    """Get or create the global session recorder."""
    global _session_recorder
    if _session_recorder is None:
        _session_recorder = GHSessionRecorder()
    return _session_recorder


def load_session(session_id: str) -> Optional[dict]:
    """Load a session by ID from disk or memory.

    Args:
        session_id: The session ID to load (e.g., "gh_session_abc123")

    Returns:
        Session data dict with entries, or None if not found
    """
    recorder = get_session_recorder()

    # First check active sessions in memory
    for doc_key, session in recorder._sessions.items():
        if session.session_id == session_id:
            return {
                "session_id": session.session_id,
                "document": session.document,
                "started": session.started,
                "ended": session.ended,
                "status": session.status,
                "entries": [e.to_dict() for e in session.entries],
                "summary": session.summary.to_dict(),
            }

    # Check completed sessions on disk
    session_path = recorder.storage_dir / f"{session_id}.json"
    if session_path.exists():
        try:
            with open(session_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load session {session_id}: {e}")

    return None


# =============================================================================
# Decorators
# =============================================================================

# Type variable for decorated function
F = TypeVar("F", bound=Callable)


def _extract_recordable_params(kwargs: dict) -> dict:
    """Extract parameters worth recording (exclude internal ones)."""
    excluded = {"document", "document_path", "_context", "_session"}
    return {k: v for k, v in kwargs.items() if k not in excluded and not k.startswith("_")}


def records_to_session(func: F) -> F:
    """Decorator that records tool calls to session automatically.

    Requirements:
    - Tool must return GHToolResult
    - Document context is retrieved automatically from GH plugin

    Usage:
        @records_to_session
        async def gh_edit(operations: list, ...) -> GHToolResult:
            ...
    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        # Import here to avoid circular imports
        from rook.learning.gh_session_history import get_session_recorder

        # Get document context - try kwargs first, then fetch from plugin
        document = kwargs.pop("_document", None)
        document_path = kwargs.pop("_document_path", None)

        if not document:
            # Will be populated by the server layer before calling
            # For now, use a placeholder
            document = kwargs.get("document", "unknown.gh")
            document_path = kwargs.get("document_path", "")

        # Call the tool
        result = await func(*args, **kwargs)

        # Ensure it's a GHToolResult
        if not isinstance(result, GHToolResult):
            logger.warning(f"{func.__name__} did not return GHToolResult, skipping recording")
            return result

        # Record to session
        try:
            recorder = get_session_recorder()
            entry_id = await recorder.record(
                action=func.__name__,
                params=_extract_recordable_params(kwargs),
                result=result,
                document=document,
                document_path=document_path,
            )

            # Add entry_id to response
            response = result.to_response()
            response["_entry_id"] = entry_id

            return response

        except Exception as e:
            logger.error(f"Failed to record {func.__name__} to session: {e}")
            # Still return the result even if recording failed
            return result.to_response()

    return wrapper  # type: ignore


def query_only(func: F) -> F:
    """Marker decorator for read-only tools (not recorded to session).

    Usage:
        @query_only
        async def gh_query():
            ...
    """
    func._query_only = True  # type: ignore
    return func


# =============================================================================
# Convenience Functions
# =============================================================================

async def record_tool_call(
    action: str,
    params: dict,
    result: GHToolResult,
    document: str,
    document_path: str,
) -> int:
    """Record a tool call to the session. Convenience wrapper."""
    recorder = get_session_recorder()
    return await recorder.record(action, params, result, document, document_path)


async def get_current_session() -> Optional[dict]:
    """Get current session info. Convenience wrapper."""
    recorder = get_session_recorder()
    return await recorder.get_current()


async def get_session_history(
    offset: int = 0,
    limit: int = 50,
    outcome: Optional[OutcomeType] = None,
) -> dict:
    """Get session history. Convenience wrapper."""
    recorder = get_session_recorder()
    return await recorder.get_history(offset, limit, outcome)


async def add_session_note(note: str, entry_id: Optional[int] = None) -> dict:
    """Add a note to session. Convenience wrapper."""
    recorder = get_session_recorder()
    return await recorder.add_note(note, entry_id)


async def end_current_session() -> dict:
    """End current session. Convenience wrapper."""
    recorder = get_session_recorder()
    return await recorder.end_session()
