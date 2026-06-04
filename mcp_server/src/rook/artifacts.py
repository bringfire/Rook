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
