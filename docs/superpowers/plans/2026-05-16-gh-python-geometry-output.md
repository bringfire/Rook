# GH Python Geometry Output Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make generated Grasshopper Python script components declare geometry outputs with concrete GH/Rhino types and assign real RhinoCommon geometry values, with a live regression proving a `Point3d` list output bakes as downstream geometry.

**Architecture:** This is a narrow guidance-and-regression slice. Update MCP tool descriptions and agent prompt/persona text so agents produce `pins_out` object forms such as `{"name": "Points", "type": "Point3d", "access": "list"}` and scripts assign `Rhino.Geometry` values such as `rg.Point3d`, while leaving runtime coercion/enforcement unchanged. Add contract tests for the guidance surfaces and one live Rhino regression anchored by `gh_bake_output`, because baking proves the output is usable GH/Rhino geometry rather than a serialized inspection artifact.

**Tech Stack:** Python MCP server, pytest, Rhino/RhinoCommon, Grasshopper RhinoCode Python 3 script components, existing Rook managed Grasshopper bake route.

---

## File Structure

- Modify `mcp_server/src/rook/server.py`
  - Responsibility: MCP tool descriptions and JSON schema text for `gh_create_python_script` and `gh_create_script`.
  - Scope: Description strings and `pins_out` schema descriptions only. Do not change `_execute_gh_create_script`, pin normalization, or runtime behavior in this slice.
- Modify `mcp_server/src/rook/agent/personas/scripter/role.md`
  - Responsibility: Scripter persona guidance for GH script outputs.
  - Scope: Replace the over-broad `DataTree[object]` output advice with geometry-first RhinoCommon list guidance plus a limited DataTree rule.
- Modify `mcp_server/src/rook/agent/personas/worker/role.md`
  - Responsibility: Worker persona guidance for when to create GH script components.
  - Scope: Add a concise geometry output contract near existing `gh_create_script` guidance.
- Modify `mcp_server/src/rook/agent/personas/architect/role.md`
  - Responsibility: Architect persona guidance for specifying script component outputs.
  - Scope: Add the same geometry output contract so plans/specs pass usable output requirements to workers.
- Modify `mcp_server/src/rook/agent/prompts/WORKER.md`
  - Responsibility: Display/snapshot worker prompt surface.
  - Scope: Add the same geometry output contract so the snapshot does not contradict runtime personas.
- Modify `mcp_server/tests/test_server_contract_hardening.py`
  - Responsibility: MCP server contract regressions.
  - Scope: Assert `gh_create_script` and `gh_create_python_script` descriptions explicitly teach typed geometry list outputs and reject dict/string/blob output patterns.
- Modify `mcp_server/tests/test_chat_prompt_builder.py`
  - Responsibility: Built persona prompt regressions.
  - Scope: Assert worker, architect, and scripter prompts contain the geometry output contract and that the old over-broad DataTree rule is absent.
- Modify `mcp_server/tests/test_gh_create_script_live.py`
  - Responsibility: Live Rhino regression for usable output geometry.
  - Scope: Create a Python script component with declared `Point3d` list output, bake its output, and assert the bake reports three baked point geometries.

## Task 1: Add Failing MCP Tool Description Contract

**Files:**
- Modify: `mcp_server/tests/test_server_contract_hardening.py`

- [ ] **Step 1: Add helpers and a failing test for geometry output guidance**

Append this test near the existing `gh_create_script` contract tests in `mcp_server/tests/test_server_contract_hardening.py`:

```python
@pytest.mark.asyncio
async def test_gh_script_tool_descriptions_teach_usable_geometry_outputs():
    required = [
        '{"name": "Points", "type": "Point3d", "access": "list"}',
        "Points = [rg.Point3d(0, 0, 0), rg.Point3d(1, 0, 0), rg.Point3d(2, 0, 0)]",
        "Do not assign coordinate dictionaries",
        "Do not assign JSON strings",
        "Do not assign wrapper/debug objects",
    ]

    tools = {tool.name: tool for tool in await server.list_tools()}
    for tool_name in ("gh_create_script", "gh_create_python_script"):
        tool = tools[tool_name]
        description = tool.description
        for phrase in required:
            assert phrase in description, f"{tool_name} missing geometry output guidance: {phrase}"

        pins_out_description = tool.inputSchema["properties"]["pins_out"]["description"]
        assert '{"name": "Points", "type": "Point3d", "access": "list"}' in pins_out_description
```

- [ ] **Step 2: Run the focused contract test and confirm it fails**

Run:

```powershell
python -m pytest mcp_server/tests/test_server_contract_hardening.py::test_gh_script_tool_descriptions_teach_usable_geometry_outputs -q
```

Expected before implementation: `FAILED`, with an assertion showing the first missing phrase from a tool description.

## Task 2: Add Failing Persona Prompt Contract

**Files:**
- Modify: `mcp_server/tests/test_chat_prompt_builder.py`

- [ ] **Step 1: Add a prompt regression for geometry output guidance**

Append this test after `test_persona_prompt_script_tool_language_is_capability_accurate`:

```python
@pytest.mark.parametrize("persona", ["worker", "architect", "scripter"])
def test_persona_prompt_script_geometry_outputs_are_rhinocommon_values(persona):
    prompt = PromptBuilder().build_system(persona)

    assert "Geometry outputs" in prompt
    assert '{"name": "Points", "type": "Point3d", "access": "list"}' in prompt
    assert "Points = [rg.Point3d(0, 0, 0), rg.Point3d(1, 0, 0), rg.Point3d(2, 0, 0)]" in prompt
    assert "Do not output coordinate dictionaries" in prompt
    assert "Do not output JSON strings" in prompt
    assert "Do not output wrapper/debug objects" in prompt
    assert "Use DataTree[object] only when you intentionally need tree topology" in prompt


def test_scripter_prompt_no_longer_requires_datatree_for_all_python_lists():
    prompt = PromptBuilder().build_system("scripter")

    assert "Python lists must be wrapped in `DataTree[object]()` for GH to display each item" not in prompt
```

- [ ] **Step 2: Run the focused prompt tests and confirm they fail**

Run:

```powershell
python -m pytest mcp_server/tests/test_chat_prompt_builder.py::test_persona_prompt_script_geometry_outputs_are_rhinocommon_values mcp_server/tests/test_chat_prompt_builder.py::test_scripter_prompt_no_longer_requires_datatree_for_all_python_lists -q
```

Expected before implementation: `FAILED`, with missing geometry guidance in at least one persona and the old DataTree sentence still present in the scripter persona.

## Task 3: Add Live Bake Regression

**Files:**
- Modify: `mcp_server/tests/test_gh_create_script_live.py`

- [ ] **Step 1: Add the live `Point3d` list bake test**

Append this test before `test_gh_create_script_omitted_language_fails_live`:

```python
async def test_gh_create_script_python_point_list_bakes_as_geometry():
    """A declared Point3d list output must be usable by downstream GH/Rhino
    geometry consumers. Baking is the anchor because it fails for dicts,
    strings, wrapper/debug objects, or other non-geometry blobs.
    """
    from rook.server import _mcp_tool_executor

    result = await _mcp_tool_executor(
        "gh_create_script",
        {
            "language": "python",
            "code": (
                "import Rhino.Geometry as rg\n"
                "Points = [rg.Point3d(0, 0, 0), rg.Point3d(1, 0, 0), rg.Point3d(2, 0, 0)]"
            ),
            "pins_in": [],
            "pins_out": [{"name": "Points", "type": "Point3d", "access": "list"}],
            "name": "UsablePointListPyLive",
            "x": 300,
            "y": 420,
        },
    )
    assert not _is_error(result), f"gh_create_script Point3d list failed: {result!r}"

    guid = _get_guid(result)
    assert isinstance(guid, str) and guid, f"no component_guid in response: {result!r}"

    bake = await _mcp_tool_executor(
        "gh_bake_output",
        {
            "targets": [
                {
                    "instanceGuid": guid,
                    "outputIndex": 1,
                    "outputName": "Points",
                }
            ],
            "layerName": "RookTest_GhPythonPointList",
            "createSublayers": True,
            "clearExisting": True,
        },
    )
    assert not _is_error(bake), f"gh_bake_output failed for Point3d list: {bake!r}"

    data = bake.get("data") if isinstance(bake, dict) else None
    assert isinstance(data, dict), f"unexpected bake response: {bake!r}"
    assert data.get("totalBaked") == 3

    per_target = data.get("perTarget")
    assert isinstance(per_target, list) and len(per_target) == 1
    target = per_target[0]
    assert target.get("bakedCount") == 3
    assert len(target.get("bakedIds", [])) == 3

    geometry_types = target.get("geometryTypes")
    assert isinstance(geometry_types, list)
    assert "Point3d" in geometry_types
```

The script component normally has output index `0` reserved for the `out` stream, so the user-declared `Points` output is index `1`. Keeping `outputName: "Points"` in the target makes the test fail loudly if index assumptions drift.

- [ ] **Step 2: Run the live regression**

Run with Rhino open, Rook loaded, and Grasshopper available:

```powershell
python -m pytest -m requires_rhino mcp_server/tests/test_gh_create_script_live.py::test_gh_create_script_python_point_list_bakes_as_geometry -q
```

Expected result:
- `PASSED` if the existing RhinoCode output path already preserves real `Point3d` values.
- `FAILED` with `totalBaked == 0`, missing `"Point3d"` in `geometryTypes`, or a `skippedReasons` entry if the declared output path cannot currently bake `Point3d` list values.

If this live test fails for a runtime transport reason, do not add a broad coercion/enforcement layer in this slice. Keep Tasks 4 and 5 scoped to guidance, record the exact bake failure in the final answer, and open/attach evidence to issue #155 for a second slice.

## Task 4: Update MCP Tool Guidance

**Files:**
- Modify: `mcp_server/src/rook/server.py`

- [ ] **Step 1: Update the `gh_create_python_script` description**

In `mcp_server/src/rook/server.py`, find the `Tool(name="gh_create_python_script", ...)` description. Replace the current single-point example section with this text:

```text
For geometry outputs, declare rich output pins with a concrete GH/Rhino geometry
type and the correct access mode, then assign RhinoCommon geometry values to the
matching output variables. A list-access geometry output should be a plain Python
list of RhinoCommon values:

{
  "code": "import Rhino.Geometry as rg\nPoints = [rg.Point3d(0, 0, 0), rg.Point3d(1, 0, 0), rg.Point3d(2, 0, 0)]",
  "pins_in": [],
  "pins_out": [{"name": "Points", "type": "Point3d", "access": "list"}],
  "name": "Point List"
}

Other geometry output pin examples:
- {"name": "Curves", "type": "Curve", "access": "list"}
- {"name": "Breps", "type": "Brep", "access": "list"}
- {"name": "Meshes", "type": "Mesh", "access": "list"}

Do not assign coordinate dictionaries, JSON strings, wrapper/debug objects, or
arbitrary Python objects when the intended output is GH/Rhino geometry.
```

Keep the existing back-compat, single-shot, and common-type text above this section.

- [ ] **Step 2: Update `gh_create_python_script` `pins_out` schema description**

Change the `pins_out` property description for `gh_create_python_script` to:

```python
"description": 'Output pin definitions as "Name:Type" strings or pin objects, e.g. [{"name": "Points", "type": "Point3d", "access": "list"}]. For geometry outputs, prefer pin objects with explicit type/access and assign RhinoCommon values to matching output variables.',
```

- [ ] **Step 3: Update the unified `gh_create_script` description**

In the `Tool(name="gh_create_script", ...)` description, insert this section after the common-types paragraph and before `Example (Python):`:

```text
Python geometry output rule:
When the semantic output is geometry, declare rich output pins with concrete
GH/Rhino geometry types and assign real RhinoCommon values. For example:

{
  "language": "python",
  "code": "import Rhino.Geometry as rg\nPoints = [rg.Point3d(0, 0, 0), rg.Point3d(1, 0, 0), rg.Point3d(2, 0, 0)]",
  "pins_in": [],
  "pins_out": [{"name": "Points", "type": "Point3d", "access": "list"}],
  "name": "Point List"
}

Do not assign coordinate dictionaries, JSON strings, wrapper/debug objects, or
arbitrary Python objects when the intended output is GH/Rhino geometry.
```

Then replace the existing Python example with the same `Point List` example above.

- [ ] **Step 4: Update `gh_create_script` `pins_out` schema description**

Change the `pins_out` property description for `gh_create_script` to:

```python
"description": 'Output pin definitions as "Name:Type" strings or pin objects, e.g. [{"name": "Points", "type": "Point3d", "access": "list"}]. For Python geometry outputs, prefer pin objects with explicit type/access and assign RhinoCommon values to matching output variables.',
```

- [ ] **Step 5: Run the MCP contract test**

Run:

```powershell
python -m pytest mcp_server/tests/test_server_contract_hardening.py::test_gh_script_tool_descriptions_teach_usable_geometry_outputs -q
```

Expected after implementation: `1 passed`.

- [ ] **Step 6: Commit the tool guidance and contract test**

Run the pre-commit scope check:

```powershell
git status --short
git diff --stat HEAD
```

Expected: only `mcp_server/src/rook/server.py` and `mcp_server/tests/test_server_contract_hardening.py` are new implementation changes for this commit. Pre-existing unrelated files may still appear and must not be staged.

Run:

```powershell
git add mcp_server/src/rook/server.py mcp_server/tests/test_server_contract_hardening.py
git commit -m "test: cover gh python geometry output guidance"
```

Expected: a commit containing only the server guidance and its contract test. Do not stage `AGENTS.md`, `docs/rook_docs/work-queue.md`, or plan/spec files unless the user explicitly asks.

## Task 5: Update Persona and Prompt Guidance

**Files:**
- Modify: `mcp_server/src/rook/agent/personas/scripter/role.md`
- Modify: `mcp_server/src/rook/agent/personas/worker/role.md`
- Modify: `mcp_server/src/rook/agent/personas/architect/role.md`
- Modify: `mcp_server/src/rook/agent/prompts/WORKER.md`
- Modify: `mcp_server/tests/test_chat_prompt_builder.py`

- [ ] **Step 1: Update the scripter output convention**

In `mcp_server/src/rook/agent/personas/scripter/role.md`, replace the current `### Python 3 — Output Convention` section with:

````markdown
### Python 3 — Output Convention

Geometry outputs must be usable GH/Rhino values, not Python blobs.

For geometry outputs, declare rich output pins with a concrete GH/Rhino geometry
type and matching access, then assign RhinoCommon values to those output variables:

```python
import Rhino.Geometry as rg
Points = [rg.Point3d(0, 0, 0), rg.Point3d(1, 0, 0), rg.Point3d(2, 0, 0)]
```

Use output pins like:

```json
[{"name": "Points", "type": "Point3d", "access": "list"}]
```

Do not output coordinate dictionaries, JSON strings, wrapper/debug objects, or
arbitrary Python objects when the intended result is geometry. Use DataTree[object]
only when you intentionally need tree topology; a plain Python list of RhinoCommon
geometry values is the first choice for list-access geometry outputs.
````

Make sure the old sentence `Python lists must be wrapped in `DataTree[object]()` for GH to display each item` is removed.

- [ ] **Step 2: Add worker persona guidance**

In `mcp_server/src/rook/agent/personas/worker/role.md`, add this block near the existing script-component guidance:

```markdown
Geometry outputs: when a Python script component outputs geometry, declare rich
`pins_out` entries such as `{"name": "Points", "type": "Point3d", "access": "list"}`
and assign real RhinoCommon values, for example
`Points = [rg.Point3d(0, 0, 0), rg.Point3d(1, 0, 0), rg.Point3d(2, 0, 0)]`.
Do not output coordinate dictionaries, JSON strings, wrapper/debug objects, or
arbitrary Python objects for geometry. Use DataTree[object] only when you
intentionally need tree topology.
```

- [ ] **Step 3: Add architect persona guidance**

In `mcp_server/src/rook/agent/personas/architect/role.md`, add this block near the existing `gh_create_script` or Grasshopper scripting guidance:

```markdown
Geometry outputs: specify script outputs with typed `pins_out` object forms such
as `{"name": "Points", "type": "Point3d", "access": "list"}` and require scripts
to assign RhinoCommon values such as
`Points = [rg.Point3d(0, 0, 0), rg.Point3d(1, 0, 0), rg.Point3d(2, 0, 0)]`.
Do not accept coordinate dictionaries, JSON strings, wrapper/debug objects, or
arbitrary Python objects when the semantic output is GH/Rhino geometry. Use
DataTree[object] only when intentional tree topology is required.
```

- [ ] **Step 4: Update the worker snapshot prompt**

In `mcp_server/src/rook/agent/prompts/WORKER.md`, add the same block as the worker persona:

```markdown
Geometry outputs: when a Python script component outputs geometry, declare rich
`pins_out` entries such as `{"name": "Points", "type": "Point3d", "access": "list"}`
and assign real RhinoCommon values, for example
`Points = [rg.Point3d(0, 0, 0), rg.Point3d(1, 0, 0), rg.Point3d(2, 0, 0)]`.
Do not output coordinate dictionaries, JSON strings, wrapper/debug objects, or
arbitrary Python objects for geometry. Use DataTree[object] only when you
intentionally need tree topology.
```

- [ ] **Step 5: Run the prompt contract tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_chat_prompt_builder.py::test_persona_prompt_script_geometry_outputs_are_rhinocommon_values mcp_server/tests/test_chat_prompt_builder.py::test_scripter_prompt_no_longer_requires_datatree_for_all_python_lists -q
```

Expected after implementation: `4 passed`.

- [ ] **Step 6: Run the existing prompt routing regression**

Run:

```powershell
python -m pytest mcp_server/tests/test_chat_prompt_builder.py::test_persona_prompt_script_tool_language_is_capability_accurate -q
```

Expected after implementation: `3 passed`.

- [ ] **Step 7: Commit persona and prompt guidance**

Run the pre-commit scope check:

```powershell
git status --short
git diff --stat HEAD
```

Expected: only the persona/prompt files and `mcp_server/tests/test_chat_prompt_builder.py` are new implementation changes for this commit. Pre-existing unrelated files may still appear and must not be staged.

Run:

```powershell
git add mcp_server/src/rook/agent/personas/scripter/role.md mcp_server/src/rook/agent/personas/worker/role.md mcp_server/src/rook/agent/personas/architect/role.md mcp_server/src/rook/agent/prompts/WORKER.md mcp_server/tests/test_chat_prompt_builder.py
git commit -m "docs: guide gh python geometry outputs"
```

Expected: a commit containing only prompt/persona files and the prompt tests.

## Task 6: Verify the Live Regression and Narrow Scope

**Files:**
- Modify: `mcp_server/tests/test_gh_create_script_live.py`

- [ ] **Step 1: Run the live bake test**

Run with Rhino open, Rook loaded, and Grasshopper available:

```powershell
python -m pytest -m requires_rhino mcp_server/tests/test_gh_create_script_live.py::test_gh_create_script_python_point_list_bakes_as_geometry -q
```

Expected if the existing output path works:

```text
1 passed
```

Expected data shape if debugging is needed:

```python
{
    "success": True,
    "data": {
        "totalBaked": 3,
        "perTarget": [
            {
                "outputIndex": 1,
                "bakedCount": 3,
                "geometryTypes": ["Point3d"],
            }
        ],
    },
}
```

- [ ] **Step 2: Commit the live regression if it passes or if it exposes a useful current failure**

Run the pre-commit scope check:

```powershell
git status --short
git diff --stat HEAD
```

Expected: only `mcp_server/tests/test_gh_create_script_live.py` is the new implementation change for this commit. Pre-existing unrelated files may still appear and must not be staged.

Run:

```powershell
git add mcp_server/tests/test_gh_create_script_live.py
git commit -m "test: prove gh python point outputs bake"
```

Expected: a commit containing only `mcp_server/tests/test_gh_create_script_live.py`.

If the live test fails because `Point3d` list output cannot be baked despite the script assigning real `rg.Point3d` values, still commit the regression only if the project convention allows known-failing live tests to be committed behind `requires_rhino`. Otherwise leave the test uncommitted and report the exact failure evidence in issue #155. Do not implement runtime coercion, C# handler refactors, or bake-service changes inside this plan.

## Task 7: Final Verification

**Files:**
- Read-only verification across modified Python and markdown files.

- [ ] **Step 1: Run focused non-live tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_server_contract_hardening.py mcp_server/tests/test_chat_prompt_builder.py -q
```

Expected: all selected tests pass. The exact count can vary as the files evolve, but there should be no failures.

- [ ] **Step 2: Run live regression**

Run with Rhino open, Rook loaded, and Grasshopper available:

```powershell
python -m pytest -m requires_rhino mcp_server/tests/test_gh_create_script_live.py::test_gh_create_script_python_point_list_bakes_as_geometry -q
```

Expected: `1 passed`.

- [ ] **Step 3: Inspect git status without staging unrelated work**

Run:

```powershell
git status --short
```

Expected:
- The intended commits are present on the current branch.
- Pre-existing unrelated dirty files such as `AGENTS.md` and `docs/rook_docs/work-queue.md` may still appear and must not be reverted or staged.
- The implementation should not modify `.vcxproj`, `.vcxproj.filters`, native C++ files, managed C# handlers, or `BakeService.cs` for this first slice.

- [ ] **Step 4: Final response evidence**

Report:

```text
Implemented guidance for gh_create_script/gh_create_python_script and worker/architect/scripter prompt surfaces.
Added contract tests for tool and prompt guidance.
Added live regression that creates a Python component with pins_out [{"name":"Points","type":"Point3d","access":"list"}], assigns rg.Point3d values, and verifies gh_bake_output reports totalBaked == 3, perTarget[0].bakedCount == 3, and geometryTypes contains Point3d.
Verification:
- python -m pytest mcp_server/tests/test_server_contract_hardening.py mcp_server/tests/test_chat_prompt_builder.py -q
- python -m pytest -m requires_rhino mcp_server/tests/test_gh_create_script_live.py::test_gh_create_script_python_point_list_bakes_as_geometry -q
```

If the live test could not be run, say exactly that and do not claim downstream proof. If it failed, include `totalBaked`, `perTarget`, and `skippedReasons` from the failure output and explicitly state runtime enforcement remains outside this slice.

## Self-Review

- Spec coverage: covered MCP tool descriptions/schema examples in Task 4, persona and prompt surfaces in Task 5, live `Point3d` list downstream bake regression in Tasks 3 and 6, and non-goals by explicitly excluding runtime enforcement and C#/managed bake changes.
- Placeholder scan: no steps rely on unspecified implementation; each code/test step names exact files, snippets, commands, and expected results.
- Type consistency: test and guidance all use `{"name": "Points", "type": "Point3d", "access": "list"}`, script output `Points = [rg.Point3d(...)]`, bake target `outputIndex: 1` with `outputName: "Points"`, and assertions on `data.totalBaked`, `data.perTarget[0].bakedCount`, and `geometryTypes` containing `"Point3d"`.
