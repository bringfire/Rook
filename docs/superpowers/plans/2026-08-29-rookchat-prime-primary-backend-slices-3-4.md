# RookChat Prime Primary Backend Slices 3-4 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the opt-in Prime-backed RookChat path into a version-custodied Rook authoring session, first qualifying read-only observation and then one bounded mutating Grasshopper task with Prime-native goals and authentic receipt-fenced evidence.

**Architecture:** Prime remains the reasoning, saved-session, IPython, compaction, and goal owner. The RookChat broker binds one immutable runtime contract and target tuple to each new conversation, launches Prime with exactly the pinned goal skill and product `rook-full` package, and relays Prime-owned state without adding a second lifecycle. The product adapter opens one direct MCP/stdio child per call. Rook verifies live process, Rhino document, and captured Grasshopper document identity before the requested operation, and remains the sole mutation, solve, receipt, and evidence authority.

**Tech Stack:** TypeScript 7/Vitest (Prime RPC and CLI), Python 3.11/aiohttp/pytest/MCP stdio (Rook broker and adapter), C# net48/RhinoCommon/Grasshopper/xUnit (managed target boundary and panel), C++17/Rhino 8 SDK (native discovery), canonical JSON/SHA-256, Windows process ownership.

**Spec:** `docs/superpowers/specs/2026-08-29-rookchat-prime-primary-backend-slices-3-4-design.md`

## Global Constraints

- This plan is unimplemented. Its exact commit must receive independent review before Task 0 begins.
- The implementation `/goal` names the exact approved plan commit. Task 0 requires the Rook worktree to be clean at that literal commit and the Prime worktree to be clean at `7690c18479c909ddea67a34e86114f7f982179a8`.
- Existing registry v1 records retain their exact Slices 1-2 text-only meaning. They are never inferred, rewritten, or reopened as v2.
- Slice 3 uses a fresh `readonly` v2 conversation. Slice 4 uses a different fresh `full` v2 conversation. A running process, kernel, record, or target lock is never elevated.
- Prime owns reasoning, provider interaction, transcript, IPython, compaction, goal state, continuation, accounting, and completion. The broker does not classify requests, infer completion, or persist a shadow goal/task lifecycle.
- Rook owns live target admission, Rhino and Grasshopper identity truth, mutation, solve state, receipts, and host evidence. Goal state is guidance and qualification evidence, not a Rook gateway prerequisite.
- Effective Prime RLM maximum depth is exactly `0` with source `chat` for these slices. Subagents are deferred, not removed from Prime permanently.
- The only model-facing tool is `ipython`. The only admitted skills are the pinned Prime goal skill and one immutable product `rook-full` package. No ambient skills, extensions, context files, prompt templates, web, images, steering, or worker delegation are added.
- The broker passes the exact immutable `rook-full/SKILL.md` path through Prime's file-backed system-prompt option. It never parses, strips, wraps, or rewrites the file.
- The supported adapter path uses one fresh MCP/stdio child per call. Connection pooling, a broker MCP proxy, model-visible tokens, and automatic replay are out of scope.
- Product `panel_locked` custody mechanically governs the unmodified `rook_full` typed/composite path. Hostile IPython, raw transport, environment monkeypatching, and arbitrary Python containment remain explicit non-claims.
- `gh_document_new`, `gh_document_open`, and transitive `gh_learn_directory` are refused in `panel_locked` v1 before nested document-open dispatch. `rhino_execute` remains admitted but receives no Grasshopper containment claim and is disqualifying if used to inspect or alter Grasshopper during Slice 4.
- ChatRunner remains the product default and rollback path. Prime remains opt-in through Slices 3-4. Default cutover is a later decision.
- Tasks 0-9 are model-free. They must run with provider credentials scrubbed and may not contact Rhino, Grasshopper, a model, or a live Rook mutation surface.
- Task 9 is a mandatory independent implementation review gate before Slice 3 live contact. Task 10 seals and reviews Slice 3 before any Slice 4 preparation. Task 11 is a separate pre-contact review gate before Slice 4 mutation.
- Live runs occur once, without retry, prompt repair, hidden tuning, or configuration drift. A failed or incomplete result is preserved honestly.
- Live evidence is written directly to separate durable, non-temporary roots and verified before interpretation. Slice 3, Slice 4 Actor, and Slice 4 evaluator ownership never share an unfenced trace.

## Execution Transition Closure

Every phase boundary below is an executable artifact handoff, not an assertion that later work should infer. Each consumer reverifies the published fact before acting, and every mismatch stops before the next phase:

| Transition | Fact bound before action | Establishing owner and transaction | Retained proof | Consumer reverification | Failure residue |
| --- | --- | --- | --- | --- | --- |
| Review authorization -> Task 0 | exact approved plan commit and pinned Prime baseline | active implementation `/goal` supplies the plan commit directly to Task 0's invoked script block | Task 0 records both HEAD/tree identities and clean-status output | Task 0 compares clean Rook `HEAD` with the supplied literal and clean Prime `HEAD` with the pinned baseline | no test or edit begins |
| Offline isolation -> every real Prime process | scrubbed provider environment, isolated agent/session roots, exact branch-local dependencies | the same PowerShell process removes credentials, creates isolated roots, and launches the Prime command | command output records roots, credential count zero, import paths, and terminal exit | every Prime-launching block repeats the complete preamble before dispatch | that invocation exits; no later shell inherits an assumed scrub |
| Source build -> installed runtime | exact tested worktree bytes and worktree `uv.lock` environment promoted through the repository-owned local deployment path | Task 0 creates the worktree venv with `uv sync --frozen`; every Python gate uses it; Task 9 closes Rhino/owned workers, builds exact outputs, and deploys with `-UseRepoVenv` | lock hash, worktree interpreter path, deployment log, installed-file/hash inventory, and chat-service manifest | Tasks 10-12 run `uv sync --frozen --check`, rehash the installed inventory, and require the manifest to name the same interpreter before contact | contact remains unauthorized; previous installed bytes or a drifted environment are not treated as current |
| Task changes -> commit -> frozen inputs | all files named by the task are staged together; evaluator owners remain unchanged | each task's explicit `git add` list includes every actual owner and its tests | focused commit and clean worktree | the next task checks clean status; Task 11 rehashes the four evaluator owners | unstaged or unexpected bytes stop the task before the next phase |
| Live execution -> evidence seal -> report | Actor/evaluator ownership, terminal receipts, installed/runtime hashes, and process cleanup are complete | qualification owner seals the evidence root first; repository report is written afterward and is not an evidence-manifest member | independently verified evidence manifest plus report citing that manifest SHA-256 | result review recomputes the evidence manifest and checks the committed report against it | sealed evidence remains immutable; an incomplete report or failed commit cannot alter the evidence claim |

After every task commit, in that same shell, run `git status --porcelain --untracked-files=all` in the owning worktree and refuse to begin the next task unless it is empty. Commit blocks below name every planned owner; unexpected modified or untracked files are never carried across a task boundary.

## Closed Product Interfaces

### Prime-generic RPC additions

```json
{"id":"1","type":"set_rlm_max_depth","maxDepth":0,"global":false}
{"id":"2","type":"get_rlm_max_depth_status"}
{"id":"3","type":"prepare_ipython_runtime"}
```

Successful recursion status is exactly:

```json
{"maxDepth":0,"source":"chat"}
```

Successful runtime preparation data is exactly:

```json
{
  "interpreterPath":"C:/absolute/contract/python.exe",
  "rookFullFile":"C:/absolute/versioned/rook_full/__init__.py",
  "goalFile":"D:/absolute/prime/skills/goal/src/goal/__init__.py",
  "callables":{"search":true,"read":true,"call":true}
}
```

`prepare_ipython_runtime` accepts no model-provided code or paths. It awaits Prime's actual persistent root provisioner with a bounded RPC deadline and executes one fixed in-kernel probe.

### Registry v2

```python
@dataclass(frozen=True)
class RuntimePreparation:
    status: Literal["pending", "prepared"]
    interpreter_path: str | None
    prepared_at_utc: str | None

@dataclass(frozen=True)
class PrimeRuntimeContractRef:
    contract_fingerprint_sha256: str
    capability_profile: Literal["readonly", "full"]
    kernel_environment_path: str
    preparation: RuntimePreparation

@dataclass(frozen=True)
class TargetFingerprintV2:
    rhino_pid: int
    rhino_process_start_utc_ticks: str
    document_runtime_serial: int
    grasshopper_document_id: str | None

@dataclass(frozen=True)
class PrimeConversationRecordV2:
    schema_version: Literal[2]
    conversation_id: str
    prime_session_id: str
    prime_session_path: str
    model: PrimeModelSelection
    runtime: PrimeRuntimeContractRef
    target: TargetFingerprintV2
    last_lifecycle: LifecycleRecord
```

The serialized key sets, pending/prepared transitions, path requirements, canonical GUID, and immutable fields are exactly those in the approved specification. The existing `PrimeConversationRecord` v1 serializer and validator remain byte-compatible.

### Runtime contract

The product package manifest and Prime goal-skill manifest use the same closed recursive manifest algorithm. Canonical JSON is compact ASCII UTF-8 without BOM or trailing newline, uses ordinal object-key order, and rejects duplicate, missing, unknown, escaped, or unlisted authority files. The package manifest hash is the package identity.

The runtime-contract record is exact:

```json
{
  "capabilityProfile":"readonly",
  "goalSkill":{"manifestSha256":"...","pathIdentity":"packages/coding-agent/skills/goal"},
  "prime":{"bundleManifestSha256":"...","gitCommitProvenance":"7690c18479c909ddea67a34e86114f7f982179a8"},
  "rlmMaxDepth":0,
  "rookPackage":{
    "adapterSha256":"...",
    "packageManifestSha256":"...",
    "projectMetadataSha256":"...",
    "skillSha256":"..."
  },
  "runtimeCompatibilityVersion":1,
  "schemaVersion":1
}
```

Its canonical SHA-256 selects `%LOCALAPPDATA%/Rook/agent-kernels/<contract-sha256>/`. The Prime bundle manifest hash is executable identity; the git commit is provenance.

### Target lock

```python
@dataclass(frozen=True)
class PanelTargetLock:
    mode: Literal["panel_locked"]
    process_id: int
    process_start_utc_ticks: str
    document_serial_number: int
    grasshopper_document_id: str | None
    capability_profile: Literal["readonly", "full"]
    reason: str = "rook_chat_panel"
```

Base fields are mandatory and fail before child launch. A missing Grasshopper ID permits non-GH calls but makes `/gh/*` fail `grasshopper_target_unbound`. Explicit selectors may only agree with this lock.

### Managed Grasshopper invariant

```text
managed callback entry
-> capture Grasshopper.Instances.ActiveCanvas once
-> capture that canvas's active GH_Document once
-> require exact nonempty GH_Document.DocumentID
-> compare parsed GUID values with the bound canonical GUID
-> invoke the handler against that same captured canvas/document object
```

There is no second `ActiveCanvas` lookup, no fallback identifier, and no handler operation after a mismatch.

### Product adapter API

```python
await rook_full.search(query)
await rook_full.read(name)
await rook_full.call(name, arguments)
```

Each call owns one bounded MCP/stdio child. An authentic Rook success or structured failure remains authoritative if cleanup later fails. If no authentic envelope arrives, the outcome is uncertain and the adapter/broker never replays automatically.

## File Map

### Prime worktree

- Modify `packages/coding-agent/src/cli/args.ts` and `packages/coding-agent/src/cli.ts`: exact `--append-system-prompt-file` loading and startup refusal.
- Modify `packages/coding-agent/src/modes/rpc/rpc-types.ts`, `rpc-mode.ts`, and `rpc-client.ts`: recursion status/set and fixed runtime-preparation RPC commands.
- Modify `packages/coding-agent/src/core/agent-session.ts` and `packages/coding-agent/src/core/tools/ipython.ts`: expose bounded preparation of the actual persistent root kernel and the fixed in-kernel import probe.
- Modify `packages/coding-agent/docs/rpc.md` and CLI docs for the generic additions.
- Create `packages/coding-agent/test/rpc-rookchat-runtime.test.ts` and extend `packages/coding-agent/test/args.test.ts`.

### Rook broker and package

- Create `mcp_server/src/rook/agent/chat/prime_runtime_contract.py`: canonical manifests, immutable package staging, runtime-contract construction, and path verification.
- Modify `mcp_server/src/rook/agent/chat/prime_registry.py`, `prime_process.py`, `prime_backend.py`, `prime_rpc_protocol.py`, `server.py`, and `service_main.py`.
- Productize `integrations/prime/skills/rook-full/` with `SKILL.md`, `pyproject.toml`, `src/rook_full/__init__.py`, `references/`, and generated `package-manifest.json`.
- Modify `mcp_server/src/rook/targeting.py`, `bridge.py`, and `server.py` for process-generation custody, locked profile, selector agreement, and document-switch refusal. Preserve `mcp_tool_profiles.py` byte-for-byte because it is an approved Slice 4 evaluator owner.
- Create `mcp_server/tests/test_prime_runtime_contract.py` and `mcp_server/tests/test_rook_full_product_adapter.py`; extend existing Prime, targeting, bridge, profile, and server tests.

### Native and managed Rook

- Modify `src/RookNative/RookServer.cpp` and `.h`: native `processStartUtcTicks` discovery.
- Modify `src/Rook/DocumentContext.cs`: strict panel-locked Rhino document resolution without fallback.
- Create `src/Rook/InternalBridge/GrasshopperRequestContext.cs`: captured canvas/document scope used only during one managed callback.
- Modify `src/Rook/InternalBridge/GrasshopperCore.cs`, `NativeGhBridgeRegistrar.cs`, and the shared Grasshopper handler context lookup in `src/Rook/Handlers/GrasshopperHandler.cs`.
- Modify `src/Rook/UI/Chat/AgentChatClient.cs`, `AgentChatTab.cs`, `ChatServiceManager.cs`, and chat resources for v2 creation, fixed profile/target, goal projection, and command refusal display.
- Extend `src/Rook.Tests/InternalBridge/NativeGhBridgeRegistrarTests.cs` and existing chat tests; create `src/Rook.Tests/InternalBridge/GrasshopperTargetContextTests.cs`.

### External qualification only

- Create `scripts/rookchat_prime_slices_3_4_qualification.py`: fixture preparation, product relay capture, evidence sealing, and evaluator separation. It is not imported by product code and does not implement model orchestration.
- Create frozen Slice 3 and Slice 4 protocol JSON files under `docs/superpowers/experiments/`.
- Create pre-contact and execution reports under `docs/superpowers/reports/`.

---

### Task 0: Admit the Reviewed Plan and Re-establish Hermetic Custody

**Files:**
- No repository file changes.
- Uses existing worktrees `C:/UDEV/Rook/.worktrees/rookchat-prime-primary-backend` and `D:/prime-agent/.worktrees/rookchat-primary-backend`.

**Interfaces:**
- Consumes: the exact plan commit named in the implementation `/goal`, Prime commit `7690c18479c909ddea67a34e86114f7f982179a8`, existing dependency lockfiles, and the approved credential-scrub rule.
- Produces: clean admitted worktrees, branch-local Node/Python/.NET dependencies, native toolchain readiness, and retained model-free preflight facts.

- [ ] **Step 1: Verify exact reviewed heads before any test or edit**

```powershell
$verifyReviewedHeads = {
    param(
        [Parameter(Mandatory = $true)]
        [ValidatePattern('^[0-9a-f]{40}$')]
        [string]$ApprovedPlanCommit
    )
    $rook = 'C:/UDEV/Rook/.worktrees/rookchat-prime-primary-backend'
    $prime = 'D:/prime-agent/.worktrees/rookchat-primary-backend'
    if ((git -C $rook status --porcelain --untracked-files=all).Length -ne 0) { throw 'Rook worktree is dirty.' }
    if ((git -C $rook rev-parse HEAD).Trim() -ne $ApprovedPlanCommit) { throw 'Rook HEAD does not equal the reviewed plan commit.' }
    if ((git -C $prime status --porcelain --untracked-files=all).Length -ne 0) { throw 'Prime worktree is dirty.' }
    if ((git -C $prime rev-parse HEAD).Trim() -ne '7690c18479c909ddea67a34e86114f7f982179a8') { throw 'Prime baseline drifted.' }
}
& $verifyReviewedHeads (Read-Host 'Paste the exact approved plan commit named in the active /goal')
```

Expected: no output and exit zero. The script block is explicitly invoked with the literal copied from the authorized `/goal`; it is not stored in an environment variable or inside this self-referential plan. A missing, malformed, stale, or unapproved literal stops before dependencies, tests, or edits.

- [ ] **Step 2: Restore exact dependencies in their owning worktrees**

```powershell
Set-Location D:/prime-agent/.worktrees/rookchat-primary-backend
npm ci
$rook = 'C:/UDEV/Rook/.worktrees/rookchat-prime-primary-backend'
Set-Location "$rook/mcp_server"
uv sync --frozen
if ($LASTEXITCODE -ne 0) { throw 'Frozen worktree Python environment preparation failed.' }
$python = "$rook/mcp_server/.venv/Scripts/python.exe"
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw "Worktree Python interpreter missing: $python" }
Set-Location $rook
dotnet restore src/Rook.Tests/Rook.Tests.csproj
```

Expected: `package-lock.json` and `mcp_server/uv.lock` remain unchanged; the authoritative Python interpreter exists beneath the implementation worktree; and `src/Rook.Tests/obj/project.assets.json` is created beneath the Rook worktree.

- [ ] **Step 3: Prove branch-local Node and Python imports**

```powershell
$prime = [IO.Path]::GetFullPath('D:/prime-agent/.worktrees/rookchat-primary-backend')
Set-Location $prime
$vitest = (& node -e "console.log(require.resolve('vitest/package.json'))").Trim()
if (-not [IO.Path]::GetFullPath($vitest).StartsWith($prime, [StringComparison]::OrdinalIgnoreCase)) { throw "Prime dependency escaped: $vitest" }
npx tsx -e "import './packages/coding-agent/src/modes/rpc/rpc-mode.ts'; console.log('prime-source-import-ok')"

$rook = [IO.Path]::GetFullPath('C:/UDEV/Rook/.worktrees/rookchat-prime-primary-backend')
Set-Location $rook
$env:PYTHONPATH = "$rook/mcp_server/src"
$env:ROOK_IMPLEMENTATION_ROOT = $rook
$python = "$rook/mcp_server/.venv/Scripts/python.exe"
& $python -c "from pathlib import Path; import os, rook, rook.agent.chat.server as s; root=Path(os.environ['ROOK_IMPLEMENTATION_ROOT']).resolve(); assert root in Path(rook.__file__).resolve().parents; assert root in Path(s.__file__).resolve().parents"
```

Expected: `prime-source-import-ok`; both Rook modules resolve beneath the implementation worktree.

- [ ] **Step 4: Freeze the model-free contact preflight repeated by every offline Prime execution block in Tasks 1-9, 11, and 12**

```powershell
$offlineRoot = [IO.Path]::GetFullPath("$env:TEMP/rookchat-prime-slices-3-4-offline")
Remove-Item -LiteralPath $offlineRoot -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path "$offlineRoot/agent" -Force | Out-Null
New-Item -ItemType Directory -Path "$offlineRoot/sessions" -Force | Out-Null
$credentialPattern = '(API_KEY|OAUTH_TOKEN|ACCESS_KEY_ID|SECRET_ACCESS_KEY|SESSION_TOKEN|BEARER_TOKEN_BEDROCK|WEB_IDENTITY_TOKEN_FILE|GITHUB_TOKEN|GH_TOKEN|HF_TOKEN|COPILOT_GITHUB_TOKEN|AWS_PROFILE|GOOGLE_APPLICATION_CREDENTIALS)$'
Get-ChildItem Env: | Where-Object Name -Match $credentialPattern | ForEach-Object { Remove-Item -LiteralPath "Env:$($_.Name)" }
Remove-Item Env:PI_CODING_AGENT_DIR -ErrorAction SilentlyContinue
$env:PRIME_AGENT_CODING_AGENT_DIR = "$offlineRoot/agent"
$env:PRIME_AGENT_SESSION_DIR = "$offlineRoot/sessions"
if (@(Get-ChildItem Env: | Where-Object Name -Match $credentialPattern).Count -ne 0) { throw 'Provider credentials remain.' }
if (Test-Path -LiteralPath "$offlineRoot/agent/auth.json") { throw 'Offline Prime auth directory is not empty.' }
```

Expected: no credentials remain and no auth file exists. Each later Prime test command repeats this preflight in its own shell invocation.

- [ ] **Step 5: Record dependency and source custody**

Record both HEAD/tree hashes, `package-lock.json` and `mcp_server/uv.lock` SHA-256 values, exact worktree `.venv` interpreter path, `uv sync --frozen` result, .NET assets path, and the selected MSVC toolset. Task 0 creates no commit.

---

### Task 1: Add Prime-Generic Runtime Custody Commands

**Files:**
- Modify: `D:/prime-agent/.worktrees/rookchat-primary-backend/packages/coding-agent/src/cli/args.ts`
- Modify: `D:/prime-agent/.worktrees/rookchat-primary-backend/packages/coding-agent/src/cli.ts`
- Modify: `D:/prime-agent/.worktrees/rookchat-primary-backend/packages/coding-agent/src/modes/rpc/rpc-types.ts`
- Modify: `D:/prime-agent/.worktrees/rookchat-primary-backend/packages/coding-agent/src/modes/rpc/rpc-mode.ts`
- Modify: `D:/prime-agent/.worktrees/rookchat-primary-backend/packages/coding-agent/src/modes/rpc/rpc-client.ts`
- Modify: `D:/prime-agent/.worktrees/rookchat-primary-backend/packages/coding-agent/src/modes/agent-connection/in-process-agent-connection.ts`
- Modify: `D:/prime-agent/.worktrees/rookchat-primary-backend/packages/coding-agent/src/core/agent-session.ts`
- Modify: `D:/prime-agent/.worktrees/rookchat-primary-backend/packages/coding-agent/src/core/tools/ipython.ts`
- Modify: `D:/prime-agent/.worktrees/rookchat-primary-backend/packages/coding-agent/docs/rpc.md`
- Test: `D:/prime-agent/.worktrees/rookchat-primary-backend/packages/coding-agent/test/args.test.ts`
- Create: `D:/prime-agent/.worktrees/rookchat-primary-backend/packages/coding-agent/test/rpc-rookchat-runtime.test.ts`

**Interfaces:**
- Adds: `--append-system-prompt-file`, `set_rlm_max_depth`, `get_rlm_max_depth_status`, and `prepare_ipython_runtime`.
- Preserves: all existing CLI arguments, `prompt_and_wait`, public `RpcClient.promptAndWait(): Promise<AgentEvent[]>`, and generic interactive behavior.

- [ ] **Step 1: Write RED CLI tests for exact file-backed prompt loading**

Cover one valid UTF-8 file and refusal for missing, directory, unreadable, and invalid-UTF-8 paths. Assert repeated file arguments preserve order and are appended after ordinary `--append-system-prompt` values according to the CLI's explicit argument order.

```ts
expect(parseArgs(["--append-system-prompt-file", promptPath]).appendSystemPromptFiles).toEqual([promptPath]);
```

Run:

```powershell
$offlineRoot = [IO.Path]::GetFullPath("$env:TEMP/rookchat-prime-slices-3-4-offline")
Remove-Item -LiteralPath $offlineRoot -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path "$offlineRoot/agent" -Force | Out-Null
New-Item -ItemType Directory -Path "$offlineRoot/sessions" -Force | Out-Null
$credentialPattern = '(API_KEY|OAUTH_TOKEN|ACCESS_KEY_ID|SECRET_ACCESS_KEY|SESSION_TOKEN|BEARER_TOKEN_BEDROCK|WEB_IDENTITY_TOKEN_FILE|GITHUB_TOKEN|GH_TOKEN|HF_TOKEN|COPILOT_GITHUB_TOKEN|AWS_PROFILE|GOOGLE_APPLICATION_CREDENTIALS)$'
Get-ChildItem Env: | Where-Object Name -Match $credentialPattern | ForEach-Object { Remove-Item -LiteralPath "Env:$($_.Name)" }
Remove-Item Env:PI_CODING_AGENT_DIR -ErrorAction SilentlyContinue
$env:PRIME_AGENT_CODING_AGENT_DIR = "$offlineRoot/agent"
$env:PRIME_AGENT_SESSION_DIR = "$offlineRoot/sessions"
if (@(Get-ChildItem Env: | Where-Object Name -Match $credentialPattern).Count -ne 0) { throw 'Provider credentials remain.' }
if (Test-Path -LiteralPath "$offlineRoot/agent/auth.json") { throw 'Offline Prime auth directory is not empty.' }

Set-Location D:/prime-agent/.worktrees/rookchat-primary-backend/packages/coding-agent
npx tsx ../../node_modules/vitest/dist/cli.js --run test/args.test.ts
```

Expected RED: the new field/argument and startup loader do not exist.

- [ ] **Step 2: Implement file-backed system-prompt loading without broker parsing**

Parse absolute paths in `args.ts`. In `cli.ts`, read each file as bytes, reject invalid UTF-8 with `TextDecoder("utf-8", { fatal: true })`, and append the decoded string through the same Prime configuration field used by literal append prompts. Do not trim, strip frontmatter, or add a skill wrapper.

- [ ] **Step 3: Write RED closed-wire tests for recursion commands**

Test exact field sets, nonnegative integer depth, boolean `global`, exact `{maxDepth, source}` response, unknown-field refusal, and preservation of existing RPC responses. Exercise the existing `AgentSession.setRlmMaxDepth()` and `getRlmMaxDepthStatus()` methods through RPC; do not reimplement settings precedence.

- [ ] **Step 4: Implement recursion RPC commands and typed client methods**

Add distinct `RpcCommand`/`RpcResponse` union members and client methods:

```ts
setRlmMaxDepth(maxDepth: number, global = false): Promise<RlmMaxDepthStatus>
getRlmMaxDepthStatus(): Promise<RlmMaxDepthStatus>
```

The RPC handler calls the already-existing generic `AgentConnection.getRlmMaxDepthStatus()` and `setRlmMaxDepth()` methods. The broker will use the typed client methods; they are not exposed as panel slash commands.

- [ ] **Step 5: Write RED actual-kernel preparation tests**

Use a fake provisioner for timeout/failure and a real isolated kernel fixture for the positive case. Prove the command:

- accepts no input fields beyond `id,type`;
- awaits the root session's persistent provisioner;
- reports the provisioner's actual interpreter;
- executes the fixed probe in that same kernel;
- returns only the four closed fields;
- surfaces missing `rook_full`, missing `goal`, or non-callable API members; and
- cannot execute caller-supplied code.

- [ ] **Step 6: Implement bounded `prepare_ipython_runtime`**

Expose a narrow `AgentSession.prepareIpythonRuntime()` that awaits `IpythonKernelProvisioner.ensure()` rather than fire-and-forget `prewarm()`, then executes one hard-coded probe through that manager. Bind it to production RPC through `InProcessAgentConnection` and a narrow `RpcModeConnectionOptions.prepareIpythonRuntime` callback; model-free `runRpcModeWithConnection` tests inject a fake callback. Do not add a daemon protocol, general kernel execution RPC, or caller-supplied probe. The RPC command relies on the existing control-command deadline at the broker.

- [ ] **Step 7: Run Prime tests and build**

```powershell
$offlineRoot = [IO.Path]::GetFullPath("$env:TEMP/rookchat-prime-slices-3-4-offline")
Remove-Item -LiteralPath $offlineRoot -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path "$offlineRoot/agent" -Force | Out-Null
New-Item -ItemType Directory -Path "$offlineRoot/sessions" -Force | Out-Null
$credentialPattern = '(API_KEY|OAUTH_TOKEN|ACCESS_KEY_ID|SECRET_ACCESS_KEY|SESSION_TOKEN|BEARER_TOKEN_BEDROCK|WEB_IDENTITY_TOKEN_FILE|GITHUB_TOKEN|GH_TOKEN|HF_TOKEN|COPILOT_GITHUB_TOKEN|AWS_PROFILE|GOOGLE_APPLICATION_CREDENTIALS)$'
Get-ChildItem Env: | Where-Object Name -Match $credentialPattern | ForEach-Object { Remove-Item -LiteralPath "Env:$($_.Name)" }
Remove-Item Env:PI_CODING_AGENT_DIR -ErrorAction SilentlyContinue
$env:PRIME_AGENT_CODING_AGENT_DIR = "$offlineRoot/agent"
$env:PRIME_AGENT_SESSION_DIR = "$offlineRoot/sessions"
if (@(Get-ChildItem Env: | Where-Object Name -Match $credentialPattern).Count -ne 0) { throw 'Provider credentials remain.' }
if (Test-Path -LiteralPath "$offlineRoot/agent/auth.json") { throw 'Offline Prime auth directory is not empty.' }

Set-Location D:/prime-agent/.worktrees/rookchat-primary-backend/packages/coding-agent
npx tsx ../../node_modules/vitest/dist/cli.js --run test/args.test.ts test/rpc-rookchat-runtime.test.ts test/rpc-prompt-response-semantics.test.ts test/rpc-client-prompt-settlement.test.ts test/ipython-provisioner.test.ts
npm run build
git diff --check
```

Expected: all tests pass, build passes, and no provider/model command is admitted.

- [ ] **Step 8: Commit the Prime-generic seam**

```powershell
git add packages/coding-agent/src packages/coding-agent/test packages/coding-agent/docs/rpc.md
git commit -m "feat(rpc): expose version-custodied IPython preparation"
```

Expected: one focused Prime commit; no Rook-specific path, profile, or semantic logic enters Prime.

---

### Task 2: Implement Canonical Package and Runtime-Contract Custody

**Files:**
- Create: `mcp_server/src/rook/agent/chat/prime_runtime_contract.py`
- Create: `mcp_server/tests/test_prime_runtime_contract.py`

**Interfaces:**
- Adds: one canonical manifest implementation shared by the Rook package and Prime goal subtree, immutable package staging, exact runtime-contract construction, and prelaunch/reopen verification.
- Produces: `RuntimeContract`, `VerifiedPackage`, `stage_product_package()`, `build_runtime_contract()`, `verify_runtime_contract()`, and contract-keyed environment paths.

- [ ] **Step 1: Write RED canonical-manifest tests**

Cover exact key sets and canonical bytes; recursive references; ordinal forward-slash paths; manifest self-exclusion; closed cache/build exclusions; uppercase hashes; size binding; extra/unlisted/missing files; duplicate normalized paths; symlink/junction/reparse escapes; BOM/trailing newline; and duplicate JSON keys.

Include a parity test proving the same algorithm produces both the Rook package manifest and the pinned Prime goal-skill manifest.

- [ ] **Step 2: Implement one canonical encoder and recursive manifest builder**

Use structured JSON data and one ASCII compact serializer (`sort_keys=True`, `separators=(",", ":")`, `ensure_ascii=True`) after validating the closed schemas. Do not hand-build JSON strings. Reject authority paths before hashing.

- [ ] **Step 3: Write RED runtime-contract tests**

Assert exact schema/key/type validation, profile distinction, fixed `rlmMaxDepth: 0`, Prime bundle identity versus git provenance, diagnostic hashes, contract fingerprint stability, and different environment paths for old/new contracts.

```python
assert readonly.fingerprint != full.fingerprint
assert readonly.kernel_environment_path.name == readonly.fingerprint
```

- [ ] **Step 4: Implement immutable staging and verification**

Stage through a sibling pending directory, fsync/close all files, verify the generated manifest, then atomically rename to:

```text
%LOCALAPPDATA%/Rook/agent-contracts/<manifest-hash>/rook-full/
```

If the final directory already exists, verify it byte-for-byte and reuse it. Never modify it in place. Verify all installed paths remain beneath the configured product root.

- [ ] **Step 5: Add same-contract and old/new concurrency tests**

Race two staging/preparation owners for one contract and assert one stable package/environment identity. Race old/new contracts and assert their source bytes, import roots, and environment paths remain distinct. These tests use fake preparation locks; Prime's real bootstrap concurrency is exercised in Task 7.

- [ ] **Step 6: Run focused tests and compilation**

```powershell
$rook='C:/UDEV/Rook/.worktrees/rookchat-prime-primary-backend'
Set-Location $rook
$env:PYTHONPATH="$rook/mcp_server/src"
$python="$rook/mcp_server/.venv/Scripts/python.exe"
& $python -m pytest mcp_server/tests/test_prime_runtime_contract.py -q
& $python -m py_compile mcp_server/src/rook/agent/chat/prime_runtime_contract.py
git diff --check
```

- [ ] **Step 7: Commit runtime-contract custody**

```powershell
git add mcp_server/src/rook/agent/chat/prime_runtime_contract.py mcp_server/tests/test_prime_runtime_contract.py
git commit -m "feat(chat): bind Prime runtime contracts to immutable packages"
```

---

### Task 3: Add Exact Registry v2 and Panel Command Admission

**Files:**
- Modify: `mcp_server/src/rook/agent/chat/prime_registry.py`
- Modify: `mcp_server/src/rook/agent/chat/prime_backend.py`
- Modify: `mcp_server/src/rook/agent/chat/server.py`
- Test: `mcp_server/tests/test_prime_registry.py`
- Test: `mcp_server/tests/test_prime_backend.py`
- Test: `mcp_server/tests/test_chat_server.py`

**Interfaces:**
- Adds: closed v2 records with immutable runtime/profile/GH target fields and the single `pending -> prepared` transition.
- Preserves: exact v1 read/write behavior, absorbing `closed`, and the existing broker lifecycle.
- Adds: pre-Prime slash-command admission limited to exact `/goal`.

- [ ] **Step 1: Freeze v1 bytes and write RED v2 schema tests**

Keep a golden v1 JSON fixture and assert load/write bytes remain unchanged. Add v2 tests for every exact key set, canonical SHA-256, canonical GUID `D` form, positive PID/ticks/serial, profile enum, absolute paths, pending/prepared paired fields, duplicate keys, and unknown fields.

```python
assert registry.load(v1_id) == expected_v1
assert registry.path_for(v1_id).read_bytes() == v1_golden_bytes
```

Expected RED: v2 records are unsupported.

- [ ] **Step 2: Implement a tagged v1/v2 union without migration**

Dispatch serialization by integer `schemaVersion`. Keep the existing v1 dataclasses and exact validators. Add v2 dataclasses separately; do not add optional v2 fields to v1. `load()` returns the tagged union, and v1 reopen remains text-only.

- [ ] **Step 3: Write RED immutable-transition tests**

Prove:

- creation writes `pending` only after Prime returns saved-session identity;
- preparation changes only the preparation triple;
- contract/profile/environment/target changes are rejected;
- `prepared -> pending` and `prepared -> prepared` rewrite attempts reject;
- restart reconciliation maps pending to lifecycle `failed/runtime_contract_unavailable` without claiming preparation; and
- cleanup/retry remains an explicit qualification or setup action.

- [ ] **Step 4: Implement explicit registry transition methods**

Add narrow methods such as:

```python
write_new_v2(record)
mark_runtime_prepared(conversation_id, interpreter_path, prepared_at_utc)
mark_pending_runtime_unavailable(conversation_id)
```

Each method loads and validates the current file under the existing namespace writer lock, applies one allowed transition, and atomically replaces that conversation's file.

- [ ] **Step 5: Write RED panel command-admission tests**

Test exact admission for `/goal`, `/goal status`, `/goal pause`, `/goal resume`, `/goal clear`, and `/goal stop`, including leading whitespace. Test refusal before `PrimeRpcProcess.command()` for `/compact`, `/refine`, `/autonomous`, `/rlm-max-depth`, aliases, near matches such as `/goalkeeper`, unknown slash commands, and future command names.

- [ ] **Step 6: Implement one lexical admission helper**

```python
def admit_prime_panel_prompt(message: str) -> None:
    remaining = message.lstrip()
    if remaining.startswith("/"):
        token = remaining.split(maxsplit=1)[0]
        if token != "/goal":
            raise PrimeBackendError("prime_command_not_admitted")
```

Invoke it before prompt lifecycle mutation or Prime dispatch. Automatic Prime compaction and continuation do not pass through this helper.

- [ ] **Step 7: Run registry/backend/server tests**

```powershell
$rook='C:/UDEV/Rook/.worktrees/rookchat-prime-primary-backend'
Set-Location $rook
$env:PYTHONPATH="$rook/mcp_server/src"
$python="$rook/mcp_server/.venv/Scripts/python.exe"
& $python -m pytest mcp_server/tests/test_prime_registry.py mcp_server/tests/test_prime_backend.py mcp_server/tests/test_chat_server.py -q
& $python -m py_compile mcp_server/src/rook/agent/chat/prime_registry.py mcp_server/src/rook/agent/chat/prime_backend.py mcp_server/src/rook/agent/chat/server.py
git diff --check
```

- [ ] **Step 8: Commit registry v2 and command custody**

```powershell
git add mcp_server/src/rook/agent/chat/prime_registry.py mcp_server/src/rook/agent/chat/prime_backend.py mcp_server/src/rook/agent/chat/server.py mcp_server/tests/test_prime_registry.py mcp_server/tests/test_prime_backend.py mcp_server/tests/test_chat_server.py
git commit -m "feat(chat): add immutable Prime conversation contracts"
```

---

### Task 4: Productize the Versioned `rook-full` Package

**Files:**
- Create: `integrations/prime/skills/rook-full/SKILL.md`
- Modify: `integrations/prime/skills/rook-full/pyproject.toml`
- Modify: `integrations/prime/skills/rook-full/src/rook_full/__init__.py`
- Create: `integrations/prime/skills/rook-full/references/grasshopper.md`
- Generate: `integrations/prime/skills/rook-full/package-manifest.json`
- Create: `mcp_server/tests/test_rook_full_product_adapter.py`
- Modify: `mcp_server/tests/test_prime_runtime_contract.py`

**Interfaces:**
- Preserves: `search(query)`, `read(name)`, and `call(name, arguments)`.
- Removes: hard-coded user paths, campaign source logging, behavioral-acceptance imports, and gateway call-limit ownership.
- Adds: closed product configuration, locked target/profile propagation, bounded per-call lifecycle, structured failure preservation, and measured startup latency.

- [ ] **Step 1: Write RED package-contract tests**

Import the package from a staged immutable path and assert:

- the public API is exactly `search/read/call`;
- command, cwd, install/data/cache paths come only from broker-validated environment fields;
- model arguments cannot set command/cwd/profile/target selectors;
- missing or malformed base lock fields prevent `stdio_client()` invocation;
- GH calls require a canonical locked GH ID;
- explicit agreeing selectors are stripped or normalized to the lock;
- conflicting selectors fail before child launch; and
- no campaign recorder or call-limit module is imported.

- [ ] **Step 2: Write RED closed-child-environment tests**

Seed the parent with provider keys, alternate target fields, hostile `PYTHONPATH`, and unrelated variables. Capture `StdioServerParameters.env` and require exactly the approved Windows bootstrap fields, constructed PATH, product runtime fields, profile, and four target fields. Assert no ambient provider credential or target/profile variable survives.

- [ ] **Step 3: Write RED lifecycle and error tests**

Use fake MCP transports to causally cover:

- bounded launch timeout;
- initialize timeout;
- tool-call timeout;
- caller cancellation during each phase;
- graceful close followed by process-tree termination on timeout;
- authentic success plus cleanup failure returns the success and separately records cleanup failure;
- authentic `McpToolError.structured_content` plus cleanup failure re-raises the same structured error;
- no-envelope transport loss raises an uncertain outcome; and
- no path automatically replays the call.

- [ ] **Step 4: Implement the direct stdio adapter**

Keep one `AsyncExitStack` per API call and one owned child. Separate `request_succeeded`, `authentic_envelope_received`, and `cleanup_succeeded` in local control flow. Record monotonic startup duration in the returned diagnostic/qualification hook without making it a product gate.

The adapter must pass the original `McpToolError` object through so Prime retains `structured_content`.

- [ ] **Step 5: Author the persistent product contract and Grasshopper reference**

`SKILL.md` must include:

- ordinary conversational/observational turns do not require a goal;
- substantive multi-step Rook authoring, repair, or extended investigation is system-authorized to create a Prime goal;
- call `goal.get()` before `goal.create()` and never work around a nonterminal goal;
- the model cannot supersede a goal, while user `/goal` commands retain Prime-native authority;
- immutable target/profile custody and payload-first APIs;
- local repair and named material uncertainty discipline;
- authentic readiness/receipt/fenced-evidence sequence;
- dedicated final `await goal.complete()` cell and final text only; and
- Stop aborts the current prompt but does not clear or complete an active goal.

Put Grasshopper-specific execution details in `references/grasshopper.md` and instruct the model to read it only for GH work. Do not create a second skill.

- [ ] **Step 6: Generate and verify the package manifest**

Use Task 2's canonical builder. Check the generated `package-manifest.json` into source as the exact product package input. A test removes the manifest, regenerates it, and compares bytes exactly.

- [ ] **Step 7: Run package and manifest tests**

```powershell
$rook='C:/UDEV/Rook/.worktrees/rookchat-prime-primary-backend'
Set-Location $rook
$env:PYTHONPATH="$rook/mcp_server/src"
$python="$rook/mcp_server/.venv/Scripts/python.exe"
& $python -m pytest mcp_server/tests/test_rook_full_product_adapter.py mcp_server/tests/test_prime_runtime_contract.py -q
& $python -m py_compile integrations/prime/skills/rook-full/src/rook_full/__init__.py
git diff --check
```

- [ ] **Step 8: Commit the self-contained product package**

```powershell
git add integrations/prime/skills/rook-full mcp_server/tests/test_rook_full_product_adapter.py mcp_server/tests/test_prime_runtime_contract.py
git commit -m "feat(chat): productize immutable Rook full skill"
```

---

### Task 5: Bind Native Process Generation and the Extended `PanelTargetLock`

**Files:**
- Modify: `src/RookNative/RookServer.cpp`
- Modify: `src/RookNative/RookServer.h`
- Modify: `mcp_server/src/rook/bridge.py`
- Modify: `mcp_server/src/rook/targeting.py`
- Modify: `src/Rook/DocumentContext.cs`
- Test: `mcp_server/tests/test_bridge.py`
- Test: `mcp_server/tests/test_multi_instance_targeting.py`
- Test: `src/Rook.Tests/UI/Chat/ChatServiceManagerTests.cs`
- Create: `src/Rook.Tests/DocumentContextTests.cs`

**Interfaces:**
- Adds native discovery field `processStartUtcTicks`, independently derived from the Rhino process.
- Extends the existing `PanelTargetLock`; no second target abstraction is introduced.
- Makes panel-locked Rhino document resolution strict instead of falling back to `RhinoDoc.ActiveDoc`.

- [ ] **Step 1: Write RED discovery and canonical-tick tests**

Add bridge fixtures with matching PID/ticks, same PID/different ticks, missing ticks, malformed/noncanonical ticks (`+1`, leading zero, whitespace), zero/overflow, and legacy records. In `panel_locked`, require refusal before `call_rhino()` when ticks are missing or mismatched. Non-panel legacy targeting keeps its existing behavior.

- [ ] **Step 2: Implement native UTC tick publication**

In `RookServer`, compute Windows process creation time independently from the running Rhino process and convert it to the same canonical positive decimal .NET UTC ticks represented by:

```text
Process.GetCurrentProcess().StartTime.ToUniversalTime().Ticks
```

Publish `processStartUtcTicks` alongside the existing human-readable `startTime`. Do not copy a broker value and do not add a nonce.

- [ ] **Step 3: Extend `PanelTargetLock` environment parsing**

Require positive PID, canonical ticks, positive Rhino serial, profile `readonly|full`, and optional canonical GH GUID. Preserve one initialization point and one config-error envelope. Missing/malformed base fields make every public adapter method fail before launch.

- [ ] **Step 4: Enforce process-generation selection before endpoint contact**

Update `resolve_tool_route()` so panel-locked discovery filters by exact PID and parsed tick identity before choosing a port. Explicit port/session/process selectors may only agree. Add a spy asserting neither `call_rhino()` nor native HTTP dispatch runs on mismatch.

- [ ] **Step 5: Add strict Rhino document context**

Add `DocumentContext.WithRequiredDocument(uint, Func<T>)` or an equivalent scoped strict flag. When a bound serial is absent from `RhinoDoc.FromRuntimeSerialNumber`, return/refuse; never fall back to `ActiveDoc`. Keep existing fallback behavior for unbound legacy call paths.

- [ ] **Step 6: Run Python, managed, and native build gates**

```powershell
$rook='C:/UDEV/Rook/.worktrees/rookchat-prime-primary-backend'
Set-Location $rook
$env:PYTHONPATH="$rook/mcp_server/src"
$python="$rook/mcp_server/.venv/Scripts/python.exe"
& $python -m pytest mcp_server/tests/test_bridge.py mcp_server/tests/test_multi_instance_targeting.py -q
dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug --no-restore --filter "FullyQualifiedName~DocumentContextTests|FullyQualifiedName~ChatServiceManagerTests"
cmd /c "call \"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat\" x64 -vcvars_ver=14.44 && msbuild src\RookNative\RookNative.vcxproj /t:Build /p:Configuration=Debug /p:Platform=x64 /p:VCToolsVersion=14.44.35207"
git diff --check
```

Expected: tests and builds pass with the working MFC toolset.

- [ ] **Step 7: Commit process-generation custody**

```powershell
git add src/RookNative/RookServer.cpp src/RookNative/RookServer.h src/Rook/DocumentContext.cs mcp_server/src/rook/bridge.py mcp_server/src/rook/targeting.py mcp_server/tests/test_bridge.py mcp_server/tests/test_multi_instance_targeting.py src/Rook.Tests
git commit -m "feat(targeting): bind panel sessions to Rhino process generation"
```

---

### Task 6: Make Grasshopper Validation and Operation Consume One Captured Document

**Files:**
- Create: `src/Rook/InternalBridge/GrasshopperRequestContext.cs`
- Modify: `src/Rook/InternalBridge/GrasshopperCore.cs`
- Modify: `src/Rook/InternalBridge/NativeGhBridgeRegistrar.cs`
- Modify: `src/Rook/Handlers/GrasshopperHandler.cs`
- Modify: `mcp_server/src/rook/bridge.py`
- Modify: `mcp_server/src/rook/targeting.py`
- Modify: `mcp_server/src/rook/server.py`
- Test: `src/Rook.Tests/InternalBridge/NativeGhBridgeRegistrarTests.cs`
- Create: `src/Rook.Tests/InternalBridge/GrasshopperTargetContextTests.cs`
- Modify: `mcp_server/tests/test_gh_authoring_capability_routing.py`
- Create: `mcp_server/tests/test_panel_locked_gh_document_switching.py`

**Interfaces:**
- Adds: one managed callback scope containing the captured canvas and exact captured GH document.
- Adds: `ROOK_MCP_TARGET_GRASSHOPPER_DOCUMENT_ID` to the broker/Prime/adapter/MCP custody path.
- Refuses: missing/wrong/switched GH identity and all three v1 document-switch capabilities before operation.

- [ ] **Step 1: Write RED capture-once managed tests**

Use a fake host whose first `ActiveCanvas` lookup returns the intended document and whose second would return a decoy. Assert one lookup total and that the operation receives the intended object reference. Add refusals for no canvas, no document, `Guid.Empty`, malformed bound GUID, mismatched `GH_Document.DocumentID`, and closed document.

- [ ] **Step 2: Implement `GrasshopperRequestContext` analogous to `DocumentContext`**

The context stores the captured canvas/document object references in an `AsyncLocal` scope for the duration of one synchronous managed callback. It exposes no target selection API. `GrasshopperCore.ResolveContext()` and `GrasshopperHandler.GetGrasshopper()` first consume the scope and do not read `ActiveCanvas` while it is active.

- [ ] **Step 3: Make callback entry own capture, validation, and scoped operation**

Extend `ExecuteReadOnlyCallback`, `ExecuteApiResponseCallback`, and direct readiness callback variants used by `/gh/*` so they:

1. receive the locked canonical GH GUID injected by MCP targeting into the native request body;
2. capture `Grasshopper.Instances.ActiveCanvas` and its document once on the UI thread;
3. read exact `GH_Document.DocumentID` as a nonempty `Guid`;
4. compare parsed GUID values;
5. enter both strict Rhino `DocumentContext` and `GrasshopperRequestContext`; and
6. invoke the handler against those captured objects.

Do not use `DocumentGuid`, `InstanceGuid`, display strings, or a later active-canvas lookup.

`bridge.py` and `targeting.py` must copy the validated lock into the request context before native dispatch. A model payload field may agree with the lock but can never replace it.

- [ ] **Step 4: Write RED direct/transitive document-switch tests**

Under `panel_locked` `full`, require `gh_document_new`, `gh_document_open`, and `gh_learn_directory` to fail before nested dispatch. Spy on `/gh/document/open` so the `gh_learn_directory` test proves zero calls. Add a capability audit that inspects the actual composite dispatch map and fails if any other typed/composite public tool reaches document open/new without admission.

- [ ] **Step 5: Implement the fixed v1 deny set and audit helper**

Keep the deny set local to panel-locked GH admission in `server.py`/targeting, after typed/composite capability resolution and before direct or transitive dispatch. Do not modify `mcp_tool_profiles.py`, remove tools from the global full profile, or claim `rhino_execute` is contained. The audit is test/qualification code, not a runtime semantic evaluator.

- [ ] **Step 6: Run managed and Python target tests**

```powershell
$rook='C:/UDEV/Rook/.worktrees/rookchat-prime-primary-backend'
Set-Location $rook
$env:PYTHONPATH="$rook/mcp_server/src"
$python="$rook/mcp_server/.venv/Scripts/python.exe"
dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug --no-restore --filter "FullyQualifiedName~NativeGhBridgeRegistrarTests|FullyQualifiedName~GrasshopperTargetContextTests"
& $python -m pytest mcp_server/tests/test_gh_authoring_capability_routing.py mcp_server/tests/test_panel_locked_gh_document_switching.py -q
& $python -m py_compile mcp_server/src/rook/server.py mcp_server/src/rook/bridge.py mcp_server/src/rook/targeting.py
git diff --check
```

- [ ] **Step 7: Commit the indivisible GH target boundary**

```powershell
git add src/Rook/InternalBridge/GrasshopperRequestContext.cs src/Rook/InternalBridge/GrasshopperCore.cs src/Rook/InternalBridge/NativeGhBridgeRegistrar.cs src/Rook/Handlers/GrasshopperHandler.cs src/Rook.Tests/InternalBridge/NativeGhBridgeRegistrarTests.cs src/Rook.Tests/InternalBridge/GrasshopperTargetContextTests.cs mcp_server/src/rook/bridge.py mcp_server/src/rook/targeting.py mcp_server/src/rook/server.py mcp_server/tests/test_gh_authoring_capability_routing.py mcp_server/tests/test_panel_locked_gh_document_switching.py
git diff --quiet -- mcp_server/src/rook/mcp_tool_profiles.py
if ($LASTEXITCODE -ne 0) { throw 'Approved evaluator owner mcp_tool_profiles.py changed.' }
$profileHash = (Get-FileHash -Algorithm SHA256 mcp_server/src/rook/mcp_tool_profiles.py).Hash
if ($profileHash -ne 'E08C6BF3E74758915336D4B2B9DDE5E986664DEBCF8DD82812657ECE99CA2329') { throw "Approved evaluator owner hash drifted: $profileHash" }
git commit -m "feat(grasshopper): bind callbacks to one captured document"
if ((git status --porcelain --untracked-files=all).Length -ne 0) { throw 'Task 6 left unstaged or uncommitted owners.' }
```

---

### Task 7: Launch and Reopen Prime from the Complete Runtime Contract

**Files:**
- Modify: `mcp_server/src/rook/agent/chat/prime_process.py`
- Modify: `mcp_server/src/rook/agent/chat/prime_rpc_protocol.py`
- Modify: `mcp_server/src/rook/agent/chat/prime_backend.py`
- Modify: `mcp_server/src/rook/agent/chat/service_main.py`
- Modify: `mcp_server/src/rook/agent/chat/server.py`
- Modify: `src/Rook/UI/Chat/ChatServiceManager.cs`
- Modify: `src/Rook/UI/Chat/AgentChatClient.cs`
- Modify: `src/Rook/UI/Chat/AgentChatTab.cs`
- Test: `mcp_server/tests/fixtures/prime_rpc_fake_child.py`
- Test: `mcp_server/tests/test_prime_process.py`
- Test: `mcp_server/tests/test_prime_rpc_protocol.py`
- Test: `mcp_server/tests/test_prime_backend.py`
- Test: `mcp_server/tests/test_chat_server.py`
- Create: `mcp_server/tests/test_prime_runtime_preparation.py`
- Test: `src/Rook.Tests/UI/Chat/ChatServiceManagerTests.cs`
- Test: `src/Rook.Tests/UI/Chat/AgentChatClientParseTests.cs`
- Test: `src/Rook.Tests/UI/Chat/AgentChatPrimeLifecycleTests.cs`

**Interfaces:**
- Replaces the Slice 2 effective `--no-tools` launch with the exact pinned goal skill, immutable Rook package, `--tools ipython`, and file-backed product contract.
- Adds first-use `pending -> prepared` custody and fail-closed reopen verification.
- Preserves one saved Prime session per conversation, single-flight prompt settlement, process generation, and existing Stop races.

- [ ] **Step 1: Write RED exact-launch tests**

Capture `create_subprocess_exec()` arguments and environment. Require exactly one tool configuration (`--tools ipython`), no `--no-tools`, `--no-skills` plus exactly two `--skill` paths, exact appended system-prompt file, no extensions/context/templates, exact `PRIME_AGENT_KERNEL_VENV`, and immutable profile/target variables. Reject any argument path outside the verified Prime/product roots.

- [ ] **Step 2: Extend `PrimeRpcProcess` with closed runtime responses**

Add parsers for recursion status and runtime preparation that require exact response key sets and absolute paths. Keep generic RPC failure strings for existing commands; do not broaden `prompt_and_wait`'s closed error object.

Add managed RED tests proving the service launch supplies validated installed product roots and one service-level capability profile from product/qualification configuration. The panel's v2 start body carries PID/ticks/Rhino serial/GH GUID, but no user-selectable profile. The broker binds its configured profile when it creates the record; there is no user-facing Inspection mode.

- [ ] **Step 3: Write RED first-use ordering tests**

Use the fake child to assert the exact sequence:

```text
launch Prime
-> get_state yields saved-session identity
-> atomic pending v2 record
-> set_rlm_max_depth(0,false)
-> get_rlm_max_depth_status == {0,chat}
-> prepare_ipython_runtime
-> verify persistent-kernel response and installed manifests
-> atomic prepared v2 record
-> first model prompt may be admitted
```

Inject failure at every boundary. Assert no prompt reaches Prime, partial environment is not admitted, and the record remains honest.

- [ ] **Step 4: Write RED reopen tests**

Before launch, require exact saved contract/package/goal/bundle bytes and an existing prepared environment. After launch, read recursion status without writing, await/inspect the existing runtime, and repeat in-kernel path/callable checks. Missing environment, pending record, wrong source/depth, wrong import origin, wrong interpreter, package drift, goal drift, bundle drift, or target drift must fail `runtime_contract_unavailable` without rebuilding or altering goal/session bytes.

- [ ] **Step 5: Implement runtime preparation in `PrimeChatBackend`**

Keep launch/configuration in the process factory and contract decisions in the backend/runtime-contract owner. Add no second process manager. Retirement on preparation failure uses the existing owned-process path and marks lifecycle failed with the precise reason.

Update `ChatServiceManager` to pass only validated installed product/runtime paths and the qualification/product profile to the broker. Update `AgentChatClient`/`AgentChatTab` to capture and send the exact v2 target once at creation. Reopen uses the recorded profile/contract and never substitutes the service's current defaults.

- [ ] **Step 6: Prove real bootstrap concurrency without provider contact**

Using the isolated Prime agent/session roots and no auth, launch two real RPC sessions against the same contract environment and invoke only the three broker-control commands. Assert both report the same interpreter/import bytes and no partial bootstrap. Repeat with old/new staged package contracts and assert each kernel imports its own package. Dispose all kernels and record zero owned child processes.

- [ ] **Step 7: Run broker preparation tests and Prime build**

```powershell
$offlineRoot = [IO.Path]::GetFullPath("$env:TEMP/rookchat-prime-slices-3-4-offline")
Remove-Item -LiteralPath $offlineRoot -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path "$offlineRoot/agent" -Force | Out-Null
New-Item -ItemType Directory -Path "$offlineRoot/sessions" -Force | Out-Null
$credentialPattern = '(API_KEY|OAUTH_TOKEN|ACCESS_KEY_ID|SECRET_ACCESS_KEY|SESSION_TOKEN|BEARER_TOKEN_BEDROCK|WEB_IDENTITY_TOKEN_FILE|GITHUB_TOKEN|GH_TOKEN|HF_TOKEN|COPILOT_GITHUB_TOKEN|AWS_PROFILE|GOOGLE_APPLICATION_CREDENTIALS)$'
Get-ChildItem Env: | Where-Object Name -Match $credentialPattern | ForEach-Object { Remove-Item -LiteralPath "Env:$($_.Name)" }
Remove-Item Env:PI_CODING_AGENT_DIR -ErrorAction SilentlyContinue
$env:PRIME_AGENT_CODING_AGENT_DIR = "$offlineRoot/agent"
$env:PRIME_AGENT_SESSION_DIR = "$offlineRoot/sessions"
if (@(Get-ChildItem Env: | Where-Object Name -Match $credentialPattern).Count -ne 0) { throw 'Provider credentials remain.' }
if (Test-Path -LiteralPath "$offlineRoot/agent/auth.json") { throw 'Offline Prime auth directory is not empty.' }

$rook='C:/UDEV/Rook/.worktrees/rookchat-prime-primary-backend'
Set-Location $rook
$env:PYTHONPATH="$rook/mcp_server/src"
$python="$rook/mcp_server/.venv/Scripts/python.exe"
& $python -m pytest mcp_server/tests/test_prime_process.py mcp_server/tests/test_prime_rpc_protocol.py mcp_server/tests/test_prime_backend.py mcp_server/tests/test_prime_runtime_preparation.py mcp_server/tests/test_chat_server.py -q
& $python -m py_compile mcp_server/src/rook/agent/chat/prime_process.py mcp_server/src/rook/agent/chat/prime_rpc_protocol.py mcp_server/src/rook/agent/chat/prime_backend.py mcp_server/src/rook/agent/chat/service_main.py
dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug --no-restore --filter "FullyQualifiedName~ChatServiceManagerTests|FullyQualifiedName~AgentChatClientParseTests|FullyQualifiedName~AgentChatPrimeLifecycleTests"

Set-Location D:/prime-agent/.worktrees/rookchat-primary-backend/packages/coding-agent
npm run build
```

Expected: all model-free tests pass; no provider request is possible in the scrubbed environment.

- [ ] **Step 8: Commit broker runtime integration**

```powershell
Set-Location C:/UDEV/Rook/.worktrees/rookchat-prime-primary-backend
git add mcp_server/src/rook/agent/chat src/Rook/UI/Chat/ChatServiceManager.cs src/Rook/UI/Chat/AgentChatClient.cs src/Rook/UI/Chat/AgentChatTab.cs src/Rook.Tests/UI/Chat mcp_server/tests/fixtures/prime_rpc_fake_child.py mcp_server/tests/test_prime_process.py mcp_server/tests/test_prime_rpc_protocol.py mcp_server/tests/test_prime_backend.py mcp_server/tests/test_prime_runtime_preparation.py mcp_server/tests/test_chat_server.py
git commit -m "feat(chat): launch Prime from immutable Rook contracts"
```

---

### Task 8: Project Prime Goals and Preserve Native Stop Semantics

**Files:**
- Modify: `mcp_server/src/rook/agent/chat/prime_rpc_protocol.py`
- Modify: `mcp_server/src/rook/agent/chat/prime_backend.py`
- Modify: `mcp_server/src/rook/agent/chat/server.py`
- Modify: `src/Rook/UI/Chat/AgentChatClient.cs`
- Modify: `src/Rook/UI/Chat/AgentChatTab.cs`
- Modify: `src/Rook/UI/Chat/Resources/chat.html`
- Modify: `src/Rook/UI/Chat/Resources/chat.css`
- Test: `mcp_server/tests/test_prime_rpc_protocol.py`
- Test: `mcp_server/tests/test_prime_backend.py`
- Test: `mcp_server/tests/test_chat_server.py`
- Test: `src/Rook.Tests/UI/Chat/AgentChatClientParseTests.cs`
- Test: `src/Rook.Tests/UI/Chat/AgentChatPrimeLifecycleTests.cs`
- Create: `scripts/rookchat_prime_slices_3_4_qualification.py`
- Create: `mcp_server/tests/test_rookchat_prime_slices_3_4_qualification.py`

**Interfaces:**
- Projects existing `get_state.goal` and `goal_update` events to the panel.
- Persists no broker goal state.
- Preserves user-native `/goal` authority and the existing three Stop outcomes.

- [ ] **Step 1: Write RED goal projection tests**

Project exact Prime-owned goal objective/status from `get_state.goal` on create/reopen and from later `goal_update` events. Reject malformed goal events through the existing protocol-failure path. Assert registry JSON contains no goal field and no inferred completion.

- [ ] **Step 2: Implement goal rows in the existing bounded relay**

Add a `goal_update` row with only the Prime-provided display fields needed by the panel. Coalesce newer status rows in `PromptSubscriptionBuffer` like model updates without dropping terminal text or settlement.

Retain structured tool failures as tool-result evidence in Prime's saved session and correlated relay. Add an end-to-end fake-child case proving one `McpToolError.structured_content` payload remains associated with the same IPython tool call through broker projection and managed parsing; the panel may summarize it but must not replace it with an unstructured success.

- [ ] **Step 3: Write RED native goal authority tests**

Using Prime's existing goal tests plus the fake child, cover:

- model `goal.create()` rejection for active, paused, and budget-limited goals;
- user `/goal <objective>` deliberate replacement;
- `/goal clear` and `/goal stop` native clearing;
- active, paused, complete, and cleared reopen unchanged; and
- target loss refusing Rook work without changing the saved Prime goal bytes.

Do not implement a broker goal endpoint or parser beyond exact panel slash admission.

- [ ] **Step 4: Write RED Stop lifecycle tests with active goals**

Cover:

```text
confirmed abort plus cleanup -> idle, goal still active
natural completion wins -> completed_before_abort, late abort ignored
abort/cleanup uncertain -> failed
```

Then admit a user interjection after confirmed Stop and prove the active goal may continue under Prime on a later ordinary prompt. `/goal resume` is used only for paused state, not aborted active work.

- [ ] **Step 5: Render goal activity without adding task ownership**

Add a compact status line in the existing chat header/status area showing Prime's objective and status. It is informational, not a new task card, progress state machine, or user-facing conversation mode.

- [ ] **Step 6: Add offline completion-discipline validation**

In test/qualification code only, parse retained Prime session entries and reject:

- a completion cell with anything besides one executable `await goal.complete()` statement;
- a later Actor tool call;
- Actor-owned or unowned adapter/Rook activity after the goal-completion event and before the Actor seal; and
- a later callback publishing into a retired prompt generation.

Do not add runtime terminalization or a product execution fence.

Implement this as pure functions in `scripts/rookchat_prime_slices_3_4_qualification.py`; the script has no live subcommands yet. The model-free tests pass synthetic ordered Prime/broker/Rook rows directly to those functions.

- [ ] **Step 7: Run Python, Prime, and managed goal tests**

```powershell
$offlineRoot = [IO.Path]::GetFullPath("$env:TEMP/rookchat-prime-slices-3-4-offline")
Remove-Item -LiteralPath $offlineRoot -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path "$offlineRoot/agent" -Force | Out-Null
New-Item -ItemType Directory -Path "$offlineRoot/sessions" -Force | Out-Null
$credentialPattern = '(API_KEY|OAUTH_TOKEN|ACCESS_KEY_ID|SECRET_ACCESS_KEY|SESSION_TOKEN|BEARER_TOKEN_BEDROCK|WEB_IDENTITY_TOKEN_FILE|GITHUB_TOKEN|GH_TOKEN|HF_TOKEN|COPILOT_GITHUB_TOKEN|AWS_PROFILE|GOOGLE_APPLICATION_CREDENTIALS)$'
Get-ChildItem Env: | Where-Object Name -Match $credentialPattern | ForEach-Object { Remove-Item -LiteralPath "Env:$($_.Name)" }
Remove-Item Env:PI_CODING_AGENT_DIR -ErrorAction SilentlyContinue
$env:PRIME_AGENT_CODING_AGENT_DIR = "$offlineRoot/agent"
$env:PRIME_AGENT_SESSION_DIR = "$offlineRoot/sessions"
if (@(Get-ChildItem Env: | Where-Object Name -Match $credentialPattern).Count -ne 0) { throw 'Provider credentials remain.' }
if (Test-Path -LiteralPath "$offlineRoot/agent/auth.json") { throw 'Offline Prime auth directory is not empty.' }

$rook='C:/UDEV/Rook/.worktrees/rookchat-prime-primary-backend'
Set-Location $rook
$env:PYTHONPATH="$rook/mcp_server/src"
$python="$rook/mcp_server/.venv/Scripts/python.exe"
& $python -m pytest mcp_server/tests/test_prime_rpc_protocol.py mcp_server/tests/test_prime_backend.py mcp_server/tests/test_chat_server.py mcp_server/tests/test_rookchat_prime_slices_3_4_qualification.py -q
dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug --no-restore --filter "FullyQualifiedName~AgentChatClientParseTests|FullyQualifiedName~AgentChatPrimeLifecycleTests"

Set-Location D:/prime-agent/.worktrees/rookchat-primary-backend/packages/coding-agent
npx tsx ../../node_modules/vitest/dist/cli.js --run test/suite/agent-session-goal.test.ts test/rpc-rookchat-runtime.test.ts
```

- [ ] **Step 8: Commit goal projection and panel behavior**

```powershell
Set-Location C:/UDEV/Rook/.worktrees/rookchat-prime-primary-backend
git add mcp_server/src/rook/agent/chat src/Rook/UI/Chat src/Rook.Tests/UI/Chat scripts/rookchat_prime_slices_3_4_qualification.py mcp_server/tests/test_prime_rpc_protocol.py mcp_server/tests/test_prime_backend.py mcp_server/tests/test_chat_server.py mcp_server/tests/test_rookchat_prime_slices_3_4_qualification.py
git commit -m "feat(chat): project Prime goal activity in RookChat"
```

---

### Task 9: Complete the Model-Free Gate and Freeze Slice 3 Contact

**Files:**
- Modify: `scripts/rookchat_prime_slices_3_4_qualification.py`
- Modify: `mcp_server/tests/test_rookchat_prime_slices_3_4_qualification.py`
- Modify: `docs/CURRENT_ARCHITECTURE.md`
- Create: `docs/superpowers/experiments/2026-08-29-rookchat-prime-slice3-observational-v1.json`
- Create: `docs/superpowers/reports/2026-08-29-rookchat-prime-slices-3-4-offline-qualification.md`
- Create: `docs/superpowers/reports/2026-08-29-rookchat-prime-slice3-precontact.md`

**Interfaces:**
- Produces: one external qualification owner for fixture setup, relay capture, evidence sealing, and manifest verification. Product code never imports it.
- Freezes: exact Slice 3 runtime/package/target/task/evidence root and one no-retry execution command.
- Stops: before Rhino, Grasshopper, Rook MCP, provider, or model contact.

- [ ] **Step 1: Write RED qualification-owner tests**

The script accepts explicit subcommands only:

```text
offline-verify
prepare-slice3
run-slice3
seal-slice3
prepare-slice4
run-slice4
seal-slice4
```

At this gate, `run-slice3` and all Slice 4 commands must refuse `precontact_not_authorized` before creating their evidence roots. Test exact evidence-root ownership, no retry field, frozen prompt bytes, trace owner labels, non-self-referential manifest verification, and zero product imports into the script's adjudication helpers.

Add source-to-install transition tests with temporary source/build/install trees. Exact admitted MCP bytes, native RHP, all managed RHP/DLL files, and chat-service manifests pass; missing, stale, extra admitted, wrong-path, wrong-hash, wrong-interpreter, or unsynchronized-worktree-environment owners fail before protocol preparation. Require every dev chat-service manifest to name the exact implementation-worktree `.venv` interpreter. Mirror the existing deploy script's closed cache/build/secret exclusions rather than inventing a second payload definition.

Add one model-free vertical with the real broker and fake Prime/kernel/MCP children that proves: readonly nested mutator refusal before dispatch; full fake mutation admission; structured failure custody through panel parsing; Stop during adapter launch, initialize, and call reaps the child; no-envelope loss is uncertain and is not replayed; late completion cannot publish; and a closed conversation cannot reopen.

- [ ] **Step 2: Implement only offline verification and Slice 3 preparation**

The script may create deterministic fixture setup requests and evidence descriptors, but it must not reason, prompt-repair, choose tools, or evaluate semantics during Actor execution. It talks to the public RookChat product surface only after later authorization.

- [ ] **Step 3: Run the complete Prime model-free gate**

```powershell
$offlineRoot = [IO.Path]::GetFullPath("$env:TEMP/rookchat-prime-slices-3-4-offline")
Remove-Item -LiteralPath $offlineRoot -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path "$offlineRoot/agent" -Force | Out-Null
New-Item -ItemType Directory -Path "$offlineRoot/sessions" -Force | Out-Null
$credentialPattern = '(API_KEY|OAUTH_TOKEN|ACCESS_KEY_ID|SECRET_ACCESS_KEY|SESSION_TOKEN|BEARER_TOKEN_BEDROCK|WEB_IDENTITY_TOKEN_FILE|GITHUB_TOKEN|GH_TOKEN|HF_TOKEN|COPILOT_GITHUB_TOKEN|AWS_PROFILE|GOOGLE_APPLICATION_CREDENTIALS)$'
Get-ChildItem Env: | Where-Object Name -Match $credentialPattern | ForEach-Object { Remove-Item -LiteralPath "Env:$($_.Name)" }
Remove-Item Env:PI_CODING_AGENT_DIR -ErrorAction SilentlyContinue
$env:PRIME_AGENT_CODING_AGENT_DIR = "$offlineRoot/agent"
$env:PRIME_AGENT_SESSION_DIR = "$offlineRoot/sessions"
if (@(Get-ChildItem Env: | Where-Object Name -Match $credentialPattern).Count -ne 0) { throw 'Provider credentials remain.' }
if (Test-Path -LiteralPath "$offlineRoot/agent/auth.json") { throw 'Offline Prime auth directory is not empty.' }

Set-Location D:/prime-agent/.worktrees/rookchat-primary-backend/packages/coding-agent
npx tsx ../../node_modules/vitest/dist/cli.js --run test/args.test.ts test/rpc-rookchat-runtime.test.ts test/rpc-prompt-response-semantics.test.ts test/rpc-client-prompt-settlement.test.ts test/ipython-provisioner.test.ts test/suite/agent-session-goal.test.ts
npm run build
git diff --check
```

- [ ] **Step 4: Run the complete Rook Python gate**

```powershell
$offlineRoot = [IO.Path]::GetFullPath("$env:TEMP/rookchat-prime-slices-3-4-offline")
Remove-Item -LiteralPath $offlineRoot -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path "$offlineRoot/agent" -Force | Out-Null
New-Item -ItemType Directory -Path "$offlineRoot/sessions" -Force | Out-Null
$credentialPattern = '(API_KEY|OAUTH_TOKEN|ACCESS_KEY_ID|SECRET_ACCESS_KEY|SESSION_TOKEN|BEARER_TOKEN_BEDROCK|WEB_IDENTITY_TOKEN_FILE|GITHUB_TOKEN|GH_TOKEN|HF_TOKEN|COPILOT_GITHUB_TOKEN|AWS_PROFILE|GOOGLE_APPLICATION_CREDENTIALS)$'
Get-ChildItem Env: | Where-Object Name -Match $credentialPattern | ForEach-Object { Remove-Item -LiteralPath "Env:$($_.Name)" }
Remove-Item Env:PI_CODING_AGENT_DIR -ErrorAction SilentlyContinue
$env:PRIME_AGENT_CODING_AGENT_DIR = "$offlineRoot/agent"
$env:PRIME_AGENT_SESSION_DIR = "$offlineRoot/sessions"
if (@(Get-ChildItem Env: | Where-Object Name -Match $credentialPattern).Count -ne 0) { throw 'Provider credentials remain.' }
if (Test-Path -LiteralPath "$offlineRoot/agent/auth.json") { throw 'Offline Prime auth directory is not empty.' }

$rook='C:/UDEV/Rook/.worktrees/rookchat-prime-primary-backend'
Set-Location $rook
$env:PYTHONPATH="$rook/mcp_server/src"
$python="$rook/mcp_server/.venv/Scripts/python.exe"
& $python -m pytest mcp_server/tests/test_prime_registry.py mcp_server/tests/test_prime_runtime_contract.py mcp_server/tests/test_prime_rpc_protocol.py mcp_server/tests/test_prime_process.py mcp_server/tests/test_prime_backend.py mcp_server/tests/test_prime_runtime_preparation.py mcp_server/tests/test_rook_full_product_adapter.py mcp_server/tests/test_bridge.py mcp_server/tests/test_multi_instance_targeting.py mcp_server/tests/test_gh_authoring_capability_routing.py mcp_server/tests/test_panel_locked_gh_document_switching.py mcp_server/tests/test_chat_server.py mcp_server/tests/test_chat_integration.py mcp_server/tests/test_rookchat_prime_slices_3_4_qualification.py -q
& $python -m compileall -q mcp_server/src/rook integrations/prime/skills/rook-full/src scripts/rookchat_prime_slices_3_4_qualification.py
```

- [ ] **Step 5: Run the complete managed and native gate**

```powershell
$rook='C:/UDEV/Rook/.worktrees/rookchat-prime-primary-backend'
Set-Location $rook
dotnet build src/Rook/Rook.csproj -c Debug --no-restore
dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug --no-restore
cmd /c "call \"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat\" x64 -vcvars_ver=14.44 && msbuild src\RookNative\RookNative.vcxproj /t:Build /p:Configuration=Debug /p:Platform=x64 /p:VCToolsVersion=14.44.35207"
git diff --check
```

- [ ] **Step 6: Promote the tested worktree through the existing local-deployment path**

Rhino and all owned `python -m rook`/chat-service workers must be closed. The exact shell checks that condition, runs the repository-owned deploy script without rebuilding different bytes, and refuses on any failure:

```powershell
$rook='C:/UDEV/Rook/.worktrees/rookchat-prime-primary-backend'
$blockers = @(Get-CimInstance Win32_Process | Where-Object {
    $_.Name -match '^Rhino(?:\.exe)?$' -or
    ($_.CommandLine -and $_.CommandLine -match 'rook\.agent\.chat\.service_main|python(?:\.exe)?\s+-m\s+rook')
})
if ($blockers.Count -ne 0) { throw "Deployment blockers remain: $($blockers.ProcessId -join ',')" }
Set-Location $rook
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/deploy-local-testing.ps1 -Configuration Debug -SkipBuild -UseRepoVenv
if ($LASTEXITCODE -ne 0) { throw 'Local product deployment failed.' }
```

Expected: the script deploys the exact already-tested native and managed Debug outputs, syncs the worktree MCP/AppData payload, writes the dev `RookChatService.json`, verifies the effective branch-local runtime, and does not run a live smoke.

- [ ] **Step 7: Execute the model-free runtime/package and installed-byte preflight**

The command that can launch real Prime repeats the complete scrub in the same shell:

```powershell
$offlineRoot = [IO.Path]::GetFullPath("$env:TEMP/rookchat-prime-slices-3-4-offline")
Remove-Item -LiteralPath $offlineRoot -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path "$offlineRoot/agent" -Force | Out-Null
New-Item -ItemType Directory -Path "$offlineRoot/sessions" -Force | Out-Null
$credentialPattern = '(API_KEY|OAUTH_TOKEN|ACCESS_KEY_ID|SECRET_ACCESS_KEY|SESSION_TOKEN|BEARER_TOKEN_BEDROCK|WEB_IDENTITY_TOKEN_FILE|GITHUB_TOKEN|GH_TOKEN|HF_TOKEN|COPILOT_GITHUB_TOKEN|AWS_PROFILE|GOOGLE_APPLICATION_CREDENTIALS)$'
Get-ChildItem Env: | Where-Object Name -Match $credentialPattern | ForEach-Object { Remove-Item -LiteralPath "Env:$($_.Name)" }
Remove-Item Env:PI_CODING_AGENT_DIR -ErrorAction SilentlyContinue
$env:PRIME_AGENT_CODING_AGENT_DIR = "$offlineRoot/agent"
$env:PRIME_AGENT_SESSION_DIR = "$offlineRoot/sessions"
if (@(Get-ChildItem Env: | Where-Object Name -Match $credentialPattern).Count -ne 0) { throw 'Provider credentials remain.' }
if (Test-Path -LiteralPath "$offlineRoot/agent/auth.json") { throw 'Offline Prime auth directory is not empty.' }

$rook='C:/UDEV/Rook/.worktrees/rookchat-prime-primary-backend'
Set-Location "$rook/mcp_server"
uv sync --frozen --check
if ($LASTEXITCODE -ne 0) { throw 'Worktree Python environment drifted from uv.lock.' }
Set-Location $rook
$env:PYTHONPATH="$rook/mcp_server/src"
$python="$rook/mcp_server/.venv/Scripts/python.exe"
& $python scripts/rookchat_prime_slices_3_4_qualification.py offline-verify
if ($LASTEXITCODE -ne 0) { throw 'Offline runtime/package/deployment verification failed.' }
```

`offline-verify` compares the complete admitted installed `mcp_server` payload against its worktree source under the deploy script's closed exclusions, compares native and all managed RHP/DLL outputs against the installed plugin paths, requires every generated `RookChatService.json` to name the exact checked worktree interpreter, and then verifies the built Prime bundle plus staged readonly/full packages. Retain the `uv.lock` hash, `uv sync --frozen --check` result, exact worktree interpreter, source/build/installed inventories, bundle/goal/package/contract hashes, actual root-kernel interpreter/import paths, recursion source/status, same-contract and old/new concurrency results, child cleanup, and zero provider credential facts. A missing or changed installed owner fails before protocol freeze.

- [ ] **Step 8: Freeze the exact Slice 3 protocol**

The protocol must bind:

- exact Rook and Prime commits/tree/bundle manifests;
- exact source/build/installed deployment inventory and chat-service manifest hashes;
- exact `mcp_server/uv.lock` hash and implementation-worktree interpreter path;
- exact goal and Rook package manifests;
- `readonly` contract fingerprint and kernel path;
- model/provider/thinking/auth disclosure selected for the live smoke;
- PID/ticks/Rhino serial/intended GH GUID capture rules;
- exact prompt from the specification;
- fresh conversation, one execution, zero retries;
- durable evidence root absent before contact;
- no goal, no mutation attempt/receipt, both definitions unchanged; and
- exact seal/manifest procedure.

Do not prepare Rhino or create either GH document yet.

- [ ] **Step 9: Write the offline and Slice 3 pre-contact reports**

Report exact commands, counts, custody hashes, closed test matrices, branch-local imports, provider-contact exclusion, installed product paths, and explicit non-claims. Include the exact proposed commands:

```powershell
$rook='C:/UDEV/Rook/.worktrees/rookchat-prime-primary-backend'
$python="$rook/mcp_server/.venv/Scripts/python.exe"
Set-Location "$rook/mcp_server"
uv sync --frozen --check
if ($LASTEXITCODE -ne 0) { throw 'Worktree Python environment drifted from uv.lock.' }
Set-Location $rook
& $python scripts/rookchat_prime_slices_3_4_qualification.py prepare-slice3 --protocol docs/superpowers/experiments/2026-08-29-rookchat-prime-slice3-observational-v1.json
& $python scripts/rookchat_prime_slices_3_4_qualification.py run-slice3 --protocol docs/superpowers/experiments/2026-08-29-rookchat-prime-slice3-observational-v1.json
```

- [ ] **Step 10: Commit the offline gate and stop**

```powershell
git add scripts/rookchat_prime_slices_3_4_qualification.py mcp_server/tests/test_rookchat_prime_slices_3_4_qualification.py docs/CURRENT_ARCHITECTURE.md docs/superpowers/experiments/2026-08-29-rookchat-prime-slice3-observational-v1.json docs/superpowers/reports/2026-08-29-rookchat-prime-slices-3-4-offline-qualification.md docs/superpowers/reports/2026-08-29-rookchat-prime-slice3-precontact.md
git commit -m "test(chat): qualify Prime Rook runtime offline"
git status --short
git -C D:/prime-agent/.worktrees/rookchat-primary-backend status --short
```

Expected: both worktrees clean. Stop for independent implementation review. Do not contact Rhino, Grasshopper, Rook MCP, Prime provider, or a model until the reviewer authorizes the exact Slice 3 command.

---

### Task 10: Execute and Seal the Single Slice 3 Observational Run

**Files:**
- Preserve byte-for-byte: `docs/superpowers/experiments/2026-08-29-rookchat-prime-slice3-observational-v1.json`.
- Create: `docs/superpowers/reports/2026-08-29-rookchat-prime-slice3-observational-v1-execution.md`
- Evidence: durable root named exactly by the frozen protocol.

**Interfaces:**
- Consumes: independently approved Task 9 commit, installed product build, fresh Rhino/GH fixture, exact readonly runtime contract, and the exact approved prompt.
- Produces: one sealed observational result and a separate review gate before any full-profile conversation is prepared.

- [ ] **Step 1: Reverify frozen bytes and absence of the evidence root**

Require clean Rook and Prime worktrees; `uv sync --frozen --check` against the implementation-worktree environment; exact protocol, runner, package, bundle, goal, contract, `uv.lock`, worktree-interpreter, and installed-file manifest hashes; exact subscription-auth disclosure; the independent review authorization recorded outside the frozen protocol in the execution evidence/report; and no existing Slice 3 evidence root. Any mismatch stops before fixture preparation. Never rewrite the frozen protocol to record authorization or repair the environment during this check.

- [ ] **Step 2: Prepare the deterministic two-document fixture outside Actor custody**

Run the approved `prepare-slice3` command after Rhino and Grasshopper are open. Create:

- one intended partially broken adjustable X-axis point-row definition;
- one distinct decoy GH definition;
- canonical `GH_Document.DocumentID` values for both;
- frozen controls, components, wiring, diagnostics, and known defect facts; and
- complete structural baselines for both definitions.

Make the intended definition active, then capture the Rhino PID, independently published native process ticks, Rhino document serial, and intended GH GUID. Do not start Prime until all identities match.

- [ ] **Step 3: Start one fresh readonly conversation and send the exact prompt once**

```text
Inspect the currently bound Grasshopper definition without modifying it. Report its existing controls, components, wiring, current errors or warnings, and whether the intended adjustable X-axis point-row behavior appears complete. Stop after giving an evidence-grounded assessment.
```

Evaluators remain silent. Do not retry, repair the prompt, switch the active definition, change model settings, or tune the skill.

- [ ] **Step 4: Settle and seal before interpretation**

After broker settlement, retain the registry record, Prime saved session, correlated relay rows, Rook structured results, target checks, per-call startup latency, and both post-run structural snapshots. Require no goal, no admitted mutation attempt, no mutation receipt, and no operation resolved against the decoy. Generate and independently verify the non-self-referential evidence manifest. The repository execution report is written afterward and is not a member of that manifest.

- [ ] **Step 5: Perform the exterior finite-fact review**

Compare only the final answer with the pre-frozen fixture facts. Do not feed the comparison back to Prime and do not invent a runtime evaluator. Keep target/profile custody, structural nonmutation, factual answer quality, broker settlement, and process cleanup as separate outcomes.

- [ ] **Step 6: Write and commit the honest Slice 3 report**

Include actual commands, hashes, model/auth disclosure, time/tokens/calls, startup latencies, goal state, mutation/receipt count, intended/decoy before-after hashes, answer/fact comparison, manifest verification, and non-claims.

```powershell
git add docs/superpowers/reports/2026-08-29-rookchat-prime-slice3-observational-v1-execution.md
git commit -m "docs: record Prime RookChat observational qualification"
git status --short
```

Stop for independent review. Slice 4 preparation is not authorized merely because Slice 3 appears successful.

---

### Task 11: Freeze the Fresh Slice 4 Full-Profile Contact Package

**Files:**
- Create: `docs/superpowers/experiments/2026-08-29-rookchat-prime-slice4-point-row-v1.json`
- Create: `docs/superpowers/reports/2026-08-29-rookchat-prime-slice4-point-row-v1-precontact.md`
- Modify: `mcp_server/tests/test_rookchat_prime_slices_3_4_qualification.py`

**Interfaces:**
- Consumes: independently approved Slice 3 evidence, unchanged seeded intended definition, unchanged decoy definition, exact full-profile contract, and the pinned point-row evaluator bytes.
- Produces: one immutable Slice 4 protocol, an absent fresh evidence root, and an exact no-retry live command.
- Stops: before any full-profile Prime conversation, provider/model prompt, or Actor mutation.

- [ ] **Step 1: Prove Slice 3 left both definitions unchanged**

Reverify the sealed Slice 3 manifest and compare the retained intended/decoy post-run snapshots to their original baselines. Refuse preparation if either changed or if the active intended GH identity no longer matches.

- [ ] **Step 2: Rehash the four approved evaluator owners**

Require exact SHA-256:

```text
scripts/grasshopper_point_row_acceptance.py
38DD024A0FDFF830BEFDFA5434976B350897C9C482141AB5D1D34CC182D40095

scripts/grasshopper_point_row_acceptance.json
A4836173494C2396FB60E0C0FAF889161980C26C078987F8CA5CA847B6A4367F

mcp_server/src/rook/gh_behavioral_acceptance.py
A3895FCE82A987DD06C2DA88F47663FBA689C7609FB85EAC151AC79F7872227D

mcp_server/src/rook/mcp_tool_profiles.py
E08C6BF3E74758915336D4B2B9DDE5E986664DEBCF8DD82812657ECE99CA2329
```

Any mismatch stops for renewed review. Do not modify these files to fit the new run.

- [ ] **Step 3: Write RED Slice 4 protocol-drift tests**

Require a fresh conversation/evidence root, `full` contract fingerprint, same intended target, exact prompt, one execution, zero retries, silent evaluator, Actor/evaluator owner labels, and explicit evidence-seal boundary. Reject reuse/elevation of the Slice 3 conversation or kernel.

- [ ] **Step 4: Freeze Actor and evaluator admission rules**

The protocol must predeclare:

- `goal.get()` then model-created goal before the first attempted admitted mutator;
- bounded attributable mutations with unique receipts and no replay;
- preservation of useful components and decoy structure;
- selected control defaults and required temporary perturbation/restoration;
- `R` as the last actual committed solve-relevant restoration mutation;
- same-`R` readiness and fenced snapshot;
- dedicated completion cell and no later Actor tool;
- Actor settlement and evidence seal before evaluator contact; and
- four independent outcome dimensions.

- [ ] **Step 5: Run the complete model-free gate again**

Rerun Task 9's exact Python, managed, native, manifest, installed-byte, target, Stop, goal, and cleanup commands. For the Prime/kernel portion, use this complete preamble and command in one fresh shell rather than relying on Task 9's former process environment:

```powershell
$offlineRoot = [IO.Path]::GetFullPath("$env:TEMP/rookchat-prime-slices-3-4-offline")
Remove-Item -LiteralPath $offlineRoot -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path "$offlineRoot/agent" -Force | Out-Null
New-Item -ItemType Directory -Path "$offlineRoot/sessions" -Force | Out-Null
$credentialPattern = '(API_KEY|OAUTH_TOKEN|ACCESS_KEY_ID|SECRET_ACCESS_KEY|SESSION_TOKEN|BEARER_TOKEN_BEDROCK|WEB_IDENTITY_TOKEN_FILE|GITHUB_TOKEN|GH_TOKEN|HF_TOKEN|COPILOT_GITHUB_TOKEN|AWS_PROFILE|GOOGLE_APPLICATION_CREDENTIALS)$'
Get-ChildItem Env: | Where-Object Name -Match $credentialPattern | ForEach-Object { Remove-Item -LiteralPath "Env:$($_.Name)" }
Remove-Item Env:PI_CODING_AGENT_DIR -ErrorAction SilentlyContinue
$env:PRIME_AGENT_CODING_AGENT_DIR = "$offlineRoot/agent"
$env:PRIME_AGENT_SESSION_DIR = "$offlineRoot/sessions"
if (@(Get-ChildItem Env: | Where-Object Name -Match $credentialPattern).Count -ne 0) { throw 'Provider credentials remain.' }
if (Test-Path -LiteralPath "$offlineRoot/agent/auth.json") { throw 'Offline Prime auth directory is not empty.' }

Set-Location D:/prime-agent/.worktrees/rookchat-primary-backend/packages/coding-agent
npx tsx ../../node_modules/vitest/dist/cli.js --run test/args.test.ts test/rpc-rookchat-runtime.test.ts test/rpc-prompt-response-semantics.test.ts test/rpc-client-prompt-settlement.test.ts test/ipython-provisioner.test.ts test/suite/agent-session-goal.test.ts
npm run build
if ($LASTEXITCODE -ne 0) { throw 'Prime model-free gate failed.' }

$rook='C:/UDEV/Rook/.worktrees/rookchat-prime-primary-backend'
Set-Location "$rook/mcp_server"
uv sync --frozen --check
if ($LASTEXITCODE -ne 0) { throw 'Worktree Python environment drifted from uv.lock.' }
Set-Location $rook
$env:PYTHONPATH="$rook/mcp_server/src"
$python="$rook/mcp_server/.venv/Scripts/python.exe"
& $python -m pytest mcp_server/tests/test_prime_registry.py mcp_server/tests/test_prime_runtime_contract.py mcp_server/tests/test_prime_rpc_protocol.py mcp_server/tests/test_prime_process.py mcp_server/tests/test_prime_backend.py mcp_server/tests/test_prime_runtime_preparation.py mcp_server/tests/test_rook_full_product_adapter.py mcp_server/tests/test_bridge.py mcp_server/tests/test_multi_instance_targeting.py mcp_server/tests/test_gh_authoring_capability_routing.py mcp_server/tests/test_panel_locked_gh_document_switching.py mcp_server/tests/test_chat_server.py mcp_server/tests/test_chat_integration.py mcp_server/tests/test_rookchat_prime_slices_3_4_qualification.py -q
if ($LASTEXITCODE -ne 0) { throw 'Rook model-free gate failed.' }
```

This is the required pre-mutation review evidence, not another architecture pass. It does not redeploy or alter the installed product; installed inventory is rehashed and must still equal the approved Task 9 deployment.

- [ ] **Step 6: Write the exact pre-contact report and command**

The one authorized command after review will be:

```powershell
$rook='C:/UDEV/Rook/.worktrees/rookchat-prime-primary-backend'
$python="$rook/mcp_server/.venv/Scripts/python.exe"
Set-Location "$rook/mcp_server"
uv sync --frozen --check
if ($LASTEXITCODE -ne 0) { throw 'Worktree Python environment drifted from uv.lock.' }
Set-Location $rook
& $python scripts/rookchat_prime_slices_3_4_qualification.py run-slice4 --protocol docs/superpowers/experiments/2026-08-29-rookchat-prime-slice4-point-row-v1.json
```

The report records the absent evidence root, exact target identities, full runtime contract, evaluator hashes, clean worktrees, and explicit prohibition on retry/prompt repair.

- [ ] **Step 7: Commit and stop for independent mutating-contact review**

```powershell
git add docs/superpowers/experiments/2026-08-29-rookchat-prime-slice4-point-row-v1.json docs/superpowers/reports/2026-08-29-rookchat-prime-slice4-point-row-v1-precontact.md mcp_server/tests/test_rookchat_prime_slices_3_4_qualification.py
git commit -m "test(chat): freeze Prime RookChat mutating qualification"
git status --short
```

Stop. Do not create the full conversation, contact the model, or mutate Grasshopper until independent review authorizes this exact command.

---

### Task 12: Execute, Seal, Evaluate, and Report the Single Slice 4 Run

**Files:**
- Create: `docs/superpowers/reports/2026-08-29-rookchat-prime-slice4-point-row-v1-execution.md`
- Modify: `docs/CURRENT_ARCHITECTURE.md` only after the result is known, with qualified wording.
- Evidence: durable Slice 4 root named exactly by the protocol.

**Interfaces:**
- Consumes: independently approved Task 11 commit and exact frozen command.
- Produces: one sealed Actor trace, one separately owned evaluator trace, one evidence manifest, four independent outcomes, and a bounded product qualification statement if all gates pass.

- [ ] **Step 1: Reverify all frozen inputs before target or model contact**

Require `uv sync --frozen --check` against the implementation-worktree environment; exact protocol, script, Rook/Prime commits, bundle, package/goal manifests, full contract, `uv.lock`, worktree interpreter, evaluator hashes, target identities, clean worktrees, installed paths, and absent evidence root. Refuse any extra CLI argument, process override, accepted root, retry count, environment repair, or configuration change.

- [ ] **Step 2: Start one fresh full conversation and send the exact prompt**

```text
The current Grasshopper document contains a partially broken adjustable X-axis point-row definition. Repair it in place so the existing Start, Step, and Count controls determine the first X coordinate, spacing, and point count, with Y and Z fixed at zero. Preserve working components where practical, resolve any current errors or warnings, and verify the behavior before stopping.
```

The prompt does not mention Prime goals or reveal the repair. The persistent product contract owns that guidance.

- [ ] **Step 3: Allow the Actor to settle without evaluator feedback**

Record the complete existing product relay and Rook envelopes. Do not intervene, steer, retry, repair, or evaluate during execution. A Stop, structured error, or incomplete goal follows the already-qualified product semantics and is preserved.

- [ ] **Step 4: Seal Actor evidence before evaluator activity**

After broker settlement:

1. freeze the Actor call/result chain and mutation receipts;
2. select `R` from Actor-owned authentic receipts only;
3. preserve the Actor same-`R` readiness result and fenced snapshot;
4. verify the dedicated one-statement completion cell;
5. record Prime goal complete state and panel goal projection;
6. record broker settlement and zero owned process/stdio children; and
7. generate the Actor evidence seal.

Any Actor-owned or unowned activity after goal completion and before this seal, any later Actor tool call, ambiguous mutation replay, duplicate receipt, or unowned call makes the Actor dimension incomplete. Do not reinterpret evaluator receipts as Actor evidence.

- [ ] **Step 5: Start the separately identified silent evaluator trace**

Reverify all four evaluator hashes, then run the existing finite point-row evaluator. Its perturbations and restoration occur under an evaluator owner ID after the Actor seal. Preserve every evaluator receipt separately and verify final structural equivalence to the repaired/restored Actor state.

- [ ] **Step 6: Adjudicate four dimensions independently**

Report separately:

1. graph and finite behavior;
2. Rhino/GH target, mutation, receipt, and fenced-evidence custody;
3. Prime goal creation, visible active projection, completion discipline, and final complete state; and
4. broker/panel settlement and process cleanup.

A correct graph does not compensate for missing goal completion. Goal completion does not compensate for target/evidence failure. Any incomplete dimension prevents the combined qualification.

- [ ] **Step 7: Seal and independently verify the complete evidence root**

Generate a non-self-referential manifest over frozen configuration, registry, Prime session/projections, package/runtime manifests, target records, Actor trace/seal, before-after snapshots, evaluator trace, latency, and process cleanup. The repository execution report does not exist yet and is explicitly outside this evidence manifest. Recompute every evidence entry and the manifest SHA-256 before interpretation claims success.

- [ ] **Step 8: Write the execution report and narrow architecture status**

Write the repository report only after Step 7 seals and verifies evidence. Cite the immutable evidence-manifest SHA-256 and exact entry count; do not add the report to that manifest. If all four dimensions pass, use only the specification's bounded product statement. If any fail, preserve the exact incomplete result and diagnosis. Do not claim hostile-Python containment, universal correctness, semantic certification, default-backend cutover, subagents, images/web, pooling, or migration.

- [ ] **Step 9: Run final offline verification and commit**

Rerun the exact Task 9 model-free suites, Prime build, .NET tests, native build, Python compilation, installed-inventory comparison, `git diff --check`, evidence-manifest verification, and zero-owned-process checks. The Prime build/test shell is self-contained below; no live credentials are needed after Actor/evaluator settlement:

```powershell
$offlineRoot = [IO.Path]::GetFullPath("$env:TEMP/rookchat-prime-slices-3-4-offline")
Remove-Item -LiteralPath $offlineRoot -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path "$offlineRoot/agent" -Force | Out-Null
New-Item -ItemType Directory -Path "$offlineRoot/sessions" -Force | Out-Null
$credentialPattern = '(API_KEY|OAUTH_TOKEN|ACCESS_KEY_ID|SECRET_ACCESS_KEY|SESSION_TOKEN|BEARER_TOKEN_BEDROCK|WEB_IDENTITY_TOKEN_FILE|GITHUB_TOKEN|GH_TOKEN|HF_TOKEN|COPILOT_GITHUB_TOKEN|AWS_PROFILE|GOOGLE_APPLICATION_CREDENTIALS)$'
Get-ChildItem Env: | Where-Object Name -Match $credentialPattern | ForEach-Object { Remove-Item -LiteralPath "Env:$($_.Name)" }
Remove-Item Env:PI_CODING_AGENT_DIR -ErrorAction SilentlyContinue
$env:PRIME_AGENT_CODING_AGENT_DIR = "$offlineRoot/agent"
$env:PRIME_AGENT_SESSION_DIR = "$offlineRoot/sessions"
if (@(Get-ChildItem Env: | Where-Object Name -Match $credentialPattern).Count -ne 0) { throw 'Provider credentials remain.' }
if (Test-Path -LiteralPath "$offlineRoot/agent/auth.json") { throw 'Offline Prime auth directory is not empty.' }

Set-Location D:/prime-agent/.worktrees/rookchat-primary-backend/packages/coding-agent
npx tsx ../../node_modules/vitest/dist/cli.js --run test/args.test.ts test/rpc-rookchat-runtime.test.ts test/rpc-prompt-response-semantics.test.ts test/rpc-client-prompt-settlement.test.ts test/ipython-provisioner.test.ts test/suite/agent-session-goal.test.ts
npm run build
if ($LASTEXITCODE -ne 0) { throw 'Prime final model-free gate failed.' }

$rook='C:/UDEV/Rook/.worktrees/rookchat-prime-primary-backend'
Set-Location "$rook/mcp_server"
uv sync --frozen --check
if ($LASTEXITCODE -ne 0) { throw 'Worktree Python environment drifted from uv.lock.' }
Set-Location $rook
$env:PYTHONPATH="$rook/mcp_server/src"
$python="$rook/mcp_server/.venv/Scripts/python.exe"
& $python -m pytest mcp_server/tests/test_prime_registry.py mcp_server/tests/test_prime_runtime_contract.py mcp_server/tests/test_prime_rpc_protocol.py mcp_server/tests/test_prime_process.py mcp_server/tests/test_prime_backend.py mcp_server/tests/test_prime_runtime_preparation.py mcp_server/tests/test_rook_full_product_adapter.py mcp_server/tests/test_bridge.py mcp_server/tests/test_multi_instance_targeting.py mcp_server/tests/test_gh_authoring_capability_routing.py mcp_server/tests/test_panel_locked_gh_document_switching.py mcp_server/tests/test_chat_server.py mcp_server/tests/test_chat_integration.py mcp_server/tests/test_rookchat_prime_slices_3_4_qualification.py -q
if ($LASTEXITCODE -ne 0) { throw 'Rook final model-free gate failed.' }
```

```powershell
git add docs/CURRENT_ARCHITECTURE.md docs/superpowers/reports/2026-08-29-rookchat-prime-slice4-point-row-v1-execution.md
git commit -m "docs: record Prime RookChat mutating qualification"
git status --short
git -C D:/prime-agent/.worktrees/rookchat-primary-backend status --short
```

Expected: both worktrees clean. Stop for independent result review. Do not make Prime the default backend or begin deferred product work.

## Review Gates

This plan contains three absorbing review stops:

1. **Before implementation:** the exact plan commit is independently approved and named in the implementation `/goal`.
2. **Before Slice 3 live contact:** Tasks 0-9 pass, both worktrees are clean, the readonly protocol/evidence root are frozen, and independent review authorizes the exact command.
3. **Before Slice 4 mutating contact:** Slice 3 is sealed and independently accepted; Task 11 freezes a fresh full conversation and exact evaluator bytes; independent review authorizes the exact command.

No later task may infer authorization from an earlier gate. A failed gate authorizes diagnosis and a scoped offline correction only, not silent retry or live continuation.

## Deferred Work

The following remain explicitly outside this plan even if Slice 4 passes:

- Prime-backed RookChat default cutover;
- images, web search, steering, and prompt rewriting;
- Prime subagents or recursive Rook access;
- automatic profile/lane routing;
- arbitrary Python/process/network containment;
- MCP child pooling;
- runtime-contract migration, reconstruction locks, and garbage collection;
- packaging-wide enablement or installer cutover;
- another live task, model comparison, or semantic evaluator; and
- supervisor, terminalization, or broker-owned goal/task machinery.
