# RookVisionDirector Prepare Take - Metadata-Only Source Graph Design

- **Status:** Draft for review
- **Date:** 2026-06-26
- **Feature:** RookVisionDirector selected-occurrence animation preparation
- **Predecessors:**
  - `docs/superpowers/specs/2026-06-24-rookvisiondirector-animation-compiler-design.md`
  - `docs/superpowers/specs/2026-06-24-rookvisiondirector-replay-native-design.md`
  - `docs/superpowers/specs/2026-06-25-rookvisiondirector-preview-loop-design.md`

## Why This Exists

Real architectural Rhino files are not authored as animation rigs. A user may ask RookVisionDirector to animate the roof, bridge, or L3 elements, but those concepts often appear as top-level block instances on diagram layers whose reachable contents live on material, entourage, setout, and source layers, with further nested block references.

The current Director replay path consumes dense per-frame object transforms, has a 256 unique object cap and an 8 MiB payload cap, and restores/applies poses per frame. That replay contract is useful for small compiled tracks, but it is not the right first substrate for arbitrary nested-block model preparation.

This slice creates the trusted source graph that later materialization and animation compilation can use. It does not create animation geometry, duplicate source objects, create proxy handles, or compile replay tracks.

## Product Rule

Slice one is narrow in input scope and deep in evidence:

- input scope is bounded selected top-level source occurrences;
- every object reachable inside each selected source occurrence gets referenced-only provenance;
- the Rhino file is not dirtied by `prepare_take`;
- generated Rhino actor objects do not exist yet;
- playback cannot target this take directly, by design.

The output is a logical actor graph plus complete sidecar provenance. Later workflows can materialize, split, duplicate, or compile selected actors from this graph.

## Architecture Boundary

Python owns:

- `take_id` generation;
- manifest, JSONL sidecars, audit reports, and storage mode;
- deterministic semantic classification;
- stale-sidecar validation;
- orchestration of native facts;
- cleanup/finalization of partial prepare runs.

Native owns only Rhino-document facts and narrow primitives:

- selected object and occurrence inspection;
- exact nested occurrence traversal when existing routes are insufficient;
- document fingerprint facts;
- accumulated transforms, bounding boxes, layer/material/object facts;
- future bounded materialization primitives, out of this slice.

Sidecar writing is Python-owned in slice one. Native must not write `take_manifest.json`, `provenance_records.jsonl`, or audit reports.

## Out Of Scope

- Whole-document preparation.
- Object duplication or geometry materialization.
- Proxy or visible handle creation.
- Director animation layers.
- Object user strings.
- Source object tagging.
- Replay track compilation.
- Capture/export.
- AI-assisted classification as an authority.
- SQLite storage.
- Embedded full provenance in the `.3dm`.
- Portable export from global storage to document-local storage.

`attach_take` and `detach_take` are separate follow-up operations. They are mentioned here only to define the trust boundary; they are not acceptance criteria for `prepare_take`.

## Input Contract

The first tool/API accepts bounded top-level source occurrences:

```json
{
  "scope": "selected_occurrences",
  "source_object_ids": ["..."],
  "use_current_selection": false,
  "page_size": 500,
  "classify_nested": false,
  "write_markdown_audit": true,
  "portable": false,
  "output_root": null
}
```

Rules:

- `source_object_ids` wins when provided.
- `use_current_selection: true` is allowed for live Rhino workflows.
- If neither `source_object_ids` nor `use_current_selection` is provided, return `missing_source_selection`.
- If both are provided, use explicit ids and include a warning.
- Reject `scope: "document"` with `unsupported_scope`.
- Only top-level document objects or top-level block instances can be actor roots.
- Nested records can appear in provenance, but requested actor roots remain bounded top-level occurrences.

Current Rhino selection is a convenience, not the canonical contract. Repeatable tests and agent workflows should pass explicit `source_object_ids`.

## Storage

Default storage is global:

```text
%LOCALAPPDATA%/Rook/director_takes/<source_fingerprint>/<take_id>/
```

Document-local storage is explicit:

```text
<3dm folder>/.rook/director_takes/<take_id>/
```

Rules:

- Never write beside the `.3dm` unless `portable: true` or `output_root` is explicit.
- If the source document is unsaved, global mode still works.
- If the source document is unsaved and document-local mode is requested, fail with `source_document_unsaved`.
- The manifest records `storage_mode: "global" | "document_local" | "custom_output_root"`.
- Responses always return absolute paths for all produced files.

Required outputs:

- `take_manifest.json`
- `provenance_records.jsonl`
- `audit_report.json`
- `audit_report.md` by default, disabled with `write_markdown_audit: false`

Conditional outputs:

- `classification_events.jsonl` only when correction or classification events exist.

## Atomic Artifact Lifecycle

Python writes into a temporary prepare directory first, then finalizes atomically.

Example:

```text
%LOCALAPPDATA%/Rook/director_takes/<source_fingerprint>/.tmp/<take_id>.<nonce>/
%LOCALAPPDATA%/Rook/director_takes/<source_fingerprint>/<take_id>/
```

Rules:

- A failed paged inventory must not leave a manifest that looks usable.
- If finalization cannot complete, either remove the temp directory or write `prepare_status: "incomplete"` inside the temp artifact only.
- A finalized `take_manifest.json` must include `prepare_status: "complete"`.
- Python computes and records the `provenance_records.jsonl` hash before finalization.
- Consumers must reject finalized artifacts whose manifest is missing, unreadable, hash-inconsistent, or not `prepare_status: "complete"`.

## Manifest Contract

`take_manifest.json` is the compact durable index. It contains pointers and summaries, not full provenance.

Required high-level fields:

```json
{
  "schema_version": 1,
  "take_id": "...",
  "prepare_status": "complete",
  "created_at": "...",
  "generator_version": "...",
  "storage_mode": "global",
  "source_document_fingerprint": {...},
  "input": {...},
  "files": {
    "provenance_records": {
      "path": "provenance_records.jsonl",
      "sha256": "..."
    },
    "audit_report_json": {
      "path": "audit_report.json",
      "sha256": "..."
    },
    "audit_report_markdown": {
      "path": "audit_report.md",
      "sha256": "..."
    }
  },
  "actors": [],
  "inventory_summary": {},
  "validation_status": "valid"
}
```

`inventory_summary` includes:

- total record count;
- actor count;
- page count;
- selected root ids;
- role counts;
- animation relevance counts;
- warning counts;
- provenance JSONL hash;
- referenced-only count;
- materialized count, expected to be zero in slice one.

## Logical Actor Contract

An actor root is a take-local planning entity, not a Rhino object.

```json
{
  "take_id": "...",
  "actor_id": "...",
  "actor_kind": "source_occurrence",
  "representation": "metadata_only",
  "source_top_level_object_id": "...",
  "source_occurrence_key": "...",
  "source_occurrence_path": [...],
  "semantic_group": "bridge",
  "classification_status": "classified"
}
```

Rules:

- `take_id` is generated per prepare run.
- `actor_id` is a generated Rook UUID, stable only within the take.
- `actor_id` is not derived from Rhino object id or deterministic source path.
- Source identity belongs to provenance.
- Repeated prepare runs of the same source selection produce different actor ids.
- Optional future rematching uses `source_occurrence_key` and source snapshots, not `actor_id`.

## Provenance JSONL Contract

`provenance_records.jsonl` contains one JSON object per reachable occurrence/object record.

All reachable source contents are included:

- renderable geometry;
- curves;
- points;
- annotations;
- hatches;
- lights;
- construction and setout helpers;
- nested instance references;
- unknown or unsupported object types.

Each record includes operational classification:

```json
{
  "schema_version": 1,
  "take_id": "...",
  "actor_id": "...",
  "provenance_id": "...",
  "source_occurrence_key": "...",
  "path_hash": "...",
  "source_occurrence_path": [],
  "source_top_level_object_id": "...",
  "source_object_id_or_definition_object_id": "...",
  "source_snapshot": {
    "object_type": "...",
    "object_name": "...",
    "layer_path": "...",
    "material_ref": "...",
    "local_bbox": [[0, 0, 0], [1, 1, 1]],
    "world_bbox": [[0, 0, 0], [1, 1, 1]],
    "world_transform": [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
  },
  "object_role": "renderable",
  "animation_relevance": "candidate",
  "materialization_status": "referenced_only"
}
```

All records in slice one use `materialization_status: "referenced_only"`.

## Fact-Rich Occurrence Paths

Every path is an ordered array from selected top-level occurrence to leaf definition object. Hashes are compact references, not the only explanation.

Each segment includes:

```json
{
  "kind": "top_instance",
  "definition_name": "...",
  "definition_id": "...",
  "definition_object_index": 42,
  "instance_reference_id": "...",
  "sibling_ordinal": 7,
  "object_id": "...",
  "object_name": "...",
  "object_type": "...",
  "layer_path": "...",
  "local_transform": [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]],
  "world_transform": [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]],
  "local_bbox": [[0, 0, 0], [1, 1, 1]],
  "world_bbox": [[0, 0, 0], [1, 1, 1]],
  "segment_fingerprint": "..."
}
```

Rules:

- Path spine uses deterministic native table order or deterministic sort. The ordering method is recorded.
- `source_occurrence_key` and `path_hash` are derived from canonicalized path facts.
- No hash is stored without adjacent facts that explain it.
- Index, name, layer, bbox, or hash changes degrade trust; they do not trigger silent remapping.

## Semantic Classification

Classification is deterministic and evidence-scored. It does not force labels.

Actor roots always receive full classification:

- `classification_status: "classified" | "ambiguous" | "unclassified"`;
- `semantic_group`, nullable;
- ranked `candidate_groups`;
- normalized `evidence`;
- explicit `conflicts`;
- `source: "rule_based"`.

Every reachable provenance record receives operational classification:

- `object_role: "renderable" | "helper" | "annotation" | "construction" | "nested_instance" | "unknown"`;
- `animation_relevance: "candidate" | "unlikely" | "structural_path_node" | "unknown"`;
- `materialization_status: "referenced_only"`.

Nested semantic classification is tiered:

- default nested records may use `classification_status: "not_evaluated"`;
- emit nested `candidate_groups` only when cheap local evidence exists;
- `classify_nested: true` requests deeper nested semantic classification.

`ambiguous` means enough evidence exists but points to multiple plausible groups. `unclassified` means there is not enough useful evidence.

## Audit Reports

`audit_report.json` is the machine contract. `audit_report.md` is deterministic, concise, and default-on for early development review.

The Markdown report includes:

- take id;
- source document summary;
- storage mode;
- selected actor count;
- actor table with short actor id, source name/layer/block, semantic status/group;
- warnings;
- stale or changed facts when applicable;
- ambiguity summaries;
- provenance counts, including referenced-only and materialized counts;
- role and animation relevance counts by actor;
- sidecar file paths.

The Markdown audit must not contain LLM prose, narrative recommendations, or speculative advice. It is a formatted view of structured audit data.

## Validation And Staleness

Validation states in slice one:

- `valid`;
- `stale_warning`;
- `source_missing`;
- `invalid_manifest`.

`actor_missing` is not a slice-one state because there are no generated Rhino actors. Future materialized actors may introduce `generated_asset_missing`.

Stale source state degrades trust but does not make the take unreadable. It blocks only operations that claim source fidelity, such as future split-from-source or refresh-from-source operations.

Audit validation must report:

- changed field;
- previous value summary;
- current value summary;
- severity.

Higher-severity examples include missing source objects, changed block definition structure, changed bbox, changed transform, or path hash changes. Lower-severity examples include document modified time differences when stronger structural facts still match.

## Source Fingerprinting

Use tiered fingerprints:

- cheap document fingerprint: path, size, modified time, Rhino doc serial or runtime serial when available, unit system;
- selected occurrence fingerprint: selected ids, top-level layers, names, object types, transforms, bboxes, block definition names/ids;
- structural traversal fingerprint: ordered reachable path facts and segment fingerprints.

Deep geometry hashing is out of scope and remains opt-in for later work.

## Native Occurrence Inventory

Exact nested inventory is a hard acceptance gate. If existing routes cannot prove stable nested occurrence paths with accumulated transforms, add a narrow read-only native primitive:

```text
POST /director/occurrence-inventory
```

First page request:

```json
{
  "source_object_ids": ["..."],
  "page_size": 500,
  "cursor": null
}
```

Later page request:

```json
{
  "inventory_session_id": "...",
  "page_size": 500,
  "cursor": "..."
}
```

Response:

```json
{
  "schema_version": 1,
  "inventory_session_id": "...",
  "source_document_fingerprint": {},
  "records": [],
  "next_cursor": "...",
  "complete": false,
  "warnings": []
}
```

Rules:

- The route is paged from the start.
- `page_size` has a native max cap.
- `cursor` is opaque.
- Native owns traversal correctness and per-record Rhino facts.
- Python loops pages and writes JSONL.
- Native does not write sidecars.
- Each page repeats enough context to detect drift or session mismatch.

### Inventory Session Consistency

Consistency is strict. Avoid mixed-time provenance.

First page establishes:

- `inventory_session_id`;
- source document fingerprint;
- document runtime serial;
- selected source ids;
- traversal ordering/version;
- page size cap;
- source object count.

Later pages must match that context. If selected ids differ, page size changes unexpectedly, session expires, document runtime serial/fingerprint changes, cursor is invalid, or traversal context no longer matches, native returns `inventory_stale` or `inventory_session_invalid`.

Python treats either error as a failed `prepare_take`, removes or quarantines partial outputs, and reports that the user should retry.

Native does not need to snapshot the full inventory in memory. It holds enough session state to enforce consistency and cursor progression.

## Prepare Flow

1. Validate input shape and selection scope.
2. Resolve explicit object ids or current Rhino selection.
3. Resolve storage mode and create a temporary prepare directory.
4. Obtain source document fingerprint.
5. Inventory selected top-level occurrences and every reachable nested object.
6. Write `provenance_records.jsonl` as inventory pages arrive.
7. Build logical actor records.
8. Run deterministic root classification and tiered nested classification.
9. Build `audit_report.json` and `audit_report.md`.
10. Compute sidecar hashes.
11. Write `take_manifest.json` with `prepare_status: "complete"`.
12. Atomically finalize the artifact directory.
13. Return summary and absolute paths.

## Response Contract

Success:

```json
{
  "take_id": "...",
  "prepare_status": "complete",
  "storage_mode": "global",
  "source_document_fingerprint": {},
  "actor_count": 3,
  "provenance_record_count": 12034,
  "validation_status": "valid",
  "paths": {
    "take_manifest": "C:/...",
    "provenance_records": "C:/...",
    "audit_report_json": "C:/...",
    "audit_report_markdown": "C:/..."
  },
  "warnings": []
}
```

Errors include:

| code | when |
|---|---|
| `missing_source_selection` | no explicit ids and no current selection requested/found |
| `unsupported_scope` | `scope` is not `selected_occurrences` |
| `source_document_unsaved` | document-local storage requested for an unsaved source document |
| `source_object_not_found` | requested top-level source id is absent |
| `unsupported_actor_root` | requested id cannot be a top-level actor root |
| `inventory_stale` | document changed during paged inventory |
| `inventory_session_invalid` | cursor/session/context mismatch |
| `inventory_incomplete` | exact reachable inventory could not be proven |
| `artifact_write_failed` | sidecar temp/final write failed |
| `invalid_manifest` | generated manifest failed self-validation |

## Acceptance Criteria

- `prepare_take` is external-only and does not dirty the active Rhino document.
- No object user strings are written.
- No source objects are modified.
- No generated Rhino actor/proxy/duplicate objects are created.
- Selected top-level occurrences become logical actor records.
- Every reachable object under each selected occurrence has a provenance JSONL record.
- All slice-one provenance records are `materialization_status: "referenced_only"`.
- Fact-rich occurrence paths include enough data to distinguish repeated nested definition uses.
- Deterministic actor-root classification supports `classified`, `ambiguous`, and `unclassified`.
- Nested records always get `object_role` and `animation_relevance`.
- Sidecars are written through a temp-then-finalize lifecycle.
- Finalized manifests cannot appear usable after failed inventory.
- The audit Markdown is deterministic and generated from structured audit data.
- If exact nested occurrence paths and accumulated transforms cannot be produced with existing routes, `/director/occurrence-inventory` is implemented before claiming slice-one completion.

## Deferred Work

- `attach_take` writes minimal document user strings that point to a manifest.
- `detach_take` clears attached document pointers.
- Source object tagging.
- Generated actor object creation.
- Proxy/handle creation.
- Explicit duplicate/materialize operations.
- Compiling selected actors into replay tracks.
- Portable export from global to document-local storage.
- SQLite-backed indexed provenance.
- AI-assisted classification.
- Full geometry hashing.
