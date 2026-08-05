# Chirp Inference Timeout Design

Date: 2026-08-05

Status: approved for implementation planning

Rook evidence baseline: `9a963e823632a160e1cfaf4e70660f8646da28fa`

Chirp implementation base: `b0acae1c91243ec7bc1de58138ac17ae58fdcb05`,
the immutable `master` merge of the separately reviewed Opus 5 planner/default
and Sonnet 5 non-planner requirements. The timeout diff must preserve that base's
model defaults and routing; those model changes are not part of this correction.

## Goal and boundary

Replace Chirp's effective 30-second cap with one bounded total inference budget
that supports slow cloud calls and local-model startup/inference. It must propagate
through local deployment and the next installer, preserve cancellation and bounded
shutdown, and report inference timeouts as runtime failures.

This is forward-only for newly generated Chirp components and the current runtime.
Existing saved components are outside the specification: no detection, marker,
migration, rewriting, compatibility path, or migration tests.

Do not add a general deadline/retry framework, per-component timeout setting, model
or routing change, category/cascade change, dependency update, native/managed
change, or broad MCP timeout change. Historical documents remain untouched.

## 1. Proven current chain

| Layer | Current bound | Effect |
| --- | --- | --- |
| Generated C# | `HttpClient.Timeout = 30s` in `chirp.rook_tool` | First effective cap; produces a generic Grasshopper runtime exception. |
| Chirp `/chirp/call` | None; synchronous FastAPI handler | All exceptions become HTTP 500; client cancellation may leave provider work running. |
| Chirp adapter | None; synchronous DSPy call | No aggregate request deadline. |
| DSPy/LiteLLM | DSPy `num_retries=3`; installed LiteLLM default 6,000s | Chirp passes no timeout and a per-attempt timeout can be multiplied by retries. |
| Provider transports | Explicit LiteLLM `timeout` is accepted by inspected Anthropic, OpenAI-compatible, custom HTTP, and local-provider paths | No lower Chirp-owned limit exists; the dependency default is not a product contract. |
| Chirp startup | 2s health request; 45s startup poll | Sidecar readiness only, not inference. |
| Rook `/chirp/create` | 10s request to deterministic source generation | Not an inference timeout. |
| Rook bridge | Connect 5s, read 120s, write 60s, pool 5s | Script injection schedules a solve and returns; these are not the generated component's Chirp transport. |
| Installed MCP client | Codex tool timeout 120s | Must not surround inference. |
| Uvicorn | Keep-alive 5s; graceful shutdown unset | Keep-alive is irrelevant to active requests; shutdown lacks a fixed bound. |
| Runtime harness | Readiness/cleanup bounded; Chirp smoke timeout omitted | Current deterministic smoke may wait indefinitely. |

The 30-second generated-client literal is the observed cause. Raising it alone
would expose the missing aggregate, cancellation, error, and shutdown contracts.

There is one surrounding hazard: after script injection, `chirp_create` waits and
calls `/gh/errors`. If the scheduled solve has entered inference, that diagnostic
can wait behind the solve and hit the 120-second bridge/client limit. The actual
response is retained as `script_result`; inspect
`script_result.data.verification_deferred`. For inference-capable creation, when
that value is true, skip both the delay and `/gh/errors`, and return at least
`verification_deferred` and `solve_scheduled` in `chirp_create.data`. Omit
`component_errors` in this deferred case rather than claiming it was checked.
Deterministic-only creation may keep its focused verification.

Rook also labels generic `/gh/errors` messages as `compilation_errors`, although
that route does not prove compiler origin.

## 2. Selected approach

Rejected alternatives are (a) raising only the C# timeout and (b) applying a full
timeout independently to every retry. The first leaves work unbounded; the second
multiplies wall-clock duration and can outlive outer callers.

Make `/chirp/call` and the adapter path asynchronous. Pass the complete adapter
coroutine to the Python 3.10-compatible aggregate deadline:

```python
await asyncio.wait_for(
    adapter.acall(...),
    timeout=inference_timeout_seconds,
)
```

DSPy's async path reaches LiteLLM's async provider transports, so cancellation
propagates instead of abandoning a worker thread. Signature work, provider
attempts, retries, and retry delays all consume the same deadline. Do not use
`shield`, worker threads, background abandonment, or custom scheduling.

Every default and model-override `dspy.LM` also receives the configured timeout.
That is a per-attempt transport backstop; the outer Chirp deadline alone governs
aggregate time. Do not add remaining-time calculations or custom retry logic, and
do not rely on LiteLLM's current 6,000-second default.

`/chirp/create` performs configuration admission and deterministic source
generation only. It does not acquire a 300-second operation budget.

## 3. Authoritative policy and configuration

| Purpose | Value |
| --- | ---: |
| Default total inference budget | 300 seconds |
| Maximum configurable budget | 1,800 seconds |
| Generated C# transport ceiling | 1,830 seconds |
| Installed acceptance watchdog | 1,860 seconds |

`CHIRP_INFERENCE_TIMEOUT_SECONDS` is the only setting. Read it once at sidecar
startup and keep it immutable for that process. Precedence is:

1. Present inherited process environment.
2. Exact canonical `<CHIRP_HOME>/.env`.
3. Built-in 300 only when absent from both.

Load only that explicit `.env`; never search upward. A higher-precedence malformed
value does not fall through. Accept the complete string only when it contains ASCII
digits `0`-`9` and resolves to 1-1,800. Do not trim. Empty, signs, decimals,
scientific notation, units, Unicode digits, zero, negative, and excessive values
are invalid.

The generated 1,830-second value is a stable safety ceiling, not the configured
budget or normal expected duration. The accepted tradeoff is that a nonresponsive
sidecar can leave a new component waiting that long. Future defaults within the
maximum do not require another regeneration design.

## 4. Admission and error contract

Invalid configuration must not initialize an LM, load a model, generate source,
begin inference, create a component, or call Grasshopper. The sidecar remains
reachable only for health and bounded failure responses.

Healthy `GET /health` is HTTP 200:

```json
{"status":"ok","version":"0.1.0"}
```

Disabled `GET /health` is also HTTP 200:

```json
{
  "status":"disabled",
  "version":"0.1.0",
  "error":{
    "code":"chirp_invalid_inference_timeout",
    "message":"Chirp is disabled because CHIRP_INFERENCE_TIMEOUT_SECONDS must contain only ASCII digits and resolve to 1–1800 seconds."
  }
}
```

Disabled `/chirp/create` and `/chirp/call` reject at admission with HTTP 503:

```json
{
  "error":"chirp_invalid_inference_timeout",
  "details":"Chirp is disabled because CHIRP_INFERENCE_TIMEOUT_SECONDS must contain only ASCII digits and resolve to 1–1800 seconds."
}
```

Never echo the invalid value, source environment, API key, or other environment
content. Rook parses health and short-circuits its 45-second poll only for this
exact reachable terminal code. All other startup behavior remains unchanged, and
Rook MCP remains available.

Catch `asyncio.TimeoutError` around the `asyncio.wait_for` call. It returns HTTP
504, never generic 500:

```json
{
  "error":"chirp_inference_timeout",
  "details":"Chirp inference exceeded its configured total request budget.",
  "timeout_seconds":300
}
```

`timeout_seconds` is the validated effective value. `wait_for` initiates
cancellation at the deadline and waits for the child coroutine to finish
cancelling, so the 504 may arrive slightly after the nominal budget; it must still
arrive within the approved 30-second transport slack. Client disconnect, explicit
shutdown, and external task cancellation propagate as cancellation; they are not
rewritten as budget exhaustion. No retry starts after the total deadline.

Generated C# recognizes 504 and reports `chirp_inference_timeout` as a Grasshopper
runtime error. Reaching its own 1,830-second ceiling reports
`chirp_transport_timeout`, not a missing adapter or compilation error.

Uvicorn gets one fixed 30-second graceful-shutdown timeout, independent of the
inference setting. Explicit shutdown may cancel inference; it must not wait for the
1,800-second maximum. Discovery cleanup stays in the bounded shutdown path.

## 5. Chirp response vocabulary

Atomically replace Chirp's `compilation_errors` with `component_errors`: messages
reported by the Grasshopper component whose compiler/runtime origin is not known.
Update every active Chirp producer, consumer, focused test, skill mirror, and
current document together. Do not return both names or add an alias, fallback,
schema version, or deprecation path. Add one scoped guard preventing the old name
from returning to active Chirp contracts without scanning historical evidence or
unrelated script-authoring contracts.

For inference-capable creation, `component_errors` appears only after the focused
diagnostic actually ran and observed messages. When
`script_result.data.verification_deferred` is true, return promptly with at least
the received `verification_deferred` and `solve_scheduled` values and omit
`component_errors`. A later independent diagnostic does not own or cancel the
component's inference.

The next release note mentions the corrected Chirp field once. Actual compiler
diagnostics are called compilation errors only when their origin is known.

## 6. Two-repository implementation boundary

Expected Chirp production files:

- `src/chirp/timeout_policy.py` (one dedicated immutable loader)
- `src/chirp/adapter.py`
- `src/chirp/server.py`
- `src/chirp/rook_tool.py`
- `src/chirp/__main__.py`

Expected Chirp active references/tests:

- `README.md`
- `templates/chirp_script_template.cs`
- `templates/example_intent_to_params.cs`
- `tests/test_adapter.py`
- `tests/test_server.py`
- `tests/test_rook_tool.py`
- `tests/test_timeout_policy.py` (new)

Expected Rook production/install files:

- `mcp_server/src/rook/chirp_manager.py`
- `mcp_server/src/rook/server.py`
- `mcp_server/src/rook/local_testing_proof.py`
- `installer/post_install.py`
- `installer/RookSetup.iss`

Expected Rook active skill files are the six mirrored `SKILL.md` files for `chirp`
and `chirp-cascade` under `.agents/skills`, `.claude/skills`, and
`installer/agent-assets/codex-skills`. Edit only text that consumes or describes
this contract and keep each three-way mirror byte-identical.

Expected Rook focused tests/guards:

- `mcp_server/tests/test_chirp_manager.py`
- `mcp_server/tests/test_server_contract_hardening.py`
- `mcp_server/tests/test_local_testing_proof.py`
- `mcp_server/tests/test_chirp_timeout_contract.py` (new scoped vocabulary/mirror guard)
- `scripts/tests/deploy-local-testing-guards.tests.ps1`
- `scripts/tests/python-runtime-packaging.tests.ps1`
- `scripts/tests/release-installer-guards.tests.ps1`

No change is expected in RookNative, managed C#, RookBIM, dependency metadata,
lockfiles, general bridge timeouts, or model/provider routing. Planning must stop
for review if evidence requires another production boundary.

## 7. Deployment and release propagation

Installer behavior is exact:

- If Chirp `.env` exists, install and repair preserve it byte-for-byte, including
  when the user enters a new API key.
- If Chirp `.env` is missing and an API key is supplied, create it with that key
  and `CHIRP_INFERENCE_TIMEOUT_SECONDS=300`.
- If Chirp `.env` is missing and no API key is supplied, do not create it solely
  for the timeout; the built-in 300 applies.
- A newly generated `.env.example` includes the uncommented timeout setting;
  an existing `.env.example` may remain untouched.

Local deployment continues to exclude `.env`, so it does not inspect, copy,
delete, validate, or rewrite the installed value.

Local deployment already mirrors Chirp source while excluding `.env`, and release
mode exact-syncs the sealed wheelhouse before `post_install.py`. Extend focused
guards rather than adding a deployment subsystem. The installer continues to
package Chirp source from the exact reviewed Chirp checkout and its wheel from
Rook's sealed wheelhouse. Manifest provenance records both accepted commits. No
dependency or lock change is expected.

Release order:

1. Implement and review Chirp timeout work from exact base
   `b0acae1c91243ec7bc1de58138ac17ae58fdcb05`.
2. Merge the coordinated Rook correction and record the accepted Chirp SHA.
3. Build/deploy/install from the resulting private Rook merge and that Chirp SHA.
4. Run installed acceptance.
5. Promote public material separately, recording both source SHAs and artifact
   hashes and including the one release-note mention.

Live acceptance must use the installed candidate, never an MCP server imported from
a detached worktree.

## 8. Verification

Focused Chirp tests prove:

- default/minimum/maximum, exact precedence, read-once immutability, and every
  invalid syntax class;
- invalid configuration initializes no LM and admits only exact health/503 failures;
- `/chirp/create` has admission but no inference budget;
- every LM receives the explicit value;
- one `asyncio.wait_for` deadline includes attempts and delays, cancellation
  reaches the fake provider, no later retry starts, exact 504 is produced promptly
  within the 30-second transport slack, and external cancellation remains
  cancellation rather than 504;
- generated source contains 1,830 and both timeout codes; and
- Uvicorn uses fixed 30-second graceful shutdown.

Focused Rook tests prove:

- exact degraded health short-circuits while other startup states retain 45s;
- admission precedes source generation and every Grasshopper request;
- inference-capable creation reads `script_result.data.verification_deferred`,
  skips its delay and `/gh/errors` when true, returns the received
  `verification_deferred` and `solve_scheduled` values, and does not report
  `component_errors` as checked;
- deterministic-only creation retains its focused verification;
- active Chirp contracts use only `component_errors`;
- the 1,860-second watchdog starts after installed readiness and bounded `finally`
  cleanup preserves body and cleanup failures; and
- install/repair/local deployment preserve existing `.env` and ship source/wheel
  bytes from the reviewed Chirp commit.

Installed acceptance uses one loopback-only OpenAI-compatible fake provider on an
owned random port. It requires no API key or internet, delays a valid response for
at least 35 seconds, and is terminated through bounded cleanup. Through installed
Rook/Chirp, create and execute one owned component and prove:

- success after more than 30 seconds with the expected typed output;
- the provider received the expected request;
- no `chirp_inference_timeout`, `chirp_transport_timeout`, or component errors;
- owned Grasshopper state is removed; and
- provider, sidecar, and host teardown runs in bounded `finally` cleanup even if
  the 1,860-second watchdog expires.

The direct inference chain must have no lower Rook/Chirp-owned HTTP, MCP,
Grasshopper, DSPy, LiteLLM, or harness timeout that can preempt the approved
policy. An external provider or locally hosted model server may enforce its own
lower limit; preserve that as a provider failure rather than reclassifying it as
Chirp budget exhaustion. Explicit shutdown remains a cancellation event with its
independent cleanup bound.

Repository-wide suites, native/managed/RookBIM builds, public promotion, and
unrelated live scenarios are outside acceptance unless an affected file's existing
focused gate requires them. Scope drift or an unexpected lower timeout stops for
review rather than expanding this correction.
