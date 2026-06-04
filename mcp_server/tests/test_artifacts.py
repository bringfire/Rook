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
