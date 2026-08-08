# Prime Agent Explicit Rook Gateway Interface Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and inertly verify one disposable V4 Prime qualification whose supported `rook_full` API is exactly `search`, `read`, and `call`.

**Architecture:** A fresh sibling copies the reviewed V3 runtime and evidence machinery, but replaces the model-facing adapter affordance with three module functions over one private, byte-identical stdio integration. The functions delegate only to Rook's canonical progressive-disclosure meta-tools. Product repositories, Rook policy, schemas, dispatch, targeting, and Prime runtime remain unchanged.

**Tech Stack:** Windows PowerShell 7, Python 3.11, `unittest`, Prime Agent runtime `0.1.0`, MCP Python SDK `1.28.0`, local Ollama configuration, deployed Rook stdio MCP.

## Global Constraints

- Source: `C:/Users/bring/AppData/Local/Temp/prime-rook-full-mutation-qualification-v3`.
- Destination: `C:/Users/bring/AppData/Local/Temp/prime-rook-full-mutation-qualification-v4`.
- Preserve every V3 artifact and evidence byte-for-byte.
- No Rook or Prime repository implementation changes.
- Supported V4 module API: `__all__ = ("search", "read", "call")`.
- No module-level `__getattr__`, exported integration instance, public `list_tools()` or `call_tool()`, or arbitrary dynamic MCP methods.
- The private integration retains inherited lower-level methods; no security-grade inaccessibility claim is made.
- `_open_session()` and transport custody remain byte-identical to V3.
- No copied schema, catalog, cache, retry, fallback, native Prime extension, performance work, critic, or witness-specific instruction.
- Existing MCP parsing, Rook profile, targeting, validation, dispatch, and tool receipts remain authoritative.
- Implementation and inert review perform no Prime, Ollama, Rook MCP, Rhino, or Grasshopper contact.
- Live execution requires a fresh row and separate one-shot authorization after independent pre-contact review.

## File Map

Disposable V4 files created or changed relative to V3:

- `agent/skills/rook-full/src/rook_full/__init__.py` — private stdio integration and three public wrappers.
- `agent/skills/prime-execute-grasshopper/SKILL.md` — explicit Prime invocation preamble; reviewed execution body unchanged.
- `operator/final_inspection.py` — replace the removed dynamic meta-tool attribute with public `call()`; preserve all evidence behavior.
- `operator/test_adapter.py` — causal public-surface/delegation tests plus existing inert custody suite.
- `operator/offline-install-commands.txt` — V4 sibling path only.
- `operator/manifest.json` — hashes of the reviewed static V4 artifacts; no row before live preflight.

Copied unchanged from V3:

- `agent/models.json`
- `agent/settings.json`
- `agent/skills/prime-execute-grasshopper/references/checkpoint-protocol.md`
- `agent/skills/rook-full/pyproject.toml`
- `cache/prime_agent_runtime-0.1.0-py3-none-any.whl`
- `operator/kernel-requirements.txt`
- `operator/run.ps1`

## Task 1: Construct And Inertly Verify V4

**Files:**

- Create: `C:/Users/bring/AppData/Local/Temp/prime-rook-full-mutation-qualification-v4/**`
- Source: `C:/Users/bring/AppData/Local/Temp/prime-rook-full-mutation-qualification-v3/**`
- Test: `C:/Users/bring/AppData/Local/Temp/prime-rook-full-mutation-qualification-v4/operator/test_adapter.py`

**Interfaces:**

- Consumes: reviewed V3 adapter, execution body, kernel requirements, launcher, inspector, and evidence contract.
- Produces: `rook_full.search(query: str)`, `rook_full.read(name: str)`, and `rook_full.call(name: str, arguments: dict)`.
- Delegates: one private integration `call_tool(name: str, arguments: dict)` call per public invocation.
- Preserves: the exact `call()` arguments object through private integration ingress.
- Returns: the exact object returned at private integration egress; exceptions propagate unchanged.

- [ ] **Step 1: Reconfirm V3 custody and require an absent V4 root**

Run:

```powershell
$V3 = 'C:/Users/bring/AppData/Local/Temp/prime-rook-full-mutation-qualification-v3'
$V4 = 'C:/Users/bring/AppData/Local/Temp/prime-rook-full-mutation-qualification-v4'

if (Test-Path -LiteralPath $V4) { throw 'V4 root already exists' }

$Expected = @{
    'operator/row.json' = 'DEB36FBF19E98B81749E85CFC071356B9F9E0AA46E2CA5107D6623BDADED8140'
    'operator/prime.jsonl' = 'A81B6620B34614D3761522B7A34BAD4F797AA6C5677E3DFB435C806B777903FE'
    'agent/sessions/019fe25e-91f1-7678-8ea5-ff710161d024.jsonl' = 'E37CF55AE04EB3D3796CFD290F70814399F77EEE1A3ECC28133FB41BF832ADA6'
    'operator/final-inspection.jsonl' = '21993446CC707EC7FB82A820CBBEAD577599AD050591BB5C929E010D4B1741B7'
    'operator/stderr.txt' = 'E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855'
}
foreach ($entry in $Expected.GetEnumerator()) {
    $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath "$V3/$($entry.Key)").Hash
    if ($actual -cne $entry.Value) { throw "V3 evidence drift: $($entry.Key)" }
}
```

Expected: command exits `0`; every V3 evidence hash matches; V4 does not exist.

- [ ] **Step 2: Create the clean sibling and copy only reviewed static inputs**

Create directories and copy this exact allowlist:

```powershell
$Static = @(
    'agent/models.json',
    'agent/settings.json',
    'agent/skills/prime-execute-grasshopper/SKILL.md',
    'agent/skills/prime-execute-grasshopper/references/checkpoint-protocol.md',
    'agent/skills/rook-full/pyproject.toml',
    'agent/skills/rook-full/src/rook_full/__init__.py',
    'cache/prime_agent_runtime-0.1.0-py3-none-any.whl',
    'operator/final_inspection.py',
    'operator/kernel-requirements.txt',
    'operator/offline-install-commands.txt',
    'operator/run.ps1',
    'operator/test_adapter.py'
)
foreach ($relative in $Static) {
    $destination = Join-Path $V4 $relative
    New-Item -ItemType Directory -Force -Path (Split-Path $destination) | Out-Null
    Copy-Item -LiteralPath (Join-Path $V3 $relative) -Destination $destination
}
New-Item -ItemType Directory -Force -Path "$V4/agent/sessions" | Out-Null
```

Do not copy V3 `row.json`, sessions, logs, evidence, kernel state, or virtual environment.

- [ ] **Step 3: Write the V4 public-surface and delegation tests before changing the adapter**

First bind the copied test suite to V4 while retaining V3 as its byte-parity source:

```python
ROOT = Path("C:/Users/bring/AppData/Local/Temp/prime-rook-full-mutation-qualification-v4")
V3_ROOT = Path("C:/Users/bring/AppData/Local/Temp/prime-rook-full-mutation-qualification-v3")
ADAPTER = ROOT / "agent/skills/rook-full/src/rook_full/__init__.py"
SKILL = ROOT / "agent/skills/prime-execute-grasshopper/SKILL.md"
V3_ADAPTER = V3_ROOT / "agent/skills/rook-full/src/rook_full/__init__.py"
V3_SKILL = V3_ROOT / "agent/skills/prime-execute-grasshopper/SKILL.md"
```

Update existing transport tests to call `module._integration._open_session(stack)` instead of the removed exported `module.rook_full`. Replace the old V3 preamble literal with the exact V4 preamble from Step 6; retain every launcher, row, evidence, short-write, and final-inspection assertion.

Then add a causal fake and an isolated async test class:

```python
class _PrivateIntegrationFake:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        if self.error is not None:
            raise self.error
        return self.result


class ExplicitGatewaySurfaceTests(unittest.IsolatedAsyncioTestCase):
    def module(self):
        return _load_module(ADAPTER, "rook_full_v4_surface")

    async def test_supported_public_surface_is_exact(self):
        module = self.module()
        self.assertEqual(module.__all__, ("search", "read", "call"))
        self.assertNotIn("__getattr__", module.__dict__)
        self.assertNotIn("rook_full", module.__dict__)
        self.assertNotIn("list_tools", module.__dict__)
        self.assertNotIn("call_tool", module.__dict__)

    async def test_public_functions_delegate_exact_canonical_envelopes(self):
        module = self.module()
        returned = object()
        fake = _PrivateIntegrationFake(result=returned)
        module._integration = fake
        arguments = {"epoch": 7, "connect": ["C1.O0>C2.I0"]}

        self.assertIs(await module.search("gh_edit"), returned)
        self.assertIs(await module.read("gh_edit"), returned)
        self.assertIs(await module.call("gh_edit", arguments), returned)
        self.assertEqual(fake.calls[0], ("rook_tools_search", {"query": "gh_edit"}))
        self.assertEqual(fake.calls[1], ("rook_tools_read", {"name": "gh_edit"}))
        self.assertEqual(fake.calls[2][0], "rook_tools_call")
        self.assertEqual(fake.calls[2][1]["name"], "gh_edit")
        self.assertIs(fake.calls[2][1]["arguments"], arguments)

    async def test_result_and_exception_are_not_reinterpreted(self):
        module = self.module()
        refused = {"error": "readonly_profile"}
        module._integration = _PrivateIntegrationFake(result=refused)
        self.assertIs(await module.call("gh_edit", {}), refused)

        error = RuntimeError("canonical refusal")
        module._integration = _PrivateIntegrationFake(error=error)
        with self.assertRaises(RuntimeError) as raised:
            await module.search("gh_edit")
        self.assertIs(raised.exception, error)
```

Add one inspector-boundary regression using a fake module whose only async function is `call(name, arguments)`:

```python
import sys
import types


async def test_snapshot_uses_public_call_once(self):
    module = self._module()
    calls = []
    sentinel = object()

    async def call(name, arguments):
        calls.append((name, arguments))
        return sentinel

    fake_module = types.SimpleNamespace(call=call)
    with patch.dict(sys.modules, {"rook_full": fake_module}):
        returned = await module._call_snapshot()

    self.assertIs(returned, sentinel)
    self.assertEqual(
        calls,
        [("gh_snapshot", {"include_data": True, "max_preview_items": 3})],
    )
```

and returns the fake's exact sentinel object.

Add a raw method-source helper using AST line bounds and `read_bytes().splitlines(keepends=True)`, then require V3 `RookFull._open_session` bytes to equal V4 `_RookFull._open_session` bytes. Extend the existing skill test so the preamble contains `rook_full.search`, `rook_full.read`, and `rook_full.call`, while bytes from `# Execute Grasshopper Work` onward equal V3 exactly.

```python
import ast


def _method_bytes(path: Path, class_name: str, method_name: str) -> bytes:
    raw = path.read_bytes()
    tree = ast.parse(raw.decode("utf-8", errors="strict"))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name == method_name:
                    lines = raw.splitlines(keepends=True)
                    return b"".join(lines[child.lineno - 1 : child.end_lineno])
    raise AssertionError(f"missing {class_name}.{method_name}")


def test_transport_method_and_execution_body_are_byte_identical(self):
    self.assertEqual(
        _method_bytes(V3_ADAPTER, "RookFull", "_open_session"),
        _method_bytes(ADAPTER, "_RookFull", "_open_session"),
    )
    marker = b"# Execute Grasshopper Work"
    current = SKILL.read_bytes()
    previous = V3_SKILL.read_bytes()
    self.assertEqual(current[current.index(marker) :], previous[previous.index(marker) :])
    preamble = current[: current.index(marker)].decode("utf-8", errors="strict")
    self.assertIn("rook_full.search", preamble)
    self.assertIn("rook_full.read", preamble)
    self.assertIn("rook_full.call", preamble)
```

- [ ] **Step 4: Run the focused tests and verify RED**

Run:

```powershell
$Python = "$V3/kernel-venv/Scripts/python.exe"
& $Python "$V4/operator/test_adapter.py" -v
```

Expected: FAIL because the copied V3 adapter has no exact `__all__`, retains module `__getattr__`/the exported `rook_full` instance, and the V3 skill preamble does not use the new public functions. Existing custody tests must not fail for unrelated reasons.

- [ ] **Step 5: Implement only the three-function adapter surface**

Preserve the copied imports, constants, environment helpers, and `_open_session()` bytes. Rename the class and instance privately, delete module `__getattr__`, and add exactly:

```python
__all__ = ("search", "read", "call")


class _RookFull(McpIntegration):
    server = "rook-full"

    async def _open_session(self, stack: AsyncExitStack) -> ClientSession:
        env = {**_STATIC_ENV, **{name: _positive_environment_value(name) for name in _TARGET_ENV}}
        parameters = StdioServerParameters(
            command=_COMMAND,
            args=["-m", "rook"],
            cwd=_CWD,
            env=env,
        )
        errlog = stack.enter_context(open(os.devnull, "w", encoding="utf-8"))
        read, write = await stack.enter_async_context(stdio_client(parameters, errlog=errlog))
        session = await stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        return session


_integration = _RookFull()


async def search(query: str):
    return await _integration.call_tool("rook_tools_search", {"query": query})


async def read(name: str):
    return await _integration.call_tool("rook_tools_read", {"name": name})


async def call(name: str, arguments: dict):
    return await _integration.call_tool(
        "rook_tools_call",
        {"name": name, "arguments": arguments},
    )
```

Do not add type coercion, validation, exception handling, result parsing, caching, retry, or fallback.

- [ ] **Step 6: Replace only the V4 skill compatibility preamble and inspector invocation**

Keep the V3 frontmatter meaning and replace its compatibility section with an executable positive recipe:

````markdown
# Prime invocation compatibility

This is a live Grasshopper execution request. Import `rook_full` in IPython.

Use the supported Python capability interface:

```python
import rook_full

search_result = await rook_full.search("gh_edit")
tool_contract = await rook_full.read("gh_edit")
tool_result = await rook_full.call("gh_edit", edit_arguments)
```

The currently pinned Grasshopper document is the only execution target.
Every inspection or mutation must use this interface and returned Rook evidence.
````

Append V3 bytes from `# Execute Grasshopper Work` onward without modification. Do not mention this witness's component choices or Y/Z behavior.

In `operator/final_inspection.py`, replace only:

```python
return await rook_full.rook_tools_call(
    name="gh_snapshot",
    arguments={"include_data": True, "max_preview_items": 3},
)
```

with:

```python
return await rook_full.call(
    "gh_snapshot",
    {"include_data": True, "max_preview_items": 3},
)
```

- [ ] **Step 7: Recreate the frozen kernel without network contact**

Change only the V3-to-V4 root in `operator/offline-install-commands.txt`, then run its commands with `--offline` on every dependency operation:

```powershell
$Root = 'C:/Users/bring/AppData/Local/Temp/prime-rook-full-mutation-qualification-v4'
$UvCache = 'C:/Users/bring/AppData/Local/uv/cache'
uv venv --offline --python 3.11 "$Root/kernel-venv"
uv pip install --offline --cache-dir $UvCache --find-links "$Root/cache" `
  --python "$Root/kernel-venv/Scripts/python.exe" `
  --requirements "$Root/operator/kernel-requirements.txt"
uv pip install --offline --cache-dir $UvCache `
  --python "$Root/kernel-venv/Scripts/python.exe" `
  --editable "$Root/agent/skills/rook-full"
uv pip install --offline --cache-dir $UvCache `
  --python "$Root/kernel-venv/Scripts/python.exe" `
  starlette==1.5.0
```

If any cached dependency is unavailable, stop. Do not contact a package index.

- [ ] **Step 8: Run GREEN verification and static custody checks**

Run:

```powershell
$Python = "$V4/kernel-venv/Scripts/python.exe"
& $Python "$V4/operator/test_adapter.py" -v
& $Python -m py_compile `
  "$V4/agent/skills/rook-full/src/rook_full/__init__.py" `
  "$V4/operator/final_inspection.py" `
  "$V4/operator/test_adapter.py"
```

Expected: all tests pass and compilation exits `0` with no network, model, MCP, Rhino, or Grasshopper contact.

Also inspect source and require:

```powershell
rg -n '__getattr__|def list_tools|def call_tool|rook_tools_[a-z_]+\(' `
  "$V4/agent/skills/rook-full/src/rook_full/__init__.py"
```

Expected: no module `__getattr__`, public lower-level method, dynamic tool function, copied schema, or copied catalog. The three canonical meta-tool names may appear only as literal delegation targets inside `search`, `read`, and `call`.

- [ ] **Step 9: Freeze the static manifest and prove absence of live evidence**

Hash exactly the 12 static files listed in **File Map**, write uppercase SHA-256 values to `operator/manifest.json`, then independently recompute every entry. Do not add `operator/row.json` yet.

```powershell
$ManifestFiles = @(
    'agent/models.json',
    'agent/settings.json',
    'agent/skills/prime-execute-grasshopper/references/checkpoint-protocol.md',
    'agent/skills/prime-execute-grasshopper/SKILL.md',
    'agent/skills/rook-full/pyproject.toml',
    'agent/skills/rook-full/src/rook_full/__init__.py',
    'cache/prime_agent_runtime-0.1.0-py3-none-any.whl',
    'operator/final_inspection.py',
    'operator/kernel-requirements.txt',
    'operator/offline-install-commands.txt',
    'operator/run.ps1',
    'operator/test_adapter.py'
)
$Manifest = [ordered]@{}
foreach ($relative in $ManifestFiles) {
    $Manifest[$relative] = (Get-FileHash -Algorithm SHA256 -LiteralPath "$V4/$relative").Hash
}
[System.IO.File]::WriteAllText(
    "$V4/operator/manifest.json",
    ($Manifest | ConvertTo-Json),
    [System.Text.UTF8Encoding]::new($false)
)
foreach ($entry in $Manifest.GetEnumerator()) {
    $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath "$V4/$($entry.Key)").Hash
    if ($actual -cne $entry.Value) { throw "manifest mismatch: $($entry.Key)" }
}
```

Require:

```powershell
Test-Path "$V4/operator/row.json"                 # False
Test-Path "$V4/operator/prime.jsonl"             # False
Test-Path "$V4/operator/stderr.txt"               # False
Test-Path "$V4/operator/final-inspection.jsonl"  # False
@(Get-ChildItem "$V4/agent/sessions" -File -ErrorAction SilentlyContinue).Count  # 0
```

Recompute the five V3 evidence hashes from Step 1 and require them to remain unchanged.

- [ ] **Step 10: Stop for mandatory independent pre-contact review**

Report:

- V4 root;
- exact changed-versus-copied file list;
- adapter, skill, inspector, manifest, and test hashes;
- `_open_session()` byte-parity result;
- execution-body and checkpoint byte-parity results;
- exact inert test count and command;
- Python compilation result;
- supported public surface and exact causal delegation results;
- absence of row and live evidence;
- unchanged V3 evidence hashes; and
- confirmation that Rook and Prime repositories remain unchanged.

Do not create a row, inspect the target, start Prime/Ollama/Rook MCP, or contact Rhino/Grasshopper. Wait for independent approval.

## Separately Authorized Live Continuation

This section is not authorized by Task 1 approval.

After independent pre-contact approval:

1. Prepare a fresh empty disposable Grasshopper canvas.
2. Corroborate the exact Rhino PID, native port/listener owner, and document serial.
3. Create `operator/row.json` using the exact V3 model, API base, intent, and evidence shape, substituting only V4 paths plus the fresh reviewed target integers.
4. Add the row hash to `manifest.json`, verify every hash, and rerun the inert suite.
5. Report the frozen row SHA-256 and confirm that no live evidence exists.
6. Obtain explicit authorization for exactly one V4 run.
7. Invoke `operator/run.ps1` exactly once with that row.
8. Do not rerun, retry, clean up, or take another inspection.
9. Retain and hash Prime JSONL, the native session, stderr, and the one final-inspection file.
10. Report these independent conclusions using the specification's evidence limits:
    - visible IPython calls to `rook_full.search/read/call`;
    - any attempted lower-level, dynamic, or private bypass;
    - whether the full tool catalog reached model context;
    - canonical delegation as a structural conclusion from the frozen adapter hash and inert tests, never as an independently observed live event;
    - final-inspection components, wires, previews, errors, and warnings;
    - adjustable Start/Step/Count and fixed-versus-adjustable Y/Z;
    - IPython count, elapsed time, and cumulative input/output tokens as observations only; and
    - every unsupported semantic claim as unproven.
11. Stop. A model comparison, performance change, native Prime extension, critic, or further prompt change is separate work.
