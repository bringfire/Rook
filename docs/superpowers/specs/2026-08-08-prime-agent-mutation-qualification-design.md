# Prime Agent Supervised Grasshopper Mutation Qualification Design

**Status:** Approved conversational design, ready for implementation planning after independent review.

**Baseline:** Exact Rook merge `2187bbcee26b6eaf94007dc400a60203203f86ae`.

**Lane:** `codex/prime-agent-mutation-qualification-design`.

## Objective

Qualify one new behavior:

> Can the local Qwen3.6:35b model, running inside Prime Agent with one explicit reviewed Grasshopper execution skill, use Rook's canonical MCP surface to create a requested parametric definition on a fresh disposable canvas and leave mechanically inspectable evidence?

This is a sibling experiment to the completed Prime readonly qualification. It reuses the proven Windows stdio transport and isolated Prime environment while changing only the authority required for supervised mutation.

The exact user intent is the one retained by the earlier ChatRunner point-field qualification:

```text
Create a Grasshopper definition that generates a row of points along the X axis using adjustable Start, Step, and Count controls, with Y and Z fixed at zero.
```

The intent reaches Prime unchanged. No topology, component count, tool sequence, scripting language, or expected implementation is appended to it.

## Evidence Anchors

The design is grounded in:

- Prime Agent commit `c98941a2`;
- the successful disposable readonly adapter at `C:/Users/bring/AppData/Local/Temp/prime-rook-readonly-qualification-v2`;
- adapter SHA-256 `E8B3BC41AA6DB224F430A80B52614568AF31798771379C9C8F9F491D964A3FC4`;
- the readonly milestone merged as Rook commit `2187bbce`;
- the merge-owned reviewed `.agents/skills/execute-grasshopper/SKILL.md`, SHA-256 `6858503160507411D5C227B36B4576FE6BA885A45B6D6A0F7EFA8B26BDA5040B`;
- its merge-owned checkpoint reference; and
- the prior ChatRunner point-field trace, which supplies the exact comparison intent but not an expected solution template.

The readonly adapter's inert baseline remains `9/9` passing tests. No model, Ollama, MCP, Rhino, or Grasshopper contact occurs during design or implementation review.

## Scope And Non-Claims

The experiment may prove only that this model/runtime/skill combination satisfies this one mutation request against authentic Rook and Grasshopper evidence.

It does not prove:

- arbitrary Grasshopper competence;
- automatic skill selection across unrelated intents;
- repeatability;
- recursion or delegation;
- knowledge or DSPy effectiveness;
- OS-level isolation;
- general mutation safety outside Rook's authority boundary;
- superiority over ChatRunner or another agent runtime;
- that Prime should become product code; or
- full runtime semantic correctness when the retained evidence cannot establish it.

The experiment does not fix ChatRunner's fallback-catalog defect or Prime's Windows console-window behavior. It changes no Rook or Prime repository code.

## Disposable Artifact Boundary

Implementation creates one fresh sibling outside both repositories:

```text
prime-rook-full-mutation-qualification/
  agent/
    settings.json
    models.json
    skills/
      rook-full/
        pyproject.toml
        src/rook_full/__init__.py
      prime-execute-grasshopper/
        SKILL.md
        references/checkpoint-protocol.md
    sessions/
  cache/
    prime_agent_runtime-0.1.0-py3-none-any.whl
  kernel-venv/
  operator/
    row.json
    run.ps1
    final_inspection.py
    test_adapter.py
    offline-install-commands.txt
    manifest.json
    prime.jsonl
    stderr.txt
    final-inspection.jsonl
```

The sibling is one-shot. Before Prime, Ollama, MCP, or host contact, the launcher refuses if `prime.jsonl`, `stderr.txt`, any native Prime session, or `final-inspection.jsonl` already exists. It never overwrites prior evidence.

Dependencies are installed offline from the reviewed local cache and wheel only. Missing cached dependencies stop setup; they do not authorize package-index contact.

## Full-Profile Adapter

The sibling package is honestly named `rook_full`. It preserves the v2 adapter's transport mechanism and lifecycle exactly.

Allowed substitutions are only:

- code-owned MCP profile `readonly` to `full`;
- package, class, server, instance, and public module identity from `rook_readonly`/`RookReadonly`/`rook-readonly` to `rook_full`/`RookFull`/`rook-full`; and
- the launcher's matching profile value.

The following remain unchanged:

- `McpIntegration` ownership;
- `_open_session()` structure;
- stack-owned `os.devnull` `errlog` and its lifetime;
- official MCP Python SDK `stdio_client()` and `ClientSession`;
- deployed Python command;
- `-m rook` argument;
- deployed MCP working directory;
- deployed runtime environment values;
- panel-locked process/document targeting;
- `mcp==1.28.0`;
- isolated kernel ownership;
- inherited runtime schema discovery and `call_tool()` dispatch; and
- the prohibition on copied schemas, custom dispatch, retries, fallbacks, or dynamic profile overrides.

An inert structural regression normalizes the approved profile and identity substitutions and then requires the mutation adapter bytes to equal the v2 adapter bytes. Any other delta fails review.

## Derived Qualification Skill

Prime receives one derived qualification skill, not two skills that it must compose.

The file contains:

1. minimal qualification-specific frontmatter;
2. a thin Prime compatibility preamble; and
3. the reviewed `execute-grasshopper` body appended byte-for-byte from its first Markdown heading onward.

The preamble states only:

```text
Import rook_full in IPython.
Invoke each Rook tool named by the reviewed method as:
await rook_full.<tool>(...)
```

It does not enumerate tools, copy schemas, suggest components or topology, prescribe calls, add a retry policy, or reinterpret the reviewed method.

The checkpoint reference is copied byte-for-byte to the same relative path expected by the reviewed skill. Tests compare the appended body and reference bytes and SHA-256 values against exact merge `2187bbce`.

This derived file is a disposable qualification adapter. It is not a new product skill.

## Frozen Row And Model Custody

The reviewed JSON row is the sole authority for:

- exact model `ollama/qwen3.6:35b`;
- explicit credential-free loopback Ollama API base;
- exact unchanged intent;
- resolved derived-skill path and hashes; and
- complete Rhino target triple: process ID, expected native port, and document serial number.

The launcher accepts exactly one argument: the row path. No CLI flag or environment variable may override individual row fields.

The isolated Prime configuration remains equivalent to the readonly specimen:

- provider `ollama`;
- OpenAI-completions compatibility;
- model ID `qwen3.6:35b`;
- built-in skills disabled;
- packages empty;
- extensions empty;
- `--offline`; and
- `--no-extensions`.

The code-owned full MCP profile is not model-selectable.

## Live Preconditions

Before separate authorization, the operator prepares:

- one fresh disposable Rhino context;
- one fresh, empty, unnamed, unsaved Grasshopper document;
- one active panel-bound document identity;
- one exact Rhino process ID;
- the native listener port owned by that process; and
- the exact Grasshopper/Rhino document serial used by panel lock.

The current native discovery record must corroborate the reviewed PID and port. A small Windows OS listener check must prove that the reviewed PID owns the reviewed loopback port. This is a preflight fact, not a new Rook targeting abstraction.

The model is expected to follow the reviewed method's own pre-mutation snapshot, live component/port admission, owned-state discipline, bounded batches, partial-success handling, one bounded correction, checkpoints, and final verification. The operator does not hard-code or enforce that call sequence; deviations remain qualification evidence.

## Prime Execution

The fixed sequence is:

```text
closed row admission
-> one Prime process
-> exact unchanged intent
-> derived reviewed skill
-> rook_full
-> separately spawned panel-locked Rook MCP subprocesses
-> authentic Grasshopper tools and receipts
-> Prime termination
```

Prime may choose:

- native components or a script component;
- component identities discovered through live Rook schemas;
- batch boundaries;
- inspection calls;
- snapshots; and
- the reviewed method's one bounded correction from current evidence.

There is no expected topology or tool-call count. All exact IPython code, MCP arguments, results, failures, and final prose remain in Prime's native session and JSON stdout.

The launcher adds no operator rerun and the adapter adds no MCP retry. Prime-owned provider transport behavior remains Prime-owned and is retained as observed evidence.

## Normal Prime Termination

Final inspection eligibility does not depend on Prime's semantic success claim or process exit code.

`normal Prime termination` means all of the following:

- the launcher observed natural process termination through its normal wait path;
- the process was not cancelled, killed, or forcibly terminated;
- stdout and stderr drains completed;
- required evidence files were closed;
- `prime.jsonl` exists, is nonempty, and is valid JSONL;
- exactly one native Prime session exists, is nonempty, and is valid JSONL; and
- the retained native session contains the exact model and exact user intent.

A nonzero Prime exit code remains eligible when this equation is satisfied. Prime may report failure or leave partial committed mutation; the independent final state is especially valuable in those cases.

Cancellation, forced termination, missing evidence, corrupt evidence, or multiple session files makes final inspection ineligible.

## Reconstructed Final Inspection

Prime and the final inspector do not share process-local context. After eligible termination, the operator reconstructs the exact panel lock from the same reviewed row in a separate MCP subprocess using the same `rook_full` adapter.

Immediately before any final-inspection call, the operator requires:

```text
current native discovery processId == row process_id
AND current native discovery port == row expected_port
AND Windows listener owner(row expected_port) == row process_id
AND reconstructed document serial == row document_serial_number
```

A mismatch refuses before MCP contact. The document serial is not inferred from discovery; it remains the exact row authority supplied to the reconstructed panel lock.

The only final-inspection call is literal:

```python
await rook_full.rook_tools_call(
    name="gh_snapshot",
    arguments={"include_data": True, "max_preview_items": 3},
)
```

The full adapter is acceptable here because this is fixed operator code, not model-controlled dispatch. Creating another readonly adapter solely for this call is forbidden.

No final-inspection retry, cleanup, interpretation, follow-up tool, or additional snapshot is permitted.

## Final-Inspection Evidence Grammar

`final-inspection.jsonl` is exclusively created and has one of two shapes:

```text
refusal
```

or:

```text
request
result
```

Each row is strict JSON with a `kind` and `payload`.

### Refusal

A refusal is the sole row when post-Prime eligibility or target admission rejects inspection. Its payload contains only one closed reason token:

- `prime_termination_ineligible`;
- `required_evidence_missing`;
- `required_evidence_invalid`; or
- `target_mismatch`.

No request or MCP call follows a refusal.

### Request

The exact request row is written and flushed before dispatch:

```json
{
  "kind": "request",
  "payload": {
    "name": "gh_snapshot",
    "arguments": {
      "include_data": true,
      "max_preview_items": 3
    }
  }
}
```

Request serialization, write, short-write, or flush failure causes zero final-inspection calls and an unsuccessful operator result. No retry or rejection row is attempted.

### Result

If the fixed call returns, its exact returned value is serialized as the `result` payload without parsing, normalization, scoring, or interpretation. A returned JSON string remains a JSON string.

Result serialization, write, short-write, or flush failure occurs after the snapshot call. The flushed request remains, the operator is unsuccessful, and no result is fabricated or retried. An OS short write may leave a partial final row; no repair is attempted.

If invocation raises, the flushed request remains and no result row is written. Existing stderr/process evidence retains the failure. Close failure also makes the operator unsuccessful and causes no retry.

The result's success or failure fields are retained exactly. A failed returned snapshot is still a returned result, not a refusal.

## Post-Run Assessment

The final snapshot is evidence, not a verdict. It may establish controls, component identities, topology, output previews, and diagnostics. It may not fully establish runtime semantics, especially for scripted components, generic Grasshopper data, absent previews, or previews truncated to three items.

Assessment asks:

> Do the retained tool records and final snapshot establish adjustable Start, Step, and Count controls producing the requested point row with fixed Y/Z and no runtime errors? Any unsupported part remains explicitly unproven.

The assessment reports ordinary facts:

- exact Prime/IPython call sequence;
- exact Rook tools, arguments, and results;
- committed, partial, failed, and unapplied operations already present in native evidence;
- whether targeting and Grasshopper-only scope were respected;
- final components and flows;
- available output previews;
- final errors and warnings;
- unsupported model claims; and
- what remains unproven.

No score, new receipt taxonomy, success object, dataset row, archive, or cleanup action is introduced.

Clean diagnostics and plausible wiring do not alone prove semantic correctness. The earlier `points` versus `Points` failure remains the governing lesson: names, casing, physical pin identity, and available runtime evidence must agree before making a semantic claim.

## Deterministic No-Contact Tests

Inert tests cover:

1. exact v2-to-full adapter substitution set and byte equality after normalization;
2. real `errlog.fileno()` availability and stack-owned closure order;
3. exact deployed command, cwd, environment, panel lock, and `mcp==1.28.0`;
4. absence of copied schemas, tool catalogs, custom dispatch, retries, or fallbacks;
5. derived skill frontmatter/preamble limits;
6. exact appended skill body bytes/hash against merge `2187bbce`;
7. exact checkpoint-reference bytes/hash;
8. closed row keys, exact model/intent, type-exact target values, and no overrides;
9. full-profile agreement between adapter and launcher;
10. one-shot refusal before contact when any evidence exists;
11. normal termination eligibility independent of Prime exit code or claimed success;
12. cancellation, forced termination, missing/corrupt evidence, and multiple sessions refusing inspection;
13. exact native discovery and Windows listener ownership admission;
14. refusal as the sole row and its closed reason tokens;
15. request flush before the one fake canonical call;
16. exact returned-value retention;
17. request-write failure causing zero calls;
18. result-write failure occurring after exactly one call with no fabricated result;
19. call exception retaining only the request; and
20. zero external contact across the full inert suite.

Fakes replace Prime, Ollama, MCP transport, Windows process/listener discovery, Rhino, and Grasshopper only at their external boundaries. The real disposable loader, adapter, skill construction, launcher admission, evidence writer, and final-inspection orchestration remain exercised.

## Anti-Quagmire Boundary

Stop and return for design review if implementation would require:

- any Rook or Prime repository code change;
- a new MCP abstraction;
- a second dispatch table or schema copy;
- dynamic profile selection;
- model-facing call enforcement;
- a generic qualification framework;
- a database, trace index, replay engine, scorecard, or archive;
- cleanup or rollback machinery;
- more than one Prime run;
- more than one operator-owned final snapshot; or
- a second model, intent, or canvas witness.

The disposable operator may use one launcher and one literal final-inspection helper. Those are experiment-specific files, not product surfaces.

## Authorization Gate And Stop Condition

Implementation and inert review authorize no live contact.

After independent approval, the operator must:

1. prepare the fresh disposable Rhino/Grasshopper target;
2. freeze and hash the complete sibling configuration and row;
3. corroborate PID/port/document custody;
4. obtain explicit authorization for exactly one mutation qualification; and
5. run once without operator rerun, adapter retry, cleanup, or fallback.

After evidence retention and factual assessment, the experiment stops. Any comparison, second model, second intent, product integration, ChatRunner fix, or Prime Windows cleanup is a separately designed slice.
