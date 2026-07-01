from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_script():
    path = Path(__file__).resolve().parents[2] / "scripts" / "lm_surface_smoke.py"
    spec = importlib.util.spec_from_file_location("lm_surface_smoke", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


SMOKE = _load_script()


def test_pythonpath_clean():
    assert SMOKE.pythonpath_clean("") is True
    assert SMOKE.pythonpath_clean("   ") is True
    assert SMOKE.pythonpath_clean("C:/repo/src") is False
    assert SMOKE.pythonpath_clean(" C:/x ") is False


def test_module_origin_ok_under_site_packages():
    root = r"C:\Users\bring\AppData\Local\Rook\venv\Lib\site-packages"
    under = r"C:\Users\bring\AppData\Local\Rook\venv\Lib\site-packages\rook\__init__.py"
    repo = r"C:\UDEV\Rook\mcp_server\src\rook\__init__.py"
    assert SMOKE.module_origin_ok(under, root) is True
    # case + separator insensitivity
    assert SMOKE.module_origin_ok(under.lower().replace("\\", "/"), root) is True
    assert SMOKE.module_origin_ok(repo, root) is False


def test_module_origin_ok_rejects_sibling_path():
    # Real containment, not string startswith: a sibling whose name shares the
    # root as a prefix must NOT pass.
    root = r"C:\Users\bring\AppData\Local\Rook\venv\Lib\site-packages"
    sibling = r"C:\Users\bring\AppData\Local\Rook\venv\Lib\site-packages2\rook\__init__.py"
    assert SMOKE.module_origin_ok(sibling, root) is False


def test_classify_cache():
    required = {"gh_snapshot", "gh_errors"}
    assert SMOKE.classify_cache(None, {"a"}, required) == "absent"
    assert SMOKE.classify_cache({"a", "b"}, {"a", "b"}, required) == "current"
    # benign drift (not in required) -> warning
    assert SMOKE.classify_cache({"a", "b"}, {"a"}, required) == "warning"
    # required-touching drift -> fail
    assert SMOKE.classify_cache({"a"}, {"a", "gh_snapshot"}, required) == "fail"


def test_degenerate_activation_failures():
    catalog_groups = {"gh_canvas", "rhino_geometry"}
    # gh_canvas present in catalog but failed -> degenerate
    assert SMOKE.degenerate_activation_failures(
        {"gh_canvas", "absent_group"}, catalog_groups
    ) == ("gh_canvas",)
    # a group absent from the catalog failing is allowed (not flagged)
    assert SMOKE.degenerate_activation_failures({"absent_group"}, catalog_groups) == ()


def test_format_surface_evidence_is_deterministic():
    out = SMOKE.format_surface_evidence(
        catalog_count=300,
        profile_name="readonly",
        intended_count=64,
        active_count=12,
        finding_histogram={"active_not_intended": 3, "group_activation_failed": 1},
        profile_findings_count=76,
    )
    assert "catalog tools: 300" in out
    assert "profile: readonly" in out
    # histogram rendered in sorted code order
    assert out.index("active_not_intended") < out.index("group_activation_failed")
    assert out == SMOKE.format_surface_evidence(
        catalog_count=300,
        profile_name="readonly",
        intended_count=64,
        active_count=12,
        finding_histogram={"group_activation_failed": 1, "active_not_intended": 3},
        profile_findings_count=76,
    )


def test_build_parser_accepts_two_subcommands():
    parser = SMOKE.build_parser()
    assert parser.parse_args(["coherence"]).command == "coherence"
    assert parser.parse_args(["surface"]).command == "surface"


def test_build_parser_rejects_unknown_subcommand():
    import pytest

    parser = SMOKE.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["nonsense"])


def test_main_fails_fast_on_nonempty_pythonpath(monkeypatch, capsys):
    # The PYTHONPATH gate runs in main() BEFORE any rook import, so this test
    # needs no deployed runtime: a dirty PYTHONPATH must return 1 immediately.
    monkeypatch.setenv("PYTHONPATH", "C:/repo/src")
    rc = SMOKE.main(["coherence"])
    assert rc == 1
    out = capsys.readouterr().out
    assert "PYTHONPATH" in out
    assert "FAIL" in out


from rook.agent.external_mcp import ExternalMcpFinding, ExternalMcpResolution


def _ext_res(*codes):
    findings = tuple(
        ExternalMcpFinding(code=c, tool="t", severity="error", message="m")
        for c in codes
    )
    return ExternalMcpResolution(
        advertised_names=("t",), wire_dispatch_names=("t",), findings=findings
    )


def test_external_parser_accepts_external():
    args = SMOKE.build_parser().parse_args(["external"])
    assert args.command == "external"


def test_external_exit_decision_fails_on_advertised_not_dispatchable():
    code, warn, fail = SMOKE.external_exit_decision(
        _ext_res("advertised_not_dispatchable").findings
    )
    assert code == 1
    assert fail == ("advertised_not_dispatchable",)


def test_external_exit_decision_fails_on_structural_errors():
    for c in ("empty_catalog", "dispatch_function_missing", "wire_source_unresolved"):
        code, _warn, fail = SMOKE.external_exit_decision(_ext_res(c).findings)
        assert code == 1 and fail == (c,)


def test_external_exit_decision_warns_not_fails_on_anomalies():
    code, warn, fail = SMOKE.external_exit_decision(
        _ext_res("multiple_dispatch_matches", "unextractable_case").findings
    )
    assert code == 0
    assert warn == ("multiple_dispatch_matches", "unextractable_case")
    assert fail == ()


def test_external_exit_decision_info_only_passes():
    code, warn, fail = SMOKE.external_exit_decision(
        _ext_res("handler_not_advertised").findings
    )
    assert code == 0 and warn == () and fail == ()


def test_run_external_refuses_when_origin_guard_fails(monkeypatch, capsys):
    # Guard honored => returns 1 WITHOUT importing the runtime.
    monkeypatch.setattr(SMOKE, "_check_origins", lambda: 1)
    rc = SMOKE.run_external()
    assert rc == 1
    out = capsys.readouterr().out
    assert "origin guard failed" in out


def test_progressive_parser_accepts_progressive():
    args = SMOKE.build_parser().parse_args(["progressive"])
    assert args.command == "progressive"


def test_progressive_gateway_metadata_validation_requires_aliases():
    catalog = {
        "rook_tools_search": {
            "function": {
                "description": "Search gh_update_script gh_set_script_pins gh_status gh_create_csharp_script gh_snapshot"
            }
        },
        "rook_tools_read": {
            "function": {
                "description": "Read gh_update_script gh_set_script_pins gh_status gh_create_csharp_script gh_snapshot"
            }
        },
        "rook_tools_call": {
            "function": {
                "description": "Call gh_update_script gh_set_script_pins gh_status gh_create_csharp_script gh_snapshot"
            }
        },
    }
    assert SMOKE.progressive_gateway_metadata_failures(catalog) == []
    bad = dict(catalog)
    bad["rook_tools_search"] = {"function": {"description": "Search tools"}}
    assert "rook_tools_search missing gh_update_script" in SMOKE.progressive_gateway_metadata_failures(bad)


def test_progressive_search_validation_requires_exact_records():
    search_results = {
        name: [{"name": name, "domain": "gh"}]
        for name in SMOKE.DG009_GH_TOOL_NAMES
    }
    assert SMOKE.progressive_search_failures(search_results) == []
    bad = dict(search_results)
    bad["gh_update_script"] = [{"name": "gh_set_script", "domain": "gh"}]
    assert "rook_tools_search did not return gh_update_script" in SMOKE.progressive_search_failures(bad)


def test_progressive_read_validation_requires_gh_object_schemas():
    read_records = {
        name: {
            "name": name,
            "domain": "gh",
            "input_schema": {"type": "object", "properties": {}},
        }
        for name in SMOKE.DG009_GH_TOOL_NAMES
    }
    assert SMOKE.progressive_read_failures(read_records) == []

    bad_name = dict(read_records)
    bad_name["gh_update_script"] = {
        "name": "gh_set_script",
        "domain": "gh",
        "input_schema": {"type": "object"},
    }
    assert "rook_tools_read returned wrong record for gh_update_script" in SMOKE.progressive_read_failures(bad_name)

    bad_schema = dict(read_records)
    bad_schema["gh_update_script"] = {
        "name": "gh_update_script",
        "domain": "gh",
        "input_schema": {"type": "array"},
    }
    assert "rook_tools_read returned invalid input_schema for gh_update_script" in SMOKE.progressive_read_failures(bad_schema)
