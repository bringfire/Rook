# LM5Y - Acceptance-Criteria Join Design

- **Date:** 2026-07-05
- **Status:** Draft for review
- **Slice:** LM5Y
- **Type:** Deterministic probe/runtime joining slice with tests

## 1. Purpose

LM5U proved a narrow positive worker result:

```text
diagnostics alone -> clarification
diagnostics + acceptance criteria -> action
```

LM5W extracted the LM5U acceptance-criteria section into a pure assembler:

```text
AcceptanceCriteriaSources -> rook.acceptance_criteria_packet:v1
```

LM5X extracted those typed sources from real passed fixture objects:

```text
workflow contract + graph receipt + convention packets
  -> AcceptanceCriteriaSources
```

LM5Y is the promised joining slice:

```text
real fixture objects
  -> extract AcceptanceCriteriaSources
  -> assemble acceptance criteria packet
  -> legacy worker-visible v3 acceptance_criteria section
```

The clean goal is to replace the hand-built LM5U
`fields.acceptance_criteria` section with LM5X extraction plus LM5W assembly,
while keeping worker-visible packet semantics stable.

LM5Y succeeds deterministically when the rendered v3 worker-visible packet is
unchanged, but its `acceptance_criteria` section is produced by LM5X
extraction plus LM5W assembly.

## 2. Controlled Variable

The controlled variable is internal construction only:

```text
hand-built acceptance_criteria section
  -> legacy projection of assemble(extract(real fixture objects))
```

The model input must not change.

LM5Y is not a new evidence-shape experiment. It is not a prompt slice, parser
slice, transport slice, model slice, or Planner integration slice.

## 3. Scope

Production/probe scope:

```text
scripts/lm5k_worker_probe.py
```

Test scope:

```text
mcp_server/tests/test_lm5k_worker_probe.py
mcp_server/tests/test_local_worker_acceptance_criteria_sources.py
mcp_server/tests/test_lm5r_two_pass_publication_probe.py only if an existing
  direct-import guard requires the LM5Y import-rule update
```

Documentation scope:

```text
docs/superpowers/specs/2026-07-05-lm5y-acceptance-criteria-join-design.md
docs/superpowers/plans/2026-07-05-lm5y-acceptance-criteria-join.md
```

Out of scope:

- No `mcp_server/src` production changes.
- No LM5W assembler changes.
- No LM5X extractor changes unless tests expose a genuine existing bug.
- No LM5R pass-1 or pass-2 prompt changes.
- No LM5R status, schema, anomaly, or publication-mechanics changes.
- No LM5G parser changes.
- No prompt artifact changes.
- No model or transport changes.
- No evidence shape changes visible to the worker.
- No manifest or attempt record changes.
- No live probe run inside the implementation PR.
- No curated evidence summary inside the implementation PR.

## 4. Visible Packet Compatibility

The worker-visible `evidence_present_v3` packet remains the LM5U packet:

```text
packet_id = lm5u_acceptance_criteria_evidence
kind = evidence
title = Acceptance-criteria repair evidence
state = post_verify_pre_bind
```

The packet fields remain:

```text
current_code
language
recommended_mode
repair_anchor
pin_contract
target_diagnostics
expected_repair_outcome
acceptance_criteria
```

No field may be added, removed, or renamed in LM5Y.

The `acceptance_criteria` field remains:

```python
{
    "source": (
        "workflow_contract + create_script.initial_execution_params + "
        "create_script.receipt.script_receipt.repair_anchor + "
        "script_body_gotcha"
    ),
    "criteria": [
        {
            "criterion_id": "...",
            "description": "...",
            "source": "...",
        },
        ...
    ],
}
```

The source string is part of the legacy worker-visible compatibility surface.
It must remain exactly:

```text
workflow_contract + create_script.initial_execution_params + create_script.receipt.script_receipt.repair_anchor + script_body_gotcha
```

## 5. Internal Construction

LM5Y may import the LM5W/LM5X boundaries into `scripts/lm5k_worker_probe.py`:

```python
from rook.agent.local_worker_acceptance_criteria import (
    assemble_acceptance_criteria_packet,
)
from rook.agent.local_worker_acceptance_criteria_sources import (
    extract_acceptance_criteria_sources,
)
```

The v3 packet builder constructs the legacy visible section from:

```python
sources = extract_acceptance_criteria_sources(
    workflow_contract=_probe_contract(),
    graph=graph,
    convention_packets=(_script_body_gotcha_packet(),),
)
packet = assemble_acceptance_criteria_packet(sources)
```

Then it projects the assembled criteria back to the LM5U visible shape:

```python
legacy_acceptance_criteria = {
    "source": LEGACY_ACCEPTANCE_CRITERIA_SOURCE,
    "criteria": [
        {
            "criterion_id": item["criterion_id"],
            "description": item["description"],
            "source": item["source"],
        }
        for item in packet["criteria"]
    ],
}
```

LM5Y must not expose these assembled-packet fields to the worker:

```text
schema
source_set
source_class
unresolved_intent
fingerprint
```

The assembled packet fingerprint is test evidence only in LM5Y. It is not
recorded in probe manifests, attempts, run summaries, or worker-visible
knowledge packets.

## 6. Import-Guard Shift

LM5X intentionally kept probe scripts from importing the new extractor while
the extractor was unconsumed. LM5Y is the join, so that temporary fence changes.

New rule:

```text
scripts/lm5k_worker_probe.py may import:
  rook.agent.local_worker_acceptance_criteria
  rook.agent.local_worker_acceptance_criteria_sources

but only for evidence_present_v3 acceptance-criteria construction.
```

Still forbidden:

```text
scripts/lm5r_two_pass_publication_probe.py must not import either module
directly.
```

LM5R continues to consume LM5K contexts indirectly through the existing
scenario selector path.

## 7. Tests

Deterministic tests must prove both truths:

```text
1. Worker-visible evidence_present_v3 packet is unchanged.
2. The acceptance_criteria section is now the legacy projection of the
   LM5W packet assembled from LM5X-extracted sources.
```

Required assertions:

- `evidence_present_v3` scenario id/version/packet id remain unchanged.
- `fields` set remains unchanged.
- `fields.acceptance_criteria.source` remains the exact legacy string.
- `fields.acceptance_criteria.criteria` has the same six criteria in the same
  order.
- Each visible criterion has exactly:
  - `criterion_id`
  - `description`
  - `source`
- The visible criteria equal:

```python
legacy_projection(
    assemble_acceptance_criteria_packet(
        extract_acceptance_criteria_sources(
            workflow_contract=_probe_contract(),
            graph=graph,
            convention_packets=(_script_body_gotcha_packet(),),
        )
    )["criteria"]
)
```

- The assembled packet fingerprint equals the LM5W/LM5X expected packet
  fingerprint.
- Rendered worker-visible v3 envelope does not contain:
  - `source_class`
  - `source_set`
  - `unresolved_intent`
  - `fingerprint`
  - `rook.acceptance_criteria_packet:v1`
- Rendered worker-visible v3 envelope still does not contain:
  - `PROBE_REPAIR_CODE`
  - `A = 42.0;`
  - hidden bind params
  - repair diff
  - replacement code
- `scripts/lm5r_two_pass_publication_probe.py` has no direct import of
  `local_worker_acceptance_criteria` or
  `local_worker_acceptance_criteria_sources`.

If `_acceptance_criteria()` has no remaining legitimate references after the
join, it may be removed. If tests or docs still need it as a legacy baseline,
the implementation may keep it, but v3 construction must no longer use a
hand-built criteria source.

## 8. Verification

Targeted deterministic gate:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm5k_worker_probe.py `
  mcp_server\tests\test_local_worker_acceptance_criteria_sources.py `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py `
  -q
```

Nearby gate:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_local_worker_acceptance_criteria.py `
  mcp_server\tests\test_local_worker_acceptance_criteria_sources.py `
  mcp_server\tests\test_lm5k_worker_probe.py `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py `
  -q
```

Static gates:

```powershell
py -3.10 -m py_compile `
  scripts\lm5k_worker_probe.py `
  mcp_server\tests\test_lm5k_worker_probe.py

git diff --check main..HEAD
```

If LM5Y updates import-guard tests outside `test_lm5k_worker_probe.py`, include
those touched test files in the `py_compile` command.

Confirm diff scope is limited to:

```text
docs/superpowers/specs/2026-07-05-lm5y-acceptance-criteria-join-design.md
docs/superpowers/plans/2026-07-05-lm5y-acceptance-criteria-join.md
scripts/lm5k_worker_probe.py
mcp_server/tests/test_lm5k_worker_probe.py
mcp_server/tests/test_local_worker_acceptance_criteria_sources.py
mcp_server/tests/test_lm5r_two_pass_publication_probe.py if import guards move
```

Confirm no `mcp_server/src` diff.

Confirm no raw `probe_runs/` artifacts.

## 9. Post-Merge Live Rerun

The implementation PR is deterministic only.

After merge, from synced `main`, run the same canonical LM5U/LM5R command:

```powershell
.\mcp_server\.venv\Scripts\python.exe scripts\lm5r_two_pass_publication_probe.py `
  --scenario evidence_absent_like `
  --scenario evidence_present_v3_like `
  --attempts 5
```

No Anthropic key is required.

The live rerun asks whether joining the internal evidence path preserved the
LM5U behavior under unchanged worker-visible input. It is not a new
acceptance-criteria evidence experiment.

Do not write a curated evidence summary until the live rerun result is
reviewed.

## 10. Success Criteria

LM5Y succeeds deterministically when:

```text
rendered v3 worker-visible packet is unchanged
acceptance_criteria is produced by LM5X extraction plus LM5W assembly
hidden repair answer remains absent
LM5R does not directly import LM5W/LM5X modules
deterministic tests pass
```

If the post-merge live run remains comparable to LM5U, the worker evidence path
has been joined to the durable assembly boundary without introducing a new
model-input variable.

## 11. Next Slice

If LM5Y lands cleanly and the post-merge live run is stable, the next slice can
move one level upstream:

```text
Planner/Compiler acceptance-criteria source extraction or contract ownership
```

That future slice should decide how real Planner/Compiler/verifier objects
produce the source facts LM5X currently receives from the probe fixture.

LM5Y should not attempt that integration.
