# Qwen3.8 Multimodal Vessel Massing V5 Pre-Contact

**Date:** 2026-08-20
**Status:** Frozen for one confirmation execution
**Purpose:** Confirm V4's architectural result with complete trace and checkpoint custody

## Bounded Delta

V5 preserves V4's two reference images, corrected architectural brief, Prime and
Qwen runtime, low thinking level, optional Python skill, adapter, Rook build,
tool surface, limits, target preparation, silent evaluation, and visual-review
requirements.

Only two demonstrated experimental boundaries change:

1. The runner's offline-only viewport classifier admits the exact successful
   `displayMode` argument variant used in V4. The request mode must be a nonempty
   string and must equal the returned mode. Other argument shapes and mismatches
   remain fail-closed.
2. The prompt states literally that the final receipt-fenced snapshot is the last
   Rook gateway call. Qwen must call `goal.complete()` immediately afterward and
   emit text only, without another diagnostic, viewport, status, or IPython call.

No semantic criterion, implementation algorithm, source code, component graph,
supervisor, product skill, adapter behavior, or shared evaluator changes.

## V4 Reproduction

Applying the corrected runner-only normalization in memory to V4's untouched
source leaves zero unknown events and selects terminal receipt:

```text
ce83238cc2328cbf7e54d430c933c188
```

V4's sealed source, manifests, hidden evaluation, and disposition remain
unchanged.

## Frozen Configuration

```text
Prime commit             739400844f8f3f280414b0c7b9c65797208815d3
model                    ollama_chat/qwen3.8:27b
thinking                 low
context                  131,072
goal token budget        9,500,000
provider token ceiling  10,000,000
wall-clock ceiling      10,800 seconds
gateway ceiling                500
skill SHA-256            2312DBF60EF17F9AA0B6503EDC281C7D367A5379F200ADEADB4747FD58A34F66
adapter SHA-256          06F1CB4AA58FD8C4C6F61F96CE7B8A5F4FEF7B6B126D00C0550B2CB3AA0BBF74
```

## Frozen Artifacts

```text
protocol
docs/superpowers/experiments/2026-08-20-qwen38-multimodal-vessel-massing-v5.json

protocol SHA-256
4D6FBBBF7329189FAC4A48C5DC28603D33B2248AE489503D549336059190DB2D

runner SHA-256
F18E0FFC3C86B6CF0A93F356EB714FCA188BCCCAD5FFA3D81635514F81CC1B14

shared acceptance SHA-256
8A68408AD6216A7DEF638EAC962B28CA7A32735312DCD00C57D038EAD8DEBAF5

evidence root
C:/UDEV/RookEvidence/2026-08-20-qwen38-multimodal-vessel-massing-v5
```

The focused runner and acceptance suites pass 249 tests with 11 existing
dependency warnings. Python compilation, protocol JSON parsing, and whitespace
validation pass. Prime is clean at the frozen commit, Rhino PID `210020` remains
available, Ollama is unloaded, and the V5 evidence root is absent.

## Execution Rule

Execute one fresh V5 Actor transaction. Evaluator feedback remains silent until
the Actor ends. Preserve and adjudicate the run even if it fails. Do not modify
or overwrite V4. Any further attempt requires a new evidence root and a concrete
observed failure.
