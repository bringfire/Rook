import os
import sys
from pathlib import Path

import sqlite3

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from rook import artifacts


def test_normalize_path_is_absolute_and_case_folded(tmp_path):
    f = tmp_path / "Model.3dm"
    f.write_bytes(b"x")
    a = artifacts.normalize_path(str(f))
    b = artifacts.normalize_path(str(f).upper())  # Windows: case-insensitive
    assert os.path.isabs(a)
    if os.name == "nt":
        assert a == b  # same artifact regardless of case


def test_artifact_id_is_deterministic_sha256_hex():
    norm = artifacts.normalize_path("C:/proj/site.3dm") if os.name == "nt" else artifacts.normalize_path("/proj/site.3dm")
    i1 = artifacts.artifact_id_for(norm)
    i2 = artifacts.artifact_id_for(norm)
    assert i1 == i2 and len(i1) == 64 and all(c in "0123456789abcdef" for c in i1)


def test_stat_file_state_present_missing(tmp_path):
    f = tmp_path / "x.3dm"
    f.write_bytes(b"abc")
    norm = artifacts.normalize_path(str(f))
    state, size, mtime = artifacts.stat_file_state(norm)
    assert state == "present" and size == 3 and isinstance(mtime, int)

    missing = artifacts.normalize_path(str(tmp_path / "nope.3dm"))
    state2, size2, mtime2 = artifacts.stat_file_state(missing)
    assert state2 == "missing" and size2 is None and mtime2 is None


def test_fresh_db_creates_table_and_persists_version(tmp_path):
    reg = artifacts.ArtifactRegistry(tmp_path / "artifacts.db")
    assert reg.schema_unsupported is None
    reg.close()
    reg2 = artifacts.ArtifactRegistry(tmp_path / "artifacts.db")  # reopen, no error
    assert reg2.schema_unsupported is None
    reg2.close()


def test_version_skew_fails_closed_without_dropping(tmp_path):
    db = tmp_path / "artifacts.db"
    reg = artifacts.ArtifactRegistry(db)
    reg._conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('artifact_registry_version','p99.9');")
    reg.close()
    reg2 = artifacts.ArtifactRegistry(db)
    assert reg2.schema_unsupported == "p99.9"   # fail closed, rows intact, table not dropped
    assert reg2._conn.execute("SELECT 1 FROM sqlite_master WHERE name='artifacts';").fetchone() is not None
    reg2.close()


def test_foreign_table_shape_fails_closed(tmp_path):
    db = tmp_path / "artifacts.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE artifacts (wrong TEXT);")
    conn.commit(); conn.close()
    reg = artifacts.ArtifactRegistry(db)
    assert reg.schema_unsupported == "unknown"
    reg.close()
