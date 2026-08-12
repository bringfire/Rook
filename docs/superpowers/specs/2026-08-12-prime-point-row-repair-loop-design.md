# Prime Point-Row Repair Loop Design

**Status:** Approved architecture, implementation-ready
**Base:** `ad4d3b2798ab38b2245d7d9d12fdadd344b16de5`
**Purpose:** Qualify the smallest useful deterministic-feedback repair loop around one local Prime Actor.

## Claim Boundary

This experiment may prove that deterministic semantic feedback enables one Qwen Actor to correct its own Grasshopper point-row result within one bounded repair.

It does not prove general Grasshopper planning, arbitrary acceptance compilation, repeatability, production readiness, or that an unfamiliar topology is wrong. Unsupported evidence remains `unproven`.

## Frozen Inputs

- Prime Agent `0.7.0`, repository `c98941a2a5cf40faecf9b4648ac3c304abf48fd3`.
- `ollama_chat/qwen3.6:35b`, reasoning explicitly requested at `medium`, with the existing frozen manifest and layer identities.
- Existing `rook_full.search/read/call` adapter and execute-Grasshopper skill bytes.
- Rook deployment and targeting custody already used by the qualified Qwen run.
- Exact intent:

  > Create a Grasshopper definition that generates a row of points along the X axis using adjustable Start, Step, and Count controls, with Y and Z fixed at zero.

- Acceptance artifact and evaluator merged through `97d73cd9`.

No prompt, skill, adapter, model, evaluator, schema, discovery, tool, or production-runtime tuning is admitted after contact.

## Architecture

```text
pre-authored acceptance artifact
-> Qwen initial user turn in one persisted Prime session
-> independent operator gh_snapshot
-> deterministic evaluation 1
-> pass: stop successfully
-> fail or incomplete: exact evaluator feedback
-> resume the same Prime session for one repair user turn
-> independent operator gh_snapshot
-> deterministic evaluation 2
-> stop
```

The operator may launch at most two sequential Prime CLI processes. The first creates the persisted session. The second, if admitted, uses `--resume <exact session path>`. These are two user turns of one Actor session, not two campaigns or two Actors.

Prime's native session remains the conversation authority. Each CLI process receives its own JSON stdout, stderr, exit code, PID-ancestry ledger, and terminal `agent_end` check.

## Deterministic State Machine

1. Refuse before the first Prime process if frozen artifacts, model identity, target custody, empty initial state, or one-shot evidence admission fails.
2. Run the initial user turn once.
3. After natural process termination, complete Prime evidence, and zero remaining owned processes, take exactly one operator snapshot.
4. Run the reviewed evaluator exactly once over that snapshot.
5. If evaluation 1 is `pass`, emit terminal success and do not create repair evidence or start another Prime process.
6. If evaluation 1 is `fail` or `incomplete`, create the exact repair message and resume the sole native session once.
7. After the same lifecycle checks, take exactly one second operator snapshot and run the evaluator exactly once.
8. Stop. Evaluation 2 alone owns the final `pass`, `fail`, or `incomplete` outcome.

Cancellation, timeout, missing terminal evidence, target drift, remaining owned processes, snapshot failure, evaluator refusal, or evidence-write failure stops the experiment incomplete. There is no retry, cleanup, alternate model, Critic call, fallback, or second campaign.

## Repair Feedback

The repair message is generated mechanically from evaluation 1 and contains only:

```json
{
  "original_intent": "<exact frozen intent>",
  "criteria": [
    {
      "criterion_id": "<exact evaluator value>",
      "status": "pass | fail | unproven",
      "evidence": {}
    }
  ],
  "repair_boundary": {
    "turns_remaining": 1,
    "may_inspect_before_repair": true,
    "may_modify": "execution_owned_components_only"
  }
}
```

`criteria` preserves evaluator order and retains every criterion, including passes. The `evidence` value is copied unchanged. The operator adds no diagnosis, score, topology, component recommendation, or Series prescription.

The exact JSON is passed as the resumed user turn and is retained by Prime's native session. The initial canvas is mechanically empty, so every component created during the initial turn is execution-owned. The existing skill's ownership rule remains authoritative during repair.

## Evidence

The disposable root retains, create-new where applicable:

- frozen row, manifest, model identity, skill, adapter, evaluator, and acceptance hashes;
- initial empty snapshot and exact target;
- initial Prime JSON stdout/stderr and process ledger;
- the sole native Prime session after each turn;
- phase-1 snapshot and evaluation;
- exact generated repair message, only when evaluation 1 blocks completion;
- repair Prime JSON stdout/stderr and process ledger, only when repair is admitted;
- phase-2 snapshot and evaluation, only after repair;
- bounded terminal status.

No new event recorder is introduced. Prime owns model/tool/session evidence; the existing operator snapshot mechanism owns canvas evidence; the reviewed evaluator owns semantic verdicts.

## Target and Pre-Contact Boundary

"Pre-contact" is used truthfully in two phases:

- Before any host or model call: inert implementation and hash checks report zero contact.
- Before model contact: one separately admitted read-only operator snapshot establishes the exact target and empty canvas. It is the only host preflight and is reported explicitly; it is not represented as zero live contact.

The final explicit authorization covers the complete initial Actor turn through optional repair and final evaluation. It is not split after evaluation 1.

## Disposable Scope

Prefer one fresh sibling of the qualified Qwen operator. Reuse the kernel and immutable common artifacts. Change only qualification-specific paths, row/evidence contracts, the adapted operator/inspector, and focused inert tests.

No changes are admitted to ChatRunner, Prime, Rook MCP, Grasshopper tools, schemas, discovery, the point-row evaluator, or production runtime. No framework, semantic registry, critic subsystem, score, campaign manifest, session pool, or new recorder is allowed.

## Inert Verification

Focused tests must causally prove:

- first evaluation `pass` causes one Prime turn, one snapshot, one evaluation, and zero repair artifacts;
- first evaluation `fail` and `incomplete` each generate the exact feedback and admit one same-session resume;
- feedback copies criterion IDs, statuses, and evidence unchanged and adds no diagnosis/topology;
- repair uses the exact sole session path and cannot create a second session;
- each phase requires one final `agent_end`, natural process termination, and zero remaining owned processes;
- no snapshot precedes terminal lifecycle admission;
- evaluation occurs exactly once per completed phase;
- second non-pass stops honestly without retry or cleanup;
- target drift, write failure, evaluator refusal, timeout, and lingering child processes fail closed;
- frozen hashes and one-shot evidence admission are checked before process entry.

Offline verification excludes Anthropic live tests and does not investigate the unrelated containment/panel-lock baseline failures.

## Review Gate

After disposable construction and inert verification, perform one independent pre-contact review. Then freeze the target and empty-canvas evidence and stop for one explicit authorization covering:

```text
initial Actor turn
-> evaluation 1
-> optional same-session repair turn
-> evaluation 2
-> stop
```
