"""P6 Slice 1 — durable artifact perception (orchestration plane).

A saved work product is addressable by its normalized path, independent of any
live session. This module is a dumb store: it accepts `source` from callers and
NEVER infers ownership (spec I8). See
docs/superpowers/specs/2026-06-04-p6-artifact-perception-design.md.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import sqlite3
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def normalize_path(path: str) -> str:
    """Absolute, symlink-resolved, case-folded (os.normcase) — so C:/A.3dm and
    c:/a.3dm are ONE artifact on Windows. The durable dedup identity."""
    return os.path.normcase(os.path.normpath(os.path.realpath(os.path.abspath(path))))


def artifact_id_for(norm_path: str) -> str:
    """Deterministic, collision-free stable handle = full SHA-256 hex of the
    normalized path (idempotent re-observation; UNIQUE in the schema)."""
    return hashlib.sha256(norm_path.encode("utf-8")).hexdigest()


def stat_file_state(norm_path: str) -> "tuple[str, int | None, int | None]":
    """(file_state, size_bytes, mtime). present iff os.stat succeeds; missing on
    FileNotFound/NotADirectory; unreachable on any other OSError (permission /
    unreachable drive / OneDrive flap) — NEVER assert missing on a flap (I2)."""
    try:
        st = os.stat(norm_path)
        return ("present", int(st.st_size), int(st.st_mtime))
    except (FileNotFoundError, NotADirectoryError):
        return ("missing", None, None)
    except OSError:
        return ("unreachable", None, None)


ARTIFACT_REGISTRY_VERSION = "p6.1"

_ARTIFACT_COLUMNS = ("artifact_id, path, file_state, source, origin_session_id, "
                     "document_name, size_bytes, mtime, label, created_at, "
                     "last_verified_at, last_missing_at")


@dataclass(frozen=True)
class ArtifactRow:
    artifact_id: str
    path: str
    file_state: str            # present | missing | unreachable
    source: str                # owned_workbench | explicit
    origin_session_id: str | None
    document_name: str | None
    size_bytes: int | None
    mtime: int | None
    label: str | None
    created_at: int
    last_verified_at: int | None
    last_missing_at: int | None


def _artifact_row(raw: "sqlite3.Row | tuple | None") -> "ArtifactRow | None":
    return None if raw is None else ArtifactRow(*raw)


def resolve_artifact_db_path() -> Path:
    """%LOCALAPPDATA%/Rook/registry/artifacts.db, falling back to %TEMP%/rook/registry.
    Separate file from P5's owned_sessions.db (Approach A, zero blast radius)."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    root = (Path(local_app_data) / "Rook" / "registry") if local_app_data \
        else (Path(tempfile.gettempdir()) / "rook" / "registry")
    return root / "artifacts.db"


class _ImmediateTx:
    """BEGIN IMMEDIATE ... COMMIT (ROLLBACK on error) holding the RLock — verbatim
    from registry.py (duplication accepted; no shared base class in Slice 1)."""

    def __init__(self, conn: sqlite3.Connection, lock: "threading.RLock"):
        self._conn = conn
        self._lock = lock

    def __enter__(self):
        self._lock.acquire()
        try:
            self._conn.execute("BEGIN IMMEDIATE;")
        except Exception:
            self._lock.release()
            raise
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            self._conn.execute("COMMIT;" if exc_type is None else "ROLLBACK;")
        finally:
            self._lock.release()
        return False


class ArtifactRegistry:
    """SQLite durable-artifact store. Mark-never-auto-delete; born-present. The
    registry accepts `source` from callers and never infers ownership (I8)."""

    def __init__(self, db_path: Path):
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.schema_unsupported: str | None = None
        self._conn = sqlite3.connect(str(db_path), isolation_level=None, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA synchronous=NORMAL;")
        self._conn.execute("PRAGMA busy_timeout=5000;")
        self._ensure_schema()

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass

    def _immediate(self) -> "_ImmediateTx":
        return _ImmediateTx(self._conn, self._lock)

    def _ensure_schema(self) -> None:
        # NEVER DROP artifacts — a missing file is a tombstone, not a reason to forget
        # history (I1/I7). Additive or fail-closed, never destructive. Decide
        # compatibility BEFORE touching the table (mirror registry.py:259).
        c = self._conn
        c.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);")
        stored = c.execute("SELECT value FROM meta WHERE key='artifact_registry_version';").fetchone()
        if stored is not None and stored[0] != ARTIFACT_REGISTRY_VERSION:
            self.schema_unsupported = stored[0]
            return
        table_exists = c.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='artifacts';").fetchone() is not None
        if table_exists:
            cols = {row[1] for row in c.execute("PRAGMA table_info(artifacts);").fetchall()}
            required = {col.strip() for col in _ARTIFACT_COLUMNS.split(",")}
            if not required.issubset(cols):
                self.schema_unsupported = "unknown"
                return
        c.execute("""
            CREATE TABLE IF NOT EXISTS artifacts (
                artifact_id      TEXT NOT NULL UNIQUE,
                path             TEXT PRIMARY KEY,
                file_state       TEXT NOT NULL,
                source           TEXT NOT NULL,
                origin_session_id TEXT,
                document_name    TEXT,
                size_bytes       INTEGER,
                mtime            INTEGER,
                label            TEXT,
                created_at       INTEGER NOT NULL,
                last_verified_at INTEGER,
                last_missing_at  INTEGER);""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_artifact_source ON artifacts(source);")
        if stored is None:
            c.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('artifact_registry_version', ?);",
                      (ARTIFACT_REGISTRY_VERSION,))
