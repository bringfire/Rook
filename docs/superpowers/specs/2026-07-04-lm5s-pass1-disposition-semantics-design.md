# LM5S Pass-1 Disposition Semantics Design

## 1. Purpose

LM5S is a diagnostic evidence-only revision of the LM5R two-pass publication
probe.

LM5R proved the publication mechanism:

```text
pass 1 thinks and decides freely
pass 2 publishes through a single-kind schema
```

The live LM5R run published `10/10` attempts, loaded `10/10` through LM5G, and
preserved `10/10` pass-1 kinds. It also exposed a new failure mode in
`evidence_absent_like`: Gemma chose `observation` in all five attempts, but the
observation carried action intent:

```json
{
  "kind": "observation",
  "message": "Decision: draft_repair_params",
  "data": {"action_id": "draft_repair_params"}
}
```

So LM5R proved publication preservation, not clean restraint semantics.

LM5S asks:

```text
Can clearer generic pass-1 kind applicability semantics reduce the observation
action-intent leak while preserving the same two-pass publication mechanics?
```

## 2. Design Line

LM5S changes pass-1 decision semantics and adds report-only anomaly evidence.
It does not change publication mechanics.

Controlled changes:

```text
PASS1_DECISION_INSTRUCTION_VERSION = "lm5s.pass1_decision_instruction:v2"
_PASS1_DECISION_INSTRUCTION gets generic per-kind applicability semantics
observation action-intent anomaly scoring is added to local evidence rows/summary
```

Unchanged:

```text
pass-2 formatter prompt
single-kind response schemas
two-pass flow
canonical model/scenarios/attempt count
status taxonomy
LM5G loader behavior
LM5N evidence packets
LM5J prompt artifact
```

Historical LM5R evidence remains interpretable because LM5R recorded
`lm5r.pass1_decision_instruction:v1` and the pass-1 instruction hash. After
LM5S, the active script default becomes
`lm5s.pass1_decision_instruction:v2` with a new hash.

## 3. Scope

LM5S may modify only:

```text
scripts/lm5r_two_pass_publication_probe.py
mcp_server/tests/test_lm5r_two_pass_publication_probe.py
docs/superpowers/specs/2026-07-04-lm5s-pass1-disposition-semantics-design.md
docs/superpowers/plans/2026-07-04-lm5s-pass1-disposition-semantics.md
```

LM5S must not add:

```text
new LM5S script
v1/v2 CLI selector
production mcp_server/src changes
curated evidence doc update during implementation
```

LM5S must not change:

```text
LM5G response loader/parser behavior
LM5J prompt text or prompt artifact renderer
LM5N evidence packet shape or contents
LM5K probe runner
LM5R pass-2 formatter prompt
LM5R single-kind schemas
production adapter/transport behavior
```

Raw and summary artifacts remain local under ignored `probe_runs/`.

## 4. Pass-1 Instruction v2

LM5S updates only the diagnostic pass-1 decision instruction appended by
`scripts/lm5r_two_pass_publication_probe.py`.

The instruction version becomes:

```python
PASS1_DECISION_INSTRUCTION_VERSION = "lm5s.pass1_decision_instruction:v2"
```

The instruction must remain generic:

```text
no draft_repair_params
no repair_same_component
no code/mode scenario fields
no component GUIDs
no model names
no raw run excerpts
```

It should define the applicability of each response kind:

```text
action_request:
  choose only when visible context is sufficient to author the required action
  input

clarification_request:
  choose when required information is missing

refusal:
  choose when the request is unsafe, unsupported, or out of scope

observation:
  choose only to report visible state or evidence
  never use observation to choose, suggest, imply, or carry an action
  do not put action identity or action choice in observation.message or
  observation.data
```

The pass-1 decision artifact shape remains the LM5R shape:

```text
all:
  kind

action_request:
  action_id

clarification_request:
  question

refusal:
  category
  reason

observation:
  message

optional:
  rationale
  intent
  action_input_intent
  known_inputs
  data_intent
```

LM5S does not require pass 1 to emit a strict LM5G response envelope.

## 5. Report-Only Anomaly Scoring

LM5S adds observation action-intent anomaly scoring as a diagnostic dimension.

It must not change attempt status. If a response is LM5G-loadable and preserves
the pass-1 kind/action/category invariants, the row remains:

```text
status = published
```

The anomaly answers a separate question:

```text
Did an observation carry allowed-action identity or action choice?
```

Interpretation:

```text
published + anomaly:
  publication preserved the decision, but pass-1 disposition semantics failed

published + no anomaly:
  publication preserved the decision and no action-intent observation leak was
  detected
```

## 6. Allowed-Action-Id Leak Detection

LM5S anomaly scoring is intentionally narrow. It detects only allowed-action-id
leakage from observations.

Allowed action ids are derived from the request envelope:

```python
allowed_action_ids = {
    action["action_id"]
    for action in request_payload["context"]["allowed_actions"]
}
```

The script must not hardcode scenario action ids such as `draft_repair_params`
in anomaly logic.

Score only payloads whose parsed `kind` is `observation`.

Reasons:

```text
observation_data_action_id_allowed:
  observation.data.action_id exactly equals an allowed action id

observation_message_mentions_allowed_action_id:
  observation.message contains an allowed action id

observation_data_mentions_allowed_action_id:
  any string value under observation.data contains an allowed action id
```

Do not add generic action-decision language detection in LM5S. In particular,
do not score phrases such as `Decision:` unless they also carry an allowed action
id. Generic text classification would turn the probe into semantic scoring.

## 7. Parsed Objects Only

Anomaly scoring inspects parsed objects only:

```text
pass 1:
  parsed decision object returned by _parse_pass1_decision

pass 2:
  parsed response object after JSON parse and successful LM5G load
```

Do not scan:

```text
raw provider content
thinking text
excerpts
prompt text
surrounding prose
truncated output
```

Ordering:

```text
pass1 anomaly:
  score immediately after pass1 decision parses

pass2 anomaly:
  score only after LM5G load succeeds
```

If pass 2 is not LM5G-loadable, structural failure is already recorded and
anomaly scoring would be noisy.

Suggested helper shape:

```python
def _observation_action_intent_reasons(
    *,
    payload: Mapping[str, Any],
    allowed_action_ids: Collection[str],
) -> tuple[str, ...]:
    ...
```

It returns an empty tuple unless:

```python
payload.get("kind") == "observation"
```

Recursive data scanning is limited to already-parsed JSON-shaped values:

```text
Mapping values:
  recurse

list/tuple values:
  recurse

str:
  substring-check allowed action ids

other scalars:
  ignore
```

## 8. Evidence Row Fields

Each attempt row should add pass-specific and combined anomaly fields:

```text
pass1_observation_action_intent_anomaly: bool
pass1_observation_action_intent_reasons: list[str]

pass2_observation_action_intent_anomaly: bool
pass2_observation_action_intent_reasons: list[str]

observation_action_intent_anomaly: bool
observation_action_intent_reasons: list[str]
```

The combined field is:

```text
pass1 anomaly OR pass2 anomaly
```

Combined reasons are the sorted union of pass-specific reasons. If both passes
leak through the same route, the combined reason appears once while the
pass-specific fields preserve attribution.

## 9. Summary Fields

LM5S should add summary group fields:

```text
observation_action_intent_anomaly_count
observation_action_intent_reason_counts
```

These fields aggregate the combined anomaly fields, not just pass 1 or pass 2.

The existing grouping dimensions remain focused on publication status and
preservation:

```text
scenario
status
pass1_kind
pass2_response_kind
kind_preserved
action_id_preserved
refusal_category_preserved
```

LM5S does not add a new status such as `published_with_anomaly`.

## 10. Canonical Run

LM5S keeps the canonical LM5R live run unchanged:

```text
model: gemma4:12b-it-qat
scenarios:
  evidence_absent_like
  evidence_present_like
attempts: 5
provider: direct Ollama /api/chat
pass1: no format, think=true, temperature=0
pass2: single-kind format, think=false, temperature=0
```

Canonical command:

```powershell
cd C:\UDEV\Rook
.\mcp_server\.venv\Scripts\python.exe scripts\lm5r_two_pass_publication_probe.py `
  --model "gemma4:12b-it-qat" `
  --scenario evidence_absent_like `
  --scenario evidence_present_like `
  --attempts 5 `
  --excerpt-chars 1200
```

No Anthropic key is required.

## 11. Success Reads

LM5S is not a model-quality ranking and not semantic repair-quality scoring.

Useful outcomes:

```text
evidence_absent_like moves to clarification_request/refusal:
  pass-1 kind semantics improved restraint

evidence_absent_like stays observation but anomaly count drops to 0:
  observation remains a state-reporting choice, but no action identity leak was
  detected

evidence_absent_like stays observation with anomaly count > 0:
  pass-1 semantics still fail; observation remains an action-intent escape hatch

evidence_present_like action_request remains published and kind-preserved:
  v2 did not break the action path
```

Do not over-read semantic repair quality. A valid action request with weak code
is still a separate evidence-quality or verifier-execution question.

## 12. Tests

Deterministic tests should cover:

```text
PASS1_DECISION_INSTRUCTION_VERSION is lm5s.pass1_decision_instruction:v2
manifest records the v2 version and instruction hash
pass-1 instruction contains generic per-kind applicability semantics
pass-1 instruction forbids observation carrying action identity/choice
pass-1 instruction contains no scenario-specific literals

anomaly helper returns empty for non-observation payloads
anomaly helper detects observation.data.action_id matching allowed action id
anomaly helper detects allowed action id in observation.message
anomaly helper detects allowed action id recursively under observation.data
anomaly helper does not use hardcoded draft_repair_params logic

pass1 anomaly fields are set after decision parse
pass2 anomaly fields are set only after LM5G load succeeds
published status remains published when anomaly is true
summary counts anomaly rows and reasons
```

Boundary tests or static guards should confirm LM5S does not touch production
modules and does not add new response parser leniency.

## 13. Verification

Targeted:

```powershell
cd C:\UDEV\Rook
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py -q
```

Nearby:

```powershell
cd C:\UDEV\Rook
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py `
  mcp_server\tests\test_lm5p_ollama_think_format_spike.py `
  mcp_server\tests\test_lm5k_worker_probe.py -q
```

Static:

```powershell
cd C:\UDEV\Rook
py -3.10 -m py_compile `
  scripts\lm5r_two_pass_publication_probe.py `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py

git diff --check origin/main..HEAD
git diff --name-only origin/main..HEAD
```

Expected scope:

```text
docs/superpowers/specs/2026-07-04-lm5s-pass1-disposition-semantics-design.md
docs/superpowers/plans/2026-07-04-lm5s-pass1-disposition-semantics.md
scripts/lm5r_two_pass_publication_probe.py
mcp_server/tests/test_lm5r_two_pass_publication_probe.py
```

No live run belongs in the implementation PR before deterministic gates pass.
After merge, run the unchanged canonical LM5R/LM5S command and review local
evidence before writing any curated evidence summary.

## 14. Non-Goals

LM5S does not add:

```text
semantic repair-quality scoring
generic action-intent text classification
prompt artifact changes
LM5G parser changes
LM5N evidence changes
production adapter or transport changes
new script family
v1/v2 selector
schema-ordering experiments
two-pass production implementation
curated evidence doc update during implementation
```

The likely follow-up depends on the LM5S evidence:

```text
if anomaly disappears:
  summarize LM5S and consider whether the pass-1 semantics are good enough for
  a later production two-pass proposal

if anomaly persists:
  design the next diagnostic slice around pass-1 disposition semantics or
  explicit decision-contract validation, not publication mechanics
```
