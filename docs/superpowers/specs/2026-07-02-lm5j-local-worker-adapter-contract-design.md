# LM5J - Local Worker Adapter Contract / Prompt Artifact Boundary Design

**Date:** 2026-07-02
**Status:** Design draft for review
**Campaign:** Rook local/internal models north-star, LM5 worker transport boundary; first slice under the planner-harness north-star's §5.1 next-empirical-pressure decision (PR #395)
**Predecessors:** LM5A turn context, LM5B response contract, LM5C disposition, LM5D one-turn harness, LM5E scenario suite, LM5F scenario evaluation, LM5G response payload loader, LM5H context payload renderer, LM5I request envelope (PR #394)
**Successor (named, not specced):** LM5K first local worker model probe

---

## 1. Goal

LM5J builds the socket the first live model will plug into. It is fully
deterministic: no live model, no provider dependency, no network.

LM5I closed the transport shape. LM5J closes the adapter contract around it:

```text
LM5I request envelope
-> prompt/message artifact               (LM5J, deterministic render)
-> transport invocation                  (LM5J protocol; fake in tests)
-> raw output parsing                    (LM5J)
-> LM5G response payload loading         (existing)
-> adapter record                        (LM5J taxonomy)
```

LM5J answers only:

```text
Given an LM5I request envelope and a transport, can Rook deterministically
produce either a syntactically loadable LM5B response or a typed
transport/parse failure artifact — with the whole path testable offline?
```

It does not answer:

```text
Which model or provider should run?          (LM5K + model selection policy)
How do candidate models actually behave?     (LM5K probe evidence)
Is a loaded response admissible/good?        (LM5B validation, LM5C disposition)
Should an action execute?                    (runner)
Should the stream continue?                  (runner)
```

Layer split:

```text
LM5A: Rook-owned artifacts -> LocalWorkerTurnContext
LM5H: context -> context payload
LM5I: context -> request envelope payload
LM5J: request envelope -> prompt artifact -> transport -> raw output
      -> response payload -> adapter record
LM5K: live provider transport + probe evidence artifacts (future)
LM5G: response payload -> LocalWorkerTurnResponse
LM5B/C/D/F: admissibility, disposition, harness, evaluation (unchanged)
```

The adapter is **one bounded invocation, not a miniature worker loop**. It has
no retry, no repair, no multi-turn state, no evaluation. Its terminal act is a
record.

---

## 2. Production Scope

Add two production modules:

```text
mcp_server/src/rook/agent/local_worker_prompt_artifact.py
mcp_server/src/rook/agent/local_worker_adapter.py
```

Add two focused test files:

```text
mcp_server/tests/test_local_worker_prompt_artifact.py
mcp_server/tests/test_local_worker_adapter.py
```

Do not edit any LM5A-I production module. If implementation reveals a genuine
LM5A-I bug, treat it as a separate finding.

No package-level exports. Callers import explicitly from the two new modules.

---

## 3. Prompt Artifact Boundary (`local_worker_prompt_artifact.py`)

### 3.1 Public surface

```python
LOCAL_WORKER_PROMPT_ARTIFACT_SCHEMA = "rook.local_worker_prompt_artifact:v1"
LOCAL_WORKER_PROMPT_TEXT_VERSION = "lm5j.prompt_text:v1"

def render_local_worker_prompt_artifact(
    request_payload: Mapping[str, Any],
) -> Mapping[str, Any]:
    ...
```

### 3.2 Accepted input

- `request_payload` must be a mapping whose `"schema"` equals
  `rook.local_worker_turn_request:v1` (the LM5I constant, imported — not
  retyped) and whose top-level key set is exactly LM5I's
  (`schema`, `context`, `response_schema`, `response_contract`).
- Anything else raises `TypeError`/`ValueError`. No duck typing, no partial
  envelopes, no schema-less authoring.

**The `response_contract` interior is load-bearing for prompt text and is
validated — the prompt contract fails closed if mutated.** Because the LM5I
payload is a mutable transport copy, LM5J re-validates exactly the sections it
reads before rendering instructions from them:

- `kinds`: non-empty sequence of non-empty strings;
- `field_sets`: mapping with string keys covering every kind, each value a
  non-empty sequence of non-empty strings;
- `required_nullable_fields`: mapping, string keys drawn from `kinds`, each
  value a sequence of non-empty strings;
- `refusal_categories`: non-empty sequence of non-empty strings.

Shape violations raise `ValueError`. LM5J does not re-validate the rest of the
envelope interior (`context` stays LM5I/LM5H's shape responsibility); only
what the renderer consumes is pinned.

### 3.3 Artifact shape

```python
{
    "schema": LOCAL_WORKER_PROMPT_ARTIFACT_SCHEMA,
    "prompt_text_version": LOCAL_WORKER_PROMPT_TEXT_VERSION,
    "messages": [
        {"role": "system", "content": "<versioned instruction text>"},
        {"role": "user", "content": "<canonical JSON of the request envelope>"},
    ],
}
```

- **Deterministic:** identical envelope in, byte-identical artifact out. The
  user-message JSON serialization is the one place LM5J is allowed to call
  `json.dumps`, with sorted keys and stable separators, so determinism is
  checkable.
- **No hidden instructions:** the system text is a module-level versioned
  constant. It describes the response contract *mechanically* — the allowed
  response kinds, per-kind field sets, required-nullable fields, and refusal
  categories are rendered from the envelope's machine-readable
  `response_contract`, never restated by hand. Prompt prose is limited to
  role framing ("you are a bounded worker; answer with exactly one JSON
  object matching one of these envelopes") and output discipline ("JSON only,
  no code fences, no commentary").
- **Versioned:** any change to instruction text bumps
  `LOCAL_WORKER_PROMPT_TEXT_VERSION`. LM5K probe artifacts will key on it so
  model behavior is attributable to an exact prompt.

### 3.4 Explicit exclusions

No Capability Index binding, no `workflow_validate`, no action authorization,
no model selection, no provider/tokenizer awareness, no per-model prompt
dialects (a per-model dialect, if ever justified by LM5K evidence, is a new
versioned artifact, not a branch inside v1).

---

## 4. Adapter Contract (`local_worker_adapter.py`)

### 4.1 Public surface

```python
LOCAL_WORKER_ADAPTER_RECORD_SCHEMA = "rook.local_worker_adapter_record:v1"

class LocalWorkerTransport(Protocol):
    def send(self, prompt_artifact: Mapping[str, Any]) -> str:
        """Return raw model output text, or raise TransportError."""

class TransportError(Exception):
    ...

@dataclass(frozen=True)
class LocalWorkerAdapterRecord:
    schema: str                      # record schema constant
    status: Literal[
        "response_loaded",
        "response_payload_invalid",
        "raw_output_invalid",
        "transport_error",
    ]
    prompt_schema: str               # prompt artifact schema constant
    prompt_text_version: str
    response: LocalWorkerTurnResponse | None   # only when response_loaded
    failure_reason: str | None       # exact taxonomy, §4.2a; None iff loaded
    raw_output_excerpt: str | None   # bounded; see §4.4

def run_local_worker_adapter(
    request_payload: Mapping[str, Any],
    transport: LocalWorkerTransport,
) -> LocalWorkerAdapterRecord:
    ...
```

### 4.2 Invocation flow

```text
validate envelope boundary + response_contract shape (prompt renderer, §3.2)
-> render prompt artifact
-> transport.send(artifact)
     TransportError            -> status=transport_error
     other Exception           -> status=transport_error
     BaseException             -> PROPAGATES (never a record)
-> require raw output is str            else raw_output_invalid
-> trim; require non-empty              else raw_output_invalid
-> json.loads                           failure -> raw_output_invalid
-> require mapping                      else raw_output_invalid
-> load_local_worker_turn_response_payload(mapping)   (LM5G)
     loader rejection          -> status=response_payload_invalid
-> status=response_loaded, response attached
```

Exception discipline (LM5D-style pin): the transport call catches `Exception`
only. `KeyboardInterrupt`, `SystemExit`, and all other `BaseException`s
propagate.

Invalid *input* (bad envelope, mutated `response_contract`, non-callable
transport) raises — caller error, not a record. Records describe what happened
at or beyond the transport boundary; exceptions describe misuse of the adapter
itself. Statuses are terminal outcomes of one bounded invocation; there is no
`prompt_rendered` in-flight status because the adapter never returns
mid-flight.

### 4.2a Failure reason taxonomy (exact, stable strings)

`failure_reason` is `None` iff `status == "response_loaded"`; otherwise it is
exactly one of the following stable forms (LM5D reason-payload discipline:
sanitized detail segments, ASCII alnum/underscore-safe):

| Status | `failure_reason` |
|---|---|
| `transport_error` | `transport_error:declared` |
| `transport_error` | `transport_error:unexpected:<ExceptionClassName>` |
| `raw_output_invalid` | `raw_output_invalid:not_text:<TypeName>` |
| `raw_output_invalid` | `raw_output_invalid:empty` |
| `raw_output_invalid` | `raw_output_invalid:json_decode` |
| `raw_output_invalid` | `raw_output_invalid:not_mapping` |
| `response_payload_invalid` | `response_payload_invalid:<sanitized_detail>` |

`<sanitized_detail>` carries the LM5G rejection cause after sanitization.
Non-string transport returns are a record (`not_text`), not an exception: the
transport boundary already executed, so its misbehavior is transport-side
evidence, consistent with the records-vs-exceptions rule above. Tests pin
every reason string exactly; new reasons are a schema-visible change, not a
drive-by.

### 4.3 Raw output parse policy

Strict for v1, with exactly one normalization: strip leading/trailing
whitespace. Then `json.loads`; the result must be a mapping.

**No fence unwrapping.** The prompt instructs "JSON only, no code fences"; a
fenced response is therefore `raw_output_invalid` (`json_decode`), so LM5K's
first probe measures prompt discipline cleanly instead of hiding
non-compliance behind a normalization. No regex extraction of embedded JSON,
no repair, no retries, no partial salvage. If LM5K evidence justifies
leniency (fences included), it arrives as a *versioned policy change* with new
tests and probe-artifact visibility, not an ad hoc patch.

### 4.4 Raw output retention policy

- Production records carry at most a **bounded excerpt**
  (`raw_output_excerpt`, first N=500 characters, control characters
  replaced), because model output can contain user/project content.
- `response_loaded` records may omit the excerpt (the loaded response is the
  content of record).
- Full raw output is **never** stored in an adapter record. Full-output
  capture is an opt-in LM5K probe artifact.
- Tests assert against canned raw outputs directly (they own the fixture), not
  against record excerpts, except where the excerpt policy itself is under
  test.

### 4.5 Relationship to LM5D (the composition rule)

The adapter is **not** a `LocalWorkerTurnWorker`. LM5D's seam expects
`Callable[[LocalWorkerTurnContext], LocalWorkerTurnResponse]`; the adapter
consumes an envelope and returns a record. One integration test (§6) proves a
thin test-local wrap — adapter behind a fake transport, surfaced as a worker
callable, run through LM5D/LM5F — but that wrap is **test-only in LM5J**.
Promoting a production composition ("model-backed worker") is LM5K-or-later
scope, decided with probe evidence in hand.

---

## 5. Import And Boundary Rules

`local_worker_prompt_artifact.py` may import:

- `LOCAL_WORKER_TURN_REQUEST_SCHEMA` from `local_worker_turn_request`;
- stdlib (`json` for the deterministic dump only).

`local_worker_adapter.py` may import:

- the prompt artifact module;
- `load_local_worker_turn_response_payload` and
  `LocalWorkerTurnResponse` from the LM5G/LM5B modules;
- stdlib (`json` for `json.loads` only).

Neither module may import or reference:

```text
model_profiles / base_agent / chat runner / RookChat / dispatcher
litellm / openai / provider SDKs / network clients
Capability Index modules
plan_graph_* runtime modules
LM5C disposition / LM5D harness / LM5F evaluation   (production; tests may)
workflow contract compiler/loader
Path / open / file IO
```

The AST guard follows the LM5H function-scoped precedent where module-level
imports are legitimate, and module-wide otherwise.

LM5J is deliberately the first LM5 production layer allowed to call
`json.loads` — raw-text parsing is the adapter's declared job (LM5I refused
it by design). It remains forbidden everywhere else in the LM5 family.

---

## 6. Tests

### Prompt artifact unit coverage

- schema/version constants exact;
- boundary rejection: wrong type, wrong schema tag, wrong key set;
- `response_contract` shape validation fails closed per §3.2: non-sequence
  kinds, empty kinds, non-string kind, field_sets missing a kind, non-string
  field name, malformed required_nullable_fields, empty refusal_categories;
- deterministic render: identical envelope → byte-identical artifact;
- system text renders kinds/field-sets/refusal categories from
  `response_contract` (mutate the envelope's contract, see the prompt change);
- no hand-restated contract facts (guard: the instruction constant contains no
  kind/field literals — they must flow from the envelope);
- messages shape exact; no extra keys.

### Adapter unit coverage

- record schema/status taxonomy exact;
- **failure reason strings pinned exactly per §4.2a** (every row exercised,
  including `not_text:<TypeName>` for a non-string transport return and
  `unexpected:<ExceptionClassName>` sanitization);
- happy path: canned strict-JSON raw output → `response_loaded` with a real
  `LocalWorkerTurnResponse`, `failure_reason is None`;
- fenced output → `raw_output_invalid` (`json_decode`) — no unwrapping;
  prose-wrapped JSON likewise;
- empty/whitespace-only output → `raw_output_invalid:empty`;
- non-JSON, JSON non-mapping → `raw_output_invalid` with the exact reason;
- LM5G-rejected mapping (wrong schema, wrong kind, missing field) →
  `response_payload_invalid:<sanitized_detail>`;
- declared `TransportError` vs unexpected `Exception` → distinguishable exact
  reasons; `KeyboardInterrupt`/`SystemExit` propagate (no record);
- mutated `response_contract` (wrong shape in kinds/field_sets/
  required_nullable_fields/refusal_categories) → raises, fail closed;
- excerpt bounding and control-character replacement;
- full raw output never present on any record;
- invalid envelope/transport raises (no record);
- import/AST guard per §5.

### Integration proof (test-local composition)

```text
compiled repair workflow (LM4W fixture)
-> build_local_worker_turn_context
-> render_local_worker_turn_request_payload (LM5I)
-> run_local_worker_adapter with a deterministic fake transport that answers
   a strict action_request payload read from the envelope's allowed_actions
-> record.status == response_loaded
-> test-local wrap: adapter surfaced as LocalWorkerTurnWorker
-> run_local_worker_turn (LM5D) -> evaluate (LM5F) -> passed
```

This is the offline dress rehearsal for LM5K: the probe will replace exactly
one element — the fake transport — with a live provider.

---

## 7. Verification

Targeted, then the focused local-worker gate (LM5 test files + plan-graph
suite), matching the LM5H/LM5I verification pattern; `git diff --check`;
production diff limited to the two new modules; no LM5A-I production edits;
no live test, no network, no provider SDK anywhere in the branch.

---

## 8. Explicit Non-Goals

- live model calls, provider SDKs, model/provider selection policy;
- LM5B/C/D/F evaluation inside the adapter (integration test composes them;
  production does not);
- production `LocalWorkerTurnWorker` composition;
- retries, fallbacks, repair, multi-turn state, streaming;
- prompt dialects per model/provider;
- full raw-output retention;
- probe evidence artifact format (LM5K owns it);
- Capability Index, workflow_validate, dispatch, graph mutation, stream
  continuation;
- async transport (LM5K decides if the live seam needs it; adding async later
  is additive).

---

## 9. Review Resolutions (round 1, 2026-07-02)

1. **Excerpt bound:** N=500 stands (no objection raised).
2. **Fence normalization:** REMOVED for v1 per review — whitespace trim only;
   fenced output is `raw_output_invalid` so the first probe measures prompt
   discipline cleanly (§4.3).
3. **`response` on non-loaded records:** `None` except `response_loaded`,
   confirmed.
4. **`prompt_rendered` status:** not a terminal record outcome, confirmed
   absent.
5. **Failure reasons:** pinned to the exact stable taxonomy in §4.2a
   (review P2).
6. **`response_contract` interior:** validated fail-closed before prompt
   rendering (§3.2) (review P2).
7. **Exception discipline:** catch `Exception` only; `BaseException`
   propagates (§4.2) (review P3).
