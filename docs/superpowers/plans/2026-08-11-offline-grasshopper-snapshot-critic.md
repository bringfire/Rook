# Offline Grasshopper Snapshot Critic Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:executing-plans to implement this plan task-by-task. This tightly
> ordered one-call experiment must use Inline Execution; do not dispatch
> parallel or subagent work.

**Goal:** Run one isolated local Qwen critic over retained intent-plus-snapshot
evidence, then—only if it qualifies—implement the smallest reusable no-contact
projection, strict-result, completion-gate, and artifact boundary.

**Architecture:** A disposable TypeScript operator calls Prime's existing
`streamSimple` provider with no tools and preserves the one response. A single
pure Python module then owns retained-snapshot admission, exact projection,
injected-Critic invocation, strict closed-result loading, completion gating,
and create-new artifact output; it is not wired into ChatRunner, Prime, MCP, or
runtime completion.

**Tech Stack:** Python 3.11+, pytest, TypeScript/tsx from the existing Prime
checkout, Prime `@earendil-works/pi-ai`, local Ollama `qwen3.6:35b`.

## Global Constraints

- Retained evidence SHA-256 must remain
  `4B3E44B853D7EEC44D6052D2C4442BEB4CEE46BD3E728C14781FCDDB43C87AE8`.
- The Critic sees only the exact original intent and authentic final snapshot.
- Exactly one local Qwen provider dispatch; `maxRetries=0`; no prompt tuning.
- No Actor, repair, Opus, external provider, Rhino, Grasshopper, MCP,
  deployment, or canvas contact.
- No ChatRunner/Prime runtime integration or permanent model-judge authority.
- Production scope is at most one Python module; tests are one focused module.
- Stop without implementation if the Critic call or strict result admission
  does not meet the experiment's semantic success criteria.

---

## File map

**Disposable qualification artifacts (outside the repository):**

- `C:/Users/bring/AppData/Local/Temp/rook-qwen-offline-critic-v1/projection.json`
  — exact Critic input.
- `.../critic-prompt.txt` — reviewed neutral prompt plus the projection.
- `.../critic-call.ts` — one tool-free Prime provider call.
- `.../prime-assistant.json` — exact returned Prime assistant message.
- `.../critic-raw.txt` — exact visible response text.
- `.../critic-result.json` — admitted closed result, created only after strict
  validation.

**Repository files:**

- Create `mcp_server/src/rook/agent/experimental_snapshot_critic.py` — the
  complete reusable no-contact boundary.
- Create `mcp_server/tests/test_experimental_snapshot_critic.py` — retained
  evidence and fake-backed causal tests.
- Create
  `docs/superpowers/reports/2026-08-11-offline-grasshopper-snapshot-critic-result.md`
  — observed evidence, claims, and non-claims.

---

### Task 1: One isolated Qwen Critic qualification

**Files:**

- Create outside repo: the six disposable files listed above.
- Read only:
  `C:/Users/bring/AppData/Local/Temp/prime-rook-qwen-strict-retest-v1/local/operator/final-inspection.jsonl`
- Read only:
  `C:/Users/bring/AppData/Local/Temp/prime-rook-qwen-strict-retest-v1/local/agent/models.json`

**Interfaces:**

- Consumes: exact intent and the two-row final-inspection JSONL.
- Produces: one raw Prime assistant message and, if admissible, one closed
  discrepancy artifact.

- [ ] **Step 1: Recheck retained evidence before creating artifacts**

Run:

```powershell
Get-FileHash -Algorithm SHA256 `
  'C:/Users/bring/AppData/Local/Temp/prime-rook-qwen-strict-retest-v1/local/operator/final-inspection.jsonl'
```

Expected: exact reviewed hash from Global Constraints.

- [ ] **Step 2: Create the projection with a strict disposable loader**

The loader must require two exact JSONL rows, the exact `gh_snapshot` request,
`success=true`, an object `data`, no duplicate keys, and strict UTF-8. Write:

```json
{
  "schema": "rook.experimental.grasshopper_snapshot_critic_input:v1",
  "intent": "Create a Grasshopper definition that generates a row of points along the X axis using adjustable Start, Step, and Count controls, with Y and Z fixed at zero.",
  "snapshot": {
    "success": true,
    "data": {}
  }
}
```

The `snapshot` value is the exact result payload; the displayed empty `data`
above is replaced by the retained value without interpretation.

- [ ] **Step 3: Create the neutral Critic prompt**

Use this instruction text verbatim before the JSON projection:

```text
You are an independent semantic critic. Determine whether the supplied final
Grasshopper snapshot satisfies the supplied user intent. Use only those two
inputs. Do not infer execution history, unseen canvas state, tool use, or any
Actor claim. Compare requested interface semantics, wiring, diagnostics, and
observed output cardinality literally. If the snapshot cannot establish a
claim, say that evidence is insufficient.

Return exactly one JSON object and no Markdown. It must contain exactly:
verdict, satisfied_claims, discrepancies, evidence_references, and
repair_requirements. verdict is pass, fail, or insufficient_evidence. The
first, second, and fifth fields are arrays of unique nonblank strings.
evidence_references is an array of objects containing exactly claim and
pointers; claim must equal one satisfied claim or discrepancy, and pointers
must be nonempty JSON Pointer arrays resolving into the supplied projection.
Every satisfied claim and discrepancy must have exactly one reference object.
For pass, discrepancies and repair_requirements are empty. For fail, both are
nonempty. Repair requirements state semantic postconditions only, not tool
calls or prescribed component topology.
```

Do not mention the known diagnosis, Series, or an expected verdict.

- [ ] **Step 4: Create and statically inspect the one-call Prime operator**

The operator must:

```typescript
const stream = streamSimple(
  model,
  {
    systemPrompt: criticInstruction,
    messages: [{ role: "user", content: projectionJson, timestamp: 0 }],
    tools: [],
  },
  {
    reasoning: "medium",
    apiKey: resolvedAuth.apiKey,
    headers: resolvedAuth.headers,
    maxRetries: 0,
    timeoutMs: 1_800_000,
  },
);
const assistant = await stream.result();
```

It must require `stopReason == "stop"`, reject tool-call blocks, write the
complete assistant message create-new, and write the concatenated text blocks
create-new. It contains no loop around `streamSimple` and imports no Agent,
tool, skill, MCP, or filesystem-mutation capability beyond its own artifact
writes.

- [ ] **Step 5: Run exactly one call**

Run the operator once through Prime's existing `tsx` installation. Do not rerun
after any result.

Expected: one successful assistant response and no tool call.

- [ ] **Step 6: Strictly load and assess the response**

Use the design's exact-key, type, coherence, uniqueness, UTF-8, and resolving
JSON-Pointer rules. If admission fails, preserve the raw artifacts and stop.

Qualification passes only if the admitted result independently establishes all
five semantic observations in the design. This assessment is performed after
the call and is never part of the prompt.

- [ ] **Step 7: Hash all disposable artifacts and recheck source evidence**

Run `Get-FileHash -Algorithm SHA256` over each artifact and the retained source.
Do not create a generalized manifest system.

---

### Task 2: Reusable no-contact boundary, test-first

**Files:**

- Create: `mcp_server/src/rook/agent/experimental_snapshot_critic.py`
- Create: `mcp_server/tests/test_experimental_snapshot_critic.py`

**Interfaces:**

- Produces:

```python
CRITIC_INPUT_SCHEMA: str
CriticResult
load_final_snapshot(path: Path) -> Mapping[str, object]
project_critic_input(intent: str, snapshot: Mapping[str, object]) -> Mapping[str, object]
load_critic_result(raw: str, projection: Mapping[str, object]) -> CriticResult
run_snapshot_critic(intent: str, snapshot: Mapping[str, object], critic: Callable[[Mapping[str, object]], str]) -> CriticResult
actor_completion_allowed(actor_reported_success: bool, result: CriticResult) -> bool
write_discrepancy_artifact(path: Path, result: CriticResult) -> bytes
```

- [ ] **Step 1: Write RED retained-evidence and projection tests**

Tests must assert the reviewed source hash, exact request admission, exact
result projection, rejection of duplicate keys/extra rows/wrong request/failed
result, and that projection keys are exactly `schema`, `intent`, and `snapshot`.
Also provide hostile Actor transcript, history, completion claim, and diagnosis
objects and prove none can enter the function signature or returned projection.

- [ ] **Step 2: Run the focused test file and observe import failure**

Run:

```powershell
$env:PYTHONPATH = 'mcp_server/src'
python -m pytest mcp_server/tests/test_experimental_snapshot_critic.py -q
```

Expected: RED because the module does not exist.

- [ ] **Step 3: Implement strict source loading and immutable projection**

Use duplicate-key rejecting `json.loads`, strict UTF-8 file reading, exact field
sets, and recursive JSON freezing with `MappingProxyType` and tuples. Do not
normalize the retained snapshot.

- [ ] **Step 4: Write RED closed-result and authority tests**

Cover every verdict, missing/extra fields, wrong types, blank or lone-surrogate
strings, duplicates, unescaped/invalid pointers, unresolved pointers, wrong
coherence, duplicate reference claims, missing claim references, and references
outside `/intent` or `/snapshot`.

- [ ] **Step 5: Implement the result dataclasses and strict loader**

`CriticResult` contains only the five approved fields. Nested references are a
frozen `EvidenceReference` with `claim: str` and `pointers: tuple[str, ...]`.
No score, confidence, outcome taxonomy, or repair instructions are added.

- [ ] **Step 6: Write RED one-call, gate, and emission tests**

Use a counting fake Critic and assert exactly one invocation with the exact
projection. Assert Actor success plus Critic fail returns false. Assert
create-new writing produces deterministic UTF-8 JSON plus newline and refuses
an existing destination.

- [ ] **Step 7: Implement invocation, completion gate, and artifact emission**

The injected Critic is invoked once. The artifact writer uses `open("xb")`, one
complete write-count check, flush, and `os.fsync`; it never retries, truncates,
or repairs.

- [ ] **Step 8: Run focused tests GREEN**

Run the command from Step 2. Expected: all tests pass with no contact.

- [ ] **Step 9: Run adjacent acceptance/evidence loader tests**

Run:

```powershell
$env:PYTHONPATH = 'mcp_server/src'
python -m pytest `
  mcp_server/tests/test_experimental_snapshot_critic.py `
  mcp_server/tests/test_local_worker_turn_response_loader.py `
  mcp_server/tests/test_local_worker_acceptance_criteria.py `
  mcp_server/tests/test_gh_scalar_expectation_acceptance_criteria.py `
  -q
```

Expected: all pass; no live-marked tests.

- [ ] **Step 10: Commit the focused implementation**

Commit only the new module and focused test file.

---

### Task 3: Result report and final verification

**Files:**

- Create:
  `docs/superpowers/reports/2026-08-11-offline-grasshopper-snapshot-critic-result.md`

**Interfaces:**

- Consumes: Task 1 artifacts and Task 2 verification.
- Produces: durable bounded claims, non-claims, and one unexecuted next
  experiment.

- [ ] **Step 1: Write the report**

Record the model/provider, one-call count, exact input boundary, observed
Critic result, artifact hashes, changed files, tests, source-evidence hash
preservation, OpenProse alignment, and explicit non-claims.

- [ ] **Step 2: Specify but do not execute the smallest next experiment**

The proposal is one fresh Actor run with a pre-authored semantic acceptance
artifact, one independent Critic assessment from final snapshot only, and at
most one repair whose authority is limited to admitted discrepancy requirements.
It requires separate design and authorization.

- [ ] **Step 3: Run final no-contact verification**

Run focused and adjacent tests, Python compilation of the new module, `git diff
--check`, source-evidence SHA-256 verification, and a static import/source scan
proving the module contains no HTTP, MCP, Rhino, Grasshopper, Prime, subprocess,
or model construction.

- [ ] **Step 4: Self-review against every design requirement**

Map each requirement to a test, artifact, or source line. Any indirect or
missing evidence remains incomplete.

- [ ] **Step 5: Commit the report and stop for independent review**

Do not integrate the module into any runtime or execute the proposed live
experiment.
