# D4 `model_id` Contract Honesty Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the `rhino_2d_to_3d_submit` MCP schema match the C# parser — `model_id` required, no false "default Hunyuan rapid" promise — without changing behavior.

**Architecture:** One TDD task, MCP layer only: update the schema test to the new contract (fails), then align `server.py`'s submit-tool schema (`required` + `model_id` description), then a grep guard against the stale wording reappearing. The C# parser already enforces `model_id`, so this is pure schema↔parser alignment.

**Tech Stack:** Python (MCP server `mcp_server/src/rook/server.py`), pytest + pytest-asyncio.

## Global Constraints

- MCP layer only. Do **not** touch the C# parser (`ReconstructionSubmitRequestParser.cs` — already correct), add any default/fallback model-selection logic, or change behavior.
- Leave the frozen historical docs `docs/superpowers/specs|plans/2026-06-19-reconstruction-2d-to-3d-*.md` alone.
- New `model_id` description, exact: `Full fal model id returned by rhino_2d_to_3d_models. Required; no implicit default.`
- Test guard rejects the stale phrases `default Hunyuan` and `when omitted`; it must **allow** `no implicit default` (which contains "default") — do NOT assert a bare absence of "default".
- D1/D2/D3 are a separate later slice — out of scope.

**Reference:** spec at `docs/superpowers/specs/2026-06-21-reconstruction-model-id-required-design.md`.

**Running the test (no worktree MCP venv):** use a Python that has `mcp` + `pytest` + `pytest-asyncio` and imports the **worktree's** `rook` (not an installed copy). From the worktree root, the reliable form is to put the worktree `mcp_server/src` first on `PYTHONPATH` and use the repo MCP venv interpreter, e.g.:
```
PYTHONPATH=mcp_server/src <python-with-mcp-pytest> -m pytest mcp_server/tests/test_reconstruction_mcp_tools.py -q
```
(On this machine the repo dev MCP venv at `C:\Users\aryan\source\repos\Rook\mcp_server\.venv\Scripts\python.exe` carries the deps; `PYTHONPATH` makes it import the worktree source.) Confirm the test imports the worktree's `server` (the assertion sees the edited schema) — if it sees the old schema, `PYTHONPATH` isn't taking precedence.

---

## File Structure

- **Modify** `mcp_server/src/rook/server.py` — the `rhino_2d_to_3d_submit` `Tool` (≈12674–12697): `required` list + `model_id` property description.
- **Modify** `mcp_server/tests/test_reconstruction_mcp_tools.py` — the submit-schema test (≈48–58).

---

### Task 1: `model_id` required in the submit schema (TDD)

**Files:**
- Modify: `mcp_server/src/rook/server.py` (`rhino_2d_to_3d_submit` Tool)
- Modify: `mcp_server/tests/test_reconstruction_mcp_tools.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `rhino_2d_to_3d_submit.inputSchema.required == ["source_artifact_id", "model_id"]`; `model_id` description = the exact new one-liner.

- [ ] **Step 1: Update the test to the new contract (rename + assertions)**

In `mcp_server/tests/test_reconstruction_mcp_tools.py`, replace:
```python
@pytest.mark.asyncio
async def test_reconstruction_submit_requires_source_artifact_id_only_for_identity():
    tools = await server.list_tools()
    submit = {t.name: t for t in tools}["rhino_2d_to_3d_submit"]

    assert set(submit.inputSchema.get("required", [])) == {"source_artifact_id"}
    assert "source_artifact_id" in submit.inputSchema["properties"]
    assert "path" not in submit.inputSchema["properties"]
    assert "image_path" not in submit.inputSchema["properties"]
    assert "local_path" not in submit.inputSchema["properties"]
```
with:
```python
@pytest.mark.asyncio
async def test_reconstruction_submit_requires_source_artifact_id_and_model_id():
    tools = await server.list_tools()
    submit = {t.name: t for t in tools}["rhino_2d_to_3d_submit"]

    assert set(submit.inputSchema.get("required", [])) == {"source_artifact_id", "model_id"}
    assert "source_artifact_id" in submit.inputSchema["properties"]
    assert "path" not in submit.inputSchema["properties"]
    assert "image_path" not in submit.inputSchema["properties"]
    assert "local_path" not in submit.inputSchema["properties"]

    # model_id must advertise the enforced contract (required; no default promise).
    # Reject the stale "default Hunyuan ... when omitted" wording. The explicit
    # phrase "no implicit default" is allowed even though it contains "default",
    # so do NOT assert a bare absence of the word "default".
    model_id_desc = submit.inputSchema["properties"]["model_id"]["description"]
    assert "default Hunyuan" not in model_id_desc
    assert "when omitted" not in model_id_desc
    assert "no implicit default" in model_id_desc
    assert "rhino_2d_to_3d_models" in model_id_desc
```

- [ ] **Step 2: Run the test to verify it fails**

Run (see Global Constraints for the interpreter):
```
PYTHONPATH=mcp_server/src <python> -m pytest "mcp_server/tests/test_reconstruction_mcp_tools.py::test_reconstruction_submit_requires_source_artifact_id_and_model_id" -q
```
Expected: FAIL — current schema has `required == {"source_artifact_id"}` and the description still contains `default Hunyuan` / `when omitted`.

- [ ] **Step 3: Align the submit-tool schema**

In `mcp_server/src/rook/server.py`, in the `rhino_2d_to_3d_submit` Tool:

(a) Replace the `model_id` property line:
```python
                    "model_id": {"type": "string", "description": "Full fal model id; default Hunyuan rapid when omitted by managed contract."},
```
with:
```python
                    "model_id": {"type": "string", "description": "Full fal model id returned by rhino_2d_to_3d_models. Required; no implicit default."},
```

(b) Replace the submit tool's `required` line:
```python
                "required": ["source_artifact_id"],
```
with:
```python
                "required": ["source_artifact_id", "model_id"],
```
(Apply this to the `rhino_2d_to_3d_submit` Tool specifically — other tools have their own `required` lines.)

- [ ] **Step 4: Run the test to verify it passes**

Run:
```
PYTHONPATH=mcp_server/src <python> -m pytest "mcp_server/tests/test_reconstruction_mcp_tools.py::test_reconstruction_submit_requires_source_artifact_id_and_model_id" -q
```
Expected: PASS.

- [ ] **Step 5: Grep guard — stale wording is gone, new phrase present**

Run:
```
rg -n "default Hunyuan|when omitted" mcp_server/src/rook/server.py mcp_server/tests/test_reconstruction_mcp_tools.py
```
Expected: **no output** (the only prior occurrences were the model_id line; both phrases are now gone, and the test rejects them by absence-assertion, not by quoting them as a substring to match).

Run:
```
rg -n "no implicit default" mcp_server/src/rook/server.py
```
Expected: exactly one hit — the `model_id` description.

- [ ] **Step 6: Run the full reconstruction MCP test file**

Run:
```
PYTHONPATH=mcp_server/src <python> -m pytest mcp_server/tests/test_reconstruction_mcp_tools.py -q
```
Expected: PASS — all reconstruction MCP tests green (17), including the call-test that already passes a `model_id`.

- [ ] **Step 7: Commit**

```bash
git add mcp_server/src/rook/server.py mcp_server/tests/test_reconstruction_mcp_tools.py
git commit -m "fix(reconstruction): require model_id in rhino_2d_to_3d_submit schema; drop false default promise"
```

---

## Notes for the PR

- Open a ready (non-draft) PR into `main`; preserve commit history (no squash unless approved); do not merge locally without review.
- No C# touched → no C# suite needed. The proof is the reconstruction MCP test file green + the grep guard.
- Expected commits on the branch: spec (2) → Task 1.
