"""P7 — coordinator-plane registry (merge contracts + declared targets).

Slice 1: Work Units + their P6 artifact provenance + Merge Contracts (a sources->target
dependency DAG); records and validates fan-in INTENT only — read-only over P6.
Slice 2: declared targets — declare intent toward a master/anchor file BEFORE it exists, then
promote it once it materializes.

Records intent ONLY — no merge executes, no geometry enters Rhino. P6 is read-only EXCEPT the one
explicit Slice-2 write: declared_target_promote_tool registers the now-materialized file through
P6's PUBLIC register_artifact() — a plain artifact row carrying NO P7 vocabulary.
Invariant: P7 references P6 by artifact_id; P6 never references P7.
See docs/superpowers/specs/2026-06-05-p7-slice1-merge-contract-registry-design.md
and  docs/superpowers/specs/2026-06-06-p7-slice2-declared-target-state-machine-design.md.
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


def _contract_graph(pairs):
    """pairs: list of (contract_id, target_artifact_id, sources_list). Directed edge A->B iff
    target(A) appears in sources(B). Returns (graph, target_of, sources_of)."""
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
    g, _, _ = _contract_graph(pairs)
    try:
        cyc = nx.find_cycle(g)   # list of (u, v) edges (2-tuples; no orientation)
    except nx.NetworkXNoCycle:
        return None
    return [u for u, _ in cyc] + [cyc[-1][1]]


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

    contract_order: list[str] | None = None
    try:
        contract_order = list(nx.lexicographical_topological_sort(g, key=lambda n: order_key[n]))
    except nx.NetworkXUnfeasible:
        problems.append({"code": "merge_cycle_detected", "cycle": _contract_cycle(pairs)})

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
                        "declaredTargets": reg.declared_targets_for(r.work_unit_id)})
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
