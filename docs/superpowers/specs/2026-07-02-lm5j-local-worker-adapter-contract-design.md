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

LM5J does not re-validate the envelope's interior; LM5I owns that shape. The
prompt renderer checks the boundary identity, then renders faithfully.

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
    failure_reason: str | None       # sanitized, LM5D-style payload discipline
    raw_output_excerpt: str | None   # bounded; see §4.4

def run_local_worker_adapter(
    request_payload: Mapping[str, Any],
    transport: LocalWorkerTransport,
) -> LocalWorkerAdapterRecord:
    ...
```

### 4.2 Invocation flow

```text
validate envelope boundary (via the prompt renderer's checks)
-> render prompt artifact
-> transport.send(artifact)
     TransportError            -> status=transport_error
     unexpected exception      -> status=transport_error
                                  (reason distinguishes declared vs unexpected)
-> parse raw output to a JSON mapping
     not parseable / not a mapping -> status=raw_output_invalid
-> load_local_worker_turn_response_payload(mapping)   (LM5G)
     loader rejection          -> status=response_payload_invalid
-> status=response_loaded, response attached
```

Invalid *input* (bad envelope, non-callable transport) raises — caller error,
not a record. Records describe what happened at or beyond the transport
boundary; exceptions describe misuse of the adapter itself. Statuses are
terminal outcomes of one bounded invocation; there is no `prompt_rendered`
in-flight status because the adapter never returns mid-flight.

### 4.3 Raw output parse policy

Strict-first, with exactly two documented normalizations, each deterministic
and tested:

1. strip leading/trailing whitespace;
2. if the entire remaining text is a single fenced block
   (```` ```json?...``` ````), unwrap it once.

Then `json.loads`; the result must be a mapping. No regex extraction of
embedded JSON, no repair, no retries, no partial salvage. If LM5K evidence
shows common failure wrappers beyond the fence case, leniency is a *versioned
policy change* with new tests, not an ad hoc patch.

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
- deterministic render: identical envelope → byte-identical artifact;
- system text renders kinds/field-sets/refusal categories from
  `response_contract` (mutate the envelope's contract, see the prompt change);
- no hand-restated contract facts (guard: the instruction constant contains no
  kind/field literals — they must flow from the envelope);
- messages shape exact; no extra keys.

### Adapter unit coverage

- record schema/status taxonomy exact;
- happy path: canned strict-JSON raw output → `response_loaded` with a real
  `LocalWorkerTurnResponse`;
- fenced output unwraps once; double-fence and prose-wrapped JSON →
  `raw_output_invalid`;
- non-JSON, JSON non-mapping → `raw_output_invalid`;
- LM5G-rejected mapping (wrong schema, wrong kind, missing field) →
  `response_payload_invalid`;
- declared `TransportError` and unexpected exception → `transport_error` with
  distinguishable sanitized reasons;
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

## 9. Open Questions For Review

1. **Excerpt bound:** N=500 characters proposed; confirm or adjust.
2. **Fence normalization:** included as the one pragmatic leniency (§4.3);
   strike it if you want pure-strict for the first probe read.
3. **`response` on non-loaded records:** proposed always `None` except
   `response_loaded`; alternative is carrying the parsed-but-rejected mapping
   for diagnosis (leans against, per retention policy — the excerpt plus
   LM5G's error message should suffice).
