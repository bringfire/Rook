# Qwen3.8 Varied-Product Cohort V1 Efficiency Attribution

Date: 2026-08-18

Classification: **offline measurement and one bounded intervention
recommendation; no intervention implemented or qualified**

## Scope

This report analyzes the sealed varied-product cohort recorded at commit
`2e204b1cefd319fcf742786f5781663bf2810ef9`. It asks where context grew,
which retained gateway results were large, which information requests repeated,
and when the two expensive rows first possessed materially sufficient artifact
evidence.

The source archive remained immutable:

```text
C:/UDEV/RookEvidence/2026-08-18-qwen38-varied-product-cohort-v1
```

No Rhino, Grasshopper, Rook MCP, Prime runtime, Ollama, Qwen, deployment, or
network contact occurred. No Prime, Rook product, installed-runtime, adapter,
or skill bytes changed.

The analysis utility and complete per-turn sidecar are:

```text
scripts/qwen38_varied_product_efficiency_analysis.py
docs/superpowers/reports/
  2026-08-18-qwen38-varied-product-cohort-v1-efficiency-attribution.json
```

Reproduction command:

```powershell
& C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe `
  scripts/qwen38_varied_product_efficiency_analysis.py `
  --evidence-root C:/UDEV/RookEvidence/2026-08-18-qwen38-varied-product-cohort-v1 `
  --output docs/superpowers/reports/2026-08-18-qwen38-varied-product-cohort-v1-efficiency-attribution.json
```

## Measurement Boundary

Three different quantities are kept separate.

1. **Provider-reported input tokens** are the context size reported for each
   model turn. Their sum is repeated provider processing, not unique context.
2. **Canonical gateway-result bytes** are the exact parsed `result` values from
   the sealed `source.jsonl`, serialized deterministically. They measure audit
   payload volume attributable to each gateway tool.
3. **Prime-retained tool-result text bytes** are the UTF-8 text in native
   session `toolResult` content. They are closer to what Qwen saw after each
   IPython cell, but remain bytes rather than provider tokens.

Prime session content bytes also count retained assistant thinking, assistant
text, IPython arguments, tool-result text, the goal context message, and the
user message. This is selected native-session content, not a reconstruction of
the provider's serialized prompt. It excludes provider system material and
protocol overhead.

Therefore this report establishes volume, repetition, and temporal
correlation. It does **not** establish a token conversion ratio or claim that a
particular gateway byte caused a particular provider token.

Repeated requests are classified mechanically:

- **Exact request repeat:** same tool and exact canonical arguments.
- **Exact repeated information:** an exact request repeat whose canonical
  result is also identical.
- **Near request repeat:** only one of three closed shapes: the same normalized
  library/search term with different options, the same snapshot projection
  shape with different preview/receipt options, or overlapping selectors in
  `gh_batch_component_info`.

A repeated request is not automatically unnecessary. Snapshots, status, and
diagnostics can legitimately repeat after mutation because live state changes.

## Per-Turn Context Growth

The JSON sidecar retains every turn's input, output, and inter-turn input
growth. Summary:

| Row | Turns | First input | Final input | Net growth | Mean inter-turn growth | Largest growth |
|---|---:|---:|---:|---:|---:|---:|
| VP1 | 24 | 5,174 | 34,445 | 29,271 | 1,272.652 | 5,951 at turn 9 |
| VP2 | 46 | 5,167 | 85,407 | 80,240 | 1,783.111 | 11,324 at turn 25 |
| VP3 | 42 | 5,174 | 81,799 | 76,625 | 1,868.902 | 10,635 at turn 18 |

Provider totals:

| Row | Cumulative input | Cumulative output | Final input / cumulative input |
|---|---:|---:|---:|
| VP1 | 484,254 | 17,351 | 7.1% |
| VP2 | 2,012,994 | 60,694 | 4.2% |
| VP3 | 2,009,582 | 47,558 | 4.1% |

The low ratios in the last column show the main operational multiplier:
VP2 and VP3 did not retain two million unique tokens. They repeatedly processed
a transcript that grew to roughly 82K-85K input tokens over 42-46 turns.

The largest VP2 increases occurred at turns 25 (`+11,324`), 18 (`+7,166`),
24 (`+6,257`), 23 (`+6,086`), and 10 (`+5,661`). The largest VP3 increases
occurred at turns 18 (`+10,635`), 22 (`+9,697`), 10 (`+6,280`), 15
(`+5,217`), and 13 (`+3,684`). These are measured context jumps. The trace
often places long generated plans, code, or printed metadata near them, but the
provider report does not expose a causal byte-to-token allocation.

## Retained Gateway Result Volume

### By Category

| Row | Category | Calls | Canonical result bytes |
|---|---|---:|---:|
| VP1 | component discovery | 7 | 14,046 |
| VP1 | schema / metadata | 9 | 14,274 |
| VP1 | structural observation | 2 | 6,574 |
| VP1 | mutation | 1 | 4,929 |
| VP1 | output inspection | 2 | 1,192 |
| VP1 | status / readiness | 1 | 573 |
| VP1 | diagnostics | 1 | 103 |
| VP2 | component discovery | 13 | 52,025 |
| VP2 | schema / metadata | 23 | 97,502 |
| VP2 | structural observation | 14 | 358,203 |
| VP2 | mutation | 7 | 173,259 |
| VP2 | status / readiness | 8 | 4,547 |
| VP2 | diagnostics | 4 | 416 |
| VP3 | component discovery | 40 | 61,185 |
| VP3 | schema / metadata | 11 | 34,570 |
| VP3 | structural observation | 14 | 231,781 |
| VP3 | mutation | 5 | 88,028 |
| VP3 | export / visual | 3 | 8,186 |
| VP3 | status / readiness | 2 | 1,140 |
| VP3 | diagnostics | 1 | 104 |

Total canonical source-result volume was 41,691 bytes for VP1, 685,952 bytes
for VP2, and 424,994 bytes for VP3.

VP2 and VP3 source volume was dominated by repeated full graph-bearing
responses:

- VP2 `gh_snapshot`: 14 calls, 358,203 bytes (52.2%).
- VP2 `gh_edit`: 7 calls, 173,259 bytes (25.3%).
- VP3 `gh_snapshot`: 14 calls, 231,781 bytes (54.5%).
- VP3 `gh_edit`: 5 calls, 88,028 bytes (20.7%).

This does **not** mean these bytes all entered Qwen's prompt. Qwen frequently
assigned a full Python result to a variable and printed only selected facts.
The source log deliberately preserves the authentic full envelope for audit.

### Prime-Visible Tool-Result Text

| Row | IPython result cells | Retained text bytes | Canonical source-result bytes |
|---|---:|---:|---:|
| VP1 | 29 | 42,077 | 41,691 |
| VP2 | 46 | 57,167 | 685,952 |
| VP3 | 43 | 87,234 | 424,994 |

VP2's largest statically attributable Prime-visible categories were schema and
metadata (20,192 bytes), component discovery (10,746), structural observations
(4,163), and status/readiness (1,241). Another 10,084 bytes came from cells
containing mixed gateway categories, and 10,540 bytes came from non-gateway
IPython work.

VP3's largest were schema and metadata (33,182 bytes), component discovery
(22,960), structural observations (13,456), non-gateway work (9,141), and mixed
gateway cells (4,055).

Static attribution is intentionally conservative. A cell using a helper or a
dynamic tool name can be reported as mixed or unattributed rather than guessed.

## Native Session Footprint

Measured selected session content:

| Row | Total bytes | Thinking | Tool-result text | IPython arguments | Assistant text |
|---|---:|---:|---:|---:|---:|
| VP1 | 104,662 | 45,552 | 42,077 | 8,936 | 6,665 |
| VP2 | 247,132 | 152,606 | 57,167 | 31,753 | 4,204 |
| VP3 | 226,193 | 105,146 | 87,234 | 29,575 | 2,860 |

For VP2, retained thinking text was 61.7% of these selected bytes, tool-result
text 23.1%, and IPython arguments 12.8%. For VP3 the corresponding shares were
46.5%, 38.6%, and 13.1%.

This establishes that information retrieval is not the only context-growth
source. Qwen's own retained reasoning and code were at least as important in
VP2. It also explains why shrinking source-log envelopes alone is unlikely to
produce proportional provider-token savings.

## Repeated Retrieval

### VP1

VP1 had no exact request repeats and no mechanically admitted near-repeat
group. Its later four `rook_tools_search` calls (`circle data`, `get data`,
`component data`, and `radius center`) were semantically related attempts to
find an output-inspection route, but the closed analyzer does not label them
duplicates. They culminated in one schema read and two focused
`gh_inspect_output` calls.

### VP2

Before the first edit at source sequence 39, VP2 made all 36 of its discovery
and schema/metadata calls. The first edit began at model turn 29, after 760,257
cumulative provider-reported tokens had already been processed.

Six successful schema reads were repeated with exact identical results:

| Schema | Sequences | Repeated canonical bytes |
|---|---|---:|
| `gh_edit` | 1, 8 | 3,606 |
| `gh_snapshot` | 2, 9 | 1,734 |
| `gh_batch_component_info` | 3, 10 | 1,341 |
| `gh_library` | 4, 18 | 1,051 |
| `gh_status` | 5, 12 | 435 |
| `gh_wait_for_solve_readiness` | 7, 11 | 733 |

These six second reads retained 8,900 canonical source bytes. They occurred
across two additional model/tool turns, turns 5 and 6, that caused the
accumulated conversation to be processed again. The traces prove the turns and
cumulative inputs, but not the counterfactual token saving had the reads been
omitted.

The ten `gh_batch_component_info` calls requested 66 selector occurrences but
only 41 unique selectors. The 25 repeats included `Number Slider` four times;
Circle, Construct Domain, Construct Point, Line, List Item, Revolve, Rotate 3D,
and Series three times each; and several two-time repeats. Sequence 31 even
contained the same GUID twice in one request.

The first three broad metadata requests, sequences 15-17, substantially
overlapped. The two `Circle` searches at sequences 19 and 20 used different
limits but the same normalized search. Searches 29 and 32 were also semantic
rephrasings for a line between points, although they are not mechanically
classified as duplicates.

Repeated snapshots, status, and diagnostics were stateful:

- Seven exact `include_data=false` snapshots occurred at sequences 38, 44, 49,
  51, 53, 58, and 63. Their results differed as epochs and graph state changed.
- Seven `include_data=true` snapshots shared the same broad projection shape,
  but varied in preview limit, receipt fence, or live state.
- Six `gh_status` calls used identical arguments but returned changing state.
- Four `gh_errors` calls remained clean, but followed different mutation
  points.

Those observations are repetition, not established waste. The final two
`gh_status` and `gh_errors` calls after the receipt-fenced sequence 66 snapshot
are the clearest avoidable pair because the admitted snapshot already included
clean diagnostics and no named material uncertainty remained.

### VP3

VP3 made 51 discovery/schema calls before its first edit at source sequence 52.
The first edit began at model turn 21, after 494,551 cumulative reported tokens.

Unlike VP2, its 17 metadata selector occurrences were all unique. Its clearest
discovery repeats were:

- `gh_library(search="line", limit=10)` repeated exactly at sequences 30 and
  46, returning the same 2,753 canonical bytes the second time.
- A third exact-name `Line` search at sequence 43 belongs to the same normalized
  subject but had different request semantics.
- General and exact searches repeated the Radians subject at sequences 33 and
  41.

VP3 also issued 12 separate `rook_tools_search` calls, including broad
`grasshopper` and `gh` searches followed by individual searches for snapshot,
edit, status, errors, library, component, solve, readiness, wait, and bake.
Seven schema reads followed.

Its snapshot repetition was again mostly stateful: five
`include_data=true,max_preview_items=3` calls, two preview-2 calls, five
`include_data=false` calls, and the final receipt-fenced snapshot. The second
bake after that final snapshot was not necessary to decide whether the
Grasshopper task was complete.

## Materially Sufficient Evidence Tails

This section is an independent judgment over the retained task intent,
topology, solved outputs, control tests, and diagnostics. It is not produced by
the mechanical analyzer.

### VP2

VP2 first possessed materially sufficient **artifact** evidence when the
receipt-fenced source sequence 57 snapshot was returned. At the following model
turn, turn 42:

- 45 components and 62 wires were present;
- diagnostics were clean;
- twelve interpolated and rotated ribs plus the revolution Brep were solved;
- seven meaningful controls and the assumptions panel were present; and
- Span/Ribs had already been perturbed and restored.

At the start of turn 42 the provider reported a 75,342-token input context.
The campaign had already processed 1,662,708 cumulative tokens. Another
410,980 tokens were processed from turn 42 through termination.

After sequence 57 Qwen:

1. captured another structural snapshot;
2. perturbed Curve and Rot;
3. captured status, data, and diagnostics;
4. captured another structural snapshot;
5. restored Curve and Rot;
6. waited on the restoration receipt;
7. captured the final receipt-fenced sequence 66 snapshot;
8. called `gh_status` and `gh_errors` once more;
9. generated a long summary; and
10. called `goal.complete()`.

The Curve/Rot test and restoration improved the evidence and were materially
relevant. A stronger fully exercised boundary was reached when Qwen received
the sequence 66 snapshot at turn 45. That turn started with an 81,426-token
context after 1,903,490 cumulative tokens. The remaining status/error check,
summary, and dedicated completion turn consumed 170,198 more tokens and caused
the first reported ceiling overshoot.

### VP3

VP3's initial graph was healthy earlier, but the user explicitly required
important controls to be exercised. Materially sufficient evidence therefore
arrived only after the control changes and the receipt-fenced source sequence
74 snapshot. Qwen first possessed and interpreted it at turn 41:

- all requested principal controls had been exercised;
- 25 components and 43 wires were present;
- 14 transformed profiles and one Loft Brep were solved;
- diagnostics were clean; and
- the latest receipt and snapshot were correlated.

Turn 41 started with an 80,878-token context after 1,893,241 cumulative tokens.
The remaining two turns consumed 163,899 tokens. Instead of completing, Qwen
baked all outputs again, then attempted another canvas image. The provider
ceiling terminated the row before completion.

## Intervention Boundaries

### 1. Versioned-skill guidance

Candidate intervention: add one session-local evidence-reuse rule to the
existing Grasshopper skill.

Expected benefit:

- directly addresses VP2's six exact repeated schema reads and 25 repeated
  metadata selectors;
- may reduce turns, which reduces repeated processing of the entire accumulated
  context;
- preserves the current adapter, evidence source log, receipt discipline, and
  model-led reasoning loop; and
- is easy to isolate in one unchanged VP2 retest.

Risks:

- Qwen may follow the instruction inconsistently;
- overly broad wording could discourage a justified refresh after refusal,
  target drift, or contradictory evidence; and
- fewer calls do not guarantee fewer tokens if Qwen substitutes longer private
  reasoning.

### 2. IPython-local caching or projection through the existing adapter

The current Actor already receives Python objects, stores them in variables,
and often prints summaries. VP2's 685,952 canonical source-result bytes became
only 57,167 retained tool-result text bytes. Exact adapter caching would still
require a model turn when Qwen unnecessarily called the method, and returning a
cached payload would still place that payload in the session if printed.

A more aggressive projection could reduce visible bytes, but it risks hiding
ports, diagnostics, partial commits, or graph state. It would also change the
qualified payload-first adapter contract. The evidence does not yet justify
that risk, especially because large snapshot/edit source envelopes were mostly
already projected by Qwen before entering conversational text.

### 3. Prime transcript compaction

Compaction directly targets repeated processing of an 80K-plus-token history
and could provide the largest theoretical reduction. It is also the largest and
least evidenced intervention:

- no retained counterfactual shows which history can be removed without harming
  Qwen's Grasshopper judgment;
- compaction must preserve target identity, resolved component/port facts,
  mutation custody, receipts, errors, assumptions, and user intent;
- a faulty summary could increase retries or semantic failure; and
- it modifies Prime rather than the local Grasshopper behavior that produced
  the clearest measured repetition.

Compaction is a later candidate if call reduction leaves cumulative input
unacceptably high. It is not the KISS first experiment.

## Single Recommended Intervention

Recommend exactly one **versioned-skill evidence-reuse rule**:

> Treat successful capability schemas, component discovery, and component
> metadata as session-local evidence. Retain and reuse them. Repeat a request
> only when a refusal, changed runtime or target identity, or contradictory
> live evidence makes a named fact stale; when new component facts are needed,
> request only the missing selectors.

This is guidance, not a hard call budget, cache, supervisor, or semantic gate.
It does not tell Qwen which components to choose or when the design is good. It
only asks the model not to reacquire facts it already possesses without a named
reason.

## Controlled VP2 Retest

Freeze the VP2 prompt, Qwen3.8 27B model, low thinking, Prime runtime, Rook
build, adapter, checkpoint protocol, target baseline, evaluator silence,
receipt-fenced completion flow, and existing resource limits. Change only the
versioned skill bytes by adding the rule above.

Predeclared primary success metrics:

1. No exact repeated successful `rook_tools_read` request.
2. No repeated metadata selector after successful resolution unless the trace
   retains one of the rule's named stale-evidence triggers.
3. Fewer than the VP2 baseline's 36 discovery/schema calls.
4. A mechanically healthy canopy artifact with no material regression in
   controls, assumptions, curves/Brep output, or diagnostics.
5. A receipt-fenced final snapshot followed by honest `goal.complete()` within
   the two-million-token and 1,800-second limits.

Secondary measurements:

- model turns versus the baseline 46;
- final input context versus 85,407 tokens;
- cumulative provider input versus 2,012,994 tokens;
- provider tokens before first mutation versus 760,257;
- repeated selector occurrences versus 25; and
- time and tokens from the first materially sufficient fenced snapshot to
  completion.

Interpretation remains conservative. One improved retest is a screening result,
not proof of causality or a default-policy promotion. If schema/metadata
repetition falls but cumulative input does not, that would weaken the case that
retrieval discipline is sufficient and strengthen the case for separately
studying Prime transcript compaction. If retrieval falls and semantic quality
also falls, the guidance is too restrictive and should not ship.

## Bounded Conclusion

The largest measured operational multiplier is repeated full-context
processing across many turns. The clearest avoidable antecedent in VP2 is not a
large individual tool payload: it is reacquisition of already successful
schema and metadata facts, followed by extra turns over a growing transcript.

The evidence does not justify adapter caching, payload projection changes, or
Prime compaction as the first move. One skill-level evidence-reuse rule is the
smallest controlled intervention that directly addresses an observed behavior
without changing authority, semantics, evidence custody, or orchestration.

Implementation and live retesting remain stopped for independent review.
