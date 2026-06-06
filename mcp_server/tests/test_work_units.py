from __future__ import annotations
import sqlite3
from pathlib import Path
import pytest
from rook import work_units


@pytest.fixture(autouse=True)
def _isolate_registries():
    """Reset both registry singletons after each test so a repointed db path never leaks
    across tests/files (monkeypatch restores the resolve_* functions; this drops the
    lazily-built singletons that may still hold a temp-db connection)."""
    yield
    from rook import artifacts
    artifacts._reset_artifact_registry_singleton()
    work_units._reset_work_units_registry_singleton()


def _fresh_registry(tmp_path) -> "work_units.WorkUnitRegistry":
    return work_units.WorkUnitRegistry(tmp_path / "work_units.db")


def test_schema_bootstrap_creates_five_tables_and_version(tmp_path):
    reg = _fresh_registry(tmp_path)
    names = {r[0] for r in reg._conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table';").fetchall()}
    assert {"work_units", "work_unit_artifacts", "merge_contracts",
            "merge_contract_sources", "work_unit_merge_contracts"}.issubset(names)
    ver = reg._conn.execute(
        "SELECT value FROM meta WHERE key='work_units_registry_version';").fetchone()
    assert ver[0] == work_units.WORK_UNITS_REGISTRY_VERSION
    assert reg.schema_unsupported is None
    reg.close()


def test_reopen_is_clean_and_additive(tmp_path):
    work_units.WorkUnitRegistry(tmp_path / "work_units.db").close()
    reg = work_units.WorkUnitRegistry(tmp_path / "work_units.db")  # no error second time
    assert reg.schema_unsupported is None
    reg.close()


def test_wrong_version_db_fails_closed(tmp_path):
    db = tmp_path / "work_units.db"
    raw = sqlite3.connect(str(db))
    raw.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);")
    raw.execute("INSERT INTO meta(key,value) VALUES('work_units_registry_version','p0.legacy');")
    raw.commit(); raw.close()
    reg = work_units.WorkUnitRegistry(db)
    assert reg.schema_unsupported == "p0.legacy"
    reg.close()
