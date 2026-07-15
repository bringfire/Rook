from __future__ import annotations

import asyncio
import importlib.util
import json
import os
from pathlib import Path

import pytest


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


def test_progressive_contract_pins_gateways_targets_and_realistic_queries():
    assert SMOKE.PROGRESSIVE_GATEWAY_NAMES == (
        "rook_tools_ls", "rook_tools_search", "rook_tools_read", "rook_tools_call"
    )
    assert SMOKE.PROGRESSIVE_ALIAS_GATEWAY_NAMES == (
        "rook_tools_search", "rook_tools_read", "rook_tools_call"
    )
    assert SMOKE.PROGRESSIVE_DISCOVERY_TARGETS == (
        "gh_update_script", "gh_set_script_pins", "gh_create_csharp_script",
        "gh_status", "gh_snapshot", "agent_status",
    )
    assert SMOKE.PROGRESSIVE_HIDDEN_TARGETS == (
        "gh_update_script", "gh_set_script_pins", "gh_create_csharp_script",
        "gh_status", "agent_status",
    )
    assert [(row["query"], row["expected_tool"], row["limit"], row["max_rank"])
            for row in SMOKE.PROGRESSIVE_INTENT_MATRIX] == [
        ("edit a Grasshopper script", "gh_update_script", 10, 10),
        ("change the inputs and outputs of a Grasshopper script", "gh_set_script_pins", 10, 10),
        ("create a C# script component in Grasshopper", "gh_create_csharp_script", 10, 10),
        ("check whether Grasshopper is ready", "gh_status", 10, 10),
        ("take a snapshot of the Grasshopper canvas", "gh_snapshot", 10, 10),
        ("check running agent status", "agent_status", 10, 1),
    ]


def test_progressive_intent_findings_report_rank_or_null():
    results = {row["query"]: [] for row in SMOKE.PROGRESSIVE_INTENT_MATRIX}
    results["check running agent status"] = [{"name": "agent_status"}]
    findings = SMOKE.progressive_intent_findings(results)
    assert len(findings) == 5
    assert {finding["code"] for finding in findings} == {"intent_discovery_rank_failed"}
    assert all(finding["observed_rank"] is None for finding in findings)
    assert findings[0] == {
        "record": "progressive_finding",
        "code": "intent_discovery_rank_failed",
        "query": "edit a Grasshopper script",
        "expected_tool": "gh_update_script",
        "limit": 10,
        "max_rank": 10,
        "observed_rank": None,
    }


def test_progressive_intent_findings_type_guard_without_renumbering_positions():
    results = {
        row["query"]: [None, "noise", 7, {"name": row["expected_tool"]}]
        for row in SMOKE.PROGRESSIVE_INTENT_MATRIX
    }
    findings = SMOKE.progressive_intent_findings(results)
    assert findings == [{
        "record": "progressive_finding",
        "code": "intent_discovery_rank_failed",
        "query": "check running agent status",
        "expected_tool": "agent_status",
        "limit": 10,
        "max_rank": 1,
        "observed_rank": 4,
    }]


def test_progressive_read_findings_require_exact_dispatchable_object_schema():
    records = {
        name: {"name": name, "mcp_dispatchable": True, "input_schema": {"type": "object"}}
        for name in SMOKE.PROGRESSIVE_DISCOVERY_TARGETS
    }
    assert SMOKE.progressive_read_findings(records) == []
    records["agent_status"]["mcp_dispatchable"] = False
    findings = SMOKE.progressive_read_findings(records)
    assert findings == [{
        "record": "progressive_finding",
        "code": "schema_read_failed",
        "target": "agent_status",
        "reason": "mcp_dispatchable_not_true",
    }]


def test_progressive_evidence_orders_checks_counts_histogram_and_emits_summary_on_failure(capsys):
    checks = [
        SMOKE.progressive_check(name, "PASS", 1, 1)
        for name in reversed(SMOKE.PROGRESSIVE_CHECK_ORDER)
    ]
    findings = [
        SMOKE.progressive_finding("intent_discovery_rank_failed", query=str(index))
        for index in range(5)
    ]
    rc = SMOKE.emit_progressive_evidence(checks, findings)
    records = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert rc == 1
    assert [record["check"] for record in records[:6]] == list(SMOKE.PROGRESSIVE_CHECK_ORDER)
    assert records[-1]["record"] == "progressive_summary"
    assert records[-1]["status"] == "FAIL"
    assert records[-1]["finding_histogram"] == {"intent_discovery_rank_failed": 5}


def test_progressive_summary_turns_missing_checks_into_blocked_records():
    checks = [SMOKE.progressive_check("gateway_presence", "FAIL", 3, 4, missing=["rook_tools_search"])]
    summary, ordered = SMOKE.progressive_summary(checks, [])
    by_name = {record["check"]: record for record in ordered}
    assert by_name["gateway_presence"]["status"] == "FAIL"
    assert by_name["exact_name_resolution"]["status"] == "BLOCKED"
    assert by_name["intent_discovery"]["status"] == "BLOCKED"
    assert summary["status"] == "FAIL"
