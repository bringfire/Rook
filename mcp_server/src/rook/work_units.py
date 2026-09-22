"""P7 — coordinator-plane registry (merge contracts + declared targets + planned contracts).

Slice 1: Work Units + their P6 artifact provenance + Merge Contracts (a sources->target
dependency DAG); records and validates fan-in INTENT only — read-only over P6.
Slice 2: declared targets — declare intent toward a master/anchor file BEFORE it exists, then
promote it once it materializes.
Slice 3: planned merge contracts — record a FUTURE fan-in graph over typed refs (artifact /
declared_target) before every artifact exists, then activate each into a strict Slice-1
merge_contract (one-at-a-time, idempotent in-tx CAS). Slice 3 makes NO P6 writes.

Records intent ONLY — no merge executes, no geometry enters Rhino. P6 is read-only EXCEPT the one
explicit Slice-2 write: declared_target_promote_tool registers the now-materialized file through
P6's PUBLIC register_artifact() — a plain artifact row carrying NO P7 vocabulary.
Invariant: P7 references P6 by artifact_id; P6 never references P7.
See docs/superpowers/specs/2026-06-05-p7-slice1-merge-contract-registry-design.md,
docs/superpowers/specs/2026-06-06-p7-slice2-declared-target-state-machine-design.md, and
docs/superpowers/specs/2026-06-06-p7-slice3-planned-merge-contracts-design.md.
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


from . import artifacts as _artifacts   # read-only P6 access (resolve + present check)

WORK_UNITS_REGISTRY_VERSION = "p7.3"
# Additive-compatible predecessors: an older db at one of these is migrated FORWARD (new tables
# created, meta upgraded), never failed closed. Unknown/newer versions still fail closed.
_SUPPORTED_PRIOR_VERSIONS = frozenset({"p7.1", "p7.2"})

MERGE_KINDS = ("worksession", "import", "linked_block", "reference", "block", "report")
REFRESH_POLICIES = ("refresh_after_save", "refresh_on_demand")
RELATIONS = ("produced", "consumed")
REF_KINDS = ("artifact", "declared_target")

# Required columns per table — a foreign/malformed existing table (current-version or missing-meta
# db) fails closed to schema_unsupported BEFORE any index/use (mirror P5/P6).
_REQUIRED_COLUMNS = {
    "work_units": {"work_unit_id", "label", "role", "metadata", "created_at"},
    "work_unit_artifacts": {"work_unit_id", "artifact_id", "relation", "created_at"},
    "merge_contracts": {"contract_id", "target_artifact_id", "merge_kind", "refresh_policy", "created_at"},
    "merge_contract_sources": {"contract_id", "source_artifact_id"},
    "work_unit_merge_contracts": {"work_unit_id", "contract_id", "created_at"},
    "declared_targets": {"declared_target_id", "work_unit_id", "intended_path", "normalized_path",
                         "predicted_artifact_id", "status", "bound_artifact_id", "label",
                         "created_at", "materialized_at"},
    "planned_merge_contracts": {"planned_contract_id", "target_ref_kind", "target_ref_id", "merge_kind",
                                "refresh_policy", "status", "activated_contract_id", "activated_at", "created_at"},
    "planned_merge_contract_sources": {"planned_contract_id", "source_ref_kind", "source_ref_id"},
    "work_unit_planned_merge_contracts": {"work_unit_id", "planned_contract_id", "created_at"},
}


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


_DECLARED_TARGET_COLUMNS = ("declared_target_id, work_unit_id, intended_path, normalized_path, "
                            "predicted_artifact_id, status, bound_artifact_id, label, "
                            "created_at, materialized_at")


@dataclass(frozen=True)
class DeclaredTargetRow:
    declared_target_id: str
    work_unit_id: str | None
    intended_path: str
    normalized_path: str
    predicted_artifact_id: str
    status: str
    bound_artifact_id: str | None
    label: str | None
    created_at: int
    materialized_at: int | None


_PLANNED_CONTRACT_COLUMNS = ("planned_contract_id, target_ref_kind, target_ref_id, merge_kind, "
                             "refresh_policy, status, activated_contract_id, activated_at, created_at")


@dataclass(frozen=True)
class PlannedContractRow:
    planned_contract_id: str
    target_ref_kind: str
    target_ref_id: str
    merge_kind: str
    refresh_policy: str
    status: str
    activated_contract_id: str | None
    activated_at: int | None
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
        if stored is not None and stored[0] != WORK_UNITS_REGISTRY_VERSION \
                and stored[0] not in _SUPPORTED_PRIOR_VERSIONS:
            self.schema_unsupported = stored[0]
            return
        # Fail closed on a foreign/malformed existing table before indexing or normal use.
        for table, required in _REQUIRED_COLUMNS.items():
            exists = c.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?;", (table,)).fetchone() is not None
            if exists:
                cols = {row[1] for row in c.execute(f"PRAGMA table_info({table});").fetchall()}
                if not required.issubset(cols):
                    self.schema_unsupported = "unknown"
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
        c.execute("""CREATE TABLE IF NOT EXISTS declared_targets (
            declared_target_id TEXT PRIMARY KEY, work_unit_id TEXT, intended_path TEXT NOT NULL,
            normalized_path TEXT NOT NULL, predicted_artifact_id TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL, bound_artifact_id TEXT, label TEXT,
            created_at INTEGER NOT NULL, materialized_at INTEGER);""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_declared_targets_work_unit ON declared_targets(work_unit_id);")
        c.execute("""CREATE TABLE IF NOT EXISTS planned_merge_contracts (
            planned_contract_id TEXT PRIMARY KEY, target_ref_kind TEXT NOT NULL, target_ref_id TEXT NOT NULL,
            merge_kind TEXT NOT NULL, refresh_policy TEXT NOT NULL, status TEXT NOT NULL,
            activated_contract_id TEXT, activated_at INTEGER, created_at INTEGER NOT NULL);""")
        c.execute("""CREATE TABLE IF NOT EXISTS planned_merge_contract_sources (
            planned_contract_id TEXT NOT NULL, source_ref_kind TEXT NOT NULL, source_ref_id TEXT NOT NULL,
            PRIMARY KEY (planned_contract_id, source_ref_kind, source_ref_id));""")
        c.execute("""CREATE TABLE IF NOT EXISTS work_unit_planned_merge_contracts (
            work_unit_id TEXT NOT NULL, planned_contract_id TEXT NOT NULL, created_at INTEGER NOT NULL,
            PRIMARY KEY (work_unit_id, planned_contract_id));""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_pmcs_contract ON planned_merge_contract_sources(planned_contract_id);")
        c.execute("CREATE INDEX IF NOT EXISTS idx_wupmc_wu ON work_unit_planned_merge_contracts(work_unit_id);")
        c.execute("CREATE INDEX IF NOT EXISTS idx_wua_wu ON work_unit_artifacts(work_unit_id);")
        c.execute("CREATE INDEX IF NOT EXISTS idx_mcs_contract ON merge_contract_sources(contract_id);")
        c.execute("CREATE INDEX IF NOT EXISTS idx_wumc_wu ON work_unit_merge_contracts(work_unit_id);")
        if stored is None or stored[0] != WORK_UNITS_REGISTRY_VERSION:
            c.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('work_units_registry_version', ?);",
                      (WORK_UNITS_REGISTRY_VERSION,))

    # ----- work units (single-statement writes; RLock-guarded) -----
    def register_work_unit(self, work_unit_id: str, *, label: str, role: str | None,
                           metadata: str | None, now: int) -> None:
        with self._immediate():
            self._conn.execute(
                "INSERT OR REPLACE INTO work_units(work_unit_id, label, role, metadata, created_at) "
                "VALUES(?,?,?,?,?);", (work_unit_id, label, role, metadata, now))

    def link_artifact(self, work_unit_id: str, artifact_id: str, relation: str, *, now: int) -> None:
        with self._immediate():
            self._conn.execute(
                "INSERT OR IGNORE INTO work_unit_artifacts(work_unit_id, artifact_id, relation, created_at) "
                "VALUES(?,?,?,?);", (work_unit_id, artifact_id, relation, now))

    def get_work_unit(self, work_unit_id: str) -> "WorkUnitRow | None":
        with self._lock:
            raw = self._conn.execute(
                "SELECT work_unit_id, label, role, metadata, created_at FROM work_units "
                "WHERE work_unit_id=?;", (work_unit_id,)).fetchone()
            return None if raw is None else WorkUnitRow(*raw)

    def list_work_units(self) -> "list[WorkUnitRow]":
        with self._lock:
            return [WorkUnitRow(*r) for r in self._conn.execute(
                "SELECT work_unit_id, label, role, metadata, created_at FROM work_units "
                "ORDER BY created_at, work_unit_id;").fetchall()]

    def artifacts_for(self, work_unit_id: str) -> "list[tuple[str, str]]":
        with self._lock:
            return [(a, rel) for a, rel in self._conn.execute(
                "SELECT artifact_id, relation FROM work_unit_artifacts WHERE work_unit_id=? "
                "ORDER BY created_at, artifact_id;", (work_unit_id,)).fetchall()]

    def work_units_for_artifact(self, artifact_id: str) -> "list[tuple[str, str]]":
        with self._lock:
            return [(wu, rel) for wu, rel in self._conn.execute(
                "SELECT work_unit_id, relation FROM work_unit_artifacts WHERE artifact_id=? "
                "ORDER BY work_unit_id;", (artifact_id,)).fetchall()]

    # ----- merge contracts (atomic write + in-transaction candidate cycle pre-check) -----
    def insert_contract(self, contract_id: str, *, target: str, sources: "list[str]",
                        merge_kind: str, refresh_policy: str, work_unit_id: str | None, now: int) -> str:
        """ONE transaction: stage candidate against existing, run the SHARED cycle detector; a cycle
        raises ContractCycleError (ROLLBACK -> nothing written); else insert contract + sources + join.
        Re-entrant: list_contracts/sources_for re-acquire the RLock inside the tx (safe)."""
        with self._immediate():
            pairs = [(c.contract_id, c.target_artifact_id, self.sources_for(c.contract_id))
                     for c in self.list_contracts()]
            pairs.append((contract_id, target, list(sources)))
            cycle = _contract_cycle(pairs)
            if cycle is not None:
                raise ContractCycleError(cycle)
            self._conn.execute(
                "INSERT INTO merge_contracts(contract_id, target_artifact_id, merge_kind, "
                "refresh_policy, created_at) VALUES(?,?,?,?,?);",
                (contract_id, target, merge_kind, refresh_policy, now))
            self._conn.executemany(
                "INSERT INTO merge_contract_sources(contract_id, source_artifact_id) VALUES(?,?);",
                [(contract_id, s) for s in sources])
            if work_unit_id is not None:
                self._conn.execute(
                    "INSERT OR IGNORE INTO work_unit_merge_contracts(work_unit_id, contract_id, created_at) "
                    "VALUES(?,?,?);", (work_unit_id, contract_id, now))
        return contract_id

    def get_contract(self, contract_id: str) -> "ContractRow | None":
        with self._lock:
            raw = self._conn.execute(
                "SELECT contract_id, target_artifact_id, merge_kind, refresh_policy, created_at "
                "FROM merge_contracts WHERE contract_id=?;", (contract_id,)).fetchone()
            return None if raw is None else ContractRow(*raw)

    def list_contracts(self) -> "list[ContractRow]":
        with self._lock:
            return [ContractRow(*r) for r in self._conn.execute(
                "SELECT contract_id, target_artifact_id, merge_kind, refresh_policy, created_at "
                "FROM merge_contracts ORDER BY created_at, contract_id;").fetchall()]

    def sources_for(self, contract_id: str) -> "list[str]":
        with self._lock:
            return [s for (s,) in self._conn.execute(
                "SELECT source_artifact_id FROM merge_contract_sources WHERE contract_id=? "
                "ORDER BY source_artifact_id;", (contract_id,)).fetchall()]

    def contracts_for(self, work_unit_id: str) -> "list[str]":
        with self._lock:
            return [c for (c,) in self._conn.execute(
                "SELECT contract_id FROM work_unit_merge_contracts WHERE work_unit_id=? "
                "ORDER BY created_at, contract_id;", (work_unit_id,)).fetchall()]

    # ----- declared targets (P7 Slice 2) -----
    def insert_declared_target(self, declared_target_id: str, *, work_unit_id: str | None,
                               intended_path: str, normalized_path: str, predicted_artifact_id: str,
                               label: str | None, now: int) -> str:
        """Insert a 'declared' row. UNIQUE(predicted_artifact_id) => one declaration per path; an
        existing one raises DeclaredTargetConflict (ROLLBACK, nothing written)."""
        with self._immediate():
            existing = self._conn.execute(
                "SELECT declared_target_id FROM declared_targets WHERE predicted_artifact_id=?;",
                (predicted_artifact_id,)).fetchone()
            if existing is not None:
                raise DeclaredTargetConflict(existing[0])
            self._conn.execute(
                "INSERT INTO declared_targets(declared_target_id, work_unit_id, intended_path, "
                "normalized_path, predicted_artifact_id, status, bound_artifact_id, label, "
                "created_at, materialized_at) VALUES(?,?,?,?,?,'declared',NULL,?,?,NULL);",
                (declared_target_id, work_unit_id, intended_path, normalized_path,
                 predicted_artifact_id, label, now))
        return declared_target_id

    def set_declared_target_materialized(self, declared_target_id: str, *, bound_artifact_id: str,
                                         now: int) -> None:
        with self._immediate():
            self._conn.execute(
                "UPDATE declared_targets SET status='materialized', bound_artifact_id=?, "
                "materialized_at=? WHERE declared_target_id=?;",
                (bound_artifact_id, now, declared_target_id))

    def get_declared_target(self, declared_target_id: str) -> "DeclaredTargetRow | None":
        with self._lock:
            raw = self._conn.execute(
                f"SELECT {_DECLARED_TARGET_COLUMNS} FROM declared_targets WHERE declared_target_id=?;",
                (declared_target_id,)).fetchone()
            return None if raw is None else DeclaredTargetRow(*raw)

    def list_declared_targets(self) -> "list[DeclaredTargetRow]":
        with self._lock:
            return [DeclaredTargetRow(*r) for r in self._conn.execute(
                f"SELECT {_DECLARED_TARGET_COLUMNS} FROM declared_targets "
                "ORDER BY created_at, declared_target_id;").fetchall()]

    def declared_targets_for(self, work_unit_id: str) -> "list[str]":
        with self._lock:
            return [d for (d,) in self._conn.execute(
                "SELECT declared_target_id FROM declared_targets WHERE work_unit_id=? "
                "ORDER BY created_at, declared_target_id;", (work_unit_id,)).fetchall()]

    # ----- planned merge contracts (P7 Slice 3) -----
    def insert_planned_contract(self, planned_contract_id: str, *, target_ref_kind: str, target_ref_id: str,
                                sources: "list[tuple[str, str]]", merge_kind: str, refresh_policy: str,
                                work_unit_id: str | None, now: int) -> str:
        """ONE tx: canonical cycle pre-check over existing + candidate (shared _contract_cycle) ->
        PlannedContractCycle (ROLLBACK, nothing written); else insert planned row + sources + optional
        ownership link. Re-entrant reads (list_planned_contracts/sources_for_planned) are RLock-safe."""
        with self._immediate():
            pairs = _planned_graph_pairs(self)
            cand_tkey = _planned_key_or_sentinel(self, target_ref_kind, target_ref_id)
            cand_skeys = [_planned_key_or_sentinel(self, k, i) for k, i in sources]
            pairs.append((planned_contract_id, cand_tkey, cand_skeys))
            cycle = _contract_cycle(pairs)
            if cycle is not None:
                raise PlannedContractCycle(cycle)
            self._conn.execute(
                "INSERT INTO planned_merge_contracts(planned_contract_id, target_ref_kind, target_ref_id, "
                "merge_kind, refresh_policy, status, activated_contract_id, activated_at, created_at) "
                "VALUES(?,?,?,?,?,'planned',NULL,NULL,?);",
                (planned_contract_id, target_ref_kind, target_ref_id, merge_kind, refresh_policy, now))
            self._conn.executemany(
                "INSERT INTO planned_merge_contract_sources(planned_contract_id, source_ref_kind, source_ref_id) "
                "VALUES(?,?,?);", [(planned_contract_id, k, i) for k, i in sources])
            if work_unit_id is not None:
                self._conn.execute(
                    "INSERT OR IGNORE INTO work_unit_planned_merge_contracts(work_unit_id, planned_contract_id, "
                    "created_at) VALUES(?,?,?);", (work_unit_id, planned_contract_id, now))
        return planned_contract_id

    def get_planned_contract(self, planned_contract_id: str) -> "PlannedContractRow | None":
        with self._lock:
            raw = self._conn.execute(
                f"SELECT {_PLANNED_CONTRACT_COLUMNS} FROM planned_merge_contracts WHERE planned_contract_id=?;",
                (planned_contract_id,)).fetchone()
            return None if raw is None else PlannedContractRow(*raw)

    def list_planned_contracts(self) -> "list[PlannedContractRow]":
        with self._lock:
            return [PlannedContractRow(*r) for r in self._conn.execute(
                f"SELECT {_PLANNED_CONTRACT_COLUMNS} FROM planned_merge_contracts "
                "ORDER BY created_at, planned_contract_id;").fetchall()]

    def sources_for_planned(self, planned_contract_id: str) -> "list[tuple[str, str]]":
        with self._lock:
            return [(k, i) for k, i in self._conn.execute(
                "SELECT source_ref_kind, source_ref_id FROM planned_merge_contract_sources "
                "WHERE planned_contract_id=? ORDER BY source_ref_kind, source_ref_id;",
                (planned_contract_id,)).fetchall()]

    def planned_contracts_for(self, work_unit_id: str) -> "list[str]":
        with self._lock:
            return [p for (p,) in self._conn.execute(
                "SELECT planned_contract_id FROM work_unit_planned_merge_contracts WHERE work_unit_id=? "
                "ORDER BY created_at, planned_contract_id;", (work_unit_id,)).fetchall()]

    def work_units_for_planned_contract(self, planned_contract_id: str) -> "list[str]":
        with self._lock:
            return [w for (w,) in self._conn.execute(
                "SELECT work_unit_id FROM work_unit_planned_merge_contracts WHERE planned_contract_id=? "
                "ORDER BY work_unit_id;", (planned_contract_id,)).fetchall()]

    def activate_planned_contract(self, planned_contract_id: str, *, candidate_contract_id: str,
                                  target: str, sources: "list[str]", merge_kind: str, refresh_policy: str,
                                  work_unit_ids: "list[str]", now: int) -> "tuple[str, bool]":
        """ONE tx with a durable CAS. Re-read + classify by the stored-state invariant: valid-activated ->
        (existing_id, True); invalid -> PlannedContractInvalid (rollback); valid-planned -> strict cycle
        pre-check + insert merge_contracts/sources/ownership + stamp planned -> (candidate, False). Two
        concurrent activations serialize on BEGIN IMMEDIATE; the loser returns the existing id."""
        with self._immediate():
            row = self.get_planned_contract(planned_contract_id)
            if row is None or _classify_planned_state(row) == "invalid":
                raise PlannedContractInvalid()
            if _classify_planned_state(row) == "activated":
                return row.activated_contract_id, True
            pairs = [(c.contract_id, c.target_artifact_id, self.sources_for(c.contract_id))
                     for c in self.list_contracts()]
            pairs.append((candidate_contract_id, target, list(sources)))
            cyc = _contract_cycle(pairs)
            if cyc is not None:
                raise ContractCycleError(cyc)
            self._conn.execute(
                "INSERT INTO merge_contracts(contract_id, target_artifact_id, merge_kind, refresh_policy, "
                "created_at) VALUES(?,?,?,?,?);", (candidate_contract_id, target, merge_kind, refresh_policy, now))
            self._conn.executemany(
                "INSERT INTO merge_contract_sources(contract_id, source_artifact_id) VALUES(?,?);",
                [(candidate_contract_id, s) for s in sources])
            for wu in work_unit_ids:
                self._conn.execute(
                    "INSERT OR IGNORE INTO work_unit_merge_contracts(work_unit_id, contract_id, created_at) "
                    "VALUES(?,?,?);", (wu, candidate_contract_id, now))
            self._conn.execute(
                "UPDATE planned_merge_contracts SET status='activated', activated_contract_id=?, "
                "activated_at=? WHERE planned_contract_id=?;", (candidate_contract_id, now, planned_contract_id))
        return candidate_contract_id, False


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


# ----- P6 resolution (read-only): two bars, by intent -----
def _p6_row(artifact_id: str):
    """Read-only P6 lookup. Returns the ArtifactRow or None. Never writes artifacts.db."""
    return _artifacts.artifact_registry().get(artifact_id=artifact_id)


def _resolve_present(artifact_ids) -> "list[dict[str, Any]]":
    """The present-bar: each id must resolve to a P6 row currently file_state=='present'.
    Returns a problems list ([] when all pass). Shared by record and validate."""
    problems: list[dict[str, Any]] = []
    for aid in artifact_ids:
        row = _p6_row(aid)
        if row is None:
            problems.append({"code": "artifact_not_registered", "artifactId": aid})
        elif row.file_state != "present":
            problems.append({"code": "artifact_not_present", "artifactId": aid})
    return problems


def _is_registered(artifact_id: str) -> bool:
    """The link-bar: provenance is historical — a since-missing artifact is still a valid link.
    Registered is enough; present is NOT required."""
    return _p6_row(artifact_id) is not None


# ----- shared contract-graph helpers (used by insert_contract AND validate) -----
class ContractCycleError(RuntimeError):
    """insert_contract's atomic pre-check: the candidate would make the contract graph cyclic.
    Raised inside the transaction -> ROLLBACK -> nothing written."""
    def __init__(self, cycle: "list[str]"):
        super().__init__("merge_cycle_detected")
        self.cycle = cycle


class DeclaredTargetConflict(RuntimeError):
    """insert_declared_target: the intended path (predicted_artifact_id) is already declared.
    Carries the existing declaration id so the tool layer can surface it."""
    def __init__(self, existing_id: str):
        super().__init__("declared_target_path_conflict")
        self.existing_id = existing_id


class PlannedContractCycle(RuntimeError):
    """insert_planned_contract's atomic pre-check: the candidate would make the canonical planned graph cyclic."""
    def __init__(self, cycle: "list[str]"):
        super().__init__("planned_contract_cycle_detected")
        self.cycle = cycle


class PlannedContractInvalid(RuntimeError):
    """activate_planned_contract's in-tx CAS: the planned row violates the stored-state invariant."""
    pass


def _contract_graph(pairs):
    """pairs: list of (contract_id, target_artifact_id, sources_list). Directed edge A->B iff
    target(A) appears in sources(B). Returns (graph, target_of, sources_of)."""
    import networkx as nx  # deferred: not needed at server import
    target_of = {cid: t for cid, t, _ in pairs}
    sources_of = {cid: list(s) for cid, _, s in pairs}
    g = nx.DiGraph()
    g.add_nodes_from(target_of)
    for a_cid, a_t, _ in pairs:
        for b_cid in target_of:
            if a_cid != b_cid and a_t in sources_of[b_cid]:
                g.add_edge(a_cid, b_cid, viaArtifact=a_t)
    return g, target_of, sources_of


def _contract_cycle(pairs) -> "list[str] | None":
    """Return a cycle (list of contract_ids) if the contract graph has one, else None. SHARED by
    insert_contract's atomic pre-check and validate's whole-graph check."""
    import networkx as nx  # deferred: not needed at server import
    g, _, _ = _contract_graph(pairs)
    try:
        cyc = nx.find_cycle(g)   # list of (u, v) edges (2-tuples; no orientation)
    except nx.NetworkXNoCycle:
        return None
    return [u for u, _ in cyc] + [cyc[-1][1]]


def _ordered_contract_ids(pairs, order_key):
    """The ONE source of truth for strict-contract execution order. pairs: list of
    (contract_id, target_artifact_id, sources_list); order_key: cid -> (created_at, contract_id).
    Returns (order, None) on success or (None, cycle) on a cyclic graph. Reused by
    _validate_graph (whole graph) and plan_linked_block_execution (whole-graph order, then
    filtered to a requested subset)."""
    import networkx as nx  # deferred: not needed at server import
    g, _, _ = _contract_graph(pairs)
    try:
        return list(nx.lexicographical_topological_sort(g, key=lambda n: order_key[n])), None
    except nx.NetworkXUnfeasible:
        return None, _contract_cycle(pairs)


# ----- planned-contract canonical-key helpers (P7 Slice 3) -----
def _planned_artifact_key(reg, ref_kind: str, ref_id: str) -> "tuple[str | None, dict | None]":
    """Project a typed ref to its canonical FUTURE-ARTIFACT key: artifact -> the artifact id itself;
    declared_target -> its predicted_artifact_id. Returns (key, None) or (None, problem)."""
    if ref_kind == "artifact":
        return ref_id, None
    if ref_kind == "declared_target":
        dt = reg.get_declared_target(ref_id)
        if dt is None:
            return None, {"code": "declared_target_not_found", "ref": {"kind": ref_kind, "id": ref_id}}
        return dt.predicted_artifact_id, None
    return None, {"code": "invalid_ref_kind", "ref": {"kind": ref_kind, "id": ref_id}}


def _planned_key_or_sentinel(reg, ref_kind: str, ref_id: str) -> str:
    """Canonical key for graph building; an unresolvable ref gets a unique sentinel so it never falsely
    unifies with another node (defensive — record validates resolution before persisting)."""
    key, _ = _planned_artifact_key(reg, ref_kind, ref_id)
    return key if key is not None else f"__unresolved__:{ref_kind}:{ref_id}"


def _planned_graph_pairs(reg) -> "list[tuple]":
    """(planned_contract_id, target_key, [source_keys]) over canonical keys, for ALL planned rows
    (planned AND activated)."""
    pairs = []
    for pc in reg.list_planned_contracts():
        tkey = _planned_key_or_sentinel(reg, pc.target_ref_kind, pc.target_ref_id)
        skeys = [_planned_key_or_sentinel(reg, k, i) for k, i in reg.sources_for_planned(pc.planned_contract_id)]
        pairs.append((pc.planned_contract_id, tkey, skeys))
    return pairs


def _planned_structural_problems(target_key: str, source_keys: "list[str]", merge_kind: str,
                                 refresh_policy: str) -> "list[dict[str, Any]]":
    """Local well-formedness over CANONICAL keys (not ref-row identity)."""
    problems: list[dict[str, Any]] = []
    if not source_keys:
        problems.append({"code": "empty_sources"})
    if len(source_keys) != len(set(source_keys)):
        problems.append({"code": "duplicate_planned_source"})
    if merge_kind not in MERGE_KINDS:
        problems.append({"code": "unknown_merge_kind", "value": merge_kind})
    if refresh_policy not in REFRESH_POLICIES:
        problems.append({"code": "unknown_refresh_policy", "value": refresh_policy})
    if target_key in source_keys:
        problems.append({"code": "planned_self_reference"})
    return problems


def _parse_ref(ref) -> "tuple[tuple[str, str] | None, dict | None]":
    """Validate a typed-ref object {kind, id}. Returns ((kind, id), None) or (None, {code, message})."""
    if not isinstance(ref, dict):
        return None, {"code": "invalid_argument", "message": "ref must be an object {kind, id}."}
    kind, rid = ref.get("kind"), ref.get("id")
    if not isinstance(rid, str) or not rid.strip():
        return None, {"code": "invalid_argument", "message": "ref 'id' must be a non-empty string."}
    if kind not in REF_KINDS:
        return None, {"code": "invalid_ref_kind", "message": f"ref 'kind' must be one of {REF_KINDS}.", "value": kind}
    return (kind, rid), None


def _classify_planned_state(row: "PlannedContractRow") -> str:
    """'planned' | 'activated' | 'invalid' by the FULL stored-state invariant (never status alone)."""
    if row.status == "planned" and row.activated_contract_id is None and row.activated_at is None:
        return "planned"
    if row.status == "activated" and row.activated_contract_id is not None and row.activated_at is not None:
        return "activated"
    return "invalid"


def _blk(code: str, **extra: Any) -> "dict[str, Any]":
    """A blocker dict carrying its retryable flag (derived from _RETRYABLE)."""
    return {"code": code, "retryable": _RETRYABLE.get(code, False), **extra}


def _resolve_planned_ref_present(reg, ref_kind: str, ref_id: str) -> "tuple[str | None, dict | None]":
    """Resolve a typed ref to a PRESENT P6 artifact id, or return a (bare) blocker. Assumes P6 is usable
    (the caller guards p6_available). declared_target -> materialized, bound==predicted, bound present."""
    ref = {"kind": ref_kind, "id": ref_id}
    if ref_kind == "artifact":
        row = _p6_row(ref_id)
        if row is None:
            return None, {"code": "artifact_not_registered", "ref": ref}
        if row.file_state != "present":
            return None, {"code": "artifact_not_present", "ref": ref}
        return ref_id, None
    if ref_kind == "declared_target":
        dt = reg.get_declared_target(ref_id)
        if dt is None:
            return None, {"code": "declared_target_not_found", "ref": ref}
        if dt.status != "materialized":
            return None, {"code": "declared_target_not_materialized", "ref": ref}
        if dt.bound_artifact_id is None:
            return None, {"code": "declared_target_bound_missing", "ref": ref}
        if dt.bound_artifact_id != dt.predicted_artifact_id:
            return None, {"code": "declared_target_bound_identity_changed", "ref": ref}
        b = _p6_row(dt.bound_artifact_id)
        if b is None or b.file_state != "present":
            return None, {"code": "declared_target_bound_not_present", "ref": ref}
        return dt.bound_artifact_id, None
    return None, {"code": "invalid_ref_kind", "ref": ref}


def _activation_blockers(reg, planned: "PlannedContractRow",
                         p6_available: bool) -> "tuple[list[dict], dict | None]":
    """ALL blockers for activating `planned` (each carrying retryable), plus {target, sources} resolved
    artifact ids when fully clear. Stored-state-invalid -> one blocker. P6 skew -> one blocker. Strict-graph
    cycle blocker ONLY when every ref resolves."""
    if _classify_planned_state(planned) == "invalid":
        return [_blk("planned_contract_already_invalid")], None
    if not p6_available:
        return [_blk("artifact_registry_unavailable")], None
    raw: list[dict] = []
    tkey = _planned_key_or_sentinel(reg, planned.target_ref_kind, planned.target_ref_id)
    src_refs = reg.sources_for_planned(planned.planned_contract_id)
    skeys = [_planned_key_or_sentinel(reg, k, i) for k, i in src_refs]
    raw += _planned_structural_problems(tkey, skeys, planned.merge_kind, planned.refresh_policy)
    rt, pt = _resolve_planned_ref_present(reg, planned.target_ref_kind, planned.target_ref_id)
    if pt is not None:
        raw.append(pt)
    resolved_sources: list[str] = []
    for k, i in src_refs:
        r, p = _resolve_planned_ref_present(reg, k, i)
        if p is not None:
            raw.append(p)
        else:
            resolved_sources.append(r)
    # strict-graph cycle ONLY when everything resolved
    if not raw and rt is not None and len(resolved_sources) == len(src_refs):
        pairs = [(c.contract_id, c.target_artifact_id, reg.sources_for(c.contract_id)) for c in reg.list_contracts()]
        pairs.append((planned.planned_contract_id, rt, resolved_sources))
        cyc = _contract_cycle(pairs)
        if cyc is not None:
            raw.append({"code": "strict_merge_cycle_detected", "cycle": cyc})
    blockers = [_blk(b["code"], **{k: v for k, v in b.items() if k != "code"}) for b in raw]
    resolved = None if blockers else {"target": rt, "sources": resolved_sources}
    return blockers, resolved


def _observe_planned_contract(reg, row: "PlannedContractRow", p6_available: bool) -> "dict[str, Any]":
    """Per-row observations; transitions nothing. An ACTIVATED row is classified FIRST and short-circuits
    — it never re-enters the activation-blocker path (post-activation artifact drift is Slice-1
    validate_merge_contract's concern, not the planned inspector's). A planned/invalid row reports its
    activation blockers; partial resolved ids are best-effort (planned + P6-usable only)."""
    state = _classify_planned_state(row)
    if state == "activated":
        return {"activatable": False, "alreadyActivated": True,
                "activatedContractId": row.activated_contract_id, "blockers": []}
    blockers, _ = _activation_blockers(reg, row, p6_available)   # 'planned' or 'invalid'
    obs: dict[str, Any] = {"activatable": (len(blockers) == 0), "alreadyActivated": False, "blockers": blockers}
    if state == "planned" and p6_available:
        rt, _pt = _resolve_planned_ref_present(reg, row.target_ref_kind, row.target_ref_id)
        if rt is not None:
            obs["resolvedTargetArtifactId"] = rt
        rs = []
        for k, i in reg.sources_for_planned(row.planned_contract_id):
            r, _p = _resolve_planned_ref_present(reg, k, i)
            if r is not None:
                rs.append(r)
        obs["resolvedSourceArtifactIds"] = rs
    else:
        obs["resolvedSourceArtifactIds"] = []
    return obs


def _planned_graph_view(reg) -> "dict[str, Any]":
    """Whole-graph view over canonical keys: plannedContractOrder (incl. activated rows), edges, graphOk,
    graphProblems. Never stored."""
    import networkx as nx  # deferred: not needed at server import
    contracts = reg.list_planned_contracts()
    pairs = _planned_graph_pairs(reg)
    g, target_of, sources_of = _contract_graph(pairs)
    problems: list[dict[str, Any]] = []
    for pc in contracts:
        problems += [{**p, "plannedContractId": pc.planned_contract_id} for p in _planned_structural_problems(
            target_of[pc.planned_contract_id], sources_of[pc.planned_contract_id], pc.merge_kind, pc.refresh_policy)]
    order: list[str] | None = None
    okey = {pc.planned_contract_id: (pc.created_at, pc.planned_contract_id) for pc in contracts}
    try:
        order = list(nx.lexicographical_topological_sort(g, key=lambda n: okey[n]))
    except nx.NetworkXUnfeasible:
        problems.append({"code": "planned_contract_cycle_detected", "cycle": _contract_cycle(pairs)})
    return {"plannedContractOrder": order,
            "edges": [{"from": u, "to": v, "viaArtifactKey": d["viaArtifact"]} for u, v, d in g.edges(data=True)],
            "graphOk": (len(problems) == 0), "graphProblems": problems}


def _structural_problems(target: str, sources: "list[str]", merge_kind: str,
                         refresh_policy: str) -> "list[dict[str, Any]]":
    """Local well-formedness shared by record + validate (NOT present, NOT acyclicity)."""
    problems: list[dict[str, Any]] = []
    if not sources:
        problems.append({"code": "empty_sources"})
    if len(sources) != len(set(sources)):
        problems.append({"code": "duplicate_contract_source"})
    if merge_kind not in MERGE_KINDS:
        problems.append({"code": "unknown_merge_kind", "value": merge_kind})
    if refresh_policy not in REFRESH_POLICIES:
        problems.append({"code": "unknown_refresh_policy", "value": refresh_policy})
    if target in sources:
        problems.append({"code": "merge_self_reference", "artifactId": target})
    return problems


def _validate_graph(reg: "WorkUnitRegistry") -> "dict[str, Any]":
    """Pure, on-demand validation of the WHOLE contract graph. Never stored."""
    contracts = reg.list_contracts()
    problems: list[dict[str, Any]] = []
    target_of: dict[str, str] = {}
    sources_of: dict[str, list[str]] = {}
    order_key: dict[str, tuple] = {}
    for ct in contracts:
        srcs = reg.sources_for(ct.contract_id)
        target_of[ct.contract_id] = ct.target_artifact_id
        sources_of[ct.contract_id] = srcs
        order_key[ct.contract_id] = (ct.created_at, ct.contract_id)
        problems += [{**p, "contractId": ct.contract_id} for p in
                     _structural_problems(ct.target_artifact_id, srcs, ct.merge_kind, ct.refresh_policy)]
        problems += [{**p, "contractId": ct.contract_id} for p in
                     _resolve_present(srcs + [ct.target_artifact_id])]

    # Contract dependency graph via the SHARED builder: edge A -> B iff target(A) in sources(B).
    pairs = [(ct.contract_id, target_of[ct.contract_id], sources_of[ct.contract_id]) for ct in contracts]
    g, _, _ = _contract_graph(pairs)

    contract_order, cycle = _ordered_contract_ids(pairs, order_key)
    if cycle is not None:
        problems.append({"code": "merge_cycle_detected", "cycle": cycle})

    if problems:
        return {"ok": False, "problems": problems}

    artifact_order: list[str] = []
    for cid in contract_order:
        for s in sources_of[cid]:
            if s not in artifact_order:
                artifact_order.append(s)
        if target_of[cid] not in artifact_order:
            artifact_order.append(target_of[cid])
    return {
        "ok": True,
        "contractOrder": contract_order,
        "artifactOrder": artifact_order,
        "edges": [{"from": u, "to": v, "viaArtifact": d["viaArtifact"]} for u, v, d in g.edges(data=True)],
        "contracts": [{"contractId": c.contract_id, "target": target_of[c.contract_id],
                       "sources": sources_of[c.contract_id], "mergeKind": c.merge_kind,
                       "refreshPolicy": c.refresh_policy} for c in contracts],
    }


def _validate_one(reg: "WorkUnitRegistry", contract_id: str) -> "dict[str, Any]":
    """Validate ONE contract: its own structural + present-bar problems, plus a cycle problem ONLY
    if THIS contract participates in the cycle. Unrelated contracts' problems are NOT reported
    (so a valid contract is not failed by an unrelated one's missing artifact)."""
    ct = reg.get_contract(contract_id)
    srcs = reg.sources_for(contract_id)
    problems = [{**p, "contractId": contract_id} for p in
                _structural_problems(ct.target_artifact_id, srcs, ct.merge_kind, ct.refresh_policy)]
    problems += [{**p, "contractId": contract_id} for p in
                 _resolve_present(srcs + [ct.target_artifact_id])]
    pairs = [(c.contract_id, c.target_artifact_id, reg.sources_for(c.contract_id))
             for c in reg.list_contracts()]
    cycle = _contract_cycle(pairs)
    if cycle is not None and contract_id in cycle:
        problems.append({"code": "merge_cycle_detected", "cycle": cycle, "contractId": contract_id})
    if problems:
        return {"ok": False, "contractId": contract_id, "problems": problems}
    return {"ok": True, "contractId": contract_id}


_PLANNABLE_MERGE_KIND = "linked_block"


def plan_linked_block_execution(reg, contract_ids):
    """Pure, Rhino-free. Derive the deterministic linked-block execution plan for a requested
    subset of strict contracts. Consumes contract ids, not sessions. Does NOT execute, inspect
    Rhino, check the present-bar, or define any execution-result envelope.

    Omitted-producer policy: ALLOW. A requested contract may depend on a contract not in the
    request; ordering still holds and no problem is raised. Artifact availability is the
    executor's runtime present-bar, not a pure planner's call.

    Returns {"ok": True, "plan": [{"contractId", "targetArtifactId"}, ...]} in execution order,
    or {"ok": False, "problems": [{"code", ...}]}.
    """
    requested = list(dict.fromkeys(contract_ids))   # dedupe, preserve first-seen
    requested_set = set(requested)

    problems: list[dict[str, Any]] = []
    for cid in requested:
        ct = reg.get_contract(cid)
        if ct is None:
            problems.append({"code": "contract_not_found", "contractId": cid})
        elif ct.merge_kind != _PLANNABLE_MERGE_KIND:
            problems.append({"code": "unsupported_merge_kind", "contractId": cid,
                             "mergeKind": ct.merge_kind})
    if problems:
        return {"ok": False, "problems": problems}

    # Order over the WHOLE contract graph (one source of truth), then filter to the requested
    # ids — a scoped subgraph drops transitive edges through omitted contracts and can invert
    # order. target_of/order_key/pairs must cover every node, so build them across all contracts.
    contracts = reg.list_contracts()
    target_of = {ct.contract_id: ct.target_artifact_id for ct in contracts}
    order_key = {ct.contract_id: (ct.created_at, ct.contract_id) for ct in contracts}
    pairs = [(ct.contract_id, ct.target_artifact_id, reg.sources_for(ct.contract_id))
             for ct in contracts]
    order, cycle = _ordered_contract_ids(pairs, order_key)
    if cycle is not None:   # defensive: insert_contract prevents cycles atomically
        return {"ok": False, "problems": [{"code": "merge_cycle_detected", "cycle": cycle}]}

    plan = [{"contractId": cid, "targetArtifactId": target_of[cid]}
            for cid in order if cid in requested_set]
    return {"ok": True, "plan": plan}


# ----- tool layer ({success, data} envelopes) -----
_RETRYABLE = {
    "artifact_not_registered": False, "artifact_not_present": True,
    "empty_sources": False, "duplicate_contract_source": False,
    "unknown_merge_kind": False, "unknown_refresh_policy": False,
    "merge_self_reference": False, "work_unit_not_found": False, "merge_cycle_detected": False,
    "contract_not_found": False, "invalid_relation": False, "invalid_argument": False,
    "work_units_registry_unavailable": True,
    "invalid_path": False,
    "declared_target_not_found": False, "declared_target_path_conflict": False,
    "declared_target_not_materialized": True, "declared_target_unreachable": True,
    "declared_target_path_identity_changed": False, "declared_target_promotion_failed": False,
    "invalid_ref_kind": False, "duplicate_planned_source": False, "planned_self_reference": False,
    "declared_target_bound_missing": False, "declared_target_bound_identity_changed": False,
    "declared_target_bound_not_present": True,
    "planned_contract_not_found": False, "planned_contract_cycle_detected": False,
    "strict_merge_cycle_detected": False, "planned_contract_already_invalid": False,
    "planned_contract_not_activatable": False, "artifact_registry_unavailable": True,
}


def _err(code: str, message: str, **extra: Any) -> "dict[str, Any]":
    return {"success": False, "data": {
        "code": code, "message": message, "retryable": _RETRYABLE.get(code, True), **extra}}


async def _registry_unusable() -> "dict[str, Any] | None":
    reg = await asyncio.to_thread(work_units_registry)
    bad = getattr(reg, "schema_unsupported", None)
    if bad is not None:
        return _err("work_units_registry_unavailable",
                    f"Work-unit registry was written by an incompatible version {bad!r}; "
                    "rows are left intact. Resolve the version skew before using P7 tools.")
    return None


async def _p6_unusable() -> "dict[str, Any] | None":
    """P7 depends on P6 as the authority — fail closed (structured artifact_registry_unavailable)
    if P6's registry is version-skewed, rather than crash inside a P6 read. Used by the tools that
    resolve artifacts against P6 (link / record / validate), NOT by the pure-P7 register / list."""
    return await _artifacts._artifact_registry_unusable()


async def register_work_unit_tool(*, label: str, role: str | None = None,
                                  metadata: Any = None, work_unit_id: str | None = None) -> "dict[str, Any]":
    if (u := await _registry_unusable()) is not None:
        return u
    if not isinstance(label, str) or not label.strip():
        return _err("invalid_argument", "'label' must be a non-empty string.")
    wid = work_unit_id if (isinstance(work_unit_id, str) and work_unit_id.strip()) else f"wu-{uuid.uuid4().hex[:12]}"
    meta_json = None if metadata is None else json.dumps(metadata)
    await asyncio.to_thread(lambda: work_units_registry().register_work_unit(
        wid, label=label, role=role, metadata=meta_json, now=int(time.time())))
    return {"success": True, "data": {"workUnitId": wid, "label": label}}


async def link_artifact_tool(*, work_unit_id: str, artifact_id: str, relation: str) -> "dict[str, Any]":
    if (u := await _registry_unusable()) is not None:
        return u
    if (p6u := await _p6_unusable()) is not None:
        return p6u
    if relation not in RELATIONS:
        return _err("invalid_relation", f"'relation' must be one of {RELATIONS}, got {relation!r}.")
    if await asyncio.to_thread(lambda: work_units_registry().get_work_unit(work_unit_id)) is None:
        return _err("work_unit_not_found", f"No work unit {work_unit_id!r}.")
    if not await asyncio.to_thread(_is_registered, artifact_id):   # link-bar: registered (present NOT required)
        return _err("artifact_not_registered", f"Artifact {artifact_id!r} is not registered in P6.")
    await asyncio.to_thread(lambda: work_units_registry().link_artifact(
        work_unit_id, artifact_id, relation, now=int(time.time())))
    return {"success": True, "data": {"workUnitId": work_unit_id, "artifactId": artifact_id,
                                      "relation": relation}}


async def record_merge_contract(*, target_artifact_id: str, source_artifact_ids: "list[str]",
                                merge_kind: str, refresh_policy: str,
                                work_unit_id: str | None = None) -> "dict[str, Any]":
    if (u := await _registry_unusable()) is not None:
        return u
    if (p6u := await _p6_unusable()) is not None:
        return p6u
    if not isinstance(target_artifact_id, str) or not target_artifact_id.strip():
        return _err("invalid_argument", "'target_artifact_id' must be a non-empty string.")
    if not isinstance(source_artifact_ids, list) or not all(
            isinstance(s, str) and s.strip() for s in source_artifact_ids):
        return _err("invalid_argument", "'source_artifact_ids' must be a list of non-empty strings.")
    sources = list(source_artifact_ids)
    # 1. local structural
    structural = _structural_problems(target_artifact_id, sources, merge_kind, refresh_policy)
    if structural:
        p = structural[0]
        return _err(p["code"], f"Contract is not well-formed: {p['code']}.",
                    **{k: v for k, v in p.items() if k != "code"})
    # 2. present-bar (same as validate) — every source + target
    present = await asyncio.to_thread(_resolve_present, sources + [target_artifact_id])
    if present:
        p = present[0]
        return _err(p["code"], f"Referenced artifact failed the present-bar: {p['code']}.",
                    artifactId=p.get("artifactId"))
    # 3. optional work unit must exist
    if work_unit_id is not None:
        if await asyncio.to_thread(lambda: work_units_registry().get_work_unit(work_unit_id)) is None:
            return _err("work_unit_not_found", f"No work unit {work_unit_id!r}.")
    # 4. atomic write + in-transaction candidate cycle pre-check (nothing written on reject)
    contract_id = f"mc-{uuid.uuid4().hex[:12]}"
    try:
        await asyncio.to_thread(lambda: work_units_registry().insert_contract(
            contract_id, target=target_artifact_id, sources=sources, merge_kind=merge_kind,
            refresh_policy=refresh_policy, work_unit_id=work_unit_id, now=int(time.time())))
    except ContractCycleError as exc:
        return _err("merge_cycle_detected",
                    "Recording this contract would introduce a cycle into the merge graph; nothing was written.",
                    cycle=exc.cycle)
    return {"success": True, "data": {"contractId": contract_id, "target": target_artifact_id,
                                      "sources": sources, "mergeKind": merge_kind,
                                      "refreshPolicy": refresh_policy}}


async def validate_merge_contract(*, contract_id: str | None = None) -> "dict[str, Any]":
    if (u := await _registry_unusable()) is not None:
        return u
    if (p6u := await _p6_unusable()) is not None:
        return p6u
    if contract_id is not None:
        if await asyncio.to_thread(lambda: work_units_registry().get_contract(contract_id)) is None:
            return _err("contract_not_found", f"No merge contract {contract_id!r}.")
        data = await asyncio.to_thread(lambda: _validate_one(work_units_registry(), contract_id))
    else:
        data = await asyncio.to_thread(lambda: _validate_graph(work_units_registry()))
    return {"success": True, "data": data}


async def list_work_units_tool(*, work_unit_id: str | None = None) -> "dict[str, Any]":
    if (u := await _registry_unusable()) is not None:
        return u
    def _build() -> "list[dict[str, Any]]":
        reg = work_units_registry()
        rows = [reg.get_work_unit(work_unit_id)] if work_unit_id else reg.list_work_units()
        rows = [r for r in rows if r is not None]
        out = []
        for r in rows:
            out.append({"workUnitId": r.work_unit_id, "label": r.label, "role": r.role,
                        "metadata": (json.loads(r.metadata) if r.metadata else None),
                        "createdAt": r.created_at,
                        "artifacts": [{"artifactId": a, "relation": rel}
                                      for a, rel in reg.artifacts_for(r.work_unit_id)],
                        "contracts": reg.contracts_for(r.work_unit_id),
                        "declaredTargets": reg.declared_targets_for(r.work_unit_id),
                        "plannedContracts": reg.planned_contracts_for(r.work_unit_id)})
        return out
    return {"success": True, "data": {"workUnits": await asyncio.to_thread(_build)}}


async def declared_target_declare_tool(*, intended_path: str, label: str | None = None,
                                       work_unit_id: str | None = None) -> "dict[str, Any]":
    """Declare intent toward a not-yet-existing anchor. Pure P7 + a path hash — does NOT touch P6
    and does NOT require the file to exist. The predicted id is a prediction, verified at promote."""
    if (u := await _registry_unusable()) is not None:
        return u
    if not isinstance(intended_path, str) or not intended_path.strip():
        return _err("invalid_path", "'intended_path' must be a non-empty string.")
    if work_unit_id is not None:
        if await asyncio.to_thread(lambda: work_units_registry().get_work_unit(work_unit_id)) is None:
            return _err("work_unit_not_found", f"No work unit {work_unit_id!r}.")
    norm = await asyncio.to_thread(_artifacts.normalize_path, intended_path)
    predicted = await asyncio.to_thread(_artifacts.artifact_id_for, norm)
    dt_id = f"dt-{uuid.uuid4().hex[:12]}"
    try:
        await asyncio.to_thread(lambda: work_units_registry().insert_declared_target(
            dt_id, work_unit_id=work_unit_id, intended_path=intended_path, normalized_path=norm,
            predicted_artifact_id=predicted, label=label, now=int(time.time())))
    except DeclaredTargetConflict as exc:
        return _err("declared_target_path_conflict",
                    f"Intended path is already declared by {exc.existing_id!r}.",
                    existingDeclaredTargetId=exc.existing_id)
    return {"success": True, "data": {
        "declaredTargetId": dt_id, "intendedPath": intended_path, "normalizedPath": norm,
        "predictedArtifactId": predicted, "status": "declared", "workUnitId": work_unit_id}}


async def declared_target_promote_tool(*, declared_target_id: str) -> "dict[str, Any]":
    """The ONLY transition to 'materialized'. Drift-check, register the real file through P6's public
    api, verify the bind, flip. Idempotent + re-entrant (safe to retry after a cross-DB crash window)."""
    if (u := await _registry_unusable()) is not None:
        return u
    if (p6u := await _p6_unusable()) is not None:
        return p6u
    row = await asyncio.to_thread(lambda: work_units_registry().get_declared_target(declared_target_id))
    if row is None:
        return _err("declared_target_not_found", f"No declared target {declared_target_id!r}.")
    if row.status == "materialized":   # idempotent: bind already done
        return {"success": True, "data": {"declaredTargetId": row.declared_target_id,
                "status": "materialized", "boundArtifactId": row.bound_artifact_id,
                "normalizedPath": row.normalized_path}}
    # (a) declared-path drift — pure recompute, no P6/disk write
    cur_norm = await asyncio.to_thread(_artifacts.normalize_path, row.intended_path)
    cur_id = await asyncio.to_thread(_artifacts.artifact_id_for, cur_norm)
    if cur_id != row.predicted_artifact_id:
        return _err("declared_target_path_identity_changed",
                    "The declared path now normalizes to a different artifact id; not promoted.",
                    predictedArtifactId=row.predicted_artifact_id, currentArtifactId=cur_id)
    # register through P6's PUBLIC api — parse the {success, data} envelope by data.code (never generic)
    r = await _artifacts.register_artifact(row.intended_path)
    if r["success"] is False:
        code = r["data"]["code"]
        if code == "artifact_file_not_found":
            return _err("declared_target_not_materialized",
                        f"No file at the declared path yet; cannot materialize {declared_target_id!r}.")
        if code == "artifact_file_unreachable":
            return _err("declared_target_unreachable",
                        f"The declared path is unreachable; cannot materialize {declared_target_id!r}.")
        if code == "artifact_id_collision":
            return _err("declared_target_path_conflict",
                        "A different registered path already owns this artifact id; not promoted.")
        if code == "artifact_registry_unavailable":
            return r  # pass the P6 envelope through unchanged
        return _err("declared_target_promotion_failed",
                    f"P6 registration failed unexpectedly: {code}.", p6Code=code)
    artifact = r["data"]["artifact"]
    # (b) bind verification — the real P6 row must match the prediction and be present
    if artifact["artifactId"] != row.predicted_artifact_id or artifact["fileState"] != "present":
        return _err("declared_target_path_identity_changed",
                    "The registered artifact does not match the prediction; not promoted.",
                    predictedArtifactId=row.predicted_artifact_id,
                    registeredArtifactId=artifact["artifactId"], fileState=artifact["fileState"])
    await asyncio.to_thread(lambda: work_units_registry().set_declared_target_materialized(
        declared_target_id, bound_artifact_id=row.predicted_artifact_id, now=int(time.time())))
    return {"success": True, "data": {"declaredTargetId": declared_target_id, "status": "materialized",
            "boundArtifactId": row.predicted_artifact_id, "normalizedPath": row.normalized_path}}


def _observe_declared_target(row: "DeclaredTargetRow", p6_available: bool) -> "dict[str, Any]":
    """Read-only observations computed at call time — NEVER a transition. fileState is a fresh disk
    stat; P6-derived fields are null when P6 is unavailable. promotable INCLUDES p6_available, so it
    never claims promotion can work when promote would die at its artifact_registry_unavailable guard.
    promotionBlockedReason is the first failing precondition in promote's own order."""
    cur_norm = _artifacts.normalize_path(row.intended_path)
    file_state, _, _ = _artifacts.stat_file_state(cur_norm)
    path_identity_stable = (_artifacts.artifact_id_for(cur_norm) == row.predicted_artifact_id)
    artifact_registered: bool | None = None
    bound_present: bool | None = None
    if p6_available:
        artifact_registered = _p6_row(row.predicted_artifact_id) is not None
        if row.status == "materialized" and row.bound_artifact_id is not None:
            b = _p6_row(row.bound_artifact_id)
            bound_present = (b is not None and b.file_state == "present")
    promotable = (row.status == "declared" and p6_available
                  and path_identity_stable and file_state == "present")
    reason: str | None = None
    if not promotable:
        if row.status == "materialized":
            reason = "already_materialized"
        elif not p6_available:
            reason = "artifact_registry_unavailable"
        elif not path_identity_stable:
            reason = "declared_target_path_identity_changed"
        elif file_state == "unreachable":
            reason = "declared_target_unreachable"
        elif file_state == "missing":
            reason = "declared_target_not_materialized"
    return {"fileState": file_state, "pathIdentityStable": path_identity_stable,
            "p6Available": p6_available, "artifactRegistered": artifact_registered,
            "boundArtifactPresent": bound_present, "promotable": promotable,
            "promotionBlockedReason": reason}


async def list_declared_targets_tool(*, declared_target_id: str | None = None) -> "dict[str, Any]":
    """List/inspect declared targets with a computed 'observed' block. Guards P7-unusable; DEGRADES
    (does not fail closed) on a P6 skew so perception is never fully blocked by the lower plane.
    An explicit unknown declared_target_id is a malformed request -> declared_target_not_found."""
    if (u := await _registry_unusable()) is not None:
        return u
    if declared_target_id is not None:
        if await asyncio.to_thread(lambda: work_units_registry().get_declared_target(declared_target_id)) is None:
            return _err("declared_target_not_found", f"No declared target {declared_target_id!r}.")
    p6_available = (await _p6_unusable()) is None
    def _build() -> "list[dict[str, Any]]":
        reg = work_units_registry()
        rows = ([reg.get_declared_target(declared_target_id)] if declared_target_id
                else reg.list_declared_targets())
        rows = [r for r in rows if r is not None]
        return [{"declaredTargetId": r.declared_target_id, "workUnitId": r.work_unit_id,
                 "intendedPath": r.intended_path, "normalizedPath": r.normalized_path,
                 "predictedArtifactId": r.predicted_artifact_id, "status": r.status,
                 "boundArtifactId": r.bound_artifact_id, "label": r.label,
                 "createdAt": r.created_at, "materializedAt": r.materialized_at,
                 "observed": _observe_declared_target(r, p6_available)} for r in rows]
    return {"success": True, "data": {"declaredTargets": await asyncio.to_thread(_build),
                                      "p6Available": p6_available}}


async def record_planned_contract(*, target, sources, merge_kind: str, refresh_policy: str,
                                  work_unit_id: str | None = None) -> "dict[str, Any]":
    """Record future fan-in intent over typed refs. Conditional P6 guard: refs are parsed FIRST, then P6
    is required ONLY if an artifact ref is present (all-declared_target planning works under P6 skew)."""
    if (u := await _registry_unusable()) is not None:
        return u
    # 1. parse refs FIRST (before any P6 guard)
    tref, terr = _parse_ref(target)
    if terr is not None:
        return _err(terr["code"], terr.get("message", "bad target ref"),
                    **{k: v for k, v in terr.items() if k not in ("code", "message")})
    if not isinstance(sources, list) or not sources:
        return _err("empty_sources", "'sources' must be a non-empty list of typed refs.")
    parsed_sources: list[tuple[str, str]] = []
    for s in sources:
        sref, serr = _parse_ref(s)
        if serr is not None:
            return _err(serr["code"], serr.get("message", "bad source ref"),
                        **{k: v for k, v in serr.items() if k not in ("code", "message")})
        parsed_sources.append(sref)
    all_refs = [tref] + parsed_sources
    has_artifact_ref = any(k == "artifact" for k, _ in all_refs)
    # 2. CONDITIONAL P6 guard — only when an artifact ref exists
    if has_artifact_ref:
        if (p6u := await _p6_unusable()) is not None:
            return p6u
    # 3. resolution (declared_target exists) + structural over canonical keys
    def _checks():
        reg = work_units_registry()
        keys, res_probs = [], []
        for (k, i) in all_refs:
            key, prob = _planned_artifact_key(reg, k, i)
            if prob is not None:
                res_probs.append(prob)
            keys.append(key)
        if res_probs:
            return res_probs, []
        return [], _planned_structural_problems(keys[0], keys[1:], merge_kind, refresh_policy)
    res_probs, struct = await asyncio.to_thread(_checks)
    if res_probs:
        p = res_probs[0]
        return _err(p["code"], f"Reference does not resolve: {p['code']}.",
                    **{k: v for k, v in p.items() if k != "code"})
    if struct:
        p = struct[0]
        return _err(p["code"], f"Planned contract is not well-formed: {p['code']}.",
                    **{k: v for k, v in p.items() if k != "code"})
    # 4. artifact link-bar (registered; present NOT required) — only reachable when P6 usable
    if has_artifact_ref:
        def _linkbar():
            return [i for k, i in all_refs if k == "artifact" and not _is_registered(i)]
        unregistered = await asyncio.to_thread(_linkbar)
        if unregistered:
            return _err("artifact_not_registered", "An artifact ref is not registered in P6.",
                        ref={"kind": "artifact", "id": unregistered[0]})
    # 5. optional work unit exists
    if work_unit_id is not None:
        if await asyncio.to_thread(lambda: work_units_registry().get_work_unit(work_unit_id)) is None:
            return _err("work_unit_not_found", f"No work unit {work_unit_id!r}.")
    # 6. atomic insert + canonical cycle pre-check
    pc_id = f"pc-{uuid.uuid4().hex[:12]}"
    try:
        await asyncio.to_thread(lambda: work_units_registry().insert_planned_contract(
            pc_id, target_ref_kind=tref[0], target_ref_id=tref[1], sources=parsed_sources,
            merge_kind=merge_kind, refresh_policy=refresh_policy, work_unit_id=work_unit_id, now=int(time.time())))
    except PlannedContractCycle as exc:
        return _err("planned_contract_cycle_detected",
                    "Recording this planned contract would introduce a cycle into the planned graph; nothing written.",
                    cycle=exc.cycle)
    return {"success": True, "data": {"plannedContractId": pc_id,
            "target": {"kind": tref[0], "id": tref[1]},
            "sources": [{"kind": k, "id": i} for k, i in parsed_sources],
            "mergeKind": merge_kind, "refreshPolicy": refresh_policy, "status": "planned",
            "workUnitId": work_unit_id}}


async def activate_planned_contract_tool(*, planned_contract_id: str) -> "dict[str, Any]":
    """One-at-a-time, idempotent (in-tx CAS), fail-closed-with-all-blockers bridge from a planned contract
    to a strict merge_contract. The only failures that escape the blocker envelope are not_found,
    already_invalid, and registry-unavailable."""
    if (u := await _registry_unusable()) is not None:
        return u
    if (p6u := await _p6_unusable()) is not None:
        return p6u
    row = await asyncio.to_thread(lambda: work_units_registry().get_planned_contract(planned_contract_id))
    if row is None:
        return _err("planned_contract_not_found", f"No planned contract {planned_contract_id!r}.")
    state = _classify_planned_state(row)
    if state == "activated":
        return {"success": True, "data": {"plannedContractId": planned_contract_id, "status": "activated",
                "contractId": row.activated_contract_id, "alreadyActivated": True}}
    if state == "invalid":
        return _err("planned_contract_already_invalid",
                    f"Planned contract {planned_contract_id!r} violates the stored-state invariant.")
    blockers, resolved = await asyncio.to_thread(
        lambda: _activation_blockers(work_units_registry(), row, True))
    if blockers:
        return {"success": False, "data": {"code": "planned_contract_not_activatable",
                "blockers": blockers, "retryable": all(b["retryable"] for b in blockers)}}
    contract_id = f"mc-{uuid.uuid4().hex[:12]}"
    def _activate():
        reg = work_units_registry()
        return reg.activate_planned_contract(
            planned_contract_id, candidate_contract_id=contract_id, target=resolved["target"],
            sources=resolved["sources"], merge_kind=row.merge_kind, refresh_policy=row.refresh_policy,
            work_unit_ids=reg.work_units_for_planned_contract(planned_contract_id), now=int(time.time()))
    try:
        final_contract_id, already = await asyncio.to_thread(_activate)
    except ContractCycleError as exc:
        return {"success": False, "data": {"code": "planned_contract_not_activatable",
                "blockers": [{"code": "strict_merge_cycle_detected", "retryable": False, "cycle": exc.cycle}],
                "retryable": False}}
    except PlannedContractInvalid:
        return _err("planned_contract_already_invalid",
                    f"Planned contract {planned_contract_id!r} violates the stored-state invariant.")
    return {"success": True, "data": {"plannedContractId": planned_contract_id, "status": "activated",
            "contractId": final_contract_id, "alreadyActivated": already,
            "target": resolved["target"], "sources": resolved["sources"],
            "mergeKind": row.merge_kind, "refreshPolicy": row.refresh_policy}}


async def list_planned_contracts_tool(*, planned_contract_id: str | None = None) -> "dict[str, Any]":
    """Inspect one (with observations) or the whole graph (+ order/edges/graphOk). Transitions nothing;
    DEGRADES on P6 skew (every row activatable=false + an artifact_registry_unavailable blocker)."""
    if (u := await _registry_unusable()) is not None:
        return u
    if planned_contract_id is not None:
        if await asyncio.to_thread(lambda: work_units_registry().get_planned_contract(planned_contract_id)) is None:
            return _err("planned_contract_not_found", f"No planned contract {planned_contract_id!r}.")
    p6_available = (await _p6_unusable()) is None
    def _build():
        reg = work_units_registry()
        if planned_contract_id is not None:
            rows, graph = [reg.get_planned_contract(planned_contract_id)], None
        else:
            rows, graph = reg.list_planned_contracts(), _planned_graph_view(reg)
        out_rows = []
        for r in [r for r in rows if r is not None]:
            out_rows.append({"plannedContractId": r.planned_contract_id,
                             "target": {"kind": r.target_ref_kind, "id": r.target_ref_id},
                             "sources": [{"kind": k, "id": i} for k, i in reg.sources_for_planned(r.planned_contract_id)],
                             "mergeKind": r.merge_kind, "refreshPolicy": r.refresh_policy, "status": r.status,
                             "activatedContractId": r.activated_contract_id, "activatedAt": r.activated_at,
                             "createdAt": r.created_at,
                             "observed": _observe_planned_contract(reg, r, p6_available)})
        return out_rows, graph
    out_rows, graph = await asyncio.to_thread(_build)
    data: dict[str, Any] = {"plannedContracts": out_rows, "p6Available": p6_available}
    if graph is not None:
        data.update(graph)
    return {"success": True, "data": data}
