# LM5K - First Local Worker Model Probe Design

**Date:** 2026-07-02
**Status:** Design draft for review
**Campaign:** Rook local/internal models north-star, LM5 worker transport boundary; second slice under the planner-harness north-star's §5.1 next-empirical-pressure decision (PR #395). Consumes LM5J (PR #396).
**Predecessors:** LM5A–I (worker turn boundary), LM5J adapter contract / prompt artifact boundary (`run_local_worker_adapter`, `rook.local_worker_prompt_artifact:v1`, prompt text `lm5j.prompt_text:v1`)
**Doctrine:** LM north-star §11.3 — model probes are evidence, not CI gates.

---

## 1. Goal

LM5K puts the first real model behind the LM5J adapter seam and produces the
campaign's first empirical read:

```text
Given the LM5I request envelope rendered through lm5j.prompt_text:v1, can a
real model reliably produce a strict LM5G-loadable response payload that
passes the LM5B/C/D/F spine?
```

Two deliverables:

1. **Production:** one reusable live transport —
   `LiteLLMWorkerTransport implements LocalWorkerTransport` — the missing
   seam between LM5J and future worker execution. Deterministically tested;
   no network in merge gates.
2. **Evidence harness:** a probe runner script that executes the golden
   scenario against a three-slot model panel and writes durable local
   evidence artifacts plus a committed curated summary.

LM5K does not answer:

```text
Is the prompt text optimal?              (prompt iteration = new version, new slice)
How do models behave across scenarios?   (round 2, after this read)
Should probe results gate merges?        (never in this horizon — evidence only)
Should the runner execute worker turns?  (runner integration is a later slice)
Which model should production use?       (model selection policy, later)
```

Layer split:

```text
LM5J:  request envelope -> prompt artifact -> transport protocol -> record
LM5K production:  LiteLLMWorkerTransport (protocol implementation, live)
LM5K script:      envelope -> transport -> adapter -> LM5D/F -> evidence
```

---

## 2. Production Scope

Add one production module:

```text
mcp_server/src/rook/agent/local_worker_model_transport.py
```

Add one focused test file:

```text
mcp_server/tests/test_local_worker_model_transport.py
```

Script (not production, but tested):

```text
scripts/lm5k_worker_probe.py
mcp_server/tests/test_lm5k_worker_probe.py   (runtime-free tests of pure logic)
```

Repo change: add `probe_runs/` to `.gitignore`.

Do not edit any LM5A–J production module.

---

## 3. Transport Contract (`local_worker_model_transport.py`)

### 3.1 Construction

```python
@dataclass(frozen=False)          # mutable: carries per-call telemetry
class LiteLLMWorkerTransport:     # implements LocalWorkerTransport
    model: str                    # resolved LiteLLM model id
    profile_api_base: str | None  # profile/CLI api_base context
    generation_params: Mapping[str, Any]   # e.g. {"temperature": 0}
    timeout_s: float = 120.0
    last_call_info: TransportCallInfo | None = None   # telemetry, read-after-call
    last_raw_output: str | None = None                # raw capture, read-after-call
```

The transport is constructed with a **resolved model id plus api-base
context**; it calls `api_base_for_model(model, profile_api_base)` internally
(pin: the existing `model_profiles` helper is the single routing authority —
the transport never re-implements provider routing).

### 3.2 `send(prompt_artifact) -> str`

```text
reset last_call_info = None, last_raw_output = None      (ALWAYS, first)
-> build messages verbatim from prompt_artifact["messages"]
-> litellm.completion(model, messages, api_base?, timeout, **generation_params)
-> extract choices[0].message.content
     missing/empty choices, None content, non-str content -> raise TransportError
-> set last_raw_output = content
-> fill last_call_info BEST-EFFORT (never raises; see 3.4)
-> return content
```

### 3.3 Error mapping (ratified)

- **Provider/LiteLLM exceptions propagate unwrapped.** The LM5J adapter
  records them as `transport_error:unexpected:<ExceptionClassName>` —
  `AuthenticationError`, `APIConnectionError`, `Timeout`, etc. become
  evidence through already-tested machinery. The transport never catches
  them.
- **`TransportError` (→ `transport_error:declared`)** is raised only for
  conditions the transport itself detects: empty/missing choices, `None`
  content, non-string content.
- No JSON mode, no `response_format`, no tool calling, no structured-output
  enforcement, no model-specific dialects in v1 (pin). LM5K measures raw
  prompt discipline: chat messages in, raw text out.

### 3.4 Telemetry is best-effort (pin)

`TransportCallInfo` (frozen dataclass): `model`, `latency_ms`,
`prompt_tokens | None`, `completion_tokens | None`, `cost_usd | None`.

Usage extraction and `litellm.completion_cost` are wrapped so that **no
telemetry failure can turn a valid model response into a transport error**:
any exception during telemetry fill leaves the affected fields `None` and
`send` still returns the content. Both attributes are reset at the top of
every `send` call, so a reader can never observe a previous call's values
after a failed call.

### 3.5 Raw-output retention

`last_raw_output` exists so the probe runner can implement `--capture-raw`
**outside** the LM5J record, preserving LM5J §4.4 (records carry bounded
excerpts only; full raw output is an opt-in probe artifact). The transport
holds at most one call's raw output; it is not a log.

### 3.6 Import rules

May import: `litellm`; `LocalWorkerTransport`/`TransportError` from
`local_worker_adapter`; `api_base_for_model` (and, if needed for defaults,
`api_key_env_for_model`, `get_models`) from `model_profiles`; stdlib.

Must not import: RookChat/chat modules, `base_agent`, dispatcher/tool
execution, LM5D/LM5F, workflow compiler/stream/runtime, Capability Index.

---

## 4. Probe Runner (`scripts/lm5k_worker_probe.py`)

### 4.1 Panel slots and resolution (pin)

Three named slots — probe vocabulary, not `ModelSet` fields:

```text
local_worker_candidate
cheap_cloud_worker_candidate
ceiling_worker_candidate
```

Resolution order per slot, first hit wins, **resolved id and source
recorded in the manifest**:

1. CLI flag (`--local`, `--cheap`, `--ceiling`, each `MODEL[@API_BASE]`);
2. environment variable (`ROOK_PROBE_LOCAL_WORKER`,
   `ROOK_PROBE_CHEAP_CLOUD_WORKER`, `ROOK_PROBE_CEILING_WORKER`, same
   format);
3. profile-derived default **only where safely inferable**: the local slot
   may fall back to the active model profile's `worker` role model when that
   model is local-provider-shaped (`ollama_chat/*`, `ollama/*`, or `openai/*`
   with a profile `api_base`). The cheap-cloud and ceiling slots have no safe
   profile inference and resolve only from CLI/env;
4. otherwise the slot is `unavailable` (recorded, never fatal).

`--skip local|cheap|ceiling` marks a slot `skipped`.

### 4.2 Candidate status (pin — configured failure is not absence)

```text
ran             resolved + attempted; at least one attempt produced an
                adapter record beyond transport_error
transport_error resolved + attempted; ALL attempts ended transport_error
                (adapter attempt records are still written — the failure is
                evidence, never hidden as absence)
unavailable     slot never resolved to a model id (no attempts exist)
skipped         explicitly excluded via --skip
```

A configured candidate whose provider fails is `transport_error` with full
attempt records, not `unavailable`. `unavailable` means only "no model id to
try."

### 4.3 Probe protocol

- One golden scenario: the compiled repair-workflow request envelope,
  constructed exactly as LM5J's integration test builds it (fixture
  duplicated into the script per repo convention; `workflow_id`
  `"lm5k_first_probe"`).
- **N = 5 attempts per candidate** (CLI `--attempts`, default 5), fresh
  envelope render per attempt.
- **Temperature 0**, fixed generation params, recorded verbatim in the
  manifest. Params are passed where the provider supports them; provider
  rejection of a param is a transport-level failure and therefore evidence.
- Per attempt: adapter invocation → when `response_loaded`, wrap the loaded
  response as a `LocalWorkerTurnWorker` → `run_local_worker_turn` (LM5D) →
  `evaluate_local_worker_scenario_result` (LM5F) with the same expectation
  block as LM5J's integration test (`expected_disposition
  "candidate_action_request"`, `expected_action_id "draft_repair_params"`).
- Two success metrics, counted separately per candidate (pin — the names
  must not blur the distinction):

  ```text
  strict_loadable = adapter.status == "response_loaded"
  spine_passed    = adapter.status == "response_loaded" AND LM5F passed
  ```

  `strict_loadable` measures format/prompt compliance (the model emitted a
  strict LM5G-loadable payload). `spine_passed` additionally requires the
  loaded response to survive LM5B/C/D/F (e.g. requesting `execution_ref`
  instead of the allowed action is loadable but not spine-passing). The
  headline is always reported as the pair `n/5 strict-loadable, m/5
  spine-passing`; the gap between them separates format-compliance
  failures from action/admissibility failures.

### 4.4 Attempt record (one JSONL line per attempt)

```text
run_id, candidate_slot, resolved_model, resolution_source, attempt_index,
adapter_status, failure_reason, raw_output_excerpt,
harness_status | null, disposition | null, evaluation_passed | null,
latency_ms | null, prompt_tokens | null, completion_tokens | null,
cost_usd | null,
prompt_text_version, prompt_schema, request_schema, response_schema,
record_schema, captured_raw_path | null
```

Telemetry fields are copied best-effort from `transport.last_call_info`;
`null` on telemetry failure. `captured_raw_path` is set only under
`--capture-raw`, pointing into the run directory's `raw/`.

---

## 5. Evidence Artifacts

### 5.1 Run directory (gitignored)

```text
probe_runs/
  lm5k-<UTC timestamp>-<short git sha>/
    manifest.json
    attempts.jsonl
    raw/
      <slot>-<attempt>.txt        # only with --capture-raw
```

`manifest.json`: run id, UTC timestamp, git commit, all schema versions
(prompt artifact, prompt text, request, response, adapter record), panel
(slot → resolved model, resolution source, candidate_status), generation
params, attempts-per-candidate, capture-raw flag, scenario workflow_id.

### 5.2 Committed summary (curated, human-authored per probe round)

```text
docs/superpowers/probes/2026-07-02-lm5k-first-worker-model-probe.md
```

Contents: prompt text version and schema versions; panel with resolved
model ids and statuses; per-candidate paired counts
`n/5 strict-loadable, m/5 spine-passing`; failure-reason groupings;
representative **bounded excerpts only**; whether raw capture was enabled
and where the local run directory lives. Never raw output, never full
attempt dumps.

### 5.3 Evidence doctrine (pin)

Probe results are evidence, never CI pass/fail. No merge gate reads
`probe_runs/`. Cross-run comparison is keyed by
`(prompt_text_version, resolved_model, schema versions, generation_params)`
— a change to any key is a new experiment, not a re-run.

---

## 6. Tests (deterministic; no live model in any merge gate)

### Transport unit tests (`test_local_worker_model_transport.py`)

With a fake/monkeypatched `litellm`:

- messages built verbatim from the artifact; model/api_base/timeout/params
  kwargs exact; `api_base_for_model` routing honored (ollama model with
  profile api_base → no api_base kwarg; `openai/*` local → api_base kwarg);
- content extraction: str content returned; empty choices / None content /
  non-str content → `TransportError`;
- provider exception (fake `RuntimeError`/auth-shaped exception) propagates
  unwrapped;
- telemetry: reset-before-call proven (stale values from a prior call are
  gone when the next call raises); best-effort proven (a
  `completion_cost` that raises leaves `cost_usd=None`, `send` still
  returns);
- `last_raw_output` set on success, `None` after a failed call;
- import/AST guard per §3.6.

### Runner logic tests (`test_lm5k_worker_probe.py`, runtime-free)

- slot resolution order (CLI > env > profile-inference > unavailable) with
  source recorded; cheap/ceiling never profile-inferred;
- candidate_status classification from synthetic attempt records (all four
  values, including all-transport_error → `transport_error` not
  `unavailable`);
- attempt JSONL shape and manifest shape (fake transport, offline end-to-end
  through the real adapter + LM5D/F, mirroring LM5J's integration test);
- `--capture-raw` writes raw files and sets `captured_raw_path`; default
  writes neither.

---

## 7. Verification

- Targeted new test files + the focused PlanGraph/local-worker gate;
- `py -3.10 -m py_compile` over the new module, script, and test files;
- `git diff --check`; production diff under `mcp_server/src` is exactly
  `local_worker_model_transport.py`;
- One live probe run against whichever panel subset is available, producing
  manifest + attempts + summary — **executed as evidence after merge-gate
  checks, not as a gate**.

---

## 8. Explicit Non-Goals

- prompt-text changes (any change bumps `LOCAL_WORKER_PROMPT_TEXT_VERSION`
  in its own slice);
- scenario diversity beyond the golden repair envelope (round 2);
- provider JSON mode / tool calling / structured output enforcement;
- async transport; retry/fallback loops; streaming;
- MCP tool exposure; RookChat integration; runner/scheduler integration;
- model selection policy; ModelSet field changes;
- committing raw model output or full run artifacts;
- probe results as CI signal.

---

## 9. Review Resolutions (brainstorm round, 2026-07-02)

1. **Shape:** thin production transport + script runner (strict split; the
   transport never decides whether the model "passed").
2. **Sync `litellm.completion`** — matches LM5J's sync `send`; no event-loop
   bridging in the first live read.
3. **Panel:** three named slots (local / cheap-cloud / ceiling), resolved at
   runtime, absence recorded as evidence.
4. **Evidence home:** gitignored `probe_runs/` + committed curated summary;
   raw capture explicit opt-in (`--capture-raw`).
5. **Protocol:** one golden scenario × N=5, temperature 0, per-attempt JSONL.
6. **Telemetry best-effort + reset-per-call** (review pin 1).
7. **Configured-but-failing ≠ unavailable** (review pin 2; §4.2).
8. **Resolution order pinned** CLI → env → safe profile inference → 
   unavailable, with source recorded (review pin 3).
9. **API-base via `api_base_for_model(model, profile_api_base)` inside the
   transport** (review pin 4).
10. **No provider JSON mode/tools in v1** (review pin 5).
11. **Provider exceptions propagate unwrapped**; `TransportError` only for
    transport-detected conditions (ratified).
12. **Telemetry/raw as read-after-call attributes**, reset per call,
    non-fatal (ratified).
13. **Two-metric headline** `strict_loadable` / `spine_passed`, always
    reported as the pair — format compliance and admissibility are distinct
    facts and the gap between them is diagnostic (spec review round 1, P2).
