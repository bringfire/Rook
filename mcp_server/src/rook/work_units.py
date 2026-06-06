"""P7 Slice 1 — coordinator-plane merge-contract registry.

Records Work Units + their P6 artifact provenance and Merge Contracts (a sources->target
dependency DAG), and validates fan-in intent. Records intent ONLY — no merge executes, no
geometry enters Rhino. Reads P6 artifacts READ-ONLY; never writes artifacts.db.
Invariant: P7 references P6 by artifact_id; P6 never references P7.
See docs/superpowers/specs/2026-06-05-p7-slice1-merge-contract-registry-design.md.
"""
from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import networkx as nx

from . import artifacts as _artifacts   # read-only P6 access (resolve + present check)

WORK_UNITS_REGISTRY_VERSION = "p7.1"

MERGE_KINDS = ("worksession", "import", "linked_block", "reference", "block", "report")
REFRESH_POLICIES = ("refresh_after_save", "refresh_on_demand")
RELATIONS = ("produced", "consumed")


def resolve_work_units_db_path() -> Path:
    """%LOCALAPPDATA%/Rook/registry/work_units.db, falling back to %TEMP%/rook/registry.
    Separate file from P5 owned_sessions.db and P6 artifacts.db."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    root = (Path(local_app_data) / "Rook" / "registry") if local_app_data \
        else (Path(tempfile.gettempdir()) / "rook" / "registry")
    return root / "work_units.db"


class _ImmediateTx:
    """BEGIN IMMEDIATE ... COMMIT (ROLLBACK on error) holding the RLock — verbatim from
    artifacts.py (duplication accepted; no shared base in Slice 1)."""
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


@dataclass(frozen=True)
class WorkUnitRow:
    work_unit_id: str
    label: str
    role: str | None
    metadata: str | None
    created_at: int


@dataclass(frozen=True)
class ContractRow:
    contract_id: str
    target_artifact_id: str
    merge_kind: str
    refresh_policy: str
    created_at: int


class WorkUnitRegistry:
    """Durable coordinator-plane store. Additive / version-gated / fail-closed (NEVER DROP)."""

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
        c = self._conn
        c.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);")
        stored = c.execute(
            "SELECT value FROM meta WHERE key='work_units_registry_version';").fetchone()
        if stored is not None and stored[0] != WORK_UNITS_REGISTRY_VERSION:
            self.schema_unsupported = stored[0]
            return
        c.execute("""CREATE TABLE IF NOT EXISTS work_units (
            work_unit_id TEXT PRIMARY KEY, label TEXT NOT NULL, role TEXT,
            metadata TEXT, created_at INTEGER NOT NULL);""")
        c.execute("""CREATE TABLE IF NOT EXISTS work_unit_artifacts (
            work_unit_id TEXT NOT NULL, artifact_id TEXT NOT NULL, relation TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            PRIMARY KEY (work_unit_id, artifact_id, relation));""")
        c.execute("""CREATE TABLE IF NOT EXISTS merge_contracts (
            contract_id TEXT PRIMARY KEY, target_artifact_id TEXT NOT NULL,
            merge_kind TEXT NOT NULL, refresh_policy TEXT NOT NULL, created_at INTEGER NOT NULL);""")
        c.execute("""CREATE TABLE IF NOT EXISTS merge_contract_sources (
            contract_id TEXT NOT NULL, source_artifact_id TEXT NOT NULL,
            PRIMARY KEY (contract_id, source_artifact_id));""")
        c.execute("""CREATE TABLE IF NOT EXISTS work_unit_merge_contracts (
            work_unit_id TEXT NOT NULL, contract_id TEXT NOT NULL, created_at INTEGER NOT NULL,
            PRIMARY KEY (work_unit_id, contract_id));""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_wua_wu ON work_unit_artifacts(work_unit_id);")
        c.execute("CREATE INDEX IF NOT EXISTS idx_mcs_contract ON merge_contract_sources(contract_id);")
        c.execute("CREATE INDEX IF NOT EXISTS idx_wumc_wu ON work_unit_merge_contracts(work_unit_id);")
        if stored is None:
            c.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('work_units_registry_version', ?);",
                      (WORK_UNITS_REGISTRY_VERSION,))


_WORK_UNITS_REGISTRY: "WorkUnitRegistry | None" = None


def work_units_registry() -> "WorkUnitRegistry":
    global _WORK_UNITS_REGISTRY
    if _WORK_UNITS_REGISTRY is None:
        _WORK_UNITS_REGISTRY = WorkUnitRegistry(resolve_work_units_db_path())
    return _WORK_UNITS_REGISTRY


def _reset_work_units_registry_singleton() -> None:
    """Test-only: drop the process-global registry so a fixture can repoint the db path."""
    global _WORK_UNITS_REGISTRY
    if _WORK_UNITS_REGISTRY is not None:
        _WORK_UNITS_REGISTRY.close()
    _WORK_UNITS_REGISTRY = None
