from __future__ import annotations

from rook.agent.external_mcp import (
    ExternalMcpFinding,
    WireDispatchEvidence,
    collect_wire_dispatch_evidence,
    extract_wire_dispatch_evidence_from_source,
)

_PREAMBLE = "async def _call_tool_dispatch(name, arguments):\n"


def _src(body: str) -> str:
    # body lines are already indented 4 spaces under the function
    return _PREAMBLE + body


def _codes(ev: WireDispatchEvidence):
    return sorted(f.code for f in ev.findings)


def test_plain_string_cases_collected():
    ev = extract_wire_dispatch_evidence_from_source(
        _src(
            "    match name:\n"
            "        case 'tool_a':\n"
            "            return 1\n"
            "        case 'tool_b':\n"
            "            return 2\n"
        )
    )
    assert ev.names == ("tool_a", "tool_b")
    assert ev.findings == ()


def test_or_pattern_collects_all_strings():
    ev = extract_wire_dispatch_evidence_from_source(
        _src(
            "    match name:\n"
            "        case 'tool_b' | 'tool_c':\n"
            "            return 1\n"
        )
    )
    assert ev.names == ("tool_b", "tool_c")
    assert ev.findings == ()


def test_wildcard_ignored():
    ev = extract_wire_dispatch_evidence_from_source(
        _src(
            "    match name:\n"
            "        case 'tool_a':\n"
            "            return 1\n"
            "        case _:\n"
            "            return 0\n"
        )
    )
    assert ev.names == ("tool_a",)
    assert ev.findings == ()


def test_guarded_case_is_unextractable():
    ev = extract_wire_dispatch_evidence_from_source(
        _src(
            "    match name:\n"
            "        case 'tool_a' if arguments:\n"
            "            return 1\n"
        )
    )
    assert ev.names == ()
    assert _codes(ev) == ["unextractable_case"]
    assert "line" in ev.findings[0].tool


def test_capture_case_is_unextractable():
    ev = extract_wire_dispatch_evidence_from_source(
        _src(
            "    match name:\n"
            "        case other:\n"
            "            return other\n"
        )
    )
    assert ev.names == ()
    assert _codes(ev) == ["unextractable_case"]


def test_non_constant_and_non_str_cases_unextractable():
    ev = extract_wire_dispatch_evidence_from_source(
        _src(
            "    match name:\n"
            "        case SOME_CONST:\n"
            "            return 1\n"
            "        case 5:\n"
            "            return 2\n"
        )
    )
    assert ev.names == ()
    assert _codes(ev) == ["unextractable_case", "unextractable_case"]


def test_missing_dispatch_function():
    ev = extract_wire_dispatch_evidence_from_source("def other():\n    return 1\n")
    assert ev.names == ()
    assert _codes(ev) == ["dispatch_function_missing"]
    assert ev.findings[0].severity == "error"


def test_multiple_match_name_blocks_warn_but_extract():
    ev = extract_wire_dispatch_evidence_from_source(
        _src(
            "    match name:\n"
            "        case 'tool_a':\n"
            "            return 1\n"
            "    match name:\n"
            "        case 'tool_b':\n"
            "            return 2\n"
        )
    )
    assert ev.names == ("tool_a", "tool_b")
    assert _codes(ev) == ["multiple_dispatch_matches"]


def test_match_on_other_subject_ignored():
    ev = extract_wire_dispatch_evidence_from_source(
        _src(
            "    match arguments:\n"
            "        case 'tool_a':\n"
            "            return 1\n"
        )
    )
    assert ev.names == ()
    assert ev.findings == ()


def test_finding_dataclasses_are_frozen():
    f = ExternalMcpFinding(code="c", tool="t", severity="info", message="m")
    try:
        f.code = "x"  # type: ignore[misc]
    except Exception:
        return
    raise AssertionError("ExternalMcpFinding should be frozen")


def test_collect_reads_real_rook_server_via_find_spec():
    ev = collect_wire_dispatch_evidence("rook.server")
    assert len(ev.names) > 300
    assert "rhino_ping" in ev.names
    assert "gh_edit" in ev.names
    # the real router is clean today: no structural extraction findings
    assert all(f.code == "unextractable_case" for f in ev.findings) or ev.findings == ()


def test_collect_sources_via_find_spec_origin(tmp_path, monkeypatch):
    import importlib.util as iu

    fake = tmp_path / "fake_server.py"
    fake.write_text(
        "async def _call_tool_dispatch(name, arguments):\n"
        "    match name:\n"
        "        case 'only_tool':\n"
        "            return 1\n",
        encoding="utf-8",
    )

    class _Spec:
        origin = str(fake)

    monkeypatch.setattr(
        "rook.agent.external_mcp.importlib.util.find_spec",
        lambda name: _Spec(),
    )
    ev = collect_wire_dispatch_evidence("whatever")
    assert ev.names == ("only_tool",)
    assert ev.findings == ()


def test_collect_unresolved_module_is_structured_error():
    ev = collect_wire_dispatch_evidence("rook.__nope_nonexistent__")
    assert ev.names == ()
    assert [f.code for f in ev.findings] == ["wire_source_unresolved"]
    assert ev.findings[0].severity == "error"


def test_collect_none_origin_is_structured_error(monkeypatch):
    class _Spec:
        origin = None

    monkeypatch.setattr(
        "rook.agent.external_mcp.importlib.util.find_spec",
        lambda name: _Spec(),
    )
    ev = collect_wire_dispatch_evidence("pkg_without_origin")
    assert ev.names == ()
    assert [f.code for f in ev.findings] == ["wire_source_unresolved"]


def test_collect_nonfile_origin_is_structured_error(monkeypatch, tmp_path):
    class _Spec:
        origin = str(tmp_path)  # a directory, not a file

    monkeypatch.setattr(
        "rook.agent.external_mcp.importlib.util.find_spec",
        lambda name: _Spec(),
    )
    ev = collect_wire_dispatch_evidence("pkg_dir_origin")
    assert ev.names == ()
    assert [f.code for f in ev.findings] == ["wire_source_unresolved"]
