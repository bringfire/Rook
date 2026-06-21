# LM2B Execution-Profile View Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a read-only `execution_profile` view that resolves a profile's intended tool set by inverting the LM2A `CapabilityInventory` and emits provenance-aware findings, changing no runtime behavior.

**Architecture:** One stdlib-only module `execution_profile.py` holds the frozen types (`ProfileDefinition`, `ProfileFinding`, `ProfileResolution`), a pure resolver that consumes only `(definitions, CapabilityInventory)`, non-authoritative tier-only seed definitions, and a pure formatter. The resolver inverts inventory records — no `SurfaceSources`, no dispatch-table rescan.

**Tech Stack:** Python 3.12, pytest, the LM2A stdlib-only `rook.agent.capability_record` module. Tests run via `mcp_server/.venv`.

## Global Constraints

- `execution_profile.py` is **stdlib-only**: imports only `dataclasses`, `typing`, and `rook.agent.capability_record`. It must NOT import `tool_groups`, `tool_dispatcher`, `tool_registry`, `tool_contracts`, or `capability_inventory`.
- Read-only/diagnostic only: no `ToolRegistry` replacement, no visibility mutation, no active-schema compilation, no provider/model profile, no PlanGraph, no file writes, no live Rhino/GH.
- The resolver derives intended membership by inverting `CapabilityInventory` records; it takes no `SurfaceSources` and does no dispatch rescan.
- Findings + severity (provenance-aware): `unknown_tier`/`unknown_group`/`unknown_tool`/`mcp_only_tool`/`missing_schema`/`empty_profile` → `warning`; `not_dispatchable` → `error`. `mcp_only_tool` and `not_dispatchable` must not double-fire; `not_dispatchable`/`missing_schema` are gated to `local_visible`.
- `tool_names` = intended names (tier ∪ groups ∪ pins, sorted/deduped, **including unknown pins**); `tools` = resolved `CapabilityRecord`s only.
- `default_profile_definitions()` takes no args and returns a constant set: only `rookchat_local` (`agent_tier0`, `groups=()`) and `readonly` (`readonly_tier0`, `groups=()`). No `planner`, no `external_mcp`.
- All tuple outputs sorted; findings sorted by `(code, subject)`.
- The resolver handles odd/out-of-Literal input defensively (a bogus `initial_tier` string just yields `unknown_tier`); tests may pass such strings with a `# type: ignore`.
- Run all commands from `C:/UDEV/Rook`. Python: `mcp_server/.venv/Scripts/python.exe`.

---

### Task 1: types + resolver

**Files:**
- Create: `mcp_server/src/rook/agent/execution_profile.py`
- Test: `mcp_server/tests/test_execution_profile.py`

**Interfaces:**
- Consumes: `CapabilityInventory`, `CapabilityRecord`, `Severity` from `rook.agent.capability_record` (LM2A; `CapabilityRecord` fields: `name, visibility, tiers, groups, dispatch_path, has_schema, risk, no_argument, mcp_only`).
- Produces:
  - `ProfileDefinition(name, initial_tier=None, groups=(), tools=(), description=None)` (frozen)
  - `ProfileFinding(profile, code, subject, severity, message)` (frozen)
  - `ProfileResolution(profile, tools, tool_names, findings)` (frozen)
  - `resolve_profile(definition: ProfileDefinition, inventory: CapabilityInventory) -> ProfileResolution`
  - `resolve_profiles(definitions, inventory) -> tuple[ProfileResolution, ...]`
  - `_sorted_profile_findings(findings: list[ProfileFinding]) -> list[ProfileFinding]` (used by Task 2 if needed)

- [ ] **Step 1: Write the failing resolver tests**

Create `mcp_server/tests/test_execution_profile.py`:

```python
from __future__ import annotations

import ast
from pathlib import Path

from rook.agent.capability_record import CapabilityInventory, CapabilityRecord
from rook.agent.execution_profile import (
    ProfileDefinition,
    resolve_profile,
    resolve_profiles,
)


def _record(
    name: str,
    *,
    visibility: str = "local_visible",
    tiers: tuple[str, ...] = (),
    groups: tuple[str, ...] = (),
    dispatch_path: str | None = "bridge_route",
    has_schema: bool = True,
    risk: tuple[str, ...] = (),
    no_argument: bool = False,
    mcp_only: bool = False,
) -> CapabilityRecord:
    return CapabilityRecord(
        name=name,
        visibility=visibility,
        tiers=tiers,
        groups=groups,
        dispatch_path=dispatch_path,
        has_schema=has_schema,
        risk=risk,
        no_argument=no_argument,
        mcp_only=mcp_only,
    )


def _inventory() -> CapabilityInventory:
    return CapabilityInventory(
        records=(
            _record("good_local", tiers=("agent_tier0",), groups=("gh_canvas",)),
            _record("nodispatch_local", tiers=("agent_tier0",), dispatch_path=None),
            _record("noschema_local", tiers=("agent_tier0",), has_schema=False),
            _record(
                "mcp_tool",
                visibility="mcp_only_visible",
                groups=("gh_knowledge",),
                dispatch_path=None,
                mcp_only=True,
            ),
            _record("readonly_tool", tiers=("readonly_tier0",)),
        ),
        findings=(),
    )


def _finding_keys(resolution):
    return {(f.code, f.subject, f.severity) for f in resolution.findings}


def test_tier_expansion_resolves_tier_members():
    res = resolve_profile(
        ProfileDefinition(name="p", initial_tier="agent_tier0"), _inventory()
    )
    assert [r.name for r in res.tools] == [
        "good_local",
        "nodispatch_local",
        "noschema_local",
    ]


def test_group_expansion_resolves_group_members():
    res = resolve_profile(
        ProfileDefinition(name="p", groups=("gh_canvas",)), _inventory()
    )
    assert [r.name for r in res.tools] == ["good_local"]


def test_pins_are_additive_and_tool_names_sorted_deduped():
    res = resolve_profile(
        ProfileDefinition(
            name="p",
            initial_tier="readonly_tier0",
            tools=("readonly_tool", "good_local"),
        ),
        _inventory(),
    )
    assert res.tool_names == ("good_local", "readonly_tool")
    assert [r.name for r in res.tools] == ["good_local", "readonly_tool"]


def test_unknown_tier_warning():
    res = resolve_profile(
        ProfileDefinition(name="p", initial_tier="ghost_tier"),  # type: ignore[arg-type]
        _inventory(),
    )
    assert ("unknown_tier", "ghost_tier", "warning") in _finding_keys(res)


def test_unknown_group_warning():
    res = resolve_profile(
        ProfileDefinition(name="p", groups=("ghost_group",)), _inventory()
    )
    assert ("unknown_group", "ghost_group", "warning") in _finding_keys(res)


def test_unknown_tool_warning_keeps_pin_in_tool_names_not_tools():
    res = resolve_profile(
        ProfileDefinition(name="p", initial_tier="agent_tier0", tools=("ghost_tool",)),
        _inventory(),
    )
    assert ("unknown_tool", "ghost_tool", "warning") in _finding_keys(res)
    assert "ghost_tool" in res.tool_names
    assert "ghost_tool" not in {r.name for r in res.tools}


def test_mcp_only_tool_does_not_also_flag_not_dispatchable():
    res = resolve_profile(
        ProfileDefinition(name="p", groups=("gh_knowledge",)), _inventory()
    )
    codes = {(f.code, f.subject) for f in res.findings}
    assert ("mcp_only_tool", "mcp_tool") in codes
    assert ("not_dispatchable", "mcp_tool") not in codes


def test_not_dispatchable_error_for_local_visible_without_path():
    res = resolve_profile(
        ProfileDefinition(name="p", tools=("nodispatch_local",)), _inventory()
    )
    assert ("not_dispatchable", "nodispatch_local", "error") in _finding_keys(res)


def test_missing_schema_warning_for_local_visible_without_schema():
    res = resolve_profile(
        ProfileDefinition(name="p", tools=("noschema_local",)), _inventory()
    )
    assert ("missing_schema", "noschema_local", "warning") in _finding_keys(res)


def test_empty_profile_warning_when_no_known_tools():
    res = resolve_profile(ProfileDefinition(name="p"), _inventory())
    assert res.tools == ()
    assert ("empty_profile", "p", "warning") in _finding_keys(res)


def test_tools_sorted_and_findings_sorted_by_code_subject():
    res = resolve_profile(
        ProfileDefinition(name="p", initial_tier="agent_tier0"), _inventory()
    )
    names = [r.name for r in res.tools]
    assert names == sorted(names)
    finding_keys = [(f.code, f.subject) for f in res.findings]
    assert finding_keys == sorted(finding_keys)


def test_resolve_profiles_preserves_definition_order():
    defs = (
        ProfileDefinition(name="b", initial_tier="readonly_tier0"),
        ProfileDefinition(name="a", initial_tier="agent_tier0"),
    )
    results = resolve_profiles(defs, _inventory())
    assert [r.profile.name for r in results] == ["b", "a"]


def _direct_import_modules(path: str) -> set[str]:
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            prefix = "." * node.level
            modules.add(f"{prefix}{node.module or ''}")
    return modules


def test_execution_profile_is_import_light():
    imports = _direct_import_modules(
        "mcp_server/src/rook/agent/execution_profile.py"
    )
    assert "rook.agent.capability_record" in imports
    assert "rook.agent.tool_groups" not in imports
    assert "rook.agent.tool_dispatcher" not in imports
    assert "rook.agent.tool_registry" not in imports
    assert "rook.agent.chat.tool_contracts" not in imports
    assert "rook.agent.capability_inventory" not in imports
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_execution_profile.py -q`
Expected: collection/import error — `ModuleNotFoundError: No module named 'rook.agent.execution_profile'`.

- [ ] **Step 3: Implement the types + resolver**

Create `mcp_server/src/rook/agent/execution_profile.py`:

```python
"""LM2B read-only execution-profile view over the LM2A capability inventory.

Stdlib-only: imports only the LM2A stdlib-only record module. Resolves a
ProfileDefinition's intended tool set by inverting CapabilityInventory records
(no SurfaceSources, no dispatch-table rescan) and emits provenance-aware
findings. Diagnostic only; changes no runtime behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal

from rook.agent.capability_record import (
    CapabilityInventory,
    CapabilityRecord,
    Severity,
)


@dataclass(frozen=True)
class ProfileDefinition:
    name: str
    initial_tier: Literal["tier0", "agent_tier0", "readonly_tier0"] | None = None
    groups: tuple[str, ...] = ()
    tools: tuple[str, ...] = ()
    description: str | None = None


@dataclass(frozen=True)
class ProfileFinding:
    profile: str
    code: str
    subject: str
    severity: Severity
    message: str


@dataclass(frozen=True)
class ProfileResolution:
    profile: ProfileDefinition
    tools: tuple[CapabilityRecord, ...]
    tool_names: tuple[str, ...]
    findings: tuple[ProfileFinding, ...]


def _sorted_profile_findings(
    findings: list[ProfileFinding],
) -> list[ProfileFinding]:
    return sorted(findings, key=lambda f: (f.code, f.subject))


def resolve_profile(
    definition: ProfileDefinition, inventory: CapabilityInventory
) -> ProfileResolution:
    records = inventory.records
    by_name = {r.name: r for r in records}
    known_groups: set[str] = set()
    known_tiers: set[str] = set()
    for record in records:
        known_groups.update(record.groups)
        known_tiers.update(record.tiers)

    tier_names: set[str] = set()
    if definition.initial_tier is not None:
        tier_names = {
            r.name for r in records if definition.initial_tier in r.tiers
        }

    group_names: set[str] = set()
    for group in definition.groups:
        group_names.update(r.name for r in records if group in r.groups)

    pin_names = set(definition.tools)
    intended = sorted(tier_names | group_names | pin_names)
    tools = tuple(by_name[name] for name in intended if name in by_name)

    name = definition.name
    findings: list[ProfileFinding] = []

    if (
        definition.initial_tier is not None
        and definition.initial_tier not in known_tiers
    ):
        findings.append(
            ProfileFinding(
                profile=name,
                code="unknown_tier",
                subject=definition.initial_tier,
                severity="warning",
                message=(
                    f"Profile '{name}' references tier "
                    f"'{definition.initial_tier}' present in no inventory record."
                ),
            )
        )
    for group in definition.groups:
        if group not in known_groups:
            findings.append(
                ProfileFinding(
                    profile=name,
                    code="unknown_group",
                    subject=group,
                    severity="warning",
                    message=(
                        f"Profile '{name}' references group '{group}' present in "
                        f"no inventory record."
                    ),
                )
            )
    for pin in definition.tools:
        if pin not in by_name:
            findings.append(
                ProfileFinding(
                    profile=name,
                    code="unknown_tool",
                    subject=pin,
                    severity="warning",
                    message=f"Profile '{name}' pins tool '{pin}' with no record.",
                )
            )

    for record in tools:
        if record.mcp_only or record.visibility == "mcp_only_visible":
            findings.append(
                ProfileFinding(
                    profile=name,
                    code="mcp_only_tool",
                    subject=record.name,
                    severity="warning",
                    message=(
                        f"Profile '{name}' includes MCP-only tool "
                        f"'{record.name}'."
                    ),
                )
            )
        elif record.visibility == "local_visible" and record.dispatch_path is None:
            findings.append(
                ProfileFinding(
                    profile=name,
                    code="not_dispatchable",
                    subject=record.name,
                    severity="error",
                    message=(
                        f"Profile '{name}' includes local-visible tool "
                        f"'{record.name}' with no dispatch path."
                    ),
                )
            )
        if record.visibility == "local_visible" and not record.has_schema:
            findings.append(
                ProfileFinding(
                    profile=name,
                    code="missing_schema",
                    subject=record.name,
                    severity="warning",
                    message=(
                        f"Profile '{name}' includes local-visible tool "
                        f"'{record.name}' with no catalog schema."
                    ),
                )
            )

    if not tools:
        findings.append(
            ProfileFinding(
                profile=name,
                code="empty_profile",
                subject=name,
                severity="warning",
                message=f"Profile '{name}' resolves to zero known tools.",
            )
        )

    return ProfileResolution(
        profile=definition,
        tools=tools,
        tool_names=tuple(intended),
        findings=tuple(_sorted_profile_findings(findings)),
    )


def resolve_profiles(
    definitions: Iterable[ProfileDefinition], inventory: CapabilityInventory
) -> tuple[ProfileResolution, ...]:
    return tuple(resolve_profile(d, inventory) for d in definitions)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_execution_profile.py -q`
Expected: PASS (13 tests passed).

- [ ] **Step 5: Compile-check the new module**

Run: `mcp_server/.venv/Scripts/python.exe -m py_compile mcp_server/src/rook/agent/execution_profile.py`
Expected: no output, exit 0.

- [ ] **Step 6: Commit**

```bash
git add mcp_server/src/rook/agent/execution_profile.py mcp_server/tests/test_execution_profile.py
git commit -m "feat(lm2b): execution-profile types and resolver

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: diagnostic seeds + formatter

**Files:**
- Modify: `mcp_server/src/rook/agent/execution_profile.py` (append)
- Modify: `mcp_server/tests/test_execution_profile.py` (append)

**Interfaces:**
- Consumes: `ProfileDefinition`, `resolve_profile`, `resolve_profiles`, `ProfileResolution` from Task 1.
- Produces:
  - `default_profile_definitions() -> tuple[ProfileDefinition, ...]`
  - `format_profile_report(resolutions: Iterable[ProfileResolution]) -> str`

- [ ] **Step 1: Write the failing seed + formatter tests**

First, ADD these two names to the EXISTING top-of-file import from
`rook.agent.execution_profile` in `mcp_server/tests/test_execution_profile.py`
(the Task 1 import block already pulls `ProfileDefinition`, `resolve_profile`,
`resolve_profiles` — extend it so the full import reads):

```python
from rook.agent.execution_profile import (
    ProfileDefinition,
    default_profile_definitions,
    format_profile_report,
    resolve_profile,
    resolve_profiles,
)
```

Then APPEND these test functions to the end of the file:

```python
def test_default_profile_definitions_are_tier_only_seeds():
    by_name = {d.name: d for d in default_profile_definitions()}
    assert set(by_name) == {"rookchat_local", "readonly"}
    assert by_name["rookchat_local"].initial_tier == "agent_tier0"
    assert by_name["rookchat_local"].groups == ()
    assert by_name["readonly"].initial_tier == "readonly_tier0"
    assert by_name["readonly"].groups == ()
    assert "planner" not in by_name
    assert "external_mcp" not in by_name


def test_default_profile_definitions_is_constant():
    assert default_profile_definitions() == default_profile_definitions()


def test_injected_planner_definition_resolves():
    res = resolve_profile(
        ProfileDefinition(name="planner", initial_tier="readonly_tier0"),
        _inventory(),
    )
    assert res.profile.name == "planner"
    assert [r.name for r in res.tools] == ["readonly_tool"]


def test_format_profile_report_is_pure_and_stable():
    results = resolve_profiles(default_profile_definitions(), _inventory())
    first = format_profile_report(results)
    second = format_profile_report(results)
    assert first == second
    assert "Profile rookchat_local:" in first
    assert "Profile readonly:" in first
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider "mcp_server/tests/test_execution_profile.py::test_default_profile_definitions_are_tier_only_seeds" -q`
Expected: FAIL — `ImportError: cannot import name 'default_profile_definitions'` (and `format_profile_report`).

- [ ] **Step 3: Implement the seeds + formatter**

Append to `mcp_server/src/rook/agent/execution_profile.py`:

```python
def default_profile_definitions() -> tuple[ProfileDefinition, ...]:
    """Non-authoritative diagnostic seed profiles.

    Both seeds are tier-only (groups=()): a name-suffix heuristic is not a
    faithful proxy for the repo's READONLY_ALLOWED_GROUPS policy, so readonly
    group membership is deferred until the source snapshot carries explicit
    evidence. No planner / external_mcp seed.
    """
    return (
        ProfileDefinition(
            name="rookchat_local",
            initial_tier="agent_tier0",
            groups=(),
            description="Local in-file execution worker (diagnostic seed).",
        ),
        ProfileDefinition(
            name="readonly",
            initial_tier="readonly_tier0",
            groups=(),
            description="Observation-only worker (diagnostic seed).",
        ),
    )


def format_profile_report(
    resolutions: Iterable[ProfileResolution],
) -> str:
    lines: list[str] = []
    for resolution in resolutions:
        counts = {"error": 0, "warning": 0, "info": 0}
        for finding in resolution.findings:
            counts[finding.severity] += 1
        lines.append(
            f"Profile {resolution.profile.name}: "
            f"{len(resolution.tools)} tools, "
            f"{len(resolution.findings)} findings "
            f"(errors={counts['error']} warnings={counts['warning']} "
            f"info={counts['info']})"
        )
        for finding in resolution.findings:
            lines.append(
                f"  [{finding.severity}] {finding.code} {finding.subject}: "
                f"{finding.message}"
            )
    return "\n".join(lines)
```

- [ ] **Step 4: Run the full test file to verify everything passes**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_execution_profile.py -q`
Expected: PASS (17 tests passed).

- [ ] **Step 5: py_compile + whitespace check**

Run: `mcp_server/.venv/Scripts/python.exe -m py_compile mcp_server/src/rook/agent/execution_profile.py`
Expected: no output, exit 0.

Run: `git diff --check`
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git add mcp_server/src/rook/agent/execution_profile.py mcp_server/tests/test_execution_profile.py
git commit -m "feat(lm2b): diagnostic seed profiles and report formatter

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

**1. Spec coverage** (against `docs/superpowers/specs/2026-06-21-lm2b-execution-profile-view-design.md`):

- Stdlib-only module + the three frozen types → Task 1 Step 3; import-light enforced by `test_execution_profile_is_import_light` (Task 1).
- Resolver inverts records, no `SurfaceSources`/rescan → Task 1 Step 3; tier/group expansion tests (Task 1 Step 1).
- `tool_names` (incl. unknown pins) vs `tools` (resolved) → `test_unknown_tool_warning_keeps_pin_in_tool_names_not_tools`.
- Findings + severity table; `mcp_only_tool`/`not_dispatchable` no double-fire; `local_visible` gate → `test_mcp_only_tool_does_not_also_flag_not_dispatchable`, `test_not_dispatchable_error_for_local_visible_without_path`, `test_missing_schema_warning_for_local_visible_without_schema`.
- `unknown_tier`/`unknown_group`/`unknown_tool`/`empty_profile` warnings → respective tests; bogus tier string handled defensively with `# type: ignore`.
- Determinism: tools sorted, findings sorted by `(code, subject)`, `resolve_profiles` order → `test_tools_sorted_and_findings_sorted_by_code_subject`, `test_resolve_profiles_preserves_definition_order`.
- `default_profile_definitions()` tier-only constant seeds, no `planner`/`external_mcp` → Task 2 Step 3; `test_default_profile_definitions_are_tier_only_seeds`, `test_default_profile_definitions_is_constant`.
- Resolver handles injected `planner` → `test_injected_planner_definition_resolves`.
- `format_profile_report` pure/secondary → `test_format_profile_report_is_pure_and_stable`.

No gaps found.

**2. Placeholder scan:** No TBD/TODO, no "add error handling", no "write tests for the above", no "similar to Task N". All module and test code is shown in full. The `CapabilityRecord` field list used in `_record` matches the merged LM2A `capability_record.py` (`name, visibility, tiers, groups, dispatch_path, has_schema, risk, no_argument, mcp_only`).

**3. Type consistency:** `ProfileDefinition`, `ProfileFinding`, `ProfileResolution`, `resolve_profile`, `resolve_profiles`, `_sorted_profile_findings` are defined in Task 1 and reused by name in Task 2. `default_profile_definitions() -> tuple[ProfileDefinition, ...]` and `format_profile_report(resolutions) -> str` match the spec and the Task 2 interfaces block. Finding codes (`unknown_tier`, `unknown_group`, `unknown_tool`, `mcp_only_tool`, `not_dispatchable`, `missing_schema`, `empty_profile`) and severities are identical between the resolver implementation and the asserting tests.
