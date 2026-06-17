# Threshold Calibration Fixture v1 -- design

> **Status (2026-06-17): DESIGN APPROVED (brainstorm complete) -- ready for writing-plans.**
> Slice owner: spatial-intelligence track, branch `feature/spatial-intelligence`
> (worktree `C:/Users/aryan/source/repos/rook-spatial`; `main` untouched).
>
> This slice resumes the spatial-intelligence track after the RookBIM export preset work. PR #263
> now provides Revit-derived `.3dm` fixture bundles with stable object join keys, sidecars,
> validation files, readable layer/object organization, and relationship indexes. This slice uses
> those bundles to evaluate and tune the `contains_semantic` read-model heuristics without changing
> runtime thresholds automatically.

---

## 1. Problem & goal

Semantic Containment Refinement v1 is intentionally provisional. It refines bbox `contains` edges
into `contains_semantic` edges using only runtime scene-graph evidence, but its ordinal thresholds
(`MARGIN_EPS`, depth fractions, volume-ratio cutoffs, and thin-container penalties) were not
calibrated against labeled real-model fixtures. Earlier live smoke showed a high positive rate on
`SpatialTest.3dm`, which suggests the heuristic may be too permissive.

RookBIM preset exports now provide a labeled fixture source:

- Rhino geometry exported as Breps where convertible.
- Stable Rhino object user strings: `revit.uniqueId`, `revit.elementId`, `revit.category`.
- Readable object names and nested `RookBim > Level > Category` layers.
- Sidecar and validation files with element records, room records, level/host/room labels, and
  `relationshipIndex` sections for `roomMembership`, `hostMembership`, and `levelMembership`.

**Goal of v1:** build a pure calibration library plus a gated live script that runs the existing
runtime read-model stack against one exported fixture bundle, joins Rook's inferred containment
candidates back to Revit sidecar facts by `revit.uniqueId`, and writes a JSON calibration report
plus a compact Markdown summary. The report identifies supported positives, contradicted positives,
missed labeled relations, ambiguous cases, and threshold-tuning observations. No automatic threshold
changes happen in this slice.

### Honesty invariant

Revit labels are **evaluation annotations only**. They are never passed into the runtime scene graph,
exact-adjacency projector, semantic containment refiner, or any runtime evidence model. The runtime
inference remains blind to Revit labels; calibration joins labels only after inference.

This prevents the slice from training or validating the heuristic against metadata that the runtime
does not have in normal pure-spatial contexts.

### In scope

- A pure Python calibration module under `mcp_server/src/rook/scene/calibration.py`.
- Fixture parsing and validation for one `.3dm` + `.sidecar.json` + `.validation.json` bundle.
- Runtime-output joining by `revit.uniqueId`.
- Per-label-family comparison buckets for host, room, and level labels.
- JSON report plus compact Markdown summary.
- A gated live script that imports/opens the fixture in live Rhino/Rook, runs existing read-model
  surfaces, and writes report artifacts.
- A limited offline fixture-validation mode that verifies bundle hygiene and report schema shape.

### Out of scope

- No threshold mutation, config writes, or automatic retuning.
- No MCP tool in v1.
- No new Rhino/Rook native route.
- No point-in-solid or exact containment engine.
- No aggregate accuracy/F1 claim across host/room/level.
- No use of Revit facts as runtime evidence.
- No multi-fixture execution in v1, although the report schema is shaped for future multi-fixture
  aggregation.

---

## 2. Architecture & placement

The durable logic lives in a pure, deterministic Python library:

```text
mcp_server/src/rook/scene/calibration.py
```

Responsibilities:

- Parse and validate fixture sidecar/validation files.
- Normalize sidecar elements, room records, and relationship indexes.
- Validate report inputs from the live runner.
- Build the runtime-object-to-Revit join map from object metadata.
- Classify candidates into per-label-family buckets.
- Compute review counts and per-family/per-category-pair metrics.
- Build a JSON report dictionary.
- Render the compact Markdown summary as a string.
- Provide `write_report_bundle(...)` as the only disk-writing helper.

The core model/report builder returns Python data structures and Markdown strings. It performs no
HTTP calls, Rhino discovery, process launching, direct live-Rhino operations, or filesystem writes.
Only `write_report_bundle(...)` touches disk.

The live orchestration is a thin gated script, likely:

```text
docs/rook_docs/rookbim-export-spike/live_calibrate_containment_fixture.py
```

Responsibilities:

- Resolve the one fixture bundle.
- Discover live Rook/Rhino.
- Prefer a fresh/isolated Rhino document.
- Open or import the `.3dm`.
- Capture the imported object set if a fresh document boundary cannot be guaranteed.
- Call the existing scene graph, exact adjacency projection, and containment refinement surfaces.
- Pass runtime outputs into `calibration.py`.
- Write the JSON and Markdown reports through `write_report_bundle(...)`.

This remains a research/evaluation workflow. It should not be exposed as an MCP tool until the UX,
report shape, and threshold-review workflow prove stable.

---

## 3. Modes

### `live_calibration`

The only mode that computes calibration metrics. It requires live Rhino/Rook and a fixture `.3dm`
loaded into a clean or isolated runtime context.

Live mode records:

- Scene graph sequence.
- Whether a fresh/isolated document was used.
- Imported object count and imported object ids where available.
- Joined object count.
- Evaluated object count.
- Category filters and object cap.
- Whether `scene_exact_neighbors` ran.
- Whether `scene_refine_containment` ran.
- Runtime route/tool status and route errors where available.
- Whether exact adjacency evidence was available to containment refinement.

### `offline_fixture_validation`

A limited hygiene mode. It:

- Resolves paths.
- Parses sidecar and validation JSON.
- Verifies required relationship indexes exist.
- Verifies element records contain join keys.
- Verifies sidecar/validation counts are internally coherent enough for calibration.
- Emits a schema-shaped report with `mode: "offline_fixture_validation"`.

It does **not** open Rhino, sync the scene graph, project exact adjacency, run semantic containment,
classify candidates, compute heuristic metrics, or claim calibration signal.

---

## 4. Live data flow

1. Resolve exactly one fixture bundle: `.3dm`, `.sidecar.json`, `.validation.json`.
2. Parse and validate the sidecar/validation through `calibration.py`.
3. Open/import the `.3dm` into a fresh/isolated Rhino document when possible.
4. If a fresh document boundary cannot be guaranteed, capture a clear pre/post imported object set
   and restrict all calibration work to imported fixture object ids.
5. Sync the existing scene graph mirror.
6. Build the object join map from runtime/Rhino object metadata:
   `revit.uniqueId`, `revit.elementId`, `revit.category`, object id, object name, and layer.
7. Select a bounded evaluation object set:
   - default: joined fixture objects with exported Revit join keys;
   - optional category filters;
   - optional cap for large fixtures;
   - calibration preset categories only when requested.
8. Run exact adjacency projection by default:
   `project_exact_adjacency: true`.
9. Run semantic containment refinement on the bounded evaluation object set.
10. Pass runtime outputs plus fixture facts into the pure calibration builder.
11. Write `<name>.calibration.json` and `<name>.calibration.md` through `write_report_bundle(...)`.

`project_exact_adjacency` is configurable and defaults to true. The report records whether it ran
because `scene_refine_containment` uses already-projected `adjacent_exact` edges as a disambiguating
signal. This evaluates the intended stacked read-model while still allowing later comparison against
bbox-only containment.

Metrics must never include pre-existing Rhino objects.

---

## 5. Fixture and runtime inputs

Fixture inputs:

- `sidecar.elements[]`
- `sidecar.rooms[]` / `sidecar.spaces[]` where present
- `sidecar.relationships.roomMembership`
- `sidecar.relationships.hostMembership`
- `sidecar.relationships.levelMembership`
- validation counts, object/layer audit fields, relationship audit fields, and artifact hashes

Runtime inputs:

- Imported runtime object ids.
- Object metadata with `revit.uniqueId`, `revit.elementId`, `revit.category`, name, and layer.
- Scene graph sequence.
- Exact-adjacency projection result when enabled.
- Semantic containment refinement result:
  - candidate ids;
  - container/contained ids;
  - verdict;
  - confidence;
  - reason;
  - evidence list;
  - bbox annotations where available.

The calibration library validates that runtime candidate endpoints can be joined to sidecar facts
before placing them in metric-eligible buckets.

---

## 6. Candidate comparison model

Host, room, and level labels are evaluated separately. They are different label families, not one
containment oracle.

Strength hierarchy:

- **Host membership** is the strongest object-object signal. It is closest to containment,
  attachment, or embedding.
- **Room membership** is spatial context. It is useful for room/space reconstruction and
  false-positive review, but it is not direct object-object containment truth unless one endpoint is
  room/reference geometry.
- **Level membership** is weak context. Same-level does not support containment by itself; level
  comparison is only useful for gross-error detection.

Candidate records include:

- `containerRuntimeId`
- `containedRuntimeId`
- joined Revit identities for both endpoints
- endpoint category/family/type/name/layer
- endpoint host/room/level labels
- Rook verdict/confidence/reason/evidence
- `exactAdjacencyEvidencePresent`
- `comparisonBasis`, for example:
  - `host_unique_id`
  - `same_room`
  - `room_endpoint`
  - `same_level`
  - `none`
- `metricEligible`, for example:

```json
{
  "host": true,
  "room": false,
  "level": false
}
```

Each candidate carries per-family buckets:

- `hostBucket`
- `roomBucket`
- `levelBucket`

It may also carry a coarse `reviewBucket` for human sorting, but `reviewBucket` is not a truth
metric.

---

## 7. Buckets

Per-family buckets:

```text
host_supported_positive
host_contradicted_positive
host_missed_labeled_relation
host_not_applicable
host_missing_label

room_supported_positive
room_contradicted_positive
room_missed_labeled_relation
room_not_applicable
room_missing_label

level_supported_positive
level_contradicted_positive
level_missed_labeled_relation
level_not_applicable
level_missing_label
```

Shared buckets:

```text
ambiguous
not_joinable
```

Bucket rules:

- `*_supported_positive`: Rook produced `contains_semantic`, and the relevant Revit label family
  supports that relation under that family's comparison rules.
- `*_contradicted_positive`: Rook produced `contains_semantic`, and the relevant label family
  contradicts that relation in a meaningful way.
- `*_missed_labeled_relation`: Revit labels indicate a relation that the selected runtime candidate
  set was expected to surface, but Rook produced no positive semantic containment candidate.
- `*_not_applicable`: the label family does not apply to this candidate/category-pair.
- `*_missing_label`: the label family would apply, but one or both endpoints lacks the necessary
  Revit label.
- `ambiguous`: labels exist, but the signals conflict or are unclear enough that the family should
  not be scored as support or contradiction.
- `not_joinable`: one or both runtime endpoints cannot be joined to fixture sidecar facts.

`ambiguous` must not be used as a catch-all for missing or non-applicable labels. This keeps
fixture/data-quality gaps separate from genuinely confusing examples.

---

## 8. Report shape

The JSON report is future-proofed for multi-fixture aggregation but v1 accepts exactly one fixture
per invocation.

```json
{
  "schemaVersion": 1,
  "mode": "live_calibration",
  "generatedAt": "2026-06-17T00:00:00Z",
  "fixtures": [
    {
      "fixtureId": "shell-preset",
      "paths": {
        "model3dm": "C:/.../shell-preset.3dm",
        "sidecar": "C:/.../shell-preset.sidecar.json",
        "validation": "C:/.../shell-preset.validation.json"
      },
      "runtime": {
        "projectExactAdjacency": true,
        "freshDocument": true,
        "graphSequence": 123,
        "sceneExactNeighbors": {
          "attempted": true,
          "succeeded": true,
          "errors": []
        },
        "sceneRefineContainment": {
          "attempted": true,
          "succeeded": true,
          "errors": []
        },
        "inputObjectCount": 2820,
        "joinedObjectCount": 2820,
        "evaluatedObjectCount": 500,
        "categoryFilters": ["Walls", "Floors"],
        "cap": 500
      },
      "summary": {
        "reviewCounts": {},
        "notJoinableCount": 0,
        "ambiguousCount": 42
      },
      "metrics": {
        "byLabelFamily": {
          "host": {},
          "room": {},
          "level": {}
        },
        "byCategoryPair": {},
        "byConfidence": {}
      },
      "candidates": []
    }
  ]
}
```

Offline reports use the same top-level shape and `fixtures[]`, with:

```json
"mode": "offline_fixture_validation"
```

Offline reports omit calibration metrics by contract or mark metric sections as empty with a clear
`metricsComputed: false` flag.

---

## 9. Metrics and review summaries

v1 computes review counts, not global accuracy.

Allowed metric groupings:

- Per label family: host, room, level.
- Per category pair, split by label family.
- Per confidence tier, split by label family.
- Per reason/evidence signal, for threshold-review hotspots.

Prohibited v1 claims:

- No single aggregate accuracy.
- No single precision/recall/F1 across host/room/level.
- No "ground truth" claim for arbitrary object-object containment.
- No automatic threshold recommendation that modifies code.

Suggested threshold adjustments are qualitative observations, such as:

- "High-confidence host-contradicted positives often combine `bbox_margin=weakens` with thin
  container classes; inspect whether the depth threshold is too permissive."
- "Missed host relations frequently lack bbox `contains` candidates; this points to candidate
  generation rather than semantic scoring."
- "Room contradictions cluster around non-room endpoints; treat these as spatial-context review,
  not object-object containment failure."

The Markdown summary includes:

- Fixture identity and mode.
- Runtime settings and route/tool status.
- Object counts and filters/caps.
- Top review counts by label family.
- Category-pair hotspots.
- High-confidence contradicted positives.
- Missed labeled host relations.
- Qualitative threshold observations.
- JSON and Markdown artifact paths.

---

## 10. Error handling

Library failures are structured and deterministic:

- Missing fixture file.
- Invalid JSON.
- Missing required sidecar/validation fields.
- Missing relationship index.
- Sidecar/validation count mismatch.
- Missing join key fields.
- Runtime candidate endpoint not joinable.

Join failures become candidate/report facts, not crashes, unless the fixture has no usable joined
objects at all. Missing labels use `*_missing_label`; non-comparable families use
`*_not_applicable`; real conflicts use `ambiguous`.

Live script behavior:

- Fails before calibration if the `.3dm` import/open fails.
- Requires a fresh/isolated document or a captured imported-object set.
- Restricts all metrics to imported fixture ids.
- Records route availability and route errors.
- Continues if exact adjacency projection fails for some objects, but records projection status and
  errors clearly.
- Fails live calibration if semantic containment refinement fails for the selected object set,
  rather than emitting partial metrics that look authoritative.

---

## 11. Testing

### Unit tests for `calibration.py`

Use synthetic sidecar/validation/runtime outputs. No live Rhino.

Assert:

- Fixture parsing and required relationship index validation.
- Join map creation from runtime metadata to `revit.uniqueId`.
- Runtime candidate records join to sidecar facts.
- Host/room/level bucket classification, including:
  - `*_supported_positive`
  - `*_contradicted_positive`
  - `*_missed_labeled_relation`
  - `*_not_applicable`
  - `*_missing_label`
  - `ambiguous`
  - `not_joinable`
- `comparisonBasis` values.
- `metricEligible` per family.
- JSON report shape with top-level `fixtures[]`.
- Offline mode emits `mode: "offline_fixture_validation"` and does not compute calibration metrics.
- Markdown summary includes key counts and artifact paths.
- Core builder performs no filesystem writes.
- `write_report_bundle(...)` is the only helper that writes report files.
- Revit labels are never present in runtime/refiner input payloads assembled by the live orchestration
  boundary. This is the honesty-invariant regression guard.

### Script-level tests

Source/contract tests with fakes:

- Argument parsing.
- Offline mode path.
- Live mode calls orchestration functions in order.
- `project_exact_adjacency` defaults to true and is recorded.
- Category filter/cap are recorded.
- Fresh-document/imported-object-set boundary is enforced.
- Route/tool status and errors are captured.

### Gated live run

Manual/live verification with Rhino/Rook:

- Use the existing exported RookBIM preset fixture bundle.
- Prefer a fresh/isolated Rhino document.
- Run exact adjacency projection by default.
- Run containment refinement on a bounded joined fixture object set.
- Write JSON + Markdown reports.
- Manually inspect top contradicted and missed cases before any threshold change is proposed.

---

## 12. Dependencies and sequencing

1. Build `calibration.py` as a pure library:
   - fixture parsing;
   - join map;
   - bucket classifier;
   - metric/review-count builder;
   - JSON/Markdown builders;
   - report writer wrapper.
2. Add unit tests for library behavior and honesty invariants.
3. Add the gated live calibration script.
4. Add script-level tests with faked runtime calls.
5. Run offline fixture validation against an existing #263 bundle.
6. Run live calibration against an imported fixture in live Rhino/Rook.

The terminal output of this slice is evidence for a human threshold-review pass. Threshold edits are
a separate approved slice.
