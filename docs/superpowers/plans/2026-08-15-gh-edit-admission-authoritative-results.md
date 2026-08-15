# Grasshopper Edit Admission And Authoritative Results Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refuse malformed or unresolved `gh_edit` temporary references before target contact or mutation, and preserve exact authoritative Grasshopper results without universal knowledge hints.

**Architecture:** Extend the existing Python `gh_edit_contract.py` with one pure request-admission owner used by canonical and direct dispatch. Mirror the exact closed contract at the start of managed `ApplyEdit` so raw endpoint callers are protected before Grasshopper access. Add the four authoritative tools to the existing knowledge-injection skip set; no production module or endpoint is added.

**Tech Stack:** Python 3.10, pytest, MCP SDK, C#/.NET, xUnit, System.Text.Json, existing Rook bridge and Grasshopper test fakes.

## Global Constraints

- Baseline is `61c686c5e1204ded860fc9a22f8acc65c4f99db6` plus documentation commit `ddfe33b2`.
- Temporary IDs match exact regex `^T[A-Za-z0-9_]{1,63}$`; total length is 2 through 64.
- Existing component identities match `^C[1-9][0-9]*$` at admission.
- Admission issue codes are exactly `invalid_temp_id`, `duplicate_temp_id`, `invalid_flow`, `invalid_component_reference`, and `unresolved_temp_reference`.
- Admission issue order is `create`, `disconnect`, `set_values`, `connect`, `groups`, preserving array order.
- No new production module, endpoint, identity family, schema copy, dependency, planner, critic, scheduler, or evaluator.
- Preserve valid `C*`/`T*` execution, mutation receipts, solve-readiness receipts, and partial-failure semantics after admission.
- Add knowledge skips only for `gh_edit`, `gh_snapshot`, `gh_status`, and `gh_errors`; preserve existing skips.
- Use `-p:RhinoPluginDir=` for managed verification so tests do not deploy a plugin.
- The three known unrelated Python baseline failures remain out of scope and must be reported separately.

---

## File Map

### Production

- `mcp_server/src/rook/gh_edit_contract.py` — pure Python request admission plus existing result projection.
- `mcp_server/src/rook/server.py` — public schema constraint and canonical pre-target admission.
- `mcp_server/src/rook/agent/tool_dispatcher.py` — direct-dispatch pre-target admission.
- `src/Rook/Handlers/GrasshopperHandler.cs` — managed raw-request admission before readiness/canvas access.
- `mcp_server/src/rook/learning/knowledge_injector.py` — authoritative-result skip set.

### Tests

- `mcp_server/tests/test_gh_edit_contract.py` — pure grammar, correlation, issue order, and immutability.
- `mcp_server/tests/test_gh_authoring_capability_routing.py` — canonical/direct zero-dispatch parity and schema surface.
- `src/Rook.Tests/Handlers/GrasshopperTerminalMutationReceiptTests.cs` — managed zero-contact/mutation and valid descriptive-ID behavior using existing fakes.
- `mcp_server/tests/test_knowledge_injector.py` — exact skip-set behavior.
- `mcp_server/tests/test_chatrunner_mcp_capability_gateway.py` — canonical gateway/direct exact-result parity.

---

### Task 1: Python Request Admission And Dispatch Parity

**Files:**

- Modify: `mcp_server/src/rook/gh_edit_contract.py`
- Modify: `mcp_server/src/rook/server.py`
- Modify: `mcp_server/src/rook/agent/tool_dispatcher.py`
- Test: `mcp_server/tests/test_gh_edit_contract.py`
- Test: `mcp_server/tests/test_gh_authoring_capability_routing.py`

**Interfaces:**

- Produces: `admit_gh_edit_request(arguments: dict[str, Any]) -> dict[str, Any] | None`
- Returns: `None` for admission; otherwise a closed failure envelope whose data has
  exactly `error="gh_edit_admission_failed"` and the ordered `issues` array.
- Consumed by: public `call_tool()`, `_call_tool_dispatch()`, and `ToolDispatcher.dispatch()` before port removal, route resolution, or native dispatch.

- [ ] **Step 1: Write the pure admission RED tests**

Add table-driven tests that freeze the contract:

```python
@pytest.mark.parametrize("temp_id", ["T1", "TActorSetControl", "T_CLEAN"])
def test_descriptive_temp_ids_are_admitted(temp_id):
    request = {
        "epoch": 3,
        "create": [{"temp_id": temp_id, "type": "slider"}],
        "set_values": [{"id": temp_id, "value": 2}],
        "groups": [{"action": "create", "members": [temp_id]}],
    }
    assert admit_gh_edit_request(request) is None


def test_duplicate_and_unresolved_temp_ids_refuse_in_fixed_order():
    request = {
        "epoch": 3,
        "create": [
            {"temp_id": "T_CLEAN", "type": "slider"},
            {"temp_id": "T_CLEAN", "type": "panel"},
        ],
        "disconnect": ["TUNKNOWN.O0>C1.I0"],
        "set_values": [{"id": "N1", "value": 2}],
        "connect": ["T_CLEAN.O0>TABSENT.I0"],
        "groups": [{"action": "create", "members": ["N2"]}],
    }
    result = admit_gh_edit_request(request)
    assert result["success"] is False
    assert result["data"]["error"] == "gh_edit_admission_failed"
    assert [issue["code"] for issue in result["data"]["issues"]] == [
        "duplicate_temp_id",
        "unresolved_temp_reference",
        "invalid_component_reference",
        "unresolved_temp_reference",
        "invalid_component_reference",
    ]
    assert request["create"][0]["temp_id"] == "T_CLEAN"
```

Also cover missing/wrong-type/overlength IDs, embedded/trailing newlines, lowercase
`t1`, malformed flows, negative/non-numeric port indices, undeclared `T*` in both
flow positions, valid `C*` references, and preservation of existing lowercase port
markers and leading-zero integer suffixes.

- [ ] **Step 2: Run the pure tests and verify RED**

Run:

```powershell
$env:PYTHONPATH = "$PWD/mcp_server/src"
& "C:/Users/bring/AppData/Local/Programs/Python/Python310/Scripts/pytest.exe" `
  -q mcp_server/tests/test_gh_edit_contract.py
```

Expected: import failure for `admit_gh_edit_request` or assertion failures because no admission owner exists.

- [ ] **Step 3: Implement the pure Python owner**

In `gh_edit_contract.py`, add only module-local compiled regexes and small pure helpers.
Expose the anchored pattern string for the public JSON Schema, but use `fullmatch()`
internally so a trailing newline cannot exploit `$` semantics:

```python
GH_EDIT_TEMP_ID_PATTERN = r"^T[A-Za-z0-9_]{1,63}$"
_TEMP_ID = re.compile(r"T[A-Za-z0-9_]{1,63}")
_COMPONENT_ID = re.compile(r"C[1-9][0-9]*")


def admit_gh_edit_request(arguments: dict[str, Any]) -> dict[str, Any] | None:
    """Return one closed pre-dispatch refusal or None without mutating arguments."""
```

Implement `_parse_flow_ids(flow: Any) -> tuple[str, str] | None` by mirroring the
current managed `ParseFlowString()` behavior: exactly one `>`, exactly one `.` on
each side, `O`/`o` for the source, `I`/`i` for the target, and integer suffixes that
parse and are nonnegative. This slice validates references without narrowing existing
port-notation compatibility. Managed admission continues to call the existing parser.

Implementation rules:

1. Collect declared temp IDs and create issues before scanning references.
2. Preserve exact ordinal uniqueness and use `_TEMP_ID.fullmatch()` and
   `_COMPONENT_ID.fullmatch()` for identity admission.
3. Scan fields in the frozen semantic order.
4. For each reference, accept exact declared `T*`, accept syntactic `C*`, classify
   undeclared syntactic `T*` as `unresolved_temp_reference`, and everything else as
   `invalid_component_reference`.
5. Store the exact offending JSON value in each issue; do not stringify containers.
6. Return the closed failure or `None`. Each dispatcher returns a refusal immediately,
   before its post-dispatch verification path, so no private sentinel is needed.

- [ ] **Step 4: Add routing and schema RED tests**

Add causal tests using hostile `call_rhino` and hostile target resolution:

```python
@pytest.mark.asyncio
async def test_invalid_edit_refuses_before_canonical_or_direct_target_contact(monkeypatch):
    request = {
        "epoch": 7,
        "create": [{"temp_id": "TActorSetControl", "type": "slider"}],
        "connect": ["N1.O0>TActorSetControl.I0"],
    }
    calls = []

    async def fail_if_contacted(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("target dispatch occurred")

    monkeypatch.setattr(server, "call_rhino", fail_if_contacted)
    monkeypatch.setattr(dispatcher_module, "call_rhino", fail_if_contacted)
    canonical = await server.call_tool("gh_edit", request, _public_mcp=True)
    direct = await ToolDispatcher(port=9950).dispatch("gh_edit", request)
    assert canonical.structuredContent == direct
    assert direct["data"]["issues"][0]["code"] == "invalid_component_reference"
    assert calls == []
```

Inspect `list_tools()` and assert the existing `temp_id` property retains its
description while adding these exact constraints:

```python
temp_id = gh_edit_schema["properties"]["create"]["items"]["properties"]["temp_id"]
assert temp_id["type"] == "string"
assert temp_id["pattern"] == "^T[A-Za-z0-9_]{1,63}$"
assert temp_id["minLength"] == 2
assert temp_id["maxLength"] == 64
assert temp_id["description"] == "Temporary ID (T1, T2, ...) for referencing in connect/groups"
```

Preserve the existing description text in addition to these constraints.

- [ ] **Step 5: Wire all Python dispatch paths**

Import `admit_gh_edit_request` beside `apply_gh_edit_contract`.

In public `call_tool()`, invoke admission after existing containment/profile/meta/schema
and script-handoff checks, but before target resolution or document enrichment. In
`_call_tool_dispatch()` and `ToolDispatcher.dispatch()`, repeat the admission immediately
after the existing script-handoff guard as defense in depth. Every path returns a
refusal immediately; no internal field is added or stripped.

Update the public schema for `temp_id` with the frozen pattern and length bounds.

- [ ] **Step 6: Run focused Python GREEN tests**

Run:

```powershell
$env:PYTHONPATH = "$PWD/mcp_server/src"
& "C:/Users/bring/AppData/Local/Programs/Python/Python310/Scripts/pytest.exe" `
  -q mcp_server/tests/test_gh_edit_contract.py `
     mcp_server/tests/test_gh_authoring_capability_routing.py
```

Expected: all tests pass and hostile target callbacks remain uncalled.

- [ ] **Step 7: Commit Task 1**

```powershell
git add -- mcp_server/src/rook/gh_edit_contract.py `
  mcp_server/src/rook/server.py `
  mcp_server/src/rook/agent/tool_dispatcher.py `
  mcp_server/tests/test_gh_edit_contract.py `
  mcp_server/tests/test_gh_authoring_capability_routing.py
git commit -m "fix: admit gh edit references before dispatch"
```

---

### Task 2: Managed Raw-Route Admission Before Grasshopper Access

**Files:**

- Modify: `src/Rook/Handlers/GrasshopperHandler.cs`
- Test: `src/Rook.Tests/Handlers/GrasshopperTerminalMutationReceiptTests.cs`

**Interfaces:**

- Consumes: the exact grammar, field order, issue codes, and refusal data from Task 1.
- Produces: private `ValidateEditAdmission(Dictionary<string, JsonElement> args) -> ApiResponse?`.
- Existing `ApplyEdit()` consumes the validated dictionary only after the helper returns `null`.

- [ ] **Step 1: Write managed RED tests for zero contact and zero mutation**

Extend the existing receipt tests with a counting `IGrasshopperCore` and the existing
`FakeDocument` counters:

```csharp
[Theory]
[InlineData("N1.O0>TActorSetControl.I0", "invalid_component_reference")]
[InlineData("TABSENT.O0>TActorSetControl.I0", "unresolved_temp_reference")]
public void ApplyEdit_InvalidReferencesRefuseBeforeGrasshopperAccess(
    string flow,
    string expectedCode)
{
    var core = new CountingReadyCore();
    var document = new FakeDocument { ThrowOnObjectsRead = true };
    var registry = new GhSolveReceiptRegistry();
    var handler = CreateHandler(document, registry: registry, bridgeCore: core);

    var response = handler.ApplyEdit(JsonSerializer.Serialize(new
    {
        epoch = 0,
        create = new[] { new { temp_id = "TActorSetControl", type = "slider" } },
        connect = new[] { flow },
    }));

    Assert.False(response.Success);
    var data = Element(response.Data);
    Assert.Equal("gh_edit_admission_failed", data.GetProperty("error").GetString());
    Assert.Equal(expectedCode,
        data.GetProperty("issues")[0].GetProperty("code").GetString());
    Assert.Equal(0, core.StatusCallCount);
    Assert.Equal(0, document.ObjectsReadCount);
    Assert.Equal(0, document.ScheduleCount);
    Assert.Empty(document.ObjectsWithoutObservation);
}
```

Add separate causal cases for duplicate `T_CLEAN`, missing/invalid/overlength IDs,
malformed flow, invalid value reference, invalid group member, and a mixed request
whose first create would otherwise commit.

Add one valid case using `TActorSetControl` and `T_CLEAN` that proves normal creation,
value setting/correlation, existing temp maps, and solve receipt behavior remain.

- [ ] **Step 2: Run managed tests and verify RED**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore -c Debug `
  --filter FullyQualifiedName~GrasshopperTerminalMutationReceiptTests `
  -p:RhinoPluginDir=
```

Expected: new tests fail because `ApplyEdit` contacts readiness/canvas before parsing
and currently mutates before reference failures.

- [ ] **Step 3: Implement managed admission in the existing handler**

Add `using System.Text.RegularExpressions;`, exact compiled identity regexes using
`\A` and `\z`, and private helpers in `GrasshopperHandler.cs`. Reuse the existing pure
`ParseFlowString()` for flow syntax; do not add another flow parser or narrow its
current port-notation behavior.

Reorder `ApplyEdit()`:

```csharp
missing-body check
-> deserialize Dictionary<string, JsonElement>
-> ValidateEditAdmission(args)
-> EnsureGrasshopperReadyForEdit("gh_edit")
-> GetGrasshopper()
-> epoch validation
-> existing receipt/mutation lifecycle unchanged
```

The helper accumulates `List<Dictionary<string, object?>>` issues. Use
`JsonElement.Clone()` when retaining a caller JSON value. Return:

```csharp
new ApiResponse
{
    Success = false,
    Data = new Dictionary<string, object?>
    {
        ["error"] = "gh_edit_admission_failed",
        ["issues"] = issues,
    },
};
```

Do not validate canvas existence for admitted `C*` syntax and do not change any
post-admission error, receipt, schedule, undo, or partial-success path.

- [ ] **Step 4: Run managed GREEN and adjacent receipt tests**

Run the Task 2 command again, then:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.cs --no-restore -c Debug `
  --filter "FullyQualifiedName~GrasshopperTerminalMutationReceiptTests|FullyQualifiedName~GrasshopperBehavioralSnapshotTests|FullyQualifiedName~GhEditSolvePathSourceTests" `
  -p:RhinoPluginDir=
```

Expected: all selected tests pass, zero plugin deployment occurs, and existing receipt
and solve scheduling assertions remain unchanged.

- [ ] **Step 5: Commit Task 2**

```powershell
git add -- src/Rook/Handlers/GrasshopperHandler.cs `
  src/Rook.Tests/Handlers/GrasshopperTerminalMutationReceiptTests.cs
git commit -m "fix: refuse invalid gh edit references before mutation"
```

---

### Task 3: Authoritative Grasshopper Result Skips

**Files:**

- Modify: `mcp_server/src/rook/learning/knowledge_injector.py`
- Test: `mcp_server/tests/test_knowledge_injector.py`
- Test: `mcp_server/tests/test_chatrunner_mcp_capability_gateway.py`

**Interfaces:**

- Consumes: existing `_SKIP_TOOLS` and `should_inject()`.
- Produces: exact no-injection behavior for `gh_edit`, `gh_snapshot`, `gh_status`, and `gh_errors` through direct and canonical gateway dispatch.

- [ ] **Step 1: Write knowledge-boundary RED tests**

Add an exact skip-set test:

```python
@pytest.mark.parametrize(
    "tool_name",
    [
        "gh_edit",
        "gh_snapshot",
        "gh_status",
        "gh_errors",
        "gh_library",
        "gh_batch_component_info",
    ],
)
def test_authoritative_grasshopper_tools_never_receive_universal_knowledge(tool_name):
    result = {"success": True, "data": {"sentinel": tool_name}}
    assert should_inject(tool_name, result) is False
```

Add one unrelated successful tool assertion proving knowledge remains eligible.

- [ ] **Step 2: Add direct/canonical gateway RED tests**

For each of the four new skips, use one native sentinel result and a hostile
`inject_knowledge`:

```python
@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name", ["gh_edit", "gh_snapshot", "gh_status", "gh_errors"])
async def test_authoritative_results_match_direct_and_canonical_without_hints(
    monkeypatch,
    tool_name,
):
    native = {"success": True, "data": {"sentinel": tool_name}}
    calls = []

    async def fake_call_rhino(endpoint, method="GET", data=None, port=None):
        calls.append((endpoint, method, data, port))
        return copy.deepcopy(native)

    async def forbidden_injection(*args, **kwargs):
        raise AssertionError("knowledge injection reached authoritative result")

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)
    monkeypatch.setattr(dispatcher_module, "call_rhino", fake_call_rhino)
    monkeypatch.setattr(server, "inject_knowledge", forbidden_injection)

    arguments = {"epoch": 0} if tool_name == "gh_edit" else {}
    direct = await ToolDispatcher(port=9950).dispatch(tool_name, arguments)
    canonical = await server.call_tool(
        "rook_tools_call",
        {"name": tool_name, "arguments": arguments},
        _public_mcp=True,
    )
    assert canonical.structuredContent == direct
    assert "knowledge_hint" not in direct["data"]
```

Use shape-compatible fixtures where existing `gh_status` normalization or readiness
hoisting applies, and compare the final established direct result rather than bypassing
those owners. Assert one target dispatch per operation and exact unchanged arguments.

- [ ] **Step 3: Run the knowledge tests and verify RED**

Run:

```powershell
$env:PYTHONPATH = "$PWD/mcp_server/src"
& "C:/Users/bring/AppData/Local/Programs/Python/Python310/Scripts/pytest.exe" `
  -q mcp_server/tests/test_knowledge_injector.py `
     mcp_server/tests/test_chatrunner_mcp_capability_gateway.py
```

Expected: the four new tools are still eligible for universal injection or the
hostile injector is reached.

- [ ] **Step 4: Extend only the existing skip set**

Add the four names to `_SKIP_TOOLS` beside the existing authoritative discovery
tools. Do not add wrappers, branches, parsers, or result copies.

- [ ] **Step 5: Run focused GREEN tests**

Run the Task 3 command again. Expected: all selected tests pass; existing two
documented knowledge-store baseline failures, if reached by a broader command, remain
separately reported.

- [ ] **Step 6: Commit Task 3**

```powershell
git add -- mcp_server/src/rook/learning/knowledge_injector.py `
  mcp_server/tests/test_knowledge_injector.py `
  mcp_server/tests/test_chatrunner_mcp_capability_gateway.py
git commit -m "fix: preserve authoritative grasshopper results"
```

---

### Task 4: Reconciliation, Verification, And Independent Review

**Files:**

- Review: all production/test files changed in Tasks 1–3
- Modify only if implementation facts require correction: `docs/superpowers/specs/2026-08-15-gh-edit-admission-authoritative-results-design.md`

**Interfaces:**

- Consumes: three independently committed production corrections.
- Produces: verified branch head suitable for independent code review and normal integration.

- [ ] **Step 1: Run focused and adjacent Python suites**

```powershell
$env:PYTHONPATH = "$PWD/mcp_server/src"
& "C:/Users/bring/AppData/Local/Programs/Python/Python310/Scripts/pytest.exe" -q `
  mcp_server/tests/test_gh_edit_contract.py `
  mcp_server/tests/test_gh_authoring_capability_routing.py `
  mcp_server/tests/test_gh_edit_postmortem.py `
  mcp_server/tests/test_knowledge_injector.py `
  mcp_server/tests/test_chatrunner_mcp_capability_gateway.py
```

Record all pass/fail counts. Confirm any failures are byte-for-byte the known baseline
failures before excluding them from this branch's verdict.

- [ ] **Step 2: Run the complete managed suite without deployment**

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore -c Debug `
  -p:RhinoPluginDir=
```

Expected: complete managed suite passes with only existing warnings.

- [ ] **Step 3: Run compilation, whitespace, and scope checks**

```powershell
& "C:/Users/bring/AppData/Local/Programs/Python/Python310/python.exe" -m compileall -q `
  mcp_server/src/rook/gh_edit_contract.py `
  mcp_server/src/rook/server.py `
  mcp_server/src/rook/agent/tool_dispatcher.py `
  mcp_server/src/rook/learning/knowledge_injector.py
git diff --check origin/main...HEAD
git status --short
git diff --stat origin/main...HEAD
```

Count nonblank production additions/deletions per owner. Stop if a sixth production
owner or new module appeared.

- [ ] **Step 4: Perform requirement-by-requirement self-review**

Confirm from tests and source:

- every declared temp ID is valid and unique before target contact;
- every flow/value/group temp reference is declared;
- `N*` never reaches native or managed mutation;
- valid descriptive IDs retain correlation and receipts;
- direct and canonical behavior agree;
- managed raw calls independently fail closed;
- all six authoritative tools bypass universal hints;
- campaign evidence root and report hash remain unchanged;
- no helix or live-runtime artifact exists yet.

- [ ] **Step 5: Obtain independent code review**

Provide the reviewer the exact baseline/head, design, plan, changed-file inventory,
test outputs, production line counts, and known baseline failures. Require P0–P3
findings with causal evidence. Address findings test-first in the owning task; do not
expand architecture.

- [ ] **Step 6: Commit any truthful documentation reconciliation**

If no reconciliation is required, do not create an empty commit. Otherwise:

```powershell
git add -- docs/superpowers/specs/2026-08-15-gh-edit-admission-authoritative-results-design.md
git commit -m "docs: reconcile gh edit admission implementation"
```

- [ ] **Step 7: Integrate normally, then deploy Release**

After review approval, push, open a non-draft PR, verify exact remote base/head and
scope, merge without rebasing, update a clean `main`, and run the standard Release
deployment. Restart Rhino and MCP only after deployment completes, then verify the
deployed managed and Python hashes against the merge build.

- [ ] **Step 8: Prepare the disposable helix qualification and stop before contact**

Reuse the frozen Qwen3.8 model/runtime/adapter/skill and receipt-fenced evidence
custody. Freeze the unchanged intent and one task-local probe covering ordered
points/curve, radial periodic XY, monotonic Z, claimed-control causality, exact
restoration, and clean diagnostics. Unsupported properties are `unproven`.

Permit one Actor run and at most one bounded same-session repair. Do not add a
staircase case or production semantic vocabulary. Corroborate a fresh empty target,
freeze local artifacts and hashes, and stop for explicit live-contact authorization.
