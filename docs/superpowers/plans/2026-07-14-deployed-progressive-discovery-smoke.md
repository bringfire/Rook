# Deployed Progressive Discovery Smoke Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add deployed-runtime and live-plugin evidence proving the existing lean progressive-discovery gateways, while preserving the five known realistic-query ranking failures as an explicit expected-red release gate.

**Architecture:** Keep the change in the existing smoke and release-proof surfaces. `scripts/lm_surface_smoke.py` owns deterministic standalone evidence and the realistic-intent matrix; `rook.local_testing_proof` and the deploy script independently prove an exact-name live `gh_status` chain; the release-readiness wrapper runs the realistic gate last. The work changes validation only and does not alter search, schemas, exposure, dispatch, or policy.

**Tech Stack:** Python 3.10+, pytest/pytest-asyncio, MCP `Tool`/`TextContent` wire objects, Windows PowerShell 5.1, existing Rook deployment and runtime-harness scripts.

## Global Constraints

- Work only in `C:/Users/aryan/source/repos/Rook/.worktrees/deployed-progressive-smoke-implementation` on branch `codex/deployed-progressive-smoke-implementation`.
- Do not modify capability-index scoring, ranking, tool descriptions, tool schemas, profile membership, dispatch, targeting, or safety policy.
- Do not add external dependencies.
- Force `ROOK_MCP_TOOL_PROFILE=lean` for both live progressive proofs and restore the inherited value afterward.
- The standalone deployed gate must run with `%LOCALAPPDATA%/Rook/venv/Scripts/python.exe` and an empty `PYTHONPATH`.
- The deployed origin gate must cover `rook`, `rook.server`, `rook.capability_index`, `rook.agent.capability_record`, `rook.agent.capability_inventory`, `rook.agent.execution_profile`, `rook.agent.profile_reconciliation`, and `rook.agent.tool_registry` under the invoked interpreter's `Lib/site-packages`.
- Current implementation acceptance is expected-red: exactly five `intent_discovery_rank_failed` findings; the five non-intent checks pass, `intent_discovery` fails 1-of-6, and release readiness fails last with `progressive_discovery_failed`.
- Origin failure stops immediately. After origins pass, emit all six check records and a final summary; a dependent check that cannot run is `BLOCKED`, never absent or falsely passing.
- Preserve ordinary deployment and the direct Rhino/Grasshopper controls.
- No native or managed source changes are required. Do not add a separate native build task; if the existing release-readiness workflow builds native payloads, record its actual result and use MSVC `14.44.35207` for any direct MFC build retry.

## File Responsibility Map

- `scripts/lm_surface_smoke.py`: pinned matrices, validation helpers, deterministic check/finding/summary records, deployed origins, and the standalone expected-red progressive runner.
- `mcp_server/tests/test_lm_surface_smoke.py`: pure validation, ordering, `BLOCKED` propagation, histogram, summary, and expected-red runner coverage.
- `mcp_server/src/rook/local_testing_proof.py`: owned live exact-name `gh_status` chain, lean scoping, public-wire decoding, and structured evidence promotion.
- `mcp_server/tests/test_local_testing_proof.py`: live ordering/profile restoration, exact-name chain, failure behavior, and owned-artifact promotion.
- `scripts/deploy-local-testing.ps1`: developer `-LiveSmoke` exact-name chain and scoped lean environment.
- `scripts/tests/deploy-local-testing-guards.tests.ps1`: static contract and ordering guards for developer live smoke.
- `scripts/validate-local-testing-stack.ps1`: final installed-runtime `progressive_discovery` release gate with scoped empty `PYTHONPATH`.
- `scripts/tests/local-testing-stack-guards.tests.ps1`: stable name/label, installed interpreter, empty environment, and gate-order guards.

---

### Task 1: Define deterministic evidence records and pinned validators

**Files:**
- Modify: `scripts/lm_surface_smoke.py:15-225`
- Test: `mcp_server/tests/test_lm_surface_smoke.py:168-235`

**Interfaces:**
- Produces: `PROGRESSIVE_GATEWAY_NAMES`, `PROGRESSIVE_ALIAS_GATEWAY_NAMES`, `PROGRESSIVE_DISCOVERY_TARGETS`, `PROGRESSIVE_HIDDEN_TARGETS`, `PROGRESSIVE_INTENT_MATRIX`, `PROGRESSIVE_CHECK_ORDER`.
- Produces: `progressive_check() -> dict[str, Any]`, `progressive_finding() -> dict[str, Any]`, `progressive_intent_findings() -> list[dict[str, Any]]`, `progressive_read_findings() -> list[dict[str, Any]]`, `progressive_summary() -> tuple[dict[str, Any], list[dict[str, Any]]]`, and `emit_progressive_evidence() -> int`.
- Consumed by: Task 2's deployed runner.

- [ ] **Step 1: Write failing tests for the pinned sets and validation contracts**

Add imports for `asyncio`, `json`, and `os`, then add tests that pin the exact products rather than scorer-friendly substitutes:

```python
import asyncio
import json
import os
```

Replace the existing `test_progressive_search_validation_requires_exact_records` and `test_progressive_read_validation_requires_gh_object_schemas` tests with the record-oriented tests below; the old string-only helper contracts are intentionally retired.

```python
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
```

- [ ] **Step 2: Run the new contract tests and confirm they fail**

Run:

```powershell
$env:PYTHONPATH = (Resolve-Path 'mcp_server/src').Path
& 'C:/Users/aryan/source/repos/Rook/mcp_server/.venv/Scripts/python.exe' -m pytest `
  mcp_server/tests/test_lm_surface_smoke.py -k 'progressive_contract or progressive_intent or progressive_read' -v
```

Expected: FAIL because the four-way gateway set, realistic matrix, and record-producing validators do not exist yet.

- [ ] **Step 3: Add the exact constants and pure validators**

Replace the current progressive constants and string-only search/read validators with this shape; retain `progressive_gateway_metadata_failures`, but iterate `PROGRESSIVE_ALIAS_GATEWAY_NAMES` inside it:

```python
from collections import Counter
from typing import Any

DG009_GH_TOOL_NAMES = (
    "gh_update_script", "gh_set_script_pins", "gh_status",
    "gh_create_csharp_script", "gh_snapshot",
)
PROGRESSIVE_GATEWAY_NAMES = (
    "rook_tools_ls", "rook_tools_search", "rook_tools_read", "rook_tools_call",
)
PROGRESSIVE_ALIAS_GATEWAY_NAMES = (
    "rook_tools_search", "rook_tools_read", "rook_tools_call",
)
PROGRESSIVE_DISCOVERY_TARGETS = (
    "gh_update_script", "gh_set_script_pins", "gh_create_csharp_script",
    "gh_status", "gh_snapshot", "agent_status",
)
PROGRESSIVE_HIDDEN_TARGETS = (
    "gh_update_script", "gh_set_script_pins", "gh_create_csharp_script",
    "gh_status", "agent_status",
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
    "gateway_presence", "lean_hiddenness", "exact_name_resolution",
    "schema_reads", "agent_status_call", "intent_discovery",
)
PROGRESSIVE_CHECK_EXPECTED = {
    "gateway_presence": 4, "lean_hiddenness": 5, "exact_name_resolution": 5,
    "schema_reads": 6, "agent_status_call": 1, "intent_discovery": 6,
}


def progressive_check(check: str, status: str, observed: int, expected: int, **details: Any) -> dict[str, Any]:
    if status not in {"PASS", "FAIL", "BLOCKED"}:
        raise ValueError(f"invalid progressive status: {status}")
    return {
        "record": "progressive_check", "check": check, "status": status,
        "observed": observed, "expected": expected, "details": details,
    }


def progressive_finding(code: str, **details: Any) -> dict[str, Any]:
    return {"record": "progressive_finding", "code": code, **details}


def progressive_intent_findings(search_results: dict[str, list[dict]]) -> list[dict[str, Any]]:
    findings = []
    for row in PROGRESSIVE_INTENT_MATRIX:
        candidates = search_results.get(row["query"], [])
        rank = next(
            (index for index, candidate in enumerate(candidates, start=1)
             if candidate.get("name") == row["expected_tool"]),
            None,
        )
        if rank is None or rank > row["max_rank"]:
            findings.append(progressive_finding(
                "intent_discovery_rank_failed", query=row["query"],
                expected_tool=row["expected_tool"], limit=row["limit"],
                max_rank=row["max_rank"], observed_rank=rank,
            ))
    return findings


def progressive_read_findings(read_records: dict[str, dict]) -> list[dict[str, Any]]:
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
        elif not isinstance(record.get("input_schema"), dict) or record["input_schema"].get("type") != "object":
            reason = "input_schema_not_object"
        if reason:
            findings.append(progressive_finding("schema_read_failed", target=target, reason=reason))
    return findings
```

- [ ] **Step 4: Add deterministic ordering, histogram, and nonzero-summary tests**

```python
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
```

- [ ] **Step 5: Implement deterministic summary and emission**

```python
def progressive_summary(checks: list[dict[str, Any]], findings: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    by_name = {record["check"]: record for record in checks}
    ordered = []
    for name in PROGRESSIVE_CHECK_ORDER:
        ordered.append(by_name.get(name) or progressive_check(
            name, "BLOCKED", 0, PROGRESSIVE_CHECK_EXPECTED[name], blocked_by=["record_missing"]
        ))
    histogram = dict(sorted(Counter(finding["code"] for finding in findings).items()))
    status = "PASS" if not findings and all(record["status"] == "PASS" for record in ordered) else "FAIL"
    return ({
        "record": "progressive_summary",
        "status": status,
        "checks": {record["check"]: record["status"] for record in ordered},
        "finding_histogram": histogram,
    }, ordered)


def emit_progressive_evidence(checks: list[dict[str, Any]], findings: list[dict[str, Any]]) -> int:
    summary, ordered = progressive_summary(checks, findings)
    for record in ordered:
        print(json.dumps(record, sort_keys=True))
    for finding in findings:
        print(json.dumps(finding, sort_keys=True))
    print(json.dumps(summary, sort_keys=True))
    return 0 if summary["status"] == "PASS" else 1
```

- [ ] **Step 6: Run the focused suite and commit**

Run:

```powershell
$env:PYTHONPATH = (Resolve-Path 'mcp_server/src').Path
& 'C:/Users/aryan/source/repos/Rook/mcp_server/.venv/Scripts/python.exe' -m pytest `
  mcp_server/tests/test_lm_surface_smoke.py -v
git add scripts/lm_surface_smoke.py mcp_server/tests/test_lm_surface_smoke.py
git commit -m "test: pin progressive discovery evidence contract"
```

Expected: all `test_lm_surface_smoke.py` tests pass.

---

### Task 2: Implement the deployed expected-red progressive runner

**Files:**
- Modify: `scripts/lm_surface_smoke.py:98-156,409-468`
- Test: `mcp_server/tests/test_lm_surface_smoke.py`

**Interfaces:**
- Consumes: all constants and evidence helpers from Task 1.
- Produces: `collect_progressive_evidence(catalog, call_tool_fn) -> tuple[list[dict], list[dict]]`.
- Produces: `run_progressive() -> int` that stops on origin failure and otherwise always emits the deterministic summary.

- [ ] **Step 1: Write a failing expected-red collector test**

Create a catalog containing all four gateways, with the five hidden targets absent and `gh_snapshot` present. Use a fake public MCP call that returns exact-name hits, valid reads, a valid `agent_status` call, but omits the first five realistic targets:

```python
def _wire(payload):
    from types import SimpleNamespace
    return [SimpleNamespace(text=json.dumps(payload))]


def _progressive_catalog(include_search=True):
    aliases = " ".join(SMOKE.DG009_GH_TOOL_NAMES)
    names = ["rook_tools_ls", "rook_tools_read", "rook_tools_call", "gh_snapshot"]
    if include_search:
        names.insert(1, "rook_tools_search")
    return {
        name: {"function": {"description": aliases if name in SMOKE.PROGRESSIVE_ALIAS_GATEWAY_NAMES else ""}}
        for name in names
    }


def test_progressive_origin_contract_pins_every_deployed_module():
    assert SMOKE._DEPLOYED_ORIGIN_MODULES == (
        "rook", "rook.server", "rook.capability_index",
        "rook.agent.capability_record", "rook.agent.capability_inventory",
        "rook.agent.execution_profile", "rook.agent.profile_reconciliation",
        "rook.agent.tool_registry",
    )


def test_collect_progressive_evidence_matches_expected_red_baseline():
    async def fake_call(name, arguments):
        if name == "rook_tools_search":
            query = arguments["query"]
            if query in SMOKE.PROGRESSIVE_DISCOVERY_TARGETS:
                return _wire([{"name": query}])
            if query == "check running agent status":
                return _wire([{"name": "agent_status"}])
            return _wire([{"name": "unrelated_tool"}])
        if name == "rook_tools_read":
            target = arguments["name"]
            return _wire({"name": target, "mcp_dispatchable": True, "input_schema": {"type": "object"}})
        if name == "rook_tools_call":
            return _wire({"count": 0, "agents": []})
        raise AssertionError((name, arguments))

    checks, findings = asyncio.run(SMOKE.collect_progressive_evidence(_progressive_catalog(), fake_call))
    by_name = {record["check"]: record for record in checks}
    assert all(by_name[name]["status"] == "PASS" for name in (
        "gateway_presence", "lean_hiddenness", "exact_name_resolution",
        "schema_reads", "agent_status_call",
    ))
    assert by_name["intent_discovery"]["status"] == "FAIL"
    assert by_name["intent_discovery"]["observed"] == 1
    assert by_name["intent_discovery"]["expected"] == 6
    assert [finding["code"] for finding in findings] == ["intent_discovery_rank_failed"] * 5
```

- [ ] **Step 2: Write failing dependency and `BLOCKED` propagation coverage**

```python
def test_missing_search_gateway_blocks_only_search_dependent_checks():
    calls = []

    async def fake_call(name, arguments):
        calls.append((name, arguments))
        if name == "rook_tools_read":
            target = arguments["name"]
            return _wire({"name": target, "mcp_dispatchable": True, "input_schema": {"type": "object"}})
        raise AssertionError((name, arguments))

    checks, findings = asyncio.run(
        SMOKE.collect_progressive_evidence(_progressive_catalog(include_search=False), fake_call)
    )
    by_name = {record["check"]: record for record in checks}
    assert by_name["gateway_presence"]["status"] == "FAIL"
    assert by_name["lean_hiddenness"]["status"] == "PASS"
    assert by_name["exact_name_resolution"]["status"] == "BLOCKED"
    assert by_name["schema_reads"]["status"] == "PASS"
    assert by_name["agent_status_call"]["status"] == "BLOCKED"
    assert by_name["intent_discovery"]["status"] == "BLOCKED"
    assert all(name == "rook_tools_read" for name, _ in calls)
    assert any(finding["code"] == "gateway_presence_failed" for finding in findings)
```

- [ ] **Step 3: Run both collector tests and verify they fail**

Run:

```powershell
$env:PYTHONPATH = (Resolve-Path 'mcp_server/src').Path
& 'C:/Users/aryan/source/repos/Rook/mcp_server/.venv/Scripts/python.exe' -m pytest `
  mcp_server/tests/test_lm_surface_smoke.py -k 'collect_progressive or missing_search_gateway' -v
```

Expected: FAIL because `collect_progressive_evidence` is not defined.

- [ ] **Step 4: Implement wire decoding and the dependency-aware collector**

Add a private decoder that rejects public MCP `Error:` text, then implement the collector in this fixed order:

```python
def _decode_public_tool_result(response) -> tuple[Any | None, str | None]:
    if not response:
        return None, "empty_response"
    text = str(response[0].text)
    if text.startswith("Error:"):
        return None, text
    try:
        return json.loads(text), None
    except json.JSONDecodeError as exc:
        return None, f"invalid_json:{exc}"


async def _meta_json(call_tool_fn, name: str, arguments: dict) -> tuple[Any | None, str | None]:
    try:
        return _decode_public_tool_result(await call_tool_fn(name, arguments))
    except Exception as exc:
        return None, f"{type(exc).__name__}:{exc}"
```

Implement the collector without early returns. This complete flow preserves independent reads when search is unavailable and blocks only dependent checks:

```python
async def collect_progressive_evidence(catalog: dict, call_tool_fn) -> tuple[list[dict], list[dict]]:
    findings: list[dict[str, Any]] = []
    names = set(catalog)

    missing_gateways = [name for name in PROGRESSIVE_GATEWAY_NAMES if name not in names]
    for name in missing_gateways:
        findings.append(progressive_finding("gateway_presence_failed", gateway=name))
    for failure in progressive_gateway_metadata_failures(catalog):
        findings.append(progressive_finding("gateway_metadata_failed", reason=failure))
    gateway_check = progressive_check(
        "gateway_presence", "PASS" if not missing_gateways else "FAIL",
        len(PROGRESSIVE_GATEWAY_NAMES) - len(missing_gateways),
        PROGRESSIVE_CHECK_EXPECTED["gateway_presence"], missing=missing_gateways,
    )

    leaked = [name for name in PROGRESSIVE_HIDDEN_TARGETS if name in names]
    for name in leaked:
        findings.append(progressive_finding("lean_hiddenness_failed", target=name))
    hidden_check = progressive_check(
        "lean_hiddenness", "PASS" if not leaked else "FAIL",
        len(PROGRESSIVE_HIDDEN_TARGETS) - len(leaked),
        PROGRESSIVE_CHECK_EXPECTED["lean_hiddenness"], leaked=leaked,
    )

    intent_findings: list[dict[str, Any]] = []
    agent_intent_ok = False
    if "rook_tools_search" in names:
        exact_passes = 0
        exact_failures = []
        for target in DG009_GH_TOOL_NAMES:
            value, error = await _meta_json(
                call_tool_fn, "rook_tools_search", {"query": target, "limit": 10}
            )
            found = isinstance(value, list) and any(item.get("name") == target for item in value)
            if found:
                exact_passes += 1
            else:
                exact_failures.append(target)
                findings.append(progressive_finding(
                    "exact_name_resolution_failed", target=target, error=error,
                ))
        exact_check = progressive_check(
            "exact_name_resolution", "PASS" if exact_passes == 5 else "FAIL",
            exact_passes, PROGRESSIVE_CHECK_EXPECTED["exact_name_resolution"],
            failed=exact_failures,
        )

        intent_results = {}
        for row in PROGRESSIVE_INTENT_MATRIX:
            value, _error = await _meta_json(
                call_tool_fn, "rook_tools_search",
                {"query": row["query"], "limit": row["limit"]},
            )
            intent_results[row["query"]] = value if isinstance(value, list) else []
        intent_findings = progressive_intent_findings(intent_results)
        intent_passes = len(PROGRESSIVE_INTENT_MATRIX) - len(intent_findings)
        intent_check = progressive_check(
            "intent_discovery", "PASS" if not intent_findings else "FAIL",
            intent_passes, PROGRESSIVE_CHECK_EXPECTED["intent_discovery"],
        )
        agent_intent_ok = not any(
            finding.get("expected_tool") == "agent_status" for finding in intent_findings
        )
    else:
        exact_check = progressive_check(
            "exact_name_resolution", "BLOCKED", 0,
            PROGRESSIVE_CHECK_EXPECTED["exact_name_resolution"],
            blocked_by=["rook_tools_search"],
        )
        intent_check = progressive_check(
            "intent_discovery", "BLOCKED", 0,
            PROGRESSIVE_CHECK_EXPECTED["intent_discovery"],
            blocked_by=["rook_tools_search"],
        )

    read_records: dict[str, dict] = {}
    read_findings: list[dict[str, Any]] = []
    if "rook_tools_read" in names:
        for target in PROGRESSIVE_DISCOVERY_TARGETS:
            value, _error = await _meta_json(call_tool_fn, "rook_tools_read", {"name": target})
            if isinstance(value, dict):
                read_records[target] = value
        read_findings = progressive_read_findings(read_records)
        read_passes = len(PROGRESSIVE_DISCOVERY_TARGETS) - len(read_findings)
        read_check = progressive_check(
            "schema_reads", "PASS" if not read_findings else "FAIL",
            read_passes, PROGRESSIVE_CHECK_EXPECTED["schema_reads"],
        )
    else:
        read_check = progressive_check(
            "schema_reads", "BLOCKED", 0,
            PROGRESSIVE_CHECK_EXPECTED["schema_reads"],
            blocked_by=["rook_tools_read"],
        )

    agent_read_ok = "agent_status" in read_records and not any(
        finding.get("target") == "agent_status" for finding in read_findings
    )
    agent_blocked_by = []
    if not agent_intent_ok:
        agent_blocked_by.append("agent_status_intent_search")
    if not agent_read_ok:
        agent_blocked_by.append("agent_status_read")
    if "rook_tools_call" not in names:
        agent_blocked_by.append("rook_tools_call")

    if agent_blocked_by:
        agent_check = progressive_check(
            "agent_status_call", "BLOCKED", 0,
            PROGRESSIVE_CHECK_EXPECTED["agent_status_call"],
            blocked_by=sorted(agent_blocked_by),
        )
    else:
        agent_call, agent_error = await _meta_json(
            call_tool_fn, "rook_tools_call", {"name": "agent_status", "arguments": {}}
        )
        agent_call_ok = (
            isinstance(agent_call, dict)
            and isinstance(agent_call.get("count"), int)
            and not isinstance(agent_call.get("count"), bool)
            and isinstance(agent_call.get("agents"), list)
        )
        if not agent_call_ok:
            findings.append(progressive_finding(
                "agent_status_call_failed", target="agent_status",
                error=agent_error, result=agent_call,
            ))
        agent_check = progressive_check(
            "agent_status_call", "PASS" if agent_call_ok else "FAIL",
            1 if agent_call_ok else 0,
            PROGRESSIVE_CHECK_EXPECTED["agent_status_call"],
        )

    findings.extend(read_findings)
    findings.extend(intent_findings)
    checks = [
        gateway_check, hidden_check, exact_check, read_check, agent_check, intent_check,
    ]
    return checks, findings
```

- [ ] **Step 5: Expand the deployed origin contract**

Replace `_LM2_MODULES` with a complete `_DEPLOYED_ORIGIN_MODULES` tuple and make `_check_origins` import every entry through `importlib.import_module`:

```python
_DEPLOYED_ORIGIN_MODULES = (
    "rook", "rook.server", "rook.capability_index",
    "rook.agent.capability_record", "rook.agent.capability_inventory",
    "rook.agent.execution_profile", "rook.agent.profile_reconciliation",
    "rook.agent.tool_registry",
)
```

Keep the existing real-path containment check. An import or containment failure returns 1 before any progressive tool call.

- [ ] **Step 6: Replace early-return progressive execution with final evidence emission**

Use the existing lean save/restore block, but after origins pass run the collector and always call `emit_progressive_evidence`:

```python
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
        checks, findings = asyncio.run(collect_progressive_evidence(catalog, call_tool))
        return emit_progressive_evidence(checks, findings)
    finally:
        if previous_profile is None:
            os.environ.pop("ROOK_MCP_TOOL_PROFILE", None)
        else:
            os.environ["ROOK_MCP_TOOL_PROFILE"] = previous_profile
```

- [ ] **Step 7: Add a runner test proving summary-last on expected-red exit**

Use explicit fake lazy-import modules, then assert `run_progressive()` returns 1, emits six checks, five findings, and one final summary. Also assert the profile is restored to a sentinel value after the run:

```python
def test_run_progressive_expected_red_emits_summary_last_and_restores_profile(monkeypatch, capsys):
    import sys
    from types import ModuleType

    fake_server = ModuleType("rook.server")

    async def fake_list_tools():
        return []

    async def fake_call_tool(_name, _arguments):
        raise AssertionError("collector is replaced in this runner test")

    fake_server.list_tools = fake_list_tools
    fake_server.call_tool = fake_call_tool
    fake_registry = ModuleType("rook.agent.tool_registry")
    fake_registry.build_catalog_from_mcp_tools = lambda _tools: {}
    monkeypatch.setitem(sys.modules, "rook.server", fake_server)
    monkeypatch.setitem(sys.modules, "rook.agent.tool_registry", fake_registry)
    monkeypatch.setattr(SMOKE, "_check_origins", lambda: 0)

    async def fake_collect(_catalog, _call_tool):
        checks = [
            SMOKE.progressive_check(name, "PASS" if name != "intent_discovery" else "FAIL", 1, 1)
            for name in SMOKE.PROGRESSIVE_CHECK_ORDER
        ]
        findings = [
            SMOKE.progressive_finding("intent_discovery_rank_failed", query=str(index))
            for index in range(5)
        ]
        return checks, findings

    monkeypatch.setattr(SMOKE, "collect_progressive_evidence", fake_collect)
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "readonly")
    rc = SMOKE.run_progressive()
    lines = capsys.readouterr().out.splitlines()
    records = [json.loads(line) for line in lines if line.startswith("{")]
    assert rc == 1
    assert [record["record"] for record in records].count("progressive_check") == 6
    assert [record["record"] for record in records].count("progressive_finding") == 5
    assert records[-1]["record"] == "progressive_summary"
    assert os.environ["ROOK_MCP_TOOL_PROFILE"] == "readonly"
```

- [ ] **Step 8: Run the Python surface suites and commit**

Run:

```powershell
$env:PYTHONPATH = (Resolve-Path 'mcp_server/src').Path
& 'C:/Users/aryan/source/repos/Rook/mcp_server/.venv/Scripts/python.exe' -m pytest `
  mcp_server/tests/test_lm_surface_smoke.py `
  mcp_server/tests/test_rook_tools_meta.py `
  mcp_server/tests/test_server_tool_profiles.py -q
git add scripts/lm_surface_smoke.py mcp_server/tests/test_lm_surface_smoke.py
git commit -m "feat: add deployed progressive discovery evidence"
```

Expected: all tests pass; no capability-index or server behavior file changes appear in `git status`.

---

### Task 3: Add the owned live exact-name chain and structured artifact evidence

**Files:**
- Modify: `mcp_server/src/rook/local_testing_proof.py:836-1123`
- Test: `mcp_server/tests/test_local_testing_proof.py:640-902`

**Interfaces:**
- Produces: `_call_public_tool(name: str, arguments: dict) -> Any`.
- Produces: `_run_live_progressive_gh_status(args: dict[str, int]) -> dict[str, Any]`.
- Produces: `_live_smoke_envelope(output: str) -> dict[str, Any] | None`.
- `run_live_smoke()` returns `details["progressive_discovery"]`.
- `owned_release_readiness_gate()` promotes the same object to its own `details["progressive_discovery"]`.

- [ ] **Step 1: Write failing exact-chain and profile-restoration tests**

Use real public-wire shapes in the helper test:

```python
async def _async_value(value):
    return value


async def _successful_direct_dispatch(name: str, _args: dict):
    if name == "rhino_ping":
        return {"success": True, "data": {"processId": 42, "port": 9001}}
    if name == "gh_status":
        return {"success": True, "data": {"ready": True}}
    if name == "chirp_create":
        return {"success": True, "data": {"component_guid": "abc", "compilation_errors": []}}
    if name == "gh_errors":
        return {"success": True, "data": {"errors": []}}
    if name == "gh_undo":
        return {"success": True, "data": {"undone": True}}
    raise AssertionError(name)


@pytest.fixture
def passing_live_progressive(monkeypatch):
    async def fake_progressive(_args):
        assert os.environ["ROOK_MCP_TOOL_PROFILE"] == "lean"
        return {
            "profile": "lean", "gateways": [
                "rook_tools_ls", "rook_tools_search", "rook_tools_read", "rook_tools_call"
            ],
            "target": "gh_status", "target_hidden": True,
            "search": [{"name": "gh_status"}],
            "read": {"name": "gh_status", "mcp_dispatchable": True, "input_schema": {"type": "object"}},
            "call": {"ready": True},
        }

    monkeypatch.setattr(proof, "_run_live_progressive_gh_status", fake_progressive)


@pytest.mark.asyncio
async def test_live_progressive_gh_status_uses_public_search_read_call(monkeypatch):
    calls = []
    monkeypatch.setattr(proof, "_list_public_tools", lambda: _async_value([
        SimpleNamespace(name=name) for name in
        ("rook_tools_ls", "rook_tools_search", "rook_tools_read", "rook_tools_call", "rhino_ping")
    ]))

    async def fake_public(name, arguments):
        calls.append((name, arguments))
        if name == "rook_tools_search":
            return [{"name": "gh_status"}]
        if name == "rook_tools_read":
            return {"name": "gh_status", "mcp_dispatchable": True, "input_schema": {"type": "object"}}
        if name == "rook_tools_call":
            return {"ready": True}
        raise AssertionError(name)

    monkeypatch.setattr(proof, "_call_public_tool", fake_public)
    result = await proof._run_live_progressive_gh_status({"port": 9001, "process_id": 42})
    assert [name for name, _ in calls] == ["rook_tools_search", "rook_tools_read", "rook_tools_call"]
    assert calls[-1][1] == {
        "name": "gh_status", "arguments": {"port": 9001, "process_id": 42}
    }
    assert result["target_hidden"] is True
    assert result["call"] == {"ready": True}


@pytest.mark.asyncio
async def test_run_live_smoke_restores_profile_after_progressive_failure(monkeypatch):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "readonly")
    monkeypatch.setattr(proof, "_call_tool_dispatch", _successful_direct_dispatch)

    async def fail_progressive(_args):
        assert os.environ["ROOK_MCP_TOOL_PROFILE"] == "lean"
        raise proof.ProofFailure("progressive_discovery_failed", "missing gh_status")

    monkeypatch.setattr(proof, "_run_live_progressive_gh_status", fail_progressive)
    with pytest.raises(proof.ProofFailure):
        await proof.run_live_smoke(port=9001, process_id=42)
    assert os.environ["ROOK_MCP_TOOL_PROFILE"] == "readonly"


@pytest.mark.asyncio
async def test_run_live_smoke_restores_profile_after_success(monkeypatch, passing_live_progressive):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
    monkeypatch.setattr(proof, "_call_tool_dispatch", _successful_direct_dispatch)
    result = await proof.run_live_smoke(port=9001, process_id=42)
    assert os.environ["ROOK_MCP_TOOL_PROFILE"] == "full"
    assert result["progressive_discovery"]["target"] == "gh_status"


@pytest.mark.asyncio
async def test_run_live_smoke_restores_profile_to_unset_state(monkeypatch, passing_live_progressive):
    monkeypatch.delenv("ROOK_MCP_TOOL_PROFILE", raising=False)
    monkeypatch.setattr(proof, "_call_tool_dispatch", _successful_direct_dispatch)
    result = await proof.run_live_smoke(port=9001, process_id=42)
    assert "ROOK_MCP_TOOL_PROFILE" not in os.environ
    assert result["progressive_discovery"]["profile"] == "lean"
```

Add the `passing_live_progressive` parameter to every existing `test_live_smoke_*` test that reaches or can reach Chirp mutation. Tests that fail during direct readiness do not need it. This keeps existing tests focused on Chirp and readiness behavior while the new tests exercise the real progressive helper.

- [ ] **Step 2: Run the new local-proof tests and verify they fail**

Run:

```powershell
$env:PYTHONPATH = (Resolve-Path 'mcp_server/src').Path
& 'C:/Users/aryan/source/repos/Rook/mcp_server/.venv/Scripts/python.exe' -m pytest `
  mcp_server/tests/test_local_testing_proof.py -k 'live_progressive or restores_profile' -v
```

Expected: FAIL because the public live helper does not exist and `run_live_smoke` does not force lean for the in-flight calls or restore all three inherited states (`readonly`, `full`, and absent).

- [ ] **Step 3: Implement public-wire decoding and the exact live chain**

Add wrappers that import the installed server lazily after the profile is forced:

```python
async def _list_public_tools():
    from .server import list_tools
    return await list_tools()


async def _call_public_tool(name: str, arguments: dict[str, Any]) -> Any:
    from .server import call_tool
    response = await call_tool(name, arguments)
    if not response:
        raise ProofFailure("progressive_discovery_failed", f"{name} returned no content")
    text = str(response[0].text)
    if text.startswith("Error:"):
        raise ProofFailure("progressive_discovery_failed", f"{name} failed", {"tool": name, "wire": text})
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProofFailure(
            "progressive_discovery_failed", f"{name} returned invalid JSON",
            {"tool": name, "wire": text, "error": str(exc)},
        ) from exc
```

Implement `_run_live_progressive_gh_status` with these exact assertions and evidence keys:

```python
async def _run_live_progressive_gh_status(args: dict[str, int]) -> dict[str, Any]:
    tools = await _list_public_tools()
    names = {tool.name for tool in tools}
    gateways = ("rook_tools_ls", "rook_tools_search", "rook_tools_read", "rook_tools_call")
    missing = [name for name in gateways if name not in names]
    if missing or "gh_status" in names:
        raise ProofFailure(
            "progressive_discovery_failed", "lean catalog contract failed",
            {"missing_gateways": missing, "gh_status_directly_advertised": "gh_status" in names},
        )

    search = await _call_public_tool("rook_tools_search", {"query": "gh_status", "limit": 10})
    if not isinstance(search, list) or not any(item.get("name") == "gh_status" for item in search):
        raise ProofFailure("progressive_discovery_failed", "gh_status exact-name search failed", {"search": search})

    read = await _call_public_tool("rook_tools_read", {"name": "gh_status"})
    read_ok = (
        isinstance(read, dict) and read.get("name") == "gh_status"
        and read.get("mcp_dispatchable") is True
        and isinstance(read.get("input_schema"), dict)
        and read["input_schema"].get("type") == "object"
    )
    if not read_ok:
        raise ProofFailure("progressive_discovery_failed", "gh_status read contract failed", {"read": read})

    called = await _call_public_tool(
        "rook_tools_call", {"name": "gh_status", "arguments": dict(args)}
    )
    return {
        "profile": "lean", "gateways": list(gateways), "target": "gh_status",
        "target_hidden": True, "search": search, "read": read, "call": called,
    }
```

- [ ] **Step 4: Scope lean around the entire owned live smoke and preserve call ordering**

In `run_live_smoke`, save the inherited profile, set lean before the first lazy server import, and restore in `finally`. Keep direct `rhino_ping` and `_ensure_grasshopper_ready` first; call `_run_live_progressive_gh_status(args)` immediately afterward and before `chirp_create`. Add the structured result to the returned dictionary:

```python
"progressive_discovery": progressive_discovery,
```

Add this ordering test:

```python
@pytest.mark.asyncio
async def test_run_live_smoke_orders_progressive_chain_before_chirp(monkeypatch):
    events = []

    async def fake_direct(name, args):
        events.append(name)
        return await _successful_direct_dispatch(name, args)

    async def fake_progressive(_args):
        events.extend(["rook_tools_search", "rook_tools_read", "rook_tools_call"])
        return {"target": "gh_status", "target_hidden": True}

    monkeypatch.setattr(proof, "_call_tool_dispatch", fake_direct)
    monkeypatch.setattr(proof, "_run_live_progressive_gh_status", fake_progressive)
    await proof.run_live_smoke(port=9001, process_id=42)
    assert events.index("rhino_ping") < events.index("gh_status")
    assert events.index("gh_status") < events.index("rook_tools_search")
    assert events.index("rook_tools_search") < events.index("rook_tools_read")
    assert events.index("rook_tools_read") < events.index("rook_tools_call")
    assert events.index("rook_tools_call") < events.index("chirp_create")
```

- [ ] **Step 5: Write failing owned-artifact promotion tests**

Update the successful fake harness to include a smoke stdout envelope:

```python
live_envelope = {
    "gate": "live_smoke", "success": True, "failure_label": None,
    "details": {"progressive_discovery": {"target": "gh_status", "target_hidden": True}},
}
```

Assert:

```python
assert result.details["progressive_discovery"] == live_envelope["details"]["progressive_discovery"]
```

Add a second test where the harness reports success but stdout contains no progressive evidence; assert the owned gate fails with `progressive_discovery_failed`.

- [ ] **Step 6: Implement robust envelope parsing and promotion**

```python
def _live_smoke_envelope(output: str) -> dict[str, Any] | None:
    for line in reversed(output.splitlines()):
        try:
            payload = json.loads(line.strip())
        except (json.JSONDecodeError, AttributeError):
            continue
        if isinstance(payload, dict) and payload.get("gate") == "live_smoke":
            return payload
    return None
```

After `details = harness.to_manifest_dict()`, parse `harness.smoke.stdout`, promote `envelope["details"]["progressive_discovery"]`, and fail a successful harness with `progressive_discovery_failed` if the object is absent. Preserve existing live failure labels when the harness itself is non-green.

- [ ] **Step 7: Run the local-proof suite and commit**

Run:

```powershell
$env:PYTHONPATH = (Resolve-Path 'mcp_server/src').Path
& 'C:/Users/aryan/source/repos/Rook/mcp_server/.venv/Scripts/python.exe' -m pytest `
  mcp_server/tests/test_local_testing_proof.py -q
git add mcp_server/src/rook/local_testing_proof.py mcp_server/tests/test_local_testing_proof.py
git commit -m "feat: prove progressive discovery in owned live smoke"
```

Expected: all local-proof tests pass, including existing Chirp/readiness failures and new profile/artifact assertions.

---

### Task 4: Extend developer `-LiveSmoke` with the same exact-name chain

**Files:**
- Modify: `scripts/deploy-local-testing.ps1:1109-1201`
- Test: `scripts/tests/deploy-local-testing-guards.tests.ps1:261-280,351-365`

**Interfaces:**
- Consumes: existing runtime contract and selected Python interpreter.
- Produces: one live-smoke JSON object containing `progressive_discovery` plus existing direct and Chirp evidence.

- [ ] **Step 1: Write failing PowerShell guards for lean scoping and ordering**

Extend `Test-DeployScriptLiveSmokeIsExplicit` with exact assertions:

```powershell
Assert-Contains -Text $content -Expected "'ROOK_MCP_TOOL_PROFILE'" -Message 'Live smoke must save and restore the MCP profile.'
Assert-Contains -Text $content -Expected "[Environment]::SetEnvironmentVariable('ROOK_MCP_TOOL_PROFILE', 'lean', 'Process')" -Message 'Live smoke must force lean.'
foreach ($gateway in @('rook_tools_ls', 'rook_tools_search', 'rook_tools_read', 'rook_tools_call')) {
    Assert-Contains -Text $content -Expected $gateway -Message "Live smoke must require gateway $gateway."
}
$directStatus = $content.IndexOf('status = await _call_tool_dispatch("gh_status", {})')
$progressiveSearch = $content.IndexOf('await public_call("rook_tools_search"')
$chirpCreate = $content.IndexOf('chirp = await _call_tool_dispatch("chirp_create"')
Assert-True -Condition ($directStatus -ge 0 -and $directStatus -lt $progressiveSearch -and $progressiveSearch -lt $chirpCreate) -Message 'Direct controls must precede the progressive chain, which must precede Chirp mutation.'
$undoFailure = $content.IndexOf('raise SystemExit(f"gh_undo cleanup failed: {undo}")')
$evidenceStart = $content.IndexOf('live_evidence = {')
$finalPrint = $content.IndexOf('print(json.dumps(live_evidence, default=str, sort_keys=True))')
Assert-True -Condition ($undoFailure -ge 0 -and $undoFailure -lt $evidenceStart -and $evidenceStart -lt $finalPrint) -Message 'Final evidence must be built and printed only after successful undo validation.'
$evidenceBlock = $content.Substring($evidenceStart, $finalPrint - $evidenceStart)
foreach ($field in @('"rhino_ping"', '"gh_status"', '"progressive_discovery"', '"chirp_create"', '"gh_errors"', '"gh_undo"')) {
    Assert-Contains -Text $evidenceBlock -Expected $field -Message "Final live evidence must include $field."
}
Assert-NotContains -Text $content -Unexpected 'print(json.dumps({"rhino_ping": ping, "gh_status": status, "chirp_create": chirp}, default=str))' -Message 'The pre-validation partial evidence print must be removed.'
```

- [ ] **Step 2: Run the deploy guards and verify failure**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/tests/deploy-local-testing-guards.tests.ps1
```

Expected: FAIL on the new progressive/lean assertions.

- [ ] **Step 3: Extend the embedded Python smoke**

Import `call_tool` and `list_tools` alongside `_call_tool_dispatch`, and add this decoder:

```python
async def public_call(name, arguments):
    response = await call_tool(name, arguments)
    if not response:
        raise SystemExit(f"{name} returned no content")
    text = str(response[0].text)
    if text.startswith("Error:"):
        raise SystemExit(f"{name} failed: {text}")
    return json.loads(text)
```

After the direct `gh_status` succeeds and before `chirp_create`:

```python
tools = await list_tools()
names = {tool.name for tool in tools}
gateways = {"rook_tools_ls", "rook_tools_search", "rook_tools_read", "rook_tools_call"}
if not gateways <= names or "gh_status" in names:
    raise SystemExit(f"lean progressive catalog failed: names={sorted(names)}")
search = await public_call("rook_tools_search", {"query": "gh_status", "limit": 10})
if not any(item.get("name") == "gh_status" for item in search):
    raise SystemExit(f"gh_status exact-name search failed: {search}")
read = await public_call("rook_tools_read", {"name": "gh_status"})
if not (read.get("name") == "gh_status" and read.get("mcp_dispatchable") is True
        and isinstance(read.get("input_schema"), dict)
        and read["input_schema"].get("type") == "object"):
    raise SystemExit(f"gh_status read contract failed: {read}")
called = await public_call("rook_tools_call", {"name": "gh_status", "arguments": {}})
progressive_discovery = {
    "profile": "lean", "gateways": sorted(gateways), "target": "gh_status",
    "target_hidden": True, "search": search, "read": read, "call": called,
}
```

Remove the existing partial `print(json.dumps(...))` immediately after `chirp_create`. After `gh_undo` has returned success, build and print the complete evidence object exactly once:

```python
live_evidence = {
    "rhino_ping": ping,
    "gh_status": status,
    "progressive_discovery": progressive_discovery,
    "chirp_create": chirp,
    "gh_errors": errors,
    "gh_undo": undo,
}
print(json.dumps(live_evidence, default=str, sort_keys=True))
```

No success-shaped JSON is emitted before Chirp validation, error inspection, and undo cleanup complete. A failure before that point exits nonzero with its existing diagnostic instead of leaving a misleading partial evidence object.

- [ ] **Step 4: Force and restore lean in the PowerShell parent**

Add `ROOK_MCP_TOOL_PROFILE` to `$environmentNames`. After applying the runtime contract environment and before launching Python, call:

```powershell
[Environment]::SetEnvironmentVariable('ROOK_MCP_TOOL_PROFILE', 'lean', 'Process')
```

The existing `$previousEnvironment` loop restores the inherited value in `finally`, including removal when it was originally absent.

- [ ] **Step 5: Run guards and commit**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/tests/deploy-local-testing-guards.tests.ps1
git add scripts/deploy-local-testing.ps1 scripts/tests/deploy-local-testing-guards.tests.ps1
git commit -m "feat: extend local live smoke with progressive discovery"
```

Expected: deploy guard suite passes.

---

### Task 5: Add the standalone progressive gate last in release readiness

**Files:**
- Modify: `scripts/validate-local-testing-stack.ps1:1-324`
- Test: `scripts/tests/local-testing-stack-guards.tests.ps1:25-66`

**Interfaces:**
- Consumes: installed `$VenvPython` and repository `scripts/lm_surface_smoke.py`.
- Produces: `progressive_discovery.json`, stdout/stderr logs, and a top-level manifest ending in `progressive_discovery_failed` under the current baseline.

- [ ] **Step 1: Write failing stable-contract and ordering guards**

Add assertions to `Test-ValidateLocalTestingStackScriptContract`:

```powershell
Assert-Contains -Text $content -Expected "Gate 'progressive_discovery'" -Message 'Release readiness must record the progressive gate.'
Assert-Contains -Text $content -Expected "FailureLabel 'progressive_discovery_failed'" -Message 'Progressive failure label must be stable.'
Assert-Contains -Text $content -Expected "'lm_surface_smoke.py'" -Message 'Release readiness must invoke the standalone smoke script.'
Assert-Contains -Text $content -Expected "'progressive'" -Message 'Release readiness must select progressive mode.'
Assert-Contains -Text $content -Expected "-ScopedEnvironment @{ PYTHONPATH = '' }" -Message 'The deployed gate must explicitly clear PYTHONPATH.'
$owned = $content.IndexOf("Invoke-ProofModuleGate -ArtifactDir `$artifactDir -Gate 'owned_release_readiness'")
$progressive = $content.IndexOf('Invoke-ProgressiveDiscoveryGate -ArtifactDir $artifactDir')
$successManifest = $content.IndexOf('Write-TopLevelManifest -ArtifactDir $artifactDir -Success $true')
Assert-True -Condition ($owned -ge 0 -and $owned -lt $progressive -and $progressive -lt $successManifest) -Message 'Progressive discovery must be the final release gate.'
```

- [ ] **Step 2: Run the stack guards and verify failure**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/tests/local-testing-stack-guards.tests.ps1
```

Expected: FAIL because the stable final gate is absent.

- [ ] **Step 3: Add scoped environment support to `Invoke-GateCommand`**

Add an optional parameter:

```powershell
[hashtable]$ScopedEnvironment = @{}
```

Before executing commands, save each named process variable and apply the scoped value. Restore all saved values in `finally`. Include a copy under `details.scoped_env` for both success and failure envelopes so the artifact affirmatively records `PYTHONPATH = ''`:

```powershell
$previousEnvironment = @{}
foreach ($name in $ScopedEnvironment.Keys) {
    $previousEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
}
try {
    foreach ($name in $ScopedEnvironment.Keys) {
        [Environment]::SetEnvironmentVariable($name, [string]$ScopedEnvironment[$name], 'Process')
    }
    foreach ($command in $Commands) {
        Invoke-ExternalChecked -Command (ConvertTo-CommandParts -Command $command) -StdoutPath $stdout -StderrPath $stderr
    }
    $success = $true
    $label = $null
    $details = @{ scoped_env = $ScopedEnvironment.Clone() }
} catch {
    $success = $false
    $label = $FailureLabel
    $details = @{ error = $_.Exception.Message; scoped_env = $ScopedEnvironment.Clone() }
} finally {
    foreach ($name in $previousEnvironment.Keys) {
        [Environment]::SetEnvironmentVariable($name, $previousEnvironment[$name], 'Process')
    }
}
```

- [ ] **Step 4: Add and invoke the final progressive gate**

Define `$ProgressiveSmoke = Join-Path $RepoRoot 'scripts\lm_surface_smoke.py'` and add:

```powershell
function Invoke-ProgressiveDiscoveryGate {
    param([Parameter(Mandatory = $true)][string]$ArtifactDir)

    Invoke-GateCommand `
        -Gate 'progressive_discovery' `
        -FailureLabel 'progressive_discovery_failed' `
        -ArtifactDir $ArtifactDir `
        -ScopedEnvironment @{ PYTHONPATH = '' } `
        -Commands @(,@($VenvPython, $ProgressiveSmoke, 'progressive'))
}
```

Call it immediately after the successful `owned_release_readiness` gate and immediately before the success manifest. The existing outer catch must therefore write a failed top-level manifest with `progressive_discovery_failed` when the expected-red smoke returns 1.

- [ ] **Step 5: Run both guard suites and commit**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/tests/deploy-local-testing-guards.tests.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/tests/local-testing-stack-guards.tests.ps1
git add scripts/validate-local-testing-stack.ps1 scripts/tests/local-testing-stack-guards.tests.ps1
git commit -m "feat: gate release readiness on progressive discovery"
```

Expected: both PowerShell guard suites pass.

---

### Task 6: Run complete acceptance and collect expected-red deployed evidence

**Files:**
- Verify only; no source changes expected.

**Interfaces:**
- Consumes: Tasks 1-5 and a running Rhino/Grasshopper instance for developer live smoke.
- Produces: unit/guard pass evidence, deployed progressive summary, live exact-name pass evidence, and release-readiness expected-red artifact.

- [ ] **Step 1: Run all targeted Python suites from the isolated worktree**

```powershell
$env:PYTHONPATH = (Resolve-Path 'mcp_server/src').Path
$TestPython = 'C:/Users/aryan/source/repos/Rook/mcp_server/.venv/Scripts/python.exe'
& $TestPython -m pytest `
  mcp_server/tests/test_lm_surface_smoke.py `
  mcp_server/tests/test_local_testing_proof.py `
  mcp_server/tests/test_rook_tools_meta.py `
  mcp_server/tests/test_server_tool_profiles.py -q
```

Expected: all tests pass. Record the exact count.

- [ ] **Step 2: Run both PowerShell guard suites**

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/tests/deploy-local-testing-guards.tests.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/tests/local-testing-stack-guards.tests.ps1
```

Expected: both print their pass messages and exit 0.

- [ ] **Step 3: Deploy the worktree payload without requiring a rebuild**

With the user's Rhino and Grasshopper instance still open:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/deploy-local-testing.ps1 -PayloadOnly -AllowRunning
```

Expected: deployment and installed-runtime verification pass. This is the ordinary deployment acceptance path and must not run realistic-query certification.

- [ ] **Step 4: Run the standalone installed-runtime progressive smoke and inspect every record**

```powershell
$env:PYTHONPATH = ''
$InstalledPython = Join-Path $env:LOCALAPPDATA 'Rook/venv/Scripts/python.exe'
& $InstalledPython scripts/lm_surface_smoke.py progressive
$ProgressiveExit = $LASTEXITCODE
```

Expected:

- `$ProgressiveExit -eq 1`.
- Six `progressive_check` records appear in `PROGRESSIVE_CHECK_ORDER`.
- `gateway_presence`, `lean_hiddenness`, `exact_name_resolution`, `schema_reads`, and `agent_status_call` are `PASS`.
- `intent_discovery` is `FAIL` with one passing row and five failing rows.
- Exactly five `intent_discovery_rank_failed` findings appear.
- The final line is `progressive_summary` with `{"intent_discovery_rank_failed": 5}` in its histogram.
- Every printed origin is under `%LOCALAPPDATA%/Rook/venv/Lib/site-packages`.

- [ ] **Step 5: Run installed developer live smoke**

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/deploy-local-testing.ps1 `
  -PayloadOnly -AllowRunning -LiveSmoke
```

Expected: exit 0. The emitted object contains direct `rhino_ping`, direct `gh_status`, structured `progressive_discovery` for hidden `gh_status`, successful Chirp creation/error inspection, and successful undo cleanup.

- [ ] **Step 6: Run release readiness after the user closes the currently open Rhino instance**

Do not terminate a user-owned Rhino process. Confirm `Get-Process Rhino -ErrorAction SilentlyContinue` returns nothing, then run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/validate-local-testing-stack.ps1 -ReleaseReadiness
$ReleaseExit = $LASTEXITCODE
$LatestArtifact = Get-ChildItem artifacts/local-testing -Directory | Sort-Object LastWriteTime -Descending | Select-Object -First 1
$Manifest = Get-Content (Join-Path $LatestArtifact.FullName 'manifest.json') -Raw | ConvertFrom-Json

if ($ReleaseExit -eq 0) {
    throw 'Release readiness unexpectedly passed the expected-red progressive gate.'
}
if ($Manifest.failure_label -ne 'progressive_discovery_failed') {
    throw "Wrong top-level failure label: $($Manifest.failure_label)"
}
if ($Manifest.gates[-1].gate -ne 'progressive_discovery') {
    throw "Progressive discovery was not last: $($Manifest.gates[-1].gate)"
}

$OwnedPath = Join-Path $LatestArtifact.FullName 'owned-release-readiness.json'
if (-not (Test-Path -LiteralPath $OwnedPath)) {
    throw "Missing owned artifact: $OwnedPath"
}
$Owned = Get-Content -LiteralPath $OwnedPath -Raw | ConvertFrom-Json
$OwnedEvidence = $Owned.details.progressive_discovery
if ($null -eq $OwnedEvidence) {
    throw 'Owned artifact did not promote structured progressive_discovery evidence.'
}
if ($OwnedEvidence.target -ne 'gh_status' -or $OwnedEvidence.target_hidden -ne $true) {
    throw "Invalid owned target evidence: $($OwnedEvidence | ConvertTo-Json -Depth 8 -Compress)"
}

$ProgressivePath = Join-Path $LatestArtifact.FullName 'progressive_discovery.json'
if (-not (Test-Path -LiteralPath $ProgressivePath)) {
    throw "Missing progressive gate artifact: $ProgressivePath"
}
$ProgressiveGate = Get-Content -LiteralPath $ProgressivePath -Raw | ConvertFrom-Json
if ($ProgressiveGate.success -ne $false -or $ProgressiveGate.failure_label -ne 'progressive_discovery_failed') {
    throw "Unexpected progressive gate envelope: $($ProgressiveGate | ConvertTo-Json -Depth 8 -Compress)"
}
if (-not (Test-Path -LiteralPath $ProgressiveGate.stdout_path)) {
    throw "Progressive stdout artifact missing: $($ProgressiveGate.stdout_path)"
}

$Records = @()
foreach ($line in Get-Content -LiteralPath $ProgressiveGate.stdout_path) {
    if (-not $line.TrimStart().StartsWith('{')) {
        continue
    }
    try {
        $record = $line | ConvertFrom-Json
    } catch {
        throw "Invalid JSONL record in progressive stdout: $line"
    }
    if ($record.record) {
        $Records += $record
    }
}

$Checks = @($Records | Where-Object { $_.record -eq 'progressive_check' })
$Findings = @($Records | Where-Object { $_.record -eq 'progressive_finding' })
$Summaries = @($Records | Where-Object { $_.record -eq 'progressive_summary' })
$ExpectedOrder = @(
    'gateway_presence', 'lean_hiddenness', 'exact_name_resolution',
    'schema_reads', 'agent_status_call', 'intent_discovery'
)
if ($Checks.Count -ne 6 -or (($Checks.check -join ',') -ne ($ExpectedOrder -join ','))) {
    throw "Wrong progressive check order: $($Checks.check -join ',')"
}

$ExpectedStatuses = [ordered]@{
    gateway_presence = 'PASS'
    lean_hiddenness = 'PASS'
    exact_name_resolution = 'PASS'
    schema_reads = 'PASS'
    agent_status_call = 'PASS'
    intent_discovery = 'FAIL'
}
foreach ($name in $ExpectedStatuses.Keys) {
    $check = @($Checks | Where-Object { $_.check -eq $name })[0]
    if ($null -eq $check -or $check.status -ne $ExpectedStatuses[$name]) {
        throw "Wrong status for $name: $($check.status)"
    }
}
$IntentCheck = @($Checks | Where-Object { $_.check -eq 'intent_discovery' })[0]
if ($IntentCheck.observed -ne 1 -or $IntentCheck.expected -ne 6) {
    throw "Wrong intent counts: $($IntentCheck.observed)/$($IntentCheck.expected)"
}
$BlockedChecks = @($Checks | Where-Object { $_.status -eq 'BLOCKED' })
if ($BlockedChecks.Count -ne 0) {
    throw "Expected-red baseline contains unexpected BLOCKED checks: $($BlockedChecks.check -join ',')"
}

$RankFindings = @($Findings | Where-Object { $_.code -eq 'intent_discovery_rank_failed' })
if ($Findings.Count -ne 5 -or $RankFindings.Count -ne 5) {
    throw "Wrong ranking findings: total=$($Findings.Count), rank=$($RankFindings.Count)"
}
if ($Summaries.Count -ne 1 -or $Records[-1].record -ne 'progressive_summary') {
    throw 'Progressive summary was not the single final JSONL record.'
}
$Summary = $Summaries[0]
if ($Summary.status -ne 'FAIL' -or $Summary.finding_histogram.intent_discovery_rank_failed -ne 5) {
    throw "Wrong progressive summary: $($Summary | ConvertTo-Json -Depth 8 -Compress)"
}

$env:PYTHONPATH = (Resolve-Path 'mcp_server/src').Path
$TestPython = 'C:/Users/aryan/source/repos/Rook/mcp_server/.venv/Scripts/python.exe'
& $TestPython -m pytest `
  mcp_server/tests/test_lm_surface_smoke.py::test_missing_search_gateway_blocks_only_search_dependent_checks `
  mcp_server/tests/test_lm_surface_smoke.py::test_progressive_summary_turns_missing_checks_into_blocked_records -q
if ($LASTEXITCODE -ne 0) {
    throw 'Executable BLOCKED-propagation acceptance tests failed.'
}
```

Expected: every assertion completes without throwing. The deployed artifact proves the healthy expected-red path has five non-intent checks passing, no unexpected `BLOCKED` records, five ranking findings, and a final failing summary. The two named synthetic tests prove missing prerequisites propagate `BLOCKED` deterministically rather than disappearing from the record set.

- [ ] **Step 7: Verify repository hygiene and final diff**

```powershell
git diff --check
git status --short --branch
git diff codex/deployed-progressive-smoke...HEAD -- `
  scripts/lm_surface_smoke.py `
  mcp_server/tests/test_lm_surface_smoke.py `
  mcp_server/src/rook/local_testing_proof.py `
  mcp_server/tests/test_local_testing_proof.py `
  scripts/deploy-local-testing.ps1 `
  scripts/tests/deploy-local-testing-guards.tests.ps1 `
  scripts/validate-local-testing-stack.ps1 `
  scripts/tests/local-testing-stack-guards.tests.ps1
```

Expected: no whitespace errors; only approved validation/test files and this plan/spec lineage are changed; the worktree branch is clean after the task commits.

## Plan Self-Review Results

- Spec coverage: every pinned gateway/target/query/origin/read/call contract maps to Tasks 1-3; both live paths map to Tasks 3-4; release ordering and failure label map to Task 5; expected-red and future-live acceptance map to Task 6.
- Requested plan coverage: record ordering, `BLOCKED` propagation, histogram accuracy, and summary emission on nonzero exit all have named unit tests in Tasks 1-2.
- Live evidence integrity: Task 3 asserts lean during owned success and failure calls and restores full, readonly, and absent inherited states; Task 4 emits its only success JSON after undo and statically pins all six evidence fields.
- Acceptance evidence: Task 6 loads structured owned evidence, follows the progressive gate's `stdout_path`, parses JSONL, executes every expected-red assertion, and reruns both named `BLOCKED`-propagation tests.
- Type consistency: all evidence helpers return JSON-serializable dictionaries; public MCP calls decode success data rather than internal `{success, data}` envelopes; live owned evidence uses `progressive_discovery` consistently from runner to artifact.
- Scope control: no search, schema, profile membership, dispatch, targeting, native, or managed behavior change is included.
