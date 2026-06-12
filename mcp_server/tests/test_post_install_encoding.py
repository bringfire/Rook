"""Regression tests for installer/post_install.py file-encoding handling.

The 1.5.11 release smoke (2026-06-11) failed finalization with
UnicodeDecodeError: Path.read_text() defaults to the locale codec (cp1252
on Windows), which cannot decode UTF-8 content such as curly quotes in the
user's ~/.claude.json. Every config read/write in post_install.py must pass
encoding="utf-8" explicitly.
"""

from __future__ import annotations

import ast
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


def _function_node(source: str, name: str) -> ast.FunctionDef:
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name} not found")


def _has_utf8_keyword(call: ast.Call) -> bool:
    return any(
        keyword.arg == "encoding"
        and isinstance(keyword.value, ast.Constant)
        and keyword.value.value == "utf-8"
        for keyword in call.keywords
    )


def _attribute_calls(function: ast.FunctionDef, name: str) -> list[ast.Call]:
    return [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == name
    ]


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


def test_post_install_summary_and_log_paths_use_utf8_source_pin():
    source = POST_INSTALL.read_text(encoding="utf-8")

    summary_path = _function_node(source, "_summary_path")
    assert "post_install_summary.json" in ast.get_source_segment(source, summary_path)

    read_summary = _function_node(source, "_read_install_summary")
    assert any(
        isinstance(call.func.value, ast.Name)
        and call.func.value.id == "path"
        and _has_utf8_keyword(call)
        for call in _attribute_calls(read_summary, "read_text")
    )

    write_summary = _function_node(source, "_write_install_summary")
    assert any(
        isinstance(call.func.value, ast.Name)
        and call.func.value.id == "path"
        and _has_utf8_keyword(call)
        for call in _attribute_calls(write_summary, "write_text")
    )

    log_path = _function_node(source, "_post_install_log_path")
    assert "post_install.log" in ast.get_source_segment(source, log_path)

    configure_logging = _function_node(source, "_configure_install_logging")
    file_handler_calls = [
        node
        for node in ast.walk(configure_logging)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "logging"
        and node.func.attr == "FileHandler"
    ]
    assert any(
        call.args
        and isinstance(call.args[0], ast.Name)
        and call.args[0].id == "log_path"
        and _has_utf8_keyword(call)
        for call in file_handler_calls
    )


def test_consume_doctor_payload_warning_severity_does_not_fail_validation():
    """Warning-severity doctor failures become installer warnings, never
    fatal checks; error-severity failures still fail validation."""
    module = _load_post_install()
    payload = {
        "checks": [
            {"name": "Claude Code config", "ok": False, "severity": "warning", "detail": "left untouched"},
            {"name": "Codex config", "ok": True, "severity": "error"},
            {"name": "ROOK_DATA_DIR writable", "ok": False, "severity": "error", "detail": "boom"},
        ],
        "warnings": ["legacy path exists"],
    }
    checks, warnings = module._consume_doctor_payload(payload)
    assert ("Codex config", True) in checks
    assert ("ROOK_DATA_DIR writable", False) in checks
    assert all(name != "Claude Code config" for name, _ in checks)
    assert any("left untouched" in w for w in warnings)
    assert "legacy path exists" in warnings
