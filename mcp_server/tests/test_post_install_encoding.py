"""Regression tests for installer/post_install.py file-encoding handling.

The 1.5.11 release smoke (2026-06-11) failed finalization with
UnicodeDecodeError: Path.read_text() defaults to the locale codec (cp1252
on Windows), which cannot decode UTF-8 content such as curly quotes in the
user's ~/.claude.json. Every config read/write in post_install.py must pass
encoding="utf-8" explicitly.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
POST_INSTALL = REPO_ROOT / "installer" / "post_install.py"


def _load_post_install():
    # post_install.py imports its sibling python_runtime_install module.
    if str(POST_INSTALL.parent) not in sys.path:
        sys.path.insert(0, str(POST_INSTALL.parent))
    spec = importlib.util.spec_from_file_location("rook_post_install", POST_INSTALL)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_register_mcp_preserves_utf8_user_config(tmp_path, monkeypatch):
    """A ~/.claude.json containing non-cp1252 UTF-8 must be read, preserved,
    and extended — not crashed on (pre-fix) or clobbered."""
    module = _load_post_install()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    config = tmp_path / ".claude.json"
    existing = {
        "projects": {"C:\\work\\Façade — “Tower B”": {"history": []}},
        "mcpServers": {"other": {"command": "x"}},
    }
    config.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")

    ok = module._register_mcp_via_file("C:/py/python.exe", "C:/mcp", {"A": "1"})
    assert ok is True

    result = json.loads(config.read_text(encoding="utf-8"))
    # Original content preserved (the curly-quoted project key survives).
    assert "C:\\work\\Façade — “Tower B”" in result["projects"]
    assert result["mcpServers"]["other"] == {"command": "x"}
    # Rook entry added.
    assert result["mcpServers"]["rook"]["command"] == "C:/py/python.exe"


def test_register_mcp_recovers_legacy_cp1252_config(tmp_path, monkeypatch):
    """A config the OLD locale-default read could parse (cp1252 with
    non-ASCII bytes that are invalid UTF-8) must still register — via the
    cp1252 fallback — not be skipped or clobbered."""
    module = _load_post_install()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    config = tmp_path / ".claude.json"
    existing = {"projects": {"C:\\work\\Café": {}}, "mcpServers": {}}
    # ensure_ascii=False + cp1252: é -> 0xE9, an invalid UTF-8 start byte.
    config.write_bytes(
        json.dumps(existing, ensure_ascii=False, indent=2).encode("cp1252")
    )

    ok = module._register_mcp_via_file("C:/py/python.exe", "C:/mcp", {})
    assert ok is True

    result = json.loads(config.read_text(encoding="utf-8"))
    assert "C:\\work\\Café" in result["projects"]
    assert result["mcpServers"]["rook"]["command"] == "C:/py/python.exe"


def test_register_mcp_never_clobbers_unreadable_config(tmp_path, monkeypatch, capsys):
    """An unparseable ~/.claude.json must be LEFT UNTOUCHED: registration is
    skipped with a warning and the install continues (returns True)."""
    module = _load_post_install()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    config = tmp_path / ".claude.json"
    broken = b'{ "mcpServers": { broken json \x9d\xff'
    config.write_bytes(broken)

    ok = module._register_mcp_via_file("C:/py/python.exe", "C:/mcp", {})
    assert ok is True
    # Byte-identical: nothing was rewritten.
    assert config.read_bytes() == broken
    assert "leaving it untouched" in capsys.readouterr().out


def _call_args(source: str, open_paren_idx: int) -> str:
    """Return the balanced-paren argument text starting at '('."""
    depth = 0
    for i in range(open_paren_idx, len(source)):
        if source[i] == "(":
            depth += 1
        elif source[i] == ")":
            depth -= 1
            if depth == 0:
                return source[open_paren_idx + 1 : i]
    return source[open_paren_idx + 1 :]


def test_no_encodingless_text_io_in_post_install():
    """Source pin: every read_text/write_text CALL in post_install.py must
    carry an explicit encoding argument (locale-default IO is forbidden).
    Comment lines are ignored; nested parens are handled."""
    raw = POST_INSTALL.read_text(encoding="utf-8")
    # Drop comment-only lines so prose mentioning read_text() can't match.
    source = "\n".join(
        ("" if line.lstrip().startswith("#") else line) for line in raw.splitlines()
    )
    violations = []
    for match in re.finditer(r"\.(read_text|write_text)\(", source):
        args = _call_args(source, match.end() - 1)
        if "encoding=" not in args:
            line = source[: match.start()].count("\n") + 1
            violations.append(f"line {line}: .{match.group(1)}({args[:60]}...)")
    assert not violations, "encoding-less text IO found:\n" + "\n".join(violations)
