# LM2G — external_mcp Catalog-vs-Wire-Dispatch Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a standalone, read-only audit that reconciles the advertised public MCP catalog against the wire-dispatch handler names statically extracted from `server._call_tool_dispatch`, surfacing any advertised tool with no wire handler.

**Architecture:** A new stdlib-only module `rook.agent.external_mcp` holds three frozen dataclasses, a pure AST extractor, a no-execution source collector, a pure reconciler, and a report formatter. A new `external` subcommand in the live-smoke script wires it against the deployed runtime behind the existing origin guard. Nothing touches `ProfileDefinition`, `CapabilityRecord`, the LM2A–F modules, or `_call_tool_dispatch` itself.

**Tech Stack:** Python 3.12, stdlib only (`ast`, `dataclasses`, `importlib.util`, `os`), pytest.

## Global Constraints

- **Read-only / diagnostic.** No `ToolRegistry`, no `ToolDispatcher`, no tool execution, no schema/visibility/wire mutation. No `import rook.server` in the new module — read its source via `find_spec(...).origin` only.
- **`external_mcp.py` is stdlib-only** plus the `Severity` literal from `rook.agent.capability_record`. It imports nothing from `execution_profile`, `profile_reconciliation`, or any `tool_*` module.
- **No new axis on existing types.** Do not add `mcp_dispatchable` (or anything) to `CapabilityRecord`; do not extend `ProfileDefinition`.
- **No allowlist.** No maintained "expected unadvertised handlers" set.
- **Severities are single-sourced** through `_SEVERITY_BY_CODE`; every finding is built via the `_finding` helper so code and table cannot drift.
- **`handler_not_advertised` is non-defect info**, documented as "a wire handler exists outside the public advertised MCP surface (may be intentional)."
- **Watchpoint 1:** `collect_wire_dispatch_evidence` must treat `spec is None`, a missing/`None` `origin`, or a non-file `origin` as a `wire_source_unresolved` error — no `Path(None)`, no traceback.
- **Watchpoint 2:** the smoke `external` failure decision is computed from structured `ExternalMcpResolution.findings` codes/severities, never from string-matching report output.
- **Test commands run from the repo root** (`C:\UDEV\Rook`) using the repo venv: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider ...`.

## File Structure

- `mcp_server/src/rook/agent/external_mcp.py` (new) — types, severity table, `_finding`, extractor, collector, reconciler, formatter. One file: all five units share the types and the severity table and have one responsibility (the external_mcp audit).
- `mcp_server/tests/test_external_mcp.py` (new) — extractor / collector / reconciler unit tests.
- `scripts/lm_surface_smoke.py` (modify) — add `external_exit_decision`, `run_external`, register `external` in `build_parser`/`main`. No change to `run_coherence`/`run_surface`.
- `mcp_server/tests/test_lm_surface_smoke.py` (modify) — `external` parser + pure-gate + origin-guard-ordering tests.

---

### Task 1: Types, severity table, and the pure AST extractor

**Files:**
- Create: `mcp_server/src/rook/agent/external_mcp.py`
- Test: `mcp_server/tests/test_external_mcp.py`

**Interfaces:**
- Consumes: `rook.agent.capability_record.Severity` (`Literal["info","warning","error"]`).
- Produces:
  - `ExternalMcpFinding(code: str, tool: str, severity: Severity, message: str)` (frozen)
  - `WireDispatchEvidence(names: tuple[str, ...], findings: tuple[ExternalMcpFinding, ...])` (frozen)
  - `ExternalMcpResolution(advertised_names, wire_dispatch_names, findings)` (frozen) — defined now, populated in Task 3
  - `_SEVERITY_BY_CODE: dict[str, Severity]` and `_finding(code, tool, message) -> ExternalMcpFinding`
  - `extract_wire_dispatch_evidence_from_source(source: str) -> WireDispatchEvidence`

- [ ] **Step 1: Write the failing tests**

Create `mcp_server/tests/test_external_mcp.py`:

```python
from __future__ import annotations

from rook.agent.external_mcp import (
    ExternalMcpFinding,
    WireDispatchEvidence,
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_external_mcp.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'rook.agent.external_mcp'`.

- [ ] **Step 3: Write the module (types + severity table + extractor)**

Create `mcp_server/src/rook/agent/external_mcp.py`:

```python
"""LM2G external_mcp public-wire-surface audit (read-only).

Reconciles the advertised public MCP catalog (server.list_tools names) against
the wire-dispatch handler names extracted by static AST parsing of
server._call_tool_dispatch. Standalone diagnostic report -- NOT an execution
profile. Never imports/executes rook.server, instantiates no ToolRegistry,
calls no tool, and mutates no schema/visibility/wire behavior.

Stdlib-only: ast, dataclasses, importlib.util, os (+ the Severity literal).
"""

from __future__ import annotations

import ast
import importlib.util
import os
from collections.abc import Iterable
from dataclasses import dataclass

from rook.agent.capability_record import Severity

_DISPATCH_FUNCTION = "_call_tool_dispatch"

_SEVERITY_BY_CODE: dict[str, Severity] = {
    "advertised_not_dispatchable": "error",
    "handler_not_advertised": "info",
    "empty_catalog": "error",
    "dispatch_function_missing": "error",
    "wire_source_unresolved": "error",
    "multiple_dispatch_matches": "warning",
    "unextractable_case": "warning",
}


@dataclass(frozen=True)
class ExternalMcpFinding:
    code: str
    tool: str
    severity: Severity
    message: str


@dataclass(frozen=True)
class WireDispatchEvidence:
    names: tuple[str, ...]
    findings: tuple[ExternalMcpFinding, ...]


@dataclass(frozen=True)
class ExternalMcpResolution:
    advertised_names: tuple[str, ...]
    wire_dispatch_names: tuple[str, ...]
    findings: tuple[ExternalMcpFinding, ...]


def _finding(code: str, tool: str, message: str) -> ExternalMcpFinding:
    return ExternalMcpFinding(
        code=code, tool=tool, severity=_SEVERITY_BY_CODE[code], message=message
    )


def _sorted_findings(
    findings: Iterable[ExternalMcpFinding],
) -> tuple[ExternalMcpFinding, ...]:
    return tuple(sorted(findings, key=lambda f: (f.code, f.tool, f.severity)))


def _subject_is_name(subject: ast.expr) -> bool:
    return isinstance(subject, ast.Name) and subject.id == "name"


def _string_value(pat: ast.pattern) -> str | None:
    if (
        isinstance(pat, ast.MatchValue)
        and isinstance(pat.value, ast.Constant)
        and isinstance(pat.value.value, str)
    ):
        return pat.value.value
    return None


def _is_wildcard(pat: ast.pattern) -> bool:
    return isinstance(pat, ast.MatchAs) and pat.pattern is None and pat.name is None


def _unextractable(node: ast.AST, reason: str) -> ExternalMcpFinding:
    line = getattr(node, "lineno", -1)
    return _finding(
        "unextractable_case",
        f"line {line}",
        f"Unextractable case ({reason}) at line {line}; skipped.",
    )


def _harvest_case(
    case: ast.match_case,
    names: set[str],
    findings: list[ExternalMcpFinding],
) -> None:
    pat = case.pattern
    if case.guard is not None:
        findings.append(_unextractable(pat, "guarded case"))
        return
    value = _string_value(pat)
    if value is not None:
        names.add(value)
        return
    if isinstance(pat, ast.MatchOr):
        for sub in pat.patterns:
            sub_value = _string_value(sub)
            if sub_value is not None:
                names.add(sub_value)
            else:
                findings.append(_unextractable(sub, "non-string OR sub-pattern"))
        return
    if _is_wildcard(pat):
        return
    findings.append(_unextractable(pat, "non-constant case pattern"))


def extract_wire_dispatch_evidence_from_source(source: str) -> WireDispatchEvidence:
    """Pure AST extraction of wire-handler names from a source string.

    Locates the function named _call_tool_dispatch and harvests string case
    labels from its `match name:` statement(s). No execution, no imports.
    """
    tree = ast.parse(source)
    func: ast.AST | None = None
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == _DISPATCH_FUNCTION
        ):
            func = node
            break
    if func is None:
        return WireDispatchEvidence(
            names=(),
            findings=(
                _finding(
                    "dispatch_function_missing",
                    _DISPATCH_FUNCTION,
                    f"Function '{_DISPATCH_FUNCTION}' not found in source; "
                    f"cannot extract wire handlers.",
                ),
            ),
        )

    name_matches = [
        m
        for m in ast.walk(func)
        if isinstance(m, ast.Match) and _subject_is_name(m.subject)
    ]
    findings: list[ExternalMcpFinding] = []
    if len(name_matches) > 1:
        findings.append(
            _finding(
                "multiple_dispatch_matches",
                _DISPATCH_FUNCTION,
                f"{len(name_matches)} 'match name:' statements in "
                f"'{_DISPATCH_FUNCTION}'; expected exactly one.",
            )
        )

    names: set[str] = set()
    for match in name_matches:
        for case in match.cases:
            _harvest_case(case, names, findings)

    return WireDispatchEvidence(
        names=tuple(sorted(names)),
        findings=_sorted_findings(findings),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_external_mcp.py -v`
Expected: PASS (all Task-1 tests).

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/agent/external_mcp.py mcp_server/tests/test_external_mcp.py
git commit -m "feat(lm2g): external_mcp types and AST wire-handler extractor"
```

---

### Task 2: No-execution source collector

**Files:**
- Modify: `mcp_server/src/rook/agent/external_mcp.py`
- Test: `mcp_server/tests/test_external_mcp.py`

**Interfaces:**
- Consumes: `extract_wire_dispatch_evidence_from_source`, `_finding` (Task 1).
- Produces: `collect_wire_dispatch_evidence(module_name: str = "rook.server") -> WireDispatchEvidence`.

- [ ] **Step 1: Write the failing tests**

Append to `mcp_server/tests/test_external_mcp.py`:

```python
from rook.agent.external_mcp import collect_wire_dispatch_evidence


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_external_mcp.py -k collect -v`
Expected: FAIL with `ImportError: cannot import name 'collect_wire_dispatch_evidence'`.

- [ ] **Step 3: Implement the collector**

Append to `mcp_server/src/rook/agent/external_mcp.py`:

```python
def collect_wire_dispatch_evidence(
    module_name: str = "rook.server",
) -> WireDispatchEvidence:
    """Resolve a module's source via find_spec(...).origin and extract evidence.

    Reads the source FILE; never imports/executes the module. Provenance is
    caller-context-dependent: with the worktree importable, find_spec resolves
    the worktree source; under the deployed smoke (empty PYTHONPATH) it resolves
    deployed site-packages.

    A missing spec, a None/missing origin, or a non-file origin yields a
    structured wire_source_unresolved error -- never a raw traceback.
    """
    spec = None
    try:
        spec = importlib.util.find_spec(module_name)
    except (ImportError, AttributeError, ValueError):
        spec = None

    origin = getattr(spec, "origin", None) if spec is not None else None
    if not origin or not os.path.isfile(origin):
        return WireDispatchEvidence(
            names=(),
            findings=(
                _finding(
                    "wire_source_unresolved",
                    module_name,
                    f"Could not resolve a readable source file for module "
                    f"'{module_name}' (origin={origin!r}).",
                ),
            ),
        )

    try:
        with open(origin, encoding="utf-8") as handle:
            source = handle.read()
    except OSError as exc:
        return WireDispatchEvidence(
            names=(),
            findings=(
                _finding(
                    "wire_source_unresolved",
                    module_name,
                    f"Could not read source for module '{module_name}' at "
                    f"{origin!r}: {exc!r}.",
                ),
            ),
        )

    return extract_wire_dispatch_evidence_from_source(source)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_external_mcp.py -v`
Expected: PASS (Task 1 + Task 2).

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/agent/external_mcp.py mcp_server/tests/test_external_mcp.py
git commit -m "feat(lm2g): no-execution wire-source collector via find_spec origin"
```

---

### Task 3: Reconciler, severity pin, and report formatter

**Files:**
- Modify: `mcp_server/src/rook/agent/external_mcp.py`
- Test: `mcp_server/tests/test_external_mcp.py`

**Interfaces:**
- Consumes: `WireDispatchEvidence`, `ExternalMcpResolution`, `_finding`, `_sorted_findings`, `_SEVERITY_BY_CODE` (Tasks 1–2).
- Produces:
  - `reconcile_external_mcp(advertised_names: Iterable[str], wire_evidence: WireDispatchEvidence) -> ExternalMcpResolution`
  - `format_external_mcp_report(resolution: ExternalMcpResolution) -> str`

- [ ] **Step 1: Write the failing tests**

Append to `mcp_server/tests/test_external_mcp.py`:

```python
from rook.agent.external_mcp import (
    ExternalMcpResolution,
    _SEVERITY_BY_CODE,
    format_external_mcp_report,
    reconcile_external_mcp,
)


def _ev(names=(), findings=()):
    return WireDispatchEvidence(names=tuple(names), findings=tuple(findings))


def _by_code(res: ExternalMcpResolution):
    out = {}
    for f in res.findings:
        out.setdefault(f.code, []).append(f.tool)
    return out


def test_advertised_without_handler_is_error():
    res = reconcile_external_mcp(("a", "b"), _ev(names=("a",)))
    by = _by_code(res)
    assert by.get("advertised_not_dispatchable") == ["b"]
    assert "advertised_not_dispatchable" not in {
        f.code for f in res.findings if f.tool == "a"
    }
    err = next(f for f in res.findings if f.code == "advertised_not_dispatchable")
    assert err.severity == "error"


def test_handler_without_advertisement_is_info():
    res = reconcile_external_mcp(("a",), _ev(names=("a", "z")))
    by = _by_code(res)
    assert by.get("handler_not_advertised") == ["z"]
    assert "advertised_not_dispatchable" not in by
    info = next(f for f in res.findings if f.code == "handler_not_advertised")
    assert info.severity == "info"


def test_empty_catalog_is_error():
    res = reconcile_external_mcp((), _ev(names=("a",)))
    by = _by_code(res)
    assert "empty_catalog" in by
    err = next(f for f in res.findings if f.code == "empty_catalog")
    assert err.severity == "error"


def test_clean_overlap_has_no_error_or_info():
    res = reconcile_external_mcp(("a", "b"), _ev(names=("a", "b")))
    assert res.findings == ()
    assert res.advertised_names == ("a", "b")
    assert res.wire_dispatch_names == ("a", "b")


def test_evidence_findings_folded_through():
    carried = ExternalMcpFinding(
        code="unextractable_case",
        tool="line 7",
        severity="warning",
        message="skipped",
    )
    res = reconcile_external_mcp(("a",), _ev(names=("a",), findings=(carried,)))
    assert carried in res.findings


def test_severity_table_pins_all_seven_codes():
    assert _SEVERITY_BY_CODE == {
        "advertised_not_dispatchable": "error",
        "handler_not_advertised": "info",
        "empty_catalog": "error",
        "dispatch_function_missing": "error",
        "wire_source_unresolved": "error",
        "multiple_dispatch_matches": "warning",
        "unextractable_case": "warning",
    }


def test_format_report_is_deterministic_string():
    res = reconcile_external_mcp(("a", "b"), _ev(names=("a",)))
    report = format_external_mcp_report(res)
    assert "1 advertised" not in report  # sanity: count is 2 advertised
    assert "2 advertised" in report
    assert "advertised_not_dispatchable b" in report
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_external_mcp.py -k "reconcile or severity or format or catalog or overlap or folded or handler or advertised" -v`
Expected: FAIL with `ImportError: cannot import name 'reconcile_external_mcp'`.

- [ ] **Step 3: Implement reconciler + formatter**

Append to `mcp_server/src/rook/agent/external_mcp.py`:

```python
def reconcile_external_mcp(
    advertised_names: Iterable[str],
    wire_evidence: WireDispatchEvidence,
) -> ExternalMcpResolution:
    """Pure two-set reconcile of advertised catalog vs. wire-dispatch handlers.

    advertised - wire  -> advertised_not_dispatchable (error; the public gate)
    wire - advertised  -> handler_not_advertised (info; NOT a defect)
    empty advertised   -> empty_catalog (error)
    wire_evidence.findings are folded through verbatim.
    """
    advertised = frozenset(advertised_names)
    wire = frozenset(wire_evidence.names)
    findings: list[ExternalMcpFinding] = list(wire_evidence.findings)

    if not advertised:
        findings.append(
            _finding(
                "empty_catalog",
                "",
                "Advertised catalog is empty; the advertised evidence source "
                "is broken.",
            )
        )

    for name in sorted(advertised - wire):
        findings.append(
            _finding(
                "advertised_not_dispatchable",
                name,
                f"Advertised MCP tool '{name}' has no wire-dispatch handler.",
            )
        )
    for name in sorted(wire - advertised):
        findings.append(
            _finding(
                "handler_not_advertised",
                name,
                f"Wire handler '{name}' exists outside the public advertised "
                f"MCP surface (may be intentional).",
            )
        )

    return ExternalMcpResolution(
        advertised_names=tuple(sorted(advertised)),
        wire_dispatch_names=tuple(sorted(wire)),
        findings=_sorted_findings(findings),
    )


def format_external_mcp_report(resolution: ExternalMcpResolution) -> str:
    counts = {"error": 0, "warning": 0, "info": 0}
    for finding in resolution.findings:
        counts[finding.severity] += 1
    lines = [
        f"External MCP audit: {len(resolution.advertised_names)} advertised, "
        f"{len(resolution.wire_dispatch_names)} wire handlers, "
        f"{len(resolution.findings)} findings "
        f"(errors={counts['error']} warnings={counts['warning']} "
        f"info={counts['info']})",
    ]
    for finding in resolution.findings:
        lines.append(
            f"  [{finding.severity}] {finding.code} {finding.tool}: "
            f"{finding.message}"
        )
    return "\n".join(lines)
```

- [ ] **Step 4: Run the full module test file**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_external_mcp.py -v`
Expected: PASS (Tasks 1–3).

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/agent/external_mcp.py mcp_server/tests/test_external_mcp.py
git commit -m "feat(lm2g): external_mcp reconciler, severity pin, report formatter"
```

---

### Task 4: Smoke `external` subcommand (origin-gated, structured-gate)

**Files:**
- Modify: `scripts/lm_surface_smoke.py`
- Test: `mcp_server/tests/test_lm_surface_smoke.py`

**Interfaces:**
- Consumes: existing `_check_origins`, `_p` (smoke); `collect_wire_dispatch_evidence`, `reconcile_external_mcp`, `format_external_mcp_report` (Tasks 2–3); `build_catalog_from_mcp_tools`, `list_tools` (existing runtime).
- Produces:
  - `external_exit_decision(findings) -> tuple[int, tuple[str, ...], tuple[str, ...]]` — pure: `(exit_code, warn_codes, fail_codes)` derived only from finding codes (Watchpoint 2).
  - `run_external() -> int`
  - `external` registered in `build_parser()` choices and dispatched in `main()`.

- [ ] **Step 1: Write the failing tests**

Append to `mcp_server/tests/test_lm_surface_smoke.py`. **Reuse the existing
`SMOKE = _load_script()` module-level object** already defined at the top of that
file (loaded via `importlib.util.spec_from_file_location`) — do NOT
`import scripts.lm_surface_smoke`. Monkeypatching `SMOKE` targets the same module
object whose globals `run_external` reads.

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_lm_surface_smoke.py -k external -v`
Expected: FAIL (`AttributeError: module 'scripts.lm_surface_smoke' has no attribute 'external_exit_decision'` / `run_external`).

- [ ] **Step 3: Implement the subcommand**

In `scripts/lm_surface_smoke.py`, add the fail/warn code sets and the pure decision helper near the top-level constants (after `_EXPECTED_EXCLUDED`):

```python
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
```

Add `run_external` after `run_surface`:

```python
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
```

Update `build_parser()` choices and `main()` dispatch:

```python
    parser.add_argument("command", choices=("coherence", "surface", "external"))
```

```python
    if args.command == "coherence":
        return run_coherence()
    if args.command == "surface":
        return run_surface()
    return run_external()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_lm_surface_smoke.py -v`
Expected: PASS (existing + new `external` tests).

- [ ] **Step 5: Run the full LM2 suite + py_compile**

Run:
```
mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_external_mcp.py mcp_server/tests/test_lm_surface_smoke.py mcp_server/tests/test_capability_record.py mcp_server/tests/test_capability_inventory.py mcp_server/tests/test_execution_profile.py mcp_server/tests/test_profile_reconciliation.py -v
mcp_server/.venv/Scripts/python.exe -m py_compile mcp_server/src/rook/agent/external_mcp.py scripts/lm_surface_smoke.py
```
Expected: all PASS; py_compile silent.

- [ ] **Step 6: Commit**

```bash
git add scripts/lm_surface_smoke.py mcp_server/tests/test_lm_surface_smoke.py
git commit -m "feat(lm2g): smoke external subcommand with structured-gate wire audit"
```

---

## Post-implementation (controller, not a task)

After Task 4 and the final whole-branch review pass:
- Open a PR `codex/lm2g-external-mcp-wire-audit` -> `main`.
- After merge: re-mirror current `main` into the deployed venv site-packages, then run the deployed smoke `external` subcommand (empty `PYTHONPATH`, deployed interpreter) and confirm **PASS** with `advertised_not_dispatchable: 0` and `handler_not_advertised: 15` (info). Also confirm `coherence` and `surface` still PASS.
- Update the campaign memory (`lm-local-model-campaign.md`): LM2G merged + verified; `external_mcp` membership done; remaining `rookchat_cloud` deferred.
