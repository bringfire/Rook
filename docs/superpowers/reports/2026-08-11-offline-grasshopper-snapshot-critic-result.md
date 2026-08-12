# Offline Grasshopper Snapshot Critic Result

**Date:** 2026-08-11

**Result:** Qualification unsuccessful; deterministic admission refused the
single Critic response. No reusable critic boundary was implemented.

## Purpose

This experiment tested whether one isolated local `qwen3.6:35b` Critic could
independently evaluate the retained failed Grasshopper result from only:

```text
exact original user intent
+ authentic final gh_snapshot
```

The Critic received no Actor reasoning, transcript, tool history, completion
claim, suggested diagnosis, skill, MCP surface, or repair authority.

## Frozen source

Source:

```text
C:/Users/bring/AppData/Local/Temp/
prime-rook-qwen-strict-retest-v1/local/operator/final-inspection.jsonl
```

SHA-256 before and after the experiment:

```text
4B3E44B853D7EEC44D6052D2C4442BEB4CEE46BD3E728C14781FCDDB43C87AE8
```

The retained source remained byte-for-byte unchanged.

The original row's existing `operator/manifest.json` has SHA-256
`FC1EE04AA16E541ACC2712325366A3B1CA017C822ABF2437D103BBD4CDE8FFB9`.
All `21/21` retained entries still match it. This experiment did not rewrite
that manifest or any covered artifact.

## Call custody

The disposable operator used Prime's existing `streamSimple` provider seam:

```text
provider: ollama_chat
model: qwen3.6:35b
api: openai-completions
reasoning: medium
tools: []
maxRetries: 0
provider payloads observed in the artifact-producing invocation: 1
assistant stopReason: stop
content blocks: thinking, text
```

No Agent loop, IPython tool, skill, extension, MCP client, Rhino client,
Grasshopper client, subprocess tool, or external provider was available to the
Critic. The operator contained one `streamSimple` invocation and no retry loop.

The operator's in-process hook required exactly one provider payload and
`maxRetries=0`, so the retained successful invocation proves one payload and no
SDK retry for that invocation. Its first create-new evidence guard occurs after
`await stream.result()`. Therefore the retained files cannot forensically
exclude a separate, unretained re-execution of the operator. This report does
not claim experiment-wide one-shot custody.

Observed usage was:

```text
input: 2544 tokens
output: 5713 tokens
total: 8257 tokens
reported cost: 0
```

Provider token accounting is retained as observational telemetry only.

## Observed Critic result

Qwen returned a syntactically valid JSON object with `verdict: fail`. Its
visible assessment independently stated that:

- the graph generates a row of X-axis points;
- Y and Z are fixed at zero;
- Start and Count controls exist;
- no adjustable Step control exists;
- an `EndX` slider substitutes for the requested Step interface;
- the intent therefore requires repair.

It did not establish the required Count-to-Range cardinality relationship:
Count controls Range steps/intervals and Count `10` produces `11` points.

It also emitted pointers rooted at `/data/...`. The frozen input projection is
rooted at `/snapshot/data/...`; therefore every supplied pointer failed the
predeclared authority/resolution rule.

The strict loader stopped with:

```text
ValueError: evidence pointer authority
```

No `critic-result.json` was created. The raw assistant and visible response
remain retained; the response was not repaired, reinterpreted as admitted, or
sent back to the model.

The frozen prompt also contains an instruction defect. After listing `verdict`
first, it says the “first, second, and fifth fields” are arrays. `verdict` is
scalar; the intended array fields were the second, third, and fifth. Qwen still
returned the intended field types, and the defect did not cause the observed
pointer-authority refusal. It nevertheless prevents treating this as a
perfectly unambiguous prompt qualification. The prompt remains unchanged and no
corrected call was made.

## Qualification criteria

| Required independent observation | Observed |
| --- | --- |
| Y and Z are structurally fixed at zero | Yes |
| No adjustable Step control exists | Yes |
| EndX substitutes a different interface for Step | Yes |
| Count drives Range steps and yields Count plus one points | No |
| The original intent was not satisfied | Yes |
| Closed artifact passes deterministic schema/authority gate | No |

The experiment therefore did not satisfy its success equation.

## Disposable artifacts

Root:

```text
C:/Users/bring/AppData/Local/Temp/rook-qwen-offline-critic-v1
```

| Artifact | SHA-256 |
| --- | --- |
| `agent/auth.json` | `CA3D163BAB055381827226140568F3BEF7EAAC187CEBD76878E0B63E9E442356` |
| `agent/models.json` | `594BD57B583C34456C4EA541E6CAF33C39D63C71E77582C916A18670FB4DAA2D` |
| `critic_artifacts.py` | `636880755DAAC8A006A5BA5F646C1DCBB0F10405F5C39EE441A903F98DF54781` |
| `critic-call.ts` | `CA532254B8C73BA82C96499F7C1E881E1D217C9B7A37A6036E3B8091D0ACD8E1` |
| `critic-prompt.txt` | `7CEA8AB78B150B1505FD89ACF2BB41E591BF96B9A436BB84A118D162EB9A34D4` |
| `projection.json` | `272D715FD97B8EE5DAA9A2DD4DE3634392E1A0EF9DC51B69E87358FCAE5E4789` |
| `prime-assistant.json` | `6168975D579BB43BCC671530F38A8AE512EE29B9DDF9241D06446ACA74B8FDC6` |
| `critic-raw.txt` | `675E756C3E42172C3E8C2B0DBC7E8329E94D4A4F01CE42106B770553F7279B40` |

The model settings file is byte-identical to the retained Qwen Actor row's
`agent/models.json`. The projection contains exactly `schema`, `intent`, and
`snapshot`; its snapshot value is the admitted final result payload.

## Repository scope

Committed design artifacts:

- `docs/superpowers/specs/2026-08-11-offline-grasshopper-snapshot-critic-design.md`
- `docs/superpowers/plans/2026-08-11-offline-grasshopper-snapshot-critic.md`
- this result report

No Python production module or test module was added. The approved design made
implementation conditional on a successful one-call qualification. Relaxing
the pointer contract or omitting the missing Count-plus-one criterion after
seeing the response would invalidate the experiment.

## Claims

This experiment proves:

- an isolated, tool-free Prime provider call can inspect intent plus authentic
  final snapshot without Actor-private evidence;
- the local model independently detected the central Step/EndX interface
  mismatch and the fixed Y/Z success;
- a deterministic gate prevented a plausible but malformed and semantically
  incomplete Critic response from acquiring completion authority;
- retained Actor evidence was not mutated; no Rhino, Grasshopper, MCP, canvas,
  deployment, external provider, or mutation surface was contacted.

## Verification

- `critic_artifacts.py` compiled with the system Python.
- The retained evidence loader admitted the exact two-row source and generated
  the intent-plus-snapshot projection.
- The original row manifest verified `21/21` retained artifacts with zero
  mismatches.
- The strict result loader causally refused the actual response at the pointer
  authority boundary and created no admitted artifact.
- The adjacent existing response/acceptance loader seam passed `82` tests.
- Static inspection found one `streamSimple` call, no retry loop, `tools: []`,
  and no MCP/Rhino/Grasshopper import or invocation in the call operator.
- Repository whitespace checks passed before this report was committed.

## Non-claims

This experiment does not prove:

- that the proposed reusable boundary is ready to implement;
- that experiment-wide one-shot custody can be reconstructed from the retained
  artifacts;
- that the frozen Critic prompt was internally unambiguous;
- that Qwen can reliably produce the closed discrepancy grammar;
- that Qwen understands Count-versus-interval cardinality from snapshots;
- that a free-form Critic should become a permanent runtime judge;
- that any repair topology is correct;
- that an Actor -> Critic -> repair loop works;
- anything about a new Actor, Opus, Rhino, Grasshopper, or MCP run.

## OpenProse alignment

The negative result strengthens the stated north star. A post-hoc free-form
Critic found useful semantics but did not reliably satisfy the evidence
contract. The durable direction remains:

```text
intent
-> explicit acceptance/postcondition artifact authored before execution
-> Actor execution
-> authentic final evidence
-> mechanical postcondition evaluation
```

The model Critic remains useful as an offline instrument for discovering which
postconditions should be authored, not as final commit authority.

## Smallest proposed live experiment — not executed

No live experiment is currently eligible. The smallest eventual experiment is:

```text
pre-authored semantic acceptance artifact
  - adjustable Start
  - adjustable Step
  - adjustable Count
  - Y and Z structurally fixed at zero
  - point count semantics explicitly defined
-> one fresh Actor run
-> one authentic final snapshot
-> mechanical acceptance evaluation
-> isolated Critic receives only intent + snapshot + failed criteria identifiers
-> at most one repair limited to admitted semantic discrepancies
-> one final mechanical evaluation
```

Before authorizing that run, a separate no-contact design must decide whether
the Critic remains merely advisory or whether a corrected closed grammar can be
qualified without post-result relaxation. This report does not authorize a
second Critic call, a prompt revision, an Actor run, or a repair.
