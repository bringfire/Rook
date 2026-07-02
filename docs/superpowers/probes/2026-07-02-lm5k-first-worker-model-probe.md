# LM5K Probe Round 1 — First Worker Model Probe (2026-07-02)

**Doctrine:** evidence, not CI. This summary is the committed artifact; raw
runs stay local (spec §5, `docs/superpowers/specs/2026-07-02-lm5k-first-worker-model-probe-design.md`).

## Run identity

| | |
|---|---|
| Run directory (local, gitignored) | `probe_runs/lm5k-20260702T202802Z-3bd5a3d3/` |
| Git commit | `3bd5a3d3` (main, post-PR #397 merge) |
| Prompt text version | `lm5j.prompt_text:v1` |
| Prompt artifact schema | `rook.local_worker_prompt_artifact:v1` |
| Request / response schemas | `rook.local_worker_turn_request:v1` / `rook.local_worker_turn_response:v1` |
| Adapter record schema | `rook.local_worker_adapter_record:v1` |
| Scenario | golden repair workflow (`lm5k_first_probe`), expected action `draft_repair_params` |
| Generation params | `{"temperature": 0}` |
| Attempts per candidate | 5 |
| Raw capture | enabled (`--capture-raw`; raw outputs in the local run dir only) |

## Headline results

| Slot | Resolved model (source) | Status | strict-loadable | spine-passing |
|---|---|---|---|---|
| local_worker_candidate | `ollama_chat/qwen3:14b` (cli) | ran | **5/5** | **0/5** |
| cheap_cloud_worker_candidate | `anthropic/claude-haiku-4-5-20251001` (cli) | ran | **0/5** | **0/5** |
| ceiling_worker_candidate | `anthropic/claude-sonnet-5` (cli) | transport_error | 0/5 | 0/5 |

Every candidate failed **differently**, and each failure class is exactly what
the paired-metric + status taxonomy was designed to separate.

## Failure-reason groupings

- **local (qwen3:14b):** zero adapter failures. All five responses were
  strict LM5G-loadable JSON — no thinking-block leakage, no fences, correct
  schema tag, correct field sets. Spine failures were *admissibility
  expectation* mismatches: 4× `clarification_request` (disposition
  `clarification_needed`), 1× `refusal` with category `insufficient_context`
  (disposition `refusal_recorded`). The harness completed on every attempt;
  the responses were protocol-valid worker responses — just not the expected
  `action_request`.
- **cheap (Haiku 4.5):** 5× `raw_output_invalid:json_decode` — every response
  was wrapped in a markdown code fence (```` ```json ````) despite the prompt's
  "no code fences" instruction. Fence-stripping was deliberately excluded from
  v1 parsing so this is measured, not masked. Content inside the fence was a
  well-formed clarification_request.
- **ceiling (Sonnet):** 5× `transport_error:unexpected:UnsupportedParamsError`
  — reproduced and diagnosed: LiteLLM rejects `temperature=0` for
  `claude-sonnet-5` client-side ("Only temperature=1 is supported"; it is a
  reasoning-default model). No API calls were made; the ceiling read did not
  happen this round.

## Representative bounded excerpts

qwen3:14b (attempt 0, refusal — verbatim, complete):

```json
{"schema": "rook.local_worker_turn_response:v1", "kind": "refusal",
 "category": "insufficient_context",
 "reason": "Required input parameters 'code' and 'mode' are not available in
 the current context to execute the 'draft_repair_params' action."}
```

Haiku (attempt 0, opening bytes):

```text
```json
{ "schema": "rook.local_worker_turn_response:v1",
  "kind": "clarification_request",
  "question": "I am ready to draft repair parameters ... (1) What is the
  specific C# code body that needs to be repaired? (2) What repair mode ...
```

## Findings

1. **The load-bearing format bet reads positive for the local tier.** A
   14B local model at $0 obeyed the response contract perfectly (5/5 strict
   JSON) — and beat the cheap cloud model on format discipline. The
   mechanical contract-rendering in `lm5j.prompt_text:v1` appears sufficient
   for format compliance on at least one local model.

2. **The spine failures are convergent evidence of a scenario-communication
   gap, not model weakness.** Both model families that produced content
   (qwen3 AND Haiku) asked the *same* question: give me the `code` and
   `mode`. They read the allowed action's `input_schema`
   (`required: ["code", "mode"]`) as inputs they should have *received*
   rather than parameters they are being asked to *author*. The context also
   names memory keys (`component_guid`, `repair_anchor`) and
   `has_execution_params: true` without exposing values, which both models
   flagged. This lands squarely on the planner-harness north-star's open
   question 1 (evidence-push composition): the worker context must
   communicate the authoring role and carry (or explicitly withhold, with
   framing) the facts it references.

3. **The bounded-worker protocol worked exactly as designed.** Faced with
   perceived missing context, the local model did not hallucinate an action —
   it used the refusal/clarification channels (LM5B vocabulary), which the
   spine recorded as valid dispositions. In production these responses would
   flow to the runner's escalation policy rather than mutating anything.
   That is the safety property the whole worker box exists to provide.

4. **Fence discipline differs by model family.** Haiku fenced 5/5 despite
   explicit instruction; qwen3 fenced 0/5. The strict-v1 parser converted
   this into a clean measurable rather than hiding it.

5. **The ceiling slot needs per-slot generation params.** `temperature=0`
   is globally pinned this round; reasoning-default models (claude-sonnet-5)
   reject it client-side. The failure was recorded as evidence and did not
   block the panel — the taxonomy behaved as specced — but round 1 has no
   ceiling read, so the "is the prompt broken?" calibration question was
   answered indirectly (by qwen3's 5/5 format compliance) rather than by the
   ceiling.

## Round-2 candidates (decisions, not commitments)

- **Scenario/context fix (highest value):** make the authoring role explicit —
  prompt-text v2 (`lm5j.prompt_text:v2`) and/or richer worker context
  (execution-param visibility or explicit "you author these inputs" framing
  on allowed actions). This is the LM5A/evidence-push question, now with
  data.
- **Per-slot generation params** so the ceiling can run at `temperature=1`
  (recorded per candidate in the manifest; a distinct experiment key per
  spec §5.3).
- **Fence policy stays strict**; Haiku's non-compliance is now a measured
  baseline to compare prompt-text v2 against.
- Previously queued: `_git_short_sha` cwd anchoring; mixed
  loaded/transport-error offline e2e; `api_base`/model-digest in the
  comparison key for local aliases.

## Comparison key for this round

`(lm5j.prompt_text:v1, <resolved_model>, schemas above, {"temperature": 0})`
— any prompt-text, scenario-context, or params change is a new experiment.
