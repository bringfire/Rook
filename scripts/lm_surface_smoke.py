#!/usr/bin/env python3
"""LM live-smoke diagnostic (pre-LM2E).

Proves the DEPLOYED rook runtime (site-packages, empty PYTHONPATH) contains the
merged LM2A-D modules, and that the LM2A->D surface chain is sane against the
deployed runtime's own advertised catalog. Diagnostic only: it deploys nothing,
starts/stops nothing, writes nothing to the deployed runtime, and never adds
repo src to sys.path.

Run with the DEPLOYED venv interpreter and an empty PYTHONPATH, e.g. (PowerShell):
  $env:PYTHONPATH=""; & "<...>/Rook/venv/Scripts/python.exe" scripts/lm_surface_smoke.py coherence
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
import os
import sys
from typing import Any


def pythonpath_clean(env_value: str) -> bool:
    """True iff PYTHONPATH is empty/whitespace-only."""
    return not env_value.strip()


def module_origin_ok(module_file: str, site_packages_root: str) -> bool:
    """True iff module_file is contained under site_packages_root.

    Real path containment via os.path.commonpath (not string startswith, which
    would false-pass a sibling like '.../site-packages2/rook'). Case-insensitive
    for Windows via normcase.
    """
    module_path = os.path.normcase(os.path.abspath(module_file))
    root_path = os.path.normcase(os.path.abspath(site_packages_root))
    try:
        return os.path.commonpath([module_path, root_path]) == root_path
    except ValueError:
        return False


def classify_cache(cache_keys, built_keys, required) -> str:
    """Cache tri-state vs. the in-process built catalog.

    - cache_keys is None        -> "absent"
    - no symmetric difference   -> "current"
    - difference touches required -> "fail"
    - otherwise                 -> "warning"
    """
    if cache_keys is None:
        return "absent"
    delta = set(cache_keys) ^ set(built_keys)
    if not delta:
        return "current"
    if delta & set(required):
        return "fail"
    return "warning"


def degenerate_activation_failures(group_failed_tools, catalog_group_names) -> tuple[str, ...]:
    """Groups that failed to activate despite being present in the catalog.

    A group genuinely absent from the catalog is allowed to fail; only a group
    with >=1 catalog member that still failed is the degenerate signal.
    """
    return tuple(sorted(set(group_failed_tools) & set(catalog_group_names)))


def format_surface_evidence(
    *,
    catalog_count: int,
    profile_name: str,
    intended_count: int,
    active_count: int,
    finding_histogram: dict,
    profile_findings_count: int,
) -> str:
    """Deterministic evidence block (histogram rendered in sorted code order)."""
    lines = [
        f"  catalog tools: {catalog_count}",
        f"  profile: {profile_name}",
        f"  intended: {intended_count}",
        f"  active: {active_count}",
        f"  profile_findings: {profile_findings_count}",
        "  registry_findings by code:",
    ]
    for code in sorted(finding_histogram):
        lines.append(f"    {code}: {finding_histogram[code]}")
    return "\n".join(lines)


# --- output helpers ---


def _p(prefix: str, msg: str) -> None:
    print(f"{prefix}: {msg}")


# --- coherence / origin guard (lazy rook import) ---

_LM2_MODULES = (
    "rook.agent.capability_record",
    "rook.agent.capability_inventory",
    "rook.agent.execution_profile",
    "rook.agent.profile_reconciliation",
)


def _site_packages_root() -> str:
    return os.path.join(sys.prefix, "Lib", "site-packages")


def _check_origins() -> int:
    """Import rook + LM2 modules and assert their origin is the deployed
    site-packages. 0 = PASS, 1 = FAIL. Prints rook/server/LM2 origins."""
    import importlib

    spr = _site_packages_root()
    print(f"  sys.prefix: {sys.prefix}")
    print(f"  site-packages root: {spr}")
    try:
        import rook
        import rook.server
    except Exception as exc:  # an import failure is a coherence FAIL
        _p("FAIL", f"could not import rook/rook.server: {exc!r}")
        return 1

    print(f"  rook.__file__: {rook.__file__}")
    print(f"  rook.server.__file__: {rook.server.__file__}")
    failed = False
    for mod_file, name in ((rook.__file__, "rook"), (rook.server.__file__, "rook.server")):
        if not module_origin_ok(mod_file, spr):
            _p("FAIL", f"{name} not under deployed site-packages ({mod_file})")
            failed = True

    for name in _LM2_MODULES:
        try:
            mod = importlib.import_module(name)
        except Exception as exc:
            _p("FAIL", f"LM2 module {name} did not import: {exc!r}")
            failed = True
            continue
        mod_file = getattr(mod, "__file__", "")
        print(f"  {name}.__file__: {mod_file}")
        if not module_origin_ok(mod_file, spr):
            _p("FAIL", f"{name} not under deployed site-packages ({mod_file})")
            failed = True

    return 1 if failed else 0


def run_coherence() -> int:
    print("== coherence ==")
    rc = _check_origins()
    if rc == 0:
        _p("PASS", "all LM2 modules import from deployed site-packages")
    return rc


# --- surface evidence (lazy rook import; gated behind _check_origins) ---

_REQUIRED_BASE = frozenset(
    {
        "request_tools",
        "search_tools",
        "gh_snapshot",
        "gh_create_csharp_script",
        "gh_update_script",
        "gh_errors",
    }
)
_EXPECTED_EXCLUDED = ("gh_exploration", "gh_knowledge", "gh_validation")

DG009_GH_TOOL_NAMES = (
    "gh_update_script",
    "gh_set_script_pins",
    "gh_status",
    "gh_create_csharp_script",
    "gh_snapshot",
)

PROGRESSIVE_GATEWAY_NAMES = (
    "rook_tools_ls",
    "rook_tools_search",
    "rook_tools_read",
    "rook_tools_call",
)

PROGRESSIVE_ALIAS_GATEWAY_NAMES = (
    "rook_tools_search",
    "rook_tools_read",
    "rook_tools_call",
)

PROGRESSIVE_DISCOVERY_TARGETS = (
    "gh_update_script",
    "gh_set_script_pins",
    "gh_create_csharp_script",
    "gh_status",
    "gh_snapshot",
    "agent_status",
)

PROGRESSIVE_HIDDEN_TARGETS = (
    "gh_update_script",
    "gh_set_script_pins",
    "gh_create_csharp_script",
    "gh_status",
    "agent_status",
)

PROGRESSIVE_INTENT_MATRIX = (
    {"query": "edit a Grasshopper script", "expected_tool": "gh_update_script", "limit": 10, "max_rank": 10},
    {"query": "change the inputs and outputs of a Grasshopper script", "expected_tool": "gh_set_script_pins", "limit": 10, "max_rank": 10},
    {"query": "create a C# script component in Grasshopper", "expected_tool": "gh_create_csharp_script", "limit": 10, "max_rank": 10},
    {"query": "check whether Grasshopper is ready", "expected_tool": "gh_status", "limit": 10, "max_rank": 10},
    {"query": "take a snapshot of the Grasshopper canvas", "expected_tool": "gh_snapshot", "limit": 10, "max_rank": 10},
    {"query": "check running agent status", "expected_tool": "agent_status", "limit": 10, "max_rank": 1},
)

PROGRESSIVE_CHECK_ORDER = (
    "gateway_presence",
    "lean_hiddenness",
    "exact_name_resolution",
    "schema_reads",
    "agent_status_call",
    "intent_discovery",
)

PROGRESSIVE_CHECK_EXPECTED = {
    "gateway_presence": 4,
    "lean_hiddenness": 5,
    "exact_name_resolution": 5,
    "schema_reads": 6,
    "agent_status_call": 1,
    "intent_discovery": 6,
}


def progressive_check(
    check: str,
    status: str,
    observed: int,
    expected: int,
    **details: Any,
) -> dict[str, Any]:
    if status not in {"PASS", "FAIL", "BLOCKED"}:
        raise ValueError(f"invalid progressive status: {status}")
    return {
        "record": "progressive_check",
        "check": check,
        "status": status,
        "observed": observed,
        "expected": expected,
        "details": details,
    }


def progressive_finding(code: str, **details: Any) -> dict[str, Any]:
    return {"record": "progressive_finding", "code": code, **details}


def progressive_gateway_metadata_failures(catalog: dict) -> list[str]:
    failures: list[str] = []
    for gateway in PROGRESSIVE_ALIAS_GATEWAY_NAMES:
        record = catalog.get(gateway)
        if not isinstance(record, dict):
            failures.append(f"{gateway} missing from lean catalog")
            continue
        function = record.get("function") if isinstance(record.get("function"), dict) else {}
        description = str(function.get("description") or "")
        for tool_name in DG009_GH_TOOL_NAMES:
            if tool_name not in description:
                failures.append(f"{gateway} missing {tool_name}")
    return failures


def progressive_intent_findings(
    search_results: dict[str, list[Any]],
) -> list[dict[str, Any]]:
    findings = []
    for row in PROGRESSIVE_INTENT_MATRIX:
        candidates = search_results.get(row["query"], [])
        rank = next(
            (
                index
                for index, candidate in enumerate(candidates, start=1)
                if isinstance(candidate, dict)
                and candidate.get("name") == row["expected_tool"]
            ),
            None,
        )
        if rank is None or rank > row["max_rank"]:
            findings.append(
                progressive_finding(
                    "intent_discovery_rank_failed",
                    query=row["query"],
                    expected_tool=row["expected_tool"],
                    limit=row["limit"],
                    max_rank=row["max_rank"],
                    observed_rank=rank,
                )
            )
    return findings


def progressive_read_findings(
    read_records: dict[str, dict],
) -> list[dict[str, Any]]:
    findings = []
    for target in PROGRESSIVE_DISCOVERY_TARGETS:
        record = read_records.get(target)
        reason = None
        if not isinstance(record, dict):
            reason = "record_missing"
        elif record.get("name") != target:
            reason = "wrong_name"
        elif record.get("mcp_dispatchable") is not True:
            reason = "mcp_dispatchable_not_true"
        elif (
            not isinstance(record.get("input_schema"), dict)
            or record["input_schema"].get("type") != "object"
        ):
            reason = "input_schema_not_object"
        if reason:
            findings.append(
                progressive_finding("schema_read_failed", target=target, reason=reason)
            )
    return findings


def progressive_summary(
    checks: list[dict[str, Any]],
    findings: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    by_name = {record["check"]: record for record in checks}
    ordered = []
    for name in PROGRESSIVE_CHECK_ORDER:
        ordered.append(
            by_name.get(name)
            or progressive_check(
                name,
                "BLOCKED",
                0,
                PROGRESSIVE_CHECK_EXPECTED[name],
                blocked_by=["record_missing"],
            )
        )
    histogram = dict(sorted(Counter(finding["code"] for finding in findings).items()))
    status = (
        "PASS"
        if not findings and all(record["status"] == "PASS" for record in ordered)
        else "FAIL"
    )
    return (
        {
            "record": "progressive_summary",
            "status": status,
            "checks": {record["check"]: record["status"] for record in ordered},
            "finding_histogram": histogram,
        },
        ordered,
    )


def emit_progressive_evidence(
    checks: list[dict[str, Any]],
    findings: list[dict[str, Any]],
) -> int:
    summary, ordered = progressive_summary(checks, findings)
    for record in ordered:
        print(json.dumps(record, sort_keys=True))
    for finding in findings:
        print(json.dumps(finding, sort_keys=True))
    print(json.dumps(summary, sort_keys=True))
    return 0 if summary["status"] == "PASS" else 1

_EXTERNAL_FAIL_CODES = frozenset(
    {
        "advertised_not_dispatchable",
        "empty_catalog",
        "dispatch_function_missing",
        "wire_source_unresolved",
    }
)
_EXTERNAL_WARN_CODES = frozenset({"multiple_dispatch_matches", "unextractable_case"})


def external_exit_decision(findings) -> tuple[int, tuple[str, ...], tuple[str, ...]]:
    """Pure gate: derive (exit_code, warn_codes, fail_codes) from finding codes.

    Failure is decided ONLY by structured codes -- never by report text.
    """
    codes = {f.code for f in findings}
    fail = tuple(sorted(codes & _EXTERNAL_FAIL_CODES))
    warn = tuple(sorted(codes & _EXTERNAL_WARN_CODES))
    return (1 if fail else 0), warn, fail


def run_surface() -> int:
    print("== surface ==")
    rc = _check_origins()
    if rc != 0:
        _p("FAIL", "origin guard failed; refusing surface work")
        return rc

    import asyncio

    from rook.server import list_tools
    from rook.agent.tool_registry import (
        build_catalog_from_mcp_tools,
        get_catalog_cache_path,
        load_catalog_from_cache,
    )
    from rook.agent.tool_groups import TOOL_GROUPS
    from rook.agent.capability_inventory import build_inventory, collect_runtime_sources
    from rook.agent.execution_profile import (
        readonly_excluded_mcp_only_groups,
        readonly_profile_from_sources,
        resolve_profile,
    )
    from rook.agent.profile_reconciliation import reconcile_profile

    try:
        tools = asyncio.run(list_tools())
        catalog = build_catalog_from_mcp_tools(tools)
    except Exception as exc:
        _p("FAIL", f"catalog build from deployed list_tools() failed: {exc!r}")
        return 1
    if not catalog:
        _p("FAIL", "deployed list_tools() produced an empty catalog")
        return 1

    try:
        sources = collect_runtime_sources()
    except Exception as exc:
        _p("FAIL", f"collect_runtime_sources() failed: {exc!r}")
        return 1
    print(f"  local tools (runtime-enriched): {len(sources.local_tool_names)}")
    inventory = build_inventory(sources, catalog)
    profile = readonly_profile_from_sources(sources)
    resolution = resolve_profile(profile, inventory)
    rec = reconcile_profile(resolution, sources, catalog)

    histogram: dict = {}
    for finding in rec.registry_findings:
        histogram[finding.code] = histogram.get(finding.code, 0) + 1
    print(
        format_surface_evidence(
            catalog_count=len(catalog),
            profile_name=rec.profile_name,
            intended_count=len(rec.intended_names),
            active_count=len(rec.active_names),
            finding_histogram=histogram,
            profile_findings_count=len(rec.profile_findings),
        )
    )

    failed = False

    excluded = readonly_excluded_mcp_only_groups(sources)
    if excluded != _EXPECTED_EXCLUDED:
        _p("FAIL", f"readonly_excluded_mcp_only_groups != {_EXPECTED_EXCLUDED}: {excluded}")
        failed = True
    overlap = set(profile.groups) & set(_EXPECTED_EXCLUDED)
    if overlap:
        _p("FAIL", f"readonly profile includes MCP-only groups: {sorted(overlap)}")
        failed = True

    catalog_group_names = {
        g for g, members in TOOL_GROUPS.items() if any(m in catalog for m in members)
    }
    group_failed = {
        f.tool for f in rec.registry_findings if f.code == "group_activation_failed"
    }
    degenerate = degenerate_activation_failures(group_failed, catalog_group_names)
    if degenerate:
        _p("FAIL", f"groups present in catalog failed to activate: {list(degenerate)}")
        failed = True

    required = set(_REQUIRED_BASE) | set(resolution.tool_names)
    cache_path = get_catalog_cache_path()
    cached = load_catalog_from_cache(cache_path)
    cache_keys = None if cached is None else set(cached.keys())
    verdict = classify_cache(cache_keys, set(catalog.keys()), required)
    if verdict == "absent":
        _p("DEGRADED", f"no catalog cache at {cache_path}; built from live list_tools()")
    elif verdict == "current":
        _p("PASS", "catalog cache matches deployed runtime")
    elif verdict == "warning":
        delta = sorted(cache_keys ^ set(catalog.keys()))
        shown = delta[:20]
        suffix = " ..." if len(delta) > 20 else ""
        _p("WARNING", f"catalog cache drifts (non-required): {shown}{suffix}")
    else:  # "fail"
        delta = sorted((cache_keys ^ set(catalog.keys())) & required)
        _p("FAIL", f"catalog cache drift touches required tools: {delta}")
        failed = True

    if failed:
        _p("FAIL", "surface evidence smoke failed")
        return 1
    _p("PASS", "surface evidence smoke passed")
    return 0


def run_external() -> int:
    print("== external ==")
    rc = _check_origins()
    if rc != 0:
        _p("FAIL", "origin guard failed; refusing external (wire-dispatch) audit")
        return rc

    import asyncio

    import rook.server
    from rook.server import list_tools
    from rook.agent.tool_registry import build_catalog_from_mcp_tools
    from rook.agent.external_mcp import (
        collect_wire_dispatch_evidence,
        reconcile_external_mcp,
    )

    try:
        tools = asyncio.run(list_tools())
        catalog = build_catalog_from_mcp_tools(tools)
    except Exception as exc:
        _p("FAIL", f"catalog build from deployed list_tools() failed: {exc!r}")
        return 1
    if not catalog:
        _p("FAIL", "deployed list_tools() produced an empty catalog")
        return 1

    evidence = collect_wire_dispatch_evidence("rook.server")
    resolution = reconcile_external_mcp(tuple(catalog.keys()), evidence)

    print(f"  wire-dispatch source: {rook.server.__file__}")
    print(f"  advertised tools: {len(resolution.advertised_names)}")
    print(f"  wire handlers: {len(resolution.wire_dispatch_names)}")
    histogram: dict = {}
    for finding in resolution.findings:
        histogram[finding.code] = histogram.get(finding.code, 0) + 1
    print("  findings by code:")
    for code in sorted(histogram):
        print(f"    {code}: {histogram[code]}")
    for finding in resolution.findings:
        if finding.code == "handler_not_advertised":
            print(f"  INFO: {finding.tool} (wire handler not advertised)")

    exit_code, warn_codes, fail_codes = external_exit_decision(resolution.findings)
    if warn_codes:
        _p("WARNING", f"extraction anomalies: {list(warn_codes)}")
    if fail_codes:
        _p("FAIL", f"external audit failed on: {list(fail_codes)}")
        return 1
    _p("PASS", "external (wire-dispatch) audit passed")
    return exit_code


def run_progressive() -> int:
    print("== progressive ==")
    previous_profile = os.environ.get("ROOK_MCP_TOOL_PROFILE")
    os.environ["ROOK_MCP_TOOL_PROFILE"] = "lean"
    try:
        rc = _check_origins()
        if rc != 0:
            _p("FAIL", "origin guard failed; refusing progressive disclosure smoke")
            return rc

        import asyncio

        from rook.server import call_tool, list_tools
        from rook.agent.tool_registry import build_catalog_from_mcp_tools

        tools = asyncio.run(list_tools())
        catalog = build_catalog_from_mcp_tools(tools)
        names = set(catalog)
        hidden_mutators = {"gh_update_script", "gh_set_script_pins", "gh_create_csharp_script"}
        if not set(PROGRESSIVE_GATEWAY_NAMES) <= names:
            missing = sorted(set(PROGRESSIVE_GATEWAY_NAMES) - names)
            _p("FAIL", f"lean catalog missing progressive gateways: {missing}")
            return 1
        if hidden_mutators & names:
            _p("FAIL", f"lean catalog directly advertised hidden GH mutators: {sorted(hidden_mutators & names)}")
            return 1

        metadata_failures = progressive_gateway_metadata_failures(catalog)
        if metadata_failures:
            for failure in metadata_failures:
                _p("FAIL", failure)
            return 1

        search_results: dict[str, list[dict]] = {}
        for tool_name in DG009_GH_TOOL_NAMES:
            response = asyncio.run(call_tool("rook_tools_search", {"query": tool_name, "limit": 10}))
            search_results[tool_name] = json.loads(response[0].text)
        search_failures = progressive_search_failures(search_results)
        if search_failures:
            for failure in search_failures:
                _p("FAIL", failure)
            return 1

        read_records: dict[str, dict] = {}
        for tool_name in DG009_GH_TOOL_NAMES:
            response = asyncio.run(call_tool("rook_tools_read", {"name": tool_name}))
            read_records[tool_name] = json.loads(response[0].text)
        read_failures = progressive_read_failures(read_records)
        if read_failures:
            for failure in read_failures:
                _p("FAIL", failure)
            return 1

        _p("PASS", "progressive disclosure smoke passed under lean")
        return 0
    finally:
        if previous_profile is None:
            os.environ.pop("ROOK_MCP_TOOL_PROFILE", None)
        else:
            os.environ["ROOK_MCP_TOOL_PROFILE"] = previous_profile


# --- CLI ---


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lm_surface_smoke",
        description="LM live-smoke diagnostic (deployed-runtime coherence + surface evidence).",
    )
    parser.add_argument("command", choices=("coherence", "surface", "external", "progressive"))
    return parser


def main(argv) -> int:
    args = build_parser().parse_args(argv)
    pythonpath = os.environ.get("PYTHONPATH", "")
    print(f"PYTHONPATH={pythonpath!r}")
    if not pythonpath_clean(pythonpath):
        _p(
            "FAIL",
            "PYTHONPATH is non-empty; refusing to run (it can shadow deployed "
            "site-packages with repo source)",
        )
        return 1
    if args.command == "coherence":
        return run_coherence()
    if args.command == "surface":
        return run_surface()
    if args.command == "external":
        return run_external()
    return run_progressive()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
